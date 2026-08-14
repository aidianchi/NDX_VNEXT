# event_card_interpreter.event_0a457426cdb8f17f 通读报告

## 通读范围

- 语料根目录：`/Users/aidianchi/Desktop/ndx_mac/output/analysis/vnext/20260731_002156/context_spread/`
- 读了哪些文件、怎么读的：
  1. `projected/event_card_interpreter.event_0a457426cdb8f17f/attempt_1.projection.md` —— **全文逐行读**（146 行，8,708 字节）。
  2. `full/event_card_interpreter.event_0a457426cdb8f17f/attempt_1.prompt.txt` —— **全文逐行读**（130 行，4,977 字符 / 7,966 字节）。提示词原文。
  3. `full/.../meta.json` —— 全读（36 行）。含 model=deepseek-v4-flash、status=ok、prompt_chars=4977、effective_date=2026-07-30。
  4. `full/.../attempt_1.parsed.normalized.json` —— 全读（31 行）。站的实际输出，仅作旁证，不作评价对象。
  5. `full/.../attempt_1.payload.json` —— **逐键程序化核对**（非逐字读）：用 python 遍历全部键路径打印值，确认它就是 Runtime Input 的 JSON 外加 stage_key/stage_name/attempt/retry_feedback 包装，无 prompt.txt 之外的隐藏内容。
  6. `context_spread/manifest.json` —— 程序化提取本站条目：`inspector_has_rules: false`（本站此前无机械检查规则）、`verification_ok: true`、`projection_ratio: 0.9825`、sha256 与文件清单一处不差。
- 抽查口径：无抽查——提示词全文仅 4,977 字符，投影与原文均全读；投影 3 处可能截断点中本站只出现 1 处（cth_01 中段 «…省略 100 字符…»），已在原文查到全文。
- 投影保真核验：投影正文 130 行与原文 130 行逐行 difflib 比对，**仅第 62 行（cth_01 hypothesis_text）有截断差异，其余 129 行全同**。
- 代码侧核验（只读，为验证提示词内的声明）：`src/agent_analysis/vnext_reporter.py:3890-3915`、`src/agent_analysis/prompts/event_card_interpreter.md:7`。

## 材料结构总览

原文 4,977 字符，布局 standard（manifest），一次 attempt 成功（status=ok）。段落目录与实测字符量（实测与投影头部目录一致）：

| 段落 | 字符 | 占比 | 内容 |
|---|---|---|---|
| `## System Message`（含 `# System-Level Constraints`） | 351 | 7.1% | 6 条通用纪律（目录把表头 18 字符与约束 333 字符分列） |
| `## User Message` | 605 | 12.2% | 任务书：事件解读员职责 + 5 条铁律 |
| `## Runtime Input` | 2,744 | 55.1% | 输入 JSON（下表细分） |
| `## 输出字段规格` | 906 | 18.2% | EventInterpretationCard 契约 12 字段清单 |
| `## Response Rules` | 371 | 7.5% | 4 条输出形式规则 |

Runtime Input 内部细分（实测，占全提示词比例）：

- `event_material` 563 字符（11.3%）——其中**被解读对象本体（标题）仅 69 字符**；`raw_text_available: false`、`raw_text_excerpt: ""`，无正文。
- `allowed_financial_links` 243 字符（4.9%）——9 个金融传导渠道。
- `competing_hypotheses` 888 字符（17.8%）——3 条假说（1 leading + 2 candidate），hypothesis_text 合计 534 字符，**全提示词所有具体市场数值（12 组）只出现在这里**。
- `output_contract` 909 字符（18.3%）——输出契约的 JSON 示例形态。
- `boundary` 130 字符（2.6%）——3 个布尔旗标。

解读：这是一份"小材料、大规则"的提示词——要解读的事件只有一行标题（69 字符），任务书+规则+契约占约 44.9%，背景假说占 17.8%。契约类内容（output_contract + 输出字段规格 + Response Rules 字段行）合计约 2,000 字符（约 40%），超过事件材料本身 3 倍以上。

