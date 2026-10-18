"""v3 前端联调用的本地 mock 后端（端口 8200）。

- 读取 `config/chains.json`：5 条产业链 × 20 只 = 100 只，节点/角色/估值口径以配置为准。
- 静态托管 `web/`，提供 V3_API 全部端点（meta / master / overview / stock / review / export / inbox）。
- 所有写操作只改进程内状态，重启即复位；不落盘、不碰 data/。

运行：
    .venv\\Scripts\\python.exe tools\\mock_v2.py
    # 或  .venv\\Scripts\\python.exe -m uvicorn tools.mock_v2:app --port 8200
"""
from __future__ import annotations

import hashlib
import json
import math
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from fastapi import FastAPI, HTTPException, Request  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.responses import JSONResponse, PlainTextResponse  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402

# --------------------------------------------------------------------------
# 配置
# --------------------------------------------------------------------------

AS_OF = date(2026, 10, 16)
UPDATED_AT = datetime(2026, 10, 18, 15, 30, 0)
HISTORY_DAYS = 750

BENCHMARK = {
    "symbol": "000300.SH",
    "name": "沪深300",
    "close": 4170.61,
    "pct_20d": -8.31,
    "pct_60d": -3.20,
}

CONFIG = json.loads((ROOT / "config" / "chains.json").read_text(encoding="utf-8"))
CHAINS: list[dict] = CONFIG["chains"]
CHAIN_BY_ID = {c["id"]: c for c in CHAINS}
CHAIN_ORDER = {c["id"]: i for i, c in enumerate(CHAINS)}

# 每条链的样例画像参数：中位分位目标、20/60 日基准涨跌、毛利/库存/估值区间
CHAIN_PARAMS = {
    "whites": dict(median=0.46, bias20=-4.0, bias60=-7.0, gm=(16, 54), inv=(45, 100),
                   pe=(9, 32), pb=(1.2, 4.6), rev=(-12, 18), price=(6, 110)),
    "pv": dict(median=0.72, bias20=3.5, bias60=12.0, gm=(8, 34), inv=(50, 130),
               pe=(8, 30), pb=(0.9, 4.8), rev=(-28, 30), price=(4, 90)),
    "auto": dict(median=0.55, bias20=0.5, bias60=3.0, gm=(10, 30), inv=(40, 100),
                 pe=(10, 45), pb=(1.2, 6.0), rev=(-15, 35), price=(5, 260)),
    "copper": dict(median=0.31, bias20=1.5, bias60=8.0, gm=(4, 22), inv=(40, 110),
                   pe=(8, 30), pb=(0.8, 4.2), rev=(-15, 25), price=(3, 45)),
    "tourism": dict(median=0.62, bias20=-3.0, bias60=-5.0, gm=(20, 88), inv=(10, 60),
                    pe=(12, 55), pb=(1.5, 7.0), rev=(-20, 38), price=(4, 120)),
}

ROLE_CN = {"upstream": "上游", "midstream": "中游", "downstream": "下游"}
STATUS_CN = {"watch": "观察", "building": "分批建仓", "holding": "持有", "reduced": "已减仓", "closed": "已结案"}
ASSUMPTION_STATUS = ("pending", "progress", "met", "invalidated")
ACTION_CN = {"watch": "观察", "buy": "建仓", "add": "加仓", "reduce": "减仓", "exit": "结案"}

INSTRUMENTS: list[dict] = []
for chain in CHAINS:
    for inst in chain["instruments"]:
        INSTRUMENTS.append({
            **inst,
            "chain_id": chain["id"],
            "chain_name": chain["name"],
            "chain_short": chain["short"],
            "valuation_basis": chain["valuation_basis"],
            "valuation_label": "PE" if chain["valuation_basis"] == "pe" else "PB",
        })
INST_BY_SYMBOL = {i["symbol"]: i for i in INSTRUMENTS}
NODES_BY_CHAIN = {c["id"]: sorted(c["nodes"], key=lambda n: n.get("sort", 0)) for c in CHAINS}


# --------------------------------------------------------------------------
# 确定性序列
# --------------------------------------------------------------------------

def _rng(*parts: str) -> random.Random:
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()
    return random.Random(int(digest[:16], 16))


def _business_days(count: int, end: date) -> list[date]:
    out: list[date] = []
    d = end
    while len(out) < count:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return list(reversed(out))


DATES = _business_days(HISTORY_DAYS, AS_OF)
QUARTERS = ["2024-03-31", "2024-06-30", "2024-09-30", "2024-12-31",
            "2025-03-31", "2025-06-30", "2025-09-30", "2025-12-31",
            "2026-03-31", "2026-06-30"]


def _round(x: float, nd: int = 2) -> float:
    return round(float(x), nd)


def _median(xs: list[float]) -> float:
    vals = sorted(x for x in xs if x is not None)
    if not vals:
        return 0.0
    mid = len(vals) // 2
    return vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2


def _pct_targets(chain_id: str) -> list[float]:
    """每条链 20 个“目标分位”：围绕链中位数展开，保留 3 高 / 3 低极端。"""
    rnd = _rng("pct-targets", chain_id)
    median = CHAIN_PARAMS[chain_id]["median"]
    spread = [median + (-0.16 + 0.32 * i / 15.0) for i in range(16)]
    spread = [min(0.93, max(0.07, v)) for v in spread]
    vals = spread + [
        rnd.uniform(0.84, 0.95), rnd.uniform(0.05, 0.14),
        rnd.uniform(0.82, 0.93), rnd.uniform(0.06, 0.16),
    ]
    rnd.shuffle(vals)
    return vals


PCT_TARGETS = {c["id"]: _pct_targets(c["id"]) for c in CHAINS}


# --------------------------------------------------------------------------
# 画像与序列
# --------------------------------------------------------------------------

def _profile(inst: dict, idx: int) -> dict:
    chain = inst["chain_id"]
    p = CHAIN_PARAMS[chain]
    rnd = _rng("profile", chain, inst["symbol"])
    price = _round(rnd.uniform(*p["price"]), 2)
    pe_center = _round(rnd.uniform(*p["pe"]), 1)
    pb_center = _round(rnd.uniform(*p["pb"]), 2)
    gm = _round(rnd.uniform(*p["gm"]), 1)
    nm = _round(gm * rnd.uniform(0.16, 0.42), 1)
    roe = _round(rnd.uniform(3, 26), 1)
    rev = _round(rnd.uniform(*p["rev"]), 1)
    profit = _round(rev + rnd.uniform(-12, 12), 1)
    inv = _round(rnd.uniform(*p["inv"]), 1)
    return dict(price=price, pe_center=pe_center, pb_center=pb_center,
                gross_margin=gm, net_margin=max(0.2, nm), roe=roe,
                revenue_yoy=rev, profit_yoy=profit, inventory_days=inv,
                pct_target=PCT_TARGETS[chain][idx],
                score=_round(rnd.uniform(40, 82), 1),
                attention=_round(rnd.uniform(30, 78), 1),
                institution=_round(rnd.uniform(0.05, 0.45), 2))


