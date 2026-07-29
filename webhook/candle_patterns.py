"""Closed-candle pattern qualification.

MT5 remains the raw geometry detector.  This module scores that raw event with
the snapshot context before it becomes a normal notification.
"""

import json
import math
import os
from datetime import datetime
from zoneinfo import ZoneInfo


PATTERN_NAMES = {
    "ENGULFING_CANDLE", "HAMMER_CANDLE", "HANGING_MAN_CANDLE",
    "SHOOTING_STAR_CANDLE", "INVERTED_HAMMER_CANDLE", "MORNING_STAR",
    "EVENING_STAR", "INSIDE_BAR_BREAKOUT",
}

PATTERN_CONFIRMATION_DEFAULTS = {
    "ENGULFING_CANDLE": "immediate",
    "HAMMER_CANDLE": "follow_through",
    "HANGING_MAN_CANDLE": "follow_through",
    "SHOOTING_STAR_CANDLE": "follow_through",
    "INVERTED_HAMMER_CANDLE": "follow_through",
    "MORNING_STAR": "follow_through",
    "EVENING_STAR": "follow_through",
    "INSIDE_BAR_BREAKOUT": "follow_through",
}


def _float(value):
    try:
        value = float(value)
        return value if math.isfinite(value) else None
    except (TypeError, ValueError):
        return None


def _setting(name, default, cast=float):
    try:
        return cast(os.environ.get(name, default))
    except (TypeError, ValueError):
        return cast(default)


def _csv_setting(name, default):
    return {item.strip().upper() for item in os.environ.get(name, default).split(",") if item.strip()}


def enabled_pattern_types():
    return _csv_setting("PATTERN_ENABLED_TYPES", ",".join(sorted(PATTERN_NAMES)))


def enabled_pattern_timeframes():
    return _csv_setting("PATTERN_ENABLED_TIMEFRAMES", "M15,M30,H1,H4")


def debug_logging_enabled():
    return os.environ.get("PATTERN_DEBUG_LOGGING", "false").lower() in {"1", "true", "yes"}


def invalidation_alerts_enabled():
    return os.environ.get("PATTERN_INVALIDATION_ALERTS", "false").lower() in {"1", "true", "yes"}


def pattern_invalidation(pattern, history):
    """Return a reason when a later closed candle decisively breaks the setup."""
    if pattern.get("lifecycle") not in {"qualified", "awaiting_confirmation", "confirmed", "alerted"}:
        return None
    candles = [_candle(item) for item in history or []]
    candles = [item for item in candles if item]
    index = next((index for index, item in enumerate(candles) if item.get("candle_time") == pattern.get("candle_time")), None)
    if index is None or index >= len(candles) - 1:
        return None
    current = candles[-1]
    atr_values = [item["high"] - item["low"] for item in candles[-14:] if item["high"] > item["low"]]
    atr = sum(atr_values) / len(atr_values) if atr_values else 0.0
    buffer = atr * _setting("PATTERN_INVALIDATION_ATR_RATIO", 0.10)
    low = _float(pattern.get("invalidation_low", pattern.get("low")))
    high = _float(pattern.get("invalidation_high", pattern.get("high")))
    if pattern.get("signal") == "BUY" and low is not None and current["close"] < low - buffer:
        return f"Closed below invalidation {low}"
    if pattern.get("signal") == "SELL" and high is not None and current["close"] > high + buffer:
        return f"Closed above invalidation {high}"
    return None


def confirmation_mode(event_type, countertrend=False):
    """Resolve the documented per-pattern mode, with stricter countertrend defaults."""
    default = PATTERN_CONFIRMATION_DEFAULTS.get(event_type, "follow_through")
    mode = os.environ.get(
        f"PATTERN_{event_type}_CONFIRMATION_MODE",
        os.environ.get("PATTERN_CONFIRMATION_MODE", default),
    ).lower()
    if mode not in {"immediate", "follow_through", "retest", "structure_confirmed"}:
        mode = default
    if countertrend and mode == "immediate" and os.environ.get("PATTERN_COUNTERTREND_IMMEDIATE", "false").lower() not in {"1", "true", "yes"}:
        return "follow_through"
    return mode


def _candle(item):
    if not isinstance(item, dict):
        return None
    values = {key: _float(item.get(key)) for key in ("open", "high", "low", "close")}
    if any(value is None for value in values.values()) or values["high"] < max(values["open"], values["close"]) or values["low"] > min(values["open"], values["close"]):
        return None
    result = values | {"candle_time": item.get("candle_time", item.get("time"))}
    for key in ("tick_volume", "volume", "session", "daily_atr"):
        if item.get(key) is not None:
            result[key] = item[key]
    return result


