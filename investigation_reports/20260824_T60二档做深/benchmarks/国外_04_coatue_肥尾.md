# 国外_04：Coatue 公开 AI 主题 deck 系列（EMW Keynote 2023–2025）拆解

> 诚实声明（先读这条）：任务指定的《Fatter Tail: The AI Revolution》（2024 年 12 月发布）**未能核实存在**。WebSearch、Bing 全文检索（`"coatue" "fatter tail"`）及 coatue.com 官网全部页面均无此标题；Coatue 公开 deck 的真实谱系是下文拆解的三件套。与该标题最接近的可核实内容：EMW 2024 deck 第 31 页有 "Macro likely moved from key market driver to **tail risk**" 的提法，以及官网 2023-11-16 博客《AI: The Coming Revolution》。怀疑"肥尾 + 2024年12月"来自某中文二手转述的误标。以下拆解基于实际打开并逐页阅读的一手材料。

## 1. 出处（标题、作者/机构、日期、URL、是否全文可得及材料边界）

本拆解覆盖 Coatue 公开 AI 周期判断的三代版本（同一框架的年度连载）：

**A. 《AI: The Coming Revolution》（2023 版，全文可得）**
- 机构：Coatue Management；署名作者 Sri Viswanath、Vibhor Khanna（PDF 封面另有 Yijia Liang）
- 日期：官网博客 2023-11-16；PDF 元数据 CreationDate 2023-11-09
- 官方博客（实际打开，curl 200）：https://www.coatue.com/blog/perspective/ai-the-coming-revolution-2023
- 官方 deck 嵌入预览（页内 iframe）：https://drive.google.com/file/d/1gQhYT7j6b2wJmrFZHNeQgTiWPyTsjOfX/preview
- 全文镜像 PDF（115 页，实际下载并用 pypdf 提取全文）：https://readwise-assets.s3.amazonaws.com/media/wisereads/articles/ai-the-coming-revolution/The_AI_Revolution.pdf

**B. EMW 2024 Keynote《Coatue View on the State of the Markets》（2024-06，只读非全文下载）**
- 机构：Coatue；主讲 Philippe Laffont 等（EMW = East Meets West 年度大会 keynote）
- 官方汇总页（实际打开，curl 200）：https://www.coatue.com/east-meets-west （"EMW 2024 PDF" 按钮）
- 官方 deck（实际打开于 Google Drive viewer，50 页）：https://drive.google.com/file/d/184tgms_70fL5P0b1l83qSXk8vpFr4kfl/view
- 官方会议回顾博客（实际打开）：https://www.coatue.com/blog/company-update/coatues-2024-emw-conference
- 材料边界：**官方设为 view-only，禁止下载**（Drive 返回 "Can't download file"，登录态浏览器实测亦然）。本次通过 Drive viewer 逐页截图（50/50 页）+ 文本层提取阅读，关键页逐一目读，非逐页全文精读。deck 内部数据标注 "as of June 2024"。

**C. EMW 2025 Keynote（2025-06，只读非全文下载）**
- 官方 replay 博客（实际打开）：https://www.coatue.com/blog/company-update/coatues-2025-emw-keynote-replay （2025-06-23，"Coatue State of the Union" keynote，Philippe Laffont + Thomas Laffont + Lucas Swisher + Jaimin Rangwalla）
- 官方会议页（实际打开，含 deck 嵌入）：https://www.coatue.com/blog/company-update/coatues-2025-emw-conference
- 官方 deck（实际打开于 Drive viewer，102 页）：https://drive.google.com/file/d/1Srl8Y4pBoKtNVYZBxmfj2TEMYM5tp1mE/preview （页内预览链接；同页另有 3 页 Disclosures 附件 https://drive.google.com/file/d/1y_h0Fw6imZKNxE1bM2dLblvO61X4nyEs/view）
- 材料边界：同样 view-only。本次用页码跳转 + 截图抽读约 15 页（封面、议程、AI 主线、capex、情绪对照、方法论页），并抓取了全文文本层碎片（图表内文字）。未逐页精读全部 102 页。

