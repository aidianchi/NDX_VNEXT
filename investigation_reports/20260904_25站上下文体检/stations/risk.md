# risk（风险哨兵）上下文体检报告

> 站：`prompt_audit/risk/attempt_1`；prompt 原文 358,652 字符（投影头部标注）。
> 证据标注约定：`投影 L行号` = `context_spread/projected/risk/attempt_1.projection.md` 行号；`payload 路径` = `attempt_1.payload.json` 内 JSON 路径；字符量除注明外均为 payload compact JSON 口径。

## 结论

**总体健康，病灶集中在材料端体量，不在指令端。** 指令区仅占 2.1% 且首尾规整、无越权、数据新鲜、输出质量高；最重的两个问题：① 与 critic 各自重运了 84% 逐字节相同的证据主菜（含四张逐股 dump 全部双运，B2 跨站坐实）；② 21 万字符证据包中 58.7% 是 4 张逐股 dump，而 risk 检查清单只消费聚合值（B3）。另发现 3 个输出字段下游零消费的半死指令和 6 条 `[M1]` 元问题混入导致的叙事污染（E2 有因果对）。

## 体检明细

### A. 顺序

**A1 段落编排** — 判定：合理（P2 备注）
- 指令区 7,516 字符（2.1%）全部在头部（投影 L8-L303）：角色定义 → 输入说明 → 输出格式示例 → 检查清单 → 关键约束 → 质量检查，主干完整。
- 权威「输出字段规格（形状以此为准）」+「Response Rules」放在 35.1 万字符 Runtime Input **之后**（投影 L7387 起，prompt 最末 812 字符）——生成点邻接规格，属合理设计；数据是结构化 JSON 而非散文，中段注意力洼地风险低于长文材料。
- **P2 备注（双规格分裂）**：头部「输出格式」示例 `boundary_status` 仅 5 键（投影 L101-L107），检查清单列 7 条边界（L182-L189），尾部规格又说「键自由」。三处口径不一，本次输出给了 7 键未受损，但形状裁决链（「形状冲突时以规格为准」，L7387 区）要求模型自行调和三处。

**A2 数据时序** — 判定：合理
- 证据卡为「读数卡」形态（`current_reading` + 读数日期 + 分位 + narrative），如 VIX 卡：「16.34（2026-09-01），10年分位约44.9%」（payload `governance_input.key_evidence_refs.L2.get_vix`）。无长时序序列，未发现时序倒置或过期段冒充当前。

**A3 few-shot 打断** — 判定：合理
- 唯一示例「风险边界评估示例」位于指令区末尾、Runtime Input 之前（投影 L281-L303），未把「任务定义 → 数据 → 输出要求」切成碎片。

**A4 重试差异** — N/A（risk 仅 attempt_1）。

### B. 体量与冗余

**B1 体量账本** — 判定：P1（最大段落必要性不足）

| 段落 | 字符 | 占比 |
|---|---|---|
| 指令区（任务/规格/清单/示例） | 7,516 | 2.1% |
| Runtime Input | 351,136 | 97.9% |
| ├ key_evidence_refs（54 张证据卡） | 210,122 | governance_input(237,719) 的 88.4% |
| ├ layer_summaries（五层摘要） | 18,035 | 7.6% |
| ├ 冲突清单+主要矛盾+防火墙+缺口+未决 | 8,901 | 3.7% |

最大 3 段（证据卡内）：`#slope_30d` 57,554、`get_m7_capex_cycle#companies` 32,775、`get_m7_buyback_flow#per_company` 25,352；加上 `#breadth_30d` 23,772，**四张卡合计 139,453 字符 = 证据包的 66.4%、governance_input 的 58.7%**。必要性判据（删掉会变差吗）：不会——输出实际引用的只有聚合值（上修斜率 +3.93%、capex 同比 +84.2%、回购 -22.4%）与 layer_summaries/TC 描述里已有的 NVDA/META/TSLA 字样，见 output.validated.json `failure_conditions[4]`、`must_preserve_risks[6]`。其余 50 张卡平均约 1.4K，是预处理良好的读数卡，必要。

**B2 站内重复 + 跨站重复主菜** — 判定：P1（本站最重发现）

