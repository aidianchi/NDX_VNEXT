# controlled_investigation 通读报告

（T47 上下文根本性审查·阶段一逐站通读。本报告边查边写，各节完成后即时落盘。）

## 通读范围

本站 = `controlled_investigation`，共 3 个调查实例、4 个提示词文件（inv_e75efe82e7c0 有 attempt_1/attempt_2 两次）。

通读方式：**4 个投影文件全部逐行通读；4 个原文 prompt 全文逐行通读**（原文仅 5.0K/5.0K/13.0K/13.1K 字符，全读无抽查）。辅以 `manifest.json` 本站条目、两次失败的 `error.json`、以及 run 目录里材料来源 artifact 的抽查核对。

| 文件 | 原文字符 | 投影字符 | 投影比 | 读法 |
|---|---|---|---|---|
| inv_ae806095c18a.attempt_1 | 5,013 | 4,743 | 94.6% | 投影全读 + 原文全读 |
| inv_c4c2b3b067ff.attempt_1 | 5,048 | 4,798 | 95.0% | 投影全读 + 原文全读 |
| inv_e75efe82e7c0.attempt_1 | 13,012 | 11,812 | 90.8% | 投影全读 + 原文全读 |
| inv_e75efe82e7c0.attempt_2 | 13,122 | 11,922 | 90.9% | 投影全读 + 原文全读 |

manifest 本站条目（命令：`python3 -c` 读 `context_spread/manifest.json` 过滤 stage==controlled_investigation）显示 4 个实例全部 `inspector_has_rules: false`、`inspector_can_read: false`、`verification_ok: true`，即这站此前没有任何机械检查规则。inv_e75efe82e7c0 两次 attempt 都带 `error.json`（校验失败重试）。

文件路径根：`/Users/aidianchi/Desktop/ndx_mac/output/analysis/vnext/20260731_002156/context_spread/`（下文 `projected/`、`full/` 均为相对此根的相对路径）。


## 材料结构总览

### 同构性（3 实例 4 文件共用骨架）

4 份提示词共用同一段文字骨架，逐字相同：

- **指令块**（角色+铁律+输出 JSON 字段说明）：每份 761 字符，占 ae/c4 的 15.2%/15.1%，占 e7 两次的 5.8%。命令：`python3` 切片量得 `instructions(0..调查问题)=761`（四份一致，ae/c4/e7a1 实测输出见下）。
- **调查问题区**：55（ae）/ 90（c4）/ 50（e7a1）字符，仅一行问题。
- **材料区**：`允许材料（只能依据以下内容）：` + `[M#] artifact=<文件名>` + JSON 体 + `[/M#]`。ae/c4 各 4,018 字符（1 份材料），e7a1 为 12,022 字符（3 份材料）。
- **尾部纪律行**（材料编号纪律）：每份 179 字符，逐字相同。

实测输出（命令：`python3` 对 3 份原文按 `调查问题：`/`允许材料`/`材料编号纪律` 切分量长度）：

```
== ae: total=5013  instructions(0..调查问题)=761  问题区=55  材料区=4018  尾部纪律=179
== c4: total=5048  instructions(0..调查问题)=761  问题区=90  材料区=4018  尾部纪律=179
== e7a1: total=13012  instructions(0..调查问题)=761  问题区=50  材料区=12022  尾部纪律=179
```

e7 attempt_2 与 attempt_1 的原文差异仅在末尾追加 110 字符的重试说明（命令：`diff inv_e75efe82e7c0.attempt_1.prompt.txt inv_e75efe82e7c0.attempt_2.prompt.txt`，输出仅第 414 行后多出 `上一次输出未通过 JSON/合约校验。…ValueError: claims_supported[0] missing [M#] material citation`；`python3` 验证共同前缀 13,012 字符 = attempt_1 全长）。

### 各实例差异

| 实例 | 调查问题 | 材料份数 | 材料来源 artifact |
|---|---|---|---|
| inv_ae806095c18a | M7 回购 -68.74% 季节性/趋势性 | 1 | bridge_memos/bridge_0.json |
| inv_c4c2b3b067ff | supplier_lookback 数据质量 | 1 | bridge_memos/bridge_0.json（同一文件） |
| inv_e75efe82e7c0（×2） | AI/半导体链条是否同步改善 | 3 | cross_layer_questions.json / event_layer_summary.json / event_mechanism_report.json |

### 投影的"段落目录"解读

