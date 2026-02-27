"""Decision Engine implementation."""

from __future__ import annotations

from pce.core.types import ActionPlan


class DecisionEngine:
    """Derives action plans from state, value score, and coherence index."""

    def deliberate(self, state: dict[str, object], value_score: float, cci: float) -> ActionPlan:
        """Select an action using adaptive scoring without domain-specific branches."""
        model_obj = state.get("model")
        model = model_obj if isinstance(model_obj, dict) else {}
        coherence_bias = float(model.get("coherence_bias", 0.0))
        state_complexity = min(1.0, len(state.keys()) / 10.0)

        candidates = {
            "stabilize": 0.55 * (1.0 - cci) + 0.25 * (1.0 - value_score) + 0.20 * state_complexity,
            "execute_strategy": 0.60 * value_score + 0.35 * cci + 0.05 * (1.0 - state_complexity),
            "collect_more_data": 0.45 * (1.0 - value_score)
            + 0.35 * (1.0 - cci)
            + 0.20 * state_complexity,
        }
        candidates["execute_strategy"] += 0.05 * max(0.0, coherence_bias)
        candidates["stabilize"] += 0.05 * max(0.0, -coherence_bias)

        ranked = sorted(candidates.items(), key=lambda pair: pair[1], reverse=True)
        action_type, best_score = ranked[0]
        priority = max(1, min(5, round(5 - (cci + value_score) * 2)))

        rationale = (
            f"Ação selecionada por score composto={best_score:.3f}; "
            f"cci={cci:.3f}, value_score={value_score:.3f}, "
            f"state_complexity={state_complexity:.3f}, coherence_bias={coherence_bias:.3f}."
        )
        expected_impact = max(0.0, min(1.0, 0.55 * value_score + 0.45 * cci))

        return ActionPlan(
            action_type=action_type,
            rationale=rationale,
            priority=priority,
            metadata={
                "state_keys": list(state.keys()),
                "candidate_scores": candidates,
                "expected_impact": expected_impact,
            },
        )
