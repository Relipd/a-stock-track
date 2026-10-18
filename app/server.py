"""v3 FastAPI：五条产业链 · 纯人工分析工作台。

数据只读 Parquet；人的判断写 SQLite。无任何大模型调用。
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from datetime import date, datetime
from threading import Thread

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from app import db
from app.cache import cache
from app.data import median, store
from config import settings
from data_engine import chains

ACTION_LABEL = {"watch": "观察", "buy": "买入", "add": "加仓", "reduce": "减仓", "exit": "清仓"}
THESIS_LABEL = {"watch": "观察", "building": "分批建仓", "holding": "持有", "reduced": "已减仓", "closed": "已结案"}
STATUS_LABEL = {"pending": "待验证", "progress": "进行中", "met": "已兑现", "invalidated": "已证伪"}
BASIS_LABEL = {"pe": "PE", "pb": "PB", "ps": "PS"}


@asynccontextmanager
async def lifespan(_: FastAPI):
    settings.ensure_dirs()
    db.seed_chains(chains.chains())
    store.reload()
    yield


app = FastAPI(title="五链投研台", version="3.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_credentials=False,
    allow_methods=["*"], allow_headers=["*"],
)


def _today() -> date:
    return datetime.now().date()


def _valid_month(month: str) -> str:
    try:
        datetime.strptime(month, "%Y-%m")
    except ValueError:
        raise HTTPException(400, "month 格式应为 YYYY-MM")
    return month


def _chain_or_404(chain_id: str) -> dict:
    c = chains.chain(chain_id)
    if not c:
        raise HTTPException(404, f"未知产业链 {chain_id}")
    return c


def _pct_of(stock: dict, basis: str):
    return stock.get("pb_pct_3y") if basis == "pb" else stock.get("pe_pct_3y")


def _thesis_with_assumptions(symbol: str) -> dict | None:
    with db.db() as conn:
        thesis = db.get_thesis(conn, symbol)
    if not thesis:
        return None
    thesis["assumptions"] = db.assumptions_of(symbol)
    thesis["status_label"] = THESIS_LABEL.get(thesis["status"], thesis["status"])
    thesis["chain_name"] = (chains.chain(thesis.get("chain_id", "")) or {}).get("name", "")
    return thesis


def _alert_counts(symbol: str) -> int:
    today = _today().isoformat()
    n = 0
    for a in db.assumptions_of(symbol):
        if a["status"] == "invalidated":
            n += 1
        elif a["status"] in ("pending", "progress") and a["deadline"] and a["deadline"] < today:
            n += 1
    return n


def _stock_row(symbol: str) -> dict | None:
    m = store.stock_metrics(symbol)
    if not m:
        return None
    with db.db() as conn:
        thesis = db.get_thesis(conn, symbol)
    m["thesis_status"] = thesis["status"] if thesis else ""
    m["thesis_status_label"] = THESIS_LABEL.get(m["thesis_status"], "")
    m["assumption_alert"] = _alert_counts(symbol)
    return m


def _inbox(chain_id: str | None = None) -> list[dict]:
    dismissed = db.dismissed_keys()
    today = _today().isoformat()
    items: list[dict] = []
    for a in db.assumptions_of(chain_id=chain_id):
        due = a["deadline"] or ""
        if a["status"] == "invalidated":
            level, kind, msg = "high", "assumption", f"假设已证伪：{a['statement']}"
        elif a["status"] in ("pending", "progress") and due and due < today:
            level, kind, msg = "watch", "assumption", f"假设已过期未验证：{a['statement']}（{due}）"
        else:
            continue
        key = f"assumption-{a['id']}"
        if key in dismissed:
            continue
        items.append({"id": key, "symbol": a["symbol"], "name": chains.name_of(a["symbol"]),
                      "chain_id": a["chain_id"], "chain_name": (chains.chain(a["chain_id"]) or {}).get("name", ""),
                      "level": level, "kind": kind, "message": msg, "created_at": a["updated_at"]})
    scope = [chain_id] if chain_id else chains.chain_ids()
    # 估值极端只在"已建立逻辑/持仓"的标的上进收件箱，避免 100 只标的刷屏；全量极端仍在月度体检里
    active = {t["symbol"] for t in _all_theses()} | {p["symbol"] for p in db.list_positions()}
    for cid in scope:
        basis = chains.valuation_basis(cid)
        for sym in chains.symbols(cid):
            if sym not in active:
                continue
            m = store.stock_metrics(sym)
            if not m:
                continue
            pct = _pct_of(m, basis)
            if pct is None or not (pct >= 0.85 or pct <= 0.15):
                continue
            key = f"valuation-{sym}"
            if key in dismissed:
                continue
            items.append({"id": key, "symbol": sym, "name": m["name"],
                          "chain_id": cid, "chain_name": (chains.chain(cid) or {}).get("name", ""),
                          "level": "high" if pct >= 0.9 or pct <= 0.1 else "watch", "kind": "valuation",
                          "message": f"{BASIS_LABEL.get(basis, basis)} 近三年分位 {pct:.0%}，{'高位' if pct >= 0.5 else '低位'}",
                          "created_at": store.updated_at() or ""})
    order = {"high": 0, "watch": 1, "low": 2}
    return sorted(items, key=lambda x: (order.get(x["level"], 9), x["chain_id"], x["symbol"]))


def _q4_delta(chain_id: str, field: str) -> float | None:
    latest, prev = [], []
    for sym in chains.symbols(chain_id):
        df = store._fund.get(sym)
        if df is None or len(df) < 5:
            continue
        v0, v4 = df.iloc[-1][field], df.iloc[-5][field]
        if v0 == v0 and v4 == v4:
            latest.append(float(v0)); prev.append(float(v4))
    if not latest or not prev:
        return None
    return round(median(latest) - median(prev), 2)


def _reads(chain_id: str) -> list[dict]:
    stocks = store.chain_metrics(chain_id)
    basis = chains.valuation_basis(chain_id)
    pcts = [p for p in (_pct_of(s, basis) for s in stocks) if p is not None]
    bench = store.benchmark() or {}
    bench60 = bench.get("pct_60d")
    rel60 = None
    med60 = median([s["pct_60d"] for s in stocks])
    if med60 is not None and bench60 is not None:
        rel60 = round(med60 - bench60, 1)
    sc = store.scissors(chain_id)
    pct_med = median(pcts)
    gm_delta = _q4_delta(chain_id, "gross_margin")
    inv_delta = _q4_delta(chain_id, "inventory_days")
    pct_tone = "up" if pct_med is not None and pct_med <= 0.2 else "down" if pct_med is not None and pct_med >= 0.8 else ""
    return [
        {"label": f"{BASIS_LABEL.get(basis, basis)} 分位中位", "value": f"{pct_med:.0%}" if pct_med is not None else "—",
         "delta": None, "tone": pct_tone, "note": f"{len(stocks)} 只标的近三年{BASIS_LABEL.get(basis, basis)}分位"},
        {"label": "毛利率中位", "value": f"{median([s['gross_margin'] for s in stocks]) or 0:.1f}%",
         "delta": gm_delta, "tone": "up" if (gm_delta or 0) > 0 else "down" if (gm_delta or 0) < 0 else "",
         "note": "较 4 个季度前，成本与结构变化"},
        {"label": "库存周转天数", "value": f"{median([s['inventory_days'] for s in stocks]) or 0:.0f} 天",
         "delta": inv_delta, "tone": "up" if (inv_delta or 0) < 0 else "down" if (inv_delta or 0) > 0 else "",
         "note": "较 4 个季度前，渠道与排产温度"},
        {"label": sc["label"], "value": f"{sc['value']:+.1f}pp" if sc["value"] is not None else "—",
         "delta": sc["delta"], "tone": "", "note": sc["note"]},
        {"label": "20 日涨跌", "value": f"{sum(1 for s in stocks if (s['pct_20d'] or 0) > 0)} 涨 / "
                                         f"{sum(1 for s in stocks if (s['pct_20d'] or 0) < 0)} 跌",
         "delta": None, "tone": "", "note": "链内相对强弱"},
        {"label": "60 日相对沪深300", "value": f"{rel60:+.1f}pp" if rel60 is not None else "—",
         "delta": None, "tone": "up" if (rel60 or 0) > 0 else "down" if (rel60 or 0) < 0 else "",
         "note": "链中位收益 − 基准收益"},
    ]


def _stock_payload(symbol: str) -> dict:
    m = store.stock_metrics(symbol)
    if not m:
        raise HTTPException(404, f"没有 {symbol} 的数据")
    thesis = _thesis_with_assumptions(symbol)
    m["thesis_status"] = (thesis or {}).get("status", "")
    m["thesis_status_label"] = THESIS_LABEL.get(m["thesis_status"], "")
    m["valuation_basis"] = chains.valuation_basis(m["chain_id"])
    position = db.get_position(symbol)
    if position:
        position["pnl_pct"] = round((m["price"] / position["entry_price"] - 1) * 100, 2) if position["entry_price"] else None
    return {
        "stock": m,
        "price": store.price_series(symbol),
        "valuation": store.valuation_series(symbol),
        "financials": store.financials(symbol),
        "business": store.business_of(symbol),
        "thesis": thesis,
        "ranks": store.peer_ranks(m["chain_id"]).get(symbol, {}),
        "star": db.get_star(symbol) or {"symbol": symbol, "starred": 0, "investment_star": 0},
        "decisions": [{k: d[k] for k in ("id", "action", "price", "weight_pct", "logic", "kill_switch",
                                        "snapshot_hash", "created_at")} for d in db.list_decisions(symbol)],
        "position": position,
        "alerts": [i for i in _inbox(m["chain_id"]) if i["symbol"] == symbol],
    }


# --------------------------------------------------------------------------- meta / master
@app.get("/api/meta")
def get_meta() -> dict:
    chain_list = []
    for c in chains.chains():
        chain_list.append({
            "id": c["id"], "name": c["name"], "short": c.get("short", ""),
            "description": c.get("description", ""), "valuation_basis": c.get("valuation_basis", "pe"),
            "valuation_label": BASIS_LABEL.get(c.get("valuation_basis", "pe"), "PE"),
            "stocks": len(c["instruments"]), "nodes": len(c["nodes"]), "kpis": c.get("kpis", []),
        })
    return {
        "chains": chain_list,
        "as_of": store.as_of(),
        "updated_at": store.updated_at(),
        "counts": {"chains": len(chain_list), "stocks": len(chains.all_symbols()),
                   "positions": len(db.list_positions()), "alerts": len(_inbox())},
        "benchmark": store.benchmark(),
    }


@app.get("/api/master")
def get_master() -> dict:
    hit = cache.get("master")
    if hit is not None:
        return hit
    aggregates = store.all_chain_aggregates()
    positions = db.list_positions()
    alloc: dict[str, float] = {}
    pos_rows = []
    total_weight = 0.0
    weighted_pnl = 0.0
    for p in positions:
        m = store.stock_metrics(p["symbol"]) or {}
        cid = p.get("chain_id", "")
        name = (chains.chain(cid) or {}).get("name", cid)
        pnl = round((m.get("price", 0) / p["entry_price"] - 1) * 100, 2) if p.get("entry_price") else None
        total_weight += float(p["weight_pct"])
        weighted_pnl += (pnl or 0) * float(p["weight_pct"])
        alloc[cid] = round(alloc.get(cid, 0) + float(p["weight_pct"]), 2)
        pos_rows.append({"symbol": p["symbol"], "name": m.get("name", p["symbol"]),
                         "chain_id": cid, "chain_name": name, "weight_pct": p["weight_pct"],
                         "entry_price": p["entry_price"], "price": m.get("price"), "pnl_pct": pnl,
                         "opened_at": p["opened_at"]})
    for agg in aggregates:
        agg["holdings_weight"] = alloc.get(agg["id"], 0)
        agg["theses"] = sum(1 for t in _all_theses() if t["chain_id"] == agg["id"])
        agg["alerts"] = len([i for i in _inbox(agg["id"])])
    upcoming = []
    today = _today()
    for a in db.assumptions_of():
        if not a["deadline"] or a["status"] in ("met", "invalidated"):
            continue
        try:
            due = date.fromisoformat(a["deadline"])
        except ValueError:
            continue
        days_left = (due - today).days
        if days_left <= 30:
            upcoming.append({"symbol": a["symbol"], "name": chains.name_of(a["symbol"]),
                             "chain_id": a["chain_id"], "statement": a["statement"],
                             "deadline": a["deadline"], "days_left": days_left})
    upcoming.sort(key=lambda x: x["days_left"])
    inbox = _inbox()
    payload = {
        "as_of": store.as_of(),
        "benchmark": store.benchmark(),
        "summary": {"chains": len(aggregates), "stocks": len(chains.all_symbols()),
                    "positions": len(positions), "total_weight": round(total_weight, 1),
                    "weighted_pnl": round(weighted_pnl / total_weight, 2) if total_weight else 0,
                    "theses": len(_all_theses()), "alerts": len(inbox),
                    "high_alerts": sum(1 for i in inbox if i["level"] == "high")},
        "chains": aggregates,
        "positions": pos_rows,
        "allocation": [{"chain_id": k, "name": (chains.chain(k) or {}).get("name", k), "weight": v}
                       for k, v in sorted(alloc.items(), key=lambda x: -x[1])],
        "inbox": inbox[:12],
        "upcoming": upcoming[:8],
        "decisions": [{k: d[k] for k in ("id", "symbol", "chain_id", "action", "logic", "created_at")}
                      for d in db.list_decisions()[:8]],
    }
    cache.put("master", payload)
    return payload


def _all_theses() -> list[dict]:
    with db.db() as conn:
        rows = db.rows(conn.execute("SELECT * FROM theses"))
    return rows


# --------------------------------------------------------------------------- chain overview
@app.get("/api/overview")
def get_overview(chain: str = Query("whites")) -> dict:
    _chain_or_404(chain)
    key = f"overview:{chain}"
    hit = cache.get(key)
    if hit is not None:
        return hit
    stocks = [r for r in (_stock_row(s) for s in chains.symbols(chain)) if r]
    ranks = store.peer_ranks(chain)
    star_map = {r["symbol"]: r for r in db.list_stars()}
    for r in stocks:
        r["ranks"] = ranks.get(r["symbol"], {})
        r["star"] = star_map.get(r["symbol"]) or {"starred": 0, "investment_star": 0}
    agg = store.chain_aggregate(chain)
    basis = agg["valuation_basis"]
    pcts = [p for p in (_pct_of(s, basis) for s in stocks) if p is not None]
    payload = {
        "as_of": store.as_of(),
        "chain": {**agg, "node_list": chains.nodes(chain), "valuation_label": BASIS_LABEL.get(basis, "PE")},
        "benchmark": store.benchmark(),
        "breadth": {"up_20d": agg["up_20d"], "down_20d": agg["down_20d"],
                    "median_pct": agg["median_pct"]},
        "nodes": store.node_aggregates(chain),
        "scissors": store.scissors(chain),
        "proxies": store.proxies(chain),
        "distribution": store.node_valuation_distribution(chain),
        "reads": _reads(chain),
        "stocks": stocks,
    }
    cache.put(key, payload)
    return payload


# --------------------------------------------------------------------------- stock
@app.get("/api/stock/{symbol}")
def get_stock(symbol: str) -> dict:
    if symbol not in set(chains.all_symbols()):
        raise HTTPException(404, "标的池中没有该代码")
    key = f"stock:{symbol}"
    hit = cache.get(key)
    if hit is not None:
        return hit
    payload = _stock_payload(symbol)
    cache.put(key, payload)
    return payload


def _max_node_size() -> int:
    sizes = []
    for c in chains.chains():
        for n in c.get("nodes", []):
            sizes.append(sum(1 for i in c.get("instruments", []) if i.get("node_id") == n["id"]))
    return max(sizes) if sizes else 6


@app.get("/api/universe")
def get_universe() -> dict:
    out = []
    for c in chains.chains():
        nodes = []
        for n in c.get("nodes", []):
            members = [{"symbol": i["symbol"], "name": i.get("name", i["symbol"]), "role": i.get("role", "")}
                       for i in c.get("instruments", []) if i.get("node_id") == n["id"]]
            nodes.append({"id": n["id"], "name": n.get("name", n["id"]), "instruments": members})
        out.append({"id": c["id"], "name": c.get("name", c["id"]), "short": c.get("short", ""), "nodes": nodes})
    return {"chains": out, "count": len(chains.all_symbols()), "max_node_size": _max_node_size()}


# --------------------------------------------------------------------------- compare
@app.get("/api/compare")
def get_compare(symbols: str = Query(""), points: int = Query(760, ge=60, le=1500)) -> dict:
    raw = [s.strip() for s in symbols.split(",") if s.strip()]
    uniq = list(dict.fromkeys(raw))
    if len(uniq) < 2:
        raise HTTPException(400, "至少选择 2 只标的")
    max_select = _max_node_size()
    if len(uniq) > max_select:
        raise HTTPException(400, f"最多对比 {max_select} 只标的（按最大节点股票数）")
    unknown = [s for s in uniq if s not in set(chains.all_symbols())]
    if unknown:
        raise HTTPException(404, f"标的池中没有：{', '.join(unknown)}")

    metrics = []
    for sym in uniq:
        m = store.stock_metrics(sym)
        if m:
            metrics.append(m)
    if len(metrics) != len(uniq):
        raise HTTPException(404, "部分标的没有数据")
    chain_ids = {m["chain_id"] for m in metrics}
    node_ids = {m["node_id"] for m in metrics}
    if len(chain_ids) != 1 or len(node_ids) != 1:
        raise HTTPException(400, "多股对比只支持同一产业链、同一节点内的标的")

    price_map = {}
    for sym in uniq:
        rows = store.price_series(sym, points)
        if rows:
            price_map[sym] = {r["date"]: r["close"] for r in rows}
    common = sorted(set.intersection(*(set(v) for v in price_map.values()))) if price_map else []
    if len(common) < 2:
        raise HTTPException(400, "没有足够的共同交易日")

    bases = {sym: price_map[sym][common[0]] for sym in price_map}
    series = []
    for sym in uniq:
        if sym not in price_map:
            continue
        for d in common:
            base = bases[sym]
            series.append({"symbol": sym, "date": d,
                           "value": round(price_map[sym][d] / base * 100, 2) if base else None})

    stocks = []
    for m in metrics:
        sym = m["symbol"]
        m["valuation_basis"] = chains.valuation_basis(m["chain_id"])
        m["valuation_pct"] = m["pb_pct_3y"] if m["valuation_basis"] == "pb" else m["pe_pct_3y"]
        m["ranks"] = store.peer_ranks(m["chain_id"]).get(sym, {})
        stocks.append({k: m.get(k) for k in (
            "symbol", "name", "chain_id", "chain_name", "node_id", "node_name", "valuation_basis",
            "price", "pct_20d", "pct_60d", "valuation_pct",
            "pe_ttm", "pe_pct_3y", "pb", "pb_pct_3y", "gross_margin", "revenue_yoy", "profit_yoy",
            "single_q_rev_yoy", "single_q_profit_yoy", "inventory_days", "receivable_days", "ccc",
            "roe", "roic", "total_mv", "ps_ttm", "dividend_yield", "forward_pe", "fcf_yield",
            "ev_ebitda", "net_debt_ratio", "cash_to_short_debt", "overseas", "ranks",
        )})
    chain_id = metrics[0]["chain_id"]
    node_id = metrics[0]["node_id"]
    chain_info = chains.chain(chain_id) or {}
    node_info = next((n for n in chain_info.get("nodes", []) if n["id"] == node_id), {})
    return {"as_of": store.as_of(), "symbols": uniq, "stocks": stocks, "series": series,
            "chain": {"id": chain_id, "name": chain_info.get("name", chain_id)},
            "node": {"id": node_id, "name": node_info.get("name", node_id)},
            "max_selectable": max_select}


# --------------------------------------------------------------------------- stars / invest
def _star_payload(symbol: str) -> dict:
    m = store.stock_metrics(symbol) or {}
    star = db.get_star(symbol) or {
        "symbol": symbol, "starred": 0, "starred_at": None, "logic_note": "",
        "logic_date": None, "logic_updated_at": None, "investment_star": 0,
        "investment_star_at": None, "decision_date": None, "decision_price": None, "decision_id": None,
    }
    return {
        "star": star,
        "stock": {
            "symbol": symbol, "name": m.get("name", chains.name_of(symbol)),
            "chain_id": m.get("chain_id", ""), "chain_name": m.get("chain_name", ""),
            "node_name": m.get("node_name", ""), "price": m.get("price"),
            "pct_20d": m.get("pct_20d"), "pct_60d": m.get("pct_60d"),
            "pe_pct_3y": m.get("pe_pct_3y"), "pb_pct_3y": m.get("pb_pct_3y"),
            "gross_margin": m.get("gross_margin"), "revenue_yoy": m.get("revenue_yoy"),
        },
        "note_history": db.star_note_history(symbol)[:8],
    }


@app.get("/api/stars")
def get_stars() -> dict:
    rows = db.list_stars()
    starred = [_star_payload(r["symbol"]) for r in rows if r["starred"]]
    archived = [_star_payload(r["symbol"]) for r in rows if not r["starred"] and (r["logic_note"] or "").strip()]
    return {"stars": starred, "archived": archived}


@app.post("/api/star")
async def post_star(request: Request) -> dict:
    body = await request.json()
    symbol = body.get("symbol")
    if symbol not in set(chains.all_symbols()):
        raise HTTPException(404, "标的池中没有该代码")
    try:
        star = db.set_star(symbol, bool(body.get("active")))
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    cache.clear()
    return {"ok": True, "star": star}


@app.post("/api/star/note")
async def post_star_note(request: Request) -> dict:
    body = await request.json()
    symbol = body.get("symbol")
    if symbol not in set(chains.all_symbols()):
        raise HTTPException(404, "标的池中没有该代码")
    try:
        star = db.save_star_logic(symbol, str(body.get("note") or ""))
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    cache.clear()
    return {"ok": True, "star": star}


@app.delete("/api/star/note")
def delete_star_note(symbol: str = Query("")) -> dict:
    if symbol not in set(chains.all_symbols()):
        raise HTTPException(404, "标的池中没有该代码")
    try:
        star = db.save_star_logic(symbol, "")
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    cache.clear()
    return {"ok": True, "star": star}


@app.post("/api/star/invest")
async def post_star_invest(request: Request) -> dict:
    body = await request.json()
    symbol = body.get("symbol")
    if symbol not in set(chains.all_symbols()):
        raise HTTPException(404, "标的池中没有该代码")
    try:
        star = db.set_investment_star(symbol, bool(body.get("active")))
    except ValueError as exc:
        raise HTTPException(409, str(exc))
    cache.clear()
    return {"ok": True, "star": star}


@app.post("/api/invest/decision")
async def post_invest_decision(request: Request) -> dict:
    body = await request.json()
    symbol = body.get("symbol")
    cid = chains.chain_of(symbol or "")
    if not cid:
        raise HTTPException(400, "标的池中没有该代码")
    star = db.get_star(symbol)
    if not star or not star["investment_star"]:
        raise HTTPException(409, "先投资加星，才能记录投资决策")
    date_text = str(body.get("date") or _today().isoformat())
    try:
        date.fromisoformat(date_text)
    except ValueError:
        raise HTTPException(400, "日期格式应为 YYYY-MM-DD")
    m = store.stock_metrics(symbol)
    if not m:
        raise HTTPException(400, "该标的没有行情数据")
    price = float(body.get("price") or m["price"])
    if price <= 0:
        raise HTTPException(400, "成交价必须大于 0")
    action = body.get("action") or "buy"
    if action not in ACTION_LABEL:
        raise HTTPException(400, "决策类型非法")
    basis = chains.valuation_basis(cid)
    pct = _pct_of(m, basis)
    snapshot = {
        "at": f"{date_text}T00:00:00+08:00", "symbol": symbol, "name": m["name"], "chain_id": cid,
        "chain_name": (chains.chain(cid) or {}).get("name", ""), "action": action,
        "action_label": ACTION_LABEL[action], "price": price,
        "weight_pct": body.get("weight_pct") or 0, "logic": body.get("logic", ""),
        "kill_switch": body.get("kill_switch", ""), "trade_date": date_text,
        "valuation": {"basis": basis, "pct": pct, "pe_ttm": m["pe_ttm"], "pb": m["pb"]},
        "financials": {"gross_margin": m["gross_margin"], "revenue_yoy": m["revenue_yoy"],
                       "profit_yoy": m["profit_yoy"], "inventory_days": m["inventory_days"]},
        "market": {"pct_20d": m["pct_20d"], "pct_60d": m["pct_60d"]},
    }
    d = db.add_decision({**body, "symbol": symbol, "chain_id": cid, "action": action,
                         "price": price, "trade_date": date_text}, snapshot)
    new_star = db.set_star_decision(symbol, date_text, price, d["id"])
    cache.clear()
    return {"ok": True, "decision": {k: d[k] for k in ("id", "action", "trade_date", "created_at")},
            "star": new_star}


# --------------------------------------------------------------------------- writes
@app.post("/api/thesis")
async def post_thesis(request: Request) -> dict:
    body = await request.json()
    symbol = body.get("symbol")
    cid = chains.chain_of(symbol or "")
    if not cid:
        raise HTTPException(400, "标的池中没有该代码")
    if body.get("status") and body["status"] not in THESIS_LABEL:
        raise HTTPException(400, "状态非法")
    thesis = db.upsert_thesis({**body, "symbol": symbol, "chain_id": cid})
    thesis["assumptions"] = db.assumptions_of(symbol)
    thesis["status_label"] = THESIS_LABEL.get(thesis["status"], thesis["status"])
    cache.clear()
    return {"ok": True, "thesis": thesis}


@app.post("/api/assumption")
async def post_assumption(request: Request) -> dict:
    body = await request.json()
    symbol = body.get("symbol")
    cid = chains.chain_of(symbol or "")
    if not cid:
        raise HTTPException(400, "标的池中没有该代码")
    if not (body.get("statement") or "").strip():
        raise HTTPException(400, "假设内容不能为空")
    with db.db() as conn:
        existing = db.get_thesis(conn, symbol)
    if not existing:
        db.upsert_thesis({"symbol": symbol, "chain_id": cid, "status": "watch"})
    item = db.add_assumption({**body, "symbol": symbol, "chain_id": cid})
    cache.clear()
    return {"ok": True, "assumption": item}


@app.patch("/api/assumption/{assumption_id}")
async def patch_assumption(assumption_id: int, request: Request) -> dict:
    body = await request.json()
    if body.get("status") and body["status"] not in STATUS_LABEL:
        raise HTTPException(400, "假设状态非法")
    if not db.update_assumption(assumption_id, body):
        raise HTTPException(404, "假设不存在或没有可更新字段")
    cache.clear()
    return {"ok": True}


@app.post("/api/decision")
async def post_decision(request: Request) -> dict:
    body = await request.json()
    symbol = body.get("symbol")
    action = body.get("action")
    cid = chains.chain_of(symbol or "")
    if not cid:
        raise HTTPException(400, "标的池中没有该代码")
    if action not in ACTION_LABEL:
        raise HTTPException(400, "决策类型非法")
    m = store.stock_metrics(symbol)
    if not m:
        raise HTTPException(400, "该标的没有行情数据")
    basis = chains.valuation_basis(cid)
    pct = _pct_of(m, basis)
    snapshot = {
        "at": db.now(), "symbol": symbol, "name": m["name"], "chain_id": cid,
        "chain_name": (chains.chain(cid) or {}).get("name", ""), "action": action,
        "action_label": ACTION_LABEL[action], "price": body.get("price") or m["price"],
        "weight_pct": body.get("weight_pct") or 0, "logic": body.get("logic", ""),
        "kill_switch": body.get("kill_switch", ""),
        "valuation": {"basis": basis, "pct": pct, "pe_ttm": m["pe_ttm"], "pb": m["pb"]},
        "financials": {"gross_margin": m["gross_margin"], "revenue_yoy": m["revenue_yoy"],
                       "profit_yoy": m["profit_yoy"], "inventory_days": m["inventory_days"]},
        "market": {"pct_20d": m["pct_20d"], "pct_60d": m["pct_60d"]},
    }
    d = db.add_decision({**body, "symbol": symbol, "chain_id": cid, "action": action}, snapshot)
    existing_star = db.get_star(symbol)
    if existing_star and existing_star["investment_star"]:
        db.set_star_decision(symbol, body.get("trade_date") or _today().isoformat(),
                             float(body.get("price") or m["price"]), d["id"])
    cache.clear()
    return {"ok": True, "decision": {k: d[k] for k in ("id", "action", "snapshot_hash", "created_at")}}


# --------------------------------------------------------------------------- review
def _review_payload(month: str, chain_id: str = "", scope: str = "wide") -> dict:
    scope = scope if scope in ("wide", "narrow") else "wide"
    scope_chains = [chain_id] if chain_id else chains.chain_ids()
    positions_all = db.list_positions(chain_id or None)
    star_rows = db.list_stars()
    starred = {r["symbol"] for r in star_rows if r["starred"]}
    invested = {r["symbol"] for r in star_rows if r["investment_star"]}
    invested |= {p["symbol"] for p in positions_all}
    scope_symbols = set(chains.symbols(chain_id)) if chain_id else set(chains.all_symbols())
    starred &= scope_symbols
    invested &= scope_symbols
    selected = invested if scope == "narrow" else (starred | invested)
    positions = [p for p in positions_all if p["symbol"] in selected]

    def stage(symbol: str) -> str:
        return "invest" if symbol in invested else "watch"

    alloc: dict[str, float] = {}
    pos_rows = []
    total_pnl = 0.0
    total_weight = 0.0
    for p in positions:
        m = store.stock_metrics(p["symbol"]) or {}
        cid = p.get("chain_id", "")
        alloc[cid] = round(alloc.get(cid, 0) + float(p["weight_pct"]), 2)
        pnl = round((m.get("price", 0) / p["entry_price"] - 1) * 100, 2) if p.get("entry_price") else None
        total_weight += float(p["weight_pct"])
        total_pnl += (pnl or 0) * float(p["weight_pct"])
        pos_rows.append({"symbol": p["symbol"], "name": chains.name_of(p["symbol"]), "weight_pct": p["weight_pct"],
                         "entry_price": p["entry_price"], "price": m.get("price"), "pnl_pct": pnl,
                         "opened_at": p["opened_at"], "stage": "invest"})

    board = []
    for cid in scope_chains:
        for sym in chains.symbols(cid):
            if sym not in selected:
                continue
            thesis = _thesis_with_assumptions(sym)
            if not thesis:
                continue
            board.append({"symbol": sym, "name": chains.name_of(sym), "chain_id": cid,
                          "chain_name": (chains.chain(cid) or {}).get("name", ""),
                          "stage": stage(sym), "starred": sym in starred,
                          "investment_star": sym in invested,
                          "thesis_status": thesis["status"], "thesis_status_label": thesis["status_label"],
                          "title": thesis["title"],
                          "assumptions": [{"id": a["id"], "statement": a["statement"], "status": a["status"],
                                           "status_label": STATUS_LABEL.get(a["status"], a["status"]),
                                           "deadline": a["deadline"], "target": a["target"]}
                                          for a in thesis["assumptions"]]})

    flags = []
    for cid in scope_chains:
        basis = chains.valuation_basis(cid)
        for sym in chains.symbols(cid):
            if sym not in selected:
                continue
            m = store.stock_metrics(sym)
            pct = _pct_of(m, basis) if m else None
            if pct is not None and (pct >= 0.8 or pct <= 0.2):
                flags.append({"symbol": sym, "name": m["name"], "chain_id": cid,
                              "chain_name": (chains.chain(cid) or {}).get("name", ""),
                              "stage": stage(sym), "pct": pct, "side": "high" if pct >= 0.5 else "low",
                              "basis": basis})
    flags.sort(key=lambda x: x["pct"], reverse=True)
    total_high = sum(1 for f in flags if f["side"] == "high")
    total_low = sum(1 for f in flags if f["side"] == "low")
    high = [f for f in flags if f["side"] == "high"][:8]
    low = [f for f in flags if f["side"] == "low"][-8:]
    flags = high + low
    flag_totals = {"high": total_high, "low": total_low}

    today = _today()
    deadlines = []
    for a in db.assumptions_of(chain_id=chain_id or None):
        if a["symbol"] not in selected:
            continue
        if not a["deadline"] or a["status"] in ("met", "invalidated"):
            continue
        try:
            due = date.fromisoformat(a["deadline"])
        except ValueError:
            continue
        days_left = (due - today).days
        if days_left <= 45:
            deadlines.append({"symbol": a["symbol"], "name": chains.name_of(a["symbol"]),
                              "chain_id": a["chain_id"], "stage": stage(a["symbol"]),
                              "statement": a["statement"], "deadline": a["deadline"], "days_left": days_left})
    deadlines.sort(key=lambda x: x["days_left"])

    decisions = [{k: d[k] for k in ("id", "symbol", "chain_id", "action", "logic", "created_at")}
                 for d in db.list_decisions(month=month, chain_id=chain_id or None)
                 if d["symbol"] in selected]
    star_by_symbol = {r["symbol"]: r for r in star_rows}
    watchlist = []
    for sym in sorted(selected):
        m = store.stock_metrics(sym) or {}
        row = star_by_symbol.get(sym) or {}
        watchlist.append({
            "symbol": sym, "name": m.get("name", chains.name_of(sym)),
            "chain_id": m.get("chain_id", ""), "chain_name": m.get("chain_name", ""),
            "node_name": m.get("node_name", ""), "stage": stage(sym),
            "price": m.get("price"), "pct_20d": m.get("pct_20d"), "pct_60d": m.get("pct_60d"),
            "note": row.get("logic_note", ""), "starred_at": row.get("starred_at"),
            "investment_star": bool(row.get("investment_star")),
        })
    stored = db.get_review(month, chain_id)
    return {
        "month": month, "chain_id": chain_id, "scope": scope,
        "chain_name": (chains.chain(chain_id) or {}).get("name", "全部产业链") if chain_id else "全部产业链",
        "summary": {"positions": len(positions), "total_weight": round(total_weight, 1),
                    "weighted_pnl": round(total_pnl / total_weight, 2) if total_weight else 0,
                    "theses": len(board), "stars": len(selected),
                    "invest": len(invested), "watch": len(selected - invested)},
        "symbols": sorted(selected),
        "watchlist": watchlist,
        "positions": pos_rows,
        "allocation": [{"chain_id": k, "name": (chains.chain(k) or {}).get("name", k), "weight": v}
                       for k, v in sorted(alloc.items(), key=lambda x: -x[1])],
        "board": board,
        "valuation_flags": flags,
        "valuation_flag_totals": flag_totals,
        "deadlines": deadlines,
        "decisions": decisions,
        "review_md": (stored or {}).get("content_md", "") if stored else "",
    }


@app.get("/api/review")
def get_review(month: str = Query(""), chain: str = Query(""), scope: str = Query("wide")) -> dict:
    month = month or _today().strftime("%Y-%m")
    _valid_month(month)
    if chain:
        _chain_or_404(chain)
    if scope not in ("wide", "narrow"):
        raise HTTPException(400, "scope 只能是 wide 或 narrow")
    key = f"review:{month}:{chain}:{scope}"
    hit = cache.get(key)
    if hit is not None:
        return hit
    payload = _review_payload(month, chain, scope)
    cache.put(key, payload)
    return payload


@app.post("/api/review")
async def post_review(request: Request) -> dict:
    body = await request.json()
    month = body.get("month") or _today().strftime("%Y-%m")
    _valid_month(month)
    chain_id = body.get("chain_id") or ""
    if chain_id:
        _chain_or_404(chain_id)
    db.upsert_review(month, str(body.get("content_md") or ""), chain_id)
    cache.clear()
    return {"ok": True}


@app.get("/api/export/review")
def export_review(month: str = Query(""), chain: str = Query(""), scope: str = Query("wide")) -> Response:
    month = month or _today().strftime("%Y-%m")
    _valid_month(month)
    p = _review_payload(month, chain, scope)
    if p["review_md"].strip():
        md = p["review_md"]
    else:
        title = f"{month} 月度复盘 · {p['chain_name']}"
        lines = [f"# {title}", "", f"数据截至：{store.as_of()}", "",
                 "## 组合", f"- 持仓 {p['summary']['positions']} 只，总仓位 {p['summary']['total_weight']}%，"
                           f"加权浮动盈亏 {p['summary']['weighted_pnl']}%", ""]
        for row in p["positions"]:
            lines.append(f"- {row['name']}（{row['symbol']}）仓位 {row['weight_pct']}%，成本 {row['entry_price']}，"
                         f"现价 {row['price']}，浮动 {row['pnl_pct']}%")
        lines += ["", "## 逻辑与假设"]
        for b in p["board"]:
            lines.append(f"### {b['name']}（{b['symbol']}）· {b['chain_name']} · {b['thesis_status_label']}")
            if b["title"]:
                lines.append(b["title"])
            for a in b["assumptions"]:
                lines.append(f"- [{a['status_label']}] {a['statement']}（目标 {a['target'] or '—'}，"
                             f"截止 {a['deadline'] or '—'}）")
        lines += ["", "## 估值极端"]
        for f in p["valuation_flags"]:
            lines.append(f"- {f['name']}（{f['symbol']}）{f['chain_name']} "
                         f"{BASIS_LABEL.get(f['basis'], f['basis'])} 分位 {f['pct']:.0%}，"
                         f"{'高位' if f['side'] == 'high' else '低位'}")
        lines += ["", "## 待验证（45 天内）"]
        for d in p["deadlines"]:
            lines.append(f"- {d['name']}（{d['chain_name']}）：{d['statement']}（截止 {d['deadline']}，剩 {d['days_left']} 天）")
        lines += ["", "## 本月决策"]
        for d in p["decisions"]:
            lines.append(f"- {d['created_at'][:10]} {chains.name_of(d['symbol'])} "
                         f"{ACTION_LABEL.get(d['action'], d['action'])}：{d['logic']}")
        md = "\n".join(lines)
    name = f"review-{month}{'-' + chain if chain else ''}.md"
    return Response(content=md, media_type="text/markdown",
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


# --------------------------------------------------------------------------- inbox / health
@app.get("/api/inbox")
def get_inbox(chain: str = Query("")) -> list[dict]:
    if chain:
        _chain_or_404(chain)
    return _inbox(chain or None)


@app.post("/api/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: str) -> dict:
    db.dismiss_alert(alert_id)
    cache.clear()
    return {"ok": True}


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "data_ok": store.ok, "as_of": store.as_of()}


@app.post("/api/warm")
def warm_cache(full: bool = Query(False)) -> dict:
    def run() -> None:
        try:
            get_master()
            for c in chains.chain_ids():
                get_overview(c)
            if full:
                month = _today().strftime("%Y-%m")
                review_key = f"review:{month}:"
                if cache.get(review_key) is None:
                    cache.put(review_key, _review_payload(month, ""))
                for sym in chains.all_symbols():
                    try:
                        key = f"stock:{sym}"
                        if cache.get(key) is None:
                            cache.put(key, _stock_payload(sym))
                    except Exception as exc:  # noqa: BLE001
                        print(f"[warm] {sym} failed: {type(exc).__name__}: {exc}", flush=True)
        except Exception as exc:  # noqa: BLE001
            print(f"[warm] failed: {type(exc).__name__}: {exc}", flush=True)

    Thread(target=run, daemon=True).start()
    return {"ok": True, "warming": True, "full": full}


@app.post("/api/reload")
def reload_data() -> dict:
    store.reload()
    cache.clear()
    return {"ok": True, "as_of": store.as_of(), "data_ok": store.ok}


if (settings.WEB_DIR / "index.html").exists():
    app.mount("/", StaticFiles(directory=str(settings.WEB_DIR), html=True), name="web")
