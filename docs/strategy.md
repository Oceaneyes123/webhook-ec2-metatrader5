# Selective multi-timeframe strategy

Read [the pre-change audit](strategy-audit.md) for the original decision flow.

## Decision flow and entry rules

**HTF bias → location → setup → closed confirmation → score → realistic R:R
→ execution → R management → journal → expectancy.**

AUTO requires at least two aligned H4/H1/M30 structure states, H1 alignment,
and no opposite established HTF trend. A CHoCH remains the existing engine's
`ranging` state, not an automatic reversal. One ranging timeframe costs score;
an entirely ranging/uncertain context cannot trade. Missing structure means wait.

BUY requires a bullish context; SELL mirrors every price comparison. M5/M15
are evaluated as entry candidates; the best passing candidate wins. M1 supplies
execution quotes, never overall direction. Quotes from Webhook2 include their
actual tick time, spread, tick size and broker minimum stop distance. Both
received time and UTC candle-close time gate stale data. Old feed versions
without `closed_at` cannot authorize AUTO.

The confirmation candle must interact with an observable S/R, confirmed swing,
previous-day level, FVG or Fibonacci 50/61.8/78.6 level. The existing feed sends
50 and 61.8; 78.6 is used only if supplied. An EMA touch alone cannot qualify.
Duplicate copies of a level do not create extra confluence; S/R and swing
references share one evidence family. Optional EMA100/200 add alignment votes
if supplied; the feed currently collects EMA20/50. EMA20 slope is derived from
the EMA recurrence and retained in the journal.

- **Pullback:** recent closes retrace against the HTF direction into a
  supporting area, with aligned EMA20/50; then a directional candle closes
  back away from that area and beyond the previous close.
- **Breakout/retest:** an earlier directional candle closes beyond a real
  level plus ATR buffer, subsequent closes hold that side, and a later candle
  retests and confirms it. A wick or the original breakout candle is insufficient.
- Both require a minimum body/range ratio and a close near the directional
  end. RSI earns momentum evidence; extreme RSI alone never reverses direction.
- Reject excessive EMA extension, wide spread, abnormal ATR, oversized current
  or immediately preceding candles, an opposing FVG containing entry, and price
  drift from the confirmation close. ATR uses true ranges including gaps and
  excludes the signal candle from its own expansion benchmark.

Scores are configurable **hypotheses, not probabilities or backtest results**.
The initial 100 positive points allocate 35 to HTF structure, 10 to EMA evidence,
30 to location/confluence, 20 to confirmation/RSI and 5 to viable R:R. Hard gates
cannot be overcome by a high score. Scores are clipped to 0–100, graded A+ at
80+, A at 70+, B at 60+, and rejected below 60. Default AUTO minimum is 70.
Outside-session and ranging penalties express initial caution; there is no
assumption that London is intrinsically profitable.

## Brackets and execution

BUY SL is below both the supporting area and the recent pullback low, plus
ATR buffer. SELL is above both resistance and the recent high. Minimum ATR
risk prevents an excessively tight stop. Round stops outward to broker ticks.
The target is the **nearest observable opposing boundary**, buffered toward
entry and rounded conservatively. Reject insufficient R:R; never extend TP
past an intervening level to manufacture a ratio. Spread is already represented
by BUY-at-ask / SELL-at-bid. Minimum stops include spread clearance.

AUTO cancels old EA limits and sends a market order only while the short-lived
Python offer remains valid. Webhook2 rechecks price drift, broker distances,
R:R, volume steps and any existing position/pending order for the symbol.
SL and TP accompany the opening request. A terminal lock and persistent setup
ID prevent duplicate execution. Broker return codes determine the recorded
execution outcome. Market-execution brokers may still slip fills; compare
actual entry/risk with the planned values.

One durable offer is allowed per signal. Offers count toward daily level
attempt limits even if HTTP delivery or broker execution is uncertain. This
deliberately sacrifices a missed trade instead of blindly retrying. Filled
trades, not polling calls or partial exits, count toward session limits.
There is one active symbol thesis, a session trade limit, a UTC-day consecutive
loss limit, and cooldowns after a loss or large win. Unresolved journal entries
block new AUTO trades until their closing deals arrive. No automatic parameter
adjustment or reset of an unresolved trade is performed.

## Exit management

Webhook2 persists the original stop, actual filled entry/volume, risk in price
units and estimated monetary risk from `OrderCalcProfit`. R always uses initial
risk, even after stops move. Parameters are frozen per setup in terminal globals
and the SQLite plan. Management continues when AUTO is paused or Python is
unavailable; attached SL/TP also remain with the broker.

