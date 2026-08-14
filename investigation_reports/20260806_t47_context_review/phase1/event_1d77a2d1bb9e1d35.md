# event_card_interpreter.event_1d77a2d1bb9e1d35 通读报告

语料根目录（下文所有相对路径的起点）：`/Users/aidianchi/Desktop/ndx_mac/output/analysis/vnext/20260731_002156/context_spread/`

## 通读范围

- 投影：`projected/event_card_interpreter.event_1d77a2d1bb9e1d35/attempt_1.projection.md`，146 行 / 4,898 字符，**逐字全读**。
- 原文：`full/event_card_interpreter.event_1d77a2d1bb9e1d35/attempt_1.prompt.txt`，130 行 / 4,985 字符，**逐字全读**。
- 投影截断核查：投影全文只有 1 处截断标记（`«…省略 100 字符…»`，投影 L78，cth_01 的 hypothesis_text 中段），已对原文定位并照抄原值（见盲区一节）。投影覆盖率 98.25%，截断处已补齐，即本报告实质基于完整原文。
- 辅助文件：`full/.../meta.json`（36 行，全读）、`full/.../attempt_1.payload.json`（用 python 解析比对，见下文）、`manifest.json`（用 python 提取本站条目）。
- manifest 本站条目：`inspector_has_rules = false`（本站此前没有机械检查规则）、`verification_ok = true`、`prompt_chars = 4985`、`projection_chars = 4898`、`projection_ratio = 0.9825`、模型 `deepseek-v4-flash`、attempts = 1、status = ok。
- 未读：`attempt_1.parsed.normalized.json`、`attempt_1.response.raw.txt`、`output.validated.json`（站产出，不属于"材料结构"审查对象），见盲区。

## 材料结构总览

提示词共 4,985 字符，5 个段落（实测，用 `re.split(r'\n(?=## )', txt)` 切段统计）：

| 段落 | 字符 | 占比 | 性质 |
|---|---|---|---|
| `## System Message`（含系统级约束 6 条） | 350 | 7.0% | 规则 |
| `## User Message`（职责 + 铁律 5 条） | 604 | 12.1% | 任务书 |
| `## Runtime Input`（JSON 数据） | 2,751 | 55.2% | 数据材料 |
| `## 输出字段规格`（EventInterpretationCard 契约） | 905 | 18.2% | 规则/契约 |
| `## Response Rules` | 371 | 7.4% | 规则 |

Runtime Input JSON 内部 5 个子块（实测，`json.dumps` 字符量）：

- `event_material` 477 字符 —— 事件本体；但 `raw_text_available=false`、`raw_text_excerpt=""`，真正可消费的事件内容只有一行标题（"Satellite maker K2 Space secures $6.8 billion valuation in new funding round"）。
- `allowed_financial_links` 170 字符 —— 9 个金融传导渠道词表。
- `competing_hypotheses` 770 字符 —— 3 条竞争假说（比 event_material 整块还大）。
- `output_contract` 718 字符 —— 输出字段示例契约（与后面的"输出字段规格"段内容同构）。
- `boundary` 96 字符 —— 三个边界旗标。

**目录解读**：这份提示词里"待解读的事件"本身信息极薄（一行标题），而规则与契约类文字（系统约束 + 任务书 + 字段规格 + Response Rules + Runtime Input 内的 output_contract）合计约 2,948 字符，占全文约 59%；与事件无关的竞争假说文本占 15.4%。规则:数据的比例严重偏向规则一侧。

一致性核查通过项（查过、未发现问题）：

- "九个金融传导渠道"（原文 L18）与 `allowed_financial_links` 实际 9 项一致。
- Response Rules L128 列出的 12 个顶层字段与 `output_contract`、输出字段规格三者字段集一致。
- `event_material.event_id`（L27 `"event:1d77a2d1bb9e1d35"`）与站目录名一致；`event_date` 与 `effective_date` 均为 2026-07-30，与 meta.json 的 effective_date 一致。
- `full/.../attempt_1.payload.json` 的 `payload["payload"]` 与提示词内 Runtime Input JSON 逐键相等（`== True`），即提示词里的数据块与 payload 工件无漂移。

