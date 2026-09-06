# event_card_interpreter · event_810ecddf46cd4262 上下文体检报告

## 结论

本站上下文编排总体健康：任务规则前置、输出规格贴近响应端、无越权、无指令硬冲突、事件材料同日新鲜，且输出 fact_summary 的全部数字经逐项核验可溯源到材料原文（0 编造）。最重的两个病灶都在材料侧：① 8,000 字符正文摘录中约 33%（约 2,600 字符）是网页刮取噪声（行情挂件×3、站点菜单、"Read Next" 推荐列表、作者简介），把预处理活推给了模型注意力；② 竞争假说文本里的内部黑话（「吸收端」「吸收引擎」「转化信号」「多源趋弱共振」）无解释，且已传染进输出叙事。用户特别问的「法典」：**本 prompt 出现 0 次**。

## 体检明细

### A. 顺序

- **A1 段落编排** — 判定：合理。结构为 System 纪律(L1-11) → 任务+铁律(L13-26) → Runtime 数据(L29-80) → 输出规格(L82-94) → Response Rules(L96-101)。指令在头尾两段，注意力洼地（中段）落的是数据而非指令；输出规格仅 954 字符、紧邻 Response Rules，离"落笔"最近。未发现重要指令被数据掩埋。
- **A2 数据时序** — 判定：合理。单事件站，`published_at` 2026-09-02 15:31 UTC、`event_date`/`effective_date` 2026-09-02（L36-38），与 run 日期（t70_glm_check_**20260902**）同日；正文叙述口径（"2026 年内跌 14%/3%/21%"）与当日快照口径一致，无过期数据冒充当前。
- **A3 few-shot 打断** — 判定：不适用。prompt 内无 few-shot 示例。
- **A4 重试差异** — 不适用（单 attempt）。

### B. 体量与冗余

- **B1 体量账本** — 判定：结构合理，摘录内部有浪费（P1）。总计 13,811 字符，占比：System Message 18（0.1%）、System-Level Constraints 336（2.4%）、User Message 1,465（10.6%）、Runtime Input 10,667（77.2%）、输出规格 954（6.9%）、Response Rules 371（2.7%）。模板合计 3,144 字符（22.8%），属健康水平。最大三段：① `raw_text_excerpt` 8,000 字符（全文 57.9%）——必要但其中约 33% 是噪声（见 C4/B3）；② User Message 1,465 字符——10 条铁律密度高但条条有下游消费，删任何一条判断都会变差，必要；③ competing_hypotheses 约 1,400 字符——输出端 supports/refutes 实际引用了其中具体论断（如"吸收引擎仍在运转"），作为引用锚点必要。三段均无整段可删项。
- **B2 站内重复** — 判定：基本干净。唯一重复：事件标题先出现在 `title` 字段，又作为 `raw_text_excerpt` 开头 106 字符原样重复（excerpt offset 0-106）。未发现同一数值多处复读（三只个股行情只在挂件里出现一次，假说内数字各出现一次）。
- **B3 粒度错配** — 判定：P1。excerpt 内 3 个 "Expand NASDAQ : … Moneyball Superscore … Key Data Points Market Cap … 52wk Range …" 行情挂件（offset 1539/2548/4268 起，各约 431 字符）、站点菜单头（offset 0-256）、"Read Next" 六条推荐文章列表（offset 6861-7517）与作者简介（offset 7517-8000，结尾还截断在半句 "on stag"）全是刮取器该清洗掉的东西，合计约 2,600 字符。模型真正要用的正文约 5,300 字符，却被要求先在一堆 "Gross Margin 49.53%" 式碎片里自我导航。

### C. 质量

