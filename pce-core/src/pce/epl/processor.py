"""Event Processing Layer implementation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from pce.core.types import PCEEvent


class EventProcessingLayer:
    """Validates incoming events against JSON Schema."""

    def __init__(self, schema_path: str) -> None:
        schema = json.loads(Path(schema_path).read_text(encoding="utf-8"))
        self._validator = Draft202012Validator(schema)

    def ingest(self, raw_event: dict[str, Any]) -> PCEEvent:
        """Validate raw event and convert to internal event envelope."""
        errors = sorted(self._validator.iter_errors(raw_event), key=str)
        if errors:
            details = "; ".join(err.message for err in errors)
            raise ValueError(f"Invalid event payload: {details}")

        return PCEEvent(
            event_type=str(raw_event["event_type"]),
            source=str(raw_event["source"]),
            payload=dict(raw_event["payload"]),
        )
