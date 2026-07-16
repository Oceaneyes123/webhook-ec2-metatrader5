import json
import mimetypes
import os
import time
import uuid
import urllib.error
import urllib.parse
import urllib.request

from .app_logger import get_logger


logger = get_logger()


def _post_telegram_request(request, retries, log=True):
    for attempt in range(retries):
        try:
            if log:
                logger.info("Sending Telegram request attempt=%s", attempt + 1)
            with urllib.request.urlopen(request, timeout=10) as response:
                result = response.read()
                if log:
                    logger.info("Telegram request sent")
                return result
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            if log:
                logger.error("Telegram HTTP error=%s", detail or str(error))
            raise RuntimeError(detail or str(error)) from error
        except urllib.error.URLError as error:
            if log:
                logger.warning("Telegram connection error attempt=%s error=%s", attempt + 1, error)
            if attempt == retries - 1:
                raise
            time.sleep(2)


def send_telegram_message(text, retries=3, chat_id=None, parse_mode="HTML", log=True):
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
    return _post_telegram_request(request, retries, log)


def send_telegram_photo(photo_path, caption=None, retries=3, chat_id=None, parse_mode="HTML"):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = chat_id or os.environ["TELEGRAM_CHAT_ID"]
    boundary = f"----HermesTelegramBoundary{uuid.uuid4().hex}"
    filename = os.path.basename(photo_path)
    content_type = mimetypes.guess_type(filename)[0] or "application/octet-stream"

    fields = {"chat_id": str(chat_id)}
    if caption:
        fields["caption"] = caption
    if parse_mode:
        fields["parse_mode"] = parse_mode

    body = bytearray()
    for name, value in fields.items():
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.extend(str(value).encode())
        body.extend(b"\r\n")

    with open(photo_path, "rb") as file:
        photo = file.read()
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(
        (
            f'Content-Disposition: form-data; name="photo"; filename="{filename}"\r\n'
            f"Content-Type: {content_type}\r\n\r\n"
        ).encode()
    )
    body.extend(photo)
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())

    request = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/sendPhoto",
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )
    return _post_telegram_request(request, retries)


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