def _geometry(candle, previous=None):
    if not candle:
        return {}
    body = abs(candle["close"] - candle["open"])
    range_ = candle["high"] - candle["low"]
    return {
        "body": body,
        "range": range_,
        "body_ratio": body / range_ if range_ else 0,
        "upper_wick": candle["high"] - max(candle["open"], candle["close"]),
        "lower_wick": min(candle["open"], candle["close"]) - candle["low"],
        "previous_body_engulfed": (
            min(candle["open"], candle["close"]) <= min(previous["open"], previous["close"])
            and max(candle["open"], candle["close"]) >= max(previous["open"], previous["close"])
        ) if previous else False,
    }


def raw_detection(event_type, signal, history):
    """Return geometry validity and diagnostics for the last closed candle."""
    candles = [_candle(item) for item in history or []]
    candles = [item for item in candles if item]
    if not candles:
        return {"valid": None, "reasons": ["Raw geometry unavailable"]}
    current = candles[-1]
    previous = candles[-2] if len(candles) > 1 else None
    geometry = _geometry(current, previous)
    body_ratio = geometry["body_ratio"]
    min_body = _setting("PATTERN_MIN_BODY_RATIO", 0.10)
    wick_ratio = _setting("PATTERN_MIN_WICK_BODY_RATIO", 2.0)
    geometry_valid = geometry["range"] > 0 and body_ratio >= min_body
    valid = geometry_valid
    reasons = []
    if geometry["range"] <= 0 or body_ratio < min_body:
        valid = False
        reasons.append("Weak or invalid candle body")
    if event_type == "ENGULFING_CANDLE":
        valid = geometry_valid and bool(previous and geometry["previous_body_engulfed"] and ((previous["close"] < previous["open"] and current["close"] > current["open"]) or (previous["close"] > previous["open"] and current["close"] < current["open"])))
        if not valid:
            reasons.append("Body does not meaningfully engulf the previous candle")
    elif event_type in {"HAMMER_CANDLE", "HANGING_MAN_CANDLE"}:
        valid = geometry_valid and geometry["lower_wick"] >= max(geometry["body"] * wick_ratio, geometry["range"] * _setting("PATTERN_MIN_WICK_RANGE_RATIO", 0.35))
        if len(candles) >= 4:
            prior = [item["close"] for item in candles[-4:-1]]
            valid = valid and ((event_type == "HAMMER_CANDLE" and prior[-1] <= prior[0]) or (event_type == "HANGING_MAN_CANDLE" and prior[-1] >= prior[0]))
        if not valid:
            reasons.append("Lower rejection wick or prior movement is insufficient")
    elif event_type in {"SHOOTING_STAR_CANDLE", "INVERTED_HAMMER_CANDLE"}:
        valid = geometry_valid and geometry["upper_wick"] >= max(geometry["body"] * wick_ratio, geometry["range"] * _setting("PATTERN_MIN_WICK_RANGE_RATIO", 0.35))
        if len(candles) >= 4:
            prior = [item["close"] for item in candles[-4:-1]]
            valid = valid and ((event_type == "SHOOTING_STAR_CANDLE" and prior[-1] >= prior[0]) or (event_type == "INVERTED_HAMMER_CANDLE" and prior[-1] <= prior[0]))
        if not valid:
            reasons.append("Upper rejection wick or prior movement is insufficient")
    elif event_type in {"MORNING_STAR", "EVENING_STAR"}:
        if len(candles) < 3:
            return {"valid": False, "geometry": geometry, "reasons": ["Three-candle star sequence is incomplete"]}
        first, middle = candles[-3], candles[-2]
        first_geometry, middle_geometry = _geometry(first), _geometry(middle)
        valid = (
            geometry_valid and first_geometry["body_ratio"] >= min_body
            and middle_geometry["body_ratio"] <= _setting("PATTERN_STAR_MAX_MIDDLE_BODY_RATIO", 0.35)
            and ((signal == "BUY" and first["close"] < first["open"] and current["close"] > current["open"] and current["close"] >= (first["open"] + first["close"]) / 2)
                 or (signal == "SELL" and first["close"] > first["open"] and current["close"] < current["open"] and current["close"] <= (first["open"] + first["close"]) / 2))
        )
        if not valid:
            reasons.append("Three-candle star sequence is incomplete")
    elif event_type == "INSIDE_BAR_BREAKOUT":
        mother = candles[-3] if len(candles) > 2 else None
        inside = previous and mother and previous["high"] <= mother["high"] and previous["low"] >= mother["low"]
        displacement = abs(current["close"] - (mother["high"] if signal == "BUY" else mother["low"])) if mother else 0
        valid = geometry_valid and bool(inside and ((signal == "BUY" and current["close"] > mother["high"]) or (signal == "SELL" and current["close"] < mother["low"])) and displacement >= geometry["range"] * _setting("PATTERN_INSIDE_BREAKOUT_RATIO", 0.15))
        if not valid:
            reasons.append("Inside-bar breakout lacks displacement")
    return {"valid": valid, "geometry": geometry, "reasons": reasons}


