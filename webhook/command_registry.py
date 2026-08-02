"""Registration and lookup for Telegram command handlers."""

COMMAND_HANDLERS = {}


def register_command(*names):
    """Register a handler for one or more Telegram command names."""

    def decorator(handler):
        for name in names:
            COMMAND_HANDLERS[name] = handler
        return handler

    return decorator


def get_command_handler(command):
    """Return the registered handler for *command*, if one exists."""

    return COMMAND_HANDLERS.get(command)
