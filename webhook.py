import html
import json
import os
import tempfile
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from app_logger import get_logger
from json_data_parser import candle_alert_message, display_symbol, is_supported_payload
from market_state import MarketState, PATTERN_TIMEFRAMES
from telegram_sender import get_telegram_updates, send_telegram_message, send_telegram_photo


def load_dotenv(path=None):
    path = Path(path) if path is not None else Path(__file__).with_name(".env")
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = (part.strip() for part in line.split("=", 1))
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)


load_dotenv()
logger = get_logger()
START_TIME = time.monotonic()
ALERTS_PAUSED = False
TRADE_MODE = "NOTRADE"
RECENT_SIGNALS = []
MARKET_STATE = MarketState()


def error_message(error):
    return (
        "⚠️ Webhook Error\n"
        f"{html.escape(type(error).__name__)}: {html.escape(str(error))}"
    )


def notify_error(error):
    try:
        send_telegram_message(error_message(error), retries=1)
    except Exception:
        logger.exception("Failed to send Telegram error notification")


def ea_issue_message(payload):
    source = str(payload.get("source", "")).strip()
    symbol = display_symbol(payload.get("symbol")).upper()
    timeframe = str(payload.get("timeframe", "")).upper()
    message = str(payload.get("message", "EA issue")).strip() or "EA issue"
    detail = str(payload.get("detail", "")).strip()
    lines = ["⚠️ EA Issue"]
    if source:
        lines.append(f"Source: <b>{html.escape(source)}</b>")
    if symbol:
        lines.append(f"Symbol: <b>{html.escape(symbol)}</b>")
    if timeframe:
        lines.append(f"Timeframe: <b>{html.escape(timeframe)}</b>")
    lines.append(html.escape(message))
    if detail:
        lines.append(f"<code>{html.escape(detail)}</code>")
    return "\n".join(lines)


def server_config():
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    public_url = os.environ.get("PUBLIC_URL", f"http://{host}:{port}/webhook")
    return host, port, public_url


def trade_config():
    return {
        "mode": TRADE_MODE,
        "lot_size": float(os.environ.get("TRADE_LOT_SIZE", "0.2")),
        "trail_pips": float(os.environ.get("TRAIL_PIPS", "20")),
    }


def polling_interval():
    return int(os.environ.get("TELEGRAM_POLL_SECONDS", "10"))


def uptime_text():
    seconds = int(time.monotonic() - START_TIME)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"


def telegram_configured():
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def health_text():
    return "\n".join(
        [
            "✅ Webhook healthy",
            f"Telegram: {'configured' if telegram_configured() else 'missing'}",
            f"Alerts: {'paused' if ALERTS_PAUSED else 'running'}",
            f"Uptime: {uptime_text()}",
        ]
    )


def help_text():
    return "\n".join(
        [
            "Telegram commands:",
            "/status - Check bot status",
            "/pause - Pause MT5 alerts",
            "/resume - Resume MT5 alerts",
            "/help - Show available commands",
            "/recent Gold - Last 5 signals on a pair",
            "/summary Gold - Multi-timeframe market summary",
            "/levels Gold - M15-H4 key levels",
            "/rsi Gold - RSI(14) 70/30 extremes",
            "/buy - Start trailing buy-limit mode",
            "/sell - Start trailing sell-limit mode",
            "/notrade - Stop trading activity",
        ]
    )


def command_reply(text):
    global ALERTS_PAUSED, TRADE_MODE

    parts = text.strip().split()
    command = parts[0].split("@", 1)[0].lower() if parts else ""
    if command == "/pause":
        ALERTS_PAUSED = True
        return "⏸️ MT5 alerts paused"
    if command == "/resume":
        ALERTS_PAUSED = False
        return "▶️ MT5 alerts resumed"
    if command == "/status":
        return "\n".join(
            [
                "✅ Bot online",
                f"Alerts: {'paused' if ALERTS_PAUSED else 'running'}",
                f"Telegram: {'configured' if telegram_configured() else 'missing'}",
                f"Recent signals: {len(RECENT_SIGNALS)}",
            ]
        )
    if command == "/help":
        return help_text()
    if command == "/buy":
        TRADE_MODE = "BUY"
        config = trade_config()
        return (
            "🟢 BUY limit mode enabled\n"
            f"Lot: {config['lot_size']}\n"
            f"Trail: {config['trail_pips']} pips below EMA20\n"
            "Confluence: M5/M15 previous candle above EMA20 and M1 EMA20 > EMA50"
        )
    if command == "/sell":
        TRADE_MODE = "SELL"
        config = trade_config()
        return (
            "🔴 SELL limit mode enabled\n"
            f"Lot: {config['lot_size']}\n"
            f"Trail: {config['trail_pips']} pips above EMA20\n"
            "Confluence: M5/M15 previous candle below EMA20 and M1 EMA50 > EMA20"
        )
    if command == "/notrade":
        TRADE_MODE = "NOTRADE"
        return "⏹️ Trading paused. No buy or sell limit orders will be trailed."
    if command == "/recent":
        symbol = display_symbol(parts[1]).upper() if len(parts) > 1 else ""
        if not symbol:
            return "Usage: /recent Gold"
        signals = [item["message"] for item in RECENT_SIGNALS if item["symbol"].upper() == symbol][-5:]
        if not signals:
            return f"No recent {symbol} signals"
        lines = [f"{index}. {message}" for index, message in enumerate(signals, 1)]
        return f"Recent {symbol} signals:\n" + "\n".join(lines)
    if command in ("/summary", "/levels", "/rsi"):
        if len(parts) < 2:
            return f"Usage: {command} Gold"
        symbol = display_symbol(parts[1]).upper()
        if command == "/summary":
            return MARKET_STATE.summary(symbol)
        if command == "/levels":
            return MARKET_STATE.levels(symbol)
        return MARKET_STATE.rsi_summary(symbol)
    return help_text()


