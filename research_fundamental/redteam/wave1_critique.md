# 红队审查：第一波取证三条承重结论的攻击记录

> 本文是研究战役的红队产物。我的职责是唱反调：攻击 `research_fundamental/src_maps/` 下三份取证地图支撑的承重结论，能推翻就推翻，推不翻就划出它们的边界。每条论断给 `文件:行号` 或 git 提交号；行号以当前工作区快照为准。我没有读 `investigation_reports/` 下的任何文件；git 提交信息与其携带的 `WORK_LOG.md` diff 按任务书许可作为证据使用（它们记录的是老板的裁决原话与施工动机，属于"老板的想法"一类信任来源的留痕）。

**裁决总览**：结论一（抄写员问题已拆除）——**修正**；结论二（判意思的闸门只剩 2 个在拦截位）——**修正**；结论三（校准闭环是有意焊死）——**守住并补强**；总论断（烂不是整体的烂）——**修正**。

---

## 一、攻击结论一："AI 被逼成抄写员的问题已被系统性拆除"

### 原结论

机械字段已由代码装配、模型报序号代码回填编号，抄写员问题被系统性拆除（orchestration_map.md 第 6 节，依据 orchestrator.py:4980 起、llm_engine.py:89-107 等十二条证据）。

### 反方最强论证

"系统性拆除"这五个字言过其实。真实状态是：**编号与身份字段的抄写确实被拆除了，但数值转抄和提示词注意力税还留在原位，而且有一处漏网字段连回填代码都写好了却只肯填一半**。我在提示词和代码里找到七个反例，按硬度排序：

1. **IA 站的 `question` 原文转录是最硬的漏网字段。** 提示词明文要求"每条必须带 `question` 原文"（prompts/integrated_adjudicator.md:51 末段），也就是让模型把输入里的问题逐字再抄一遍。可代码明明有这个能力：同一个函数里，`question_id` 已经按序号回填、模型自填的一律不采信（src/integrated_synthesis_report.py:879-905），而 `question` 原文只在模型留空时才由代码补（同文件 905-907：`if not str(answer.get("question") or "").strip(): answer["question"] = question_text.get(qid, ...)`)。这意味着模型抄错原文不会被纠正、不会被发现。序号机制的设计原话是"抄写笔误物理关闭"，但这段代码恰恰留了一扇没关的门：同一行的左右两侧，id 物理关闭，原文敞开着。
2. **`CoreFact.raw_data` 是纯转抄字段，登记表自己承认。** llm_engine.py:89-91 的登记表写着："模型填。原始数据转存，vNext 主链不消费（只有 legacy_adapter 拿它做指标名匹配）"。一个主链不消费、只为旧报告器兼容导出存在的字段，每次层卡调用都要模型把输入原始数据整段转抄一遍——这正是"代码能干却让 AI 干"的活标本。
3. **层卡的数字转抄处于无闸区。** 层分析师要把输入里的数值抄进 `core_facts[].value` 和 `historical_percentile`（契约在 contracts.py:751-755，提示词要求在 l1_analyst.md:100-107 的 Output Discipline）。但层卡校验器 `_validate_layer_card_v2`（orchestrator.py:7150-7211）只查 function_id 和 metric 名，不查数值；全仓 grep `core_facts` 在 persistent_checks_a/b.py 与 packet_builder.py 零命中——没有任何代码把层卡数字对回输入。全系统唯一的数字逐字核对器只装在终审一站（orchestrator.py:7034-7046）。也就是说：五层分析师每人每次 run 都在做无核对背账的数字转抄，而"抄写员已拆除"的结论恰恰建立在数字核对器存在之上。
4. **代码已接管执行的纪律，提示词还在重复收注意力税。** 层站提示词由四个来源拼装（orchestrator.py:8063-8129：法典 + 范例 + 内联合约 + md 文件），其中内联合约 8083-8084 行仍写着"function_id 必须等于输入 function_id""metric 必须优先等于输入 metric_name"——而代码已经在 8772-8775 行把 metric 强制回填、在 8754-8770 行把拼错的 function_id 回正。执行被机器接管了，对模型的要求却没有撤，这是"拆了一半"的直接证据。
5. **质量检查清单里的机械项横跨五份提示词。** "输出是否是有效的 JSON"出现在 cross_layer_bridge.md:249、reviser.md:256、risk_sentinel.md:222——但 JSON 语法已由严格表单（llm_engine.py:564-603）和 pydantic 双层锁死，模型自查这一句纯属浪费。reviser.md:249 让模型自查"所有 evidence_refs 是否存在于证据索引中"，代码闸门 `_validate_stage_evidence_refs`（orchestrator.py:6857-6889）正在做同一件事。thesis_builder.md:344-346 让模型自查字段非空，pydantic 必填约束已经在兜底。
6. **沿用上游冲突时，序号之外的字段仍要模型重抄。** 模型报 `conflict_ordinal` 之后，代码只回填 `conflict_id`（orchestrator.py:5135，`_map_conflict_ordinals_to_ids` 只动这一个字段）；而输出模板（thesis_builder.md:249-258）仍要求模型为沿用冲突重写 conflict_type、severity、description、implication、involved_layers 五个字段。对"原样沿用"的场景，这五个字段都是上游冲突的确定性拷贝，代码能抄却没抄。
7. **DSH 调研员背着格式税。** persona.md:24 要求证据锚写成"c1、c2"且"与中文之间留空格……代码靠这个认卡"——让 AI 为代码的解析器调整标点，是典型的人伺候机器。

