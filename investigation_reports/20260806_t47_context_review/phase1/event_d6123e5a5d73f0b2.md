# event_card_interpreter.event_d6123e5a5d73f0b2 通读报告

站族：event_card_interpreter（事件卡片解读员）；实例：event:d6123e5a5d73f0b2；attempt 1；模型 deepseek-v4-flash；run 20260731_002156。

## 通读范围

读了哪些文件、读了多少、怎么读的：

| 文件 | 量 | 读法 |
|---|---|---|
| `projected/event_card_interpreter.event_d6123e5a5d73f0b2/attempt_1.projection.md` | 146 行 / 8,720 字节 | 逐行全读 |
| `full/event_card_interpreter.event_d6123e5a5d73f0b2/attempt_1.prompt.txt` | 130 行 / 4,989 字符 | 逐行全读（通读主材料） |
| `full/.../meta.json` | 36 行 | 逐行全读 |
| `full/.../attempt_1.payload.json` | 4,044 字节 | 未逐行目读；用 python 全量键值比对（见发现 7） |
| `context_spread/manifest.json` | 本站条目 | 用 python 提取（未逐行读全量） |

方法与命令：

- 投影 vs 原文差异：`diff <(sed -n '17,146p' 投影) <(sed -n '1,130p' 原文)` → 仅 `62c62` 一处（投影唯一截断点，cth_01 假说文本中段 «…省略 100 字符…»）。被省略段已对照原文第 62 行读到全值："格在MA200上方并接近Donchian下轨，显示抛压可能已近尾声。若实际利率不再上行，盈利兑现将触发估值修复，市场可能已过度悲观。净流动性边际改善和期限利差转正也提供宽松背景。主线对信用尾部风险的重"。即投影 100% 覆盖处均已核对，无抽查。
- 分块字符量：python 解析 prompt.txt 内嵌 Runtime Input JSON，逐键 `len(json.dumps(...))` 计数。
- 字段/关键词定位：`grep -n`（evidence_ref、raw_data、NO_DATA_AVAILABLE、材料、trigger_reasons、upgrade_candidate、数字行等），命令与输出照抄于各发现内。

manifest.json 本站条目关键值（命令：`python3 -c` 遍历 `m['instances']` 按 id 过滤）：

```
"prompt_chars": 4989,  "projection_chars": 4902,  "projection_ratio": 0.9826,
"inspector_has_rules": false,  "inspector_can_read": true,  "verification_ok": true
```

即：这站此前连机械检查规则都没有（`inspector_has_rules: false`）；投影覆盖率 98.3%，唯一丢失的就是上述 100 字符中段。

## 材料结构总览

段落目录（照抄投影文件头，字符口径=投影目录）：

| 段落 | 字符 | 占比 | 内容 |
|---|---|---|---|
| `## System Message` 段头 | 18 | 0.4% | 段标题本身 |
| `# System-Level Constraints (不可违反)` | 333 | 6.7% | 6 条通用纪律 |
| `## User Message` | 605 | 12.1% | 任务书：解读员职责 + 5 条铁律 |
| `## Runtime Input` | 2,756 | 55.2% | 输入 JSON（事件材料+假说+契约+边界） |
| `## 输出字段规格` | 906 | 18.2% | EventInterpretationCard 契约字段表 |
| `## Response Rules` | 371 | 7.4% | 5 条返回规则 |
| 合计 | 4,989 | 100% | |

Runtime Input 内部结构（python 实测，JSON body 2,737 字符口径，命令输出原文）：

```
event_material: 481 chars (17.6% of RuntimeInput)
allowed_financial_links: 170 chars (6.2% of RuntimeInput)
competing_hypotheses: 770 chars (28.1% of RuntimeInput)
output_contract: 718 chars (26.2% of RuntimeInput)
boundary: 96 chars (3.5% of RuntimeInput)
```

解读这张分布图的三个要点：

