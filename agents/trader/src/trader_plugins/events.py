"""Standard event envelope and event type constants for trader runtime."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4


EVENT_MARKET_CANDLE_CLOSED = "market.candle.closed"
EVENT_STATE_INTEGRATED = "state.integrated"
EVENT_DECISION_PLAN_CREATED = "decision.trade_plan.created"
EVENT_EXECUTION_FILLED = "execution.order.filled"
EVENT_EXECUTION_SKIPPED = "execution.skipped"
EVENT_METRICS_UPDATED = "metrics.updated"
EVENT_GUARDRAIL_LOCKED = "guardrail.locked"
EVENT_GUARDRAIL_UNLOCKED = "guardrail.unlocked"
EVENT_DATA_INTEGRITY_DEGRADED = "system.data_integrity.degraded"
EVENT_LEARNING_TRAIN_RUN_STARTED = "learning.train.run.started"
EVENT_LEARNING_TRAIN_RUN_COMPLETED = "learning.train.run.completed"
EVENT_LEARNING_MODEL_PROMOTED = "learning.model.promoted"
EVENT_LEARNING_MODEL_ROLLED_BACK = "learning.model.rolled_back"
EVENT_LEARNING_DRIFT_DETECTED = "learning.drift.detected"
EVENT_POLICY_UPDATED = "policy.updated"


@dataclass(slots=True)
class EventEnvelope:
    """Immutable event envelope for audit, replay and causal tracing."""

    event_type: str
    source: str
    payload: dict[str, Any]
    correlation_id: str
    causation_id: str | None = None
    actor: str | None = None
    version: int = 1
    event_id: str = field(default_factory=lambda: str(uuid4()))
    ts: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        """Serialize envelope to JSON-friendly dictionary."""
        return asdict(self)


def new_correlation_id() -> str:
    """Create stable correlation chain id."""
    return str(uuid4())
