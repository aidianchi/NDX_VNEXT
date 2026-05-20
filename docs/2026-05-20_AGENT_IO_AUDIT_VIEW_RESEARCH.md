# Agent 输入/输出审计视图研究文档

日期：2026-05-20  
状态：产品方向研究 / 后续实现依据  
适用对象：后续 Codex、Claude 或其他 AI agent 继续实现 `Agent 输入/输出审计视图` 前，应先读本文，再读 `ARCHITECTURE.md`、`NEXT_STEPS.md`、`PLAIN_LANGUAGE_AGENT_PIPELINE_REVIEW.md`。

---

## 0. 一句话结论

Agent 输入/输出审计视图的第一目标，不是自动判断每个 agent 是否聪明，而是让人能看见：

> 每个 agent 到底看到了什么，产出了什么，哪些产出真的进入了下游推理，哪些只是漂亮但无用的标签。

这件事应该优先于复杂自动审计脚本。因为现在最需要证明的，不是系统能不能给字段打分，而是这条多 agent 流水线到底有没有真实发生“分工推理”。

如果第一版做对，它会像一张透明的投研流水账：人能顺着一条结论往回追，看到它来自哪个 agent、哪些证据、哪些反证、在哪一步被保留、在哪一步被丢弃。

---

## 1. 为什么要做这个视图

### 1.1 多 agent 系统最大的风险不是 agent 少，而是看不见

`ndx_vnext` 的目标不是让一个大模型直接写一份市场报告，而是生成一条可审计、可展开、可交互阅读的 NDX 投研推理链。这个目标很正确，但它也带来一个新问题：

> 链条越长，越容易让人误以为“步骤多”就等于“推理深”。

如果没有审计视图，系统可能出现几种表面很高级、实际很危险的情况：

- L1-L5 看似分工，实际被提前喂了其他层的运行时结论。
- 某个 layer 分析了很多指标，最后只传下去一个 `fear`、`expensive`、`risk_on` 之类的低价值标签。
- Bridge 看似在做跨层冲突，实际只是把 L1-L5 的标题重新排列。
- Thesis 看似综合，实际把高价值反证和未解决张力压扁成一句“中性偏谨慎”。
- Final 看似裁决，实际只是内部审批话术，不能帮助读者理解市场。

这些问题靠“再加一个自动检查脚本”不一定能解决。因为在我们还没看清系统真实运行形态之前，自动脚本很容易只检查表面字段是否存在，而不是检查字段是否真的有认知价值。

### 1.2 审计视图是认识论工具，不只是 UI 功能

这个视图的价值不只是“页面更好看”。它本质上是在回答一个认识论问题：

> 我们怎么知道这套 agent 流水线真的在生产知识，而不是在传递符号？

对投研系统来说，“知识”不是漂亮形容词，而是能经受追问的东西：

1. 它判断的对象是什么。
2. 它依据了哪些证据。
3. 它知道这些证据能证明什么、不能证明什么。
4. 它保留了哪些反证和冲突。
5. 它告诉我们什么情况会改变判断。
6. 它在下游确实改变了某个结论、风险边界或行动含义。

审计视图要把这些东西摊开。它不是替人思考，而是帮助人看见系统有没有真的思考。

### 1.3 为什么不先做复杂自动审计

自动审计当然有价值，但它应该是第二步。

第一步应该先让人看见真实链路，原因有三点：

1. **先看事实，再写规则。** 只有看过多次真实 run，才知道哪些字段经常有价值，哪些字段经常是噪音。
2. **避免把错误标准自动化。** 如果一开始就写复杂评分，很容易奖励“字段齐全”，而不是奖励“推理有效”。
3. **降低实现负担。** 只读视图不改主链路、不影响发布、不引入新决策权，风险小，收益快。

白话说：

> 先把厨房装上透明窗，再决定哪些动作需要装报警器。

---

## 2. 这个视图最终应该带来的效果

第一版完成后，用户打开一个 run，不应该只看到最终报告，而应该能回答五个问题。

### 2.1 每个 agent 收到了什么

用户应该能看到：

