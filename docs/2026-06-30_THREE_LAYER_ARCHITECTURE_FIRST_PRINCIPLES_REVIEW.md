# 三层研报架构第一性原理审查：研究、对抗与修复

日期：2026-06-30

审查对象：

- `docs/2026-6-27 三层架构暂定结构.md`
- `docs/2026-06-27_THREE_LAYER_REPORT_ARCHITECTURE_PLAIN.md`
- `docs/2026-06-27_三层研报的辩证法方法论：数据、新闻与市场本质.md`

本文不是替代原三篇文档，而是对它们做一次更严格的研究审查：

1. 先从金融学第一性原理判断这套三层想法是否站得住。
2. 再用对抗式视角挑出它最容易失败的地方。
3. 最后给出修复后的架构版本，供后续工程接入使用。

一句话结论：

> 三层架构方向是正确的，但不能只理解成“三份报告”。更稳健的定义是：数据、事件、综合判断三种证据状态被隔离生产、分级升级、受控交叉，最后由发布闸门限制结论的自信程度。

---

## 1. 本次审查的判断标准

本次不是问“文档写得顺不顺”，而是问五个更底层的问题：

1. 它是否符合金融市场的基本定价逻辑？
2. 它是否能减少 AI 被叙事带偏的风险？
3. 它是否保护 vNext 已经建立的 L1-L5 上下文隔离？
4. 它是否能让普通读者读懂，同时让专业读者审计？
5. 它是否能落成工程规则，而不是只停留在好听的方法论？

本次使用的项目边界：

- `ARCHITECTURE.md`：vNext 核心目标是可审计、可展开、可交互阅读的 NDX 投研推理链。
- `RESEARCH_CANON.md`：指标必须先定义对象、口径和发言权；代理指标不能冒充事实，技术指标不能替代估值判断。
- `NEXT_STEPS.md`：三层研报架构已经列为 P1 攻坚项。
- `RUN_REVIEW_CHECKLIST.md`：新闻只能作为辅助 sidecar，不能进入 L1-L5 evidence_ref；历史回测必须尊重 effective_date。
- 当前代码：已有 `news_event_ledger.json`、`news_layer_analysis.json`、`news_event_data_links.json` 的雏形，也已有 `event_refs` 进入 Bridge / Thesis 的路径。

---

## 2. 第一性原理：NDX 研报到底在研究什么

### 2.1 指数价格不是新闻分数，也不是指标分数

从金融学最底层看，NDX 的价格可以粗略理解为市场对以下因素的综合定价：

- 未来现金流：成分公司未来盈利、现金流、利润率和再投资回报。
- 折现率：名义利率、真实利率、政策利率路径。
- 风险溢价：投资者为不确定性要求的补偿。
- 流动性与融资条件：资金是否愿意承担风险。
- 持仓结构：指数集中度、广度、龙头权重、被动资金和拥挤度。
- 交易情绪与叙事：短期价格会受预期、故事和资金反馈影响。

所以 NDX 研究不能只问“今天有什么新闻”，也不能只问“指标是多少”。它真正要问的是：

> 当前价格隐含了什么预期？这些预期有没有被现金流、折现率、风险溢价、结构和价格行为共同支持？什么证据会推翻它？

三篇文档最合理的地方，就是它们没有把新闻直接塞进结论，而是要求先拆成数据层、事件层和综合层。

### 2.2 数据更硬，但数据不是本质本身

三篇文档说“数据也是现象”，这个判断是正确的。

原因很简单：

- VIX 是期权保险价格，不是恐慌本身。
- PE 是价格和盈利的比值，不是便宜或昂贵的完整答案。
- 信用利差是融资风险溢价，不是衰退事实本身。
- NDX/NDXE 比率是集中度和扩散的观察窗，不是龙头基本面的直接证明。
- 技术指标是价格行为结果，不是估值依据。

这与 `RESEARCH_CANON.md` 的指标发言权是一致的：指标必须知道自己能证明什么，也必须知道自己不能证明什么。

