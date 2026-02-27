"""Epsilon-greedy policy profiles for the assistant plugin."""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import TypedDict


class ProfileConfig(TypedDict):
    """Discrete decoding profile configuration."""

    temperature: float
    top_p: float
    presence_penalty: float


class ProfileStats(TypedDict):
    """Bandit statistics tracked per profile."""

    count: int
    avg_reward: float


class PolicyState(TypedDict):
    """Persisted policy state for epsilon-greedy selection."""

    epsilon: float
    feedback_count: int
    selected_profile: str
    profiles: dict[str, ProfileStats]


PROFILES: dict[str, ProfileConfig] = {
    "P0": {"temperature": 0.2, "top_p": 0.8, "presence_penalty": 0.0},
    "P1": {"temperature": 0.7, "top_p": 0.9, "presence_penalty": 0.1},
    "P2": {"temperature": 0.9, "top_p": 0.95, "presence_penalty": 0.2},
    "P3": {"temperature": 0.4, "top_p": 0.9, "presence_penalty": 0.0},
}

EPSILON_START = 0.6
EPSILON_MIN = 0.05
EPSILON_DECAY = 0.92


@dataclass(slots=True)
class PolicyChoice:
    """One policy selection decision."""

    profile_id: str
    mode: str
    epsilon: float
    config: ProfileConfig


def default_policy_state() -> PolicyState:
    """Build default policy baseline."""
    return {
        "epsilon": EPSILON_START,
        "feedback_count": 0,
        "selected_profile": "P3",
        "profiles": {
            profile_id: {"count": 0, "avg_reward": 0.0}
            for profile_id in sorted(PROFILES.keys())
        },
    }


def choose_profile(policy_state: PolicyState) -> PolicyChoice:
    """Select one profile using epsilon-greedy policy."""
    epsilon = float(policy_state["epsilon"])
    profiles = policy_state["profiles"]

    if random.random() < epsilon:
        profile_id = random.choice(sorted(PROFILES.keys()))
        mode = "explore"
    else:
        profile_id = max(
            sorted(PROFILES.keys()),
            key=lambda candidate: float(profiles.get(candidate, {"avg_reward": 0.0})["avg_reward"]),
        )
        mode = "exploit"

    return PolicyChoice(
        profile_id=profile_id,
        mode=mode,
        epsilon=epsilon,
        config=PROFILES[profile_id],
    )


def reward_from_feedback(payload: dict[str, object]) -> float:
    """Normalize accepted feedback contracts into [-1, 1]."""
    reward = payload.get("reward")
    if isinstance(reward, (int, float)):
        return max(-1.0, min(1.0, float(reward)))

    rating = payload.get("rating")
    if isinstance(rating, int):
        normalized = (float(rating) - 3.0) / 2.0
        return max(-1.0, min(1.0, normalized))

    accepted = payload.get("accepted")
    if isinstance(accepted, bool):
        return 1.0 if accepted else -1.0

    return 0.0


def update_policy(policy_state: PolicyState, profile_id: str, reward: float) -> PolicyState:
    """Update profile stats and decay epsilon."""
    profiles_copy: dict[str, ProfileStats] = {
        key: {"count": int(stats["count"]), "avg_reward": float(stats["avg_reward"])}
        for key, stats in policy_state["profiles"].items()
    }
    if profile_id not in profiles_copy:
        profiles_copy[profile_id] = {"count": 0, "avg_reward": 0.0}

    selected_stats = profiles_copy[profile_id]
    updated_count = int(selected_stats["count"]) + 1
    updated_avg = float(selected_stats["avg_reward"]) + (
        reward - float(selected_stats["avg_reward"])
    ) / float(updated_count)

    selected_stats["count"] = updated_count
    selected_stats["avg_reward"] = updated_avg

    return {
        "epsilon": max(EPSILON_MIN, float(policy_state["epsilon"]) * EPSILON_DECAY),
        "feedback_count": int(policy_state["feedback_count"]) + 1,
        "selected_profile": profile_id,
        "profiles": profiles_copy,
    }
