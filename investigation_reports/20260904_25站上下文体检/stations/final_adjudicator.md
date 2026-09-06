# final_adjudicator 上下文体检报告

## 结论

整体健康：任务指令前置、输出规格置尾、无越权、数据新鲜、输出叙事质量高（用人话、无黑话直出、几乎不背题）。最重的两个问题都在**重试链路**上：①本站实际跑了两个 invocation（02:02 与 04:05），第一次 attempt_1 因模型输出「完整 JSON 后又开了第二个 JSON」（Extra data）而失败，重试上下文是**整套 20 万字符原样重发 + 仅 1,024 字符反馈**（>99.5% 是重复），失败原因本身与材料质量无直接因果、与「单一巨型 JSON 输出规格」（成功样本 52,600 字符）有间接关系；②`key_evidence_refs` 占 prompt 63%（141k 字符），其中约 27k 是模型用不上的流水线溯源元数据（CIK、pit_safe、逐公司逐季度 dump），另有三层叙述字段互为复读。磁盘上 attempt_1/attempt_2 分别来自两个 invocation，第一次失败的原始响应已被覆盖丢失，只能从重试反馈的引用片段还原。

## 体检明细

### A. 顺序

**A1 段落编排** — 判定：合理
- 结构为「System 纪律(0-409) → 角色定义(409) → 输出格式模板 → 约束(10557) → Runtime Input(12449-218709) → 输出字段规格(218709) → Response Rules」。任务定义在前、权威输出规格在生成点旁边（尾部），符合长上下文的头尾注意力分布。
- 输出形状出现两份：早段「## 输出格式」JSON 模板（offset 4069 附近）与尾段「## 输出字段规格」（218709）。prompt 自带优先级声明「形状冲突时以规格为准」（attempt_2 投影 offset ~182000 处 Response Rules），冲突被文档化兜底，但两份形状确有出入（见 C1）。

**A2 数据时序** — 判定：合理
- 49/53 条证据的 `current_reading` 日期为 2026-08-31/09-01/09-02（如 L1.get_10y2y_spread_bp "+40.0bp（2026-09-01）"），effective_date=2026-09-02，新鲜。
- 个别滞后数据（forward 快照过期 42 天、Top10 权重滞后 19 天）已在 `known_data_gaps` 显式标注，模型输出也如实引用为置信度限制（adjudicator_notes）。未来日期（2026-09-13/09-27、2027-01-25）为财报静默窗/事件日历，非时序倒置。

**A3 few-shot 打断** — 判定：合理（未发现）
- prompt 中 "Example" 出现 0 次、"示例" 1 次；主干未被示例切碎。「【反模板】」（offset 2667）明确声明 JSON 模板只是结构说明。

**A4 重试差异**（本站主菜）— 判定：P1（机制性浪费）+ 一个存疑事实
- **磁盘事实需要先澄清**：attempt_2 文件 mtime 02:02-02:12，早于 attempt_1 的 04:05-04:10；meta.json（04:10）记录 `attempts: 1, retry_feedback: false`。即：磁盘上这两个 attempt 来自**两次不同的 invocation**——第一次 invocation（~02:02）attempt_1 失败、attempt_2 重试成功；第二次 invocation（04:05）全新跑、attempt_1 直接成功并覆盖了 meta/output.validated.json/attempt_1 文件。第一次失败时的 prompt 与原始响应已丢失。
- **重试是「整套重发+反馈」，不是「只补更正」**：attempt_2 的 prompt（201,218 字符）包含完整角色定义 + 完整 Runtime Input（165,081 字符，投影口径），仅在**末尾**追加 1,024 字符反馈块（attempt_2.prompt.txt offset 200194-201218）。重试上下文中 >99.5% 与失败尝试相同的指令+数据被整体重读，新信息占比 0.5%。按 20 万字符估算，重试一次的注意力/成本 ≈ 数万 token 级，全为重复。
- **两盘 prompt 相差的 22,277 字符不是反馈复读**：逐键对比投影，差异几乎全部在 `key_evidence_refs`（attempt_1 139,928 vs attempt_2 117,651，差 22,277），thesis_* 系列各有 ±100-700 字符浮动——这是两次 invocation 上游阶段（thesis/reviser 等 LLM 站）重跑的**非确定性漂移**，不是重试机制多发的内容。重试机制本身多发的只有那 1,024 字符反馈。
- **反馈块质量本身不错**：引用了「JSON 语法错误定位: Extra data（提取出的 JSON 块内第 362 行第 1 列）」、错误位置前后约 200 字符、响应末尾片段，并给出「请仅输出修正后的 JSON 对象」。设计合格，问题只在重发全量。

