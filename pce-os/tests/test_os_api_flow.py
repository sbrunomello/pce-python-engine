import pce_api.main as api_main
from fastapi.testclient import TestClient
from pce.sm.manager import StateManager


def test_purchase_request_approve_with_budget_updates_twin(tmp_path) -> None:
    db = tmp_path / "state.db"
    state_manager = StateManager(f"sqlite:///{db}")
    state_manager.save_state({})

    app = api_main.build_app(state_manager=state_manager)
    client = TestClient(app)

    budget_response = client.post(
        "/events",
        json={
            "event_type": "budget.updated",
            "source": "os-test",
            "payload": {
                "domain": "os.robotics",
                "tags": ["budget"],
                "budget_total": 500.0,
                "budget_remaining": 500.0,
            },
        },
    )
    assert budget_response.status_code == 200

    response = client.post(
        "/events",
        json={
            "event_type": "purchase.requested",
            "source": "os-test",
            "payload": {
                "domain": "os.robotics",
                "tags": ["purchase"],
                "projected_cost": 123.0,
                "risk_level": "MEDIUM",
            },
        },
    )
    assert response.status_code == 200
    pending = client.get("/os/approvals").json()["pending"]
    assert len(pending) == 1

    approval_id = pending[0]["approval_id"]
    approve = client.post(
        f"/os/approvals/{approval_id}/approve",
        json={"actor": "tester", "notes": "approved"},
    )
    assert approve.status_code == 200
    assert approve.json()["action_type"] == "os.record_purchase"
    assert client.get("/os/approvals").json()["pending"] == []

    twin_after = client.get("/os/robotics/state").json()["robotics_twin"]
    assert twin_after["budget_remaining"] == 377.0
    assert twin_after["purchase_history"][0]["approval_id"] == approval_id


def test_purchase_request_approve_without_budget_returns_conflict(tmp_path) -> None:
    db = tmp_path / "state.db"
    state_manager = StateManager(f"sqlite:///{db}")
    state_manager.save_state({})

    app = api_main.build_app(state_manager=state_manager)
    client = TestClient(app)

    response = client.post(
        "/events",
        json={
            "event_type": "purchase.requested",
            "source": "os-test",
            "payload": {
                "domain": "os.robotics",
                "tags": ["purchase"],
                "projected_cost": 123.0,
                "risk_level": "MEDIUM",
            },
        },
    )
    assert response.status_code == 200
    approval_id = client.get("/os/approvals").json()["pending"][0]["approval_id"]

    approve = client.post(
        f"/os/approvals/{approval_id}/approve",
        json={"actor": "tester", "notes": "approved"},
    )
    assert approve.status_code == 409
    assert approve.json()["detail"] == "insufficient_budget_for_purchase"

    assert client.get("/os/approvals").json()["pending"] == []
    twin_after = client.get("/os/robotics/state").json()["robotics_twin"]
    assert twin_after["budget_remaining"] == 0.0
    assert twin_after["purchase_history"] == []
