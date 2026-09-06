# counter_thesis 上下文体检报告

> 对象：`t70_glm_check_20260902/prompt_audit/counter_thesis/attempt_1.prompt.txt`（318,262 字符，单 attempt）
> 投影保留率 96.8%；输出文件 `output.validated.json` 存在，E 环节按正路执行。

## 结论

本站编排纪律是全链少有的干净样本：指令区紧凑置顶、输出规格置尾、无越权、无指令冲突、证据白名单闭环验证通过、输出无复读无传染。主要问题集中在体量端：evidence_index 一段独占 65.5%（208,419 字符），46 个指标的 narrative+reasoning+first_principles_chain 全套搬运，其中约半数推理全文超出反方任务所需；同一数值在站内最多被陈述 41 次；且本站与 thesis 站的 Runtime 输入 85% 块级重叠，同份 evidence_index 两站各发一遍。特别关注三项的判定：**evidence_ref 159 次 = payload 字段名自然组成，不是指令念叨**（指令区仅 6 次且全部功能性）；**B2 重叠 85%**；**对抗质量要求段落给了可执行的对抗标准，不是空话**。

## 体检明细

### A. 顺序

**A1 段落编排** — 判定：合理 — 证据：指令区仅 1,935 字符（0.6%）置顶，依次为角色 → 对抗质量要求 → 输入边界 → 证据纪律 → 叙事文风约定（投影 offset 38-93 行）；输出字段规格（810 字符）置于 Runtime Input 之后（原文 offset 317,107），即「任务定义在头、数据在中、输出要求在尾」的标准布局。任务定义与输出规格相距约 315k 字符，但因两端夹数据、两端均为低注意力风险位（首尾），未见指令被数据掩埋的洼地效应。无「重要指令埋在中段」问题。

**A2 数据时序** — 判定：合理 — 证据：无逐 tick 行情序列；季度级财报历史表为旧→新排列（如 offset 193,996 起首元素 `2023Q3`，offset 196,805 起首元素 `2024Q3`，最新在末尾）。所有当前读数自带日期（2026-09-01/08-31/2026-08），`context_summary`（原文 offset ≈2,400）明示「早于运行时点属正常时点纪律」，无过期段落冒充当前状态。

**A3 few-shot 打断** — 判定：合理 — 证据：全文 `Example` 出现 0 次，无示例打断主干。

**A4 重试差异** — 不适用：本站仅 attempt_1。

### B. 体量与冗余

**B1 体量账本** — 判定：P1 — 账本（按原文 offset 实测）：

| 段落 | 字符 | 占比 |
|---|---|---|
| 指令区（含系统约束+角色+纪律） | 1,935 | 0.6% |
| packet_meta | 1,858 | 0.6% |
| layer_summaries | 20,076 | 6.3% |
| bridge_summaries | 30,739 | 9.7% |
| conflicts 三段合计 | 9,504 | 3.0% |
| **evidence_index** | **208,419** | **65.5%** |
| synthesis_guidance | 923 | 0.3% |
| bridge_v1_structure | 26,880 | 8.4% |
| bridge_v2_feedback_summary | 615 | 0.2% |
| non_stub_investigation_reports | 11,023 | 3.5% |
| allowed_evidence_refs | 3,698 | 1.2% |
| 输出规格+response rules | 1,317 | 0.4% |

最大段 evidence_index = 46 个指标 × 每个 ~4.5k 字符，字段含 `current_reading`/`normalized_state`/`narrative`/`reasoning_process`/`first_principles_chain`/`cross_layer_implications`/`misread_guards`/`falsifiers` 全套（投影 offset 1296-1373 为 L1 首两例）。判据检验：反方任务是「对现有结论做重新归属与重新加权」（输出 `independence_boundary` 自述），需要的是各层结论读数与主线解释——`narrative`+`normalized_state` 已足够；`reasoning_process`（~800 字/指标）与 `first_principles_chain`（5 环/指标）是层分析师的推理过程回放，删除后反方判断不会变差。估算约 90-100k 字符属可裁剪（占总 prompt ~30%）。

**B2 站内重复** — 判定：P1 — 同一事实五处复读，实测（按段落区间分类计数）：
- `4.75`（10Y 名义利率）：layer_summaries 7 + bridge_summaries 3 + conflicts 4 + evidence_index 24 + bridge_v1 3 = **41 次**
- `2.44`（10Y 实际利率）：5 段合计 32 次
- `99.6`（实际利率分位）：6 段合计 36 次
- `8.97`/897bp（CCC-BB 分层利差）：合计 18 次
- `16.34`（VIX）：14 次
其中 evidence_index 与 layer_summaries 的 `key_evidence` 互为近逐字复读（例：L1 首指标 `current_reading` 原文 offset ≈65,480 与 layer_summaries `key_evidence` offset ≈5,700 同文）。三层（layer_summaries→bridge_summaries→evidence_index）非严格互相复制但大量共引同一数字，复读主源是 evidence_index 把每层结论在各指标条目里再讲一遍。

