# Deep Research 法典集成计划

> **给后续代码 agent 的要求：** 真正开始实现代码前，必须使用 `superpowers:test-driven-development`；在声称完成前，必须使用 `superpowers:verification-before-completion`。本文同时写给人和 agent，因此会尽量避免金融黑话和工程黑话。

**目标：** 把 `deep-research-report.md` 升级为 vNext 系统的共同研究法典，用来指导指标判读、市场状态诊断、跨层级推理和少文本提示范例。

**总体架构：** 在 agent 推理之前，增加一层静态的“研究法典”。L1-L5 仍然只接收本层运行时数据，但可以接收静态规则：每个指标是什么意思、它能证明什么、不能证明什么、需要哪些指标交叉验证、哪些证据会推翻它的判断。Bridge 和治理阶段再用同一套规则检查冲突、越权推理和弱逻辑。

**技术栈：** Python、Pydantic 合约、Markdown prompt、现有 vNext artifacts、pytest。

---

## 1. 给非专业读者的简明解释

`deep-research-report.md` 应该成为系统的 **研究规则书**。

现在 vNext 已经会要求每个层级 agent 写更深的指标分析，这是对的。但还不够。agent 还需要一套共同标准，知道：

- 每个指标能证明什么；
- 每个指标不能证明什么；
- 哪些其他指标必须确认它；
- 出现什么证据时，必须撤回当前判断；
- 一个信号到底是真正的市场状态线索，还是只是噪音。

新的核心规则很简单：

> vNext 不只是让 agent “分析指标”，还要让 agent 明白每个指标的发言权。

举几个例子：

- RSI 可以帮助判断交易节奏，但不能证明市场便宜。
- VIX 可以说明保险费很贵，但 VIX 高本身不是买入信号。
- 净流动性很有用，但它只是代理指标，不是官方真理。
- 高估值不一定看空，但“高估值 + 高实际利率 + 信用恶化”是严重冲突。
- 价格趋势向上很重要，但如果市场广度很弱，系统必须保留这个张力。

这就是本轮升级的核心。

## 2. 为什么这会改变路线图

旧计划把 UI 和 Bridge v2 放得比较靠前。

在深入研究 `deep-research-report.md` 之前，这个顺序是合理的。但读完之后，需要重排。

这份报告不是“更多范例”。它是一套更高级的推理标准。如果在这套标准接入系统之前，就先做 Bridge v2 或 UI 美化，我们可能只是把一个训练不足的系统包装得更漂亮。

新的顺序应该是：

```text
Deep Research 研究法典
  -> L0 投资对象定义
  -> 让 L1-L5 输出带有法典意识
  -> Bridge v2 typed conflict / resonance / transmission map
  -> 治理阶段客观性防火墙
  -> 最新 full smoke 验证
  -> 原生 UI 迭代
```

## 3. 关键概念

### Deep Research 研究法典

“法典”就是规则书。

在本项目里，它指的是从 `deep-research-report.md` 中提取出来的一组结构化规则。它告诉每个 agent：应该如何有纪律地解释指标。

### L0 投资对象定义

分析市场之前，vNext 必须先定义“我们到底在分析什么”。

对本项目来说，通常涉及：

- NDX：Nasdaq-100 指数。
- QQQ：用于交易 Nasdaq-100 暴露的 ETF。
- NDXE：Nasdaq-100 等权指数。
- QEW 或历史 QQEW：等权 Nasdaq-100 暴露的 ETF 代理。

这很重要，因为 QQQ 不是“所有科技股”。它是一个规则化、改良市值加权、高集中度的 Nasdaq-100 交易载体。如果投资对象理解错了，后面所有指标都可能被误读。

### 指标发言权

每个指标都有自己的发言范围。

例如：

- 实际利率指标对估值压力有强发言权。
- 信用利差对风险偏好和融资压力有强发言权。
- 情绪指标只有弱发言权，除非信用和广度确认它。
- 技术指标主要负责交易时机，不负责证明估值是否合理。
- 结构指标主要负责判断集中度和广度，不负责短线买卖点。