- Default +1R: move SL to entry (price breakeven; costs may still yield a loss).
- Default +1.5R: protect +0.5R. Stops only tighten and respect freeze/stops levels.
- Optional +2R partial: close the configured fraction of initial volume, rounded
  down to the broker step, leaving a valid residual. **Disabled initially** via
  `partial_fraction: 0`. Hedging uses ticket-specific partial close; netting
  uses a position-bound opposite deal. A prior/manual partial prevents a repeat.
  An uncertain request is not retried automatically.
- From +2R, default trailing follows the previous closed M5 low/high; optionally
  choose M5 EMA20 or disable trailing. This is a candle-level trail, not a new
  confirmed external swing detector. It cannot loosen a protected stop.
- The nearest structural TP remains the final exit. A runner or partial only
  operates when there is enough structural room to reach its R trigger. No
  synthetic distant second TP is added.

TPSL skips `S:` strategy orders/positions entirely. Its existing pip SL/TP and
breakeven remain available for legacy/manual entries. Do not run an old TPSL
binary alongside new strategy positions: it does not know this exclusion.

MFE/MAE are sampled from executable bid/ask on delivered terminal ticks, plus
the final exit; terminal downtime cannot be reconstructed as tick-level MFE.
R management arithmetic includes executable initialization self-checks in
`StrategyManagementChecks`; compilation alone is not evidence they ran.

## Configuration reference

Defaults live in [`strategy_config.json`](../strategy_config.json). Set
`STRATEGY_CONFIG_FILE` to a JSON file containing only deliberate overrides;
weight overrides merge by key. Unknown top-level keys and invalid numeric
values fail closed. Existing `TRADE_LOT_SIZE` still controls requested volume;
this change does not introduce automatic equity-based position sizing.

| Parameter | Default | Meaning |
|---|---:|---|
| min_score | 70 | Minimum AUTO evidence score; at least 60 |
| min_rr | 1.5 | Minimum buffered, spread-aware planned reward/risk |
| allowed_sessions | all five | Asian, London, London/NY, New York, Outside |
| enabled_setups | pullback, breakout_retest | Enabled entry sequences |
| htf_min_aligned | 2 | Required aligned H4/H1/M30 structure states |
| require_h1 | true | H1 must agree with selected HTF bias |
| entry_timeframes | M5, M15 | Closed-candle setup candidates |
| freshness_grace_seconds | 120 | Grace beyond one timeframe period since close/receipt |
| quote_max_age_seconds | 10 | Maximum execution tick age |
| atr_period | 14 | True ranges in each volatility measurement window |
| atr_min_ratio / atr_max_ratio | 0.5 / 2.5 | Current ATR versus preceding ATR window |
| expansion_max_atr | 2.5 | Maximum current/previous true range in ATR |
| extension_max_atr | 2.0 | Maximum entry distance from EMA20 in ATR |
| spread_max_atr | 0.15 | Maximum spread in ATR |
| location_max_atr | 0.75 | Maximum entry distance from meaningful area |
| level_cluster_atr | 0.25 | Interaction/confluence and repeat-level tolerance |
| retest_lookback | 6 | Recent candles for sequence and invalidation |
| break_buffer_atr | 0.12 | Minimum close beyond broken level; hold tolerance |
| confirmation_body_ratio | 0.35 | Minimum body / total range |
| confirmation_close_location | 0.65 | Minimum close location toward directional end |
| sl_buffer_atr | 0.2 | Buffer beyond invalidation |
| sl_min_atr | 0.75 | Minimum initial stop distance |
| target_buffer_atr | 0.1 | Exit before opposing boundary |
| rsi_buy_min / rsi_sell_max | 50 / 50 | Momentum evidence thresholds, never reversal triggers |
| max_trades_session | 3 | Filled trades per symbol/account/session category/UTC day |
| max_consecutive_losses | 3 | Stop entries after this UTC-day loss sequence |
| loss_cooldown_seconds | 1800 | Pause after a losing completed trade |
| large_win_r | 2.0 | R result triggering win cooldown |
| win_cooldown_seconds | 900 | Pause after large completed win |
| max_level_attempts_day | 1 | Durable offers near same directional level per UTC day |
| plan_ttl_seconds | 15 | Execution offer lifetime |
| execution_tolerance_atr | 0.15 | Confirmation-close drift and final quote deviation |
| breakeven_r | 1.0 | Price-breakeven trigger; 0 disables |
| protect_r / protect_lock_r | 1.5 / 0.5 | Protection trigger and profit locked in R |
| partial_close_r / partial_fraction | 2.0 / 0.0 | Partial trigger and initial-volume fraction; 0 fraction disables |
| trail_start_r | 2.0 | Trailing trigger; 0 disables |
| trailing_method | structure | Previous M5 low/high; alternatives ema, off |
| weights.h4 / h1 / m30 | 15 / 15 / 5 | Aligned HTF evidence |
| weights.ema | 10 | Proportion of available momentum/EMA alignment votes |
| weights.location / confluence | 20 / 10 | Meaningful area and independent coincident families |
| weights.confirmation / rsi | 15 / 5 | Closed confirmation and RSI momentum |
| weights.rr | 5 | Viable structural R:R |
| weights.range_penalty | 10 | Deduction when one participating HTF is ranging |
| weights.weak_session_penalty | 5 | Initial Outside-session deduction |

