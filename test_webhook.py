import json
import os
import tempfile
import time
import urllib.error
import urllib.parse
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import app_logger
import json_data_parser
import telegram_sender
import webhook


class WebhookTest(unittest.TestCase):
    def setUp(self):
        webhook.ALERTS_PAUSED = False
        webhook.RECENT_SIGNALS.clear()

    def make_handler(self, path, body=b"", method="POST"):
        handler = webhook.WebhookHandler.__new__(webhook.WebhookHandler)
        handler.path = path
        handler.headers = {"Content-Length": str(len(body))}
        handler.rfile = BytesIO(body)
        handler.wfile = BytesIO()
        handler.responses = []
        handler.send_response = lambda code: handler.responses.append(("code", code))
        handler.send_header = lambda key, value: handler.responses.append((key, value))
        handler.end_headers = lambda: None
        return handler

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
                "Bias: Directional / UNKNOWN\n"
                "🕒 2026.06.26 05:00 PM\n"
                "💰 1.2345 - 1.2360",
            },
        )

    def test_send_telegram_message_can_override_chat_id(self):
        requests = []

        def fake_urlopen(request, timeout):
            requests.append(request)

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
            {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID": "default"},
        ), patch("urllib.request.urlopen", fake_urlopen):
            telegram_sender.send_telegram_message("message", chat_id="command-chat")

        self.assertEqual(json.loads(requests[0].data)["chat_id"], "command-chat")

    def test_engulfing_candle_message_uses_buy_format(self):
        self.assertEqual(
            json_data_parser.candle_alert_message(
                {
                    "event_type": "ENGULFING_CANDLE",
                    "signal": "BUY",
                    "symbol": "GOLDmicro",
                    "timeframe": "M15",
                    "candle_time": "2026.06.26 12:00",
                    "open": "1.2345",
                    "close": "1.2360",
                }
            ),
            "📈 GOLD Engulfing Candle - M15\n"
            "Bias: Bullish / BUY\n"
            "🕒 2026.06.26 05:00 PM\n"
            "💰 1.2345 - 1.2360",
        )

    def test_candle_message_removes_broker_prefix_and_suffix_from_symbol(self):
        self.assertEqual(
            json_data_parser.candle_alert_message(
                {
                    "event_type": "HAMMER_CANDLE",
                    "signal": "BUY",
                    "symbol": "microEURUSDm#",
                    "timeframe": "M15",
                    "candle_time": "2026.06.26 12:00",
                    "open": "1.2345",
                    "close": "1.2360",
                }
            ).splitlines()[0],
            "📈 EURUSD Hammer Candle - M15",
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
            "📉 Engulfing Candle - H1\n"
            "Bias: Bearish / SELL\n"
            "🕒 2026.06.26 06:00 PM\n"
            "💰 1.2360 - 1.2345",
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
            "📈 Engulfing Candle - H4\n"
            "Bias: Bullish / BUY\n"
            "🕒 2026.06.27 04:30 AM\n"
            "💰 1.2345 - 1.2360",
        )

    def test_candle_message_uses_timezone_offset_from_environment(self):
        with patch.dict(os.environ, {"TIMEZONE_OFFSET_HOURS": "-2"}):
            self.assertEqual(
                json_data_parser.display_time("2026.06.26 01:30"),
                "2026.06.25 11:30 PM",
            )

    def test_engulfing_candle_message_rejects_missing_fields(self):
        with self.assertRaisesRegex(ValueError, "timeframe"):
            json_data_parser.candle_alert_message({"open": "1.2"})

    def test_is_supported_payload_accepts_alert_events(self):
        supported = (
            "ENGULFING_CANDLE",
            "HAMMER_CANDLE",
            "HANGING_MAN_CANDLE",
            "SHOOTING_STAR_CANDLE",
            "INVERTED_HAMMER_CANDLE",
            "MORNING_STAR",
            "EVENING_STAR",
            "INSIDE_BAR_BREAKOUT",
        )
        for event_type in supported:
            with self.subTest(event_type=event_type):
                self.assertTrue(
                    json_data_parser.is_supported_payload({"event_type": event_type})
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
            "📈 Hammer Candle - M15\n"
            "Bias: Bullish / BUY\n"
            "🕒 2026.06.26 05:00 PM\n"
            "💰 1.2345 - 1.2360",
        )

    def test_fixed_bias_patterns_infer_signal_and_bias(self):
        patterns = {
            "SHOOTING_STAR_CANDLE": ("📉", "Bearish / SELL"),
            "INVERTED_HAMMER_CANDLE": ("📈", "Bullish / BUY"),
            "MORNING_STAR": ("📈", "Bullish / BUY"),
            "EVENING_STAR": ("📉", "Bearish / SELL"),
        }
        for event_type, (icon, bias) in patterns.items():
            with self.subTest(event_type=event_type):
                message = json_data_parser.candle_alert_message(
                    {
                        "event_type": event_type,
                        "timeframe": "M15",
                        "candle_time": "2026.06.27 10:15",
                        "open": "2335.20",
                        "close": "2336.10",
                    }
                )
                self.assertTrue(message.startswith(icon))
                self.assertIn(f"Bias: {bias}", message)

    def test_inside_bar_breakout_uses_payload_signal(self):
        for signal, icon, bias in (
            ("BUY", "📈", "Bullish / BUY"),
            ("SELL", "📉", "Bearish / SELL"),
        ):
            with self.subTest(signal=signal):
                message = json_data_parser.candle_alert_message(
                    {
                        "event_type": "INSIDE_BAR_BREAKOUT",
                        "signal": signal,
                        "timeframe": "M15",
                        "candle_time": "2026.06.27 10:15",
                        "open": "2335.20",
                        "close": "2336.10",
                    }
                )
                self.assertTrue(message.startswith(icon))
                self.assertIn(f"Bias: {bias}", message)

    def test_candle_message_includes_ohlc_when_high_and_low_are_available(self):
        message = json_data_parser.candle_alert_message(
            {
                "event_type": "SHOOTING_STAR_CANDLE",
                "timeframe": "M15",
                "candle_time": "2026.06.27 10:15",
                "open": "2335.20",
                "high": "2341.80",
                "low": "2334.90",
                "close": "2336.10",
            }
        )
        self.assertIn(
            "💰 O: 2335.20 | H: 2341.80 | L: 2334.90 | C: 2336.10",
            message,
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
            updates = telegram_sender.get_telegram_updates(offset=6, timeout_seconds=10)

        request, timeout = requests[0]
        query = urllib.parse.parse_qs(urllib.parse.urlparse(request.full_url).query)
        self.assertEqual(request.full_url.split("?", 1)[0], "https://api.telegram.org/bottoken/getUpdates")
        self.assertEqual(query, {"timeout": ["10"], "offset": ["6"]})
        self.assertEqual(timeout, 15)
        self.assertEqual(updates, [{"update_id": 7}])

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

    def test_health_endpoint_returns_text_status(self):
        handler = self.make_handler("/health", method="GET")
        with patch.dict(
            os.environ,
            {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID": "chat"},
        ):
            handler.do_GET()

        self.assertIn(("code", 200), handler.responses)
        self.assertIn(("Content-Type", "text/plain; charset=utf-8"), handler.responses)
        text = handler.wfile.getvalue().decode()
        self.assertIn("✅ Webhook healthy", text)
        self.assertIn("Telegram: configured", text)
        self.assertIn("Uptime:", text)

    def test_telegram_pause_and_resume_commands_control_alerts(self):
        with patch("webhook.send_telegram_message") as send:
            self.make_handler(
                "/telegram",
                b'{"message":{"text":"/pause","chat":{"id":"cmd-chat"}}}',
            ).do_POST()

            handler = self.make_handler(
                "/webhook",
                b'{"event_type":"ENGULFING_CANDLE","signal":"BUY","symbol":"GOLDmicro",'
                b'"timeframe":"M1","candle_time":"2026.06.26 11:11:00",'
                b'"open":4029.07,"close":4030.23}',
            )
            handler.do_POST()

            self.make_handler(
                "/telegram",
                b'{"message":{"text":"/resume","chat":{"id":"cmd-chat"}}}',
            ).do_POST()

        send.assert_any_call("⏸️ MT5 alerts paused", chat_id="cmd-chat")
        send.assert_any_call("▶️ MT5 alerts resumed", chat_id="cmd-chat")
        self.assertEqual(handler.wfile.getvalue(), b"paused")

    def test_telegram_command_can_arrive_on_webhook_path(self):
        with patch("webhook.send_telegram_message") as send:
            handler = self.make_handler(
                "/webhook",
                b'{"message":{"text":"/status","chat":{"id":"cmd-chat"}}}',
            )
            handler.do_POST()

        self.assertEqual(handler.wfile.getvalue(), b"ok")
        send.assert_called_once()
        self.assertEqual(send.call_args.kwargs["chat_id"], "cmd-chat")
        self.assertIn("Bot online", send.call_args.args[0])

    def test_telegram_status_help_and_recent_commands(self):
        webhook.RECENT_SIGNALS.extend(
            [
                {"symbol": "GOLD", "message": "signal 1"},
                {"symbol": "EURUSD", "message": "ignored"},
                {"symbol": "GOLD", "message": "signal 2"},
            ]
        )

        with patch("webhook.send_telegram_message") as send:
            for text in ("/status", "/help", "/recent Gold"):
                self.make_handler(
                    "/telegram",
                    json.dumps({"message": {"text": text, "chat": {"id": "cmd-chat"}}}).encode(),
                ).do_POST()

        messages = [call.args[0] for call in send.call_args_list]
        self.assertIn("✅ Bot online\nAlerts: running", messages[0])
        self.assertIn("/recent Gold", messages[1])
        self.assertEqual(messages[2], "Recent GOLD signals:\n1. signal 1\n2. signal 2")

    def test_poll_telegram_once_replies_and_returns_next_offset(self):
        updates = [{"update_id": 41, "message": {"text": "/status", "chat": {"id": "cmd-chat"}}}]

        with patch("webhook.get_telegram_updates", return_value=updates) as get_updates, patch(
            "webhook.send_telegram_message"
        ) as send:
            next_offset = webhook.poll_telegram_once(10)

        get_updates.assert_called_once_with(offset=10, timeout_seconds=10)
        self.assertEqual(next_offset, 42)
        send.assert_called_once()
        self.assertEqual(send.call_args.kwargs["chat_id"], "cmd-chat")
        self.assertIn("Bot online", send.call_args.args[0])


if __name__ == "__main__":
    unittest.main()
