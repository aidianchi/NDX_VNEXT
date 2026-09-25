# Q8 白名单深度复核：裁决层与数据层逐组件盘点

> **状态横幅（2026-09-21 追加）：本文件是 62 个组件的结构证据与初版裁决卡。其中内容层资产（提示词、范例、报告器文字装配）的裁决已被 `白名单_终版.md` 取代（内容验尸后升级为重写/重造）；本文件的证据层（体量、依赖关系、死物清单）仍然有效，裁决以终版为准。**
>
> 本文是研究战役 Q8"换器官"决策的白名单复核交付物。任务：把裁决层（`src/agent_analysis/`）和数据层（`src/core/`、`src/tools_*.py` 及根目录杂项）的每个组件逐个过堂，给出可直接拍板的保留/重写/删除清单。
>
> **证据口径**：每个论断带 `文件:行号`。行号以本次复核时的当前工作区为准；凡与 2026-09-15 快照的三份源码地图（`src_maps/`）一致的论断，直接沿用地图行号。所有"谁依赖它"均用 grep 实测 import 关系得出，不抄文档。
>
> **裁决尺**：每个组件按 QE 答卷的废物五问精神过堂（没有它判断还能否交付、它守的规矩是什么、手段是否合法、成本是否相称、该由谁接手），落进四档之一：**A=保留原样 / B=保留功能但接口重写 / C=重建 / D=删除候选**。
>
> **一个重要缺席声明**：任务书指定的 `research_fundamental/answers/Q8.md`（换器官总答案）在复核时**不存在**——`answers/` 目录下没有该文件，全仓 glob 无任何 Q8 文件，`research_fundamental/` 尚未入 git。本文末尾的"与粗表差异对照"因此以红队裁决（`redteam/wave1_critique.md` 第四节"按层分诊"：重建=主链编排器单体+提示词四源拼装；保留=事件层+第三层 IA）为重建基线。

---

## 一、汇总统计

**裁决分布（62 个盘点单元）**：

| 裁决 | 数量 | 行数合计 | 说明 |
|---|---|---|---|
| A 保留原样 | 51 | 约 48,373 行 | 含事件层 `event_research/`（2,554 行，只核接口不逐文件过堂） |
| B 保留功能、接口重写 | 6 | 14,402 行 | vnext_reporter 7,019 + prompts/ 目录 2,829 + tools_L3 1,999 + tools_L1 1,418 + main.py 1,022 + tools.py 115 |
| C 重建 | 1 | 9,954 行 | orchestrator.py 一个文件 |
| D 删除候选 | 4 | 4,114 行 | legacy_adapter 957 + core/reporter 558 + chart_generator 2,410 + reasoning_examples 189（最后一项是盘点范围外补充） |

**口径说明**：

- 盘点总行数 76,843 行（`src/` 下在范围内的 Python 文件 + `prompts/` 目录 19 个 md）。另有 `report_styles/` 五个 CSS 共 10,792 行样式资产，随 vnext_reporter 保留，不计入上表行数。
- C 档的"提示词四源拼装层"物理上住在 orchestrator.py（内联 v2 合约 8066-8124、bridge 合约 8133-8164、thesis 合约 8167-8230、INLINE_PROMPTS 兜底 337-345）与 llm_engine.py（system 兜底 513-520）里，共约 200 行，已在两个文件的行数内，不重复计。
- 除文件级 D 外，另有**文件内死代码段约 1,412 行**（vnext_reporter 内 444 行、orchestrator 内约 118 行、tools_L1 孤儿块约 340 行、tools_L3 孤儿约 150 行、prompts/context_loader.md 160 行、tools.py 内死键若干行），单列在第五节死物清单。
- B 档的 prompts/ 目录含死物 context_loader.md（160 行），该文件单独立 D。

**一句话总貌**：全仓 7.7 万行里，真正需要推倒重建的只有主编排器一个文件（9,954 行，占 13%）；需要动接口或清洗的六个组件共 1.44 万行；能整体删的是一条 4,114 行的旧报告链加约 1,400 行散落死物；其余约 4.8 万行（62%）原样保留。红队"按层分诊"的方向经逐组件实测后成立，且比粗表更收了一刀：报告器不需要重建，只需要拆。

---

## 二、裁决层 `src/agent_analysis/` 逐组件裁决卡

