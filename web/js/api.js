/* API 客户端：默认同源；file:// 下自动指向本地 mock（8200）；可用 ?api=... 覆盖。 */
(function () {
  "use strict";
  const V2 = (window.V2 = window.V2 || {});
  const MOCK_BASE = "http://127.0.0.1:8200";

  function base() {
    const q = new URLSearchParams(location.search).get("api");
    if (q) return q.replace(/\/+$/, "");
    if (location.protocol === "http:" || location.protocol === "https:") return location.origin;
    return MOCK_BASE;
  }

  class ApiError extends Error {
    constructor(message, status) {
      super(message);
      this.name = "ApiError";
      this.status = status || 0;
    }
  }

  async function request(path, options) {
    const opts = options || {};
    const url = base() + path;
    const controller = new AbortController();
    const timer = setTimeout(function () { controller.abort(); }, 15000);
    const headers = Object.assign({ Accept: "application/json" }, opts.headers || {});
    if (opts.body != null) headers["Content-Type"] = "application/json";
    try {
      const res = await fetch(url, {
        method: opts.method || "GET",
        headers: headers,
        body: opts.body,
        signal: controller.signal,
        cache: "no-store",
      });
      const raw = await res.text();
      let data = null;
      if (raw) {
        try { data = JSON.parse(raw); } catch (_) { data = null; }
      }
      if (!res.ok) {
        const detail = data && (data.detail || data.message);
        throw new ApiError(String(detail || raw.slice(0, 180) || ("HTTP " + res.status)), res.status);
      }
      return data === null && raw ? raw : data;
    } catch (err) {
      if (err instanceof ApiError) throw err;
      if (err && err.name === "AbortError") throw new ApiError("请求超时（15 秒）");
      throw new ApiError("无法连接后端 " + base());
    } finally {
      clearTimeout(timer);
    }
  }

  async function text(path) {
    const url = base() + path;
    const res = await fetch(url, { cache: "no-store" });
    if (!res.ok) throw new ApiError("导出失败：HTTP " + res.status, res.status);
    return res.text();
  }

  V2.api = {
    base: base,
    request: request,
    text: text,
    get: function (path) { return request(path); },
    post: function (path, body) { return request(path, { method: "POST", body: JSON.stringify(body) }); },
    del: function (path) { return request(path, { method: "DELETE" }); },
    patch: function (path, body) { return request(path, { method: "PATCH", body: JSON.stringify(body) }); },
    ApiError: ApiError,
  };
})();