### B. 体量与冗余

**B1 体量账本**（attempt_1 prompt 222,876 字符；payload JSON 序列化口径 152,965 字符）
- `key_evidence_refs`：prompt 口径 141,053 字符（offset 56336-197389），**占 63%**。53 条证据、平均 1,897 字符/条（payload 口径）。
- 第二梯队：thesis_* 系列合计约 30k（thesis_price_reflection_map 3.6k、thesis_principal_contradiction 3.3k、thesis_reader_conclusion 2.8k 等）；`fact_card` 13,301 字符（prompt offset 197415 起）。
- 指令面合计约 18k（8%）。头部指令 + 尾部规格各 ~3.5k，编排不胖。
- **必要性判断**：证据索引是终审站的核心输入，保留正确；但其内部构成有明显水分（见 B2/B3），估算 40-50k 字符可裁而不伤裁决质量。

**B2 站内重复** — 判定：P1
- **fact_card 与 key_evidence_refs.current_reading 逐字复读**：53 条 fact_card 的 `reading` 字符串与证据索引条目的 `current_reading` 完全相同（例：`"+40.0bp（2026-09-01），未倒挂；10年分位约50.1%、5年分位64.6%；低于MA20（46.75bp）约14.44%，边际趋平。"` 同时出现在 prompt offset 197415 段（fact_card）与 56336 段内（key_evidence_refs）。fact_card 整块 13.3k 字符基本是复读 + authority 标签。它承担「数字菜单」闸门职能（角色定义 offset ~3900：「判决正文与读者面字段里的数字只能选用这张卡……的原值」），是有意冗余，但 13.3k 只为防编数字，性价比可议。
- **同一数字全 prompt 高频重复**：`99.6`（实际利率分位）×23 次、`2.44`×23 次、`1.42`（简式收益差距）×21 次、`84%`（capex 同比）×13 次、`45.75`（Top10 权重）×10 次。分布上 99.6 有 6 次在 key_evidence_refs 区间内（各 L1 条目的 narrative 反复引用同一跨层背景）、17 次在区间外（thesis_*/must_preserve_risks/矛盾清单反复引用）。每条层证据的叙述都携带全套跨层背景数字，是「每条证据都自带全局摘要」式的复读。
- **矛盾三处申报**：`thesis_principal_contradiction`（3.3k）+ `principal_contradictions`（2.4k）+ `high_severity_typed_conflicts`（3.4k）三个键覆盖同一矛盾域；`thesis_reader_conclusion`（2.8k）与输出规格中的 reader_final 又是一对上下游同构。

**B3 粒度错配** — 判定：P1（局部）
- 证据条目内 `field_value` 占 payload key_evidence_refs 的 37%（37,201/100,546 字符），其中两条是纯流水线溯源：`L4.get_m7_buyback_flow#per_company`（13,826 字符）与 `L4.get_m7_capex_cycle#companies`（13,543 字符）——逐公司 dict 含 `cik: '0000320193'`、`pit_safe`、`duplicate_rows_removed: 0`、`coverage_quarters`、逐季度 source 数组。终审模型真正需要的只是「回购同比 -22%、GOOGL/META 归零（第三方回退需打折）、capex 同比 +84%」这几个数；两条合计 27.4k 字符（占 key_evidence_refs 的 ~19%）是预处理该干的活被推给了注意力。缓解因素：模型的 adjudicator_notes 确实消费了其中「无申报日核验的第三方回退」做了打折处理——溯源有一点用，但粒度远超需要。
- 叙述层三重复读：每条证据同时携带 `narrative`（5.3k）、`reasoning_process`（6.6k）、`first_principles_chain`（3.9k，payload 口径），三者是同一推理的三种复述，再加 `misread_guards` 3.8k、`cross_validation_targets` 2.4k、`canonical_question` 1.7k 等层分析师脚手架字段——这些是给层内分析用的，对终审边际价值低。

