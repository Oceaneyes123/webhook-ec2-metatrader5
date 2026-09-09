"""Account-report Telegram command handlers."""

from .account import market_report, price_report, why_report
from .command_registry import register_command
from .json_data_parser import display_symbol
from .state import market_state


@register_command("/price", "/market", "/why")
def account_command(command, argument):
    symbol = display_symbol(argument).upper() if argument else ""
    if not symbol:
        return f"Usage: {command} Gold"
    if command == "/price":
        return price_report(symbol, market_state())
    if command == "/market":
        return market_report(symbol, market_state())
    return why_report(symbol)
