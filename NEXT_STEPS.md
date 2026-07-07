# vNext 下一步

更新日期：2026-07-06

阅读方式：本文件只记录两类内容：

1. 当前仍未完成、需要后续执行的事项。
2. 尚未排进施工队列、但值得保留的后续方向思考。

已经完成的事项不在这里维护，统一看 `WORK_LOG.md`。架构原则看 `ARCHITECTURE.md`，运行复盘看 `RUN_REVIEW_CHECKLIST.md`，数据边界看 `DATA_COVERAGE_REVIEW.md`。

---

## 当前待完成

| 优先级 | 类别 | 待办 | 为什么重要 | 完成标准 |
| --- | --- | --- | --- | --- |
| P0 | vNext 第 5 步：claim 级结果记分 | 按 `docs/2026-07-06_STAGE0-4_REVIEW_AND_DIRECTION.md` 的“修正二”扩展 `outcome_review.py`，让每条 final claim 在 T+20/60/120 交易日窗口可被逐条复盘 | 第 4 步读者出口已经把 claim 台账翻译成买入/卖出条件差距；下一步要让系统知道哪些 claim 类型和证据来源事后真的有诊断力，否则流程可审计但学习闭环仍缺半边 | 任选一个历史回测 run 能产出 `claim_outcome_scores.json`；每条 claim 输出 `verdict(consistent | falsifier_triggered | not_scorable)` 和 `scoring_evidence`；`not_scorable` 必须写明原因；跨 run 聚合脚本能按 `claim_type` 和 `source_tier` 汇总表现；打分产物不得进入后续 run 的 L1-L5 输入 |
| P0 | 核心系统 | Mao / Decision 主链最新验收与薄点修复 | 主要矛盾、次要矛盾、五类价格反映、踏空/确认成本和 Run Review 检查已经落地；现在不是从零重构，而是要用最新 L4 数据源上位后的 fresh run 验证整条链是否还稳，防止字段有了但读者结论又退回口号 | 用最新数据跑完整链路并生成 `brief`、Prompt Inspector、Run Review；Bridge / Thesis / Risk / Final 都能用人话说明主要矛盾、价格反映、赔率、核心/战术/等待动作和失效条件；Run Review 对 data / bridge / thesis / risk / final / expression 无 fail；Prompt Inspector 未发现跨层污染或旧立场锚点 |
| P1 | 数据基础 | L3 广度、集中度和历史成分数据补强 | L4 已接入 Wind NDX 风险溢价和指数级估值主锚，当前更大的数据短板回到 L3：NDX 是市值加权指数，如果没有更好的广度、等权、Top10 权重和 point-in-time universe，系统仍容易把“少数龙头很强”误读成“整个指数健康” | 为 `get_advance_decline_line`、`get_percent_above_ma`、`get_new_highs_lows`、`get_mcclellan_oscillator_nasdaq_or_nyse`、`get_ndx_ndxe_ratio`、Top10 权重建立更稳定来源或明确 fallback；实时和回测都写清数据日期、覆盖率、口径和不能证明什么；缺数据时降低置信度，不用 L5 价格趋势替代 L3 内部健康 |
| P1 | 核心系统 / 输出体验 | 三层研报架构接入攻坚 | 形成三个独立入口：1）现有 vNext 纯数据研报继续只基于正式数据和 L1-L5 / Bridge / Thesis / Risk / Final；2）新增独立新闻/事件简报，整理 Fed、SEC、Nasdaq、Invesco、公司 filings、官方新闻稿、主流新闻和市场叙事；3）新增综合总报告，读取纯数据研报和新闻简报，做交叉质询并生成谨慎但明确的综合解释。通俗路线见 `docs/2026-06-27_THREE_LAYER_REPORT_ARCHITECTURE_PLAIN.md`。当前先不新建 skill，重点先落在产物关系、阅读入口和工程路线 | 分三步验收：1）纯数据研报仍能独立生成 native brief / Prompt Inspector / Run Review，且不接收新闻；2）能独立生成 `news_event_brief`，写清事件事实、来源、日期、市场相关性、解释和限制；3）能生成 `integrated_synthesis_report`，明确区分数据支持、新闻支持、综合解释、置信度、反证和后续观察；三份报告独立落盘、独立入口、互相引用但不互相覆盖，综合报告允许解释，但不得用单条新闻冒充复杂市场因果证明 |
| P1 | 输出体验 | 研究控制台重做为简洁用户启动器 | 当前控制台把运行启动、开发命令、人工数据、sidecar、产物索引和安全说明混在一页；用户真正需要的是选择运行模式、是否回测、是否收集新闻材料，然后开始运行并查看状态。详细计划见 `docs/2026-06-16_RESEARCH_CONSOLE_SIMPLIFICATION_PLAN.md` | 主界面只保留完整运行/仅收集数据/用已有数据分析、末次数据摘要、是否回测、收集新闻材料、开始运行、状态、最新报告/workbench/日志入口；Trendonify、workbench 模块多选、人工数据大表和命令预览默认不在主界面常驻；桌面和 390px 手机宽度检查通过 |
| P2 | 数据基础 | 采集机 / 快照模式收尾 | `--collect-only`、`--data-json`、控制台入口和 README 两段式说明已经存在；下一步不是重建，而是把“同一数据快照贯穿采集、分析、报告、复盘”的用户体验和审计痕迹补齐，减少半截数据、半截分析、网络路径切换造成的不可复现 | 用一轮真实两段式 run 验证：采集阶段生成不可变数据快照、chart/news sidecar、校验摘要和数据边界；分析阶段只消费同一快照；`run_summary.json`、brief、Prompt Inspector 和 Run Review 都能清楚显示使用了哪份快照、采集时间、有效日期、跳过项和缺口 |
| P2 | 文档治理 | 文档归档与入口瘦身 | 根目录主文档仍可用，但 `docs/` 中多份 4 月旧审计/实验材料已不是当前事实，容易让后续 agent 误读 | 列出保留/归档/删除候选；历史材料优先移入 `docs/archive/` 并加索引；根目录通俗报告保留索引，避免散落文档互相抢入口 |

