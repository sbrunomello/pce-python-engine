"""Minimal FastAPI interface for PCE."""

from __future__ import annotations

from uuid import uuid4

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from agents.rover import router as rover_router
from agents.rover.app import runtime as rover_runtime
from pce.afs.feedback import AdaptiveFeedbackSystem
from pce.ao.orchestrator import ActionOrchestrator
from pce.core.cci import CCIMetric
from pce.core.config import Settings
from pce.core.types import ExecutionResult
from pce.de.engine import DecisionEngine
from pce.epl.processor import EventProcessingLayer
from pce.isi.integrator import InternalStateIntegrator
from pce.sm.manager import StateManager
from pce.vel.evaluator import ValueEvaluationLayer

settings = Settings()
app = FastAPI(title="PCE API", version="0.1.0")

# Composition root: dependencies are instantiated once and kept independent by contracts.
epl = EventProcessingLayer(settings.event_schema_path)
isi = InternalStateIntegrator()
vel = ValueEvaluationLayer()
sm = StateManager(settings.db_url)
de = DecisionEngine(sm)
ao = ActionOrchestrator()
afs = AdaptiveFeedbackSystem(sm)
cci_metric = CCIMetric()


class EventIn(BaseModel):
    """Raw event API input model."""

    event_type: str
    source: str
    payload: dict[str, object]


@app.post("/events")
def process_event(event_in: EventIn) -> dict[str, object]:
    """End-to-end event processing pipeline entrypoint with real CCI computation."""
    try:
        event = epl.ingest(event_in.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    state = sm.load_state()
    updated_state = isi.integrate(state, event)
    sm.remember_event(event)

    strategic_values = updated_state.get("strategic_values")
    value_score = vel.evaluate_event(
        event, strategic_values if isinstance(strategic_values, dict) else None
    )

    domain = event.payload.get("domain")
    event_type = event.event_type

    if domain == "robotics" and event_type.startswith("feedback.robotics"):
        feedback_result = ExecutionResult(
            action_type="robotics.feedback",
            success=True,
            observed_impact=float(event.payload.get("reward", 0.0)),
            notes="robotics feedback ingestion",
            metadata={"feedback": event.payload},
        )
        adapted_state = afs.adapt(updated_state, feedback_result)
        sm.save_state(adapted_state)

        cci, components = cci_metric.from_state_manager(sm)
        q_update = adapted_state.get("robotics_rl", {})
        return {
            "event_id": event.event_id,
            "updated": bool(q_update),
            "epsilon": q_update.get("epsilon"),
            "q_update": q_update,
            "value_score": value_score,
            "cci": cci,
            "cci_components": {
                "decision_consistency": components.decision_consistency,
                "priority_stability": components.priority_stability,
                "contradiction_rate": components.contradiction_rate,
                "predictive_accuracy": components.predictive_accuracy,
            },
        }

    cci, components = cci_metric.from_state_manager(sm)
    plan = de.deliberate(updated_state, value_score, cci)
    result = ao.execute(plan)

    violated_values = [] if value_score >= 0.6 else ["long_term_coherence"]
    respected_values = len(violated_values) == 0

    sm.remember_action(
        action_id=str(uuid4()),
        event_id=event.event_id,
        action_type=plan.action_type,
        priority=plan.priority,
        value_score=value_score,
        expected_impact=float(plan.metadata.get("expected_impact", 0.5)),
        observed_impact=result.observed_impact,
        respected_values=respected_values,
        violated_values=violated_values,
        metadata={"rationale": plan.rationale, "robot_action": plan.metadata.get("robot_action")},
    )

    # recompute with new action included and persist to history
    cci, components = cci_metric.from_state_manager(sm)
    sm.save_cci_snapshot(
        cci_id=str(uuid4()),
        cci=cci,
        metrics={
            "decision_consistency": components.decision_consistency,
            "priority_stability": components.priority_stability,
            "contradiction_rate": components.contradiction_rate,
            "predictive_accuracy": components.predictive_accuracy,
        },
    )

    result.metadata["violated_values"] = violated_values
    adapted_state = afs.adapt(updated_state, result)
    sm.save_state(adapted_state)

    action_payload = plan.metadata.get("robot_action", plan.action_type)
    return {
        "event_id": event.event_id,
        "value_score": value_score,
        "cci": cci,
        "cci_components": {
            "decision_consistency": components.decision_consistency,
            "priority_stability": components.priority_stability,
            "contradiction_rate": components.contradiction_rate,
            "predictive_accuracy": components.predictive_accuracy,
        },
        "action_type": plan.action_type,
        "action": action_payload,
        "metadata": plan.metadata,
        "success": result.success,
    }


@app.get("/cci")
def get_cci() -> dict[str, float]:
    """Expose current real-time CCI."""
    cci, _ = cci_metric.from_state_manager(sm)
    return {"cci": cci}


@app.get("/state")
def get_state() -> dict[str, object]:
    """Expose persisted cognitive state."""
    return {"state": sm.load_state()}


@app.get("/cci/history")
def get_cci_history() -> dict[str, object]:
    """Expose historical CCI snapshots."""
    return {"history": sm.get_cci_history()}


@app.post("/agents/rover/control/clear_policy")
def clear_rover_policy() -> dict[str, object]:
    """Reset persisted robotics RL policy and hyperparameters."""
    sm.clear_robotics_policy()
    state = sm.load_state()
    if "robotics" in state:
        state["robotics"] = {}
        sm.save_state(state)
    return {"status": "cleared", "defaults": sm.get_robotics_params()}


@app.post("/agents/rover/control/reset_stats")
async def reset_rover_stats() -> dict[str, object]:
    """Reset rover runtime local counters without touching RL policy."""
    await rover_runtime.reset_stats()
    await rover_runtime.broadcast(rover_runtime._frame_payload({"type": "robot.stop"}))
    return {"status": "stats_reset"}


app.include_router(rover_router)
