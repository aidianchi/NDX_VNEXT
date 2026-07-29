# vNext 工作记录

阅读方式：最新完成事项放在最上面。这里记录已经完成的事，是**历史**不是状态；"某件事做没做完"的唯一权威是 `现在.md`。
关闭某项待办时，在当日条目里写 `【关闭 T##】`——编号就此永久退役，不得复用。
本文件只保留最近三个月；2026-06-30 及更早的条目见 `docs/archive/2026-04_2026-06_WORK_LOG.md`（含其中的关闭记录）。

---

## 2026-07-29

### 【关闭 T29】严格模式离线 schema 体检：8 个契约扫完，4 个今天就能开

**改了什么／为什么**：严格模式已被真实 run 证伪两次，两次都栽在 schema 转换上。这类问题可以被程序穷举，不该拿花钱的真实跑去撞。离线扫全部 8 个 stage 契约，共 7 处不合规，**全是同一种**——`Dict[str, Any]` / `extra=allow` 生成的"没有属性的 object"，严格模式实测直接报 `An object with no properties is not allowed`。

**结论**：`BridgeMemo` / `ThesisDraft` / `EventInterpretationCard` / `EventSectionSummary` 零问题，今天就能开。`LayerCard`(1) / `CounterThesisDraft`(1) / `FinalAdjudication`(3) / `AnalysisRevised`(2) 各有命中，**其中 6 处是代码事后填的诊断字段**（`token_usage` 甚至在 `orchestrator.py:7187` 被强制置空），本就不该出现在给模型的 schema 里；只有 `CoreFact.raw_data` 是模型真会填的，需要权衡。

**否决了什么**：没有顺手删掉那 6 个字段。删是对的，但那是"哪些字段该进模型 schema"的设计决定，且当前只有桥接要开严格模式（零问题），不构成阻塞——留给用户在扩范围时一并定。

**红灯测试在哪**：`tests/test_governance_input.py::test_strict_tool_schema_meets_provider_constraints`（关掉 sanitizer 的 `additionalProperties` 即红）与 `::test_strict_tool_schema_free_form_objects_are_registered`（登记表少一条即红，且过期登记也报错）。登记表 `llm_engine.STRICT_SCHEMA_FREE_FORM_OBJECTS` 逐条写清"由谁填"——那是决定修法的关键信息。

**验证**：全量 `--cache-clear` 1024 passed。

---

### 甲的规格漂移回归修复 + 体检跑三个发现 + 文档纪律换挡

**改了什么／为什么**

- **自动规格必须标注嵌套子字段的类型**（`ae13050`、`233dfe2`）。只写栏目名不写填法，比压根不提更危险——它把模型从"不填"推到"乱填"。真实代价：run `20260728_222759` 的 L1 两次尝试全废、整跑死在第一站（`magnitude` 填成 -4.9、`raw_data` 填成一句话）。覆盖面从 Literal/dict 扩到 list，并补上第二层（`ClaimLedgerEntry` 的三个枚举此前连字段名都不可见）。
- **事件引用前缀陷阱**：`event:` 前缀 + `[card:<id>]` 写法互相卡死，`event_section_summary` 连挂四跑、每次静默吞掉报告整节。修法是 payload 直接给现成引用串、报错带合法示例；**否决了去前缀容错**——那等于默许写错还把错误藏起来。
- **冲突编号通道**：`Conflict` 契约根本没有 `conflict_id`，闸门只能拿被正方改写过的类型名认亲，于是谎报"高严重度冲突被抹平"而冲突一条没丢。修法是补编号通道；**否决了放宽闸门**——放宽等于拆掉"冲突是资产"这条边界的守卫。
- **CLAUDE.md 换挡**：人话版从"内容清单"改成"写法要求"（用户自行翻译的版本明显更好，差别在写法不在内容）；新增执行纪律"闸门不判意思"；`WORK_LOG` 从"只增不改"改为按月滚动归档 + 条目写决策不写过程。
- **一条"常见误判"被证伪并改写**：原文说"报告某节留空 = 宁缺毋滥闸门在工作"。今天证明那一节连空四跑不是闸门尽职，是模型被规则卡死。原文会让下一个人看到空白就安心走开。

**红灯测试在哪**

- `tests/test_governance_input.py::test_field_spec_exposes_constrained_nested_subfield_types` —— 穷举所有深度的受限子字段；**期望值刻意不引用实现常量**（初版从 `_CONTRACT_SPEC_MAX_NESTED_DEPTH` 推导，把常量调小测试就自己闭嘴，是在"红灯点不亮"时发现的）。
- `tests/test_vnext_orchestrator.py::test_schema_guard_matches_retained_conflict_by_upstream_conflict_id` / `test_schema_guard_flags_missing_conflict_id_as_possible_id_gap` / `test_event_section_summary_errors_carry_prefixed_citation_example` / `test_event_section_summary_payload_hands_model_a_ready_made_citation`
- `tests/test_docs_consistency.py::test_task_ids_are_never_reused` 扫描范围扩到 `docs/archive/**/*WORK_LOG*.md`，否则每轮转一次归档就静默出现一段可复用编号区间。

**验证**：全量 `--cache-clear` 1022 passed。体检跑 23 站 20 站一次过。甲的实测结论：净收益无膨胀——五层 `magnitude` 填充 0/57 → 34/43，五层响应合计 89583 → 81975（−8.5%）；此前"甲导致输出膨胀 46%"的数字基准选错（拿同一次失败跑的两次尝试对比），作废。

**归档动作**：WORK_LOG 2026-06-30 及更早的 39 个条目整段搬入 `docs/archive/2026-04_2026-06_WORK_LOG.md`，55 个条目逐条哈希比对确认逐字未改，21 条关闭记录一条不少。根目录从 3786 行降到 1164 行。历史条目**不做追溯性瘦身**——"写决策不写过程"只对将来生效。

---

## 2026-07-28

### 【关闭 T28】【关闭 T19】越有争议的假说越不被要求回应：触发集合倒置修复 + 真实 run 双验收

**病机**：`_run_hypothesis_competition`（`orchestrator.py:2290-2350`）只要 `_build_adjudication_change_records` 产出任何降级记录（受控调查提出挑战，或存在 `fallback_warnings`），就把**全部**假说（含反方、含 base）统一改判 `kept_unresolved`、`leading_hypothesis_id=""`；而 `_validate_thesis_hypothesis_responses` 只收集 `status == "candidate"`，于是 candidate 集合归零、合约整体空转。四次真实 run 里三次 candidate 数为 0。**逻辑正好反了：越有争议、越需要被正面回应的假说，越容易被降级，也就越不会被要求回应。**

**设计裁决**：触发集合从 `status == "candidate"` 扩大为 `status != "downgraded"`（`candidate` / `leading` / `split` / `kept_unresolved` 全要求回应）。`CompetingHypothesis.status` 没有 `"rejected"` 取值，HANDOFF 说的"非 rejected"落到代码上就是"非 `downgraded`"——它是唯一表示"已被正式裁决出局"的状态。`kept_unresolved` 的语义是"没有胜出、张力未解决"，不等于"不需要被回应"，所以合格回应允许 `absorb_partially`，**不强求** `accept_and_revise` 或 `reject`；否则"冲突是资产"会退化成逼模型对每条争议硬下结论。`reject` 仍必须带合法 `evidence_ref`。`leading` 也纳入必答集合（它通常是 thesis 自己的主线，显式声明"为什么接受"便宜且可审计）。

**前置条件先验证再动手**（不做这步就是重演 T19）：`prompt_audit/thesis/attempt_1.payload.json` 实测 `synthesis_packet.competing_hypotheses` 逐条带 `hypothesis_id` + `status` + 正文，2/2 无截断——模型看得见它必须回应的东西。`_carry_forward_reviser_thesis_fields`（`orchestrator.py:5226`）只在键完全缺席时继承、键存在（含空列表）交给 validator 硬拦，与新合约互补不冲突。断点续跑路径（`orchestrator.py:3992`）用同一 validator，一并收紧。

**同步登记**：`STAGE_CONTRACT_PROMPT_REQUIREMENTS` 的 `thesis` / `reviser` 各增 `kept_unresolved` / `downgraded`；`thesis_builder.md`「对竞争假说的强制回应」与 `reviser.md`「竞争假说回应纪律」同步改写（含"kept_unresolved 可用 absorb_partially 承认张力未解决"）。

**顺带定位的既有缺陷**：run `20260719_130534` 里 thesis 写了 2 条回应（`accept_and_revise` + `absorb_partially`），`analysis_revised.json` 的 `revised_thesis.hypothesis_responses` 却是空的——reviser 整段丢掉且无人报警。四次 run 的 revised 全空。已加专测锁定"thesis 答了、reviser 交空列表"这一形态。

**红灯实证**（`git stash` 旧 orchestrator 对照）：`test_kept_unresolved_hypotheses_with_zero_responses_are_now_blocked` 改前断言失败（旧逻辑放行）、改后拦下；`test_reviser_kept_unresolved_responses_explicitly_emptied_still_fails` 改前 `DID NOT RAISE RuntimeError`、改后抛出。另有 `absorb_partially` 正向用例与 `reject` 无证据回归用例。

**真实 run 验收（`20260728_110702`，用户批准花费）**。该 run 因终审站崩溃走了一次断点续跑，**续跑重跑了 counter_thesis 起的全部叙事站**（`stat` 实测：`bridge_0.json` 停在 11:18 被复用，`counter_thesis.json` / `hypothesis_competition.json` 11:46、`synthesis_packet.json` 11:49、`thesis_draft.json` 11:50、`analysis_revised.json` 11:55 全部被重写），所以本 run 留下了**两批独立的验收样本**，两批都成立：

| 项 | 首跑（已被覆盖，仅存于当时读数） | 续跑后（当前 artifacts，可复核） |
|---|---|---|
| 竞争假说 | 3 条全 `kept_unresolved`（`bridge_v2`×1 + `counter_thesis`×2，含一条"反方的反方"） | 2 条全 `kept_unresolved`（`bridge_v2`×1 + `counter_thesis`×1） |
| `thesis` | `attempts=1`，回应 3/3 | `attempts=1`，回应 2/2 |
| `analysis_revised` | `attempts=1`，回应 3/3 完整保留 | `attempts=1`，回应 2/2 完整保留，无 `degraded_fallback` |
| verdict | `accept_and_revise`×1 + `absorb_partially`×2 | `accept_and_revise`×1 + **`reject`×1** |
| 证据 | 每条 3-4 个真实 ref | 每条 **4** 个 ref，逐条比对 `evidence_index` **零越界** |

两批合起来覆盖了 HANDOFF 全部验收面：`absorb_partially`（承认张力未解决、不逼硬下结论）由首跑证实；**`reject` 必须带合法反证 evidence_ref 这一支由续跑真实触发并通过**——这是 HANDOFF「回应内容不是敷衍」那条标准第一次在真实 run 里被考到。

**thesis 与 reviser 在两批里都是一次通过，扩大合约零重试成本**——"改完每次都崩"的风险判断被真实数据否定。同时这是 T19「漏字段」修复**第一次拿到真实 run 实证**（此前四次 run 的 revised 全空，合约根本没被考到），故一并关闭 T19。

**附带记录**：`--resume-run-dir` 的检查点复用只到 bridge 为止，counter_thesis 之后的叙事站全部重跑（本次 4 次真实 LLM 调用）。续跑会**静默覆盖**已验证过的产物——这次首跑那批 3 假说样本就是这样消失的。以后拿真实 run 做验收时，结论要以最终落盘的 artifacts 为准，中途读到的数不能当最终证据。

### 单一事实源全仓审计：修掉一个活跃 bug + 两处名单收敛为一份

用户提出的排查方向：把"同一件事实分两处各存一份、没人负责对账"这类缺陷穷举出来。审计全文 `investigation_reports/20260728_single_source_audit/FINDINGS.md`。

**已修 1 —— `usage_rank` 漏收 `validation_only`（唯一一条活跃 bug）**：`_field_authority_from_payload` 里的 `usage_rank` **既当排序表又当白名单**，而 36 行之后的 `_field_authority_usages` 另写了一份 `allowed` 集合，两份已漂移。实测复现：输入 `{"usage": "validation_only"}` → 输出 `{"usage": "audit_only"}`。`tools_L4.py` 有 6 处真实产出该等级（Wind PE 与 Yahoo 交叉校验等），下游 `packet_builder.py:796,831` / `vnext_reporter.py:4331` 把它与 `core_allowed` 同等对待——标签被改写后，报告里"这条证据为何被降级"的审计文案与工具本意对不上。当时未翻转 verified/downgraded 判定，是因为两者恰好同档，**侥幸不是设计保证**。既有两条 claim_gate 测试手工构造 passport 绕过了该函数，所以一直显示通过、其实没保护真实路径。修法：合并为唯一常量 `METRIC_AUTHORITY_USAGE_RANK`，白名单由其键派生；`validation_only` 与 `audit_only` 同档，**只恢复标签真实性，不改变任何既有强弱判定**。

**已修 2 —— 五类价格反映名单两处硬编码**：`orchestrator.PRICE_REFLECTION_CATEGORIES` 键与 `run_review.REQUIRED_PRICE_REFLECTION_CATEGORIES` 各存一份。依赖方向核实为 orchestrator → run_review 单向，`contracts.py` 是唯一不造成循环导入的落点。新增 `contracts.PRICE_REFLECTION_CATEGORY_KEYS` 为唯一名单，run_review 派生，orchestrator 富字典由测试强制键一致。

**红灯实证**：`test_metric_authority_usage_vocabulary_has_exactly_one_source`（删掉 `validation_only` 一行即报 `assert 'audit_only' == 'validation_only'`）、`test_price_reflection_category_list_has_exactly_one_source`（另含"每类必须写全 target/label/hint"，防代码补齐拼出空文案）。

**已核实、留给用户决定（未动手）**：
- **T20 被坐实**：`tools_L4.py` 7 处 MetricAuthority 里 5 处 key 即真实字段名，2 处（`get_m7_buyback_flow` / `get_m7_capex_cycle`）用概念分组名。已复现具体后果——`orchestrator.py:2892-2893` 按概念名取 `value_payload.get(field)` 恒为 `None` → `evidence_value_missing` + `verified` 恒 `False`，**底层数据完好也被永久判定证据缺失**。不再是理论担忧。
- **`CoreFact` 三个低填充字段**：`historical_percentile` / `trend` / `magnitude`。四个真实 run 填充实测 8/57、0/60、1/54、0/39（`historical_percentile`），波动 0%~15%。**订正此前两处表述**：(1)"1/54 与 0/60"是同一字段在两次 run 的填充数，不是两个字段各一个数；(2)"只有 magnitude 有消费方"不准确——三者在 `legacy_adapter.py:268,294,328` 都被读取（vNext 主链无据此下结论的逻辑这一点仍成立）。**新增变量**：当日上线的 `_render_contract_field_spec` 已把这三个字段列进每次层分析 prompt，净效果是成本还是收益需下一次真实 run 的填充率对照判定，审计报告里已留基线表。

**登记在案暂不处理**：`{"high","medium","low"}` 在 orchestrator 内 4 处重复字面量（纯维护负担）；`AdjudicationChangeRecord.old_status/new_status` 为自由 `str` 且写入过枚举外的值，但全仓无读取方。

**阴性结论**：`CompetingHypothesis.status` 语义判定**没有第四处**（覆盖 `src/`、`tests/`、`scripts/`、`console_run_all.py`、`legacy_adapter.py`）；本次审计**没有发现"会让真实 run 崩"级别的新问题**。

**验证**：全量 `--cache-clear` **1017 passed**。

### 断点续跑只复用到 bridge：反方站从未接进检查点机制

用户指出 `--resume-run-dir` 的实测行为与其帮助文字"verified stage checkpoints are reused"不符，要求裁决修文档还是修行为。**裁决：修行为。** 帮助文字描述的是设计意图，反方站只是从来没接上。

**根因（单点）**：`counter_thesis.json` 经 `_save_json` 直接落盘，`_record_stage_artifact` 未带 `stage_key` / `payload`——实测 manifest 里 `stage_key=None, payload_sha256=None`；`_build_counter_thesis` 中也没有 `_load_stage_checkpoint`。其余叙事站（bridge/thesis/reviser/final/layer cards）两者俱全。**一条缺失引发整条级联**：续跑必重跑反方 → `competing_hypotheses` 变 → `synthesis_packet` 变 → thesis 检查点的 `payload_sha256` 失配 → thesis / reviser / final 依次重跑，并静默覆盖已产出的产物（真实事故 run `20260728_110702`：首跑那批 3 条假说的验收样本因此永久消失）。

**修复**：
1. `_build_counter_thesis` 开头加 `_load_stage_checkpoint("counter_thesis.json", ...)`；结尾把 payload 与 fallback 标记存 `self._last_counter_thesis_payload/_fallback`，由 `_run_hypothesis_competition` 落盘后带 `stage_key` + `payload` 补记（不重算 payload，避免两处构造逻辑分叉——正是本轮反复治理的那类重复）。
2. `_record_stage_artifact` 新增 `checkpoint_reusable` 覆写参数；**走了确定性兜底的反方稿登记为不可复用**——模板凑数稿不是"已验证"结果，续跑必须重试而不是把它永久固化。
3. `_record_stage_artifact` 在续跑模式下、产物 sha 变化时写入 `overwritten_in_resume={previous_sha256, previous_updated_at}`。**行为不变**（重跑就该写新结果），但"我当时读到的那份还在不在"从此可查。sha 未变时继承既有痕迹——同一份产物会被登记两次（`_save_json` 先无 stage_key 记一次、调用方再补记一次），不继承就会把留痕自己擦掉。

**红灯实证**：移除 counter_thesis 检查点 → `test_orchestrator_runs_full_chain_with_fake_llm` 报 `AssertionError: assert 'running' == 'resumed'`。新增 `test_counter_thesis_checkpoint_is_reused_on_resume`（正常稿可复用 / payload 指纹变则拒 / 兜底稿拒）与 `test_resume_overwrite_of_verified_artifact_leaves_a_trace`。

**过程中两处自我更正（如实记录）**：(1) 首次写的红灯测试因 `-k` 过滤未匹配而**从未被执行**，差点把没跑过的测试当实证；(2) 该断言本身写错了——断言反方站被复用，但该夹具下反方必然走兜底，而"兜底稿不得复用"正是我自己刚定的规则，**拒绝复用才是正确行为**。已改为断言"必须拒绝复用"，另写成功路径用例。

### 合约治理机制改造：字段规格由契约生成（甲）+ 登记不再靠人记得（丙）

用户读完当日汇报后的裁决："三件套（合约写在代码 → 说明书写在 prompt → 关键词登记表对账）不优雅"。诊断成立：登记表并没有消除重复，而是把两份变成三份，且只查关键词在不在、不查解释对不对，还得靠人记得去登记。据此做两处改造，用户批准甲、丙，明确否决乙（让 validator 自带 spec 句并注入 prompt——会把手写说明书改成机器拼装，牺牲这个项目赖以产出质量的说明书语气与分寸）。

**甲：`_compose_prompt` 注入由契约生成的「输出字段规格」。** 新增 `_render_contract_field_spec()` + `_render_contract_type()`，遍历 `model_cls.model_fields`，把每个字段渲染成"名称（必填/可选）：形状 —— description"。形状渲染区分对象 / 数组 / 标量 / Literal / Enum / 可为 null，并对嵌套模型展开一层子字段名（上限 8 个）。Response Rules 追加一条优先级声明："形状以规格为准，正文示例只解释语义"。

**这从结构上根除了形状漂移这一类事故**：只要字段在 pydantic 模型里，它就一定出现在 prompt 里。当天崩掉的 `claim_ledger` 现在渲染为 `对象 ClaimLedger{schema_version, generated_at, effective_date, entries, publish_gate, …} 或 null`——模型不可能再猜成裸数组；20260724 那次 counter_thesis 猜错字段名烧掉 28 万 token 的事故同理。行为规则（"必须逐一回应非 downgraded 假说"）不在覆盖范围，仍由手写说明书 + 登记闸门承担，这是刻意的分工。体积成本：FinalAdjudication 2588 字符、ThesisDraft 2074、BridgeMemo 2173，约占各站 prompt 的 3%。

顺带订正 `ThesisDraft.hypothesis_responses` 的 `description`——T28 之后它仍写着"对每个 candidate 竞争假说的逐一回应"。以前这句只在代码里，现在它直接进 prompt，准确性成了硬要求。

**丙：登记表改由反射闸门守。** 新增 `test_every_validator_bearing_stage_is_registered_in_prompt_requirements`：用 AST 静态扫描 `orchestrator.py` 里所有 `self._run_stage(...)` 调用，凡带 `validator=` 且 `stage_key` 为字面量的，必须在 `STAGE_CONTRACT_PROMPT_REQUIREMENTS` 里有登记；`stage_key` 为运行时拼接的调用点必须落在新增的 `DYNAMIC_STAGE_KEY_CALL_SITES` 豁免名单里并写明理由（豁免必须看得见，不能被扫描器沉默跳过）。另加 `test_registered_prompt_requirement_keywords_are_not_vacuous` 防止用空串/单字符关键词骗过闸门。

**闸门一上线立刻查出三个漏登记的 stage**：
- `event_card_interpreter` / `event_section_summary`：说明书本来就写了对应规则（"该事件可能通过"前缀、`[card:...]` 引用格式与 2-5 张区间），纯属漏登记，补登记即可。
- **`bridge` 是真缺口**：`_validate_bridge_memo_v2` 硬性要求每条 `resonance_chains` 的 `confirming_indicators` 与 `falsifiers` 非空，而 `cross_layer_bridge.md` 里这两个词**各出现 0 次**。真实代价当场可查——run `20260728_110702` 的 bridge `attempts=2`，报错正是 `resonance_chains[resonance_chain].confirming_indicators must not be empty`，白烧一次 11 万 token 的调用。已在 `cross_layer_bridge.md`「必须遵守」补写三条（typed_conflicts 三必填、resonance_chains 五必填含两条易漏项的语义解释、transmission_paths 的 path_id 唯一），并登记。

**红灯实证**：把 `bridge` 登记临时删掉，闸门当场报 `这些 stage 挂了 validator 却没有登记：{'bridge': 3990}`。

**一次操作事故（如实记录）**：验证红灯后我用 `git checkout src/agent_analysis/orchestrator.py` 去"恢复"，把该文件上全部未提交改动一次性冲掉（T28 触发集合、reasoned_verdict 分组解析、claim_ledger 登记、甲、丙五处）。其余文件未受影响。已按记录逐处重建并由全量测试确认无丢失。**教训：working tree 有未提交改动时，`git checkout <file>` 是不可逆丢弃，不是恢复；临时试验必须用 `git stash push <file>` + `git stash pop`。**

**验证**：全量 `--cache-clear` **1013 passed**。

### 报告层的同一处逻辑倒置：越有争议的假说越不会出现在报告里（T28 的第三处）

用户读完 T28 汇报后问"主线对反方的回应能不能进报告"。查下来这不是新功能，是**同一个 bug 的第三处**：`vnext_reporter._hypothesis_competition_block`（`vnext_reporter.py:4514`）也用 `status == "candidate"` 过滤假说。而 `_run_hypothesis_competition` 一旦触发降级就把全部假说改判 `kept_unresolved`——于是这一节在真实 run 里长期只剩 counter_thesis 单独成块，读者只看得见反方说了什么，看不到主线逐条怎么答的。**逐条回应的渲染代码（verdict 标签 + reasoning 正文 + 证据 chips）一直都在，只是从不执行。**

真实样本：run `20260728_110702` 两条假说全 `kept_unresolved`，修复前该节渲染出的字面结论是"**本轮没有结构化竞争假说。**"——明明有两条。

**修复**（与合约层口径统一）：
- 过滤条件改为 `status != "downgraded"`。
- `include_leading=True` 的调用点（`vnext_reporter.py:4718`）此前靠"只有 candidate 才进 cards"隐式避免重复；放宽后领先假说会同时出现在独立卡和 cards 里，故显式把 `leading_hypothesis_id` 从 cards 列表排除。
- 卡片行标题从写死的「暂不采纳」改为「主线怎么回应」（有回应时）。旧标题在触发集合放宽前只可能配 candidate，放宽后会承载 `accept_and_revise`，把"采纳"渲染成"暂不采纳"；verdict 本就单独显示在卡片标签上，正文行保持中性即可。

**红灯实证**（`git stash` 旧 reporter）：新增 `test_brief_stress_section_shows_kept_unresolved_hypotheses_and_their_responses`，改前渲染出 `本轮没有结构化竞争假说。`、断言失败，改后两条 kept_unresolved 假说各带回应正文、`downgraded` 那条被正确排除。既有 `test_r2_stress_section_uses_r7_hypothesis_response` 同步改为断言新标题。

**版式核对**：重新生成 brief 后该节纯文字 1067 字，占全篇 64132 字的 **1.7%**；全篇既有 70 个 `<details>` 折叠块，该节不折叠不构成版面压力。是否折叠交用户裁决。

全量 `--cache-clear` **1009 passed**。

### 终审站两处规格漂移（本次真实 run 现场暴露，其中一处是 2026-07-27 收紧的真实回归）

`20260728_110702` 首次跑到终审站硬崩、无产物无报告。两个独立崩因，都是同型病（合约写在代码里、说明书没写）：

