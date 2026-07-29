import tempfile
import unittest
import os
import json
from pathlib import Path
from unittest.mock import patch

from tests.test_helpers import snapshot
from webhook.candle_patterns import _level_interaction, confirmation_result, evaluate, raw_detection
from webhook import events
from webhook import market_state
from webhook.json_data_parser import candle_alert_message
from webhook.market_state import MarketState
from webhook.market_structure import confirm_structure


def candle(time, open_, high, low, close, **extra):
    return {"candle_time": time, "open": open_, "high": high, "low": low, "close": close, **extra}


class CandlePatternTest(unittest.TestCase):
    def test_short_star_history_and_three_candle_inside_breakout_regressions(self):
        short = [candle("1", 100, 101, 98, 99), candle("2", 98, 100, 97, 99)]
        self.assertFalse(raw_detection("MORNING_STAR", "BUY", short)["valid"])
        inside = [candle("1", 100, 105, 95, 99), candle("2", 99, 102, 98, 101), candle("3", 101, 107, 100, 106.5)]
        self.assertTrue(raw_detection("INSIDE_BAR_BREAKOUT", "BUY", inside)["valid"])

    def test_all_preserved_patterns_have_safe_raw_results(self):
        history = [candle(str(index), 100 - index, 101 - index, 98 - index, 99 - index) for index in range(4)]
        history += [candle("4", 96, 98, 94, 97), candle("5", 97, 97.5, 96.5, 97.1), candle("6", 97.1, 101, 96.8, 100)]
        for event_type, signal in (("ENGULFING_CANDLE", "BUY"), ("HAMMER_CANDLE", "BUY"), ("HANGING_MAN_CANDLE", "SELL"), ("SHOOTING_STAR_CANDLE", "SELL"), ("INVERTED_HAMMER_CANDLE", "BUY"), ("MORNING_STAR", "BUY"), ("EVENING_STAR", "SELL"), ("INSIDE_BAR_BREAKOUT", "BUY")):
            result = raw_detection(event_type, signal, history)
            self.assertIn(result["valid"], (True, False, None), event_type)

    def test_higher_timeframe_bias_and_countertrend_confirmation(self):
        history = [candle(str(index), 100, 101, 99, 100.5) for index in range(13)]
        history.append(candle("14", 100.4, 101, 98, 100.8))
        result = evaluate("HAMMER_CANDLE", "BUY", {"timeframe": "M15", "candle_time": "14"}, history, {"M15": {"ema_bias": "BULLISH", "levels": {"support": 100.7}}, "H1": {"ema_bias": "BEARISH", "levels": {}}})
        self.assertEqual(result["higher_timeframe_bias"], "BEARISH")
        self.assertEqual(result["confirmation_mode"], "follow_through")

    def test_engulfing_can_be_immediate(self):
        history = [candle(str(index), 100, 101, 99, 100.5) for index in range(12)]
        history += [candle("12", 101, 102, 100, 100), candle("13", 99.5, 103, 99, 102.5)]
        result = evaluate("ENGULFING_CANDLE", "BUY", {"timeframe": "M15", "candle_time": "13"}, history, {"M15": {"ema_bias": "BULLISH", "levels": {"support": 102.4}}})
        self.assertEqual(result["confirmation_mode"], "immediate")

    def test_direct_raw_event_is_informational_not_normal_alert(self):
        class Server:
            def __init__(self):
                self.body = None
            def write_text(self, code, body):
                self.body = body
        server = Server()
        with patch.object(events._tg, "send_telegram_message") as send:
            events._handle_candle_pattern({"event_type": "HAMMER_CANDLE", "signal": "BUY", "symbol": "GOLD", "timeframe": "M15", "candle_time": "1", "open": 100, "close": 101}, server)
        self.assertEqual(server.body, "ok")
        self.assertIn("Awaiting context", send.call_args.args[0])

    def test_restart_dedup_and_failed_or_expired_lifecycle(self):
        history = [candle(str(index), 100, 101, 99, 100.5) for index in range(13)]
        history += [candle("13", 101, 102, 100, 100), candle("14", 99.5, 103, 99, 102.5)]
        payload = snapshot("M15", "14", candle_history=history, ema20=101, ema50=100, levels={"support": 102.4, "resistance": None, "fib": None, "bullish_fvg": None, "bearish_fvg": None}, retained_patterns=[{"event_type": "ENGULFING_CANDLE", "signal": "BUY"}])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            state = MarketState(path)
            first = state.update(payload)
            state.mark_notified(first[0])
            self.assertEqual(MarketState(path).update(payload), [])

            old_max_age = market_state.PATTERN_MAX_AGE_CANDLES
            old_retention = market_state.PATTERN_RETENTION_CANDLES
            market_state.PATTERN_MAX_AGE_CANDLES = 2
            market_state.PATTERN_RETENTION_CANDLES = 3
            hammer_history = [candle(str(index), 100, 101, 99, 100.5) for index in range(13)] + [candle("20", 100, 101, 98, 100.8)]
            hammer = snapshot("M15", "20", candle_history=hammer_history, ema20=101, ema50=100, levels={"support": 100.7, "resistance": None, "fib": None, "bullish_fvg": None, "bearish_fvg": None}, retained_patterns=[{"event_type": "HAMMER_CANDLE", "signal": "BUY"}])
            state = MarketState(path)
            self.assertEqual(state.update(hammer), [])
            hammer_history.append(candle("21", 100.8, 101, 100.4, 100.6))
            self.assertEqual(state.update(snapshot("M15", "21", candle_history=hammer_history, retained_patterns=[])), [])
            hammer_history.append(candle("22", 100.6, 100.8, 100.3, 100.5))
            state.update(snapshot("M15", "22", candle_history=hammer_history, retained_patterns=[]))
            pattern = next(item for item in state.data["symbols"]["GOLD"]["M15"]["retained_patterns"] if item["event_type"] == "HAMMER_CANDLE")
            self.assertEqual(pattern["lifecycle"], "expired")
            hammer_history.append(candle("23", 100.5, 100.8, 100.2, 100.4))
            state.update(snapshot("M15", "23", candle_history=hammer_history, retained_patterns=[]))
            self.assertFalse(any(item["event_type"] == "HAMMER_CANDLE" for item in state.data["symbols"]["GOLD"]["M15"]["retained_patterns"]))
            market_state.PATTERN_MAX_AGE_CANDLES = old_max_age
            market_state.PATTERN_RETENTION_CANDLES = old_retention

    def test_context_message_tolerates_missing_optional_data(self):
        message = candle_alert_message({"event_type": "ENGULFING_CANDLE", "signal": "BUY", "symbol": "GOLD", "timeframe": "M15", "candle_time": "1", "open": 100, "close": 101, "qualified": True, "score": 70, "confidence": "Strong", "context_classification": "Unknown context"})
        self.assertIn("Quality", message)
        self.assertIn("Unknown context", message)
        invalidation = candle_alert_message({"event_type": "PATTERN_INVALIDATED", "signal": "BUY", "symbol": "GOLD", "timeframe": "M15", "candle_time": "2", "open": 100, "close": 95, "score": 0, "invalidation_reason": "Closed below invalidation 99"})
        self.assertIn("Invalidation warning", invalidation)

    def test_volume_session_daily_vwap_and_level_context(self):
        history = [candle(str(index), 100, 101, 99, 100.5, tick_volume=100) for index in range(11)]
        history.append(candle("11", 101, 102, 99, 99.5, tick_volume=100))
        history.append(candle("2026.07.29 08:00:00", 99, 103, 98, 102.5, tick_volume=200))
        payload = {"timeframe": "M15", "candle_time": "2026.07.29 08:00:00", "daily_high": 110, "daily_low": 90, "daily_atr": 25, "vwap": 101}
        snapshots = {"M15": {"ema_bias": "BULLISH", "levels": {"support": 101.5, "resistance": 102}}, "D1": {"candle_history": [candle(str(index), 95, 105, 90, 100) for index in range(14)]}}
        with patch.dict(os.environ, {"PATTERN_CANDLE_TIMEZONE": "UTC", "PATTERN_SESSION_TIMEZONE": "Asia/Manila", "PATTERN_SESSION_WINDOWS": json.dumps({"Tokyo": [8, 17, 1], "London": [15, 24, 1.5], "New York": [20, 29, 1]})}, clear=False):
            result = evaluate("ENGULFING_CANDLE", "BUY", payload, history, snapshots)
        self.assertEqual(result["tick_volume_ratio"], 2.0)
        self.assertIn("London", result["session"])
        self.assertIsNotNone(result["daily_atr_consumed"])
        self.assertEqual(result["vwap_event"], "reclaim")
        self.assertTrue(result["liquidity_sweep"])
        self.assertTrue(result["opposing_level"])

    def test_session_time_is_converted_from_candle_timezone(self):
        history = [candle(str(index), 100, 101, 99, 100.5) for index in range(13)]
        history += [candle("13", 101, 102, 100, 100), candle("2026.07.29 08:00:00", 99.5, 103, 98, 102.5)]
        with patch.dict(os.environ, {"PATTERN_CANDLE_TIMEZONE": "UTC", "PATTERN_SESSION_TIMEZONE": "Asia/Manila", "PATTERN_SESSION_WINDOWS": json.dumps({"Tokyo": [0, 1, 1], "London": [15, 24, 1], "New York": [2, 3, 1]})}, clear=False):
            result = evaluate("ENGULFING_CANDLE", "BUY", {"timeframe": "M15"}, history, {"M15": {"ema_bias": "BULLISH", "levels": {}}})
        self.assertEqual(result["session"], "London")

    def test_sweep_requires_material_atr_penetration(self):
        snapshots = {"M15": {"levels": {"support": 100}}}
        previous = candle("1", 100, 101, 99.5, 99.8)
        tiny = candle("2", 99.8, 101, 99.9, 100.2)
        real = candle("3", 99.8, 101, 99.4, 100.2)
        self.assertIsNone(_level_interaction(tiny, previous, "BUY", snapshots, 1.0)["sweep"])
        self.assertIsNotNone(_level_interaction(real, previous, "BUY", snapshots, 1.0)["sweep"])

    def test_pattern_invalidation_is_persisted_silent_and_restart_deduplicated(self):
        history = [candle(str(index), 100, 101, 99, 100.5) for index in range(13)]
        history += [candle("13", 101, 102, 100, 100), candle("14", 99.5, 103, 99, 102.5)]
        initial = snapshot("M15", "14", candle_history=history, ema20=101, ema50=100, levels={"support": 102.4, "resistance": None, "fib": None, "bullish_fvg": None, "bearish_fvg": None}, retained_patterns=[{"event_type": "ENGULFING_CANDLE", "signal": "BUY"}])
        later_history = history + [candle("15", 102.5, 103, 95, 95.5)]
        later = snapshot("M15", "15", candle_history=later_history, retained_patterns=[])
        with patch.dict(os.environ, {"PATTERN_INVALIDATION_ALERTS": "false"}, clear=False), tempfile.TemporaryDirectory() as directory:
            state = MarketState(Path(directory) / "state.json")
            first = state.update(initial)
            notified = first[0] if first else {**state.data["symbols"]["GOLD"]["M15"]["retained_patterns"][0], "symbol": "GOLD", "timeframe": "M15"}
            state.mark_notified(notified)
            self.assertEqual(state.data["symbols"]["GOLD"]["M15"]["retained_patterns"][0]["lifecycle"], "alerted")
            from webhook.candle_patterns import pattern_invalidation
            self.assertEqual(state.data["symbols"]["GOLD"]["M15"]["retained_patterns"][0]["candle_time"], "14")
            self.assertIn("invalidation_low", state.data["symbols"]["GOLD"]["M15"]["retained_patterns"][0])
            self.assertIsNotNone(pattern_invalidation(state.data["symbols"]["GOLD"]["M15"]["retained_patterns"][0], later_history))
            self.assertEqual(state.update(later), [])
            self.assertEqual(state.data["symbols"]["GOLD"]["M15"]["retained_patterns"][0]["lifecycle"], "invalidated")
            self.assertEqual(MarketState(Path(directory) / "state.json").update(later), [])

    def test_pattern_invalidation_alert_is_opt_in_and_deduplicated(self):
        history = [candle(str(index), 100, 101, 99, 100.5) for index in range(13)]
        history += [candle("13", 101, 102, 100, 100), candle("14", 99.5, 103, 99, 102.5)]
        initial = snapshot("M15", "14", candle_history=history, ema20=101, ema50=100, levels={"support": 102.4, "resistance": None, "fib": None, "bullish_fvg": None, "bearish_fvg": None}, retained_patterns=[{"event_type": "ENGULFING_CANDLE", "signal": "BUY"}])
        later_history = history + [candle("15", 102.5, 103, 95, 95.5)]
        later = snapshot("M15", "15", candle_history=later_history, retained_patterns=[])
        with patch.dict(os.environ, {"PATTERN_INVALIDATION_ALERTS": "true"}, clear=False), tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "state.json"
            state = MarketState(path)
            first = state.update(initial)
            notified = first[0] if first else {**state.data["symbols"]["GOLD"]["M15"]["retained_patterns"][0], "symbol": "GOLD", "timeframe": "M15"}
            state.mark_notified(notified)
            self.assertEqual(state.data["symbols"]["GOLD"]["M15"]["retained_patterns"][0]["lifecycle"], "alerted")
            invalidations = state.update(later)
            self.assertEqual([item["event_type"] for item in invalidations], ["PATTERN_INVALIDATED"])
            state.mark_notified(invalidations[0])
            self.assertEqual(MarketState(path).update(later), [])

    def test_context_classes_and_retest_structure_confirmation(self):
        history = [candle(str(index), 100 + index, 101 + index, 99 + index, 100.5 + index) for index in range(11)]
        history.append(candle("11", 111, 112, 109, 110))
        history.append(candle("12", 109, 114, 108, 113))
        payload = {"timeframe": "M15", "candle_time": "12"}
        result = evaluate("ENGULFING_CANDLE", "BUY", payload, history, {"M15": {"ema_bias": "BULLISH", "levels": {}}})
        self.assertIn(result["context_classification"], {"Trend-following", "Pullback continuation", "Unknown"})
        pattern = {"confirmation_mode": "retest", "signal": "BUY", "candle_time": "12", "close": 110.8, "low": 109}
        self.assertEqual(confirmation_result(pattern, history + [candle("13", 110.8, 112, 110.5, 111.5)]), "confirmed")
        structure = {**pattern, "confirmation_mode": "structure_confirmed", "structure_confirmed": True}
        self.assertEqual(confirmation_result(structure, history), "confirmed")

    def test_same_candle_related_patterns_are_grouped(self):
        history = [candle("1", 100, 101, 99, 100.5), candle("2", 99, 102, 98, 101.5)]
        payload = snapshot("M15", "2", candle_history=history, retained_patterns=[{"event_type": "ENGULFING_CANDLE", "signal": "BUY"}, {"event_type": "HAMMER_CANDLE", "signal": "BUY"}])
        context = {"qualified": True, "confirmed": True, "score": 70, "raw_valid": True, "confidence": "Strong", "confirmation_mode": "immediate", "confirmation_status": "Confirmed"}
        with patch.object(market_state, "evaluate", return_value=context):
            notifications = MarketState(Path(tempfile.mkdtemp()) / "state.json").update(payload)
        self.assertEqual(len(notifications), 1)
        self.assertEqual(notifications[0]["related_patterns"], ["HAMMER_CANDLE"])

    def test_partial_history_is_suppressed_through_market_state(self):
        with tempfile.TemporaryDirectory() as directory:
            state = MarketState(Path(directory) / "state.json")
            payload = snapshot("M15", "1", candle_history=[candle("1", 100, 101, 99, 100.5)], retained_patterns=[{"event_type": "ENGULFING_CANDLE", "signal": "BUY"}])
            notifications = state.update(payload)
            retained = state.data["symbols"]["GOLD"]["M15"]["retained_patterns"][0]
        self.assertEqual(notifications, [])
        self.assertEqual(retained["lifecycle"], "raw_detected")
        self.assertFalse(retained["confirmed"])

    def test_m30_update_does_not_invalidate_m15_or_mutate_higher_state(self):
        with tempfile.TemporaryDirectory() as directory:
            state = MarketState(Path(directory) / "state.json")
            state.update(snapshot("H1", "1", retained_patterns=[]))
            state.update(snapshot("M15", "2", retained_patterns=[{"event_type": "ENGULFING_CANDLE", "signal": "BUY"}]))
            state.update(snapshot("M30", "3", retained_patterns=[{"event_type": "SHOOTING_STAR_CANDLE", "signal": "SELL"}]))
            m15 = state.data["symbols"]["GOLD"]["M15"]["retained_patterns"][0]
            h1 = state.data["symbols"]["GOLD"]["H1"]["retained_patterns"]
        self.assertFalse(m15.get("invalidated", False))
        self.assertEqual(h1, [])

    def test_engulfing_and_weak_overlap(self):
        history = [candle("1", 100, 101, 98, 99), candle("2", 98.5, 102, 98, 101.5)]
        self.assertTrue(raw_detection("ENGULFING_CANDLE", "BUY", history)["valid"])
        weak = [candle("1", 100, 101, 99, 99.5), candle("2", 99.4, 100.2, 99, 99.8)]
        self.assertFalse(raw_detection("ENGULFING_CANDLE", "BUY", weak)["valid"])

    def test_small_pattern_and_far_level_are_not_qualified(self):
        history = [candle(str(index), 100, 100.2, 99.8, 100.1) for index in range(14)]
        history[-1] = candle("14", 100.0, 100.5, 98.5, 100.4)
        result = evaluate("HAMMER_CANDLE", "BUY", {"timeframe": "M15", "candle_time": "14"}, history, {"M15": {"ema_bias": "BEARISH", "levels": {}}})
        self.assertFalse(result["qualified"])
        self.assertIn("Far from a meaningful key level", result["reasons_reduced"])

    def test_small_wick_pattern_fails_raw_body_threshold(self):
        history = [candle(str(index), 100, 100.2, 99.8, 100.1) for index in range(3)]
        history.append(candle("3", 100, 101, 98, 100.05))
        self.assertFalse(raw_detection("HAMMER_CANDLE", "BUY", history)["valid"])

    def test_level_and_trend_can_qualify_a_pattern(self):
        history = [candle(str(index), 100, 101, 99, 100.5) for index in range(13)]
        history.append(candle("14", 100.4, 101, 98, 100.8))
        payload = {"timeframe": "M15", "candle_time": "14"}
        result = evaluate("HAMMER_CANDLE", "BUY", payload, history, {"M15": {"ema_bias": "BULLISH", "levels": {"support": 100.7}}})
        self.assertTrue(result["qualified"])
        self.assertEqual(result["nearest_key_level"]["label"], "Support")

    def test_market_state_persists_pattern_context_and_deduplicates_candle(self):
        with tempfile.TemporaryDirectory() as directory:
            state = MarketState(Path(directory) / "state.json")
            history = [candle(str(index), 100, 101, 99, 100.5) for index in range(13)]
            history.append(candle("14", 100.4, 101, 98, 100.8))
            payload = snapshot("M15", "14", candle_history=history, ema20=101, ema50=100, levels={"support": 100.7, "resistance": None, "fib": None, "bullish_fvg": None, "bearish_fvg": None}, retained_patterns=[{"event_type": "HAMMER_CANDLE", "signal": "BUY"}])
            notifications = state.update(payload)
            self.assertEqual([item for item in notifications if item["event_type"] == "HAMMER_CANDLE"], [])
            pattern = state.data["symbols"]["GOLD"]["M15"]["retained_patterns"][0]
            self.assertTrue(pattern["pattern_id"].endswith(":14"))
            self.assertIn("context_classification", pattern)
            self.assertEqual(pattern["lifecycle"], "awaiting_confirmation")
            history.append(candle("15", 100.8, 102, 100.5, 101.8))
            next_payload = snapshot("M15", "15", candle_history=history, ema20=101, ema50=100, levels=payload["levels"], retained_patterns=[])
            confirmed = state.update(next_payload)
            self.assertEqual([item["event_type"] for item in confirmed], ["HAMMER_CANDLE"])
            state.mark_notified(confirmed[0])
            self.assertEqual(state.data["symbols"]["GOLD"]["M15"]["retained_patterns"][0]["lifecycle"], "alerted")
            self.assertEqual(state.update(payload), [])

    def test_structure_confirmation_uses_persisted_trend_vocabulary(self):
        history = [candle(str(index), 100, 101, 99, 100.5) for index in range(14)]
        history.append(candle("15", 100.5, 102, 100, 101.5))
        with tempfile.TemporaryDirectory() as directory:
            state = MarketState(Path(directory) / "state.json")
            state.data["market_structure"] = {"GOLD": {"M30": {"trend": "bullish"}}}
            pending = {
                "event_type": "HAMMER_CANDLE", "signal": "BUY", "candle_time": "14",
                "confirmation_mode": "structure_confirmed", "qualified": True,
                "confirmed": False, "lifecycle": "awaiting_confirmation",
            }
            state.data["symbols"] = {"GOLD": {"M30": {"retained_patterns": [pending]}}}
            notifications = state.update(snapshot("M30", "15", candle_history=history, retained_patterns=[]))
        self.assertEqual([item["event_type"] for item in notifications], ["HAMMER_CANDLE"])

    def test_choch_ranging_state_is_not_rebuilt_from_old_swings(self):
        swings = [
            {"id": "h1", "type": "high", "price": 100, "broken": False},
            {"id": "l1", "type": "low", "price": 90, "broken": False},
            {"id": "h2", "type": "high", "price": 110, "broken": False},
            {"id": "l2", "type": "low", "price": 95, "broken": True},
        ]
        structure = {"GOLD": {"M30": {
            "trend": "ranging", "swings": swings, "broken": ["l2"],
            "ranging_swing_ids": [item["id"] for item in swings],
        }}}
        history = [candle(str(index), 100, 101, 99, 100) for index in range(6)]
        confirm_structure(structure, "GOLD", "M30", history)
        self.assertEqual(structure["GOLD"]["M30"]["trend"], "ranging")


if __name__ == "__main__":
    unittest.main()
