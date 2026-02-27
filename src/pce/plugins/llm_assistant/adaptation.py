"""Assistant adaptation plugin for feedback-driven policy and memory updates."""

from __future__ import annotations

import json

from pce.core.plugins import AdaptationPlugin
from pce.core.types import ExecutionResult, PCEEvent
from pce.plugins.llm_assistant.policy import reward_from_feedback, update_policy
from pce.plugins.llm_assistant.storage import AssistantStorage


class AssistantAdaptationPlugin(AdaptationPlugin):
    """Applies online learning updates from assistant feedback events."""

    name = "assistant.adaptation"

    def __init__(self, storage: AssistantStorage) -> None:
        self._storage = storage

    def match(self, event: PCEEvent, state: dict[str, object], result: ExecutionResult) -> bool:
        _ = (state, result)
        return event.payload.get("domain") == "assistant" and event.event_type.startswith(
            "feedback.assistant"
        )

    def adapt(
        self,
        state: dict[str, object],
        event: PCEEvent,
        result: ExecutionResult,
    ) -> dict[str, object]:
        _ = result
        payload = event.payload
        session_id = str(payload.get("session_id", "")).strip()
        if not session_id:
            return state

        reward = reward_from_feedback(payload)
        pending = self._storage.pop_pending_feedback(session_id) or {}
        profile_id = str(pending.get("profile_id", "P3"))

        policy_state = self._storage.get_policy_state()
        updated_policy = update_policy(policy_state, profile_id, reward)
        self._storage.save_policy_state(updated_policy)

        reward_window = self._storage.get_reward_window()
        reward_window.append(reward)
        reward_window = reward_window[-50:]
        self._storage.save_reward_window(reward_window)

        count_feedbacks = float(len(reward_window))
        avg_reward = sum(reward_window) / count_feedbacks if count_feedbacks else 0.0
        success_count = len([value for value in reward_window if value > 0.0])
        success_rate = float(success_count) / count_feedbacks if count_feedbacks else 0.0

        metrics = {
            "count_feedbacks": count_feedbacks,
            "avg_reward": avg_reward,
            "success_rate": success_rate,
        }
        self._storage.save_metrics(metrics)

        notes = payload.get("notes")
        wrote_preference = False
        wrote_avoid = False
        if isinstance(notes, str) and notes.strip() and reward > 0.0:
            self._storage.add_preference(session_id, notes)
            wrote_preference = True
        if isinstance(notes, str) and notes.strip() and reward < 0.0:
            self._storage.add_avoid(session_id, notes)
            wrote_avoid = True

        profile_stats = updated_policy["profiles"].get(profile_id, {"count": 0, "avg_reward": 0.0})
        afs_explain = {
            "updated": True,
            "reward": reward,
            "profile_stats": {
                "profile_id": profile_id,
                "count": int(profile_stats["count"]),
                "avg_reward": float(profile_stats["avg_reward"]),
            },
            "metrics": metrics,
            "wrote_preference": wrote_preference,
            "wrote_avoid": wrote_avoid,
        }

        print(
            json.dumps(
                {
                    "event": "llm_feedback",
                    "session_id": session_id,
                    "reward": reward,
                    "updated_profile": profile_id,
                    "new_epsilon": updated_policy["epsilon"],
                    "wrote_preference": wrote_preference,
                    "wrote_avoid": wrote_avoid,
                },
                ensure_ascii=False,
            )
        )

        mutated_state = dict(state)
        mutated_state["assistant_learning"] = {
            "updated": True,
            "epsilon": updated_policy["epsilon"],
            "count_feedbacks": count_feedbacks,
            "avg_reward": avg_reward,
            "success_rate": success_rate,
            "afs_explain": afs_explain,
        }
        return mutated_state