### C. 质量

**C1 指令冲突** — 判定：P2
- **approval_status 枚举打架**：模板两处（prompt offset 4069、8433）写 `"approved | approved_with_reservations | rejected"`（三值），尾部权威规格（218863）写 `"approved" / "approved_with_reservations" / "needs_revision" / "rejected"`（四值，多 needs_revision）。本 run 输出用了 approved_with_reservations，未踩坑，但四值枚举若被模型选中（如第一次失败响应的第二个 JSON 即写了 "approved"），与角色定义的字面约束存在解释空间。
- **模板与规格形状漂移同族**：早段输出格式模板含 quality_gate/reader_final/price_reflection_map 但**缺** `long_term_assessment`（规格 218709 段有）。有「以规格为准」兜底，仍是漂移源。
- **轻度张力**：「【反模板】不得照抄本文件出现过的短语」（offset 2667）与输入侧 thesis_* 字段本就在「本文件」里、且终审需要承继上游结论——模型实际承继了 40-146 字符的同名段落（见 E1），严格字面上违反反模板，实质是设计默许的承继。建议把反模板的适用范围改成「不得照抄指令性文案，承继输入字段除外」。

**C2 死指令** — 判定：未发现
- 抽查规格 27 个字段，输出全部存在（`spec 有而输出缺失: []`）。`quality_gate` 子对象完整落账、`stance_label` 按枚举输出「偏防守」、`claim_ledger`/`token_usage` 按「可选」为 null（与「不用你输出」一致）。约束类指令也活：「必须注明须经个人投资政策书与再平衡带确认」（offset 12375）在输出 portfolio_actions 中逐字执行。

**C3 黑话词典** — 判定：P2（轻）
- **「报告门脸徽章」**：全文仅 1 次（prompt offset 2175，【姿态标签 stance_label】段：「它是报告门脸徽章直接消费的受控短字段」）。无解释什么是「门脸徽章」——新模型只能靠上下文猜是「报告首屏的姿态标签位」。语义可猜度高、且是受控字段的用途说明，危害有限。列入传染源候选，但本次未传染：输出中「门脸」0 次。
- **synthesis_packet 死引用 ×14**：1 次在指令面（offset 1688：「即 `synthesis_packet.evidence_index` 的子集」——引用一个本次输入里不存在的对象路径），13 次在证据条目 note 字段里反复出现「完整明细保留在 synthesis_packet.json / evidence_registry…」（offset 123062 起共 13 处）。模型无法打开这些文件，纯属管道自言自语。
- 其余系统自造词检查：「三明治」「恒空」「4C」「沙盘」均 0 次；「个人投资政策书/再平衡带」是约束段强制的固定话术，不算传染。通用金融术语为主，黑话密度在 25 站中应属最低档。

**C4 数据新鲜度** — 判定：合理
- 见 A2：核心读数 D-1/D 日，滞后项显式标注在 `known_data_gaps`（prompt 内，模型在 must_preserve_risks 第十条完整转述「forward 快照过期 42 天、Top10 权重快照滞后 19 天」）。未发现字段名暗示「当前」实为旧值的案例。

### D. 隔离

**D1 越权扫描** — 判定：未发现（干净）
- 关键词全 0 命中：`browser_sidecar`、`user_decision_profile`、`golden_pit`、`final_adjudication`（本站自身历史输出）、`thesis_draft`（终审口径声明修订前原稿不入输入，offset ~9100：「修订前原稿只落盘供审计、不在本输入里」）、`apparent_cross_layer_signals`、`layer_raw_data`。
- 本站是层间宪法下的终点消费者，看到 L1-L5 证据、critique、counter_thesis、revision_summary 均属设计内授权。未见个人决策档案类内容。

