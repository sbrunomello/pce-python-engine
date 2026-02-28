from pce.core.types import ActionPlan
from pce_os.policy import ApprovalGate


def test_approval_gate_enqueue_and_approve_flow() -> None:
    gate = ApprovalGate()
    state: dict[str, object] = {"pce_os": {"robotics_twin": {"budget_remaining": 100.0}}}

    plan = ActionPlan(
        action_type="os.request_purchase_approval",
        rationale="need approval",
        priority=1,
        metadata={"projected_cost": 150.0, "risk_level": "HIGH", "purchase_id": "po-1"},
    )
    pending, with_pending = gate.enqueue_pending_approval(
        "decision-1",
        plan,
        state,
        state,
        {"correlation_id": "c1"},
    )

    assert pending["approval_id"]
    assert len(gate.list_pending(with_pending)) == 1

    record, approved_state = gate.transition_approve(
        pending["approval_id"],
        "alice",
        "ok",
        with_pending,
    )
    approved_event = gate.build_approval_event(record, "alice", "ok")

    assert approved_event["event_type"] == "purchase.completed"
    assert approved_event["payload"]["purchase_id"] == "po-1"
    assert gate.list_pending(approved_state) == []
