import json
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path


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


def send_telegram_message(payload):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    text = payload if isinstance(payload, str) else json.dumps(payload, indent=2)
    data = json.dumps({"chat_id": chat_id, "text": text}).encode()
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(detail or str(error)) from error


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
            send_telegram_message(payload)
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
    HTTPServer((host, port), WebhookHandler).serve_forever()
