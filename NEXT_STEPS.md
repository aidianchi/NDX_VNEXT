# vNext 下一步

更新日期：2026-05-07
阅读方式：最新事项放在最上面。完成后把结果写入 `WORK_LOG.md`，同样按时间倒序。

---

## 最新下一步

### 新一轮反馈：workbench 从展示图升级为可操作看盘台

- 用户对多模块 workbench 的两个批注成立，而且是第一优先级的交互债：
  - 主图一次性显示 MA5/20/60/200、Bollinger、Donchian、VWAP 和 Volume，虽然信息全，但默认画面过载。看盘台应允许用户像 TradingView 一样随时显示/隐藏指标，并提供“简洁 / 趋势 / 波动区间 / 综合”预设。
  - 主图和 Volume/OBV/MACD/RSI/ATR/MFI/CMF 副图目前只被同一个区间按钮粗略同步。真正的研究体验应支持共享时间轴、联动十字光标和缩放，也应允许临时解除联动做局部检查，然后一键“统一时间轴”回到同一窗口。
- 外部一手参照结论：
  - TradingView Advanced Charts 的指标体系支持添加、显示、位置和模板化，但官方说明 Advanced Charts/Trading Platform 不面向个人、爱好或测试使用，不能作为当前默认依赖；当前继续以 Lightweight Charts 为主更稳。
  - Lightweight Charts 官方 time scale 支持读取/设置 visible range，也支持订阅 range 变化；这足够实现“主图/副图时间轴锁定、解除锁定、统一时间轴”。
  - Highcharts Stock 的 range selector / navigator 提供成熟时间窗口和全局预览思路，适合借鉴“底部全局时间滑块”，但不必立即换库。
  - ECharts 的 legend selected、dataZoom、axisPointer 联动适合宏观多线图模块；后续若利率/估值/流动性模块要做归一化、多轴和强联动，可作为补充库候选。
- 第一性原则判断：workbench 不应只是“把报告里的图放大”。它要回答“我想看什么、隐藏什么、哪些 pane 共享同一时间、当前日期所有指标读数如何互相印证”。因此下一轮应优先补交互控制，而不是继续扩指标数量。
- 本轮已完成第一版可操作看盘台：L5 主图默认采用克制预设，支持指标显隐、图例点击切换、五类预设、副图折叠、时间轴锁定/解锁、一键统一时间轴、跨 pane readout；非 L5 模块支持序列图例显隐、归一化和双轴切换。最新输出：`output/reports/vnext_interactive_charts_20260506_controls.html`。
- 根据页面批注追加修正：L5 副图不再用 2x2 并列布局，改为全宽纵向 pane，并默认统一到同一 1Y 时间窗口；这样 Volume、OBV、MACD、RSI/ATR、MFI/CMF 与主图保持同一横轴阅读逻辑。
- 2026-05-07 追加修正：所有 L5 pane 统一右侧价格刻度最小宽度，解决主图与副图绘图区纵向轴线不齐；切换到波动信用、利率估值、广度集中度、流动性时，顶部摘要改为对应 layer 的精简分析，右侧 crosshair 改读当前模块序列，不再停留在 L5 OHLC/RSI。
- QQQ 交互图默认数据窗口从约 420 天扩到 1825 天；最新 `chart_time_series.json` 中 QQQ 行数为 1254，覆盖 2021-05-10 至 2026-05-06。页面默认仍打开 1Y 视窗，用户可点 ALL 查看完整窗口。

