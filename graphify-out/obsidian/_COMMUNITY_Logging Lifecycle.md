---
type: community
cohesion: 2.00
members: 2
---

# Logging Lifecycle

**Cohesion:** 2.00 - tightly connected
**Members:** 2 nodes

## Members
- [[Five-Hour Log Lifecycle]] - code - webhook/app_logger.py
- [[Log Cleanup Contract Tests]] - code - tests/test_app_logger.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Logging_Lifecycle
SORT file.name ASC
```
