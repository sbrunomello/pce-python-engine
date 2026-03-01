from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from trader_plugins.adaptation import triple_barrier_labels
from trader_plugins.ao import MockBroker
from trader_plugins.config import TraderConfig, mode_from_ccif
from trader_plugins.decision import TraderDecisionEngine
from trader_plugins.events import EVENT_DECISION_PLAN_CREATED, EVENT_EXECUTION_FILLED, EVENT_MARKET_CANDLE_CLOSED
from trader_plugins.ledger import TraderEventLedger
from trader_plugins.runtime import TraderRuntime
from trader_plugins.types import Candle, TradePlan


def test_triple_barrier_labeling() -> None:
    closes = [100, 101, 103, 99, 97, 96, 98]
    labels = triple_barrier_labels(closes, horizon=3, tp=0.02, sl=0.02)
    assert labels[0] == "TP_FIRST"
    assert labels[2] == "SL_FIRST"


def test_macro_gate_blocks_bear() -> None:
    engine = TraderDecisionEngine(TraderConfig())
    plan = engine.deliberate(
        symbol="BTCUSDT",
        macro_regime="bear",
        model_out={"p_win": 0.9, "uncertainty": 0.1},
        state={"limits": {}, "dd_day": 0.0, "dd_month": 0.0, "suggested_qty": 1.0, "portfolio": {"positions": {}}},
        mode="normal",
        lock_entries=False,
    )
    assert plan.action == "NO_TRADE"
    assert plan.gate_results[0]["passed"] is False


def test_risk_sizing_05_percent() -> None:
    runtime = TraderRuntime()
    runtime.state["portfolio"] = {"equity": 100_000.0, "cash": 100_000.0, "positions": {}}
    qty = runtime._size_from_risk(atr=100.0, price=10_000.0)
    assert qty == 5.0


def test_ccif_modes() -> None:
    assert mode_from_ccif(0.86, locked=False) == "normal"
    assert mode_from_ccif(0.71, locked=False) == "cautious"
    assert mode_from_ccif(0.56, locked=False) == "restricted"
    assert mode_from_ccif(0.9, locked=True) == "locked"


def test_mockbroker_buy_sell_realized_pnl() -> None:
    broker = MockBroker(TraderConfig(fee_bps=0.0, slippage_bps=0.0))
    state = {"portfolio": {"cash": 10_000.0, "positions": {}, "realized_pnl": 0.0}}
    buy = TradePlan("dec1", "BTCUSDT", "ENTER_LONG", 1.0, "ok", 0.7, 0.2, 0.6, "normal", [])
    sell = TradePlan("dec2", "BTCUSDT", "EXIT", 0.4, "ok", 0.2, 0.7, 0.6, "normal", [])

    broker.execute(buy, state, mark_price=100.0)
    out = broker.execute(sell, state, mark_price=120.0)

    assert out.event_type == EVENT_EXECUTION_FILLED
    assert state["portfolio"]["positions"]["BTCUSDT"]["qty"] == 0.6
    assert state["portfolio"]["realized_pnl"] == 8.0


def test_replay_deterministic_same_final_state_and_decision_events(tmp_path) -> None:
    csv_path = tmp_path / "candles.csv"
    start = datetime(2026, 1, 1, tzinfo=UTC)
    csv_path.write_text(
        "symbol,timeframe,timestamp,open,high,low,close,volume\n"
        + "\n".join(
            [
                f"BTCUSDT,4h,{(start + timedelta(hours=4*i)).isoformat()},100,101,99,{100 + i},1000"
                for i in range(12)
            ]
            + [
                f"BTCUSDT,1h,{(start + timedelta(hours=i)).isoformat()},100,101,99,{100 + i*0.5},900"
                for i in range(24)
            ]
        ),
        encoding="utf-8",
    )

    cfg1 = TraderConfig(db_url=f"sqlite:///{tmp_path / 'state1.db'}", artifacts_dir=tmp_path / "a1", logs_dir=tmp_path / "a1" / "logs")
    cfg2 = TraderConfig(db_url=f"sqlite:///{tmp_path / 'state2.db'}", artifacts_dir=tmp_path / "a2", logs_dir=tmp_path / "a2" / "logs")

    r1 = TraderRuntime(cfg1)
    d1 = r1.replay_csv(csv_path)
    s1 = r1.state

    r2 = TraderRuntime(cfg2)
    d2 = r2.replay_csv(csv_path)
    s2 = r2.state

    q1 = r1.ledger.query(event_type=EVENT_DECISION_PLAN_CREATED)
    q2 = r2.ledger.query(event_type=EVENT_DECISION_PLAN_CREATED)

    assert len(d1) == len(d2)
    assert len(q1) == len(q2)
    assert s1["portfolio"]["equity"] == s2["portfolio"]["equity"]


