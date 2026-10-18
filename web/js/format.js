/* 格式化与中文词表 */
(function () {
  "use strict";
  const V2 = (window.V2 = window.V2 || {});

  const STATUS_CN = {
    watch: "观察",
    building: "分批建仓",
    holding: "持有",
    reduced: "已减仓",
    closed: "已结案",
  };
  const ASSUMPTION_CN = {
    pending: "待验证",
    progress: "进行中",
    met: "已兑现",
    invalidated: "已证伪",
  };
  const ASSUMPTION_ORDER = ["pending", "progress", "met", "invalidated"];
  const ACTION_CN = { watch: "观察", buy: "建仓", add: "加仓", reduce: "减仓", exit: "结案" };
  const ROLE_CN = { upstream: "上游", midstream: "中游", downstream: "下游" };

  function isNum(v) {
    return v !== null && v !== undefined && v !== "" && !Number.isNaN(Number(v));
  }

  const fmt = {
    esc: function (value) {
      return String(value === null || value === undefined ? "" : value).replace(/[&<>"']/g, function (ch) {
        return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch];
      });
    },
    price: function (v) {
      if (!isNum(v)) return "—";
      return Number(v).toFixed(2);
    },
    num: function (v, digits) {
      if (!isNum(v)) return "—";
      return Number(v).toFixed(digits === undefined ? 1 : digits);
    },
    pct: function (v, digits) {
      if (!isNum(v)) return "—";
      const d = digits === undefined ? 2 : digits;
      const n = Number(v);
      return (n > 0 ? "+" : "") + n.toFixed(d);
    },
    pctSigned: function (v, digits) {
      if (!isNum(v)) return "—";
      const d = digits === undefined ? 2 : digits;
      const n = Number(v);
      const sign = n > 0 ? "+" : "";
      return sign + n.toFixed(d) + "%";
    },
    ratioPct: function (v, digits) {
      if (!isNum(v)) return "—";
      const d = digits === undefined ? 0 : digits;
      return (Number(v) * 100).toFixed(d) + "%";
    },
    weight: function (v) {
      if (!isNum(v)) return "—";
      return Number(v).toFixed(1) + "%";
    },
    days: function (v) {
      if (!isNum(v)) return "—";
      return Number(v).toFixed(1);
    },
    date: function (iso) {
      return iso ? String(iso).slice(0, 10) : "—";
    },
    dateTime: function (iso) {
      return iso ? String(iso).replace("T", " ").slice(0, 16) : "—";
    },
    localDateTime: function (d) {
      const date = d || new Date();
      const p = function (n) { return String(n).padStart(2, "0"); };
      return date.getFullYear() + "-" + p(date.getMonth() + 1) + "-" + p(date.getDate()) +
        " " + p(date.getHours()) + ":" + p(date.getMinutes());
    },
    timeOnly: function (iso) {
      return iso ? String(iso).replace("T", " ").slice(5, 16) : "—";
    },
    signClass: function (v) {
      if (!isNum(v) || Number(v) === 0) return "flat";
      return Number(v) > 0 ? "up" : "down";
    },
    toneClass: function (v, direction) {
      if (!isNum(v) || !direction || direction === "neutral") return "";
      const n = Number(v);
      if (direction === "inverse") return n < 0 ? "up" : n > 0 ? "down" : "";
      if (direction === "pct_low_good") return n <= 0.2 ? "up" : n >= 0.8 ? "down" : "";
      if (direction === "pct_high_good") return n >= 0.8 ? "up" : n <= 0.2 ? "down" : "";
      if (direction === "cash") return n >= 1.2 ? "up" : n < 1 ? "down" : "";
      return n > 0 ? "up" : n < 0 ? "down" : "";
    },
    rank: function (r) {
      if (!r || !r.rank || !r.n) return "";
      return '<span class="rank-badge" title="同节点排名，1=最好，分母=有效样本">' + r.rank + "/" + r.n + "</span>";
    },
    status: function (key) {
      return STATUS_CN[key] || key || "观察";
    },
    assumption: function (key) {
      return ASSUMPTION_CN[key] || key || "待验证";
    },
    action: function (key) {
      return ACTION_CN[key] || key || "";
    },
    role: function (key) {
      return ROLE_CN[key] || key || "";
    },
    quarterLabel: function (reportDate) {
      const s = String(reportDate || "");
      const year = s.slice(2, 4);
      const month = s.slice(5, 7);
      const q = month === "03" ? 1 : month === "06" ? 2 : month === "09" ? 3 : month === "12" ? 4 : 0;
      return year + "Q" + q;
    },
    monthFromAsOf: function (asOf) {
      return asOf ? String(asOf).slice(0, 7) : new Date().toISOString().slice(0, 7);
    },
    basisLabel: function (basis) {
      return basis === "pb" ? "PB" : "PE";
    },
    basisPct: function (obj, basis) {
      if (!obj) return null;
      if (basis === "pb") return obj.pb_pct_3y !== undefined ? obj.pb_pct_3y : obj.pb_pct;
      return obj.pe_pct_3y !== undefined ? obj.pe_pct_3y : obj.pe_pct;
    },
    basisValue: function (obj, basis) {
      if (!obj) return null;
      return basis === "pb" ? obj.pb : obj.pe_ttm;
    },
    positionStatus: function (key) {
      const map = { open: "持有中", closed: "已结清", watching: "观察" };
      return map[key] || key || "—";
    },
    deadlineInfo: function (deadline, asOf) {
      const dl = String(deadline || "");
      if (!dl) return { text: "未设期限", overdue: false, days: null };
      const end = Date.parse(dl + "T00:00:00Z");
      const ref = Date.parse(String(asOf || dl) + "T00:00:00Z");
      if (Number.isNaN(end) || Number.isNaN(ref)) return { text: dl, overdue: false, days: null };
      const days = Math.round((end - ref) / 86400000);
      if (days < 0) return { text: "逾期 " + Math.abs(days) + " 天", overdue: true, days: days };
      if (days === 0) return { text: "今天到期", overdue: false, days: days, soon: true };
      return { text: days + " 天后到期", overdue: false, days: days, soon: days <= 7 };
    },
  };

  fmt.STATUS_CN = STATUS_CN;
  fmt.ASSUMPTION_CN = ASSUMPTION_CN;
  fmt.ASSUMPTION_ORDER = ASSUMPTION_ORDER;
  fmt.ACTION_CN = ACTION_CN;
  fmt.ROLE_CN = ROLE_CN;
  V2.fmt = fmt;
})();
