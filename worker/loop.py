"""Example continuous processing loop for background workers."""

from __future__ import annotations

import time

from pce.core.cci import CCIInput, CCIMetric
from pce.core.config import Settings
from pce.de.engine import DecisionEngine
from pce.epl.processor import EventProcessingLayer
from pce.examples.scenarios import financial_event_example, robot_event_example
from pce.isi.integrator import InternalStateIntegrator
from pce.sm.manager import StateManager
from pce.vel.evaluator import ValueEvaluationLayer


def run_loop(iterations: int = 3, sleep_s: float = 0.2) -> None:
    """Run a tiny deterministic processing loop for demonstration."""
    settings = Settings()
    epl = EventProcessingLayer(settings.event_schema_path)
    isi = InternalStateIntegrator()
    vel = ValueEvaluationLayer()
    sm = StateManager(settings.db_url)
    de = DecisionEngine()
    cci_metric = CCIMetric()

    events = [financial_event_example(), robot_event_example()]
    for index in range(iterations):
        raw = events[index % len(events)]
        event = epl.ingest(raw)
        state = sm.load_state()
        updated = isi.integrate(state, event)
        value_score = vel.evaluate_event(event)
        cci = cci_metric.compute(CCIInput(0.7, 0.75, 0.1, 0.6))
        plan = de.deliberate(updated, value_score, cci)
        sm.remember_event(event)
        sm.save_state(updated)
        print(f"[{index}] action={plan.action_type} cci={cci:.2f} value={value_score:.2f}")
        time.sleep(sleep_s)


if __name__ == "__main__":
    run_loop()
