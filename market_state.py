"""Persistent latest-state storage for market snapshots."""

import html
import json
import math
import os
import threading
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from json_data_parser import SUPPORTED_EVENTS, display_symbol, display_time


TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4")
EMA_TIMEFRAMES = TIMEFRAMES[:2]
PATTERN_TIMEFRAMES = TIMEFRAMES[2:]
RSI_TIMEFRAMES = ("M5", "M15", "M30", "H1", "H4")
RSI_LOOKBACKS = {"M5": 30, "M15": 30, "M30": 10, "H1": 10, "H4": 10}
CHART_CANDLE_LOOKBACK = 60


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

    if payload.get("rsi14") is not None:
        snapshot["rsi14"] = _number(payload.get("rsi14"), "rsi14")

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

            if "rsi14" in snapshot:
                history = list(previous.get("rsi_history", []))
                current_entry = {
                    "candle_time": snapshot["candle_time"],
                    "rsi14": snapshot["rsi14"],
                }
                if history and history[-1].get("candle_time") == snapshot["candle_time"]:
                    history[-1] = current_entry
                else:
                    history.append(current_entry)
                snapshot["rsi_history"] = history[-max(RSI_LOOKBACKS.values()):]
            elif previous.get("rsi_history"):
                snapshot["rsi_history"] = previous["rsi_history"]

            candle_history = list(previous.get("candle_history", []))
            current_candle = {
                "candle_time": snapshot["candle_time"],
                "open": snapshot["open"],
                "high": snapshot["high"],
                "low": snapshot["low"],
                "close": snapshot["close"],
            }
            if candle_history and candle_history[-1].get("candle_time") == snapshot["candle_time"]:
                candle_history[-1] = current_candle
            else:
                candle_history.append(current_candle)
            snapshot["candle_history"] = candle_history[-CHART_CANDLE_LOOKBACK:]

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
                    lines.append(f"<i>{html.escape(display_time(pattern['candle_time']))}</i>")

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

    def rsi_summary(self, symbol):
        symbol = display_symbol(symbol).upper()
        with self.lock:
            timeframes = self.data["symbols"].get(symbol)
            if not timeframes:
                return f"<b>{html.escape(symbol)}</b>\nAwaiting RSI data"

            lines = [f"📈 <b>{html.escape(symbol)} RSI(14)</b>"]
            for timeframe in RSI_TIMEFRAMES:
                snapshot = timeframes.get(timeframe)
                lines.append(f"\n<b>{timeframe}</b>")
                if not snapshot or "rsi14" not in snapshot:
                    lines.append("Awaiting data")
                    continue

                rsi = snapshot["rsi14"]
                status = "Overbought" if rsi >= 70 else "Oversold" if rsi <= 30 else "Neutral"
                lines[-1] = f"<b>{timeframe}</b>: <code>{rsi:.2f}</code> — {status}"
                history = snapshot.get("rsi_history", [])[-RSI_LOOKBACKS[timeframe]:]
                above = [entry for entry in history if entry.get("rsi14", 0) >= 70]
                below = [entry for entry in history if entry.get("rsi14", 100) <= 30]
                if above:
                    latest = above[-1]
                    lines.append(
                        "Closed above 70: "
                        f"<code>{latest['rsi14']:.2f}</code> at "
                        f"<i>{html.escape(display_time(latest['candle_time']))}</i>"
                    )
                if below:
                    latest = below[-1]
                    lines.append(
                        "Closed below 30: "
                        f"<code>{latest['rsi14']:.2f}</code> at "
                        f"<i>{html.escape(display_time(latest['candle_time']))}</i>"
                    )
                if not above and not below:
                    lines.append(
                        f"No 70/30 extreme in last {RSI_LOOKBACKS[timeframe]} candles"
                    )
            return "\n".join(lines)

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

    def levels_chart(self, symbol, output_path):
        symbol = display_symbol(symbol).upper()
        output_path = Path(output_path)
        with self.lock:
            timeframes = self.data["symbols"].get(symbol)
            if not timeframes:
                return None
            chart_items, prices, latest_snapshot, candles, candle_timeframe = self._chart_items(timeframes)

        if not latest_snapshot or not prices:
            return None

        width, height = 1100, 760
        margin_left, margin_right, margin_top, margin_bottom = 90, 280, 70, 70
        plot_left, plot_right = margin_left, width - margin_right
        plot_top, plot_bottom = margin_top, height - margin_bottom
        low, high = min(prices), max(prices)
        padding = max((high - low) * 0.12, latest_snapshot["close"] * 0.002, 1)
        low -= padding
        high += padding

        def y_for(price):
            return int(plot_bottom - ((price - low) / (high - low)) * (plot_bottom - plot_top))

        image = Image.new("RGB", (width, height), "#0f172a")
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()
        draw.rectangle([plot_left, plot_top, plot_right, plot_bottom], outline="#334155", width=2)
        draw.text((margin_left, 24), f"{symbol} Key Levels", fill="#f8fafc", font=font)
        draw.text(
            (margin_left, 44),
            f"Latest {latest_snapshot['timeframe']} close: {self._price(latest_snapshot['close'], latest_snapshot)} at {display_time(latest_snapshot['candle_time'])}",
            fill="#cbd5e1",
            font=font,
        )
        if candles:
            draw.text(
                (margin_left, 60),
                f"Candlesticks: recent {candle_timeframe} candles from EA snapshots",
                fill="#94a3b8",
                font=font,
            )

        for tick in range(6):
            price = low + (high - low) * tick / 5
            y = y_for(price)
            draw.line([plot_left, y, plot_right, y], fill="#1e293b")
            draw.text((12, y - 6), self._price(price, latest_snapshot), fill="#94a3b8", font=font)

        current_y = y_for(latest_snapshot["close"])
        draw.line([plot_left, current_y, plot_right, current_y], fill="#f8fafc", width=3)
        draw.text((plot_right + 8, current_y - 8), "Current", fill="#f8fafc", font=font)

        colors = {
            "support": "#22c55e",
            "resistance": "#ef4444",
            "fib": "#38bdf8",
            "previous_day": "#f59e0b",
            "bullish_fvg": "#16a34a",
            "bearish_fvg": "#dc2626",
        }
        labels = []
        for item in chart_items:
            color = colors[item["kind"]]
            if "low" in item:
                y1, y2 = y_for(item["high"]), y_for(item["low"])
                draw.rectangle([plot_left, y1, plot_right, y2], fill=color, outline=color)
                draw.line([plot_left, y1, plot_right, y1], fill="#e2e8f0", width=1)
                draw.line([plot_left, y2, plot_right, y2], fill="#e2e8f0", width=1)
                label_y = (y1 + y2) // 2
                label = f"{item['label']} {self._price(item['low'], latest_snapshot)}-{self._price(item['high'], latest_snapshot)}"
            else:
                label_y = y_for(item["price"])
                draw.line([plot_left, label_y, plot_right, label_y], fill=color, width=2)
                label = f"{item['label']} {self._price(item['price'], latest_snapshot)}"
            labels.append((label_y, label))

        if candles:
            self._draw_candles(draw, candles, plot_left, plot_right, y_for)

        labels.sort(key=lambda entry: entry[0])
        next_y = plot_top
        for label_y, label in labels:
            adjusted_y = max(label_y - 7, next_y)
            adjusted_y = min(adjusted_y, plot_bottom - 12)
            draw.text((plot_right + 8, adjusted_y), label, fill="#f8fafc", font=font)
            next_y = adjusted_y + 14

        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path, "PNG")
        return output_path

    def _chart_items(self, timeframes):
        items = []
        prices = []
        latest_snapshot = None
        previous_day_added = False
        for timeframe in PATTERN_TIMEFRAMES:
            snapshot = timeframes.get(timeframe)
            if not snapshot:
                continue
            latest_snapshot = snapshot if latest_snapshot is None or snapshot["candle_time"] > latest_snapshot["candle_time"] else latest_snapshot
            prices.extend([snapshot["open"], snapshot["high"], snapshot["low"], snapshot["close"]])
            levels = snapshot["levels"]
            for key, label, kind in (
                ("support", f"{timeframe} Support", "support"),
                ("resistance", f"{timeframe} Resistance", "resistance"),
            ):
                value = levels.get(key)
                if value is not None:
                    items.append({"kind": kind, "label": label, "price": value})
                    prices.append(value)
            if not previous_day_added:
                previous_day_high = levels.get("previous_day_high")
                previous_day_low = levels.get("previous_day_low")
                if previous_day_high is not None and previous_day_low is not None:
                    items.append({"kind": "previous_day", "label": "PDH", "price": previous_day_high})
                    items.append({"kind": "previous_day", "label": "PDL", "price": previous_day_low})
                    prices.extend([previous_day_high, previous_day_low])
                    previous_day_added = True
            fib = levels.get("fib")
            if fib:
                for key in ("38.2", "50.0", "61.8"):
                    items.append({"kind": "fib", "label": f"{timeframe} Fib {key}", "price": fib[key]})
                    prices.append(fib[key])
            for key, label, kind in (
                ("bullish_fvg", f"{timeframe} Bull FVG", "bullish_fvg"),
                ("bearish_fvg", f"{timeframe} Bear FVG", "bearish_fvg"),
            ):
                zone = levels.get(key)
                if zone:
                    items.append({"kind": kind, "label": label, "low": zone["low"], "high": zone["high"]})
                    prices.extend([zone["low"], zone["high"]])
        candles, candle_timeframe = self._chart_candles(timeframes)
        for candle in candles:
            prices.extend([candle["open"], candle["high"], candle["low"], candle["close"]])
        return items, prices, latest_snapshot, candles, candle_timeframe

    def _chart_candles(self, timeframes):
        for timeframe in PATTERN_TIMEFRAMES:
            snapshot = timeframes.get(timeframe)
            if not snapshot:
                continue
            history = snapshot.get("candle_history") or [
                {
                    "candle_time": snapshot["candle_time"],
                    "open": snapshot["open"],
                    "high": snapshot["high"],
                    "low": snapshot["low"],
                    "close": snapshot["close"],
                }
            ]
            return history[-40:], timeframe
        return [], None

    @staticmethod
    def _draw_candles(draw, candles, plot_left, plot_right, y_for):
        count = len(candles)
        if not count:
            return
        span = max(plot_right - plot_left, 1)
        slot = span / count
        body_half_width = max(3, min(11, int(slot * 0.28)))
        for index, candle in enumerate(candles):
            x = int(plot_left + slot * (index + 0.5))
            open_y = y_for(candle["open"])
            high_y = y_for(candle["high"])
            low_y = y_for(candle["low"])
            close_y = y_for(candle["close"])
            bullish = candle["close"] >= candle["open"]
            color = "#14b8a6" if bullish else "#f87171"
            draw.line([x, high_y, x, low_y], fill=color, width=2)
            body_top = min(open_y, close_y)
            body_bottom = max(open_y, close_y)
            if body_top == body_bottom:
                body_bottom += 1
            draw.rectangle(
                [x - body_half_width, body_top, x + body_half_width, body_bottom],
                fill=color,
                outline=color,
            )

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
