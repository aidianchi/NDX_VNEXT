# 全系统闸门普查（Q-E / Q7 取证）

> 研究员任务：枚举 `src/` 下全部校验类机制（函数名带 check/validate/verify/gate/audit 的、assert 拦截、schema 校验、提示词里要求 AI 自查/自证/复述的段落），按老板闸门六原则的两条标尺分类。
>
> **分类标尺**（老板原话的转述）：
> - **A = 身份或形状校验，代码该做。** 枚举值合法吗、字段在吗、编号对得上吗、数字在材料里逐字找得到吗之外——凡代码能确定性生成或回填的字段，不该让 AI 填。
> - **B = 意思判断，疑似设计错误。** 两段散文像不像、措辞够不够保守、这句话是不是在把缺失当理由——凡要比对模型散文才能判定的规则，都是设计错误。
> - **C = 拿不准，需总研究员研判。**
>
> **方法**：只读源码，每个论断给 `文件:行号`。全系统 `src/` 下没有 `assert` 拦截（全库搜索 `^\s*assert\s` 零命中），pydantic 是唯一的 schema 校验框架（`src/agent_analysis/contracts.py`）。`scripts/layer2_supplement_prototype/prototype_loop.py` 不在 `src/` 下，但 `src/event_research/card.py:23-26` 直接 import 它的校验器当二档材料卡的运行时校验用，所以它的三条词表子条按"生效机制"收录。
>
> **边界声明**：`orchestrator.py` 的"判决正文数字逐字比对"（`_validate_reasoned_verdict_refs` 内，7034-7046 行）由另一位研究员专项深挖，本表收录并分类，但不展开；在别处发现的同类机制（数字必须逐字/等值出现在材料里）全部收录：见 #18、#52。

## 汇总统计

- **普查机制总数：89 个**（75 个代码机制 + 14 个提示词机制；另有 6 组 20 个名字命中但实非闸门的簿记/渲染/装配函数，列在文末附录，不计入总数）。
- **A 类（身份/形状，代码该做）：59 个**（66%）。
- **B 类（意思判断，疑似设计错误）：20 个**（22%）。其中只有 2 个仍在"打回重试"的拦截位（#7、#18），1 个半拦截（#15 会把 schema_guard 报告压成未通过），其余 17 个已被项目自己降级为"留痕不拦/只标注"或无代码强制的提示词清单——多条降级注释里白纸黑字写着"闸门宪法 v2：形状代理语义一律出局"，说明项目方向已经对，但病灶还在原位运转。
- **C 类（拿不准）：10 个**（11%）。

**B 类最危险的 5 个**（按"拦截力 × 误伤面"排序，详细杀伤力评估见文末）：

1. `orchestrator._validate_investigation_limits_against_materials`（2864）——**仍在 raise 打回**，用正则判调查员散文"是不是夸大了材料缺席"，材料里出现任何一个数字就禁止调查员说"没有定量数据"，哪怕那个数字与问题无关。
2. `orchestrator._validate_reasoned_verdict_refs` 的数字存在性比对子条（7034-7046）——**仍在拦截终审判决正文**，AI 推导、换算、四舍五入出的数字只要不在 payload 里逐字出现就打回，重试耗尽整份终审降级为 rejected 兜底。
3. 原型材料卡校验器的**模糊词禁表**（`scripts/.../prototype_loop.py:112-141,312-317`，经 `src/event_research/card.py:61` 生效）——事实段里出现"可能/预计/may/could/would/should"等 24 个词就打错误码，而"Fed 预计维持利率"这种转述官方预期的合法事实写法会被误伤（只有加引号的原话豁免）。
4. 原型材料卡校验器的**解读段强制模糊词 + 事实/解读前缀相同检测**（同文件 142-152、323-334）——解读段必须含"可能/假设/若"等词才算合格，事实段与解读段前缀相同即判"没分离"：用词汇表和字符串前缀代理"作者有没有把事实和推断分开"，两头都会误伤合法写法。
5. `orchestrator._composite_submetric_issue`（7315，`_run_schema_guard` 内）——用 16 个中英文关键词判"高严重度冲突是不是把 CNN 恐惧贪婪指数的子项升格成总分"，命中即进 `consistency_issues`、把整份 schema_guard 报告压成 `passed=False`。

---

## 主表

**失败后果图例**：打回 = 报错喂回模型重试；重跑 = 触发整站/整阶段重跑；阻断 = 流程停止或拒绝执行；降级 = 产物被降级/字段被清空；标记 = 只留痕/标注/告警，不拦；静默 = 无反馈通道的簿记动作。

### 一、`src/agent_analysis/orchestrator.py`（主编排器，24 项）

