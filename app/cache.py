"""本地 API 结果缓存（SQLite）。

页面/接口只读本地文件；这里再缓存“计算后的 JSON”，让总览、单链、活文档、
月报等重复访问从 1–3 秒降到毫秒级。数据文件变化或 /api/reload 时自动失效。
"""
from __future__ import annotations

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from config.settings import CACHE_DB, DATA_DIR

SCHEMA_VERSION = "v4"


class ApiCache:
    def __init__(self, path: Path = CACHE_DB) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._init()

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.path, timeout=5)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init(self) -> None:
        try:
            with self._conn() as conn:
                conn.execute(
                    "CREATE TABLE IF NOT EXISTS api_cache ("
                    " key TEXT PRIMARY KEY, payload TEXT NOT NULL,"
                    " built_at TEXT NOT NULL, data_version TEXT NOT NULL)"
                )
                conn.execute("CREATE INDEX IF NOT EXISTS idx_cache_built ON api_cache(built_at)")
        except sqlite3.Error:
            pass

    def data_version(self) -> str:
        """数据版本 = 数据日期 + 文件 mtime；文件变化即缓存失效。"""
        files = []
        for pattern in ("*.parquet", "state.sqlite"):
            files.extend(DATA_DIR.glob(pattern))
        mtimes = []
        for f in files:
            try:
                mtimes.append(f.stat().st_mtime)
            except OSError:
                continue
        stamp = max(mtimes) if mtimes else 0
        return f"{SCHEMA_VERSION}:{int(stamp)}"

    def get(self, key: str) -> dict | None:
        version = self.data_version()
        try:
            with self._conn() as conn:
                row = conn.execute(
                    "SELECT payload FROM api_cache WHERE key=? AND data_version=?",
                    (key, version),
                ).fetchone()
            if not row:
                return None
            return json.loads(row[0])
        except (sqlite3.Error, json.JSONDecodeError):
            return None

    def put(self, key: str, payload: dict) -> None:
        version = self.data_version()
        try:
            with self._conn() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO api_cache(key,payload,built_at,data_version) VALUES(?,?,?,?)",
                    (key, json.dumps(payload, ensure_ascii=False, default=str),
                     datetime.now().isoformat(timespec="seconds"), version),
                )
                conn.execute("DELETE FROM api_cache WHERE data_version<>?", (version,))
        except sqlite3.Error:
            pass

    def clear(self) -> None:
        try:
            with self._conn() as conn:
                conn.execute("DELETE FROM api_cache")
        except sqlite3.Error:
            pass


cache = ApiCache()
