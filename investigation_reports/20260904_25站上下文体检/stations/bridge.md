# bridge 上下文体检报告

> 站：bridge（跨层桥）· run：t70_glm_check_20260902 · 2026-09-04
> 材料：attempt_1.prompt.txt（154,242 字符）· 投影保留率 96.7% · 输出 output.validated.json（45,506 字节，存在）
> offset 说明：`@N` = 原文字符偏移；`投影:L` = 投影行号。evidence_ref 在原文出现 72 次（指令区 16 / Runtime 46 / 规格区 10）。

## 结论

总体编排合理：任务定义与纪律在前、五张 layer card 居中、输出规格收尾，隔离干净（D1 零命中），输出端形状全合规、叙事质量高。两个 P1 病灶：①「事件纪律（三明治口径，恒空）」段标题黑话无解释，且已被模型原样回抄进输出的 normalization_notes——C3 定罪成立；但该指令本身**不是**死指令（它防住了编造事件，event_refs=[] 且无假事件 ID），C2 赦免。②五张 card 全文搬运整体必要，但卡内三层复读（core_facts→hooks→indicator_analyses→synthesis）使同一事实在单卡最多出现 9 次，估计 2-3 万字符为复读。

## 体检明细

### A. 顺序

**A1 段落编排** — 判定：合理（附 1 个 P2）
指令区 0-11,328（7.3%）：System 约束 → Bridge Contract → 事件纪律 → 角色/流程/约束/质检 → 三个场景示例。Runtime 数据 11,328-151,194（90.7%）。输出字段规格 @151,194 + Response Rules @153,726 收尾（2.0%）。任务定义和纪律在头部，输出规格紧贴生成点（末尾），数据虽处中段"注意力洼地"，但它就是本站的原材料，且关键纪律（升格纪律、必须遵守清单）都在数据之前完整给出——编排无指令被埋没。
P2：输出形状被描述了 4 遍——Contract 散文（@~600）、输出格式 JSON 骨架（@3,170 起，2,328 字符）、三个场景示例（2,147 字符）、输出字段规格（@151,194，2,532 字符）。骨架与规格形状有出入（骨架 conflicts 无 conflict_id/conflict_ordinal，无 typed_conflicts/resonance_chains/transmission_paths），靠 Response Rules「形状冲突时以规格为准」（投影:3681）兜底。

**A2 数据时序** — 判定：合理
各 raw_data 均带 date/effective_date：如 10Y-2Y `2026-09-01`（投影:543）、Fed Funds `2026-08-01`（投影:562）、M2 `2026-07-01`（投影:602）。context_brief.data_summary 明示「早于运行时点属正常时点纪律」（投影:481）。L5 quality_self_check 主动声明「基于2026-09-01收盘的确定性快照，运行时点2026-09-02盘中可能出现新信息」（投影:3649）。无过期数据冒充当前状态。

**A3 few-shot 打断** — 判定：合理（附 1 个 P2）
三个场景示例位于指令区尾部（投影:356-474），Runtime 数据之前，未把「任务定义→数据→输出要求」主干切碎。P2：示例是旧 schema——conflicts 无 evidence_refs/conflict_id，无 v2/v3 字段；与规格有三处形状不一致，模型需靠「以规格为准」自行调和。

**A4 重试差异** — 不适用。meta.json 显示 attempts:1，无重试。

### B. 体量与冗余

**B1 体量账本** — 判定：结构合理，卡内有水分
| 区块 | 字符 | 占比 |
|---|---|---|
| 指令区（0→Runtime） | 11,328 | 7.3% |
| Runtime Input（五卡+brief+hooks） | 139,866 | 90.7% |
| 输出规格+Response Rules | 3,048 | 2.0% |

五卡分段：L1 28,337 / L2 30,586 / L3 20,776 / L4 30,839 / L5 27,817。必要性判定：Bridge 的职责就是「读取各 LayerCard 的 indicator_analyses、layer_synthesis、internal_conflict_analysis 和 cross_layer_hooks」（投影:57），indicator_analyses 区（每卡 11.6K-21.2K，含 reasoning_process / cross_layer_implications / evidence_refs / falsifiers）是跨层判断的直接生产资料，删掉判断会变差——**五卡全文搬运本身必要**，不是 B1 病灶。真正的水分在卡内复读（见 B2），估计可省 2-3 万字符而不损失任何事实。

**B2 站内重复** — 判定：P1，卡内三层复读
同一事实在**同一张卡**的 core_facts、cross_layer_hooks、indicator_analyses、layer_synthesis、internal_conflict_analysis 五个层级反复出现。典型证据——L3 的 QQQ Top10 权重 45.75% 在 prompt 出现 **9 次**：core_facts value @72,892 + raw_data @73,171 → hooks conclusion @76,190 + hooks question @77,119 → indicator_analyses 三处 @84,107 / @84,558 / @84,898（current_reading、reasoning_process、first_principles_chain）→ layer_synthesis @89,609 → internal_conflict_analysis @90,455。同类：707.64 ×10、30.02 ×13、734.58 ×4。core_facts 区（每卡 6.0K-7.4K）与 indicator_analyses 的 current_reading 数值高度重叠，raw_data 的明细 dict 是 indicator_analyses 已消化数据的二次搬运。

