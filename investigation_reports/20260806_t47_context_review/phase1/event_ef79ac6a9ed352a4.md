# event_card_interpreter.event_ef79ac6a9ed352a4 通读报告

## 通读范围

读了哪些文件、读了多少、怎么读的：

| 文件 | 大小 | 读法 |
|---|---|---|
| `projected/event_card_interpreter.event_ef79ac6a9ed352a4/attempt_1.projection.md` | 149 行 / 8,743 字节 | **全读**（Read 工具，行 1–149 全量返回） |
| `full/event_card_interpreter.event_ef79ac6a9ed352a4/attempt_1.prompt.txt` | 133 行 / 5,012 字符 | **全读**（Read 工具，行 1–133 全量返回），与投影逐段对照 |
| `full/.../meta.json` | 36 行 | 全读 |
| `full/.../attempt_1.payload.json` | 4,073 字节 | 抽查头部 600 字符，确认其为 Runtime Input 的载荷包装 |
| `context_spread/manifest.json`（本站条目） | — | 用 python 提取本站条目全读 |

投影截断核查：全投影只有 **1 处**截断标记，已查原文。

```
$ grep -n "省略\|__omitted__\|__table_projection__" projected/.../attempt_1.projection.md
81:      "hypothesis_text": "主线认为……RSI 32.4接近超卖，价«…省略 100 字符…»视可能高估了扩散概率……",
```
被省略的 100 字符即 cth_01 假说文本中段，原文 full/attempt_1.prompt.txt:65 已查得全文（"价格在MA200上方并接近Donchian下轨……主线对信用尾部风险的重视可能"）。除这一处外，投影与原文逐段一致（我两边全读后逐段对照；manifest 记 `verification_ok: true`、`projection_ratio: 0.9826`）。

manifest 本站条目关键值（命令：`python3 -c "import json; ..."` 遍历 `instances` 匹配 `ef79ac6a9ed352a4`）：
- `prompt_chars: 5012`，`projection_chars: 4925`，`projection_ratio: 0.9826`
- **`inspector_has_rules: false`**（这站此前连机械检查规则都没有）
- `verification_ok: true`

未读为审查对象的文件：`attempt_1.response.raw.txt`、`attempt_1.parsed.normalized.json`、`output.validated.json`——任务是审"材料结构本身"，不评价站产出，故未纳入（见"盲区"）。

## 材料结构总览

实测段落字符数（命令：python 对 `attempt_1.prompt.txt` 按 `\n## ` 切分取 `len()`，总字符 5,012 与 manifest/投影头一致）：

```
总字符数: 5012
   350 字符 | ## System Message          （ 7.0%）
   604 字符 | ## User Message            （12.1%）
  2778 字符 | ## Runtime Input           （55.4%）
   905 字符 | ## 输出字段规格（…契约自动生成…） （18.1%）
   371 字符 | ## Response Rules           （ 7.4%）
```

与投影头部"段落目录"一致（目录按自身口径标 18/333/605/2779/906/371，差异≤1 字符属标题行计数口径）。

Runtime Input（2,760 字符 JSON 块）内部构成（命令：python 提取 `## Runtime Input` 后 JSON，`json.dumps` 逐键测长）：

```
event_material:         536 字符 (19.4%)   ← 本站的职责对象（一条事件）
allowed_financial_links: 190 字符 ( 6.9%)
competing_hypotheses:   826 字符 (29.9%)   ← 3 条竞争假说全文
output_contract:        820 字符 (29.7%)   ← 输出形状示例
boundary:               104 字符 ( 3.8%)
```

分布图解读：这是一份"轻任务"提示词——规则/契约类文字（System 350 + User 604 + 输出字段规格 905 + Response Rules 371 + Runtime Input 内的 output_contract 820 + boundary 104 ≈ 3,154 字符，约 **63%**）远多于被解读的事件本体（event_material 536 字符，约 **11%**，而其中真正承载事实的只有 title 一个字段 30 字符）。描述"输出长什么样"的内容以三种形态重复出现（见发现 7）。