- L1 收到了哪些 L1 数据和 L1 context brief。
- L2 收到了哪些信用、波动、情绪材料。
- L3 收到了哪些广度、集中度、结构材料。
- L4 收到了哪些估值、盈利、风险补偿材料。
- L5 收到了哪些趋势、量价、技术状态材料。
- Bridge 收到了哪些 L1-L5 artifact。
- Thesis 收到了哪个压缩后的 synthesis packet。
- Critic / Risk / Reviser / Final 分别收到了哪些上游产物。

更重要的是，用户应该能看到 agent **没有收到什么**。

例如 L3 卡片里应该明确显示：

- 未收到 L1 runtime highlights。
- 未收到 L2 输出。
- 未收到 L4/L5 当前判断。
- 未收到 Bridge memo。
- 未收到 Thesis 或 Final 结论。

这比一句“我们保证上下文隔离”更有说服力。

### 2.2 每个 agent 输出了什么

用户不需要默认看到完整 JSON。第一版应该先抽取核心输出：

- 主要判断。
- 支持证据。
- 反证或冲突。
- 不确定性。
- 失效条件。
- evidence refs。
- 字段质量提示。

完整 JSON 可以折叠查看，但不应该成为默认阅读方式。审计视图不是让人翻机器内脏，而是让人快速看清“这一步有没有干活”。

### 2.3 下游到底用了什么

系统要能展示一个字段的去向：

- 被哪个下游 agent 使用。
- 用在什么下游字段。
- 是直接引用、合并使用、反驳使用，还是完全未使用。
- 如果被 Final 丢弃，是在哪一步丢的。

这会直接暴露两类问题：

- 上游 agent 产出很多，但下游根本不用，说明上游在制造噪音。
- 下游结论很强，但追不到上游字段，说明下游可能在自由发挥。

### 2.4 L1-L5 context isolation 是否成立

第一版必须让隔离变成可见事实，而不是架构口号。

对于每个 L1-L5 agent，审计视图都应该展示三栏：

```text
允许输入
实际输入
禁止输入检查
```

允许输入包括：

- ObjectCanon。
- 本层 IndicatorCanon。
- 本层 runtime context。
- 静态五层职责说明。

实际输入包括：

- artifact 路径。
- 输入包 trace id 或 hash。
- 本层 evidence refs。
- 本层 context brief 名称。

禁止输入检查包括：

- 其他层 runtime context：未出现。
- 其他层输出 artifact：未出现。
- Bridge 当前判断：未出现。
- Thesis / Final 当前判断：未出现。
- 全局跨层 highlights：未进入 L1-L5。

如果这里做清楚，后续复盘时就能用一句白话判断：

> L4 知道自己负责估值，但不知道 L5 这次怎么看趋势；它没有被趋势结论提前带节奏。

### 2.5 垃圾标签会更早暴露

如果某个字段只有“风险偏高”“动能改善”“结构分化”，但没有 evidence refs、没有机制、没有反证、没有下游使用，它应该在审计视图里显得很单薄。

这不是为了羞辱模型，而是为了保护系统。垃圾字段最危险的地方，不是它看起来空，而是它看起来像结论。

---

## 3. 第一版最小产品形态

### 3.1 页面定位

第一版建议叫：

```text
Agent Trace / Agent 输入输出审计
```

它可以是 native brief 里的一个审计层，也可以是独立 HTML 页面。实现上选更简单的一种。关键是第一版只读，不参与主链路决策。

它的用户不是普通报告读者，而是：

- 系统设计者。
- 后续 AI 维护者。
- 做 run 复盘的人。
- 想判断流水线是否真的分工推理的人。

### 3.2 页面结构

推荐结构：

```text
顶部：Run 总览
左侧：Pipeline 节点列表
中间：当前 agent 输入 / 输出
右侧：字段下游消费去向
底部或折叠区：原始 JSON / trace 细节
```

顶部总览展示：

- `run_id`
- `effective_date`
- 实时 / 回测 / 快照模式
- DataIntegrity 状态
- publish status
- artifact 根目录
- 是否启用新闻 sidecar
- strict backtest invariant 摘要

左侧 pipeline 展示：

```text
Data / Audit
Context Build
L1
L2
L3
L4
L5
Bridge
Synthesis
Thesis
Critic
Risk
Schema Guard
Reviser
Final
Brief
```

中间区域展示当前节点：

