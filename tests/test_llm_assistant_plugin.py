from fastapi.testclient import TestClient

from api.main import app, assistant_client, assistant_storage, assistant_value_model


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
    assert body["metadata"]["explain"]["de"]["final_profile"]["profile_id"] in {
        "P0",
        "P1",
        "P2",
        "P3",
    }


def test_override_deterministico(monkeypatch) -> None:
    assistant_storage.clear_all()

    def mock_reply(*args, **kwargs) -> str:
        _ = (args, kwargs)
        return "resposta segura"

    monkeypatch.setattr(assistant_client, "generate_reply_sync", mock_reply)
    monkeypatch.setattr(assistant_value_model, "evaluate", lambda event, state: 0.4)
    monkeypatch.setattr(
        assistant_value_model,
        "components",
        lambda event, state: {"relevance": 0.4, "safety": 0.9, "clarity": 0.9},
    )
    client = TestClient(app)

    response = client.post(
        "/events",
        json=_assistant_observation_payload("s-override", "Me dê uma sugestão arriscada."),
    )
    assert response.status_code == 200
    explain_de = response.json()["metadata"]["explain"]["de"]

    assert explain_de["override_reason"] is not None
    assert explain_de["final_profile"]["profile_id"] == "P0"
    assert float(explain_de["final_decoding"]["temperature"]) <= 0.3


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


def test_feedback_negativo_salva_avoid_e_entra_no_prompt(monkeypatch) -> None:
    assistant_storage.clear_all()
    captured_messages: list[list[dict[str, str]]] = []

    def mock_reply(messages, **kwargs) -> str:
        _ = kwargs
        captured_messages.append(messages)
        return "ok"

    monkeypatch.setattr(assistant_client, "generate_reply_sync", mock_reply)
    client = TestClient(app)

    first_obs = client.post(
        "/events",
        json=_assistant_observation_payload("s-avoid", "me ajude com escrita"),
    )
    assert first_obs.status_code == 200

    feedback_payload = {
        "event_type": "feedback.assistant.v1",
        "source": "assistant-web",
        "payload": {
            "domain": "assistant",
            "session_id": "s-avoid",
            "reward": -1.0,
            "tags": ["feedback", "assistant"],
            "notes": "não seja prolixo",
        },
    }
    feedback_response = client.post("/events", json=feedback_payload)
    assert feedback_response.status_code == 200

    second_obs = client.post(
        "/events",
        json=_assistant_observation_payload("s-avoid", "agora explique de novo"),
    )
    assert second_obs.status_code == 200

    latest_messages = captured_messages[-1]
    system_prompt = latest_messages[0]["content"]
    assert "Evitar:" in system_prompt
    assert "não seja prolixo" in system_prompt

    memory_used = second_obs.json()["metadata"]["explain"]["isi"]["memory_used"]
    assert memory_used["avoid_count"] > 0


def test_pending_delete_seguro_por_sessao() -> None:
    assistant_storage.clear_all()

    assistant_storage.set_pending_feedback("sessao-a", {"profile_id": "P0"})
    assistant_storage.set_pending_feedback("sessao-b", {"profile_id": "P1"})

    popped = assistant_storage.pop_pending_feedback("sessao-a")
    assert popped is not None

    remaining = assistant_storage._state_manager.plugin_list_prefix(
        assistant_storage.namespace,
        "pending:",
    )
    keys = [key for key, _value in remaining]
    assert "pending:sessao-a:v1" not in keys
    assert "pending:sessao-b:v1" in keys


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
