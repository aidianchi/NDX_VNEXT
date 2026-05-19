# vNext 下一步

更新日期：2026-05-19  
阅读方式：本文件只放“接下来要做什么”和少量已完成快照。详细完成记录写入 `WORK_LOG.md`，按时间倒序。

---

## 现在最重要的待办

这部分是当前真正的下一步。完成后把条目移到“已完成快照”，并在 `WORK_LOG.md` 写详细记录。

| 优先级 | 类别 | 待办 | 为什么重要 | 完成标准 |
| --- | --- | --- | --- | --- |
| P1 | 数据基础 | yfinance 盈利质量代理实时模式审计 | 回测模式已自动跳过 yfinance 成分股基本面批量代理；实时模式仍可把它作为 sanity check 使用，但必须确认字段来源、公式和 stale cache 边界 | 针对 `get_ndx_pe_and_earnings_yield`、`get_ndx_forward_earnings_quality` 输出审计结论；字段覆盖率、公式、缓存新鲜度、失败 fallback 和不能证明什么都写入 data_quality / prompt / brief |
| P1 | 核心系统 | 新闻事件-数据连接器真实 run 复盘 | `news_event_data_links.json` 已落地，但需要观察真实 run 中哪些连接有帮助、哪些只是噪声，防止新闻叙事污染 | 至少 1 次 `--enable-news` 完整 run 复盘；确认事件连接只作背景观察，不进入 L1-L5，不成为 evidence_ref；必要时调整阈值和展示数量 |
| P1 | 核心系统 | 严格回测剩余 invariant 设计 | 本轮已堵住 CNN FGI、chart/news effective_date、回测跳过契约和 cache 脏写入，但 ALFRED vintage、财报 first-reported、LLM 后验知识和 point-in-time universe 审计仍未系统化 | 写出严格回测 invariant 方案；明确哪些能工程化强制、哪些只能降级/明示；补充 RUN_REVIEW_CHECKLIST 和 DataIntegrity/packet metadata |
| P1 | 数据基础 | L3/yfinance 运行稳定性专项 | 本轮已把 yfinance 长退避、cache fallback、SQLite/文件句柄/限流等失败类型产品化为 runtime diagnostics，但仍需真实失败日志证明根因并减少系统性失败 | 复盘失败日志和批量下载路径；必要时限制并发/文件句柄，明确 cache 读写边界；L3 失败时质量状态、DataIntegrity 和报告发布状态一致 |
| P1 | 数据基础 | 历史数据研究助理 skill 原型 | 回测缺口不能靠主分析链临场补；需要一个独立联网研究助理持续寻找候选历史数据源，并把“如何找到”的经验沉淀成可复用规则 | 读取 `backtest_data_boundaries` 生成候选证据包；输出链接、发布时间、数据日期、摘录/截图、适用风险和置信度；默认标记 `research_candidate` / `manual_review_required`，不得直接进入 L1-L5 |
| P2 | 数据基础 | 采集机 / 快照模式产品化 | 当前网络环境里 yfinance/Yahoo 和 DeepSeek 的最佳网络路径不同；采集与推理解耦能减少半截数据、半截分析、难复现的问题 | `collect-only` 产物包含不可变数据快照、chart/news sidecar、校验摘要和数据边界；主电脑可选择快照只跑 LLM/报告；文档说明单机分流与双机采集两种运行法 |
| P2 | 文档治理 | 文档瘦身与归档审查 | 根目录主文档仍可用，但 `docs/` 中多份 4 月旧审计/实验材料已不是当前事实，容易让后续 agent 误读 | 列出保留/归档/删除候选；历史材料优先移入 `docs/archive/` 并加索引，确认无引用后再删除 |

---

## 已完成快照

这里只保留最近完成事项的摘要，详细内容见 `WORK_LOG.md`。

### 2026-05-19