def _price_series(inst: dict, profile: dict) -> list[float]:
    chain = inst["chain_id"]
    p = CHAIN_PARAMS[chain]
    rnd = _rng("price", chain, inst["symbol"])
    n = HISTORY_DAYS
    rets = [rnd.gauss(0.0002, 0.017) for _ in range(n - 1)]
    target20 = p["bias20"] + rnd.uniform(-8.0, 8.0)
    target60 = p["bias60"] + rnd.uniform(-10.0, 10.0)
    L20 = math.log(1.0 + target20 / 100.0)
    L60 = math.log(1.0 + target60 / 100.0)
    # 先校最近 40 日让 60 日累计 = L60（扣除最后 20 日），再精确校最后 20 日，
    # 两步互不影响，20/60 日涨跌与设定完全一致。
    delta60 = (L60 - L20) - sum(rets[-60:-20])
    rets[-60:-20] = [x + delta60 / 40.0 for x in rets[-60:-20]]
    delta20 = L20 - sum(rets[-20:])
    rets[-20:] = [x + delta20 / 20.0 for x in rets[-20:]]
    series = [1.0]
    for r in rets:
        series.append(series[-1] * math.exp(r))
    scale = profile["price"] / series[-1]
    closes = [_round(x * scale, 2) for x in series]
    closes[-1] = profile["price"]
    return closes


def _rank(values: list[float], v: float) -> float:
    below = sum(1 for x in values if x < v)
    return _round(below / max(1, len(values) - 1), 3)


def _valuation_series(inst: dict, profile: dict, closes: list[float]) -> dict:
    """按 chains.json 的 valuation_basis 生成月度估值序列，再插值到日频。"""
    chain = inst["chain_id"]
    basis = inst["valuation_basis"]
    rnd = _rng("valuation", chain, inst["symbol"])
    n = len(closes)
    step = 21
    m_idx = list(range(0, n, step))
    if m_idx[-1] != n - 1:
        m_idx.append(n - 1)
    m = len(m_idx)
    center = profile["pe_center"] if basis == "pe" else profile["pb_center"]
    growth_start = 0.82 + rnd.uniform(-0.03, 0.05)
    slow = 0.0
    vals: list[float] = []
    for k, i in enumerate(m_idx):
        t = k / max(1, m - 1)
        growth = growth_start + (1.0 - growth_start) * t
        slow = slow * 0.985 + rnd.gauss(0.0, 0.012)
        vals.append(center * ((closes[i] / closes[-1]) ** 0.35) / growth * math.exp(slow))

    ramp = min(12, m - 1)
    for _ in range(5):
        ordered = sorted(vals)
        target = profile["pct_target"]
        target_val = ordered[min(m - 1, max(0, int(target * (m - 1))))]
        factor = target_val / vals[-1]
        for k in range(ramp + 1):
            j = m - ramp - 1 + k
            w = k / ramp
            vals[j] *= 1.0 + (factor - 1.0) * w

    now = _round(vals[-1], 2)
    vals[-1] = now
    if basis == "pe":
        pe_m, pb_m = vals, [x * profile["pb_center"] / profile["pe_center"] for x in vals]
    else:
        pb_m, pe_m = vals, [x * profile["pe_center"] / profile["pb_center"] for x in vals]
    pe_now, pb_now = _round(pe_m[-1], 1), _round(pb_m[-1], 2)
    pe_m[-1], pb_m[-1] = pe_now, pb_now
    pct_m = [_rank(vals, x) for x in vals]
    other_m = pb_m if basis == "pe" else pe_m
    other_pct_m = [_rank(other_m, x) for x in other_m]

    def interp(series: list[float], i: int) -> float:
        if i <= m_idx[0]:
            return series[0]
        for k in range(1, m):
            if i <= m_idx[k]:
                x0, x1 = m_idx[k - 1], m_idx[k]
                w = (i - x0) / max(1, x1 - x0)
                return series[k - 1] + (series[k] - series[k - 1]) * w
        return series[-1]

    rows = []
    for i, d in enumerate(DATES):
        pe_pct = interp(pct_m, i) if basis == "pe" else interp(other_pct_m, i)
        pb_pct = interp(pct_m, i) if basis == "pb" else interp(other_pct_m, i)
        rows.append({
            "date": d.isoformat(),
            "pe_ttm": _round(interp(pe_m, i), 2),
            "pb": _round(interp(pb_m, i), 2),
            "pe_pct": _round(pe_pct, 3),
            "pb_pct": _round(pb_pct, 3),
        })
    rows[-1]["pe_ttm"] = pe_now
    rows[-1]["pb"] = pb_now
    rows[-1]["pe_pct"] = pct_m[-1] if basis == "pe" else other_pct_m[-1]
    rows[-1]["pb_pct"] = pct_m[-1] if basis == "pb" else other_pct_m[-1]
    basis_pct = rows[-1]["pe_pct"] if basis == "pe" else rows[-1]["pb_pct"]
    return {"rows": rows, "pe_now": pe_now, "pb_now": pb_now, "basis_pct": basis_pct}


def _financials(inst: dict, profile: dict) -> list[dict]:
    rnd = _rng("financials", inst["chain_id"], inst["symbol"])
    out = []
    n = len(QUARTERS)
    for i, q in enumerate(QUARTERS):
        t = (i + 1) / n
        wobble = rnd.uniform(-1.0, 1.0)
        out.append({
            "report_date": q,
            "revenue_yoy": _round(profile["revenue_yoy"] + (1 - t) * rnd.uniform(-8, 5) + wobble * 1.8, 1),
            "profit_yoy": _round(profile["profit_yoy"] + (1 - t) * rnd.uniform(-10, 5) + wobble * 2.2, 1),
            "gross_margin": _round(profile["gross_margin"] + (1 - t) * rnd.uniform(-2.4, 1.4) + wobble * 0.35, 1),
            "net_margin": _round(max(0.2, profile["net_margin"] + (1 - t) * rnd.uniform(-1.6, 0.9) + wobble * 0.25), 1),
            "roe": _round(max(0.5, profile["roe"] + (1 - t) * rnd.uniform(-3, 2) + wobble * 0.4), 1),
            "inventory_days": _round(profile["inventory_days"] + (1 - t) * rnd.uniform(-7, 9) + wobble * 1.8, 1),
        })
    return out


