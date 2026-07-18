# EA Acceptance Checklist

Use a demo account. Start with `NOTRADE`; enable live trading only after the relevant checks pass. Mark each item when the stated result is visible in MT5, Telegram, or the webhook log.

## Shared setup and daily health

- [ ] The Python webhook starts and `http://127.0.0.1:8000/health` reports healthy.
- [ ] Telegram is configured and the bot replies to `/status` and `/help`.
- [ ] MT5 allows WebRequest access to `http://127.0.0.1:8000`.
- [ ] Each attached EA uses the intended chart symbol and the correct webhook URL and timeout.
- [ ] A normal webhook/Telegram outage produces a useful MT5 log message; the EA keeps running and resumes when the service returns.
- [ ] Invalid EA inputs prevent that EA from starting and send one clear EA-issue alert rather than placing or changing orders.
- [ ] `/status` shows Webhook1 and Webhook2 as running after their heartbeats arrive, stale after they stop, and missing when they are not attached.
- [ ] Restart the webhook service and MT5 separately. Confirm the EAs reconnect, state and trade modes remain available, and alerts do not repeat unexpectedly.
- [ ] Attach the EAs to a broker symbol alias such as `Goldmicro` or `XAUUSD`. Confirm Telegram reports the expected normalized symbol, such as `GOLD`.

## Webhook1: market data and alerts

### Start-up and data delivery

- [ ] Attach Webhook1 to a chart with algorithmic trading allowed. It starts without an EA issue and sends an initial snapshot for M1, M5, M15, M30, H1, and H4.
- [ ] On each subsequent closed candle, the matching timeframe refreshes once. The still-forming candle does not create a snapshot or alert.
- [ ] Webhook1 sends a heartbeat at the configured interval and `/status` shows its chart symbol and a recent age.
- [ ] Set an invalid `ChartHistoryBars`, `LevelLookbackBars`, `SwingStrength`, `AtrPeriod`, `MinFvgAtrRatio`, or `HeartbeatSeconds`. Webhook1 refuses to start and explains the input issue.
- [ ] Use a chart with too little price history or unavailable indicator data. Webhook1 reports the issue without sending malformed alerts or crashing.

### Quotes, indicators, and Telegram reports

- [ ] `/price Gold` shows current bid, ask, spread, daily open/high/low, percentage change, candle time, and data age from Webhook1.
- [ ] Stop market updates past the configured stale threshold. `/price Gold` flags the quote as stale.
- [ ] `/market Gold` reports the M5 EMA trend and current configured trading session. Check a session boundary and a daylight-saving change for London or New York.
- [ ] `/summary Gold` shows the available M1/M5 EMA bias and M15–H4 pattern confluence.
- [ ] `/rsi Gold` shows current RSI(14) and its 70/30 extreme history for each available timeframe.
- [ ] An M1 or M5 EMA20/EMA50 crossover sends one directional alert. The same bias on later candles does not repeat the crossover alert.
- [ ] `/recent Gold` returns up to five recent alerts for Gold and does not mix in another symbol's alerts.

### Candlestick patterns and alert controls

- [ ] On M15, M30, H1, and H4, exercise each supported setup with suitable historical/demo data: bullish and bearish engulfing, hammer, hanging man, shooting star, inverted hammer, morning star, evening star, and inside-bar breakout.
- [ ] Each valid pattern alert identifies its symbol, timeframe, direction, candle, and relevant price data.
- [ ] A pattern outside M15–H4 does not send a pattern alert.
- [ ] Re-send or revisit an unchanged pattern. It is not alerted twice.
- [ ] Update a different pattern timeframe. Confirm retained patterns from the other monitored timeframes refresh or invalidate as the market state changes.
- [ ] Run `/pause`, allow snapshots and a potential pattern/crossover alert, then run `/summary`, `/levels`, `/rsi`, `/price`, and `/market`. Reports stay current while automatic alerts stay silent.
- [ ] Run `/resume` and verify that new qualifying alerts arrive again; already-notified paused alerts do not flood Telegram.

### Levels and chart history

- [ ] `/levels Gold` shows available M15–H4 support, resistance, Fibonacci 38.2/50/61.8 levels, bullish/bearish fair-value gaps, and previous-day high/low.
- [ ] The levels command delivers its key-level image. Candles, level labels, and FVG zones are legible at the selected `ChartHistoryBars` setting.
- [ ] Test a market where no valid swing, Fibonacci pair, or unfilled FVG exists. The report clearly omits unavailable levels without failing.
- [ ] Change `LevelLookbackBars`, `SwingStrength`, `AtrPeriod`, and `MinFvgAtrRatio` on demo data. Confirm level and FVG selection changes in the expected direction and remains usable.
- [ ] Confirm the M15–H4 level report uses closed candles and the most recent previous-day range, not incomplete data.

## Webhook2: pending-entry management

