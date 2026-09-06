# event_card_interpreter.event_69090f897651b377 上下文体检报告

- 站：event_card_interpreter（单事件实例 event_69090f897651b377），attempt 1，模型 glm-5.3-flash
- 原文：`prompt_audit/event_card_interpreter.event_69090f897651b377/attempt_1.prompt.txt`，6,170 字符（meta.json `prompt_chars: 6170`，实测一致）
- 输出：`output.validated.json`（与 `attempt_1.parsed.normalized.json` 逐字节一致；与 `attempt_1.response.raw.txt` JSON 等价，实测 `json.loads(raw)==out` 为 True）
- 证据坐标均为该 prompt 文件内的**字符偏移**（Python `str.find` 实测）。

## 结论

本站材料编排、隔离与输出闭环基本健康，是全套 run 里少数「模板比数据还多」的小站：6,170 字符里运行时数据只占 49%，瘦是因为事件本身小（一条 Wind 报道，摘录约 450 字且 `raw_text_available: true`），不是材料缺失。最重的病灶在事件原文质量（C4）：摘录是拼接品——开头 4 个字「英伟达财报超预期」（offset 2309）与后文「财报发布前下跌」（offset 2569）时态矛盾且无过渡，模型据此把英伟达财报当成**未来**检验点，漏掉了摘录开头已经给出的「超预期」这一事实，构成一条能连上的「材料缺陷 → 输出遗漏」因果对（E2）。次要问题：竞争假说块的上游黑话无解释，并有一处（「盈利吸收」）传染进了输出叙事字段。

## 体检明细

### A. 顺序

- **A1 段落编排** — 合理。段落全景（字符偏移实测）：System Message 0-18；System-Level Constraints 18-354；User Message（任务+铁律）354-1819；Runtime Input 1819-4845；输出字段规格 4845-5799；Response Rules 5799-6170。任务定义在最前，输出规格紧贴 Response Rules 收尾、离生成时刻最近，6k 量级不存在中段注意力洼地问题。
- **A2 数据时序** — 合理（字段层面）。`published_at/event_date/effective_date` 三时间戳齐全（offset 2186-2225 一带），effective_date=2026-09-02 与 meta.json 的分析时点一致，材料发布 2026-08-28 早 5 天、属正常事件延迟且已被标注。但**摘录内部**时序混乱，归入 C4，见下。
- **A3 few-shot 打断** — 不适用。prompt 无示例段落。
- **A4 重试差异** — 不适用。单 attempt（meta.json `"attempts": 1`）。

### B. 体量与冗余

- **B1 体量账本** — 基本合理，1 项 P2。占比（投影段落目录+偏移实测交叉验证）：Runtime Input 3,026 字符（49.0%）、User Message 1,465（23.7%）、输出规格 954（15.5%）、Response Rules 371（6.0%）、Constraints 336（5.4%）、System Message 18（0.3%）。Runtime Input 内部：event_material 约 938 字符（15.2%），**competing_hypotheses 块 1,698 字符（占全文 27.5%、占 Runtime Input 56%）**，boundary 约 128（2.1%）。最大三段：假说块、铁律、事件材料。判定：铁律与规格是本站质量的主要来源，删任何一条判断都会变差，必要；假说块是 supports/refutes 判断的引用背景，必要但**超配**——两条 counter 假说全文塞了约 60 个定量细节（57bp、PE 44% 分位、RSI 46.56、FGI 35.4、702.7-703.4 支撑簇……offset 3019-4717），而输出对这些的消费只是 3 个 hypothesis_id 引用，压到每条 1/3 篇幅不损失判断力（P2）。**站特别关注①的答案**：6,170 字符的「瘦」是任务本性（单条新闻事件），不是缺料——摘录自含标题、来源、日期、完整叙事与收尾句，且 `raw_text_available: true`（offset 2260 附近）。附带发现：模板侧（Constraints+User Message+规格+Rules=3,126 字符，50.7%）比数据侧还多，事件越小模板占比越高，属可接受的固定开销。
- **B2 站内重复** — 未发现实质重复。数据只出现一遍；唯一的轻度重复是「entities/event_type 由代码装配、填了也被覆盖」在铁律（offset 1180 附近）与输出规格（offset 5013、5093）各说一遍，约 60 字符，可忽略。
- **B3 粒度错配** — 数据侧无（本站没有行情序列 dump，市场数据是叙事摘录）。假说块的「论证链全文 vs 卡片只需核心主张」是同性质问题的变体，已并入 B1 的 P2。

### C. 质量