**D. 2025 年下半年流传的"400 年泡沫研究"版本（仅二手，未能定位一手）**
- The VC Corner（2025-11-02，付费墙，实际打开免费段）：https://www.thevccorner.com/p/coatue-ai-report-18-charts 称 Coatue "studied 30 market bubbles across 400 years"、全文 59 页、给出 "AI Abundance (probability >66%) vs AI Reckoning (<33%)" 情景概率。但在 coatue.com 官网（含 C:\Takes 栏目全部 slug，实际打开核对）未找到对应一手发布；EMW 2025 deck 内我抽读到的长历史图是 **1800–2025 行业市值集中度图**（约 225 年），"400 年 30 个泡沫"的说法未能在一手材料中复现。**凡涉及该版本的表述本文一律标注为二手转述。**

## 2. 选取理由（影响力证据）

Coatue 是 AUM 约 $54–70B 的跨一二级市场科技对冲基金（ Forbes 人物页、vcsheet 简介，搜索结果确认）， Philippe Laffont 主讲；其 EMW keynote deck 是对冲基金圈被引用最广的公开 AI 周期判断，EMW 页自引 Bill Gurley 为大会背书。实际打开的引用/转述证据：

- **The VC Corner**（Ruben Dominguez，VC 向 newsletter，2025-11-02）："Coatue just published one of the most talked-about reports in tech and finance this year"，付费长文逐图拆解 18 张幻灯片（上文 D，实际打开）。
- **AI Supremacy**（Michael Spencer，大型 AI newsletter，2025-06-22，实际打开）：专文拆解 EMW 2025 的 "Fantastic 40 by 2030" 预测名单，讨论 "Google 落榜、OpenAI 进前十" 引发的争议；并给出 Coatue 分量依据："over 50 AI-related companies in their portfolio"、"raised a $1 billion fund specifically for AI investments in 2024"。
- **Fabrica Ventures**（VC 官方博客，2025-06-29，实际打开）：逐条转述 EMW 2025 keynote 十个论点（浪潮史、ChatGPT 800M MAU、capex $365B 等），标题即 "AI Supercycle in Motion"。
- **SaaSletter**（Matt Harney，SaaS 研究 newsletter，2024-07-16，实际打开）：EMW 2024 专题快评，称 "the ever popular 'Coatue View on the State of the Markets'"。
- **Henrik Torstensson**（Alliance VC 合伙人，2024-07-12，实际打开）：推荐 EMW 2024 State of the Market 演讲视频。
- **中文圈**：微信公众号/腾讯新闻/雪球 2024-07-24 同文《Coatue答2024：AI没有泡沫，美国VC退出也难》多点转载（腾讯新闻页实际打开，curl 200：https://view.inews.qq.com/a/20240724A08MU900）。

## 3. 证据结构（数据点与来源；一手披露占比；来源档次）

deck 的证据页脚模式统一：每个数字都带 "Source: Bloomberg as of June 2024" 式标注 + 大段免责声明；附录自述 "Coatue has derived this information from publicly available information and/or data from third party sources… have not been independently verified"。即**它是"数据策展 + 观点合成"，几乎零一手披露**；唯一接近一手的是 2023 版引用的 "~600 enterprise executives" AI 认知调查和 Coatue 自身组合观察。来源档次分布：Bloomberg/CapitalIQ（行情财务）、公司财报口径、Ramp（企业 AI 付费渗透）、World Bank/Statista（宏观）、Morgan Stanley Research（渗透率）、GitHub/Hugging Face（开发者生态）——主流二手数据源为主，来源标注纪律好。

代表性数据点（均从我实际打开的页面/截图读取）：

