"""Value Evaluation Layer implementation."""

from __future__ import annotations

from collections.abc import Mapping
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

    def _resolve_values(self, override: Mapping[str, float] | None = None) -> StrategicValues:
        """Resolve currently active strategic values, allowing state-driven overrides."""
        if not override:
            return self.values
        return StrategicValues(
            safety=float(override.get("safety", self.values.safety)),
            efficiency=float(override.get("efficiency", self.values.efficiency)),
            financial_responsibility=float(
                override.get(
                    "financial_responsibility",
                    self.values.financial_responsibility,
                )
            ),
            long_term_coherence=float(
                override.get("long_term_coherence", self.values.long_term_coherence)
            ),
        )

    def evaluate_event(
        self,
        event: PCEEvent,
        strategic_values_override: Mapping[str, float] | None = None,
    ) -> float:
        """Compute value alignment score [0,1] from event tags and payload semantics."""
        if event.payload.get("domain") == "robotics":
            return self._evaluate_robotics(event)

        active_values = self._resolve_values(strategic_values_override)
        tags = set(event.payload.get("tags", []))
        score = 0.0
        score += active_values.safety if "safe" in tags else active_values.safety * 0.4
        score += (
            active_values.efficiency
            if "efficient" in tags
            else active_values.efficiency * 0.5
        )
        score += (
            active_values.financial_responsibility
            if "budget-aware" in tags
            else active_values.financial_responsibility * 0.6
        )
        score += active_values.long_term_coherence if "strategic" in tags else 0.5
        return max(0.0, min(1.0, score / 4.0))

    def _evaluate_robotics(self, event: PCEEvent) -> float:
        payload = event.payload
        sensors = payload.get("sensors", {}) if isinstance(payload.get("sensors"), dict) else {}

        front = int(sensors.get("front", 0))
        distance = float(payload.get("distance", payload.get("delta", {}).get("manhattan", 0)))
        step_reward = float(payload.get("reward", -0.01))

        safety = 0.0 if front == 0 else 1.0
        progress = max(0.0, min(1.0, 1.0 - (distance / 20.0)))
        efficiency = max(0.0, min(1.0, 1.0 + min(0.0, step_reward)))

        value_score = 0.5 * safety + 0.35 * progress + 0.15 * efficiency
        return max(0.0, min(1.0, value_score))
