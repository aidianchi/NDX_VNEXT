# risk 通读报告

站 = risk（Risk Sentinel 风险哨兵），run 20260731_002156，attempt_1，模型 deepseek-v4-pro，effective_date 2026-07-30。manifest 记 `inspector_has_rules: true`、`verification_ok: true`。

## 通读范围

- **主材料（全读）**：`projected/risk/attempt_1.projection.md`，5,258 行 / 231,247 字节（manifest 记投影字符 191,772，原文 236,788，投影比 0.8099）。分 7 段顺序通读：1–200、200–349、350–1349、1350–2349、2350–3349、3350–4349、4350–5258，无跳读。
- **原文（核查用）**：`full/risk/attempt_1.prompt.txt`，236,788 字符 / 6,553 行。用 `python3 json.loads` 完整解析其中 Runtime Input（229,315 字符的 `governance_input`），对 41 个顶层键、30 条 `key_evidence_refs` 逐键计量字符数；投影中 11 处散文截断中段（共 1,802 字符，形如 `«…省略 N 字符…»`）全部从 full/ 回收并通读；数值与引用用 grep/集合运算核对。
- **元信息（全读）**：`full/risk/meta.json`、`context_spread/manifest.json` 的 risk 条目。
- **未逐行读**：投影中 2 处 `__table_projection__`（`breadth_30d` 的 0y/+1y 成分表，各 103 行，仅 head 3 + tail 1 + stats）的中段各 99 行；full/ 中有全量但本次未逐行展开。详见"盲区"。
- **未读**：`attempt_1.response.raw.txt`、`parsed.normalized.json`、`output.validated.json`——它们是本站产出，不是"材料结构"审查对象。

## 材料结构总览

提示词全文 236,788 字符，三段分布（命令：`python3` 对 `full/risk/attempt_1.prompt.txt` 按 `## Runtime Input`、`## 输出字段规格` 锚点切分计量）：

| 区段 | 字符 | 占比 |
|---|---|---|
| 任务书+规则（System Message 至 `## 示例`） | 6,661 | 2.8% |
| `## Runtime Input`（一个 `governance_input` JSON） | 229,315 | 96.8% |
| `## 输出字段规格` + `## Response Rules` | 812 | 0.3% |

段落目录（投影头部）解读：29 个段落中 28 个合计不到 4%，唯一大头是 `## Runtime Input`（229,315 字符，96.8%）。任务书声明（projection:65）："你只会收到一个压缩后的 `governance_input` JSON 对象"。

`governance_input` 实际 41 个顶层键，字符量前五（`len(json.dumps(...))`）：

```
116150  key_evidence_refs        ← 占全提示词 49.0%
  3985  thesis_price_reflection_map
  2631  thesis_reader_conclusion
  2414  thesis_principal_contradiction
  2150  thesis_time_horizon_views
```

`key_evidence_refs` 30 条证据卡中，前 3 条合计 89,829 字符（全提示词的 37.9%），其余 27 条每条仅 670–1,187 字符：

```
 58859  L4.get_ndx_earnings_revision_metrics#slope_30d   ← 单条占全提示词 24.9%
 23705  L4.get_ndx_earnings_revision_metrics#breadth_30d
  7265  L4.get_m7_capex_cycle#m7_aggregate
  1187  L5.get_multi_scale_ma_position
  ...（26 条均 ≤1,187）
```

即：这站的材料结构 = 一本很薄的任务书 + 一个以"证据卡全文"为主体的巨型 JSON；JSON 内部一半体量是证据卡，证据卡的一半体量是两条盈利修正明细卡。

## 发现清单

> 行号凡未特别说明，均指 `projected/risk/attempt_1.projection.md`；标注 full: 的指 `full/risk/attempt_1.prompt.txt`。每条附可复跑命令与关键输出原文。

### F1 「证据索引」名实不符：声明是索引，实际投递全细节证据卡 + 原始明细表，且占近半体量

