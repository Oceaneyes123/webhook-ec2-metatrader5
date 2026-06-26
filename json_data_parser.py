def engulfing_candle_message(payload):
    if not isinstance(payload, dict):
        payload = {}

    signal = str(payload.get("signal", "")).upper()
    direction = "📈" if signal == "BUY" else "📉" if signal == "SELL" else "📊"

    return (
        f"{direction} Engulfing Candle - {payload.get('timeframe', '')}\n"
        f"🕒 {payload.get('candle_time', payload.get('time', ''))}\n"
        f"💰 {payload.get('open', '')} - {payload.get('close', '')}"
    )
