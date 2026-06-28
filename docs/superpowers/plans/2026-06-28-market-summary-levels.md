# Market Summary and Levels Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add unified multi-timeframe snapshots, persistent market state, and HTML Telegram summary/level reports while restricting M1/M5 analysis to EMA20/EMA50.

**Architecture:** MT5 computes indicators, patterns, and levels from its local history and posts one snapshot per closed candle. Python validates and atomically persists the latest state, deduplicates pattern alerts, and formats on-demand Telegram reports.

**Tech Stack:** MQL5, Python standard library, `unittest`

---

### Task 1: Define the Python snapshot and report contract

**Files:**
- Create: `market_state.py`
- Modify: `test_webhook.py`

- [ ] Add failing tests for M1/M5 EMA snapshot validation, neutral EMA equality, M15–H4 level snapshots, invalid timeframe rejection, persistence reload, duplicate-candle suppression, higher-timeframe invalidation, and BUY/SELL/WAIT confluence.
- [ ] Add failing tests for `/summary <symbol>` and `/levels <symbol>` HTML output, missing-symbol usage, missing data, and HTML escaping.
- [ ] Run `python -m unittest test_webhook.py` and confirm failures are caused by the missing state API.
- [ ] Implement `MarketState.update`, JSON loading/atomic saving, retained-pattern invalidation, `summary`, and `levels` with only stdlib modules.
- [ ] Re-run `python -m unittest test_webhook.py` and confirm the state/report tests pass.

### Task 2: Integrate snapshots and HTML into the webhook

**Files:**
- Modify: `telegram_sender.py`
- Modify: `json_data_parser.py`
- Modify: `webhook.py`
- Modify: `test_webhook.py`

- [ ] Add failing tests for Telegram `parse_mode=HTML`, snapshot ingestion, retry deduplication, pause-with-state-update, snapshot pattern alerts, legacy M1/M5 pattern rejection, and help text.
- [ ] Run the targeted tests and confirm expected failures.
- [ ] Add optional HTML parse mode to `send_telegram_message` and escape all dynamic legacy-alert fields.
- [ ] Route `TIMEFRAME_SNAPSHOT` through `MarketState` before pause suppression, send only newly detected M15–H4 patterns, and expose `/summary` and `/levels`.
- [ ] Keep legacy M15–H4 pattern payloads and `/recent` working.
- [ ] Run the full Python test suite.

### Task 3: Produce unified snapshots in MT5

**Files:**
- Modify: `Webhook.mq5` through its existing MetaTrader symlink

- [ ] Add EMA20/EMA50 handles for M1/M5 and release them on deinitialization.
- [ ] Restrict every candle-pattern detector to M15, M30, H1, and H4.
- [ ] Add configurable 100-bar swing, two-bar strength, ATR(14), and 0.25 ATR FVG calculations.
- [ ] Calculate nearest support/resistance, latest alternating-pivot Fibonacci retracements, previous-day high/low, and nearest unfilled qualifying bullish/bearish FVGs.
- [ ] Replace per-pattern webhook sends with one `TIMEFRAME_SNAPSHOT` containing common OHLC data plus EMA or pattern/level data.
- [ ] Send non-notifying initialization snapshots and notifying new-bar snapshots.
- [ ] Compile with MetaEditor and resolve all MQL5 errors.

### Task 4: Documentation and verification

**Files:**
- Modify: `README.md`

- [ ] Document the snapshot behavior, EA inputs, JSON state file, HTML mode, `/summary <symbol>`, and `/levels <symbol>`.
- [ ] Run `python -m unittest test_webhook.py`.
- [ ] Run `python -m py_compile app_logger.py json_data_parser.py market_state.py telegram_sender.py webhook.py test_webhook.py`.
- [ ] Run `git diff --check` and inspect the final diff for unrelated changes.
- [ ] Do not commit or push.
