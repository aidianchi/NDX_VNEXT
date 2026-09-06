# event_card_interpreter.event_69b3ccdfc80285bb 上下文体检报告

## 结论

本站整体健康：编排合理、无越权、无指令硬冲突、输出闭环质量高（模型甚至主动防御了材料缺陷）。最重的两个问题都在**采集端而非提示词端**：① 事件"正文"是整页抓取，约 3,400 字符（占 prompt 25%）是行情条/广告/作者简介/相关文章等页面杂物；② 页面行情组件无时点标注且混用 9/1 收盘与 9/2 盘中两个交易日，"At close" 字段名暗示当前、实为昨日。两处模型都识别并防御了，但债在源头。

对象：attempt_1（唯一 attempt），模型 glm-5.3-flash，prompt 13,786 字符（meta.json:9）。分析时点 2026-09-03 03:04（文件落盘时间），事件日 2026-09-02。output.validated.json 与 attempt_1.parsed.normalized.json 内容一致（已比对）。

## 体检明细

### A. 顺序

- **A1 段落编排** — 合理 — 指令区 0–1819（System 约束 0–354，User Message 任务+铁律 354–1819），Runtime Input 1819–12461（77.2%），输出规格 12461–13415，Response Rules 13415–13786。输出规格虽离任务描述约 1.1 万字符，但它位于注意力高端区（末尾）且紧贴 Response Rules，关键纪律（来源分寸、叙事说人话）全部在数据之前。未发现重要指令埋进数据洼地。
- **A2 数据时序** — 合理（页面组件内混杂另记 C4）— event_date = effective_date = 2026-09-02（offset 2250/2266），与 run 时点差 1 天，无过期段落冒充当前状态。
- **A3 few-shot 打断** — 合理 — 无示例段落，主干「任务→数据→规格」未被切开。也无示例可供参考；对本站非必需，不算病灶。
- **A4 重试差异** — 不适用 — 单 attempt（meta.json:5-6）。

### B. 体量与冗余

- **B1 体量账本** — **P1** — 段落占比（投影目录）：`## Runtime Input` 10,642（77.2%）＞ User Message 1,465（10.6%）＞ 输出规格 954（6.9%）＞ Response Rules 371（2.7%）＞ 系统约束 336（2.4%）。Runtime Input 内部：raw_text_excerpt 约 8,027 字符（占全文 **58.2%**）、competing_hypotheses 约 1,698（12.3%，三条假说 112/692/490 字符）。最大段 excerpt 是必要材料，但其中约 **3,400 字符（42%）是页面杂物**：
  - 页面 chrome + 行情条：offset 2442–3118（676 字符），同一 107 字符行情条「S&P 500 7,680.10 +0.53% Dow Jones 53,066.20 … Russell 2000 2,944.50 +0.74%」逐字重复 **6 次**（count=6，642 字符）；
  - 订阅广告：offset 3890–4222（332 字符，"Just released. Our analysts … Enter your email …"）；
  - 作者简介 + 联系方式：offset 8294–8830（536 字符）；
  - 涨跌幅榜组件：offset 8830–9591（761 字符）；
  - 相关文章列表 + 续读引流：offset 9210–10343（约 1,130 字符）。
  判据检验：删掉这 3,400 字符，模型判断不会变差——正文真正的财报数字（营收 46.97B、AI 订单 60.9B、积压 95B 等，offset 5000–5700 区间）全部保留。competing_hypotheses 段必要（supports/refutes 的唯一引用对象，输出实测引用了 hyp_base/hyp_counter_4a0b）。输出规格必要（形状契约）。
- **B2 站内重复** — P2 — 最重的是行情条逐字×6（见 B1）；其余为源文自带（"95 billion backlog" 在 Quick Read 与正文各一次，offset ~3580 / 5701），非系统搬运。三层复读（raw_data/facts/brief）问题本站不存在——本站输入只有一份材料。
- **B3 粒度错配** — P2 — 行情条与涨跌幅榜是同构表格噪声，模型需要的 min/max/最新/变化率一个都不在其中（同一批指数数字重复 6 遍，个股行情反而与正文自述的 $445.40 +4.8% 口径不一致）。这是抓取噪声问题，与 B1 同源，预处理债不该推给模型注意力。

