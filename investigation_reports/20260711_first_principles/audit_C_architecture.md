# ndx_vnext 推理链与架构层 第一性原理审计（审计 C：架构）

调查范围：只读代码审计 + 一次真实 run 产物核查。未修改仓库任何文件。
真实 run 使用路径：`output/analysis/vnext/20260709_233816/`（与任务给定路径一致，无需替换）。

标注约定：**[已验证]** = 我实际读了代码/artifact 并确认；**[推测]** = 基于已验证事实的合理推断，未逐行穷举证实。ARCHITECTURE.md 等自述文档只作线索，不作为结论证据；结论证据一律是 `文件:行号` 或 artifact 路径。

---

## ① 理想最小架构（先立靶子，后面用来量现状的偏差）

目标不是"L1-L5+Bridge+Thesis+Counter-Thesis+Critic+Risk+Adjudicator"这个人类职位式分工，而是"可审计、防幻觉、防越权"这三件事本身需要什么。第一性拆解：

1. **确定性数据闸门**（代码，不需要 LLM）：采集数据 → 校验覆盖率/未来数据泄漏/来源冲突 → 决定能不能进入分析。这是硬约束，必须在任何 LLM 介入之前跑完，且必须是纯代码。
2. **N 个视角局部化的解读单元**（可以是 LLM，也可以是规则）：每个视角只吃自己负责的数据子集，产出"本视角看到了什么、有什么把握、需要谁核实"。视角之间的输入隔离必须是**结构性**的（代码层面切片），不能只靠 prompt 里写"别看别的"。
3. **一次显式的冲突/共振捕获**：把 N 个局部解读放在一起，找出互相支持和互相矛盾的地方，并且**保留**矛盾，不强行拉平。
4. **至少一次真正独立的对抗检验**：一个视角，输入被物理限制为"不能看到当前结论"，任务是找反例/反证据。这是防幻觉的核心机制，必须真的独立（读不到主线结论），而且必须真的执行（不能因为解析失败就静默退化成模板文本却不被任何下游感知）。
5. **一次把证据、结论、反证、失效条件绑定在一起的裁决**：产出最终立场，并且这个立场的每一句关键论断都能倒查到具体证据引用。
6. **确定性的证据-论断核验**（代码，不需要 LLM）：检查裁决阶段声称的每条 evidence_ref 是否真实存在、是否被越权使用（比如技术指标证明估值便宜）、是否配了反证和失效条件。这一步理论上完全可以是纯 Python，不需要新的 LLM 调用。
7. **发布闸门**：任一环节不达标（数据不完整、证据核验不过、越权发言）就整体标记为不可发布，而不是继续往下走生成一份"看起来完整"的报告。
8. **审计留痕**：每一步的输入输出要落盘，能倒查。

大约 5-7 次实质性 LLM 调用（N 个局部视角 + 1 次冲突捕获 + 1 次对抗检验 + 1 次裁决，视角数按 L1-L5 五个算是 5+3=8 次）就能覆盖以上全部本质环节，其余都应该是确定性代码。下面用这把尺子量现状。

---

## ② 现状真实管线（以代码 + 真实 run 为准）

### 阶段与调用顺序（源自 `src/agent_analysis/orchestrator.py` 的 `VNextOrchestrator.run()`，300-541 行）**[已验证]**

