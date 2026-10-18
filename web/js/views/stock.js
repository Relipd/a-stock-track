/* 标的活文档：#/stock/{symbol} */
(function () {
  "use strict";
  const V2 = (window.V2 = window.V2 || {});
  const fmt = V2.fmt;
  const ui = V2.ui;

  const STATUS_STEPS = ["watch", "building", "holding", "reduced", "closed"];
  const ACTIONS = ["watch", "buy", "add", "reduce", "exit"];

  let state = { data: null, overview: null, meta: null, symbol: "", pendingStatus: "watch" };

  function pctSpan(value, digits) {
    return '<span class="' + fmt.signClass(value) + '">' + fmt.pctSigned(value, digits) + "</span>";
  }

  function railHTML(overview, current) {
    const nodes = overview.nodes || [];
    const stocks = overview.stocks || [];
    const head = '<p class="rail-head">' + (stocks.length || 20) + " 只标的 · 按节点</p>";
    const groups = nodes.map(function (node) {
      const members = stocks.filter(function (s) { return s.node_id === node.id; });
      return (
        '<div class="rail-group">' +
        '<p class="rail-node">' + fmt.esc(node.name) + " · " + members.length + "</p>" +
        members.map(function (s) {
          const active = s.symbol === current;
          return '<a class="rail-link" href="#/stock/' + encodeURIComponent(s.symbol) + '"' +
            (active ? ' aria-current="page"' : "") +
            ' title="' + fmt.esc(s.name) + " · " + fmt.status(s.thesis_status) + '">' +
            "<span>" + fmt.esc(s.name) + "</span>" +
            '<span class="rail-sym">' + fmt.esc(s.symbol) + "</span></a>";
        }).join("") +
        "</div>"
      );
    }).join("");
    return head + groups;
  }

  function pickerHTML(overview, current) {
    const nodes = overview.nodes || [];
    const stocks = overview.stocks || [];
    const groups = nodes.map(function (node) {
      const members = stocks.filter(function (s) { return s.node_id === node.id; });
      return '<optgroup label="' + fmt.esc(node.name) + '">' +
        members.map(function (s) {
          return '<option value="' + fmt.esc(s.symbol) + '"' + (s.symbol === current ? " selected" : "") +
            ">" + fmt.esc(s.name) + " " + fmt.esc(s.symbol) + "</option>";
        }).join("") + "</optgroup>";
    }).join("");
    return (
      '<div class="stock-picker">' +
      '<label class="field"><span class="field-label">切换标的</span>' +
      '<select class="input" id="stock-select">' + groups + "</select></label></div>"
    );
  }

  function statusMachine(status) {
    return STATUS_STEPS.map(function (s, i) {
      const arrow = i ? '<span class="status-arrow" aria-hidden="true">→</span>' : "";
      return arrow +
        '<button type="button" class="status-step" role="radio" aria-checked="' + (s === status) +
        '" data-status="' + s + '">' + fmt.status(s) + "</button>";
    }).join("");
  }

  function statsHTML(stock) {
    const basis = stock.valuation_basis || "pe";
    const label = fmt.basisLabel(basis);
    return (
      '<dl class="stats">' +
      '<div class="stat"><dt>' + label + '（TTM）</dt><dd>' + fmt.num(fmt.basisValue(stock, basis), 1) +
      '<span class="stat-sub ' + fmt.toneClass(fmt.basisPct(stock, basis), "pct_low_good") + '">分位 ' +
      fmt.ratioPct(fmt.basisPct(stock, basis)) + "</span>" +
      fmt.rank(stock.ranks && stock.ranks.valuation_pct) + "</dd></div>" +
      '<div class="stat"><dt>毛利率</dt><dd>' + fmt.num(stock.gross_margin, 1) + "%" +
      fmt.rank(stock.ranks && stock.ranks.gross_margin) + "</dd></div>" +
      '<div class="stat"><dt>营收同比</dt><dd class="' + fmt.signClass(stock.revenue_yoy) + '">' +
      fmt.pctSigned(stock.revenue_yoy, 1) + fmt.rank(stock.ranks && stock.ranks.revenue_yoy) + "</dd></div>" +
      '<div class="stat"><dt>利润同比</dt><dd class="' + fmt.signClass(stock.profit_yoy) + '">' +
      fmt.pctSigned(stock.profit_yoy, 1) + fmt.rank(stock.ranks && stock.ranks.profit_yoy) + "</dd></div>" +
      '<div class="stat"><dt>库存天数</dt><dd>' + fmt.num(stock.inventory_days, 1) +
      fmt.rank(stock.ranks && stock.ranks.inventory_days) + "</dd></div>" +
      '<div class="stat"><dt>ROE</dt><dd>' + fmt.num(stock.roe, 1) + "%" +
      fmt.rank(stock.ranks && stock.ranks.roe) + "</dd></div>" +
      "</dl>"
    );
  }

  function starNoteHTML(star) {
    if (!star || !star.starred) return "";
    const has = Boolean((star.logic_note || "").trim());
    return (
      '<section class="panel star-note-panel">' +
      '<div class="panel-head"><h2 class="section-h2">关注逻辑</h2>' +
      '<p class="caption">加星 ' + fmt.esc(star.starred_at || "—") +
      " · 首次记录 " + fmt.esc(star.logic_date || "—") +
      " · 更新 " + fmt.esc(star.logic_updated_at || "—") + "</p></div>" +
      '<div data-note-view><p class="star-note-body">' +
      (has ? fmt.esc(star.logic_note) : "还没有评语。加星后写下核心逻辑、反方观点和估值锚点。") + "</p>" +
      '<div class="star-note-actions"><button type="button" class="btn-text" data-note-edit>' +
      (has ? "修改" : "写评语") + "</button>" +
      (has && !star.investment_star ? '<button type="button" class="btn-text danger" data-note-delete>删除</button>' : "") +
      (has && star.investment_star ? '<span class="caption">投资加星期间评语锁定，不能删除</span>' : "") +
      "</div></div>" +
      '<form class="star-note-form" data-note-form hidden>' +
      '<textarea class="input" data-note-input rows="4" placeholder="为什么关注它？核心变量、反方观点、估值锚点。">' +
      fmt.esc(star.logic_note || "") + "</textarea>" +
      '<div class="star-note-actions"><button type="submit" class="btn btn-primary">保存</button>' +
      '<button type="button" class="btn-text" data-note-cancel>取消</button>' +
      '<span class="form-state" data-note-state role="status"></span></div></form></section>'
    );
  }

  function qualityHTML(stock) {    const items = [
      ["总市值", stock.total_mv ? fmt.num(stock.total_mv / 1e8, 0) + " 亿" : "—", ""],
      ["市销率 PS", stock.ps_ttm ? fmt.num(stock.ps_ttm, 2) : "—", ""],
      ["股息率", stock.dividend_yield === null || stock.dividend_yield === undefined ? "—" : fmt.num(stock.dividend_yield, 2) + "%", ""],
      ["ROIC", (stock.roic === null || stock.roic === undefined ? "—" : fmt.num(stock.roic, 1) + "%") + fmt.rank(stock.ranks && stock.ranks.roic), ""],
      ["FCF 收益率", (stock.fcf_yield === null || stock.fcf_yield === undefined ? "—" : fmt.num(stock.fcf_yield, 2) + "%") + fmt.rank(stock.ranks && stock.ranks.fcf_yield), fmt.toneClass(stock.fcf_yield, "up")],
      ["净负债率", stock.net_debt_ratio === null || stock.net_debt_ratio === undefined ? "—" : fmt.num(stock.net_debt_ratio, 1) + "%", ""],
      ["单季营收", (stock.single_q_rev_yoy === null || stock.single_q_rev_yoy === undefined ? "—" : fmt.pctSigned(stock.single_q_rev_yoy, 1)) + fmt.rank(stock.ranks && stock.ranks.single_q_rev_yoy), fmt.signClass(stock.single_q_rev_yoy)],
      ["单季扣非", (stock.single_q_profit_yoy === null || stock.single_q_profit_yoy === undefined ? "—" : fmt.pctSigned(stock.single_q_profit_yoy, 1)) + fmt.rank(stock.ranks && stock.ranks.single_q_profit_yoy), fmt.signClass(stock.single_q_profit_yoy)],
      ["Forward PE", (stock.forward_pe ? fmt.num(stock.forward_pe, 1) + (stock.forward_pe_year ? " · " + stock.forward_pe_year + "E" : "") : "—") + fmt.rank(stock.ranks && stock.ranks.forward_pe), ""],
      ["现金/短债", stock.cash_to_short_debt === null || stock.cash_to_short_debt === undefined ? "—" : fmt.num(stock.cash_to_short_debt, 2), fmt.toneClass(stock.cash_to_short_debt, "cash")],
      ["海外收入", stock.overseas && stock.overseas.ratio !== null ? fmt.ratioPct(stock.overseas.ratio) : "—", ""],
      ["股东户数环比", (stock.holder_num_chg_pct === null || stock.holder_num_chg_pct === undefined ? "—" : fmt.pctSigned(stock.holder_num_chg_pct, 1)), fmt.toneClass(stock.holder_num_chg_pct, "inverse")],
    ];
    return '<dl class="stats stats-quality">' + items.map(function (x) {
      return '<div class="stat"><dt>' + x[0] + "</dt><dd" + (x[2] ? ' class="' + x[2] + '"' : "") + ">" + x[1] + "</dd></div>";
    }).join("") + "</dl>";
  }

  function assumptionHTML(a, asOf) {
    const dl = fmt.deadlineInfo(a.deadline, asOf);
    const chips = fmt.ASSUMPTION_ORDER.map(function (s) {
      return '<button type="button" class="status-chip" data-status="' + s + '" aria-pressed="' +
        (a.status === s) + '">' + fmt.assumption(s) + "</button>";
    }).join("");
    return (
      '<li class="assumption" data-assumption-id="' + fmt.esc(a.id) + '">' +
      "<div>" +
      '<p class="a-statement">' + fmt.esc(a.statement) + "</p>" +
      '<p class="a-meta">' +
      (a.metric ? "<span>" + fmt.esc(a.metric) + (a.target ? " " + fmt.esc(a.target) : "") + "</span>" : "") +
      (a.deadline ? "<span>截止 " + fmt.esc(fmt.date(a.deadline)) + "</span>" : "") +
      (dl.overdue ? '<span class="a-overdue">' + dl.text + "</span>" : "") +
      "</p>" +
      (a.evidence ? '<p class="a-evidence">证据：' + fmt.esc(a.evidence) + "</p>" : "") +
      "</div>" +
      '<div class="a-controls">' +
      '<div class="status-chips" role="group" aria-label="假设状态">' + chips + "</div>" +
      '<input class="input a-evidence-input" data-evidence aria-label="假设证据" placeholder="' +
      (a.evidence ? "更新证据" : "证据") + '">' +
      '<button type="button" class="btn a-update" data-save-evidence>保存证据</button>' +
      '<span class="form-state a-state" role="status"></span>' +
      "</div>" +
      "</li>"
    );
  }

  function updateEvidenceLine(row, text) {
    let p = row.querySelector(".a-evidence");
    if (!p) {
      p = document.createElement("p");
      p.className = "a-evidence";
      const meta = row.querySelector(".a-meta");
      if (meta && meta.parentNode) meta.parentNode.insertBefore(p, meta.nextSibling);
      else if (row.firstElementChild) row.firstElementChild.appendChild(p);
    }
    p.textContent = "证据：" + text;
  }

  function assumptionsListHTML(thesis, asOf) {
    const list = thesis && thesis.assumptions ? thesis.assumptions : [];
    if (!list.length) {
      return '<li class="empty">还没有假设。先写下一条可被证伪的判断——它决定这笔投资何时该退出。' +
        '<button type="button" class="btn-text" data-open-assumption>新增第一条假设</button></li>';
    }
    return list.map(function (a) { return assumptionHTML(a, asOf); }).join("");
  }

  function timelineHTML(data) {
    const decisions = data.decisions || [];
    if (!decisions.length) {
      return '<p class="empty">还没有决策记录。第一次记录通常从「观察」开始——写下当时的价格与理由。' +
        '<a class="btn-text" href="#decision-form">去记录</a></p>';
    }
    return '<ol class="timeline">' + decisions.map(function (d) {
      return (
        '<li class="decision">' +
        '<span class="d-date num">' + fmt.esc(fmt.dateTime(d.created_at)) + "</span>" +
        '<span class="d-action">' + fmt.action(d.action) +
        ' <span class="d-price num">' + fmt.price(d.price) + "</span>" +
        (Number(d.weight_pct) ? '<span class="d-weight">仓位 ' + fmt.weight(d.weight_pct) + "</span>" : "") +
        "</span>" +
        '<div class="d-body">' +
        '<p class="d-logic">' + fmt.esc(d.logic || "") + "</p>" +
        (d.kill_switch ? '<p class="d-kill"><b>证伪：</b>' + fmt.esc(d.kill_switch) + "</p>" : "") +
        (d.snapshot_hash ? '<p class="d-hash" title="' + fmt.esc(d.snapshot_hash) + '">快照 ' +
          fmt.esc(String(d.snapshot_hash).slice(0, 12)) + "…</p>" : "") +
        "</div></li>"
      );
    }).join("") + "</ol>";
  }

  function businessPanel(b) {
    if (!b || !((b.products || []).length || (b.regions || []).length)) return "";
    const products = (b.products || []).slice(0, 8);
    const regions = (b.regions || []).slice(0, 5);
    const productRows = products.map(function (p) {
      const ratio = Number(p.ratio) || 0;
      return (
        "<tr>" +
        '<td class="t-left">' + fmt.esc(p.item) + "</td>" +
        '<td class="t-right num">' + (p.revenue === null ? "—" : fmt.num(p.revenue / 1e8, 1) + " 亿") + "</td>" +
        '<td class="t-right num">' + fmt.ratioPct(ratio) +
        '<span class="biz-bar" aria-hidden="true"><i style="width:' + (ratio * 100).toFixed(1) + '%"></i></span></td>' +
        '<td class="t-right num">' + (p.gross_margin === null ? "—" : fmt.num(p.gross_margin * 100, 1) + "%") + "</td>" +
        "</tr>"
      );
    }).join("");
    const regionRows = regions.map(function (p) {
      return '<span class="biz-region">' + fmt.esc(p.item) + " " + fmt.ratioPct(p.ratio) + "</span>";
    }).join("");
    return (
      '<section class="panel" id="business-panel">' +
      '<div class="panel-head"><h2 class="section-h2">主营构成</h2>' +
      '<p class="caption">' + fmt.esc(b.report_date || "") + " · 按产品 / 按地区</p></div>" +
      (b.main_business ? '<p class="business-desc">' + fmt.esc(b.main_business) + "</p>" : "") +
      (products.length
        ? '<div class="table-wrap"><table class="stocks business-table"><thead><tr>' +
          '<th class="t-left">产品</th><th class="t-right">收入</th>' +
          '<th class="t-right">收入占比</th><th class="t-right">毛利率</th>' +
          "</tr></thead><tbody>" + productRows + "</tbody></table></div>"
        : "") +
      (regionRows ? '<p class="biz-regions"><span class="caption">按地区</span>' + regionRows + "</p>" : "") +
      (b.overseas && b.overseas.ratio !== null
        ? '<p class="biz-regions"><span class="caption">海外收入</span>' +
          '<span class="biz-region">占比 ' + fmt.ratioPct(b.overseas.ratio) +
          (b.overseas.ratio_delta === null || b.overseas.ratio_delta === undefined ? "" : "（同比 " + (Number(b.overseas.ratio_delta) > 0 ? "+" : "") + fmt.num(b.overseas.ratio_delta, 1) + "pp）") +
          (b.overseas.gross_margin === null || b.overseas.gross_margin === undefined ? "" : " · 毛利率 " + fmt.num(b.overseas.gross_margin, 1) + "%") +
          "</span></p>"
        : "") +
      "</section>"
    );
  }

  function thesisPanel(data) {
    const t = data.thesis;
    const status = t ? t.status : "watch";
    const alerts = data.alerts || [];
    const asOf = (state.meta && state.meta.as_of) || "";
    const updated = t && t.updated_at ? "更新于 " + fmt.date(t.updated_at) : "尚未建立逻辑卡 · 保存后开始记录";
    return (
      '<section class="panel" id="thesis-panel">' +
      '<div class="panel-head">' +
      '<h2 class="section-h2">我的逻辑</h2>' +
      '<p class="caption" id="thesis-caption">' + fmt.esc(updated) + "</p>" +
      "</div>" +
      (alerts.length
        ? '<div class="alert-strip">' + alerts.map(function (a) {
          return '<p class="alert-line"><span>' + fmt.esc(a.message) + "</span></p>";
        }).join("") + "</div>"
        : "") +
      '<form id="thesis-form" novalidate>' +
      '<div class="status-machine" role="radiogroup" aria-label="逻辑状态">' + statusMachine(status) + "</div>" +
      '<div class="thesis-fields">' +
      '<label class="field"><span class="field-label">一句话标题</span>' +
      '<input class="input" name="title" placeholder="例如：整机龙头，成本下行 + 出海" value="' +
      fmt.esc(t && t.title ? t.title : "") + '"></label>' +
      '<label class="field"><span class="field-label">核心逻辑</span>' +
      '<textarea class="input" name="core_logic" rows="4" placeholder="写下买入理由、关键变量与不买的理由。">' +
      fmt.esc(t && t.core_logic ? t.core_logic : "") + "</textarea></label>" +
      "</div>" +
      '<div class="form-grid cols-2" style="margin-top:16px">' +
      '<label class="field"><span class="field-label">估值看法</span>' +
      '<textarea class="input" name="valuation_view" rows="3" placeholder="什么价格算便宜，什么价格算贵。">' +
      fmt.esc(t && t.valuation_view ? t.valuation_view : "") + "</textarea></label>" +
      '<label class="field"><span class="field-label">持有周期</span>' +
      '<input class="input" name="horizon" placeholder="例如：6-12 个月" value="' +
      fmt.esc(t && t.horizon ? t.horizon : "") + '">' +
      '<span class="caption" style="display:block;margin-top:8px">周期决定用哪张财报验证假设。</span></label>' +
      "</div>" +
      '<div class="form-actions">' +
      '<button type="submit" class="btn btn-primary">保存逻辑卡</button>' +
      '<span class="form-state" id="thesis-state" role="status"></span>' +
      "</div>" +
      "</form>" +
      '<div class="panel-subhead">' +
      '<h3 class="section-h3">假设清单</h3>' +
      '<button type="button" class="btn-text" id="assumption-toggle">＋ 新增假设</button>' +
      "</div>" +
      '<div class="add-assumption" id="assumption-form-wrap" hidden>' +
      '<form id="assumption-form" class="form-grid cols-3" novalidate>' +
      '<label class="field" style="grid-column:1/-1"><span class="field-label">假设陈述（可被证伪）<span class="req">*</span></span>' +
      '<input class="input" name="statement" placeholder="例如：Q3 毛利率同比提升至 27% 以上" required></label>' +
      '<label class="field"><span class="field-label">指标</span>' +
      '<input class="input" name="metric" placeholder="销售毛利率"></label>' +
      '<label class="field"><span class="field-label">目标</span>' +
      '<input class="input" name="target" placeholder="≥27%"></label>' +
      '<label class="field"><span class="field-label">截止日</span>' +
      '<input class="input" type="date" name="deadline"></label>' +
      '<div class="form-actions" style="grid-column:1/-1">' +
      '<button type="submit" class="btn btn-ink">添加假设</button>' +
      '<button type="button" class="btn-text" id="assumption-cancel">取消</button>' +
      '<span class="form-state" id="assumption-state" role="status"></span>' +
      "</div></form></div>" +
      '<ul class="assumptions" id="assumption-list">' + assumptionsListHTML(t, asOf) + "</ul>" +
      "</section>"
    );
  }

  function decisionsPanel(data) {
    return (
      '<section class="panel" id="decisions-panel">' +
      '<div class="panel-head">' +
      '<h2 class="section-h2">决策记录</h2>' +
      '<p class="caption">提交时固化价格、估值与财务快照，并计算 sha256</p>' +
      "</div>" +
      '<form id="decision-form" class="decision-form" novalidate>' +
      '<h3 class="section-h3">记录一次决策</h3>' +
      '<div class="form-grid cols-3" style="margin-top:14px">' +
      '<label class="field"><span class="field-label">类型</span><select class="input" name="action">' +
      ACTIONS.map(function (a) {
        return '<option value="' + a + '">' + fmt.action(a) + "</option>";
      }).join("") + "</select></label>" +
      '<label class="field"><span class="field-label">成交价 / 现价</span>' +
      '<input class="input num" type="number" step="0.01" min="0" name="price" value="' +
      fmt.price(data.stock.price) + '"></label>' +
      '<label class="field"><span class="field-label">计划仓位 %</span>' +
      '<input class="input num" type="number" step="0.1" min="0" max="100" name="weight_pct" value="0"></label>' +
      "</div>" +
      '<div class="form-grid" style="margin-top:16px">' +
      '<label class="field"><span class="field-label">理由<span class="req">*</span></span>' +
      '<textarea class="input" name="logic" rows="2" placeholder="为什么在此时做这个动作。"></textarea></label>' +
      '<label class="field"><span class="field-label">证伪条件</span>' +
      '<textarea class="input" name="kill_switch" rows="2" placeholder="出现什么情况说明这次判断错了。"></textarea></label>' +
      "</div>" +
      '<div class="form-actions">' +
      '<button type="submit" class="btn btn-ink">记录决策</button>' +
      '<span class="form-state" id="decision-state" role="status"></span>' +
      "</div>" +
      "</form>" +
      '<div id="decision-timeline">' + timelineHTML(data) + "</div>" +
      "</section>"
    );
  }

  function viewHTML(data, overview, meta) {
    const s = data.stock;
    const star = data.star || {};
    const investmentLocked = Number(star.investment_star) === 1;
    s.ranks = data.ranks || {};
    const pos = data.position;
    const thesis = data.thesis;
    const asOf = (meta && meta.as_of) || "";
    const positionLine = pos
      ? (pos.shares !== undefined && pos.shares !== null ? "持仓 " + pos.shares + " 股 · " : "持仓 · ") +
        "成本 " + fmt.price(pos.entry_price) + " · 仓位 " + fmt.weight(pos.weight_pct) +
        " · 浮盈 " + fmt.pctSigned(pos.pnl_pct, 1)
      : "当前无持仓";
    const basis = s.valuation_basis || "pe";
    const basisLabel = fmt.basisLabel(basis);
    return (
      '<div class="stock-layout">' +
      '<aside class="stock-rail" aria-label="标的池">' + railHTML(overview, s.symbol) + "</aside>" +
      '<div class="stock-main">' +
      pickerHTML(overview, s.symbol) +
      '<header class="stock-head">' +
      '<p class="meta-line"><a class="chain-link-inline" href="#/chain/' + encodeURIComponent(s.chain_id) + '">' +
      fmt.esc(s.chain_name) + "</a>" +
      '<span class="dot">' + fmt.esc(s.node_name) + '</span><span class="dot">' + fmt.role(s.role) +
      '</span><span class="dot">' + fmt.esc(s.symbol) + "</span>" +
      (asOf ? '<span class="dot">数据截至 ' + fmt.esc(asOf) + "</span>" : "") + "</p>" +
      '<div class="stock-title-line">' +
      '<h1 class="display">' + fmt.esc(s.name) + "</h1>" +
      '<span class="stock-price num">' + fmt.price(s.price) + "</span>" +
      '<span class="stock-chg ' + fmt.signClass(s.pct_1d) + '">' + fmt.pctSigned(s.pct_1d) + "</span>" +
      '<button type="button" id="star-toggle" class="star-toggle" data-starred="' + (star.starred ? "1" : "0") +
      '" data-invest="' + (investmentLocked ? "1" : "0") + '"' +
      (investmentLocked ? ' disabled title="投资加星中，需先结算或取消投资加星"' : "") + ">" +
      (star.starred ? "★ 已加星" : "☆ 加星") + "</button>" +
      "</div>" +
      '<p class="stock-subline">' +
      "<span>20 日 <strong>" + pctSpan(s.pct_20d) + "</strong></span>" +
      "<span>60 日 <strong>" + pctSpan(s.pct_60d) + "</strong></span>" +
      '<span>我的状态 <strong id="sub-status">' + fmt.status(s.thesis_status) + "</strong></span>" +
      '<span id="sub-position">' + fmt.esc(positionLine) + "</span>" +
      "</p>" +
      statsHTML(s) +
      qualityHTML(s) +
      "</header>" +
      starNoteHTML(star) +
      '<div class="chart-duo">' +
      '<figure class="chart-figure"><figcaption><span>收盘价</span><span class="unit">近三年 · 日</span></figcaption>' +
      '<div class="chart-body" id="chart-price"></div></figure>' +
      '<figure class="chart-figure"><figcaption><span>' + basisLabel + ' 分位</span><span class="unit">' +
      basisLabel + " " + fmt.num(fmt.basisValue(s, basis), 2) + " · 分位 " +
      fmt.ratioPct(fmt.basisPct(s, basis)) + " · 3 月均</span></figcaption>" +
      '<div class="chart-body" id="chart-pe"></div></figure>' +
      "</div>" +
      '<figure class="chart-figure chart-wide"><figcaption><span>财务趋势</span>' +
      '<span class="unit">近 10 个季度 · 右轴为库存天数</span></figcaption>' +
      '<div class="chart-body" id="chart-fin"></div></figure>' +
      businessPanel(data.business) +
      thesisPanel(data) +
      decisionsPanel(data) +
      "</div></div>"
    );
  }

  function bind(container, ctx) {
    const stateEl = container.querySelector("#thesis-state");
    const thesisForm = container.querySelector("#thesis-form");
    const thesisCaption = container.querySelector("#thesis-caption");
    const subStatus = container.querySelector("#sub-status");
    const asOf = (state.meta && state.meta.as_of) || "";
    const starBtn = container.querySelector("#star-toggle");
    if (starBtn) {
      starBtn.addEventListener("click", async function () {
        if (starBtn.disabled) return;
        const active = starBtn.getAttribute("data-starred") !== "1";
        try {
          await V2.api.post("/api/star", { symbol: state.symbol, active: active });
          V2.app.route();
        } catch (err) {
          starBtn.title = err.message;
        }
      });
    }
    const noteForm = container.querySelector("[data-note-form]");
    const noteView = container.querySelector("[data-note-view]");
    if (noteForm && noteView) {
      const openNote = function () {
        noteForm.hidden = false;
        noteView.hidden = true;
      };
      const closeNote = function () {
        noteForm.hidden = true;
        noteView.hidden = false;
      };
      const editBtn = container.querySelector("[data-note-edit]");
      if (editBtn) editBtn.addEventListener("click", openNote);
      const cancelBtn = container.querySelector("[data-note-cancel]");
      if (cancelBtn) cancelBtn.addEventListener("click", closeNote);
      noteForm.addEventListener("submit", async function (ev) {
        ev.preventDefault();
        const note = noteForm.querySelector("[data-note-input]").value;
        const stateEl = noteForm.querySelector("[data-note-state]");
        try {
          await V2.api.post("/api/star/note", { symbol: state.symbol, note: note });
          V2.app.route();
        } catch (err) {
          if (stateEl) stateEl.textContent = err.message;
        }
      });
      const delBtn = container.querySelector("[data-note-delete]");
      if (delBtn) {
        delBtn.addEventListener("click", async function () {
          if (!window.confirm("删除这段逻辑评语？历史版本会保留在本地。")) return;
          try {
            await V2.api.del("/api/star/note?symbol=" + encodeURIComponent(state.symbol));
            V2.app.route();
          } catch (err) {
            const stateEl = noteForm.querySelector("[data-note-state]");
            if (stateEl) stateEl.textContent = err.message;
          }
        });
      }
    }

    container.querySelectorAll(".status-step").forEach(function (btn) {
      btn.addEventListener("click", function () {
        container.querySelectorAll(".status-step").forEach(function (b) { b.setAttribute("aria-checked", "false"); });
        btn.setAttribute("aria-checked", "true");
        state.pendingStatus = btn.getAttribute("data-status");
      });
    });

    if (thesisForm) {
      thesisForm.addEventListener("submit", async function (ev) {
        ev.preventDefault();
        const fd = new FormData(thesisForm);
        const payload = {
          symbol: state.symbol,
          status: state.pendingStatus,
          title: (fd.get("title") || "").toString().trim(),
          core_logic: (fd.get("core_logic") || "").toString().trim(),
          valuation_view: (fd.get("valuation_view") || "").toString().trim(),
          horizon: (fd.get("horizon") || "").toString().trim(),
        };
        const btn = thesisForm.querySelector('button[type="submit"]');
        ui.busy(btn, true, "保存中…");
        ui.setFormState(stateEl, "", "");
        try {
          const res = await V2.api.post("/api/thesis", payload);
          state.data.thesis = res.thesis;
          if (subStatus) subStatus.textContent = fmt.status(res.thesis.status);
          if (thesisCaption) thesisCaption.textContent = "更新于 " + fmt.date(res.thesis.updated_at);
          ui.setFormState(stateEl, "已保存 " + fmt.localDateTime(), "ok");
        } catch (err) {
          ui.setFormState(stateEl, "保存失败：" + err.message, "error");
        } finally {
          ui.busy(btn, false);
        }
      });
    }

    const assumptionWrap = container.querySelector("#assumption-form-wrap");
    const toggle = container.querySelector("#assumption-toggle");
    const assumptionForm = container.querySelector("#assumption-form");
    const assumptionList = container.querySelector("#assumption-list");
    const assumptionState = container.querySelector("#assumption-state");

    function openAssumptionForm() {
      if (!assumptionWrap) return;
      assumptionWrap.hidden = false;
      const input = assumptionForm && assumptionForm.querySelector('input[name="statement"]');
      if (input) input.focus();
    }
    function closeAssumptionForm() {
      if (assumptionWrap) assumptionWrap.hidden = true;
    }
    if (toggle) toggle.addEventListener("click", function () {
      if (assumptionWrap && assumptionWrap.hidden) openAssumptionForm(); else closeAssumptionForm();
    });
    const cancel = container.querySelector("#assumption-cancel");
    if (cancel) cancel.addEventListener("click", closeAssumptionForm);
    container.addEventListener("click", function (ev) {
      if (ev.target.closest("[data-open-assumption]")) openAssumptionForm();
    });

    if (assumptionForm) {
      assumptionForm.addEventListener("submit", async function (ev) {
        ev.preventDefault();
        const fd = new FormData(assumptionForm);
        const statement = (fd.get("statement") || "").toString().trim();
        if (!statement) {
          ui.setFormState(assumptionState, "假设陈述不能为空。", "error");
          return;
        }
        const payload = {
          symbol: state.symbol,
          scope: "stock",
          statement: statement,
          metric: (fd.get("metric") || "").toString().trim(),
          target: (fd.get("target") || "").toString().trim(),
          deadline: (fd.get("deadline") || "").toString().trim(),
        };
        const btn = assumptionForm.querySelector('button[type="submit"]');
        ui.busy(btn, true, "添加中…");
        ui.setFormState(assumptionState, "", "");
        try {
          const res = await V2.api.post("/api/assumption", payload);
          if (!state.data.thesis) {
            state.data.thesis = { status: state.pendingStatus, assumptions: [] };
          }
          state.data.thesis.assumptions = state.data.thesis.assumptions || [];
          state.data.thesis.assumptions.push(res.assumption);
          assumptionList.innerHTML = assumptionsListHTML(state.data.thesis, asOf);
          assumptionForm.reset();
          ui.setFormState(assumptionState, "已添加假设", "ok");
          if (thesisCaption) thesisCaption.textContent = "更新于 " + fmt.date(new Date().toISOString());
        } catch (err) {
          ui.setFormState(assumptionState, "添加失败：" + err.message, "error");
        } finally {
          ui.busy(btn, false);
        }
      });
    }

    if (assumptionList) {
      assumptionList.addEventListener("click", async function (ev) {
        const row = ev.target.closest(".assumption");
        if (!row) return;
        const id = row.getAttribute("data-assumption-id");
        const rowState = row.querySelector(".a-state");

        if (ev.target.closest(".status-chip")) {
          const chip = ev.target.closest(".status-chip");
          const status = chip.getAttribute("data-status");
          const evidenceInput = row.querySelector("[data-evidence]");
          const evidence = evidenceInput && evidenceInput.value.trim() ? evidenceInput.value.trim() : "";
          const payload = { status: status };
          if (evidence) payload.evidence = evidence;
          try {
            await V2.api.patch("/api/assumption/" + encodeURIComponent(id), payload);
            row.querySelectorAll(".status-chip").forEach(function (c) {
              c.setAttribute("aria-pressed", String(c === chip));
            });
            const item = state.data.thesis && state.data.thesis.assumptions
              ? state.data.thesis.assumptions.find(function (a) { return String(a.id) === String(id); })
              : null;
            if (item) {
              item.status = status;
              if (evidence) item.evidence = evidence;
              item.updated_at = new Date().toISOString().slice(0, 10);
            }
            if (evidence) updateEvidenceLine(row, evidence);
            if (evidenceInput) evidenceInput.value = "";
            ui.setFormState(rowState, "已更新为「" + fmt.assumption(status) + "」", "ok");
          } catch (err) {
            ui.setFormState(rowState, "更新失败：" + err.message, "error");
          }
        }

        if (ev.target.closest("[data-save-evidence]")) {
          const evidenceInput = row.querySelector("[data-evidence]");
          const evidence = evidenceInput ? evidenceInput.value.trim() : "";
          if (!evidence) {
            ui.setFormState(rowState, "先填写证据再保存。", "error");
            return;
          }
          try {
            await V2.api.patch("/api/assumption/" + encodeURIComponent(id), { evidence: evidence });
            const item = state.data.thesis && state.data.thesis.assumptions
              ? state.data.thesis.assumptions.find(function (a) { return String(a.id) === String(id); })
              : null;
            if (item) item.evidence = evidence;
            updateEvidenceLine(row, evidence);
            if (evidenceInput) evidenceInput.value = "";
            ui.setFormState(rowState, "证据已保存", "ok");
          } catch (err) {
            ui.setFormState(rowState, "保存失败：" + err.message, "error");
          }
        }
      });
    }

    const decisionForm = container.querySelector("#decision-form");
    const decisionState = container.querySelector("#decision-state");
    const decisionTimeline = container.querySelector("#decision-timeline");
    if (decisionForm) {
      decisionForm.addEventListener("submit", async function (ev) {
        ev.preventDefault();
        const fd = new FormData(decisionForm);
        const logic = (fd.get("logic") || "").toString().trim();
        if (!logic) {
          ui.setFormState(decisionState, "请写下这次决策的理由。", "error");
          return;
        }
        const payload = {
          symbol: state.symbol,
          action: (fd.get("action") || "watch").toString(),
          price: Number(fd.get("price")) || state.data.stock.price,
          weight_pct: Number(fd.get("weight_pct")) || 0,
          logic: logic,
          kill_switch: (fd.get("kill_switch") || "").toString().trim(),
        };
        const btn = decisionForm.querySelector('button[type="submit"]');
        ui.busy(btn, true, "记录中…");
        ui.setFormState(decisionState, "", "");
        try {
          const res = await V2.api.post("/api/decision", payload);
          state.data.decisions = state.data.decisions || [];
          state.data.decisions.unshift(res.decision);
          decisionTimeline.innerHTML = timelineHTML(state.data);
          decisionForm.querySelector('[name="logic"]').value = "";
          decisionForm.querySelector('[name="kill_switch"]').value = "";
          // 同步头部状态与持仓摘要，避免用户以为状态没变
          const nextStatus = payload.action === "buy" || payload.action === "add" ? "holding"
            : payload.action === "exit" ? "closed" : payload.action === "reduce" ? "reduced" : "watch";
          if (subStatus) subStatus.textContent = fmt.status(nextStatus);
          container.querySelectorAll(".status-step").forEach(function (b) {
            b.setAttribute("aria-checked", String(b.getAttribute("data-status") === nextStatus));
          });
          const posEl = container.querySelector("#sub-position");
          if (posEl && (payload.action === "buy" || payload.action === "add")) {
            posEl.textContent = "持仓 · 成本 " + fmt.price(payload.price) + " · 仓位 " + payload.weight_pct.toFixed(1) + "%";
          } else if (posEl && payload.action === "exit") {
            posEl.textContent = "已清仓";
          }
          ui.setFormState(decisionState, "决策已记录，快照 " + (res.decision.snapshot_hash || "").slice(0, 8), "ok");
        } catch (err) {
          ui.setFormState(decisionState, "记录失败：" + err.message, "error");
        } finally {
          ui.busy(btn, false);
        }
      });
    }

    const select = container.querySelector("#stock-select");
    if (select) {
      select.addEventListener("change", function () {
        location.hash = "#/stock/" + encodeURIComponent(select.value);
      });
    }

    const goToForm = location.hash.indexOf("#decision-form") >= 0;
    if (goToForm) {
      const form = container.querySelector("#decision-form");
      if (form) form.scrollIntoView({ block: "center" });
    }
    container.addEventListener("click", function (ev) {
      const link = ev.target.closest('a[href="#decision-form"]');
      if (link) {
        ev.preventDefault();
        const form = container.querySelector("#decision-form");
        if (form) {
          form.scrollIntoView({ block: "center", behavior: "smooth" });
          const ta = form.querySelector("textarea");
          if (ta) ta.focus();
        }
      }
    });
  }

  async function render(container, ctx) {
    const symbol = ctx.symbol;
    container.innerHTML = '<p class="loading">载入标的…</p>';
    let data;
    let overview;
    let meta = ctx.meta;
    try {
      const stockPromise = V2.api.get("/api/stock/" + encodeURIComponent(symbol));
      data = await stockPromise;
      const chainId = (data.stock && data.stock.chain_id) || "whites";
      const results = await Promise.all([
        V2.api.get("/api/overview?chain=" + encodeURIComponent(chainId)),
        meta ? Promise.resolve(meta) : V2.api.get("/api/meta"),
      ]);
      overview = results[0];
      meta = results[1];
    } catch (err) {
      container.innerHTML =
        '<header class="view-head"><div><p class="meta-line">标的</p><h1 class="display">' +
        fmt.esc(symbol) + "</h1></div></header>" + ui.errorHTML(err.message) +
        '<p style="margin-top:20px"><a class="btn-text" href="#/overview">返回总览</a></p>';
      return;
    }
    if (!data || !data.stock) {
      container.innerHTML = ui.errorHTML("未找到标的 " + symbol, false);
      return;
    }
    if (!data.stock.valuation_basis) {
      const chainInfo = ((ctx.chains || [])).find(function (c) { return c.id === data.stock.chain_id; });
      data.stock.valuation_basis = (chainInfo && chainInfo.valuation_basis) || "pe";
    }
    state = {
      data: data,
      overview: overview,
      meta: meta,
      symbol: symbol,
      pendingStatus: data.thesis ? data.thesis.status : "watch",
    };
    container.innerHTML = viewHTML(data, overview, meta);
    const basis = data.stock.valuation_basis || "pe";
    V2.charts.price(container.querySelector("#chart-price"), data.price);
    V2.charts.valuationPercentile(container.querySelector("#chart-pe"), data.valuation, {
      basis: basis,
      label: fmt.basisLabel(basis),
    });
    V2.charts.financials(container.querySelector("#chart-fin"), data.financials);
    bind(container, ctx);
    if (ctx.onTitle) ctx.onTitle(data.stock.name);
    if (ctx.onSymbol) ctx.onSymbol(symbol);
    if (ctx.onChain) ctx.onChain(data.stock.chain_id);
  }

  V2.views = V2.views || {};
  V2.views.stock = { render: render };
})();
