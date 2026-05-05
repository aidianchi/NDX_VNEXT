# vNext 下一步

最近更新：2026-05-05
阅读方式：最新事项放在最上面。完成后把结果写入 `WORK_LOG.md`，同样按时间倒序。

---

## 最新下一步

### 输出体验：L1-L5 指标级可视化已落地

- 用户指出“四张大图不应该是全部数据可视化”，这个判断成立。vNext 的底稿价值在于每个指标都有独立发言权，因此必要图表应贴近指标卡，而不是只集中在报告前部。
- 本轮已完成第一版指标级微图：L1-L5 指标卡会按数据形状展示历史分位/5Y/10Y/z-score、均线或基准偏离、组成项、广度、M7 基本面、估值源、Damodaran 当前 ERP lens、收益差距压力、技术区间、MA ladder、MACD、OBV、成交量和 Donchian channel。
- 设计原则已明确：只有能回答“位置、变化、结构、分歧、区间、压力”的数据才图表化；没有历史或结构语境的单点值不强行画图。
- 旧 `chart_generator.py` / `chart_adapter_v6.py` 仍可作为 legacy 参考，但 native brief 当前不把它们作为主路径。主路径应继续直接消费 vNext artifacts，避免图表数据和报告文字来自不同抓取时点。
- 旧 run `output/analysis/vnext/20260502_193057` 重新生成后，默认报告含 29 个指标级可视化；复杂指标使用可展开区，避免底稿阅读被大图打断。
- 进一步调研后确认：底稿微图不能替代看盘式交互图。已安装 `lightweight-charts@5.2.0` 并新增独立原型 `output/reports/vnext_interactive_charts_20260502.html`，用于验证 QQQ K 线、成交量、MA overlay、区间按钮和 crosshair readout。
- 已修复 native brief JSON payload 嵌入 bug，避免 `JSON.parse` 失败影响证据抽屉和跳转。

### 指标级可视化后的下一轮观察

| 顺序 | 类别 | 任务 | 为什么重要 | 完成标准 |
| --- | --- | --- | --- | --- |
| 1 | 输出体验 | 明确图表三层架构 | 当前微图、市场总览图、看盘式交互图各自回答的问题不同，混在一起会让报告失焦 | 写入设计规则：底稿微图用于速读，大图用于跨层总览，Lightweight workbench 用于交互探索 |
| 2 | 数据基础 | 将交互图数据纳入 artifacts | 当前原型的 QQQ OHLCV 来自生成时 yfinance 拉取，和旧 run 的文字并非严格同一时点 | 在 vNext run 中保存必要时间序列，例如 QQQ OHLCV、MA、volume、VIX、10Y、ERP monthly series，让交互图同源可审计 |
| 3 | 输出体验 | 决定哪些指标进入 Lightweight workbench | 不是所有指标都适合 K 线式交互；L1/L4 更适合多轴线图或 regime panel | 先纳入 L5 价格/成交量/均线/Donchian/MACD，再评估 L1 利率、VIX、ERP 是否做多 pane |
| 4 | 输出体验 | 真实最新 run 后复核微图覆盖 | 旧 run 缺少最新 Damodaran 月度序列、WorldPERatio 结构化字段和未来新增 L5 量价质量指标 | 最新 DeepSeek run 生成 brief 后，确认每层有图指标、无图指标和降级说明都合理 |
| 5 | 输出体验 | 修复 evidence hash 直达体验 | 浏览器直接打开 `#evidence-Lx-...` 时，目前主要依赖点击事件展开层级，直接 hash 直达仍不够自然 | 打开任一 evidence hash 能自动展开对应 Layer、滚动到指标卡并高亮 |
| 6 | 输出体验 | 建立图表视觉回归 | 指标微图和交互图数量变多后，移动端和长文本容易产生挤压 | 对桌面/移动截取五层底稿和交互 workbench，检查微图非空、文字不溢出、details 和区间按钮可用 |
| 7 | 输出体验 | 决定是否正式弃用 legacy chart 主路径 | 旧 Plotly 图表仍在 legacy reporter 中存在，维护两套路线上会造成混乱 | 明确 legacy chart 只服务旧报告，或迁移少数高价值时间序列到 native artifacts 后归档旧管线 |

### L4 数据源复盘后的修正方向（1-5 已完成）