def is_telegram_update(payload):
    return isinstance(payload, dict) and isinstance(payload.get("message"), dict)


def reply_to_telegram_update(update):
    message = update.get("message", {})
    text = message.get("text", "")
    chat_id = str(message.get("chat", {}).get("id", ""))
    if not text or not chat_id:
        return
    if maybe_send_levels_chart(text, chat_id):
        return
    send_telegram_message(command_reply(text), chat_id=chat_id)


def maybe_send_levels_chart(text, chat_id):
    parts = text.strip().split()
    command = parts[0].split("@", 1)[0].lower() if parts else ""
    if command != "/levels" or len(parts) < 2:
        return False
    symbol = display_symbol(parts[1]).upper()
    report = MARKET_STATE.levels(symbol)
    safe_symbol = "".join(character for character in symbol if character.isalnum()) or "symbol"
    output_path = Path(tempfile.gettempdir()) / f"{safe_symbol.lower()}_key_levels.png"
    chart_path = MARKET_STATE.levels_chart(symbol, output_path)
    if not chart_path:
        logger.info("No levels chart data for symbol=%s; sending text report only", symbol)
        send_telegram_message(report, chat_id=chat_id)
        return True
    caption = report if len(report) <= 1000 else f"🧭 <b>{html.escape(symbol)} Key Levels</b>"
    logger.info("Sending levels chart photo symbol=%s path=%s", symbol, chart_path)
    send_telegram_photo(str(chart_path), caption=caption, chat_id=chat_id)
    if caption != report:
        send_telegram_message(report, chat_id=chat_id)
    return True


def poll_telegram_once(offset=None):
    updates = get_telegram_updates(offset=offset, timeout_seconds=polling_interval())
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


class WebhookHandler(BaseHTTPRequestHandler):
    def write_text(self, code, text, content_type="text/plain; charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(text.encode())

    def write_json(self, code, payload):
        self.write_text(
            code,
            json.dumps(payload, separators=(",", ":")),
            "application/json; charset=utf-8",
        )

    def do_GET(self):
        path = urllib.parse.urlparse(self.path).path
        if path == "/health":
            self.write_text(200, health_text())
            return
        if path == "/trade-config":
            self.write_json(200, trade_config())
            return
        self.send_error(404)

    def do_POST(self):
        if self.path == "/telegram":
            self.handle_telegram()
            return
        if self.path != "/webhook":
            logger.warning("Rejected request path=%s", self.path)
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length else ""
        logger.info("Received webhook body=%s", body)
        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError:
            payload = body
            logger.warning("Webhook body is not JSON")
        logger.info("Parsed webhook payload=%r", payload)

        try:
            if is_telegram_update(payload):
                reply_to_telegram_update(payload)
                self.write_text(200, "ok")
                return
            if not is_supported_payload(payload):
                logger.info("Ignored unsupported payload")
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ignored")
                return
            if payload.get("event_type") == "EA_ERROR":
                send_telegram_message(ea_issue_message(payload))
                self.write_text(200, "ok")
                return
            if payload.get("event_type") == "TIMEFRAME_SNAPSHOT":
                notifications = MARKET_STATE.update(payload)
                if not ALERTS_PAUSED:
                    for notification in notifications:
                        message = candle_alert_message(notification)
                        send_telegram_message(message)
                        MARKET_STATE.mark_notified(notification)
                        RECENT_SIGNALS.append(
                            {
                                "symbol": display_symbol(
                                    notification.get("symbol")
                                ).upper(),
                                "message": message,
                            }
                        )
                    del RECENT_SIGNALS[:-50]
                else:
                    for notification in notifications:
                        MARKET_STATE.mark_notified(notification)
                self.write_text(200, "ok")
                return
            if str(payload.get("timeframe", "")).upper() not in PATTERN_TIMEFRAMES:
                logger.info("Ignored candle pattern outside M15-H4")
                self.write_text(200, "ignored")
                return
            if ALERTS_PAUSED:
                logger.info("Ignored webhook while alerts are paused")
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"paused")
                return

            message = candle_alert_message(payload)
            logger.info("Sending Telegram message=%r", message)
            send_telegram_message(message)
            RECENT_SIGNALS.append(
                {"symbol": display_symbol(payload.get("symbol")).upper(), "message": message}
            )
            del RECENT_SIGNALS[:-50]
        except Exception as error:
            logger.exception("Webhook handling failed")
            notify_error(error)
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(error).encode())
            return

        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"ok")

    def handle_telegram(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length else ""
        try:
            update = json.loads(body) if body else {}
            reply_to_telegram_update(update)
        except Exception as error:
            logger.exception("Telegram command handling failed")
            self.write_text(500, str(error))
            return
        self.write_text(200, "ok")


if __name__ == "__main__":
    host, port, public_url = server_config()
    logger.info("Starting webhook server host=%s port=%s public_url=%s", host, port, public_url)
    start_telegram_polling()
    print(f"Listening on {public_url}")
    HTTPServer((host, port), WebhookHandler).serve_forever()
