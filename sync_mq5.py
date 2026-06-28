import os
import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).parent
CANONICAL = ROOT / "mq5" / "Webhook.mq5"
LIVE_LINK = ROOT / "Webhook.mq5"


def sync_mq5(source=CANONICAL, target=None):
    source = Path(source)
    target = Path(target or os.environ.get("MT5_MQ5_PATH", LIVE_LINK)).expanduser()
    if not source.is_file():
        raise FileNotFoundError(f"canonical MQ5 source not found: {source}")
    if source.resolve() == target.resolve():
        raise ValueError("canonical source and live target are the same file")
    if not target.resolve().parent.is_dir():
        raise FileNotFoundError(f"live MQ5 directory not found: {target.resolve().parent}")

    shutil.copy2(source, target)
    return source.resolve(), target.resolve()


if __name__ == "__main__":
    try:
        copied_source, copied_target = sync_mq5()
    except (OSError, ValueError) as error:
        print(f"MQ5 sync failed: {error}", file=sys.stderr)
        raise SystemExit(1)
    print(f"Copied {copied_source} -> {copied_target}")