- 用户指出的两个 L4 问题经初步官网复核后成立：WorldPERatio 不应只作为 PE 绝对值校验源，Damodaran 当前实现也不应只优先读取年度 `histimpl.xls`。
- WorldPERatio 官网对 Nasdaq 100 提供 PE、数据日期、1/5/10/20 年滚动均值、标准差区间、相对均值的 σ 偏离、估值标签、50/200 日趋势边际和前瞻回归提示。它可以辅助描述相对位置，但除非页面明确给出 percentile/rank，仍不得写成历史分位。
- Damodaran 官网存在更适合“当前 ERP”的官方月度路径：`ERPbymonth.xlsx` 已包含 2008-09 至 2026-05-01 的月度数据；`ERPMay26.xlsx` 也可直接下载，2026-05-01 文件内包含 10Y Treasury、Aa1 default spread、adjusted riskfree rate、expected return 和多种 implied ERP 口径。年度 `histimpl.xls` 应保留为长期历史背景，不再作为最新 ERP 首选。
- 代码已完成 1-3 步：Damodaran 月度 ERP 优先，WorldPERatio 相对位置结构化，L4 prompt / few-shot / packet builder 已明确区分真实 percentile、std-dev / z-score relative context、monthly current ERP 和 annual history fallback。
- 输出体验已完成 4-5 步：native `brief` 新增“市场图谱”章节，展示 L4 估值相对位置尺、Damodaran ERP 月度路径、WorldPERatio 窗口标签、L1-L4 利率估值压力图；新增 first-screen 研究控制台 `output/reports/vnext_research_console.html`。
- 真实官网 smoke 已确认：`get_damodaran_us_implied_erp("2026-05-01")` 可读取 `ERPbymonth.xlsx` 的 2026-05-01 多口径 ERP，并合并 `ERPMay26.xlsx` 的 default spread / expected return；全量测试 `python3 -m pytest -q` 为 86 passed。
- 详细通俗复盘已写入 `PLAIN_LANGUAGE_L4_DATA_SOURCE_REVIEW.md` 和 `PLAIN_LANGUAGE_OUTPUT_EXPERIENCE_REVIEW.md`。

### 输出体验 4-5 落地后的下一轮观察

| 顺序 | 类别 | 任务 | 为什么重要 | 完成标准 |
| --- | --- | --- | --- | --- |
| 1 | 输出体验 | 用最新真实 run 验证图表数据完整性 | 当前生成页沿用 2026-05-02 旧 run，旧 artifact 没有 Damodaran 月度序列和 WorldPERatio 结构化窗口 | 下一次 DeepSeek run 后重新生成 brief，确认 ERP 月度线图、WorldPERatio 窗口标签、利率估值压力图都吃到最新字段 |
| 2 | 输出体验 | 控制台第二阶段能力取舍 | 第一版控制台只生成模板和运行命令，不直接写文件或执行本地任务 | 决定是否允许控制台写入 `manual_data.local.json`、启动 run、自动打开最新报告；若做，必须有明确安全边界 |
| 3 | 输出体验 | 图表视觉回归 | 本机 Python/Node Playwright 未安装，已做 Chrome headless 截图，但还不是完整交互测试 | 补齐浏览器自动化依赖后，对桌面和移动 viewport 截图，检查图表非空、文字不溢出、证据抽屉可打开 |

### 输出体验反馈：当前改造版不是终版

- 用户已查看 `output/reports/vnext_research_ui_brief_20260502.html` 的改造版，并明确表示：当前审美方向不满意，尤其主视觉配色不应作为后续默认方向。
- 五层底稿区域的点击/展开/跳转动效存在问题：用户感知为“似乎无法跳转，动画有问题”。这说明当前交互反馈不够清楚，也可能存在浏览器侧展开状态或滚动定位问题。
- 这版可以作为“输出体验第一轮结构尝试”保留，但不能被视为最终 UI，也不能作为审美定稿。
- 下一阶段输出体验只记录方向：审美方向需要重新指明；五层展开、证据抽屉、跳转反馈和动效需要继续优化；图表/数据/报告的打开方式仍需更自然、更低门槛。

### L4 估值锚口径确认

- 人工/Wind 是最高信任、可选输入的主锚：当前重点支持 `PE`、`PB`、`PS`、`ERP` 及其 5/10 年分位。
- Trendonify 是有价值的自动分位来源；若普通采集遇到 403，本轮只记录不可用和后续待解决，不硬绕、不静默退回 yfinance。
- WorldPERatio 不只是 PE 校验源；它的 Nasdaq 100 PE、均值、标准差、估值区间和滚动口径可与人工数据互参，用来辅助描述相对位置。但如果页面没有明确 percentile/rank，不能写成历史百分位。
- Damodaran implied ERP 是美国市场风险补偿背景锚，不替代 NDX 自身 PE / PB / PS / Forward PE 分位。
- yfinance component model 保留为当前值、覆盖率和口径校验，不承担历史估值 regime 主判断。

