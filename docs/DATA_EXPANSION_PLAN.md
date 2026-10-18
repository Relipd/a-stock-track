# 数据扩容方案 v1：对 Gemini 建议的补充与校正

> **2026-10-18 已落地**：`valuation_ext`（393,896 行）、`financials_ext`（4,100 行）、`financial_ratios_ext`（14,307 行）、`dividends`、`forecast`、`chips`、`macro_futures`；`business` 扩为近 5 年历史期（15,754 行）。UI 已加“分节点估值与质量 / 外部代理 / 估值与质量”区块；测试 14 passed。
>
> 输入：Gemini 2026-10-18 建议、`docs/AKSHARE_FIELDS.md` 实测、当前项目 200 只/五链数据层。
> 结论：**方向正确，但不能“全接 P1、无缝填补行业 KPI”。** 应接“财报科目 + 期货 + 选择性宏观”，并明确它们是**代理读数**，不是真实行业 KPI。

## 1. 先修正 Gemini 的 4 个判断

| Gemini 说法 | 实际情况 | 处理 |
|---|---|---|
| “每条链 20 家” | 当前已是 **40 只/链，共 200 只** | 节点聚合用 8–15 只/节点，单季营收不能只看“4 家” |
| “全接 P1（期货+宏观）” | 期货可用；宏观里 `exports_yoy` 最新只到 **2025-09**，`real_estate` 只到 **2025-12**；`passenger_load_factor`、`traffic_volume`、`retail`、`electricity` 到 2026-08 | **不全接**；按“最新日期 + 频率 + 覆盖”筛选 |
| “财报科目+期货=最硬核行业景气数据” | 财报是**季度滞后**数据；期货只覆盖铜/锂/工业硅，不覆盖硅料/组件/RevPAR/排产 | 定位为“**代理指标**”，不能替代真实行业 KPI |
| “新建 macro_futures 即可无缝填补 4 个行业 KPI” | 只能补“价格/宏观弱代理”，不能补排产、RevPAR、TC/RC、铜杆开工 | README/UI 继续标“代理”，不要宣称已接真实 KPI |

另外两点要注意：

- `stock_zh_valuation_comparison_em` 只有 **8 行（同业+行业中值）**，适合做单股对标，不适合当全行业分位；
- `stock_news_em`、`stock_individual_fund_flow`、`stock_hsgt_hold_stock_em`、`stock_zh_a_spot_em`、行业板块接口当前**不可用**，不要写进 P0。

## 2. 逐链信号：Gemini 的想法 → 可落地字段

### 2.1 白色家电（PE）

| 信号 | 字段 | 计算/口径 | 数据状态 |
|---|---|---|---|
| 排产代理 | 上游零部件单季营收同比 `DJD_TOI_YOY`；整机存货/预收 | 上游节点 8 只中位；整机 `INVENTORY`、预收 `CONTRACT_LIAB`（若字段存在） | `DJD_TOI_YOY` 实测可用；预收需确认字段 |
| 出口代理 | `stock_zygc_em` 按地区“境外/外销”收入占比、毛利率 | 历史期按地区分类，境外收入/总收入；海外毛利率 | 历史 13–17 期，199/200 只有数据 |
| 成本冲击 | CU0 收盘价/20/60 日涨跌 | 期货日频 | 可用 |
| 内需底座 | `macro_china_consumer_goods_retail` 同比 | 月度 | 到 2026-08，可用 |
| 渠道压货 | Δ存货天数 + Δ应收天数 vs 单季营收 | `ΔCHZZTS + ΔYSZKZZTS` 与 `DJD_TOI_YOY` 同向背离 | 可用 |
| 现金安全垫 | FCF、股息率、PE 分位 | FCF = OCF − Capex；股息率 = 近 12 个月每股派息/股价 | FCF/分红可用 |

**补充**：白电“整机毛利率 − 上游毛利率”比单看毛利率更能识别成本转嫁；上游 8 只里含压缩机、阀件、电机，建议按“上游中位 − 整机中位”做剪刀差，而不是全链一个数。

### 2.2 汽车（PE）

