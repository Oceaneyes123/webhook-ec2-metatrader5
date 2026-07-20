"""Chart rendering for key-level visualisations.

Extracted from MarketState to decouple PIL image generation from state management.
Receives a MarketState instance and reads its data for chart generation.
"""

from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    Image = ImageDraw = ImageFont = None

from .json_data_parser import display_symbol, display_time
from .market_state import CHART_CANDLE_LOOKBACK, PATTERN_TIMEFRAMES, _price


class MarketChart:
    """Renders key-level PNG charts from MarketState data."""

    def __init__(self, market_state):
        self.state = market_state

    def levels_chart(self, symbol, output_path):
        if Image is None:
            return None
        symbol = display_symbol(symbol).upper()
        output_path = Path(output_path)
        with self.state.lock:
            timeframes = self.state.data["symbols"].get(symbol)
            if not timeframes:
                return None
            chart_items, latest_snapshot, candles, candle_timeframe = (
                self._chart_items(timeframes)
            )

        if not latest_snapshot or not candles:
            return None

        width, height = 1100, 760
        margin_left, margin_right, margin_top, margin_bottom = 90, 280, 70, 70
        plot_left, plot_right = margin_left, width - margin_right
        plot_top, plot_bottom = margin_top, height - margin_bottom
        latest_candle = candles[-1]
        low = min(candle["low"] for candle in candles)
        high = max(candle["high"] for candle in candles)
        padding = max(
            (high - low) * 0.15,
            latest_candle["close"] * 0.001,
            1,
        )
        low -= padding
        high += padding

        def y_for(price):
            return int(
                plot_bottom
                - ((price - low) / (high - low)) * (plot_bottom - plot_top)
            )

        image = Image.new("RGB", (width, height), "#0f172a")
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()
        draw.rectangle(
            [plot_left, plot_top, plot_right, plot_bottom], outline="#334155", width=2
        )
        draw.text(
            (margin_left, 24),
            f"{symbol} Key Levels",
            fill="#f8fafc",
            font=font,
        )
        draw.text(
            (margin_left, 44),
            f"Candlestick chart: {candle_timeframe}, latest close "
            f"{_price(latest_candle['close'], latest_snapshot)} at "
            f"{display_time(latest_candle['candle_time'])}",
            fill="#cbd5e1",
            font=font,
        )

        for tick in range(6):
            price = low + (high - low) * tick / 5
            y = y_for(price)
            draw.line([plot_left, y, plot_right, y], fill="#1e293b")
            draw.text(
                (12, y - 6),
                _price(price, latest_snapshot),
                fill="#94a3b8",
                font=font,
            )

        current_y = y_for(latest_candle["close"])
        draw.line(
            [plot_left, current_y, plot_right, current_y], fill="#f8fafc", width=3
        )
        draw.text(
            (plot_right + 8, current_y - 8),
            "Current",
            fill="#f8fafc",
            font=font,
        )

        colors = {
            "support": "#22c55e",
            "resistance": "#ef4444",
            "fib": "#38bdf8",
            "previous_day": "#f59e0b",
            "bullish_fvg": "#16a34a",
            "bearish_fvg": "#dc2626",
        }
        zone_fills = {
            "bullish_fvg": "#173f3a",
            "bearish_fvg": "#4a252e",
        }
        labels = []
        for item in (item for item in chart_items if "low" in item):
            color = colors[item["kind"]]
            label = (
                f"{item['label']} {_price(item['low'], latest_snapshot)}-"
                f"{_price(item['high'], latest_snapshot)}"
            )
            if item["low"] > high:
                labels.append((plot_top, f"{label} above chart"))
            elif item["high"] < low:
                labels.append((plot_bottom, f"{label} below chart"))
            else:
                clipped_low = max(item["low"], low)
                clipped_high = min(item["high"], high)
                y1, y2 = y_for(clipped_high), y_for(clipped_low)
                draw.rectangle(
                    [plot_left, y1, plot_right, y2],
                    fill=zone_fills[item["kind"]],
                    outline=color,
                )
                draw.line([plot_left, y1, plot_right, y1], fill="#e2e8f0", width=1)
                draw.line([plot_left, y2, plot_right, y2], fill="#e2e8f0", width=1)
                labels.append(((y1 + y2) // 2, label))

        for item in (item for item in chart_items if "low" not in item):
            color = colors[item["kind"]]
            label = f"{item['label']} {_price(item['price'], latest_snapshot)}"
            if item["price"] > high:
                labels.append((plot_top, f"{label} above chart"))
            elif item["price"] < low:
                labels.append((plot_bottom, f"{label} below chart"))
            else:
                label_y = y_for(item["price"])
                draw.line(
                    [plot_left, label_y, plot_right, label_y], fill=color, width=2
                )
                labels.append((label_y, label))

        self._draw_candles(draw, candles, plot_left, plot_right, y_for)

        time_labels = (
            (0, plot_left),
            (len(candles) // 2, (plot_left + plot_right) // 2),
            (len(candles) - 1, plot_right),
        )
        for index, x in time_labels:
            text = display_time(candles[index]["candle_time"])
            text_width = draw.textbbox((0, 0), text, font=font)[2]
            draw.text(
                (
                    max(
                        plot_left,
                        min(x - text_width // 2, plot_right - text_width),
                    ),
                    plot_bottom + 12,
                ),
                text,
                fill="#94a3b8",
                font=font,
            )

        labels.sort(key=lambda entry: entry[0])
        next_y = plot_top
        for label_y, label in labels:
            adjusted_y = max(label_y - 7, next_y)
            adjusted_y = min(adjusted_y, plot_bottom - 12)
            draw.text(
                (plot_right + 8, adjusted_y),
                label,
                fill="#f8fafc",
                font=font,
            )
            next_y = adjusted_y + 14

        output_path.parent.mkdir(parents=True, exist_ok=True)
        image.save(output_path, "PNG")
        return output_path

    def _chart_items(self, timeframes):
        items = []
        latest_snapshot = None
        previous_day_added = False
        for timeframe in PATTERN_TIMEFRAMES:
            snapshot = timeframes.get(timeframe)
            if not snapshot:
                continue
            latest_snapshot = (
                snapshot
                if latest_snapshot is None
                or snapshot["candle_time"] > latest_snapshot["candle_time"]
                else latest_snapshot
            )
            levels = snapshot["levels"]
            for key, label, kind in (
                ("support", f"{timeframe} Support", "support"),
                ("resistance", f"{timeframe} Resistance", "resistance"),
            ):
                value = levels.get(key)
                if value is not None:
                    items.append({"kind": kind, "label": label, "price": value})
            if not previous_day_added:
                previous_day_high = levels.get("previous_day_high")
                previous_day_low = levels.get("previous_day_low")
                if previous_day_high is not None and previous_day_low is not None:
                    items.append(
                        {
                            "kind": "previous_day",
                            "label": "PDH",
                            "price": previous_day_high,
                        }
                    )
                    items.append(
                        {
                            "kind": "previous_day",
                            "label": "PDL",
                            "price": previous_day_low,
                        }
                    )
                    previous_day_added = True
            fib = levels.get("fib")
            if fib:
                for key in ("61.8",):
                    items.append(
                        {
                            "kind": "fib",
                            "label": f"{timeframe} Fib {key}",
                            "price": fib[key],
                        }
                    )
            for key, label, kind in (
                ("bullish_fvg", f"{timeframe} Bull FVG", "bullish_fvg"),
                ("bearish_fvg", f"{timeframe} Bear FVG", "bearish_fvg"),
            ):
                zone = levels.get(key)
                if zone:
                    items.append(
                        {
                            "kind": kind,
                            "label": label,
                            "low": zone["low"],
                            "high": zone["high"],
                        }
                    )
        candles, candle_timeframe = self._chart_candles(timeframes)
        if latest_snapshot is None and candle_timeframe:
            latest_snapshot = timeframes[candle_timeframe]
        return items, latest_snapshot, candles, candle_timeframe

    def _chart_candles(self, timeframes):
        priority = ("M15", "M30", "H1", "H4", "M1", "M5")
        for timeframe in priority:
            snapshot = timeframes.get(timeframe)
            history = snapshot.get("candle_history") if snapshot else None
            if history:
                return history[-CHART_CANDLE_LOOKBACK:], timeframe
        for timeframe in priority:
            snapshot = timeframes.get(timeframe)
            if snapshot:
                return [
                    {
                        "candle_time": snapshot["candle_time"],
                        "open": snapshot["open"],
                        "high": snapshot["high"],
                        "low": snapshot["low"],
                        "close": snapshot["close"],
                    }
                ], timeframe
        return [], None

    @staticmethod
    def _draw_candles(draw, candles, plot_left, plot_right, y_for):
        count = len(candles)
        if not count:
            return
        span = max(plot_right - plot_left, 1)
        slot = span / count
        body_half_width = max(1, min(11, int(slot * 0.28)))
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
                outline="#0f172a",
            )
