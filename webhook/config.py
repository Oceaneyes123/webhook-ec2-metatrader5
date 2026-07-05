"""Environment config loading and utility helpers."""

import os
import time
from pathlib import Path

from .app_logger import get_logger

logger = get_logger()
START_TIME = time.monotonic()


def load_dotenv(path=None):
    path = Path(path) if path is not None else Path(__file__).parent.parent / ".env"
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


def server_config():
    host = os.environ.get("HOST", "127.0.0.1")
    port = int(os.environ.get("PORT", "8000"))
    public_url = os.environ.get("PUBLIC_URL", f"http://{host}:{port}/webhook")
    return host, port, public_url


def polling_interval():
    return int(os.environ.get("TELEGRAM_POLL_SECONDS", "10"))


def heartbeat_stale_seconds():
    return int(os.environ.get("EA_HEARTBEAT_STALE_SECONDS", "90"))


def telegram_configured():
    return bool(os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"))


def uptime_text():
    seconds = int(time.monotonic() - START_TIME)
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {seconds}s"
    return f"{seconds}s"
