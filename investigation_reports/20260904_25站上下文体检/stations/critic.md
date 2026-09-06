# critic 上下文体检报告

> 站：critic（审查 thesis 草稿）。材料：`prompt_audit/critic/attempt_1.prompt.txt`（368,407 字符）；对照：`prompt_audit/thesis/attempt_1.prompt.txt`（298,713 字符）。offset 均指 prompt.txt 字符偏移。

## 结论

编排合格、证据选择精准、输出扎实闭环：critic 拿到的 53 条 key_evidence_refs 完整覆盖了支撑链/冲突/价格反映地图引用的全部 33+ 个 ref，六类攻击重点全部可执行且输出逐项兑现。最重的 1 个病灶是 P1 级体量浪费：4 条 L4 证据被逐成分股展开成 139K 字符（占全 prompt 38.5%），其中相对 thesis 版本的 +105K 增量（96/102 只成分股逐行 dump）在输出中**零消费**。多出的 7 万字符不是"额外上游材料"，而是同一批证据从"摘要版"换成了"逐成分展开版"。

## 多出来的 7 万是什么（B1/B2 主菜）

两站 runtime JSON 实测（解析 prompt 内 JSON 逐键统计，非投影估算）：

| | critic (361,712) | thesis (282,466) |
|---|---|---|
| 证据明细 | key_evidence_refs **286,989**（79.3%） | evidence_index **188,771**（63.2%） |
| 上游综合 | thesis_* 正文全套 + counter_thesis_hypotheses（各 ≤4K） | bridge_summaries 27,925 + layer_summaries 19,195 + competing_hypotheses 7,728 |

关键事实：critic 的 53 条 key_evidence_refs 是 thesis 的 93 条 evidence_index 的**子集**（键 100% 重叠），但同键内容更大——53 条合计 critic 204,090 vs thesis 98,721（紧凑序列化），**增量 +105,369**，几乎全部来自 4 条 L4 条目从"抽样摘要版"换成"逐成分全量版"：

| 条目 | critic | thesis | 增量 | 展开内容 |
|---|---|---|---|---|
| `#slope_30d` | 57,554 | 5,017 | +52,537 | 96 行 constituents + 10 条 flagged（offset 253,182 起） |
| `#companies` (capex) | 32,775 | 14,787 | +17,988 | 7 家 × 40 季逐行（offset 133,944 起） |
| `#per_company` (buyback) | 25,352 | 14,699 | +10,653 | 每家 12 季 quarters 数组（offset 91,770 起） |
| `#breadth_30d` | 23,772 | 3,399 | +20,373 | 两口径 × 102 只成分股逐行（offset 202,922 起） |

净账：+105K（4 条展开）− 90K（thesis 独有的 40 条较小证据条目）− 55K（bridge/layer summaries 等被拿走）+ critic 独有的 thesis_* 正文与冲突/反方材料 ≈ **+69.7K**，即题目里的 7 万。

**必要弹药还是稀释？** 判定为稀释（P1）：
- critic 的实际证据核查全部落在摘要层：major 发现引用的是 Wind 快照绝对值（PE 30.02/PB 9.15）与 known_data_gaps（offset 361,097）声明，minor 发现引用的两口径读数（0y 60.7% / +1y 41.9%）在 **thesis 版 3,399 字符的摘要里就有**（`"value": {"0y": 60.747075, "+1y": 41.903099"}`）——不需要展开版。
- 逐成分明细零消费：输出全文不含 slope_30d flagged 名单里任何一只票（AVGO/SNDK/WDC/MNST/SNPS 等 10 只均未出现），也未引用任何成分股行。139K（38.5% of prompt）里被用到的只有聚合值、flagged 权重百分比和 periods 汇总——这些 thesis 版摘要同样具备。
- 证据**选择**本身精准：支撑链 4 条 + 冲突 4 条 + 价格反映地图 5 类引用的全部 33+ 个 ref 都在 53 条内（逐一比对，缺失为空）。问题只在 4 条的展开粒度，不在覆盖面。

## 体检明细

### A. 顺序

