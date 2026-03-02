"""API and websocket tests for Trader UI server contracts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from agents.trader.ui_server import create_app


def _seed_replay_csv(tmp_path):
    csv_path = tmp_path / "candles.csv"
    start = datetime(2026, 1, 1, tzinfo=UTC)
    lines = ["symbol,timeframe,timestamp,open,high,low,close,volume"]
    for i in range(4):
        lines.append(f"BTCUSDT,4h,{(start + timedelta(hours=4*i)).isoformat()},100,101,99,{100+i},100")
    for i in range(8):
        lines.append(f"BTCUSDT,1h,{(start + timedelta(hours=i)).isoformat()},100,101,99,{100+i*0.2},100")
    csv_path.write_text("\n".join(lines), encoding="utf-8")
    return csv_path


def test_ui_health() -> None:
    app = create_app(use_binance=False, loop_interval_s=0.05)
    client = TestClient(app)
    resp = client.get("/api/health")
    assert resp.status_code == 200
    payload = resp.json()
    for key in ["status", "now", "runtime_running", "ledger_ok", "db_ok", "ui_version", "active_model_version", "policy_version", "value_policy_version"]:
        assert key in payload


def test_ws_backfill() -> None:
    app = create_app(use_binance=False, loop_interval_s=0.01)
    client = TestClient(app)

    client.post("/api/control/start", json={"mode": "live", "interval_sec": 0.01})
    with client.websocket_connect("/ws/events") as ws:
        hello = ws.receive_json()
        assert hello["type"] == "hello"
        ws.send_json({"type": "backfill", "limit": 10})
        got_event = False
        for _ in range(30):
            msg = ws.receive_json()
            if msg.get("type") == "event":
                got_event = True
                break
        assert got_event is True
    client.post("/api/control/stop")


def test_trace_endpoint(tmp_path) -> None:
    app = create_app(use_binance=False, loop_interval_s=0.01)
    client = TestClient(app)
    csv_path = _seed_replay_csv(tmp_path)

    start = client.post("/api/control/start", json={"mode": "replay", "replay_csv": str(csv_path), "interval_sec": 0.0})
    assert start.status_code == 200

    # replay runs quickly; grab latest decision correlation
    decisions = client.get("/api/decisions?limit=20").json()
    assert decisions
    cid = decisions[0]["correlation_id"]

    trace = client.get(f"/api/trace/{cid}")
    assert trace.status_code == 200
    body = trace.json()
    assert "stages" in body
    assert "EPL events" in body["stages"]
    assert "DE events" in body["stages"]
    assert "AO events" in body["stages"]


def test_control_replay(tmp_path) -> None:
    app = create_app(use_binance=False, loop_interval_s=0.01)
    client = TestClient(app)
    csv_path = _seed_replay_csv(tmp_path)

    started = client.post("/api/control/start", json={"mode": "replay", "replay_csv": str(csv_path), "interval_sec": 0.01})
    assert started.status_code == 200
    assert started.json()["runtime_running"] is True

    stopped = client.post("/api/control/stop")
    assert stopped.status_code == 200
    assert stopped.json()["runtime_running"] is False
