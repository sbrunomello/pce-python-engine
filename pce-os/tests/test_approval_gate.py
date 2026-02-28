from pce.core.types import ActionPlan
from pce.sm.manager import StateManager
from pce_os.policy import ApprovalGate


def test_approval_gate_enqueue_and_approve_flow(tmp_path) -> None:
    db = tmp_path / "state.db"
    sm = StateManager(f"sqlite:///{db}")
    sm.save_state({"pce_os": {"robotics_twin": {"budget_remaining": 100.0}}})
    gate = ApprovalGate(sm)

    plan = ActionPlan(
        action_type="os.request_purchase_approval",
        rationale="need approval",
        priority=1,
        metadata={"projected_cost": 150.0, "risk_level": "HIGH"},
    )
    pending = gate.enqueue_pending_approval(
        "decision-1",
        plan,
        sm.load_state(),
        {"correlation_id": "c1"},
    )

    assert pending["approval_id"]
    assert len(gate.list_pending()) == 1

    approved_event = gate.approve(pending["approval_id"], "alice", "ok")
    assert approved_event["event_type"] == "purchase.approved"
    assert gate.list_pending() == []
