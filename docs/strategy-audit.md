# Strategy audit — before implementation

Reviewed the repository through CodeGraph (Python call paths), canonical MQL5
sources (not indexed), configuration, reports, tests and source-sync workflow.
Baseline: 201 pytest tests pass; canonical Webhook2 compiles with zero errors
and warnings. Generated graph/cache files are derived documentation.

## Existing flow

Webhook1 collects closed M1/M5/M15/M30/H1/H4/D1 candles, EMA20/50, RSI14,
S/R, Fibonacci 38.2/50/61.8, unfilled FVG and previous-day levels. Python
MarketState persists history and confirms external swings, BOS, CHoCH and
level interactions; MarketAnalyzer and MarketChart produce reports. These
Python analyses do not control entries. BigMove is a separate range alert EA.
SQLite AccountStore records transactions, reconciliation, latest decisions
and account reports. Telegram/polling changes persisted trading modes;
Webhook2 polls /trade-config and manages entries on its timer.

1. BUY: M1 EMA20 > EMA50; both open and close of the previous M5 and M15
   candles exceed their EMA20. SELL mirrors these rules.
2. Manual pending entry: BUY at M1 EMA20 minus trail_pips; SELL above EMA20.
   No attached SL/TP. Although TrailPendingOrder supports modification, the
   caller deletes both directions every cycle before recreating the order.
3. AUTO ignores those confluence rules. It creates BUY limits at untouched
   swing lows and SELL limits at untouched swing highs across M30/H1/H4/D1.
   Both directions can coexist. No Python structure, momentum or R:R gate.
4. Key-level orders stay at their original price. Within the cluster distance,
   the lowest BUY/highest SELL survives. Session-opening safety cancels nearby
   key-level orders within its configured time and pip windows.
5. NOTRADE, an EA position, or manual-close cooldown cancels pending limits.
   Failed config fetch eventually stops management but leaves pending orders.
6. TPSL independently supplies missing fixed 100-pip SL/TP by default and
   moves stops at +50 pips to entry plus/minus 10 pips. OnlySetIfMissing keeps
   existing brackets but does not disable its pip-based breakeven.
7. Webhook2 trails pending entries, not position stops. No R-based partials,
   initial-risk journal, MFE/MAE or expectancy analytics exist.

## Expectancy weaknesses and concrete changes

- HTF structure, BOS/CHoCH, RSI, FVG, Fib and previous-day data inform reports
  but not AUTO. Use the existing structure state as the directional gate.
- Blind first-touch entries and two-sided limits permit countertrend/range
  trades. Require location plus closed M5/M15 pullback or break/retest evidence.
- No room/R:R evaluation and initially naked entries. Attach logical SL and
  nearest-structure TP at execution, accounting for spread and broker ticks.
- No expansion/extension gate, session outcomes, loss cooldown or setup
  attempts. Add explicit, configurable gates and durable execution context.
- Pip breakeven can override a sound trade thesis. Give strategy positions
  one manager; retain TPSL only for legacy/manual positions.
- The AUTO Telegram description contradicts execution. Report the actual
  decision and make rejected evidence visible through /why.

The supplied command_trading.py and EMA.mq5 do not exist in this checkout.
/leveltrade and /ematrade are also absent; they will expose the existing
legacy approaches explicitly. EMA100/200 are not collected; optional supplied
values can contribute without adding indicators. Existing session reports
use IANA time zones. The real sync entry point is python -m webhook.sync_mq5,
not the obsolete root sync_mq5.py command in AGENTS.md.

No evidence in this audit establishes profitable parameters. Initial scores
and thresholds are hypotheses to evaluate out of sample, after costs.