BUNDLE: dict[str, dict] = {}
NODE_NAME = {c["id"]: {n["id"]: n["name"] for n in NODES_BY_CHAIN[c["id"]]} for c in CHAINS}
for chain in CHAINS:
    for idx, inst in enumerate(chain["instruments"]):
        full = INST_BY_SYMBOL[inst["symbol"]]
        full["node_name"] = NODE_NAME[chain["id"]][inst["node_id"]]
        profile = _profile(full, idx)
        closes = _price_series(full, profile)
        valuation = _valuation_series(full, profile, closes)
        BUNDLE[inst["symbol"]] = {
            **full,
            "profile": profile,
            "closes": closes,
            "valuation": valuation["rows"],
            "financials": _financials(full, profile),
            "pe_now": valuation["pe_now"],
            "pb_now": valuation["pb_now"],
            "basis_pct": valuation["basis_pct"],
            "pct_1d": _round((closes[-1] / closes[-2] - 1) * 100, 2),
            "pct_20d": _round((closes[-1] / closes[-21] - 1) * 100, 2),
            "pct_60d": _round((closes[-1] / closes[-61] - 1) * 100, 2),
        }


# --------------------------------------------------------------------------
# 初始人工状态
# --------------------------------------------------------------------------

def _snapshot_hash(*parts) -> str:
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


def _mk_assumption(aid: int, symbol: str, statement: str, metric: str, target: str,
                   deadline: str, status: str = "pending", evidence: str = "",
                   scope: str = "stock") -> dict:
    return {
        "id": aid, "symbol": symbol, "scope": scope, "statement": statement,
        "metric": metric, "target": target, "deadline": deadline, "status": status,
        "evidence": evidence, "updated_at": "2026-10-16",
    }


def _initial_theses() -> dict[str, dict]:
    return {
        "000333.SZ": {
            "id": 1, "symbol": "000333.SZ", "chain_id": "whites", "status": "holding",
            "title": "整机龙头：成本下行 + 出海",
            "core_logic": "空调排产与出口同步回暖，铜价回落让成本端改善；ToB 业务提供第二条曲线。"
                          "13 倍 PE 位于近三年 42% 分位，赔率一般，持有不加。",
            "valuation_view": "12–14 倍是合理区间，12 倍以下才有明显安全边际；向上需要 Q3 毛利率确认。",
            "horizon": "6-12 个月", "created_at": "2026-08-12", "updated_at": "2026-10-16",
            "assumptions": [
                _mk_assumption(1, "000333.SZ", "Q3 毛利率同比提升至 27% 以上", "销售毛利率", "≥27%", "2026-10-31", "progress",
                               "H1 已达 26.8%，Q3 待披露"),
                _mk_assumption(2, "000333.SZ", "空调出口量连续两个季度正增长", "空调出口同比", "≥5%", "2026-11-08"),
            ],
        },
        "300274.SZ": {
            "id": 2, "symbol": "300274.SZ", "chain_id": "pv", "status": "building",
            "title": "逆变器出海，储能是第二增长",
            "core_logic": "海外逆变器需求稳定，储能系统出货放量；组件价格下行反而利好电站装机。"
                          "PB 分位 72% 偏贵，只做小仓位，等回落到 50% 分位以下再加。",
            "valuation_view": "PB 3 倍以下有安全边际，4 倍以上只持有不加。",
            "horizon": "6-12 个月", "created_at": "2026-09-05", "updated_at": "2026-10-15",
            "assumptions": [
                _mk_assumption(3, "300274.SZ", "储能出货量同比翻倍", "储能出货量", "≥100%", "2026-11-15", "progress",
                               "H1 储能收入 +118%"),
                _mk_assumption(4, "300274.SZ", "海外收入占比维持 55% 以上", "海外收入占比", "≥55%", "2026-11-20"),
            ],
        },
        "600660.SH": {
            "id": 3, "symbol": "600660.SH", "chain_id": "auto", "status": "holding",
            "title": "汽玻龙头，全球化与高分红",
            "core_logic": "全球份额继续提升，海外工厂爬坡摊薄成本；分红率稳定，15 倍 PE 对应 20% 的利润增速。",
            "valuation_view": "14–18 倍合理，跌破 12 倍加仓。",
            "horizon": "12-24 个月", "created_at": "2026-06-18", "updated_at": "2026-10-14",
            "assumptions": [
                _mk_assumption(5, "600660.SH", "海外收入增速保持 20% 以上", "海外营收同比", "≥20%", "2026-10-05", "pending"),
                _mk_assumption(6, "600660.SH", "毛利率维持 34% 以上", "销售毛利率", "≥34%", "2026-11-12", "progress",
                               "H1 35.1%"),
            ],
        },
        "601888.SH": {
            "id": 5, "symbol": "601888.SH", "chain_id": "tourism", "status": "holding",
            "title": "免税客流修复，毛利见底",
            "core_logic": "离岛免税销售额环比改善，机场租金重谈后成本压力下降；PE 分位 62%，持有观察。",
            "valuation_view": "25 倍以下加仓，35 倍以上减仓。",
            "horizon": "6-12 个月", "created_at": "2026-08-28", "updated_at": "2026-10-13",
            "assumptions": [
                _mk_assumption(8, "601888.SH", "离岛免税销售额同比转正", "免税销售额同比", "≥0%", "2026-10-25", "pending"),
                _mk_assumption(9, "601888.SH", "毛利率环比提升", "销售毛利率", "≥32%", "2026-11-10", "progress",
                               "Q2 31.5%"),
            ],
        },
        "601899.SH": {
            "id": 4, "symbol": "601899.SH", "chain_id": "copper", "status": "watch",
            "title": "铜矿放量，等更好的 PB",
            "core_logic": "铜价高位 + 自有矿放量，PB 分位 31% 不算贵；但资本开支上行，先跟踪产量指引。",
            "valuation_view": "PB 2.2 倍以下分批，3 倍以上不再加。",
            "horizon": "12-18 个月", "created_at": "2026-09-20", "updated_at": "2026-10-12",
            "assumptions": [
                _mk_assumption(7, "601899.SH", "全年铜产量指引不下调", "铜产量", "≥指引下限", "2026-10-10", "invalidated",
                               "Q3 指引下调 3%，逻辑证伪"),
            ],
        },
    }


