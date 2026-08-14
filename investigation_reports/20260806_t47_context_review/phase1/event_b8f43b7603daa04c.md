# event_card_interpreter.event_b8f43b7603daa04c 通读报告

站族：event_card_interpreter（事件材料解读员，把一条采集好的事件材料变成结构化卡片）。
语料根目录：`output/analysis/vnext/20260731_002156/context_spread/`（下文路径均相对该目录）。
manifest 事实：该站两个 attempt 均 `inspector_has_rules: false`（此前无机械检查规则）、`verification_ok: true`；模型 `deepseek-v4-flash`；attempt_1 因 parse_error 触发 attempt_2，最终 status ok（证据：`full/event_card_interpreter.event_b8f43b7603daa04c/meta.json` 及 `manifest.json` instances 两条记录）。

## 通读范围

| 文件 | 量 | 读法 |
|---|---|---|
| `projected/.../attempt_1.projection.md` | 146 行 / 8,912 字节 | 全读 |
| `projected/.../attempt_2.projection.md` | 165 行 / 9,805 字节 | 全读 |
| `full/.../attempt_1.prompt.txt` | 7,171 字符 | 全读（分段读取；Runtime Input 整体 JSON 解析核验） |
| `full/.../attempt_2.prompt.txt` | 7,763 字符 | 用 `diff` 与 attempt_1 全覆盖比对（唯一差异为尾部追加 19 行），追加部分逐行读 |
| `full/.../attempt_1.payload.json` / `attempt_2.payload.json` | 6,242 / 7,055 字节 | JSON 解析并逐键 diff |
| `full/.../meta.json` | 3,814 字节 | 全读 |
| `full/.../attempt_1.response.raw.txt` | 1,858 字符 | 为分析重试反馈做 JSON 解析定位＋错位片段抽查 |
| `manifest.json` 本站两条 instance 记录 | — | 全读 |

投影截断回查：两个投影各只有 2 处 «…省略…» 标记、无 `__omitted__`/`__table_projection__` 标记（命令：`grep -c '«…省略' projected/.../*.projection.md` → 均输出 2；`grep -n '__omitted__\|__table_projection__\|__total__'` → 无输出）。两处（raw_text_excerpt 中段 2,020 字符、cth_01 中段 100 字符）均已回 `full/` 查原文并恢复全文，见发现 3、核验一致项。

两个 attempt 的差异（总）：`diff full/.../attempt_1.prompt.txt full/.../attempt_2.prompt.txt` 输出仅 `130a131,149` 一段追加（重试反馈，592 字符，文件末尾无换行）；两个 prompt 的 Runtime Input 逐字相同（命令：python 提取 `## Runtime Input` 至 `## 输出字段规格` 之间文本，`prompt_payload == payload.json['payload']` → True）。payload.json 差异仅 `attempt` 号与 `retry_feedback` 字段（逐键 diff 输出仅这两处）。

## 材料结构总览

按投影头部"段落目录"（attempt_1 / attempt_2，字符数为原文口径）：

| 段落 | attempt_1 | attempt_2 | 内容 |
|---|---|---|---|
| `## System Message` | 18（0.3%） | 18（0.2%） | 仅段标题本身，无实质内容 |
| `# System-Level Constraints (不可违反)` | 333（4.6%） | 333（4.3%） | 6 条通用纪律 |
| `## User Message` | 605（8.4%） | 605（7.8%） | 职责说明＋5 条铁律 |
| `## Runtime Input` | 4,938（68.9%） | 4,938（63.6%） | 全部输入数据（JSON） |
| `## 输出字段规格` | 906（12.6%） | 906（11.7%） | EventInterpretationCard 契约 |
| `## Response Rules` | 371（5.2%） | 963（12.4%） | 输出规则（attempt_2 追加 592 字符重试反馈） |
| 合计 | 7,171 | 7,763 | |

Runtime Input（实测 4,919 字符，不含段标题）内部构成：
- `event_material`：含 `raw_text_excerpt` 实测 2,200 字符（占整个提示词约 30.7%），是全文最大单一数据块；事件为 Motley Fool 报道 "$19.6 Billion: The Microsoft Earnings Number That Matters Most"（tier=reliable_mainstream_report，effective_date=2026-07-30）。
- `allowed_financial_links`：9 个金融传导渠道。
- `competing_hypotheses`：3 条（hyp_base leading＋cth_01/cth_02 candidate）。
- `output_contract`：实测 907 字符（提示词行 71–103），输出契约的 JSON 示例形态。
- `boundary`：实测 126 字符（行 104–108），3 个布尔边界标记。

