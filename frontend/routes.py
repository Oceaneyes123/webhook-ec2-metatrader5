import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .ea_dashboard import DASHBOARD_CONFIGS, grouped, update
from webhook.account import STORE
from webhook.strategy_journal import StrategyJournal, metrics, performance_segments
from webhook.trade_state import TRADE_MODE, symbol_trade_modes, set_trade_mode
from webhook import state

TEMPLATES = Environment(loader=FileSystemLoader(Path(__file__).parent / "templates"), autoescape=select_autoescape())


def dashboard(handler):
    selected = parse_qs(urlparse(handler.path).query).get("ea", [DASHBOARD_CONFIGS[0]])[0]
    if selected not in DASHBOARD_CONFIGS: selected = DASHBOARD_CONFIGS[0]
    journal = StrategyJournal(STORE)
    trades = journal.trades()
    today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0).timestamp()
    closed_today = [trade for trade in trades if trade.get("closed_at", 0) >= today]
    with state.MARKET_STATE.lock:
        received = [frame.get("received_at", 0) for frames in state.MARKET_STATE.data["symbols"].values() for frame in frames.values()]
    snapshot = STORE.account_snapshot()
    overview = {
        "modes": symbol_trade_modes(), "default_mode": TRADE_MODE,
        "alerts_paused": state.alerts_paused(), "positions": STORE.positions(),
        "equity": snapshot.get("equity"), "balance": snapshot.get("balance"),
        "closed_pnl": sum(trade["net_pnl"] for trade in closed_today),
        "performance": metrics(trades), "segments": performance_segments(trades),
        "market_age": int(time.time() - max(received)) if received else None,
        "lifecycle": journal.lifecycle(),
    }
    handler.write_text(200, TEMPLATES.get_template("ea_dashboard.html").render(eas=DASHBOARD_CONFIGS, selected=selected, groups=grouped(selected), overview=overview), "text/html; charset=utf-8")


def api(handler):
    name = parse_qs(urlparse(handler.path).query).get("ea", [""])[0]
    try:
        if handler.command == "GET": handler.write_json(200, {"ea": name, "groups": grouped(name)}); return
        raw = handler.rfile.read(int(handler.headers.get("Content-Length", 0)) or 0)
        values = json.loads(raw or b"{}").get("values", {}) if handler.headers.get("Content-Type", "").startswith("application/json") else {key.removeprefix("values."): value[-1] for key, value in parse_qs(raw.decode()).items() if key.startswith("values.")}
        update(name, values); handler.write_json(200, {"updated": list(values)})
    except (OSError, ValueError, json.JSONDecodeError) as error: handler.write_json(400, {"error": str(error)})


def trade_mode_api(handler):
    try:
        raw = handler.rfile.read(int(handler.headers.get("Content-Length", 0)) or 0)
        values = parse_qs(raw.decode())
        symbol, mode = values.get("symbol", [""])[-1], values.get("mode", [""])[-1]
        if not symbol or mode not in {"AUTO", "NOTRADE"}:
            raise ValueError("symbol and AUTO or NOTRADE mode required")
        handler.write_json(200, {"symbol": symbol, "mode": set_trade_mode(mode, symbol)})
    except (OSError, ValueError) as error: handler.write_json(400, {"error": str(error)})
