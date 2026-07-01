import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).parent
CANONICAL = ROOT / "mq5" / "Webhook.mq5"
SCRIPT = ROOT / "sync_mq5.py"


class SyncMq5Test(unittest.TestCase):
    def run_sync(self, target):
        environment = os.environ.copy()
        environment["MT5_MQ5_PATH"] = str(target)
        return subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )

    def test_sync_copies_canonical_source_to_configured_target(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "Webhook.mq5"

            result = self.run_sync(target)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(target.read_bytes(), CANONICAL.read_bytes())

    def test_sync_rejects_canonical_file_as_target(self):
        result = self.run_sync(CANONICAL)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("same file", result.stderr.lower())

    def test_canonical_mq5_uses_one_local_webhook_url(self):
        source = CANONICAL.read_text(encoding="utf-8")

        self.assertIn(
            'input string WebhookUrl = "http://127.0.0.1:8000/webhook";',
            source,
        )
        self.assertNotIn("ENV_PRODUCTION", source)
        self.assertNotIn("ProductionWebhookUrl", source)
        self.assertNotIn("3.27.46.138", source)
    def test_canonical_mq5_contains_rsi_and_trade_control_features(self):
        source = CANONICAL.read_text(encoding="utf-8")

        self.assertIn("iRSI(_Symbol, Timeframes[i], 14, PRICE_CLOSE)", source)
        self.assertIn("/trade-config", source)
        self.assertIn("TradeMagicNumber", source)
        self.assertIn("BuyConfluence()", source)
        self.assertIn("SellConfluence()", source)
        self.assertIn("trade.BuyLimit", source)
        self.assertIn("trade.SellLimit", source)
        self.assertIn("HasOpenPositionForSymbol()", source)
        self.assertIn("One open position per symbol", source)
        self.assertIn("SendEaIssue", source)
        self.assertIn("EA_ERROR", source)
        self.assertIn("TradeResultText", source)
        self.assertIn("ManageTrading();", source)


if __name__ == "__main__":
    unittest.main()