因此，第一层纯数据研报不应该被叫作“真理层”。更准确的说法是：

> 第一层是可审计市场现象层。它的价值不是全知，而是干净、可追溯、能约束叙事。

### 2.3 新闻不天然低级，但新闻必须先降权

三篇文档反对“新闻只是主观叙事”，这个判断也正确。

有些新闻其实是现实条件变化：

- FOMC 决议会改变政策约束。
- SEC 文件会改变公司披露事实。
- Nasdaq / Invesco 文件会改变指数或产品口径。
- 公司 earnings / guidance 会改变盈利路径。
- 监管政策可能改变风险溢价。

但新闻的危险在于，它经常把三件事混在一起：

- 事实：发生了什么。
- 解释：别人如何理解它。
- 交易叙事：市场愿意怎样讲这个故事。

所以第二层不能只是“新闻摘要”。它应该是：

> 事件事实、来源强度、市场叙事和待验证假设的账本。

这也解释了为什么原文要求来源分级、事件日期、发布日期、影响链路和限制条件。这个方向是合理的。

### 2.4 综合层的价值是裁决，不是润色

金融市场里最常见的错误不是“没有材料”，而是“材料太多以后强行讲成一个故事”。

综合层如果只是把数据报告和新闻摘要合并成一篇顺滑长文，它会退化成事后解释器。真正有价值的综合层要回答：

- 数据和新闻是否指向同一个机制？
- 哪些只是时间相近，不能当因果？
- 新闻打开的是抽象可能性，还是已经有数据支持的现实性？
- 哪个矛盾现在最支配 NDX？
- 哪一面暂时占上风？
- 反证是什么？
- 什么条件出现后必须改判断？

所以三篇文档把综合报告定位成“交叉质询”“矛盾裁决层”，在金融研究上是合理的。

---

## 3. 三篇文档最强的合理性

### 3.1 它抓住了 vNext 的核心矛盾

当前 vNext 的核心矛盾是：

> 数据链必须干净，但真实市场又不只由正式数据驱动。

只保留纯数据，系统更干净，但可能解释慢、解释窄。

放开新闻解释，系统更敏感，但容易被故事污染。

三层架构的合理性在于，它没有简单选择一边，而是把矛盾拆开：

- 第一层负责干净。
- 第二层负责外部世界。
- 第三层负责受控综合。

这比“禁止新闻”或“让新闻进入 L1-L5”都更稳健。

### 3.2 它符合 Context-first, role-second

`ARCHITECTURE.md` 明确说，agent 拆分首先是为了隔离上下文，不是为了模拟投研团队角色。

三层文档延续了这个原则：

- L1-L5 不看新闻。
- 新闻层不冒充 evidence_ref。
- 综合层读取前两者，但不能反向污染前两者。

这与现有架构一致。

需要注意的是：文档里“像投行研究部流水线”的比喻是有用的，但不能让工程实现滑回“角色扮演”。后续实现时，仍应以输入输出边界为准，而不是以“谁像什么岗位”为准。

### 3.3 它把新闻影响映射回金融链路

原文要求每条新闻说明可能影响的金融链路，例如：

- earnings_path
- valuation_multiple
- discount_rate
- risk_premium
- liquidity_condition
- credit_condition
- index_structure
- market_breadth
- technical_flow

这是非常关键的修正。

因为新闻本身不直接等于投资结论。新闻必须先说明它可能打到哪个金融机制，再由数据和后续价格确认。

正确例子：

> 某条 AI 订单新闻可能影响龙头 earnings_path，但是否足以支持 NDX 估值扩张，还要看盈利预期、估值、真实利率、集中度和广度。

错误例子：

> AI 新闻很强，所以高估值合理。

三层文档明确禁止后一种跳跃，这是合理的。

### 3.4 它保护了反证和未知

三篇文档反复强调：

- 反证必须保留。
- 冲突不能抹平。
- not_explained 不能删除。
- 强结论要有失效条件。

