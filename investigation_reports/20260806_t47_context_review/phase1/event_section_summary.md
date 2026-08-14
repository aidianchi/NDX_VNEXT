# event_section_summary 通读报告

## 通读范围

语料根目录：`/Users/aidianchi/Desktop/ndx_mac/output/analysis/vnext/20260731_002156/context_spread/`

| 文件 | 大小/行数 | 读法 |
|---|---|---|
| `projected/event_section_summary/attempt_1.projection.md` | 19,552 字节 / 248 行 | 逐行全读 |
| `projected/event_section_summary/attempt_2.projection.md` | 20,611 字节 / 262 行 | 逐行全读 |
| `full/event_section_summary/attempt_1.prompt.txt` | 19,844 字节（manifest 记 12,353 字符） | 开头逐字节核查（`head -c 400 \| cat -v`）；与 attempt_2 做 `diff` 全文比对；投影 2 处截断标记处回查原文全文 |
| `full/event_section_summary/attempt_2.prompt.txt` | 20,904 字节（manifest 记 12,921 字符） | 同上（diff 覆盖全文） |
| `full/event_section_summary/attempt_1.payload.json` | 15,833 字节 | python 解析，顶层键与 `payload` 子键全列；`payload` 与 attempt_2 做序列化比对 |
| `full/event_section_summary/attempt_2.payload.json` | 16,793 字节 | 同上；`retry_feedback` 字段全文读取（520 字符） |
| `full/event_section_summary/attempt_1.response.raw.txt` | 2,192 字节 / 10 行 | 逐行全读 + python `json.loads` 验证 |
| `full/event_section_summary/attempt_2.response.raw.txt` | 1,944 字节 / 10 行 | 逐行全读 + python `json.loads` 验证 |
| `full/event_section_summary/meta.json` | 6,090 字节 / 57 行 | 逐行全读 |
| `manifest.json`（本站两条 instance 记录） | — | python 提取本站条目 |

两个 attempt 的 Runtime Input（即 payload.json 的 `payload` 子树）经 `json.dumps(sort_keys=True)` 比对**完全一致**；两个 prompt 全文的 `diff` 显示唯一差异是 attempt_2 末尾追加的 14 行重试反馈块。因此 attempt 间差异分析以该反馈块为焦点，其余部分按单份材料通读。

（后续章节边查边追加。）

## 材料结构总览

### 段落目录解读（两份投影头部目录 + 实测）

| 段 | attempt_1（总 12,353 字符） | attempt_2（总 12,921 字符） | 性质 |
|---|---|---|---|
| `## System Message` | 18 字符（0.1%） | 18 字符（0.1%） | 空壳段：原文开头即 `## System Message` 紧接子标题 `# System-Level Constraints`，18 字符即标题行本身（`head -c 400 … \| cat -v` 实测） |
| `# System-Level Constraints (不可违反)` | 333（2.7%） | 333（2.6%） | 规则：6 条通用纪律 |
| `## User Message` | 1,262（10.2%） | 1,262（9.8%） | 任务书：职责 + 8 条铁律 + 输出字段说明 |
| `## Runtime Input` | 10,362（83.9%） | 10,362（80.2%） | 数据：JSON 载荷（两 attempt 逐字节一致） |
| `## 输出字段规格…` | 168（1.4%） | 168（1.3%） | 规则：2 个输出字段形状 |
| `## Response Rules` | 210（1.7%） | 778（6.0%） | 规则；attempt_2 因末尾追加 568 字符重试反馈块而膨胀（反馈块无独立标题，投影并入此段） |

三分法汇总（attempt_1）：任务书 1,262（10.2%）；规则类 333+168+210=711（5.8%）；数据 10,362（83.9%）。材料大头是数据，符合"收束员"职责（对 10 张事件卡写总结）。

### Runtime Input 内部构成（实测，pretty JSON 10,343 字符）

