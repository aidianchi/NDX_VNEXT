# event_card_interpreter · event_1ba51e4463f20b2c 上下文体检报告

> 站点：event_card_interpreter（单事件实例，10 个同模板事件卡之一）
> 材料：prompt 12,262 字符；投影 5,153 字符（42.0%）；输出 `output.validated.json`（存在，已读）
> 证据行号均指 `prompt_audit/event_card_interpreter.event_1ba51e4463f20b2c/attempt_1.prompt.txt`

## 结论

本站整体健康：材料新鲜、事件原文质量好、输出忠实且说人话，未发现 P0/P1 级病灶。最值得改的两点：①批量成本——10 张事件卡里模板+竞争假说约 5,211 字符逐字重复（md5 已验证 10 份完全一致），其中竞争假说全文下发但模型只用它挑 hypothesis_id，占本实例 13.8%；②两处轻微指令张力（「不用你填」vs「顶层字段必须匹配」）与两处黑话微传染（「吸收引擎」、枚举值 `earnings_path` 进叙事）。特别核查：**「法典」一词在本站 prompt 与输出中均未出现**。

## 体检明细

### A. 顺序

- **A1 段落编排** — 判定：合理 — 证据：结构为「纪律(L1-11) → 任务合约(L13-26) → 数据(L29-80) → 输出规格(L82-94) → Response Rules(L96-101)」。任务定义在前、数据居中、输出规格紧贴生成点，无重要指令埋进数据洼地的问题。
- **A2 数据时序** — 判定：合理（无时序序列可排）— 证据：唯一时间数据是 passport 三元组 `published_at/event_date/effective_date = 2026-09-02`（L36-38），单一时点无排列方向问题；无过期段落冒充当前状态。
- **A3 few-shot 打断** — 判定：合理（无示例）— 证据：全 prompt 无 `Example:` 类片段，主干未被切碎。Response Rules L100 特意声明「形状冲突时以规格为准」，防示例干扰，设计自觉。
- **A4 重试差异** — 不适用：本站仅 attempt_1。

### B. 体量与冗余

- **B1 体量账本** — 判定：P2（批量成本结构性存在，单实例可接受）。实测字符账（python 逐段切片）：

| 段落 | 字符 | 占比 | 归属 |
|---|---|---|---|
| System Message（纪律） | 354 | 2.9% | 模板 |
| User Message（任务合约） | 1,465 | 11.9% | 模板 |
| Runtime Input·event_material | 7,030 | 57.3% | **事件独有** |
| Runtime Input·allowed_financial_links | 241 | 2.0% | 模板 |
| Runtime Input·competing_hypotheses | 1,698 | 13.8% | run 级共享 |
| Runtime Input·boundary | 128 | 1.0% | 模板 |
| 输出字段规格 | 954 | 7.8% | 模板 |
| Response Rules | 371 | 3.0% | 模板 |

  模板部分合计 3,513 字符（28.6%），事件独有 7,030（57.3%）。用 md5 对 10 个实例比对：System+User 段、competing_hypotheses 段、输出规格+RR 段三段哈希在 10 份间**全部相同**——即每张卡有 5,211 字符（42.5%）逐字重复，10 张卡合计约 52,110 字符重复文本。最大三段中，event_material（7,030）必要（无正文则卡无从写起）；competing_hypotheses（1,698）**必要性存疑**：模型对它的全部消费只是输出 2 个 hypothesis_id（见输出 `supports_hypotheses`/`refutes_hypotheses`），两条反方假说各约 500-700 字符的五环/四环链条细节对本任务超出所需，一行主旨+id 即可支撑同样的判断。
- **B2 站内重复** — 判定：轻微 — 证据：九渠道枚举在 prompt 内出现 2 遍（L47-56 `allowed_financial_links` 与 L88 输出规格 `financial_link` 枚举），约 241 字符重复；其余无同数字/同事实复读。
- **B3 粒度错配** — 判定：不适用 — 证据：本站输入是单篇散文摘录（6,507 字符），无同构时序序列需要预处理。

### C. 质量

