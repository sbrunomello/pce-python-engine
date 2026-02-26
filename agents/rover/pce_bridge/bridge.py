from __future__ import annotations

import hashlib
import os
from typing import Any

import httpx

from .contracts import FEEDBACK_EVENT_TYPE, OBSERVATION_EVENT_TYPE


class PCEBridge:
    def __init__(
        self,
        events_url: str | None = None,
        timeout_seconds: float = 5.0,
    ) -> None:
        self.events_url = events_url or os.getenv("PCE_EVENTS_URL", "http://127.0.0.1:8000/events")
        self._client = httpx.AsyncClient(timeout=timeout_seconds)

    async def close(self) -> None:
        await self._client.aclose()

    async def decide(self, observation_payload: dict[str, Any], trace_id: str) -> dict[str, Any]:
        payload = {
            "event_type": OBSERVATION_EVENT_TYPE,
            "source": "agents.rover",
            "payload": {
                "domain": "robotics",
                "tags": ["observation", "sensors"],
                **observation_payload,
            },
        }
        try:
            response = await self._client.post(self.events_url, json=payload)
            response.raise_for_status()
            result = response.json()
            return self._adapt_action(result.get("action"), observation_payload)
        except (httpx.HTTPError, ValueError):
            # Keep the simulation fluid even when the decision endpoint is slow/unavailable.
            # We intentionally degrade to a deterministic local policy instead of blocking ticks.
            return self._fallback_action(observation_payload)

    async def send_feedback(self, feedback_payload: dict[str, Any]) -> None:
        payload = {
            "event_type": FEEDBACK_EVENT_TYPE,
            "source": "agents.rover",
            "payload": {
                "domain": "robotics",
                "tags": ["feedback", "step_result"],
                **feedback_payload,
            },
        }
        response = await self._client.post(self.events_url, json=payload)
        response.raise_for_status()

    def _fallback_action(self, observation_payload: dict[str, Any]) -> dict[str, Any]:
        sensors = observation_payload["sensors"]
        if int(sensors["front"]) > 0:
            return {"type": "robot.move_forward", "amount": 1}
        if int(sensors["front_left"]) > int(sensors["front_right"]):
            return {"type": "robot.turn_left"}
        return {"type": "robot.turn_right"}

    def _adapt_action(
        self, pce_action: object, observation_payload: dict[str, Any]
    ) -> dict[str, Any]:
        delta = observation_payload["delta"]
        sensors = observation_payload["sensors"]
        if int(sensors["front"]) > 0 and abs(int(delta["dx"])) + abs(int(delta["dy"])) > 0:
            return {"type": "robot.move_forward", "amount": 1}

        if isinstance(pce_action, str) and pce_action:
            choice = int(hashlib.sha256(pce_action.encode("utf-8")).hexdigest(), 16) % 2
            return {"type": "robot.turn_left" if choice == 0 else "robot.turn_right"}

        return {"type": "robot.stop"}