```
1.  DataCollector + DataIntegrity            代码，无 LLM   (src/main.py:398-457)
2.  AnalysisPacketBuilder                    代码，无 LLM   (packet_builder.py:335-371)
3.  context_brief（全局）                     代码，无 LLM   (orchestrator.py:3162-3184)
4.  L1 Analyst  → LLM 调用 #1                (orchestrator.py:655-691, 循环体)
5.  L2 Analyst  → LLM 调用 #2
6.  L3 Analyst  → LLM 调用 #3
7.  L4 Analyst  → LLM 调用 #4
8.  L5 Analyst  → LLM 调用 #5
9.  Bridge v1   → LLM 调用 #6                (orchestrator.py:2611-2647)
10. feedback inquiry messages                代码，无 LLM   (orchestrator.py:907-1063)
11. InquiryRouter 路由                        代码，无 LLM   (orchestrator.py:1063-1086)
12. Controlled Investigation ×N              代码，无 LLM，**硬编码模板**  (orchestrator.py:1099-1150)
13. Bridge v2                                代码，无 LLM，**对 v1 做字段搬运**  (orchestrator.py:1183-1284)
14. SynthesisPacket 构建                      代码，无 LLM   (orchestrator.py:2677-2846)
15. Counter-Thesis  → LLM 调用 #7（失败会有确定性兜底）      (orchestrator.py:1384-1426)
16. Hypothesis Competition 合并               代码，无 LLM   (orchestrator.py:1286-1382)
17. Evidence Registry 构建                    代码，无 LLM   (orchestrator.py:1742-1898)
18. Thesis Builder → LLM 调用 #8              (orchestrator.py:2649-2675)
19. Critic       → LLM 调用 #9                (orchestrator.py:348-354)
20. Risk Sentinel → LLM 调用 #10              (orchestrator.py:356-362)
21. Schema Guard                             代码，无 LLM   (orchestrator.py:3710-3958)
    [若不过，Critic/Risk 各重跑一次 → 最多再 +2 次 LLM 调用]  (orchestrator.py:369-404)
22. Reviser      → LLM 调用 #11               (orchestrator.py:414-425)
23. Final Adjudicator → LLM 调用 #12           (orchestrator.py:439-457)
24. Final Claim Ledger 构建 + 核验             代码，无 LLM   (orchestrator.py:2004-2213)
25. Golden Pit Checklist / User Decision Profile   代码，无 LLM
26. Run Review Report / Outcome Review Report      代码，无 LLM
27. Post-Run Reflection Library                    代码，无 LLM，**产出后无人读取**
```

即：**12 次真实 LLM 调用是基线**（L1-L5 ×5、Bridge ×1、Counter-Thesis ×1、Thesis ×1、Critic ×1、Risk ×1、Reviser ×1、Final ×1），其余全部是确定性 Python 代码。这个比例本身是健康的——大部分"治理"工作没有交给 LLM，这点比很多同类项目更克制。

### 真实 run 的调用与 token 量级（`output/analysis/vnext/20260709_233816/llm_stage_diagnostics.json`、`final_adjudication.json` 的 `token_usage` 字段）**[已验证，非估计]**

| 阶段 | 状态 | 尝试次数 | prompt tokens | completion tokens |
|---|---|---|---|---|
| L1 | ok | 1 | 24,542 | 5,172 |
| L2 | ok | 1 | 22,792 | 4,511 |
| L3 | ok | 1 | 18,622 | 5,280 |
| L4 | ok | 1 | 33,280 | 6,329 |
| L5 | ok | 1 | 22,555 | 10,891 |
| Bridge | ok | 1 | 29,671 | 7,084 |
| Counter-Thesis | **failed→兜底** | 2 | 33,524 | 2,577 |
| Thesis | ok | 1 | 33,701 | 5,333 |
| Critic | ok | 1 | 16,094 | 5,075 |
| Risk | ok | 1 | 16,858 | 2,331 |
| Reviser | ok | 1 | 17,439 | 11,134 |
| Final | ok | 2 | 18,900 | 6,210 |
| **合计** | | | **287,978** | **71,927**（总 359,905） |

单次正式 run 约 36 万 token，12 个逻辑阶段、实际发生 14 次网络级 LLM 调用（含 2 次失败重试）。这是一个中等规模的量级，不算离谱，但 Counter-Thesis 那 33,524 个 prompt token 因为两次都类型校验失败，**完全没有产出任何被使用的内容**，全部浪费。

### 与 ARCHITECTURE.md 自述的出入 **[已验证]**

`ARCHITECTURE.md` 第 216-238 行给出的"推荐调用链"一共 20 步、17 个模型/代码节点，其中**完全没有出现** `Counter-Thesis`、`Claim Ledger`、`Evidence Passport`、`Golden Pit Checklist`、`InquiryRouter`、`hypothesis_competition`、`state_ledger` 这些词（对全文 575 行做过精确 grep，零命中）。而这些恰恰是 `orchestrator.py` 里现在最重的几块新增子系统（`_build_hypothesis_competition`、`_build_final_claim_ledger`、`_build_evidence_registry`、`InquiryRouter` 相关方法群，合计几百行代码）。也就是说：**项目自己的架构说明文档已经落后于代码本身的复杂度增长**，这不是我的推测，是对文档做穷举检索后的事实。

---

## ③ 关键发现（按严重度从高到低，每条附代码/artifact 证据）

### 发现 1【严重，已验证】"受控调查"反馈环全链路目前 100% 不产生任何效果，但机制本身相当庞大