def _initial_positions() -> dict[str, dict]:
    plan = [
        ("000333.SZ", 8.0, 9.6),
        ("300274.SZ", 4.0, 3.2),
        ("600660.SH", 3.0, -2.4),
        ("601899.SH", 2.0, 5.1),
        ("601888.SH", 1.0, 1.8),
    ]
    out = {}
    for i, (symbol, weight, pnl) in enumerate(plan, start=1):
        price = BUNDLE[symbol]["closes"][-1]
        entry = _round(price / (1.0 + pnl / 100.0), 2)
        out[symbol] = {
            "id": i, "symbol": symbol, "chain_id": BUNDLE[symbol]["chain_id"],
            "chain_name": BUNDLE[symbol]["chain_name"],
            "weight_pct": weight, "entry_price": entry, "opened_at": "2026-09-02",
            "status": "open",
        }
    return out


def _initial_decisions() -> list[dict]:
    plan = [
        ("000333.SZ", "buy", 8.0, "估值分位偏低 + 毛利率改善，先建 8% 底盘。", "毛利率连续两季低于 25% 或 PE 分位升破 80%", "2026-10-14T10:42:00"),
        ("300274.SZ", "buy", 4.0, "储能出货翻倍，先建 4% 仓位，PB 回落到 50% 分位以下再加。", "储能增速低于 30%", "2026-10-08T14:12:00"),
        ("600660.SH", "buy", 3.0, "海外产能爬坡，15 倍 PE 对应 20% 增速。", "海外收入增速低于 10%", "2026-10-06T09:40:00"),
        ("601899.SH", "watch", 0.0, "铜产量指引待确认，先观察不开仓。", "产量指引下调且 PB 升破 70% 分位", "2026-10-04T11:05:00"),
        ("601888.SH", "buy", 1.0, "免税客流恢复，试仓 1%。", "离岛免税销售额连续两季负增长", "2026-10-02T10:20:00"),
        ("002050.SZ", "watch", 0.0, "热管理订单跟踪，等待机器人定点。", "机器人订单证伪", "2026-09-22T15:30:00"),
    ]
    out = []
    for i, (symbol, action, weight, logic, kill, created) in enumerate(plan, start=1):
        b = BUNDLE[symbol]
        out.append({
            "id": i, "symbol": symbol, "name": b["name"], "chain_id": b["chain_id"],
            "chain_name": b["chain_name"], "action": action,
            "price": b["closes"][-1], "weight_pct": weight,
            "logic": logic, "kill_switch": kill,
            "snapshot_hash": _snapshot_hash(symbol, action, logic, kill),
            "created_at": created,
        })
    return out


def _initial_alerts() -> list[dict]:
    plan = [
        ("000333.SZ", "valuation", "high", "PE 分位 82%，接近高位，核对估值假设"),
        ("000521.SZ", "valuation", "high", "PE 分位 95%，处于高位"),
        ("002508.SZ", "valuation", "watch", "PE 分位 84%，竣工端未见拐点"),
        ("000333.SZ", "assumption", "high", "假设「Q3 毛利率同比提升至 27% 以上」10-31 到期"),
        ("002050.SZ", "valuation", "watch", "PE 分位 88%，等待机器人定点"),
        ("300274.SZ", "valuation", "high", "PB 分位 72%，高于持有区间"),
        ("600438.SH", "valuation", "high", "PB 分位 91%，硅料价格若反弹需重估"),
        ("002129.SZ", "valuation", "watch", "PB 分位 88%，硅片价格战未见底"),
        ("600660.SH", "assumption", "high", "假设「海外收入增速保持 20% 以上」已逾期 11 天"),
        ("601127.SH", "valuation", "watch", "PE 分位 90%，新车型订单待验证"),
        ("601899.SH", "assumption", "high", "假设「全年铜产量指引不下调」已证伪，请更新逻辑"),
        ("601888.SH", "valuation", "watch", "PE 分位 84%，免税销售额增速放缓"),
    ]
    out = []
    for i, (symbol, kind, level, message) in enumerate(plan, start=1):
        b = BUNDLE[symbol]
        out.append({
            "id": ("valuation-%s" % symbol) if kind == "valuation" else ("assumption-%d" % i),
            "symbol": symbol, "name": b["name"], "chain_id": b["chain_id"],
            "chain_name": b["chain_name"], "level": level, "kind": kind,
            "message": message, "created_at": "2026-10-18T09:%02d:00" % (10 + i),
            "resolved": False,
        })
    return out


DB: dict = {}
DB["theses"] = _initial_theses()
DB["positions"] = _initial_positions()
DB["decisions"] = _initial_decisions()
DB["alerts"] = _initial_alerts()
DB["review_md"] = {}
DB["assumption_seq"] = 100
DB["decision_seq"] = 100


# --------------------------------------------------------------------------
# 聚合
# --------------------------------------------------------------------------

def _stock_row(symbol: str) -> dict:
    b = BUNDLE[symbol]
    thesis = DB["theses"].get(symbol)
    alerts = sum(
        1 for a in (thesis["assumptions"] if thesis else [])
        if a["status"] in ("pending", "progress") and a.get("deadline") and a["deadline"] < AS_OF.isoformat()
    )
    return {
        "symbol": symbol, "name": b["name"],
        "chain_id": b["chain_id"], "chain_name": b["chain_name"],
        "node_id": b["node_id"], "node_name": b["node_name"], "role": b["role"],
        "price": b["closes"][-1], "pct_1d": b["pct_1d"], "pct_20d": b["pct_20d"], "pct_60d": b["pct_60d"],
        "pe_ttm": b["pe_now"], "pe_pct_3y": b["valuation"][-1]["pe_pct"],
        "pb": b["pb_now"], "pb_pct_3y": b["valuation"][-1]["pb_pct"],
        "valuation_basis": b["valuation_basis"],
        "gross_margin": b["profile"]["gross_margin"],
        "revenue_yoy": b["profile"]["revenue_yoy"],
        "profit_yoy": b["profile"]["profit_yoy"],
        "inventory_days": b["profile"]["inventory_days"],
        "score": b["profile"]["score"], "attention": b["profile"]["attention"],
        "thesis_status": thesis["status"] if thesis else "watch",
        "assumption_alert": alerts,
        "basis_pct": b["basis_pct"],
    }


def _chain_stocks(chain_id: str) -> list[dict]:
    chain = CHAIN_BY_ID[chain_id]
    rows = [_stock_row(i["symbol"]) for i in chain["instruments"]]
    rows.sort(key=lambda r: (CHAIN_ORDER[chain_id], r["name"]))
    return rows


