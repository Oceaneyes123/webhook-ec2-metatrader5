"""Tests for app_logger — log cleanup."""
from __future__ import annotations

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from webhook import app_logger


class LoggerCleanTest(unittest.TestCase):
    """Log rotation / cleanup."""

    def test_logger_cleans_log_after_five_hours(self):
        with tempfile.TemporaryDirectory() as directory:
            log_file = Path(directory) / "webhook.log"
            log_file.write_text("old log", encoding="utf-8")
            old_time = time.time() - app_logger.CLEAN_AFTER_SECONDS - 1
            os.utime(log_file, (old_time, old_time))

            with patch.object(app_logger, "LOG_FILE", log_file):
                app_logger._clean_old_log()

            self.assertEqual(log_file.read_text(encoding="utf-8"), "")


if __name__ == "__main__":
    unittest.main()
