# v3 API 契约（五条产业链 · 纯人工分析）

后端 `app.server:app`，`http://127.0.0.1:8000`。v2 端点保留，新增多链与总览；所有链级数据带 `chain_id`。
产业链配置：`config/chains.json`（whites / pv / auto / copper / tourism，各 40 只，共 200 只）。

## 1. GET `/api/meta`
```json
{
  "chains": [
    {"id":"whites","name":"白色家电","short":"白电","description":"...",
     "valuation_basis":"pe","valuation_label":"PE","stocks":20,"nodes":5,
     "kpis":[{"name":"空调排产","unit":"万台","freq":"月","source":"产业在线"}]},
    {"id":"pv","name":"光伏能源","short":"光伏","valuation_basis":"pb","valuation_label":"PB","stocks":20,"nodes":5,"kpis":[...]}
  ],
  "as_of":"2026-10-16",
  "updated_at":"2026-10-18T15:30:00",
  "counts":{"chains":5,"stocks":100,"positions":0,"alerts":9},
  "benchmark":{"symbol":"000300.SH","name":"沪深300","close":4170.61,"pct_20d":-8.31,"pct_60d":-3.2}
}
```

## 2. GET `/api/master`（总览）
```json
{
  "as_of":"2026-10-16",
  "benchmark":{...},
  "summary":{"chains":5,"stocks":100,"positions":2,"total_weight":18.0,"weighted_pnl":3.2,
             "theses":3,"alerts":12,"high_alerts":4},
  "chains":[
    {"id":"whites","name":"白色家电","short":"白电","valuation_basis":"pe","stocks":40,
     "median_pct":0.46,"median_gross_margin":26.2,"median_revenue_yoy":3.1,
     "pct_20d":-5.9,"pct_60d":-8.7,"relative_60d":5.8,
     "up_20d":6,"down_20d":14,"high_pct":5,"low_pct":7,
     "holdings_weight":10.0,"theses":2,"alerts":4,"kpis":[...]},
    ...
  ],
  "positions":[{"symbol":"000333.SZ","name":"美的集团","chain_id":"whites","chain_name":"白色家电",
                "weight_pct":8.0,"entry_price":77.2,"price":84.6,"pnl_pct":9.6,"opened_at":"..."}],
  "allocation":[{"chain_id":"whites","name":"白色家电","weight":8.0}],
  "inbox":[{"id":"assumption-3","symbol":"000333.SZ","name":"美的集团","chain_id":"whites",
            "chain_name":"白色家电","level":"high","kind":"assumption","message":"...","created_at":"..."}],
  "upcoming":[{"symbol":"000333.SZ","name":"美的集团","chain_id":"whites",
               "statement":"...","deadline":"2026-10-31","days_left":12}],
  "decisions":[{"id":1,"symbol":"000333.SZ","chain_id":"whites","action":"buy","logic":"...","created_at":"..."}]
}
```
象限用 `median_pct`（x，0~1）与 `relative_60d`（y，pp）；气泡=持仓权重；`high_pct/low_pct` 为估值极端数。

## 3. GET `/api/overview?chain=whites`
```json
{
  "as_of":"...",
  "chain":{"id":"whites","name":"白色家电","short":"白电","description":"...",
           "valuation_basis":"pe","valuation_label":"PE","stocks":40,"nodes":5,
           "median_pct":0.46,"median_gross_margin":26.2,"median_revenue_yoy":3.1,
           "pct_20d":-5.9,"pct_60d":-8.7,"relative_60d":5.8,"up_20d":6,"down_20d":14,
           "high_pct":5,"low_pct":7,"node_list":[...同 meta.nodes],"kpis":[...]},
  "benchmark":{...},
  "breadth":{"up_20d":6,"down_20d":14,"median_pct":0.46},
  "nodes":[{"id":"upstream","name":"上游零部件","role":"upstream","description":"...","stocks":8,
            "median_pct":0.22,"p25_pct":0.12,"p75_pct":0.97,
            "median_gross_margin":15.3,"gross_margin_delta":-0.1,
            "median_inventory_days":74.8,"inventory_days_delta":0.8,
            "median_revenue_yoy":1.8,"median_profit_yoy":-3.0,
            "median_receivable_days":93.2,"median_debt_ratio":49.3,"median_roe":3.9,
            "median_roic":3.4,"median_ccc":85.5,"median_fcf_yield":1.4,"median_forward_pe":24.5,
            "median_dividend_yield":1.3,"median_overseas_ratio":0.32,
            "pct_20d":-7.5,"pct_60d":-4.0}],
  "scissors":{"label":"上游−下游毛利率差","value":-11.7,"delta":2.2,"note":"..."},
  "proxies":[{"label":"沪铜主力","series_id":"CU0","value":109860,"date":"2026-10-16","freq":"D","unit":"元/吨","chg_20d":-2.1}],
  "distribution":[{"node_id":"upstream","name":"上游零部件","points":[{"symbol":"...","name":"...","pct":0.45}]}],
  "reads":[{"label":"PE 分位中位","value":"46%","delta":null,"note":"..."}, ... 6 条],
  "stocks":[ ... 与 v2 stocks 相同，另含 chain_id/chain_name/valuation_basis/ranks ... ]
}
```

