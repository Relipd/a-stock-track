"""环境自检：依赖 / 数据 / 状态库 / 服务端口。"""
from __future__ import annotations

import importlib
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PACKAGES = ["pandas", "numpy", "pyarrow", "akshare", "fastapi", "uvicorn", "pytest", "httpx"]


def main() -> int:
    print(f"Python {sys.version.split()[0]}  ({sys.executable})")
    problems = 0
    for name in PACKAGES:
        try:
            mod = importlib.import_module(name)
            print(f"  [ok] {name:10s} {getattr(mod, '__version__', '')}")
        except Exception as exc:  # noqa: BLE001
            problems += 1
            print(f"  [!!] {name:10s} 缺失：{exc}")

    from app import db
    from app.data import store
    from config import settings
    from data_engine import chains

    print(f"\n产业链：{len(chains.chains())} 条 / 标的 {len(chains.all_symbols())} 只")
    print(f"数据：ok={store.ok} 截至 {store.as_of() or '—'}")
    print(f"主营构成：{len(store.business)} 行 / {store.business['symbol'].nunique() if not store.business.empty else 0} 只")
    print(f"扩展数据：估值 {len(store.val_ext):,} / 三表 {len(store.fin_ext):,} / 指标 {len(store.ratios):,} / "
          f"筹码 {len(store.chips):,} / 宏观期货 {len(store.macro):,}")
    db.init()
    db.seed_chains(chains.chains())
    print(f"状态库：{settings.STATE_DB}")
    with socket.socket() as s:
        busy = s.connect_ex(("127.0.0.1", 8000)) == 0
    print(f"端口 8000：{'已占用（服务可能已启动）' if busy else '空闲'}")
    print("\n结论：" + ("环境就绪 ✅" if problems == 0 else f"有 {problems} 项待修复 ❌"))
    return 0 if problems == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