`_build_investigation_report`（`orchestrator.py:1099-1150`）在**唯一的构造点**（`orchestrator.py:1133`）把 `is_deterministic_stub=True` 硬编码写死；全仓库 grep `is_deterministic_stub` 只有这一处赋值为 `True`，没有任何路径能把它设为 `False`（已对 `src/agent_analysis/*.py` 做过穷举 grep）。而 `_build_bridge_v2`（`orchestrator.py:1194-1198`）判断"这次调查是否改变了判断"的逻辑是：

```python
changed = bool(
    not getattr(report, "is_deterministic_stub", False)
    and report.claims_challenged
    and "strong_single_path_adjudication" not in report.claims_challenged
)
```

由于 `is_deterministic_stub` 恒为 `True`，`changed` **在当前代码下数学上恒为 `False`**。真实 run 的 `bridge_memos/bridge_v2.json` 里 `feedback_loop_summary.changed_judgment_count = 0`，与代码推导完全吻合（`output/analysis/vnext/20260709_233816/bridge_memos/bridge_v2.json`）。三份 `investigation_reports/*.json` 的 `finding` 字段是三选一的固定模板句（"本轮未执行真实调查，仅登记……"），逐字核对过其中两份完全相同。

但支撑这套机制的代码量不小：`InquiryMessage`/`AgentSpec`/`InvestigationReport`/`InquiryRouterOutput` 等 5+ 个合约类（`contracts.py`）、`InquiryRouter` 独立模块、`orchestrator.py` 里 `_build_feedback_inquiry_messages`（907-970）、`_build_event_challenge_messages`（971-1022）、`_build_observation_inquiry_messages`（1023-1062）、`_route_feedback_inquiries`、`_run_controlled_investigations`、`_build_investigation_report`、`_build_bridge_v2`、`_build_hypothesis_competition` 里对 investigation 的消费逻辑，粗估至少 400-500 行代码，专门为了产出"我们什么都没查"这句话，并保证它永远不影响任何结论。

**这是本次审计里最能说明"精密 vs 臃肿"张力的单一证据**：机制的工程完成度（合约、路由、预算控制、只读边界校验 `_read_allowed_context_notes` 会拒绝越权路径读取）相当高，但产出价值目前是零，且没有任何测试或告警提示这个子系统已经名存实亡。

### 发现 2【严重，已验证（真实 run 实锤）】Final Adjudicator 的部分"独立裁决"内容是对上游 LLM 输出的逐字节复制，不是新的认知产物

对比同一次真实 run 里三份文件：
- `analysis_revised.json` 的 `revised_thesis.time_horizon_views[0]`
- `final_adjudication.json` 的 `reader_final.time_horizon_summary[0]`

两者字段级逐一比对（horizon/view/action_implication/evidence_refs/invalidation_conditions）**完全相同，一字不差**。

同样，`final_adjudication.json` 的 `must_preserve_risks`（5 条风险陈述，每条 100+ 字）与 `risk_boundary_report.json` 的 `must_preserve_risks` **逐条完全相同**。

这说明：ARCHITECTURE.md 和 CLAUDE.md 里强调的"Final Adjudicator 独立裁决"，在这次真实 run 里，其"独立"部分实际发生在别处（Reviser 吸收 Critique 的修订、Risk Sentinel 定义风险边界），Final 这一步至少在 `time_horizon_summary` 和 `must_preserve_risks` 两个维度上，是把已经算好的内容原样誊抄进 `reader_final` 结构。它真正新增的内容是 `quality_gate`（approval_status 决策）和 `final_stance`/`priced_narrative` 的重新措辞（这两处经检查确实有实质改写，不是复制）。**结论不是"Final 这一步没用"，而是"Final 这次 LLM 调用里，大部分 token 花在了搬运而不是裁决"**——18,900 个 prompt token、6,210 个 completion token 里，有相当比例是在生成本来就该由代码直接拼接的字段。

### 发现 3【中高，已验证】"L1-L5 运行时隔离"是真实的结构性代码过滤，但是靠单进程内多处手工切片保证的，不是物理/进程级隔离，且已经存在一个未使用但已构建好的全层数据泄漏通道

