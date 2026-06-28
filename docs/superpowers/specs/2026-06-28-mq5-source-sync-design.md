# MQ5 Source Sync Design

## Goal

Keep the root `Webhook.mq5` symlink for direct access to MetaTrader while
making a regular repository file the authoritative MQ5 source.

## Workflow

- `mq5/Webhook.mq5` is the canonical source and receives every MQ5 edit first.
- Root `Webhook.mq5` remains a symlink to the live MetaTrader Experts file.
- `sync_mq5.py` copies the canonical source to the live file after changes.
- The default live target is the symlink target. `MT5_MQ5_PATH` may override
  it for another MetaTrader installation.
- Sync is one-way only. The script never copies live changes back into the
  repository.

## Safety and Validation

The sync script rejects a missing canonical source, missing live target
directory, or source and target resolving to the same file. It uses
`shutil.copy2` and reports the copied source and destination.

A standard-library unit test copies between temporary files and verifies that
the destination exactly matches the canonical source.

`AGENTS.md` requires this sequence for all MQ5 work:

1. Edit `mq5/Webhook.mq5`.
2. Run relevant tests and compile the canonical file.
3. Run `python sync_mq5.py`.
4. Compile or reload the live MetaTrader file.

Agents must not edit root `Webhook.mq5` directly because it writes through the
symlink to the live installation.