这正好对应 vNext 的核心目标：可追问、可审计、可反驳。

从金融研究角度看，这一点尤其重要。市场里很多错误不是因为不知道正方证据，而是因为忽略了反方证据。

---

## 4. 对抗式审查：这套想法最容易失败在哪里

下面不是否定三层架构，而是用最苛刻的方式找它的破口。

### 问题 1：当前代码中的第一层可能已经不够“纯”

三层文档说第一层纯数据研报包括 L1-L5、Bridge / Risk / Final 等数据侧结论。

但当前代码里：

- `AnalysisPacket.event_refs` 会保存事件底账。
- `_run_bridge` 会把 `packet.event_refs` 传给 Bridge。
- `SynthesisPacket.event_index` 会继续把事件索引传给 Thesis。
- Prompt 约束说 event_refs 只能当背景或催化剂，不能替代 evidence_refs。

这比“新闻进入 L1-L5”安全很多，但严格讲，Bridge / Thesis 已经可能看到事件材料。

如果未来第一层被定义为“现有 vNext 主链完整输出”，而主链里 Bridge / Thesis 能看到 `event_refs`，那么第一层就不是纯数据研报，而是“数据主链 + 事件旁证”。

风险：

- 模型可能先被事件暗示，再组织数据侧冲突。
- Prompt 虽然禁止把 event_refs 当 evidence_ref，但不能完全防止叙事锚定。
- 读者会误以为第一层已经是完全数据独立。

修复要求：

> 第一层纯数据研报必须有一个 data-only 运行模式：L1-L5、Bridge、Thesis、Risk、Final 全程不接收 event_refs、news sidecar、browser sidecar 或新闻摘要。

### 问题 2：“新闻”这个词太宽，容易混淆事实、披露和报道

原文已经做了来源分级，但还不够细。

同样叫新闻，性质差异很大：

- Fed 决议是官方政策事实。
- SEC 10-Q 是公司披露事实。
- Bloomberg 报道可能包含事实、匿名源和记者解释。
- 卖方策略报告是观点。
- 社媒热词是叙事扩散。

如果都放在“新闻层”，普通读者可能仍然把它们当成同类材料。

修复要求：

> 第二层不应命名为单纯新闻层，而应命名为事件与叙事层。每条材料要拆成 claim，而不是只拆成 article。

每个 claim 至少要区分：

- fact_claim：可核验事实。
- disclosure_claim：公司披露事实。
- data_release_claim：官方数据发布。
- interpretation_claim：报道或分析中的解释。
- view_claim：机构或专家观点。
- narrative_claim：市场叙事。
- rumor_claim：未确认线索。

### 问题 3：综合层有变成“万能解释器”的风险

三篇文档希望综合层找主要矛盾、现象与本质、偶然与必然。这是深刻的。

但危险在于：如果没有硬字段约束，模型可能用辩证法语言包装不确定性。

坏写法：

> 要辩证看待 AI 叙事与估值压力，二者既对立又统一，当前市场处于复杂演化阶段。

这句话看似深刻，其实没有回答：

- 判断对象是什么？
- 哪些数据支持？
- 哪些事件支持？
- 哪些证据反驳？
- 哪个条件会让判断失效？

修复要求：

> 辩证法只能作为研究约束，不能作为输出修辞。综合层每个重要判断都必须结构化。

必要字段：

- judgment_object
- claim
- explanation_grade
- data_support
- event_support
- price_reflection
- counterevidence
- unresolved_tension
- falsifiers
- watchlist

### 问题 4：解释等级还需要硬降级规则

原文定义了：

- confirmed_fact
- data_supported_read
- news_supported_read
- integrated_explanation
- plausible_hypothesis
- weak_signal
- not_explained

方向正确，但还缺少“什么时候必须降级”的硬规则。

建议补充：

