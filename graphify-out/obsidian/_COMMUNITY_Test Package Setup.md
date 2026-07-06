---
type: community
cohesion: 1.00
members: 2
---

# Test Package Setup

**Cohesion:** 1.00 - tightly connected
**Members:** 2 nodes

## Members
- [[__init__.py]] - code - tests/__init__.py
- [[webhook-ec2 test suite.  Automatically adds the project root to ``sys.path`` so]] - rationale - tests/__init__.py

## Live Query (requires Dataview plugin)

```dataview
TABLE source_file, type FROM #community/Test_Package_Setup
SORT file.name ASC
```
