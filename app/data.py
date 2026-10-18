"""只读数据层（v3）：加载五条产业链的本地 Parquet，提供指标、序列与链级聚合。

不做网络请求、不写文件。缺失数据返回空结构。
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from config.settings import (
    BUSINESS_DESC_PARQUET,
    BUSINESS_PARQUET,
    CHIPS_PARQUET,
    DIVIDENDS_PARQUET,
    FINANCIALS_EXT_PARQUET,
    FORECAST_PARQUET,
    FUNDAMENTALS_PARQUET,
    MACRO_FUTURES_PARQUET,
    OHLCV_PARQUET,
    SENTIMENT_PARQUET,
    VALUATION_EXT_PARQUET,
    VALUATION_PARQUET,
)
from data_engine import chains as chain_cfg


def _num(v, nd: int = 2):
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if pd.isna(x):
        return None
    return round(x, nd)


def median(values: list) -> float | None:
    clean = sorted(float(v) for v in values if v is not None)
    if not clean:
        return None
    n = len(clean)
    mid = clean[n // 2] if n % 2 else (clean[n // 2 - 1] + clean[n // 2]) / 2
    return round(mid, 3)


class DataStore:
    def __init__(self) -> None:
        self.ohlcv = pd.DataFrame()
        self.fund = pd.DataFrame()
        self.val = pd.DataFrame()
        self.sent = pd.DataFrame()
        self.business = pd.DataFrame()
        self.business_desc = pd.DataFrame()
        self.val_ext = pd.DataFrame()
        self.fin_ext = pd.DataFrame()
        self.ratios = pd.DataFrame()
        self.divs = pd.DataFrame()
        self.forecast = pd.DataFrame()
        self.chips = pd.DataFrame()
        self.macro = pd.DataFrame()
        self.reload()

    def reload(self) -> None:
        def read(path: Path) -> pd.DataFrame:
            if not path.exists():
                return pd.DataFrame()
            df = pd.read_parquet(path)
            for col in ("trade_date", "report_date"):
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col])
            return df

        self.ohlcv = read(OHLCV_PARQUET)
        self.fund = read(FUNDAMENTALS_PARQUET)
        self.val = read(VALUATION_PARQUET)
        if not self.ohlcv.empty and not self.val.empty:
            trading = set(self.ohlcv.loc[self.ohlcv["symbol"] == "000300.SH", "trade_date"])
            if not trading:
                trading = set(self.ohlcv["trade_date"])
            self.val = self.val[self.val["trade_date"].isin(trading)].copy()
        self.sent = read(SENTIMENT_PARQUET)
        self.business = read(BUSINESS_PARQUET)
        self.business_desc = read(BUSINESS_DESC_PARQUET)
        self.val_ext = read(VALUATION_EXT_PARQUET)
        self.fin_ext = read(FINANCIALS_EXT_PARQUET)
        self.ratios = read(FINANCIALS_EXT_PARQUET.parent / "financial_ratios_ext.parquet")
        self.divs = read(DIVIDENDS_PARQUET)
        self.forecast = read(FORECAST_PARQUET)
        self.chips = read(CHIPS_PARQUET)
        self.macro = read(MACRO_FUTURES_PARQUET)
        self._px = {s: d.sort_values("trade_date") for s, d in self.ohlcv.groupby("symbol")} if not self.ohlcv.empty else {}
        self._fund = {s: d.sort_values("report_date") for s, d in self.fund.groupby("symbol")} if not self.fund.empty else {}
        self._val = {s: d.sort_values("trade_date") for s, d in self.val.groupby("symbol")} if not self.val.empty else {}
        self._sent = {s: d for s, d in self.sent.groupby("symbol")} if not self.sent.empty else {}
        self._biz = {s: d for s, d in self.business.groupby("symbol")} if not self.business.empty else {}
        self._biz_desc = {r["symbol"]: dict(r) for r in self.business_desc.to_dict("records")} if not self.business_desc.empty else {}
        self._ranks_cache: dict[str, dict] = {}
        self._val_ext = {s: d.sort_values("trade_date") for s, d in self.val_ext.groupby("symbol")} if not self.val_ext.empty else {}
        self._fin_ext = {s: d.sort_values("report_date") for s, d in self.fin_ext.groupby("symbol")} if not self.fin_ext.empty else {}
        self._ratios = {s: d.sort_values("report_date") for s, d in self.ratios.groupby("symbol")} if not self.ratios.empty else {}
        self._divs = {s: d for s, d in self.divs.groupby("symbol")} if not self.divs.empty else {}
        self._forecast = {r["symbol"]: dict(r) for r in self.forecast.to_dict("records")} if not self.forecast.empty else {}
        self._chips = {s: d.sort_values("report_date") for s, d in self.chips.groupby("symbol")} if not self.chips.empty else {}
        self._macro = {s: d.sort_values("date") for s, d in self.macro.groupby("series_id")} if not self.macro.empty else {}

    @property
    def ok(self) -> bool:
        return bool(self._px)

    def as_of(self) -> str:
        if not self._px:
            return ""
        return max(d["trade_date"].max() for d in self._px.values()).strftime("%Y-%m-%d")

    def updated_at(self) -> str | None:
        paths = [OHLCV_PARQUET, FUNDAMENTALS_PARQUET, VALUATION_PARQUET, SENTIMENT_PARQUET]
        stamps = [p.stat().st_mtime for p in paths if p.exists()]
        if not stamps:
            return None
        return pd.Timestamp(max(stamps), unit="s").tz_localize("UTC").tz_convert("Asia/Shanghai").isoformat(timespec="seconds")

    def benchmark(self) -> dict | None:
        meta = chain_cfg.benchmark()
        px = self._px.get(meta["symbol"])
        if px is None or len(px) < 2:
            return None
        last = px.iloc[-1]["close"]
        prev20 = px.iloc[-21]["close"] if len(px) > 21 else px.iloc[0]["close"]
        prev60 = px.iloc[-61]["close"] if len(px) > 61 else px.iloc[0]["close"]
        return {"symbol": meta["symbol"], "name": meta["name"], "close": _num(last),
                "pct_20d": _num((last / prev20 - 1) * 100),
                "pct_60d": _num((last / prev60 - 1) * 100)}

    def price_series(self, symbol: str, points: int = 760) -> list[dict]:
        px = self._px.get(symbol)
        if px is None:
            return []
        tail = px.tail(points)
        return [{"date": d.strftime("%Y-%m-%d"), "close": _num(c), "high": _num(h), "low": _num(l)}
                for d, c, h, l in zip(tail["trade_date"], tail["close"], tail["high"], tail["low"])]

    def valuation_series(self, symbol: str, points: int = 760) -> list[dict]:
        val = self._val.get(symbol)
        if val is None:
            return []
        tail = val.tail(points)
        return [{"date": r.trade_date.strftime("%Y-%m-%d"), "pe_ttm": _num(r.pe_ttm), "pb": _num(r.pb),
                 "pe_pct": _num(r.pe_pct_3y, 3), "pb_pct": _num(r.pb_pct_3y, 3)} for r in tail.itertuples()]

    def financials(self, symbol: str, points: int = 8) -> list[dict]:
        fund = self._fund.get(symbol)
        if fund is None:
            return []
        tail = fund.tail(points)
        return [{"report_date": r.report_date.strftime("%Y-%m-%d"), "revenue_yoy": _num(r.revenue_yoy),
                 "profit_yoy": _num(r.profit_yoy), "gross_margin": _num(r.gross_margin),
                 "net_margin": _num(r.net_margin), "roe": _num(r.roe),
                 "inventory_days": _num(r.inventory_days)} for r in tail.itertuples()]

    def _ttm(self, symbol: str, field: str) -> float | None:
        """把东财累计报表转成 TTM：最新累计 + 上年年报 − 上年同期。"""
        df = self._fin_ext.get(symbol)
        if df is None or df.empty or field not in df.columns:
            return None
        d = df.dropna(subset=[field])
        if d.empty:
            return None
        latest = d.iloc[-1]
        end = latest["report_date"]
        if pd.isna(end) or pd.isna(latest[field]):
            return None
        if end.month == 12:
            return float(latest[field])
        annual = d[(d["report_date"].dt.year == end.year - 1) & (d["report_date"].dt.month == 12)]
        prev = d[(d["report_date"].dt.year == end.year - 1) & (d["report_date"].dt.month == end.month)]
        if annual.empty or prev.empty:
            return None
        return float(latest[field]) + float(annual.iloc[-1][field]) - float(prev.iloc[-1][field])

    def _overseas(self, symbol: str) -> dict:
        df = self._biz.get(symbol)
        if df is None or df.empty:
            return {}
        latest = df["report_date"].max()
        prev_date = latest - pd.DateOffset(years=1)
        keys = ("境外", "海外", "国外", "外销", "其他国家和地区")
        excl = ("境内", "国内", "其他(补充)", "内部抵销", "其他（补充）", "内部抵消")

        def calc(date) -> tuple[float | None, float | None]:
            cur = df[(df["report_date"] == date) & (df["category"].astype(str).str.contains("地区"))]
            if cur.empty:
                return None, None
            rows = [r for r in cur.itertuples()
                    if any(k in str(r.item) for k in keys) and not any(x in str(r.item) for x in excl)]
            if not rows:
                return None, None
            ratio = sum(float(r.revenue_ratio) for r in rows if pd.notna(r.revenue_ratio))
            rev = sum(float(r.revenue) for r in rows if pd.notna(r.revenue))
            gm_num = sum(float(r.gross_margin) * float(r.revenue) for r in rows
                         if pd.notna(r.gross_margin) and pd.notna(r.revenue))
            gm = (gm_num / rev * 100) if rev else None
            return _num(ratio, 4), _num(gm, 2)

        ratio, gm = calc(latest)
        prev_ratio, _ = calc(prev_date)
        return {"report_date": pd.Timestamp(latest).strftime("%Y-%m-%d"),
                "ratio": ratio, "gross_margin": gm,
                "ratio_prev": prev_ratio,
                "ratio_delta": _num((ratio - prev_ratio) * 100, 2) if ratio is not None and prev_ratio is not None else None}

    def _ext_metrics(self, symbol: str, price: float, total_mv: float | None = None) -> dict:
        """估值扩展 + 三表 TTM + 财务指标 + 分红/预测/筹码。"""
        out: dict = {}
        val = self._val_ext.get(symbol)
        if val is not None and not val.empty:
            r = val.iloc[-1]
            out.update({
                "total_mv": _num(r.get("total_mv"), 0),
                "float_mv": _num(r.get("float_mv"), 0),
                "pe_ttm_em": _num(r.get("pe_ttm_em")),
                "pb_em": _num(r.get("pb_em")),
                "ps_ttm": _num(r.get("ps_ttm")),
                "pcf_ttm": _num(r.get("pcf_ttm")),
                "peg": _num(r.get("peg")),
            })
            total_mv = out.get("total_mv") or total_mv

        fin = self._fin_ext.get(symbol)
        if fin is not None and not fin.empty:
            r = fin.iloc[-1]
            for src, dst in (("TOTAL_PARENT_EQUITY", "parent_equity"), ("MONETARYFUNDS", "monetary_funds"),
                             ("SHORT_LOAN", "short_debt"), ("LONG_LOAN", "long_debt"),
                             ("BOND_PAYABLE", "bond_payable"), ("INVENTORY", "inventory_abs"),
                             ("ACCOUNTS_RECE", "accounts_rece"), ("CIP", "cip"),
                             ("FIXED_ASSET", "fixed_asset")):
                out[dst] = _num(r.get(src), 0)
            short = out.get("short_debt") or 0
            long = out.get("long_debt") or 0
            bond = out.get("bond_payable") or 0
            cash = out.get("monetary_funds") or 0
            equity = out.get("parent_equity") or 0
            net_debt = short + long + bond - cash
            out["net_debt"] = _num(net_debt, 0)
            out["net_debt_ratio"] = _num(net_debt / equity * 100, 1) if equity > 0 else None
            out["cash_to_short_debt"] = _num(cash / short, 2) if short > 0 else None
            out["fcf_ttm"] = _num((self._ttm(symbol, "NETCASH_OPERATE") or 0) -
                                 (self._ttm(symbol, "CONSTRUCT_LONG_ASSET") or 0), 0) \
                if self._ttm(symbol, "NETCASH_OPERATE") is not None else None
            out["capex_ttm"] = _num(self._ttm(symbol, "CONSTRUCT_LONG_ASSET"), 0)
            ebitda = None
            if self._ttm(symbol, "OPERATE_PROFIT") is not None:
                ebitda = sum((self._ttm(symbol, f) or 0) for f in
                             ("OPERATE_PROFIT", "FA_IR_DEPR", "IA_AMORTIZE", "LPE_AMORTIZE", "USERIGHT_ASSET_AMORTIZE"))
            out["ebitda_ttm"] = _num(ebitda, 0)
            imp = None
            if self._ttm(symbol, "ASSET_IMPAIRMENT_LOSS") is not None or self._ttm(symbol, "CREDIT_IMPAIRMENT_LOSS") is not None:
                imp = abs(self._ttm(symbol, "ASSET_IMPAIRMENT_LOSS") or 0) + abs(self._ttm(symbol, "CREDIT_IMPAIRMENT_LOSS") or 0)
            out["impairment_ttm"] = _num(imp, 0)
            out["impairment_to_equity"] = _num(imp / equity * 100, 2) if imp is not None and equity > 0 else None
            if total_mv and ebitda and ebitda > 0:
                out["ev_ebitda"] = _num((total_mv + net_debt) / ebitda, 2)
            if total_mv and out.get("fcf_ttm") is not None:
                out["fcf_yield"] = _num(out["fcf_ttm"] / total_mv * 100, 2)

        ratios = self._ratios.get(symbol)
        if ratios is not None and not ratios.empty:
            r = ratios.iloc[-1]
            for src, dst in (("DJD_TOI_YOY", "single_q_rev_yoy"), ("DJD_DPNP_YOY", "single_q_profit_yoy"),
                             ("ROIC", "roic"), ("ROEJQ", "roe_weighted"),
                             ("PAYABLE_TDAYS", "payable_days"), ("PREPAID_ACCOUNTS_TDAYS", "prepaid_days")):
                out[dst] = _num(r.get(src), 2)
            # 存货/应收天数取自 THS 摘要
            base = self._fund.get(symbol)
            if base is not None and not base.empty:
                br = base.iloc[-1]
                inv = _num(br.get("inventory_days"))
                ar = _num(br.get("receivable_days"))
                pay = out.get("payable_days")
                if inv is not None and ar is not None and pay is not None:
                    out["ccc"] = _num(inv + ar - pay, 1)
        out["overseas"] = self._overseas(symbol)

        div = self._divs.get(symbol)
        if div is not None and not div.empty and price:
            d = div.copy()
            d["ex_date"] = pd.to_datetime(d.get("ex_date"), errors="coerce")
            cutoff = pd.Timestamp.now().normalize() - pd.Timedelta(days=365)
            d = d[(d["progress"].astype(str) == "实施") & d["ex_date"].notna() &
                  (d["ex_date"] >= cutoff) & (d["ex_date"] <= pd.Timestamp.now())]
            if not d.empty:
                per_share = float(pd.to_numeric(d["cash_per_10"], errors="coerce").fillna(0).sum()) / 10
                out["dividend_yield"] = _num(per_share / price * 100, 2)
                out["dividend_per_share_12m"] = _num(per_share, 4)

        fc = self._forecast.get(symbol)
        if fc:
            out["report_count"] = _num(fc.get("report_count"), 0)
            out["eps_2026e"] = _num(fc.get("eps_2026e"))
            out["eps_2027e"] = _num(fc.get("eps_2027e"))
            for year, field in (("2026", "eps_2026e"), ("2027", "eps_2027e")):
                eps = out.get(field)
                if price and eps and eps > 0:
                    out["forward_pe"] = _num(price / eps, 2)
                    out["forward_pe_year"] = year
                    break

        chips = self._chips.get(symbol)
        if chips is not None and not chips.empty:
            r = chips.iloc[-1]
            out["holder_num"] = _num(r.get("holder_num"), 0)
            out["holder_num_chg_pct"] = _num(r.get("holder_num_chg_pct"), 2)
            out["avg_holder_mv"] = _num(r.get("avg_holder_mv"), 0)
            out["chips_date"] = pd.Timestamp(r["report_date"]).strftime("%Y-%m-%d") if pd.notna(r.get("report_date")) else None

        return out

    def stock_metrics(self, symbol: str) -> dict | None:
        px = self._px.get(symbol)
        if px is None or px.empty:
            return None
        close = px["close"].astype(float)
        last = float(close.iloc[-1])
        pct_1d = (last / float(close.iloc[-2]) - 1) * 100 if len(close) >= 2 else None
        pct_20d = (last / float(close.iloc[-21]) - 1) * 100 if len(close) >= 21 else None
        pct_60d = (last / float(close.iloc[-61]) - 1) * 100 if len(close) >= 61 else None
        tail = px.tail(250)
        high_52w = _num(tail["high"].max()) if "high" in tail else None
        low_52w = _num(tail["low"].min()) if "low" in tail else None

        val = self._val.get(symbol)
        pe = pe_pct = pb = pb_pct = None
        if val is not None and not val.empty:
            r = val.iloc[-1]
            pe, pe_pct = _num(r.get("pe_ttm")), _num(r.get("pe_pct_3y"), 3)
            pb, pb_pct = _num(r.get("pb")), _num(r.get("pb_pct_3y"), 3)

        fund = self._fund.get(symbol)
        gm = nm = roe = rev_yoy = prof_yoy = inv_days = recv_days = debt_ratio = None
        gm_chg = None
        if fund is not None and not fund.empty:
            r = fund.iloc[-1]
            gm, nm, roe = _num(r.get("gross_margin")), _num(r.get("net_margin")), _num(r.get("roe"))
            rev_yoy, prof_yoy = _num(r.get("revenue_yoy")), _num(r.get("profit_yoy"))
            inv_days = _num(r.get("inventory_days"))
            recv_days = _num(r.get("receivable_days"))
            debt_ratio = _num(r.get("debt_ratio"))
            if len(fund) >= 5:
                prev = fund.iloc[-5]
                if pd.notna(r.get("gross_margin")) and pd.notna(prev.get("gross_margin")):
                    gm_chg = _num(float(r["gross_margin"]) - float(prev["gross_margin"]))

        sent = self._sent.get(symbol)
        score = attention = institution = None
        if sent is not None and not sent.empty:
            r = sent.iloc[-1]
            score, attention, institution = _num(r.get("score")), _num(r.get("attention")), _num(r.get("institution"), 3)

        meta = chain_cfg.symbol_meta(symbol) or {}
        chain_id = meta.get("chain_id", "")
        node_id = meta.get("node_id", "")
        data = {
            "symbol": symbol, "name": meta.get("name", symbol),
            "chain_id": chain_id, "chain_name": meta.get("chain_name", ""),
            "node_id": node_id,
            "node_name": chain_cfg.node_name(chain_id, node_id) if chain_id else "",
            "role": meta.get("role", ""),
            "price": _num(last), "pct_1d": _num(pct_1d), "pct_20d": _num(pct_20d), "pct_60d": _num(pct_60d),
            "high_52w": high_52w, "low_52w": low_52w,
            "pe_ttm": pe, "pe_pct_3y": pe_pct, "pb": pb, "pb_pct_3y": pb_pct,
            "gross_margin": gm, "gross_margin_chg": gm_chg, "net_margin": nm, "roe": roe,
            "revenue_yoy": rev_yoy, "profit_yoy": prof_yoy, "inventory_days": inv_days,
            "receivable_days": recv_days, "debt_ratio": debt_ratio,
            "score": score, "attention": attention, "institution": institution,
        }
        data.update(self._ext_metrics(symbol, last))
        return data

    def business_of(self, symbol: str) -> dict | None:
        df = self._biz.get(symbol)
        if df is None or df.empty:
            return None
        latest = df["report_date"].max()
        cur = df[df["report_date"] == latest]

        def pack(category: str) -> list[dict]:
            sub = cur[cur["category"].astype(str).str.contains(category)]
            sub = sub.sort_values("revenue_ratio", ascending=False)
            return [{
                "item": str(r.item),
                "revenue": _num(r.revenue, 0),
                "ratio": _num(r.revenue_ratio, 4),
                "gross_margin": _num(r.gross_margin, 4),
            } for r in sub.itertuples()]

        desc = self._biz_desc.get(symbol, {})
        return {
            "report_date": pd.Timestamp(latest).strftime("%Y-%m-%d"),
            "products": pack("产品")[:8],
            "regions": pack("地区")[:6],
            "overseas": self._overseas(symbol),
            "main_business": desc.get("main_business", ""),
            "product_type": desc.get("product_type", ""),
            "product_name": desc.get("product_name", ""),
        }

    def macro_latest(self, series_id: str) -> dict | None:
        d = self._macro.get(series_id)
        if d is None or d.empty:
            return None
        d = d.dropna(subset=["value"])
        if d.empty:
            return None
        r = d.iloc[-1]
        out = {
            "series_id": series_id, "value": _num(r["value"], 2),
            "date": pd.Timestamp(r["date"]).strftime("%Y-%m-%d"),
            "freq": r.get("freq", ""), "unit": r.get("unit", ""),
            "source": r.get("source", ""),
        }
        if out["freq"] == "D" and len(d) > 61:
            v = float(r["value"])
            out["chg_20d"] = _num((v / float(d.iloc[-21]["value"]) - 1) * 100, 1) if float(d.iloc[-21]["value"]) else None
            out["chg_60d"] = _num((v / float(d.iloc[-61]["value"]) - 1) * 100, 1) if float(d.iloc[-61]["value"]) else None
            out["delta_20d"] = _num(v - float(d.iloc[-21]["value"]), 0)
        return out

    def proxies(self, chain_id: str) -> list[dict]:
        mapping = {
            "whites": [("CU0", "沪铜主力"), ("retail_yoy", "社零同比")],
            "pv": [("SI0", "工业硅主力")],
            "auto": [("LC0", "碳酸锂主力")],
            "copper": [("CU0", "沪铜主力"), ("cu_inv", "铜期货库存"), ("electricity_yoy", "全社会用电同比")],
            "tourism": [("pax_load", "民航客座率"), ("aviation_pax_yoy", "民航客运量同比"),
                        ("aviation_turnover", "民航总周转量")],
        }
        out = []
        for sid, label in mapping.get(chain_id, []):
            m = self.macro_latest(sid)
            if m:
                out.append({"label": label, **m})
        return out

    # ------------------------------------------------------------------ 链级聚合
    def chain_metrics(self, chain_id: str) -> list[dict]:
        return [m for m in (self.stock_metrics(s) for s in chain_cfg.symbols(chain_id)) if m]

    def _delta4(self, symbol: str, field: str) -> float | None:
        df = self._fund.get(symbol)
        if df is None or len(df) < 5:
            return None
        a, b = df.iloc[-1].get(field), df.iloc[-5].get(field)
        if pd.isna(a) or pd.isna(b):
            return None
        return float(a) - float(b)

    def peer_ranks(self, chain_id: str) -> dict[str, dict[str, dict]]:
        """同节点内的指标排名：1=最好，分母=该节点有效样本数。"""
        cache_key = f"ranks:{chain_id}"
        cached = getattr(self, "_ranks_cache", {}).get(cache_key)
        if cached is not None:
            return cached
        stocks = self.chain_metrics(chain_id)
        basis = chain_cfg.valuation_basis(chain_id)
        metrics = {
            "gross_margin": "desc", "revenue_yoy": "desc", "profit_yoy": "desc",
            "roe": "desc", "roic": "desc", "fcf_yield": "desc",
            "dividend_yield": "desc", "single_q_rev_yoy": "desc",
            "single_q_profit_yoy": "desc", "forward_pe": "asc",
            "inventory_days": "asc", "receivable_days": "asc",
            "ccc": "asc", "net_debt_ratio": "asc",
            "cash_to_short_debt": "desc",
        }
        out: dict[str, dict[str, dict]] = {}
        by_node: dict[str, list[dict]] = {}
        for s in stocks:
            by_node.setdefault(s.get("node_id", ""), []).append(s)
        for node_stocks in by_node.values():
            for metric, direction in metrics.items():
                vals = [(s, s.get(metric)) for s in node_stocks if s.get(metric) is not None]
                n = len(vals)
                if n < 3:
                    continue
                for s, value in vals:
                    if direction == "desc":
                        better = sum(1 for _, other in vals if other > value)
                    else:
                        better = sum(1 for _, other in vals if other < value)
                    out.setdefault(s["symbol"], {})[metric] = {"rank": better + 1, "n": n}
            # 估值分位按该链口径单独排名
            pct_key = "pb_pct_3y" if basis == "pb" else "pe_pct_3y"
            vals = [(s, s.get(pct_key)) for s in node_stocks if s.get(pct_key) is not None]
            n = len(vals)
            if n >= 3:
                for s, value in vals:
                    better = sum(1 for _, other in vals if other < value)
                    out.setdefault(s["symbol"], {})["valuation_pct"] = {"rank": better + 1, "n": n}
        self._ranks_cache = getattr(self, "_ranks_cache", {})
        self._ranks_cache[cache_key] = out
        return out

    def node_aggregates(self, chain_id: str) -> list[dict]:
        stocks = self.chain_metrics(chain_id)
        basis = chain_cfg.valuation_basis(chain_id)
        out = []
        for node in chain_cfg.nodes(chain_id):
            group = [s for s in stocks if s["node_id"] == node["id"]]
            if not group:
                continue
            pcts = [s["pb_pct_3y"] if basis == "pb" else s["pe_pct_3y"] for s in group]
            pcts = [p for p in pcts if p is not None]
            gm_deltas = [self._delta4(s["symbol"], "gross_margin") for s in group]
            inv_deltas = [self._delta4(s["symbol"], "inventory_days") for s in group]
            vals = sorted(pcts)
            p25 = vals[int(len(vals) * 0.25)] if vals else None
            p75 = vals[min(len(vals) - 1, int(len(vals) * 0.75))] if vals else None
            out.append({
                "id": node["id"], "name": node["name"], "role": node["role"],
                "description": node.get("description", ""), "stocks": len(group),
                "median_pct": median(pcts), "p25_pct": _num(p25, 3), "p75_pct": _num(p75, 3),
                "median_gross_margin": median([s["gross_margin"] for s in group]),
                "gross_margin_delta": median(gm_deltas),
                "median_inventory_days": median([s["inventory_days"] for s in group]),
                "inventory_days_delta": median(inv_deltas),
                "median_revenue_yoy": median([s["revenue_yoy"] for s in group]),
                "median_profit_yoy": median([s["profit_yoy"] for s in group]),
                "median_receivable_days": median([s.get("receivable_days") for s in group]),
                "median_debt_ratio": median([s.get("debt_ratio") for s in group]),
                "median_roe": median([s["roe"] for s in group]),
                "median_roic": median([s.get("roic") for s in group]),
                "median_ccc": median([s.get("ccc") for s in group]),
                "median_fcf_yield": median([s.get("fcf_yield") for s in group]),
                "median_forward_pe": median([s.get("forward_pe") for s in group]),
                "median_dividend_yield": median([s.get("dividend_yield") for s in group]),
                "median_single_q_rev_yoy": median([s.get("single_q_rev_yoy") for s in group]),
                "median_single_q_profit_yoy": median([s.get("single_q_profit_yoy") for s in group]),
                "median_net_debt_ratio": median([s.get("net_debt_ratio") for s in group]),
                "median_cash_to_short_debt": median([s.get("cash_to_short_debt") for s in group]),
                "median_overseas_ratio": median([(s.get("overseas") or {}).get("ratio") for s in group]),
                "pct_20d": median([s["pct_20d"] for s in group]),
                "pct_60d": median([s["pct_60d"] for s in group]),
            })
        return out

    def scissors(self, chain_id: str) -> dict:
        """用成分股代理计算“上游 − 下游”毛利率差及 4 季变化（不引入外部行业数据）。"""
        stocks = self.chain_metrics(chain_id)
        labels = {
            "whites": "上游零部件 − 下游毛利率差",
            "pv": "制造段 − 逆变器/电站毛利率差",
            "auto": "零部件 − 智能化/服务毛利率差",
            "copper": "矿端 − 电网终端毛利率差",
            "tourism": "酒店 − 景区毛利率差",
        }
        label = labels.get(chain_id, "上游−下游毛利率差")
        if chain_id == "tourism":
            up = [s for s in stocks if s["node_id"] == "hotel"]
            down = [s for s in stocks if s["node_id"] == "scenic"]
            note = "酒店运营 − 景区目的地 成分股毛利率中位差；旅游服务不在本口径内"
        else:
            up = [s for s in stocks if s["role"] == "upstream"]
            down = [s for s in stocks if s["role"] == "downstream"]
            note = "上游与下游节点成分股中位差，正数表示上游毛利率更高"
        if not up or not down:
            nodes = self.node_aggregates(chain_id)
            if len(nodes) < 2:
                return {"label": label, "value": None, "delta": None, "note": note}
            first, last = nodes[0], nodes[-1]
            up_gm, down_gm = first["median_gross_margin"], last["median_gross_margin"]
            up_d, down_d = first["gross_margin_delta"], last["gross_margin_delta"]
            note = f"{first['name']} − {last['name']} 毛利率差"
        else:
            up_gm = median([s["gross_margin"] for s in up])
            down_gm = median([s["gross_margin"] for s in down])
            up_d = median([self._delta4(s["symbol"], "gross_margin") for s in up])
            down_d = median([self._delta4(s["symbol"], "gross_margin") for s in down])
        if up_gm is None or down_gm is None:
            return {"label": label, "value": None, "delta": None, "note": note}
        return {
            "label": label,
            "value": _num(up_gm - down_gm, 2),
            "delta": _num((up_d or 0) - (down_d or 0), 2) if up_d is not None and down_d is not None else None,
            "note": note,
        }


    def chain_aggregate(self, chain_id: str) -> dict:
        stocks = self.chain_metrics(chain_id)
        basis = chain_cfg.valuation_basis(chain_id)
        pcts = [(s["pb_pct_3y"] if basis == "pb" else s["pe_pct_3y"]) for s in stocks]
        pcts = [p for p in pcts if p is not None]
        benchmark = self.benchmark()
        bench60 = benchmark.get("pct_60d") if benchmark else None
        med60 = median([s["pct_60d"] for s in stocks])
        c = chain_cfg.chain(chain_id) or {}
        return {
            "id": chain_id, "name": c.get("name", chain_id), "short": c.get("short", ""),
            "description": c.get("description", ""), "valuation_basis": basis,
            "stocks": len(stocks),
            "median_pct": median(pcts),
            "median_gross_margin": median([s["gross_margin"] for s in stocks]),
            "median_revenue_yoy": median([s["revenue_yoy"] for s in stocks]),
            "pct_20d": median([s["pct_20d"] for s in stocks]),
            "pct_60d": median([s["pct_60d"] for s in stocks]),
            "relative_60d": round((med60 or 0) - (bench60 or 0), 2),
            "up_20d": sum(1 for s in stocks if (s["pct_20d"] or 0) > 0),
            "down_20d": sum(1 for s in stocks if (s["pct_20d"] or 0) < 0),
            "high_pct": sum(1 for p in pcts if p >= 0.8),
            "low_pct": sum(1 for p in pcts if p <= 0.2),
            "kpis": chain_cfg.kpis(chain_id),
        }

    def all_chain_aggregates(self) -> list[dict]:
        return [self.chain_aggregate(cid) for cid in chain_cfg.chain_ids()]

    def node_valuation_distribution(self, chain_id: str) -> list[dict]:
        stocks = self.chain_metrics(chain_id)
        basis = chain_cfg.valuation_basis(chain_id)
        out = []
        for node in chain_cfg.nodes(chain_id):
            pts = []
            for s in stocks:
                if s["node_id"] != node["id"]:
                    continue
                p = s["pb_pct_3y"] if basis == "pb" else s["pe_pct_3y"]
                if p is not None:
                    pts.append({"symbol": s["symbol"], "name": s["name"], "pct": p})
            out.append({"node_id": node["id"], "name": node["name"], "points": pts})
        return out


store = DataStore()