- **C1 指令冲突** — 判定：P2（一对轻度张力）— 证据：L24 称 `entities`、`event_type`、`event_id`、`passport`「由代码按采集底账装配回填，**不用你填**——填了也会被底账值覆盖」；但 L99 Response Rules 要求「JSON 顶层字段必须匹配: event_id, ..., entities, event_type, ..., passport」，且输出规格 L83/94 将 `event_id`、`passport` 标为**必填**。模型被同时要求「别填」和「必须交」，实际选择照填（response.raw.txt 含全部字段）。不致错，但属自相矛盾的措辞。
- **C2 死指令** — 判定：一条存疑 — 证据：抽查 `fact_summary`/`mechanism_hypothesis`/`limitations`/`needs_data_confirmation`/`upgrade_candidate`：输出里全部存在且通过校验（`output.validated.json`），活。**存疑**：L24 的「填了也会被底账值覆盖」——底账 `entities: []`（L40），而输出 `entities` 有 6 个代码（BRKA/BRKB/GOOGL/CVX/OXY/AAPL）且 response.raw 与 validated 一致，说明至少在落盘点覆盖并未发生。该承诺要么不实、要么覆盖发生在落盘之后，需要看装配代码才能定。
- **C3 黑话词典** — 判定：P2（少量未解释自造词，均在受控位置）。**「法典」未出现**（prompt 0 次、输出 0 次）。清点：
  - `底账` ×5（L24、L83、L86-87、L94）：无正式解释，但语境（「采集底账装配回填」「对应新闻事件底账的 event_id」）足以让新模型推出「采集时的注册记录」，可懂。
  - `卡级标签` ×1（L26）：语境可懂（「代码装配的卡级标签承载来源分寸」）。
  - 竞争假说正文内的自造词：`折现率复合体`、`解保险`、`多源趋弱共振`、`吸收引擎`（L61/66/71）——均无解释。缓解因素：L22 明确「竞争假说块只作 supports/refutes 的引用背景，其中的表述与数字不得当事实引用」，且 L66 内含大量数字细节（57bp、3.63%、+84% 等），若被当事实引用会违反纪律第 1 条——prompt 已提前封堵。
- **C4 数据新鲜度** — 判定：合理（本站质量主菜，成绩好）— 证据：材料标题、来源、日期三齐全（L33-38：title + `Yahoo Finance M7 Headlines` + published_at 2026-09-02T15:26Z）；`raw_text_available: true`（L41），正文摘录 6,507 字符为完整文章主体（我已逐关键词核实：模型 fact_summary 引用的 1.6 million 用户、8% 数据中心占比、32,400 兆瓦、5.4 million 客户、$33.5B/29B 资本开支、$365B 现金全部在摘录中，无编造）。事件日期距 run 时间（2026-09-03 落盘）不足 12 小时，无过期数据。唯一杂质：摘录开头约 190 字符是网页导航噪音（`Accessibility Menu ▲ S&P 500 + ---% | ▲ Stock Advisor...`，L42），未清洗。

### D. 隔离

- **D1 越权扫描** — 判定：未发现越权 — 证据：关键词 `final_adjudication`/`thesis_draft`/`browser_sidecar`/`user_decision_profile`/`golden_pit` 在 prompt 中均为 0 次命中。`competing_hypotheses`（L58-74）是 run 级假说登记而非其他层 card 结论，且属本站设计内输入（供 supports/refutes 引用）。`boundary`（L75-79）三键 `event_ref_only/must_not_become_l1_l5_evidence_ref/must_not_feed_back` 显式声明事件层不回流，隔离设计在位。

### E. 输出闭环

