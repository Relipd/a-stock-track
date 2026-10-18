"""v3 API 契约测试：多链 / 总览 / 单链 / 跨链写入与月度体检。"""
from __future__ import annotations


def _get(client, path, **params):
    r = client.get(path, params=params)
    assert r.status_code == 200, (path, r.status_code, r.text[:300])
    return r.json()


def test_meta_and_master(client):
    meta = _get(client, "/api/meta")
    assert len(meta["chains"]) == 5
    assert {c["id"] for c in meta["chains"]} == {"whites", "pv", "auto", "copper", "tourism"}
    assert meta["counts"]["stocks"] == 200
    assert meta["benchmark"]["symbol"] == "000300.SH"

    master = _get(client, "/api/master")
    assert len(master["chains"]) == 5
    assert master["summary"]["chains"] == 5
    for c in master["chains"]:
        for key in ("median_pct", "relative_60d", "holdings_weight", "theses", "alerts"):
            assert key in c, (c["id"], key)


def test_overview_each_chain(client):
    for cid in ("whites", "pv", "auto", "copper", "tourism"):
        data = _get(client, "/api/overview", chain=cid)
        assert data["chain"]["id"] == cid
        assert len(data["stocks"]) == 40
        assert len(data["nodes"]) >= 3
        assert len(data["reads"]) == 6
        assert data["chain"]["valuation_basis"] in ("pe", "pb")
        assert data["stocks"][0]["chain_id"] == cid
        assert len(data["distribution"]) == len(data["nodes"])
        assert data["scissors"]["value"] is not None
        assert "inventory_days_delta" in data["nodes"][0]
        assert data["proxies"], cid
        assert "median_roic" in data["nodes"][0]
        sample = data["stocks"][0]
        assert sample["ranks"], cid
        rank = next(iter(sample["ranks"].values()))
        assert 1 <= rank["rank"] <= rank["n"]
    assert client.get("/api/overview", params={"chain": "nope"}).status_code == 404


def test_compare(client):
    data = _get(client, "/api/compare", symbols="600438.SH,688303.SH,600089.SH")
    assert len(data["stocks"]) == 3
    assert data["chain"]["id"] == "pv"
    assert data["node"]["id"] == "silicon"
    assert len(data["series"]) > 1000
    assert all(s["value"] is not None for s in data["series"][:20])
    assert all(s.get("ranks") for s in data["stocks"])
    all_silicon = "600438.SH,688303.SH,600089.SH,601865.SH,603806.SH,002623.SZ,603260.SH,300821.SZ"
    full = _get(client, "/api/compare", symbols=all_silicon)
    assert len(full["stocks"]) == 8
    assert full["max_selectable"] >= 8
    # 跨链 / 跨节点必须拒绝
    r = client.get("/api/compare", params={"symbols": "600438.SH,000333.SZ"})
    assert r.status_code == 400
    assert client.get("/api/compare", params={"symbols": "600438.SH"}).status_code == 400
    assert client.get("/api/compare", params={"symbols": "600438.SH,999999.SZ"}).status_code == 404


def test_star_and_invest_flow(client):
    assert client.post("/api/star/note", json={"symbol": "000333.SZ", "note": "x"}).status_code == 409
    assert client.post("/api/star/invest", json={"symbol": "000333.SZ", "active": True}).status_code == 409
    assert client.post("/api/star", json={"symbol": "000333.SZ", "active": True}).status_code == 200
    assert client.post("/api/star/invest", json={"symbol": "000333.SZ", "active": True}).status_code == 409
    assert client.post("/api/star/note", json={"symbol": "000333.SZ", "note": "成本下行 + 出海"}).status_code == 200
    assert client.post("/api/star/invest", json={"symbol": "000333.SZ", "active": True}).status_code == 200
    # 投资加星期间不能撤星
    assert client.post("/api/star", json={"symbol": "000333.SZ", "active": False}).status_code == 409
    d = client.post("/api/invest/decision", json={
        "symbol": "000333.SZ", "date": "2026-10-10", "price": 80.0,
        "weight_pct": 5, "logic": "测试结算", "kill_switch": "毛利率跌破 25%",
    })
    assert d.status_code == 200
    assert d.json()["star"]["investment_star"] == 0
    assert d.json()["decision"]["trade_date"] == "2026-10-10"
    # 结算后可撤星，逻辑评语保留
    assert client.post("/api/star", json={"symbol": "000333.SZ", "active": False}).status_code == 200
    stars = _get(client, "/api/stars")
    assert not any(x["star"]["symbol"] == "000333.SZ" for x in stars["stars"])
    assert any(x["star"]["logic_note"] == "成本下行 + 出海" for x in stars["archived"])


