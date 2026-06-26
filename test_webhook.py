import json
import os
import tempfile
import time
import urllib.error
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import app_logger
import json_data_parser
import telegram_sender
import webhook


class WebhookTest(unittest.TestCase):
    def test_webhook_ignores_non_engulfing_candle_close(self):
        sent = []
        handler = webhook.WebhookHandler.__new__(webhook.WebhookHandler)
        handler.path = "/webhook"
        handler.headers = {
            "Content-Length": "170",
        }
        body = (
            b'{"event_type":"M1_CANDLE_CLOSE","message":"BUY candle closed",'
            b'"signal":"BUY","symbol":"GOLDmicro","timeframe":"M1",'
            b'"candle_time":"2026.06.26 11:11:00","open":4029.07,"close":4030.23}'
        )
        handler.headers["Content-Length"] = str(len(body))
        handler.rfile = BytesIO(body)
        handler.wfile = BytesIO()
        handler.send_response = lambda code: sent.append(("code", code))
        handler.end_headers = lambda: None

        with patch("webhook.send_telegram_message") as send:
            handler.do_POST()

        send.assert_not_called()
        self.assertIn(("code", 200), sent)
        self.assertEqual(handler.wfile.getvalue(), b"ignored")

    def test_send_telegram_message_posts_to_send_message_api(self):
        requests = []

        def fake_urlopen(request, timeout):
            requests.append((request, timeout))

            class Response:
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return None

                def read(self):
                    return b'{"ok":true}'

            return Response()

        with patch.dict(
            os.environ,
            {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID": "chat"},
        ), patch("urllib.request.urlopen", fake_urlopen):
            telegram_sender.send_telegram_message(
                json_data_parser.candle_alert_message(
                    {
                        "event_type": "ENGULFING_CANDLE",
                        "timeframe": "M15",
                        "candle_time": "2026.06.26 12:00",
                        "open": "1.2345",
                        "close": "1.2360",
                    }
                )
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
                "🕒 2026.06.26 05:00 PM\n"
                "💰 1.2345 - 1.2360",
            },
        )

    def test_engulfing_candle_message_uses_buy_format(self):
        self.assertEqual(
            json_data_parser.candle_alert_message(
                {
                    "event_type": "ENGULFING_CANDLE",
                    "signal": "BUY",
                    "timeframe": "M15",
                    "candle_time": "2026.06.26 12:00",
                    "open": "1.2345",
                    "close": "1.2360",
                }
            ),
            "📈 Engulfing Candle - M15\n🕒 2026.06.26 05:00 PM\n💰 1.2345 - 1.2360",
        )

    def test_engulfing_candle_message_uses_sell_format(self):
        self.assertEqual(
            json_data_parser.candle_alert_message(
                {
                    "event_type": "ENGULFING_CANDLE",
                    "signal": "SELL",
                    "timeframe": "H1",
                    "candle_time": "2026.06.26 13:00",
                    "open": "1.2360",
                    "close": "1.2345",
                }
            ),
            "📉 Engulfing Candle - H1\n🕒 2026.06.26 06:00 PM\n💰 1.2360 - 1.2345",
        )

    def test_candle_message_adds_five_hours_and_rolls_date(self):
        self.assertEqual(
            json_data_parser.candle_alert_message(
                {
                    "event_type": "ENGULFING_CANDLE",
                    "signal": "BUY",
                    "timeframe": "H4",
                    "candle_time": "2026.06.26 23:30:00",
                    "open": "1.2345",
                    "close": "1.2360",
                }
            ),
            "📈 Engulfing Candle - H4\n🕒 2026.06.27 04:30 AM\n💰 1.2345 - 1.2360",
        )

    def test_engulfing_candle_message_rejects_missing_fields(self):
        with self.assertRaisesRegex(ValueError, "timeframe"):
            json_data_parser.candle_alert_message({"open": "1.2"})

    def test_is_supported_payload_accepts_alert_events(self):
        self.assertTrue(
            json_data_parser.is_supported_payload({"event_type": "ENGULFING_CANDLE"})
        )
        self.assertTrue(
            json_data_parser.is_supported_payload({"event_type": "HAMMER_CANDLE"})
        )
        self.assertTrue(
            json_data_parser.is_supported_payload({"event_type": "HANGING_MAN_CANDLE"})
        )
        self.assertFalse(
            json_data_parser.is_supported_payload({"event_type": "M1_CANDLE_CLOSE"})
        )

    def test_hammer_message_uses_hammer_title(self):
        self.assertEqual(
            json_data_parser.candle_alert_message(
                {
                    "event_type": "HAMMER_CANDLE",
                    "signal": "BUY",
                    "timeframe": "M15",
                    "candle_time": "2026.06.26 12:00",
                    "open": "1.2345",
                    "close": "1.2360",
                }
            ),
            "📈 Hammer Candle - M15\n🕒 2026.06.26 05:00 PM\n💰 1.2345 - 1.2360",
        )

    def test_error_message_format(self):
        self.assertEqual(
            webhook.error_message(ValueError("bad payload")),
            "⚠️ Webhook Error\nValueError: bad payload",
        )

    def test_send_telegram_message_includes_telegram_error_body(self):
        def fake_urlopen(request, timeout):
            raise urllib.error.HTTPError(
                request.full_url,
                400,
                "Bad Request",
                {},
                BytesIO(b'{"description":"Bad Request: chat not found"}'),
            )

        with patch.dict(
            os.environ,
            {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID": "chat"},
        ), patch("urllib.request.urlopen", fake_urlopen):
            with self.assertRaisesRegex(Exception, "chat not found"):
                telegram_sender.send_telegram_message("message")

    def test_send_telegram_message_retries_connection_errors(self):
        calls = []

        def fake_urlopen(request, timeout):
            calls.append(request)
            if len(calls) == 1:
                raise urllib.error.URLError("temporary network issue")

            class Response:
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return None

                def read(self):
                    return b'{"ok":true}'

            return Response()

        with patch.dict(
            os.environ,
            {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID": "chat"},
        ), patch("urllib.request.urlopen", fake_urlopen), patch("time.sleep"):
            telegram_sender.send_telegram_message("message")

        self.assertEqual(len(calls), 2)

    def test_logger_cleans_log_after_five_hours(self):
        with tempfile.TemporaryDirectory() as directory:
            log_file = Path(directory) / "webhook.log"
            log_file.write_text("old log", encoding="utf-8")
            old_time = time.time() - app_logger.CLEAN_AFTER_SECONDS - 1
            os.utime(log_file, (old_time, old_time))

            with patch.object(app_logger, "LOG_FILE", log_file):
                app_logger._clean_old_log()

            self.assertEqual(log_file.read_text(encoding="utf-8"), "")

    def test_server_config_defaults_to_ec2_ready_bind(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                webhook.server_config(),
                ("0.0.0.0", 8000, "http://localhost:8000/webhook"),
            )

    def test_server_config_uses_env_values(self):
        with patch.dict(
            os.environ,
            {
                "HOST": "127.0.0.1",
                "PORT": "9000",
                "PUBLIC_URL": "http://3.27.46.138:9000/webhook",
            },
            clear=True,
        ):
            self.assertEqual(
                webhook.server_config(),
                ("127.0.0.1", 9000, "http://3.27.46.138:9000/webhook"),
            )


if __name__ == "__main__":
    unittest.main()