- **C1 指令冲突** — 1 项 P2 措辞张力。铁律说「`fact_summary` 里只许出现材料里**逐字**有的东西」（offset 430 附近），输出规格说「`fact_summary`（必填）：字符串 —— 只包含原材料**事实的摘要**」（offset 4885 附近）。逐字与摘要不可兼得，两处严格度不一致；实际输出走的是「转述+关键数字保留」路线（fact_summary 411 字符，内含与原文完全一致的最长片段「高通上涨1.97%，英特尔上涨0.87%，博通下跌0.32%，费城半导体指数上涨0.20%」34 字），符合规格的松口径。意图无歧义（只许事实、不许编造），故仅记措辞张力，非真冲突。其余规则（不编造数字 vs 机制假设化、不复读免责声明 vs 卡不能证明涨跌）互为补充，无打架。
- **C2 死指令** — 未发现。规格 12 个顶层字段在 output.validated.json 里全部存在且非空；抽查 `mechanism_hypothesis.financial_link="valuation_multiple"`（在 allowed_financial_links 九渠道内，offset 3025 附近）、`passport` 五字段与底账逐字一致、`supports/refutes` 引用的 3 个 hypothesis_id 全部来自输入。系统约束第 4 条提到 `evidence_refs`（offset 130 附近），本卡输出规格无此字段——属通用模板在无该字段站点上的惰性残留，无害但可按站裁剪（P2 级备注）。
- **C3 黑话词典** — **传染源清单（均无解释）**，全部位于竞争假说块（上游 thesis/counter_thesis 原文直传）：
  - 「折现率复合体」「薄至为负的风险补偿」「吸收端/吸收能力」（hyp_base，offset 3202 起）——系统自造的利率-估值框架词，新模型无法只凭 prompt 理解；
  - 「主线自己登记的**转化信号**」（hyp_counter_4a，offset 3400 附近）——指涉上游簿记（某处登记的信号清单），prompt 里没有该登记；
  - 「**链条五环**」「**链条四环**」「方向对抗·建设性」「解释对抗·结构性」（offset 3175、4210 附近）——上游论证格式标签，无解释；
  - 「**多源趋弱共振**」（hyp_counter_7c，offset 4213 附近）——主线术语，无解释。
  - 有解释的：tier 九档词表（offset 655-770）附了分寸说明，是正面样板；「采集标签」「底账」「竞争假说块只作引用背景」均有上下文说明。
  - 铁律明确「竞争假说块……表述与数字不得当事实引用」（offset 1000 附近），且要求叙事字段「生僻术语首次出现给半句解释」——假说块内的黑话是刻意直传的上游原文，风险不在 prompt 自身而在**传染输出**（见 E1）。
- **C4 数据新鲜度** — **本站最重病灶（P1）**。摘录是拼接品且无过渡标注：
  - 开头即「**英伟达财报超预期** 8月中旬以来……」（offset 2309）——读作财报**已发生且超预期**（文章发布 2026-08-28）；
  - 后文「英伟达在**财报发布前**下跌1.59%」（offset 2569）、「在英伟达财报及后续货币政策信号**落地前**……窄幅整理」（offset 2450 附近）——又读作财报**未发生**；
  - 两段时态矛盾。「英伟达财报超预期」形似从文章另一小节（盘后段）拼来的小标题，拼接处无「（盘后更新）」之类的过渡说明。
  - 后果见 E2 因果对①。

### D. 隔离

- **D1 越权扫描** — 未发现越权。全文扫描 `final_adjudication / thesis_draft / browser_sidecar / user_decision_profile / golden_pit / apparent_cross_layer_signals / layer_card` 均 0 命中。本站看到了竞争假说块（含上游定量数据），但这正是该站职能所需——其任务就是把事件映射到 supports/refutes（铁律 offset 1000 附近明示），且 boundary 块（offset 4717-4845）三重围栏 `event_ref_only / must_not_become_l1_l5_evidence_ref / must_not_feed_back` 全部为 true，输出 limitations 第 5 条也复述了该边界。判定：设计内暴露，围栏完好。

### E. 输出闭环