## 发现清单

> 以下只列事实与线索，不定严重度、不开处方。行号均指 `full/event_card_interpreter.event_0a457426cdb8f17f/attempt_1.prompt.txt`。

### 发现 1：输出契约在站内以三种形态重复出现（结构性冗余）

事实：同一份 EventInterpretationCard 契约出现三次——① Runtime Input 内 `output_contract` JSON 示例（prompt.txt 第 71-103 行，907 字符，占全提示词 18.3%）；② `## 输出字段规格` 清单（第 111-123 行，906 字符，18.2%）；③ `## Response Rules` 第 128 行顶层字段列表（208 字符）。三者合计约 2,021 字符（约 40.6%）。Response Rules 第 129 行自己承认两种形态可能冲突："正文里的示例只解释语义，形状冲突时以规格为准"。

证据命令与输出：
```
$ python3 (分段测量，见"材料结构总览")
output_contract          chars=  909 share_of_prompt=18.3%
## 输出字段规格  chars= 906 share=18.2%
line 128 chars: 208 -> - JSON 顶层字段必须匹配: event_id, fact_summary, ...
```

### 发现 2：弱来源措辞规则两处自相矛盾（声明与声明打架）

事实：User Message 铁律第 4 条（第 20 行）说"**措辞完全由你决定，没有固定说法要套**……这里不设措辞检查"；但 Runtime Input `output_contract` 的 `interpretation` 示例值（第 74 行）写着"模型解读；弱来源以据报道或该媒体称开头"——给弱来源规定了固定开头句式。Response Rules 第 129 行的"示例只解释语义、形状冲突以规格为准"只裁断形状冲突，不裁断这条语义层面的措辞矛盾；两处规则同时有效时模型遵哪条，文本未给出答案。

证据命令与输出：
```
$ grep -n "据报道\|该媒体称\|措辞完全由你决定\|没有固定说法" attempt_1.prompt.txt
20:- 来源不是官方披露的、或材料只有标题没有正文的……**措辞完全由你决定，没有固定说法要套**……所以这里不设措辞检查。
74:    "interpretation": "模型解读；弱来源以据报道或该媒体称开头",
```
旁证（实际输出选了哪边）：`attempt_1.parsed.normalized.json` 第 4 行 interpretation 以"仅据标题推测"开头——既非"据报道"也非"该媒体称"，即实际遵循了 User Message 一侧。

### 发现 3：系统约束第 4、5 条引用输入与输出中均不存在的字段（无作用对象的规则）

事实：System 约束第 4 条（第 9 行）"所有 evidence_refs 必须来自本次输入的 raw_data"——但输入 JSON 顶层键只有 event_material / allowed_financial_links / competing_hypotheses / output_contract / boundary，无 `raw_data`；输出契约 12 字段中也无 `evidence_refs`。第 5 条（第 10 行）针对 `NO_DATA_AVAILABLE` 标记——该标记在输入中未出现；本站实际的空数据是用 `raw_text_available: false` + `raw_text_excerpt: ""`（第 36-37 行）表达的。这两条约束在本站材料里找不到任何可作用的键。

证据命令与输出：
```
$ grep -n "evidence_refs\|raw_data\|NO_DATA_AVAILABLE" attempt_1.prompt.txt
9:4. 所有 evidence_refs 必须来自本次输入的 raw_data，不得凭记忆添加。
10:5. 若输入出现 `NO_DATA_AVAILABLE`，只能把它当作数据边界或置信度限制……
（全文仅此 2 行命中）
```

### 发现 4：任务书 framing 承诺"正文摘录"，实际材料里正文为空