跨站（与 critic 对照，两份 payload 逐字段比对）：
- risk `governance_input` 237,719 字符中 **199,599（84.0%）与 critic 逐字节相同**：42/54 张证据卡完全一致（190,698 字符）+ TC 冲突清单 3,392 + 主要矛盾 2,440 + 防火墙摘要 1,014 + 数据缺口 1,192 + 未决问题 863。
- 四张巨型卡（#slope_30d、#companies、#per_company、#breadth_30d，合计 139.5K）在 critic 侧**全部原样双运**（identical=True）。
- 两站差异仅：12 张卡在 critic 侧被替换为字面量 `13`（存疑：疑为截断/筛选标记，建议 critic 站报告跟进）；critic 独有 thesis_* 字段约 15K；critic 的 `layer_summaries` 为空（risk 有 18,035）。
- **判定：risk 与 critic 确实各自完整重运了同一套材料主菜，两个审查站拿到的证据面基本同一**（risk 侧甚至更肥：多 12 张完整卡 + 五层摘要）。

站内：
- `objective_firewall_summary.unresolved_tensions` **逐字复读** TC_01–TC_05 的 description（payload 对比确认 TC_01 description 为 tensions[0] 子串）；TC_01 description 全 prompt 出现 **3 次**（conflicts[0]、tensions[0]、tensions 末尾按 conflict_type 重复条目），TC_02–TC_05 各 2 次。
- `unresolved_questions` 内部自重复：第 1 条与第 7 条同为「期货重新收紧定价的性质（通胀约束vs增长过热）」（投影 L7361/L7367 区）。
- 同一数值多次同框（payload 全文计数）：`2.44`×24、`99.6`×17、`-1.42`×13、`702.7`×12、`8.97`×10、`45.75`×10、`63.34`×9、`57bp`×8。例：实际利率 2.44%/99.6 分位同时出现在 L1 摘要（投影 L312/L333）、L1.get_10y_real_rate 卡、TC_01 description、防火墙 tensions——同一数字最多 5 处同框，属 layer_facts ↔ 证据卡 ↔ 冲突清单三层的典型互为复读。

**B3 粒度错配** — 判定：P1
- `#slope_30d` 卡的 `field_value`（56,602 字符）内含 `constituents` 96 项逐股记录（53,475 字符，含 ticker/weight/slope_raw/fy1/fy2_revision/fiscal_weight 等）+ flagged 10 + invalid 6（payload 实测）。风险哨兵的检查清单（失效条件/边界/保留风险/矩阵）只消费聚合值，96 股逐行 dump 把 L4/bridge 层的预处理活推给了 risk 的注意力。

### C. 质量

**C1 指令冲突** — 判定：P2（两对轻微张力，无 P0）
1. 尾部规格把全部 8 个字段标为「可选」（投影 L7387 区）vs 关键约束「must_preserve_risks 必须非空」「质量检查 failure_conditions ≥2」「冲突矩阵必须显式检查」（L258、L269、L278）——存在/形状两套口径，实际输出两全，未造成损伤。
2. 「你拿不到论点论证……不得脑补一个论点出来攻击」（L77，论证盲设计）vs `principal_contradictions[0].action_implication` 直接给出「核心仓：持有……战术仓：以702.7-703.4与718为执行触发……等待现金：……」的仓位动作（payload）——输入自带准论点/仓位语义，与论证盲意图有张力；本次输出未照抄为自身判断，仅作背景消化。
3. 非冲突澄清：「不得编造概率数字」vs `failure_conditions.probability` 枚举——枚举选择不属编造统计，不构成冲突。

**C2 死指令** — 判定：指令侧排除；输出端坐实 3 个半死字段
- **检查清单 ↔ 数据一一对应（用户重点问题：数据支持了吗？支持）**：13 种冲突矩阵 A-M 所需指标全部在卡内（PE、趋势、A/D、XLY/XLP、10Y、铜金比等），输出 `conflict_matrix_check` 显式给出全部 13 键（output.validated.json L130-L144）；3.6 条要求的 `price_reflection` 字段存在（`partially_reflected`）；矛盾-冲突有 `contradiction_id`/`conflict_refs` 可对号（TC_01/02/04）；18 条数据缺口可逐条列入失效条件。清单不是死指令。
- **输出 8 字段全部产出且形状合规**。但下游消费检索（reviser / final_adjudicator / integrated_adjudicator 的 payload 关键词计数）：`must_preserve_risks` 被 reviser(×1) 与 final_adjudicator(×3) 消费，opportunity/confirmation/false_safety 被 reviser 消费；**`failure_conditions`、`boundary_status`、`conflict_matrix_check`、`generated_at` 三站全部 0 命中**——约一半的产出劳动无人读取，其中 `boundary_status`（哨兵的红黄绿总表）恰是本站名义上的头号交付物。

