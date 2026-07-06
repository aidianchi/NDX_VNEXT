# vNext 7月3日架构吸收前置审计报告

> **本报告已被 [2026-07-05_VNEXT_ARCHITECTURE_AUDIT_V2.md](./2026-07-05_VNEXT_ARCHITECTURE_AUDIT_V2.md) 取代。** V2 保留本报告全部 30 条审计项和证据引用，但按四层共识框架重新组织，补充了优先级排序、条目角色标注和跨层依赖。请使用 V2。

审计日期：2026-07-04

审计目标：只回答“现有系统真实做到哪里、两篇 7 月 3 日文档要求什么、差距是什么”。本报告不做系统改造，不改代码，不改测试，也不提前指定施工路线。

## 1. 领导摘要

现有 vNext 不是一个需要推倒重来的系统。它已经有一条固定主链：先做数据完整性检查，再让 L1-L5 五个分析层各自独立分析，之后由 Bridge 做跨层综合，再进入 SynthesisPacket、Thesis、Critic、Risk、Reviser、Final，最后由 Run Review 复盘。这条链路在代码里是固定的，不是让自由 Agent 临场决定研究什么。证据：`src/main.py:394`、`src/main.py:453`、`src/agent_analysis/orchestrator.py:206`、`src/agent_analysis/orchestrator.py:213`、`src/agent_analysis/orchestrator.py:333`。

7 月 3 日两篇文档不是否定现有架构，而是把验收标准抬高了。`2026-07-03_NDX_VNEXT_EPISTEMIC_ARCHITECTURE_REPORT.md` 主要要求系统能把“市场判断、风险边界、个人决策翻译”分开，所有重要结论都有证据、反证和失效条件，并且用三层架构保护事实、事件、综合判断之间的边界。证据：`docs/2026-07-03_NDX_VNEXT_EPISTEMIC_ARCHITECTURE_REPORT.md:46`、`:119`、`:172`、`:260`、`:422`、`:521`。`2026-07-03_harness讨论.md` 主要要求保留固定主链，同时在 Bridge 之后增加受控的 Gap Planner、AgentSpec、InvestigationReport 和二次综合，让动态调查只补缺口，不破坏 L1-L5 隔离。证据：`docs/2026-07-03_harness讨论.md:110`、`:204`、`:381`、`:457`、`:529`、`:580`。

最大的已实现优势是边界意识。L1-L5 运行时隔离已经是代码级设计：每层只拿本层数据、本层事实、本层上下文，事件材料默认不进入 AnalysisPacket。证据：`src/agent_analysis/orchestrator.py:463`、`:468`、`:1000`、`src/agent_analysis/packet_builder.py:287`、`tests/test_vnext_packet_builder.py:198`、`tests/test_vnext_orchestrator.py:452`。数据发布闸门也较强：DataIntegrity 会阻断严重数据问题，blocked/unpublishable 时主链不继续生成正式结论。证据：`src/main.py:394`、`:400`、`:453`、`src/core/checker.py:217`、`:351`。

最大的差距不是“有没有字段”，而是“字段背后的语义是否真的成立”。例如现有系统有 `principal_contradiction`、`price_reflection_map`、`falsifiers`、`permission_type` 等字段，但其中一部分可以由代码兜底补齐。字段存在不能自动证明主要矛盾分析、价格反映判断、指标发言权约束已经可靠完成。证据：`src/agent_analysis/orchestrator.py:2617`、`:2627`、`:2954`、`:2967`、`:3104`、`:3130`。

最明确的未实现项有四类。第一，统一 Evidence Passport 还没有覆盖数据、事件、报告结论和最终自然语言 claim；现在是数据侧有 `data_quality`，事件侧有 claim ledger，主链有 evidence index，但不是一个统一证据注册表。证据：`src/data_evidence.py:15`、`src/agent_analysis/orchestrator.py:595`、`src/event_narrative_ledger.py:440`。第二，竞争假说还没有成为强类型结构；现有 Critic 不是独立 Counter-Thesis，Thesis 也没有 2-4 个假说的支持、反证、诊断力和胜出理由结构。证据：`src/agent_analysis/contracts.py:817`、`:862`、`:918`、`src/agent_analysis/orchestrator.py:217`。第三，Bridge 后动态调查链路没有实现；没有 Gap Planner、AgentSpec、InvestigationReport、预算、停止条件和 Bridge V2 二次综合。证据：`src/agent_analysis/orchestrator.py:213`、`:214`、`:215`。第四，最终结论没有 claim-level ledger；事件侧有 `event_claim_ledger.json`，但 Final/Thesis 的每条自然语言结论没有统一的 `claim_id -> evidence_refs -> counter_evidence_refs -> inference_steps -> verified` 台账。证据：`src/event_narrative_ledger.py:1305`、`src/agent_analysis/contracts.py:1194`。

一句话结论：现有系统已经具备“固定主链 + 隔离 + 数据闸门 + 事件侧链 + 初步审计”的骨架；7 月 3 日两篇文档要求的是把它升级成“证据护照统一、竞争假说显式、动态调查受控、最终结论可逐条审计”的更高标准。本报告只确认差距，不给施工路线。

## 2. 审计方法

### 2.1 证据来源

本审计使用四类证据：

| 类型 | 使用方式 | 代表证据 |
| --- | --- | --- |
| 源码 | 只读检查主链、合同、报告生成、数据闸门、事件侧链、UI 入口 | `src/main.py`、`src/agent_analysis/orchestrator.py`、`src/agent_analysis/contracts.py`、`src/data_evidence.py`、`src/integrated_synthesis_report.py` |
| 测试 | 判断哪些边界已经被自动化保护 | `tests/test_vnext_packet_builder.py`、`tests/test_vnext_orchestrator.py`、`tests/test_three_layer_artifacts.py`、`tests/test_data_evidence_contract.py`、`tests/test_run_review.py` |
| 真实产物 | 检查代码是否真的落到 run artifact | `output/analysis/vnext/20260701_131914/run_summary.json`、`pure_data_report.json`、`integrated_synthesis_report.json`、`event_mechanism_report.json`、`data_integrity_report.json`、`run_review_report.json`、`synthesis_packet.json` |
| 7 月 3 日文档 | 提取目标验收标准，不把建议当作现状事实 | `docs/2026-07-03_NDX_VNEXT_EPISTEMIC_ARCHITECTURE_REPORT.md`、`docs/2026-07-03_harness讨论.md` |

### 2.2 审计边界

本报告覆盖：数据采集与 DataIntegrity、AnalysisPacket、L1-L5 隔离、Bridge、SynthesisPacket、Thesis/Critic/Risk/Reviser/Final、第二层事件材料、第三层综合报告、Run Review、Prompt Inspector、报告 UI、测试覆盖。

本报告不覆盖：实际改造方案、代码修改、测试修改、成本排期、人员分工、历史回测收益评估、投资结论正确性评估。