def _node_metrics(chain_id: str, rows: list[dict]) -> list[dict]:
    out = []
    for node in NODES_BY_CHAIN[chain_id]:
        members = [r for r in rows if r["node_id"] == node["id"]]
        out.append({
            "id": node["id"], "name": node["name"], "role": node["role"],
            "description": node["description"], "stocks": len(members),
            "median_pct": _round(_median([r["basis_pct"] for r in members]), 3),
            "median_gross_margin": _round(_median([r["gross_margin"] for r in members]), 1),
            "median_revenue_yoy": _round(_median([r["revenue_yoy"] for r in members]), 1),
            "pct_20d": _round(_median([r["pct_20d"] for r in members]), 1),
        })
    return out


def _chain_metrics(chain_id: str, rows: list[dict]) -> dict:
    basis = CHAIN_BY_ID[chain_id]["valuation_basis"]
    label = "PE" if basis == "pe" else "PB"
    pct20 = _round(_median([r["pct_20d"] for r in rows]), 1)
    pct60 = _round(_median([r["pct_60d"] for r in rows]), 1)
    return {
        "median_pct": _round(_median([r["basis_pct"] for r in rows]), 3),
        "median_gross_margin": _round(_median([r["gross_margin"] for r in rows]), 1),
        "median_revenue_yoy": _round(_median([r["revenue_yoy"] for r in rows]), 1),
        "pct_20d": pct20, "pct_60d": pct60,
        "relative_60d": _round(pct60 - BENCHMARK["pct_60d"], 1),
        "up_20d": sum(1 for r in rows if r["pct_20d"] > 0),
        "down_20d": sum(1 for r in rows if r["pct_20d"] < 0),
        "high_pct": sum(1 for r in rows if r["basis_pct"] > 0.8),
        "low_pct": sum(1 for r in rows if r["basis_pct"] < 0.2),
        "valuation_label": label,
    }


def _positions_for_chain(chain_id: str) -> list[dict]:
    return [p for p in DB["positions"].values() if p["chain_id"] == chain_id]


def _alerts_for_chain(chain_id: str) -> list[dict]:
    return [a for a in DB["alerts"] if not a["resolved"] and a["chain_id"] == chain_id]


def _scenario_position(p: dict) -> dict:
    b = BUNDLE[p["symbol"]]
    price = b["closes"][-1]
    pnl = _round((price / p["entry_price"] - 1) * 100, 1)
    return {
        "symbol": p["symbol"], "name": b["name"],
        "chain_id": p["chain_id"], "chain_name": p["chain_name"],
        "weight_pct": p["weight_pct"], "entry_price": p["entry_price"],
        "price": price, "pnl_pct": pnl, "opened_at": p["opened_at"],
        "status": p.get("status", "open"),
    }


def _all_positions() -> list[dict]:
    return [_scenario_position(p) for p in DB["positions"].values()]


def _weighted_pnl(positions: list[dict]) -> float:
    total = sum(p["weight_pct"] for p in positions)
    if not total:
        return 0.0
    return _round(sum(p["weight_pct"] * p["pnl_pct"] for p in positions) / total, 1)


def _chain_payload(chain_id: str) -> dict:
    chain = CHAIN_BY_ID[chain_id]
    rows = _chain_stocks(chain_id)
    metrics = _chain_metrics(chain_id, rows)
    positions = _positions_for_chain(chain_id)
    label = metrics["valuation_label"]
    return {
        "id": chain_id, "name": chain["name"], "short": chain["short"],
        "description": chain["description"], "valuation_basis": chain["valuation_basis"],
        "valuation_label": label, "stocks": len(rows), "nodes": len(NODES_BY_CHAIN[chain_id]),
        **metrics,
        "holdings_weight": _round(sum(p["weight_pct"] for p in positions), 1),
        "theses": sum(1 for t in DB["theses"].values() if t.get("chain_id") == chain_id),
        "alerts": len(_alerts_for_chain(chain_id)),
        "kpis": chain.get("kpis", []),
        "node_list": NODES_BY_CHAIN[chain_id],
    }


def _overview_reads(chain_id: str, rows: list[dict], metrics: dict) -> list[dict]:
    label = metrics["valuation_label"]
    top = max(rows, key=lambda r: r["pct_20d"])
    weak = min(rows, key=lambda r: r["pct_20d"])
    return [
        {"label": label + " 分位中位", "value": "%d%%" % round(metrics["median_pct"] * 100),
         "delta": None, "note": "20 只标的近三年" + label + "分位"},
        {"label": "毛利率中位", "value": "%.1f%%" % metrics["median_gross_margin"], "delta": 0.6,
         "note": "成本与产品结构的中位表现"},
        {"label": "20 日涨跌", "value": "%d 涨 / %d 跌" % (metrics["up_20d"], metrics["down_20d"]),
         "delta": None, "note": "领涨 %s，偏弱 %s" % (top["name"], weak["name"])},
        {"label": "相对强弱（60 日）", "value": ("%+.1f pp" % metrics["relative_60d"]),
         "delta": None, "note": "相对沪深300 的超额，正数为强于基准"},
        {"label": "极端估值", "value": "%d 高 / %d 低" % (metrics["high_pct"], metrics["low_pct"]),
         "delta": None, "note": label + " 分位 >80% 或 <20%"},
    ]


def _overview(chain_id: str) -> dict:
    rows = _chain_stocks(chain_id)
    metrics = _chain_metrics(chain_id, rows)
    nodes = _node_metrics(chain_id, rows)
    distribution = []
    for node in NODES_BY_CHAIN[chain_id]:
        points = [
            {"symbol": r["symbol"], "name": r["name"], "pct": r["basis_pct"]}
            for r in rows if r["node_id"] == node["id"]
        ]
        points.sort(key=lambda p: p["pct"])
        distribution.append({"node_id": node["id"], "name": node["name"], "points": points})
    return {
        "as_of": AS_OF.isoformat(),
        "chain": _chain_payload(chain_id),
        "benchmark": dict(BENCHMARK),
        "breadth": {"up_20d": metrics["up_20d"], "down_20d": metrics["down_20d"],
                    "median_pct": metrics["median_pct"]},
        "nodes": nodes,
        "distribution": distribution,
        "reads": _overview_reads(chain_id, rows, metrics),
        "stocks": rows,
    }