- 按 `2026-05-19_0409_BACKTEST_SYNTHESIS_AUDIT.md` 完成 P0/P1 闸门修复：Net Liquidity、Crowdedness、Damodaran monthly series 都按回测日裁剪或明确 unavailable；inactive manual metrics 不再进入 packet/prompt；DataIntegrity 递归扫描嵌套日期与 notes 日期，并对未来数据写出 blocked/unpublishable 状态、阻断主流程；Bridge/schema guard 校验死链 refs、重复 transmission path 和空关键字段。
- 继续完成 audit 剩余项第一轮：L3 failed/unavailable/nested-None 不再进入关键事实或 analysis_required；L5/QQQ/QQEW 日频请求统一按 yfinance 排他 end 请求 T+1 再过滤到 T；native brief 首屏展示发布状态、回测日、观察日期范围、采集/生成时间；safe/warning 中文化，token usage 摘要化；console 回写 native brief/workbench 到 `run_summary.json`；CNN Fear & Greed 等复合指标的子项不得绕过总分语义升格成 high 跨层冲突；L2 evidence_refs dict 输出会被 normalizer 收敛成标准字符串 refs。
- audit 剩余项第二轮：yfinance runtime diagnostics 记录 retry/cache fallback/failed、退避秒数、采集耗时和失败类型；DataIntegrity、collect-only / run summary、native brief 审计区展示诊断摘要；native brief 新增买方动作层，把风险边界和失效条件转成加仓/减仓/等待/观察窗口。
- `backtest_data_boundaries` 进入 `analysis_packet.meta/context` 和 native report 审计区，brief 可直接展示回测跳过项、原因和 future upgrade。
- 验证：旧 `output/data/data_collected_v9_20250409.json` 被新 DataIntegrity 判定为 blocked；P0/P1 闸门修复时 `python3 -m pytest -q` 为 294 passed；剩余项第一轮 targeted tests 为 26 passed；第二轮全量测试为 304 passed。

### 2026-05-18

- 按回测原则拍板更新 L4 自动采集：回测模式下，未提供人工/Wind 覆盖时，`get_ndx_pe_and_earnings_yield`、`get_ndx_forward_earnings_quality`、`get_equity_risk_premium` 这类依赖 yfinance 成分股批量基本面的自动路径直接跳过，并写入 `backtest_data_boundaries`；宁缺勿错，不再反复触发批量错误后给伪置信度。
- 回测口径明确：暂时做到“数据日期不超过回测日”；ALFRED first-vintage、财报 first-reported、point-in-time universe 和 LLM 训练后验知识列为后续严格回测升级，不进入当前 P0 修复范围。
- 记录两个后续方向：联网历史数据研究助理只产出待审候选证据包，并把每次探索经验沉淀为可复用规则；采集机/快照模式把数据采集和 DeepSeek 推理解耦，先支持同机分流，必要时再升级为双机采集。

### 2026-05-17

- 修复 workbench crosshair 模块映射：价格技术主图和全部副图都回到 `price_technical` 读数路径；所有图新增左上角 hover 序列读数，最新 workbench 桌面/移动视觉回归通过。
- 修复 2025-04-09 回测 P0 前瞻污染：CNN FGI 回测只用历史数组，回测跳过项不再被 L4 contract 必填，`historical_percentile` 字符串说明不再触发 Pydantic 崩溃，chart/news sidecar 加 `effective_date` 守门，DataIntegrity 不再把跳过/低覆盖/未来日期报成 100%，yfinance frame cache 拒绝明显不完整 batch。
- 修复 WTREGEN/TGA 早期混合缓存单位：2009 年前净流动性不再出现由单位错误造成的假负数。
- 新增 `news_layer_analysis.json` 独立新闻层 sidecar，生成中文概要、可能股市影响、压力通道和新闻层总分析；不进入 L1-L5，不成为 `evidence_ref`。
- L4 新增 DanjuanFunds/蛋卷基金 NDX 估值校验源，解析 PE/PB/PE percentile/PB percentile/ROE/PEG/eva_type/date/sample_start/update time；真实接口验证 NDX PE `36.51`、PE 分位 `87.0`、PB 分位 `99.68`。
- 估值分位权威顺序明确为 Manual/Wind > trusted Trendonify > DanjuanFunds/蛋卷基金 > WorldPERatio std-dev context；yfinance 成分股 PE/PB/Forward PE 降为 component-model proxy / sanity check，不再作为估值 regime 主锚。
- yfinance 增加持久缓存和失败保留旧值；QQQ 图表与成分股 `.info` 走更稳的缓存路径，减少限流导致的空图和空指标。
- Workbench 默认历史窗口从 5 年改为 10 年起步，按钮改为 10Y / 15Y / ALL。
- 新增 `news_event_data_links.json`：把官方事件底账和 chart time series 做时间邻近连接，只输出 temporal association / co-movement observation / needs_bridge_review，不写因果证明，不进入 L1-L5，不成为 `evidence_ref`。
- Native brief 新闻栏升级为“官方事件底账与市场连接观察”；控制台旧版 HTML/charts 日常入口软删除，并通过 `console_logs_entry_v3` 解决旧服务继续显示 visual regression / legacy HTML 入口的问题。
- 验证：`python3 -m pytest -q` 为 263 passed；真实蛋卷接口、`news_event_data_links.json`、新版 brief 与 8765 控制台均已验证。

