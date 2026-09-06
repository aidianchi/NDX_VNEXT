# event_card_interpreter.event_5d714693f02f5ec6 上下文体检报告

> 检查时间 2026-09-04。材料：`prompt_audit/event_card_interpreter.event_5d714693f02f5ec6/`（attempt_1，唯一 attempt，model glm-5.3-flash，prompt 11,520 字符）。下引行号均指 `attempt_1.prompt.txt`；excerpt 内部偏移指 `raw_text_excerpt` 字符串内 offset。

## 结论

本站编排、隔离、输出闭环都健康，唯一的实质性病灶在**事件材料本身**：`raw_text_excerpt` 共 5,774 字符，其中约 **62.2%（3,590 字符）是 Yahoo 页面抓取噪音**（导航、行情快照、广告、无关旧闻标题、隐私页脚），真正的文章正文只有 2,184 字符——噪音占了整份 prompt 的 31.2%。模型（GLM）这次扛住了：`fact_summary` 只取正文事实，且在 `limitations` 里主动声明了噪音隔离；但把整页 dump 直接塞给模型是把采集层该做的清洗推给模型注意力，噪音区还含有同一指标两个互相矛盾的报价（Bitcoin 77,132.93 vs 63,925.97），一旦被误当事实会直接污染事件卡。次要问题：passport/event_type 的「不用你填」与输出规格「必填」存在一处措辞冲突（未造成危害）。

## 体检明细

### A. 顺序

- **A1 段落编排** — 合理。结构为：系统纪律（行 1-11，336 字符）→ 任务定义+铁律（行 13-26，1,465 字符）→ Runtime Input（行 29-80，8,376 字符）→ 输出字段规格（行 82-94，954 字符）→ Response Rules（行 96-101，371 字符）。任务定义在最前、输出规格+响应规则收尾，符合「头尾放指令、中间放数据」的注意力布局；铁律（行 16-26）与输出规格（行 82-94）相距约 8.4k 字符，但规格本身是自包含的枚举说明，且行 100 明确「形状冲突时以规格为准」，风险可控。
- **A2 数据时序** — 合理。单事件材料：`published_at` = `event_date` = `effective_date` = 2026-09-02（行 36-38），meta.json `effective_date: 2026-09-02`、attempt 落盘 2026-09-03，材料与分析时点同日，无过期数据冒充当前。
- **A3 few-shot 打断** — 未发现。全 prompt 无示例段落（无 `Example:` 样式内容），主干未被切碎。
- **A4 重试差异** — 不适用。meta.json `"attempt": 1, "attempts": 1`，单次成功。

### B. 体量与冗余

- **B1 体量账本** — **P1**。段落占比（投影段落目录）：Runtime Input 72.7%（8,376）＞ User Message 12.7%（1,465）＞ 输出规格 8.3%（954）＞ Response Rules 3.2%（371）＞ 系统纪律 2.9%（336）＞ System Message 0.2%（18）。Runtime Input 内部：`raw_text_excerpt` 5,774 字符（占 Runtime Input 69%、占全 prompt 50.1%），三条竞争假说合计 1,294 字符（112+692+490），其余为枚举与 boundary。**最大段 raw_text_excerpt 对判断的必要性只有正文那 2,184 字符**：删掉 3,590 字符噪音，判断不会变差、反而更安全（见 C4/B3 证据）；竞争假说段删掉则 supports/refutes 无从落笔，必要。
- **B2 站内重复** — 基本未发现。九个传导渠道枚举出现 3 次（User Message 行 18「九个金融传导渠道」、Runtime Input `allowed_financial_links` 行 47-57、输出规格行 88），每次约 90-130 字符，合计 <400 字符，且规格那份是约束生效所必需，属可接受冗余。Runtime Input 与 payload.json 的重复是审计落盘设计，不进模型上下文，不计。
- **B3 粒度错配** — **P1**（本站形态是「页面噪音未清洗」而非「行情序列全量 dump」）。证据（excerpt 内 offset）：头部 0-727 为导航+行情快照（`"Oops, something went wrong Skip to navigation Skip to main content ... S&P 500 7,675.71 +44.24 +0.58% Dow 30 53,052.83..."`）；正文起点 727（`"Chicago Fed President Austan Goolsbee..."`）；正文中间 1220-1349 插入广告（`"Warning! GuruFocus has detected 5 Warning Signs with TTGPF. Is QQQ fairly valued? Test your thesis with our free DCF calculator."`）；正文终点约 3040（`"...turn the AI spending boom into an unexpected headwind for valuations."`）；尾部 3040-5774 共 2,734 字符全是页脚：隐私链接 + 约 10 条**只有标题没有正文**的无关旧闻（`"Fed's Goolsbee says oil shock could exacerbate inflationary impulse of AI hype Reuters • 3mo ago"` 等）+ 个股报价表。噪音合计 3,590 字符（62.2%）。min/max/最新值这类预处理在该段落同样缺位——首尾两块行情快照互相矛盾（见 C4），本应全部剥离。