def _master() -> dict:
    chain_rows = []
    all_positions = _all_positions()
    for chain in CHAINS:
        rows = _chain_stocks(chain["id"])
        metrics = _chain_metrics(chain["id"], rows)
        positions = _positions_for_chain(chain["id"])
        chain_rows.append({
            "id": chain["id"], "name": chain["name"], "short": chain["short"],
            "description": chain["description"], "valuation_basis": chain["valuation_basis"],
            "valuation_label": metrics["valuation_label"], "stocks": len(rows),
            "median_pct": metrics["median_pct"],
            "median_gross_margin": metrics["median_gross_margin"],
            "median_revenue_yoy": metrics["median_revenue_yoy"],
            "pct_20d": metrics["pct_20d"], "pct_60d": metrics["pct_60d"],
            "relative_60d": metrics["relative_60d"],
            "up_20d": metrics["up_20d"], "down_20d": metrics["down_20d"],
            "high_pct": metrics["high_pct"], "low_pct": metrics["low_pct"],
            "holdings_weight": _round(sum(p["weight_pct"] for p in positions), 1),
            "theses": sum(1 for t in DB["theses"].values() if t.get("chain_id") == chain["id"]),
            "alerts": len(_alerts_for_chain(chain["id"])),
            "kpis": chain.get("kpis", []),
        })
    allocation: dict[str, dict] = {}
    for p in all_positions:
        row = allocation.setdefault(p["chain_id"], {"chain_id": p["chain_id"], "name": p["chain_name"], "weight": 0.0})
        row["weight"] = _round(row["weight"] + p["weight_pct"], 1)
    alerts = [a for a in DB["alerts"] if not a["resolved"]]
    upcoming = _upcoming("")
    month = AS_OF.strftime("%Y-%m")
    decisions = [d for d in DB["decisions"] if d["created_at"][:7] == month]
    decisions.sort(key=lambda d: d["created_at"], reverse=True)
    return {
        "as_of": AS_OF.isoformat(),
        "benchmark": dict(BENCHMARK),
        "summary": {
            "chains": len(CHAINS), "stocks": len(INSTRUMENTS),
            "positions": len(all_positions),
            "total_weight": _round(sum(p["weight_pct"] for p in all_positions), 1),
            "weighted_pnl": _weighted_pnl(all_positions),
            "theses": len(DB["theses"]),
            "alerts": len(alerts),
            "high_alerts": sum(1 for a in alerts if a.get("level") == "high"),
        },
        "chains": chain_rows,
        "positions": all_positions,
        "allocation": sorted(allocation.values(), key=lambda r: -r["weight"]),
        "inbox": sorted(alerts, key=lambda a: a["created_at"], reverse=True),
        "upcoming": upcoming,
        "decisions": decisions,
    }


def _stock_meta(symbol: str) -> dict:
    b = BUNDLE[symbol]
    thesis = DB["theses"].get(symbol)
    return {
        "symbol": symbol, "name": b["name"],
        "chain_id": b["chain_id"], "chain_name": b["chain_name"],
        "node_id": b["node_id"], "node_name": b["node_name"], "role": b["role"],
        "valuation_basis": b["valuation_basis"],
        "price": b["closes"][-1], "pct_1d": b["pct_1d"], "pct_20d": b["pct_20d"], "pct_60d": b["pct_60d"],
        "pe_ttm": b["pe_now"], "pe_pct_3y": b["valuation"][-1]["pe_pct"],
        "pb": b["pb_now"], "pb_pct_3y": b["valuation"][-1]["pb_pct"],
        "gross_margin": b["profile"]["gross_margin"], "net_margin": b["profile"]["net_margin"],
        "roe": b["profile"]["roe"], "revenue_yoy": b["profile"]["revenue_yoy"],
        "profit_yoy": b["profile"]["profit_yoy"], "inventory_days": b["profile"]["inventory_days"],
        "score": b["profile"]["score"], "attention": b["profile"]["attention"],
        "institution": b["profile"]["institution"],
        "thesis_status": thesis["status"] if thesis else "",
        "thesis_status_label": STATUS_CN.get(thesis["status"], "") if thesis else "",
    }


# --------------------------------------------------------------------------
# 复盘
# --------------------------------------------------------------------------

def _review_key(month: str, chain_id: str) -> str:
    return month + "|" + (chain_id or "")


def _build_review_md(month: str, chain_id: str) -> str:
    label = CHAIN_BY_ID[chain_id]["name"] if chain_id else "全部产业链"
    positions = [p for p in _all_positions() if not chain_id or p["chain_id"] == chain_id]
    total = _round(sum(p["weight_pct"] for p in positions), 1)
    pnl = _weighted_pnl(positions)
    lines = [
        "# %s %s 月度体检" % (month, label), "",
        "数据截至 %s。" % AS_OF.isoformat(), "",
        "## 组合", "",
        "- 持仓 %d 只，总仓位 %.1f%%，浮动盈亏 %+.1f%%。" % (len(positions), total, pnl),
    ]
    by_chain: dict[str, float] = {}
    for p in positions:
        by_chain[p["chain_name"]] = _round(by_chain.get(p["chain_name"], 0) + p["weight_pct"], 1)
    for name, weight in by_chain.items():
        lines.append("- %s %.1f%%。" % (name, weight))
    lines += ["", "## 假设变化", ""]
    for symbol, thesis in DB["theses"].items():
        if chain_id and thesis.get("chain_id") != chain_id:
            continue
        for a in thesis["assumptions"]:
            if a["status"] in ("met", "invalidated") and a.get("updated_at", "") >= "2026-10-01":
                verdict = "兑现" if a["status"] == "met" else "证伪"
                lines.append("- %s｜%s：%s。%s" % (BUNDLE[symbol]["name"], a["statement"], verdict, a["evidence"]))
    lines += ["", "## 估值", ""]
    flags = _review_flags(chain_id)
    high = [f for f in flags if f["side"] == "high"]
    low = [f for f in flags if f["side"] == "low"]
    lines.append("- 高位（分位 >80%）：" + ("、".join("%s %d%%" % (f["name"], f["pct"] * 100) for f in high) or "无") + "。")
    lines.append("- 低位（分位 <20%）：" + ("、".join("%s %d%%" % (f["name"], f["pct"] * 100) for f in low) or "无") + "。")
    lines += ["", "## 下月待办", ""]
    for row in _upcoming(chain_id)[:6]:
        lines.append("- %s｜%s：%s 到期。" % (row["name"], row["statement"], row["deadline"]))
    return "\n".join(lines) + "\n"


def _upcoming(chain_id: str = "") -> list[dict]:
    rows = []
    for thesis in DB["theses"].values():
        if chain_id and thesis.get("chain_id") != chain_id:
            continue
        for a in thesis["assumptions"]:
            if a["status"] in ("pending", "progress") and a.get("deadline"):
                try:
                    dl = date.fromisoformat(a["deadline"])
                except ValueError:
                    continue
                days = (dl - AS_OF).days
                if -31 <= days <= 31:
                    b = BUNDLE[thesis["symbol"]]
                    rows.append({"symbol": thesis["symbol"], "name": b["name"],
                                 "chain_id": b["chain_id"], "chain_name": b["chain_name"],
                                 "statement": a["statement"], "deadline": a["deadline"], "days_left": days})
    rows.sort(key=lambda r: r["days_left"])
    return rows


