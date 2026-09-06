# event_card_interpreter.event_c5ee0104 上下文体检报告

> 站：event_card_interpreter 单事件实例。任务书写的实例 ID 结尾为 `...5fc9`，run 内实际目录为 `event_c5ee0104915b5fcf`（结尾 `cf`），确认为同一站，按实际目录执行。
> 材料：投影 `context_spread/projected/event_card_interpreter.event_c5ee0104915b5fcf/attempt_1.projection.md`；原文 `prompt_audit/.../attempt_1.prompt.txt`（9,516 字符）；输出 `output.validated.json`。
> 事件本体：Berkshire 持仓 Alphabet 378 亿美元（Yahoo Finance 转载 GuruFocus，2026-09-02，tier=reliable_mainstream_report）。

## 结论

本站上下文编排合理、输出质量高，唯一实质病灶是**事件原文材料被网页外壳污染**：`raw_text_excerpt` 3,742 字符中约 62%（约 2,317 字符）是 Yahoo 页面导航、行情组件、自选股榜与广告尾巴，占整个 prompt 的约 24%，且组件里还藏着两个互相矛盾的比特币报价。模型这次自己识破并把噪声写进了 `limitations`（输出侧闭环反而成了亮点），但这个防线是模型自觉而非材料保证，属 P1。其余检查项基本干净。

## 体检明细

### A. 顺序

**A1 段落编排** — 判定：合理 — 证据：段落目录（投影 L8-13）显示结构为 System 纪律（336 字符，0.2%）→ User 任务+铁律（1,465，15.4%）→ Runtime Input（6,372，67.0%）→ 输出规格（954，10.0%）→ Response Rules（371，3.9%）。任务定义在数据之前、输出规格紧贴 Response Rules 收尾，主干「任务 → 数据 → 规格 → 规则」完整不断裂。铁律块（原文 offset 354-1819）前置且逐条编号，无重要指令埋进数据。

**A2 数据时序** — 判定：合理（未发现问题）— 证据：本站无时序数据段；`event_date`/`effective_date` 均 2026-09-02 且与 `published_at` 一致（原文 offset ~1860-1890 区域）。材料内的快照时点（"held nearly 106 million Alphabet shares at the end of June"）是 6 月末持仓、9 月 2 日报道，模型已正确标注两个月空窗（输出 `limitations[1]`）。

**A3 few-shot 打断** — 判定：不适用 — 证据：全文无 `Example:` 类示例段（原文 offset 0-9516 通读确认）。

**A4 重试差异** — 不适用（单 attempt 站）。

### B. 体量与冗余

**B1 体量账本** — 判定：P1（病灶集中在 Runtime Input 内部构成）— 证据：总 9,516 字符中 Runtime Input 占 6,372（67.0%），其中：
- `raw_text_excerpt` 3,742 字符（占全文 39.3%），但正文只有约 1,425 字符（"BRK-B GOOG This article first appeared…" 到 "Terms and Privacy Policy Your Privacy Choices" 之间），前后网页外壳合计约 2,317 字符（62%）。
- `competing_hypotheses` 三条合计 1,294 字符（hyp_base 112 / hyp_counter_4a0b9f25fe 692 / hyp_counter_7c11370905 490）。

必要性：摘录正文部分删掉则卡片无法成立，必要；外壳部分删掉判断只会变好（见 B3）；假说块删掉则 supports/refutes 失去引用背景，有必要，但两条对抗假说各 692/490 字符的五环/四环全文，对只需引用 hypothesis_id 的本站是超配（见下方 P2）。

**B2 站内重复** — 判定：合理（未发现问题）— 证据：3,78 亿、106M 股、10.4%、3,647 亿、8% 爱荷华等事件数字在 prompt 内各出现一次（仅存在于 raw_text_excerpt）；输出规格里的 tier 枚举在 User 铁律（offset ~570 区域）与 `event_material.tier` 字段各出现一次，属规则+数据的最小重复。

