# `/levels` Candle-First Chart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Send 200 closed MT5 candles per snapshot and render `/levels` with a candle-defined y-axis plus non-distorting key-level overlays.

**Architecture:** `Webhook1` and `MarketSnapshot.mqh` own chronological candle-history production. `market_state.py` normalizes optional history, prefers M15 for charts, and separates the candle price range from overlay positioning. Existing Pillow and Telegram paths remain in place.

**Tech Stack:** MQL5, Python standard library, Pillow, `unittest`

---

### Task 1: Lock the MQL5 snapshot contract

**Files:**
- Modify: `test_sync_mq5.py`
- Modify: `mq5/Webhook1.mq5`
- Modify: `mq5/Webhook2.mq5`
- Modify: `mq5/includes/MarketSnapshot.mqh`

- [x] **Step 1: Write failing source-contract assertions**

Update `test_market_ea_owns_snapshots_only` to require:

```python
self.assertIn("input int ChartHistoryBars = 200;", ea)
self.assertIn("for(int shift = ChartHistoryBars; shift >= 1; shift--)", market)
self.assertIn('{\\"time\\":\\"', market)
```

Update `test_trade_ea_owns_trade_management_only` to require:

```python
self.assertIn("does not send chart/history data", ea)
```

- [x] **Step 2: Verify RED**

Run:

```powershell
python -m unittest test_sync_mq5.SyncMq5Test.test_market_ea_owns_snapshots_only test_sync_mq5.SyncMq5Test.test_trade_ea_owns_trade_management_only -v
```

Expected: failures for the 80-bar default, reverse loop, `candle_time` key, and missing Webhook2 comment.

- [x] **Step 3: Apply the minimum MQL5 changes**

Set:

```mql5
input int ChartHistoryBars = 200;
```

Document Webhook ownership near each EA header. In `BuildCandlesJson`, iterate
from `ChartHistoryBars` down to `1`, read `iTime/iOpen/iHigh/iLow/iClose`,
skip invalid values, and emit:

```mql5
{"time":"...","open":...,"high":...,"low":...,"close":...}
```

Keep the existing top-level snapshot OHLC and `"source":"webhook1"`.

- [x] **Step 4: Verify GREEN**

Run the focused command from Step 2. Expected: both tests pass.

### Task 2: Normalize supplied candle history without breaking old snapshots

**Files:**
- Modify: `test_webhook.py`
- Modify: `market_state.py`

- [x] **Step 1: Write failing history tests**

Change the supplied-history fixture to chronological order and mix `time` with
`candle_time`:

```python
payload["candles"] = [
    {"time": "2026.06.28 10:00:00", "open": 2295.0, "high": 2305.0, "low": 2290.0, "close": 2300.0},
    {"candle_time": "2026.06.28 10:01:00", "open": 2300.0, "high": 2310.0, "low": 2290.0, "close": 2305.0},
]
```

Assert the normalized order is unchanged. Add an explicit snapshot-without-
`source` test and a two-update fallback-history test with no `candles` key.

- [x] **Step 2: Verify RED**

Run:

```powershell
python -m unittest test_webhook.WebhookTest.test_market_state_uses_supplied_candle_history test_webhook.WebhookTest.test_market_state_accumulates_history_without_candles -v
```

Expected: supplied history fails because `time` is rejected and input is
reversed; fallback remains passing.

- [x] **Step 3: Implement normalization**

Set `CHART_CANDLE_LOOKBACK = 200`. In `validate_snapshot`, only validate
`candles` when the key exists, accept `time` or `candle_time`, and normalize to
`candle_time`. In `MarketState.update`, use supplied chronological history
directly; only append the top-level candle when `candles` is absent.

- [x] **Step 4: Verify GREEN**

Run the focused command from Step 2 plus the explicit source compatibility
tests. Expected: all pass.

### Task 3: Prefer M15 and render candle-first

**Files:**
- Modify: `test_webhook.py`
- Modify: `market_state.py`

- [x] **Step 1: Write failing chart tests**

Add a selection test that supplies M30/H1/H4 history before M15 and asserts:

```python
history, timeframe = state._chart_candles(state.data["symbols"]["GOLD"])
self.assertEqual(timeframe, "M15")
self.assertEqual(len(history), 200)
```

Add a far-level chart test with candles around 2300 and FVG/point levels around
4000. Record `ImageDraw.ImageDraw.text` calls and assert label strings contain
`above chart`. Inspect candle-color pixels and assert their vertical span is
greater than 200 pixels, proving distant levels did not alter the y-axis.

- [x] **Step 2: Verify RED**

Run:

```powershell
python -m unittest test_webhook.WebhookTest.test_levels_chart_prefers_m15_history test_webhook.WebhookTest.test_far_levels_are_labels_without_compressing_candles -v
```

Expected: selection returns the current first pattern timeframe/40 bars and
the old chart compresses candles.

- [x] **Step 3: Implement candle-first rendering**

Use timeframe priority:

```python
("M15", "M30", "H1", "H4", "M1", "M5")
```

Derive `low/high` only from candle lows/highs, add 15% padding with the approved
minimums, clip intersecting FVGs, suffix out-of-range labels, draw muted zones
then in-range lines then candles, and add first/middle/latest x-axis labels.
Use a one-pixel minimum candle half-width so 200 bodies do not overlap.

- [x] **Step 4: Verify GREEN**

Run the focused command from Step 2 and the existing two chart tests. Expected:
all pass.

### Task 4: Full verification and live MQL5 sync

**Files:**
- Verify all modified files
- Synchronize the five canonical MQL5 sources to live targets

- [x] **Step 1: Run the Python suite**

```powershell
python -m unittest -v
```

Expected: zero failures.

- [x] **Step 2: Compile canonical EAs**

Run MetaEditor command-line compilation for:

```text
mq5/Webhook1.mq5
mq5/Webhook2.mq5
```

Expected: both logs report zero errors.

- [x] **Step 3: Sync and compile live EAs**

```powershell
python sync_mq5.py
```

Compile/reload root `Webhook1.mq5` and `Webhook2.mq5`. Expected: zero compile
errors.

- [x] **Step 4: Compare canonical and live files**

Use `sync_mq5.RELATIVE_SOURCES` and resolved root EA targets to compare bytes
for all five canonical/live pairs. Expected: every pair matches.

- [x] **Step 5: Inspect the final diff**

```powershell
git diff --check
git status --short
git diff -- mq5 market_state.py test_webhook.py test_sync_mq5.py docs/superpowers
```

Expected: only requested source, tests, and design/plan changes. Do not commit
or push.
