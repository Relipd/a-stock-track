/* 投资页：#/invest —— 加星 → 逻辑评语 → 投资加星 → 投资决策（结算后自动取消投资星） */
(function () {
  "use strict";
  const V2 = (window.V2 = window.V2 || {});
  const fmt = V2.fmt;
  const ui = V2.ui;

  function today() {
    const d = new Date();
    const p = function (n) { return String(n).padStart(2, "0"); };
    return d.getFullYear() + "-" + p(d.getMonth() + 1) + "-" + p(d.getDate());
  }

  function readCapital() {
    const raw = Number(localStorage.getItem("v2_invest_capital"));
    return raw > 0 ? raw : 1000000;
  }

  function summaryValues(positions, capital) {
    let invested = 0;
    let market = 0;
    let weight = 0;
    (positions || []).forEach(function (p) {
      const w = Number(p.weight_pct) || 0;
      const entry = Number(p.entry_price) || 0;
      const price = Number(p.price) || entry;
      const cost = capital * w / 100;
      invested += cost;
      market += cost * (entry > 0 ? price / entry : 1);
      weight += w;
    });
    return { invested: invested, market: market, pnl: market - invested, weight: weight, cash: capital - invested };
  }

  function money(v) {
    return fmt.num((Number(v) || 0) / 1e4, 1) + " 万";
  }

  function summaryHTML(master) {
    const capital = readCapital();
    const v = summaryValues(master.positions, capital);
    const pnlTone = v.pnl > 0 ? "up" : v.pnl < 0 ? "down" : "";
    return (
      '<section class="panel invest-summary"><div class="panel-head"><h2 class="section-h2">我的筹码</h2>' +
      '<p class="caption">按账户本金与仓位估算，不是券商实盘</p></div>' +
      '<div class="summary-grid">' +
      '<label class="field summary-capital"><span class="field-label">账户本金（元）</span>' +
      '<input class="input num" id="invest-capital" type="number" min="1000" step="10000" value="' + capital + '"></label>' +
      '<div class="summary-item"><span>总筹码（市值）</span><strong class="num" id="sum-market">' + money(v.market) + "</strong></div>" +
      '<div class="summary-item"><span>总投入</span><strong class="num" id="sum-invested">' + money(v.invested) + "</strong></div>" +
      '<div class="summary-item"><span>总仓位</span><strong class="num" id="sum-weight">' + fmt.num(v.weight, 1) + "%</strong></div>" +
      '<div class="summary-item"><span>总浮盈</span><strong class="num ' + pnlTone + '" id="sum-pnl">' +
      (v.pnl > 0 ? "+" : "") + money(v.pnl) + "</strong></div>" +
      '<div class="summary-item"><span>现金/可用</span><strong class="num" id="sum-cash">' + money(v.cash) + "</strong></div>" +
      '<div class="summary-item"><span>持仓</span><strong class="num" id="sum-count">' + (master.positions || []).length + " 只</strong></div>" +
      "</div></section>"
    );
  }

  function paintSummary(container, positions, capital) {
    const v = summaryValues(positions, capital);
    const set = function (id, text, tone) {
      const el = container.querySelector(id);
      if (!el) return;
      el.textContent = text;
      el.classList.toggle("up", tone === "up");
      el.classList.toggle("down", tone === "down");
    };
    set("#sum-market", money(v.market));
    set("#sum-invested", money(v.invested));
    set("#sum-weight", fmt.num(v.weight, 1) + "%");
    set("#sum-pnl", (v.pnl > 0 ? "+" : "") + money(v.pnl), v.pnl > 0 ? "up" : v.pnl < 0 ? "down" : "");
    set("#sum-cash", money(v.cash));
  }

  function noteBlock(item) {
    const star = item.star;
    const has = Boolean((star.logic_note || "").trim());
    return (
      '<div class="star-note">' +
      '<div data-note-view><p class="star-note-body">' +
      (has ? fmt.esc(star.logic_note) : "还没有评语。写下核心逻辑、反方观点和估值锚点。") + "</p>" +
      '<p class="star-note-date">首次记录 ' + fmt.esc(star.logic_date || "—") +
      " · 更新 " + fmt.esc(star.logic_updated_at || "—") + "</p>" +
      '<div class="star-note-actions"><button type="button" class="btn-text" data-note-edit>' +
      (has ? "修改" : "写评语") + "</button>" +
      (has && !star.investment_star ? '<button type="button" class="btn-text danger" data-note-delete>删除</button>' : "") +
      (has && star.investment_star ? '<span class="caption">投资加星期间评语锁定</span>' : "") +
      "</div></div>" +
      '<form class="star-note-form" data-note-form hidden>' +
      '<textarea class="input" data-note rows="3" placeholder="为什么关注它？核心变量、反方观点、估值锚点。">' +
      fmt.esc(star.logic_note || "") + "</textarea>" +
      '<div class="star-note-actions"><button type="button" class="btn" data-save-note>保存评语</button>' +
      '<button type="button" class="btn-text" data-note-cancel>取消</button>' +
      '<span class="form-state" data-note-state role="status"></span></div></form></div>'
    );
  }

  function decisionForm(item) {
    const s = item.stock;
    return (
      '<form class="invest-form" data-invest-form>' +
      '<div class="form-grid cols-3">' +
      '<label class="field"><span class="field-label">决策日期</span>' +
      '<input class="input" type="date" name="date" value="' + today() + '"></label>' +
      '<label class="field"><span class="field-label">成交价</span>' +
      '<input class="input num" type="number" step="0.01" min="0.01" name="price" value="' + fmt.num(s.price, 2) + '"></label>' +
      '<label class="field"><span class="field-label">仓位 %</span>' +
      '<input class="input num" type="number" step="0.1" min="0" name="weight_pct" value="0"></label>' +
      '</div>' +
      '<label class="field"><span class="field-label">动作</span>' +
      '<select class="input" name="action"><option value="buy">买入</option><option value="add">加仓</option></select></label>' +
      '<label class="field"><span class="field-label">理由</span>' +
      '<textarea class="input" name="logic" rows="2" placeholder="为什么在这个价格做这个动作。">' + fmt.esc(item.star.logic_note || "") + "</textarea></label>" +
      '<label class="field"><span class="field-label">证伪条件</span>' +
      '<textarea class="input" name="kill_switch" rows="2" placeholder="出现什么情况说明这次判断错了。"></textarea></label>' +
      '<div class="star-note-actions"><button type="submit" class="btn btn-primary">记录并结算</button>' +
      '<span class="form-state" data-invest-state role="status"></span></div>' +
      "</form>"
    );
  }

  function starCard(item) {
    const star = item.star;
    const s = item.stock;
    const locked = Number(star.investment_star) === 1;
    const hasNote = Boolean((star.logic_note || "").trim());
    return (
      '<section class="panel star-card" data-symbol="' + fmt.esc(s.symbol) + '">' +
      '<div class="star-card-head"><div>' +
      '<p class="meta-line"><a class="chain-link-inline" href="#/stock/' + encodeURIComponent(s.symbol) + '">' +
      fmt.esc(s.name) + "</a> · " + fmt.esc(s.chain_name) + " · " + fmt.esc(s.node_name) + "</p>" +
      '<p class="star-meta">加星 ' + fmt.esc(star.starred_at || "—") + " · 现价 " + fmt.price(s.price) +
      " · 20 日 " + fmt.pctSigned(s.pct_20d, 1) +
      (star.decision_date ? " · 已结算 " + fmt.esc(star.decision_date) + " @ " + fmt.price(star.decision_price) : "") + "</p></div>" +
      '<div class="star-card-actions">' +
      (locked
        ? '<span class="star-pill">投资加星中</span>'
        : '<button type="button" class="btn-text" data-star-remove>撤星</button>') +
      "</div></div>" +
      noteBlock(item) +
      (locked
        ? '<div class="invest-box"><p class="caption">投资加星已开启 · 逻辑评语已锁定为前置条件</p>' +
          decisionForm(item) +
          '<button type="button" class="btn-text" data-invest-toggle="0">取消投资加星</button></div>'
        : '<div class="star-note-actions"><button type="button" class="btn" data-invest-toggle="1"' +
          (hasNote ? "" : " disabled") + ">投资加星</button>" +
          '<span class="caption">先写逻辑评语，再打开投资决策</span></div>') +
      '<p class="form-state" data-star-state role="status"></p>' +
      "</section>"
    );
  }

  function archivedCard(item) {
    const s = item.stock;
    return (
      '<li class="archived-row"><div><a class="stock-name" href="#/stock/' + encodeURIComponent(s.symbol) + '">' +
      fmt.esc(s.name) + '</a><span class="chain-short">' + fmt.esc(s.chain_name) + " · " + fmt.esc(s.node_name) + "</span></div>" +
      "<p>" + fmt.esc(item.star.logic_note || "") + "</p>" +
      '<span class="caption">加星 ' + fmt.esc(item.star.starred_at || "—") + " · 逻辑日期 " + fmt.esc(item.star.logic_date || "—") + "</span></li>"
    );
  }

  async function render(container, ctx) {
    container.innerHTML = '<p class="loading">载入投资池…</p>';
    let stars;
    let master;
    try {
      const res = await Promise.all([
        V2.api.get("/api/stars"), V2.api.get("/api/master"),
      ]);
      stars = res[0];
      master = res[1];
    } catch (err) {
      container.innerHTML = ui.errorHTML("载入投资池失败：" + err.message);
      return;
    }
    const starred = stars.stars || [];
    const archived = stars.archived || [];
    container.innerHTML =
      '<header class="view-head"><div><p class="meta-line">投资 · 加星 → 逻辑评语 → 投资加星 → 决策</p>' +
      '<h1 class="display">投资</h1>' +
      '<p class="lede">加星是关注，投资加星才进入决策；决策结算后投资星自动取消，逻辑评语永久保留。星标与评语保存在本地 data/state.sqlite，重启不会丢失。</p></div></header>' +
      summaryHTML(master) +
      '<section class="star-list"><div class="section-head"><h2 class="section-h2">已加星</h2>' +
      '<p class="caption">' + starred.length + " 只 · 逻辑评语可随时修订</p></div>" +
      (starred.length ? starred.map(starCard).join("") : ui.emptyHTML("还没有加星标的。", "去单链或活文档点击☆加星。")) +
      "</section>" +
      '<section class="star-archived"><div class="section-head"><h2 class="section-h2">已撤星 · 逻辑保留</h2>' +
      '<p class="caption">' + archived.length + " 条 · 不参与投资加星，但保留历史评语</p></div>" +
      (archived.length ? '<ul class="archived-list">' + archived.map(archivedCard).join("") + "</ul>" :
        '<p class="caption">暂无已撤星记录。</p>') +
      "</section>";

    const capitalInput = container.querySelector("#invest-capital");
    if (capitalInput) {
      capitalInput.addEventListener("change", function () {
        const capital = Number(capitalInput.value);
        if (!(capital > 0)) return;
        localStorage.setItem("v2_invest_capital", String(capital));
        paintSummary(container, master.positions || [], capital);
      });
    }

    container.querySelectorAll("[data-star-remove]").forEach(function (btn) {
      btn.addEventListener("click", async function () {
        const card = btn.closest("[data-symbol]");
        try {
          await V2.api.post("/api/star", { symbol: card.getAttribute("data-symbol"), active: false });
          V2.app.route();
        } catch (err) {
          const state = card.querySelector("[data-star-state]");
          if (state) state.textContent = err.message;
        }
      });
    });

    container.querySelectorAll("[data-save-note]").forEach(function (btn) {
      btn.addEventListener("click", async function () {
        const card = btn.closest("[data-symbol]");
        const form = btn.closest("[data-note-form]");
        const note = form.querySelector("[data-note]").value;
        try {
          await V2.api.post("/api/star/note", { symbol: card.getAttribute("data-symbol"), note: note });
          V2.app.route();
        } catch (err) {
          const state = form.querySelector("[data-note-state]");
          if (state) state.textContent = err.message;
        }
      });
    });

    container.querySelectorAll("[data-note-edit]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        const card = btn.closest("[data-symbol]");
        const view = card.querySelector("[data-note-view]");
        const form = card.querySelector("[data-note-form]");
        if (view) view.hidden = true;
        if (form) form.hidden = false;
      });
    });
    container.querySelectorAll("[data-note-cancel]").forEach(function (btn) {
      btn.addEventListener("click", function () {
        const card = btn.closest("[data-symbol]");
        const view = card.querySelector("[data-note-view]");
        const form = card.querySelector("[data-note-form]");
        if (view) view.hidden = false;
        if (form) form.hidden = true;
      });
    });
    container.querySelectorAll("[data-note-delete]").forEach(function (btn) {
      btn.addEventListener("click", async function () {
        const card = btn.closest("[data-symbol]");
        if (!window.confirm("删除这段逻辑评语？历史版本会保留在本地。")) return;
        try {
          await V2.api.del("/api/star/note?symbol=" + encodeURIComponent(card.getAttribute("data-symbol")));
          V2.app.route();
        } catch (err) {
          const state = card.querySelector("[data-note-state]");
          if (state) state.textContent = err.message;
        }
      });
    });

    container.querySelectorAll("[data-invest-toggle]").forEach(function (btn) {
      btn.addEventListener("click", async function () {
        const card = btn.closest("[data-symbol]");
        const active = btn.getAttribute("data-invest-toggle") === "1";
        try {
          await V2.api.post("/api/star/invest", { symbol: card.getAttribute("data-symbol"), active: active });
          V2.app.route();
        } catch (err) {
          const state = card.querySelector("[data-star-state]");
          if (state) state.textContent = err.message;
        }
      });
    });

    container.querySelectorAll("[data-invest-form]").forEach(function (form) {
      form.addEventListener("submit", async function (ev) {
        ev.preventDefault();
        const card = form.closest("[data-symbol]");
        const fd = new FormData(form);
        const state = form.querySelector("[data-invest-state]");
        const payload = {
          symbol: card.getAttribute("data-symbol"),
          date: fd.get("date"),
          price: Number(fd.get("price")),
          weight_pct: Number(fd.get("weight_pct")),
          action: fd.get("action"),
          logic: fd.get("logic"),
          kill_switch: fd.get("kill_switch"),
        };
        try {
          await V2.api.post("/api/invest/decision", payload);
          V2.app.route();
        } catch (err) {
          if (state) state.textContent = err.message;
        }
      });
    });
  }

  V2.views = V2.views || {};
  V2.views.invest = { render: render };
})();
