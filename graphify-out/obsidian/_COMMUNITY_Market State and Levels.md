---
type: community
cohesion: 0.09
members: 33
---

# Market State and Levels

**Cohesion:** 0.09 - loosely connected
**Members:** 33 nodes

## Members
- [[.__init__()_3]] - code - webhook/market_state.py
- [[._ema_bias()]] - code - webhook/market_state.py
- [[._invalidate_patterns()]] - code - webhook/market_state.py
- [[._load()]] - code - webhook/market_state.py
- [[._pattern_key()]] - code - webhook/market_state.py
- [[._process_patterns()]] - code - webhook/market_state.py
- [[._save()]] - code - webhook/market_state.py
- [[.mark_notified()]] - code - webhook/market_state.py
- [[.update()]] - code - webhook/market_state.py
- [[Candle-Defined Chart Axis]] - document - docs/superpowers/plans/2026-07-02-levels-candlestick-visibility.md
- [[Candle-First Key Levels Chart]] - code - webhook/market_chart.py
- [[Chart Level and Candle Selection]] - code - webhook/market_chart.py
- [[Chronological Candle History Normalization]] - document - docs/superpowers/plans/2026-07-02-levels-candlestick-visibility.md
- [[Deterministic BUY SELL WAIT Confluence]] - document - docs/superpowers/specs/2026-06-28-market-summary-levels-design.md
- [[EMA and Pattern Timeframe Roles]] - document - docs/superpowers/specs/2026-06-28-market-summary-levels-design.md
- [[Ingest a TIMEFRAME_SNAPSHOT payload.          Returns a list of notification dic]] - rationale - webhook/market_state.py
- [[Levels Candle-First Chart Plan]] - document - docs/superpowers/plans/2026-07-02-levels-candlestick-visibility.md
- [[Levels Chart Delivery Flow]] - code - webhook/polling.py
- [[Mark a notification as having been sent, so it won't fire again.]] - rationale - webhook/market_state.py
- [[Mark retained patterns from other timeframes as invalidated.]] - rationale - webhook/market_state.py
- [[Market State Analyzer and Chart Singletons]] - code - webhook/state.py
- [[Market Summary and Levels Design]] - document - docs/superpowers/specs/2026-06-28-market-summary-levels-design.md
- [[Market Summary and Levels Plan]] - document - docs/superpowers/plans/2026-06-28-market-summary-levels.md
- [[MarketState]] - code - webhook/market_state.py
- [[Pattern and EMA Notification Pipeline]] - code - webhook/market_state.py
- [[Pause Suppresses Alerts but Preserves State]] - document - docs/superpowers/specs/2026-06-28-market-summary-levels-design.md
- [[Retained Pattern Invalidation]] - code - webhook/market_state.py
- [[Shared Runtime State]] - code - webhook/state.py
- [[Support, Resistance, Fibonacci, PDHPDL, and FVG Levels]] - document - docs/superpowers/specs/2026-06-28-market-summary-levels-design.md
- [[Thread-safe persistence manager for symboltimeframe market snapshots.]] - rationale - webhook/market_state.py
- [[Timeframe Snapshot Validation]] - code - webhook/market_state.py
- [[Unified Timeframe Snapshot Pipeline]] - document - docs/superpowers/plans/2026-06-28-market-summary-levels.md
- [[Unique key for a pattern within a symboltimeframe.]] - rationale - webhook/market_state.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Market_State_and_Levels
SORT file.name ASC
```

## Connections to other communities
- 8 edges to [[_COMMUNITY_Market Analysis Tests]]
- 2 edges to [[_COMMUNITY_Shared Test Fixtures]]
- 2 edges to [[_COMMUNITY_Local Server Runtime]]
- 1 edge to [[_COMMUNITY_Server and Commands]]

## Top bridge nodes
- [[MarketState]] - degree 20, connects to 3 communities
- [[.update()]] - degree 8, connects to 1 community
- [[.mark_notified()]] - degree 5, connects to 1 community
- [[Candle-First Key Levels Chart]] - degree 4, connects to 1 community
- [[Levels Chart Delivery Flow]] - degree 4, connects to 1 community