"""AkShare HTTP 响应缓存：同一 URL 同一自然日只真正请求一次。

做法：在 requests.Session.send 外面包一层，GET 200 响应落到
data/raw_http_cache.sqlite；同一天再次调用直接回放 Response。
只在采集脚本中安装，Web 服务不安装、不联网。

用法：
  from data_engine import ak_cache
  ak_cache.install()
  # 同一天重复跑 fetch_* 时，相同 URL 不再打 AkShare/东财/百度
  python -m data_engine.ak_cache --stats
  python -m data_engine.ak_cache --clear
"""
from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import threading
from datetime import date, datetime, timedelta
from pathlib import Path

from config.settings import DATA_DIR

CACHE_DB = DATA_DIR / "raw_http_cache.sqlite"
MAX_BODY = 32 * 1024 * 1024
_LOCK = threading.Lock()
_INSTALLED = False


def _conn() -> sqlite3.Connection:
    CACHE_DB.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(CACHE_DB, timeout=15)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def _init() -> None:
    with _conn() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS http_cache ("
            " key TEXT PRIMARY KEY, url TEXT, day TEXT, status INTEGER,"
            " headers TEXT, body BLOB, created_at TEXT)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_http_day ON http_cache(day)")


def _key(url: str) -> tuple[str, str]:
    day = date.today().isoformat()
    return hashlib.sha256((day + "|" + url).encode("utf-8")).hexdigest(), day


def _get(url: str):
    key, day = _key(url)
    try:
        with _conn() as conn:
            row = conn.execute(
                "SELECT status, headers, body FROM http_cache WHERE key=? AND day=?",
                (key, day),
            ).fetchone()
        return row
    except sqlite3.Error:
        return None


def _put(url: str, status: int, headers: dict, body: bytes) -> None:
    key, day = _key(url)
    try:
        with _LOCK, _conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO http_cache(key,url,day,status,headers,body,created_at)"
                " VALUES(?,?,?,?,?,?,?)",
                (key, url, day, status, json.dumps(dict(headers), ensure_ascii=False),
                 body, datetime.now().isoformat(timespec="seconds")),
            )
    except sqlite3.Error:
        pass


def install() -> None:
    global _INSTALLED
    if _INSTALLED or os.environ.get("AK_CACHE_DISABLE") == "1":
        return
    try:
        import requests
        from requests.structures import CaseInsensitiveDict
    except ImportError:
        return
    _init()
    try:
        prune(7)
    except sqlite3.Error:
        pass
    original = requests.sessions.Session.send

    def send(self, request, **kwargs):  # type: ignore[no-untyped-def]
        if request.method.upper() != "GET" or kwargs.get("stream"):
            return original(self, request, **kwargs)
        cached = _get(request.url)
        if cached:
            status, headers, body = cached
            resp = requests.Response()
            resp.status_code = status
            resp._content = body
            resp.headers = CaseInsensitiveDict(json.loads(headers or "{}"))
            resp.url = request.url
            resp.request = request
            resp.encoding = "utf-8"
            resp.reason = "OK"
            return resp
        resp = original(self, request, **kwargs)
        try:
            if resp.status_code == 200 and len(resp.content) <= MAX_BODY:
                _put(request.url, resp.status_code, resp.headers, resp.content)
        except Exception:  # noqa: BLE001
            pass
        return resp

    requests.sessions.Session.send = send
    _INSTALLED = True


def stats() -> dict:
    _init()
    with _conn() as conn:
        total = conn.execute("SELECT COUNT(*) FROM http_cache").fetchone()[0]
        today = conn.execute("SELECT COUNT(*) FROM http_cache WHERE day=?", (date.today().isoformat(),)).fetchone()[0]
        size = CACHE_DB.stat().st_size if CACHE_DB.exists() else 0
    return {"total": total, "today": today, "bytes": size, "path": str(CACHE_DB)}


def clear(days: int = 0) -> int:
    _init()
    with _conn() as conn:
        if days > 0:
            cutoff = (date.today() - timedelta(days=days)).isoformat()
            cur = conn.execute("DELETE FROM http_cache WHERE day < ?", (cutoff,))
        else:
            cur = conn.execute("DELETE FROM http_cache")
        return cur.rowcount


def prune(days: int = 7) -> int:
    return clear(days)


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description="AkShare 原始 HTTP 缓存")
    parser.add_argument("--stats", action="store_true")
    parser.add_argument("--clear", action="store_true")
    parser.add_argument("--prune", type=int, default=7)
    args = parser.parse_args()
    if args.clear:
        n = clear()
        print(f"cleared {n} rows")
    if args.prune:
        print(f"pruned {prune(args.prune)} rows older than {args.prune} days")
    print(json.dumps(stats(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
