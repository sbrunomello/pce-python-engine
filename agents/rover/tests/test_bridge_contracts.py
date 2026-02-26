from agents.rover.pce_bridge.contracts import build_observation_payload


def test_observation_payload_contract_keys_and_types() -> None:
    payload = build_observation_payload(
        {
            "tick": 1,
            "episode_id": "ep-1",
            "world": {
                "robot": {"x": 1, "y": 2, "dir": 0, "energy": 99.0},
                "goal": {"x": 4, "y": 5},
            },
        },
        {"front": 1, "front_left": 2, "front_right": 3, "left": 4, "right": 5},
    )

    assert payload["tick"] == 1
    assert isinstance(payload["episode_id"], str)
    assert isinstance(payload["robot"]["x"], int)
    assert isinstance(payload["robot"]["energy"], float)
    assert set(payload["sensors"].keys()) == {"front", "front_left", "front_right", "left", "right"}
    assert isinstance(payload["delta"]["manhattan"], int)
