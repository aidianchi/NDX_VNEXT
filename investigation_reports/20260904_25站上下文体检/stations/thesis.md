# thesis 上下文体检报告

> 站：thesis（Decision Thesis Builder）。材料：`prompt_audit/thesis/attempt_1.prompt.txt`（298,713 字符）及投影、`output.validated.json`。模型 glm-5.3-flash，attempt=1，无重试。
> 下文 offset 均为 prompt.txt 字符偏移（总长 298,713）。

## 结论

**总体合理，是 25 站里结构最健康的一类**：合约承诺的「只消费 synthesis_packet」属实——Runtime Input 282,485 字符（94.6%）整体就是一个 `synthesis_packet` JSON 对象，没有混入原始层数据，不构成 C1 指令冲突。最重的两个问题都在证据索引内部：①`evidence_index` 独占 152,393 字符（占全 prompt 51%），其中两条 M7 公司级明细（capex 12 季度逐季行 + 回购逐季行）合计 29,486 字符（约 10%），是「预处理该干没干」的逐季 dump（P1）；②关键数值在 layer_summaries / bridge_summaries / conflicts / firewall / evidence_index 五处结构性复读（如实际利率 2.44% 出现 29 次，P2）。输出端闭环全部验证通过：45 个 ref 全部合法、5 条高严重度冲突全保留、序号回填机制按设计运转，E2 未发现「材料缺陷 → 输出缺陷」因果。

## 体检明细

### A. 顺序

**A1 段落编排** — 判定：合理。
结构为：系统约束（offset 33）→ 契约与指令（offset 407–12,864，含角色、证据纪律、竞争假说回应、质量检查）→ Runtime Input（offset 12,865，94.6%）→ 输出字段规格（offset 295,350，98.9%）→ 冲突清单（offset 297,910）→ Response Rules（offset 298,117）。指令全在数据前、输出规格和序号清单贴在末尾（注意力高点），「冲突清单（按序号引用）」紧邻 Response Rules，正是模型填 `conflict_ordinal` 时需要回头查的位置。输出端验证：retained_conflicts 5 条序号 1–5 全部正确（output.validated.json）。无洼地。

**A2 数据时序** — 判定：合理（有一处小观察）。
主体数据是「当前值 + 分位 + 均线关系」快照，不是长时序，无新旧倒置问题。唯一的时序型数据是 M7 公司级逐季行：capex 从 2023Q3 排到最新（旧→新），回购从 2025Q2 排到 2026Q2（旧→新，`latest_period_end: "2026-06-30"` 显式标注最新值，offset 约 26 万区间内）。方向一致且最新值有显式字段，不构成时序陷阱。
小观察：synthesis_packet 有两个生成时间——顶层 `generated_at: 2026-09-02T18:50:31Z`（prompt 行 386）与 `packet_meta.generated_at: 2026-09-02T15:40:04+00:00`（行 390），相差约 3 小时，字段名相同、语义靠猜（见 C4）。

**A3 few-shot 打断** — 判定：合理。
唯一的示例是【反模板】JSON 结构模板（offset 3,496，约 500 字符），位于指令区、数据区之前，只演示字段结构且明言「尖括号内不是可复用文案」。没有把「任务→数据→输出要求」主干切碎。

**A4 重试差异** — 不适用（attempt=1，meta.json `attempts: 1`）。

### B. 体量与冗余

**B1 体量账本** — 判定：P1（单点）+ 结构合理。
前三大段：Runtime Input 282,485（94.6%）、对竞争假说的强制回应 6,108（2.0%）、输出字段规格 2,560（0.9%）。Runtime Input 内部（解析自 prompt 的 JSON）：

| 键 | 字符 | 占全 prompt |
|---|---:|---:|
| evidence_index（93 条） | 152,393 | 51.0% |
| bridge_summaries（1 条 Bridge） | 22,093 | 7.4% |
| layer_summaries（5 层） | 18,035 | 6.0% |
| competing_hypotheses（3 条） | 6,838 | 2.3% |
| 其余 10 键合计 | ~9,100 | ~3% |

evidence_index 作为「所有 evidence_refs 的合法出处」是必要骨架（删掉判断无法落地），中位条目 1,195 字符也克制。**不必要的是其中两条**（见 B3）。

**B2 站内重复** — 判定：P2。
同一数值跨结构复读（按 JSON 路径归桶统计）：
- 实际利率 `2.44`：29 次 = layer_summaries[0]×4 + bridge_summaries×4 + high_severity_conflicts×1 + typed_conflicts×1 + competing_hypotheses×1 + objective_firewall_summary×2 + evidence_index×16
- 集中度 `45.75`：16 次（layer 5 / bridge 5 / conflicts 2 / firewall 1 / index 3）
- CCC-BB `8.97`：14 次；混合 OAS `2.65`：14 次

五层结构（layer card → bridge → conflicts → firewall → index）各有职责，复读部分是设计使然；但同一数字最多 6 处再现、evidence_index 内部还因「分位/均线上下文」再重述 16 次，属于「每层各说一遍带数字的同一句话」。占量不大（layer+bridge+conflicts 合计约 44k），未达 P1。

