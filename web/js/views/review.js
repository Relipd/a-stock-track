/* 月度体检：#/review?chain= */
(function () {
  "use strict";
  const V2 = (window.V2 = window.V2 || {});
  const fmt = V2.fmt;
  const ui = V2.ui;

  const GROUPS = ["pending", "progress", "met", "invalidated"];
  const KIND_CN = { valuation: "估值", assumption: "假设", thesis: "逻辑", price: "价格" };

  let currentMonth = null;
  let currentChain = "";
  let currentScope = "wide";
  let dirty = false;

  function monthOf(ctx) {
    const meta = ctx && ctx.meta;
    if (currentMonth) return currentMonth;
    return fmt.monthFromAsOf(meta && meta.as_of);
  }

  function summaryHTML(review) {
    const s = review.summary || {};
    const rawPnl = s.pnl_pct !== undefined && s.pnl_pct !== null ? s.pnl_pct : s.weighted_pnl;
    const pnl = Number(rawPnl);
    const allocation = review.allocation || [];
    const maxWeight = allocation.reduce(function (m, a) { return Math.max(m, Number(a.weight) || 0); }, 0);
    const bars = allocation.map(function (a) {
      const width = maxWeight ? (Number(a.weight) / maxWeight) * 100 : 0;
      return (
        '<div class="allocation-row">' +
        '<span class="allocation-label">' + fmt.esc(a.name) + "</span>" +
        '<div class="allocation-bar"><i style="width:' + width.toFixed(1) + '%"></i></div>' +
        '<span class="weight">' + fmt.weight(a.weight) + "</span>" +
        "</div>"
      );
    }).join("");
    return (
      '<div>' +
      '<dl class="big-figures">' +
      '<div class="big-figure"><dt>持仓</dt><dd class="num">' + (s.positions || 0) +
      '<span class="unit">只</span></dd></div>' +
      '<div class="big-figure"><dt>总仓位</dt><dd class="num">' + fmt.num(s.total_weight, 1) +
      '<span class="unit">%</span></dd></div>' +
      '<div class="big-figure"><dt>浮动盈亏</dt><dd class="num ' + (pnl > 0 ? "up" : pnl < 0 ? "down" : "") + '">' +
      (pnl > 0 ? "+" : "") + fmt.num(rawPnl, 1) + '<span class="unit">%</span></dd></div>' +
      '<div class="big-figure"><dt>逻辑卡</dt><dd class="num">' + (s.theses || 0) +
      '<span class="unit">张</span></dd></div>' +
      "</dl>" +
      '<p class="caption">浮动盈亏按仓位加权；数据由持仓记录与最新收盘价推算。</p>' +
      '<p class="scope-counts">' + (currentScope === "narrow" ? "窄口径 · 投资" : "宽口径 · 全部加星") +
      "：加星 " + (s.stars || 0) + " 只 · 投资 " + (s.invest || 0) + " 只 · 观察 " + (s.watch || 0) + " 只</p>" +
      "</div>" +
      '<div class="allocation">' +
      '<div class="section-head"><h2 class="section-h2">' + (currentChain ? "节点分布" : "行业分布") + "</h2>" +
      '<p class="caption">条长按最大仓位归一</p></div>' +
      (bars || '<p class="empty">本月没有持仓。</p>') +
      "</div>"
    );
  }

  function chainTag(name) {
    return name ? '<span class="chain-tag">' + fmt.esc(name) + "</span>" : "";
  }

  function watchlistHTML(review) {
    const rows = review.watchlist || [];
    if (!rows.length) return '<p class="empty">当前口径没有加星标的。</p>';
    const group = function (stage, title) {
      const list = rows.filter(function (r) { return r.stage === stage; });
      if (!list.length) return "";
      return '<div class="watch-group"><h3 class="board-stage-title">' + title +
        '<span class="count">' + list.length + " 只</span></h3>" +
        list.map(function (r) {
          return '<a class="watch-row" href="#/stock/' + encodeURIComponent(r.symbol) + '">' +
            '<span class="watch-name">' + fmt.esc(r.name) +
            '<em>' + fmt.esc(r.node_name || r.chain_name || "") + "</em></span>" +
            '<span class="watch-price num">' + fmt.price(r.price) + "</span>" +
            '<span class="watch-chg ' + fmt.signClass(r.pct_20d) + '">20 日 ' + fmt.pctSigned(r.pct_20d, 1) + "</span>" +
            '<span class="watch-chg ' + fmt.signClass(r.pct_60d) + '">60 日 ' + fmt.pctSigned(r.pct_60d, 1) + "</span>" +
            '<span class="watch-note">' + fmt.esc(r.note || "尚无评语") + "</span></a>";
        }).join("") + "</div>";
    };
    return group("invest", "投资") + group("watch", "加星");
  }

  function boardHTML(review, asOf) {
    const board = review.board || [];
    const groupList = function (list) {
    const groups = GROUPS.map(function (status) {
      const rows = [];
      list.forEach(function (stock) {
        (stock.assumptions || []).forEach(function (a) {
          if (a.status === status) {
            rows.push({
              name: stock.name, symbol: stock.symbol, statement: a.statement,
              deadline: a.deadline, chain_name: stock.chain_name,
            });
          }
        });
      });
      if (!rows.length) return "";
      const items = rows.map(function (r) {
        const dl = fmt.deadlineInfo(r.deadline, asOf);
        let extra = "";
        if ((status === "pending" || status === "progress") && dl.days !== null && dl.days !== undefined) {
          extra = dl.days < 0 ? "逾期 " + Math.abs(dl.days) + " 天" : dl.days === 0 ? "今天到期" : dl.days + " 天后";
        }
        return (
          '<div class="board-row">' +
          '<a class="board-name" href="#/stock/' + encodeURIComponent(r.symbol) + '">' + fmt.esc(r.name) + "</a>" +
          (currentChain ? "" : chainTag(r.chain_name)) +
          '<span class="board-statement">' + fmt.esc(r.statement) + "</span>" +
          '<span class="board-deadline' + (dl.overdue ? " overdue" : "") + '">' +
          (r.deadline ? fmt.esc(fmt.date(r.deadline)) + (extra ? " · " + extra : "") : "未设期限") +
          "</span></div>"
        );
      }).join("");
      return (
        '<div class="board-group">' +
        '<div class="board-group-head"><h3>' + fmt.assumption(status) + "</h3>" +
        '<span class="count">' + rows.length + " 条</span></div>" + items + "</div>"
      );
    }).filter(Boolean).join("");
    return groups;
    };
    const invest = board.filter(function (s) { return s.stage === "invest"; });
    const watch = board.filter(function (s) { return s.stage !== "invest"; });
    const part = function (title, list) {
      if (!list.length) return "";
      return '<div class="board-stage"><h3 class="board-stage-title">' + title +
        '<span class="count">' + list.length + " 只</span></h3>" + groupList(list) + "</div>";
    };
    const out = part("投资", invest) + part("加星", watch);
    return out || ui.emptyHTML("这个月还没有加星标的的假设记录。先去加星，再写可以被证伪的判断。");
  }

  function deadlinesHTML(review) {
    const rows = review.deadlines || [];
    if (!rows.length) return '<p class="empty">未来一个月没有到期假设。</p>';
    return rows.map(function (r) {
      const cls = r.days_left < 0 ? "overdue" : r.days_left <= 7 ? "soon" : "";
      const text = r.days_left < 0 ? "逾期 " + Math.abs(r.days_left) + " 天"
        : r.days_left === 0 ? "今天到期" : r.days_left + " 天后";
      return (
        '<div class="deadline-row">' +
        '<a class="deadline-name" href="#/stock/' + encodeURIComponent(r.symbol) + '">' + fmt.esc(r.name) + "</a>" +
        '<span class="deadline-days ' + cls + '">' + text + "</span>" +
        '<span class="deadline-meta">' +
        (currentChain ? "" : fmt.esc(r.chain_name || "") + " · ") +
        fmt.esc(r.statement) + " · 截止 " + fmt.esc(fmt.date(r.deadline)) + "</span>" +
        "</div>"
      );
    }).join("");
  }

  function flagPct(r) {
    return r.pct !== undefined && r.pct !== null ? r.pct : r.pe_pct_3y;
  }

  function flagRowHTML(r) {
    const high = r.side === "high";
    const label = fmt.basisLabel(r.basis || "pe");
    return (
      '<div class="flag-row">' +
      '<a class="flag-name" href="#/stock/' + encodeURIComponent(r.symbol) + '">' + fmt.esc(r.name) + "</a>" +
      (currentChain ? "" : chainTag(r.chain_name)) +
      '<span class="flag-pct ' + (high ? "high" : "low") + '">' + fmt.ratioPct(flagPct(r)) +
      '<span class="flag-side">' + (high ? "偏高" : "偏低") + "</span></span>" +
      '<span class="flag-meta">' + label + " 分位" + (high ? "高位" : "低位") +
      " · 逐只核对逻辑</span></div>"
    );
  }

  function flagTotals(review) {
    const rows = review.valuation_flags || [];
    const t = review.valuation_flag_totals;
    if (t && t.high !== undefined) {
      return { high: Number(t.high) || 0, low: Number(t.low) || 0 };
    }
    return {
      high: rows.filter(function (r) { return r.side === "high"; }).length,
      low: rows.filter(function (r) { return r.side === "low"; }).length,
    };
  }

  function flagsHTML(review) {
    const rows = review.valuation_flags || [];
    const totals = flagTotals(review);
    if (!rows.length) {
      return totals.high + totals.low === 0
        ? '<p class="empty">本月没有已跟踪标的处于极端分位。</p>'
        : '<p class="empty">暂无可列出的极端标的。</p>';
    }
    const highRows = rows.filter(function (r) { return r.side === "high"; })
      .sort(function (a, b) { return flagPct(b) - flagPct(a); }).slice(0, 8);
    const lowRows = rows.filter(function (r) { return r.side === "low"; })
      .sort(function (a, b) { return flagPct(a) - flagPct(b); }).slice(0, 8);
    const group = function (title, list, total) {
      if (!list.length) return "";
      return (
        '<div class="flag-group">' +
        '<div class="flag-group-head"><h3>' + title + "</h3>" +
        '<span class="count">显示 ' + list.length + " / 共 " + total + " 只</span></div>" +
        '<div class="flags-grid">' + list.map(flagRowHTML).join("") + "</div></div>"
      );
    };
    return group("高位 ≥80%", highRows, totals.high) + group("低位 ≤20%", lowRows, totals.low);
  }

  function decisionsHTML(review, nameOf) {
    const rows = review.decisions || [];
    if (!rows.length) return '<p class="empty">本月还没有决策记录。</p>';
    return rows.map(function (d) {
      const price = d.price !== undefined && d.price !== null && d.price !== "" ? fmt.price(d.price) : "";
      const name = nameOf[d.symbol] || d.name || d.symbol || "";
      return (
        '<div class="deadline-row">' +
        '<span class="deadline-name">' + fmt.esc(name) + " · " + fmt.action(d.action) + "</span>" +
        '<span class="deadline-days">' + fmt.esc(price) + "</span>" +
        '<span class="deadline-meta">' +
        (currentChain ? "" : fmt.esc(d.chain_name || "") + " · ") +
        fmt.esc(d.logic || "") + " · " + fmt.esc(fmt.timeOnly(d.created_at)) + "</span>" +
        "</div>"
      );
    }).join("");
  }

  function inboxHTML(inbox, symbols) {
    const allowed = new Set(symbols || []);
    const rows = (inbox || []).filter(function (a) {
      return allowed.has(a.symbol) && (!currentChain || a.chain_id === currentChain);
    });
    if (!rows.length) return '<p class="empty">没有待处理提醒。</p>';
    return rows.map(function (a) {
      return (
        '<div class="inbox-row" data-alert-id="' + fmt.esc(a.id) + '">' +
        '<span class="inbox-name">' + fmt.esc(a.name) + " · " +
        fmt.esc(currentChain ? "" : (a.chain_name || "") + " · ") + fmt.esc(KIND_CN[a.kind] || a.kind) + "</span>" +
        '<button type="button" class="btn-text" data-resolve>标记已处理</button>' +
        '<span class="inbox-meta">' + fmt.esc(a.message) + "</span></div>"
      );
    }).join("");
  }

  function chainOptions(chains, selected) {
    const items = ['<option value="">全部产业链</option>'];
    (chains || []).forEach(function (c) {
      items.push('<option value="' + fmt.esc(c.id) + '"' + (c.id === selected ? " selected" : "") + ">" +
        fmt.esc(c.name) + "</option>");
    });
    return items.join("");
  }

  function viewHTML(review, inbox, meta, month, chains) {
    const asOf = (meta && meta.as_of) || review.as_of || "";
    const label = currentChain
      ? (function () {
        const c = (chains || []).find(function (x) { return x.id === currentChain; });
        return c ? fmt.basisLabel(c.valuation_basis) : "PE";
      })()
      : "PE / PB";
    const totals = flagTotals(review);
    const nameOf = {};
    (review.board || []).forEach(function (b) { nameOf[b.symbol] = b.name; });
    (review.valuation_flags || []).forEach(function (f) { nameOf[f.symbol] = f.name; });
    (review.deadlines || []).forEach(function (d) { nameOf[d.symbol] = d.name; });
    return (
      '<header class="review-head">' +
      '<p class="meta-line"><span>数据截至 ' + fmt.esc(asOf) + '</span>' +
      '<span class="dot">' + fmt.esc(review.chain_name || "全部产业链") + "</span>" +
      '<span class="dot">按月复盘</span></p>' +
      '<div class="review-title-line">' +
      '<h1 class="display">月度体检</h1>' +
      '<div class="review-controls">' +
      '<label class="month-pick">月份<input type="month" id="review-month" value="' + fmt.esc(month) + '"></label>' +
      '<label class="month-pick">产业链<select id="review-chain">' +
      chainOptions(chains, currentChain) + "</select></label>" +
      '<label class="month-pick">口径<select id="review-scope">' +
      '<option value="wide"' + (currentScope === "wide" ? " selected" : "") + ">宽口径 · 全部加星</option>" +
      '<option value="narrow"' + (currentScope === "narrow" ? " selected" : "") + ">窄口径 · 投资</option>" +
      "</select></label>" +
      "</div>" +
      "</div>" +
      '<p class="lede">只体检已加星标的：宽口径看全部加星，窄口径只看投资加星/持仓；其他 200 只不进入体检。</p>' +
      "</header>" +
      '<section class="review-summary">' + summaryHTML(review) + "</section>" +
      '<section class="review-watch"><div class="section-head"><h2 class="section-h2">加星池</h2>' +
      '<p class="caption">只列已加星；投资 = 投资加星/持仓，加星 = 观察</p></div>' +
      watchlistHTML(review) + "</section>" +
      '<div class="review-columns">' +
      "<section>" +
      '<div class="section-head"><h2 class="section-h2">假设看板</h2>' +
      '<p class="caption">按状态分组 · 点击标的名进入活文档</p></div>' +
      boardHTML(review, asOf) +
      '<section class="side-block flags-block"><h2 class="section-h2">估值极端名单</h2>' +
      '<p class="side-note">近三年分位 ≥80% / ≤20%；共 ' + fmt.esc(String(totals.high)) + " 高 / " +
      fmt.esc(String(totals.low)) + " 低，列前 8+8</p>" +
      flagsHTML(review) + "</section>" +
      "</section>" +
      "<aside>" +
      '<section class="side-block"><h2 class="section-h2">到期提醒</h2>' +
      '<p class="side-note">一个月内到期的待验证 / 进行中假设</p>' + deadlinesHTML(review) + "</section>" +
      '<section class="side-block"><h2 class="section-h2">决策流水</h2>' +
      '<p class="side-note">本月记录的全部动作</p>' + decisionsHTML(review, nameOf) + "</section>" +
      '<section class="side-block"><h2 class="section-h2">待处理提醒</h2>' +
      '<p class="side-note">估值与假设触发的提醒，处理后从列表移除</p>' + inboxHTML(inbox, review.symbols) + "</section>" +
      "</aside>" +
      "</div>" +
      '<section class="panel review-editor">' +
      '<div class="panel-head"><h2 class="section-h2">月度复盘</h2>' +
      '<p class="caption">Markdown · 保存后写入本地库 · ' + fmt.esc(review.chain_name || "全部产业链") + "</p></div>" +
      '<label class="field"><span class="field-label sr-only">复盘内容</span>' +
      '<textarea class="input" id="review-md" rows="16" placeholder="写下本月的判断变化、对错与下月待办。">' +
      fmt.esc(review.review_md || "") + "</textarea></label>" +
      '<div class="form-actions">' +
      '<button type="button" class="btn btn-primary" id="review-save">保存复盘</button>' +
      '<button type="button" class="btn btn-ink export" id="review-export">导出 Markdown</button>' +
      '<span class="form-state" id="review-state" role="status"></span>' +
      "</div>" +
      "</section>");
  }

  function updateHash(month, chainId, scope) {
    const params = [];
    if (chainId) params.push("chain=" + encodeURIComponent(chainId));
    if (scope && scope !== "wide") params.push("scope=" + encodeURIComponent(scope));
    const query = params.length ? "?" + params.join("&") : "";
    history.replaceState(null, "", "#/review" + query);
  }

  function bind(container, ctx) {
    const monthInput = container.querySelector("#review-month");
    const chainSelect = container.querySelector("#review-chain");
    const scopeSelect = container.querySelector("#review-scope");
    const md = container.querySelector("#review-md");
    const saveBtn = container.querySelector("#review-save");
    const exportBtn = container.querySelector("#review-export");
    const reviewState = container.querySelector("#review-state");
    const inbox = container.querySelector("aside");

    if (md) md.addEventListener("input", function () { dirty = true; });

    function confirmDirty() {
      if (!dirty) return true;
      return window.confirm("当前复盘尚未保存，切换会丢失修改。继续？");
    }

    if (monthInput) {
      monthInput.addEventListener("change", function () {
        const next = monthInput.value;
        if (!next || next === currentMonth) return;
        if (!confirmDirty()) {
          monthInput.value = currentMonth;
          return;
        }
        dirty = false;
        currentMonth = next;
        updateHash(currentMonth, currentChain, currentScope);
        render(container, Object.assign({}, ctx, { chain: currentChain, scope: currentScope }));
      });
    }

    if (chainSelect) {
      chainSelect.addEventListener("change", function () {
        const next = chainSelect.value;
        if (next === currentChain) return;
        if (!confirmDirty()) {
          chainSelect.value = currentChain;
          return;
        }
        dirty = false;
        currentChain = next;
        updateHash(currentMonth, currentChain, currentScope);
        render(container, Object.assign({}, ctx, { chain: currentChain, scope: currentScope }));
      });
    }

    if (scopeSelect) {
      scopeSelect.addEventListener("change", function () {
        const next = scopeSelect.value;
        if (next === currentScope) return;
        if (!confirmDirty()) {
          scopeSelect.value = currentScope;
          return;
        }
        dirty = false;
        currentScope = next;
        updateHash(currentMonth, currentChain, currentScope);
        render(container, Object.assign({}, ctx, { chain: currentChain, scope: currentScope }));
      });
    }

    if (saveBtn) {
      saveBtn.addEventListener("click", async function () {
        const content = md ? md.value : "";
        ui.busy(saveBtn, true, "保存中…");
        ui.setFormState(reviewState, "", "");
        try {
          await V2.api.post("/api/review", {
            month: currentMonth, chain_id: currentChain, scope: currentScope, content_md: content,
          });
          dirty = false;
          ui.setFormState(reviewState, "已保存 " + fmt.localDateTime(), "ok");
        } catch (err) {
          ui.setFormState(reviewState, "保存失败：" + err.message, "error");
        } finally {
          ui.busy(saveBtn, false);
        }
      });
    }

    if (exportBtn) {
      exportBtn.addEventListener("click", async function () {
        ui.busy(exportBtn, true, "导出中…");
        ui.setFormState(reviewState, "", "");
        const suffix = currentChain ? "-" + currentChain : "";
        const filename = "review-" + currentMonth + suffix + ".md";
        try {
          const text = await V2.api.text("/api/export/review?month=" + encodeURIComponent(currentMonth) +
            (currentChain ? "&chain=" + encodeURIComponent(currentChain) : "") +
            "&scope=" + encodeURIComponent(currentScope));
          V2.ui.download(filename, text);
          ui.setFormState(reviewState, "已导出 " + filename, "ok");
        } catch (err) {
          V2.ui.download(filename, md ? md.value : "");
          ui.setFormState(reviewState, "导出接口不可用，已改为导出当前编辑内容：" + err.message, "error");
        } finally {
          ui.busy(exportBtn, false);
        }
      });
    }

    if (inbox) {
      inbox.addEventListener("click", async function (ev) {
        const btn = ev.target.closest("[data-resolve]");
        if (!btn) return;
        const row = btn.closest(".inbox-row");
        const host = row.parentNode;
        const id = row.getAttribute("data-alert-id");
        btn.disabled = true;
        try {
          await V2.api.post("/api/alerts/" + encodeURIComponent(id) + "/resolve", {});
          row.remove();
          if (host && !host.querySelector(".inbox-row")) {
            host.innerHTML = '<p class="empty">没有待处理提醒。</p>';
          }
        } catch (err) {
          btn.disabled = false;
          ui.setFormState(reviewState, "处理失败：" + err.message, "error");
        }
      });
    }
  }

  async function render(container, ctx) {
    const meta = ctx.meta;
    const month = monthOf(ctx);
    currentMonth = month;
    currentChain = ctx.chain || (V2.app && V2.app.currentReviewChain ? V2.app.currentReviewChain() : "") || "";
    currentScope = ctx.scope || "wide";
    container.innerHTML = '<p class="loading">载入月度数据…</p>';
    let review;
    let inbox;
    try {
      const results = await Promise.all([
        V2.api.get("/api/review?month=" + encodeURIComponent(month) +
          (currentChain ? "&chain=" + encodeURIComponent(currentChain) : "") +
          "&scope=" + encodeURIComponent(currentScope)),
        V2.api.get("/api/inbox"),
      ]);
      review = results[0];
      inbox = results[1] || [];
    } catch (err) {
      container.innerHTML =
        '<header class="review-head"><div><p class="meta-line">月度复盘</p>' +
        '<h1 class="display">月度体检</h1></div></header>' + ui.errorHTML(err.message);
      return;
    }
    dirty = false;
    container.innerHTML = viewHTML(review, inbox, meta, month, ctx.chains || []);
    bind(container, ctx);
    if (ctx.onTitle) ctx.onTitle(currentChain ? "月度体检 · " + (review.chain_name || "") : "月度体检");
    if (ctx.onChain) ctx.onChain(currentChain);
  }

  V2.views = V2.views || {};
  V2.views.review = { render: render };
})();
