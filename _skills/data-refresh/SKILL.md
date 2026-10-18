# data-refresh · 五链本地数据刷新 Skill

## 何时用

当你说“刷新数据 / 更新五链 / 拉最新行情 / 把缓存热一下”，在终端或 IDE 里运行：

```powershell
.venv\Scripts\python.exe _skills\data-refresh\scripts\refresh.py --status
.venv\Scripts\python.exe _skills\data-refresh\scripts\refresh.py
```

- 默认只跑“过期”的数据集，不每次全量。
- `--force` 强制全量；`--datasets chains,valuation_ext` 只跑部分。
- 完成后自动 `POST /api/reload` 并 `POST /api/warm`，页面直接命中缓存。

## 数据集与 TTL

| key | 内容 | TTL |
|---|---|---|
| `chains` | 行情/财务摘要/PE-PB/舆情 | 1 天 |
| `valuation_ext` | 市值/PS/PCF/PEG、分红、预测 | 1 天 |
| `financial_ext` | 三表精选、ROIC/单季/CCC | 7 天 |
| `business` | 历史主营构成、海外占比 | 30 天 |
| `chips` | 股东户数 | 7 天 |
| `macro` | 期货/铜库存/月频宏观 | 1 天 |

## 它做了什么

1. 读 `data/fetch_manifest.json`，按 TTL 判断哪些数据集过期；
2. 用并发采集器拉数（`--workers`），写 Parquet；
3. 更新 manifest；
4. 如果本地服务在跑：`POST /api/reload` 清 API 缓存 + 热加载，`POST /api/warm` 预计算总览/五链缓存；
5. 打印本次跑了什么、耗时、下次建议。

## 边界

- 只负责“数据拉取/更新”，不生成任何投资判断；
- 不修改 `data/state.sqlite`（逻辑/假设/决策）；
- 所有网络请求仍由 AkShare 发出；页面本身不联网；
- 若接口失败，保留旧 Parquet，不破坏已有数据。
- 原始 HTTP 响应在同一天内由 `data/raw_http_cache.sqlite` 去重：同一 URL 同一天只真正请求一次。若确实要强制拿最新（例如盘中），先运行 `python -m data_engine.ak_cache --clear` 或设置 `AK_CACHE_DISABLE=1`。