### C. 质量

- **C1 指令冲突** — **P2**，一处。User Message 行 24："`entities`、`event_type`（采集标签）、`event_id` 与 `passport` 由代码按采集底账装配回填，**不用你填**——填了也会被底账值覆盖"；但输出规格行 94 标 `passport`（**必填**）、行 99 Response Rules 要求 "JSON 顶层字段必须匹配: ... passport"。一边说别填、一边说必填。实际输出两全了（模型照抄输入值填了 passport，输出行 30-36 与底账一致），未造成危害，但措辞应统一。其余无冲突：「不得编造数字」（行 6-7）与输出规格无强制定量字段，兼容；「不要复读免责声明」（行 26）与系统纪律条件语言要求（行 8）不冲突。
- **C2 死指令** — 未发现，抽查字段全部为活。①`fact_summary`/`interpretation`/`mechanism_hypothesis` 输出齐全（output.validated.json 行 3-9）；②`needs_data_confirmation` 输出 4 条（输出行 23-28），且下游 `event_section_summary/attempt_1.prompt.txt` 行 54/76/98/120 明确嵌入了各卡片的 `needs_data_confirmation` 字段——下游真实消费；③`supports_hypotheses`/`refutes_hypotheses` 输出引用了真实存在的 `hyp_base_f076e8b18c`/`hyp_counter_4a0b9f25fe`（输出行 11-16 vs 输入行 60/65）；④铁律「不要复读免责声明」得到遵守，输出无此类收尾句。
- **C3 黑话词典** — 本站重点核查项。**「法典」「门脸」「三明治口径」「恒空」在本 prompt 中均未出现**（全文检索 0 命中）。存在的内部词：①「底账」（行 24 两处、行 83/86/87 各一处，共 5 次）——系统自造词（采集底账=事件采集登记簿），首次出现（行 24）无解释，新模型只能靠上下文猜；但它只出现在「不用你填/由代码装配」的否决性指令里，猜错代价低，**不列入传染源**。②「主线解释」（行 61）、「折现率复合体」「吸收端」（行 61 内）——thesis 层内部提法，出现在竞争假说文本内，行 22 已明确「竞争假说块只作 supports/refutes 的引用背景，其中的表述与数字不得当事实引用」，已隔离。③`kept_unresolved`（行 62/67/72，3 次）——状态枚举无解释，属惰性簿记值，模型无需使用。
- **C4 数据新鲜度** — **P1**（与 B3 同源）。事件本体新鲜：tier=`reliable_mainstream_report`、`raw_text_available: true`（行 41），正文 2,184 字符真实可用且含可验证数据点（9/4 非农、9/10 PPI、9/11 CPI），**不是只有标题**。但噪音区混入了未标注的过期/自相矛盾数据：同一 Bitcoin 报价在 excerpt 内出现两个值——头部快照 `"Bitcoin USD 77,132.93 -748.50 -0.96%"`（offset ~330）与尾部快照 `"BTC-USD Bitcoin USD 63,925.97 -905.20 (-1.40%)"`（offset ~4310），相差 21%，显系不同时点的缓存残片；另有大量 "3mo ago""5mo ago" 的旧闻标题无日期边界说明。`effective_date` 字段名暗示「当前有效」，值本身正确（2026-09-02），但保护范围只覆盖元数据、不覆盖正文噪音。

### D. 隔离

- **D1 越权扫描** — 未发现越权。全文检索 `final_adjudication`/`thesis_draft`/`browser_sidecar`/`user_decision_profile`/`golden_pit`/其他层 layer card 路径均 0 命中。`competing_hypotheses`（主假说+两条反方假说）出现在输入里是**任务设计内**的：铁律行 19 要求把结论落实在 supports/refutes 字段，行 22 同时给假说文本设了「不得当事实引用」的使用边界；Runtime Input 的 `boundary` 块（行 75-79：`event_ref_only` / `must_not_become_l1_l5_evidence_ref` / `must_not_feed_back`）显式声明了本卡不得回流为层证据。隔离设计完整。

### E. 输出闭环

