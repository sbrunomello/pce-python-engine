"""Minimal FastAPI interface for PCE."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from pce.afs.feedback import AdaptiveFeedbackSystem
from pce.ao.orchestrator import ActionOrchestrator
from pce.core.cci import CCIInput, CCIMetric
from pce.core.config import Settings
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
de = DecisionEngine()
ao = ActionOrchestrator()
afs = AdaptiveFeedbackSystem()
cci_metric = CCIMetric()


class EventIn(BaseModel):
    """Raw event API input model."""

    event_type: str
    source: str
    payload: dict[str, object]


@app.post("/events")
def process_event(event_in: EventIn) -> dict[str, object]:
    """End-to-end event processing pipeline entrypoint."""
    try:
        event = epl.ingest(event_in.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    state = sm.load_state()
    updated_state = isi.integrate(state, event)
    sm.remember_event(event)

    value_score = vel.evaluate_event(event)
    cci = cci_metric.compute(
        CCIInput(
            decision_consistency=min(1.0, 0.55 + 0.01 * sm.recent_event_count()),
            priority_stability=0.7,
            contradiction_rate=0.1,
            predictive_accuracy=0.65,
        )
    )
    plan = de.deliberate(updated_state, value_score, cci)
    result = ao.execute(plan)
    adapted_state = afs.adapt(updated_state, result)
    sm.save_state(adapted_state)

    return {
        "event_id": event.event_id,
        "value_score": value_score,
        "cci": cci,
        "action": plan.action_type,
        "success": result.success,
    }


@app.get("/cci")
def get_cci() -> dict[str, float]:
    """Expose current CCI approximation."""
    cci = cci_metric.compute(
        CCIInput(
            decision_consistency=min(1.0, 0.55 + 0.01 * sm.recent_event_count()),
            priority_stability=0.72,
            contradiction_rate=0.12,
            predictive_accuracy=0.66,
        )
    )
    return {"cci": cci}
