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

    def test_market_state_rejects_snapshot_for_unknown_timeframe(self):
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            with self.assertRaisesRegex(ValueError, "timeframe"):
                state.update(snapshot("D1", "2026.06.28 10:00:00"))


class MarketStatePatternsTest(unittest.TestCase):
    """Pattern tracking, invalidation, and notification dedup."""

    def test_higher_opposing_pattern_invalidates_older_lower_pattern(self):
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
            self.assertIn("(invalidated)", report)

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
        self.assertEqual(
            [pattern["event_type"] for pattern in first],
            ["ENGULFING_CANDLE", "MORNING_STAR"],
        )
        self.assertEqual(duplicate, [])

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
        self.assertEqual(len(notifications), 1)


if __name__ == "__main__":
    unittest.main()
