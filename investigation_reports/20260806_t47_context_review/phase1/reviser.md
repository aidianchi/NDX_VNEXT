# reviser 通读报告

> 阶段一·逐站通读。语料根目录：`/Users/aidianchi/Desktop/ndx_mac/output/analysis/vnext/20260731_002156/context_spread/`（下文 `full:` / `proj:` 行号分别指 `full/reviser/attempt_1.prompt.txt` 与 `projected/reviser/attempt_1.projection.md`）。只读语料，未修改任何语料/代码文件。

## 通读范围

- **投影全读**：`projected/reviser/attempt_1.projection.md` 5366 行逐区读完——头部段落目录（1–40）、任务书指令区（41–366，逐字）、Runtime Input 区（367–5351，分 5 段全读）、尾部契约区（5352–5366，逐字）。投影 197,248 字符 / 原文 242,402 字符（81.4%，manifest.json 记录 `inspector_has_rules: true`、`verification_ok: true`）。
- **程序化核查**（均用 python3 解析 full prompt 第 318–6640 行的内嵌 JSON，可复跑）：
  - governance_input 42 键的字符分布；key_evidence_refs 30 条逐条字符量；
  - 输入中全部 evidence_refs/counterevidence_refs（去重 33 种）与索引 30 键的逐字比对；
  - event_refs 全树扫描、mixed_field_authority 全条目扫描；
  - thesis_principal_contradiction vs principal_contradictions[0] 的 difflib 相似度；
  - unresolved_questions 三处逐字比对；slope_30d 内 flagged 列表与 constituents 的 ticker 集合比对；
  - 12 处 `«…省略 N 字符…»` 散文**全部**回查原文（grep 出完整字符串）；
  - 数值专项 grep：30.31 / 29.4 / 41.66 / 36% / 48bp / 702.73 / 90日+10.7% / 4.61 / 3.3% / FGI / MACD / CMF / 33.7 / 16.9 / "高于MA20 3.26%"。
- **辅助文件**：`full/reviser/meta.json`（模型 deepseek-v4-pro，effective_date 2026-07-30，attempts=1，status ok）；`full/reviser/attempt_1.parsed.normalized.json`（注意：这是**输出**解析件，非输入）。
- **未逐字读**：`attempt_1.payload.json`（280,046 字节）、`response.raw.txt`、`output.validated.json`（本阶段任务是审材料结构，不是评产出）；breadth_30d 的 103×2 行成分表原文（投影只给 head 3 + tail 1 + stats，未逐行回查）。详见盲区节。

## 材料结构总览

### 段落目录解读（投影头部目录，字符量为原文区段口径）

| 区段 | 字符 | 占比 |
|---|---|---|
| System Message（系统级约束 6 条） | 351 | 0.1% |
| 任务书（角色/硬合约×2/输入说明/输出格式/修订原则×5/流程×5/约束/质检/示例） | ≈9,300 | ≈3.8% |
| **Runtime Input（governance_input JSON）** | **231,241** | **95.4%** |
| 输出字段规格（AnalysisRevised 契约） | 1,817 | 0.7% |
| Response Rules | 307 | 0.1% |

### Runtime Input 内部构成（实测，命令见各发现）

- 顶层只有 `governance_input` 一个键，其下 42 个键，JSON 共 231,223 字符。
- **`key_evidence_refs`（dict[30]）= 116,150 字符，占运行时输入 50.2%**。其中三条盈利/资本开支相关子条目合计 89,829 字符（38.9%）：
  - `L4.get_ndx_earnings_revision_metrics#slope_30d`：58,859 字符（25.5%）——内含 97 行成分股全表（每行 18 个字段）+ 42 行 flagged 列表 + 6 行 invalid 列表；
  - `#breadth_30d`：23,705 字符（10.3%）——内含 103 行×2 期成分表（投影截断为 head/tail）；
  - `L4.get_m7_capex_cycle#m7_aggregate`：7,265 字符（3.1%）——12 个季度×3 份（by_calendar_quarter 全表 + latest/prior 两份整季重复）。
