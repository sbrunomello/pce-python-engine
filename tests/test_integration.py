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
    assert "cci" in response.json()

    cci_response = client.get("/cci")
    assert cci_response.status_code == 200
