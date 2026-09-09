"""Repository entry point for canonical-to-live MQL5 synchronization."""

from webhook.sync_mq5 import main

if __name__ == "__main__":
    raise SystemExit(main())
