# Two-EA Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the single MT5 EA with tracked market and trade EAs, tracked shared includes, and one sync operation that updates every live MQL5 source file.

**Architecture:** Shared transport and candle primitives live in `WebhookCommon.mqh`; market-only and trade-only behavior live in separate includes called by thin EA lifecycle files. The existing Python process remains the single webhook and Telegram integration. Root symlinks identify the two live EA targets, and the sync script derives the live `includes` directory from them.

**Tech Stack:** MQL5, Python standard library, `unittest`, MetaEditor compiler

---

### Task 1: Specify the tracked MQL5 split and two-target sync

**Files:**
- Modify: `test_sync_mq5.py`
- Modify: `sync_mq5.py`

- [ ] **Step 1: Write failing tests for both EAs and shared includes**

Add tests that create two temporary live EA targets and an `includes` directory,
call a multi-file `sync_mq5(targets=...)`, and assert byte equality for:

```python
EXPECTED_MQL5_FILES = (
    Path("Webhook1.mq5"),
    Path("Webhook2.mq5"),
    Path("includes/WebhookCommon.mqh"),
    Path("includes/MarketSnapshot.mqh"),
    Path("includes/TradeManager.mqh"),
)
```

Also assert that each target is distinct from its canonical source and that all
five canonical files exist.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
python -m unittest test_sync_mq5.py -v
```

Expected: failure because the five canonical paths and multi-file sync behavior
do not exist.

- [ ] **Step 3: Implement the smallest multi-file sync**

Replace the singular constants with:

```python
CANONICAL_DIR = ROOT / "mq5"
LIVE_EAS = (ROOT / "Webhook1.mq5", ROOT / "Webhook2.mq5")
RELATIVE_SOURCES = (
    Path("Webhook1.mq5"),
    Path("Webhook2.mq5"),
    Path("includes/WebhookCommon.mqh"),
    Path("includes/MarketSnapshot.mqh"),
    Path("includes/TradeManager.mqh"),
)
```

Implement one loop that validates all sources and destinations before copying,
creates only the live `includes` directory, copies with `shutil.copy2`, and
returns the copied `(source, target)` pairs. Derive the live Experts directory
from the resolved parent of the two root EA links. Do not add an environment
variable or generic manifest abstraction.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run the same unittest command. Expected: all sync tests pass.

### Task 2: Specify Python source compatibility

**Files:**
- Modify: `test_webhook.py`
- Modify: `webhook.py`

- [ ] **Step 1: Write failing source-routing tests**

Add focused tests using the existing in-memory request handler:

```python
def test_ea_issue_message_includes_source_when_present(self):
    self.assertIn(
        "Source: <b>webhook2</b>",
        webhook.ea_issue_message(
            {"source": "webhook2", "event_type": "EA_ERROR", "message": "failed"}
        ),
    )

def test_ea_issue_message_omits_source_when_missing(self):
    self.assertNotIn(
        "Source:",
        webhook.ea_issue_message({"event_type": "EA_ERROR", "message": "failed"}),
    )
```

Post representative `EA_ERROR` payloads from `webhook1`, `webhook2`, and without
`source`, asserting HTTP 200. Post a `TIMEFRAME_SNAPSHOT` with
`source=webhook1`, patch `MARKET_STATE.update`, and assert it receives the
payload.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
python -m unittest test_webhook.WebhookTest.test_ea_issue_message_includes_source_when_present -v
```

Expected: failure because the source label is absent.

- [ ] **Step 3: Add the optional escaped source line**

In `ea_issue_message`, read and normalize `source` exactly like the existing
optional fields and insert:

```python
if source:
    lines.append(f"Source: <b>{html.escape(source)}</b>")
```

Do not add source validation or change event routing: current routing already
accepts both values and a missing value because it dispatches by `event_type`.

- [ ] **Step 4: Run all webhook tests and verify GREEN**

Run:

```powershell
python -m unittest test_webhook.py -v
```

Expected: all webhook tests pass.

### Task 3: Extract common and market behavior

**Files:**
- Create: `mq5/includes/WebhookCommon.mqh`
- Create: `mq5/includes/MarketSnapshot.mqh`
- Create: `mq5/Webhook1.mq5`

- [ ] **Step 1: Add failing structural checks**

In `test_sync_mq5.py`, assert `Webhook1.mq5` includes both market headers,
defines `ChartHistoryBars = 80`, and does not contain `ManageTrading`.
Assert snapshot payload source contains:

```python
self.assertIn('\\"source\\":\\"webhook1\\"', market_source)
self.assertIn('\\"candles\\":[', market_source)
```

- [ ] **Step 2: Run the structural tests and verify RED**

