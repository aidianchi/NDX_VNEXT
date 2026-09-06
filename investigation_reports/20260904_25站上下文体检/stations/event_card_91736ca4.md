# event_card_interpreter · event_91736ca49c5b5c89 上下文体检报告

> 2026-09-04。对象：`prompt_audit/event_card_interpreter.event_91736ca49c5b5c89/attempt_1.prompt.txt`（5,792 字符）。
> 本实例是 10 个事件实例中最瘦的一个。除本报告外未修改任何文件。

## 结论

本站指令编排、隔离与输出纪律都干净，**唯一重病灶在材料准入端（P1）**：一条仅含标题、零正文、零数字的第三方转述材料（`raw_text_available: false`）被标为 `mainline` 送进主链，消耗 5,792 字符 prompt，其中模板 + 运行级常量占 86.2%，事件独有内容仅 13.8%（真实信息约 250 字符）——模型产出的卡也自认只是"极弱的旁证"，却仍请求 `upgrade_candidate: true` 继续消耗下游。次要问题（P2）：主线/反方假说文本携带未解释的内部黑话（"约束端""吸收""折现率复合体""转化信号"），其中"约束端""吸收"已泄漏进输出叙事。

## 体检明细

### A. 顺序

- **A1 段落编排** — 判定：合理 — 证据：System 纪律（offset 18）、任务与铁律（offset 354）、运行数据（offset 1,819）、输出规格（offset 4,467）、Response Rules（offset 5,421）。任务定义在 User Message 首句，输出规格紧贴 Response Rules 收尾，符合「任务 → 数据 → 规格」顺序；全文仅 5,792 字符，无中段注意力洼地风险。
- **A2 数据时序** — 判定：合理 — 证据：材料无时间序列；`published_at`/`event_date`/`effective_date` 全为 2026-09-02（prompt L36-38），口径一致，无过期段冒充当前状态。
- **A3 few-shot 打断** — 判定：合理（无示例）— 证据：全文无 `Example:` 块；但 Response Rules L100 写"正文里的示例只解释语义"，正文实际没有示例，见 C2。
- **A4 重试差异** — 不适用：本站仅 attempt_1。

### B. 体量与冗余

- **B1 体量账本** — 判定：**P1** — 段落占比（投影目录，实测一致）：Runtime Input 2,648（45.7%）＞ User Message 1,465（25.3%）＞ 输出规格 954（16.5%）＞ System Constraints 336（5.8%）＞ Response Rules 371（6.4%）。
  关键拆分（按 offset 实测）：
  - 站模板（System 18 + Constraints 336 + User Message 1,465 + 规格 954 + Response Rules 371）= **3,144 字符（54.3%）**；
  - 运行级常量（`competing_hypotheses` 1,698 + `allowed_financial_links` + `boundary` ≈ 1,847 字符，31.9%）：`hyp_counter_4a0b9f25fe` 已 grep 确认出现在本 run 全部 10 个事件实例及 critic / final_adjudicator / reviser 的 prompt 中，对本站是**逐实例重发的常量**；
  - 事件独有 = `event_material` 块 801 字符（13.8%），其中真实信息仅标题 95 字符（L33）+ 来源/日期/标志位约 150 字符，且 `raw_text_available: false`、`raw_text_excerpt: ""`（L41-42）——**零正文、零数字**。
  判据检验（"删掉会变差吗"）：规格与铁律不可删；`allowed_financial_links` 不可删（机制枚举的合法域）；`competing_hypotheses` 1,698 字符对一条标题级材料明显超配——假说文本单条最长 692 字符（L66），是事件本体信息量的近 3 倍，模型被迫用两篇高密度论文去对照一个 95 字符标题。最大三段中唯一可大幅压缩的就是它（可换成各假说一行的摘要卡）。
  与「弱来源不进主链」宪法的关系：`tier: reliable_mainstream_report`（L35）在站内词表（L21）属第三方转述档、非最弱档（`market_narrative`/`unverified_signal`），**字面上不构成该宪法最弱档**；但「仅标题 + mainline 直采进主链」是否在宪法管辖内，需宪法原文才能定（存疑：需 `弱来源不进主链` 条款的原文）。按体检尺子，仅标题材料走全套主链推理 + 请求升级，判 **P1 明显浪费**。