**B3 粒度错配** — 判定：P1（本站最重的病灶）。
`L4.get_m7_capex_cycle#companies`（14,787 字符）与 `L4.get_m7_buyback_flow#per_company`（14,699 字符）是 7 家公司 × 逐季原始行的 dump：capex 每家 12 个季度（`quarters: {_prompt_summary: true, count: 12, sample: [{calendar_quarter: "2023Q3", ..., "derivation": "discrete_quarter_from_cumulative_ytd_diff", ...}]}`），回购每家 5 个季度，每行约 15 个字段（form/fiscal_year/pit_safe/source 等）。而 thesis 的下游需要的恰是这两条目**已经另给的聚合面**：`#m7_aggregate`（3,722 字符）单独存在，per_company 顶层也有 `ttm_buyback_usd_bn: 82.226`、`latest_quarter_buyback_usd_bn: 25.105` 等摘要字段。同样值得注意的是：索引对成分股明细已有裁剪机制（`constituents._prompt_summary: true, sample: 3 条 + "完整明细保留在 synthesis_packet.json 供审计"`），说明系统知道该裁，唯独逐季公司行没套用同一机制。29.5k 字符（约全 prompt 10%）把「算好 TTM/同比再喂」的活推给了模型注意力。

### C. 质量

**C1 指令冲突** — 判定：未发现。
本站焦点问题：合约说「你现在只消费 synthesis_packet。不要重新分析原始数据」（offset 407），而 Runtime Input 28.2 万字符——经解析，它整体是单个 JSON 对象，顶层键就是 `synthesis_packet`，内含 layer_summaries（每层 9–11 个指标的结构化摘要 + key_evidence）、bridge_summaries、conflicts、evidence_index 等，全部是加工后的摘要级载荷。**合约与内容一致，不构成 C1**。B3 指出的逐季公司行是「摘要包里塞了偏原始的粒度」，属于体量/粒度问题（P1），不是「合约与内容打架」的指令冲突。其余成对检查：「不得编造数字」（系统约束 1–5）vs 输出规格的定量字段——规格只要求形状不强制数值，模型在 `missing_evidence` 里也确实写了「输入未提供，不臆造」（output.price_reflection_map[rates]）；「诚实保留未解决争议」vs「必须给方向」——契约对 kept_unresolved 假说显式允许 absorb_partially（offset ~4,300），无打架。

**C2 死指令** — 判定：未发现（抽查 6 项全活）。
- `hypothesis_responses`：3 条假说（全部 kept_unresolved）→ 输出 3 条回应，ordinal 1–3、verdict 均 absorb_partially、每条带 refs。活。
- `retained_conflicts` 保留全部高严重度冲突：输入冲突清单 5 条（TC_01–TC_05，prompt 行 6730–6734）→ 输出 5 条，ordinal 全对。活。
- 「`hypothesis_id` 由系统按序号回填，不要自己填写」（offset ~4,450）：raw response 中无 `hypothesis_id`、无 `hyp_base_f076e8b18c` 字样，validated 中已回填——机制按设计运转，非死指令。`conflict_id` 同理。
- `time_horizon_views` 三档 / `portfolio_actions` 三桶 / `price_reflection_map` 五类：输出 3/3/5 全覆盖。活。
- ref 纪律「必须来自 evidence_index」：输出 45 个去重 ref，**0 个非法**。活。
- `reader_conclusion.invalidation_items` 输出为空数组——该字段可选（规格未标必填），不算死指令，仅记录。

**C3 黑话词典** — 判定：基本干净，1 个观察项。
系统自造代号清点（出现次数 / 首现是否解释）：
- `mixed_field_authority` ×49：契约首现（offset 682）即给三条完整规则（父 ref 不能支撑强结论 / 必须用 `#FieldName` 子 ref / 子引用必须存在于索引）。解释充分。
- `misread_guards` ×93、`field_authority` ×102：每条 evidence_index 条目自带中文 `canonical_question`（如「大众风险情绪是否处于极端区间？」）和中文 guard 文案（「情绪指标必须被信用、广度和价格确认。」，offset ~87,329 起）。新模型可只凭 prompt 看懂。
- `objective_firewall_summary` ×5：契约首现即解释「检查投资对象、指标发言权、跨层验证和最强反证」（offset ~1,100）。充分。
- 「发言权」×23、「五类」×9：后者在 Step 3（行 320）显式枚举 credit/rates/valuation/technical_panic/liquidity。充分。
- 观察项：evidence_index 条目内 `"material": "supplier"`（×19，首现 offset 174,987）——"material/supplier" 这对枚举全 prompt 无解释，语义（数据材料来自供应商口径？）只能靠猜。因它在结构字段深处、模型无需引用，未造成可观测伤害，列 P2 传染源观察。
- 「门脸」「三明治」「4C」「恒空」等其他站代号：0 命中。

**C4 数据新鲜度** — 判定：P2（标注一致性）。
`data_date: 2026-09-02` 与 run 的 effective_date 一致（meta.json），过期数据有显式旗标（L2 risk_flags 含 `term_structure_reading_stale_by_one_week`，且 context_summary 明言「早于运行时点属正常时点纪律」）。唯一问题：同包两个 `generated_at`（18:50:31Z vs 15:40:04+00:00，prompt 行 386/390）字段同名、差 3 小时、无注释说明谁是权威生成时间。模型未受影响，但审计对账时会踩坑。

