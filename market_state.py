"""Persistent latest-state storage for market snapshots."""

import html
import json
import math
import os
import threading
from pathlib import Path

from json_data_parser import SUPPORTED_EVENTS, display_symbol


TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4")
EMA_TIMEFRAMES = TIMEFRAMES[:2]
PATTERN_TIMEFRAMES = TIMEFRAMES[2:]


def _number(value, field):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field} must be numeric")
    value = float(value)
    if not math.isfinite(value):
        raise ValueError(f"{field} must be finite")
    return value


def _optional_number(value, field):
    return None if value is None else _number(value, field)


def _zone(value, field):
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"{field} must be an object or null")
    low = _number(value.get("low"), f"{field}.low")
    high = _number(value.get("high"), f"{field}.high")
    if low >= high:
        raise ValueError(f"{field}.low must be below high")
    return {"low": low, "high": high}


def _fib(value):
    if value is None:
        return None
    if not isinstance(value, dict) or value.get("direction") not in ("UP", "DOWN"):
        raise ValueError("levels.fib must contain direction UP or DOWN")
    return {
        "direction": value["direction"],
        **{
            key: _number(value.get(key), f"levels.fib.{key}")
            for key in ("start", "end", "38.2", "50.0", "61.8")
        },
    }


def validate_snapshot(payload):
    if not isinstance(payload, dict):
        raise ValueError("snapshot payload must be a JSON object")
    if payload.get("event_type") != "TIMEFRAME_SNAPSHOT":
        raise ValueError("event_type must be TIMEFRAME_SNAPSHOT")

    symbol = display_symbol(payload.get("symbol"))
    timeframe = str(payload.get("timeframe", "")).upper()
    candle_time = str(payload.get("candle_time", "")).strip()
    if not symbol:
        raise ValueError("snapshot symbol is required")
    if timeframe not in TIMEFRAMES:
        raise ValueError(f"unsupported snapshot timeframe: {timeframe or 'missing'}")
    if not candle_time:
        raise ValueError("snapshot candle_time is required")

    digits = payload.get("digits", 5)
    if isinstance(digits, bool) or not isinstance(digits, int) or not 0 <= digits <= 10:
        raise ValueError("digits must be an integer from 0 to 10")
    notify_patterns = payload.get("notify_patterns", True)
    if not isinstance(notify_patterns, bool):
        raise ValueError("notify_patterns must be boolean")

    snapshot = {
        "symbol": symbol.upper(),
        "timeframe": timeframe,
        "candle_time": candle_time,
        "digits": digits,
        "notify_patterns": notify_patterns,
        **{
            key: _number(payload.get(key), key)
            for key in ("open", "high", "low", "close")
        },
    }

    if timeframe in EMA_TIMEFRAMES:
        snapshot["ema20"] = _number(payload.get("ema20"), "ema20")
        snapshot["ema50"] = _number(payload.get("ema50"), "ema50")
        snapshot["ema_bias"] = (
            "BULLISH"
            if snapshot["ema20"] > snapshot["ema50"]
            else "BEARISH"
            if snapshot["ema20"] < snapshot["ema50"]
            else "NEUTRAL"
        )
        snapshot["patterns"] = []
        return snapshot

    patterns = payload.get("patterns", [])
    if not isinstance(patterns, list):
        raise ValueError("patterns must be a list")
    snapshot["patterns"] = []
    for pattern in patterns:
        if not isinstance(pattern, dict):
            raise ValueError("each pattern must be an object")
        event_type = pattern.get("event_type")
        signal = str(pattern.get("signal", "")).upper()
        if event_type not in SUPPORTED_EVENTS:
            raise ValueError(f"unsupported pattern event_type: {event_type}")
        if signal not in ("BUY", "SELL"):
            raise ValueError("pattern signal must be BUY or SELL")
        snapshot["patterns"].append({"event_type": event_type, "signal": signal})

    levels = payload.get("levels")
    if not isinstance(levels, dict):
        raise ValueError("levels must be an object")
    snapshot["levels"] = {
        "support": _optional_number(levels.get("support"), "levels.support"),
        "resistance": _optional_number(levels.get("resistance"), "levels.resistance"),
        "fib": _fib(levels.get("fib")),
        "bullish_fvg": _zone(levels.get("bullish_fvg"), "levels.bullish_fvg"),
        "bearish_fvg": _zone(levels.get("bearish_fvg"), "levels.bearish_fvg"),
        "previous_day_high": _optional_number(
            levels.get("previous_day_high"), "levels.previous_day_high"
        ),
        "previous_day_low": _optional_number(
            levels.get("previous_day_low"), "levels.previous_day_low"
        ),
    }
    return snapshot


