"""Persistent latest-state storage for market snapshots.

Keeps candle-history, EMA, RSI, patterns, and key-level data per symbol/timeframe.
State management only — analysis and chart rendering live in market_analyzer.py
and market_chart.py respectively.
"""

import json
import os
import tempfile
import threading
from datetime import datetime, timedelta
from pathlib import Path
from .app_logger import get_logger
from .json_data_parser import SUPPORTED_EVENTS, display_symbol

logger = get_logger()

# Timeframe constants used across the codebase.
TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4")
EMA_TIMEFRAMES = ("M1", "M5")
PATTERN_TIMEFRAMES = ("M15", "M30", "H1", "H4")
RSI_TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4")
RSI_LOOKBACKS = {"M1": 60, "M5": 36, "M15": 24, "M30": 16, "H1": 12, "H4": 8}
CHART_CANDLE_LOOKBACK = 60  # candles in levels chart

# Default path used when none is supplied.
DEFAULT_PATH = Path("market_state.json")

_OFFSET = int(os.environ.get("TIMEZONE_OFFSET_HOURS", "8"))


def display_time(value):
    """Convert MT5 datetime value to human-readable string."""
    if not value:
        return "?"
    if isinstance(value, (int, float)):
        parsed = datetime.fromtimestamp(float(value))
    else:
        try:
            parsed = datetime.strptime(str(value), "%Y.%m.%d %H:%M")
        except ValueError:
            try:
                parsed = datetime.strptime(str(value), "%Y.%m.%d %H:%M:%S")
            except ValueError:
                return str(value)
    return (parsed + timedelta(hours=_OFFSET)).strftime("%Y.%m.%d %I:%M %p")


def _price(value, snapshot):
    """Format a price to the snapshot's decimal digits."""
    return f"{value:.{snapshot['digits']}f}"


def validate_snapshot(payload):
    """Raise ValueError if payload is not a valid TIMEFRAME_SNAPSHOT."""
    if not isinstance(payload, dict):
        raise ValueError("payload is not a dict")
    timeframe = str(payload.get("timeframe", "")).upper()
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"unsupported timeframe: {timeframe}")
    symbol = display_symbol(payload.get("symbol", "")).upper()
    if not symbol:
        raise ValueError("missing or empty symbol")
    for required in ("open", "high", "low", "close"):
        if required not in payload:
            raise ValueError(f"missing required field: {required}")
    if "levels" in payload:
        levels = payload["levels"]
        if not isinstance(levels, dict):
            raise ValueError("levels is not a dict")
        for key in ("support", "resistance", "fib", "bullish_fvg", "bearish_fvg"):
            if key not in levels:
                raise ValueError(f"missing required level: {key}")
    patterns = payload.get("patterns", payload.get("retained_patterns", []))
    if isinstance(patterns, list):
        for pattern in patterns:
            event_type = pattern.get("event_type")
            if event_type not in SUPPORTED_EVENTS:
                raise ValueError(f"unsupported pattern event_type: {event_type}")