先给隔离"是真的"的证据（这点比我预期的扎实）：
- `packet_builder.py:514-570` 的 `_group_raw_data` 把采集到的指标按 `layer` 分组存进 `AnalysisPacket.raw_data: Dict[layer, ...]`；
- `orchestrator.py:693-708` 的 `_build_layer_stage_payload` 用 `packet.raw_data.get(layer, {})` 只取当前层；
- `orchestrator.py:4217-4233` 的 `_filter_layer_raw_data_for_prompt` 做**第二道**过滤：对每个字段查 `deep_research_canon.get_indicator_canon(function_id)`，只保留 `canon.layer.value == layer_value` 的字段；
- `orchestrator.py:3186-3209` 的 `_build_layer_context_brief` 只把 `context_brief.layer_highlights.get(layer, [])` 塞给该层，且 `apparent_cross_layer_signals=[]`（强制清空跨层候选信号）。

这是两道独立的代码级过滤（一道在打包阶段按 layer 分组，一道在组 prompt 前按 canon 二次核对），**不是仅凭 prompt 文案约束**。但同时要指出三个限制：

1. **不是进程隔离**。所有 L1-L5 调用发生在同一个 `VNextOrchestrator` 实例、同一个 Python 进程、同一个 `self.llm_engine` 对象里，顺序执行（`orchestrator.py:657` 的 `for layer in ["L1","L2","L3","L4","L5"]` 循环）。隔离完全依赖"没有代码路径把其他层数据塞进 payload"这件事持续成立，是一种**靠纪律维持的结构隔离**，而不是不可能违反的隔离。
2. **存在一个已构建但未使用的全层泄漏通道**：`packet_builder.py:480-512` 的 `_build_context` 会构建 `context.layer_states`/`context.layer_summaries`，**包含全部五层的当前状态**，并挂在 `AnalysisPacket.context` 字段上。对 `orchestrator.py` 全文 grep `packet.context`/`packet_model.context`，零命中——这个字段现在完全没被读取，因此当前不构成实际泄漏。但它是一颗放好的雷：任何人以后想"方便地"往某层 prompt 里加点上下文，最近的现成入口就是这个已经聚合了全部层状态的字段，一旦被接上就是全层信息秒穿透。
3. 隔离只覆盖"数据"，不覆盖"方法论声明"。`orchestrator.py:4084-4092` 的 v2_contract 明确告诉每层 LLM"其他层负责什么"（静态本体，不是数据），这是合理的，但也说明隔离的边界定义本身依赖 prompt 文本约定，代码只保证了"当前状态数值"不泄漏，没有、也不可能保证"LLM 不会用训练知识脑补其他层现在是牛市还是熊市"。

### 发现 4【中高，已验证】orchestrator.py 是一个 5672 行、170 个方法的单一类，承担了至少 8 类不同职责，其中多类不属于"编排"

`class VNextOrchestrator`（`orchestrator.py:256-5660`）内部方法按职责分类（逐个方法名扫描后归类，已验证）：
- 管线时序控制（`run`、`_run_bridge`、`_run_thesis` 等，约 15 个方法）——这才是"编排器"本职；
- Prompt 组装/裁剪/压缩（`_compose_prompt`、`_compose_layer_prompt`、`_sanitize_prompt_payload`、`_summarize_l4_raw_data_for_prompt`、`_summarize_long_series` 等，约 15 个方法）；
- Schema/合约校验（`_validate_layer_card_v2`、`_validate_bridge_memo_v2`、`_run_schema_guard`、`_validate_counter_thesis_draft` 等，约 8 个方法，`_run_schema_guard` 单方法就近 250 行）；
- 证据登记与核验（`_build_evidence_registry`、`_verify_claim_entry`、`_claim_ledger_publish_gate`、`_claim_specific_counter_refs`、`_claim_specific_falsifiers` 等，约 15 个方法）；
- 文件 IO / 校验和 / 断点续跑（`_save_json`、`_sha256_file`、`_stable_stage_payload_sha256`、`_load_stage_checkpoint`、`_write_stage_manifest` 等，约 12 个方法）；
- 数据归一化（`_normalize_payload`、`_normalize_conflict`、`_normalize_price_reflection_category`、`_normalize_trend` 等，约 25 个方法，多为几行的小函数但数量庞大）；
- 假说竞争与裁决（`_build_hypothesis_competition`、`_dedupe_hypotheses`、`_build_adjudication_change_records` 等）；
- 用户决策档案 / Golden Pit Checklist / 跨 run 回顾（`_load_user_decision_profile`、`_build_golden_pit_checklist`、`_evaluate_metric_predicates`、`_build_run_review_report`、`_build_outcome_review_report`）。

