"""Telegram command registry — maps /command strings to handler functions."""

import html
import tempfile
from pathlib import Path

from .app_logger import get_logger
from .config import telegram_configured
from .heartbeat import EA_HEARTBEATS, heartbeat_status_lines
from .json_data_parser import display_symbol
from .messages import help_text
from . import state as _state
from .telegram_sender import send_telegram_message, send_telegram_photo
from .trade_state import (
    TRADE_STATE,
    TRADE_MODE,
    get_trade_mode,
    set_trade_mode,
    trade_config,
)
from .account import market_report, price_report, why_report

logger = get_logger()


# === Command Registry ===
#
# Each handler receives (command, symbol). Returning None lets the caller fall
# through to /help. Use register_command to add a new command.
COMMAND_HANDLERS = {}


def register_command(*names):
    """Decorator: register a function for one or more Telegram commands."""
    def decorator(fn):
        for name in names:
            COMMAND_HANDLERS[name] = fn
        return fn
    return decorator


@register_command("/pause")
def _cmd_pause(command, symbol):
    _state.ALERTS_PAUSED = True
    return "⏸️ MT5 alerts paused"


@register_command("/resume")
def _cmd_resume(command, symbol):
    _state.ALERTS_PAUSED = False
    return "▶️ MT5 alerts resumed"


@register_command("/status")
def _cmd_status(command, symbol):
    lines = [
        "✅ Bot online",
        f"Alerts: {'paused' if _state.ALERTS_PAUSED else 'running'}",
        f"Telegram: {'configured' if telegram_configured() else 'missing'}",
        f"Recent signals: {len(_state.RECENT_SIGNALS)}",
    ]
    if symbol:
        lines.append(f"Trade mode for {symbol}: {get_trade_mode(symbol)}")
    else:
        lines.append(f"Default trade mode: {get_trade_mode()}")
        if TRADE_STATE["symbols"]:
            lines.append("Symbol overrides:")
            lines.extend(
                f"{name}: {mode}"
                for name, mode in sorted(TRADE_STATE["symbols"].items())
            )
        ea_lines = heartbeat_status_lines()
        if ea_lines:
            lines.append("")
            lines.append("EA status:")
            lines.extend(ea_lines)
    return "\n".join(lines)


@register_command("/help")
def _cmd_help(command, symbol):
    return help_text()


@register_command("/buy")
def _cmd_buy(command, symbol):
    set_trade_mode("BUY", symbol)
    config = trade_config(symbol)
    return (
        f"🟢 BUY limit mode enabled{' for ' + symbol if symbol else ''}\n"
        f"Lot: {config['lot_size']}\n"
        f"Trail: {config['trail_pips']} pips below EMA20\n"
        "Confluence: M5/M15 previous candle above EMA20 and M1 EMA20 > EMA50"
    )


@register_command("/sell")
def _cmd_sell(command, symbol):
    set_trade_mode("SELL", symbol)
    config = trade_config(symbol)
    return (
        f"🔴 SELL limit mode enabled{' for ' + symbol if symbol else ''}\n"
        f"Lot: {config['lot_size']}\n"
        f"Trail: {config['trail_pips']} pips above EMA20\n"
        "Confluence: M5/M15 previous candle below EMA20 and M1 EMA50 > EMA20"
    )


@register_command("/notrade")
def _cmd_notrade(command, symbol):
    set_trade_mode("NOTRADE", symbol)
    if symbol:
        return f"⏹️ Trading paused for {symbol}"
    return "⏹️ Trading paused. No buy or sell limit orders will be trailed."


@register_command("/recent")
def _cmd_recent(command, symbol):
    if not symbol:
        return "Usage: /recent Gold"
    signals = [item["message"] for item in _state.RECENT_SIGNALS if item["symbol"].upper() == symbol][-5:]
    if not signals:
        return f"No recent {symbol} signals"
    lines = [f"{index}. {message}" for index, message in enumerate(signals, 1)]
    return f"Recent {symbol} signals:\n" + "\n".join(lines)


@register_command("/summary", "/levels", "/rsi")
def _cmd_market_command(command, symbol):
    if not symbol:
        return f"Usage: {command} Gold"
    if command == "/summary":
        return _state.MARKET_ANALYZER.summary(symbol)
    if command == "/levels":
        return _state.MARKET_ANALYZER.levels(symbol)
    return _state.MARKET_ANALYZER.rsi_summary(symbol)


@register_command("/price", "/market", "/why")
def _cmd_account_command(command, symbol):
    if not symbol:
        return f"Usage: {command} Gold"
    if command == "/price":
        return price_report(symbol, _state.MARKET_STATE)
    if command == "/market":
        return market_report(symbol, _state.MARKET_STATE)
    return why_report(symbol)


def command_reply(text):
    parts = text.strip().split()
    command = parts[0].split("@", 1)[0].lower() if parts else ""
    symbol = display_symbol(parts[1]).upper() if len(parts) > 1 else ""

    handler = COMMAND_HANDLERS.get(command)
    if handler:
        return handler(command, symbol)
    return help_text()


def is_telegram_update(payload):
    return isinstance(payload, dict) and (isinstance(payload.get("message"), dict) or isinstance(payload.get("callback_query"), dict))
