"""v3 状态库：五条产业链的人工判断、假设、决策、持仓、复盘、提醒忽略。

只存"人的判断"；行情/财务/估值都在 Parquet。所有状态都带 chain_id，支持单链与跨链总览。
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from config.settings import STATE_DB

SCHEMA = """
CREATE TABLE IF NOT EXISTS chains (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, short TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '', valuation_basis TEXT NOT NULL DEFAULT 'pe',
    sort INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS nodes (
    chain_id TEXT NOT NULL, id TEXT NOT NULL, name TEXT NOT NULL, role TEXT NOT NULL,
    description TEXT, sort INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (chain_id, id)
);
CREATE TABLE IF NOT EXISTS instruments (
    symbol TEXT PRIMARY KEY, name TEXT NOT NULL, chain_id TEXT NOT NULL,
    node_id TEXT NOT NULL, role TEXT NOT NULL, sort INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS theses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL UNIQUE, chain_id TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'watch',
    title TEXT NOT NULL DEFAULT '', core_logic TEXT NOT NULL DEFAULT '',
    valuation_view TEXT NOT NULL DEFAULT '', horizon TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS thesis_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL, version INTEGER NOT NULL,
    payload_json TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS assumptions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL, chain_id TEXT NOT NULL, scope TEXT NOT NULL DEFAULT 'stock',
    statement TEXT NOT NULL, metric TEXT NOT NULL DEFAULT '',
    target TEXT NOT NULL DEFAULT '', deadline TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'pending', evidence TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL, chain_id TEXT NOT NULL, action TEXT NOT NULL,
    price REAL, weight_pct REAL, logic TEXT NOT NULL DEFAULT '',
    kill_switch TEXT NOT NULL DEFAULT '',
    trade_date TEXT NOT NULL DEFAULT '',
    snapshot_json TEXT NOT NULL, snapshot_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS stars (
    symbol TEXT PRIMARY KEY,
    starred INTEGER NOT NULL DEFAULT 0,
    starred_at TEXT,
    logic_note TEXT NOT NULL DEFAULT '',
    logic_date TEXT,
    logic_updated_at TEXT,
    investment_star INTEGER NOT NULL DEFAULT 0,
    investment_star_at TEXT,
    decision_date TEXT,
    decision_price REAL,
    decision_id INTEGER,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS star_note_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL, note TEXT NOT NULL, created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL UNIQUE, chain_id TEXT NOT NULL, entry_price REAL NOT NULL,
    weight_pct REAL NOT NULL, opened_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'open', updated_at TEXT NOT NULL,
    latest_decision_id INTEGER
);
CREATE TABLE IF NOT EXISTS reviews (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    month TEXT NOT NULL, chain_id TEXT NOT NULL DEFAULT '',
    content_md TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
    UNIQUE (month, chain_id)
);
CREATE TABLE IF NOT EXISTS dismissed_alerts (
    key TEXT PRIMARY KEY, created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_assumptions_symbol ON assumptions(symbol);
CREATE INDEX IF NOT EXISTS idx_decisions_symbol ON decisions(symbol);
CREATE INDEX IF NOT EXISTS idx_decisions_chain ON decisions(chain_id);
CREATE INDEX IF NOT EXISTS idx_positions_chain ON positions(chain_id);
"""


def now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def connect(db_path: Path | str = STATE_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), timeout=15)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def db(db_path: Path | str = STATE_DB):
    conn = connect(db_path)
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init(db_path: Path | str = STATE_DB) -> None:
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with db(db_path) as conn:
        conn.executescript(SCHEMA)
        cols = {r[1] for r in conn.execute("PRAGMA table_info(decisions)")}
        if "trade_date" not in cols:
            conn.execute("ALTER TABLE decisions ADD COLUMN trade_date TEXT NOT NULL DEFAULT ''")


def seed_chains(chains: list[dict]) -> None:
    init()
    with db() as conn:
        for order, c in enumerate(chains):
            conn.execute(
                "INSERT INTO chains(id,name,short,description,valuation_basis,sort) VALUES(?,?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name, short=excluded.short, "
                "description=excluded.description, valuation_basis=excluded.valuation_basis, sort=excluded.sort",
                (c["id"], c["name"], c.get("short", c["name"]), c.get("description", ""),
                 c.get("valuation_basis", "pe"), order),
            )
            for n in sorted(c.get("nodes", []), key=lambda x: x.get("sort", 0)):
                conn.execute(
                    "INSERT INTO nodes(chain_id,id,name,role,description,sort) VALUES(?,?,?,?,?,?) "
                    "ON CONFLICT(chain_id,id) DO UPDATE SET name=excluded.name, role=excluded.role, "
                    "description=excluded.description, sort=excluded.sort",
                    (c["id"], n["id"], n["name"], n["role"], n.get("description", ""), n.get("sort", 0)),
                )
            for i, inst in enumerate(c.get("instruments", [])):
                conn.execute(
                    "INSERT INTO instruments(symbol,name,chain_id,node_id,role,sort) VALUES(?,?,?,?,?,?) "
                    "ON CONFLICT(symbol) DO UPDATE SET name=excluded.name, chain_id=excluded.chain_id, "
                    "node_id=excluded.node_id, role=excluded.role, sort=excluded.sort",
                    (inst["symbol"], inst["name"], c["id"], inst["node_id"], inst["role"], i),
                )


def rows(cur) -> list[dict]:
    return [dict(r) for r in cur.fetchall()]


def chains() -> list[dict]:
    with db() as conn:
        return rows(conn.execute("SELECT * FROM chains ORDER BY sort"))


def instruments(chain_id: str | None = None) -> list[dict]:
    with db() as conn:
        if chain_id:
            return rows(conn.execute("SELECT * FROM instruments WHERE chain_id=? ORDER BY sort", (chain_id,)))
        return rows(conn.execute("SELECT * FROM instruments ORDER BY chain_id, sort"))


# ------------------------------------------------------------------ thesis
def get_thesis(conn: sqlite3.Connection, symbol: str) -> dict | None:
    row = conn.execute("SELECT * FROM theses WHERE symbol=?", (symbol,)).fetchone()
    return dict(row) if row else None


def upsert_thesis(payload: dict) -> dict:
    symbol = payload["symbol"]
    chain_id = payload.get("chain_id", "")
    ts = now()
    with db() as conn:
        existing = get_thesis(conn, symbol)
        if existing:
            version = conn.execute(
                "SELECT COALESCE(MAX(version),0)+1 FROM thesis_versions WHERE symbol=?", (symbol,)
            ).fetchone()[0]
            conn.execute(
                "INSERT INTO thesis_versions(symbol,version,payload_json,created_at) VALUES(?,?,?,?)",
                (symbol, version, json.dumps(existing, ensure_ascii=False, default=str), ts),
            )
            conn.execute(
                "UPDATE theses SET chain_id=?, status=?, title=?, core_logic=?, valuation_view=?, horizon=?, updated_at=? WHERE symbol=?",
                (chain_id or existing["chain_id"], payload.get("status", existing["status"]),
                 payload.get("title", existing["title"]), payload.get("core_logic", existing["core_logic"]),
                 payload.get("valuation_view", existing["valuation_view"]),
                 payload.get("horizon", existing["horizon"]), ts, symbol),
            )
        else:
            conn.execute(
                "INSERT INTO theses(symbol,chain_id,status,title,core_logic,valuation_view,horizon,created_at,updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (symbol, chain_id, payload.get("status", "watch"), payload.get("title", ""),
                 payload.get("core_logic", ""), payload.get("valuation_view", ""),
                 payload.get("horizon", ""), ts, ts),
            )
        return get_thesis(conn, symbol) or {}


def assumptions_of(symbol: str | None = None, chain_id: str | None = None) -> list[dict]:
    sql, args = "SELECT * FROM assumptions WHERE 1=1", []
    if symbol:
        sql += " AND symbol=?"; args.append(symbol)
    if chain_id:
        sql += " AND chain_id=?"; args.append(chain_id)
    sql += " ORDER BY id DESC"
    with db() as conn:
        return rows(conn.execute(sql, args))


def add_assumption(payload: dict) -> dict:
    ts = now()
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO assumptions(symbol,chain_id,scope,statement,metric,target,deadline,status,evidence,created_at,updated_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (payload["symbol"], payload.get("chain_id", ""), payload.get("scope", "stock"),
             payload["statement"], payload.get("metric", ""), payload.get("target", ""),
             payload.get("deadline", ""), payload.get("status", "pending"), payload.get("evidence", ""), ts, ts),
        )
        row = conn.execute("SELECT * FROM assumptions WHERE id=?", (cur.lastrowid,)).fetchone()
        return dict(row)


def update_assumption(assumption_id: int, payload: dict) -> bool:
    fields, values = [], []
    for key in ("statement", "metric", "target", "deadline", "status", "evidence", "scope"):
        if key in payload:
            fields.append(f"{key}=?")
            values.append(payload[key])
    if not fields:
        return False
    values += [now(), assumption_id]
    with db() as conn:
        conn.execute(f"UPDATE assumptions SET {', '.join(fields)}, updated_at=? WHERE id=?", values)
        return conn.total_changes > 0


# ------------------------------------------------------------------ decisions / positions
def add_decision(payload: dict, snapshot: dict) -> dict:
    ts = now()
    snap_text = json.dumps(snapshot, ensure_ascii=False, sort_keys=True, default=str)
    digest = hashlib.sha256(snap_text.encode("utf-8")).hexdigest()
    symbol = payload["symbol"]
    chain_id = payload.get("chain_id", "")
    with db() as conn:
        cur = conn.execute(
            "INSERT INTO decisions(symbol,chain_id,action,price,weight_pct,logic,kill_switch,trade_date,snapshot_json,snapshot_hash,created_at) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?)",
            (symbol, chain_id, payload["action"], payload.get("price"), payload.get("weight_pct"),
             payload.get("logic", ""), payload.get("kill_switch", ""), payload.get("trade_date", ""),
             snap_text, digest, ts),
        )
        decision_id = cur.lastrowid
        action = payload["action"]
        weight = float(payload.get("weight_pct") or 0)
        price = float(payload.get("price") or 0)
        if action in ("buy", "add") and price > 0:
            existing = conn.execute("SELECT * FROM positions WHERE symbol=?", (symbol,)).fetchone()
            if existing:
                new_weight = min(100.0, float(existing["weight_pct"]) + weight) if weight else float(existing["weight_pct"])
                total_cost = float(existing["entry_price"]) * float(existing["weight_pct"]) + price * weight
                new_entry = total_cost / new_weight if new_weight else price
                conn.execute(
                    "UPDATE positions SET entry_price=?, weight_pct=?, updated_at=?, status='open', latest_decision_id=? WHERE symbol=?",
                    (new_entry, new_weight, ts, decision_id, symbol),
                )
            else:
                conn.execute(
                    "INSERT INTO positions(symbol,chain_id,entry_price,weight_pct,opened_at,status,updated_at,latest_decision_id) "
                    "VALUES(?,?,?,?,?, 'open', ?,?)",
                    (symbol, chain_id, price, weight or 0, ts, ts, decision_id),
                )
            thesis = get_thesis(conn, symbol)
            if thesis:
                if thesis["status"] in ("watch", "closed"):
                    conn.execute("UPDATE theses SET status='holding', updated_at=? WHERE symbol=?", (ts, symbol))
            else:
                conn.execute(
                    "INSERT INTO theses(symbol,chain_id,status,created_at,updated_at) VALUES(?,?,'holding',?,?)",
                    (symbol, chain_id, ts, ts),
                )
        elif action in ("reduce", "exit"):
            existing = conn.execute("SELECT * FROM positions WHERE symbol=?", (symbol,)).fetchone()
            if existing:
                new_weight = 0 if action == "exit" else max(0.0, float(existing["weight_pct"]) - weight)
                conn.execute(
                    "UPDATE positions SET weight_pct=?, status=?, updated_at=? WHERE symbol=?",
                    (new_weight, "closed" if new_weight <= 0 else "open", ts, symbol),
                )
            thesis = get_thesis(conn, symbol)
            if thesis:
                conn.execute("UPDATE theses SET status=?, updated_at=? WHERE symbol=?",
                             ("closed" if action == "exit" else "reduced", ts, symbol))
        row = conn.execute("SELECT * FROM decisions WHERE id=?", (decision_id,)).fetchone()
        return dict(row)


def list_decisions(symbol: str | None = None, month: str | None = None, chain_id: str | None = None) -> list[dict]:
    sql, args = "SELECT * FROM decisions WHERE 1=1", []
    if symbol:
        sql += " AND symbol=?"; args.append(symbol)
    if month:
        sql += " AND created_at LIKE ?"; args.append(month + "%")
    if chain_id:
        sql += " AND chain_id=?"; args.append(chain_id)
    sql += " ORDER BY id DESC"
    with db() as conn:
        return rows(conn.execute(sql, args))


def get_position(symbol: str) -> dict | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM positions WHERE symbol=? AND status='open'", (symbol,)).fetchone()
        return dict(row) if row else None


def list_positions(chain_id: str | None = None) -> list[dict]:
    sql, args = "SELECT * FROM positions WHERE status='open'", []
    if chain_id:
        sql += " AND chain_id=?"; args.append(chain_id)
    sql += " ORDER BY weight_pct DESC"
    with db() as conn:
        return rows(conn.execute(sql, args))


# ------------------------------------------------------------------ stars / investment
def get_star(symbol: str) -> dict | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM stars WHERE symbol=?", (symbol,)).fetchone()
        return dict(row) if row else None


def list_stars() -> list[dict]:
    with db() as conn:
        return rows(conn.execute(
            "SELECT * FROM stars ORDER BY starred DESC, investment_star DESC, updated_at DESC"
        ))


def _ensure_star_row(conn: sqlite3.Connection, symbol: str) -> sqlite3.Row:
    conn.execute(
        "INSERT INTO stars(symbol,updated_at) VALUES(?,?) ON CONFLICT(symbol) DO NOTHING",
        (symbol, now()),
    )
    return conn.execute("SELECT * FROM stars WHERE symbol=?", (symbol,)).fetchone()


def set_star(symbol: str, active: bool) -> dict:
    with db() as conn:
        row = _ensure_star_row(conn, symbol)
        if not active and row["investment_star"]:
            raise ValueError("投资加星存在时不能撤星")
        ts = now()
        if active:
            conn.execute(
                "UPDATE stars SET starred=1, starred_at=?, updated_at=? WHERE symbol=?",
                (ts[:10], ts, symbol),
            )
        else:
            conn.execute("UPDATE stars SET starred=0, updated_at=? WHERE symbol=?", (ts, symbol))
        return dict(conn.execute("SELECT * FROM stars WHERE symbol=?", (symbol,)).fetchone())


def save_star_logic(symbol: str, note: str) -> dict:
    clean = str(note or "").strip()
    with db() as conn:
        row = _ensure_star_row(conn, symbol)
        if not row["starred"]:
            raise ValueError("先加星才能写逻辑评语")
        if row["investment_star"] and not clean:
            raise ValueError("投资加星期间不能清空逻辑评语")
        ts = now()
        first_date = row["logic_date"] or ts[:10]
        if clean and clean != (row["logic_note"] or ""):
            conn.execute("INSERT INTO star_note_versions(symbol,note,created_at) VALUES(?,?,?)",
                         (symbol, clean, ts))
        conn.execute(
            "UPDATE stars SET logic_note=?, logic_date=?, logic_updated_at=?, updated_at=? WHERE symbol=?",
            (clean, first_date, ts, ts, symbol),
        )
        return dict(conn.execute("SELECT * FROM stars WHERE symbol=?", (symbol,)).fetchone())


def set_investment_star(symbol: str, active: bool) -> dict:
    with db() as conn:
        row = _ensure_star_row(conn, symbol)
        if active:
            if not row["starred"]:
                raise ValueError("先加星才能投资加星")
            if not (row["logic_note"] or "").strip():
                raise ValueError("先写逻辑评语才能投资加星")
            conn.execute(
                "UPDATE stars SET investment_star=1, investment_star_at=?, updated_at=? WHERE symbol=?",
                (now()[:10], now(), symbol),
            )
        else:
            conn.execute(
                "UPDATE stars SET investment_star=0, investment_star_at=NULL, updated_at=? WHERE symbol=?",
                (now(), symbol),
            )
        return dict(conn.execute("SELECT * FROM stars WHERE symbol=?", (symbol,)).fetchone())


def star_note_history(symbol: str) -> list[dict]:
    with db() as conn:
        return rows(conn.execute(
            "SELECT * FROM star_note_versions WHERE symbol=? ORDER BY id DESC", (symbol,)
        ))


def set_star_decision(symbol: str, trade_date: str, price: float, decision_id: int) -> dict:
    with db() as conn:
        _ensure_star_row(conn, symbol)
        conn.execute(
            "UPDATE stars SET investment_star=0, investment_star_at=NULL, decision_date=?, decision_price=?, decision_id=?, updated_at=? WHERE symbol=?",
            (trade_date, price, decision_id, now(), symbol),
        )
        return dict(conn.execute("SELECT * FROM stars WHERE symbol=?", (symbol,)).fetchone())



def get_review(month: str, chain_id: str = "") -> dict | None:
    with db() as conn:
        row = conn.execute("SELECT * FROM reviews WHERE month=? AND chain_id=?", (month, chain_id)).fetchone()
        return dict(row) if row else None


def upsert_review(month: str, content_md: str, chain_id: str = "") -> None:
    ts = now()
    with db() as conn:
        conn.execute(
            "INSERT INTO reviews(month,chain_id,content_md,created_at,updated_at) VALUES(?,?,?,?,?) "
            "ON CONFLICT(month,chain_id) DO UPDATE SET content_md=excluded.content_md, updated_at=excluded.updated_at",
            (month, chain_id, content_md, ts, ts),
        )


def dismissed_keys() -> set[str]:
    with db() as conn:
        return {r["key"] for r in conn.execute("SELECT key FROM dismissed_alerts")}


def dismiss_alert(key: str) -> None:
    with db() as conn:
        conn.execute("INSERT OR IGNORE INTO dismissed_alerts(key,created_at) VALUES(?,?)", (key, now()))
