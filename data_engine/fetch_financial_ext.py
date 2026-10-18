"""P0 财务扩展：三大报表精选字段 + 东财 141 项财务指标精选。

输出：
  data/financials_ext.parquet
  data/financial_ratios_ext.parquet
"""
from __future__ import annotations

import argparse
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

BAL_FIELDS = ["TOTAL_ASSETS", "TOTAL_LIABILITIES", "TOTAL_PARENT_EQUITY", "MONETARYFUNDS",
              "SHORT_LOAN", "LONG_LOAN", "BOND_PAYABLE", "INVENTORY", "ACCOUNTS_RECE",
              "NOTE_ACCOUNTS_RECE", "FIXED_ASSET", "CIP"]
PROFIT_FIELDS = ["TOTAL_OPERATE_INCOME", "OPERATE_COST", "OPERATE_PROFIT", "TOTAL_PROFIT",
                 "NETPROFIT", "PARENT_NETPROFIT", "DEDUCT_PARENT_NETPROFIT", "FINANCE_EXPENSE",
                 "ASSET_IMPAIRMENT_LOSS", "CREDIT_IMPAIRMENT_LOSS"]
CASH_FIELDS = ["NETCASH_OPERATE", "CONSTRUCT_LONG_ASSET", "FA_IR_DEPR", "IA_AMORTIZE",
               "LPE_AMORTIZE", "USERIGHT_ASSET_AMORTIZE"]
RATIO_FIELDS = ["REPORT_DATE", "DJD_TOI_YOY", "DJD_DPNP_YOY", "ROIC", "ROEJQ",
                "PAYABLE_TDAYS", "PREPAID_ACCOUNTS_TDAYS", "CHZZTS", "YSZKZZTS",
                "XSMLL", "XSJLL", "ZCFZL", "FCFF_FORWARD", "OPERATE_CYCLE"]

FIN_COLS = ["symbol", "report_date"] + BAL_FIELDS + PROFIT_FIELDS + CASH_FIELDS
RATIO_COLS = ["symbol", "report_date"] + [c for c in RATIO_FIELDS if c != "REPORT_DATE"]


def _atomic(df: pd.DataFrame, path: Path) -> None:
    tmp = path.with_suffix(".tmp.parquet")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def _prefix(symbol: str) -> str:
    return ("SH" if symbol.endswith(".SH") else "SZ") + symbol.split(".")[0]


def fetch_statements(symbol: str) -> pd.DataFrame:
    import akshare as ak
    frames = []
    specs = [
        (ak.stock_balance_sheet_by_yearly_em, BAL_FIELDS),
        (ak.stock_profit_sheet_by_yearly_em, PROFIT_FIELDS),
        (ak.stock_cash_flow_sheet_by_yearly_em, CASH_FIELDS),
    ]
    base = None
    for fn, fields in specs:
        raw = fn(symbol=_prefix(symbol))
        if raw is None or raw.empty:
            continue
        keep = ["REPORT_DATE"] + [c for c in fields if c in raw.columns]
        cur = raw[keep].copy()
        cur["REPORT_DATE"] = pd.to_datetime(cur["REPORT_DATE"], errors="coerce")
        cur = cur.dropna(subset=["REPORT_DATE"]).drop_duplicates("REPORT_DATE")
        for c in fields:
            if c in cur.columns:
                cur[c] = pd.to_numeric(cur[c], errors="coerce")
        base = cur if base is None else base.merge(cur, on="REPORT_DATE", how="outer")
    if base is None or base.empty:
        return pd.DataFrame(columns=FIN_COLS)
    base = base.rename(columns={"REPORT_DATE": "report_date"})
    base.insert(0, "symbol", symbol)
    return base.sort_values("report_date")


def fetch_ratios(symbol: str) -> pd.DataFrame:
    import akshare as ak
    raw = ak.stock_financial_analysis_indicator_em(symbol=symbol, indicator="按报告期")
    if raw is None or raw.empty:
        return pd.DataFrame(columns=RATIO_COLS)
    raw = raw.copy()
    raw["REPORT_DATE"] = pd.to_datetime(raw["REPORT_DATE"], errors="coerce")
    keep = ["REPORT_DATE"] + [c for c in RATIO_COLS if c in raw.columns and c != "symbol"]
    cur = raw[keep].dropna(subset=["REPORT_DATE"]).drop_duplicates("REPORT_DATE")
    for c in RATIO_COLS:
        if c in cur.columns and c not in ("symbol", "report_date"):
            cur[c] = pd.to_numeric(cur[c], errors="coerce")
    cur = cur.rename(columns={"REPORT_DATE": "report_date"})
    cur.insert(0, "symbol", symbol)
    return cur.sort_values("report_date")


def main() -> int:
    parser = argparse.ArgumentParser(description="三大报表与财务指标扩展")
    parser.add_argument("--only-missing", action="store_true")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    out = settings.DATA_DIR
    out.mkdir(parents=True, exist_ok=True)
    fin_path = out / "financials_ext.parquet"
    ratio_path = out / "financial_ratios_ext.parquet"
    old_fin = pd.read_parquet(fin_path) if fin_path.exists() else pd.DataFrame(columns=FIN_COLS)
    old_ratio = pd.read_parquet(ratio_path) if ratio_path.exists() else pd.DataFrame(columns=RATIO_COLS)

    syms = chains.all_symbols()
    if args.limit:
        syms = syms[: args.limit]
    if args.only_missing and not old_fin.empty:
        have = set(old_fin["symbol"])
        syms = [s for s in syms if s not in have]

    fins, ratios, errors = [], [], []
    t0 = time.time()

    def worker(sym: str):
        f = r = None
        errs = []
        try:
            f = fetch_statements(sym)
        except Exception as exc:  # noqa: BLE001
            errs.append(f"{sym} 三表: {type(exc).__name__}: {exc}")
        try:
            r = fetch_ratios(sym)
        except Exception as exc:  # noqa: BLE001
            errs.append(f"{sym} 指标: {type(exc).__name__}: {exc}")
        return sym, f, r, errs

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(worker, s) for s in syms]
        for i, fut in enumerate(as_completed(futures), 1):
            sym, f, r, errs = fut.result()
            if f is not None and not f.empty:
                fins.append(f)
            if r is not None and not r.empty:
                ratios.append(r)
            errors.extend(errs)
            if i % 20 == 0:
                print(f"[financial] {i}/{len(syms)} …", flush=True)

    new_fin = pd.concat(fins, ignore_index=True) if fins else pd.DataFrame(columns=FIN_COLS)
    new_ratio = pd.concat(ratios, ignore_index=True) if ratios else pd.DataFrame(columns=RATIO_COLS)
    for old, new, path, cols in (
        (old_fin, new_fin, fin_path, FIN_COLS),
        (old_ratio, new_ratio, ratio_path, RATIO_COLS),
    ):
        if not new.empty and not old.empty:
            old = old[~old["symbol"].isin(set(new["symbol"]))]
            new = pd.concat([old, new], ignore_index=True)
        if not new.empty:
            _atomic(new[[c for c in cols if c in new.columns]], path)
    print(f"[financial] 三表 {len(new_fin):,} 行 / 指标 {len(new_ratio):,} 行，"
          f"用时 {time.time() - t0:.0f}s，错误 {len(errors)}")
    for e in errors[:8]:
        print("  !", e)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
