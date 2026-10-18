/* 总览（组合指挥台）：#/overview */
(function () {
  "use strict";
  const V2 = (window.V2 = window.V2 || {});
  const fmt = V2.fmt;
  const ui = V2.ui;

  const STATUS_MAP = { open: "持有中", closed: "已结清", watching: "观察" };
  const KIND_CN = { valuation: "估值", assumption: "假设", thesis: "逻辑", price: "价格" };

  let state = { master: null, meta: null };

  function benchmarkText(b) {
    const chg = b.pct_20d !== undefined && b.pct_20d !== null ? b.pct_20d : b.chg_20d;
    return fmt.esc(b.name) + " " +
      '<span class="' + fmt.signClass(chg) + '">' + fmt.pctSigned(chg) + "</span>";
  }

  function bandHTML(master) {
    const s = master.summary || {};
    const pnl = Number(s.weighted_pnl);
    const bench = master.benchmark || {};
    return (
      '<section class="ov-band" aria-label="组合摘要">' +
      '<dl class="ov-stats">' +
      '<div class="ov-stat"><dt>总仓位</dt><dd class="num">' + fmt.num(s.total_weight, 1) +
      '<span class="unit">%</span></dd><p class="ov-stat-sub">' + (s.positions || 0) + " 只持仓 · " +
      (s.chains || 5) + " 条链</p></div>" +
      '<div class="ov-stat"><dt>加权浮盈</dt><dd class="num ' + (pnl > 0 ? "up" : pnl < 0 ? "down" : "") + '">' +
      (pnl > 0 ? "+" : "") + fmt.num(s.weighted_pnl, 1) + '<span class="unit">%</span></dd>' +
      '<p class="ov-stat-sub">按仓位加权</p></div>' +
      '<div class="ov-stat"><dt>逻辑卡</dt><dd class="num">' + (s.theses || 0) +
      '<span class="unit">张</span></dd><p class="ov-stat-sub">覆盖 ' +
      (master.chains || []).filter(function (c) { return c.theses > 0; }).length + " 条链</p></div>" +
      '<div class="ov-stat"><dt>待办</dt><dd class="num' + ((s.alerts || 0) > 0 ? " has-todo" : "") + '">' +
      (s.alerts || 0) + '<span class="unit">条</span></dd><p class="ov-stat-sub">其中高危 ' +
      (s.high_alerts || 0) + " 条</p></div>" +
      '<div class="ov-stat"><dt>基准（20 日）</dt><dd class="num">' + benchmarkText(bench) +
      '</dd><p class="ov-stat-sub">' + fmt.price(bench.close) + " · 截至 " + fmt.esc(master.as_of || "") +
      "</p></div>" +
      "</dl></section>"
    );
  }

  function quadrantHTML(master) {
    return (
      '<div class="ov-main">' +
      '<figure class="ov-quadrant">' +
      '<figcaption><span>行业象限</span>' +
      '<span class="unit">x = 估值分位 · y = 相对强弱（60 日，pp）· 气泡 = 持仓权重</span></figcaption>' +
      '<div class="chart-body ov-quadrant-body" id="quadrant-chart"></div>' +
      '<p class="caption">accent 表示待办 ≥ 3 条；点击气泡或行业表行进入对应产业链。</p>' +
      "</figure>" +
      '<aside class="ov-side">' +
      '<section class="ov-todos">' +
      '<div class="section-head"><h2 class="section-h2">待办</h2>' +
      '<span class="caption">全部链 · 前 6 条可处理</span></div>' +
      inboxHTML(master) +
      "</section>" +
      "</aside>" +
      "</div>"
    );
  }

  function chainTableHTML(chains) {
    if (!chains || !chains.length) {
      return ui.emptyHTML("没有产业链数据。", "");
    }
    const head =
      "<thead><tr>" +
      '<th class="t-left">产业链</th>' +
      '<th class="t-right">标的数</th>' +
      '<th class="t-right">估值分位</th>' +
      '<th class="t-right">20 日</th>' +
      '<th class="t-right">60 日</th>' +
      '<th class="t-right">相对强弱</th>' +
      '<th class="t-right">持仓</th>' +
      '<th class="t-right">逻辑</th>' +
      '<th class="t-right">待办</th>' +
      "</tr></thead>";
    const body = chains.map(function (c) {
      const label = c.valuation_label || fmt.basisLabel(c.valuation_basis);
      return (
        '<tr class="chain-row" data-chain="' + fmt.esc(c.id) + '">' +
        '<td class="t-left"><span class="chain-name">' + fmt.esc(c.name) + "</span>" +
        '<span class="chain-short">' + fmt.esc(c.short) + " · " + label + " 口径</span></td>" +
        '<td class="t-right num">' + (c.stocks || 0) + "</td>" +
        '<td class="t-right ' + fmt.toneClass(c.median_pct, "pct_low_good") + '">' + fmt.ratioPct(c.median_pct) + ui.meter(c.median_pct) + "</td>" +
        '<td class="t-right ' + fmt.signClass(c.pct_20d) + '">' + fmt.pctSigned(c.pct_20d, 1) + "</td>" +
        '<td class="t-right ' + fmt.signClass(c.pct_60d) + '">' + fmt.pctSigned(c.pct_60d, 1) + "</td>" +
        '<td class="t-right ' + fmt.signClass(c.relative_60d) + '">' +
        (c.relative_60d > 0 ? "+" : "") + fmt.num(c.relative_60d, 1) + " pp</td>" +
        '<td class="t-right num">' + (c.holdings_weight ? fmt.weight(c.holdings_weight) : "—") + "</td>" +
        '<td class="t-right num">' + (c.theses || "—") + "</td>" +
        '<td class="t-right num' + (c.alerts ? " has-todo" : "") + '">' + (c.alerts || "—") + "</td>" +
        "</tr>"
      );
    }).join("");
    return '<table class="stocks chains-table">' + head + "<tbody>" + body + "</tbody></table>";
  }

  function positionsHTML(master) {
    const rows = master.positions || [];
    if (!rows.length) {
      return ui.emptyHTML("还没有跨链持仓。去任意产业链的标的活文档里建立逻辑，再记录第一次建仓。",
        ' <a class="btn-text" href="#/chain/whites">去白电产业链</a>');
    }
    const head =
      "<thead><tr>" +
      '<th class="t-left">标的</th>' +
      '<th class="t-left">链</th>' +
      '<th class="t-right">权重</th>' +
      '<th class="t-right">成本</th>' +
      '<th class="t-right">现价</th>' +
      '<th class="t-right">浮盈</th>' +
      '<th class="t-right">状态</th>' +
      "</tr></thead>";
    const body = rows.map(function (p) {
      return (
        '<tr class="position-row" data-symbol="' + fmt.esc(p.symbol) + '">' +
        '<td class="t-left"><span class="stock-name">' + fmt.esc(p.name) + "</span>" +
        '<span class="stock-sym">' + fmt.esc(p.symbol) + "</span></td>" +
        '<td class="t-left">' + fmt.esc(p.chain_name) + "</td>" +
        '<td class="t-right num">' + fmt.weight(p.weight_pct) + "</td>" +
        '<td class="t-right num">' + fmt.price(p.entry_price) + "</td>" +
        '<td class="t-right num">' + fmt.price(p.price) + "</td>" +
        '<td class="t-right ' + fmt.signClass(p.pnl_pct) + '">' + fmt.pctSigned(p.pnl_pct, 1) + "</td>" +
        '<td class="t-right">' + fmt.esc(STATUS_MAP[p.status] || p.status || "—") + "</td>" +
        "</tr>"
      );
    }).join("");
    return '<table class="stocks positions-table">' + head + "<tbody>" + body + "</tbody></table>";
  }

  function inboxHTML(master) {
    const items = (master.inbox || []).slice(0, 6);
    if (!items.length) {
      const first = ((master.chains || [])[0] || {}).id || "whites";
      return ui.emptyHTML("暂无待办。去产业链里写逻辑与假设，触发条件会在这里汇总。",
        ' <a class="btn-text" href="#/chain/' + encodeURIComponent(first) + '">进入产业链</a>');
    }
    return (
      '<div class="ov-inbox">' + items.map(function (a) {
        return (
          '<div class="inbox-row" data-alert-id="' + fmt.esc(a.id) + '">' +
          '<span class="inbox-name">' + fmt.esc(a.name) + " · " + fmt.esc(a.chain_name || "") + "</span>" +
          '<button type="button" class="btn-text" data-resolve>标记已处理</button>' +
          '<span class="inbox-meta">' + fmt.esc(KIND_CN[a.kind] || a.kind) + " · " + fmt.esc(a.message) + "</span>" +
          "</div>"
        );
      }).join("") + "</div>" +
      (master.inbox.length > 6
        ? '<p class="caption ov-more">另有 ' + (master.inbox.length - 6) + " 条，去月度体检处理。</p>"
        : "")
    );
  }

  function upcomingHTML(master) {
    const rows = (master.upcoming || []).slice(0, 6);
    if (!rows.length) return ui.emptyHTML("未来一个月没有到期假设。", "");
    return '<div class="ov-list">' + rows.map(function (r) {
      const cls = r.days_left < 0 ? "overdue" : r.days_left <= 7 ? "soon" : "";
      const text = r.days_left < 0 ? "逾期 " + Math.abs(r.days_left) + " 天"
        : r.days_left === 0 ? "今天到期" : r.days_left + " 天后";
      return (
        '<div class="ov-row">' +
        '<a class="ov-row-name" href="#/stock/' + encodeURIComponent(r.symbol) + '">' + fmt.esc(r.name) + "</a>" +
        '<span class="ov-row-days ' + cls + '">' + text + "</span>" +
        '<span class="ov-row-meta">' + fmt.esc(r.chain_name || "") + " · " + fmt.esc(r.statement) +
        " · 截止 " + fmt.esc(fmt.date(r.deadline)) + "</span></div>"
      );
    }).join("") + "</div>";
  }

  function decisionsHTML(master) {
    const rows = (master.decisions || []).slice(0, 6);
    if (!rows.length) return ui.emptyHTML("本月还没有决策记录。", "");
    return '<div class="ov-list">' + rows.map(function (d) {
      return (
        '<div class="ov-row">' +
        '<a class="ov-row-name" href="#/stock/' + encodeURIComponent(d.symbol) + '">' +
        fmt.esc(d.name || d.symbol) + "</a>" +
        '<span class="ov-row-days">' + fmt.action(d.action) + "</span>" +
        '<span class="ov-row-meta">' + fmt.esc(d.chain_name || "") + " · " +
        fmt.esc(d.logic || "") + " · " + fmt.esc(fmt.timeOnly(d.created_at)) + "</span></div>"
      );
    }).join("") + "</div>";
  }

  function viewHTML(master, meta) {
    const asOf = master.as_of || (meta && meta.as_of) || "";
    const count = (master.chains || []).length;
    return (
      '<header class="ov-head">' +
      '<p class="meta-line"><span>数据截至 ' + fmt.esc(asOf) + "</span>" +
      '<span class="dot">' + count + " 条产业链 · " + ((master.summary || {}).stocks || 0) + " 只标的</span>" +
      '<span class="dot">基准 ' + benchmarkText(master.benchmark || {}) + "</span></p>" +
      '<h1 class="display">五链总览</h1>' +
      '<p class="lede">五条产业链摆在一起看：哪条便宜、哪条在走强、仓位压在哪里、哪些判断该验证了。总览只读，判断去链里做。</p>' +
      "</header>" +
      bandHTML(master) +
      quadrantHTML(master) +
      '<section class="ov-section">' +
      '<div class="section-head"><h2 class="section-h2">行业表</h2>' +
      '<span class="caption">各链中位读数 · 点击行进入产业链</span></div>' +
      '<div class="table-wrap">' + chainTableHTML(master.chains) + "</div>" +
      "</section>" +
      '<div class="ov-lower">' +
      '<section class="ov-section">' +
      '<div class="section-head"><h2 class="section-h2">跨链持仓</h2>' +
      '<span class="caption">共 ' + ((master.positions || []).length) + " 只 · 点击进入活文档</span></div>" +
      '<div class="table-wrap">' + positionsHTML(master) + "</div>" +
      "</section>" +
      '<aside class="ov-side ov-lower-side">' +
      '<section class="ov-section">' +
      '<div class="section-head"><h2 class="section-h2">到期假设</h2>' +
      '<span class="caption">30 天内</span></div>' + upcomingHTML(master) + "</section>" +
      '<section class="ov-section">' +
      '<div class="section-head"><h2 class="section-h2">本月决策</h2>' +
      '<span class="caption">全部产业链</span></div>' + decisionsHTML(master) + "</section>" +
      "</aside>" +
      "</div>"
    );
  }

  function bind(container, master) {
    container.querySelectorAll("tr[data-chain]").forEach(function (row) {
      row.addEventListener("click", function () {
        location.hash = "#/chain/" + encodeURIComponent(row.getAttribute("data-chain"));
      });
    });
    container.querySelectorAll("tr[data-symbol]").forEach(function (row) {
      row.addEventListener("click", function () {
        location.hash = "#/stock/" + encodeURIComponent(row.getAttribute("data-symbol"));
      });
    });
    const inboxHost = container.querySelector(".ov-todos");
    if (inboxHost) {
      inboxHost.addEventListener("click", async function (ev) {
        const btn = ev.target.closest("[data-resolve]");
        if (!btn) return;
        const row = btn.closest(".inbox-row");
        const id = row.getAttribute("data-alert-id");
        btn.disabled = true;
        try {
          await V2.api.post("/api/alerts/" + encodeURIComponent(id) + "/resolve", {});
          row.remove();
          master.summary.alerts = Math.max(0, (master.summary.alerts || 0) - 1);
          const band = container.querySelector(".ov-stat:nth-child(4) dd");
          if (band) band.innerHTML = master.summary.alerts + '<span class="unit">条</span>';
          if (!inboxHost.querySelector(".inbox-row")) {
            inboxHost.innerHTML = ui.emptyHTML("没有待处理提醒。", "");
          }
        } catch (err) {
          btn.disabled = false;
          const errLine = document.createElement("p");
          errLine.className = "error-line";
          errLine.textContent = "处理失败：" + err.message;
          row.appendChild(errLine);
        }
      });
    }
    const chart = container.querySelector("#quadrant-chart");
    if (chart) {
      V2.charts.quadrant(chart, master.chains || [], function (chainId) {
        location.hash = "#/chain/" + encodeURIComponent(chainId);
      });
    }
  }

  async function render(container, ctx) {
    container.innerHTML = '<p class="loading">载入总览…</p>';
    let master;
    let meta = ctx.meta;
    try {
      const results = await Promise.all([
        V2.api.get("/api/master"),
        meta ? Promise.resolve(meta) : V2.api.get("/api/meta"),
      ]);
      master = results[0];
      meta = results[1];
    } catch (err) {
      container.innerHTML =
        '<header class="ov-head"><p class="meta-line">总览</p><h1 class="display">五链总览</h1></header>' +
        ui.errorHTML(err.message);
      return;
    }
    if (!master || !master.chains) {
      container.innerHTML = ui.errorHTML("总览数据为空。", false);
      return;
    }
    state = { master: master, meta: meta };
    container.innerHTML = viewHTML(master, meta);
    bind(container, master);
    if (ctx.onTitle) ctx.onTitle("五链总览");
  }

  V2.views = V2.views || {};
  V2.views.overview = { render: render };
})();
