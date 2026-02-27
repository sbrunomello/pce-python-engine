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
from pce.core.plugins import PluginRegistry
from pce.core.types import ExecutionResult
from pce.de.engine import DecisionEngine
from pce.epl.processor import EventProcessingLayer
from pce.isi.integrator import InternalStateIntegrator
from pce.plugins.llm_assistant import (
    AssistantAdaptationPlugin,
    AssistantDecisionPlugin,
    AssistantStorage,
    AssistantValueModelPlugin,
    OpenRouterClient,
)
from pce.plugins.llm_assistant.config import load_openrouter_credentials
from pce.plugins.robotics import (
    RoboticsAdaptationPlugin,
    RoboticsDecisionPlugin,
    RoboticsStorage,
    RoboticsValueModelPlugin,
)
from pce.sm.manager import StateManager
from pce.vel.evaluator import ValueEvaluationLayer

settings = Settings()
app = FastAPI(title="PCE API", version="0.1.0")

# Composition root: dependencies are instantiated once and kept independent by contracts.
epl = EventProcessingLayer(settings.event_schema_path)
isi = InternalStateIntegrator()
vel = ValueEvaluationLayer()
sm = StateManager(settings.db_url)
de = DecisionEngine()
ao = ActionOrchestrator()
afs = AdaptiveFeedbackSystem()
cci_metric = CCIMetric()

plugin_registry = PluginRegistry()
robotics_storage = RoboticsStorage(sm)
assistant_storage = AssistantStorage(sm)
assistant_value_model = AssistantValueModelPlugin()
openrouter_credentials = load_openrouter_credentials()
assistant_client = OpenRouterClient(
    api_key=openrouter_credentials["api_key"],
    model=openrouter_credentials["model"],
    base_url=openrouter_credentials["base_url"],
    timeout_s=float(openrouter_credentials["timeout_s"]),
    referer=openrouter_credentials["referer"],
    title=openrouter_credentials["title"],
)
plugin_registry.register_value_model(RoboticsValueModelPlugin())
plugin_registry.register_value_model(assistant_value_model)
plugin_registry.register_decision(RoboticsDecisionPlugin(robotics_storage))
plugin_registry.register_decision(
    AssistantDecisionPlugin(assistant_storage, assistant_value_model, assistant_client)
)
plugin_registry.register_adaptation(RoboticsAdaptationPlugin(robotics_storage))
plugin_registry.register_adaptation(AssistantAdaptationPlugin(assistant_storage))


class EventIn(BaseModel):
    """Raw event API input model."""

    event_type: str
    source: str
    payload: dict[str, object]


@app.post("/events")
def process_event(event_in: EventIn) -> dict[str, object]:
    """End-to-end event processing pipeline entrypoint with plugin dispatch."""
    try:
        event = epl.ingest(event_in.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    state = sm.load_state()
    updated_state = isi.integrate(state, event)
    sm.remember_event(event)

    value_score = plugin_registry.evaluate(event, updated_state, fallback=vel.evaluate_event)

    cci, components = cci_metric.from_state_manager(sm)
    cci_payload = {
        "decision_consistency": components.decision_consistency,
        "priority_stability": components.priority_stability,
        "contradiction_rate": components.contradiction_rate,
        "predictive_accuracy": components.predictive_accuracy,
    }
    plan = plugin_registry.deliberate(
        event,
        updated_state,
        value_score,
        cci,
        fallback=de.deliberate,
    )
    explain = plan.metadata.get("explain")
    if isinstance(explain, dict):
        cci_explain = explain.get("cci")
        if isinstance(cci_explain, dict):
            cci_explain["components"] = cci_payload

    if event.event_type.startswith("feedback."):
        result = ExecutionResult(
            action_type=event.event_type,
            success=True,
            observed_impact=float(event.payload.get("reward", 0.0)),
            notes="feedback ingestion",
            metadata={"feedback": event.payload},
        )
    else:
        result = plugin_registry.execute(plan, fallback=ao.execute)

    adapted_state = plugin_registry.adapt(updated_state, event, result, fallback=afs.adapt)
    sm.save_state(adapted_state)

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
        metadata={"rationale": plan.rationale, "plan_metadata": plan.metadata},
    )

    cci, components = cci_metric.from_state_manager(sm)
    cci_payload = {
        "decision_consistency": components.decision_consistency,
        "priority_stability": components.priority_stability,
        "contradiction_rate": components.contradiction_rate,
        "predictive_accuracy": components.predictive_accuracy,
    }
    sm.save_cci_snapshot(
        cci_id=str(uuid4()),
        cci=cci,
        metrics=cci_payload,
    )

    action_payload = plan.metadata.get("action_payload", plan.action_type)
    response: dict[str, object] = {
        "event_id": event.event_id,
        "value_score": value_score,
        "cci": cci,
        "cci_components": cci_payload,
        "action_type": plan.action_type,
        "action": action_payload,
        "metadata": plan.metadata,
        "success": result.success,
    }

    if event.event_type.startswith("feedback."):
        q_update = adapted_state.get("robotics_rl")
        response["updated"] = bool(q_update)
        response["epsilon"] = q_update.get("epsilon") if isinstance(q_update, dict) else None
        response["q_update"] = q_update if isinstance(q_update, dict) else {}
        assistant_learning = adapted_state.get("assistant_learning")
        if isinstance(assistant_learning, dict):
            response["assistant_learning"] = assistant_learning
            explain_metadata = response.get("metadata")
            if isinstance(explain_metadata, dict):
                explain_payload = explain_metadata.get("explain")
                if isinstance(explain_payload, dict):
                    explain_payload["afs"] = assistant_learning.get(
                        "afs_explain", {"updated": True}
                    )

    return response


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
    """Reset rover plugin RL policy and episode state."""
    defaults = robotics_storage.clear_policy()
    state = sm.load_state()
    if "robotics" in state:
        state["robotics"] = {}
        sm.save_state(state)
    return {"status": "cleared", "defaults": defaults}


@app.post("/agents/rover/control/reset_stats")
async def reset_rover_stats() -> dict[str, object]:
    """Reset rover runtime local counters without touching RL policy."""
    await rover_runtime.reset_stats()
    await rover_runtime.broadcast(rover_runtime._frame_payload({"type": "robot.stop"}))
    return {"status": "stats_reset"}


@app.post("/agents/assistant/control/clear_memory")
def clear_assistant_memory() -> dict[str, object]:
    """Reset assistant plugin memory/policy and clear assistant state slice."""
    deleted = assistant_storage.clear_all()
    state = sm.load_state()
    if "assistant" in state:
        state["assistant"] = {}
    if "assistant_learning" in state:
        state["assistant_learning"] = {}
    sm.save_state(state)
    return {"status": "cleared", "deleted": deleted, "epsilon": 0.6}


app.include_router(rover_router)
