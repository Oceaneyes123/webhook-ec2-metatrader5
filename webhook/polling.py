"""Telegram long-polling — fetches updates and dispatches commands."""

import html
import tempfile
import threading
import time
from pathlib import Path

from .app_logger import get_logger
from .commands import command_reply, is_telegram_update
from .config import polling_interval
from .json_data_parser import display_symbol
from .state import MARKET_ANALYZER, MARKET_CHART
from . import telegram_sender as _tg

logger = get_logger()


def reply_to_telegram_update(update):
    message = update.get("message", {})
    text = message.get("text", "")
    chat_id = str(message.get("chat", {}).get("id", ""))
    if not text or not chat_id:
        return
    if maybe_send_levels_chart(text, chat_id):
        return
    _tg.send_telegram_message(command_reply(text), chat_id=chat_id)


def maybe_send_levels_chart(text, chat_id):
    parts = text.strip().split()
    command = parts[0].split("@", 1)[0].lower() if parts else ""
    if command != "/levels" or len(parts) < 2:
        return False
    symbol = display_symbol(parts[1]).upper()
    report = MARKET_ANALYZER.levels(symbol)
    safe_symbol = "".join(character for character in symbol if character.isalnum()) or "symbol"
    output_path = Path(tempfile.gettempdir()) / f"{safe_symbol.lower()}_key_levels.png"
    chart_path = MARKET_CHART.levels_chart(symbol, output_path)
    if not chart_path:
        logger.info("No levels chart data for symbol=%s; sending text report only", symbol)
        _tg.send_telegram_message(report, chat_id=chat_id)
        return True
    caption = report if len(report) <= 1000 else f"🧭 <b>{html.escape(symbol)} Key Levels</b>"
    logger.info("Sending levels chart photo symbol=%s path=%s", symbol, chart_path)
    _tg.send_telegram_photo(str(chart_path), caption=caption, chat_id=chat_id)
    if caption != report:
        _tg.send_telegram_message(report, chat_id=chat_id)
    return True


def poll_telegram_once(offset=None):
    updates = _tg.get_telegram_updates(offset=offset, timeout_seconds=polling_interval())
    for update in updates:
        reply_to_telegram_update(update)
    if not updates:
        return offset
    return max(update["update_id"] for update in updates) + 1


def poll_telegram_forever():
    offset = None
    while True:
        try:
            offset = poll_telegram_once(offset)
        except Exception:
            logger.exception("Telegram polling failed")
            time.sleep(polling_interval())


def start_telegram_polling():
    thread = threading.Thread(target=poll_telegram_forever, daemon=True)
    thread.start()
    return thread