| 组件（文件） | 职责一句话 | 行数 | 健康/病灶证据（文件:行号） | 谁依赖它（实测 import） | 裁决 | 一句话理由 |
|---|---|---|---|---|---|---|
| orchestrator.py | 主编排器：21 阶段流水线 + 13 类 AI 站的组装、重试、校验、装配 | 9,954 | 病灶：单体占全仓 14%（红队第四节）；两个 B 类拦截闸 `_validate_investigation_limits_against_materials`（2864-2894）、终审数字逐字核对（7034-7046）；提示词四源拼装内联（8063-8129）；4 个零引用死方法（1478、4235、4245、5954-6043） | main.py:15/35；__init__.py:6 导出 | **C** | 职责真实（调度必须存在），但内部构造是架构级病灶本体，重写收益最大处就在这里 |
| contracts.py | pydantic 契约层：全部 AI 站输出的数据形状与跨字段校验 | 2,807 | 健康：字段约束群是形状校验正面典型（gate_census #25）；语义 validator 已按 2026-08-31 T69 降级为留痕（2469-2536 注释链） | orchestrator、packet_builder、inquiry_router、outcome_review、run_review、deep_research_canon、main.py、integrated_synthesis_report.py | **A** | 契约是数据形状不是编排逻辑，与编排器实现解耦，重建编排器不必动它 |
| vnext_reporter.py | 报告渲染器：run 目录 JSON → 单文件 HTML（brief/layers/cockpit/atlas/workbench 五模板） | 7,019 | 拆分实测：渲染排版约 6,300 行；判断/闸门混入约 250-300 行（投资者立场分类 `_classify_investor_stance` 643-658；PC-28 抗诉口径在 2605-2645 被复制实现第二份；三道闸门 `_validate_ref_digest` 2289 阻断、`_layer_forbidden_checks` 6386、`_generic_label_flags` 6414）；死代码 444 行（9 个零引用函数，见死物清单 #7） | console_run_all.py:14/26（生产链唯二调用方之一） | **B** | 报刊原则下它是排版工、主体健康；但判断逻辑、三道闸门、444 行死代码要从渲染器里拆出去，模板调度结构（`_main_sections` 2463-2505 显式字典）保留 |
| packet_builder.py | 分析包装配器：data_json → analysis_packet（分层事实卡、候选跨层关系） | 1,082 | 健康：纯代码装配；事件隔离边界明文（406-445，"event_ref only... not numeric proof" 在 443）；`allow_event_refs` 默认 False 的空管道设计（367、379-383） | main.py:17/37；orchestrator.py:71/128（取 `indicator_payload_unavailable_reason`） | **A** | 装配工，干的是代码该干的活；编排器重建后 packet 契约不变它就不变 |
| llm_engine.py | 调用引擎：多模型轮换、严格表单锁、system 纪律注入、审计落盘 | 931 | 健康：strict schema 剪枝（110-287）把"代码填"字段从发给模型的表单里物理剪掉，是卸载抄写负担的机关；导入时架构校验（917-931）。瑕疵：内嵌兜底纪律 5 条比文件版 6 条少一条"空数据纪律"（513-520 vs prompts/system_constraints.md:7） | orchestrator.py:66/123；`call_with_fallback` 经 main.py:884/921 传给出题官与 IA | **A** | 一台引擎服务全部 13 类调用，职责单一、方向正确；兜底少一条纪律是提示词归建时要补的小账 |
| context_spread.py | 离线审计工具：把每次 AI 调用实际收到的上下文逐字导出投影供复查 | 739 | 健康但闲置：src 内零调用方（grep 实测）；有 tests/test_context_spread.py；设计自述"校验从落盘产物独立回查"（1-33） | 无 src 调用方 | **A** | 它是"逐字查账"能力的离线工具，不进主链不占跑道，重建后照旧能用 |
| few_shot.py | 层站 few-shot 选例器：按本层实际 function_id 选最多 4 条范例 | 102 | 健康：示例块放提示词前部 6-19% 符合实证结论；防抄袭声明（97-100）；Q6 专项二裁决"机制设计合理" | orchestrator.py:64/121；读 prompt_examples.py 注册表 | **A** | 机制本身无病灶；提示词体系归建时随包搬迁、不改逻辑 |
| deep_research_canon.py | 指标法典（RESEARCH_CANON 的代码化）：指标身份、权限档、法典提示词生成 | 1,006 | 健康：法典六字段由 `_backfill_indicator_canon_fields` 强制装配（orchestrator.py:9203-9249）；999-1004 的逐字纪律有代码身份比对背书（gate_census #88 正面例） | orchestrator.py:63/120 | **A** | 法典内容是真资产；它是四源拼装的第一源，归建时只改接线不改内容 |
| inquiry_router.py | 问询路由器（纯代码）：把反馈问询路由成受控调查任务书，带禁读清单 | 179 | 健康：薄路由；禁读清单（24-31）含 `post_run_reflection_library.current_run`，是校准隔离的执法点之一；政策清单写死"调查报告不得回写 L1-L5 层卡"（116-119） | orchestrator.py:65/122 | **A** | 它是"问题进数据层"的现存路由机关，也是双向提问回路反向段的天然挂点（见第六节） |
| legacy_adapter.py | 新旧轨转换器：vNext artifacts → 旧 V9 格式 logic_vnext.json | 957 | 病灶（结构性）：主链每跑必执行（main.py:849-865），产物唯一读者是 core/reporter.py 的旧版 HTML 报告（main.py:928-930）；还养着死概念键 masters_perspective（902） | 仅 main.py:14/34（经 __init__.py:5 导出）；tests/test_vnext_legacy_adapter.py | **D**（条件删除） | 主链产物已纯 vNext，它服务的外部消费者只剩旧报告器一个；不是兜底，是活的双轨——删掉它只需老板拍板"旧版 HTML 报告停生成"一个产品决定 |
| outcome_review.py | 打分器：final_claim_ledger 每条 claim 的方向判定与 T+20/60/120 窗口兑现 | 542 | 健康：方向判定关键词法（221-239）自带坦白；每份产物内嵌 `no_backflow_rule` 禁令（365、523）；`_leakage_checks` 主动防泄露扫描（369-384） | orchestrator.py:73/130（仅回测 run 打分，1119-1128）；outcome_scoring_runner.py:44/48 | **A** | 校准闭环前半截的建成部分；闭环断在回流不在它（event_calibration_map 第 3 节） |
| outcome_scoring_runner.py | 离线批跑器：扫历史 run 给满 20 天成熟期的 claim 打分 | 429 | 健康：边界明文"不许碰 orchestrator、不许碰 run 内 outcome_review_report"（21-28） | 无 src 调用方（`__main__` 入口 405）；tests/test_outcome_scoring_runner.py | **A** | 离线批跑器，与主链零耦合，重建编排器不影响它 |
| run_review.py | run 复盘生成器：产出 learning_updates 与 next_run_checks | 1,081 | 健康（本体）：纯代码簿记。注意：其产物的下游全断——reflection 条目被打"本 run 禁用"烙印（orchestrator.py:1154-1156），这是校准闭环的断点，不是本文件的病 | orchestrator.py:72/129；产物仅 vnext_reporter 展示层读（2039、6230） | **A** | 簿记员本职无恙；它产出的学习点无人消费是老板明文否决的设计现状，不是删除理由 |
| prompt_inspector.py | 提示词审计页生成器：把 prompt_audit 落盘件做成可翻查的 HTML | 765 | 健康：console 链固定一环（console_run_all.py:206-208） | console_run_all.py:13/25 | **A** | 审计工具，"逐字查账"的展示面，重建后照旧可用 |
| persistent_checks_a.py | 常设检查 A 包：PC-01~PC-10（分料身份、引用对账、事件字段恒空等） | 944 | 健康：注册表 926-935；十条全是落盘产物间的身份/计数对账（gate_census #41-43）；只读 run_dir、单条异常不崩整包（939-943） | orchestrator.py:8429 动态 import；main.py:925 重跑 | **A** | 校验对象是 artifact 契约而非编排器实现——编排器重建后只要 artifact 文件名与 schema 不变，它们继续有效（详见第六节专条） |
| persistent_checks_b.py | 常设检查 B 包：PC-11~PC-26、PC-28、PC-29 | 1,356 | 健康：注册表 1323 起共 18 条；docstring 写明"PC-27 已退役，编号永不复用"（实测 28 项在跑，与红队修正一致）；PC-28 抗诉三条件（1191-1260）是"代码核验来源+模型判实质"分工样板 | orchestrator.py:8430 动态 import；main.py:925；PC-29 反向读 event_research/term_activation（1281） | **A** | 同上；其中 PC-06、PC-26 两条 C 类词表子条按 QE 程序单独复核，不牵连整包 |
| prompts/（19 个 md） | 提示词层：15 个站说明书 + system 六条纪律 + IA 两份 + 1 份死文件 | 2,829 | 健康与病灶混合：15 份经 orchestrator.py:149-165 的 PROMPT_FILES 登记；2 份 IA 经 integrated_synthesis_report.py:15-16 直读；system_constraints.md 经 llm_engine.py:502 加载；context_loader.md 零引用（死物 #1）；质量自查清单里的机械项（cross_layer_bridge.md:249、reviser.md:256、risk_sentinel.md:222 等）是注意力税（红队第一节反例 5） | 上述三个加载点 | **B** | md 文件的内容资产保留；要归建的是"四源拼装"编制——同一套纪律对代码写一遍、对模型写一遍（内联合约 8066-8124 与 l1_analyst.md 大面积重叠）必须收成单一来源 |
| report_styles/（5 个 css） | 报告样式资产 | 10,792 | 健康：被 vnext_reporter `_css`（6943）按 style 名加载 | vnext_reporter.py | **A** | 纯样式资产，与判断逻辑零纠缠 |
| __init__.py | 包导出面 | 82 | 导出 VNextOrchestrator、run_vnext_analysis、adapt_vnext_to_legacy 等（4-9） | main.py、console_run_all.py | **A** | 门面文件；注意它导出的 run_vnext_analysis 全仓无调用方（死物 #9） |

