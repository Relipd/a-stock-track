# v3 架构 · 五链投研台

> 五条产业链（白电 / 光伏 / 汽车全产业链 / 铜下游 / 酒店旅游），每链 40 只、共 200 只；
> 纯人工分析，月为最短周期；不做量化因子、不接大模型。

## 1. 分层

```
config/chains.json（5 链：节点/标的/估值口径/KPI 定义）
        │
data_engine/fetch_chains.py ──▶ data/*.parquet（行情/财务/估值/舆情，只读）
data_engine/fetch_business.py ─▶ data/business*.parquet（主营构成/介绍，只读）
data_engine/fetch_valuation_ext.py ─▶ data/valuation_ext.parquet（市值/PS/PCF/PEG）
data_engine/fetch_financial_ext.py ─▶ data/financials_ext.parquet + financial_ratios_ext.parquet
data_engine/fetch_chips.py ─▶ data/chips.parquet（股东户数）
data_engine/fetch_macro.py ─▶ data/macro_futures.parquet（期货/宏观长表）
        │
app/data.py（指标/序列/链级聚合） ──▶ app/server.py（FastAPI）
        │                                  │
        └────────── data/cache.sqlite（API JSON 缓存，数据版本失效）
        │                                  │
        └──── SQLite（逻辑/假设/决策/持仓/复盘）◀── 浏览器 web/
```

- **链配置化**：`config/chains.json` 是唯一产业链来源。新增/修改链只改配置 + 重跑采集，不改引擎。
- **数据层**：`fetch_chains.py` 遍历 200 只标的；行情（新浪，腾讯回退）、财务（同花顺摘要）、估值（百度 PE/PB + 分位）、舆情（东财千股千评）；`fetch_business.py` 采东财主营构成 + 同花顺主营介绍；原子写 Parquet，按链增量合并。
- **只读层**：`chain_metrics / node_aggregates / scissors / chain_aggregate / all_chain_aggregates / node_valuation_distribution / business_of`。链级比较：估值分位中位、毛利率/库存 4 季变化、应收/负债/ROE、上下游毛利率差、20/60 日收益、相对沪深300、涨跌家数、估值极端数；个股另含主营产品/地区收入占比。
- **状态层**：`chains / nodes / instruments / theses / assumptions / decisions / positions / reviews / dismissed_alerts`，所有状态带 `chain_id`。
- **API**：`/api/meta`、`/api/master`（总览）、`/api/overview?chain=`、`/api/stock/{symbol}`、写操作、`/api/review?chain=`；契约见 [`V3_API.md`](V3_API.md)。
- **前端**：`#/overview`（总览）、`#/chain/{id}`、`#/stock/{symbol}`、`#/review?chain=`；同一个安静仪器风格。

## 2. 链定义

| id | 名称 | 估值口径 | 节点 |
|---|---|---|---|
| `whites` | 白色家电 | PE | 上游零部件 / 整机·空冰洗 / 厨电 / 小家电 / 清洁电器 |
| `pv` | 光伏能源 | PB | 硅料·辅材 / 硅片·电池 / 组件 / 逆变器·电站 / 设备 |
| `auto` | 汽车全产业链 | PE | 电池·零部件 / 整车 / 智能化·服务 |
| `copper` | 铜下游 | PB | 铜矿·冶炼 / 铜加工 / 电缆 / 电网·终端 |
| `tourism` | 酒店旅游 | PE | 酒店运营 / 景区目的地 / 旅游服务·免税 |

每条链在配置里还带 4 个行业 KPI 定义（如白电的空调排产、光伏的硅料价格、汽车的乘用车零售、铜的沪铜/铜杆开工率、酒店的 RevPAR）。**KPI 目前只有定义，未接数据**；链读数暂时由成分股聚合（毛利率中位、库存天数、估值分位、20 日涨跌、60 日相对基准）。接入方式见 §5。

## 3. 数据模型

Parquet：`ohlcv`（200 + 基准）、`fundamentals`、`valuation`、`sentiment`、`business`、`business_desc`。
SQLite（全部带 chain_id）：
- `theses`：每标的一条逻辑卡（状态、标题、核心逻辑、估值看法、周期）；
- `assumptions`：可证伪假设（scope=stock/industry、指标、目标、截止日、状态、证据）；
- `decisions`：不可改流水 + 快照 JSON + sha256（含链、估值口径与分位、财务、20/60 日）；
- `positions`：按仓位百分比管理；
- `reviews`：按 `(month, chain_id)` 存，`chain_id=''` 为全链月报。

状态机与 v2 相同：`watch → building → holding → reduced → closed`。

## 4. 总览（`/api/master` + `#/overview`）

只读层，不复制详情：
- 组合条：总仓位、加权浮盈、逻辑数、待办数；
- **行业象限**：x=链估值分位中位，y=60 日相对沪深300（pp），气泡=链持仓权重，红点=有高优预警；
- 行业表：估值分位 / 20 日 / 60 日 / 相对强弱 / 持仓 / 逻辑 / 待办；
- 跨链持仓、待办、30 天内到期假设、最近决策；
- 点击进入单链工作台或标的活文档。

## 5. 后续扩展（不改引擎）

1. **行业 KPI 接入**：新增 `industry_indicators` 表（chain_id, name, date, value, source），支持手工录入 + 可选自动抓取；链读数优先用真实 KPI，缺失时回退成分股代理。
2. **新增产业链**：在 `config/chains.json` 增加一条（节点/标的/估值口径/KPI），跑 `fetch_chains --chain <id>`，前端自动出现该链与总览行。
3. **同名标的跨链**：当前 `instruments.symbol` 唯一；若出现一只股票属于两条链，需要把 `instruments` 改为 `(chain_id, symbol)` 联合主键 + 标的池表拆分，改动集中在该表与 `chains.symbol_meta`。

## 6. 运行与验证

```powershell
.venv\Scripts\python.exe scripts\bootstrap.py          # 建库 + 采集（约 10 分钟）
.venv\Scripts\python.exe -m uvicorn app.server:app --port 8000
.venv\Scripts\python.exe -m pytest -q
.venv\Scripts\python.exe scripts\e2e_check.py
```

测试覆盖：5 链配置与 200 只数据完整性、链级聚合、总览、跨链写入/持仓/月报过滤、收件箱忽略、导出。
