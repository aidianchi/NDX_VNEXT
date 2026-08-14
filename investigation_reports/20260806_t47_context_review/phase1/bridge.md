# bridge 通读报告

站：`bridge`（attempt_1）；run：20260731_002156；manifest 记录：prompt_chars=112,814，projection_chars=112,597（99.8%），`inspector_has_rules=true`。

## 通读范围

- 主读材料：`context_spread/projected/bridge/attempt_1.projection.md`，全文 3,275 行 / 158,260 字节（`wc -l -c` 实测），**逐行全读**，分 6 个连续区段读完（行 1–120、121–800、801–1500、1501–2200、2201–2900、2901–3275）。
- 原文对照：`context_spread/full/bridge/attempt_1.prompt.txt`（3,171 行 / 156,930 字节）。投影中全部 6 处 «…省略 N 字符…» 截断标记（行 1050、1051、2077、2552、2553、3218，均为 layer_synthesis / internal_conflict_analysis 散文中段）已逐一在原文中取出全文核对，见"盲区"节。
- 索引：`context_spread/manifest.json` 已读（确认本站原文/投影字符数、机械检查规则存在）。
- 字符量统计口径：用 python3 对投影全文按节标题切分统计；对 Runtime Input 的 JSON 用 `json.loads` 解析后按键统计（compact 序列化），另用原文偏移量计算各 layer card 在 pretty-print 原文中的实际占位。
- 未读：attempt_1.parsed.normalized.json、attempt_1.payload.json、attempt_1.response.raw.txt、output.validated.json（任务边界是"提示词材料结构"，不含产出；payload 与 prompt 的差异不在本片范围）。

## 材料结构总览

原文 112,814 字符，按节标题切分（命令：`python3` 对 `full/bridge/attempt_1.prompt.txt` 按节标题 `str.find` 切分统计）：

| 区块 | 字符 | 占比 |
|---|---|---|
| System Message（系统级约束 6 条） | 351 | 0.3% |
| vNext v2 Bridge Contract（契约散文） | 1,509 | 1.3% |
| 角色定义（NDX Agent vNext 标题+角色） | 384 | 0.3% |
| ## 输入（声明的输入清单） | 538 | 0.5% |
| ## 输出格式（JSON 模板） | 2,388 | 2.1% |
| ## Bridge 类型（三类桥） | 391 | 0.3% |
| ## 分析流程（Step 1–5 + 升格纪律 + 冲突矩阵） | 1,760 | 1.6% |
| ## 关键约束（绝对禁止/必须遵守） | 822 | 0.7% |
| ## 质量检查清单 | 381 | 0.3% |
| ## 场景示例（三个完整 JSON 示例） | 2,173 | 1.9% |
| ## 事件引用 (event_refs) | 538 | 0.5% |
| **## Runtime Input（数据材料）** | **98,533** | **87.3%** |
| ## 输出字段规格（BridgeMemo 契约自动生成） | 2,514 | 2.2% |
| ## Response Rules | 516 | 0.5% |

任务书+规则合计约 11,231 字符（9.9%），数据材料 98,533 字符（87.3%），输出形状定义两处合计 5,418 字符（4.8%，含 Response Rules）。

Runtime Input 内部（原文偏移量切分，pretty-print 含缩进空白）：

- `context_brief`：2,022 字符（含 `layer_highlights` 1,269 字符 compact、`apparent_cross_layer_signals` 97、`special_attention` 97、`task_description` 68、`data_summary` 32、`generated_at` 29）。
- `candidate_cross_layer_links`：1,027 字符，3 条链接（L1_L4、L3_L5、L1_L5）。
- `layer_cards` 五张卡合计约 95,434 字符：L1 18,507（9 个 indicator_analyses）、L2 22,312（13 个）、L3 13,105（6 个）、L4 18,509（9 个）、L5 23,001（11 个）。五卡覆盖面均衡，最大/最小比约 1.76。

