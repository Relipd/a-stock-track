/* 后台逐步预取：在页面空闲时把总览/五链/全部标的/体检的数据拉进服务端缓存。
   页面本身仍然只是只读；预取失败不影响当前页面。 */
(function () {
  "use strict";
  if (navigator.connection && navigator.connection.saveData) return;
  if (location.hash.indexOf("noprefetch") >= 0) return;

  const done = new Set();
  const queue = [];
  let running = false;

  function add(url) {
    if (!url || done.has(url) || queue.indexOf(url) >= 0) return;
    queue.push(url);
  }

  function sleep(ms) {
    return new Promise(function (resolve) { setTimeout(resolve, ms); });
  }

  async function idle() {
    if (window.requestIdleCallback) {
      await new Promise(function (resolve) { window.requestIdleCallback(resolve, { timeout: 1200 }); });
    } else {
      await sleep(120);
    }
  }

  async function pump() {
    if (running) return;
    running = true;
    while (queue.length) {
      const url = queue.shift();
      if (done.has(url)) continue;
      try {
        const res = await fetch(url, { headers: { Accept: "application/json" } });
        if (res.ok) done.add(url);
      } catch (_) { /* 离线/取消时跳过 */ }
      document.documentElement.setAttribute("data-prefetch", String(done.size));
      await idle();
    }
    running = false;
  }

  async function build() {
    add("/api/master");
    add("/api/universe");
    add("/api/review");
    try {
      const meta = await fetch("/api/meta", { headers: { Accept: "application/json" } }).then(function (r) { return r.json(); });
      (meta.chains || []).forEach(function (c) {
        add("/api/overview?chain=" + encodeURIComponent(c.id));
      });
    } catch (_) { /* noop */ }
    try {
      const uni = await fetch("/api/universe", { headers: { Accept: "application/json" } }).then(function (r) { return r.json(); });
      const symbols = [];
      (uni.chains || []).forEach(function (c) {
        (c.nodes || []).forEach(function (n) {
          (n.instruments || []).forEach(function (i) { symbols.push(i.symbol); });
        });
      });
      symbols.forEach(function (s) { add("/api/stock/" + encodeURIComponent(s)); });
    } catch (_) { /* noop */ }
  }

  window.addEventListener("load", function () {
    setTimeout(function () {
      build().then(pump);
    }, 900);
  });

  window.V2 = window.V2 || {};
  window.V2.prefetch = { done: function () { return done.size; }, queue: function () { return queue.length; } };
})();