1. **事件实质内容极小。** event_material 481 字符里，事件本身的全部内容 = 标题 81 字符（"Exchange-Traded Funds, Equity Futures Higher Pre-Bell Thursday Amid Tech Earnings"），其余 400 字符是 id/来源/时间/类型/旗标等元数据；`entities: []`、`raw_text_available: false`、`raw_text_excerpt: ""`。标题占全文 4,989 字符的 1.6%。
2. **输出形状说明占大头。** output_contract（718）+ 输出字段规格（906）+ Response Rules（371）= 1,995 字符，占全文 40.0%——同一份输出契约以三种形态各讲了一遍（详见发现 5）。
3. **竞争假说是输入里信息密度最高的部分。** 三条假说文本合计 534 字符（hyp_base 48 + cth_01 280 + cth_02 206），内含约 10 个具体定量数据点；是事件实质内容（81 字符、零数据点）的 6.6 倍（详见发现 2）。

## 发现清单

### 发现 1：任务书声称材料含"正文摘录"，实到材料只有标题（正文摘录为空字符串）

**证据**（`full/.../attempt_1.prompt.txt`，以下行号均指该文件）：

- 第 14 行任务书原文："给你一条已经采集好的事件材料（标题、来源、日期、**正文摘录**），你的任务是把它变成一张对投研有用的结构化卡片。"
- 第 35–37 行实到材料：
  ```
  "entities": [],
  "raw_text_available": false,
  "raw_text_excerpt": "",
  ```
- 第 28 行为唯一事件内容：`"title": "Exchange-Traded Funds, Equity Futures Higher Pre-Bell Thursday Amid Tech Earnings"`（81 字符）。

**事实描述**：任务书把"正文摘录"列为已给材料的组成部分，但本例 `raw_text_available=false`、`raw_text_excerpt=""`，事件全部实质内容就是一行英文标题。任务书第 20 行另有"材料只有标题没有正文的，解读措辞该降一档"的降级条款，即规则层面预见了这种情形；但任务书开头对材料形态的描述（"标题、来源、日期、正文摘录"四件俱全）与本例实际到手的形态不符。事件实质内容占全文 1.6%（81/4,989 字符）。

### 发现 2：材料信息结构偏科——手里的定量信息全部来自"竞争假说"，而不是来自要解读的事件

**证据**：

- 分块字符量（python 解析 Runtime Input，命令与输出见"材料结构总览"）：`event_material: 481 chars (17.6%)`、`competing_hypotheses: 770 chars (28.1%)`。
- 假说文本内含的定量数据点（命令 `grep -n "[0-9]" attempt_1.prompt.txt`，输出关键行照抄）：
  - 第 57 行（hyp_base）："极端实际利率（**99.4%分位**）"
  - 第 62 行（cth_01）："Forward PE仅**19.46倍**……盈利修正30日斜率**+4.2%**、90日**+10.7%**与M7资本开支加速（同比**+75%**）……**RSI 32.4**接近超卖，价格在**MA200**上方并接近Donchian下轨……整体HY OAS仅**31%分位**"
  - 第 67 行（cth_02）："supplier_lookback影响（30d flagged权重**41%**）……M7回购大幅收缩（同比**-68.74%**）"
- 事件材料侧数据点：0 个（发现 1）。

**事实描述**：三条假说文本 534 字符、含约 10 个具体定量数据点；要解读的事件 81 字符、零数据点。假说是 supports/refutes 的合法消费对象（第 19 行铁律、第 84–88 行契约均要求引用 hypothesis_id），属职责所需材料；结构事实是：这站手里攥着的可引用定量内容 100% 来自系统既有假说（含其他环节的既有判断与数字），事件本身不提供任何可核对的内容。同时第 7 行约束"不得编造点位、跌幅、估值倍数……"与假说文本提供的大量现成数字并存，约束未说明引用假说文本中的数字算不算"输入数据明确提供"（第 6 行约束的豁免条件）。

### 发现 3：两条"不可违反"的系统约束引用了本站输入/输出 Schema 中不存在的字段与标记

**证据**（命令 `grep -n "evidence_ref\|raw_data\|NO_DATA_AVAILABLE" attempt_1.prompt.txt`，输出照抄）：

```
9:4. 所有 evidence_refs 必须来自本次输入的 raw_data，不得凭记忆添加。
10:5. 若输入出现 `NO_DATA_AVAILABLE`，只能把它当作数据边界或置信度限制；不得围绕空数据补写数值、趋势、分位或原因。
106:    "must_not_become_l1_l5_evidence_ref": true,
```

**事实描述**：