| 信号 | 字段 | 计算/口径 | 数据状态 |
|---|---|---|---|
| 价格战烈度 | 整车单季毛利率 `XSMLL`、零部件应收 `YSZKZZTS` | 整车节点毛利率环比；零部件应收天数同比 | 可用 |
| 锂价 | LC0 收盘价 | 日频 | 可用 |
| 出海 | 按地区“境外”收入占比/毛利率 | 历史主营构成 | 可用（部分公司拆分粗） |
| 经营杠杆 | `DJD_DPNP_YOY / DJD_TOI_YOY` | 仅营收增速 >15% 且分母不接近 0 时有效 | 可用，需防负值/极端值 |
| 产业链占款 | CCC = 存货天数 + 应收天数 − 应付天数 | 应付/预付天数用 `_em` 的 `PAYABLE_TDAYS`/`PREPAID_ACCOUNTS_TDAYS` | 部分公司缺失，缺失则不算 |
| 前瞻估值 | 2026E/2027E EPS、forward PE、PEG | forward PE = 现价/预测 EPS；PEG = PE/增速 | 预测为快照，需存抓取日 |

**补充**：汽车“智能化/服务”节点用静态 PE 容易失真，forward PE 必须用**同一预测年度**（2026E 或 2027E）统一，不能有的用 25E、有的用 27E。

### 2.3 酒店旅游（PE）

| 信号 | 字段 | 计算/口径 | 数据状态 |
|---|---|---|---|
| 出行温度 | 民航客座率、民航总周转量、客运量 | 月度；客座率看同比与旺季 | 到 2026-08，可用 |
| 旺季兑现 | Q3 单季毛利率 vs 过去 3 年 Q3 均值 | 用单季 `XSMLL`；Q3 为 7–9 月 | 可用 |
| 折旧噪音 | EV/EBITDA、市现率 | EV = 市值 + 有息负债 − 现金；EBITDA = 营业利润 + 折旧摊销 | 可计算；`FA_IR_DEPR`/`IA_AMORTIZE`/`LPE_AMORTIZE` 可用 |
| 扩建排雷 | CIP/固定资产、Capex/OCF、财务费用 | CIP `CIP`、`FIXED_ASSET`、`CONSTRUCT_LONG_ASSET`、`FINANCE_EXPENSE` | 可用 |
| 免税/景区客流 | —— | —— | **无 AkShare 免费源，需手工** |

**补充**：酒店/景区“单季毛利率”受会计口径（折旧在成本/费用）影响；EV/EBITDA 要统一用 TTM，不要用 24A 年报快照直接和当前市值比。

### 2.4 光伏（PB）

| 信号 | 字段 | 计算/口径 | 数据状态 |
|---|---|---|---|
| 出清进度 | Capex 同比、CIP 环比、存货绝对额环比 | Capex 用 **TTM/4Q 滚动**（避免单季季节性）；CIP、INVENTORY 用期末值 | 可用 |
| 硅料价格代理 | SI0 工业硅期货 | 日频；不是多晶硅致密料价格 | 可用，但**不能等同**硅料价格 |
| 净资产失血 | 单季扣非净利、资产/信用减值、归母净资产 | BV burn = (单季扣非净利 − 减值)/期初归母净资产 | 可用 |
| 生存期 | 货币资金、短债、长债、债券、资产负债率 | 现金短债比 = 现金/短债；净负债率 = (有息负债−现金)/归母净资产 | 可用 |
| 设备坏账 | 设备节点应收天数、信用减值 | `YSZKZZTS`、`CREDIT_IMPAIRMENT_LOSS` | 可用 |
| 估值 | PB、PB 分位、ROIC | 可用 | 可用 |

**补充**：光伏“资本开支腰斩”要看**全链 40 只的 Capex TTM 同比中位**，不能只看 2–3 家；设备节点应收/合同负债是独立风险，需单列。

### 2.5 铜下游（PB）

| 信号 | 字段 | 计算/口径 | 数据状态 |
|---|---|---|---|
| 铜价/库存 | CU0、`futures_inventory_em("cu")` | 日频价格 + 库存增减 | 可用 |
| 矿 vs 冶炼 | 节点毛利率差、ROIC | 矿端/冶炼分组；不能从主营构成直接得到“自产矿比例” | **自给率不可自动提取**，需手工 |
| 中游垫资 | Δ存货 + Δ应收 / 营收、OCF/净利、短债 | `INVENTORY`、`ACCOUNTS_RECE`、`NETCASH_OPERATE`、`SHORT_LOAN` | 可用 |
| 电网需求 | 全社会用电同比、电网设备存货/合同负债 | 宏观用电 + 节点存货/预收 | 用电可用；招标金额无 |
| 估值 | PB/ROIC、PB 分位 | ROIC 用 `_em` 的 `ROIC`（%） | 可用 |