### 2.3 多 agent 分工

主审计负责框架、证据标准、整合、差距矩阵和对抗式审查。并行 explorer 只做只读窄任务：

| 分工 | 输出定位 | 主审计使用方式 |
| --- | --- | --- |
| 主链数据流审计 | DataIntegrity、AnalysisPacket、L1-L5、Bridge、SynthesisPacket、Run Review | 作为现有架构画像和差距矩阵证据，主审计重新整合 |
| 事件/三层/UI 审计 | 新闻事件侧链、Integrated Synthesis、报告 UI | 用于判断三层架构与阅读工作台成熟度 |
| 测试与发布闸门审计 | DataIntegrity、Schema Guard、Run Review、Prompt Inspector、测试覆盖 | 用于区分硬闸门、软检查和展示型审计 |
| 两篇文档清单化 | 把 7 月 3 日文档转成可检查标准 | 用作验收清单草案，主审计去重和归类 |

子 agent 输出只作为材料，不能直接成为最终结论。本报告中的判断以源码、测试、产物或文档证据为准。

### 2.4 判断等级

| 等级 | 含义 |
| --- | --- |
| 已做到 | 有明确源码路径、测试或真实产物支持，且实现语义基本符合目标 |
| 部分做到 | 有结构、字段或局部机制，但覆盖面、强度或一致性不足 |
| 语义不足 | 字段存在或报告能生成，但不能证明背后的推理质量已经可靠 |
| 未做到 | 未发现对应源码结构、产物或测试 |
| 方向正确但暂缓 | 目标合理，但现状尚未到实施判断阶段，需等待更基础差距解决 |
| 不建议做/需重审 | 文档建议与现有红线或项目目标可能冲突，不能直接吸收 |
| 待确认 | 证据不足，不能装作已经审计完成 |

## 3. 现有架构画像

### 3.1 当前真实数据流

当前主入口是 `main.run_pipeline`。系统先采集或读取 `data_json`，随后立即运行 DataIntegrity，写入 `data_integrity_report.json`。如果 DataIntegrity 判定 blocked/unpublishable，主流程会生成审计型报告摘要并抛错停止，不继续进入 vNext LLM 主链。证据：`src/main.py:394`、`:400`、`:453`。

DataIntegrity 的阻断条件包括成功率过低、关键层无成功指标、未来日期、估值源阻断冲突、数据证据合约 hard block 等。它输出 `blocked`、`unpublishable`、`publish_status`、`blocking_reasons`。证据：`src/core/checker.py:19`、`:217`、`:351`。

通过 DataIntegrity 后，`AnalysisPacketBuilder` 将指标按 L1-L5 分组，生成 `raw_data`、`facts_by_layer`、`candidate_cross_layer_links` 和可选 `event_refs`。默认情况下，即使存在事件账本，事件引用也不进入 AnalysisPacket；只有显式 `allow_event_refs=True` 时才保留。证据：`src/agent_analysis/packet_builder.py:287`、`:301`、`:307`、`tests/test_vnext_packet_builder.py:177`、`:198`。

Orchestrator 的固定链路是：`analysis_packet` -> `context_brief` -> L1-L5 layer cards -> Bridge -> `synthesis_packet` -> Thesis -> Critic/Risk -> Schema Guard -> Reviser -> Final -> Run Review -> Outcome Review -> post-run reflection。证据：`src/agent_analysis/orchestrator.py:206`、`:213`、`:217`、`:333`。

### 3.2 L1-L5 隔离

L1-L5 隔离不是文档口号，而是运行时 payload 约束。每层只拿本层 context brief、本层 facts、本层 raw data 和过滤后的本层 manual overrides；layer context brief 清空跨层信号。证据：`src/agent_analysis/orchestrator.py:463`、`:468`、`:1000`。

测试验证 L1 prompt 只含 L1 材料，事件引用默认不会进入 packet，更不会进入 `raw_data["L1"]`。证据：`tests/test_vnext_orchestrator.py:452`、`tests/test_vnext_packet_builder.py:198`、`:204`。

需要保留的细节是：Bridge/Thesis 合同允许在存在 `event_refs` 时把事件作为背景或催化剂使用，但不能替代正式 `evidence_refs`。当前主流程默认没有给 L1-L5 event refs。证据：`src/agent_analysis/orchestrator.py:1884`、`:1911`、`src/main.py:455`。

### 3.3 Bridge 与 SynthesisPacket

Bridge 是第一处读取所有 layer cards 的阶段。它输出 typed conflicts、resonance chains、transmission paths、principal contradiction、secondary contradictions、price reflection map、transformation signals 等。证据：`src/agent_analysis/orchestrator.py:508`、`src/agent_analysis/contracts.py:445`、`:466`、`:508`、`:529`、`:560`、`:599`、`:614`。

SynthesisPacket 是压缩层。它从 LayerCard 建 `evidence_index`，从 Bridge 汇总冲突、主要矛盾、价格反映、事件索引和 guidance，Thesis 之后主要读这个包而不是原始全部材料。证据：`src/agent_analysis/orchestrator.py:574`、`:595`、`:684`、`src/agent_analysis/contracts.py:702`。

但这里必须区分“结构存在”和“语义成立”。`principal_contradiction` 可以由代码按最高严重度冲突兜底生成，`dominant_side` 可能被填成 `unclear_until_thesis`；`price_reflection_map` 缺项时也会被自动补 `unclear`。这说明字段覆盖不等于模型已经完成高质量主要矛盾和价格反映分析。证据：`src/agent_analysis/orchestrator.py:2954`、`:2967`、`:3104`、`:3130`、`:3141`、`tests/test_vnext_orchestrator.py:1425`。

### 3.4 Thesis/Critic/Risk/Reviser/Final

主链已经有 Thesis、Critic、Risk、Reviser、Final 的固定阶段。Final 把内部质量闸门和读者结论分开，`quality_gate` 与 `reader_final` 是不同字段，Final prompt 也明确要求分离。证据：`src/agent_analysis/orchestrator.py:217`、`:219`、`:224`、`src/agent_analysis/contracts.py:1262`、`src/agent_analysis/prompts/final_adjudicator.md:5`。

当前 Critic 是对已有 Thesis 的审查，不是独立盲写的 Counter-Thesis。ThesisDraft 有主论点、支撑链、保留冲突、主要矛盾、价格反映，但没有强类型的 2-4 个竞争假说结构。证据：`src/agent_analysis/contracts.py:817`、`:862`、`:918`。

### 3.5 第二层事件材料

第二层不是简单新闻列表。`NewsEventLedgerBuilder` 的来源包括官方 RSS、SEC、Yahoo Finance RSS、Alpha Vantage、Reddit、Wind financial_docs。它写入 `news_event_ledger.json` 和 `event_source_raw.jsonl`，并声明自身不是 L1-L5 输入，`event_ref` 与 `evidence_ref` 分离。证据：`src/news_event_ledger.py:43`、`:500`、`:528`、`:550`、`:553`、`:593`。