- **C1 指令冲突** — 判定：无 P0/P1 级冲突，两处轻度表述张力（P2）：① User Message L24 说 `event_id`/`passport` "由代码按采集底账装配回填，**不用你填**"，而输出规格 L83/L94 标 `event_id`（必填）、`passport`（必填）——必填与"不用你填"口径不一，靠 L24 末句"填了也会被底账值覆盖"兜住，未造成输出错误；② 叙事纪律 L25 "字段名……不进叙事字段" 与机制句式 L18 "该事件可能通过××渠道影响××" 有轻微诱导：模型最终在 mechanism 散文里裸写了枚举值 `earnings_path`（见 E1）。
- **C2 死指令** — 判定：一处（P2）。System 纪律第 4 条（L9）要求"所有 `evidence_refs` 必须来自本次输入里实际提供的材料条目"——但本站输出规格（L82-94）**没有 evidence_refs 字段**，属模板泛化残留的死指令。抽查其余字段均活：`fact_summary`/`interpretation`/`mechanism_hypothesis`/`limitations`/`needs_data_confirmation`/`upgrade_candidate` 在 output.validated.json 全部有实值且形状合规。
- **C3 黑话词典** — 判定：部分传染（P1/P2）。「法典」0 次。有解释的：tier 词表（L21 逐档给出取值与分寸）、九个传导渠道（L47-56 枚举）、「竞争假说块」（L22 说明了仅作引用背景）。**无解释的传染源**：①「底账」×5（L24×2、L25、L86、L87），"采集底账"是系统自造词，仅靠上下文可猜；②「主线」「反方」×6（hyp_base/hyp_counter 文本内，L61/66/71），阵营标签无解释；③「吸收端/吸收能力/吸收引擎」×4（L61/66），纯内部 shorthand；④「转化信号」×1（L66）、「多源趋弱共振」×1（L71）、「链条五环/四环」×2（L66/71）；⑤ 来源名 "Yahoo Finance **M7** Headlines"（L34）的 M7 未解释。②③④全部住在竞争假说文本里，prompt 虽声明其"只作引用背景"，但没禁止词汇传染（见 E1）。
- **C4 数据新鲜度**（本站重点）— 判定：**材料时效健康，但材料纯度差（P1）**。时效：事件发布、event_date、effective_date、run 日全部为 2026-09-02 同日，无过期伪装。纯度：`raw_text_available: true` 名副其实（8,000 字符摘录含完整文章主体），但混入约 2,600 字符站点噪声（明细见 B3）。另一处口径隐患：文章叙述数字（如 NFLX "25 times trailing"）与挂件快照（当日价 $82.50、52wk 区间）来源时点不同，未在输入侧标注——模型输出端自行发现并处理了（limitations 第 5 条），属侥幸自救而非设计保障。

### D. 隔离

- **D1 越权扫描** — 判定：未发现越权。全 prompt 无 `final_adjudication`、`thesis_draft`、`golden_pit`、`user_decision_profile`、其他层 layer card 路径命中。competing_hypotheses 是 thesis/counter 层派生文本，但本站职责就是给假说提供 supports/refutes，属设计内引用背景，且 `boundary`（L75-79）明确 `event_ref_only` / `must_not_become_l1_l5_evidence_ref` / `must_not_feed_back`，输出 limitations 第 6 条也如实回写了该边界。

### E. 输出闭环

- **E1 叙事字段体检** —
  - **黑话传染**：成立（P1/P2）。interpretation 直接沿用假说内部词「吸收端」「吸收引擎」「轮动消化」「结构性解释」且未给读者半句解释（output.validated.json `interpretation`）；mechanism 散文裸写枚举 `earnings_path`，正撞上 L25 "字段名……不进叙事字段" 的自家纪律。轻度项：limitations 第 6 条复读 boundary 配置属 meta 信息入叙事字段。
  - **复读机检测**：干净。对 fact_summary / interpretation / mechanism 散文做 15 字符滑窗比对，唯一命中是专名 " Rick Munarriz "（作者名），无背题句。
  - **簿记语言密度**：总体好。fact_summary 把 18%/11.7%、25×/21×、+45%/翻倍/+145% 等全部嵌在因果句里；`fact_summary` 数字逐项回查原文全部命中（"18%"@excerpt:2120、"11.7%"@2131、"25 times"@2468、"$100B"@2712、"$1.4T"@4425、"45% through the next four years"@6299、"cut in half"@5499），**零编造**。
  - **长度纪律**：输出规格对叙事字段无长度要求，无法违反；fact_summary 约 700 字符单段偏长但信息密度合格。