### Start-up, configuration, and safety

- [ ] Attach Webhook2 only to a chart intended for trade management. It starts without an EA issue and does not publish market snapshots.
- [ ] Set an invalid management interval, heartbeat interval, config refresh period, or stale-cache period. Webhook2 refuses to start and sends an EA issue.
- [ ] With `/notrade`, Webhook2 creates no pending entry and removes its existing buy-limit and sell-limit orders for that symbol and magic number.
- [ ] `/status` shows the default mode and any per-symbol overrides. Restart the webhook service and confirm those modes persist.
- [ ] Run `/buy Gold`, `/sell Gold`, and `/notrade Gold`. Confirm each affects Gold only; other symbol overrides remain unchanged.
- [ ] Run `/buy`, `/sell`, and `/notrade` without a symbol. Confirm each changes the default mode used by symbols without overrides.
- [ ] Check `/why Gold` after each decision. It reports the direction, pass/fail result, reason, market-data age, and decision age.
- [ ] With the server available, confirm Webhook2 obtains the configured mode, lot size, and trail distance from `/trade-config`.
- [ ] Temporarily interrupt the server after a successful fetch. Webhook2 uses a still-valid cached config, then stops trading when the cache exceeds `TradeConfigMaxStaleSeconds`.
- [ ] Start Webhook2 while the config endpoint is unavailable. It places or modifies no order until it has a valid config.
- [ ] Return an invalid lot size or trail distance from the config endpoint. Webhook2 reports the issue and uses only an allowed valid cache, if one exists.

### Buy and sell confluence

- [ ] In BUY mode, confirm no order exists until M1 EMA20 is above EMA50 and the closed M5 and M15 candles are both above EMA20.
- [ ] When BUY confluence passes, Webhook2 creates one buy-limit at EMA20 minus the configured trail pips, below the current ask, using the configured lot size and magic number.
- [ ] As M1 EMA20 moves, the buy-limit trails to the new valid price. It does not modify for insignificant price movement.
- [ ] Break any BUY confluence condition. Webhook2 removes its buy-limit and `/why` identifies the failed condition.
- [ ] In SELL mode, confirm no order exists until M1 EMA50 is above EMA20 and the closed M5 and M15 candles are both below EMA20.
- [ ] When SELL confluence passes, Webhook2 creates one sell-limit at EMA20 plus the configured trail pips, above the current bid, using the configured lot size and magic number.
- [ ] As M1 EMA20 moves, the sell-limit trails to the new valid price. Break sell confluence and confirm the sell-limit is removed.
- [ ] Switch from BUY to SELL and then SELL to BUY. Webhook2 removes the opposite pending order before maintaining the new direction.
- [ ] Use a price that would put a buy limit at or above ask, or a sell limit at or below bid. Webhook2 skips the order and records the reason.
- [ ] Open a position with Webhook2's symbol and magic number. It removes both of its pending limits and creates no second position.
- [ ] Open a manual or another-EA position on the same symbol. Verify the intended one-open-position safety behavior before relying on automated entries.
- [ ] Confirm Webhook2 does not assign TP or SL to its pending entries. The separate TPSL EA owns exit protection.

### Trade and account activity

- [ ] Fill a Webhook2 pending order. Telegram receives the trade-open notification with symbol, direction, entry price, volume, and any SL/TP.
- [ ] Perform manual trades and trades from another EA, including a pending-order create/modify/cancel, fill, full close, partial close, reversal, SL change, TP change, broker rejection, and a netting or hedging case available on the demo account. Telegram records each account-wide transaction with the correct type and identifiers.
- [ ] Repeat or resend a transaction event, then restart the service. Confirm acknowledged transaction alerts do not repeat; a failed delivery can retry.
- [ ] Confirm a stop-loss close, take-profit close, and manual close show the right reason and realized P&L. Check balance when the legacy close notification is used.
- [ ] Let `AccountReconcileSeconds` elapse with positions and pending orders present. Confirm account balance, equity, positions, and pending orders reconcile to the actual MT5 account.
- [ ] Open a sufficiently profitable position. Receive one profit-protection alert with current pips, floating P&L, SL/TP, duration, and the action buttons.

### Account-wide Telegram actions

> Enable `ACCOUNT_ACTIONS_ENABLED`, authorized Telegram chat/user, matching server secret, and Webhook2 `AccountActionSecret` only on a demo account. These actions can affect manual and other-EA positions across the account.

