from webhook.ea_config import DASHBOARD_CONFIGS, load, update


def grouped(name):
    values = load(name)
    groups = {}
    for key, value in values.items():
        group = "Connection" if key.startswith(("Webhook", "WebRequest")) else "Timing" if any(word in key for word in ("Seconds", "Minutes", "Timer", "Interval", "Cooldown", "Refresh")) else "Risk and execution" if any(word in key for word in ("Lot", "Lots", "Profit", "Stop", "Take", "Breakeven", "Magic", "Deviation", "Target")) else "Indicators and signals"
        groups.setdefault(group, []).append({"key": key, "value": value, "type": "bool" if isinstance(value, bool) else "number" if isinstance(value, (int, float)) else "text"})
    return groups