- 其余 27 条索引条目各 670–1,190 字符；Thesis 原文各字段（thesis_*）合计约 2.5 万字符（≈11%）；Critic/Risk/Schema 三方反馈合计约 2,000 字符（<1%）。
- 6 个键为空值/空容器：`revision_summary: null`（full:6637）、`schema_structural_issues: []`、`schema_consistency_issues: []`、`schema_missing_fields: []`（proj:1061–1063）、`key_event_refs: {}`（full:6567）、`critique_cross_layer_issues: []`（proj:5347）。

## 发现清单

### F-01 证据索引占材料一半，且其消费定位只是"对照用"
事实：`key_evidence_refs` 独占运行时输入 50.2%（116,150/231,223 字符），其中 slope_30d 一条占 25.5%（58,859 字符，含 97 行成分股原始数据）。而任务书对该索引的定位是"与高严重度冲突和 Thesis 支撑链相关的关键证据引用（**修正数据引用错误时对照用**）"（full:66 区域「输入」说明），synthesis_guidance 另规定"**Thesis 只能整合 synthesis_packet，不得重新分析原始指标**"（proj:5336）。reviser 的角色定义是"编辑，不是重写者"（proj:62-63）。
证据：
```
$ python3 解析内嵌 JSON（命令见 总览节）
  58859 (25.5% of runtime)  L4.get_ndx_earnings_revision_metrics#slope_30d
  23705 (10.3% of runtime)  L4.get_ndx_earnings_revision_metrics#breadth_30d
   7265 ( 3.1% of runtime)  L4.get_m7_capex_cycle#m7_aggregate
  ...其余 27 条各 670–1,190 字符
```

### F-02 上游 Thesis 自带的 3 条 evidence_ref 不在给定索引中
事实：输入材料里共出现 33 种去重 evidence_refs/counterevidence_refs，其中 3 种逐字查证不在 `key_evidence_refs` 30 键中：`L2.get_ig_oas_bp`（full:799）、`L2.get_vix_term_structure`（full:826）、`L1.get_fed_funds_rate_path`（full:849），全部位于 `thesis_price_reflection_map` 的 counterevidence_refs。而硬合约要求 reviser 输出的所有 ref "必须**逐字**存在于 `key_evidence_refs` / evidence_index 中"（proj:75、79-81）。
证据：
```
$ grep -n "L1.get_fed_funds_rate_path\|L2.get_ig_oas_bp\|L2.get_vix_term_structure" full/reviser/attempt_1.prompt.txt
799:          "L2.get_ig_oas_bp"
826:          "L2.get_vix_term_structure"
849:          "L1.get_fed_funds_rate_path",
$ python3 集合比对：引用去重后 33 种；不在索引中的 3 种（即上三条）
```

### F-03 证据纪律提供的"退回函数级父引用"通道在材料里不存在；mixed_field_authority 条款无适用对象
事实：证据引用纪律给了两个"诚实选项"，其一是"退回索引中存在的函数级父引用（该父引用未标记 mixed_field_authority 时）"（proj:82）。但 4 个函数级父引用 `L4.get_ndx_earnings_revision_metrics`、`L4.get_equity_risk_premium`、`L4.get_m7_capex_cycle`、`L4.get_ndx_wind_valuation_snapshot` 经程序核对**都不在**索引 30 键中——索引只收 `#子引用` 形态。同一条纪律还用一整条讲 `mixed_field_authority=true` 的处理（proj:83），但 30 条条目里该字段全为 false。
证据：
```
$ python3: for parent in [...4 个父 ref...]: print(parent in keys)
L4.get_ndx_earnings_revision_metrics -> False
L4.get_equity_risk_premium -> False
L4.get_m7_capex_cycle -> False
L4.get_ndx_wind_valuation_snapshot -> False
$ python3: [k for k,v in ker.items() if v.get('mixed_field_authority') is True] -> []
```