| 触发条件 | 必须降级为 |
| --- | --- |
| 只有单条媒体报道，无官方或公司原始来源 | `weak_signal` 或 `plausible_hypothesis` |
| 新闻有来源但没有数据或价格确认 | `news_supported_read`，不得成为强投资结论 |
| 数据与新闻冲突且未解释 | `not_explained` 或 `plausible_hypothesis` |
| 数据层 DataIntegrity blocked | 综合报告不得发布为正式结论 |
| 反证强于支持证据 | 降低置信度，并把反证置顶 |
| 事件发布日期晚于 effective_date | 回测中不得使用 |
| 用单个公司事件推整个 NDX | 降级，除非权重和指数贡献被明确量化 |

### 问题 5：NDX 对象边界需要更硬

三篇文档提到了 NDX、QQQ、NDXE、M7、半导体等对象，但后续实现必须更硬。

原因：

- NDX 是指数。
- QQQ 是 ETF，可交易但有基金结构。
- NDXE 是等权指数，用于观察扩散。
- M7 是权重龙头集合，不等于整个 NDX。
- 半导体是产业链，不等于 NDX。

如果综合报告说“AI 利好 NDX”，必须回答：

- 利好的是哪些成分？
- 它们占 NDX 权重多少？
- 是盈利路径利好，还是估值叙事利好？
- 是否扩散到等权和广度？
- 有没有被真实利率或风险溢价抵消？

修复要求：

> 综合层每个判断第一字段必须是判断对象。对象不清，强结论自动降级。

### 问题 6：市场价格既是结果，也是信息，文档还可以更明确

方法论文档已经提到价格会反过来制造新闻、改变预期和资金行为，这是正确的。

但工程结构里还需要明确：

- 价格不是事实终点。
- 价格可能已经提前反映新闻。
- 新闻解释价格时，必须问“价格是否早已反映”。
- 市场上涨不证明新闻解释正确。
- 市场下跌也不证明新闻是原因。

修复要求：

综合层必须加入 `price_reflection` 字段：

- not_reflected
- partially_reflected
- largely_reflected
- over_reflected
- unclear

并且要说明依据来自哪里。

### 问题 7：大 Agent 的开放调查需要合规边界

原文把大 Agent 定位为外勤调查员，这个方向对。但开放调查最容易失控。

风险：

- 找到材料后过度相信搜索结果。
- 为了证明已有结论而选择性检索。
- 把登录态页面或浏览器材料误当正式证据。
- 在回测中拿当前网页解释过去。
- 把多个二手报道当成多个独立来源。

修复要求：

大 Agent 输出必须是候选证据包，不是结论。候选证据包至少包含：

- search_path：怎么找的。
- source_url / source_name。
- source_type。
- published_at。
- event_date。
- original_source_available：是否追到原始来源。
- extracted_claims。
- counter_sources。
- limitations。
- upgrade_recommendation：是否建议升级为正式源。
- status：research_candidate / manual_review_required / rejected / formal_source_candidate。

### 问题 8：发布闸门需要区分“不能发布结论”和“可以发布失败说明”

原文说纯数据研报 blocked / unpublishable 时，综合总报告不能发布为正式结论。正确。

但产品上还需要允许一种输出：

> 当前不能发布正式投资结论，因为数据闸门未通过；下面只给出失败原因、缺失证据、可读材料和下一步观察。

否则用户可能只看到系统沉默，不知道为什么不能发。

修复要求：

综合报告发布状态分成：

- publishable_integrated_report
- publishable_with_caveats
- draft_only
- audit_only
- blocked

`blocked` 时不能有正式主判断，但可以有审计说明。

---

## 5. 修复后的三层架构定义

### 5.1 第一层：纯数据研报

定位：

> 只基于正式数据源和 vNext artifacts 的数据侧推理链。

输入允许：

- 正式数据源。
- 已升级为正式数据链的人工/Wind/工具数据。
- L0 ObjectCanon。
- IndicatorCanon。
- 本层运行时数据。
- data-only Bridge / Thesis 所需的 L1-L5 artifacts。

