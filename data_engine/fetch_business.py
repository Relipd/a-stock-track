"""采集主营业务构成（按产品/按地区）与主营介绍。

数据源：AkShare 东财主营构成 `stock_zygc_em`、同花顺主营介绍 `stock_zyjs_ths`。
输出：data/business.parquet、data/business_desc.parquet（只保留最新报告期）。

用法：
    python -m data_engine.fetch_business            # 全部 200 只（约 3~5 分钟）
    python -m data_engine.fetch_business --only-missing
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings  # noqa: E402
from data_engine import ak_cache  # noqa: E402

ak_cache.install()
from data_engine import chains  # noqa: E402

BUSINESS_COLS = ["symbol", "name", "report_date", "category", "item", "revenue",
                 "revenue_ratio", "cost", "cost_ratio", "profit", "profit_ratio", "gross_margin"]
DESC_COLS = ["symbol", "name", "main_business", "product_type", "product_name", "scope"]


def _atomic(df: pd.DataFrame, path: Path) -> None:
    tmp = path.with_suffix(".tmp.parquet")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def _prefix(symbol: str) -> str:
    return ("SH" if symbol.endswith(".SH") else "SZ") + symbol.split(".")[0]


def fetch_one(symbol: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    import akshare as ak
    name = chains.name_of(symbol)
    code = symbol.split(".")[0]
    comp = pd.DataFrame(columns=BUSINESS_COLS)
    desc = pd.DataFrame(columns=DESC_COLS)
    try:
        raw = ak.stock_zygc_em(symbol=_prefix(symbol))
        if raw is not None and not raw.empty:
            raw = raw.copy()
            raw["报告日期"] = pd.to_datetime(raw["报告日期"])
            # 保留近 5 年历史期，用于海外收入占比与结构变化
            last = raw["报告日期"].max()
            raw = raw[raw["报告日期"] >= (last - pd.Timedelta(days=365 * 5))]
            # 只留"按产品分类 / 按地区分类"，其它分类类型跳过
            raw = raw[raw["分类类型"].isin(["按产品分类", "按地区分类"])]
            comp = pd.DataFrame({
                "symbol": symbol, "name": name, "report_date": raw["报告日期"],
                "category": raw["分类类型"],
                "item": raw["主营构成"].astype(str),
                "revenue": pd.to_numeric(raw["主营收入"], errors="coerce"),
                "revenue_ratio": pd.to_numeric(raw["收入比例"], errors="coerce"),
                "cost": pd.to_numeric(raw["主营成本"], errors="coerce"),
                "cost_ratio": pd.to_numeric(raw["成本比例"], errors="coerce"),
                "profit": pd.to_numeric(raw["主营利润"], errors="coerce"),
                "profit_ratio": pd.to_numeric(raw["利润比例"], errors="coerce"),
                "gross_margin": pd.to_numeric(raw["毛利率"], errors="coerce"),
            })
    except Exception as exc:  # noqa: BLE001
        print(f"[business] {symbol} 主营构成失败 {type(exc).__name__}: {exc}", flush=True)
    try:
        raw = ak.stock_zyjs_ths(symbol=code)
        if raw is not None and not raw.empty:
            r = raw.iloc[0]
            desc = pd.DataFrame([{
                "symbol": symbol, "name": name,
                "main_business": r.get("主营业务", ""),
                "product_type": r.get("产品类型", ""),
                "product_name": r.get("产品名称", ""),
                "scope": r.get("经营范围", ""),
            }], columns=DESC_COLS)
    except Exception as exc:  # noqa: BLE001
        print(f"[business] {symbol} 主营介绍失败 {type(exc).__name__}: {exc}", flush=True)
    return comp, desc


def main() -> int:
    parser = argparse.ArgumentParser(description="主营构成与主营介绍采集")
    parser.add_argument("--only-missing", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    out = settings.DATA_DIR
    out.mkdir(parents=True, exist_ok=True)
    comp_path, desc_path = out / "business.parquet", out / "business_desc.parquet"
    old_comp = pd.read_parquet(comp_path) if comp_path.exists() else pd.DataFrame(columns=BUSINESS_COLS)
    old_desc = pd.read_parquet(desc_path) if desc_path.exists() else pd.DataFrame(columns=DESC_COLS)

    syms = chains.all_symbols()
    if args.only_missing and not old_comp.empty:
        have = set(old_comp["symbol"])
        syms = [s for s in syms if s not in have]
    if args.limit:
        syms = syms[: args.limit]

    comps, descs, errors = [], [], []
    t0 = time.time()

    def worker(sym: str):
        return sym, *fetch_one(sym)

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(worker, s) for s in syms]
        for i, fut in enumerate(as_completed(futures), 1):
            sym, c, d = fut.result()
            if not c.empty:
                comps.append(c)
            else:
                errors.append(sym)
            if not d.empty:
                descs.append(d)
            if i % 20 == 0:
                print(f"[business] {i}/{len(syms)} …", flush=True)

    new_comp = pd.concat(comps, ignore_index=True) if comps else pd.DataFrame(columns=BUSINESS_COLS)
    new_desc = pd.concat(descs, ignore_index=True) if descs else pd.DataFrame(columns=DESC_COLS)
    if not new_comp.empty and not old_comp.empty:
        old_comp = old_comp[~old_comp["symbol"].isin(set(new_comp["symbol"]))]
        new_comp = pd.concat([old_comp, new_comp], ignore_index=True)
    if not new_desc.empty and not old_desc.empty:
        old_desc = old_desc[~old_desc["symbol"].isin(set(new_desc["symbol"]))]
        new_desc = pd.concat([old_desc, new_desc], ignore_index=True)
    if not new_comp.empty:
        _atomic(new_comp[BUSINESS_COLS], comp_path)
    if not new_desc.empty:
        _atomic(new_desc[DESC_COLS], desc_path)
    print(f"[business] 完成 {len(new_comp)} 条构成 / {len(new_desc)} 条介绍，用时 {time.time() - t0:.0f}s，失败 {len(errors)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
