from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RewardInput:
    prev_distance: int
    current_distance: int
    collision: bool
    reached_goal: bool


def compute_step_reward(data: RewardInput) -> float:
    reward = -0.1
    if data.reached_goal:
        return reward + 100.0
    if data.collision:
        reward -= 5.0
    if data.current_distance < data.prev_distance:
        reward += 1.0
    elif data.current_distance > data.prev_distance:
        reward -= 1.0
    return reward
