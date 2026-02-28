"""Approval and risk policy gates for PCE-OS."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pce.core.types import ActionPlan
from pce.sm.manager import StateManager

_PENDING_APPROVALS_SLICE = "pending_approvals"


class ApprovalGate:
    """Approve-to-execute policy manager using state slice persistence."""

    def __init__(self, state_manager: StateManager) -> None:
        self._sm = state_manager

    def decide_if_requires_approval(
        self,
        plan: ActionPlan,
        state: dict[str, object],
    ) -> tuple[bool, str]:
        """Decide whether a plan must enter pending approvals."""
        action_type = plan.action_type
        if action_type.startswith("purchase.") or action_type == "os.request_purchase_approval":
            return True, "purchase_flow_mandatory_gate"

        metadata = plan.metadata
        projected_cost = float(metadata.get("projected_cost", 0.0))
        risk_level = str(metadata.get("risk_level", "LOW"))
        twin = self._read_twin(state)
        budget_remaining = float(twin.get("budget_remaining", 0.0))

        if budget_remaining < projected_cost:
            return True, "budget_remaining_below_projection"
        if risk_level == "HIGH":
            return True, "risk_level_high"

        return False, "none"

    def enqueue_pending_approval(
        self,
        decision_id: str,
        plan: ActionPlan,
        snapshot_state: dict[str, object],
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Store pending approval request and return created record."""
        approvals = self.list_pending()
        approval_id = str(uuid4())
        record = {
            "approval_id": approval_id,
            "decision_id": decision_id,
            "created_at": datetime.now(UTC).isoformat(),
            "status": "pending",
            "action_type": plan.action_type,
            "priority": plan.priority,
            "rationale": plan.rationale,
            "projected_cost": float(plan.metadata.get("projected_cost", 0.0)),
            "risk": str(plan.metadata.get("risk_level", "LOW")),
            "metadata": metadata or {},
            "snapshot_state": snapshot_state,
            "plan": {
                "action_type": plan.action_type,
                "rationale": plan.rationale,
                "priority": plan.priority,
                "metadata": plan.metadata,
            },
        }
        approvals.append(record)
        self._save_pending(approvals)
        return record

    def approve(self, approval_id: str, actor: str, notes: str) -> dict[str, Any]:
        """Mark approval approved and return event payload for pipeline ingestion."""
        record = self._transition(approval_id, actor, notes, approved=True)
        return {
            "event_type": "purchase.approved",
            "source": "os.control_plane",
            "payload": {
                "domain": "os.robotics",
                "tags": ["approval", "purchase"],
                "approval_id": approval_id,
                "decision_id": record["decision_id"],
                "actor": actor,
                "notes": notes,
                "approved_plan": record["plan"],
            },
        }

    def reject(self, approval_id: str, actor: str, reason: str) -> dict[str, Any]:
        """Mark approval rejected and return event payload for pipeline ingestion."""
        record = self._transition(approval_id, actor, reason, approved=False)
        return {
            "event_type": "purchase.rejected",
            "source": "os.control_plane",
            "payload": {
                "domain": "os.robotics",
                "tags": ["approval", "purchase"],
                "approval_id": approval_id,
                "decision_id": record["decision_id"],
                "actor": actor,
                "reason": reason,
            },
        }

    def list_pending(self) -> list[dict[str, Any]]:
        state = self._sm.load_state()
        os_state = state.get("pce_os")
        if not isinstance(os_state, dict):
            return []
        pending = os_state.get(_PENDING_APPROVALS_SLICE)
        if not isinstance(pending, list):
            return []
        return [
            item
            for item in pending
            if isinstance(item, dict) and item.get("status") == "pending"
        ]

    def _transition(
        self,
        approval_id: str,
        actor: str,
        summary: str,
        approved: bool,
    ) -> dict[str, Any]:
        state = self._sm.load_state()
        os_state = state.get("pce_os")
        if not isinstance(os_state, dict):
            raise ValueError("No pending approvals found")
        approvals = os_state.get(_PENDING_APPROVALS_SLICE)
        if not isinstance(approvals, list):
            raise ValueError("No pending approvals found")

        for item in approvals:
            if isinstance(item, dict) and item.get("approval_id") == approval_id:
                item["status"] = "approved" if approved else "rejected"
                item["resolved_at"] = datetime.now(UTC).isoformat()
                item["actor"] = actor
                item["summary"] = summary
                self._save_all(approvals)
                return item
        raise ValueError(f"Approval '{approval_id}' not found")

    def _save_pending(self, pending: list[dict[str, Any]]) -> None:
        self._save_all(pending)

    def _save_all(self, approvals: list[dict[str, Any]]) -> None:
        state = self._sm.load_state()
        os_state = state.get("pce_os")
        if not isinstance(os_state, dict):
            os_state = {}
        os_state[_PENDING_APPROVALS_SLICE] = approvals
        state["pce_os"] = os_state
        self._sm.save_state(state)

    @staticmethod
    def _read_twin(state: dict[str, object]) -> dict[str, Any]:
        os_state = state.get("pce_os")
        if not isinstance(os_state, dict):
            return {}
        twin = os_state.get("robotics_twin")
        if not isinstance(twin, dict):
            return {}
        return twin
