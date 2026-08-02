"""Parsing helpers for Telegram command text."""


def parse_command(text):
    """Return a normalized command name and its raw second value."""

    parts = text.strip().split()
    command = parts[0].split("@", 1)[0].lower() if parts else ""
    argument = parts[1] if len(parts) > 1 else ""
    return command, argument