### 2026-05-16

- 复核并合并 Claude 20260513 审计分支方向：治理阶段 `generated_at` 代码覆盖、L4 长序列进入 prompt 前摘要化、反编造约束提升到 system message、DataIntegrity 扩展、workbench 数据时效性警告、指标时间戳与 U7-U10 简化修复。
- 补强 objective firewall：至少 3 层必须包含可用指标 payload，空层容器不再让 `object_clear` 误判为清晰。
- 补强 Kimi HTTP fallback：实际携带 system constraints，并兼容 `get_extra_headers("kimi")` 返回 `None`。
- 验证：`.venv/bin/python -m pytest -q` 为 253 passed。

### 2026-05-12

- L4 外部估值源稳定收口：Damodaran 官网月度 `ERPbymonth.xlsx` 优先并验证 120 条月度序列；WorldPERatio 当前页面 Last 1Y/5Y/10Y/20Y 标准差窗口可结构化解析且不冒充 historical percentile；Trendonify 继续走用户信任的 `bb-browser` sidecar，不把 requests 403 硬修成主链路。
- Trusted Trendonify sidecar 支持合并进 `ThirdPartyChecks`，并带 `browser_sidecar` 元数据；刷新遇到 Cloudflare/空页面时按 page_type 保留旧可用值，避免污染。
- manual/Wind PE 仍作为主值时，collector 会附加 live `ThirdPartyChecks` 作为审计交叉校验；Damodaran live monthly 不再被 manual ERP 覆盖。
- 研究控制台主入口从“视觉回归”改为“查看日志”，优先服务复跑和排障；视觉回归保留为开发验证脚本。
- 验证：`python3 -m pytest -q` 为 154 passed；`--collect-only` 真实采集成功，`output/data/data_collected_v9_live.json` 中包含 WorldPERatio、Trendonify trailing/forward 与 Damodaran monthly。

### 2026-05-10

- 修复控制台运行环境：control service 会把白名单 `python3` 命令绑定为启动服务的虚拟环境解释器，避免 macOS 系统 Python 3.9 导致 `pandas_ta` 缺失。
- 控制台产物跳转改为本地服务 `/artifact?path=...`，解决 `http://127.0.0.1` 页面无法可靠打开 `file://` HTML 的问题；完整运行完成后自动打开最新 native brief。
- 新 brief/workbench 命名简化为 `vnext_brief_<数据采集分钟>_<运行分钟>.html` 和 `vnext_workbench_<数据采集分钟>_<运行分钟>.html`；控制台继续兼容旧文件名。
- 修复 M2 YoY 分位、WTREGEN 单位混合缓存、净流动性 dtype 异常，以及默认实时模式误触发历史成分股路径的问题。
- 真实 `--collect-only` 验证：`output/data/data_collected_v9_live.json` 中 39 个指标全部有值，0 缺失，0 错误。

### 2026-05-09

