"""Action Orchestrator implementation."""

from __future__ import annotations

from datetime import UTC, datetime

from pce.core.types import ActionPlan, ExecutionResult


class ActionOrchestrator:
    """Executes planned actions and emits traceable results."""

    def execute(self, plan: ActionPlan) -> ExecutionResult:
        """Perform deterministic execution for generic action plans."""
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