### E. 输出闭环

**E1 叙事字段体检**（对象：output.validated.json，来自 04:05 invocation 的成功 run）
- **黑话传染**：无。「门脸/三明治/恒空/4C」在输出中 0 次；「闸门」4 次全部落在内部字段（adjudicator_notes「质量闸门通过」「证据闸门逐项核验」、quality_gate.notes、must_preserve_risks 的「IG 稳定是唯一闸门」比喻），reader_final 全系字段干净。
- **复读机检测**（输出与 prompt 最长公共子串）：`reader_final.one_liner` = 0（完全原创）；`payoff_assessment` = 146 字符（「趋势/技术类中性偏负：……大于当前波动读数所示。合计……」，源自 thesis_payoff_assessment，prompt offset 21792）；`must_preserve_risks[0]` = 97 字符（源自输入 must_preserve_risks 同名段）；`three_reasons[0]` = 40 字符（源自 thesis_reader_conclusion）；`reasoned_verdict` = 48 字符（证据 ref 字符串，必然重复）。**判定：全部为同名上下游字段承继，非背题**；五句抽检中唯一面向读者的 one_liner 零重复，读者面是重新写作的。
- **簿记语言密度**：reasoned_verdict 内 ref 以 `[L4.get_xxx]` 形式嵌在因果链句尾，服务可追溯性，非裸列；reader_final 面向读者无 ref。合格。
- **长度纪律**：规格对叙事字段无硬性长度（reasoned_verdict 仅要求「写完整、按条书写，不凑字」）；one_liner 142 字符，三条 three_reasons 各 60-90 字符，守纪律。
- 附带观察：本 run 输出 52,600 字符单行 JSON，27 字段全数落账、validator 0 error——是各站中输出完成度最高的一类。

**E2 因果对**
- **对 1（成立，机制级）**：输出规格要求单次返回 27 字段巨型 JSON（成功样本 52,600 字符；attempt_2 重试样本 26,971 字符）→ 第一次 invocation 的 attempt_1 生成 57,874 字符响应时，在写完一个完整 JSON（361 行，末尾 `"token_usage": null, "claim_ledger": null`）后又开了第二个 JSON（`{"generated_at": "2026-09-03T00:00:00Z", "approval_status": "approved", "final_stance": "主导矛盾是十年极端且边际趋紧的折现率环境…"`），整体解析报 Extra data → 校验失败 → 触发整套 20 万字符重发。【材料证据：attempt_2.prompt.txt offset 200194-201218 反馈块引用；【输出证据：output.validated.json 整体体量 52.6k 佐证输出需求量级】。注意：失败响应原文已丢失（attempt_1 文件被 04:05 重跑覆盖），「长输出诱发重复生成」是从引用片段与输出体量的推断，定案需保留失败原始响应。
- **对 2（成立，成本级）**：重试采用整套重发制 → 修复一个格式错误的边际信息成本 1,024 字符，实付注意力 ~20 万字符（attempt_2.prompt.txt 全长 201,218，其中反馈仅 offset 200194-201218）。属于「材料编排缺陷 → 资源浪费」因果，未伤及输出质量（重试样本 attempt_2 与重跑样本结论一致：均偏防守、approved 系）。
- 其余材料缺陷（B2/B3 冗余、C1 枚举冲突、C3 死引用）在输出端均**未**检出对应毛病——输出叙事干净、判定有据。诚实结论：本站材料的问题主要是花钱，不是说谎。

## 病灶清单（按严重度排序）

