# Two-EA Refactor Design

## Goal

Replace the single `Webhook.mq5` EA with two focused EAs while preserving the
existing Python webhook and Telegram behavior:

- `Webhook1.mq5` publishes market snapshots and pattern data.
- `Webhook2.mq5` manages trade mode, confluence, and pending orders.

Both EAs use `http://127.0.0.1:8000/webhook` by default and communicate with
the same Python server. Telegram remains entirely in Python.

## Repository and Live Files

The repository will track:

```text
mq5/
  Webhook1.mq5
  Webhook2.mq5
  includes/
    WebhookCommon.mqh
    MarketSnapshot.mqh
    TradeManager.mqh
```

All three shared `.mqh` files are canonical source files tracked by Git. No
shared MQL5 source will exist only in the live MetaTrader installation.

The legacy canonical `mq5/Webhook.mq5` and root `Webhook.mq5` link will be
removed. Root `Webhook1.mq5` and `Webhook2.mq5` links will point to their live
MetaTrader Experts files.

`sync_mq5.py` will copy both canonical EA files through those two root links,
then copy all three canonical include files into the live Experts `includes`
directory in one run. No new environment variable or alternate
target-directory mechanism will be added.

## Shared MQL5 Code

`WebhookCommon.mqh` will contain only behavior used by both EAs:

- `Candle`
- timeframe, datetime, JSON, and number formatting
- candle reading and candle geometry helpers
- webhook POST handling and WebRequest diagnostics
- `PipSize` if both EAs require it

Each EA will define the existing shared input names expected by the include,
including `WebhookUrl`, `WebRequestTimeoutMs`, and `PrintDebugLogs`.

## Market EA

`Webhook1.mq5` will include `WebhookCommon.mqh` and `MarketSnapshot.mqh`.
It will:

- monitor M1, M5, M15, M30, H1, and H4 closed candles;
- own snapshot EMA and RSI handles;
- detect patterns and calculate levels, FVGs, Fibonacci levels, support,
  resistance, and previous-day levels;
- include up to `ChartHistoryBars` previous candles in a `candles` array;
- add `"source":"webhook1"` to every payload;
- send `TIMEFRAME_SNAPSHOT` events; and
- contain no order or position management.

`MarketSnapshot.mqh` will hold the market-only structs and functions moved from
the current EA, including snapshot payload construction and timeframe checks.

## Trade EA

`Webhook2.mq5` will include `WebhookCommon.mqh`, `TradeManager.mqh`, and the
standard `Trade.mqh`. It will:

- own only the EMA handles needed for M1/M5/M15 trade confluence;
- fetch the existing `/trade-config` endpoint;
- apply BUY, SELL, and NOTRADE modes;
- manage the existing trailing buy-limit and sell-limit orders;
- preserve the one-open-position-per-symbol rule;
- add `"source":"webhook2"` to EA error and trade-status payloads; and
- send no market snapshots or market-level calculations.

`TradeManager.mqh` will hold the trade configuration, HTTP GET parsing, error
reporting, confluence, order lookup, pending-order trailing, and trading logic.

## Python Compatibility

The Python server will accept `webhook1`, `webhook2`, or a missing `source`.
Existing event routing remains unchanged:

- `TIMEFRAME_SNAPSHOT` continues updating `MarketState`.
- `EA_ERROR` continues sending a Telegram issue message.
- Missing `source` remains backward compatible.
- EA issue messages include a source label only when a source is present.

No second bot, chat ID, or MQL5 Telegram implementation will be introduced.

## Tests and Verification

Python tests will cover:

- acceptance of `source=webhook1`;
- acceptance of `source=webhook2`;
- acceptance when `source` is missing;
- source display in `EA_ERROR` messages;
- `Webhook1` snapshots continuing to update market state; and
- `sync_mq5.py` copying both canonical EAs and all shared includes to their
  distinct live targets.

Tests will be written and observed failing before production changes. After the
refactor, all Python tests will run, both canonical EAs will be compiled, the
sync script will run, both live EAs will be compiled or reloaded, and canonical
and live file bytes will be compared.

No git commit or push will be performed.
