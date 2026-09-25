# 编排层源码取证地图（第四、五层：架构分工与 AI 上下文工程）

这份文件回答研究战役第四层（Q5 三层架构、Q-C 代码与 AI 的分工边界、Q-D 数据层与事件层的对质）和第五层（Q6 每个 agent 的必要充分上下文）的取证问题。全部论断来自当前源码，每条给出 `文件:行号`。

## 0. 怎么读这份文件

- 本系统一次完整运行（下称"一跑"）的入口是 `src/main.py` 的 `run_pipeline()`（src/main.py:667-993）。它先采集数据，再跑主编排器，再跑第三层综合裁决，最后渲染报告。
- "站"（stage）是流水线上的一次独立处理步骤。一个站要么由纯代码执行，要么调用一次 AI。所有 AI 站共用同一台调用引擎。
- "契约"（contract）是 `src/agent_analysis/contracts.py` 里用 pydantic（一个 Python 数据校验库）定义的数据形状。AI 的输出必须长得跟契约一模一样，否则这站不算完成。
- "闸门"（gate）是代码里的校验点。闸门失败的处理方式只有两种：带着错误原因让 AI 重写一次，或者降级（产物照样落盘，但打上"不可发布"或"降级"标记）。
- 文中所有"行号"指 2026-09-15 工作区快照的行号；核心文件是 `src/agent_analysis/orchestrator.py`（9,954 行，下称 orchestrator.py）。

## 1. 流水线全图

### 1.1 顶层链路（src/main.py）

| 顺序 | 阶段 | 谁执行 | 输入 → 输出 | 证据 |
|---|---|---|---|---|
| 1 | 数据采集 | 代码（DataCollector） | 日期 → `data_json`（L1-L5 全部指标原始数据） | src/main.py:678-680 |
| 2 | 数据完整性检查 | 代码（DataIntegrity） | `data_json` → `integrity_report`；若 blocked/unpublishable 则走早退分支（不写正式报告，只留审计产物） | src/main.py:705、719-779 |
| 3 | 分析包装配 | 代码（AnalysisPacketBuilder.build） | `data_json` → `analysis_packet.json`（按 L1-L5 分组、每层提炼事实卡、推断层状态、生成候选跨层关系） | src/main.py:589-593；src/agent_analysis/packet_builder.py:353-404 |
| 4 | 主编排器 | 混合（代码 + 13 类 AI 站） | packet → 全部 vNext artifacts | src/main.py:836-842（`orchestrator.run(packet)`） |
| 5 | legacy 兼容导出 | 代码（adapt_vnext_to_legacy） | artifacts → `logic_vnext.json`（供旧报告器消费） | src/main.py:849-865 |
| 6 | 纯数据报告清单 | 代码（build_pure_data_report_manifest） | artifacts → `pure_data_report.json`（声明第一层是"纯数据报告"，事件材料禁入） | src/main.py:867-873；src/integrated_synthesis_report.py:100-146 |
| 7 | 出题官 + 同步巡逻 | AI（事件层研究部，旁路，失败不炸主链） | 六站对抗残局 → 出题、巡逻成果上"研究架" | src/main.py:874-898 |
| 8 | 第三层综合裁决（IA） | 混合（代码闸门 + 最多 3 次 AI 调用） | 第一层判决 + 事件层产物 → `integrated_synthesis_report.json` | src/main.py:916-922；src/integrated_synthesis_report.py:1552-1637 |
| 9 | 常设检查重跑 | 代码 | 让 PC-04/05 能读到 IA 的 prompt payload | src/main.py:923-925 |
| 10 | HTML 报告渲染 | 纯代码（VNextReportGenerator，不调 AI） | run 目录全部 JSON → 单文件 HTML | src/main.py:928-930；src/agent_analysis/vnext_reporter.py:1869-1923 |

### 1.2 主编排器内部（orchestrator.py 的 `VNextOrchestrator.run()`，692-1058）