- 声明（76 行）：`- **key_evidence_refs**: 与高严重度冲突和 Thesis 支撑链相关的证据索引`
- 实际：`key_evidence_refs` 共 30 条、116,150 字符（占全提示词 49.0%）。每条不是"索引"而是全字段证据卡，含 `narrative / reasoning_process / first_principles_chain / cross_layer_implications / risk_flags / permission_type / canonical_question / misread_guards / cross_validation_targets / falsifiers / core_vs_tactical_boundary / confidence / source_tier / mixed_field_authority` 等 15 个字段（样例见 1001–1036）。
- 其中三条卡内含原始明细表：
  - `#slope_30d` 58,859 字符（2247–4801）：97 行成分明细（每行 17 个字段：slope、slope_raw、winsorized、fy1/fy2_revision、fy1_weight、fiscal_year_end、anchor 日期、flag 原因……）+ 40 行 flagged 明细 + 6 行 invalid 明细；
  - `#breadth_30d` 23,705 字符（2054–2246）：0y/+1y 两套各 103 行成分表（投影后仅 head/tail）；
  - `#m7_aggregate` 7,265 字符（1554–2019）：12 个季度逐季明细，且同一季度对象在 `by_calendar_quarter`、`latest_covered_quarter`、`prior_covered_quarter` 三处重复出现（如 2026Q1 逐字出现于 1871–1901 与 1932–1962）。
- 证据命令（可复跑）：
  ```
  python3 - <<'EOF'
  import json
  txt = open('full/risk/attempt_1.prompt.txt').read()
  i = txt.index('## Runtime Input'); j = txt.index('## 输出字段规格')
  g = json.loads(txt[i:j][txt[i:j].index('{'):].strip())['governance_input']
  ker = g['key_evidence_refs']
  for k in sorted(ker, key=lambda k:-len(json.dumps(ker[k],ensure_ascii=False))):
      print(len(json.dumps(ker[k],ensure_ascii=False)), k)
  EOF
  ```
  输出前 3 行原文：`58859 L4.get_ndx_earnings_revision_metrics#slope_30d` / `23705 L4.get_ndx_earnings_revision_metrics#breadth_30d` / `7265 L4.get_m7_capex_cycle#m7_aggregate`。

### F2 声明 22 个「关键字段」，实际 41 个顶层键；其中 4 个键与本站输出字段同名且为空数组

- 声明（65–79）："你只会收到一个压缩后的 `governance_input` JSON 对象，关键字段如下："后列 22 个字段名。
- 实际 41 键（同 F1 脚本打印，top-level key count: 41）。未在声明中出现的 19 个键：`thesis_confidence`(306)、`thesis_hypothesis_responses`(364)、`retained_conflict_types`(403)、`thesis_reader_conclusion`(525)、`schema_passed`(992)、`schema_structural_issues`/`schema_consistency_issues`/`schema_missing_fields`(993–995)、`must_preserve_risks`/`opportunity_costs`/`confirmation_costs`/`false_safety_risks`(996–999)、`key_event_refs`(5169)、`evidence_registry_summary`(5170)、`pricing_expectation_ledger`(5190)、`synthesis_guidance`(5225)、`critique_overall`(5237)、`critique_cross_layer_issues`(5238)、`revision_summary`(5239)。
- 其中 `must_preserve_risks`、`opportunity_costs`、`confirmation_costs`、`false_safety_risks` 四键与本站输出字段规格（5247、5249–5251）同名，在输入里以空数组出现：
  ```
  996:    "must_preserve_risks": [],
  997:    "opportunity_costs": [],
  998:    "confirmation_costs": [],
  999:    "false_safety_risks": [],
  ```
- 另有 `schema_passed: true`、三个 schema_* 空数组、`critique_overall: null`、`revision_summary: null` 等上游校验占位（992–995、5237–5239）。

### F3 `synthesis_guidance`（827 字符）是发给 Thesis/Final 的行为指令，出现在 risk 站输入里

- 5225–5236，共 10 条，原文示例：
  - 5227：`"Thesis 只能整合 synthesis_packet，不得重新分析原始指标。"`
  - 5233：`"Thesis / Final 的重要自然语言结论会进入 final_claim_ledger；缺证据、缺反证、缺失效条件或证据权限不足时必须降级。"`
- 该字段不在 65–79 的声明字段清单中；指令对象是 Thesis/Final 站的行为，不是 Risk Sentinel 的检查口径。

### F4 结构性冗余：同一内容以多份/多形态在站内重复

