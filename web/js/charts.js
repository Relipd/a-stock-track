/* 本地 Plotly 图表：纸色主题、透明背景、无网格、细轴线、涨跌 token */
(function () {
  "use strict";
  const V2 = (window.V2 = window.V2 || {});

  const T = {
    ink: "#26251e",
    muted: "#5f5d55",
    surface: "#d6d4ce",
    accent: "#2456d6",
    up: "#a33a2b",
    down: "#2f6b4f",
    rule: "rgba(38,37,30,0.28)",
    ruleSoft: "rgba(38,37,30,0.14)",
    inkWash: "rgba(38,37,30,0.05)",
    barWash: "rgba(38,37,30,0.18)",
  };

  const CONFIG = {
    displayModeBar: false,
    responsive: true,
    scrollZoom: false,
    doubleClick: false,
    showTips: false,
  };

  function sans() {
    const v = getComputedStyle(document.documentElement).getPropertyValue("--font-sans").trim();
    return v || "Segoe UI, PingFang SC, Microsoft YaHei, sans-serif";
  }

  function baseLayout(extra) {
    const font = sans();
    const layout = {
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: { family: font, size: 11, color: T.muted },
      margin: { l: 44, r: 14, t: 10, b: 28 },
      hovermode: "x unified",
      hoverlabel: {
        bgcolor: T.surface,
        bordercolor: T.ruleSoft,
        font: { family: font, size: 12, color: T.ink },
        align: "left",
      },
      showlegend: false,
      dragmode: false,
      xaxis: {
        showgrid: false,
        zeroline: false,
        showline: true,
        linecolor: T.rule,
        linewidth: 1,
        ticks: "outside",
        tickcolor: T.rule,
        ticklen: 3,
        tickfont: { size: 10.5, color: T.muted },
        automargin: true,
      },
      yaxis: {
        showgrid: false,
        zeroline: false,
        showline: false,
        ticks: "outside",
        tickcolor: T.rule,
        ticklen: 3,
        tickfont: { size: 10.5, color: T.muted },
        automargin: true,
      },
    };
    return Object.assign(layout, extra || {});
  }

  function available(el) {
    if (window.Plotly) return true;
    el.innerHTML = V2.ui.errorHTML("Plotly 未载入：请确认 web/vendor/plotly.min.js 存在。", false);
    return false;
  }

  function draw(el, traces, layout) {
    if (!el || !available(el)) return;
    window.Plotly.react(el, traces, layout, CONFIG);
  }

  function smooth(values, window) {
    if (!values.length || window <= 1) return values.slice();
    const out = [];
    let sum = 0;
    for (let i = 0; i < values.length; i++) {
      sum += values[i];
      if (i >= window) sum -= values[i - window];
      out.push(i >= window - 1 ? sum / window : values[i]);
    }
    out[out.length - 1] = values[values.length - 1];
    return out;
  }

  const charts = {
    T: T,
    price: function (el, price) {
      if (!price || !price.length) {
        el.innerHTML = V2.ui.emptyHTML("暂无价格序列。", "");
        return;
      }
      const dates = price.map(function (p) { return p.date; });
      const closes = price.map(function (p) { return p.close; });
      const highs = price.map(function (p) { return p.high === null || p.high === undefined ? p.close : p.high; });
      const lows = price.map(function (p) { return p.low === null || p.low === undefined ? p.close : p.low; });
      const last = closes[closes.length - 1];
      const hi = Math.max.apply(null, highs);
      const lo = Math.min.apply(null, lows);
      const traces = [
        {
          type: "scatter",
          mode: "lines",
          x: dates,
          y: closes,
          line: { color: T.ink, width: 1.3 },
          hovertemplate: "%{x|%Y-%m-%d}　收盘 %{y:.2f}<extra></extra>",
        },
        {
          type: "scatter",
          mode: "markers",
          x: [dates[dates.length - 1]],
          y: [last],
          marker: { color: T.ink, size: 5 },
          hoverinfo: "skip",
        },
      ];
      const layout = baseLayout({
        xaxis: Object.assign(baseLayout().xaxis, { tickformat: "%Y-%m", nticks: 6 }),
        yaxis: Object.assign(baseLayout().yaxis, { nticks: 5 }),
        margin: { l: 46, r: 14, t: 10, b: 28 },
        shapes: [
          { type: "line", xref: "paper", x0: 0, x1: 1, y0: hi, y1: hi,
            line: { color: T.muted, width: 1, dash: "dot" } },
          { type: "line", xref: "paper", x0: 0, x1: 1, y0: lo, y1: lo,
            line: { color: T.muted, width: 1, dash: "dot" } },
        ],
        annotations: [
          { xref: "paper", x: 1, y: hi, xanchor: "right", yanchor: "bottom",
            text: "区间最高 " + hi.toFixed(2), showarrow: false,
            font: { size: 10, color: T.muted } },
          { xref: "paper", x: 1, y: lo, xanchor: "right", yanchor: "top",
            text: "区间最低 " + lo.toFixed(2), showarrow: false,
            font: { size: 10, color: T.muted } },
        ],
      });
      draw(el, traces, layout);
    },

    multiPrice: function (el, series, stocks) {
      if (!series || !series.length) {
        el.innerHTML = V2.ui.emptyHTML("暂无对比数据。", "");
        return;
      }
      const colors = [T.ink, T.accent, T.up, T.down, T.muted, "#7a6a4f", "#4f6b7a", "#8a5a3a",
        "#6b5b7a", "#3f7a6b", "#8a7a2f", "#5a4f7a", "#7a3f5a", "#3f5a7a", "#6b7a3f"];
      const bySym = {};
      series.forEach(function (r) {
        (bySym[r.symbol] = bySym[r.symbol] || []).push(r);
      });
      const nameBySym = {};
      (stocks || []).forEach(function (s) { nameBySym[s.symbol] = s.name; });
      const traces = Object.keys(bySym).map(function (sym, i) {
        const rows = bySym[sym];
        return {
          type: "scatter", mode: "lines",
          name: nameBySym[sym] || sym,
          x: rows.map(function (r) { return r.date; }),
          y: rows.map(function (r) { return r.value; }),
          line: { color: colors[i % colors.length], width: 1.4 },
          hovertemplate: "%{x|%Y-%m-%d}<br>" + (nameBySym[sym] || sym) + " %{y:.1f}<extra></extra>",
        };
      });
      const layout = baseLayout({
        xaxis: Object.assign(baseLayout().xaxis, { tickformat: "%Y-%m", nticks: 6 }),
        yaxis: Object.assign(baseLayout().yaxis, { nticks: 5, title: { text: "归一化（起点=100）", font: { size: 10 } } }),
        margin: { l: 46, r: 14, t: 10, b: 28 },
        showlegend: true,
        legend: { orientation: "h", y: 1.08, x: 0, font: { size: 10.5, color: T.muted } },
        hovermode: "x unified",
      });
      draw(el, traces, layout);
    },

    valuationPercentile: function (el, valuation, opts) {
      const o = opts || {};
      const basis = o.basis === "pb" ? "pb" : "pe";
      const label = o.label || (basis === "pb" ? "PB" : "PE");
      if (!valuation || !valuation.length) {
        el.innerHTML = V2.ui.emptyHTML("暂无估值序列。", "");
        return;
      }
      const dates = valuation.map(function (v) { return v.date; });
      const raw = valuation.map(function (v) {
        const pct = basis === "pb" ? v.pb_pct : v.pe_pct;
        return Math.round(Number(pct) * 1000) / 10;
      });
      const pcts = smooth(raw, 63);
      const traces = [
        {
          type: "scatter",
          mode: "lines",
          x: dates,
          y: pcts,
          line: { color: T.ink, width: 1.25 },
          hovertemplate: "%{x|%Y-%m-%d}　" + label + " 分位 %{y:.0f}%（3 月均）<extra></extra>",
        },
        {
          type: "scatter",
          mode: "markers",
          x: [dates[dates.length - 1]],
          y: [raw[raw.length - 1]],
          marker: { color: T.ink, size: 5 },
          hovertemplate: "%{x|%Y-%m-%d}　当前" + label + " 分位 %{y:.0f}%<extra></extra>",
        },
      ];
      const layout = baseLayout({
        xaxis: Object.assign(baseLayout().xaxis, { tickformat: "%Y-%m", nticks: 6 }),
        yaxis: {
          showgrid: false,
          zeroline: false,
          showline: false,
          ticks: "outside",
          tickcolor: T.rule,
          ticklen: 3,
          tickfont: { size: 10.5, color: T.muted },
          range: [0, 100],
          tickvals: [0, 20, 50, 80, 100],
          ticktext: ["0%", "20%", "50%", "80%", "100%"],
          automargin: true,
        },
        shapes: [
          { type: "rect", xref: "paper", x0: 0, x1: 1, yref: "y", y0: 0, y1: 20,
            fillcolor: "rgba(47,107,79,0.08)", line: { width: 0 }, layer: "below" },
          { type: "rect", xref: "paper", x0: 0, x1: 1, yref: "y", y0: 80, y1: 100,
            fillcolor: "rgba(163,58,43,0.08)", line: { width: 0 }, layer: "below" },
          { type: "line", xref: "paper", x0: 0, x1: 1, yref: "y", y0: 20, y1: 20,
            line: { color: T.ruleSoft, width: 1 } },
          { type: "line", xref: "paper", x0: 0, x1: 1, yref: "y", y0: 80, y1: 80,
            line: { color: T.ruleSoft, width: 1 } },
        ],
        margin: { l: 46, r: 14, t: 10, b: 28 },
      });
      draw(el, traces, layout);
    },

    financials: function (el, financials) {
      if (!financials || !financials.length) {
        el.innerHTML = V2.ui.emptyHTML("暂无财务数据。", "");
        return;
      }
      const rows = financials.slice().sort(function (a, b) {
        return String(a.report_date).localeCompare(String(b.report_date));
      });
      const x = rows.map(function (r) { return V2.fmt.quarterLabel(r.report_date); });
      const traces = [
        {
          type: "bar",
          x: x,
          y: rows.map(function (r) { return r.revenue_yoy; }),
          name: "营收同比",
          marker: { color: T.barWash, line: { width: 0 } },
          hovertemplate: "营收同比 %{y:.1f}%<extra></extra>",
        },
        {
          type: "scatter",
          mode: "lines+markers",
          x: x,
          y: rows.map(function (r) { return r.gross_margin; }),
          name: "毛利率",
          line: { color: T.ink, width: 1.5 },
          marker: { color: T.ink, size: 3.5 },
          hovertemplate: "毛利率 %{y:.1f}%<extra></extra>",
        },
        {
          type: "scatter",
          mode: "lines+markers",
          x: x,
          y: rows.map(function (r) { return r.inventory_days; }),
          name: "库存天数",
          yaxis: "y2",
          line: { color: T.muted, width: 1.2, dash: "dot" },
          marker: { color: T.muted, size: 3 },
          hovertemplate: "库存 %{y:.1f} 天<extra></extra>",
        },
      ];
      const font = sans();
      let maxPct = 0;
      let minPct = 0;
      rows.forEach(function (r) {
        maxPct = Math.max(maxPct, Number(r.gross_margin) || 0, Number(r.revenue_yoy) || 0);
        minPct = Math.min(minPct, Number(r.revenue_yoy) || 0, Number(r.gross_margin) || 0);
      });
      const ymax = Math.max(10, Math.ceil((maxPct * 1.15) / 5) * 5);
      const ymin = Math.min(0, Math.floor((minPct * 1.15) / 5) * 5);
      const layout = baseLayout({
        margin: { l: 46, r: 46, t: 30, b: 28 },
        xaxis: Object.assign(baseLayout().xaxis, { type: "category", tickfont: { size: 10, color: T.muted } }),
        yaxis: Object.assign(baseLayout().yaxis, {
          ticksuffix: "%",
          tickformat: ".0f",
          nticks: 4,
          range: [ymin, ymax],
          zeroline: true,
          zerolinecolor: T.ruleSoft,
          zerolinewidth: 1,
        }),
        yaxis2: {
          overlaying: "y",
          side: "right",
          showgrid: false,
          zeroline: false,
          showline: false,
          ticks: "outside",
          tickcolor: T.rule,
          ticklen: 3,
          tickfont: { size: 10, color: T.muted },
          tickformat: ".0f",
          nticks: 3,
          automargin: true,
        },
        showlegend: true,
        legend: {
          orientation: "h",
          x: 0,
          y: 1.16,
          xanchor: "left",
          yanchor: "top",
          font: { family: font, size: 10.5, color: T.muted },
          bgcolor: "rgba(0,0,0,0)",
        },
        hovermode: "x unified",
      });
      draw(el, traces, layout);
    },

    quadrant: function (el, chains, onSelect) {
      if (!chains || !chains.length) {
        el.innerHTML = V2.ui.emptyHTML("暂无产业链数据。", "");
        return;
      }
      const font = sans();
      const maxWeight = chains.reduce(function (m, c) {
        return Math.max(m, Number(c.holdings_weight) || 0);
      }, 0);
      const traces = [{
        type: "scatter",
        mode: "markers+text",
        x: chains.map(function (c) { return Number(c.median_pct) * 100; }),
        y: chains.map(function (c) { return Number(c.relative_60d); }),
        text: chains.map(function (c) { return c.short || c.name; }),
        textposition: "top center",
        textfont: { family: font, size: 11, color: T.ink },
        marker: {
          size: chains.map(function (c) {
            const w = Number(c.holdings_weight) || 0;
            return 14 + (maxWeight ? (w / maxWeight) * 22 : 0);
          }),
          color: chains.map(function (c) { return (Number(c.alerts) || 0) >= 3 ? T.accent : T.ink; }),
          opacity: 0.9,
          line: { width: 0 },
        },
        customdata: chains.map(function (c) {
          return [c.id, c.name, Number(c.median_pct) * 100, Number(c.relative_60d),
            Number(c.holdings_weight) || 0, Number(c.alerts) || 0,
            Number(c.pct_20d) || 0, Number(c.pct_60d) || 0];
        }),
        hovertemplate:
          "<b>%{customdata[1]}</b><br>" +
          "估值分位 %{x:.0f}%　相对强弱 %{y:+.1f} pp<br>" +
          "持仓 %{customdata[4]:.1f}%　待办 %{customdata[5]} 条<br>" +
          "20 日 %{customdata[6]:+.1f}%　60 日 %{customdata[7]:+.1f}%<extra></extra>",
      }];
      const corner = function (x, y, xa, ya, text) {
        return {
          x: x, y: y, xref: "paper", yref: "paper", text: text,
          showarrow: false, xanchor: xa, yanchor: ya,
          font: { family: font, size: 10, color: T.muted },
        };
      };
      const layout = baseLayout({
        margin: { l: 64, r: 22, t: 28, b: 48 },
        hovermode: "closest",
        xaxis: Object.assign(baseLayout().xaxis, {
          range: [0, 100],
          ticksuffix: "%",
          title: { text: "估值分位", font: { family: font, size: 10.5, color: T.muted }, standoff: 10 },
        }),
        yaxis: Object.assign(baseLayout().yaxis, {
          title: { text: "相对强弱（60 日，pp）", font: { family: font, size: 10.5, color: T.muted }, standoff: 8 },
        }),
        shapes: [
          { type: "line", xref: "paper", x0: 0, x1: 1, yref: "y", y0: 0, y1: 0,
            line: { color: T.ruleSoft, width: 1 } },
          { type: "line", yref: "paper", y0: 0, y1: 1, xref: "x", x0: 50, x1: 50,
            line: { color: T.ruleSoft, width: 1 } },
        ],
      });
      draw(el, traces, layout);
      el.style.cursor = "pointer";
      if (el.removeAllListeners) el.removeAllListeners("plotly_click");
      el.on("plotly_click", function (ev) {
        const point = ev && ev.points && ev.points[0];
        if (point && point.customdata && typeof onSelect === "function") {
          onSelect(point.customdata[0]);
        }
      });
    },

    purge: function (el) {
      if (el && window.Plotly) {
        try { window.Plotly.purge(el); } catch (_) { /* noop */ }
      }
    },
  };

  V2.charts = charts;
})();