- 泡沫对照（EMW 2024 p20）："AI is not a valuation bubble like .com era" —— Cisco 1999：5 年均值 37x P/E → 峰值 132x；NVDA 2024：5 年均值 40x → 当前 39x。**用"龙头估值没扩张"反驳"泡沫"**。
- capex 可承受性（EMW 2024 p23-24）：2030 AI Infra 成本测算 = 25M GPU（2024 约 5M）、约 $1.2T、相当于 "18% of global IT spend"；ROI 桥：$1.2T 投入按 25% ROIC 需约 $1.8T 年价值创造 = "5% of global payroll" 的 OPEX 削减，**或** "$3.6T of revenue generation at 50% margin"（≈3% of global public co revenues / 2% of global GDP）。
- AI 对指数的贡献（EMW 2024 p9-10）：SPX YTD 归因 AI vs Non-AI，中位收益 "AI: 20% / Non-AI: 2%"；AI Infra 自 2023-01 以来新增市值 "~$6T"。
- 渗透率（EMW 2025 p25）："Share of US business with paid subscriptions to AI (Ramp estimate)" 达 42%（Q1 2025），标注 "Positive inflection as reasoning models emerged!"。
- 采用速度（EMW 2025，经 Fabrica 转述并与 deck 文本层一致）：ChatGPT 30 个月 800M MAU（Facebook 用了 6 年）；Anthropic 年化收入 $1B→$2B→$3B 间隔分别为 21 个月/3 个月/2 个月；五大巨头 2025 年 capex 合计 $365B（+70% vs 2024，Fabrica 转述）。
- 缺席信号对照（EMW 2025 p40）："25-year sentiment indicators are near peak negativity"（商业/投资者/消费者情绪三图）对 "bleeding edge data shows resilience"（核心零售 trailing 28D 日频跟踪，"We are tracking data daily!"）。
- 行业结构（EMW 2025 p65）：估值 $50B+ 的私营公司合计市值 2015 年 $51B → 2024 $1,135B → 发布时 $1,357B。

## 4. 推理链（证据→结论的步骤；反方并置；可证伪性）

主链条（三代版本同一骨架，逐年更新数据）：

1. **浪潮定位**：1950s 以来七次技术浪潮（Mainframe→PC→Networking→Web1.0→Web2.0→Cloud/SaaS→GenAI），每次约十年；AI 是下一个 supercycle（2024 p11 明确画出 "Coatue's View" 曲线高于 "Consensus View"）。
2. **采用速度**：渗透率每次平台更迭减半时间（2023 版 p7 引 Morgan Stanley）；ChatGPT 800M MAU / 30 个月。
3. **估值辩护**：不是 1999 —— 龙头 P/E 没扩张（NVDA 39x vs Cisco 132x），盈利真实；1999 七巨头均值 67x vs 2025 约 28x（后者为 VC Corner 二手转述口径）。
4. **capex 可承受性与 ROI 桥**：把 AI 基建成本换算成全球 IT 支出/GDP/工资的百分比，再反推需要多少 OPEX 削减或收入创造来打平——这是全套 deck 最接近"可证伪阈值"的一页。
5. **赢家结构**：S 曲线四阶段框架（Phase 1 AI Core Infrastructure → Phase 2 Edge AI → Phase 3 AI Applications → Phase 4+ Physical AI，2024 p12）；"FAANG → Mag 7 → Sexy 6 → Fab 5 → AI 4" 缩写更迭（2024 p9）；2025 升级为 "Fantastic 40 by 2030" 名单预测。

反方并置（做得比多数卖方好，但服务于既定多头结论）：

- "Key Questions" 页用 ↑↓ 两栏并列 "Are we in an AI bubble? / Why is NVDA worth $3T?" 与 "Is software dead?"（2024 p19/p25）。
- "Battleground Debate: Is Software an AI Loser or Winner?"（2024 p27）明列空方论据："Will AI shrink the labor force and pressure seat-based monetization?"、"If AI drives cost of coding to zero, why buy software vs. build your own?"。
- 2025 版有 "Positives vs Watchouts" 双栏（p55："Events can scare, but trends define" 对 "Trees don't grow to the sky"）；VC Corner 转述称报告明列 "leverage is creeping back / retail investors borrowing" 为少数真实风险，并给出 "AI Reckoning (<33%)" 反情景（二手）。
- 局限：反方被呈现为"待回答的问题"，而非与多方同权重的证据菜单；结论方向（AI supercycle）从头到尾预设。

可证伪预测/阈值：

- **年度自我记分卡**：EMW 2024 p7 "How did Coatue do on its 2023 predictions?" —— "Dawn of a new super cycle" → "NVDA blew past our price targets"；"Hard landing unlikely" → "Economy even more resilient"。对错逐条公示。
- **群体预测对照**："Wisdom of our 2023 EMW crowd"（p4-6）把去年参会者投票（49% 认为市场未见底）与实际结果（Nasdaq +30%）对照，形成可复盘的时间序列。
- 明确阈值型预测少；多为方向性观点 + 事后记分。"AI 占美股市值 75%" 以提问形式给出（2025 p6），非承诺。

