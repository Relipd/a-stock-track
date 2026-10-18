"""多产业链配置加载（config/chains.json）。

一条产业链 = 节点拓扑 + 标的池 + 估值口径 + 行业 KPI 定义（KPI 暂只定义，后续可接手工/自动数据）。
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "chains.json"


@lru_cache(maxsize=1)
def load() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def chains() -> list[dict]:
    return load()["chains"]


def chain(chain_id: str) -> dict | None:
    return next((c for c in chains() if c["id"] == chain_id), None)


def chain_ids() -> list[str]:
    return [c["id"] for c in chains()]


def benchmark() -> dict:
    return load()["benchmark"]


def instruments(chain_id: str | None = None) -> list[dict]:
    out = []
    for c in chains():
        if chain_id and c["id"] != chain_id:
            continue
        for i in c["instruments"]:
            out.append({**i, "chain_id": c["id"], "chain_name": c["name"]})
    return out


def symbols(chain_id: str | None = None) -> list[str]:
    return [i["symbol"] for i in instruments(chain_id)]


def all_symbols() -> list[str]:
    return symbols()


def symbol_meta(symbol: str) -> dict | None:
    for i in instruments():
        if i["symbol"] == symbol:
            return i
    return None


def name_of(symbol: str) -> str:
    meta = symbol_meta(symbol)
    return meta["name"] if meta else symbol


def chain_of(symbol: str) -> str | None:
    meta = symbol_meta(symbol)
    return meta["chain_id"] if meta else None


def node_of(symbol: str) -> str | None:
    meta = symbol_meta(symbol)
    return meta["node_id"] if meta else None


def nodes(chain_id: str) -> list[dict]:
    c = chain(chain_id)
    return c["nodes"] if c else []


def node_name(chain_id: str, node_id: str) -> str:
    return next((n["name"] for n in nodes(chain_id) if n["id"] == node_id), node_id)


def valuation_basis(chain_id: str) -> str:
    c = chain(chain_id)
    return (c or {}).get("valuation_basis", "pe")


def kpis(chain_id: str) -> list[dict]:
    c = chain(chain_id)
    return (c or {}).get("kpis", [])


def ak_code(symbol: str) -> str:
    return symbol.split(".")[0]
