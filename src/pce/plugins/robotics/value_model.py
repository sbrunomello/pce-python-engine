"""Robotics ValueModel plugin implementation."""

from __future__ import annotations

from pce.core.plugins import ValueModelPlugin
from pce.core.types import PCEEvent


class RoboticsValueModelPlugin(ValueModelPlugin):
    """Domain value evaluator for robotics observations and feedback."""

    name = "robotics.value_model"

    def match(self, event: PCEEvent, state: dict[str, object]) -> bool:
        _ = state
        return event.payload.get("domain") == "robotics"

    def evaluate(self, event: PCEEvent, state: dict[str, object]) -> float:
        _ = state
        payload = event.payload
        sensors = payload.get("sensors", {}) if isinstance(payload.get("sensors"), dict) else {}

        front = int(sensors.get("front", 0))
        distance = float(payload.get("distance", payload.get("delta", {}).get("manhattan", 0)))
        step_reward = float(payload.get("reward", -0.01))

        safety = 0.0 if front == 0 else 1.0
        progress = max(0.0, min(1.0, 1.0 - (distance / 20.0)))
        efficiency = max(0.0, min(1.0, 1.0 + min(0.0, step_reward)))
        value_score = 0.5 * safety + 0.35 * progress + 0.15 * efficiency
        return max(0.0, min(1.0, value_score))
