# 输出体验 4-5 步通俗说明

## 一句话说明

这次把图表正式放进 native `brief` 报告，并做了一个第一屏研究控制台：用户可以先看图表证据，再从同一入口处理人工数据、模型选择、运行命令和报告打开。

补充更新：在四张市场总览图之后，又把 L1-L5 底稿里的必要指标做成了“指标旁微图”。现在图表不只集中在前面的“市场图谱”，也会贴着每个指标解释它的相对位置、组成、分歧或技术区间。

再次补充：指标旁微图仍然不是“看盘软件”。它们适合快速读懂底稿，但不适合像 TradingView 那样缩放、悬停、比较、切换时间范围。因此本轮又新增了一个独立的交互图原型页面，用来验证真正的看盘式图表应该长什么样。

## 为什么要改

只靠文字报告有一个问题：结论看起来完整，但读者很难快速判断“关键证据到底长什么样”。尤其是 L4 估值层，PE、ERP、WorldPERatio 标准差语境、真实利率压力这些信息，天然适合用图表先展示相对位置，再让文字解释原因。

控制台也是同一个逻辑。人工/Wind 数据、flash/pro 模型、数据源健康和报告入口如果分散在命令行、配置文件和输出目录里，用户每次运行都要重新想一遍流程，门槛太高。

## 参考了哪些成熟产品

- TradingView Supercharts 的启发：图表不是附属品，而是分析空间的中心；同一图表要能比较资产、套用指标、保存模板、快速切换工具。
- Bloomberg Terminal 的启发：专业金融工具强调自定义工作区、监控、告警、图表和新闻的组合，目的是帮助快速决策，而不是只展示漂亮页面。
- Koyfin 的启发：一个好 dashboard 要让用户在同一屏组织 watchlist、图表、数据表和分享入口，减少来回切换。
- Financial Times Visual Vocabulary 的启发：不同数据问题应该用不同图形。时间序列用线图，正负偏离用发散/压力尺，类别比较用表格或条形结构。

## 实际做了什么

1. native `brief` 新增“市场图谱”章节。
2. 报告内新增四张原生图表：
   - L4 估值相对位置尺。
   - Damodaran ERP 月度路径。
   - WorldPERatio 窗口标签。
   - L1-L4 利率估值压力图。
3. 每张图绑定 evidence ref，点击后仍能回到指标底稿。
4. Damodaran 月度解析器现在保留 `monthly_series`，未来真实 run 可直接画 ERP 月度线图。
5. 新增 `src/research_console.py`，生成 `output/reports/vnext_research_console.html`。
6. 控制台第一屏包含人工/Wind 输入、flash/pro 选择、数据源健康、运行命令、报告入口和人工模板保存。
7. L1-L5 指标卡新增内联微图：历史分位、5 年/10 年语境、z-score、均线偏离、组成项、广度、M7 基本面、估值源、收益差距压力、技术区间和资金流确认都能在底稿旁边看到。
8. 复杂指标采用可展开图。例如 Fear & Greed 可以展示分项，M7 基本面用热力格但默认折叠，避免底稿变得过长。
9. 安装 `lightweight-charts@5.2.0`，生成独立交互图原型 `output/reports/vnext_interactive_charts_20260502.html`，包含 QQQ K 线、成交量、MA5/20/60/200、区间按钮和 crosshair 读数。
10. 修复 brief 页面 JSON 嵌入错误，避免浏览器端解析失败影响证据抽屉和跳转。

## 修改后有什么变化

读报告时，读者不用先吞完整段落，就能看到估值压力的大致位置、ERP 的官方月度路径是否可用、WorldPERatio 只是在标准差语境里发言，以及利率压力是否和估值压力同向。

做研究时，用户不必先记命令和文件路径。控制台会把常用选择摆出来，并生成清晰的运行命令。它现在不直接执行本地命令，这是有意保守：第一版先降低操作认知负担，不急着把浏览器变成本地任务执行器。

## 刻意没有做什么