**B3 粒度错配** — 判定：未发现
抽查 L1 全部 core_facts.raw_data：均为 ~10-14 字段的预加工摘要（level/ma20/percentile_10y/z_score/trend_note，投影:534-544 等），无几十行同构序列逐行 dump。上游已把 min/max/分位/变化率算好（如 Fed Funds 的 min_1y/max_1y/mean_1y，投影:558-560），预处理没有推给模型注意力。投影中 26 处「省略」标记对应的是 layer_synthesis 等长散文中段，非行情序列。

### C. 质量

**C1 指令冲突** — 判定：2 对，1 对已被模型调和、1 对存疑
① supporting_facts 两处口径打架：Contract @740「supporting_facts 只能填写 evidence ref 字符串……不要写中文事实句、数值解释或自然语言」 vs 输出格式骨架 @3,192「"supporting_facts": ["<来自 Layer Cards 的事实>"]」。后者按字面邀请写自然语言。模型实际按契约执行（输出 normalization_notes[1] 明示「按Bridge v2契约仅填evidence ref字符串」；全量核验 21 条 supporting_facts 含中文 0 条），本轮无害但冲突真实存在。
② 姿态纪律 vs 上游暗示：prompt 正文「不得为了满足格式把弱张力升格为 high……严重度必须由证据决定」（投影:267-268）vs context_brief.special_attention「检查高严重度冲突是否被完整保留」（投影:486）。后者在没有任何高严重度冲突上下文的情况下预设其存在，是上游塞给 bridge 的先验，与「证据决定严重度」相抵触。输出 typed_conflicts severity = [high, medium, medium, medium, low]——无法确证 high 是否受此暗示（**存疑**：需要无 special_attention 的对照 run 才能定）。

**C2 死指令** — 判定：事件纪律段赦免；event_refs 字段级恒空属系统级死重
「事件纪律」段（@1,878，全文 114 字符）：「本轮输入不包含任何事件材料；BridgeMemo.event_refs 由系统装配为空列表 []，无需输出。不得自行引入事件 ID，也不得把事件写成 evidence_ref。」核验输出：event_refs=[]，无任何事件 ID，normalization_notes[0] 明示遵守。该指令**成功防住了幻觉事件注入**，是活指令。但另有结构问题：输出规格把 event_refs 列为合法可选字段（原文行 3,569）且 Response Rules 顶层字段清单包含它（行 3,575）——既然所有输入站永远不给事件材料，下游规格与每轮输出仍为恒空字段保留位置，字段级死重属实，属契约层问题而非本站执行问题。其余抽查：typed_conflicts（5 条）、resonance_chains（3 条）、price_reflection_map（5 类全覆盖）、principal_contradiction（11 键全填）均产出且形状合规——活。

**C3 黑话词典** — 判定：1 个确认传染源 + 3 个低危代号
- 「三明治口径」：1 次，@1,878 段标题，**全文无任何解释**。新模型无法从 prompt 知道它指什么（跨站统一装配口径？）。**确认传染源**：output.validated.json 的 normalization_notes[0] 原样回抄「事件纪律（三明治口径）：本轮无事件材料输入，event_refs恒为空列表」——黑话已进入输出物。
- 「恒空」：1 次，@1,878 标题。且与正文矛盾：标题说「恒」（跨 run 恒定），正文说「本轮输入不包含」——若事件管线未来上线，「恒空」即失效，措辞不准。
- 「Mao Thought 主链」：1 次，Step 5 标题（投影:305）。内部方法论代号，正文「抓主要矛盾」解释充分，标题黑话冗余但正文可救。
- 「Schema Guard」：1 次（投影:274），功能可由「否则会判为过度升格」推断，低危。
- 运行时数据里的「O10纪律」（L5 notes，投影:3,653）来自上游 layer card，非本站 prompt 自造，登记备查。

**C4 数据新鲜度** — 判定：合理
最旧数据 M2 2026-07-01 带 trend_note 说明（投影:603）；L4 明示「A/D与McClellan最新合格日为2026-08-28……存在1个交易日错位」（投影:2,297）；L4 修正指标「自产档案口径约6.2% vs 供应商口径约4.0%」分歧已标注（投影:2,923）。无字段名暗示"当前"而值是旧的情形。

### D. 隔离

