# final_adjudicator 通读报告

## 通读范围

语料根目录：`/Users/aidianchi/Desktop/ndx_mac/output/analysis/vnext/20260731_002156/context_spread/`

- 站：`final_adjudicator`，实例 `final_adjudicator.attempt_1`。manifest.json：`prompt_chars=247,717`，`projection_chars=203,028`（82.0%），`inspector_has_rules=true`，`verification_ok=true`。
- 原文：`full/final_adjudicator/attempt_1.prompt.txt`（293,959 字节 / 6,726 行）。下文行号无特别说明时均指此文件。
- 投影：`projected/final_adjudicator/attempt_1.projection.md`（248,704 字节 / 5,489 行）。

阅读方式（分区 + 程序化全图，非抽查）：

1. **任务书**（第 1–370 行：System Message、角色定义、输入、输出格式模板、判决正文、claim_ledger、裁决流程、关键约束、质量检查、长期资产评估）：经投影逐字全读，关键句回原文核对行号。
2. **## 输出字段规格 / ## Response Rules**（第 6693–6726 行）：经投影逐字全读，回原文核对行号。
3. **## Runtime Input**（第 371–6692 行，231,319 字符，占 93.4%）：用 python 直接解析原文 JSON，取得 `governance_input` 全部 41 个键的字符量/类型/空值清单（结构全图），随后**逐键读出全文**——全部 40 个非索引字段逐字读完；`key_evidence_refs` 30 条目中，23 条父级条目的全部子字段（narrative/reasoning_process/guards/falsifiers 等）逐字读完，7 条 `#` 子引用的元数据与汇总标量逐字读完。**例外（未逐字读完）**：3 条子引用内嵌的成分级原始数据表（`slope_30d` 的 97 行 constituents / 42 行 flagged，`breadth_30d` 的 103 行 × 2 periods 表，`m7_aggregate` 的 12 行季度表）只读了表结构、列名、汇总标量与头部行，中段行未逐行核对。
4. 投影截断标记（14 处 «…省略 N 字符…» + 2 处 `__table_projection__`）：涉及的散文字段因第 3 步直接从原文读取，已全部覆盖；`__table_projection__` 两处即上述成分表，中段未回查（见"盲区"）。
5. 数值/引用一致性：python 在原文上做跨字段比对（evidence_refs 合法性、相似度、数字抽取），命令随发现列出。

## 材料结构总览

按投影"段落目录"（百分比相对原文 247,717 字符）：

| 部分 | 字符 | 占比 |
|---|---|---|
| 任务书全部（System 约束 333 + 角色定义 2,380 + 输入 882 + 输出格式 4,742 + 判决正文 859 + claim_ledger 562 + 裁决流程/关键约束/质量检查/长期资产评估等） | ≈12,458 | ≈5.0% |
| `## Runtime Input` | 231,319 | 93.4% |
| `## 输出字段规格`（契约自动生成） | 3,293 | 1.3% |
| `## Response Rules` | 647 | 0.3% |

Runtime Input 是一个 JSON：`{"governance_input": {...}}`，41 个顶层键。按紧凑序列化计 145,499 字符，分布：

- **`key_evidence_refs`（证据索引）：116,150 字符，占 governance_input 的 79.8%**。30 个条目：23 条函数级父条目（L1×5、L2×3、L3×4、L4×4、L5×7）+ 7 条 `parent#Field` 子引用（全部 L4）。
- 其余 40 键合计 29,349 字符（20.2%）：thesis_* 系列 21 键约 22,000 字符（Thesis 站结论全文），治理/批评/修订 19 键约 7,300 字符。
- 索引内部：3 条子引用内嵌成分级原始数据表 `field_value` 合计 87,613 字符（`slope_30d` 58,097 + `breadth_30d` 22,965 + `m7_aggregate` 6,551），占索引 75.5%、占整个 governance_input 的 60.2%。

解读：这站名义上收到的是"压缩后的 governance_input"（第 76 行原文），实际体量的六成是 L4 两条盈利修正指标与 M7 capex 的逐成分股/逐季度原始数据；Thesis 结论、Bridge 矛盾、Critic 意见、Schema 结果等治理信息合计不到三成。

## 发现清单

### F-01 证据索引占材料八成，其中四分之三是原始成分级数据而非索引元数据

