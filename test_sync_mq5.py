import tempfile
import unittest
from pathlib import Path

import sync_mq5


ROOT = Path(__file__).parent
MQ5 = ROOT / "mq5"
RELATIVE_SOURCES = (
    Path("Webhook1.mq5"),
    Path("Webhook2.mq5"),
    Path("includes/WebhookCommon.mqh"),
    Path("includes/MarketSnapshot.mqh"),
    Path("includes/TradeManager.mqh"),
    Path("TPSL.mq5"),
)


class SyncMq5Test(unittest.TestCase):
    def make_sources(self, source_dir):
        for relative in RELATIVE_SOURCES:
            source = source_dir / relative
            source.parent.mkdir(parents=True, exist_ok=True)
            source.write_text(str(relative), encoding="utf-8")

    def test_sync_copies_both_eas_and_shared_includes(self):
        with tempfile.TemporaryDirectory() as directory:
            temporary = Path(directory)
            source_dir = temporary / "mq5"
            live_dir = temporary / "Experts"
            self.make_sources(source_dir)
            live_dir.mkdir()

            copied = sync_mq5.sync_mq5(
                source_dir=source_dir,
                live_eas=(
                    live_dir / "Webhook1.mq5",
                    live_dir / "Webhook2.mq5",
                ),
            )

            self.assertEqual(len(copied), len(RELATIVE_SOURCES))
            for relative in RELATIVE_SOURCES:
                self.assertEqual(
                    (live_dir / relative).read_bytes(),
                    (source_dir / relative).read_bytes(),
                )

    def test_sync_rejects_canonical_files_as_live_targets(self):
        with tempfile.TemporaryDirectory() as directory:
            source_dir = Path(directory) / "mq5"
            self.make_sources(source_dir)

            with self.assertRaisesRegex(ValueError, "same file"):
                sync_mq5.sync_mq5(
                    source_dir=source_dir,
                    live_eas=(
                        source_dir / "Webhook1.mq5",
                        source_dir / "Webhook2.mq5",
                    ),
                )

    def test_all_canonical_mql5_sources_exist(self):
        for relative in RELATIVE_SOURCES:
            with self.subTest(relative=relative):
                self.assertTrue((MQ5 / relative).is_file())

    def test_market_ea_owns_snapshots_only(self):
        ea = (MQ5 / "Webhook1.mq5").read_text(encoding="utf-8")
        market = (MQ5 / "includes/MarketSnapshot.mqh").read_text(encoding="utf-8")

        self.assertIn('#include "includes/WebhookCommon.mqh"', ea)
        self.assertIn('#include "includes/MarketSnapshot.mqh"', ea)
        self.assertIn("input int ChartHistoryBars = 200;", ea)
        self.assertIn("CheckAllTimeframes();", ea)
        self.assertNotIn("ManageTrading", ea)
        self.assertIn('\\"source\\":\\"webhook1\\"', market)
        self.assertIn('\\"candles\\":', market)
        self.assertIn("BuildCandlesJson", market)
        self.assertIn(
            "for(int shift = ChartHistoryBars; shift >= 1; shift--)", market
        )
        self.assertIn('{\\"time\\":\\"', market)
        self.assertIn("CalculateLevels", market)

    def test_trade_ea_owns_trade_management_only(self):
        ea = (MQ5 / "Webhook2.mq5").read_text(encoding="utf-8")
        manager = (MQ5 / "includes/TradeManager.mqh").read_text(encoding="utf-8")

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
        ea = (MQ5 / "Webhook2.mq5").read_text(encoding="utf-8")
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
        manager = (MQ5 / "includes/TradeManager.mqh").read_text(encoding="utf-8")

        self.assertIn("string UrlEncode(string value)", manager)
        self.assertIn('"/trade-config?symbol="', manager)
        self.assertIn("UrlEncode(_Symbol)", manager)

    def test_both_eas_use_the_local_webhook_default(self):
        expected = 'input string WebhookUrl = "http://127.0.0.1:8000/webhook";'
        for name in ("Webhook1.mq5", "Webhook2.mq5"):
            source = (MQ5 / name).read_text(encoding="utf-8")
            with self.subTest(name=name):
                self.assertIn(expected, source)

    def test_legacy_canonical_ea_is_removed(self):
        self.assertFalse((MQ5 / "Webhook.mq5").exists())

    def test_readme_documents_two_ea_setup(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")

        self.assertIn("## Two-EA MT5 Setup", readme)
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
        ea = (MQ5 / "Webhook1.mq5").read_text(encoding="utf-8")

        self.assertIn("input int HeartbeatSeconds = 30;", ea)
        self.assertIn("EventSetTimer(HeartbeatSeconds);", ea)
        self.assertIn("void OnTimer()", ea)
        self.assertIn('SendEaHeartbeat("webhook1")', ea)
        self.assertIn("EventKillTimer();", ea)
        self.assertIn("HeartbeatSeconds < 10", ea)

    def test_webhook2_has_heartbeat_and_config_cache(self):
        ea = (MQ5 / "Webhook2.mq5").read_text(encoding="utf-8")

        self.assertIn("input int HeartbeatSeconds = 30;", ea)
        self.assertIn("input int TradeConfigRefreshSeconds = 5;", ea)
        self.assertIn("input int TradeConfigMaxStaleSeconds = 30;", ea)
        self.assertIn("lastHeartbeatTime", ea)
        self.assertIn("MaybeSendHeartbeat", ea)
        self.assertIn('SendEaHeartbeat("webhook2")', ea)
        self.assertIn("HeartbeatSeconds < 10", ea)
        self.assertIn("TradeConfigRefreshSeconds < 1", ea)
        self.assertIn("TradeConfigMaxStaleSeconds < TradeConfigRefreshSeconds", ea)

    def test_trade_manager_has_config_cache(self):
        manager = (MQ5 / "includes/TradeManager.mqh").read_text(encoding="utf-8")

        self.assertIn("cachedTradeConfig", manager)
        self.assertIn("hasCachedTradeConfig", manager)
        self.assertIn("cachedTradeConfigTime", manager)
        self.assertIn("TradeConfigRefreshSeconds", manager)
        self.assertIn("TradeConfigMaxStaleSeconds", manager)
        self.assertIn("Using cached trade config", manager)
        self.assertIn("stale-but-allowed fallback", manager)

    def test_webhook_common_has_send_ea_heartbeat(self):
        common = (MQ5 / "includes/WebhookCommon.mqh").read_text(encoding="utf-8")

        self.assertIn("SendEaHeartbeat", common)
        self.assertIn("EA_HEARTBEAT", common)


if __name__ == "__main__":
    unittest.main()