Run `python -m unittest test_sync_mq5.py -v`. Expected: failure because the
market files do not exist.

- [ ] **Step 3: Move shared primitives without behavior changes**

Move `Candle`, `TimeframeToText`, `JsonEscape`, `DateTimeToText`,
`JsonNumberOrNull`, `PrintWebRequestHelp`, `SendWebhook`, `ReadCandle`,
`CandleBody`, `CandleRange`, `UpperWick`, `LowerWick`, `IsBullishCandle`,
`IsBearishCandle`, `HasValidBody`, and `PipSize` into `WebhookCommon.mqh`.

- [ ] **Step 4: Move market-only behavior and add candle history**

Move pattern detection, indicator reads, levels, payload construction, and
timeframe checks into `MarketSnapshot.mqh`. Add a `BuildCandlesJson` loop over
closed shifts `1..ChartHistoryBars`, stopping when candle time/data is
unavailable. Add `"source":"webhook1"` and the resulting `candles` array to
every snapshot.

- [ ] **Step 5: Create the thin market EA**

Define market inputs and six timeframe arrays, initialize EMA20/EMA50/RSI
handles for all six timeframes, call `CheckAllTimeframes` from `OnInit` and
`OnTick`, and release every valid handle from `OnDeinit`. Do not include
`Trade.mqh` or trade functions.

- [ ] **Step 6: Run structural tests and compile Webhook1**

Run the sync tests, then compile canonical `mq5/Webhook1.mq5` with the installed
MetaEditor compiler. Expected: tests pass and compiler reports zero errors.

### Task 4: Extract trade behavior

**Files:**
- Create: `mq5/includes/TradeManager.mqh`
- Create: `mq5/Webhook2.mq5`
- Delete: `mq5/Webhook.mq5`

- [ ] **Step 1: Add failing structural checks**

Assert `Webhook2.mq5` includes common/trade headers, creates exactly three
EMA20 and three EMA50 handles for M1/M5/M15, and contains no
`CheckAllTimeframes`, RSI handle, level calculation, or snapshot payload.
Assert trade issue payload source contains:

```python
self.assertIn('\\"source\\":\\"webhook2\\"', trade_source)
```

- [ ] **Step 2: Run structural tests and verify RED**

Run `python -m unittest test_sync_mq5.py -v`. Expected: failure because the
trade files do not exist.

- [ ] **Step 3: Move trade-only behavior**

Move `TradeConfig`, issue throttling, `TradeResultText`, `TradeConfigUrl`,
`HttpGet`, JSON value readers, `FetchTradeConfig`, EMA confluence, pending
order lookup/deletion/trailing, and `ManageTrading` into `TradeManager.mqh`.
Add `"source":"webhook2"` to `EA_ERROR` payloads.

- [ ] **Step 4: Create the thin trade EA**

Define shared and trade inputs, `CTrade`, issue-throttle state, the M1/M5/M15
timeframe array, and six EMA handles. Initialize and release only those
handles; call `ManageTrading` from `OnTick`.

- [ ] **Step 5: Remove the legacy canonical EA and compile Webhook2**

Delete `mq5/Webhook.mq5`. Run structural tests and compile canonical
`mq5/Webhook2.mq5`. Expected: tests pass and compiler reports zero errors.

### Task 5: Replace live links, sync, document, and verify

**Files:**
- Delete: `Webhook.mq5`
- Create symlinks: `Webhook1.mq5`, `Webhook2.mq5`
- Modify: `README.md`
- Modify: `AGENTS.md`

- [ ] **Step 1: Replace the legacy live link**

Remove only the repository root `Webhook.mq5` symlink. Create root symlinks
whose targets are sibling live files named `Webhook1.mq5` and `Webhook2.mq5`
in the same MetaTrader Experts directory.

- [ ] **Step 2: Update workflow documentation**

Document both canonical EAs, all three tracked shared includes, two root live
links, the one-way five-file sync, and the requirement to compile/reload both
live EAs. Remove singular legacy workflow statements.

- [ ] **Step 3: Run the complete Python suite**

Run:

```powershell
python -m unittest discover -v
```

Expected: all tests pass.

- [ ] **Step 4: Sync and compare all five files**

Run `python sync_mq5.py`. Compare each canonical EA/include byte-for-byte with
its live target. Expected: all comparisons are equal.

- [ ] **Step 5: Compile or reload both live EAs**

Compile live `Webhook1.mq5` and `Webhook2.mq5` using MetaEditor and confirm zero
errors. If MetaEditor cannot be automated, report that exact remaining manual
verification rather than claiming completion.

- [ ] **Step 6: Inspect the final diff**

Run `git status --short`, `git diff --check`, and review the scoped diff.
Do not stage, commit, or push.
