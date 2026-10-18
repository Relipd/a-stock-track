"""AkShare 通用采集函数（行情/财务/估值/舆情/基准），供 fetch_chains 复用。
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings  # noqa: E402
from data_engine import ak_cache, chains as universe  # noqa: E402

ak_cache.install()

OHLCV_COLS = ["symbol", "trade_date", "open", "high", "low", "close", "volume", "amount", "turnover"]
FUND_COLS = ["symbol", "report_date", "revenue_yoy", "profit_yoy", "gross_margin", "net_margin",
             "roe", "inventory_days", "receivable_days", "debt_ratio", "ocf_to_profit"]
VAL_COLS = ["symbol", "trade_date", "pe_ttm", "pb", "pe_pct_3y", "pb_pct_3y", "pe_pct_1y", "pb_pct_1y"]
SENT_COLS = ["symbol", "name", "trade_date", "score", "attention", "institution", "pe_dynamic",
             "turnover", "price", "pct_chg"]


def _sleep(seconds: float = 0.45) -> None:
    time.sleep(seconds)


def _retry(fn, attempts: int = 3, wait: float = 1.2):
    last = None
    for i in range(attempts):
        try:
            return fn()
        except Exception as exc:  # noqa: BLE001 - 数据源不稳定
            last = exc
            time.sleep(wait * (i + 1))
    raise last  # type: ignore[misc]


def _atomic_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.parquet")
    df.to_parquet(tmp, index=False)
    os.replace(tmp, path)


def fetch_ohlcv(symbol: str, start: str, end: str) -> pd.DataFrame:
    """优先新浪（稳定），失败回退腾讯/东财；统一为元/股/%。"""
    import akshare as ak
    code = universe.ak_code(symbol)
    prefix = "sh" if symbol.endswith(".SH") else "sz"
    sina_code = prefix + code

    def from_sina() -> pd.DataFrame:
        raw = ak.stock_zh_a_daily(symbol=sina_code, start_date=start, end_date=end, adjust="qfq")
        if raw is None or raw.empty:
            raise ValueError("empty")
        return pd.DataFrame({
            "symbol": symbol,
            "trade_date": pd.to_datetime(raw["date"]),
            "open": pd.to_numeric(raw["open"], errors="coerce"),
            "high": pd.to_numeric(raw["high"], errors="coerce"),
            "low": pd.to_numeric(raw["low"], errors="coerce"),
            "close": pd.to_numeric(raw["close"], errors="coerce"),
            "volume": pd.to_numeric(raw["volume"], errors="coerce"),
            "amount": pd.to_numeric(raw["amount"], errors="coerce"),
            "turnover": pd.to_numeric(raw["turnover"], errors="coerce") * 100,
        })

    def from_tx() -> pd.DataFrame:
        raw = ak.stock_zh_a_hist_tx(symbol=sina_code, start_date=start, end_date=end, adjust="qfq")
        if raw is None or raw.empty:
            raise ValueError("empty")
        return pd.DataFrame({
            "symbol": symbol,
            "trade_date": pd.to_datetime(raw["date"]),
            "open": pd.to_numeric(raw["open"], errors="coerce"),
            "high": pd.to_numeric(raw["high"], errors="coerce"),
            "low": pd.to_numeric(raw["low"], errors="coerce"),
            "close": pd.to_numeric(raw["close"], errors="coerce"),
            "volume": pd.to_numeric(raw["volume"], errors="coerce") * 100,
            "amount": pd.to_numeric(raw["amount"], errors="coerce"),
            "turnover": pd.to_numeric(raw["turnover"], errors="coerce") * 100,
        })

    for fn in (from_sina, from_tx):
        try:
            return fn().dropna(subset=["close"]).sort_values("trade_date").reset_index(drop=True)
        except Exception:  # noqa: BLE001 - 换源重试
            time.sleep(0.6)
    return pd.DataFrame(columns=OHLCV_COLS)


def _clean_pct(series: pd.Series) -> pd.Series:
    if series.dtype == object:
        series = (series.astype(str).str.replace("%", "", regex=False)
                  .str.replace(",", "", regex=False).str.strip().replace({"--": None, "nan": None}))
    return pd.to_numeric(series, errors="coerce")


def _clean_num(series: pd.Series) -> pd.Series:
    if series.dtype == object:
        series = (series.astype(str).str.replace(",", "", regex=False).str.strip()
                  .replace({"--": None, "nan": None}))
    return pd.to_numeric(series, errors="coerce")


def fetch_fundamentals(symbol: str, start_year: str) -> pd.DataFrame:
    """优先同花顺摘要（毛利率字段完整），失败回退财务指标接口。"""
    import akshare as ak
    code = universe.ak_code(symbol)
    try:
        raw = _retry(lambda: ak.stock_financial_abstract_ths(symbol=code, indicator="按报告期"))
    except Exception:
        raw = None
    if raw is not None and not raw.empty:
        cols = {
            "revenue_yoy": "营业总收入同比增长率",
            "profit_yoy": "净利润同比增长率",
            "gross_margin": "销售毛利率",
            "net_margin": "销售净利率",
            "roe": "净资产收益率",
            "inventory_days": "存货周转天数",
            "receivable_days": "应收账款周转天数",
            "debt_ratio": "资产负债率",
        }
        df = pd.DataFrame({"symbol": symbol, "report_date": pd.to_datetime(raw["报告期"])})
        for key, col in cols.items():
            df[key] = _clean_pct(raw[col]) if key not in ("inventory_days", "receivable_days") else _clean_num(raw[col])
        df["ocf_to_profit"] = None
        df = df.dropna(subset=["report_date"]).sort_values("report_date")
        return df[FUND_COLS].reset_index(drop=True)

    raw = _retry(lambda: ak.stock_financial_analysis_indicator(symbol=code, start_year=start_year))
    if raw is None or raw.empty:
        return pd.DataFrame(columns=FUND_COLS)
    df = pd.DataFrame({
        "symbol": symbol,
        "report_date": pd.to_datetime(raw["日期"]),
        "revenue_yoy": _clean_pct(raw.get("主营业务收入增长率(%)", pd.Series(dtype=float))),
        "profit_yoy": _clean_pct(raw.get("净利润增长率(%)", pd.Series(dtype=float))),
        "gross_margin": _clean_pct(raw.get("销售毛利率(%)", pd.Series(dtype=float))),
        "net_margin": _clean_pct(raw.get("销售净利率(%)", pd.Series(dtype=float))),
        "roe": _clean_pct(raw.get("净资产收益率(%)", pd.Series(dtype=float))),
        "inventory_days": _clean_num(raw.get("存货周转天数(天)", pd.Series(dtype=float))),
        "receivable_days": _clean_num(raw.get("应收账款周转天数(天)", pd.Series(dtype=float))),
        "debt_ratio": _clean_pct(raw.get("资产负债率(%)", pd.Series(dtype=float))),
        "ocf_to_profit": _clean_num(raw.get("经营现金净流量与净利润的比率", pd.Series(dtype=float))),
    })
    return df.dropna(subset=["report_date"]).sort_values("report_date").reset_index(drop=True)


def _pct_rank(series: pd.Series) -> pd.Series:
    valid = series.dropna()
    if valid.empty:
        return pd.Series(index=series.index, dtype=float)
    rank = valid.expanding(min_periods=20).apply(lambda s: float((s <= s.iloc[-1]).mean()))
    return rank.reindex(series.index)


def _rolling_pct(series: pd.Series) -> pd.Series:
    valid = series.dropna()
    if valid.empty:
        return pd.Series(index=series.index, dtype=float)
    rank = valid.rolling(250, min_periods=120).apply(lambda s: float((s <= s.iloc[-1]).mean()))
    return rank.reindex(series.index)


def fetch_valuation(symbol: str, start: str) -> pd.DataFrame:
    import akshare as ak
    code = universe.ak_code(symbol)

    def get(indicator: str) -> pd.DataFrame:
        raw = _retry(lambda: ak.stock_zh_valuation_baidu(symbol=code, indicator=indicator, period="近三年"))
        if raw is None or raw.empty:
            return pd.DataFrame(columns=["trade_date", indicator])
        out = pd.DataFrame({
            "trade_date": pd.to_datetime(raw["date"]),
            indicator: pd.to_numeric(raw["value"], errors="coerce"),
        })
        return out.dropna().sort_values("trade_date")

    pe = get("市盈率(TTM)")
    pb = get("市净率")
    if pe.empty and pb.empty:
        return pd.DataFrame(columns=VAL_COLS)
    df = pe.merge(pb, on="trade_date", how="outer").sort_values("trade_date")
    # 去掉周末/明显重复的非交易日；节假日由本地行情日历在加载时再过滤
    df = df[df["trade_date"].dt.dayofweek < 5]
    df = df.dropna(subset=["市盈率(TTM)", "市净率"], how="all")
    pe_s = df["市盈率(TTM)"]
    pb_s = df["市净率"]
    df["pe_ttm"] = pe_s
    df["pb"] = pb_s
    df["pe_pct_3y"] = _pct_rank(pe_s) if pe_s.notna().any() else None
    df["pb_pct_3y"] = _pct_rank(pb_s) if pb_s.notna().any() else None
    df["pe_pct_1y"] = _rolling_pct(pe_s)
    df["pb_pct_1y"] = _rolling_pct(pb_s)
    df["symbol"] = symbol
    df = df[df["trade_date"] >= pd.to_datetime(start)]
    return df[VAL_COLS].reset_index(drop=True)


def fetch_sentiment(symbols: list[str] | None = None) -> pd.DataFrame:
    """东财千股千评快照，过滤到给定标的池（默认全部产业链）。"""
    import akshare as ak
    syms = symbols or universe.symbols()
    raw = _retry(lambda: ak.stock_comment_em())
    if raw is None or raw.empty:
        return pd.DataFrame(columns=SENT_COLS)
    raw = raw.copy()
    raw["代码"] = raw["代码"].astype(str).str.zfill(6)
    code_to_symbol = {universe.ak_code(s): s for s in syms}
    raw = raw[raw["代码"].isin(code_to_symbol)]
    rows = []
    for rec in raw.to_dict("records"):
        sym = code_to_symbol.get(str(rec.get("代码")).zfill(6))
        if not sym:
            continue
        rows.append({
            "symbol": sym, "name": universe.name_of(sym),
            "trade_date": pd.to_datetime(rec.get("交易日") or datetime.now().date()),
            "score": rec.get("综合得分"),
            "attention": rec.get("关注指数"),
            "institution": rec.get("机构参与度"),
            "pe_dynamic": rec.get("市盈率"),
            "turnover": rec.get("换手率"),
            "price": rec.get("最新价"),
            "pct_chg": rec.get("涨跌幅"),
        })
    return pd.DataFrame(rows, columns=SENT_COLS)


def fetch_benchmark(start: str, end: str) -> pd.DataFrame:
    import akshare as ak
    try:
        raw = _retry(lambda: ak.stock_zh_index_daily(symbol=universe.benchmark()["index"]))
    except Exception:
        return pd.DataFrame(columns=OHLCV_COLS)
    if raw is None or raw.empty:
        return pd.DataFrame(columns=OHLCV_COLS)
    df = pd.DataFrame({
        "symbol": universe.benchmark()["symbol"],
        "trade_date": pd.to_datetime(raw["date"]),
        "open": pd.to_numeric(raw["open"], errors="coerce"),
        "high": pd.to_numeric(raw["high"], errors="coerce"),
        "low": pd.to_numeric(raw["low"], errors="coerce"),
        "close": pd.to_numeric(raw["close"], errors="coerce"),
        "volume": pd.to_numeric(raw["volume"], errors="coerce"),
        "amount": pd.NA,
        "turnover": pd.NA,
    })
    df = df[df["trade_date"] >= pd.to_datetime(start)]
    return df.dropna(subset=["close"]).sort_values("trade_date").reset_index(drop=True)