Session classification reuses existing `REPORT_SESSIONS` IANA-zone windows,
including daylight-saving transitions. London/NY overlap is a distinct category;
London takes priority over Asian overlap. `allowed_sessions` controls strategy
participation independently of report-delivery switches. UTC day boundaries
are used consistently for limits and weekday analytics.

## Journal and evaluation

The existing account database gains `strategy_plans`, `strategy_deals` and
`strategy_marks`. Plans retain configuration, score components, HTF structure,
entry timeframe/session, levels, RSI, EMA, ATR, confirmation, entry/SL/TP and
planned R:R. Broker/account/deal identity deduplicates transactions. Partial
closes aggregate into one position result; opening and exit commission, fees
and swap are included. Failed strategy-deal webhook deliveries are queued in
MT5 `MQL5/Files/strategy_events` and retried after restart.

New legacy/manual fills also receive journal context, explicitly unscored.
Delayed legacy fills do not borrow current context as historical evidence.
Historical trades without original monetary risk are never assigned invented
R. Reversed/missing-entry/incomplete positions are excluded from measured R.

`/performance Gold` shows the count of complete measured trades, wins/losses,
win rate, average winning/losing R, expectancy/average R, total R, R profit
factor, closed-trade maximum drawdown and current losing streak. Breakdowns
show sample size and expectancy by setup, grade, direction, session, UTC
weekday, timeframe, HTF bias and planned R:R bucket. Open/incomplete/unscored
records are reported as excluded. Profit factor uses R so different trade
sizes do not dominate; drawdown is closed-trade cumulative R, not account-equity
drawdown. Expectancy is `(sum net R) / measured trades`, equivalent to win rate
times average win minus loss rate times average loss, with breakevens retained
in the denominator.

Compare results over a meaningful sample and untouched forward periods. Track
costs, slippage, missing-event exclusions and configuration version together.
Report dispersion and confidence intervals in later research before concluding
that one setup/session is better. Replay alternative BE/trailing policies
against ordered tick/bar paths; MFE alone cannot prove a counterfactual exit.
Never optimize parameters on a handful of trades or automatically retune live
settings. No profitability claim or historical profitability backtest is made.

## Commands and verification

- `/auto Gold`: selective Python strategy.
- `/buy Gold`, `/sell Gold`: explicit legacy EMA-direction entry modes, with
  current AUTO assessment warnings; no AUTO gate applied.
- `/ematrade Gold`: automatic direction using the old EMA confluence rules.
- `/leveltrade Gold`: explicit old two-sided untouched key-level limits.
- `/notrade Gold`: cancel pending entries and stop new entries; keep managing
  existing positions and their protective brackets.
- `/setup Gold`: read-only current setup/why-wait report. A stale quote reports
  wait; it does not fetch or invent a fresh price.
- `/why Gold`: latest Python decision, including rejection reason.
- `/performance Gold`: measured journal outcomes and grouped expectancy.

Run `python -m pytest -q`. Compile canonical Webhook1, Webhook2 and TPSL, run
`python -m webhook.sync_mq5`, compile live copies, and compare all source hashes.
Do not confuse successful compilation with broker execution validation. Next
validate on a demo account: entry/SL/TP, spread widening, restart with a position,
outage/replayed exits, symbol volume steps, hedging and netting partial reduction,
and interaction with any other installed position manager. The MQL management
self-check runs on Webhook2 initialization. No test should place real trades.
The Python suite also compiles and runs the verbatim MQL stop/partial arithmetic
as C++ with standard math aliases when g++ (native or WSL) is available. This
checks arithmetic boundaries; it does not emulate broker order handling.

Implementation references: [MT5 OrderCalcProfit](https://www.mql5.com/en/docs/trading/ordercalcprofit)
for account-currency risk and [MT5 trade execution principles](https://www.metatrader5.com/en/terminal/help/trading/performing_deals)
for netting reductions. These document platform semantics, not strategy expectancy.

## Verification completed on 2026-09-09

- `python -m pytest -q`: **223 passed**, including actual MQL management
  arithmetic compiled and executed through WSL g++.
- Canonical and live Webhook1, Webhook2 and TPSL: **0 errors, 0 warnings** each.
- `python -m webhook.sync_mq5`: all seven canonical/live source pairs match
  byte-for-byte. Live sources matched the pre-change repository before sync.
- `git diff --check`: passed with the repository's normal line-ending settings.
- MetaTrader was not running. No real trades, server restart, commits or pushes
  were performed. Start/restart Python and validate the compiled EAs on a demo
  account before relying on live execution. Profitability remains unmeasured.
