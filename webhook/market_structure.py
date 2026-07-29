"""Closed-candle market structure and key-level interaction rules."""

from __future__ import annotations

import os
import logging
from statistics import mean


TIMEFRAME_RANK = {"M30": 0, "H1": 1, "H4": 2, "D1": 3}
SWING_BARS = {tf: int(os.environ.get("STRUCTURE_SWING_BARS_" + tf, "2")) for tf in TIMEFRAME_RANK}
MAX_SWINGS = 80
BREAK_ATR_BUFFER = float(os.environ.get("STRUCTURE_BREAK_ATR_BUFFER", "0.12"))
MIN_BODY_RATIO = float(os.environ.get("STRUCTURE_MIN_BODY_RATIO", "0.5"))
REJECTION_WICK_RATIO = float(os.environ.get("LEVEL_REJECTION_WICK_RATIO", "1.2"))
SWING_MIN_PROMINENCE_ATR = float(os.environ.get("STRUCTURE_MIN_PROMINENCE_ATR", "0.35"))
BREAK_CLOSE_LOCATION = float(os.environ.get("STRUCTURE_MIN_CLOSE_LOCATION", "0.65"))
SWEEP_PENETRATION_ATR = float(os.environ.get("LEVEL_SWEEP_PENETRATION_ATR", "0.15"))
REJECTION_MIN_BODY_RATIO = float(os.environ.get("LEVEL_REJECTION_MIN_BODY_RATIO", "0.25"))
SWEEP_MIN_BODY_RATIO = float(os.environ.get("LEVEL_SWEEP_MIN_BODY_RATIO", "0.35"))
COINCIDENCE_ATR = float(os.environ.get("LEVEL_COINCIDENCE_ATR", "0.25"))
LEVEL_MIN_STRENGTH = float(os.environ.get("LEVEL_MIN_STRENGTH", "0.75"))
STRICTNESS_MODE = os.environ.get("MARKET_STRICTNESS", "balanced").lower()
STRICTNESS_MULTIPLIER = {"conservative": 1.25, "balanced": 1.0, "aggressive": 0.75}.get(STRICTNESS_MODE, 1.0)
logger = logging.getLogger(__name__)


