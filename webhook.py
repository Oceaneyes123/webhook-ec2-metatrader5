import json
import os
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from json_data_parser import engulfing_candle_message
from telegram_sender import send_telegram_message


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
            print(f"Server failed: {error}. Restarting in 5 seconds...", flush=True)
            time.sleep(5)


class WebhookHandler(BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path != "/webhook":
            self.send_error(404)
            return

        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode("utf-8") if length else ""
        try:
            payload = json.loads(body) if body else {}
        except json.JSONDecodeError:
            payload = body

        try:
            send_telegram_message(engulfing_candle_message(payload))
        except Exception as error:
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
    print(f"Listening on {public_url}")
    run_server(host, port)