### F-04 Thesis 散文多处关键数字在索引中无对应条目；PE 一处同指标两值
事实（均经 grep 定位、与 30 条索引逐条比对）：
- "Trailing PE **30.31**" 出现 7 处（full:429、536、651、670、700、777、6612），另有"trailing PE约30倍"（full:323）；索引中唯一的 PE 值是 `L4.get_ndx_wind_valuation_snapshot#PE` 的 `field_value: 29.4`（full:6267）——同一指标散文与索引值不同（30.31 vs 29.4）。
- "10年**41.66%分位**"出现 7 处（full:323、429、733、758、865、1004、1007）；索引 #PE 条目只有 field_value，没有任何分位字段。
- "盈利收益率（3.3%）低于10年期美债利率（4.61%）"（full:323、549、758）；索引无 10Y 名义利率条目（3.3% 与 30.31 自洽：1/30.31=3.30%；与索引 29.4 则为 3.40%）。
- "90日+10.7%"出现 6 处（full:323、359、430、649、651、769），critique_overall 也引用"90d +10.7%"（full:6635）；索引只有 30d 条目（#slope_30d、#breadth_30d），没有任何 90d 条目。
- "VWAP 702.73" 6 处（full:324、434、435、446、507、542）——索引无 VWAP 条目；"加息约48bp"（full:322、838、845）——无 fed_funds_rate_path 条目；"VIX 71.6%分位""FGI 38"（full:322）——无 VIX/FGI 条目；"MACD柱状图…-4.96""CMF -0.133"（full:324、347、811）——无 MACD/CMF 条目；"IG OAS…33.7%分位"（full:795）、"VIX期限结构…16.9%低分位"（full:821）——对应条目均不在索引。
证据示例：
```
$ grep -n "30\.31" full/reviser/attempt_1.prompt.txt | head -3
429: ..."thesis_priced_narrative": "…（Forward PE 19.46→Trailing PE 30.31的压缩空间）…"
$ grep -n "29\.4" full/reviser/attempt_1.prompt.txt
6267:        "field_value": 29.4,
```

### F-05 "高于MA20 3.26%"压缩表述 5 处，其中一处按字面读自相矛盾
事实：索引原文是 "2.41%，99.4%分位，高于MA20（2.334）3.26%"（full:1101）——MA20=2.334，高出幅度 3.26%。散文 5 处压缩为"高于MA20 3.26%"（full:400、451、650、733、1007），丢掉了 MA20 的值；其中 cth_01 的 reasoning（full:400）写成"**但当前实际利率2.41%高于MA20 3.26%**"，按字面读即"2.41% > 3.26%"，不成立。
证据：
```
$ grep -n "高于MA20 3\.26\|高于MA20（2\.334）" full/reviser/attempt_1.prompt.txt
400: …cth_01 reasoning…实际利率2.41%高于MA20 3.26%…
451 / 650 / 733 / 1007: …（高于MA20 3.26%）…
1101: "current_reading": "2.41%，99.4%分位，高于MA20（2.334）3.26%",
```

### F-06 "隐含约36%的盈利增长预期"口径不明，两种口径相差约20个百分点
事实：full:323 写 "Forward PE仅19.46倍，**隐含约36%的盈利增长预期（Trailing vs Forward差距）**"。按材料自身的 30.31/19.46 验算：PE 折扣口径 (30.31−19.46)/30.31=35.8%≈36%（对得上数字，但这不是"盈利增长预期"）；盈利增长口径 30.31/19.46−1=+55.8%。若用索引 PE 29.4 算增长口径为 +51.1%。材料中无任何处注明 36% 的口径。

### F-07 同一 41.66 分位，描述词两个版本
事实：thesis_valuation 与防火墙第 4 条 tension 写 "41.66%分位（**中等**）"（full:323、1007）；high_severity_typed_conflicts 的 description 与防火墙前 3 条 tension 写 "41.66分位（**中等偏高**）"（full:865、1004）。

### F-08 主要矛盾双份近重复：Thesis 版与 Bridge 版同 id 并存
事实：`thesis_principal_contradiction`（2,414 字符，full:646 区域）与 `principal_contradictions[0]`（1,897 字符，full:939 区域）是同一 `contradiction_id: RATE_VS_EARNINGS_ABSORPTION` 的两个版本，JSON 序列化后 difflib 相似度 0.721；「输入」说明将后者登记为"Bridge 主要矛盾候选"（full:56 区域）。两版的 transformation_signals 是同样 3 个信号的不同表述； unresolved_questions 分别为 4 条与 3 条，内容近似但无一条逐字相同。
证据：
```
$ python3: difflib.SequenceMatcher(a, b).ratio()
thesis_principal_contradiction chars: 2414 | principal_contradictions[0] chars: 1897
similarity: 0.721
```