- (a) 主要矛盾双份：`thesis_principal_contradiction`（627–683，2,414 字符）与 `principal_contradictions[0]`（920–977，1,899 字符）同一 `contradiction_id: RATE_VS_EARNINGS_ABSORPTION`。difflib 对两 JSON 串（sort_keys）相似度 = **0.721**。任务书把两者分述为不同来源（73 行 Thesis 的判断、74 行 Bridge v3 候选），实际内容近逐字。
- (b) `objective_firewall_summary.unresolved_tensions`（984–989）4 条中 3 条与 `high_severity_typed_conflicts` 的 `description` 逐字相同（脚本比对结果 `True×3`）；第 4 条以 conflict_type `rate_vs_valuation` 为键（其余 3 条以 conflict_id 为键，键制式混用），内容是第一条冲突 `L1_L4_valuation_compression` 的改写复述（988 行）。
- (c) `thesis_reader_conclusion`（525–626，2,631 字符）把 `thesis_time_horizon_views`（2,150 字符）和 `thesis_portfolio_actions`（1,515 字符）的三个 horizon、三个 bucket 用通俗语言整体再写一遍：3 组 view 逐字比对 0 条相同但语义一一对应；action 措辞对示例：`维持防御性低配` vs `保持防御，暂不加仓`、`轻仓博弈超卖反弹，严格风控` vs `可轻仓试探反弹，但必须设好止损`。
- (d) 顶层 `unresolved_questions`（5211–5224，12 条）与 `thesis_principal_contradiction.unresolved_questions`（677–682，4 条）语义重叠（supplier_lookback 数据质量、回购季节性、Forward/Trailing 差值、简式收益差距消化程度四个主题两边都有），逐字比对 0 条相同——同一件事两种措辞各写一遍。

### F5 数值矛盾：NDX trailing PE 在同一提示词里并存三个值

- `32.5`：任务书两处示例（111 行 `"实际利率 1.95% 高位 + PE 32.5 高估值"`；290 行 `"PE 32.5（78%分位）"`；对应 full: 74、247）。
- `30.31`：Thesis 正文 7 处（full: 367、474、589、608、638、715、6509，如 "Forward PE从19.46向Trailing PE 30.31靠拢"）。
- `29.4`：Wind 证据卡 `"field_value": 29.4`（4869，full: 6164）。
- 另：`thesis_valuation` 称 "Forward PE仅19.46倍，隐含约36%的盈利增长预期（Trailing vs Forward差距）"（304，full: 261）。用并存的两个 trailing 值分别计算：30.31/19.46−1 = **55.8%**，29.4/19.46−1 = **51.1%**，均不等于 36%。
- 命令：`python3 -c "import re; ..."` 逐模式计数（输出见工作记录）；关键行原文照抄如上。

### F6 任务书示例与本次真实数据方向相反；两个示例互相也不一致

- 示例数值：实际利率 `1.95%（82%分位）`（111、290）、PE `32.5（78%分位）`（290）、`"盈利增速放缓风险：Forward/Trailing PE 比率暗示增速预期已下调"`（113）、`"breadth_deterioration": "breached"`（108）。
- 本次真实数据：实际利率 2.41%（99.4%分位，1041）、PE 29.4/30.31（10 年 41.66%分位，304/261）、盈利修正 30 日 +4.2% 向上（2254）。
- 两处示例之间：`earnings_miss` 在输出格式示例中为 `"safe"`（105），在风险边界评估示例中为 `"warning"`（282）；输出格式示例 `boundary_status` 列 5 项（103–109），检查清单列 7 项（175–182），风险边界评估示例列 7 项（280–288）。

### F7 引用了未投递的证据卡；散文中的多个数字在材料里没有对应卡片

