"""Telegram message formatting — pure presentation helpers with no side effects."""

import html

from .config import telegram_configured, uptime_text
from .json_data_parser import display_symbol


def error_message(error):
    return (
        "⚠️ Webhook Error\n"
        f"{html.escape(type(error).__name__)}: {html.escape(str(error))}"
    )


def ea_issue_message(payload):
    source = str(payload.get("source", "")).strip()
    symbol = display_symbol(payload.get("symbol")).upper()
    timeframe = str(payload.get("timeframe", "")).upper()
    message = str(payload.get("message", "EA issue")).strip() or "EA issue"
    detail = str(payload.get("detail", "")).strip()
    lines = ["⚠️ EA Issue"]
    if source:
        lines.append(f"Source: <b>{html.escape(source)}</b>")
    if symbol:
        lines.append(f"Symbol: <b>{html.escape(symbol)}</b>")
    if timeframe:
        lines.append(f"Timeframe: <b>{html.escape(timeframe)}</b>")
    lines.append(html.escape(message))
    if detail:
        lines.append(f"<code>{html.escape(detail)}</code>")
    return "\n".join(lines)


def trade_close_message(payload):
    symbol = display_symbol(payload.get("symbol", "")).upper() or "?"
    reason = payload.get("reason", "MANUAL_CLOSE")
    profit = float(payload.get("profit", 0))
    balance = float(payload.get("balance", 0))

    reason_labels = {
        "TP_HIT": "🎯 TP Hit",
        "SL_HIT": "🛑 SL Hit",
        "MANUAL_CLOSE": "👋 Manual Close",
    }
    reason_label = reason_labels.get(reason, reason)

    emoji = "🟢" if profit >= 0 else "🔴"
    sign = "+" if profit >= 0 else ""

    return (
        f"{emoji} <b>Trade Closed</b>\n"
        f"Symbol: {symbol}\n"
        f"Reason: {reason_label}\n"
        f"P&L: {sign}{profit:.2f}\n"
        f"💰 Balance: {balance:.2f}"
    )


def trade_open_message(payload):
    symbol = display_symbol(payload.get("symbol", "")).upper() or "?"
    trade_type = str(payload.get("type", "")).upper()
    price = payload.get("price")
    volume = float(payload.get("volume", 0))
    sl = payload.get("sl")
    tp = payload.get("tp")

    emoji = "📈" if trade_type == "BUY" else "📉"
    lines = [
        f"{emoji} <b>Manual Trade Opened</b>",
        f"Symbol: {symbol}",
        f"Type: {'🟢 BUY' if trade_type == 'BUY' else '🔴 SELL'}",
    ]
    if price is not None:
        lines.append(f"Price: {html.escape(str(price))}")
    if volume > 0:
        lines.append(f"Volume: {volume:.2f}")
    if sl is not None and float(sl) > 0:
        lines.append(f"SL: {html.escape(str(sl))}")
    if tp is not None and float(tp) > 0:
        lines.append(f"TP: {html.escape(str(tp))}")

    return "\n".join(lines)


def big_move_message(payload):
    symbol = display_symbol(payload.get("symbol", "")).upper() or "?"
    value = lambda key: html.escape(str(payload.get(key, "?")))
    return (
        f"⚡ <b>Big M15 Move</b>\n"
        f"Symbol: {symbol}\n"
        f"🕒 {value('candle_time')}\n"
        f"Range: <code>{value('range')}</code>\n"
        f"Current D1 ATR(14): <code>{value('daily_atr')}</code>\n"
        f"Threshold: <code>{value('threshold')}</code> ({value('atr_percent')}%)"
    )


def help_text():
    return "\n".join(
        [
            "Telegram commands:",
            "/status - Check bot status",
            "/pause - Pause MT5 alerts",
            "/resume - Resume MT5 alerts",
            "/help - Show available commands",
            "/recent Gold - Last 5 signals on a pair",
            "/summary Gold - Multi-timeframe market summary",
            "/levels Gold - M15-H4 key levels",
            "/rsi Gold - RSI(14) 70/30 extremes",
            "/buy - Start trailing buy-limit mode",
            "/buy Gold - Start buy-limit mode for one symbol",
            "/sell - Start trailing sell-limit mode",
            "/sell Gold - Start sell-limit mode for one symbol",
            "/notrade - Stop trading activity",
            "/notrade Gold - Stop trading for one symbol",
        ]
    )


def health_text():
    # Import here to avoid circular dependency at module level
    from .state import ALERTS_PAUSED

    return "\n".join(
        [
            "✅ Webhook healthy",
            f"Telegram: {'configured' if telegram_configured() else 'missing'}",
            f"Alerts: {'paused' if ALERTS_PAUSED else 'running'}",
            f"Uptime: {uptime_text()}",
        ]
    )
