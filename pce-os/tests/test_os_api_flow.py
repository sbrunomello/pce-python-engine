from api.main import app, sm
from fastapi.testclient import TestClient


def test_purchase_request_requires_approval_then_approve_transitions() -> None:
    sm.save_state({})
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
