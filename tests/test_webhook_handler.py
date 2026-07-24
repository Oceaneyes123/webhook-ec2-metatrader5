"""Tests for webhook handler dispatch, Telegram commands, EA lifecycle, and trade state."""
from __future__ import annotations

import json
import os
import tempfile
import unittest
from uuid import uuid4
from pathlib import Path
from unittest.mock import patch

from tests.test_helpers import make_handler

import webhook


class TelegramEnvTest(unittest.TestCase):
    """Telegram initialisation and env detection."""

    def test_telegram_configured_returns_true_when_env_set(self):
        with patch.dict(
            os.environ,
            {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID": "chat"},
        ):
            self.assertTrue(webhook.telegram_configured())

    def test_telegram_configured_returns_false_when_token_missing(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(webhook.telegram_configured())

    def test_telegram_configured_returns_false_when_chat_id_missing(self):
        with patch.dict(
            os.environ, {"TELEGRAM_BOT_TOKEN": "token"}, clear=True
        ):
            self.assertFalse(webhook.telegram_configured())

    def test_load_dotenv_skips_comments_and_empty(self):
        with patch.dict(
            os.environ,
            {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID": "chat"},
        ):
            self.assertEqual(os.environ.get("TELEGRAM_BOT_TOKEN"), "token")
            webhook.load_dotenv()


class WebhookHandlerTest(unittest.TestCase):
    """Webhook POST dispatch via WebhookHandler."""

    def test_webhook_rejects_invalid_path(self):
        handler = make_handler(webhook, "/invalid", b"")
        handler.do_POST()
        self.assertEqual(handler.wfile.getvalue(), b"404 Not Found")

    def test_webhook_accepts_valid_payload(self):
        with patch.object(
            webhook.MARKET_STATE, "update", return_value=[]
        ) as update:
            handler = make_handler(
                webhook,
                "/webhook",
                json.dumps(
                    {
                        "event_type": "TIMEFRAME_SNAPSHOT",
                        "source": "webhook1",
                        "symbol": "GOLDmicro",
                        "timeframe": "M1",
                        "candle_time": "2026.06.28 10:01:00",
                    }
                ).encode(),
            )
            handler.do_POST()

        self.assertEqual(handler.wfile.getvalue(), b"ok")
        update.assert_called_once()

    def test_webhook_accepts_non_json_body(self):
        handler = make_handler(
            webhook, "/webhook", b"some raw text"
        )
        handler.do_POST()
        self.assertEqual(handler.wfile.getvalue(), b"ignored")

    def test_webhook_engulfing_candle_sends_telegram_notification(self):
        with patch("webhook.telegram_sender.send_telegram_message") as send:
            handler = make_handler(
                webhook,
                "/webhook",
                b'{"event_type":"ENGULFING_CANDLE","signal":"BUY","symbol":"GOLDmicro","timeframe":"M15","candle_time":"2026.06.26 11:11:00","open":4029.07,"close":4030.23}',
            )
            handler.do_POST()

        self.assertEqual(handler.wfile.getvalue(), b"ok")
        send.assert_called_once()
        self.assertIn("GOLD", send.call_args.args[0])

    def test_webhook_big_move_sends_telegram_notification(self):
        with patch("webhook.telegram_sender.send_telegram_message") as send:
            handler = make_handler(
                webhook,
                "/webhook",
                b'{"event_type":"BIG_MOVE","symbol":"GOLDmicro","timeframe":"H1","candle_time":"2026.06.26 11:15:00","range":10,"daily_atr":40,"threshold":10,"atr_percent":25}',
            )
            handler.do_POST()

        self.assertEqual(handler.wfile.getvalue(), b"ok")
        self.assertIn("Big H1 Move", send.call_args.args[0])

    def test_trade_transaction_notification_filter(self):
        cases = (
            ("TRADE_TRANSACTION_REQUEST", 0, 260628, False),
            ("PENDING_ORDER_CREATED", 0, 260628, False),
            ("PENDING_ORDER_MODIFIED", 0, 260628, False),
            ("PENDING_ORDER_CANCELLED", 0, 260628, False),
            ("POSITION_SL_MODIFIED", 49.9, 260628, False),
            ("POSITION_SL_MODIFIED", 50, 260628, True),
            ("POSITION_OPENED", 0, 0, False),
        )
        with patch("webhook.telegram_sender.send_telegram_message") as send:
            expected_count = 0
            event_prefix = uuid4().hex
            for index, (kind, sl_change_pips, magic_number, expected) in enumerate(cases):
                handler = make_handler(webhook, "/webhook", json.dumps({
                    "event_type": "TRADE_TRANSACTION", "event_id": f"notification-filter-{event_prefix}-{index}",
                    "transaction_type": kind, "symbol": "GOLD", "sl_change_pips": sl_change_pips,
                    "magic_number": magic_number,
                }).encode())
                handler.do_POST()
                expected_count += expected
                self.assertEqual(send.call_count, expected_count)

    def test_manual_trade_reconciliation_does_not_notify(self):
        with patch("webhook.telegram_sender.send_telegram_message") as send:
            handler = make_handler(webhook, "/webhook", json.dumps({
                "event_type": "ACCOUNT_RECONCILIATION",
                "positions": [{
                    "position_ticket": uuid4().hex, "symbol": "GOLD", "magic_number": 0,
                    "profit_pips": 50, "floating_profit": 10,
                }],
            }).encode())
            handler.do_POST()

        self.assertEqual(handler.wfile.getvalue(), b"ok")
        send.assert_not_called()

    def test_telegram_pause_and_resume_commands_control_alerts(self):
        send = unittest.mock.MagicMock()
        with patch("webhook.telegram_sender.send_telegram_message", send):
            handler = make_handler(
                webhook,
                "/webhook",
                b'{"event_type":"ENGULFING_CANDLE","signal":"BUY","symbol":"GOLDmicro","timeframe":"M15","candle_time":"2026.06.26 11:11:00","open":4029.07,"close":4030.23}',
            )
            handler.do_POST()

            make_handler(
                webhook,
                "/telegram",
                b'{"message":{"text":"/pause","chat":{"id":"cmd-chat"}}}',
            ).do_POST()

            make_handler(
                webhook,
                "/telegram",
                b'{"message":{"text":"/resume","chat":{"id":"cmd-chat"}}}',
            ).do_POST()

        send.assert_any_call("⏸️ MT5 alerts paused", chat_id="cmd-chat")
        send.assert_any_call("▶️ MT5 alerts resumed", chat_id="cmd-chat")

    # -- Telegram commands --

    def test_telegram_command_can_arrive_on_webhook_path(self):
        with patch("webhook.telegram_sender.send_telegram_message") as send:
            handler = make_handler(
                webhook,
                "/webhook",
                b'{"message":{"text":"/status","chat":{"id":"cmd-chat"}}}',
            )
            handler.do_POST()

        self.assertEqual(handler.wfile.getvalue(), b"ok")
        send.assert_called_once()
        self.assertEqual(send.call_args.kwargs["chat_id"], "cmd-chat")
        self.assertIn("Bot online", send.call_args.args[0])

    def test_telegram_status_help_and_recent_commands(self):
        webhook.RECENT_SIGNALS.clear()
        webhook.RECENT_SIGNALS.extend(
            [
                {"symbol": "GOLD", "message": "signal 1"},
                {"symbol": "EURUSD", "message": "ignored"},
                {"symbol": "GOLD", "message": "signal 2"},
            ]
        )

        with patch("webhook.telegram_sender.send_telegram_message") as send:
            for text in ("/status", "/help", "/recent Gold"):
                make_handler(
                    webhook,
                    "/telegram",
                    json.dumps(
                        {"message": {"text": text, "chat": {"id": "cmd-chat"}}}
                    ).encode(),
                ).do_POST()

        messages = [call.args[0] for call in send.call_args_list]
        self.assertIn("✅ Bot online\nAlerts: running", messages[0])
        self.assertIn("/recent Gold", messages[1])
        self.assertEqual(
            messages[2], "Recent GOLD signals:\n1. signal 1\n2. signal 2"
        )

    def test_poll_telegram_once_replies_and_returns_next_offset(self):
        updates = [
            {
                "update_id": 41,
                "message": {"text": "/status", "chat": {"id": "cmd-chat"}},
            }
        ]

        with patch(
            "webhook.telegram_sender.get_telegram_updates",
            return_value=updates,
        ) as get_updates, patch(
            "webhook.telegram_sender.send_telegram_message"
        ) as send:
            next_offset = webhook.poll_telegram_once(10)

        get_updates.assert_called_once_with(offset=10, timeout_seconds=10)
        self.assertEqual(next_offset, 42)
        send.assert_called_once()
        self.assertEqual(send.call_args.kwargs["chat_id"], "cmd-chat")
        self.assertIn("Bot online", send.call_args.args[0])

    def test_summary_levels_and_rsi_commands_require_a_symbol(self):
        self.assertEqual(
            webhook.command_reply("/summary"), "Usage: /summary Gold"
        )
        self.assertEqual(
            webhook.command_reply("/levels"), "Usage: /levels Gold"
        )
        self.assertEqual(webhook.command_reply("/rsi"), "Usage: /rsi Gold")

    def test_help_lists_summary_levels_rsi_and_trade_commands(self):
        message = webhook.help_text()
        self.assertIn("/summary Gold", message)
        self.assertIn("/levels Gold", message)
        self.assertIn("/rsi Gold", message)
        self.assertIn("/buy - Start trailing buy-limit mode", message)
        self.assertIn("/sell - Start trailing sell-limit mode", message)
        self.assertIn("/notrade - Stop trading activity", message)


# ── EA error handling ──────────────────────────────────────────────────


class EaErrorTest(unittest.TestCase):
    """EA error payload handling."""

    def test_ea_error_payload_is_sent_to_telegram(self):
        payload = {
            "event_type": "EA_ERROR",
            "symbol": "GOLDmicro",
            "timeframe": "M1",
            "message": "BuyLimit failed",
            "detail": "retcode=10030",
        }
        with patch("webhook.telegram_sender.send_telegram_message") as send:
            handler = make_handler(webhook, "/webhook", json.dumps(payload).encode())
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
                "webhook.telegram_sender.send_telegram_message"
            ) as send:
                payload = {
                    "event_type": "EA_ERROR",
                    "source": source,
                    "message": "EA failed",
                }
                handler = make_handler(
                    webhook, "/webhook", json.dumps(payload).encode()
                )
                handler.do_POST()

                self.assertEqual(handler.wfile.getvalue(), b"ok")
                send.assert_called_once()

    # -- Snapshot integration --

    def test_webhook1_snapshot_updates_market_state(self):
        from tests.test_helpers import snapshot

        payload = snapshot("M1", "2026.06.28 10:01:00")
        payload["source"] = "webhook1"
        with patch.object(
            webhook.MARKET_STATE, "update", return_value=[]
        ) as update:
            handler = make_handler(webhook, "/webhook", json.dumps(payload).encode())
            handler.do_POST()

        self.assertEqual(handler.wfile.getvalue(), b"ok")
        update.assert_called_once_with(payload)

    def test_strong_rsi_snapshot_sends_telegram_notification(self):
        payload = {
            "event_type": "TIMEFRAME_SNAPSHOT",
            "symbol": "GOLDmicro",
            "timeframe": "M5",
            "candle_time": "2026.06.28 10:01:00",
            "open": 2300.0,
            "high": 2310.0,
            "low": 2290.0,
            "close": 2305.0,
            "rsi14": 71.5,
        }
        notification = {
            "event_type": "STRONG_RSI",
            "symbol": "GOLD",
            "timeframe": "M5",
            "candle_time": payload["candle_time"],
            "rsi14": payload["rsi14"],
        }
        with patch.object(webhook.MARKET_STATE, "update", return_value=[notification]), \
             patch.object(webhook.MARKET_STATE, "mark_notified"), \
             patch("webhook.telegram_sender.send_telegram_message") as send:
            handler = make_handler(webhook, "/webhook", json.dumps(payload).encode())
            handler.do_POST()

        self.assertEqual(handler.wfile.getvalue(), b"ok")
        message = send.call_args.args[0]
        self.assertIn("Strong RSI(14)", message)
        self.assertIn("71.50", message)
        self.assertIn("Overbought / SELL", message)

    def test_key_level_snapshot_sends_higher_timeframe_notification(self):
        payload = {
            "event_type": "TIMEFRAME_SNAPSHOT",
            "symbol": "GOLDmicro",
            "timeframe": "M5",
            "candle_time": "2026.06.28 10:01:00",
            "open": 2285.0,
            "high": 2285.0,
            "low": 2275.0,
            "close": 2280.0,
        }
        notification = {
            "event_type": "KEY_LEVEL_REACHED",
            "symbol": "GOLD",
            "timeframe": "M15",
            "candle_time": payload["candle_time"],
            "key_level_price": 2280.0,
            "key_level_label": "Support",
            "coincident_timeframes": ["M5"],
            "digits": 2,
        }
        with patch.object(webhook.MARKET_STATE, "update", return_value=[notification]), \
             patch.object(webhook.MARKET_STATE, "mark_notified"), \
             patch("webhook.telegram_sender.send_telegram_message") as send:
            handler = make_handler(webhook, "/webhook", json.dumps(payload).encode())
            handler.do_POST()

        message = send.call_args.args[0]
        self.assertIn("M15 Support", message)
        self.assertIn("Also coincides with M5 timeframe key level.", message)


# ── Trade state / config ──────────────────────────────────────────────


class TradeStateTest(unittest.TestCase):
    """Trade mode persistence and symbol overrides."""

    def setUp(self):
        self.trade_state_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.trade_state_directory.cleanup)
        self.trade_state_env = patch.dict(
            os.environ,
            {
                "TRADE_STATE_FILE": str(
                    Path(self.trade_state_directory.name) / "trade_state.json"
                )
            },
        )
        self.trade_state_env.start()
        self.addCleanup(self.trade_state_env.stop)
        from webhook import trade_state, state

        state.ALERTS_PAUSED = False
        state.RECENT_SIGNALS.clear()
        trade_state.TRADE_MODE = "NOTRADE"
        trade_state.TRADE_STATE.clear()
        trade_state.TRADE_STATE.update({
            "default_mode": "NOTRADE",
            "symbols": {},
            "updated_at": "",
        })

    def test_trade_mode_commands_update_trade_config(self):
        with patch.dict(
            os.environ, {"TRADE_LOT_SIZE": "0.30", "TRAIL_PIPS": "25"}
        ):
            self.assertIn("BUY limit mode", webhook.command_reply("/buy"))
            self.assertEqual(
                webhook.trade_config(),
                {"mode": "BUY", "lot_size": 0.30, "trail_pips": 25.0},
            )
            self.assertIn(
                "SELL limit mode", webhook.command_reply("/sell")
            )
            self.assertEqual(webhook.trade_config()["mode"], "SELL")
            self.assertIn(
                "Trading paused", webhook.command_reply("/notrade")
            )
            self.assertEqual(webhook.trade_config()["mode"], "NOTRADE")

    def test_missing_trade_state_uses_defaults(self):
        self.assertEqual(
            webhook.load_trade_state(),
            {"default_mode": "NOTRADE", "symbols": {}, "updated_at": ""},
        )

    def test_corrupt_trade_state_uses_defaults(self):
        webhook.trade_state_path().write_text("{broken", encoding="utf-8")
        self.assertEqual(
            webhook.load_trade_state(),
            {"default_mode": "NOTRADE", "symbols": {}, "updated_at": ""},
        )

    def test_buy_saves_default_trade_mode(self):
        webhook.command_reply("/buy")
        saved = json.loads(
            webhook.trade_state_path().read_text(encoding="utf-8")
        )
        self.assertEqual(saved["default_mode"], "BUY")
        self.assertTrue(saved["updated_at"].endswith("Z"))

    def test_load_trade_state_restores_default_mode(self):
        webhook.command_reply("/sell")
        self.assertEqual(webhook.load_trade_state()["default_mode"], "SELL")

    def test_save_trade_state_creates_parent_directories(self):
        nested = (
            Path(self.trade_state_directory.name)
            / "missing"
            / "directory"
            / "state.json"
        )
        with patch.dict(os.environ, {"TRADE_STATE_FILE": str(nested)}):
            webhook.save_trade_state(
                {
                    "default_mode": "BUY",
                    "symbols": {},
                    "updated_at": "",
                }
            )
        self.assertEqual(
            json.loads(nested.read_text(encoding="utf-8"))["default_mode"],
            "BUY",
        )

    def test_symbol_trade_commands_do_not_change_default_mode(self):
        webhook.command_reply("/buy")
        self.assertIn(
            "for GOLD", webhook.command_reply("/sell Gold")
        )
        self.assertEqual(webhook.get_trade_mode(), "BUY")
        self.assertEqual(webhook.get_trade_mode("GOLD"), "SELL")
        self.assertIn(
            "for GOLD", webhook.command_reply("/notrade Gold")
        )
        self.assertEqual(webhook.get_trade_mode(), "BUY")
        self.assertEqual(webhook.get_trade_mode("GOLD"), "NOTRADE")

    def test_symbol_overrides_are_saved_and_reloaded(self):
        webhook.command_reply("/buy Gold")
        saved = json.loads(
            webhook.trade_state_path().read_text(encoding="utf-8")
        )
        reloaded = webhook.load_trade_state()
        self.assertEqual(webhook.get_trade_mode(), "NOTRADE")
        self.assertEqual(saved["symbols"], {"GOLD": "BUY"})
        self.assertEqual(reloaded["symbols"], {"GOLD": "BUY"})

    def test_status_reports_symbol_mode(self):
        webhook.command_reply("/buy Gold")
        self.assertIn(
            "Trade mode for GOLD: BUY",
            webhook.command_reply("/status Gold"),
        )

    def test_status_reports_default_mode_and_symbol_overrides(self):
        webhook.command_reply("/buy")
        webhook.command_reply("/sell Gold")
        status = webhook.command_reply("/status")
        self.assertIn("Default trade mode: BUY", status)
        self.assertIn("GOLD: SELL", status)

    def test_trade_config_endpoint_returns_json(self):
        webhook.command_reply("/buy")
        handler = make_handler(
            webhook, "/trade-config?symbol=Gold", method="GET"
        )
        handler.do_GET()
        self.assertIn(("code", 200), handler.responses)
        self.assertIn(
            ("Content-Type", "application/json; charset=utf-8"),
            handler.responses,
        )
        self.assertEqual(
            json.loads(handler.wfile.getvalue()), webhook.trade_config()
        )

    def test_trade_config_endpoint_uses_normalized_symbol_override(self):
        webhook.command_reply("/buy")
        webhook.command_reply("/sell Gold")

        exact_gold = make_handler(
            webhook, "/trade-config?symbol=GOLD", method="GET"
        )
        exact_gold.do_GET()
        gold = make_handler(
            webhook, "/trade-config?symbol=GOLDmicro", method="GET"
        )
        gold.do_GET()
