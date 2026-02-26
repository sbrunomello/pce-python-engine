from __future__ import annotations

from collections import deque


class RingBuffer:
    def __init__(self, max_size: int = 300) -> None:
        self._items: deque[dict[str, object]] = deque(maxlen=max_size)

    def append(self, item: dict[str, object]) -> None:
        self._items.append(item)

    def items(self) -> list[dict[str, object]]:
        return list(self._items)