### 证据

上文每条已带行号；核心锚点重列：src/integrated_synthesis_report.py:905-907、src/agent_analysis/llm_engine.py:89-91、src/agent_analysis/orchestrator.py:7150-7211、7034-7046、8083-8084、8772-8775、5135、prompts/integrated_adjudicator.md:51、prompts/reviser.md:249、256、prompts/cross_layer_bridge.md:249、prompts/risk_sentinel.md:222、src/event_research/persona.md:24。

### 裁决：修正

编号类抄写（conflict_id、hypothesis_id、question_id、claim_ledger、revision_claimed_fields、事件卡身份字段）确实已被系统性拆除，且报错通道对模型明示（如 thesis_builder.md:357），这部分守住。但"问题已被系统性拆除"作为整句不成立。修正后的表述：

> **身份与编号字段的抄写已系统性拆除（模型报序号、代码回填）；但三类抄写负担仍在原位：层卡数值转抄无代码核对、IA 的 question 原文转抄留了半扇没关的门、五份提示词的质量检查清单仍在向模型收代码早已接管的注意力税。**

---

## 二、攻击结论二："判意思的闸门只剩 2 个还在拦截位"

### 原结论

普查 89 个机制中 20 个 B 类（意思判断），其中 18 个已降级为留痕不拦，只剩 2 个还在拦截位（gate_census.md 汇总统计节）。

### 反方最强论证

两个拦截位的判断本身复核属实（见下），但支撑它的普查口径有三处伤：总数不可靠、"29 项常设检查"多数了一项、"18 个降级留痕"里有一个其实还在往老板眼前挂红牌。

**第一处伤：89 这个总数有实锤遗漏。** 我按普查自己的收录规则（函数名带 check/validate/verify/gate）复核，至少漏了这些生效机制：

- `state_ledger.py:236-303` 的 `_validate_method_revision_entry`：方法修正台账的入库闸门，raise 拦截，且会跑 `git cat-file` 核验 change_ref 是不是真实提交——这是全仓唯一一个"查 git 提交真伪"的闸门，普查完全没有收录。
- `api_config.py:37、479、670、693` 的 API 配置验证簿记群（4 个函数）。
- `tools_L4.py:778、1714、3368` 的载荷形状校验（3 处）。
- 提示词侧的 14 项（#76-#89）漏了四个文件的自查/格式要求：`topic_composer.md`（出题官的输出格式与"好题五性"自查）、`persona.md`（DSH 调研员的人设纪律与证据锚格式）、`integrated_adjudicator_critic.md`、`event_section_summary.md`。

