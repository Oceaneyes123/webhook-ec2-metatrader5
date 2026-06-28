import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from app_logger import get_logger


logger = get_logger()


def send_telegram_message(text, retries=3, chat_id=None, parse_mode="HTML"):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = chat_id or os.environ["TELEGRAM_CHAT_ID"]
    payload = {"chat_id": chat_id, "text": text}
    if parse_mode:
        payload["parse_mode"] = parse_mode
    data = json.dumps(payload).encode()
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


def get_telegram_updates(offset=None, timeout_seconds=10):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    params = {"timeout": str(timeout_seconds)}
    if offset is not None:
        params["offset"] = str(offset)
    url = f"https://api.telegram.org/bot{token}/getUpdates?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=timeout_seconds + 5) as response:
        data = json.loads(response.read().decode("utf-8"))
    if not data.get("ok"):
        raise RuntimeError(data)
    return data.get("result", [])
