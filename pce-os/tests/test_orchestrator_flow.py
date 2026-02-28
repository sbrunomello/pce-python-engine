from pce.core.types import PCEEvent
from pce_os.plugins import AgentOrchestrator


def test_orchestrator_purchase_completed_schedules_test() -> None:
    orchestrator = AgentOrchestrator()
    event = PCEEvent(
        event_type="purchase.completed",
        source="test",
        payload={"domain": "os.robotics", "purchase_id": "po-123"},
    )

    result = orchestrator.deliberate(
        event,
        twin_snapshot={"budget_remaining": 50.0},
        correlation_id="corr-2",
        decision_id="dec-2",
    )
    action_types = [action["action_type"] for action in result["actions"]]

    assert "os.schedule_test" in action_types
