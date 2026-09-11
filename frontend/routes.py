import base64
import hmac
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .ea_dashboard import EAS, grouped, update

TEMPLATES = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"), autoescape=select_autoescape())


def _authorized(handler):
    password = os.environ.get("DASHBOARD_PASSWORD", "")
    try: supplied = base64.b64decode(handler.headers.get("Authorization", "").removeprefix("Basic ")).decode().split(":", 1)[1]
    except (ValueError, UnicodeDecodeError, IndexError): supplied = ""
    return bool(password) and hmac.compare_digest(password, supplied)


def _require(handler):
    if _authorized(handler): return True
    handler.send_response(401); handler.send_header("WWW-Authenticate", 'Basic realm="MT5 configuration"'); handler.end_headers()
    return False


def dashboard(handler):
    if not _require(handler): return
    selected = parse_qs(urlparse(handler.path).query).get("ea", [EAS[0]])[0]
    if selected not in EAS: selected = EAS[0]
    handler.write_text(200, TEMPLATES.get_template("ea_dashboard.html").render(eas=EAS, selected=selected, groups=grouped(selected)), "text/html; charset=utf-8")


def api(handler):
    if not _require(handler): return
    name = parse_qs(urlparse(handler.path).query).get("ea", [""])[0]
    try:
        if handler.command == "GET": handler.write_json(200, {"ea": name, "groups": grouped(name)}); return
        raw = handler.rfile.read(int(handler.headers.get("Content-Length", 0)) or 0)
        values = json.loads(raw or b"{}").get("values", {}) if handler.headers.get("Content-Type", "").startswith("application/json") else {key.removeprefix("values."): value[-1] for key, value in parse_qs(raw.decode()).items() if key.startswith("values.")}
        update(name, values); handler.write_json(200, {"updated": list(values)})
    except (OSError, ValueError, json.JSONDecodeError) as error: handler.write_json(400, {"error": str(error)})
