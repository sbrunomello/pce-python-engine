"""Decision Engine implementation."""

from __future__ import annotations

from pce.core.types import ActionPlan


class DecisionEngine:
    """Derives action plans from state, value score, and coherence index."""

    def deliberate(self, state: dict[str, object], value_score: float, cci: float) -> ActionPlan:
        """Select an action using explicit thresholds and transparent rationale."""
        if cci < 0.4:
            return ActionPlan(
                action_type="stabilize",
                rationale="CCI baixo: priorizar estabilização cognitiva",
                priority=1,
                metadata={"cci": cci, "value_score": value_score},
            )

        if value_score >= 0.75:
            return ActionPlan(
                action_type="execute_strategy",
                rationale="Alto alinhamento estratégico e coerência satisfatória",
                priority=2,
                metadata={"state_keys": list(state.keys())},
            )

        return ActionPlan(
            action_type="collect_more_data",
            rationale="Alinhamento insuficiente: coletar eventos adicionais",
            priority=3,
            metadata={"cci": cci, "value_score": value_score},
        )
