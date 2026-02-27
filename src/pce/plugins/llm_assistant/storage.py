"""StateManager-backed storage for assistant plugin data."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pce.plugins.llm_assistant.policy import PolicyState, ProfileStats, default_policy_state
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
            return {"last_messages": [], "summary": "", "preferences": []}

        messages = stored.get("last_messages")
        preferences = stored.get("preferences")
        return {
            "last_messages": messages if isinstance(messages, list) else [],
            "summary": str(stored.get("summary", ""))[:600],
            "preferences": preferences if isinstance(preferences, list) else [],
        }

    def save_session_memory(self, session_id: str, memory: dict[str, Any]) -> None:
        """Persist one session memory document."""
        self._state_manager.plugin_set_json(self.namespace, f"mem:{session_id}", memory)

    def set_pending_feedback(self, session_id: str, pending: dict[str, Any]) -> None:
        """Persist pending decision data used by adaptation."""
        self._state_manager.plugin_set_json(self.namespace, f"pending:{session_id}", pending)

    def pop_pending_feedback(self, session_id: str) -> dict[str, Any] | None:
        """Load and remove pending decision metadata."""
        key = f"pending:{session_id}"
        pending = self._state_manager.plugin_get_json(self.namespace, key)
        self._state_manager.plugin_delete_prefix(self.namespace, key)
        return pending if isinstance(pending, dict) else None

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
            "preferences": list(memory.get("preferences", []))[:10],
        }
        self.save_session_memory(session_id, updated_memory)
        return updated_memory

    def add_preference(self, session_id: str, note: str) -> dict[str, Any]:
        """Persist a user preference bullet for future prompting."""
        memory = self.get_session_memory(session_id)
        preferences = [str(item) for item in memory.get("preferences", []) if str(item).strip()]
        clean_note = note.strip()[:120]
        if clean_note and clean_note not in preferences:
            preferences.append(clean_note)
        memory["preferences"] = preferences[-10:]
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
