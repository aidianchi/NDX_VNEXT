# integrated_adjudicator 通读报告

站：integrated_adjudicator（实例 20260730T165426Z，attempt_1）
语料根：`output/analysis/vnext/20260731_002156/context_spread/`
manifest 备注：`inspector_has_rules: false`、`inspector_can_read: false`（这站此前连机械检查规则都没有）。

## 通读范围

- 投影：`projected/integrated_adjudicator/20260730T165426Z/attempt_1.projection.md`，524 行 / 23,771 字符（占原文 94.9%），**全读**，含头部段落目录。
- 原文：`full/integrated_adjudicator/20260730T165426Z/attempt_1.prompt.txt`，523 行 / 25,056 字符（44,022 字节），**全读**。
- 投影三处截断全部到原文核对过：
  - `reasoned_verdict` 中段 «…省略 1292 字符…»（投影第 68 行 → 原文第 52 行，整段读完）；
  - `principal_contradiction.why_principal` «…省略 78 字符…»（投影第 72 行 → 原文第 56 行）；
  - `payoff_assessment` «…省略 238 字符…»、`priced_narrative` «…省略 234 字符…»（投影第 165-166 行 → 原文第 149-150 行）；
  - `allowed_data_refs` 中段 `__omitted__: 19 / __total__: 34`（投影第 178-181 行 → 原文第 151-186 行，34 项全部读到）；
  - MSFT 事件卡 `fact_summary`/`interpretation` 各 «…省略 120 字符…»（投影第 327-328 行 → 原文第 326-327 行）。
- 读法：投影与原文均 100% 逐行通读，无抽查；另用 python3 脚本对 JSON 块做结构化核对（脚本与输出见各发现条目）。

## 材料结构总览

段落目录（投影第 6-13 行）：

| 段落 | 字符 | 占比 |
|---|---|---|
| `# 第三层综合裁决人`（任务书） | 246 | 1.0% |
| `## 不可逾越的边界`（规则） | 828 | 3.3% |
| `## 你要输出的 JSON 字段`（输出规范） | 1,622 | 6.5% |
| `## 降级规矩` | 171 | 0.7% |
| `## 输出格式` | 570 | 2.3% |
| `## 本轮输入`（数据材料，一个 JSON 块） | 21,619 | 86.3% |

输入 JSON 内各顶层键字符量（python3 `json.dumps` 实测，命令见发现 0 附注）：

- 数据层判决本体（final_stance/reasoned_verdict/principal+secondary_contradictions/must_preserve_risks/invalidation_conditions/payoff_assessment/priced_narrative）：约 6,022 字符
- 白名单两块（allowed_data_refs 1,046 + ref_authority 1,493）：2,539 字符
- 事件卡 10 张（event_interpretation_cards）：8,713 字符（其中 3 张自述"关联不足"的卡 2,248 字符，占 25.9%）
- 调查报告 2 份（investigation_reports）：975 字符
- 跨层问题 7 道（cross_layer_questions）：737 字符
- 其余（effective_date/approval_status/confidence/cards_empty/allowed_investigation_ids）：约 93 字符

解读：任务书+规则+输出规范合计约 3.4k 字符（13.7%），数据材料 21.6k（86.3%）。数据材料里**事件卡（8.7k）比数据层判决本体（6.0k）还大**——而这站职责是"数据判决是锚"，事件材料按规则只能作解释线索。

## 发现清单

### 总览附注（材料结构总览的字符量来源）

命令（在 `full/integrated_adjudicator/20260730T165426Z/` 下执行）：

```bash
python3 - << 'EOF'
import json, re
raw = open('attempt_1.prompt.txt', encoding='utf-8').read()
js = json.loads(re.search(r'```json\n(.*)\n```', raw, re.S).group(1))
for k,v in js.items(): print(k, len(json.dumps(v, ensure_ascii=False)))
EOF
```

