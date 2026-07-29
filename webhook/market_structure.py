"""Closed-candle market structure and key-level interaction rules."""

from __future__ import annotations

from statistics import mean


TIMEFRAME_RANK = {"M30": 0, "H1": 1, "H4": 2, "D1": 3}
SWING_BARS = {"M30": 2, "H1": 2, "H4": 2, "D1": 2}
MAX_SWINGS = 80


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
    buffer = value_at_risk * 0.12
    if direction == "UP":
        return close >= level + buffer and body / span >= 0.5 and (close - low) / span >= 0.65
    return close <= level - buffer and body / span >= 0.5 and (high - close) / span >= 0.65


def confirm_structure(structure, symbol, timeframe, candles):
    """Confirm non-repainting external swings and emit BOS/CHoCH only from them."""
    frames = structure.setdefault(symbol, {})
    state = frames.get(timeframe)
    # Older state files stored only "UP"/"DOWN" here; discard that lossy model.
    if not isinstance(state, dict):
        state = frames[timeframe] = {"trend": "unknown", "swings": [], "broken": []}
    state.setdefault("swings", [])
    state.setdefault("broken", [])
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
            if prominent >= strength * 0.35:
                swing_id = "%s:%s:%s:%s" % (symbol, timeframe, kind, pivot.get("candle_time"))
                if not any(item["id"] == swing_id for item in state["swings"]):
                    state["swings"].append({"id": swing_id, "type": kind, "price": price, "time": pivot.get("candle_time"), "prominence": prominent, "broken": False})
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
            state["trend"] = "bullish"
            state["protected_low"] = lows[-1]
        elif highs[-1]["price"] < highs[-2]["price"] and lows[-1]["price"] < lows[-2]["price"]:
            state["trend"] = "bearish"
            state["protected_high"] = highs[-1]
    candle = candles[-1]
    events = []
    targets = (("UP", highs[-1] if highs else None), ("DOWN", lows[-1] if lows else None))
    for direction, swing in targets:
        if not swing or swing["id"] in state["broken"] or not candle_quality(candle, swing["price"], direction, strength):
            continue
        trend = state.get("trend", "unknown")
        protected = state.get("protected_low" if direction == "DOWN" else "protected_high")
        is_choch = (trend == "bullish" and direction == "DOWN" and protected and protected["id"] == swing["id"]) or (trend == "bearish" and direction == "UP" and protected and protected["id"] == swing["id"])
        is_bos = (trend == "bullish" and direction == "UP") or (trend == "bearish" and direction == "DOWN")
        if not (is_bos or is_choch):
            continue
        state["broken"].append(swing["id"])
        swing["broken"] = True
        if is_choch:
            state["trend"] = "ranging"  # wait for a new HH/HL or LH/LL before a BOS
            state["ranging_swing_ids"] = [item["id"] for item in state["swings"]]
        state["last_event"] = {"type": "CHOCH" if is_choch else "BOS", "direction": direction, "swing": swing, "candle_time": candle.get("candle_time")}
        events.append(state["last_event"])
    return events


def level_id(symbol, source_timeframe, label, value, is_zone):
    if is_zone:
        return "%s|%s|%s|%.5f:%.5f" % (symbol, source_timeframe, label, value[0], value[1])
    return "%s|%s|%s|%.5f" % (symbol, source_timeframe, label, value)


def classify_level(candle, previous_close, value, is_zone, volatility, previous_state):
    """Classify one closed candle; stronger outcomes intentionally win over touch."""
    lower, upper = value if is_zone else (value, value)
    level = (lower + upper) / 2
    opening, high, low, close = (_number(candle.get(key)) for key in ("open", "high", "low", "close"))
    span = max(high - low, 10 ** -6)
    body = abs(close - opening)
    buffer, penetration = volatility * 0.12, volatility * 0.15
    previous_close = _number(previous_close, opening)
    up_break = previous_close <= upper and candle_quality(candle, upper, "UP", volatility)
    down_break = previous_close >= lower and candle_quality(candle, lower, "DOWN", volatility)
    if previous_state.get("lifecycle") == "broken_down" and up_break:
        return "KEY_LEVEL_RECLAIM_UP"
    if previous_state.get("lifecycle") == "broken_up" and down_break:
        return "KEY_LEVEL_RECLAIM_DOWN"
    if up_break:
        return "KEY_LEVEL_BREAK_UP"
    if down_break:
        return "KEY_LEVEL_BREAK_DOWN"
    # A sweep must penetrate materially and recover; it is not a weak rejection.
    if low <= lower - penetration and close >= upper + buffer and body / span >= 0.35:
        return "KEY_LEVEL_SWEEP_UP"
    if high >= upper + penetration and close <= lower - buffer and body / span >= 0.35:
        return "KEY_LEVEL_SWEEP_DOWN"
    if low <= lower and close >= upper + buffer and (min(opening, close) - low) / max(body, 10 ** -6) >= 1.2 and body / span >= 0.25:
        return "KEY_LEVEL_REJECTION_UP"
    if high >= upper and close <= lower - buffer and (high - max(opening, close)) / max(body, 10 ** -6) >= 1.2 and body / span >= 0.25:
        return "KEY_LEVEL_REJECTION_DOWN"
    if previous_state.get("lifecycle") == "broken_up" and low <= upper and close > upper + buffer:
        return "KEY_LEVEL_RETEST_HOLD_UP"
    if previous_state.get("lifecycle") == "broken_down" and high >= lower and close < lower - buffer:
        return "KEY_LEVEL_RETEST_HOLD_DOWN"
    return None
