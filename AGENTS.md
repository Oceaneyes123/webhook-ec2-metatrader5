# Repository Instructions

## MQ5 Source Workflow

`mq5/Webhook.mq5` is the canonical, tracked MQ5 source. Root `Webhook.mq5` is
a symlink to the live MetaTrader Experts file and remains available for easy
inspection.

For every MQ5 change:

1. Edit `mq5/Webhook.mq5` first.
2. Run relevant tests and compile the canonical file.
3. Run `python sync_mq5.py`.
4. Compile or reload the live MetaTrader file.
5. Verify the canonical and live files match when the change is complete.

Never edit root `Webhook.mq5` directly. Doing so changes the live MetaTrader
file before the repository source. `sync_mq5.py` is intentionally one-way from
the canonical file to the live file.

The script targets root `Webhook.mq5` by default. Set `MT5_MQ5_PATH` to use a
different MetaTrader installation.

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