## 发现清单

### 发现 1：输出契约同站双份呈现，且其中一份的措辞规定与任务书直接矛盾

- 证据 A（任务书说措辞自由）：`full/event_card_interpreter.event_1d77a2d1bb9e1d35/attempt_1.prompt.txt:20`
  命令：`sed -n '20p' full/event_card_interpreter.event_1d77a2d1bb9e1d35/attempt_1.prompt.txt`
  输出：`- 来源不是官方披露的、或材料只有标题没有正文的，解读措辞该降一档就降一档，\`limitations\` 里如实写清限制。**措辞完全由你决定，没有固定说法要套**——报告会由代码在每条事件旁自动标出来源等级与"仅标题与片段·降级阅读"，读者不会误判，所以这里不设措辞检查。`
- 证据 B（数据块里的契约示例却规定固定开头）：同文件 `:74`
  命令：`sed -n '74p' full/event_card_interpreter.event_1d77a2d1bb9e1d35/attempt_1.prompt.txt`
  输出：`"interpretation": "模型解读；弱来源以据报道或该媒体称开头",`
- 证据 C（字段规格对此语义中立）：同文件 `:114`
  输出：`- \`interpretation\`（必填）：字符串 —— 与事实分开的模型解读`
- 证据 D（冲突仲裁条款只管"形状"）：同文件 `:129`
  输出：`- 字段的**形状**（对象 / 数组 / 标量、是否可为 null）以上面「输出字段规格」为准；正文里的示例只解释语义，形状冲突时以规格为准。`
- 事实描述：同一份 12 字段输出契约在站内出现两次——`output_contract`（Runtime Input 内，718 字符）和 `## 输出字段规格` 段（905 字符），合计 1,623 字符，约占全文 32.5%。两处不只是冗余：`output_contract` 的 interpretation 示例写着"弱来源以据报道或该媒体称开头"这一固定措辞要求，而 User Message L20 明文"措辞完全由你决定，没有固定说法要套……这里不设措辞检查"。Response Rules L129 的仲裁条款（"形状冲突时以规格为准"）只覆盖形状冲突，不覆盖这种语义层面的矛盾，模型读到两条相反指令时材料本身没有给出以谁为准的规则。

### 发现 2：系统级约束引用的输入结构（raw_data / NO_DATA_AVAILABLE / evidence_refs）在本站材料中不存在

- 证据 A：`attempt_1.prompt.txt:9` —— `4. 所有 evidence_refs 必须来自本次输入的 raw_data，不得凭记忆添加。`
- 证据 B：`attempt_1.prompt.txt:10` —— `5. 若输入出现 \`NO_DATA_AVAILABLE\`，只能把它当作数据边界或置信度限制；不得围绕空数据补写数值、趋势、分位或原因。`
- 证据 C：命令 `python3 -c "..."`（对全文搜三个关键词的出现行号）
  输出：`'raw_data' 出现行号: [9]`；`'NO_DATA_AVAILABLE' 出现行号: [10]`；`'evidence_refs' 出现行号: [9]`
- 证据 D：Runtime Input 顶层键（同文件 L25-109 的 JSON）：`['event_material', 'allowed_financial_links', 'competing_hypotheses', 'output_contract', 'boundary']`，无 `raw_data`；Response Rules L128 规定的 12 个顶层输出字段中也无 `evidence_refs`。
- 事实描述：系统约束 4 要求 evidence_refs 必须来自"本次输入的 raw_data"，但本站的输入 JSON 没有 `raw_data` 键，输出契约里也没有 `evidence_refs` 字段——该约束引用的输入键路径和输出字段在这份材料里都不存在。系统约束 5 针对 `NO_DATA_AVAILABLE` 占位符，该占位符全文只出现在约束条文自己这一行。这两条约束对本站是悬空的（它们显然是为别的站型写的通用约束）。