- 第 9 行约束 4 提到 `evidence_refs` 和 `raw_data`：全 prompt 中这两个词只出现在该条文自身（第 106 行的 `must_not_become_l1_l5_evidence_ref` 是 boundary 旗标名，不是输出字段）。输入 JSON（第 26–108 行）没有 `raw_data` 键；输出契约（第 71–103 行）与输出字段规格（第 112–123 行）都没有 `evidence_refs` 字段。该约束指向的对象在本站不存在。
- 第 10 行约束 5 针对 `NO_DATA_AVAILABLE` 标记：该标记在本例输入中不出现；本例实际的空数据信号是第 36–37 行的 `raw_text_available: false` + `raw_text_excerpt: ""`。约束描述的标记与本例使用的空数据表示法对不上（语义相近，字面不同）。
- 6 条系统约束中的这 2 条，其适用对象在本站材料里没有实例。

### 发现 4：铁律关键词"材料"未界定指涉边界

**证据**（命令 `grep -n "材料" attempt_1.prompt.txt`，输出照抄关键行）：

```
14:你是外部世界材料层的解读员。给你一条已经采集好的事件材料（标题、来源、日期、正文摘录）……
17:- 事实和解读必须分开写。`fact_summary` 里只许出现材料里逐字有的东西；……
20:- ……你要做的是别把只有标题的材料写得像读过全文一样确定。
73:    "fact_summary": "只写材料事实",
76:      "材料中的实体"
113:- `fact_summary`（必填）：字符串 —— 只包含原材料事实的摘要
115:- `entities`（可选）：数组，元素为 字符串 —— 材料中涉及的实体
```

**事实描述**："材料"一词出现 7 处，均未定义它指 `event_material` 这一块，还是指整个 Runtime Input（含 `competing_hypotheses` 的假说文本）。按字面后一种读法，假说文本里的数字（19.46、+75%、-68.74% 等）也"逐字有的"，可以合法进入 `fact_summary`；按前一种读法则不行。两种读法在 prompt 内都能成立，没有消歧条文。本例事件只有标题，这个边界问题被放大——`fact_summary` 能写什么，几乎完全取决于"材料"怎么界定。

### 发现 5：输出形状以三种形态重复声明（合计占全文 40%），其中两处指令字面相互矛盾

**证据**：

- 三处声明（行号 + python 分块字符量）：
  1. 第 71–103 行 `output_contract`（Runtime Input 内，718 字符）：12 个字段以"示例值"形态给出，无必填/可选标注；
  2. 第 111–123 行 `## 输出字段规格`（906 字符）：同一契约的正式字段表，标注 6 必填（event_id、fact_summary、interpretation、event_type、mechanism_hypothesis、passport）+ 6 可选；
  3. 第 125–130 行 `## Response Rules`（371 字符）：第 128 行再次列出全部 12 个顶层字段名。
  合计 718+906+371 = 1,995 字符 = 全文 4,989 字符的 40.0%。
- 矛盾点 a（可选字段是否必须出现）：第 128 行原文"JSON 顶层字段必须匹配: event_id, fact_summary, interpretation, entities, event_type, mechanism_hypothesis, supports_hypotheses, refutes_hypotheses, limitations, needs_data_confirmation, upgrade_candidate, passport。"——12 个字段全列、含 6 个可选字段，未说明可选字段可否省略；与规格的"可选"划分之间的取舍只能依赖第 129 行"字段的**形状**……以上面「输出字段规格」为准；正文里的示例只解释语义，形状冲突时以规格为准"来消解。
- 矛盾点 b（弱来源措辞）：第 74 行 output_contract 示例原文 `"interpretation": "模型解读；弱来源以据报道或该媒体称开头"`（给弱来源定了一个开头句式）；第 20 行铁律原文"**措辞完全由你决定，没有固定说法要套**——报告会由代码在每条事件旁自动标出来源等级与"仅标题与片段·降级阅读"，读者不会误判，所以这里不设措辞检查"。一处给固定说法，一处明说没有固定说法，两句并存于同一 prompt。
- 重复但一致的一处：九个金融传导渠道枚举两遍——第 43–53 行 `allowed_financial_links` 数组，与第 117 行规格内联枚举 `financial_link:"earnings_path"|"valuation_multiple"|"discount_rate"|"risk_premium"|"liquidity_condition"|"credit_condition"|"index_structure"|"market_breadth"|"technical_flow"`，逐项一致。

