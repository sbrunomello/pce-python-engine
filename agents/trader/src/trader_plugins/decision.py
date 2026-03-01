"""DE layer: deterministic multi-option deliberation with value-governed scoring."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from trader_plugins.config import TraderConfig
from trader_plugins.types import TradeOption, TradePlan
from trader_plugins.value_policy import ValuePolicy


class TraderDecisionEngine:
    """Applies macro/model/guardrail gates and ranks explicit alternatives."""

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
        value_policy: ValuePolicy,
    ) -> TradePlan:
        p_win = float(model_out.get("p_win", 0.5))
        uncertainty = float(model_out.get("uncertainty", 1.0))
        threshold = float(state.get("dynamic_threshold", self._config.p_win_threshold))
        portfolio = state.get("portfolio", {}) if isinstance(state.get("portfolio"), dict) else {}
        positions = portfolio.get("positions", {}) if isinstance(portfolio.get("positions"), dict) else {}
        symbol_pos = positions.get(symbol, {}) if isinstance(positions.get(symbol), dict) else {}
        current_qty = float(symbol_pos.get("qty", 0.0))

        gate_results = self._build_gate_results(
            symbol=symbol,
            macro_regime=macro_regime,
            p_win=p_win,
            uncertainty=uncertainty,
            threshold=threshold,
            model_out=model_out,
            state=state,
            mode=mode,
            lock_entries=lock_entries,
        )

        options = self._evaluate_options(
            symbol=symbol,
            p_win=p_win,
            uncertainty=uncertainty,
            mode=mode,
            state=state,
            current_qty=current_qty,
            macro_regime=macro_regime,
            gates=gate_results,
            value_policy=value_policy,
        )
        options_sorted = sorted(options, key=lambda item: item.final_score, reverse=True)
        selected = self._select_best_valid_option(options_sorted, current_qty=current_qty, mode=mode)

        now = datetime.now(UTC)
        mark_price = float((state.get("prices", {}) if isinstance(state.get("prices"), dict) else {}).get(symbol, 0.0))
        atr = float(((state.get("market", {}) if isinstance(state.get("market"), dict) else {}).get(symbol, {}) or {}).get("1h", {}).get("features", {}).get("atr", 0.0))
        if atr <= 0:
            atr = max(mark_price * 0.005, 1e-9)
        entry_price = mark_price
        stop_distance = max(atr, entry_price * 0.005) if entry_price > 0 else atr

        action = selected.option_type
        qty = 0.0
        if action == "ENTER_LONG":
            qty = float(state.get("suggested_qty", 0.0))
        elif action in {"EXIT_LONG", "REDUCE"}:
            qty = current_qty if action == "EXIT_LONG" else round(current_qty * 0.5, 6)
        elif action in {"HOLD", "NO_TRADE"}:
            qty = 0.0

        if mode == "locked" and action == "ENTER_LONG":
            action = "NO_TRADE"
            qty = 0.0

        risk_r = stop_distance if action == "ENTER_LONG" and entry_price > 0 else 0.0
        expected_r = max(0.0, (p_win * 2.0) - 1.0)
        stop_price = max(0.0, entry_price - stop_distance) if action == "ENTER_LONG" else 0.0
        take_price = entry_price + (2.0 * stop_distance) if action == "ENTER_LONG" else 0.0

        invalidation_reason = ""
        if action == "NO_TRADE":
            invalidation_reason = "best_option_invalid_or_threshold_blocked"
        elif action == "HOLD":
            invalidation_reason = "position_maintained_pending_new_signal"

        value_breakdown = {
            "selected_option": action,
            "selected_final_score": selected.final_score,
            "expected_value_score": selected.expected_value,
            "risk_score": selected.risk,
            "cost_score": selected.cost,
            "consistency_score": selected.consistency,
            "quality_score": selected.quality,
            "weights": value_policy.to_dict().get("weights", {}),
            "mode": mode,
        }

        return TradePlan(
            decision_id=f"dec-{now.strftime('%Y%m%d%H%M%S')}-{uuid4().hex[:8]}",
            symbol=symbol,
            action=action,
            qty=round(max(0.0, qty), 6),
            reason="; ".join([f"{row['gate']}={'PASS' if row['passed'] else 'FAIL'}" for row in gate_results]) + f"; selected={action}",
            p_win=p_win,
            uncertainty=uncertainty,
            threshold=threshold,
            mode=mode,
            value_policy_version=value_policy.value_policy_version,
            gate_results=gate_results,
            entry_price=entry_price,
            stop_price=stop_price,
            take_price=take_price,
            risk_R=risk_r,
            expected_R=expected_r,
            invalidation_reason=invalidation_reason,
            time_horizon=f"{self._config.prediction_horizon_hours}h",
            value_breakdown=value_breakdown,
            alternatives=options_sorted,
            metadata={"ts": now.isoformat()},
        )

    def _build_gate_results(self, *, symbol: str, macro_regime: str, p_win: float, uncertainty: float, threshold: float, model_out: dict[str, float], state: dict[str, object], mode: str, lock_entries: bool) -> list[dict[str, object]]:
        gate_results: list[dict[str, object]] = []
        macro_pass = macro_regime not in {"bear", "invalid"}
        gate_results.append({"gate": "macro_4h", "passed": macro_pass, "value": macro_regime})

        uncertainty_limit = self._uncertainty_limit(mode)
        model_missing = bool(model_out.get("model_missing", 0.0))
        model_pass = (not model_missing) and p_win >= threshold and uncertainty <= uncertainty_limit
        gate_results.append({"gate": "model", "passed": model_pass, "value": {"p_win": p_win, "uncertainty": uncertainty, "threshold": threshold, "uncertainty_limit": uncertainty_limit, "model_missing": model_missing}})

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
        return gate_results

    def _evaluate_options(self, *, symbol: str, p_win: float, uncertainty: float, mode: str, state: dict[str, object], current_qty: float, macro_regime: str, gates: list[dict[str, object]], value_policy: ValuePolicy) -> list[TradeOption]:
        del symbol
        base_quality = 1.0 - min(1.0, uncertainty)
        if macro_regime in {"invalid"}:
            base_quality *= 0.5
        consistency = 1.0 if macro_regime in {"bull", "sideways"} else 0.4
        cost_base = (self._config.fee_bps + self._config.slippage_bps) / 100.0

        options = ["ENTER_LONG", "EXIT_LONG", "HOLD", "REDUCE", "NO_TRADE"]
        out: list[TradeOption] = []
        gate_ok = all(bool(row.get("passed")) for row in gates)
        mode_mod = value_policy.mode_modifiers.get(mode, value_policy.mode_modifiers["restricted"])

        for opt in options:
            expected = p_win if opt == "ENTER_LONG" else (1.0 - p_win if opt in {"EXIT_LONG", "REDUCE"} else 0.5)
            risk = min(1.0, uncertainty + (0.25 if opt == "ENTER_LONG" else 0.10 if opt == "HOLD" else 0.05))
            cost = min(1.0, cost_base * (1.0 if opt in {"ENTER_LONG", "EXIT_LONG", "REDUCE"} else 0.2))
            quality = max(0.0, min(1.0, base_quality - (0.15 if opt == "ENTER_LONG" and not gate_ok else 0.0)))
            option_consistency = consistency if opt in {"ENTER_LONG", "HOLD"} else 1.0 - (consistency * 0.4)

            final = (
                value_policy.weights.opportunity_weight * expected * mode_mod.opportunity_multiplier
                - value_policy.weights.risk_weight * risk * mode_mod.risk_multiplier
                + value_policy.weights.quality_weight * quality * mode_mod.quality_multiplier
                + value_policy.weights.consistency_weight * option_consistency * mode_mod.consistency_multiplier
                - value_policy.weights.cost_weight * cost * mode_mod.cost_multiplier
            )

            if opt == "ENTER_LONG" and current_qty > 0:
                final -= 0.15
            if opt in {"EXIT_LONG", "REDUCE"} and current_qty <= 0:
                final -= 1.0
            if opt == "HOLD" and current_qty <= 0:
                final -= 0.3
            if opt == "NO_TRADE":
                final += 0.02
            if mode == "locked" and opt == "ENTER_LONG":
                final -= 2.0

            out.append(
                TradeOption(
                    option_type=opt,
                    expected_value=round(expected, 6),
                    risk=round(risk, 6),
                    cost=round(cost, 6),
                    quality=round(quality, 6),
                    consistency=round(option_consistency, 6),
                    final_score=round(final, 6),
                    rationale=f"opt={opt};gate_ok={gate_ok};mode={mode}",
                )
            )
        return out

    def _select_best_valid_option(self, options: list[TradeOption], *, current_qty: float, mode: str) -> TradeOption:
        for opt in options:
            if mode == "locked" and opt.option_type == "ENTER_LONG":
                continue
            if opt.option_type in {"EXIT_LONG", "REDUCE", "HOLD"} and current_qty <= 0:
                continue
            return opt
        return TradeOption("NO_TRADE", 0.0, 1.0, 0.0, 0.0, 0.0, -1.0, "fallback")

    def _uncertainty_limit(self, mode: str) -> float:
        if mode == "normal":
            return self._config.uncertainty_gate_normal
        if mode == "cautious":
            return self._config.uncertainty_gate_cautious
        if mode == "restricted":
            return self._config.uncertainty_gate_restricted
        return 0.0
