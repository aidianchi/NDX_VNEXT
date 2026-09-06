# event_card_interpreter.event_f6b2da3c8dbb4737 上下文体检报告

## 结论

本站整体健康：编排清晰、无指令冲突、无越权、无编造数字，输出是一张分寸得当的高质量事件卡。最重的两个问题都不在编排而在**工具与材料端**：① 投影截断器把尾部数字 155.18 从中间劈成残留「5.18」，与 integrated_adjudicator 的 22.92 **同根因**（固定字符数截断不感知数字边界，已实锤）；② raw_text_excerpt 是未清洗的网页抓取——纳指行情组件在 8,000 字符摘录里重复 6 次、混有作者简介与推广模块，属于「预处理该干的活」被推给了模型，好在模型全部正确识别并写进了 limitations。

## 体检明细

### A. 顺序

- **A1 段落编排** — 判定：合理 — 证据：段落目录（投影 offset 6-14）。结构为：系统纪律（336 字符，2.4%）→ 任务+铁律（1,465 字符，10.6%）→ Runtime Input（10,631 字符，77.2%）→ 输出规格（954 字符，6.9%）→ Response Rules（371 字符，2.7%）。任务定义在数据之前，输出规格紧贴数据之后且 Response Rules 明示「形状以上面输出字段规格为准」，主干未被切碎。数据段占 77% 但本站任务就是解读这段数据，位置合理。
- **A2 数据时序** — 判定：不适用/合理 — 本站无时序序列。事件时间字段齐全且自洽：published_at `Tue, 01 Sep 2026 16:13:44 +0000`、event_date `2026-09-01`、effective_date `2026-09-02`（投影 offset 52-54）。
- **A3 few-shot 打断** — 判定：合理（无示例）— 全文无 `Example:` 类插入。
- **A4 重试差异** — 判定：不适用 — 仅 attempt_1。

### B. 体量与冗余

- **B1 体量账本** — 判定：合理。最大三段：Runtime Input 10,631（77.2%，其中 raw_text_excerpt 独占 8,000 字符）、User Message 1,465（10.6%）、输出规格 954（6.9%）。逐一过「删掉判断会变差吗」：raw_text_excerpt 是本站唯一事实来源，必要；铁律段每条都在输出里被兑现（见 C2），必要；输出规格被 Response Rules 引用为准，必要。未发现可删段落。
- **B2 站内重复** — 判定：合理（仅 1 处可忽略）。标题在 `event_material.title` 与 raw_text_excerpt 开头各出现一次（「Oracle Falls 4% as Bond Selloff Tests Its Debt-Funded AI Buildout」，后者原文出现 2 次）；竞争假说三段各仅出现一次。未发现 layer_raw_data/layer_facts/context_brief 式三层复读。
- **B3 粒度错配** — 判定：P2。证据（原文 excerpt 实测，excerpt 起点约 byte 4543）：
  - 纳指行情组件 `Nasdaq 100 29,159.40 +0.…` 在 8,000 字符摘录中**重复 6 次**（页面导航条在抓取时未去重）；
  - 摘录头部是页面 chrome：`Skip to content ❚❚ At close S&P 500 7,680.10 +0.53% Dow Jones 53,066.20…`；
  - 中段混有与事件无关的作者简介（`With a master's degree in education, David has taught at the elementary, high school…`，约 byte 12100 起）与尾部无关行情表 `Biggest Winners C CHTR … 450.20 +5.93% T TTD Tra`（byte 12480-12580）。
  这约 1,000+ 字符是采集端该剥掉的噪声。模型未被其误导，反而主动标注（见 E2），但每次 run 每个事件都在重复支付这笔注意力税。

### C. 质量

