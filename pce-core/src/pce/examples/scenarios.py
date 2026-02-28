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


def os_demo_events() -> list[dict[str, object]]:
    """Minimal PCE-OS workflow sequence for robotics digital twin demo."""
    return [
        {
            "event_type": "project.goal.defined",
            "source": "os-demo",
            "payload": {
                "domain": "os.robotics",
                "tags": ["goal"],
                "phase": "planning",
                "goal": "Build field-test rover",
            },
        },
        {
            "event_type": "budget.updated",
            "source": "os-demo",
            "payload": {
                "domain": "os.robotics",
                "tags": ["budget"],
                "budget_total": 5000.0,
                "budget_remaining": 5000.0,
            },
        },
        {
            "event_type": "part.candidate.added",
            "source": "os-demo",
            "payload": {
                "domain": "os.robotics",
                "tags": ["bom"],
                "component_id": "lidar-1",
                "name": "2D Lidar",
                "quantity": 1,
                "estimated_unit_cost": 650.0,
                "risk_level": "MEDIUM",
            },
        },
        {
            "event_type": "purchase.requested",
            "source": "os-demo",
            "payload": {
                "domain": "os.robotics",
                "tags": ["purchase"],
                "purchase_id": "po-001",
                "projected_cost": 650.0,
                "risk_level": "MEDIUM",
            },
        },
    ]