- 证据：`key_evidence_refs` 116,150 / 145,499 字符（79.8%）。
  命令：`python3` 解析原文 JSON 逐键计 `len(json.dumps(v))`（脚本见通读范围第 3 步）。输出（节选）：
  ```
  116150  dict    key_evidence_refs
  TOTAL governance_input json chars: 145499
  ```
  索引内逐条目输出（节选）：
  ```
  58859  dict    L4.get_ndx_earnings_revision_metrics#slope_30d
  23705  dict    L4.get_ndx_earnings_revision_metrics#breadth_30d
   7265  dict    L4.get_m7_capex_cycle#m7_aggregate
  ```
  这三条的 `field_value` 分别是：97 个成分股的逐股修正斜率表（`constituents` 49,436 字符 + `flagged` 42 条 6,976 + `invalid` 6 条 1,038）、103 成分 × 2 期的修正广度表、M7 十二个日历季度 capex 表（第 1117–6650 行区间）。
- 事实：任务书把 `key_evidence_refs` 定义为"证据索引"（第 44 行：refs 的合法来源清单），但索引 75.5% 的字节是 L4 原始计算中间产物（逐股数据），不是"哪些 ref 合法"的元数据。 Final 站的全部指令（判决正文、price_reflection_map 等）只需要引用 ref 名与权限，没有任何指令要求 Final 消费逐股斜率。

### F-02 索引中体量最大的两条证据恰是任务书要求"必须降级"的 supporting_only

- 证据：`L4.get_ndx_earnings_revision_metrics#slope_30d` 与 `#breadth_30d` 的 `field_authority`（命令同 F-01，逐条目打印）：
  ```
  slope_30d   field_authority={"source": "component_model", "usage": "supporting_only", ... "must not be upgraded to a core valuation conclusion."}
  breadth_30d field_authority={... "usage": "supporting_only" ...}
  ```
  任务书第 42–44 行（字段级证据闸门）："supporting_only / validation_only / audit_only 必须降级"。判决正文规则（投影第 355 行）："输入中标记为 audit-only 或 supporting_only 的字段不得作为正文中的数值依据"。
- 事实：两条 supporting_only 条目合计 81,062 字符，占证据索引的 69.8%；即材料按字节计的大头，恰好是规则上最不能作为结论依据的两条。其余 28 条（含全部 core_allowed 条目）合计仅 35,088 字符。

### F-03 同一指标两个读数：实际利率 MA20 在证据条目中是 2.334，在 thesis 侧 5 处被写成 3.26，并出现算术矛盾句

- 证据：证据条目（第 1153 行）：
  ```
  "current_reading": "2.41%，99.4%分位，高于MA20（2.334）3.26%",
  ```
  即 MA20=2.334、现值比 MA20 高 3.26%。但 thesis 侧 5 处写成"高于MA20 3.26%"（命令 `grep -n '高于MA20' attempt_1.prompt.txt`）：
  ```
  453:  ...当前实际利率2.41%高于MA20 3.26%，仍在上升趋势中...（thesis_hypothesis_responses[1].reasoning）
  503:  ...当前实际利率2.41%仍在上升趋势（高于MA20 3.26%）...（thesis_time_horizon_views[1].view）
  702:  ...实际利率99.4%分位且仍在上升趋势（高于MA20 3.26%）...（thesis_principal_contradiction.dominant_side）
  785:  ...且实际利率仍在上升趋势中（高于MA20 3.26%）...（thesis_price_reflection_map[0].rationale）
  1059: ...L1实际利率处于99.4%历史极端分位（2.41%，高于MA20 3.26%）...（objective_firewall_summary.unresolved_tensions[3]）
  ```
- 事实：按自然读法，这 5 处的"MA20 3.26%"表示 MA20=3.26%，与证据条目的 MA20=2.334 冲突；第 453 行"2.41%高于MA20 3.26%"按此读法是 2.41>3.26，算术不成立。`must_preserve_risks[0]`（第 1068 行）写"仍高于MA20"（无数值），与证据条目 narrative（第 1155 行）一致。同一材料中"实际利率相对 MA20 的位置"存在 2.334 与 3.26 两个可得多重读数。

### F-04 thesis 字段引用了 3 个不在 key_evidence_refs 中的 evidence ref

