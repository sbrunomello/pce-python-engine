"""AO layer: deterministic mock execution and portfolio updates."""

from __future__ import annotations

from datetime import UTC, datetime

from trader_plugins.config import TraderConfig
from trader_plugins.events import EVENT_EXECUTION_FILLED, EVENT_EXECUTION_SKIPPED
from trader_plugins.types import FillResult, TradePlan


class MockBroker:
    """Deterministic broker simulator with fee, slippage and basic PnL accounting."""

    def __init__(self, config: TraderConfig) -> None:
        self._config = config

    def execute(self, plan: TradePlan, state: dict[str, object], mark_price: float) -> FillResult:
        portfolio = state["portfolio"] if isinstance(state.get("portfolio"), dict) else {}
        positions = portfolio.setdefault("positions", {})
        position = positions.setdefault(plan.symbol, {"qty": 0.0, "avg_price": 0.0})

        if plan.action in {"NO_TRADE", "HOLD"} or plan.qty <= 0:
            return FillResult(
                event_type=EVENT_EXECUTION_SKIPPED,
                source="trader/ao",
                payload={"decision_id": plan.decision_id, "reason": plan.reason, "symbol": plan.symbol},
            )

        fee_mult = self._config.fee_bps / 10_000.0
        slippage_mult = self._config.slippage_bps / 10_000.0

        if plan.action not in {"ENTER_LONG", "EXIT_LONG", "REDUCE", "EXIT"}:
            return FillResult(
                event_type=EVENT_EXECUTION_SKIPPED,
                source="trader/ao",
                payload={"decision_id": plan.decision_id, "reason": f"unsupported_action:{plan.action}", "symbol": plan.symbol},
            )

        side = "BUY" if plan.action == "ENTER_LONG" else "SELL"
        signed_slippage = slippage_mult if side == "BUY" else -slippage_mult
        exec_price = mark_price * (1.0 + signed_slippage)

        prev_qty = float(position.get("qty", 0.0))
        avg_price = float(position.get("avg_price", 0.0))
        requested_qty = float(plan.qty)

        if side == "SELL" and requested_qty > prev_qty:
            return FillResult(
                event_type=EVENT_EXECUTION_SKIPPED,
                source="trader/ao",
                payload={
                    "decision_id": plan.decision_id,
                    "reason": "sell_qty_exceeds_position",
                    "symbol": plan.symbol,
                    "requested_qty": requested_qty,
                    "position_qty": prev_qty,
                },
            )

        gross_notional = exec_price * requested_qty
        fee = gross_notional * fee_mult

        if side == "BUY":
            total_cost = gross_notional + fee
            portfolio["cash"] = float(portfolio.get("cash", 0.0)) - total_cost
            new_qty = prev_qty + requested_qty
            position["avg_price"] = 0.0 if new_qty == 0 else ((avg_price * prev_qty) + (exec_price * requested_qty)) / new_qty
            position["qty"] = new_qty
            realized_delta = 0.0
        else:
            proceeds = gross_notional - fee
            portfolio["cash"] = float(portfolio.get("cash", 0.0)) + proceeds
            new_qty = prev_qty - requested_qty
            position["qty"] = new_qty
            if new_qty == 0:
                position["avg_price"] = 0.0
            realized_delta = (exec_price - avg_price) * requested_qty - fee
            portfolio["realized_pnl"] = float(portfolio.get("realized_pnl", 0.0)) + realized_delta

        return FillResult(
            event_type=EVENT_EXECUTION_FILLED,
            source="trader/ao",
            payload={
                "decision_id": plan.decision_id,
                "symbol": plan.symbol,
                "side": side,
                "action": plan.action,
                "qty": requested_qty,
                "price": exec_price,
                "fee": fee,
                "realized_pnl_delta": realized_delta,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
