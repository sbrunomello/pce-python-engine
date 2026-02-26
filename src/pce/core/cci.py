"""Cognitive Coherence Index implementation."""

from __future__ import annotations

from dataclasses import dataclass
from statistics import pstdev
from typing import Any


@dataclass(slots=True)
class CCIInput:
    """CCI normalized inputs in [0, 1] range."""

    decision_consistency: float
    priority_stability: float
    contradiction_rate: float
    predictive_accuracy: float


@dataclass(slots=True)
class CCIMetric:
    """Weighted CCI metric normalized into [0, 1]."""

    weight_consistency: float = 0.35
    weight_stability: float = 0.25
    weight_non_contradiction: float = 0.25
    weight_predictive_accuracy: float = 0.15

    def compute(self, data: CCIInput) -> float:
        """Compute the real-time CCI from strategic coherence signals.

        Formula (normalized 0..1):
          CCI = wc * consistency + ws * stability +
                wn * (1 - contradiction_rate) + wp * predictive_accuracy
        """
        values = [
            data.decision_consistency,
            data.priority_stability,
            data.contradiction_rate,
            data.predictive_accuracy,
        ]
        if any(v < 0.0 or v > 1.0 for v in values):
            msg = "CCI input values must be normalized between 0 and 1"
            raise ValueError(msg)

        weighted = (
            self.weight_consistency * data.decision_consistency
            + self.weight_stability * data.priority_stability
            + self.weight_non_contradiction * (1 - data.contradiction_rate)
            + self.weight_predictive_accuracy * data.predictive_accuracy
        )
        return max(0.0, min(1.0, weighted))

    def from_state_manager(self, state_manager: Any) -> tuple[float, CCIInput]:
        """Derive all CCI components from real action traces in StateManager."""
        recent_actions = state_manager.get_recent_actions(20)
        if not recent_actions:
            baseline = CCIInput(0.5, 0.5, 0.0, 0.5)
            return self.compute(baseline), baseline

        respected_count = sum(1 for action in recent_actions if action["respected_values"])
        decision_consistency = respected_count / len(recent_actions)

        priorities = [int(action["priority"]) for action in recent_actions]
        if len(priorities) == 1:
            priority_stability = 1.0
        else:
            spread = min(1.0, pstdev(priorities) / 3.0)
            priority_stability = 1.0 - spread

        contradictions = state_manager.calculate_contradictions()
        contradiction_rate = float(contradictions["contradiction_rate"])

        accuracies: list[float] = []
        for action in recent_actions:
            expected = float(action["expected_impact"])
            observed = float(action["observed_impact"])
            error = abs(expected - observed)
            accuracies.append(max(0.0, 1.0 - error))
        predictive_accuracy = sum(accuracies) / len(accuracies)

        components = CCIInput(
            decision_consistency=decision_consistency,
            priority_stability=priority_stability,
            contradiction_rate=contradiction_rate,
            predictive_accuracy=predictive_accuracy,
        )
        return self.compute(components), components