## 4. GET `/api/stock/{symbol}`（增加主营构成与价格高低）
`stock` 增加 `chain_id`、`chain_name`、`valuation_basis`、`high_52w`、`low_52w`；并增加扩展字段：`total_mv/ps_ttm/pcf_ttm/peg/dividend_yield/forward_pe/roic/fcf_yield/ev_ebitda/net_debt_ratio/cash_to_short_debt/ccc/single_q_rev_yoy/single_q_profit_yoy/overseas/holder_num_chg_pct`；
`price[]` 增加 `high`、`low`；`business` 返回：
```json
{"report_date":"2026-06-30",
 "products":[{"item":"光伏相关产品","revenue":19651022792.0,"ratio":0.572,"gross_margin":-0.1224}],
 "regions":[{"item":"境内","revenue":26516954777.0,"ratio":0.7718,"gross_margin":-0.0566}],
 "overseas":{"report_date":"2026-06-30","ratio":0.435,"gross_margin":26.3,"ratio_prev":0.427,"ratio_delta":0.8},
 "main_business":"...","product_type":"...","product_name":"..."}
```
`thesis` 增加 `chain_id`；返回增加 `ranks`（同节点排名，1=最好，n=有效样本）。

## 5. 写操作（不变，后端自动带 chain_id）
- `POST /api/thesis`、`POST /api/assumption`、`PATCH /api/assumption/{id}`、`POST /api/decision`
- 投资页新增：
  - `GET /api/stars` → `{"stars":[加星项],"archived":[已撤星但保留逻辑项]}`；
  - `POST /api/star` `{"symbol":"000333.SZ","active":true}` 加星/撤星；投资加星存在时撤星返回 409；
  - `POST /api/star/note` `{"symbol":"...","note":"..."}` 保存逻辑评语，必须已加星；首次写入记录当天日期，历史在 `star_note_versions`；
  - `POST /api/star/invest` `{"symbol":"...","active":true}` 开启投资加星，必须已有逻辑评语；
  - `POST /api/invest/decision` `{"symbol":"...","date":"2026-10-10","price":80.0,"weight_pct":5,"logic":"...","kill_switch":"..."}` 记录投资决策并**自动取消投资加星**，初始加星和逻辑评语保留。
- `POST /api/review` 增加可选 `chain_id`（`""` 表示全部产业链）
- 决策接口增加可选 `trade_date`（投资页结算日期）；返回/列表保留 `trade_date`。
- `GET /api/review?month=&chain=`：`chain` 为空返回全链；返回增加 `chain_id/chain_name`，`valuation_flags` 用 `pct` 与 `basis`（不再固定 `pe_pct_3y`）
  - `valuation_flags` 最多 8 高 + 8 低（按极端程度），同时返回 `valuation_flag_totals: {"high": N, "low": M}` 表示当前范围内的全量数量；
  - 带 `chain` 过滤时 flags/totals 只统计该链（页面文案用「当前范围」更准确）。
- `GET /api/export/review?month=&chain=`：同名过滤

## 5.1 实现差异

| 契约 | 实际 | 说明 |
|---|---|---|
| `master.chains[].valuation_label` | 无，前端由 `valuation_basis` 推导 | 避免重复字段 |
| `overview.nodes[].median_pe_pct` | 改为 `median_pct`（按链的估值口径） | PE/PB 两种口径统一 |
| `review.valuation_flags[].pe_pct_3y` | 改为 `pct` + `basis` | 光伏/铜用 PB |
| 估值极端名单 | 全市场只列前 8+8，全量在 `totals` | 避免 200 只刷屏；链内过滤时为本链统计 |
| 收件箱估值提醒 | 只对「已建立逻辑/持仓」的标的 | 避免 45 条噪音；全量极端仍在体检名单 |

## 5.2 GET `/api/universe` 与 `/api/compare`

`/api/universe` 返回五链/节点/全部标的，用于对比选择。

`/api/compare?symbols=600438.SH,688303.SH,600089.SH`（2–N 只，**必须同链同节点**；N=最大节点股票数，当前 15）返回：
```json
{"as_of":"2026-10-16","symbols":["..."],
 "stocks":[{"symbol":"...","name":"...","chain_name":"...","node_name":"...",
             "price":11.33,"pct_20d":-1.5,"pe_pct_3y":0.68,"pb_pct_3y":0.17,
             "roic":-3.8,"forward_pe":62.9,"overseas":{"ratio":0.22,...}}],
 "series":[{"symbol":"...","date":"2023-10-16","value":100.0}],
 "stocks[].ranks":{"valuation_pct":{"rank":1,"n":8},"gross_margin":{"rank":2,"n":8},"...":"同节点排名，1=最好"}}
```
`series` 为共同交易日上的归一化收盘价（起点=100），最多 N 只（N=最大节点股票数，单节点不超过成员数）。

## 5.3 估值交易日清洗

百度 PE/PB 原始序列含周末/节假日；`normalize_valuation` 以本地行情日历过滤，并用有效值重算 `pe_pct_3y/pb_pct_3y/pe_pct_1y/pb_pct_1y`，避免非交易日 NaN 造成分位 0 / 图表断崖。

## 5.4 缓存

`app/cache.py` 将总览/单链/活文档/月报的 JSON 缓存在 `data/cache.sqlite`；缓存键含数据版本（Parquet/state.sqlite mtime），数据变化或 `/api/reload` 失效；所有写接口（逻辑/假设/决策/月报/忽略）完成后主动清缓存。首次计算约 2–3s，命中约 3–5ms。

## 6. 前端路由
- `#/overview` 总览（默认）
- `#/chain/{chainId}` 单链（`whites|pv|auto|copper|tourism`）
- `#/stock/{symbol}` 活文档
- `#/review?chain=` 月度体检（默认全部，链下拉过滤）
- `#/compare?symbols=` 多股对比（2–N 只，同链同节点，归一化价格 + 指标对照）
- 顶栏：总览 / 当前链名 / 链切换 / 月度体检；导航当前链高亮。
