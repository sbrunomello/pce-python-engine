"""AFS layer: robust labeling, lightweight model training, walk-forward metrics, and drift checks."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from statistics import mean
from typing import Any

from trader_plugins.config import TraderConfig


FEATURE_COLUMNS = ["ret_1", "ret_6", "atr", "rsi", "ema_slope", "bb_width", "adx_like"]


@dataclass(slots=True)
class LabelingConfig:
    """Versioned triple-barrier configuration."""

    version: str
    horizon: int
    tp_atr_mult: float
    sl_atr_mult: float


@dataclass(slots=True)
class SimpleModel:
    """Distance-to-centroid classifier with uncertainty estimate."""

    version: str
    pos_centroid: dict[str, float]
    neg_centroid: dict[str, float]
    train_score: float
    feature_version: str
    label_version: str

    def predict(self, features: dict[str, float]) -> tuple[float, float]:
        pos = _distance(features, self.pos_centroid)
        neg = _distance(features, self.neg_centroid)
        denom = max(1e-9, pos + neg)
        p_win = 1.0 - (pos / denom)
        uncertainty = abs(0.5 - p_win) * -2 + 1
        return max(0.0, min(1.0, p_win)), max(0.0, min(1.0, uncertainty))


def triple_barrier_labels_from_ohlc(
    rows: list[dict[str, float]],
    *,
    config: LabelingConfig,
) -> list[str]:
    """Label sequence using high/low path and ATR-based dynamic barriers."""
    labels = ["NONE"] * len(rows)
    for idx, row in enumerate(rows):
        entry = float(row.get("close", 0.0))
        atr = float(row.get("atr", 0.0))
        if entry <= 0 or atr <= 0:
            continue
        tp = entry + config.tp_atr_mult * atr
        sl = entry - config.sl_atr_mult * atr
        end = min(len(rows), idx + config.horizon + 1)
        tag = "NONE"
        for nxt in range(idx + 1, end):
            high = float(rows[nxt].get("high", rows[nxt].get("close", 0.0)))
            low = float(rows[nxt].get("low", rows[nxt].get("close", 0.0)))
            if high >= tp:
                tag = "TP_FIRST"
                break
            if low <= sl:
                tag = "SL_FIRST"
                break
        labels[idx] = tag
    return labels


class TraderAFS:
    """Model trainer/registry manager with walk-forward validation."""

    def __init__(self, config: TraderConfig) -> None:
        self._config = config
        self._config.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def train(
        self,
        rows: list[dict[str, float]],
        labels: list[str],
        *,
        dataset_hash: str,
        feature_version: str,
        label_version: str,
    ) -> dict[str, Any]:
        usable = [(x, y) for x, y in zip(rows, labels, strict=False) if y in {"TP_FIRST", "SL_FIRST"}]
        if len(usable) < self._config.min_train_samples:
            return {"trained": False, "reason": "insufficient_samples"}

        metrics = self._walk_forward(usable, folds=max(2, self._config.walk_forward_folds))
        aggregate = metrics["aggregate_metrics"]

        pos = [x for x, y in usable if y == "TP_FIRST"]
        neg = [x for x, y in usable if y == "SL_FIRST"]
        if not pos or not neg:
            return {"trained": False, "reason": "single_class_only"}

        version = f"model-{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}"
        model = SimpleModel(version, _centroid(pos), _centroid(neg), float(aggregate["accuracy"]), feature_version, label_version)
        model_path = self._config.artifacts_dir / f"{version}.json"
        model_path.write_text(json.dumps(asdict(model), ensure_ascii=False, indent=2), encoding="utf-8")

        status = "candidate"
        if (
            float(aggregate["accuracy"]) >= self._config.promotion_min_accuracy
            and float(aggregate["brier"]) <= self._config.promotion_max_brier
            and float(aggregate["coverage"]) >= self._config.promotion_min_coverage
        ):
            status = "approved"

        return {
            "trained": True,
            "version": version,
            "model_path": str(model_path),
            "status": status,
            "dataset_hash": dataset_hash,
            "feature_version": feature_version,
            "label_version": label_version,
            "fold_metrics": metrics["fold_metrics"],
            "aggregate_metrics": aggregate,
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
            feature_version=str(payload.get("feature_version", self._config.feature_version)),
            label_version=str(payload.get("label_version", self._config.label_version)),
        )

    def drift_check(self, recent_outcomes: list[float], baseline: float) -> dict[str, object]:
        if not recent_outcomes:
            return {"flag": False, "reason": "no_recent_outcomes"}
        current = mean(recent_outcomes)
        drift = baseline - current
        return {"flag": drift > self._config.drift_drop_threshold, "baseline": baseline, "current": current, "drift": drift}

    def _walk_forward(self, usable: list[tuple[dict[str, float], str]], folds: int) -> dict[str, Any]:
        n = len(usable)
        fold_size = max(4, n // (folds + 1))
        fold_metrics: list[dict[str, float | int]] = []
        for fold_idx in range(folds):
            train_end = fold_size * (fold_idx + 1)
            val_end = min(n, train_end + fold_size)
            train_set = usable[:train_end]
            val_set = usable[train_end:val_end]
            if len(train_set) < 10 or len(val_set) < 4:
                continue
            pos = [x for x, y in train_set if y == "TP_FIRST"]
            neg = [x for x, y in train_set if y == "SL_FIRST"]
            if not pos or not neg:
                continue
            model = SimpleModel("wf", _centroid(pos), _centroid(neg), 0.0, self._config.feature_version, self._config.label_version)
            fold_metrics.append(_compute_metrics(model, val_set, threshold=self._config.p_win_threshold))

        if not fold_metrics:
            return {
                "fold_metrics": [],
                "aggregate_metrics": {"accuracy": 0.0, "precision_tp": 0.0, "recall_tp": 0.0, "brier": 1.0, "coverage": 0.0, "expectancy_r": -1.0},
            }

        keys = ["accuracy", "precision_tp", "recall_tp", "brier", "coverage", "expectancy_r"]
        aggregate = {k: float(mean([float(m[k]) for m in fold_metrics])) for k in keys}
        return {"fold_metrics": fold_metrics, "aggregate_metrics": aggregate}


def _compute_metrics(model: SimpleModel, val_set: list[tuple[dict[str, float], str]], threshold: float) -> dict[str, float | int]:
    preds: list[tuple[float, str]] = []
    for features, label in val_set:
        p_win, _ = model.predict(features)
        preds.append((p_win, label))

    tp = fp = fn = tn = 0
    brier_acc = 0.0
    covered = 0
    expectancy = 0.0
    for p_win, label in preds:
        y = 1 if label == "TP_FIRST" else 0
        pred = 1 if p_win >= 0.5 else 0
        if pred == 1 and y == 1:
            tp += 1
        elif pred == 1 and y == 0:
            fp += 1
        elif pred == 0 and y == 1:
            fn += 1
        else:
            tn += 1
        brier_acc += (p_win - y) ** 2
        if p_win >= threshold:
            covered += 1
            expectancy += 1.5 if y == 1 else -1.0

    total = len(preds)
    accuracy = (tp + tn) / max(total, 1)
    precision = tp / max(tp + fp, 1)
    recall = tp / max(tp + fn, 1)
    brier = brier_acc / max(total, 1)
    coverage = covered / max(total, 1)
    expectancy_r = expectancy / max(covered, 1)
    return {
        "samples": total,
        "accuracy": accuracy,
        "precision_tp": precision,
        "recall_tp": recall,
        "brier": brier,
        "coverage": coverage,
        "expectancy_r": expectancy_r,
    }


def _distance(a: dict[str, float], b: dict[str, float]) -> float:
    keys = set(a).intersection(b)
    if not keys:
        return 1.0
    return sum(abs(float(a[k]) - float(b[k])) for k in keys) / len(keys)


def _centroid(rows: list[dict[str, float]]) -> dict[str, float]:
    keys = set().union(*[set(item.keys()) for item in rows])
    return {key: sum(float(item.get(key, 0.0)) for item in rows) / len(rows) for key in keys}
