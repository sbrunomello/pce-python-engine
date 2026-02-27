"""Robotics Decision plugin implementation."""

from __future__ import annotations

from typing import Any

from pce.core.plugins import DecisionPlugin
from pce.core.types import ActionPlan, PCEEvent
from pce.plugins.robotics.rl import (
    ROBOT_ACTIONS,
    action_to_robot_command,
    build_state_key,
    choose_action,
)
from pce.plugins.robotics.storage import RoboticsStorage


class RoboticsDecisionPlugin(DecisionPlugin):
    """Epsilon-greedy robotics decision plugin."""

    name = "robotics.decision"

    def __init__(self, storage: RoboticsStorage) -> None:
        self._storage = storage

    def match(self, event: PCEEvent, state: dict[str, object]) -> bool:
        _ = state
        return event.payload.get("domain") == "robotics" and event.event_type.startswith(
            "observation.robotics"
        )

    def deliberate(
        self,
        event: PCEEvent,
        state: dict[str, object],
        value_score: float,
        cci: float,
    ) -> ActionPlan:
        _ = (value_score, cci)
        observation = self._resolve_observation(event, state)
        episode_id = str(observation.get("episode_id", event.payload.get("episode_id", "global")))
        state_key = build_state_key(observation)

        params = self._storage.get_params()
        epsilon = float(params.get("epsilon", 1.0))
        q_values = self._storage.get_q(state_key)
        chosen_action, mode = choose_action(q_values, epsilon)
        best_action = max(ROBOT_ACTIONS, key=lambda action: q_values.get(action, 0.0))

        transition: dict[str, Any] = {
            "episode_id": episode_id,
            "state_key": state_key,
            "action": chosen_action,
            "tick": int(observation.get("tick", 0)),
        }
        self._storage.set_episode_pending_transition(state, episode_id, transition)

        rationale = (
            "robotics epsilon-greedy: "
            f"episode={episode_id}, mode={mode}, chosen={chosen_action}, best={best_action}, "
            f"epsilon={epsilon:.4f}."
        )
        return ActionPlan(
            action_type="robotics.action",
            rationale=rationale,
            priority=2,
            metadata={
                "action_payload": action_to_robot_command(chosen_action),
                "rl": {
                    "state_key": state_key,
                    "epsilon": epsilon,
                    "q": q_values,
                    "policy_mode": mode,
                    "best_action": best_action,
                },
            },
        )

    @staticmethod
    def _resolve_observation(event: PCEEvent, state: dict[str, object]) -> dict[str, Any]:
        payload_observation = dict(event.payload)
        robotics = state.get("robotics")
        if not isinstance(robotics, dict):
            return payload_observation

        episode_id = str(payload_observation.get("episode_id", "global"))
        episodes = robotics.get("episodes")
        if not isinstance(episodes, dict):
            return payload_observation

        episode_state = episodes.get(episode_id)
        if not isinstance(episode_state, dict):
            return payload_observation

        observation = episode_state.get("last_observation")
        if not isinstance(observation, dict):
            return payload_observation
        return dict(observation)
