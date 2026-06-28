# Automatic `.env` Loading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `webhook.py` load repository-local `.env` settings automatically.

**Architecture:** Add one standard-library `load_dotenv` function to `webhook.py` and call it before module-level configuration is initialized. Existing process environment variables remain authoritative.

**Tech Stack:** Python standard library and `unittest`

---

### Task 1: Load `.env`

**Files:**
- Modify: `webhook.py`
- Test: `test_webhook.py`

- [ ] **Step 1: Write failing tests**

Add tests that call `webhook.load_dotenv` with a temporary file and verify plain
and quoted values load, existing environment variables win, and a missing file
does not fail.

- [ ] **Step 2: Verify the tests fail**

Run:

```powershell
python -m unittest test_webhook.WebhookTest.test_load_dotenv test_webhook.WebhookTest.test_load_dotenv_ignores_missing_file
```

Expected: errors because `webhook.load_dotenv` does not exist.

- [ ] **Step 3: Implement the loader**

Add `load_dotenv(path=None)` using `pathlib.Path`, line parsing with
`str.split("=", 1)`, quote trimming, and `os.environ.setdefault`. Call it before
`logger`, `MARKET_STATE`, and other module-level state are initialized.

- [ ] **Step 4: Verify focused and full tests**

Run:

```powershell
python -m unittest test_webhook.WebhookTest.test_load_dotenv test_webhook.WebhookTest.test_load_dotenv_ignores_missing_file
python -m unittest test_webhook.py
python -m py_compile webhook.py test_webhook.py
```

Expected: all tests pass and compilation exits successfully.

No commit or push: repository instructions prohibit unrequested commits.
