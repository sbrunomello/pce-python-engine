"""Value model plugin for assistant domain events."""

from __future__ import annotations

from pce.core.plugins import ValueModelPlugin
from pce.core.types import PCEEvent


class AssistantValueModelPlugin(ValueModelPlugin):
    """Scores assistant events against tactical values."""

    name = "assistant.value_model"

    def match(self, event: PCEEvent, state: dict[str, object]) -> bool:
        _ = state
        return event.payload.get("domain") == "assistant"

    def evaluate(self, event: PCEEvent, state: dict[str, object]) -> float:
        components = self.components(event, state)
        value_score = (
            0.35 * components["safety"]
            + 0.20 * components["efficiency"]
            + 0.20 * components["long_term_coherence"]
            + 0.25 * components["helpfulness"]
        )
        return max(0.0, min(1.0, value_score))

    def components(self, event: PCEEvent, state: dict[str, object]) -> dict[str, float]:
        """Expose value components for explainability."""
        text = str(event.payload.get("text", ""))
        text_len = len(text)

        strategic_values_obj = state.get("strategic_values")
        strategic_values = (
            strategic_values_obj if isinstance(strategic_values_obj, dict) else {}
        )

        safety = 1.0
        if any(token in text.lower() for token in ("hack", "exploit", "malware")):
            safety = 0.2

        efficiency = 1.0 if text_len <= 600 else 0.7 if text_len <= 1400 else 0.4
        helpfulness = 0.8 if text_len >= 8 else 0.4
        coherence_hint = float(strategic_values.get("long_term_coherence", 0.8))
        long_term_coherence = max(0.0, min(1.0, coherence_hint))

        return {
            "safety": safety,
            "efficiency": efficiency,
            "long_term_coherence": long_term_coherence,
            "helpfulness": helpfulness,
        }