1. **`claim_ledger` 形状**：`final_adjudicator.md` 里该字段 grep 命中 **0 次**，契约却要求 `Optional[ClaimLedger]`（对象）。模型只能猜，猜成裸 `List[ClaimLedgerEntry]`，第一次尝试即被 pydantic 拒。修：`FinalAdjudication` 增 `model_validator(mode="before")` 把裸列表补回 `{"entries": [...]}`（每个条目仍逐字过 `ClaimLedgerEntry`，缺必填照拒）；`final_adjudicator.md` 补 `## claim_ledger` 一节含 JSON 示例与"宁可整个不写也别写错形状"；`STAGE_CONTRACT_PROMPT_REQUIREMENTS["final"]` 追加 `claim_ledger`。

2. **`reasoned_verdict` 逗号合并引用——2026-07-27 收紧的真实回归**。线上原文：`reasoned_verdict cites refs outside evidence_index: ['L1.get_10y_real_rate, L4.get_equity_risk_premium#level', 'L3.get_advance_decline_line, L5.get_obv_qqq']`。两条 ref 都合法，模型只是把它们逗号合并进同一个方括号；`re.findall(r"\[([^\[\]]+)\]")` 把整串当成一个 ref，判越界，重试两次后整跑崩。**这是把"至少一条引用"收紧为"至少三条不同引用"之后的第一次真实 run，收紧恰好把模型推向了这种写法。** 修法不是把计数退回去：新增 `_reasoned_verdict_bracket_groups()` 按 `[,，、;；]` 拆分组内内容（每一段仍要逐字过 `_resolve_claim_evidence_ref`，不放松任何 ref 合法性），`_validate_reasoned_verdict_refs` 与 `_annotate_reasoned_verdict_refs` 共用；计数条件同时改为 `方括号组数 ≥ 3 且不同引用 ≥ 3`——后者比原"3 条不同引用"更贴 `final_adjudicator.md:244` 原文（"三条主要理由每条必须至少带一个方括号"），顺带堵住"单方括号塞三条"这个新洞。说明书补"一个方括号只放一个 ref"。

**红灯实证**：`git stash` 旧 orchestrator+contracts，两条新测试分别报出**与线上逐字相同**的 `outside evidence_index` 串、以及 `ValidationError: claim_ledger`；恢复后全过。

**断点续跑救回该 run**（`--resume-run-dir`，复用已验证检查点，只重跑终审）：`final_adjudicator attempts=1` 一次通过，`claim_ledger` 8 条 entries，`reasoned_verdict` 1174 字符 / **11 个方括号组、每组一条 ref**（说明书修改生效，模型不再逗号合并），`approval_status=approved_with_reservations`，native brief / workbench / prompt inspector 全部产出。`event_section_summary` 仍 `failed`——是"宁缺毋滥"闸门的既有正常行为（见 `CLAUDE.md` 常见误判），非本次引入。

**验证**：全量 `--cache-clear` 1001 → **1008 passed**，零回归。

### 【关闭 T27】`price_reflection_map` 倒向"已反映"：不是缺陷，是实验做错了站点——受控重采样反转了原假设

**先纠正上一条记录里的实验方法。** 2026-07-27 条目末尾"A/B 两组共 6 次采样全部为 0"这个证据**不成立**：那 6 次采样打在 **thesis** 站点，而 `price_reflection_map` 是 bridge 站点生成、thesis 与 final 逐字继承的（三份产物实测完全一致）。在 thesis 重采测到的是"继承是否稳定"，不是"判断是否稳定"。真正产生判断的 bridge 站点，两次 run 实际上只有 n=1 对 n=1。

**HANDOFF 的优先假设也被证伪**：`_ensure_price_reflection_categories`（`orchestrator.py:7272`）补齐缺失类别时默认写 `reflected_state="unclear"`，不是任何"已反映"值；两次 run 的 `normalization_notes` 都没有 `price_reflection_categories_added_by_code`，五类全是模型原生输出，代码没插手。

**"输入瘦身削薄了 bridge"这条线索同样证伪**：`NARRATIVE_STAGE_PROMPT_DROP_FIELDS`（`orchestrator.py:238`）只有 `thesis` / `counter_thesis` 两个 key；`_sanitize_prompt_payload` 的 `bridge` 分支（`orchestrator.py:5885`）只调 `_strip_empty_event_prompt_fields`，无任何裁剪。两份 `prompt_audit/bridge/attempt_1.prompt.txt` 从开头到 `## Runtime Input` 的前 10888 字符**逐字节相同**。两次 run 之间也没有任何代码提交（07-25 全天仅 `9f8d484`，12:22，早于两次 run 且不涉 bridge）。

**受控重采样实验（真实 API，用户批准后执行）**：直接回放两份已落盘的 bridge prompt 原文（零组装漂移），固定 `deepseek-v4-flash`，每组 n=4，统计口径复用 `_ensure_price_reflection_categories`：

| payload | 历史那次的 `not_reflected` 数 | 重采 4 次 |
|---|---|---|
| A = `20260725_145833` | 3 | **0, 1, 1, 0** |
| B = `20260725_232410` | 0 | **1, 1, 1, 2** |

两次历史值**都无法在自己的 payload 上复现**，两组分布还互相重叠；被怀疑"系统性倒向已反映"的 B payload 重采下反而更偏 `not_reflected`。**原假设的方向本身不成立。** 8 个样本全部模型原生写满五类，出现的 4 次 `unclear` 全是模型原生（3 次落在 `liquidity`）。

**裁决为"合理行为 + 一个既有设计弱点"**，未改 `orchestrator.py`。判读说明已写入 `RESEARCH_CANON.md`（`price_reflection_map` 判读边界一节）：类别齐全性由代码兜底保证≠五类都被分析过、`unclear` 语义、不同时段同数据日 run 之间地图正常迁移、以及"不能在下游站点重采来推断 bridge 稳定性"。

**顺带修掉一个审计诚实性缺陷（第一性原理审计发现，非本现象成因）**：`run_review.py` 的 `price_reflection_map` 复盘检查里，`thin_items` 判据是三个字段任一为空，而代码补齐的占位条目恒定把三者填成非空模板文案——占位类别永远进不了 `thin_items`，一路落到 `pass` 分支，给出"已覆盖五类，并包含反证与动作含义"的结论，即使其中几类从未被模型分析过。区分线索只在另一条互不引用的 `normalization_notes` finding 里。修法：新增 `code_filled_categories` 分支，从 `normalization_notes` 解析 `price_reflection_categories_added_by_code:` 前缀，把占位类别从"覆盖五类"结论里显式扣除并点名。

另记一条**未处理的观察**（不在 T27 修复范围）：`CoreFact` 契约备有 `historical_percentile` / `trend` / `magnitude` 三个结构化字段，但 L1-L5 几乎从不填（A 组 1/54、B 组 0/60），分位数实际被层级模型随手写进自由文本 `value`——A 组 L1 九条核心事实条条带分位数、B 组全部剥掉。分位数仍从 `context_brief.layer_highlights` 和 `indicator_analyses` 到达 bridge（全 payload 出现次数 77/110 vs 70/93，同一量级），所以是**显著性差异不是信息丢失**；`historical_percentile` 在 vNext 主链无消费方，字段空着不会让代码读到 `None` 出错。

**验证**：`tests/test_run_review.py` 新增红灯测试 `test_run_review_does_not_call_code_filled_price_reflection_categories_covered`，实证改前命中 `pass`（断言失败）、改后命中 `observe` 并点名 credit/liquidity。全量 `--cache-clear` **1006 passed**。

调查全文：`investigation_reports/20260727_handoff_open_threads/T27_FINDINGS.md`。

---

## 2026-07-27

### 输入瘦身的受控复核：撤销 0.40% 的那一半、保留 72.71% 的那一半（用户逐条裁决后施工）

用户读 brief 后反馈两点疑虑（改判条件变少、开头段语气变了），要求**从第一性原理判断瘦身合不合理，不许臆断**。

**方法论更正（先于任何结论）**：用户原本拿 `20260719_130534` 对比 `20260725_232410`，该对照组不成立——数据日不同（07-19 vs 07-25），且中间夹杂多批不相关改动。改用**同数据日**的 `20260725_145833`（瘦身前）vs `20260725_232410`（瘦身后），两者 `function_availability_percent` 均 93.9%。

**重复采样实验**（复用 `_compose_prompt("thesis", ThesisDraft, payload)` 真实组装路径，固定 `deepseek-v4-pro`，同一份 `synthesis_packet.json`）：

| 条件 | `invalidation_conditions` 条数 |
|---|---|
| 现状瘦身 | **[2, 2, 2]**（+ 原跑 232410 = 2，共 **4/4 恒为 2**） |
| 仅保留 `hypothesis_competition_summary`，其余不变 | **[4, 5, 3]** |
| 未瘦身历史基线 145833 | 4 |

两组区间**零重叠**。推翻此前"倾向于是 LLM 采样方差"的判断——是系统性偏移。

**省量分解**（`_sanitize_prompt_payload("thesis", ...)` 逐步拆解，基准 516,085 字符）：丢弃四字段仅省 **0.40%**（2,074 字符），压缩证据索引明细省 **72.71%**（375,269 字符）。73% 的收益里 99.5% 来自后者。

**机制**：`hypothesis_competition_summary.retained_disputes` 装的是 **11 条未解决争议**（"盈利修正供应商数据待验证""实际利率极值是结构性还是周期性"等）。改判条件本就是从"我哪里还不确定"推导出来的；把不确定清单从 thesis 眼前拿走，它只能退化成"多条件同时成立才算失效"的复合 AND 条件——概率上近乎永不触发，等于把确认偏误制度化，且删掉了「HY OAS 走阔 >3.5% 即转空」这类**单信号独立触发通道**。

**施工**：
- `NARRATIVE_STAGE_PROMPT_DROP_FIELDS["thesis"]` 撤出 `hypothesis_competition_summary` 与 `adjudication_history`（后者 403 字符，是 `candidate → kept_unresolved` 的降级审计链）；保留 `counter_thesis_boundary` / `evidence_registry_summary`（纯记账元数据）。改后**仍省 73.03%**，94 个 evidence ref 一个不少，11 条未解决争议全部回到 thesis 视野。
- `_validate_reasoned_verdict_refs` 从"至少一条引用"收紧为"**至少三条不同引用**"。依据不是新拍数字：`final_adjudicator.md:243-245` 已写死"总-分-总"结构与"三条主要理由每条必须至少带一个方括号 evidence_ref"，此前只查 ≥1 条，放过了 20260725_232410 的真实事故形态——514 字单段连续文字把状态/矛盾/风险/定价/赔率/仓位/失效条件全部压进一段，零层级。`STAGE_CONTRACT_PROMPT_REQUIREMENTS["final"]` 同步登记 `三条主要理由`。

**订正两处此前表述**：(1) 先前称"去掉 max_length 上限本应更长却更短、反直觉"——前提不成立，去上限改动日期为 2026-07-26，晚于两次 run，两次 `reasoned_verdict`（1259/514 字）均落在当时的 300–1300 区间内，从未触及上限。(2) 先前称判决正文"腰斩=变空"——不准确：232410 的 514 字承载的主张数其实更多，真正丢的是**总分层级结构与可追溯引用**，非信息量。

**验证**：新增 `test_reasoned_verdict_requires_three_distinct_citations_for_three_reasons`（单引用/双引用/同一引用重复三次均须拦下；三条不同引用通过；越界引用仍优先拦下），改写 `test_thesis_prompt_drops_low_value_fields_and_keeps_required_ones` 断言两字段必须保留。全量 `--cache-clear` 1000 → **1001 passed**，零回归。

**未查清、已交接**：`price_reflection_map` 的 `not_reflected` 计数瘦身前为 3、瘦身后为 0，且 A/B 两组共 6 次采样**全部为 0**——恢复 disputes 字段不能解释，根因未定位（T27）；「必须回应竞争假说」合约因 `candidate → kept_unresolved` 降级而空转，越有争议越不被要求回应（T28）。细节见 `investigation_reports/20260727_handoff_open_threads/HANDOFF.md`。

---

## 2026-07-26

### T26 后续：真实 run 证伪了首版的 anyOf 判断，修正两处真实 bug（原判断错误，已如实记录）

用户让 Codex 用 T26 首版代码跑了一次真实 run（`output/analysis/vnext/codex_strict_bridge_20260726_2032/`）：数据采集和 L1-L5 全部跑通，bridge 站点两次尝试均 `empty_response`（`llm_stage_diagnostics.json` 记录），用户反馈 DeepSeek 报错"anyOf 节点缺少顶层 type"，并明确指出这与首版 WORK_LOG 里"anyOf 官方支持、原样保留即可"的判断不一致。

**订正**：那条判断错了。用真实 API 直接复现（不是猜测），逐个排查：

1. **真实报错 1**（用户指出的那条，直接复现验证）：`{'error': {'message': "Invalid tool parameters schema : field \`anyOf\`: missing field \`type\`", ...}}`。逐个 schema 形态用真实 API 测试后确认：pydantic 给 `Optional[原始类型]` 生成的 `anyOf:[{type:T},{type:"null"}]`，DeepSeek strict 模式要求这类节点同级必须有 `type`；`Optional[嵌套模型]` 生成的 `anyOf:[{$ref:...},{type:"null"}]`，正确修法是把 `$ref` 解析并内联展开（不是加 sibling type——实测加了会撞另一条"An object with no properties is not allowed"）。
2. **真实报错 2**（诊断过程中额外发现，用户未提及但更早触发、掩盖了报错 1 的真实验证）：`{'error': {'message': 'Thinking mode does not support this tool_choice', ...}}`。DeepSeek v4 系列默认开启思考模式（即使不显式请求），首版代码强制指定单个函数名的 `tool_choice` 与思考模式不兼容；改成 `tool_choice="auto"` 后思考模式下可正常调用唯一注册的工具。**这条 bug 比报错 1 更早触发**，意味着首版代码的 anyOf 判断实际上从未在真实 API 上被验证过——Codex 那次真实跑到的报错，很可能是报错 2 掩盖后报错 1 才露出来的（或两者交替），首版 WORK_LOG 里"anyOf 原样可用"完全是未经真实调用验证的文档字面推断，这次才是真正对照真实 API 行为核实。

**修复**：
- `llm_engine.py` 的 `sanitize_json_schema_for_strict_tool_calling` 重写为两遍处理：第一遍不变（`additionalProperties`/`required`/剥离不支持约束）；第二遍新增 `anyOf` 修正——collapse 纯原始类型的 Optional 为 `type` 数组去掉 `anyOf`；`$ref` 分支解析并内联展开、保留 `anyOf` 结构但不加 sibling type。
- `_call_ai` 的 `tool_choice` 从强制指定函数名改为 `"auto"`（唯一注册一个工具时行为等价，且思考模式下才真正可用）。

**验证**（真实 API 调用，非 mock）：
- 用真实 `BridgeMemo.model_json_schema()` 走完整 `sanitize_json_schema_for_strict_tool_calling` → 真实调用 DeepSeek → **HTTP 200，返回完整合法 JSON，17 个必填字段齐全**，`principal_contradiction: null` 正确输出（证明 `$ref`+`null` 分支修法成立）。
- 返回结果进一步过 `BridgeMemo.model_validate()`：pydantic 校验通过，`layers_connected` 正确解析为 `Layer` 枚举。
- 单测更新：`test_sanitize_json_schema_for_strict_tool_calling_meets_deepseek_requirements` 改为锁定修正后的真实规则（不再断言"anyOf 原样保留"，改为断言"裸 anyOf 不能 survive、`$ref` 不能留在 anyOf 分支里"），并显式核实测试前提（原始 schema 确实是被拒绝的形态）；`test_call_ai_uses_strict_tool_calling_when_schema_provided` 的 `tool_choice` 断言同步更新为 `"auto"`。
- 全量 `--cache-clear` **1000 passed**（净增 0——本轮是修正既有测试的错误断言，不是新增测试面）。

**给用户的诚实说明**：首版 WORK_LOG 写的"anyOf 官方支持、不需要处理"是没有对照真实 API 验证过的判断，这次真实跑直接证伪了它，是真实的错误而不是配置问题——用户的怀疑是对的。这次的修复是逐条用真实 API 调用验证过的（不是又一轮文档字面推断），且额外挖出了一个用户没提到、但同样会导致 bridge 失败的独立 bug（思考模式与强制 tool_choice 不兼容）。

**未完成**：仍需要一次真实完整 pipeline run（走 `_run_bridge` 真实 L1-L5 数据，而不是本轮这种孤立的 schema 验证调用）确认桥接站点在严格模式下产出的叙事实质内容不打折、`_validate_bridge_memo_v2` 业务校验能正常通过，见 `现在.md` T26。

---

### T26：DeepSeek 严格函数调用（Strict Function Calling）试点落地——桥接站点单点，代码+单测完工，未关单

用户批准按此前提出的方案动手：捡起 `docs/2026-05-10_BRIDGE_JSON_RESILIENCE_AI_AUDIT.md` 第8节"阶段 C"被搁置两个半月的建议——把 bridge 站点从 `response_format=json_object`（只保证合法 JSON、不保证 schema）切换到 DeepSeek 官方的 strict function calling（服务端保证 100% 命中 schema）。

**关键发现（施工过程中，改变了原计划的改动范围）**：原方案设想需要改造 `contracts.py` 里 `BridgeMemo` 及其 7 个嵌套类（移除 `extra="allow"`、把 `Optional` 字段转成带默认值的必填）。实际检查 `BridgeMemo.model_json_schema()` 的真实输出后发现不需要——strict 模式的"schema 层面要求"（`additionalProperties:false`、字段全部进 `required`）只约束**发给 API 的那份 JSON Schema**，不要求 Python 侧的 pydantic 模型本身做对应改动；`anyOf`/`$ref`/`$def` 官方明确支持，Optional 字段在 pydantic 里生成的 `anyOf:[{type},{type:null}]` 结构原样可用。于是把改动收敛成：只在**发送给 API 前**对 schema 做一次无损的净化转换，`contracts.py` 一行未动——比原计划更小、更安全。

**实现**：
- `llm_engine.py` 新增 `sanitize_json_schema_for_strict_tool_calling(schema)`：递归给每个 object 类型补 `additionalProperties:false` + 补全 `required`，剥离 `minLength`/`maxLength`/`minItems`/`maxItems`/`format`（后者不在官方支持类型清单内，且这类字段的值本来就会被 orchestrator 代码强制覆盖，模型输出什么不影响结果）。
- `_call_ai`/`call_with_fallback` 新增 `strict_tool_schema`/`strict_tool_name` 两个可选参数：**只在显式传入时**才走 `tools`/`tool_choice` 路径（解析 `tool_calls[0].function.arguments` 作为返回文本，不再是 `message.content`），不传时的调用形态和试点之前逐字节相同——这是本次改动唯一的分叉点，经全量测试验证不影响其余任何 stage。
- `orchestrator.py` 新增 `_STRICT_TOOL_CALLING_ELIGIBLE_STAGES = {"bridge"}`（试点范围收窄到代码里显式列出的白名单）+ `_strict_tool_schema_for_stage`：按环境变量 `NDX_STRICT_TOOL_CALLING_STAGES`（逗号分隔）决定是否为某次调用启用，默认不设置环境变量、行为完全不变。`_run_bridge` 接入该开关。

**验证**：
- `sanitize_json_schema_for_strict_tool_calling` 用 `BridgeMemo` 的真实 schema（含 7 层嵌套 `$defs`）端到端断言：净化前确认原始输入确实带着 `additionalProperties:true`/`minItems` 等不合规项（证明测试前提成立，不是测一个已经干净的输入），净化后逐层核对全部合规，且 `anyOf`/`$ref` 结构原样保留。
- `_call_ai` 新增 mock 测试验证：传 `strict_tool_schema` 时发送 `tools`/`tool_choice`、不发送 `response_format`，返回值取自 `tool_calls[0].function.arguments`；不传时的调用与试点前完全一致（新增专门的回归测试锁定这一点）。
- `_run_stage`/`_strict_tool_schema_for_stage` 新增 4 条测试：默认关闭、环境变量无法越权启用白名单外的站点、bridge 显式开启后返回已净化的 schema、`_run_stage` 只在传入 schema 时才把它递给引擎（其余调用完全收不到这个参数）。
- 全量 `--cache-clear` 由 993 passed 增至 **1000 passed**，零回归。

**未完成——不能靠单测替代的一条**：这套改动"能不能跑通"已经证明，"效果好不好"没法证明——是否真的减少了桥接站点的重试、token 花费会不会异常、桥接产出的叙事实质内容会不会因为约束更严而变差，这些只有真实调用一次 DeepSeek 才能回答。需要用户设置环境变量 `NDX_STRICT_TOOL_CALLING_STAGES=bridge` 跑一次真实完整 run 并与不开启的版本对比，见 `现在.md` T26。

---

### 数字规则重构：字数上限系统性审计 + 全面放宽/移除

用户追问：这套系统是自己 vibe coding 出来的，很多规则自己都不知道有哪些，怀疑字数类上限"没有参考意义"，要求列举全部数字规则并判断哪些合理。核实后用户明确指示：`overall_assessment` 直接不设限、`revision_direction` 放宽到 500；并纠正了 Fable 此前"没出过事就先不动"的保守判断——"没出过事不代表合理"，要求从这个角度全面重构，"字多一点并不会有什么坏处"。

**审计方法**：脚本提取 `contracts.py` 全部 `Field(max_length=/min_length=)`（52 处）+ 手工核查自定义 `field_validator`（`reasoned_verdict` 的 300-1300 双边界）+ `orchestrator.py` 内非 Field 的数量阈值（`event_section_summary` 的引用数量 2-5、`summary_text` 字符带 100-600）。分三类：结构完整性（"不许留空"，未动）、证据诚信（`_reject_missing_evidence_as_direction_claim` 等非长度型语义校验，未动——这些是"不得编造""指标不得越权"的具体落地，不是随手定的数字）、数量上限（本条处理的对象）。

**逐字段复核方法**：不是无脑全删，而是先查每个字段是否喂进 `vnext_reporter.py` 的固定宽度展示位（`grep` 渲染代码里是否出现在 `<h1>`/hero title/卡片头部 `<span>` 这类位置）。查到两处**有真实下游依据、明确保留**：

- `FinalAdjudication.final_stance`（200字）——渲染进报告 `<h1>` 主标题和 hero title，无限长会直接破坏报告首屏排版，这是真实约束不是随手数字，维持不变。
- `LayerCard.local_conclusion`（500字）——渲染进层卡片头部 `<span class="layer-summary">`，与其它徽章同行展示，维持不变。

其余全部确认"不进入任何固定宽度展示位、纯属人为限制"，处理方式：

| 字段 | 原上限 | 新状态 |
|---|---|---|
| `Critique.overall_assessment` | 200 | **移除**（用户明确指示；真实事故已复现） |
| `Critique.revision_direction` | 300 | **放宽到 500**（用户明确指示） |
| `CrossLayerClaim.mechanism` | 300 | 移除 |
| `Conflict.implication` | 300 | 移除 |
| `BridgeMemo.implication_for_ndx` | 500 | 移除 |
| `ThesisDraft.environment/valuation/timing_assessment` | 各300 | 移除 |
| `ThesisDraft.main_thesis` | 500 | 移除 |
| `ThesisDraft.state_diagnosis` | 600 | 移除 |
| `ThesisDraft.priced_narrative` | 800 | 移除 |
| `ThesisDraft.payoff_assessment` | 600 | 移除 |
| `ThesisDraft.confirmation_cost` | 600 | 移除 |
| `AnalysisRevised.revision_summary` | 500 | 移除 |
| `FinalAdjudication.adjudicator_notes` | 500 | 移除 |
| `FinalAdjudication.reasoned_verdict` | 300-1300 | 下限 300 保留（强制"总-分-总+三条理由+引用"实质内容，非任意数字），上限放宽到 3000 |
| `ContextBrief.data_summary` | 300 | 移除 |
| `event_section_summary.summary_text`（`orchestrator.py` 校验，非 pydantic Field） | 100-600 | 下限 100 保留（同理强制实质总结），上限放宽到 1500 |

同步更新 `critic.md`（移除 200 字提示、更新为 500 字）、`event_section_summary.md`（150-400 → 100-1500 并注明"上限宽松，不必刻意压缩"）、`orchestrator.py` 里 event_section_summary payload 模板文案、`STAGE_CONTRACT_PROMPT_REQUIREMENTS["critic"]` 登记（从 `("200 字符","300 字符")` 改为 `("500",)`，因 overall_assessment 已无约束可登记）。

**测试处理**：`test_critic_stage_retries_after_overlong_overall_assessment` 的前提已失效（该字段不再有上限），拆成两条——`test_critic_overall_assessment_has_no_length_cap`（锁定移除生效，超长文本一次通过不重试）+ `test_critic_stage_retries_after_overlong_revision_direction`（锁定 revision_direction 新上限仍能触发重试自愈）。`tests/test_contracts.py` 与 `tests/test_vnext_orchestrator.py` 里两处 `"过长" * 651`（对应旧 1300 上限）改为 `"过长" * 1501`（对应新 3000 上限）。

**验证**：全量 `--cache-clear` 由 992 passed 增至 **993 passed**（净增 1：移除 1 条失效测试、新增 2 条），零回归；`tests/test_governance_input.py`（含防漂移闸门）与 `tests/test_docs_consistency.py` 共 15 passed。