- `event_cards` 数组：9,314 字符（90.1%）；`output_contract` 269；`boundary` 256；其余为 `effective_date`/`card_count`/`title_only_card_count`。
- 逐卡大小（payload.json 实测）：MSFT 卡（a04c）2,170 字符，为最大单卡（占卡片数组 23%），也是 10 张中唯一"有全文且未自述与判断对象无关"的卡；其余 9 张在 658–844 字符之间。
- 卡片数组里每张卡固定 11 个键：`citation, event_date, event_id, fact_summary, financial_link, interpretation, limitations, published_at, raw_text_available, source, tier`。

### 两 attempt 差异

- `diff full/…/attempt_1.prompt.txt full/…/attempt_2.prompt.txt` 全文输出仅一处：`232a233,246`，即 attempt_2 在 Response Rules 之后追加 14 行：`上一次返回未通过结构校验，错误如下：` + attempt_1 的 parse_error 消息全文 + `请仅输出修正后的 JSON 对象，不要附加任何解释。`
- payload.json 侧印证：attempt_1 的 `retry_feedback` 为空字符串，attempt_2 的 `retry_feedback` 为 520 字符错误消息；两边 `payload` 子树序列化比对完全相等（9,213 字符紧凑 JSON）。
- `full/` 两份 prompt 的 sha256 与 manifest 记录一致（`74e13bc3…`、`cb0fc500…`），原文副本可信。

## 发现清单

> 以下只记事实与线索，不定级、不开方。行号未特别说明时指 `full/event_section_summary/attempt_1.prompt.txt`（attempt_2 相同内容行号一致，唯一差异在末尾反馈块，见发现 11）。

### 发现 1：任务书声称卡片含"机制假设"，但 10 张卡实际字段中没有这个键

- 证据 A（`attempt_1.prompt.txt:14`）：
  ```
  你是外部世界材料层的收束员。本轮的事件解读卡已经全部生成完毕（每张卡含事实摘要、解读、机制假设、来源等级）；…
  ```
- 证据 B（命令 `python3` 对 `attempt_1.payload.json` 的 `payload.event_cards` 取全部键的并集，输出照抄）：
  ```
  ['citation', 'event_date', 'event_id', 'fact_summary', 'financial_link', 'interpretation', 'limitations', 'published_at', 'raw_text_available', 'source', 'tier']
  含 mechanism/机制 字样的键: []
  ```
- 事实：任务书描述每张卡含"事实摘要、解读、机制假设、来源等级"四样；卡片实际键中，"事实摘要≈fact_summary、来源等级≈tier"可对应，"机制假设"无任何同名字段（最近的只有 interpretation/financial_link）。同时卡片实际还有任务书未提及的 4 个键（citation、financial_link、limitations、event_date 等）。任务书第二段（L16）确实解释了 raw_text_available/limitations/published_at/event_date，但"机制假设"始终无落点。

### 发现 2：系统级约束第 4、5 条引用的键（evidence_refs / raw_data / NO_DATA_AVAILABLE）在本站输入与输出中均不存在

- 证据（命令：对 `attempt_1.prompt.txt` 全文统计关键词出现次数并打印上下文，输出照抄）：
  ```
  'NO_DATA_AVAILABLE' 出现 1 次   → 行10（约束5）
  'raw_data' 出现 1 次           → 行9（约束4）
  'evidence_refs' 出现 1 次      → 行9（约束4）
  ```
  行9：`4. 所有 evidence_refs 必须来自本次输入的 raw_data，不得凭记忆添加。`；行10：`5. 若输入出现 \`NO_DATA_AVAILABLE\`，只能把它当作数据边界…`
- 事实：三个关键词各只出现 1 次，且全部位于系统约束模板本身。实测输入顶层键为 `['effective_date', 'event_cards', 'card_count', 'title_only_card_count', 'output_contract', 'boundary']`（无 `raw_data`）；输出契约只有 `summary_text`、`cited_event_ids`（无 `evidence_refs`）；输入数据里也真实不存在 `NO_DATA_AVAILABLE` 占位。约束 4/5 对本站是引用不存在之物的模板条文。

