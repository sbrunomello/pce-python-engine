import httpx

from agents.rover.pce_bridge.bridge import PCEBridge


class FailingClient:
    async def post(self, *args, **kwargs):
        raise httpx.ReadTimeout("slow")


def test_decide_falls_back_when_pce_is_slow() -> None:
    bridge = PCEBridge()
    bridge._client = FailingClient()  # type: ignore[assignment]

    observation = {
        "sensors": {
            "front": 0,
            "front_left": 2,
            "front_right": 1,
            "left": 1,
            "right": 1,
        },
        "delta": {"dx": 0, "dy": 0},
    }

    import asyncio

    action = asyncio.run(bridge.decide(observation, trace_id="t-1"))
    assert action == {"type": "robot.turn_left"}
