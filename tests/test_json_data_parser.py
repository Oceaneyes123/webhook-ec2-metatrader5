"""Tests for json_data_parser — candle messages, symbol aliases, display time."""
from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from webhook import json_data_parser


class CandleAlertMessageTest(unittest.TestCase):
    """Message formatting for candle/pattern alerts."""

    def test_engulfing_candle_message_uses_buy_format(self):
        self.assertEqual(
            json_data_parser.candle_alert_message(
                {
                    "event_type": "ENGULFING_CANDLE",
                    "signal": "BUY",
                    "symbol": "GOLDmicro",
                    "timeframe": "M15",
                    "candle_time": "2026.06.26 12:00",
                    "open": "1.2345",
                    "close": "1.2360",
                }
            ),
            "📈 GOLD Engulfing Candle - M15\n"
            "Bias: Bullish / BUY\n"
            "🕒 2026.06.26 05:00 PM\n"
            "💰 1.2345 - 1.2360",
        )

    def test_candle_message_removes_broker_prefix_and_suffix_from_symbol(self):
        self.assertEqual(
            json_data_parser.candle_alert_message(
                {
                    "event_type": "HAMMER_CANDLE",
                    "signal": "BUY",
                    "symbol": "microEURUSDm#",
                    "timeframe": "M15",
                    "candle_time": "2026.06.26 12:00",
                    "open": "1.2345",
                    "close": "1.2360",
                }
            ).splitlines()[0],
            "📈 EURUSD Hammer Candle - M15",
        )

    def test_candle_message_escapes_dynamic_html(self):
        message = json_data_parser.candle_alert_message(
            {
                "event_type": "ENGULFING_CANDLE",
                "signal": "BUY",
                "symbol": "X<Y",
                "timeframe": "M15",
                "candle_time": "2026.06.26 12:00",
                "open": "1<2",
                "close": "3&4",
            }
        )
        self.assertIn("X&lt;Y", message)
        self.assertIn("1&lt;2 - 3&amp;4", message)
        self.assertNotIn("X<Y", message)

    def test_engulfing_candle_message_uses_sell_format(self):
        self.assertEqual(
            json_data_parser.candle_alert_message(
                {
                    "event_type": "ENGULFING_CANDLE",
                    "signal": "SELL",
                    "timeframe": "H1",
                    "candle_time": "2026.06.26 13:00",
                    "open": "1.2360",
                    "close": "1.2345",
                }
            ),
            "📉 Engulfing Candle - H1\n"
            "Bias: Bearish / SELL\n"
            "🕒 2026.06.26 06:00 PM\n"
            "💰 1.2360 - 1.2345",
        )

    def test_candle_message_adds_five_hours_and_rolls_date(self):
        self.assertEqual(
            json_data_parser.candle_alert_message(
                {
                    "event_type": "ENGULFING_CANDLE",
                    "signal": "BUY",
                    "timeframe": "H4",
                    "candle_time": "2026.06.26 23:30:00",
                    "open": "1.2345",
                    "close": "1.2360",
                }
            ),
            "📈 Engulfing Candle - H4\n"
            "Bias: Bullish / BUY\n"
            "🕒 2026.06.27 04:30 AM\n"
            "💰 1.2345 - 1.2360",
        )

    def test_candle_message_uses_timezone_offset_from_environment(self):
        with patch.dict(os.environ, {"TIMEZONE_OFFSET_HOURS": "-2"}):
            self.assertEqual(
                json_data_parser.display_time("2026.06.26 01:30"),
                "2026.06.25 11:30 PM",
            )

    def test_engulfing_candle_message_rejects_missing_fields(self):
        with self.assertRaisesRegex(ValueError, "timeframe"):
            json_data_parser.candle_alert_message({"open": "1.2"})

    def test_hammer_message_uses_hammer_title(self):
        self.assertEqual(
            json_data_parser.candle_alert_message(
                {
                    "event_type": "HAMMER_CANDLE",
                    "signal": "BUY",
                    "timeframe": "M15",
                    "candle_time": "2026.06.26 12:00",
                    "open": "1.2345",
                    "close": "1.2360",
                }
            ),
            "📈 Hammer Candle - M15\n"
            "Bias: Bullish / BUY\n"
            "🕒 2026.06.26 05:00 PM\n"
            "💰 1.2345 - 1.2360",
        )

    def test_fixed_bias_patterns_infer_signal_and_bias(self):
        patterns = {
            "SHOOTING_STAR_CANDLE": ("📉", "Bearish / SELL"),
            "INVERTED_HAMMER_CANDLE": ("📈", "Bullish / BUY"),
            "MORNING_STAR": ("📈", "Bullish / BUY"),
            "EVENING_STAR": ("📉", "Bearish / SELL"),
        }
        for event_type, (icon, bias) in patterns.items():
            with self.subTest(event_type=event_type):
                message = json_data_parser.candle_alert_message(
                    {
                        "event_type": event_type,
                        "timeframe": "M15",
                        "candle_time": "2026.06.27 10:15",
                        "open": "2335.20",
                        "close": "2336.10",
                    }
                )
                self.assertTrue(message.startswith(icon))
                self.assertIn(f"Bias: {bias}", message)

    def test_inside_bar_breakout_uses_payload_signal(self):
        for signal, icon, bias in (
            ("BUY", "📈", "Bullish / BUY"),
            ("SELL", "📉", "Bearish / SELL"),
        ):
            with self.subTest(signal=signal):
                message = json_data_parser.candle_alert_message(
                    {
                        "event_type": "INSIDE_BAR_BREAKOUT",
                        "signal": signal,
                        "timeframe": "M15",
                        "candle_time": "2026.06.27 10:15",
                        "open": "2335.20",
                        "close": "2336.10",
                    }
                )
                self.assertTrue(message.startswith(icon))
                self.assertIn(f"Bias: {bias}", message)

    def test_candle_message_includes_ohlc_when_high_and_low_are_available(self):
        message = json_data_parser.candle_alert_message(
            {
                "event_type": "SHOOTING_STAR_CANDLE",
                "timeframe": "M15",
                "candle_time": "2026.06.27 10:15",
                "open": "2335.20",
                "high": "2341.80",
                "low": "2334.90",
                "close": "2336.10",
            }
        )
        self.assertIn(
            "💰 O: 2335.20 | H: 2341.80 | L: 2334.90 | C: 2336.10",
            message,
        )


