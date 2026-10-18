"""五链数据刷新 Skill：按 TTL 跑过期数据集，更新 manifest，热加载缓存。

用法：
  python _skills/data-refresh/scripts/refresh.py --status
  python _skills/data-refresh/scripts/refresh.py
  python _skills/data-refresh/scripts/refresh.py --force --datasets chains,macro
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "data" / "fetch_manifest.json"
BASE = "http://127.0.0.1:8000"

DATASETS = {
    "chains": {"cmd": ["-m", "data_engine.fetch_chains", "--workers", "6"], "ttl_days": 1, "label": "行情/财务/估值/舆情"},
    "valuation_ext": {"cmd": ["-m", "data_engine.fetch_valuation_ext", "--workers", "8"], "ttl_days": 1, "label": "估值/分红/预测"},
    "financial_ext": {"cmd": ["-m", "data_engine.fetch_financial_ext"], "ttl_days": 7, "label": "三表/财务指标"},
    "business": {"cmd": ["-m", "data_engine.fetch_business", "--workers", "8"], "ttl_days": 30, "label": "主营构成"},
    "chips": {"cmd": ["-m", "data_engine.fetch_chips"], "ttl_days": 7, "label": "股东户数"},
    "macro": {"cmd": ["-m", "data_engine.fetch_macro"], "ttl_days": 1, "label": "期货/宏观"},
}


def load_manifest() -> dict:
    if MANIFEST.exists():
        try:
            return json.loads(MANIFEST.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"datasets": {}, "updated_at": None}


def save_manifest(m: dict) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    m["updated_at"] = datetime.now().isoformat(timespec="seconds")
    MANIFEST.write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")


def stale(name: str, m: dict) -> bool:
    last = (m.get("datasets", {}).get(name) or {}).get("last_run")
    if not last:
        return True
    try:
        dt = datetime.fromisoformat(last)
    except ValueError:
        return True
    return datetime.now() - dt > timedelta(days=DATASETS[name]["ttl_days"])


def post(path: str, timeout: int = 30) -> bool:
    try:
        req = urllib.request.Request(BASE + path, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="五链数据刷新")
    parser.add_argument("--status", action="store_true", help="只显示状态，不抓取")
    parser.add_argument("--force", action="store_true", help="忽略 TTL，全部重跑")
    parser.add_argument("--datasets", default="", help="逗号分隔：chains,valuation_ext,...")
    parser.add_argument("--no-reload", action="store_true", help="不调用本地 API reload/warm")
    args = parser.parse_args()

    m = load_manifest()
    selected = [s.strip() for s in args.datasets.split(",") if s.strip()] or list(DATASETS)
    unknown = [s for s in selected if s not in DATASETS]
    if unknown:
        print("未知数据集:", ", ".join(unknown))
        return 2

    print(f"manifest: {MANIFEST}")
    for name in selected:
        last = (m.get("datasets", {}).get(name) or {}).get("last_run") or "从未"
        due = stale(name, m)
        flag = "需更新" if due else "新鲜"
        print(f"  {name:14s} {DATASETS[name]['label']:12s} 上次 {last:20s} {flag}")

    if args.status:
        return 0

    todo = [n for n in selected if args.force or stale(n, m)]
    if not todo:
        print("\n没有过期数据集。")
    else:
        print(f"\n开始刷新 {len(todo)} 个数据集 …")
        started = time.time()
        for name in todo:
            cmd = [sys.executable] + DATASETS[name]["cmd"]
            print(f"\n[{name}] {' '.join(cmd[1:])}", flush=True)
            t0 = time.time()
            code = subprocess.call(cmd, cwd=str(ROOT))
            took = round(time.time() - t0, 1)
            m.setdefault("datasets", {})[name] = {
                "last_run": datetime.now().isoformat(timespec="seconds"),
                "ok": code == 0,
                "seconds": took,
            }
            save_manifest(m)
            print(f"[{name}] {'ok' if code == 0 else 'FAIL'} {took}s", flush=True)
        print(f"\n刷新结束，共 {round(time.time() - started, 1)}s")

    if not args.no_reload:
        if post("/api/reload"):
            print("API reload ok")
            if post("/api/warm"):
                print("缓存预热已触发")
        else:
            print("本地服务未运行，跳过 reload/warm")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
