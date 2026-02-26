import pytest

from pce.epl.processor import EventProcessingLayer


def test_epl_validates_event_schema() -> None:
    layer = EventProcessingLayer("docs/contracts/events.schema.json")
    event = layer.ingest(
        {
            "event_type": "cashflow.update",
            "source": "finance-agent",
            "payload": {"domain": "finance", "tags": ["safe"]},
        }
    )
    assert event.event_type == "cashflow.update"


def test_epl_rejects_invalid_event() -> None:
    layer = EventProcessingLayer("docs/contracts/events.schema.json")
    with pytest.raises(ValueError):
        layer.ingest({"event_type": "x", "source": "y", "payload": {"domain": "finance"}})