- 证据：命令：python 遍历 governance_input（除 key_evidence_refs 外）所有 `evidence_refs/counterevidence_refs`，与索引 30 键比对。输出：
  ```
  *** NOT IN key_evidence_refs ***  L1.get_fed_funds_rate_path   (used 1x, e.g. thesis_price_reflection_map[4])
  *** NOT IN key_evidence_refs ***  L2.get_ig_oas_bp            (used 1x, e.g. thesis_price_reflection_map[2])
  *** NOT IN key_evidence_refs ***  L2.get_vix_term_structure   (used 1x, e.g. thesis_price_reflection_map[3])
  ```
  行号：第 901 行（`"L1.get_fed_funds_rate_path"`，liquidity 类 counterevidence_refs）、第 851 行（`"L2.get_ig_oas_bp"`，credit 类）、第 878 行（`"L2.get_vix_term_structure"`，technical_panic 类）。
  任务书第 44 行："所有 evidence_refs / counterevidence_refs 必须**逐字**来自治理输入提供的证据索引（key_evidence_refs…）"。
- 事实：上游 thesis 的 price_reflection_map 五类中有三类的反证引用不在 Final 收到的索引里；与这些 ref 绑定的数字（加息 48bp、IG OAS 33.7% 分位、VIX 期限结构 16.9% 分位，第 897/847/873 行）在索引中也无对应条目。Final 若遵守第 44 行规则就无法追溯这三条反证，若照抄就违反规则。

### F-05 thesis 散文中多组数字在 key_evidence_refs 无对应条目

- 证据（命令：`grep -n <模式> attempt_1.prompt.txt`，逐条核对索引 30 键清单）：
  - "90日+10.7%"（90 日盈利修正斜率）：第 376、412、482、6687 行等；索引只有 `#slope_30d` 与 `#breadth_30d`，无任何 90d 条目。
  - "MACD柱状图负向扩大（-4.96）"与"CMF -0.133"：第 377 行；索引无 MACD/CMF 条目（L5 仅 adx/atr/donchian/multi_scale_ma/obv/rsi/volume 七条）。
  - "VWAP 702.73"：第 377、703、785 行附近多处；索引无 VWAP 条目。
  - "VIX 71.6%分位"与"FGI 38"：第 375 行（thesis_environment）；索引只有 VXN（87.2%分位），无 VIX/FGI 条目。
  - "10年期美债利率（4.61%）"：第 376、601、810 行；索引无 10Y 名义利率条目（L1 仅 10y2y/real/fed_funds/m2/net_liquidity）。`L4.get_equity_risk_premium#level.field_authority.reason` 自述"由已核验的 NDX 收益率与 10Y 美债名义收益率相减得到"，但名义收益率数值不在索引中。
- 事实：任务书统计约束（第 37–38 行）要求不得使用输入未提供的数字；这些数字本身在输入文本里出现，但 Final 的合法引用池（索引）无法覆盖它们——Final 若在正文引用这些数字，找不到可标注的 ref。

### F-06 Trailing PE 两值并存（29.4 vs 30.31），"盈利收益率3.3%"与"简式收益差距-1.21%"同句不自洽

- 证据：`L4.get_ndx_wind_valuation_snapshot#PE` 的 `field_value`（第 6319 行）：`"field_value": 29.4`。thesis 散文 6 处写"Trailing PE 30.31"（命令 `grep -n '30\.31'`，第 481、588、703、722、829、6664 行）。`L4.get_equity_risk_premium#level` 的 `field_value`（第 1612 行）：`-1.21`。第 376 行（thesis_valuation）原文：
  ```
  "简式收益差距为-1.21%——盈利收益率（3.3%）低于10年期美债利率（4.61%），安全垫为负"
  ```
- 事实：3.3−4.61=−1.31，不等于同句的 −1.21；−1.21 与 Wind PE 29.4 自洽（1/29.4=3.40%，3.40−4.61=−1.21），而 3.3% 与 30.31 自洽（1/30.31=3.30%）。即"收益率 3.3%"和"差距 −1.21%"分别对应材料里两个不同的 Trailing PE，被并列在同一句因果里；thesis_valuation 另写"trailing PE约30倍，处于10年41.66%分位"，41.66 分位挂在哪个 PE 上材料未注明。另：`objective_firewall_summary` 第 1059 行称该分位"中等"，第 917/1056 行称"中等偏高"，同一分位两种定性。

### F-07 "隐含约36%的盈利增长预期"用材料自身数字算不出来