### 客观性防火墙

客观性防火墙是在系统给出强结论前必须通过的一组问题。

它问：

1. 我们正在判断的市场对象到底是什么？
2. 当前引用的每个指标分别有什么发言权？
3. 数据频率和发布日期是否匹配？
4. 至少有两个不同层级互相验证了吗？
5. 哪个可观察证据会推翻当前结论？

如果 agent 答不清这些问题，就不应该使用“大买”“大卖”“黄金坑”“顶部”这类强标签。

## 4. 需要新增什么

### 4.1 ObjectCanon：投资对象法典

`ObjectCanon` 用来在 L1-L5 开始分析前，说明当前投资对象。

它应该回答：

- 当前判断对象是什么：NDX、QQQ、QEW、NDXE、美股大盘、成长风格，还是某个交易组合？
- 指数和可交易 ETF 有什么区别？
- 当前对象有哪些集中度风险？
- 最近哪些指数方法学变化重要？
- 哪些比较是有效的，哪些比较会误导？

这是静态上下文。它可以给 L1-L5 使用，不会破坏运行时隔离。

### 4.2 IndicatorCanon：指标法典

`IndicatorCanon` 应该按 `function_id` 索引。

每个指标条目应包含：

- `function_id`
- `metric_name`
- `layer`
- `permission_type`：事实型、代理型、合成型、技术型、结构型
- `source_hint`：数据来源提示
- `frequency_hint`：数据频率提示
- `canonical_question`：这个指标真正回答的问题
- `interpretation_rules`：如何读水平、变化、相对关系和结构
- `misread_guards`：常见误读提醒
- `cross_validation_targets`：需要哪些其他指标确认或挑战
- `falsifiers`：哪些可观察条件会削弱或推翻当前解读
- `core_vs_tactical_boundary`：这个指标主要影响长期框架、短期执行，还是两者都有
- `b_prompt`：高密度少文本提示卡

### 4.3 RegimeScenarioCanon：市场状态情景法典

`RegimeScenarioCanon` 用来保存报告里的市场状态模板。

有价值的情景包括：

- 软着陆扩张；
- 金发姑娘；
- 真实利率上行导致估值承压；
- 流动性修复；
- 狭窄龙头牛市；
- 广度扩散的健康牛市；
- 非信用危机型恐慌；
- 信用压力市；
- 衰退式降息；
- 熊陡和债市波动冲击；
- 假突破风险；
- 真右侧修复；
- 黄金坑候选。

每个情景应包含：

- 指标组合；
- 主因果逻辑；
- 主假设；
- 反证条件；
- 风控触发器；
- 必须保留的证据或冲突。

注意：情景只是模板，不是自动结论。agent 不能看到一个条件相似就机械套用。

### 4.4 ObjectiveFirewallSummary：客观性防火墙摘要

在 Thesis 或 Final 给出强结论前，应生成这个摘要。

它应该总结：

- 对象是否清晰；
- 指标发言权是否正确；
- 数据时间是否对齐；
- 是否有跨层验证；
- 最强反证是什么；
- 还有哪些未解决张力。

## 5. 每个 agent 应该如何变化

### L1-L5 Layer Analysts

L1-L5 仍然必须保持上下文隔离。

它们可以接收：

- 本层运行时数据；
- 本层相关的 `IndicatorCanon`；
- 静态的 `ObjectCanon`。

它们不能接收：

- 其他层的当前数据；
- 其他层的当前结论；
- 基于当前运行时数据生成的 Bridge 候选结论。

每条 `IndicatorAnalysis` 都应该带有法典意识。用白话说，每条指标分析都应该说明：

- 这个指标被允许告诉我们什么；
- 当前数据具体说明了什么；
- 需要哪些其他证据确认；
- 什么情况会证明这次解读错了；
- 这个信号属于长期框架、短期执行，还是只是风险提醒。

