"""FastAPI UI server for Trader end-to-end observability (Sprint 3.5)."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections import defaultdict
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from trader_plugins.config import TraderConfig
from trader_plugins.events import EventEnvelope
from trader_plugins.runtime import TraderRuntime, _fetch_latest_binance_candle
from trader_plugins.types import Candle

UI_VERSION = "0.3.5"
ROOT = Path(__file__).resolve().parent
UI_DIR = ROOT / "ui"


_STAGE_ORDER = ["EPL", "ISI", "VEL", "SM", "DE", "AO", "AFS"]


def _event_stage(event_type: str) -> str:
    if event_type.startswith("market."):
        return "EPL"
    if event_type.startswith("state."):
        return "ISI"
    if event_type.startswith("metrics.ccif"):
        return "VEL"
    if event_type.startswith("metrics.") or event_type.startswith("guardrail."):
        return "SM"
    if event_type.startswith("decision."):
        return "DE"
    if event_type.startswith("execution."):
        return "AO"
    if event_type.startswith("learning.") or event_type.startswith("policy.") or event_type.startswith("value_policy."):
        return "AFS"
    return "AFS"


class EventHub:
    """WebSocket fanout hub with per-client subscriptions and ledger backfill."""

    def __init__(self, runtime: TraderRuntime) -> None:
        self.runtime = runtime
        self._clients: dict[WebSocket, dict[str, Any]] = {}

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self._clients[websocket] = {"filters": {}}

    def disconnect(self, websocket: WebSocket) -> None:
        self._clients.pop(websocket, None)

    async def on_client_message(self, websocket: WebSocket, message: dict[str, Any]) -> None:
        msg_type = str(message.get("type", "")).lower()
        if msg_type == "subscribe":
            filters = message.get("filters") if isinstance(message.get("filters"), dict) else {}
            self._clients.setdefault(websocket, {})["filters"] = filters
            await websocket.send_json({"type": "ack", "op": "subscribe", "filters": filters})
            return
        if msg_type == "backfill":
            limit = int(message.get("limit", 200))
            limit = max(1, min(limit, 5000))
            for item in self.runtime.ledger.tail(limit):
                if self._matches_filters(item, self._clients.get(websocket, {}).get("filters", {})):
                    await websocket.send_json({"type": "event", "envelope": item})
            await websocket.send_json({"type": "ack", "op": "backfill", "limit": limit})

    def _matches_filters(self, envelope: dict[str, Any], filters: dict[str, Any]) -> bool:
        evt = filters.get("type")
        sym = filters.get("symbol")
        cid = filters.get("correlation_id")
        payload = envelope.get("payload", {}) if isinstance(envelope.get("payload"), dict) else {}
        if evt and envelope.get("event_type") != evt:
            return False
        if sym and payload.get("symbol") != sym:
            return False
        if cid and envelope.get("correlation_id") != cid:
            return False
        return True

    async def broadcast(self, envelope: EventEnvelope | dict[str, Any]) -> None:
        data = envelope.to_dict() if isinstance(envelope, EventEnvelope) else envelope
        dead: list[WebSocket] = []
        for ws, meta in list(self._clients.items()):
            try:
                if self._matches_filters(data, meta.get("filters", {})):
                    await ws.send_json({"type": "event", "envelope": data})
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(ws)


class RuntimeController:
    """Owns runtime singleton + live/replay control loops."""

    def __init__(self, *, use_binance: bool, loop_interval_s: float) -> None:
        self.use_binance = use_binance
        self.loop_interval_s = loop_interval_s
        self.runtime: TraderRuntime | None = None
        self.event_hub: EventHub | None = None
        self.runtime_running = False
        self.decisions_paused = False
        self.mode = "idle"
        self._task: asyncio.Task[None] | None = None
        self._init_runtime()

    def _observer(self, envelope: EventEnvelope) -> None:
        if self.event_hub is None:
            return
        loop = asyncio.get_event_loop()
        loop.create_task(self.event_hub.broadcast(envelope))

    def _init_runtime(self) -> None:
        runtime = TraderRuntime(TraderConfig(), observer=self._observer)
        self.runtime = runtime
        self.event_hub = EventHub(runtime)

    async def start(self, payload: dict[str, Any]) -> None:
        if self.runtime_running:
            return
        self.mode = str(payload.get("mode", "live"))
        self.runtime_running = True
        interval = float(payload.get("interval_sec", self.loop_interval_s))
        symbols = payload.get("symbols")
        if isinstance(symbols, list) and symbols:
            self.runtime.config.symbols = [str(s).upper() for s in symbols]

        if self.mode == "replay":
            replay_csv = payload.get("replay_csv")
            if not replay_csv:
                raise HTTPException(status_code=400, detail="replay_csv is required for replay mode")
            self._task = asyncio.create_task(self._run_replay(Path(str(replay_csv)), interval))
        else:
            self._task = asyncio.create_task(self._run_live(interval))

    async def stop(self) -> None:
        self.runtime_running = False
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        self.mode = "idle"

    async def reset_demo(self) -> None:
        await self.stop()
        self._init_runtime()

    async def _run_replay(self, csv_path: Path, interval_sec: float) -> None:
        self.mode = "replay"
        with csv_path.open("r", encoding="utf-8") as handle:
            header = [x.strip() for x in handle.readline().strip().split(",")]
            for raw in handle:
                if not self.runtime_running:
                    break
                row = dict(zip(header, raw.strip().split(","), strict=False))
                if not row.get("symbol"):
                    continue
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
                self.runtime.on_candle(candle)
                await asyncio.sleep(max(interval_sec, 0.0))
        self.runtime_running = False
        self.mode = "idle"

    async def _run_live(self, interval_sec: float) -> None:
        self.mode = "live"
        while self.runtime_running:
            for symbol in self.runtime.config.symbols:
                for timeframe in [self.runtime.config.execution_timeframe, self.runtime.config.macro_timeframe]:
                    candle = self._load_candle(symbol, timeframe)
                    if candle is None:
                        continue
                    if self.decisions_paused and timeframe == self.runtime.config.execution_timeframe:
                        self.runtime.epl.ingest(candle)
                    else:
                        self.runtime.on_candle(candle)
            await asyncio.sleep(max(interval_sec, 0.1))

    def _load_candle(self, symbol: str, timeframe: str) -> Candle | None:
        if self.use_binance:
            candle = _fetch_latest_binance_candle(symbol, timeframe)
            if candle is not None:
                return candle
        market = self.runtime.state.get("market", {}).get(symbol, {}).get(timeframe, {})
        last_close = float(market.get("features", {}).get("last_close", 100.0))
        close = max(1.0, last_close * 1.0005)
        now = datetime.now(UTC)
        return Candle(symbol=symbol, timeframe=timeframe, timestamp=now, open=last_close, high=close * 1.001, low=close * 0.999, close=close, volume=1000.0)


def create_app(*, use_binance: bool | None = None, loop_interval_s: float = 2.0) -> FastAPI:
    controller = RuntimeController(use_binance=(os.getenv("TRADER_UI_DISABLE_BINANCE", "0") != "1") if use_binance is None else use_binance, loop_interval_s=loop_interval_s)

    app = FastAPI(title="PCE Observability Console", version=UI_VERSION)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
    app.state.controller = controller

    app.mount("/ui", StaticFiles(directory=UI_DIR), name="ui")

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(UI_DIR / "index.html")

    @app.on_event("shutdown")
    async def _shutdown_runtime() -> None:
        await controller.stop()

    @app.get("/api/health")
    async def api_health() -> dict[str, Any]:
        state = controller.runtime.state
        return {
            "status": "ok",
            "now": datetime.now(UTC).isoformat(),
            "runtime_running": controller.runtime_running,
            "ledger_ok": controller.runtime.ledger.path.exists() or True,
            "db_ok": True,
            "ui_version": UI_VERSION,
            "active_model_version": state.get("models", {}).get("active_model_version") or state.get("models", {}).get("active"),
            "policy_version": state.get("policy", {}).get("policy_version"),
            "value_policy_version": state.get("value_policy", {}).get("value_policy_version"),
        }

    @app.get("/api/ledger/tail")
    async def api_ledger_tail(limit: int = Query(default=500, ge=1, le=5000)) -> list[dict[str, Any]]:
        return controller.runtime.ledger.tail(limit)

    @app.get("/api/ledger/query")
    async def api_ledger_query(
        type: str | None = None,
        symbol: str | None = None,
        correlation_id: str | None = None,
        since: str | None = None,
        limit: int = Query(default=200, ge=1, le=5000),
    ) -> list[dict[str, Any]]:
        events = controller.runtime.ledger.query(event_type=type, symbol=symbol, since_ts=since, limit=None)
        if correlation_id:
            events = [e for e in events if e.get("correlation_id") == correlation_id]
        return events[-limit:]

    @app.get("/api/trace/{correlation_id}")
    async def api_trace(correlation_id: str) -> dict[str, Any]:
        events = controller.runtime.ledger.query(limit=None)
        chain = [e for e in events if e.get("correlation_id") == correlation_id]
        chain.sort(key=lambda x: (str(x.get("ts", "")), str(x.get("event_id", ""))))
        if not chain:
            raise HTTPException(status_code=404, detail="correlation_id not found")

        grouped: dict[str, list[dict[str, Any]]] = {stage: [] for stage in _STAGE_ORDER}
        for e in chain:
            grouped[_event_stage(str(e.get("event_type", "")))].append(e)

        durations: dict[str, float] = {}
        for stage in _STAGE_ORDER:
            items = grouped[stage]
            if len(items) >= 2:
                t0 = datetime.fromisoformat(str(items[0]["ts"]))
                t1 = datetime.fromisoformat(str(items[-1]["ts"]))
                durations[stage] = (t1 - t0).total_seconds()
            elif items:
                durations[stage] = 0.0

        versions = {
            "model_version": controller.runtime.state.get("models", {}).get("active_model_version") or controller.runtime.state.get("models", {}).get("active"),
            "policy_version": controller.runtime.state.get("policy", {}).get("policy_version"),
            "value_policy_version": controller.runtime.state.get("value_policy", {}).get("value_policy_version"),
            "feature_version": controller.runtime.config.feature_version,
            "label_version": controller.runtime.config.label_version,
        }
        return {
            "correlation_id": correlation_id,
            "events": chain,
            "stages": {
                "EPL events": grouped["EPL"],
                "ISI events": grouped["ISI"],
                "VEL events": grouped["VEL"],
                "SM events": grouped["SM"],
                "DE events": grouped["DE"],
                "AO events": grouped["AO"],
                "AFS events": grouped["AFS"],
            },
            "durations_by_stage_sec": durations,
            "causality_chain": [
                {"event_id": e.get("event_id"), "causation_id": e.get("causation_id"), "event_type": e.get("event_type")} for e in chain
            ],
            "versions": versions,
        }

    @app.get("/api/state")
    async def api_state() -> dict[str, Any]:
        st = controller.runtime.state
        return {
            "market_state": st.get("market", {}),
            "portfolio_state": st.get("portfolio", {}),
            "guardrails": {
                "dd_day": st.get("dd_day", 0.0),
                "dd_month": st.get("dd_month", 0.0),
                "trades_total_day": st.get("limits", {}).get("trades_total_day", 0),
                "by_asset": st.get("limits", {}).get("trades_by_asset_day", {}),
                "locked": str(st.get("metrics", {}).get("mode", "")) == "locked",
                "lock_reason": "data_lock" if str(st.get("metrics", {}).get("mode", "")) == "locked" else None,
            },
            "metrics": st.get("metrics", {}),
            "registry": controller.runtime.storage.load_model_registry(),
            "last_prices_by_symbol": st.get("prices", {}),
            "model_info": st.get("models", {}),
        }

    @app.get("/api/decisions")
    async def api_decisions(limit: int = Query(default=200, ge=1, le=2000)) -> list[dict[str, Any]]:
        rows = controller.runtime.ledger.query(event_type="decision.trade_plan.created", limit=limit)
        out: list[dict[str, Any]] = []
        for e in reversed(rows):
            plan = e.get("payload", {}).get("plan", {})
            out.append(
                {
                    "ts": e.get("ts"),
                    "symbol": e.get("payload", {}).get("symbol"),
                    "action": plan.get("action"),
                    "qty": plan.get("qty"),
                    "p_win": plan.get("p_win"),
                    "uncertainty": plan.get("uncertainty"),
                    "threshold": plan.get("threshold"),
                    "mode": plan.get("mode"),
                    "cci_f": controller.runtime.state.get("metrics", {}).get("cci_f"),
                    "model_version": controller.runtime.state.get("models", {}).get("active_model_version"),
                    "decision_id": plan.get("decision_id"),
                    "correlation_id": e.get("correlation_id"),
                    "gate_results": plan.get("gate_results", []),
                    "alternatives": plan.get("alternatives", []),
                    "explanation": plan.get("reason"),
                }
            )
        return out

    @app.get("/api/executions")
    async def api_executions(limit: int = Query(default=200, ge=1, le=2000)) -> list[dict[str, Any]]:
        rows = controller.runtime.ledger.query(event_type="execution.order.filled", limit=limit)
        return list(reversed(rows))

    @app.get("/api/models")
    async def api_models() -> dict[str, Any]:
        return {
            "active_model": controller.runtime.state.get("models", {}).get("active_model_version") or controller.runtime.state.get("models", {}).get("active"),
            "registry": controller.runtime.storage.load_model_registry(),
            "mock": False,
        }

    @app.get("/api/policies")
    async def api_policies() -> dict[str, Any]:
        return {
            "policy": controller.runtime.state.get("policy", {}),
            "value_policy": controller.runtime.state.get("value_policy", {}),
            "history": {"mock": True, "note": "MOCK: versioned history pending"},
        }

    @app.post("/api/control/start")
    async def api_control_start(payload: dict[str, Any]) -> dict[str, Any]:
        await controller.start(payload)
        return {"ok": True, "runtime_running": controller.runtime_running, "mode": controller.mode}

    @app.post("/api/control/stop")
    async def api_control_stop() -> dict[str, Any]:
        await controller.stop()
        return {"ok": True, "runtime_running": controller.runtime_running}

    @app.post("/api/control/pause_decisions")
    async def api_pause_decisions() -> dict[str, Any]:
        controller.decisions_paused = True
        return {"ok": True, "paused": True}

    @app.post("/api/control/resume_decisions")
    async def api_resume_decisions() -> dict[str, Any]:
        controller.decisions_paused = False
        return {"ok": True, "paused": False}

    @app.post("/api/control/reset_demo")
    async def api_reset(payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("confirm") is not True:
            raise HTTPException(status_code=400, detail="confirm=true required")
        await controller.reset_demo()
        return {"ok": True}

    @app.post("/api/control/train")
    async def api_control_train(payload: dict[str, Any]) -> dict[str, Any]:
        mode = str(payload.get("mode", "dataset"))
        dataset = payload.get("dataset_path") or payload.get("candles_csv") or "agents/trader/data/sample_features.csv"
        if mode not in {"dataset", "candles"}:
            raise HTTPException(status_code=400, detail="invalid mode")
        result = controller.runtime.train_from_csv(Path(str(dataset)))
        return {"ok": True, "mode": mode, "result": result}

    @app.post("/api/control/set_policy")
    async def api_set_policy(payload: dict[str, Any]) -> dict[str, Any]:
        policy = controller.runtime.state.setdefault("policy", {})
        if "p_win_threshold" in payload:
            v = float(payload["p_win_threshold"])
            if not (0.0 <= v <= 1.0):
                raise HTTPException(status_code=400, detail="p_win_threshold out of range")
            controller.runtime.config.p_win_threshold = v
            policy["dynamic_threshold"] = v
        if "risk_per_trade" in payload:
            v = float(payload["risk_per_trade"])
            if not (0.0 <= v <= 0.2):
                raise HTTPException(status_code=400, detail="risk_per_trade out of range")
            policy["risk_per_trade"] = v
        if "max_trades_per_day" in payload:
            v = int(payload["max_trades_per_day"])
            if not (1 <= v <= 1000):
                raise HTTPException(status_code=400, detail="max_trades_per_day out of range")
            controller.runtime.config.risk.max_trades_per_day = v
        policy["policy_version"] = f"policy-ui-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        controller.runtime._emit(event_type="policy.updated", source="trader/ui", actor="trader/ui", correlation_id=f"policy-{datetime.now(UTC).timestamp()}", payload={"policy": policy})
        return {"ok": True, "policy": policy}

    @app.post("/api/control/set_value_policy")
    async def api_set_value_policy(payload: dict[str, Any]) -> dict[str, Any]:
        vp = controller.runtime.state.setdefault("value_policy", {})
        for k, v in payload.items():
            if isinstance(v, (int, float)):
                if not (-10.0 <= float(v) <= 10.0):
                    raise HTTPException(status_code=400, detail=f"{k} out of range")
                vp[k] = float(v)
            else:
                vp[k] = v
        vp["value_policy_version"] = f"value-ui-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        controller.runtime._emit(event_type="value_policy.updated", source="trader/ui", actor="trader/ui", correlation_id=f"value-policy-{datetime.now(UTC).timestamp()}", payload={"value_policy": vp})
        return {"ok": True, "value_policy": vp}

    @app.websocket("/ws/events")
    async def ws_events(websocket: WebSocket) -> None:
        await controller.event_hub.connect(websocket)
        try:
            await websocket.send_json({"type": "hello", "ui_version": UI_VERSION})
            while True:
                data = await websocket.receive_json()
                if isinstance(data, dict):
                    await controller.event_hub.on_client_message(websocket, data)
        except WebSocketDisconnect:
            controller.event_hub.disconnect(websocket)

    @app.get("/api/download/ledger_tail")
    async def api_download_ledger_tail(limit: int = Query(default=2000, ge=1, le=10000)) -> JSONResponse:
        return JSONResponse(content=controller.runtime.ledger.tail(limit))

    return app


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Trader UI server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8787)
    parser.add_argument("--loop-interval", type=float, default=2.0)
    args = parser.parse_args()

    import uvicorn

    uvicorn.run(create_app(loop_interval_s=args.loop_interval), host=args.host, port=args.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