事件叙事侧链会生成事件簇、claim 账本、研究包、市场验证、事件摘要、机制报告、跨层问题和 HTML。证据：`src/event_narrative_ledger.py:1291`、`:1300`、`:1316`、`:1319`。

事件材料有降级规则：社交传闻降为 `unverified_signal`，标题-only 和未读正文材料降级，市场窗口观察明确“不构成因果证明”。证据：`src/news_event_ledger.py:364`、`src/event_narrative_ledger.py:523`、`:620`、`src/news_event_data_linker.py:196`。

测试覆盖了有效日期过滤、原始 source record、Reddit 传闻降级、正文抓取、错误壳不当正文等。证据：`tests/test_news_event_ledger.py:58`、`:82`、`:109`、`:135`。

### 3.6 第三层综合报告

`IntegratedSynthesisReportBuilder` 已有不可回写、事件不能成为 L1-L5 evidence、DataIntegrity 发布闸门、claim 降级、反证/失效条件/未解释项。证据：`src/integrated_synthesis_report.py:91`、`:122`、`:140`、`:196`、`:276`。

测试确认 DataIntegrity blocked 时只能 `audit_only`，不可发布正式投资结论；事件 claim 没有数据确认时降级为 `plausible_hypothesis`。证据：`tests/test_three_layer_artifacts.py:444`、`:465`。

但第三层综合报告还不是完整裁决引擎。它没有独立 `competing_hypotheses` 字段，更接近用 `conflict_matrix`、`downgraded_claims`、`unresolved_tension` 来表达张力。证据：`src/integrated_synthesis_report.py:119`、`:251`。

### 3.7 Run Review、Prompt Inspector 与报告 UI

Run Review 会读取主链产物和 DataIntegrity，按 data、bridge、thesis、risk、final、expression 等归因，不改变当前结论。它能发现主链字段缺失、价格反映薄、赔率语言矛盾等问题，但不是逐句证据审计。证据：`src/agent_analysis/run_review.py:163`、`:186`、`:262`、`:301`、`:448`、`tests/test_run_review.py:10`。

Prompt Inspector 能生成独立 HTML，并扫描 prompt 边界，例如其他层 card、Bridge/Thesis/Final、news sidecar、browser sidecar 等输入污染风险。证据：`src/agent_analysis/prompt_inspector.py:85`、`:212`、`:287`、`src/console_run_all.py:142`、`:161`。

报告 UI 已有 `cockpit/brief/atlas/workbench` 模板、L1-L5 accordion、证据抽屉和审计索引，也能暴露第二/三层 artifact 链接。证据：`src/agent_analysis/vnext_reporter.py:50`、`:69`、`:1134`、`tests/test_vnext_reporter.py:638`、`src/control_service.py:400`、`:404`。但它还不是 7 月 3 日文档要求的“30 秒裁决、5 分钟简报、深度研究、审计重放”四层可折叠裁决工作台。证据：`docs/2026-07-03_NDX_VNEXT_EPISTEMIC_ARCHITECTURE_REPORT.md:422`、`:437`。

### 3.8 真实 run artifact 抽样

抽样目录：`output/analysis/vnext/20260701_131914`。

| 产物 | 观察 |
| --- | --- |
| `run_summary.json` | 链接 pure data、event mechanism、integrated synthesis、run review 等产物；final stance 是有保留的战术性判断；approval 为 `approved_with_reservations` |
| `pure_data_report.json` | `schema_version=pure_data_report_v1`，`publish_status=publishable`，声明 data-only，并禁止新闻、事件、浏览器 sidecar、event_refs 等输入 |
| `integrated_synthesis_report.json` | 声明 no-backflow 与 evidence rule；发布门为 `publishable_integrated_report`；但综合判断偏规则化，`price_reflection` 为 `unclear` |
| `event_mechanism_report.json` | headline 低置信，`cannot_be_used_as_primary_evidence=True`，主线包括 AI/semiconductor earnings、macro/rate/valuation pressure、market breadth 等 |
| `data_integrity_report.json` | `publishable`，blocking reasons 为空；data evidence contract summary 中 hard block 为 0，但有 degraded/audit_warn 项 |
| `synthesis_packet.json` | 包含 `principal_contradictions`、evidence refs 和 transformation signals |

该样本证明：产物链已经连通，边界声明已经进入真实 artifact；同时也暴露出第三层综合仍偏规则化、价格反映语义较弱等问题。证据：上述真实 artifact 文件与 `src/integrated_synthesis_report.py:196`、`src/agent_analysis/orchestrator.py:684` 的生成逻辑一致。

## 4. 7月3日目标验收清单

### 4.1 Epistemic Architecture 文档清单

