"""System and status Telegram command handlers."""

from .command_registry import register_command
from .config import telegram_configured
from .heartbeat import heartbeat_status_lines
from .json_data_parser import display_symbol
from .messages import help_text
from .state import (
    alerts_paused,
    recent_signal_count,
    recent_signals_for,
    set_alerts_paused,
)
from .trade_state import get_trade_mode, overtrade_config, symbol_trade_modes


def _symbol(argument):
    return display_symbol(argument).upper() if argument else ""


@register_command("/pause")
def pause(command, argument):
    set_alerts_paused(True)
    return "\u23f8\ufe0f MT5 alerts paused"


@register_command("/resume")
def resume(command, argument):
    set_alerts_paused(False)
    return "\u25b6\ufe0f MT5 alerts resumed"


@register_command("/status")
def status(command, argument):
    symbol = _symbol(argument)
    lines = [
        "\u2705 Bot online",
        f"Alerts: {'paused' if alerts_paused() else 'running'}",
        f"Telegram: {'configured' if telegram_configured() else 'missing'}",
        f"Recent signals: {recent_signal_count()}",
    ]
    if symbol:
        lines.append(f"Trade mode for {symbol}: {get_trade_mode(symbol)}")
    else:
        lines.append(f"Default trade mode: {get_trade_mode()}")
        overtrade = overtrade_config()
        lines.append(
            "Overtrade security: "
            f"{'enabled' if overtrade['enabled'] else 'disabled'} "
            f"(close at ${overtrade['profit_target']:.2f})"
        )
        overrides = symbol_trade_modes()
        if overrides:
            lines.append("Symbol overrides:")
            lines.extend(f"{name}: {mode}" for name, mode in sorted(overrides.items()))
        ea_lines = heartbeat_status_lines()
        if ea_lines:
            lines.append("")
            lines.append("EA status:")
            lines.extend(ea_lines)
    return "\n".join(lines)


@register_command("/help")
def help_command(command, argument):
    return help_text()


@register_command("/recent")
def recent(command, argument):
    symbol = _symbol(argument)
    if not symbol:
        return "Usage: /recent Gold"
    signals = recent_signals_for(symbol, limit=5)
    if not signals:
        return f"No recent {symbol} signals"
    lines = [f"{index}. {message}" for index, message in enumerate(signals, 1)]
    return f"Recent {symbol} signals:\n" + "\n".join(lines)
