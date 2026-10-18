# web/ — v3 前端（五条产业链 · 200 只 · 纯人工分析）

月度投研工作台：总览（组合指挥台）+ 5 条单链 + 标的活文档 + 月度体检。
无构建工具、无框架、可离线；只读 + 人工表单，无任何大模型调用。

## 运行

```powershell
# 1) 真实后端（端口 8000，静态托管本目录）
.venv\Scripts\python.exe -m uvicorn app.server:app --host 127.0.0.1 --port 8000
# 浏览器打开 http://127.0.0.1:8000/

# 2) 联调 mock（端口 8200，读 config/chains.json 生成 5 链样例）
.venv\Scripts\python.exe tools\mock_v2.py
# 浏览器打开 http://127.0.0.1:8200/
```

`file://` 直接打开 `web/index.html` 也可以：此时 API 默认指向
`http://127.0.0.1:8200`（mock，已开 CORS）；`?api=http://127.0.0.1:8000` 可覆盖。

## 路由

| hash | 视图 |
| --- | --- |
| `#/overview`（默认） | 五链总览：组合条、行业象限（x=估值分位 / y=相对强弱 / 气泡=持仓）、行业表、跨链持仓、待办、到期假设、本月决策 |
| `#/chain/{chainId}` | 单链：`whites` 白电 / `pv` 光伏 / `auto` 汽车 / `copper` 铜下游 / `tourism` 酒店旅游；产业链 SVG、40 只标的表、产业链读数、估值分位分布 |
| `#/stock/{symbol}` | 标的活文档：该链 40 只标的、价格 / 估值分位 / 财务趋势、逻辑卡与状态机、假设清单、决策时间线与动作入口 |
| `#/review?chain=` | 月度体检：月份 + 链过滤、组合摘要、假设看板、估值极端名单（8 高 + 8 低）、到期提醒、决策流水、待办、复盘编辑与导出 Markdown |

顶栏：总览 / 5 条链切换（当前链高亮）/ 月度体检；`#/chain` 兼容跳到 `whites`。

## 文件

```
index.html          外壳与脚本顺序（plotly → api/format/ui/charts/diagram → views → app）
styles.css          设计 token 与全部样式（纸色/墨色/唯一 accent；无渐变无阴影，圆角 ≤6px）
js/api.js           同源 / file:// 回退 mock、超时与错误归一化
js/format.js        数字、百分比、日期、PE/PB 口径、中文词表
js/ui.js            错误行、空状态、表单状态、下载
js/charts.js        本地 Plotly 纸色主题：价格、估值分位、财务趋势、行业象限
js/diagram.js       产业链 SVG：按 node_list 角色分列、正交折线、rx=6、4px 网格、≤2 处 accent；
                    role="img" + title/desc；<820px 自动切纵向
js/views/overview.js 总览（只读 + 跳转；待办可标记已处理）
js/views/chain.js    单链视图（PE/PB 标签由 chain.valuation_basis 决定）
js/views/stock.js    标的活文档（人工表单）
js/views/review.js   月度体检（链过滤、估值极端 8+8、复盘编辑、导出）
vendor/             本地 plotly.min.js 与 STIX Two Text（latin 子集，离线可用）
```

## 接口与口径

- 端点见 `docs/V3_API.md`：`/api/meta`、`/api/master`、`/api/overview?chain=`、
  `/api/stock/{symbol}`、`/api/review?month=&chain=`、`/api/export/review`、`/api/inbox`。
- 估值口径：`chain.valuation_basis` 为 `pe` 或 `pb`，前端据此选择
  `pe_ttm/pe_pct_3y` 或 `pb/pb_pct_3y`，并显示 `chain.valuation_label`。
- 月度体检的 `valuation_flags` 可能只返回前 8 高 + 8 低，同时给
  `valuation_flag_totals: {high, low}`；前端按分组展示并在说明中标注全量计数。
- 写操作失败都在行内显示错误并保留表单内容；总览不写业务数据。

## 说明

- **为什么不是 `<script type="module">`**：浏览器在 `file://` 下会以 CORS 拒绝加载
  ES module；为满足“file:// 与 FastAPI 静态托管都能跑”，这里用按序加载的 ES2020
  经典脚本，每个文件仍是独立模块单元，无构建步骤。
- 字体：标题/叙述 STIX Two Text（本地 woff2，回退 Times New Roman / Noto Serif SC），
  密集表格与标签用系统无衬线；数字统一 `font-variant-numeric: tabular-nums`。