**给用户的说明**：这次审计确认了用户的怀疑——所有 max_length 数字本身都没有找到任何文档化的依据（没有"界面只能显示多少字"或"下游系统装不下"这类理由）。但两个例外（`final_stance`、`local_conclusion`）不是"没出过事所以先留着"的托辞，而是真查到了具体的下游渲染代码证明它们喂进固定宽度位置——这两处保留是基于新证据，不是延续旧的保守判断。

---

### "为什么频繁第一次没过"系统性追问：DeepSeek 严格模式事实核查 + 批评者/五层说明书补漏两处

用户追问：今天真实跑里那么多站点第一次没通过，到底是约束不够硬、说明书不够优雅，还是没用对 DeepSeek 的 JSON 模式？要求研究整体架构有没有系统性不优雅。

**排查方法**：不凭印象回答，逐条查代码 + 逐条查真实 run 的报错原文，把当天所有重试按根因分类，而不是笼统归为"模型不听话"。

**结论一：不是 JSON 模式用错**。`llm_engine.py:166` 确认已用 `response_format={"type":"json_object"}`；当天两次真实跑的 `llm_stage_diagnostics.json` 里所有重试均为 `schema_validation_error`/`contract_validation_error`，零个 `parse_error`——JSON 语法合法性从未是问题，`json_object` 模式的职责边界与实测完全吻合。

**结论二：但代码里有一段被搁置两个半月的"强模式"线索**。`llm_engine.py:57,79,100` 的 `service_beta_features["deepseek"]` 只被赋值、全仓库无第二处读取；追出仓库里已有一份 2026-05-10 的历史审计文档（`docs/2026-05-10_BRIDGE_JSON_RESILIENCE_AI_AUDIT.md`），当时已完整诊断同一类问题（bridge 站点 event_refs 类型漂移崩溃），去 DeepSeek 官方文档核实过存在"Strict Function Calling (Beta)"——服务端保证 100% 命中 schema，但当时只做了"阶段 A/B"（parse_error 反馈强化 + 切 `/beta` 端点），"阶段 C"（真正注册 strict tool）被记录为"仍是根治路径"后从未执行。**用户怀疑这可能是 AI 编造的功能，故这次不直接采信旧文档，重新联网核实**：用 `web-access` skill 直接抓取 `api-docs.deepseek.com` 当前版本的 JSON Output 和 Tool Calls 两个页面原文——确认该模式**截至 2026-07-26 仍然存在**，仍是 Beta、仍需 `/beta` base_url、仍要求 `additionalProperties:false` 和全字段 required、仍不支持 `min/maxLength`/`min/maxItems`、思考模式下可用；官方文档未明确 `deepseek-v4-flash` 是否支持（示例只出现 v4-pro），也未说明能否与 `response_format=json_object` 同时使用——这两点如实标注为"文档未回答"，不是我推断出来的答案。**结论：这不是幻觉，是真实存在、且被搁置至今的改进项，需要按 5 月文档建议的方式先单点试点，而不是直接采信推广。**

**结论三：约束不够硬这个怀疑是对的，而且不是孤例**。把批评者、五层分析师站点的判卷标准和说明书逐条比对（风险哨兵、事件卡解读、事件汇总、五层的 `core_facts` 等已核对确认说明书写清楚，不受影响），新发现两处与 reviser/counter_thesis 同型的漏洞：

- 【已修复】`Critique.overall_assessment`（`max_length=200`）和 `revision_direction`（`max_length=300`）都是 pydantic 硬约束，但 `critic.md` 从未提及这两个字数上限——真实事故当天复现：`overall_assessment` 写长被打回重试一次。已在 `critic.md` 补齐两处上限说明，并在 `STAGE_CONTRACT_PROMPT_REQUIREMENTS` 登记 `"critic": ("200 字符", "300 字符")`，扩展防漂移闸门覆盖面（登记表首次覆盖非 lambda-validator 类型的合约，即 pydantic 原生长度约束）。
- 【已修复】`LayerCard.local_conclusion`（必填、`max_length=500`）是五层共享的 `_compose_layer_prompt` 契约文本里唯一一处"提到字段名但从未指示必须输出"的字段——"必须新增并认真填写的字段"清单里没有它，只在别处顺带提了一句"layer_synthesis 不能只重复 local_conclusion"。真实事故当天复现：L4 站点因 `local_conclusion Field required` 被打回重试一次。已在共享契约文本里补上明确指令。由于这是 5 个 stage 共享一段 Python 动态拼接文本、不是单个静态 prompt 文件，不适合塞进 `STAGE_CONTRACT_PROMPT_REQUIREMENTS`（该机制假设每个 stage 对应一个静态文件），改为单独测试直接调用 `_compose_layer_prompt` 断言拼接结果。

**验证**：新增 2 条测试（`test_critic_stage_retries_after_overlong_overall_assessment` 锁定"写长了仍能靠重试自愈"这条安全网；`test_layer_prompt_documents_local_conclusion_as_required_field` 锁定共享契约文本包含必填指令）。全量 `--cache-clear` 由 990 passed 增至 **992 passed**，零回归；`tests/test_docs_consistency.py` 7 passed。

**给用户的最终判断**：当天的重试大致分两类，不能一概而论。一类是"说明书没写清楚"（今天连续找到 5 处：bridge 5月已修、reviser/counter_thesis 本周已修、critic/L1-L5 本条修），这是真实的架构缺陷，可以且应该根治，思路是把 `STAGE_CONTRACT_PROMPT_REQUIREMENTS` 覆盖面继续扩大到所有站点。另一类是"说明书写清楚了，模型仍偶尔不合规"（l2 漏填一条 core_fact、事件卡偶尔忘记降级措辞、事件总结的引用交叉核对），这是概率性输出的正常代价，重试机制本身没有问题，不需要也不应该为此推倒重来。DeepSeek 的严格模式（若試點成功）主要能收窄第二类里"字段结构性缺失/类型错误"的子集，但官方 schema 本身不支持长度约束，所以像批评者的字数上限这类问题就算换了严格模式也治不了——文档纪律仍是唯一根治路径。

---

### 真实完整 run（`20260725_232410`）端到端验收，T24 关单 + 发现并修复终审判决书零引用漏洞

用户手动跑通一次干净完整 run，要求"看一下还有什么需要收尾的，高质量解决"。逐项核对上一批五条并行线在真实 API 调用下的表现，不只看测试绿灯。

**上一批五条线的真实 run 验收结果**：

- 【关闭 T24】论点建构 + 反方输入瘦身。真实结算单（`final_adjudication.json.token_usage`）：thesis 站读入量从上一次真实跑的 278,764 prompt tokens 降到 **67,372**（降 75.8%，超过预测的 72.9%）；counter_thesis 从 282,286 降到 **71,320**（降 74.7%，超过预测的 70.2%）；全跑总 prompt tokens 从 1,250,568 降到 957,630（降 23.4%）。判断质量未见劣化：`reasoned_verdict` 连贯、引用真实数字（实际利率 2.43%/99.6分位、盈利修正 30日+4%/90日+10% 等），方向与证据面吻合（利率类/估值类/趋势类共振指向"赔率偏不利"）。反方与论点建构均 `attempts=1`，无需重试。
- **反方修复（T21）真实验证**：`counter_thesis` 站 `attempts=1, errors=0`——此前反复失败、烧掉约 28 万 token 的问题在真实 API 调用下没有复现，一次通过。
- **修订者规格漂移修复（T19）真实再验证**：`reviser` 站 `attempts=1, errors=0`，`reviser_thesis_field_carry_forward` / `reviser_degraded_fallback` 均未触发——两道安全网继续保持"备而不用"，说明书本身撑住了。
- **机械站点 flash 路由（T25）真实验证**：`event_card_interpreter` 全部合计约 1.56 万 prompt tokens、`event_section_summary` 约 3,897 tokens，与预期"省不了多少钱但原则一致"的判断吻合，未观察到降级导致的质量异常。

**本轮真实 run 顺带发现的独立问题（不在原五条线范围内，当场诊断修复）**：

终审判决书给读者看的正文 `reasoned_verdict` 这次一字未引用证据——514 字、内容连贯、数字详实（利率分位、PE、广度百分比等一应俱全），却**零处**方括号引用。`final_adjudicator.md` 白纸黑字："三条主要理由每条必须至少带一个方括号标注的 evidence_ref……这是硬要求，一个都没有等于整段作废。"但代码侧从未把这条规则接成会拦截、触发重试的合约——`_annotate_reasoned_verdict_refs` 只在生成**之后**做软性标注（写进 `quality_gate.notes` 的 `reasoned_verdict_missing_refs`），不会让 `_run_stage` 重试；final 阶段的 `validator=` 只有 `_validate_stage_evidence_refs`，该函数只扫描结构化的 `evidence_refs`/`counterevidence_refs` 字段，`reasoned_verdict` 是自由文本，从未落入它的检查范围。报告照常按 `approved_with_reservations` 发布，读者看到的主判决文字完全没有可追溯证据。

**根因归类**：与本次系列事故同宗——A 类规格漂移的变体。区别在于这次不是"说明书没写规则"（`final_adjudicator.md` 本来就写了、还给了正确格式示例 `[L1.get_10y_real_rate]`），而是"规则没有被强制"：判卷标准里压根没有对应的校验钩子。修复不需要碰 prompt，只需要把说明书已经声明的"硬要求"真的做成硬校验。

**修复**：新增 `_validate_reasoned_verdict_refs`（复用既有的 `_resolve_claim_evidence_ref` 解析逻辑），接进 final 阶段 `_run_stage` 的 `validator=` 链：`reasoned_verdict` 非空时，零方括号引用 → 拒绝；引用了不在 `evidence_index` 里的 ref → 拒绝。不改动 `_annotate_reasoned_verdict_refs`（继续服务续跑加载旧检查点时的软性标注，且它的既有两条单测——非阻塞、零引用打软标记——原样保留，未被本次改动破坏）；不放大终审阶段本来就有的爆炸半径（`reasoned_verdict` 的 300-1300 字长度要求此前就是会触发重试的硬 pydantic 校验，这次只是把"必须带引用"提到同一严重度，不是新增一种此前不存在的失败模式）。

**验证**：红灯先行——独立脚本证实修复前的 `_validate_stage_evidence_refs` 单独作用于零引用判决文本时返回空错误列表（即会静默放行，逐字复现真实 run 的漏洞）。新增 2 条测试：零引用触发重试、引用非法 ref 触发重试，均验证重试反馈生效、第二次尝试正确通过。全量 `--cache-clear` 由 988 passed 增至 **990 passed**，零回归；`tests/test_docs_consistency.py` 7 passed。

**本轮扫过、确认健康、无需处理的信号**（如实记录，避免下次误判为新 bug）：critic/l2/l4 各自的单站点自愈重试（首次触发既有校验、第二次自行修正，非本次改动引入）；`event_section_summary` 两次尝试失败后按设计留空，属于既有"宁缺毋滥"闸门（`CLAUDE.md`「常见误判」已记录，不是遗漏）；`final_claim_ledger.json` 中 1 条 thesis claim 因 `only_weak_or_derived_evidence_refs` 被判定为 `downgraded`（非 `blocked`）——核对该 claim 的四要素（evidence_refs/counter_evidence_refs/inference_steps/falsification_conditions）齐全，降级理由是所依赖证据全部为技术面衍生指标而非核心强证据，是"指标不得越权"闸门正确工作，不是缺陷。

**未完成**：本批改动（含 2026-07-25 的 T19/T21/T24/T25 全部四批 + 本条的 reasoned_verdict 修复）均未提交入库，待用户确认后统一提交。

---

## 2026-07-25

### T24（论点建构 + 反方输入瘦身）：方案 + 代码 + 测试完工，未关单——等一次真实 run 验收判断质量

T21 落地后解封，worktree 隔离施工，两阶段门槛制（先出书面方案 + 预估节省，达标才动手，严禁触碰证据索引 key、竞争假说、冲突相关字段、反方独立性边界）。Fable 合并前独立用真实 run 的 `synthesis_packet.json` 复核了安全性，不只信 agent 自报。

**方案发现**（`investigation_reports/20260725_thesis_counter_thesis_slimming/PROPOSAL.md`）：两站读入量大的瓶颈不在 `SynthesisPacket` 顶层字段（去掉全部非 `evidence_index` 字段理论上限只有 7.4%），而在 `evidence_index` 内部——单条 `L2.get_vix_term_structure#percentile_context` 就有 228,941 字符，评估后确认是"审计级全量明细"（逐票/逐日序列），两站说明书从未要求读取，且两站合法引用只到 `parent#field` 一层，模型没有任何路径能合法引用到某一票或某一天，模型看了也用不上。

**实施**：不改 `_run_thesis` / `_counter_thesis_prompt_payload` 构造的完整 payload（继续用于 checkpoint 续跑比对和审计），只在最后一步"喂给 LLM 的 prompt 文本"这一层做压缩——`_sanitize_prompt_payload` 新增 thesis/counter_thesis 分支：丢弃两站说明书均未要求的顶层字段（`evidence_registry_summary` 等），并对 `evidence_index` 每条记录里超过双阈值（条数>8 且序列化>800字符）的嵌套列表压缩成"count+2-3条样本+说明"，聚合字段（`value`/`coverage`/`windows`/`winsorized_weight_pct`）原样保留。

**Fable 独立复核**（不是转述 agent 报告）：用真实 `output/analysis/vnext/20260725_145833/synthesis_packet.json` 跑一遍真实的 `_sanitize_prompt_payload("thesis", ...)`，实测 thesis payload 518,835→140,397 字符，**降 72.9%**（agent 自报 72.6%，吻合）；`evidence_index` 94 个 ref key 压缩前后**逐字完全一致**；`competing_hypotheses` 逐字保留；`high_severity_typed_conflicts` 初查有 1 处差异，追查后确认是既有的 `_strip_empty_event_prompt_fields`（T24 之前就存在的逻辑）清掉了一个本来就是空列表的 `event_refs` 字段，冲突的严重度/描述/机制/影响/证据引用等实质内容未受影响，不是本次改动引入的问题。

**验证**：新增 5 条测试（thesis/counter_thesis 各一条验证必需字段保留+冗余字段丢弃+ref key不变+聚合字段不变+超长列表压缩、阈值边界测试、端到端真实 `_run_stage` 落盘验证没进样本的行确实从磁盘上的 prompt 文本消失）。全量 `--cache-clear` 由 984 passed 增至 **988 passed**，零回归；`tests/test_docs_consistency.py` 7 passed。

**未完成——不能靠测试替代的一条**：压缩掉 92% 的证据审计明细后，论点建构和反方的**判断质量**会不会受影响，这是模型行为问题，不是格式问题，测试只能证明"结构对、没丢引用"，不能证明"少看这些明细，结论不会变差"。必须靠一次真实 LLM run 验收才能关单，见 `现在.md`。

---

### T21/T22/T23/T25 四条并行线关单（多 agent 并行施工 + Fable 逐项复核合并）

用户在核实 T17-T19 之余，追问三件事：这套架构是否有根本性浪费、reviser 那次事故有没有同类漏网之鱼、以及能否全面换 flash 降本。诊断结论：全面 flash 不划算（弱模型违约率上升，重试单价正好压在最贵的两站上，省下的会吐回去）；但診断过程中用真实 token_usage 结算单坐实了另一个具体病灶——反方（counter_thesis）复刻了 reviser 崩溃前一模一样的规格漂移病。用户批准按拆解出的五条线（T21-T25）分头施工，本条记录关闭其中四条（T24 留待下条记录，因为它依赖 T21 先落地才解封）。

**并行拆分方式**：T21（改 counter_thesis 相关代码）、T25（改模型路由配置）用独立 git worktree 隔离，避免与彼此、与当时主工作树里未提交的 T19 改动互相踩踏；T22（只读调查）、T23（新建文档）不碰既有代码，直接在主工作树跑。四个 agent 并行执行，完工后逐个由 Fable 亲自核对真实数据、审查 diff、手工合并（非 git merge，因 worktree 落后主仓库提交，逐 hunk 核对内容一致后搬运），不接受 agent 自述"已完成"。

- 【关闭 T25】机械站点选择性换 flash。事件卡解读、事件汇总两站路由改 flash 优先、pro 兜底；判断脊梁站点路由未动。核实事件卡产出确实被隔离在 `event_index`（非 `evidence_index`），不进主证据链，换模型不会让弱判断升格为强证据。真实数据显示这两站合计仅占全跑 token 的约 2.7%，如实告知用户"省不了多少钱，价值在原则一致性"，未夸大效果。改动仅 `config/stage_model_routing.json`、`orchestrator.py` 默认路由字典、新增 1 条路由测试。

- 【关闭 T22】批评者/风险哨兵冗余可行性调查（只读）。核实到一条比"是否冗余"更重要的事实：某次真实跑里，批评者精确指出"回购同比收缩 69%"这个数字无数据支撑（对应字段为 null）建议删除，但**同一次跑**里风险哨兵在完全不知情的情况下把这个已被证伪的数字当既定事实写进了风险论证——证明"两个独立视角互相校验"这个默认预期目前架构上并未兑现。同时定位重叠根因：`critic.md`"过度谨慎与错过赔率"一节与 `risk_sentinel.md`"3.5 双向风险与确认成本"一节是同一件事的设计层面对撞，不是巧合。产出三选一书面建议（合并/仅改重试策略/维持现状），推荐"仅改重试策略"为唯一无代价改动，"合并"会真实牺牲"证据面均衡"原则，需要额外 A/B 验证，**决定权留用户**，未产出任何代码改动。报告：`investigation_reports/20260725_critic_risk_redundancy/OVERLAP_AUDIT.md`。

- 【关闭 T23】人话架构文档。逐站点讲清楚回答什么问题/凭什么有发言权/看不到什么/失败会怎样，配真实花钱地图（`token_usage` 实测数字），加"还没人替你验证过的设计决定"一节（收录 T22/T20/T24 三项）。Fable 抽查核实了文档里的关键事实（回购 69% 数字矛盾、终审第二次才通过、结构检查未过但未触发重跑等），均与真实数据吻合，未发现编造，未做实质改写。交付：`系统说明_人话版.md`。

- 【关闭 T21】反方 counter_thesis 合约—说明书错位修复。根因与 reviser 那次事故同型：`_validate_counter_thesis_draft` 和 pydantic 结构校验要求的字段名，`counter_thesis.md` 从未逐字写过，模型只能凭经验猜——两次真实事故复现同一模式（`hypothesis_text` 猜成 summary/statement，`falsification_conditions` 猜成 falsification_signals），两次尝试共烧掉约 28 万 prompt token，最后退回确定性兜底稿。修复：`counter_thesis.md` 补齐「输出字段纪律（硬合约）」+ 完整正确 JSON 示例；`STAGE_CONTRACT_PROMPT_REQUIREMENTS` 登记表新增 `counter_thesis` 条目（与已有 thesis/reviser/final 条目合并，非覆盖）；红灯回归测试用会"照 prompt 抄字段名"的 fake engine 精确复现两条真实报错，修复前红、修复后一次通过。

  **Fable 在合并 agent 产出时发现并补做的追加修复**（不在原 T21 任务范围内，是复核 T23 文档时发现的缺口）：修订者失败降级时会显式打 `degraded_fallback` 标记并传导进终审判决书的质量闸门（T19 的 D 类工作），但反方失败降级时此前只留痕在 `counter_thesis.json` 自己的 `prompt_input_audit` 里，终审判决书完全看不出这次反方论证是模板凑数，两个站点的降级可见度不对称。补齐：`_build_hypothesis_competition` 把 counter_thesis 的 `fallback_reason` 计入 `HypothesisCompetition.fallback_warnings`；主流程在原有 `reviser_degraded_unrevised_thesis` 质量闸门备注旁新增对应的 `counter_thesis_degraded_deterministic_fallback` 备注。新增 2 条测试（降级触发时正确标记、正常产出时不误标）。

**验证**：全量 `--cache-clear` 由 T19 收工时的 980 passed 增至 **984 passed**（T25 +1、T21 主修复 +1、T21 追加修复 +2，零回归）；`tests/test_docs_consistency.py` 7 passed。

**未完成**：四项修复均未提交入库，与此前 T17-T19 的工作树改动一起，待用户批准后统一提交。T20（命名空间根治方案）、T24（输入瘦身，本条记录后立即启动）仍未开工，见 `现在.md`。

---

### 干净完整 run 端到端验收，T17/T18/T19 三项一并关单

用户手动跑通一次干净完整 run（`output/analysis/vnext/20260725_145833/`），逐项核对三个待验收事项，证据均在同一次 run 里坐实：

- 【关闭 T17】L4 句柄泄漏治本 + 分层缓存修复。`data_integrity_report.json`：`function_availability_percent=93.9`（前次 82.3%）、`confidence_percent=91.1`、`blocked=False`、`publish_status="publishable"`；`analysis_packet.json` 中 `get_equity_risk_premium` 多处正常出现，确认恢复。代码已随 commit `9f8d484` 入库。
- 【关闭 T18】reviser 证据引用优雅降级 + `get_ndx_earnings_revision_metrics` 授权登记。`synthesis_packet.evidence_index` 核对：该函数五个字段（`slope_30d` / `slope_90d` / `breadth_30d` / `dispersion_ntm` / `analyst_coverage`）均登记为 `supporting_only`，与设计一致；本次 run 净化逻辑未被触发（`llm_stage_diagnostics.json` 无 `reviser_evidence_ref_sanitization` 记录），说明本轮无非法引用可净化，不是功能失效。代码已随 commit `9f8d484` 入库。
- 【关闭 T19】reviser 合约架构性修复（规格漂移 + 软着陆），验收判据见下方施工记录。`llm_stage_diagnostics.json`：reviser `attempts=1`，`reviser_thesis_field_carry_forward` 与 `reviser_degraded_fallback` 均未出现——即**第一次尝试就过、且两道安全网都没触发**，证明是 A/B 类说明书修复本身治本，不是靠 C/D 类兜底混过去的。`final_adjudication.json.quality_gate.notes` 中也没有 `reviser_degraded_unrevised_thesis` 标记。

同一份 run 的真实结算单（`final_adjudication.json.token_usage`）顺带暴露了下一个问题：反方（counter_thesis）复刻了 reviser 崩溃前一模一样的规格漂移病，`attempts=2` 且 `status=failed`，两次尝试共约 28 万 prompt token 全部作废、代码兜底稿顶上；加上论点建构（约 27.9 万 prompt token），两站合计吃掉全跑 45% 的 token。已拆解为 T21-T25 五条线继续处理，见 `现在.md`。

### reviser 连崩两跑的根因诊断与架构性修复（T19 施工记录）

**诊断（证据取自失败 run `output/analysis/vnext/20260724_223804/`）**：不是"约束太多压垮模型"，是 **reviser 挂的合约最多、说明书写的最少**。

- `llm_stage_diagnostics.json`：reviser 两次尝试报同一条错（`candidate hypothesis hyp_counter_33b7f68546 is missing from hypothesis_responses`），非随机失手。
- `prompt_audit/reviser/attempt_{1,2}.parsed.normalized.json`：两次 `revised_thesis` 键集合**逐字相同**，且恰好等于 `reviser.md` 输出模板 + Step 3 清单列出的 19 个字段。模型严格照说明书作答；`hypothesis_responses` 从不在说明书里。
- 输入体量**不是**病因：reviser `prompt_chars=70,671`，thesis `prompt_chars=596,649`（8.4 倍）却通过。
- 材料本就在手：`attempt_1.prompt.txt:321-344` 完整携带 `thesis_hypothesis_responses`（两个 id、verdict、理由、合法 refs），但 `reviser.md` 输入字段表未列该字段。
- 重试无效的机制：`_run_stage` 把 `last_error` 追加在完整 prompt 之后，正文仍是 18 字段模板 → 反馈与正文自相矛盾，且重试是整份重采样，无法表达"保持其余不变只补一个字段"。
- 合约面盘点：thesis 挂 1 条 validator、prompt 写了；final 挂 1 条、prompt 写了子字段权限；**reviser 挂 2 条（严格超集）、prompt 一条没写**。二跑与三跑的死因正是这两条。

**修复（按第一性原理分类施工）**：

- **A 类 规格漂移**：`reviser.md` 补齐 `hypothesis_responses`（输入表 / 输出模板 / Step 3 第 7 位 / 质检表 / 绝对禁止表）与「证据引用纪律」硬合约节；`final_adjudicator.md` 补 evidence_index 逐字合法性。
- **B 类 命名空间不一致**：合法子引用名来自 `MetricAuthority` 条目名，与工具 `value` 真实字段名是两套词汇（本跑 thesis attempt 1 即因 `L4.get_m7_buyback_flow#m7_quarterly_total` 命中）。三份 prompt（thesis/reviser/final）统一加"只能逐字使用索引已存在的 ref、不得自行拼接 `parent#field`"。根治口径留 T20。
- **C 类 职责错配**：`_carry_forward_reviser_thesis_fields` —— reviser **整个遗漏**的 `revised_thesis` 字段从原稿原样继承、打 `carried_forward_from_thesis` 标记、写 `stage_diagnostics.reviser_thesis_field_carry_forward`。白名单起步只放 `hypothesis_responses`；键存在（含空数组）一律不碰，交 validator 硬拦。接线为 `pre_validate_transform`（继承先行、净化在后），无签名改动。
- **D 类 爆炸半径**：reviser 调用点加 try/except（对照 `counter_thesis` 既有成例），失败退回未修订原稿。`AnalysisRevised` 新增 `degraded_fallback`（Optional，向后兼容）；`revision_summary` 带 `[degraded]` 声明；进 `_append_final_quality_note("reviser_degraded_unrevised_thesis")`；`_load_reviser_checkpoint` 拒绝把降级产物当检查点复用，避免一次失败被续跑永久固化。
- **F 类 防漂移**：新增 `STAGE_CONTRACT_PROMPT_REQUIREMENTS` 登记表 + `tests/test_governance_input.py` 两条闸门（合约必须在 prompt 里写过、三份 prompt 必须有命名空间纪律）。**对修复前的 prompt 跑该闸门会红 9 处**，其中 reviser 的 2 处正是二跑/三跑死因。
- **E 类 反馈回路**（定向修补重试）**未做**：本次事故可证其无效——模型手上没有该字段的 schema，再精准的反馈也修不了。前置修复完成后重试将变罕见，留待再评估。

