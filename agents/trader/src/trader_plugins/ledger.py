"""Append-only event ledger for trader runtime audit and replay support."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from trader_plugins.events import EventEnvelope


class TraderEventLedger:
    """Simple append-only JSONL ledger with tail and lightweight query."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> Path:
        return self._path

    def append(self, envelope: EventEnvelope) -> None:
        """Append an envelope as a single immutable JSON line."""
        with self._path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(envelope.to_dict(), ensure_ascii=False) + "\n")

    def tail(self, limit: int) -> list[dict[str, Any]]:
        """Return the latest N events from the ledger."""
        if limit <= 0 or not self._path.exists():
            return []
        with self._path.open("r", encoding="utf-8") as handle:
            rows = handle.readlines()
        return [json.loads(line) for line in rows[-limit:] if line.strip()]

    def query(
        self,
        *,
        event_type: str | None = None,
        symbol: str | None = None,
        since_ts: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Filter events by type/symbol/since_ts. v0 linear scan."""
        if not self._path.exists():
            return []

        out: list[dict[str, Any]] = []
        with self._path.open("r", encoding="utf-8") as handle:
            for raw in handle:
                if not raw.strip():
                    continue
                event = json.loads(raw)
                if event_type and event.get("event_type") != event_type:
                    continue
                if since_ts and str(event.get("ts", "")) < since_ts:
                    continue
                if symbol:
                    payload = event.get("payload", {})
                    if not isinstance(payload, dict) or payload.get("symbol") != symbol:
                        continue
                out.append(event)

        if limit is not None and limit > 0:
            return out[-limit:]
        return out
