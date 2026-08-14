# thesis 通读报告

## 通读范围

- 站：`thesis`，实例 `thesis.attempt_1`（manifest.json `instances[31]`：`layout=standard`，`prompt_chars=209,854`，`projection_chars=209,728`，投影比 99.94%，`verification_ok=true`，`inspector_has_rules=true`）。
- 通读主材料：`context_spread/projected/thesis/attempt_1.projection.md`（278,845 字节 / 209,728 字符 / 5,499 行）。
- 原文备查：`context_spread/full/thesis/attempt_1.prompt.txt`（278,492 字节 / 209,854 字符 / 5,385 行）。
- 读法：全文 5,499 行分区通读——任务书/规则区（投影第 31–490 行）逐字全读；`## Runtime Input` 数据区（第 491–5,470 行，约 19.4 万字符）先解析 JSON 结构做分区地图，再逐区全读，遇投影截断标记（`«…省略 N 字符…»`、`__omitted__`、`__table_projection__`）回 full/ 查原值；输出字段规格与 Response Rules（第 5,471–5,499 行）逐字全读。
- 边查边写：本报告按节即时追加，非一次性写成。

## 材料结构总览

投影头部"段落目录"（投影第 6–29 行）给出的分布：

| 段落 | 字符 | 占比 |
|---|---|---|
| System Message + System-Level Constraints | 351 | 0.2% |
| vNext v2 Decision Thesis Contract（User Message 开头） | 1,319 | 0.6% |
| 角色定义 | 1,813 | 0.9% |
| 输入 | 323 | 0.2% |
| 输出格式 | 89 | 0.0% |
| 对竞争假说的强制回应 | 6,007 | 2.9% |
| 工作流程 Step 1–5 | 1,220 | 0.6% |
| 绝对禁止 | 297 | 0.1% |
| 质量检查 | 870 | 0.4% |
| **Runtime Input** | **194,429** | **92.6%** |
| 输出字段规格（ThesisDraft 契约） | 2,469 | 1.2% |
| Response Rules | 596 | 0.3% |

解读：任务书/规则合计约 12.9k 字符（6.1%），数据材料（Runtime Input）占绝对大头 92.6%。本站的结构审查重心因此落在 Runtime Input 的内部构成：它装了什么、与"只消费 synthesis_packet"的声明是否一致。

（以下各节随通读进度追加）

## 发现清单

说明：以下行号除特别注明"投影"外，均指 `context_spread/full/thesis/attempt_1.prompt.txt`（原文 5,385 行）。所有 JSON 比对用 `json.loads` 后做逐字节相等判断，命令均可复跑。

### A. 结构性缺失（指令要求消费 X，材料里没有 X）

**发现 1：任务书声明的 `event_index` 在包中不存在，全包无任何事件材料，但事件相关规则与待答问题多处出现**
- 任务书"## 输入"清单（full:82-94）列了 11 个重点字段，其中第 10 个是 `event_index`（full:93）。
- 实际 `synthesis_packet` 的键（核对命令：`python3 -c "json.loads(...).keys()"`）为：generated_at / packet_meta / context_summary / layer_summaries / bridge_summaries / high_severity_conflicts / high_severity_typed_conflicts / principal_contradictions / competing_hypotheses / hypothesis_competition_summary / adjudication_history / objective_firewall_summary / evidence_index / synthesis_guidance——**没有 `event_index`**。
- 全包 grep `evt_` 命中 0 次；`"event_refs"` 仅命中 2 次，都在任务书输出模板里（full:236、267），即材料中不存在任何事件 id。
- 但事件规则出现在三处：角色定义【证据纪律】（full:44"event_refs 只能作为催化剂、背景或观察事项"）、synthesis_guidance[9]（full:5352"event_refs 与 evidence_refs 分离"）、输出模板两个 `event_refs: []` 字段。
- 且 `hypothesis_competition_summary.retained_disputes` 末尾两条恰是事件问题（full:1504-1505）："事件是否已经因果性改变 NDX 走势"、"事件材料是否可直接成为 L1-L5 evidence_ref"——这两题在包内没有任何可供回答的事件材料。
- 附带事实：包中 generated_at / packet_meta / context_summary / adjudication_history 四个键不在任务书 11 字段清单里（量级很小，共约 930 字符；其中 adjudication_history 是空数组 `[]`，full:1512）。