4 个投影的 `## 段落目录（标题 · 字符量 · 占比）` 下面**全部为空**（命令：`python3` 抽取 4 个投影该节内容，输出均为 `''`）。原因是提示词正文没有任何 markdown 标题，目录工具无段可列。因此本站的材料分布图无法从投影目录获得，上表分布为我按标记行切分实测。

投影保真度抽查：投影体与原文的首处差异仅为 JSON 缩进（ae 在字符 2514、e7a1 在字符 895 起差异均为缩进空格数），未见内容丢失；投影比例 90.8%–95.0% 的差值主要由投影头部说明文字与重缩进造成。

### 数值一致性抽查

对 ae/c4 两份原文做全量数字 token 提取（命令：`re.findall(r'\d+(?:\.\d+)?(?:%|bp|分位)?')` + Counter），同一指标未出现不同值（如 4.2%×5/×6 均为 30d 盈利修正斜率、99.4% 均为实际利率分位、19.46/30.31 为 Forward/Trailing PE 对）。注意 661.73（"从高位跌至"）与 661.14（Donchian 下轨）是不同指标相邻出现，不构成同指标异值。

### 与其他审查片的分工

inv_ae806095c18a / inv_c4c2b3b067ff 的"铁律第 5 行声明'你不知道系统当前的判断' vs [M1] 内含 `action_implication` 仓位指令"这一矛盾，H3 隔离片已独立发现并覆盖，本报告不重复展开。仅补一句站内事实：e7 实例的三份材料（问题清单/事件簇摘要/机制报告节选）中不存在 `action_implication` 类仓位指令，该矛盾形态在 e7 上不成立。

## 发现清单

（只报事实，不定级、不开方。行号除注明"投影"外均指 `full/controlled_investigation/` 下原文 prompt。）

### 发现 1：全部 7 份材料体在约 3,954 字符处硬截断，JSON 不闭合，断点在字符串/键名/ID 中间

证据：

- `full/.../inv_ae806095c18a.attempt_1.prompt.txt:125-126`：`      "claim": "M7资本开支加速（同比+75%）提供结构` 之后直接接 `[/M1]`（字符串中间断）。
- `full/.../inv_c4c2b3b067ff.attempt_1.prompt.txt:125-127`：`      "conflict_t` 之后接 `[/M1]`（键名中间断）。
- `full/.../inv_e75efe82e7c0.attempt_1.prompt.txt:155-156`：`        "even` 之后接 `[/M1]`（事件 ID 中间断）；`:278-279`：`      "event_cluster_id": "event_cluster:579a673` 之后接 `[/M2]`；`:410-412`：`"event:b807a33cc46abfdd",` 空行后接 `[/M3]`。
- 命令：`python3` 按 `\[M\d\] artifact=` 与 `\[/M\d\]` 切分量体长，输出：`M1 body chars: 3954 | M2: 3956 | M3: 3953`（e7a1）；`ae M1 body chars: 3954  c4 M1 body chars: 3954`。

事实：7 份材料体（ae×1、c4×1、e7×3）长度全部落在 3,953–3,956 字符，且全部在 JSON 中间断开后直接跟 `[/M#]` 闭标记。调查员拿到的每份材料都是不完整 JSON，无法整体解析；能读到什么取决于截断点落在哪里。提示词未以任何形式告知材料被截断。

### 发现 2：e7 的 [M3] 与 [M1] 近似逐字重复，重复内容占该提示词材料区约 66%

证据：

- 命令：`python3` 抽取 e7a1 三个材料体比较，输出：`M1(renamed) vs M3 common prefix chars: 3952 of M1 len 3966`、`M1 lines=130 M3 lines=129 identical-position lines=128`（M1 顶级键 `questions` 改名为 `cross_layer_questions` 后与 M3 逐行前 128 行相同）。
- 源级验证：命令 `python3` 比较 run 目录两个 artifact，输出 `emr.cross_layer_questions[0] == cross_layer_questions.json questions[0]? True`；`event_mechanism_report.json size: 155802`，其顶级键为 `['schema_version','generated_at_utc','headline_judgment','mainlines','news_cards','event_research_cards','cross_layer_questions','claim_permission_ledger','scheduled_future_events','delivery_to_integrated_report']`。

事实：同一份跨层问题清单以两个不同 artifact 名（cross_layer_questions.json 与 event_mechanism_report.json）进了同一提示词，M1 体 3,954 + M3 体 3,953 ≈ 7,908 字符，占材料区 12,022 字符的约 66%。event_mechanism_report.json 其余 8 个顶级段全部未进材料（见发现 6）。