- **E1 叙事字段体检** — 合格。①黑话传染：`fact_summary`/`interpretation`/`mechanism_hypothesis.hypothesis` 全部用行业通语（折现率、限制性政策、服务业通胀），C3 清单中的内部词（底账、主线解释、kept_unresolved）在叙事散文里 0 次出现；"主线解释""多头对抗假说"仅作为对输入假说的指称出现且语义自明（输出行 4）。②复读机检测：抽查 5 句叙事（fact_summary 3 句、interpretation 2 句），无 ≥15 连续字符与 prompt 完全相同——材料是英文、叙事是中文转述，结构性排除了背题；对假说文本的最接近处（"期货收紧定价会被证伪" vs 输入 "若期货收紧定价被证伪"）仅 8 字符重合且为转述。③簿记语言密度：叙事中无字段名/ref/ID/枚举裸列，数字（9月4日、9月10日、9月11日）均嵌在验证条件因果链里，符合铁律行 25。④长度纪律：输出规格未对叙事字段设长度要求，铁律要求「判断先行、每条一个意思」，`interpretation` 为一段 ~450 字长文，信息密度高但方向明确，未违反明文规则。
- **E2 因果对** — 成立一对：**材料缺陷（B3/C4：excerpt 62.2% 页面噪音、含矛盾报价与无关标题）→ 输出被迫自带隔离声明**。输出 `limitations[2]`（输出行 20）：`"原始材料为整页抓取，夹带与正文无关的行情快照、个股报价和其他媒体的关联标题（均只有标题、无正文），这些页面内容未按本事件事实处理；关联标题如需引用必须另行采集原文。"` ——模型识别出了与体检完全相同的噪音清单并消耗一条 limitations 篇幅做分诊说明。这是负向闭环：GLM 这次扛住了，但正确性依赖模型注意力而非数据质量；换个弱模型或换个事件，噪音区的矛盾报价（Bitcoin 77,132.93 vs 63,925.97）被误编入 `fact_summary` 的风险是真实的（铁律行 17 恰恰允许 fact_summary 收录"材料里逐字有的东西"，噪音也在材料里）。

## 病灶清单（按严重度排序）

| 严重度 | 病灶 | 证据位置 |
|---|---|---|
| P1 | raw_text_excerpt 62.2%（3,590/5,774 字符）是页面抓取噪音，正文仅 2,184 字符；噪音占整份 prompt 31.2%，采集层清洗缺位 | prompt.txt 行 42；excerpt offset 0-727（导航+行情）、1220-1349（广告）、3040-5774（页脚+无关标题） |
| P1 | 噪音区含同一指标两个矛盾报价（Bitcoin 77,132.93 vs 63,925.97）及无边界旧闻标题，误读即污染 fact_summary | excerpt offset ~330 与 ~4310；铁律行 17 允许"逐字收录"放大此风险 |
| P2 | passport/event_type「不用你填」（行 24）vs 输出规格「必填」+顶层字段必须匹配（行 94/99）措辞冲突 | prompt.txt 行 24 vs 行 94、99 |
| P2 | 「底账」（5 次）首次出现无解释；属低风险否决性指令语境，未传染输出 | prompt.txt 行 24、83、86、87；输出 0 命中 |
| P2 | `kept_unresolved` 枚举值无解释（惰性簿记，未传染） | prompt.txt 行 62/67/72 |

无 P0。A1-A3、B2、C1（除上）、D1、E1 均未发现问题。

## 修复建议

1. **对应 P1（噪音）**：改采集/装配层，在 `raw_text_excerpt` 进入 payload 前做正文抽取（readability 类正文提取或至少按站点模板剥离导航/页脚/广告/报价组件），把 5,774 字符压到 ~2,200 字符的纯正文；顺带省掉每张事件卡约 31% 的 token。
2. **对应 P1（矛盾快照）**：清洗规则需显式剔除页面内嵌行情/日历组件（它们与事件无关且时点可能互斥）；若担心信息损失，可在 `event_material` 里另立 `page_context` 字段并标注「非事件事实」，与正文物理隔离。
3. **对应 P2（措辞冲突）**：统一 passport/event_type 的口径——要么输出规格对模型填的值标「必填但会被底账覆盖」，要么 User Message 改为「 passport 需按输入原样回填」，二选一。
4. **对应 P2（黑话）**：「底账」首次出现处加半句解释（如「采集底账（即事件采集登记记录）」）；`kept_unresolved` 可不解释，成本大于收益。
5. 不建议动的：prompt 的段落编排、竞争假说的引用边界设定、叙事字段「说人话」铁律——这三处是本站做得最好的部分，本次输出质量（limitations 主动隔离噪音）正是它们生效的证据。
