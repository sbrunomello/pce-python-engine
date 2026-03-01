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
class TradeOption:
    """Candidate action evaluated during deliberation."""

    option_type: str
    expected_value: float
    risk: float
    cost: float
    quality: float
    consistency: float
    final_score: float
    rationale: str


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
    value_policy_version: str
    gate_results: list[dict[str, Any]]
    entry_price: float = 0.0
    stop_price: float = 0.0
    take_price: float = 0.0
    risk_R: float = 0.0
    expected_R: float = 0.0
    invalidation_reason: str = ""
    time_horizon: str = ""
    value_breakdown: dict[str, Any] = field(default_factory=dict)
    alternatives: list[TradeOption] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class FillResult:
    """Execution fill/skipped result normalized as payload."""

    event_type: str
    payload: dict[str, Any]
    source: str = "trader/ao"
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