### 发现 3：任务书开篇声明材料含"正文摘录"，实际事件正文为空，可消费事实只有一行标题

- 证据 A：`attempt_1.prompt.txt:14` —— `你是外部世界材料层的解读员。给你一条已经采集好的事件材料（标题、来源、日期、正文摘录），你的任务是把它变成一张对投研有用的结构化卡片。`
- 证据 B：`attempt_1.prompt.txt:36-37` —— `"raw_text_available": false,` / `"raw_text_excerpt": "",`
- 证据 C：`attempt_1.prompt.txt:35` —— `"entities": [],`
- 事实描述：任务书开篇把输入描述为"标题、来源、日期、正文摘录"四件套，但本实例的 `raw_text_available=false`、正文摘录为空字符串，事件材料里逐字存在的事实只有 L28 那一行英文标题（外加时间、来源等元数据）；采集侧的 `entities` 也是空数组。铁律第 4 条（L20）预见了"材料只有标题没有正文"的情形并要求降档处理，所以空正文本身有指令兜底，但开篇那句对材料构成的声明与本实例实际内容不符。

### 发现 4：事件文本与事件类型/来源栏目/触发理由三类标签之间存在张力，标签本身带相关性诱导

- 证据 A：`attempt_1.prompt.txt:28` —— `"title": "Satellite maker K2 Space secures $6.8 billion valuation in new funding round",`
- 证据 B：`attempt_1.prompt.txt:30` —— `"source": "Yahoo Finance M7 Headlines",`
- 证据 C：`attempt_1.prompt.txt:34` —— `"event_type": "mega_cap_market_news",`
- 证据 D：`attempt_1.prompt.txt:38-41` —— `"trigger_reasons": ["mainline", "inquiry_reference"]`
- 证据 E：`attempt_1.prompt.txt:21` —— `- 与纳指 100 没有可说明关联的事件，诚实输出 \`interpretation: 与判断对象关联不足\`，不要硬找联系。`
- 事实描述：标题文本说的是一家卫星制造公司（K2 Space）的融资估值，文本本身不含任何纳指 100 / 超大市值成分股指涉；但材料同时给这条事件贴了三处"与主线/大盘股相关"性质的标签：`event_type=mega_cap_market_news`、来源栏目名含 "M7"、`trigger_reasons` 表明上游因"主线""问询引用"而采集它。另一方面任务书 L21 又要求对关联不足的事件诚实输出"与判断对象关联不足"。即：材料自带的标签信号与任务书的诚实退出指令方向相反。（该事件与纳指 100 是否真有关联需要外部知识，超出本审查范围；此处只报告材料内部可见的标签与文本张力。）

### 发现 5：与事件无关的市场定量断言占材料大头，且大于事件材料本体

- 证据 A：命令（python 切 Runtime Input JSON 子块统计字符量）
  输出：`event_material 477` / `allowed_financial_links 170` / `competing_hypotheses 770` / `output_contract 718` / `boundary 96`
- 证据 B：`attempt_1.prompt.txt:62`（cth_01）含"当前Forward PE仅19.46倍""盈利修正30日斜率+4.2%、90日+10.7%""M7资本开支加速（同比+75%）""RSI 32.4接近超卖""价格在MA200上方并接近Donchian下轨""整体HY OAS仅31%分位"；`:67`（cth_02）含"supplier_lookback影响（30d flagged权重41%）""M7回购大幅收缩（同比-68.74%）"；`:57`（hyp_base）含"极端实际利率（99.4%分位）"。
- 证据 C：`attempt_1.prompt.txt:17` —— `- 事实和解读必须分开写。\`fact_summary\` 里只许出现材料里逐字有的东西；你的推断全部放进 \`interpretation\` 和 \`mechanism_hypothesis\`。`
- 事实描述：`competing_hypotheses` 块 770 字符，比事件材料整块（477 字符）大 61%，而事件本体可消费信息只有一行标题；假说文本内含至少 9 组具体市场定量断言（估值倍数、分位、斜率、同比、RSI、OAS、权重），全部不是事件材料的内容。`fact_summary` 的"逐字来自材料"铁律（L17）把这些数字挡在事实栏外，但对 interpretation / mechanism_hypothesis / needs_data_confirmation 能否引用这些假说内数字，材料里只有散文界定，没有字段级规则；同时系统约束 2（L7"不得编造点位、跌幅、估值倍数……"）因这些数字"输入数据明确提供"而不构成引用障碍。也就是说，一个只有标题的事件，其解读卡的大部分可用"素材"实际来自假说块而非事件本身。

