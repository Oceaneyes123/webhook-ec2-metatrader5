import logging
import os
from pathlib import Path


LOG_FILE = Path(os.environ.get("WEBHOOK_LOG_FILE", "webhook.log"))
MAX_LOG_BYTES = 10 * 1024 * 1024


class CleanFileHandler(logging.FileHandler):
    def emit(self, record):
        _clean_old_log(self)
        super().emit(record)
        _clean_old_log(self)


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
    if LOG_FILE.exists() and LOG_FILE.stat().st_size > MAX_LOG_BYTES:
        if handler and handler.stream:
            handler.stream.close()
            handler.stream = None
        LOG_FILE.write_text("", encoding="utf-8")
