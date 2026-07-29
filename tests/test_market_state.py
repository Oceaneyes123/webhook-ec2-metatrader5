"""Tests for market_state — snapshot ingestion, pattern notifications, candle history."""
from __future__ import annotations

import importlib
import tempfile
import unittest
from pathlib import Path

from webhook import market_analyzer, market_state
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

    def test_key_level_notifications_ignore_m5_and_m15(self):
        levels = {"support": 2280.0, "resistance": None, "fib": None, "bullish_fvg": None, "bearish_fvg": None}
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            for timeframe in ("M5", "M15"):
                notifications = state.update(
                    snapshot(timeframe, "2026.06.28 10:00:00", open=2285.0, high=2287.0, low=2275.0, close=2282.0, levels=levels)
                )
                self.assertEqual(notifications, [])

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
