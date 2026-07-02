import json
import importlib.util
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
import market_state
import telegram_sender
import webhook


class WebhookTest(unittest.TestCase):
    def setUp(self):
        webhook.ALERTS_PAUSED = False
        webhook.TRADE_MODE = "NOTRADE"
        webhook.RECENT_SIGNALS.clear()

    def test_load_dotenv(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / ".env"
            path.write_text(
                'TELEGRAM_BOT_TOKEN=file-token\n'
                'TELEGRAM_CHAT_ID="123456789"\n'
                "PORT=9001\n",
                encoding="utf-8",
            )
            with patch.dict(
                os.environ, {"TELEGRAM_BOT_TOKEN": "process-token"}, clear=True
            ):
                webhook.load_dotenv(path)

                self.assertEqual(os.environ["TELEGRAM_BOT_TOKEN"], "process-token")
                self.assertEqual(os.environ["TELEGRAM_CHAT_ID"], "123456789")
                self.assertEqual(os.environ["PORT"], "9001")

    def test_load_dotenv_ignores_missing_file(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.dict(os.environ, {}, clear=True):
                webhook.load_dotenv(Path(directory) / ".env")

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

    def snapshot(self, timeframe, candle_time, **values):
        payload = {
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
                "parse_mode": "HTML",
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

    def test_send_telegram_message_can_disable_html(self):
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
            {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID": "chat"},
        ), patch("urllib.request.urlopen", fake_urlopen):
            telegram_sender.send_telegram_message("<raw>", parse_mode=None)

        self.assertNotIn("parse_mode", json.loads(requests[0].data))

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

    def test_candle_message_escapes_dynamic_html(self):
        message = json_data_parser.candle_alert_message(
            {
                "event_type": "ENGULFING_CANDLE",
                "signal": "BUY",
                "symbol": "X<Y",
                "timeframe": "M15",
                "candle_time": "2026.06.26 12:00",
                "open": "1<2",
                "close": "3&4",
            }
        )
        self.assertIn("X&lt;Y", message)
        self.assertIn("1&lt;2 - 3&amp;4", message)
        self.assertNotIn("X<Y", message)

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

    def test_server_config_defaults_to_local_bind(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                webhook.server_config(),
                ("127.0.0.1", 8000, "http://127.0.0.1:8000/webhook"),
            )

    def test_server_config_uses_env_values(self):
        with patch.dict(
            os.environ,
            {
                "HOST": "127.0.0.1",
                "PORT": "9000",
                "PUBLIC_URL": "http://example.test:9000/webhook",
            },
            clear=True,
        ):
            self.assertEqual(
                webhook.server_config(),
                ("127.0.0.1", 9000, "http://example.test:9000/webhook"),
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
                b'"timeframe":"M15","candle_time":"2026.06.26 11:11:00",'
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

    def test_summary_levels_and_rsi_commands_require_a_symbol(self):
        self.assertEqual(webhook.command_reply("/summary"), "Usage: /summary Gold")
        self.assertEqual(webhook.command_reply("/levels"), "Usage: /levels Gold")
        self.assertEqual(webhook.command_reply("/rsi"), "Usage: /rsi Gold")

    def test_help_lists_summary_levels_rsi_and_trade_commands(self):
        message = webhook.help_text()
        self.assertIn("/summary Gold", message)
        self.assertIn("/levels Gold", message)
        self.assertIn("/rsi Gold", message)
        self.assertIn("/buy - Start trailing buy-limit mode", message)
        self.assertIn("/sell - Start trailing sell-limit mode", message)
        self.assertIn("/notrade - Stop trading activity", message)

    def test_trade_mode_commands_update_trade_config(self):
        with patch.dict(os.environ, {"TRADE_LOT_SIZE": "0.30", "TRAIL_PIPS": "25"}):
            self.assertIn("BUY limit mode", webhook.command_reply("/buy"))
            self.assertEqual(
                webhook.trade_config(),
                {"mode": "BUY", "lot_size": 0.30, "trail_pips": 25.0},
            )
            self.assertIn("SELL limit mode", webhook.command_reply("/sell"))
            self.assertEqual(webhook.trade_config()["mode"], "SELL")
            self.assertIn("Trading paused", webhook.command_reply("/notrade"))
            self.assertEqual(webhook.trade_config()["mode"], "NOTRADE")

    def test_trade_config_endpoint_returns_json(self):
        webhook.command_reply("/buy")
        handler = self.make_handler("/trade-config?symbol=Gold", method="GET")
        handler.do_GET()

        self.assertIn(("code", 200), handler.responses)
        self.assertIn(("Content-Type", "application/json; charset=utf-8"), handler.responses)
        self.assertEqual(json.loads(handler.wfile.getvalue()), webhook.trade_config())

    def test_ea_error_payload_is_sent_to_telegram(self):
        payload = {
            "event_type": "EA_ERROR",
            "symbol": "GOLDmicro",
            "timeframe": "M1",
            "message": "BuyLimit failed",
            "detail": "retcode=10030",
        }
        with patch("webhook.send_telegram_message") as send:
            handler = self.make_handler("/webhook", json.dumps(payload).encode())
            handler.do_POST()

        self.assertEqual(handler.wfile.getvalue(), b"ok")
        send.assert_called_once()
        message = send.call_args.args[0]
        self.assertIn("⚠️ EA Issue", message)
        self.assertIn("GOLD", message)
        self.assertIn("M1", message)
        self.assertIn("BuyLimit failed", message)
        self.assertIn("retcode=10030", message)

    def test_ea_issue_message_includes_source_when_present(self):
        message = webhook.ea_issue_message(
            {
                "event_type": "EA_ERROR",
                "source": "webhook2",
                "message": "BuyLimit failed",
            }
        )

        self.assertIn("Source: <b>webhook2</b>", message)

    def test_ea_issue_message_omits_source_when_missing(self):
        message = webhook.ea_issue_message(
            {"event_type": "EA_ERROR", "message": "BuyLimit failed"}
        )

        self.assertNotIn("Source:", message)

    def test_ea_error_accepts_both_sources(self):
        for source in ("webhook1", "webhook2"):
            with self.subTest(source=source), patch(
                "webhook.send_telegram_message"
            ) as send:
                payload = {
                    "event_type": "EA_ERROR",
                    "source": source,
                    "message": "EA failed",
                }
                handler = self.make_handler(
                    "/webhook", json.dumps(payload).encode()
                )

                handler.do_POST()

                self.assertEqual(handler.wfile.getvalue(), b"ok")
                send.assert_called_once()

    def test_webhook1_snapshot_updates_market_state(self):
        payload = self.snapshot("M1", "2026.06.28 10:01:00")
        payload["source"] = "webhook1"
        with patch.object(webhook.MARKET_STATE, "update", return_value=[]) as update:
            handler = self.make_handler("/webhook", json.dumps(payload).encode())

            handler.do_POST()

        self.assertEqual(handler.wfile.getvalue(), b"ok")
        update.assert_called_once_with(payload)

    def test_market_state_module_is_available(self):
        self.assertIsNotNone(importlib.util.find_spec("market_state"))

    def test_market_state_persists_ema_snapshot_and_neutral_equality(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            state = market_state.MarketState(path)
            self.assertEqual(
                state.update(
                    self.snapshot(
                        "M1", "2026.06.28 10:01:00", ema20=2306.0, ema50=2305.0
                    )
                ),
                [],
            )
            state.update(
                self.snapshot(
                    "M5", "2026.06.28 10:05:00", ema20=2305.0, ema50=2305.0
                )
            )

            report = market_state.MarketState(path).summary("Gold")

        self.assertIn("<b>M1</b>", report)
        self.assertIn("Bullish", report)
        self.assertIn("<b>M5</b>", report)
        self.assertIn("Neutral", report)

    def test_market_state_uses_supplied_candle_history(self):
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            payload = self.snapshot(
                "M1",
                "2026.06.28 10:01:00",
                ema20=2306.0,
                ema50=2305.0,
            )
            payload["candles"] = [
                {
                    "time": "2026.06.28 10:00:00",
                    "open": 2295.0,
                    "high": 2305.0,
                    "low": 2290.0,
                    "close": 2300.0,
                },
                {
                    "candle_time": "2026.06.28 10:01:00",
                    "open": 2300.0,
                    "high": 2310.0,
                    "low": 2290.0,
                    "close": 2305.0,
                },
            ]

            state.update(payload)

            history = state.data["symbols"]["GOLD"]["M1"]["candle_history"]
            self.assertEqual(
                [candle["candle_time"] for candle in history],
                ["2026.06.28 10:00:00", "2026.06.28 10:01:00"],
            )

    def test_market_state_accumulates_history_without_candles(self):
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            for minute in (0, 1):
                state.update(
                    self.snapshot(
                        "M1",
                        f"2026.06.28 10:{minute:02d}:00",
                        ema20=2306.0,
                        ema50=2305.0,
                    )
                )

            history = state.data["symbols"]["GOLD"]["M1"]["candle_history"]

        self.assertEqual(
            [candle["candle_time"] for candle in history],
            ["2026.06.28 10:00:00", "2026.06.28 10:01:00"],
        )

    def test_market_state_accepts_optional_webhook1_source(self):
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            without_source = self.snapshot(
                "M15", "2026.06.28 10:00:00", patterns=[], levels={}
            )
            with_source = self.snapshot(
                "M15",
                "2026.06.28 10:15:00",
                source="webhook1",
                patterns=[],
                levels={},
            )

            state.update(without_source)
            state.update(with_source)

        self.assertEqual(
            state.data["symbols"]["GOLD"]["M15"]["candle_time"],
            "2026.06.28 10:15:00",
        )

    def test_market_state_stores_rsi_history_and_reports_extremes(self):
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            for index in range(31):
                state.update(
                    self.snapshot(
                        "M5",
                        f"2026.06.28 10:{index:02d}:00",
                        ema20=2306.0,
                        ema50=2305.0,
                        rsi14=71.0 if index == 0 else 55.0,
                    )
                )
            state.update(
                self.snapshot(
                    "M15",
                    "2026.06.28 10:15:00",
                    patterns=[],
                    levels={},
                    rsi14=29.0,
                )
            )
            state.update(
                self.snapshot(
                    "H1",
                    "2026.06.28 23:30:00",
                    patterns=[],
                    levels={},
                    rsi14=72.5,
                )
            )

            report = state.rsi_summary("Gold")

        self.assertIn("📈 <b>GOLD RSI(14)</b>", report)
        self.assertIn("<b>M5</b>: <code>55.00</code> — Neutral", report)
        self.assertNotIn("10:00:00", report)
        self.assertIn("<b>M15</b>: <code>29.00</code> — Oversold", report)
        self.assertIn("Closed below 30", report)
        self.assertIn("2026.06.28 03:15 PM", report)
        self.assertIn("<b>H1</b>: <code>72.50</code> — Overbought", report)
        self.assertIn("Closed above 70", report)
        self.assertIn("2026.06.29 04:30 AM", report)
        self.assertNotIn("23:30:00", report)

    def test_market_state_rejects_snapshot_for_unknown_timeframe(self):
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            with self.assertRaisesRegex(ValueError, "timeframe"):
                state.update(self.snapshot("D1", "2026.06.28 10:00:00"))

    def test_higher_opposing_pattern_invalidates_older_lower_pattern(self):
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            state.update(
                self.snapshot(
                    "M15",
                    "2026.06.28 10:00:00",
                    patterns=[{"event_type": "ENGULFING_CANDLE", "signal": "BUY"}],
                    levels={},
                )
            )
            state.update(
                self.snapshot(
                    "H1",
                    "2026.06.28 11:00:00",
                    patterns=[{"event_type": "SHOOTING_STAR_CANDLE", "signal": "SELL"}],
                    levels={},
                )
            )
            report = state.summary("Gold")
            self.assertIn("Engulfing Candle", report)
            self.assertIn("(invalidated)", report)

            state.update(
                self.snapshot(
                    "M15",
                    "2026.06.28 12:00:00",
                    patterns=[{"event_type": "HAMMER_CANDLE", "signal": "BUY"}],
                    levels={},
                )
            )
            report = state.summary("Gold")

        self.assertIn("Hammer Candle", report)
        self.assertNotIn("Hammer Candle — Bullish (invalidated)", report)

    def test_summary_confluence_returns_buy_sell_or_wait(self):
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            state.update(
                self.snapshot(
                    "M1", "2026.06.28 12:01:00", ema20=2310.0, ema50=2300.0
                )
            )
            state.update(
                self.snapshot(
                    "M5", "2026.06.28 12:05:00", ema20=2310.0, ema50=2300.0
                )
            )
            state.update(
                self.snapshot(
                    "M15",
                    "2026.06.28 23:15:00",
                    patterns=[{"event_type": "HAMMER_CANDLE", "signal": "BUY"}],
                    levels={},
                )
            )
            buy_summary = state.summary("Gold")
            self.assertIn("<b>Suggestion: BUY</b>", buy_summary)
            self.assertIn("2026.06.29 04:15 AM", buy_summary)
            self.assertNotIn("23:15:00", buy_summary)

            state.update(
                self.snapshot(
                    "H1",
                    "2026.06.29 00:00:00",
                    patterns=[{"event_type": "EVENING_STAR", "signal": "SELL"}],
                    levels={},
                )
            )
            self.assertIn("<b>Suggestion: WAIT</b>", state.summary("Gold"))

            state.update(
                self.snapshot(
                    "M1", "2026.06.28 13:01:00", ema20=2290.0, ema50=2300.0
                )
            )
            state.update(
                self.snapshot(
                    "M5", "2026.06.28 13:05:00", ema20=2290.0, ema50=2300.0
                )
            )

            self.assertIn("<b>Suggestion: SELL</b>", state.summary("Gold"))

    def test_levels_report_formats_all_higher_timeframes_and_missing_data(self):
        levels = {
            "support": 2280.0,
            "resistance": 2340.0,
            "fib": {
                "direction": "UP",
                "start": 2260.0,
                "end": 2360.0,
                "38.2": 2321.8,
                "50.0": 2310.0,
                "61.8": 2298.2,
            },
            "bullish_fvg": {"low": 2275.0, "high": 2285.0},
            "bearish_fvg": None,
            "previous_day_high": 2350.0,
            "previous_day_low": 2250.0,
        }
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            state.update(
                self.snapshot(
                    "M15", "2026.06.28 12:15:00", patterns=[], levels=levels
                )
            )
            report = state.levels("Gold")

        self.assertIn("<b>M15</b>", report)
        self.assertIn("Support: <code>2280.00</code>", report)
        self.assertIn("Fib 38.2/50/61.8", report)
        self.assertIn("Bearish FVG: None found", report)
        self.assertIn("<b>M30</b>\nAwaiting data", report)
        self.assertIn("PDH / PDL: <code>2350.00</code> / <code>2250.00</code>", report)

    def test_summary_escapes_dynamic_symbol(self):
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            payload = self.snapshot(
                "M1", "2026.06.28 12:01:00", ema20=2310.0, ema50=2300.0
            )
            payload["symbol"] = "X<Y"
            state.update(payload)

            report = state.summary("X<Y")

        self.assertIn("X&lt;Y", report)
        self.assertNotIn("X<Y", report)

    def test_market_state_returns_each_pattern_notification_once(self):
        payload = self.snapshot(
            "M15",
            "2026.06.28 12:15:00",
            patterns=[
                {"event_type": "ENGULFING_CANDLE", "signal": "BUY"},
                {"event_type": "MORNING_STAR", "signal": "BUY"},
            ],
            levels={},
        )
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            first = state.update(payload)
            for pattern in first:
                state.mark_notified(pattern)
            duplicate = state.update(payload)

        self.assertEqual(
            [pattern["event_type"] for pattern in first],
            ["ENGULFING_CANDLE", "MORNING_STAR"],
        )
        self.assertEqual(duplicate, [])

    def test_initial_snapshot_stores_patterns_without_notification(self):
        payload = self.snapshot(
            "H4",
            "2026.06.28 12:00:00",
            notify_patterns=False,
            patterns=[{"event_type": "EVENING_STAR", "signal": "SELL"}],
            levels={},
        )
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            self.assertEqual(state.update(payload), [])
            report = state.summary("Gold")

        self.assertIn("Evening Star", report)

    def test_webhook_stores_snapshot_and_sends_new_patterns_once(self):
        payload = self.snapshot(
            "M15",
            "2026.06.28 12:15:00",
            patterns=[{"event_type": "ENGULFING_CANDLE", "signal": "BUY"}],
            levels={},
        )
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            with patch.object(webhook, "MARKET_STATE", state, create=True), patch(
                "webhook.send_telegram_message"
            ) as send:
                first = self.make_handler("/webhook", json.dumps(payload).encode())
                first.do_POST()
                duplicate = self.make_handler("/webhook", json.dumps(payload).encode())
                duplicate.do_POST()

            report = state.summary("Gold")

        self.assertEqual(first.wfile.getvalue(), b"ok")
        self.assertEqual(duplicate.wfile.getvalue(), b"ok")
        send.assert_called_once()
        self.assertIn("Engulfing Candle", send.call_args.args[0])
        self.assertIn("Engulfing Candle", report)

    def test_webhook_retries_pattern_alert_after_telegram_failure(self):
        payload = self.snapshot(
            "M15",
            "2026.06.28 12:15:00",
            patterns=[{"event_type": "ENGULFING_CANDLE", "signal": "BUY"}],
            levels={},
        )
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            with patch.object(webhook, "MARKET_STATE", state), patch(
                "webhook.send_telegram_message",
                side_effect=[RuntimeError("Telegram unavailable"), b'{"ok":true}'],
            ) as send, patch("webhook.notify_error"):
                first = self.make_handler("/webhook", json.dumps(payload).encode())
                first.do_POST()
                retry = self.make_handler("/webhook", json.dumps(payload).encode())
                retry.do_POST()

        self.assertEqual(first.responses[0], ("code", 500))
        self.assertEqual(retry.wfile.getvalue(), b"ok")
        self.assertEqual(send.call_count, 2)

    def test_paused_webhook_stores_snapshot_without_pattern_alert(self):
        payload = self.snapshot(
            "H1",
            "2026.06.28 13:00:00",
            patterns=[{"event_type": "EVENING_STAR", "signal": "SELL"}],
            levels={},
        )
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            with patch.object(webhook, "MARKET_STATE", state, create=True), patch(
                "webhook.send_telegram_message"
            ) as send:
                webhook.ALERTS_PAUSED = True
                handler = self.make_handler("/webhook", json.dumps(payload).encode())
                handler.do_POST()
                webhook.ALERTS_PAUSED = False
                retry = self.make_handler("/webhook", json.dumps(payload).encode())
                retry.do_POST()

            report = state.summary("Gold")

        self.assertEqual(handler.wfile.getvalue(), b"ok")
        self.assertEqual(retry.wfile.getvalue(), b"ok")
        send.assert_not_called()
        self.assertIn("Evening Star", report)

    def test_webhook_ignores_legacy_pattern_on_m1(self):
        payload = {
            "event_type": "ENGULFING_CANDLE",
            "signal": "BUY",
            "symbol": "GOLDmicro",
            "timeframe": "M1",
            "candle_time": "2026.06.28 13:00:00",
            "open": 2300.0,
            "close": 2310.0,
        }
        with patch("webhook.send_telegram_message") as send:
            handler = self.make_handler("/webhook", json.dumps(payload).encode())
            handler.do_POST()

        self.assertEqual(handler.wfile.getvalue(), b"ignored")
        send.assert_not_called()

    def test_summary_and_levels_commands_use_market_state(self):
        levels = {
            "support": 2280.0,
            "resistance": 2340.0,
            "fib": None,
            "bullish_fvg": None,
            "bearish_fvg": None,
            "previous_day_high": 2350.0,
            "previous_day_low": 2250.0,
        }
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            state.update(
                self.snapshot(
                    "M1", "2026.06.28 13:01:00", ema20=2310.0, ema50=2300.0
                )
            )
            state.update(
                self.snapshot(
                    "M15", "2026.06.28 13:15:00", patterns=[], levels=levels
                )
            )
            with patch.object(webhook, "MARKET_STATE", state, create=True):
                summary = webhook.command_reply("/summary Gold")
                level_report = webhook.command_reply("/levels Gold")

        self.assertIn("<b>GOLD Market Summary</b>", summary)
        self.assertIn("<b>GOLD Key Levels</b>", level_report)

    def test_levels_chart_writes_png_with_key_levels(self):
        levels = {
            "support": 2280.0,
            "resistance": 2340.0,
            "fib": {
                "direction": "UP",
                "start": 2260.0,
                "end": 2360.0,
                "38.2": 2321.8,
                "50.0": 2310.0,
                "61.8": 2298.2,
            },
            "bullish_fvg": {"low": 2275.0, "high": 2285.0},
            "bearish_fvg": {"low": 2345.0, "high": 2355.0},
            "previous_day_high": 2350.0,
            "previous_day_low": 2250.0,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "levels.png"
            state = market_state.MarketState(Path(directory) / "state.json")
            state.update(
                self.snapshot(
                    "M15",
                    "2026.06.28 13:15:00",
                    close=2305.0,
                    patterns=[],
                    levels=levels,
                )
            )

            result = state.levels_chart("Gold", path)

            self.assertEqual(result, path)
            self.assertTrue(path.exists())
            self.assertGreater(path.stat().st_size, 1000)
            self.assertEqual(path.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_levels_chart_prefers_m15_history_and_keeps_200_bars(self):
        levels = {
            "support": None,
            "resistance": None,
            "fib": None,
            "bullish_fvg": None,
            "bearish_fvg": None,
            "previous_day_high": None,
            "previous_day_low": None,
        }
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            for timeframe in ("M30", "H1", "H4", "M15"):
                payload = self.snapshot(
                    timeframe,
                    f"2026.06.28 {timeframe}:00",
                    patterns=[],
                    levels=levels,
                )
                payload["candles"] = [
                    {
                        "time": f"{timeframe}-{index:03d}",
                        "open": 2300.0,
                        "high": 2310.0,
                        "low": 2290.0,
                        "close": 2305.0,
                    }
                    for index in range(200)
                ]
                state.update(payload)

            history, timeframe = state._chart_candles(
                state.data["symbols"]["GOLD"]
            )

        self.assertEqual(timeframe, "M15")
        self.assertEqual(len(history), 200)

    def test_levels_chart_uses_m1_history_only_as_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            state.update(
                self.snapshot(
                    "M1",
                    "2026.06.28 10:01:00",
                    ema20=2306.0,
                    ema50=2305.0,
                )
            )

            history, timeframe = state._chart_candles(
                state.data["symbols"]["GOLD"]
            )

        self.assertEqual(timeframe, "M1")
        self.assertEqual(len(history), 1)

    def test_far_levels_are_labels_without_compressing_candles(self):
        levels = {
            "support": 2000.0,
            "resistance": 4000.0,
            "fib": None,
            "bullish_fvg": None,
            "bearish_fvg": {"low": 4100.0, "high": 4200.0},
            "previous_day_high": 4300.0,
            "previous_day_low": 1900.0,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "levels.png"
            state = market_state.MarketState(Path(directory) / "state.json")
            payload = self.snapshot(
                "M15",
                "2026.06.28 13:30:00",
                open=2308.0,
                high=2320.0,
                low=2302.0,
                close=2301.0,
                patterns=[],
                levels=levels,
            )
            payload["candles"] = [
                {
                    "time": "2026.06.28 13:15:00",
                    "open": 2300.0,
                    "high": 2310.0,
                    "low": 2290.0,
                    "close": 2306.0,
                },
                {
                    "time": "2026.06.28 13:30:00",
                    "open": 2308.0,
                    "high": 2320.0,
                    "low": 2302.0,
                    "close": 2301.0,
                },
            ]
            state.update(payload)

            with patch.object(
                market_state.ImageDraw.ImageDraw, "text", autospec=True
            ) as draw_text:
                state.levels_chart("Gold", path)

            labels = [call.args[2] for call in draw_text.call_args_list]
            with market_state.Image.open(path) as image:
                pixels = image.load()
                candle_ys = [
                    y
                    for x in range(90, 820)
                    for y in range(70, 690)
                    if pixels[x, y] in ((20, 184, 166), (248, 113, 113))
                ]

        self.assertIn("M15 Bear FVG 4100.00-4200.00 above chart", labels)
        self.assertIn("M15 Support 2000.00 below chart", labels)
        self.assertGreater(max(candle_ys) - min(candle_ys), 200)

    def test_levels_chart_draws_recent_candlesticks(self):
        levels = {
            "support": 2280.0,
            "resistance": 2340.0,
            "fib": None,
            "bullish_fvg": {"low": 2290.0, "high": 2320.0},
            "bearish_fvg": None,
            "previous_day_high": None,
            "previous_day_low": None,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "levels.png"
            state = market_state.MarketState(Path(directory) / "state.json")
            state.update(
                self.snapshot(
                    "M15",
                    "2026.06.28 13:15:00",
                    open=2300.0,
                    high=2310.0,
                    low=2290.0,
                    close=2306.0,
                    patterns=[],
                    levels=levels,
                )
            )
            state.update(
                self.snapshot(
                    "M15",
                    "2026.06.28 13:30:00",
                    open=2308.0,
                    high=2320.0,
                    low=2302.0,
                    close=2301.0,
                    patterns=[],
                    levels=levels,
                )
            )

            result = state.levels_chart("Gold", path)

            self.assertEqual(result, path)
            candle_history = state.data["symbols"]["GOLD"]["M15"]["candle_history"]
            self.assertEqual(
                [entry["candle_time"] for entry in candle_history],
                ["2026.06.28 13:15:00", "2026.06.28 13:30:00"],
            )
            with market_state.Image.open(path) as image:
                pixels = image.load()
                candle_pixels = 0
                for x in range(90, 820):
                    for y in range(70, 690):
                        if pixels[x, y] in ((20, 184, 166), (248, 113, 113)):
                            candle_pixels += 1
                self.assertGreater(candle_pixels, 40)

    def test_levels_telegram_command_sends_chart_photo_with_report_caption(self):
        levels = {
            "support": 2280.0,
            "resistance": 2340.0,
            "fib": None,
            "bullish_fvg": None,
            "bearish_fvg": None,
            "previous_day_high": 2350.0,
            "previous_day_low": 2250.0,
        }
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            state.update(
                self.snapshot(
                    "M15", "2026.06.28 13:15:00", patterns=[], levels=levels
                )
            )
            with patch.object(webhook, "MARKET_STATE", state, create=True), patch(
                "webhook.send_telegram_message"
            ) as send_message, patch("webhook.send_telegram_photo") as send_photo:
                webhook.reply_to_telegram_update(
                    {"message": {"text": "/levels Gold", "chat": {"id": "cmd-chat"}}}
                )

            send_message.assert_not_called()
            send_photo.assert_called_once()
            self.assertEqual(send_photo.call_args.kwargs["chat_id"], "cmd-chat")
            self.assertIn("<b>GOLD Key Levels</b>", send_photo.call_args.kwargs["caption"])
            photo_path = Path(send_photo.call_args.args[0])
            self.assertTrue(photo_path.exists())
            self.assertEqual(photo_path.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")


if __name__ == "__main__":
    unittest.main()