解读：这是一个"小任务书＋一份大材料"的站——规则文本（System Constraints＋User Message＋Response Rules）合计约 1,309 字符（18%），数据与契约占绝对大头；而数据大头里近一半是原始报道摘录本身。

## 发现清单

### 发现 1：输出契约以两种形态重复出现（合计约 1,813 字符，约占全提示词 25%），且两处对"弱来源措辞"的指引存在张力

事实：同一份 EventInterpretationCard 契约出现两次——(a) Runtime Input 内的 `output_contract` JSON 示例（`full/.../attempt_1.prompt.txt:71-103`，实测 907 字符）；(b) 文末 `## 输出字段规格（由 EventInterpretationCard 契约自动生成，形状以此为准）` 段落（投影行 127–139，目录记 906 字符）。Response Rules 自己承认双形态并存：`字段的**形状**（对象 / 数组 / 标量、是否可为 null）以上面「输出字段规格」为准；正文里的示例只解释语义，形状冲突时以规格为准。`（`attempt_1.prompt.txt:129`，投影行 145）。

张力点：`output_contract` 内 `"interpretation": "模型解读；弱来源以据报道或该媒体称开头"`（`attempt_1.prompt.txt:74`）给了一个固定开头模板；而 User Message 铁律写 `**措辞完全由你决定，没有固定说法要套**……所以这里不设措辞检查`（`attempt_1.prompt.txt:20`，投影行 36）。一处给模板、一处声明不设模板。

证据命令：
```
$ python3 -c "…定位 output_contract 子串…"   # 见会话
output_contract block chars in prompt: 907
$ sed -n '71,103p' full/.../attempt_1.prompt.txt   # output_contract JSON 全块
```

### 发现 2：System-Level Constraints 第 4、5 条引用的键在本站输入与输出契约中均不存在

事实：约束 4 `所有 evidence_refs 必须来自本次输入的 raw_data，不得凭记忆添加。`（`attempt_1.prompt.txt:9`）——本站输出契约没有 `evidence_refs` 字段（契约 12 字段为 event_id/fact_summary/interpretation/entities/event_type/mechanism_hypothesis/supports_hypotheses/refutes_hypotheses/limitations/needs_data_confirmation/upgrade_candidate/passport），Runtime Input 里也没有 `raw_data` 键（实际数据键为 `event_material`）。约束 5 引用 `NO_DATA_AVAILABLE`（`attempt_1.prompt.txt:10`），该标记在输入中未出现（本例 `raw_text_available: true`）。

证据命令：
```
$ grep -n 'NO_DATA_AVAILABLE\|raw_data\|evidence_refs' full/.../attempt_1.prompt.txt
9:4. 所有 evidence_refs 必须来自本次输入的 raw_data，不得凭记忆添加。
10:5. 若输入出现 `NO_DATA_AVAILABLE`，只能把它当作数据边界或置信度限制；…
```
即这三个词只出现在约束文本自身，材料与契约中均无对应物。

### 发现 3：raw_text_excerpt 是恰好 2,200 字符的硬截断片段，结尾断在单词中间，材料中无任何字段声明截断

事实：`"raw_text_available": true`（`attempt_1.prompt.txt:36`），同行为 `raw_text_excerpt`（行 37）。实测 excerpt 长度恰好 2,200 字符，结尾为 `…Microsoft 365 Copilot reached over 30 million paid seats, reflecting the conf`——在单词 "conf…" 中间断开。材料中没有"已截断/全文长度/截断位置"之类的标记字段；User Message 铁律只区分"有正文 / 只有标题"两档（`attempt_1.prompt.txt:20`，投影行 36），没有覆盖"正文被截断"这档。

证据命令：
```
$ python3 -c "
import json; t=open('full/.../attempt_1.prompt.txt').read()
p=json.loads(t[t.index('## Runtime Input')+16:t.index('## 输出字段规格')])
ex=p['event_material']['raw_text_excerpt']; print(len(ex), repr(ex[-60:]))"
2200 '…Microsoft 365 Copilot reached over 30 million paid seats, reflecting the conf'
```
（投影在此处标记 «…省略 2020 字符…»，投影行 53；中段 2,020 字符已回 full 查原文。）