事实：User Message 开头（第 14 行）"给你一条已经采集好的事件材料（标题、来源、日期、正文摘录）"——把"正文摘录"列为材料的标准组件；但 event_material 里 `raw_text_available: false`、`raw_text_excerpt: ""`（第 36-37 行），本条事件没有正文摘录。铁律第 4 条（第 20 行）对"只有标题没有正文"的情形另有降级措辞规则兜底，即空正文是规则覆盖内的情形，但 framing 句的组件清单与本条实况不符。

证据：prompt.txt 第 14 行 vs 第 36-37 行（原文照抄）：
```
14:你是外部世界材料层的解读员。给你一条已经采集好的事件材料（标题、来源、日期、正文摘录）……
36:    "raw_text_available": false,
37:    "raw_text_excerpt": "",
```

### 发现 5：待解读材料与背景材料体量倒挂，且全部具体数值只存在于背景假说中

事实：被解读对象本体（事件标题）69 字符；`event_material` 整块 563 字符（11.3%）。`competing_hypotheses` 三条假说正文合计 534 字符（约为标题的 7.7 倍），其中携带全提示词仅有的 12 组具体市场数值：实际利率 99.4%分位、Forward PE 19.46、盈利修正 30 日 +4.2% / 90 日 +10.7%、M7 资本开支同比 +75%、RSI 32.4、MA200、HY OAS 31%分位、supplier_lookback 30d flagged 权重 41%、M7 回购同比 -68.74%。铁律（第 17 行）要求 `fact_summary`"只许出现材料里逐字有的东西"，而事件材料侧可逐字引用的只有标题、来源、三个日期；数值面全部由假说侧供给。

证据命令与输出：
```
$ python3 (数值 token 全文提取 Counter)
[('99.4%', 1), ('19.46', 1), ('+4.2%', 1), ('+10.7%', 1), ('+75%', 1), ('32.4', 1),
 ('200', 1), ('31%', 1), ('41%', 1), ('-68.74%', 1), …全部唯一，且均落在第 57/62/67 行（三条 hypothesis_text）]
event_material.title chars: 69
hypothesis_text total chars: 534
```

### 发现 6：九条金融传导渠道清单出现两次（重复，但两处一致）

事实：`allowed_financial_links` 作为输入数据出现于第 43-53 行（243 字符）；同 9 项同顺序又以枚举字面量内嵌进输出字段规格第 117 行（`financial_link:"earnings_path"|…|"technical_flow"`）。逐值比对一致，无冲突。

证据：prompt.txt 第 43-53 行与第 117 行原文对照（已逐值核对）。

### 发现 7：两个输入块无任何指令引用、不映射任何输出字段

事实：`trigger_reasons: ["mainline","inquiry_reference"]`（第 38-41 行）与 `boundary` 三旗标（第 104-108 行：event_ref_only / must_not_become_l1_l5_evidence_ref / must_not_feed_back，约 130 字符）在全文grep下只出现在 JSON 数据里——System 约束、User Message、输出契约、字段规格、Response Rules 均未提及这些键，也不要求模型对它们做任何事。

证据命令与输出：
```
$ grep -n "trigger_reasons\|boundary\|event_ref_only\|must_not_become\|must_not_feed_back" attempt_1.prompt.txt
38:    "trigger_reasons": [
104:  "boundary": {
105:    "event_ref_only": true,
106:    "must_not_become_l1_l5_evidence_ref": true,
107:    "must_not_feed_back": true
$ grep -n "mainline\|inquiry_reference" attempt_1.prompt.txt
39:      "mainline",
40:      "inquiry_reference"
（两组键均只在数据行命中，零指令行命中）
```

### 发现 8："弱来源"分档被两处规则引用，但材料未给判定标准

事实：第 20 行按"来源不是官方披露的"分档、第 74 行按"弱来源"分档；材料给出 `tier: "reliable_mainstream_report"`（第 30 行，全文仅出现 1 次），但提示词内没有 tier 取值清单，也没有"哪个 tier 算弱来源/算官方披露"的映射。本事件 tier 为可靠主流媒体转述，是否触发第 74 行的"弱来源"句式，从材料本身无法判定。

