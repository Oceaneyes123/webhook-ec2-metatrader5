"""Durable strategy proposals, deal journal and R-based reports in AccountStore SQLite."""

import html
import json
import re
from collections import defaultdict
from datetime import datetime, timezone

from .strategy import number
from .json_data_parser import display_symbol


def account_key(payload):
    return f"{payload.get('broker_server', '')}:{payload.get('account_login', '')}"


def setup_id(payload):
    comment = str(payload.get("comment", ""))
    return payload.get("setup_id") or (comment[2:] if comment.startswith("S:") else "")


class StrategyJournal:
    def __init__(self, store):
        self.store = store
        with store.lock, store._connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS strategy_plans (
                    id TEXT PRIMARY KEY, account TEXT, symbol TEXT, created REAL, payload TEXT);
                CREATE INDEX IF NOT EXISTS strategy_plans_symbol ON strategy_plans(account,symbol,created);
                CREATE TABLE IF NOT EXISTS strategy_deals (
                    id TEXT PRIMARY KEY, position TEXT, setup_id TEXT, ts REAL, payload TEXT);
                CREATE INDEX IF NOT EXISTS strategy_deals_position ON strategy_deals(position,ts);
                CREATE TABLE IF NOT EXISTS strategy_marks (position TEXT PRIMARY KEY, payload TEXT);
            """)

    def plans(self, account, symbol, since=0):
        with self.store.lock, self.store._connect() as db:
            return [json.loads(r[0]) for r in db.execute(
                "SELECT payload FROM strategy_plans WHERE account=? AND symbol=? AND created>=? ORDER BY created",
                (account, symbol, since))]

    def accounts(self):
        """Latest reconciliation per broker/account, with server receipt time."""
        with self.store.lock, self.store._connect() as db:
            rows = db.execute("SELECT ts,payload FROM account_snapshots ORDER BY ts DESC")
            result = {}
            for row in rows:
                payload = json.loads(row["payload"])
                key = account_key(payload)
                if key != ":" and key not in result:
                    result[key] = {**payload, "received_at": row["ts"]}
        return result

    def lifecycle(self, limit=12, now=None, account=None, symbol=None, snapshots=None,
                  trades=None, ack_timeout=120, account_max_age=180):
        """Reconcile evidence without treating a missing position as proof of no fill."""
        now = datetime.now(timezone.utc).timestamp() if now is None else now
        clauses, args = ["1=1"], []
        for column, value in (("account", account), ("symbol", symbol)):
            if value:
                clauses.append(f"{column}=?")
                args.append(value)
        with self.store.lock, self.store._connect() as db:
            plans = [json.loads(row[0]) for row in db.execute(
                "SELECT payload FROM strategy_plans WHERE " + " AND ".join(clauses) + " ORDER BY created DESC", args)]
            events = {}
            for row in db.execute("SELECT payload FROM events WHERE kind='ENTRY_DECISION' ORDER BY ts DESC,rowid DESC"):
                event = json.loads(row[0])
                events.setdefault(event.get("setup_id"), event)
        snapshots = self.accounts() if snapshots is None else snapshots
        grouped = defaultdict(list)
        for trade in self.trades(symbol, account) if trades is None else trades:
            grouped[trade.get("setup_id")].append(trade)
        rows = []
        for plan in plans:
            if not plan.get("execution_offer", True):
                continue
            decision = events.get(plan.get("setup_id"), {})
            deals = grouped[plan["setup_id"]]
            snapshot = snapshots.get(plan.get("account"), {})
            fresh = 0 <= now - number(snapshot.get("received_at")) <= account_max_age
            positions = snapshot.get("positions", []) if fresh else []
            live = any(setup_id(p) == plan["setup_id"] for p in positions if isinstance(p, dict))
            reason = str(decision.get("reason", ""))
            code = re.match(r"retcode=(\d+)\b", reason)
            # Only definite non-execution outcomes release the entry hold. Timeouts
            # and transport failures require broker evidence; never blind-retry.
            rejected = reason.startswith("Expired offer, price drift") or (code and int(code[1]) in {
                10004, 10006, 10013, 10014, 10015, 10016, 10017, 10018, 10019, 10020, 10021,
                10022, 10024, 10026, 10027, 10030, 10032, 10033, 10034, 10035, 10042, 10043, 10044, 10046})
            if live:
                status, detail = "Filled", "Open position confirmed by MT5 reconciliation"
            elif deals and all(t.get("closed") for t in deals):
                status, detail = "Closed", "All journaled fills and closes matched"
            elif deals:
                status = "Uncertain" if fresh and number(snapshot.get("received_at")) > max(number(t.get("opened_at")) for t in deals) else "Filled"
                detail = "Position absent; awaiting missing closing deals" if status == "Uncertain" else "Fill recorded; awaiting fresh account reconciliation"
            elif decision.get("result") == "FAIL" and rejected:
                status, detail = "Rejected", reason
            elif decision.get("result") == "FAIL":
                status, detail = "Uncertain", reason or "Execution failed without a definite broker rejection"
            elif now >= number(plan.get("expires_at")) + ack_timeout:
                status, detail = "Uncertain", "Awaiting broker fill/history evidence; automatic retries held"
            elif decision.get("result") == "PASS":
                status, detail = "Submitted", reason or "Awaiting broker fill"
            elif now >= number(plan.get("expires_at")):
                status, detail = "Awaiting confirmation", "Offer expired; waiting for terminal evidence"
            else:
                status, detail = "Proposed", "Awaiting MT5 execution"
            rows.append({"status": status, "detail": detail, "plan": plan, "updated_at": decision.get("event_time", plan.get("evaluated_at"))})
        return rows if limit is None else rows[:limit]

    def entry_hold(self, account, symbol, now, cfg, snapshots=None):
        snapshots = self.accounts() if snapshots is None else snapshots
        snapshot = snapshots.get(account, {})
        if not 0 <= now - number(snapshot.get("received_at")) <= cfg["account_max_age_seconds"]:
            return "Account reconciliation missing or stale; waiting for MT5"
        for key, label in (("positions", "Open position"), ("pending_orders", "Pending order")):
            if any(display_symbol(p.get("symbol")).upper() == symbol for p in snapshot.get(key, []) if isinstance(p, dict)):
                return f"{label} already exists for {symbol}"
        for row in self.lifecycle(None, now, account, symbol, snapshots,
                                  ack_timeout=cfg["execution_ack_timeout_seconds"], account_max_age=cfg["account_max_age_seconds"]):
            if row["status"] not in {"Closed", "Rejected"}:
                return f"Execution {row['status'].lower()} ({row['plan']['setup_id']}): {row['detail']}"
        return ""

    def realized(self, start, end, account, symbol=None):
        """Deal-time cash flow, including opening costs and partial closes exactly once."""
        with self.store.lock, self.store._connect() as db:
            rows = db.execute("SELECT d.payload,p.symbol FROM strategy_deals d JOIN strategy_plans p ON p.id=d.setup_id WHERE d.ts>=? AND d.ts<? AND p.account=?",
                              (start, end, account)).fetchall()
        totals = dict.fromkeys(("profit", "commission", "swap", "fee"), 0.0)
        count = 0
        for row in rows:
            if symbol and row["symbol"] != symbol:
                continue
            event = json.loads(row["payload"])
            count += 1
            for key in totals:
                totals[key] += number(event.get(key))
        return {**totals, "net": sum(totals.values()), "deals": count}

    def reserve(self, plan, account):
        """One durable offer per signal; uncertain delivery must not cause blind retries."""
        plan = {**plan, "account": account}
        with self.store.lock, self.store._connect() as db:
            changed = db.execute("INSERT OR IGNORE INTO strategy_plans VALUES (?,?,?,?,?)",
                                 (plan["setup_id"], account, plan["symbol"], plan["evaluated_at"], json.dumps(plan))).rowcount
        return bool(changed)

    @staticmethod
    def position_key(event):
        return f"{event.get('broker_server', '')}:{event.get('account_login', '')}:{event.get('position_id', event.get('position_ticket', ''))}"

    def record(self, event, timestamp):
        key = self.position_key(event)
        with self.store.lock, self.store._connect() as db:
            setup_id = event.get("setup_id")
            if not setup_id:
                row = db.execute("SELECT setup_id FROM strategy_deals WHERE position=? LIMIT 1", (key,)).fetchone()
                setup_id = row[0] if row else None
            if not setup_id:
                return
            deal = str(event.get("deal_ticket") or "")
            if deal not in ("", "0"):
                # Broker/account/deal identity survives delivery retries and duplicate EA feeds.
                event_id = f"{event.get('broker_server', '')}:{event.get('account_login', '')}:{deal}"
                db.execute("INSERT OR IGNORE INTO strategy_deals VALUES (?,?,?,?,?)",
                           (event_id, key, setup_id, timestamp, json.dumps(event)))
            if number(event.get("initial_risk")) > 0:
                old = db.execute("SELECT payload FROM strategy_marks WHERE position=?", (key,)).fetchone()
                marks = json.loads(old[0]) if old else {}
                for name in ("mfe_r", "mae_r"):
                    marks[name] = max(number(marks.get(name)), number(event.get(name)))
                for name in ("initial_risk", "risk_cash", "initial_volume", "current_r"):
                    if event.get(name) is not None:
                        if name == "risk_cash" and not event.get("risk_confirmed", True):
                            continue
                        marks[name] = event[name]
                db.execute("INSERT OR REPLACE INTO strategy_marks VALUES (?,?)", (key, json.dumps(marks)))

    def trades(self, symbol=None, account=None):
        # ponytail: replay this personal journal in memory; SQL aggregates if history makes polling slow.
        with self.store.lock, self.store._connect() as db:
            rows = db.execute("SELECT d.*, p.payload AS plan FROM strategy_deals d LEFT JOIN strategy_plans p ON p.id=d.setup_id ORDER BY d.ts,d.id").fetchall()
            marks = {r[0]: json.loads(r[1]) for r in db.execute("SELECT * FROM strategy_marks")}
        grouped = {}
        for row in rows:
            event = json.loads(row["payload"])
            plan = json.loads(row["plan"]) if row["plan"] else {}
            if symbol and plan.get("symbol") != symbol:
                continue
            if account and plan.get("account") != account:
                continue
            trade = grouped.setdefault(row["position"], {**plan, "position": row["position"], "net_pnl": 0.0,
                "volume_in": 0.0, "volume_out": 0.0, "opened_at": None, "closed_at": None,
                "actual_r": None, "exit_reason": "", "journal_complete": bool(plan), "risk_cash": 0.0,
                "commission": 0.0, "swap": 0.0, "fee": 0.0})
            trade["net_pnl"] += sum(number(event.get(k)) for k in ("profit", "commission", "swap", "fee"))
            for cost in ("commission", "swap", "fee"):
                trade[cost] += number(event.get(cost))
            kind = event.get("transaction_type")
            if kind in {"POSITION_OPENED", "PENDING_ORDER_FILLED"}:
                trade["volume_in"] += number(event.get("volume"))
                trade["opened_at"] = min(trade["opened_at"] or row["ts"], row["ts"])
                trade["actual_entry"] = event.get("entry_price")
            elif kind in {"POSITION_CLOSED", "STOP_LOSS_HIT", "TAKE_PROFIT_HIT", "MANUAL_CLOSE", "PARTIAL_CLOSE", "MANUAL_PARTIAL_CLOSE"}:
                trade["volume_out"] += number(event.get("volume"))
                trade["closed_at"] = max(trade["closed_at"] or row["ts"], row["ts"])
                trade["exit_reason"] = event.get("reason", kind)
            elif kind == "POSITION_REVERSED":
                trade["journal_complete"] = False
            if event.get("risk_confirmed", True):
                trade["risk_cash"] = max(trade["risk_cash"], number(event.get("risk_cash")))
            trade["initial_risk"] = number(event.get("initial_risk"), trade.get("initial_risk", 0))
        for key, trade in grouped.items():
            trade.update(marks.get(key, {}))
            trade["closed"] = trade["volume_in"] > 0 and abs(trade["volume_out"] - trade["volume_in"]) < 1e-7
            if trade["closed"] and trade["journal_complete"] and number(trade.get("risk_cash")) > 0:
                trade["actual_r"] = trade["net_pnl"] / trade["risk_cash"]
        return list(grouped.values())


def overtrade_reason(plan, trades, offers, now, cfg):
    offers = [p for p in offers if p.get("execution_offer", True)]
    opened = [t for t in trades if t.get("opened_at")]
    if any(not t.get("closed") for t in opened):
        return "One active thesis already exists for this symbol (unresolved journal position)"
    today = datetime.fromtimestamp(now, timezone.utc).date()
    same_day = lambda ts: datetime.fromtimestamp(ts, timezone.utc).date() == today
    session_trades = [t for t in opened if same_day(t["opened_at"]) and t.get("session") == plan["session"]]
    if len(session_trades) >= cfg["max_trades_session"]:
        return "Maximum session trades reached"
    closed = sorted((t for t in opened if t.get("closed")), key=lambda t: t["closed_at"])
    day_closed = [t for t in closed if same_day(t["closed_at"])]
    streak = 0
    for trade in reversed(day_closed):
        if trade["net_pnl"] >= 0:
            break
        streak += 1
    if streak >= cfg["max_consecutive_losses"]:
        return "Consecutive-loss limit reached for UTC day"
    if closed:
        last = closed[-1]
        cooldown = cfg["loss_cooldown_seconds"] if last["net_pnl"] < 0 else cfg["win_cooldown_seconds"] if number(last.get("actual_r")) >= cfg["large_win_r"] else 0
        if now - last["closed_at"] < cooldown:
            return "Cooldown after loss/large win"
    if any(p["setup_id"] == plan["setup_id"] for p in offers):
        return "Duplicate setup already offered"
    if any(p["expires_at"] > now for p in offers):
        return "Another execution offer is still active"
    attempts = [p for p in offers if same_day(p["evaluated_at"]) and p["direction"] == plan["direction"]
                and abs(p["level"]["low"] - plan["level"]["low"]) <= plan["atr"] * cfg["level_cluster_atr"]]
    if len(attempts) >= cfg["max_level_attempts_day"]:
        return "Maximum attempts on this level reached for UTC day"
    return ""


def metrics(trades):
    rs = [t["actual_r"] for t in sorted(trades, key=lambda t: t.get("closed_at") or 0) if t.get("actual_r") is not None]
    wins, losses = [r for r in rs if r > 0], [r for r in rs if r < 0]
    equity = peak = drawdown = 0.0
    streak = 0
    for r in rs:
        equity += r
        peak = max(peak, equity)
        drawdown = max(drawdown, peak - equity)
        streak = streak + 1 if r < 0 else 0
    n = len(rs)
    return {"trades": n, "wins": len(wins), "losses": len(losses), "win_rate": len(wins) / n if n else 0,
            "avg_win_r": mean_value(wins), "avg_loss_r": -mean_value(losses),
            "expectancy": mean_value(rs), "total_r": sum(rs), "average_r": mean_value(rs),
            "profit_factor": sum(wins) / -sum(losses) if losses else None,
            "max_drawdown_r": drawdown, "losing_streak": streak}


def performance_segments(trades):
    rows = []
    for label, field in (("Setup", "setup_type"), ("Session", "session")):
        grouped = defaultdict(list)
        for trade in trades:
            if trade.get("actual_r") is not None:
                grouped[trade.get(field, "unknown")].append(trade)
        rows.extend({"group": label, "name": name, **metrics(items)} for name, items in sorted(grouped.items()))
    return rows


def mean_value(values):
    return sum(values) / len(values) if values else 0.0


def performance_report(trades, symbol):
    m = metrics(trades)
    pf = f"{m['profit_factor']:.2f}" if m["profit_factor"] is not None else "n/a (no losses)"
    omitted = sum(t.get("actual_r") is None for t in trades)
    lines = [f"<b>{html.escape(symbol)} strategy performance</b>",
             f"Trades {m['trades']} | W {m['wins']} / L {m['losses']} | Win rate {m['win_rate']:.1%}",
             f"Avg win {m['avg_win_r']:.2f}R | Avg loss {m['avg_loss_r']:.2f}R",
             f"Expectancy / Avg R: {m['expectancy']:+.2f}R | Total {m['total_r']:+.2f}R",
             f"Profit factor (R): {pf} | Max closed-trade DD: {m['max_drawdown_r']:.2f}R",
             f"Losing streak: {m['losing_streak']} | Open/incomplete excluded: {omitted}",
             "Net of reported commission, fee and swap. Legacy trades have no reconstructed R."]
    dimensions = {"Setup": lambda t: t.get("setup_type", "unknown"), "Score": lambda t: t.get("grade", "unknown"),
        "Direction": lambda t: t.get("direction", "unknown"), "Session": lambda t: t.get("session", "unknown"),
        "Day": lambda t: datetime.fromtimestamp(t["opened_at"], timezone.utc).strftime("%a"),
        "Timeframe": lambda t: t.get("timeframe", "unknown"), "HTF": lambda t: t.get("htf_bias", "unknown"),
        "Planned RR": lambda t: "<1.5" if t.get("planned_rr", 0) < 1.5 else "1.5–2" if t["planned_rr"] < 2 else "2–3" if t["planned_rr"] < 3 else "3+"}
    for label, key in dimensions.items():
        groups = defaultdict(list)
        for trade in trades:
            if trade.get("actual_r") is not None:
                groups[str(key(trade))].append(trade)
        parts = [f"{html.escape(name)}: n={len(items)}, E={metrics(items)['expectancy']:+.2f}R" for name, items in sorted(groups.items())]
        if parts:
            lines.append(f"<b>{label}</b> — " + "; ".join(parts))
    lines.append("Small samples are descriptive, not proof. Parameters never auto-adjust.")
    return "\n".join(lines)
