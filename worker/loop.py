"""Example continuous processing loop for background workers."""

from __future__ import annotations

import time
from uuid import uuid4

from pce.afs.feedback import AdaptiveFeedbackSystem
from pce.ao.orchestrator import ActionOrchestrator
from pce.core.cci import CCIMetric
from pce.core.config import Settings
from pce.de.engine import DecisionEngine
from pce.epl.processor import EventProcessingLayer
from pce.examples.scenarios import financial_event_example, robot_event_example
from pce.isi.integrator import InternalStateIntegrator
from pce.sm.manager import StateManager
from pce.vel.evaluator import ValueEvaluationLayer


def run_loop(iterations: int = 10, sleep_s: float = 0.05) -> None:
    """Run deterministic processing loop showcasing CCI evolution over time."""
    settings = Settings()
    epl = EventProcessingLayer(settings.event_schema_path)
    isi = InternalStateIntegrator()
    vel = ValueEvaluationLayer()
    sm = StateManager(settings.db_url)
    de = DecisionEngine()
    ao = ActionOrchestrator()
    afs = AdaptiveFeedbackSystem()
    cci_metric = CCIMetric()

    events = [financial_event_example(), robot_event_example()]
    for index in range(iterations):
        raw = events[index % len(events)]
        event = epl.ingest(raw)
        state = sm.load_state()
        updated = isi.integrate(state, event)
        sm.remember_event(event)

        value_score = vel.evaluate_event(event, updated.get("strategic_values"))
        cci_before, _ = cci_metric.from_state_manager(sm)
        plan = de.deliberate(updated, value_score, cci_before)
        result = ao.execute(plan)

        violated_values = [] if value_score >= 0.6 else ["long_term_coherence"]
        sm.remember_action(
            action_id=str(uuid4()),
            event_id=event.event_id,
            action_type=plan.action_type,
            priority=plan.priority,
            value_score=value_score,
            expected_impact=float(plan.metadata.get("expected_impact", 0.5)),
            observed_impact=result.observed_impact,
            respected_values=len(violated_values) == 0,
            violated_values=violated_values,
            metadata={"source": "worker.loop", "iteration": index},
        )

        cci_after, components = cci_metric.from_state_manager(sm)
        sm.save_cci_snapshot(
            cci_id=str(uuid4()),
            cci=cci_after,
            metrics={
                "decision_consistency": components.decision_consistency,
                "priority_stability": components.priority_stability,
                "contradiction_rate": components.contradiction_rate,
                "predictive_accuracy": components.predictive_accuracy,
            },
        )

        result.metadata["violated_values"] = violated_values
        sm.save_state(afs.adapt(updated, result))

        print(
            f"[{index:02d}] event={event.event_type} action={plan.action_type} "
            f"cci_before={cci_before:.3f} cci_after={cci_after:.3f} value={value_score:.3f}"
        )
        time.sleep(sleep_s)


if __name__ == "__main__":
    run_loop()