输出（节选）：`reasoned_verdict: 1482`、`principal_contradiction: 2390`、`secondary_contradictions: 932`、`must_preserve_risks: 453`、`invalidation_conditions: 330`、`payoff_assessment: 420`、`priced_narrative: 416`、`allowed_data_refs: 1046`、`ref_authority: 1493`、`event_interpretation_cards: 8713`、`investigation_reports: 975`、`cross_layer_questions: 737`，合计 19,541（不含键名与缩进）。

---

### 发现 1：ref_authority 权限标签体系与规则文本不匹配

事实：规则段只定义了 `audit_only` 和 `supporting_only` 两档的用法；实际输入里 34 个 ref 的权限值为：`unknown` 23 个、`supporting_only` 6 个、`core_allowed` 5 个、`audit_only` 0 个。规则全文未出现 "unknown" 和 "core_allowed" 的语义说明。被边界规则树为"锚"、且在判决散文中引用最多的 `L1.get_10y_real_rate`，标的正是 `unknown`。

证据：
- 规则原文（`attempt_1.prompt.txt:14`，`grep -n audit_only`）："标为 audit_only 的 ref，其数值不得作为正文论据、不得进入 `data_support` 和 `current_phenomena`（引用时必须带"仅审计参考"限定语）；supporting_only 的 ref 只能作辅助佐证，不能独立支撑结论。"
- 标签统计（python3 `collections.Counter(js['ref_authority'].values())`）：`Counter({'unknown': 23, 'supporting_only': 6, 'core_allowed': 5})`。
- `attempt_1.prompt.txt:188`：`"L1.get_10y_real_rate": "unknown",`。

### 发现 2：指令要求按 ref 引数据，输入里却没有按 ref 组织的数据观测

事实：指令要求 `data_support`、`current_phenomena`、三条主要论证的方括号标注都挂 ref（如 `[L1.get_10y_real_rate]`），`conflict_matrix.data_side_refs` 也必须是具体 data ref。但输入中不存在任何"ref → 数值/观测"的数据摘要结构；全部数据值嵌在第一层判决的散文（reasoned_verdict、principal_contradiction 等）里。34 个白名单 ref 中，20 个的 ref 名在 `allowed_data_refs`/`ref_authority` 两个清单之外从未出现；其中 11 个在全文（含散文）中连对应该指标的数值或描述都找不到：`L5.get_obv_qqq`、`L2.get_vxn`、`L4.get_ndx_wind_valuation_snapshot#PB`、`L4.get_ndx_wind_valuation_snapshot#PS`、`L4.get_ndx_earnings_revision_metrics#breadth_30d`、`L5.get_atr_qqq`、`L1.get_m2_yoy`、`L1.get_fed_funds_rate`、`L2.get_ig_oas_bp`、`L2.get_vix_term_structure`、`L1.get_fed_funds_rate_path`。

证据：
- 指令原文（`attempt_1.prompt.txt:25`）："data_support 只放输入"允许引用的 data refs 清单"里出现过的 ref"；`:28`："`data_side_refs` 必须是具体的 data ref"。
- 20 个未点名 ref（python3：从 JSON 中剔除两个清单键后搜索各 ref 名，输出原文照抄）：`L5.get_obv_qqq / L2.get_vxn / L4.get_m7_capex_cycle#m7_aggregate / L4.get_damodaran_us_implied_erp / L3.get_ndx_ndxe_ratio / L3.get_qqq_top10_concentration / L5.get_donchian_channels_qqq / L2.get_hy_oas_bp / L5.get_volume_analysis_qqq / L4.get_ndx_wind_valuation_snapshot#PB / #PS / L4...#breadth_30d / L5.get_atr_qqq / L1.get_m2_yoy / L1.get_fed_funds_rate / L4...#slope_90d / L4.get_m7_earnings_blackout_calendar / L2.get_ig_oas_bp / L2.get_vix_term_structure / L1.get_fed_funds_rate_path`。（其中 9 个虽无 ref 名但有散文数值，如 capex +75%、Donchian 下轨 661.14、90 日 +10.7%。）
- 11 个无值 ref 的关键词搜证（python3 按 OBV/VXN/PB/PS/breadth/ATR/M2/联邦基金/IG/VIX/降息概率 逐行搜索）：OBV、ATR、M2、IG、VIX 零命中；VXN 仅出现在问题句（`:503`）中无数值；PB/PS/breadth/fed_funds 仅命中两个清单自身的行；"降息概率/基金期货"仅命中事件卡 `needs_data_confirmation`（`:402`，即作为"缺的数据"出现，不是作为数据出现）。

