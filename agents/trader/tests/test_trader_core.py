from __future__ import annotations

from datetime import UTC, datetime, timedelta

from trader_plugins.adaptation import triple_barrier_labels
from trader_plugins.ao import MockBroker
from trader_plugins.config import TraderConfig, mode_from_ccif
from trader_plugins.decision import TraderDecisionEngine
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
        state={"limits": {}, "dd_day": 0.0, "dd_month": 0.0, "suggested_qty": 1.0},
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


def test_mockbroker_deterministic_fill() -> None:
    broker = MockBroker(TraderConfig(fee_bps=10.0, slippage_bps=5.0))
    state = {"portfolio": {"cash": 10_000.0, "positions": {}}}
    plan = TradePlan(
        decision_id="dec1",
        symbol="BTCUSDT",
        action="BUY",
        qty=1.0,
        reason="ok",
        p_win=0.7,
        uncertainty=0.2,
        threshold=0.6,
        mode="normal",
        gate_results=[],
    )
    fill1 = broker.execute(plan, state, mark_price=100.0)
    state2 = {"portfolio": {"cash": 10_000.0, "positions": {}}}
    fill2 = broker.execute(plan, state2, mark_price=100.0)
    assert fill1.payload["price"] == fill2.payload["price"]
    assert fill1.payload["fee"] == fill2.payload["fee"]


def test_replay_deterministic_same_final_state(tmp_path) -> None:
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

    cfg1 = TraderConfig(db_url=f"sqlite:///{tmp_path / 'state1.db'}")
    cfg2 = TraderConfig(db_url=f"sqlite:///{tmp_path / 'state2.db'}")

    r1 = TraderRuntime(cfg1)
    d1 = r1.replay_csv(csv_path)
    s1 = r1.state

    r2 = TraderRuntime(cfg2)
    d2 = r2.replay_csv(csv_path)
    s2 = r2.state

    assert len(d1) == len(d2)
    assert s1["portfolio"]["equity"] == s2["portfolio"]["equity"]
    assert s1["metrics"]["decisions_total"] == s2["metrics"]["decisions_total"]
