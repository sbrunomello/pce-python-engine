"""Cognitive Coherence Index implementation."""

from __future__ import annotations

from dataclasses import dataclass


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