| 顺序 | 类别 | 任务 | 为什么重要 | 完成标准 |
| --- | --- | --- | --- | --- |
| 1 | 输出体验 | L5 主图增加指标显示/隐藏控制 | 默认全开会造成视觉拥挤，用户需要在简洁观察和综合验证之间切换 | 已完成：主图提供 Candles、MA5/20/60/200、Bollinger、Donchian、VWAP、Volume overlay 开关；默认克制；图例点击可切换 |
| 2 | 输出体验 | 增加指标预设模板 | 看盘软件的价值不是让用户每次手动点十几个开关，而是提供常用观察模式 | 已完成：提供“简洁价格”“趋势均线”“波动区间”“量价确认”“全部指标”；预设写入 localStorage，不污染 artifact |
| 3 | 输出体验 | 实现主图与副图时间轴锁定/解锁 | 当前副图共享窗口不够强，缩放/拖拽后容易失去同屏比较意义 | 已完成：增加“时间轴锁定”和“统一时间轴”；锁定时 visible logical range 联动，解锁后可局部检查 |
| 4 | 输出体验 | 联动 crosshair 与统一读数面板 | 用户看某一天时，需要同时读 OHLC、Volume、OBV、MACD、RSI、MFI、CMF，而不是只读主图；切换模块后还必须读当前模块序列 | 已完成：L5 主图/副图移动会更新统一 readout；非 L5 模块 crosshair 显示该模块序列值，并在支持的 Lightweight Charts 环境中同步 crosshair |
| 5 | 输出体验 | 副图 pane 重新分组与可折叠 | 四个副图好看，但不是每次都需要；移动端更容易拥挤 | 已完成：Volume、OBV、MACD、RSI/ATR、MFI/CMF 均可启停；移动端保持单列 |
| 6 | 输出体验 | 非 L5 模块增加 legend / normalize / dual-axis 控制 | VIX、OAS、10Y、ERP、流动性单位不同，简单多线图容易误导 | 已完成第一版：波动信用、利率估值、广度集中度、流动性模块支持序列显隐、归一化和双轴重绘 |
| 7 | 输出体验 | 为 workbench 交互增加回归测试 | 这类交互最容易在后续改样式时悄悄坏掉 | 已完成：测试覆盖指标开关、预设、时间轴按钮、模块归一化/双轴控件和 crosshair 同步代码；视觉回归保留桌面/移动截图 |

### 新一轮反馈：研究控制台从报告入口升级为总控开关

- 现有 `output/reports/vnext_research_console.html` 比旧 GUI 美观，但仍偏“命令生成页”。用户的定位更高：它应是 vNext 的运行前总控台，集中处理人工数据、模型选择、运行模式、可选数据源、报告/工作台生成和未来新闻源等扩展入口。
- 旧 `/Users/aidianchi/Desktop/launcher.py` 外观和交互确实落后，但功能线索有价值：人工 L4 顺序输入、历史时点分析、模型调用顺序、API 配置入口、新闻开关、图表叠加模式、运行模式选择和启动本地任务。这些不应被新控制台遗忘。
- 关键边界：self-contained HTML 默认不能直接安全写本地文件或执行命令。下一阶段应先做“高质量配置与命令面板”；若要真正一键运行，应建立一个明确权限边界的本地 control service，所有写文件/执行命令都必须有显式确认和日志。
- 本轮已完成第一版总控台重构：页面按六区组织，人工数据从纯 JSON 升级为结构化表单，运行模式、模型顺序、功能开关、workbench 模块、artifact 入口、数据源健康和一键运行安全方案均有明确位置。最新输出：`output/reports/vnext_research_console.html`。
- 根据页面批注追加修正：运行模式不再使用 full/data only/report only 这类旧式流程词，改为 vNext 当前架构语言：完整 vNext、只采集数据、已有数据分析、只生成 brief、只生成 workbench、视觉回归。人工估值输入改为 PE/PB/PS 各自成组，当前值、5Y 分位和 10Y 分位放在一起；旧版 HTML 明确标注为过渡期兼容产物，默认不建议使用。
- 2026-05-07 追加修正：控制台新增“运行”按钮。当前按钮调用本机 `127.0.0.1:8765` vNext control service；若服务未启动则明确提示没有执行命令。这保留了总控台的真实运行入口，同时不让静态 HTML 越权执行本地任务。