- 收到什么。
- 没收到什么。
- 输出了什么。
- 哪些字段有 evidence refs。
- 哪些字段有反证。
- 哪些字段只有标签。

右侧区域展示字段去向：

- 下游直接使用。
- 下游合并使用。
- 下游反驳使用。
- 下游未使用。

### 3.3 第一版必须展示的信息

第一版不要贪多，但必须有这些。

#### A. Agent 输入清单

每个 agent 至少展示：

- agent 名称。
- stage 名称。
- 输入 artifact 列表。
- 输入 artifact 类型。
- 输入来源路径。
- 输入 evidence refs 数量。
- 输入数据日期边界。
- 对 L1-L5：是否只使用本层 context brief。
- 对 L1-L5：禁止输入检查结果。

#### B. Agent 输出摘要

每个 agent 至少展示：

- 核心结论。
- 关键字段列表。
- 每个关键字段是否绑定 evidence refs。
- 每个关键字段是否包含反证 / uncertainty / falsifier。
- 每个关键字段的下游消费状态。

#### C. Evidence refs

至少能看到：

- 字段引用了哪些 evidence refs。
- evidence refs 来自哪个 layer / metric / artifact。
- 是否存在空引用、泛引用或无法追溯引用。

第一版不用做复杂证据图谱，只要能追到来源即可。

#### D. 下游消费

字段消费状态建议分四类：

- `directly_used`：下游明确引用该字段或 evidence refs。
- `merged_used`：下游把它和其他字段合成 typed conflict、resonance 或 thesis。
- `used_as_counterevidence`：下游把它作为反证、风险边界或限制条件。
- `not_used`：存在于输出中，但后续没有被消费。

注意：`not_used` 不等于错误。它只是提示人类复盘：这个字段是否本来就不重要，还是系统漏用了。

#### E. 字段质量提示

第一版不要做复杂分数，先做简单标记：

- `has_evidence`
- `has_counterevidence`
- `has_falsifier`
- `used_downstream`
- `generic_label`
- `missing_evidence`
- `possible_permission_overreach`
- `not_used_downstream`

这些提示应该帮助人快速发现问题，而不是制造一个新的神秘评分。

---

## 4. 怎么判断字段有价值，还是垃圾标签

### 4.1 有价值字段的特征

一个字段有价值，不是因为它听起来专业，而是因为它能干活。

有价值字段通常满足：

1. 它回答了一个明确问题。
2. 它绑定了具体 evidence refs。
3. 它说明证据能证明什么。
4. 它说明证据不能证明什么。
5. 它保留了反证、不确定性或失效条件。
6. 它能被下游使用。
7. 它让后续判断变得更清楚，而不是更模糊。

例如：

```text
高真实利率继续压制估值修复，但 NDX PE 分位已经从极端高位回落，说明“贵”仍是压力，不等于“赔率一定差”。
```

这个字段有价值，因为它同时说明：

- 判断对象：真实利率与估值。
- 支持证据：利率、PE 分位。
- 限制：贵不等于必跌。
- 冲突：压力与赔率改善可能同时存在。
- 下游用途：Bridge 可形成 typed conflict，Thesis 可进入 pricing/payoff 判断。

### 4.2 垃圾标签字段的特征

垃圾标签不是指字段完全没内容，而是它不能支持严肃判断。

常见垃圾标签：

- `fear`
- `risk_on`
- `expensive`
- `momentum_positive`
- `neutral`
- `watch closely`
- `market stress elevated`
- `valuation pressure`
- `breadth divergence`

这些词本身不是禁用词。问题在于，如果它们单独出现，没有证据、机制、反证和下游用途，就只是漂亮标签。

垃圾字段通常有这些特征：

1. 换个日期也能说。
2. 换个市场也能说。
3. 没有 evidence refs。
4. 没有指标数值或来源。
5. 没有说明为什么重要。
6. 没有说明什么会推翻它。
7. 下游没有真正使用。
8. 使用了超出指标权限的推理。

例如：

```text
市场情绪偏恐慌，建议保持谨慎。
```

这句话可能是真的，但审计上价值很低。它没有回答：

- 哪个指标说明恐慌？
- VIX 是多少？
- 信用利差是否确认？
- 恐慌是风险，还是可能带来更厚赔率？
- 下游该怎么用？
- 什么情况会改变这个判断？

