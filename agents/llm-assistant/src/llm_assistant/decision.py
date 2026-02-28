"""Assistant decision plugin that calls OpenRouter and emits assistant actions."""

from __future__ import annotations

import hashlib
import json
import re
import time
from typing import Any

from pce.core.plugins import DecisionPlugin
from pce.core.types import ActionPlan, PCEEvent
from llm_assistant.client import OpenRouterError, OpenRouterMissingAPIKeyError
from llm_assistant.policy import apply_profile_override, choose_profile
from llm_assistant.storage import AssistantStorage
from llm_assistant.value_model import AssistantValueModelPlugin


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
        bandit_choice = choose_profile(policy_state)
        override = apply_profile_override(choice=bandit_choice, value_score=value_score, cci=cci)
        final_choice = override.choice

        strategic_values = state.get("strategic_values")
        strategic_values_dict = strategic_values if isinstance(strategic_values, dict) else {}

        messages = self._build_messages(
            user_text=user_text,
            memory=memory,
            strategic_values=strategic_values_dict,
        )
        serialized_prompt = json.dumps(messages, sort_keys=True).encode("utf-8")
        prompt_hash = hashlib.sha256(serialized_prompt).hexdigest()

        final_decoding = {
            "temperature": float(final_choice.config["temperature"]),
            "top_p": float(final_choice.config["top_p"]),
            "presence_penalty": float(final_choice.config["presence_penalty"]),
        }

        openrouter_error: str | None = None
        try:
            reply_text = self._llm_client.generate_reply_sync(messages, **final_decoding)
        except OpenRouterMissingAPIKeyError as exc:
            openrouter_error = _format_exception_short(exc)
            _log_llm_error(
                session_id=session_id,
                model=getattr(self._llm_client, "model", "unknown"),
                prompt_hash=prompt_hash,
                error=openrouter_error,
            )
            reply_text = (
                "Configuração ausente/erro OpenRouter. Ajuste "
                "OPENROUTER_API_KEY/OPENROUTER_MODEL."
            )
        except OpenRouterError as exc:
            openrouter_error = _format_exception_short(exc)
            _log_llm_error(
                session_id=session_id,
                model=getattr(self._llm_client, "model", "unknown"),
                prompt_hash=prompt_hash,
                error=openrouter_error,
            )
            reply_text = (
                "Configuração ausente/erro OpenRouter. Ajuste "
                "OPENROUTER_API_KEY/OPENROUTER_MODEL."
            )

        self._storage.append_session_message(session_id, "user", user_text)
        self._storage.append_session_message(session_id, "assistant", reply_text)
        self._storage.set_pending_feedback(
            session_id,
            {
                "profile_id": final_choice.profile_id,
                "epsilon": bandit_choice.epsilon,
                "bandit_profile_id": bandit_choice.profile_id,
                "bandit_mode": bandit_choice.mode,
                "final_mode": final_choice.mode,
                "override_reason": override.override_reason,
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
                    "avoid_count": len(memory.get("avoid", [])),
                    "avoid_injected": bool(memory.get("avoid", [])),
                },
            },
            "vel": {"value_score": value_score, "components": components},
            "cci": {"cci": cci, "components": {}},
            "de": {
                "selected_by_bandit": {
                    "profile_id": bandit_choice.profile_id,
                    "mode": bandit_choice.mode,
                    "epsilon": bandit_choice.epsilon,
                },
                "final_profile": {
                    "profile_id": final_choice.profile_id,
                    "mode": final_choice.mode,
                },
                "override_reason": override.override_reason,
                "final_decoding": final_decoding,
                "model": getattr(self._llm_client, "model", "unknown"),
                "prompt_hash": prompt_hash,
                "openrouter_error": openrouter_error,
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
                    "profile": bandit_choice.profile_id,
                    "final_profile": final_choice.profile_id,
                    "mode": final_choice.mode,
                    "override_reason": override.override_reason,
                    "epsilon": bandit_choice.epsilon,
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
                f"assistant profile={final_choice.profile_id} mode={final_choice.mode} "
                f"epsilon={bandit_choice.epsilon:.4f}"
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
        preferences = [str(item).strip()[:120] for item in memory.get("preferences", [])][:10]
        avoids = [str(item).strip()[:120] for item in memory.get("avoid", [])][:10]
        pref_section = "\n".join(f"- {item}" for item in preferences if item) or "- none"
        avoid_section = "\n".join(f"- {item}" for item in avoids if item) or "- none"

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
                    f"Evitar:\n{avoid_section}\n"
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


def _log_llm_error(*, session_id: str, model: str, prompt_hash: str, error: str) -> None:
    """Emit sanitized structured error logs for OpenRouter failures."""
    print(
        json.dumps(
            {
                "event": "llm_error",
                "session_id": session_id,
                "model": model,
                "prompt_hash": prompt_hash,
                "error": _sanitize_error_text(error),
            },
            ensure_ascii=False,
        )
    )


def _format_exception_short(exc: Exception, *, limit: int = 240) -> str:
    """Build short error string preserving type and first message excerpt."""
    error_text = f"{type(exc).__name__}: {exc}"
    compact = re.sub(r"\s+", " ", error_text).strip()
    return _sanitize_error_text(compact[:limit])


def _sanitize_error_text(text: str) -> str:
    """Redact sensitive tokens while keeping actionable diagnostics."""
    redacted = re.sub(r"(?i)bearer\s+[a-z0-9._-]+", "Bearer [REDACTED]", text)
    redacted = re.sub(r"(?i)(api[_-]?key\s*[=:]\s*)([^\s,;]+)", r"\1[REDACTED]", redacted)
    redacted = re.sub(r"\bsk-[A-Za-z0-9_-]{12,}\b", "sk-[REDACTED]", redacted)
    return redacted