- 修复控制台分段验证闭环：`src/main.py --collect-only` 支持只采集数据；控制台自动填入最近数据 JSON，“已有数据分析”改为只跑 vNext/LLM；普通分析日期不再自动触发回测，只有勾选“历史日期 / 回测”才传 `--date`；workbench 在 yfinance 限流、L5 技术指标缺失时降级生成，不再因 `None.get()` 崩溃。
- 控制台完成产品化闭环：新增一键启动器 `open_research_console.command` / `src/open_research_console.py`，`control_service` 根地址直接服务控制台，控制台载入上次人工数据，保存人工数据后可一键运行完整报告，自动串联 vNext、native brief 和 workbench。
- 用 `$impeccable` 对控制台和 brief 完成 shape/craft/polish：控制台改成“运行仪器”层级，brief 改成左侧 sticky 导航 + 右侧长文阅读，默认样式切到 OKLCH token，去掉彩色侧边条惯性，并把 console 纳入桌面/移动视觉回归。
- 新增本地 `control_service` MVP：提供 `/health` 和 `/run`，只接受白名单命令，日志写入 `output/logs/control_service/`。
- 修复研究控制台“运行”按钮脚本初始化问题，重新生成 `output/reports/vnext_research_console.html`。
- 新增官方新闻/事件 sidecar：`src/news_event_ledger.py` 生成独立 `news_event_ledger.json`，当前接入 Federal Reserve、BLS、BEA 官方 RSS 与 M7 SEC submissions。
- `src/main.py` 新增 `--enable-news`，只写事件底账，不污染 L1-L5 runtime context。
- 新增 L2 指标 `get_hy_quality_spread_bp`：FRED / ICE BofA `BAMLH0A3HYC - BAMLH0A1HYBB`，用于观察低质高收益债相对 BB 的尾部信用压力。
- 新增 L3 指标 `get_qqq_top10_concentration`：读取 Invesco QQQ 官方持仓 API，输出 Top10 / Top5 / Top3 / M7 权重、Top10 相对等权基准超额权重、QQQ 相对 QQEW 的 1M/3M/6M 表现差，并明确当前持仓与历史变化 proxy 边界。
- 新增 L4 指标 `get_ndx_forward_earnings_quality`：基于 yfinance 成分股模型补充 forward earnings yield、Forward EPS 增长代理、盈利/收入增长、利润率质量，以及 M7 next-year EPS 30日修正方向；L4 prompt 和 brief 指标可直接消费。
- `bb-browser` 已确认安装并可用，但本轮 Invesco 官方 JSON 端点可直接稳定访问，暂不把 `bb-browser` 接入主数据链；它仍保留为 P2 人工调研/sidecar 试验项。
- 控制台人工 ERP 输入新增 5Y / 10Y 分位，并写入独立 Manual/Wind ERP reference；不再把 ERP 输入混入 NDX 简式收益差距。
- Trendonify 研究更新：直连 requests 与 Jina Reader 仍返回 Cloudflare 验证页；`bb-browser` 启动 daemon 后可用真实浏览器拿到页面文本。实测 2026-05-08 页面：Trailing PE 38.07、10Y percentile 100；Forward PE 23.73、5Y percentile 40、10Y percentile 57.5、20Y percentile 71.2。Parser 已能结构化 1Y/5Y/10Y/20Y/since-inception 多窗口百分位。
- control service 补齐 `/status/<job_id>`、`/cancel/<job_id>` 和运行前确认；控制台新增状态刷新、取消任务、日志尾部和失败原因展示。
- 新闻事件底账升级到 `news_event_ledger_v2`：每条事件有 `source_tier`、`event_type`、`published_at`、`symbols`、`layers`、`dedupe_id`，并按时间窗口去重；事件仍不进入 L1-L5 runtime context。
- AnalysisPacket / Bridge / Thesis 新增 `event_ref` 通道，与 `evidence_ref` 分离；Bridge/Thesis 只能把事件写成解释、触发或观察背景，不能写成证明。
- 真实数据 run 验证 `HY CCC & Lower - BB OAS`：`output/analysis/vnext/20260509_134942/analysis_packet.json` 中该指标成功，最新值 7.44，`data_quality` 完整；同 run 的 `chart_time_series.json` 有 `HY_QUALITY_SPREAD` 786 行，波动信用 workbench 已生成 `output/reports/vnext_interactive_charts_20260509_hy_quality.html`。
- Trendonify / `bb-browser` 已实现隔离 sidecar：`src/browser_sidecar.py` 输出 `output/browser_sidecar/trendonify_ndx_valuation.json`，控制台有“信任 bb-browser 来源”勾选框、页面跳转、单独拿数据按钮和输出入口；主 L4 requests 链仍不自动启动浏览器。
- 补齐 `PRODUCT.md` 和 `DESIGN.md`，`$impeccable` context loader 已确认可读取。
- 全量测试：`python3 -m pytest -q`，117 passed。

### 2026-05-07

- 修复 workbench 主图与副图纵向轴线不齐。
- 修复模块切换后顶部摘要和 crosshair 读数仍停留在 L5 的问题。
- QQQ 交互图默认数据窗口扩到 1825 天。
- 控制台新增“运行”按钮入口，最初调用本机 `127.0.0.1:8765` control service。

### 2026-05-06

- workbench 从展示图升级为可操作看盘台：指标显隐、预设、时间轴锁定/解锁、统一时间轴、跨 pane readout、副图启停。
- 控制台重构为六区总控：运行对象与日期、人工/Wind 数据、模型与流程、功能开关、输出入口、运行日志/健康/安全。
- legacy Plotly chart 退出默认主路径，只有显式 `--enable-legacy-charts` 才启用。

