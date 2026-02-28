from pce_os.models import RobotProjectState
from pce_os.twin_store import RobotTwinStore


def test_apply_event_is_deterministic_for_same_sequence() -> None:
    seed = RobotProjectState(budget_total=1000, budget_remaining=1000)
    store_a = RobotTwinStore(seed)
    store_b = RobotTwinStore(seed)

    events = [
        (
            "part.candidate.added",
            {
                "component_id": "motor-1",
                "name": "BLDC Motor",
                "quantity": 2,
                "estimated_unit_cost": 120.0,
                "domain": "os.robotics",
                "tags": ["bom"],
            },
        ),
        (
            "purchase.completed",
            {
                "purchase_id": "po-1",
                "total_cost": 240.0,
                "domain": "os.robotics",
                "tags": ["purchase"],
            },
        ),
    ]

    for event_type, payload in events:
        state_a = store_a.apply_event(event_type, payload, {"at": "2026-01-01T00:00:00+00:00"})
        state_b = store_b.apply_event(event_type, payload, {"at": "2026-01-01T00:00:00+00:00"})

    assert state_a.model_dump(mode="json") == state_b.model_dump(mode="json")
    assert state_a.budget_remaining == 760.0
    assert state_a.cost_projection.projected_total_cost == 240.0
