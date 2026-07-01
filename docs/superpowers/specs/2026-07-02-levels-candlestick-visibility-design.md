# `/levels` Candlestick Visibility Design

## Goal

Keep the existing `/levels` chart layout while making its recent price
candlesticks visible on the same plot as the key levels.

## Design

Retain the existing candle history, price scaling, chart dimensions, colors,
labels, and Telegram delivery flow. Change only the drawing order in
`MarketState.levels_chart`: draw level zones and level lines before drawing the
candlesticks, so opaque FVG zones cannot cover the candle bodies and wicks.
Labels remain outside the plot and are drawn after the candles.

## Test

Extend the candlestick chart regression test with an FVG zone that overlaps the
candle prices. Assert that bullish and bearish candle-colored pixels remain in
the plot after rendering. Run the focused chart tests, then the full test suite.

## Out of Scope

No transparency system, separate candle panel, new dependency, chart resizing,
or change to the `/levels` command response.