### 发现 3：事件层材料以"仅标题无正文"为主，有实质内容的两张自述与判断对象无关

事实：10 张事件卡中 8 张在 `limitations`/`fact_summary` 自述仅标题或无正文；MSFT 卡自述"仅提供摘录，非全文"；仅 2 张美联储执法公告卡（event:4a41774d6a5c953b、event:82d5d8fb4b9d331a）有完整事实陈述，而这 2 张的 interpretation 首句均为"与判断对象关联不足"。另有 K2 Space 卡（event:1d77a2d1bb9e1d35）同样自述"与判断对象关联不足"。3 张"关联不足"卡合计 2,248 字符，占事件卡块 8,693 字符的 25.9%。本站核心动作一是"把数据判决和外部世界放进同一张桌子上对质"，`conflict_matrix` 要求每张卡一行。

证据：
- 任务书（`:3-5`）："你的任务…1. 把数据判决和外部世界放进同一张桌子上对质"；conflict_matrix 规范（`:28`）："每张事件卡一行"。
- 自述仅标题/无正文（`sed -n` 抽取，原文照抄）：`:271` "仅有标题可用，无完整正文…"、`:292` "仅有标题，无正文摘录可用…"、`:317` "仅有标题可读，无正文内容…"、`:342` "仅提供摘录，非全文"、`:407` "仅有标题摘要，无全文内容可用…"、`:455` "仅有标题可用，无正文全文…"；另 `:230` fact_summary "材料仅包含标题与来源元数据，无正文摘录可用"。
- 关联不足（`grep -n 与判断对象关联不足`）：`:281`、`:352`、`:370` 三处，均为 interpretation 首句。
- 字符统计（python3 `json.dumps` 逐卡）：3 张关联不足卡 2,248 字符 / 全部 10 卡 8,693 字符。

### 发现 4：MSFT 事件卡 interpretation 在原文中被截断于词中；该卡为英文，与其余 9 张中文卡语言不一

事实：event:b8f43b7603daa04c 的 `interpretation` 字段在原文第 327 行以 "…index weight postin" 结束——句子在单词中间断开，后接引号闭合。这不是投影伪影（投影对应处有 «…省略 120 字符…» 标记，核对原文后确认断点就是材料本身的断点）。同卡 `fact_summary`/`interpretation` 为英文，其余 9 张卡均为中文；输出格式要求"全部输出必须使用中文"。

证据：
- `attempt_1.prompt.txt:327`（`grep -n postin`）：`"interpretation": "MSFT's earnings report shows strong top-line growth, … For NDX, MSFT as the largest or near-largest index weight postin",`
- 投影第 328 行对应位置有 `«…省略 120 字符…»`，原文核对后确认截断在 "postin"。
- 中文要求：`:39` "全部输出必须使用中文（evidence_ref 与 event_id 保持原文）"。

### 发现 5：事件卡引用的假设 ID 在输入中无定义（悬空引用之一）

事实：事件卡的 `supports_hypotheses`/`refutes_hypotheses` 共引用 3 个假设 ID：`hyp_base_88ece56ecb`（event:75be…、event:39356…）、`cth_01`（event:75be…、7392…、b8f4…、d612…、0a45…）、`cth_02`（event:75be…）。这些 ID 在事件卡块之外的输入全文中没有任何定义或文本——本站在材料里无法知道每条假设的内容。

