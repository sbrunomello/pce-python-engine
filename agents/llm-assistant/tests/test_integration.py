from fastapi.testclient import TestClient

from api.main import app


def test_api_event_flow() -> None:
    client = TestClient(app)
    payload = {
        "event_type": "cashflow.update",
        "source": "finance-agent",
        "payload": {
            "domain": "finance",
            "tags": ["safe", "strategic", "efficient", "budget-aware"],
        },
    }
    response = client.post("/events", json=payload)
    assert response.status_code == 200
    body = response.json()
    assert "cci" in body
    assert "cci_components" in body

    cci_response = client.get("/cci")
    assert cci_response.status_code == 200

    state_response = client.get("/state")
    assert state_response.status_code == 200
    assert "state" in state_response.json()

    history_response = client.get("/cci/history")
    assert history_response.status_code == 200
    assert isinstance(history_response.json()["history"], list)
