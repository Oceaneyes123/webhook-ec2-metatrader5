"""Wire the pure engine to the existing market state and account store."""

import copy
import hashlib
import html
import logging
import threading
import time
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from .account import STORE, sessions
from .json_data_parser import display_symbol
from .strategy import evaluate, number, settings
from .strategy_journal import StrategyJournal, overtrade_reason

logger = logging.getLogger(__name__)


def session_name(now):
    active = []
    for name, zone, start, end in sessions():
        local = datetime.fromtimestamp(now, ZoneInfo(zone)).time()
        if (start <= local < end) if start <= end else (local >= start or local < end):
            active.append(name)
    if "London" in active and "New York" in active:
        return "London/NY"
    return next((name for name in ("New York", "London", "Asian") if name in active), "Outside")


def decision(symbol, market, cfg, quote=None, now=None):
    now = time.time() if now is None else now
    symbol = display_symbol(symbol).upper()
    with market.lock:
        frames = copy.deepcopy(market.data["symbols"].get(symbol, {}))
        structure = copy.deepcopy(market.data.get("market_structure", {}).get(symbol, {}))
    # Optional D1 levels cannot silently survive stale feeds.
    if now - number(frames.get("D1", {}).get("closed_at")) > 86400 + cfg["freshness_grace_seconds"]:
        frames.pop("D1", None)
    return evaluate(frames, structure, symbol, now, session_name(now), cfg, quote)


def execution_config(symbol, market, query, store=STORE):
    now = time.time()
    try:
        cfg = settings()
    except (OSError, ValueError, TypeError) as error:
        reason = f"NO TRADE: Invalid strategy config: {error}"
        store.decision({"symbol": symbol, "direction": "WAIT", "result": "FAIL", "reason": reason,
                        "time": datetime.fromtimestamp(now, timezone.utc).isoformat()})
        return {"strategy_direction": "WAIT", "strategy_reason": reason}
    account = query.get("broker_server", [""])[0] + ":" + query.get("account", [""])[0]
    quote = {key: number(query.get(key, [None])[0]) for key in ("bid", "ask", "tick_size", "stops_distance")}
    quote["received_at"] = number(query.get("quote_time", [None])[0])
    with store.lock:
        plan = decision(symbol, market, cfg, quote, now)
        journal = StrategyJournal(store)
        if plan["result"] == "PASS":
            plan["setup_id"] = hashlib.sha256((account + ":" + plan["setup_id"]).encode()).hexdigest()[:16]
            plan["config"] = cfg
            if account == ":":
                reason = "Execution account identity missing"
            else:
                reason = overtrade_reason(plan, journal.trades(plan["symbol"], account), journal.plans(account, plan["symbol"]), now, cfg)
            if reason or not journal.reserve(plan, account):
                plan.update(result="FAIL", reason="NO TRADE: " + (reason or "Duplicate setup"))
        plan["time"] = datetime.fromtimestamp(now, timezone.utc).isoformat()
        store.decision(plan)
    logger.debug("%s %s score=%s", plan["symbol"], plan["reason"], plan["score"])
    result = {"strategy_direction": plan["direction"] if plan["result"] == "PASS" else "WAIT",
              "strategy_reason": plan["reason"]}
    if plan["result"] == "PASS":
        result.update({"setup_id": plan["setup_id"], "entry": plan["entry"], "sl": plan["sl"], "tp": plan["tp"],
                       "expires_at": plan["expires_at"], "min_rr": cfg["min_rr"],
                       "execution_tolerance": plan["atr"] * cfg["execution_tolerance_atr"], **plan["management"]})
        # Sending setup alerts is authorized by the requested alert feature. No send during evaluation/tests.
        from . import state, telegram_sender
        from .config import telegram_configured
        if not state.ALERTS_PAUSED and telegram_configured():
            def send_alert():
                try:
                    telegram_sender.send_telegram_message(setup_message(plan))
                except Exception:
                    logger.exception("Setup alert delivery failed %s", plan["setup_id"])
            # Telegram retries must not consume the executable quote's lifetime.
            threading.Thread(target=send_alert, daemon=True).start()
    return result


def journal_transaction(payload, store=STORE):
    from .account import _event_timestamp
    journal = StrategyJournal(store)
    stamp = _event_timestamp(payload)
    event = dict(payload)
    if not event.get("setup_id") and event.get("transaction_type") in {"POSITION_OPENED", "PENDING_ORDER_FILLED"}:
        # Legacy/manual fills are journaled too. Never invent initial monetary risk.
        key = journal.position_key(event)
        event["setup_id"] = hashlib.sha256(("manual:" + key).encode()).hexdigest()[:16]
        symbol = display_symbol(event.get("symbol")).upper()
        direction = str(event.get("direction", "unknown")).replace("DEAL_TYPE_", "")
        now = time.time()
        from .state import MARKET_STATE
        try:
            cfg = settings()
            assessment = decision(symbol, MARKET_STATE, cfg, now=now) if abs(now - stamp) <= cfg["quote_max_age_seconds"] else {"reason": "Delayed fill; contemporaneous context unavailable"}
        except (ValueError, TypeError, OSError):
            assessment = {"reason": "Strategy configuration unavailable at fill"}
        plan = {"setup_id": event["setup_id"], "symbol": symbol, "direction": direction,
                "result": "MANUAL", "execution_offer": False, "evaluated_at": stamp,
                "setup_type": "legacy_manual", "score": None, "grade": "unscored",
                "htf_bias": assessment.get("htf_bias", "unknown"), "structure": assessment.get("structure", {}),
                "session": session_name(stamp), "timeframe": "manual", "entry": event.get("entry_price"),
                "sl": event.get("sl"), "tp": event.get("tp"), "planned_rr": None,
                "auto_assessment": assessment, "context_captured_at": now,
                "reason": "Explicit legacy/manual entry; R unavailable unless original monetary risk is recorded"}
        account = str(event.get("broker_server", "")) + ":" + str(event.get("account_login", ""))
        journal.reserve(plan, account)
    journal.record(event, stamp)


def setup_message(plan):
    if plan["result"] != "PASS":
        return html.escape(plan["reason"])
    return (f"<b>{plan['grade']} {plan['direction']} SETUP — {html.escape(plan['symbol'])}</b>\n"
            f"Score: {plan['score']}/100 | HTF: {plan['htf_bias']}\n"
            f"Setup: {plan['setup_type']} | {plan['timeframe']} | {html.escape(plan['session'])}\n"
            f"Entry: {plan['entry']:.5f} | SL: {plan['sl']:.5f} | TP: {plan['tp']:.5f}\n"
            f"Initial risk: {plan['initial_risk']:.5f} price units | R:R: 1:{plan['planned_rr']:.2f}\n"
            f"Location: {html.escape(plan['level']['timeframe'] + ' ' + plan['level']['label'])}\n"
            "Confluence: " + html.escape(", ".join(plan["confluence"]))
            + ("\nWarnings: " + html.escape("; ".join(plan["warnings"])) if plan["warnings"] else "")
            + "\nExecution offer; broker fill is not yet confirmed.")