class DisplayTimeTest(unittest.TestCase):
    """Timezone offset display formatting."""

    def test_display_time_accepts_seconds(self):
        self.assertEqual(
            json_data_parser.display_time("2026.06.26 01:30:45"),
            "2026.06.26 06:30 AM",
        )

    def test_display_time_returns_invalid_value_unchanged(self):
        self.assertEqual(json_data_parser.display_time("not a date"), "not a date")

    def test_display_time_returns_empty_for_none_or_blank(self):
        self.assertEqual(json_data_parser.display_time(None), "")
        self.assertEqual(json_data_parser.display_time("  "), "")

    def test_display_time_uses_default_offset_when_environment_is_invalid(self):
        with patch.dict(os.environ, {"TIMEZONE_OFFSET_HOURS": "invalid"}):
            self.assertEqual(
                json_data_parser.display_time("2026.06.26 01:30"),
                "2026.06.26 06:30 AM",
            )


class SupportedPayloadTest(unittest.TestCase):
    """Payload event-type filtering."""

    def test_is_supported_payload_accepts_alert_events(self):
        supported = (
            "ENGULFING_CANDLE",
            "HAMMER_CANDLE",
            "HANGING_MAN_CANDLE",
            "SHOOTING_STAR_CANDLE",
            "INVERTED_HAMMER_CANDLE",
            "MORNING_STAR",
            "EVENING_STAR",
            "INSIDE_BAR_BREAKOUT",
        )
        for event_type in supported:
            with self.subTest(event_type=event_type):
                self.assertTrue(
                    json_data_parser.is_supported_payload({"event_type": event_type})
                )
        self.assertFalse(
            json_data_parser.is_supported_payload({"event_type": "M1_CANDLE_CLOSE"})
        )

    def test_heartbeat_is_supported(self):
        self.assertTrue(
            json_data_parser.is_supported_payload({"event_type": "EA_HEARTBEAT"})
        )

    def test_trade_close_is_supported(self):
        self.assertTrue(
            json_data_parser.is_supported_payload(
                {
                    "event_type": "TRADE_CLOSE",
                    "symbol": "GOLD",
                    "reason": "TP_HIT",
                    "profit": 50.0,
                    "balance": 10000.0,
                }
            )
        )


class SymbolAliasTest(unittest.TestCase):
    """Symbol normalisation."""

    def test_gold_aliases_normalize_to_gold(self):
        for alias in ("GOLD", "Gold", "Goldmicro", "Goldm#", "XAUUSD"):
            with self.subTest(alias=alias):
                self.assertEqual(json_data_parser.display_symbol(alias), "GOLD")

    def test_xauusd_normalizes_to_gold(self):
        self.assertEqual(json_data_parser.display_symbol("XAUUSD"), "GOLD")

    def test_unknown_symbol_falls_back_safely(self):
        self.assertEqual(json_data_parser.display_symbol("EURUSD"), "EURUSD")
        self.assertEqual(json_data_parser.display_symbol("microEURUSDm#"), "EURUSD")

    def test_empty_symbol_returns_empty(self):
        self.assertEqual(json_data_parser.display_symbol(""), "")
        self.assertEqual(json_data_parser.display_symbol(None), "")
        self.assertEqual(json_data_parser.display_symbol("  "), "")


if __name__ == "__main__":
    unittest.main()