| 顺序 | 阶段 | 谁执行 | 输出 artifact | 证据（orchestrator.py 行号） |
|---|---|---|---|---|
| 0 | 落盘 analysis_packet / runtime_boundary_manifest / feedback_contract_manifest | 代码 | 三个 JSON | 694-696 |
| 1 | context_brief（任务说明书） | 代码（`_build_context_brief`） | `context_brief.json` | 698 |
| 2 | L1-L5 五张层卡 | **AI ×5**（`_run_layer_cards`，ThreadPoolExecutor 并行） | `layer_cards/L1..L5.json` | 701；1172-1219 |
| 3 | Bridge（跨层桥接备忘录） | **AI ×1**（`_run_bridge`） | `bridge_memos/` | 702；4795-4831 |
| 4 | 反馈问询生成 + 路由 | 代码（`_build_feedback_inquiry_messages` + 纯代码 InquiryRouter） | 问询清单、AgentSpec 任务书 | 703-704；src/agent_analysis/inquiry_router.py:58-179 |
| 5 | 受控调查 | **AI ×N**（`_run_controlled_investigations`，每条委托一次，自带两次重试 + stub 兜底） | `investigation_reports/*.json` | 705；2359 起 |
| 6 | bridge_v2 合并 | 代码（`_build_bridge_v2`，把调查结果并进桥接备忘录） | bridge v2 | 706 |
| 7 | synthesis_packet（综合包） | 代码（`_build_synthesis_packet`） | `synthesis_packet.json`（含 evidence_index 证据索引） | 714 |
| 8 | 假说竞争 | 代码 + **AI ×1**（`_build_hypothesis_competition` 3025 起，内含 `_build_counter_thesis` AI 调用；失败退确定性反方 `_build_deterministic_counter_thesis`） | `hypothesis_competition.json`、`counter_thesis.json` | 715；3025；3142；3341 |
| 9 | 事件解读卡 | **AI ×N**（每张候选事件卡一次 `_run_stage`；外加事件总结 AI `_build_event_section_summary`） | `event_interpretation_cards.json`、`event_layer_summary` 段落 | 729；1851-2001；2003-2156 |
| 10 | evidence_registry（证据注册表） | 代码（`_build_evidence_registry`） | `evidence_registry.json` | 734 |
| 11 | Thesis（决策论点） | **AI ×1**（`_run_thesis`） | `thesis_draft.json` | 743 |
| 12 | Critic（批评者） | **AI ×1** | `critique.json` | 750 |
| 13 | Risk Sentinel（风险哨兵，论证盲：看不到 thesis 论证） | **AI ×1** | `risk_boundary_report.json` | 766；论证盲分料在 `_dump_governance_input` 374-386 |
| 14 | Schema Guard | 纯代码（`_run_schema_guard`） | `schema_guard_report.json` | 775；7272-7581 |
| 15 | schema 不过 → 带反馈重跑 critic/risk 各一次 | AI | 同上两个 artifact 覆写 | 780-825 |
| 16 | Reviser（修订者） | **AI ×1**；失败退 `_build_degraded_analysis_revised`（未修订原稿 + degraded 标记） | `analysis_revised.json` | 846-920；6825 |
| 17 | Final Adjudicator（终审裁决人） | **AI ×1**（`_run_final_adjudicator_stage`）；重试耗尽退 approval_status=rejected 的降级裁决 | `final_adjudication.json` | 944；6904-6953 |
| 18 | final_claim_ledger（断言台账）+ 发布闸门 | 代码（`_build_final_claim_ledger`） | `final_claim_ledger.json` | 981 |
| 19 | golden_pit_checklist（黄金坑检查单） | 代码 | `golden_pit_checklist.json` | 1003 |
| 20 | run_review / outcome_review / reflection | 代码 | 三个复盘 JSON | 1013-1034 |
| 21 | 常设检查 | 代码（`_run_persistent_checks`，跑 persistent_checks_a/b 的 PC-01~PC-29） | `persistent_checks_report.json` | 1035 |

## 2. 每次 AI 调用清单

一跑之内共有 **13 类 AI 调用**（主链 11 类 + 第三层 2 类），按角色、上下文组成、组装函数、输出消费者列全。所有主链 AI 站都走同一台引擎：`_run_stage`（orchestrator.py:6153-6416）负责组装提示词、重试、解析、校验；`LLMEngine.call_with_fallback`（src/agent_analysis/llm_engine.py:722-773）负责多模型轮换（每个模型最多试 2 次，记住上次成功的模型）。

