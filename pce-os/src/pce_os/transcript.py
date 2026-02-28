"""Transcript ring buffer helpers stored in pce_os state slice."""

from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from typing import Any

_TRANSCRIPT_KEY = "transcript"
_MAX_ITEMS = 500


def read_transcript(state: dict[str, object]) -> dict[str, Any]:
    """Return normalized transcript payload from state."""
    os_state = state.get("pce_os")
    if not isinstance(os_state, dict):
        return {"cursor": 0, "items": []}

    transcript = os_state.get(_TRANSCRIPT_KEY)
    if not isinstance(transcript, dict):
        return {"cursor": 0, "items": []}

    cursor = int(transcript.get("cursor", 0))
    raw_items = transcript.get("items", [])
    items = [item for item in raw_items if isinstance(item, dict)] if isinstance(raw_items, list) else []
    return {"cursor": cursor, "items": items}


def append_transcript_item(
    state: dict[str, object],
    *,
    kind: str,
    payload: dict[str, Any],
    correlation_id: str,
    decision_id: str = "",
    agent: str = "",
    ts: str | None = None,
) -> tuple[dict[str, object], dict[str, Any]]:
    """Append one transcript record, preserving max ring size."""
    next_state = deepcopy(state)
    os_state = next_state.get("pce_os")
    if not isinstance(os_state, dict):
        os_state = {}

    transcript = read_transcript(next_state)
    next_cursor = int(transcript["cursor"]) + 1
    item = {
        "cursor": next_cursor,
        "ts": ts or datetime.now(UTC).isoformat(),
        "kind": kind,
        "agent": agent,
        "payload": payload,
        "correlation_id": correlation_id,
        "decision_id": decision_id,
    }
    items = [*transcript["items"], item]
    if len(items) > _MAX_ITEMS:
        items = items[-_MAX_ITEMS:]

    os_state[_TRANSCRIPT_KEY] = {"cursor": next_cursor, "items": items}
    next_state["pce_os"] = os_state
    return next_state, item


def items_since(state: dict[str, object], cursor: int) -> list[dict[str, Any]]:
    """Return transcript items newer than cursor."""
    transcript = read_transcript(state)
    return [item for item in transcript["items"] if int(item.get("cursor", 0)) > cursor]
