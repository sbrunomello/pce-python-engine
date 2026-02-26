"""Adaptive Feedback System implementation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pce.core.types import ExecutionResult


class AdaptiveFeedbackSystem:
    """Updates internal model slices based on execution outcomes."""

    def adapt(self, state: Mapping[str, Any], result: ExecutionResult) -> dict[str, Any]:
        """Apply lightweight adaptive update without introducing heavy ML dependencies."""
        next_state = dict(state)
        model = dict(next_state.get("model", {}))
        learning_rate = float(model.get("learning_rate", 0.1))

        # Reward successful trajectories, penalize weak outcomes.
        outcome = result.observed_impact if result.success else -result.observed_impact
        delta = learning_rate * outcome
        model["coherence_bias"] = float(model.get("coherence_bias", 0.0)) + delta
        model["last_action"] = result.action_type

        next_state["model"] = model
        return next_state