要说明的是：遗漏的全部是 A 类（形状校验）或提示词类，所以"B 类 20 个"的构成不受影响；但"89 个"这个总数从此不可引用，后续答卷要用必须重数。

**第二处伤：常设检查是 28 项，不是 29 项。** PC-27 已退役且编号永不复用（persistent_checks_b.py 注册表在 1323 行起，A 包 926-935 行；注册表注释与 run_checks_b 的 docstring 均写明"PC-27 已退役"）。orchestration_map.md 第 55 行说"29 项常设检查"，gate_census 标题沿用了"PC-01~PC-29"的区间写法——两个文件都按编号上限说话，实际在跑的少一项。

**第三处伤（最重）：#15 不是纯留痕，它有读者可见的出口。** `_composite_submetric_issue`（orchestrator.py:7315-7350）命中后进 consistency_issues，把 schema_guard 报告的 passed 压成 False（7572-7573 行）。这份"未通过"有两个出口：其一，HTML 报告的治理区会把 `passed=False` 渲染成红色"False"徽章（vnext_reporter.py:6271-6275，CSS class 为 bad）——老板翻开报告就能看到一面本不该由关键词词表决定的红旗；其二，run_summary.json 的 `publish_quality_status` 会被压成 `review_required`（src/main.py:932-935）。后者我查过，全仓没有代码读者（grep 仅命中写入点），所以它的实际杀伤力止于前者——但前者足够让"留痕不拦"四个字失效：它不拦内容，却在报告里制造一个名不副实的"结构未通过"信号。#13（指标权限越界词表，orchestrator.py:5531-5534 汇入同一 quality_status 通道）同理。

**反方向的复核也要如实记录**：我验证了普查对另外两条"留痕不出墙"的判断，它们属实。事件卡的 semantic_warnings 不进 IA 的输入（`_compact_card_for_prompt` 在 integrated_synthesis_report.py:989-1009，不含该字段），也不进报告渲染（vnext_reporter.py 零命中）；DSH 材料卡的镣铐标签只进简报计数（brief.py:79）和 run_summary，IA 消费端过滤只看对账状态（sync_patrol.py:143-210），不受词表标签影响。PC 分类抽查（PC-20② 正则判的是系统自己的错误消息而非 AI 散文，归 A 成立；PC-06、PC-26 标 C 是诚实的）未见系统性错判。

### 裁决：修正

"只剩 2 个还在拦截位"复核属实、守住——#7（orchestrator.py:2502 调用 2864-2894，正则判调查员散文且 raise 进重试循环）和 #18（数字存在性比对，7034-7046）都确实还在打回位置。但结论的支撑口径要修正为三句：

> **拦截位的意思判断闸门是 2 个，复核属实。但普查总数 89 不可引用（至少漏了 state_ledger 方法修正台账闸门等 8 处生效机制与 4 个提示词文件）；"PC-01~29"应为"28 项在跑、PC-27 退役"；"18 个降级留痕"应改为"17 个真留痕 + 1 个（#15）留痕之外还会在报告治理区挂红牌、在 run_summary 压发布档位标签"。**

---

## 三、攻击结论三："校准闭环是被有意焊死而非烂尾"

### 原结论

分数到方法修正的最后一截不存在，且这是有意设计——依据是 no_backflow_rule 等禁令明文（event_calibration_map.md 3.3-3.4 节，锚点 outcome_scoring_runner.py:29-31 等）。

### 反方最强论证（"这不是设计，是恐惧的堆积"）与它的失败

我带着对立假说去查 git 历史：如果禁令是事故后补丁堆出来的，时间线上应该能看到"先泄露、后加闸"的修补痕迹。查到的证据全部指向反面：

