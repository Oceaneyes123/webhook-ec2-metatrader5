def engulfing_candle_message(payload):
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

    return (
        f"{direction} Engulfing Candle - {payload.get('timeframe', '')}\n"
        f"🕒 {payload.get('candle_time', payload.get('time', ''))}\n"
        f"💰 {payload.get('open', '')} - {payload.get('close', '')}"
    )