| # | 机制 | 文件:行号 | 检查什么 | 失败后果 | 分类 | 理由 |
|---|---|---|---|---|---|---|
| 1 | STAGE_CONTRACT_PROMPT_REQUIREMENTS 登记表 | orchestrator.py:167-235 | 各站 prompts/*.md 必须逐字含有登记表里的关键词，由 tests/test_governance_input.py 强制对齐 | 阻断（CI 测试红） | A | 查的是自家静态文件里词在不在，是机械事实；注：它用"词出现"代理"说明书写清了规则"，有语义缝隙，但对象是自家文件不是 AI 散文，风险低 |
| 2 | _event_card_validation_errors | orchestrator.py:1801-1836 | 事件卡 supports/refutes 引用的 hypothesis_id 是否 ⊆ 本轮假说清单 | 打回 | A | 纯编号存在性比对；注释（1815-1835）自述已删掉三条措辞闸门和方向越权词表 |
| 3 | _event_card_semantic_notes / _event_card_semantic_warnings | orchestrator.py:410-442, 1839-1849 | 事件卡事实段的带符号数字是否与原材料同幅度反号；fact_summary 与 interpretation 是否逐字相同 | 标记（semantic_warnings + logger.warning） | B | 符号比对是"涨写成跌"的形状代理——材料里同时有 -2% 和 +2%（区间）时，卡只引其一也会命中；注释（417-419）自认"符号比对只是语义的形状代理" |
| 4 | _hindsight_causal_suspects | orchestrator.py:2234-2253 | 事件总结正文是否命中 7 条"事后/确定因果"正则（含 `因为.{1,40}所以` 这种泛匹配） | 标记 | B | 词表判散文语气；任何正常因果句都命中，纯噪音发生器，幸好已降级只留痕 |
| 5 | _event_section_summary_validation_errors | orchestrator.py:2256-2334 | [card:] 引用清单与正文一致、id ⊆ 本轮卡、禁 L1-L5 数据 ref、日期 ≤ effective_date | 打回 | A | 全是身份/隔离/时点类机械检查（2287-2291 注释自述删掉了计数与长度子条） |
| 6 | _validate_investigation_material_citations | orchestrator.py:2768-2791 | 调查报告各文本字段必须含 [M#] 引用且编号 ≤ 材料数 | 打回 | A | 编号存在性比对 |
| 7 | _validate_investigation_limits_against_materials | orchestrator.py:2864-2894 | 用 5 条正则扫调查员 limits 散文，若"否认材料有数字"而 materials_text 里出现任何数字则 raise | 打回（在 2451-2502 的重试循环里，耗尽则调查失败） | B | 正则判散文意思；材料里有一个与问题无关的百分数，调查员如实说"没有定量数据"也会被打回。杀伤力评估见文末 #1 |
| 8 | _counter_thesis_prompt_input_audit | orchestrator.py:3309-3339 | 反方站 payload 树里不得出现 thesis_draft.json 等禁读文件名 | 标记（审计字段） | A | 文件名出现与否是机械事实，且只审计不拦 |
| 9 | _validate_counter_thesis_draft | orchestrator.py:3262-3278 | 反方假说 refs ⊆ allowed_refs、必填字段非空 | 打回 | A | 引用身份 + 存在性 |
| 10 | _verify_claim_entry | orchestrator.py:4063-4181 | claim 的每条引用在证据登记册可解析、字段权限（supporting_only/rejected 等）不越权、有无独立强证据 | 降级（claim 从 verified 降为 downgraded/blocked） | A | 判的全是"引用在不在登记册、登记册上写的权限档是什么"——登记册元数据比对，不读散文 |
| 11 | _claim_ledger_publish_gate | orchestrator.py:4183-4194 | 汇总 claim 台账的 blocked/downgraded 状态 | 降级（发布闸门转 blocked/downgraded） | A | 机械状态汇聚 |
| 12 | _validate_thesis_hypothesis_responses | orchestrator.py:5254-5311 | 每个非 downgraded 竞争假说是否恰有一条回应、reject 是否带合法 ref | 打回 | A | 编号计数 + 引用身份 |
| 13 | _find_indicator_authority_overreach + _AUTHORITY_OVERREACH_RULES | orchestrator.py:552-570, 5587-5620 | 按指标权限档（technical/proxy/composite/structural）对指标散文跑关键词正则（如"超买…证明…估值便宜"） | 标记（semantic_warnings → quality_status=review_required） | B | 正则无否定感知："超买不能证明估值便宜"这种合法的否定句照样命中。杀伤力评估见文末 |
| 14 | _run_schema_guard（主体） | orchestrator.py:7272-7581 | 五层卡齐全、refs 合法、bridge/thesis 冲突按 {conflict_id, conflict_type} 认亲 | 重跑（schema_guard_retry 开启时带反馈重跑 thesis/critic/risk 一次）+ 标记 | A | 主体是结构齐全性与编号比对；7296-7305 注释明示"只判身份不判权限" |
| 15 | _composite_submetric_issue（_run_schema_guard 内嵌） | orchestrator.py:7315-7350, 7465-7470 | 高严重度冲突文本命中"子项/分项"类词而不命中"总分/综合"类词，即判"子项升格总分" | 标记+压状态（进 consistency_issues → passed=False → review_required） | B | 关键词判散文意思；合法地讨论"垃圾债偏好背离"只要不写"总分"二字就命中。杀伤力评估见文末 #5 |
| 16 | _validate_stage_evidence_refs | orchestrator.py:6857-6889 | 各站输出的 evidence_refs 是否 ⊆ synthesis_packet.evidence_index | 打回 | A | 引用身份比对 |
| 17 | _validate_reasoned_verdict_refs（引用部分） | orchestrator.py:6977-7033 | 判决正文至少有一条方括号引用、每条引用逐字 ∈ 索引 | 打回；耗尽则终审降级 rejected 兜底（6943-6953） | A | 引用身份比对 |
| 18 | _validate_reasoned_verdict_refs（数字存在性比对子条） | orchestrator.py:7034-7046, 7065-7075 | 判决正文里的百分数/小数 token 必须逐字出现在终审 payload 文本里 | 打回；耗尽降级 | B | 老板标尺明列"推导数字能不能在材料里逐字找到"是意思判断；另一研究员专项深挖，此处收录不展开。同类机制见 #52 |
| 19 | _validate_final_conflict_responses | orchestrator.py:7102-7148 | thesis 保留的高严重度 conflict_id 必须逐字出现在终审输出里 | 打回 | A | 编号逐字出现是身份比对（7114-7117 注释："不判意思"） |
| 20 | _validate_layer_card_v2 | orchestrator.py:7150-7211 | 层卡覆盖全部输入指标、function_id 无幻觉、metric 名与输入一致、quality_self_check 覆盖齐 | 打回 | A | 键集比对；7196-7204 还反向修正 AI 自报的覆盖清单（代码派生装配） |
| 21 | _validate_bridge_memo_v2 | orchestrator.py:7213-7270 | bridge 必填字段非空、path_id 去重、evidence_refs 不得含 event: 前缀 | 打回 | A | 存在性 + 前缀身份 + 隔离 |
| 22 | _strip_extra_forbidden_fields | orchestrator.py:484-… | pydantic extra_forbid 报错时剥掉多余字段 | 静默修复+留痕 | A | 修复型簿记，不判内容 |
| 23 | checkpoint 复验链（_load_reviser_checkpoint 等） | orchestrator.py:6807-6856, 8632 起 | 已落盘 artifact 重新过 model_validate 才准复用 | 重跑（复验失败则该站重跑） | A | 形状复验本身合法；注：它是语义 validator 的放大器——contracts.py:2521-2526 注释实录旧语义闸曾借它把旧产物整份作废 |
| 24 | _run_persistent_checks | orchestrator.py:8421-… | 调起 PC-01~PC-29 常设检查包 | 标记（汇总落盘） | A | 调度器，本身不判 |

### 二、`src/agent_analysis/contracts.py`（pydantic 合约，12 项）

| # | 机制 | 文件:行号 | 检查什么 | 失败后果 | 分类 | 理由 |
|---|---|---|---|---|---|---|
| 25 | 字段级约束群（min_length=1、Literal 枚举、extra="forbid"，遍布全文） | contracts.py 全文（例：478、505、1156） | 枚举合法、字段非空、不多塞字段 | 打回（pydantic ValidationError 进重试） | A | 形状校验的正面典型 |
| 26 | _validate_fact_interpretation_separation | contracts.py:431-444 | 事件卡 fact_summary 与 interpretation 是否逐字相同 | 标记（2026-08-31 起从 raise 降级为 logger.warning） | B | "两段散文逐字相同"只是"没分离"的形状代理——433-437 注释自认"判'事实与解读是否混写'要读懂内容，超出闸门职权" |
| 27 | _validate_answer_evidence_linkage | contracts.py:490-496 | answered_by_data 必须带 ref、partially_answered 必须写缺口 | 打回 | A | 枚举↔字段联动，机械 |
| 28 | _validate_concrete_data_side | contracts.py:511-520 | data_side_refs 不得是 "pure_data_report" 等占位词、confirmed/challenged 必须带 ref | 打回 | A | 占位词是固定字面量黑名单，属身份比对 |
| 29 | _validate_material_refs | contracts.py:543-547 | material 级异议必须点名 contradicted_data | 打回 | A | 联动存在性 |
| 30 | CompetingHypothesis 等宽容归一化群 | contracts.py:1163-1256 | 吸收模型字段名变体（别名映射、单值转列表） | 静默修复 | A | 仆从式归一化，不判内容 |
| 31 | _require_refs_for_numeric_percent_return（+ FinalAdjudication 侧同法 _normalize_long_term_assessment_payload） | contracts.py:1712-1726, 2407-2451 | 估值隐含回报字段含百分比数字但未附 evidence_refs → 清空该字段并留痕 | 降级（清空字段） | A | "有数字就要有引用"是存在性检查；注：它会删除 AI 写的内容，属 fail-closed 执法，曾把整份裁决炸掉后才降级为字段级（1716-1719 注释） |
| 32 | _normalize_stance_label | contracts.py:2469-2494 | stance_label 全半角归一、同义词映射、非法值清空 | 降级（清空非法值+留痕） | A | 枚举身份检查 |
| 33 | _stance_label_direction_conflict（被 2486 调用） | contracts.py:1611-1645 | 徽章（如"偏进攻"）与判决正文的方向词共现检测（带 16 字否定窗口） | 标记（已降级留痕） | B | 关键词代理"徽章与正文方向矛不矛盾"；2487-2490 注释自认"语义关键词判断（形状代理语义）"。杀伤力评估见文末 |
| 34 | _missing_evidence_as_direction_claim（被 2513 调用） | contracts.py:1648-1698, 2512-2536 | "缺失/缺乏"类词与"放大…风险"类词在同一逗号从句共现（带反事实豁免） | 标记（已降级留痕） | B | 句法共现代理"是否把证据缺失当方向性理由"——2521-2523 注释自认"超出闸门'只管机械事实'的职权" |
| 35 | _note_missing_reasoned_verdict | contracts.py:2453-2467 | 判决正文缺失则记 quality_gate.notes | 标记 | A | 存在性 |
| 36 | QualitySelfCheck 字段 | contracts.py:852-862 | coverage_complete / covered_function_ids | 代码装配（无失败态） | A | 正面先例：注释写明"由代码派生装配"，AI 不用自证 |

### 三、`src/integrated_synthesis_report.py`（第三层 IA，4 项）

| # | 机制 | 文件:行号 | 检查什么 | 失败后果 | 分类 | 理由 |
|---|---|---|---|---|---|---|
| 37 | _parse_and_validate | integrated_synthesis_report.py:620-822 | 伪引用剔除（白名单）、未知问题/卡片丢弃、无证据回答自动降级、正文方括号标注核对 | 静默剔除+留痕；model_validate 失败则打回 | A | 全是白名单身份比对与状态机联动；663-678 注释明示"伪引用硬闸门：不在白名单里的引用一律剔除并留痕" |
| 38 | _publish_gate | integrated_synthesis_report.py:1133-1203 | 汇聚 DataIntegrity/claim 台账/终审状态 → 发布档位 | 降级（转 audit_only） | A | 状态汇聚，无内容判断 |
| 39 | _check_time_consistency | integrated_synthesis_report.py:1205-1267 | 各输入产物的 as-of 日期一致（容差可由环境变量调） | 降级（不一致转 audit_only） | A | 日期比对，时点纪律的机械化 |
| 40 | _write_audit / _write_failure_record | integrated_synthesis_report.py:1102-1131 | 校验失败原因独立落盘 | 静默 | A | 簿记；1116 注释：供事后分辨"真违规"还是"规矩冤枉人" |

### 四、常设检查包 PC-01 ~ PC-29（post-run 只读审计，6 项条目）

| # | 机制 | 文件:行号 | 检查什么 | 失败后果 | 分类 | 理由 |
|---|---|---|---|---|---|---|
| 41 | PC-01~PC-05、PC-07~PC-09 | persistent_checks_a.py:196-871 | critic/risk 分料身份、引用全集对账、委托调查数对账、事件字段恒空、同名指标多值、指令键存在性 | 标记（post-run 检查报告） | A | 全是落盘产物间的身份/计数对账 |
| 42 | PC-06 立场字段检测子条 | persistent_checks_a.py:55, 724-726 | 调查材料体内是否含 "dominant_side"/"action_implication"/"不宜重仓"/"触发核心仓" 词 | 标记 | C | 前两个是字段名（身份）；后两个是中文字串——材料若正当转述"券商建议不宜重仓"会误伤。是否真误伤取决于材料来源构成，需总研究员研判 |
| 43 | PC-10 事件站措辞口径检测 | persistent_checks_a.py:878-918 | 事件站提示词指令区是否含旧 A 说法/旧 B 说法/统一限定语 | 标记 | A | 查的是自家提示词静态文本（890-897 注释：两种旧说法都作废）；注：用 regex 词表代理"措辞口径统一"，有语义缝隙，但对象是自家文件 |
| 44 | PC-11~PC-17、PC-19~PC-25、PC-28、PC-29 | persistent_checks_b.py:247-1313 | 输出示例指标存在性、占位日期、percentile 取值域、容器名与 severity 一致、null 占位进输入、冲突矩阵行完整、L4 数据陈旧+回购逐字重复行、canon 名一致、持仓锚计数、斜率材料状态、抗诉亮灯三条件、词表三账一致 | 标记 | A | 全是形状/身份/日期/枚举比对；PC-28（1191-1260）是"代码核验来源 + 模型判实质"的分工样板 |
| 45 | PC-18 回购逐字重复行子条 | persistent_checks_b.py:737-756 | 回购明细里逐字重复的行 | 标记 | A | 逐字重复是身份比对 |
| 46 | PC-26 yield gap 身份检查 | persistent_checks_b.py:1147-1181 | passport 的 usage=supporting_only 且 reason 含"诊断"或"辅助"关键词 | 标记 | C | usage 是枚举（A）；但"reason 必须含某关键词"用词存在性代理"身份是否写明"——reason 是谁写的（代码还是 AI）决定这是不是伪闸门，需总研究员核实 |

### 五、事件层 `src/event_research/`（+ 原型校验器，12 项）

| # | 机制 | 文件:行号 | 检查什么 | 失败后果 | 分类 | 理由 |
|---|---|---|---|---|---|---|
| 47 | validate_research_card（形状部分） | src/event_research/card.py:37-85 | 卡片字段齐、source_pointer 形状、可选字段非空、域名白名单豁免 | 标记（validation_errors 随卡落盘，不拦——runner.py:248-250 注释："二档撤发布闸门"） | A | 形状校验 |
| 48 | 原型模糊词禁表（FACT_HEDGE_WORDS_CN/EN） | scripts/layer2_supplement_prototype/prototype_loop.py:112-141, 306-317；经 src/event_research/card.py:61 生效 | fact_summary 含"可能/也许/预计/暗示/或将/有望/估计/may/might/could/likely/expected/would/should"等 24 词即打错误码（引号内豁免） | 标记（镣铐标签，进 cards_with_shackle_labels 计数） | B | 词表判"作者有没有在事实段里夹带推测"。杀伤力评估见文末 #3 |
| 49 | 原型解读段强制模糊词（INTERPRETATION_MARKERS） | 同上:142-152, 319-324 | interpretation 必须含"可能/假设/推测/猜想/若/也许/或许/不排除/待确认"之一 | 标记（错误码 interpretation_missing_hypothesis_marker） | B | 强制词汇出现代理"解读段有没有标明假设性"。杀伤力评估见文末 #4 |
| 50 | 原型事实/解读分离检测 | 同上:326-334 | fact 与 interpretation 前缀相同（去空白后 startswith 互判）即打错误码 | 标记 | B | "两段散文像不像"的字符串前缀版——解读段合法地以复述事实开头（"基于上述裁员事实，假设…"）会误伤 |
| 51 | validate_narrative_state | src/event_research/runner.py:126-142 | narrative_state 七字段齐全非空、无未知字段 | 标记 | A | 形状 |
| 52 | check_narrative_numbers | src/event_research/narrative_check.py:81-122 | 判断段里每个带单位数字（金额/百分比/基点）归一化后必须能在证据卡文本里找到等值数 | 标记（黄灯，注释 8-12 行明示"不拦截发布……代码容易误判，一定要避免乱拦"） | B | **orchestrator 数字逐字核对的同类机制**：AI 从卡里两个数算出的差值/合计永远找不到，必误伤推导数字；所幸只标注。收录理由见任务书 |
| 53 | validate_topics | src/event_research/topic_composer.py:123-155 | 任务书六字段非空、material_classes ∈ 合法枚举 | 降级（进 dropped 留痕不拒收） | A | 形状+枚举；124 行注释"闸门只守形状" |
| 54 | verify_keyword_ledgers | src/event_research/term_activation.py:324-398 | 词表三本账（overrides↔change_log↔candidates）身份一致 | 标记 | A | 329 行注释自认"校验形状与身份比对（闸门不判意思）" |
| 55 | check_budget + budget_gate hook | src/event_research/budget.py:60-80; hooks/budget_gate.py:21-33 | 经费卡余额，耗尽则 hook 阻断工具调用 | 阻断（预算耗尽） | A | 计数器，纯机械 |
| 56 | fetch_gate hook | src/event_research/hooks/fetch_gate.py:7-28 | web_fetch 的 url 必须 https 且在域名白名单 | 阻断（deny） | A | 白名单身份 |
| 57 | agenda.py 参数校验 | src/event_research/agenda.py:76-113 | source/status 枚举、question 非空、budget_cap 正整数 | 阻断（raise） | A | 入参形状 |
| 58 | reconcile_cards / quote_similarity | src/event_research/reconcile.py:96, 203-241 | 卡片的 source_pointer.quote 与抓取记录的 shingle 相似度是否过阈值 → verified/downgraded | 降级（downgraded_source_unverified 等档位） | C | 文本同一性的阈值化相似度比对：比"逐字"宽，比"意思"窄，介于身份与意思之间。阈值取值与误杀率没有实测记录，需总研究员研判 |

### 六、数据层与其余散件（10 项条目）

| # | 机制 | 文件:行号 | 检查什么 | 失败后果 | 分类 | 理由 |
|---|---|---|---|---|---|---|
| 59 | DataIntegrity | src/core/checker.py:29-471 | 指标缺失、未来日期、来源分歧、coverage 因子 | 降级（blocked → publish_status=blocked） | A | 数据面机械检查，发布闸门的合法主力 |
| 60 | _manual_data_staleness_check | src/core/collector.py:97-126 | 人工数据日期距运行参考日是否超阈值 | 标记（102 行注释："callers never block publish on this signal alone"） | A | 日期算术 |
| 61 | _merge_manual_ndx_valuation_checks | src/core/collector.py:205-… | 人工估值交叉核对合并进采集结果 | 静默 | A | 簿记 |
| 62 | recompute_belt 17 个 check_* 函数 | src/recompute_belt.py:237-1813（check_damodaran_erp_percentiles 等） | 用原始序列确定性重算分位/比率/均线，与管道产出比对 | 标记（findings 清单） | A | 重算带（recompute belt）是"数字由代码核"的正面典型——它自己去算，不要求 AI 自证 |
| 63 | tools_L4 审计函数群 | src/tools_L4.py:1861, 2929, 3002, 3770 | 成分股估值与第三方来源交叉核对 | 标记 | A | 数据交叉验证 |
| 64 | analog_history_audit 三函数 | src/analog_history_audit.py:227, 413, 565 | 历史类比序列审计 | 标记 | A | 数据审计（离线工具） |
| 65 | audit_visual_coverage | src/report_visual_coverage.py:34-… | 报告 HTML 的视觉覆盖审计 | 标记 | A | 离线审计工具 |
| 66 | 入参校验群 | src/tools_L1.py（9 处 raise ValueError）、tools_L2.py（11 处）、tools_L3.py（11 处）、tools_L4.py（5 处）、tools_common.py（3 处）、data_manager.py（2 处）、chart_generator.py（2 处）、expectation_ledger.py:535/573 等 | 日期格式、参数取值域 | 阻断（raise） | A | 函数入参形状 |
| 67 | validate_date | src/main.py:169-… | CLI 日期参数格式 | 阻断 | A | 入参形状 |
| 68 | control_service 两校验 | src/control_service.py:135, 164 | 控制台命令白名单、环境变量覆盖形状 | 阻断（拒绝执行） | A | 白名单身份 |

### 七、`src/agent_analysis/` 其余文件（7 项）

| # | 机制 | 文件:行号 | 检查什么 | 失败后果 | 分类 | 理由 |
|---|---|---|---|---|---|---|
| 69 | verify_instance_files | src/agent_analysis/context_spread.py:434-510+ | 投影文件与原文 sha256/标题/键路径/数值 token 逐一比对 | 标记（校验报告） | A | 查的是代码生成的投影文件，不是 AI 散文；439 行注释"不再自算自证" |
| 70 | _leakage_checks | src/agent_analysis/outcome_review.py:369-384 | 提示词产物里不得出现 outcome_review 等回流 token | 标记 | A | 固定 token 串扫描，隔离检查 |
| 71 | _validate_ref_digest | src/agent_analysis/vnext_reporter.py:2289-2299 | ref-digest 字段集合与体积上限 | 阻断（raise） | A | 形状+体积 |
| 72 | _layer_forbidden_checks | src/agent_analysis/vnext_reporter.py:6386-6399 | 层输入里不得有他层 highlights/跨层信号 | 标记（审计区展示） | A | 键存在性，层间隔离 |
| 73 | _generic_label_flags | src/agent_analysis/vnext_reporter.py:6414-6421 | payload JSON 里命中 "fear"/"risk_on"/"expensive" 等 9 个英文标签词即列出 | 标记 | C | 词命中代理"是否有泛化标签混入"；payload 是系统数据不是模型散文，但 JSON dump 里任何字段值含这些词都命中（如指标描述文本），误伤面是审计噪音，需研判 |
| 74 | validate_prompt_examples（+ llm_engine 导入时强制） | src/prompt_examples.py:693-758; src/agent_analysis/llm_engine.py:917-927 | few-shot 范例注册表与 tools 注册表键一致、4C 字段齐 | 阻断（SystemExit，启动失败） | A | 注册表键集身份比对 |
| 75 | _persist_checker_input | src/main.py:323-… | 把 DataIntegrity 输入落盘供复验 | 静默 | A | 簿记 |

### 八、提示词里的 AI 自查/自证/复述机制（14 项）

这一区没有代码强制力，但按任务书收录——它们是"让 AI 自己给自己把关"的注意力消耗点。

| # | 机制 | 文件:行号 | 要求 AI 做什么 | 失败后果 | 分类 | 理由 |
|---|---|---|---|---|---|---|
| 76 | system_constraints.md 六条纪律 | prompts/system_constraints.md:1-10 | 不编造数字、缺证据用条件语言、refs 只来自输入 | 无代码强制 | C | 原则条款是闸门宪法 v2 认可的"提示词原则"通道；但第 3 条"没有证据时使用条件语言（'可能''若…则…'）"与 #48 模糊词禁表方向相反——一个要 AI 多说"可能"，一个见"可能"就打标签，两套机制打架，需总研究员研判 |
| 77 | context_loader.md 质量检查清单 | prompts/context_loader.md:104-113 | 自查 data_summary 是否含日期、五层是否齐、"输出是否是有效的 JSON" | 无代码强制 | B | "输出是否是有效 JSON""字段是否齐"是代码零成本能查的，让分析师自查违反"不埋没人才"；意思项又无强制力，两头落空 |
| 78 | cross_layer_bridge.md 质量检查清单 | prompts/cross_layer_bridge.md:238-249 | 自查 claim 数、mechanism 有无、"严重度是否与证据相称"、"输出是否是有效的 JSON" | 无代码强制 | B | 同上：形状项浪费注意力，"严重度与证据相称"是让 AI 判自己的意思且无复核 |
| 79 | risk_sentinel.md 检查清单+质量检查 | prompts/risk_sentinel.md:97, 210-222 | 自查失效条件数、各字段非空、"输出是否是有效的 JSON" | 无代码强制 | B | 字段非空全部由 contracts.py pydantic 兜底（#25），清单是重复劳动 |
| 80 | thesis_builder.md 质量检查 | prompts/thesis_builder.md:344-359 | 自查字段非空、方向一致、conflict_ordinal 填写正确 | 无代码强制 | B | 357 行 ordinal 已改代码回填（"编号由系统按序号回填"）——好先例证明这类自查可代码化；剩余"方向与合计一致"等意思项仍在让 AI 自证 |
| 81 | critic.md 质量检查 | prompts/critic.md:168-177 | 自查"是否检查过跨层逻辑""是否检查过过度谨慎" | 无代码强制 | C | 过程要求（查没查过）无法机器化，属提示词原则通道；是否浪费需研判 |
| 82 | reviser.md 质量检查 | prompts/reviser.md:242-256 | 自查假说回应一一对应、refs 在索引内、"输出是否是有效的 JSON" | 无代码强制 | B | 249 行"所有 evidence_refs 是否存在于证据索引中"是 #16 代码闸门已在查的东西；245 行明示"无需自查"是好先例——同一清单里新旧两种哲学并存 |
| 83 | final_adjudicator.md 质量检查 | prompts/final_adjudicator.md:376-392 | 自查 headline 句式（≤30 字、无数字）、stance_label 与 final_stance 方向一致、refs 可追溯 | 无代码强制 | B | 385 行"stance_label 是否……与 final_stance 方向一致"是让 AI 判自己的意思，而对应的代码探针（#33）已按宪法降级为留痕——意思判断的执法真空由提示词兜底，正是宪法设计的现状，但是否算"废物机制"待老板定 |
| 84 | L1-L5 分析师 Output Discipline（五份） | prompts/l1_analyst.md:100-107（l2/l3/l4/l5 同构） | 只返回 JSON、core_facts 是对象数组、每个必分析指标有一条 analysis、缺失写进 quality_self_check | 由 #20 代码闸门兜底 | C | 形状要求与代码闸门重复表述，属"合约-说明书对齐"设计（#1 登记表的合法用途）；重复本身是否有害需研判 |
| 85 | controlled_investigator.md 逐字引用纪律 | prompts/controlled_investigator.md:6 | "数字、分位、日期只能从材料里逐字引用；禁止创造任何新数字" | 由 #6/#7 代码闸门配套 | B | 原则本身合理，但配套闸门 #7 把它执法成了"正则判 limits 散文"，提示词原则被代码越界背书 |
| 86 | event_card_interpreter.md 规则群 | prompts/event_card_interpreter.md:4-14 | 事实/解读分开、仅标题卡 upgrade_candidate=false、不复读免责声明 | 部分由代码装配兜底 | C | "事实段只许出现材料里逐字有的东西"是逐字纪律（与 #18/#52 同族但无代码执法）；措辞条款已按 2026-07-30 裁决由代码渲染代劳（orchestrator.py:1815-1827），设计方向正确 |
| 87 | integrated_adjudicator.md 边界与降级规矩 | prompts/integrated_adjudicator.md:21-47 | 抗诉三条件、cards_empty 降级写法 | 由 #29/#45 配套 | C | 代码核验来源、模型判实质的分工样板，原则通道合理使用 |
| 88 | deep_research_canon.py 内嵌提示词 | src/agent_analysis/deep_research_canon.py:1004 | "function_id 必须逐字来自输入指标键——抄错一个字代码会按输入键集回正或打回重写" | 由代码回正/打回 | A | 说明书如实描述代码行为的正面例：逐字要求有代码身份比对背书 |
| 89 | counter_thesis.md 证据纪律 | prompts/counter_thesis.md:39-51 | refs 必须来自证据索引 | 由 #9 兜底 | C | 原则+代码对齐 |

---

## B 类杀伤力评估（逐项）

### #1（最高危）：`orchestrator._validate_investigation_limits_against_materials` — orchestrator.py:2864-2894

**它拦截什么**：调查员在 limits 字段里写"材料没有定量数据"类措辞，而本次材料文本里（`materials_text`）出现任何一个带单位数字（正则 `\d+(?:\.\d+)?\s*(?:%|％|倍|点|分位|亿美元|万亿美元)`，2869-2874 行）。

**原样引用关键代码**：

```python
denies_reported_numbers = bool(
    re.search(r"(?:无|没有|未包含任何).{0,10}(?:定量|量化|数值|数字).{0,6}(?:数据|指标)", limits_text)
    or re.search(r"(?:未分析|没有分析).{0,12}(?:具体)?(?:数字|数值)", limits_text)
    or re.search(r"(?:不包含|不含|没有|无).{0,8}实际市场数据", limits_text)
    or (...)
)
if denies_reported_numbers:
    raise ValueError("limits overstates material absence: materials contain reported numbers; ...")
```

**误伤分析**：三层误伤叠加。第一，它把"材料里有没有数字"和"材料里有没有*回答问题所需的*数字"混为一谈——材料里有一个与问题无关的百分数（比如材料讲人口结构、附了一个 2.3% 的失业率），调查员如实写"材料未包含本问题所需的定量数据"就会命中第一条正则被打回。第二，正则不认识合法变体："未提供""缺乏""见不到"不在词表里能逃过，而"没有……量化指标"这种如实陈述必被抓——执法口径只惩罚措辞碰巧的人。第三，它在 2451-2502 的重试循环里 raise，每次误伤烧一整次调查调用，耗尽则整张调查失败。它判的是"散文的意思是否夸大了材料缺席"，正是老板标尺里"意思判断"的教科书案例。

### #2：`orchestrator._validate_reasoned_verdict_refs` 数字存在性比对子条 — orchestrator.py:7034-7046

**它拦截什么**：终审判决正文（reasoned_verdict）里的每个百分数/小数 token，必须逐字出现在终审站实际收到的 payload 文本里。

**原样引用关键代码**：

```python
missing_numbers = [
    token
    for token in self._reasoned_verdict_numeric_tokens(verdict)
    if token not in source_text
]
if missing_numbers:
    return [
        "final_adjudication.numbers_grounding: reasoned_verdict contains numbers "
        "that are not present in the stage payload (identity check, not semantic): "
        f"{missing_numbers[:5]}. Only use numbers that appear verbatim in the input."
    ]
```

**误伤分析**（本机制由另一研究员深挖，此处只列误伤面）：合法 AI 行为里有一整类会产出不逐字出现的数字——两个输入数字的差值（"较上月回落 0.4 个百分点"）、单位换算（payload 写 0.023、正文写 2.3%）、四舍五入、多来源合计。注释（7002-7005）自辩"是身份比对不是语义判断"，但按老板标尺，"推导数字能不能在材料里逐字找到"恰恰被明列为意思判断的例子：它惩罚的是"做了算术"这个行为，而算术是分析师的本职。失败后果是终审打回，耗尽后整份裁决降级为 rejected 兜底（6943-6953）。

### #3：原型材料卡模糊词禁表 — scripts/layer2_supplement_prototype/prototype_loop.py:112-141, 306-317（经 src/event_research/card.py:61 生效）

**它拦截什么**：材料卡 fact_summary（事实段）出现 24 个"模糊词"之一：中文 可能/也许/预计/暗示/或将/有望/估计/猜测/大概/或许，英文 may/might/could/likely/expected/expects/possibly/perhaps/maybe/probably/would/should 等。

**原样引用关键代码**：

```python
FACT_HEDGE_WORDS_CN: Tuple[str, ...] = ("可能", "也许", "预计", "暗示", "或将", "有望", "估计", "猜测", "大概", "或许")
FACT_HEDGE_WORDS_EN: Tuple[str, ...] = ("may", "might", "could", "likely", "expected", "expects", "possibly", "perhaps", "maybe", "probably", "would", "should", ...)
...
for word in FACT_HEDGE_WORDS_CN:
    if word in fact_no_space:
        errors.append(f"fact_summary_hedge_word:{word}")
```

**误伤分析**：它假设"事实段出现模糊词 = 作者在夹带推测"。但转述官方预期是事实段的合法内容——"Fed 官员预计年内维持利率不变"，"预计"的主语是 Fed 不是作者；引号豁免（309-310 行）只救加了引号的原话，中文财经文本大量转述不加引号。更系统性的矛盾：system_constraints.md 第 3 条要求 AI"没有证据时使用条件语言（'可能''若…则…'）"（prompts/system_constraints.md:7），同一个词在纪律里被要求、在校验器里被惩罚。当前后果只是卡片被打镣铐标签（runner.py:248-251 注释：二档已撤发布闸门），不拦内容，但它污染 `cards_with_shackle_labels` 计数——狼来了效应：标签不再可信，真违规混在冤案里被一起无视。

### #4：原型解读段强制模糊词 + 事实/解读前缀检测 — 同文件 142-152, 319-334

**它拦截什么**：两条互锁的词表规则——interpretation（解读段）必须含"可能/假设/推测/猜想/若/也许/或许/不排除/待确认"之一（否则打 `interpretation_missing_hypothesis_marker`）；fact 与 interpretation 去空白后前缀相同（startswith 互判）即打 `fact_interpretation_not_separated`。

**原样引用关键代码**：

```python
INTERPRETATION_MARKERS: Tuple[str, ...] = ("可能", "假设", "推测", "猜想", "若", "也许", "或许", "不排除", "待确认")
...
if not any(marker in interp_no_space for marker in INTERPRETATION_MARKERS):
    errors.append("interpretation_missing_hypothesis_marker")
...
if (fact_no_space == interp_no_space
    or interp_no_space.startswith(fact_no_space)
    or fact_no_space.startswith(interp_no_space)):
    errors.append("fact_interpretation_not_separated")
```

**误伤分析**：第一条把"标明假设性"这个意思压缩成"必须含某个词"——AI 写"这一链路若兑现，对应盈利预期上修"含"若"能过；写"传导路径是 X→Y→Z"这种机制陈述不含词就被打标签，哪怕它客观上就是假设。更糟的是它与 #3 方向相反：解读段被强制加"可能"，事实段被禁止加"可能"，AI 要在两个词表之间走钢丝。第二条用字符串前缀代理"事实与解读有没有分开"——解读段以复述事实开头（先引材料再给推断，正是合约 #26 想要的结构）会被 startswith 误伤。两条都只是标签（不拦），但标签错了会把"事实/解读分离"这个真原则搞成空话。

### #5：`orchestrator._composite_submetric_issue` — orchestrator.py:7315-7350, 7465-7470

**它拦截什么**：severity=high 且引用 CNN 恐惧贪婪指数的冲突，其文本（conflict_id/conflict_type/description/mechanism/implication 五字段拼接）命中"子项/分项/market momentum/put/call"等 9 个词之一、且不命中"总分/综合/total score"等 8 个词之一，即判"子项升格总分"。

**原样引用关键代码**：

```python
submetric_tokens = ("market momentum", "put/call", "safe haven", "junk bond",
                    "stock price strength", "stock price breadth", "market volatility", "子项", "分项")
aggregate_tokens = ("total score", "overall", "aggregate", "headline", "总分", "综合", "整体", "总指标")
if any(token in text for token in submetric_tokens) and not any(token in text for token in aggregate_tokens):
    return ("high severity conflict uses CNN Fear & Greed sub-metric without aggregate-score semantics; ...")
```

**误伤分析**：一条合法的高严重度冲突——"恐惧贪婪指数的 junk bond 分项与总分背离"——如果作者措辞是"junk bond 分项与整体读数背离"，"整体"在词表里能逃过；写"与指数读数背离"就命中。它惩罚的是措辞选择，不是语义升格。后果比纯留痕重：命中进 `consistency_issues`，把 `_run_schema_guard` 的 `passed` 压成 False（7572 行）、quality_status 压成 review_required（7573 行）——虽然 780 行的重跑条件只看 structural/missing，consistency 不触发重跑，但这份"未通过"的报告会进 schema_guard_report.json 和治理输入包，给下游站喂一个名不副实的"结构有问题"信号。

### 其余 B 类（杀伤力较低，均已降级或只标注）

- **#33 `_stance_label_direction_conflict`**（contracts.py:1611-1645, 2486-2493）：徽章与正文方向词共现检测。带 16 字否定窗口（1615-1619），"不宜加仓"能豁免，但"加仓窗口未到"这类非否定非肯定表述照样可能命中；已降级为留痕不拦，误伤只剩审计噪音。
- **#34 `_missing_evidence_as_direction_claim`**（contracts.py:1648-1698）：防"盈利证据缺失放大下行风险"这类真事故句子（1648-1650 注释）。有反事实豁免与分句边界设计，误伤面已收窄；已降级留痕。
- **#26 `_validate_fact_interpretation_separation`**（contracts.py:431-444）：逐字相同检测。只有两字段完全一模一样才命中——真一样的确大概率是没分离，误伤面小；已降级留痕。
- **#3' `_event_card_semantic_notes`**（orchestrator.py:410-442）：带符号数字反号检测。材料里同时出现 -2% 与 +2%（区间/两个主体）时，卡只引其一即命中；已降级留痕。
- **#4' `_hindsight_causal_suspects`**（orchestrator.py:2234-2253）：`因为.{1,40}所以` 这类泛匹配把任何因果句都列为"确定因果嫌疑"；已降级留痕，是纯噪音发生器。
- **#52 `check_narrative_numbers`**（narrative_check.py:81-122）：数字等值核对，推导数字必误伤；设计上自知（8-12 行注释："代码容易误判，一定要避免乱拦"），只标黄灯。
- **提示词自查清单（#76-#82 中的 B 类）**：不拦截任何输出，杀伤力是注意力税——每次调用让分析师花输出 token 和注意力自查"输出是否是有效 JSON"这类代码零成本能查的项，违反闸门六原则的注意力优先与不埋没人才两条。

---

## 附录：名字命中但实非闸门的函数（6 组 20 个，不计入 89 个总数）

这些函数名字带 check/audit/gate，但读源码确认是簿记、渲染或装配，不做任何拦截判断：

| 函数 | 文件:行号 | 实际职责 |
|---|---|---|
| _prompt_audit_stage_dir / _prompt_audit_stage_label / _prompt_audit_relpath / _archive_existing_audit_file / _save_prompt_audit_text / _save_prompt_audit_json / _infer_effective_date_from_prompt_audit / _infer_run_mode_from_prompt_audit / _infer_data_boundary_from_prompt_audit | orchestrator.py:6418-6565 | 提示词审计件的落盘与路径拼装 |
| _build_golden_pit_checklist / _checklist_status_from_claim | orchestrator.py:4414, 4538 | 黄金坑检查清单的装配与状态映射（从 claim 状态机械映射，不做校验） |
| _slim_object_run_gate_for_prompt / _strip_prompt_audit_bookkeeping_fields | orchestrator.py:7878, 8221 | 提示词瘦身与字段摘除 |
| _write_audit_index / _brief_audit_line / _agent_io_audit_section / _audit_section | vnext_reporter.py:1925, 2788, 6306, 6542 | 审计区 HTML 渲染 |
| _build_object_run_gate / _strip_recompute_audit_inputs | packet_builder.py:325, 44 | 对象边界卡装配（名字叫 gate 实为 payload）、输入摘字段 |
| _aggregate_analysis | news_layer_analyzer.py:256 | 聚合器，非校验 |

## 未核实事项（不知道，验证方法）

1. PC-26 的 reason 字段是代码装配还是 AI 填写——决定 #46 是不是伪闸门。验证方法：读 `evidence_registry` 的 authority_model 生成代码（orchestrator.py 内 `_field_authority_from_payload` 附近）。
2. `_generic_label_flags`（#72）的审计展示位置是否被任何人阅读——若无人读，它是纯浪费。验证方法：查 vnext_reporter.py 调用点生成的 HTML 区块。
3. 原型校验器的三条 B 类子条在事件层产物里的历史命中率（误伤频率）——需要跑历史 run 目录统计 `validation_errors` 分布，本研究员未做。