| 顺序 | 类别 | 任务 | 为什么重要 | 完成标准 |
| --- | --- | --- | --- | --- |
| 1 | 输出体验 | 重构控制台信息架构 | 总控台不能把所有开关堆成表单，应按真实研究流程组织 | 已完成：分成“运行对象与日期”“人工/Wind 数据”“模型与运行模式”“数据源/功能开关”“输出与工作台”“运行日志/健康/安全”六区 |
| 2 | 输出体验 | 人工数据从 JSON 文本升级为结构化表单 | 普通使用者不应直接编辑大段 JSON，且手填数值需要校验 | 已完成：PE/PB/PS/ERP/percentile/date/source/confidence 表单输入；保留高级 JSON 抽屉；空字段不覆盖；有范围校验和预览 |
| 3 | 输出体验 | 恢复并现代化运行模式选择 | 旧 launcher 的 full/data_only/report_only 等模式有实际价值，但 UI 文案必须符合 vNext 架构 | 已完成：可选完整 vNext、只采集数据、已有数据分析、只生成 brief、只生成 workbench、视觉回归；命令预览同步更新 |
| 4 | 输出体验 | 模型选择升级为“策略 + 顺序” | 只给 flash/pro 三个按钮不够表达 fallback 策略 | 已完成：提供 flash 优先、pro only、自定义顺序；默认 deepseek-v4-flash -> deepseek-v4-pro；不暴露密钥 |
| 5 | 数据基础 | 功能开关纳入控制台 | 新闻源、Trendonify、legacy charts、workbench 模块、图表叠加模式都应从同一处管理 | 已完成：控制台列出新闻源预留、Trendonify 暂缓、legacy charts opt-in、workbench 模块和 L5 默认预设 |
| 6 | 输出体验 | 报告与 artifact 入口升级 | 用户应能从控制台打开最新 brief、workbench、run 目录和诊断结果 | 已完成：列出最新 brief、workbench、run 目录和 visual regression summary；缺失时显示缺口原因 |
| 7 | 核心系统 | 评估一键运行的安全方案 | 直接在浏览器执行本地任务风险较高，但长期总控台需要真正启动能力 | 已完成第一版入口：页面有“运行”按钮，调用本机 control service；后续服务本体必须具备 allowlist、确认弹窗、日志、失败恢复和项目路径白名单 |
| 8 | 输出体验 | 控制台视觉与交互重设计 | 总控台应像专业研究终端，不像临时表单 | 已完成：高密度三列/响应式布局；desktop/mobile 截图已生成到 `output/reports/visual_regression/20260506_controls/` |

### 输出体验：L1-L5 指标级可视化已落地

