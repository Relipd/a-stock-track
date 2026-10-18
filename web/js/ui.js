/* 小部件：错误行、空状态、表单状态、分位条 */
(function () {
  "use strict";
  const V2 = (window.V2 = window.V2 || {});
  const fmt = V2.fmt;

  const ui = {
    errorHTML: function (message, retry) {
      const retryBtn = retry === false
        ? ""
        : '<button type="button" class="btn-text" data-retry>重试</button>';
      return '<p class="error-line" role="alert"><span>' + fmt.esc(message) + "</span>" + retryBtn + "</p>";
    },
    emptyHTML: function (text, actionHTML) {
      return '<p class="empty">' + fmt.esc(text) + (actionHTML || "") + "</p>";
    },
    setFormState: function (el, message, kind) {
      if (!el) return;
      el.textContent = message || "";
      el.classList.remove("is-ok", "is-error");
      if (kind === "ok") el.classList.add("is-ok");
      if (kind === "error") el.classList.add("is-error");
    },
    meter: function (value) {
      if (value === null || value === undefined || Number.isNaN(Number(value))) return "";
      const pct = Math.max(0, Math.min(1, Number(value)));
      const cls = pct > 0.8 ? " extreme-high" : pct < 0.2 ? " extreme-low" : "";
      return '<span class="meter' + cls + '"><i style="width:' + (pct * 100).toFixed(1) + '%"></i></span>';
    },
    busy: function (button, busy, label) {
      if (!button) return;
      if (busy) {
        button.dataset.idleLabel = button.textContent;
        button.disabled = true;
        button.textContent = label || "提交中…";
      } else {
        button.disabled = false;
        button.textContent = button.dataset.idleLabel || button.textContent;
      }
    },
    download: function (filename, text) {
      const blob = new Blob([text], { type: "text/markdown;charset=utf-8" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      setTimeout(function () { URL.revokeObjectURL(url); }, 2000);
    },
  };

  V2.ui = ui;
})();