其中"文件 IO/校验和/断点续跑"和"数据归一化"这两类，本质上是独立于"编排"的基础设施关注点，完全可以拆成 `StageIO`/`PayloadNormalizer` 这类无状态工具模块，被 `VNextOrchestrator` 调用而不是内嵌成 170 个方法之一。这不影响功能正确性（我没有发现因为塞在一个类里而产生的 bug），但直接影响可维护性：**任何人想读懂"L1-L5 到底能看到什么"，必须在 5672 行、170 个方法里定位散落的 6-8 个相关方法**，这本身就是认知负担，与"context-first"的架构初衷（降低认知负担）是矛盾的。

模块间依赖关系本身是健康的（已验证，逐文件 grep 内部 import）：`contracts.py` 是唯一的公共基础，不反向依赖任何 sibling；`orchestrator.py` 是唯一的顶层消费者，依赖 `contracts/deep_research_canon/few_shot/inquiry_router/llm_engine/outcome_review/packet_builder/run_review`，没有被这些模块反向导入——**没有循环依赖**。但 `orchestrator.py` 本身是典型的"上帝模块"（god module）：它是全仓库唯一一个同时认识几乎所有其他 `agent_analysis` 子模块的地方。

另外，`src/agent_analysis/vnext_reporter.py`（5019 行）是另一个体量相当的巨型模块，负责纯 HTML 报告渲染，不属于推理链，但同样是"该拆分而未拆分"的证据，说明这不是 orchestrator 孤立的问题，而是这个代码库的通病。

### 发现 5【中，已验证】contracts.py 的 schema 复杂度与实际使用之间有明显落差，但落差集中在少数几个新子系统，不是全面过度设计

`contracts.py` 共 2086 行、69 个 `BaseModel`/`Enum` 类、580 处 `Field(...)` 声明（`grep -c "^class " contracts.py` = 69，`grep -c ": .* = Field(" contracts.py` = 580）。抽查发现两种情况并存：
- **确实在用、且被下游消费**的复杂字段：比如 `EvidencePassport.authority_model`（`contracts.py:138-163` 附近）在真实 run 里对应 43 个 passport 条目，`source_tier` 分布 `{proxy:21, official:4, unknown:4, licensed_provider:1, formal_data_source:3, derived_inference:10}`，`verified=True` 的有 35/43（`output/analysis/vnext/20260709_233816/evidence_registry.json`），这是真实、有区分度的数据，不是空壳字段。
- **构建了但未被消费**的字段：`AnalysisPacket.context`（发现 3 已述）是最典型的例子；`post_run_reflection_library.json`（`orchestrator.py:618-653` 生成）经 grep `src/agent_analysis/vnext_reporter.py`、`legacy_adapter.py`、`main.py` 全部零命中——这是一个被生产出来、写入磁盘、但目前没有任何代码路径读取它的 artifact。

因此"过度设计"的准确定性应该是：**不是 contracts.py 整体过度设计，而是最近新增的几个子系统（受控调查、post-run reflection、部分 Golden Pit Checklist 字段）领先于消费方存在**——先把数据结构和生产端建好，消费端还没跟上。这是渐进式开发中常见的"写多用少"债务，不是设计哲学错误。

### 发现 6【中，已验证】Claim Ledger 的证据核验是真实的结构化核验，不是形式主义的"字段存在性检查"，但"claim-specific"的颗粒度停留在类型级（7 类），不是逐条论断级

`_verify_claim_entry`（`orchestrator.py:2095-2171`）做的事情：把每条 claim 的 `evidence_refs` 与真实 `EvidenceRegistry.passports` 做存在性比对（`orchestrator.py:2096-2097`），检查引用的字段级权限（`field_authority`/`field_usage`，`orchestrator.py:2105-2162`，能识别 `rejected`/`supporting_only`/`validation_only` 等越权情形并触发 `block`），检查是否只有弱证据/衍生证据支撑（`orchestrator.py:2141`）。这比"检查字段是否非空"复杂得多，是真的在做交叉引用校验。真实 run 里 8 条 claim 全部 `verified: True`（`final_claim_ledger.json` 的 `publish_gate.status = "pass"`），说明这次 run 的证据链条经过了这道真实核验且通过。

但 `_claim_specific_counter_refs`（`orchestrator.py:2246-2295`）和 `_claim_specific_falsifiers`（`orchestrator.py:2297-2341`）的"claim-specific"是按 `claim_type`（`market_state`/`valuation`/`timing`/`price_reflection`/`risk_boundary`/`action_translation`，共 6-7 类）分支路由，同一 `claim_type` 下的所有具体论断会拿到同一批候选反证/失效条件池，不是针对"这句话本身"单独推导反证。也就是说核验的深度是真实的，但反证/失效条件的**归因粒度**是类型级而非语句级——这是一个介于"形式主义"和"逐条深度核验"之间的中间态。

