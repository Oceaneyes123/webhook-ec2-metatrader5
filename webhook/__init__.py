"""Webhook package.

Application code imports directly from the module that owns each object.  The
small lazy map below preserves the package-level API used by existing callers
without importing and initializing the whole application on ``import webhook``.
"""

from importlib import import_module

_COMPAT_EXPORTS = {
    "EA_HEARTBEATS": ("heartbeat", "EA_HEARTBEATS"),
    "HEARTBEAT_ALERT_STATES": ("heartbeat", "HEARTBEAT_ALERT_STATES"),
    "MARKET_STATE": ("state", "MARKET_STATE"),
    "RECENT_SIGNALS": ("state", "RECENT_SIGNALS"),
    "WebhookHandler": ("server", "WebhookHandler"),
    "check_heartbeat_alerts": ("heartbeat", "check_heartbeat_alerts"),
    "command_reply": ("commands", "command_reply"),
    "ea_issue_message": ("messages", "ea_issue_message"),
    "ema_enabled": ("trade_state", "ema_enabled"),
    "get_trade_mode": ("trade_state", "get_trade_mode"),
    "health_text": ("messages", "health_text"),
    "heartbeat_stale_seconds": ("config", "heartbeat_stale_seconds"),
    "heartbeat_status_lines": ("heartbeat", "heartbeat_status_lines"),
    "help_text": ("messages", "help_text"),
    "is_supported_payload": ("json_data_parser", "is_supported_payload"),
    "load_dotenv": ("config", "load_dotenv"),
    "load_trade_state": ("trade_state", "load_trade_state"),
    "overtrade_config": ("trade_state", "overtrade_config"),
    "poll_telegram_once": ("polling", "poll_telegram_once"),
    "record_ea_heartbeat": ("heartbeat", "record_ea_heartbeat"),
    "save_trade_state": ("trade_state", "save_trade_state"),
    "send_telegram_message": ("telegram_sender", "send_telegram_message"),
    "strong_rsi_message": ("messages", "strong_rsi_message"),
    "telegram_configured": ("config", "telegram_configured"),
    "trade_config": ("trade_state", "trade_config"),
    "trade_state_path": ("trade_state", "trade_state_path"),
}

__all__ = sorted(_COMPAT_EXPORTS)


def __getattr__(name):
    target = _COMPAT_EXPORTS.get(name)
    if target is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module_name, attribute = target
    value = getattr(import_module(f".{module_name}", __name__), attribute)
    globals()[name] = value
    return value


def __dir__():
    return sorted(set(globals()) | set(_COMPAT_EXPORTS))
