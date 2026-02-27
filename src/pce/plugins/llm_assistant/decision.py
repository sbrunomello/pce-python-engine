"""Assistant decision plugin that calls OpenRouter and emits assistant actions."""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any

from pce.core.plugins import DecisionPlugin
from pce.core.types import ActionPlan, PCEEvent
from pce.plugins.llm_assistant.client import OpenRouterError, OpenRouterMissingAPIKeyError
from pce.plugins.llm_assistant.policy import choose_profile
from pce.plugins.llm_assistant.storage import AssistantStorage
from pce.plugins.llm_assistant.value_model import AssistantValueModelPlugin


class AssistantDecisionPlugin(DecisionPlugin):
    """Builds LLM prompts and emits reply action payloads."""

    name = "assistant.decision"

    def __init__(
        self,
        storage: AssistantStorage,
        value_model: AssistantValueModelPlugin,
        llm_client: Any,
    ) -> None:
        self._storage = storage
        self._value_model = value_model
        self._llm_client = llm_client

    def match(self, event: PCEEvent, state: dict[str, object]) -> bool:
        _ = state
        return event.payload.get("domain") == "assistant" and event.event_type.startswith(
            "observation.assistant"
        )

    def deliberate(
        self,
        event: PCEEvent,
        state: dict[str, object],
        value_score: float,
        cci: float,
    ) -> ActionPlan:
        started = time.perf_counter()
        payload = event.payload
        session_id = str(payload.get("session_id", "")).strip() or "global"
        user_text = str(payload.get("text", "")).strip()

        memory = self._storage.get_session_memory(session_id)
        policy_state = self._storage.get_policy_state()
        choice = choose_profile(policy_state)

        strategic_values = state.get("strategic_values")
        strategic_values_dict = strategic_values if isinstance(strategic_values, dict) else {}

        messages = self._build_messages(
            user_text=user_text,
            memory=memory,
            strategic_values=strategic_values_dict,
        )
        serialized_prompt = json.dumps(messages, sort_keys=True).encode("utf-8")
        prompt_hash = hashlib.sha256(serialized_prompt).hexdigest()

        try:
            reply_text = self._llm_client.generate_reply_sync(
                messages,
                temperature=float(choice.config["temperature"]),
                top_p=float(choice.config["top_p"]),
                presence_penalty=float(choice.config["presence_penalty"]),
            )
        except OpenRouterMissingAPIKeyError:
            reply_text = (
                "Configuração ausente/erro OpenRouter. Ajuste "
                "OPENROUTER_API_KEY/OPENROUTER_MODEL."
            )
        except OpenRouterError:
            reply_text = (
                "Configuração ausente/erro OpenRouter. Ajuste "
                "OPENROUTER_API_KEY/OPENROUTER_MODEL."
            )

        self._storage.append_session_message(session_id, "user", user_text)
        self._storage.append_session_message(session_id, "assistant", reply_text)
        self._storage.set_pending_feedback(
            session_id,
            {
                "profile_id": choice.profile_id,
                "epsilon": choice.epsilon,
                "value_score": value_score,
                "cci": cci,
                "ts": event.timestamp.isoformat(),
            },
        )

        components = self._value_model.components(event, state)
        explain = {
            "epl": {
                "event_type": event.event_type,
                "domain": payload.get("domain"),
                "tags": payload.get("tags", []),
            },
            "isi": {
                "state_keys_used": [
                    key for key in ("assistant", "strategic_values", "model") if key in state
                ],
                "memory_used": {
                    "has_summary": bool(memory.get("summary")),
                    "msgs": len(memory.get("last_messages", [])),
                    "prefs": len(memory.get("preferences", [])),
                },
            },
            "vel": {"value_score": value_score, "components": components},
            "cci": {"cci": cci, "components": {}},
            "de": {
                "policy_profile": choice.profile_id,
                "epsilon": choice.epsilon,
                "mode": choice.mode,
                "model": getattr(self._llm_client, "model", "unknown"),
                "prompt_hash": prompt_hash,
            },
            "ao": {"execution": "emitted"},
            "afs": {"pending": True},
        }

        latency_ms = (time.perf_counter() - started) * 1000.0
        print(
            json.dumps(
                {
                    "event": "llm_decision",
                    "session_id": session_id,
                    "profile": choice.profile_id,
                    "epsilon": choice.epsilon,
                    "value_score": value_score,
                    "cci": cci,
                    "latency_ms": round(latency_ms, 2),
                    "user_text_len": len(user_text),
                    "user_preview": _sanitize_preview(user_text, limit=80),
                    "reply_len": len(reply_text),
                    "reply_preview": _sanitize_preview(reply_text, limit=80),
                },
                ensure_ascii=False,
            )
        )

        return ActionPlan(
            action_type="assistant.action",
            rationale=(
                f"assistant profile={choice.profile_id} mode={choice.mode} "
                f"epsilon={choice.epsilon:.4f}"
            ),
            priority=2,
            metadata={
                "action_payload": {
                    "type": "assistant.reply",
                    "text": reply_text,
                    "format": "markdown",
                },
                "explain": explain,
            },
        )

    @staticmethod
    def _build_messages(
        *,
        user_text: str,
        memory: dict[str, Any],
        strategic_values: dict[str, object],
    ) -> list[dict[str, str]]:
        """Compose bounded OpenRouter conversation payload."""
        preferences = [str(item) for item in memory.get("preferences", [])][:10]
        pref_section = "\n".join(f"- {item[:80]}" for item in preferences) or "- none"

        strategic_items = [f"{key}={value}" for key, value in strategic_values.items()]
        strategic_section = ", ".join(strategic_items[:8]) if strategic_items else "none"

        summary = str(memory.get("summary", ""))[:600]
        messages: list[dict[str, str]] = [
            {
                "role": "system",
                "content": (
                    "Você é um assistente útil, seguro e objetivo. "
                    "Responda em markdown com clareza. "
                    f"Preferências conhecidas:\n{pref_section}\n"
                    f"Objetivos estratégicos: {strategic_section}."
                ),
            },
            {
                "role": "system",
                "content": "Internal rule: explain mode OFF. Never expose hidden reasoning.",
            },
        ]

        if summary:
            messages.append(
                {
                    "role": "system",
                    "content": f"Resumo de contexto recente (pode estar incompleto): {summary}",
                }
            )

        messages.append({"role": "user", "content": user_text[:2000]})
        return messages


def _sanitize_preview(text: str, *, limit: int) -> str:
    """Redact text for logs while preserving minimal observability."""
    compact = re.sub(r"\s+", " ", text).strip()
    return compact[:limit]
