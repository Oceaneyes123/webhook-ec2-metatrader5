"""Trading-mode and overtrade Telegram command handlers."""

import math

from .command_registry import register_command
from .json_data_parser import display_symbol
from .trade_state import (
    key_level_orders_enabled,
    ema_enabled,
    overtrade_config,
    set_key_level_orders_enabled,
    set_ema_enabled,
    set_overtrade_enabled,
    set_overtrade_profit_target,
    set_trade_mode,
    trade_config,
)


def _symbol(argument):
    return display_symbol(argument).upper() if argument else ""


@register_command("/buy")
def buy(command, argument):
    symbol = _symbol(argument)
    set_trade_mode("BUY", symbol)
    config = trade_config(symbol)
    return (
        f"\U0001f7e2 BUY limit mode enabled{' for ' + symbol if symbol else ''}\n"
        f"Lot: {config['lot_size']}\n"
        f"Trail: {config['trail_pips']} pips below EMA20\n"
        "Additional trails: 10 pips above M5 EMA20; 5 pips above M15 EMA20\n"
        "Confluence: M5/M15 previous candle above EMA20 and M1 EMA20 > EMA50"
    )


@register_command("/sell")
def sell(command, argument):
    symbol = _symbol(argument)
    set_trade_mode("SELL", symbol)
    config = trade_config(symbol)
    return (
        f"\U0001f534 SELL limit mode enabled{' for ' + symbol if symbol else ''}\n"
        f"Lot: {config['lot_size']}\n"
        f"Trail: {config['trail_pips']} pips above EMA20\n"
        "Additional trails: 10 pips below M5 EMA20; 5 pips below M15 EMA20\n"
        "Confluence: M5/M15 previous candle below EMA20 and M1 EMA50 > EMA20"
    )


@register_command("/auto")
def auto(command, argument):
    symbol = _symbol(argument)
    if not symbol:
        return "Usage: /auto Gold"
    set_trade_mode("AUTO", symbol)
    config = trade_config(symbol)
    return (
        f"\U0001f916 AUTO mode enabled for {symbol}\n"
        f"Lot: {config['lot_size']}\n"
        "Will trail the fully confirmed direction at M1 EMA20, M5 EMA20 +/− 10 "
        "pips, and M15 EMA20 +/− 5 pips."
    )


@register_command("/notrade")
def notrade(command, argument):
    symbol = _symbol(argument)
    set_trade_mode("NOTRADE", symbol)
    if symbol:
        return f"\u23f9\ufe0f Trading paused for {symbol}"
    return "\u23f9\ufe0f Trading paused. No buy or sell limit orders will be trailed."


@register_command("/overtrade")
def overtrade(command, argument):
    argument = argument.strip().lower()
    if not argument:
        config = overtrade_config()
        return (
            "Overtrade security is "
            f"{'enabled' if config['enabled'] else 'disabled'}. "
            f"Profit target: ${config['profit_target']:.2f}\n"
            "Usage: /overtrade on | off | <profit target>"
        )
    if argument == "on":
        config = set_overtrade_enabled(True)
        return f"Overtrade security enabled (close at ${config['profit_target']:.2f})."
    if argument == "off":
        set_overtrade_enabled(False)
        return "Overtrade security disabled."
    try:
        profit_target = float(argument)
    except ValueError:
        return "Usage: /overtrade on | off | <profit target>"
    if not math.isfinite(profit_target) or profit_target <= 0:
        return "Profit target must be a positive dollar amount."
    config = set_overtrade_profit_target(profit_target)
    return f"Overtrade profit target set to ${config['profit_target']:.2f}."


@register_command("/leveltrade")
def leveltrade(command, argument):
    argument = argument.strip().lower()
    if argument == "on":
        set_key_level_orders_enabled(True)
        return "Key-level limit orders enabled."
    if argument == "off":
        set_key_level_orders_enabled(False)
        return "Key-level limit orders disabled and existing key-level limits will be removed."
    return (
        "Key-level limit orders are "
        f"{'enabled' if key_level_orders_enabled() else 'disabled'}.\n"
        "Usage: /leveltrade on | off"
    )


@register_command("/ematrade")
def ematrade(command, argument):
    argument = argument.strip().lower()
    if argument == "on":
        set_ema_enabled(True)
        return "EMA trading enabled."
    if argument == "off":
        set_ema_enabled(False)
        return "EMA trading disabled."
    return (
        "EMA trading is "
        f"{'enabled' if ema_enabled() else 'disabled'}.\n"
        "Usage: /ematrade on | off"
    )