---

## 后续方向思考

这些不是当前施工清单。只有当它们被拆成明确完成标准后，才移入“当前待完成”。

### 核心推理

- 保持 L1-L5 context isolation 为硬红线：L1-L5 可以知道静态职责边界，但不能看到其他层本轮运行时数据、摘要、结论、候选跨层关系或 Thesis / Bridge 当前判断。
- Decision Semantics 的字段已经扩到主要矛盾、价格反映、赔率和动作层；后续重点是 fresh run 里的表达质量和一致性，不是继续堆术语。
- Bridge / Thesis / Final 已经有主要矛盾字段和 Run Review 检查；后续要防止模型虽然填了字段，却没有真正说明“哪一面占支配、哪些证据会让判断转化”。
- Prompt Inspector 已经取代正文 Agent IO Audit 成为主要审计入口；后续可补语义级下游追踪，但不应恢复大块正文审计。

### 数据基础

- L3 仍是关键薄弱层：广度、集中度、point-in-time universe 和历史结构数据需要继续补源；不能用价格强弱替代内部健康度。
- 严格回测仍有长期升级空间：ALFRED first-vintage、财报 first-reported、point-in-time NDX universe 和 LLM 后验知识都已明示为限制，但尚未工程化解决。
- 新闻、浏览器、登录态工具和 sidecar 结果默认不得进入 L1-L5 evidence refs。后续方向不是把新闻塞进纯数据研报，而是单独生成新闻/事件简报，并在第三层综合总报告中与纯数据研报交叉质询、谨慎解释。
- L4 已经改为 Wind NDX 风险溢价和指数级估值主锚；Damodaran、WorldPERatio、yfinance / Yahoo / SEC / 东财保留背景、参照、成分解释和对照校验角色。后续只在 fresh run 或源冲突暴露新问题时再补，不再作为当前独立 P1 待办。

### 输出体验

- `brief` 是连续阅读报告；workbench 是看盘式探索页面；控制台是运行前配置面板。三者不要互相替代。
- Prompt Inspector 是审计主入口；brief 只保留轻量 Agent Health，避免正文被审计材料压垮。
- 图表应继续绑定 evidence refs。图表负责暴露位置、趋势、分歧和压力，不替代文字推理。

### 文档治理

- `NEXT_STEPS.md` 只放未完成和方向思考。
- `WORK_LOG.md` 只放已完成事实和验证结果。
- `ARCHITECTURE.md` 放长期原则和架构边界。
- `RUN_REVIEW_CHECKLIST.md` 放真实 run / 回测复盘流程。
- `DATA_COVERAGE_REVIEW.md` 放数据源覆盖、fallback、有效日期和置信度边界。

---

## 暂缓或边界

- OpenBB：暂缓整个平台接入，只吸收 provider metadata、coverage discovery 和数据治理思路。
- Trendonify：真实浏览器 sidecar 已落地；主链仍不硬绕 403，不静默退回 yfinance。
- Legacy Agent IO Audit 复杂化：不再作为正文主路线；Prompt Inspector 才是后续审计能力的主入口。
- 正式前端框架化：在 brief / console / workbench 信息架构稳定前继续保持 self-contained HTML。
- 新闻 LLM 解读：当前只做官方事件底账和事件-数据时间邻近连接，不做泛新闻情绪和摘要。泛新闻源后续应被三层研报结构替代：纯数据研报保持独立，新闻/事件简报单独解释外部世界，综合总报告再把两者合成一个更全面但有边界的解释。
- 交易执行、组合建议、自动下单：不属于 vNext 当前范围。
