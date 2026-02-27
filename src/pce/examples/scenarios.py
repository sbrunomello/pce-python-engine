"""Examples aligned with whitepaper requirements."""

from __future__ import annotations


def financial_event_example() -> dict[str, object]:
    """Financial agent example: cashflow and budget event."""
    return {
        "event_type": "cashflow.update",
        "source": "finance-agent",
        "payload": {
            "domain": "finance",
            "cash_in": 1200.0,
            "cash_out": 830.0,
            "budget_remaining": 370.0,
            "tags": ["budget-aware", "strategic", "efficient", "safe"],
        },
    }


def autonomous_event_example() -> dict[str, object]:
    """Simple autonomous robot example: sensor + goals event."""
    return {
        "event_type": "robot.sensor",
        "source": "robot-core",
        "payload": {
            "domain": "autonomous",
            "obstacle_distance_m": 1.8,
            "battery_level": 0.64,
            "goal": "reach_waypoint_A",
            "tags": ["safe", "strategic"],
        },
    }