### C. 质量

- **C1 指令冲突** — 未发现硬冲突；两处张力记 P2：
  1. 铁律「数字嵌在因果链里…不陈列」（offset 1610）vs `fact_summary`「只包含原材料事实」（规格 offset ~12530）。事实摘要天然是数字陈列；输出 fact_summary 743 字符确为密集数字陈列。规则未对事实字段豁免。
  2. System rule 4「所有 evidence_refs 必须来自本次输入」（offset 205），但本站输出规格（12461–13415）**没有 evidence_refs 字段**——通用系统提示与本站契约错位。本站模型无暴露面，属死约束而非冲突。
- **C2 死指令** — 合理 — 抽查全部 12 个规格字段（event_id/fact_summary/interpretation/entities/event_type/mechanism_hypothesis/supports_hypotheses/refutes_hypotheses/limitations/needs_data_confirmation/upgrade_candidate/passport），全部在 output.validated.json 出现且形状匹配。`entities` 输入为 `[]`、输出为 ["DELL","NVDA"]，与「由代码按采集底账装配回填」（offset 1477）的约定一致，装配链活。
- **C3 黑话词典** — P2 — 清点：
  - 有解释（好）：tier 词表 10 个取值逐档给了分寸（User Message，offset ~700–870）；「关联不足」退出有定义（offset 1344）；「护照/passport」形状在规格中定义。
  - 无解释但可推断：「底账」3 处（offset 1477/1481 区间及规格区）未解释，新分析师模型可从上下文推出"登记底册"义，列观察项。
  - **传染源**：competing_hypotheses 文本内系统自造黑话零解释——「折现率复合体」（10769）、「薄至为负的风险补偿」（~10790）、「吸收端/约束端」（10818）、「转化信号」（11081）、「多源趋弱共振」（11846）、「链条五环/四环」。prompt 只给了「不得当事实引用」护栏（offset 1253），没有任何术语解释。实测已传染输出：interpretation 使用了「盈利吸收"腿"」「约束腿」（引用假说原词、带归属），下游综合裁决可读（同系统生成），对报告读者未解释 → 记 P2。
- **C4 数据新鲜度** — **P1** — 字段级日期健康（见 A2），但**正文内行情组件无时点标注且混用两个交易日**：'At close' DELL 450.20 +5.93%（offset 2461 起）实为 **9/1 收盘**（425 × 1.0593 = 450.20），而 'Companies Mentioned' DELL $444.76 +4.65%（offset 9591 起）是 **9/2 盘中**（425 × 1.0465 = 444.76），正文自述 "$445.40 midmorning…up 4.8%" 亦为 9/2 盘中。"At close" 字段名暗示"最新收盘"，值却是昨日——正中 C4 定义。模型在 limitations[3] 防御了（"时点与口径未注明，不能当作正式行情数据使用"），但 fact_summary 尾句仍引用该快照并写"当日"，存在轻微残留歧义。

### D. 隔离

- **D1 越权扫描** — 合理 — 关键词全文扫描全部 0 命中：final_adjudication、thesis_draft、browser_sidecar、user_decision_profile、golden_pit、layer_card、apparent_cross_layer_signals、layer_raw_data、context_brief 均 0 次。competing_hypotheses 含主线/反方假说全文，是本站设计输入（supports/refutes 引用对象），非越权；boundary 块（offset 12333–12461）显式声明 `event_ref_only / must_not_become_l1_l5_evidence_ref / must_not_feed_back`，回流隔离在位。

### E. 输出闭环