- 用户指出“四张大图不应该是全部数据可视化”，这个判断成立。vNext 的底稿价值在于每个指标都有独立发言权，因此必要图表应贴近指标卡，而不是只集中在报告前部。
- 本轮已完成第一版指标级微图：L1-L5 指标卡会按数据形状展示历史分位/5Y/10Y/z-score、均线或基准偏离、组成项、广度、M7 基本面、估值源、Damodaran 当前 ERP lens、收益差距压力、技术区间、MA ladder、MACD、OBV、成交量和 Donchian channel。
- 设计原则已明确：只有能回答“位置、变化、结构、分歧、区间、压力”的数据才图表化；没有历史或结构语境的单点值不强行画图。
- 旧 `chart_generator.py` / `chart_adapter_v6.py` 仍可作为 legacy 参考，但 native brief 当前不把它们作为主路径。主路径应继续直接消费 vNext artifacts，避免图表数据和报告文字来自不同抓取时点。
- 旧 run `output/analysis/vnext/20260502_193057` 重新生成后，默认报告含 29 个指标级可视化；复杂指标使用可展开区，避免底稿阅读被大图打断。
- 进一步调研后确认：底稿微图不能替代看盘式交互图。已安装 `lightweight-charts@5.2.0` 并新增独立原型 `output/reports/vnext_interactive_charts_20260502.html`，用于验证 QQQ K 线、成交量、MA overlay、区间按钮和 crosshair readout。
- 已修复 native brief JSON payload 嵌入 bug，避免 `JSON.parse` 失败影响证据抽屉和跳转。
- 图表三层架构已固定：底稿微图回答“这个指标当下处在哪”，市场总览图回答“跨层压力和共振在哪里”，Lightweight workbench 回答“价格、成交量和技术结构如何交互探索”。三者不能互相替代。
- workbench 分层不应机械等同 L1-L5。L1-L5 是推理隔离层，适合底稿、审计和 evidence refs；workbench 是同屏比较层，应按“共享时间轴 + 共同研究问题”组织模块，并在每条序列上保留 L1-L5 来源标签。推荐模块为：价格技术、波动信用、利率估值、广度集中度、流动性。
- 交互图数据已开始纳入 vNext artifacts：主流水线会在 run 目录写入 `chart_time_series.json`，当前先保存 QQQ OHLCV、成交量和 MA5/20/60/200；workbench 优先读取该 artifact，只有缺失时才退回生成时报价抓取。
- evidence hash 直达已修复：直接打开 `#evidence-Lx-...` 会自动展开对应 Layer、滚动到指标卡并高亮，便于审查者直接分享和复核证据。
- 已用 2026-05-06 新采集数据完成真实 DeepSeek smoke：`output/analysis/vnext/20260506_075229`，并生成 `output/reports/vnext_research_ui_brief_20260505_20260506_075229.html` 和 `output/reports/vnext_interactive_charts_20260506.html`。
- 最新 packet 已确认吃到 Damodaran `ERPbymonth.xlsx` / `ERPMay26.xlsx`、`monthly_series=120`、WorldPERatio 结构化相对位置；Trendonify 仍不可用，应继续作为数据源边界。
- 最新 brief 指标级微图覆盖为 30 个：L1 7/8、L2 8/9、L3 5/6、L4 3/3、L5 7/9。无图项主要是缺少结构/历史语境的单点或节奏指标，不应硬画。
- 已建立 Chrome headless 视觉回归：桌面/移动截图覆盖 latest brief 与 workbench，摘要在 `output/reports/visual_regression/20260506_final/visual_regression_summary.json`。
- legacy Plotly chart 已退出默认主路径：`src/main.py` 默认关闭 legacy charts，只有显式 `--enable-legacy-charts` 才开启旧 HTML 图表。
- 用户确认暂缓 Trendonify 可用性，本轮按顺序完成 2-7：workbench 双层分类原则已固化；`chart_time_series.json` 已扩展到多面板序列；控制台新增 workbench 模块选择；L5 价格技术工作台升级为 K 线 + MA/Bollinger/Donchian/VWAP + Volume/OBV/MACD/RSI/ATR/MFI/CMF 副图；LLM 阶段新增 `llm_stage_diagnostics.json` 记录重试样本；视觉回归新增布局溢出风险检查。
- 最新多模块 workbench 原型：`output/reports/vnext_interactive_charts_20260506_modules.html`；控制台：`output/reports/vnext_research_console.html`；视觉回归摘要：`output/reports/visual_regression/20260506_modules/visual_regression_summary.json`。

### 指标级可视化后的下一轮观察

| 顺序 | 类别 | 任务 | 为什么重要 | 完成标准 |
| --- | --- | --- | --- | --- |
| 1 | 输出体验 | 明确图表三层架构 | 当前微图、市场总览图、看盘式交互图各自回答的问题不同，混在一起会让报告失焦 | 已完成：底稿微图用于速读，市场总览图用于跨层总览，Lightweight workbench 用于交互探索 |
| 2 | 数据基础 | 将交互图数据纳入 artifacts | 当前原型的 QQQ OHLCV 来自生成时 yfinance 拉取，和旧 run 的文字并非严格同一时点 | 已完成第一阶段：vNext run 保存 `chart_time_series.json`，workbench 优先读取；后续扩展 VIX、10Y、ERP monthly series |
| 3 | 输出体验 | 决定哪些指标进入 Lightweight workbench | 不是所有指标都适合 K 线式交互；L1/L4 更适合多轴线图或 regime panel | 已完成第一阶段决策：先纳入 L5 价格/成交量/均线，Donchian/MACD 暂从指标卡摘要进入，L1/L4 待多 pane 方案 |
| 4 | 输出体验 | 真实最新 run 后复核微图覆盖 | 旧 run 缺少最新 Damodaran 月度序列、WorldPERatio 结构化字段和未来新增 L5 量价质量指标 | 已完成：`20260506_075229` 生成 brief，覆盖审计通过，L5 量价质量指标新增微图 |
| 5 | 输出体验 | 修复 evidence hash 直达体验 | 浏览器直接打开 `#evidence-Lx-...` 时，目前主要依赖点击事件展开层级，直接 hash 直达仍不够自然 | 已完成：hashchange 和首屏加载都会自动展开、滚动并高亮对应指标卡 |
| 6 | 输出体验 | 建立图表视觉回归 | 指标微图和交互图数量变多后，移动端和长文本容易产生挤压 | 已完成第一版：`src/report_visual_regression.py` 截取 desktop/mobile，latest run 摘要 passed |
| 7 | 输出体验 | 决定是否正式弃用 legacy chart 主路径 | 旧 Plotly 图表仍在 legacy reporter 中存在，维护两套路线上会造成混乱 | 已完成：legacy chart 只服务旧 HTML，默认关闭；显式 `--enable-legacy-charts` 才启用 |

