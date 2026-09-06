# reviser（修订者）上下文体检报告

> run：`t70_glm_check_20260902` · attempt_1 · 原文 213,908 字符（`prompt_audit/reviser/attempt_1.prompt.txt`，下称 P，偏移为该文件字符 offset）
> 输出：`output.validated.json` 存在，E 环节按其分析。

## 结论

reviser 的指令侧（任务定义、两条硬合约、修订原则、检查清单）编排在 25 站标准形态内、质量较高，D1 未发现越权，输出是一次真实修订（非复读）。最重的病灶在体量结构：**本站的主菜——critic+risk 反馈合计仅约 5.7k 字符（占 governance_input 3.9%），而被标为「对照用」的证据索引 `key_evidence_refs` 高达 100.5k 字符（47% 整个 prompt）**，其中 29.5k 是两条 M7 每公司季度原始序列（B3），另有 10.8k 的 `fact_card` 与索引 `current_reading` 逐字重复（B2/P1）；次要病灶是 `revision_claimed_fields` 的指令冲突——正文要求模型精细自报并以 PC-03 不合格相胁，输出规格却声明「模型自报会被覆盖」，实测代码确实丢弃了模型清单（C1/C2/P2）。

## 体检明细

### A. 顺序

- **A1 段落编排** — 判定：合理（附一处 P2）
  - 结构：指令区 P 0–9,890（5.8%）→ Runtime Input P 9,890–211,379（201,489 字符，94.2%）→ 输出字段规格 P 211,379 → 冲突清单 P 213,369 → Response Rules P 213,576。
  - 两条硬合约位置好：「竞争假说回应纪律」P 655、「证据引用纪律」P 1406，紧跟角色定义；修订原则五条（接受批评/整合风险/修结构/保留冲突/调立场）在 P 5559，叙事文风约定 P 5275，绝对禁止清单 P 7439——全部在数据块之前，无埋没。
  - 两个序号机制都有双向锚定：正文 P 2936 前向引用「提示词末尾『冲突清单（按序号引用）』」，末尾 P 213369 给出 TC_01–TC_05 序号表；实测生效——raw 响应中 `conflict_id`/`hypothesis_id` 出现 0 次（模型没自填），validated 中由系统回填为 `TC_01` 等。P2 一处：正文「输出格式」示例在 P 3592，权威规格「形状以此为准」在 20 万字符之后的 P 211379，两者相隔整个数据块，靠 Response Rules（P 213576）末尾补一句「形状冲突时以规格为准」弥合。
- **A2 数据时序** — 判定：合理。季度序列旧→新升序（capex AAPL 首条 2023Q3，buyback `latest_period_end: 2026-06-30`）；运行时读数日期 2026-09-01/08-31 对 09-02 的 run 属新鲜；滞后数据被显式标注（`known_data_gaps`：「锚截至2026-08-14、滞后运行时点19天」「持仓快照过期42天…降级使用」）。
- **A3 few-shot 打断** — 判定：合理。仅一个「修订示例」（1,273 字符）位于指令区末尾 P 8610、数据块之前，未切碎主干。
- **A4** — 本站单 attempt，不适用。

### B. 体量与冗余

- **B1 体量账本** — 判定：P1（主菜与配菜比例倒挂）
  governance_input 值合计 ≈148.5k 字符，分布：

  | 块 | 字符 | 占 input |
  |---|---|---|
  | `key_evidence_refs`（53 条证据卡全文） | 100,546 | 67.7%（占整个 prompt 47.0%） |
  | thesis 草稿（thesis_* 20 个字段，被修订对象） | ≈19,731 | 13.3% |
  | `fact_card` | 10,838 | 7.3% |
  | 其余上游（TC 冲突 3,392、principal_contradictions 2,440、counter_thesis 2,788、known_data_gaps 1,192、unresolved_questions 863、firewall 1,014 等） | ≈11,960 | 8.1% |
  | **risk 反馈**（must_preserve_risks 1,736 + opportunity_costs 1,086 + confirmation_costs 922 + false_safety_risks 606） | **4,350** | **2.9%** |
  | **critic 反馈**（critique_overall 894 + critique_cross_layer_issues 488） | **1,382** | **0.9%** |
  | schema guard 结果 | 10（全通过、空数组） | ~0% |

  「按反馈修订」这一职责的主菜（反馈 5.7k）只有证据索引的 **1/17.5**。索引有部分必要性（证据引用纪律 P 1406 要求 refs 必须出自索引；输出实际用了 45 个 distinct ref、全部命中索引，零编造），但 53 条每条都带 `reasoning_process`（6.5k）/`narrative`（5.4k）/`misread_guards`（3.8k）/`cross_layer_implications`（2.1k）等 19 个字段——修订者对照 ref 合法性只需 ref 名 + `current_reading`（3.4k）+ authority 标记，叙述性字段是给「读证据做判断」的站用的，不是给「改稿」的站用的。判据检验：删掉索引里的叙述字段，本次输出的判断不会变差——revision_summary 里「撤回分位表述」所对照的 `known_data_gaps`（1,192 字符）才是那一票的真正依据。