- 证据：第 376 行："Forward PE仅19.46倍，隐含约36%的盈利增长预期（Trailing vs Forward差距）"。材料中的两个 Trailing PE：30.31（thesis 散文）与 29.4（Wind 条目，第 6319 行）。
- 事实：30.31/19.46−1=+55.8%；29.4/19.46−1=+51.1%；只有 1−19.46/30.31=35.8% 约等于 36%——即该数是把"Forward PE 相对 Trailing 的折价"当作了"盈利增长预期"。材料中无其他可得出 36% 的数字组合。

### F-08 输出形状在任务书与契约之间多处不一致

- 证据与事实：
  - (a) `approval_status` 枚举：任务书输出模板（第 103 行）与 quality_gate 模板（第 239 行）均为 `"approved | approved_with_reservations | rejected"`（3 值）；契约（第 6695 行）为 `"approved" / "approved_with_reservations" / "needs_revision" / "rejected"`（4 值，多 `needs_revision`）。
  - (b) `claim_ledger` 形状：任务书（第 262–281 行）称"可选字段，但形状是硬约束"，模板 entries 成员为 `{claim_id, source_stage, claim_text, claim_type, evidence_refs, counterevidence_refs}`；契约（第 6719 行）的 ClaimLedger 要求 `{schema_version, generated_at, effective_date, entries:[ClaimLedgerEntry{source_stage, claim_type, evidence_refs, counter_evidence_refs, inference_steps, falsification_conditions, authority_status, …}], publish_gate, evidence_registry_ref, no_backflow_rule}`。字段名不同（`counterevidence_refs` vs `counter_evidence_refs`），必填成员不同（claim_id/claim_text vs inference_steps/falsification_conditions/authority_status），契约多 4 个台账级字段。Response Rules（第 6725 行）说"形状冲突时以规格为准"，任务书说自己的形状是"硬约束"并引用真实事故（run 20260728_110702）。
  - (c) `stance_label`：任务书（第 52 行）"必须输出 stance_label 字段"；契约（第 6697 行）"stance_label（可选）：字符串 或 null"。
  - (d) `long_term_assessment`：任务书有整节语义要求（第 360–368 行），但其输出格式模板（第 99–250 行的 JSON）不含该字段；契约含（第 6713 行，可选）。模板同样不含契约里的 `generated_at`、`token_usage`。
- 事实陈述：四处不一致中，(a)(b) 是枚举值/字段名层面的直接冲突，(c)(d) 是"必须 vs 可选/缺失"的义务层级不一致。

### F-09 synthesis_guidance 含发给 Thesis 站的指令，并引用本站材料中不存在的字段

- 证据：第 6675–6685 行 `synthesis_guidance`（10 条，827 字符），原文照抄其中 3 条：
  ```
  "Thesis 只能整合 synthesis_packet，不得重新分析原始指标。",
  "必须显式消费 competing_hypotheses / hypothesis_competition_summary：正式综合前至少比较主线解释和反方解释；若证据不足，必须降级或保留争议。",
  "所有 key_support_chains 的 evidence_refs 必须来自 evidence_index 或 bridge_summaries。",
  ```
  命令：python 列出 governance_input 41 键——无 `synthesis_packet`、`competing_hypotheses`、`hypothesis_competition_summary`、`bridge_summaries`、`evidence_index`。
- 事实：这份指引的对象是 Thesis 站（"Thesis 只能整合…"），却装在 Final 的输入里；它点名要求消费的材料在 Final 的输入中不存在。Final 实际只拿到 `thesis_hypothesis_responses`（第 436 行起，对 `hyp_base_88ece56ecb`/`cth_01`/`cth_02` 三个假说的 verdict 与 reasoning），假说原文不在材料中——Final 能看到"驳回/吸收"的结论，看不到被驳回的假说本身。

### F-10 任务书点名可引的"预期-兑现台账"自声明 audit_only 且 forbidden_as_core_ref

- 证据：第 6646–6652 行 `pricing_expectation_ledger`：
  ```
  "metric_authority": "supporting_only",
  "effective_date": "2026-07-31",
  "packet_effective_date": "2026-07-30",
  "usage_rule": "pricing_narrative_support_only; forbidden_as_core_ref",
  "status": "audit_only_effective_date_mismatch"
  ```
  任务书第 343 行："分歧声明只能引用输入 refs（利率路径、盈利预期、波动溢价、预期-兑现台账），禁止凭空断言'市场认为'"。判决正文规则（投影第 355 行）："输入中标记为 audit-only 或 supporting_only 的字段不得作为正文中的数值依据"。
