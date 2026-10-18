/* 外壳：hash 路由（总览 / 单链 / 活文档 / 月度体检）、五链切换、masthead 元数据 */
(function () {
  "use strict";
  const V2 = (window.V2 = window.V2 || {});
  const fmt = V2.fmt;

  const view = document.getElementById("main");
  const chainNav = document.getElementById("chain-nav");
  const metaAsOf = document.getElementById("meta-asof");
  const metaBench = document.getElementById("meta-bench");
  const conn = document.getElementById("conn-state");
  const connText = document.getElementById("conn-text");
  const banner = document.getElementById("conn-banner");
  const bannerText = document.getElementById("conn-banner-text");
  const retryBtn = document.getElementById("conn-retry");

  const S = {
    meta: null,
    chains: [],
    token: 0,
    lastSymbol: sessionStorage.getItem("v3:last-symbol") || "",
    stockChain: "",
    route: null,
  };

  function parseRoute() {
    const raw = (location.hash || "").replace(/^#\/?/, "");
    const qIndex = raw.indexOf("?");
    const path = qIndex >= 0 ? raw.slice(0, qIndex) : raw;
    const query = new URLSearchParams(qIndex >= 0 ? raw.slice(qIndex + 1) : "");
    const parts = path.split("/").filter(Boolean);
    if (parts[0] === "chain") {
      return { name: "chain", chainId: parts[1] || "whites" };
    }
    if (parts[0] === "stock" && parts[1]) {
      return { name: "stock", symbol: decodeURIComponent(parts[1]) };
    }
    if (parts[0] === "review") {
      return { name: "review", chain: query.get("chain") || "", scope: query.get("scope") || "wide" };
    }
    if (parts[0] === "compare") {
      return { name: "compare", symbols: (query.get("symbols") || "").split(",").filter(Boolean),
               chain: query.get("chain") || "", node: query.get("node") || "" };
    }
    if (parts[0] === "invest") {
      return { name: "invest" };
    }
    return { name: "overview" };
  }

  function chainHref(id) {
    return "#/chain/" + encodeURIComponent(id);
  }

  function renderChains() {
    if (!chainNav) return;
    chainNav.innerHTML = S.chains.map(function (c) {
      return '<a href="' + chainHref(c.id) + '" data-chain="' + fmt.esc(c.id) +
        '" title="' + fmt.esc(c.name) + " · " + c.stocks + " 只\">" + fmt.esc(c.short) + "</a>";
    }).join("");
  }

  function activeChainId(route) {
    if (route.name === "chain") return route.chainId;
    if (route.name === "stock") return S.stockChain;
    if (route.name === "review") return route.chain || "";
    return "";
  }

  function setNav(route) {
    document.querySelectorAll(".mainnav [data-nav]").forEach(function (a) {
      const key = a.getAttribute("data-nav");
      const active = (key === "overview" && route.name === "overview") ||
        (key === "review" && route.name === "review") ||
        (key === "compare" && route.name === "compare") ||
        (key === "invest" && route.name === "invest");
      if (active) a.setAttribute("aria-current", "page");
      else a.removeAttribute("aria-current");
    });
    const active = activeChainId(route);
    if (chainNav) {
      chainNav.querySelectorAll("[data-chain]").forEach(function (a) {
        if (a.getAttribute("data-chain") === active) a.setAttribute("aria-current", "page");
        else a.removeAttribute("aria-current");
      });
    }
  }

  function setTitle(name) {
    document.title = name ? name + " · 五链投研台" : "五链投研台 · 月度人工分析";
  }

  function renderMeta(meta) {
    if (!meta) return;
    if (metaAsOf) metaAsOf.textContent = meta.as_of || "—";
    const b = meta.benchmark || {};
    if (metaBench && b.name) {
      const chg = b.pct_20d !== undefined && b.pct_20d !== null ? b.pct_20d : b.chg_20d;
      const pieces = [fmt.esc(b.name)];
      if (b.close !== undefined && b.close !== null) pieces.push(fmt.price(b.close));
      if (chg !== undefined && chg !== null) {
        pieces.push('<span class="' + fmt.signClass(chg) + '">' + fmt.pctSigned(chg) + "</span>");
      }
      metaBench.innerHTML = pieces.join(" ");
    } else if (metaBench) {
      metaBench.textContent = "—";
    }
  }

  function setConn(ok, message) {
    if (!conn) return;
    conn.setAttribute("data-state", ok ? "ok" : "error");
    conn.title = message || (ok ? "后端已连接" : "后端未连接");
    if (connText) connText.textContent = ok ? "已连接" : "未连接";
  }

  async function loadMeta() {
    try {
      const meta = await V2.api.get("/api/meta");
      S.meta = meta;
      S.chains = meta.chains || [];
      renderChains();
      renderMeta(meta);
      setConn(true);
      if (banner) banner.hidden = true;
      return meta;
    } catch (err) {
      setConn(false, err.message);
      if (banner) banner.hidden = false;
      if (bannerText) bannerText.textContent = "后端未连接：" + err.message + "（" + V2.api.base() + "）";
      return null;
    }
  }

  function normalizeRoute(route) {
    if (route.name === "chain" && S.chains.length) {
      const known = S.chains.some(function (c) { return c.id === route.chainId; });
      if (!known) return { name: "overview" };
    }
    return route;
  }

  async function route() {
    const route = normalizeRoute(parseRoute());
    if (!location.hash) history.replaceState(null, "", "#/overview");
    if (route.name === "chain" && !/^#\/chain\/[^/]+/.test(location.hash || "")) {
      history.replaceState(null, "", chainHref(route.chainId));
    }
    S.route = route;
    if (route.name === "chain" || route.name === "overview") S.stockChain = "";
    setNav(route);

    const token = ++S.token;
    document.querySelectorAll(".js-plotly-plot").forEach(function (el) {
      V2.charts.purge(el);
    });
    view.innerHTML = '<p class="loading">载入中…</p>';
    const ctx = {
      meta: S.meta,
      chains: S.chains,
      chainId: route.chainId,
      chain: route.chain || "",
      node: route.node || "",
      scope: route.scope || "wide",
      symbol: route.symbol,
      symbols: route.symbols || [],
      onTitle: setTitle,
      onChain: function (chainId) {
        S.stockChain = chainId || "";
        setNav(S.route || route);
      },
      onSymbol: function (symbol) {
        S.lastSymbol = symbol;
        sessionStorage.setItem("v3:last-symbol", symbol);
      },
    };
    try {
      if (route.name === "stock") await V2.views.stock.render(view, ctx);
      else if (route.name === "chain") await V2.views.chain.render(view, ctx);
      else if (route.name === "review") await V2.views.review.render(view, ctx);
      else if (route.name === "compare") await V2.views.compare.render(view, ctx);
      else if (route.name === "invest") await V2.views.invest.render(view, ctx);
      else await V2.views.overview.render(view, ctx);
    } catch (err) {
      if (token === S.token) view.innerHTML = V2.ui.errorHTML("页面渲染失败：" + err.message);
      return;
    }
    if (token !== S.token) return;
    window.scrollTo(0, 0);
    try { view.focus({ preventScroll: true }); } catch (_) { /* noop */ }
  }

  function reload() {
    loadMeta().then(route, route);
  }

  function init() {
    document.addEventListener("click", function (ev) {
      const retry = ev.target.closest("[data-retry]");
      if (retry) {
        ev.preventDefault();
        reload();
      }
    });
    if (retryBtn) retryBtn.addEventListener("click", reload);
    window.addEventListener("hashchange", route);
    loadMeta().then(route, route);
  }

  V2.app = {
    reload: reload,
    route: route,
    getMeta: function () { return S.meta; },
    getChains: function () { return S.chains; },
  };
  V2.views = V2.views || {};

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