### 发现 3：ae 与 c4 拿到同一 bridge_0.json 的不同键子集裁剪，约 68% 内容相同

证据：命令 `python3` 比较两份 M1 体，输出：`ae/c4 M1 common prefix chars: 2704`（体长均 3,954）；`ae top-level keys: ['unresolved_questions', 'principal_contradiction', 'cross_layer_claims']`、`c4 top-level keys: ['unresolved_questions', 'principal_contradiction', 'key_uncertainties', 'typed_conflicts']`。源文件 `bridge_memos/bridge_0.json` 22,185 字符，顶级键 17 个。

事实：两个不同的调查问题分到的是同一份 bridge 备忘录、相同开头 2,704 字符，然后各自带不同的键子集，各覆盖源文件约 18%，且都在第 3,954 字符处被切断。源键序为 `cross_layer_claims…principal_contradiction…unresolved_questions…`，材料体内键序被重排为 `unresolved_questions` 在前。

### 发现 4：材料包不按调查问题过滤——他案问题及其数字随包分发

证据：

- ae 原文 `inv_ae806095c18a.attempt_1.prompt.txt:28` 含有 c4 的调查问题逐字串：`"盈利修正斜率的置信度受supplier_lookback影响（30d flagged权重41%，90d 51%），数据质量是否可靠？财报静默期是否导致修正数据失真？"`；c4 原文 `:29` 含 ae 的问题逐字串 `"M7回购大幅收缩（同比-68.74%）是季节性还是趋势性？…"`。
- 数字 token 统计（命令见总览节）：ae 材料中 `41%` 出现 2 次、`51%` 1 次——这些数字属于 c4 的问题而非 ae 自己的；c4 材料中 `68.74%` 出现 2 次。

事实：bridge_0.json 的 5 条 unresolved_questions 全量随材料进入每一份调查提示词；ae 的调查员能读到 c4 的问题及全部附随数字，反之亦然。e7 同理：M1/M3 含 4.5 个与本次调查无关的问题（见发现 5）。

### 发现 5：e7 中与调查问题直接相关的材料仅 838 字符（占全提示词 6.4%），且全部为问题复述+事件 ID 列表

证据：命令 `python3` 量 M1 中目标问题块，输出：`M1 question[0] block chars: 838 of M1 body 3954`。e7a1 全文 13,012 字符。M1 其余 4 个完整问题为"指数结构分化""宏观利率压制""信用流动性""新闻映射数据指标"（原文 :55-125），M2 前 4 个完整事件簇 minimum_fact 全部为 Fed 行政类事件（原文 :164/193/222/251：`Federal Reserve issues FOMC statement`、`Minutes of the Board's discount rate meetings…`、`…task forces…`、`…enforcement action with TS Banking Group…`）。

事实：调查问题要求回答"半导体链条、AI 权重股和盈利预期有没有同步改善"，而 13K 字符的提示词里与该问题直接相关的材料只有 838 字符的问题自身定义和 13 个事件 ID，其余为无关问题清单与 Fed 行政事件摘要。

### 发现 6：e7 源 artifact 中与问题相关的内容未进材料；截断点恰好切掉唯一科技巨头事件簇

证据（命令均为 `python3` 读 run 目录源文件）：

- `event_mechanism_report.json` 的 `headline_judgment`：`"今天最值得盯的是"AI 盈利链条能不能缓解估值压力？"…"`；`mainlines[0]`：`"mainline_id": "ai_semiconductor_earnings", "title": "AI 盈利链条能不能缓解估值压力？"`。这些段落在 M3 中未出现——M3 只取了与 M1 重复的 `cross_layer_questions`。
- `event_layer_summary.json` 源共 6 簇，输出列表显示 `[4] $19.6 Billion: The Microsoft Earnings Number That Matters Most`；材料 M2 在第 5 簇的 cluster ID 处被切断（原文 :278 `"event_cluster_id": "event_cluster:579a673`），即唯一与科技巨头财报相关的簇只进去半个 ID。
- `cross_layer_questions.json` 源共 7 问；输出 `question:data_to_event:index_strength_breadth_gap in prompt? False`、`question:data_to_event:expensive_but_resilient in prompt? False`；第 5 问 `question:e60711bd4809cf3c` 的 22 个 event_refs 只进 18 个（`e60711bd event_refs total: 22 | shown before cut: 18 in M1`）。

