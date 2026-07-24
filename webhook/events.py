"""EA webhook event dispatcher — strongly-typed handlers by event_type."""

import time

from .app_logger import get_logger
from .json_data_parser import candle_alert_message, display_symbol
from .messages import big_move_message, ea_issue_message, error_message, key_level_message, strong_rsi_message, trade_close_message, trade_open_message
from . import state as _state
from . import telegram_sender as _tg
from .account import STORE, action_buttons, profit_alert, transaction_message

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


@register_handler("TRADE_TRANSACTION")
def _handle_trade_transaction(payload, server):
    event_id = str(payload.get("event_id") or payload.get("deal_ticket") or payload.get("order_ticket"))
    STORE.event(payload)
    kind = str(payload.get("transaction_type") or "")
    try:
        notify = payload.get("magic_number") not in (0, "0", None) and kind not in {"TRADE_TRANSACTION_REQUEST", "PENDING_ORDER_CREATED", "PENDING_ORDER_MODIFIED", "PENDING_ORDER_CANCELLED"} and (not kind.startswith("POSITION_SL_") or float(payload.get("sl_change_pips", 0)) >= 50)
    except (TypeError, ValueError):
        notify = False
    if notify and event_id and STORE.claim_delivery(event_id):
        try:
            _tg.send_telegram_message(transaction_message(payload))
        except Exception:
            logger.exception("Transaction delivery failed event_id=%s", event_id)
            raise
        STORE.delivered(event_id)
    alert = profit_alert(payload)
    alert_id = "profit-alert:%s" % (payload.get("position_ticket") or payload.get("ticket") or "")
    if alert and STORE.event({"event_id": alert_id, "event_type": "PROFIT_ALERT", "event_time": payload.get("event_time")}):
        pass
    if alert and STORE.claim_delivery(alert_id):
        try:
            _tg.send_telegram_message(alert, reply_markup=action_buttons())
        except Exception:
            logger.exception("Profit alert delivery failed event_id=%s", alert_id)
            raise
        STORE.delivered(alert_id)
    server.write_text(200, "ok")


@register_handler("ACCOUNT_RECONCILIATION")
def _handle_reconciliation(payload, server):
    _state_account = payload.get("positions", [])
    if isinstance(_state_account, list):
        for position in STORE.reconcile(_state_account, payload):
            if position.get("magic_number") in (0, "0", None):
                continue
            alert = profit_alert(position)
            alert_id = "profit-alert:%s" % (position.get("position_ticket") or position.get("ticket") or "")
            if alert:
                STORE.event({"event_id": alert_id, "event_type": "PROFIT_ALERT"})
            if alert and STORE.claim_delivery(alert_id):
                try:
                    _tg.send_telegram_message(alert, reply_markup=action_buttons())
                except Exception:
                    logger.exception("Profit alert delivery failed event_id=%s", alert_id)
                    raise
                STORE.delivered(alert_id)
    server.write_text(200, "ok")


@register_handler("ENTRY_DECISION")
def _handle_entry_decision(payload, server):
    STORE.decision(payload)
    server.write_text(200, "ok")


@register_handler("ACCOUNT_ACTION_RESULT")
def _handle_action_result(payload, server):
    request_id = str(payload.get("request_id", ""))
    if not STORE.event({"event_id": f"action-result:{request_id}", "event_type": "ACTION_AUDIT", **payload}):
        server.write_text(200, "ok")
        return
    STORE.action_result(request_id)
    results = payload.get("results", [])
    details = "\n".join(f"{item.get('ticket', '?')}: {item.get('status', '?')} — {item.get('reason', '?')}" for item in results if isinstance(item, dict))
    _tg.send_telegram_message(
        "<b>Account action result</b>\n"
        f"Action: {payload.get('action', '?')}\n"
        f"Modified: {payload.get('modified', 0)} | Skipped: {payload.get('skipped', 0)} | Failed: {payload.get('failed', 0)}\n"
        f"MT5 retcode: {payload.get('retcode', '?')} {payload.get('retcode_description', '')}"
        + (f"\n{details}" if details else "")
    )
    server.write_text(200, "ok")


@register_handler("BIG_MOVE")
def _handle_big_move(payload, server):
    if not _state.ALERTS_PAUSED:
        _tg.send_telegram_message(big_move_message(payload))
    server.write_text(200, "ok")


@register_handler("TIMEFRAME_SNAPSHOT")
def _handle_tf_snapshot(payload, server):
    STORE.event({**payload, "event_id": "snapshot:%s:%s:%s" % (payload.get("symbol"), payload.get("timeframe"), payload.get("candle_time"))})
    notifications = _state.MARKET_STATE.update(payload)
    if not _state.ALERTS_PAUSED:
        for notification in notifications:
            message = (
                key_level_message(notification)
                if notification.get("event_type") == "KEY_LEVEL_REACHED"
                else strong_rsi_message(notification)
                if notification.get("event_type") == "STRONG_RSI"
                else candle_alert_message(notification)
            )
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
