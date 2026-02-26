"""Value Evaluation Layer implementation."""

from __future__ import annotations

from dataclasses import dataclass

from pce.core.types import PCEEvent


@dataclass(slots=True)
class StrategicValues:
    """Explicit values that constrain and prioritize decisions."""

    safety: float = 1.0
    efficiency: float = 0.8
    financial_responsibility: float = 0.9
    long_term_coherence: float = 1.0


class ValueEvaluationLayer:
    """Scores event/decision alignment to explicit strategic values."""

    def __init__(self, strategic_values: StrategicValues | None = None) -> None:
        self.values = strategic_values or StrategicValues()

    def evaluate_event(self, event: PCEEvent) -> float:
        """Compute value alignment score [0,1] from event tags and payload semantics."""
        tags = set(event.payload.get("tags", []))
        score = 0.0
        score += self.values.safety if "safe" in tags else self.values.safety * 0.4
        score += self.values.efficiency if "efficient" in tags else self.values.efficiency * 0.5
        score += (
            self.values.financial_responsibility
            if "budget-aware" in tags
            else self.values.financial_responsibility * 0.6
        )
        score += self.values.long_term_coherence if "strategic" in tags else 0.5
        return max(0.0, min(1.0, score / 4.0))
