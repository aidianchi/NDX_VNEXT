# event_card_interpreter（event_a691a49aece7f9ae）上下文体检报告

## 结论

本站编排合理、输出质量高，未发现 P0。最重的两个问题：① 正文摘录（raw_text_excerpt，7,955 字符）约 45% 是抓取页面的导航/页脚模板噪音（约 3,554 字符，占全 prompt 26%），预处理该干的清洗活被推给模型注意力（P1）；② 竞争假说块里的内部黑话「主线」「吸收端」等未加解释，传染进输出的叙事字段（P1，轻度）。

## 体检明细

> 总量：13,675 字符。分段（投影段落目录，offset 回原文核对）：`## System Message` 0–354（18 字符）、System-Level Constraints 含于其中（336 字符）、`## User Message` offset 354–1,819（1,465 字符）、`## Runtime Input` offset 1,819–12,350（10,531 字符，77.0%）、`## 输出字段规格` offset 12,350–13,304（954）、`## Response Rules` offset 13,304–13,675（371）。

### A. 顺序

- **A1 段落编排** — 判定：合理。任务定义与铁律在最前（User Message offset 354–1,819），数据居中，输出规格紧贴末尾（12,350）后接 Response Rules，规格处于注意力近端；无重要指令埋没于数据洼地。
- **A2 数据时序** — 判定：合理（无时序序列）。单一事件材料，published_at / event_date / effective_date 齐备且一致（均为 2026-09-02，offset ~2,350–2,410）。页面挂件行情数字（SPY 765.84 等）是站点模板残留而非运行时数据，见 B1。
- **A3 few-shot 打断** — 判定：合理。无示例插入（prompt 中无 "Example:" 类片段），主干未被打断。
- **A4 重试差异** — 不适用（单 attempt）。

### B. 体量与冗余

- **B1 体量账本** — 判定：P1。最大段是 Runtime Input 内的 `raw_text_excerpt`（7,955 字符，占全 prompt 58.2%），其中：
  - 头部导航/菜单模板：offset 2,314–5,364，约 3,051 字符（Benzinga 多语言菜单、"Top Stocks/Learn" 列表整段重复两遍——"Stock of the Day" 出现 2 次、SPY 765.84 行情条出现 2 次）；
  - 真正新闻正文：offset 5,364–9,765，约 4,401 字符（必要：这是本站唯一的事实来源，删掉判断无从谈起）；
  - 页脚模板：offset 9,765–10,268，约 503 字符。
  - 即约 3,554 字符（占全 prompt 26.0%）删掉后判断不会变差——输出 limitations[4] 反证了这一点：模型明确写「页面行情条数字（SPY/QQQ/NVDA报价）为站点挂件而非文章报道内容，未采用」（output.validated.json）。
  - 第二大块 competing_hypotheses（offset 10,525–12,223，约 1,675 字符，12.2%）：必要——supports/refutes 必须引用 hypothesis_id，模型需知道假说清单；删掉输出规格中三个字段即失效。
- **B2 站内重复** — 判定：P2（轻）。事件标题在 `title` 字段（offset ~2,310）与摘录内（offset ~2,327）出现两遍；导航模板自身整段重复两遍（见 B1）。无三层复读（本站无 layer_raw_data/context_brief 搬运）。
- **B3 粒度错配** — 判定：P1（与 B1 同根）。摘录是未清洗的整页 HTML 转文本，导航、页脚、"Add Benzinga News as your preferred source on Google" 等全量 dump；正文只占 55%。去噪是采集端一行清洗可解决的事，不该由模型注意力现场过滤。

### C. 质量

- **C1 指令冲突** — 判定：P2，三处轻度张力，无 P0 级对立：
  1. System 纪律第 4 条「所有 evidence_refs 必须来自本次输入里实际提供的材料条目」（offset 205）——本站输出规格（offset 12,350 起）没有 evidence_refs 字段，该条在本站是死指令（共享约束的残留），轻微噪音。
  2. User Message「`entities`、`event_type`、`event_id` 与 `passport` 由代码按采集底账装配回填，**不用你填**」（offset ~1,610）vs 输出规格「event_id（必填）」「passport（必填）」及 Response Rules「JSON 顶层字段必须匹配」——「不用填」与「必填」字面矛盾；有「填了也会被底账值覆盖」补救，且输出实际全部填了并与底账一致，未造成实害。
  3. 「`fact_summary` 里只许出现材料里**逐字**有的东西」（offset ~450）措辞过严——材料是英文，输出摘要是中文，按字面无一处"逐字"；实际执行按语义意图（不编造事实）走，输出合规，但措辞会误导。
- **C2 死指令** — 判定：基本活。抽查 5 个字段：`fact_summary`/`interpretation`/`mechanism_hypothesis`（含九渠道枚举，实际选 earnings_path）/`needs_data_confirmation`（5 条具体数据诉求）/`upgrade_candidate`（true）——输出全部按规格产出；`supports/refutes` 用的 hypothesis_id 与输入逐字一致。唯一死指令嫌疑是 System 纪律第 4 条的 evidence_refs（见 C1-1）。
- **C3 黑话词典** — 判定：P1（轻）。通用金融术语（ERP、折现率等）不计。「法典」「三明治」「门脸」「4C」「恒空」等本 run 常见代号在本站 prompt 中均未出现（find 均 -1）。本站自造代号集中在 competing_hypotheses 块（offset 10,525–12,223）：「主线」6 次（首次 10,628）、「约束端」（10,695）、「吸收端」（10,707）、「链条五环/四环」（10,975、11,759）、「转化信号」（10,970）、「吸收引擎」（11,341）、「多源趋弱共振」（11,735）、「方向对抗·建设性」（10,865）、「解释对抗·结构性」（11,682）。首次出现时**均无解释**——新加入的分析师模型只能从「主线解释：」前缀猜个大概，「吸收端」「链条五环」则无从看懂。缓解项：User Message 有「竞争假说块只作引用背景，其中的表述与数字不得当事实引用」（offset ~1,260）；`trigger_reasons: ["mainline"]`（offset 10,260）的语义也有「采集标签不是事实」一句兜底。
- **C4 数据新鲜度** — 判定：合理。event_date = effective_date = published_at 日期 = 2026-09-02（offset ~2,380–2,410），run 落盘时间 2026-09-03 03:00（meta.json），当日材料当日解读，无过期数据、无字段名暗示"当前"而值旧的情况。

