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


@dataclass(slots=True)
class PolicyOverrideResult:
    """Result of optional deterministic safety override over bandit choice."""

    choice: PolicyChoice
    override_reason: str | None


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


def apply_profile_override(
    *,
    choice: PolicyChoice,
    value_score: float,
    cci: float,
) -> PolicyOverrideResult:
    """Apply deterministic safety override when strategic confidence is low."""
    if value_score < 0.55:
        return PolicyOverrideResult(
            choice=PolicyChoice(
                profile_id="P0",
                mode="override_safe",
                epsilon=choice.epsilon,
                # Clamp decoding to deterministic-safe values regardless of profile defaults.
                config={
                    "temperature": min(0.3, float(PROFILES["P0"]["temperature"])),
                    "top_p": min(0.85, float(PROFILES["P0"]["top_p"])),
                    "presence_penalty": 0.0,
                },
            ),
            override_reason=f"override_safe: value_score={value_score:.2f} < 0.55",
        )
    if cci < 0.45:
        return PolicyOverrideResult(
            choice=PolicyChoice(
                profile_id="P0",
                mode="override_safe",
                epsilon=choice.epsilon,
                config={
                    "temperature": min(0.3, float(PROFILES["P0"]["temperature"])),
                    "top_p": min(0.85, float(PROFILES["P0"]["top_p"])),
                    "presence_penalty": 0.0,
                },
            ),
            override_reason=f"override_safe: cci={cci:.2f} < 0.45",
        )

    if value_score > 0.75 and cci > 0.65:
        return PolicyOverrideResult(choice=choice, override_reason="no_override_high_confidence")

    return PolicyOverrideResult(choice=choice, override_reason=None)


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