### F-09 unresolved_questions 同内容三处共存、逐字互不相同
事实：`thesis_principal_contradiction.unresolved_questions`（4 条，full:696）、`principal_contradictions[0].unresolved_questions`（3 条，full:990）、顶层 `unresolved_questions`（12 条，full:6609 起，含 5 条带 `[M1]` 后缀的"缺材料"条目和 2 条事件相关条目）三处并存。程序比对：Bridge 版 3 条在顶层 12 条中**无一逐字命中**（均为近似改写，如 flagged 权重一处写"41%"、另一处写"30d flagged权重41%，90d 51%"）。
证据：
```
$ python3: q in q3 逐条判定
bridge q 是否在顶层列表中: False | 盈利修正斜率+4.2%的置信度受supplier_lookback影响（flag…（×3 均 False）
```

### F-10 六个键到达但未在「输入」说明中登记
事实：「输入」说明（full:46-67）列举了 21 组关键字段；实际 42 键中以下 6 个未被提及：`retained_conflict_types`（full:422）、`key_event_refs`（full:6567）、`evidence_registry_summary`（full:6568）、`pricing_expectation_ledger`（full:6588）、`unresolved_questions`（full:6609）、`revision_summary`（full:6637）。其中 `revision_summary` 是 reviser **自己输出契约的必填字段名**（full:6643），在输入里以 `null` 出现。

### F-11 pricing_expectation_ledger 自带"禁用"标记却进了输入
事实：该键（full:6588-6601）自带 `"usage_rule": "pricing_narrative_support_only; forbidden_as_core_ref"`（full:6599）、`"status": "audit_only_effective_date_mismatch"`（full:6600），且其 `effective_date: 2026-07-31` 与 `packet_effective_date: 2026-07-30` 不一致（meta.json 记本 run effective_date 为 2026-07-30）；downgrade_rules 含 "must_not_enter_l1_l5_raw_prompt_or_evidence_ref"。

### F-12 指令要求消费的三方反馈，实际为空或仅有 275 字符
事实：修订原则 3"修复结构问题"与 Step 1"理解 Schema Guard 的结构问题"（proj:186-191、218）对应的材料是三个空数组：`schema_structural_issues/consistency_issues/missing_fields: []`（proj:1061-1063，`schema_passed: true`，内部自洽）。修订原则 1"接受有效批评"列举了批评类型（数据引用错误/逻辑跳跃/过度自信，proj:172-175），但 `critique_cross_layer_issues: []`（proj:5347），`critique_overall` 仅 275 字符且结论是"**未发现重大逻辑断裂或证据矛盾**……不足以推翻防御立场"（proj:5346；省略的 93 字符已回查原文，为"幸存的最强反对意见：盈利修正斜率 30d +4.2% 与 90d +10.7% 方向性一致……"）。

### F-13 "high_severity_typed_conflicts" 名实不符；retained_conflict_types 与其对不上
事实：该字段 3 条中只有 1 条 `severity: high`（L1_L4_valuation_compression），另 2 条为 medium（full:859-986；程序输出见下）——而「输入」说明称它是"必须在最终报告中保留的**高严重度**跨层冲突"（full:59 区域），「必须遵守」要求"保留所有 high severity 冲突"（proj:283）。另外 `retained_conflict_types`（full:422-427）4 个标签中：`technical_bounce_vs_weak_breadth` 与 typed conflicts 里的 `technical_vs_fundamental_breadth` 不同名；`growth_assumption_vs_rate_headwind` 没有任何对应 typed conflict。
证据：
```
$ python3 遍历 high_severity_typed_conflicts
L1_L4_valuation_compression | severity: high | type: rate_vs_valuation | status: confirmed
L2_L4_credit_vs_earnings | severity: medium | type: credit_tail_vs_earnings_momentum | status: unresolved
L5_L3_oversold_vs_structure | severity: medium | type: technical_vs_fundamental_breadth | status: unresolved
retained_conflict_types: ['rate_vs_valuation', 'credit_tail_vs_earnings_momentum', 'technical_bounce_vs_weak_breadth', 'growth_assumption_vs_rate_headwind']
```

### F-14 事件证据通道整体为空，但两条规则在管它
事实：`key_event_refs: {}`（full:6567）；全树扫描所有 `event_refs` 数组，**0 处非空**。而证据引用纪律有 "event_refs 只能作催化剂、背景或观察事项"（proj:84），synthesis_guidance 有 "event_refs 与 evidence_refs 分离"（proj:5344）。同时 `evidence_registry_summary` 称上游共有 72 条 event 护照（full:6568-6587：`"by_kind": {"data": 120, "event": 72, ...}`，passport_count 198，downgrade_count 80）。

