"""Pure closed-candle setup evaluation. No Telegram, storage or MT5 side effects."""

import hashlib
import json
import math
import os
from pathlib import Path
from statistics import mean

FRAME_SECONDS = {"M1": 60, "M5": 300, "M15": 900, "M30": 1800, "H1": 3600, "H4": 14400, "D1": 86400}
CONFIG_PATH = Path(__file__).resolve().parent.parent / "strategy_config.json"


def settings():
    config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    override = os.environ.get("STRATEGY_CONFIG_FILE")
    if override:
        supplied = json.loads(Path(override).read_text(encoding="utf-8"))
        if not isinstance(supplied, dict):
            raise ValueError("Strategy overrides must be a JSON object")
        if supplied.keys() - config.keys():
            raise ValueError("Unknown strategy settings: " + str(supplied.keys() - config.keys()))
        config = {**config, **supplied, "weights": {**config["weights"], **supplied.get("weights", {})}}
    for key, value in config.items():
        if isinstance(value, (int, float)) and (not math.isfinite(value) or value < 0):
            raise ValueError(f"Invalid strategy setting: {key}")
    for key in ("atr_period", "retest_lookback", "htf_min_aligned", "max_trades_session", "max_consecutive_losses", "max_level_attempts_day"):
        if not isinstance(config[key], int) or config[key] < 1:
            raise ValueError(f"{key} must be a positive integer")
    if not 60 <= config["min_score"] <= 100 or config["min_rr"] <= 0 or config["htf_min_aligned"] > 3:
        raise ValueError("Invalid score, R:R or HTF requirement")
    for key in ("confirmation_body_ratio", "confirmation_close_location", "partial_fraction"):
        if not 0 <= config[key] < 1:
            raise ValueError(f"{key} must be in [0, 1)")
    if config["trailing_method"] not in {"off", "structure", "ema"}:
        raise ValueError("Invalid trailing method")
    if not config["entry_timeframes"] or set(config["entry_timeframes"]) - {"M5", "M15"}:
        raise ValueError("Entry timeframes must be M5/M15")
    if set(config["enabled_setups"]) - {"pullback", "breakout_retest"}:
        raise ValueError("Unknown setup type")
    if set(config["allowed_sessions"]) - {"Asian", "London", "London/NY", "New York", "Outside"}:
        raise ValueError("Unknown session")
    if any(not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 for v in config["weights"].values()):
        raise ValueError("Weights must be finite and nonnegative")
    if config["atr_min_ratio"] >= config["atr_max_ratio"] or config["sl_min_atr"] <= 0 or config["plan_ttl_seconds"] <= 0:
        raise ValueError("Invalid volatility, stop or expiry setting")
    if config["protect_r"] > 0 and config["protect_lock_r"] >= config["protect_r"]:
        raise ValueError("Protected profit must be below the protection trigger")
    if config["partial_fraction"] > 0 and config["partial_close_r"] <= 0:
        raise ValueError("Partial exits require a positive R trigger")
    return config


def number(value, default=0.0):
    try:
        result = float(value)
        return result if math.isfinite(result) else default
    except (ValueError, TypeError):
        return default


def true_ranges(candles):
    return [max(c["high"] - c["low"], abs(c["high"] - p["close"]), abs(c["low"] - p["close"]))
            for p, c in zip(candles, candles[1:])]


def closed_history(snapshot):
    candles = snapshot.get("candle_history", [])
    if not isinstance(candles, list):
        return []
    result = []
    for raw in candles:
        if not isinstance(raw, dict):
            return []
        c = {k: number(raw.get(k), float("nan")) for k in ("open", "high", "low", "close")}
        if any(not math.isfinite(v) or v <= 0 for v in c.values()) or c["low"] > min(c["open"], c["close"]) or c["high"] < max(c["open"], c["close"]):
            return []
        result.append({**raw, **c})
    # A stale/partial history must never act as the latest confirmation.
    if not result or result[-1].get("candle_time") != snapshot.get("candle_time"):
        return []
    times = [str(c.get("candle_time", "")) for c in result]
    if not all(a < b for a, b in zip(times, times[1:])):
        return []
    return result