段落目录解读：这站材料=一份约 1.1 万字符的"测绘员任务书"+五张完整 LayerCard（每层含 core_facts、local_conclusion、cross_layer_hooks、indicator_analyses、layer_synthesis、internal_conflict_analysis、quality_self_check、notes 全套字段）+ 一个契约开头没有声明的 `context_brief` 摘要块 + 3 条候选跨层链接。契约要求的四类消费对象（indicator_analyses、layer_synthesis、internal_conflict_analysis、cross_layer_hooks）在五张卡里全部实际存在且非空；`data_summary` 称"47/50 个指标成功"，与卡内覆盖（48 个 function_id 有 analyses，其中 get_cftc_nq_positioning 标记不可用；另有 2 个 L4 指标在 quality_self_check 里标 unavailable/disabled）算术自洽。

## 发现清单

（每条：标题 + 证据 + 事实描述；不定级、不开方。行号无特别说明时指 `projected/bridge/attempt_1.projection.md`。）

### 1. 同三句"成品"跨层判断在 Runtime Input 中逐字出现三次，且排在 layer_cards 之前

证据：
```
$ grep -n "流动性收紧与高估值并存\|广度走弱但价格趋势仍强\|环境偏紧但趋势仍强" projected/bridge/attempt_1.projection.md
506:      "流动性收紧与高估值并存，估值压缩风险需要在桥接阶段被显式检验。",
507:      "广度走弱但价格趋势仍强，趋势质量与集中度风险需要被单独讨论。",
508:      "环境偏紧但趋势仍强，需确认价格是否只是延迟反应。"
512:      "流动性收紧与高估值并存，估值压缩风险需要在桥接阶段被显式检验。",
513:      "广度走弱但价格趋势仍强，趋势质量与集中度风险需要被单独讨论。",
514:      "环境偏紧但趋势仍强，需确认价格是否只是延迟反应。"
520:      "description": "流动性收紧与高估值并存，估值压缩风险需要在桥接阶段被显式检验。",
531:      "description": "广度走弱但价格趋势仍强，趋势质量与集中度风险需要被单独讨论。",
542:      "description": "环境偏紧但趋势仍强，需确认价格是否只是延迟反应。"
```
事实：行 506–508 是 `context_brief.apparent_cross_layer_signals`，行 512–514 是 `context_brief.special_attention`（两处逐字相同，各 97 字符 compact），行 520/531/542 是 `candidate_cross_layer_links` 三条链接各自的 `description`（再次逐字相同）。即同三句已写成判断句的跨层结论（估值压缩风险、趋势质量/集中度、价格延迟反应），以三种不同字段身份重复三遍；它们位于 Runtime Input 开头（行 505 起），五张 layer_cards 从行 551 才开始。Bridge 的任务书（行 79）是"读取所有 Layer Cards，识别层与层之间的支撑关系和冲突"，材料在原始数据之前预置了结论候选。

### 2. context_brief 未在"## 输入"清单中声明，且其 layer_highlights 是 core_facts 的压缩副本（两处小出入）

证据：
- 行 87–101（Read 输出）："## 输入"清单只有两项——"1. 5 个 Layer Cards…2. 候选跨层关系（来自 analysis_packet.json）"，无 context_brief。
- 行 473–516：Runtime Input 的第一个键就是 `context_brief`，含 `layer_highlights`（compact 1,269 字符，按 L1–L5 各挑 3 条指标压缩成"指标名|值|分位|趋势"字符串）。抽查数值与卡内一致（如行 482 "10Y Real Rate | 值=2.41 | 分位=99.35974389755903" vs 行 654–665 卡内 2.41% / 99.4）。
- 出入一：行 490 "NDX/NDXE Ratio | 值=2.7861 | 分位=90.0517309988062 | **趋势=below**"；卡内同指标（行 1748–1752）`trend: "falling"`，"below" 实为 raw_data.ratio_trend_vs_ma20 的位置标记（行 1755）。
- 出入二：行 495 Damodaran 高亮的"值"为 `{'data_date': '2026-07-01', 'sp500_level': 7499.0, 'us_10y_treasury_rate': 4.45}`，不含 ERP 数值本身；卡内同指标（行 2162–2167）value=4.3。

事实：任务书的输入清单没有提到 context_brief，但它占 Runtime Input 首块 2,022 字符，其中 layer_highlights 与卡内 core_facts 是同一批数值的第二次呈现（重复材料），且压缩过程中产生了两处语义/内容小出入（趋势标签口径不同、高亮"值"缺主数值）。