**验证**：新增 9 条测试（遗漏继承一次通过、显式空数组仍硬拦、模型自答不被覆盖、继承来源非法仍硬拦、降级产物保原稿+保冲突+声明降级、降级进质量闸门、降级检查点不被续跑复用、合约—说明书一致性、命名空间纪律）。红灯先行：修复前复现出与生产逐字相同的错误。全量 `--cache-clear` 由基线 **971 passed** 增至 **980 passed**（9 条全部新增，零回归）；`tests/test_docs_consistency.py` 7 passed。

**端到端验收结果**：见上方「干净完整 run 端到端验收」条目——`attempts=1`，两道安全网均未触发，判据达标，【关闭 T19】。

---

## 2026-07-24

### 全成分 NTM Forward PE 正式链落地（工单 E4，Codex 施工 + Fable 接线验收）

- 【关闭 T14】L4 forward PE 断供正式补上：`get_ndx_forward_pe_full_constituent`——Invesco 官方全持仓权重（共享模块 `src/qqq_holdings.py`，vintage_archiver 同源改导入）+ yfinance FY1/FY2 一致预期财历感知 NTM 插值（无财历者 0.5/0.5 并披露占比）+ 含亏损成分的调和聚合（1/Σ(w̃ᵢ·NTM盈利收益率ᵢ)，消除剔亏偏差）。时点红线：历史 end_date 一律 `no_point_in_time_consensus_for_backtest`；持仓超 10 天标 stale；覆盖率/排除清单/兜底状态全披露。注册三件套（tools 注册表、collector L4 清单+回测跳过表、evidence_families 新家族 `ndx_full_constituent_forward_pe`）由 Fable 亲手接线。RESEARCH_CANON 新增判读卡（水平证据不得单独证明便宜/贵，须与盈利修正连用）。
- 验证：live 冒烟 Fable 亲跑——**forward PE 21.698、Invesco 直连成功、覆盖 100%、103 成分零排除**；NVDA NTM 插值手工复算精确吻合；全量 `--cache-clear` **952 passed**（基线 944 + 8 条新 mock 测试）；Codex 沙箱内 Invesco 406 判定为环境（沙箱不继承代理）非代码。关单细节见 `investigation_reports/20260723_l4_earnings_audit/WORK_ORDERS.md` E4。

### 盈利预期修正指标家族落地 + 验收轮抓出并修正符号翻转缺陷（工单 E5，Codex 施工 + Fable 验收亲改）

- 【关闭 T15】`get_ndx_earnings_revision_metrics` 进主链：30/90 日修正斜率（剥离日历漂移的 FY1/FY2 分腿公式）、上修/下修广度、NTM 预期分歧、分析师覆盖；材料双轨**档案优先**（±2 天锚），雅虎回看值只补未覆盖窗口并带 `supplier_lookback` + 逐窗口验证状态；财报周双触发低置信标记；历史 end_date 诚实拒绝。档案隔离声明范围化升格（仅限本指标家族的时点材料，其余用途仍隔离）；expectation_ledger 注记双轨化；注册三件套 + 法典判读卡齐备。
- **验收轮的关键修正（Fable 亲改）**：首版 live 斜率 −1.35%/30d 被证实由数据残缺统治——LIN 现值归零（−100%）、SPCX 穿零（−514%）、WBD 近零基数（+216%），SPCX 一只即拉反指数符号。加三道防线（近零基数/符号穿越/±100% 单腿 → 无效剔除；幸存极端值 ±50% 温莎化并披露；标记机制不变）后复跑：**30d +2.25%、90d +8.57%**，符号与广度（+56.9pp 净上修）及已知上修周期一致。"无意义"与"真实但嘈杂"不得混同已写入法典。
- 验证：TSLA 斜率逐值手工复算吻合；防线新增 2 条测试；全量 `--cache-clear` **962 passed**；archiver README 模板同步升格文本防覆盖。细节见工单 E5 关单记录。

### 只读终审退回五处 → 全部修复终验（Codex 审 → Fable 裁 → Codex 修 → Fable 终验放行）

- 用户令 Codex 只读终审 E4/E5，判 Not ready 退回五条；Fable 逐条对代码亲验：四条属实（治理接线七处登记点全缺——比终审所列更大，含 packet L4 成员表缺席；覆盖率硬门缺失；±100% 一刀切误杀可靠基数真实修正；divergence 口径混用系 Fable 上轮遗留），一条（Invesco 406）裁为环境差异非代码缺陷。
- 修复：治理九文件接线齐（data_evidence 四表、packet L4 成员、canon 双判读卡、l4_analyst 菜单、state_ledger 四键）；E4 <90% 与 E5 各子块 <70% 覆盖硬门；ill-defined 判定只留近零基数+符号穿越（精确 −100% 仍被覆盖，测试锁定）；divergence 原始值同口径。新增 5 组测试。
- 终验（Fable）：治理面 grep 横扫九文件齐；全量 **967 passed** 复跑；live 冒烟两指标 availability/覆盖/温莎化正常（30d +2.38%、90d +9.70% 保持正号）；终验冒烟出现一次带代理环境 406 走兜底（2 天新鲜、门内可用），实证健壮性保障为"兜底+新鲜度门"。经用户授权整批提交推送。







### 盈利预期缺口终审 + E1/E2/E3 三线施工收口（双 AI 报告对比核验 → Fable 终审裁决 → 并行派工）

背景：用户提交 ChatGPT 审计与 WorkBuddy 调查两份 L4 盈利预期缺口报告，委托 Fable 终审。对比核验（`investigation_reports/20260723_l4_earnings_audit/COMPARISON.md`）与终审裁决（同目录 `DECISION.md`：七项分歧逐条裁决、P0-P3 施工顺序、两条两份报告都漏掉的决定性证据——前 15 否决条款的重估条件已触发、雅虎回看值角色已有决策记录）。用户批准 P0-P2 拆单（工单包 E1-E6，同目录 `WORK_ORDERS.md`），并修复 Clash 分流使 Invesco 持仓接口恢复直连。

- 【关闭 T13】P0 语义与守恒修复（工单 E1）：①final_stance claim gate——"证据缺失"与"放大×风险方向"子句级共现即 raise（fail-closed 触发重生成），反事实句放行，落位 `contracts.py` model_validator（循 stance_label 方向冲突检测真实先例）；`final_adjudicator.md` 补"缺失证据不得定方向"纪律；末次 run 事故原句作反例测试。②过期分位退出核心摘要——根因是 `packet_builder` 深扫描兜底绕过门控直读 `HistoryOfMarket` 原始子字段，修复为深扫描排除该键（68.5 陈旧分位不再冒充摘要）。③`hom_available` 保留 presence 分支语义（回测下 eligibility 恒 False，改定义会静默抹掉诚实降级呈报），另立 `hom_decision_eligible` 与顶层 `availability=available/stale` 修覆盖率失真。④sidecar daemon 报错归因修正，fail-closed 不变。两处偏离字面工单均经 Fable 拍板，细节见工单关单记录。
- E2 档案宇宙扩容（T15 子件，T15 继续开放）：vintage 每日快照从前 15 扩到 Invesco 全持仓——实跑 108 条过滤 5 条得 103 只（含 3 只 ADR），权重覆盖 99.86%，yfinance 103/103 零失败，耗时 384s；schema_version 1→2，隔离声明保留，静态兜底同步扩容；实跑写临时路径，当日正式快照确认未覆盖。
- E3 供应商回看值对账（T15 子件）：纯档案脚本 `scripts/validate_supplier_lookback.py` 对 292 对"雅虎 7daysAgo vs 自建档案当日实拍"——中位偏差 0.0034%、≤1% 容差占比 96.92%、9 条离群集中于财报周的 TSLA/GOOG/GOOGL（最大 +12.99%，方向为低估修正斜率、偏保守）。Fable 复跑脚本+手工复算后**闸门裁决：有限通过**——档案优先、雅虎只填未覆盖窗口、`supplier_lookback` 标签+逐窗口验证状态、财报周低置信标记、回测只用档案；30/60/90 天窗口 08-11/09-10/10-10 补验（工单初稿 90 天日期算错，worker 纠正）。裁决全文在工单 E3 节。

### 验证

- 全量测试：`.venv/bin/python -m pytest --cache-clear -q` **944 passed，58 warnings**（前日基线 921；warnings 同类既有）。
- 定向：E1 五个相关测试文件 83 passed；E2 `test_vintage_archiver.py`+`test_expectation_ledger.py` 29 passed；均 Fable 复跑。
- claim gate 另由 Fable 用五个边界探针直接调用验证（拦截/放行全部符合设计）。
- E3 脚本确定性：两次运行输出逐字节一致；最大离群对（TSLA +1q）由 Fable 对原始档案手工复算吻合。
- `tests/test_docs_consistency.py` 7 passed。



### 十项未完成重新裁决：关闭重复/低价值项，HoM 体检完成

- 用户逐项听取人话解释后拍板重排队列：只保留可选个人阈值、缩小版透明化审计、到期成绩单和下次真实运行验收四项。“等你决定”降为 0；个人阈值可以永久不配置，不阻断市场分析。
- 【关闭 T01】状态纠错：旧快照兼容修复与 20240805 / 20250409 / 20260509 三份复核已在 2026-07-17 完成，`WORK_LOG.md` 当日记录明确三份仍为 `blocked + unpublishable`。`8cf2f49` 重建《现在》时从过期工单误复活了该项，本次不重复施工。
- 【关闭 T02】取消第三层接管首页：第三层只负责事件与数据对质解释，继续由经过 Critic/Reviser/Final 治理的第一层判断坐首页，不为了署名切换新建一个难以可靠证明的自然语言语义检测器。
- 【关闭 T03】HoM 真实接口体检完成：HTTP 200；trailing 32.58 与 2026-07-22 尾值一致；forward 24.29 与 2026-05-18 尾值一致但已陈旧。独立复核发现上游覆盖率与总权重自报 110.4%–112.88%，口径未解释；新增百分比合理性门，超界即将 HoM 全部字段降为 `audit_only`，并移除简化路径中写死的 `market_cap_coverage=100.0%`。历史 `end_date` 路径因没有当时留存 vintage/PIT 覆盖率，也固定降为 `audit_only`，防止用今天看到的回溯曲线伪装成历史当时事实。trailing 50 点不报分位；forward 298 点计算为 68.5 分位，但只作陈旧审计参考。完整记录见 `investigation_reports/20260722_hom_source_audit/REPORT.md`。
- 【关闭 T05】取消“纳指集中度书面论证”必交作业：查明 `concentration_argument_status/note` 只存在公开结构占位，运行时没有消费路径，原完成判据无法产生声称的系统效果。报告中的强制催促文案改为“如未来真改个人政策上限，按正常政策复审”，不再列为当前作业。
- 【关闭 T07】取消独立巨型文件拆分：用户可见收益低、回归面大；未来功能必须触及相关区域时就地拆分，不再单独立项。
- 【关闭 T08】从未完成计数中移除：数据史审计已判定干净 PIT 历史不足，“历史上像今天”引擎继续冻结且不施工。如未来数据条件实质改变，必须以新编号重新立项，不复活 T08。
- T09 时间语义更正：20 个自然日只是让打分器不再跳过 run；真正的首份完整成绩需要 T+20 个交易日数据齐全，不再宣称 7 月 27 日必然出结论。

### 验证

- HoM API 直连与项目函数各实跑一次，两路值、尾值日期、样本数与时效状态一致。
- 定向测试：`tests/test_docs_consistency.py tests/test_vnext_reporter.py tests/test_l4_external_valuation_sources.py` 共 **112 passed，4 warnings**。
- 全量测试：`.venv/bin/python -m pytest --cache-clear -q` 从头执行，**921 passed，58 warnings**。warning 与改动前基线同类，为第三方弃用提示和既有精度提示。
- `git diff --check` 通过。
- 独立 reviewer 两轮复核：先发现 HoM 自报覆盖率/总权重超过 100% 仍可穿透，以及历史 `end_date` 会把今天取得的回溯数组当成当时可见数据；两项均已修复并补回归测试。最终复核无新的 Critical / Important 发现。

### 文档体系重建：状态单点收归 `现在.md`，`TASKS.md` / `NEXT_STEPS.md` 废止（用户发起审计，Fable 主刀）

**起因**：用户反映 `NEXT_STEPS.md` 与 `人话进度报告.md` 混乱，提出"未完成与已完成应分文档"，要求审计并评估是否需要文档与 `CLAUDE.md` 改革。

**审计发现（全部可复核）**：① 记分板三重计数冲突——`人话进度报告.md` 正文声明已解决 47、清单标题写 23、实际列 30；第 38-47 项中 12 项全文零命中，不可寻址。② `NEXT_STEPS.md` 的"推进方向"7 段中 4 段是整段已完工内容；"等你拍板"3 条中 2 条已销案，其中 GitHub 转私有一条与同文件下方 3 行处的销案声明直接矛盾；章节编号 0,2,3,4,5,7,6 错乱。③ 记分板排队第 2 位、注明"数据基础最大遗留"的旧快照回放不兼容，在 `NEXT_STEPS.md` 全文查无此项。④ 工单标题过期：#21 仍写"待开工"（实际 7-17 收口），#16 无完成标记（实际已落地）。⑤ 根目录 27 个 md / 13,141 行，14 个停在 5 月。⑥ `CLAUDE.md` 文档路由不含 `人话进度报告.md` 与工单台账；四账收尾纪律只存在于 agent 私人记忆，换 agent 即失效。

**根因**：状态被**声明**而非**计算**，且副本数 > 1。2026-07-13 曾以"立规矩"方式修过同类漂移，9 天后原样复发——流程约束对本项目无效。

**设计推导（与用户两轮对话后定稿）**：本次先落地了 `TASKS.md`（状态台账）+ `NEXT_STEPS.md`（路线图）的两文件方案，随即被用户质疑"这两个都是待办类，为何不合"。复审确认用户正确：二者变更触发完全重叠，拆分制造了一条只为看住接缝而存在的断言。进一步用**可推导性检验**（doc_A 能否由 doc_B 机械推导；能则是副本、必须收敛，不能则回答不同问题、独立合法）重排全部文档，得到最终结构：

- **`现在.md`（新建，唯一状态源）**：等你决定的 / 我接下来要做的 / 全部未完成台账 / 系统现状 / 明确不做的事。owner 与 agent 读**同一份**——二者对"现在什么状态、该做哪件"的查询同构，答案必须逐字相同。台账新增两个必填字段：**完成判据**（把"我说做完了"变成"标准说做完了"，让非技术 owner 不读代码也能验收）与**细节锚点**（技术注意事项下沉到工单，保证看板可读的同时不丢信息）。新增"我接下来要做的"一行，把 owner 的否决权从"偶尔大会诊"变成持续零成本。
- **`人话进度报告.md`（定性修正）**：此前误定性为"WORK_LOG 的白话版"——按可推导性检验该定性错误且危险（若真是副本就该删）。它与 `WORK_LOG.md` 互不可推导：日志的体裁不含否决的备选、未做事项及理由、用户裁定、对 owner 的行动请求。正式定性为**决策记录**（对应软件工程中 ADR 与 CHANGELOG 的标准分工）。删除全部内嵌台账（历史漂移全部发生在状态构件上，叙述本身从未出错）；路由改为"涉及方向与取舍时 agent **必读**"——它是项目中唯一记录 owner 意志的载体。
- **废止 `TASKS.md` / `NEXT_STEPS.md`**：内容分流至 `现在.md`（逐项）与 `CLAUDE.md`（常见误判提醒）；`NEXT_STEPS.md` 的文档地图删除，与 `CLAUDE.md` 文档路由重复。
- **`CLAUDE.md` 重写**：北极星压缩为三支柱 + 六问单段；常驻边界 9 条（新增"历史材料不是现状"）；文档路由改表格且全项目唯一一份；执行纪律新增"状态只写一处 + `【关闭 T##】` 标记 + 编号永不复用"与"信必须够格"；新增"常见误判"段。**行数与改革前持平但装下了更多约束**。
- **`tests/test_docs_consistency.py` 重写（7 条）**：台账良构（编号唯一、状态枚举、完成判据与锚点必填）、标题计数由实际行数支撑、看板不得出现完成标记、"接下来要做的"必须指向存活编号、**编号永不复用**（扫描 `WORK_LOG.md` 的 `【关闭 T##】` 对照当前台账，提供"东西不会被悄悄弄丢"的机器保证）、信中不得出现台账表、四份入口文档（CLAUDE/AGENTS/README/现在）的路由路径必须可解析。**没有一条在校验两份副本是否相等**——需要对账测试即说明结构仍有冗余。
- **历史材料归档**：12 份 5 月期一次性审查与旧版通俗说明 `git mv` 进 `docs/archive/2026-05/`，附 `docs/archive/INDEX.md` 逐份说明理由。根目录 md 由 27 降至 15。**未归档的同期文件**：`回测原则.md`（第一性原理推导的回测必要条件，仍是现行准则，本次补进路由——此前处于零引用的失联状态）、`DESIGN.md`（`$impeccable` 技能的设计寄存器输入，仍被读取）。
- **路由修复**：`README.md` / `AGENTS.md` / `ARCHITECTURE.md` / 工单台账开头均残留指向已删文件的路由，逐处改指 `现在.md`；测试的路径校验范围随之从 1 份扩到 4 份入口文档（只查 `CLAUDE.md` 抓不到这类死链，本次实证）。
- **工单台账**：#21 标题改为已完成并指向完成记录；#16 复核后标注"已落地 / 部分被取代"，如实说明原第 ⑦ 项上行触发机会栏在 R2 脊柱重构中未保留、功能由【转多】方向失效条件承载；四份 `WORK_ORDERS.md` 顶部统一加"状态权威声明"指向 `现在.md`。

**一次性迁移边界**：这次为了拔掉旧副本，删除了《人话进度报告》顶部已经失真的常驻记分板，并原位勘误工单 #16 / #21；因此“只增不改”是本次结构合入后的维护规则，不是对这份迁移 diff 的错误描述。以后旧信、旧日志和旧工单事实不再覆写，有变化只追加带日期的勘误或关单记录。

**提交前复核与验证**：两轮独立 reviewer 共找到并已修复九类收口遗漏：唯一状态源的测试数与“未提交”自失效句、Q3/Q6 真实运行验收漏项、规则内部的状态副本歧义、归档索引死链、T05 假锚点、归档搬家造成的历史报告相对链接失效、“只增不改”迁移边界没有说清，以及《现在》开场误伤长期规则；旧路线图中的历史 `docs/` 大扫除也已明确裁定为不单独立项。路径测试从四份入口扩到入口及其直接指向的六份活文档，并补“等你项精确一致、下一件只能有一项且必须可开工、细节锚点至少落到真实文件”。新测试仍为 7 个职责级测试函数，反向注入逐项确认会红。最终 `.venv/bin/python -m pytest --cache-clear -q` 从头执行：**918 passed，58 warnings**。纯文档与文档测试层，未触碰 `src/`、prompt、artifact 合约与报告渲染。

---

## 2026-07-20

### 报告质量工单包 Q1/Q3-Q6 完工（Q2 暂缓）：Fable 主刀 + 两个 Sonnet worker 并行，三轮提交前复审后 911 测试全绿

- 用户拍板：除 Q2（透明化与权威性审计）暂缓外全部实施；Q1 选修标签不改数值；Q4 选 A+C；施工不再派 Codex，简单件派 Sonnet subagent、Fable 逐项亲验。工单包 `investigation_reports/20260720_report_quality/WORK_ORDERS.md`。
- **Q1 利差单位标签修复（worker A 施工，Fable 亲验）**：`tools_L1.py` 的 HY/IG OAS 与 `tools_L2.py` 的质量利差把 FRED 原生百分比值标成 basis points 的病根修正——unit 如实改为 percent / percentage points（正常+unavailable 兜底双路径），notes 补命名史（函数名 `_bp` 保留，系跨 artifact 合约键）；`l2_analyst.md` 加单位纪律（须写 X.XX%（≈XXXbp））；canon HY/IG 判读卡补单位口径；6 条新测试锁定。数值与函数名零改动，历史快照零污染。顺带核实 `get_10y2y_spread_bp` 确有 ×100 换算，非同类病。
- **Q3 governed 事件总结（Fable 亲做）**：新合约 `EventSectionSummary` + 亲笔提示词 `event_section_summary.md`（只许引用本轮事件卡、[card:] 引用、固定边界句结尾、禁触 L1-L5、150-400 字、弱材料须如实说明）+ orchestrator 独立阶段（校验器五重：引用声明与正文逐一对应、卡片白名单、2-5 张引用带、边界句、禁 L1-L5 ref、长度容忍带；失败宁缺毋滥留痕 section_summary_failure）+ 渲染进外部世界章节顶部。R6"事件卡 10 张硬上限"测试改为按阶段前缀分账（卡片仍严格 10，总结重试 ≤3）。live 验收留待下次真实 run。
- **Q4 L1-L5 内嵌折叠+全局开关（Fable 亲做，用户拍板 A+C）**：每层"展开全部 N 个指标卡（含发言权边界与反证）"折叠回归 brief 内（完整判读卡：读数/标尺/判读正文/发言权边界/反证）；06 章节头新增"全部展开/收起"开关；Playwright 实测五层全开/全收与文案切换。
- **Q5 短姿态枚举（worker B 施工合约与提示词，Fable 接线徽章并亲验）**：`FinalAdjudication.stance_label` 可选受控枚举（防守等待/偏防守/中性观察/偏进攻/进攻），NFKC 清理+同义映射+非法值字段级清空且留痕 quality_gate.notes（W3 先例），旧档案整体回放兼容；final_adjudicator 提示词三处要求；门脸徽章优先读枚举、旧档案回退关键词抽取；11 条新测试。
- **Q6 补采清单质量（worker B 施工，Fable 接线并亲验）**：查明"缺口未由模型明示"占位系 `_parse_and_validate` 代码兜底（模型漏写缺口时避免整次裁决报废），非模型产出；补采条目带 quality=specified/low_quality_placeholder 结构化标记 + 顶层 low_quality_count；integrated_adjudicator 提示词强制写明具体缺什么数据/字段/窗口、禁笼统套话；渲染端优先读 quality 标记（旧档案回退文案匹配）；4 条新测试。
- 附带小修：事件卡 chip 短 ID 先剥 `event_` 前缀再截尾（不再出现"vent_abc"式切字）。
- 验证：全量 **903 passed**（基线 881 + 新增 22）；正式报告重生成，Playwright 冒烟（徽章短词、五层开关、移动端 390 无溢出、零 JS 错误）。改动未提交，待用户审阅。
- **提交前 Codex 复审揪出 4 条真实问题（Fable 逐条核实代码后确认非幻觉，全部修复）**：①事件总结 payload 缺 raw_text_available/effective_date，模型既无法履行"如实说明材料质量"要求，也没有代码防线拦"事后信息回流"进历史报告——payload 改为从原始事件底账代码级富化，新增材料质量豁免句校验+日期泄漏校验；②Q1 单位修对了但 `prompt_examples.py` 里 `get_hy_oas_bp`/`get_ig_oas_bp` 的运行时 few-shot 范例仍是旧的"620.0=620个基点"口径且在 L2 层默认注入列表里，新规则与反例同时喂给模型——范例数值与叙述改成 percent 口径；③Q6 的 `answered_by_data`→`cannot_answer_yet` 自动降级分支不回填缺口，缺口为空时整条从补采清单静默消失（降级越多能看见的问题越少）；空话识别只做两个固定字符串精确匹配——两个降级分支统一回填占位，新增空话短语表（长度阈值试过因误伤"盈利修正"这类合法短缺口被撤销）；④姿态徽章 `stance_label` 只做枚举校验不查方向，"进攻"标签可能配"防守"正文——新增粗粒度方向冲突检测，冲突即清空回退关键词兜底，"中性观察"不做二次揣测避免误伤。新增 8 条测试；全量 **907 passed**；报告二次重生成 Playwright 冒烟结果与第一轮一致。
- 姿态兼容语义更正：现代产物若 `stance_label` 因非法值或方向冲突被清空，门脸保持不显示，绝不再用旧关键词猜回；只有完全没有该键的旧档案才启用兼容回退。
- 用户于 2026-07-22 查收修复反馈并确认：复核无阻断后提交整批改动，将 `main` 无损快进为最新主线；本轮不包含远端推送授权。
- 第二轮独立复审继续复现三条边界绕过并完成加固：①少数仅标题/非官方来源卡也必须在自身引用附近出现降级归因，并拦截无日期的事后确认、确定性因果和中文格式未来日期；②模型省略整题或显式写“未作答”时，系统补成 `cannot_answer_yet` 并进入补采清单与低质量计数；③姿态方向关键词增加常见否定关系识别，`不宜加仓`、`而非防守` 不再被当成正向信号。新增 2 个独立测试函数并扩展 Q3 既有验证器场景；全量 **909 passed**。
- 第三轮复审继续补齐英文标点/跨行禁句、斜杠与点号日期、现代空标签不得被旧逻辑猜回、补采顺序/去重/具体缺口保留，以及“空话前缀+具体字段”不得误伤。最终以 `.venv/bin/python -m pytest --cache-clear -q` 从头执行：**911 passed，58 warnings**，`lastfailed` 缓存不存在。
- CLAUDE.md 复核（用户问询）：工作区干净、无手滑改动，最后一次变更为 7-19 有意的括注清理；内容现状良好，不建议为精简而精简。`.codex/config.toml` 与 `docs/4.20 VNEXT_REPORT.md` 两处游离改动经用户确认无所谓后恢复原样。

