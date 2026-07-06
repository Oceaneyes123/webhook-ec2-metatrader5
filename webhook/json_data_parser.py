import html
import json
import os
from datetime import datetime, timedelta


SUPPORTED_EVENTS = {
    "ENGULFING_CANDLE": "Engulfing Candle",
    "HAMMER_CANDLE": "Hammer Candle",
    "HANGING_MAN_CANDLE": "Hanging Man Candle",
    "SHOOTING_STAR_CANDLE": "Shooting Star Candle",
    "INVERTED_HAMMER_CANDLE": "Inverted Hammer Candle",
    "MORNING_STAR": "Morning Star",
    "EVENING_STAR": "Evening Star",
    "INSIDE_BAR_BREAKOUT": "Inside Bar Breakout",
}

SYMBOL_ALIASES = {
    "GOLD": ["GOLD", "Gold", "Goldmicro", "Goldm#", "XAUUSD"],
}

# Load optional environment override for SYMBOL_ALIASES
_env_aliases = os.environ.get("SYMBOL_ALIASES_JSON")
if _env_aliases:
    try:
        _parsed = json.loads(_env_aliases)
        if isinstance(_parsed, dict):
            SYMBOL_ALIASES = _parsed
    except (json.JSONDecodeError, TypeError):
        pass

PATTERN_BIAS = {
    "HAMMER_CANDLE": ("BUY", "Bullish / BUY"),
    "HANGING_MAN_CANDLE": ("SELL", "Bearish / SELL"),
    "SHOOTING_STAR_CANDLE": ("SELL", "Bearish / SELL"),
    "INVERTED_HAMMER_CANDLE": ("BUY", "Bullish / BUY"),
    "MORNING_STAR": ("BUY", "Bullish / BUY"),
    "EVENING_STAR": ("SELL", "Bearish / SELL"),
}


def display_time(value):
    value = "" if value is None else str(value).strip()
    if not value:
        return ""
    for time_format in ("%Y.%m.%d %H:%M:%S", "%Y.%m.%d %H:%M"):
        try:
            parsed = datetime.strptime(value, time_format)
            break
        except ValueError:
            parsed = None
    if parsed is None:
        return value
    try:
        offset = float(os.getenv("TIMEZONE_OFFSET_HOURS", "5"))
    except ValueError:
        offset = 5
    return (parsed + timedelta(hours=offset)).strftime("%Y.%m.%d %I:%M %p")


def is_supported_payload(payload):
    return isinstance(payload, dict) and (
        payload.get("event_type") in SUPPORTED_EVENTS
        or payload.get("event_type") in ("TIMEFRAME_SNAPSHOT", "EA_ERROR", "EA_HEARTBEAT", "TRADE_CLOSE", "TRADE_OPEN")
    )


def display_symbol(value):
    symbol = str(value or "").strip()
    if not symbol:
        return ""
    # Build case-insensitive lookup: canonical => uppercase key
    alias_lookup = {}
    for canonical, aliases in SYMBOL_ALIASES.items():
        alias_lookup[canonical.lower()] = canonical
        for alias in aliases:
            alias_lookup[alias.lower()] = canonical
    # Check alias map first
    lower = symbol.lower()
    if lower in alias_lookup:
        return alias_lookup[lower]
    # Fallback cleanup for broker prefix/suffix
    for suffix in ("micro", "m#"):
        if symbol.lower().endswith(suffix):
            symbol = symbol[: -len(suffix)]
    for prefix in ("micro", "m#"):
        if symbol.lower().startswith(prefix):
            symbol = symbol[len(prefix) :]
    return symbol


def signal_and_bias(payload):
    fixed = PATTERN_BIAS.get(payload.get("event_type"))
    if fixed:
        return fixed
    signal = str(payload.get("signal", "")).upper()
    return signal, {
        "BUY": "Bullish / BUY",
        "SELL": "Bearish / SELL",
    }.get(signal, "Directional / UNKNOWN")


def candle_alert_message(payload):
    if not isinstance(payload, dict):
        raise ValueError("webhook payload must be a JSON object")

    required = ("timeframe", "open", "close")
    missing = [key for key in required if payload.get(key) in (None, "")]
    if not payload.get("candle_time") and not payload.get("time"):
        missing.append("candle_time")
    if missing:
        raise ValueError(f"missing required webhook field(s): {', '.join(missing)}")

    signal, bias = signal_and_bias(payload)
    direction = "📈" if signal == "BUY" else "📉" if signal == "SELL" else "📊"
    title = SUPPORTED_EVENTS.get(payload.get("event_type"), "Candle Alert")
    symbol = display_symbol(payload.get("symbol"))
    symbol_text = f"{html.escape(symbol)} " if symbol else ""
    candle_time = display_time(payload.get("candle_time", payload.get("time", "")))
    if all(payload.get(key) not in (None, "") for key in ("high", "low")):
        price = (
            f"O: {html.escape(str(payload['open']))} | "
            f"H: {html.escape(str(payload['high']))} | "
            f"L: {html.escape(str(payload['low']))} | "
            f"C: {html.escape(str(payload['close']))}"
        )
    else:
        price = (
            f"{html.escape(str(payload.get('open', '')))} - "
            f"{html.escape(str(payload.get('close', '')))}"
        )

    return (
        f"{direction} {symbol_text}{title} - "
        f"{html.escape(str(payload.get('timeframe', '')))}\n"
        f"Bias: {bias}\n"
        f"🕒 {html.escape(candle_time)}\n"
        f"💰 {price}"
    )


engulfing_candle_message = candle_alert_message
