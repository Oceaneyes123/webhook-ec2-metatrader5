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
from .market_structure import (
    TIMEFRAME_RANK, atr, classify_level, confirm_structure, level_id,
    level_strength, level_tolerance, LEVEL_MIN_STRENGTH,
)
from .candle_patterns import (
    confirmation_result, debug_logging_enabled, enabled_pattern_timeframes,
    enabled_pattern_types, evaluate, invalidation_alerts_enabled,
    pattern_invalidation,
)

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
PATTERN_MAX_AGE_CANDLES = int(os.environ.get("PATTERN_MAX_AGE_CANDLES", "8"))
PATTERN_RETENTION_CANDLES = int(os.environ.get("PATTERN_RETENTION_CANDLES", "32"))
LEVEL_RETENTION = int(os.environ.get("LEVEL_RETENTION", "200"))
LEVEL_REARM_ATR = float(os.environ.get("LEVEL_REARM_DISTANCE_ATR", "0.5"))
LEVEL_STALE_UPDATES = int(os.environ.get("LEVEL_STALE_UPDATES", "20"))
LEVEL_COOLDOWN_MULTIPLIER = int(os.environ.get("LEVEL_COOLDOWN_MULTIPLIER", "5"))
LEVEL_DEBUG = os.environ.get("MARKET_DEBUG_LOGGING", "false").lower() in {"1", "true", "yes"}
ENABLED_LEVEL_TYPES = {item.strip() for item in os.environ.get("LEVEL_ENABLED_TYPES", "").split(",") if item.strip()}
ENABLED_LEVEL_EVENTS = {item.strip() for item in os.environ.get("LEVEL_ENABLED_EVENTS", "").split(",") if item.strip()}

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
            if not isinstance(pattern, dict):
                continue
            event_type = pattern.get("event_type")
            if event_type not in SUPPORTED_EVENTS:
                raise ValueError(f"unsupported pattern event_type: {event_type}")