| 严重度 | 病灶 | 证据位置 |
|---|---|---|
| P1 | 重试为整套重发：201,218 字符上下文中新信息仅 1,024 字符反馈，>99.5% 重复 | attempt_2.prompt.txt offset 200194-201218 |
| P1 | 输出规格迫使单次 ~5 万字符级 JSON，放大格式失败概率（Extra data），失败即触发全量重发 | attempt_2.prompt.txt offset 200194 反馈块；output.validated.json 52.6k |
| P1 | key_evidence_refs 内 27.4k 字符逐公司溯源元数据（cik/pit_safe/逐季度 dump）超出终审所需粒度 | prompt offset 56336-197389 区间内 L4.get_m7_buyback_flow#per_company / L4.get_m7_capex_cycle#companies |
| P1 | fact_card（13.3k）与 53 条证据的 current_reading 逐字复读；同一数字全 prompt 复读 10-23 次 | prompt offset 197415+ vs 56336+；「99.6」×23、「2.44」×23 |
| P1 | 每条证据 narrative/reasoning_process/first_principles_chain 三重复述 + 层内脚手架字段（misread_guards 等）约 20k+ | payload key_evidence_refs 字段构成统计 |
| P2 | approval_status 枚举两处三值 vs 规格四值（needs_revision） | prompt offset 4069、8433 vs 218863 |
| P2 | 输出模板与规格形状漂移（模板缺 long_term_assessment） | prompt offset 4069-10000 vs 218709+ |
| P2 | 「报告门脸徽章」黑话无解释（1 次，未传染输出） | prompt offset 2175 |
| P2 | synthesis_packet 死引用 14 次（指令面 1 + 证据 note 13），指向模型打不开的文件 | prompt offset 1688、123062 起 13 处 |
| P2 | 反模板「不得照抄本文件短语」与输入字段承继的设计默许相抵触 | prompt offset 2667 vs 输出 payoff_assessment 146 字符承继 |
| 存疑 | 磁盘 attempt_1/attempt_2 分属两个 invocation，失败原始响应被覆盖丢失，A4 对比基于重试反馈引用与上游漂移数据 | meta.json（attempts:1）；文件 mtime 02:02 vs 04:05 |

## 修复建议

1. **重试改增量上下文**（对病灶 1）：格式校验失败类重试不值得重发 20 万字符。保留原 prompt 的结构引用（或缓存 prefix），重试消息只带「输出规格摘要 + 失败定位 + 反馈」；或至少把反馈块从尾部 1k 扩为「错误类型 + 需要重做的字段清单」，让重试输出对齐（本次重试输出 27k 字符、缺 1 字段，与全量样本 52.6k 差一倍，疑似重试时模型简化了产出）。
2. **给巨型输出减压**（对病灶 2）：把 must_preserve_risks/invalidation_items/invalidation_conditions 这类三处近重复的输出字段合并去重，或将 price_reflection_map、secondary_contradictions 等重叙述字段降为「有变化才写」；目标把单响应压回 ~30k 字符以内，直接降低 Extra data / 截断类失败率。
3. **证据索引瘦身**（对病灶 3/5）：`field_value` 中的逐公司溯源（cik、pit_safe、duplicate_rows_removed、逐季度 source 数组）在装配层预消化成一行「数据质量标记」（如 `quality_flag: third_party_fallback_needs_discount`）；narrative/reasoning_process/first_principles_chain 三选一保留（建议 narrative+chain），层内脚手架字段（canonical_question、cross_validation_targets、core_vs_tactical_boundary）对终审站剔除。预估可砍 key_evidence_refs 的 30-40%。
4. **fact_card 去重**（对病灶 4）：fact_card 只保留 ref + authority（reading 指向证据索引条目即可），或反过来让证据索引条目内联 authority、删掉 fact_card；数字闸门职能不因去重失效。
5. **枚举与模板对齐**（对病灶 6/7）：approval_status 枚举以规格四值为唯一口径，同步修改角色定义两处；输出格式模板改为引用「见尾部规格」或由同一代码生成，杜绝双源。
6. **黑话与死引用清理**（对病灶 8/9）：「报告门脸徽章」改为「报告首屏姿态标签（brief 首屏徽章）」；synthesis_packet.json 的 note 改为面向模型有意义的措辞（如「明细已截断，仅用当前读数」），删除模型无法访问的文件名引用。
7. **审计链路保全**（对存疑项）：失败 attempt 的 prompt/raw 不应被后续重跑覆盖——按 invocation 分目录落盘，否则 A4 类体检和线上排障都只能靠引用片段还原。