**发现 2：synthesis_guidance 要求"必须尊重 evidence_registry_summary"，包中没有这个键**
- full:5348："必须尊重 evidence_registry_summary：数据、事件、调查、假说和最终 claim 使用同一种 evidence id；弱权限证据不能越权支撑强结论。"
- 核对：`'evidence_registry_summary' in sp` → False。包内最接近的是 `evidence_index`；两者名字不同，材料里没有任何文字说明二者关系。

**发现 3：系统级约束引用"raw_data"，本站输入里没有 raw_data**
- full:9（System Message 第 4 条）："所有 evidence_refs 必须来自本次输入的 raw_data，不得凭记忆添加。"
- 核对：`'raw_data' in sp` → False；本站 Runtime Input 只有 `synthesis_packet` 一个顶层键（任务书 full:15 也说"你现在只消费 synthesis_packet"）。同一份提示词内，系统约束与任务书对"证据出处"的指称不一致（raw_data vs synthesis_packet.evidence_index）。

### B. 结构性冗余（同一份材料多份/多形态重复）

**发现 4：typed_conflicts 在包内逐字节重复两份（各 2,095 字符）**
- `bridge_summaries[0].typed_conflicts`（full:634 起，macro_valuation Bridge 内）与 `synthesis_packet.high_severity_typed_conflicts`（full:1215 起）经 `==` 比较为 True：3 条冲突（L1_L4_valuation_compression / L2_L4_credit_vs_earnings / L5_L3_oversold_vs_structure）连同 description、mechanism、falsifiers、evidence_refs 完全相同的结构体出现两次。

**发现 5：同一组冲突在站内以 3 种形态出现 4 处**
- 形态一（纯字符串）：`bridge_summaries[0].key_conflicts`（full:628-633，621 字符）4 条。
- 形态二（结构体 plain）：`high_severity_conflicts`（full:1169-1213，1,516 字符）4 条；其 description 与形态一逐条相同（仅差"rate_vs_valuation: "等前缀，经 split(': ',1)[1] 比对 4/4 全中）。
- 形态三（结构体 typed）：发现 4 所述两份（各 2,095 字符，但只有 3 条，见发现 9）。
- 第四处复述：`objective_firewall_summary.unresolved_tensions`（full:1519-1523，496 字符）4 条——前 3 条 = typed_conflicts 的 description 加 conflict_id 前缀（逐字节验证 True），第 4 条 = key_conflicts[0] 全文（逐字节验证 True）。
- 合计：同一组跨层冲突的文本在本站提示词里占约 2,095×2 + 1,516 + 621 + 496 ≈ 6.8k 字符。

**发现 6：principal_contradiction 逐字节重复两份（各 1,843 字符）**
- `synthesis_packet.principal_contradictions[0]`（full:1292 起）与 `bridge_summaries[0].principal_contradiction`（full:855 起）`==` 比较为 True，含 transformation_signals、unresolved_questions 等全部 11 个键。

**发现 7：transformation_signals 在同一 Bridge 对象内重叠两遍**
- `bridge_summaries[0].principal_contradiction.transformation_signals`（full:875 起，562 字符，3 条）与 `bridge_summaries[0].contradiction_transformation_signals`（full:1061 起，997 字符，5 条）：前 3 条信号文本几乎相同，差异仅为修饰语（例："盈利修正斜率（30d）从+4.2%转负" vs "盈利修正斜率（30d）从+4.2%转负且持续两周"；"实际利率从2.41%回落至2.0%以下（约90%分位以下）" vs 同句加"且持续"）。同一 Bridge 内同一组信号两个清单、措辞微差。

**发现 8：同一组"未解决问题/不确定性"在包内复制 4-5 份**
- 逐字节验证结果（`==` 比较）：
  - `bridge_summaries[0].unresolved_questions`（5 条，full:1104，349 字符）== `hypothesis_competition_summary.retained_disputes[:5]`（full:1493）；
  - `bridge_summaries[1].unresolved_questions`（12 条，full:1138，723 字符）== `retained_disputes` 全量；
  - `bridge_summaries[1].key_uncertainties`（12 条，full:1153，610 字符）== `bridge_summaries[0].key_uncertainties`（5 条，full:1112）+ `retained_disputes[5:]`；
  - `competing_hypotheses[0].cannot_explain`（10 条，full:1373，667 字符）== `retained_disputes[:10]`；
  - `competing_hypotheses[0].falsification_conditions`（10 条，full:1385）== typed_conflicts 三条的 falsifiers 与 pc.transformation_signals 信号的合并重排（人工逐条比对，内容全部可在前述两处找到原文）。