证据命令与输出：
```
$ grep -c "reliable_mainstream_report" attempt_1.prompt.txt
1
$ grep -n "tier" attempt_1.prompt.txt
30:    "tier": "reliable_mainstream_report",
98:      "tier": "照抄 event_material.tier",
123:- `passport`（必填）：对象 EventInterpretationPassport{source, tier, …}
```

### 发现 9：Response Rules"顶层字段必须匹配"列出全部 12 字段，其中 6 个在规格里标注"可选"

事实：字段规格（第 115-122 行）把 entities / supports_hypotheses / refutes_hypotheses / limitations / needs_data_confirmation / upgrade_candidate 标为"可选"；但 Response Rules 第 128 行"JSON 顶层字段必须匹配:"后列出含这 6 个在内的全部 12 字段。"必须匹配"指字段集合对齐还是 12 个全必填，文本未区分。

证据：prompt.txt 第 115-122 行（6 处"可选"）vs 第 128 行（12 字段全列）。旁证：实际输出（parsed.normalized.json）12 字段全给齐，含空数组 `refutes_hypotheses: []`。

### 发现 10：以下核查项未发现矛盾（查过、干净）

- 日期内部一致：`published_at: "Wed, 29 Jul 2026 22:57:32 +0000"`——`python3` 验证 2026-07-29 确为 Wednesday；event_date 2026-07-29、effective_date 2026-07-30 与 22:57 UTC 发布时间顺序自洽。
- 数值无重复矛盾：全文数值 token 提取后每个定量声明只出现一次，无同一指标不同值（见发现 5 的 Counter 输出）。
- "代码自动标注"声明有实证：User Message 称"报告会由代码在每条事件旁自动标出来源等级与'仅标题与片段·降级阅读'"——代码实证存在：`src/agent_analysis/vnext_reporter.py:3903`（`read_state = "已读正文" if interpretation_card and str(card.get("raw_text_excerpt") or "").strip() else "仅标题与片段 · 降级阅读"`，其中 `card` 是原始事件卡，该卡确有 raw_text_excerpt 字段）；User Message 措辞与模板 `src/agent_analysis/prompts/event_card_interpreter.md:7` 一致。
- 九渠道枚举：输入数据与字段规格两处完全一致（发现 6）。
- 投影保真：投影正文与原文 130 行逐行 diff，仅第 62 行 cth_01 hypothesis_text 一处 «…省略 100 字符…»，其余全同；省略段已在原文核到全文。

## 盲区

- 投影截断：本站投影仅 1 处截断（cth_01 hypothesis_text 中段 «…省略 100 字符…»），已在原文核到全文（"价格在MA200上方并接近Donchian下轨……主线对信用尾部风险的重"，实测正好 100 字符）。无未查的截断。
- `attempt_1.payload.json` 未逐字通读，而是用 python 逐键遍历打印全部值核对——确认它 = Runtime Input 的 JSON + stage 包装（stage_key/stage_name/attempt/retry_feedback），无 prompt.txt 之外的额外提示内容。
- 代码侧只做了存在性核验（vnext_reporter.py:3903 的标注逻辑确实存在于代码库），**未验证该代码路径在本次 run（20260731_002156）中确实执行**，也未验证生成 output_contract 示例值（"弱来源以据报道或该媒体称开头"）的代码/模板出处——该矛盾的两条文本各自从何而来未追溯。
- 未读其他 24 站的任何材料（纪律限制），因此无法判断发现的通用约束段（System 6 条）、契约三形态重复等是本站独有还是全 run 通病。
- manifest 显示本站 `inspector_has_rules: false`（此前无机械检查规则），本报告全部结论来自人工通读。
- `output.validated.json` / `attempt_1.response.raw.txt` 与 parsed.normalized.json 同 sha256（manifest files 段），故只读了 parsed 一份。
