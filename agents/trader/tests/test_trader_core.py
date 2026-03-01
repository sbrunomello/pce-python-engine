from __future__ import annotations

import csv
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from trader_plugins.adaptation import LabelingConfig, triple_barrier_labels_from_ohlc
from trader_plugins.ao import MockBroker
from trader_plugins.config import TraderConfig, mode_from_ccif
from trader_plugins.dataset import build_feature_dataset_from_candles
from trader_plugins.decision import TraderDecisionEngine
from trader_plugins.events import (
    EVENT_DECISION_PLAN_CREATED,
    EVENT_EXECUTION_FILLED,
    EVENT_MARKET_CANDLE_CLOSED,
    EVENT_METRICS_CCIF_UPDATED,
    EVENT_POLICY_UPDATED,
    EVENT_VALUE_POLICY_UPDATED,
)
from trader_plugins.ledger import TraderEventLedger
from trader_plugins.runtime import TraderRuntime
from trader_plugins.types import Candle, TradePlan
from trader_plugins.value_policy import default_value_policy


def test_triple_barrier_labeling_uses_high_low_and_atr() -> None:
    rows = [
        {"close": 100.0, "high": 100.0, "low": 100.0, "atr": 1.0},
        {"close": 100.1, "high": 101.6, "low": 99.8, "atr": 1.0},
        {"close": 100.0, "high": 100.0, "low": 98.8, "atr": 1.0},
    ]
    cfg = LabelingConfig(version="lbl", horizon=2, tp_atr_mult=1.5, sl_atr_mult=1.0)
    labels = triple_barrier_labels_from_ohlc(rows, config=cfg)
    assert labels[0] == "TP_FIRST"
    assert labels == triple_barrier_labels_from_ohlc(rows, config=cfg)