- 集合差（cited − delivered）：`L1.get_fed_funds_rate_path`、`L2.get_ig_oas_bp`、`L2.get_vix_term_structure` 三者被 `thesis_price_reflection_map` 的 `counterevidence_refs` 引用（830、780、807），但 30 条投递卡中不存在。
- 这些引用各自携带具体数字，材料里只有结论没有出处：`"IG OAS同样仅33.7%分位"`（776）、`"VIX期限结构仍为contango（虽处16.9%低分位）"`（802）、`"Fed Funds Futures定价未来12个月加息48bp"`（826，另 819）。
- 从 full/ 回收的散文中段还有： `"波动率偏高（VIX 71.6%分位，VXN 87.2%分位），情绪偏恐惧（FGI 38）"`（full: 260）、`"MACD柱状图负向扩大（-4.96）……CMF -0.133确认派发"`（full: 262）——无 `get_vix`、FGI、`get_macd_qqq`、CMF 对应证据卡（VXN 有卡）。
- `"VWAP 702.73"` 全文 9 行出现（415、416、427、488、523、634、689、899、928），含作为止盈位的动作指令（488：`"止盈：VWAP 702.73附近或MA20 704.33附近，分批止盈"`）；30 条卡中无 VWAP 指标卡。
- 命令：对 `governance_input` 全 JSON 正则 `L[1-5]\.get_[a-z0-9_]+(#…)?` 取引用集合并与 30 个投递键做差集，输出原文：`L1.get_fed_funds_rate_path` / `L2.get_ig_oas_bp` / `L2.get_vix_term_structure`。（注：`ig_oas` 另在 1253 作为某卡的 cross_validation_targets 名字出现一次，非数据。）

### F8 90 日盈利修正：多处断言，材料里没有任何 90 日数据

- `"90日+10.7%"` 出现 4 处（340、632、750、926）；顶层 `unresolved_questions` 称 `"盈利修正斜率的置信度受supplier_lookback影响（30d flagged权重41%，90d 51%）"`（5212）。
- `key_evidence_refs` 只投递 `#slope_30d` 与 `#breadth_30d`；grep `slope_90d|90-day|90d` 在全部数据键中无 90 日字段命中（90d 字样仅出现在上述断言行）。
- 即 "90日+10.7%" 与 "90d flagged 51%" 两个数字在材料内没有出处。

### F9 `high_severity_typed_conflicts` 名实不符：声明"高严重度"，实装 3 条中 2 条 severity=medium

- 声明（75）：`- **high_severity_typed_conflicts**: 必须在最终报告中保留的高严重度跨层冲突`
- 实际：840–919 共 3 条冲突，`"severity": "high"` 仅 1 条（844，`L1_L4_valuation_compression`）；`"severity": "medium"` 2 条（870，`L2_L4_credit_vs_earnings`；896，`L5_L3_oversold_vs_structure`）。

### F10 `key_event_refs` 投递为空对象，同一块的注册表却记 72 个 event passport

- 5169：`"key_event_refs": {},`
- 5170–5189 `evidence_registry_summary`：`"passport_count": 198`，`"by_kind": { "data": 120, "event": 72, "investigation": 3, "hypothesis": 3 }`（72 在 5175）。
- `key_event_refs` 不在 65–79 的声明字段清单中；任务书对 event 的唯一规则在 `synthesis_guidance` 5235："event_refs 与 evidence_refs 分离"。

### F11 `known_data_gaps` 混入一条非数据缺口条目

- 声明（77）：`- **known_data_gaps**: 已知数据缺口（哪一层少了什么数据）`
- 实际 5 条（5204–5210），前 4 条是"某函数不可用/缺数据"（CFTC 仓位、crowdedness 短仓、wind PIT 盈利预期、forward earnings quality）；第 5 条为 `"[L3] narrow_breadth"`（5209）——这是 L3 证据卡里的 `risk_flags` 取值（对照 1321–1322 `"risk_flags": ["narrow_breadth"]`），不是"少了什么数据"。

### F12 证据卡内部的异常/边界数值原样进入材料

- `slope_30d` 成分表中 PAYX `"fiscal_year_end": "2020-08-31"`（4488），同表其他成分均为 2026–2027 年；锚定日为 2026-06-30。
- winsorize 帽值作为成分 slope 进入材料：HON `"slope": -0.5`（3859，slope_raw −0.5817，winsorized: true）、MSTR `"slope": -0.5`（4607，slope_raw −0.5438）、NBIS `"slope": 0.5`（4292，slope_raw 0.8763）；flagged 列表里同样出现（2513、2696、2610）。

### F13 System Message 引用本站输入里不存在的键

- 42：`4. 所有 evidence_refs 必须来自本次输入的 raw_data，不得凭记忆添加。`
- 43：`5. 若输入出现 \`NO_DATA_AVAILABLE\`，只能把它当作数据边界……`
- grep 全提示词：`raw_data` 与 `NO_DATA_AVAILABLE` 仅命中这两行自身；本站实际输入键是 `governance_input`（301），其下无 `raw_data`，全文无 `NO_DATA_AVAILABLE` 实例。