### 发现 3：`cited_event_ids` 的必填性在不同小节表述不一致

- 证据（`grep -n "cited_event_ids" attempt_1.prompt.txt` 输出照抄）：
  ```
  30:- `cited_event_ids`：正文中实际引用过的 event_id 列表（与正文一致，缺一不可、多一不可）。
  210:    "cited_event_ids": [
  225:- `cited_event_ids`（可选）：数组，元素为 字符串 —— 正文实际引用的 event_id 列表
  230:- JSON 顶层字段必须匹配: summary_text, cited_event_ids。
  ```
  另有 L28：`输出 JSON，只含两个字段：`
- 事实：L225「输出字段规格」把 `cited_event_ids` 标为**可选**；L230「Response Rules」要求顶层字段必须匹配这两个字段；L28 称"只含两个字段"。三处对同一字段的必填性口径不一（可选 vs 必须出现）。字段规格自己声明"形状以此为准"（L223 标题），而 Response Rules 说"形状冲突时以规格为准"（L231）。

### 发现 4：降级措辞要求自相顶牛——"必须带指定词"与"措辞完全由你决定"并存

- 证据：
  - L21：`…弱来源（非官方）转述必须带"据报道"或"该媒体称"。`
  - L219（boundary.note）：`"本轮 10 张卡中有 7 张 raw_text_available=false（仅标题，未读全文），引用这些卡时必须带降级措辞（据报道/该媒体称/仅标题）。"`
  - L23：`…**措辞完全由你决定，没有固定说法要套，也不会有措辞检查**——报告会由代码在每条事件旁自动标出来源等级与"仅标题与片段·降级阅读"。你要保证的是判断的分寸，不是用词。`
- 事实：L21 与 L219 两处规定必须携带指定降级用词（"据报道"/"该媒体称"/"仅标题"），L23 又声明"没有固定说法要套、也不会有措辞检查"。L21 针对"弱来源（非官方）转述"、L23 针对"raw_text_available=false 或非官方来源的卡"——适用对象大面积重叠（本轮 7 张仅标题卡全部是非官方来源），两处指令对同一张卡同时给出"必须带固定词"与"没有固定说法"。

### 发现 5：同一条边界句与引用格式规则在 4–6 个小节重复出现

- 证据（命令输出照抄）：
  ```
  边界句逐字出现次数: 2          （"以上事件材料不构成主证据，判断以数据层为准。"）
  '边界句': 3 次 / '边界声明': 1 次 / '[card:<event_id>]': 2 次 / '[card:...]': 2 次 / '原样抄': 1 次
  ```
- 事实（逐处定位）：结尾边界句要求出现在 ① L25 任务书铁律（逐字全文）；② L209 `output_contract.summary_text`（"含引用与结尾边界句"）；③ L218 `boundary.must_end_with`（逐字全文）；④ L224 字段规格（"含 [card:<event_id>] 引用与结尾边界句"）。引用格式规则出现在 ① L20（`[card:<event_id>]` 格式 + event_id 来源限制 + 引用 2–5 张）；② L29–30（输出字段说明）；③ L209（"引用一律原样抄 event_cards[].citation 字段的值，不要自行拼接、不要删改 id（本轮示例：…）"）；④ L210–212（`output_contract.cited_event_ids` 说明）；⑤ L224；⑥ L230。指令实际要求消费的方式只有一种（写一段含引用、以边界句结尾的总结），同一规则在任务书、数据内嵌契约（output_contract/boundary）、字段规格、Response Rules 四处层面反复陈述。

### 发现 6：每张卡的 `citation` 字段都是 `event_id` 的机械包装，数据级重复