### 更早已完成

- L1-L5 v2 artifacts 固定为 `indicator_analyses`、`layer_synthesis`、`internal_conflict_analysis`、`cross_layer_hooks`、`quality_self_check`。
- Bridge v2 已开始显式识别跨层冲突、共振和传导。
- Damodaran 月度 ERP 与 WorldPERatio 相对位置已纳入 L4 数据基础。
- Native `brief`、指标级微图、chart time-series artifact 和 visual regression 基线已落地。

---

## 暂缓或只观察

- OpenBB：暂缓整个平台接入。当前只学习它的 provider metadata、coverage discovery 和数据治理思路。
- Trendonify：真实浏览器 sidecar 已落地；主链仍不硬绕 403，不静默退回 yfinance。后续只观察采集稳定性、来源信任流程和是否需要人工一键导入。
- 正式前端框架化：在 brief / console / workbench 信息架构稳定前继续保持 self-contained HTML。
- 新闻 LLM 解读：当前只做官方事件底账和事件-数据时间邻近连接，不做泛新闻情绪和摘要。
- 交易执行、组合建议、自动下单：不属于 vNext 当前范围。

---

## 长期原则

### 三类目标

1. 核心系统：推理链、上下文隔离、跨层关系、治理校验。
2. 数据基础：数据采集、标准化、数据源覆盖、缺口和置信度边界。
3. 输出体验：native HTML、交互 workbench、审美、排版和连续阅读体验。

### 依赖关系

1. 数据基础是地基。数据不准，核心系统越强，越可能严肃地分析错误材料。
2. 核心系统是骨架。没有干净推理链，输出体验只是把混乱包装得更好看。
3. 输出体验是交付面。没有好的阅读和交互，系统再强也很难被人持续使用和审查。

### 不可破坏原则

- 不得回退 L1-L5 context isolation。
- 不得让 `legacy_adapter.py` 成为主要认知生产者。
- 不得为了报告顺滑抹平冲突。
- 不得把新闻、浏览器采集或登录态工具直接混入主指标链。
- 不得用未经证据支持的历史概率、回测收益、样本期包装判断。
- 回测缺口的联网探索必须先进入待审候选层，不能直接污染 L1-L5 主证据；稳定可重复后再升级为正式采集规则。

---

## 文档清理候选

先不直接删除，下一轮按“当前事实 / 历史材料 / 可删除噪音”三类处理：

| 候选 | 建议 | 理由 |
| --- | --- | --- |
| `docs/2026-04-24_*`、`docs/2026-04-25_*` | 优先归档到 `docs/archive/` | 多数是 vNext 初期审计、prompt 实验和 legacy 对比，历史价值仍在，但不应作为当前路线入口 |
| `docs/4.20 VNEXT_REPORT.md` | 归档并在 ARCHITECTURE 留摘要链接 | 长篇初始路线图，很多内容已被 `ARCHITECTURE.md` / `NEXT_STEPS.md` 吸收 |
| 根目录 `PLAIN_LANGUAGE_*` | 暂保留，后续合并索引 | 面向普通读者，受众不同；可加一份索引说明哪些仍是当前解释，哪些是历史说明 |
| `audit_report_20260517.md`、`PROJECT_AUDIT_20260513.md` | 保留为审计记录 | 仍解释了重要缺陷来源；不能当作当前待办清单使用 |
| `ai_response_debug_*.txt` | 可考虑移入 `output/debug/` 或删除 | 调试原始响应不适合作为根目录长期文档 |

---

## 验证命令

macOS / Linux：

```bash
python3 -m pytest -q
```

```bash
python3 src/research_console.py
```

```bash
python3 src/control_service.py
```

```bash
python3 src/main.py --models deepseek-v4-flash,deepseek-v4-pro --skip-report --disable-charts --enable-news
```

```bash
python3 src/agent_analysis/vnext_reporter.py --run-dir output/analysis/vnext/<run_id> --template brief
```

```bash
python3 src/interactive_chart_workbench.py --run-dir output/analysis/vnext/<run_id> --modules price_technical,volatility_credit,rates_valuation,breadth_concentration,liquidity
```

Windows PowerShell：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

如果 PowerShell 在命令执行前直接报 `8009001d`，通常是 Windows PowerShell / Crypto Provider 初始化问题；临时绕过方式是用 `cmd.exe` 运行同样命令。