### 3. "## 输入"列举的候选关系示例与实际链接不重合；实际三条链接均不含 L2

证据：
- 行 96–101（Read 输出）：输入声明的候选关系示例为"L1-L4: 流动性→估值 / L2-L4: 情绪→估值 / L2-L3: 情绪→广度 / L3-L5: 广度→趋势 / 等等"。
- 行 517–550：实际 `candidate_cross_layer_links` 三条为 L1_L4、L3_L5、L1_L5。
事实：示例中的 L2-L4、L2-L3 在实际链接中不存在；实际链接中的 L1_L5 不在示例中；三条实际链接均不涉及 L2，而 L2 卡是五卡中第二大（22,312 字符），其 cross_layer_hooks 指向 L4/L3/L5/L1 四层（行 1191–1215）。示例带有"等等"二字，并非封闭承诺，此处仅记录声明与实物的不重合。

### 4. 冲突矩阵"A-M"只有 A/B/C/K 四行，其余以省略号代替

证据：
```
$ sed -n '190,215p' full/bridge/attempt_1.prompt.txt
检查冲突矩阵 A-M：

| ID | 冲突 | 你的检查 |
|----|------|---------|
| A | 宏观悲观 vs 趋势强势 | 是否触发？ |
| B | 宏观/情绪乐观 vs 内部健康度恶化 | 是否触发？ |
| C | 估值昂贵 vs 趋势强劲 | 是否触发？ |
| K | 指数创新高 vs A/D线恶化 | 是否触发？ |
| ... | ... | ... |
```
（投影行 266–274 内容相同。）
事实：指令要求"检查冲突矩阵 A-M"（字母跨度 13 项），但材料中矩阵本体只有 4 行定义加一行省略号；D–J、L、M 共 9 行的冲突定义不存在于本站材料。

### 5. event_refs 有整节用法说明、契约也要求该字段，但 Runtime Input 中没有任何事件底账

证据：
- 行 458–470："## 事件引用 (event_refs)"整节（538 字符），首句"如果输入包含 `event_refs`（官方事件底账），Bridge 可以在以下场景中引用事件 ID"，随后列出 typed_conflicts/resonance_chains/transmission_paths/顶层四处引用位置。
```
$ grep -n "event" projected/bridge/attempt_1.projection.md | awk -F: '$1>473' | head -5
3255:- `cross_layer_claims`（可选）：… event_refs:[]} …
3257:- `typed_conflicts`（可选）：… event_refs:[] …
3258:- `resonance_chains`（可选）：… event_refs:[] …
3259:- `transmission_paths`（可选）：… event_refs:[] …
3260:- `principal_contradiction`（可选）：… event_refs:[], …
```
即 Runtime Input 全区（行 473–3249）对 "event" 零命中；命中全部在"输出字段规格"之后。
- 行 3267、3273：输出字段规格与 Response Rules 均把 event_refs 列为顶层字段。
- 旁证（run 目录，非本站语料）：`ls output/analysis/vnext/20260731_002156/` 可见 event_1d77a2d1bb9e1d35.md、event_3935663507f48598.md 等事件产物；manifest.json 显示本 run 有 10 个 event_card_interpreter 实例和 event_section_summary。
事实：指令花一整节教 event_refs 怎么用，输出契约把它列为顶层字段，但本站输入里根本没有 event_refs 键——节首条件句"如果输入包含"在本 run 不成立。本次运行的事件系统有产出，但未进入 bridge 的材料。

### 6. 质量检查清单要求 cross_layer_claims ≥2，而被标明"合法输出"的场景三示例为 []

证据：
- 行 329："- [ ] cross_layer_claims 是否包含至少 2 个支撑关系？"
- 行 338："## 场景示例（三种 regime 都是合法输出）"
- 行 437（场景三 JSON）："cross_layer_claims": [],
事实：清单条款与场景三示例直接矛盾；指令中没有说明二者冲突时以谁为准（Response Rules 行 3274 的"以规格为准"只覆盖字段形状，不覆盖条数要求）。

### 7. 场景示例的 supporting_facts 使用本次输入中不存在的 ref 字符串