## 5. 方法特征

- **剧本化框架**：AI S-Curve 四阶段剧本（Infra→Edge→Apps→Physical），每年标注"我们走到哪了"——2024 说 infra 是最大赢家，2025 说 "new class of AI winners may take center stage"（AI Power +18% YTD 等），是同一剧本的时间序列化追踪。
- **历史类比**：Cisco 1999 vs NVDA 2024 估值对照；1993–2000 互联网/PC 生产率案例（2025 p45-46，员工/$1M 收入变化 + 格林斯潘式引文）；1800–2025 行业市值集中度长图（"Will AI reach 75%+ of total US market cap?"）。
- **自我归因与记分**：每年开篇先给去年预测打分、给参会者群体预测打分，再展开新论点——校准闭环前置到叙事开头，而不是藏在附录。
- **缺席信号/背离捕捉**：2025 p40 把 25 年情绪指标的极端悲观与日频硬数据的韧性并置（"市场感觉"与"实测数据"的背离本身就是论据）。
- **连载纪律**：EMW 2016 年起年度更新，同一框架迭代（acronym 更迭本身就是对"共识漂移"的追踪），配合 C:\Takes 博客做周更图表（官网实际打开，2026 年仍在更新 chart-of-the-day 系列）。
- **合规边界作为方法的一部分**：每页来源 + 日期 + "Coatue opinion and analysis" 归属分离，附录长免责声明明确"第三方数据未独立核实"——观点与事实的分层标注是可学的形式纪律。

## 6. 我们可学清单（3-5 条具体可迁移做法）

1. **年度自我记分卡前置**：每年新报告第一节先公示"去年预测 vs 实际"（Coatue Prediction / Reality 两列表），再讲新观点。可迁移为我们的"校准闭环"显性化：判断必须先展示上期对错，再发新判断——这直接服务我们的第三根支柱。
2. **ROI 桥式阈值**：把 capex 叙事换算成"需要创造多少价值才能打平"（$1.2T 投入 → $1.8T OPEX 削减 = 5% global payroll，或 $3.6T 收入 = 2% global GDP）。给我们的 capex 监控提供了可证伪的锚：不是问"capex 大不大"，而是问"兑现路径占全球工资/GDP 的百分之几、按季偏离多少"。
3. **群体预测作为对照组**：记录参会者/市场共识投票，次年对照实际结果。我们能低成本复刻：把每期自家判断与市场一致预期（卖方调查、预测市场）同表存档，事后双向评分——既评自己也评共识。
4. **多空并置的版式纪律**：↑↓ 双栏 Key Questions、"Battleground Debate" 把空方论据原文列出再逐条回应。对应我们"证据面均衡"的落地形式：反方不是风险章节的一句话，而是与多方同版式、同颗粒度的并置。
5. **"缺席信号"页**：情绪 25 年极端悲观 vs 日频硬数据韧性的并置，是捕捉"该发生没发生/该弱不弱"的范式。我们的事件层可以专设"背离页"：叙事温度（媒体/情绪代理）与高频事实（每日跟踪序列）的差值本身就是信号。

---

### 附：本次实际打开过的 URL 清单

一手：coatue.com/east-meets-west、/blog/perspective/ai-the-coming-revolution-2023、/blog/company-update/coatues-2024-emw-conference、/blog/company-update/coatues-2025-emw-conference、/blog/company-update/coatues-2025-emw-keynote-replay、/c/takes；Drive viewer 三个文件（id: 184tgms…/EMW2024 50页、1Srl8Y…/EMW2025 102页、1y_h0F…/EMW2025 Disclosures 3页）；readwise-assets.s3.amazonaws.com 的 2023 版全文 PDF。
二手（影响力证据）：thevccorner.com、ai-supremacy.com、fabricaventures.com、saasletter.com、torstensson.com、view.inews.qq.com 各一篇（URL 见第 2 节）。
