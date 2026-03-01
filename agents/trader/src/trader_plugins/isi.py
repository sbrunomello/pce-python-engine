"""ISI layer: market state integration and feature generation."""

from __future__ import annotations

from collections import defaultdict, deque
from statistics import mean

from trader_plugins.types import InternalEvent


class TraderISI:
    """Maintains rolling state for each symbol/timeframe and computes indicators."""

    def __init__(self, maxlen: int = 1200) -> None:
        self._candles: dict[tuple[str, str], deque[dict[str, float]]] = defaultdict(lambda: deque(maxlen=maxlen))

    def integrate(self, event: InternalEvent) -> dict[str, object]:
        payload = event.payload
        symbol = str(payload["symbol"])
        timeframe = str(payload["timeframe"])

        series = self._candles[(symbol, timeframe)]
        series.append(
            {
                "open": float(payload["open"]),
                "high": float(payload["high"]),
                "low": float(payload["low"]),
                "close": float(payload["close"]),
                "volume": float(payload["volume"]),
            }
        )
        closes = [row["close"] for row in series]
        highs = [row["high"] for row in series]
        lows = [row["low"] for row in series]

        features = {
            "ret_1": _safe_ret(closes, 1),
            "ret_6": _safe_ret(closes, 6),
            "atr": _atr(highs, lows, closes, 14),
            "rsi": _rsi(closes, 14),
            "ema_slope": _ema_slope(closes, 12),
            "bb_width": _bb_width(closes, 20),
            "adx_like": _adx_like(highs, lows, closes, 14),
            "integrity_ok": bool(payload.get("integrity_ok", True)),
            "integrity_issues": list(payload.get("integrity_issues", [])),
            "last_close": closes[-1],
        }
        regime = _regime(features)

        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "features": features,
            "regime": regime,
            "timestamp": payload["timestamp"],
        }


def _safe_ret(closes: list[float], lookback: int) -> float:
    if len(closes) <= lookback:
        return 0.0
    prev = closes[-(lookback + 1)]
    if prev == 0:
        return 0.0
    return (closes[-1] / prev) - 1.0


def _atr(highs: list[float], lows: list[float], closes: list[float], period: int) -> float:
    if len(closes) < 2:
        return 0.0
    start = max(1, len(closes) - period)
    tr_values = []
    for idx in range(start, len(closes)):
        tr = max(
            highs[idx] - lows[idx],
            abs(highs[idx] - closes[idx - 1]),
            abs(lows[idx] - closes[idx - 1]),
        )
        tr_values.append(tr)
    return mean(tr_values) if tr_values else 0.0


def _rsi(closes: list[float], period: int) -> float:
    if len(closes) < period + 1:
        return 50.0
    gains = []
    losses = []
    for idx in range(len(closes) - period, len(closes)):
        diff = closes[idx] - closes[idx - 1]
        gains.append(max(0.0, diff))
        losses.append(max(0.0, -diff))
    avg_gain = mean(gains)
    avg_loss = mean(losses) if mean(losses) > 0 else 1e-9
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _ema_slope(closes: list[float], period: int) -> float:
    if not closes:
        return 0.0
    alpha = 2.0 / (period + 1.0)
    ema = closes[0]
    history: list[float] = []
    for value in closes:
        ema = alpha * value + (1.0 - alpha) * ema
        history.append(ema)
    if len(history) < 4:
        return 0.0
    base = history[-4]
    if base == 0:
        return 0.0
    return (history[-1] - base) / base


def _bb_width(closes: list[float], period: int) -> float:
    if len(closes) < period:
        return 0.0
    window = closes[-period:]
    mid = mean(window)
    variance = mean([(x - mid) ** 2 for x in window])
    stdev = variance**0.5
    if mid == 0:
        return 0.0
    return (4 * stdev) / mid


def _adx_like(highs: list[float], lows: list[float], closes: list[float], period: int) -> float:
    if len(closes) < period + 1:
        return 0.0
    changes = [abs(closes[idx] - closes[idx - 1]) for idx in range(len(closes) - period, len(closes))]
    atr = _atr(highs, lows, closes, period)
    if atr == 0:
        return 0.0
    return min(100.0, 10.0 * mean(changes) / atr)


def _regime(features: dict[str, float | bool | list[str]]) -> str:
    if not bool(features["integrity_ok"]):
        return "invalid"
    slope = float(features["ema_slope"])
    adx_like = float(features["adx_like"])
    if slope > 0 and adx_like >= 15:
        return "bull"
    if slope < 0 and adx_like >= 15:
        return "bear"
    return "sideways"