## 三、入口、第三层与 core/ 裁决卡

| 组件（文件） | 职责一句话 | 行数 | 健康/病灶证据 | 谁依赖它 | 裁决 | 一句话理由 |
|---|---|---|---|---|---|---|
| main.py | 流水线入口：采集→完整性→packet→编排器→legacy 导出→出题/巡逻→IA→常设检查重跑→旧报告渲染 | 1,022 | 健康主干（run_pipeline 667-993）；病灶两处：legacy 导出段（849-865）喂养 D 档旧报告链；925 行跨模块调 orchestrator 私有方法 `_run_persistent_checks()`，是接口泄漏 | console_run_all.py:22/34 | **B** | 编排顺序与接线真实有效；legacy 段随 D 裁决走、私有方法调用随新编排器转正为公开接口 |
| console_run_all.py | 产品入口：run_pipeline + PromptInspector + 原生 brief + 图表工作台 + sidecar 刷新 | 239 | 健康：断点续跑的 sha256 指纹核对（73-97）是防"假装复用"的硬纪律 | 无（它就是入口） | **A** | 薄编排壳，职责清晰 |
| integrated_synthesis_report.py | 第三层综合裁决（IA）：数据判决与外部世界对质的唯一桌子 | 1,637 | 健康：伪引用白名单"许可集合⊆实发集合"恒真（663-678，红队第四节正面）；时间一致性闸（1205-1267）；失败全走降级不炸链（288-318）；Q6 评为 13 类站里与文献对齐最好的一站。小病灶：question 原文转录留了半扇门（905-907，红队第一节反例 1） | main.py:28/48 | **A** | 红队认证的健康器官，重写它会误伤；半扇门小病灶随提示词归建顺手修 |
| core/collector.py | 数据采集器：LAYER_FUNCTIONS 五层注册表（147-203）是"系统测什么"的唯一真相 | 681 | 健康：回测跳过清单"宁缺勿错"（256-289，每个函数带 reason+anomaly）；手工数据 120 天只标注不阻断（97-126） | main.py:41（经 core/__init__） | **A** | 数据层的登记总台，纪律在线 |
| core/checker.py | DataIntegrity 数据完整性检查：发布闸门的第一道 | 524 | 健康：数据面机械检查，发布闸门合法主力（gate_census #59）；内依赖 evidence_families 与 recompute_belt | main.py:41 | **A** | 闸门该守的样子 |
| core/evidence_families.py | 证据家族表：同族证据加权重不当独立证据 | 208 | 健康：L5 全部 11 个函数共享一家族（44-193），防共线性作弊 | core/checker.py:24/26 | **A** | 一张表，职责单一 |
| core/reporter.py | 旧版 V9 HTML 报告器 | 558 | 病灶（结构性）：唯一输入是 legacy_adapter 的 logic_json（main.py:928-930）；还消费死概念键 masters_perspective（444-446） | main.py:41（经 core/__init__） | **D**（条件删除） | 与 legacy_adapter、chart_generator 同一根藤上的旧报告链；老板停旧报告即整链删除 |
| core/__init__.py | core 包导出面 | 12 | — | main.py | **A** | 门面文件 |