- **E2 因果对** — 两对成立：① **假说黑话无解释 → 输出传染**：材料证据 L61/66/71（「吸收端」「转化信号」「多源趋弱共振」首现即裸用）→ 输出 `interpretation` 未加解释直接沿用「吸收端」「吸收引擎」。② **摘录混入挂件快照 → 输出自费拆弹**：材料证据 excerpt offset 1539/2548/4268（挂件行情与文章叙述口径混排）→ 输出 `limitations` 第 5 条专门写"文中嵌有发文时点的行情快照……口径与时点可能不完全一致"。说明：②是模型正确消化了材料缺陷，未产生错误输出，但代价是注意力；若模型没拆弹， fact_summary 有把挂件价当文章论据的风险。

## 病灶清单（按严重度排序）

| 严重度 | 病灶 | 证据位置 |
|---|---|---|
| P1 | 正文摘录约 33%（约 2,600/8,000 字符）是网页刮取噪声：站点菜单、3 个行情挂件、Read Next 列表、作者简介（结尾半句截断） | prompt.txt L42；excerpt offset 0-256 / 1539+431 / 2548+431 / 4268+431 / 6861-8000 |
| P1 | 竞争假说文本内部黑话（吸收端×4、主线/反方×6、转化信号、多源趋弱共振、链条五环）首现无解释，并传染进输出叙事 | prompt.txt L61/66/71 → output.validated.json `interpretation` |
| P2 | mechanism 叙事散文裸写枚举值 `earnings_path`，违反 L25 "字段名不进叙事字段"纪律 | output.validated.json `mechanism_hypothesis.hypothesis` |
| P2 | System 纪律第 4 条要求 evidence_refs，但本站输出契约无此字段（模板泛化死指令） | prompt.txt L9 vs L82-94 |
| P2 | 「底账」×5、「M7」×1 无解释 | prompt.txt L24/25/86/87、L34 |
| P2 | `event_id`/`passport` 规格标"必填"与 User Message"不用你填"表述不一致 | prompt.txt L24 vs L83/94 |
| P2 | limitations 第 6 条复读 boundary 配置（meta 信息入叙事字段，弱） | output.validated.json `limitations[5]` |

## 修复建议

1. **（对应 P1-噪声）改采集/装配层**：对 Motley Fool 类转载页在落 `raw_text_excerpt` 前做正文抽取——剥掉 "Expand NASDAQ : … Key Data Points …" 挂件、站点菜单、"Read Next"、About the Author；挂件里的市值/52wk 区间若想保留，结构化为独立 `snapshot` 字段并标注口径时点，而不是混进散文。本例可省约 2,600 字符（19% 的整个 prompt）。
2. **（对应 P1-黑话）改假说下发模板**：竞争假说文本入 event_card 输入前做词汇归一——「吸收端/吸收引擎」替换或首次出现附半句解释（如"吸收端＝靠盈利增长消化高估值的变量"）；或在 User Message 铁律里加一句"引用假说原话时同步给出通俗转述"。下游综合裁决是内部读者，但叙事字段明示还有"报告读者"。
3. **（对应 P2-枚举入散文）改机制句式模板**：把 L18 句式改成"该事件可能通过〔渠道的通语说法，如『盈利路径』〕影响××"，枚举值只写在结构字段 `financial_link` 里。
4. **（对应 P2-死指令）改 System 模板**：纪律第 4 条改为按站条件渲染，本站无 evidence_refs 字段就不下发该条（或改写为"supports/refutes 只能引用本次输入提供的 hypothesis_id"）。
5. **（对应 P2-必填表述）改一处措辞**：输出规格对 `event_id`/`passport` 标注"由代码装配，模型可不填"，与 L24 对齐。
