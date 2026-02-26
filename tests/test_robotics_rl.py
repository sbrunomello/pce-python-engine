from fastapi.testclient import TestClient

from api.main import app
from pce.robotics.rl import build_state_key, q_learning_update


def _observation_event() -> dict[str, object]:
    return {
        "event_type": "observation.robotics.sensors.v1",
        "source": "agents.rover",
        "payload": {
            "domain": "robotics",
            "tags": ["observation", "sensors"],
            "tick": 1,
            "episode_id": "ep-test",
            "robot": {"x": 1, "y": 1, "dir": 1, "energy": 100.0},
            "goal": {"x": 4, "y": 1},
            "sensors": {
                "front": 4,
                "front_left": 2,
                "front_right": 2,
                "left": 1,
                "right": 3,
            },
            "delta": {"dx": 3, "dy": 0, "manhattan": 3},
        },
    }


def test_robotics_state_key_discretization() -> None:
    key = build_state_key(
        {
            "robot": {"dir": 1},
            "delta": {"dx": 9, "dy": 0},
            "sensors": {"front": 4, "left": 1, "right": 2},
        }
    )
    assert key == "d1_dx1_dy0_f3_l1_r2"


def test_q_learning_update_formula() -> None:
    updated = q_learning_update(current_q=0.2, reward=1.0, max_next_q=0.8, alpha=0.2, gamma=0.95)
    assert round(updated, 4) == 0.512


def test_robotics_observation_then_feedback_updates_q_table() -> None:
    client = TestClient(app)
    clear = client.post("/agents/rover/control/clear_policy")
    assert clear.status_code == 200

    observation_response = client.post("/events", json=_observation_event())
    assert observation_response.status_code == 200
    observation_body = observation_response.json()
    assert observation_body["action_type"] == "robotics.action"
    assert observation_body["action"]["type"].startswith("robot.")

    feedback_payload = {
        "event_type": "feedback.robotics.step_result.v1",
        "source": "agents.rover",
        "payload": {
            "domain": "robotics",
            "tags": ["feedback", "step_result"],
            "tick": 2,
            "episode_id": "ep-test",
            "reward": 1.0,
            "done": False,
            "reason": "running",
            "distance": 2,
            "collisions": 0,
            "next_observation": {
                "tick": 2,
                "episode_id": "ep-test",
                "robot": {"x": 2, "y": 1, "dir": 2, "energy": 99.0},
                "goal": {"x": 4, "y": 1},
                "sensors": {
                    "front": 1,
                    "front_left": 2,
                    "front_right": 2,
                    "left": 1,
                    "right": 3,
                },
                "delta": {"dx": 2, "dy": 0, "manhattan": 2},
            },
        },
    }
    feedback_response = client.post("/events", json=feedback_payload)
    assert feedback_response.status_code == 200
    feedback_body = feedback_response.json()
    assert feedback_body["updated"] is True
    assert feedback_body["q_update"]["next_state_key"] != feedback_body["q_update"]["state_key"]
    assert float(feedback_body["q_update"]["new_q"]) > float(feedback_body["q_update"]["old_q"])
