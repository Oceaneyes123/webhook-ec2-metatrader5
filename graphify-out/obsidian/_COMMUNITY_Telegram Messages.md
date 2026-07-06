---
type: community
cohesion: 0.50
members: 4
---

# Telegram Messages

**Cohesion:** 0.50 - moderately connected
**Members:** 4 nodes

## Members
- [[Escaped EA Issue Message]] - code - webhook/messages.py
- [[Telegram Message Formatting]] - code - webhook/messages.py
- [[Trade Close Notifications]] - document - README.md
- [[Trade Open and Close Notifications]] - code - webhook/messages.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Telegram_Messages
SORT file.name ASC
```