**B3 粒度错配** — 判定：P1 — 证据：摘录外壳段（原文 offset 约 1890-2650 前段 + 约 3700-5300 后段）包含：导航（"Oops, something went wrong Skip to navigation Skip to main content"）、大盘行情条（S&P 7,675.71 / Dow 53,050.10 / VIX 15.45 等）、"Warning! GuruFocus has detected 3 Warning Sign with MSFT" 推广条、约 20 只个股涨跌榜（DELL/CRDO/GTLB/PANW/NVDA/INTC…）、"Top economic events" 房贷利率表、"Edit your Dock"。其中行情组件还自相矛盾：BTC-USD 先报 "77,105.00 -776.43 -1.00%"，后又报 "63,925.97 -905.20 (-1.40%)"；GTLB、CRDO 也各出现两个不同价。这是采集端清洗（正文抽取）缺位，把「预处理该干的活」连同噪声一起推给了模型注意力，且矛盾报价有被误当事实引用的风险。

### C. 质量

**C1 指令冲突** — 判定：合理（未发现冲突）— 证据：System 纪律（offset 18-354）要求不编造、条件语言、evidence_refs 只能来自输入；User 铁律要求事实/解读分离、机制只写假设、弱来源保守解读，方向一致。`event_type` 一处看似矛盾（铁律说"不用你填——填了也会被底账值覆盖"，输出规格又列为可选字段），但规格括号内同样注明"模型填了也会被覆盖"，两处口径一致，非冲突；模型实际填了 "mega_cap_market_news"（输出 L6），按约会被覆盖，无害。

**C2 死指令** — 判定：合理（抽查 5 项全活）— 证据：输出规格 12 个字段与 `output.validated.json` 顶层逐一对应：`fact_summary`/`interpretation`/`mechanism_hypothesis{financial_link,hypothesis}`/`supports_hypotheses`/`limitations`/`needs_data_confirmation`/`upgrade_candidate`/`passport` 全部有实值且形状符合；`mechanism_hypothesis.financial_link="earnings_path"` 在九渠道枚举内。无「规格要求但输出缺失」项。

**C3 黑话词典** — 判定：P2 — 清点结果：
- 重点排查对象「法典」：**0 次出现**（另「三明治」「门脸」「恒空」「4C」「黄金坑」均 0 次）。本站无该传染源。
- 系统自造词（均出现在 `competing_hypotheses` 引文内，非任务规则层）：「主线」6 次（首次 hyp_base 开头 "主线解释：当前主导NDX收益/风险的主要矛盾…"，label 与指代可由上下文自明）；「吸收」4 次（"吸收端是唯一能维持当前倍数的变量" / "吸收引擎仍在运转"——新模型难自明，首次无解释）；「折现率复合体」1 次（无解释）；「转化信号」1 次（"主线自己登记的转化信号"，所指登记表未随材料提供，新模型只能猜）；「防备」3 次（语境可懂）。
- 传染源判定：「吸收（端/引擎）」「转化信号」「折现率复合体」三项首次出现无解释，列入传染源；但因 User 铁律明文"竞争假说块……其中的表述与数字不得当事实引用"（offset ~700 区域），且输出未裸用（见 E1），实际危害有限。

**C4 数据新鲜度** — 判定：合理（数据新鲜，唯一隐患已控）— 证据：`published_at` 2026-09-02 15:34 UTC，prompt 落盘 2026-09-03，事件当日分析；passport 与 event_material 日期一致（输出 L30-36）。6 月末持仓快照是 13F 披露节奏的正常滞后，模型已在 `limitations[1]` 明示"约两个月的空窗期"。隐患：外壳行情组件的报价（S&P/BTC/个股）无 as-of 标注且互相矛盾，字段名暗示"当前行情"但值可能是陈旧/错乱缓存——模型本次明写"页内与事件本体无关的数字一律不作事实依据"（输出 `limitations[3]`），风险被输出端吸收。

### D. 隔离

**D1 越权扫描** — 判定：合理（未发现越权）— 证据：关键词扫描 `final_adjudication`/`thesis_draft`/`browser_sidecar`/`user_decision_profile`/`golden_pit`/`apparent_cross_layer_signals`/layer card 路径：全部 0 命中。`competing_hypotheses` 含 L1-L5 层面统计（QQQ vs MA200 7.9%、FGI 35.4、RSI 46.56 等），但这是本站设计内的引用背景（供 supports/refutes 引用），且 Runtime Input 尾部带显式边界（原文 offset ~8100 区域）："event_ref_only": true / "must_not_become_l1_l5_evidence_ref": true / "must_not_feed_back": true——隔离靠设计声明而非泄漏，属合规提供。

### E. 输出闭环