证据：
- python3：收集全部卡的 supports/refutes 得 `{'cth_02', 'hyp_base_88ece56ecb', 'cth_01'}`，在剔除 `event_interpretation_cards` 块后的原文中搜索，三者均 `False`（未出现）。
- 出现位置示例：`attempt_1.prompt.txt:259-265`（event:75be16e97675b582 的 supports/refutes）。

### 发现 6：调查报告引用输入中不存在的材料键 [M1]，且与"跨层问题"的声明对不上（悬空引用之二 + 声明与现实矛盾）

事实：(a) 两份调查报告的 finding/claims/cannot_establish 中共 9 处标注 `[M1]` 作为材料来源，但输入中不存在名为 M1 的材料或图例。(b) 调查报告对象没有 `question_id` 字段（键仅 investigation_id/finding/claims_supported/claims_challenged/cannot_establish/confidence）。(c) 任务书引言称"受控调查员对若干跨层问题交来了调查报告"，但两份报告的主题——M7 回购 -68.74% 是季节性还是趋势、盈利修正 supplier_lookback flagged 权重 41%/51%——逐字对应的是 `principal_contradiction.unresolved_questions` 第 1、3 条，而非 7 道 `cross_layer_questions` 中的任何一道；`question_answers` 规范（`:27`）又允许答案引用 `investigation_refs`。

证据：
- [M1] 9 处（`grep -n M1`）：`:466`、`:468`、`:472`、`:473`、`:479`、`:481`、`:485`、`:486`、`:487`，例：`:479` "…既无法确认数据质量可靠，也无法确认或挑战财报静默期导致失真。 [M1]"。
- 引言（`:3`）："受控调查员对若干跨层问题交来了调查报告。"
- 对应判决未决问题（`:104`）："盈利修正30日斜率+4.2%的置信度受supplier_lookback影响（flagged权重41%）…"；`:106`："M7回购同比-68.74%是capex优先战略的结构性转变还是包含季节性因素？…"
- 报告键列表（python3 `list(r.keys())`）：无 question 相关字段。

### 发现 7：任务书第 2 条只提单向问题，实际输入含反向题；question_answers 规范无事件侧引用通道

事实：任务书三件事的第 2 条写"逐条回答'新闻事件给数据层出的题'"（事件→数据单向）。实际 `cross_layer_questions` 7 道中有 2 道反向题（数据→事件）：`question:data_to_event:index_strength_breadth_gap`、`question:data_to_event:expensive_but_resilient`，题干分别是"…新闻事件里是否有少数大权重公司或半导体事件在支撑指数？"、"…新闻事件里是否有盈利上修、回购、资金流或政策预期解释？"。输出规范（`:27`）要求"对输入里每一道 cross_layer_question 各回答一次"且"答案必须引用 data_refs 或 investigation_refs"——规范只给数据侧和调查侧两种引用通道，没有事件卡引用通道。

证据：
- 任务书（`:6`）："2. 逐条回答"新闻事件给数据层出的题"。"
- 反向题（`grep -n data_to_event`）：`:514`、`:518`。
- 引用规范（`:27`，原文照抄）："答案必须引用 data_refs 或 investigation_refs，凭空作答等于违规。"

### 发现 8：数值矛盾——收益差距 -1.21% 与同句给出的两个构成值算不齐

事实：`reasoned_verdict` 第二段："简式收益差距为-1.21%——盈利收益率3.3%甚至低于10年期美债利率4.61%"。按同句给出的两个构成值计算：3.3% − 4.61% = −1.31%，与句中声明的 −1.21% 差 0.1 个百分点。材料未给出更高精度的构成值，无法从输入判断是舍入还是笔误。另：同段 "Trailing PE 30倍" 与 principal_contradiction 多处 "Trailing PE 30.31倍" 并存（精度不一致）。