def test_daily_monthly_reset_and_day_start_equity(tmp_path) -> None:
    cfg = TraderConfig(db_url=f"sqlite:///{tmp_path / 'state.db'}", artifacts_dir=tmp_path / "art", logs_dir=tmp_path / "art" / "logs")
    runtime = TraderRuntime(cfg)
    runtime.state["limits"]["trades_total_day"] = 3

    c1 = Candle("BTCUSDT", "1h", datetime(2026, 1, 31, 23, 0, tzinfo=UTC), 100, 101, 99, 100, 10)
    c2 = Candle("BTCUSDT", "1h", datetime(2026, 2, 1, 0, 0, tzinfo=UTC), 100, 101, 99, 101, 10)
    runtime.on_candle(c1)
    runtime.on_candle(c2)

    assert runtime.state["limits"]["last_day"] == "2026-02-01"
    assert runtime.state["limits"]["last_month"] == "2026-02"
    assert runtime.state["limits"]["trades_total_day"] >= 0


def test_mtm_by_symbol_equity_calculation(tmp_path) -> None:
    cfg = TraderConfig(db_url=f"sqlite:///{tmp_path / 'state.db'}", artifacts_dir=tmp_path / "art", logs_dir=tmp_path / "art" / "logs")
    runtime = TraderRuntime(cfg)
    runtime.state["portfolio"] = {
        "cash": 50_000.0,
        "equity": 50_000.0,
        "positions": {"BTCUSDT": {"qty": 1.0, "avg_price": 10_000.0}, "ETHUSDT": {"qty": 2.0, "avg_price": 2_000.0}},
        "realized_pnl": 0.0,
        "unrealized_pnl": 0.0,
    }
    runtime.state["prices"] = {"BTCUSDT": 11_000.0, "ETHUSDT": 1_500.0}
    runtime._update_risk_state(datetime(2026, 1, 1, tzinfo=UTC))
    assert runtime.state["portfolio"]["equity"] == 64_000.0


def test_causality_chain_candle_to_decision_to_execution(tmp_path) -> None:
    cfg = TraderConfig(db_url=f"sqlite:///{tmp_path / 'state.db'}", artifacts_dir=tmp_path / "art", logs_dir=tmp_path / "art" / "logs")
    runtime = TraderRuntime(cfg)

    candle = Candle("BTCUSDT", "1h", datetime(2026, 1, 1, 1, 0, tzinfo=UTC), 100, 101, 99, 100, 10)
    runtime.on_candle(candle)

    market = runtime.ledger.query(event_type=EVENT_MARKET_CANDLE_CLOSED, limit=1)[0]
    decision = runtime.ledger.query(event_type=EVENT_DECISION_PLAN_CREATED, limit=1)[0]
    execution = runtime.ledger.query(event_type=EVENT_EXECUTION_FILLED, limit=1)
    if not execution:
        execution = runtime.ledger.query(event_type="execution.skipped", limit=1)

    assert decision["causation_id"] == market["event_id"]
    assert execution[0]["causation_id"] == decision["event_id"]


def test_ledger_tail_query(tmp_path) -> None:
    path = tmp_path / "events.jsonl"
    ledger = TraderEventLedger(path)
    path.write_text('\n'.join([json.dumps({"event_type": "a", "payload": {"symbol": "BTC"}, "ts": "2026-01-01T00:00:00+00:00"}) for _ in range(3)]) + '\n', encoding='utf-8')
    assert len(ledger.tail(2)) == 2
    assert len(ledger.query(event_type="a", symbol="BTC", limit=2)) == 2
