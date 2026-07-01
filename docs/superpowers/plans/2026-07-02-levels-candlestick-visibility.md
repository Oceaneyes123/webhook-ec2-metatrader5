# `/levels` Candlestick Visibility Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Keep `/levels` candlesticks visible when their prices overlap opaque key-level zones.

**Architecture:** Preserve the existing chart data and drawing helpers. Add an overlapping-zone regression case, then change only the layer order in `MarketState.levels_chart` so level graphics render before candlesticks.

**Tech Stack:** Python, Pillow, `unittest`

---

### Task 1: Prove and fix candlestick visibility

**Files:**
- Modify: `test_webhook.py:1063`
- Modify: `market_state.py:531-560`

- [ ] **Step 1: Write the failing regression test**

In `test_levels_chart_draws_recent_candlesticks`, replace the empty bullish FVG
with a zone covering both test candles:

```python
"bullish_fvg": {"low": 2290.0, "high": 2320.0},
```

Keep the existing pixel assertion. With the current layer order, the opaque
zone is drawn over the candles and removes their teal/red pixels.

- [ ] **Step 2: Run the focused test and verify RED**

Run:

```powershell
python -m unittest test_webhook.WebhookTest.test_levels_chart_draws_recent_candlesticks -v
```

Expected: `FAIL` because `candle_pixels` is `0`, not greater than `40`.

- [ ] **Step 3: Apply the minimum render-order change**

In `MarketState.levels_chart`, remove this block from before the `colors`
mapping:

```python
if candles:
    self._draw_candles(draw, candles, plot_left, plot_right, y_for)
```

Insert the same block immediately after the `for item in chart_items` loop and
before `labels.sort(...)`:

```python
if candles:
    self._draw_candles(draw, candles, plot_left, plot_right, y_for)
```

- [ ] **Step 4: Run the focused test and verify GREEN**

Run:

```powershell
python -m unittest test_webhook.WebhookTest.test_levels_chart_draws_recent_candlesticks -v
```

Expected: `OK` with one passing test.

- [ ] **Step 5: Run full verification**

Run:

```powershell
python -m unittest -v
```

Expected: all tests pass.

- [ ] **Step 6: Inspect the final diff**

Run:

```powershell
git diff --check
git diff -- market_state.py test_webhook.py docs/superpowers/specs/2026-07-02-levels-candlestick-visibility-design.md docs/superpowers/plans/2026-07-02-levels-candlestick-visibility.md
```

Confirm that existing uncommitted candle-history work remains intact and that
the implementation adds no dependency or unrelated refactor. Do not commit or
push.
