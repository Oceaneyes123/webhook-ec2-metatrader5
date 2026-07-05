"""EA heartbeat tracking — records, ages, and reports heartbeat status."""

import time

from .app_logger import get_logger
from .config import heartbeat_stale_seconds
from .json_data_parser import display_symbol

logger = get_logger()

EA_HEARTBEATS: dict = {}


def record_ea_heartbeat(payload):
    source = str(payload.get("source", "")).strip().lower()
    if not source:
        return
    symbol = display_symbol(payload.get("symbol"))
    status = str(payload.get("status", "running")).strip().lower() or "running"
    EA_HEARTBEATS[source] = {
        "source": source,
        "symbol": symbol,
        "status": status,
        "last_seen": time.monotonic(),
    }


def heartbeat_age_seconds(source):
    entry = EA_HEARTBEATS.get(source)
    if entry is None:
        return None
    return int(time.monotonic() - entry["last_seen"])


def heartbeat_status_lines():
    known_sources = ["webhook1", "webhook2", "tpsl"]
    display_names = {"webhook1": "Webhook1", "webhook2": "Webhook2", "tpsl": "TPSL"}
    stale = heartbeat_stale_seconds()
    lines = []
    for source in known_sources:
        name = display_names.get(source, source.capitalize())
        entry = EA_HEARTBEATS.get(source)
        if entry is None:
            lines.append(f"{name}: missing")
        else:
            age = heartbeat_age_seconds(source)
            sym = entry.get("symbol", "")
            if age is not None and age <= stale:
                ago_text = _format_age(age)
                lines.append(f"{name}: {entry['status']}, {sym}, {ago_text} ago")
            else:
                ago_text = _format_age(age) if age is not None else "?"
                lines.append(f"{name}: stale, {sym}, {ago_text} ago")
    # Add any unknown sources after known ones
    for source in sorted(EA_HEARTBEATS):
        if source not in known_sources:
            name = source.capitalize()
            entry = EA_HEARTBEATS[source]
            age = heartbeat_age_seconds(source)
            sym = entry.get("symbol", "")
            if age is not None and age <= stale:
                ago_text = _format_age(age)
                lines.append(f"{name}: {entry['status']}, {sym}, {ago_text} ago")
            else:
                ago_text = _format_age(age) if age is not None else "?"
                lines.append(f"{name}: stale, {sym}, {ago_text} ago")
    return lines


def _format_age(seconds):
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    secs = seconds % 60
    if minutes < 60:
        return f"{minutes}m {secs}s"
    hours = minutes // 60
    mins = minutes % 60
    return f"{hours}h {mins}m"