class MarketState:
    """Thread-safe persistence manager for symbol/timeframe market snapshots."""

    def __init__(self, path=None):
        self.path = Path(path) if path else DEFAULT_PATH
        self.lock = threading.RLock()
        self.data = {"symbols": {}, "key_level_alerts": {}, "level_objects": {}, "market_structure": {}, "divergence_alerts": {}}
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
            self.data.setdefault("level_objects", {})
            self.data.setdefault("market_structure", {})
            self.data.setdefault("divergence_alerts", {})
        except (FileNotFoundError, json.JSONDecodeError, ValueError):
            self.data = {"symbols": {}, "key_level_alerts": {}, "level_objects": {}, "market_structure": {}, "divergence_alerts": {}}

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
        if any(payload.get(key) is False for key in ("closed", "candle_closed", "is_closed")):
            logger.debug("Ignored unfinished candle symbol=%s timeframe=%s", payload.get("symbol"), payload.get("timeframe"))
            return []
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
                "daily_atr": payload.get("daily_atr"),
                "vwap": payload.get("vwap"),
                "rsi_notified_at": prev_rsi_notified_at,
                "received_at": time.time(),
            }
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
                        **{key: candle.get(key) for key in ("open", "high", "low", "close", "rsi14", "tick_volume", "volume", "session", "daily_atr") if key in candle},
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
                    for optional in ("tick_volume", "volume"):
                        if payload.get(optional) is not None:
                            candle_entry[optional] = payload[optional]
                    if rsi is not None:
                        candle_entry["rsi14"] = rsi
                    hist = timeframes.get(timeframe, {}).get("candle_history", [])
                    if not hist or hist[-1].get("candle_time") != candle_time:
                        hist = list(hist)
                        hist.append(candle_entry)
                    # Cap auto-accumulated candle history
                    hist = hist[-DIVERGENCE_HISTORY:]
                    snapshot["candle_history"] = hist

            # Process raw MT5 pattern events only after closed-candle history is available.
            _processed = self._process_patterns(payload, symbol, timeframe, snapshot.get("candle_history", []), timeframes)
            _retained = []
            _pattern_notifications = []
            for _entry in _processed:
                if "symbol" in _entry:
                    _pattern_notifications.append(_entry)
                else:
                    _retained.append(_entry)
            snapshot["retained_patterns"] = _retained

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

            # Structure is independent of reference levels: only confirmed swings
            # can produce BOS/CHoCH.  Key-level interactions remain level events.
            if timeframe in KEY_LEVEL_ALERT_TIMEFRAMES:
                for event in confirm_structure(
                    self.data.setdefault("market_structure", {}),
                    symbol,
                    timeframe,
                    snapshot.get("candle_history", []),
                ):
                    swing = event["swing"]
                    notifications.append({
                        "event_type": "KEY_LEVEL_%s_%s" % (event["type"], event["direction"]),
                        "symbol": symbol, "timeframe": timeframe,
                        "source_timeframe": timeframe,
                        "candle_time": event["candle_time"], "signal": "BUY" if event["direction"] == "UP" else "SELL",
                        "key_level_key": swing["id"], "key_level_price": swing["price"],
                        "key_level_label": "External swing %s" % swing["type"],
                        "structure_event_type": event["type"], "broken_swing_type": swing["type"],
                        "broken_swing_time": swing.get("time"), "protected_level": event.get("protected_level"),
                        "break_distance": event.get("break_distance"), "atr_displacement": event.get("atr_displacement"),
                        "structure_after": event.get("structure_after"), "external": event.get("external", True),
                        "close_price": payload.get("close"), "lifecycle": "confirmed",
                        "strength": swing.get("atr_relative"),
                        "confirmation_reason": "confirmed external swing and ATR/body close",
                        "structure_event": True, "structure_before": event.get("structure_before", "unknown"),
                        "event_id": "%s:%s:%s:%s" % (symbol, timeframe, event["type"], swing["id"]),
                        "digits": payload.get("digits", 5),
                    })
            notifications.extend(self._key_level_notifications(symbol, timeframe, timeframes, snapshot, payload))
            notifications.extend(
                self._divergence_notifications(symbol, timeframe, timeframes, snapshot)
            )

            timeframes[timeframe] = snapshot
            self._save()
        return notifications

    @staticmethod
    def _ema_bias(ema20, ema50):
        if ema20 is None or ema50 is None:
            return "NEUTRAL"
        return "BULLISH" if ema20 > ema50 else "BEARISH" if ema20 < ema50 else "NEUTRAL"

    def _process_patterns(self, payload, symbol, timeframe, history=None, timeframes=None):
        raw = payload.get("patterns", payload.get("retained_patterns", []))
        if not isinstance(raw, list):
            return []
        if timeframe not in enabled_pattern_timeframes():
            raw = []
        else:
            raw = [pattern for pattern in raw if isinstance(pattern, dict) and str(pattern.get("event_type", "")).upper() in enabled_pattern_types()]
        existing = {}
        with self.lock:
            old_snapshot = self.data["symbols"].get(symbol, {}).get(timeframe, {})
            for pattern in old_snapshot.get("retained_patterns", []):
                key = self._pattern_key(pattern)
                existing[key] = pattern

        result = []
        seen = set()
        for pattern in raw:
            event_type = pattern.get("event_type")
            signal = pattern.get("signal", "")
            candle_time = payload.get("candle_time")
            key = self._pattern_key({**pattern, "candle_time": candle_time})
            seen.add(key)

            is_new = key not in existing
            was_invalidated = existing.get(key, {}).get("invalidated", False) if not is_new else False

            context_snapshots = dict(timeframes or {})
            context_snapshots[timeframe] = {
                **self.data["symbols"].get(symbol, {}).get(timeframe, {}),
                "levels": payload.get("levels", {}),
                "ema_bias": self._ema_bias(payload.get("ema20"), payload.get("ema50")),
                "vwap": payload.get("vwap"),
                "daily_open": payload.get("daily_open"), "daily_high": payload.get("daily_high"),
                "daily_low": payload.get("daily_low"), "daily_atr": payload.get("daily_atr"),
            }
            context = evaluate(event_type, signal, payload, history or [], context_snapshots)
            event_candle = history[-1] if history and isinstance(history[-1], dict) else payload
            pattern_state = {
                "event_type": event_type, "signal": signal, "candle_time": candle_time,
                "invalidated": False, "pattern_id": "%s:%s:%s:%s:%s" % (symbol, timeframe, event_type, signal, candle_time),
                "open": event_candle.get("open"), "high": event_candle.get("high"), "low": event_candle.get("low"), "close": event_candle.get("close"),
                "lifecycle": "confirmed" if context.get("confirmed") else "awaiting_confirmation" if context.get("qualified") else "raw_detected",
                **context,
            }
            if not is_new and not was_invalidated:
                pattern_state = {**existing[key], **context}
            if (is_new or was_invalidated) and context.get("confirmed"):
                result.append(
                    {
                        "event_type": event_type,
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "signal": signal,
                        "candle_time": candle_time,
                        "open": event_candle.get("open"),
                        "high": event_candle.get("high"),
                        "low": event_candle.get("low"),
                        "close": event_candle.get("close"),
                        "ema20": payload.get("ema20"),
                        "ema50": payload.get("ema50"),
                        "digits": payload.get("digits", 5),
                        **pattern_state,
                    }
                )
            result.append(pattern_state)

        # Advance persisted patterns even when MT5 no longer lists the raw event.
        for key, previous in existing.items():
            if key in seen:
                continue
            updated = dict(previous)
            lifecycle = updated.get("lifecycle")
            invalidation_reason = pattern_invalidation(updated, history or [])
            if invalidation_reason and not updated.get("invalidated"):
                updated.update({
                    "invalidated": True,
                    "lifecycle": "invalidated",
                    "invalidated_at": payload.get("candle_time"),
                    "invalidation_reason": invalidation_reason,
                    "confirmation_status": "Invalidated",
                    "age_candles": int(updated.get("age_candles", 0)) + 1,
                })
                if invalidation_alerts_enabled() and not updated.get("invalidation_notified"):
                    result.append({
                        **updated,
                        "event_type": "PATTERN_INVALIDATED",
                        "original_event_type": updated.get("event_type"),
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "candle_time": payload.get("candle_time"),
                        "open": payload.get("open"), "high": payload.get("high"),
                        "low": payload.get("low"), "close": payload.get("close"),
                        "confidence": "Informational", "score": 0,
                        "confirmation_status": "Invalidated",
                    })
                    updated["invalidation_notified"] = True
                result.append(updated)
                continue
            if lifecycle in {"alerted", "failed", "invalidated", "expired"}:
                updated["age_candles"] = int(updated.get("age_candles", 0)) + 1
                if updated["age_candles"] >= PATTERN_RETENTION_CANDLES:
                    continue
                result.append(updated)
                continue
            structure = self.data.get("market_structure", {}).get(symbol, {}).get(timeframe, {})
            if updated.get("confirmation_mode") == "structure_confirmed":
                trend = structure.get("trend") if isinstance(structure, dict) else None
                updated["structure_confirmed"] = bool(
                    updated.get("structure_confirmed")
                    or (updated.get("signal") == "BUY" and trend == "bullish")
                    or (updated.get("signal") == "SELL" and trend == "bearish")
                )
            confirmation = confirmation_result(updated, history or [])
            if confirmation == "confirmed":
                updated.update({"lifecycle": "confirmed", "confirmed_at": payload.get("candle_time"), "confirmation_status": "Confirmed"})
                result.append({**updated, "symbol": symbol, "timeframe": timeframe, "open": payload.get("open"), "high": payload.get("high"), "low": payload.get("low"), "close": payload.get("close"), "digits": payload.get("digits", 5)})
            elif confirmation == "failed":
                updated.update({"lifecycle": "failed", "invalidated": True, "invalidated_at": payload.get("candle_time"), "confirmation_status": "Failed"})
            elif confirmation == "expired" or int(updated.get("age_candles", 0)) + 1 >= PATTERN_MAX_AGE_CANDLES:
                updated.update({"lifecycle": "expired", "expired_at": payload.get("candle_time"), "confirmation_status": "Expired", "age_candles": int(updated.get("age_candles", 0)) + 1})
            else:
                updated["age_candles"] = int(updated.get("age_candles", 0)) + 1
            if updated.get("lifecycle") != "expired" or updated.get("age_candles", 0) < PATTERN_RETENTION_CANDLES:
                result.append(updated)

        if os.environ.get("PATTERN_ALERT_GROUPING_ENABLED", "true").lower() not in {"0", "false", "no"}:
            grouped = {}
            for item in result:
                if "symbol" in item:
                    grouped.setdefault((item.get("timeframe"), item.get("candle_time"), item.get("signal")), []).append(item)
            hidden = set()
            for group in grouped.values():
                if len(group) < 2:
                    continue
                primary = group[0]
                primary["related_patterns"] = [item.get("event_type") for item in group[1:]]
                hidden.update(id(item) for item in group[1:])
            result = [item for item in result if id(item) not in hidden]
        if debug_logging_enabled():
            for item in result:
                if item.get("lifecycle") == "raw_detected":
                    logger.debug("Suppressed candle pattern %s: %s", item.get("pattern_id"), item.get("reasons_reduced", []))
        return result
    def mark_notified(self, notification):
        """Mark a notification as having been sent, so it won't fire again."""
        with self.lock:
            symbol = display_symbol(notification.get("symbol", "")).upper()
            timeframe = notification.get("timeframe", "")
            key = self._pattern_key(notification)
            if notification.get("structure_event"):
                structure = self.data.setdefault("market_structure", {}).setdefault(symbol, {}).setdefault(timeframe, {})
                event_id = notification.get("event_id")
                history = structure.setdefault("notified_event_ids", [])
                if event_id and event_id not in history:
                    history.append(event_id)
                    del history[:-100]
                structure["last_notified_event_id"] = event_id
                self._save()
                return
            if notification.get("event_type", "").startswith("KEY_LEVEL_"):
                alerts = self.data.setdefault("key_level_alerts", {}).setdefault(symbol, {})
                for level_key in [notification["key_level_key"], *notification.get("coincident_keys", [])]:
                    state = alerts.get(level_key, {})
                    if not isinstance(state, dict):
                        state = {}
                    state["armed"] = False
                    state["last_candle"] = notification.get("candle_time")
                    state["age_candles"] = 0
                    state["cooldown_until"] = time.time() + self._level_cooldown_seconds(
                        notification.get("cooldown_source_timeframe", notification.get("source_timeframe", timeframe))
                    )
                    state.setdefault("events", {})[notification["event_type"]] = time.time()
                    event_type = notification["event_type"]
                    if event_type == "KEY_LEVEL_BREAK_UP":
                        state["lifecycle"] = "broken_up"
                        state["awaiting_retest"] = True
                        state["retest_held"] = False
                    elif event_type == "KEY_LEVEL_BREAK_DOWN":
                        state["lifecycle"] = "broken_down"
                        state["awaiting_retest"] = True
                        state["retest_held"] = False
                    elif event_type.startswith("KEY_LEVEL_RECLAIM_"):
                        state["lifecycle"] = event_type.removeprefix("KEY_LEVEL_").lower()
                        state["awaiting_retest"] = False
                    elif event_type.startswith("KEY_LEVEL_RETEST_HOLD_"):
                        state["retest_held"] = True
                        state["awaiting_retest"] = False
                    elif event_type.startswith("KEY_LEVEL_RETEST_FAILURE_"):
                        state["failure_count"] = int(state.get("failure_count", 0)) + 1
                        state["lifecycle"] = "invalidated" if state["failure_count"] >= 2 else "retest_failed"
                        state["awaiting_retest"] = False
                    elif not str(state.get("lifecycle", "")).startswith("broken_"):
                        state["lifecycle"] = event_type.replace("KEY_LEVEL_", "").lower()
                    state.pop("pending", None)
                    alerts[level_key] = state
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
            if notification.get("event_type") == "PATTERN_INVALIDATED":
                for pattern in snapshot.get("retained_patterns", []):
                    if pattern.get("pattern_id") == notification.get("pattern_id"):
                        pattern["invalidation_notified"] = True
                self._save()
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
                    pattern["lifecycle"] = "alerted"
                    pattern["alerted_at"] = time.time()
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

    @staticmethod
    def _level_metadata(levels, label):
        keys = {
            "Support": "support", "Resistance": "resistance", "Fib 61.8": "fib",
            "Bullish FVG": "bullish_fvg", "Bearish FVG": "bearish_fvg",
            "Previous Day High": "previous_day_high", "Previous Day Low": "previous_day_low",
        }
        raw = levels.get(keys.get(label, ""))
        if label == "Fib 61.8" and isinstance(raw, dict):
            raw = raw.get("61.8")
        return raw if isinstance(raw, dict) else {}

    def _persistent_level(self, symbol, source_timeframe, label, value, is_zone, snapshot):
        """Resolve a drifting feed level to one durable object and alert state."""
        objects = self.data.setdefault("level_objects", {}).setdefault(symbol, {})
        current = (sum(value) / 2) if is_zone else value
        volatility = atr(snapshot.get("candle_history", []))
        metadata = self._level_metadata(snapshot.get("levels", {}), label)
        requested_origin = metadata.get("origin_time") or metadata.get("origin_candle")
        requested_reason = metadata.get("reason") or metadata.get("creation_reason")
        requested_direction = metadata.get("direction")
        tolerance = level_tolerance(value, volatility)
        object_id, item = None, None
        for candidate_id, candidate in objects.items():
            if candidate.get("source_timeframe") != source_timeframe or candidate.get("label") != label:
                continue
            if requested_origin:
                if str(candidate.get("origin_time")) != str(requested_origin):
                    continue
                if requested_reason and str(candidate.get("creation_reason")) != str(requested_reason):
                    continue
                if requested_direction and str(candidate.get("direction")) != str(requested_direction):
                    continue
                object_id, item = candidate_id, candidate
                break
            old = candidate.get("value", current)
            old_center = sum(old) / 2 if isinstance(old, list) else old
            if abs(float(old_center) - float(current)) <= max(tolerance, candidate.get("zone_width", 0) * 0.5):
                object_id, item = candidate_id, candidate
                break
        if item is None:
            origin = metadata.get("origin_time") or metadata.get("origin_candle") or snapshot.get("candle_time")
            reason = metadata.get("reason") or metadata.get("creation_reason") or "configured"
            direction = metadata.get("direction") or ("support" if "support" in label.lower() or "low" in label.lower() else "resistance" if "resistance" in label.lower() or "high" in label.lower() else "neutral")
            object_id = level_id(symbol, source_timeframe, label, value, is_zone, origin, reason, direction)
            item = {
                "id": object_id, "symbol": symbol, "source_timeframe": source_timeframe,
                "label": label, "value": list(value) if is_zone else value, "is_zone": is_zone,
                "origin_time": origin, "creation_reason": reason, "direction": direction,
                "created_at": snapshot.get("candle_time"), "last_seen": snapshot.get("candle_time"),
                "zone_width": (value[1] - value[0]) if is_zone else 0,
            }
            objects[object_id] = item
        else:
            item["value"] = list(value) if is_zone else value
            item["last_seen"] = snapshot.get("candle_time")
        item.setdefault("strength", level_strength(source_timeframe, metadata))
        item.setdefault("interactions", 0)
        item.setdefault("lifecycle", "created")
        alerts = self.data.setdefault("key_level_alerts", {}).setdefault(symbol, {})
        state = alerts.get(object_id)
        if not isinstance(state, dict):
            legacy_prefix = "%s|%s|%s|" % (symbol, source_timeframe, label)
            legacy_key = next((
                key for key in alerts
                if str(key).startswith(legacy_prefix) and str(key).count("|") == 3
            ), None)
            state = alerts.pop(legacy_key) if legacy_key else {}
            alerts[object_id] = state
        state.update({"level_id": object_id, "source_timeframe": source_timeframe, "level_type": label})
        state.setdefault("armed", True)
        state.setdefault("events", {})
        state.setdefault("lifecycle", item.get("lifecycle", "created"))
        state.setdefault("interaction_count", 0)
        state.setdefault("interaction_cycle", 0)
        state.setdefault("strength", item["strength"])
        state.setdefault("age_candles", 0)
        state.setdefault("touch_count", 0)
        state["presence_misses"] = 0
        return item, state

    def _retain_level_objects(self, symbol, seen_ids):
        objects = self.data.setdefault("level_objects", {}).setdefault(symbol, {})
        alerts = self.data.setdefault("key_level_alerts", {}).setdefault(symbol, {})
        for object_id, item in list(objects.items()):
            if object_id in seen_ids:
                item["presence_misses"] = 0
                continue
            item["presence_misses"] = int(item.get("presence_misses", 0)) + 1
            if item["presence_misses"] >= LEVEL_STALE_UPDATES and not alerts.get(object_id, {}).get("pending"):
                objects.pop(object_id, None)
                alerts.pop(object_id, None)
        if len(objects) > LEVEL_RETENTION:
            keep = sorted(objects.items(), key=lambda pair: pair[1].get("last_seen", ""), reverse=True)[:LEVEL_RETENTION]
            keep_ids = {key for key, _ in keep}
            for object_id in list(objects):
                if object_id in keep_ids or alerts.get(object_id, {}).get("pending"):
                    continue
                objects.pop(object_id, None)
                alerts.pop(object_id, None)
        for alert_id in list(alerts):
            if alert_id not in objects and not alerts[alert_id].get("pending"):
                alerts.pop(alert_id, None)

    @staticmethod
    def _level_cooldown_seconds(timeframe):
        value = str(timeframe).upper()
        minutes = int(value[1:]) * {"M": 1, "H": 60, "D": 1440}[value[0]]
        return minutes * 60 * LEVEL_COOLDOWN_MULTIPLIER

    @staticmethod
    def _is_sequence_event(event_type):
        return any(token in event_type for token in ("_BREAK_", "_RETEST_", "_RECLAIM_"))

    def _level_cooldown_active(self, state, timeframe):
        events = state.get("events", {})
        latest = max((float(value) for value in events.values()), default=0.0)
        until = latest + self._level_cooldown_seconds(timeframe) if latest else float(state.get("cooldown_until", 0))
        return time.time() < until

    def _key_level_notifications(self, symbol, timeframe, timeframes, snapshot, payload):
        if timeframe not in KEY_LEVEL_ALERT_TIMEFRAMES:
            return []

        pending = {}
        for state in self.data.setdefault("key_level_alerts", {}).setdefault(symbol, {}).values():
            notification = state.get("pending") if isinstance(state, dict) else None
            if (
                notification
                and notification.get("timeframe") == timeframe
                and notification.get("candle_time") == payload.get("candle_time")
            ):
                pending[notification["event_id"]] = notification
        if pending:
            return list(pending.values())

        frames = dict(timeframes)
        frames[timeframe] = snapshot
        previous_close = timeframes.get(timeframe, {}).get("close", payload.get("open"))
        volatility = atr(snapshot.get("candle_history", []))
        matches = []
        seen_ids = set()
        for source_timeframe in KEY_LEVEL_ALERT_TIMEFRAMES:
            for label, value, is_zone in self._key_level_values(frames.get(source_timeframe, {}).get("levels", {})):
                if ENABLED_LEVEL_TYPES and label not in ENABLED_LEVEL_TYPES:
                    continue
                level, state = self._persistent_level(symbol, source_timeframe, label, value, is_zone, frames[source_timeframe])
                key = level["id"]
                seen_ids.add(key)
                event_type = classify_level(payload, previous_close, value, is_zone, volatility, state, label)
                lower, upper = value if is_zone else (value, value)
                distance = min(abs(float(payload["close"]) - lower), abs(float(payload["close"]) - upper))
                if event_type is None:
                    touched = float(payload["high"]) >= lower and float(payload["low"]) <= upper
                    if touched:
                        state["touch_count"] += 1
                        state["interaction_count"] += 1
                        state["interaction_cycle"] += 1 if state.get("armed", True) else 0
                        state["strength"] = max(0.0, float(state.get("strength", level["strength"])) - 0.05)
                        if state.get("lifecycle") not in {"broken_up", "broken_down", "invalidated", "expired"}:
                            state["lifecycle"] = "touched"
                    # Rearm only after meaningful ATR-relative separation, not one quiet candle.
                    if distance >= volatility * LEVEL_REARM_ATR and state.get("lifecycle") not in {"invalidated", "expired"}:
                        state["armed"] = True
                    if LEVEL_DEBUG and not touched:
                        logger.debug("Suppressed key level %s: no confirmed interaction", key)
                    continue
                if ENABLED_LEVEL_EVENTS and event_type not in ENABLED_LEVEL_EVENTS:
                    if LEVEL_DEBUG:
                        logger.debug("Suppressed key level %s: event type disabled (%s)", key, event_type)
                    continue
                if float(state.get("strength", level["strength"])) < LEVEL_MIN_STRENGTH:
                    if LEVEL_DEBUG:
                        logger.debug("Suppressed key level %s: strength %.2f below threshold", key, state.get("strength", 0))
                    continue
                retest_pending = state.get("awaiting_retest") and event_type.startswith("KEY_LEVEL_RETEST_")
                lifecycle_transition = retest_pending or event_type.startswith("KEY_LEVEL_RECLAIM_")
                if state.get("last_candle") == payload.get("candle_time") or (not state.get("armed", True) and not lifecycle_transition):
                    if LEVEL_DEBUG:
                        logger.debug("Suppressed key level %s: duplicate candle or not rearmed", key)
                    continue
                price = (lower + upper) / 2
                matches.append((price, event_type, source_timeframe, label, key, state, level))

        grouped = {}
        for match in matches:
            placed = False
            for group_key, group in grouped.items():
                if group_key[1] == match[1] and abs(group[0][0] - match[0]) <= max(level_tolerance(group[0][6].get("value", group[0][0]), volatility), level_tolerance(match[6].get("value", match[0]), volatility)):
                    group.append(match)
                    placed = True
                    break
            if not placed:
                grouped[(match[0], match[1])] = [match]
        notifications = []
        for (_, event_type), group in grouped.items():
            price, _, source_timeframe, label, key, state, level = max(group, key=lambda item: TIMEFRAME_RANK[item[2]])
            if self._level_cooldown_active(state, source_timeframe) and not self._is_sequence_event(event_type):
                continue
            notification = {
                "event_type": event_type, "symbol": symbol, "timeframe": timeframe,
                "source_timeframe": source_timeframe, "candle_time": payload.get("candle_time"),
                "key_level_key": key, "key_level_price": price, "key_level_label": label,
                "coincident_levels": [{"timeframe": item[2], "label": item[3]} for item in group if item[4] != key],
                "coincident_keys": [item[4] for item in group if item[4] != key],
                "digits": payload.get("digits", 5),
                "event_id": "%s:%s:%s" % (key, event_type, payload.get("candle_time")),
                "close_price": payload.get("close"), "strength": state.get("strength"),
                "lifecycle": state.get("lifecycle"), "confirmation_reason": "closed candle with ATR/body confirmation",
                "cooldown_source_timeframe": source_timeframe,
            }
            state["pending"] = notification
            notifications.append(notification)
        self._retain_level_objects(symbol, seen_ids)
        return notifications

    def _key_level_alert_state(self, symbol, key):
        alerts = self.data.setdefault("key_level_alerts", {}).setdefault(symbol, {})
        state = alerts.get(key)
        if not isinstance(state, dict):
            state = {"armed": True, "events": {}, "lifecycle": "active"}
            alerts[key] = state
        state.setdefault("armed", True)
        state.setdefault("events", {})
        state.setdefault("lifecycle", "active")
        return state


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
                    result.append((label, float(value.get("price", value.get("value"))) if isinstance(value, dict) else float(value), False))
            except (KeyError, TypeError, ValueError):
                continue
        return result

    @staticmethod
    def _pattern_key(pattern):
        """Unique key for a pattern within a symbol/timeframe."""
        return (pattern.get("event_type"), pattern.get("signal"), pattern.get("candle_time"))