## 发现清单

（只报线索与事实，不定级、不开方。行号均指 `full/event_card_interpreter.event_ef79ac6a9ed352a4/attempt_1.prompt.txt`，下文简称"原文"。）

### 发现 1：System 约束引用本站不存在的概念（evidence_refs / raw_data / NO_DATA_AVAILABLE）

命令：
```
$ grep -n "evidence_refs\|raw_data\|NO_DATA_AVAILABLE" full/.../attempt_1.prompt.txt
9:4. 所有 evidence_refs 必须来自本次输入的 raw_data，不得凭记忆添加。
10:5. 若输入出现 `NO_DATA_AVAILABLE`，只能把它当作数据边界或置信度限制；不得围绕空数据补写数值、趋势、分位或原因。
```
事实：
- 约束 4（原文行 9）要求"所有 evidence_refs 必须来自本次输入的 raw_data"，但本站输入 JSON 的顶层键只有 `event_material / allowed_financial_links / competing_hypotheses / output_contract / boundary`（原文行 25–112），**没有 `raw_data`**；输出契约 12 个字段（原文行 131 与行 114–126）中**没有 `evidence_refs` 字段**。该约束指向的输入键与输出字段在本站均不存在，是通用模板约束套用到一个不消费它的站上。
- 约束 5 提到的 `NO_DATA_AVAILABLE` 标记在输入中未出现；该约束写作条件式（"若输入出现"），属不适用而非矛盾。

### 发现 2：output_contract 示例给弱来源规定了固定开头，与 User Message"没有固定说法要套"直接冲突

原文照抄：
- 原文行 20（User Message 铁律）："**措辞完全由你决定，没有固定说法要套**——报告会由代码在每条事件旁自动标出来源等级与"仅标题与片段·降级阅读"，读者不会误判，所以这里不设措辞检查。"
- 原文行 77（Runtime Input → output_contract）：`"interpretation": "模型解读；弱来源以据报道或该媒体称开头"`

事实：User Message 明示"没有固定说法要套"；同一提示词内 output_contract 的 interpretation 示例语义却写明"弱来源以据报道或该媒体称开头"——即一个固定开头说法。本实例 `tier: "third_party_calendar"`（行 30）且 `raw_text_available: false`（行 38），正属"弱来源"情形，两条指令对本实例同时适用且指向相反行为。Response Rules（原文行 132）只说"正文里的示例只解释语义，形状冲突时以规格为准"，该条款覆盖的是**形状**冲突，未覆盖语义/措辞冲突归谁管。

### 发现 3：另一条固定字面输出与"措辞完全由你决定"并存

原文照抄：
- 原文行 21："与纳指 100 没有可说明关联的事件，诚实输出 `interpretation: 与判断对象关联不足`，不要硬找联系。"

事实：行 21 要求 `interpretation` 在特定情形下取一个具体固定字符串，与行 20"措辞完全由你决定，没有固定说法要套"并存。两者语境不同（行 20 针对弱来源降级措辞，行 21 针对无关联事件），属指令内部表述张力；本实例事件为 AAPL（纳指 100 成分股）财报日历，行 21 分支大概率不触发，但提示词层面张力存在。

### 发现 4：任务书声称给"正文摘录"，实际材料无正文

原文照抄：
- 原文行 14："给你一条已经采集好的事件材料（标题、来源、日期、正文摘录）"
- 原文行 38–39：`"raw_text_available": false,` / `"raw_text_excerpt": "",`

命令：
```
$ python3 - <<'EOF'  （提取 event_material 逐字段测长）
  raw_text_available: 5 字符 = false
  raw_text_excerpt: 2 字符 = ""
EOF
```
事实：任务书描述的材料形态包含"正文摘录"，本实例实际正文摘录为空字符串、`raw_text_available=false`。行 20 与行 36 区域确有对"只有标题没有正文"情形的降级规则，即该情形被指令预期；但任务书第一句对材料形态的声明与本实例现实不符。

