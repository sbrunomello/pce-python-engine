from pce.afs.feedback import AdaptiveFeedbackSystem
from pce.ao.orchestrator import ActionOrchestrator
from pce.core.cci import CCIInput, CCIMetric
from pce.core.types import PCEEvent
from pce.de.engine import DecisionEngine
from pce.isi.integrator import InternalStateIntegrator
from pce.vel.evaluator import ValueEvaluationLayer


def test_pipeline_layers_interaction() -> None:
    isi = InternalStateIntegrator()
    vel = ValueEvaluationLayer()
    de = DecisionEngine()
    ao = ActionOrchestrator()
    afs = AdaptiveFeedbackSystem()
    cci = CCIMetric()

    event = PCEEvent(
        event_type="robot.sensor",
        source="robot-core",
        payload={"domain": "robotics", "tags": ["safe", "strategic"]},
    )
    state = isi.integrate({}, event)
    value = vel.evaluate_event(event)
    coherence = cci.compute(CCIInput(0.8, 0.7, 0.1, 0.6))
    plan = de.deliberate(state, value, coherence)
    result = ao.execute(plan)
    adapted = afs.adapt(state, result)

    assert plan.action_type in {"execute_strategy", "collect_more_data", "stabilize"}
    assert "model" in adapted