| ID | 检查问题 | 为什么重要 | 通过标准 | 失败表现 | 相关现有证据 |
| --- | --- | --- | --- | --- | --- |
| EPI-01 | 系统是否先定义判断对象，而不是直接给结论？ | 判断对象不清，证据和结论会错位 | run 中明确对象、边界、时间、口径、方法 | 只写“NDX 看多/看空”，不说明对象口径 | 文档要求：`docs/2026-07-03_NDX_VNEXT_EPISTEMIC_ARCHITECTURE_REPORT.md:64`、`:79`；现有：`src/agent_analysis/contracts.py:105`、`src/agent_analysis/orchestrator.py:710` |
| EPI-02 | 每个重要市场结论是否包含对象、证据、反证、失效条件？ | 这是项目红线，也是可审计推理链的最低要求 | 重要判断都能追溯 evidence/counter/falsifier | 只有结论和语气，没有反证或失效边界 | 文档：`:24`、`:422`；现有：`src/agent_analysis/contracts.py:219`、`:702`、`src/integrated_synthesis_report.py:196` |
| EPI-03 | 是否区分市场判断、风险边界、个人决策翻译？ | 避免把研究结论误写成操作指令 | 三类输出分栏，权限不同 | 用估值/技术指标直接推出买卖动作 | 文档：`:46`；现有：`src/agent_analysis/contracts.py:1262`、`src/agent_analysis/prompts/final_adjudicator.md:5` |
| EPI-04 | 是否有统一 Evidence Passport？ | 证据没有护照，就无法知道材料能证明什么、不能证明什么 | 数据、事件、报告 claim 都进入统一证据注册表 | 数据证据、新闻证据、最终结论各说各话 | 文档：`:119`；现有：`src/data_evidence.py:15`、`src/agent_analysis/orchestrator.py:595`、`src/event_narrative_ledger.py:440` |
| EPI-05 | 是否区分证据权威等级？ | 防止代理指标、标题新闻、市场价格越权发言 | source tier、材料形态、可证明范围、不可证明范围明确 | 新闻标题、社交传闻、代理指标被当成事实 | 文档：`:147`；现有：`src/data_evidence.py:226`、`src/news_event_ledger.py:364`、`src/event_narrative_ledger.py:620` |
| EPI-06 | L1-L5 是否运行时隔离？ | 第一层主分析不能被新闻、Bridge 或 Thesis 反向污染 | 每层只读本层数据和本层上下文 | L1 prompt 中出现其他层结论或事件侧链 | 文档：`:190`；现有：`src/agent_analysis/orchestrator.py:463`、`:1000`、`tests/test_vnext_orchestrator.py:452` |
| EPI-07 | L1-L5 输出是否遵守指标发言权？ | 指标不能证明它不能证明的东西 | 指标有 permission、canonical question、misread guard、falsifier | 技术指标证明估值便宜，代理指标冒充官方事实 | 文档：`:190`、`:224`；现有：`src/agent_analysis/contracts.py:123`、`:219`、`src/agent_analysis/orchestrator.py:2617` |
| EPI-08 | 第二层事件材料是否结构化，而不是新闻堆砌？ | 事件只可解释、挑战、提出问题，不能替代数据证据 | 事件簇、claim、研究包、验证、降级规则齐全 | 新闻列表直接成为市场结论证据 | 文档：`:224`；现有：`src/event_narrative_ledger.py:1291`、`:1300`、`tests/test_three_layer_artifacts.py:374` |
| EPI-09 | 三层是否保持 two-track independence？ | 防止事件叙事反向污染 L1-L5 主分析 | 纯数据报告和综合报告分离，综合不回写 | integrated report 结论进入 L1-L5 evidence | 文档：`:260`；现有：`src/integrated_synthesis_report.py:91`、`:122`、`tests/test_three_layer_artifacts.py:533` |
| EPI-10 | 是否有受控追问消息类型？ | 允许补证据，但必须可控，不能让动态调查破坏边界 | 有 observation inquiry、event challenge、adjudication gap 等消息协议 | 未解决问题只停留在文本里，或随意启动自由 agent | 文档：`:260`、`:474`；现有：`src/agent_analysis/contracts.py:634`、`src/agent_analysis/run_review.py:495` |
| EPI-11 | 第二层材料是否禁止成为 L1-L5 主证据？ | 这是现有红线之一 | event_ref 与 evidence_ref 分离，默认不进入 AnalysisPacket | 新闻或浏览器材料进入 L1-L5 `evidence_ref` | 文档：`:260`；现有：`src/agent_analysis/packet_builder.py:287`、`src/news_event_ledger.py:553`、`tests/test_vnext_packet_builder.py:198` |
| EPI-12 | 是否有竞争假说机制？ | 高质量判断不是单一路径，而是多个解释互相竞争 | 2-4 个假说，有支持、反证、诊断力、胜出/保留理由 | 只有单一主线和一个 Critic 评论 | 文档：`:316`；现有：`src/agent_analysis/contracts.py:817`、`:862`、`:918` |
| EPI-13 | 是否支持非单调推理和版本化重判？ | 新证据可能推翻旧结论，旧结论不能被悄悄覆盖 | 新证据触发重判，保留旧版本和变化理由 | 只覆盖报告，无法说明为什么改判 | 文档：`:338`；现有：`src/agent_analysis/orchestrator.py:310`、`:348`、`:2254` |
| EPI-14 | 主要矛盾是否成为真实分析，而非口号？ | 主要矛盾决定哪些冲突支配当下结论 | 主导矛盾、次要矛盾、转化信号、价格反映都有实证支撑 | 字段存在但由兜底生成，dominant side 不清 | 文档：`:364`；现有：`src/agent_analysis/contracts.py:529`、`src/agent_analysis/orchestrator.py:3104` |
| EPI-15 | 报告 UI 是否支持四层阅读工作台？ | 领导需要先看结论，也能逐层展开审计 | 30 秒、5 分钟、深度研究、审计重放四层可折叠 | 只有长报告或散落 artifact 链接 | 文档：`:422`、`:437`；现有：`src/agent_analysis/vnext_reporter.py:50`、`:1134` |
| EPI-16 | 发布闸门是否覆盖数据、证据、反证和可发布性？ | blocked/unpublishable 不能伪装成正式结论 | DataIntegrity、证据护照、反证、失效条件共同守门 | 数据 blocked 仍发布投资结论，或语义缺陷不降级 | 文档：`:521`；现有：`src/core/checker.py:351`、`src/integrated_synthesis_report.py:140`、`tests/test_three_layer_artifacts.py:444` |

### 4.2 Harness 讨论文档清单