- 即同一组问题清单在 Runtime Input 中至少出现 4 份完整或近完整拷贝。

### C. 不一致与矛盾（声明与现实、数值、容器口径）

**发现 9：两个"高严重度冲突"容器条目集不一致，且名称与内容严重度不符**
- `high_severity_conflicts`（full:1169）4 条：L1_L4_valuation_compression(high)、L2_L4_credit_vs_earnings(medium)、L5_L3_oversold_vs_structure(medium)、L1_L4_earnings_growth_vs_discount_rate(medium，full:1204)。
- `high_severity_typed_conflicts`（full:1215）只有前 3 条，缺 L1_L4_earnings_growth_vs_discount_rate。
- 两个容器名都带 high_severity，但 4 条里 3 条 severity=medium、3 条里 2 条 medium。
- 任务书 full:17 要求"retained_conflicts 必须包含 synthesis_packet.high_severity_conflicts 中的所有高严重度冲突"——在两个容器条目集不一致、且容器内混有 medium 的情况下，"所有高严重度冲突"指哪个集合、是否含 medium 条，材料本身没有给出界定。

**发现 10：objective_firewall_summary 的 strongest_falsifier 声称"真实利率回落"，与包内全部利率读数相反**
- full:1518：`"strongest_falsifier": "信用未恶化且真实利率回落，削弱衰退式解释"`。
- 包内实际利率的全部事实性表述：L1 key_evidence（full:437）与 evidence_index current_reading（full:1944）均为"2.41%，99.4%分位，高于MA20（2.334）3.26%"；L1 narrative（evidence_index 内）"仍在上行趋势中（高于MA20）"；bridge price_reflection_map rates 类（full:961）"实际利率仍在上升趋势中（高于MA20 3.26%）"。
- 全包 grep"真实利率/实际利率…回落"的其余命中全部是假设性失效条件（"若回落至90%分位以下"等），没有任何一处事实读数支持"已回落"。firewall 是任务书 full:18 点名"必须读取"的闸门字段。

**发现 11：同一利率比较在包内两种写法，压缩版可读作 MA20=3.26%**
- 原始写法（L1 key_evidence full:437、evidence_index full:1944）："高于MA20（2.334）3.26%"——MA20=2.334%，现值高于它 3.26%。
- 压缩写法出现于 4 处：bridge key_conflicts（full:629）、high_severity_conflicts（full:1174）、firewall unresolved_tensions（full:1523）、price_reflection_map rates rationale（full:961）："高于MA20 3.26%"——括号丢失后可读作 MA20=3.26%（比现值 2.41% 还高 85bp），与原始写法数值关系相反。

**发现 12：两个 PE/盈利收益率口径并存且被混用在同一条论证里，材料内无 reconciliation**
- Wind 口径：PE=29.4、trailing earnings yield 3.40%（evidence_index `L4.get_ndx_wind_valuation_snapshot` full:3559 区与 `L4.get_equity_risk_premium` full:4388）；简式收益差距 -1.21% = 3.40% − 4.61%。
- 另一口径：PE=30.31、EarningsYield=3.3%（`L4.get_ndx_pe_and_earnings_yield` full:3559，current_reading 注明 Danjuan 分位）。
- 混用处：price_reflection_map valuation 类 rationale（full:986）写"盈利收益率（3.3%）低于无风险利率（4.61%）"——3.3−4.61=−1.31，与同一类目 target 及全包各处使用的 -1.21% 相差 10bp，同一论证块内两个差距数值并存。
- 材料内对两个 PE（29.4 vs 30.31）为何并存没有任何说明文字；wind 条目 misread_guard 只有"Wind RiskPremium定义未核验，不能解释为补偿厚薄"。

**发现 13：上游 Bridge 递来的子引用在 evidence_index 里不存在（悬空 ref）**
- bridge price_reflection_map valuation 类：evidence_refs 含 `L4.get_damodaran_us_implied_erp#damodaran_erp_historical_percentiles`（full:992），counterevidence_refs 含 `L4.get_damodaran_us_implied_erp#erp_t12m_adjusted_payout`（full:1002）。
- evidence_index 中 `L4.get_damodaran_us_implied_erp` 只有函数级父条目（full:4884 区），**没有任何 # 子条目**（`damodaran` 相关键仅 1 个，命令输出：`damodaran keys in ei: ['L4.get_damodaran_us_implied_erp']`）。
- 任务书 full:48 规定"子引用必须逐字存在于 evidence_index 中，不得自行拼接……需要的子引用不在索引里时，只能退回索引中存在的非 mixed 父引用，或放弃该论断"——即上游输入本身携带了按本站规则不合法的子 ref。