### F-15 synthesis_guidance 引用多个材料里不存在的键，且措辞对象是 Thesis 不是 Reviser
事实：synthesis_guidance（full:6623-6633 区域，10 条）中：`competing_hypotheses`、`hypothesis_competition_summary`、`evidence_index`（材料只有其子集 key_evidence_refs）、`bridge_summaries`、`final_claim_ledger` 经程序核对均不在 governance_input 中；"必须保留 **high_severity_conflicts**" 与实际键名 **high_severity_typed_conflicts** 不一致。措辞上："**Thesis** 只能整合 synthesis_packet，不得重新分析原始指标"、"**Thesis / Final** 的重要自然语言结论会进入 final_claim_ledger"——主语均为 Thesis。
证据：
```
$ python3 键存在性核对
competing_hypotheses -> False
hypothesis_competition_summary -> False
evidence_index -> False
bridge_summaries -> False
final_claim_ledger -> False
high_severity_conflicts -> False  (实际键 high_severity_typed_conflicts -> True)
```

### F-16 假说只有"回应"没有"假说"：无原文、无状态字段
事实：`thesis_hypothesis_responses` 3 条（hyp_base_88ece56ecb / cth_01 / cth_02）每条仅含 `hypothesis_id / verdict / reasoning / evidence_refs` 四个键（程序输出见下）——没有假说原文，也没有 `candidate/leading/kept_unresolved/split` 状态字段。而硬合约要求按状态区别处理："对应 `kept_unresolved` 假说的回应允许是 `absorb_partially`"（proj:74），并声明列表"覆盖 Thesis 阶段所有非 downgraded 状态的竞争假说"（proj:70）。reviser 从这份材料里无法核对任一假说的状态，只能看到 reasoning 里的一句转述。
证据：
```
$ python3: for h in thesis_hypothesis_responses: print(sorted(h.keys()))
hyp_base_88ece56ecb keys: ['evidence_refs', 'hypothesis_id', 'reasoning', 'verdict']
cth_01 / cth_02 同上
```

### F-17 系统级约束引用的字段名在本站材料中不存在
事实：System Message 约束 4："所有 evidence_refs 必须来自本次输入的 **raw_data**"（full:9）——全 prompt 中 raw_data 仅出现这一处，governance_input 无此键（本站实际引用源是 `key_evidence_refs`，见用户消息 proj:79）。约束 5 的 `NO_DATA_AVAILABLE`（full:10）在输入中也未出现。
证据：
```
$ grep -c "raw_data" full/reviser/attempt_1.prompt.txt -> 1（即系统消息该行）
$ grep -c "NO_DATA_AVAILABLE" full/reviser/attempt_1.prompt.txt -> 1（同上）
```

### F-18 任务书示例里的 evidence_refs 全部不在索引中
事实：「修订示例」的 key_support_chains 示例使用 `L1.real_rate`、`L4.pe_ratio`、`L4.erp`（full:295）、`L3.ndx_ndxe_ratio`、`L3.advance_decline_line`（full:300）——逐字核对全部不在索引 30 键中（真实形态为 `L1.get_10y_real_rate`、`L3.get_ndx_ndxe_ratio` 等）。证据引用纪律明确"看到字段名不代表 `parent#field` 是合法 ref"（proj:81），示例本身的 ref 形态与合法形态不符。
证据：
```
$ python3: 示例 5 个 ref in keys -> 全 False
```

### F-19 输出契约双份并存、细节不交圈；输入/输出置信度键名不同
事实：任务书「输出格式」段给了一份完整示例 JSON（full:69-124），尾部又有「输出字段规格（由 AnalysisRevised 契约自动生成，形状以此为准）」（full:6641-6648），Response Rules 声明"形状冲突时以规格为准"（full:6654）。两处差异：示例含 `"overall_confidence": "medium"`（full:112），规格的 ThesisDraft 字段枚举以 `…}` 收尾、未显式列出 overall_confidence（full:6646）。另：输入键名 `thesis_confidence`（"medium"）与输出键名 `overall_confidence` 的映射任务书未提及。