### brief 视觉终局返工：Fable 亲自接手，宋体事故根因 + 全脊柱对照样张实测（截图驱动）

- 背景：用户裁定 Codex 两轮视觉返工后"仍远不如 demo"，指定 Fable 亲改。根因盘点发现 Codex 全程无法打开页面（file:// 受限），等于盲改；本轮改为 Playwright 截图驱动，桌面+移动逐屏与 `demo_20260717_spine.html` 对照，改一轮看一轮。
- **总根因（Fable 自己埋的雷）**：`slate_v3.css` 头部注释含 `sec-*/` 字样，`*/` 提前终止注释，注释残文变成非法选择器**吞掉整个 `:root` 令牌块**——宋体栈、圆角、阴影等自 WO-R2 交付起从未生效，正文一直退化为系统黑体/Times。这就是"气质不对"的最大来源。修复后正文/标题全面回到 Source Serif Pro/Songti 判断书排版；注释中已写明此坑。
- **门脸卡对齐样张**：kicker 补齐元信息（判断对象/数据截至/运行号）；徽章改为短词+加粗值（姿态"防守等待"经治理文本规则抽取、赔率取 payoff 冒号前短句、可信度、发布），不再截断长句；判决正文分段；空"最强异议"占位不再渲染；新增关键读数卡 aside（主要矛盾+支撑链 refs → digest 取数：中文名、大数值、分位标尺，色调按 HIGH/LOW_QUANTILE_DANGER 保守规则）。正方章节同法补 aside 读数卡，与门脸共享去重集合。
- **外部世界章节重构**：16 张全文解读卡压缩为样张式紧凑事实行（日期栏+标题+来源·等级·阅读状态），解读/待确认数据折叠进行内 `details`；前 8 条直显、其余折叠；tier 机器枚举中文化（官方源/可靠媒体转述/市场叙事·低可靠）；新增"本轮事件底账 N 条·官方源 M 条"读数卡。**模板句 headline_judgment 拟作章节总结时被 R1 回归测试拦下，裁定正确并撤回**——合规的章节总结留给紧随的综合裁决（LLM 治理链产物），"第二层 governed 摘要"另立工单。
- **综合裁决清噪**：问答"依据"由裸函数名改为可点中文引用章，investigation 伪 ref 降级为"受控调查"不可点标签（回归测试同步）；"缺口未由模型明示"占位行不再上正文；事件叙事×数据检验折叠为计数 fold；W2 补采清单人读化（占位缺口合并计数）折叠于章节末。
- **脊柱定稿**：01 正方主论证 → 02 反方压力测试 → 03 外部世界 → 04 综合裁决 → 05 改判条件（含"和上次比什么变了"折叠，独立"变化"章节及其死代码删除）→ 06 L1-L5 五层底稿 → 07 审计。改判条件回到样张整行 flip 列表；临界观察压成一行状态签；压力情景推演折叠。
- **其他**：五层关键读数卡改为"中文名小字+数值大字+标尺"（digest display_value，缺失时按 PE/百分比模式窄提取）；审计链接由全路径文本改为短标签（修复移动端 652px 横向溢出，现 390=390）；`<title>` 改为"NDX 投资判断书 · 日期"；抽屉底部动作排版修正。
- 验证：真实 run `20260719_130534` 官方路径重生成；桌面/移动截图逐屏核验；抽屉点击命中冒烟通过、零 JS 错误；页高 18167px → 12274px。R1/R2 回归断言按新等价不变量更新（tier 中文、`ev-detail` 折叠、伪 ref 人读降级、脊柱去 change）。全量 **881 passed**（基线持平），58 条既有 warning。
- 遗留（内容级，渲染器不越权代改，见 NEXT_STEPS）：L2 利差单位标注失真（8.09/2.71/0.78 标 bp 实为百分点）；外部世界缺合规 LLM 总结；final_stance 无短姿态枚举字段；W2 补采条目多为"未由模型明示"占位。

---

## 2026-07-19

### brief 二次视觉返工：正文、五层底稿与证据抽屉回到样张阅读结构

- 用户截图复核确认，上一轮虽已修复章节脊柱和暖纸色，但主论证仍被 `chain-grid` 渲染成三栏后台卡，五层底稿仍是多层嵌套卡片，抽屉还把整段说明当作大号读数；因此不能把它称为样张验收通过。
- 本轮将正方主论证改为样张的连续文章结构：`主要矛盾 → 三条支撑链 → 价格已计入什么 → 三个时间尺度`，删除该区默认的卡片栅格和机器指标标题；正文引用改为短中文标签，如「L1·10年实际利率」。
- 五层底稿改为每层一段层级摘要 + 两张关键读数卡；完整指标卡不再嵌在 brief 的折叠里，而是留在独立 layers artifact。移除了默认阅读面上的嵌套 `layer-detail`、风险代码、英文函数名以及“折叠 → 指标卡 → 卡内折叠”的后台结构。
- 证据抽屉改为人读层名与短标题；生成器明确产出短 `display_value` 和小字 `detail`，不可用/状态文本不再被当作 26px 大号值。关闭按钮回到轻量角标，问答标题恢复辅助层级。机器 ref 只保留在复制/审计动作，不再是抽屉正文。
- 验证：真实 run `20260719_130534` 已重新生成 [brief](output/reports/vnext_brief_20260719_1305.html)；新增回归测试锁定“正方无默认 `chain-grid`、brief 五层没有完整指标卡/卡内折叠、抽屉短读数与不可用状态”。`tests/test_vnext_reporter.py` **68 passed**；全量测试已执行通过，基线 **881**。

### brief 按 style-b demo 契约返工：脊柱、抽屉与控制台阅读入口收口

- **A 排版**：brief 不再依赖“查找旧标题再字符串替换”的脆弱缝合。事件事实区与第三层综合裁决改为结构化传入 `section_id` / `section_kicker`，脊柱固定为：门脸 → 01 正方 → 02 反方 → 03 外部世界 → 04 第三层综合裁决 → 05 改判条件 → 06 变化 → 07 L1-L5 五层底稿 → 08 审计；各主章节统一 `sec-head`（编号和标题同行、底线）。门脸恢复为样张的“外层章节 + 内层单张 `facade` 卡片”，长姿态不再截断成徽章；徽章回到标题后、正文前；改判条件改回 demo 的行式 `flip > dir + 文本` 结构。正式 brief 固定使用 B 样张的暖纸浅色调，不再随系统深色模式切换为近黑底。
- **B 抽屉**：引用标签在生成时从 `ref-digest` 取正式的 `层级·指标名`，字段级引用也回退至同一指标名；判决正文按空行分段；同一方括号里的逗号/顿号多引用拆成多个独立 chip；没有层级点号的普通词和 investigation 引用降为不可点文字。真实事故样本 `20260719_130534/final_adjudication.json` 已固化为回归测试。
- **C 控制台**：任务完成后的阅读组只保留「综合总报告」（native brief）、「Workbench」和（路径不同时）「完整报告」；所有 JSON 直链和废弃新闻事件 HTML 下架。event-only 同步回退至 native brief → 完整报告 → Workbench。
- 验证：真实 run `20260719_130534` 本地重生成 [brief](output/reports/vnext_brief_20260719_1305.html)，章节序列与 92 个引用逐项程序校验通过（字段级引用按 drawer 的 canonical 规则解析；逗号/无点 data-ref 均为 0），门脸判决 4 段、6 条 flip、裸 `get_` 标签 0；控制台页实际生成且仅保留阅读组。全量测试 **880 passed**、58 条既有 warning（相对此前日志基线 877 净增 3）。浏览器环境拒绝访问本地 `file://` 页面，未绕过；视觉核验保留为本机直接打开文件即可补做的一项环境限制。

### 续跑二次事故排查：假续跑根因 + L5 裸百分号，两处修复（Fable 亲查亲修）

- 事故：用户点一键续跑（job `20260719_173231_379`），L1-L4 全部重跑而非复用存档（假续跑坐实），随后 L5 两次尝试均因模型输出 `"value": -26.58%`（裸百分号，非法 JSON）解析失败，run 再次死亡。
- 根因一（假续跑）：续跑路径上 `run_pipeline` 仍然**重新采集新闻**并**重建 analysis_packet**；checkpoint 的 input_sha256 就是 packet 的稳定哈希（易变字段只豁免 `generated_at`），新闻重采带来新事件 + 新时间戳 → packet 变 → 指纹全变 → 五重防伪校验**正确地**拒绝了全部存档。防伪机制无错，错在续跑时不该重造输入。修复：resume 模式复用既有 `news_event_ledger.json` 与 `analysis_packet.json`（损坏则退回重建并留日志），指纹自然吻合。
- 根因二（L5 解析）：`_light_repair_json` 增加第四类窄修复——裸百分比数值加引号（与既有三类手滑修复同款风格），真实事故样本固化为回归测试。
- 预检验证（不花钱）：真实 run 目录上实测——packet round-trip 可加载；L1-L4 存档指纹与当前 packet **完全吻合**（将被复用）；thesis 存档因 17:36 新闻重采污染指纹将诚实重跑；data_date=2026-07-19 同日，时点闸门无碍。全量测试 **877 passed**（876 + 净增 1）。
- 复活执行：经 control service 白名单通道重新提交续跑（job `20260719_181202_954`），监视器盯复用生效与终态。

### 断点续跑一键化：run 中断不再等于全部重跑（Fable 应用户要求亲做）

- 背景：run `20260719_130534` 失败后，用户发现"重跑一遍等于数据采集和前面所有 LLM 阶段全部重付费"。续跑机制（`--resume-from-existing` + 五重指纹校验的阶段 checkpoint）其实早已存在，缺的是对人友好的把手。
- 三层把手补齐：① `main.py` 在 LLM 阶段开始前落盘 `resume_hint.json`（原始快照路径+sha256 指纹+现成的续跑命令），run 中断时日志直接打印续跑命令；② `console_run_all.py` 新增 `--resume-run-dir`——自动从档案找回原始数据快照并核对指纹，**对不上就拒绝执行**（原始采集文件被后续采集覆盖时，续跑会退化成全量重跑，宁可明说不可假装复用）；③ 控制台新增"断点续跑"卡片：服务端 `/resumable` 接口侦测中断 run（有档案、缺终点产物、快照指纹完好），页面一键提交白名单命令，跨日续跑显示"会被时点闸门降级为审计参考"的提示。
- 已为 `20260719_130534` 补写档案（该 run 中断于机制诞生前），实测侦测正确：快照指纹完好、同日、命令可用——控制台打开即可一键续跑，只补付最后一步的钱。
- 验证：6 条新测试（档案写入与指纹、resolver 拒绝篡改快照、console 传参、/resumable 候选过滤、页面元素）；控制台页面实际生成并核对；全量 **876 passed**（870 + 净增 6）、58 条既有 warning。

### W3 首次 live 实弹暴露三处不优雅：长期评估字段违规炸掉整次 run（Fable 亲自排查修复）

- 事故：run `20260719_130534` 在 final_adjudicator 两次尝试后整次失败。attempt 1 五个校验错误（含假说结构体被 `List[str]` 拒收 + reasoned_verdict 超长）；attempt 2 修复了前述问题，却因 `valuation_implied_return` 含百分比且未附 evidence_refs 触发 W3 硬 validator，run 陪葬。这正是 W3 验收时申报的"未做真实 LLM 在线抽样"剩余风险的实弹兑现。
- 亲读 prompt_audit 原文后定性为三处设计不优雅，而非模型能力问题：①**提示词与合约打架**——提示词要求每条假说"注明证据状态"，模型合法产出 `{hypothesis, evidence_status}` 结构体，合约却只收纯字符串；②**百分比拦截误伤**——validator 意图是拦"编造年化收益"，正则却打中"PE 71% 分位、10Y 名义 4.57%"这类提示词明确鼓励引用的输入事实；③**爆炸半径失当**——可选辅助字段的违规炸掉整个 run，违背系统"降级不断链"惯例（confirmed 无证据自动降级、audit_only 引用降权、W1 audit_only 同理）。
- 修复（`contracts.py`，架构对齐既有"宽容归一化 + 硬闸门"分层）：严格核心不动——直接构造 `LongTermAssessment` 时 % 无 refs 依然拒收；`FinalAdjudication` 的 LLM 边界新增 `_normalize_long_term_assessment_payload`：假说结构体归一为"假说（证据状态：…）"句子；含 % 无 refs 的估值隐含回报**字段级 fail-closed**（清空 + uncertainty_notes 留痕注明原文在 prompt_audit），违规数字依然进不了报告，但 run 存活、其余合法内容保留。
- 验证：用事故 run 的 attempt 2 真实 payload 整体回放 `FinalAdjudication.model_validate` 通过（估值字段清空留痕、三条假说与对象质量全保留）；两份真实事故原文固化为回归测试；全量 **870 passed**（868 + 净增 2）、58 条既有 warning。

### 第一性原理工单包 W1-W7 全部完工验收（Codex 施工约 2 小时不间断，Fable 逐单亲验，统一提交）

- 施工方式沿用既定分工：Codex 按 `investigation_reports/20260718_first_principles_debate/WORK_ORDERS.md` 逐单顺序施工、逐单更新状态行、全程不提交；Fable 定时验收（监视器盯完工信号），逐单读关键改动、核状态行、亲跑全量测试后统一提交。**868 测试全绿**（基线 800 + 新增 68），与 Codex 自报一致。
- **W1 时点契约硬闸门（骨架级）**：综合报告所有输入必须同一 as_of 日历日；`_check_time_consistency` 收集五类日期，"≥2 且全等"才放行，缺日期/无效日期/错配一律 fail-closed 为 audit_only 并在 blocking_reasons 写明具体日期；时点不一致时 LLM 裁决直接跳过；报告页警示条上线。DEBATE.md 终审抓到的"7-14 数据 + 7-18 事件卡照常盖章"漏洞正式堵死。
- **W2 缺口受控反馈**：run 落盘 `recollection_requests.json`，只从三处结构化缺口字段复制文本（代码结构保证够不到判决正文），候选函数经 Evidence Registry 核验不猜；报告审计区新增"下轮建议补采清单"。
- **W3 长期资产评估层**：`LongTermAssessment` 合约上线（3-5 年以上判断与 6-12 月周期姿态分离，% 回报数字无 refs 拒收）；Fable 亲笔提示词逐字入 final_adjudicator；核心仓动作展示层强制带"须经个人投资政策书与再平衡带确认"。
- **W4 预期-兑现台账**："已定价"从断言变测量：`expectation_vs_realized.json` 三分册（自建 vintage 盈利修正、利率路径定价 vs FRED 实际兑现、VIX 隐含-实现溢价），全程 PIT、`supporting_only`、主链失败不阻断；priced_narrative 强制带分歧声明。
- **W5 评分归因台账**：已评分 claim 带保守 `error_taxonomy`；`method_revision_ledger.jsonl` 空台账 + 严格写入校验（commit 必须真实存在）建成，7-27 首批成熟评分的复盘流程写入 RUN_REVIEW_CHECKLIST（Fable/用户主持，系统不自动改方法）。
- **W6 类比数据史审计**：独立脚本审计 DFII10/HY OAS/NDX 估值谱系/VIX 的干净 PIT 历史，结论 **`rejected_insufficient_clean_pit_history`——不准入任何类比引擎**（合格产出：诚实回答"样本不够"）；顺带查明 FRED 自 2026-04 起对 HY OAS 只开放三年访问窗。
- **W7 官方仓位数据**：CFTC COT（NQ Legacy，周二快照+3 天可见）与 FINRA 融资余额（月末+21 天可见）两条官方源上线，field-level `supporting_only` 全套权限/判读卡/升级路径；ETF 申赎资金流无官方免费源，诚实不做记入数据边界。
- **W8 事件研究**：维持冻结，验收确认无越界实现。
- 剩余低风险如实保留：W3/W4 未做真实 LLM/FRED 在线抽样，W7 本机 CFTC API TLS 失败（诚实 unavailable），均留待下次 live run 自然覆盖。逐单验收细节见工单包"验收记录区"。

### 三层架构第一性原理对辩：Fable 立场书 + Codex 质证 + Fable 终审（纯审查，零代码改动）

- 起因：用户在 R1-R8 收官后自问"三层架构是不是业余胡乱猜想"，要求从金融与判断科学的第一性原理审查一/二/三层逻辑是否有根本缺陷。采用用户提议的共享文档对辩制：`investigation_reports/20260718_first_principles_debate/DEBATE.md`，双方轮流追加、署名、互不改稿、每论断带 repo 证据或原理推导。
- Fable 第 1 轮：六项原理（回报恒等式/共识偏差/低信噪比与基础比率/反身性/校准/用户 IPS）推出候选发现 F1-F6；先做事实核查，两处自我预设被真实系统推翻并如实记录（time_horizon_views 真实填充；仓位数据并非空白）。
- Codex 第 1 轮（gpt-5.6-sol high）：逐条裁定 + 两条新发现 F7（最长时间尺度仅 6-12 月却直接给核心仓动作，缺 3-5 年层与个人决策政策分离）、F8（跨层双时点一致性缺失：7-14 数据+7-18 事件卡仍判"可发布+允许正式结论"）；反驳 F3（`news_event_data_linker.py` 早已存在，temporal_association-only）。
- Fable 终审：Codex 五条硬引用逐一亲验全部属实；F3 认账撤回（现状判断错误）；F8 采纳并补诚实说明（错配输入系 R8 混合注入所致，但闸门放行是真实系统行为=意外渗透测试）；F1 降级采纳（六道防线为准入条件）。**终审结论：三层划分不动；唯一骨架级缺陷=层间时点契约与 run 生命周期（F8）；优先序 F8>F7>F2>F6>F1>F4>F3（条件性远期）。是否立案待用户拍板（NEXT_STEPS 开关 4）。**

### R8 第三层真裁决终稿：Fable 亲做 + Codex 红队 + 逐条裁决（重构工单包 R1-R8 全部关单）

- 流程按用户指定：Fable 亲自实现 → Codex 红队（只读沙箱，15 条发现全部带可复现证据）→ Fable 逐条裁决（C1-C5 全采纳、I 类 6.5/7、M 类 4/4，两处部分采纳均记明理由）→ 修复终验。
- 实现要点：`IntegratedAdjudication` 合约族（姿态锚+证据联动 validator）；builder LLM 裁决级（effective_date/ref_authority/调查白名单入载荷、不可信材料声明、宽容归一化+伪引用硬闸门、confirmed 无证据自动降级、调用异常降级、invocation 级审计）；Fable 撰写裁决提示词（数据判决为锚、六档证据分级、PIT 与权限纪律、注入防护）；报告新增"第三层·综合裁决"章节——**"新闻出题、数据回答"闭环首次可见**。
- 红队最重要的裁决：门脸署名切换暂缓（C1：形状校验防不住正文实质改判），第一层 reasoned_verdict 继续坐镇门脸，第三层正文在本层章节完整呈现；语义锚机制另立小单后再切换。
- 终验：800 测试全绿（794+6 红队回归）；live 三轮迭代后终版 1386 字对质正文（四事件卡标注、五风险点名、6 题全答、16 条纯净 data_support），权威纪律进入模型行文。闸门实弹记录：一轮 live 中 8 条包裹式引用被硬闸门全数拦截（后以格式别名归一放行合法部分）——伪引用防线被真实验证。
- DeepSeek 消耗：R8 验证共 4 次真实调用（含红队前 2 次）。

### 充值后收尾：R3 关单、两批工作合并提交并推送 main、R6 派工（Fable）

- 用户充值 DeepSeek 后，R3 判决正文完成三轮实证迭代定稿：v2（788 字，风险全点名但标注归零）→ v3（1198 字，10 标注全解析、五风险全点名、权限内联自标、失效条件双向，Fable 亲读合格）。裁定字数带按现实修正（提示词 600-1200，机器校验带 300-1300，`contracts.py` + 两处测试 fixture 同步），实质要求全程未放宽。验收样本存档 `investigation_reports/20260717_redesign/r3_v3_acceptance_sample.json`。**R1-R7 七单全部关单。**
- 用户拍板"可全部提交、仓库保持公开"：两批已验收工作（07-17 方向 1-4 收口 + 07-18 重构 R1-R7）合并为一个提交 `afc44a6`（55 文件，+7647/−722；两批在共享文件上交织，按文件粒度无法干净分离，提交信息分批说明并指向各自 WORK_LOG 条目）。main 快进至 afc44a6 并推送 origin（连带此前滞留的 922acc6/aa71398/c183897 一并上远端），工作分支同步推送。775 测试全绿后提交。
- R6（LLM 事件卡）派工：Fable 决定继续用 Codex（本轮表现优秀），直连 CLI 配方后台开工；验收后再提交。docs/superpowers/（07-17 施工计划文档）经查阅后一并入库。

### 定时验收第二轮：R1-R7 六单中五单验收通过，R3 余额阻塞待重验；slate_v3 皮肤交付（Fable）

- 用户亲自重跑的 Codex 完成全部五单施工（R3 06:20 / R4 07:10 / R7 07:23 / R5 08:21 / R2 08:52），全程未提交（遵守本波纪律）、逐单更新状态行、两处语义疑点诚实上报不冒充通过。Fable 逐单亲验：775 测试全绿亲跑（基线 721+54）。
- **R2 验收通过 + CSS 交付**：体积/复读/digest（23.9KB/42 指标）/锚点/脊柱顺序断言逐项复核；Fable 交付 `report_styles/slate_v3.css`（令牌契约同 slate_v2、B 风格、深色模式、新钩子+旧类双覆盖、抽屉组件移植），默认样式切 slate_v3（方法+CLI 默认、后缀规则、1 处测试同步）。v3 成品 `vnext_brief_20260715_001617_v3.html` = **92,198 bytes，较原版 744KB 降 87.6%**，104 类程序化全覆盖。
- **R4 验收通过（Fable 裁决）**：三份真实调查报告亲读——两份完全合格；信用报告"语义倒置"裁定为格式歧义非实质错误（实为对"扩散恐惧"的合法挑战，先写结论后名主张），下游降级为保守 kept_unresolved 无污染。**`downgrade_or_split_events` 机制建成后首次开火（17 run 恒零 → 1）**。调查员提示词加一行澄清（challenged 放被削弱的原主张）。
- **R5 验收通过（Fable 亲验）**：Clash diff 恰三条域名同 SEC 节点其余未动（备份 `clash-verge.yaml.backup_20260718_075019`）；live 底账 Fed/BLS/BEA 零错误、9 条官方日历事件、2024 泄漏=0、未来项物理隔离（21 条独立日程）、零默认实体误标；新闻模块零 L1-L5 标签残留；"窗口外"3 条经盘问实为按 event_date 归窗的日历项，语义正确。
- **R7 验收通过（Fable 亲验）**：2 candidate 各一 response，absorb_partially 带 3 refs 理由充分，reject 带 5 个合法 refs 点名具体反证。
- **R3 代码验收通过、live 正文阻塞**：Fable 亲读 396 字失败样本裁定为提示词约束交互过紧非模型能力问题；定稿提示词升 v2（字数 450-800、风险短语点名制、audit-only 数值禁令），验证驱动持久化 `investigation_reports/20260717_redesign/r3v2_verdict_driver.py`。执行时发现 **DeepSeek API 402 Insufficient Balance**（Codex 凌晨 8 次重试耗尽余额）——充值后跑驱动+亲读即关单；这同时阻塞一切 live LLM run。
- 过程记录：resume 重放曾遇 L1 空响应，根因即 402；直连驱动（复用 prompt_audit 审计件换血 v2 文本）为后续同类验证留了轻量路径。

### 定时验收第一轮：R1 通过；Codex 半夜停工，剩余五单经 rescue 通道重派（Fable）

