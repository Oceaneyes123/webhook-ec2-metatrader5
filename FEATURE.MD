In this repository  implement the following features while preserving the current architecture, existing Telegram commands, webhook behavior, market analysis, trade management, EA heartbeat system, symbol aliases, and tests.

Do not replace working functionality unnecessarily. Extend the existing modular structure and reuse the current event dispatcher, Telegram sender, command registry, message formatting, state management, trade configuration, and shared MQL5 include files where appropriate.

Before making changes:

* Review the complete repository.
* Identify the current trade-open and trade-close detection flow.
* Identify how Telegram polling, commands, callbacks, alerts, market snapshots, symbol normalization, and trade state currently work.
* Identify whether the account is operating in netting or hedging mode and ensure the implementation works safely for both.
* Preserve backward compatibility for existing webhook event payloads and Telegram commands.
* Add or update automated tests for every new behavior.
* Update the README with all new commands, configuration values, event payload descriptions, buttons, schedules, and safety behavior.

## 1. Replace Timer-Based Trade Detection With `OnTradeTransaction()`

Replace the current position-open and position-close detection that compares position state during the timer loop.

Use `OnTradeTransaction()` as the primary mechanism for detecting all account trade activity.

The monitoring must cover all trades in the MetaTrader account, regardless of:

* Symbol
* Chart where the EA is attached
* Magic number
* Whether the position was opened manually
* Whether the position was opened by Webhook2
* Whether the position was opened by another EA

Detect and report meaningful trade events, including:

* Position opened
* Position closed
* Partial close
* Pending order created
* Pending order modified
* Pending order cancelled
* Pending order filled
* Stop-loss modified
* Take-profit modified
* Stop-loss hit
* Take-profit hit
* Manual close
* Broker or EA trade-operation rejection

Every event must contain enough identifiers to distinguish individual transactions and prevent ambiguity when several positions exist at the same time.

Include relevant fields such as:

* Account login
* Broker server
* Symbol
* Position ticket
* Order ticket
* Deal ticket
* Magic number
* Trade direction
* Volume
* Entry price
* Exit price
* Stop-loss
* Take-profit
* Realized profit
* Commission
* Swap
* Close reason
* Event time
* Event source

Create a unique event identifier so retrying the same webhook request does not produce duplicate Telegram alerts.

Keep the existing timer for responsibilities that still need periodic execution, such as trade management, heartbeat transmission, reconciliation, or scheduled checks. It must no longer be the primary method for detecting whether trades opened or closed.

Add periodic account reconciliation as a backup. The EA should occasionally send or compare the current positions and pending orders so the Python application can recover if a transaction event was missed.

The implementation must correctly handle:

* Multiple simultaneous positions
* Hedging accounts
* Netting accounts
* Several positions closing close together
* A position closing while another remains open
* Partial closes
* Multiple deals belonging to one position
* Manual and EA trades existing together
* Restarting the EA while positions are already open
* Restarting the Python service
* Duplicate transaction events
* Events arriving out of order

## 2. Add `/price` Command

Add a Telegram command using this format:

`/price <symbol>`

The command should use the project’s existing symbol-normalization and alias system.

The response must include:

* Normalized display symbol
* Current bid
* Current ask
* Current spread
* Daily open
* Daily high
* Daily low
* Percentage change from the daily open
* Timestamp of the latest price
* Age of the latest price data

Display a clear warning when the available market data is stale.

The command must not silently display old data as current data.

Where practical, use the latest MetaTrader-provided market snapshot rather than relying on an external price source.

Return a helpful usage message when the symbol is missing or unavailable.

## 3. Add `/market` Command

Add a Telegram command using this format:

`/market <symbol>`

The market report should focus on:

* M5 EMA trend
* Current trading-session status

Use the existing EMA data and existing project conventions. Prefer reusing the EMA periods already collected by the repository rather than introducing unrelated indicators.

The M5 EMA trend should give a simple result such as:

* Bullish
* Bearish
* Mixed
* Unavailable
* Stale

