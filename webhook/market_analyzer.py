"""Market analysis logic — summary, levels, RSI reports.

Extracted from MarketState to separate analysis from state management.
Receives a MarketState instance and reads its data for read-only reports.
"""

import html

from .json_data_parser import SUPPORTED_EVENTS, display_symbol, display_time
from .market_state import (
    EMA_TIMEFRAMES,
    LEVEL_TIMEFRAMES,
    PATTERN_TIMEFRAMES,
    RSI_LOOKBACKS,
    RSI_TIMEFRAMES,
    _price,
)


class MarketAnalyzer:
    """Read-only analysis over a MarketState's persisted data."""

    def __init__(self, market_state):
        self.state = market_state

    # ------------------------------------------------------------------
    # Multi-timeframe summary
    # ------------------------------------------------------------------

    def summary(self, symbol):
        symbol = display_symbol(symbol).upper()
        with self.state.lock:
            timeframes = self.state.data["symbols"].get(symbol)
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
                    f"EMA20 / EMA50: <code>{_price(snapshot['ema20'], snapshot)}</code>"
                    f" / <code>{_price(snapshot['ema50'], snapshot)}</code>"
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
                    lines.append(
                        f"<i>{html.escape(display_time(pattern['candle_time']))}</i>"
                    )

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
            for pattern in timeframes.get(timeframe, {}).get(
                "retained_patterns", []
            )
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

    # ------------------------------------------------------------------
    # RSI summary
    # ------------------------------------------------------------------

    def rsi_summary(self, symbol):
        symbol = display_symbol(symbol).upper()
        with self.state.lock:
            timeframes = self.state.data["symbols"].get(symbol)
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
                status = (
                    "Overbought"
                    if rsi >= 70
                    else "Oversold"
                    if rsi <= 30
                    else "Neutral"
                )
                lines[-1] = f"<b>{timeframe}</b>: <code>{rsi:.2f}</code> — {status}"
                history = snapshot.get("rsi_history", [])[
                    -RSI_LOOKBACKS[timeframe] :
                ]
                above = [entry for entry in history if entry.get("rsi14", 0) >= 70]
                below = [
                    entry for entry in history if entry.get("rsi14", 100) <= 30
                ]
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

    # ------------------------------------------------------------------
    # Key levels report
    # ------------------------------------------------------------------

    def levels(self, symbol):
        symbol = display_symbol(symbol).upper()
        with self.state.lock:
            timeframes = self.state.data["symbols"].get(symbol)
            if not timeframes:
                return f"<b>{html.escape(symbol)}</b>\nAwaiting data"

            lines = [f"🧭 <b>{html.escape(symbol)} Key Levels</b>"]
            previous_day = None
            for timeframe in LEVEL_TIMEFRAMES:
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
                            f"<code>{_price(fib[key], snapshot)}</code>"
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
                    f"<code>{_price(high, snapshot)}</code> / "
                    f"<code>{_price(low, snapshot)}</code>"
                )
            else:
                lines.append("PDH / PDL: None found")
            return "\n".join(lines)

    # ------------------------------------------------------------------
    # Formatting helpers (read-only, state-free)
    # ------------------------------------------------------------------

    def _level(self, value, snapshot):
        return (
            "None found"
            if value is None
            else f"<code>{_price(value, snapshot)}</code>"
        )

    def _format_zone(self, zone, snapshot):
        if zone is None:
            return "None found"
        return (
            f"<code>{_price(zone['low'], snapshot)}</code>–"
            f"<code>{_price(zone['high'], snapshot)}</code>"
        )
