from __future__ import annotations

OBSERVATION_EVENT_TYPE = "observation.robotics.sensors.v1"
FEEDBACK_EVENT_TYPE = "feedback.robotics.step_result.v1"


def build_observation_payload(
    world_state: dict[str, object], sensors: dict[str, int]
) -> dict[str, object]:
    world = world_state["world"]
    robot = world["robot"]
    goal = world["goal"]
    dx = int(goal["x"]) - int(robot["x"])
    dy = int(goal["y"]) - int(robot["y"])
    return {
        "tick": int(world_state["tick"]),
        "episode_id": str(world_state["episode_id"]),
        "robot": {
            "x": int(robot["x"]),
            "y": int(robot["y"]),
            "dir": int(robot["dir"]),
            "energy": float(robot["energy"]),
        },
        "goal": {"x": int(goal["x"]), "y": int(goal["y"])},
        "sensors": {
            "front": int(sensors["front"]),
            "front_left": int(sensors["front_left"]),
            "front_right": int(sensors["front_right"]),
            "left": int(sensors["left"]),
            "right": int(sensors["right"]),
        },
        "delta": {"dx": dx, "dy": dy, "manhattan": abs(dx) + abs(dy)},
    }


def build_feedback_payload(world_state: dict[str, object]) -> dict[str, object]:
    metrics = world_state["metrics"]
    return {
        "tick": int(world_state["tick"]),
        "episode_id": str(world_state["episode_id"]),
        "reward": float(metrics["reward"]),
        "done": bool(metrics["done"]),
        "reason": metrics["reason"],
        "distance": int(metrics["distance"]),
        "collisions": int(metrics["collisions"]),
    }
