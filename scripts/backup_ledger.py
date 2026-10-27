"""Copy the execution ledger (db + wal/shm) to a backup directory.

Usage: python scripts/backup_ledger.py [--dest DIR]
Default dest: backups/ledger/<timestamp>/ under the project root.
"""

from __future__ import annotations

import argparse
import shutil
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_LEDGER = ROOT / "data" / "trading" / "ledger.db"


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ledger", type=Path, default=DEFAULT_LEDGER)
    parser.add_argument("--dest", type=Path, default=None)
    args = parser.parse_args()

    if not args.ledger.is_file():
        raise SystemExit(f"ledger not found: {args.ledger}")
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    dest = args.dest or (ROOT / "backups" / "ledger" / stamp)
    dest.mkdir(parents=True, exist_ok=True)
    for suffix in ("", "-wal", "-shm"):
        src = Path(str(args.ledger) + suffix)
        if src.exists():
            shutil.copy2(src, dest / src.name)
    print(f"ledger backed up to {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
