"""Read-only runtime configuration for the canonical MetaTrader EAs."""

import hashlib
from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
EAS = ("Webhook1", "Webhook2", "BigMove", "EMA", "TPSL", "Overtrade")


def load(name):
    if name not in EAS:
        raise ValueError("Unknown EA")
    path = CONFIG_DIR / f"{name}.yml"
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    values = data.get("values", {})
    if not isinstance(values, dict) or any(isinstance(value, (dict, list)) for value in values.values()):
        raise ValueError("EA configuration values must be scalars")
    return values


def payload(name):
    values = load(name)
    version = hashlib.sha256(repr(sorted(values.items())).encode()).hexdigest()[:12]
    return {"ea": name, "version": version, "values": values}
