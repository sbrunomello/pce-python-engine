"""End-to-end Trader runtime wiring EPL->ISI->VEL->SM->DE->AO->AFS with governed learning lifecycle."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from trader_plugins.adaptation import FEATURE_COLUMNS, LabelingConfig, TraderAFS, triple_barrier_labels_from_ohlc
from trader_plugins.ao import MockBroker
from trader_plugins.config import TraderConfig, mode_from_ccif
from trader_plugins.dataset import build_feature_dataset_from_candles
from trader_plugins.decision import TraderDecisionEngine
from trader_plugins.epl import TraderEPL
from trader_plugins.events import (
    EVENT_DATA_INTEGRITY_DEGRADED,
    EVENT_DECISION_PLAN_CREATED,
    EVENT_EXECUTION_FILLED,
    EVENT_EXECUTION_SKIPPED,
    EVENT_GUARDRAIL_LOCKED,
    EVENT_GUARDRAIL_UNLOCKED,
    EVENT_LEARNING_DRIFT_DETECTED,
    EVENT_LEARNING_MODEL_PROMOTED,
    EVENT_LEARNING_MODEL_ROLLED_BACK,
    EVENT_LEARNING_TRAIN_RUN_COMPLETED,
    EVENT_LEARNING_TRAIN_RUN_STARTED,
    EVENT_METRICS_UPDATED,
    EVENT_POLICY_UPDATED,
    EVENT_STATE_INTEGRATED,
    EventEnvelope,
)
from trader_plugins.expression import TraderExpressionLayer
from trader_plugins.isi import TraderISI
from trader_plugins.ledger import TraderEventLedger
from trader_plugins.registry import ModelRegistry
from trader_plugins.storage import TraderStorage
from trader_plugins.types import Candle
from trader_plugins.value_model import TraderValueModel


class TraderRuntime:
    """Independent runtime for demo trading with mock execution."""

    def __init__(self, config: TraderConfig | None = None) -> None:
        self.config = config or TraderConfig()
        self.config.logs_dir.mkdir(parents=True, exist_ok=True)
        self.storage = TraderStorage(self.config.db_url)
        self.state = self.storage.load_runtime_state()
        self.ledger = TraderEventLedger(self.config.artifacts_dir / "ledger" / "events.jsonl")
        self.epl = TraderEPL()
        self.isi = TraderISI()
        self.vel = TraderValueModel()
        self.de = TraderDecisionEngine(self.config)
        self.ao = MockBroker(self.config)
        self.afs = TraderAFS(self.config)
        self.expression = TraderExpressionLayer()
        self._ensure_state_defaults()
        self._active_model_meta = self._load_active_model_meta()
        self._active_model = self._load_active_model()

    def build_dataset_from_candles(self, candles_csv: Path, out_path: Path, symbols: list[str], timeframe: str) -> dict[str, Any]:
        return build_feature_dataset_from_candles(candles_csv, symbols=symbols, timeframe=timeframe, lookback_max=1200, out_path=out_path, config=self.config)

    def replay_csv(self, csv_path: Path) -> list[dict[str, Any]]:
        decisions: list[dict[str, Any]] = []
        with csv_path.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                candle = Candle(
                    symbol=str(row["symbol"]),
                    timeframe=str(row["timeframe"]),
                    timestamp=datetime.fromisoformat(str(row["timestamp"])),
                    open=float(row["open"]),
                    high=float(row["high"]),
                    low=float(row["low"]),
                    close=float(row["close"]),
                    volume=float(row["volume"]),
                )
                decision = self.on_candle(candle)
                if decision:
                    decisions.append(decision)
        self._persist()
        return decisions

    def train_from_csv(self, csv_path: Path) -> dict[str, object]:
        run_id = f"train-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        started = self._emit(
            event_type=EVENT_LEARNING_TRAIN_RUN_STARTED,
            source="trader/afs",
            actor="trader/afs",
            correlation_id=run_id,
            payload={"run_id": run_id, "dataset": str(csv_path)},
        )

        rows = self._load_dataset_rows(csv_path)
        labels = triple_barrier_labels_from_ohlc(
            rows,
            config=LabelingConfig(
                version=self.config.label_version,
                horizon=self.config.label_horizon_candles,
                tp_atr_mult=self.config.label_tp_atr_mult,
                sl_atr_mult=self.config.label_sl_atr_mult,
            ),
        )
        result = self.afs.train(
            [{k: float(r.get(k, 0.0)) for k in FEATURE_COLUMNS} for r in rows],
            labels,
            dataset_hash=str(rows[0].get("dataset_hash", "unknown")) if rows else "unknown",
            feature_version=self.config.feature_version,
            label_version=self.config.label_version,
        )
        result["run_id"] = run_id
        result["labeling"] = {
            "label_version": self.config.label_version,
            "horizon": self.config.label_horizon_candles,
            "tp_atr_mult": self.config.label_tp_atr_mult,
            "sl_atr_mult": self.config.label_sl_atr_mult,
        }

        if bool(result.get("trained")):
            self._register_training_result(result)

        self._emit(
            event_type=EVENT_LEARNING_TRAIN_RUN_COMPLETED,
            source="trader/afs",
            actor="trader/afs",
            correlation_id=run_id,
            causation_id=started.event_id,
            payload={
                "run_id": run_id,
                "trained": bool(result.get("trained")),
                "dataset_hash": result.get("dataset_hash"),
                "feature_version": self.config.feature_version,
                "label_version": self.config.label_version,
                "model_version": result.get("version"),
                "fold_metrics": result.get("fold_metrics", []),
                "aggregate_metrics": result.get("aggregate_metrics", {}),
            },
        )
        self._persist()
        return result

    def activate_model(self, model_version: str) -> dict[str, Any]:
        registry = ModelRegistry(self.storage.load_model_registry())
        rec = registry.set_active(model_version, reason="manual_activation")
        if rec is None:
            return {"activated": False, "reason": "model_not_found", "model_version": model_version}
        self.storage.save_model_registry(registry.records)
        self.state.setdefault("models", {})["active"] = model_version
        self.state.setdefault("models", {})["active_model_version"] = model_version
        self._active_model_meta = rec
        self._active_model = self.afs.load_model(model_version)
        self._emit(
            event_type=EVENT_LEARNING_MODEL_PROMOTED,
            source="trader/registry",
            actor="trader/registry",
            correlation_id=f"promote-{model_version}",
            payload={"model_version": model_version, "reason": "manual_activation"},
        )
        self._persist()
        return {"activated": True, "model_version": model_version}

    def live_demo_once(self) -> list[dict[str, Any]]:
        output: list[dict[str, Any]] = []
        for symbol in self.config.symbols:
            for timeframe in [self.config.execution_timeframe, self.config.macro_timeframe]:
                candle = _fetch_latest_binance_candle(symbol, timeframe)
                if candle is None:
                    continue
                decision = self.on_candle(candle)
                if decision is not None:
                    output.append(decision)
        self._persist()
        return output

    def on_candle(self, candle: Candle) -> dict[str, Any] | None:
        market_event = self.epl.ingest(candle)
        self.ledger.append(market_event)
        integrated = self.isi.integrate(market_event)
        symbol = integrated["symbol"]
        timeframe = integrated["timeframe"]
        features = integrated["features"]

        self.state.setdefault("market", {}).setdefault(symbol, {})[timeframe] = integrated
        self._update_prices(symbol, float(features.get("last_close", candle.close)))
        self._update_risk_state(candle.timestamp)

        state_event = self._emit(
            event_type=EVENT_STATE_INTEGRATED,
            source="trader/isi",
            actor="trader/isi",
            correlation_id=market_event.correlation_id,
            causation_id=market_event.event_id,
            payload={
                "symbol": symbol,
                "timeframe": timeframe,
                "timestamp": integrated["timestamp"],
                "regime": integrated["regime"],
                "features": {"ret_1": features.get("ret_1"), "ret_6": features.get("ret_6"), "atr": features.get("atr"), "rsi": features.get("rsi"), "integrity_ok": features.get("integrity_ok")},
            },
        )

        data_lock = not bool(features.get("integrity_ok", True))
        if data_lock:
            self._emit(
                event_type=EVENT_DATA_INTEGRITY_DEGRADED,
                source="trader/isi",
                actor="trader/isi",
                correlation_id=market_event.correlation_id,
                causation_id=state_event.event_id,
                payload={"symbol": symbol, "timeframe": timeframe, "issues": list(features.get("integrity_issues", []))},
            )

        if timeframe != self.config.execution_timeframe:
            self._emit_metrics(market_event.correlation_id, state_event.event_id, reset_reason="market_update")
            self._persist()
            return None

        macro = self.state.get("market", {}).get(symbol, {}).get(self.config.macro_timeframe, {})
        macro_regime = str(macro.get("regime", "sideways")) if isinstance(macro, dict) else "sideways"
        p_win, uncertainty, model_missing = self._model_predict(features)

        value_scores = self.vel.evaluate(integrated, p_win)
        previous_mode = str(self.state.get("metrics", {}).get("mode", "cautious"))
        self._update_ccif(value_scores, data_lock)
        if model_missing:
            self.state.setdefault("metrics", {})["mode"] = "restricted"
        self._emit_guardrail_transition(previous_mode, str(self.state.get("metrics", {}).get("mode", "cautious")), market_event)

        suggested_qty = self._size_from_risk(float(features.get("atr", 0.0)), float(features.get("last_close", candle.close)))
        self.state["suggested_qty"] = suggested_qty

        plan = self.de.deliberate(
            symbol=str(symbol),
            macro_regime=macro_regime,
            model_out={"p_win": p_win, "uncertainty": uncertainty, "model_missing": 1.0 if model_missing else 0.0},
            state=self.state,
            mode=str(self.state.get("metrics", {}).get("mode", "cautious")),
            lock_entries=data_lock,
        )

        decision_event = self._emit(
            event_type=EVENT_DECISION_PLAN_CREATED,
            source="trader/de",
            actor="trader/de",
            correlation_id=market_event.correlation_id,
            causation_id=market_event.event_id,
            payload={
                "symbol": symbol,
                "plan": asdict(plan),
                "references": {"correlation_id": market_event.correlation_id, "causation_id": market_event.event_id},
                "risk_budget": self.state.get("risk_budget", 0.0),
                "equity": self.state.get("portfolio", {}).get("equity", self.config.starting_cash),
                "model_version": self.state.get("models", {}).get("active_model_version"),
                "feature_version": self.config.feature_version,
                "label_version": self._active_model_meta.get("label_version") if isinstance(self._active_model_meta, dict) else self.config.label_version,
                "policy_version": self.state.get("policy", {}).get("policy_version"),
                "model_missing": model_missing,
            },
        )

        fill = self.ao.execute(plan, self.state, float(features.get("last_close", candle.close)))
        execution_event = self._emit(
            event_type=fill.event_type if fill.event_type in {EVENT_EXECUTION_FILLED, EVENT_EXECUTION_SKIPPED} else EVENT_EXECUTION_SKIPPED,
            source=fill.source,
            actor="trader/ao",
            correlation_id=market_event.correlation_id,
            causation_id=decision_event.event_id,
            payload=fill.payload,
        )

        self._record_outcome(plan, execution_event.event_type)
        self._maybe_apply_drift_policy(correlation_id=market_event.correlation_id, causation_id=execution_event.event_id)

        fills = self.state.setdefault("fills", [])
        if isinstance(fills, list):
            fills.append(fill.payload)
            if len(fills) > 500:
                del fills[:-500]

        if execution_event.event_type == EVENT_EXECUTION_FILLED:
            limits = self.state.get("limits", {})
            limits["trades_total_day"] = int(limits.get("trades_total_day", 0)) + 1
            by_asset = limits.setdefault("trades_by_asset_day", {})
            by_asset[symbol] = int(by_asset.get(symbol, 0)) + 1
            self.state.get("metrics", {})["trades_executed"] = int(self.state.get("metrics", {}).get("trades_executed", 0)) + 1

        self.state.get("metrics", {})["decisions_total"] = int(self.state.get("metrics", {}).get("decisions_total", 0)) + 1
        self.state.get("metrics", {})["p_win_avg"] = float(self.state.get("metrics", {}).get("p_win_avg", 0.0)) * 0.9 + p_win * 0.1

        self._update_portfolio_unrealized()
        self._update_risk_state(candle.timestamp)

        metrics_event = self._emit_metrics(market_event.correlation_id, execution_event.event_id)
        explanation = self.expression.explain(plan, {"dd_day": self.state.get("dd_day", 0.0), "dd_month": self.state.get("dd_month", 0.0), "ccif": self.state.get("metrics", {}).get("cci_f", 0.0), "mode": self.state.get("metrics", {}).get("mode", "cautious")})

        decision = {
            "decision_id": plan.decision_id,
            "event_id": market_event.event_id,
            "decision_event_id": decision_event.event_id,
            "execution_event_id": execution_event.event_id,
            "metrics_event_id": metrics_event.event_id,
            "symbol": symbol,
            "plan": asdict(plan),
            "execution": fill.payload,
            "metrics": self.state.get("metrics", {}),
            "explanation": explanation,
            "correlation_id": market_event.correlation_id,
            "causation_id": market_event.event_id,
            "model_version": self.state.get("models", {}).get("active_model_version"),
            "feature_version": self.config.feature_version,
            "label_version": self._active_model_meta.get("label_version") if isinstance(self._active_model_meta, dict) else self.config.label_version,
            "policy_version": self.state.get("policy", {}).get("policy_version"),
        }
        self._log_json("decisions", decision)
        self._persist()
        return decision

    def _load_dataset_rows(self, csv_path: Path) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        with csv_path.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if row.get("timeframe") != self.config.execution_timeframe:
                    continue
                rows.append(
                    {
                        "symbol": str(row.get("symbol", "")),
                        "timeframe": str(row.get("timeframe", "")),
                        "timestamp": str(row.get("timestamp", "")),
                        "open": float(row.get("open", 0.0)),
                        "high": float(row.get("high", row.get("close", 0.0))),
                        "low": float(row.get("low", row.get("close", 0.0))),
                        "close": float(row.get("close", 0.0)),
                        "atr": float(row.get("atr", 0.0)),
                        "ret_1": float(row.get("ret_1", 0.0)),
                        "ret_6": float(row.get("ret_6", 0.0)),
                        "rsi": float(row.get("rsi", 50.0)),
                        "ema_slope": float(row.get("ema_slope", 0.0)),
                        "bb_width": float(row.get("bb_width", 0.0)),
                        "adx_like": float(row.get("adx_like", 0.0)),
                        "dataset_hash": str(row.get("dataset_hash", "")),
                    }
                )
        return rows

    def _register_training_result(self, result: dict[str, Any]) -> None:
        registry = ModelRegistry(self.storage.load_model_registry())
        parent = registry.active()
        rec = registry.add_candidate(result, parent_version=parent.get("model_version") if parent else None)

        if self.config.model_auto_promote_approved_to_active and rec.get("status") == "approved":
            registry.set_active(str(rec["model_version"]), reason="auto_promotion")
            self.state.setdefault("models", {})["active"] = rec["model_version"]
            self.state.setdefault("models", {})["active_model_version"] = rec["model_version"]
            self._active_model_meta = rec
            self._active_model = self.afs.load_model(str(rec["model_version"]))
            self._emit(
                event_type=EVENT_LEARNING_MODEL_PROMOTED,
                source="trader/registry",
                actor="trader/registry",
                correlation_id=f"promote-{rec['model_version']}",
                payload={"model_version": rec["model_version"], "reason": "auto_promotion"},
            )
        self.storage.save_model_registry(registry.records)

    def _emit(self, *, event_type: str, source: str, correlation_id: str, payload: dict[str, Any], causation_id: str | None = None, actor: str | None = None) -> EventEnvelope:
        env = EventEnvelope(event_type=event_type, source=source, payload=payload, correlation_id=correlation_id, causation_id=causation_id, actor=actor)
        self.ledger.append(env)
        return env

    def _emit_metrics(self, correlation_id: str, causation_id: str, reset_reason: str | None = None) -> EventEnvelope:
        payload = {
            "cci_f": self.state.get("metrics", {}).get("cci_f", 0.0),
            "dd_day": self.state.get("dd_day", 0.0),
            "dd_month": self.state.get("dd_month", 0.0),
            "trades_total_day": self.state.get("limits", {}).get("trades_total_day", 0),
            "mode": self.state.get("metrics", {}).get("mode", "cautious"),
            "equity": self.state.get("portfolio", {}).get("equity", self.config.starting_cash),
            "policy_version": self.state.get("policy", {}).get("policy_version"),
        }
        if reset_reason:
            payload["reset_reason"] = reset_reason
        return self._emit(event_type=EVENT_METRICS_UPDATED, source="trader/runtime", actor="trader/runtime", correlation_id=correlation_id, causation_id=causation_id, payload=payload)

    def _emit_guardrail_transition(self, previous_mode: str, current_mode: str, market_event: EventEnvelope) -> None:
        if previous_mode != "locked" and current_mode == "locked":
            self._emit(event_type=EVENT_GUARDRAIL_LOCKED, source="trader/runtime", actor="trader/runtime", correlation_id=market_event.correlation_id, causation_id=market_event.event_id, payload={"reason": "mode_locked", "symbol": market_event.payload.get("symbol")})
        elif previous_mode == "locked" and current_mode != "locked":
            self._emit(event_type=EVENT_GUARDRAIL_UNLOCKED, source="trader/runtime", actor="trader/runtime", correlation_id=market_event.correlation_id, causation_id=market_event.event_id, payload={"reason": "mode_recovered", "symbol": market_event.payload.get("symbol")})

    def _size_from_risk(self, atr: float, price: float) -> float:
        equity = float(self.state.get("portfolio", {}).get("equity", self.config.starting_cash))
        risk_per_trade = float(self.state.get("policy", {}).get("risk_per_trade", self.config.risk.risk_per_trade))
        risk_budget = equity * risk_per_trade
        self.state["risk_budget"] = risk_budget
        stop_distance = max(atr, price * 0.005)
        mode = str(self.state.get("metrics", {}).get("mode", "cautious"))
        if mode == "locked" or stop_distance <= 0:
            return 0.0
        qty = risk_budget / stop_distance
        return round(max(0.0, qty), 6)

    def _model_predict(self, features: dict[str, Any]) -> tuple[float, float, bool]:
        if self._active_model is None:
            baseline = 0.55 + 0.20 * max(-1.0, min(1.0, float(features.get("ema_slope", 0.0)) * 20))
            return max(0.0, min(1.0, baseline)), 0.5, True
        numeric = {k: float(v) for k, v in features.items() if isinstance(v, (int, float))}
        p_win, uncertainty = self._active_model.predict(numeric)
        return p_win, uncertainty, False

    def _load_active_model(self):
        active = self.state.get("models", {}).get("active_model_version") or self.state.get("models", {}).get("active")
        if isinstance(active, str):
            return self.afs.load_model(active)
        return None

    def _load_active_model_meta(self) -> dict[str, Any]:
        active = self.state.get("models", {}).get("active_model_version") or self.state.get("models", {}).get("active")
        records = self.storage.load_model_registry()
        for rec in records:
            if rec.get("model_version") == active:
                return rec
        return {"model_version": active, "label_version": self.config.label_version}

    def _update_ccif(self, value_scores: dict[str, object], data_lock: bool) -> None:
        current = float(self.state.get("metrics", {}).get("cci_f", 0.8))
        opportunity = float(value_scores.get("opportunity", 0.0))
        risk = float(value_scores.get("risk", 1.0))
        quality = float(value_scores.get("quality", 0.0))
        next_ccif = max(0.0, min(1.0, 0.6 * current + 0.2 * opportunity + 0.2 * (1 - risk) * quality))
        mode = mode_from_ccif(next_ccif, locked=data_lock)
        self.state.setdefault("metrics", {})["cci_f"] = next_ccif
        self.state.setdefault("metrics", {})["mode"] = mode

    def _record_outcome(self, plan, event_type: str) -> None:
        if event_type != EVENT_EXECUTION_FILLED:
            return
        outcome = 1.0 if plan.action == "ENTER_LONG" and plan.p_win >= plan.threshold else 0.0
        recent = self.state.setdefault("metrics", {}).setdefault("recent_outcomes", [])
        if isinstance(recent, list):
            recent.append(outcome)
            if len(recent) > self.config.drift_recent_window:
                del recent[:-self.config.drift_recent_window]

    def _maybe_apply_drift_policy(self, *, correlation_id: str, causation_id: str) -> None:
        active = self._active_model_meta if isinstance(self._active_model_meta, dict) else {}
        baseline = float((active.get("aggregate_metrics") or {}).get("accuracy", 0.0))
        if baseline <= 0:
            return
        recent = self.state.get("metrics", {}).get("recent_outcomes", [])
        if not isinstance(recent, list) or len(recent) < 5:
            return
        drift = self.afs.drift_check([float(x) for x in recent], baseline)
        if not bool(drift.get("flag")):
            return
        self._emit(event_type=EVENT_LEARNING_DRIFT_DETECTED, source="trader/afs", actor="trader/afs", correlation_id=correlation_id, causation_id=causation_id, payload={"drift": drift, "active_model": active.get("model_version")})

        policy = self.state.setdefault("policy", {})
        policy["dynamic_threshold"] = min(self.config.drift_threshold_max, float(policy.get("dynamic_threshold", self.config.p_win_threshold)) + self.config.drift_threshold_step)
        policy["risk_per_trade"] = max(0.0001, float(policy.get("risk_per_trade", self.config.risk.risk_per_trade)) * self.config.drift_risk_multiplier)
        policy["mode"] = "restricted"
        policy["policy_version"] = f"pol-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}-{correlation_id[:4]}"
        self.state["dynamic_threshold"] = policy["dynamic_threshold"]
        self.state.setdefault("metrics", {})["mode"] = "restricted"

        self._emit(event_type=EVENT_POLICY_UPDATED, source="trader/policy", actor="trader/policy", correlation_id=correlation_id, causation_id=causation_id, payload=policy)

        registry = ModelRegistry(self.storage.load_model_registry())
        current = registry.active()
        prev = registry.previous_approved(exclude_version=current.get("model_version") if current else None)
        if current and prev:
            registry.rollback(from_version=str(current.get("model_version")), to_version=str(prev.get("model_version")), reason="drift_performance_drop")
            self.storage.save_model_registry(registry.records)
            self.state.setdefault("models", {})["active_model_version"] = prev.get("model_version")
            self.state.setdefault("models", {})["active"] = prev.get("model_version")
            self._active_model_meta = prev
            self._active_model = self.afs.load_model(str(prev.get("model_version")))
            self._emit(event_type=EVENT_LEARNING_MODEL_ROLLED_BACK, source="trader/registry", actor="trader/registry", correlation_id=correlation_id, payload={"from": current.get("model_version"), "to": prev.get("model_version"), "reason": "drift_performance_drop"})

    def _update_prices(self, symbol: str, mark_price: float) -> None:
        self.state.setdefault("prices", {})[symbol] = mark_price

    def _update_portfolio_unrealized(self) -> None:
        portfolio = self.state.get("portfolio", {})
        positions = portfolio.get("positions", {}) if isinstance(portfolio.get("positions"), dict) else {}
        prices = self.state.get("prices", {}) if isinstance(self.state.get("prices"), dict) else {}
        unrealized = 0.0
        for sym, pos in positions.items():
            if not isinstance(pos, dict):
                continue
            qty = float(pos.get("qty", 0.0))
            if qty <= 0:
                continue
            avg = float(pos.get("avg_price", 0.0))
            mark = float(prices.get(sym, avg))
            unrealized += (mark - avg) * qty
        portfolio["unrealized_pnl"] = unrealized

    def _apply_period_resets(self, now_ts: datetime) -> list[str]:
        limits = self.state.setdefault("limits", {})
        portfolio = self.state.setdefault("portfolio", {})
        day_key = now_ts.astimezone(UTC).strftime("%Y-%m-%d")
        month_key = now_ts.astimezone(UTC).strftime("%Y-%m")
        events: list[str] = []
        if str(limits.get("last_day", "")) != day_key:
            limits["trades_total_day"] = 0
            limits["trades_by_asset_day"] = {}
            limits["day_start_equity"] = float(portfolio.get("equity", self.config.starting_cash))
            limits["last_day"] = day_key
            events.append("daily")
        if str(limits.get("last_month", "")) != month_key:
            limits["month_start_equity"] = float(portfolio.get("equity", self.config.starting_cash))
            limits["last_month"] = month_key
            events.append("monthly")
        return events

    def _update_risk_state(self, now_ts: datetime) -> None:
        portfolio = self.state.get("portfolio", {})
        cash = float(portfolio.get("cash", 0.0))
        positions = portfolio.get("positions", {}) if isinstance(portfolio.get("positions"), dict) else {}
        prices = self.state.get("prices", {}) if isinstance(self.state.get("prices"), dict) else {}
        mtm = 0.0
        for sym, pos in positions.items():
            if isinstance(pos, dict):
                mtm += float(pos.get("qty", 0.0)) * float(prices.get(sym, pos.get("avg_price", 0.0)))
        equity = cash + mtm
        portfolio["equity"] = equity
        self._apply_period_resets(now_ts)
        limits = self.state.setdefault("limits", {})
        day_start = float(limits.get("day_start_equity", equity))
        month_start = float(limits.get("month_start_equity", equity))
        self.state["dd_day"] = max(0.0, (day_start - equity) / max(day_start, 1e-9))
        self.state["dd_month"] = max(0.0, (month_start - equity) / max(month_start, 1e-9))

    def _ensure_state_defaults(self) -> None:
        self.state.setdefault("policy", {})
        policy = self.state["policy"]
        policy.setdefault("policy_version", self.config.policy_version)
        policy.setdefault("dynamic_threshold", self.config.p_win_threshold)
        policy.setdefault("risk_per_trade", self.config.risk.risk_per_trade)
        policy.setdefault("mode", "restricted")
        self.state.setdefault("dynamic_threshold", policy["dynamic_threshold"])
        self.state.setdefault("models", {}).setdefault("active_model_version", self.state.get("models", {}).get("active"))

    def _persist(self) -> None:
        self.storage.save_runtime_state(self.state)

    def _log_json(self, stream: str, payload: dict[str, Any]) -> None:
        path = self.config.logs_dir / f"{stream}.jsonl"
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _fetch_latest_binance_candle(symbol: str, timeframe: str) -> Candle | None:
    interval = "1h" if timeframe == "1h" else "4h"
    url = "https://api.binance.com/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": 1}
    try:
        response = httpx.get(url, params=params, timeout=4.0)
        response.raise_for_status()
        rows = response.json()
        if not isinstance(rows, list) or not rows:
            return None
        row = rows[0]
        ts = datetime.fromtimestamp(int(row[0]) / 1000, tz=UTC)
        return Candle(symbol=symbol, timeframe=timeframe, timestamp=ts, open=float(row[1]), high=float(row[2]), low=float(row[3]), close=float(row[4]), volume=float(row[5]))
    except Exception:
        return None
