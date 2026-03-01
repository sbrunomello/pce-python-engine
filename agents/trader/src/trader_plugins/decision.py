"""DE layer: deterministic gate ordering and trade plan generation."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from trader_plugins.config import TraderConfig
from trader_plugins.types import TradePlan


class TraderDecisionEngine:
    """Applies macro/model/guardrail gates in fixed order."""

    def __init__(self, config: TraderConfig) -> None:
        self._config = config

    def deliberate(
        self,
        *,
        symbol: str,
        macro_regime: str,
        model_out: dict[str, float],
        state: dict[str, object],
        mode: str,
        lock_entries: bool,
    ) -> TradePlan:
        p_win = float(model_out.get("p_win", 0.5))
        uncertainty = float(model_out.get("uncertainty", 1.0))
        threshold = float(state.get("dynamic_threshold", self._config.p_win_threshold))
        gate_results: list[dict[str, object]] = []

        macro_pass = macro_regime != "bear" and macro_regime != "invalid"
        gate_results.append({"gate": "macro_4h", "passed": macro_pass, "value": macro_regime})

        model_pass = p_win >= threshold and uncertainty <= 0.45
        gate_results.append(
            {
                "gate": "model",
                "passed": model_pass,
                "value": {"p_win": p_win, "uncertainty": uncertainty, "threshold": threshold},
            }
        )

        now = datetime.now(UTC)
        limits = state.get("limits", {}) if isinstance(state.get("limits"), dict) else {}
        per_asset = limits.get("trades_by_asset_day", {}) if isinstance(limits.get("trades_by_asset_day"), dict) else {}
        guardrails_pass = (
            not lock_entries
            and int(limits.get("trades_total_day", 0)) < self._config.risk.max_trades_per_day
            and int(per_asset.get(symbol, 0)) < self._config.risk.max_trades_per_asset_day
            and float(state.get("dd_day", 0.0)) < self._config.risk.daily_drawdown_limit
            and float(state.get("dd_month", 0.0)) < self._config.risk.monthly_drawdown_limit
            and mode != "locked"
        )
        gate_results.append({"gate": "guardrails", "passed": guardrails_pass})

        allow_trade = macro_pass and model_pass and guardrails_pass
        qty = float(state.get("suggested_qty", 0.0)) if allow_trade else 0.0
        action = "BUY" if allow_trade else "NO_TRADE"

        return TradePlan(
            decision_id=f"dec-{now.strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}",
            symbol=symbol,
            action=action,
            qty=qty,
            reason="; ".join([f"{row['gate']}={'PASS' if row['passed'] else 'FAIL'}" for row in gate_results]),
            p_win=p_win,
            uncertainty=uncertainty,
            threshold=threshold,
            mode=mode,
            gate_results=gate_results,
            metadata={"ts": now.isoformat()},
        )