- 事实：任务书把"预期-兑现台账"列为分歧声明的合法引用源之一；该台账自身携带 `forbidden_as_core_ref` 与 `audit_only`（且 effective_date 与 packet 日期错一天）标记；判决正文规则又禁止 audit-only/supporting_only 字段作数值依据。三条表述并存于同一 prompt，各自合法边界不一致。

### F-11 字段级权限词汇只覆盖 7/30 条目，且另有两条的"supporting_only"身份只存在于散文里

- 证据：命令：python 逐条目打印 `permission_type` / `mixed_field_authority` / `field_authority`（完整输出见工作记录）。结果：
  - 7 条 `#` 子引用有 `field_authority.usage`：core_allowed×5（ERP#level、m7_aggregate、Wind PB/PE/PS）、supporting_only×2（breadth_30d、slope_30d）。本 run 材料中无 validation_only/audit_only/rejected 实例。
  - 23 条父级条目无 `usage` 字段，只有另一套词汇 `permission_type ∈ {fact×6, proxy×3, composite×3, structural×4, technical×7}`（按逐条目输出计数）+ `mixed_field_authority=false`。
  - `L4.get_m7_buyback_flow`（permission_type="fact"）的 narrative（第 1634 行）："…但属于supporting_only证据"；`L4.get_m7_earnings_blackout_calendar`（permission_type="composite"）的 boundary（第 2161 行）："只作回购支撑节奏的 supporting_only 时间上下文…"。
  - 任务书第 42–44 行的闸门以 core_allowed/supporting_only/validation_only/audit_only/rejected 表述，并要求"不得从结论文字猜测字段权限"。
- 事实：闸门词汇在机器可读字段里只存在于 7 条 L4 子引用；23 条父级条目的权限用另一套词汇表达，两套词汇之间材料未给映射；两条父级条目（buyback、blackout）的 supporting_only 身份仅以散文形式出现——其 `permission_type` 分别是 fact/composite。另外，4 个混族父引用（`L4.get_equity_risk_premium`、`L4.get_m7_capex_cycle`、`L4.get_ndx_earnings_revision_metrics`、`L4.get_ndx_wind_valuation_snapshot`）本身不在索引中，索引里只有它们的子引用——与第 42 行"函数级父引用只能表示混合容器"的表述并存。

### F-12 结构性重复量化（同一内容多份/多形态）

- 证据与事实（命令：python difflib.SequenceMatcher 与逐字段比对）：
  - (a) 主要矛盾双份交付：`thesis_principal_contradiction`（2,414 字符，第 698 行起）与 `principal_contradictions[0]`（1,897 字符，第 991 行起）：`contradiction_id`（RATE_VS_EARNINGS_ABSORPTION）、`conflict_refs`、`evidence_refs` 三者完全相同，整体文本相似度 0.759。措辞漂移实例：transformation_signals 第一条 thesis 版"盈利修正30日斜率从+4.2%转负且持续两周"（第 720 行）vs bridge 版"盈利修正斜率（30d）从+4.2%转负"（第 1014 行，无持续条件）；action_implication thesis 版"回落至2.0%以下"（第 705 行）vs bridge 版"回落至90%分位以下"（第 999 行）。
  - (b) 同一组冲突 4 种载体：`retained_conflict_types`（3 个类型标签，第 475 行）＝ `high_severity_typed_conflicts` 的 conflict_type 列表（完全重合）；`high_severity_typed_conflicts` 3 条的 description 逐字（作为子串）重复于 `objective_firewall_summary.unresolved_tensions`（程序验证 identical=True，第 917 vs 1056 行等）；unresolved_tensions 还多出第 4 条 `rate_vs_valuation: …`（第 1059 行），是第 1 条冲突的改写扩写版，且携带 F-03 的 MA20 失真。另两站字段 `thesis_principal_contradiction.conflict_refs` 与 `principal_contradictions[0].conflict_refs` 再次引用同一组 conflict id。
  - (c) 读者结论内嵌两份改写：`thesis_reader_conclusion.time_horizon_summary`（1,153 字符）与 `thesis_time_horizon_views`（2,150 字符）三个 horizon 一一对应、evidence_refs 全为子集（程序验证 subset=True）；`action_summary`（751 字符）与 `thesis_portfolio_actions`（1,515 字符）三个 bucket 一一对应、refs 全为子集。即时间尺度判断与仓位动作各以"技术语言版 + 人话版"出现两次。
  - (d) 字段名与内容不符：`high_severity_typed_conflicts`（第 911 行起）3 条中 2 条 `severity="medium"`（L2_L4_credit_vs_earnings、L5_L3_oversold_vs_structure），只有 1 条为 high。
