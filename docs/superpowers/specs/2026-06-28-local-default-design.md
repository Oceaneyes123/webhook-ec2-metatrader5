# Local-Default Setup Design

## Goal

Run the webhook and MT5 EA locally on `127.0.0.1:8000` by default while
retaining the existing systemd service file for possible future Linux use.

## Changes

- Python binds to `127.0.0.1` and reports
  `http://127.0.0.1:8000/webhook` when no environment overrides are set.
- Canonical `mq5/Webhook.mq5` uses one configurable `WebhookUrl` input with
  local URL default. Production environment switching and hardcoded public IPs
  are removed.
- Canonical MQ5 changes are synchronized through `python sync_mq5.py`.
- README becomes a local-first Windows and MT5 setup guide using PowerShell
  environment variables and local health/webhook URLs.
- `webhook-ec2.service` remains unchanged and is identified only as an
  optional future Linux deployment artifact.

## Validation

Python tests lock the local server default and canonical MQ5 configuration.
The full Python suite and byte-compilation run after changes. MetaEditor
compiles the canonical source, the sync script updates the live source, hashes
must match, and MetaEditor compiles the live source.
