"""Market-analysis Telegram command handlers."""

from .command_registry import register_command
from .json_data_parser import display_symbol
from .state import market_analyzer


@register_command("/summary", "/levels", "/rsi", "/vwap")
def market_command(command, argument):
    symbol = display_symbol(argument).upper() if argument else ""
    if not symbol:
        return f"Usage: {command} Gold"
    analyzer = market_analyzer()
    if command == "/summary":
        return analyzer.summary(symbol)
    if command == "/levels":
        return analyzer.levels(symbol)
    if command == "/vwap":
        return analyzer.vwap(symbol)
    return analyzer.rsi_summary(symbol)