The response should briefly explain the basis of the result, such as the relative positioning of the existing M5 EMAs.

The session section should show whether the market is currently within:

* Asian session
* London session
* New York session
* An overlap between sessions
* Outside the configured sessions

Session calculations must use recognized market time zones and automatically account for daylight saving changes for London and New York.

Display session times in Philippine time for the user.

The implementation must not use hard-coded fixed UTC offsets for London and New York throughout the entire year.

## 4. Add Profit-Protection Alerts

Monitor every open position in the account, regardless of symbol, magic number, or source.

Send a profit-protection alert when an individual position first reaches at least 50 pips in profit.

Requirements:

* Calculate pips using the correct configured or symbol-specific pip size.
* Support Gold and broker-specific symbol variations correctly.
* Trigger the 50-pip alert only once for each position.
* Store the triggered state so restarting the Python service does not send the same threshold alert repeatedly.
* Do not trigger the alert again merely because profit falls below and later returns above 50 pips.
* Include the position ticket so separate positions on the same symbol are tracked independently.

The alert should show:

* Symbol
* Direction
* Position ticket
* Entry price
* Current price
* Current profit in pips
* Current floating profit in account currency
* Current stop-loss
* Current take-profit
* Position duration

The alert should include relevant Telegram action buttons.

## 5. Make Alerts Actionable With Telegram Buttons

Add Telegram inline buttons to appropriate trade and profit-protection alerts.

Required buttons:

* `Move SL to BE`
* `Close Profitable Positions`

Use Telegram callback queries and integrate them cleanly with the existing Telegram polling system.

### Move SL to BE

This action must apply to all currently open positions in the account that are more than 30 pips in profit.

For each eligible position:

* Move the stop-loss to secure approximately 10 pips of profit.
* For a buy position, place the stop-loss above the entry price by 10 pips.
* For a sell position, place the stop-loss below the entry price by 10 pips.
* Use the correct symbol-specific pip size.
* Normalize prices according to the symbol’s tick size and digits.
* Respect the broker’s stop level, freeze level, and modification restrictions.
* Never move a stop-loss backward to a worse level.
* Skip positions already protected by a better stop-loss.
* Skip positions that are no longer above 30 pips in profit when confirmation occurs.
* Report which positions were modified, skipped, or failed.

Because this action may modify multiple positions, require confirmation before execution.

The confirmation message should clearly show:

* Number of currently eligible positions
* Symbols involved
* The intended protected-profit level
* Confirm button
* Cancel button

Revalidate all positions after the user confirms. Do not rely only on the state from when the first button was pressed.

### Close Profitable Positions

This action must close every currently profitable open position in the account.

A profitable position means its current floating profit is greater than zero in account currency.

Apply this regardless of:

* Symbol
* Magic number
* Whether the position is manual
* Whether the position was opened by this project
* Number of pips in profit

Require confirmation before execution.

The confirmation message should show:

* Number of currently profitable positions
* Symbols
* Approximate combined floating profit
* Confirm button
* Cancel button

After confirmation:

* Re-fetch the current positions.
* Close only positions that are still profitable.
* Do not close positions that became unprofitable before execution.
* Report each successful close, skipped position, and failure.
* Include the final realized result when available.

### Telegram Button Security and Reliability

Implement the following safeguards:

* Accept callbacks only from the configured authorized Telegram chat.
* Prefer validating the Telegram user ID when available.
* Use short-lived confirmation tokens.
* Expire old confirmations.
* Prevent the same callback from being executed twice.
* Answer callback queries so Telegram does not leave the loading indicator active.
* Log every requested, confirmed, cancelled, successful, skipped, and failed action.
* Do not embed sensitive account details or credentials in callback data.
* Keep callback data within Telegram limits.
* Provide a clear message when no positions are eligible.

The Python service should send trade-action instructions to MetaTrader through a safe mechanism compatible with the existing architecture. MetaTrader must return an execution result so Telegram can report the real outcome rather than assuming success.

## 6. Add Daily 24-Hour Report

