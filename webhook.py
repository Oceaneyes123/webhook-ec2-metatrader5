import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

from app_logger import get_logger
from json_data_parser import candle_alert_message, display_symbol, is_supported_payload
from telegram_sender import get_telegram_updates, send_telegram_message


logger = get_logger()
START_TIME = time.monotonic()
ALERTS_PAUSED = False
RECENT_SIGNALS = []


def error_message(error):
    return f"⚠️ Webhook Error\n{type(error).__name__}: {error}"


def notify_error(error):
    try:
        send_telegram_message(error_message(error), retries=1)
    except Exception:
        logger.exception("Failed to send Telegram error notification")


def server_config():
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    public_url = os.environ.get("PUBLIC_URL", f"http://localhost:{port}/webhook")
    return host, port, public_url


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
        ]
    )


def command_reply(text):
    global ALERTS_PAUSED

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
    if command == "/recent":
        symbol = display_symbol(parts[1]).upper() if len(parts) > 1 else ""
        if not symbol:
            return "Usage: /recent Gold"
        signals = [item["message"] for item in RECENT_SIGNALS if item["symbol"].upper() == symbol][-5:]
        if not signals:
            return f"No recent {symbol} signals"
        lines = [f"{index}. {message}" for index, message in enumerate(signals, 1)]
        return f"Recent {symbol} signals:\n" + "\n".join(lines)
    return help_text()


def is_telegram_update(payload):
    return isinstance(payload, dict) and isinstance(payload.get("message"), dict)


def reply_to_telegram_update(update):
    message = update.get("message", {})
    text = message.get("text", "")
    chat_id = str(message.get("chat", {}).get("id", ""))
    if text and chat_id:
        send_telegram_message(command_reply(text), chat_id=chat_id)


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

    def do_GET(self):
        if self.path == "/health":
            self.write_text(200, health_text())
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
