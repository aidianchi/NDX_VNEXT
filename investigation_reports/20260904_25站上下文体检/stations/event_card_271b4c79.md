# event_card_interpreter · event_271b4c79178e1077 上下文体检报告

> 体检对象：`prompt_audit/event_card_interpreter.event_271b4c79178e1077/attempt_1.prompt.txt`（7,455 字符，单 attempt，模型 glm-5.3-flash）
> 输出：`output.validated.json`（与 `attempt_1.response.raw.txt` 逐字段一致，validated 未做改写）
> 行号均指 prompt.txt 行号；「字符位」为该片段在 prompt 全文的字符 offset。

## 结论

本站整体健康：**无 P0/P1 级病灶，编排、隔离、输出纪律均合格**。最重的两个问题都在材料端：①事件正文摘录 1,658 字符中约 83%（1,382 字符）是网页导航/页脚样板，真正的正文只有 276 字符，纯 token 浪费（P1）；②run 级固定搬运的竞争假说块 1,582 字符（占全 prompt 21%）与本事件（个体禁业令）零相关。模型顶住了这两处噪声，输出是一张干净的「关联不足」退出卡，未发现材料缺陷传导为输出毛病。

## 体检明细

### A. 顺序

- **A1 段落编排** — 判定：合理。结构为 System 纪律（L1-6）→ 任务铁律（L13-26）→ Runtime Input（L29-80）→ 输出规格（L82-94）→ Response Rules（L96-101）。任务定义与输出要求分居数据两侧，但 L100 明确「形状以规格为准」，规格+响应规则紧贴尾部收束，指令不被数据淹没；Runtime Input 本身就是待处理对象，居中合理。铁律共 10 条集中在 260 字符内（L16-26），无埋没。
- **A2 数据时序** — 判定：合理。本卡无时间序列；时间字段为单点 passport（published_at 2026-08-27 / event_date 2026-08-27 / effective_date 2026-09-02，L36-38）。effective_date=2026-09-02 恰为 run 日期，字段名略歧义（更像"进入本次分析"而非事件生效日），但 prompt L21 对 tier 分寸有定义、对 effective_date 语义无解释——新模型只能靠字段名猜。记 P2 观察项，不影响本卡。
- **A3 few-shot 打断** — 判定：合理（无示例）。全文无 Example 块；L100 提到「正文里的示例只解释语义」是预防性条款，实际无示例，无打断问题。
- **A4 重试差异** — 不适用（单 attempt，meta.json `"attempts": 1`）。

### B. 体量与冗余

- **B1 体量账本** — 总 7,455 字符。分账（与另一实例 event_5d714693f02f5ec6 逐字比对确认边界）：
  - **严格模板**（10 卡逐字相同）：System Message+约束 354（L1-11）＋ User Message 铁律 1,465（L13-26）＝头部 1,819；allowed_financial_links 170（L47-57）；boundary 96（L75-79）；输出规格 954＋Response Rules 371＝尾部 1,325。合计 **3,410 字符（45.7%）**。
  - **run 级共享**（10 卡逐字相同，已比对）：competing_hypotheses 1,582（L58-74，三条假说 112/692/490 字符）。模板+共享＝**4,992 字符（67.0%）**。
  - **事件独有**：event_material ≈2,156（JSON 序列化口径，L31-46），其中 raw_text_excerpt 1,658。**仅占 28.9%**，且实质性事件文本仅 276 字符＝全 prompt 的 **3.7%**。
  - 最大三段：Runtime Input 4,311（57.8%）/ User Message 1,465（19.7%）/ 输出规格 954（12.8%）。头部与尾部模板对「防止编造、约束输出形状」必要，删之判断变差；**competing_hypotheses 对本卡删掉判断不变差**（supports/refutes 输出均为空数组，1,582 字符零引用）。