**E1 叙事字段体检** — 总判定：高质量，仅轻度术语传染。
- **黑话传染**：P2。`interpretation` 两处使用假说块术语："与建设性对抗假说中'吸收引擎仍在运转'的论证同向"（带引号+归属，可辩护）、"对主线假说的直接检验力弱"、"也不触及折现率与风险溢价这条约束腿"——"主线""约束腿""吸收"未给最终报告读者解释。缓解因素：每处均嵌在因果链里且可回溯到 prompt 内假说原文，下游读者是第三层综合裁决（本就共享这套词表），未裸列。
- **复读机检测**：通过。对全部叙事字段与 prompt 做最长公共子串检测，最大重合仅 13 字符（"Yahoo Finance"、"earnings_path"，均为专名/枚举），无 ≥15 字符连续复述；fact_summary 全部换成"报道称……"的转述句式，是作答不是背题。
- **簿记语言密度**：合理。叙事散文里 `earnings_path`、hypothesis_id 只出现在结构字段或以"收入路径"等通语出现；数字（378 亿、10.4%、8%）均嵌在比较/判断句中。
- **长度纪律**：合理。输出规格对叙事字段无长度要求；实际 fact_summary 约 330 字、interpretation 约 450 字，判断先行、逐条成段。

**E2 因果对** — 未发现「材料缺陷 → 输出毛病」的负向因果；发现一对**正向闭环**：材料缺陷（raw_text_excerpt 混入矛盾行情组件，BTC "77,105.00" 与 "63,925.97" 并存，原文 offset 约 1950 与约 4050 区域）→ 输出主动免疫（`limitations[3]`："转载页混入大量行情组件与广告……比特币出现77,105与63,925两种并存报价，提示页面行情数据可能延迟或出错，页内与事件本体无关的数字一律不作事实依据"）。材料噪声被转化为一条高质量限制声明，这是本站最值得保留的行为样本。轻度负向关联仅剩 C3/E1 那条术语传染（假说块术语 → 叙事散文未解释使用），因有归属限定，不构成实际误导。

## 病灶清单（按严重度排序）

| 严重度 | 病灶 | 证据位置 |
|---|---|---|
| P1 | `raw_text_excerpt` 62%（约 2,317/3,742 字符）为页面外壳（导航/行情条/自选股榜/广告），占全文 prompt 约 24%；组件内含互相矛盾的 BTC 报价（77,105 vs 63,925）及约 20 只无关个股行情，既浪费注意力又有误引风险 | 原文 Runtime Input 内摘录字段；投影 L58 |
| P2 | 两条对抗假说以五环/四环全文（692+490 字符）供给只需引用 hypothesis_id 的本站，链条细节超出必要 | 原文 competing_hypotheses 段 |
| P2 | 假说块内部黑话「吸收（端/引擎）」「转化信号」「折现率复合体」首次出现无解释；轻度传染至输出叙事（"吸收引擎""主线假说""约束腿"未向报告读者解释，均有归属限定） | 原文 hyp_counter_4a0b9f25fe/hyp_base 文本；输出 interpretation |

未发现：A 环顺序问题、「法典」等站间传染词、C1 指令冲突、C2 死指令、C4 过期数据、D1 越权、E1 复读机输出。

## 修复建议

1. **（对 P1·外壳污染）** 改事件采集管道的正文抽取：对 Yahoo 等转载页在入账前剥离导航/行情组件/自选股榜/广告尾巴（按锚点截取正文、或按"连续标的价格模式"过滤），`raw_text_excerpt` 只留正文；若无法保证清洗质量，新增布尔字段如 `body_extraction_confident` 让模型显式降分寸，而不是依赖模型自觉识破。
2. **（对 P2·假说全文超配）** 给 event_card_interpreter 投喂假说块时改为一句话摘要 + hypothesis_id（每条 ≤150 字符），完整链条留在 thesis/critic 站；本站只做「这条事件与哪个假说同向/相悖」的归类判断。
3. **（对 P2·黑话无解释）** 在假说块首次注入处加一行 30 字内的注释（如"吸收端＝盈利上修对估值的消化能力；转化信号＝主线预登记的翻多触发条件"），或在 user message 铁律里补半句；同时可在叙事字段纪律里点名这几个词"进入叙事时须带半句解释"。
4. **（加固亮点）** 把本站输出 `limitations[3]` 的"噪声免疫"行为提炼进该站 few-shot 或铁律示例，使其从模型自觉变成可复现的站级行为。
