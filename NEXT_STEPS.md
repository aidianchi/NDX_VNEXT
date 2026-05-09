# vNext 下一步

更新日期：2026-05-09  
阅读方式：本文件只放“接下来要做什么”和少量已完成快照。详细完成记录写入 `WORK_LOG.md`，按时间倒序。

---

## 现在最重要的待办

这部分是当前真正的下一步。完成后把条目移到“已完成快照”，并在 `WORK_LOG.md` 写详细记录。

| 优先级 | 类别 | 待办 | 为什么重要 | 完成标准 |
| --- | --- | --- | --- | --- |
| P2 | 核心系统 | L4 prompt 专用摘要 | 1M 上下文模型能容忍约 18 万字符，但当前 L4 重复塞长序列，成本、速度和注意力效率不理想 | 长序列留在 artifact，prompt 只保留 latest/start/end/count/percentile/关键拐点；L4 prompt chars 明显下降 |

---

## 已完成快照

这里只保留最近完成事项的摘要，详细内容见 `WORK_LOG.md`。

### 2026-05-09

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
- 新闻 LLM 解读：当前只做官方事件底账，不做泛新闻情绪和摘要。
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