1. **每条禁令都是随产物出生自带的，不是事后补的。** outcome review 2026-05-23 出生，初版就带 `_leakage_checks` 主动泄露扫描（提交 a58b17a，提交名就叫 "Add outcome review and isolated historical runs"——"隔离"写在名字里）；反思库 2026-06-08 出生自带 `forbidden_for_current_run`（提交 8739ab9，属"TradingAgents 借鉴 Phase 0-5"这个有编号、有阶段的计划性工程）；打分器 2026-07-07 出生自带 `no_backflow_rule`（提交 4b2163e）；离线批跑器 2026-07-12 出生自带边界条文（提交 ddc08c9，提交名叫 "Power on calibration loop"——开环的那半截是主动点亮的，不是没人想起来）。
2. **分数从未进过提示词。** `git log -S "outcome" -- src/agent_analysis/prompts/` 零命中——不存在"先漏后焊"，因为从来没有漏过。
3. **最硬的证据是老板的两次明文否决。** 提交 fd87a17（2026-08-23）携带的 WORK_LOG 记录："修法⑤重申否决（重点记录）：校准闭环跑分/'最小真实一圈'演练——老板原话'房子没盖好你能让客户去验房吗'，系统完全稳定之前不做、**不再提议**。老板明确指出此事他重复裁决过却被反复重提"。这不是代码里埋着的恐惧，是老板当面说过两遍的"先别接通"。
4. **反方能找到的最好证据是冗余度**：同一道禁令叠了五层——模块 docstring（outcome_scoring_runner.py:20-30）、`NO_BACKFLOW_RULE` 常量（64-67 行附近）、每份打分产物内嵌 `no_backflow_rule` 字段（outcome_review.py:365、523）、`_leakage_checks` 主动扫描（369-384）、inquiry_router.py:32 与 orchestrator.py:1362、1556 的禁止清单。五层锁同一扇门，形态上确实像"反复加锁"。但每一层的引入提交都是计划性工单而非事故修复，所以"堆积"在时间线上不成立；这更像防御纵深（一道挡不住还有下一道）的刻意形态，只是纵深到五层是否必要，可以另开一问。

### 裁决：守住，但修正一处措辞

结论成立且比原表述更硬。唯一要修的是"焊死"这个词的所指：git 记录显示，**被焊死的是"分数回流进提示词"这条通道（五层禁令，出生自带），而"评分自动修正方法"这一截不是被焊死的已建物，是被老板两次明文否决的未建物**——通道随时可以按老板命令放行，桥还得新施工。这两者在"重写还是改"的决策里含义不同，答卷必须分开说。

修正后表述：

> **校准闭环的前半截（判断落账→事后打分→分数落账）是建成在跑的；分数→提示词/权重的回流通道被五层出生自带的禁令焊死，且老板在 2026-08-23 重申否决"系统稳定前接通跑分"（提交 fd87a17 的 WORK_LOG 记录）。这是有意设计，不是烂尾，也不是恐惧堆积——全部禁令随各自产物出生自带，git 历史中无任何先泄露后补救的痕迹。**

---

## 四、攻击总论断："烂不是整体的烂"

### 原论断

第一波取证的隐含总论断是：系统的烂是局部的、有方向的（闸门方向已对、新子系统干净），不是整体性腐烂。

### 反方最强论证（整体性腐烂的证据链）

我能为"整体性腐烂"找到的最强论证，不是某一处的病，而是**病的分布方式本身构成结构条件**：

