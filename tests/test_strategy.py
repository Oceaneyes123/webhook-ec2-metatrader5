"""Deterministic market and lifecycle scenarios, without Telegram or a broker."""

import copy
import json
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from webhook.account import AccountStore
from webhook.strategy import evaluate, settings, true_ranges
from webhook.strategy_journal import StrategyJournal, metrics, overtrade_reason, performance_report
from webhook.strategy_runtime import execution_config, session_name, journal_transaction

NOW = datetime(2026, 9, 9, 14, tzinfo=timezone.utc).timestamp()


def market(sell=False, breakout=False):
    candles = [{"candle_time": str(i).zfill(2), "open": 102, "close": 102.2, "high": 103.2, "low": 101, "rsi14": 52} for i in range(32)]
    for i, close in enumerate((103, 102.5, 102, 101.5, 100.3), 26):
        candles[i].update(open=close + .2, close=close, high=close + 1, low=close - 1)
    if breakout:
        for i, close in enumerate((98.5, 99, 99.5, 101.5, 100.3), 26):
            candles[i].update(open=close - .8, close=close, high=close + .3, low=close - 1)
    candles[-1].update(open=100, close=101, low=99.4, high=101.3, rsi14=55)
    snap = {"candle_time": "31", "closed_at": NOW - 10, "received_at": NOW - 5,
            "ema20": 100.5, "ema50": 99.5, "rsi14": 55, "digits": 2,
            "candle_history": candles, "levels": {"support": 100, "resistance": 112, "fib": {"61.8": 100}}}
    if breakout:
        snap["levels"] = {"support": 100, "resistance": 112}
    if sell:
        for candle in candles:
            candle.update(open=200 - candle["open"], close=200 - candle["close"], low=200 - candle["high"], high=200 - candle["low"], rsi14=100 - candle["rsi14"])
        snap.update(ema20=99.5, ema50=100.5, rsi14=45, levels={"support": 88, "resistance": 100, "fib": {"61.8": 100}})
    frames = {tf: copy.deepcopy(snap) for tf in ("M5", "M15", "M30", "H1", "H4")}
    structure = {tf: {"trend": "bearish" if sell else "bullish"} for tf in ("M30", "H1", "H4")}
    quote = {"bid": 99 if sell else 100.98, "ask": 99.02 if sell else 101, "received_at": NOW, "tick_size": .01}
    return frames, structure, quote