- **E1 叙事字段体检** — 合格，一处 P2 传染 —
  - 黑话传染：interpretation 使用假说原词「盈利吸收"腿"」「约束腿」，带归属引用（"主线假说把吸收端视为…"）但未给读者半句解释（同 C3 传染源）。
  - 复读机检测：抽 5 句（fact_summary 首句、interpretation 首句、mechanism_hypothesis.hypothesis、limitations[0]、needs_data_confirmation[0]）均为中文再组织，未发现 ≥15 连续字符与 prompt 逐字重复（源材料为英文，引语均经翻译转述）。
  - 簿记语言：hypothesis_id/枚举/字段名只住结构字段；叙事中数字嵌在因果链服务比较（如"23 倍对 44 倍"的对照、"只触及吸收侧，完全不触及约束腿"）。干净。
  - 长度纪律：规格无长度要求（N/A）；实际 fact_summary 743 / interpretation 610 字符，克制。
- **E2 因果对** — 两对成立（均为"材料缺陷 → 模型正确防御"的正向因果），一对不成立：
  1. 行情组件混两日无时点（offset 2461–3118、9591–9686）→ limitations[3] 显式降级 + needs_data_confirmation[2] 要求正式行情核对。成立（防御性）。
  2. 源文数字矛盾：Cramer 引语称英伟达 "trades at just 23 times this year's earnings estimate"（offset 6952–7057）vs "P/E of 23 versus NVIDIA's 44"（offset 3648）与 "NVIDIA sits near 44"（offset 6541）→ limitations[2] 点名矛盾 + needs_data_confirmation[3] 要求核对。成立（防御性）。
  3. B1 页面杂物 → 输出损伤：不成立。模型未把广告/榜单当事实，limitations[4] 反而主动标注"正文混有推广内容…需人工甄别"。浪费成立、伤害未发生。

## 病灶清单（按严重度排序）

| 严重度 | 病灶 | 证据位置 |
|---|---|---|
| P1 | 事件正文为整页抓取，约 3,400 字符页面杂物（占 prompt 25%），行情条逐字重复 6 次 | prompt offset 2442–3118、3890–4222、8294–10343 |
| P1 | 页面行情组件无时点标注且混用 9/1 收盘与 9/2 盘中，"At close" 暗示当前实为昨日 | prompt offset 2461、9591；output limitations[3] |
| P2 | 假说文本内部黑话（折现率复合体/吸收端/转化信号/多源趋弱共振）零解释，且已传染输出叙事字段（带归属未释义） | prompt offset 10769/10818/11081/11846；output interpretation |
| P2 | System rule 4 引用本站不存在的 evidence_refs 字段（通用约束与站契约错位） | prompt offset 205 vs 12461–13415 |
| P2 | 「数字不陈列」铁律未对 fact_summary 豁免，与事实字段性质相抵 | prompt offset 1610 vs 规格区 ~12530 |
| P2 | 「底账」未解释（可推断，观察项） | prompt offset 1477、1481 |

## 修复建议

1. **（对应 P1-1）** 改采集端 event material builder：正文抽取改用 readability 式正文提取，剥掉页面 chrome、广告、作者简介、涨跌幅榜、相关文章；行情条同一数据只保留一份。预计每事件省约 3,400 字符（本例 25%）。
2. **（对应 P1-2）** 页面行情快照必须携带 quote_timestamp 并与正文叙述口径对齐；无法定时的组件数据整块丢弃（正文已有行情叙述，快照无增量价值）。
3. **（对应 P2-1）** 竞争假说文本入卡前附一行术语微注，或维护「黑话 → 半句解释」词典随假说块注入；同时要求输出叙事字段引用假说术语时首次出现给半句解释（与既有"生僻术语首次出现给半句解释"铁律对齐）。
4. **（对应 P2-2）** 系统级约束按站裁剪：输出契约无 evidence_refs 字段的站不注入 rule 4，避免死约束随站繁殖。
5. **（对应 P2-3）** 铁律「数字不陈列」补一句「fact_summary 除外」，消除规则与字段性质的自相张力。
