"""Dataset build pipeline from candles using EPL + ISI for feature parity with runtime."""

from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
from typing import Any

from trader_plugins.config import TraderConfig
from trader_plugins.epl import TraderEPL
from trader_plugins.isi import TraderISI
from trader_plugins.types import Candle


def build_feature_dataset_from_candles(
    candles_csv: Path,
    symbols: list[str],
    timeframe: str,
    lookback_max: int,
    out_path: Path,
    config: TraderConfig | None = None,
) -> dict[str, Any]:
    """Build deterministic training dataset from candle feed and ISI features."""
    cfg = config or TraderConfig()
    epl = TraderEPL()
    isi = TraderISI(maxlen=max(lookback_max, 200))
    wanted = {s.strip() for s in symbols if s.strip()}

    rows: list[dict[str, Any]] = []
    with candles_csv.open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            if row.get("timeframe") != timeframe:
                continue
            symbol = str(row.get("symbol", ""))
            if wanted and symbol not in wanted:
                continue
            candle = Candle(
                symbol=symbol,
                timeframe=str(row["timeframe"]),
                timestamp=_parse_ts(str(row["timestamp"])),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row["volume"]),
            )
            evt = epl.ingest(candle)
            integrated = isi.integrate(evt)
            features = integrated["features"]
            rows.append(
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "timestamp": integrated["timestamp"],
                    "open": candle.open,
                    "high": candle.high,
                    "low": candle.low,
                    "close": candle.close,
                    "volume": candle.volume,
                    "ret_1": features.get("ret_1", 0.0),
                    "ret_6": features.get("ret_6", 0.0),
                    "atr": features.get("atr", 0.0),
                    "rsi": features.get("rsi", 50.0),
                    "ema_slope": features.get("ema_slope", 0.0),
                    "bb_width": features.get("bb_width", 0.0),
                    "adx_like": features.get("adx_like", 0.0),
                    "integrity_ok": bool(features.get("integrity_ok", True)),
                    "regime_4h": None,
                    "feature_version": cfg.feature_version,
                }
            )

    dataset_hash = _compute_dataset_hash(rows, cfg.feature_version)
    for row in rows:
        row["dataset_hash"] = dataset_hash

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = list(rows[0].keys()) if rows else [
            "symbol", "timeframe", "timestamp", "open", "high", "low", "close", "volume",
            "ret_1", "ret_6", "atr", "rsi", "ema_slope", "bb_width", "adx_like", "integrity_ok",
            "regime_4h", "feature_version", "dataset_hash"
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return {
        "rows": len(rows),
        "symbols": sorted({row["symbol"] for row in rows}),
        "timeframe": timeframe,
        "feature_version": cfg.feature_version,
        "dataset_hash": dataset_hash,
        "out_path": str(out_path),
    }


def _parse_ts(value: str):
    from datetime import datetime

    return datetime.fromisoformat(value)


def _compute_dataset_hash(rows: list[dict[str, Any]], feature_version: str) -> str:
    norm = []
    for row in rows:
        base = {k: row[k] for k in row.keys() if k != "dataset_hash"}
        norm.append(base)
    payload = json.dumps({"feature_version": feature_version, "rows": norm}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