- 05:23 定时验收启动。取证：Codex 于 00:28-00:29 完成 WO-R1 代码后未提交、未更新状态行即停工，其余五单零痕迹（git log 无 WO-Rx 提交、无 WO 指纹、无活动进程）。
- R1 验收通过（Fable 亲验）：721 测试全绿（基线 714+7）；重生成 brief 断言全过（美光模板=0、拼接 bug=0、罐头复核区消失、决策翻译"无模型参与"、16 张主线新闻卡带来源/tier/日期）。Fable 补修一处小瑕疵：`published_at` RFC/ISO 混合格式统一为 YYYY-MM-DD（`vnext_reporter._display_date`）。
- **git 纪律修订**：本波施工不做任何提交——工作树混有 2026-07-17 方向 1-4 收口批次的未提交改动，按单提交会互相污染；改为整批验收后与用户确认统一提交方案（已写进工单包总纪律）。
- 剩余五单（R3→R4→R7→R5→R2）经 codex-rescue 通道重派，git 纪律修订与 R5 步骤 0 沙箱降级预案已随派工下达；3 小时后有兜底复查。

- 对最新 run `20260715_001617` 及 brief 做四问诊断（报告疲劳/新闻管线/交叉质询/推理机制），三条并行取证线 + Fable 逐项亲验。核心结论：① 报告"累"的病根是四阅读层级被压扁成滚动条（判断句复读 7 次、新旧冲突卡双份、隐藏 JSON 占文件 53%），CSS 工程本身合格；② 新闻子系统全程无 LLM（12 桶关键词模板冒充"AI 分析"，模板错配/截断/拼接三类 bug 实证），本次 run 官方源（Fed/BLS/BEA/SEC×7）全部 SSL 失败，`effective_date` 为空时 45 天窗口被旁路（2024-07 事件混入），实体兜底把英国房企公告标成全 M7；③ 数据链内交叉质询真实（Bridge typed conflicts + Critic 真命中），新闻-数据"综合"是两句模板文案二选一；④ 受控追问只有骨架（`is_deterministic_stub` 恒 True，"本轮未执行真实调查"），竞争假说真实健康（3 假说、反方独立性可审计），非单调降级机制 17 个 run 从未触发（触发源被 stub 堵死）。
- 结论对照两份 2026-07-03 设计文档：认识论架构报告实施率约六成、未实施的恰是灵魂件（第二层 LLM 卡/第三层真裁决/追问执行器/非单调触发）；Gemini 报告三条病理诊断全部实证命中、处方（编造权重阈值/Neo4j/动作矩阵点位）不可采信。
- 最终裁决"太碎"根因实证：`final_adjudication.json` 30 余个文本字段最长仅 140 字，合约无成文论证字段——立"判决正文双轨"方案。
- 用户拍板决议清单 v3 → 立工单包 `investigation_reports/20260717_redesign/WORK_ORDERS.md`（R1 模板三类处置 / R2 脊柱重排 / R3 判决正文双轨 / R4 受控调查执行器 / R5 新闻官方日历底账+三 bug / R6 LLM 事件卡 / R7 Thesis 强制回应竞争假说 / R8 第三层真裁决范围锁定），全部 LLM 提示词原文已由 Fable 定稿内嵌，Codex 施工、Fable 验收。
- 报告样张 `output/reports/demo_20260717_spine.html`（Fable 亲做，正方先行脊柱 + A/B/C 三排版风格切换，内容全部取自真实 run，判决正文段为字段素材手工合成的形态演示）。等用户选型后 R2 开工。
- 待用户两个开关：Phase 0 Clash 放行 `www.federalreserve.gov`/`www.bls.gov`/`www.bea.gov`；样张 A/B/C 选型。

### NEXT_STEPS 方向 1–4 收口（盈利预期保持暂停）

- 旧快照兼容：只把“没有新合约、没有有效值、且带明确采集失败文本”的旧 payload 从伪 `available` 归一为 `unavailable`；新合约空值继续硬阻断。复核 `20240805` / `20250409` / `20260509` 三份旧快照，全部仍为 `blocked + unpublishable`；2024 快照的未来估值、2025 的 L3 低覆盖、2026 的 L4 低覆盖都没有被洗白。
- 独立重算输入：采集器把生产函数返回的长序列移到顶层 `recompute_inputs`，写 SHA256 后再供纯 stdlib 第二本账使用；`AnalysisPacketBuilder` 测试确认该附件不进入 L1-L5 raw_data / prompt。L5 增加完整 PIT 截断 OHLCV，第二本账独立实现 SMA/RSI/MACD/ATR/ADX/DI/OBV/MFI/CMF/Donchian/VWAP；L1/L2 增加长窗口 value series、动量和分位重算。
- 真实 live 采集后复核：此前 61 个 `unrecomputable_missing_raw` 降为 6。最终落盘快照（46 指标，2026-07-17 18:25 完成）共 223 项，217 match、0 deviation、6 missing raw、0 uncovered，覆盖率 97.31%，critical deviation=0，DataIntegrity=86.6%、publishable。本轮 Wind 不可用使检查总数少于前一次；6 个保留项是 ERP 上游缺值 1 项和第三方检查字段缺原始序列 5 项，没有冒充已覆盖。
- 重算账本钓出并修复旧 bug：`analyze_series_momentum_relativity` 收到 `date` 列 + RangeIndex 时，1 年分位曾退化成全历史；现在按日期列截取真实 1 年窗口。VIX3M/VIX 分位重算改为由两条未舍入的腿独立相除，避免四位小数排名产生假偏差。
- 权限纪律：8 个弱权限指标（VIX、VXN、铜金比、HYG、XLY/XLP、拥挤度、VXN/VIX、CNN 恐贪）统一由证据归一层补 `metric_authority` 与 `downgrade_rules`；真实拥挤度字段名已对齐，合并采用最小权限胜出，旧 payload 不能把 supporting/audit-only 抬为 core，未知字段或非法 usage 枚举统一 fail-closed 为 audit-only。Evidence Passport 继承这些规则，且 unavailable/无有效观测值一律 `verified=false`。
- 盈利预期：未实现 Top 15 forward EPS、自建全指数 forward PE 或 FMP/Finnhub；HoM 继续只作第三方参考。来源名、methodology、formula、notes、coverage 与上游 metadata 中所有 Bloomberg BEst 表述均统一加“HoM 公开 API 自述归因、未独立核验”限定；递归测试扫描完整 payload，避免任何运行时字段误标 Bloomberg 官方源。
- 个人决策出口：`UserDecisionProfile` 只读取 tracked/local 文档里的 `reader_exit` 白名单，金额与持仓字段不会进入模型或报告。空纪律不再静默通过或启用默认阈值，而是生成 `profile_disciplines_unconfigured` 闸门。状态变量补 evidence ref、单位、允许比较符；Wind PE 分位路径修正为 `PEHistoricalPercentile`；阈值必须 `confirmed` 且单位匹配，否则 `insufficient_evidence`。
- Golden Pit：predicate 条件引用 Evidence Registry 可解析的完整字段路径，并生成 predicate 专属失效条件；派生回撤同时引用 Donchian 上轨与 QQQ 价格，未注册引用会 fail-closed。无 predicate 的旧条件才使用 claim 级 refs/falsifiers 兜底。
- 输出体验：新增 HY OAS、ADX、MACD 等静态本地术语解释，支持 hover/focus/click 与键盘，重复术语使用唯一 tooltip ID 且同步 ARIA 状态；新增 `source_snapshot.json`，报告展示快照模式、文件名、真实 SHA256、真实采集时间、有效日。pipeline 与 event-only 都会在创建产物前拒绝把 live/未标日期快照重贴成历史。简洁研究控制台沿用既有实现并纳入验收。
- 最终审查补强：快照内旧式 `raw_data.recompute_input` 会迁移到顶层审计附件，AnalysisPacket 和最终 prompt 各自再清洗一次；live/undated 快照搭配历史 `--date` 直接拒绝；实时审计缺文件或时间时写 `not_recorded`，不再生成看似完整的占位值。
- 方向 5 评估后暂不动工：巨型文件拆分、恒零调查 stub 和历史 docs 归档都需要独立设计/迁移验收，本轮贸然修改只会扩大回归面。
- 未提交、未推送；保留用户原有 `.codex/*`、`NEXT_STEPS.md`、`WORK_LOG.md` 和调查文档改动。

验证：

- 首次全量：`693 passed, 2 failed`；两项均为 VIX 新独立公式与旧测试夹具当前值选择不一致，已修正后定向 `5 passed`。
- 最终全量：`714 passed, 58 warnings in 41.61s`（项目 `.venv` / Python 3.12）；warning 均为既有第三方弃用提示或测试夹具的数值精度提示。另有 legacy/DataIntegrity、recompute、authority、state ledger/orchestrator、HoM、reporter、console 等定向测试全部通过。

---

## 2026-07-16

### SEC YKK 路由恢复与 HoM 单路优先判断

- 检查 Clash Verge 当前生效规则：FRED 的 `api.stlouisfed.org` / `fred.stlouisfed.org` 走 YKK，其余未单独列出的外部域名走 `AI-Chain` → IPRoyal。
- 只新增一条 `DOMAIN,data.sec.gov,🇺🇸 UnitedStates 02` 规则并重载 Clash；没有改 FRED 规则，也没有把 Yahoo、GitHub 或其他外部域名切到 YKK。
- 对照验证：未改路由时 SEC 仍为 `SSL_ERROR_SYSCALL`；YKK 临时通道访问 `data.sec.gov` 的 submissions 与 companyfacts 均 HTTP 200；项目实际调用 `_fetch_sec_xbrl_summary("AAPL")` 返回 `availability=available`，AAPL 的 capex、回购、收入和稀释 EPS 均命中，最新 filed date 为 2026-05-01。
- HoM 实时获取验证：`https://historyofmarket.com/api/ndx/forward-pe.json` 可用；trailing PE=34.21（2026-07-16，当前可用），forward PE=24.29（数据尾日 2026-05-18，代码正确标记 `stale_for_decision`，不可作当前决策值）；forward 历史 298 点、2008-10-31 起，percentile=68.5 的计算链可重算。
- HoM 来源复核：公开站点将自己定位为独立数据聚合与历史图表站；forward PE 页面声称采用 Bloomberg BEst，但站点总说明同时写明 Bloomberg forward-PE 文件“manually maintained”。因此 HoM 不是 Bloomberg 官方直连接口；`updated=2026-07-16` 只是数据包更新时间，forward 历史尾值仍是 2026-05-18，说明上游 forward 序列没有跟随包更新时间同步延长。
- 主审判断：暂不实施工单 #18 的“前 15 权重股 forward EPS 自算”主路；先把 HoM 的来源、字段一致性、更新时间和历史回放验证扎实。前 15 自算保留为低优先级备选，不进入主证据链。
- M7 主路验收：live 与 `effective_date=2026-06-01` 的 PIT smoke 均通过。资本开支 7/7 家走 SEC、均 `pit_safe=true`；回购 6/7 家走 SEC，1 家缺官方字段且未偷偷用 yfinance 补齐，保持诚实缺失。资本开支最新覆盖到 2026Q1，合计 $90.011B，来源为 `sec_xbrl`。

收尾判断：SEC 路由和 M7 主路已恢复；旧文档中“SEC 生产中从未成功”的表述已改为“当时默认路径失败”。历史记录显示旧 `companyfacts` 官方交叉检查曾有 20/20 成功，后续失败是路径/代理问题，不是 SEC 数据从未拿到过。

---

## 2026-07-14

### 数据基础三连修 + 证据菜单再平衡收官 + DataIntegrity 家族计分 + 对称性审计（Fable 编排，两轮并行施工）

完成内容（提交 `922acc6` 波次一、`aa71398` 波次二、本批文档与对称性补丁）：

- **幸存者偏差硬防线（红线修复，新工单 #19）**：调查证实 `get_ndx100_components` 在回测模式历史库失败时会静默穿透到四条"当前名单"策略（只留一条不进审计流的日志）。修复：回测分支只信任 `nasdaq_100_ticker_history`，失败即抛 `HistoricalUniverseUnavailable`（tools_common 定义），绝不落回；广度四件套与 L4 成分股快照捕获后返回诚实 unavailable（照 `get_qqq_top10_concentration` 样板）；全路径（历史库/官网API/Wikipedia/GitHub库/静态兜底）返回 `universe_provenance`（来源/as_of/数量），随共享面板缓存透传进 payload data_quality；"回退往年年末"近似分支如实声明实际名单日期与近似性质（Fable 补）。6 个新测试含"策略被调用即炸"的反向断言。
- **手工数据槽位边界收紧（工单 #7 完成）**：Damodaran ERP 槽位新增 `manual_source_type` 来源声明（非 `damodaran_official` → anomaly `erp_independence_compromised_manual_source_not_damodaran`/`manual_erp_provenance_undeclared`，防三 ERP 声部静默塌缩）；六槽位模板声明 `primary_fields`，`has_meaningful_manual_override` 只认主字段（填 1 个元数据字段不再整条冒充人工覆盖）；人工数据超 120 天/无日期 → `manual_data_stale`/`manual_data_date_missing` 标注。全部只标注不阻断。12 个新测试。
- **利率预期路径缩水版上线（工单 #4，新指标 `get_fed_funds_rate_path`，L1，Codex sol 施工）**：13 个月 ZQ 单月合约（ticker 实测 `ZQ<月码><年>.CBT`，+18 月未挂牌 404 证实缩水到 12 个月合理）；隐含利率=100−价、路径+斜率+三态分类（±12.5bp 缓冲带）、流动性三级分级（<5 剔除/<100 降级标注）、EFFR 锚偏差>0.35pp 标注；PIT 逐合约截断；easing_priced 明文禁止单独作流动性利多（须与 HY OAS/增长交叉验证）。belt 独立重算 implied/slope/cuts 并防协调篡改。live 实跑：`tightening_priced`，未来 12 个月定价约 51bp 收紧。
- **回购与财报静默期日历上线（工单 #4 收官，两个 L4 新指标，Codex sol 施工）**：`get_m7_earnings_blackout_calendar`（财报日−21/+2 天规则窗，规则参数入 payload 可重算；PIT 用已实现财报日作当时日程近似并如实标注；live：6/7 家在窗、等权占比 85.7%，与 7 月底财报季完全吻合）；`get_m7_buyback_flow`（镜像 capex 双通道：SEC XBRL 主路+Yahoo 备胎 pit_safe=false；live：2026Q1 可覆盖 5/7 家合计 $20.73B，TTM 因覆盖不足诚实留空不冒充 M7 全量）。belt 重算窗口/季度标签/TTM/可比集合。
- **DataIntegrity 证据家族计分（GOV-04/P0，新工单 #20，Sonnet 施工）**：新建 `src/core/evidence_families.py`（46 函数全量映射+分组理由行内注释；未映射 id 单例兜底=老合成测试期望值零改动）；`confidence_percent` 改家族计权（同源函数共享家族权重，L5 11 个技术函数从 11 票并成 1 票），惩罚量不变但分母变小=只紧不松；新增 `function_availability_percent`（旧公式保留）与 `family_coverage` 块；层级及格线保持函数口径（他单产物，边界注释写明）。真实 run 重算：函数口径 95.3% vs 家族口径 92.6%，publishable 不翻转。Fable 裁决：HoM 估值与成分股自算拆为两个家族（生产默认路径不同源，20260712 run 一活一死实证两条流）。
- **多空证据源对称性审计（工单 #4 尾项，Explore 枚举 + Fable 裁决）**：46 函数三处编码（canon/payload/prompt）逐一核对。**裁决：证据菜单不再先天偏空**——31/46 双向、0 个只准乐观、8 个只准风险，其中 5 个不对称是认识论正确（IG 稳定≠股票安全、拥挤度低≠买入信号、正挂常态无利多信息等）；3 个真缺口已当场补齐（%Above MA 修复方向获得与 A/D 同等的削弱风险许可、HYG 修复+OAS 收窄可作确认证据、实际利率高位回落可作估值承受力改善证据但须区分衰退式回落）；VIX 期限结构 payload 的倒挂 reason 补上法典已授权的"战术仓逢恐慌分批确认"用途说明，消除 payload/canon 文本失调。系统性遗留（8 个弱权限指标缺 payload 级 metric_authority，canon 纪律无法运行时强制）立新工单 #21。
- **L3 广度 + History of Market live 验收（Fable 亲跑 `--collect-only`）**：广度四件套 4/4 available、成分覆盖率 98.06-100%、universe_provenance=nasdaq_api/103 只；HoM trailing 分位 45 点/64 天正确撤回（`insufficient_history`，双门槛 200 点/270 天），forward 分位 298 点正常给出 68.5 并独立标注 `stale_for_decision`；三个新指标 live 全活。4 个 Wind 依赖指标因 Wind 终端未开诚实降级（upstream None），fresh 快照家族口径 86.6%/函数口径 91.2%，闸门未阻断。

验证结果：

- 全量测试 611 → **670** 全绿（波次一 641、波次二 670，每波 Fable 亲跑复核，非仅采信施工报告）。
- 施工方关键结论全部主对话二次核实：幸存者防线 diff 逐段审读、家族映射表逐行验收并当场改判一处、codex 两单均有独立 reviewer 两轮复核 + Fable 抽查边界编码。
- live 冒烟与 collect-only 数字均与外部现实交叉吻合（M7 静默窗与 7 月底财报季一致、NVDA 8 月底财报不在窗内）。

剩余边界：

- 8 个弱权限指标（get_vix 等）缺 payload 级 metric_authority/downgrade_rules → 工单 #21 待开工。
- 回购 TTM/YoY 在 Yahoo 免费层对 AMZN/TSLA 无回购行时诚实留空；SEC 复活后主路可补全。
- Wind 四指标本次 live 降级是终端未开所致，非代码回归。
- 旧快照回放兼容（#11）与 61 个 belt 缺原料字段未动，仍是数据基础最大的两块遗留。

---

## 2026-07-13

### 个人决策画像接线（工单 #17）

完成内容：

- 权威来源 = 用户个人投资政策书（`2026-06-29.个人投资政策书.md`）。真实参数（净资产约数、流动性下限、月支出估计等）落盘 `config/user_decision_profile.local.json`——已被 `.gitignore` 的 `config/*local*.json` 规则覆盖，`git check-ignore` 验证生效；`config/user_decision_profile.json`（git 跟踪）改写为纯 schema 占位，不含任何真实金额。
- `vnext_reporter.py` 的"个人决策翻译"区改为确定性模板（`_personal_policy_translation`，无 LLM 调用，结构上不读取 profile 里任何金额字段）：按 `_classify_investor_stance` 关键词分类出防御/乐观/中性三支固定文案，说明本轮判断对"部署规则"实际能不能构成暂停/加速理由；再列出带【转多】标签的失效条件（无则诚实占位，不脑补点位）；再列风险条件并固定追加"市场涨跌不构成修改政策的理由"；固定免责尾注。
- 13 个新测试覆盖三分支文案、转多标签有/无、风险条件回退链、画像未配置时的隔离占位、金额永不渲染断言（含假数字 fixture）、`.gitignore` 生效验证；顺带清理因卡片重设计变成孤儿的 `.profile-list` CSS 规则。611 全绿（Fable 亲跑复核，非仅采信施工报告）。
- 用真实 run `20260712_221916` 重生成 brief，逐字核对渲染文本与模板一致；对全部 git 跟踪文件和重生成的 HTML 做金额扫描（`git grep`/word-boundary grep），确认 100000/300000/3787 等真实数字零泄漏。

验证结果：

- 全量测试 611 通过（598 基线 + 13 新增）。
- Fable 独立复核：`git check-ignore -v` 确认真实数据文件被排除；`git grep` 扫描全部 git 跟踪文件确认零金额泄漏；亲自重跑测试与全链验证，未仅采信施工报告。

剩余边界：

- `config/user_decision_profile.json`（git 跟踪版）被清空后，golden-pit-checklist 依赖的 `buy_disciplines`/`sell_disciplines` metric_predicates 阈值随之降级为空条目——这些阈值本来就是未经用户逐条确认的草案（见 `NEXT_STEPS.md` P1"用户确认个人决策档案阈值"），不算真实回退，但待用户确认后需要重新决定阈值该落 tracked 占位文件还是并入 local overlay。
- 投资者姿态三分类（防御/乐观/中性）为施工方设计选择，工单原文只要求两个方向；如需改回两档可另提小单。

---

## 2026-07-12

### 独立重算校验带、M7 资本开支周期、VIX 期限结构（当日追加）

- 独立重算校验带 `src/recompute_belt.py`（纯 stdlib 第二本账，零管线 import）：分位/比率/均线/动量重算 + 量级哨兵，接入 checker 硬闸门（critical deviation → blocked，standard 只记录，总开关可应急豁免，带自身崩溃不炸闸门）；live 快照实跑 0 偏差，Damodaran 分位与净流动性两本账咬合，注入式篡改与单位混用均被抓获。
- 新指标 `get_m7_capex_cycle`（L4）：SEC XBRL 主路（filed_date 级 PIT）+ yfinance 季度现金流备胎（pit_safe=false、仅限 live、回测禁用）；当时该次运行因 SEC 域名不可达而未走通官方主路，实跑的 $135.5B、YoY +75.52% 不能推出“生产中从未成功”。后续历史产物已有旧 `companyfacts` 20/20 官方成功记录；当前应表述为“默认代理路径曾失败”。
- 新指标 `get_vix_term_structure`（L2）：VIX3M/VIX 比值+contango/backwardation 判定+5y/10y 分位；payload 自带原始序列供第二本账独立重算（新规矩首次落地）；2024-08-05 历史极端倒挂回测验证吻合。fed funds futures 免费源探源完成（ZQ 合约可行但远月流动性薄，CME 不可达，建议缩水版）。
- 测试推进：530 → 577 全绿；main 分四批推送至 `58125a1` 后续。
- 全链 E2E 验收（工单#10）通过：run `20260712_221916`，publishable 93.2%、belt 0 偏差、claim 7/8（唯一降级为真命中）、两个新指标全链零越权、Critic 抓住并修正一次真实过度悲观、四份报告正常生成；新 prompt 首次正式姿态经人工审定合格。钓出 coverage-factor 子串误读与 Schema Guard 两处疑似误报（WORK_ORDERS #14/#15）。
- checker 判决可回放（工单#6，Codex gpt-5.4 施工、Fable 验收）：`checker_input_snapshot.json` + `checker_input_sha256`；边界回归测试补齐；580 全绿。
- Codex 分流通道打通：`codex exec --sandbox workspace-write -m gpt-5.4`（repo 配置的 gpt-5.6 账号不支持、gpt-5.6-luna 需升级 CLI）；脏活默认走 Codex，Fable 负责规格冻结与 diff 级验收。

### 校准闭环通电、盈利预期 vintage 档案启动、首次推送 main

完成内容：

- 首次将全部第一性原理重建工作合并推送到 main（`59d6d96..323bc88` 后续增量到 `ddc08c9`）；此后每批工单验收后推送一次。
- 校准闭环通电（工单#2）：新增 `src/agent_analysis/outcome_scoring_runner.py` 批量打分器——扫描 vNext run、≥20 自然日成熟门槛、复用 `outcome_review.py` 判定逻辑对照 QQQ 后向价格窗口，落 per-run `claim_outcome_scores.json` 并幂等 append `output/state_ledger/claim_outcome_ledger.jsonl`；每条打分带 `data_quality_caveat`，未成熟窗口标 pending 不硬打分。
- 盈利预期 vintage 档案启动（工单#4 前置）：新增独立脚本 `src/vintage_archiver.py`，每日快照 NDX 前 15 权重股的 yfinance eps_trend/eps_revisions/earnings_estimate/revenue_estimate + FMP analyst-estimates 原始响应至 `output/vintage_archive/YYYYMMDD/eps_consensus.json`；隔离观察数据，不入 L1-L5 证据链、不得作 evidence_ref；2026-07-12 第一份档案已落盘。定时任务未安装（建议 crontab 见工单报告）。
- Wind 美股盈利预期判死（实测：茅台对照证明 PIT 机制通、AAPL/NDX.GI 无数据=账号无美股一致预期权限）；yfinance `eps_trend` 实测提供 90 天后视镜，修正斜率立即可算。

验证结果：

- 全量测试 535 通过（530 基线 + 5 档案测试；校准打分器 7 项测试已含在 530 内）。
- 批量打分器实树运行：15 个候选 run 全部因太年轻被诚实跳过（零编造判定）；判定语义经受控 fixture 三样例人工复核。首次真实成熟打分预计 2026-07-27 后。
- 档案首日快照：15/15 yfinance 成功；11/15 FMP（MU/GOOG/AVGO/AMAT 被免费层 402 挡住，逐票诚实记录）；Invesco 持仓接口 406 时静态回退生效并如实标注。

剩余边界：

- 旧快照回放兼容性问题（L3 `available_without_meaningful_value` hard block 旧 schema 快照；回测模式 L4 Wind 函数跳过导致跌破单层及格线）记入 WORK_ORDERS #11/#4。
- yfinance 属 third_party_unofficial：AAPL `60daysAgo=0.0` 一类字段漂移需保持怀疑；升级为正式数据源前仅作隔离观察。

---

## 2026-07-10

### 完整 Markdown 体检、薄而硬元信息、L3 稀疏日与 History of Market 分位修复

完成内容：

