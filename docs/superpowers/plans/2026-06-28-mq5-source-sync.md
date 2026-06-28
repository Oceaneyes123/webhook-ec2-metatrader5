# MQ5 Source Sync Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `mq5/Webhook.mq5` the canonical repository source while preserving root `Webhook.mq5` as a live MetaTrader symlink.

**Architecture:** A standard-library Python script copies the canonical file one way to the live target. Repository instructions require canonical-first edits and prohibit direct symlink edits.

**Tech Stack:** Python standard library, MQL5, `unittest`

---

### Task 1: Lock the sync contract

**Files:**
- Create: `test_sync_mq5.py`

- [ ] Add a subprocess test that sets `MT5_MQ5_PATH` to a temporary destination, runs `sync_mq5.py`, and asserts byte-for-byte equality with `mq5/Webhook.mq5`.
- [ ] Add a test that sets the target to the canonical file and expects a nonzero exit with a same-file error.
- [ ] Run `python -m unittest test_sync_mq5.py` and confirm failure because the script and canonical copy do not exist.

### Task 2: Add the canonical source and sync command

**Files:**
- Create: `mq5/Webhook.mq5`
- Create: `sync_mq5.py`

- [ ] Copy the current live MQ5 source exactly into `mq5/Webhook.mq5`; do not replace root `Webhook.mq5`.
- [ ] Implement `sync_mq5.py` with `pathlib`, `os`, and `shutil.copy2`; default to root `Webhook.mq5`, honor `MT5_MQ5_PATH`, reject missing paths and identical resolved files, and print the completed copy.
- [ ] Run `python -m unittest test_sync_mq5.py` and confirm both tests pass.

### Task 3: Document and verify the workflow

**Files:**
- Create: `AGENTS.md`

- [ ] Record the canonical-first MQ5 workflow, CodeGraph usage, and no-commit/no-push rules.
- [ ] Compile `mq5/Webhook.mq5` with MetaEditor.
- [ ] Run `python sync_mq5.py`, verify canonical and live SHA-256 hashes match, then compile the live file.
- [ ] Run all Python tests, byte-compilation, and `git diff --check`.
- [ ] Do not commit or push.