**D1 越权扫描** — 判定：干净
搜 `final_adjudication` / `thesis_draft` / `browser_sidecar` / `user_decision_profile` / `golden_pit` / `revised_thesis` / `final_thesis`：**全部 0 命中**。`apparent_cross_layer_signals` 在 context_brief 出现但为空列表（投影:483），且该字段本就是 bridge 职责范围内的输入而非越权。五张 layer card 是 bridge 的法定输入，不算越权。未发现任何下游结论、个人档案或其他站产物泄入。

### E. 输出闭环

**E1 叙事字段体检**
- **黑话传染**：命中 1 处——normalization_notes[0] 回抄「三明治口径」「恒为空」（见 C3）。该字段是簿记/审计记录而非读者散文，严重度受此缓解，但黑话确实穿过输出端。
- **复读机检测**：135 个叙事字段中 27 个含 ≥15 连续字符与 prompt 逐字重合。核验最长 8 例：32 字「对冲拥挤（SKEW≈149、QQQ put/call 1.79）」、30 字「OBV 20日净流出约1.33亿股、CMF -0.0899、」等，来源**全部是 layer card 的数据句**（L2 synthesis、L5 indicator_analyses），属数据短语搬运，非指令背诵。未发现背题。
- **簿记语言密度**：叙事字段把数字嵌在因果链里。如 why_principal：「约束端（L1实际利率99.6分位、L4负收益差距、L2尾部信用100分位）封顶向上空间并抽走向下缓冲」——ref 落在因果链里服务判断，非裸列。ref/ID 均住在结构字段。合格。
- **长度纪律**：输出规格对叙事字段无长度要求；实际输出（implication_for_ndx 约 380 字）偏长但信息密度高，无违规可判。

**E2 因果对**
- **成对 1**：材料——段标题黑话「## 事件纪律（三明治口径，恒空）」@1,878 无解释 → 输出——normalization_notes[0] 原样回抄该黑话。唯一的实锤「材料缺陷 → 输出毛病」链。
- **不成对（存疑）**：special_attention「检查高严重度冲突是否被完整保留」→ 输出含 1 个 high typed_conflict。无法证明因果，需对照实验。
- **未成病**：supporting_facts 语义冲突 → 模型自行调和成功（0 条中文事实句），未兑现为输出毛病。

## 病灶清单（按严重度排序）

| 严重度 | 病灶 | 证据位置 |
|---|---|---|
| P1 | 段标题黑话「三明治口径/恒空」无解释，且被模型原样回抄进输出 normalization_notes | prompt @1,878；output.validated.json normalization_notes[0] |
| P1 | 卡内三层复读：同一事实在单卡最多出现 9 次（45.75），五卡估 2-3 万字符复读 | @72,892 / @76,190 / @84,107 / @89,609 / @90,455 等 |
| P2 | context_brief.special_attention 预设高严重度冲突存在，与「严重度由证据决定、不得升格」纪律相抵触 | 投影:486 vs 投影:267-268 |
| P2 | supporting_facts 两处口径冲突：契约「只能 ref」vs 输出骨架「来自 Layer Cards 的事实」 | @740 vs @3,192 |
| P2 | 输出形状 4 处描述（契约/骨架/场景示例/规格），示例与骨架是旧 schema，靠兜底规则调和 | @~600 / @3,170 / 投影:356-474 / @151,194 |
| P2 | event_refs 恒空字段仍占输出规格与 Response Rules 位置，每轮产出 [] | 原文行 3,569 / 3,575 |

## 修复建议

1. **（P1→黑话）** 改 `## 事件纪律（三明治口径，恒空）` 标题为自解释文案，如 `## 事件纪律（本轮无事件输入）`；若「三明治口径」是跨站装配术语，在首次出现处补半句解释（「三明治口径：event 字段由系统在 sandwich 层统一装配，各分析站不自行填写」）。同时统一「恒空」vs「本轮」措辞。
2. **（P1→卡内复读）** 装配 bridge 输入时去重：core_facts 保留，cross_layer_hooks / indicator_analyses 中的同数值语句改为引用式短语（如「见 core_facts.45.75」）或仅保留增量语义；layer_synthesis / internal_conflict_analysis 是模型产出而非数据，可保留。目标省 15-20% Runtime 字符。
3. **（P2→special_attention）** 该字段仅在确有高严重度冲突待保留时注入，并改写为中性句式（「若输入中存在 high 冲突，验证其是否被完整映射」），避免在空证据时预设结论。
4. **（P2→supporting_facts）** 删除输出格式骨架里的 `<来自 Layer Cards 的事实>` 占位，改为 `<evidence ref 字符串，如 "L4.get_ndx_pe_and_earnings_yield">`，与契约对齐。
5. **（P2→形状四处描述）** 输出格式骨架与场景示例升级到 v3 schema，或干脆只留「输出字段规格」一处权威描述 + 一个 v3 全字段示例，砍掉旧骨架。
6. **（P2→event_refs）** 若事件管线短期内不会上线，从输出规格与 Response Rules 顶层字段清单中移除 event_refs，改为系统装配层静默补 []；上线时再加回。