### F14 输出契约内部张力：规格全"可选" vs 清单要求非空/最少条数；冲突矩阵 13 种 vs 示例 4 键

- 输出字段规格（5243–5251）8 个字段全部标注 `（可选）`；而"必须遵守"要求 `✅ must_preserve_risks 必须非空`（251），质量检查要求 `failure_conditions 是否列出了至少 2 个失效条件？`（262）。
- 冲突矩阵：检查清单称 `检查 13 种冲突矩阵（A-M）中哪些被触发`（215）并给全 A–M 列表（229–241）；输出格式示例 `conflict_matrix_check` 只演示 A/B/C/K 4 键（140–145）；质量检查只问 `是否检查了 A、B、C、K 等关键冲突？`（271）。
- 边界清单口径不一见 F6（5 项 vs 7 项 vs 7 项）。

### F15 输入已预答本站职责要点，且含无出处量化估计与具体交易参数

- 任务书给本站的职责是"检查 Decision Thesis 是否充分考虑了所有风险因素……哪些风险边界必须保留，以及是否遗漏了过度谨慎、等待确认和假安全带来的风险"（53），并细化为失效条件/确认成本/机会成本/主要矛盾检查（151–211）。
- 输入里的 Thesis 已自带这些答案：`thesis_invalidation_conditions` 5 条（518–524）、`thesis_confirmation_cost`（517）、每个 horizon 的 `invalidation_conditions`（424–428、441–445、458–462）、`thesis_payoff_assessment` 的双向证据盘点（411）、`thesis_price_reflection_map` 每类的 `missing_evidence`（730–733、759–762、783–786、810–813、834–837）、`thesis_hypothesis_responses` 对三个假说的裁决与理由（364–402）。
- `thesis_portfolio_actions` 含具体交易参数（465–516）：`"入场参考Donchian下轨附近（661-665），止损设于MA200下方（640以下），止盈目标VWAP（702.73）附近"`（416）、`"仓位上限：正常战术仓的30-50%"`（490）。
- `thesis_confirmation_cost` 含量化估计 `"等待将错过估值修复的第一波上涨（可能5-10%级别）"`（full: 474；投影 517 行截断，中段已回收）——材料内无该 5-10% 幅度的出处；System Message 第 2 条（40）恰禁止"编造点位、跌幅……或其他定量影响幅度"。

## 盲区

1. **两张 103 行成分表的中段未逐行读**：`breadth_30d` 的 `0y`/`+1y` constituents 在投影中是 `__table_projection__`（各 103 行，仅 head 3 + tail 1 + min/max stats，2104–2157、2174–2227）。中段各 99 行我只读了 stats 汇总（weight/up/down/net_direction 的 min/max），未逐行展开 full/ 中的全量。若需逐行核（如检查中段是否有异常 ticker），可查 `full/risk/attempt_1.prompt.txt` 对应位置。
2. **投影↔原文未做逐字节 diff**：manifest 记 `verification_ok: true`、`projection_ratio 0.8099`；我只对 11 处散文截断点（共 1,802 字符，已全部从 full/ 回收通读，内容为 F5/F7/F15 涉及的数字与论证延续）和抽查键做了对照，未全量 diff。
3. **产出侧未读**：`attempt_1.response.raw.txt` / `parsed.normalized.json` / `output.validated.json` 未纳入本次审查（它们是产出不是材料；manifest 显示 response 与 parsed 哈希相同）。
4. **任务书引用的外部文件未读**：228 行 `完整列表（参考 NDX_COMMAND_V9.txt）`——该文件不在本站材料内，冲突矩阵 A–M 的定义我只能看到提示词内列出的 13 行标题，各条的触发阈值定义不可见。
5. **`pricing_expectation_ledger`（5190–5203）只有一个引用壳**：`artifact_ref: expectation_vs_realized.json`、`status: audit_only_effective_date_mismatch`（effective_date 2026-07-31 vs packet 2026-07-30），正文未投递；它声明 `must_not_enter_l1_l5_raw_prompt_or_evidence_ref`，本站不是 L1–L5，我无从判断该壳信息对本站的预期用途。
6. **`slope_30d` 97 行成分表逐行读了投影展示的全量（2728–4731），但未对每个 ticker 的 fy1/fy2_revision 做加权重算**——无法独立验证 0.0420763769 这个总分与 97 行明细是否算术一致。
