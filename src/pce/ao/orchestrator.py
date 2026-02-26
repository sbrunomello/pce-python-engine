"""Action Orchestrator implementation."""

from __future__ import annotations

from datetime import UTC, datetime

from pce.core.types import ActionPlan, ExecutionResult


class ActionOrchestrator:
    """Executes planned actions and emits traceable results."""

    def execute(self, plan: ActionPlan) -> ExecutionResult:
        """Perform deterministic execution and keep robotics impact feedback-driven."""
        if plan.action_type == "robotics.action":
            return ExecutionResult(
                action_type=plan.action_type,
                success=True,
                observed_impact=0.0,
                notes=plan.rationale,
                metadata={
                    "executed_at": datetime.now(UTC).isoformat(),
                    "priority": plan.priority,
                    "robot_action": plan.metadata.get("robot_action", {}),
                    "execution_mode": "emitted",
                },
            )

        success = plan.action_type != "collect_more_data"
        impact = 0.8 if success else 0.3
        return ExecutionResult(
            action_type=plan.action_type,
            success=success,
            observed_impact=impact,
            notes=plan.rationale,
            metadata={
                "executed_at": datetime.now(UTC).isoformat(),
                "priority": plan.priority,
            },
        )