**事实描述**：同一份输出契约以"示例契约 / 正式字段表 / 返回规则清单"三种形态各出现一次，共占全文 40.0%；其中"12 字段全列 vs 6 可选"与"固定开头句式 vs 措辞完全由你决定"两处字面冲突，前者有明文消解规则（以规格为准），后者没有——第 129 行的消解规则只覆盖"形状"，不覆盖措辞语义。

### 发现 6：若干材料字段在全 prompt 中没有任何消费指令

**证据**（命令 `grep -n "trigger_reasons\|event_ref_only\|must_not\|upgrade_candidate" attempt_1.prompt.txt`，输出照抄）：

```
38:    "trigger_reasons": [
95:    "upgrade_candidate": false,
105:    "event_ref_only": true,
106:    "must_not_become_l1_l5_evidence_ref": true,
107:    "must_not_feed_back": true
122:- `upgrade_candidate`（可选）：布尔 —— 是否值得进入后续正式证据升级流程
128:- JSON 顶层字段必须匹配: …… upgrade_candidate, passport。
```

**事实描述**：

- `trigger_reasons`（第 38–41 行，值 `["mainline", "inquiry_reference"]`）：全文仅出现于数据本身，没有任何指令解释其含义或要求如何消费。
- `boundary` 三旗标（第 104–108 行，均 true）：全文仅出现于数据本身，无任何指令将其与本站输出行为关联。
- `upgrade_candidate`：判定标准全文只有第 122 行一句"是否值得进入后续正式证据升级流程"，无阈值、无条件、无"升级流程"是什么的说明。
- 相邻小项：`event_type` 在材料中已有值 `"market_news_report"`（第 34 行），输出契约（第 78 行）与规格（第 116 行）只写"事件类型"，未像 passport 五字段（第 97–101 行均标"照抄 event_material.××"）那样指明是否照抄。

### 发现 7（阴性结果）：时间互洽、数值无矛盾、payload 与 prompt 输入一致

**证据与事实**：

- 时间一致性：命令 `python3 -c "import datetime; print(datetime.date(2026,7,30).strftime('%A'))"` → 输出 `Thursday`。第 31 行 `published_at: "Thu, 30 Jul 2026 13:11:32 +0000"`、第 32–33 行 `event_date`/`effective_date` 均为 `2026-07-30`、第 28 行标题含 "Pre-Bell Thursday"——四处互洽。
- 数值矛盾检查：命令 `grep -n "[0-9]" attempt_1.prompt.txt` 列出全部含数字行（见发现 2 照抄），同一指标未在不同位置出现不同值。未发现数值矛盾。
- 输入一致性：命令 python 解析 `attempt_1.payload.json` 的 `payload` 键并与 prompt.txt 内嵌 Runtime Input JSON 全量比较 → 输出 `payload == prompt RuntimeInput JSON: True`。payload.json 不含 prompt 之外的额外材料。
- 投影保真性：命令 `diff`（见"通读范围"）显示投影与原文仅差 1 行（第 62 行 cth_01 中段 «…省略 100 字符…»），省略段已回查原文，无信息盲区残留。

## 盲区

- **投影截断**：本站投影只有 1 处截断（第 78 行 cth_01 文本中段 100 字符），已对照原文第 62 行读到全值；不存在"截断没查原文"的残留。
- **产出侧文件未逐字读**：`attempt_1.response.raw.txt`、`attempt_1.parsed.normalized.json`、`output.validated.json` 未逐字阅读——本任务边界是审查"输入材料结构"，不评价站产出；这些文件与本报告的结论无关，但如果后续要核对"站的实际输出是否受上述结构问题影响"，需要补读。
- **payload.json 未逐行目读**：用程序做了全量键值相等性比较（结果 True），未人工逐字符核对格式差异。
- **"约束块是否全站通用样板"未验证**：发现 3 只陈述站内事实（约束引用的字段/标记在本站 schema 中不存在）；该约束块是否为所有 25 站共用模板、在其他站是否有对应字段，按纪律未查看其他站，无法回答。
- **manifest.json 全量未逐行读**：只提取了本站条目；全 run 的统计口径（如 `stage_dir_count`、`total_prompt_chars` 的构成）未核对。
- **九个渠道的语义未审**：`allowed_financial_links` 九项只做了"两处枚举一致"的核对，未审九项划分本身是否合理（超出"材料结构对不对"的范围，属内容设计问题）。
