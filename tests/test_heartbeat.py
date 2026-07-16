"""Tests for EA heartbeat management."""
from __future__ import annotations

import json
import time
import unittest
from io import BytesIO
from unittest.mock import patch

import webhook
from tests.test_helpers import make_handler


class HeartbeatTest(unittest.TestCase):
    """EA heartbeat recording and status reporting."""

    def setUp(self):
        webhook.EA_HEARTBEATS.clear()
        webhook.HEARTBEAT_ALERT_STATES.clear()

    def test_record_ea_heartbeat_stores_source_symbol_and_status(self):
        webhook.record_ea_heartbeat(
            {
                "event_type": "EA_HEARTBEAT",
                "source": "webhook1",
                "symbol": "GOLDmicro",
                "status": "running",
            }
        )
        self.assertIn("webhook1", webhook.EA_HEARTBEATS)
        entry = webhook.EA_HEARTBEATS["webhook1"]
        self.assertEqual(entry["source"], "webhook1")
        self.assertEqual(entry["symbol"], "GOLD")
        self.assertEqual(entry["status"], "running")
        self.assertIn("last_seen", entry)

    def test_record_ea_heartbeat_normalizes_symbol(self):
        webhook.record_ea_heartbeat(
            {
                "event_type": "EA_HEARTBEAT",
                "source": "webhook1",
                "symbol": "XAUUSD",
                "status": "running",
            }
        )
        self.assertEqual(
            webhook.EA_HEARTBEATS["webhook1"]["symbol"], "GOLD"
        )

    def test_record_ea_heartbeat_normalizes_source_to_lowercase(self):
        webhook.record_ea_heartbeat(
            {
                "event_type": "EA_HEARTBEAT",
                "source": "Webhook1",
                "symbol": "GOLDmicro",
                "status": "running",
            }
        )
        self.assertIn("webhook1", webhook.EA_HEARTBEATS)

    def test_webhook_ea_heartbeat_returns_ok_no_telegram(self):
        with patch("webhook.send_telegram_message") as send:
            handler = webhook.WebhookHandler.__new__(webhook.WebhookHandler)
            handler.path = "/webhook"
            handler.request_version = "HTTP/1.1"
            body = json.dumps(
                {
                    "event_type": "EA_HEARTBEAT",
                    "source": "webhook1",
                    "symbol": "GOLDmicro",
                    "status": "running",
                }
            ).encode()
            handler.headers = {"Content-Length": str(len(body))}
            handler.rfile = BytesIO(body)
            handler.wfile = BytesIO()
            handler.send_response = lambda code: None
            handler.end_headers = lambda: None
            handler.do_POST()

        self.assertEqual(handler.wfile.getvalue(), b"ok")
        send.assert_not_called()

    def test_webhook_ea_heartbeat_stores_heartbeat(self):
        webhook.EA_HEARTBEATS.clear()
        with patch("webhook.send_telegram_message") as send:
            handler = webhook.WebhookHandler.__new__(webhook.WebhookHandler)
            handler.path = "/webhook"
            handler.request_version = "HTTP/1.1"
            body = json.dumps(
                {
                    "event_type": "EA_HEARTBEAT",
                    "source": "webhook2",
                    "symbol": "GOLDmicro",
                    "status": "running",
                }
            ).encode()
            handler.headers = {"Content-Length": str(len(body))}
            handler.rfile = BytesIO(body)
            handler.wfile = BytesIO()
            handler.send_response = lambda code: None
            handler.end_headers = lambda: None
            handler.do_POST()

        self.assertIn("webhook2", webhook.EA_HEARTBEATS)
        self.assertEqual(
            webhook.EA_HEARTBEATS["webhook2"]["symbol"], "GOLD"
        )

    def test_status_shows_missing_when_no_heartbeats(self):
        webhook.EA_HEARTBEATS.clear()
        status = webhook.command_reply("/status")
        self.assertIn("EA status:", status)
        self.assertIn("Webhook1: missing", status)
        self.assertIn("Webhook2: missing", status)
        self.assertIn("TPSL: missing", status)

    def test_status_shows_running_with_fresh_heartbeat(self):
        webhook.EA_HEARTBEATS.clear()
        webhook.record_ea_heartbeat(
            {
                "event_type": "EA_HEARTBEAT",
                "source": "webhook1",
                "symbol": "GOLDmicro",
                "status": "running",
            }
        )
        status = webhook.command_reply("/status")
        self.assertIn("Webhook1: running, GOLD", status)
        self.assertIn("Webhook2: missing", status)

    def test_status_shows_stale_when_heartbeat_old(self):
        webhook.EA_HEARTBEATS.clear()
        age = webhook.heartbeat_stale_seconds() + 10
        webhook.EA_HEARTBEATS["webhook1"] = {
            "source": "webhook1",
            "symbol": "GOLD",
            "status": "running",
            "last_seen": time.monotonic() - age,
        }
        status = webhook.command_reply("/status")
        self.assertIn("Webhook1: stale, GOLD", status)

    def test_unknown_source_accepted_and_appears_after_known(self):
        webhook.EA_HEARTBEATS.clear()
        webhook.record_ea_heartbeat(
            {
                "event_type": "EA_HEARTBEAT",
                "source": "myea",
                "symbol": "EURUSD",
                "status": "running",
            }
        )
        lines = webhook.heartbeat_status_lines()
        self.assertEqual(lines[0], "Webhook1: missing")
        self.assertTrue(any("Myea" in line for line in lines))

    def test_stale_alert_is_sent_once_then_recovery_is_sent_once(self):
        now = 1_000
        webhook.EA_HEARTBEATS["webhook1"] = {
            "source": "webhook1",
            "symbol": "GOLD",
            "status": "running",
            "last_seen": now - webhook.heartbeat_stale_seconds() - 1,
        }
        alerts = []

        webhook.check_heartbeat_alerts(now=now, notify=alerts.append)
        webhook.check_heartbeat_alerts(now=now + 1, notify=alerts.append)
        webhook.EA_HEARTBEATS["webhook1"]["last_seen"] = now + 2
        webhook.check_heartbeat_alerts(now=now + 2, notify=alerts.append)
        webhook.check_heartbeat_alerts(now=now + 3, notify=alerts.append)

        self.assertEqual(len(alerts), 2)
        self.assertIn("stale", alerts[0])
        self.assertIn("recovered", alerts[1])


if __name__ == "__main__":
    unittest.main()