- **B2 站内重复** — 判定：合理（未发现）— 同一数值/事实在 prompt 内只出现一次；标题、日期均无复读。跨实例的假说块重复已计入 B1。
- **B3 粒度错配** — 判定：合理（未发现）— 本站无行情序列；假说文本里的定量已是预处理后的摘要值（如"RSI 46.56、ADX 11.91"，L71），不是逐行 dump。

### C. 质量

- **C1 指令冲突** — 判定：P2（轻微张力，无实质打架）—
  1. System Constraint 4（L9）"所有 evidence_refs 必须来自本次输入里实际提供的材料条目" vs 本站输出契约**没有 evidence_refs 字段**（规格 L83-110）——通用纪律与本站契约错配，非冲突但属死指令（见 C2）。
  2. L17 "fact_summary 里只许出现材料里逐字有的东西" vs 输出 fact_summary 把英文标题翻译成中文转述（输出 L3）——模型做了宽松执行（翻译≠逐字），但未添加事实且加了"该媒体称"限定语，规则意图（不编造）未破坏；建议措辞改准。
  未发现 P0/P1 级互相打架。
- **C2 死指令** — 判定：P2 — 抽查结果：
  1. 输出 12 个顶层字段全部有值且过 validated（output.validated.json L1-38）——活。
  2. `evidence_refs`（System L9）：契约中不存在 → 本站死指令（通用模板未按站裁剪）。
  3. Response Rules L100 "正文里的示例"：正文无任何示例 → 引用不存在物的死条款。
  4. `upgrade_candidate: true`（输出 L30）是否真被下游消费：本站材料看不到，**存疑，需核对升级流程消费方**。
- **C3 黑话词典** — 判定：P2 — prompt 内部代号清点（基准：FGI、SKEW、put/call、RSI、ADX、MA200、trailing PE、ERP 类通用术语不计）：
  | 代号 | 首现 | 次数 | 首现有无解释 |
  |---|---|---|---|
  | 折现率复合体 | L61（hyp_base，offset≈2,7xx） | 1 | 无 |
  | 吸收端/吸收引擎/吸收 | L61/66/71（假说块内） | 4 | 无 |
  | 约束端 | L61 | 1 | 无 |
  | 转化信号 | L66（"主线自己登记的转化信号"） | 1 | 无，且引用了 prompt 外的内部登记表 |
  | 解保险 | L66 | 1 | 无（行话，可由上下文猜出） |
  全部来自 `competing_hypotheses` 的 thesis 层原文搬运，prompt 未给任何一条释义。**传染源成立：假说块是本站唯一黑话入口。**
- **C4 数据新鲜度** — 判定：合理（未发现过期）— `published_at` 2026-09-02 13:08 UTC（L36），文件落盘 2026-09-03 03:09（UTC 19:09），滞后约 6 小时、距当日美股收盘约 1 小时。输出 `needs_data_confirmation[0]` 要的"当日收盘数据"（输出 L25）在运行时点确实尚未产生——这是事件队列的正常时滞而非数据缺陷；卡片把它列为待确认而非硬填，处置正确。

### D. 隔离

- **D1 越权扫描** — 判定：合理（设计内）— 关键词 `final_adjudication`/`thesis_draft`/`browser_sidecar`/`user_decision_profile`/`golden_pit`/`apparent_cross_layer_signals` 全文零命中。看到的竞争假说是裁决前状态（`status: kept_unresolved`，L62/72/78），且带三重隔离标志（L76-78）`event_ref_only` / `must_not_become_l1_l5_evidence_ref` / `must_not_feed_back`，User Message L22 亦明确假说"表述与数字不得当事实引用"。备注：假说文本内嵌 L3/L5 层定量（L71 的 RSI/ADX/均线占比、L66 的 put/call 1.79、FGI 35.4），属设计内的引用背景，但加重了 B1 的超配问题。

### E. 输出闭环

