"""v3 初始化：建状态库 + 写入五条产业链 +（可选）采集真实数据。

用法：
    python scripts/bootstrap.py            # 建库 + 无数据时自动采集
    python scripts/bootstrap.py --refresh  # 强制重新采集（约 10 分钟）
    python scripts/bootstrap.py --no-fetch # 只建库
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import db  # noqa: E402
from app.data import store  # noqa: E402
from config import settings  # noqa: E402
from data_engine import chains  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="五链投研台初始化")
    parser.add_argument("--refresh", action="store_true", help="强制重新采集 AkShare 数据")
    parser.add_argument("--no-fetch", action="store_true", help="只建库，不采集")
    args = parser.parse_args()

    settings.ensure_dirs()
    db.init()
    db.seed_chains(chains.chains())
    print(f"[bootstrap] 状态库就绪：{settings.STATE_DB}")
    print(f"[bootstrap] 产业链 {len(chains.chains())} 条 / 节点 "
          f"{sum(len(c['nodes']) for c in chains.chains())} 个 / 标的 {len(chains.all_symbols())} 只")

    if not args.no_fetch and (args.refresh or not store.ok):
        print("[bootstrap] 采集 AkShare 真实数据（约 10 分钟）…")
        code = subprocess.call([sys.executable, "-m", "data_engine.fetch_chains"], cwd=str(ROOT))
        if code != 0:
            print("[bootstrap] 采集失败，检查网络或稍后重试")
    if not args.no_fetch and (args.refresh or not settings.BUSINESS_PARQUET.exists()):
        print("[bootstrap] 采集主营构成（约 4 分钟）…")
        subprocess.call([sys.executable, "-m", "data_engine.fetch_business"], cwd=str(ROOT))
    if not args.no_fetch:
        for mod, path, label in (
            ("data_engine.fetch_valuation_ext", settings.VALUATION_EXT_PARQUET, "估值/分红/预测"),
            ("data_engine.fetch_financial_ext", settings.FINANCIALS_EXT_PARQUET, "三表/财务指标"),
            ("data_engine.fetch_chips", settings.CHIPS_PARQUET, "股东户数"),
            ("data_engine.fetch_macro", settings.MACRO_FUTURES_PARQUET, "期货/宏观代理"),
        ):
            if args.refresh or not path.exists():
                print(f"[bootstrap] 采集{label} …")
                subprocess.call([sys.executable, "-m", mod], cwd=str(ROOT))
    store.reload()
    print(f"[bootstrap] 数据：ok={store.ok} 截至 {store.as_of() or '—'}")
    print("[bootstrap] 启动：.venv\\Scripts\\python.exe -m uvicorn app.server:app --port 8000")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