| ID | 检查问题 | 为什么重要 | 通过标准 | 失败表现 | 相关现有证据 |
| --- | --- | --- | --- | --- | --- |
| HAR-01 | 是否保留固定主链，而不是自由 agent 全权编排？ | 投研系统需要可复现、可审计 | L1-L5、Bridge、Thesis、Critic、Risk、Final 固定 | 每次 run 由 agent 临时决定流程 | 文档：`docs/2026-07-03_harness讨论.md:110`；现有：`src/agent_analysis/orchestrator.py:213`、`:224` |
| HAR-02 | L1-L5 是否不做动态化？ | 动态 L1-L5 会破坏上下文隔离 | 五层固定，只在层内分析 | 动态 agent 自由读取其他层和新闻 | 文档：`:580`；现有：`src/agent_analysis/orchestrator.py:463`、`tests/test_vnext_orchestrator.py:452` |
| HAR-03 | Bridge 是否承担跨层关系发现？ | Bridge 是固定主链的中枢 | 输出冲突、共振、传导、主要矛盾 | L1-L5 各说各话，没人综合 | 文档：`:261`；现有：`src/agent_analysis/contracts.py:560`、`:599`、`:614` |
| HAR-04 | Bridge 是否正确处理 price reflection？ | 价格反映不是价格涨跌说明一切 | 区分已反映、未反映、误反映、不确定 | 用走势直接证明基本面或估值结论 | 文档：`:261`、`:890`；现有：`src/agent_analysis/contracts.py:508`、`src/agent_analysis/orchestrator.py:2954` |
| HAR-05 | Bridge 后是否有 Gap Planner？ | Bridge 找到未解问题后，需要受控补证据 | Gap Planner 只针对关键缺口开调查任务 | 未解决问题停在文字里 | 文档：`:340`、`:381`；现有：`src/agent_analysis/orchestrator.py:213`、`:214` |
| HAR-06 | 动态 agent 是否只用于 Bridge 后补缺口？ | 防止动态 harness 污染主链 | 动态任务位置固定在 Bridge 后、Thesis 前或审计侧 | 动态 agent 进入 L1-L5 主分析 | 文档：`:434`、`:622`；现有未见对应调度 |
| HAR-07 | 是否有 AgentSpec？ | 动态 agent 必须被任务、上下文、禁区和预算约束 | 明确 question、allowed context、forbidden context、budget、stop | 只给自由问题，让 agent 自行搜集 | 文档：`:457`；现有未见强类型 AgentSpec |
| HAR-08 | 是否有 InvestigationReport？ | 补充调查结果必须可审计、可被 Bridge 二次读取 | 输出 finding、evidence、counter、confidence、limits | 调查输出散文，无法进入主链 | 文档：`:529`；现有未见强类型 InvestigationReport |
| HAR-09 | 是否有预算和停止条件？ | 控成本，也防止无限追问 | 每个调查有 token/time/source/stop conditions | 一直追问直到看似满意 | 文档：`:731`、`:869`；现有未见对应运行结构 |
| HAR-10 | 动态调查是否禁止回写 L1-L5？ | 保留主链清洁性 | 调查结果只能进 Bridge V2/Thesis，不回写 layer cards | 调查结果修改 L1-L5 产物 | 文档：`:204`、`:580`；现有事件侧有 no-backflow，但调查链未实现 |
| HAR-11 | 新闻/事件侧链是否保持隔离？ | 新闻可以解释和挑战，不能成为第一层证据 | 新闻账本、事件账本、综合报告独立 | 新闻直接进入 L1-L5 raw/evidence | 文档：`:622`；现有：`src/news_event_ledger.py:550`、`src/integrated_synthesis_report.py:122` |
| HAR-12 | 主链是否仍可一键跑通？ | 架构升级不能破坏可用性 | 当前固定链可完整落 artifact | 系统必须人工拼接阶段 | 文档：`:869`；现有：`src/main.py:455`、`:520`、`src/control_service.py:400` |
| HAR-13 | 是否有 Counter-Thesis Builder？ | 反方需要独立形成强论点，而非只评论正方 | 与 Thesis 相对独立，有自己的证据链和失效条件 | Critic 只在 Thesis 后挑错 | 文档：`:890`；现有：`src/agent_analysis/orchestrator.py:217`、`:219` |
| HAR-14 | 是否有最终 Claim Ledger？ | 领导看到的每句话都应可追问 | 重要最终 claim 有 evidence/counter/inference/verification 台账 | 只有段落结论，不能逐条审计 | 文档：`:890`；现有事件侧：`src/event_narrative_ledger.py:1305`；主链缺口：`src/agent_analysis/contracts.py:1194` |

## 5. 差距矩阵

状态说明：`已做到` 表示当前实现和目标基本一致；`部分做到` 表示已有结构但覆盖不足；`语义不足` 表示字段或报告存在但不能证明推理质量；`未做到` 表示未发现对应机制；`方向正确但暂缓` 表示不应现在立刻施工；`需重审` 表示可能与边界冲突。

| ID | 状态 | 证据 | 差距与风险 | 备注 |
| --- | --- | --- | --- | --- |
| EPI-01 | 部分做到 / 语义不足 | `src/agent_analysis/contracts.py:105`、`src/agent_analysis/orchestrator.py:710` | 有 ObjectCanon 和 objective firewall，但 `object_clear` 更像数据覆盖检查，不是完整对象护照；对象、口径、成分、方法、时间边界未统一成为 run gate | 不指定施工方案 |
| EPI-02 | 部分做到 | `src/agent_analysis/contracts.py:219`、`:702`、`src/integrated_synthesis_report.py:196` | 指标和综合报告有 evidence/counter/falsifier 字段，但最终自然语言 claim 没有逐条台账 | 层级不足在真实产物层和最终 claim 层 |
| EPI-03 | 部分做到 | `src/agent_analysis/contracts.py:1262`、`src/agent_analysis/prompts/final_adjudicator.md:5` | Final 区分质量闸门和读者结论，但市场判断、风险边界、个人行动翻译仍未形成统一 Portfolio Policy 边界 | 风险在表达层 |
| EPI-04 | 部分做到 | `src/data_evidence.py:15`、`src/agent_analysis/orchestrator.py:595`、`src/event_narrative_ledger.py:440` | 数据、事件、主链 evidence index 是三个局部系统，不是统一 Evidence Passport | schema 层不足 |
| EPI-05 | 部分做到 | `src/data_evidence.py:226`、`src/news_event_ledger.py:364`、`src/event_narrative_ledger.py:620` | 数据和事件侧有权威/降级规则，但没有贯穿所有 claim 的统一 authority model | 规则层不足 |
| EPI-06 | 已做到 | `src/agent_analysis/orchestrator.py:463`、`:1000`、`tests/test_vnext_orchestrator.py:452` | 默认主链隔离成立；仅需注意 legacy `allow_event_refs=True` 不能被误用 | 当前不建议改动主原则 |
| EPI-07 | 部分做到 / 语义不足 | `src/agent_analysis/contracts.py:123`、`:219`、`src/agent_analysis/orchestrator.py:2617` | 字段和 backfill 存在，但自动补齐不等于 LLM 真正理解指标权限 | prompt 层、真实产物层不足 |
| EPI-08 | 部分做到（偏强） | `src/event_narrative_ledger.py:1291`、`:1300`、`tests/test_three_layer_artifacts.py:374` | 事件侧结构化较强，但覆盖范围主要是新闻/事件，不等于所有二层材料类型都完成 | 覆盖层不足 |
| EPI-09 | 已做到 | `src/integrated_synthesis_report.py:91`、`:122`、`tests/test_three_layer_artifacts.py:533` | 默认主链和三层报告有 no-backflow 边界；需继续防止未来动态调查破坏边界 | 是未来约束，不是现有缺陷 |
| EPI-10 | 未做到 | `src/agent_analysis/contracts.py:634`、`src/agent_analysis/run_review.py:495` | 只有 unresolved questions 等文本结构，未见受控消息协议 | 不提前定义施工方式 |
| EPI-11 | 已做到 | `src/agent_analysis/packet_builder.py:287`、`src/news_event_ledger.py:553`、`tests/test_vnext_packet_builder.py:198` | 默认 event_ref 不进入 L1-L5 主证据；风险来自未来兼容开关或动态 harness 误用 | 当前边界清晰 |
| EPI-12 | 未做到 | `src/agent_analysis/contracts.py:817`、`:862`、`:918` | 没有强类型 competing hypotheses；Critic 不能替代竞争假说 | 语义层重大缺口 |
| EPI-13 | 部分做到 | `src/agent_analysis/orchestrator.py:310`、`:348`、`:2254` | 有 checkpoint、manifest、post-run reflection，但没有新证据触发重判和版本链协议 | 运行协议层不足 |
| EPI-14 | 部分做到 / 语义不足 | `src/agent_analysis/contracts.py:529`、`src/agent_analysis/orchestrator.py:2954`、`:3104` | 主要矛盾和价格反映字段较全，但可兜底生成，真实诊断力不稳定 | Bridge 语义层不足 |
| EPI-15 | 部分做到 | `src/agent_analysis/vnext_reporter.py:50`、`:1134`、`tests/test_vnext_reporter.py:638` | 已有 cockpit/brief/atlas/workbench 和证据抽屉，但不是四层裁决工作台 | UI 信息架构不足 |
| EPI-16 | 部分做到 | `src/core/checker.py:351`、`src/integrated_synthesis_report.py:140`、`tests/test_three_layer_artifacts.py:444` | 数据发布闸门强；语义发布闸门较弱，竞争假说、claim ledger、证据护照不完整 | hard gate 与 semantic gate 不均衡 |
| HAR-01 | 已做到 | `src/agent_analysis/orchestrator.py:213`、`:224` | 固定主链已存在 | 不应推倒 |
| HAR-02 | 已做到 | `src/agent_analysis/orchestrator.py:463`、`tests/test_vnext_orchestrator.py:452` | L1-L5 不应动态化，当前符合 | 未来也应保持 |
| HAR-03 | 已做到 / 部分做到 | `src/agent_analysis/contracts.py:560`、`:599`、`:614` | Bridge 结构已覆盖跨层关系；语义质量仍受兜底字段影响 | 结构层已强，语义层待加强 |
| HAR-04 | 语义不足 | `src/agent_analysis/contracts.py:508`、`src/agent_analysis/orchestrator.py:2954`、`:2967` | price reflection 五类可被补 `unclear`，不能保证真实完成价格反映诊断 | 真实产物层不足 |
| HAR-05 | 未做到 | `src/agent_analysis/orchestrator.py:213`、`:214`、`:215` | Bridge 后没有 Gap Planner | 不提前指定实现 |
| HAR-06 | 未做到 / 方向正确但暂缓 | `docs/2026-07-03_harness讨论.md:434`、`:622` | 动态 agent 适用位置是文档建议，现有主链未实现 | 应等差距矩阵被确认后再讨论 |
| HAR-07 | 未做到 | `docs/2026-07-03_harness讨论.md:457` | 未见强类型 AgentSpec | 不把概念先写成工程任务 |
| HAR-08 | 未做到 | `docs/2026-07-03_harness讨论.md:529` | 未见强类型 InvestigationReport | 同上 |
| HAR-09 | 未做到 | `docs/2026-07-03_harness讨论.md:731`、`:869` | 动态调查预算和停止条件未实现 | 因调查链未实现而自然缺失 |
| HAR-10 | 未做到（调查链缺失）/ 原则已在事件侧做到 | `src/integrated_synthesis_report.py:91`、`:122` | 事件侧 no-backflow 成立；动态调查 no-backflow 尚无对象可验收 | 不能把事件侧等同调查侧 |
| HAR-11 | 已做到 / 部分做到 | `src/news_event_ledger.py:550`、`src/integrated_synthesis_report.py:122`、`tests/test_three_layer_artifacts.py:533` | 新闻/事件侧链隔离较好；未来新增材料类型仍需同等边界 | 当前实现偏强 |
| HAR-12 | 已做到 | `src/main.py:455`、`:520`、`src/control_service.py:400` | 当前主链和 artifact 入口可跑通；未来动态 harness 不得破坏这一点 | 当前不构成差距 |
| HAR-13 | 未做到 | `src/agent_analysis/orchestrator.py:217`、`:219` | Critic 不是独立 Counter-Thesis Builder | 语义层缺口 |
| HAR-14 | 未做到 | `src/event_narrative_ledger.py:1305`、`src/agent_analysis/contracts.py:1194` | 事件侧有 claim ledger，最终主链没有 claim-level ledger | 最终审计层缺口 |

