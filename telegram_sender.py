import json
import os
import time
import urllib.error
import urllib.request

from app_logger import get_logger


logger = get_logger()


def send_telegram_message(text, retries=3, chat_id=None):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = chat_id or os.environ["TELEGRAM_CHAT_ID"]
    data = json.dumps({"chat_id": chat_id, "text": text}).encode()
    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    for attempt in range(retries):
        try:
            logger.info("Sending Telegram request attempt=%s", attempt + 1)
            with urllib.request.urlopen(request, timeout=10) as response:
                result = response.read()
                logger.info("Telegram request sent")
                return result
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            logger.error("Telegram HTTP error=%s", detail or str(error))
            raise RuntimeError(detail or str(error)) from error
        except urllib.error.URLError as error:
            logger.warning("Telegram connection error attempt=%s error=%s", attempt + 1, error)
            if attempt == retries - 1:
                raise
            time.sleep(2)
