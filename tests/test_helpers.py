"""Shared test utilities for webhook-ec2 tests.

Provides helpers used across multiple test modules:
  - make_handler        – create a WebhookHandler instance for testing
  - snapshot            – build a TIMEFRAME_SNAPSHOT payload
  - fake_urlopen_ok     – urlopen that returns {"ok": True}
  - collect_requests    – urlopen that records calls and returns OK
"""
from __future__ import annotations

import json
import urllib.error
from io import BytesIO
from pathlib import Path
from typing import Any


# ── HTTP Handler helpers ──────────────────────────────────────────────


def make_handler(webhook_mod: Any, path: str, body: bytes = b"", method: str = "POST"):
    """Return a bare ``WebhookHandler`` wired with dummy I/O.

    The handler's ``responses`` list accumulates ``(key, value)`` tuples
    passed to ``send_response`` / ``send_header``.
    """
    handler = webhook_mod.WebhookHandler.__new__(webhook_mod.WebhookHandler)
    handler.path = path
    handler.headers = {"Content-Length": str(len(body))}
    handler.rfile = BytesIO(body)
    handler.wfile = BytesIO()
    handler.responses = []
    handler.send_response = lambda code: handler.responses.append(("code", code))
    handler.send_header = lambda key, value: handler.responses.append((key, value))
    handler.end_headers = lambda: None
    return handler


def snapshot(timeframe: str, candle_time: str, **values: Any) -> dict[str, Any]:
    """Build a ``TIMEFRAME_SNAPSHOT`` payload with sensible defaults."""
    payload: dict[str, Any] = {
        "event_type": "TIMEFRAME_SNAPSHOT",
        "symbol": "GOLDmicro",
        "timeframe": timeframe,
        "candle_time": candle_time,
        "open": 2300.0,
        "high": 2310.0,
        "low": 2290.0,
        "close": 2305.0,
        "digits": 2,
        "notify_patterns": True,
    }
    payload.update(values)
    return payload


# ── Telegram mock helpers ─────────────────────────────────────────────


class _TelegramResponse:
    """File-like object that returns *data* when read."""

    def __init__(self, data: bytes):
        self._data = data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return None

    def read(self):
        return self._data


def fake_urlopen_ok(body: dict | None = None) -> Any:
    """Return a ``urlopen`` callable that always returns ``{"ok": True}``."""
    payload = json.dumps(body or {"ok": True}).encode()
    return lambda _request, _timeout=None: _TelegramResponse(payload)


def collect_requests(requests_list: list | None = None):
    """Return a ``urlopen`` callable that records ``(request, timeout)`` calls.

    The factory also returns a reference to the shared list so callers
    can inspect captured requests after the test runs.
    """
    if requests_list is None:
        requests_list = []

    def urlopen(request, timeout=None):
        requests_list.append((request, timeout))
        return _TelegramResponse(b'{"ok":true}')

    return urlopen, requests_list


def urlopen_first_error_then_ok(requests_list: list | None = None):
    """Return a ``urlopen`` that fails once, then succeeds on retry."""
    if requests_list is None:
        requests_list = []
    calls: list = []

    def urlopen(request, timeout=None):
        calls.append(request)
        requests_list.append((request, timeout))
        if len(calls) == 1:
            raise urllib.error.URLError("temporary network issue")
        return _TelegramResponse(b'{"ok":true}')

    return urlopen, requests_list


# ── MQ5 test constants ────────────────────────────────────────────────

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MQ5_SOURCE_DIR = PROJECT_ROOT / "mq5"

MQ5_RELATIVE_SOURCES = (
    Path("Webhook1.mq5"),
    Path("Webhook2.mq5"),
    Path("includes/WebhookCommon.mqh"),
    Path("includes/MarketSnapshot.mqh"),
    Path("includes/TradeManager.mqh"),
    Path("TPSL.mq5"),
)


def make_mq5_sources(source_dir: Path) -> None:
    """Write placeholder MQ5 source files under *source_dir*."""
    for relative in MQ5_RELATIVE_SOURCES:
        target = source_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(str(relative), encoding="utf-8")