def _review_flags(chain_id: str = "") -> list[dict]:
    flags = []
    for symbol, b in BUNDLE.items():
        if chain_id and b["chain_id"] != chain_id:
            continue
        pct = b["basis_pct"]
        if pct > 0.8 or pct < 0.2:
            flags.append({
                "symbol": symbol, "name": b["name"],
                "chain_id": b["chain_id"], "chain_name": b["chain_name"],
                "pct": pct, "side": "high" if pct > 0.8 else "low",
                "basis": b["valuation_basis"],
            })
    flags.sort(key=lambda r: r["pct"])
    return flags


def _review(month: str, chain_id: str) -> dict:
    if chain_id and chain_id not in CHAIN_BY_ID:
        raise HTTPException(status_code=404, detail="unknown chain: " + chain_id)
    positions = [p for p in _all_positions() if not chain_id or p["chain_id"] == chain_id]
    total = _round(sum(p["weight_pct"] for p in positions), 1)
    allocation: dict[str, dict] = {}
    for p in positions:
        if chain_id:
            key = BUNDLE[p["symbol"]]["node_name"]
            label = key
        else:
            key = p["chain_id"]
            label = CHAIN_BY_ID[p["chain_id"]]["name"]
        row = allocation.setdefault(key, {"chain_id": p["chain_id"], "name": label, "weight": 0.0})
        row["weight"] = _round(row["weight"] + p["weight_pct"], 1)
    board = []
    for symbol, thesis in DB["theses"].items():
        if chain_id and thesis.get("chain_id") != chain_id:
            continue
        board.append({
            "symbol": symbol, "name": BUNDLE[symbol]["name"],
            "chain_id": BUNDLE[symbol]["chain_id"], "chain_name": BUNDLE[symbol]["chain_name"],
            "thesis_status": thesis["status"],
            "assumptions": [
                {"id": a["id"], "statement": a["statement"], "status": a["status"],
                 "deadline": a["deadline"], "target": a.get("target", "")}
                for a in thesis["assumptions"]
            ],
        })
    board.sort(key=lambda r: (CHAIN_ORDER[r["chain_id"]], r["name"]))
    month_decisions = [
        d for d in DB["decisions"]
        if d["created_at"][:7] == month and (not chain_id or d["chain_id"] == chain_id)
    ]
    month_decisions.sort(key=lambda d: d["created_at"], reverse=True)
    key = _review_key(month, chain_id)
    md = DB["review_md"].get(key)
    if md is None:
        md = _build_review_md(month, chain_id)
    return {
        "month": month,
        "chain_id": chain_id,
        "chain_name": CHAIN_BY_ID[chain_id]["name"] if chain_id else "全部产业链",
        "summary": {
            "positions": len(positions), "total_weight": total,
            "weighted_pnl": _weighted_pnl(positions),
            "pnl_pct": _weighted_pnl(positions),
            "theses": sum(1 for t in DB["theses"].values() if not chain_id or t.get("chain_id") == chain_id),
        },
        "positions": positions,
        "allocation": sorted(allocation.values(), key=lambda r: -r["weight"]),
        "board": board,
        "valuation_flags": _review_flags(chain_id),
        "deadlines": _upcoming(chain_id),
        "decisions": month_decisions,
        "review_md": md,
    }


# --------------------------------------------------------------------------
# FastAPI
# --------------------------------------------------------------------------