def collect_levels(frames, structure):
    """Keep provenance; copies of previous-day/Fib levels are not independent votes."""
    levels = []
    for tf in ("M15", "M30", "H1", "H4", "D1"):
        raw = frames.get(tf, {}).get("levels") or {}
        if not isinstance(raw, dict):
            continue
        candidates = [(k, raw.get(k), "structure" if k in {"support", "resistance"} else "fvg" if "fvg" in k else "previous_day") for k in ("support", "resistance", "previous_day_high", "previous_day_low", "bullish_fvg", "bearish_fvg")]
        fib = raw.get("fib") or {}
        if not isinstance(fib, dict):
            fib = {}
        for ratio in ("50.0", "61.8", "78.6"):
            candidates.append(("fib_" + ratio, fib.get(ratio), "fib"))
        for swing in structure.get(tf, {}).get("swings", []):
            if swing.get("valid", True) and not swing.get("broken"):
                candidates.append(("swing_" + swing.get("type", ""), swing.get("price"), "structure"))
        for label, value, family in candidates:
            if isinstance(value, dict):
                low = number(value.get("low", value.get("price", value.get("value"))))
                high = number(value.get("high", low))
            else:
                low = high = number(value)
            if low > 0 and high >= low:
                levels.append({"timeframe": tf, "label": label, "family": family, "low": low, "high": high})
    return levels


def grade(score):
    return "A+" if score >= 80 else "A" if score >= 70 else "B" if score >= 60 else "NO TRADE"


def evaluate(frames, structure, symbol, now, session, config, quote=None):
    """Return one best setup or explicit rejection. Quotes include spread in planned R."""
    base = {"symbol": symbol, "result": "FAIL", "direction": "WAIT", "score": 0, "grade": "NO TRADE",
            "session": session, "evaluated_at": now, "reason": "", "warnings": [], "confluence": [],
            "structure": {tf: structure.get(tf, {}).get("trend", "unknown") for tf in ("H4", "H1", "M30")}}

    def reject(reason):
        return {**base, "reason": "NO TRADE: " + reason}

    for tf in ("H4", "H1", "M30", *config["entry_timeframes"]):
        snap = frames.get(tf, {})
        age = now - number(snap.get("closed_at"))
        if not snap or age < 0 or age > FRAME_SECONDS[tf] + config["freshness_grace_seconds"] or now - number(snap.get("received_at")) > FRAME_SECONDS[tf] + config["freshness_grace_seconds"]:
            return reject(f"Stale or missing {tf} closed-candle data")
    trends = base["structure"]
    for bias in ("bullish", "bearish"):
        if list(trends.values()).count(bias) >= config["htf_min_aligned"]:
            break
    else:
        return reject("HTF ranging/uncertain or conflicting structure")
    opposite = "bearish" if bias == "bullish" else "bullish"
    if opposite in trends.values() or (config["require_h1"] and trends["H1"] != bias):
        return reject("H1/H4/M30 structure conflicts with direction")
    direction, sign = ("BUY", 1) if bias == "bullish" else ("SELL", -1)
    base.update(direction=direction, htf_bias=bias)
    if session not in config["allowed_sessions"]:
        return reject("Session restricted: " + session)
    quote = quote if quote is not None else frames.get("M1", {})
    bid, ask = number(quote.get("bid")), number(quote.get("ask"))
    if bid <= 0 or ask < bid or not 0 <= now - number(quote.get("received_at")) <= config["quote_max_age_seconds"]:
        return reject("Stale or invalid execution quote")
    entry = ask if sign == 1 else bid
    levels = collect_levels(frames, structure)
    candidates = [_setup(frames, levels, tf, entry, ask - bid, sign, base, config, quote)
                  for tf in config["entry_timeframes"]]
    return max(candidates, key=lambda item: (item["result"] == "PASS", item["score"]))