每个 AI 调用发出的消息固定是两条：一条 system 消息（`prompts/system_constraints.md` 全文，六条不可违反的纪律；文件丢失时用内嵌五条兜底，llm_engine.py:502-521、553-556），一条 user 消息（站提示词 + 本站 payload）。采样参数固定 temperature=0.2（llm_engine.py:560）。DeepSeek 服务额外加两把锁：strict function calling（把契约转成 JSON Schema 当表单发过去，llm_engine.py:564-603）和 `response_format=json_object`（语法锁）；schema 转换函数是 `sanitize_json_schema_for_strict_tool_calling`（llm_engine.py:110-287），其中标注"代码填"的字段会被直接从发给模型的 schema 里剪掉（登记表在 llm_engine.py:89-107）。

| # | 站 | 角色 | 上下文组成（payload） | 组装函数 | 提示词文件 | 输出消费者 |
|---|---|---|---|---|---|---|
| 1 | L1-L5 层分析师 ×5 | 单层分析师，只看本层数据（层间运行时隔离写在提示词开头，prompts/l1_analyst.md:5-7） | 本层指标原文 + 静态五层本体 + context_brief | `_compose_layer_prompt`（orchestrator.py:8052-8130） | prompts/l1~l5_analyst.md | Bridge（第 2 站） |
| 2 | bridge | 跨层关系测绘员 | 5 张层卡 + 候选跨层关系 | `_run_bridge`（4795-4831） | prompts/cross_layer_bridge.md | synthesis_packet（代码合并）、Thesis |
| 3 | 受控调查 ×N | 受控调查员："你不知道、也不需要知道系统当前的判断是什么"（prompts/controlled_investigator.md:5） | 一个待裁决问题 + 一小包允许读的材料 | `_run_controlled_investigations`（orchestrator.py:2359 起） | prompts/controlled_investigator.md | bridge_v2、Thesis、IA |
| 4 | counter_thesis | 反方假说构造者；**禁止读** thesis_draft / analysis_revised / final_adjudication（prompts/counter_thesis.md:31-37） | synthesis_packet（去自引用版）+ bridge v1 + 调查摘要 + 许可 ref 清单 | `_build_hypothesis_competition` 内（3142-3225） | prompts/counter_thesis.md | Thesis（必须逐条回应假说） |
| 5 | 事件卡解读 ×N | 事件解读员；事实与解读分栏 | 单条事件材料（标题/来源/日期/正文摘录）+ 竞争假说清单 | `_build_event_interpretation_cards`（1851-2001） | prompts/event_card_interpreter.md | IA（第三层）、事件总结 |
| 6 | 事件总结 | 事件层收束员；**禁止提及 L1-L5 任何指标**（prompts/event_section_summary.md:6） | 本轮全部事件卡 + effective_date；有效卡 <2 张时代码直接跳过、不调模型（prompts/event_section_summary.md:18） | `_build_event_section_summary`（2003-2156） | prompts/event_section_summary.md | IA、报告"外部世界对照"章节 |
| 7 | thesis | 决策论点构建者 | synthesis_packet（层摘要、bridge 摘要、高严重度冲突、evidence_index、竞争假说） | `_run_thesis`（743 调用） | prompts/thesis_builder.md | Critic、Risk、Reviser |
| 8 | critic | 批评者，"挑刺不是完善"（prompts/critic.md:9-12） | 压缩 governance_input：thesis 核心段落 + 高严重度冲突 + 关键证据索引 | 750 调用；分料 `_dump_governance_input`（374-386） | prompts/critic.md | Reviser |
| 9 | risk | 风险哨兵，**论证盲**："你拿不到论点论证……这是刻意设计（论证盲），不得脑补一个论点出来攻击"（prompts/risk_sentinel.md:30） | 压缩 governance_input：只有层摘要 + 冲突清单 + 证据数值卡片，无 thesis 段落 | 766 调用；同一 `_dump_governance_input` | prompts/risk_sentinel.md | Reviser、Final |
| 10 | reviser | 修订者（编辑不是重写者，prompts/reviser.md:9-11） | thesis 原稿 + critic 批评 + risk 风险清单 + schema 问题 + 证据索引 | 846-920 | prompts/reviser.md | Final Adjudicator |
| 11 | final_adjudicator | 终审裁决人，双身份（quality_gate 内部校验 + reader_final 读者结论，prompts/final_adjudicator.md:5-10） | 压缩 governance_input：修订稿 + revision_summary + 高严重度冲突 + fact_card（"本次允许使用的数字菜单"）+ 反方假说 | `_run_final_adjudicator_stage`（6904-6953）；payload 在 run():932-935 组装 | prompts/final_adjudicator.md | claim_ledger（代码）、IA、报告首屏 |
| 12 | integrated_adjudicator（IA，第三层） | 综合裁决人；"数据判决是基准，你无权改判"（prompts/integrated_adjudicator.md:23） | 第一层判决摘录 + 事件卡（≤10 张，逐卡截断）+ 非 stub 调查报告（≤3）+ 研究架巡逻 + 跨层问题 + 从实发 payload 导出的许可 ref 清单 | `_llm_adjudication`（src/integrated_synthesis_report.py:288-458；payload 组装 367-397）；llm_caller 由 main.py:921 传入 | prompts/integrated_adjudicator.md | 第三层报告、补采清单、抗诉横幅 |
| 13 | IA 批评者 + IA 定稿 | 第三层批评者，只挑四类刺（逻辑跳步/因果越界/抹平冲突/引用与数字，prompts/integrated_adjudicator_critic.md:10-15） | IA 草稿 + 与 IA 相同的输入面 | `_critic_and_finalize`（src/integrated_synthesis_report.py:487-555）；批评者和定稿各最多 2 次尝试，失败退草稿 + degraded 标注 | prompts/integrated_adjudicator_critic.md | 第三层报告 |