Send an automatic daily report at 6:00 AM Philippine time.

The reporting period must cover the immediately preceding 24 hours, not the previous calendar day.

For example, a report sent at 6:00 AM should cover activity from 6:00 AM the previous day until 6:00 AM today.

The report should cover all account trades and include:

* Starting balance when available
* Ending balance
* Current equity
* Number of positions opened
* Number of positions closed
* Number of winning closed trades
* Number of losing closed trades
* Breakeven trades
* Gross profit
* Gross loss
* Net realized profit
* Commission
* Swap
* Win rate
* Largest winning trade
* Largest losing trade
* Current open positions
* Current floating profit or loss
* Number of 50-pip profit alerts triggered
* Number of breakeven actions performed
* Number of profitable-position close actions performed
* Manual trade count
* EA trade count when identifiable

Clearly state the exact start and end timestamps of the reporting period in Philippine time.

Avoid dividing by zero or showing misleading statistics when there were no closed trades.

The report schedule must remain correct after service restarts and should avoid sending duplicate reports for the same reporting window.

## 7. Add End-of-Session Reports

Generate reports at the end of all three sessions:

* Asian
* London
* New York

Use authoritative time-zone definitions and automatically account for daylight saving time where applicable.

Convert the session-end schedule to Philippine time for delivery.

Each session report should include:

* Session name
* Exact session start and end
* Session times in Philippine time
* Symbols observed during the session
* Session open
* Session high
* Session low
* Session close or latest available price
* Price change
* Percentage change
* Number of trades opened during the session
* Number of trades closed during the session
* Realized profit or loss during the session
* Remaining open positions
* M5 EMA trend at the session end
* Largest move observed
* Important alerts triggered during the session

When London or New York daylight saving changes, the Philippine delivery time must adjust automatically.

Avoid sending duplicate session reports after restarts.

If the service was offline at the exact session end, send the missed report after recovery when enough data exists, clearly marking it as delayed.

## 8. Add Entry-Decision Report

Add an entry-decision reporting system for the existing Webhook2 entry logic.

The report must be available in two ways:

1. Telegram command:

`/why <symbol>`

2. Automatic notification whenever an entry attempt is rejected.

The report should remain concise.

Only show:

* Symbol
* Requested direction
* Final result: PASS or FAIL
* Final rejection reason when failed
* Decision timestamp
* Data freshness

Do not list every indicator value or every successful condition.

Examples of rejection reasons may include:

* M1 EMA direction failed
* M5 candle alignment failed
* M15 candle alignment failed
* Market data unavailable
* Indicator data unavailable
* Spread too high, when applicable
* Existing position prevents entry
* Pending order conflict
* Trading mode is NOTRADE
* Trade configuration unavailable
* Broker restriction
* Stale market data

When several rules fail, return the primary rejection reason that most directly prevented the entry. Define and document a consistent priority order for rejection reasons.

The `/why` command should return the latest decision for the requested normalized symbol.

Include the age of that decision and warn when it is stale.

Automatic rejection messages should have deduplication or cooldown logic so the same failed condition does not repeatedly spam Telegram on every timer execution.

A new message may be sent when:

* The rejection reason changes
* The requested direction changes
* The decision changes from PASS to FAIL
* The decision changes from FAIL to PASS
* A configured cooldown expires

Successful entry decisions may be stored for `/why` without requiring automatic Telegram alerts unless an actual order or trade event already generates one.

## 9. Persistence

Persist data needed for these features.

Use a lightweight local database, preferably SQLite, unless the repository already has a more suitable persistent data layer.

Persist at least:

* Processed transaction-event identifiers
* Position tracking state
* Profit-alert threshold state per position
* Latest price and market data timestamps
* Entry-decision reports
* Telegram confirmation tokens
* Telegram action audit records
* Daily report windows already sent
* Session reports already sent
* Trade events needed for reports

The application must recover cleanly after restarting.

Do not depend only on in-memory lists for features requiring historical accuracy or deduplication.

Provide safe database initialization and migration behavior.

## 10. Configuration

