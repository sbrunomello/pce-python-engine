"""Controlled bus for bounded inter-agent communication."""

from __future__ import annotations

from collections import defaultdict, deque

from pce_os.agents.base import AgentMessage


class AgentBus:
    """Queue with turn limit, dedupe, and per-agent ingress rate limiting."""

    def __init__(self, *, max_turns: int = 6, per_agent_limit: int = 4) -> None:
        self.max_turns = max_turns
        self.per_agent_limit = per_agent_limit
        self._queue: deque[AgentMessage] = deque()
        self._seen: set[str] = set()

    def enqueue(self, message: AgentMessage) -> bool:
        """Enqueue message once using a deterministic dedupe key."""
        dedupe_key = message.dedupe_key or self._message_key(message)
        if dedupe_key in self._seen:
            return False
        self._seen.add(dedupe_key)
        self._queue.append(message)
        return True

    def dequeue_for_all(self) -> dict[str, list[AgentMessage]]:
        """Drain one turn and fan-in messages grouped by destination agent."""
        grouped: dict[str, list[AgentMessage]] = defaultdict(list)
        while self._queue:
            message = self._queue.popleft()
            inbox = grouped[message.to_agent]
            if len(inbox) >= self.per_agent_limit:
                continue
            inbox.append(message)
        return grouped

    def __len__(self) -> int:
        return len(self._queue)

    @staticmethod
    def _message_key(message: AgentMessage) -> str:
        content_key = "|".join(f"{k}:{message.content[k]}" for k in sorted(message.content.keys()))
        return f"{message.from_agent}->{message.to_agent}:{message.kind}:{content_key}"
