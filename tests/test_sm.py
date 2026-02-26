from pathlib import Path

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
