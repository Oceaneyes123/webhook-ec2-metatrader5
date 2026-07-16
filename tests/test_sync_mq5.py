"""Tests for sync_mq5 — file copying and source validation."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from webhook import sync_mq5
from tests.test_helpers import MQ5_RELATIVE_SOURCES, MQ5_SOURCE_DIR, make_mq5_sources

ROOT = Path(__file__).resolve().parent.parent


class SyncMq5Test(unittest.TestCase):
    """MQ5 source sync behaviour."""

    def test_sync_copies_eas_and_shared_includes(self):
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            source_dir = temporary / "mq5"
            live_dir = temporary / "Experts"
            make_mq5_sources(source_dir)
            live_dir.mkdir()

            copied = sync_mq5.sync_mq5(
                source_dir=source_dir,
                live_eas=(
                    live_dir / "Webhook1.mq5",
                    live_dir / "Webhook2.mq5",
                ),
            )

            self.assertEqual(len(copied), len(MQ5_RELATIVE_SOURCES))
            for relative in MQ5_RELATIVE_SOURCES:
                self.assertEqual(
                    (live_dir / relative).read_bytes(),
                    (source_dir / relative).read_bytes(),
                )

    def test_sync_rejects_canonical_files_as_live_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            source_dir = Path(directory) / "mq5"
            make_mq5_sources(source_dir)

            with self.assertRaisesRegex(ValueError, "same file"):
                sync_mq5.sync_mq5(
                    source_dir=source_dir,
                    live_eas=(
                        source_dir / "Webhook1.mq5",
                        source_dir / "Webhook2.mq5",
                    ),
                )


class Mq5SourceExistenceTest(unittest.TestCase):
    """All canonical MQL5 source files exist."""

    def test_all_canonical_mql5_sources_exist(self):
        for relative in MQ5_RELATIVE_SOURCES:
            with self.subTest(relative=relative):
                self.assertTrue((MQ5_SOURCE_DIR / relative).is_file())

    def test_legacy_canonical_ea_is_removed(self):
        self.assertFalse((MQ5_SOURCE_DIR / "Webhook.mq5").exists())


class EaContentTest(unittest.TestCase):
    """Structural assertions on MQ5 source contents."""

    def test_market_ea_owns_snapshots_only(self):
        ea = (MQ5_SOURCE_DIR / "Webhook1.mq5").read_text(encoding="utf-8")
        market = (MQ5_SOURCE_DIR / "includes/MarketSnapshot.mqh").read_text(
            encoding="utf-8"
        )

        self.assertIn('#include "includes/WebhookCommon.mqh"', ea)
        self.assertIn('#include "includes/MarketSnapshot.mqh"', ea)
        self.assertIn("input int ChartHistoryBars = 200;", ea)
        self.assertIn("CheckAllTimeframes();", ea)
        self.assertNotIn("ManageTrading", ea)
        self.assertIn('\\"source\\":\\"webhook1\\"', market)
        self.assertIn('\\"candles\\":', market)
        self.assertIn("BuildCandlesJson", market)
        self.assertIn(
            "for(int shift = ChartHistoryBars; shift >= 1; shift--)",
            market,
        )
        self.assertIn('{\\"time\\":\\"', market)
        self.assertIn("CalculateLevels", market)

    def test_trade_ea_owns_trade_management_only(self):
        ea = (MQ5_SOURCE_DIR / "Webhook2.mq5").read_text(encoding="utf-8")
        manager = (MQ5_SOURCE_DIR / "includes/TradeManager.mqh").read_text(
            encoding="utf-8"
        )

        self.assertIn('#include "includes/WebhookCommon.mqh"', ea)
        self.assertIn('#include "includes/TradeManager.mqh"', ea)
        self.assertIn("does not send chart/history data", ea)
        self.assertIn("ManageTrading();", ea)
        self.assertNotIn("CheckAllTimeframes", ea)
        self.assertNotIn("rsiHandles", ea)
        self.assertNotIn("CalculateLevels", manager)
        self.assertNotIn("TIMEFRAME_SNAPSHOT", manager)
        self.assertIn('\\"source\\":\\"webhook2\\"', manager)
        self.assertIn("FetchTradeConfig", manager)
        self.assertIn("TrailPendingOrder", manager)

    def test_trade_ea_manages_trading_on_timer(self):
        ea = (MQ5_SOURCE_DIR / "Webhook2.mq5").read_text(encoding="utf-8")
        on_tick = ea.split("void OnTick()", 1)[1].split("}", 1)[0]

        self.assertIn("input int TradeManageIntervalSeconds = 1;", ea)
        self.assertIn("TradeManageIntervalSeconds < 1", ea)
        self.assertIn("return INIT_PARAMETERS_INCORRECT;", ea)
        self.assertIn("EventSetTimer(TradeManageIntervalSeconds);", ea)
        self.assertIn("void OnTimer()", ea)
        self.assertIn("ManageTrading();", ea)
        self.assertIn("EventKillTimer();", ea)
        self.assertNotIn("ManageTrading();", on_tick)

    def test_trade_config_url_includes_encoded_chart_symbol(self):
        manager = (MQ5_SOURCE_DIR / "includes/TradeManager.mqh").read_text(
            encoding="utf-8"
        )

        self.assertIn("string UrlEncode(string value)", manager)
        self.assertIn('"/trade-config?symbol="', manager)
        self.assertIn("UrlEncode(_Symbol)", manager)

    def test_both_eas_use_the_local_webhook_default(self):
        expected = (
            'input string WebhookUrl = "http://127.0.0.1:8000/webhook";'
        )
        for name in ("Webhook1.mq5", "Webhook2.mq5"):
            source = (MQ5_SOURCE_DIR / name).read_text(encoding="utf-8")
            with self.subTest(name=name):
                self.assertIn(expected, source)

    def test_big_move_ea_checks_closed_m15_range_against_current_daily_atr(self):
        source = (MQ5_SOURCE_DIR / "BigMove.mq5").read_text(encoding="utf-8")

        self.assertIn("iATR(_Symbol, PERIOD_D1, AtrPeriod)", source)
        self.assertIn("iTime(_Symbol, PERIOD_M15, 1)", source)
        self.assertIn("CopyBuffer(dailyAtrHandle, 0, 0, 1, atr)", source)
        self.assertIn("range < threshold", source)
        self.assertIn('\\"event_type\\":\\"BIG_MOVE\\"', source)

    def test_readme_documents_mt5_ea_setup(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("## MT5 EA Setup", readme)
        self.assertIn("BigMove.mq5", readme)
        self.assertIn("trade_state.json", readme)
        self.assertIn("TRADE_STATE_FILE", readme)
        self.assertIn("TradeManageIntervalSeconds", readme)
        for command in (
            "/summary Gold",
            "/levels Gold",
            "/rsi Gold",
            "/buy Gold",
            "/sell Gold",
            "/notrade Gold",
            "/status Gold",
        ):
            with self.subTest(command=command):
                self.assertIn(command, readme)

    def test_webhook1_has_heartbeat_timer(self):
        ea = (MQ5_SOURCE_DIR / "Webhook1.mq5").read_text(encoding="utf-8")

        self.assertIn("input int HeartbeatSeconds = 30;", ea)
        self.assertIn("EventSetTimer(HeartbeatSeconds);", ea)
        self.assertIn("void OnTimer()", ea)
        self.assertIn('SendEaHeartbeat("webhook1")', ea)
        self.assertIn("EventKillTimer();", ea)
        self.assertIn("HeartbeatSeconds < 10", ea)

    def test_webhook2_has_heartbeat_and_config_cache(self):
        ea = (MQ5_SOURCE_DIR / "Webhook2.mq5").read_text(encoding="utf-8")

        self.assertIn("input int HeartbeatSeconds = 30;", ea)
        self.assertIn("input int TradeConfigRefreshSeconds = 5;", ea)
        self.assertIn("input int TradeConfigMaxStaleSeconds = 30;", ea)
        self.assertIn("lastHeartbeatTime", ea)
        self.assertIn("MaybeSendHeartbeat", ea)
        self.assertIn('SendEaHeartbeat("webhook2")', ea)
        self.assertIn("HeartbeatSeconds < 10", ea)
        self.assertIn("TradeConfigRefreshSeconds < 1", ea)
        self.assertIn(
            "TradeConfigMaxStaleSeconds < TradeConfigRefreshSeconds", ea
        )

    def test_trade_manager_has_config_cache(self):
        manager = (MQ5_SOURCE_DIR / "includes/TradeManager.mqh").read_text(
            encoding="utf-8"
        )

        self.assertIn("cachedTradeConfig", manager)
        self.assertIn("hasCachedTradeConfig", manager)
        self.assertIn("cachedTradeConfigTime", manager)
        self.assertIn("TradeConfigRefreshSeconds", manager)
        self.assertIn("TradeConfigMaxStaleSeconds", manager)
        self.assertNotIn("Using cached trade config", manager)
        self.assertNotIn("Refreshed trade config", manager)
        self.assertIn("stale-but-allowed fallback", manager)

    def test_webhook_common_has_send_ea_heartbeat(self):
        common = (MQ5_SOURCE_DIR / "includes/WebhookCommon.mqh").read_text(
            encoding="utf-8"
        )

        self.assertIn("SendEaHeartbeat", common)
        self.assertIn("EA_HEARTBEAT", common)

    def test_webhook_common_has_send_trade_close(self):
        common = (MQ5_SOURCE_DIR / "includes/WebhookCommon.mqh").read_text(
            encoding="utf-8"
        )

        self.assertIn("SendTradeCloseNotification", common)
        self.assertIn("TRADE_CLOSE", common)

    def test_trade_manager_has_position_close_detection(self):
        manager = (MQ5_SOURCE_DIR / "includes/TradeManager.mqh").read_text(
            encoding="utf-8"
        )

        self.assertIn("lastHadPosition", manager)
        self.assertIn("SendTradeCloseNotification", manager)
        self.assertIn("DEAL_REASON_TP", manager)
        self.assertIn("HistorySelect", manager)
        self.assertIn("TP_HIT", manager)
        self.assertIn("SL_HIT", manager)
        self.assertIn("MANUAL_CLOSE", manager)

    def test_trade_manager_notifies_when_an_ea_order_fills(self):
        manager = (MQ5_SOURCE_DIR / "includes/TradeManager.mqh").read_text(
            encoding="utf-8"
        )

        self.assertIn("NotifyFilledEaPositions", manager)
        self.assertIn('"webhook2"', manager)

    def test_webhook_common_has_send_trade_open(self):
        common = (MQ5_SOURCE_DIR / "includes/WebhookCommon.mqh").read_text(
            encoding="utf-8"
        )

        self.assertIn("SendTradeOpenNotification", common)
        self.assertIn("TRADE_OPEN", common)

    def test_trade_manager_has_manual_position_open_detection(self):
        manager = (MQ5_SOURCE_DIR / "includes/TradeManager.mqh").read_text(
            encoding="utf-8"
        )

        # P2 fix: tracks individual tickets, not a bool
        self.assertIn("lastManualPositionTickets", manager)
        self.assertIn("SendTradeOpenNotification", manager)
        # Detects new tickets regardless of EA position presence
        self.assertIn("TradeMagicNumber", manager)
        self.assertIn("StringFind", manager)
        # Iterates all positions (not just first), handles multiple opens per tick
        self.assertIn("for(int index = PositionsTotal() - 1; index >= 0; index--)", manager)

    def test_trade_ea_initializes_manual_position_tracker(self):
        ea = (MQ5_SOURCE_DIR / "Webhook2.mq5").read_text(encoding="utf-8")

        self.assertIn("lastManualPositionTickets", ea)
        # Initializes from existing positions at startup to avoid phantom TRADE_OPEN
        self.assertIn("HasOpenPositionForSymbol", ea)


if __name__ == "__main__":
    unittest.main()