### Bridge

Bridge 不应只是写一段跨层 memo。

Bridge 应该成为跨层逻辑的结构化建模者，明确区分：

- 冲突；
- 共振；
- 传导路径；
- 未解决问题；
- 数据缺口；
- 反证条件。

Bridge 尤其要保留这些冲突：

- 高实际利率 vs 高估值；
- 价格趋势强 vs 市场广度弱；
- 流动性改善 vs 信用恶化；
- VIX 回落 vs 集中度风险上升；
- 降息来自经济压力，而不是健康宽松；
- 龙头股强势 vs 指数整体广度脆弱。

### Thesis Builder

Thesis 不应该重新发明事实。

它应该在阅读以下材料后，判断当前最像哪种市场状态：

- layer summaries；
- evidence index；
- typed Bridge map；
- objective firewall summary。

它的核心任务是说明：

- 当前更像哪种 regime；
- 为什么这个判断只是有条件成立；
- 什么会推翻它；
- 哪些冲突必须继续保留。

### Critic

Critic 应该成为主要的“越权推理检查员”。

它要攻击：

- 用情绪指标推翻信用指标；
- 用技术指标推翻估值或结构风险；
- 把代理指标当成官方真理；
- 没有信用和广度确认就声称“黄金坑”；
- 广度不确认时声称“健康突破”；
- 把降息机械理解成利好；
- 忽略数据频率或发布日期错配。

### Risk Sentinel

Risk 应该更具体，少一点夸张。

除非输入里本来就有历史统计数字，否则 Risk 不应该编造“历史概率”。

它应该聚焦可观察触发器：

- HY OAS 走阔；
- IG OAS 走阔；
- A/D 走弱；
- New Lows 扩大；
- VXN 比 VIX 更快上升；
- MOVE 或 ATR 扩张；
- 200 日均线失守；
- 实现波动追上隐含波动；
- QQQ/QEW 或 NDX/NDXE 显示集中度压力。

### Reviser

Reviser 不应该把故事写顺。

它应该把过度自信的结论改成条件式结论：

> 当前更像 X，但如果 Y 和 Z 出现，就必须撤回这个判断。

这才是 vNext 应该有的语气。

### Final Adjudicator

Final 应该有权拒绝一份分析，如果：

- 投资对象定义缺失；
- 指标发言权被违反；
- 高严重度冲突被隐藏；
- 反证条件很空泛；
- 风险触发器不可观察；
- 最终立场强于证据。

## 6. 新优先级

### P0：保留现有安全门

已经完成：

- L1-L5 如果返回旧式薄 LayerCard，会在 Bridge 消费前被拒绝。

这个安全门不能削弱。

### P1A：构建 Deep Research 研究法典

先创建静态法典结构和提取路径。

交付物：

- `ObjectCanon`
- `IndicatorCanon`
- `RegimeScenarioCanon`
- 测试：证明可以按 layer 和 `function_id` 选择法典条目

### P1B：让 L1-L5 输出带有法典意识

给 `IndicatorAnalysis` 增加法典字段。

第一阶段只做 warning，不直接 hard fail。

原因：

> 先教会 agent，再用几轮 smoke 稳定输出，最后再收紧合约。

### P1C：修正对象定义，并提高 L3 数据优先级

L3 数据工作应该上调优先级。

这不只是“多补几个广度指标”。它关系到系统有没有读对投资对象：

- NDX vs QQQ；
- NDXE vs QEW；
- 历史 QQEW 只是旧代理；
- Top10 权重；
- 市场广度和集中度。

### P1D：Bridge v2

Bridge v2 应该在 layer 输出已经带有法典意识后再做。

否则我们只是把旧推理结构化，而不是把更好的推理结构化。

### P1E：治理阶段客观性防火墙

Thesis、Critic、Risk、Reviser 和 Final 应消费更窄、更干净的治理输入包：