补充三个上下文工程事实：

- **提示词优先读文件，文件丢了才用内嵌兜底**。`_load_prompt`（orchestrator.py:8380-8393）优先读 `prompts/*.md`（文件登记表 PROMPT_FILES 在 149-165）；`INLINE_PROMPTS`（337-345）是六个治理站的一句话兜底说明书。注意 `prompts/context_loader.md` 是死文件：orchestrator.py 全文没有任何引用（grep 零命中），第 1 阶段的 context_brief 由纯代码生成（698 行），该提示词描述的"Context Loader AI 站"在当前主链里不存在。
- **每站契约要求登记在一张表里**。`STAGE_CONTRACT_PROMPT_REQUIREMENTS`（orchestrator.py:177-235）登记每站提示词必须交代什么；schema 能锁的进 schema、代码能装配的不让模型填，剩下的才进提示词。
- **审计落盘是逐次调用的**。每次尝试的提示词与原始响应都写进 `prompt_audit/<stage>/attempt_N.*`（主链由 `_run_stage` 落盘；IA 由 `_write_audit` 落盘，src/integrated_synthesis_report.py:1102-1113）。`context_spread.py` 是事后审计工具，把这些落盘文件导出投影供复查（src/agent_analysis/context_spread.py:1-33），不在运行时主链里。

## 3. 闸门清单

闸门分五层：契约层、运行时校验器、纯代码闸门、常设检查、发布链闸门。运行时校验器的共同行为：失败时把错误原文喂回给 AI 重写（增量重试规则在 orchestrator.py:6213-6229），每站最多 `max_node_retries=2` 次尝试，耗尽后走该站自己的降级路径（见第 1.2 节各站兜底）。

### 3.1 契约层（contracts.py，2,807 行）

每个站的输出都有一个 pydantic 模型（LayerCard、BridgeMemo、ThesisDraft、Critique、RiskReport、AnalysisRevised、FinalAdjudication、IntegratedAdjudication 等），字段类型、枚举值、必填项由 schema 锁定。契约内还有 validator（校验器函数）做跨字段检查。2026-08-31 的 T69"闸门宪法 v2"把一批"需要读懂语义才能判"的校验降级为"留痕不拦"（semantic_warnings），例如：sign_reversal（orchestrator.py:410-442）、hindsight_causal（2234-2253）、stance_label 方向冲突（contracts.py:2469-2494）、missing_evidence_as_direction（contracts.py:2512-2536）。保留下来的硬校验全是身份比对（编号在不在清单里、引用在不在索引里）。

### 3.2 运行时校验器（接进 `_run_stage` 的 validator 链）

