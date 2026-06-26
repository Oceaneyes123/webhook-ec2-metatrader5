import json
import os
import tempfile
import urllib.error
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import webhook


class WebhookTest(unittest.TestCase):
    def test_send_telegram_message_posts_to_send_message_api(self):
        requests = []

        def fake_urlopen(request, timeout):
            requests.append((request, timeout))

            class Response:
                def __enter__(self):
                    return self

                def __exit__(self, *args):
                    return None

                def read(self):
                    return b'{"ok":true}'

            return Response()

        with patch.dict(
            os.environ,
            {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID": "chat"},
        ), patch("urllib.request.urlopen", fake_urlopen):
            webhook.send_telegram_message({"hello": "world"})

        request, timeout = requests[0]
        self.assertEqual(
            request.full_url,
            "https://api.telegram.org/bottoken/sendMessage",
        )
        self.assertEqual(timeout, 10)
        self.assertEqual(request.headers["Content-type"], "application/json")
        self.assertEqual(
            json.loads(request.data),
            {"chat_id": "chat", "text": '{\n  "hello": "world"\n}'},
        )

    def test_load_env_reads_dotenv_without_overwriting_existing_values(self):
        with tempfile.TemporaryDirectory() as directory:
            env_file = Path(directory) / ".env"
            env_file.write_text(
                "TELEGRAM_BOT_TOKEN=from-file\n"
                "TELEGRAM_CHAT_ID=from-file\n",
                encoding="utf-8",
            )

            with patch.dict(
                os.environ,
                {"TELEGRAM_BOT_TOKEN": "from-env"},
                clear=True,
            ):
                webhook.load_env(env_file)

                self.assertEqual(os.environ["TELEGRAM_BOT_TOKEN"], "from-env")
                self.assertEqual(os.environ["TELEGRAM_CHAT_ID"], "from-file")

    def test_send_telegram_message_includes_telegram_error_body(self):
        def fake_urlopen(request, timeout):
            raise urllib.error.HTTPError(
                request.full_url,
                400,
                "Bad Request",
                {},
                BytesIO(b'{"description":"Bad Request: chat not found"}'),
            )

        with patch.dict(
            os.environ,
            {"TELEGRAM_BOT_TOKEN": "token", "TELEGRAM_CHAT_ID": "chat"},
        ), patch("urllib.request.urlopen", fake_urlopen):
            with self.assertRaisesRegex(Exception, "chat not found"):
                webhook.send_telegram_message({"hello": "world"})

    def test_server_config_defaults_to_ec2_ready_bind(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertEqual(
                webhook.server_config(),
                ("0.0.0.0", 8000, "http://localhost:8000/webhook"),
            )

    def test_server_config_uses_env_values(self):
        with patch.dict(
            os.environ,
            {
                "HOST": "127.0.0.1",
                "PORT": "9000",
                "PUBLIC_URL": "http://3.27.46.138:9000/webhook",
            },
            clear=True,
        ):
            self.assertEqual(
                webhook.server_config(),
                ("127.0.0.1", 9000, "http://3.27.46.138:9000/webhook"),
            )


if __name__ == "__main__":
    unittest.main()
