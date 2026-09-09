"""Strategy-report Telegram command handlers."""

from . import state
from .account import STORE
from .command_registry import register_command
from .json_data_parser import display_symbol
from .strategy import settings
from .strategy_journal import StrategyJournal, performance_report
from .strategy_runtime import decision, setup_message


@register_command("/setup", "/performance")
def strategy_report(command, argument):
    symbol = display_symbol(argument).upper() if argument else ""
    if not symbol:
        return f"Usage: {command} Gold"
    if command == "/performance":
        return performance_report(StrategyJournal(STORE).trades(symbol), symbol)
    return setup_message(decision(symbol, state.market_state(), settings()))
