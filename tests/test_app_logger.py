"""Tests for app_logger — log cleanup."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from webhook import app_logger


class LoggerCleanTest(unittest.TestCase):
    """Log rotation / cleanup."""

    def test_logger_cleans_log_over_ten_megabytes(self):
        with tempfile.TemporaryDirectory() as directory:
            log_file = Path(directory) / "webhook.log"
            log_file.write_text("old log", encoding="utf-8")

            with patch.object(app_logger, "LOG_FILE", log_file):
                with patch.object(app_logger, "MAX_LOG_BYTES", 1):
                    app_logger._clean_old_log()

            self.assertEqual(log_file.read_text(encoding="utf-8"), "")

    def test_logger_keeps_log_at_limit(self):
        with tempfile.TemporaryDirectory() as directory:
            log_file = Path(directory) / "webhook.log"
            log_file.write_text("x", encoding="utf-8")

            with patch.object(app_logger, "LOG_FILE", log_file):
                with patch.object(app_logger, "MAX_LOG_BYTES", 1):
                    app_logger._clean_old_log()

            self.assertEqual(log_file.read_text(encoding="utf-8"), "x")


if __name__ == "__main__":
    unittest.main()
