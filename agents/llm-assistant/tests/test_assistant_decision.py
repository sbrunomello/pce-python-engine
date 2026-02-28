from __future__ import annotations

from pce.core.types import PCEEvent
from llm_assistant.client import OpenRouterError
from llm_assistant.decision import AssistantDecisionPlugin
from llm_assistant.value_model import AssistantValueModelPlugin


class _StorageStub:
    def get_session_memory(self, session_id: str) -> dict[str, object]:
        del session_id
        return {"summary": "", "last_messages": [], "preferences": [], "avoid": []}

    def get_policy_state(self) -> dict[str, object]:
        return {
            "epsilon": 0.0,
            "feedback_count": 0,
            "selected_profile": "P0",
            "profiles": {
                "P0": {"count": 1, "avg_reward": 0.5},
                "P1": {"count": 0, "avg_reward": 0.0},
                "P2": {"count": 0, "avg_reward": 0.0},
                "P3": {"count": 0, "avg_reward": 0.0},
            },
        }

    def append_session_message(self, session_id: str, role: str, text: str) -> None:
        del session_id, role, text

    def set_pending_feedback(self, session_id: str, payload: dict[str, object]) -> None:
        del session_id, payload


class _FailingLLMClient:
    model = "provider/model"

    def generate_reply_sync(self, messages, **kwargs):  # type: ignore[no-untyped-def]
        del messages, kwargs
        raise OpenRouterError("401 Unauthorized api_key=sk-secret-123456789")


def test_assistant_decision_exposes_openrouter_error_and_logs(capsys) -> None:
    plugin = AssistantDecisionPlugin(_StorageStub(), AssistantValueModelPlugin(), _FailingLLMClient())
    event = PCEEvent(
        event_type="observation.assistant.v1",
        source="assistant-ui",
        payload={
            "domain": "assistant",
            "session_id": "sess-1",
            "text": "Teste rápido",
            "tags": ["assistant"],
        },
    )

    plan = plugin.deliberate(event, {"strategic_values": {}}, value_score=0.8, cci=0.9)

    openrouter_error = plan.metadata["explain"]["de"]["openrouter_error"]
    assert openrouter_error.startswith("OpenRouterError: 401 Unauthorized")
    assert "api_key=[REDACTED]" in openrouter_error

    stdout = capsys.readouterr().out
    assert '"event": "llm_error"' in stdout
    assert '"session_id": "sess-1"' in stdout
    assert '"model": "provider/model"' in stdout
    assert '"prompt_hash":' in stdout
