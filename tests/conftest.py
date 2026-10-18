"""pytest 公共夹具：临时状态库 + FastAPI TestClient。"""
from __future__ import annotations

import contextlib
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import db as dbm  # noqa: E402


@pytest.fixture()
def client(tmp_path, monkeypatch):
    dbfile = tmp_path / "state.sqlite"
    real_db = dbm.db

    @contextlib.contextmanager
    def patched(db_path=None):
        with real_db(dbfile) as conn:
            yield conn

    monkeypatch.setattr(dbm, "db", patched)
    dbm.init()

    from fastapi.testclient import TestClient

    from app.server import app

    with TestClient(app) as c:
        yield c
