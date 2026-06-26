import logging
import os
import time
from pathlib import Path


LOG_FILE = Path(os.environ.get("WEBHOOK_LOG_FILE", "webhook.log"))
CLEAN_AFTER_SECONDS = 5 * 60 * 60


class CleanFileHandler(logging.FileHandler):
    def emit(self, record):
        _clean_old_log(self)
        super().emit(record)


def get_logger():
    logger = logging.getLogger("webhook")
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    handler = CleanFileHandler(LOG_FILE, encoding="utf-8")
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    )
    logger.addHandler(handler)
    return logger


def _clean_old_log(handler=None):
    if LOG_FILE.exists() and time.time() - LOG_FILE.stat().st_mtime >= CLEAN_AFTER_SECONDS:
        if handler and handler.stream:
            handler.stream.close()
            handler.stream = None
        LOG_FILE.write_text("", encoding="utf-8")