- [ ] An unauthorized Telegram chat or user cannot start an account action.
- [ ] With actions disabled, action buttons and callbacks produce no account change.
- [ ] Select **Move SL to BE**. The confirmation lists only positions above the eligibility threshold; cancel leaves every position unchanged.
- [ ] Confirm **Move SL to BE**. Webhook2 revalidates each selected position and moves SL to the configured protected-pip level, retaining TP.
- [ ] Verify the BE action skips positions below threshold, positions blocked by broker stop/freeze distance, and positions already protected by a better SL. Telegram lists modified, skipped, and failed tickets.
- [ ] Select **Close Profitable Positions**, cancel once, then confirm once. Only still-profitable selected positions close; losing positions remain open.
- [ ] Let a confirmation expire, reuse a confirmation, or repeat an action request. Webhook2 executes it at most once and reports the outcome.
- [ ] Configure a wrong or blank action secret. Webhook2 receives no queued account action and makes no account-wide change.

### Reports and recovery

- [ ] Allow a daily report window to complete. Telegram receives one report for the preceding 24 hours with trade totals, P&L, costs, balances, open exposure, and market summary.
- [ ] Allow each enabled Asian, London, and New York session window to complete. Confirm times follow the sessions' local clocks and adjust for DST.
- [ ] Disable daily reports, all session reports, and one named session in turn. Only the enabled reports send.
- [ ] Stop the service across a report boundary, then restore it within `REPORT_RECOVERY_DAYS`. Confirm a delayed report appears only for a window with stored activity or an account snapshot.

## TPSL: take-profit, stop-loss, and breakeven protection

### Scope and default protection

- [ ] Attach TPSL to the symbol chart that Webhook2 manages. Confirm the Experts log shows its selected TP/SL, breakeven, scope, and timer settings.
- [ ] With `ManageCurrentSymbolOnly=true`, TPSL changes positions and pending orders on its chart symbol only. With it disabled, test the intended account-wide scope on demo first.
- [ ] Set `MagicNumberFilter` to Webhook2's magic number. Confirm TPSL manages only those entries; set it to `0` only after confirming that all magic numbers should be managed.
- [ ] For a new buy position with no SL or TP, TPSL sets SL below entry and TP above entry by the configured pip distances.
- [ ] For a new sell position with no SL or TP, TPSL sets SL above entry and TP below entry by the configured pip distances.
- [ ] Test the configured pip distances on each traded broker symbol, especially metals or symbols with two, three, or five decimal places.
- [ ] With `OnlySetIfMissing=true`, TPSL preserves an existing SL and TP. It fills only the missing protection.
- [ ] With `OnlySetIfMissing=false`, TPSL replaces existing SL and TP with the configured pip-based values. Test only on a disposable demo position.

### Pending orders and breakeven

- [ ] Create buy-limit, sell-limit, buy-stop, sell-stop, buy-stop-limit, and sell-stop-limit orders without SL/TP. TPSL adds the correct directional protection while preserving entry price, expiry, and stop-limit price.
- [ ] With `OnlySetIfMissing=true`, TPSL leaves a fully protected pending order unchanged and fills only a missing SL or TP.
- [ ] Let a buy position reach `BreakevenTriggerPips`. TPSL moves its SL to entry plus `BreakevenOffsetPips` and retains TP.
- [ ] Let a sell position reach the trigger. TPSL moves its SL to entry minus the offset and retains TP.
- [ ] Before the trigger, TPSL does not move SL to breakeven. After it has protected a position, it does not replace that SL with a worse value.
- [ ] Disable `UseBreakeven`. TP/SL setup continues but no breakeven modification occurs.
- [ ] Verify tick-driven updates and the timer fallback both maintain protection at the configured `TimerSeconds` interval.
- [ ] Force a broker rejection, invalid quote, or stop-level restriction. TPSL logs the ticket, broker retcode, and description; it does not alter other positions or orders.

## BigMove: range alerts

- [ ] Attach BigMove to each intended symbol. It initializes its D1 ATR handle and does not alert immediately for the candle already closed at attachment.
- [ ] On a newly closed M15, M30, H1, H2, or H4 candle whose range reaches its threshold percentage of current D1 ATR(14), Telegram sends a BigMove alert with the symbol, close time, range, ATR, threshold, and percentage.
- [ ] Verify the thresholds: M15 16%, M30 22%, H1 32.5%, H2 42.5%, and H4 60% of D1 ATR.
- [ ] A newly closed candle below its threshold produces no alert. A qualifying candle produces one alert only.
- [ ] Run `/pause` before a qualifying candle and confirm BigMove alerts are suppressed; `/resume` restores alerts for later qualifying candles.
- [ ] Set `AtrPeriod` below 1. BigMove refuses to start and does not alert.
- [ ] Make D1 ATR data unavailable or zero. BigMove waits safely and resumes checking when valid ATR data returns.

## Final demo-to-live gate

- [ ] Save screenshots or Telegram message links for one successful test from each section, plus the account-action tests if enabled.
- [ ] Confirm `Webhook1` remains attached for market reports even if Webhook2 is not used.
- [ ] Confirm Webhook2 and TPSL are both attached and configured before enabling entry management on a live account.
- [ ] Set the final trade mode to `NOTRADE`, review open positions and pending orders, then enable only the symbols and features approved for live use.