### D. 隔离

**D1 越权扫描** — 判定：未发现（干净）。
全 prompt 搜索 `final_adjudication`、`thesis_draft`、`browser_sidecar`、`user_decision_profile`、`golden_pit`、`apparent_cross_layer_signals`、`layer_raw_data`：**全部 0 命中**。thesis 该看到的东西（五层摘要、bridge、冲突、假说、evidence_index）齐备，不该看到的（下游 critic/reviser/final 结论、跨站档案）一个没漏。

### E. 输出闭环

**E1 叙事字段体检** — 判定：优秀。
- **黑话传染**：叙事字段（main_thesis 187 字、payoff_assessment 354 字、reader_conclusion.one_liner 82 字等）无 C3 代号直出。「简式收益差距」「解保险」等词源自输入 bridge/counter_thesis 文本（offset 25,973 / 78,059），非模型生造；按文风约定「生僻术语首次出现给半句解释」的标准，「简式收益差距」未加半句解释，扣半分（P2 级瑕疵，量级很小）。
- **复读机检测**：对 4 个主要叙事字段做最长公共子串检测，与 prompt 的最大重合分别为 10 / 13 / 21 / 20 字符——超 15 的两处均为数值事实短语（「阈值、QQQ put/call持仓1.79」「简式收益差距-1.42%、美国大盘ERP」），是复述数据而非背题。抽 5 句核验通过。
- **簿记语言密度**：数字嵌在因果链里（如 payoff_assessment：「利率（实际利率十年极端且上行、倍数无缓冲可让）……唯一明确使补偿变厚的类别：盈利（30日上修斜率+3.93%…）」），ref/ID/枚举只出现在结构字段。符合文风约定第 2、3 条。
- **长度纪律**：输出规格未对叙事字段设长度限制；实际 82–354 字，无失控。

**E2 因果对** — 未发现成立的因果对。
材料侧最重的缺陷（B3 的 29.5k 逐季 dump）在输出端**没有留下伤痕**：模型只消费了聚合层（valuation_assessment 引「M7回购同比-22%」「可比六家同比+84%」，均可由 `#m7_aggregate` 与 per_company 顶层摘要字段直接得出），未逐季复算、未被细节带偏。唯一可记的弱关联：29.5k 明细若缺失，判断不会变差——反向证明其冗余，但不构成「缺陷→毛病」因果。指令密集区（契约 12.8k 字符 21 条规则）→ 输出端 21 个顶层字段 + 全部纪律条款均合规，说明该模型在此体量下注意力资源充裕。

## 病灶清单（按严重度排序）

| 严重度 | 病灶 | 证据位置 |
|---|---|---|
| P1 | evidence_index 内两条 M7 公司级逐季明细共 29,487 字符（约全 prompt 10%）是逐行 dump，聚合版已单独存在，且同包已有 `_prompt_summary` 裁剪机制却未套用 | `L4.get_m7_capex_cycle#companies`（14,787 字符）、`L4.get_m7_buyback_flow#per_company`（14,699 字符），Runtime Input 内；对照 `#m7_aggregate` 3,722 字符 |
| P2 | 关键数值跨五层结构复读（2.44%×29、45.75×16、8.97×14、2.65×14） | prompt Runtime Input 全段；归桶统计见 B2 |
| P2 | `material: "supplier"` 枚举 ×19 无任何解释，语义靠猜 | prompt offset 174,987 首现 |
| P2 | 同包两个同名 `generated_at` 相差 3 小时、无注释 | prompt 行 386（18:50:31Z）vs 行 390（15:40:04+00:00） |
| P2 | 叙事字段「简式收益差距」未按文风约定给半句解释（源自输入 bridge 文本） | 输出 valuation_assessment / payoff_assessment；输入 offset 25,973 |

## 修复建议

1. **（对应 P1）给 evidence_index 的公司级明细套用 `_prompt_summary` 裁剪**：`#companies` 与 `#per_company` 只保留每家公司顶层摘要字段（TTM、latest_quarter、同比）+ 聚合条目 `#m7_aggregate`，逐季行照 constituents 的先例移出 prompt、留审计文件。预计省约 29k 字符（≈10%），判断不受损（E2 已反向验证）。
2. **（对应 P2 复读）给 evidence_index 条目瘦身数值重述**：条目内只保 field_value + field_authority + 子 ref 清单，分位/均线叙事性重述收敛到 layer_summaries 一处，避免同一数字在索引内再现 16 次。
3. **（对应 P2 枚举）在契约的 evidence 纪律段补一句** `material` 枚举的含义（或直接改用自解释值）；同步在 packet_meta 注明两个 `generated_at` 各自语义（建议改名 `packet_generated_at` / `analysis_packet_generated_at`）。
4. **（对应 P2 文风）文风约定的示例里加一条**：来自上游的口径词（如「简式收益差距」）首次进叙事字段时给半句白话解释。