## 四、数据层工具与根目录杂项裁决卡

| 组件（文件） | 职责一句话 | 行数 | 健康/病灶证据 | 谁依赖它 | 裁决 | 一句话理由 |
|---|---|---|---|---|---|---|
| tools.py | 工具注册表：collector 只能经它取函数 | 115 | 病灶（卫生死角）：孤儿注册两枚（49、66 行）、legacy 别名一枚（55）、死概念键 masters_perspective=None（97）、乱码注释一行（102，双重编码残骸）；"Layer 1/2/3"注释分组与 collector 实际分层不一致（layers_map 头部已声明注释不作数） | core/collector.py；prompt_examples.py（启动校验钉它） | **B** | 注册表机制保留（它是采集器与启动校验的共同锚），但五个死注册项要清洗——且清洗顺序受制于 prompt_examples 启动闸门（见死物清单） |
| tools_L1.py | L1 宏观采集（FRED 利率主干） | 1,418 | 健康主干（FRED 官方日频，layers_map L1 节）；病灶：孤儿函数 get_qqq_net_liquidity_ratio（948）+ 文件尾部"已废弃孤儿指标"块四个函数 DXY/SOFR/WTI/Gold-WTI（1119-1414，约 296 行，文件自述"从未接入运行时，仅供考古"） | tools.py、tools_L2、tools_L4、chart_generator、chart_time_series_artifacts | **B** | 采集主体保留；约 340 行孤儿代码删掉 |
| tools_L2.py | L2 风险偏好采集（VIX/OAS/CFTC/FINRA/CNN） | 1,721 | 健康：弱来源限权镣铐齐全（layers_map L2 节；VIX 期限结构 not_bullish_evidence 镣铐在 575-580） | tools.py、analog_history_audit.py | **A** | 能测当下恐慌的器官，无死物 |
| tools_L3.py | L3 内部健康度采集（广度/集中度） | 1,999 | 健康：幸存者防线最严（19-259，拿不到历史宇宙就硬失败）；病灶：孤儿函数 get_m7_fundamentals（1857 起，约 140 行）+ legacy 别名 get_qqq_qqew_ratio（784-790） | tools.py、tools_L2、tools_L4、core/collector.py | **B** | 采集主体保留；约 150 行孤儿删除 |
| tools_L4.py | L4 估值盈利采集（资格体系最精密的一层） | 8,268 | 健康：字段级权限、第三方交叉校验、回测 fail-closed（972-973、4629-4645 等，layers_map L4 节）；体量大是数据源纪律的代价不是病灶 | tools.py、core/collector.py、analog_history_audit.py、browser_sidecar.py、news_event_ledger.py | **A** | 全仓资格纪律最严的器官；"规则最严、历史最穷"是数据现状不是代码病 |
| tools_L5.py | L5 价格趋势采集（单一 QQQ OHLCV 源） | 1,153 | 健康：确定性快照带 sha256 供重算带复算（131、235）；用途边界写明"only price truth"（249-250） | tools.py | **A** | 份内事最扎实 |
| tools_common.py | 采集共享基建（HTTP、缓存、FRED/yfinance 封装、M7 名单 292） | 1,868 | 健康 | 13 个文件（采集层全部 + 图表 + 台账 + outcome_review） | **A** | 地基 |
| chart_generator.py | 旧报告图表生成器 | 2,410 | 病灶（结构性）：唯一调用方是 core/reporter.py（实测 grep 唯一命中） | core/reporter.py | **D**（条件删除） | 旧报告链的第三环，随旧报告同进退；注意它也 import tools_L1，删它对采集层零影响 |
| chart_adapter_v6.py | 图表数据适配器 | 355 | 健康 | chart_time_series_artifacts.py、interactive_chart_workbench.py、chart_generator.py | **A** | 工作台图表链在用；chart_generator 删除后它的消费者仍有两个 |
| chart_time_series_artifacts.py | 图表时序产物装配 | 696 | 健康 | main.py、interactive_chart_workbench.py | **A** | 主链落盘件 |
| interactive_chart_workbench.py | 交互图表工作台 HTML 生成器 | 1,888 | 健康：console 链固定一环（console_run_all.py:213） | console_run_all.py:21/33 | **A** | 展示面 |
| data_availability.py | 数据可用性登记（哪些指标本轮可用/为何不可用） | 207 | 健康 | collector、checker、data_evidence、packet_builder、orchestrator | **A** | 缺口诚实的登记处 |
| data_cache.py | 本地缓存 | 263 | 健康 | tools_common.py | **A** | 基建 |
| data_evidence.py | 证据资格体系：七档来源分级 + 字段级权限 + 硬阻断规则 | 680 | 健康：SOURCE_TIER_AUTHORITY_MODEL（262-291）、WEAK_METRIC_AUTHORITY_POLICIES（147-216）、hard_block 四类（636-653） | tools_L1/L2/L4、collector、checker、packet_builder、orchestrator、main | **A** | "什么证据有资格说话"的法典执行层，是数据层的免疫系统 |
| data_manager.py | CSV 缓存与 asof 合并（backward 防前视 261-265） | 277 | 健康：7 天陈旧只警告仍返回旧数据（96-106）是明文纪律 | tools_common.py、chart_generator.py | **A** | 基建 |
| manual_data.py | 人工数据通道：Wind 人工抄数以 licensed_manual 身份进主链 | 454 | 健康：默认 `active: False`（29）；是回测估值缺口的唯一合法补给管（layers_map 缺口 8） | collector、packet_builder、research_console、control_service、console_run_all | **A** | 合法的例外开口，设计内 |
| news_event_ledger.py | 新闻事件采集（RSS）与事件卡落盘 | 1,455 | 健康：sidecar 隔离纪律硬编码（news_layer_analyzer.py:216-218 "never evidence_ref"）；读 event_research 词表（25/30） | main.py | **A** | 事件层新闻半边的采集器 |
| news_layer_analyzer.py | 新闻层分析器（sidecar） | 321 | 健康：隔离政策明文（216-218） | main.py | **A** | sidecar 本分 |
| news_event_data_linker.py | 新闻-数据关联器 | 351 | 健康 | main.py | **A** | sidecar 本分 |
| event_narrative_ledger.py | 事件主线聚类 + 跨层出题工厂（纯代码，不调 AI） | 1,729 | 健康：`_build_cross_layer_questions`（1088 起）产出 `direction="event_to_data"` 的问题——这是"事件层向数据层出题"的现存半成品（详见第六节） | main.py | **A** | 双向回路反向段的出题源头已经长在这里 |
| expectation_ledger.py | 预期-兑现台账 | 604 | 健康本体；注意：治理站消费已于 08-15 切断（orchestrator.py:5845-5848 喂空字典），配套摘要函数已成死代码（orchestrator.py:5954-6043） | main.py | **A** | 台账本体无恙；死的是 orchestrator 里的摘要函数，记在死物清单 |
| state_ledger.py | 状态台账 + 方法修正台账 | 318 | 健康：含全仓唯一"查 git 提交真伪"的闸门 `_validate_method_revision_entry`（236-303，红队第二节补登记）；状态台账禁进提示词（199-203） | orchestrator.py、main.py | **A** | 簿记与闸门都在正轨 |
| qqq_holdings.py | QQQ 持仓快照 | 269 | 健康 | tools_L4.py、vintage_archiver.py | **A** | 数据地基 |
| recompute_belt.py | 重算带：17 个 check_* 函数用原始序列确定性重算分位/比率并与管道比对 | 1,832 | 健康：gate_census #62 明列"代码自己重算、不要求 AI 自证"的正面典型 | core/checker.py | **A** | QE 第五问出口（c）的既有样板 |
| research_console.py | 研究控制台后端 | 1,361 | 健康 | control_service.py、open_research_console.py | **A** | 运营工具，不在主链 |
| open_research_console.py | 控制台打开脚本 | 158 | 健康 | 无（入口脚本）；有 tests | **A** | 运营入口 |
| control_service.py | 控制服务：命令白名单、环境变量覆盖、词表圈选入口 | 743 | 健康：白名单校验（135、164）；是老板圈词表的入口（import event_research.term_activation 22/37） | 无（服务入口）；有 tests | **A** | 运营服务，与主链重建无涉 |
| analog_history_audit.py | 历史类比序列离线审计 | 586 | 健康 | 无 src 调用方（`__main__` 入口）；有 tests | **A** | 离线审计工具 |
| browser_sidecar.py | 浏览器旁挂采集（Trendonify 等第三方校验源） | 288 | 健康：隔离纪律在采集侧声明（tools_L4.py:3773-3775 禁它偷渡进 L1-L5 载荷）；console 链的可信刷新分支（console_run_all.py:133-171） | console_run_all.py:15/27 | **A** | sidecar 本分 |
| vintage_archiver.py | PIT 快照归档器：L4 盈利修正档案的生产者 | 533 | 健康：它是 layers_map 缺口 1 里"档案 2026-07-12 起积累"的积累机关 | 无 src 调用方（离线维护工具）；有 tests | **A** | L4 回测证据的地基维护工 |
| api_config.py | API 密钥与端点配置 | 954 | 健康（红队补登记了 4 个簿记校验函数，全是 A 类） | tools_common、config、news_event_ledger、llm_engine、main | **A** | 基建 |
| config.py | 路径配置（path_config） | 383 | 健康 | 18 个文件 | **A** | 基建 |

