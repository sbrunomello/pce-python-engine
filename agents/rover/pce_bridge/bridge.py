from __future__ import annotations

import os
from typing import Any

import httpx

from .contracts import FEEDBACK_EVENT_TYPE, OBSERVATION_EVENT_TYPE


class PCEBridge:
    def __init__(
        self,
        events_url: str | None = None,
        timeout_seconds: float = 0.25,
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
            action = result.get("action")
            if isinstance(action, dict) and isinstance(action.get("type"), str):
                return {
                    "action": action,
                    "metadata": result.get("metadata", {}),
                    "trace_id": trace_id,
                }
            return {"action": self._fallback_action(observation_payload), "metadata": {}, "trace_id": trace_id}
        except (httpx.HTTPError, ValueError):
            # Keep the simulation fluid even when the decision endpoint is slow/unavailable.
            return {"action": self._fallback_action(observation_payload), "metadata": {}, "trace_id": trace_id}

    async def send_feedback(self, feedback_payload: dict[str, Any]) -> dict[str, Any]:
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
        body = response.json()
        return body if isinstance(body, dict) else {}

    def _fallback_action(self, observation_payload: dict[str, Any]) -> dict[str, Any]:
        sensors = observation_payload["sensors"]
        if int(sensors["front"]) > 0:
            return {"type": "robot.move_forward", "amount": 1}
        if int(sensors["front_left"]) > int(sensors["front_right"]):
            return {"type": "robot.turn_left"}
        return {"type": "robot.turn_right"}
