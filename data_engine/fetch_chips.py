"""P1 筹码：股东户数变化（季度）。

输出：data/chips.parquet
"""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings  # noqa: E402
from data_engine import ak_cache  # noqa: E402

ak_cache.install()
from data_engine import chains  # noqa: E402

COLS = ["symbol", "report_date", "holder_num", "holder_num_chg_pct", "avg_holder_mv", "total_mv"]


def main() -> int:
    import akshare as ak
    out = settings.DATA_DIR
    path = out / "chips.parquet"
    old = pd.read_parquet(path) if path.exists() else pd.DataFrame(columns=COLS)
    syms = chains.all_symbols()
    t0 = time.time()
    errors = []

    def worker(sym: str):
        try:
            raw = ak.stock_zh_a_gdhs_detail_em(symbol=sym.split(".")[0])
            if raw is None or raw.empty:
                return None
            raw = raw.copy()
            cur = pd.DataFrame({
                "symbol": sym,
                "report_date": pd.to_datetime(raw["股东户数统计截止日"], errors="coerce"),
                "holder_num": pd.to_numeric(raw["股东户数-本次"], errors="coerce"),
                "holder_num_chg_pct": pd.to_numeric(raw["股东户数-增减比例"], errors="coerce"),
                "avg_holder_mv": pd.to_numeric(raw["户均持股市值"], errors="coerce"),
                "total_mv": pd.to_numeric(raw["总市值"], errors="coerce"),
            })
            return cur.dropna(subset=["report_date"])
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{sym}: {type(exc).__name__}: {exc}")
            return None

    rows = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(worker, s) for s in syms]
        for i, fut in enumerate(as_completed(futures), 1):
            r = fut.result()
            if r is not None and not r.empty:
                rows.append(r)
            if i % 20 == 0:
                print(f"[chips] {i}/{len(syms)} …", flush=True)
    new = pd.concat(rows, ignore_index=True) if rows else pd.DataFrame(columns=COLS)
    if not new.empty and not old.empty:
        old = old[~old["symbol"].isin(set(new["symbol"]))]
        new = pd.concat([old, new], ignore_index=True)
    if not new.empty:
        new = new.drop_duplicates(["symbol", "report_date"]).sort_values(["symbol", "report_date"])
        tmp = path.with_suffix(".tmp.parquet")
        new[COLS].to_parquet(tmp, index=False)
        os.replace(tmp, path)
    print(f"[chips] {len(new):,} 行 / {new['symbol'].nunique()} 只，用时 {time.time() - t0:.0f}s，错误 {len(errors)}")
    for e in errors[:6]:
        print("  !", e)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
