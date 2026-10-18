"""采集五条产业链（101 只标的 + 沪深300）的真实数据：行情 / 财务 / 估值 / 舆情。

用法：
    python -m data_engine.fetch_chains               # 全量（约 8~10 分钟）
    python -m data_engine.fetch_chains --chain whites  # 只采一条链
    python -m data_engine.fetch_chains --limit 3      # 调试
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings  # noqa: E402
from data_engine import chains  # noqa: E402
from data_engine.fetch_common import _sleep  # noqa: E402
from data_engine.fetch_common import (
    FUND_COLS, OHLCV_COLS, SENT_COLS, VAL_COLS,
    _atomic_parquet,
    fetch_benchmark, fetch_fundamentals, fetch_ohlcv, fetch_sentiment, fetch_valuation,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="五条产业链真实数据采集")
    parser.add_argument("--chain", default="", help="只采一条链（whites/pv/auto/copper/tourism）")
    parser.add_argument("--days", type=int, default=1100)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--only-missing", action="store_true", help="只采本地还没有行情的标的")
    parser.add_argument("--workers", type=int, default=6, help="并发线程数（默认 6）")
    parser.add_argument("--out", default=str(settings.DATA_DIR))
    args = parser.parse_args()

    end_dt = datetime.now()
    start_dt = end_dt - timedelta(days=args.days)
    start, end = start_dt.strftime("%Y%m%d"), end_dt.strftime("%Y%m%d")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    syms = chains.symbols(args.chain or None)
    all_syms = list(syms)
    if args.limit:
        syms = syms[: args.limit]

    frames = {"ohlcv": [], "fundamentals": [], "valuation": []}
    errors: list[str] = []
    t0 = time.time()

    # 先读已有数据，支持按链增量合并
    existing: dict[str, pd.DataFrame] = {}
    for name, path in (("ohlcv", out / "ohlcv.parquet"), ("fundamentals", out / "fundamentals.parquet"),
                       ("valuation", out / "valuation.parquet"), ("sentiment", out / "sentiment.parquet")):
        existing[name] = pd.read_parquet(path) if path.exists() else pd.DataFrame()

    if args.only_missing and not existing["ohlcv"].empty:
        have = set(existing["ohlcv"]["symbol"])
        syms = [s for s in syms if s not in have]
    print(f"[fetch] {len(syms)} 只标的（{args.chain or '全部产业链'}）", flush=True)

    def worker(sym: str) -> tuple[dict, list[str]]:
        one = {"ohlcv": None, "fundamentals": None, "valuation": None}
        errs: list[str] = []
        try:
            one["ohlcv"] = fetch_ohlcv(sym, start, end)
        except Exception as exc:  # noqa: BLE001
            errs.append(f"{sym} 行情: {type(exc).__name__}: {exc}")
        try:
            one["fundamentals"] = fetch_fundamentals(sym, "2022")
        except Exception as exc:  # noqa: BLE001
            errs.append(f"{sym} 财务: {type(exc).__name__}: {exc}")
        try:
            one["valuation"] = fetch_valuation(sym, (start_dt - timedelta(days=1100)).strftime("%Y-%m-%d"))
        except Exception as exc:  # noqa: BLE001
            errs.append(f"{sym} 估值: {type(exc).__name__}: {exc}")
        return one, errs

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(worker, s): s for s in syms}
        for i, fut in enumerate(as_completed(futures), 1):
            sym = futures[fut]
            one, errs = fut.result()
            for key in ("ohlcv", "fundamentals", "valuation"):
                if one[key] is not None and not one[key].empty:
                    frames[key].append(one[key])
            errors.extend(errs)
            if i % 10 == 0 or errs:
                print(f"[{i}/{len(syms)}] {sym} {'FAIL ' + errs[0] if errs else 'ok'}", flush=True)

    print("采集舆情快照（全部标的）…", flush=True)
    try:
        sent = fetch_sentiment(all_syms)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"舆情: {type(exc).__name__}: {exc}")
        sent = pd.DataFrame(columns=SENT_COLS)

    print("采集基准 …", flush=True)
    try:
        bench = fetch_benchmark(start, end)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"基准: {type(exc).__name__}: {exc}")
        bench = pd.DataFrame(columns=OHLCV_COLS)

    def merge(name: str, new_rows: list[pd.DataFrame], key: list[str]) -> pd.DataFrame:
        old = existing[name]
        if old is not None and not old.empty:
            syms_in = {df["symbol"].iloc[0] for df in new_rows if not df.empty}
            old = old[~old["symbol"].isin(syms_in)]
        parts = [old] if old is not None and not old.empty else []
        parts += [df for df in new_rows if df is not None and not df.empty]
        if not parts:
            return pd.DataFrame()
        df = pd.concat(parts, ignore_index=True)
        return df.drop_duplicates(subset=key).sort_values(key).reset_index(drop=True)

    ohlcv = merge("ohlcv", frames["ohlcv"] + [bench], ["symbol", "trade_date"])
    fund = merge("fundamentals", frames["fundamentals"], ["symbol", "report_date"])
    val = merge("valuation", frames["valuation"], ["symbol", "trade_date"])
    sent = merge("sentiment", [sent], ["symbol", "trade_date"])

    for name, df, cols in [("ohlcv", ohlcv, OHLCV_COLS), ("fundamentals", fund, FUND_COLS),
                           ("valuation", val, VAL_COLS), ("sentiment", sent, SENT_COLS)]:
        if df is None or df.empty:
            print(f"[warn] {name} 为空，跳过写入")
            continue
        df = df[[c for c in cols if c in df.columns]]
        _atomic_parquet(df, out / f"{name}.parquet")
        print(f"[ok] {name}: {len(df):,} 行，{df['symbol'].nunique()} 个标的", flush=True)
    try:
        from data_engine.normalize_valuation import clean_valuation
        clean_valuation()
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] 估值交易日清洗失败: {type(exc).__name__}: {exc}")

    print(f"完成，用时 {time.time() - t0:.0f}s，错误 {len(errors)} 个")
    for e in errors[:12]:
        print("  !", e)
    return 0 if ohlcv is not None and not ohlcv.empty else 1


if __name__ == "__main__":
    raise SystemExit(main())