### 4.3 最小判断标准

第一版可以用一个朴素规则：

> 如果一个字段没有证据、没有机制、没有反证、没有下游用途，它就是疑似垃圾字段。

不用急着自动删除它。先让它在审计视图里显眼即可。

---

## 5. 怎么证明下游真的使用了上游输出

### 5.1 不要只看 agent 是否运行成功

agent 运行成功不等于推理链条成立。

真正要看的是：

- L1-L5 的哪些字段进入了 Bridge。
- Bridge 的哪些 typed conflicts / resonance chains / transmission paths 进入了 SynthesisPacket。
- SynthesisPacket 的哪些字段进入了 Thesis。
- Thesis 的哪些核心结论被 Critic 攻击。
- Risk Sentinel 保留了哪些风险边界。
- Reviser 有没有保留 Critic 和 Risk 的有效挑战。
- Final 有没有把关键冲突、失效条件和行动边界留给读者。

### 5.2 字段去向比字段存在更重要

审计视图应该允许人从一个字段一路追下去。

例如：

```text
L4.output.valuation_pressure
  -> Bridge.typed_conflicts[real_rate_vs_valuation]
  -> SynthesisPacket.core_tensions[0]
  -> Thesis.pricing_narrative
  -> RiskBoundary.must_preserve_risks
  -> Final.reader_conclusion
```

如果这条链成立，说明 L4 的字段真的影响了最终判断。

如果链条是：

```text
L4.output.valuation_pressure
  -> not_used
```

那就要问：这是合理丢弃，还是系统浪费了一个上游信号？

### 5.3 使用类型要区分

字段被使用不只有一种方式。

第一版至少区分：

- **直接使用**：下游直接引用字段、短语或 evidence refs。
- **合并使用**：下游把它和其他字段组合成更高层关系。
- **反驳使用**：下游用它限制另一个结论。
- **未使用**：没有任何下游痕迹。

这比简单的“used=true/false”更接近真实推理。

---

## 6. 怎么展示 L1-L5 没有看到其他层运行时信息

### 6.1 核心原则

L1-L5 可以知道静态五层框架，但不能知道其他层本轮运行时状态。

白话说：

> 允许知道别人负责什么，禁止知道别人这次看到了什么、判断了什么。

审计视图要把这件事变成可检查事实。

### 6.2 L1-L5 输入边界卡

每个 L1-L5 agent 都应该有一张输入边界卡。

卡片结构：

```text
Agent: L3 Breadth / Concentration

Allowed:
- ObjectCanon
- L3 IndicatorCanon
- L3 runtime context
- static layer responsibility map

Actually received:
- layer_context_briefs/L3.json
- L3 raw metrics
- L3 indicator canon
- object canon

Forbidden and absent:
- layer_context_briefs/L1.json
- layer_context_briefs/L2.json
- layer_context_briefs/L4.json
- layer_context_briefs/L5.json
- layer_cards/L1-L5.json
- bridge_memos/*.json
- thesis_draft.json
- final_adjudication.json
- global apparent_cross_layer_signals
```

这张卡要服务一个非常实际的判断：

> 如果 L3 输出了“广度弱但估值修复可能提供支撑”，它是不是偷看了 L4？如果没有收到 L4 输入，那这种说法就应该被标记为越权或泛化，而不是当作可靠跨层判断。

### 6.3 隔离证明不是靠模型自述

不要让 agent 自己说“我没有看到其他层”。模型自述没有审计价值。

要靠 context assembly 的实际输入证明：

- 输入 artifact 列表。
- 输入包 trace id / hash。
- prompt payload 片段。
- 禁止 artifact 缺席检查。

只要输入包里没有其他层 runtime artifact，隔离就有事实基础。

---

## 7. 怎么避免审计视图自己变成负担

### 7.1 第一版坚持只读

第一版不要让审计视图参与任何发布决策。

它不应该：

- 阻断发布。
- 自动改写 agent 输出。
- 替 Final 下结论。
- 给市场判断打最终分。

它只负责让人看见。

### 7.2 默认摘要，按需展开

不要默认展示完整 prompt 和完整 JSON。那会让页面变成数据垃圾场。

默认层级应该是：

