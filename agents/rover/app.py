from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse

from .logging.logger import StructuredLogger
from .logging.ring_buffer import RingBuffer
from .pce_bridge.bridge import PCEBridge
from .pce_bridge.contracts import build_feedback_payload, build_observation_payload
from .world.world import GridWorld

ROBOT_NAME = "rover"
BASE_PATH = f"/agents/{ROBOT_NAME}"
WEB_DIR = Path(__file__).parent / "web"

router = APIRouter()


class RoverRuntime:
    def __init__(self) -> None:
        self.world = GridWorld()
        self.log_buffer = RingBuffer(max_size=500)
        self.logger = StructuredLogger(self.log_buffer)
        self.bridge = PCEBridge()
        self.clients: set[WebSocket] = set()
        self.task: asyncio.Task[None] | None = None
        self.running = False
        self.tick_rate_hz = 120
        # Render each simulation tick so the UI stays aligned with the runtime loop.
        self.frame_rate_hz = self.tick_rate_hz
        self.log_every = 1
        self.feedback_every = 2
        self.reward_window: list[float] = []
        self.window_size = 100
        self.attempts_total = 0
        self.episode_successes = 0
        self.failures_battery = 0
        self.failures_timeout = 0
        self.failures_collision = 0
        self.run_started_at: float | None = None
        self.total_run_seconds = 0.0

    async def start(self) -> None:
        if self.running:
            return
        self.running = True
        if self.run_started_at is None:
            self.run_started_at = time.monotonic()
        self.task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        if self.run_started_at is not None:
            self.total_run_seconds += time.monotonic() - self.run_started_at
            self.run_started_at = None
        self.running = False
        if not self.task:
            return
        if asyncio.current_task() is self.task:
            return
        if not self.task.done():
            self.task.cancel()
            try:
                await self.task
            except asyncio.CancelledError:
                pass
        self.task = None

    async def shutdown(self) -> None:
        await self.stop()
        await self.bridge.close()

    async def reset(self) -> None:
        await self.stop()
        self.world.reset()
        self.reward_window.clear()
        # A reset starts a brand-new runtime session timer.
        self.total_run_seconds = 0.0
        self.run_started_at = None
        await self.broadcast(self._init_payload())

    async def reset_stats(self) -> None:
        self.attempts_total = 0
        self.episode_successes = 0
        self.failures_battery = 0
        self.failures_timeout = 0
        self.failures_collision = 0

    async def _loop(self) -> None:
        try:
            render_every = max(1, int(self.tick_rate_hz / max(1, self.frame_rate_hz)))
            while self.running:
                snapshot = self.world.snapshot()
                sensors = self.world.sensors()
                observation = build_observation_payload(
                    snapshot,
                    {
                        "front": sensors.front,
                        "front_left": sensors.front_left,
                        "front_right": sensors.front_right,
                        "left": sensors.left,
                        "right": sensors.right,
                    },
                )
                trace_id = f"ep:{snapshot['episode_id']}/t:{snapshot['tick']}"
                decision = await self.bridge.decide(observation, trace_id)
                action = decision.get("action", {"type": "robot.stop"})
                if not isinstance(action, dict):
                    action = {"type": "robot.stop"}
                self.world.apply_action(action)
                state = self.world.snapshot()
                next_sensors = self.world.sensors()
                next_observation = build_observation_payload(
                    state,
                    {
                        "front": next_sensors.front,
                        "front_left": next_sensors.front_left,
                        "front_right": next_sensors.front_right,
                        "left": next_sensors.left,
                        "right": next_sensors.right,
                    },
                )

                if state["tick"] % self.feedback_every == 0 or bool(state["metrics"]["done"]):
                    feedback = build_feedback_payload(state)
                    feedback["next_observation"] = next_observation
                    feedback_result = await self.bridge.send_feedback(feedback)
                    decision["feedback"] = feedback_result

                self.reward_window.append(float(state["metrics"]["reward"]))
                if len(self.reward_window) > self.window_size:
                    self.reward_window.pop(0)

                if state["tick"] % self.log_every == 0:
                    log_item = self.logger.log(
                        level="info",
                        component="rover.loop",
                        message="tick_processed",
                        trace_id=trace_id,
                        data={
                            "sensors": observation["sensors"],
                            "action": action,
                            "reward": state["metrics"]["reward"],
                        },
                    )
                    await self.broadcast(log_item)

                if state["tick"] % render_every == 0 or bool(state["metrics"]["done"]):
                    await self.broadcast(self._frame_payload(action, decision))

                if bool(state["metrics"]["done"]):
                    reason = str(state["metrics"].get("reason", ""))
                    self.attempts_total += 1
                    if reason == "goal":
                        self.episode_successes += 1
                    elif reason == "battery_depleted":
                        self.failures_battery += 1
                    elif reason == "timeout":
                        self.failures_timeout += 1
                    elif reason == "collision":
                        self.failures_collision += 1

                    if self.running:
                        self.world.reset()
                        self.reward_window.clear()
                        await self.broadcast(self._init_payload())
                        continue
                    break

                await asyncio.sleep(1.0 / self.tick_rate_hz)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            self.logger.log(
                level="error",
                component="rover.loop",
                message="loop_failed",
                trace_id="runtime",
                data={"error": str(exc)},
            )
            self.running = False
        finally:
            if asyncio.current_task() is self.task:
                self.task = None

    def _init_payload(self) -> dict[str, Any]:
        run_seconds = self.total_run_seconds
        if self.run_started_at is not None:
            run_seconds += time.monotonic() - self.run_started_at
        return {
            "type": "init",
            "tick": self.world.metrics.tick,
            "episode_id": self.world.episode_id,
            "world": {
                "w": self.world.width,
                "h": self.world.height,
                "obstacles": [{"x": x, "y": y} for x, y in sorted(self.world.obstacles)],
                "robot": {
                    "x": self.world.robot.x,
                    "y": self.world.robot.y,
                    "dir": self.world.robot.direction,
                    "energy": self.world.robot.energy,
                },
                "goal": {"x": self.world.goal.x, "y": self.world.goal.y},
                "start": {"x": self.world.start[0], "y": self.world.start[1]},
            },
            "runtime": {
                "elapsed_seconds": run_seconds,
            },
            "logs": self.log_buffer.items(),
        }

    def _frame_payload(self, action: dict[str, Any], decision: dict[str, Any] | None = None) -> dict[str, Any]:
        state = self.world.snapshot()
        avg = sum(self.reward_window) / len(self.reward_window) if self.reward_window else 0.0
        decision_data = decision or {}
        metadata = decision_data.get("metadata", {}) if isinstance(decision_data, dict) else {}
        rl_meta = metadata.get("rl", {}) if isinstance(metadata, dict) else {}
        run_seconds = self.total_run_seconds
        if self.run_started_at is not None:
            run_seconds += time.monotonic() - self.run_started_at
        success_rate = self.episode_successes / max(1, self.attempts_total)

        return {
            "type": "frame",
            "tick": state["tick"],
            "episode_id": state["episode_id"],
            "world": state["world"],
            "metrics": {
                **state["metrics"],
                "avg_reward_window": avg,
                "running": self.running,
                "epsilon": rl_meta.get("epsilon"),
                "policy_mode": rl_meta.get("policy_mode"),
                "best_action": rl_meta.get("best_action"),
                "q_values": rl_meta.get("q", {}),
                "attempts_total": self.attempts_total,
                "successes": self.episode_successes,
                "failures_battery": self.failures_battery,
                "failures_timeout": self.failures_timeout,
                "failures_collision": self.failures_collision,
                "success_rate": success_rate,
                "elapsed_seconds": run_seconds,
            },
            "last_action": action,
        }

    async def broadcast(self, payload: dict[str, Any]) -> None:
        stale: list[WebSocket] = []
        for client in self.clients:
            try:
                await client.send_json(payload)
            except RuntimeError:
                stale.append(client)
        for client in stale:
            self.clients.discard(client)