- **C1 指令冲突** — 判定：未发现。铁律互相咬合：`event_type`/`trigger_reasons` 是采集标签（User Message，投影 offset 38）与「关联不足退出」（offset 39）一致；「标签与正文对不上时优先走关联不足」与输出规格 `event_type` 标注「模型填了也会被覆盖」（offset 103）自洽。
- **C2 死指令** — 判定：未发现（抽查 8 项全活）。对照 output.validated.json：fact_summary✓ interpretation✓ mechanism_hypothesis.financial_link=`discount_rate`（在九渠道枚举内）✓ supports/refutes 引用真实 hypothesis_id `hyp_base_f076e8b18c`/`hyp_counter_4a0b9f25fe`✓ limitations 7 条✓ needs_data_confirmation 5 条✓ upgrade_candidate=true✓ passport 五字段与 event_material 逐字一致✓。
- **C3 黑话词典** — 判定：基本无传染源。「法典」一词本站 prompt 中出现 **0 次**。内部代号清点：`主线`（首次出现在 competing_hypotheses[0]，投影 offset 77，带内嵌自释「当前主导NDX收益/风险的主要矛盾…」）；`反方`（offset 82，上下文「方向对抗·建设性（对主线的中性偏防守姿态做多头对抗）」半自释）；`采集底账`（offset 40，有半句说明「由代码按采集底账装配回填，不用你填」）。新入场模型仅凭 prompt 基本可懂。残留一项见 E1（输出端）。
- **C4 数据新鲜度** — 判定：合理。事件发布 2026-09-01 16:13 UTC，run 日期 2026-09-02，effective_date=2026-09-02，无过期数据、无「字段名暗示当前但值是旧」的情形。**事件原文材料质量**（本站特别关注②）问题归入 B3：摘录含 6 次重复行情组件、作者简介、推广模块（输出 limitations 第 7 条自己承认「新闻与推广混合排版降低材料干净度」）；且页面行情模块（纳指 100 `29,159.40 +0.21%`）与正文盘中口径（`QQQ 跌 0.9%`）矛盾，源头是「At close 快照」与正文写作时点不同——材料未标注，是本站唯一实质性的材料质量缺陷（模型正确兜住，见 E2）。

### D. 隔离

- **D1 越权扫描** — 判定：未发现越权。7 个关键词 `final_adjudication`/`thesis_draft`/`browser_sidecar`/`user_decision_profile`/`golden_pit`/`apparent_cross_layer`/`layer_card` 在原文中全部 **0 命中**。competing_hypotheses 三段全文（约 900 字符，含「过去3个月等权跑赢市值加权约8个百分点」等具体数字）属设计内引用背景——supports/refutes 需引用其 hypothesis_id，且铁律明确「其中的表述与数字不得当事实引用」（投影 offset 38）；输出核查确认模型只把假说当「表述」引用、未引其数字，边界被遵守。`boundary.event_ref_only/must_not_feed_back`（offset 91-95）为元数据约束，非越权。

### E. 输出闭环

- **E1 叙事字段体检** —
  - **黑话传染**：P2。interpretation 直用「主线假说」「反方建设性假说」未给报告读者解释（fact_summary 干净；「折现率对阵盈利上修」是主线假说文本的压缩改写，下游 integrated_adjudicator 看得懂，但第三层报告读者未必）。
  - **复读机检测**：未发现。抽 5 句核验，叙事均为中文改写英文原文（如 fact_summary「Oracle 2026财年资本开支557亿美元」对原文 `capital expenditure totaled $55.7 billion, up from $21.2 billion`），无 ≥15 连续字符逐字复现。
  - **簿记语言密度**：低。数字嵌在因果链（「ORCL跌4%、SKYY跌2% 跌幅大于 QQQ跌0.9%」服务杠杆分化判断）；ref/ID 只在结构字段。mechanism_hypothesis 结尾「本卡不将其写成已发生的因果」接近但未违反「不复读免责声明」铁律（禁的是必涨必跌式收尾）。
  - **长度纪律**：规格未对叙事字段设长度要求。fact_summary 单段约 1,000 字符塞了约 20 个事实，与「每条一个意思」有张力——P2，属「转录式摘要」。
  - **数字真实性抽查**：142.82/200.45/161.76/710.30/4.78/244.12/29,159.40 在原文各出现 1 次；$55.7B/$23.7B/$43B/$5B/$122.3B/$218.7B/$553B 各命中原文（如 `producing a cash outflow $23.7 billion greater than`）。**零编造**。
