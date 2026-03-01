"""FastAPI UI server for the Trader runtime.

This module intentionally stays self-contained inside ``agents/trader`` so the
web UI can run independently from pce-os.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from trader_plugins.config import TraderConfig
from trader_plugins.runtime import TraderRuntime, _fetch_latest_binance_candle
from trader_plugins.types import Candle

UI_VERSION = "0.1.0"
ROOT = Path(__file__).resolve().parent
UI_DIR = ROOT / "ui"
ARTIFACTS_DIR = ROOT / "artifacts"
LOGS_PATH = ARTIFACTS_DIR / "logs" / "decisions.jsonl"
UI_CACHE_PATH = ARTIFACTS_DIR / "ui_cache.json"


class EventHub:
    """Track connected websocket clients and broadcast JSON events."""

    def __init__(self) -> None:
        self._clients: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._clients.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        self._clients.discard(websocket)

    async def emit(self, event_type: str, payload: dict[str, Any]) -> None:
        message = {"type": event_type, "payload": payload, "ts": datetime.now(UTC).isoformat()}
        dead: list[WebSocket] = []
        for client in self._clients:
            try:
                await client.send_json(message)
            except Exception:
                dead.append(client)
        for ws in dead:
            self._clients.discard(ws)


class RuntimeController:
    """Holds runtime state and control-loop semantics for UI endpoints."""

    def __init__(self, runtime: TraderRuntime, *, use_binance: bool, loop_interval_s: float) -> None:
        self.runtime = runtime
        self.use_binance = use_binance
        self.loop_interval_s = loop_interval_s
        self.runtime_running = False
        self.decisions_paused = False
        self._task: asyncio.Task[None] | None = None
        self.event_hub = EventHub()
        self.policy_version = 1
        self.train_runs: dict[str, dict[str, Any]] = {}

    async def start(self) -> None:
        if self.runtime_running:
            return
        self.runtime_running = True
        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        self.runtime_running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    def pause(self) -> None:
        self.decisions_paused = True

    def resume(self) -> None:
        self.decisions_paused = False

    async def reset(self) -> None:
        await self.stop()
        self.runtime = TraderRuntime(self.runtime.config)
        self.policy_version = 1
        self._save_ui_cache({"last_reset": datetime.now(UTC).isoformat()})

    async def _run_loop(self) -> None:
        while self.runtime_running:
            try:
                await self._tick_once()
            except Exception as exc:  # noqa: BLE001
                await self.event_hub.emit("log", {"level": "error", "message": f"loop error: {exc}"})
            await asyncio.sleep(self.loop_interval_s)

    async def _tick_once(self) -> None:
        symbols = list(self.runtime.config.symbols)
        timeframes = [self.runtime.config.execution_timeframe, self.runtime.config.macro_timeframe]
        for symbol in symbols:
            for timeframe in timeframes:
                candle = self._load_candle(symbol, timeframe)
                if candle is None:
                    continue
                if self.decisions_paused and timeframe == self.runtime.config.execution_timeframe:
                    event = self.runtime.epl.ingest(candle)
                    integrated = self.runtime.isi.integrate(event)
                    self.runtime.state.setdefault("market", {}).setdefault(symbol, {})[timeframe] = integrated
                    self.runtime.storage.save_runtime_state(self.runtime.state)
                else:
                    decision = self.runtime.on_candle(candle)
                    if decision:
                        await self.event_hub.emit("decision", decision)
                        await self.event_hub.emit("execution", decision.get("execution", {}))
                market = self.runtime.state.get("market", {}).get(symbol, {}).get(timeframe, {})
                await self.event_hub.emit("candle", {"symbol": symbol, "timeframe": timeframe, "market": market})

        await self.event_hub.emit("metrics", self.runtime.state.get("metrics", {}))

    def _load_candle(self, symbol: str, timeframe: str) -> Candle | None:
        if self.use_binance:
            candle = _fetch_latest_binance_candle(symbol, timeframe)
            if candle is not None:
                return candle
        # Offline fallback: deterministic pseudo-candle from current state.
        market = self.runtime.state.get("market", {}).get(symbol, {}).get(timeframe, {})
        last_close = float(market.get("features", {}).get("last_close", 100.0))
        close = max(1.0, last_close * 1.0005)
        now = datetime.now(UTC)
        return Candle(
            symbol=symbol,
            timeframe=timeframe,
            timestamp=now,
            open=last_close,
            high=close * 1.001,
            low=close * 0.999,
            close=close,
            volume=1000.0,
        )

    def _save_ui_cache(self, payload: dict[str, Any]) -> None:
        UI_CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
        UI_CACHE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def create_app(*, use_binance: bool | None = None, loop_interval_s: float = 5.0) -> FastAPI:
    config = TraderConfig()
    runtime = TraderRuntime(config)
    controller = RuntimeController(
        runtime,
        use_binance=(os.getenv("TRADER_UI_DISABLE_BINANCE", "0") != "1") if use_binance is None else use_binance,
        loop_interval_s=loop_interval_s,
    )

    app = FastAPI(title="Trader UI Server", version=UI_VERSION)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.state.controller = controller

    UI_DIR.mkdir(parents=True, exist_ok=True)
    app.mount("/ui", StaticFiles(directory=UI_DIR), name="ui")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(UI_DIR / "index.html")

    @app.on_event("shutdown")
    async def _shutdown_runtime() -> None:
        # Ensure control loop tasks are always cancelled on app shutdown/tests.
        await controller.stop()


    @app.get("/api/health")
    async def api_health() -> dict[str, Any]:
        return {
            "status": "ok",
            "time": datetime.now(UTC).isoformat(),
            "runtime_running": controller.runtime_running,
            "db_ok": True,
            "model_active": bool(controller.runtime.state.get("models", {}).get("active")),
            "ui_version": UI_VERSION,
        }

    @app.get("/api/state")
    async def api_state() -> dict[str, Any]:
        state = controller.runtime.state
        data_quality = {
            "integrity_ok": True,
            "issues": [],
        }
        market_state = state.get("market", {})
        for symbol in market_state.values():
            if isinstance(symbol, dict):
                for tf_data in symbol.values():
                    if isinstance(tf_data, dict):
                        feats = tf_data.get("features", {})
                        if isinstance(feats, dict) and not bool(feats.get("integrity_ok", True)):
                            data_quality["integrity_ok"] = False
                            data_quality["issues"].append({"message": "integrity flag false", "ts": datetime.now(UTC).isoformat()})
        return {
            "market_state": market_state,
            "portfolio_state": state.get("portfolio", {}),
            "limits": state.get("limits", {}),
            "metrics": state.get("metrics", {}),
            "data_quality": data_quality,
            "policy_version": controller.policy_version,
        }

    @app.get("/api/decisions")
    async def api_decisions(limit: int = Query(default=200, ge=1, le=1000)) -> list[dict[str, Any]]:
        return _read_decisions(limit)

    @app.get("/api/trades")
    async def api_trades(limit: int = Query(default=200, ge=1, le=1000)) -> list[dict[str, Any]]:
        trades: list[dict[str, Any]] = []
        for item in _read_decisions(limit):
            execution = item.get("execution", {})
            if execution.get("event_type") == "execution.fill" or execution.get("side"):
                trades.append(
                    {
                        "trade_id": execution.get("fill_id", item.get("decision_id")),
                        "decision_id": item.get("decision_id"),
                        "timestamp": execution.get("timestamp", item.get("timestamp")),
                        "symbol": item.get("symbol"),
                        "side": execution.get("side", "unknown"),
                        "qty": execution.get("qty", 0),
                        "price": execution.get("price", 0),
                        "pnl": execution.get("realized_pnl", 0.0),
                    }
                )
        return trades

    @app.get("/api/portfolio")
    async def api_portfolio() -> dict[str, Any]:
        portfolio = controller.runtime.state.get("portfolio", {})
        positions = portfolio.get("positions", {})
        exposure = {
            symbol: float(pos.get("qty", 0.0)) * float(pos.get("avg_price", 0.0))
            for symbol, pos in positions.items()
            if isinstance(pos, dict)
        }
        equity_curve = _load_mock_equity_curve(float(portfolio.get("equity", 100000.0)))
        return {
            "positions": positions,
            "exposure_by_symbol": exposure,
            "equity_curve": equity_curve,
            "mock": True,
        }

    @app.get("/api/models")
    async def api_models() -> dict[str, Any]:
        state = controller.runtime.state
        registry = controller.runtime.storage.load_model_registry()
        return {
            "active_model_version": state.get("models", {}).get("active"),
            "model_registry": registry,
            "last_train_run": _last_train_run(controller.train_runs),
        }

    @app.post("/api/train")
    async def api_train(payload: dict[str, Any], background_tasks: BackgroundTasks) -> dict[str, Any]:
        mode = payload.get("mode", "from_features")
        if mode not in {"from_features", "from_candles"}:
            raise HTTPException(status_code=400, detail="invalid mode")
        run_id = f"train-{uuid.uuid4().hex[:12]}"
        controller.train_runs[run_id] = {
            "state": "queued",
            "metrics": {},
            "logs": ["queued"],
            "started_at": datetime.now(UTC).isoformat(),
            "mock": mode == "from_candles",
        }

        async def _train_task() -> None:
            run = controller.train_runs[run_id]
            run["state"] = "running"
            run["logs"].append("running")
            try:
                csv_path = payload.get("csv_path") or "agents/trader/data/sample_features.csv"
                result = controller.runtime.train_from_csv(Path(csv_path))
                run["state"] = "done"
                run["metrics"] = result
                run["logs"].append("done")
            except Exception as exc:  # noqa: BLE001
                run["state"] = "error"
                run["logs"].append(str(exc))

        background_tasks.add_task(_train_task)
        return {"accepted": True, "run_id": run_id}

    @app.get("/api/train/status")
    async def api_train_status(run_id: str) -> dict[str, Any]:
        run = controller.train_runs.get(run_id)
        if not run:
            raise HTTPException(status_code=404, detail="run_id not found")
        return run

    @app.post("/api/control/start")
    async def api_control_start() -> dict[str, Any]:
        await controller.start()
        return {"ok": True, "runtime_running": controller.runtime_running}

    @app.post("/api/control/stop")
    async def api_control_stop() -> dict[str, Any]:
        await controller.stop()
        return {"ok": True, "runtime_running": controller.runtime_running}

    @app.post("/api/control/pause")
    async def api_control_pause() -> dict[str, Any]:
        controller.pause()
        return {"ok": True, "paused": True}

    @app.post("/api/control/resume")
    async def api_control_resume() -> dict[str, Any]:
        controller.resume()
        return {"ok": True, "paused": False}

    @app.post("/api/control/reset")
    async def api_control_reset(payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("confirm") is not True:
            raise HTTPException(status_code=400, detail="confirm=true required")
        await controller.reset()
        return {"ok": True, "runtime_running": controller.runtime_running}

    @app.post("/api/control/config")
    async def api_control_config(payload: dict[str, Any]) -> dict[str, Any]:
        threshold = payload.get("threshold")
        if threshold is not None:
            threshold = float(threshold)
            if threshold < 0.50 or threshold > 0.80:
                raise HTTPException(status_code=400, detail="threshold out of range")
            controller.runtime.config.p_win_threshold = threshold

        symbols = payload.get("symbols")
        if symbols is not None:
            if not isinstance(symbols, list) or not symbols or len(symbols) > 20:
                raise HTTPException(status_code=400, detail="invalid symbols")
            controller.runtime.config.symbols = [str(s).upper() for s in symbols]

        for key in ("fee_bps", "slippage_bps"):
            if key in payload:
                value = float(payload[key])
                if value < 0 or value > 100:
                    raise HTTPException(status_code=400, detail=f"{key} out of range")
                setattr(controller.runtime.config, key, value)

        risk_limits = payload.get("risk_limits")
        if isinstance(risk_limits, dict):
            for r_key in ("max_trades_per_day", "max_trades_per_asset_day"):
                if r_key in risk_limits:
                    val = int(risk_limits[r_key])
                    if val < 1 or val > 100:
                        raise HTTPException(status_code=400, detail=f"{r_key} out of range")
                    setattr(controller.runtime.config.risk, r_key, val)

        controller.policy_version += 1
        controller.runtime.state["policy_version"] = controller.policy_version
        controller.runtime.storage.save_runtime_state(controller.runtime.state)
        return {"ok": True, "policy_version": controller.policy_version}

    @app.websocket("/ws/events")
    async def ws_events(websocket: WebSocket) -> None:
        await controller.event_hub.connect(websocket)
        try:
            await websocket.send_json({"type": "log", "payload": {"message": "connected"}, "ts": datetime.now(UTC).isoformat()})
            await websocket.send_json({"type": "metrics", "payload": controller.runtime.state.get("metrics", {}), "ts": datetime.now(UTC).isoformat()})
            while True:
                # Keep the socket alive. Client messages are ignored in v0.
                await websocket.receive_text()
        except WebSocketDisconnect:
            controller.event_hub.disconnect(websocket)

    @app.get("/api/download/decisions")
    async def download_decisions() -> JSONResponse:
        return JSONResponse(content=_read_decisions(limit=2000))

    @app.get("/api/download/state")
    async def download_state() -> JSONResponse:
        return JSONResponse(content=controller.runtime.state)

    return app


def _read_decisions(limit: int) -> list[dict[str, Any]]:
    if not LOGS_PATH.exists():
        return []
    lines = LOGS_PATH.read_text(encoding="utf-8").splitlines()[-limit:]
    items: list[dict[str, Any]] = []
    for line in reversed(lines):
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        plan = row.get("plan", {}) if isinstance(row.get("plan"), dict) else {}
        explanation = row.get("explanation", {}) if isinstance(row.get("explanation"), dict) else {}
        items.append(
            {
                "decision_id": row.get("decision_id"),
                "timestamp": plan.get("timestamp", row.get("ts")),
                "symbol": row.get("symbol"),
                "p_win": plan.get("model_out", {}).get("p_win"),
                "uncertainty": plan.get("model_out", {}).get("uncertainty"),
                "threshold": plan.get("threshold"),
                "mode": plan.get("mode"),
                "gate_results": plan.get("gate_results"),
                "action": plan.get("action"),
                "qty": plan.get("qty"),
                "explanation": explanation,
                "execution": row.get("execution", {}),
                "raw": row,
            }
        )
    return items


def _load_mock_equity_curve(latest: float) -> list[dict[str, Any]]:
    now = datetime.now(UTC)
    curve = []
    for idx in range(20):
        curve.append(
            {
                "ts": (now).isoformat(),
                "equity": latest * (0.99 + (idx / 1000.0)),
                "mock": True,
            }
        )
    return curve


def _last_train_run(runs: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if not runs:
        return {"mock": True, "state": "none", "logs": ["no training run yet"]}
    run_id = sorted(runs.keys())[-1]
    return {"run_id": run_id, **runs[run_id]}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Trader UI server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--loop-interval", type=float, default=5.0)
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(create_app(loop_interval_s=args.loop_interval), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
