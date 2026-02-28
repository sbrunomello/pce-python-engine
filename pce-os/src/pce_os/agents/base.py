"""Base agent contracts for deterministic multi-agent orchestration."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from pce.core.types import PCEEvent


@dataclass(slots=True)
class AgentMessage:
    """Message exchanged between agents through the controlled bus."""

    from_agent: str
    to_agent: str
    kind: str
    content: dict[str, Any] = field(default_factory=dict)
    dedupe_key: str = ""


@dataclass(slots=True)
class AgentInput:
    """Input passed to each agent during orchestration rounds."""

    event: PCEEvent
    twin_snapshot: dict[str, Any]
    incoming_messages: list[AgentMessage] = field(default_factory=list)
    correlation_id: str = ""
    decision_id: str = ""
    enable_llm: bool = False
    allow_llm_actions: bool = False


@dataclass(slots=True)
class AgentOutput:
    """Structured response from a domain agent."""

    proposed_actions: list[dict[str, Any]] = field(default_factory=list)
    messages: list[AgentMessage] = field(default_factory=list)
    risk_flags: list[str] = field(default_factory=list)
    questions: list[str] = field(default_factory=list)
    confidence: float = 0.5
    rationale: str = ""


class Agent(ABC):
    """Common protocol for all orchestrated agents."""

    name: str

    @abstractmethod
    def process(self, agent_input: AgentInput) -> AgentOutput:
        """Process one agent turn deterministically."""