def _nearest_level(price, snapshots):
    levels = _levels(snapshots)
    return min(((abs(price - value), timeframe, label, value) for timeframe, label, value in levels), default=None)


def _levels(snapshots):
    levels = []
    for timeframe, snapshot in snapshots.items():
        if not isinstance(snapshot, dict):
            continue
        values = snapshot.get("levels", {})
        for label in ("support", "resistance", "previous_day_high", "previous_day_low"):
            value = _float(values.get(label)) if isinstance(values, dict) else None
            if value is not None:
                levels.append((timeframe, label.replace("_", " ").title(), value))
        if isinstance(values, dict) and isinstance(values.get("fib"), dict):
            for label, value in values["fib"].items():
                value = _float(value)
                if value is not None:
                    levels.append((timeframe, f"Fib {label}", value))
    return levels


def _session_context(value):
    windows = {"Tokyo": (8, 17, 1.0), "London": (15, 24, 1.0), "New York": (20, 29, 1.0)}
    try:
        override = json.loads(os.environ.get("PATTERN_SESSION_WINDOWS", "{}"))
        for name, item in override.items():
            windows[name] = (int(item[0]), int(item[1]), float(item[2]) if len(item) > 2 else 1.0)
    except (TypeError, ValueError, json.JSONDecodeError, IndexError):
        pass
    try:
        parsed = datetime.strptime(str(value), "%Y.%m.%d %H:%M:%S")
    except (TypeError, ValueError):
        return {"name": "Unknown", "active": [], "weight": None}
    try:
        source = ZoneInfo(os.environ.get("PATTERN_CANDLE_TIMEZONE", "Asia/Manila"))
        destination = ZoneInfo(os.environ.get("PATTERN_SESSION_TIMEZONE", "Asia/Manila"))
        local = parsed.replace(tzinfo=source).astimezone(destination)
    except Exception:
        local = parsed
    hour = local.hour + local.minute / 60
    active = []
    weights = []
    for name, (start, end, default_weight) in windows.items():
        adjusted_hour = hour if hour >= start % 24 else hour + 24
        if start <= adjusted_hour < end:
            active.append(name)
            weights.append(_setting("PATTERN_SESSION_WEIGHT_" + name.upper().replace(" ", "_"), default_weight))
    return {"name": "/".join(active) + " overlap" if len(active) > 1 else active[0] if active else "Outside configured sessions", "active": active, "weight": sum(weights) / len(weights) if weights else 0.0}


def _daily_context(payload, snapshots):
    high, low = _float(payload.get("daily_high")), _float(payload.get("daily_low"))
    daily_range = high - low if high is not None and low is not None and high >= low else None
    d1 = snapshots.get("D1", {}) if isinstance(snapshots.get("D1", {}), dict) else {}
    d1_history = d1.get("candle_history", [])
    ranges = [float(item["high"]) - float(item["low"]) for item in d1_history[-14:] if _float(item.get("high")) is not None and _float(item.get("low")) is not None and float(item["high"]) >= float(item["low"])]
    daily_atr = _float(payload.get("daily_atr")) or _float(d1.get("daily_atr")) or (sum(ranges) / len(ranges) if ranges else None)
    consumed = daily_range / daily_atr if daily_range is not None and daily_atr else None
    return {"daily_range": daily_range, "daily_atr": daily_atr, "daily_atr_consumed": consumed, "daily_range_warning": consumed >= _setting("PATTERN_DAILY_ATR_WARNING_RATIO", 0.80) if consumed is not None else False}