| 校验器 | 位置（orchestrator.py） | 校验什么 | 失败后果 |
|---|---|---|---|
| `_validate_layer_card_v2` | 7150-7211 | 层卡形状与 evidence_refs 合法性 | 带错误重试 |
| `_validate_bridge_memo_v2` | 7213-7270 | bridge 输出；**evidence_refs 禁 `event:` 前缀**（7248-7269） | 带错误重试 |
| `_validate_counter_thesis_draft` | 3262-3278 | 反方假说引用 ⊆ 许可清单 | 重试；耗尽退确定性反方 |
| `_validate_thesis_hypothesis_responses` | 5254-5311 | thesis 对每个非 downgraded 假说恰有一条回应 | 带错误重试 |
| `_event_card_validation_errors` | 1801-1836 | 事件卡 supports/refutes_hypotheses ⊆ 竞争假说清单 | 带错误重试 |
| 事件总结校验 | 2256-2334 | 含时点闸：总结里不得出现晚于 effective_date 的日期（2313-2333） | 带错误重试 |
| 调查材料 [M#] 引用校验 | 2768-2791 | 调查报告引用的材料编号必须真实存在 | 带错误重试 |
| `_validate_stage_evidence_refs` | 6857-6889 | 各站 evidence_refs ⊆ evidence_index | 带错误重试 |
| `_validate_reasoned_verdict_refs` | 6977-7047 | 终审判决正文：零引用拦截、引用 ∈ evidence_index、**数字逐字核对**（详见第 5 节） | 带错误重试；耗尽退 rejected 降级裁决 |
| `_validate_final_conflict_responses` | 7102-7148 | 高严重度冲突编号必须出现在终审输出 | 带错误重试 |

### 3.3 纯代码闸门

- `_run_schema_guard`（orchestrator.py:7272-7581）：结构检查 + 高严重度冲突"认亲"（7506-7548）；不通过则带反馈重跑 critic/risk 一次（780-825）。
- `_verify_claim_entry`（orchestrator.py:4063）+ `_claim_ledger_publish_gate`（4183）：断言台账逐条核对 + 发布闸门；闸 blocked 时报告不渲染（src/main.py:928、936-939）。
- 严格表单消毒：`sanitize_json_schema_for_strict_tool_calling`（llm_engine.py:110-287）把契约转成 DeepSeek 接受的形态；`normalize_none_list_fields_for_strict_schema_validation`（315-396）是配对归一化。
- 导入时架构校验：`validate_prompt_examples` 不过直接终止程序（llm_engine.py:919-931）。

### 3.4 常设检查（PC-01 ~ PC-29）

一跑收尾时跑 29 项常设检查（`_run_persistent_checks`，orchestrator.py:1035），登记表在 src/agent_analysis/persistent_checks_a.py:926-935（PC-01~PC-10）与 persistent_checks_b.py:1323-1332 及续表（PC-11~PC-29）。这些检查只出报告不改产物；其中 PC-28 是"抗诉"红灯（persistent_checks_b.py:1206-1257，详见第 4 节）。

### 3.5 发布链闸门

DataIntegrity 阻断 → 早退（src/main.py:719）；final approval_status=rejected → 第三层只能 audit_only（src/integrated_synthesis_report.py:1160-1167）；claim_gate blocked → 不渲染 HTML 报告（src/main.py:928）。第三层自己还有一道时间一致性闸：所有输入 artifact 的 as-of 日期不一致即 audit_only（src/integrated_synthesis_report.py:1205-1267，接入 publish_gate 1183-1203）。

## 4. 对质点：事件层产物如何进入数据层裁决

答案分两半：**第一层（数据链）在运行时对事件材料物理隔离；真正的对质发生在第三层（IA），且裁决规则是"数据判决为锚、异议走抗诉通道"。**

### 4.1 隔离侧（事件材料进不了数据层）

- 分析包里事件只以 `event_refs` 背景身份存在，每条自带使用边界："event_ref only: catalyst/background/observation, not numeric proof"（packet_builder.py:406-445，边界原话在 443 行）。
- Bridge 的 evidence_refs 禁止 `event:` 前缀（`_validate_bridge_memo_v2`，orchestrator.py:7248-7269）。
- 第一层产物清单的提示词政策明文列出七个禁止输入（news_event_ledger、event_narrative_ledger、cross_layer_questions 等），并注明"事件材料只能出现在第二层和第三层产物里"（src/integrated_synthesis_report.py:111-123）。
- 第三层报告的回流禁令："This report must not feed back into L1-L5, Bridge, Thesis, Risk, Reviser, or Final"（src/integrated_synthesis_report.py:248）；InquiryRouter 的政策清单同样写死"调查报告不得回写或注入 L1-L5 层卡"（inquiry_router.py:116-119）。

### 4.2 事件侧产物怎么生成

事件层产物由 main.py 生成（不在主编排器内）：`news_event_ledger.json`（src/main.py:703）、`event_narrative_ledger`（826-834）、`event_layer_summary`、`event_mechanism_report`、`cross_layer_questions` 等写进 run 目录（清单见 957-969）。主编排器消费它们的位置只有两处：`_select_event_card_candidates`（orchestrator.py:1703-1763，读 news_event_ledger + event_mechanism_report 挑候选卡）和 `_event_passports`（3845-3880，读 event_narrative_ledger）。然后每张候选卡由事件卡解读 AI 生成结构化卡片（1851-2001），卡上的 supports/refutes_hypotheses 只能挂到治理链已有的竞争假说上（校验在 1801-1836）——这是事件材料触达主链判断的唯一形式化通道：给假说提供"解释线索或待验证挑战"，永远不能当数据证据。

### 4.3 对质侧（第三层 IA）

- 接线：main.py:916-922 调用 `write_integrated_synthesis_report`，传入 `llm_caller=orchestrator.llm_engine.call_with_fallback`；全部输入 artifact 的加载在 src/integrated_synthesis_report.py:1552-1637。
- 裁决规则：提示词明文"**数据判决是基准，你无权改判**"（prompts/integrated_adjudicator.md:23）。机器侧同规则写成 policy："The layer-3 adjudication may not deviate from the layer-1 final_stance; tensions are recorded, never re-adjudicated"（src/integrated_synthesis_report.py:250）。
- 对质动作一：`conflict_matrix` 每张事件卡一行，relation 三选一（confirmed_by_data / challenged_by_data / not_yet_testable）；机器硬闸门把"声称被数据证实/削弱但给不出数据侧 ref"的行自动降级为 not_yet_testable（src/integrated_synthesis_report.py:770-786）。
- 对质动作二：`question_answers` 逐条回答"新闻事件给数据层出的题"（cross_layer_questions）；声称"数据足以回答"却拿不出 data_refs/investigation_refs 的回答被自动降级为 cannot_answer_yet（707-768）。
- 对质动作三：`data_verdict_objections` 抗诉通道。只有"研究架对账通过的核实事实 + materiality=material"的异议才算抗诉：常设检查 PC-28 亮红灯（persistent_checks_b.py:1206-1257），报告第一屏置顶抗诉横幅（vnext_reporter.py:2605-2645，横幅原话："【抗诉】经核实的外部事实与数据判决正面冲突——改判与否由你裁决，数据判决为锚、系统不改"）。事件卡来源的挑战只记录不亮灯（prompts/integrated_adjudicator.md:23、40；契约 DataVerdictObjection 在 contracts.py:523-547，IntegratedConflictRow 在 499-520）。
- 伪引用硬闸门：IA 输出的所有 data ref 必须在"从实发 payload 导出的白名单"里，不在的一律剔除并留痕（src/integrated_synthesis_report.py:663-678）；白名单从实际发给模型的 payload 里导出，保证"许可集合 ⊆ 实际发送集合"恒真（设计说明在 360-366 注释，收集函数在 944-980）。
- 失败处置：IA 调用失败、校验失败、发布闸门 audit_only、时间不一致——全部走"返回 None + 原因写进 policy.llm_note + 确定性拼装照跑"，绝不阻断 run（288-318、452-458）。

### 4.4 冲突如何记录

主链内：Bridge 产出 typed_conflicts → 高严重度冲突在 schema_guard 认亲（7506-7548）→ thesis/reviser/final 必须逐条回应（`_validate_final_conflict_responses` 7102-7148）→ 保留进 final_claim_ledger。跨层（事件对数据）：conflict_matrix + data_verdict_objections + unexplained_items 三个载体（src/integrated_synthesis_report.py:269-277、1513-1536）。任何一层都不允许"为顺滑抹平冲突"——这条禁令同时写在 bridge、thesis、reviser、final、IA 五份提示词里（如 prompts/cross_layer_bridge.md:220-221、prompts/final_adjudicator.md:345）。

## 5. 专项猎捕："数字逐字核对"校验器

**结论：它存在，健在，而且是硬闸门（失败触发重试，重试耗尽触发降级裁决）。**

- 本体：`_validate_reasoned_verdict_refs`（orchestrator.py:6977-7047），2026-08-16 T42② 引入"数字存在性比对"。docstring 原文（7002-7005）："`source_text`（T42②）是终审这一站实际收到的 payload 文本。传了就额外做'数字存在性比对'：判决正文里出现的百分数 / 小数值必须逐字出现在本次输入中——'报告里写的 2.3%，原始 payload 里找不找得到 2.3%'是身份比对，不是语义判断，符合「闸门不判意思」。"
- 当前行为：提取判决正文 `reasoned_verdict` 里的百分数和小数 token（`_reasoned_verdict_numeric_tokens`，7064-7075；正则为 `r"\d+(?:\.\d+)?\s*%|\d+\.\d+"`，在 7071 行；**纯整数故意不提取**，注释 7068-7069 说明是为了避免把"三条理由""纳斯达克100"这类行文数字误判成编造数据）。任何一个 token 不在终审实收 payload 文本里，即返回校验错误。错误消息原文（7042-7045）：`"final_adjudication.numbers_grounding: reasoned_verdict contains numbers that are not present in the stage payload (identity check, not semantic): {missing}. Only use numbers that appear verbatim in the input."`
- 接线点：`_run_final_adjudicator_stage` 的 validator lambda（orchestrator.py:6926-6941）；`source_text` 由 run():935 组装——`final_source_text = json.dumps(final_payload, ensure_ascii=False, default=str)`，即终审实际收到的全部输入序列化后的文本。比对方向是"输出里的每个数字 ⊆ 输入文本"，是子集关系，不是逐句对齐。
- 失败后果：校验错误进入 `_run_stage` 的重试反馈，模型带错误重写；重写耗尽后 `_run_final_adjudicator_stage` 退回 approval_status=rejected 的降级裁决（6904-6953）。
- 同函数另外两道闸：零引用拦截（7012-7016）和引用逐字 ∈ evidence_index（7023-7033，容忍逗号合并的解析在 7050-7062）。
- 已拆除的同类闸门留档：2026-08-31 T69 P0-4 删除了"≥3 方括号组且 ≥3 条不同引用"的计数子条（注释 6996-7000），删除理由是"括号组数代理'总-分-总'结构是形状代理语义（闸门宪法 v2）"。
- 配套机制（构造即忠实）：T70 P-B 事实卡 `_build_fact_card`（orchestrator.py:8005-8037）从证据索引装配"本段允许出现的数字"菜单，每条带 ref、指标名、数值原值、权限档；docstring 原话（8010-8011）："写作层只从卡里选用数字；数字写错是装配 bug（装配自检，响了修管道，不打回模型）"。提示词侧对应 final_adjudicator.md:119："数字若与卡不符是装配的 bug，由系统修管道，不由你凑对。"也就是说：数字核对器的职责是兜底，第一道防线是"输入侧就把可用数字限定成一张菜单"。

## 6. "AI 被逼成抄写员"的其他证据

"抄写员"指 AI 被迫逐字背抄编号、字段名、固定句式，把认知精力耗在簿记上。源码证据显示：系统已经系统性地把这类负担从 AI 肩上卸掉，改成"模型报序号、代码回填编号"或"代码直接装配、模型不用填"。逐条证据如下（前四条是"序号代报"机制，后六条是"代码装配"机制）：

1. **冲突只报序号**。orchestrator.py:4980-5251 实现 conflict_ordinal/hypothesis_ordinal 机制（设计原话："模型报序号、代码回填编号，抄写笔误物理不可能"）。提示词侧：thesis_builder.md:251"沿用上游冲突时填它在「冲突清单（按序号引用）」里的序号：第 1 条填 1、第 2 条填 2……编号由系统按序号回填"；报错后果也写明（thesis_builder.md:357）："报错了系统会带合法范围打回"。reviser.md:46、224 同款。
2. **假说只报序号**。thesis_builder.md:81"每条回应用 `hypothesis_ordinal` 填该假说在 `competing_hypotheses` 数组里的序号……`hypothesis_id` 由系统按序号回填，不要自己填写"；reviser.md:17 同款。
3. **第三层问答只报序号**。prompts/integrated_adjudicator.md:38、51"每条用 `question_ordinal` 标明回答的是第几问……`question_id` 由系统按序号回填，不要自己填写"；代码回填在 src/integrated_synthesis_report.py:879-905，注释（879-883）写明"ordinal 在场时模型自填的 id 一律不采信，抄写笔误物理关闭"。
4. **终审不用填台账**。prompts/final_adjudicator.md:298-299"`claim_ledger` 由代码整本装配……你输出的任何 claim_ledger 内容都会在归一化阶段被摘除、不参与校验"。
5. **修订清单不用自报**。prompts/reviser.md:218"`revision_claimed_fields` 不用你填：它由代码把 `revised_thesis` 与修订前逐字段比对后装配（PC-03 的核对在代码里），模型自报会被整体覆盖——把精力放在修订本身。"
6. **事件卡的身份字段不用填**。prompts/event_card_interpreter.md:12"`entities`、`event_type`（采集标签）、`event_id` 与 `passport` 由代码按采集档案（新闻底稿库）装配回填，不用你填——填了也会被档案值覆盖。"
7. **事件总结的引用清单不用另列**。prompts/event_section_summary.md:16"引用清单不需要你另外列出——代码会从正文里的 `[card:...]` 标记里自动提取"；同文件 :18"跳过判断由代码做，不由你做"。
8. **指标法典六字段强制装配**。`_backfill_indicator_canon_fields`（orchestrator.py:9203-9249）；配套法典原文 src/agent_analysis/deep_research_canon.py:999-1004："function_id 必须逐字来自输入指标键——抄错一个字代码会按输入键集回正或打回重写"。
9. **机械字段统一装配**。`_assemble_stage_mechanical_fields`（orchestrator.py:8716 起）：凡代码能确定性生成的字段（身份名、枚举值、编号、时间戳、引用键）一律由代码装配。
10. **"代码填"的字段从发给模型的 schema 里剪掉**。llm_engine.py:89-107 的 `STRICT_SCHEMA_FREE_FORM_OBJECTS` 登记表逐条标注"代码填/模型填"，剪枝逻辑在 227-287——模型在表单里根本看不到这些字段。第三层同款：schema_version / judgment_object / stance_echo 由代码装配，"模型答卷里的 stance_echo 一律摘除、不参与校验"（src/integrated_synthesis_report.py:636-642、811-821）。
11. **空列表不用誊抄**。prompts/thesis_builder.md:23"没有用到事件背景时该字段直接省略（系统会补空列表），不要逐字誊抄 `\"event_refs\": []`"。
12. **数字抄写本身已变成身份比对**。第 5 节的数字逐字核对器 + 事实卡组合，把"模型背诵数字"换成了"模型从菜单里选数字、代码验明正身"。

残余的"抄写"负担（如实记录）：层分析师仍被要求"function_id 必须等于输入 function_id"（`_compose_layer_prompt` 的逐字纪律，orchestrator.py:8052-8130），受控调查员被要求"数字、分位、日期只能从材料里逐字引用"（prompts/controlled_investigator.md:6）。这两处属于"输入材料的引用纪律"而非"簿记字段填写"，且有第 5 节那类身份比对闸门兜底。

## 7. 边界与局限

- 本图覆盖 `src/main.py`、`src/agent_analysis/`（orchestrator、contracts、packet_builder、llm_engine、inquiry_router、vnext_reporter、persistent_checks_a/b、prompts/）与 `src/integrated_synthesis_report.py`。数据层采集器（tools_L1-L5）、事件层研究框架（src/event_research/）的内部结构不在本图范围，另有专图。
- 行号以 2026-09-15 工作区快照为准；后续改动会使行号漂移，函数名不变。
- "13 类 AI 调用"按角色分类计数；一次真实运行的调用次数 = 5（层卡）+ 1（bridge）+ 受控调查实际委托数 + 1（counter_thesis）+ 事件卡实际张数 + ≤1（事件总结，卡少时跳过）+ 1（thesis）+ 1（critic）+ 1（risk）+ ≤2（schema 不过时重跑 critic/risk）+ 1（reviser）+ 1（final）+ ≤3（IA 草稿/批评/定稿），再乘以每站最多 2 次重试上限。
