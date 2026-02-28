import pytest
from pce.epl.processor import EventProcessingLayer


@pytest.fixture
def layer() -> EventProcessingLayer:
    return EventProcessingLayer("pce-core/docs/contracts/events.schema.json")


def test_os_event_schema_happy_path(layer: EventProcessingLayer) -> None:
    event = layer.ingest(
        {
            "event_type": "project.goal.defined",
            "source": "planner",
            "payload": {"domain": "os.robotics", "tags": ["goal"], "goal": "build rover"},
        }
    )
    assert event.event_type == "project.goal.defined"


def test_os_event_schema_invalid_event_type(layer: EventProcessingLayer) -> None:
    with pytest.raises(ValueError):
        layer.ingest(
            {
                "event_type": "invalid.os.type",
                "source": "planner",
                "payload": {"domain": "os.robotics", "tags": ["goal"]},
            }
        )