def _volume_context(current, candles):
    values = [_float(item.get("tick_volume", item.get("volume"))) for item in candles[:-1][-10:]]
    current_volume = _float(current.get("tick_volume", current.get("volume")))
    values = [value for value in values if value is not None and value > 0]
    if current_volume is None or not values:
        return {"current": current_volume, "average": sum(values) / len(values) if values else None, "ratio": None}
    average = sum(values) / len(values)
    return {"current": current_volume, "average": average, "ratio": current_volume / average if average else None}


def _prior_movement(candles):
    closes = [item["close"] for item in candles[-6:-1]]
    if len(closes) < 2:
        return {"direction": "unknown", "strength": None}
    change = closes[-1] - closes[0]
    span = max(closes) - min(closes)
    return {"direction": "up" if change > 0 else "down" if change < 0 else "flat", "strength": abs(change) / span if span else 0.0}


def _level_interaction(current, previous, signal, snapshots, atr):
    price = current["close"]
    levels = _levels(snapshots)
    if not levels:
        return {"sweep": None, "opposing": None}
    relevant = []
    opposing = []
    for timeframe, label, value in levels:
        distance = abs(price - value)
        if distance <= atr * _setting("PATTERN_LEVEL_ATR_TOLERANCE", 0.50):
            relevant.append((distance, timeframe, label, value))
        is_opposing = (signal == "BUY" and "Resistance" in label) or (signal == "SELL" and "Support" in label)
        if is_opposing:
            opposing.append((distance, timeframe, label, value))
    sweep = None
    for distance, timeframe, label, value in relevant:
        penetration = value - current["low"] if signal == "BUY" else current["high"] - value
        swept = penetration >= atr * _setting("PATTERN_SWEEP_MIN_ATR_RATIO", 0.15) and ((signal == "BUY" and current["low"] < value and current["close"] > value) or (signal == "SELL" and current["high"] > value and current["close"] < value))
        if swept:
            sweep = {"timeframe": timeframe, "label": label, "price": value, "distance": distance, "penetration": penetration, "reclaimed": True}
            break
    nearby_opposing = min(opposing, default=None)
    return {"sweep": sweep, "opposing": ({"timeframe": nearby_opposing[1], "label": nearby_opposing[2], "price": nearby_opposing[3], "distance": nearby_opposing[0]} if nearby_opposing and nearby_opposing[0] <= atr * _setting("PATTERN_OPPOSING_LEVEL_ATR_TOLERANCE", 0.75) else None)}


