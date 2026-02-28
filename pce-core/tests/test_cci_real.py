from pathlib import Path
from uuid import uuid4

from pce.core.cci import CCIMetric
from pce.sm.manager import StateManager


def test_cci_from_state_manager_uses_real_action_history(tmp_path: Path) -> None:
    db = tmp_path / "real-cci.db"
    sm = StateManager(f"sqlite:///{db}")

    for index in range(4):
        sm.remember_action(
            action_id=str(uuid4()),
            event_id=f"e-{index}",
            action_type="execute_strategy",
            priority=2 + (index % 2),
            value_score=0.8,
            expected_impact=0.8,
            observed_impact=0.7,
            respected_values=index != 3,
            violated_values=[] if index != 3 else ["safety"],
            metadata={"index": index},
        )

    cci, components = CCIMetric().from_state_manager(sm)

    assert 0.0 <= cci <= 1.0
    assert components.decision_consistency == 0.75
    assert components.contradiction_rate == 0.25
    assert round(components.predictive_accuracy, 4) == 0.9


def test_state_manager_cci_history_roundtrip(tmp_path: Path) -> None:
    db = tmp_path / "history.db"
    sm = StateManager(f"sqlite:///{db}")

    sm.save_cci_snapshot(
        cci_id="c1",
        cci=0.77,
        metrics={
            "decision_consistency": 0.8,
            "priority_stability": 0.9,
            "contradiction_rate": 0.1,
            "predictive_accuracy": 0.7,
        },
    )

    history = sm.get_cci_history()
    assert len(history) == 1
    assert history[0]["cci"] == 0.77
    assert history[0]["metrics"]["decision_consistency"] == 0.8
