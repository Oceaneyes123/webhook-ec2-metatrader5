"""Tests for market_analyzer — summary, levels, RSI reports."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from webhook import market_analyzer, market_state
from tests.test_helpers import snapshot


class MarketAnalyzerSummaryTest(unittest.TestCase):
    """Summary confluence (buy / sell / wait)."""

    def test_summary_confluence_returns_buy_sell_or_wait(self):
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            state.update(
                snapshot("M1", "2026.06.28 12:01:00", ema20=2310.0, ema50=2300.0)
            )
            state.update(
                snapshot("M5", "2026.06.28 12:05:00", ema20=2310.0, ema50=2300.0)
            )
            state.update(
                snapshot(
                    "M15",
                    "2026.06.28 23:15:00",
                    retained_patterns=[{"event_type": "HAMMER_CANDLE", "signal": "BUY"}],
                )
            )
            buy_summary = market_analyzer.MarketAnalyzer(state).summary("Gold")
            self.assertIn("<b>Suggestion: BUY</b>", buy_summary)
            self.assertIn("2026.06.29 04:15 AM", buy_summary)
            self.assertNotIn("23:15:00", buy_summary)

            state.update(
                snapshot(
                    "H1",
                    "2026.06.29 00:00:00",
                    retained_patterns=[{"event_type": "EVENING_STAR", "signal": "SELL"}],
                )
            )
            self.assertIn(
                "<b>Suggestion: WAIT</b>",
                market_analyzer.MarketAnalyzer(state).summary("Gold"),
            )

            state.update(
                snapshot("M1", "2026.06.28 13:01:00", ema20=2290.0, ema50=2300.0)
            )
            state.update(
                snapshot("M5", "2026.06.28 13:05:00", ema20=2290.0, ema50=2300.0)
            )
            self.assertIn(
                "<b>Suggestion: SELL</b>",
                market_analyzer.MarketAnalyzer(state).summary("Gold"),
            )


class MarketAnalyzerLevelsTest(unittest.TestCase):
    """Levels report formatting."""

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
                snapshot(
                    "M15", "2026.06.28 12:15:00", retained_patterns=[], levels=levels
                )
            )
            report = market_analyzer.MarketAnalyzer(state).levels("Gold")

        self.assertIn("<b>M15</b>", report)
        self.assertIn("Support: <code>2280.00</code>", report)
        self.assertIn("Fib 38.2/50/61.8", report)
        self.assertIn("Bearish FVG: None found", report)
        self.assertIn("<b>M30</b>\nAwaiting data", report)
        self.assertIn(
            "PDH / PDL: <code>2350.00</code> / <code>2250.00</code>", report
        )


class MarketAnalyzerHtmlEscapeTest(unittest.TestCase):
    """HTML escaping in reports."""

    def test_summary_escapes_dynamic_symbol(self):
        with tempfile.TemporaryDirectory() as directory:
            state = market_state.MarketState(Path(directory) / "state.json")
            payload = snapshot(
                "M1", "2026.06.28 12:01:00", ema20=2310.0, ema50=2300.0
            )
            payload["symbol"] = "X<Y"
            state.update(payload)
            report = market_analyzer.MarketAnalyzer(state).summary("X<Y")
        self.assertIn("X&lt;Y", report)
        self.assertNotIn("X<Y", report)


if __name__ == "__main__":
    unittest.main()