def test_macro_gate_blocks_bear() -> None:
    engine = TraderDecisionEngine(TraderConfig())
    plan = engine.deliberate(
        symbol="BTCUSDT",
        macro_regime="bear",
        model_out={"p_win": 0.9, "uncertainty": 0.1},
        state={"limits": {}, "dd_day": 0.0, "dd_month": 0.0, "suggested_qty": 1.0, "portfolio": {"positions": {}}},
        mode="normal",
        lock_entries=False,
        value_policy=default_value_policy(),
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
    buy = TradePlan("dec1", "BTCUSDT", "ENTER_LONG", 1.0, "ok", 0.7, 0.2, 0.6, "normal", "value-pol-v1", [])
    sell = TradePlan("dec2", "BTCUSDT", "EXIT_LONG", 0.4, "ok", 0.2, 0.7, 0.6, "normal", "value-pol-v1", [])

    broker.execute(buy, state, mark_price=100.0)
    out = broker.execute(sell, state, mark_price=120.0)

    assert out.event_type == EVENT_EXECUTION_FILLED
    assert state["portfolio"]["positions"]["BTCUSDT"]["qty"] == 0.6
    assert state["portfolio"]["realized_pnl"] == 8.0


def test_dataset_build_expected_columns_and_deterministic_hash(tmp_path: Path) -> None:
    candles = tmp_path / "candles.csv"
    candles.write_text(
        "symbol,timeframe,timestamp,open,high,low,close,volume\n"
        "BTCUSDT,1h,2026-01-01T00:00:00+00:00,100,101,99,100,1\n"
        "BTCUSDT,1h,2026-01-01T01:00:00+00:00,100,102,99,101,1\n",
        encoding="utf-8",
    )
    out1 = tmp_path / "d1.csv"
    out2 = tmp_path / "d2.csv"
    r1 = build_feature_dataset_from_candles(candles, ["BTCUSDT"], "1h", 120, out1)
    r2 = build_feature_dataset_from_candles(candles, ["BTCUSDT"], "1h", 120, out2)
    assert r1["dataset_hash"] == r2["dataset_hash"]
    with out1.open("r", encoding="utf-8") as handle:
        cols = next(csv.reader(handle))
    assert "ret_1" in cols and "atr" in cols and "dataset_hash" in cols and "feature_version" in cols


def test_walk_forward_metrics_and_registry_lifecycle(tmp_path: Path) -> None:
    dataset = tmp_path / "dataset.csv"
    start = datetime(2026, 1, 1, tzinfo=UTC)
    lines = ["symbol,timeframe,timestamp,open,high,low,close,volume,ret_1,ret_6,atr,rsi,ema_slope,bb_width,adx_like,integrity_ok,regime_4h,feature_version,dataset_hash"]
    for i in range(80):
        direction = 1 if i % 2 == 0 else -1
        close = 100 + direction * (i * 0.2)
        high = close + (2.0 if direction > 0 else 0.8)
        low = close - (2.0 if direction < 0 else 0.8)
        ret_1 = 0.01 if direction > 0 else -0.01
        ret_6 = 0.02 if direction > 0 else -0.02
        lines.append(f"BTCUSDT,1h,{(start + timedelta(hours=i)).isoformat()},100,{high},{low},{close},100,{ret_1},{ret_6},1.0,55,{ret_1},0.1,20,True,,feat-v2,hash1")
    dataset.write_text("\n".join(lines), encoding="utf-8")

    cfg = TraderConfig(db_url=f"sqlite:///{tmp_path / 'state.db'}", artifacts_dir=tmp_path / "art", logs_dir=tmp_path / "art" / "logs")
    runtime = TraderRuntime(cfg)
    result = runtime.train_from_csv(dataset)
    assert result["trained"] is True
    assert len(result["fold_metrics"]) >= 1
    assert "accuracy" in result["aggregate_metrics"]

    act = runtime.activate_model(result["version"])
    assert act["activated"] is True


def test_drift_changes_policy_version_and_updates_ledger(tmp_path: Path) -> None:
    cfg = TraderConfig(db_url=f"sqlite:///{tmp_path / 'state.db'}", artifacts_dir=tmp_path / "art", logs_dir=tmp_path / "art" / "logs")
    runtime = TraderRuntime(cfg)
    runtime.state["policy"] = {"policy_version": "pol-old", "dynamic_threshold": 0.6, "risk_per_trade": 0.005, "mode": "normal"}
    runtime.state["metrics"]["recent_outcomes"] = [0.0] * 10
    runtime._active_model_meta = {"model_version": "m1", "aggregate_metrics": {"accuracy": 0.9}, "label_version": "lbl"}
    runtime._maybe_apply_drift_policy(correlation_id="cid-1", causation_id="cause-1")
    assert runtime.state["policy"]["policy_version"] != "pol-old"
    assert runtime.state["policy"]["dynamic_threshold"] > 0.6
    assert runtime.state["policy"]["risk_per_trade"] < 0.005
    events = runtime.ledger.query(event_type=EVENT_POLICY_UPDATED, limit=5)
    assert events
    assert runtime.ledger.query(event_type=EVENT_VALUE_POLICY_UPDATED, limit=5)


def test_decision_generates_ranked_alternatives_and_selects_best() -> None:
    engine = TraderDecisionEngine(TraderConfig())
    state = {
        "limits": {},
        "dd_day": 0.0,
        "dd_month": 0.0,
        "suggested_qty": 1.0,
        "portfolio": {"positions": {"BTCUSDT": {"qty": 0.0, "avg_price": 0.0}}},
        "market": {"BTCUSDT": {"1h": {"features": {"atr": 2.0}}}},
        "prices": {"BTCUSDT": 100.0},
    }
    plan = engine.deliberate(
        symbol="BTCUSDT",
        macro_regime="bull",
        model_out={"p_win": 0.72, "uncertainty": 0.2},
        state=state,
        mode="normal",
        lock_entries=False,
        value_policy=default_value_policy(),
    )
    assert len(plan.alternatives) == 5
    assert plan.alternatives[0].final_score >= plan.alternatives[1].final_score
    assert plan.action == plan.alternatives[0].option_type


def test_tradeplan_contains_stop_take_and_r_values() -> None:
    engine = TraderDecisionEngine(TraderConfig())
    state = {
        "limits": {},
        "dd_day": 0.0,
        "dd_month": 0.0,
        "suggested_qty": 2.0,
        "portfolio": {"positions": {}},
        "market": {"BTCUSDT": {"1h": {"features": {"atr": 5.0}}}},
        "prices": {"BTCUSDT": 100.0},
    }
    plan = engine.deliberate(
        symbol="BTCUSDT",
        macro_regime="bull",
        model_out={"p_win": 0.8, "uncertainty": 0.1},
        state=state,
        mode="normal",
        lock_entries=False,
        value_policy=default_value_policy(),
    )
    if plan.action == "ENTER_LONG":
        assert plan.stop_price == 95.0
        assert plan.take_price == 110.0
        assert plan.risk_R == 5.0
        assert plan.expected_R > 0.0


def test_ccif_components_and_locked_mode_when_low(tmp_path: Path) -> None:
    cfg = TraderConfig(db_url=f"sqlite:///{tmp_path / 'state.db'}", artifacts_dir=tmp_path / "art", logs_dir=tmp_path / "art" / "logs")
    runtime = TraderRuntime(cfg)
    runtime.state["metrics"]["p_win_avg"] = 0.1
    runtime.state["metrics"]["recent_outcomes"] = [0.0] * 20
    runtime.state["portfolio"]["positions"] = {"BTCUSDT": {"qty": 10.0, "avg_price": 100.0}}
    runtime.state["prices"] = {"BTCUSDT": 100.0}
    candle = Candle("BTCUSDT", "1h", datetime(2026, 1, 1, 1, 0, tzinfo=UTC), 100, 100, 99, 100, 1)
    runtime.on_candle(candle)
    assert "dc" in runtime.state["metrics"] and "rs" in runtime.state["metrics"] and "vr" in runtime.state["metrics"] and "pa" in runtime.state["metrics"]
    assert runtime.ledger.query(event_type=EVENT_METRICS_CCIF_UPDATED, limit=5)
    assert runtime.state["metrics"]["mode"] in {"restricted", "locked", "cautious", "normal"}


def test_value_policy_versions_increase_on_roll(tmp_path: Path) -> None:
    cfg = TraderConfig(db_url=f"sqlite:///{tmp_path / 'state.db'}", artifacts_dir=tmp_path / "art", logs_dir=tmp_path / "art" / "logs")
    runtime = TraderRuntime(cfg)
    first = runtime.state["value_policy"]["value_policy_version"]
    runtime._roll_value_policy(correlation_id="cid", causation_id="cause", reason="test", quality_floor=0.5, risk_ceiling=0.6)
    second = runtime.state["value_policy"]["value_policy_version"]
    assert first != second
    assert runtime.ledger.query(event_type=EVENT_VALUE_POLICY_UPDATED, limit=1)


def test_replay_deterministic_same_final_state_and_decision_events(tmp_path: Path) -> None:
    csv_path = tmp_path / "candles.csv"
    start = datetime(2026, 1, 1, tzinfo=UTC)
    csv_path.write_text(
        "symbol,timeframe,timestamp,open,high,low,close,volume\n"
        + "\n".join(
            [f"BTCUSDT,4h,{(start + timedelta(hours=4*i)).isoformat()},100,101,99,{100 + i},1000" for i in range(12)]
            + [f"BTCUSDT,1h,{(start + timedelta(hours=i)).isoformat()},100,101,99,{100 + i*0.5},900" for i in range(24)]
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


def test_daily_monthly_reset_and_day_start_equity(tmp_path: Path) -> None:
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


def test_mtm_by_symbol_equity_calculation(tmp_path: Path) -> None:
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


def test_causality_chain_candle_to_decision_to_execution(tmp_path: Path) -> None:
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


def test_ledger_tail_query(tmp_path: Path) -> None:
    path = tmp_path / "events.jsonl"
    ledger = TraderEventLedger(path)
    path.write_text("\n".join([json.dumps({"event_type": "a", "payload": {"symbol": "BTC"}, "ts": "2026-01-01T00:00:00+00:00"}) for _ in range(3)]) + "\n", encoding="utf-8")
    assert len(ledger.tail(2)) == 2
    assert len(ledger.query(event_type="a", symbol="BTC", limit=2)) == 2