证据：
- `attempt_1.prompt.txt:52`（`grep -n '3.3%甚至低于'`）："…而简式收益差距为-1.21%——盈利收益率3.3%甚至低于10年期美债利率4.61%，安全垫为负。"
- "30倍"同处 `:52`；"30.31倍"见 `:58`（secondary_side）、`:77`（transformation_signals[0].implication）。

### 发现 9：invalidation_conditions 第 5 条方向标签与内容相反

事实：该条以【转空】开头，内容却是"价格放量突破VWAP（702.73）且A/D线同步回升、%Above50d回升至60%以上"并"转向'趋势可能反转'"——向上突破加广度修复被标成"转空"。此为上游第一层判决自带内容，经输入原样进入本站；本站指令要求 `principal_contradiction`/`falsifiers` 等"从数据判决继承…不可改变实质"。

证据：
- `attempt_1.prompt.txt:147`（`grep -n '【转空】价格放量突破'`，原文照抄）：`"【转空】价格放量突破VWAP（702.73）且A/D线同步回升、%Above50d回升至60%以上——'反弹空间有限'的判断失效，转向'趋势可能反转'"`
- 对照同块另两条【转空】（`:145-146`）：内容均为下跌/转负方向。
- 继承要求（`:24`）："principal_contradiction / principal_aspect：主要矛盾与当前主导面（从数据判决继承…不可改变实质）。"

### 发现 10：结构性冗余三处

事实：
- (a) `principal_contradiction.transformation_signals` 的 3 条 `signal` 与 `invalidation_conditions` 前 3 条逐字重复——signal 原文作为 invalidation 条目的前缀出现，后者只多失效含义后缀。例：signal "实际利率从2.41%回落至2.0%以下（约90%分位）且持续两周"（`:84`）与 invalidation "【转多】实际利率从2.41%回落至2.0%以下（约90%分位）且持续两周——'估值压缩为主'的判断失效…"（`:143`）。
- (b) `allowed_data_refs`（34 项，1,046 字符）与 `ref_authority`（34 键，1,493 字符）键集完全相同（python3 集合比较 `set(refs)==set(auth)` 为 `True`，双向差集为空），同一批 ref 名在输入中出现两遍；加上各 `evidence_refs` 子集，部分 ref 名（如 L1.get_10y_real_rate）在输入中出现 5 次以上。
- (c) "不可信引用材料"免责说明出现两次，内容几乎逐字：`:15`（边界第 5 条）与 `:44`（JSON 块前的说明）。

证据：
- python3 逐条打印 transformation_signals 与 invalidation_conditions（输出见通读过程，signal 与 invalidation 前缀逐字相同）。
- 集合比较：`in allowed not in auth: set()`、`in auth not in allowed: set()`。
- `grep -n 不可信引用材料`：`:15`、`:44` 两处。

## 盲区

- **无未核对的投影截断**：本投影三处截断类型全部到 full/ 原文核对（reasoned_verdict 1,292 字符、why_principal 78、payoff_assessment 238、priced_narrative 234、allowed_data_refs 中段 19 项、MSFT 卡两处各 120 字符）。投影对原文覆盖率 94.9%，缺失 5.1% 已全部补读。
- **未读站产出**：`full/integrated_adjudicator/20260730T165426Z/attempt_1.response.raw.txt` 未读——本任务审"材料结构"，不审站产出；发现 8、9 的矛盾是否实际影响了产出，不在本片范围。
- **未溯上游**：发现 3、4、6、9 涉及的材料（事件卡、调查报告、第一层判决）在上游站是如何生成的，未读上游站（final_adjudicator、event_card_interpreter.*、controlled_investigation）的提示词，只能确认这些事实以原文形态进入了本站输入。调查报告里 [M1] 指向什么材料，从本站输入无法得知。
- **数字仲裁未做**：发现 8 的 0.1pp 差异是舍入还是笔误，材料内无法判定，未引入外部数据核实（红线：只用输入内材料）。