证据：
```
$ grep -n "liquidity_expansionary\|valuation_low_percentile\|breadth_healthy\|earnings_growth_strong" projected/bridge/attempt_1.projection.md
353:        "L4.earnings_growth_strong"
393:        "L1.liquidity_expansionary",
394:        "L4.valuation_low_percentile"
402:        "L3.breadth_healthy"
```
- 契约（行 60）："cross_layer_claims[].supporting_facts 只能填写 evidence ref 字符串，格式如 \"L4.get_ndx_pe_and_earnings_yield\"…"
- 五张卡实际 function_id 全集（举例定位：L1 行 711/747/785/826/862/897/935/973/1014；L4 行 2207/2247/2283/2322/2362/2401/2440/2474/2513）均为 `get_*` 形式，无 `earnings_growth_strong`、`liquidity_expansionary`、`valuation_low_percentile`、`breadth_healthy` 四者。
事实：三个场景示例共使用 4 个 supporting_facts ref，全部是本次输入中不存在的"语义式"代号，形态也与契约给定的 `get_*` 函数引用示例不同。示例位于教学区（行 338–456），其写法与契约规则方向相反；模板区另有警告（行 109）"不得照抄历史 run 的短语或矛盾代号"，但这几个示例 ref 本身的合法性没有说明。

### 8. 输出形状在材料中有三处定义，互相漂移；"输出格式"模板缺全部 v2 新增字段

证据：
- "## 输出格式" JSON 模板（行 111–214）顶层键：bridge_type、layers_connected、cross_layer_claims、conflicts、principal_contradiction、secondary_contradictions、price_reflection_map、contradiction_transformation_signals、implication_for_ndx、key_uncertainties——共 10 个。
- "## 输出字段规格"（行 3251–3268）顶层键 17 个，多出：generated_at、typed_conflicts、resonance_chains、transmission_paths、unresolved_questions（顶层）、event_refs、normalization_notes；且规格中 Conflict 含 `conflict_id`（行 3256），模板 conflicts 元素（行 127–136）无此字段；规格中 CrossLayerClaim 含 `event_refs`（行 3255），模板 claims 元素（行 117–125）无此字段。
- 契约散文（行 61–70）把 typed_conflicts 称为"更高优先级的 Bridge v2 产物"，并要求原生填写 typed_conflicts / resonance_chains / transmission_paths / principal_contradiction / secondary_contradictions / price_reflection_map / contradiction_transformation_signals / unresolved_questions。
- Response Rules（行 3274）："字段的**形状**…以上面「输出字段规格」为准；正文里的示例只解释语义，形状冲突时以规格为准。"
事实：输出形状由契约散文、输出格式模板、自动生成规格三处分别定义；模板比规格少 7 个顶层字段，其中恰包括被契约称为"更高优先级产物"的 typed_conflicts、resonance_chains、transmission_paths 三个 v2 主打字段。漂移有显式裁决规则兜底（以规格为准），但模板本身未与规格同步。

### 9. L1 core_facts 内 `raw_data.percentile_10y` 同键混用两种量纲（0–1 与 0–100）

证据：
```
$ grep -n "percentile_10y" projected/bridge/attempt_1.projection.md
567:            "percentile_10y": 0.529
581:            "percentile_10y": 75.4
606:            "percentile_10y": 42.7
623:            "percentile_10y": 0.5795
636:            "percentile_10y": 0.1783
650:            "percentile_10y": 0.978
664:            "percentile_10y": 0.9936
678:            "percentile_10y": 0.585
```
事实：L1 卡 core_facts 数组的 raw_data 中，同名键 `percentile_10y` 在 Fed Funds Rate（75.4，行 581）和 M2（42.7，行 606）两项为 0–100 制，其余六项为 0–1 小数制；卡顶层 `historical_percentile` 字段则统一为 0–100（行 559、575、601、615、631、643、657、671）。材料中无字段说明两种量纲。

### 10. L2 卡内自相矛盾：core_facts 把 get_crowdedness_dashboard 记为 null/stable/normal，同卡详细分析判 elevated 并给出具体读数