**发现 14：mfa 规则指定的强制引用路径上，子条目缺值或为壳**
- 任务书 full:17/46/5349：mfa=true 的父 ref 不能支撑强结论，必须用 #FieldName 子 ref。mfa=true 的父条目共 8 个（L1.get_fed_funds_rate_path、L2.get_crowdedness_dashboard、L2.get_vix_term_structure、L2.get_cnn_fear_greed_index、L4.get_ndx_wind_valuation_snapshot、L4.get_ndx_pe_and_earnings_yield、L4.get_equity_risk_premium、L4.get_m7_capex_cycle）。
- 实例一：bridge 与 cth_01 均以 `L4.get_m7_capex_cycle#m7_aggregate` 为 M7 资本开支 +74.96% 的支撑 ref；该子条目（full:4554 区）的 field_value **没有 value/availability 键**，+74.96 只出现在嵌套的 `latest_covered_quarter.yoy_pct` 与 `yoy_acceleration.latest_yoy_pct` 里；兄弟子条目 `#yoy_acceleration` 的 field_value 整体缺失（壳），而同样内容又嵌在 #m7_aggregate 内部。
- 实例二：`L4.get_ndx_pe_and_earnings_yield`（mfa=true）的三个子条目中 `#ForwardPE` field_value 缺失（其 misread_guard 自述"ForwardPE陈旧不可用"）。
- 总体普查（54 个 # 子条目）：仅 7 个带完整 value 结构，22 个为裸标量，7 个 value=null，18 个 field_value 缺失/null——即 25/54 个子条目取不到值；其中全部 7 个 CFTC 子条目、5 个 FINRA 子条目均无值。

**发现 15：L2 摘要正文使用恐贪指数，但其 indicator_refs 不含该指标**
- L2 local_conclusion（full:454）"恐惧情绪（FGI 38）"、layer_synthesis（full:455）同、internal_conflict_analysis（full:486）"恐贪指数为恐惧（38），但垃圾债需求子指标为贪婪（64）"。
- L2.indicator_refs（full:456-469）共 12 个 ref，不含 `L2.get_cnn_fear_greed_index`。
- evidence_index 里该指标父条目（full:3096，current_reading "37.97，评级'fear'"）与 #score/#sub_metrics 子条目均存在。
- 旁证：packet_meta 称 47/50 指标成功；五层 indicator_refs 并集恰好 47 个；FGI 是 evidence_index 48 个父条目中唯一不在任何 indicator_refs 里的。哪 3 个指标失败、失败的是哪几个，包内没有任何清单。

### D. 职责与材料错配

**发现 16：evidence_index 占 Runtime Input 的 53.1%，内含单层推理全文与审计级明细，与"不得重新分析原始指标"的职责并存**
- 体量：evidence_index 102 条、103,322 字符，占 Runtime Input（约 194.6k 字符）的 53.1%；行跨度 full:1527-5340（3,814 行）。
- 内容形态一：48 个函数级父条目各自携带 narrative / reasoning_process / first_principles_chain / cross_layer_implications / falsifiers / core_vs_tactical_boundary 等单层推理全文（例：`L1.get_10y_real_rate` 的 narrative 含"此信号优先级极高"，reasoning_process 为 4 步编号推理）。而任务书（full:15）说"不要替 L1-L5 补写单指标推理"、synthesis_guidance[1]（full:5344 区）说"不得重新分析原始指标"——单指标推理原文本就全部在站内材料里。
- 内容形态二：最大 4 条均为 L4 盈利修正/资本开支条目（slope_30d 4,775 字符、slope_90d 4,392、m7_aggregate 3,459、breadth_30d 3,206），内含逐 ticker 成分样本、winsorized_count、flagged_weight_pct、coverage 权重等审计级明细，并自带标注 `"_prompt_summary": true` 与注释"完整明细保留在 synthesis_packet.json / evidence_registry.json 供审计与独立重算"（full:3149、3874 等 11 处 `_prompt_summary`）。
- 引用面：102 条中 47 条在包内 evidence_index 之外从未被任何 ref 形式引用（正则 `L[1-5]\.[a-z0-9_]+(#…)?` 全文提取比对），含全部 7 条 CFTC 子条目、全部 5 条 FINRA 子条目、FGI 父子 3 条、wind snapshot #RiskPremium 等；未被引用的 47 条约占 102 条的 46%。