class MarketState:
    def __init__(self, path=None):
        default = Path(__file__).with_name("market_state.json")
        self.path = Path(path or os.environ.get("STATE_FILE", default))
        self.lock = threading.Lock()
        self.data = self._load()

    def _load(self):
        if not self.path.exists():
            return {"symbols": {}}
        with self.path.open(encoding="utf-8") as file:
            data = json.load(file)
        if not isinstance(data, dict) or not isinstance(data.get("symbols"), dict):
            raise ValueError(f"invalid market state file: {self.path}")
        return data

    def _save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as file:
            json.dump(self.data, file, ensure_ascii=False, separators=(",", ":"))
        os.replace(temporary, self.path)

    def update(self, payload):
        snapshot = validate_snapshot(payload)
        timeframe = snapshot["timeframe"]
        notifications = []
        with self.lock:
            timeframes = self.data["symbols"].setdefault(snapshot["symbol"], {})
            previous = timeframes.get(timeframe, {})
            same_candle = previous.get("candle_time") == snapshot["candle_time"]
            notified = set(previous.get("notified_patterns", [])) if same_candle else set()
            retained = previous.get("retained_patterns", [])

            if snapshot["patterns"]:
                retained = [
                    {
                        **pattern,
                        "candle_time": snapshot["candle_time"],
                        "invalidated": False,
                    }
                    for pattern in snapshot["patterns"]
                ]
            snapshot["retained_patterns"] = retained
            if not snapshot["notify_patterns"]:
                notified.update(self._pattern_key(pattern) for pattern in snapshot["patterns"])
            snapshot["notified_patterns"] = sorted(notified)
            timeframes[timeframe] = snapshot

            if snapshot["patterns"]:
                self._invalidate_patterns(timeframes, timeframe)
                if snapshot["notify_patterns"]:
                    notifications = [
                        {
                            **{
                                key: snapshot[key]
                                for key in (
                                    "symbol",
                                    "timeframe",
                                    "candle_time",
                                    "open",
                                    "high",
                                    "low",
                                    "close",
                                )
                            },
                            **pattern,
                        }
                        for pattern in snapshot["patterns"]
                        if self._pattern_key(pattern) not in notified
                    ]
            self._save()
        return notifications

    def mark_notified(self, notification):
        symbol = display_symbol(notification.get("symbol")).upper()
        timeframe = str(notification.get("timeframe", "")).upper()
        candle_time = str(notification.get("candle_time", ""))
        key = self._pattern_key(notification)
        with self.lock:
            snapshot = self.data["symbols"].get(symbol, {}).get(timeframe)
            if not snapshot or snapshot.get("candle_time") != candle_time:
                return
            notified = set(snapshot.get("notified_patterns", []))
            notified.add(key)
            snapshot["notified_patterns"] = sorted(notified)
            self._save()

    @staticmethod
    def _pattern_key(pattern):
        return f"{pattern.get('event_type')}:{pattern.get('signal')}"

    def _invalidate_patterns(self, timeframes, updated_timeframe):
        updated_index = TIMEFRAMES.index(updated_timeframe)
        updated = timeframes[updated_timeframe]
        updated_patterns = updated.get("retained_patterns", [])

        for lower_timeframe in TIMEFRAMES[2:updated_index]:
            lower = timeframes.get(lower_timeframe)
            if not lower:
                continue
            for lower_pattern in lower.get("retained_patterns", []):
                if (
                    not lower_pattern.get("invalidated")
                    and updated["candle_time"] > lower_pattern["candle_time"]
                    and any(
                        pattern["signal"] != lower_pattern["signal"]
                        for pattern in updated_patterns
                        if not pattern.get("invalidated")
                    )
                ):
                    lower_pattern["invalidated"] = True

        for pattern in updated_patterns:
            if pattern.get("invalidated"):
                continue
            for higher_timeframe in TIMEFRAMES[updated_index + 1 :]:
                higher = timeframes.get(higher_timeframe)
                if not higher:
                    continue
                if higher["candle_time"] <= pattern["candle_time"]:
                    continue
                if any(
                    higher_pattern["signal"] != pattern["signal"]
                    for higher_pattern in higher.get("retained_patterns", [])
                    if not higher_pattern.get("invalidated")
                ):
                    pattern["invalidated"] = True
                    break

    def summary(self, symbol):
        symbol = display_symbol(symbol).upper()
        with self.lock:
            timeframes = self.data["symbols"].get(symbol)
            if not timeframes:
                return f"<b>{html.escape(symbol)}</b>\nAwaiting data"

            lines = [f"📊 <b>{html.escape(symbol)} Market Summary</b>"]
            for timeframe in EMA_TIMEFRAMES:
                snapshot = timeframes.get(timeframe)
                lines.append(f"\n<b>{timeframe}</b>")
                if not snapshot:
                    lines.append("Awaiting data")
                    continue
                bias = snapshot["ema_bias"].title()
                lines.append(
                    f"EMA20 / EMA50: <code>{self._price(snapshot['ema20'], snapshot)}</code>"
                    f" / <code>{self._price(snapshot['ema50'], snapshot)}</code>"
                )
                lines.append(f"Bias: <b>{bias}</b>")

            for timeframe in PATTERN_TIMEFRAMES:
                snapshot = timeframes.get(timeframe)
                lines.append(f"\n<b>{timeframe}</b>")
                if not snapshot:
                    lines.append("Awaiting data")
                    continue
                patterns = snapshot.get("retained_patterns", [])
                if not patterns:
                    lines.append("No retained pattern")
                    continue
                for pattern in patterns:
                    direction = "Bullish" if pattern["signal"] == "BUY" else "Bearish"
                    status = " (invalidated)" if pattern.get("invalidated") else ""
                    lines.append(
                        f"{SUPPORTED_EVENTS[pattern['event_type']]} — "
                        f"{direction}{status}"
                    )
                    lines.append(f"<i>{html.escape(pattern['candle_time'])}</i>")

            suggestion, reason = self._suggestion(timeframes)
            lines.extend(
                [
                    "",
                    f"<b>Suggestion: {suggestion}</b>",
                    html.escape(reason),
                ]
            )
            return "\n".join(lines)

    def _suggestion(self, timeframes):
        ema_biases = [
            timeframes.get(timeframe, {}).get("ema_bias")
            for timeframe in EMA_TIMEFRAMES
        ]
        signals = {
            pattern["signal"]
            for timeframe in PATTERN_TIMEFRAMES
            for pattern in timeframes.get(timeframe, {}).get("retained_patterns", [])
            if not pattern.get("invalidated")
        }
        if ema_biases == ["BULLISH", "BULLISH"] and signals == {"BUY"}:
            return "BUY", "M1/M5 EMA and active higher-timeframe patterns align."
        if ema_biases == ["BEARISH", "BEARISH"] and signals == {"SELL"}:
            return "SELL", "M1/M5 EMA and active higher-timeframe patterns align."
        if None in ema_biases:
            return "WAIT", "M1/M5 EMA data is incomplete."
        if ema_biases[0] != ema_biases[1] or "NEUTRAL" in ema_biases:
            return "WAIT", "M1/M5 EMA trends are not aligned."
        if not signals:
            return "WAIT", "No active M15-H4 pattern confirmation."
        return "WAIT", "EMA and higher-timeframe pattern directions conflict."

    def levels(self, symbol):
        symbol = display_symbol(symbol).upper()
        with self.lock:
            timeframes = self.data["symbols"].get(symbol)
            if not timeframes:
                return f"<b>{html.escape(symbol)}</b>\nAwaiting data"

            lines = [f"🧭 <b>{html.escape(symbol)} Key Levels</b>"]
            previous_day = None
            for timeframe in PATTERN_TIMEFRAMES:
                snapshot = timeframes.get(timeframe)
                lines.append(f"\n<b>{timeframe}</b>")
                if not snapshot:
                    lines.append("Awaiting data")
                    continue
                levels = snapshot["levels"]
                lines.append(
                    f"Support: {self._level(levels['support'], snapshot)}"
                    f" | Resistance: {self._level(levels['resistance'], snapshot)}"
                )
                fib = levels["fib"]
                if fib:
                    lines.append(
                        "Fib 38.2/50/61.8: "
                        + " / ".join(
                            f"<code>{self._price(fib[key], snapshot)}</code>"
                            for key in ("38.2", "50.0", "61.8")
                        )
                        + f" ({fib['direction']})"
                    )
                else:
                    lines.append("Fibonacci: None found")
                lines.append(
                    "Bullish FVG: "
                    + self._format_zone(levels["bullish_fvg"], snapshot)
                )
                lines.append(
                    "Bearish FVG: "
                    + self._format_zone(levels["bearish_fvg"], snapshot)
                )
                if (
                    previous_day is None
                    and levels["previous_day_high"] is not None
                    and levels["previous_day_low"] is not None
                ):
                    previous_day = (
                        levels["previous_day_high"],
                        levels["previous_day_low"],
                        snapshot,
                    )

            lines.append("")
            if previous_day:
                high, low, snapshot = previous_day
                lines.append(
                    "PDH / PDL: "
                    f"<code>{self._price(high, snapshot)}</code> / "
                    f"<code>{self._price(low, snapshot)}</code>"
                )
            else:
                lines.append("PDH / PDL: None found")
            return "\n".join(lines)

    def _level(self, value, snapshot):
        return (
            "None found"
            if value is None
            else f"<code>{self._price(value, snapshot)}</code>"
        )

    def _format_zone(self, zone, snapshot):
        if zone is None:
            return "None found"
        return (
            f"<code>{self._price(zone['low'], snapshot)}</code>–"
            f"<code>{self._price(zone['high'], snapshot)}</code>"
        )

    @staticmethod
    def _price(value, snapshot):
        return f"{value:.{snapshot['digits']}f}"