def evaluate(event_type, signal, payload, history, snapshots):
    """Score one raw event.  Returns notification-ready context or suppression."""
    candles = [_candle(item) for item in history or []]
    candles = [item for item in candles if item]
    current = candles[-1] if candles else None
    if len(candles) < 2:
        return {"qualified": False, "confirmed": False, "confirmation_mode": "follow_through", "confidence": "Informational", "score": 0, "raw_valid": None, "reasons_reduced": ["Insufficient closed-candle history"], "confirmation_status": "Suppressed"}
    raw = raw_detection(event_type, signal, history)
    if raw["valid"] is False:
        return {"qualified": False, "confidence": "Informational", "score": 0, "raw_valid": False, "reasons_reduced": raw["reasons"]}
    if current and payload.get("candle_time") and current.get("candle_time") != payload.get("candle_time"):
        return {"qualified": False, "confidence": "Informational", "score": 0, "raw_valid": raw["valid"], "reasons_reduced": ["Pattern candle is not the latest closed candle"]}
    if not current:
        return {"qualified": False, "confirmed": False, "confidence": "Informational", "score": 0, "raw_valid": raw["valid"], "reasons_reduced": ["Missing candle history"], "confirmation_status": "Suppressed"}
    geometry = raw.get("geometry", _geometry(current))
    atr_values = [item["high"] - item["low"] for item in candles[-14:] if item["high"] > item["low"]]
    atr = sum(atr_values) / len(atr_values) if atr_values else 0
    score = 35
    passed, reduced = [], list(raw.get("reasons", []))
    if atr and geometry["range"] >= atr * _setting("PATTERN_MIN_ATR_RATIO", 0.35):
        score += 10; passed.append("Candle has meaningful ATR-relative size")
    elif atr:
        score -= 20; reduced.append("Candle is too small relative to ATR")
    level = _nearest_level(current["close"], snapshots)
    tolerance = atr * _setting("PATTERN_LEVEL_ATR_TOLERANCE", 0.50) if atr else 0
    if level and (not tolerance or level[0] <= tolerance):
        score += 25; passed.append(f"Near {level[2]} ({level[1]})")
    else:
        score -= 15; reduced.append("Far from a meaningful key level")
    timeframe = str(payload.get("timeframe", "")).upper()
    rank = {"M15": 0, "M30": 1, "H1": 2, "H4": 3, "D1": 4}
    higher = [
        (rank.get(str(frame).upper(), -1), snapshot)
        for frame, snapshot in snapshots.items()
        if rank.get(str(frame).upper(), -1) > rank.get(timeframe, -1)
        and isinstance(snapshot, dict)
    ]
    higher.sort(reverse=True, key=lambda item: item[0])
    higher_biases = [item[1].get("ema_bias") for item in higher if item[1].get("ema_bias") in {"BULLISH", "BEARISH"}]
    current_bias = higher_biases[0] if higher_biases else "unknown"
    aligned = (signal == "BUY" and current_bias == "BULLISH") or (signal == "SELL" and current_bias == "BEARISH")
    if aligned:
        score += 15; passed.append("Aligned with EMA trend")
    elif current_bias in {"BULLISH", "BEARISH"}:
        score -= 15; reduced.append("Countertrend against EMA bias")
    if geometry["range"] and geometry["range"] > atr * _setting("PATTERN_EXTREME_ATR_RATIO", 2.5):
        score -= 10; reduced.append("Extreme candle may be exhaustion")
    prior = _prior_movement(candles)
    volume = _volume_context(current, candles)
    if volume["ratio"] is not None:
        if volume["ratio"] >= _setting("PATTERN_VOLUME_EXPANSION_RATIO", 1.25):
            score += _setting("PATTERN_VOLUME_EXPANSION_SCORE", 8, int); passed.append("Tick volume expanded")
        elif volume["ratio"] <= _setting("PATTERN_LOW_VOLUME_RATIO", 0.70):
            score -= _setting("PATTERN_LOW_VOLUME_SCORE", 6, int); reduced.append("Tick volume is low")
    session = _session_context(current.get("candle_time"))
    if session["weight"] is not None:
        score += (session["weight"] - 1.0) * _setting("PATTERN_SESSION_SCORE", 5)
    daily = _daily_context(payload, snapshots)
    if daily["daily_range_warning"]:
        score -= _setting("PATTERN_DAILY_ATR_WARNING_SCORE", 8, int); reduced.append("Daily ATR mostly consumed")
    vwap = _float(payload.get("vwap"))
    previous_close = candles[-2]["close"] if len(candles) > 1 else None
    vwap_event = "unknown"
    if vwap is not None and previous_close is not None:
        if signal == "BUY" and previous_close < vwap <= current["close"]:
            score += _setting("PATTERN_VWAP_SCORE", 8, int); passed.append("VWAP reclaimed"); vwap_event = "reclaim"
        elif signal == "SELL" and previous_close > vwap >= current["close"]:
            score += _setting("PATTERN_VWAP_SCORE", 8, int); passed.append("VWAP rejected"); vwap_event = "rejection"
        elif (signal == "BUY" and current["close"] < vwap) or (signal == "SELL" and current["close"] > vwap):
            score -= _setting("PATTERN_VWAP_OPPOSING_SCORE", 5, int); reduced.append("VWAP position opposes direction"); vwap_event = "opposing"
    interaction = _level_interaction(current, candles[-2] if len(candles) > 1 else None, signal, snapshots, atr)
    if interaction["sweep"]:
        score += _setting("PATTERN_SWEEP_SCORE", 12, int); passed.append("Liquidity sweep reclaimed")
    if interaction["opposing"]:
        score -= _setting("PATTERN_OPPOSING_LEVEL_SCORE", 12, int); reduced.append("Nearby opposing level")
    confidence = "Fully confirmed" if score >= 85 else "Strong" if score >= 70 else "Moderate" if score >= 55 else "Weak" if score >= 40 else "Informational"
    minimum = _setting("PATTERN_MIN_ALERT_SCORE", 60, int)
    countertrend = current_bias in {"BULLISH", "BEARISH"} and not aligned
    strictness = _setting("PATTERN_COUNTERTREND_STRICTNESS", 1.0)
    if countertrend:
        score -= max(0.0, strictness - 1.0) * 10
    alignment_required = os.environ.get("PATTERN_REQUIRE_HTF_ALIGNMENT", "false").lower() in {"1", "true", "yes"}
    if alignment_required and current_bias == "unknown":
        score -= _setting("PATTERN_MISSING_HTF_SCORE", 15, int)
        reduced.append("Higher-timeframe alignment unavailable")
    mode = confirmation_mode(event_type, countertrend)
    qualified = score >= minimum and raw["valid"] is not False
    confirmed = qualified and mode == "immediate"
    if aligned and prior["direction"] == ("down" if signal == "BUY" else "up"):
        context_classification = "Pullback continuation"
    elif aligned:
        context_classification = "Trend-following"
    elif countertrend:
        context_classification = "Countertrend reversal"
    elif level:
        context_classification = "Range reaction"
    else:
        context_classification = "Unknown"
    return {
        "qualified": qualified, "confirmed": confirmed,
        "score": max(0, min(100, score)), "confidence": confidence,
        "raw_valid": raw["valid"], "body_ratio": geometry["body_ratio"],
        "atr_relative_size": geometry["range"] / atr if atr else None,
        "nearest_key_level": ({"timeframe": level[1], "label": level[2], "price": level[3], "distance": level[0]} if level else None),
        "reasons_passed": passed, "reasons_reduced": reduced,
        "context_classification": context_classification,
        "higher_timeframe_bias": current_bias,
        "higher_timeframe_alignment_required": alignment_required,
        "countertrend_strictness": strictness,
        "prior_movement": prior,
        "liquidity_sweep": interaction["sweep"], "opposing_level": interaction["opposing"],
        "vwap": vwap, "vwap_event": vwap_event,
        "session": session["name"], "session_weight": session["weight"],
        "daily_range": daily["daily_range"], "daily_atr": daily["daily_atr"],
        "daily_atr_consumed": daily["daily_atr_consumed"], "daily_range_warning": daily["daily_range_warning"],
        "tick_volume": volume["current"], "average_tick_volume": volume["average"], "tick_volume_ratio": volume["ratio"],
        "upper_wick_ratio": geometry["upper_wick"] / geometry["body"] if geometry["body"] else None,
        "lower_wick_ratio": geometry["lower_wick"] / geometry["body"] if geometry["body"] else None,
        "invalidation_low": min(item["low"] for item in candles[-3:]) if event_type in {"MORNING_STAR", "EVENING_STAR"} else (candles[-3]["low"] if event_type == "INSIDE_BAR_BREAKOUT" and len(candles) >= 3 else current["low"]),
        "invalidation_high": max(item["high"] for item in candles[-3:]) if event_type in {"MORNING_STAR", "EVENING_STAR"} else (candles[-3]["high"] if event_type == "INSIDE_BAR_BREAKOUT" and len(candles) >= 3 else current["high"]),
        "confirmation_mode": mode,
        "confirmation_status": "Confirmed" if confirmed else "Awaiting confirmation" if qualified else "Suppressed",
    }