**补充**：Gemini 说“用 stock_zygc_em 识别自产铜精矿利润占比”——**做不到**。主营构成通常只分“铜产品/其他”，不披露自产 vs 外购矿；自给率要手工/年报分部。

## 3. 数据层建议（按“可验证”而不是“全接”）

### 3.1 估值表 `valuation.parquet` 扩列

| 新字段 | 来源 | 频率 | 备注 |
|---|---|---|---|
| total_mv, float_mv, total_shares | `stock_value_em` | 日 | 2018 起；用于 EV、FCF yield、股息率 |
| pe_ttm, pe_static, pb, ps_ttm, pcf_ttm, peg | 同上 | 日 | 与百度 PE/PB 并存，先校验差异 |
| dividend_yield | 分红 + 股价 | 日/年 | 近 12 个月现金派息/股价 |
| forward_pe_2026e, forward_pe_2027e | 预测 EPS + 股价 | 日 | 统一预测年度 |
| ev_ebitda_ttm | 三表 + 市值 | 日/季 | TTM EBITDA；快照可用 `valuation_comparison_em` 交叉校验 |

> `stock_zh_valuation_comparison_em` 只做**单股同业对标**，不写入全市场表中，避免 200 次调用和口径混乱。

### 3.2 财务表 `fundamentals.parquet` 扩列（季度）

| 新字段 | 来源/公式 |
|---|---|
| single_q_rev_yoy, single_q_profit_yoy | `_em` 的 `DJD_TOI_YOY`、`DJD_DPNP_YOY`；缺失时用累计报表差分 |
| roic, roe_weighted | `_em` 的 `ROIC`、`ROEJQ` |
| payable_days, prepaid_days, ccc | `_em` 的 `PAYABLE_TDAYS`、`PREPAID_ACCOUNTS_TDAYS`；CCC = 存货天数 + 应收天数 − 应付天数 |
| capex, fcf | `CONSTRUCT_LONG_ASSET`；FCF = `NETCASH_OPERATE` − capex |
| cip, fixed_asset, total_equity, monetary_funds | 资产负债表 |
| short_debt, long_debt, bond_payable | 资产负债表 |
| net_debt, net_debt_ratio, cash_to_short_debt | 计算 |
| impairment, impairment_to_equity | 利润表资产/信用减值 / 归母净资产 |
| ebitda_ttm | 营业利润 + `FA_IR_DEPR` + `IA_AMORTIZE` + `LPE_AMORTIZE`（+使用权摊销） |
| inventory_abs, accounts_rece | 资产负债表；用于环比/同比与垫资 |

### 3.3 主营表 `business.parquet` 扩历史

- 保留近 5 年、每期 `按产品/按地区/按行业`；
- 新增 `overseas_rev_ratio`、`overseas_gm`（按“境外/外销/国外/其他国家和地区”归并，口径写清楚）；
- 注意“其他(补充)”“内部抵销”不能计入海外收入。

### 3.4 筹码/预期表 `chips.parquet`（新增）

| 字段 | 来源 | 频率 |
|---|---|---|
| holder_num, holder_num_chg_pct, avg_holder_mv | `stock_zh_a_gdhs_detail_em` | 季度 |
| top10_ratio, top10_change | `stock_gdfx_top_10_em` | 季度 |
| report_count, buy_count, eps_2026e/2027e | `stock_profit_forecast_em` | 快照（需存抓取日） |

> 股东户数是**季度**数据，Gemini 的“月度筹码加速”不成立；只能做季度级别的左侧验证。

### 3.5 `macro_futures.parquet`（新增，长表）

不要做成宽表；统一长表：

```text
series_id | date | freq | value | unit | source | fetched_at
CU0       | 2026-10-16 | D | 109860 | 元/吨 | futures_main_sina | ...
LC0       | 2026-10-16 | D | 96320 | 元/吨 | ...
SI0       | 2026-10-16 | D | 8925 | 元/吨 | ...
cu_inv    | 2026-10-16 | D | 36386 | 吨 | futures_inventory_em | ...
retail_yoy| 2026-08 | M | 0.4 | % | macro_china_consumer_goods_retail | ...
electricity_yoy | 2026-08 | M | 4.3 | % | macro_china_society_electricity | ...
pax_load  | 2026-08 | M | 88.8 | % | macro_china_passenger_load_factor | ...
traffic_yoy | 2026-08 | M | ... | % | macro_china_society_traffic_volume | ...
```