输入禁止：

- news_event_ledger。
- news_layer_analysis。
- browser sidecar。
- 登录态工具材料。
- 大 Agent 候选证据包。
- 综合总报告当前判断。
- 其他层运行时输入在 L1-L5 阶段跨层传播。

输出：

- pure_data_report.json / md / html。
- layer_cards。
- data-only bridge_memos。
- data-only thesis / risk / final。
- DataIntegrity。
- Prompt Inspector。
- Run Review。

关键修复：

> data-only Bridge / Thesis 不接收 event_refs。事件材料只能进入第二层和第三层。

### 5.2 第二层：事件与叙事账本

定位：

> 记录外部世界发生了什么、谁说了什么、市场正在讲什么，以及这些材料可能影响哪条金融链路。

它不是 L1-L5 的证据源，而是综合层的候选解释材料。

最小结构：

```json
{
  "event_id": "event:...",
  "claims": [
    {
      "claim_id": "claim:...",
      "claim_type": "official_fact | disclosure_claim | data_release_claim | interpretation_claim | view_claim | narrative_claim | rumor_claim",
      "source_type": "official_fact | company_disclosure | reliable_mainstream_report | sell_side_or_expert_view | market_narrative | unverified_signal",
      "source_name": "",
      "source_url": "",
      "published_at": "",
      "event_date": "",
      "information_available_at": "",
      "related_index_object": "NDX | QQQ | NDXE | M7 | sector | company",
      "affected_financial_links": [],
      "fact_summary": "",
      "interpretation_summary": "",
      "what_it_can_support": "",
      "what_it_cannot_support": "",
      "needs_data_confirmation": true,
      "counterevidence_or_limits": [],
      "status": "event_fact | research_candidate | manual_review_required | rejected"
    }
  ]
}
```

重要原则：

- 先拆 claim，再做摘要。
- 官方事实也不自动等于 NDX 结论。
- 主流报道不是原始来源，除非它引用并可追到原始文件。
- 卖方观点和市场叙事只能作为观点或情绪材料。
- 未确认信号默认不得进入强结论。

### 5.3 第三层：综合矛盾裁决报告

定位：

> 读取纯数据研报和事件账本，在不污染前两层的前提下，判断它们如何互相确认、削弱、冲突或暂时无法解释。

最小结构：

```json
{
  "integrated_judgments": [
    {
      "judgment_object": "NDX",
      "claim": "",
      "explanation_grade": "integrated_explanation",
      "confidence": "low | medium | high",
      "data_support": [],
      "event_support": [],
      "price_reflection": "partially_reflected",
      "counterevidence": [],
      "unresolved_tension": [],
      "falsifiers": [],
      "watchlist": [],
      "publishability_note": ""
    }
  ],
  "conflict_matrix": [],
  "unexplained_items": [],
  "downgraded_claims": [],
  "publish_gate": {}
}
```

强结论的最低要求：

- 判断对象清楚。
- 至少有正式数据支持，或数据与事件共同支持。
- 新闻支持不能单独变成强投资结论。
- 反证和失效条件必须可观察。
- 未解释冲突必须保留。
- DataIntegrity blocked 时不能发布正式综合结论。

---

## 6. 对原三篇文档的具体修订建议

### 6.1 对 `三层架构暂定结构.md`

保留：

- “固定团队 + 专项分析师 + 大 Agent + 审计部门”的通俗比喻。
- “体检数据不能被传闻污染，外勤调查不能冒充化验结果”的核心表达。

建议补充：

- 明确第一层的 Bridge / Thesis / Final 必须有 data-only 模式。
- 把“大 Agent 候选证据包”写成候选状态，不得直接进入结论。
- 把“代码闸门”细化为来源、日期、因果越权、对象口径、发布状态五类检查。

### 6.2 对 `THREE_LAYER_REPORT_ARCHITECTURE_PLAIN.md`

保留：

