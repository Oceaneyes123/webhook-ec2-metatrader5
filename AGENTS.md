# Repository Instructions

## MQ5 Source Workflow

The canonical, tracked MQL5 sources are:

- `mq5/Webhook1.mq5`
- `mq5/Webhook2.mq5`
- `mq5/includes/WebhookCommon.mqh`
- `mq5/includes/MarketSnapshot.mqh`
- `mq5/includes/TradeManager.mqh`

Root `Webhook1.mq5` and `Webhook2.mq5` are symlinks to the live MetaTrader
Experts files and remain available for easy inspection.

For every MQ5 change:

1. Edit the canonical file under `mq5/` first.
2. Run relevant tests and compile both canonical EAs.
3. Run `python sync_mq5.py`.
4. Compile or reload both live MetaTrader EAs.
5. Verify all canonical and live MQL5 files match when the change is complete.

Never edit the root EA links or live includes directly. Doing so changes the
live MetaTrader files before the repository source. `sync_mq5.py` is
intentionally one-way from the five canonical files to the live files.

The script targets the two root live links and copies shared includes into
their live `includes` directory.

## CodeGraph

This project has a CodeGraph MCP server (`codegraph_*` tools) configured.
Prefer it for structural questions:

| Question | Tool |
| --- | --- |
| Where is a symbol defined? | `codegraph_search` |
| What calls a symbol? | `codegraph_callers` |
| What does a symbol call? | `codegraph_callees` |
| What would a change affect? | `codegraph_impact` |
| Show a symbol's source or signature | `codegraph_node` |
| Get focused task context | `codegraph_context` |
| Explore related symbols together | `codegraph_explore` |
| List indexed files | `codegraph_files` |
| Check index health | `codegraph_status` |

Use native search for literal text queries or after opening a specific file.
Trust CodeGraph structural results instead of rechecking them with grep. If
`.codegraph/` is missing, ask before running `codegraph init -i`.

## Git

- Never commit unless explicitly requested.
- Never push commits.