- 交付根目录 `NDX_L1-L5_数据与推理链完整体检_20260710.md`，按采集、算法语义、来源权威、point-in-time、发布治理、prompt/报告和运维文档分类列出 77 项问题；旧 HTML 不再作为完整问题台账。
- DataIntegrity 元信息改成“薄而硬”：不可用项只保留真实原因；coverage 只对成分聚合和一致预期等需要覆盖率的指标强制；vintage 只对历史回测中的可修订宏观/盈利预期强制；URL/license 移到来源注册语义；代理公式、未来数据、latest-only 回测混入、代理冒充官方、核心 fallback 无解释和重大估值冲突等硬闸门继续保留。同一 7 月 10 日快照重算从 `110 degraded + 36 audit_warn` 降为 `0 + 0`，完整度仍为 90.0%，没有靠放松发布阈值抬分。
- L3 共享价格面板新增目标日/窗口/逐股票缺口诊断与定向补抓；每次 `DataCollector.run()` 清空本轮缓存；% Above MA、新高新低和 McClellan 不再因一个稀疏日用 `dropna(any)` 删除整只股票，而是按实际观察数和每日覆盖率选择最近合格日。
- History of Market 历史分位增加样本数与跨度双门槛：trailing 至少 200 点且跨度 270 天，forward 至少 60 点且跨度 1642 天；不足时输出 `percentile=null`、`status=insufficient_history`，同时保留原始序列和相对位置上下文。Trailing/Forward 观察日、API 更新时间和 freshness 继续独立。
- L3 主 prompt 只讨论广度、集中度、Top10/M7 权重；M7 盈利质量归 L4。仓库内旧 nested prompt 文件仍在磁盘上，供历史/归档识别，但 `_load_prompt` 已移除二级 fallback，运行时不可达，不能据此声称旧规则仍会进入当前 prompt。

验证结果：

- L3 稀疏日、补洞、缓存与相邻回归：57 项通过；仍待真实网络 fresh collect。
- History of Market 外部估值源测试文件：31 项通过；2026-07-10 实时抽查 trailing 为 43 点/60 天，正确撤回分位，forward 为 298 点/9149 天并保留独立观察日。
- 元信息聚焦回归：96 项通过；同一快照重算 `hard_block=0, degraded=0, audit_warn=0`。
- 本轮多组测试存在重叠，不能把 57、31、96 简单相加成独立测试总数；最新代码尚未完成 fresh 全链 vNext，发布质量仍待最终验收。

剩余边界：

- 历史 current-universe fallback、字段级 `MetricAuthority` 下传、证据家族计权和 fresh E2E 尚未关闭；详见 `NEXT_STEPS.md`。
- History of Market 与 L3 修复均已通过模拟/聚焦测试，但仍需在 fresh 完整报告中核对数据与展示。

---

### VPN 修复后 FRED 真实恢复、Wind PIT 盈利预期通道布线与本地体检报告交付

完成内容：

- FRED 单序列实测确认 `DFII10`、`DGS10`、`T10YIE` 走官方 API，`source_tier=official_api`，不是旧缓存假恢复；另外实测 Fed Funds 与 M2 成功。
- 重跑真实 `--collect-only`：40 项旧口径指标约 118 秒完成，FRED/L1 从 7/9 run 的 3/8 恢复到 8/8；DataIntegrity 复算 90.0%、`publish_status=publishable`、无阻断原因。
- 真实 Wind CLI 对 NDX.GI point-in-time NTM/FY1 一致预期请求返回“没找到数据”；按 Wind skill 的 UNKNOWN 错误指令没有改写问句或切换接口强行重试。
- 新增 `get_ndx_wind_point_in_time_earnings_expectations`：只接受明确历史观察日、相同 NTM/FY1 口径、相同 fiscal period end 的指数一致预期 EPS；自动计算 30/90 日修正幅度、日历归一的修正斜率和上调/下调广度；历史 vintage 不足、口径混用、财年滚动、当前观察过期或越过 effective date 均明确 unavailable，不用当前值冒充历史。
- 新指标已进入 L4 collector、tool registry、data evidence、packet builder、canon 与 L4 prompt；Wind Forward PE 在自然语言返回不保留字段代码时仍为 supporting-only，修正斜率只在 PIT 验证通过后才允许作盈利预期主证据。
- 生成真正可点击的本地报告 `output/reports/NDX_L1-L5_数据与推理链体检_20260710.html`，包含两次运行的分层可用率对比、L4 来源分工、P0/P1 问题表、Wind 盈利预期契约和下一步顺序。

验证结果：

- Wind PIT 盈利预期针对性与 L4/packet/canon 回归：77 passed、6 warnings。
- 全量回归：493 passed、58 warnings。
- 报告渲染 QA：浅色/深色/手机宽度均有 1 个 Recharts SVG 挂载，无控制台错误和页面级水平溢出；禁用 JavaScript 时同数据静态 SVG 仍显示。

剩余边界：

- Wind PIT 通道的工程契约已完成，但真实数据仍未取得，尚不能声称生产可用。
- 当前快照 L3 仅 3/6；DataIntegrity 仍有 110 条 degraded 元信息问题，主要是 source URL、coverage 和 vintage date 未在上游填实。

### L1-L5 数据、指标语义、prompt 与发布链第一性原理审计及第一批硬修复

审计对象：冻结 run `20260709_233816`、当前 `discuss-l4-redesign` 工作区、L1-L5 采集/处理、canon、层 prompt、Claim Ledger、DataIntegrity 与报告渲染。结论：7/9 run 的“NDX 估值偏高”方向仍有 Wind 主锚支持，但该 run 不应按可发布结论使用；L1 仅 3/8，L3 腾落线被稀疏末行污染，L4 的 18.29% 盈利代理仅来自 10/103 只且不是增长率，Trendonify 旧 sidecar 越权进入 L4 prompt，Claim Ledger 的公共 refs 会让无关强证据洗白具体 claim。

完成修复：

- L4 来源治理：正式第三方检查不再读取/提升浏览器 sidecar；Trendonify stale/audit-only 不进入 prompt、分位选择和报告主尺；History of Market 分离 API 更新时间与 trailing/forward 实际观察日，历史覆盖不再复制当前覆盖，无 vintage 的历史值不具决策资格；Alpha Vantage latest-only fallback 禁止伪装成回测日。
- L4 权限与语义：Wind PE/PB/PS 保持主锚；Wind RiskPremium 在字段代码、公式、单位未核清前降为 supporting-only；10 年 Wind 分位最低样本从 1900 提高到 2300；Forward/trailing proxy 改名为 earnings gap，旧 growth 字段置空；成分覆盖少于 50 只不输出 NDX 聚合，M7 少于 5/7 不输出整体修正方向；成分模型默认关闭、仅显式开启用于审计。
- 层边界：`get_m7_fundamentals` 退出 L3 主运行时，L3 prompt 同步删除；History of Market 不再作为独立 L4 函数重复计票。
- L1/L2/L3 数据正确性：M2 level/date 为空时显式 unavailable；HYG 使用 dividend-adjusted price 且明确仍是 OAS 的代理；A/D Line 只在连续两日均有价格的有效对上计算，单日覆盖低于 80% 时排除该日，不再把 NaN 当作不涨不跌。
- 发布治理：任一 L1-L5 正式层可用率低于 50% 即阻断发布；Final 附加 Claim Ledger 后重新落盘并更新 stage manifest；估值、时点、价格反映和风险 claim 按相关层筛选 refs，不能再由公共证据池洗白；claim gate blocked 时不生成普通报告，downgraded 时标记 review_required。
- 报告与证据：Wind PE 分位不再被第三方循环覆盖；数据证据日期可从嵌套 `value.date/observation_date` 正确提取；实时网站测试改为固定 fixture，代码正确性不再依赖网站当天连通性。

验证结果：

- `python3 -m compileall -q src`：通过。
- `.venv/bin/python -m pytest -q`：490 passed，58 warnings；warnings 为 OpenBB/Pydantic、pandas_datareader 与 `datetime.utcnow` 等既有弃用提示及一条常量序列精度提示，无测试失败。
- 真实 `--collect-only` 验收生成 `output/data/data_collected_v9_live.json`（40 项，约 476 秒）：FRED API / pandas-datareader / fredgraph CSV 三路仍因 SSL connection_error 失败；新 DataIntegrity 复算 65.1%，L1 仅 2/8，按新分层闸门正确 `blocked`。M2 明确 unavailable；A/D Line 自动排除 2026-07-09 稀疏末行，回退到 2026-07-07 的 103/103 有效价格对；Wind PE 35.88、10 年分位 81.42% 可用，RiskPremium 10 年窗口因仅 1925 个样本被拒绝，字段权限为 supporting-only；History of Market forward 观察过期后不再进入当前值；成分盈利模型默认关闭并明确 unavailable；简式收益差因 10Y 缺失而不计算。
- 已生成 Codex 内报告《NDX L1–L5 数据与推理链体检》，含 7/9 run 分层可用率图、L4 来源角色表、问题/修复优先级和下一步验收标准；7/10 已补成可点击的本地 HTML 文件。

剩余：按 `NEXT_STEPS.md` 先做 fresh collect-only 验收；随后接入 Wind point-in-time 指数级 NTM/FY1 一致预期与修正序列，并把 DataIntegrity 从函数计数升级为证据家族计数。

## 2026-07-08

### codex 双路施工验收通过：FRED 错误穿透与 keyless 兜底、金额单位标注、层 prompt 减肥

完成内容（codex 施工，Fable 独立验收；未 commit，工作区待用户确认）：

- FRED 修复（src/tools_common.py +317 行、src/tools_L1.py +169 行）：`safe_request` 增加结构化失败原因（dns_error/connection_error/timeout/http_<status>/invalid_json，向后兼容旧调用）；新增 `fredgraph.csv` keyless CSV 兜底通道（处理 '.' 缺失值与日期过滤）；`_fetch_fred_series_pdr` 在 pandas_datareader 缺失/空结果时显式记录，不再静默空表；fallback_chain（API→pdr→CSV）与失败原因穿透到 data_quality/DataIntegrity；`get_fed_funds_rate` 空值防护，不再把断网伪装成 empty_observation_payload。
- 金额单位标注：净流动性 payload 新增 `level_unit / momentum_4w_unit / components_unit / component_units = billion_usd`（数值不变，WALCL 百万→十亿缩放逻辑已核对）。
- 层 prompt 减肥（src/agent_analysis/orchestrator.py +57 行）：`_layer_indicator_manifest` 不再复制完整 value（只留路由字段，data_quality 大结构摘要化）；`_filter_layer_raw_data_for_prompt` 对 prompt 副本递归剥离 `source_switches` 簿记（副本式重建，artifacts 落盘不变——已人工核查非原地修改）；L4 长序列（如 Damodaran monthly）prompt 内摘要化；层合约新增"引用金额数值必须带 payload unit，无标注不得猜测"纪律。
- 量化效果（用 20260707_163359 真实 packet 离线重组）：L4 prompt 380,172 → 144,002 字符（-62%）；L5 71,216 → 62,669；L1 50,876 → 49,541。未达 60K 目标的原因经核实成立：剩余主体是估值数值本体、第三方校验、Damodaran 摘要等有效分析数据，不为凑指标删有效信息。

验收过程：文件边界核查（两路各自只动许可文件集，互不相交）；全量测试独立复跑 `pytest tests/ -q` 473 通过（新增 7 个测试全部 monkeypatch 离线，无联网依赖）；剥离函数副本安全性人工审读；单位字段与 CSV 兜底代码抽查。

剩余（见 NEXT_STEPS P0）：FRED 网络恢复后跑一次 fresh run 做端到端综合验收（L1 覆盖回升、报告图组回归、L1 叙事单位正确、prompt_audit 确认输出质量不降）。

### NEXT_STEPS.md 排查确认失去维护，作废重写

- 排查结论：旧版与 2026-07-07 独立审核宣布的"施工收尾、架构冻结一个季度、进入使用期"直接矛盾——仍挂着 P0"Mao/Decision 主链验收"（已被审核收口取代）和 P1"三层研报架构接入攻坚"（6/30-7/1 已落地：三份产物独立落盘、控制台与 brief 入口链接齐全，见当日 WORK_LOG 与 7/7 run 产物）。
- 重写内容：新增"当前状态锚点"段落固化冻结期规则（允许 bug 修复/数据维修/prompt 卫生/呈现打磨，不允许新增阶段/artifact/改合约）；把审核遗留的三项使用期事项（回测验收打分器、确认决策档案阈值、攒台账 ≥5 条）显式入表；保留仍有效条目（L3 补源、控制台简化、快照审计痕迹、文档归档）并按 7/7 run 实况更新证据；并入 7/8 排查新增的 P0 FRED 修复、P1 prompt 减肥、P1 单位标注、P2 术语弹层、P2 上游产物粒度；方向思考区去掉已完成项，加入用户阅读画像锚点和"与 WORK_LOG 矛盾时以完成事实为准"的自愈规则。

### 第一性原理排查：报告不需要推倒重来，真正的病灶在数据管道与 prompt 工程

排查结论（详细待办已录入 `NEXT_STEPS.md` 新增 P0/P1 行）：

- 形式载体判定：自包含 HTML 保留（用户确认桌面大屏通读完整判断书、常看 L1-L5 底稿、几乎不看审计区、术语要悬浮解释——阅读画像已存入 agent 记忆）；排版经 7/8 改造后为倒金字塔+渐进披露，不需要大刀阔斧重来。
- 报告以外问题三项实锤：① FRED 采集集体失败（7/7 网络/DNS 故障 + safe_request 吞错误 + pandas_datareader fallback 静默失效 + fed_funds 无空值防护；codex 只读根因排查，6/27、7/1 run 均正常）；② 层 prompt 双重注入 + L4 被 370 条 per-ticker 来源审计记录污染到 38 万字符；③ 金额类 payload 无单位标注，净流动性被 L1 agent 写错 10 倍（"5815.95 亿"实为 5815.95 十亿）。
- 本次已修（报告渲染层）：`_score_bar` 增加 display 参数，Volume ratio 显示真值（0.55x 而非条位置 27.5）、CMF 显示原始值（-0.14 而非归一化 27.4），删除冗余 "CMF raw" meta；重新生成 brief 验证，`pytest tests/test_vnext_reporter.py` 26 通过。

### brief 报告形式与内容全面进化：清除死叙事、去重、补上被埋没的高价值产物

完成内容（`src/agent_analysis/vnext_reporter.py` + `report_styles/slate_v2.css` + `tests/test_vnext_reporter.py`）：

- 内容诚实性修复：删除 5 分钟图册里写死的三段旧叙事（"高实际利率与价格趋势并存""总量信用利差极低""等权补涨是好消息"——本轮 run 实际利率 N/A、信用数据缺失，正文在与自己的数据打架）。图组改为数据驱动：约束组文案取 `principal_contradiction`，信用/宽度组文案取 L2/L3 层结论；没有图表数据的图组整组不渲染，缺口在"数据缺口"读出格里明示。同步删掉 stat chips 里写死的"信用总量 极宽 / 内部分化 极高"。
- 去重：① Bridge V2 与第一轮内容逐字段指纹比对，完全一致时折叠为跟进卡（注明"调查未建立新证据，原有张力全部保留"），冲突区体量减半；② 旧口径 conflicts 与 typed_conflicts 同 id 时不再第三次渲染；③ 读者出口纪律条件卡的整包 refs/反证（上游按批次写入每条）改为共用块只展示一次，条目变成紧凑清单；④ hero 与读者出口对 state_diagnosis 的四次重复降为一次；⑤ 层底稿展开后 summary 文本不再与正文重复（CSS）。
- 补上被埋没的产物：① `hypothesis_competition.json` + `counter_thesis.json` 首次进正文——冲突区新增"谁在竞争解释权"（主线/挑战假说、各自解释不了什么、裁决理由、反方最强论证、还没吵完的争议）；② Final 的 `time_horizon_views`（未来几天/1-3月/6-12月）和 `price_reflection_map`（五类价格反映+状态胶囊）进读者出口；③ `confirmation_cost` + `payoff_assessment` 合为"赔率与等待的代价"；④ hero 副卡首格改为主要矛盾（含 dominant_side）；⑤ 新闻区读出格新增"第三层综合裁决"一行（`integrated_synthesis_report` 的 claim + 待确认比例，其余仍留审计区）。
- 人话化与排版：个人决策翻译从机器串（`small_position_dca_waiting_for_golden_pit。；`）改为结构化条目并翻译枚举；新闻卡片压缩为紧凑行（AI 分析折叠），每卡重复的"媒体解释不能当官方事实"上收到区块说明；watchlist 去重限 6 条；同层冲突不再显示"L5—L5"轴；章节编号修正为 01-07（原先出现三个 04）。
- 结果：桌面页高 21050→16248px（-23%），移动 37008→28261px（-24%）；证据 ref chips 31/31 无损，三条 typed 冲突、共振链、传导路径、审计区全部保留。

验证结果：

- `python -m pytest tests/test_vnext_reporter.py -q`：26 通过（含 5 个新契约测试：checklist 共用块去重、空清单兜底、无数据图组省略+缺口披露、主要矛盾驱动约束文案、bridge 指纹去重、假说竞争渲染）。
- 用 run `20260707_163359` 重新生成 native brief 并覆盖 `output/reports/vnext_brief_20260707_1633.html`；Playwright 1440px/390px 分段截图人工+子代理巡检。

剩余风险 / 上游发现（未在本次修，见 NEXT_STEPS）：

- 上游 `golden_pit_checklist.json` 生成阶段把全量 refs（10 个）和反证（19 条）整包写进每个条目，未按条目区分；报告层已做共用块呈现，但根治要在生成阶段。
- 上游 `event_mechanism_report.json` 的新闻正文片段在小数点处截断（"利率在3。"），且部分新闻主线归类机械（SpaceX 入指被归为"折现率"线）；属于事件层 prompt/截断逻辑问题。

### 独立审核确认：4b2163e 批次验收通过，施工阶段收尾，进入冻结使用期

- 复核 `4b2163e`（claim 级结果记分 + 谓词求值 + 阶段模型路由 + Final/Reviser 证据源头校验）：实现与指引文档规格一致；谓词缺变量保守判 insufficient_evidence 且判定轨迹全程落在 `status_evidence`；模型路由只在 available_models 内生效并写入阶段诊断；`_validate_stage_evidence_refs` 在生成时打回越界引用，与 claim 台账的事后比例降级形成两层防线。
- 独立验证：`python -m pytest -q` 461 通过；用 `fable_counter_thesis_fix_validation_2` 的真实 claim 台账离线烟测打分器——6 条 claim 因未来窗口不存在全部如实 `not_scorable` 并写明 `future_price_windows_missing_or_incomplete`，方向识别与 source_tier 提取正常。
- 已知 v1 简化（打分器自身已如实标注）：verdict 基于价格后续走势代理 + 文本方向启发式（`direction_method=claim_text_fallback`），不是逐条失效条件的字面求值；state_ledger 已在 payload 中预留为后续升级路径。
- 状态判定：路线图阶段 0-5、修正一/二、治理后续项全部落地并合入 main。按停机准则，架构冻结一个季度；剩余为使用期事项：① 一次历史回测 fresh run 验收打分器真实判定；② 用户确认决策档案阈值；③ 日常 `--official` run 攒台账 ≥5 条解锁展示层。

### P0/P1/P2 收口：claim 级结果记分、谓词化条件状态、阶段模型路由与证据源头校验

完成内容：

- P0 claim 级结果记分：`outcome_review.py` 现在读取 `final_claim_ledger.json` 与 `evidence_registry.json`，对每条 final claim 生成 T+20 / T+60 / T+120 窗口复盘，输出 `verdict = consistent | falsifier_triggered | not_scorable`、`scoring_evidence`、`claim_type` 和 `source_tiers`；`outcome_review_report.json` 内嵌摘要，独立 `claim_outcome_scores.json` 可落盘。
- 新增 `scripts/aggregate_claim_outcome_scores.py`：跨 run 扫描 `claim_outcome_scores.json`，按 `claim_type` 和 `source_tier` 汇总一致、触发反证和不可评分数量；该产物明确只属于 post-Final 学习材料，不得回流 L1-L5。
- P1 谓词求值器：`GoldenPitChecklist` 的 profile 条件优先读取 `config/user_decision_profile.json` 中的 `metric_predicates`，用 `state_ledger.extract_state_variables` 同一套稳定状态变量判定 `met / not_met / insufficient_evidence`；旧 `_claim_text_supports_buy/sell` 仅在没有谓词时作为 fallback，并写入 `status_method=claim_text_fallback`。
- P2 per-stage 模型路由：新增 `config/stage_model_routing.json`，`counter_thesis / thesis / reviser / final` 默认优先 `deepseek-v4-pro`，失败后降级到用户传入的剩余模型链；`llm_stage_diagnostics.json` 记录每阶段 `preferred_models` 与 fallback chain。
- P2 Final/Reviser evidence_refs 源头校验：`reviser` 和 `final` 生成时递归检查 `evidence_refs / counterevidence_refs / counter_evidence_refs`，引用不在 `synthesis_packet.evidence_index` 内会触发 `_run_stage` 重试，并在 stage diagnostics 留下 `contract_validation_error`。

对抗式审查结论：

- 后验隔离：`claim_outcome_scores.json` 只由 Outcome Review / 聚合脚本生成，发生在 Final 与 Claim Ledger 之后；产物带 no-backflow 声明，未进入 L1-L5、Bridge、Thesis、Risk、Reviser、Final prompt。
- 条件判定边界：有 `metric_predicates` 时不再让 claim 文本替状态变量发言；变量缺失时记 `insufficient_evidence`，不会用其它指标冒充 Wind 估值分位或缺失变量。
- 模型路由边界：阶段偏好只改变调用顺序，不改变 prompt 内容和 L1-L5 上下文隔离；没有可用 pro 模型时自动回到用户提供的模型链。
- 证据引用边界：Final/Reviser 的越界引用在生成阶段打回，不再只靠后续 claim 台账降级；但 checkpoint 恢复旧 artifact 时仍按现有 stage manifest 逻辑加载，后续如需可加恢复时复验。

验证结果：

- 聚焦测试：`python3 -m pytest tests/test_outcome_review.py tests/test_vnext_orchestrator.py::test_stage5_golden_pit_checklist_defers_cross_run_diff_even_if_previous_exists tests/test_vnext_orchestrator.py::test_stage5_profile_conditions_use_metric_predicates_before_claim_text_fallback tests/test_vnext_orchestrator.py::test_run_stage_uses_stage_model_routing_for_cognitive_stages tests/test_vnext_orchestrator.py::test_reviser_final_evidence_refs_outside_index_trigger_retry -q`：8 通过。
- 全量测试：`python3 -m pytest -q`：461 通过，4 个环境/依赖 warning。

剩余风险：

- claim outcome 的方向识别仍是透明的文本 fallback，适合先建立学习闭环，但不能解释复杂非方向性 claim；此类 claim 会输出 `not_scorable` 和原因，不编造胜率。
- 当前 claim 评分主要用 QQQ 后验价格路径；未来若积累足够 official state ledger，可把估值/广度/信用类 claim 的状态变量失效条件纳入更细评分。
- 用户决策档案里的阈值仍是草案，正式启用前仍需用户确认。

### 跨 run 对比定案 + 状态台账记录层上线 + 个人决策档案草案

完成内容：

- 跨 run 对比设计定案并写入 `docs/2026-07-06_STAGE0-4_REVIEW_AND_DIRECTION.md` 修正一：对比轴从"上一份报告"改为"上一个市场状态"；只比确定性状态变量和稳定条件 ID，`claim:<hash>` 回声条目与 LLM 派生项永不参与报警；`git_sha` 不同带系统版本横幅；报警白名单只含条件翻转/失效条件触发/闸门变化；展示层等三闸门（谓词化、≥5 条 official 记录、代码稳定），记录层先行。
- 新增 `src/state_ledger.py`：从 run 目录提取约 20 个确定性状态变量（估值 PE、净流动性、VIX/HYG 分位、广度、NDX/NDXE 分位、趋势与唐奇安回撤等）+ profile 条件状态 + 发布闸门，附 `git_sha` 与 schema 版本，append-only 写入 `output/state_ledger/state_ledger.jsonl`，同 run_id 去重；缺失变量如实记入 `missing_variables`（Wind 离线时不冒充）。
- `src/main.py` 接入：新增 `--official` 参数标记正式日度 run；run_pipeline 结束时自动追加台账（失败不阻断 run），结果写入 `run_summary.state_ledger`。
- 新增 `config/user_decision_profile.json` 草案：价值买入-趋势卖出纪律写成 metric 谓词（估值买入区、黄金坑回撤+恐慌确认、趋势破坏、信用恶化），全部阈值标注 `draft_needs_user_confirmation`；该文件会被编排器自动加载替换内置占位档案。
- 修复 codex 第 4 步测试的隔离缺陷：`test_stage5_golden_pit_checklist_defers_cross_run_diff_even_if_previous_exists` 原本调用 `_load_user_decision_profile()` 隐式依赖仓库 config 全局状态，改为显式构造档案。
- `NEXT_STEPS.md` 新增 P1（状态台账展示层三闸门）与 P2（认知阶段模型路由 + Final 引用源头校验）。

验证结果：

- `python -m pytest -q`：456 通过（含新增 `tests/test_state_ledger.py` 3 条）。
- 用真实 run `fable_counter_thesis_fix_validation_2` 干跑台账：19 个非空确定性变量、Wind 两项如实记缺、闸门状态正确、重复追加被拒。
- `config/user_decision_profile.json` 通过 `UserDecisionProfile.model_validate` 加载校验。

剩余风险：