def _setup(frames, levels, tf, entry, spread, sign, base, cfg, quote):
    plan = {**base, "timeframe": tf, "entry": entry, "confluence": [], "warnings": []}
    def reject(reason):
        return {**plan, "result": "FAIL", "reason": "NO TRADE: " + reason}
    snapshot = frames[tf]
    candles = closed_history(snapshot)
    period = cfg["atr_period"]
    if len(candles) < 2 * period + 2:
        return reject(f"Incomplete {tf} ATR/confirmation history")
    ranges = true_ranges(candles[:-1])  # exclude the signal candle from its own expansion benchmark
    atr = mean(ranges[-period:])
    baseline = mean(ranges[-2 * period:-period])
    if atr <= 0 or baseline <= 0:
        return reject("Invalid ATR")
    ratio = atr / baseline
    plan.update(atr=atr, volatility_ratio=ratio, volatility="low" if ratio < cfg["atr_min_ratio"] else "extreme" if ratio > cfg["atr_max_ratio"] else "elevated" if ratio > 1 else "normal")
    if not cfg["atr_min_ratio"] <= ratio <= cfg["atr_max_ratio"]:
        return reject("Abnormal volatility")
    c, previous = candles[-1], candles[-2]
    if max(true_ranges(candles[-3:])) > atr * cfg["expansion_max_atr"]:
        return reject("Extreme candle expansion; wait for a later retest")
    ema20, ema50 = number(snapshot.get("ema20")), number(snapshot.get("ema50"))
    if min(ema20, ema50) <= 0:
        return reject("EMA data missing")
    extension = abs(entry - ema20) / atr
    plan["extension_atr"] = extension
    if extension > cfg["extension_max_atr"]:
        return reject(f"Price extended {extension:.2f} ATR from EMA20")
    if spread > atr * cfg["spread_max_atr"]:
        return reject("Spread too large relative to ATR")
    if abs(entry - c["close"]) > atr * cfg["execution_tolerance_atr"]:
        return reject("Execution quote has moved away from the confirmation close")
    if any(l["low"] <= entry <= l["high"] and l["label"] == ("bearish_fvg" if sign == 1 else "bullish_fvg") for l in levels):
        return reject("Entry is inside an opposing FVG; no clear room")
    tolerance = atr * cfg["location_max_atr"]
    near = [level for level in levels if min(abs(entry - level["low"]), abs(entry - level["high"])) <= tolerance
            and (level["high"] < entry if sign == 1 else level["low"] > entry)
            and c["low"] <= level["high"] + atr * cfg["level_cluster_atr"]
            and c["high"] >= level["low"] - atr * cfg["level_cluster_atr"]]
    if not near:
        return reject("No meaningful level at the confirmation candle")
    # Direction-aware geometry is shared for pullback and retest confirmation.
    span = c["high"] - c["low"]
    close_location = ((c["close"] - c["low"]) if sign == 1 else (c["high"] - c["close"])) / span if span else 0
    confirmed = (sign * (c["close"] - c["open"]) > 0 and span > 0
                 and abs(c["close"] - c["open"]) / span >= cfg["confirmation_body_ratio"]
                 and close_location >= cfg["confirmation_close_location"]
                 and sign * (c["close"] - previous["close"]) > 0)
    if not confirmed:
        return reject("No closed-candle rejection/reclaim confirmation")
    selected, kind = None, None
    for level in sorted(near, key=lambda l: abs(entry - (l["high"] if sign == 1 else l["low"]))):
        edge = level["high"] if sign == 1 else level["low"]
        recent = candles[-cfg["retest_lookback"] - 1:-1]
        breaks = [i for i in range(1, len(recent)) if sign * (recent[i - 1]["close"] - edge) <= 0
                  and sign * (recent[i]["close"] - edge) > atr * cfg["break_buffer_atr"]
                  and sign * (recent[i]["close"] - recent[i]["open"]) > 0
                  and abs(recent[i]["close"] - recent[i]["open"]) >= (recent[i]["high"] - recent[i]["low"]) * cfg["confirmation_body_ratio"]]
        held = breaks and all(sign * (bar["close"] - edge) >= -atr * cfg["break_buffer_atr"] for bar in recent[breaks[-1]:])
        if held and sign * (c["close"] - edge) > 0 and "breakout_retest" in cfg["enabled_setups"]:
            selected, kind = level, "breakout_retest"
            break
        pulled_back = sign * (recent[-1]["close"] - recent[0]["close"]) < 0
        supportive = level["label"] not in ({"resistance", "swing_high", "previous_day_high", "bearish_fvg"} if sign == 1 else {"support", "swing_low", "previous_day_low", "bullish_fvg"})
        if pulled_back and supportive and sign * (ema20 - ema50) > 0 and "pullback" in cfg["enabled_setups"]:
            selected, kind = level, "pullback"
            break
    if not selected:
        return reject("No pullback ending or confirmed breakout/retest sequence")
    edge = selected["low"] if sign == 1 else selected["high"]
    swing = min(bar["low"] for bar in candles[-cfg["retest_lookback"]:]) if sign == 1 else max(bar["high"] for bar in candles[-cfg["retest_lookback"]:])
    invalidation = min(edge, swing) if sign == 1 else max(edge, swing)
    risk = max(sign * (entry - invalidation) + atr * cfg["sl_buffer_atr"], atr * cfg["sl_min_atr"])
    tick = number(quote.get("tick_size"), 10 ** -int(snapshot.get("digits", 5)))
    if tick <= 0:
        return reject("Invalid broker tick size")
    sl = (math.floor if sign == 1 else math.ceil)((entry - sign * risk) / tick) * tick
    opposing = sorted({level["low"] if sign == 1 else level["high"] for level in levels
                       if (level["low"] >= entry if sign == 1 else level["high"] <= entry)}, reverse=sign == -1)
    if not opposing:
        return reject("No observable structural target")
    tp = (math.floor if sign == 1 else math.ceil)((opposing[0] - sign * atr * cfg["target_buffer_atr"]) / tick) * tick
    risk = sign * (entry - sl)
    rr = sign * (tp - entry) / risk
    if sl <= 0 or tp <= 0:
        return reject("Invalid nonpositive bracket price")
    plan.update(setup_type=kind, level=selected, relevant_levels=near, invalidation=invalidation, sl=sl, tp=tp,
                initial_risk=risk, planned_rr=rr, opposing_level=opposing[0], confirmation="closed rejection/reclaim" if kind == "pullback" else "closed breakout then retest",
                rsi=snapshot.get("rsi14"), ema={k: snapshot.get(k) for k in ("ema20", "ema50", "ema100", "ema200")})
    if rr < cfg["min_rr"]:
        return reject(f"Opposing level allows {rr:.2f}R; required {cfg['min_rr']:.2f}R")
    if min(risk, sign * (tp - entry)) < number(quote.get("stops_distance")) + spread:
        return reject("Bracket is inside broker minimum stop distance")
    w = cfg["weights"]
    evidence = {tf.lower(): w[tf.lower()] for tf, trend in base["structure"].items() if trend == base["htf_bias"]}
    evidence.update(location=w["location"], confirmation=w["confirmation"], rr=w["rr"])
    # EMA slope follows the EMA recurrence; optional longer EMAs supply extra votes.
    ema_votes = [sign * (ema20 - ema50) > 0, sign * (c["close"] - ema20) > 0]
    m5 = frames.get("M5", {})
    ema_votes.append(sign * (number(m5.get("close"), c["close"]) - number(m5.get("ema20"))) > 0)
    for short, long in (("ema50", "ema100"), ("ema100", "ema200")):
        if number(snapshot.get(short)) > 0 and number(snapshot.get(long)) > 0:
            ema_votes.append(sign * (number(snapshot[short]) - number(snapshot[long])) > 0)
    evidence["ema"] = round(w["ema"] * sum(ema_votes) / len(ema_votes), 2)
    plan["ema"]["slope20"] = (number(c["close"]) - ema20) * (2 / 21) / (1 - 2 / 21)
    families = {l["family"] for l in near if abs(l["low"] - selected["low"]) <= atr * cfg["level_cluster_atr"]}
    if len(families) > 1:
        evidence["confluence"] = w["confluence"]
    rsi = number(snapshot.get("rsi14"), -1)
    previous_rsi = number(previous.get("rsi14"), rsi)
    if 0 <= rsi <= 100 and ((sign == 1 and rsi >= cfg["rsi_buy_min"] and rsi >= previous_rsi) or (sign == -1 and rsi <= cfg["rsi_sell_max"] and rsi <= previous_rsi)):
        evidence["rsi"] = w["rsi"]
    if "ranging" in base["structure"].values():
        evidence["range_penalty"] = -w["range_penalty"]
        plan["warnings"].append("One HTF is ranging")
    if base["session"] == "Outside":
        evidence["weak_session_penalty"] = -w["weak_session_penalty"]
        plan["warnings"].append("Outside major sessions; liquidity not verified")
    score = min(100, max(0, sum(evidence.values())))
    plan.update(score=score, grade=grade(score), score_evidence=evidence,
                confluence=[key for key, value in evidence.items() if value > 0])
    if score < cfg["min_score"]:
        return reject(f"Score {score} < required {cfg['min_score']}")
    # Stable daily level thesis prevents a new candle from bypassing attempt limits.
    level_bucket = round(edge / max(atr * cfg["level_cluster_atr"], tick))
    thesis = f"{base['symbol']}:{base['direction']}:{level_bucket}"
    identity = f"{thesis}:{tf}:{kind}:{snapshot['candle_time']}"
    plan.update(result="PASS", reason=f"{kind}: HTF → location → confirmation → score → R:R",
                setup_id=hashlib.sha256(identity.encode()).hexdigest()[:16], thesis=thesis,
                candle_time=snapshot["candle_time"], expires_at=base["evaluated_at"] + cfg["plan_ttl_seconds"],
                management={k: cfg[k] for k in ("breakeven_r", "protect_r", "protect_lock_r", "partial_close_r", "partial_fraction", "trail_start_r", "trailing_method")})
    return plan