- **A1 段落编排** — 合理。指令块仅 6,103 字符（1.7%）且完整置顶：角色定义（offset 593 起）→ 输入说明（1,711）→ 输出格式 → 字段长度纪律 → 六类攻击重点（offset 2,716 起，91–540 字符/类）→ 攻击策略 → 3 个攻击示例（4,470–5,600）→ Runtime Input（6,103–367,834）→ 输出字段规格（367,834）+ Response Rules 收尾。无"任务定义被埋进数据"的洼地；few-shot 示例放在指令块尾部、数据之前，未切断主干。
- **A1 六类攻击重点可执行性** — 合理且全部兑现。每类都指名可核查的输入字段：攻击 2 指向 `thesis_key_support_chains` vs `key_evidence_refs`（两者均在输入）；攻击 3/策略 3 指向 `retained_conflict_types` 并明确"正文未提供的解释不是你的检查项"（offset ~4,570，防幻觉条款，好设计）；攻击 6 指向 `payoff_assessment` vs `thesis_price_reflection_map`。输出对照：major 分位缺口即攻击 2 的产物，overall_assessment 的方向一致性核查即攻击 6 的产物。
- **A2 数据时序** — 合理。长序列统一旧→新升序（如 AMZN quarters 2023Q1→2024Q4），最新值在尾部但有 `latest_calendar_quarter`/`latest_period_end` 标头字段，无需扫数组即可定位。
- **A3 few-shot 打断** — 未发现（见 A1）。
- **A4 重试差异** — 不适用（单 attempt 站）。

### B. 体量与冗余

- **B1 体量账本** — key_evidence_refs 79.3% 一家独大，其余 43 个键合计 <11%，无单键超 4K。53 条证据对"逐条核查 evidence_refs 解读"这活是必要弹药（删掉任何一条，对应的核查就落空）；但 4 条的逐成分展开（139K，38.5%）删掉后判断不会变差——见上节。**P1**。
- **B2 站内重复** — 基本干净。thesis 正文段与 key_evidence_refs 的数值重叠（如 2.44% 实际利率同时出现在 thesis_environment 与 L1 条目）属"论点 + 证据本"的必要配对，非复读。真正的重复在**跨站层**：critic 与 thesis 拿到同一批证据的两个版本（见上表），且 critic 版对 4 条做了反向降采样劣化——thesis 拿摘要、critic 拿全量，两版不一致本身是维护隐患。16 个空模板字段（`critique_overall=null`、`layer_summaries=[]`、`pricing_expectation_ledger={}` 等）暴露 governance_input 复用了上游站模板，占位无信息。**P2**。
- **B3 粒度错配** — 命中，即本站最重病灶：4 条 L4 条目的 96/102 行逐成分 dump 是"预处理该干的活"原样推给了模型注意力，而模型的行为证明它只消费聚合层。**P1**。

### C. 质量

- **C1 指令冲突** — 未发现实质冲突。核对过的高危对：核心原则"不设问题数量下限" vs 质量检查"至少检查一次过度谨慎/赔率风险"（检查义务 ≠ 报告数量，不打架）；"aggressively 攻击" vs "编造问题与放过问题同样是失职"（双向对齐，显式自洽）；系统约束"evidence_refs 须来自输入" vs 输出规格（输出本无 evidence_refs 字段，约束作用于叙事引用，边界清楚）。
- **C2 死指令** — 输出规格 4 个必填/可选字段（overall_assessment/issues/cross_layer_issues/revision_direction）在 output.validated.json 中全部存在且被下游消费（reviser 站输入）。抽查通过，无死指令。反向问题在输入侧：16 个恒空占位键（见 B2）。
- **C3 黑话词典** — 指令块自造词均有解释：`governance_input`（输入节列了 17 个字段语义）、`objective_firewall_summary（客观性防火墙摘要）`、`Decision Semantics`（策略 5 逐字段解释）、TC_01–TC_05（high_severity_typed_conflicts 内有 conflict_id + mechanism + implication 全文，offset 31,780 起）。**传染源 2 个，都在上游数据散文里**：①"法典"——9 次（首现 offset 58,312，L2 证据正文"按法典它不能单独证明股市下跌"），无任何解释；②"core_facts 的 magnitude 标签"（offset 362,345，known_data_gaps 内），无解释。两者模型均未带进输出（"法典"在输出中出现 0 次），实际伤害未发生。**P2**。
- **C4 数据新鲜度** — 良好。数据日期覆盖至 2026-09-13（运行时点 2026-09-02 之后的价格触发位），无过期数据冒充当前。缺口全部显式标注：Top10 快照滞后 19 天、forward PE 快照过期 42 天、CFTC/FINRA SSL 失败留边界（known_data_gaps，offset 361,097 起）。存疑一处：AMZN 回购 quarters 数组 12 行全 0.0 且止于 2024Q4，内含重复行（'2024Q1' 连续出现两次，offset ~113K 附近），虽有 `stale_reason` 字段兜底，但全 0 + 重复行 + 20 个月跨度值得上游数据端自查。**P2（存疑）**。

### D. 隔离

