"""Internal State Integrator implementation."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pce.core.types import PCEEvent
from pce.robotics.rl import build_state_key


class InternalStateIntegrator:
    """Pure function-like state integrator for deterministic updates."""

    def integrate(self, state: Mapping[str, Any], event: PCEEvent) -> dict[str, Any]:
        """Merge event payload into current state with event metadata."""
        next_state = dict(state)
        domain = event.payload.get("domain", "general")
        state_slice = dict(next_state.get(domain, {}))
        state_slice.update(event.payload)
        state_slice["last_event_id"] = event.event_id
        state_slice["last_event_type"] = event.event_type
        next_state[domain] = state_slice

        if domain == "robotics":
            self._integrate_robotics(next_state, event)

        return next_state

    def _integrate_robotics(self, next_state: dict[str, Any], event: PCEEvent) -> None:
        robotics = dict(next_state.get("robotics", {}))
        episodes = dict(robotics.get("episodes", {}))
        payload = event.payload
        episode_id = str(payload.get("episode_id", "global"))
        tick = int(payload.get("tick", 0))

        episode = dict(episodes.get(episode_id, {}))
        if event.event_type.startswith("observation.robotics"):
            observation = dict(payload)
            state_key = build_state_key(observation)
            previous_observation = episode.get("last_observation")
            episode["prev_observation"] = previous_observation
            episode["last_observation"] = observation
            episode["last_state_key"] = state_key
            episode["last_tick"] = tick
        elif event.event_type.startswith("feedback.robotics"):
            episode_stats = dict(episode.get("episode_stats", {}))
            reward = float(payload.get("reward", 0.0))
            done = bool(payload.get("done", False))
            collisions = int(payload.get("collisions", episode_stats.get("collisions", 0)))
            episode_stats["total_reward"] = float(episode_stats.get("total_reward", 0.0)) + reward
            episode_stats["steps"] = int(episode_stats.get("steps", 0)) + 1
            episode_stats["collisions"] = collisions
            if done and str(payload.get("reason", "")) == "goal":
                episode_stats["successes"] = int(episode_stats.get("successes", 0)) + 1
            episode["episode_stats"] = episode_stats

            transition = dict(episode.get("pending_transition", {}))
            transition["reward"] = reward
            transition["done"] = done
            transition["feedback_tick"] = tick
            episode["pending_transition"] = transition

        episodes[episode_id] = episode
        robotics["episodes"] = episodes
        next_state["robotics"] = robotics