### D. 隔离

- **D1 越权扫描** — 判定：合理，未发现越权。`final_adjudicat`、`thesis_draft`、`browser_sidecar`、`user_decision_profile`、`golden_pit`、`apparent_cross_layer_signals`、其他层 layer card 路径在 prompt 中命中均为 0。competing_hypotheses 携带了 thesis/counter_thesis 层的判断内容，但这正是本站设计所需（supports/refutes 的引用背景），且 boundary 块（offset 12,223）显式声明 `event_ref_only: true`、`must_not_become_l1_l5_evidence_ref: true`、`must_not_feed_back: true`，输出 limitations[6] 也复述了该边界——隔离有言在先且被输出遵守。

### E. 输出闭环

- **E1 叙事字段体检**（对象：fact_summary、interpretation、mechanism_hypothesis.hypothesis、limitations、needs_data_confirmation）：
  - **黑话传染**：有，轻度（P1）。interpretation 直接使用「主线判断」「主线矛盾的核心变量：吸收端」「建设性假设」，mechanism_hypothesis 用「吸收端」——均沿自 competing_hypotheses 原文措辞，未向读者解释「主线」指什么。下游"第三层综合裁决"懂这套词，但 User Message 明示读者还包括"报告读者"，对后者即黑话直出。
  - **复读机检测**：未发现。逐句与 prompt 比对，叙事字段与 prompt 的最长逐字重合仅 26 字符（"Yahoo Finance M7 Headlines"，来源名，合法）；interpretation 与 mechanism 最长重合 0 字符，是作答不是背题。
  - **簿记语言密度**：低。叙事字段无字段名/枚举/ref 裸列；数字（129 亿美元、约 10 亿美元、1.5 亿 ARR、86 倍市销率——均可在正文 offset 6,9xx–7,5xx 找到出处，"86 times sales" 为正文原话）嵌在因果链里服务判断。fact_summary 中 Polymarket 76%/Kalshi 9.2% 虽为新闻末尾杂闻，但被 limitations[4] 口径之外的 limitations[3] 标注「不是权威概率估计」，处理得当。
  - **长度纪律**：输出规格未对叙事字段设长度要求，无从违反；interpretation 约 480 字、fact_summary 约 430 字，密度合理。
- **E2 因果对** — 1 对成立：
  - 材料缺陷：raw_text_excerpt 混入约 3,554 字符站点导航/页脚模板（prompt offset 2,314–5,364、9,765–10,268）→ 输出反应：limitations[4] 被迫专门写一句「页面行情条数字（SPY/QQQ/NVDA报价）为站点挂件而非文章报道内容，未采用」。模型守住了（值得肯定），但噪音消耗了一次显式甄别与一个 limitation 槽位——若模板噪音更长或更像正文，即有误导风险。
  - 其余（黑话传染 → E1 措辞）算 C3→E1 的同一条因果，已并入上文，不重复立对。

## 病灶清单（按严重度排序）

| 严重度 | 病灶 | 证据位置 |
|---|---|---|
| P1 | raw_text_excerpt 45% 为站点导航/页脚模板噪音（3,554 字符，占全 prompt 26%），采集端未清洗 | prompt offset 2,314–5,364、9,765–10,268 |
| P1（轻） | 竞争假说块内部黑话（主线/吸收端/链条五环等）无解释，且传染进输出叙事字段 | prompt offset 10,525–12,223；output.validated.json `interpretation`、`mechanism_hypothesis.hypothesis` |
| P2 | System 纪律第 4 条 evidence_refs 为本站死指令（输出规格无此字段） | prompt offset 205 vs 12,350 起 |
| P2 | 「不用你填」vs「event_id/passport 必填」字面矛盾（有覆盖机制兜底，未造成实害） | prompt offset ~1,610 vs 12,350 起 |
| P2 | 「fact_summary 只许逐字」措辞过严（英文材料/中文摘要按字面不可能合规） | prompt offset ~450 |

## 修复建议

1. （对 P1-噪音）在事件采集/装配管道加一步正文提取（boilerplate 剥离，如 readability 类处理或站点模板白名单），保证 raw_text_excerpt 只含新闻正文；预计可减全 prompt 约 26%，并消除输出端被迫写"挂件未采用"式甄别句。
2. （对 P1-黑话）在 competing_hypotheses 装配时为每个假说附一行"读者口径"白话摘要（或把「主线/吸收端/约束端」替换为通用表述），并在 User Message 加一句"叙事字段向报告读者复述假说时用通用措辞"；若叙事字段确要保留「主线」，首次出现给半句解释。
3. （对 P2）三处措辞微调：System 纪律第 4 条限定为"若输出规格含 evidence_refs"；User Message 改为「event_id/passport 照抄输入值即可（会被底账覆盖）」；「逐字」改为「只允许材料中明确给出的事实，不得添加推断与外部数字」。
