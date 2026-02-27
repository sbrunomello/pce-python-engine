"""Adaptive Feedback System implementation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pce.core.types import ExecutionResult


class AdaptiveFeedbackSystem:
    """Updates internal model slices based on execution outcomes."""

    def adapt(self, state: Mapping[str, Any], result: ExecutionResult) -> dict[str, Any]:
        """Apply adaptive update to model and strategic value weights."""
        next_state = dict(state)
        model = dict(next_state.get("model", {}))
        learning_rate = float(model.get("learning_rate", 0.1))

        outcome = result.observed_impact if result.success else -result.observed_impact
        delta = learning_rate * outcome
        model["coherence_bias"] = float(model.get("coherence_bias", 0.0)) + delta
        model["last_action"] = result.action_type

        strategic_values = dict(
            next_state.get(
                "strategic_values",
                {
                    "safety": 1.0,
                    "efficiency": 0.8,
                    "financial_responsibility": 0.9,
                    "long_term_coherence": 1.0,
                },
            )
        )
        violated_values = list(result.metadata.get("violated_values", []))
        contradiction_penalty = 0.05 if violated_values else 0.0
        feedback_boost = 0.03 * max(-1.0, min(1.0, outcome))

        for key, current in strategic_values.items():
            weight = float(current)
            if key in violated_values:
                weight += contradiction_penalty
            else:
                weight += feedback_boost
            strategic_values[key] = max(0.2, min(1.5, weight))

        next_state["model"] = model
        next_state["strategic_values"] = strategic_values
        return next_state