## 6. 关键发现

1. 现有骨架方向与两篇文档基本一致，不是冲突关系。固定主链、L1-L5 隔离、Bridge 综合、事件侧链、纯数据报告/综合报告分离，已经接近 7 月 3 日文档里的底层原则。证据：`src/agent_analysis/orchestrator.py:213`、`src/agent_analysis/orchestrator.py:463`、`src/integrated_synthesis_report.py:91`、`docs/2026-07-03_harness讨论.md:110`、`:580`。

2. 数据发布闸门强于语义发布闸门。DataIntegrity 能硬阻断 blocked/unpublishable；但主要矛盾、价格反映、竞争假说、最终 claim 级证据链等语义质量更多依赖字段、prompt、自检和人工阅读。证据：`src/core/checker.py:351`、`src/main.py:453`、`src/agent_analysis/orchestrator.py:2954`、`:3104`、`src/agent_analysis/run_review.py:448`。

3. Evidence Passport 是当前最核心的横向缺口。数据侧、事件侧、主链 evidence index 都有局部证据结构，但没有统一到“每个材料能证明什么、不能证明什么、支持哪些 claim、反驳哪些 claim、诊断作用是什么”的证据护照。证据：`docs/2026-07-03_NDX_VNEXT_EPISTEMIC_ARCHITECTURE_REPORT.md:119`、`src/data_evidence.py:15`、`src/agent_analysis/orchestrator.py:595`、`src/event_narrative_ledger.py:440`。

4. Bridge 已经有“主要矛盾”的工程骨架，但语义可靠性不能只看字段。现有字段丰富，Run Review 也能检查薄弱项；但是兜底生成和自动补 `unclear` 说明它还不能被等同为稳定的辩证裁决。证据：`src/agent_analysis/contracts.py:529`、`src/agent_analysis/orchestrator.py:2954`、`:3104`、`tests/test_vnext_orchestrator.py:1425`。

5. 第二层事件材料比预想成熟。它已经有事件簇、claim ledger、研究包、市场验证、机制报告、跨层问题和降级规则；但它的成熟不等于能回写 L1-L5，也不等于最终综合已经有完整竞争假说。证据：`src/event_narrative_ledger.py:1291`、`:1300`、`:1316`、`src/integrated_synthesis_report.py:122`。

6. 第三层综合报告当前更像“边界守门 + 解释整合”，还不是“完整裁决法庭”。它可以表达冲突、降级、反证、失效条件，但没有强类型竞争假说，也没有最终 claim ledger。证据：`src/integrated_synthesis_report.py:119`、`:196`、`:251`、`:276`。

7. Harness 文档中最关键的新东西尚未实现：Bridge 后 Gap Planner、AgentSpec、InvestigationReport、预算、停止条件、Bridge V2。这个缺口明确存在，但本报告不把它直接转成施工路线。证据：`docs/2026-07-03_harness讨论.md:381`、`:457`、`:529`、`:731`、`src/agent_analysis/orchestrator.py:213`。

8. 报告 UI 已有分层阅读雏形，但不是 7 月 3 日要求的四层裁决工作台。现有 cockpit/brief/atlas/workbench、accordion、证据抽屉、artifact 链接提供了基础；真正的“30 秒裁决、5 分钟简报、深度研究、审计重放”仍未完成。证据：`src/agent_analysis/vnext_reporter.py:50`、`:1134`、`docs/2026-07-03_NDX_VNEXT_EPISTEMIC_ARCHITECTURE_REPORT.md:422`。

