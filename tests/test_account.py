import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from webhook.account import AccountStore, due_reports, market_report, pip_size, price_report, report_text, session_status


class _State:
    def __init__(self, snapshot):
        self.data = {"symbols": {"GOLD": {"M1": snapshot, "M5": snapshot}}}


class AccountFeatureTest(unittest.TestCase):
    def test_price_report_and_stale_warning(self):
        snapshot = {"bid": 2350.0, "ask": 2350.1, "daily_open": 2300, "daily_high": 2360, "daily_low": 2290, "digits": 2, "candle_time": "now", "received_at": time.time() - 999}
        report = price_report("Goldmicro", _State(snapshot))
        self.assertIn("GOLD Price", report); self.assertIn("stale", report)

    def test_market_session_uses_dst_zone(self):
        self.assertIn("London", session_status(datetime(2026, 7, 1, 17, 0, tzinfo=__import__("zoneinfo").ZoneInfo("Asia/Manila"))))

    def test_gold_pip_size_and_transaction_deduplication(self):
        self.assertEqual(pip_size("Goldmicro", 2), 0.1)
        with tempfile.TemporaryDirectory() as directory:
            store = AccountStore(Path(directory) / "account.db")
            self.assertTrue(store.event({"event_id": "deal-1"}))
            self.assertFalse(store.event({"event_id": "deal-1"}))

    def test_event_uses_payload_time_and_delivery_lease_recovers(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AccountStore(Path(directory) / "account.db")
            store.event({"event_id": "old", "event_time": "2020.01.01 00:00:00", "event_time_offset_seconds": 28800})
            start = datetime(2019, 12, 31, tzinfo=__import__("zoneinfo").ZoneInfo("Asia/Manila"))
            self.assertEqual(len(store.events_between(start, start + __import__("datetime").timedelta(days=2))), 1)
            self.assertTrue(store.claim_delivery("old", 0))
            self.assertTrue(store.claim_delivery("old", 0))
            store.delivered("old")
            self.assertFalse(store.claim_delivery("old", 0))

    def test_action_claim_lease_and_pending_orders_survive_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "account.db"; store = AccountStore(path)
            store.queue_action("be", {"tickets": ["1"]})
            first = store.claim_action(); self.assertIsNotNone(first)
            with store._connect() as db:
                db.execute("UPDATE actions SET claim_until=0")
            self.assertIsNotNone(store.claim_action())
            store.reconcile([], {"pending_orders": [{"order_ticket": "7", "symbol": "GOLD"}]})
            with store._connect() as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM pending_orders").fetchone()[0], 1)

    def test_confirmation_is_single_use_and_cooldown_can_retry_after_delivery_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AccountStore(Path(directory) / "account.db")
            token = store.confirmation("close", {"tickets": ["1"]})
            self.assertIsNotNone(store.consume_confirmation(token))
            self.assertIsNone(store.consume_confirmation(token))
            self.assertTrue(store.claim_cooldown("decision", 60))
            store.release_cooldown("decision")
            self.assertTrue(store.claim_cooldown("decision", 60))

    def test_market_report_uses_m5_ema(self):
        snapshot = {"ema20": 2, "ema50": 1, "received_at": time.time()}
        self.assertIn("Bullish", market_report("GOLD", _State(snapshot)))

    def test_reconciliation_removes_departed_positions(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AccountStore(Path(directory) / "account.db")
            store.reconcile([{"position_ticket": "1"}])
            store.reconcile([{"position_ticket": "2"}])
            self.assertEqual(store.positions(), [{"position_ticket": "2"}])

    def test_daily_report_is_due_at_six_am_manila(self):
        reports = due_reports(datetime(2026, 7, 1, 6, 0, tzinfo=__import__("zoneinfo").ZoneInfo("Asia/Manila")))
        self.assertTrue(any(name == "Daily 24-hour Report" for name, _, _ in reports))

    def test_report_includes_account_snapshot_and_stop_loss_close(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AccountStore(Path(directory) / "account.db")
            store.reconcile([], {"balance": 1000, "equity": 995, "pending_orders": []})
            store.event({"event_id": "sl-1", "event_type": "TRADE_TRANSACTION", "transaction_type": "STOP_LOSS_HIT", "symbol": "GOLD", "profit": -5, "magic_number": 260628})
            store.event({"event_id": "m5-1", "event_type": "TIMEFRAME_SNAPSHOT", "symbol": "GOLD", "timeframe": "M5", "candle_time": "2026.01.01 00:00", "open": 10, "high": 12, "low": 9, "close": 11})
            now = datetime.now(__import__("zoneinfo").ZoneInfo("Asia/Manila"))
            text = report_text("Daily", now - __import__("datetime").timedelta(minutes=1), now + __import__("datetime").timedelta(minutes=1), store)
            self.assertIn("Balance / Equity: 1000 / 995", text)
            self.assertIn("0/1/0", text)
            self.assertIn("GOLD session O/H/L/C: 10.0 / 12.0 / 9.0 / 11.0 (+10.00%)", text)
            self.assertIn("Starting balance: unavailable", text)

    def test_session_windows_use_local_start_and_recovery_requires_data(self):
        now = datetime(2026, 7, 2, 2, 0, tzinfo=__import__("zoneinfo").ZoneInfo("Asia/Manila"))
        london = next(item for item in due_reports(now) if item[0] == "London Session Report")
        self.assertEqual(london[1].astimezone(__import__("zoneinfo").ZoneInfo("Europe/London")).hour, 8)
        self.assertEqual(london[2].astimezone(__import__("zoneinfo").ZoneInfo("Europe/London")).hour, 17)
        with tempfile.TemporaryDirectory() as directory:
            store = AccountStore(Path(directory) / "account.db")
            recovered = due_reports(now, store)
            self.assertFalse(any(end < london[2] for name, _, end in recovered if name == "London Session Report"))

    def test_report_uses_gross_profit_and_end_snapshot_positions(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AccountStore(Path(directory) / "account.db")
            start = datetime.now(__import__("zoneinfo").ZoneInfo("Asia/Manila")) - timedelta(minutes=2)
            store.reconcile([{ "position_ticket": "1", "floating_profit": 3}], {"balance": 100, "equity": 103, "positions": [{"position_ticket": "1", "floating_profit": 3}]})
            store.event({"event_id": "close", "event_type": "TRADE_TRANSACTION", "transaction_type": "MANUAL_PARTIAL_CLOSE", "profit": 10, "commission": -2, "swap": -1})
            text = report_text("Daily", start, start + timedelta(minutes=3), store)
            self.assertIn("Gross +/− / Net: +10.00 / +0.00 / +7.00", text)
            self.assertIn("partial closes: 1", text)
            self.assertIn("Open positions / floating at report end: 1 / +3.00", text)

    def test_missed_daily_window_is_returned_after_restart(self):
        reports = due_reports(datetime(2026, 7, 1, 5, 0, tzinfo=__import__("zoneinfo").ZoneInfo("Asia/Manila")))
        daily = next(item for item in reports if item[0] == "Daily 24-hour Report")
        self.assertEqual(daily[2].hour, 6)
        self.assertEqual(daily[2].day, 30)