1. **核心文件是单体巨兽。** orchestrator.py 9,954 行（grep -c 实测），占全仓 69,803 行 Python 的 14%；配上 vnext_reporter.py 7,019 行，两个文件占了全仓近四分之一。仅此一点是"大"不是"烂"，但下面几条说明大而脏。
2. **提示词在代码里长出了第二套。** 层站提示词由四个来源拼装（orchestrator.py:8063-8129：法典 + few-shot 范例 + 内联 v2 合约 + md 文件），其中 8065-8128 的内联合约与 l1_analyst.md 的 Context Boundary、隔离纪律大面积重叠——同一套纪律写两遍，改一处忘一处的结构条件已经成熟。全仓含中文指令散文（"必须/不得/禁止"簇）的 .py 文件有 11 个，orchestrator.py 一处就占 42 簇。
3. **死文件被测试防腐。** prompts/context_loader.md 描述的"Context Loader AI 站"在主链不存在，全仓代码对它零引用（grep 命中仅 tests/test_governance_input.py:1089 一处，且是死条款反向扫描）——它不死，只是没人读。
4. **死指标被架构闸门强制保鲜。** `get_qqq_net_liquidity_ratio` 注册在 TOOLS_REGISTRY（tools.py:49）、配着 few-shot 范例（prompt_examples.py:221-258）、被启动校验钉住（prompt_examples.py:693-758 要求范例键必须是注册表键的子集，不过则 SystemExit），但 DataCollector 的五层采集清单（core/collector.py:148-206）从不采集它，全仓无任何运行时调用。要删掉它得先过启动闸门——**保鲜机制本身在保护尸体**。
5. **概念键残骸。** tools.py:97 有 `"masters_perspective": None` 这个空值概念键，只有 legacy_adapter.py:902 还在填它。
6. **核心注册表文件有卫生死角。** tools.py:100-102 的注释是双重编码乱码（"浠嶇劧閫氳繃"这类字形），说明这个文件很久没有被人眼完整读过。
7. **同一道禁令叠五层**（见第三节）——单看是防御纵深，放进这份清单里看，是"只敢加、不敢减"的系统性体态。

这套论证的力道在于：它不是孤立毛病的清单，而是同一个体态（只增不减、多源拼装、尸体保鲜）在主链核心、提示词层、注册表层三个不同的高度上各自独立地出现。

### 正方守住的部分

腐烂的分布确实不均。新子系统干净：事件层九个闸门全是 A 类（event_calibration_map.md 4.3 节复核无误）；IA 的伪引用白名单闸门设计精良（integrated_synthesis_report.py:663-678，"许可集合 ⊆ 实际发送集合"恒真）；2026-08 以来的提交链（59f05e6 序号代报、386cfd2 编号回声代码化、1870aa4 文书字段装配六批）方向一致地把负担从模型肩上搬到代码里。git 月度频率显示 orchestrator.py 的改动在 9 月已收敛（4 次，vs 8 月 26 次）——它不再疯长，但也没有瘦下来。

### 裁决：修正

> **"烂不是整体的烂"在"闸门与新子系统"的范围内成立，但作为系统级判断过于乐观。实测证据支持更精确的表述：腐烂是结构性且跨层同态的（只增不减、提示词多源拼装、死物被闸门保鲜，在编排器、提示词、注册表三个高度同形出现），但它集中在最老的主链编排器与兼容层；新子系统健康、闸门演进方向正确。"重写还是改"的答案因此不能按"整体/局部"二分拍板，要按层分诊：主链编排器的单体化和提示词四源拼装是架构级病灶，重写收益最大处在这里；事件层与第三层是健康器官，重写会误伤。**

---

## 附：本文未验证的事项（不知道，验证方法）

1. 层卡 core_facts 里的错抄数字是否会流进终审事实卡菜单（fact_card 由证据索引装配，orchestrator.py:8005-8037；证据索引的数字取自哪里——层卡还是采集包原文——我没追完）。验证方法：读 `_build_synthesis_packet` 与 `_build_evidence_registry`，确认 evidence_index 的数值来源是 data_json 原文还是层卡转抄。若取自原文，反例 3 的杀伤力降级为"展示层噪音"；若取自层卡，它是主链级漏洞。
2. 18 个"留痕"标记的历史触发频率（是天天响的噪音还是从未响过的哑弹）。验证方法：扫 output/ 历史 run 目录的 semantic_warnings / consistency_issues 分布。
3. census 遗漏面我只做了函数名与提示词文件两个角度的抽查，不是全量重数。验证方法：按普查任务书的收录规则全量重跑一遍计数。
