"""Exact response contracts for the Telegram command surface."""

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import webhook

FIXTURES = Path(__file__).with_name("fixtures")


class CommandContractTest(unittest.TestCase):
    def setUp(self):
        from webhook import heartbeat, state, trade_state

        state.ALERTS_PAUSED = False
        state.RECENT_SIGNALS.clear()
        heartbeat.EA_HEARTBEATS.clear()
        trade_state.TRADE_MODE = "NOTRADE"
        trade_state.TRADE_STATE.clear()
        trade_state.TRADE_STATE.update(
            {
                "default_mode": "NOTRADE",
                "symbols": {},
                "overtrade_enabled": True,
                "overtrade_profit_target": 1.0,
                "key_level_orders_enabled": True,
                "updated_at": "",
            }
        )

    def test_representative_payload_fixtures_are_valid(self):
        telegram = json.loads((FIXTURES / "telegram_status.json").read_text(encoding="utf-8"))
        snapshot = json.loads((FIXTURES / "timeframe_snapshot.json").read_text(encoding="utf-8"))

        self.assertEqual(telegram["message"]["text"], "/status")
        self.assertTrue(webhook.is_supported_payload(snapshot))

    def test_health_response_snapshot(self):
        with (
            patch("webhook.messages.telegram_configured", return_value=True),
            patch("webhook.messages.uptime_text", return_value="1m"),
        ):
            self.assertEqual(
                webhook.health_text(),
                "\u2705 Webhook healthy\nTelegram: configured\nAlerts: running\nUptime: 1m",
            )

    def test_core_command_response_snapshots(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                webhook.command_reply("/status"),
                "\u2705 Bot online\n"
                "Alerts: running\n"
                "Telegram: missing\n"
                "Recent signals: 0\n"
                "Default trade mode: NOTRADE\n"
                "Overtrade security: enabled (close at $1.00)\n"
                "Key-level limit orders: enabled\n\n"
                "EA status:\n"
                "Webhook1: missing\n"
                "Webhook2: missing\n"
                "TPSL: missing\n"
                "Overtrade: missing",
            )
        self.assertEqual(webhook.command_reply("/pause"), "\u23f8\ufe0f MT5 alerts paused")
        self.assertEqual(webhook.command_reply("/resume"), "\u25b6\ufe0f MT5 alerts resumed")
        self.assertEqual(webhook.command_reply("/summary"), "Usage: /summary Gold")
        self.assertEqual(
            webhook.command_reply("/overtrade"),
            "Overtrade security is enabled. Profit target: $1.00\n"
            "Usage: /overtrade on | off | <profit target>",
        )

    def test_unknown_command_falls_back_to_help(self):
        self.assertEqual(webhook.command_reply("/unknown anything"), webhook.help_text())

    def test_parser_keeps_second_value_generic(self):
        from webhook.command_parser import parse_command

        self.assertEqual(parse_command("/overtrade@my_bot 12.5 ignored"), ("/overtrade", "12.5"))

    def test_plain_package_import_does_not_initialize_server(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                "import sys, webhook; print('webhook.server' in sys.modules)",
            ],
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.stdout.strip(), "False")


if __name__ == "__main__":
    unittest.main()