- 合计可量化重复：仅 (a)+(b) 的显式重复约 6,000+ 字符；(c) 为同构改写 1,904 字符。

### F-13 指令要求消费、但材料为空或缺位的项

- 证据（命令：`grep -n`）：第 1064–1066 行 `"schema_structural_issues": []` / `"schema_consistency_issues": []` / `"schema_missing_fields": []`；第 6688 行 `"critique_cross_layer_issues": []`；第 6619 行 `"key_event_refs": {}`。
- 事实：
  - 输出模板与契约多处含 `event_refs` 数组（KeySupportChain.event_refs 第 6700 行、transformation_signals.event_refs、ClaimLedgerEntry 关联事件），synthesis_guidance 第 6685 行要求"event_refs 与 evidence_refs 分离"，但材料提供的事件引用池为空（`key_event_refs={}`），任务书未说明事件池为空时 event_refs 该如何填。
  - 裁决流程 Step 1（第 287 行）要求"检查 Schema Guard、证据链、DataIntegrity、must-preserve risks、高严重度冲突"；命令 `grep -n 'DataIntegrity\|data_integrity\|publish'` 显示全 prompt 中 DataIntegrity 只出现在该指令句本身，governance_input 41 键中无任何 DataIntegrity/发布状态字段。
  - Critic 的跨层问题清单为空（`critique_cross_layer_issues=[]`），只有 `critique_overall` 一段总评（275 字符，第 6687 行）。

### F-14 输入清单与实际键的对账：承诺的都在，另有 9 个未申报键；known_data_gaps 末条格式不一

- 证据：任务书第 76–96 行"关键字段包括"清单（33 个名字）与 python 解析的实际 41 键逐一比对：清单内全部存在；实际存在但清单未提及的 9 键：`thesis_confidence`（第 378 行）、`thesis_dependencies`、`thesis_hypothesis_responses`、`schema_missing_fields`、`key_event_refs`、`evidence_registry_summary`、`pricing_expectation_ledger`、`unresolved_questions`、`synthesis_guidance`。清单措辞为"关键字段包括"（非封闭）。第 6654–6660 行 `known_data_gaps` 前 4 条为 `get_*` 函数名，第 5 条为 `"[L3] narrow_breadth"`（第 6659 行，层标签+指标名格式，与 L3.get_advance_decline_line 条目的 risk_flags 值同名）。
- 事实：输入契约（"你只会收到一个压缩后的 governance_input JSON 对象"，第 76 行）与顶层级现实一致（Runtime Input 仅 governance_input 一个键）；但字段清单不封闭，未申报键中包含 Final 会被指令要求消费的内容（如 synthesis_guidance、pricing_expectation_ledger）。

## 盲区

1. **成分级原始数据表未逐行读**：`slope_30d.field_value.constituents`（97 行）与 `flagged`（42 行）、`breadth_30d` 的 103 行 × 2 periods 成分表（投影第 2318/2388 行为 `__table_projection__`，中段行被投影省略）、`m7_aggregate.by_calendar_quarter`（12 行）。我读了这些表的完整键结构、列名、汇总标量（coverage/flagged_weight_pct/yoy_acceleration 等）与头部行，未逐行核对中段成分数据；若中段行内藏数值矛盾，本报告无法发现。
2. **超集材料不可见**：任务书/指引引用的 `synthesis_packet.evidence_index` 全量、`evidence_registry` 本体（198 个 passport）、`competing_hypotheses` 假说原文、Bridge/Thesis 的完整 prompt 均不在本站材料中；"key_evidence_refs 是 evidence_index 子集"、"passport_count=198、downgrade_count=80"等自述无法验证。
3. **投影本身未逐字通读**：我以原文解析为主、投影为辅（投影用于段落目录、任务书与截断标记定位）。投影规则声称散文逐字保留，我抽查核对了 10 余处投影-原文一致（含全部 «…省略…» 标记的原文回查），但未做全文 diff。
4. **未审的东西**：`attempt_1.response.raw.txt`、`output.validated.json`、`meta.json` 不属于"站收到的材料"，未读、未用于任何发现；25 站中其余站材料未触碰。
5. 数值核查以"跨字段一致性"为限：只验证材料内部数字是否互相矛盾，未对照外部真实市场数据（如 QQQ 实际价格）验证真伪。