- **B2 站内重复** — 判定：轻微。同一事实在 prompt 内无复读；payload.json 与 prompt 的 Runtime Input 重复属落盘审计设计，非上下文缺陷。唯一重复形态：模型被要求填 event_id/passport（输出照抄输入 L32/34-38 原值，response.raw.txt 已含全字段），是「填了也会被覆盖」的自我搬运（见 C1 第二条）。
- **B3 粒度错配** — 判定：P1，本站最实的一条。raw_text_excerpt（prompt 字符位 2,347 起）实测：导航/BOM 前段 1,204 字符＋页脚 178 字符＝**1,382（83%）样板**，实质正文（"The Federal Reserve Board on Thursday announced…"至"…Misappropriation of customer funds"）仅 276 字符（17%）；且摘录以 UTF-8 BOM 乱码 `ï»¿` 开头（采集清洗未剥离）。模型需要的正是那 276 字符。10 张同源事件卡叠加，此浪费 ×10。

### C. 质量

- **C1 指令冲突** — 判定：P2，两对轻度冲突。
  1. L18「机制只能写成假设……并从给定的九个金融传导渠道里选择」＋规格 L88 `mechanism_hypothesis`（必填） vs L23「与纳指 100 没有可说明关联的事件，诚实输出 `interpretation: 与判断对象关联不足`」——**退出通道下 mechanism_hypothesis 填什么没有定义**。输出以自创「格式占位」假设化解（output.validated.json → mechanism_hypothesis.hypothesis："……仅为格式占位，不构成有效传导线索"），自洽但属模型自由发挥。
  2. L24「`entities`、`event_type`……`event_id` 与 `passport` 由代码按采集底账装配回填，**不用你填**」 vs L99「JSON 顶层字段必须匹配： event_id, …, passport」（12 个字段全列）——模型被同时要求"别填"和"必须输出"。实测模型照抄输入值填了全部字段（raw 顶层 12 键齐全），无实害，但字面打架。
- **C2 死指令** — 判定：未发现。抽查 6 字段：fact_summary/interpretation/mechanism_hypothesis/limitations/needs_data_confirmation/upgrade_candidate 输出全有且语义吻合规格（L83-93）；supports/refutes 允许为空，本卡为空属诚实退出非缺答。
- **C3 黑话词典** — 判定：P2（轻度）。**「法典」在本站 prompt 与输出中均 0 次**（grep 实证），用户关注的传染未发生。实际清点：
  - `底账` ×5（L24、L83、L86、L87），无定义；「采集底账」凭上下文可猜为"事件登记册"，半透明。
  - `卡级标签` ×1（L26），同上。
  - 竞争假说文本内部黑话：`约束端/吸收端`（L61）、`解保险`、`赔率结构`、`转化信号`（L66）、`Top10权重代理`、`一线`（L71），均无解释。缓冲：L22 明确「竞争假说块只作 supports/refutes 的引用背景，其中的表述与数字不得当事实引用」，且本卡未引用任何假说表述，实际零伤害。
- **C4 数据新鲜度** — 判定：合理。published_at/event_date/effective_date 三字段齐全（L36-38），事件 2026-08-27 距 run 日 2026-09-02 共 6 天，官方新闻稿无过期问题。**正文可用性：有正文**（raw_text_available: true），但如 B3 所述"有而稀"——83% 是网页样板。另外 tier=official_macro 与实际内容（美联储官网新闻稿）相符，来源等级标注准确。

### D. 隔离

- **D1 越权扫描** — 判定：未发现。grep `final_adjudication|thesis_draft|browser_sidecar|user_decision_profile|golden_pit|layer_card|apparent_cross_layer` 全文 **0 命中**。competing_hypotheses 是 thesis 层产物，但事件卡属外围解读站，L75-79 boundary 明确 `event_ref_only / must_not_become_l1_l5_evidence_ref / must_not_feed_back`，L22 限定其"仅作引用背景"——属设计内引用且带隔离声明，非越权。

### E. 输出闭环

- **E1 叙事字段体检** — 总体良好，一处轻度传染：
  - **黑话传染**：P2。叙事字段直出系统内部称呼「主线」×2——interpretation「被标为政策与金融条件类的**主线**索材」、limitations[2]「采集标签（政策与金融条件、**主线**）」。「主线」是主假说的内部代号（源自 L61「主线解释：」与 trigger_reasons="mainline"），叙事中未给读者任何解释。其余黑话（底账/约束端等）未进输出。
  - **复读机检测**：未发现。抽 5 句核验（fact_summary 首句、interpretation 首句、limitations[0]、limitations[3]、needs_data_confirmation[0]），均无 ≥15 连续字符与 prompt 重合；interpretation 首句「与判断对象关联不足。」是 L23 命令的 9 字符标准退出语，属合规照办。
  - **簿记语言密度**：合格。「采集标签」「格式占位」等簿记词均嵌在解释因果链里服务判断（如 mechanism_hypothesis 明说"仅为格式占位，不构成有效传导线索"），无裸列字段名/ID。
  - **长度纪律**：输出规格未对叙事字段设长度要求；实际 fact_summary 137 字、interpretation 199 字，克制且判断先行，无违规可谈。
  - **事实一致性**：fact_summary 与原文逐点吻合（人名 Gadiel Rosario-Alvarado、机构、事由 misappropriation of customer funds、日期），无编造。
