"""Tests for telegram_sender — send_message, get_updates, retries."""
from __future__ import annotations

import json
import os
import time
import unittest
import urllib.error
import urllib.parse
from io import BytesIO
from unittest.mock import patch

from webhook import telegram_sender
from tests.test_helpers import collect_requests, fake_urlopen_ok


class SendTelegramMessageTest(unittest.TestCase):
    """Telegram message sending behaviour."""

    def test_send_telegram_message_posts_to_send_message_api(self):
        urlopen_fn, requests = collect_requests()

        with patch.dict(
            os.environ,
            {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID": "chat"},
        ), patch("urllib.request.urlopen", urlopen_fn):
            telegram_sender.send_telegram_message(
                "📊 Engulfing Candle - M15\n"
                "Bias: Directional / UNKNOWN\n"
                "🕒 2026.06.26 05:00 PM\n"
                "💰 1.2345 - 1.2360"
            )

        request, timeout = requests[0]
        self.assertEqual(
            request.full_url,
            "https://api.telegram.org/bottoken/sendMessage",
        )
        self.assertEqual(timeout, 10)
        self.assertEqual(request.headers["Content-type"], "application/json")
        self.assertEqual(
            json.loads(request.data),
            {
                "chat_id": "chat",
                "text": "📊 Engulfing Candle - M15\n"
                "Bias: Directional / UNKNOWN\n"
                "🕒 2026.06.26 05:00 PM\n"
                "💰 1.2345 - 1.2360",
                "parse_mode": "HTML",
            },
        )

    def test_send_telegram_message_can_override_chat_id(self):
        urlopen_fn, requests = collect_requests()

        with patch.dict(
            os.environ,
            {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID": "default"},
        ), patch("urllib.request.urlopen", urlopen_fn):
            telegram_sender.send_telegram_message("message", chat_id="command-chat")

        self.assertEqual(
            json.loads(requests[0][0].data)["chat_id"], "command-chat"
        )

    def test_send_telegram_message_can_disable_html(self):
        urlopen_fn, requests = collect_requests()

        with patch.dict(
            os.environ,
            {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID": "chat"},
        ), patch("urllib.request.urlopen", urlopen_fn):
            telegram_sender.send_telegram_message("<raw>", parse_mode=None)

        self.assertNotIn("parse_mode", json.loads(requests[0][0].data))

    def test_send_telegram_message_includes_telegram_error_body(self):
        def raise_error(_request, _timeout=None, **kwargs):
            raise urllib.error.HTTPError(
                "https://api.telegram.org/bottoken/sendMessage",
                400,
                "Bad Request",
                {},
                BytesIO(b'{"description":"Bad Request: chat not found"}'),
            )

        with patch.dict(
            os.environ,
            {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID": "chat"},
        ), patch("urllib.request.urlopen", raise_error):
            with self.assertRaisesRegex(Exception, "chat not found"):
                telegram_sender.send_telegram_message("message")

    def test_send_telegram_message_retries_connection_errors(self):
        from tests.test_helpers import urlopen_first_error_then_ok

        urlopen_fn, requests = urlopen_first_error_then_ok()

        with patch.dict(
            os.environ,
            {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID": "chat"},
        ), patch("urllib.request.urlopen", urlopen_fn), patch("time.sleep"):
            telegram_sender.send_telegram_message("message")

        self.assertEqual(len(requests), 2)


class GetTelegramUpdatesTest(unittest.TestCase):
    """Polling for incoming updates."""

    def test_get_telegram_updates_uses_offset_and_timeout(self):
        requests = []

        def fake_urlopen(request, timeout):
            requests.append((request, timeout))

            class Response:
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return None

                def read(self):
                    return b'{"ok":true,"result":[{"update_id":7}]}'

            return Response()

        with patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "token"}), patch(
            "urllib.request.urlopen", fake_urlopen
        ):
            updates = telegram_sender.get_telegram_updates(
                offset=6, timeout_seconds=10
            )

        request, timeout = requests[0]
        query = urllib.parse.parse_qs(
            urllib.parse.urlparse(request.full_url).query
        )
        self.assertEqual(
            request.full_url.split("?", 1)[0],
            "https://api.telegram.org/bottoken/getUpdates",
        )
        self.assertEqual(query, {"timeout": ["10"], "offset": ["6"]})
        self.assertEqual(timeout, 15)
        self.assertEqual(updates, [{"update_id": 7}])


if __name__ == "__main__":
    unittest.main()