app = FastAPI(title="v3 mock backend", version="3.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _require_symbol(symbol: str) -> dict:
    if symbol not in BUNDLE:
        raise HTTPException(status_code=404, detail="unknown symbol: " + symbol)
    return BUNDLE[symbol]


def _require_chain(chain_id: str) -> str:
    if not chain_id:
        return "whites"
    if chain_id not in CHAIN_BY_ID:
        raise HTTPException(status_code=404, detail="unknown chain: " + chain_id)
    return chain_id


@app.get("/api/health")
def health():
    return {"status": "ok", "data_ok": True, "as_of": AS_OF.isoformat()}


@app.get("/api/meta")
def meta():
    alerts = [a for a in DB["alerts"] if not a["resolved"]]
    chains = []
    for chain in CHAINS:
        chains.append({
            "id": chain["id"], "name": chain["name"], "short": chain["short"],
            "description": chain["description"], "valuation_basis": chain["valuation_basis"],
            "valuation_label": "PE" if chain["valuation_basis"] == "pe" else "PB",
            "stocks": len(chain["instruments"]), "nodes": len(NODES_BY_CHAIN[chain["id"]]),
            "kpis": chain.get("kpis", []),
        })
    return {
        "chains": chains,
        "as_of": AS_OF.isoformat(),
        "updated_at": UPDATED_AT.isoformat(timespec="seconds"),
        "counts": {"chains": len(CHAINS), "stocks": len(INSTRUMENTS),
                   "positions": len(DB["positions"]), "alerts": len(alerts)},
        "benchmark": dict(BENCHMARK),
    }


@app.get("/api/master")
def master():
    return _master()


@app.get("/api/overview")
def overview(chain: str = "whites"):
    return _overview(_require_chain(chain))


@app.get("/api/stock/{symbol}")
def stock_detail(symbol: str):
    b = _require_symbol(symbol)
    thesis = DB["theses"].get(symbol)
    decisions = [d for d in DB["decisions"] if d["symbol"] == symbol]
    decisions.sort(key=lambda d: d["created_at"], reverse=True)
    position = DB["positions"].get(symbol)
    alerts = [
        {"id": a["id"], "level": a["level"], "kind": a["kind"], "message": a["message"],
         "created_at": a["created_at"]}
        for a in DB["alerts"] if a["symbol"] == symbol and not a["resolved"]
    ]
    return {
        "stock": _stock_meta(symbol),
        "price": [{"date": d, "close": c} for d, c in zip(DATES, b["closes"])],
        "valuation": b["valuation"],
        "financials": list(reversed(b["financials"])),
        "thesis": thesis,
        "decisions": decisions,
        "position": position,
        "alerts": alerts,
    }


@app.post("/api/thesis")
async def post_thesis(request: Request):
    payload = await request.json()
    symbol = payload.get("symbol", "")
    inst = _require_symbol(symbol)
    status = payload.get("status", "watch")
    if status not in STATUS_CN:
        raise HTTPException(status_code=422, detail="invalid status: " + str(status))
    existing = DB["theses"].get(symbol)
    thesis = {
        "id": existing["id"] if existing else len(DB["theses"]) + 100,
        "symbol": symbol, "chain_id": inst["chain_id"],
        "status": status,
        "title": (payload.get("title") or "").strip(),
        "core_logic": (payload.get("core_logic") or "").strip(),
        "valuation_view": (payload.get("valuation_view") or "").strip(),
        "horizon": (payload.get("horizon") or "").strip(),
        "created_at": existing["created_at"] if existing else date.today().isoformat(),
        "updated_at": date.today().isoformat(),
        "assumptions": existing["assumptions"] if existing else [],
    }
    DB["theses"][symbol] = thesis
    return {"ok": True, "thesis": thesis}


@app.post("/api/assumption")
async def post_assumption(request: Request):
    payload = await request.json()
    symbol = payload.get("symbol", "")
    inst = _require_symbol(symbol)
    statement = (payload.get("statement") or "").strip()
    if not statement:
        raise HTTPException(status_code=422, detail="statement is required")
    thesis = DB["theses"].get(symbol)
    if thesis is None:
        thesis = {
            "id": len(DB["theses"]) + 100, "symbol": symbol, "chain_id": inst["chain_id"],
            "status": "watch", "title": "", "core_logic": "", "valuation_view": "", "horizon": "",
            "created_at": date.today().isoformat(), "updated_at": date.today().isoformat(),
            "assumptions": [],
        }
        DB["theses"][symbol] = thesis
    DB["assumption_seq"] += 1
    assumption = _mk_assumption(
        DB["assumption_seq"], symbol, statement,
        (payload.get("metric") or "").strip(), (payload.get("target") or "").strip(),
        (payload.get("deadline") or "").strip(), "pending", "",
        (payload.get("scope") or "stock").strip() or "stock",
    )
    assumption["updated_at"] = date.today().isoformat()
    thesis["assumptions"].append(assumption)
    thesis["updated_at"] = date.today().isoformat()
    return {"ok": True, "assumption": assumption}


@app.patch("/api/assumption/{assumption_id}")
async def patch_assumption(assumption_id: str, request: Request):
    payload = await request.json()
    status = payload.get("status")
    if status is not None and status not in ASSUMPTION_STATUS:
        raise HTTPException(status_code=422, detail="invalid status: " + str(status))
    for thesis in DB["theses"].values():
        for a in thesis["assumptions"]:
            if str(a["id"]) == str(assumption_id):
                if status is not None:
                    a["status"] = status
                if payload.get("evidence") is not None:
                    a["evidence"] = str(payload["evidence"]).strip()
                a["updated_at"] = date.today().isoformat()
                thesis["updated_at"] = a["updated_at"]
                return {"ok": True}
    raise HTTPException(status_code=404, detail="unknown assumption: " + str(assumption_id))


@app.post("/api/decision")
async def post_decision(request: Request):
    payload = await request.json()
    symbol = payload.get("symbol", "")
    inst = _require_symbol(symbol)
    action = payload.get("action", "")
    if action not in ACTION_CN:
        raise HTTPException(status_code=422, detail="invalid action: " + str(action))
    logic = (payload.get("logic") or "").strip()
    if not logic:
        raise HTTPException(status_code=422, detail="logic is required")
    DB["decision_seq"] += 1
    decision = {
        "id": DB["decision_seq"], "symbol": symbol, "name": inst["name"],
        "chain_id": inst["chain_id"], "chain_name": inst["chain_name"],
        "action": action,
        "price": _round(payload.get("price") or BUNDLE[symbol]["closes"][-1], 2),
        "weight_pct": _round(payload.get("weight_pct") or 0.0, 2),
        "logic": logic, "kill_switch": (payload.get("kill_switch") or "").strip(),
        "snapshot_hash": _snapshot_hash(symbol, action, payload.get("price"),
                                        payload.get("weight_pct"), logic, payload.get("kill_switch")),
        "created_at": datetime.now().replace(microsecond=0).isoformat(),
    }
    DB["decisions"].insert(0, decision)
    return {"ok": True, "decision": decision}


@app.get("/api/review")
def get_review(month: str | None = None, chain: str | None = None):
    month = month or AS_OF.strftime("%Y-%m")
    if not (len(month) == 7 and month[4] == "-" and month[:4].isdigit() and month[5:].isdigit()):
        raise HTTPException(status_code=422, detail="invalid month: " + month)
    return _review(month, chain or "")


@app.post("/api/review")
async def post_review(request: Request):
    payload = await request.json()
    month = payload.get("month", "")
    if not (len(month) == 7 and month[4] == "-"):
        raise HTTPException(status_code=422, detail="invalid month: " + month)
    if payload.get("content_md") is None:
        raise HTTPException(status_code=422, detail="content_md is required")
    chain_id = payload.get("chain_id", "") or ""
    if chain_id:
        _require_chain(chain_id)
    DB["review_md"][_review_key(month, chain_id)] = str(payload["content_md"])
    return {"ok": True}


@app.get("/api/export/review")
def export_review(month: str | None = None, chain: str | None = None):
    month = month or AS_OF.strftime("%Y-%m")
    chain_id = chain or ""
    md = DB["review_md"].get(_review_key(month, chain_id)) or _build_review_md(month, chain_id)
    name = "review-" + month + ("-" + chain_id if chain_id else "") + ".md"
    return PlainTextResponse(
        md,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="%s"' % name},
    )


@app.get("/api/inbox")
def inbox():
    items = [a for a in DB["alerts"] if not a["resolved"]]
    items.sort(key=lambda a: a["created_at"], reverse=True)
    return [
        {k: a[k] for k in ("id", "symbol", "name", "chain_id", "chain_name", "level", "kind", "message", "created_at")}
        for a in items
    ]


@app.post("/api/alerts/{alert_id}/resolve")
def resolve_alert(alert_id: str):
    for a in DB["alerts"]:
        if str(a["id"]) == str(alert_id):
            a["resolved"] = True
            return {"ok": True}
    raise HTTPException(status_code=404, detail="unknown alert: " + str(alert_id))


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(status_code=exc.status_code, content={"ok": False, "detail": exc.detail})


WEB_DIR = ROOT / "web"
if WEB_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(WEB_DIR), html=True), name="web")


if __name__ == "__main__":
    import uvicorn

    print("mock v3: http://127.0.0.1:8200  (static: %s)" % WEB_DIR)
    uvicorn.run(app, host="127.0.0.1", port=8200, log_level="info")
