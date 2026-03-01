"""AFS layer: labeling, lightweight model training, registry, and drift checks."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from statistics import mean

from trader_plugins.config import TraderConfig


def triple_barrier_labels(closes: list[float], horizon: int = 6, tp: float = 0.015, sl: float = 0.01) -> list[str]:
    """Label closes with TP_FIRST / SL_FIRST / NONE using fixed horizon."""
    labels = ["NONE"] * len(closes)
    for idx in range(len(closes)):
        entry = closes[idx]
        if entry <= 0:
            continue
        up = entry * (1 + tp)
        down = entry * (1 - sl)
        end = min(len(closes), idx + horizon + 1)
        tag = "NONE"
        for j in range(idx + 1, end):
            if closes[j] >= up:
                tag = "TP_FIRST"
                break
            if closes[j] <= down:
                tag = "SL_FIRST"
                break
        labels[idx] = tag
    return labels


@dataclass(slots=True)
class SimpleModel:
    """Distance-to-centroid classifier with uncertainty estimate."""

    version: str
    pos_centroid: dict[str, float]
    neg_centroid: dict[str, float]
    train_score: float

    def predict(self, features: dict[str, float]) -> tuple[float, float]:
        pos = _distance(features, self.pos_centroid)
        neg = _distance(features, self.neg_centroid)
        denom = max(1e-9, pos + neg)
        p_win = 1.0 - (pos / denom)
        uncertainty = abs(0.5 - p_win) * -2 + 1
        return max(0.0, min(1.0, p_win)), max(0.0, min(1.0, uncertainty))


class TraderAFS:
    """Model trainer/registry manager with walk-forward validation."""

    def __init__(self, config: TraderConfig) -> None:
        self._config = config
        self._config.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def train(self, rows: list[dict[str, float]], labels: list[str]) -> dict[str, object]:
        usable = [(x, y) for x, y in zip(rows, labels, strict=False) if y in {"TP_FIRST", "SL_FIRST"}]
        if len(usable) < 20:
            return {"trained": False, "reason": "insufficient_samples"}

        split = max(10, int(len(usable) * 0.7))
        train_set = usable[:split]
        val_set = usable[split:]

        pos = [x for x, y in train_set if y == "TP_FIRST"]
        neg = [x for x, y in train_set if y == "SL_FIRST"]
        if not pos or not neg:
            return {"trained": False, "reason": "single_class_only"}

        version = f"model-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        model = SimpleModel(version, _centroid(pos), _centroid(neg), 0.0)
        score = self._validate(model, val_set)
        model.train_score = score

        model_path = self._config.artifacts_dir / f"{version}.json"
        model_path.write_text(json.dumps(asdict(model), ensure_ascii=False, indent=2), encoding="utf-8")

        return {
            "trained": True,
            "version": version,
            "train_score": score,
            "model_path": str(model_path),
            "status": "candidate" if score < 0.55 else "approved",
        }

    def load_model(self, version: str) -> SimpleModel | None:
        path = self._config.artifacts_dir / f"{version}.json"
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return SimpleModel(
            version=str(payload["version"]),
            pos_centroid={str(k): float(v) for k, v in payload["pos_centroid"].items()},
            neg_centroid={str(k): float(v) for k, v in payload["neg_centroid"].items()},
            train_score=float(payload["train_score"]),
        )

    def drift_check(self, recent_outcomes: list[float], baseline: float) -> dict[str, object]:
        if not recent_outcomes:
            return {"flag": False, "reason": "no_recent_outcomes"}
        current = mean(recent_outcomes)
        drift = baseline - current
        return {"flag": drift > 0.12, "baseline": baseline, "current": current, "drift": drift}

    @staticmethod
    def _validate(model: SimpleModel, val_set: list[tuple[dict[str, float], str]]) -> float:
        if not val_set:
            return 0.5
        hits = 0
        for features, label in val_set:
            p_win, _ = model.predict(features)
            pred = "TP_FIRST" if p_win >= 0.5 else "SL_FIRST"
            if pred == label:
                hits += 1
        return hits / len(val_set)


def _distance(a: dict[str, float], b: dict[str, float]) -> float:
    keys = set(a).intersection(b)
    if not keys:
        return 1.0
    return sum(abs(float(a[k]) - float(b[k])) for k in keys) / len(keys)


def _centroid(rows: list[dict[str, float]]) -> dict[str, float]:
    keys = set().union(*[set(item.keys()) for item in rows])
    return {key: sum(float(item.get(key, 0.0)) for item in rows) / len(rows) for key in keys}
