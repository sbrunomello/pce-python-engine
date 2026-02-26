from pathlib import Path
from uuid import uuid4

from pce.core.types import PCEEvent
from pce.sm.manager import StateManager


def test_state_manager_persists_state(tmp_path: Path) -> None:
    db = tmp_path / "state.db"
    sm = StateManager(f"sqlite:///{db}")

    sm.save_state({"finance": {"budget": 10}})
    loaded = sm.load_state()
    assert loaded["finance"]["budget"] == 10

    sm.remember_event(
        PCEEvent(
            event_type="x",
            source="test",
            payload={"domain": "general", "tags": ["safe"]},
        )
    )
    assert sm.recent_event_count() == 1


def test_state_manager_action_methods(tmp_path: Path) -> None:
    db = tmp_path / "actions.db"
    sm = StateManager(f"sqlite:///{db}")

    sm.remember_action(
        action_id=str(uuid4()),
        event_id="event-1",
        action_type="stabilize",
        priority=3,
        value_score=0.5,
        expected_impact=0.6,
        observed_impact=0.4,
        respected_values=False,
        violated_values=["safety"],
        metadata={"m": 1},
    )

    recent = sm.get_recent_actions(20)
    assert len(recent) == 1
    assert recent[0]["action_type"] == "stabilize"

    contradictions = sm.calculate_contradictions()
    assert contradictions["total_actions"] == 1
    assert contradictions["contradiction_rate"] == 1.0
