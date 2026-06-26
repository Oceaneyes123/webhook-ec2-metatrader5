import json
import os
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from app_logger import get_logger
from json_data_parser import engulfing_candle_message, is_engulfing_payload
from telegram_sender import send_telegram_message


logger = get_logger()


def error_message(error):
    return f"⚠️ Webhook Error\n{type(error).__name__}: {error}"


def notify_error(error):
    try:
        send_telegram_message(error_message(error), retries=1)
    except Exception:
        logger.exception("Failed to send Telegram error notification")


def load_env(path=".env"):
    path = Path(path)
    if not path.exists():
        return

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def server_config():
    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8000"))
    public_url = os.environ.get("PUBLIC_URL", f"http://localhost:{port}/webhook")
    return host, port, public_url


def run_server(host, port):
    while True:
        try:
            HTTPServer((host, port), WebhookHandler).serve_forever()
        except KeyboardInterrupt:
            raise
        except Exception as error:
            logger.exception("Server failed, restarting")
            print(f"Server failed: {error}. Restarting in 5 seconds...", flush=True)
            time.sleep(5)


class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
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
            if not is_engulfing_payload(payload):
                logger.info("Ignored non-engulfing payload")
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ignored")
                return

            message = engulfing_candle_message(payload)
            logger.info("Sending Telegram message=%r", message)
            send_telegram_message(message)
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


if __name__ == "__main__":
    load_env()
    host, port, public_url = server_config()
    logger.info("Starting webhook server host=%s port=%s public_url=%s", host, port, public_url)
    print(f"Listening on {public_url}")
    run_server(host, port)