- **E1 叙事字段体检**（叙事字段：fact_summary / interpretation / mechanism_hypothesis.hypothesis / limitations / needs_data_confirmation）：
  - **黑话传染**：P2 — interpretation 中「主假说中『集中于龙头且仍在进行的盈利上修』」（15 字符与 L61 假说正文逐字相同）及「巨头资本开支可作为无碍运转的吸收引擎」（`吸收引擎` 为 L66 自造词，prompt 1 次→输出 1 次）——引语式使用、加了引号，且下游读者之一是同系统的综合裁决站；但对外部报告读者无解释。轻度传染。
  - **复读机检测**：未发现背题 — 抽 5 句核验，仅上述 15 字符假说引语（属 prompt 明示允许的「引用背景」）与 7 字符机制句式模板（「该事件可能通过」）命中；fact_summary 六个数字均出自 excerpt 而非 prompt 其他段落，无 ≥15 字符的无关复读。
  - **簿记语言密度**：P2 — mechanism_hypothesis.hypothesis 叙事里裸写枚举值 `earnings_path`（「该事件可能通过earnings_path渠道影响纳指100」），违反 prompt 自己的规矩（L25「字段名……不进叙事字段」）。枚举本已住在同对象的 `financial_link` 结构字段里，叙事中重复一次属冗余簿记。其余叙事字段干净，数字均嵌在因果链里（如「8%来自数据中心客户→需求侧旁证」），非裸列。
  - **长度纪律**：输出规格未对叙事字段设长度要求；实际输出 fact_summary 约 380 字、interpretation 约 300 字，克制合理。
- **E2 因果对**：
  1. **连成**：竞争假说全文下发（材料证据 L58-74，1,698 字符含自造词）→ interpretation 直接搬用假说内部术语「吸收引擎」「盈利上修」进叙事（输出证据 `interpretation` 字段）——材料里的黑话是输出的传染源。
  2. **连成（轻度）**：「不用你填」（L24）vs「顶层字段必须匹配」（L99）的张力 → 模型照单全填（response.raw 含 entities/event_type/passport 全字段），指令冲突未造成错误但造成措辞与行为脱节。
  3. 其余（数据质量、新鲜度、顺序）→ 输出质量良好，无缺陷可归因，未发现其他因果。

## 病灶清单（按严重度排序）

| 严重度 | 病灶 | 证据位置 |
|---|---|---|
| P2 | 10 张事件卡共享文本 5,211 字符/张（42.5%）逐字重复，其中 competing_hypotheses 全文（1,698 字符）超出「只挑 hypothesis_id」所需 | prompt L58-74；10 实例 md5 比对 |
| P2 | 指令张力：「不用你填——填了也会被覆盖」vs「顶层字段必须匹配」+ event_id/passport 必填 | prompt L24 vs L83/94/99 |
| P2 | 假说自造词（吸收引擎/折现率复合体/解保险/多源趋弱共振）无解释，其中「吸收引擎」传染进输出叙事 | prompt L61/66/71；output `interpretation` |
| P2 | 枚举值 `earnings_path` 裸进叙事字段，违反 prompt 自订的「簿记语言不进叙事」规矩 | prompt L25；output `mechanism_hypothesis.hypothesis` |
| P2 | 「填了也会被底账值覆盖」承诺与落盘输出不符（底账 entities=[] 但输出 6 代码），存疑 | prompt L24、L40；output.validated.json `entities` |
| P2 | 摘录开头约 190 字符网页导航噪音未清洗 | prompt L42 |

## 修复建议

1. **砍竞争假说下集体量**：给每条假说增加一行 `gist` 字段（30-60 字主旨），事件卡 prompt 只发 `hypothesis_id + gist + status`，五环/四环全文留给真正消费它的裁决站。单卡省约 1,200 字符，10 卡省约 1.2 万字符，且不改变 supports/refutes 判断所需的信息量。
2. **统一「谁填字段」的口径**：把 L24 改为「这些字段你可以原样回传输入里的值，形状上必须出现在顶层 JSON」（与 L99 对齐）；或 Response Rules 豁免这四个字段，二选一。同时核实装配代码是否真的执行覆盖，若否，删掉「填了也会被覆盖」这句不实承诺。
3. **假说文本内的自造词在首次出现处加半句括注**，或在 prompt 铁律里加一句「假说正文的系统自造词不得原样进入叙事字段，改用通语转述」，阻断「吸收引擎」式传染。
4. **采集端清洗摘录**：剥掉网页导航噪音（`Accessibility Menu ▲ ...`），每卡省约 190 字符噪音并降低 fact_summary 混入页面元素的风险。
5. 叙事字段枚举处理：在输出规格 `mechanism_hypothesis` 条目加一句「hypothesis 文本用渠道中文名（如『盈利路径』），不要重复枚举值」。
