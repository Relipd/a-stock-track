"""数据层契约测试（五条产业链真实数据）。"""
from __future__ import annotations

import pytest

from app.data import store
from data_engine import chains


pytestmark = pytest.mark.skipif(not store.ok, reason="本地还没有采集数据")

EXPECTED = {"whites": 40, "pv": 40, "auto": 40, "copper": 40, "tourism": 40}


def test_five_chains_config():
    assert chains.chain_ids() == ["whites", "pv", "auto", "copper", "tourism"]
    for cid, n in EXPECTED.items():
        assert len(chains.symbols(cid)) == n, cid
    assert len(chains.all_symbols()) == 200
    assert len(set(chains.all_symbols())) == 200


def test_all_chains_have_real_metrics():
    for cid in chains.chain_ids():
        stocks = store.chain_metrics(cid)
        assert len(stocks) == EXPECTED[cid], f"{cid} 有效行情 {len(stocks)}"
        for s in stocks:
            assert s["price"] and s["price"] > 0
            assert s["gross_margin"] is not None, f"{s['symbol']} 缺毛利率"
            assert s["revenue_yoy"] is not None, f"{s['symbol']} 缺营收增速"
            basis_pct = s["pb_pct_3y"] if s["node_id"] and chains.valuation_basis(cid) == "pb" else s["pe_pct_3y"]
            assert basis_pct is not None and 0 <= basis_pct <= 1, f"{s['symbol']} 分位异常"


def test_chain_aggregates():
    aggs = store.all_chain_aggregates()
    assert len(aggs) == 5
    for a in aggs:
        assert a["stocks"] == 40
        assert a["median_pct"] is not None
        assert a["pct_20d"] is not None
        assert a["kpis"], f"{a['id']} 缺 KPI 定义"


def test_benchmark_and_as_of():
    assert store.as_of() >= "2026-09-01"
    bench = store.benchmark()
    assert bench and bench["symbol"] == "000300.SH"
    assert bench["pct_20d"] is not None and bench["pct_60d"] is not None


def test_series():
    for sym in ("000333.SZ", "600438.SH", "002594.SZ", "601899.SH", "600754.SH"):
        px = store.price_series(sym)
        assert len(px) > 400, sym
        assert px[-1]["high"] is not None and px[-1]["low"] is not None, sym
        assert len(store.valuation_series(sym)) > 400, sym
        assert len(store.financials(sym)) >= 6, sym


def test_business_composition():
    assert len(store.business) > 1000
    assert len(store.business["symbol"].unique()) >= 199
    b = store.business_of("600438.SH")
    assert b and b["products"], "通威缺主营构成"
    assert b["report_date"] >= "2026-06-30"
    assert abs(sum(p["ratio"] for p in b["products"]) - 1) < 0.15
    assert b["regions"] and b["main_business"]


def test_node_metrics_and_scissors():
    for cid in chains.chain_ids():
        nodes = store.node_aggregates(cid)
        assert nodes, cid
        for n in nodes:
            assert "inventory_days_delta" in n
            assert "median_receivable_days" in n
            assert "p25_pct" in n and "p75_pct" in n
            assert "median_roic" in n and "median_ccc" in n
            assert "median_fcf_yield" in n and "median_forward_pe" in n
        sc = store.scissors(cid)
        assert sc["value"] is not None, cid
        assert sc["label"]


def test_extended_metrics_and_proxies():
    m = store.stock_metrics("000333.SZ")
    assert m["total_mv"] and m["total_mv"] > 0
    assert m["ps_ttm"] is not None
    assert m["roic"] is not None
    assert m["fcf_yield"] is not None
    assert m["forward_pe"] is not None
    assert m["overseas"]["ratio"] is not None
    assert m["holder_num_chg_pct"] is not None
    assert store.proxies("copper"), "copper 缺外部代理"
    assert any(p["series_id"] == "CU0" for p in store.proxies("copper"))
    assert store.proxies("tourism")


def test_valuation_trading_days_only():
    v = store.val
    assert not v.empty
    assert (v["trade_date"].dt.dayofweek < 5).all(), "估值序列仍含周末"
    last = v["trade_date"].max().strftime("%Y-%m-%d")
    assert last <= store.as_of()