- typed Bridge map；
- high-severity conflicts；
- objective firewall summary；
- must-preserve risks；
- evidence refs。

### P2：Smoke 和原生 UI

完成以上步骤后，再把 UI 放回高优先级。

UI 应该展示：

- L0 投资对象定义；
- 指标发言权标签；
- 反证条件；
- typed conflicts；
- 风险触发器；
- 原始 evidence refs。

### P3：Legacy Adapter 降责

等 native UI 稳定后：

- legacy adapter 只保留兼容导出；
- 它不能参与主推理文本生成。

## 7. 明确不要做什么

不要：

- 把整个 `deep-research-report.md` 硬塞进每个 prompt；
- 让 L1-L5 看到其他层运行时结论；
- 把报告中的仓位百分比复制成 agent 输出；
- 让情绪或技术指标压倒事实、信用或结构指标；
- 在客观性防火墙没通过时使用“黄金坑”“顶部”“大买”“大卖”；
- 让 Risk 编造历史概率；
- 在推理标准升级前优先做 UI 美化。

## 8. 第一轮实施任务

第一轮实现应该小而稳。

### Task 1：定义 Canon 合约

文件：

- 修改：`src/agent_analysis/contracts.py`
- 测试：`tests/test_deep_research_canon.py`

新增 Pydantic 模型：

- `ObjectCanon`
- `IndicatorCanon`
- `RegimeScenarioCanon`
- `ObjectiveFirewallSummary`

### Task 2：增加静态 Canon Builder

文件：

- 新建：`src/agent_analysis/deep_research_canon.py`
- 测试：`tests/test_deep_research_canon.py`

先做一组精选条目：

- L0 投资对象定义；
- DGS10；
- DFII10；
- T10YIE；
- FEDFUNDS；
- HY OAS；
- VIX / VXN；
- 净流动性；
- PE / Forward PE；
- ERP；
- A/D；
- QQQ/QEW 或 NDX/NDXE；
- 均线；
- ATR；
- ADX；
- RSI；
- MACD。

### Task 3：注入 Layer-Local Canon

文件：

- 修改：`src/agent_analysis/orchestrator.py`
- 修改：`src/agent_analysis/prompts/l1_analyst.md` 到 `l5_analyst.md`
- 测试：`tests/test_vnext_orchestrator.py`

只注入当前层当前 `function_id` 对应的 canon。

同时注入静态 `ObjectCanon`。

### Task 4：温和扩展 IndicatorAnalysis

文件：

- 修改：`src/agent_analysis/contracts.py`
- 修改：`src/agent_analysis/orchestrator.py`
- 测试：`tests/test_vnext_orchestrator.py`

新增可选字段：

- `permission_type`
- `canonical_question`
- `misread_guards`
- `cross_validation_targets`
- `falsifiers`
- `core_vs_tactical_boundary`

SchemaGuard 第一阶段只 warning，不 fail。

### Task 5：重新规划 Bridge v2，再开始编码

文件：

- 更新本根目录计划，或在根目录新建 Bridge v2 计划。

在 Tasks 1-4 验证之前，不要启动 Bridge v2。

## 9. 成功标准

当以下条件满足时，说明集成有效：

- 每个 layer 都能说明每个指标被允许证明什么；
- 代理指标被明确标为代理指标；
- 技术指标留在执行层，不越权解释估值或宏观；
- Bridge 能引用精确跨层冲突和反证条件；
- Thesis 以条件式方式判断 regime，而不是武断下结论；
- Critic 能抓出指标越权；
- Risk 给出可观察触发器，而不是编造统计数字；
- Final 能拒绝过度自信的分析；
- UI 能展示投资对象、指标发言权、反证条件和 evidence refs。

## 10. 一句话北极星

vNext 应该成为这样一个系统：每个市场结论都能回答：

> 我们判断的对象是什么，哪些证据有发言权，什么证据确认它，什么证据反驳它，以及出现什么情况我们会改变判断？

