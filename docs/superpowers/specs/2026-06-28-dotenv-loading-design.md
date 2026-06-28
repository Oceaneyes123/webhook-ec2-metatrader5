# Automatic `.env` Loading

## Goal

Load repository-local `.env` values when `webhook.py` starts so Telegram
credentials and other settings are available without manual PowerShell setup.

## Design

- Add a small standard-library loader in `webhook.py`.
- Read `.env` next to `webhook.py`, independent of the current directory.
- Ignore blank lines and comments.
- Split assignments at the first `=`, trim whitespace and matching quotes.
- Never overwrite variables already present in the process environment.
- Load before module-level configuration such as `MARKET_STATE` is initialized.
- Do nothing when `.env` does not exist.

## Verification

Add focused tests proving that:

1. `.env` values are loaded.
2. Existing process variables take precedence.
3. Missing `.env` files are harmless.

Run the full Python unit test suite and syntax compilation.
