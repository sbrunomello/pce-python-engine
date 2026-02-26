"""Adaptive Feedback System implementation."""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from pce.core.types import ExecutionResult
from pce.robotics.rl import ROBOT_ACTIONS, build_state_key, q_learning_update
from pce.sm.manager import StateManager


class AdaptiveFeedbackSystem:
    """Updates internal model slices based on execution outcomes."""

    def __init__(self, state_manager: StateManager | None = None) -> None:
        self._state_manager = state_manager

    def adapt(self, state: Mapping[str, Any], result: ExecutionResult) -> dict[str, Any]:
        """Apply adaptive update to model and strategic value weights."""
        if result.action_type == "robotics.feedback" and self._state_manager is not None:
            return self._adapt_robotics_feedback(dict(state), result)

        next_state = dict(state)
        model = dict(next_state.get("model", {}))
        learning_rate = float(model.get("learning_rate", 0.1))

        # Reward successful trajectories, penalize weak outcomes.
        outcome = result.observed_impact if result.success else -result.observed_impact
        delta = learning_rate * outcome
        model["coherence_bias"] = float(model.get("coherence_bias", 0.0)) + delta
        model["last_action"] = result.action_type

        # Adaptive strategic value tuning driven by explicit contradictions + feedback.
        strategic_values = dict(
            next_state.get(
                "strategic_values",
                {
                    "safety": 1.0,
                    "efficiency": 0.8,
                    "financial_responsibility": 0.9,
                    "long_term_coherence": 1.0,
                },
            )
        )
        violated_values = list(result.metadata.get("violated_values", []))
        contradiction_penalty = 0.05 if violated_values else 0.0
        feedback_boost = 0.03 * max(-1.0, min(1.0, outcome))

        for key, current in strategic_values.items():
            weight = float(current)
            if key in violated_values:
                # Increase salience of violated values so future scoring emphasizes them.
                weight += contradiction_penalty
            else:
                weight += feedback_boost
            strategic_values[key] = max(0.2, min(1.5, weight))

        next_state["model"] = model
        next_state["strategic_values"] = strategic_values
        return next_state

    def _adapt_robotics_feedback(
        self,
        state: dict[str, Any],
        result: ExecutionResult,
    ) -> dict[str, Any]:
        robotics = state.get("robotics")
        if not isinstance(robotics, dict):
            return state

        feedback = result.metadata.get("feedback")
        if not isinstance(feedback, dict):
            return state

        episode_id = str(feedback.get("episode_id", ""))
        if not episode_id:
            return state

        episodes = robotics.get("episodes")
        if not isinstance(episodes, dict):
            return state
        episode = episodes.get(episode_id)
        if not isinstance(episode, dict):
            return state

        transition = episode.get("pending_transition")
        if not isinstance(transition, dict):
            return state

        state_key = str(transition.get("state_key", ""))
        action = str(transition.get("action", ""))
        next_observation = feedback.get("next_observation")
        if isinstance(next_observation, dict):
            next_state_key = build_state_key(next_observation)
        else:
            next_state_key = str(episode.get("last_state_key", state_key))
            print(
                json.dumps(
                    {
                        "event": "q_update_missing_next_observation",
                        "episode_id": episode_id,
                        "tick": feedback.get("tick", transition.get("tick", 0)),
                    },
                    ensure_ascii=False,
                )
            )
        reward = float(feedback.get("reward", 0.0))
        done = bool(feedback.get("done", False))
        tick = int(feedback.get("tick", transition.get("tick", 0)))

        if not state_key or action not in ROBOT_ACTIONS:
            return state

        params = self._state_manager.get_robotics_params()
        alpha = float(params["alpha"])
        gamma = float(params["gamma"])
        epsilon = float(params["epsilon"])
        epsilon_decay = float(params["epsilon_decay"])
        epsilon_min = float(params["epsilon_min"])

        q_current = self._state_manager.get_q(state_key)
        old_q = float(q_current.get(action, 0.0))
        q_next = self._state_manager.get_q(next_state_key)
        max_next = max((float(q_next.get(candidate, 0.0)) for candidate in ROBOT_ACTIONS), default=0.0)
        new_q = q_learning_update(old_q, reward, max_next if not done else 0.0, alpha, gamma)

        self._state_manager.set_q(state_key, action, new_q)
        new_epsilon = max(epsilon_min, epsilon * epsilon_decay)
        self._state_manager.update_robotics_params(epsilon=new_epsilon)
        self._state_manager.remember_transition(
            episode_id=episode_id,
            tick=tick,
            state_key=state_key,
            action=action,
            reward=reward,
            next_state_key=next_state_key,
            done=done,
        )
        success = done and str(feedback.get("reason", "")) == "goal"
        self._state_manager.update_robotics_stats(
            episode_id=episode_id,
            reward=reward,
            collisions=int(feedback.get("collisions", 0)),
            success=success,
        )

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

        episode["last_transition"] = q_update
        episode["pending_transition"] = {}
        episodes[episode_id] = episode
        robotics["episodes"] = episodes
        state["robotics"] = robotics
        state["robotics_rl"] = {"updated": True, **q_update}
        return state