**C3 黑话词典** — 判定：P2（2 个传染源）
- 「简式差距/简式收益差距」：TC_01 description 首现（投影 L524 区「简式差距-1.42%」），全文无定义；已传染进输出叙事（must_preserve_risks[0]「简式收益差距-1.42%」），终审读者难解其义（即 forward 盈利收益率对 10Y 的简式差）。
- 「[M1]」：unresolved_questions 后 6 条引用（投影 L7367-L7373「[M1]被标记为已截断……」），全文无任何定义——新模型无从知道这是哪个 artifact 的标记。
- 「Bridge」：输入节作上游阶段名（L74「Bridge 主要矛盾候选」），无一句解释，低危（可从上下文推断）。「论证盲」首现即括号自释（L77）、「客观性防火墙」字段中文名自释，均可读。RRP/OAS/contango 等为通用术语不计。

**C4 数据新鲜度** — 判定：合理
- 卡片读数日期 2026-08-31/09-01/09-02，输出 `generated_at` 2026-09-02T19:52Z，新鲜。
- 过期快照全部显式标注：Top10 权重快照「锚截至2026-08-14、滞后运行时点19天」、forward PE 快照「过期42天」（known_data_gaps，投影 L7340 区）。无未标注的过期数据。

### D. 隔离

**D1 越权扫描** — 判定：未发现
- `final_adjudication`/`user_decision_profile`/`golden_pit`/`browser_sidecar`/`apparent_cross_layer_signals`/`layer_card` 全部 0 命中；`counter_thesis_hypotheses` 为空数组（投影 L7378）。`thesis` 的 8 次命中均为 `layer_synthesis` 等词的子串（Grep 逐条核验），仅 L77 为指令自述「拿不到论点」。risk 按设计可见五层摘要 + 跨层钩子，不属越权。

### E. 输出闭环

**E1 叙事字段体检**（对象：failure_conditions 的 condition/impact、must_preserve_risks、false_safety_risks）— 判定：整体优秀，2 处例外
- **黑话传染**：「简式收益差距」未解释直出（must_preserve_risks[0]）；「裁决标准因输入材料截断不完整」属元信息直出（见 E2）。
- **复读机检测**：6 句抽样，最长公共片段 16-19 字符共 3 句，均为数值短语（如「CCC-BB分层利差8.97个百分点」）或对 TC_01 implication 措辞的沿用（「这是当前对NDX收益/风险结构支配力最…」18 字，源：TC_01.implication「这是当前对NDX收益/风险结构支配力最强的单一关系」）；句子结构均为重组而非背题——基本通过，TC_01 措辞沿用记边界情况。
- **簿记语言密度**：数字全部嵌在因果链里服务判断（如 failure_conditions[2] 把 ADX 11.91、布林带 0.0397、ATR 682.22 串成「破位斜率」论证），无裸列。例外：must_preserve_risks[9] 与 confirmation_costs[2] 的「输入材料截断」是关于材料而非市场的簿记语言。
- **长度纪律**：规格未设长度要求；实际每条 60-150 字，克制，无违规可言。

**E2 因果对**
1. **成立**：材料缺陷——unresolved_questions 混入 6 条关于「[M1]」artifact 截断的元问题（投影 L7367-L7373，「需[M1]完整版」「[M1]可见部分只对相邻问题……」）→ 输出毛病——must_preserve_risks[9] 与 confirmation_costs[2] 把「裁决标准因输入材料截断不完整」写成市场风险条目。模型把「我的审查材料被截断」这个流程问题升格为风险叙事，正是这 6 条元问题的直接回声。
2. **成立（浪费但无害）**：四张逐股 dump 共 139.5K 字符（B1/B3）→ 输出零逐股发现，仅引聚合值——纯字节浪费，未造成输出损伤。
3. 站内数值复读（B2）未在输出端发现对应毛病，输出反而对各字段做了差异化表述——不成因果，不硬凑。

