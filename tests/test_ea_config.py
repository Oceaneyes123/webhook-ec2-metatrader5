import unittest
import re
from pathlib import Path

from webhook.ea_config import EAS, load, payload


class EaConfigTest(unittest.TestCase):
    def test_every_canonical_ea_has_scalar_yaml_config(self):
        for ea in EAS:
            with self.subTest(ea=ea):
                self.assertTrue(load(ea))
                self.assertEqual(payload(ea)["ea"], ea)

    def test_account_action_secret_is_not_remotely_configured(self):
        self.assertNotIn("AccountActionSecret", load("Webhook2"))

    def test_yaml_covers_each_nonsecret_input(self):
        root = Path(__file__).resolve().parent.parent / "mq5"
        for ea in EAS:
            with self.subTest(ea=ea):
                inputs = set(re.findall(r"^input\s+\w+\s+(\w+)", (root / f"{ea}.mq5").read_text(encoding="utf-8"), re.M))
                self.assertEqual(inputs - {"AccountActionSecret"}, set(load(ea)))
