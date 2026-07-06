---
type: community
cohesion: 0.36
members: 9
---

# MQL5 Source Workflow

**Cohesion:** 0.36 - loosely connected
**Members:** 9 nodes

## Members
- [[Canonical-First MQL5 Source Workflow]] - document - AGENTS.md
- [[Canonical-to-Live MQL5 Sync]] - code - webhook/sync_mq5.py
- [[MQL5 Source Sync Plan]] - document - docs/superpowers/plans/2026-06-28-mq5-source-sync.md
- [[Market and Trade EA Separation]] - document - docs/superpowers/plans/2026-07-02-two-ea-refactor.md
- [[One-Way Canonical Source Copy]] - document - docs/superpowers/plans/2026-06-28-mq5-source-sync.md
- [[Tracked MQL5 Source Manifest]] - code - webhook/sync_mq5.py
- [[Two-EA MT5 Setup]] - document - README.md
- [[Two-EA Refactor Plan]] - document - docs/superpowers/plans/2026-07-02-two-ea-refactor.md
- [[Two-Target Multi-File Sync]] - document - docs/superpowers/plans/2026-07-02-two-ea-refactor.md

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/MQL5_Source_Workflow
SORT file.name ASC
```