### 发现 4：正文摘录混入网页脚手架文本与抓取时刻的行情角标

事实：excerpt 开头不是报道正文，而是站点导航与 UI 碎片：`…| The Motley Fool Accessibility Menu ▲ S&P 500 + ---% | ▲ Stock Advisor + ---% Join The Motley Fool Search for a company Accessibility ... Help `；中部夹有 `Image source: The Motley Fool.`；并带有抓取时点的行情角标 `Microsoft ( MSFT +15.09% )`（均见 `attempt_1.prompt.txt:37`）。铁律要求 `fact_summary` "只许出现材料里逐字有的东西"（`attempt_1.prompt.txt:17`，投影行 33）——材料里逐字有的东西包含上述脚手架。

证据命令：`sed -n '37p' full/.../attempt_1.prompt.txt | head -c 400`
输出（照抄）：`"raw_text_excerpt": "$19.6 Billion: The Microsoft Earnings Number That Matters Most | The Motley Fool Accessibility Menu ▲ S&P 500 + ---% | ▲ Stock Advisor + ---% Join The Motley Fool Search for a company Accessibility ... Help Microsoft ( MSFT +15.09% ) stock is up 13% today …"`

### 发现 5：材料内部数值矛盾——MSFT 单日涨幅在同一段摘录里有两个不同的值

事实：同一 `raw_text_excerpt` 内，行情角标为 `Microsoft ( MSFT +15.09% )`，紧随其后的正文写 `stock is up 13% today`（同一行内相邻出现，`attempt_1.prompt.txt:37`）。两个单日涨幅数字（+15.09% 与 +13%）在材料里并存，且都属于"材料里逐字有的东西"（fact_summary 铁律的照抄范围）。其余财务数字（营收 $90B vs $76.4B、净利 +31%、EPS $4.81 vs $3.86、全年 EPS $17.95 vs $13.64）在 excerpt 内部口径一致。

证据命令：`grep -o 'MSFT +15.09% ) stock is up 13% today' full/.../attempt_1.prompt.txt`
输出：`MSFT +15.09% ) stock is up 13% today`

### 发现 6：event_material.entities 是空数组，而材料中明确出现多个实体

事实：输入侧 `"entities": []`（`attempt_1.prompt.txt:35`）；同一材料标题与 excerpt 中明确出现 Microsoft/MSFT、Tesla、Alphabet、Satya Nadella、Azure、Microsoft 365 Copilot 等实体。输出契约又要求 `entities` 填"材料中的实体"（`attempt_1.prompt.txt:75-77`，投影行 93-95）。即：输入侧该字段留空，抽取动作完全交给模型。

证据命令：
```
$ python3 -c "…; print(p['event_material']['entities'])"
[]
$ grep -o 'Tesla and Alphabet\|Satya Nadella' full/.../attempt_1.prompt.txt
Tesla and Alphabet
Satya Nadella
```

### 发现 7：trigger_reasons 与 boundary 两个块占约 200 字符，但全部指令文本均未提及或要求消费它们

事实：`"trigger_reasons": ["mainline", "inquiry_reference"]`（`attempt_1.prompt.txt:38-41`）；`"boundary": {"event_ref_only": true, "must_not_become_l1_l5_evidence_ref": true, "must_not_feed_back": true}`（行 104-108，实测 126 字符）。User Message 铁律、输出字段规格、Response Rules 全文中没有任何一处引用这些键、解释其语义或要求模型对其作出反应；输出契约 12 个字段里也没有与它们对应的字段。`boundary` 键名语义指向"隔离纪律"，但这类纪律只以裸布尔值躺在数据 JSON 里。

证据命令：
```
$ grep -n 'trigger_reasons\|boundary\|event_ref_only' full/.../attempt_1.prompt.txt
38:    "trigger_reasons": [
104:  "boundary": {
105:    "event_ref_only": true,
```
（全部命中均在 Runtime Input JSON 块内部，指令文本零命中。）

### 发现 8：attempt_2 的重试反馈把模型上一轮答案的尾部原样塞回提示词，且反馈给出的错误定位与实际 JSON 语法错误位置不符

