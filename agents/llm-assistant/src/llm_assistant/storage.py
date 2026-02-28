"""StateManager-backed storage for assistant plugin data."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from llm_assistant.policy import PolicyState, ProfileStats, default_policy_state
from pce.sm.manager import StateManager


class AssistantStorage:
    """Namespace-scoped persistence for memory, policy and metrics."""

    namespace = "llm_assistant"

    def __init__(self, state_manager: StateManager) -> None:
        self._state_manager = state_manager

    def get_policy_state(self) -> PolicyState:
        """Load policy state with defaults for missing fields."""
        stored = self._state_manager.plugin_get_json(self.namespace, "policy")
        defaults = default_policy_state()
        if not isinstance(stored, dict):
            self._state_manager.plugin_set_json(self.namespace, "policy", defaults)
            return defaults

        merged_profiles: dict[str, ProfileStats] = {
            key: {
                "count": int(value.get("count", 0)),
                "avg_reward": float(value.get("avg_reward", 0.0)),
            }
            for key, value in defaults["profiles"].items()
        }
        persisted_profiles = stored.get("profiles")
        if isinstance(persisted_profiles, dict):
            for key, value in persisted_profiles.items():
                if isinstance(value, dict):
                    merged_profiles[str(key)] = {
                        "count": int(value.get("count", 0)),
                        "avg_reward": float(value.get("avg_reward", 0.0)),
                    }

        normalized: PolicyState = {
            "epsilon": float(stored.get("epsilon", defaults["epsilon"])),
            "feedback_count": int(stored.get("feedback_count", defaults["feedback_count"])),
            "selected_profile": str(stored.get("selected_profile", defaults["selected_profile"])),
            "profiles": merged_profiles,
        }
        return normalized

    def save_policy_state(self, policy_state: PolicyState) -> None:
        """Persist policy state."""
        self._state_manager.plugin_set_json(self.namespace, "policy", policy_state)

    def get_metrics(self) -> dict[str, float]:
        """Load rolling performance metrics."""
        stored = self._state_manager.plugin_get_json(self.namespace, "metrics")
        if not isinstance(stored, dict):
            default_metrics = {
                "count_feedbacks": 0.0,
                "avg_reward": 0.0,
                "success_rate": 0.0,
            }
            self._state_manager.plugin_set_json(self.namespace, "metrics", default_metrics)
            return default_metrics
        return {
            "count_feedbacks": float(stored.get("count_feedbacks", 0.0)),
            "avg_reward": float(stored.get("avg_reward", 0.0)),
            "success_rate": float(stored.get("success_rate", 0.0)),
        }

    def save_metrics(self, metrics: dict[str, float]) -> None:
        """Persist performance metrics."""
        self._state_manager.plugin_set_json(self.namespace, "metrics", metrics)

    def get_reward_window(self) -> list[float]:
        """Load bounded reward history for rolling success-rate."""
        stored = self._state_manager.plugin_get_json(self.namespace, "reward_window")
        if not isinstance(stored, list):
            return []
        return [float(value) for value in stored][:100]

    def save_reward_window(self, values: list[float]) -> None:
        """Persist bounded reward history."""
        self._state_manager.plugin_set_json(self.namespace, "reward_window", values[:100])

    def get_session_memory(self, session_id: str) -> dict[str, Any]:
        """Load conversation memory for one session."""
        stored = self._state_manager.plugin_get_json(self.namespace, f"mem:{session_id}")
        if not isinstance(stored, dict):
            return {"last_messages": [], "summary": "", "preferences": [], "avoid": []}

        messages = stored.get("last_messages")
        normalized_messages = list(messages)[-10:] if isinstance(messages, list) else []
        preferences = stored.get("preferences")
        avoid = stored.get("avoid")
        return {
            "last_messages": normalized_messages,
            "summary": str(stored.get("summary", ""))[:600],
            "preferences": _sanitize_memory_list(preferences),
            "avoid": _sanitize_memory_list(avoid),
        }

    def save_session_memory(self, session_id: str, memory: dict[str, Any]) -> None:
        """Persist one session memory document."""
        payload = {
            "last_messages": list(memory.get("last_messages", []))[-10:],
            "summary": str(memory.get("summary", ""))[:600],
            "preferences": _sanitize_memory_list(memory.get("preferences")),
            "avoid": _sanitize_memory_list(memory.get("avoid")),
        }
        self._state_manager.plugin_set_json(self.namespace, f"mem:{session_id}", payload)

    def set_pending_feedback(self, session_id: str, pending: dict[str, Any]) -> None:
        """Persist pending decision data used by adaptation."""
        self._state_manager.plugin_set_json(self.namespace, f"pending:{session_id}:v1", pending)

    def pop_pending_feedback(self, session_id: str) -> dict[str, Any] | None:
        """Load and remove pending decision metadata."""
        pending_prefix = f"pending:{session_id}:"
        pending = self._state_manager.plugin_get_json(self.namespace, f"{pending_prefix}v1")
        self._state_manager.plugin_delete_prefix(self.namespace, pending_prefix)

        if isinstance(pending, dict):
            return pending

        legacy_key = f"pending:{session_id}"
        legacy_pending = self._state_manager.plugin_get_json(self.namespace, legacy_key)
        legacy_matches = self._state_manager.plugin_list_prefix(self.namespace, legacy_key)
        # Only cleanup legacy key when the prefix window maps to a single exact key.
        if len(legacy_matches) == 1 and legacy_matches[0][0] == legacy_key:
            self._state_manager.plugin_delete_prefix(self.namespace, legacy_key)
        return legacy_pending if isinstance(legacy_pending, dict) else None

    def append_session_message(self, session_id: str, role: str, text: str) -> dict[str, Any]:
        """Append one bounded message and refresh summary snapshot."""
        memory = self.get_session_memory(session_id)
        now_iso = datetime.now(UTC).isoformat()
        messages = list(memory.get("last_messages", []))
        messages.append({"role": role, "text": text[:800], "ts": now_iso})
        messages = messages[-10:]

        short_texts = [str(item.get("text", ""))[:80] for item in messages]
        summary = " | ".join(short_texts)[-600:]

        updated_memory = {
            "last_messages": messages,
            "summary": summary,
            "preferences": _sanitize_memory_list(memory.get("preferences")),
            "avoid": _sanitize_memory_list(memory.get("avoid")),
        }
        self.save_session_memory(session_id, updated_memory)
        return updated_memory

    def add_preference(self, session_id: str, note: str) -> dict[str, Any]:
        """Persist a user preference bullet for future prompting."""
        memory = self.get_session_memory(session_id)
        preferences = _sanitize_memory_list(memory.get("preferences"))
        clean_note = note.strip()[:120]
        if clean_note and clean_note not in preferences:
            preferences.append(clean_note)
        memory["preferences"] = preferences[-10:]
        self.save_session_memory(session_id, memory)
        return memory

    def add_avoid(self, session_id: str, note: str) -> dict[str, Any]:
        """Persist an avoid bullet for future prompting."""
        memory = self.get_session_memory(session_id)
        avoid = _sanitize_memory_list(memory.get("avoid"))
        clean_note = note.strip()[:120]
        if clean_note and clean_note not in avoid:
            avoid.append(clean_note)
        memory["avoid"] = avoid[-10:]
        self.save_session_memory(session_id, memory)
        return memory

    def clear_all(self) -> int:
        """Clear assistant namespace keys used by this plugin."""
        deleted = 0
        for prefix in ("mem:", "pending:", "policy", "metrics", "reward_window"):
            deleted += self._state_manager.plugin_delete_prefix(self.namespace, prefix)
        self._state_manager.plugin_set_json(self.namespace, "policy", default_policy_state())
        self._state_manager.plugin_set_json(
            self.namespace,
            "metrics",
            {"count_feedbacks": 0.0, "avg_reward": 0.0, "success_rate": 0.0},
        )
        self._state_manager.plugin_set_json(self.namespace, "reward_window", [])
        return deleted


def _sanitize_memory_list(raw: Any) -> list[str]:
    """Normalize preferences/avoid lists to bounded clean strings."""
    if not isinstance(raw, list):
        return []
    values: list[str] = []
    for item in raw:
        text = str(item).strip()[:120]
        if text and text not in values:
            values.append(text)
        if len(values) >= 10:
            break
    return values
