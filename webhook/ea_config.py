"""Read-only runtime configuration for the canonical MetaTrader EAs."""

import hashlib
import os
import shutil
import tempfile
from datetime import datetime
from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).resolve().parent.parent / "config"
EAS = ("Webhook1", "Webhook2", "BigMove", "EMA", "TPSL", "Overtrade")
TELEGRAM_CONFIG = "Telegram"
DASHBOARD_CONFIGS = EAS + (TELEGRAM_CONFIG,)


def path_for(name):
    if name not in DASHBOARD_CONFIGS:
        raise ValueError("Unknown EA")
    return CONFIG_DIR / f"{name}.yml"


def load(name):
    path = path_for(name)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    values = data.get("values", {})
    if not isinstance(values, dict) or any(isinstance(value, (dict, list)) for value in values.values()):
        raise ValueError("EA configuration values must be scalars")
    return values


def update(name, values):
    current = load(name)
    if not isinstance(values, dict) or set(values) - set(current):
        raise ValueError("Unknown configuration key")
    for key, value in values.items():
        old = current[key]
        if isinstance(old, bool):
            if str(value).lower() not in {"true", "false"}:
                raise ValueError(f"{key} must be true or false")
            current[key] = str(value).lower() == "true"
        elif isinstance(old, int) and not isinstance(old, bool):
            current[key] = int(value)
        elif isinstance(old, float):
            current[key] = float(value)
        elif isinstance(old, str):
            current[key] = str(value)
    path = path_for(name)
    backup = path.with_name(f"{name}.backup.{datetime.now():%Y%m%d-%H%M%S-%f}.yml")
    shutil.copy2(path, backup)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent, delete=False) as temporary:
        yaml.safe_dump({"values": current}, temporary, sort_keys=False)
        temporary_path = Path(temporary.name)
    try:
        os.replace(temporary_path, path)
    finally:
        if temporary_path.exists():
            temporary_path.unlink()
    return current


def payload(name):
    values = load(name)
    version = hashlib.sha256(repr(sorted(values.items())).encode()).hexdigest()[:12]
    return {"ea": name, "version": version, "values": values}