事实（差异面）：attempt_2 相对 attempt_1 的唯一变化是 Response Rules 段后追加 592 字符（`diff` 输出 `130a131,149`）：先声明"上一次返回未通过结构校验"，再原样引用上一轮响应的末尾片段——其中包含该模型自己上一轮写出的 `needs_data_confirmation` 三条内容（"MSFT官方8-K或SEC 10-K文件中的完整财务数据"等）、`"upgrade_candidate": true` 及 passport 值（`attempt_2.prompt.txt:131-149`）。即本轮输入中混入了模型上一轮的部分输出。

事实（定位面）：反馈文本指示"响应末尾片段（用于定位 JSON 语法错误，请检查最后未闭合的数组、对象或字符串）"（`attempt_2.prompt.txt:134`）。但对 attempt_1 原始响应实测，JSON 解析错误位于响应前段第 3 行 fact_summary 内——CEO 引言使用了未转义的 ASCII 双引号：

```
$ python3 -c "import json; json.loads(open('full/.../attempt_1.response.raw.txt').read())"
JSONDecodeError: Expecting ',' delimiter: line 3 column 289 (char 330)
$ python3 -c "r=open('full/.../attempt_1.response.raw.txt').read(); print(repr(r[270:400]))"
'期Windows OEM与设备营收同比-7%，Xbox内容与服务营收同比-10%。CEO Satya Nadella称"Azure营收首次突破1000亿美元，Microsoft 365 Copilot付费席位超过3000万"。文章指出微软在AI基础设施巨额资本'
```

而反馈所引用的响应末尾片段本身是完整闭合的 JSON 尾部（passport 段，括号成对）。实际错误（前段未转义引号）与反馈指示的排查方向（末尾未闭合结构）不一致。

## 核验一致项（查过、未见异常）

- `published_at: "Thu, 30 Jul 2026 16:00:42 +0000"` 的星期与日期自洽：`date -j -f '%Y-%m-%d' '2026-07-30' '+%A'` → `Thursday`。
- User Message 说"从给定的九个金融传导渠道里选择"，`allowed_financial_links` 实测 9 项，且与输出规格中 EventMechanismHypothesis 的 9 值枚举逐项一致（投影行 59-69 vs 行 133）。
- 投影截断第二处（cth_01 `hypothesis_text` 中段 «…省略 100 字符…»，投影行 78）已回原文恢复：全文 280 字符，被省略内容为"在MA200上方并接近Donchian下轨，显示抛压可能已近尾声。若实际利率不再上行，盈利兑现将触发估值修复，市场可能已过度悲观。净流动性边际改善和期限利差转正也提供宽松背景。主线对信用尾部风险的重"一段的中部。
- 三条 competing_hypotheses 之间的数字不构成同名指标冲突：cth_01 的"M7资本开支…同比+75%"与 cth_02 的"M7回购…同比-68.74%"是不同指标（资本开支 vs 回购）；hyp_base 的"实际利率 99.4%分位"与 cth_01 的"HY OAS 31%分位"也是不同指标。
- 两个 attempt 的 Runtime Input 逐字相同；prompt 内嵌 JSON 与 `attempt_1.payload.json` 的 `payload` 键逐字相同（python 比对 → True）。

## 盲区

- 投影与原文的散文部分未做逐字 diff（manifest 两条记录均 `verification_ok: true`，且我抽查的段落一致）；理论上存在投影保真但散文有细微出入而未被我发现的可能。
- `attempt_2.response.raw.txt`（3,260 字节）、`attempt_2.parsed.normalized.json`、`output.validated.json` 未逐字读——它们是输出侧产物，本任务焦点是"输入材料结构"；读它们的唯一目的是分析重试反馈，该目的已通过 attempt_1 响应达成。
- 原报道全文不可得：材料本身就是 2,200 字符窗口（见发现 3）， excerpt 之外的原报道内容、以及"2,200 字符窗口占全文多大比例"无从判断。
- `raw_text_excerpt` 在 payload 上游是如何生成/截断的（采集管线行为）不在本语料范围内，未查。
- 其余 10 个 event_card_interpreter 兄弟站未读（任务边界外），发现 2、4、7 是否为该站族普遍模式无法从本片语料断言。
