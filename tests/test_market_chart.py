"""Tests for market_chart — levels chart PNG generation."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from webhook import market_chart, market_analyzer, market_state
from tests.test_helpers import snapshot


class MarketChartLevelsTest(unittest.TestCase):
    """Levels chart image output."""

    def test_levels_chart_writes_png_with_key_levels(self):
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
            "bearish_fvg": {"low": 2345.0, "high": 2355.0},
            "previous_day_high": 2350.0,
            "previous_day_low": 2250.0,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "levels.png"
            state = market_state.MarketState(Path(directory) / "state.json")
            state.update(
                snapshot(
                    "M15",
                    "2026.06.28 13:15:00",
                    close=2305.0,
                    retained_patterns=[],
                    levels=levels,
                )
            )
            result = market_chart.MarketChart(state).levels_chart("Gold", path)

            self.assertEqual(result, path)
            self.assertTrue(path.exists())
            self.assertGreater(path.stat().st_size, 1000)
            self.assertEqual(path.read_bytes()[:8], b"\x89PNG\r\n\x1a\n")

    def test_levels_chart_draws_recent_candlesticks(self):
        levels = {
            "support": 2280.0,
            "resistance": 2340.0,
            "fib": None,
            "bullish_fvg": {"low": 2290.0, "high": 2320.0},
            "bearish_fvg": None,
            "previous_day_high": None,
            "previous_day_low": None,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "levels.png"
            state = market_state.MarketState(Path(directory) / "state.json")
            state.update(
                snapshot(
                    "M15",
                    "2026.06.28 13:15:00",
                    open=2300.0,
                    high=2310.0,
                    low=2290.0,
                    close=2306.0,
                    retained_patterns=[],
                    levels=levels,
                    candle_history=[
                        {"candle_time": "2026.06.28 13:15:00", "open": 2300.0, "high": 2310.0, "low": 2290.0, "close": 2306.0},
                        {"candle_time": "2026.06.28 13:30:00", "open": 2308.0, "high": 2320.0, "low": 2302.0, "close": 2301.0},
                    ],
                )
            )
            result = market_chart.MarketChart(state).levels_chart("Gold", path)

            self.assertEqual(result, path)
            candle_history = state.data["symbols"]["GOLD"]["M15"][
                "candle_history"
            ]
            self.assertEqual(
                [entry["candle_time"] for entry in candle_history],
                ["2026.06.28 13:15:00", "2026.06.28 13:30:00"],
            )
            with market_chart.Image.open(path) as image:
                pixels = image.load()
                candle_pixels = 0
                for x in range(90, 820):
                    for y in range(70, 690):
                        if pixels[x, y] in (
                            (20, 184, 166),
                            (248, 113, 113),
                        ):
                            candle_pixels += 1
                self.assertGreater(candle_pixels, 40)

    def test_far_levels_are_labels_without_compressing_candles(self):
        levels = {
            "support": 2000.0,
            "resistance": 4000.0,
            "fib": None,
            "bullish_fvg": None,
            "bearish_fvg": {"low": 4100.0, "high": 4200.0},
            "previous_day_high": 4300.0,
            "previous_day_low": 1900.0,
        }
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "levels.png"
            state = market_state.MarketState(Path(directory) / "state.json")
            payload = snapshot(
                "M15",
                "2026.06.28 13:30:00",
                open=2308.0,
                high=2320.0,
                low=2302.0,
                close=2301.0,
                retained_patterns=[],
                levels=levels,
            )
            payload["candles"] = [
                {
                    "time": "2026.06.28 13:15:00",
                    "open": 2300.0,
                    "high": 2310.0,
                    "low": 2290.0,
                    "close": 2306.0,
                },
                {
                    "time": "2026.06.28 13:30:00",
                    "open": 2308.0,
                    "high": 2320.0,
                    "low": 2302.0,
                    "close": 2301.0,
                },
            ]
            state.update(payload)

            with patch.object(
                market_chart.ImageDraw.ImageDraw, "text", autospec=True
            ) as draw_text:
                market_chart.MarketChart(state).levels_chart("Gold", path)

            labels = [call.args[2] for call in draw_text.call_args_list]
            with market_chart.Image.open(path) as image:
                pixels = image.load()
                candle_ys = [
                    y
                    for x in range(90, 820)
                    for y in range(70, 690)
                    if pixels[x, y] in ((20, 184, 166), (248, 113, 113))
                ]

        self.assertIn(
            "M15 Bear FVG 4100.00-4200.00 above chart", labels
        )
        self.assertIn("M15 Support 2000.00 below chart", labels)
        self.assertGreater(max(candle_ys) - min(candle_ys), 200)


if __name__ == "__main__":
    unittest.main()
