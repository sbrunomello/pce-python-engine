"""Tabular Q-learning helpers for robotics domain."""

from __future__ import annotations

import random
from typing import Any

ROBOT_ACTIONS = ("FWD", "L", "R", "S")

DEFAULT_HYPERPARAMS: dict[str, float] = {
    "alpha": 0.2,
    "gamma": 0.95,
    "epsilon": 1.0,
    "epsilon_decay": 0.9995,
    "epsilon_min": 0.05,
}


def _bucket_sensor(raw: Any) -> int:
    value = max(0, int(raw))
    if value == 0:
        return 0
    if value == 1:
        return 1
    if value <= 3:
        return 2
    return 3


def _sign(raw: Any) -> int:
    value = int(raw)
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def build_state_key(payload: dict[str, Any]) -> str:
    """Create stable discretized state key from rover observation payload."""
    robot = payload.get("robot", {})
    sensors = payload.get("sensors", {})
    delta = payload.get("delta", {})
    direction = int(robot.get("dir", 0)) % 4
    dx_sign = _sign(delta.get("dx", 0))
    dy_sign = _sign(delta.get("dy", 0))
    front_bucket = _bucket_sensor(sensors.get("front", 0))
    left_bucket = _bucket_sensor(sensors.get("left", 0))
    right_bucket = _bucket_sensor(sensors.get("right", 0))
    return f"d{direction}_dx{dx_sign}_dy{dy_sign}_f{front_bucket}_l{left_bucket}_r{right_bucket}"


def choose_action(q_values: dict[str, float], epsilon: float) -> tuple[str, str]:
    """Choose robotics action using epsilon-greedy policy."""
    if random.random() < epsilon:
        return random.choice(ROBOT_ACTIONS), "explore"

    ranked = sorted(ROBOT_ACTIONS, key=lambda action: q_values.get(action, 0.0), reverse=True)
    return ranked[0], "exploit"


def action_to_robot_command(action: str) -> dict[str, Any]:
    """Convert compact RL action to robot command payload."""
    mapping: dict[str, dict[str, Any]] = {
        "FWD": {"type": "robot.move_forward", "amount": 1},
        "L": {"type": "robot.turn_left"},
        "R": {"type": "robot.turn_right"},
        "S": {"type": "robot.stop"},
    }
    return dict(mapping.get(action, {"type": "robot.stop"}))


def q_learning_update(
    current_q: float,
    reward: float,
    max_next_q: float,
    alpha: float,
    gamma: float,
) -> float:
    """Apply tabular Q-learning update rule."""
    target = reward + gamma * max_next_q
    return current_q + alpha * (target - current_q)
