"""把估值序列对齐到真实交易日，并重算 PE/PB 分位。

背景：百度估值序列包含周末/节假日重复值，且个别非交易日 PB 为 NaN，
会把分位算成 0，图表上表现为“断崖”。这里以本地行情日历为准做清洗。
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings  # noqa: E402

VAL_COLS = ["symbol", "trade_date", "pe_ttm", "pb", "pe_pct_3y", "pb_pct_3y", "pe_pct_1y", "pb_pct_1y"]


def _pct_rank(series: pd.Series) -> pd.Series:
    valid = series.dropna()
    if valid.empty:
        return pd.Series(index=series.index, dtype=float)
    rank = valid.expanding(min_periods=20).apply(lambda s: float((s <= s.iloc[-1]).mean()))
    return rank.reindex(series.index)


def _rolling_rank(series: pd.Series, window: int = 250, min_periods: int = 120) -> pd.Series:
    valid = series.dropna()
    if valid.empty:
        return pd.Series(index=series.index, dtype=float)
    rank = valid.rolling(window, min_periods=min_periods).apply(lambda s: float((s <= s.iloc[-1]).mean()))
    return rank.reindex(series.index)


def clean_valuation() -> tuple[int, int]:
    ohlcv = pd.read_parquet(settings.OHLCV_PARQUET, columns=["symbol", "trade_date"])
    ohlcv["trade_date"] = pd.to_datetime(ohlcv["trade_date"])
    bench = ohlcv[ohlcv["symbol"] == "000300.SH"]
    trading = set(bench["trade_date"]) if not bench.empty else set(ohlcv["trade_date"])
    val = pd.read_parquet(settings.VALUATION_PARQUET)
    val["trade_date"] = pd.to_datetime(val["trade_date"])
    before = len(val)
    val = val[val["trade_date"].isin(trading)].copy()

    parts = []
    for sym, d in val.groupby("symbol", sort=False):
        d = d.sort_values("trade_date").copy()
        d = d.dropna(subset=["pe_ttm", "pb"], how="all")
        d["pe_pct_3y"] = _pct_rank(d["pe_ttm"])
        d["pb_pct_3y"] = _pct_rank(d["pb"])
        d["pe_pct_1y"] = _rolling_rank(d["pe_ttm"])
        d["pb_pct_1y"] = _rolling_rank(d["pb"])
        parts.append(d)
    out = pd.concat(parts, ignore_index=True) if parts else val
    out = out[VAL_COLS].sort_values(["symbol", "trade_date"]).reset_index(drop=True)
    tmp = settings.VALUATION_PARQUET.with_suffix(".tmp.parquet")
    out.to_parquet(tmp, index=False)
    os.replace(tmp, settings.VALUATION_PARQUET)
    return before, len(out)


def main() -> int:
    before, after = clean_valuation()
    print(f"valuation cleaned: {before:,} -> {after:,} rows; weekends removed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
