from datetime import datetime, timedelta


SUPPORTED_EVENTS = {
    "ENGULFING_CANDLE": "Engulfing Candle",
    "HAMMER_CANDLE": "Hammer Candle",
    "HANGING_MAN_CANDLE": "Hanging Man Candle",
}


def display_time(value):
    try:
        parsed = datetime.strptime(value, "%Y.%m.%d %H:%M:%S")
    except ValueError:
        parsed = datetime.strptime(value, "%Y.%m.%d %H:%M")
    return (parsed + timedelta(hours=5)).strftime("%Y.%m.%d %I:%M %p")


def is_supported_payload(payload):
    return isinstance(payload, dict) and payload.get("event_type") in SUPPORTED_EVENTS


def display_symbol(value):
    symbol = str(value or "").strip()
    for suffix in ("micro", "m#"):
        if symbol.lower().endswith(suffix):
            symbol = symbol[: -len(suffix)]
    for prefix in ("micro", "m#"):
        if symbol.lower().startswith(prefix):
            symbol = symbol[len(prefix) :]
    return symbol


def candle_alert_message(payload):
    if not isinstance(payload, dict):
        raise ValueError("webhook payload must be a JSON object")

    required = ("timeframe", "open", "close")
    missing = [key for key in required if payload.get(key) in (None, "")]
    if not payload.get("candle_time") and not payload.get("time"):
        missing.append("candle_time")
    if missing:
        raise ValueError(f"missing required webhook field(s): {', '.join(missing)}")

    signal = str(payload.get("signal", "")).upper()
    direction = "📈" if signal == "BUY" else "📉" if signal == "SELL" else "📊"
    title = SUPPORTED_EVENTS.get(payload.get("event_type"), "Candle Alert")
    symbol = display_symbol(payload.get("symbol"))
    symbol_text = f"{symbol} " if symbol else ""
    candle_time = display_time(payload.get("candle_time", payload.get("time", "")))

    return (
        f"{direction} {symbol_text}{title} - {payload.get('timeframe', '')}\n"
        f"🕒 {candle_time}\n"
        f"💰 {payload.get('open', '')} - {payload.get('close', '')}"
    )


engulfing_candle_message = candle_alert_message
