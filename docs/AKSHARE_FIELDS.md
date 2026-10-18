# AkShare 字段清单（本项目实测）

> 环境：AkShare 1.19.1，2026-10-18 实测。字段数 = 接口返回 DataFrame 的列数，含代码/日期/元数据，不等于可用指标数。
> 结论：**能拿千余列，但真正能直接用于五链判断的约 200–300 个；行业景气类字段大多没有。**

## 0. 项目当前已用字段（56 列）

| 文件 | 字段 |
|---|---|
| `ohlcv` | symbol, trade_date, open, high, low, close, volume, amount, turnover（9） |
| `fundamentals` | symbol, report_date, revenue_yoy, profit_yoy, gross_margin, net_margin, roe, inventory_days, receivable_days, debt_ratio, ocf_to_profit（11） |
| `valuation` | symbol, trade_date, pe_ttm, pb, pe_pct_3y, pb_pct_3y, pe_pct_1y, pb_pct_1y（8） |
| `sentiment` | symbol, name, trade_date, score, attention, institution, pe_dynamic, turnover, price, pct_chg（10） |
| `business` | symbol, name, report_date, category, item, revenue, revenue_ratio, cost, cost_ratio, profit, profit_ratio, gross_margin（12） |
| `business_desc` | symbol, name, main_business, product_type, product_name, scope（6） |

---

## 1. 行情与交易（stock-level）

| 接口 | 字段数 | 字段 | 频率 | 状态 |
|---|---:|---|---|---|
| `stock_zh_a_daily` | 9 | date, open, high, low, close, volume, amount, outstanding_share, turnover | 日 | 已用（新浪） |
| `stock_zh_a_hist_tx` | 9 | date, open, close, high, low, amount, volume（腾讯口径） | 日 | 备用 |
| `stock_zh_a_spot_em` | 23 | 代码/名称/最新价/涨跌幅/成交量/成交额/换手率/市盈率/市净率/总市值/流通市值等 | 实时快照 | **东财连接失败，不稳定** |
| `stock_bid_ask_em` | 约 20 | 买卖五档、最新价、均价、涨跌 | 实时 | 未测 |

## 2. 三大报表（东财，按报告期）

| 接口 | 字段数 | 关键字段（节选） | 频率 | 状态 |
|---|---:|---|---|---|
| `stock_balance_sheet_by_report_em` | **319** | TOTAL_ASSETS, TOTAL_LIABILITIES, TOTAL_PARENT_EQUITY, MONETARYFUNDS, SHORT_LOAN, LONG_LOAN, BOND_PAYABLE, FIXED_ASSET, CIP（在建工程）, INVENTORY, ACCOUNTS_RECE, NOTE_ACCOUNTS_RECE + 各项 YoY | 季度 | 实测可用（79 期） |
| `stock_profit_sheet_by_report_em` | **203** | TOTAL_OPERATE_INCOME, OPERATE_COST, OPERATE_PROFIT, TOTAL_PROFIT, NETPROFIT, PARENT_NETPROFIT, DEDUCT_PARENT_NETPROFIT, FINANCE_EXPENSE, INTEREST_EXPENSE, ASSET_IMPAIRMENT_LOSS, CREDIT_IMPAIRMENT_LOSS + YoY | 季度 | 实测可用 |
| `stock_cash_flow_sheet_by_report_em` | **254** | NETCASH_OPERATE, CONSTRUCT_LONG_ASSET（资本开支）, NETPROFIT, ASSET_IMPAIRMENT, IA_AMORTIZE（无形摊销）, LPE_AMORTIZE（长期待摊）, FINANCE_EXPENSE, INVENTORY_REDUCE + YoY | 季度 | 实测可用 |

**可由此计算**：FCF = `NETCASH_OPERATE − CONSTRUCT_LONG_ASSET`；EV/EBITDA =（总市值 + 有息负债 − 现金）/（营业利润 + 折旧摊销）；净负债、净资产、在建工程、减值损失、单季度值（累计报表差分）。

## 3. 财务比率（两套，字段高度重叠）

| 接口 | 字段数 | 关键字段（节选） | 覆盖 | 状态 |
|---|---:|---|---|---|
| `stock_financial_analysis_indicator`（新浪） | **86** | 每股收益、每股净资产、ROE、销售毛利率/净利率、营收/净利增长率、应收账款/存货周转天数、资产负债率、流动/速动比率、经营现金流对净利润比率、股息发放率、总资产 | 14 期 | 实测可用 |
| `stock_financial_analysis_indicator_em`（东财） | **141** | EPSJB, BPS, TOTALOPERATEREVE, PARENTNETPROFIT, ROEJQ, XSMLL, XSJLL, ZCFZL, CHZZTS, YSZKZZTS, FCFF_FORWARD/BACK, ROIC, DJD_TOI_YOY（单季营收同比）, DJD_DPNP_YOY（单季净利同比）, 预付/应付周转天数, 营业周期 | 79 期 | 实测可用 |
| `stock_financial_abstract_ths` | 约 16 | 报告期、营收/净利同比、毛利率、净利率、ROE、库存/应收天数、负债率 | 季度 | 当前已用 |

