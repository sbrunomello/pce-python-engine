"""Model registry lifecycle management for trader learning."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


class ModelRegistry:
    """In-memory helper around persisted model registry records."""

    def __init__(self, records: list[dict[str, Any]] | None = None) -> None:
        self.records = records or []

    def add_candidate(self, run: dict[str, Any], *, parent_version: str | None) -> dict[str, Any]:
        rec = {
            "model_version": run["version"],
            "status": run["status"],
            "created_at": datetime.now(UTC).isoformat(),
            "dataset_hash": run["dataset_hash"],
            "feature_version": run["feature_version"],
            "label_version": run["label_version"],
            "aggregate_metrics": run["aggregate_metrics"],
            "promotion_reason": "metrics_threshold_met" if run["status"] == "approved" else None,
            "demotion_reason": None,
            "parent_version": parent_version,
        }
        self.records.append(rec)
        return rec

    def set_active(self, model_version: str, *, reason: str) -> dict[str, Any] | None:
        target = None
        for rec in self.records:
            if rec.get("model_version") == model_version:
                rec["status"] = "active"
                rec["promotion_reason"] = reason
                target = rec
            elif rec.get("status") == "active":
                rec["status"] = "approved"
        return target

    def active(self) -> dict[str, Any] | None:
        for rec in reversed(self.records):
            if rec.get("status") == "active":
                return rec
        return None

    def previous_approved(self, exclude_version: str | None = None) -> dict[str, Any] | None:
        for rec in reversed(self.records):
            if rec.get("model_version") == exclude_version:
                continue
            if rec.get("status") in {"approved", "active"}:
                return rec
        return None

    def rollback(self, *, from_version: str | None, to_version: str, reason: str) -> dict[str, Any] | None:
        switched = self.set_active(to_version, reason="rollback")
        if from_version:
            for rec in self.records:
                if rec.get("model_version") == from_version:
                    rec["status"] = "approved"
                    rec["demotion_reason"] = reason
        return switched
