"""EPL layer: market ingest normalization and data integrity checks."""

from __future__ import annotations

from datetime import timedelta
from hashlib import sha256

from trader_plugins.types import Candle, InternalEvent

_TIMEFRAME_DELTA = {"1h": timedelta(hours=1), "4h": timedelta(hours=4)}


class TraderEPL:
    """Normalizes candles and emits idempotent internal events."""

    def __init__(self) -> None:
        self._last_ts: dict[tuple[str, str], object] = {}
        self._seen_keys: set[str] = set()

    def ingest(self, candle: Candle) -> InternalEvent:
        key = (candle.symbol, candle.timeframe)
        previous = self._last_ts.get(key)
        delta = _TIMEFRAME_DELTA.get(candle.timeframe)

        issues: list[str] = []
        if previous is not None and candle.timestamp < previous:
            issues.append("out_of_order")
        if previous is not None and delta is not None and candle.timestamp - previous > delta * 2:
            issues.append("gap_detected")

        idempotency_key = sha256(
            (
                f"{candle.symbol}|{candle.timeframe}|{candle.timestamp.isoformat()}|"
                f"{candle.open:.8f}|{candle.high:.8f}|{candle.low:.8f}|{candle.close:.8f}|{candle.volume:.8f}"
            ).encode("utf-8")
        ).hexdigest()
        if idempotency_key in self._seen_keys:
            issues.append("duplicate")
        else:
            self._seen_keys.add(idempotency_key)

        self._last_ts[key] = candle.timestamp

        return InternalEvent(
            event_type="market.candle",
            payload={
                "symbol": candle.symbol,
                "timeframe": candle.timeframe,
                "timestamp": candle.timestamp.isoformat(),
                "open": candle.open,
                "high": candle.high,
                "low": candle.low,
                "close": candle.close,
                "volume": candle.volume,
                "idempotency_key": idempotency_key,
                "integrity_issues": issues,
                "integrity_ok": len(issues) == 0,
            },
            source="trader/epl",
        )
