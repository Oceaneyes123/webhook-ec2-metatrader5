import shutil
import sys
from pathlib import Path


ROOT = Path(__file__).parent
CANONICAL_DIR = ROOT / "mq5"
LIVE_EAS = (ROOT / "Webhook1.mq5", ROOT / "Webhook2.mq5")
RELATIVE_SOURCES = (
    Path("Webhook1.mq5"),
    Path("Webhook2.mq5"),
    Path("includes/WebhookCommon.mqh"),
    Path("includes/MarketSnapshot.mqh"),
    Path("includes/TradeManager.mqh"),
)


def sync_mq5(source_dir=CANONICAL_DIR, live_eas=LIVE_EAS):
    source_dir = Path(source_dir)
    live_eas = tuple(Path(path) for path in live_eas)
    if len(live_eas) != 2:
        raise ValueError("exactly two live EA targets are required")

    live_eas = tuple(path.resolve() for path in live_eas)
    live_dir = live_eas[0].parent
    if live_eas[1].parent != live_dir or not live_dir.is_dir():
        raise FileNotFoundError(f"live MQ5 directory not found: {live_dir}")

    targets = live_eas + tuple(
        live_dir / relative for relative in RELATIVE_SOURCES[2:]
    )
    pairs = tuple(
        ((source_dir / relative).resolve(), target.resolve())
        for relative, target in zip(RELATIVE_SOURCES, targets)
    )
    for source, target in pairs:
        if not source.is_file():
            raise FileNotFoundError(f"canonical MQ5 source not found: {source}")
        if source == target:
            raise ValueError("canonical source and live target are the same file")

    (live_dir / "includes").mkdir(exist_ok=True)
    for source, target in pairs:
        shutil.copy2(source, target)
    return pairs


if __name__ == "__main__":
    try:
        copied = sync_mq5()
    except (OSError, ValueError) as error:
        print(f"MQ5 sync failed: {error}", file=sys.stderr)
        raise SystemExit(1)
    for copied_source, copied_target in copied:
        print(f"Copied {copied_source} -> {copied_target}")