### 发现 6：tier 取值 "reliable_mainstream_report" 无词表定义，"来源等级"概念无映射

- 证据 A：命令 `python3 -c "..."`（搜 'tier' 与 'reliable_mainstream_report' 出现行号）
  输出：`'tier' 出现行号: [30, 98, 123]`；`'reliable_mainstream_report' 出现行号: [30]`
- 证据 B：`attempt_1.prompt.txt:20` 引用"来源等级"概念（"报告会由代码在每条事件旁自动标出来源等级"）；`:36`（User Message 铁律第 4 条区域）要求按"来源不是官方披露的"降档。
- 事实描述：`tier=reliable_mainstream_report` 这个枚举值全文只出现一次（L30），提示词内没有任何 tier 词表、等级排序或"可靠主流报道 vs 官方披露"的映射；任务书把"来源等级"的标注责任交给"代码自动标出"（L20），但判读"该不该降档"的依据（tier 值落在哪个等级）材料里没有给出。`passport` 又要求照抄 tier 值（L98、L113），即该值会原样进入产出。

### 发现 7（核查通过项，记录为负结果）：未发现数值矛盾

- 证据：命令 `grep -oE '(Forward PE[^，。]*|[0-9]+\.?[0-9]*%分位|\+[0-9]+\.?[0-9]*%|-[0-9]+\.?[0-9]*%|RSI [0-9]+\.?[0-9]*|[0-9]+\.?[0-9]*倍|同比[^，。]*)' ... | sort | uniq -c`
  输出：每个数值串计数均为 1（`1 Forward PE仅19.46倍`、`1 99.4%分位`、`1 31%分位`、`1 +4.2%`、`1 +10.7%`、`1 同比+75%…`、`1 同比-68.74%…`、`1 RSI 32.4`、`1 Forward PE看似较低实则不牢`）。
- 事实描述：同一指标在材料不同位置取不同值的情形，在本站材料中未发现；所有定量断言各只出现一次，均位于 competing_hypotheses 内。

## 盲区

- **投影截断已补**：投影唯一截断点（投影 L78，cth_01 hypothesis_text 中段，标记 `«…省略 100 字符…»`）已查原文。被省略的 100 字符原文照抄（`attempt_1.prompt.txt:62` 内）：`格在MA200上方并接近Donchian下轨，显示抛压可能已近尾声。若实际利率不再上行，盈利兑现将触发估值修复，市场可能已过度悲观。净流动性边际改善和期限利差转正也提供宽松背景。主线对信用尾部风险的重`。其中含 MA200、Donchian 两个技术指标引用，投影读者会看不到这两个词。除此之外投影与原文无其他差异（4985 vs 4898 字符的差值即此 100 字符减去标记本身）。
- **未逐字读站产出**：`full/.../attempt_1.response.raw.txt`（1,592 字节）、`attempt_1.parsed.normalized.json`、`output.validated.json` 是站的产出而非输入材料，本任务界定为"材料结构审查"，未逐字读；因此"模型实际是否被发现 1/4/5 诱导"不在本报告范围。
- **外部事实未核**：K2 Space 与纳指 100 的真实关联、"Yahoo Finance M7 Headlines" 栏目的实际收录范围、"reliable_mainstream_report" 在系统其他代码里的词表定义，均需查语料外资料，本次未做。
- **跨站一致性未查**：同一 event_id 在其他站（如采集站、报告组装站）里如何被引用、competing_hypotheses 的文本是否与假说生成站的输出逐字一致，超出本站边界，未查。