**发现 17：bridge_summaries[1]（feedback_bridge_v2）是空壳，但它占据任务书点名的主要矛盾来源位**
- full:1121-1167：该 Bridge 的 key_claims / key_conflicts / typed_conflicts / resonance_chains / transmission_paths / secondary_contradictions / price_reflection_map / contradiction_transformation_signals 全部为 `[]`，principal_contradiction 为 `null`；非空的只有从它处逐字节复制的 unresolved_questions 与 key_uncertainties（见发现 8），以及 implication_for_ndx（full:1152）："Bridge V2 已读取受控 InvestigationReport。若调查未能建立新证据，二次综合必须保留原有张力并降低强裁决倾向。"——这是一条流程说明，不含任何市场内容。
- 所指的 InvestigationReport 内容不在包内：全包仅 cth_01/cth_02 的 source_refs 出现字符串 "investigation_reports/*.json"（full:1448、1485），无任何调查报告正文或摘要。
- 任务书 Step 2（full:406 区）把 `bridge_summaries[].principal_contradiction` 列为主要矛盾的来源之一；两个 Bridge 之一该字段为 null。

**发现 18：任务书"必填"与契约生成规格"可选"口径相反**
- 任务书（full:20）"Decision Semantics 必填语义"点名 state_diagnosis、priced_narrative、payoff_assessment、time_horizon_views、portfolio_actions、confirmation_cost、invalidation_conditions 等必须填写；质量检查（full:473 区）逐条查这些字段"是否非空/是否覆盖"。
- 输出字段规格（full:5367-5370 等）把上述字段全部标注"（可选）"；必填的只有 environment_assessment / valuation_assessment / timing_assessment / main_thesis / overall_confidence。
- Response Rules（full:5380 区）写"字段的形状……以上面「输出字段规格」为准"，但必填与否不属于形状问题，两份规则对同一字段的强制程度说法相反。

## 盲区

- **evidence_index 父条目 narrative 未逐条精读**：48 个函数级父条目中，我逐字精读了 8 个（L1.get_10y_real_rate、L4.get_ndx_earnings_revision_metrics#slope_30d、L4.get_m7_capex_cycle#m7_aggregate、L4.get_m7_buyback_flow#actual_buyback_spending、L4.get_damodaran_us_implied_erp、L2.get_cnn_fear_greed_index、L4.get_ndx_wind_valuation_snapshot、L4.get_ndx_pe_and_earnings_yield），其余 40 个父条目只读了 current_reading / normalized_state / permission_type / source_tier / mfa 标志的紧凑扫描，narrative、reasoning_process、misread_guards 全文未逐条读。条目级数值矛盾（如某条目 narrative 与另一条目读数打架）可能有漏网。
- **数值核对是抽查不是穷举**：跨区交叉核对了约 15 组数字（实际利率 2.41/99.4%、HY 质量利差 837bp/99.9%、PE 29.4/30.31、EY 3.40/3.3、Forward PE 19.46、修正斜率 +4.2%/+10.7%、广度 56.9%、回购 -68.74%、capex +74.96%、VIX 20.66/71.6%、VXN 30.84/87.2%、净流动性 5915.18B/+108.38B、QQQ 661.73、Donchian 下轨 661.14、FGI 37.97 vs 38），未发现除发现 10/11/12 外的矛盾；但 102 条目的全部数值未逐一重算（如 breadth_30d 的 {"0y": 56.9, "+1y": 54.96} 与摘要只用 56.9 的关系未深究）。
- **投影截断处全部回原文核对过，无实际盲区**：投影共 8 处 `«…省略 N 字符…»`（75-165 字符，全在散文中段，投影行 531/558/634/645/674/686/1225/1520），对应段落我在 full/ 原文均已逐字读过。11 处 `_prompt_summary: true` 是原始 payload 自带的样本标记（非投影截断），其完整明细在包外文件（synthesis_packet.json / evidence_registry.json），我未打开包外文件核对。
- **未读同目录其他文件**：full/thesis/ 下的 attempt_1.payload.json、attempt_1.parsed.normalized.json、attempt_1.response.raw.txt、output.validated.json、meta.json 未读——任务边界是审"输入材料结构"，站的产出不在范围内。
- **"为什么这样组包"不可知**：我只能陈述包内事实（如 evidence_index 里 47 条未被引用、25 条子条目无值），这些是有意留白（给 Thesis 的引用菜单）还是组装疏漏，材料本身无法回答，本报告不做动机判断。
