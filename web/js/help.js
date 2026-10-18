/* 指标悬浮说明：定义、判别方向、注意点。
   通过 data-help 自动标注页面上的 dt/th/读数/代理标签，避免每个视图重复写文案。 */
(function () {
  "use strict";

  const HELP = {
    pe: {
      label: "PE(TTM)",
      def: "滚动市盈率 = 总市值 / 最近 12 个月归母净利。",
      dir: "同一行业里越低越便宜；但要先确认利润不是周期顶点或一次性收益。",
      caveat: "亏损公司 PE 为负，不能按“越低越好”理解；PE 链的亏损股应单独剔除。"
    },
    pb: {
      label: "PB",
      def: "市净率 = 总市值 / 归母净资产。",
      dir: "同一行业里越低越便宜；周期底部要看净资产是否会被减值侵蚀。",
      caveat: "重资产/周期行业低 PB 可能是“假便宜”；轻资产行业不能直接和重资产比。"
    },
    pe_pct: {
      label: "PE 近三年分位",
      def: "当前 PE 在近三年自身历史中的位置（0%–100%）。",
      dir: "≤20% 为历史低位，≥80% 为历史高位；低分位是关注区，不是自动买入信号。",
      caveat: "分位只说明相对自己的历史，不说明绝对便宜；负 PE/利润失真时不可用。"
    },
    pb_pct: {
      label: "PB 近三年分位",
      def: "当前 PB 在近三年自身历史中的位置（0%–100%）。",
      dir: "≤20% 为历史低位，≥80% 为历史高位；周期股低分位还要结合 ROE 与净资产质量。",
      caveat: "净资产可能被减值/亏损侵蚀，低 PB 不等于低风险。"
    },
    valuation_pct: {
      label: "估值分位中位",
      def: "链内/节点内标的估值分位的中位数；PE 链看 PE，PB 链看 PB。",
      dir: "越低代表整体越便宜；结合 60 日相对强弱判断“便宜但仍在走弱”还是“便宜且转强”。",
      caveat: "是成分股聚合代理，不是全行业估值分位。"
    },
    gross_margin: {
      label: "毛利率",
      def: "毛利 / 营收，反映产品定价权与成本转嫁能力。",
      dir: "越高越好；但要看行业模式，加工/贸易型公司天然低毛利。",
      caveat: "高毛利也可能被高销售费用吞噬，需同时看净利率与费用率。"
    },
    gross_margin_delta: {
      label: "毛利率 Δ4Q",
      def: "最新报告期毛利率 − 4 个季度前毛利率。",
      dir: "为正表示成本/价格/结构在改善，为负表示被挤压；连续改善更有意义。",
      caveat: "单季波动可能来自会计口径、产品结构或一次性因素。"
    },
    inventory_days: {
      label: "库存周转天数",
      def: "存货平均余额 / 营业成本 × 天数，衡量存货消化速度。",
      dir: "下降通常代表去库存、周转改善；上升可能是备货，也可能是滞销积压。",
      caveat: "要结合营收增速：营收增长 + 库存天数上升可能是压货；营收下降 + 库存上升更危险。"
    },
    inventory_delta: {
      label: "库存天数 Δ4Q",
      def: "最新库存天数 − 4 个季度前库存天数。",
      dir: "下降偏正面（去化），上升偏负面（积压/备货）；结合订单与营收判断。",
      caveat: "季节性强的行业要同比/同季比较，不能只看单季环比。"
    },
    scissors: {
      label: "上下游毛利率差",
      def: "上游节点与下游节点毛利率中位之差，及 4 季变化。",
      dir: "正值表示上游毛利率更高，负值表示下游更强；方向本身不代表好坏，要看你持有哪一段。",
      caveat: "是成分股代理，不是真实加工费/价差；节点分类不同会影响结果。"
    },
    revenue_yoy: {
      label: "营收同比",
      def: "最新报告期营业收入相对上年同期增速。",
      dir: "为正且加速通常偏正面；连续下滑要警惕需求或份额流失。",
      caveat: "并表、提价、低基数都会影响增速，需结合量和价。"
    },
    profit_yoy: {
      label: "净利同比",
      def: "最新报告期归母净利相对上年同期增速。",
      dir: "高于营收增速说明经营杠杆/利润率改善；低于营收增速说明成本或费用在吞噬利润。",
      caveat: "非经常性损益、减值、税率会扭曲；优先看扣非。"
    },
    single_q_rev: {
      label: "单季营收同比",
      def: "单季度营业收入同比，比累计同比更早看到拐点。",
      dir: "转正/加速偏正面；连续两个季度改善更可靠。",
      caveat: "单季基数与季节性影响大，需结合全年与同行。"
    },
    single_q_profit: {
      label: "单季扣非同比",
      def: "单季度扣非归母净利同比，剔除一次性损益。",
      dir: "改善偏正面；与单季营收同比一起看经营杠杆。",
      caveat: "低基数/高基数会造成极端值，负值不能直接解释为“弹性”。"
    },
    receivable_days: {
      label: "应收周转天数",
      def: "应收账款平均余额 / 营收 × 天数，衡量回款速度。",
      dir: "下降偏正面（回款变好）；上升说明账期拉长、议价权变弱或放宽信用。",
      caveat: "整车/零部件/设备行业账期天然长，需同节点比较。"
    },
    debt_ratio: {
      label: "资产负债率",
      def: "总负债 / 总资产。",
      dir: "越低财务风险越小；但过低也可能意味着没有用好杠杆。",
      caveat: "金融、地产、重资产行业口径差异大，不能跨行业硬比。"
    },
    roe: {
      label: "ROE",
      def: "归母净利 / 归母净资产，衡量股东资本回报。",
      dir: "越高越好；稳定高 ROE 是质量信号。",
      caveat: "高杠杆也能推高 ROE，需结合负债率与 ROIC。"
    },
    roic: {
      label: "ROIC",
      def: "投入资本回报率，剔除杠杆影响，衡量经营资产创造回报的能力。",
      dir: "高于资本成本才创造价值；同行业内越高越好。",
      caveat: "重资产行业 ROIC 天然偏低，不能和轻资产直接比。"
    },
    ccc: {
      label: "CCC 现金转换周期",
      def: "存货天数 + 应收天数 − 应付天数，衡量营运资金占用。",
      dir: "越低越好；为负说明占用上下游资金、产业链地位强。",
      caveat: "加工/贸易型公司 CCC 天然低，不能直接和品牌龙头比。"
    },
    fcf_yield: {
      label: "FCF 收益率",
      def: "自由现金流（经营现金流 − 资本开支）/ 总市值。",
      dir: "越高越好；持续为正说明真实现金创造能力。",
      caveat: "重资产扩张期 FCF 可能为负，不一定是坏事；负值要结合 Capex 看。"
    },
    forward_pe: {
      label: "Forward PE",
      def: "现价 / 未来年度预测 EPS（本页优先用 2026E，其次 2027E）。",
      dir: "越低越便宜；但预测 EPS 可信度决定参考价值。",
      caveat: "预测是卖方一致预期快照，可能滞后/乐观；亏损或低覆盖公司参考性弱。"
    },
    dividend_yield: {
      label: "股息率",
      def: "近 12 个月每股现金派息 / 现价。",
      dir: "越高现金回报越强；稳定高股息对成熟龙头是安全垫。",
      caveat: "特别股息、一次性派息会抬高读数；高股息也可能意味着低增长。"
    },
    ps_ttm: {
      label: "市销率 PS",
      def: "总市值 / 最近 12 个月营业收入。",
      dir: "同行业内越低越便宜；适合利润波动大或亏损的公司。",
      caveat: "低毛利商业模式 PS 天然低，不能跨模式比较。"
    },
    total_mv: {
      label: "总市值",
      def: "总股本 × 现价。",
      dir: "用于判断公司体量与流动性；不是估值高低信号。",
      caveat: "市值会随价格波动，比较时注意同一天。"
    },
    ev_ebitda: {
      label: "EV/EBITDA",
      def: "企业价值 / 息税折旧摊销前利润。",
      dir: "同行业内越低越便宜；适合重资产、折旧大的行业。",
      caveat: "EBITDA 为负时无意义；资本结构差异会影响 EV。"
    },
    net_debt_ratio: {
      label: "净负债率",
      def: "（有息负债 − 货币资金）/ 归母净资产。",
      dir: "越低越安全；为负说明净现金。",
      caveat: "重资产/扩张期公司负债高是常态，需结合现金流与到期结构。"
    },
    cash_to_short_debt: {
      label: "现金 / 短债",
      def: "货币资金 / 短期借款。",
      dir: "越高短期偿债越安全；>1 通常较稳。",
      caveat: "货币资金可能受限；短债为 0 时无意义。"
    },
    overseas: {
      label: "海外收入占比",
      def: "按地区主营构成中境外/海外收入占总收入比例。",
      dir: "越高代表全球化程度越高；是否有利取决于海外景气、关税与汇率。",
      caveat: "按地区分类口径不统一，含港澳/其他地区；不能直接等同于出口。"
    },
    holder_num_chg: {
      label: "股东户数环比",
      def: "最新披露期股东户数相对上期的变化比例。",
      dir: "下降 + 户均市值上升通常代表筹码集中，偏正面；上升代表分散。",
      caveat: "季度数据、滞后；股本变动/送转会影响可比性。"
    },
    report_count: {
      label: "研报覆盖数",
      def: "近六个月覆盖该股的研报数量。",
      dir: "高覆盖代表市场关注度高；低覆盖 + 基本面改善可能有预期差。",
      caveat: "不是买卖信号；拥挤度高时反而要防杀估值。"
    },
    pct_20d: {
      label: "20 日涨跌",
      def: "近 20 个交易日收盘价涨跌幅。",
      dir: "为正代表短期强势；结合估值与基本面判断是否追高。",
      caveat: "短期动量不等于中期趋势，波动大的周期股容易反转。"
    },
    pct_60d: {
      label: "60 日涨跌",
      def: "近 60 个交易日收盘价涨跌幅。",
      dir: "为正代表中期趋势偏强；负值代表仍在调整。",
      caveat: "需结合相对基准，单看绝对涨跌会被市场 beta 误导。"
    },
    relative_60d: {
      label: "60 日相对沪深300",
      def: "链/标的 60 日收益 − 沪深300 60 日收益，单位 pp。",
      dir: "为正代表跑赢基准，为负代表跑输；低位 + 转正组合更值得关注。",
      caveat: "相对强弱不预测未来，只是资金与景气的同步指标。"
    },
    valuation_spread: {
      label: "估值分位 P25–P75",
      def: "节点内个股估值分位的 25%/75% 分位区间。",
      dir: "区间越窄说明节点内部估值一致；越宽说明分化大，需挑个股。",
      caveat: "样本少的节点（<5 只）参考性弱。"
    },
    breadth: {
      label: "20 日涨跌家数",
      def: "链内 20 日上涨/下跌的标的数量。",
      dir: "上涨家数多说明链内广度强；只有少数龙头涨则持续性存疑。",
      caveat: "等权计数，不反映市值权重。"
    },
    cu: {
      label: "沪铜主力",
      def: "上期所铜主力合约收盘价，作为铜价代理。",
      dir: "上涨利好铜矿/资源端，压制铜加工/电缆等成本端；下跌反之。",
      caveat: "期货价格不等于现货加工费，不能替代 TC/RC。"
    },
    lc: {
      label: "碳酸锂主力",
      def: "碳酸锂期货主力合约收盘价。",
      dir: "上涨利好锂资源，压制电池/整车成本；下跌反之。",
      caveat: "期货预期属性强，和现货、库存可能背离。"
    },
    si: {
      label: "工业硅主力",
      def: "工业硅期货主力合约收盘价。",
      dir: "上涨抬升硅料/硅片成本；下跌缓解成本压力。",
      caveat: "工业硅不是多晶硅致密料，不能等同于硅料价格。"
    },
    cu_inv: {
      label: "铜期货库存",
      def: "交易所铜库存。",
      dir: "库存下降通常偏紧、利多铜价；库存上升偏宽松。",
      caveat: "显性库存只是一部分，还需看保税区/社会库存。"
    },
    retail: {
      label: "社零同比",
      def: "社会消费品零售总额同比。",
      dir: "回升代表内需消费改善，偏正面；下滑偏负面。",
      caveat: "总量数据，不能替代家电/汽车等细分品类。"
    },
    electricity: {
      label: "全社会用电同比",
      def: "全社会用电量同比增速。",
      dir: "回升代表工业与经济活动改善，利好铜/电网需求。",
      caveat: "受气温、基数影响，单月波动大。"
    },
    pax_load: {
      label: "民航客座率",
      def: "民航客座率（旅客周转量/可用座位）。",
      dir: "上升代表出行需求强，利好酒店/旅游/机场。",
      caveat: "客座率上升也可能靠降价换量，需结合票价与毛利率。"
    },
    pax_yoy: {
      label: "民航客运量同比",
      def: "民航客运量同比增速。",
      dir: "回升代表出行需求改善，偏正面。",
      caveat: "节假日和基数影响大，需看月度趋势。"
    },
    turnover_aviation: {
      label: "民航总周转量",
      def: "民航运输总周转量。",
      dir: "上升代表航空出行景气改善。",
      caveat: "是量的指标，不含票价与客座率质量。"
    },
    portfolio_weight: {
      label: "总仓位",
      def: "所有持仓市值权重之和（按仓位百分比）。",
      dir: "高仓位代表风险暴露高；低仓位代表防守。",
      caveat: "仓位是主观决定，不是市场信号。"
    },
    weighted_pnl: {
      label: "加权浮盈",
      def: "按持仓权重加权的浮动盈亏。",
      dir: "正为盈利，负为亏损；用于组合体检，不是个股判断。",
      caveat: "受建仓时点与仓位影响，不能直接评价选股能力。"
    },
    theses: {
      label: "逻辑卡",
      def: "已建立的标的逻辑数量。",
      dir: "覆盖越多不代表越好；要看是否有假设、是否持续验证。",
      caveat: "空库为 0 是正常的，不代表没有机会。"
    },
    alerts: {
      label: "待办",
      def: "收件箱中未处理的证伪/到期/估值提醒。",
      dir: "越多说明需要复核的判断越多；高优提醒优先处理。",
      caveat: "估值提醒只覆盖已建逻辑/持仓的标的，不是全市场。"
    },
    benchmark: {
      label: "沪深300",
      def: "组合与行业比较的基准指数。",
      dir: "相对基准为正代表跑赢；为负代表跑输。",
      caveat: "单一基准，不完全代表五条产业链的风格。"
    },
    market_cap: {
      label: "总市值",
      def: "总股本 × 现价。",
      dir: "体量/流动性参考，不是估值信号。",
      caveat: "比较时需同一天。"
    }
  };

  const RULES = [
    [/P25|P75/, "valuation_spread"],
    [/PE.*分位|市盈率.*分位/, "pe_pct"],
    [/PB.*分位|市净率.*分位/, "pb_pct"],
    [/上游.*下游|制造段|零部件.*智能化|矿端|酒店.*景区|毛利率差/, "scissors"],
    [/单季营收/, "single_q_rev"],
    [/单季扣非|单季.*扣非/, "single_q_profit"],
    [/毛利率/, "gross_margin"],
    [/库存/, "inventory_days"],
    [/应收/, "receivable_days"],
    [/净负债率/, "net_debt_ratio"],
    [/资产负债率|负债率/, "debt_ratio"],
    [/ROIC/, "roic"],
    [/ROE/, "roe"],
    [/CCC|现金转换周期/, "ccc"],
    [/FCF/, "fcf_yield"],
    [/Forward PE|远期 PE/, "forward_pe"],
    [/股息率/, "dividend_yield"],
    [/现金.*短债/, "cash_to_short_debt"],
    [/EV\/EBITDA/, "ev_ebitda"],
    [/市销率|PS/, "ps_ttm"],
    [/总市值/, "total_mv"],
    [/海外收入/, "overseas"],
    [/股东户数/, "holder_num_chg"],
    [/研报/, "report_count"],
    [/相对强弱|相对沪深300/, "relative_60d"],
    [/营收.*净利|营收增速|营收同比/, "revenue_yoy"],
    [/净利增速|利润同比|净利同比/, "profit_yoy"],
    [/20 日|20日/, "pct_20d"],
    [/60 日|60日/, "pct_60d"],
    [/涨.*跌/, "breadth"],
    [/分位|估值/, "valuation_pct"],
    [/市盈率|PE（TTM）|PE\(TTM\)|^PE$/, "pe"],
    [/市净率|^PB$/, "pb"],
    [/沪铜|CU0/, "cu"],
    [/碳酸锂|LC0/, "lc"],
    [/工业硅|SI0/, "si"],
    [/铜.*库存|铜期货库存/, "cu_inv"],
    [/社零/, "retail"],
    [/用电/, "electricity"],
    [/客座率/, "pax_load"],
    [/民航客运量/, "pax_yoy"],
    [/民航总周转量/, "turnover_aviation"],
    [/总仓位/, "portfolio_weight"],
    [/加权浮盈/, "weighted_pnl"],
    [/逻辑卡/, "theses"],
    [/待办/, "alerts"],
    [/沪深300/, "benchmark"]
  ];

  function keyFor(text) {
    const t = String(text || "").replace(/\s+/g, " ").trim();
    if (!t || t.length > 40) return "";
    for (const [re, key] of RULES) {
      if (re.test(t)) return key;
    }
    return "";
  }

  let tip = null;
  let current = null;

  function ensure() {
    if (tip) return tip;
    tip = document.createElement("div");
    tip.id = "metric-help";
    tip.setAttribute("role", "tooltip");
    tip.hidden = true;
    document.body.appendChild(tip);
    return tip;
  }

  function hide() {
    current = null;
    if (tip) tip.hidden = true;
  }

  function show(el) {
    const key = el.getAttribute("data-help");
    const h = HELP[key];
    if (!h) return;
    current = el;
    const t = ensure();
    t.innerHTML = "";
    const inner = document.createElement("div");
    inner.className = "help-inner";
    const kicker = document.createElement("p");
    kicker.className = "help-kicker";
    kicker.textContent = "指标说明";
    const title = document.createElement("p");
    title.className = "help-title";
    title.textContent = h.label;
    const rule = document.createElement("div");
    rule.className = "help-rule";
    const def = document.createElement("p");
    def.className = "help-def";
    def.textContent = h.def;
    const dir = document.createElement("p");
    dir.className = "help-dir";
    const dirStrong = document.createElement("strong");
    dirStrong.textContent = "判别方向：";
    dir.appendChild(dirStrong);
    dir.appendChild(document.createTextNode(h.dir));
    const caveat = document.createElement("p");
    caveat.className = "help-caveat";
    caveat.textContent = "注意：" + h.caveat;
    inner.appendChild(kicker);
    inner.appendChild(title);
    inner.appendChild(rule);
    inner.appendChild(def);
    inner.appendChild(dir);
    inner.appendChild(caveat);
    t.appendChild(inner);
    t.hidden = false;

    const r = el.getBoundingClientRect();
    const tw = 350;
    let left = r.right + 12;
    if (left + tw > window.innerWidth - 12) left = r.left - tw - 12;
    if (left < 12) left = Math.max(12, Math.min(r.left, window.innerWidth - tw - 12));
    let top = r.top;
    const th = t.offsetHeight || 220;
    if (top + th > window.innerHeight - 12) top = Math.max(12, window.innerHeight - th - 12);
    t.style.left = left + "px";
    t.style.top = top + "px";
  }

  function decorate(root) {
    const nodes = (root || document).querySelectorAll("dt, th, .read-label, .proxy-label, .stat dt");
    nodes.forEach(function (el) {
      if (el.getAttribute("data-help")) return;
      const key = keyFor(el.textContent);
      if (!key) return;
      el.setAttribute("data-help", key);
      el.setAttribute("tabindex", "0");
      el.setAttribute("aria-describedby", "metric-help");
      el.classList.add("helpable");
    });
  }

  function bind() {
    document.addEventListener("pointerover", function (ev) {
      const el = ev.target.closest("[data-help]");
      if (el) show(el);
    });
    document.addEventListener("pointerout", function (ev) {
      const el = ev.target.closest("[data-help]");
      if (!el) return;
      if (ev.relatedTarget && el.contains(ev.relatedTarget)) return;
      hide();
    });
    document.addEventListener("focusin", function (ev) {
      const el = ev.target.closest("[data-help]");
      if (el) show(el);
    });
    document.addEventListener("focusout", function (ev) {
      if (ev.target.closest && ev.target.closest("[data-help]")) hide();
    });
    document.addEventListener("click", function (ev) {
      const el = ev.target.closest("[data-help]");
      if (el) { show(el); return; }
      if (!ev.target.closest("#metric-help")) hide();
    });
    window.addEventListener("resize", hide);
    window.addEventListener("scroll", function () {
      if (current && tip && !tip.hidden) {
        const r = current.getBoundingClientRect();
        if (r.bottom < 0 || r.top > window.innerHeight) hide();
      }
    }, true);
  }

  function start() {
    bind();
    decorate(document);
    const main = document.getElementById("main");
    if (!main || !window.MutationObserver) return;
    let scheduled = false;
    const obs = new MutationObserver(function () {
      if (scheduled) return;
      scheduled = true;
      requestAnimationFrame(function () {
        scheduled = false;
        decorate(main);
      });
    });
    obs.observe(main, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
})();