## 7. 对抗式审查

### 攻击 1：这份报告是否被 7 月 3 日新文档带偏，低估了现有系统？

回应：有这个风险，所以本报告把现有主链、L1-L5 隔离、DataIntegrity、事件侧链、Run Review 都作为独立画像写清楚，并在差距矩阵中把 HAR-01、HAR-02、EPI-06、EPI-09、EPI-11 判为已做到或偏强。证据来自 `src/agent_analysis/orchestrator.py:213`、`:463`、`src/main.py:453`、`src/integrated_synthesis_report.py:91`。

### 攻击 2：是否把字段存在误判成架构成熟？

回应：没有。本报告多次把 `principal_contradiction`、`price_reflection_map`、`permission_type` 等判为“结构存在但语义不足”。兜底生成和 backfill 证据来自 `src/agent_analysis/orchestrator.py:2617`、`:2954`、`:3104`。

### 攻击 3：是否把哲学词硬翻译成工程任务？

回应：报告刻意把“主要矛盾”“非单调推理”“竞争假说”转成可检查问题，而不是直接要求工程实现某个抽象概念。例如 EPI-14 检查的是主导矛盾、次要矛盾、转化信号、价格反映是否有证据支撑；EPI-13 检查的是版本化重判协议。证据来自文档要求 `docs/2026-07-03_NDX_VNEXT_EPISTEMIC_ARCHITECTURE_REPORT.md:338`、`:364` 与现有实现 `src/agent_analysis/orchestrator.py:2254`。

### 攻击 4：是否混淆了数据证据和新闻事件材料？

回应：没有。报告明确认定事件侧链隔离较强，新闻/事件不能成为 L1-L5 主证据，且 integrated report 声明 no-backflow。证据：`src/news_event_ledger.py:550`、`:553`、`src/integrated_synthesis_report.py:122`、`tests/test_vnext_packet_builder.py:198`。同时报告也指出事件侧成熟不等于最终综合成熟。

### 攻击 5：是否因为没有统一 Evidence Passport，就忽略了现有 data_evidence 的价值？

回应：没有。EPI-04 被判为“部分做到”，不是“未做到”。现有 `data_quality` 覆盖 provider、source、source_tier、as_of、effective_date、coverage、formula、anomalies 等，并被 DataIntegrity 检查。证据：`src/data_evidence.py:15`、`:226`、`:330`、`tests/test_data_evidence_contract.py:63`。差距只是它还没有统一覆盖事件材料和最终 claim。

### 攻击 6：是否提前决定一定要做动态 Harness？

回应：没有。HAR-06 被标成“未做到 / 方向正确但暂缓”。报告只确认现有缺口，不判断它是否是下一步最优施工项。动态 harness 还有污染、成本、漂移、假精确、压缩损失风险，文档本身也提醒这些风险。证据：`docs/2026-07-03_harness讨论.md:731`。

### 攻击 7：是否忽略了动态 Harness 可能破坏上下文隔离？

回应：没有。报告把 HAR-10 单独列为未来验收项：动态调查即使实现，也不能回写 L1-L5。当前事件侧 no-backflow 不能自动证明未来动态调查 no-backflow。证据：`src/integrated_synthesis_report.py:91`、`:122`、`docs/2026-07-03_harness讨论.md:204`、`:580`。

### 攻击 8：是否把报告 UI 差距夸大了？

回应：报告没有说 UI 不可用，只说“不等于四层裁决工作台”。现有 UI 有 cockpit/brief/atlas/workbench、accordion、证据抽屉和 artifact 链接；但目标文档要求的是 30 秒、5 分钟、深度研究、审计重放的固定阅读结构。证据：`src/agent_analysis/vnext_reporter.py:50`、`:1134`、`docs/2026-07-03_NDX_VNEXT_EPISTEMIC_ARCHITECTURE_REPORT.md:422`。

### 攻击 9：测试已经很多，为什么还说语义闸门弱？

回应：测试覆盖数据合约、隔离、事件降级、三层报告、Run Review、reporter 等关键边界；但测试多不等于每个重要自然语言 claim 都被逐条证据审计。Schema Guard 检查 evidence_refs、传导路径、复合指标越权等，但没有验证每句结论的 claim-level 推理链。证据：`src/agent_analysis/orchestrator.py:1492`、`:1612`、`:1622`、`tests/test_run_review.py:10`。

### 攻击 10：真实产物样本是否足够代表现状？

回应：不完全足够。本报告使用 `output/analysis/vnext/20260701_131914` 作为真实产物抽样，用来验证产物链存在和某些语义弱点；但它不能代表所有 run 的质量。因此凡依赖单个样本的判断只作为佐证，不作为唯一结论。该点保留为剩余风险。

### 攻击 11：是否应该直接给出第二、三、四步施工路线？

回应：不应该。用户明确要求本任务是审计和路线判断前置工作，差距矩阵不能直接跳到施工方案。本报告遵守这一点，只给状态、证据、风险和备注。后续路线必须从已确认的差距矩阵里长出来。

### 攻击 12：是否存在证据不足却写得太肯定的地方？

回应：最需要降级的是“真实产物层成熟度”。当前抽样 run 能证明 artifacts 连通和边界声明存在，但不能证明所有真实 run 都稳定产生高质量主要矛盾、价格反映和综合裁决。因此本报告把这些项归为“部分做到 / 语义不足”，而不是“已做到”。

## 8. 附录：源码/产物/测试索引

### 8.1 7 月 3 日目标文档

| 文件 | 用途 |
| --- | --- |
| `docs/2026-07-03_NDX_VNEXT_EPISTEMIC_ARCHITECTURE_REPORT.md:24` | 系统需要回答的核心问题 |
| `docs/2026-07-03_NDX_VNEXT_EPISTEMIC_ARCHITECTURE_REPORT.md:46` | 市场判断、风险边界、个人决策翻译 |
| `docs/2026-07-03_NDX_VNEXT_EPISTEMIC_ARCHITECTURE_REPORT.md:119` | Evidence Passport |
| `docs/2026-07-03_NDX_VNEXT_EPISTEMIC_ARCHITECTURE_REPORT.md:190` | L1-L5 输出与禁区 |
| `docs/2026-07-03_NDX_VNEXT_EPISTEMIC_ARCHITECTURE_REPORT.md:260` | two-track independence 与不可回写 |
| `docs/2026-07-03_NDX_VNEXT_EPISTEMIC_ARCHITECTURE_REPORT.md:316` | 竞争假说 |
| `docs/2026-07-03_NDX_VNEXT_EPISTEMIC_ARCHITECTURE_REPORT.md:364` | 主要矛盾 |
| `docs/2026-07-03_NDX_VNEXT_EPISTEMIC_ARCHITECTURE_REPORT.md:422` | 四层阅读工作台 |
| `docs/2026-07-03_NDX_VNEXT_EPISTEMIC_ARCHITECTURE_REPORT.md:521` | 发布闸门 |
| `docs/2026-07-03_harness讨论.md:110` | 当前固定主流程 |
| `docs/2026-07-03_harness讨论.md:204` | 上下文隔离 |
| `docs/2026-07-03_harness讨论.md:261` | Bridge 角色 |
| `docs/2026-07-03_harness讨论.md:381` | Gap Planner / Investigation flow |
| `docs/2026-07-03_harness讨论.md:457` | AgentSpec |
| `docs/2026-07-03_harness讨论.md:529` | InvestigationReport |
| `docs/2026-07-03_harness讨论.md:731` | 动态 harness 风险 |
| `docs/2026-07-03_harness讨论.md:890` | Counter-Thesis 与 Claim Ledger |

