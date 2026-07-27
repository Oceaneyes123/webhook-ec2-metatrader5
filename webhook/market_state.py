"""Persistent latest-state storage for market snapshots.

Keeps candle-history, EMA, RSI, patterns, and key-level data per symbol/timeframe.
State management only — analysis and chart rendering live in market_analyzer.py
and market_chart.py respectively.
"""

import json
import os
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from .app_logger import get_logger
from .json_data_parser import SUPPORTED_EVENTS, display_symbol

logger = get_logger()

# Timeframe constants used across the codebase.
TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4", "D1")
EMA_TIMEFRAMES = ("M1", "M5")
PATTERN_TIMEFRAMES = ("M15", "M30", "H1", "H4")
LEVEL_TIMEFRAMES = ("M5", "M15", "M30", "H1", "H4", "D1")
KEY_LEVEL_ALERT_TIMEFRAMES = ("M30", "H1", "H4", "D1")
RSI_TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4", "D1")
RSI_LOOKBACKS = {"M1": 60, "M5": 36, "M15": 24, "M30": 16, "H1": 12, "H4": 8, "D1": 5}
RSI_STRONG_LOW = 30
RSI_STRONG_HIGH = 70
CHART_CANDLE_LOOKBACK = 60  # candles in levels chart
DIVERGENCE_HISTORY = 200

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
        self.data = {"symbols": {}, "key_level_alerts": {}, "market_structure": {}, "divergence_alerts": {}}
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
            self.data.setdefault("key_level_alerts", {})
            self.data.setdefault("market_structure", {})
            self.data.setdefault("divergence_alerts", {})
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            self.data = {"symbols": {}, "key_level_alerts": {}, "market_structure": {}, "divergence_alerts": {}}

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
            prev_rsi_notified_at = snapshot.get("rsi_notified_at", 0)

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
                "bid": payload.get("bid", payload.get("close")),
                "ask": payload.get("ask", payload.get("close")),
                "daily_open": payload.get("daily_open"),
                "daily_high": payload.get("daily_high"),
                "daily_low": payload.get("daily_low"),
                "vwap": payload.get("vwap"),
                "rsi_notified_at": prev_rsi_notified_at,
                "received_at": time.time(),
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
            rsi_notification = None
            rsi = payload.get("rsi14")
            if rsi is not None:
                snapshot["rsi14"] = rsi
                try:
                    rsi = float(rsi)
                    cooldown = self._rsi_cooldown_seconds(timeframe)
                    if (
                        (rsi <= RSI_STRONG_LOW or rsi >= RSI_STRONG_HIGH)
                        and time.time() - float(prev_rsi_notified_at) >= cooldown
                    ):
                        rsi_notification = {
                            "event_type": "STRONG_RSI",
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "candle_time": payload.get("candle_time"),
                            "rsi14": rsi,
                            "open": payload.get("open"),
                            "high": payload.get("high"),
                            "low": payload.get("low"),
                            "close": payload.get("close"),
                        }
                except (TypeError, ValueError):
                    rsi_notification = None

            # Candle history
            candle_history = payload.get("candle_history", payload.get("candles"))
            if candle_history and isinstance(candle_history, list):
                snapshot["candle_history"] = [
                    {
                        **{key: candle.get(key) for key in ("open", "high", "low", "close", "rsi14") if key in candle},
                        "candle_time": candle.get("candle_time", candle.get("time")),
                    }
                    for candle in candle_history
                    if isinstance(candle, dict) and candle.get("candle_time", candle.get("time"))
                ][-DIVERGENCE_HISTORY:]
                if rsi is not None:
                    for candle in reversed(snapshot["candle_history"]):
                        if candle["candle_time"] == payload.get("candle_time"):
                            candle["rsi14"] = rsi
                            break

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
                    if rsi is not None:
                        candle_entry["rsi14"] = rsi
                    hist = timeframes.get(timeframe, {}).get("candle_history", [])
                    if not hist or hist[-1].get("candle_time") != candle_time:
                        hist = list(hist)
                        hist.append(candle_entry)
                    # Cap auto-accumulated candle history
                    hist = hist[-DIVERGENCE_HISTORY:]
                    snapshot["candle_history"] = hist

            snapshot["rsi_history"] = [
                {"candle_time": candle["candle_time"], "rsi14": candle["rsi14"]}
                for candle in snapshot.get("candle_history", [])
                if candle.get("rsi14") is not None
            ][-DIVERGENCE_HISTORY:]

            # Build notifications (pattern + EMA crossover)
            notifications = []
            if rsi_notification:
                notifications.append(rsi_notification)
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

            notifications.extend(
                self._key_level_notifications(
                    symbol, timeframe, timeframes, snapshot, payload
                )
            )
            notifications.extend(
                self._divergence_notifications(symbol, timeframe, timeframes, snapshot)
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
            if notification.get("event_type", "").startswith("KEY_LEVEL_"):
                alerts = self.data.setdefault("key_level_alerts", {}).setdefault(symbol, {})
                state = alerts.get(notification["key_level_key"], {})
                if not isinstance(state, dict):
                    state = {}
                state["armed"] = False
                state.setdefault("events", {})[notification["event_type"]] = time.time()
                alerts[notification["key_level_key"]] = state
                direction = notification.get("structure_direction")
                if direction:
                    self.data.setdefault("market_structure", {}).setdefault(symbol, {})[
                        notification["timeframe"]
                    ] = direction
                self._save()
                return
            snapshot = self.data["symbols"].get(symbol, {}).get(timeframe)
            if not snapshot:
                return
            if notification.get("event_type") == "STRONG_RSI":
                snapshot["rsi_notified_at"] = time.time()
                self._save()
                return
            if notification.get("event_type", "").startswith("DIVERGENCE_"):
                self.data.setdefault("divergence_alerts", {}).setdefault(symbol, {}).setdefault(
                    timeframe, {}
                )[notification["divergence_key"]] = time.time()
                self._save()
                return
            patterns = snapshot.get("retained_patterns", [])
            for pattern in patterns:
                if self._pattern_key(pattern) == key:
                    pattern["notified"] = True
            self._save()

    @staticmethod
    def _rsi_cooldown_seconds(timeframe):
        timeframe = str(timeframe)
        value = int(timeframe[1:])
        minutes = value * {"M": 1, "H": 60, "D": 1440}[timeframe[0]]
        return minutes * 5 * 60

    def _divergence_notifications(self, symbol, timeframe, timeframes, snapshot):
        history = snapshot.get("candle_history", [])
        if len(history) < 5:
            return []
        lows = [item for index, item in enumerate(history[2:-2], 2) if item.get("rsi14") is not None and item["low"] < history[index - 1]["low"] and item["low"] < history[index + 1]["low"]]
        highs = [item for index, item in enumerate(history[2:-2], 2) if item.get("rsi14") is not None and item["high"] > history[index - 1]["high"] and item["high"] > history[index + 1]["high"]]
        matches = []
        if len(lows) >= 2:
            previous, current = lows[-2:]
            if current["low"] < previous["low"] and current["rsi14"] > previous["rsi14"]:
                matches.append(("DIVERGENCE_REGULAR_BULLISH", "BUY", previous, current))
            if current["low"] > previous["low"] and current["rsi14"] < previous["rsi14"]:
                matches.append(("DIVERGENCE_HIDDEN_BULLISH", "BUY", previous, current))
        if len(highs) >= 2:
            previous, current = highs[-2:]
            if current["high"] > previous["high"] and current["rsi14"] < previous["rsi14"]:
                matches.append(("DIVERGENCE_REGULAR_BEARISH", "SELL", previous, current))
            if current["high"] < previous["high"] and current["rsi14"] > previous["rsi14"]:
                matches.append(("DIVERGENCE_HIDDEN_BEARISH", "SELL", previous, current))
        alerts = self.data.setdefault("divergence_alerts", {}).setdefault(symbol, {}).setdefault(timeframe, {})
        notifications = []
        for event_type, signal, previous, current in matches:
            key = f"{event_type}:{current['candle_time']}"
            if key in alerts:
                continue
            level = self._nearest_key_level(timeframes, timeframe, snapshot, current["close"])
            notifications.append({
                "event_type": event_type, "signal": signal, "symbol": symbol, "timeframe": timeframe,
                "candle_time": current["candle_time"], "price": current["close"], "rsi14": current["rsi14"],
                "previous_price": previous["close"], "previous_rsi14": previous["rsi14"], "digits": snapshot["digits"],
                "divergence_key": key, "nearest_key_level": level,
            })
        return notifications

    def _nearest_key_level(self, timeframes, timeframe, snapshot, price):
        snapshots = dict(timeframes)
        snapshots[timeframe] = snapshot
        matches = []
        for level_timeframe in KEY_LEVEL_ALERT_TIMEFRAMES:
            for label, value, is_zone in self._key_level_values(snapshots.get(level_timeframe, {}).get("levels", {})):
                if value is not None:
                    level_price = sum(value) / 2 if is_zone else value
                    matches.append((abs(price - level_price), level_timeframe, label, level_price))
        if not matches:
            return None
        _, level_timeframe, label, level_price = min(matches)
        return {"timeframe": level_timeframe, "label": label, "price": level_price}

    def _key_level_notifications(self, symbol, timeframe, timeframes, snapshot, payload):
        if timeframe not in KEY_LEVEL_ALERT_TIMEFRAMES:
            return []

        levels_by_timeframe = dict(timeframes)
        levels_by_timeframe[timeframe] = snapshot
        low = float(payload.get("low"))
        high = float(payload.get("high"))
        if timeframe == "D1":
            low = min(float(payload.get("bid", payload.get("close"))), float(payload.get("ask", payload.get("close"))))
            high = max(float(payload.get("bid", payload.get("close"))), float(payload.get("ask", payload.get("close"))))

        matches = []
        for level_timeframe in KEY_LEVEL_ALERT_TIMEFRAMES:
            levels = levels_by_timeframe.get(level_timeframe, {}).get("levels", {})
            for label, value, is_zone in self._key_level_values(levels):
                if value is None:
                    continue
                level_price = (value[0] + value[1]) / 2 if is_zone else value
                key = f"{level_price:.5f}"
                event_type = self._key_level_event(payload, value, is_zone)
                alert_state = self._key_level_alert_state(symbol, key)
                if event_type is None:
                    if not self._key_level_touched(low, high, value, is_zone):
                        alert_state["armed"] = True
                    continue
                matches.append((key, event_type, level_timeframe, label, level_price, alert_state))

        grouped = {}
        for key, event_type, level_timeframe, label, level_price, alert_state in matches:
            grouped.setdefault((key, event_type), []).append((level_timeframe, label, level_price, alert_state))

        notifications = []
        timeframe_rank = {
            name: index for index, name in enumerate(KEY_LEVEL_ALERT_TIMEFRAMES)
        }
        for (key, event_type), group in grouped.items():
            primary_timeframe, primary_label, level_price, alert_state = max(
                group, key=lambda item: timeframe_rank[item[0]]
            )
            event_type, structure_direction = self._structure_event(
                symbol, primary_timeframe, event_type
            )
            cooldown = self._rsi_cooldown_seconds(primary_timeframe)
            last_alert_at = float(alert_state.get("events", {}).get(event_type, 0))
            if not alert_state.get("armed", True) or time.time() - last_alert_at < cooldown:
                alert_state["armed"] = False
                continue
            coincident = sorted({item[0] for item in group if item[0] != primary_timeframe}, key=timeframe_rank.get)
            notifications.append(
                {
                    "event_type": event_type,
                    "symbol": symbol,
                    "timeframe": primary_timeframe,
                    "candle_time": payload.get("candle_time"),
                    "key_level_key": key,
                    "key_level_price": level_price,
                    "key_level_label": primary_label,
                    "coincident_timeframes": coincident,
                    "digits": payload.get("digits", 5),
                    "structure_direction": structure_direction,
                }
            )
        return notifications

    def _structure_event(self, symbol, timeframe, event_type):
        if event_type not in ("KEY_LEVEL_BREAK_UP", "KEY_LEVEL_BREAK_DOWN"):
            return event_type, None
        direction = "UP" if event_type.endswith("_UP") else "DOWN"
        previous = self.data.get("market_structure", {}).get(symbol, {}).get(timeframe)
        kind = "CHOCH" if previous and previous != direction else "BOS"
        return f"KEY_LEVEL_{kind}_{direction}", direction

    def _key_level_alert_state(self, symbol, key):
        alerts = self.data.setdefault("key_level_alerts", {}).setdefault(symbol, {})
        state = alerts.get(key)
        if not isinstance(state, dict):
            state = {"armed": True, "events": {}}
            alerts[key] = state
        state.setdefault("armed", True)
        state.setdefault("events", {})
        return state

    @staticmethod
    def _key_level_touched(low, high, value, is_zone):
        return low <= value[1] and high >= value[0] if is_zone else low <= value <= high

    @staticmethod
    def _key_level_event(payload, value, is_zone):
        open_price = float(payload.get("open"))
        close = float(payload.get("close"))
        low = float(payload.get("low"))
        high = float(payload.get("high"))
        if is_zone:
            lower, upper = value
            if open_price >= upper and close < lower:
                return "KEY_LEVEL_BREAK_DOWN"
            if open_price <= lower and close > upper:
                return "KEY_LEVEL_BREAK_UP"
            if open_price > upper and close > upper and low <= upper:
                return "KEY_LEVEL_REJECTION_UP"
            if open_price < lower and close < lower and high >= lower:
                return "KEY_LEVEL_REJECTION_DOWN"
            return None
        if open_price < value < close:
            return "KEY_LEVEL_BREAK_UP"
        if open_price > value > close:
            return "KEY_LEVEL_BREAK_DOWN"
        if open_price > value and close > value and low <= value:
            return "KEY_LEVEL_REJECTION_UP"
        if open_price < value and close < value and high >= value:
            return "KEY_LEVEL_REJECTION_DOWN"
        return None

    @staticmethod
    def _key_level_values(levels):
        values = (
            ("Support", levels.get("support"), False),
            ("Resistance", levels.get("resistance"), False),
            ("Fib 61.8", levels.get("fib", {}).get("61.8") if isinstance(levels.get("fib"), dict) else None, False),
            ("Bullish FVG", levels.get("bullish_fvg"), True),
            ("Bearish FVG", levels.get("bearish_fvg"), True),
            ("Previous Day High", levels.get("previous_day_high"), False),
            ("Previous Day Low", levels.get("previous_day_low"), False),
        )
        result = []
        for label, value, is_zone in values:
            try:
                if is_zone and isinstance(value, dict):
                    result.append((label, (float(value["low"]), float(value["high"])), True))
                elif not is_zone and value is not None:
                    result.append((label, float(value), False))
            except (KeyError, TypeError, ValueError):
                continue
        return result

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
