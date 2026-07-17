"""Durable account-wide trade events, concise commands, and safe callbacks."""

import html
import json
import os
import secrets
import sqlite3
import threading
import time
from datetime import datetime, time as clock, timedelta
from zoneinfo import ZoneInfo

from .config import account_actions_enabled, account_db_path, price_stale_seconds
from .json_data_parser import display_symbol

PHT = ZoneInfo(os.environ.get("PHILIPPINE_TIMEZONE", "Asia/Manila"))
SESSIONS = (("Asian", "Asia/Tokyo", clock(9), clock(18)),
            ("London", "Europe/London", clock(8), clock(17)),
            ("New York", "America/New_York", clock(8), clock(17)))


class _Connection(sqlite3.Connection):
    """Close SQLite files on context exit (the stdlib default only commits)."""
    def __exit__(self, *args):
        result = super().__exit__(*args)
        self.close()
        return result


class AccountStore:
    def __init__(self, path=None):
        self.path = str(path or account_db_path())
        self.lock = threading.RLock()
        with self._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS events (id TEXT PRIMARY KEY, kind TEXT, ts REAL, payload TEXT);
                CREATE TABLE IF NOT EXISTS positions (ticket TEXT PRIMARY KEY, payload TEXT, updated REAL);
                CREATE TABLE IF NOT EXISTS account_snapshots (ts REAL PRIMARY KEY, payload TEXT);
                CREATE TABLE IF NOT EXISTS decisions (symbol TEXT PRIMARY KEY, payload TEXT, updated REAL);
                CREATE TABLE IF NOT EXISTS confirmations (token TEXT PRIMARY KEY, action TEXT, payload TEXT, expires REAL, used INTEGER DEFAULT 0);
                CREATE TABLE IF NOT EXISTS actions (id TEXT PRIMARY KEY, action TEXT, payload TEXT, created REAL, claimed INTEGER DEFAULT 0);
                CREATE TABLE IF NOT EXISTS reports (window TEXT PRIMARY KEY, sent REAL);
            """)

    def _connect(self):
        db = sqlite3.connect(self.path, factory=_Connection)
        db.row_factory = sqlite3.Row
        return db

    def event(self, payload):
        event_id = str(payload.get("event_id") or payload.get("deal_ticket") or payload.get("order_ticket") or secrets.token_hex(12))
        with self.lock, self._connect() as db:
            try:
                db.execute("INSERT INTO events VALUES (?,?,?,?)", (event_id, str(payload.get("event_type", "TRADE_TRANSACTION")), time.time(), json.dumps(payload)))
            except sqlite3.IntegrityError:
                return False
        return True

    def reconcile(self, positions, account=None):
        with self.lock, self._connect() as db:
            db.execute("DELETE FROM positions")
            for position in positions:
                ticket = str(position.get("position_ticket") or position.get("ticket") or "")
                if ticket:
                    db.execute("INSERT OR REPLACE INTO positions VALUES (?,?,?)", (ticket, json.dumps(position), time.time()))
            if isinstance(account, dict):
                db.execute("INSERT INTO account_snapshots VALUES (?,?)", (time.time(), json.dumps(account)))
        return positions

    def positions(self):
        with self.lock, self._connect() as db:
            return [json.loads(row["payload"]) for row in db.execute("SELECT payload FROM positions")]

    def decision(self, payload):
        symbol = display_symbol(payload.get("symbol")).upper()
        with self.lock, self._connect() as db:
            db.execute("INSERT OR REPLACE INTO decisions VALUES (?,?,?)", (symbol, json.dumps(payload), time.time()))

    def latest_decision(self, symbol):
        with self.lock, self._connect() as db:
            row = db.execute("SELECT payload,updated FROM decisions WHERE symbol=?", (display_symbol(symbol).upper(),)).fetchone()
        return (json.loads(row["payload"]), row["updated"]) if row else (None, None)

    def confirmation(self, action, payload, seconds=None):
        token = secrets.token_urlsafe(12)
        expires = time.time() + (seconds or int(os.environ.get("CONFIRMATION_EXPIRY_SECONDS", "120")))
        with self.lock, self._connect() as db:
            db.execute("INSERT INTO confirmations(token,action,payload,expires) VALUES (?,?,?,?)", (token, action, json.dumps(payload), expires))
        return token

    def consume_confirmation(self, token):
        with self.lock, self._connect() as db:
            row = db.execute("SELECT * FROM confirmations WHERE token=?", (token,)).fetchone()
            if not row or row["used"] or row["expires"] < time.time():
                return None
            db.execute("UPDATE confirmations SET used=1 WHERE token=?", (token,))
        return row

    def queue_action(self, action, payload):
        action_id = secrets.token_urlsafe(12)
        with self.lock, self._connect() as db:
            db.execute("INSERT INTO actions VALUES (?,?,?,?,0)", (action_id, action, json.dumps(payload), time.time()))
        return action_id

    def claim_action(self):
        with self.lock, self._connect() as db:
            row = db.execute("SELECT * FROM actions WHERE claimed=0 ORDER BY created LIMIT 1").fetchone()
            if not row: return None
            db.execute("UPDATE actions SET claimed=1 WHERE id=?", (row["id"],))
        return {"id": row["id"], "action": row["action"], **json.loads(row["payload"])}

    def action_result(self, action_id):
        with self.lock, self._connect() as db:
            db.execute("DELETE FROM actions WHERE id=?", (action_id,))

    def report_sent(self, window):
        with self.lock, self._connect() as db:
            try:
                db.execute("INSERT INTO reports VALUES (?,?)", (window, time.time()))
            except sqlite3.IntegrityError:
                return False
        return True

    def report_exists(self, window):
        with self.lock, self._connect() as db:
            return db.execute("SELECT 1 FROM reports WHERE window=?", (window,)).fetchone() is not None

    def events_between(self, start, end):
        with self.lock, self._connect() as db:
            rows = db.execute("SELECT payload FROM events WHERE ts>=? AND ts<?", (start.timestamp(), end.timestamp())).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def account_snapshot(self, at=None):
        """Most recent reconciliation at or before ``at``."""
        query = "SELECT payload FROM account_snapshots"
        args = ()
        if at is not None:
            query += " WHERE ts<=?"; args = (at.timestamp(),)
        query += " ORDER BY ts DESC LIMIT 1"
        with self.lock, self._connect() as db:
            row = db.execute(query, args).fetchone()
        return json.loads(row["payload"]) if row else {}


STORE = AccountStore()


def pip_size(symbol, digits=5, point=None):
    """MT5 convention: fractional FX quotes use ten points; metals default to 0.1."""
    name = display_symbol(symbol).upper()
    if name == "GOLD" or name.startswith("XAU"):
        return float(os.environ.get("GOLD_PIP_SIZE", "0.1"))
    return (point or 10 ** -int(digits)) * (10 if int(digits) in (3, 5) else 1)


def _snapshot(symbol, market_state):
    frames = market_state.data["symbols"].get(display_symbol(symbol).upper(), {})
    return frames.get("M1") or frames.get("M5"), frames


def price_report(symbol, market_state):
    symbol = display_symbol(symbol).upper()
    snapshot, _ = _snapshot(symbol, market_state)
    if not snapshot:
        return f"<b>{html.escape(symbol)}</b>\nPrice unavailable. Awaiting MetaTrader data."
    received = float(snapshot.get("received_at", 0))
    age = max(0, int(time.time() - received)) if received else None
    bid, ask = snapshot.get("bid", snapshot.get("close")), snapshot.get("ask", snapshot.get("close"))
    daily_open = snapshot.get("daily_open", snapshot.get("open"))
    high, low = snapshot.get("daily_high", snapshot.get("high")), snapshot.get("daily_low", snapshot.get("low"))
    spread = abs(float(ask) - float(bid)) if bid is not None and ask is not None else None
    change = ((float(bid) - float(daily_open)) / float(daily_open) * 100) if daily_open else None
    digits = int(snapshot.get("digits", 5))
    fmt = lambda value: "?" if value is None else f"{float(value):.{digits}f}"
    lines = [f"💱 <b>{html.escape(symbol)} Price</b>", f"Bid / Ask: <code>{fmt(bid)} / {fmt(ask)}</code>", f"Spread: <code>{fmt(spread)}</code>", f"Daily O/H/L: <code>{fmt(daily_open)} / {fmt(high)} / {fmt(low)}</code>", f"Change: <code>{change:+.2f}%</code>" if change is not None else "Change: ?", f"Latest: {html.escape(str(snapshot.get('candle_time', '?')))}", f"Data age: {age if age is not None else '?'}s"]
    if age is None or age > price_stale_seconds(): lines.append("⚠️ <b>Market data is stale; do not treat this as a live quote.</b>")
    return "\n".join(lines)


def session_status(now=None):
    now = now or datetime.now(PHT)
    active = []
    for name, zone, start, end in SESSIONS:
        local = now.astimezone(ZoneInfo(zone)).time()
        if start <= local < end: active.append(name)
    return " / ".join(active) if active else "Outside configured sessions"


def session_times(now=None):
    now = now or datetime.now(PHT)
    return " | ".join(
        f"{name}: {datetime.combine(now.astimezone(ZoneInfo(zone)).date(), start, tzinfo=ZoneInfo(zone)).astimezone(PHT):%H:%M}–{datetime.combine(now.astimezone(ZoneInfo(zone)).date(), end, tzinfo=ZoneInfo(zone)).astimezone(PHT):%H:%M}"
        for name, zone, start, end in SESSIONS
    )


def market_report(symbol, market_state, now=None):
    symbol = display_symbol(symbol).upper(); snapshot, frames = _snapshot(symbol, market_state)
    m5 = frames.get("M5")
    if not m5: trend, reason = "Unavailable", "Awaiting M5 EMA data"
    else:
        age = int(time.time() - m5.get("received_at", 0))
        if age > price_stale_seconds(): trend, reason = "Stale", f"M5 data age: {age}s"
        else:
            a, b = m5.get("ema20"), m5.get("ema50")
            trend = "Bullish" if a and b and a > b else "Bearish" if a and b and a < b else "Mixed"
            reason = f"M5 EMA20 {'>' if trend == 'Bullish' else '<' if trend == 'Bearish' else '='} EMA50" if a is not None and b is not None else "EMA values unavailable"
    return f"📊 <b>{html.escape(symbol)} Market</b>\nM5 trend: <b>{trend}</b>\n{reason}\nSession: <b>{session_status(now)}</b>\nPHT sessions: {session_times(now)}"


def why_report(symbol):
    decision, updated = STORE.latest_decision(symbol)
    symbol = display_symbol(symbol).upper()
    if not decision: return f"<b>{html.escape(symbol)}</b>\nNo entry decision recorded."
    age = int(time.time() - updated)
    lines = [f"🧭 <b>{html.escape(symbol)} Entry Decision</b>", f"Direction: {html.escape(str(decision.get('direction', '?')))}", f"Result: <b>{html.escape(str(decision.get('result', 'FAIL')))}</b>"]
    if decision.get("reason"): lines.append(f"Reason: {html.escape(str(decision['reason']))}")
    lines.extend([f"Time: {html.escape(str(decision.get('time', '?')))}", f"Age: {age}s" + (" ⚠️ stale" if age > price_stale_seconds() else "")])
    return "\n".join(lines)


def transaction_message(payload):
    symbol = display_symbol(payload.get("symbol")).upper() or "?"
    kind = str(payload.get("transaction_type") or payload.get("kind") or "Trade transaction").replace("_", " ").title()
    lines = [f"💼 <b>{html.escape(kind)}</b>", f"Symbol: {html.escape(symbol)}"]
    for label, key in (("Position", "position_ticket"), ("Order", "order_ticket"), ("Deal", "deal_ticket"), ("Direction", "direction"), ("Volume", "volume"), ("Profit", "profit"), ("Reason", "reason")):
        if payload.get(key) not in (None, "", 0): lines.append(f"{label}: {html.escape(str(payload[key]))}")
    return "\n".join(lines)


def profit_alert(payload):
    ticket = str(payload.get("position_ticket") or payload.get("ticket") or "")
    if not ticket: return None
    pips = float(payload.get("profit_pips", 0))
    if pips < float(os.environ.get("PROFIT_ALERT_PIPS", "50")): return None
    if not STORE.event({"event_id": f"profit-alert:{ticket}", "event_type": "PROFIT_ALERT"}): return None
    symbol = display_symbol(payload.get("symbol")).upper()
    return "\n".join((f"🛡️ <b>Profit Protection</b>", f"Symbol: {html.escape(symbol)}", f"Position: {html.escape(ticket)}", f"Direction: {html.escape(str(payload.get('direction', '?')))}", f"Entry / Current: {payload.get('entry_price', '?')} / {payload.get('current_price', '?')}", f"Profit: <b>{pips:.1f} pips</b> ({float(payload.get('floating_profit', 0)):+.2f})", f"SL / TP: {payload.get('sl', '?')} / {payload.get('tp', '?')}", f"Duration: {payload.get('duration', '?')}"))


def confirmation_prompt(action):
    positions = STORE.positions()
    if action == "be":
        eligible = [p for p in positions if float(p.get("profit_pips", 0)) > float(os.environ.get("BREAKEVEN_ELIGIBILITY_PIPS", "30"))]
        title = "Move SL to BE"
        detail = f"{len(eligible)} eligible positions; protects about {os.environ.get('BREAKEVEN_PROTECTED_PIPS', '10')} pips."
    else:
        eligible = [p for p in positions if float(p.get("floating_profit", p.get("profit", 0))) > 0]
        title = "Close Profitable Positions"
        detail = f"{len(eligible)} positions; combined floating profit {sum(float(p.get('floating_profit', p.get('profit', 0))) for p in eligible):+.2f}."
    if not eligible: return "No positions are currently eligible.", None
    token = STORE.confirmation(action, {"tickets": [str(p.get("position_ticket") or p.get("ticket")) for p in eligible], "eligibility_pips": float(os.environ.get("BREAKEVEN_ELIGIBILITY_PIPS", "30")), "protected_pips": float(os.environ.get("BREAKEVEN_PROTECTED_PIPS", "10"))})
    return f"⚠️ <b>Confirm: {title}</b>\n{detail}\nPositions are revalidated before execution.", {"inline_keyboard": [[{"text": "Confirm", "callback_data": f"confirm:{token}"}, {"text": "Cancel", "callback_data": f"cancel:{token}"}]]}


def action_buttons():
    return {"inline_keyboard": [[{"text": "Move SL to BE", "callback_data": "act:be"}, {"text": "Close Profitable Positions", "callback_data": "act:close"}]]}


def report_text(name, start, end, store=STORE):
    events = store.events_between(start, end)
    closed = [e for e in events if e.get("transaction_type") in ("POSITION_CLOSED", "PARTIAL_CLOSE", "MANUAL_CLOSE", "STOP_LOSS_HIT", "TAKE_PROFIT_HIT")]
    profit = [float(e.get("profit", 0)) for e in closed]
    gross_profit, gross_loss = sum(p for p in profit if p > 0), sum(p for p in profit if p < 0)
    positions = store.positions(); floating = sum(float(p.get("floating_profit", 0)) for p in positions)
    opening, ending = store.account_snapshot(start), store.account_snapshot(end)
    balance, equity = ending.get("balance"), ending.get("equity")
    manual = sum(e.get("magic_number") in (0, "0", None) for e in closed)
    automated = len(closed) - manual
    win_rate = 100 * sum(p > 0 for p in profit) / len(profit) if profit else 0
    symbols = ", ".join(sorted({display_symbol(e.get("symbol")).upper() for e in events if e.get("symbol")})) or "none"
    lines = [f"📋 <b>{name}</b>", f"Period: {start.astimezone(PHT):%Y-%m-%d %H:%M} – {end.astimezone(PHT):%Y-%m-%d %H:%M} PHT", f"Symbols: {html.escape(symbols)}", f"Opened / Closed: {sum(e.get('transaction_type') in ('POSITION_OPENED', 'PENDING_ORDER_FILLED') for e in events)} / {len(closed)}", f"Wins/Losses/BE (win rate): {sum(p > 0 for p in profit)}/{sum(p < 0 for p in profit)}/{sum(p == 0 for p in profit)} ({win_rate:.0f}%)", f"Gross +/− / Net: {gross_profit:+.2f} / {gross_loss:+.2f} / {sum(profit):+.2f}", f"Commission / Swap: {sum(float(e.get('commission', 0)) for e in closed):+.2f} / {sum(float(e.get('swap', 0)) for e in closed):+.2f}", f"Largest win/loss: {max(profit, default=0):+.2f} / {min(profit, default=0):+.2f}", f"Manual / EA closes: {manual} / {automated}", f"Open positions / floating: {len(positions)} / {floating:+.2f}", f"Balance / Equity: {balance if balance is not None else '?'} / {equity if equity is not None else '?'}", f"Profit alerts / BE actions / close actions: {sum(e.get('event_type') == 'PROFIT_ALERT' for e in events)} / {sum(e.get('action') == 'be' for e in events)} / {sum(e.get('action') == 'close' for e in events)}"]
    snapshots = [e for e in events if e.get("event_type") == "TIMEFRAME_SNAPSHOT"]
    by_symbol = {}
    for snap in snapshots:
        symbol = display_symbol(snap.get("symbol")).upper()
        if symbol and all(snap.get(key) is not None for key in ("open", "high", "low", "close")):
            by_symbol.setdefault(symbol, []).append(snap)
    for symbol, candles in sorted(by_symbol.items()):
        candles.sort(key=lambda item: str(item.get("candle_time", "")))
        lines.append(f"{html.escape(symbol)} session O/H/L/C: {candles[0]['open']} / {max(float(c['high']) for c in candles)} / {min(float(c['low']) for c in candles)} / {candles[-1]['close']}")
    return "\n".join(lines)


def due_reports(now=None):
    now = now or datetime.now(PHT)
    end = now.replace(second=0, microsecond=0)
    due = []
    hour = int(os.environ.get("DAILY_REPORT_HOUR", "6"))
    scheduled = end.replace(hour=hour, minute=0)
    if end < scheduled: scheduled -= timedelta(days=1)
    if os.environ.get("DAILY_REPORT_ENABLED", "true").lower() in ("1", "true", "yes"):
        due.append(("Daily 24-hour Report", scheduled - timedelta(days=1), scheduled))
    for name, zone, _start, finish in SESSIONS:
        if os.environ.get("SESSION_REPORTS_ENABLED", "true").lower() not in ("1", "true", "yes"): break
        local = end.astimezone(ZoneInfo(zone))
        scheduled_end = datetime.combine(local.date(), finish, tzinfo=ZoneInfo(zone))
        if local < scheduled_end: scheduled_end -= timedelta(days=1)
        local_start = datetime.combine(scheduled_end.date(), _start, tzinfo=ZoneInfo(zone))
        due.append((f"{name} Session Report", local_start, scheduled_end))
    return due