1. 人类可读摘要。
2. 核心字段。
3. evidence refs。
4. 下游消费。
5. 折叠的原始 JSON。

如果用户要查细节，再展开。

### 7.3 少做图，多做追踪

第一版不需要炫酷大图谱。

更有价值的是：

- 清楚的 agent 卡片。
- 清楚的输入边界。
- 清楚的字段去向。
- 清楚的质量标记。

图可以有，但不要让图变成主产品。很多复杂图谱最后只是把混乱画得更漂亮。

### 7.4 不引入新术语体系

审计视图应该使用已有概念：

- agent
- artifact
- evidence refs
- context brief
- layer card
- bridge memo
- synthesis packet
- thesis
- risk boundary
- final adjudication

不要为了审计视图新增一套复杂术语。术语越多，后续 AI 越容易把产品做成“解释审计视图的审计视图”。

### 7.5 不追求一步到位

第一版只要解决三个痛点就够了：

1. L1-L5 输入隔离是否可见。
2. 输出字段是否有证据和反证。
3. 下游是否真正消费了这些字段。

其他都可以后置。

---

## 8. 成功标准

第一版完成后，应该能用 5 分钟回答这些问题：

1. 这次 run 的 DataIntegrity 和 publish status 是什么？
2. L1-L5 分别收到了哪些输入？
3. L1-L5 是否看到了其他层运行时信息？
4. 每个 layer 最重要的 3-5 个输出字段是什么？
5. 这些字段有没有 evidence refs？
6. 这些字段有没有反证、冲突或失效条件？
7. Bridge 是否真的消费了 L1-L5 输出？
8. Bridge 产出的 typed conflicts / resonance / transmission 是否进入 Thesis？
9. Thesis 的核心判断有没有被 Critic / Risk 检查？
10. Final 保留了哪些冲突，丢弃了哪些冲突？
11. 哪些字段是未被消费的噪音？
12. 哪些字段看起来像越权推理？

如果这些问题答得上来，第一版就成功。

如果页面很漂亮，但这些问题答不上来，第一版就失败。

---

## 9. 预期收益

### 9.1 对系统设计者

它能帮助判断多 agent 架构是否真的有效。

不是看 agent 名字是否合理，而是看：

- 分层输入是否干净。
- 输出是否有信息量。
- 跨层关系是否真的由 Bridge 处理。
- 下游是否保留高价值冲突。
- 最终报告是否继承了上游证据，而不是重新编故事。

### 9.2 对后续 AI 维护者

它能降低后续 AI 误改架构的概率。

后续 AI 常见风险是：

- 为了方便，把全局 context brief 喂给 L1-L5。
- 为了 UI 简洁，只展示最终 stance。
- 为了自动化，过早写一堆表面规则。
- 为了报告顺滑，把冲突压平。

审计视图会让这些问题更容易被发现。

### 9.3 对真实 run 复盘

它能让复盘从“读最终报告”变成“检查推理链”。

例如 2025-04-09 这种样本，复盘不应只问：

> 最终 stance 对不对？

还要问：

- L4 是否看到了估值压缩和赔率改善？
- L5 是否看到了趋势风险与承接信号并存？
- Bridge 是否把风险未解除和赔率改善放在同一个冲突里？
- Thesis 是否把“风险高”误写成“赔率差”？
- Final 是否把确认成本讲清楚？

审计视图能让这些问题更快落到 artifact 层，而不是停留在感受层。

### 9.4 对自动审计脚本

它会为第二阶段自动化提供真实样本。

等人类通过审计视图看过足够多 run，就能知道哪些检查值得自动化，例如：

- L1-L5 禁止 artifact 检查。
- evidence refs 缺失检查。
- 下游未消费字段比例。
- 泛标签字段占比。
- typed conflict 是否缺少双方 evidence refs。
- Final 是否丢失 must-preserve risks。

这样写出来的自动脚本才不容易变成形式主义。

---

## 10. 第一版不要做什么

为了防止范围膨胀，第一版明确不做这些：

- 不做自动市场结论评分。
- 不做复杂语义相似度裁判。
- 不做全量 prompt diff 浏览器。
- 不做炫技式知识图谱。
- 不把审计视图变成新的发布闸门。
- 不自动重写 agent 输出。
- 不把所有 JSON 默认展开。
- 不试图一次覆盖所有历史 run。
- 不新增会污染 L1-L5 的运行时输入。