**盘点范围外补充两行**（讲故事必需，不计入汇总统计）：

| 组件 | 职责 | 行数 | 证据 | 谁依赖它 | 裁决 | 理由 |
|---|---|---|---|---|---|---|
| prompt_examples.py | few-shot 范例注册表 + 启动架构校验（693-758） | 758 | 健康本体；但它把孤儿函数 get_qqq_net_liquidity_ratio（221-258）与 get_m7_fundamentals（525 起）的范例钉进注册表，启动校验要求范例键 ⊆ tools 注册表键——保鲜机制护住尸体（红队第四节反例 4） | llm_engine.py:923（导入时强制）、few_shot.py:23 | A（备注联动） | 注册表机制是好器官；删孤儿函数必须先删这里的范例再过启动闸，顺序写进死物清单 |
| reasoning_examples.py | 旧版推理过程范例库 | 189 | 病灶（死物）：src 内零 import（grep 实测）；仅 scripts/apply_lexicon_edits.py、static_jargon_scan.py 与 test_docs_consistency.py 摸到它；现行 few-shot 走 prompt_examples.py，与本文无关 | 无 src 调用方 | **D** | 旧 few-shot 体系的遗骸，无人读 |

## 五、死物清单（单独标记）

判定口径：没有任何运行时代码引用、但被测试/启动校验/导出面钉住而删不掉的产物，或文件内零引用函数。引用全部经 grep 与 AST 双重核实。

