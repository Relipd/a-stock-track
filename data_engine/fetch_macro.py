"""P1 代理数据：期货主力、铜库存、月频宏观（长表）。

输出：data/macro_futures.parquet
列：series_id, date, freq, value, unit, source
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import settings  # noqa: E402
from data_engine import ak_cache  # noqa: E402

ak_cache.install()

COLS = ["series_id", "date", "freq", "value", "unit", "source"]


def _month(value: str) -> pd.Timestamp | None:
    s = str(value).strip()
    m = re.match(r"(\d{4})[.\-年](\d{1,2})", s)
    if not m:
        return None
    return pd.Timestamp(year=int(m.group(1)), month=int(m.group(2)), day=1)


def _futures(rows: list[dict], series_id: str, symbol: str, source: str, unit: str) -> None:
    try:
        import akshare as ak
        df = ak.futures_main_sina(symbol=symbol, start_date="20240101", end_date=datetime.now().strftime("%Y%m%d"))
        if df is None or df.empty:
            return
        df = df.copy()
        df["日期"] = pd.to_datetime(df["日期"], errors="coerce")
        for r in df.dropna(subset=["日期"]).itertuples():
            rows.append({"series_id": series_id, "date": r.日期, "freq": "D",
                         "value": float(r.收盘价), "unit": unit, "source": source})
    except Exception as exc:  # noqa: BLE001
        print(f"[macro] {series_id} 失败 {type(exc).__name__}: {exc}", flush=True)


def _append_month(rows: list[dict], series_id: str, date: pd.Timestamp, value, unit: str, source: str) -> None:
    if date is None or pd.isna(value):
        return
    rows.append({"series_id": series_id, "date": date, "freq": "M",
                 "value": float(value), "unit": unit, "source": source})


def main() -> int:
    rows: list[dict] = []
    import akshare as ak

    _futures(rows, "CU0", "CU0", "futures_main_sina", "元/吨")
    _futures(rows, "LC0", "LC0", "futures_main_sina", "元/吨")
    _futures(rows, "SI0", "SI0", "futures_main_sina", "元/吨")

    try:
        inv = ak.futures_inventory_em(symbol="cu")
        inv["日期"] = pd.to_datetime(inv["日期"], errors="coerce")
        for r in inv.dropna(subset=["日期"]).itertuples():
            rows.append({"series_id": "cu_inv", "date": r.日期, "freq": "D",
                         "value": float(r.库存), "unit": "吨", "source": "futures_inventory_em"})
    except Exception as exc:  # noqa: BLE001
        print(f"[macro] 铜库存失败 {type(exc).__name__}: {exc}", flush=True)

    try:
        d = ak.macro_china_consumer_goods_retail()
        for r in d.itertuples():
            _append_month(rows, "retail_yoy", _month(r.月份), getattr(r, "同比增长", None), "%",
                          "macro_china_consumer_goods_retail")
    except Exception as exc:  # noqa: BLE001
        print(f"[macro] 社零失败 {type(exc).__name__}: {exc}", flush=True)

    try:
        d = ak.macro_china_society_electricity()
        for r in d.itertuples():
            _append_month(rows, "electricity_yoy", _month(r.统计时间),
                          getattr(r, "全社会用电量同比", None), "%", "macro_china_society_electricity")
    except Exception as exc:  # noqa: BLE001
        print(f"[macro] 用电量失败 {type(exc).__name__}: {exc}", flush=True)

    try:
        d = ak.macro_china_passenger_load_factor()
        for r in d.itertuples():
            _append_month(rows, "pax_load", _month(r.统计时间), getattr(r, "客座率", None), "%",
                          "macro_china_passenger_load_factor")
    except Exception as exc:  # noqa: BLE001
        print(f"[macro] 客座率失败 {type(exc).__name__}: {exc}", flush=True)

    try:
        d = ak.macro_china_society_traffic_volume()
        av = d[d["统计对象"] == "民航"]
        for r in av.itertuples():
            _append_month(rows, "aviation_pax_yoy", _month(r.统计时间), getattr(r, "客运量同比增长", None), "%",
                          "macro_china_society_traffic_volume")
            _append_month(rows, "aviation_turnover", _month(r.统计时间), getattr(r, "民航总周转量", None), "亿人公里",
                          "macro_china_society_traffic_volume")
    except Exception as exc:  # noqa: BLE001
        print(f"[macro] 民航周转失败 {type(exc).__name__}: {exc}", flush=True)

    try:
        d = ak.macro_china_pmi()
        for r in d.itertuples():
            _append_month(rows, "pmi_manufacturing", _month(r.月份), getattr(r, "制造业-指数", None), "点",
                          "macro_china_pmi")
    except Exception as exc:  # noqa: BLE001
        print(f"[macro] PMI失败 {type(exc).__name__}: {exc}", flush=True)

    out = pd.DataFrame(rows, columns=COLS)
    if out.empty:
        print("[macro] 没有数据")
        return 1
    out = out.drop_duplicates(["series_id", "date"]).sort_values(["series_id", "date"])
    path = settings.MACRO_FUTURES_PARQUET
    tmp = path.with_suffix(".tmp.parquet")
    out.to_parquet(tmp, index=False)
    os.replace(tmp, path)
    print(f"[macro] {len(out):,} 行 / {out['series_id'].nunique()} 个序列 -> {path}")
    print(out.groupby("series_id")["date"].max().to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