第一版要小而锋利。它只解决“看清楚”。

---

## 11. 后续实现建议

### 11.1 数据来源

优先直接消费现有 vNext artifacts：

- `analysis_packet.json`
- `context_brief.json`
- `layer_context_briefs/Lx.json`
- `layer_cards/L1-L5.json`
- `bridge_memos/*.json`
- `synthesis_packet.json`
- `thesis_draft.json`
- `critique.json`
- `risk_boundary_report.json`
- `schema_guard_report.json`
- `analysis_revised.json`
- `final_adjudication.json`
- `run_summary.json`
- `data_integrity_report.json`

不要为了审计视图重跑 agent。审计视图应该是 artifact viewer，不是新的推理阶段。

### 11.2 实现优先级

建议顺序：

1. 先做 run 总览。
2. 再做 L1-L5 输入边界卡。
3. 再做每个 agent 输出摘要。
4. 再做 evidence refs 追踪。
5. 再做字段下游消费状态。
6. 最后再加质量提示。

不要一开始就做复杂 UI。

### 11.3 和 native brief 的关系

`brief` 是给读者看的连续报告。Agent 审计视图是给复盘者看的透明链路。

两者可以在同一个 HTML 里，但信息架构要分清：

- brief 回答“这次市场怎么看”。
- audit trace 回答“系统是怎么得出这个看法的”。

审计视图不应该抢 brief 的首屏，也不应该把读者报告变成工程日志。

### 11.4 和 workbench 的关系

workbench 是看盘式探索页面，重点是图表、时间序列和指标对比。

Agent 审计视图重点是：

- 输入边界。
- 输出字段。
- evidence refs。
- 下游消费。

不要把两者混成一个页面。它们可以互相链接，但不要互相替代。

---

## 12. 给后续 AI 的工作指令

如果你是后续接手实现的 AI，请遵守这些原则：

1. **先读本文，再读 `ARCHITECTURE.md` 和 `PLAIN_LANGUAGE_AGENT_PIPELINE_REVIEW.md`。**
   不要凭空设计审计视图。

2. **保持只读。**
   第一版不改变主推理链，不改变 agent 输出，不改变发布状态。

3. **先证明输入边界，再美化页面。**
   L1-L5 context isolation 是最高价值展示。

4. **字段去向比字段数量重要。**
   不要做一个只罗列 JSON 的页面。要让人知道字段有没有被下游使用。

5. **不要制造新黑箱评分。**
   第一版用简单质量标记，不做复杂分数。

6. **保留冲突，不要让审计视图帮系统粉饰太平。**
   如果上游有冲突、下游丢了冲突，页面应该让人看出来。

7. **不要把新闻、浏览器、登录态工具或 sidecar 结果抬升为 L1-L5 evidence refs。**
   审计视图可以展示它们作为 sidecar 的存在，但不能改变它们的数据权限。

8. **回测模式必须尊重 effective date。**
   审计视图展示数据日期时，不得用当前网页或当前成分股基本面伪装成历史当时可见事实。

9. **实现完成后，用一个真实 run 验证。**
   至少检查 `2025-04-09` 或最新合适 run：L1-L5 输入边界、字段 evidence refs、Bridge 消费、Final 保留/丢弃。

10. **如果需要新增自动检查，先把它作为提示，不要直接变成发布闸门。**
    自动化应来自审计视图暴露出的稳定问题，而不是先验想象。

---

## 13. 最终判断

Agent 输入/输出审计视图值得做，而且应该作为 vNext 下一阶段的核心产品能力之一。

它的意义不在于多一个页面，而在于给整套系统装上一层“可见性”。没有这层可见性，多 agent 架构很容易退化成一串漂亮名词；有了这层可见性，我们才能判断：

- 哪些 agent 真在生产认知。
- 哪些字段只是标签。
- 哪些冲突被保留。
- 哪些证据被误用。
- 哪些结论真的来自上游。
- 哪些地方需要自动审计。

第一版只要做到一件事：

> 让人顺着一个最终判断，能一路追回血肉，而不是只追到一堆空标签。

这就是它的产品价值，也是它的研究价值。
