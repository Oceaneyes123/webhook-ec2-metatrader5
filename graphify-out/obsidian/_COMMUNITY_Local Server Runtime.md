---
type: community
cohesion: 0.11
members: 21
---

# Local Server Runtime

**Cohesion:** 0.11 - loosely connected
**Members:** 21 nodes

## Members
- [[127.0.0.18000 Default]] - document - docs/superpowers/plans/2026-06-28-local-default.md
- [[Atomic Market-State Persistence]] - code - webhook/market_state.py
- [[Atomic Trade-State Persistence]] - code - webhook/trade_state.py
- [[EA Heartbeat Ingestion]] - code - webhook/server.py
- [[EA Heartbeat Monitoring]] - document - README.md
- [[Local MT5 Webhook-to-Telegram Architecture]] - document - README.md
- [[Local-Default Setup Design]] - document - docs/superpowers/specs/2026-06-28-local-default-design.md
- [[Local-Default Setup Plan]] - document - docs/superpowers/plans/2026-06-28-local-default.md
- [[Optional Future Linux Deployment]] - document - docs/superpowers/specs/2026-06-28-local-default-design.md
- [[Persistent Trade Mode State]] - code - webhook/trade_state.py
- [[Symbol-Specific Trade Mode Overrides]] - code - webhook/trade_state.py
- [[Telegram Command Surface]] - document - README.md
- [[Telegram HTTP Transport]] - code - webhook/telegram_sender.py
- [[Telegram Long Polling]] - code - webhook/polling.py
- [[Telegram Multipart Photo Upload]] - code - webhook/telegram_sender.py
- [[Telegram Request Retry Policy]] - code - webhook/telegram_sender.py
- [[Trade Configuration Endpoint]] - code - webhook/server.py
- [[Trade Configuration Projection]] - code - webhook/trade_state.py
- [[Webhook Event Dispatch]] - code - webhook/server.py
- [[Webhook HTTP Server]] - code - webhook/server.py
- [[Webhook2 Trade Config Cache]] - document - README.md

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Local_Server_Runtime
SORT file.name ASC
```

## Connections to other communities
- 2 edges to [[_COMMUNITY_Market State and Levels]]

## Top bridge nodes
- [[Atomic Market-State Persistence]] - degree 2, connects to 1 community
- [[Telegram Multipart Photo Upload]] - degree 2, connects to 1 community