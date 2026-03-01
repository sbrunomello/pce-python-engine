"""Configuration primitives for the Trader agent."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class RiskLimits:
    """Risk and guardrail constraints for demo trading."""

    risk_per_trade: float = 0.005
    daily_drawdown_limit: float = 0.02
    monthly_drawdown_limit: float = 0.10
    max_trades_per_day: int = 8
    max_trades_per_asset_day: int = 3


@dataclass(slots=True)
class TraderConfig:
    """Top-level configuration used by all layers."""

    symbols: list[str] = field(default_factory=lambda: ["BTCUSDT", "ETHUSDT", "SOLUSDT"])
    execution_timeframe: str = "1h"
    macro_timeframe: str = "4h"
    prediction_horizon_hours: int = 6
    train_window_months: int = 18
    retrain_days: int = 7
    drift_check_days: int = 1
    p_win_threshold: float = 0.60
    feature_version: str = "feat-v2"
    label_version: str = "lbl-tb-atr-v1"
    policy_version: str = "pol-bootstrap"
    model_auto_promote_approved_to_active: bool = False
    promotion_min_accuracy: float = 0.55
    promotion_max_brier: float = 0.23
    promotion_min_coverage: float = 0.05
    uncertainty_gate_normal: float = 0.50
    uncertainty_gate_cautious: float = 0.40
    uncertainty_gate_restricted: float = 0.30
    drift_drop_threshold: float = 0.12
    drift_recent_window: int = 30
    drift_threshold_step: float = 0.05
    drift_threshold_max: float = 0.85
    drift_risk_multiplier: float = 0.50
    walk_forward_folds: int = 3
    min_train_samples: int = 24
    label_horizon_candles: int = 6
    label_tp_atr_mult: float = 1.5
    label_sl_atr_mult: float = 1.0
    fee_bps: float = 8.0
    slippage_bps: float = 4.0
    starting_cash: float = 100_000.0
    artifacts_dir: Path = Path("agents/trader/artifacts")
    logs_dir: Path = Path("agents/trader/artifacts/logs")
    db_url: str = "sqlite:///./agents/trader/artifacts/trader_state.db"
    risk: RiskLimits = field(default_factory=RiskLimits)


def mode_from_ccif(ccif: float, *, locked: bool) -> str:
    """Return operational mode from CCI-F score and lock state."""
    if locked:
        return "locked"
    if ccif >= 0.85:
        return "normal"
    if ccif >= 0.70:
        return "cautious"
    if ccif >= 0.55:
        return "restricted"
    return "locked"
