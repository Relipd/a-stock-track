"""P0 估值扩展：stock_value_em（市值/PE/PB/PS/PCF/PEG）、分红、盈利预测。

输出：
  data/valuation_ext.parquet
  data/dividends.parquet
  data/forecast.parquet
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

VAL_COLS = ["symbol", "trade_date", "total_mv", "float_mv", "total_shares", "float_shares",
            "close_em", "pe_ttm_em", "pe_static", "pb_em", "ps_ttm", "pcf_ttm", "peg"]
DIV_COLS = ["symbol", "announce_date", "ex_date", "cash_per_10", "progress"]
FC_COLS = ["symbol", "report_count", "buy", "add", "neutral", "reduce", "sell",
           "eps_2025e", "eps_2026e", "eps_2027e", "eps_2028e", "fetched_at"]


def _atomic(df: pd.DataFrame, path: Path) -> None:
    tmp = path.with_suffix(".tmp.parquet")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def _code(symbol: str) -> str:
    return symbol.split(".")[0]


def fetch_valuation(symbol: str) -> pd.DataFrame:
    import akshare as ak
    raw = ak.stock_value_em(symbol=_code(symbol))
    if raw is None or raw.empty:
        return pd.DataFrame(columns=VAL_COLS)
    out = pd.DataFrame({
        "symbol": symbol,
        "trade_date": pd.to_datetime(raw["数据日期"], errors="coerce"),
        "total_mv": pd.to_numeric(raw["总市值"], errors="coerce"),
        "float_mv": pd.to_numeric(raw["流通市值"], errors="coerce"),
        "total_shares": pd.to_numeric(raw["总股本"], errors="coerce"),
        "float_shares": pd.to_numeric(raw["流通股本"], errors="coerce"),
        "close_em": pd.to_numeric(raw["当日收盘价"], errors="coerce"),
        "pe_ttm_em": pd.to_numeric(raw["PE(TTM)"], errors="coerce"),
        "pe_static": pd.to_numeric(raw["PE(静)"], errors="coerce"),
        "pb_em": pd.to_numeric(raw["市净率"], errors="coerce"),
        "ps_ttm": pd.to_numeric(raw["市销率"], errors="coerce"),
        "pcf_ttm": pd.to_numeric(raw["市现率"], errors="coerce"),
        "peg": pd.to_numeric(raw["PEG值"], errors="coerce"),
    })
    return out.dropna(subset=["trade_date"]).sort_values("trade_date")


def fetch_dividend(symbol: str) -> pd.DataFrame:
    import akshare as ak
    raw = ak.stock_history_dividend_detail(symbol=_code(symbol), indicator="分红")
    if raw is None or raw.empty:
        return pd.DataFrame(columns=DIV_COLS)
    out = pd.DataFrame({
        "symbol": symbol,
        "announce_date": pd.to_datetime(raw["公告日期"], errors="coerce"),
        "ex_date": pd.to_datetime(raw["除权除息日"], errors="coerce"),
        "cash_per_10": pd.to_numeric(raw["派息"], errors="coerce"),
        "progress": raw["进度"].astype(str),
    })
    return out.dropna(subset=["announce_date"])


def fetch_forecast(symbols: list[str]) -> pd.DataFrame:
    import akshare as ak
    raw = ak.stock_profit_forecast_em()
    if raw is None or raw.empty:
        return pd.DataFrame(columns=FC_COLS)
    raw = raw.copy()
    raw["code"] = raw["代码"].astype(str).str.zfill(6)
    sym_by_code = {_code(s): s for s in symbols}
    raw = raw[raw["code"].isin(sym_by_code)]
    out = pd.DataFrame({
        "symbol": raw["code"].map(sym_by_code),
        "report_count": pd.to_numeric(raw["研报数"], errors="coerce"),
        "buy": pd.to_numeric(raw["机构投资评级(近六个月)-买入"], errors="coerce"),
        "add": pd.to_numeric(raw["机构投资评级(近六个月)-增持"], errors="coerce"),
        "neutral": pd.to_numeric(raw["机构投资评级(近六个月)-中性"], errors="coerce"),
        "reduce": pd.to_numeric(raw["机构投资评级(近六个月)-减持"], errors="coerce"),
        "sell": pd.to_numeric(raw["机构投资评级(近六个月)-卖出"], errors="coerce"),
        "eps_2025e": pd.to_numeric(raw["2025预测每股收益"], errors="coerce"),
        "eps_2026e": pd.to_numeric(raw["2026预测每股收益"], errors="coerce"),
        "eps_2027e": pd.to_numeric(raw["2027预测每股收益"], errors="coerce"),
        "eps_2028e": pd.to_numeric(raw["2028预测每股收益"], errors="coerce"),
    })
    out["fetched_at"] = datetime.now().isoformat(timespec="seconds")
    return out.dropna(subset=["symbol"]).reset_index(drop=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="估值/分红/盈利预测扩展")
    parser.add_argument("--only-missing", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--workers", type=int, default=8)
    args = parser.parse_args()

    out = settings.DATA_DIR
    out.mkdir(parents=True, exist_ok=True)
    syms = chains.all_symbols()
    if args.limit:
        syms = syms[: args.limit]

    val_path, div_path = out / "valuation_ext.parquet", out / "dividends.parquet"
    old_val = pd.read_parquet(val_path) if val_path.exists() else pd.DataFrame(columns=VAL_COLS)
    old_div = pd.read_parquet(div_path) if div_path.exists() else pd.DataFrame(columns=DIV_COLS)
    if args.only_missing and not old_val.empty:
        have = set(old_val["symbol"])
        syms = [s for s in syms if s not in have]

    vals, divs, errors = [], [], []
    t0 = time.time()

    def worker(sym: str):
        v = d = None
        errs = []
        try:
            v = fetch_valuation(sym)
        except Exception as exc:  # noqa: BLE001
            errs.append(f"{sym} 估值: {type(exc).__name__}: {exc}")
        try:
            d = fetch_dividend(sym)
        except Exception as exc:  # noqa: BLE001
            errs.append(f"{sym} 分红: {type(exc).__name__}: {exc}")
        return v, d, errs

    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = [pool.submit(worker, s) for s in syms]
        for i, fut in enumerate(as_completed(futures), 1):
            v, d, errs = fut.result()
            if v is not None and not v.empty:
                vals.append(v)
            if d is not None and not d.empty:
                divs.append(d)
            errors.extend(errs)
            if i % 20 == 0:
                print(f"[valuation] {i}/{len(syms)} …", flush=True)

    new_val = pd.concat(vals, ignore_index=True) if vals else pd.DataFrame(columns=VAL_COLS)
    new_div = pd.concat(divs, ignore_index=True) if divs else pd.DataFrame(columns=DIV_COLS)
    if not new_val.empty and not old_val.empty:
        old_val = old_val[~old_val["symbol"].isin(set(new_val["symbol"]))]
        new_val = pd.concat([old_val, new_val], ignore_index=True)
    if not new_div.empty and not old_div.empty:
        old_div = old_div[~old_div["symbol"].isin(set(new_div["symbol"]))]
        new_div = pd.concat([old_div, new_div], ignore_index=True)
    if not new_val.empty:
        _atomic(new_val[VAL_COLS], val_path)
    if not new_div.empty:
        _atomic(new_div[DIV_COLS], div_path)

    fc = fetch_forecast(chains.all_symbols())
    if not fc.empty:
        _atomic(fc[FC_COLS], out / "forecast.parquet")
    print(f"[valuation] 估值 {len(new_val):,} 行 / 分红 {len(new_div):,} 行 / 预测 {len(fc):,} 行，"
          f"用时 {time.time() - t0:.0f}s，错误 {len(errors)}")
    for e in errors[:8]:
        print("  !", e)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