## 4. 估值与市值

| 接口 | 字段数 | 字段 | 频率 | 状态 |
|---|---:|---|---|---|
| `stock_value_em` | **13** | 数据日期, 当日收盘价, 当日涨跌幅, 总市值, 流通市值, 总股本, 流通股本, PE(TTM), PE(静), 市净率, **PEG值**, **市现率**, **市销率** | 日（2018 起） | 实测可用（000333：2130 行） |
| `stock_zh_valuation_comparison_em` | **20** | 排名, 代码, 简称, PEG, 市盈率-TTM/25E/26E/27E, 市销率-24A/TTM/25E/26E/27E, 市净率-24A/MRQ, 市现率1/2, **EV/EBITDA-24A**, 行业中值行 | 快照（8 行） | 实测可用 |
| `stock_zh_valuation_baidu` | 2 | PE(TTM) / PB（只支持这两个指标） | 日 | 当前已用 |
| `stock_hk_valuation_baidu` | 2 | 港股 PE/PB | 日 | 不相关 |

**可补**：PS、市现率、PEG、EV/EBITDA、forward PE（25E/26E/27E）、市值/股本；**股息率**需用分红接口 + 股价计算。

## 5. 分红、主营、预测

| 接口 | 字段数 | 字段 | 状态 |
|---|---:|---|---|
| `stock_history_dividend_detail` | 8 | 公告日期, 送股, 转增, 派息, 进度, 除权除息日, 股权登记日, 红股上市日 | 实测可用（15 期） |
| `stock_fhps_em` | 约 10 | 分红送配方案、股权登记日、除权除息日等 | 未测 |
| `stock_zygc_em` | **11** | 股票代码, 报告日期, 分类类型（按产品/按地区/按行业）, 主营构成, 主营收入, 收入比例, 主营成本, 成本比例, 主营利润, 利润比例, 毛利率 | 已用（199/200 只） |
| `stock_zyjs_ths` | 5 | 主营业务, 产品类型, 产品名称, 经营范围 | 已用（200/200） |
| `stock_profit_forecast_em` | **13** | 研报数, 买入/增持/中性/减持/卖出家数, 2025–2028 预测 EPS | 实测可用（全市场 2891 行） |
| `stock_research_report_em` | 约 10 | 研报标题/机构/评级/目标价/日期 | 未测 |

## 6. 股东、资金、公告

| 接口 | 字段数 | 字段 | 状态 |
|---|---:|---|---|
| `stock_gdfx_top_10_em` | 7 | 名次, 股东名称, 股份类型, 持股数, 占总股本比例, 增减, 变动比率 | 实测可用（10 行） |
| `stock_zh_a_gdhs_detail_em` | 15 | 股东户数（本次/上次/增减/比例）、户均持股市值/数量、总市值、总股本、股本变动 | 实测可用（60 期） |
| `stock_margin_detail_szse` | 8 | 融资买入额, 融资余额, 融券卖出量, 融券余量, 融券余额, 融资融券余额 | 接口可用（所选日期 0 行） |
| `stock_notice_report` | 6 | 代码, 名称, 公告标题, 公告类型, 公告日期, 网址 | 实测可用（1371 行） |
| `stock_news_em` | 约 6 | 关键词/新闻标题/内容/发布时间/来源 | **当前 pandas 解析报错，暂不可用** |
| `stock_individual_fund_flow` | 约 10 | 主力/超大/大/中/小单净流入、净占比 | **东财连接失败** |
| `stock_hsgt_hold_stock_em` | 约 8 | 北向持股数量/市值/占比/排名 | **解析失败** |

## 7. 期货与库存（可直接补行业价格代理）

| 接口 | 字段数 | 字段 | 状态 |
|---|---:|---|---|
| `futures_main_sina`（CU0 / LC0 / SI0） | 8 | 日期, 开盘价, 最高价, 最低价, 收盘价, 成交量, 持仓量, 动态结算价 | 实测可用（431 行/合约） |
| `futures_inventory_em`（cu） | 3 | 日期, 库存, 增减 | 实测可用（67 行） |
| `futures_spot_price` / `futures_rule` | 约 10 | 现货价、基差、保证金、手续费 | 未测 |

> CU0=沪铜主力、LC0=碳酸锂主力、SI0=工业硅主力；可直接做“铜价/锂价/工业硅”代理。**硅料/组件现货价、TC/RC、铜杆开工率不在 AkShare 免费接口内。**

## 8. 宏观（可做五链的弱代理）

