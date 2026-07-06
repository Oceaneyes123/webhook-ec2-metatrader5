"""MQ5 source sync — copies canonical sources to the live MT5 Experts folder.

Resolves the live MT5 Experts directory via a fallback chain:

  1. ``MT5_EXPERTS_DIR`` environment variable (explicit override)
  2. Auto-scan ``%APPDATA%/MetaQuotes/Terminal/*/MQL5/Experts/`` for a
     terminal that already contains *Webhook1.mq5* (zero-config on new
     machines)
  3. Symlinks at the repo root (``Webhook1.mq5`` / ``Webhook2.mq5``)

Usage::

    python -m webhook.sync_mq5
    # or
    MT5_EXPERTS_DIR="C:/Users/.../MQL5/Experts" python -m webhook.sync_mq5
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CANONICAL_DIR = ROOT / "mq5"
LIVE_EAS = (ROOT / "Webhook1.mq5", ROOT / "Webhook2.mq5")
RELATIVE_SOURCES = (
    Path("Webhook1.mq5"),
    Path("Webhook2.mq5"),
    Path("includes/WebhookCommon.mqh"),
    Path("includes/MarketSnapshot.mqh"),
    Path("includes/TradeManager.mqh"),
    Path("TPSL.mq5"),
)
"""Files to copy: the two EAs first, then shared includes, then TPSL."""


# ── Live-directory resolution ──────────────────────────────────────────


def _resolve_via_env() -> Path | None:
    """Return the Experts directory from ``$MT5_EXPERTS_DIR``, or *None*."""
    raw = os.environ.get("MT5_EXPERTS_DIR")
    if not raw:
        return None
    path = Path(raw).resolve()
    if not path.is_dir():
        print(
            f"⚠ MT5_EXPERTS_DIR is set but directory not found: {path}",
            file=sys.stderr,
        )
        return None
    # Sanity check — it should look like an Experts folder
    if not path.name.casefold() == "experts":
        print(
            f"⚠ MT5_EXPERTS_DIR points to '{path.name}', not 'Experts' — "
            "continuing anyway",
            file=sys.stderr,
        )
    return path


def _scan_terminal_instances() -> list[Path]:
    """List all ``*/MQL5/Experts`` directories under ``%APPDATA%/…``."""
    appdata = os.environ.get("APPDATA")
    if not appdata:
        return []
    terminals_dir = Path(appdata) / "MetaQuotes" / "Terminal"
    if not terminals_dir.is_dir():
        return []
    results: list[Path] = []
    for entry in terminals_dir.iterdir():
        experts = entry / "MQL5" / "Experts"
        if experts.is_dir():
            results.append(experts.resolve())
    return results


def _resolve_via_scan() -> Path | None:
    """Auto-detect the MT5 Experts directory by scanning terminal instances.

    Returns the single unambiguous match, or *None* when zero or multiple
    candidates are found.
    """
    candidates = _scan_terminal_instances()
    if not candidates:
        return None

    # Look for a terminal that already has our EA file
    matches: list[Path] = []
    for experts in candidates:
        if (experts / "Webhook1.mq5").is_file():
            matches.append(experts)

    if len(matches) == 1:
        return matches[0]
    if len(matches) > 1:
        print(
            "⚠ Multiple MT5 terminals contain Webhook1.mq5 — cannot auto-detect.\n"
            "  Set MT5_EXPERTS_DIR to the correct Experts folder.\n"
            "  Candidates:\n"
            + "\n".join(f"    - {p}" for p in matches),
            file=sys.stderr,
        )
        return None
    return None


def _resolve_via_symlinks(live_eas: tuple[Path, ...]) -> Path | None:
    """Resolve the live Experts directory from repo-root symlinks."""
    resolved = tuple(p.resolve(strict=False) for p in live_eas)
    live_dir = resolved[0].parent
    if live_dir == resolved[1].parent and live_dir.is_dir():
        return live_dir
    return None


def _find_live_dir(
    live_eas: tuple[Path, ...],
) -> Path:
    """Fallback chain: env var → auto-scan → symlinks → error.

    Returns the resolved live Experts directory.
    """
    # 1 — explicit env var override
    env_dir = _resolve_via_env()
    if env_dir is not None:
        print(f"✓ Using MT5 Experts dir from MT5_EXPERTS_DIR: {env_dir}")
        return env_dir

    # 2 — auto-scan terminal instances
    scan_dir = _resolve_via_scan()
    if scan_dir is not None:
        print(f"✓ Auto-detected MT5 Experts dir: {scan_dir}")
        return scan_dir

    # 3 — symlink fallback
    symlink_dir = _resolve_via_symlinks(live_eas)
    if symlink_dir is not None:
        print(f"✓ Using MT5 Experts dir from symlinks: {symlink_dir}")
        return symlink_dir

    # 4 — nothing worked; build a helpful error
    hints: list[str] = []
    hints.append(
        "  • Set MT5_EXPERTS_DIR (e.g. export MT5_EXPERTS_DIR="
        "\"C:/Users/.../AppData/Roaming/MetaQuotes/Terminal/<ID>/MQL5/Experts\")"
    )

    terminals = _scan_terminal_instances()
    if terminals:
        hints.append(
            "  • Found MT5 terminal(s) but none has Webhook1.mq5 yet.\n"
            "    Install the EAs first or pick one:\n"
            + "\n".join(f"      - {p}" for p in terminals)
        )
    else:
        hints.append(
            "  • No MT5 terminals found under %APPDATA%/MetaQuotes/Terminal/.\n"
            "    Is MetaTrader 5 installed?"
        )
        hints.append(
            "  • If you have symlinks (Webhook1.mq5 / Webhook2.mq5) from a\n"
            "    previous setup, they may be broken (wrong machine). Re-create\n"
            "    them pointing to the correct MT5 Experts folder on this machine."
        )

    raise FileNotFoundError(
        "Could not find live MT5 Experts directory.\n" + "\n".join(hints)
    )


# ── Core sync function ────────────────────────────────────────────────


def sync_mq5(
    source_dir: Path | str = CANONICAL_DIR,
    live_eas: tuple[Path | str, ...] | None = None,
    live_dir: Path | str | None = None,
) -> tuple[tuple[Path, Path], ...]:
    """Copy canonical MQ5 sources to the live MT5 Experts folder.

    Parameters
    ----------
    source_dir
        Directory containing canonical ``mq5/`` sources.
    live_eas
        Explicit EA target paths (used to derive the live Experts
        directory). Pass *None* (default) to resolve via the fallback
        chain (env → scan → symlinks).
    live_dir
        Explicit live Experts directory. Takes precedence over *live_eas*
        when resolving the target folder.

    Returns
    -------
    Pairs of ``(source_file, copied_target)``.
    """
    source_dir = Path(source_dir).resolve()

    # ── Resolve the target Experts directory ──
    if live_dir is not None:
        target_dir = Path(live_dir).resolve()
        if not target_dir.is_dir():
            raise FileNotFoundError(f"live MT5 Experts directory not found: {target_dir}")
    elif live_eas is not None:
        # Backward-compat: resolve from explicit EA paths
        eas = tuple(Path(p).resolve() for p in live_eas)
        if len(eas) != 2:
            raise ValueError("exactly two live EA targets are required")
        target_dir = eas[0].parent
        if eas[1].parent != target_dir or not target_dir.is_dir():
            raise FileNotFoundError(f"live MQ5 directory not found: {target_dir}")
    else:
        # Default: resolve via fallback chain
        target_dir = _find_live_dir(LIVE_EAS)

    # ── Build copy pairs ──
    targets: tuple[Path, ...] = (
        target_dir / "Webhook1.mq5",
        target_dir / "Webhook2.mq5",
        target_dir / "includes/WebhookCommon.mqh",
        target_dir / "includes/MarketSnapshot.mqh",
        target_dir / "includes/TradeManager.mqh",
        target_dir / "TPSL.mq5",
    )
    pairs: tuple[tuple[Path, Path], ...] = tuple(
        (source_dir / relative, target)
        for relative, target in zip(RELATIVE_SOURCES, targets)
    )

    # ── Validate ──
    for source, target in pairs:
        if not source.is_file():
            raise FileNotFoundError(f"canonical MQ5 source not found: {source}")
        if source.resolve() == target.resolve():
            raise ValueError(
                f"canonical source and live target are the same file: {source}"
            )

    # ── Copy ──
    (target_dir / "includes").mkdir(parents=True, exist_ok=True)
    for source, target in pairs:
        shutil.copy2(source, target)

    return pairs


# ── CLI entry point ───────────────────────────────────────────────────


if __name__ == "__main__":
    try:
        copied = sync_mq5()
    except (FileNotFoundError, OSError, ValueError) as error:
        print(f"MQ5 sync failed: {error}", file=sys.stderr)
        raise SystemExit(1)
    for copied_source, copied_target in copied:
        print(f"Copied {copied_source} -> {copied_target}")