### 下一轮新观察

| 顺序 | 类别 | 任务 | 为什么重要 | 完成标准 |
| --- | --- | --- | --- | --- |
| 1 | 数据基础 | 继续解决 Trendonify 可用性 | 最新真实采集仍显示 Trendonify unavailable，NDX 历史估值分位仍缺一个高价值自动源 | 决定浏览器采集、缓存或人工输入路径；不得静默退回 yfinance |
| 2 | 输出体验 | 固定 workbench 双层分类原则 | 直接按 L1-L5 分会保留审计秩序，但会削弱同屏比较；直接按主题分会更直观，但可能丢失证据来源边界 | 已完成：底稿/审计按 L1-L5；workbench 按价格技术、波动信用、利率估值、广度集中度、流动性组织；模块与序列保留 Layer、function_id、provider、frequency |
| 3 | 数据基础 | 扩展 `chart_time_series.json` 多面板序列 | workbench 当前只覆盖 QQQ OHLCV/MA/volume，VIX、10Y、ERP、广度和流动性仍不能同源交互 | 已完成：artifact 增加 VIX/VXN/VXN-VIX、HY/IG OAS、HYG、10Y/真实利率/breakeven/Fed funds、Damodaran ERP monthly、QQQ/QQEW、净流动性/WALCL/TGA/RRP、M2 YoY |
| 4 | 输出体验 | 重构 workbench 为研究模块选择器 | 控制台若按单个函数选择会淹没用户；按研究模块选择更接近真实看盘/投研工作流 | 已完成：控制台可勾选价格技术、波动信用、利率估值、广度集中度、流动性，并生成 `--modules` workbench 命令；workbench 页面也有模块 tabs |
| 5 | 输出体验 | 优先完成 L5 价格技术工作台 | L5 指标共享 QQQ 价格时间轴，最适合 TradingView 式交互，也最能检验突破、回撤和量价确认 | 已完成：主图含 K 线、MA、Bollinger、Donchian、VWAP；副图含 Volume、OBV、MACD、RSI、ATR、MFI、CMF；区间按钮同步主图和副图读数 |
| 6 | 核心系统 | 复盘 DeepSeek 输出稳定性 | 两次真实 run 暴露过 L1/L2 JSON parse retry、L5 coverage retry，以及 L4 超长输入 | 已完成第一阶段：新增 `llm_stage_diagnostics.json`，记录 stage、attempts、parse/schema/contract error、raw_excerpt 和 prompt_chars；后续真实 run 可直接定位重试成本 |
| 7 | 输出体验 | 提升视觉回归判定能力 | 当前视觉回归能确认截图非空并提供人工检查基线，但还不能自动识别横向溢出 | 已完成：视觉回归摘要新增 `layout_checks`，检测明显固定宽度超视口和移动端内联 nowrap 风险；最新 brief + 多模块 workbench desktop/mobile 均 passed |

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
| 1 | 输出体验 | 用最新真实 run 验证图表数据完整性 | 当前生成页沿用 2026-05-02 旧 run，旧 artifact 没有 Damodaran 月度序列和 WorldPERatio 结构化窗口 | 已完成：`20260506_075229` packet 含 Damodaran 月度序列和 WorldPERatio 结构化窗口，brief 已重新生成 |
| 2 | 输出体验 | 控制台第二阶段能力取舍 | 第一版控制台只生成模板和运行命令，不直接写文件或执行本地任务 | 决定是否允许控制台写入 `manual_data.local.json`、启动 run、自动打开最新报告；若做，必须有明确安全边界 |
| 3 | 输出体验 | 图表视觉回归 | 本机 Python/Node Playwright 未安装，已做 Chrome headless 截图，但还不是完整交互测试 | 已完成第一版：Chrome headless desktop/mobile 截图落盘，browser-use 检查 hash 和 workbench 可见 |

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