| 接口 | 字段数 | 字段/含义 | 状态 |
|---|---:|---|---|
| `macro_china_consumer_goods_retail` | 约 4 | 社零总额/同比 | 实测可用 |
| `macro_china_industrial_production_yoy` | 约 4 | 工业增加值同比 | 实测可用 |
| `macro_china_society_electricity` | 17 | 全社会/一二三产/居民用电量及同比 | 实测可用 |
| `macro_china_real_estate` | 8 | 国房景气指数及涨跌幅 | 实测可用（不是竣工面积） |
| `macro_china_passenger_load_factor` | 3 | 民航客座率/载运率 | 实测可用（月度） |
| `macro_china_society_traffic_volume` | 16 | 货运/客运量、周转量、民航总周转量 | 实测可用 |
| `macro_china_exports_yoy` / `imports_yoy` | 5 | 进出口同比（商品/日期/今值/预测/前值） | 实测可用 |
| `macro_china_pmi` | 5 | 制造业/非制造业 PMI 及同比 | 实测可用 |
| `macro_china_international_tourism_fx` | 4 | 入境旅游人数/比重 | 实测可用（年度，旧） |

## 9. 明确拿不到 / 不稳定的（需要手工或付费源）

| 五链需要 | AkShare 情况 |
|---|---|
| 空调内销/出口排产（产业在线） | 无 |
| 家电出口金额/数量（海关细分） | 只有总量进出口同比，无家电细分 |
| 住宅竣工面积（月度） | 无直接接口；`macro_china_real_estate` 是景气指数 |
| 乘用车零售/新能源渗透率/终端折扣率/经销商库存预警 | 无 |
| 高阶智驾渗透率 | 无 |
| 酒店 RevPAR / OCC / ADR | 无 |
| 景区客流 / 人均旅游消费 / 免税销售额 | 无 |
| 民航票价指数 | 无（只有客座率/总周转量） |
| 硅料/硅片/电池/组件现货价、现金成本 | 无 |
| 光伏月度装机、开工率、行业库存 | 无 |
| 铜 TC/RC、硫酸价格、铜杆/铜管/铜箔开工率 | 无 |
| 国网招标/中标金额、特高压批次 | 无 |
| 行业指数/全市场行业中位估值 | 东财行业接口当前连接失败；可用池内 40 只中位代理 |
| 公告/研报全文 | 公告列表有，正文无；研报只有预测 EPS/评级，无全文 |

---

## 10. 按“接入成本”排序的选择菜单

### A. 估值扩展包（低成本，直接补 Gemini 的 PE/PB 标准）
- `stock_value_em`：总市值、流通市值、总股本、PE(TTM/静)、PB、PS、市现率、PEG（13 字段，日频）；
- `stock_zh_valuation_comparison_em`：forward PE、EV/EBITDA、行业中值（20 字段，快照）；
- `stock_history_dividend_detail`：股息率（8 字段，季度/年度）。

### B. 财务扩展包（中成本，补 FCF / EV / 净资产 / 减值）
- 资产负债表（319）、利润表（203）、现金流量表（254）→ FCF、EBITDA、净负债、在建工程、减值、单季值；
- `stock_financial_analysis_indicator_em`（141）→ ROIC、FCFF、单季同比、周转天数；
- `stock_financial_analysis_indicator`（86）→ 股息发放率、费用/负债结构。

### C. 行业代理包（低成本，能自动抓）
- CU0 / LC0 / SI0 期货（8 字段）→ 铜价、锂价、工业硅价；
- 铜库存（3 字段）；
- 社零、工业增加值、用电量、民航客座率/周转量、进出口同比、PMI（宏观弱代理）。

### D. 主营/预测包（低成本）
- `stock_zygc_em` 历史期（当前只取最新期）；
- `stock_profit_forecast_em`：2025–2028 预测 EPS、评级家数；
- `stock_gdfx_top_10_em`、`stock_zh_a_gdhs_detail_em`：股东集中度/户数变化。

### E. 暂不建议
- `stock_news_em`（解析报错）、`stock_individual_fund_flow`/`stock_hsgt_hold_stock_em`（东财连接失败）、行业指数（连接失败）；
- 高频/实时快照（`spot_em`）对月度人工判断价值低，且不稳定。

---

## 11. 建议你优先挑的字段（我的排序）

1. **P0（直接影响 PE/PB 判断）**：`stock_value_em` 全 13 字段 + 分红派息 + 三表关键 12 字段（FCF/净资产/有息负债/在建工程/减值）+ `_em` 的 ROIC/单季同比。
2. **P1（行业代理）**：CU0、LC0、SI0、铜库存、社零/用电/民航客座率。
3. **P2（辅助）**：forward PE/EV-EBITDA/行业中值、股东户数、公告列表、预测 EPS。
4. **不做**：RevPAR、排产、折扣率、TC/RC、铜杆开工、免税、景区客流、行业指数（不在 AkShare 免费源内）。

你只要告诉我“P0 全接 / 只接 A+B / 再接 C 的哪几个”，我就按这个清单扩数据层；不选的字段不会先写。