- 证据（命令：校验全部卡片 `citation == "[card:"+event_id+"]"`，输出照抄）：
  ```
  event_id 唯一: True
  citation 全部等于 "[card:"+event_id+"]": True
  ```
- 事实：10/10 张卡的 citation 串可由 event_id 套固定模板生成（每条约 29 字符，合计约 290 字符）。材料同时携带两者，而 L209 又要求"原样抄 citation、不要自行拼接"——即数据里冗余了一份派生串，指令再禁止接收方自己派生。

### 发现 7：同一 `event_cards` 数组内 `published_at` 存在三种时间格式

- 证据（命令：按正则归类，输出照抄）：
  ```
  ISO8601 1 张: 52a4 2026-07-30T16:21:56Z
  RFC2822-+0000 7 张: b582 Thu, 30 Jul 2026 16:11:06 +0000 ...
  RFC2822-GMT 2 张: 953b Thu, 30 Jul 2026 15:00:00 GMT ...
  ```
- 事实：同一键在同一数组里有三种序列化形态（ISO8601 / RFC2822 带 +0000 / RFC2822 带 GMT 字样）。任务书 L16 要求模型依据 `published_at`/`event_date` 做时间判断，但未提供统一格式。

### 发现 8：AAPL 日历卡（ef79ac6a9ed352a4）的 `published_at` 与本次 run 启动时刻秒级重合

- 证据（命令输出照抄）：
  ```
  本机时区: ('CST', 'CST') -28800
  20260731_002156 按本地(UTC+8) 折算 UTC 时间戳: 1785428516.0
  "2026-07-30T16:21:56Z" 的 UTC 时间戳: 1785428516
  ```
  卡片字段（投影 attempt_1 L61–63 照抄）：`"source": "Yahoo Finance earnings dates + deterministic estimated blackout rule", "tier": "third_party_calendar", "published_at": "2026-07-30T16:21:56Z"`
- 事实：run 目录名 `20260731_002156`（本机时区 UTC+8 的 2026-07-31 00:21:56）折算成 UTC 与该卡 `published_at` 精确到秒相同。该卡是 10 张中唯一 ISO8601 格式、唯一 third_party_calendar 来源、且由"确定性规则推算"生成的卡——其 `published_at` 数值等于 run 启动时刻，而非一个独立的来源发布时间。任务书 L32 称 `published_at` 为"材料时间"。

### 发现 9：MSFT 卡（b8f43b7603daa04c）`fact_summary` 内有两处"首次突破 1000 亿美元"，指标名不同

- 证据（命令：从 payload 提取该卡全串，长度实测 fact_summary 934 字符、interpretation 713 字符；关键原文照抄）：
  - 头部：`Microsoft (MSFT) stock rose approximately 13% on quarterly earnings. Revenue increased 18% YoY; cloud computing revenue exceeded $100B for the first time.`
  - 尾部：`Azure revenue surpassed $100B for the first time; M365 Copilot reached over 30M paid seats.`
- 事实：同一 `fact_summary` 内，"cloud computing revenue exceeded $100B for the first time" 与 "Azure revenue surpassed $100B for the first time" 并存——同一里程碑表述、两个不同指标名，材料自身未说明二者关系。另注：投影省略的 754 字符中段（«…省略 754 字符…»，投影 L124）含该卡几乎全部硬数字（Q4 营收 $90B/净利 $35.76B/+31%/EPS $4.81、FY2026 营收 $331.8B/+18%、八个分部增速、Windows OEM -7%/Xbox -10% 等），该卡 2,170 字符居 10 卡之首。

### 发现 10：材料覆盖偏科——7/10 仅标题、3/10 自述与判断对象无关、有全文且相关的只有 1 张

