# Candlestick Pattern Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add five candlestick-pattern alerts to the MT5 EA and directional-bias/OHLC reporting to the Python webhook.

**Architecture:** Keep detection in `Webhook.mq5`, using shared candle math helpers and the existing new-bar scan. Keep presentation in `json_data_parser.py`, using event and fixed-bias mappings while deriving dynamic bias from `signal`.

**Tech Stack:** MQL5, Python standard library, `unittest`

---

### Task 1: Lock the Python reporting contract with failing tests

**Files:**
- Modify: `test_webhook.py`

- [ ] Add tests asserting all five event types are supported.
- [ ] Add a fixed-bias test using a `SHOOTING_STAR_CANDLE` payload without `signal`; expect a bearish icon and `Bias: Bearish / SELL`.
- [ ] Add an `INSIDE_BAR_BREAKOUT` test with `signal=BUY`; expect `Bias: Bullish / BUY`.
- [ ] Add an OHLC test with both `high` and `low`; expect `💰 O: ... | H: ... | L: ... | C: ...`.
- [ ] Update existing message assertions to include the new `Bias:` line while retaining `💰 open - close` when high/low are absent.
- [ ] Run `python -m unittest test_webhook.py` and confirm failures are caused by missing event/bias/OHLC behavior.

### Task 2: Implement Python event and bias reporting

**Files:**
- Modify: `json_data_parser.py`

- [ ] Extend `SUPPORTED_EVENTS` with:

```python
"SHOOTING_STAR_CANDLE": "Shooting Star Candle",
"INVERTED_HAMMER_CANDLE": "Inverted Hammer Candle",
"MORNING_STAR": "Morning Star",
"EVENING_STAR": "Evening Star",
"INSIDE_BAR_BREAKOUT": "Inside Bar Breakout",
```

- [ ] Add fixed bias data and a small resolver:

```python
PATTERN_BIAS = {
    "HAMMER_CANDLE": ("BUY", "Bullish / BUY"),
    "HANGING_MAN_CANDLE": ("SELL", "Bearish / SELL"),
    "SHOOTING_STAR_CANDLE": ("SELL", "Bearish / SELL"),
    "INVERTED_HAMMER_CANDLE": ("BUY", "Bullish / BUY"),
    "MORNING_STAR": ("BUY", "Bullish / BUY"),
    "EVENING_STAR": ("SELL", "Bearish / SELL"),
}

def signal_and_bias(payload):
    fixed = PATTERN_BIAS.get(payload.get("event_type"))
    if fixed:
        return fixed
    signal = str(payload.get("signal", "")).upper()
    return signal, {"BUY": "Bullish / BUY", "SELL": "Bearish / SELL"}.get(
        signal, "Directional / UNKNOWN"
    )
```

- [ ] Build the price line with labeled OHLC only when both `high` and `low` are present; otherwise retain the old open-close line.
- [ ] Insert `Bias: {bias}` between the title and time lines.
- [ ] Run `python -m unittest test_webhook.py` and confirm all Python tests pass.

### Task 3: Add configurable MQL5 candle helpers and detectors

**Files:**
- Modify: `Webhook.mq5`

- [ ] Add EA inputs:

```mql5
input double MaxBodyPercent = 35.0;
input double MinLongWickBodyRatio = 2.0;
input double MaxSmallWickBodyRatio = 1.0;
input double StrongCandleBodyPercent = 50.0;
```

- [ ] Add shared helpers `CandleBody`, `CandleRange`, `UpperWick`, `LowerWick`, `IsBullishCandle`, and `IsBearishCandle`.
- [ ] Update existing pin-bar math to use the helpers and reject zero range/body.
- [ ] Add `IsUpperWickPinBar`, `IsShootingStar`, and `IsInvertedHammer`. Use `close2 > close3 && close3 > close4` for Shooting Star and the inverse for Inverted Hammer.
- [ ] Add `IsMorningStar` and `IsEveningStar`. Require candle 3's body to meet `StrongCandleBodyPercent`, candle 2's body to be at most `MaxBodyPercent` of candle 3's body, and candle 1 to close through candle 3's body midpoint.
- [ ] Add `InsideBarBreakoutSignal`; require candle 2 inside candle 3 and return `BUY` only when candle 1 closes above the mother high or `SELL` only when it closes below the mother low.

### Task 4: Send every distinct match with complete payload data

**Files:**
- Modify: `Webhook.mq5`

- [ ] Extend `BuildPayload` with high, low, and bias fields.
- [ ] Add `SendPattern` to centralize logging, bias selection, payload construction, and `SendWebhook`.
- [ ] Rename `CheckEngulfingOnTimeframe` to `CheckPatternsOnTimeframe`.
- [ ] Read candles 1–4 once and document their indices.
- [ ] Keep the existing new-bar guard, then evaluate each pattern with independent `if` statements so multiple matches send on one closed candle.
- [ ] Keep existing Engulfing behavior on all scanned timeframes and existing Hammer/Hanging Man timeframe restrictions; scan all new patterns on all configured timeframes.
- [ ] Update `CheckAllTimeframes` to call `CheckPatternsOnTimeframe`.

### Task 5: Verify source and behavior

**Files:**
- Verify: `Webhook.mq5`
- Verify: `json_data_parser.py`
- Verify: `test_webhook.py`

- [ ] Run `python -m unittest test_webhook.py`; expect zero failures.
- [ ] Run `python -m py_compile json_data_parser.py webhook.py telegram_sender.py app_logger.py test_webhook.py`; expect exit code 0.
- [ ] Compile `Webhook.mq5` with MetaEditor if available; otherwise report compiler unavailability explicitly.
- [ ] Run `git diff --check`; expect no whitespace errors.
- [ ] Review `git diff` for only the requested feature, prior timezone change, CodeGraph initialization, spec, and plan. Do not commit or push.