class StrategyTests(unittest.TestCase):
    def setUp(self):
        self.cfg = settings()
        self.frames, self.structure, self.quote = market()

    def run_plan(self, session="London/NY"):
        return evaluate(self.frames, self.structure, "GOLD", NOW, session, self.cfg, self.quote)

    def test_bullish_and_bearish_a_plus_pullbacks(self):
        for sell in (False, True):
            self.frames, self.structure, self.quote = market(sell)
            p = self.run_plan()
            self.assertEqual(p["result"], "PASS", p)
            self.assertEqual(p["direction"], "SELL" if sell else "BUY")
            self.assertEqual(p["setup_type"], "pullback")
            self.assertEqual(p["grade"], "A+")
            self.assertAlmostEqual(abs(p["tp"] - p["entry"]) / abs(p["entry"] - p["sl"]), p["planned_rr"])
            self.assertTrue(p["sl"] > p["invalidation"] if sell else p["sl"] < p["invalidation"])

    def test_breakout_waits_for_closed_break_then_retest(self):
        self.frames, self.structure, self.quote = market(breakout=True)
        p = self.run_plan()
        self.assertEqual(p["result"], "PASS", p)
        self.assertEqual(p["setup_type"], "breakout_retest")
        self.cfg["enabled_setups"] = ["breakout_retest"]
        for frame in self.frames.values():
            frame["candle_history"][-3]["close"] = 99.9
        self.assertEqual(self.run_plan()["result"], "FAIL")

    def test_conflicting_structure_and_range(self):
        self.structure["H1"]["trend"] = "bearish"
        self.assertIn("conflicts", self.run_plan()["reason"])
        for s in self.structure.values():
            s["trend"] = "ranging"
        self.assertIn("ranging", self.run_plan()["reason"])

    def test_changing_one_choch_to_range_does_not_reverse(self):
        self.structure["H4"]["trend"] = "ranging"
        p = self.run_plan()
        self.assertEqual(p["direction"], "BUY")
        self.assertIn("range_penalty", p["score_evidence"])

    def test_nearby_opposition_cannot_manufacture_rr(self):
        for frame in self.frames.values():
            frame["levels"]["resistance"] = 102
        p = self.run_plan()
        self.assertEqual(p["result"], "FAIL")
        self.assertIn("Opposing level", p["reason"])
        self.assertLess(p["planned_rr"], self.cfg["min_rr"])

    def test_extension_volatility_spread_and_low_score(self):
        self.quote.update(bid=107.98, ask=108)
        self.assertIn("extended", self.run_plan()["reason"])
        self.frames, self.structure, self.quote = market()
        for frame in self.frames.values():
            frame["candle_history"][-1]["high"] = 120
        self.assertIn("expansion", self.run_plan()["reason"])
        self.frames, self.structure, self.quote = market()
        self.cfg["atr_max_ratio"] = .5
        self.assertIn("volatility", self.run_plan()["reason"])
        self.cfg = settings()
        self.quote["bid"] = 99
        self.assertIn("Spread", self.run_plan()["reason"])
        self.quote["bid"] = 100.98
        self.cfg["weights"] = {key: 1 for key in self.cfg["weights"]}
        self.assertIn("Score", self.run_plan()["reason"])

    def test_session_stale_and_nonfinite_data(self):
        self.cfg["allowed_sessions"] = ["London"]
        self.assertIn("Session restricted", self.run_plan()["reason"])
        self.cfg = settings()
        self.frames["H1"]["closed_at"] = NOW - 20000
        self.assertIn("Stale", self.run_plan()["reason"])
        self.frames["H1"]["closed_at"] = NOW - 10
        self.quote["ask"] = float("nan")
        self.assertIn("invalid execution quote", self.run_plan()["reason"])

    def test_rejection_and_real_pullback_required(self):
        for frame in self.frames.values():
            frame["candle_history"][-1]["open"] = 101.2
        self.assertIn("confirmation", self.run_plan()["reason"])

    def test_repeated_level_copies_do_not_increase_score(self):
        one = self.run_plan()
        for tf in ("M15", "M30", "H4"):
            self.frames[tf]["levels"] = {}
        self.assertEqual(self.run_plan()["score"], one["score"])

    def test_true_range_includes_gaps(self):
        self.assertEqual(true_ranges([{"close": 100}, {"high": 105, "low": 104}]), [5])

    def test_overtrading_limits_and_restart_attempts(self):
        plan = self.run_plan()
        self.assertEqual(overtrade_reason(plan, [], [], NOW, self.cfg), "")
        self.assertIn("Duplicate", overtrade_reason(plan, [], [plan], NOW, self.cfg))
        offer = {**plan, "setup_id": "earlier", "expires_at": NOW - 1}
        self.assertIn("attempts", overtrade_reason(plan, [], [offer], NOW, self.cfg))
        trades = [{"opened_at": NOW - 20000 + i * 100, "closed_at": NOW - 19000 + i * 100,
                   "closed": True, "net_pnl": -1, "actual_r": -1, "session": "Asian"} for i in range(3)]
        self.assertIn("Consecutive", overtrade_reason(plan, trades, [], NOW, self.cfg))
        for trade in trades:
            trade["session"] = "London/NY"
        self.assertIn("session", overtrade_reason(plan, trades, [], NOW, self.cfg))
        trades = [{**trades[-1], "closed_at": NOW - 2}]
        self.assertIn("Cooldown", overtrade_reason(plan, trades, [], NOW, self.cfg))
        trades[0]["closed"] = False
        self.assertIn("active thesis", overtrade_reason(plan, trades, [], NOW, self.cfg))

    def test_journal_partial_fills_costs_dedup_and_account_isolation(self):
        with tempfile.TemporaryDirectory() as directory:
            store = AccountStore(Path(directory) / "test.db")
            journal = StrategyJournal(store)
            plan = self.run_plan()
            self.assertTrue(journal.reserve(plan, "demo:1"))
            base = {"setup_id": plan["setup_id"], "broker_server": "demo", "account_login": 1,
                    "position_ticket": "10", "initial_risk": 2, "risk_cash": 100, "mfe_r": 2.5, "mae_r": .3}
            deals = [dict(base, deal_ticket="1", transaction_type="POSITION_OPENED", volume=1, commission=-2),
                     dict(base, deal_ticket="2", transaction_type="PARTIAL_CLOSE", volume=.5, profit=100, commission=-1),
                     dict(base, deal_ticket="3", transaction_type="TAKE_PROFIT_HIT", volume=.5, profit=150, commission=-1, swap=-1)]
            journal.record(deals[0], NOW)
            journal.record(deals[1], NOW + 10)
            self.assertIsNone(journal.trades()[0]["actual_r"])
            journal.record(deals[2], NOW + 20)
            journal.record(deals[2], NOW + 20)
            trade = StrategyJournal(AccountStore(store.path)).trades()[0]
            self.assertAlmostEqual(trade["actual_r"], 2.45)
            self.assertEqual(trade["net_pnl"], 245)
            self.assertEqual(trade["mfe_r"], 2.5)
            self.assertEqual(journal.trades(account="demo:2"), [])
            self.assertIn("Expectancy", performance_report([trade], "GOLD"))

    def test_expectancy_drawdown_and_breakevens(self):
        result = metrics([{"actual_r": r, "closed_at": i} for i, r in enumerate((2, -1, 0, -1, -1))])
        self.assertAlmostEqual(result["expectancy"], -.2)
        self.assertEqual(result["max_drawdown_r"], 3)
        self.assertEqual(result["losing_streak"], 2)
        self.assertEqual(result["wins"], 1)

    def test_execution_endpoint_offer_is_durable_without_placing_trades(self):
        market_state = SimpleNamespace(lock=threading.RLock(), data={"symbols": {"GOLD": self.frames}, "market_structure": {"GOLD": self.structure}})
        query = {k: [str(v)] for k, v in dict(self.quote, account="1", broker_server="demo", quote_time=NOW).items()}
        with tempfile.TemporaryDirectory() as directory, patch("webhook.strategy_runtime.time.time", return_value=NOW), patch("webhook.config.telegram_configured", return_value=False):
            store = AccountStore(Path(directory) / "test.db")
            first = execution_config("Gold", market_state, query, store)
            self.assertEqual(first["strategy_direction"], "BUY", first)
            second = execution_config("Gold", market_state, query, store)
            self.assertEqual(second["strategy_direction"], "WAIT")
            self.assertEqual(len(StrategyJournal(store).plans("demo:1", "GOLD")), 1)

    def test_dst_sessions_have_explicit_overlap(self):
        self.assertEqual(session_name(NOW), "London/NY")
        self.assertEqual(session_name(datetime(2026, 1, 5, 14, tzinfo=timezone.utc).timestamp()), "London/NY")

    def test_empty_quote_and_late_entry_do_not_fall_back_to_old_price(self):
        self.quote = {}
        self.assertIn("quote", self.run_plan()["reason"])
        self.frames, self.structure, self.quote = market()
        self.quote.update(bid=101.98, ask=102)
        self.assertIn("moved away", self.run_plan()["reason"])

    def test_history_order_missing_history_and_opposing_zone(self):
        for frame in self.frames.values():
            frame["candle_history"][10], frame["candle_history"][11] = frame["candle_history"][11], frame["candle_history"][10]
        self.assertIn("Incomplete", self.run_plan()["reason"])
        self.frames, self.structure, self.quote = market()
        self.frames["H1"]["levels"]["bearish_fvg"] = {"low": 100.9, "high": 102}
        self.assertIn("opposing FVG", self.run_plan()["reason"])

    def test_missing_monetary_risk_is_never_invented(self):
        with tempfile.TemporaryDirectory() as directory:
            journal = StrategyJournal(AccountStore(Path(directory) / "test.db"))
            p = self.run_plan()
            journal.reserve(p, "demo:1")
            base = {"setup_id": p["setup_id"], "account_login": 1, "position_ticket": "1", "volume": 1}
            journal.record(dict(base, deal_ticket="1", transaction_type="POSITION_OPENED"), NOW)
            journal.record(dict(base, deal_ticket="2", transaction_type="POSITION_CLOSED", profit=100), NOW + 1)
            self.assertTrue(journal.trades()[0]["closed"])
            self.assertIsNone(journal.trades()[0]["actual_r"])

    def test_config_override_validation(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "settings.json"
            with patch.dict("os.environ", {"STRATEGY_CONFIG_FILE": str(path)}):
                path.write_text(json.dumps({"weights": {"h4": 20}}))
                self.assertEqual(settings()["weights"]["h4"], 20)
                for bad in ({"min_rr": -1}, {"partial_fraction": 1}, {"entry_timeframes": ["M1"]}, {"unknown_setting": 5}, {"protect_lock_r": 5}):
                    path.write_text(json.dumps(bad))
                    with self.assertRaises(ValueError):
                        settings()

    def test_new_manual_fill_is_journaled_without_fabricated_r(self):
        with tempfile.TemporaryDirectory() as directory, patch("webhook.strategy_runtime.time.time", return_value=NOW):
            store = AccountStore(Path(directory) / "test.db")
            event = {"account_login": 1, "broker_server": "demo", "position_ticket": "1", "symbol": "Gold", "direction": "DEAL_TYPE_BUY", "volume": 1, "event_time": NOW}
            journal_transaction(dict(event, deal_ticket="10", transaction_type="POSITION_OPENED"), store)
            journal_transaction(dict(event, deal_ticket="11", transaction_type="MANUAL_CLOSE", profit=10), store)
            trade = StrategyJournal(store).trades("GOLD")[0]
            self.assertEqual(trade["setup_type"], "legacy_manual")
            self.assertTrue(trade["closed"])
            self.assertIsNone(trade["actual_r"])

    def test_strategy_alert_does_not_block_execution_response(self):
        market_state = SimpleNamespace(lock=threading.RLock(), data={"symbols": {"GOLD": self.frames}, "market_structure": {"GOLD": self.structure}})
        query = {k: [str(v)] for k, v in dict(self.quote, account="1", broker_server="demo", quote_time=NOW).items()}
        with tempfile.TemporaryDirectory() as directory, patch("webhook.strategy_runtime.time.time", return_value=NOW), patch("webhook.config.telegram_configured", return_value=True), patch("webhook.state.ALERTS_PAUSED", False), patch("webhook.strategy_runtime.threading.Thread") as thread:
            result = execution_config("Gold", market_state, query, AccountStore(Path(directory) / "test.db"))
            self.assertEqual(result["strategy_direction"], "BUY")
            thread.return_value.start.assert_called_once()

    def test_actual_mql_management_arithmetic(self):
        # MQL's numeric functions use C++ syntax. Compile the verbatim production
        # functions with math aliases, rather than testing a Python reimplementation.
        prefix = []
        if not shutil.which("g++"):
            if sys.platform != "win32" or not shutil.which("wsl"):
                self.skipTest("g++ or WSL g++ needed for cross-language arithmetic check")
            prefix = ["wsl", "--exec"]
        source = (Path(__file__).resolve().parents[1] / "mq5/includes/TradeManager.mqh").read_text()
        arithmetic = source[source.index("double StrategyLockR("):source.index("void SendStrategyTransaction(")]
        cpp = "#include <cmath>\n#define MathMax std::fmax\n#define MathAbs std::fabs\n#define MathFloor std::floor\n" + arithmetic + "\nint main(){return StrategyManagementChecks() ? 0 : 1;}\n"
        driver = """import pathlib, subprocess, sys, tempfile
with tempfile.TemporaryDirectory() as d:
    executable = str(pathlib.Path(d) / 'strategy-check')
    subprocess.run(['g++', '-x', 'c++', '-std=c++11', '-', '-o', executable], input=sys.stdin.read(), text=True, check=True)
    subprocess.run([executable], check=True)
"""
        result = subprocess.run(prefix + (["python3"] if prefix else [sys.executable]) + ["-c", driver], input=cpp, text=True, capture_output=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