Add clear configuration options for:

* Philippine reporting timezone
* Daily report time, defaulting to 6:00 AM
* Session definitions
* Profit-alert threshold, defaulting to 50 pips
* Breakeven eligibility threshold, defaulting to more than 30 pips
* Breakeven protected profit, defaulting to 10 pips
* Price-data stale threshold
* Entry-decision rejection cooldown
* Confirmation expiration time
* Authorized Telegram chat
* Optional authorized Telegram user
* Account-wide action enable or disable switch
* Session report enable or disable options
* Daily report enable or disable option

Use environment variables or the repository’s existing configuration approach.

Do not hard-code credentials or secrets.

## 11. Safety Requirements

Because this project can modify and close live trades:

* Preserve a safe default mode.
* Do not enable destructive Telegram actions unless explicitly configured.
* Validate every action immediately before execution.
* Never assume an order modification or close succeeded.
* Return the real MetaTrader result code and readable failure reason.
* Handle market-closed conditions.
* Handle connection failures.
* Handle symbol trading restrictions.
* Handle invalid stops.
* Handle requotes and price changes where applicable.
* Handle partially successful account-wide actions.
* Avoid blocking the webhook request while Telegram or report generation is slow.
* Prevent duplicate executions caused by retries.
* Do not expose the Telegram bot token, chat ID, account login, or other secrets in logs, documentation examples, tests, or committed files.
* Review the repository for accidentally committed credentials and replace them with placeholders or environment-variable instructions.

## 12. Testing Requirements

Add automated tests covering at least:

* Trade opened through `OnTradeTransaction()`
* Trade closed through `OnTradeTransaction()`
* Stop-loss hit
* Take-profit hit
* Manual close
* Partial close
* Multiple simultaneous positions
* Multiple transactions arriving rapidly
* Duplicate events
* Out-of-order events
* Restart recovery
* `/price` output
* Stale `/price` data
* `/market` M5 trend status
* Session status across daylight saving changes
* 50-pip alert firing once
* Separate alerts for separate position tickets
* Correct pip calculation for broker-specific Gold symbols
* Breakeven eligibility above 30 pips
* Breakeven placement at approximately 10 pips profit
* Existing better stop-loss not moved backward
* Broker stop-level rejection
* Closing all currently profitable positions
* A position becoming unprofitable before confirmation
* Confirmation expiration
* Duplicate callback prevention
* Unauthorized Telegram callback
* Daily 24-hour reporting window
* Daily report deduplication
* Asian session report
* London daylight saving schedule
* New York daylight saving schedule
* Entry-decision PASS result
* Entry-decision rejection reason
* Automatic rejection-alert cooldown
* `/why` stale-decision warning
* Telegram delivery failure and retry
* Partial success when modifying or closing multiple positions

Use fixtures representing realistic MetaTrader transaction payloads.

## 13. Documentation

Update the README with:

* New architecture and data flow
* `OnTradeTransaction()` responsibilities
* Any new EA or shared include
* New webhook event types
* `/price`
* `/market`
* `/why`
* Daily report schedule
* Session-report schedules
* Daylight saving behavior
* Profit-protection alerts
* Telegram button behavior
* Confirmation workflow
* Account-wide scope of actions
* All configuration variables
* Database location and recovery behavior
* Security requirements
* Setup instructions
* Testing instructions
* Demo-account verification checklist

Clearly warn that:

* `Move SL to BE` can modify all qualifying positions in the account.
* `Close Profitable Positions` can close profitable positions regardless of symbol, magic number, or trade source.
* These features must be tested on a demo account before live use.

## Expected Result

The completed implementation should provide reliable, account-wide trade monitoring based primarily on `OnTradeTransaction()`, current price and M5 market-status commands, one-time 50-pip protection alerts, automatic 24-hour and session reports, confirmed Telegram trade-action buttons, and concise entry-decision reporting.

The implementation should be modular, persistent, testable, resistant to duplicate events, safe across restarts, compatible with the existing repository, and suitable for later expansion without concentrating all logic in one file.