| 顺序 | 类别 | 任务 | 为什么重要 | 完成标准 |
| --- | --- | --- | --- | --- |
| 1 | 数据基础 | 继续观察 Trendonify 的可用路径 | 当前普通 HTTP 访问仍 403；系统已能正确承认不可用，但 Trendonify 的历史分位价值很高 | 决定是否做浏览器采集、缓存、或人工录入路径；不得静默 fallback 成 yfinance |
| 2 | 输出体验 | 暂缓 brief 大改，只记录阅读卡点 | 审美和交互应等证据链稳定后升级 | 只记录来源、覆盖率、更新时间、简式收益差距标签和百分位展示的阅读问题 |

---

## 三类目标是否合理

合理，而且建议固定为以后所有计划的一级分类。

### 1. 核心系统

这是“怎么推理”的问题，也是当前重中之重。

包括：

- L1-L5 是否保持上下文隔离；
- 每层是否有指标级分析、层内综合、内部冲突、自检；
- Bridge 是否生成 typed conflict / resonance / transmission map；
- Thesis 是否只整合，不重新脑补；
- Critic / Risk / Reviser / Final 是否保留冲突、风险和证据边界；
- governance input 是否减少 token，同时不丢关键证据。

判断标准：推理链是否干净、具体、可追溯，不为了顺滑结论抹平张力。

### 2. 数据基础

这是“凭什么推理”的问题。

包括：

- 数据采集是否稳定；
- 指标定义是否清楚；
- 历史频率、发布日期、观测日期是否区分；
- 数据是否需要 fallback；
- 哪些指标只是代理，不能当官方事实；
- L3 广度、成分股、集中度、领导力扩散等结构数据是否足够。

判断标准：系统在不知道时能承认不知道，在数据弱时能降低置信度，而不是用漂亮文字掩盖缺口。

### 3. 输出体验

这是“别人怎么读懂、怎么追问”的问题。

包括：

- 默认报告是 `brief`，还是另一个更适合连续阅读的模板；
- 是否需要正式前端 viewer；
- evidence ref 跳转是否顺手；
- 风险、冲突、反证是否醒目；
- 普通读者是否能从最终判断一路追到证据；
- 页面审美是否专业、克制、耐读。

判断标准：读者不需要懂代码，也能明白结论从哪里来、哪里有风险、什么证据会改变判断。

---

## 三类之间的关系

优先级不是永远固定的，但依赖关系很清楚：

1. 数据基础是地基。数据不准，核心系统越强，越可能严肃地分析错误材料。
2. 核心系统是骨架。没有干净推理链，输出体验只是把混乱包装得更好看。
3. 输出体验是交付面。没有好的阅读和交互，系统再强也很难被人持续使用和审查。

因此当前策略是：

- 核心系统继续作为第一优先级；
- 数据基础作为并行审计线，不能长期欠账；
- 输出体验等 `brief` 经过真实阅读验证后，再决定是否正式前端化。

---

## 当前不优先做

- 不新增更多 agent 角色。
- 不把 L3 立刻升级为 hard fail。
- 不把 `RESEARCH_CANON.md` 大段塞进 prompt。
- 不继续美化 legacy HTML。
- 不在 `brief` 信息架构确认前急着上正式前端框架。
- 不用未经证据支持的历史概率、回测收益、样本期包装判断。

## 靠后观察：外部库启示

- OpenBB 的启示是“数据源要有 provider、口径和可发现工具”，短期先学它的数据治理方式，不急着把整个平台接进来。
- vectorbt 的角色是离线实验室：以后用来检验策略假设和冲突场景，不让回测结果直接污染 L1-L5 的本次运行判断。

---

## 需要用户判断的点

1. `brief` 页面是否真的适合作为默认阅读入口。
2. 数据线优先补 L3，还是先做全量数据覆盖复盘。
3. 输出体验下一阶段是继续 self-contained HTML，还是准备正式 viewer。

---

## 验证命令

全量测试：

macOS / Linux：

```bash
python -m pytest -q
```

Windows PowerShell：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

生成四个 UI 模板：

```powershell
.\.venv\Scripts\python.exe src\agent_analysis\vnext_reporter.py --run-dir output\analysis\vnext\<run_id> --template all --output output\reports\vnext_ui_template.html
```

真实 smoke：

```powershell
.\.venv\Scripts\python.exe src\main.py --models deepseek-v4-flash,deepseek-v4-pro --data-json output\data\data_collected_v9_live.json --skip-report --disable-charts
```