### 发现 7【中，已验证】DataIntegrity 发布闸门是真实、有阈值、有硬约束的代码校验，不是自述性质的软指标

`src/core/checker.py:155-421` 的 `DataIntegrity.run()` 实打实做了：未来数据泄漏检测（`_future_date_violations`，`checker.py:126-135`，用 `backtest_date` 与指标里的日期字段比较）、按层最低置信度硬阈值（`MIN_FORMAL_LAYER_CONFIDENCE_PERCENT=50.0`，`checker.py:23`）、发布置信度硬阈值（`MIN_PUBLISH_CONFIDENCE_PERCENT=60.0`，`checker.py:22`）、数据证据合约硬阻断（`hard_evidence_issues`）、跨源估值分歧阻断。`src/main.py:404-457` 确认：一旦 `integrity_report.blocked`，流程会**提前退出，不构建 AnalysisPacket，不跑任何 LLM**，只产出 `pure_data_report`/`data_integrity_report` 并 `raise RuntimeError`。这是真实的硬闸门，不是走个形式。

### 发现 8【中，已验证】单点失败即整体崩溃，没有顶层异常兜底；断点续跑机制是真实的但默认关闭

`_run_stage`（`orchestrator.py:3251-3401`）在 `max_node_retries`（默认 2，`orchestrator.py:266`）次尝试后如果仍未通过 schema/校验，直接 `raise RuntimeError(...)`（`orchestrator.py:3401`）。`src/main.py` 的 `run_pipeline`（373-602 行）和 `main()`（605-621 行）**都没有 try/except 包裹 `orchestrator.run(packet)` 调用**（`main.py:504`）——一旦某个 LLM 阶段用尽重试仍失败（比如两个可用模型都返回不合法 JSON），整个进程直接异常退出，不写 `run_summary.json`，不产出任何"部分完成"的正式总结（虽然已经跑完的阶段产物仍会留在磁盘，因为是逐阶段 `_save_json` 的）。

Counter-Thesis 例外：它单独用 `try/except` 包住 `_run_stage` 调用（`orchestrator.py:1398-1415`），失败后落到确定性兜底 `_build_deterministic_counter_thesis`（`orchestrator.py:1542-1604`），这是本次真实 run 里**实际发生**的路径（`llm_stage_diagnostics.json` 记录两次 `schema_validation_error`，错误信息显示 LLM 把 `independence_boundary` 和 `input_refs` 的类型完全搞反了——该给字符串的给了 dict，该给 list 的给了 dict）。但这种"个别阶段单独兜底、其余阶段直接掀桌子"的不一致处理策略，本身是一种脆弱性：系统对失败的容忍度取决于某个具体阶段有没有被人手工包一层 try/except，而不是有统一的降级策略。

断点续跑（`resume_from_existing`）是真实机制：`_load_stage_checkpoint`（`orchestrator.py:4598-4654`）会校验产物文件的 sha256、payload 的 sha256、`stage_key`/`stage_name` 是否匹配，任何一项对不上就放弃复用、重新跑，这是正确的幂等性设计（不会因为输入变了还错误复用旧结果）。但默认 `resume_from_existing=False`（`orchestrator.py:268`），必须显式传 `--resume-from-existing`（`main.py:82`）才会启用，日常单次运行不会自动受益于这个能力。

### 发现 9【低中，已验证】两层重试机制叠加，逻辑正确但存在冗余

`LLMEngine.call_with_fallback`（`llm_engine.py:267-306`）本身对每个候选模型做 2 次网络级重试（`for attempt in range(2)`，`llm_engine.py:290`），外层 `_run_stage` 又做最多 `max_node_retries`（默认 2）次"重新组 prompt+重新调用"的语义级重试（`orchestrator.py:3282`）。两层重试的失败原因不同（前者是网络/API 失败，后者是 JSON 解析/schema 校验失败），逻辑上不算错，但组合起来意味着最坏情况下一个阶段可能触发到 `模型数 × 2 × 2` 次真实网络调用，且两层重试没有共享退避/日志视角，增加了排查"这次到底重试了几次、为什么"的难度。真实 run 里绝大多数阶段一次成功（`attempts=1`），只有 Final 和 Counter-Thesis 走到了外层重试，说明这不是高频问题，但机制本身有简化空间。