### 8.2 主链与合同

| 文件 | 用途 |
| --- | --- |
| `src/main.py:394`、`:400`、`:453` | DataIntegrity 先于主链；blocked 时停止 |
| `src/main.py:455`、`:520` | AnalysisPacket 与后续 artifacts 生成 |
| `src/agent_analysis/packet_builder.py:287`、`:301`、`:307` | AnalysisPacket 默认不保留 event refs |
| `src/agent_analysis/orchestrator.py:206`、`:213`、`:217`、`:333` | 固定 Orchestrator 主链 |
| `src/agent_analysis/orchestrator.py:463`、`:468`、`:1000` | L1-L5 隔离 payload |
| `src/agent_analysis/orchestrator.py:508` | Bridge 读取 layer cards |
| `src/agent_analysis/orchestrator.py:574`、`:595`、`:684` | SynthesisPacket 构建 |
| `src/agent_analysis/orchestrator.py:2617`、`:2627` | 指标权限字段 backfill |
| `src/agent_analysis/orchestrator.py:2954`、`:2967` | price_reflection_map 兜底 |
| `src/agent_analysis/orchestrator.py:3104`、`:3130`、`:3141` | principal_contradiction 兜底 |
| `src/agent_analysis/contracts.py:105` | ObjectCanon |
| `src/agent_analysis/contracts.py:123` | IndicatorCanon |
| `src/agent_analysis/contracts.py:219` | IndicatorAnalysis |
| `src/agent_analysis/contracts.py:445`、`:466`、`:508`、`:529`、`:560` | Bridge 相关合同 |
| `src/agent_analysis/contracts.py:702` | SynthesisPacket |
| `src/agent_analysis/contracts.py:817`、`:862`、`:918` | ThesisDraft 缺少竞争假说结构 |
| `src/agent_analysis/contracts.py:1262` | Final quality gate 与 reader final |

### 8.3 数据完整性与证据合约

| 文件 | 用途 |
| --- | --- |
| `src/core/checker.py:19`、`:217`、`:351` | DataIntegrity 闸门 |
| `src/data_evidence.py:15` | data evidence contract |
| `src/data_evidence.py:226`、`:330` | data_quality 规范化与 hard block 检查 |
| `tests/test_data_evidence_contract.py:63` | data evidence contract 测试 |
| `tests/test_core_checker.py:36`、`:260` | DataIntegrity 测试 |

### 8.4 第二层事件材料与第三层综合

| 文件 | 用途 |
| --- | --- |
| `src/news_event_ledger.py:43`、`:500`、`:528` | 新闻/事件来源 |
| `src/news_event_ledger.py:550`、`:553`、`:593` | 事件账本不作为 L1-L5 输入 |
| `src/news_event_ledger.py:364` | 社交传闻降级 |
| `src/event_narrative_ledger.py:523`、`:620` | title-only/市场窗口观察降级 |
| `src/event_narrative_ledger.py:1291`、`:1300`、`:1316`、`:1319` | 事件侧链产物 |
| `src/news_event_data_linker.py:196` | 事件与市场观察不能构成因果证明 |
| `src/integrated_synthesis_report.py:91`、`:122` | no-backflow 与 evidence rule |
| `src/integrated_synthesis_report.py:140` | integrated report 发布闸门 |
| `src/integrated_synthesis_report.py:196`、`:251`、`:276` | 综合判断、冲突矩阵、claim 降级 |
| `tests/test_three_layer_artifacts.py:444`、`:465`、`:533` | 三层产物边界测试 |

### 8.5 Run Review、Prompt Inspector、UI

| 文件 | 用途 |
| --- | --- |
| `src/agent_analysis/run_review.py:163`、`:186` | Run Review 入口 |
| `src/agent_analysis/run_review.py:262`、`:301`、`:448` | 主链薄弱项检查 |
| `tests/test_run_review.py:10`、`:139`、`:183` | Run Review 测试 |
| `src/agent_analysis/prompt_inspector.py:85`、`:212`、`:287` | Prompt Inspector HTML 与边界扫描 |
| `src/console_run_all.py:142`、`:161` | Prompt Inspector 生成入口 |
| `src/agent_analysis/vnext_reporter.py:50`、`:69`、`:1134` | 报告模板、accordion、证据抽屉 |
| `tests/test_vnext_reporter.py:638` | Reporter 测试 |
| `src/control_service.py:400`、`:404` | 控制台 artifact 链接 |

### 8.6 真实 run artifact

| 文件 | 审计用途 |
| --- | --- |
| `output/analysis/vnext/20260701_131914/run_summary.json` | 验证完整产物链和最终 stance |
| `output/analysis/vnext/20260701_131914/pure_data_report.json` | 验证 data-only 和 forbidden inputs 声明 |
| `output/analysis/vnext/20260701_131914/integrated_synthesis_report.json` | 验证 no-backflow、publish gate 和综合判断弱点 |
| `output/analysis/vnext/20260701_131914/event_mechanism_report.json` | 验证事件侧链输出和 primary evidence 禁令 |
| `output/analysis/vnext/20260701_131914/data_integrity_report.json` | 验证 DataIntegrity 产物 |
| `output/analysis/vnext/20260701_131914/run_review_report.json` | 验证复盘产物存在 |
| `output/analysis/vnext/20260701_131914/synthesis_packet.json` | 验证 principal contradictions、evidence refs、transformation signals |

## 9. 本报告的剩余风险

1. 真实产物只抽样了一个较新的 run，足以证明产物链存在，但不足以证明所有 run 质量稳定。
2. 本报告没有运行全量测试；测试证据来自源码审计和已有测试文件，不代表当前工作区所有测试都通过。
3. 7 月 3 日两篇文档本身是原则性建议，不是已定产品需求；本报告把它们转成验收项，但没有决定优先级和施工顺序。
4. `.understand-anything` 图谱如果存在，只能作为参考；本报告没有把旧图谱当作完整架构事实。
