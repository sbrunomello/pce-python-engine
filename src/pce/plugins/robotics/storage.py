"""Storage wrapper for robotics plugin persistence."""

from __future__ import annotations

from typing import Any

from pce.plugins.robotics.rl import DEFAULT_HYPERPARAMS, ROBOT_ACTIONS
from pce.sm.manager import StateManager


class RoboticsStorage:
    """Namespace-scoped wrapper around StateManager plugin KV APIs."""

    namespace = "robotics"

    def __init__(self, state_manager: StateManager) -> None:
        self._state_manager = state_manager

    def get_params(self) -> dict[str, float]:
        """Return persisted params merged with defaults."""
        stored = self._state_manager.plugin_get_json(self.namespace, "params")
        if not isinstance(stored, dict):
            self._state_manager.plugin_set_json(self.namespace, "params", DEFAULT_HYPERPARAMS)
            return dict(DEFAULT_HYPERPARAMS)

        merged = dict(DEFAULT_HYPERPARAMS)
        for key, value in stored.items():
            merged[str(key)] = float(value)
        return merged

    def set_params(self, **updates: float) -> dict[str, float]:
        """Update selected params and return persisted set."""
        params = self.get_params()
        for key, value in updates.items():
            params[key] = float(value)
        self._state_manager.plugin_set_json(self.namespace, "params", params)
        return params

    def get_q(self, state_key: str) -> dict[str, float]:
        """Load state-action values with canonical action set."""
        stored = self._state_manager.plugin_get_json(self.namespace, f"q:{state_key}")
        if not isinstance(stored, dict):
            return {action: 0.0 for action in ROBOT_ACTIONS}
        return {action: float(stored.get(action, 0.0)) for action in ROBOT_ACTIONS}

    def set_q(self, state_key: str, q_dict: dict[str, float]) -> dict[str, float]:
        """Persist all q-values for a state key."""
        normalized = {action: float(q_dict.get(action, 0.0)) for action in ROBOT_ACTIONS}
        self._state_manager.plugin_set_json(self.namespace, f"q:{state_key}", normalized)
        return normalized

    def set_q_value(self, state_key: str, action: str, value: float) -> dict[str, float]:
        """Persist one state-action pair while retaining the others."""
        current = self.get_q(state_key)
        current[action] = float(value)
        return self.set_q(state_key, current)

    def clear_policy(self) -> dict[str, float]:
        """Reset all q-values and restore default parameters."""
        self._state_manager.plugin_delete_prefix(self.namespace, "q:")
        self._state_manager.plugin_set_json(self.namespace, "params", DEFAULT_HYPERPARAMS)
        return dict(DEFAULT_HYPERPARAMS)

    def list_q(self, limit: int = 1000) -> list[tuple[str, dict[str, float]]]:
        """Expose a bounded set of persisted q entries for diagnostics/tests."""
        rows = self._state_manager.plugin_list_prefix(self.namespace, "q:", limit=limit)
        parsed: list[tuple[str, dict[str, float]]] = []
        for key, value in rows:
            state_key = key.removeprefix("q:")
            q_values = value if isinstance(value, dict) else {}
            normalized = {action: float(q_values.get(action, 0.0)) for action in ROBOT_ACTIONS}
            parsed.append((state_key, normalized))
        return parsed

    def set_episode_pending_transition(
        self,
        state: dict[str, object],
        episode_id: str,
        transition: dict[str, Any],
    ) -> dict[str, object]:
        """Persist pending transition in in-memory cognitive state slice."""
        robotics_obj = state.get("robotics")
        robotics = dict(robotics_obj) if isinstance(robotics_obj, dict) else {}
        episodes = dict(robotics.get("episodes", {}))
        episode = dict(episodes.get(episode_id, {}))
        episode["pending_transition"] = transition
        episode["last_action"] = transition.get("action")
        episodes[episode_id] = episode
        robotics["episodes"] = episodes
        state["robotics"] = robotics
        return state

    def pop_episode_pending_transition(
        self,
        state: dict[str, object],
        episode_id: str,
    ) -> tuple[dict[str, Any] | None, dict[str, object]]:
        """Load+clear pending transition from state and return both values."""
        robotics_obj = state.get("robotics")
        robotics = dict(robotics_obj) if isinstance(robotics_obj, dict) else {}
        episodes = dict(robotics.get("episodes", {}))
        episode = dict(episodes.get(episode_id, {}))
        transition = episode.get("pending_transition")
        parsed = dict(transition) if isinstance(transition, dict) else None
        episode["pending_transition"] = {}
        episodes[episode_id] = episode
        robotics["episodes"] = episodes
        state["robotics"] = robotics
        return parsed, state