- 证据（命令输出照抄）：
  ```
  raw_text_available=false 实际: 7 | title_only_card_count 字段: 7
  tier: {'third_party_calendar': 1, 'reliable_mainstream_report': 7, 'official_macro': 2}
  interpretation 含"与判断对象关联不足"的卡数: 3
  ```
  逐卡实测：raw_text=true 的 3 张为 a04c（MSFT，reliable_mainstream_report）、953b 与 331a（均为 Federal Reserve Press Releases/official_macro，且 interpretation 首句均为"与判断对象关联不足"）；第三张自述无关的是 1d35（K2 Space 融资，仅标题）。10 张卡的 source 中 8 张含 "Yahoo Finance"（7 张 M7/QQQ Headlines 标题聚合 + 1 张 earnings dates 日历），2 张为 Fed 新闻稿。
- 事实：任务要求"至少引用两张、至多五张最有分量的卡"（L20），而材料里"有全文且未自述无关"的卡仅 MSFT 一张；官方来源（official_macro）两张均为与 NDX 自述无关的银行执法个案。材料分布实测：仅标题 70%、自述无关 30%、单一聚合来源（Yahoo Finance 系）占 80%。

### 发现 11：重试反馈块（attempt_2 唯一增量）的错误定位提示与实际语法错误不符；两 attempt 以同一模式失败

- 证据 A（`diff` 全文输出仅 `232a233,246`，attempt_2 末尾追加 14 行，照抄首尾）：
  ```
  上一次返回未通过结构校验，错误如下：
  event_section_summary did not return a parseable JSON object. 原始响应字符数: 1020. 响应末尾片段（用于定位 JSON 语法错误，请检查最后未闭合的数组、对象或字符串）：
  …
  请仅输出修正后的 JSON 对象，不要附加任何解释。
  ```
- 证据 B（命令：`python3 json.loads` 校验两份原始响应，输出照抄）：
  ```
  attempt_1.response.raw.txt JSONDecodeError: Expecting ',' delimiter: line 2 column 228 (char 229)
    around error: '…自由现金流[card:event:b8f43b7603daa04c]。这为"AI投资究竟是价值破坏还是生产性资本支出"这一竞争假说…'
  attempt_2.response.raw.txt JSONDecodeError: Expecting ',' delimiter: line 2 column 213 (char 214)
  ```
- 证据 C（meta.json L8/L18–30 照抄要点）：`"status": "failed"`，两个 attempt 的 `kind` 均为 `parse_error`。
- 事实：①反馈块提示"请检查最后未闭合的数组、对象或字符串"并展示响应**末尾**片段，而该末尾片段（`…为准。",\n "cited_event_ids": [ … ]\n}`）结构完整闭合；实际首个语法错误位于响应第 229 字符（全长 1,020，约 22% 处）——`summary_text` 字符串内一个未转义的 ASCII 双引号（这为"AI投资…），错误类型是"字符串内未转义引号"而非"末尾未闭合"。②反馈块不含错误位置信息，只给末尾片段。③attempt_2 在拿到该反馈后仍以同一模式失败（char 214 处同样未转义引号）。④反馈块把 attempt_1 的输出片段（约 400 字符，含正文措辞与完整 cited_event_ids 列表）带入了 attempt_2 的材料。

### 发现 12（核验通过项）：计数、唯一性、时间纪律、attempt 间一致性的阴性结果

- 证据（命令输出照抄）：
  ```
  event_cards 实际张数: 10 | card_count 字段: 10
  raw_text_available=false 实际: 7 | title_only_card_count 字段: 7
  boundary.note: 本轮 10 张卡中有 7 张 raw_text_available=false…
  event_id 唯一: True
  event_date 集合: ['2026-07-29', '2026-07-30'] | effective_date: 2026-07-30
  Runtime Input(payload) 两 attempt 完全一致: True
  ```
- 事实：`card_count`/`title_only_card_count`/`boundary.note` 三处计数与卡片实际一致；event_id 无重复；全部卡片的 event_date/published_at 不晚于 effective_date（2026-07-30），材料内无未来日期；两 attempt 的数据载荷逐字节一致（差异仅反馈块）。同一指标在不同位置出现不同值的情况：未发现（核心 PCE +3.3%、MSFT +18%/$19.6B 等在卡内 fact_summary 与 interpretation 间取值一致）。