证据：
- 行 1142–1149（core_facts）：`"metric": "get_crowdedness_dashboard", "value": null, "historical_percentile": null, "trend": "stable", "magnitude": "normal", "raw_data": null`。
- 行 1485–1490（同卡 indicator_analyses）：`"current_reading": "SKEW=139.55（尾部风险中性偏上），QQQ Put/Call（OI）=1.24（看空情绪主导），QQQ短仓数据缺失", "normalized_state": "elevated"`。
事实：同一张 L2 卡内，汇总区把该指标记为空值+平稳+正常，详细分析区却给出具体子项读数并定级 elevated。Bridge 分析流程 Step 1（行 238–241）指令是"提取每层的 core_facts"，按汇总区读与按详细分析区读会得到相反结论。

### 11. core_facts.raw_data 五卡覆盖不均：L2 全 null、L4 全 {}，仅 L1/L3/L5 有内容；L3 一项 value 为 JSON 字符串而非标量

证据：
- L2 core_facts 12 项 raw_data 全为 null：行 1092、1100、1108、1116、1124、1132、1140、1148、1156、1164、1172、1180（`grep -n '"raw_data": null'` 命中即这些行）。
- L4 core_facts 8 项 raw_data 全为 {}：行 2111、2119、2127、2135、2143、2151、2159、2167。
- L1（行 562–568 等）、L3（行 1753–1759 等）、L5（行 2595–2598 等）各项 raw_data 有具体数值字典。
- 行 1775：L3 "% Stocks Above MA (NDX100)" 的 value 是字符串 `"{\"percent_above_50d\": 48.51, \"percent_above_200d\": 63.37}"`，同项 raw_data 才是解析后的 dict（行 1779–1782）；同卡其它项 value 均为标量。
- 对照：系统级约束第 4 条（行 50）"所有 evidence_refs 必须来自本次输入的 raw_data"。
事实：同名字段 core_facts.raw_data 在五张卡里只有三张有实质内容（L2 十二项全 null、L4 八项全空字典）；L2/L4 两卡的数值只能从内联 value/percentile 字段取得。另有一项 value 字段类型与同表其它项不一致（字符串内嵌 JSON）。

## 盲区

- **投影截断已全部核对原文，无遗留**。投影共 6 处 «…省略 N 字符…»（行 1050、1051、2077、2552、2553、3218），全部是各卡 layer_synthesis / internal_conflict_analysis 散文字符串的中段。已用 python3 从 `full/bridge/attempt_1.prompt.txt` 的 Runtime Input JSON 中取出 10 个相关字段全文（L1.synthesis 272 字符、L1.conflict 255、L2.synthesis 185、L2.conflict 230、L3.synthesis 238、L3.conflict 301、L4.synthesis 324、L4.conflict 345、L5.synthesis 280、L5.conflict 210），逐字通读：补全部分只是论证展开的散文，无新增字段、无新增数字、无与投影可见部分矛盾的数值。除这 6 处外投影无其它截断标记（`grep -n "«…省略"` 仅这 6 行命中；无 __omitted__/__table_projection__ 标记）。
- **未读产出侧文件**：attempt_1.response.raw.txt、output.validated.json、attempt_1.parsed.normalized.json、attempt_1.payload.json 未读——本片任务是"站收到的材料结构"，产出质量不在边界内；payload 与 prompt 的转录差异也未核对。
- **未对照站外源头核验裁剪**：candidate_cross_layer_links 是否完整转录自 run 目录的 analysis_packet.json、context_brief.apparent_cross_layer_signals 由谁生成，均需读站外文件，受"不扩大范围"纪律约束未做。因此发现 1/2/3 只描述"材料内呈现的事实"，不涉及上游生成环节。
- **"47/50 个指标成功"的分母无法独立复核**：完整 50 指标清单不在本站材料内；仅能与卡内覆盖做算术自洽核对（48 个 function_id 有 analyses，其中 1 个标 unavailable，另 2 个 L4 指标在 quality_self_check 标 unavailable/disabled，47+3=50 自洽）。
- **同构字段抽查口径**：五卡 48 个 indicator_analyses 我全部逐条读完（非抽查）；core_facts 的数值一致性只做了跨位置抽查（layer_highlights vs core_facts 抽 5 项、卡内 reading vs core_facts 抽 8 项），未对全部数值做逐位比对。