def confirmation_result(pattern, history):
    """Evaluate the next closed candle for a persisted follow-through pattern."""
    if pattern.get("confirmation_mode") == "structure_confirmed":
        return "confirmed" if pattern.get("structure_confirmed") else None
    if pattern.get("confirmation_mode") not in {"follow_through", "retest"}:
        return None
    candles = [_candle(item) for item in history or []]
    candles = [item for item in candles if item]
    pattern_time = pattern.get("candle_time")
    index = next((index for index, item in enumerate(candles) if item.get("candle_time") == pattern_time), None)
    if index is None or index >= len(candles) - 1:
        return None
    next_candle = candles[index + 1]
    high = _float(pattern.get("high"))
    low = _float(pattern.get("low"))
    signal = pattern.get("signal")
    pattern_close = _float(pattern.get("close")) or next_candle["open"]
    if pattern.get("confirmation_mode") == "retest":
        confirmed = (signal == "BUY" and next_candle["low"] <= pattern_close and next_candle["close"] > pattern_close) or (signal == "SELL" and next_candle["high"] >= pattern_close and next_candle["close"] < pattern_close)
    else:
        confirmed = (signal == "BUY" and next_candle["close"] > (high or next_candle["open"])) or (signal == "SELL" and next_candle["close"] < (low or next_candle["open"]))
    failed = (signal == "BUY" and next_candle["close"] < (low or next_candle["open"])) or (signal == "SELL" and next_candle["close"] > (high or next_candle["open"]))
    return "confirmed" if confirmed else "failed" if failed else None