def _number(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def atr(candles):
    """Small, dependency-free ATR approximation for closed candle filtering."""
    ranges = [_number(item.get("high")) - _number(item.get("low")) for item in candles[-14:]]
    return max(mean(ranges), 10 ** -6) if ranges else 10 ** -6


def candle_quality(candle, level, direction, value_at_risk):
    """Require displacement, a real body and a close near the breaking end."""
    opening, high, low, close = (_number(candle.get(key)) for key in ("open", "high", "low", "close"))
    span, body = max(high - low, 10 ** -6), abs(close - opening)
    buffer = value_at_risk * BREAK_ATR_BUFFER * STRICTNESS_MULTIPLIER
    if direction == "UP":
        return close >= level + buffer and body / span >= MIN_BODY_RATIO and (close - low) / span >= BREAK_CLOSE_LOCATION
    return close <= level - buffer and body / span >= MIN_BODY_RATIO and (high - close) / span >= BREAK_CLOSE_LOCATION


def confirm_structure(structure, symbol, timeframe, candles):
    """Confirm non-repainting external swings and emit BOS/CHoCH only from them."""
    frames = structure.setdefault(symbol, {})
    state = frames.get(timeframe)
    # Older state files stored only "UP"/"DOWN" here; discard that lossy model.
    if not isinstance(state, dict):
        state = frames[timeframe] = {"trend": "unknown", "swings": [], "broken": []}
    state.setdefault("swings", [])
    if not isinstance(state["swings"], list):
        state["swings"] = []
    state.setdefault("broken", [])
    for swing in state["swings"]:
        swing.setdefault("valid", True)
        swing.setdefault("broken", swing.get("id") in state["broken"])
        swing.setdefault("protected", False)
        swing.setdefault("external", True)
        swing.setdefault("internal", False)
        swing.setdefault("structure_event", None)
    by_id = {item.get("id"): item for item in state["swings"]}
    for key in ("protected_high", "protected_low"):
        protected = state.get(key)
        if isinstance(protected, dict) and protected.get("id") in by_id:
            state[key] = by_id[protected["id"]]
    state.setdefault("last_bos", None)
    state.setdefault("last_choch", None)
    state.setdefault("last_structural_event_time", None)
    state.setdefault("last_confirmed_swing_high", None)
    state.setdefault("last_confirmed_swing_low", None)
    state.setdefault("establishment_state", "established" if state.get("trend") in {"bullish", "bearish"} else "unknown")
    if len(candles) < 2 * SWING_BARS.get(timeframe, 2) + 2:
        return []
    strength = atr(candles)
    right = SWING_BARS.get(timeframe, 2)
    pivot_index = len(candles) - right - 1
    pivot = candles[pivot_index]
    swing_added = False
    before, after = candles[pivot_index - right:pivot_index], candles[pivot_index + 1:pivot_index + right + 1]
    if len(before) == len(after) == right:
        high, low = _number(pivot.get("high")), _number(pivot.get("low"))
        for kind, price, peers in (("high", high, [_number(x.get("high")) for x in before + after]), ("low", low, [_number(x.get("low")) for x in before + after])):
            prominent = price - max(peers) if kind == "high" else min(peers) - price
            if prominent >= strength * SWING_MIN_PROMINENCE_ATR:
                swing_id = "%s:%s:%s:%s" % (symbol, timeframe, kind, pivot.get("candle_time"))
                if not any(item["id"] == swing_id for item in state["swings"]):
                    state["swings"].append({
                        "id": swing_id, "type": kind, "price": price,
                        "time": pivot.get("candle_time"), "confirmation_time": candles[-1].get("candle_time"),
                        "prominence": prominent, "atr_relative": prominent / strength,
                        "internal": False, "external": True, "valid": True,
                        "broken": False, "protected": False, "structure_event": None,
                    })
                    swing_added = True
    state["swings"] = state["swings"][-MAX_SWINGS:]
    highs = [item for item in state["swings"] if item["type"] == "high"]
    lows = [item for item in state["swings"] if item["type"] == "low"]
    old_swing_ids = set(state.get("ranging_swing_ids", []))
    new_swings = [item for item in state["swings"] if item["id"] not in old_swing_ids]
    structure_ready = state.get("trend") != "ranging" or (
        swing_added and {item["type"] for item in new_swings} == {"high", "low"}
    )
    if structure_ready and len(highs) >= 2 and len(lows) >= 2:
        if highs[-1]["price"] > highs[-2]["price"] and lows[-1]["price"] > lows[-2]["price"]:
            for item in state.get("swings", []):
                item["protected"] = False
            state["trend"] = "bullish"
            state["protected_high"] = None
            state["protected_low"] = lows[-1]
            state["last_higher_high"], state["last_higher_low"] = highs[-1], lows[-1]
        elif highs[-1]["price"] < highs[-2]["price"] and lows[-1]["price"] < lows[-2]["price"]:
            for item in state.get("swings", []):
                item["protected"] = False
            state["trend"] = "bearish"
            state["protected_low"] = None
            state["protected_high"] = highs[-1]
            state["last_lower_high"], state["last_lower_low"] = highs[-1], lows[-1]
    state["last_confirmed_swing_high"] = highs[-1] if highs else state.get("last_confirmed_swing_high")
    state["last_confirmed_swing_low"] = lows[-1] if lows else state.get("last_confirmed_swing_low")
    for key in ("protected_high", "protected_low"):
        if state.get(key):
            state[key]["protected"] = True
    candle = candles[-1]
    events = []
    trend = state.get("trend", "unknown")
    active_protected = state.get("protected_low" if trend == "bullish" else "protected_high")
    targets = []
    if trend == "bullish":
        targets = [("UP", highs[-1] if highs else None, "BOS"), ("DOWN", active_protected, "CHOCH")]
    elif trend == "bearish":
        targets = [("DOWN", lows[-1] if lows else None, "BOS"), ("UP", active_protected, "CHOCH")]
    seen_target_ids = set()
    for direction, swing, event_type in targets:
        if not swing or swing["id"] in seen_target_ids:
            continue
        seen_target_ids.add(swing["id"])
        if swing["id"] in state["broken"] or not candle_quality(candle, swing["price"], direction, strength):
            continue
        is_choch = event_type == "CHOCH"
        is_bos = event_type == "BOS"
        protected = swing if is_choch else active_protected
        state["broken"].append(swing["id"])
        swing["broken"] = True
        if is_choch:
            state["trend"] = "ranging"
            state["establishment_state"] = "awaiting_new_sequence"
            state["ranging_swing_ids"] = [item["id"] for item in state["swings"]]
        state["last_event"] = {"type": event_type, "direction": direction, "swing": swing, "candle_time": candle.get("candle_time")}
        swing["structure_event"] = state["last_event"]["type"]
        state["last_event"].update({
            "structure_before": trend,
            "structure_after": "ranging" if is_choch else trend,
            "protected_level": protected["price"] if protected else None,
            "break_distance": abs(_number(candle.get("close")) - swing["price"]),
            "atr_displacement": abs(_number(candle.get("close")) - swing["price"]) / strength,
            "external": True,
        })
        state["last_structural_event_time"] = candle.get("candle_time")
        state["last_choch" if is_choch else "last_bos"] = state["last_event"]
        if not is_choch:
            state["establishment_state"] = "established"
        events.append(state["last_event"])
    return events


def level_id(symbol, source_timeframe, label, value, is_zone, origin_time="legacy", reason="configured", direction="neutral"):
    origin = str(origin_time or "legacy").replace("|", "/")
    reason = str(reason or "configured").replace("|", "/")
    direction = str(direction or "neutral").replace("|", "/")
    if is_zone:
        return "%s|%s|%s|%.5f:%.5f|%s|%s|%s" % (symbol, source_timeframe, label, value[0], value[1], origin, reason, direction)
    return "%s|%s|%s|%.5f|%s|%s|%s" % (symbol, source_timeframe, label, value, origin, reason, direction)


def classify_level(candle, previous_close, value, is_zone, volatility, previous_state, level_kind=""):
    """Classify one closed candle; stronger outcomes intentionally win over touch."""
    lower, upper = value if is_zone else (value, value)
    level = (lower + upper) / 2
    opening, high, low, close = (_number(candle.get(key)) for key in ("open", "high", "low", "close"))
    span = max(high - low, 10 ** -6)
    body = abs(close - opening)
    buffer, penetration = volatility * BREAK_ATR_BUFFER * STRICTNESS_MULTIPLIER, volatility * SWEEP_PENETRATION_ATR * STRICTNESS_MULTIPLIER
    previous_close = _number(previous_close, opening)
    if previous_state.get("lifecycle") in {"invalidated", "expired"}:
        return None
    up_break = previous_close <= upper and candle_quality(candle, upper, "UP", volatility)
    down_break = previous_close >= lower and candle_quality(candle, lower, "DOWN", volatility)
    lifecycle = previous_state.get("lifecycle", "active")
    if lifecycle == "retest_failed" and up_break:
        return "KEY_LEVEL_RECLAIM_UP"
    if lifecycle == "retest_failed" and down_break:
        return "KEY_LEVEL_RECLAIM_DOWN"
    kind = str(level_kind).lower()
    support = any(token in kind for token in ("support", "previous day low"))
    resistance = any(token in kind for token in ("resistance", "previous day high"))
    if lifecycle == "broken_down":
        if previous_state.get("retest_held") and up_break:
            return "KEY_LEVEL_RECLAIM_UP"
        if previous_state.get("awaiting_retest") and high >= lower:
            if close >= upper + buffer:
                return "KEY_LEVEL_RETEST_FAILURE_UP"
            if close < lower - buffer:
                return "KEY_LEVEL_RETEST_HOLD_DOWN"
    if lifecycle == "broken_up":
        if previous_state.get("retest_held") and down_break:
            return "KEY_LEVEL_RECLAIM_DOWN"
        if previous_state.get("awaiting_retest") and low <= upper:
            if close <= lower - buffer:
                return "KEY_LEVEL_RETEST_FAILURE_DOWN"
            if close > upper + buffer:
                return "KEY_LEVEL_RETEST_HOLD_UP"
    # A sweep/rejection is an interaction with the level side, not a break of it.
    if (support or not resistance) and previous_close >= upper and low <= lower - penetration and close >= upper + buffer and body / span >= SWEEP_MIN_BODY_RATIO:
        return "KEY_LEVEL_SWEEP_UP"
    if (resistance or not support) and previous_close <= lower and high >= upper + penetration and close <= lower - buffer and body / span >= SWEEP_MIN_BODY_RATIO:
        return "KEY_LEVEL_SWEEP_DOWN"
    if (support or not resistance) and low <= lower and close >= upper + buffer and (min(opening, close) - low) / max(body, 10 ** -6) >= REJECTION_WICK_RATIO and body / span >= REJECTION_MIN_BODY_RATIO:
        return "KEY_LEVEL_REJECTION_UP"
    if (resistance or not support) and high >= upper and close <= lower - buffer and (high - max(opening, close)) / max(body, 10 ** -6) >= REJECTION_WICK_RATIO and body / span >= REJECTION_MIN_BODY_RATIO:
        return "KEY_LEVEL_REJECTION_DOWN"
    if up_break:
        return "KEY_LEVEL_BREAK_UP"
    if down_break:
        return "KEY_LEVEL_BREAK_DOWN"
    return None


def level_tolerance(value, volatility):
    """ATR/zone-aware tolerance used for coincidence grouping."""
    lower, upper = value if isinstance(value, tuple) else (value, value)
    return max(volatility * COINCIDENCE_ATR, (upper - lower) * 0.5)


def level_strength(source_timeframe, metadata=None):
    """Return a stable configurable strength score for alert filtering."""
    supplied = metadata.get("strength") if isinstance(metadata, dict) else None
    try:
        return float(supplied) if supplied is not None else 1.0 + TIMEFRAME_RANK.get(source_timeframe, 0) * 0.25
    except (TypeError, ValueError):
        return 1.0 + TIMEFRAME_RANK.get(source_timeframe, 0) * 0.25
