/* 多股对比：#/compare?chain=&node=&symbols= —— 只允许同链同节点 */
(function () {
  "use strict";
  const V2 = (window.V2 = window.V2 || {});
  const fmt = V2.fmt;
  const ui = V2.ui;

  const LABELS = {
    valuation_pct: "估值分位", gross_margin: "毛利率", revenue_yoy: "营收增速",
    profit_yoy: "净利增速", single_q_rev_yoy: "单季营收", single_q_profit_yoy: "单季扣非",
    inventory_days: "库存天数", receivable_days: "应收天数", ccc: "CCC",
    net_debt_ratio: "净负债率", cash_to_short_debt: "现金/短债", fcf_yield: "FCF 收益率",
    forward_pe: "Forward PE", roe: "ROE", roic: "ROIC", dividend_yield: "股息率",
    pct_20d: "20 日", pct_60d: "60 日", overseas: "海外收入", ps_ttm: "PS",
    ev_ebitda: "EV/EBITDA"
  };

  const DIR = {
    valuation_pct: "pct_low_good", inventory_days: "inverse", receivable_days: "inverse",
    ccc: "inverse", net_debt_ratio: "inverse", cash_to_short_debt: "cash",
    revenue_yoy: "up", profit_yoy: "up", single_q_rev_yoy: "up", single_q_profit_yoy: "up",
    fcf_yield: "up", pct_20d: "up", pct_60d: "up"
  };

  const NODE_PROFILES = {
    "whites:upstream": ["valuation_pct", "gross_margin", "inventory_days", "revenue_yoy", "roe", "fcf_yield", "pct_60d"],
    "whites:appliance": ["valuation_pct", "gross_margin", "revenue_yoy", "profit_yoy", "dividend_yield", "fcf_yield", "overseas"],
    "whites:kitchen": ["valuation_pct", "gross_margin", "revenue_yoy", "receivable_days", "inventory_days", "roe", "pct_60d"],
    "whites:small": ["valuation_pct", "gross_margin", "revenue_yoy", "profit_yoy", "inventory_days", "overseas", "fcf_yield"],
    "whites:clean": ["valuation_pct", "gross_margin", "revenue_yoy", "profit_yoy", "inventory_days", "overseas", "pct_60d"],
    "pv:silicon": ["valuation_pct", "gross_margin", "inventory_days", "single_q_rev_yoy", "net_debt_ratio", "cash_to_short_debt", "fcf_yield", "pct_60d"],
    "pv:wafer": ["valuation_pct", "gross_margin", "inventory_days", "single_q_rev_yoy", "net_debt_ratio", "fcf_yield", "pct_60d"],
    "pv:module": ["valuation_pct", "gross_margin", "inventory_days", "overseas", "revenue_yoy", "receivable_days", "pct_60d"],
    "pv:inverter": ["valuation_pct", "gross_margin", "roe", "roic", "overseas", "forward_pe", "fcf_yield", "pct_60d"],
    "pv:equipment": ["valuation_pct", "gross_margin", "receivable_days", "revenue_yoy", "forward_pe", "fcf_yield", "pct_60d"],
    "auto:parts": ["valuation_pct", "gross_margin", "receivable_days", "ccc", "revenue_yoy", "roic", "overseas"],
    "auto:oem": ["valuation_pct", "gross_margin", "revenue_yoy", "profit_yoy", "inventory_days", "net_debt_ratio", "overseas"],
    "auto:smart": ["valuation_pct", "gross_margin", "revenue_yoy", "profit_yoy", "forward_pe", "roic", "overseas"],
    "copper:raw": ["valuation_pct", "gross_margin", "roe", "roic", "net_debt_ratio", "dividend_yield", "pct_60d"],
    "copper:processing": ["valuation_pct", "gross_margin", "receivable_days", "inventory_days", "ccc", "net_debt_ratio", "cash_to_short_debt"],
    "copper:cable": ["valuation_pct", "gross_margin", "receivable_days", "inventory_days", "net_debt_ratio", "revenue_yoy", "pct_60d"],
    "copper:grid": ["valuation_pct", "gross_margin", "roe", "roic", "receivable_days", "dividend_yield", "pct_60d"],
    "tourism:hotel": ["valuation_pct", "gross_margin", "revenue_yoy", "profit_yoy", "roe", "net_debt_ratio", "pct_60d"],
    "tourism:scenic": ["valuation_pct", "gross_margin", "revenue_yoy", "profit_yoy", "roe", "net_debt_ratio", "pct_60d"],
    "tourism:service": ["valuation_pct", "gross_margin", "revenue_yoy", "profit_yoy", "roe", "forward_pe", "pct_60d"]
  };

  const state = { universe: null, chain: "", node: "", selected: [], max: 8, globalMax: 15 };

  function chainOf(universe, cid) {
    return (universe.chains || []).find(function (c) { return c.id === cid; });
  }

  function nodeOf(universe, cid, nid) {
    const chain = chainOf(universe, cid);
    return chain ? (chain.nodes || []).find(function (n) { return n.id === nid; }) : null;
  }

  function membersOf(universe, cid, nid) {
    const node = nodeOf(universe, cid, nid);
    return node ? node.instruments || [] : [];
  }

  function profileOf(cid, nid) {
    return NODE_PROFILES[cid + ":" + nid] || ["valuation_pct", "gross_margin", "revenue_yoy", "profit_yoy", "roe", "pct_60d"];
  }

  function symbolChainNode(universe, symbols) {
    for (const sym of symbols) {
      for (const c of universe.chains || []) {
        for (const n of c.nodes || []) {
          if ((n.instruments || []).some(function (i) { return i.symbol === sym; })) {
            return { chain: c.id, node: n.id };
          }
        }
      }
    }
    return null;
  }

  function defaultSelection(universe, cid, nid, symbols, maxSelect) {
    const members = membersOf(universe, cid, nid);
    const valid = symbols.filter(function (s) { return members.some(function (m) { return m.symbol === s; }); });
    const picked = valid.slice(0, maxSelect || 8);
    while (picked.length < Math.min(3, members.length)) {
      const s = members[picked.length].symbol;
      if (picked.indexOf(s) === -1) picked.push(s);
    }
    return picked;
  }

  function optionHTML(value, label, selected) {
    return '<option value="' + fmt.esc(value) + '"' + (selected ? " selected" : "") + ">" + fmt.esc(label) + "</option>";
  }

  function checksHTML(members, selected) {
    const set = new Set(selected);
    return members.map(function (m) {
      return '<label class="compare-check"><input type="checkbox" value="' + fmt.esc(m.symbol) + '"' +
        (set.has(m.symbol) ? " checked" : "") + "><span>" + fmt.esc(m.name) +
        '<em>' + fmt.esc(m.symbol) + "</em></span></label>";
    }).join("");
  }

  function controlsHTML(universe, cid, nid, selected, maxSelect) {
    const chainOpts = (universe.chains || []).map(function (c) {
      return optionHTML(c.id, c.name, c.id === cid);
    }).join("");
    const chain = chainOf(universe, cid);
    const nodeOpts = (chain ? chain.nodes || [] : []).map(function (n) {
      return optionHTML(n.id, n.name, n.id === nid);
    }).join("");
    const members = membersOf(universe, cid, nid);
    const node = nodeOf(universe, cid, nid);
    return (
      '<div class="compare-selectors">' +
      '<label class="compare-field"><span>产业链</span><select id="compare-chain">' + chainOpts + "</select></label>" +
      '<label class="compare-field"><span>节点</span><select id="compare-node">' + nodeOpts + "</select></label>" +
      "</div>" +
      '<div class="compare-picker-body"><div class="compare-select-wrap">' +
      '<div class="compare-checks" id="compare-checks">' + checksHTML(members, selected) + "</div></div>" +
      '<div class="compare-actions"><button type="button" class="btn btn-primary" id="compare-go">开始对比</button>' +
      '<div class="compare-mini-actions"><button type="button" class="btn-text" id="compare-all">全选</button>' +
      '<button type="button" class="btn-text" id="compare-none">清空</button></div>' +
      '<p class="caption" id="compare-hint">仅限同一链、同一节点内比较（' + fmt.esc(node ? node.name : "") + "）· 最多 " + maxSelect + " 只</p>" +
      '<p class="compare-selected" id="compare-selected"></p>' +
      '<p class="form-state" id="compare-error" role="status"></p></div></div>'
    );
  }

  function metricHTML(stock, key, basis) {
    const v = stock[key];
    if (v === null || v === undefined) return "—";
    const tone = DIR[key] ? fmt.toneClass(v, DIR[key]) : "";
    let text;
    if (key === "valuation_pct") text = fmt.ratioPct(v);
    else if (key === "gross_margin" || key === "roe" || key === "roic" || key === "fcf_yield" ||
             key === "net_debt_ratio" || key === "dividend_yield" || key === "ev_ebitda" || key === "ps_ttm")
      text = fmt.num(v, 1) + "%";
    else if (key === "inventory_days" || key === "receivable_days" || key === "ccc")
      text = fmt.num(v, 1) + " 天";
    else if (key === "single_q_rev_yoy" || key === "single_q_profit_yoy" || key === "revenue_yoy" ||
             key === "profit_yoy" || key === "pct_20d" || key === "pct_60d")
      text = fmt.pctSigned(v, 1);
    else if (key === "forward_pe") text = fmt.num(v, 1) + "x";
    else if (key === "cash_to_short_debt") text = fmt.num(v, 2);
    else if (key === "overseas") text = fmt.ratioPct(stock.overseas ? stock.overseas.ratio : null);
    else text = fmt.num(v, 1);
    return '<span class="' + tone + '">' + text + "</span>" + fmt.rank(stock.ranks && stock.ranks[key]);
  }

  function tableHTML(stocks, cid, nid, basis) {
    const keys = profileOf(cid, nid);
    const head = "<thead><tr><th class=\"t-left\">标的</th>" + keys.map(function (k) {
      return '<th class="t-right">' + fmt.esc(LABELS[k] || k) + "</th>";
    }).join("") + "</tr></thead>";
    const rows = stocks.map(function (s) {
      return "<tr>" +
        '<td class="t-left"><a class="stock-name" href="#/stock/' + encodeURIComponent(s.symbol) + '">' +
        fmt.esc(s.name) + '</a><span class="chain-short">' + fmt.esc(s.symbol) + "</span></td>" +
        keys.map(function (k) {
          return '<td class="t-right num">' + metricHTML(s, k, basis) + "</td>";
        }).join("") + "</tr>";
    }).join("");
    return '<div class="table-wrap"><table class="stocks compare-table">' + head + "<tbody>" + rows + "</tbody></table></div>";
  }

  function selectedFrom(container) {
    return Array.from(container.querySelectorAll("#compare-checks input[type=checkbox]"))
      .filter(function (box) { return box.checked; })
      .map(function (box) { return box.value; });
  }

  function syncPicker(container, universe, cid, nid, selected) {
    const chain = chainOf(universe, cid);
    const nodeSel = container.querySelector("#compare-node");
    if (nodeSel) {
      nodeSel.innerHTML = (chain ? chain.nodes || [] : []).map(function (n) {
        return optionHTML(n.id, n.name, n.id === nid);
      }).join("");
    }
    const checks = container.querySelector("#compare-checks");
    if (checks) checks.innerHTML = checksHTML(membersOf(universe, cid, nid), selected);
    const node = nodeOf(universe, cid, nid);
    const hint = container.querySelector("#compare-hint");
    if (hint) hint.textContent = "仅限同一链、同一节点内比较（" + (node ? node.name : "") + "）· 最多 " + state.max + " 只";
  }

  async function render(container, ctx) {
    container.innerHTML = '<p class="loading">载入多股对比…</p>';
    let universe;
    try {
      universe = await V2.api.get("/api/universe");
    } catch (err) {
      container.innerHTML = ui.errorHTML("载入标的池失败：" + err.message);
      return;
    }
    state.universe = universe;
    let symbols = (ctx.symbols || []);
    let derived = symbolChainNode(universe, symbols);
    let cid = ctx.chain || (derived && derived.chain) || "pv";
    let nid = ctx.node || (derived && derived.node) || "silicon";
    if (!chainOf(universe, cid)) cid = "pv";
    if (!nodeOf(universe, cid, nid)) {
      const chain = chainOf(universe, cid);
      nid = chain && chain.nodes.length ? chain.nodes[0].id : "silicon";
    }
    const maxSelect = universe.max_node_size || 8;
    const nodeMembers = membersOf(universe, cid, nid);
    const nodeMax = Math.min(maxSelect, nodeMembers.length || maxSelect);
    state.globalMax = maxSelect;
    state.max = nodeMax;
    symbols = defaultSelection(universe, cid, nid, symbols, nodeMax);
    state.chain = cid;
    state.node = nid;
    state.selected = symbols;

    const hash = "#/compare?chain=" + cid + "&node=" + nid + "&symbols=" + symbols.join(",");
    if (location.hash !== hash) history.replaceState(null, "", hash);

    container.innerHTML =
      '<header class="view-head"><div><p class="meta-line">多股对比 · 同链同节点 · 归一化起点=100</p>' +
      '<h1 class="display">多股对比</h1>' +
      '<p class="lede">只在同一产业链、同一节点内比较（上游不和整机、硅料不和组件硬比）；下方按该节点核心指标展示。</p></div></header>' +
      '<section class="panel compare-picker">' +
      '<div class="panel-head"><h2 class="section-h2">选择节点与标的</h2>' +
      '<p class="caption" id="compare-count">2–' + state.max + " 只 · 已选 " + symbols.length + " 只</p></div>" +
      controlsHTML(universe, cid, nid, symbols, state.max) +
      '</section>' +
      '<section class="compare-result"><div class="section-head"><h2 class="section-h2">归一化价格</h2>' +
      '<p class="caption" id="compare-asof"></p></div><figure class="chart-figure chart-wide">' +
      '<div class="chart-body" id="compare-chart"></div></figure><div id="compare-table"></div></section>';

    const chainSel = container.querySelector("#compare-chain");
    const nodeSel = container.querySelector("#compare-node");
    if (chainSel) {
      chainSel.addEventListener("change", function () {
        const chain = chainOf(universe, chainSel.value);
        const firstNode = chain && chain.nodes.length ? chain.nodes[0].id : "";
        const members = membersOf(universe, chainSel.value, firstNode);
        state.chain = chainSel.value;
        state.node = firstNode;
        state.max = Math.min(state.globalMax, members.length || state.globalMax);
        state.selected = members.slice(0, Math.min(3, members.length)).map(function (m) { return m.symbol; });
        const countEl = container.querySelector("#compare-count");
        if (countEl) countEl.textContent = "2–" + state.max + " 只";
        syncPicker(container, universe, state.chain, state.node, state.selected);
      });
    }
    if (nodeSel) {
      nodeSel.addEventListener("change", function () {
        const members = membersOf(universe, state.chain, nodeSel.value);
        state.node = nodeSel.value;
        state.max = Math.min(state.globalMax, members.length || state.globalMax);
        state.selected = members.slice(0, Math.min(3, members.length)).map(function (m) { return m.symbol; });
        const countEl = container.querySelector("#compare-count");
        if (countEl) countEl.textContent = "2–" + state.max + " 只";
        syncPicker(container, universe, state.chain, state.node, state.selected);
      });
    }
    const go = container.querySelector("#compare-go");
    if (go) {
      go.addEventListener("click", function () {
        const picked = selectedFrom(container);
        const err = container.querySelector("#compare-error");
        if (picked.length < 2 || picked.length > state.max) {
          if (err) err.textContent = "请选择 2–" + state.max + " 只同节点标的";
          return;
        }
        location.hash = "#/compare?chain=" + state.chain + "&node=" + state.node +
          "&symbols=" + encodeURIComponent(picked.join(","));
      });
    }

    const checks = container.querySelector("#compare-checks");
    if (checks) {
      checks.addEventListener("change", function (ev) {
        const box = ev.target.closest("input[type=checkbox]");
        if (!box) return;
        let picked = selectedFrom(container);
        const err = container.querySelector("#compare-error");
        if (picked.length > state.max) {
          box.checked = false;
          if (err) err.textContent = "最多选择 " + state.max + " 只";
          picked = selectedFrom(container);
        } else if (err) {
          err.textContent = "";
        }
        state.selected = picked;
        const count = container.querySelector("#compare-count");
        if (count) count.textContent = "2–" + state.max + " 只 · 已选 " + picked.length + " 只";
      });
    }
    const allBtn = container.querySelector("#compare-all");
    if (allBtn) {
      allBtn.addEventListener("click", function () {
        container.querySelectorAll("#compare-checks input[type=checkbox]").forEach(function (box) {
          box.checked = true;
        });
        state.selected = selectedFrom(container);
        const count = container.querySelector("#compare-count");
        if (count) count.textContent = "2–" + state.max + " 只 · 已选 " + state.selected.length + " 只";
      });
    }
    const noneBtn = container.querySelector("#compare-none");
    if (noneBtn) {
      noneBtn.addEventListener("click", function () {
        container.querySelectorAll("#compare-checks input[type=checkbox]").forEach(function (box) {
          box.checked = false;
        });
        state.selected = [];
        const count = container.querySelector("#compare-count");
        if (count) count.textContent = "2–" + state.max + " 只 · 已选 0 只";
      });
    }

    let data;
    try {
      data = await load(symbols);
    } catch (err) {
      container.querySelector("#compare-table").innerHTML = ui.errorHTML("对比失败：" + err.message);
      return;
    }
    const count = container.querySelector("#compare-count");
    if (count) count.textContent = "2–" + state.max + " 只 · 已选 " + (data.symbols || []).length + " 只";
    const picked = container.querySelector("#compare-selected");
    if (picked) picked.innerHTML = (data.stocks || []).map(function (s) {
      return '<span class="compare-chip">' + fmt.esc(s.name) + "</span>";
    }).join("");
    const asof = container.querySelector("#compare-asof");
    if (asof) asof.textContent = "数据截至 " + (data.as_of || "") + " · 归一化";
    V2.charts.multiPrice(container.querySelector("#compare-chart"), data.series, data.stocks);
    container.querySelector("#compare-table").innerHTML =
      '<div class="section-head"><h2 class="section-h2">' + fmt.esc(data.node ? data.node.name : "") + '核心指标</h2>' +
      '<p class="caption">按节点特征取数；小字 1/8=节点内排名，红=正向，绿=负向</p></div>' +
      tableHTML(data.stocks || [], data.chain ? data.chain.id : cid, data.node ? data.node.id : nid,
                data.stocks && data.stocks[0] ? data.stocks[0].valuation_basis : "pe");
  }

  async function load(symbols) {
    const q = "?symbols=" + encodeURIComponent(symbols.join(",")) + "&points=760";
    return V2.api.get("/api/compare" + q);
  }

  V2.views = V2.views || {};
  V2.views.compare = { render: render };
})();