- 日频/月频**不混算**；UI 显示 `as_of` 与频率；
- 宏观数据按“最新可得月”取值，不做跨月前向填充；
- `exports_yoy`、`real_estate` 已停更（2025-09/2025-12），**不接入自动读数**，最多存档。

## 4. 公式与护栏（必须写死在脚本里）

| 指标 | 公式 | 护栏 |
|---|---|---|
| FCF | OCF − Capex | 用 TTM；Capex 为负/缺失则空 |
| FCF yield | FCF / 总市值 | 市值 >0；FCF 为负也展示 |
| EV | 总市值 + 短债 + 长债 + 应付债券 − 货币资金 | 不含租赁负债时注明 |
| EBITDA | 营业利润 + 折旧 + 无形/长期待摊摊销 | 用 TTM；银行/保险不适用 |
| EV/EBITDA | EV / EBITDA | EBITDA ≤0 时空，不强行算 |
| 股息率 | 近 12 个月每股现金派息 / 现价 | 特别股息单列；除权日对齐 |
| DOL | 单季扣非净利同比 / 单季营收同比 | 营收同比 >15% 且分母绝对值 >1%；负值不解释为弹性 |
| CCC | 存货天数 + 应收天数 − 应付天数 | 缺应付/应收则空；行业差异大，只做同节点比较 |
| BV burn | (单季扣非净利 − |资产减值| − |信用减值|) / 期初归母净资产 | 期初净资产 >0；单季年化需标注 |
| Capex 收缩 | TTM Capex 同比 | 用 4Q 滚动，避免单季季节性 |
| 海外收入占比 | 境外收入 / 总收入 | 剔“其他(补充)/内部抵销”；口径写清 |
| PB/ROIC | PB / (ROIC/100) | ROIC ≤0 时空；跨节点不可直接比 |
| 现金短债比 | 货币资金 / 短期借款 | 短债为 0 时空 |

## 5. 覆盖/新鲜度（实测）

| 数据 | 最新 | 覆盖 | 结论 |
|---|---|---|---|
| `stock_value_em` | 2026-10 | 样本 000333 2,130 行（2018 起） | 可接；需全量覆盖测试 |
| 三大报表 | 2026-06-30 | 79–97 期/股 | 可接；Q3 未出 |
| `_em` 比率 | 2026-06-30 | 141 列，5 个样本关键字段可用 | 可接；部分字段 NaN |
| `stock_zygc_em` | 2026-06-30 | 13–17 期/股 | 可接历史 |
| `stock_zh_a_gdhs_detail_em` | 最新季度 | 60 期 | 可接，季度频率 |
| 期货 CU0/LC0/SI0 | 2026-10-16 | 431 行 | 可接 |
| 铜库存 | 2026-10-16 | 67 行 | 可接 |
| 社零/用电/客座率/民航周转 | 2026-08 | 209–2,975 行 | 可接 |
| 出口同比 | **2025-09** | 542 行 | 停更，不接 |
| 国房景气 | **2025-12** | 326 行 | 停更，不接 |
| 新闻/资金流/北向/实时快照 | —— | 接口报错 | 不接 |

## 6. 修正后的接入建议

**P0（先做）**
- `stock_value_em` 全字段（13）；
- 分红派息（股息率）；
- 三大报表精选 ~25 列（FCF/Capex/CIP/净资产/有息负债/现金/减值/存货/应收/营业利润/折旧摊销）；
- `_em` 的 ROIC、DJD 单季同比、应付/预付天数、FCFF；
- 预测 EPS/研报数（forward PE）。

**P1（第二批）**
- 历史主营构成（按地区，海外占比）；
- CU0/LC0/SI0 + 铜库存；
- 社零、用电、客座率、民航周转（仅这些新鲜数据）；
- 股东户数（季度）。

**P2（可选）**
- 同业估值快照（`valuation_comparison_em`）用于单股对标；
- 公告列表；十大股东。

**不接**
- 出口同比、国房景气（停更）；新闻、资金流、北向、实时快照（接口坏）；行业指数（连接失败）。

## 7. 最后一句

Gemini 的“用财报科目替代行业高频数据”方向对，但**替代的是“景气验证”，不是“行业 KPI 本身”**。真正落地时：
1) 先接 P0，把 PE/PB/EV/FCF/股息/单季/ROIC 做扎实；
2) 再加 P1 的价格/宏观代理；
3) 所有代理在 UI 上标“代理”，并显示 `as_of`，避免把季度财报当成实时景气。