- **B2 站内重复** — 判定：P1
  `fact_card`（10,838 字符，53 条）与 `key_evidence_refs` 的键 100% 重合（53/53），reading 字段与索引 `current_reading` 抽验 34 条中 29 条逐字相同。同一句子「+40.0bp（2026-09-01），未倒挂…」在 P 内出现两次：offset 49,865（索引内）与 190,873（fact_card 内）；「2.44%（2026-08-31）」同样两见。fact_card 是索引 current_reading 的整套复读，≈10.8k 字符纯冗余。与 thesis 站对照：thesis 的 prompt（298,713 字符）不含该索引，草稿文本系 thesis 输出传入，属必要传递，非重复搬运。
- **B3 粒度错配** — 判定：P2
  索引内两条巨型条目：`L4.get_m7_capex_cycle#companies`（14,787）与 `L4.get_m7_buyback_flow#per_company`（14,699），合计 29,486 字符（索引的 29%），内容是 7 家公司 × 12/5 个季度的原始序列（AAPL capex 自 2023Q3 起、含 `period_start/period_end` 逐季结构）。修订者对这两条的真实需要是「ref 合法 + 最新读数」（各条已有 `latest_quarter_buyback_usd_bn`/`ttm_buyback_usd_bn` 摘要）；逐季全量 dump 把预处理活推给了注意力。输出中这两个 ref 仅被当作父引用挂在支撑链上，季度明细未被消费。

### C. 质量

- **C1 指令冲突** — 判定：P2（1 对）
  - `revision_claimed_fields`：正文 Step 5（P 7090 起）要求「同时填写…机器会逐项核对（PC-03），对不上整份产出判不合格」，质量检查清单亦有一条；而输出规格（P 211379+）写「**由代码 diff 装配，模型自报会被覆盖**」。若自报必被覆盖，PC-03 核对的对象就说不通——两处指令对同一字段的归属陈述互相打架。
  - 未发现其他冲突对：「保留未解决冲突」（P 5xxx）与「必须给明确方向」类要求在本 prompt 中已用 verdict 三选一、`absorb_partially` 合法化等方式调和；系统级「不得编造分位」与输出规格无强制定量字段。
- **C2 死指令** — 判定：P2（1 项实锤，序号机制均活）
  - **死**：`revision_claimed_fields`。模型在 raw 中自报 23 项（含 `conditions`/`weight`/`reasoning` 等嵌套键，违反正文「只列 revised_thesis 叶子字段名」），validated 中被代码 diff 重写为 17 项（差集：模型多报 7 项、漏报 `confirmation_cost`）——自报整体被丢弃，正文那一整段填写教学 + PC-03 威胁是让模型空转。
  - **活**：`hypothesis_ordinal`（raw 3 次、3 条假说恰各一条）、`conflict_ordinal`（raw 5 次、与清单一一对应）、`conflict_id`/`hypothesis_id` 禁自填（raw 0 次出现，系统回填成功）。
- **C3 黑话词典** — 判定：基本合理（1 个轻传染源）
  - 已解释：`mixed_field_authority`（36 次，P 1406 段有定义）、TC_01–05（23 次，末尾序号表兜底）、Schema Guard（4 次，角色定义中引入）、synthesis_packet（14 次，P 1406 段括号内给出与 `key_evidence_refs` 的关系）。
  - 轻传染源：**PC-03**（1 次，P 7090 附近「机器会逐项核对（PC-03）」）——新模型只能猜是某校验码，且如 C1 所述该指令本身归属不明。「Decision Semantics」（1 次，P 7430 段「必须遵守」内）无指向性说明，但后文自带字段列举，风险低。「简式收益差距」（12 次）为系统自造缩语，首现于 thesis_main 数据内无定义，语义可猜，列为观察项。
- **C4 数据新鲜度** — 判定：合理。读数 2026-08-31/09-01，run 日 09-02；唯二过期快照（19 天、42 天）均在 `known_data_gaps` 显式标注降级，无字段名暗示「当前」实为旧值的情形。

### D. 隔离

- **D1 越权扫描** — 判定：未发现越权
  全 payload 检索：`final_adjudication` 0、`final_adjudicator` 0、`browser_sidecar` 0、`user_decision_profile` 0、`golden_pit` 0、`layer_raw_data` 0、`apparent_cross_layer_signals` 0。reviser 处于 thesis 之后的治理层，看到全五层证据索引与 bridge 冲突属于其修订职责内的合法视野；唯一 `one_liner` 命中是草稿 `thesis_reader_conclusion.one_liner`（被修订对象本体），非越权。

### E. 输出闭环

