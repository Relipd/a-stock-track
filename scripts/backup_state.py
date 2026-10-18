"""Consistent rolling backup of the local state database."""
from __future__ import annotations

import sqlite3
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config.settings import STATE_DB  # noqa: E402


def main() -> int:
    if not STATE_DB.exists():
        print("[backup] state.sqlite 不存在，跳过")
        return 0
    out_dir = STATE_DB.parent / "backups"
    out_dir.mkdir(parents=True, exist_ok=True)
    dest = out_dir / f"state-{datetime.now().strftime('%Y%m%d-%H%M%S')}.sqlite"
    src = sqlite3.connect(str(STATE_DB), timeout=15)
    dst = sqlite3.connect(str(dest))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    backups = sorted(out_dir.glob("state-*.sqlite"), key=lambda p: p.stat().st_mtime, reverse=True)
    for old in backups[20:]:
        old.unlink(missing_ok=True)
    print(f"[backup] {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