**B2（跨站对照，特别关注项）** — 判定：P1 — counter_thesis Runtime 输入 316,327 字符 vs thesis Runtime 输入 285,848 字符；随机抽样 300 个 500 字符块，**85%（255/300）在对方 prompt 中逐字出现**。两站各嵌入同一份 synthesis_packet：`evidence_index` 在 counter_thesis 为 208,419 字符、在 thesis 侧约 212,705 字符（含格式差异），即 **~210k 字符的同一证据包向两个下游站各发一遍**，系统级重复搬运约 27 万字符。两站任务不同（反方 vs 主线），共享底料合理；不合理的是底料本身带了 65% 的推理全文（见 B1）——裁掉推理全文后两站重叠负担同步减半。

**B3 粒度错配** — 判定：P2 — 本站无逐 tick 行情 dump，总体优于多数站。剩余问题：15 个超长内联数组中 14 个是季度财报/日历历史全量记录（各 2,146-3,290 字符，如 offset 193,996 `calendar_quarter/period_start` 逐季记录、offset 219,248 AAPL 等 ticker 财报日历）。反方用到的是「盈利上修斜率 +3.9%」「资本开支同比 +84%」这类统计量（输出 CTH_01 引用），逐季全量记录可预处理为摘要+极值。

### C. 质量

**C1 指令冲突** — 判定：未发现 — 系统约束 6 条（不得编造数字/条件语言/refs 来源/空数据纪律/合法 JSON）与证据纪律、输出规格互相一致。交叉验证：证据纪律要求「所有 refs 必须来自 allowed_evidence_refs」（offset ≈1,300），allowed 列表 93 项（offset 313,247-316,945）；输出实际使用 33 个 ref，逐一核对**全部被列表覆盖**（含 `parent#field` 子引用形式，父 ref 均在列）。无「要明确方向」vs「必须保留冲突」类对撞。

**C2 死指令** — 判定：未发现（抽查 5 项全活）— `support/counter/diagnostic_evidence_refs`（输出有且合法）、`cannot_explain`（两条假说各 4-6 条实文）、`falsification_conditions`（各 4 条、含具体触发点位如 702.7-703.4）、`prompt_input_audit`（输出全键填写）、`independence_boundary`（有实文）。输出规格各字段虽标「可选」，输出全部落实。

**C3 黑话词典** — 判定：P2（仅 1 项传染源）— 清点结果：系统自造词极少。「`non_stub_investigation_reports`/`stub`」出现 5 次（首次 offset 1,087，输入边界处），**未解释 stub 惯例**——新模型可从上下文猜出「非占位调查报告」，但严格讲缺半句解释，列入传染源。「转化信号」1 次（offset 307,072，bridge_v1 引文内，上下文有实例可推断）。「地心引力」（offset 4,394）「买单」（offset 30,638）为修辞非代号。通用金融术语（OAS、SKEW、ERP、put/call）不计。与全链多数站相比，本站黑话面极小。

**C4 数据新鲜度** — 判定：合理 — 运行时点 2026-09-02（packet_meta `generated_at` offset ≈2,100），数据日期 2026-09-01（VIX/HY OAS 等）、2026-08-31（10Y）、2026-08（Fed Funds）、2026-07（M2），全部早于运行时点 1-30 天且逐条带日期标注；`context_summary` 明示时点纪律。无字段名暗示「当前」而值过期的情况。

### D. 隔离

**D1 越权扫描** — 判定：未发现越权 — 全文关键词扫描：`thesis_draft`/`analysis_revised`/`final_adjudication` 各 2 次，全部落在两处：输入边界的**禁止清单**（offset 1,156-1,260「你禁止读取或引用」）与 `forbidden_context_refs` 合同字段（offset 316,978-317,032）——均为禁令元数据，非内容泄漏。`browser_sidecar`/`user_decision_profile`/`golden_pit`/`apparent_cross_layer_signals` 0 次。`layer_cards/L1.json` 等 3 次均为 ref 字符串出现在调查报告的 evidence_refs 引用里（offset 309,365、312,317），非卡片内容。旁证：输出 `forbidden_inputs_read: []` 且 `independence_boundary` 逐项声明未读三份禁件。隔离宪法执行到位。

### E. 输出闭环

**E1 叙事字段体检** — 判定：优秀 —
- **黑话传染**：无。叙事散文（hypothesis_text、cannot_explain、falsification_conditions、principal_counterargument）全部使用行业通语与带日期的数字；C3 清单中的 `stub` 未进入叙事。
- **复读机检测**：随机抽 69 个 25 字符片段（覆盖 2 条假说文本、adjudication_reason、cannot_explain、falsification_conditions、principal_counterargument），**0 个与 prompt 逐字相同**；最长逐字公共串检索为 0。模型在作答不是在背题。
- **簿记语言密度**：结构字段（33 个 refs）全部待在结构位；散文中仅 1 处字段名直出——`falsification_conditions` 里「cuts_priced_bps远离零而非回摆」（输出文件 61 行），其余数字均嵌在因果链中服务判断（如「FGI 35.4 且恐惧集中于信用子项」用于压低惊喜门槛的论证）。
- **长度纪律**：输出规格未设长度要求；实际假说文本 692/490 字符、adjudication_reason 316/353 字符、principal_counterargument 483 字符，克制且信息密度高，无违规可谈。