### 发现 5：event_type 标 "official_calendar"，tier 标 "third_party_calendar"，source 含 "estimated"

原文照抄：
- 原文行 29：`"source": "Yahoo Finance earnings dates + deterministic estimated blackout rule"`
- 原文行 30：`"tier": "third_party_calendar"`
- 原文行 34：`"event_type": "official_calendar"`

事实：同一事件的 `event_type` 含 "official"（官方日历），而 `tier` 为第三方日历、`source` 为 Yahoo Finance 且含 "estimated"（估计）字样。两个字段对来源权威级别的语义指向不同；提示词未告诉模型当 `event_type` 与 `tier` 语义不齐时以哪个为准（输出契约中 `event_type` 字段说明仅"事件类型"四字，原文行 119）。

### 发现 6：事件本体事实密度极低，材料中的定量信息全部来自 competing_hypotheses

命令与输出（python 提取各假说文本中的数字片段、event_material 全文中数字）：
```
competing_hypotheses 各条:
  hyp_base_88ece56ecb: text 48 字符, status=leading
  cth_01: text 280 字符, status=candidate
  cth_02: text 206 字符, status=candidate
hyp_base_88ece56ecb 数字片段: ['99.4%']
cth_01 数字片段: ['19.46倍', '30', '+4.2%', '90', '+10.7%', '7', '+75%', '32.4', '200', '31%']
cth_02 数字片段: ['30', '41%', '7', '-68.74%']
event_material 全文中数字: ['79', '6', '9', '352', '4', '2026-07-30T16:21:56', '2026-07-30', '2026-07-30']
```
事实：
- 站的职责对象是 event_material，但其 12 个字段中承载事实的只有 `title: "AAPL scheduled earnings date"`（30 字符，原文行 28）；事件本体**不含任何定量内容**，连"scheduled earnings date"具体是哪一天、哪个财季、盘前盘后都没有——只有 `event_date: "2026-07-30"` 与 `published_at` 同日（原文行 31–33），材料未说明该日期是"排期发布日"还是"财报当日"。
- 提示词里全部实质定量信息（99.4% 分位、Forward PE 19.46 倍、+4.2%、+10.7%、+75%、RSI 32.4、MA200、HY OAS 31% 分位、41%、-68.74% 等）都来自 `competing_hypotheses` 三条假说文本（原文行 57–73，共 826 字符，占 Runtime Input 29.9%），多于 event_material 的 536 字符（19.4%）。
- 并存约束：System 行 7"不得编造点位、跌幅、估值倍数……"；铁律行 17"fact_summary 里只许出现材料里逐字有的东西"。假说文本里这些数字属于"输入中明确提供"还是"不得当材料事实"，提示词没有划定。

### 发现 7：结构性重复——同一份输出形状以三种形态出现三次，合计约占全提示词 42%

命令：
```
$ grep -n "fact_summary" full/.../attempt_1.prompt.txt
17:- 事实和解读必须分开写。`fact_summary` 里只许出现材料里逐字有的东西……
76:    "fact_summary": "只写材料事实",
116:- `fact_summary`（必填）：字符串 —— 只包含原材料事实的摘要
131:- JSON 顶层字段必须匹配: event_id, fact_summary, interpretation, entities, ……
```
事实：
- 12 个输出字段的完整清单出现 **3 次**：① Runtime Input 内 `output_contract` JSON 示例（原文行 74–106，实测 820 字符）；② `## 输出字段规格` 段落（原文行 114–126，905 字符）；③ Response Rules 顶层字段清单（原文行 131）。三处内容一致（均为同一契约的示例/规格/清单形态），未发现字段名或形状冲突。
- 9 项金融链路枚举完整出现 **2 次**（命令 `grep -n "earnings_path"`：行 47 的 JSON 数组、行 120 规格内联枚举 `"earnings_path"|"valuation_multiple"|…`），另有行 18"九个金融传导渠道"与行 84"从 allowed_financial_links 选择一项"两处引用。枚举两处一致，且与"九个"的说法一致（实测 9 项）。
- 重复描述输出形状的合计 ≈ 820 + 905 + 371（Response Rules 全段）≈ 2,096 字符，占全提示词 5,012 的 **41.8%**。