## 病灶清单（按严重度排序）

| 严重度 | 病灶 | 证据位置 |
|---|---|---|
| P1 | risk 与 critic 各自重运 84% 逐字节相同的证据主菜（199,599/237,719 字符），四张巨型卡全部双运 | 两站 payload governance_input 逐字段比对 |
| P1 | 证据包 58.7%（139,453 字符）是 4 张逐股 dump（96 成分 slope_30d 等），risk 清单只消费聚合值 | payload `key_evidence_refs` 四卡；output.validated.json 引用面 |
| P1 | 站内大段逐字复读：TC_01 description ×3、TC_02-05 ×2（防火墙 tensions 复读 TC 清单）；unresolved_questions 第 1/7 条自重复 | payload `objective_firewall_summary.unresolved_tensions`；投影 L7361/L7367 |
| P2 | `failure_conditions`/`boundary_status`/`conflict_matrix_check` 三个输出字段下游零消费（reviser/final/integrated 三站 0 命中） | 三站 payload 关键词计数 |
| P2 | unresolved_questions 混入 6 条 `[M1]` 元问题 → 输出把「材料截断」写进市场风险叙事（E2 对 1） | 投影 L7367-L7373 → output must_preserve_risks[9] |
| P2 | 「简式差距」「[M1]」无解释且传染进叙事散文 | TC_01 description；output must_preserve_risks[0]/[9] |
| P2 | 双输出规格分裂：示例 5 键边界 vs 清单 7 边界 vs 尾部规格「键自由」 | 投影 L101-L107 / L182-L189 / L7387 |
| P2 | 尾部规格全字段「可选」vs 关键约束「必须非空/≥2/显式检查」两套口径 | 投影 L7387 区 vs L258/L269/L278 |

## 修复建议

1. **（对应 P1 双运主菜）** 给审查站做差异化投喂：risk 与 critic 共享的证据包（TC 清单、主要矛盾、缺口、未决、54 张卡）在编排层只保留各自视角需要的子集——risk 保留五层摘要+冲突/矛盾/缺口面，critic 保留 thesis 面+其被标记的 12 张相关卡；四张巨型卡对两个审查站都换成聚合摘要卡（headline 值 + top/bottom 5 成分 + invalid 计数），全量 dump 留给按 ref 回查的通道。预计单站 Runtime 可从 ~35 万压到 <8 万字符。
2. **（对应 P1 粒度）** 在证据卡生成端做预处理：`#slope_30d`/`#companies`/`#per_company`/`#breadth_30d` 四卡增加 `aggregate` 视图字段（已算好的 value/winsorized/flagged 摘要），成分级明细默认不出现在审查站上下文。
3. **（对应 P1 站内复读）** `objective_firewall_summary.unresolved_tensions` 改为只存 `TC_0x` 引用 + 一句话增量（strongest_falsifier 已是此形态），不重复全文 description；unresolved_questions 去重（第 1/7 条合并）。
4. **（对应 P2 死字段）** 二选一：让 reviser/final_adjudicator 显式消费 `boundary_status` 与 `conflict_matrix_check`（红黄绿总表对终审有信息量）；或从 risk 输出契约中删掉这三个字段及配套检查清单段落，省下生成与校验成本。
5. **（对应 P2 元问题污染）** 上游把「artifact 截断/材料不完整」类问题分流到独立的 `material_limitations` 字段（或在编排层截留），不得混入 `unresolved_questions`；同时给 `[M1]` 类 artifact 标记附一句内联说明。
6. **（对应 P2 黑话）** TC_01 description 首次出现「简式差距」处补半句定义（如「简式差距：forward 盈利收益率减 10Y 名义收益率」）；或在叙事文风约定里要求输出端首现展开。
7. **（对应 P2 规格分裂）** 合并三处口径：头部「输出格式」示例的 boundary_status 补齐 7 键与清单一致，尾部规格只声明「存在性以关键约束为准、形状以本规格为准」。