- **D1 越权扫描** — 干净。`final_adjudication`/`browser_sidecar`/`user_decision_profile`/`golden_pit`/`apparent_cross_layer_signals`/其他层 layer card 路径全部 0 命中。`counter_thesis` 3 次命中均为本站设计内输入（角色说明 + counter_thesis_hypotheses 数据，offset 364,419）；"bridge" 3 次命中为上游冲突正文引用与 synthesis_guidance 约束文本，非越权。thesis 草稿正文是本站法定输入，不构成越权。

### E. 输出闭环

- **E1 叙事字段体检** — 总体优质。复读机检测：抽 5 句核验，4 句在 prompt 中无 ≥15 字连续同文（模型在作答非背题）；唯一命中的"按法典它不能单独证明股市下跌"是 critic **有意引用**上游冲突正文作核查依据，属正当引用。长度纪律：overall_assessment 无上限约束，实际 ~1,400 字符且信息密度成立；revision_direction 约定"点到为止"，实际 ~830 字符、按优先级列 6 条，踩线但在"不失真"的豁免内。两处瑕疵：①叙事散文里字段名/编号密度偏高——`payoff_assessment`、`breadth_30d`、`TC_01/02/04`、`price_reflection_map.rates` 直接进 issue 正文，与自家"叙事字段文风约定"（"字段名、编号这类内部簿记语言不进叙事字段"）相抵；考虑到声明读者是 Reviser、TC 编号可在输入中解析，判 P2。②`target` 属结构字段应保持机器形状，但实际出现 `"thesis_valuation（波及 thesis_price_reflection_map.rates 与 TC_01）"` 这类中文注解混入，形状污染。**P2**。
- **E2 因果对** — 材料缺陷 → 输出毛病只连成一对弱因果：**B3 逐成分展开 139K（材料，offset 253,182 等 4 处）→ 输出零引用（output.validated.json 全文无 flagged 名单内任何 ticker）**——没造成输出错误，代价是 token 与注意力预算。反方向的正因果更显著：known_data_gaps 的分位缺口声明（offset 362,307）+ Wind 快照绝对值 → critic 抓出 thesis_valuation 引用无源分位的 major，说明"证据本 + 数据缺口声明"这套材料设计按预期生效。其余（空模板字段、法典黑话）在输出端无可见毛病。

## 病灶清单

| 严重度 | 病灶 | 证据位置 |
|---|---|---|
| P1 | 4 条 L4 证据逐成分股展开 139K（38.5% of prompt），相对 thesis 摘要版 +105K 增量在输出中零消费 | prompt.txt offset 91,770 / 133,944 / 202,922 / 253,182；output.validated.json 无 AVGO/SNDK/WDC 等任何成分股行 |
| P2 | governance_input 复用上游模板，16 个恒空占位键随 prompt 下发 | offset ~31,702 起（critique_overall/layer_summaries/fact_card 等，实测全空） |
| P2 | 上游散文黑话"法典"（9 次）"core_facts magnitude"无解释， prompt 内无释义（输出未传染） | offset 58,312 / 362,345 |
| P2 | 叙事散文字段名/TC 编号密度违反自家文风约定；target 结构字段混入中文注解 | output.validated.json issues[0].target、issues[0].issue 等 |
| P2 | AMZN 回购 quarters 12 行全 0、止于 2024Q4、含重复行（有 stale_reason 兜底，上游数据端存疑） | offset ~113,000 附近；quarters 尾部 '2024Q1' ×2 |

## 修复建议

1. **（对 P1）给 key_evidence_refs 设粒度上限**：4 条大条目改为"聚合值 + flagged 前若干条 + coverage 摘要"的摘要版（thesis 版即现成模板，3–15K 足够），逐成分行留 payload.json 按需查。预计省 ~120K 字符（约 prompt 的 1/3），critic 的核查能力不受损——本次输出已证明它只消费聚合层。同时消除两站同证据两版本的不一致维护面。
2. **（对 P2 空字段）** 构建 governance_input 时丢弃恒空键，或加一行"以下字段本站不适用：…"，别把 16 个空槽发给模型。
3. **（对 C3）** 在 known_data_gaps 或输入说明加一行黑话注："法典 = 层间证据纪律/冲突登记规则"（按系统实际定义）；"core_facts" 改为直述字段路径。
4. **（对 E1）** 输出校验器对 `target` 字段加形状检查（只允许字段路径/索引表达式，注解移入 issue 正文首句）；文风约定里补一句"TC_xx 编号首次出现时附冲突短名"。
5. **（对 C4 存疑项）** 上游 m7_buyback_flow 数据端核查 AMZN 序列：重复行去重、确认 2025 年后无申报是真实无回购还是抓取停止，把 stale_reason 写明到期时间。