**E2 因果对** — 未发现因果 — 材料端的两个病灶（evidence_index 过量、站内复读）在输出端**没有对应毛病**：输出论证全部锚定在结论层读数与分位数字上，未见因材料冗余导致的混淆、串层或复读。反向推论成立：输出只消费了 evidence_index 中结论层信息，恰证 B1 中「推理全文搬运非必需」的判定。唯一可记的轻微关联：材料允许引用的 `parent#field` 子 ref 语法（证据纪律段）被输出正确使用（如 `L1.get_fed_funds_rate_path#state`），说明该纪律段落的可执行性经输出验证为真。

## 特别关注项裁决（委托方三项）

1. **evidence_ref 159 次**：**payload 自然组成，非指令念叨**。指令区（前 1,935 字符）仅 6 次，全部是功能性字段指称（系统约束第 4 条、输入边界、证据纪律对 `support/counter/diagnostic_evidence_refs` 与 `allowed_evidence_refs` 的定义）；其余 153 次全在 Runtime Input 数据区，构成是 `"evidence_refs": [` 数组键 78 次、`parent_evidence_ref` 值 ~47 次、`counter_evidence_refs` 等——是证据条目结构的字段名，属数据形状，不构成注意力污染。
2. **B2 上游包重叠度**：与 thesis 站 Runtime 输入 85% 块级重叠（255/300 抽样块逐字命中），同份 ~210k 字符 evidence_index 双站各发一遍。共享底料设计合理，问题在底料含 ~50% 推理全文（见 B1/B2）。
3. **对抗质量要求/证据纪律可执行性**：**给了可执行标准，不是空话**。证据：①方向对抗三分支规则（主线防守→构造最强建设性解读；进攻→最强看空；冲突→一多一空，投影 offset 48-53 行）；②排除免责声明式假说（「"证据不够所以主线可能不对"不算合格的反方假说——那是数据边界，不是替代解释」）；③可操作的失败出口（「构造不出有说服力的对立解释本身也是信息……明确写"当前证据下无法构造有区分力的反方假说"并说明缺什么观察」）。输出端验证：CTH_01 确为方向对抗（对中性偏防守主线做多侧对抗，`prompt_input_audit.main_line_stance_assessed` 有记录），CTH_02 为解释对抗，组合合规。证据纪律配 93 项白名单+子 ref 语法+输出校验通过，闭环完整。

## 病灶清单（按严重度排序）

| 严重度 | 病灶 | 证据位置 |
|---|---|---|
| P1 | evidence_index 全套逐指标推理搬运占 prompt 65.5%（208,419 字符），reasoning_process/first_principles_chain 等约半数内容超出反方任务所需 | 原文 offset 65,387-273,806 |
| P1 | 同一数值站内五处复读：「4.75」41 次、「99.6」36 次、「2.44」32 次，主源是 evidence_index 对 layer_summaries 的近逐字复读 | offset 65,387-273,806 及各段 |
| P1 | 与 thesis 站 Runtime 输入 85% 块级重叠，同份 ~210k evidence_index 双站各发一遍，系统级重复约 27 万字符 | 两站 prompt 对照（本站 offset 65,387 起） |
| P2 | 14 个季度财报/日历历史全量表（2.1-3.3k 字符/个）可预处理为统计摘要，粒度粗于任务需要 | offset 193,996 / 219,248 / 230,839 等 |
| P2 | 「stub/non_stub」系统自造词未解释，1 项黑话传染源 | offset 1,087 |
| P2 | 输出散文 1 处字段名直出（cuts_priced_bps），未翻译成人话 | output.validated.json:61 |

## 修复建议

1. **（对应 P1×2）裁剪 evidence_index 推理全文**：反方站只投递每指标的 `current_reading` + `normalized_state` + `narrative` + `risk_flags`，砍去 `reasoning_process`/`first_principles_chain`/`misread_guards`/`falsifiers`/`cross_layer_implications`。预计 208k→~100k 字符，站内复读与跨站重复同步减半。改动点：synthesis_packet 组装器对 counter_thesis/thesis 消费者增加「结论层视图」。
2. **（对应 P1×3）上游包去重**：把「结论层视图」做成共享构件，两站引用同一份精简包；bridge_summaries 与 evidence_index 的重复陈述由组装器保证只保留一处全文、其余处只留 ref 指针。
3. **（对应 B3）财报历史预处理**：组装器把逐季记录压成「近 8 季趋势 + 极值 + 最新值」一行摘要，原始表留作可展开附件（本任务实际未消费逐季明细）。
4. **（对应 C3）补半句解释**：输入边界处「non_stub_investigation_reports（非占位的真实调查报告）」加括号注释，一个词的成本消除唯一传染源。
5. **（对应 E1/P2）文风约定补一句**：叙事字段中「字段名出现时改写为业务语言」，如 cuts_priced_bps → 「期货隐含的降息幅度报价」。
