from __future__ import annotations

import hashlib
from typing import Any

import httpx

from .contracts import FEEDBACK_EVENT_TYPE, OBSERVATION_EVENT_TYPE


class PCEBridge:
    def __init__(self, events_url: str = "http://127.0.0.1:8000/events") -> None:
        self.events_url = events_url

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
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.post(self.events_url, json=payload)
            response.raise_for_status()
            result = response.json()
        return self._adapt_action(result.get("action"), observation_payload)

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
        async with httpx.AsyncClient(timeout=3.0) as client:
            response = await client.post(self.events_url, json=payload)
            response.raise_for_status()

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