- 三层是证据治理，不是排版分类。
- 来源标签和解释等级。
- 发布闸门。
- 三份报告独立入口、独立落盘。

建议修订：

- 把“新闻/事件简报”升级为“事件与叙事账本”。
- 把 `news_supported_read` 的能力边界写得更硬：不得单独形成强投资结论。
- 加入 data-only 第一层运行要求：第一层不得接收 `event_refs`。
- 加入 claim 粒度：一篇文章可以拆出多个 claim，不同 claim 的来源强度和可证明范围不同。
- 加入 blocked 时的 audit-only 输出规则。

### 6.3 对 `三层研报的辩证法方法论`

保留：

- 数据和新闻都是市场现象。
- 内因与外因。
- 量变与质变。
- 偶然与必然。
- 可能性与现实性。
- 主要矛盾和矛盾主要方面。
- 禁止误用辩证法。

建议修订：

- 明确辩证法字段必须工程化，不允许变成修辞。
- 每个“主要矛盾”判断必须绑定证据、反证、失效条件。
- 加入价格反映字段，防止用新闻事后解释已经提前定价的变化。
- 加入“对象边界优先”：NDX / QQQ / NDXE / M7 / 个股不能互相偷换。

---

## 7. 后续工程接入建议

### 阶段 1：先把第一层变成真正 data-only

目标：

- 现有 vNext 纯数据研报独立生成。
- L1-L5、Bridge、Thesis、Risk、Final 均不接收 event_refs。
- Prompt Inspector 能检查 data-only 运行中没有新闻字段。

验收：

- `analysis_packet.json` 中 data-only 模式没有 event_refs，或 event_refs 为空且不进入 prompt。
- Bridge prompt 不包含新闻/事件材料。
- Thesis prompt 不包含 event_index。
- 生成的 pure_data_report 能独立发布。

### 阶段 2：把第二层从摘要升级为账本

目标：

- 当前 `news_event_ledger` 和 `news_layer_analysis` 升级为 claim-based 账本。
- 每条 claim 有来源等级、发布时间、事件时间、信息可见时间、金融链路、限制和待验证数据。

验收：

- 一条新闻可以拆多个 claim。
- claim_type 和 source_type 分开。
- 每个 claim 明确 what_it_can_support / what_it_cannot_support。
- 回测模式过滤晚于 effective_date 的 claim。

### 阶段 3：新增 integrated_synthesis_report

目标：

- 第三层只读取 pure_data_report 和 event_narrative_ledger。
- 输出 integrated_judgments、conflict_matrix、unexplained_items、downgraded_claims 和 publish_gate。

验收：

- 每个重要判断都有判断对象、数据支持、事件支持、反证、失效条件。
- 新闻单独支持的判断不会被写成强投资结论。
- not_explained 明确保留。
- DataIntegrity blocked 时输出 audit-only 或 blocked，不输出正式主判断。

---

## 8. 修复后的最终判断

三篇文档的核心想法是合理的，而且方向上优于两种极端方案：

- 极端一：只看数据，导致系统对真实世界事件反应迟钝。
- 极端二：把新闻塞进主链，导致 L1-L5 被叙事污染。

但它们需要进一步收紧三件事：

1. 第一层必须是真正 data-only，不能让 event_refs 进入数据侧 Bridge / Thesis。
2. 第二层不能只是新闻摘要，而要变成事件、来源、claim、金融链路和限制条件的账本。
3. 第三层不能只是综合长文，而要变成带解释等级、降级规则、反证、失效条件和发布闸门的矛盾裁决层。

修复后的架构可以概括为：

> 数据层负责干净地说“正式数据正在显示什么”；事件层负责诚实地说“外部世界发生了什么、市场在讲什么、这些材料最多能支持什么”；综合层负责谨慎地说“两者在哪些条件下互相确认、冲突或暂时无法解释”。

这样，三层架构才真正符合 vNext 的核心原则：

> 可追问、可审计、可展开阅读；重要结论必须有判断对象、支持证据、反驳证据和失效条件。