### 发现 13：指令散文自身用 ASCII 双引号包裹中文短语（22 处），而该写法放进 JSON 字符串值即非法——与两次失败的形态同构

- 证据（命令：对 `attempt_1.prompt.txt` 分区统计引号字符，输出照抄）：
  ```
  散文区(User Message) 全角引号 “”: 0 个; ASCII ": 22 个
  Runtime Input 区 ASCII "(含JSON语法): 466 个; 转义 \": 4 处
  Runtime Input 区 全角引号: 0 个
  ```
  散文区实例（照抄）：L9 `使用条件语言（"可能""若...则..."）或定性表达`；L21 `禁止写成已经发生的因果（"因为X所以指数Y"是禁句式）。弱来源（非官方）转述必须带"据报道"或"该媒体称"。`
- 事实：提示词散文通篇以 ASCII `"` 当中文引号用（任务书 22 处、系统约束区亦然）；数据区 JSON 字符串内另有 4 处正确转义的 `\"` 示范（如 f17f 卡 `\"AI's Biggest Winners Are Selling Off…\"`、`\"反常\"`）。约束 6（L11）要求"输出严格合法的 JSON"，但全文未提示"正文中的引号需要转义/避免"。两次 parse_error 的出错点均为 `summary_text` 内未转义的 ASCII `"`（char 229 / char 214），其用法（这为"AI投资究竟是…"）与指令散文的引号用法同构。

## 盲区

1. **投影散文部分未逐字节比对原文**：我信任了投影规则声明（"散文逐字保留"），仅核验了：①两份投影的省略标记确实只有 2 处（grep `省略|__omitted__|__total__|__table_projection__`，均命中 MSFT 卡同两行）；②2 处省略已回查 payload 原文全串（发现 9）；③`full/` 两 prompt 的 sha256 与 manifest 一致；④两 attempt 原文 `diff` 仅差末尾反馈块。投影与原文之间散文的逐字节一致性本身未独立验证。
2. **段落目录的字符量未独立复算**：目录中各段字符数/占比（如 Runtime Input 10,362 字符、83.9%）为投影工具自报。我用 `json.dumps(payload, indent=2)` 复算 Runtime Input 得 10,343 字符，与自报差 19 字符，差异来源未追（可能为键序/序列化细节）。
3. **未读 `prompt_audit/` 原始目录**：`full/` 声明复制自 `prompt_audit/event_section_summary/`（投影头第 2 行），我以 sha256 对账代替直读原目录。
4. **上游成因未追**：published_at 为何三种格式、日历卡 published_at 为何等于 run 启动时刻、citation 为何冗余派生、"机制假设"措辞来自哪个模板、约束 4/5 模板为何本站不适用仍注入——这些成因在 `src/` 代码侧，本阶段任务边界为材料结构本身，未查代码。
5. **产出失败的行为根因不归因**：模型为何两次都输出未转义引号（是模仿散文引号习惯还是其他原因）属产出侧行为分析，我只记录材料侧事实（发现 11、13），不做因果断定。
6. **产出合规性未逐条核验**：两份响应的 summary_text 是否落在 100–1500 字、引用 2–5 张等要求是否满足，属产出评价，未系统核验（仅注意到两次响应均引用 5 张卡、均含结尾边界句）。
7. **effective_date 与 run 时刻的关系未深究**：meta.json 记 `effective_date: 2026-07-30`、`mode: latest`，run 目录为 2026-07-31 00:21:56（本地），二者约差 8 小时的语义（为何 latest 对应前一日）未追查。
8. **其他 24 站未读**：跨站重复（如同一事件卡是否也喂给别的站、约束模板是否全站通用）超出本片边界，未看。

—— 报告完 ——
