"""全局路径与常量（v3：五链投研台）。"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
WEB_DIR = ROOT / "web"
DOCS_DIR = ROOT / "docs"

STATE_DB = DATA_DIR / "state.sqlite"
CACHE_DB = DATA_DIR / "cache.sqlite"

OHLCV_PARQUET = DATA_DIR / "ohlcv.parquet"
FUNDAMENTALS_PARQUET = DATA_DIR / "fundamentals.parquet"
VALUATION_PARQUET = DATA_DIR / "valuation.parquet"
SENTIMENT_PARQUET = DATA_DIR / "sentiment.parquet"
BUSINESS_PARQUET = DATA_DIR / "business.parquet"
BUSINESS_DESC_PARQUET = DATA_DIR / "business_desc.parquet"
VALUATION_EXT_PARQUET = DATA_DIR / "valuation_ext.parquet"
FINANCIALS_EXT_PARQUET = DATA_DIR / "financials_ext.parquet"
DIVIDENDS_PARQUET = DATA_DIR / "dividends.parquet"
FORECAST_PARQUET = DATA_DIR / "forecast.parquet"
CHIPS_PARQUET = DATA_DIR / "chips.parquet"
MACRO_FUTURES_PARQUET = DATA_DIR / "macro_futures.parquet"

TZ = "Asia/Shanghai"
CACHE_TTL_SECONDS = 30


def ensure_dirs() -> None:
    for d in (DATA_DIR, WEB_DIR, DOCS_DIR):
        d.mkdir(parents=True, exist_ok=True)
