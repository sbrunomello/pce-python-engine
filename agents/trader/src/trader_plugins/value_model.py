"""VEL layer: opportunity/risk/quality scoring."""

from __future__ import annotations


class TraderValueModel:
    """Computes score tuple and policy flags from integrated state."""

    def evaluate(self, state: dict[str, object], p_win: float) -> dict[str, object]:
        features = state["features"] if isinstance(state.get("features"), dict) else {}
        atr = float(features.get("atr", 0.0))
        bb_width = float(features.get("bb_width", 0.0))
        data_ok = bool(features.get("integrity_ok", True))

        opportunity = max(0.0, min(1.0, 0.7 * p_win + 0.3 * max(0.0, float(features.get("ret_6", 0.0)) + 0.5)))
        volatility_penalty = min(1.0, atr / max(1.0, float(features.get("last_close", 1.0))))
        risk = max(0.0, min(1.0, 0.7 * volatility_penalty + 0.3 * min(1.0, bb_width)))
        quality = 1.0
        flags: list[str] = []
        if not data_ok:
            quality -= 0.7
            flags.append("integrity_bad")
        if volatility_penalty > 0.04:
            quality -= 0.2
            flags.append("high_volatility")
        quality = max(0.0, min(1.0, quality))

        return {
            "opportunity": opportunity,
            "risk": risk,
            "quality": quality,
            "policy_flags": flags,
        }