事实：M2/M3 的选材与截断使 e7 调查员看不到源文件中直接以 AI/半导体命名的分析段落；6 个事件簇里唯一的微软财报簇也只有半个 ID 可见。

### 发现 7：ae 材料中回购主题只有"问题自体复读"×3，无任何回购数据；截断点恰好落在源中唯一直接回答该问题的 claim 中间

证据：

- 命令 `python3` 计数，输出：`ae 调查问题串 verbatim copies: 3 | -68.74% count: 3`。三处为：原文 :22（调查问题）、:29（M1 outer unresolved_questions[1]，逐字）、:87（M1 嵌套 principal_contradiction.unresolved_questions[2]，变体"若持续，EPS增厚效应何时在估值中体现？"）。
- 全文 `回购` 仅 2 次（均在上述问题串内）；材料中没有回购金额、序列、季度或日期数据。
- 源核对（`python3` 定位源 bridge_0.json）：`grep -o -i 'buyback\|repurchase\|回购'` 计 `回购×5、buyback×2`；其中 `buyback` 两处位于 `cross_layer_claims[3]`（源 pos 1535/1555），该条完整为 `"claim": "M7资本开支加速（同比+75%）提供结构性长期盈利支撑，但短期回购收缩削弱EPS增厚"`，`supporting_facts: ['L4.get_m7_capex_cycle#m7_aggregate', 'L4.get_m7_buyback_flow#actual_buyback_spending']`，`mechanism` 含 `"同期回购收缩（同比-68.74%）→EPS增厚效应减弱→短期估值支撑下降"`。
- 截断点比对（`python3`）：`ae visible is prefix of source claim[3]? True`、`visible chars: 20 / full claim chars: 42`——ae 材料在 cross_layer_claims[3] 的第 20 个字符处断开（原文 :125 `"claim": "M7资本开支加速（同比+75%）提供结构`），可见部分只含资本开支 +75%，回购机制与 `L4.get_m7_buyback_flow#actual_buyback_spending` 数据引用全部在断点之后。
- 另一处回购实质句在源 `resonance_chains` 段（pos 8299，`EARNINGS_OFFSET_POTENTIAL`："…但力度有限且面临回购收缩阻力"），同样未进材料。

事实：调查问题问"季节性还是趋势性""何时显现"，材料中与回购相关的全部可读内容就是问题本身的三次出现（含变体）；源备忘录中唯一带回购机制与回购数据引用的 claim 被从正中间切断，切断处之后的半个句子恰好是回答该问题的那一半。

### 发现 8：c4 材料中 supplier_lookback 主题同样只有问题复读，且嵌套变体丢失"90d 51%"；源中的供应商数据附注未进材料

证据：

- 命令 `python3` 计数，输出：`c4 调查问题串 verbatim copies: 2`，`'supplier_lookback' occurrences: 2`、`'41%' occurrences: 5`、`'51%' occurrences: 1`、`'财报静默期' occurrences: 2`。嵌套变体（原文 :85）为 `"盈利修正斜率+4.2%的置信度受supplier_lookback影响（flagged权重41%），数据质量是否可靠？"`——只写 41%，未指明天数，也没有 51%。
- 源核对：源 `normalization_notes` 段（pos 21961）含 `"L4盈利修正数据中的supplier_lookback待验证（30d flagged权重41%, 90d 51%），当前置信度受限"`（命令输出原文照抄），未进 c4 材料。
- 材料中无任何 supplier 诊断数据（无 flagged 定义、无样本数、无来源构成），可证明"数据质量是否可靠"的字段为零。

事实：c4 拿到的材料里，关于其调查问题的全部信息是问题自身的两种复述加 key_uncertainties 里的一句再述（原文 :92 `"盈利修正斜率（30d +4.2%）能否持续？财报静默期后的数据质量如何？"`）；源文件里仅有的、带"待验证/置信度受限"定性的附注恰好没被选进材料。

### 发现 9：材料内 requested_checks 与所属问题文不对题（源数据即如此），并在 M1、M3 中各复读一遍

证据：e7a1 原文 :112-120（M1）与 :368-376（M3）均为：`"question_id": "question:142ca091cfc1bc18"`，`"question": "如果信用和流动性是风险来源，HYG、HY OAS 和净流动性有没有恶化？"`，其 `requested_checks` 却是 `"美光和半导体指数是否相对纳指100继续走强" / "AI 相关权重股盈利预期是否同步上修" / "涨幅是否扩散到更多半导体和硬件公司"`——与问题 `8cc9c73c046fdff2`（:33-37）的 checks 逐字相同。源级确认：`python3` 打印源 cross_layer_questions.json，输出 `question:142ca091cfc1bc18 | 如果信用和流动性是风险来源… | checks: ['美光和半导体指数是否相对纳指100继续走强', 'AI 相关权重股盈利预期是否同步上修']`。

