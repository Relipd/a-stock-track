/* 单链视图：#/chain/{chainId} */
(function () {
  "use strict";
  const V2 = (window.V2 = window.V2 || {});
  const fmt = V2.fmt;
  const ui = V2.ui;

  let state = { overview: null, meta: null, chain: null, chainId: "whites", activeNode: "" };

  function chainMeta(overview, chainId, meta) {
    if (overview && overview.chain) return overview.chain;
    const fromMeta = ((meta && meta.chains) || []).find(function (c) { return c.id === chainId; });
    if (fromMeta) {
      return Object.assign({ valuation_label: fmt.basisLabel(fromMeta.valuation_basis) }, fromMeta);
    }
    return {
      id: chainId, name: chainId, short: chainId, description: "",
      valuation_basis: "pe", valuation_label: "PE", stocks: 0, nodes: 0, node_list: [],
    };
  }

  function benchLine(bench) {
    const b = bench || {};
    const chg = b.pct_20d !== undefined && b.pct_20d !== null ? b.pct_20d : b.chg_20d;
    const pieces = [];
    if (b.name) pieces.push(fmt.esc(b.name));
    if (b.close !== undefined && b.close !== null) pieces.push(fmt.price(b.close));
    if (chg !== undefined && chg !== null) {
      pieces.push('<span class="' + fmt.signClass(chg) + '">' + fmt.pctSigned(chg) + "</span>");
    }
    return pieces.join(" ");
  }

  function headFigures(chain, breadth) {
    const up = breadth ? breadth.up_20d : 0;
    const down = breadth ? breadth.down_20d : 0;
    const rel = Number(chain.relative_60d);
    return (
      '<dl class="head-figures head-figures-4">' +
      '<div class="head-figure"><dt>20 日涨跌</dt><dd class="num">' + up +
      '<span class="unit">涨</span> / ' + down + '<span class="unit">跌</span></dd></div>' +
      '<div class="head-figure"><dt>' + fmt.esc(chain.valuation_label || fmt.basisLabel(chain.valuation_basis)) +
      ' 分位中位</dt><dd class="num ' + fmt.toneClass(chain.median_pct, "pct_low_good") + '">' + fmt.ratioPct(chain.median_pct) + "</dd></div>" +
      '<div class="head-figure"><dt>相对强弱（60 日）</dt><dd class="num ' + fmt.signClass(rel) + '">' +
      (rel > 0 ? "+" : "") + fmt.num(rel, 1) + '<span class="unit">pp</span></dd></div>' +
      '<div class="head-figure"><dt>极端估值</dt><dd class="num">' + (chain.high_pct || 0) +
      '<span class="unit">高</span> / ' + (chain.low_pct || 0) + '<span class="unit">低</span></dd></div>' +
      "</dl>"
    );
  }

  function readsHTML(reads) {
    const list = reads || [];
    if (!list.length) return ui.emptyHTML("暂无产业链读数。", "");
    return list.slice(0, 6).map(function (r) {
      return (
        '<li class="read">' +
        '<p class="read-label">' + fmt.esc(r.label) + "</p>" +
        '<p class="read-value num ' + (r.tone || "") + '">' + fmt.esc(r.value) + "</p>" +
        '<p class="read-note">' + fmt.esc(r.note || "") + "</p>" +
        "</li>"
      );
    }).join("");
  }

  function deltaCell(value, unit, direction) {
    if (value === null || value === undefined) return "";
    const n = Number(value);
    return '<span class="metric-delta ' + fmt.toneClass(n, direction || "up") + '">Δ ' +
      (n > 0 ? "+" : "") + fmt.num(n, 1) + (unit || "") + "</span>";
  }

  function qualityTableHTML(overview) {
    const nodes = overview.nodes || [];
    if (!nodes.length) return "";
    const rows = nodes.map(function (n) {
      const fcf = n.median_fcf_yield;
      const fpe = n.median_forward_pe;
      const div = n.median_dividend_yield;
      const ccc = n.median_ccc;
      const roic = n.median_roic;
      const overseas = n.median_overseas_ratio;
      return (
        "<tr>" +
        '<td class="t-left"><span class="stock-name">' + fmt.esc(n.name) + "</span></td>" +
        '<td class="t-right num">' + (roic === null || roic === undefined ? "—" : fmt.num(roic, 1) + "%") + "</td>" +
        '<td class="t-right num">' + (ccc === null || ccc === undefined ? "—" : fmt.num(ccc, 0) + " 天") + "</td>" +
        '<td class="t-right num">' + (fcf === null || fcf === undefined ? "—" : '<span class="' + fmt.toneClass(fcf, "up") + '">' + fmt.num(fcf, 2) + "%</span>") + "</td>" +
        '<td class="t-right num">' + (fpe === null || fpe === undefined ? "—" : fmt.num(fpe, 1) + "x") + "</td>" +
        '<td class="t-right num">' + (div === null || div === undefined ? "—" : fmt.num(div, 2) + "%") + "</td>" +
        '<td class="t-right num">' + (overseas === null || overseas === undefined ? "—" : fmt.ratioPct(overseas)) + "</td>" +
        "</tr>"
      );
    }).join("");
    return (
      '<section class="stocks-section">' +
      '<div class="section-head"><h2 class="section-h2">分节点估值与质量</h2>' +
      '<p class="caption">ROIC / CCC / FCF 收益率 / 远期 PE / 股息率 / 海外收入，均为现有数据计算</p></div>' +
      '<div class="table-wrap"><table class="stocks node-quality-table"><thead><tr>' +
      '<th class="t-left">节点</th><th class="t-right">ROIC</th><th class="t-right">CCC</th>' +
      '<th class="t-right">FCF 收益率</th><th class="t-right">远期 PE</th>' +
      '<th class="t-right">股息率</th><th class="t-right">海外收入</th>' +
      "</tr></thead><tbody>" + rows + "</tbody></table></div></section>"
    );
  }

  function proxiesHTML(proxies) {
    const list = proxies || [];
    if (!list.length) return "";
    return (
      '<section class="proxy-strip"><div class="section-head"><h2 class="section-h2">外部代理</h2>' +
      '<p class="caption">期货/宏观，只作景气代理，不是真实行业 KPI；按各自最新日期</p></div>' +
      '<div class="proxy-grid">' + list.map(function (p) {
        const chg = p.chg_20d === null || p.chg_20d === undefined ? "" :
          '<span class="proxy-chg ' + fmt.signClass(p.chg_20d) + '">20日 ' + fmt.pctSigned(p.chg_20d, 1) + "</span>";
        return '<div class="proxy-card"><p class="proxy-label">' + fmt.esc(p.label) + "</p>" +
          '<p class="proxy-value num">' + fmt.num(p.value, p.freq === "D" ? 0 : 2) +
          '<span class="unit">' + fmt.esc(p.unit || "") + "</span></p>" +
          '<p class="proxy-date">' + fmt.esc(p.date || "") + chg + "</p></div>";
      }).join("") + "</div></section>"
    );
  }

  function nodeMetricsHTML(overview, chain) {
    const nodes = overview.nodes || [];
    if (!nodes.length) return "";
    const label = chain.valuation_label || fmt.basisLabel(chain.valuation_basis);
    const rows = nodes.map(function (n) {
      return (
        "<tr>" +
        '<td class="t-left"><span class="stock-name">' + fmt.esc(n.name) + "</span>" +
        '<span class="chain-short">' + (n.stocks || 0) + " 只 · " + fmt.role(n.role) + "</span></td>" +
        '<td class="t-right num">' + (n.median_gross_margin === null ? "—" : fmt.num(n.median_gross_margin, 1) + "%") +
        deltaCell(n.gross_margin_delta, "pp", "up") + "</td>" +
        '<td class="t-right num">' + (n.median_inventory_days === null ? "—" : fmt.num(n.median_inventory_days, 0) + " 天") +
        deltaCell(n.inventory_days_delta, " 天", "inverse") + "</td>" +
        '<td class="t-right num">' + (n.median_revenue_yoy === null ? "—" : '<span class="' + fmt.signClass(n.median_revenue_yoy) + '">' + fmt.pctSigned(n.median_revenue_yoy, 1) + "</span>") +
        '<span class="metric-delta ' + fmt.signClass(n.median_profit_yoy) + '">净利 ' + (n.median_profit_yoy === null ? "—" : fmt.pctSigned(n.median_profit_yoy, 1)) + "</span></td>" +
        '<td class="t-right num">' + (n.median_receivable_days === null ? "—" : fmt.num(n.median_receivable_days, 0) + " 天") + "</td>" +
        '<td class="t-right num">' + (n.median_debt_ratio === null ? "—" : fmt.num(n.median_debt_ratio, 1) + "%") + "</td>" +
        '<td class="t-right num">' + (n.median_roe === null ? "—" : fmt.num(n.median_roe, 1) + "%") + "</td>" +
        '<td class="t-right num ' + fmt.toneClass(n.median_pct, "pct_low_good") + '">' + fmt.ratioPct(n.median_pct) +
        '<span class="chain-short">' + fmt.ratioPct(n.p25_pct) + "–" + fmt.ratioPct(n.p75_pct) + "</span></td>" +
        '<td class="t-right num ' + fmt.signClass(n.pct_20d) + '">' + fmt.pctSigned(n.pct_20d, 1) + "</td>" +
        '<td class="t-right num ' + fmt.signClass(n.pct_60d) + '">' + fmt.pctSigned(n.pct_60d, 1) + "</td>" +
        "</tr>"
      );
    }).join("");
    return (
      '<section class="stocks-section">' +
      '<div class="section-head"><h2 class="section-h2">分节点指标</h2>' +
      '<p class="caption">按节点聚合，仅用现有行情/财务/估值数据；Δ4Q 为对 4 个季度前的变化</p></div>' +
      '<div class="table-wrap"><table class="stocks node-metrics-table"><thead><tr>' +
      '<th class="t-left">节点</th>' +
      '<th class="t-right">毛利率 / Δ4Q</th>' +
      '<th class="t-right">库存天数 / Δ4Q</th>' +
      '<th class="t-right">营收 / 净利增速</th>' +
      '<th class="t-right">应收天数</th>' +
      '<th class="t-right">负债率</th>' +
      '<th class="t-right">ROE</th>' +
      '<th class="t-right">' + fmt.esc(label) + ' 分位（P25–P75）</th>' +
      '<th class="t-right">20 日</th>' +
      '<th class="t-right">60 日</th>' +
      "</tr></thead><tbody>" + rows + "</tbody></table></div></section>"
    );
  }

  function distHTML(overview, chain) {
    const nodes = overview.nodes || [];
    const dist = overview.distribution || [];
    if (!nodes.length && !dist.length) return ui.emptyHTML("暂无估值分布数据。", "");
    const nodesById = {};
    nodes.forEach(function (n) { nodesById[n.id] = n; });
    const rows = dist.map(function (group) {
      const node = nodesById[group.node_id] || { median_pct: 0.5 };
      const dots = (group.points || []).map(function (p, i) {
        const pct = Math.max(0, Math.min(1, Number(p.pct)));
        const cls = pct > 0.8 ? " high" : pct < 0.2 ? " low" : "";
        const left = "min(max(" + (pct * 100).toFixed(1) + "%, 5px), calc(100% - 5px))";
        const bottom = 2 + (i % 2) * 7;
        return '<i class="dist-dot' + cls + '" style="left:' + left + ";bottom:" + bottom + 'px" title="' +
          fmt.esc(p.name) + " " + fmt.esc(p.symbol) + " · 分位 " + fmt.ratioPct(pct) + '"></i>';
      }).join("");
      return (
        '<div class="dist-row">' +
        '<span class="dist-label">' + fmt.esc(String(group.name || "").replace(" · ", "·")) + "</span>" +
        '<div class="dist-track">' +
        '<i class="dist-median" style="left:' + (Number(node.median_pct) * 100).toFixed(1) +
        '%" title="节点中位 ' + fmt.ratioPct(node.median_pct) + '"></i>' + dots + "</div>" +
        '<span class="dist-count">' + (group.points || []).length + "</span></div>"
      );
    }).join("");
    return rows +
      '<div class="dist-axis"><span></span><div class="ticks"><span>0%</span><span>25%</span>' +
      '<span>50%</span><span>75%</span><span>100%</span></div><span></span></div>' +
      '<p class="caption dist-note">圆点为个股近三年' + fmt.esc(chain.valuation_label || fmt.basisLabel(chain.valuation_basis)) +
      "分位，竖线为该节点中位；红色 &gt;80%，绿色 &lt;20%。全链中位 " +
      fmt.ratioPct(chain.median_pct) + "。</p>";
  }

  function tableHTML(overview, chain, activeNode) {
    const stocks = overview.stocks || [];
    const nodeList = chain.node_list || (overview.nodes || []);
    const metricById = {};
    (overview.nodes || []).forEach(function (n) { metricById[n.id] = n; });
    const label = chain.valuation_label || fmt.basisLabel(chain.valuation_basis);
    const basis = chain.valuation_basis || "pe";
    const groups = nodeList.filter(function (n) { return !activeNode || n.id === activeNode; });
    const head =
      "<thead><tr>" +
      '<th class="t-left">名称 / 代码</th>' +
      '<th class="c-role t-left">位置</th>' +
      "<th>现价</th>" +
      "<th>20 日</th>" +
      '<th class="c-60d">60 日</th>' +
      '<th class="c-pe">' + label + "</th>" +
      "<th>" + label + " 近三年分位</th>" +
      '<th class="c-gm">毛利率</th>' +
      '<th class="c-rev">营收增速</th>' +
      '<th class="c-inv">库存天数</th>' +
      "<th>我的状态</th>" +
      "<th>假设提醒</th>" +
      "</tr></thead>";
    const body = groups.map(function (node) {
      const members = stocks.filter(function (s) { return s.node_id === node.id; });
      const nm = metricById[node.id] || {};
      const nodeHead =
        '<tr class="node-row"><th colspan="12">' +
        '<span class="node-title">' + fmt.esc(node.name) + "</span>" +
        '<span class="node-sub">' + members.length + " 只 · 20 日中位 " + fmt.pctSigned(nm.pct_20d, 1) +
        " · " + label + " 分位中位 " + fmt.ratioPct(nm.median_pct) +
        " · 毛利率中位 " + fmt.num(nm.median_gross_margin, 1) + "%</span></th></tr>";
      if (!members.length) {
        return nodeHead + '<tr class="stock-row-empty"><td colspan="12" class="t-left muted">该节点数据待补齐。</td></tr>';
      }
      return nodeHead + members.map(function (s) {
        const stActive = s.thesis_status && s.thesis_status !== "watch" && s.thesis_status !== "closed";
        const alert = Number(s.assumption_alert || 0);
        const pct = fmt.basisPct(s, basis);
        return (
          '<tr class="stock-row" data-symbol="' + fmt.esc(s.symbol) + '">' +
          '<td class="t-left"><span class="stock-name"><a href="#/stock/' + encodeURIComponent(s.symbol) + '">' +
          fmt.esc(s.name) + "</a>" +
          '<button type="button" class="star-inline" data-star-toggle="' + fmt.esc(s.symbol) + '" data-starred="' +
          (s.star && s.star.starred ? "1" : "0") + '"' + (s.star && s.star.investment_star ? " disabled" : "") +
          ' title="' + (s.star && s.star.investment_star ? "投资加星中，不能撤星" : "加星/撤星") + '">' +
          (s.star && s.star.starred ? "★" : "☆") + "</button></span>" +
          '<span class="stock-sym">' + fmt.esc(s.symbol) + "</span></td>" +
          '<td class="c-role t-left">' + fmt.role(s.role) + "</td>" +
          '<td class="num">' + fmt.price(s.price) + "</td>" +
          '<td class="' + fmt.signClass(s.pct_20d) + '">' + fmt.pctSigned(s.pct_20d, 1) + "</td>" +
          '<td class="c-60d ' + fmt.signClass(s.pct_60d) + '">' + fmt.pctSigned(s.pct_60d, 1) + "</td>" +
          '<td class="c-pe">' + fmt.num(fmt.basisValue(s, basis), 1) + "</td>" +
          "<td>" + fmt.ratioPct(pct) + ui.meter(pct) + fmt.rank(s.ranks && s.ranks.valuation_pct) + "</td>" +
          '<td class="c-gm">' + fmt.num(s.gross_margin, 1) + "%" + fmt.rank(s.ranks && s.ranks.gross_margin) + "</td>" +
          '<td class="c-rev ' + fmt.signClass(s.revenue_yoy) + '">' + fmt.pctSigned(s.revenue_yoy, 1) +
          fmt.rank(s.ranks && s.ranks.revenue_yoy) + "</td>" +
          '<td class="c-inv">' + fmt.num(s.inventory_days, 1) + fmt.rank(s.ranks && s.ranks.inventory_days) + "</td>" +
          '<td><span class="st' + (stActive ? " st-active" : "") + '">' + fmt.status(s.thesis_status) + "</span></td>" +
          '<td class="cell-alert' + (alert ? " has-alert" : "") + '">' + (alert ? alert + " 条" : "—") + "</td>" +
          "</tr>"
        );
      }).join("");
    }).join("");
    return '<table class="stocks">' + head + "<tbody>" + body + "</tbody></table>";
  }

  function filtersHTML(chain, activeNode) {
    const nodeList = chain.node_list || [];
    const total = chain.stocks || 0;
    const items = ['<button type="button" class="filter-btn" data-filter="" aria-pressed="' +
      (!activeNode) + '">全部 ' + total + "</button>"];
    nodeList.forEach(function (n) {
      items.push('<button type="button" class="filter-btn" data-filter="' + fmt.esc(n.id) +
        '" aria-pressed="' + (activeNode === n.id) + '">' + fmt.esc(n.name) + "</button>");
    });
    return items.join("");
  }

  function diagramNodes(overview) {
    return (overview.nodes || []).map(function (n) {
      return {
        id: n.id, name: n.name, role: n.role, stocks: n.stocks,
        median_pct: n.median_pct, pct_20d: n.pct_20d, description: n.description,
      };
    });
  }

  function paintFigure(container) {
    const chain = state.chain;
    V2.diagram.render(container.querySelector("#chain-svg"), {
      nodes: diagramNodes(state.overview),
      nodeList: chain.node_list || [],
      label: chain.valuation_label || "PE",
      activeNode: state.activeNode,
      onSelect: function (id) {
        state.activeNode = id;
        paintFigure(container);
        paintTable(container);
        paintFilters(container);
      },
    });
    paintFilters(container);
  }

  function paintFilters(container) {
    const host = container.querySelector("#node-filters");
    if (!host) return;
    host.innerHTML = filtersHTML(state.chain, state.activeNode);
    host.querySelectorAll("[data-filter]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        state.activeNode = btn.getAttribute("data-filter");
        paintFigure(container);
        paintTable(container);
        paintFilters(container);
      });
    });
  }

  function paintTable(container) {
    const wrap = container.querySelector("#stocks-table-wrap");
    if (!wrap) return;
    wrap.innerHTML = tableHTML(state.overview, state.chain, state.activeNode);
    wrap.querySelectorAll("tr[data-symbol]").forEach(function (row) {
      row.addEventListener("click", function (ev) {
        if (ev.target.closest("a") || ev.target.closest("[data-star-toggle]")) return;
        location.hash = "#/stock/" + encodeURIComponent(row.getAttribute("data-symbol"));
      });
    });
    wrap.querySelectorAll("[data-star-toggle]").forEach(function (btn) {
      btn.addEventListener("click", async function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        if (btn.disabled || btn.getAttribute("data-busy") === "1") return;
        const active = btn.getAttribute("data-starred") !== "1";
        btn.setAttribute("data-busy", "1");
        btn.disabled = true;
        try {
          if (!V2.api || typeof V2.api.post !== "function") throw new Error("前端版本过旧，请刷新页面");
          await V2.api.post("/api/star", { symbol: btn.getAttribute("data-star-toggle"), active: active });
          btn.setAttribute("data-starred", active ? "1" : "0");
          btn.textContent = active ? "★" : "☆";
          btn.title = active ? "已加星，点击撤星" : "加星/撤星";
        } catch (err) {
          btn.title = err && err.message ? err.message : "加星失败";
          const count = container.querySelector("#stocks-count");
          if (count) count.textContent = "加星失败：" + (err && err.message ? err.message : "未知错误");
        } finally {
          btn.removeAttribute("data-busy");
          btn.disabled = false;
        }
      });
    });
    const count = container.querySelector("#stocks-count");
    if (count) {
      const total = state.chain.stocks || 0;
      const shown = state.activeNode
        ? (state.overview.stocks || []).filter(function (s) { return s.node_id === state.activeNode; }).length
        : total;
      count.textContent = shown === total
        ? "共 " + total + " 只 · 按节点分组 · 小字 1/8=同节点排名（1 最好）"
        : "筛选出 " + shown + " 只 / " + total + " · 小字 1/8=同节点排名";
    }
  }

  async function render(container, ctx) {
    const chainId = ctx.chainId || "whites";
    container.innerHTML = '<p class="loading">载入产业链…</p>';
    let overview;
    let meta = ctx.meta;
    try {
      const results = await Promise.all([
        V2.api.get("/api/overview?chain=" + encodeURIComponent(chainId)),
        meta ? Promise.resolve(meta) : V2.api.get("/api/meta"),
      ]);
      overview = results[0];
      meta = results[1];
    } catch (err) {
      container.innerHTML =
        '<header class="view-head"><div><p class="meta-line">产业链</p><h1 class="display">' +
        fmt.esc(chainId) + "</h1></div></header>" + ui.errorHTML(err.message);
      return;
    }
    const chain = chainMeta(overview, chainId, meta);
    const empty = !((overview.stocks || []).length);
    state = { overview: overview, meta: meta, chain: chain, chainId: chainId, activeNode: "" };
    const asOf = overview.as_of || (meta && meta.as_of) || "";
    const label = chain.valuation_label || "PE";
    container.innerHTML =
      '<header class="view-head">' +
      "<div>" +
      '<p class="meta-line"><span>数据截至 ' + fmt.esc(asOf) + '</span><span class="dot">基准 ' +
      benchLine(overview.benchmark) + '</span><span class="dot">' + fmt.esc(label) + " 口径</span></p>" +
      '<h1 class="display">' + fmt.esc(chain.name) + "</h1>" +
      '<p class="lede">' + fmt.esc(chain.description || "") + "</p>" +
      "</div>" +
      headFigures(chain, overview.breadth || { up_20d: 0, down_20d: 0 }) +
      "</header>" +
      (empty
        ? '<section class="panel chain-empty">' +
          ui.emptyHTML("这条产业链的数据正在采集中，稍后刷新即可。", "") + "</section>"
        : '<figure class="chain-figure">' +
          '<div id="chain-svg"></div>' +
          "<figcaption>" +
          '<span>产业链结构 · 节点为各节点中位读数，点击可与下方表格联动</span>' +
          '<span class="node-filters" id="node-filters" role="group" aria-label="按产业链节点筛选"></span>' +
          "</figcaption>" +
          "</figure>" +
          nodeMetricsHTML(overview, chain) +
          qualityTableHTML(overview) +
          '<section class="stocks-section">' +
          '<div class="section-head">' +
          '<h2 class="section-h2">' + (chain.stocks || 0) + " 只标的</h2>" +
          '<p class="caption" id="stocks-count"></p>' +
          "</div>" +
          '<div class="table-wrap" id="stocks-table-wrap"></div>' +
          "</section>" +
          '<section class="chain-reads">' +
          "<div>" +
          '<div class="section-head"><h2 class="section-h2">产业链读数</h2>' +
          '<p class="caption">来自节点与全链的中位数据，不作预测</p></div>' +
          '<ol class="reads">' + readsHTML(overview.reads) + "</ol>" +
          "</div>" +
          "<div>" +
          '<div class="section-head"><h2 class="section-h2">估值分位分布</h2>' +
          '<p class="caption">近三年' + fmt.esc(label) + " 分位</p></div>" +
          '<div class="dist">' + distHTML(overview, chain) + "</div>" +
          "</div>" +
          "</section>" +
          proxiesHTML(overview.proxies));
    if (!empty) {
      paintFigure(container);
      paintTable(container);
      paintFilters(container);
    }
    if (ctx.onTitle) ctx.onTitle(chain.name);
    if (ctx.onChain) ctx.onChain(chainId);
  }

  V2.views = V2.views || {};
  V2.views.chain = { render: render };
})();
