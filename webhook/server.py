"""HTTP server — WebhookHandler with GET and POST dispatch."""

import json
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from .app_logger import get_logger
from .commands import is_telegram_update
from .config import account_actions_enabled, load_dotenv, server_config
from .events import EVENT_HANDLERS
from .heartbeat import record_ea_heartbeat, start_heartbeat_monitor
from .messages import health_text
from .polling import reply_to_telegram_update, start_telegram_polling
from .trade_state import trade_config
from .account import STORE, due_reports, report_text

logger = get_logger()


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
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        if path == "/health":
            self.write_text(200, health_text())
            return
        if path == "/trade-config":
            symbol = urllib.parse.parse_qs(parsed_url.query).get("symbol", [None])[0]
            self.write_json(200, trade_config(symbol))
            return
        if path == "/account-action":
            secret = __import__("os").environ.get("ACCOUNT_ACTION_SECRET", "")
            if not account_actions_enabled() or not secret or self.headers.get("X-Account-Action-Key") != secret:
                self.write_text(403, "forbidden")
                return
            self.write_json(200, STORE.claim_action() or {})
            return
        self.send_error(404)

    def do_POST(self):
        if self.path == "/telegram":
            self.handle_telegram()
            return
        if self.path != "/webhook":
            logger.warning("Rejected request path=%s", self.path)
            self.write_text(404, "404 Not Found")
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length else ""
        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError:
            payload = body
            logger.warning("Webhook body is not JSON")

        if isinstance(payload, dict) and payload.get("event_type") == "EA_HEARTBEAT":
            record_ea_heartbeat(payload)
            self.write_text(200, "ok")
            return

        logger.info("Received webhook event_type=%s symbol=%s", payload.get("event_type") if isinstance(payload, dict) else None, payload.get("symbol") if isinstance(payload, dict) else None)

        try:
            if is_telegram_update(payload):
                reply_to_telegram_update(payload)
                self.write_text(200, "ok")
                return

            if isinstance(payload, dict):
                event_type = payload.get("event_type")
                handler = EVENT_HANDLERS.get(event_type)
                if handler:
                    handler(payload, self)
                    return

            logger.info(
                "Ignored unsupported payload event_type=%s",
                payload.get("event_type") if isinstance(payload, dict) else None,
            )
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"ignored")
        except Exception as error:
            logger.exception("Webhook handling failed")
            self.notify_error(error)
            self.send_response(500)
            self.end_headers()
            self.wfile.write(str(error).encode())

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

    def notify_error(self, error):
        try:
            from .messages import error_message
            from .telegram_sender import send_telegram_message
            send_telegram_message(error_message(error), retries=1)
        except Exception:
            logger.exception("Failed to send Telegram error notification")


def main():
    load_dotenv()
    host, port, public_url = server_config()
    logger.info("Starting webhook server host=%s port=%s public_url=%s", host, port, public_url)
    start_telegram_polling()
    start_heartbeat_monitor()
    def reports():
        while True:
            for name, start, end in due_reports(store=STORE):
                window = f"{name}:{start.isoformat()}:{end.isoformat()}"
                if not STORE.report_exists(window):
                    from .telegram_sender import send_telegram_message
                    try:
                        send_telegram_message(report_text(name, start, end))
                    except Exception:
                        logger.exception("Report delivery failed window=%s", window)
                    else:
                        STORE.report_sent(window)
            time.sleep(30)
    threading.Thread(target=reports, daemon=True).start()
    print(f"Listening on {public_url}")
    ThreadingHTTPServer((host, port), WebhookHandler).serve_forever()


if __name__ == "__main__":
    main()
