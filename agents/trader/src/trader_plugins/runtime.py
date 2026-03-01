"""End-to-end Trader runtime wiring EPL->ISI->VEL->SM->DE->AO->AFS."""

from __future__ import annotations

import csv
import json
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from trader_plugins.adaptation import TraderAFS, triple_barrier_labels
from trader_plugins.ao import MockBroker
from trader_plugins.config import TraderConfig, mode_from_ccif
from trader_plugins.decision import TraderDecisionEngine
from trader_plugins.epl import TraderEPL
from trader_plugins.expression import TraderExpressionLayer
from trader_plugins.isi import TraderISI
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
        self.epl = TraderEPL()
        self.isi = TraderISI()
        self.vel = TraderValueModel()
        self.de = TraderDecisionEngine(self.config)
        self.ao = MockBroker(self.config)
        self.afs = TraderAFS(self.config)
        self.expression = TraderExpressionLayer()
        self._active_model = self._load_active_model()

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
        rows: list[dict[str, float]] = []
        closes: list[float] = []
        with csv_path.open("r", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                if row.get("timeframe") != self.config.execution_timeframe:
                    continue
                closes.append(float(row["close"]))
                rows.append(
                    {
                        "ret_1": float(row.get("ret_1", 0.0)),
                        "ret_6": float(row.get("ret_6", 0.0)),
                        "atr": float(row.get("atr", 0.0)),
                        "rsi": float(row.get("rsi", 50.0)),
                        "ema_slope": float(row.get("ema_slope", 0.0)),
                        "bb_width": float(row.get("bb_width", 0.0)),
                        "adx_like": float(row.get("adx_like", 0.0)),
                    }
                )
        labels = triple_barrier_labels(closes, horizon=self.config.prediction_horizon_hours)
        result = self.afs.train(rows, labels)
        if bool(result.get("trained")):
            registry = self.storage.load_model_registry()
            status = str(result["status"])
            if status == "approved":
                status = "active"
                self.state.setdefault("models", {})["active"] = result["version"]
            registry.append({**result, "status": status, "created_at": datetime.now(UTC).isoformat()})
            self.storage.save_model_registry(registry)
            self._active_model = self.afs.load_model(str(result["version"]))
        return result

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
        event = self.epl.ingest(candle)
        integrated = self.isi.integrate(event)
        symbol = integrated["symbol"]
        timeframe = integrated["timeframe"]

        self.state.setdefault("market", {}).setdefault(symbol, {})[timeframe] = integrated
        features = integrated["features"]
        data_lock = not bool(features.get("integrity_ok", True))

        if timeframe != self.config.execution_timeframe:
            self._persist()
            return None

        macro = self.state.get("market", {}).get(symbol, {}).get(self.config.macro_timeframe, {})
        macro_regime = str(macro.get("regime", "sideways")) if isinstance(macro, dict) else "sideways"

        p_win, uncertainty = self._model_predict(features)
        value_scores = self.vel.evaluate(integrated, p_win)
        self._update_ccif(value_scores, data_lock)
        self._update_risk_state(symbol, float(features.get("last_close", candle.close)))

        suggested_qty = self._size_from_risk(float(features.get("atr", 0.0)), float(features.get("last_close", candle.close)))
        self.state["suggested_qty"] = suggested_qty
        plan = self.de.deliberate(
            symbol=str(symbol),
            macro_regime=macro_regime,
            model_out={"p_win": p_win, "uncertainty": uncertainty},
            state=self.state,
            mode=str(self.state.get("metrics", {}).get("mode", "cautious")),
            lock_entries=data_lock,
        )
        fill = self.ao.execute(plan, self.state, float(features.get("last_close", candle.close)))
        if fill.event_type == "execution.fill":
            limits = self.state.get("limits", {})
            limits["trades_total_day"] = int(limits.get("trades_total_day", 0)) + 1
            by_asset = limits.setdefault("trades_by_asset_day", {})
            by_asset[symbol] = int(by_asset.get(symbol, 0)) + 1
            self.state.get("metrics", {})["trades_executed"] = int(self.state.get("metrics", {}).get("trades_executed", 0)) + 1

        self.state.get("metrics", {})["decisions_total"] = int(self.state.get("metrics", {}).get("decisions_total", 0)) + 1
        self.state.get("metrics", {})["p_win_avg"] = (
            float(self.state.get("metrics", {}).get("p_win_avg", 0.0)) * 0.9 + p_win * 0.1
        )

        explanation = self.expression.explain(
            plan,
            {
                "dd_day": self.state.get("dd_day", 0.0),
                "dd_month": self.state.get("dd_month", 0.0),
                "ccif": self.state.get("metrics", {}).get("cci_f", 0.0),
                "mode": self.state.get("metrics", {}).get("mode", "cautious"),
            },
        )

        decision = {
            "decision_id": plan.decision_id,
            "event_id": event.event_id,
            "symbol": symbol,
            "plan": asdict(plan),
            "execution": fill.payload,
            "metrics": self.state.get("metrics", {}),
            "explanation": explanation,
        }
        self._log_json("decisions", decision)
        self._persist()
        return decision

    def _size_from_risk(self, atr: float, price: float) -> float:
        equity = float(self.state.get("portfolio", {}).get("equity", self.config.starting_cash))
        risk_budget = equity * self.config.risk.risk_per_trade
        stop_distance = max(atr, price * 0.005)
        qty = risk_budget / max(stop_distance, 1e-9)
        return round(max(0.0, qty), 6)

    def _model_predict(self, features: dict[str, Any]) -> tuple[float, float]:
        if self._active_model is None:
            baseline = 0.55 + 0.20 * max(-1.0, min(1.0, float(features.get("ema_slope", 0.0)) * 20))
            return max(0.0, min(1.0, baseline)), 0.5
        numeric = {k: float(v) for k, v in features.items() if isinstance(v, (int, float))}
        return self._active_model.predict(numeric)

    def _load_active_model(self):
        active = self.state.get("models", {}).get("active") if isinstance(self.state.get("models"), dict) else None
        if isinstance(active, str):
            return self.afs.load_model(active)
        return None

    def _update_ccif(self, value_scores: dict[str, object], data_lock: bool) -> None:
        current = float(self.state.get("metrics", {}).get("cci_f", 0.8))
        opportunity = float(value_scores.get("opportunity", 0.0))
        risk = float(value_scores.get("risk", 1.0))
        quality = float(value_scores.get("quality", 0.0))
        next_ccif = max(0.0, min(1.0, 0.6 * current + 0.2 * opportunity + 0.2 * (1 - risk) * quality))
        mode = mode_from_ccif(next_ccif, locked=data_lock)
        self.state.setdefault("metrics", {})["cci_f"] = next_ccif
        self.state.setdefault("metrics", {})["mode"] = mode

    def _update_risk_state(self, symbol: str, mark_price: float) -> None:
        _ = symbol
        portfolio = self.state.get("portfolio", {})
        cash = float(portfolio.get("cash", 0.0))
        positions = portfolio.get("positions", {}) if isinstance(portfolio.get("positions"), dict) else {}
        mtm = 0.0
        for pos in positions.values():
            if isinstance(pos, dict):
                mtm += float(pos.get("qty", 0.0)) * mark_price
        equity = cash + mtm
        portfolio["equity"] = equity

        limits = self.state.setdefault("limits", {})
        day_start = float(limits.get("day_start_equity", equity))
        month_start = float(limits.get("month_start_equity", equity))
        self.state["dd_day"] = max(0.0, (day_start - equity) / max(day_start, 1e-9))
        self.state["dd_month"] = max(0.0, (month_start - equity) / max(month_start, 1e-9))

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
        return Candle(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=ts,
            open=float(row[1]),
            high=float(row[2]),
            low=float(row[3]),
            close=float(row[4]),
            volume=float(row[5]),
        )
    except Exception:
        return None
