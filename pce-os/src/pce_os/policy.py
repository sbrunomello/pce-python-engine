"""Approval and risk policy gates for PCE-OS."""

from __future__ import annotations

import logging
from copy import deepcopy
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pce.core.types import ActionPlan

_PENDING_APPROVALS_SLICE = "pending_approvals"
logger = logging.getLogger(__name__)


class ApprovalGate:
    """Approve-to-execute policy manager operating on state snapshots."""

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
        state: dict[str, object],
        metadata: dict[str, Any] | None = None,
    ) -> tuple[dict[str, Any], dict[str, object]]:
        """Return created pending record and updated state (without persistence)."""
        approvals = self._list_all_approvals(state)
        approval_id = str(uuid4())
        record: dict[str, Any] = {
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
        return record, self._write_approvals(state, approvals)

    def transition_approve(
        self,
        approval_id: str,
        actor: str,
        notes: str,
        state: dict[str, object],
    ) -> tuple[dict[str, Any], dict[str, object]]:
        """Approve one pending request and return updated state."""
        return self._transition(approval_id, actor, notes, approved=True, state=state)

    def transition_reject(
        self,
        approval_id: str,
        actor: str,
        reason: str,
        state: dict[str, object],
    ) -> tuple[dict[str, Any], dict[str, object]]:
        """Reject one pending request and return updated state."""
        return self._transition(approval_id, actor, reason, approved=False, state=state)

    def build_approval_event(
        self,
        record: dict[str, Any],
        actor: str,
        notes: str,
    ) -> dict[str, Any]:
        """Build the simulator event emitted when an approval is granted in v0."""
        approved_plan = record.get("plan")
        plan_metadata = approved_plan.get("metadata", {}) if isinstance(approved_plan, dict) else {}
        projected_cost = float(
            plan_metadata.get("projected_cost", record.get("projected_cost", 0.0))
        )
        purchase_id = str(
            plan_metadata.get("purchase_id")
            or record.get("metadata", {}).get("purchase_id")
            or f"purchase-{record.get('approval_id', 'unknown')}"
        )
        return {
            "event_type": "purchase.completed",
            "source": "os.control_plane",
            "payload": {
                "domain": "os.robotics",
                "tags": ["purchase", "completed"],
                "approval_id": record["approval_id"],
                "decision_id": record["decision_id"],
                "actor": actor,
                "notes": notes,
                "purchase_id": purchase_id,
                "total_cost": projected_cost,
                "approved_plan": approved_plan,
            },
        }

    def build_rejection_event(
        self,
        record: dict[str, Any],
        actor: str,
        reason: str,
    ) -> dict[str, Any]:
        """Build event emitted when an approval is rejected."""
        return {
            "event_type": "purchase.rejected",
            "source": "os.control_plane",
            "payload": {
                "domain": "os.robotics",
                "tags": ["approval", "purchase"],
                "approval_id": record["approval_id"],
                "decision_id": record["decision_id"],
                "actor": actor,
                "reason": reason,
            },
        }


    def get_approval(self, state: dict[str, object], approval_id: str) -> dict[str, Any]:
        """Return one approval record by id."""
        for item in self._list_all_approvals(state):
            if item.get("approval_id") == approval_id:
                return item
        raise ValueError(f"Approval '{approval_id}' not found")

    def list_pending(self, state: dict[str, object]) -> list[dict[str, Any]]:
        """List pending approvals from an in-memory state snapshot."""
        return [
            item
            for item in self._list_all_approvals(state)
            if isinstance(item, dict) and item.get("status") == "pending"
        ]

    def _transition(
        self,
        approval_id: str,
        actor: str,
        summary: str,
        approved: bool,
        state: dict[str, object],
    ) -> tuple[dict[str, Any], dict[str, object]]:
        approvals = self._list_all_approvals(state)

        for item in approvals:
            if isinstance(item, dict) and item.get("approval_id") == approval_id:
                item["status"] = "approved" if approved else "rejected"
                item["resolved_at"] = datetime.now(UTC).isoformat()
                item["actor"] = actor
                item["summary"] = summary
                next_state = self._write_approvals(state, approvals)
                logger.info(
                    "approval_resolved approval_id=%s decision_id=%s status=%s",
                    approval_id,
                    item.get("decision_id"),
                    item["status"],
                )
                return item, next_state
        raise ValueError(f"Approval '{approval_id}' not found")

    @staticmethod
    def _list_all_approvals(state: dict[str, object]) -> list[dict[str, Any]]:
        os_state = state.get("pce_os")
        if not isinstance(os_state, dict):
            return []
        pending = os_state.get(_PENDING_APPROVALS_SLICE)
        if not isinstance(pending, list):
            return []
        return [item for item in pending if isinstance(item, dict)]

    @staticmethod
    def _write_approvals(
        state: dict[str, object],
        approvals: list[dict[str, Any]],
    ) -> dict[str, object]:
        next_state = deepcopy(state)
        os_state = next_state.get("pce_os")
        if not isinstance(os_state, dict):
            os_state = {}
        os_state[_PENDING_APPROVALS_SLICE] = approvals
        next_state["pce_os"] = os_state
        return next_state

    @staticmethod
    def _read_twin(state: dict[str, object]) -> dict[str, Any]:
        os_state = state.get("pce_os")
        if not isinstance(os_state, dict):
            return {}
        twin = os_state.get("robotics_twin")
        if not isinstance(twin, dict):
            return {}
        return twin
