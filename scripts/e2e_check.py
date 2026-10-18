"""v3 端到端交互验证（Playwright + 本机 Edge，真实后端 :8000）。

流程：总览 → 行业表跳转光伏链 → 通威活文档（逻辑/假设/买入）→ 月度体检（按链过滤/保存）。
"""
from __future__ import annotations

from pathlib import Path

import requests
from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
SHOTS = Path(__file__).resolve().parents[1] / "docs" / "screenshots"
SHOTS.mkdir(parents=True, exist_ok=True)


def log(msg: str) -> None:
    print(f"[e2e] {msg}", flush=True)


def main() -> int:
    failures: list[str] = []
    console_errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(viewport={"width": 1680, "height": 1300})
        page.on("pageerror", lambda e: failures.append(f"页面 JS 异常: {e}"))
        page.on("console", lambda m: m.type == "error" and console_errors.append(m.text[:200]))

        # ---------------- 总览 ----------------
        log("打开总览 …")
        page.goto(f"{BASE}/#/overview", wait_until="networkidle", timeout=60000)
        page.wait_for_selector(".chain-row", timeout=30000)
        rows = page.locator(".chain-row").count()
        if rows != 5:
            failures.append(f"行业表 {rows} 条，期望 5")
        if "五链总览" not in page.inner_text("main"):
            failures.append("总览标题缺失")
        page.screenshot(path=str(SHOTS / "e2e_overview.png"), full_page=True)

        # ---------------- 单链 ----------------
        log("点击行业表进入光伏 …")
        page.locator('.chain-row[data-chain="pv"]').click()
        page.wait_for_url("**/#/chain/pv", timeout=15000)
        page.wait_for_selector(".stock-row", timeout=30000)
        if "光伏能源" not in page.inner_text("main"):
            failures.append("光伏链标题缺失")
        if page.locator(".stock-row").count() != 40:
            failures.append(f"光伏链标的 {page.locator('.stock-row').count()} 只，期望 40")
        if "分节点指标" not in page.inner_text("main"):
            failures.append("单链页缺少分节点指标")
        if "分节点估值与质量" not in page.inner_text("main"):
            failures.append("单链页缺少分节点估值与质量")
        if "外部代理" not in page.inner_text("main"):
            failures.append("单链页缺少外部代理")
        page.screenshot(path=str(SHOTS / "e2e_chain_pv.png"), full_page=True)

        # ---------------- 活文档 ----------------
        log("进入通威活文档 …")
        page.locator('.stock-row[data-symbol="600438.SH"]').click()
        page.wait_for_url("**/#/stock/600438.SH", timeout=15000)
        page.wait_for_selector("#thesis-form", timeout=30000)
        if "通威股份" not in page.inner_text("main"):
            failures.append("活文档标题不是通威股份")
        if "主营构成" not in page.inner_text("main"):
            failures.append("活文档缺少主营构成")
        if "总市值" not in page.inner_text("main"):
            failures.append("活文档缺少扩展估值/质量指标")
        if "区间最高" not in page.inner_text("main"):
            failures.append("收盘价图缺少最高/最低虚线标注")

        page.fill('#thesis-form input[name="title"]', "硅料价格触底，成本优势等待反转")
        page.fill('#thesis-form textarea[name="core_logic"]',
                  "硅料价格处于周期底部，行业现金成本支撑；公司多晶硅成本领先，若需求边际改善则盈利弹性大。")
        page.fill('#thesis-form textarea[name="valuation_view"]', "PB 分位 18% 附近，按周期底部区间对待。")
        page.fill('#thesis-form input[name="horizon"]', "6-12 个月")
        page.locator("#thesis-form button[type=submit]").click()
        page.wait_for_timeout(1800)
        if "已保存" not in page.inner_text("#thesis-state"):
            failures.append("逻辑卡保存失败")
        else:
            log("逻辑卡已保存")

        log("新增假设 …")
        page.click("#assumption-toggle")
        page.fill('#assumption-form input[name="statement"]', "多晶硅价格连续两个月回升")
        page.fill('#assumption-form input[name="metric"]', "多晶硅致密料价格")
        page.fill('#assumption-form input[name="target"]', "≥ 40 元/kg")
        page.fill('#assumption-form input[name="deadline"]', "2026-11-30")
        page.locator("#assumption-form button[type=submit]").click()
        page.wait_for_timeout(1500)
        if "多晶硅价格连续两个月回升" not in page.inner_text("#assumption-list"):
            failures.append("假设未加入清单")
        else:
            log("假设已加入")

        log("记录买入决策 …")
        page.select_option('#decision-form select[name="action"]', "buy")
        page.fill('#decision-form input[name="weight_pct"]', "4")
        page.fill('#decision-form textarea[name="logic"]', "PB 分位低位，先建 4% 观察仓。")
        page.fill('#decision-form textarea[name="kill_switch"]', "若硅料价格跌破现金成本且持续 2 个月，退出。")
        page.locator("#decision-form button[type=submit]").click()
        page.wait_for_timeout(2000)
        timeline = page.inner_text("#decision-timeline")
        if "建仓" not in timeline and "买入" not in timeline:
            failures.append("决策时间线未出现建仓记录")
        if "持有" not in page.inner_text("#sub-status"):
            failures.append("决策后状态未变为持有")
        page.screenshot(path=str(SHOTS / "e2e_stock_pv.png"), full_page=True)

        # 月度体检只包含已加星标的；为通威加星
        requests.post(f"{BASE}/api/star", json={"symbol": "600438.SH", "active": True}, timeout=20)

        # ---------------- 月度体检 ----------------
        log("打开月度体检并按链过滤 …")
        page.goto(f"{BASE}/#/review?chain=pv", wait_until="networkidle", timeout=60000)
        page.wait_for_selector("#review-md", timeout=30000)
        text = page.inner_text("main")
        if "月度体检" not in text or "光伏能源" not in text:
            failures.append("月度体检缺少光伏链")
        if "通威股份" not in text:
            failures.append("月度体检缺少通威的逻辑/假设")
        page.fill("#review-md", "# 2026-10 光伏复盘\n\n通威建 4% 观察仓，等待硅料价格验证。")
        page.select_option("#review-chain", "pv")
        page.wait_for_timeout(800)
        page.click("#review-save")
        page.wait_for_timeout(1500)
        if "已保存" not in page.inner_text("#review-state"):
            failures.append("月报保存失败")
        else:
            log("月报已保存")
        page.screenshot(path=str(SHOTS / "e2e_review_pv.png"), full_page=True)

        # ---------------- 多股对比 ----------------
        log("打开多股对比 …")
        page.goto(f"{BASE}/#/compare?chain=pv&node=silicon&symbols=600438.SH,688303.SH,600089.SH", wait_until="networkidle", timeout=60000)
        page.wait_for_selector(".compare-table", timeout=30000)
        if "多股对比" not in page.inner_text("main"):
            failures.append("多股对比标题缺失")
        if "硅料" not in page.inner_text("main"):
            failures.append("多股对比缺少同节点说明")
        if page.locator(".compare-table tbody tr").count() != 3:
            failures.append("多股对比表格不是 3 行")
        page.screenshot(path=str(SHOTS / "e2e_compare.png"), full_page=True)

        browser.close()

    if console_errors:
        log(f"控制台错误 {len(console_errors)} 条（前 3）：")
        for err in console_errors[:3]:
            log("  " + err)
    if failures:
        log("失败项：")
        for f in failures:
            log(" - " + f)
        return 1
    log("全部通过 ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