runtime = RoverRuntime()


@router.on_event("shutdown")
async def shutdown_runtime() -> None:
    await runtime.shutdown()


@router.get(BASE_PATH + "/")
async def rover_ui() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html")


@router.get(BASE_PATH + "/app.js")
async def rover_js() -> FileResponse:
    return FileResponse(WEB_DIR / "app.js")


@router.get(BASE_PATH + "/styles.css")
async def rover_css() -> FileResponse:
    return FileResponse(WEB_DIR / "styles.css")


@router.post(BASE_PATH + "/control/start")
async def start() -> dict[str, object]:
    await runtime.start()
    await runtime.broadcast(runtime._init_payload())
    return {"status": "running", "tick": runtime.world.metrics.tick}


@router.post(BASE_PATH + "/control/stop")
async def stop() -> dict[str, object]:
    await runtime.stop()
    return {"status": "stopped", "tick": runtime.world.metrics.tick}


@router.post(BASE_PATH + "/control/reset")
async def reset() -> dict[str, object]:
    await runtime.reset()
    return {"status": "reset", "episode_id": runtime.world.episode_id}


@router.get(BASE_PATH + "/state")
async def state() -> dict[str, object]:
    return runtime._frame_payload({"type": "robot.stop"})


@router.websocket(BASE_PATH + "/ws")
async def websocket_endpoint(websocket: WebSocket) -> None:
    await websocket.accept()
    runtime.clients.add(websocket)
    await websocket.send_json(runtime._init_payload())
    await websocket.send_json(runtime._frame_payload({"type": "robot.stop"}))
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        runtime.clients.discard(websocket)