- 决策档案阈值全部是草案（Forward PE ≤ 20、回撤 ≥ 15% + VIX 分位 ≥ 70% 等），需用户逐条确认；Wind 估值分位谓词在 Wind 源接通前记 insufficient_evidence。
- 台账的唐奇安回撤是"距通道上轨"口径，不等于距 52 周高点的标准回撤；启用展示层前应确认口径或补 52 周高点变量。
- 谓词化状态判定（展示层闸门 ①）尚未实现，黄金坑清单当前仍是关键词启发式判定。

### 完成第 4 步：阶段 5 读者出口（决策稀疏版）+ 对抗式审查

完成内容：

- 新增阶段 5 合同：`UserDecisionProfile` / `UserDecisionCondition` 与 `GoldenPitChecklist` / `GoldenPitChecklistItem`。个人决策档案只描述持仓状态、目标、风险承受、买入纪律和卖出纪律；黄金坑清单只在 Final / Claim Ledger 之后生成。
- 编排器在 `final_claim_ledger.json` 之后落盘 `user_decision_profile.json` 与 `golden_pit_checklist.json`。清单来源限定为 `final_claim_ledger` 中 `valuation` / `timing` / `risk_boundary` claim + 个人买卖纪律；`changed_since_last_run` 当前只保留预留字段并标记 `deferred_until_run_quality_stable`，暂不读取上一 run 做 diff。
- Claim 台账补出 `valuation` 与 `timing` 类型条目，供黄金坑清单读取；个人纪律聚合采用保守语义，不能把“估值 claim 证据完整”误判成“买入条件满足”。例如“估值安全垫仍不足”即使 verified，也只会让买入纪律显示 `not_met`。
- Runtime Boundary Manifest 增加 reader-exit 边界；Prompt Inspector 增加硬检查：`user_decision_profile` / `golden_pit_checklist` / 个人决策档案 / 黄金坑清单 一旦进入任意分析 prompt，标记违规。
- Native brief 首屏改为阶段 5A 定调：30 秒版回答“当前状态、距离买入/卖出纪律还差哪些证据”；“上次 run 以来变化”暂缓前置，报告内明确四层阅读入口：30 秒裁决、5 分钟简报、深度研究、审计重放。
- Run Review 增加阶段 5 读者出口检查：缺 `golden_pit_checklist` 记 observe；字段不完整记 fail；完整且声明 no-backflow 记 pass。

对抗式审查结论：

- 上游污染检查：个人档案和黄金坑清单只在 Final / Claim Ledger 之后生成；Prompt Inspector 对所有 LLM 分析阶段加拦截，未发现现有 prompt 注入路径。
- 伪确定性检查：黄金坑清单不输出交易指令，只输出 `met / not_met / insufficient_evidence` 和失效条件；买入纪律聚合对负面估值文本保守判 `not_met`。
- 跨 run 边界检查：真实上一 run diff 已退回，`changed_since_last_run` 只写暂缓状态；未来启用时仍不得进入 L1-L5、Bridge、Thesis、Critic、Risk、Reviser、Final 或竞争裁决。

验证结果：

- 聚焦测试：`python3 -m pytest tests/test_contracts.py tests/test_vnext_orchestrator.py::test_stage4_evidence_registry_and_final_claim_ledger_are_auditable tests/test_vnext_orchestrator.py::test_stage5_golden_pit_checklist_defers_cross_run_diff_even_if_previous_exists tests/test_vnext_reporter.py::test_vnext_reporter_generates_native_ui tests/test_vnext_reporter.py::test_prompt_inspector_flags_user_decision_profile_in_analysis_prompt tests/test_run_review.py::test_run_review_passes_stage5_golden_pit_checklist_when_complete -q`：27 通过。
- 全量测试：`python3 -m pytest -q`：453 通过，4 个环境/依赖 warning。

剩余风险：

- 默认 `UserDecisionProfile` 是保守占位；正式使用前应在 `config/user_decision_profile.json` 写入真实持仓状态、风险承受和纪律参数。
- 黄金坑清单的条件满足判断仍依赖 claim 文本语义和保守关键词；后续如果 Final claim 语言风格变化，需要继续补测试，避免把“证据完整”当成“条件满足”。
- 跨 run 变化对比已主动暂缓；等 claim schema、数据源覆盖、Run Review 通过历史和多轮 run 行为稳定后再启用。
- 第 5 步 claim 级结果记分尚未开始；阶段 5 读者出口已可用，但学习闭环仍需后续 `claim_outcome_scores.json`。

### 第 0-3 步验收审核 + Counter-Thesis schema 摩擦与 claim 闸门误伤修复

完成内容：

- 审核 codex 第 0-3 步全部提交（`fe2f154`..`a46b5a0`）与计划外 L4 超时提交 `4e14316`：验收合格，L4 改动未弱化数据闸门（跳过项记入 `skipped`/`degraded`，SEC 角色诚实降级为 cross-check）。
- 用 fresh run `codex_external_timeout_validation` 做行为验证：stub 不再触发降级、竞争裁决出现主导假说、principal/price reflection 均 native、claim 反证已按类型区分、Run Review 零 fail。
- 修复该 run 暴露的两个新问题：
  1. Counter-Thesis LLM 两次尝试均死于 schema 摩擦（漏 `hypothesis_id`；`cannot_establish` 写成字符串；`what_it_cannot_explain`/`failure_conditions` 字段变体），高质量反方内容被整体丢弃。`contracts.py` 为 `CompetingHypothesis.hypothesis_id` 加默认工厂，加字符串→列表 coercion 与已观测字段别名吸收；`orchestrator.py` 保留 `fallback_reason` 不被审计覆写。
  2. Final 支撑链混入说明性 token `known_data_gaps`，导致全部 claim 被 `evidence_refs_not_in_registry` 误标 blocked。台账构建改为只保留 `L#.func` 形式或注册表内的真实引用，剔除项记入 `dropped_non_evidence_tokens`；真实引用缺失仍照常阻断。
- `docs/2026-07-06_STAGE0-4_REVIEW_AND_DIRECTION.md` 写入修正一（黄金坑清单 + 决策稀疏定调）、修正二（claim 级结果记分）、停机准则和 2026-07-07 审核记录。

验证结果：

- `python -m pytest -q`：449 通过。
- 用 `codex_external_timeout_validation` run 中两份被拒绝的原始 LLM 返回回放合约：修复后均通过校验（意味着当时两次尝试本可成功）。
- 启动 `fable_counter_thesis_fix_validation` 验证 run（复用 2026-07-07 数据快照），验证 LLM 反方端到端落地。

第二轮（同日）：验证 run `fable_counter_thesis_fix_validation` 复盘与追加修复：

- 该 run 确认竞争裁决行为正常（主导假说成立、stub 豁免生效、Run Review 零 fail），但 Counter-Thesis 再次以两个**新的**形状变体失败退回 fallback：attempt 1 用 `falsifiers`（正是本库 TypedConflict 等合同的正式字段名，模型从 payload 学来，必然复发）和 `explains_poorly`；attempt 2 把 `principal_counterargument` 写成 `{"summary": ...}` dict。两次的内容质量都很高（失效条件具体到"净流动性 4 周动量 < -50B""铜金比跌破 MA50"级别的可观察阈值）。
- Final 阶段幻觉出 `L5.get_ta_indicators`（真名 `get_qqq_technical_indicators`），经共享 refs 池把全部 6 条 claim 拉黑为 blocked——闸门第二次喊狼来了。
- 追加修复：合约层吸收 `falsifiers`/`explains_poorly` 别名与 dict 反方论点；`_verify_claim_entry` 改为比例原则——无法核验的引用点名降级（`unverifiable_evidence_refs:`），仅当没有任何可核验引用时才阻断。
- 回放验证：两份新失败返回经修复后合约 + 编排器验证器均通过；至此两次真实 run 的全部 4 次 LLM 尝试在修复后都会成功。
- `python -m pytest -q`：449 通过。启动第三次验证 run `fable_counter_thesis_fix_validation_2` 做最终收口。

第三轮（同日）：验证 run `fable_counter_thesis_fix_validation_2` 最终验收通过：

- counter_thesis LLM 阶段 1 次尝试即成功（仍是 flash 模型，证明别名吸收是关键瓶颈）。产出两个真反方假说：其一挑战估值压力（Trailing PE 高分位是低基数效应，Forward PE 分位 58.3% 说明压力已部分吸收），其二挑战趋势弱化判断（头部向等权的健康轮动 vs 趋势反转）；支持/反证 refs 不重叠且语义合理，失效条件具体到"HY OAS 扩大至 500bp 以上""NDX/NDXE 跌破 2.85"级别的可观察阈值。
- 竞争裁决：主线 leading、两个反方 candidate、9 条保留争议、无虚假降级——输出不再是常量。
- claim 台账：publish gate `pass`，6/6 verified，无幻觉引用误伤。
- Run Review 零 fail；`prompt_input_audit.thesis_read=false` 实测成立。
- 阶段 3（Counter-Thesis 真 LLM 化）的行为验收在本 run 内达成；跨市场状态方差验收（历史回测日 run）仍留待后续。

剩余风险：

- 字段别名吸收只覆盖已观测变体；后续新变体应继续在合约层吸收并补测试，而不是放宽 validator 语义。更根治的方向是给 counter_thesis 等认知阶段做按阶段模型路由（当前引擎"上次成功者优先"，反方阶段常落在最弱的 flash 上），已列为 codex 后续项。
- Final/Reviser 阶段目前不校验 evidence_refs 是否在 evidence_index 内，幻觉引用在源头就该被打回（像 counter_thesis validator 那样），已列为 codex 后续项。
- 步骤 2 的"不同市场状态下反方假说有真实差异"验收仍需一个历史回测日 run 确认。

---

## 2026-07-06

### 阶段 0-4 审查后更正：合同关闭，行为未关闭

完成内容：

- 按 `docs/2026-07-06_STAGE0-4_REVIEW_AND_DIRECTION.md` 更正阶段 2/3/4 的完成语义：此前记录的“完成”只代表合同、artifact 管道和最小审计链完成，不代表调查、反方假说和 claim 台账已经具备充分行为质量。
- `InvestigationReport` 增加 `is_deterministic_stub`；当前确定性调查如实标注“未执行真实调查，仅登记缺口”，不得作为真实反证触发竞争裁决降级。
- Counter-Thesis 改为优先走独立 LLM 阶段；确定性构建器只作为失败兜底，并在假说来源中标记为 `deterministic_fallback`。
- Claim 台账改为按 claim 类型匹配反证和失效条件；无法逐条对应时写入降级原因，不再用全局反证池冒充逐条反证。
- Bridge V2 在 SynthesisPacket 中只贡献反馈摘要和未解决问题，不再把 Bridge V1 的冲突和主要矛盾重复计入 Thesis 输入。

状态更正：

- EPI-08 / EPI-10 / EPI-12 / EPI-13：合同与运行管道已关闭，真实行为质量未关闭。
- HAR-05 / HAR-06 / HAR-07 / HAR-08 / HAR-09 / HAR-13：合同、边界和最小 artifact 已关闭，真实调查质量、反方认知质量和跨 run 方差仍需后续 fresh run 验收。
- 阶段 4 的 Evidence Passport / Claim Ledger 合同已关闭；claim-specific 反证已开始落地，但仍需真实 run 检查每条 claim 的语义对应是否足够强。

验证结果：

- 聚焦测试：`python3 -m pytest tests/test_contracts.py tests/test_vnext_orchestrator.py tests/test_run_review.py -q`：64 通过，4 个环境/依赖 warning。
- 全量测试：`python3 -m pytest -q`：444 通过，4 个环境/依赖 warning。
- fresh run 尝试：`python3 src/main.py --models deepseek-v4-flash,deepseek-v4-pro --skip-report --disable-charts --run-id codex_stage1_3_validation` 在实时 L4 成分股 SEC CIK map HTTPS 握手处长时间无输出后中断；中断发生在 vNext artifacts 生成前，本轮不能作为真实产物验收。

剩余风险：

- Counter-Thesis 的真实质量取决于 LLM 输出和证据引用校验；本轮已接入阶段和 fallback，但尚未用两个不同真实市场状态 fresh run 验收方差。
- 动态调查仍不是真工具调查；stub 已诚实标注，后续应在真实反方假说暴露关键分歧后再接动态调查工具。
- 实时 fresh run 还需要处理 SEC CIK map / 外部 HTTPS 卡住时的超时或缓存兜底，否则 L4 多源成分股补全可能阻塞后续 LLM 验收。

---

### vNext 阶段 3：最小竞争裁决落地

完成内容：

- 新增竞争裁决合同：`CompetingHypothesis`、`CounterThesisDraft`、`HypothesisCompetition`、`AdjudicationChangeRecord` 和 `AdjudicationHistory`。
- 在 Bridge V2 之后、Thesis 之前生成 `counter_thesis.json`、`hypothesis_competition.json`、`adjudication_history.json` 和 `competition_adjudication_manifest.json`。
- Counter-Thesis 首次生成只读取 `synthesis_packet.json`、`bridge_memos/bridge_v2.json` 和 `investigation_reports/*.json`，并显式禁止读取 `thesis_draft.json`、`analysis_revised.json`、`final_adjudication.json`。
- `SynthesisPacket` 增加竞争假说摘要，让 Thesis 正式综合前能看到至少主线解释和反方解释；调查结果只能改变假说状态、保留争议或触发重判记录，不回写 L1-L5 layer card。
- 新增非单调重判记录：当 InvestigationReport 挑战强单一路径裁决，或主要矛盾/价格反映来自代码兜底时，保留旧假说、触发证据和降级/保留争议原因。
- Run Review 新增 `competition` 归因检查：缺竞争卷宗会 fail，Counter-Thesis 未禁读 Thesis 会 fail，兜底生成的 principal_contradiction / price_reflection 会 observe，降级/分叉/保留争议记录会被审计。

验证结果：

- 语法检查：`python3 -m py_compile src/agent_analysis/contracts.py src/agent_analysis/orchestrator.py src/agent_analysis/run_review.py` 通过。
- 聚焦测试：`python3 -m pytest tests/test_contracts.py tests/test_run_review.py tests/test_vnext_orchestrator.py -q`：58 通过，4 个环境/依赖 warning。

对抗式审查结论：

- 反方独立性：测试确认 `counter_thesis.json` 在 Thesis 生成前出现，`prompt_input_audit.thesis_read=false`，并把 `thesis_draft.json` 放入 forbidden context。
- 反证不被吞：受控调查的 `claims_challenged` / `cannot_establish` 会进入竞争假说的反证、不能解释项和 `downgrade_or_split_events`，不会直接强化主线。
- 改判可审计：`adjudication_history.json` 保留旧假说、新假说、触发证据、变化类型和原因。
- 兜底可见：Bridge 的 `normalization_notes` 中只要出现主要矛盾或价格反映兜底，竞争卷宗会记录 `fallback_warnings`，Run Review 标记为 observe。
- 隔离边界：新增竞争产物只被 Thesis / governance 读取；L1-L5 输入策略仍禁止 `investigation_reports`、Bridge、Thesis、Final 和事件侧链进入。

剩余风险：

- 2026-07-06 审查后更正：Counter-Thesis 已改为优先走独立 LLM 阶段，确定性构建器只作为失败兜底；解释质量仍需 fresh run 验收。
- 当前重判逻辑以调查报告挑战项和兜底痕迹为触发条件，尚未做更细的证据权重模型；阶段 4 的统一 Evidence Passport / claim 台账会继续增强证据级追踪。

---

## 2026-07-06

### 完成 vNext 实施路线图阶段 4：统一证据与最终 claim 台账

完成内容：

- 新增统一 `EvidencePassport` / `EvidenceRegistry` 合同，覆盖数据、事件、受控调查、竞争假说和最终 claim。
- 新增 `ClaimLedger` / `ClaimLedgerEntry`，为 Thesis / Final 的重要自然语言结论登记证据、反证、推理步骤、失效条件和验证状态。
- 编排器生成并落盘 `evidence_registry.json` 与 `final_claim_ledger.json`；Final 原始检查点保持不被 claim 台账回写污染，恢复运行可继续复用。
- 统一 source tier / authority / downgrade 规则：事件、标题新闻、代理指标、派生假说和最终 claim 不得越权充当强主证据。
- Run Review 新增证据与 claim 台账对抗式审查：缺证据、缺反证、缺失效条件、弱权限证据无降级规则都会被标记。
- Integrated Synthesis Report 读取证据注册表和 claim 台账摘要，但不允许其反向污染 L1-L5 或纯数据主链。

验证结果：

- `python3 -m py_compile src/agent_analysis/contracts.py src/agent_analysis/orchestrator.py src/agent_analysis/run_review.py src/integrated_synthesis_report.py src/data_evidence.py`
- `python3 -m pytest -q`
- 结果：`441 passed, 4 warnings`

剩余风险：

- 当前 claim ledger 为确定性生成，能保证可审计字段完整；后续阶段 5 仍需把读者出口和语义发布闸门做得更细。
- 事件材料进入统一注册表后仍默认弱权限，只能做解释线索；正式升级为主证据仍需要单独数据源升级流程。

---

## 2026-07-01

### 第二层新闻事件研报重构落地

完成内容：

- 将第二层正式从“事件账本 + 窗口观察”升级为“新闻事件研报 + 跨层问题交付”。
- 新增 `event_mechanism_report.json`、`cross_layer_questions.json`、`event_mechanism_cards.json` 和 `event_mechanism_report.html`。
- 新闻按主线组织，不再按标题列表堆叠；默认主线包括 AI/半导体盈利、宏观利率估值压力、指数结构/广度、信用/流动性，以及其他观察。
- 每条新闻卡生成读者可读字段：标题、来源、日期、摘要、AI 分析、能支持什么、不能支持什么、还要确认什么、缺失证据和置信度。
- 旧 `event_market_validation.json` 保留兼容，但窗口观察降级为 `background_market_observation`，不再写成市场确认新闻，也不在读者页作为验证结论展示。
- 新增第二层独立 HTML 报告，结构对齐样张：新闻事件初步判断、事件快照、主线新闻卡、点击弹窗、事件研究卡、新闻给数据层的问题、主张台账、给综合研报的一句话。
- 综合 vNext brief 优先读取 `event_mechanism_report.json`，事件区改为展示新闻解释、数据待确认问题、证据缺口和给综合研报的交付，不再只是旧 04 标题列表。
- 控制台 `/latest-product` 和 event-only 模式优先打开新版新闻事件 HTML。
- 纯数据 manifest 禁止输入新增 `event_mechanism_report` 和 `cross_layer_questions`，继续防止第二层污染 L1-L5。

验证结果：

- 已用新规则刷新 `output/analysis/vnext/20260701_131914` 的第二层产物、`integrated_synthesis_report.json`、`vnext_brief_20260701_1319.html` 和 `vnext_workbench_20260701_1319.html`。
- 独立新闻事件 HTML 静态验收通过：包含“新闻事件初步判断”“可以说”“不能说”“data-detail”“AI 分析”“给综合研报的一句话”“新闻事件给数据层出的题”；不包含 `earnings_path`、`discount_rate`、`risk_premium`、`Layer 2 Event Mechanism Report`、“第二层可以说”、“新闻导致价格变化”。
- 全量测试：`python3 -m pytest -q`：417 通过，4 个环境/依赖 warning。

剩余风险：

- 新闻分析仍主要基于现有标题、摘要和来源字段；缺 URL、未读全文的材料已降级，但还没有自动追原文、找反方全文或安装专项深度事件研究 workflow。
- 综合 brief 底部嵌入的完整 vNext 数据 JSON 仍包含部分内部 evidence/ref 字段，这是全站审计数据，不属于新版新闻事件区；若未来要彻底面向非技术读者，需要单独做“隐藏审计 JSON / 懒加载审计”的前端治理。

### 综合报告实跑审查与质量修复

完成内容：

- 对 `output/analysis/vnext/20260701_131914` 做三路审查：第一层数据质量、第二层事件研究、第三层综合报告/HTML 可读性。
- 结论：本次 run 没有被 DataIntegrity 闸门挡住，`publish_status=publishable`，最终判断“估值偏高、宏观约束偏紧、只支持战术试探”基本合理；事件材料没有进入 L1-L5 / Bridge / Thesis / Risk / Reviser / Final 的运行 prompt。
- 修复第二层措辞越权：媒体标题不再写成“官方事件”，标题-only claim 的 `fact_part/fact_summary` 只记录“某来源在某时发布某标题”，解释和叙事部分明确未读全文不能推出强解释。
- 修复市场验证措辞：`partly_confirmed` 改为 `temporal_association_observed`，保留“只代表时间关联，不构成因果证明”的边界。
- 修复事件摘要排序：标题-only 不能高置信，ETF NPORT/N-CSR 这类基金文件不会再挤占高重要性事件位。
- 修复 legacy 导出里的“数值冒充分位”：只有字段名明确是 percentile 的值才显示为“分位”，普通价格、ADL、RSI、ATR 不再被写成历史分位。
- Native brief 主文新增“事件与叙事层”小节，用户打开 HTML 就能看到第二层只做解释线索、不能做主证据；审计入口新增 `event_layer_summary.json`。
- 为控制台就绪检测补回兼容标记，避免新旧 launcher 文案造成测试误判。

验证结果：

- 已用新规则刷新本次 run 的派生产物：`event_narrative_ledger.json`、`event_claim_ledger.json`、`event_market_validation.json`、`event_layer_summary.json`、`integrated_synthesis_report.json`、`logic_vnext.json`、`vnext_brief_20260701_1319.html`、`vnext_workbench_20260701_1319.html`。
- 回查确认不再出现 `官方事件`、`partly_confirmed`、`736.4% 分位`、`439.0% 分位`、`106.0% 分位` 等旧问题。
- 全量测试：`python3 -m pytest -q`：415 通过，4 个环境/依赖 warning。

剩余风险：

- 第一层数据证据元信息仍有大量 `source_url`、`coverage`、`vintage_date` 缺口；本轮只修了最误导读者的表达层问题，没有全面补齐数据合约。
- 第二层仍是规则化事件研究，不是全文原文核验和反方材料检索；标题-only 材料现在会降级，但还没有自动深读全文。

### 第二层事件研究 Agent 五段式流水线落地

完成内容：

- 将第二层从旧的“新闻/事件标题侧栏”升级为五段式事件研究流水线：采集与时间闸门、事件聚类与 claim 拆解、事件研究包、市场验证、账本/报告/综合层交付。
- `NewsEventLedgerBuilder` 新增 `event_source_raw.jsonl`，每条材料记录来源、发布时间、信息可见时间、正文可用性、hash、采集状态和第二层边界；历史 run 中未来材料和无日期材料不会进入事件账本。
- `EventNarrativeLedgerBuilder` 现在除 `event_narrative_ledger.json` 外，还会写出 `event_clusters.json`、`event_claim_ledger.json`、`event_research_packets/*.json`、`event_market_validation.json`、`event_layer_summary.json`、`event_adversarial_review.json` 和 `event_narrative_report.md`。
- claim 枚举收敛为计划要求的 7 类：`official_fact`、`company_disclosure`、`data_release_claim`、`interpretation_claim`、`view_claim`、`narrative_claim`、`rumor_claim`；标题-only 材料自动低置信，社媒/未验证信号不能变成官方事实。
- 市场验证器只输出确认程度和时间邻近观察，固定声明不构成因果证明；缺少验证数据时降级为 `insufficient_data`。
- 第三层综合报告显式读取 `event_layer_summary.json`，同时保留 `event_narrative_ledger.json` 兼容旧入口；第二层仍禁止反向流入 L1-L5 / Bridge / Thesis / Risk / Reviser / Final data-only prompts。
- `run_summary.json` 增加完整第二层卷宗路径，方便控制台和后续审计入口读取。
- 顺手修复全量测试暴露的两个既有兼容缺口：恢复 `VNextReportGenerator._data_quality_box`，并为 L3 Top10 集中度补回 `_qqq_equal_weight_performance_spread` 兼容别名（内部仍使用 NDX/NDXE 底层口径）。

验证结果：

- 聚焦测试：`tests/test_news_event_ledger.py tests/test_news_event_data_linker.py tests/test_news_layer_analyzer.py tests/test_three_layer_artifacts.py`：15 通过。
- 主链相关测试：`tests/test_main_cli.py tests/test_main_collect_only.py tests/test_vnext_packet_builder.py tests/test_control_service.py tests/test_research_console.py tests/test_vnext_reporter.py tests/test_prompt_guardrails.py`：64 通过。
- 全量测试：`python3 -m pytest -q`：410 通过，4 个环境/依赖 warning。

对抗式审查结论：

- 未来函数：历史 `effective_date` 下未来材料和无日期材料被排除；实时模式保留但标注日期不确定。
- 标题党：`raw_text_available=false` 的 claim 只能低置信，研究包会记录降级原因。
- 情绪源越权：`unverified_signal` 固定降为 `rumor_claim`，不能生成 `official_fact`。
- 事后讲故事：市场验证只写 `temporal association only; no causal proof`，不允许把新闻写成价格原因。
- 第一层污染：新增产物只由第二层/第三层读取；纯数据 manifest 仍声明禁止 `event_refs`、news/event ledger 和 browser sidecar。

剩余风险：

- Wind financial docs、Yahoo/Alpha Vantage、社媒等 adapter 目前是结构预留，尚未完成真实自动接入；当前真实采集仍以官方 RSS 和 SEC EDGAR 为主。
- 事件研究包目前是规则化研究包，不是 LLM 深度调查；重大事件的原文追踪、全文公告/filing 阅读和反方材料检索仍属于后续深度模式。