- **E1 叙事字段体检**
  - **黑话传染**：轻。`revision_summary`（674 字符）裸用字段名「known_data_gaps」「why_retained」（「——known_data_gaps明示历史分位整体缺失」），违反本站自己的文风约定（P 5275「字段名…不进叙事字段」）；`accepted_critiques` 第 1 条结尾「（但未采纳事前减仓，见rejected_critiques）」同病。各 1 处，密度低。
  - **复读机检测**：未发现病灶。被列为修订的字段确属重写——`main_thesis` 新旧最长公共子串 34 字符（旧 187/新 407）、`valuation_assessment` 25 字符、`payoff_assessment` 25 字符；`state_diagnosis` 新旧 187/187 全同但**未**出现在自报与 diff 清单中，属诚实的未修订保留，不是背题。
  - **簿记语言密度**：叙事散文里 ref/数字嵌在因果链中（如 valuation_assessment「trailing盈利收益率比10年期美债低1.42个百分点（简式差距、诊断用）」），无裸列；45 个 distinct 证据 ref 全部落在结构字段。
  - **长度纪律**：输出规格对叙事字段无长度要求，实际各叙事字段 187–674 字符，克制。
- **E2 因果对**
  1. **能连**：文风约定位于 P 5275（数据块之前、仅 284 字符、无逐字段点名）→ 输出 `revision_summary`/`accepted_critiques` 各出现 1 处裸字段名（`known_data_gaps`/`why_retained`/`rejected_critiques`）。弱因果（材料位置×措辞 → 输出小瑕疵），P2。
  2. **能连**：`revision_claimed_fields` 双重指令（正文教学+威胁 vs 规格声明覆盖）→ 模型照教填写但报了 7 个不合规范的嵌套键、漏 1 项，整份自报被代码丢弃。指令本身的归属混乱直接产出了这份无效劳动，P2。
  3. **连不成**：fact_card 10.8k 重复与 29.5k 季度 dump 未在输出端造成任何具体毛病（引用纪律全部遵守、无编造 ref），属纯浪费——明说「未发现输出因果」。

## 病灶清单（按严重度排序）

| 严重度 | 病灶 | 证据位置 |
|---|---|---|
| P1 | 主菜倒挂：critic+risk 反馈仅 5.7k（3.9%），证据索引 100.5k（67.7%），索引 53 条全字段证据卡远超「修订对照」所需 | P offset 49,676 起；payload `governance_input.key_evidence_refs` |
| P1 | `fact_card`（10.8k）与 `key_evidence_refs.current_reading` 整套逐字重复（53/53 键重合、29/34 抽验全同） | P 49,865 与 190,873 同句两现 |
| P2 | `revision_claimed_fields` 指令冲突：正文教学+PC-03 威胁 vs 规格声明「模型自报会被覆盖」，实测自报 23 项被 diff 17 项整体覆盖 | P 7090 与 P 211,379+；raw vs validated 差集 |
| P2 | 两条 M7 每公司季度序列 29.5k（索引 29%）粒度错配，修订只消费了父引用 | payload `key_evidence_refs.L4.get_m7_capex_cycle#companies` / `L4.get_m7_buyback_flow#per_company` |
| P2 | 权威输出规格与正文示例相隔 20 万字符，仅靠末尾 Response Rules 一句弥合 | P 3592 vs P 211,379 / P 213,576 |
| P2 | 叙事字段 3 处裸字段名（known_data_gaps/why_retained/rejected_critiques），违反本站文风约定 | output.validated.json `revision_summary`、`accepted_critiques[2]` |
| P2 | 黑话 PC-03（1 次）无解释且指向的指令归属不明 | P 7090 附近 |

未发现：D1 越权、A2 时序倒置、C4 过期未标注、复读机输出、编造 evidence_ref（45/45 命中索引）。

## 修复建议

1. **（对应 P1·索引）** 把 `key_evidence_refs` 拆成两档下发：修订对照必需的 `ref → {metric, current_reading, normalized_state, permission_type, mixed_field_authority}`（估算 <15k）；`narrative/reasoning_process/misread_guards/cross_layer_implications` 等叙述字段只发给「读证据做判断」的站。53 条卡的判断力在 critic/risk/thesis 阶段已经消化进草稿和反馈里，reviser 不需要二次消化。
2. **（对应 P1·fact_card）** 直接删除 `fact_card`，或在装配时 diff 去重——它是索引 `current_reading` 的逐字副本，省 10.8k 无损。
3. **（对应 P2·季度序列）** `#companies` / `#per_company` 两条子引用只保留每公司的 latest/ttm 摘要字段与 min/max，原始 `quarters` 数组留原始层，可省 ≈25k。
4. **（对应 P2·claimed_fields 冲突）** 二选一：要么规格认账「会被覆盖」，把正文 Step 5 的填写教学与 PC-03 威胁改为「此字段由代码 diff 装配，模型无需填写」；要么保留模型自报并把 PC-03 定义清楚（核对谁与谁）。现状是双份指令 + 双份劳动 + 一份被丢。
5. **（对应 P2·规格距离）** 在正文「输出格式」示例处加一句与 Response Rules 相同的「形状以末尾规格为准」前向声明（正文对 conflict_ordinal 已有同款前向引用先例，P 2936），成本一句话。
6. **（对应 P2·文风）** 文风约定里点名高频重灾区：「提到输入块时用『已知数据缺口清单』不用 `known_data_gaps`，提到字段时说『保留理由』不用 `why_retained`」；或在装配侧对叙事字段做一次字段名→中文短语的后处理替换。
