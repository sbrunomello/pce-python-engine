"""Canonical domain types shared across PCE layers."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


@dataclass(slots=True)
class PCEEvent:
    """Immutable event envelope used by all layers."""

    event_type: str
    source: str
    payload: dict[str, Any]
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    event_id: str = field(default_factory=lambda: str(uuid4()))


@dataclass(slots=True)
class ActionPlan:
    """Decision Engine output consumed by Action Orchestrator."""

    action_type: str
    rationale: str
    priority: int
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ExecutionResult:
    """Action execution outcome used by AFS feedback loop."""

    action_type: str
    success: bool
    observed_impact: float
    notes: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