class MarketState:
    """Thread-safe persistence manager for symbol/timeframe market snapshots."""

    def __init__(self, path=None):
        self.path = Path(path) if path else DEFAULT_PATH
        self.lock = threading.RLock()
        self.data = {"symbols": {}}
        self._load()

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _load(self):
        try:
            with open(self.path, "r") as f:
                self.data = json.load(f)
            if "symbols" not in self.data:
                self.data = {"symbols": {}}
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            self.data = {"symbols": {}}

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = None
        try:
            with tempfile.NamedTemporaryFile(
                "w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as f:
                json.dump(self.data, f)
                f.write("\n")
                tmp = Path(f.name)
            os.replace(str(tmp), str(self.path))
        finally:
            if tmp and tmp.exists():
                tmp.unlink()

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    def update(self, payload):
        """Ingest a TIMEFRAME_SNAPSHOT payload.

        Returns a list of notification dicts (new non-paused patterns detected).
        Each notification has 'symbol', 'event_type', 'signal', 'timeframe',
        'candle_time', plus the snapshot fields (open/high/low/close, etc).
        """
        validate_snapshot(payload)
        timeframe = str(payload.get("timeframe", "")).upper()
        symbol = display_symbol(payload.get("symbol", "")).upper()

        with self.lock:
            if symbol not in self.data["symbols"]:
                self.data["symbols"][symbol] = {}
            timeframes = self.data["symbols"][symbol]
            snapshot = timeframes.get(timeframe, {})
            prev_ema_bias = snapshot.get("ema_bias")
            prev_rsi_history = snapshot.get("rsi_history", [])

            # Build snapshot from payload
            snapshot = {
                "source": payload.get("source", ""),
                "candle_time": payload.get("candle_time"),
                "open": payload.get("open"),
                "high": payload.get("high"),
                "low": payload.get("low"),
                "close": payload.get("close"),
                "ema20": payload.get("ema20"),
                "ema50": payload.get("ema50"),
                "ema_bias": self._ema_bias(payload.get("ema20"), payload.get("ema50")),
                "digits": payload.get("digits", 5),
                "levels": payload.get("levels", {}),
                "chart_timeframe": payload.get("chart_timeframe", ""),
            }
            # Process patterns, separating notification-worthy from retained
            _processed = self._process_patterns(payload, symbol, timeframe)
            _retained = []
            _pattern_notifications = []
            for _entry in _processed:
                if "symbol" in _entry:
                    _pattern_notifications.append(_entry)
                else:
                    _retained.append(_entry)
            snapshot["retained_patterns"] = _retained

            # RSI
            rsi = payload.get("rsi14")
            if rsi is not None:
                snapshot["rsi14"] = rsi
                history = list(prev_rsi_history)
                history.append(
                    {
                        "candle_time": payload.get("candle_time"),
                        "rsi14": rsi,
                    }
                )
                # Cap RSI history to the largest lookback needed
                max_rsi = max(RSI_LOOKBACKS.values())
                history = history[-max_rsi:]
                snapshot["rsi_history"] = history

            # Candle history
            candle_history = payload.get("candle_history")
            if candle_history and isinstance(candle_history, list):
                snapshot["candle_history"] = candle_history

            # Auto-accumulate candle history from snapshot OHLC
            if "candle_history" not in snapshot:
                candle_time = payload.get("candle_time")
                if candle_time:
                    candle_entry = {
                        "candle_time": candle_time,
                        "open": payload.get("open"),
                        "high": payload.get("high"),
                        "low": payload.get("low"),
                        "close": payload.get("close"),
                    }
                    hist = timeframes.get(timeframe, {}).get("candle_history", [])
                    if not hist or hist[-1].get("candle_time") != candle_time:
                        hist = list(hist)
                        hist.append(candle_entry)
                    # Cap auto-accumulated candle history
                    hist = hist[-CHART_CANDLE_LOOKBACK:]
                    snapshot["candle_history"] = hist

            # Build notifications (pattern + EMA crossover)
            notifications = []
            _notify = bool(payload.get("notify_patterns", True))
            if _notify:
                notifications.extend(_pattern_notifications)
            new_bias = snapshot["ema_bias"]
            if timeframe in EMA_TIMEFRAMES and prev_ema_bias is not None:
                if prev_ema_bias != new_bias:
                    notifications.append(
                        {
                            "event_type": "EMA_CROSSOVER",
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "candle_time": payload.get("candle_time"),
                            "signal": "BUY" if new_bias == "BULLISH" else "SELL",
                            "open": payload.get("open"),
                            "high": payload.get("high"),
                            "low": payload.get("low"),
                            "close": payload.get("close"),
                            "ema20": payload.get("ema20"),
                            "ema50": payload.get("ema50"),
                            "digits": payload.get("digits", 5),
                        }
                    )

            timeframes[timeframe] = snapshot
            if timeframe in PATTERN_TIMEFRAMES:
                self._invalidate_patterns(timeframes, timeframe)
            self._save()
        return notifications

    @staticmethod
    def _ema_bias(ema20, ema50):
        if ema20 is None or ema50 is None:
            return "NEUTRAL"
        return "BULLISH" if ema20 > ema50 else "BEARISH" if ema20 < ema50 else "NEUTRAL"

    def _process_patterns(self, payload, symbol, timeframe):
        raw = payload.get("patterns", payload.get("retained_patterns", []))
        if not isinstance(raw, list):
            return []
        existing = {}
        with self.lock:
            old_snapshot = self.data["symbols"].get(symbol, {}).get(timeframe, {})
            for pattern in old_snapshot.get("retained_patterns", []):
                key = self._pattern_key(pattern)
                existing[key] = pattern

        result = []
        for pattern in raw:
            event_type = pattern.get("event_type")
            signal = pattern.get("signal", "")
            candle_time = payload.get("candle_time")
            key = self._pattern_key(pattern)

            is_new = key not in existing
            was_invalidated = existing.get(key, {}).get("invalidated", False) if not is_new else False

            if is_new or was_invalidated:
                result.append(
                    {
                        "event_type": event_type,
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "signal": signal,
                        "candle_time": candle_time,
                        "open": payload.get("open"),
                        "high": payload.get("high"),
                        "low": payload.get("low"),
                        "close": payload.get("close"),
                        "ema20": payload.get("ema20"),
                        "ema50": payload.get("ema50"),
                        "digits": payload.get("digits", 5),
                    }
                )

            result.append(
                {
                    "event_type": event_type,
                    "signal": signal,
                    "candle_time": candle_time,
                    "invalidated": False,
                }
            )

        return result

    def mark_notified(self, notification):
        """Mark a notification as having been sent, so it won't fire again."""
        with self.lock:
            symbol = display_symbol(notification.get("symbol", "")).upper()
            timeframe = notification.get("timeframe", "")
            key = self._pattern_key(notification)
            snapshot = self.data["symbols"].get(symbol, {}).get(timeframe)
            if not snapshot:
                return
            patterns = snapshot.get("retained_patterns", [])
            for pattern in patterns:
                if self._pattern_key(pattern) == key:
                    pattern["notified"] = True
            self._save()

    @staticmethod
    def _pattern_key(pattern):
        """Unique key for a pattern within a symbol/timeframe."""
        return (pattern.get("event_type"), pattern.get("signal"))

    def _invalidate_patterns(self, timeframes, updated_timeframe):
        """Mark retained patterns from other timeframes as invalidated."""
        for tf in PATTERN_TIMEFRAMES:
            if tf == updated_timeframe:
                continue
            snapshot = timeframes.get(tf)
            if not snapshot:
                continue
            for pattern in snapshot.get("retained_patterns", []):
                if not pattern.get("invalidated"):
                    pattern["invalidated"] = True