- 没有接入重型前端框架。当前信息架构还在确认，self-contained HTML 更稳。
- 没有把旧 legacy chart 系统作为主产品。图表直接从 vNext artifacts 和 `analysis_packet.raw_data` 取数。
- 没有给每一个数字硬配图。只有能说明“位置、变化、结构、分歧、区间、压力”的数据才画；没有上下文的单点值仍保留文字。
- 没有把交互看盘图直接塞进 brief 主报告。brief 是阅读空间，看盘图是探索空间；两者先分开，避免报告变得笨重。
- 没有把 WorldPERatio 标准差标签写成历史分位。
- 没有让控制台直接改写 `manual_data.local.json` 或直接执行 DeepSeek run。浏览器下载模板更安全，运行命令由用户确认后执行。
- 没有重新跑 DeepSeek 全链路。新版报告沿用已有 run 生成；下一次真实 run 会自然带入新 Damodaran 月度序列和 WorldPERatio 结构化字段。

## 如何验证有效

- 针对报告和控制台新增测试：确认图表章节、四类图表、evidence refs、控制台六个第一屏能力都存在。
- 针对指标级可视化新增测试：确认 L1 相对位置、L2 情绪分项、L3 广度和 M7、L5 均线与 Donchian 通道都会出现在对应指标卡里。
- 针对 Damodaran 月度解析器测试：确认月度最新行和 `monthly_series` 能被解析。
- 用真实历史 run 重新生成 `output/reports/vnext_research_ui_brief_20260502.html`。
- 重新生成后的旧 run 报告包含 29 个指标级微图。
- 交互图原型已在 in-app browser 打开检查：K 线、均线、成交量、3M/6M/1Y/ALL 按钮可见，当前页面无脚本错误。
- 生成 `output/reports/vnext_research_console.html`。
- 用 Chrome headless 截图检查报告首页和控制台首页，确认页面可渲染、控制台第一屏可读。

## 普通读者该怎么看

这次不是“做得更花”，而是把证据放到更接近人类判断的位置：先看图，再读解释，再点开底稿。图表不代替推理，但能更快暴露冲突。

控制台也不是正式产品壳，而是第一块操作台。它先解决“我下一步该填哪里、选哪个模型、怎么运行、报告在哪里”的问题。

## 后续最重要的观察点

1. 下一次真实 run 后，Damodaran ERP 月度线图是否能展示 2026-05-01 这类最新数据。
2. WorldPERatio 窗口标签在真实报告里是否足够清楚地区分“标准差语境”和“历史分位”。
3. 控制台是否应该进入第二阶段：真正写入本地人工模板、启动运行、打开最新报告。
4. 图表是否需要移动端专项优化和截图回归测试。
5. evidence hash 直达体验还要继续修：直接打开某个 `#evidence-...` 时，应自动展开对应层级并高亮指标卡。
6. 交互图的数据要不要进入 vNext artifacts。当前原型的 QQQ OHLCV 是生成页面时拉取，下一步最好让 run 本身保存时间序列，保证图表和文字同源。

## 简单词汇表

- evidence ref：证据引用，点击后能回到对应指标底稿。
- ERP：权益风险溢价，表示股票相对无风险利率要求的补偿。
- 月度序列：每个月一行的数据，用来观察变化趋势。
- 标准差语境：说明当前值离历史均值有多远，但不等于历史分位。
- first-screen 控制台：打开页面第一屏就能完成主要操作选择的控制界面。

## 参考来源

- TradingView Help Center: Getting started with Supercharts, https://www.tradingview.com/support/solutions/43000746464-getting-started-with-supercharts/
- Bloomberg Professional Services: Bloomberg Terminal, https://professional.bloomberg.com/products/bloomberg-terminal/
- Koyfin: Custom Dashboards, https://www.koyfin.com/features/custom-dashboards/
- Financial Times Visual Vocabulary PDF, https://cobwebstorage.blob.core.windows.net/deicasecompfileuploads/Visual-vocabulary-Financial%20Times.pdf