- **E2 因果对** — 能连成一对：
  - **因果对**：规格缺口（L18＋L88 强制 mechanism_hypothesis 必填且必选九渠道 × L23「关联不足退出」无字段出口定义）→ 输出被迫自创占位假设（output.validated.json → mechanism_hypothesis："该假设在本材料范围内没有可观测落点，**仅为格式占位**"）。输出自我标注未误导，故 P2。
  - B3 的 83% 样板、1,582 字符无关假说块两处材料缺陷，输出端**未**产生对应毛病（模型准确提炼并全部忽略）——连不成因果，反而说明本卡模型抗噪能力足够；浪费是真实的，误判没有发生。

## 病灶清单（按严重度排序）

| 严重度 | 病灶 | 证据位置 |
|---|---|---|
| P1 | 正文摘录 83%（1,382/1,658 字符）为网页导航/页脚样板，实质正文仅 276 字符，且带 BOM 乱码 `ï»¿`；10 卡同源叠加放大 | prompt 字符位 2,347 起（L42 raw_text_excerpt） |
| P2 | competing_hypieses 块 1,582 字符（21%）run 级固定搬运，本卡零相关零引用 | prompt L58-74；输出 supports/refutes 均空 |
| P2 | mechanism_hypothesis 必填 ×「关联不足退出」无出口定义，逼出模型自创「格式占位」假设 | prompt L18/L23/L88 ↔ output mechanism_hypothesis |
| P2 | 「不用你填」（L24）与「顶层字段必须匹配全部 12 字段」（L99）字面冲突 | prompt L24 vs L99 |
| P2 | 内部黑话无解释：「底账」×5、「约束端/吸收端/解保险」等；输出端「主线」×2 直出叙事字段 | prompt L24/61/66/71；output interpretation/limitations[2] |
| P2 | effective_date 字段名语义未定义（值=run 日期），靠猜 | prompt L38；C4 |

未发现：P0 级问题；越权（D1 零命中）；指令性复读输出；事实编造；「法典」黑话（0 次）；时序倒置。

## 修复建议

1. **（对 P1）改采集清洗**：raw_text_excerpt 入库前剥离站点导航/页脚/`ï»¿` BOM，只保留正文段；或直接以「Press Release 日期行→正文末行」为切窗。收益约 1,382 字符/卡 ×10 卡。
2. **（对病灶 2）假说块按需注入**：竞争假说块压缩为每条一行摘要（id＋一句主旨），事件与假说词面零重叠时整体省略；卡片确需引用时再取全文。预计本类卡省 1,300+ 字符。
3. **（对病灶 3）给退出通道定义字段出口**：在 User Message 铁律中加一句「走关联不足退出时，mechanism_hypothesis 整体填 null（规格同步改为可空）或固定填 sentinel 值」，消除模型自由发挥空间。
4. **（对病灶 4）统一口径**：L99 的必匹配字段清单改为「模型产出 8 个智力字段，event_id/entities/event_type/passport 可省略、由底账装配补齐」，与 L24 对齐。
5. **（对病灶 5）微改词表**：User Message 首次出现「采集底账」处加半句定义（"即事件登记库"）；叙事纪律（L25）追加示例「不得在叙事中直接写『主线』，应写『基准情形假说』」。
6. **（对病灶 6）**在 passport 规格处给 effective_date 一句定义（"材料进入本次分析的日期"）。

---

*取证命令与中间数字：模板边界由与 event_5d714693f02f5ec6 实例逐字 diff 确认（head/tail/links/hypotheses/boundary 全等）；样板占比、字段字符量由 python 实测；「法典」与越权关键词 grep 均 0 命中。*
