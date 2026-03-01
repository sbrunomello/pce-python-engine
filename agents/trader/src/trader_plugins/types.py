"""Domain types for trader pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(slots=True)
class Candle:
    """Normalized OHLCV candle."""

    symbol: str
    timeframe: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(slots=True)
class TradePlan:
    """Audit-friendly trade plan produced by Decision Engine."""

    decision_id: str
    symbol: str
    action: str
    qty: float
    reason: str
    p_win: float
    uncertainty: float
    threshold: float
    mode: str
    gate_results: list[dict[str, Any]]
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FillResult:
    """Execution fill/skipped result normalized as payload."""

    event_type: str
    payload: dict[str, Any]
    source: str = "trader/ao"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
