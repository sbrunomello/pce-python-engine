"""Robotics Adaptation plugin implementation."""

from __future__ import annotations

import json

from pce.core.plugins import AdaptationPlugin
from pce.core.types import ExecutionResult, PCEEvent
from rover_plugins.rl import ROBOT_ACTIONS, build_state_key, q_learning_update
from rover_plugins.storage import RoboticsStorage


class RoboticsAdaptationPlugin(AdaptationPlugin):
    """Q-learning adaptation for robotics feedback events."""

    name = "robotics.adaptation"

    def __init__(self, storage: RoboticsStorage) -> None:
        self._storage = storage

    def match(self, event: PCEEvent, state: dict[str, object], result: ExecutionResult) -> bool:
        _ = (state, result)
        return event.payload.get("domain") == "robotics" and event.event_type.startswith(
            "feedback.robotics"
        )

    def adapt(
        self,
        state: dict[str, object],
        event: PCEEvent,
        result: ExecutionResult,
    ) -> dict[str, object]:
        _ = result
        feedback = event.payload
        episode_id = str(feedback.get("episode_id", ""))
        if not episode_id:
            return state

        transition, mutated_state = self._storage.pop_episode_pending_transition(state, episode_id)
        if not isinstance(transition, dict):
            return mutated_state

        state_key = str(transition.get("state_key", ""))
        action = str(transition.get("action", ""))
        if not state_key or action not in ROBOT_ACTIONS:
            return mutated_state

        next_observation = feedback.get("next_observation")
        next_state_key = (
            build_state_key(next_observation)
            if isinstance(next_observation, dict)
            else str(transition.get("state_key", state_key))
        )

        reward = float(feedback.get("reward", 0.0))
        done = bool(feedback.get("done", False))
        params = self._storage.get_params()

        alpha = float(params["alpha"])
        gamma = float(params["gamma"])
        epsilon = float(params["epsilon"])
        epsilon_decay = float(params["epsilon_decay"])
        epsilon_min = float(params["epsilon_min"])

        q_current = self._storage.get_q(state_key)
        old_q = float(q_current.get(action, 0.0))
        q_next = self._storage.get_q(next_state_key)
        max_next = max(float(q_next.get(candidate, 0.0)) for candidate in ROBOT_ACTIONS)

        new_q = q_learning_update(old_q, reward, max_next if not done else 0.0, alpha, gamma)
        self._storage.set_q_value(state_key, action, new_q)

        new_epsilon = max(epsilon_min, epsilon * epsilon_decay)
        self._storage.set_params(epsilon=new_epsilon)

        q_update = {
            "state_key": state_key,
            "action": action,
            "reward": reward,
            "old_q": old_q,
            "new_q": new_q,
            "max_next": max_next,
            "next_state_key": next_state_key,
            "epsilon": new_epsilon,
            "done": done,
        }
        print(json.dumps({"event": "q_update", **q_update}, ensure_ascii=False))

        mutated_state["robotics_rl"] = {"updated": True, **q_update}
        return mutated_state
