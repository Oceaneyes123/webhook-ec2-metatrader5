"""Tests for market_state — snapshot ingestion, pattern notifications, candle history."""
from __future__ import annotations

import importlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from webhook import market_analyzer, market_state
from webhook.market_structure import classify_level, confirm_structure, level_id
from tests.test_helpers import snapshot


class MarketStateModuleTest(unittest.TestCase):
    """MarketState module availability."""

    def test_market_state_module_is_available(self):
        self.assertIsNotNone(importlib.util.find_spec("webhook.market_state"))


class MarketStateSnapshotTest(unittest.TestCase):
    """Snapshot ingestion and data persistence."""

    def test_market_state_persists_ema_snapshot_and_neutral_equality(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            state = market_state.MarketState(path)
            self.assertEqual(
                state.update(
                    snapshot("M1", "2026.06.28 10:01:00", ema20=2306.0, ema50=2305.0)
                ),
                [],
            )
            state.update(
                snapshot("M5", "2026.06.28 10:05:00", ema20=2305.0, ema50=2305.0)
            )
            report = market_analyzer.MarketAnalyzer(
                market_state.MarketState(path)
            ).summary("Gold")
        self.assertIn("<b>M1</b>", report)
        self.assertIn("Bullish", report)
        self.assertIn("<b>M5</b>", report)
        self.assertIn("Neutral", report)

    def test_market_state_uses_supplied_candle_history(self):
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            payload = snapshot(
                "M1",
                "2026.06.28 10:01:00",
                ema20=2306.0,
                ema50=2305.0,
            )
            payload["candle_history"] = [
                {
                    "candle_time": "2026.06.28 10:00:00",
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
            history = state.data["symbols"]["GOLD"]["M1"].get("candle_history", [])
            self.assertEqual(
                [candle["candle_time"] for candle in history],
                ["2026.06.28 10:00:00", "2026.06.28 10:01:00"],
            )

    def test_market_state_accumulates_history_without_candles(self):
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            for minute in (0, 1):
                state.update(
                    snapshot(
                        "M1",
                        f"2026.06.28 10:{minute:02d}:00",
                        ema20=2306.0,
                        ema50=2305.0,
                    )
                )
            history = state.data["symbols"]["GOLD"]["M1"].get("candle_history", [])
        self.assertEqual(
            [candle["candle_time"] for candle in history],
            ["2026.06.28 10:00:00", "2026.06.28 10:01:00"],
        )

    def test_market_state_accepts_optional_webhook1_source(self):
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            without_source = snapshot(
                "M15", "2026.06.28 10:00:00", retained_patterns=[]
            )
            with_source = snapshot(
                "M15",
                "2026.06.28 10:15:00",
                source="webhook1",
                retained_patterns=[],
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
                    snapshot(
                        "M5",
                        f"2026.06.28 10:{index:02d}:00",
                        ema20=2306.0,
                        ema50=2305.0,
                        rsi14=71.0 if index == 0 else 55.0,
                    )
                )
            state.update(
                snapshot(
                    "M15",
                    "2026.06.28 10:15:00",
                    retained_patterns=[],
                    rsi14=29.0,
                )
            )
            state.update(
                snapshot(
                    "H1",
                    "2026.06.28 23:30:00",
                    retained_patterns=[],
                    rsi14=72.5,
                )
            )
            report = market_analyzer.MarketAnalyzer(state).rsi_summary("Gold")
        self.assertIn("<b>GOLD RSI(14)</b>", report)
        self.assertIn("<b>M5</b>: <code>55.00</code> — Neutral", report)
        self.assertNotIn("10:00:00", report)
        self.assertIn("<b>M15</b>: <code>29.00</code> — Oversold", report)
        self.assertIn("Closed below 30", report)
        self.assertIn("2026.06.28 03:15 PM", report)
        self.assertIn("<b>H1</b>: <code>72.50</code> — Overbought", report)
        self.assertIn("Closed above 70", report)
        self.assertIn("2026.06.29 04:30 AM", report)
        self.assertNotIn("23:30:00", report)

    def test_strong_rsi_notification_uses_timeframe_cooldown(self):
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            payload = snapshot("M5", "2026.06.28 10:00:00", rsi14=71.0)

            notifications = state.update(payload)
            self.assertEqual(notifications[0]["event_type"], "STRONG_RSI")
            state.mark_notified(notifications[0])

            self.assertEqual(state.update({**payload, "candle_time": "2026.06.28 10:05:00"}), [])
            state.data["symbols"]["GOLD"]["M5"]["rsi_notified_at"] -= 25 * 60
            self.assertEqual(
                state.update({**payload, "candle_time": "2026.06.28 10:10:00"})[0]["event_type"],
                "STRONG_RSI",
            )

    def test_key_level_notification_prefers_higher_timeframe_and_rearms_after_exit(self):
        levels = {
            "support": 2280.0,
            "resistance": 2340.0,
            "fib": None,
            "bullish_fvg": None,
            "bearish_fvg": None,
        }
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            state.update(
                snapshot(
                    "H1",
                    "2026.06.28 10:15:00",
                    open=2300.0,
                    close=2305.0,
                    low=2290.0,
                    high=2310.0,
                    levels=levels,
                )
            )
            notifications = state.update(
                snapshot(
                    "M30",
                    "2026.06.28 10:20:00",
                    open=2285.0,
                    close=2282.0,
                    low=2275.0,
                    high=2285.0,
                    levels=levels,
                )
            )

            self.assertEqual(len(notifications), 1)
            self.assertEqual(notifications[0]["event_type"], "KEY_LEVEL_REJECTION_UP")
            self.assertEqual(notifications[0]["timeframe"], "M30")
            self.assertEqual(notifications[0]["source_timeframe"], "H1")
            state.mark_notified(notifications[0])
            self.assertEqual(
                state.update(
                    snapshot(
                        "M30",
                        "2026.06.28 10:25:00",
                        open=2285.0,
                        close=2282.0,
                        low=2275.0,
                        high=2285.0,
                        levels=levels,
                    )
                ),
                [],
            )
            state.update(snapshot("M30", "2026.06.28 10:30:00", low=2290.0, high=2300.0, levels=levels))
            state.data["key_level_alerts"]["GOLD"][notifications[0]["key_level_key"]]["events"]["KEY_LEVEL_REJECTION_UP"] -= 6 * 60 * 60
            notifications = state.update(
                snapshot("M30", "2026.06.28 10:35:00", open=2290.0, high=2291.0, low=2270.0, close=2284.0, levels=levels)
            )
            self.assertEqual(notifications[0]["event_type"], "KEY_LEVEL_REJECTION_UP")

    def test_key_level_break_notifies_separately_after_rejection(self):
        levels = {"support": 2280.0, "resistance": None, "fib": None, "bullish_fvg": None, "bearish_fvg": None}
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            rejection = state.update(snapshot("M30", "2026.06.28 10:00:00", open=2285.0, high=2287.0, low=2278.0, close=2282.0, levels=levels))[0]
            state.mark_notified(rejection)
            state.update(snapshot("M30", "2026.06.28 10:05:00", low=2290.0, high=2300.0, levels=levels))
            broke = state.update(snapshot("M30", "2026.06.28 10:10:00", open=2285.0, high=2286.0, low=2275.0, close=2278.0, levels=levels))
        self.assertEqual(broke[0]["event_type"], "KEY_LEVEL_BREAK_DOWN")

    def test_opposite_key_level_break_is_not_choch(self):
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            down = state.update(snapshot("M30", "2026.06.28 10:00:00", open=2285.0, high=2286.0, low=2275.0, close=2278.0, levels={"support": 2280.0, "resistance": None, "fib": None, "bullish_fvg": None, "bearish_fvg": None}))[0]
            state.mark_notified(down)
            up = state.update(snapshot("M30", "2026.06.28 10:30:00", open=2295.0, high=2310.0, low=2294.0, close=2305.0, levels={"support": None, "resistance": 2300.0, "fib": None, "bullish_fvg": None, "bearish_fvg": None}))[0]
        self.assertEqual(down["event_type"], "KEY_LEVEL_BREAK_DOWN")
        self.assertEqual(up["event_type"], "KEY_LEVEL_BREAK_UP")

    def test_fibonacci_break_is_never_bos_or_choch(self):
        levels = {"support": None, "resistance": None, "fib": {"61.8": 2300.0}, "bullish_fvg": None, "bearish_fvg": None}
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            state.update(snapshot("M30", "2026.06.28 10:00:00", open=2290, high=2295, low=2288, close=2292, levels=levels))
            result = state.update(snapshot("M30", "2026.06.28 10:30:00", open=2292, high=2312, low=2290, close=2310, levels=levels))
        self.assertEqual([item["event_type"] for item in result], ["KEY_LEVEL_BREAK_UP"])

    def test_level_identity_includes_source_and_type(self):
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            state.update(snapshot("H1", "2026.06.28 10:00:00", levels={"support": 2280.0, "resistance": None, "fib": None, "bullish_fvg": None, "bearish_fvg": None}))
            state.update(snapshot("M30", "2026.06.28 10:30:00", open=2285, high=2287, low=2270, close=2282, levels={"support": None, "resistance": None, "fib": {"61.8": 2280.0}, "bullish_fvg": None, "bearish_fvg": None}))
        keys = state.data["key_level_alerts"]["GOLD"]
        self.assertTrue(any("H1|Support" in key for key in keys))
        self.assertTrue(any("M30|Fib 61.8" in key for key in keys))

    def test_key_level_state_advances_only_after_delivery_for_all_coincident_levels(self):
        levels = {"support": 2280.0, "resistance": None, "fib": {"61.8": 2280.0}, "bullish_fvg": None, "bearish_fvg": None}
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            notification = state.update(snapshot("M30", "1", open=2285, high=2286, low=2275, close=2278, levels=levels))[0]
            keys = [notification["key_level_key"], *notification["coincident_keys"]]
            self.assertTrue(all("last_candle" not in state.data["key_level_alerts"]["GOLD"][key] for key in keys))
            self.assertEqual(state.update(snapshot("M30", "1", open=2285, high=2286, low=2275, close=2278, levels=levels)), [notification])
            state.mark_notified(notification)
            self.assertTrue(all(state.data["key_level_alerts"]["GOLD"][key]["lifecycle"] == "broken_down" for key in keys))
            self.assertTrue(all(state.data["key_level_alerts"]["GOLD"][key]["last_candle"] == "1" for key in keys))

    def test_retest_keeps_broken_lifecycle_for_later_reclaim(self):
        levels = {"support": 2280.0, "resistance": None, "fib": None, "bullish_fvg": None, "bearish_fvg": None}
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            broke = state.update(snapshot("M30", "1", open=2285, high=2286, low=2275, close=2278, levels=levels))[0]
            state.mark_notified(broke)
            state.update(snapshot("M30", "2", open=2265, high=2270, low=2255, close=2260, levels=levels))
            retest = state.update(snapshot("M30", "3", open=2275, high=2282, low=2270, close=2276, levels=levels))[0]
            state.mark_notified(retest)
            self.assertEqual(state.data["key_level_alerts"]["GOLD"][retest["key_level_key"]]["lifecycle"], "broken_down")
            state.update(snapshot("M30", "4", open=2270, high=2275, low=2265, close=2270, levels=levels))
            reclaimed = state.update(snapshot("M30", "5", open=2275, high=2295, low=2274, close=2290, levels=levels))[0]
        self.assertEqual(reclaimed["event_type"], "KEY_LEVEL_RECLAIM_UP")

    def test_key_level_notifications_ignore_m5_and_m15(self):
        levels = {"support": 2280.0, "resistance": None, "fib": None, "bullish_fvg": None, "bearish_fvg": None}
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            for timeframe in ("M5", "M15"):
                notifications = state.update(
                    snapshot(timeframe, "2026.06.28 10:00:00", open=2285.0, high=2287.0, low=2275.0, close=2282.0, levels=levels)
                )
                self.assertEqual(notifications, [])

    def test_unfinished_snapshot_is_not_stored_or_analyzed(self):
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            payload = snapshot("M30", "1", closed=False)
            self.assertEqual(state.update(payload), [])
            self.assertNotIn("GOLD", state.data["symbols"])

    def test_resistance_sweep_is_not_a_key_level_break(self):
        levels = {"support": None, "resistance": 2300.0, "fib": None, "bullish_fvg": None, "bearish_fvg": None}
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            result = state.update(snapshot("M30", "1", open=2280, high=2310, low=2275, close=2295, levels=levels))
        self.assertEqual(result[0]["event_type"], "KEY_LEVEL_SWEEP_DOWN")

    def test_structure_notification_includes_confirmed_swing_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            state.data["market_structure"] = {"GOLD": {"M30": {
                "trend": "bullish",
                "swings": [
                    {"id": "h", "type": "high", "price": 2300, "time": "h-time", "broken": False},
                    {"id": "l", "type": "low", "price": 2280, "time": "l-time", "broken": False},
                ],
                "broken": [], "protected_low": {"id": "l", "price": 2280},
            }}}
            history = [
                {"candle_time": str(index), "open": 2290, "high": 2300, "low": 2280, "close": 2295}
                for index in range(6)
            ]
            history.append({"candle_time": "2", "open": 2299, "high": 2310, "low": 2298, "close": 2308})
            result = state.update(snapshot("M30", "2", open=2299, high=2310, low=2298, close=2308, candle_history=history))
        self.assertEqual(result[0]["event_type"], "KEY_LEVEL_BOS_UP")
        self.assertEqual(result[0]["broken_swing_time"], "h-time")
        self.assertEqual(result[0]["protected_level"], 2280)
        self.assertGreater(result[0]["atr_displacement"], 0)

    def test_structure_choch_checks_non_latest_protected_swings_and_deduplicates(self):
        cases = [
            ("bullish", "DOWN", "protected-low", 2280, 2270, 2290, 2275, 2276),
            ("bearish", "UP", "protected-high", 2320, 2330, 2250, 2310, 2325),
        ]
        for trend, direction, protected_id, protected_price, newer_price, continuation_price, low, close in cases:
            with self.subTest(trend=trend):
                if trend == "bullish":
                    swings = [
                        {"id": "continuation", "type": "high", "price": continuation_price, "time": "h-time"},
                        {"id": protected_id, "type": "low", "price": protected_price, "time": "p-time"},
                        {"id": "newer", "type": "low", "price": newer_price, "time": "n-time"},
                    ]
                    protected = {"id": protected_id, "type": "low", "price": protected_price, "time": "p-time"}
                    candle = {"candle_time": "break-time", "open": 2285, "high": 2290, "low": low, "close": close}
                else:
                    swings = [
                        {"id": "continuation", "type": "low", "price": continuation_price, "time": "l-time"},
                        {"id": protected_id, "type": "high", "price": protected_price, "time": "p-time"},
                        {"id": "newer", "type": "high", "price": newer_price, "time": "n-time"},
                    ]
                    protected = {"id": protected_id, "type": "high", "price": protected_price, "time": "p-time"}
                    candle = {"candle_time": "break-time", "open": 2312, "high": 2330, "low": 2310, "close": close}
                state = {"trend": trend, "swings": swings, "broken": [], "protected_low": protected if trend == "bullish" else None, "protected_high": protected if trend == "bearish" else None}
                history = [dict(candle_time=str(index), open=2300, high=2310, low=2290, close=2300) for index in range(6)] + [candle]
                structure = {"GOLD": {"M30": state}}
                first = confirm_structure(structure, "GOLD", "M30", history)
                self.assertEqual([(event["type"], event["direction"], event["swing"]["id"]) for event in first], [("CHOCH", direction, protected_id)])
                self.assertEqual(first[0]["protected_level"], protected_price)
                self.assertEqual(confirm_structure(structure, "GOLD", "M30", history), [])

    def test_bearish_bos_reports_active_protected_high(self):
        state = {
            "trend": "bearish",
            "swings": [
                {"id": "protected-high", "type": "high", "price": 2320, "time": "h-time"},
                {"id": "continuation-low", "type": "low", "price": 2280, "time": "l-time"},
            ],
            "broken": [],
            "protected_high": {"id": "protected-high", "type": "high", "price": 2320, "time": "h-time"},
        }
        history = [dict(candle_time=str(index), open=2300, high=2310, low=2290, close=2300) for index in range(6)]
        history.append({"candle_time": "break-time", "open": 2275, "high": 2280, "low": 2260, "close": 2265})
        events = confirm_structure({"GOLD": {"M30": state}}, "GOLD", "M30", history)
        self.assertEqual([(event["type"], event["direction"]) for event in events], [("BOS", "DOWN")])
        self.assertEqual(events[0]["protected_level"], 2320)

    def test_level_classifier_table_rejects_weak_and_distinguishes_outcomes(self):
        cases = [
            ("bullish break", {"open": 2300, "high": 2312, "low": 2299, "close": 2310}, 2300, 2295, "Resistance", "KEY_LEVEL_BREAK_UP"),
            ("bearish break", {"open": 2300, "high": 2301, "low": 2288, "close": 2290}, 2305, 2310, "Support", "KEY_LEVEL_BREAK_DOWN"),
            ("weak doji", {"open": 2300, "high": 2302, "low": 2298, "close": 2300.1}, 2300, 2295, "Support", None),
            ("bullish rejection", {"open": 2308, "high": 2310, "low": 2290, "close": 2303}, 2300, 2308, "Support", "KEY_LEVEL_REJECTION_UP"),
            ("bullish sweep", {"open": 2302, "high": 2310, "low": 2290, "close": 2309}, 2300, 2305, "Support", "KEY_LEVEL_SWEEP_UP"),
            ("bearish sweep", {"open": 2302, "high": 2320, "low": 2290, "close": 2290}, 2300, 2295, "Resistance", "KEY_LEVEL_SWEEP_DOWN"),
        ]
        for name, candle, level, previous, kind, expected in cases:
            with self.subTest(name=name):
                self.assertEqual(classify_level(candle, previous, level, False, 10, {}, kind), expected)

    def test_retest_failure_is_distinct_from_later_reclaim(self):
        level = 2300.0
        failed = classify_level(
            {"open": 2290, "high": 2310, "low": 2288, "close": 2305},
            2290, level, False, 10, {"lifecycle": "broken_down", "awaiting_retest": True}, "Support"
        )
        held = classify_level(
            {"open": 2300, "high": 2302, "low": 2288, "close": 2290},
            2295, level, False, 10, {"lifecycle": "broken_down", "awaiting_retest": True}, "Support"
        )
        reclaimed = classify_level(
            {"open": 2290, "high": 2310, "low": 2288, "close": 2305},
            2290, level, False, 10, {"lifecycle": "broken_down", "retest_held": True}, "Support"
        )
        self.assertEqual(failed, "KEY_LEVEL_RETEST_FAILURE_UP")
        self.assertEqual(held, "KEY_LEVEL_RETEST_HOLD_DOWN")
        self.assertEqual(reclaimed, "KEY_LEVEL_RECLAIM_UP")

    def test_level_id_distinguishes_origin_and_reason(self):
        first = level_id("GOLD", "H1", "Support", 2300, False, "candle-1", "swing", "support")
        second = level_id("GOLD", "H1", "Support", 2300, False, "candle-2", "swing", "support")
        self.assertNotEqual(first, second)

    def test_level_objects_are_stable_across_small_drift_and_reload(self):
        levels = {"support": 2280.0, "resistance": None, "fib": None, "bullish_fvg": None, "bearish_fvg": None}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            state = market_state.MarketState(path)
            state.update(snapshot("M30", "1", open=2300, high=2305, low=2295, close=2302, levels=levels))
            first = next(iter(state.data["level_objects"]["GOLD"]))
            state.update(snapshot("M30", "2", open=2300, high=2305, low=2296, close=2302, levels={**levels, "support": 2281.0}))
            self.assertEqual(list(state.data["level_objects"]["GOLD"]), [first])
            reloaded = market_state.MarketState(path)
            reloaded.update(snapshot("M30", "3", open=2300, high=2305, low=2296, close=2302, levels={**levels, "support": 2281.5}))
            self.assertEqual(list(reloaded.data["level_objects"]["GOLD"]), [first])

    def test_same_explicit_origin_keeps_identity_when_price_revises_far(self):
        base = {"resistance": None, "fib": None, "bullish_fvg": None, "bearish_fvg": None}
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            first_levels = {**base, "support": {"price": 2280.0, "origin_time": "pivot-1"}}
            second_levels = {**base, "support": {"price": 2400.0, "origin_time": "pivot-1"}}
            state.update(snapshot("M30", "1", levels=first_levels))
            first = next(iter(state.data["level_objects"]["GOLD"]))
            state.update(snapshot("M30", "2", levels=second_levels))
            self.assertEqual(list(state.data["level_objects"]["GOLD"]), [first])
            self.assertEqual(state.data["level_objects"]["GOLD"][first]["value"], 2400.0)

    def test_same_origin_but_different_reason_or_direction_separates_levels(self):
        base = {"resistance": None, "fib": None, "bullish_fvg": None, "bearish_fvg": None}
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            state.update(snapshot("M30", "1", levels={**base, "support": {"price": 2280, "origin_time": "pivot", "reason": "swing", "direction": "support"}}))
            state.update(snapshot("M30", "2", levels={**base, "support": {"price": 2400, "origin_time": "pivot", "reason": "liquidity", "direction": "resistance"}}))
            self.assertEqual(len(state.data["level_objects"]["GOLD"]), 2)

    def test_nearby_levels_group_with_highest_timeframe_primary(self):
        levels = {"support": 2280.0, "resistance": None, "fib": None, "bullish_fvg": None, "bearish_fvg": None}
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            state.update(snapshot("H1", "1", open=2300, high=2305, low=2295, close=2302, levels=levels))
            result = state.update(snapshot("M30", "2", open=2293, high=2295, low=2270, close=2286, levels={**levels, "support": 2282.0}))
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["source_timeframe"], "H1")
        self.assertTrue(result[0]["coincident_keys"])

    def test_grouped_h4_h1_level_uses_h4_cooldown(self):
        levels = {"support": 2280.0, "resistance": None, "fib": None, "bullish_fvg": None, "bearish_fvg": None}
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            state.update(snapshot("H4", "1", open=2300, high=2305, low=2295, close=2302, levels=levels))
            result = state.update(snapshot("H1", "2", open=2293, high=2295, low=2270, close=2286, levels={**levels, "support": 2282.0}))
            self.assertEqual(result[0]["cooldown_source_timeframe"], "H4")
            with patch("webhook.market_state.time.time", return_value=1000):
                state.mark_notified(result[0])
            for key in [result[0]["key_level_key"], *result[0]["coincident_keys"]]:
                self.assertEqual(state.data["key_level_alerts"]["GOLD"][key]["cooldown_until"], 1000 + 4 * 60 * 60 * 5)

    def test_group_cooldown_uses_h4_when_h1_is_already_expired(self):
        levels = {"support": 2280.0, "resistance": None, "fib": None, "bullish_fvg": None, "bearish_fvg": None}
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            state.update(snapshot("H4", "1", open=2300, high=2305, low=2295, close=2302, levels=levels))
            with patch("webhook.market_state.time.time", return_value=1000):
                first = state.update(snapshot("H1", "2", open=2293, high=2295, low=2270, close=2286, levels={**levels, "support": 2282.0}))[0]
                state.mark_notified(first)
            state.update(snapshot("H1", "3", open=2300, high=2310, low=2290, close=2305, levels={**levels, "support": 2282.0}))
            for key in [first["key_level_key"], *first["coincident_keys"]]:
                entry = state.data["key_level_alerts"]["GOLD"][key]
                if entry["source_timeframe"] == "H1":
                    entry["events"][first["event_type"]] = 1000 - state._level_cooldown_seconds("H1") - 1
            h1_expiry = 1000 + state._level_cooldown_seconds("H1") + 1
            with patch("webhook.market_state.time.time", return_value=h1_expiry):
                self.assertEqual(state.update(snapshot("H1", "4", open=2293, high=2295, low=2270, close=2286, levels={**levels, "support": 2282.0})), [])
            with patch("webhook.market_state.time.time", return_value=1000 + state._level_cooldown_seconds("H4") + 1):
                self.assertTrue(state.update(snapshot("H1", "5", open=2293, high=2295, low=2270, close=2286, levels={**levels, "support": 2282.0})) )

    def test_direct_retest_hold_and_failure_are_one_shot_then_reclaim(self):
        levels = {"support": 2280.0, "resistance": None, "fib": None, "bullish_fvg": None, "bearish_fvg": None}
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            broke = state.update(snapshot("M30", "1", open=2285, high=2286, low=2275, close=2278, levels=levels))[0]
            state.mark_notified(broke)
            hold = state.update(snapshot("M30", "2", open=2278, high=2282, low=2270, close=2276, levels=levels))[0]
            self.assertEqual(hold["event_type"], "KEY_LEVEL_RETEST_HOLD_DOWN")
            state.mark_notified(hold)
            self.assertEqual(state.update(snapshot("M30", "3", open=2278, high=2282, low=2270, close=2276, levels=levels)), [])
            state.update(snapshot("M30", "4", open=2270, high=2275, low=2265, close=2270, levels=levels))
            reclaimed = state.update(snapshot("M30", "5", open=2275, high=2295, low=2274, close=2290, levels=levels))[0]
            self.assertEqual(reclaimed["event_type"], "KEY_LEVEL_RECLAIM_UP")
            failed_state = market_state.MarketState(Path(directory) / "failed.json")
            broke = failed_state.update(snapshot("M30", "1", open=2285, high=2286, low=2275, close=2278, levels=levels))[0]
            failed_state.mark_notified(broke)
            failure = failed_state.update(snapshot("M30", "2", open=2278, high=2290, low=2275, close=2285, levels=levels))[0]
            self.assertEqual(failure["event_type"], "KEY_LEVEL_RETEST_FAILURE_UP")

    def test_touch_updates_state_without_telegram_event_and_decays_strength(self):
        levels = {"support": 2300.0, "resistance": None, "fib": None, "bullish_fvg": None, "bearish_fvg": None}
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            state.update(snapshot("M30", "1", open=2305, high=2307, low=2300, close=2305, levels=levels))
            key = next(iter(state.data["key_level_alerts"]["GOLD"]))
            item = state.data["key_level_alerts"]["GOLD"][key]
        self.assertEqual(item["lifecycle"], "touched")
        self.assertEqual(item["touch_count"], 1)
        self.assertLess(item["strength"], 1.0)

    def test_structure_protected_pointer_and_post_choch_sequence_survive_reload(self):
        swings = [
            {"id": "h1", "type": "high", "price": 110, "time": "h1"},
            {"id": "l1", "type": "low", "price": 100, "time": "l1"},
            {"id": "h2", "type": "high", "price": 120, "time": "h2"},
            {"id": "l2", "type": "low", "price": 105, "time": "l2"},
        ]
        structure = {"GOLD": {"M30": {"trend": "bullish", "swings": swings, "broken": [], "protected_low": {"id": "l2", "price": 105}}}}
        candles = [{"candle_time": str(i), "open": 110, "high": 112, "low": 108, "close": 110} for i in range(6)]
        confirm_structure(structure, "GOLD", "M30", candles)
        self.assertIs(structure["GOLD"]["M30"]["protected_low"], structure["GOLD"]["M30"]["swings"][3])
        self.assertTrue(structure["GOLD"]["M30"]["swings"][3]["protected"])
        self.assertFalse(structure["GOLD"]["M30"]["swings"][1]["protected"])
        self.assertEqual(structure["GOLD"]["M30"]["last_confirmed_swing_low"]["id"], "l2")
        state = structure["GOLD"]["M30"]
        state["trend"] = "ranging"
        state["establishment_state"] = "awaiting_new_sequence"
        state["ranging_swing_ids"] = [item["id"] for item in swings]
        state["swings"].append({"id": "h3", "type": "high", "price": 125, "time": "h3"})
        candles[-1] = {"candle_time": "7", "open": 124, "high": 130, "low": 123, "close": 129}
        self.assertEqual(confirm_structure(structure, "GOLD", "M30", candles), [])

    def test_structure_delivery_is_not_recorded_as_key_level_lifecycle(self):
        notification = {"structure_event": True, "event_id": "GOLD:M30:BOS:h", "symbol": "GOLD", "timeframe": "M30"}
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            state.mark_notified(notification)
            self.assertNotIn("GOLD", state.data["key_level_alerts"])
            self.assertIn(notification["event_id"], state.data["market_structure"]["GOLD"]["M30"]["notified_event_ids"])

    def test_sparse_old_state_loads_and_level_object_retention_is_bounded(self):
        levels = {"support": 2200.0, "resistance": None, "fib": None, "bullish_fvg": None, "bearish_fvg": None}
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            path.write_text(json.dumps({"symbols": {}, "key_level_alerts": {"GOLD": {}}, "market_structure": {"GOLD": {"M30": "UP"}}}))
            state = market_state.MarketState(path)
            old_limit = market_state.LEVEL_RETENTION
            market_state.LEVEL_RETENTION = 2
            try:
                for index, price in enumerate((2200.0, 2300.0, 2400.0)):
                    state.update(snapshot("M30", str(index), open=2500, high=2510, low=2490, close=2505, levels={**levels, "support": price}))
                self.assertLessEqual(len(state.data["level_objects"]["GOLD"]), 2)
                self.assertLessEqual(len(state.data["key_level_alerts"]["GOLD"]), 2)
            finally:
                market_state.LEVEL_RETENTION = old_limit

    def test_present_level_does_not_expire_but_absent_level_is_retired(self):
        levels = {"support": 2280.0, "resistance": None, "fib": None, "bullish_fvg": None, "bearish_fvg": None}
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            old_limit, old_stale = market_state.LEVEL_RETENTION, market_state.LEVEL_STALE_UPDATES
            market_state.LEVEL_RETENTION, market_state.LEVEL_STALE_UPDATES = 2, 2
            try:
                for index in range(5):
                    state.update(snapshot("M30", str(index), levels=levels))
                key = next(iter(state.data["level_objects"]["GOLD"]))
                self.assertNotEqual(state.data["key_level_alerts"]["GOLD"][key]["lifecycle"], "expired")
                state._retain_level_objects("GOLD", set())
                state._retain_level_objects("GOLD", set())
                self.assertNotIn(key, state.data["level_objects"]["GOLD"])
                self.assertNotIn(key, state.data["key_level_alerts"]["GOLD"])
            finally:
                market_state.LEVEL_RETENTION, market_state.LEVEL_STALE_UPDATES = old_limit, old_stale

    def test_rearm_requires_source_timeframe_cooldown(self):
        levels = {"support": 2280.0, "resistance": None, "fib": None, "bullish_fvg": None, "bearish_fvg": None}
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            with patch("webhook.market_state.time.time", return_value=1000):
                first = state.update(snapshot("M30", "1", open=2285, high=2287, low=2278, close=2282, levels=levels))[0]
                state.mark_notified(first)
            state.update(snapshot("M30", "2", open=2300, high=2310, low=2290, close=2305, levels=levels))
            with patch("webhook.market_state.time.time", return_value=1001):
                self.assertEqual(state.update(snapshot("M30", "3", open=2285, high=2287, low=2278, close=2282, levels=levels)), [])
            with patch("webhook.market_state.time.time", return_value=1000 + 30 * 60 * 5 + 1):
                self.assertTrue(state.update(snapshot("M30", "4", open=2285, high=2287, low=2278, close=2282, levels=levels)))

    def test_market_state_rejects_snapshot_for_unknown_timeframe(self):
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            with self.assertRaisesRegex(ValueError, "timeframe"):
                state.update(snapshot("W1", "2026.06.28 10:00:00"))

    def test_divergence_alerts_regular_and_hidden_on_any_timeframe(self):
        def candles(lows, rsis):
            return [
                {"time": f"2026.06.28 10:{index:02d}:00", "open": low + 2, "high": low + 4, "low": low, "close": low + 2, "rsi14": rsi}
                for index, (low, rsi) in enumerate(zip(lows, rsis))
            ]

        levels = {"support": 6.5, "resistance": 20.0, "fib": None, "bullish_fvg": None, "bearish_fvg": None}
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            state.update(snapshot("H1", "2026.06.28 10:00:00", levels=levels))
            regular = state.update(snapshot("M1", "2026.06.28 10:08:00", candle_history=candles([10, 11, 8, 11, 12, 11, 7, 11, 12], [50, 48, 30, 45, 50, 45, 40, 48, 52])))
            state.mark_notified(regular[0])
            hidden = state.update(snapshot("H4", "2026.06.28 10:08:00", candle_history=candles([12, 13, 7, 13, 14, 13, 8, 13, 14], [50, 48, 45, 47, 50, 45, 35, 48, 52])))
        self.assertEqual(regular[0]["event_type"], "DIVERGENCE_REGULAR_BULLISH")
        self.assertEqual(regular[0]["nearest_key_level"]["timeframe"], "H1")
        self.assertEqual(hidden[0]["event_type"], "DIVERGENCE_HIDDEN_BULLISH")


class MarketStatePatternsTest(unittest.TestCase):
    """Pattern tracking, invalidation, and notification dedup."""

    def test_patterns_are_independent_across_timeframes(self):
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            state.update(
                snapshot(
                    "M15",
                    "2026.06.28 10:00:00",
                    retained_patterns=[{"event_type": "ENGULFING_CANDLE", "signal": "BUY"}],
                )
            )
            state.update(
                snapshot(
                    "H1",
                    "2026.06.28 11:00:00",
                    retained_patterns=[{"event_type": "SHOOTING_STAR_CANDLE", "signal": "SELL"}],
                )
            )
            report = market_analyzer.MarketAnalyzer(state).summary("Gold")
            self.assertIn("Engulfing Candle", report)
            self.assertNotIn("Engulfing Candle — Bullish (invalidated)", report)

            state.update(
                snapshot(
                    "M15",
                    "2026.06.28 12:00:00",
                    retained_patterns=[{"event_type": "HAMMER_CANDLE", "signal": "BUY"}],
                )
            )
            report = market_analyzer.MarketAnalyzer(state).summary("Gold")
        self.assertIn("Hammer Candle", report)
        self.assertNotIn("Hammer Candle — Bullish (invalidated)", report)

    def test_market_state_returns_each_pattern_notification_once(self):
        payload = snapshot(
            "M15",
            "2026.06.28 12:15:00",
            retained_patterns=[
                {"event_type": "ENGULFING_CANDLE", "signal": "BUY"},
                {"event_type": "MORNING_STAR", "signal": "BUY"},
            ],
        )
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            first = state.update(payload)
            for pattern in first:
                state.mark_notified(pattern)
            duplicate = state.update(payload)
        self.assertEqual(first, [])
        self.assertEqual(duplicate, [])

    def test_market_state_notifies_patterns_sent_by_the_ea(self):
        payload = snapshot(
            "M15",
            "2026.06.28 12:15:00",
            patterns=[{"event_type": "ENGULFING_CANDLE", "signal": "BUY"}],
        )
        with tempfile.TemporaryDirectory() as directory:
            notifications = market_state.MarketState(
                Path(directory) / "state.json"
            ).update(payload)
        self.assertEqual(notifications, [])

    def test_initial_snapshot_stores_patterns_without_notification(self):
        payload = snapshot(
            "H4",
            "2026.06.28 12:00:00",
            notify_patterns=False,
            retained_patterns=[{"event_type": "EVENING_STAR", "signal": "SELL"}],
        )
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            self.assertEqual(state.update(payload), [])
            report = market_analyzer.MarketAnalyzer(state).summary("Gold")
        self.assertIn("Evening Star", report)

    def test_initial_snapshot_stores_patterns_and_returns_notifications(self):
        payload = snapshot(
            "H4",
            "2026.06.28 12:00:00",
            notify_patterns=True,
            retained_patterns=[{"event_type": "EVENING_STAR", "signal": "SELL"}],
        )
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            notifications = state.update(payload)
        self.assertEqual(notifications, [])


if __name__ == "__main__":
    unittest.main()
