"""AO layer: deterministic mock execution and portfolio updates."""

from __future__ import annotations

from datetime import UTC, datetime

from trader_plugins.config import TraderConfig
from trader_plugins.types import InternalEvent, TradePlan


class MockBroker:
    """Deterministic broker simulator with fee and slippage."""

    def __init__(self, config: TraderConfig) -> None:
        self._config = config

    def execute(self, plan: TradePlan, state: dict[str, object], mark_price: float) -> InternalEvent:
        if plan.action == "NO_TRADE" or plan.qty <= 0:
            return InternalEvent(
                event_type="execution.skipped",
                source="trader/ao",
                payload={"decision_id": plan.decision_id, "reason": plan.reason, "symbol": plan.symbol},
            )

        portfolio = state["portfolio"] if isinstance(state.get("portfolio"), dict) else {}
        positions = portfolio.setdefault("positions", {})
        position = positions.setdefault(plan.symbol, {"qty": 0.0, "avg_price": 0.0})

        fee_mult = self._config.fee_bps / 10_000.0
        slippage_mult = self._config.slippage_bps / 10_000.0
        exec_price = mark_price * (1.0 + slippage_mult)
        gross_cost = exec_price * plan.qty
        fee = gross_cost * fee_mult
        total_cost = gross_cost + fee

        portfolio["cash"] = float(portfolio.get("cash", 0.0)) - total_cost
        prev_qty = float(position["qty"])
        new_qty = prev_qty + plan.qty
        position["avg_price"] = (
            0.0
            if new_qty == 0
            else ((float(position["avg_price"]) * prev_qty) + (exec_price * plan.qty)) / new_qty
        )
        position["qty"] = new_qty

        return InternalEvent(
            event_type="execution.fill",
            source="trader/ao",
            payload={
                "decision_id": plan.decision_id,
                "symbol": plan.symbol,
                "side": plan.action,
                "qty": plan.qty,
                "price": exec_price,
                "fee": fee,
                "timestamp": datetime.now(UTC).isoformat(),
            },
        )