def test_stock_detail_across_chains(client):
    for sym, name in (("600438.SH", "通威股份"), ("002594.SZ", "比亚迪"), ("601899.SH", "紫金矿业")):
        data = _get(client, f"/api/stock/{sym}")
        assert data["stock"]["name"] == name
        assert data["stock"]["chain_id"]
        assert data["stock"]["valuation_basis"] in ("pe", "pb")
        assert len(data["price"]) > 400
        assert data["price"][-1]["high"] is not None
        assert data["stock"]["high_52w"] and data["stock"]["low_52w"]
        if sym == "600438.SH":
            assert data["business"]["products"]
            assert data["business"]["report_date"]
            assert data["business"]["overseas"]["ratio"] is not None
            assert data["stock"]["total_mv"] and data["stock"]["forward_pe"]
            assert data["ranks"]


def test_cross_chain_manual_flow(client):
    # 白电：建逻辑 + 假设 + 买入
    assert client.post("/api/thesis", json={
        "symbol": "000333.SZ", "status": "watch", "title": "整机龙头",
        "core_logic": "成本下行 + 出海", "valuation_view": "PE 分位 42%", "horizon": "6-12 个月",
    }).status_code == 200
    a = client.post("/api/assumption", json={
        "symbol": "000333.SZ", "scope": "stock", "statement": "Q3 毛利率提升",
        "deadline": "2026-10-31",
    })
    assert a.status_code == 200
    d1 = client.post("/api/decision", json={
        "symbol": "000333.SZ", "action": "buy", "price": 77.2, "weight_pct": 8,
        "logic": "估值低位", "kill_switch": "毛利率 < 26%",
    })
    assert d1.status_code == 200 and len(d1.json()["decision"]["snapshot_hash"]) == 64

    # 光伏：另一条链的决策，验证跨链聚合
    d2 = client.post("/api/decision", json={
        "symbol": "600438.SH", "action": "watch", "price": 20.0, "weight_pct": 0,
        "logic": "硅料价格触底观察", "kill_switch": "价格继续下行",
    })
    assert d2.status_code == 200

    master = _get(client, "/api/master")
    assert master["summary"]["positions"] == 1
    assert master["summary"]["total_weight"] == 8
    assert len(master["positions"]) == 1
    assert master["positions"][0]["chain_id"] == "whites"
    assert any(c["id"] == "whites" and c["holdings_weight"] == 8 for c in master["chains"])

    pv = _get(client, "/api/overview", chain="pv")
    assert any(s["symbol"] == "600438.SH" for s in pv["stocks"])

    # 月度体检只看已加星标的
    for sym in ("000333.SZ", "600438.SH"):
        assert client.post("/api/star", json={"symbol": sym, "active": True}).status_code == 200
    review_all = _get(client, "/api/review", month="2026-10")
    assert review_all["summary"]["positions"] == 1
    assert review_all["summary"]["stars"] == 2
    assert review_all["summary"]["invest"] == 1
    assert review_all["summary"]["watch"] == 1
    assert review_all["chain_id"] == ""
    assert len(review_all["decisions"]) == 2
    assert all(b["stage"] in ("invest", "watch") for b in review_all["board"])

    review_whites = _get(client, "/api/review", month="2026-10", chain="whites")
    assert review_whites["chain_name"] == "白色家电"
    assert len(review_whites["decisions"]) == 1
    assert all(b["chain_id"] == "whites" for b in review_whites["board"])
    assert all(b["symbol"] in ("000333.SZ", "600438.SH") for b in review_all["board"])

    review_narrow = _get(client, "/api/review", month="2026-10", scope="narrow")
    assert review_narrow["summary"]["stars"] == 1
    assert review_narrow["summary"]["invest"] == 1
    assert review_narrow["summary"]["watch"] == 0
    assert len(review_narrow["decisions"]) == 1

    saved = client.post("/api/review", json={"month": "2026-10", "chain_id": "whites",
                                             "content_md": "# 白电复盘\n\n本月建仓美的。"})
    assert saved.status_code == 200
    export = client.get("/api/export/review", params={"month": "2026-10", "chain": "whites"})
    assert export.status_code == 200 and "本月建仓美的" in export.text


def test_validation_and_inbox(client):
    assert client.post("/api/thesis", json={"symbol": "999999.SZ"}).status_code == 400
    assert client.post("/api/decision", json={"symbol": "000333.SZ", "action": "xxx"}).status_code == 400
    assert client.post("/api/assumption", json={"symbol": "000333.SZ", "statement": " "}).status_code == 400
    assert client.get("/api/review", params={"month": "2026/10"}).status_code == 400

    # 估值提醒只对"已建立逻辑"的标的生效；石头科技 PE 分位极低，建逻辑后应出现
    assert client.post("/api/thesis", json={"symbol": "688169.SH", "status": "watch",
                                            "title": "清洁电器观察"}).status_code == 200
    inbox = _get(client, "/api/inbox")
    assert isinstance(inbox, list) and inbox
    assert all(i["chain_id"] for i in inbox)
    first = inbox[0]["id"]
    client.post(f"/api/alerts/{first}/resolve")
    assert first not in {x["id"] for x in _get(client, "/api/inbox")}

    whites_inbox = _get(client, "/api/inbox", chain="whites")
    assert all(i["chain_id"] == "whites" for i in whites_inbox)


def test_health(client):
    h = _get(client, "/api/health")
    assert h["status"] == "ok" and h["data_ok"] is True
