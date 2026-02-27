from fastapi.testclient import TestClient

from api.main import app, assistant_client, assistant_storage


def _assistant_observation_payload(session_id: str, text: str) -> dict[str, object]:
    return {
        "event_type": "observation.assistant.v1",
        "source": "assistant-web",
        "payload": {
            "domain": "assistant",
            "session_id": session_id,
            "text": text,
            "context": {"channel": "web", "user": "mello"},
            "tags": ["observation", "assistant"],
        },
    }


def test_observation_returns_reply_action(monkeypatch) -> None:
    assistant_storage.clear_all()

    def mock_reply(*args, **kwargs) -> str:
        _ = (args, kwargs)
        return "hello"

    monkeypatch.setattr(assistant_client, "generate_reply_sync", mock_reply)
    client = TestClient(app)

    response = client.post(
        "/events",
        json=_assistant_observation_payload("s-observation", "Olá, me ajude com um plano."),
    )
    assert response.status_code == 200
    body = response.json()

    assert body["action"]["type"] == "assistant.reply"
    assert body["action"]["text"] == "hello"
    assert "explain" in body["metadata"]
    assert body["metadata"]["explain"]["de"]["policy_profile"] in {"P0", "P1", "P2", "P3"}


def test_feedback_updates_policy(monkeypatch) -> None:
    assistant_storage.clear_all()

    def mock_reply(*args, **kwargs) -> str:
        _ = (args, kwargs)
        return "primeira resposta"

    monkeypatch.setattr(assistant_client, "generate_reply_sync", mock_reply)
    client = TestClient(app)

    response_observation = client.post(
        "/events",
        json=_assistant_observation_payload("s-feedback", "Quero ajuda para estudar Python."),
    )
    assert response_observation.status_code == 200

    policy_before = assistant_storage.get_policy_state()
    epsilon_before = float(policy_before["epsilon"])

    feedback_payload = {
        "event_type": "feedback.assistant.v1",
        "source": "assistant-web",
        "payload": {
            "domain": "assistant",
            "session_id": "s-feedback",
            "reward": 1.0,
            "tags": ["feedback", "assistant"],
            "notes": "gosto de respostas em tópicos",
        },
    }
    response_feedback = client.post("/events", json=feedback_payload)
    assert response_feedback.status_code == 200

    policy_after = assistant_storage.get_policy_state()
    metrics_after = assistant_storage.get_metrics()

    assert policy_after["feedback_count"] >= 1
    assert float(policy_after["epsilon"]) < epsilon_before
    assert metrics_after["count_feedbacks"] >= 1.0


def test_clear_memory_endpoint(monkeypatch) -> None:
    assistant_storage.clear_all()

    def mock_reply(*args, **kwargs) -> str:
        _ = (args, kwargs)
        return "memória temporária"

    monkeypatch.setattr(assistant_client, "generate_reply_sync", mock_reply)
    client = TestClient(app)

    response = client.post(
        "/events",
        json=_assistant_observation_payload(
            "s-clear", "Guarde minha preferência por respostas curtas."
        ),
    )
    assert response.status_code == 200

    assert assistant_storage.get_session_memory("s-clear")["last_messages"]
    clear_response = client.post("/agents/assistant/control/clear_memory")
    assert clear_response.status_code == 200

    memory_after = assistant_storage.get_session_memory("s-clear")
    policy_after = assistant_storage.get_policy_state()

    assert memory_after["last_messages"] == []
    assert float(policy_after["epsilon"]) == 0.6