- **E2 因果对** —
  - 对 1（材料噪声 → 输出正确兜底）：材料缺陷「行情模块 29,159.40 +0.21% 与正文 QQQ -0.9% 口径矛盾」（excerpt 头部 byte ~4735 起）→ 输出 `limitations[4]` 明确标注「时间口径不一致，纳指100当日实际方向无法从本材料确认」且 `needs_data_confirmation[1]` 要求独立行情源核对。**好的因果闭环**。
  - 对 2（投影缺口 → 输出无恙）：截断劈开 155.18 → 输出全程未提 CHTR（该值本属无关行情噪声），**未造成下游伤害**，但校验器缺口成立，见下节。
  - 材料问题 → 输出毛病的**恶性**因果：未发现。

## 额外任务：155.18 投影缺口定位（结论：与 22.92 同根因，实锤）

- **它是什么数**：Yahoo 页面「Biggest Winners」行情组件里 **Charter Communications（CHTR）的股价**：`Biggest Winners C CHTR Charter Communications 155.18 +6.15% D DELL Dell Technologies 450.20 +5.93% T TTD Tra`。
- **在什么结构里**：`event_material.raw_text_excerpt`（采集的网页摘录）**尾部**。该字符串总长 8,000 字符（起点约 byte 4543），155.18 位于原文 **byte 12518**，距字符串末尾 62 字符（数字之后还剩 56 字符：` +6.15% D DELL Dell Technologies 450.20 +5.93% T TTD Tra`）。
- **出现 2 次的口径**：prompt.txt 中 1 次（byte 12518）+ attempt_1.payload.json 中 1 次（byte 8623，同一字段），合计 2 次，与校验器报告一致。投影中 **0 次完整出现**。
- **为什么截断没保住它**：长字符串规则是「头 120 + 尾 60」。尾部 60 字符窗口实测为 `5.18 +6.15% D DELL Dell Technologies 450.20 +5.93% T TTD Tra`——窗口起点落在 155.18 起点之后 2 个字符（62 > 60），**「15」被切掉，残留「5.18」这个看似合法的错误文本**。
- **同根因判定**：**是**。与 integrated_adjudicator 的 22.92 完全同根因：按固定字符数切割不感知数字/token 边界，把数字从中间劈开且残留段仍是合法数字形状，导致校验器按完整值匹配报丢、人眼看投影也难察觉。修复应落在截断器（尾部窗口对齐到最近的数字/词边界，或对命中「数值白名单」的尾部内容保完整值），而不是改本站 prompt。

## 病灶清单（按严重度排序）

- P1 | 投影截断器把尾部数字从中间劈开（155.18 → 残留 5.18），与 integrated_adjudicator 22.92 同根因，属截断器通用缺陷 | 原文 byte 12518；投影 offset 58
- P2 | raw_text_excerpt 未清洗：纳指行情组件重复 6 次 + 页面导航/作者简介/无关行情表/推广混排，约 1,000+ 字符噪声 | excerpt 起点约 byte 4543，byte 4735-5167（重复组件）、12100-12581（作者简介+行情表）
- P2 | 材料自身口径矛盾未标注：页面收盘快照（NDX 29,159.40 +0.21%）vs 正文盘中（QQQ -0.9%） | byte ~4735 vs 正文段；输出 limitations[4] 已兜底
- P2 | interpretation 直用「主线假说/反方假说」等内部代号，未对第三层报告读者解释 | output.validated.json interpretation 字段
- P2 | fact_summary 约 1,000 字符单段塞约 20 个事实，与铁律「每条一个意思」有张力，偏转录式摘要 | output.validated.json fact_summary 字段

## 修复建议

1. **截断器**（对 155.18/22.92 根因）：长字符串尾部窗口在落点处对齐最近的词/数字边界（如回退到上一个空白符再起剪），并在投影中标注「尾部边界可能截断数值」；或在截断前扫描窗口边缘是否处于 `[0-9.,%$]+` 内，是则扩窗到边界。改 `context_spread` 投影工具，一处修全站受益。
2. **采集端清洗**（对 B3/C4）：`raw_text_excerpt` 入库前剥页面 chrome——导航条/重复行情组件去重、作者简介与推广模块剔除、尾部无关行情表截除；并在材料里标注行情快照时点（「At close」），消除与正文的隐性口径差。
3. **输出端措辞**（对 E1/P2）：铁律里补半句——叙事字段首次提「主线假说/反方假说」时给一个短语级说明（如「主线假说（系统当前主解释）」）；或在 event_section_summary 层做一次术语展开。