| # | 死物 | 位置 | 体量 | 被什么钉住 | 处置顺序 |
|---|---|---|---|---|---|
| 1 | prompts/context_loader.md（描述一个主链里不存在的"Context Loader AI 站"） | agent_analysis/prompts/context_loader.md 全文 | 160 行 | tests/test_governance_input.py:1089 的死条款反向扫描 | 先删测试条款，再删文件 |
| 2 | get_qqq_net_liquidity_ratio 孤儿函数 | 定义 tools_L1.py:948；注册 tools.py:49 | 约 90 行 | prompt_examples.py:221-258 范例 + llm_engine.py:919-931 启动校验（范例键须 ⊆ 注册表键，不过则 SystemExit） | 先删范例→再删注册项→最后删函数 |
| 3 | get_m7_fundamentals 孤儿函数 | 定义 tools_L3.py:1857 起；注册 tools.py:66 | 约 140 行 | prompt_examples.py:525 起范例 + 同上启动校验；collector.py:257 只在回测跳过清单提它（LAYER_FUNCTIONS 147-203 无它） | 同上三步走 |
| 4 | get_qqq_qqew_ratio legacy 别名 | tools_L3.py:784-790；注册 tools.py:55 | 约 10 行 | tools.py 注册项（55 行注释自述 legacy compatibility alias） | 删注册项+删函数 |
| 5 | masters_perspective 死概念键整条僵尸链 | tools.py:97（None 占位）→ legacy_adapter.py:902（填充）→ core/reporter.py:444-446（消费）→ prompt_examples.py:417（范例） | 散布 4 文件 | 整条链活在 legacy 轨道里 | 随 legacy 三联删除一并走 |
| 6 | tools_L1.py 尾部"已废弃孤儿指标"块（get_dxy_index / get_sofr_rate / get_wti_oil / get_gold_wti_ratio） | tools_L1.py:1119-1414 | 约 296 行 | 无钉住者，文件自述"从未接入运行时，仅供考古"（1120-1122 注释） | 直接删 |
| 7 | vnext_reporter.py 九个零引用函数 | _source_tier_label(560-587)、_summary_fragments(884-890)、_narrative_list(891-897)、_percentile_rank(907-913)、_data_quality_box(2343-2370)、_reader_exit_section(3154-3317)、_charts_section(3583-3595)、_indicator_micro_chart(3690-3706)、_memo_chartbook_section(3801-3973) | 合计 444 行 | 无钉住者；模板调度是显式字典（2463-2505），无字符串动态派发，零引用确凿 | 直接删 |
| 8 | orchestrator.py 四个零引用方法 | _build_initial_inquiry_router_output(1478-1484)、_claim_counter_refs(4235-4244)、_claim_falsifiers(4245-4255)、_pricing_expectation_ledger_summary(5954-6043) | 合计约 118 行 | 无钉住者；前两个被 _claim_specific_* 变体（4256、4307）取代，最后一个随 08-15 台账喂空（5845-5848）而失去读者 | 随编排器重建一并埋 |
| 9 | run_vnext_analysis 公共门面 | orchestrator.py:9940 起；__init__.py:6/50 导出 | — | __init__ 导出面，但全仓（src/scripts/tests）无调用方 | 重建编排器时决定要不要保留这个 API 门面 |
| 10 | reasoning_examples.py 旧范例库 | src/reasoning_examples.py 全文 | 189 行 | scripts 两个工具与 docs 一致性测试 | 先改 scripts 与测试引用，再删文件 |

**死物合计**：文件内死段约 1,412 行 + 文件级 189 行（reasoning_examples）≈ 1,600 行。注意 #2/#3 的删除顺序受制于启动闸门——这是"保鲜机制保护尸体"的实锤（红队第四节反例 4），动手前必须先拆 prompt_examples 里的范例钉。

## 六、四个专项的深拆结论

### 6.1 vnext_reporter.py（7,019 行）拆解：部分保留，不重建

- **渲染排版约 6,300 行**：模块级格式化工具函数（203-1868，约 1,665 行）+ VNextReportGenerator 类内 150 余个 section/visual 方法（1869-6963）+ 五套模板显式调度（323-330 的 TEMPLATE_ORDER：cockpit/brief/atlas/workbench/layers）。这部分是报刊原则下"代码只排版装配"的正面主体。
- **判断逻辑混入约 250-300 行**：投资者立场分类 `_classify_investor_stance`（643-658）是渲染器在替判决做二次分类；最硬的一处是 **PC-28 抗诉亮灯口径在报告器里被复制实现了第二份**（2605-2645，与 persistent_checks_b.py:1191-1260 同规则两份代码）——同一规则两处实现，正是"改一处忘一处"的结构条件。
- **闸门混入三道**：`_validate_ref_digest`（2289，raise 阻断）、`_layer_forbidden_checks`（6386）、`_generic_label_flags`（6414，gate_census #73 的 C 类词表探针）。渲染器里长闸门，意味着"报告生成"这个动作可能因校验而 raise——职责越界。
- **死代码 444 行**（死物清单 #7），其中 `_memo_chartbook_section`（3801-3973）服务的 memo 模板已不存在于 TEMPLATE_ORDER。
- **结论**：裁决 B。保留模板调度与全部视觉方法，拆出判断与闸门（抗诉口径归 PC-28 单源），删 444 行死物。它不需要重建——重建一份 7,000 行 HTML 渲染器是纯粹的浪费。

### 6.2 legacy_adapter.py 与双轨终局：不是兜底，是活的双轨

