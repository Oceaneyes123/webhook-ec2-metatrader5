"""Compatibility facade for the Telegram command surface."""

# Import handler modules once so their decorators populate the registry.
from . import command_account, command_market, command_system, command_trading  # noqa: F401, E402
from .command_parser import parse_command
from .command_registry import COMMAND_HANDLERS, get_command_handler, register_command
from .messages import help_text

__all__ = ["COMMAND_HANDLERS", "command_reply", "is_telegram_update", "register_command"]


def command_reply(text):
    command, argument = parse_command(text)
    handler = get_command_handler(command)
    if handler:
        return handler(command, argument)
    return help_text()


def is_telegram_update(payload):
    return isinstance(payload, dict) and (
        isinstance(payload.get("message"), dict) or isinstance(payload.get("callback_query"), dict)
    )