### 发现 8：两块材料无任何消费指令（trigger_reasons、boundary 三 flag）

原文照抄：
- 原文行 40–44：`"trigger_reasons": ["mainline", "inquiry_reference", "official_calendar_landing"]`
- 原文行 107–111：`"boundary": {"event_ref_only": true, "must_not_become_l1_l5_evidence_ref": true, "must_not_feed_back": true}`

事实：全文（含 System/User/规格/Response Rules）没有任何一处解释 `trigger_reasons` 三个值的含义或要求模型消费它；`boundary` 三个布尔值（均 true）也没有对应的行为指令——例如 `must_not_feed_back: true` 要求模型做/不做什么，提示词未说明。两块共约 166 字符（62 + 104），属于塞进来但指令未要求消费的材料。

### 发现 9：指令文本自述"不设措辞检查"，与 manifest 记录一致

- 原文行 20："……所以这里不设措辞检查。"
- manifest 本站条目：`"inspector_has_rules": false`

事实：提示词自述与机械记录一致——这站运行时没有任何机械检查规则兜底，行为完全依赖模型对指令的遵从。

## 核查为一致/正常的项（如实记录，不算发现）

- 段落目录字符量与实测一致（差异 ≤1 字符/段，属标题行计数口径）；投影率 98.3% 与 manifest 一致。
- "九个金融传导渠道"：allowed_financial_links 实测 9 项，一致（原文行 18 vs 行 46–56）。
- `output_contract` 中 passport"照抄 event_material.source/tier/published_at/event_date/effective_date"（原文行 99–105）与 event_material 实际五字段一一对应，无悬空引用。
- 同一指标在材料不同位置出现不同值的情况：**未发现**（各定量片段均只出现一次）。
- `meta.json`：`status: ok`、`attempts: 1`、`validation_errors: []`、`errors: []`、`effective_date: "2026-07-30"` 与事件 `effective_date` 一致；`data_boundary.max_input_date: null`、`backtest_cutoff_respected: null`（该站无输入 artifact 边界记录，`input_artifacts: []`）。

## 盲区

1. **站产出未审**：`attempt_1.response.raw.txt`、`attempt_1.parsed.normalized.json`、`output.validated.json` 未读未评——任务是审"材料结构本身"，产出好坏不在本片范围。因此发现 2/3 的矛盾实际如何影响产出，本片不回答。
2. **`payload.json` 只抽查了头部 600 字符**（确认其为 `{stage_key, stage_name, attempt, payload, retry_feedback}` 包装且 `payload` 与提示词 Runtime Input 同键），未做逐字节 diff；`retry_feedback` 的值未确认。
3. **下游行为未验证**：原文行 20 声称"报告会由代码在每条事件旁自动标出来源等级与『仅标题与片段·降级阅读』"——该代码行为是否真实发生超出本站语料范围，未验证。
4. **跨站衔接未查**：本站输入的 `competing_hypotheses` 三条假说由上游哪个站产生、与本 run 其他 24 站所见假说是否同源一致，未查（超出本站边界）。
5. **投影↔原文一致性靠逐段人眼对照**，非程序化 diff；投影唯一截断处（cth_01 中段 100 字符）已回查原文，其余部分有 manifest `verification_ok: true` 与人眼对照双重支持，但未跑字符级 diff。
6. **`source` 字段中 "deterministic estimated blackout rule" 的具体规则内容**未包含在材料中，也无从在本站语料内查证其含义——它只是一个来源描述字符串。
