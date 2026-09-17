"""Dashboard regressions using an isolated journal and rendered HTML."""

import io
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from frontend import routes
from webhook import trade_state
from webhook.account import AccountStore
from webhook.strategy import settings
from webhook.strategy_journal import StrategyJournal


class DashboardTests(unittest.TestCase):
    def test_open_trade_and_daily_deal_cash_flow(self):
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
        with tempfile.TemporaryDirectory() as directory:
            store = AccountStore(Path(directory) / "test.db")
            journal = StrategyJournal(store)
            journal.reserve({"setup_id": "s", "symbol": "GOLD", "evaluated_at": today,
                             "expires_at": today + 30}, "demo:1")
            base = {"setup_id": "s", "broker_server": "demo", "account_login": 1, "position_ticket": "1"}
            journal.record(dict(base, deal_ticket="1", transaction_type="POSITION_OPENED", volume=1, commission=-2), today - 200)
            handler = SimpleNamespace(path="/dashboard", write_text=Mock())
            with patch.object(routes, "STORE", store):
                routes.dashboard(handler)
                self.assertEqual(handler.write_text.call_args.args[0], 200)
                journal.record(dict(base, deal_ticket="2", transaction_type="PARTIAL_CLOSE", volume=.5, profit=100, commission=-1), today - 100)
                close = dict(base, deal_ticket="3", transaction_type="POSITION_CLOSED", volume=.5, profit=50, commission=-1, swap=-1, fee=-1)
                journal.record(close, today)
                journal.record(close, today)  # Delivery retries must not double count.
                journal.record(dict(base, position_ticket="2", deal_ticket="4", transaction_type="POSITION_OPENED", volume=1, commission=-2), today + 1)
                journal.record(dict(base, deal_ticket="5", transaction_type="PARTIAL_CLOSE", profit=999), today + 86400)
                routes.dashboard(handler)
            html = handler.write_text.call_args.args[1]
            self.assertIn("Today realized P&amp;L (UTC)", html)
            self.assertIn("+45.00", html)
            self.assertEqual(journal.realized(today, today + 86400, "demo:1")["net"], 45)
            self.assertEqual(journal.realized(today, today + 86400, "demo:2")["net"], 0)

    def test_modes_render_current_runtime_and_submit_explicit_selection(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(trade_state, "TRADE_MODE", "NOTRADE"), \
                patch.object(trade_state, "TRADE_STATE", {"default_mode": "NOTRADE", "symbols": {}}), \
                patch.object(trade_state, "save_trade_state"), \
                patch.object(routes, "STORE", AccountStore(Path(directory) / "test.db")):
            trade_state.set_trade_mode("AUTO")
            for mode in ("BUY", "SELL", "LEVEL", "EMA", "AUTO", "NOTRADE"):
                trade_state.set_trade_mode(mode, "GOLD")
                handler = SimpleNamespace(path="/dashboard", write_text=Mock())
                routes.dashboard(handler)
                html = handler.write_text.call_args.args[1]
                self.assertIn("Default: AUTO", html)
                self.assertIn(f'<option value="{mode}" selected>{mode}</option>', html)
                self.assertNotIn("Resume AUTO", html)
                body = f"symbol=GOLD&mode={mode}".encode()
                handler = SimpleNamespace(rfile=io.BytesIO(body), headers={"Content-Length": str(len(body))}, write_json=Mock())
                routes.trade_mode_api(handler)
                self.assertEqual(handler.write_json.call_args.args[0], 200)
                self.assertEqual(trade_state.get_trade_mode("GOLD"), mode)

    def test_invalid_mode_does_not_mutate_runtime(self):
        for body in (b"symbol=GOLD&mode=UNKNOWN", b"symbol=GOLD", b"symbol=+++&mode=AUTO"):
            handler = SimpleNamespace(rfile=io.BytesIO(body), headers={"Content-Length": str(len(body))}, write_json=Mock())
            with patch.object(routes, "set_trade_mode") as setter:
                routes.trade_mode_api(handler)
                self.assertEqual(handler.write_json.call_args.args[0], 400)
                setter.assert_not_called()

    def test_execution_timeout_reconciliation_and_entry_hold(self):
        now = 1800000000
        cfg = settings()
        with tempfile.TemporaryDirectory() as directory, patch("webhook.account.time.time", return_value=now) as clock:
            store = AccountStore(Path(directory) / "test.db")
            journal = StrategyJournal(store)
            journal.reserve({"setup_id": "s", "symbol": "GOLD", "evaluated_at": now - 1000,
                             "expires_at": now - cfg["execution_ack_timeout_seconds"]}, "demo:1")
            store.event({"event_id": "pass", "event_type": "ENTRY_DECISION", "setup_id": "s", "result": "PASS"})
            self.assertEqual(journal.lifecycle(now=now - 1)[0]["status"], "Submitted")
            self.assertEqual(journal.lifecycle(now=now)[0]["status"], "Uncertain")
            self.assertIn("missing or stale", journal.entry_hold("demo:1", "GOLD", now, cfg))
            position = {"position_ticket": "1", "symbol": "GOLD", "comment": "S:s"}
            snapshot = {"broker_server": "demo", "account_login": 1, "positions": [position]}
            store.reconcile([position], snapshot)
            self.assertEqual(journal.lifecycle(now=now)[0]["status"], "Filled")
            self.assertIn("Open position", journal.entry_hold("demo:1", "GOLD", now, cfg))
            self.assertIn("missing or stale", journal.entry_hold("demo:1", "GOLD", now + cfg["account_max_age_seconds"] + 1, cfg))
            clock.return_value = now + 1
            store.reconcile([], {**snapshot, "positions": []})
            self.assertIn("uncertain", journal.entry_hold("demo:1", "GOLD", now + 1, cfg))
            store.event({"event_id": "reject", "event_type": "ENTRY_DECISION", "setup_id": "s", "result": "FAIL", "reason": "retcode=10006"})
            self.assertEqual(journal.entry_hold("demo:1", "GOLD", now + 1, cfg), "")


if __name__ == "__main__":
    unittest.main()
