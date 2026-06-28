# Local-Default Setup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Python webhook and MQ5 EA use `127.0.0.1:8000` by default and document local setup.

**Architecture:** Keep runtime overrides available through Python environment variables and one MQ5 URL input. Preserve the systemd unit unchanged for future use.

**Tech Stack:** Python standard library, MQL5, PowerShell, `unittest`

---

### Task 1: Lock local defaults with failing tests

**Files:**
- Modify: `test_webhook.py`
- Modify: `test_sync_mq5.py`

- [ ] Change the server-default assertion to require `127.0.0.1:8000`.
- [ ] Add a canonical MQ5 contract test requiring one local `WebhookUrl` and rejecting production environment constants and public IPs.
- [ ] Run both targeted tests and confirm they fail against current defaults.

### Task 2: Implement local Python and MQ5 defaults

**Files:**
- Modify: `webhook.py`
- Modify: `mq5/Webhook.mq5`

- [ ] Change Python's default host and public URL to `127.0.0.1`.
- [ ] Replace MQ5 environment selection with one configurable local-default URL.
- [ ] Remove public IP help text and environment logging from MQ5.
- [ ] Run targeted tests until green.

### Task 3: Document and verify local setup

**Files:**
- Modify: `README.md`

- [ ] Document PowerShell environment variables, local startup, health check, MT5 WebRequest setup, canonical MQ5 sync, commands, testing, and troubleshooting.
- [ ] Retain `webhook-ec2.service` unchanged and mention it only as an optional future Linux artifact.
- [ ] Compile canonical MQ5, run `python sync_mq5.py`, verify hashes, and compile live MQ5.
- [ ] Run all Python tests, byte-compilation, and `git diff --check`.
- [ ] Do not commit or push.
