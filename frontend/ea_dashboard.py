import os
import shutil
from datetime import datetime
from pathlib import Path

import yaml

from webhook.ea_config import CONFIG_DIR, EAS, load


def grouped(name):
    values = load(name)
    groups = {}
    for key, value in values.items():
        group = "Connection" if key.startswith(("Webhook", "WebRequest")) else "Timing" if any(word in key for word in ("Seconds", "Minutes", "Timer", "Interval", "Cooldown", "Refresh")) else "Risk and execution" if any(word in key for word in ("Lot", "Lots", "Profit", "Stop", "Take", "Breakeven", "Magic", "Deviation", "Target")) else "Indicators and signals"
        groups.setdefault(group, []).append({"key": key, "value": value, "type": "bool" if isinstance(value, bool) else "number" if isinstance(value, (int, float)) else "text"})
    return groups


def update(name, values):
    current = load(name)
    if not isinstance(values, dict) or set(values) - set(current): raise ValueError("Unknown configuration key")
    for key, value in values.items():
        old = current[key]
        if isinstance(old, bool):
            if str(value).lower() not in {"true", "false"}: raise ValueError(f"{key} must be true or false")
            current[key] = str(value).lower() == "true"
        elif isinstance(old, int) and not isinstance(old, bool): current[key] = int(value)
        elif isinstance(old, float): current[key] = float(value)
        elif isinstance(old, str): current[key] = str(value)
    path = CONFIG_DIR / f"{name}.yml"; backup = path.with_name(f"{name}.backup.{datetime.now():%Y%m%d-%H%M%S}.yml")
    shutil.copy2(path, backup)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(yaml.safe_dump({"values": current}, sort_keys=False), encoding="utf-8")
    temporary.replace(path)
    return current
