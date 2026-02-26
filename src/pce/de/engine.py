"""Decision Engine implementation."""

from __future__ import annotations

from typing import Any

from pce.core.types import ActionPlan
from pce.robotics.rl import ROBOT_ACTIONS, action_to_robot_command, build_state_key, choose_action
from pce.sm.manager import StateManager


class DecisionEngine:
    """Derives action plans from state, value score, and coherence index."""

    def __init__(self, state_manager: StateManager | None = None) -> None:
        self._state_manager = state_manager

    def deliberate(self, state: dict[str, object], value_score: float, cci: float) -> ActionPlan:
        """Select an action using adaptive scoring without hardcoded action rules."""
        robotics_plan = self._deliberate_robotics(state)
        if robotics_plan is not None:
            return robotics_plan

        # Dynamic pressure from state complexity and model feedback.
        model = state.get("model", {}) if isinstance(state.get("model"), dict) else {}
        coherence_bias = float(model.get("coherence_bias", 0.0))
        state_complexity = min(1.0, len(state.keys()) / 10.0)

        # Candidate actions are ranked by a compositional score instead of thresholds.
        candidates = {
            "stabilize": 0.55 * (1.0 - cci) + 0.25 * (1.0 - value_score) + 0.20 * state_complexity,
            "execute_strategy": 0.60 * value_score + 0.35 * cci + 0.05 * (1.0 - state_complexity),
            "collect_more_data": 0.45 * (1.0 - value_score)
            + 0.35 * (1.0 - cci)
            + 0.20 * state_complexity,
        }
        candidates["execute_strategy"] += 0.05 * max(0.0, coherence_bias)
        candidates["stabilize"] += 0.05 * max(0.0, -coherence_bias)

        ranked = sorted(candidates.items(), key=lambda pair: pair[1], reverse=True)
        action_type, best_score = ranked[0]
        priority = max(1, min(5, int(round(5 - (cci + value_score) * 2))))

        rationale = (
            f"Ação selecionada por score composto={best_score:.3f}; "
            f"cci={cci:.3f}, value_score={value_score:.3f}, "
            f"state_complexity={state_complexity:.3f}, coherence_bias={coherence_bias:.3f}."
        )
        expected_impact = max(0.0, min(1.0, 0.55 * value_score + 0.45 * cci))

        return ActionPlan(
            action_type=action_type,
            rationale=rationale,
            priority=priority,
            metadata={
                "state_keys": list(state.keys()),
                "candidate_scores": candidates,
                "expected_impact": expected_impact,
            },
        )

    def _deliberate_robotics(self, state: dict[str, object]) -> ActionPlan | None:
        if self._state_manager is None:
            return None
        robotics = state.get("robotics")
        if not isinstance(robotics, dict):
            return None
        episodes = robotics.get("episodes")
        if not isinstance(episodes, dict) or not episodes:
            return None

        episode_id, episode_state = next(reversed(episodes.items()))
        if not isinstance(episode_state, dict):
            return None
        observation = episode_state.get("last_observation")
        if not isinstance(observation, dict):
            return None

        state_key = build_state_key(observation)
        params = self._state_manager.get_robotics_params()
        epsilon = float(params.get("epsilon", 1.0))
        q_values = self._state_manager.get_q(state_key)
        normalized_q = {action: float(q_values.get(action, 0.0)) for action in ROBOT_ACTIONS}
        chosen_action, mode = choose_action(normalized_q, epsilon)

        pending_transition: dict[str, Any] = {
            "state_key": state_key,
            "action": chosen_action,
            "tick": int(observation.get("tick", episode_state.get("last_tick", 0))),
            "episode_id": episode_id,
        }
        updated_episodes = dict(episodes)
        updated_episode_state = dict(episode_state)
        updated_episode_state["last_action"] = chosen_action
        updated_episode_state["pending_transition"] = pending_transition
        updated_episodes[str(episode_id)] = updated_episode_state
        robotics["episodes"] = updated_episodes
        state["robotics"] = robotics

        best_q = max(normalized_q.values())
        rationale = (
            "robotics epsilon-greedy: "
            f"episode={episode_id}, sensors={observation.get('sensors')}, delta={observation.get('delta')}, "
            f"mode={mode}, chosen={chosen_action}, best_q={best_q:.4f}."
        )
        robot_action = action_to_robot_command(chosen_action)
        return ActionPlan(
            action_type="robotics.action",
            rationale=rationale,
            priority=2,
            metadata={
                "robot_action": robot_action,
                "rl": {
                    "state_key": state_key,
                    "epsilon": epsilon,
                    "q": normalized_q,
                    "policy_mode": mode,
                    "best_action": max(normalized_q, key=normalized_q.get),
                },
            },
        )