### 发现 10【低，已验证，正面发现】Critic → Reviser 这一段在这次真实 run 里做了真实的认知工作，不是复述

`critique.json` 的 `issues[0]` 精确指出：thesis 的支撑链 2 引用了 `L5.get_qqq_technical_indicators`，但该证据的 `normalized_state='bearish_bias'`（MACD 空头、OBV 流出、ADX 弱），与支撑链描述的"提供下行缓冲、可能支撑价格企稳"**直接矛盾**，并给出具体修改建议。这是需要交叉核对两份不同产物（thesis 的论证 vs L5 layer card 的具体指标状态）才能发现的问题，不是简单复述。`analysis_revised.json` 的 `revision_summary` 显示 Reviser 确实针对性回应了这条批评（强化流动性到估值传导链、下调对低置信度盈利修正数据的依赖权重、补充信用持续恶化场景），`main_thesis` 文本在修订前后有实质性差异（新增了"利率数据缺失使传导路径不完整"这一关键限定）。**这是本次审计里对"Critic/Reviser 是否只是形式流程"这个问题最直接的反证**：至少这一次，这两步确实改变了最终表述的内容和严谨度。

---

## ④ 总判断：分层判断，不是简单的"保留"或"推倒重来"

不和稀泥，明确立场：**核心推理骨架保留，治理外围子系统砍掉或重做，orchestrator.py 必须拆分。**

- **保留（结构性证据支持这些是真实机制，值得继续投入）**：
  - L1-L5 payload 级隔离的两道过滤（发现 3）——这是"Context-first"里少数被代码真正兑现的承诺，值得保留并且应该补一条自动化测试防止 `AnalysisPacket.context` 那类字段被误接入 prompt。
  - DataIntegrity 发布闸门（发现 7）——真实、有硬阈值、正确短路后续流程。
  - Claim Ledger 的证据存在性/权限核验逻辑（发现 6）——真实交叉核验，比大多数"形式主义合规"项目做得扎实。
  - Critic → Reviser 这条链（发现 10）——有真实 run 证据支持它产生实质改动。
  - 断点续跑的 sha256 校验设计（发现 8 后半）——设计正确，只是没默认打开、没被日常使用。

- **砍掉或重做（当前投入产出比很差，且是"偶然复杂度"而非"本质复杂度"）**：
  - 受控调查反馈环（InquiryRouter → AgentSpec → InvestigationReport → Bridge v2）：发现 1 证明它在数学上不可能改变任何判断。要么给它接一个真实的信息获取能力（哪怕只是"重新读取一次更严格过滤的数据"这种最小真实调查），要么直接删掉，用一行"本 run 未做补充调查"的静态说明代替这几百行机制。**不应该让它继续以"看起来在工作"的姿态占据代码和 token 预算**。
  - Bridge v2 作为独立"第二次综合"的定位需要改名或合并：它现在就是纯 Python 对 Bridge v1 字段的重新打包（发现见 ②），继续叫"Bridge v2"容易让人误以为发生了第二次 LLM 综合。
  - Counter-Thesis 的确定性兜底文本（`_build_deterministic_counter_thesis`）质量偏低（发现 2 呼应），且这次真实 run 就命中了兜底路径。要么修 CounterThesisDraft 的 schema 让 LLM 更容易一次通过，要么承认"两次都失败就用模板"这件事本身需要被上抛为需要人工关注的信号，而不是安静地继续往下走生成一份"完整"报告。
  - `post_run_reflection_library.json` 这类"生产了没人读"的 artifact：要么接上消费端（比如真的用于生成下次 run 的 few-shot 或测试用例），要么先不生成，减少认知噪音。

- **必须重写（不是内容问题，是结构问题）**：
  - `orchestrator.py` 本身。5672 行、170 个方法、8 类混装职责（发现 4）已经超过任何人能一次性建立完整心智模型的规模。建议按发现 4 里的职责分类拆成至少 4-5 个模块：`stage_runner`（LLM 调用+重试+校验的通用循环）、`prompt_composer`（现在的 `_compose_*`/`_sanitize_*`/`_summarize_*` 一族）、`claim_verification`（现在的 `_build_evidence_registry`/`_verify_claim_entry`/`_claim_*`一族）、`stage_io`（`_save_json`/`_sha256_file`/checkpoint 一族）、`payload_normalizer`（25 个 `_normalize_*` 方法）。拆分本身不改变行为，是纯粹的可维护性重构，但对"这套系统到底在做什么"这个问题的可回答性影响很大。