实测链路：main.py:849 调 `adapt_vnext_to_legacy` → 落盘 logic_vnext.json（862-865）→ main.py:928-930 把它喂给 core/reporter.py 的 ReportGenerator 生成旧版 HTML；console_run_all 默认**不**传 `--skip-legacy-report`（55 行参数定义、198 行接线），所以**每一次正式跑都会生成新旧两份报告**。legacy_adapter 的依赖方只有 main.py 这一处（grep 实测），但它的产物养活 core/reporter.py（558 行）+ chart_generator.py（2,410 行，唯一消费者就是 core/reporter）。三件套合计 3,925 行。终局建议：这不是"主链纯化后自然死亡"的兼容层——它每跑必执行。它成为删除候选只需要老板一个产品决定："旧版 HTML 报告停生成"。拍板后三件套同批删除，连带死物 #5 的 masters_perspective 僵尸链。

### 6.3 提示词体系：每个 AI 站的提示词实际由哪几个来源拼成

实测逐站来源表（全部经源码亲见，非抄地图）：

| 站 | system 消息 | 站提示词来源 | 组装点 |
|---|---|---|---|
| L1-L5 层分析师 ×5 | system_constraints.md（llm_engine.py:502 加载，513-520 内嵌五条兜底） | **四源**：法典 build_layer_canon_prompt（deep_research_canon.py）+ few-shot（few_shot.py:61-102 读 prompt_examples.py）+ 内联 v2 合约（orchestrator.py:8066-8124）+ md 文件（prompts/lX_analyst.md），拼装原话 `parts = [canon_prompt, few_shot, v2_contract, prompt_body]` 在 8126-8128 | orchestrator.py:8052-8130 |
| bridge | 同上 | **两源**：内联 bridge 合约（8133-8164）+ cross_layer_bridge.md | 8132-8164 |
| thesis | 同上 | **两源**：内联 thesis 合约（8167-8230，含 event_index 条件分支）+ thesis_builder.md | 8166-8230 |
| counter_thesis / critic / risk / reviser / final / 受控调查 / 事件卡 / 事件总结 | 同上 | **单源 md**（PROMPT_FILES 登记在 orchestrator.py:149-165；文件丢失时 INLINE_PROMPTS 一句话兜底 337-345）+ payload + 字段规格（_render_contract_field_spec 7788）+ Response Rules（_compose_prompt 7613-7648） | _run_stage 统一通道 |
| IA + IA 批评者（第三层） | 同上 | **单源 md**：integrated_adjudicator.py:15-16 直读两份 md；**无内嵌兜底**，文件丢失返回 `prompt_file_missing` 优雅降级（integrated_synthesis_report.py:320-322） | integrated_synthesis_report.py:288-458、487-555 |
| DSH 调研员（事件层） | persona.md + 本次议程（runner.py:66-74 拼装） | persona.md（住 event_research/，不住 prompts/） | runner.py:100-112、211-214 |
| 出题官 topic_composer | 无 system 概念 | **单源 md**：topic_composer.md（住 event_research/）+ JSON 输入块（topic_composer.py:215-225） | topic_composer.py:176-237 |

**归建结论**："提示词散落在约 20 个代码文件"的说法实测收敛为三个物理住所——①prompts/ 目录 19 份 md；②orchestrator.py 内联（层合约+bridge 合约+thesis 合约+INLINE_PROMPTS 兜底，约 200 行）；③event_research/ 两份 md（persona、topic_composer）。外加两处补丁：llm_engine.py 的 system 兜底与文件版不齐（5 vs 6 条），IA 无兜底（方向相反但自洽）。**统一归建的正确对象不是 md 文件内容，而是"四源拼装"这个编制本身**：内联合约与 md 大面积重叠（红队实测 8065-8128 vs l1_analyst.md），同一纪律对代码写一遍对模型写一遍，归建后要收成"每站一份单一来源说明书 + 代码只递材料"。

### 6.4 persistent_checks 28 项：整体保留，理由三条

1. **它们校验的是 artifact 契约，不是编排器实现。** 两包入口 `run_checks_a(run_dir)` / `run_checks_b(run_dir)`（persistent_checks_a.py:937-943、persistent_checks_b.py:1336-1356）只读 run 目录的落盘 JSON，与 orchestrator 内部函数零耦合。编排器重建后，只要 artifact 文件名与 schema 不变，28 项检查原样有效。
2. **质量分布健康。** 按 gate_census 与红队复核：28 项里 26 项是 A 类身份/形状对账；C 类只有 PC-06 词表子条（persistent_checks_a.py:724-726）与 PC-26 关键词子条（persistent_checks_b.py:1147-1181）两条，按 QE 程序单独复核即可，不牵连整包；PC-28 是"代码核验来源+模型判实质"的分工样板（persistent_checks_b.py:1191-1260）。PC-27 已退役、编号永不复用（注册表 docstring 实测）。
3. **唯一的接口病灶在调度侧不在检查侧。** orchestrator._run_persistent_checks（orchestrator.py:8421 起）是私有方法，main.py:925 跨模块直接调私有方法重跑——这是接口泄漏，新编排器应把"常设检查重跑"转正为公开接口或挪进 console_run_all。
- 另注一个实测发现：`persistent_checks_report.json` 目前在 src 内**没有任何代码读者**（grep 实测，vnext_reporter 的治理区与抗诉横幅都不读它）——它是纯人工审计向产物。这不是删除理由（留痕位的设计如此），但重建时值得给 28 项检查配一个代码读者或明示"仅供人读"。

### 6.5 event_research/ 接口核对与"双向提问回路"挂点

