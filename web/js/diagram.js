/* 产业链图：inline SVG，正交折线连接、rx=6 节点、4px 网格、最多 2 处 accent、无阴影。
   节点按角色列排布（上游 / 中游 / 下游），列宽与行数随 config/chains.json 的 node_list 变化；
   <=820px 切为纵向角色行。role="img" + <title>/<desc>；点击节点筛选下方表格。 */
(function () {
  "use strict";
  const V2 = (window.V2 = window.V2 || {});
  const fmt = V2.fmt;

  const ROLE_ORDER = ["upstream", "midstream", "downstream"];
  const FOCAL_ROLE = "midstream";

  function buildColumns(nodes) {
    const cols = ROLE_ORDER.map(function (role) {
      return nodes.filter(function (n) { return n.role === role; });
    }).filter(function (arr) { return arr.length > 0; });
    const others = nodes.filter(function (n) { return ROLE_ORDER.indexOf(n.role) < 0; });
    if (others.length) cols.push(others);
    return cols.length ? cols : [nodes.slice()];
  }

  function pairIndices(aCount, bCount) {
    const pairs = [];
    if (aCount === 1) {
      for (let j = 0; j < bCount; j++) pairs.push([0, j]);
    } else if (bCount === 1) {
      for (let i = 0; i < aCount; i++) pairs.push([i, 0]);
    } else {
      const n = Math.min(aCount, bCount);
      for (let i = 0; i < n; i++) pairs.push([i, i]);
      for (let i = n; i < aCount; i++) pairs.push([i, bCount - 1]);
      for (let j = n; j < bCount; j++) pairs.push([aCount - 1, j]);
    }
    return pairs;
  }

  function hPath(sx, sy, tx, ty, busX) {
    const r = 8;
    if (Math.abs(sy - ty) < 0.5) return "M" + sx + " " + sy + " H" + tx;
    const dy = ty > sy ? 1 : -1;
    const s1 = dy > 0 ? 1 : 0;
    const s2 = dy > 0 ? 0 : 1;
    return "M" + sx + " " + sy + " H" + (busX - r) +
      " A" + r + " " + r + " 0 0 " + s1 + " " + busX + " " + (sy + dy * r) +
      " V" + (ty - dy * r) +
      " A" + r + " " + r + " 0 0 " + s2 + " " + (busX + r) + " " + ty +
      " H" + tx;
  }

  function vPath(sx, sy, tx, ty, busY) {
    const r = 8;
    if (Math.abs(sx - tx) < 0.5) return "M" + sx + " " + sy + " V" + ty;
    const dx = tx > sx ? 1 : -1;
    const s1 = dx > 0 ? 0 : 1;
    const s2 = dx > 0 ? 1 : 0;
    return "M" + sx + " " + sy + " V" + (busY - r) +
      " A" + r + " " + r + " 0 0 " + s1 + " " + (sx + dx * r) + " " + busY +
      " H" + (tx - dx * r) +
      " A" + r + " " + r + " 0 0 " + s2 + " " + tx + " " + (busY + r) +
      " V" + ty;
  }

  function desktopLayout(cols) {
    const ncols = cols.length;
    const boxW = ncols >= 3 ? 280 : ncols === 2 ? 320 : 360;
    const gapX = ncols >= 3 ? 200 : 260;
    const totalW = ncols * boxW + (ncols - 1) * gapX;
    const marginX = (1400 - totalW) / 2;
    const boxH = 88;
    const gapY = 28;
    let rows = 1;
    cols.forEach(function (c) { rows = Math.max(rows, c.length); });
    const contentH = rows * boxH + (rows - 1) * gapY;
    const vbH = contentH + 120;
    const geo = {};
    cols.forEach(function (column, ci) {
      const x = marginX + ci * (boxW + gapX);
      const colH = column.length * boxH + (column.length - 1) * gapY;
      const startY = (vbH - colH) / 2;
      column.forEach(function (node, ni) {
        geo[node.id] = { x: x, y: startY + ni * (boxH + gapY), w: boxW, h: boxH };
      });
    });
    return { geo: geo, viewBox: "0 0 1400 " + vbH, gap: gapX, boxW: boxW, boxH: boxH, vertical: false };
  }

  function mobileLayout(cols) {
    const boxW = 200;
    const gapX = 20;
    const rowH = 88;
    const gapY = 48;
    const vbW = 720;
    const vbH = cols.length * rowH + (cols.length - 1) * gapY + 80;
    const geo = {};
    cols.forEach(function (rowNodes, ri) {
      const totalW = rowNodes.length * boxW + (rowNodes.length - 1) * gapX;
      const startX = (vbW - totalW) / 2;
      rowNodes.forEach(function (node, ni) {
        geo[node.id] = { x: startX + ni * (boxW + gapX), y: 40 + ri * (rowH + gapY), w: boxW, h: rowH };
      });
    });
    return { geo: geo, viewBox: "0 0 " + vbW + " " + vbH, gap: gapY, boxW: boxW, boxH: rowH, vertical: true };
  }

  function nodeHTML(node, g, activeNode, focalId) {
    if (!g) return "";
    const selected = activeNode === node.id;
    const dimmed = activeNode && activeNode !== node.id;
    const focal = node.id === focalId;
    const cls = "chain-node" + (focal ? " focal" : "") + (selected ? " selected" : "") + (dimmed ? " dimmed" : "");
    const cx = g.x + 16;
    const pct = Number(node.pct_20d);
    const pctCls = pct > 0 ? "up" : pct < 0 ? "down" : "flat";
    return (
      '<g class="' + cls + '" data-node="' + fmt.esc(node.id) + '" role="listitem">' +
      "<title>" + fmt.esc(node.name) + "：" + (node.stocks || 0) + " 只标的，分位中位 " +
      fmt.ratioPct(node.median_pct) + "，20 日中位 " + fmt.pctSigned(node.pct_20d, 1) + "</title>" +
      '<rect class="node-mask" x="' + g.x + '" y="' + g.y + '" width="' + g.w + '" height="' + g.h +
      '" rx="6" fill="#e6e4df"/>' +
      '<rect class="node-fill" x="' + g.x + '" y="' + g.y + '" width="' + g.w + '" height="' + g.h + '" rx="6"/>' +
      '<text class="node-name" x="' + cx + '" y="' + (g.y + 30) + '">' + fmt.esc(node.name) + "</text>" +
      '<text class="node-meta" x="' + cx + '" y="' + (g.y + 50) + '">' + (node.stocks || 0) +
      " 只 · " + fmt.esc(node.label || "PE") + " 分位 " + fmt.ratioPct(node.median_pct) + "</text>" +
      '<text class="node-pct ' + pctCls + '" x="' + cx + '" y="' + (g.y + 70) + '">20 日 ' +
      fmt.pctSigned(node.pct_20d, 1) + "</text>" +
      "</g>"
    );
  }

  function render(container, opts) {
    const nodes = (opts.nodes || []).slice();
    if (!nodes.length) {
      container.innerHTML = "";
      return;
    }
    const label = opts.label || "PE";
    nodes.forEach(function (n) { n.label = label; });
    const byId = {};
    nodes.forEach(function (n) { byId[n.id] = n; });
    const cols = buildColumns(nodes);
    const vertical = (container.clientWidth || window.innerWidth) < 820;
    const layout = vertical ? mobileLayout(cols) : desktopLayout(cols);
    const geo = layout.geo;
    const activeNode = opts.activeNode || "";

    let focal = nodes.find(function (n) { return n.role === FOCAL_ROLE; });
    if (!focal) focal = nodes[Math.min(1, nodes.length - 1)];
    const focalId = focal ? focal.id : "";

    const outCount = {};
    const inCount = {};
    const links = [];
    for (let ci = 0; ci < cols.length - 1; ci++) {
      const a = cols[ci];
      const b = cols[ci + 1];
      const pairs = pairIndices(a.length, b.length);
      pairs.forEach(function (pair, idx) {
        const s = a[pair[0]];
        const t = b[pair[1]];
        links.push({ s: s, t: t, junction: ci, index: idx, count: pairs.length });
        outCount[s.id] = (outCount[s.id] || 0) + 1;
        inCount[t.id] = (inCount[t.id] || 0) + 1;
      });
    }
    const outSeen = {};
    const inSeen = {};
    const paths = links.map(function (l) {
      const sg = geo[l.s.id];
      const tg = geo[l.t.id];
      if (!sg || !tg) return "";
      const oi = (outSeen[l.s.id] = (outSeen[l.s.id] || 0) + 1);
      const ii = (inSeen[l.t.id] = (inSeen[l.t.id] || 0) + 1);
      const totalOut = outCount[l.s.id] || 1;
      const totalIn = inCount[l.t.id] || 1;
      const focalLink = l.t.id === focalId && l.junction === 0;
      if (vertical) {
        const sx = sg.x + sg.w / 2;
        const tx = tg.x + tg.w / 2;
        const sy = sg.y + sg.h;
        const ty = tg.y;
        const busY = layout.gap * (l.count === 1 ? 0.5
          : 0.25 + 0.5 * (l.index / Math.max(1, l.count - 1))) + sy;
        return '<path class="chain-link' + (focalLink ? " focal-link" : "") + '" d="' +
          vPath(sx, sy, tx, ty, busY) + '" marker-end="url(#' + (focalLink ? "chain-arrow-accent" : "chain-arrow") + ')"/>';
      }
      const sx = sg.x + sg.w;
      const sy = sg.y + sg.h * (oi / (totalOut + 1));
      const tx = tg.x;
      const ty = tg.y + tg.h * (ii / (totalIn + 1));
      const busX = sg.x + sg.w + layout.gap * (l.count === 1 ? 0.5
        : 0.25 + 0.5 * (l.index / Math.max(1, l.count - 1)));
      return '<path class="chain-link' + (focalLink ? " focal-link" : "") + '" d="' +
        hPath(sx, sy, tx, ty, busX) + '" marker-end="url(#' + (focalLink ? "chain-arrow-accent" : "chain-arrow") + ')"/>';
    }).join("");

    const nodeSVG = Object.keys(geo).map(function (id) {
      return nodeHTML(byId[id], geo[id], activeNode, focalId);
    }).join("");

    const rolesText = cols.map(function (c) { return c.length; }).join(" + ");
    const svg =
      '<svg viewBox="' + layout.viewBox + '" role="img" aria-labelledby="chain-svg-title chain-svg-desc" preserveAspectRatio="xMidYMid meet">' +
      '<title id="chain-svg-title">' + fmt.esc((opts.chainName || "产业链") + "结构图") + "</title>" +
      "<desc id=\"chain-svg-desc\">" + fmt.esc(
        "按上游 / 中游 / 下游分组的产业链结构，共 " + nodes.length + " 个节点（各列 " + rolesText +
        " 个）；节点标注标的数量、近三年 " + label + " 分位中位与 20 日涨跌中位。可点击节点筛选下方标的表。"
      ) + "</desc>" +
      "<defs>" +
      '<marker id="chain-arrow" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="#5f5d55"/></marker>' +
      '<marker id="chain-arrow-accent" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="#2456d6"/></marker>' +
      '<marker id="chain-arrow-link" markerWidth="8" markerHeight="6" refX="7" refY="3" orient="auto"><polygon points="0 0, 8 3, 0 6" fill="#2456d6"/></marker>' +
      "</defs>" +
      '<g class="chain-links" aria-hidden="true">' + paths + "</g>" +
      '<g role="list" aria-label="产业链节点">' + nodeSVG + "</g>" +
      "</svg>";
    container.innerHTML = svg;
    const svgEl = container.querySelector("svg");
    if (svgEl) {
      svgEl.addEventListener("click", function (ev) {
        const g = ev.target.closest("[data-node]");
        if (!g) return;
        const id = g.getAttribute("data-node");
        if (typeof opts.onSelect === "function") opts.onSelect(id === activeNode ? "" : id);
      });
    }
  }

  V2.diagram = { render: render };
})();