- **E1 叙事字段体检** — 总体优良，1 处黑话传染：
  - **黑话传染**：`mechanism_hypothesis.hypothesis`（142 字符）末句「……该渠道的压制假设即被证伪，**倍数支撑回到盈利吸收一侧**」——「盈利吸收」是 C3 清单里 hyp_base「吸收端」家族的黑话，未给读者半句解释，违反铁律「生僻术语首次出现给半句解释」。全输出仅此 1 处（`interpretation`、`fact_summary`、`limitations`、`needs_data_confirmation` 扫描「折现率复合体/多源趋弱共振/转化信号/解保险/链条」均 0 命中）。P2，单发非扩散。
  - **复读机检测**：抽全部 3 个散文主字段与 prompt 做最长公共子串比对——`interpretation` 与 `mechanism_hypothesis` 最长公共片段 **0 字**（无 ≥15 字符重合）；`fact_summary` 最长重合 34 字（芯片行情句），属铁律明确要求的逐字事实，非背题。通过。
  - **簿记语言密度**：叙事散文里无字段名/ID/枚举裸列；ID 类（hypothesis_id）正确住在 supports/refutes 结构字段；数字均嵌在因果句中（如「三大指数涨跌幅均不超过0.21%，而苹果、Meta、微软涨逾1%……指数平静与个股分化并存」）。通过。
  - **长度纪律**：输出规格未对叙事字段设长度限制；fact_summary 411 字 / interpretation 367 字 / mechanism 142 字，比例得当，无超长或过瘦。
- **E2 因果对** — 2 对：
  - **对①（材料 C4 → 输出事实遗漏）**：摘录拼接缺陷（offset 2309「英伟达财报超预期」 vs offset 2569「财报发布前」，无过渡）→ 输出把财报整体当未来事件：`interpretation`「英伟达财报因此是材料点名的最近检验事件」、`needs_data_confirmation[0]`「英伟达财报**实际业绩**与数据中心/AI相关收入及资本开支指引」——而摘录开头已给出业绩「超预期」。下游读者会以为财报检验点还在前方。模型侧亦有责任（开头四字它确实读到了并写进了 fact_summary……实则没有：fact_summary 未提「超预期」），但无过渡的拼接摘录是直接诱因。严重度 P1（有 boundary 围栏兜底，不至于进正式证据链）。
  - **对②（假说块黑话 C3 → 叙事传染 E1）**：hyp_base「吸收端是唯一能维持当前倍数的变量」（offset 3202）→ `mechanism_hypothesis.hypothesis`「倍数支撑回到盈利吸收一侧」。P2。

## 病灶清单（按严重度排序）

| 严重度 | 病灶 | 证据位置 |
|---|---|---|
| P1 | 事件摘录为无过渡拼接品，财报时态自相矛盾（开头「已超预期」vs 后文「发布前」），导致输出把英伟达财报当未来检验点、漏掉「超预期」这一已有事实 | prompt offset 2309 / 2569 ↔ output.validated.json `interpretation`、`needs_data_confirmation[0]` |
| P2 | 竞争假说块携带 5+ 个无解释上游黑话（折现率复合体、吸收端、转化信号、链条N环、多源趋弱共振），且「盈利吸收」已传染输出叙事 1 处 | prompt offset 3202/3400/4213 ↔ output `mechanism_hypothesis.hypothesis` |
| P2 | 假说块 1,698 字符（占全文 27.5%）携带约 60 个定量细节，输出仅消费 3 个 hypothesis_id，可压缩约 2/3 | prompt offset 3019-4717 ↔ output `supports/refutes` |
| P2 | 「fact_summary 只许逐字」（铁律）vs「事实的摘要」（规格）措辞张力 | prompt offset 430 / 4885 |
| P2（备注） | 通用约束第 4 条提及本站不存在的 `evidence_refs` 字段；「代码装配」说明在铁律与规格重复两遍 | prompt offset 130 / 1180 / 5013 |

## 修复建议

1. **（对 P1）改采集侧摘录装配**：`raw_text_excerpt` 拼接多段时在拼接处插入显式分隔（如「……」+ 时间标记或「（盘后更新）」），或当摘录首句与其余正文时态冲突时降级 `tier`/加 `excerpt_spliced: true` 标记；不要把另一小节的标题裸拼进正文开头。
2. **（对 P1 的输出侧兜底）**在 event_card_interpreter 的铁律中加一条：「摘录内出现时态冲突时，在 limitations 里显式登记『材料内部时序不一致』，不得默认取其一」。
3. **（对黑话传染）**在竞争假说块入口加一行约定：「假说文本中的系统自造词（如『吸收端』『转化信号』）在 supports/refutes 与叙事字段中引用时需转写为通用表述，不得原样带入叙事字段」。
4. **（对假说块超配）**向上游约定：传给 event_card_interpreter 的假说文本可截取每条的核心主张句（首句+结论句），论证链细节留在引用背景的 full 版本按需取，预计每实例省 1,000+ 字符。
5. **（对措辞张力）**统一口径：铁律改为「fact_summary 只许包含原材料中的事实（可转述，数字与限定语保持原样），不得混入推断」。
6. **（模板裁剪，低优先）**按站裁掉无对应字段的通用约束条目（evidence_refs），「代码装配」说明只保留在输出规格一处。