**对外接口实测**（不逐文件过堂，红队已判健康器官）：main.py:24-26/882-912 调 `sync_patrol.run_sync_gap_patrol`、`topic_composer.compose_topics`、`term_activation.collect_term_candidates`；control_service.py:22/37 调 term_activation（老板圈词表入口）；news_event_ledger.py:25/30 读词表 overrides；persistent_checks_b.py:1281 的 PC-29 查词表三账；IA 经文件接口 `research_shelf.json` 消费巡逻成果（integrated_synthesis_report.py:1580-1586）。**唯一不干净的接口**：card.py:23-26 反向 import `scripts/layer2_supplement_prototype/prototype_loop.py` 的校验器——src 依赖 scripts，且该校验器的三条 B 类词表子条（模糊词禁表等，gate_census #48-50）物理住在 src 外。归建时应把这个校验器内收进 src 并按 QE 五问复核三条词表子条。

**双向提问回路挂点结论**：

- **已有方向（数据层→事件层）**：出题官 topic_composer.py（读六站对抗残局出题，82-120 的输入面 + 176-237 的主流程）→ 缺口桥 gap_bridge.py（任务书转候选议程，47-94）→ 议程账本 agenda.py（charter/gap/boss 三来源，41）。链路完整在跑。
- **反向（事件层→数据层）的现存半成品**：event_narrative_ledger.py:1088 的 `_build_cross_layer_questions` 是纯代码出题工厂，产出的问题带 `direction="event_to_data"` 标记；但这些问题的消费者只有两个——IA 在同一次 run 里当场回答（integrated_synthesis_report.py 的 question_answers，带自动降级闸 707-768）和出题官当残局读（topic_composer.py:86）。**"事件层的题进入数据层的后续采集/分析议程"这一截不存在**——问题止步于裁决桌，没有变成数据层的家庭作业。
- **天然挂点（按现成程度排序）**：① **inquiry_router.py**（179 行纯代码路由器）：它已经是"把问题路由成数据层受控调查任务书"的机关（orchestrator.py:1568 装配问询、2359 起执行调查），反向题进数据层最短的物理通道；② **topic_composer.py 的对称位**：它已同时读 bridge 残局与 cross_layer_questions（83-88），加一个"反向出题官"对称函数即可；③ **agenda.py 的 source 枚举**：反向题可作为新 source 类型或新 gap_ref 前缀入账，复用只追加账本与去重机制；④ **main.py:874-898 的出题/巡逻接线段**：新回路被主链调用的现实位置，与现有"出题官挂了不许炸主链"的降级纪律同款。

## 七、与"重建三样、保留四样"粗表的差异对照

**前提声明**：`answers/Q8.md` 不存在，无官方粗表可对照。以下以红队"按层分诊"裁决（`redteam/wave1_critique.md` 第四节：重建=主链编排器单体化 + 提示词四源拼装；保留=事件层 + 第三层 IA）为基线，逐条说本清单的裁决与它的一致处与出入。

| 粗表立场 | 本清单裁决 | 出入与理由 |
|---|---|---|
| 重建：主链编排器单体 | 一致：orchestrator.py 判 C（9,954 行整文件重建） | 无出入；本清单补了 4 处死方法（约 118 行）作为重建时不必带走的行李 |
| 重建：提示词四源拼装 | **收窄**：重建对象是"拼装编制"（orchestrator/llm_engine 内约 200 行内联代码与四源接线），不是 prompts/ 19 份 md 的内容——md 判 B（内容保留、归建重排） | 粗表容易被误读成"提示词文件重写"；实测逐站来源表（6.3 节）证明病灶在编制不在文本 |
| 保留：事件层 | 一致：event_research/ 整体 A | 补一处接口异常：card.py 反向依赖 scripts/ 原型校验器，归建时内收（6.5 节） |
| 保留：第三层 IA | 一致：integrated_synthesis_report.py 判 A | 补一个小病灶：question 原文转录半扇门（905-907），随归建顺手修 |
| 粗表未表态：vnext_reporter.py | 本清单补判 **B**（7,019 行：渲染保留、判断与闸门拆出、444 行死代码删除） | 粗表二分法下它容易被误并进"主链重写"；实测它是健康排版工，重建即误伤（6.1 节） |
| 粗表未表态：legacy 双轨终局 | 本清单补判 **D**：legacy_adapter + core/reporter + chart_generator 三件套 3,925 行条件删除 | 实测它不是兜底而是每跑必执行的活双轨（6.2 节）；删除只需老板一个产品决定 |
| 粗表未表态：28 项常设检查 | 本清单补判 **A** 整体保留 | 依据是它只读 artifact 契约、与编排器实现解耦（6.4 节）——编排器重建不必带它陪葬 |
| 粗表未表态：死物 | 本清单单列死物清单 10 项约 1,600 行 | 含红队已发现的 context_loader.md 与两个孤儿函数，新发现 reasoning_examples.py 遗骸、vnext_reporter 444 行死段、orchestrator 4 个死方法、masters_perspective 僵尸链、tools_L1 尾部 296 行考古块 |

## 八、边界与未核实事项

1. 本清单的"零引用"判定基于 AST 引用扫描 + 全仓 grep 双重核实；对字符串动态派发已做专项排除（vnext_reporter 模板调度为显式字典，orchestrator 无 getattr 调用内部方法的形态）。残余风险：若有经配置文件字符串名间接调用的路径未被发现。验证方法：对死物清单逐项跑 `grep -rn "<函数名>" --include='*.py' --include='*.json' --include='*.yaml' src/ scripts/ tests/`。
2. vnext_reporter 的"判断逻辑约 250-300 行"是逐函数估算，未做行级精确切分。验证方法：按 6.1 节列出的函数清单逐段丈量。
3. B 类拦截闸（orchestrator.py:2864、7034-7046）的拆除属 QE 处置程序范围，本清单只登记不裁决拆除顺序；按 QE 纪律，拦截位机制须先降级留痕观察一个真实运行周期再删代码。