事实：这是材料源数据自带的内部矛盾（信用/流动性问题配半导体 checks），不是投影或装包引入；它随 M1、M3 的重复结构在提示词里出现两次。

### 发现 10：两次 attempt 均因 [M#] 引用格式校验失败；重试说明拼入 attempt_2 材料尾部；字段说明与纪律行对格式的表述不一致

证据：

- 错误文件（`cat` 输出）：attempt_1 `{"attempt": 1, "error": "ValueError: claims_supported[0] missing [M#] material citation"}`；attempt_2 `{"attempt": 2, "error": "ValueError: finding missing [M#] material citation"}`。
- attempt_2 原文比 attempt_1 多 110 字符（`diff` 输出）：`上一次输出未通过 JSON/合约校验。请重新输出完整 JSON，不要省略任何字段。校验错误：ValueError: claims_supported[0] missing [M#] material citation`。
- attempt_1 响应（`head -c 1200` 输出）：其 `claims_supported[0]` 写的是 `"需要价格、利率、波动、信用和广度数据做基础确认"——M2中每个事件集群…`（裸 `M2`，无方括号），而同一响应的 `counter_evidence_refs` 用了 `"[M2] 事…"` 方括号格式。attempt_2 响应 `finding` 写 `基于提供的材料（M1、M2、M3）`（裸括号格式），claims 列表全空。
- 提示词字段说明（原文 :12-13）只说 `每条附材料编号`；`[M#]` 方括号格式只出现在末尾纪律行（:414）：`每一项都必须原样写出至少一个可用的 [M#] 编号`。

事实：合约校验器按 `[M#]` 方括号格式逐项检查；提示词在字段定义处没有给出该格式，只在全材料之后的最后一行给出。调查员两次输出都用了裸 `M2`/`（M1、M2、M3）` 写法并被判失败。另注：e7 两实例之外，ae/c4 无 error.json，一次通过（manifest 条目无 error 文件）。


## 盲区

- **响应文件未全读**：e7 两次 attempt 的 response.txt 只读了前约 1,200 字符（足够确认发现 10 的引用格式事实）；ae/c4 的 response.txt 未读（本站审查对象是材料结构，响应仅用于佐证校验失败）。若需核对"材料缺陷如何传导到输出"，这两份响应还没人逐字读过。
- **投影保真未逐字节验证**：4 个投影与原文的比对只做到"首处差异点"（ae 字符 2514、e7a1 字符 895，均为 JSON 重缩进）；其后是否每处都只有缩进差异，未全量 diff。投影字符数低于原文（94.6%/95.0%/90.8%/90.9%）我归因为重缩进+投影头部说明，属推断非穷举验证。
- **源 artifact 未全文通读**：bridge_0.json（22,185 字符）、event_mechanism_report.json（155,802 字符）、event_layer_summary.json、cross_layer_questions.json 只按关键词定位抽查（回购/buyback/supplier_lookback/问题 ID/顶级键）。发现 6-8 中"唯一""仅"类措辞的覆盖范围 = 上述关键词与结构定位能触达的范围；源文件中不用这些词表述的相关内容（若有）不在本报告结论内。
- **截断与选材机制未追代码**：3,954 字符预算、键子集选择（ae 得 cross_layer_claims、c4 得 key_uncertainties+typed_conflicts）、键序重排（unresolved_questions 提前）由什么代码/参数决定，未查 src/（本片任务只问材料结构本身，不问成因）。
- **数值一致性仅抽查**：ae/c4 做了全量数字 token 提取比对（无同指标异值）；e7 材料几乎无数字（发现 5/6），未做跨实例数字对账（如 ae/c4 材料里的数字与 L1-L5 各站是否一致，超出本片范围）。
- **其他站是否同样截断未查**：3,954 字符统一截断是否也发生在别的站，超出本片边界。
- **inv_e75efe82e7c0 之外是否还有更多调查实例**：以 manifest 与目录为准（3 实例 4 文件），未发现遗漏。

---

通读完成。4 投影 + 4 原文全读，10 条发现，每条证据可复跑。