- **E1 叙事字段体检** — 判定：P2（仅黑话传染一项）—
  - 黑话传染：输出 `interpretation` 出现"约束端主导的解释""冲击已被吸收"（输出 L4），直接沿用 C3 清单里的内部代号且未对报告读者解释。`fact_summary`/`mechanism_hypothesis`/`limitations` 干净；"风险补偿"属通用术语不计。
  - 复读机检测：对 12 个叙事串与 prompt 做最长公共子串机械核验，除 `fact_summary` 逐字引用英文标题 95 字符（规则明确允许的"材料逐字事实"，非背题）外，**全部 ≤10 字符，无 ≥15 字符复写**。模型在作答，不是背题。
  - 簿记语言密度：叙事字段以因果散文为主，枚举/ID/ref 留在结构字段（`supports_hypotheses` 仅含 2 个 hypothesis_id），符合 L25 的"说人话"铁律。
  - 长度纪律：输出规格未对叙事字段设长度要求，无违规可言。
- **E2 因果对** — 两对成立：
  1. **P1 因果对**：材料仅标题零正文（prompt L41-42，offset≈2,4xx）→ 输出 `interpretation` 近半篇幅是"不能确认/无法区分"的元讨论并自评"极弱的旁证"（输出 L4），`limitations[0]` 明写"材料仅含标题、无正文"（输出 L18）→ 但 `upgrade_candidate: true`（输出 L30）仍请求升级深挖。低信息材料 → 高成本解读 → 追加消耗，因果链完整。
  2. **P2 因果对**：假说块黑话无解释（prompt L61/66/71）→ 输出叙事"约束端""吸收"未解释直出（输出 L4）。传染源 → 传染实锤，一一对应。

## 病灶清单（按严重度排序）

| 严重度 | 病灶 | 证据位置 |
|---|---|---|
| P1 | 仅标题、零数字的第三方转述材料标为 mainline 进主链：模板+运行级常量占 86.2%（3,144+1,847 / 5,792），事件独有仅 13.8%，产出卡自评"极弱旁证"仍 upgrade_candidate=true；是否触「弱来源不进主链」宪法存疑（tier 属中档，需宪法原文定性） | prompt L33/L35/L41-42；输出 L4/L30 |
| P2 | `competing_hypotheses` 1,698 字符对 95 字符标题级材料超配，且为本 run 10 个实例逐份重发的常量（≈1.7 万字符重复投喂） | prompt offset 2,638-4,336；grep `hyp_counter_4a0b9f25fe` 命中 10 实例 |
| P2 | 假说块黑话无解释（折现率复合体/吸收/约束端/转化信号），"约束端""吸收"已泄漏进输出叙事 | prompt L61/66/71；输出 L4 |
| P2 | 通用模板死指令：System Constraint 4 的 `evidence_refs` 本站契约不存在；Response Rules 引用不存在的"正文里的示例" | prompt L9、L100 |
| P2 | "fact_summary 只许逐字" 规格与执行有轻微张力（模型做了翻译转述，未添事实，规则措辞可改准） | prompt L17；输出 L3 |

## 修复建议

1. **（对应 P1）采集准入加门槛**：`raw_text_available: false` 且 `trigger_reasons` 含 `mainline` 的 `reliable_mainstream_report` 材料，先走轻量通道（仅记 event_id + 标题进事件段落汇总），不触发整套 event_card_interpreter 推理；或对仅标题材料强制 `upgrade_candidate` 上限为"由代码按 tier/正文有无覆写"，不允许模型自请升级。需同时核对「弱来源不进主链」宪法原文，把"仅标题"明确纳入管辖（或明文豁免）。
2. **（对应 P2 假说块）假说降维**：发给事件站的 `competing_hypotheses` 换成每条 ≤120 字符的摘要卡（hypothesis_id + 一句主张 + 状态），全文留给 critic/final_adjudicator 等真正裁决的站；10 实例可省约 1.5 万字符重复投喂。
3. **（对应 P2 黑话）** 假说文本入站前做黑话注解（首次出现附半句释义），或在 User Message 加一张 4-5 行的内部代号小词典；输出侧在叙事字段纪律里点名"约束端/吸收端等主线内部词不得直出"。
4. **（对应 P2 死指令）** System Constraints 按站裁剪：本站删 evidence_refs 条或改写为"supports/refutes 只能引用输入中的 hypothesis_id"；Response Rules 删"正文里的示例"半句。
5. **（对应 P2 措辞）** L17 改为"fact_summary 只许包含材料本身承载的事实（允许翻译，不允许添加）"，消除"逐字"与翻译行为的张力。
