"""Versioned value policy for governed trader deliberation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass(slots=True)
class ValueWeights:
    """Weights used to compose final value score."""

    opportunity_weight: float
    risk_weight: float
    quality_weight: float
    consistency_weight: float
    cost_weight: float


@dataclass(slots=True)
class ValueThresholds:
    """Hard viability thresholds applied before selecting an option."""

    min_quality: float
    max_risk: float
    min_opportunity: float


@dataclass(slots=True)
class ValueModeModifier:
    """Mode-specific multipliers for caution/constraint."""

    opportunity_multiplier: float
    risk_multiplier: float
    quality_multiplier: float
    consistency_multiplier: float
    cost_multiplier: float


@dataclass(slots=True)
class ValuePolicy:
    """Complete and versioned policy driving decision scores."""

    value_policy_version: str
    weights: ValueWeights
    thresholds: ValueThresholds
    mode_modifiers: dict[str, ValueModeModifier]
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "value_policy_version": self.value_policy_version,
            "weights": {
                "opportunity_weight": self.weights.opportunity_weight,
                "risk_weight": self.weights.risk_weight,
                "quality_weight": self.weights.quality_weight,
                "consistency_weight": self.weights.consistency_weight,
                "cost_weight": self.weights.cost_weight,
            },
            "thresholds": {
                "min_quality": self.thresholds.min_quality,
                "max_risk": self.thresholds.max_risk,
                "min_opportunity": self.thresholds.min_opportunity,
            },
            "mode_modifiers": {
                mode: {
                    "opportunity_multiplier": mod.opportunity_multiplier,
                    "risk_multiplier": mod.risk_multiplier,
                    "quality_multiplier": mod.quality_multiplier,
                    "consistency_multiplier": mod.consistency_multiplier,
                    "cost_multiplier": mod.cost_multiplier,
                }
                for mode, mod in self.mode_modifiers.items()
            },
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ValuePolicy":
        weights = data.get("weights", {}) if isinstance(data.get("weights"), dict) else {}
        thresholds = data.get("thresholds", {}) if isinstance(data.get("thresholds"), dict) else {}
        mode_mods_raw = data.get("mode_modifiers", {}) if isinstance(data.get("mode_modifiers"), dict) else {}
        mode_mods: dict[str, ValueModeModifier] = {}
        for mode, mod in mode_mods_raw.items():
            if not isinstance(mod, dict):
                continue
            mode_mods[mode] = ValueModeModifier(
                opportunity_multiplier=float(mod.get("opportunity_multiplier", 1.0)),
                risk_multiplier=float(mod.get("risk_multiplier", 1.0)),
                quality_multiplier=float(mod.get("quality_multiplier", 1.0)),
                consistency_multiplier=float(mod.get("consistency_multiplier", 1.0)),
                cost_multiplier=float(mod.get("cost_multiplier", 1.0)),
            )
        if not mode_mods:
            mode_mods = default_value_policy("value-pol-fallback").mode_modifiers
        return cls(
            value_policy_version=str(data.get("value_policy_version", "value-pol-fallback")),
            weights=ValueWeights(
                opportunity_weight=float(weights.get("opportunity_weight", 0.35)),
                risk_weight=float(weights.get("risk_weight", 0.25)),
                quality_weight=float(weights.get("quality_weight", 0.20)),
                consistency_weight=float(weights.get("consistency_weight", 0.15)),
                cost_weight=float(weights.get("cost_weight", 0.05)),
            ),
            thresholds=ValueThresholds(
                min_quality=float(thresholds.get("min_quality", 0.35)),
                max_risk=float(thresholds.get("max_risk", 0.75)),
                min_opportunity=float(thresholds.get("min_opportunity", 0.25)),
            ),
            mode_modifiers=mode_mods,
            created_at=str(data.get("created_at", datetime.now(UTC).isoformat())),
        )


def default_value_policy(version: str = "value-pol-v1") -> ValuePolicy:
    """Return deterministic default value policy baseline."""

    return ValuePolicy(
        value_policy_version=version,
        weights=ValueWeights(0.35, 0.25, 0.20, 0.15, 0.05),
        thresholds=ValueThresholds(min_quality=0.35, max_risk=0.75, min_opportunity=0.25),
        mode_modifiers={
            "normal": ValueModeModifier(1.0, 1.0, 1.0, 1.0, 1.0),
            "cautious": ValueModeModifier(0.90, 1.15, 1.05, 1.05, 1.10),
            "restricted": ValueModeModifier(0.75, 1.35, 1.10, 1.10, 1.20),
            "locked": ValueModeModifier(0.0, 2.0, 1.2, 1.2, 1.5),
        },
    )