### F-20 防火墙摘要的 unresolved_tensions 与 typed conflicts 互为复制
事实：`objective_firewall_summary.unresolved_tensions` 4 条（full:1003-1007）中，前 3 条逐字复制 `high_severity_typed_conflicts` 的 description（full:865 等区域），第 4 条 "rate_vs_valuation: …" 是 typed conflicts 之外的第 4 段冲突文本（且其描述词用"（中等）"，与复制段的"（中等偏高）"并存，见 F-07）。

### F-21 reader_conclusion 是三个 thesis 字段的大白话改写副本
事实：`thesis_reader_conclusion`（2,631 字符，full:544-645 区域）内的 time_horizon_summary（3 条）、action_summary（3 条）、invalidation_summary（3 条）与 `thesis_time_horizon_views`（2,150 字符）、`thesis_portfolio_actions`（1,515 字符）、`thesis_invalidation_conditions`（310 字符）逐条一一对应，内容为口语化改写（如"保持防御性低配"→"保持防御，暂不加仓"）。同批判断以正式版+大白话版两种形态并存于输入。

### F-22 slope_30d 条目内部重复登记；投影对同类数组处理不一
事实：slope_30d 内 `flagged` 列表 42 条与 `constituents` 97 条中 `flagged=true` 的 42 条 **ticker 集合完全相同**（程序验证），是同批股票的两次登记（flagged 列表字段是 constituents 字段的子集：ticker/weight_pct/slope/reasons/earnings_dates）。另外 12 个季度的 capex 汇总在 `by_calendar_quarter` 全量列出后，`latest_covered_quarter`/`prior_covered_quarter` 又把其中两季整季重复一遍（full:1992-2071）。投影层观察（不影响原文事实）：slope_30d 的 97 行非标量 constituents 在投影中全量保留（约 2000 行），而 breadth_30d 的 103 行表被 `__table_projection__` 截断（proj:2214、2284，共 2 处）——同构大数组在投影里一种全留、一种截断。
证据：
```
$ python3 集合比对
slope_30d: flagged 列表 42 条; constituents 97 条，其中 flagged=true 42 条
flagged 列表 ticker 集合 == constituents flagged=true 集合: True
$ grep -c "__table_projection__" proj… -> 2
```

### F-23 known_data_gaps 末条混入一条 risk_flag
事实：`known_data_gaps`（full:6602-6607）前 4 条均为不可用数据函数（如 "get_cftc_nq_positioning 不可用…"），第 5 条是 `"[L3] narrow_breadth"`——这是 L3 条目的 risk_flag 形态（对比 proj:1430 `"risk_flags": ["narrow_breadth"]`），不是数据缺口。

## 盲区

1. **breadth_30d 的 103×2 行成分表原文未逐行回查**：投影只保留 head 3 + tail 1 + min/max 统计（proj:2214-2266、2284-2336）。判断它与 reviser 职责无关、结构风险低，未回 full/ 逐行核对；若需核对该表内部一致性（如 weight_pct 合计），需补查。
2. **payload.json（280,046 字节）未读**：它与 prompt.txt 的关系（是否仅多模型参数、是否含 prompt 之外的 system 字段）未核对。
3. **response.raw.txt / output.validated.json 未逐字读**：本阶段定位是"材料结构对不对"，不评价站产出；parsed.normalized.json 仅用于确认输出契约形状（revised_thesis 20 键齐全）。
4. **投影保真度只做了定点抽查**：12 处 «…省略» 散文我全部回查了原文（见 F-04/05/06/12 所引完整字符串），但未对投影与原文做全文 diff；manifest 记 `verification_ok: true`。
5. **索引之外的上游不可见**：key_evidence_refs 声明是 `synthesis_packet.evidence_index` 的子集（proj:79）。F-04 中"散文有数字、索引无条目"的现象，我无法区分是"子集筛选时被筛掉"还是"上游本来就没有该条目"——其他站的材料不在本任务范围。
6. **Critic/Risk/Schema 三方的完整产出不可见**：reviser 只收到压缩后的 critique_overall（275 字符）等字段；压缩是否保真（例如 Critic 原文是否真没有跨层问题）无法从本站材料核对。
7. **数值只核对了"材料内自洽性"**：如 PE 30.31 vs 29.4 哪个对、41.66% 分位的出处，需回到上游 L4 数据工件核对，超出本站语料范围，我不断言哪边是错的。
