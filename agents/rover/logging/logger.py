from __future__ import annotations

from datetime import UTC, datetime

from .ring_buffer import RingBuffer


class StructuredLogger:
    def __init__(self, buffer: RingBuffer) -> None:
        self.buffer = buffer

    def log(
        self,
        level: str,
        component: str,
        message: str,
        trace_id: str,
        data: dict[str, object] | None = None,
    ) -> dict[str, object]:
        entry = {
            "type": "log",
            "level": level,
            "ts": datetime.now(tz=UTC).isoformat(),
            "component": component,
            "message": message,
            "trace_id": trace_id,
            "data": data or {},
        }
        self.buffer.append(entry)
        return entry
