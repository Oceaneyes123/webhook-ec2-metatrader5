"""EA webhook event dispatcher — strongly-typed handlers by event_type."""

from .app_logger import get_logger
from .json_data_parser import candle_alert_message, display_symbol
from .messages import ea_issue_message, error_message, trade_close_message, trade_open_message
from . import state as _state
from . import telegram_sender as _tg

logger = get_logger()

# Timeframe filter for candle pattern alerts (used by event handlers)
# Defined here so handlers can access it; the canonical constant lives in
# market_state and is re-exported through __init__.
from .market_state import PATTERN_TIMEFRAMES  # noqa: E402


# === Event Dispatcher ===
#
# Registers strongly-typed handlers for EA webhook event types.
# Adding a new event type is a one-function change — no touching do_POST().
EVENT_HANDLERS = {}


def register_handler(*event_types):
    """Decorator: register a function for one or more event types."""
    def decorator(fn):
        for event_type in event_types:
            EVENT_HANDLERS[event_type] = fn
        return fn
    return decorator


def notify_error(error):
    try:
        _tg.send_telegram_message(error_message(error), retries=1)
    except Exception:
        logger.exception("Failed to send Telegram error notification")


@register_handler("EA_ERROR")
def _handle_ea_error(payload, server):
    _tg.send_telegram_message(ea_issue_message(payload))
    server.write_text(200, "ok")


@register_handler("TRADE_CLOSE")
def _handle_trade_close(payload, server):
    logger.info(
        "Received TRADE_CLOSE from %s, %s",
        payload.get("source", "?"),
        payload.get("symbol", "?"),
    )
    _tg.send_telegram_message(trade_close_message(payload))
    server.write_text(200, "ok")


@register_handler("TRADE_OPEN")
def _handle_trade_open(payload, server):
    logger.info(
        "Received TRADE_OPEN from %s, %s, %s",
        payload.get("source", "?"),
        payload.get("symbol", "?"),
        payload.get("type", "?"),
    )
    _tg.send_telegram_message(trade_open_message(payload))
    server.write_text(200, "ok")


@register_handler("TIMEFRAME_SNAPSHOT")
def _handle_tf_snapshot(payload, server):
    notifications = _state.MARKET_STATE.update(payload)
    if not _state.ALERTS_PAUSED:
        for notification in notifications:
            message = candle_alert_message(notification)
            _tg.send_telegram_message(message)
            _state.MARKET_STATE.mark_notified(notification)
            _state.RECENT_SIGNALS.append({
                "symbol": display_symbol(notification.get("symbol")).upper(),
                "message": message,
            })
        del _state.RECENT_SIGNALS[:-50]
    else:
        for notification in notifications:
            _state.MARKET_STATE.mark_notified(notification)
    server.write_text(200, "ok")


@register_handler("ENGULFING_CANDLE", "HAMMER_CANDLE", "HANGING_MAN_CANDLE",
                   "SHOOTING_STAR_CANDLE", "INVERTED_HAMMER_CANDLE",
                   "MORNING_STAR", "EVENING_STAR", "INSIDE_BAR_BREAKOUT")
def _handle_candle_pattern(payload, server):
    if str(payload.get("timeframe", "")).upper() not in PATTERN_TIMEFRAMES:
        logger.info("Ignored candle pattern outside M15-H4")
        server.write_text(200, "ignored")
        return
    if _state.ALERTS_PAUSED:
        logger.info("Ignored webhook while alerts are paused")
        server.send_response(200)
        server.end_headers()
        server.wfile.write(b"paused")
        return
    message = candle_alert_message(payload)
    logger.info("Sending Telegram message=%r", message)
    _tg.send_telegram_message(message)
    _state.RECENT_SIGNALS.append({
        "symbol": display_symbol(payload.get("symbol")).upper(),
        "message": message,
    })
    del _state.RECENT_SIGNALS[:-50]
    server.write_text(200, "ok")