---

## ⑤ 给总报告的核心启示（可直接引用）

1. **"L1-L5 运行时隔离"这个卖点基本兑现**：`orchestrator.py` 里有两道独立的代码级过滤（按 layer 分组 + 按指标 canon 二次核对）把其他层数据排除在每层 prompt 之外，这不是靠 prompt 文案自觉，是结构性代码保证——但保证的边界是"当前进程内没有代码路径引用其他层数据"，而不是进程/权限级隔离，且已经存在一个构建好但幸好未接入 prompt 的全层数据字段（`AnalysisPacket.context`），是个需要立刻加测试防守的雷。

2. **架构里最贵的一块——受控调查反馈环——目前是纯摆设**：代码可以证明它数学上永远不可能改变任何判断（`is_deterministic_stub` 恒真 → `changed` 恒假），真实 run 也确认 `changed_judgment_count: 0`。这是"精密但空转"的教科书案例：工程完成度高（合约、路由、预算、越权读取拦截都做了），但对最终结论的边际贡献是零，建议优先砍掉或做成真正有效的机制，而不是当作"已完成"继续维护。

3. **最终裁决阶段（Final Adjudicator）并不总是产生新内容**：真实 run 证据显示它的 `time_horizon_summary` 和 `must_preserve_risks` 是对上游 Reviser/Risk Sentinel 输出的逐字复制，真正的新增价值集中在 `quality_gate`（发布审批决策）。这意味着"六步治理链"里至少有一步的 LLM 调用大部分 token 花在搬运而非裁决，值得重新评估这一步是否需要整段重写 prompt，还是应该把"复制不变字段+只让 LLM 写 approval 决策"这个分工在代码层面显式化（这样能省下大量 token）。

4. **不是所有治理步骤都是走过场**：Critic 在真实 run 里指出了一个需要跨文件交叉核对才能发现的证据矛盾（thesis 引用的技术指标状态实际与其论点相反），Reviser 确实针对性修订了主论断文本。这说明问题不在于"要不要有对抗性检查这个环节"，而在于"哪些具体环节被验证过真的有效、哪些只是名字像有效"——本报告为每个环节都给出了这个区分，总报告不应该笼统地肯定或否定整条链，要按环节分别对待。

5. **orchestrator.py（5672 行/170 方法）和 vnext_reporter.py（5019 行）是同一种病的两个部位**：职责混装导致的"上帝模块"，不是循环依赖或架构分层错误（依赖图本身是干净的树状结构，contracts.py 在底层，orchestrator.py 在顶层，没有反向依赖）。这是可以纯靠拆分方法归类解决的可维护性债务，不需要推翻整体架构设计，但如果不做，下一次想验证"某条隔离/核验承诺是否兑现"的审计成本会持续上升——这次审计定位关键方法平均花了不少来回搜索时间，本身就是证据。

---

## 附：调查过程中的路径核实说明

- 任务给定的 `output/analysis/vnext/20260709_233816/` 真实存在，本次全部真实 run 证据均取自此目录，未替换为其他 run。
- `src/core/checker.py` 存在且确认为 DataIntegrity 发布闸门实现（对应任务里提到的"DataIntegrity 发布闸门"）。
- 任务提到的 `src/agent_analysis/llm_engine.py`、`prompt_inspector.py`、`legacy_adapter.py` 均存在，本报告对 `llm_engine.py` 做了针对性核实（`call_with_fallback` 的重试语义），`prompt_inspector.py`/`legacy_adapter.py` 因时间预算未做逐行深读，仅确认其模块边界（无 sibling 内部 import，属于下游消费/审计工具，不在推理主链的关键路径上）——这是本次审计明确未覆盖到底的部分，如需更高置信度结论应补充复核。
- `src/state_ledger.py`、`src/agent_analysis/outcome_review.py` 均存在且路径与任务描述一致；`state_ledger.py` 全文已读，`outcome_review.py` 因时间预算只做了消费关系核实（被 `orchestrator.py` 的 `_build_outcome_review_report` 调用），未逐行核实其内部评分算法的可靠性，这也是未完全覆盖的部分。
- `contracts.py` 实际为 2086 行，与任务描述一致；`orchestrator.py` 实际为 5672 行，与任务描述一致。
