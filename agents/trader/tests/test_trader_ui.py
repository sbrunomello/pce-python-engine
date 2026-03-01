"""API and websocket smoke tests for the Trader UI server."""

from __future__ import annotations

from fastapi.testclient import TestClient

from agents.trader.ui_server import create_app


def test_health_and_state_schema() -> None:
    app = create_app(use_binance=False, loop_interval_s=0.1)
    client = TestClient(app)

    health = client.get("/api/health")
    assert health.status_code == 200
    payload = health.json()
    assert payload["status"] == "ok"
    assert "runtime_running" in payload

    state = client.get("/api/state")
    assert state.status_code == 200
    snapshot = state.json()
    assert "market_state" in snapshot
    assert "portfolio_state" in snapshot
    assert "metrics" in snapshot


def test_control_start_stop_and_runtime_running_flag() -> None:
    app = create_app(use_binance=False, loop_interval_s=0.1)
    client = TestClient(app)

    start = client.post("/api/control/start")
    assert start.status_code == 200
    assert start.json()["runtime_running"] is True

    health_running = client.get("/api/health").json()
    assert health_running["runtime_running"] is True

    stop = client.post("/api/control/stop")
    assert stop.status_code == 200
    assert stop.json()["runtime_running"] is False


def test_websocket_receives_runtime_event_after_start() -> None:
    app = create_app(use_binance=False, loop_interval_s=0.05)
    client = TestClient(app)

    start = client.post("/api/control/start")
    assert start.status_code == 200

    with client.websocket_connect("/ws/events") as ws:
        connected = ws.receive_json()
        assert connected["type"] == "log"

        metrics = ws.receive_json()
        assert metrics["type"] == "metrics"

    client.post("/api/control/stop")
