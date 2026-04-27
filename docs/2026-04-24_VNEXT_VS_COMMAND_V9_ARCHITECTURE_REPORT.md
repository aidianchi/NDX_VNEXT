# vNext vs Command V9 架构与分析质量报告

日期：2026-04-24

对比对象：

- 老版主指令：`C:\ndx_agent\src\NDX_COMMAND_V9.txt`
- 老版少样本范例：`C:\ndx_agent\src\prompt_examples.py`
- 老版运行器：`C:\ndx_agent\src\core\analyzer.py`
- vNext 合约：`C:\ndx_vnext\src\agent_analysis\contracts.py`
- vNext prompt：`C:\ndx_vnext\src\agent_analysis\prompts\*.md`
- vNext 最新产物：`C:\ndx_vnext\output\analysis\vnext\20260424_204741`

## 1. 核心结论

用户的判断基本成立，但需要分成两层说。

第一层，vNext 的架构方向是正确的。它把老版 `NDX_COMMAND_V9.txt` 中单个 Analyst / Critic / Reviser 的长链条拆成了更接近真实投资团队的分工：L1-L5 专家、Cross-Layer Bridge、Thesis Builder、Critic、Risk Sentinel、Schema Guard、Reviser、Final Adjudicator。这种结构确实更像现实中的顶级投资研究流程：不同领域专家先给出各自判断，然后由组合经理或策略负责人做跨领域整合，再由风险和批评角色进行压力测试。

第二层，当前 vNext 实现并没有完全兑现这个架构优势。它目前更强的是“组织结构”和“治理流程”，而不是“每个专业 analyst 的深度研究质量”。尤其在 L1-L5 层，当前产物是 `LayerCard`，主要包含 `core_facts`、`local_conclusion`、`risk_flags`、`cross_layer_hooks` 和 `notes`。它不是老版 Command V9 那种对每一个指标输出完整 `narrative + reasoning_process` 的研究初稿。

因此，当前状态应定义为：

> vNext 在组织架构上领先老版，但在每个 layer analyst 的原生研究职责、指标级叙事、4C few-shot 注入和初稿完整性上，确实存在明显退化风险。

这不是小问题。它会影响 Bridge、Thesis 和 Critic 的上游材料质量。Bridge 再聪明，也只能拆解它看到的东西；如果 Layer Analyst 只给摘要，Bridge 就会基于摘要做冲突识别，而不是基于每个指标的完整推理做更深层的金融辨析。

## 2. vNext 的真实优势是什么

vNext 相比老版的优势不是“模型更聪明”，而是“认知流程被拆开并落盘”。

老版 `NDX_COMMAND_V9.txt` 的内部结构是三阶段：

- Analyst Draft：生成完整 `__LOGIC__`
- Critic：审查初稿
- Reviser：基于批评意见修订终稿

这套设计已经很强，但所有 Analyst 工作在一个超长 prompt 中完成。它的问题是：

- 五层指标分析、层内综合、跨层综合都在一个大上下文内发生。
- 模型可能为了形成完整故事而提前抹平冲突。
- 跨层冲突主要依靠同一个 Analyst/Strategist 在同一轮里自行发现。
- 如果某一层材料很复杂，容易被其他层上下文稀释。

vNext 解决的是这些问题：

- L1-L5 分开运行，减少单个 agent 的上下文污染。
- 每一层先只负责本层，不直接越权给最终投资判断。
- Bridge Agent 明确负责层与层之间的支撑、冲突和共振。
- Thesis Builder 只整合已有 LayerCard 和 BridgeMemo，不重新发明事实。
- Critic、Risk Sentinel、Schema Guard 和 Final Adjudicator 让治理角色独立化。
- 每个中间产物都落盘，便于审计。

这确实更接近现实投资团队。一个顶级纳斯达克100研究团队通常不会让一个人同时深挖宏观流动性、信用情绪、指数广度、基本面估值、技术趋势，再自己质疑自己、自己批准自己。更现实的流程是：

- 宏观/流动性研究员判断利率、通胀、流动性和政策约束。
- 信用/情绪研究员判断波动率、信用利差、风险偏好和拥挤度。
- 市场结构研究员判断广度、集中度、领导力和内部脆弱性。
- 基本面/估值研究员判断 PE、ERP、盈利预期和安全边际。
- 技术/交易研究员判断趋势、动量、波动、入场和止损条件。
- 策略负责人或组合经理整合这些观点，明确主线和冲突。
- 风险负责人或投资委员会成员提出反方意见和失效条件。

所以，vNext 的“多 agent 分工”不是形式主义。它有真实金融研究上的合理性。（批注：那么，有更合理、更顶级的多agent分工吗？帮我深刻的研究）

## 3. 老版 Command V9 的关键优势

老版有一个目前 vNext 没完全保住的核心优势：Analyst 初稿本身就很完整。

在 `NDX_COMMAND_V9.txt` 中，第一阶段明确要求针对每一个指标执行“数据-逻辑-叙事”三步法：

- 数据：陈述 Level、Momentum、Relativity。
- 逻辑：解释这些数据在金融学上的内在含义。
- 叙事：融合为 `narrative`。
- 同时生成 `reasoning_process`，用自然语言解释从原始数据到结论的完整推理过程。

该文件还明确要求：

- `metric` 必须精确使用 `data_json.indicators[].metric_name`。
- 每个指标都要生成对象。
- `reasoning_process` 要体现因果清晰、专业深度、避免重复。
- 输出必须进入 `indicator_narratives.layer_1` 到 `layer_5`。

更重要的是，老版运行器 `C:\ndx_agent\src\core\analyzer.py` 在 Analyst 调用前会动态注入少样本范例：

- 根据 `data_json.indicators[].function_id` 匹配 `PROMPT_EXAMPLES`。
- 对每个出现的指标注入 4C 认知范例。
- 如果存在 reasoning 范例，也注入该指标的推理过程范例。
- 还显式注入 `masters_perspective` 范例。

这意味着老版不是只靠 `NDX_COMMAND_V9.txt` 的抽象要求，而是在运行时把“具体指标应该如何解释”的范例放进上下文。它的优势是：

- 指标级分析天然完整。
- 指标名称与报告生成器天然对齐。
- 每个指标的叙事风格被 few-shot 约束。
- Critic 审查的是完整推理链，而不是摘要。
- Reviser 修订的是完整 `__LOGIC__`，不是事后补文案。

这正是老版报告看起来更“像研究报告”的原因。（批注：老版本有别的更多的优势吗？深刻探讨）

## 4. 当前 vNext 的主要缺口

### 4.1 Layer Analyst 的输出合约过薄

当前 `LayerCard` 合约定义在 `C:\ndx_vnext\src\agent_analysis\contracts.py`。

它的核心字段是：

- `core_facts`
- `local_conclusion`
- `confidence`
- `risk_flags`
- `cross_layer_hooks`
- `notes`

`CoreFact` 只包含：

- `metric`
- `value`
- `historical_percentile`
- `trend`
- `magnitude`
- `raw_data`

这套结构适合做“事实卡片”，不适合直接承载“专业 analyst 的完整研究笔记”。它没有以下字段：（批注：这不就是把api弄来的原始数据似是而非的加工了一下吗，实际上没有任何价值吧？）

- `indicator_narratives`
- `reasoning_process`
- `evidence_refs`
- `causal_chain`
- `indicator_level_caveats`
- `report_ready_narrative`

真实产物也验证了这一点。最新 `L1.json` 的 keys 是：

- `layer`
- `generated_at`
- `core_facts`
- `local_conclusion`
- `confidence`
- `risk_flags`
- `cross_layer_hooks`
- `notes`

其中没有 `indicator_narratives`，也没有 `reasoning_process`。

因此，现在的 L1-L5 agent 更像“把指标整理成事实卡 + 层级摘要”，还不是“流动性专家/估值专家/趋势专家逐指标写深度研究”。

### 4.2 vNext 的 layer prompt 没有要求每指标输出完整叙事

查看 `l1_analyst.md` 到 `l5_analyst.md`，它们的输出格式都是 `LayerCard`。这些 prompt 会要求识别核心事实、局部结论、风险标记和跨层 hooks，但没有要求像老版那样对每个指标输出：

- `metric`
- `narrative`
- `reasoning_process`

例如 `l1_analyst.md` 的输出示例只要求 `core_facts`，其中每个 fact 是结构化数值事实，而不是自然语言研究段落。

这会带来一个直接后果：

> vNext 的 layer agent 目前没有被合约强制成为“完整研究报告作者”，而只是“结构化事实提取 + 本层摘要作者”。

### 4.3 当前报告中的推理文本主要来自兼容层再生成

最新报告中，`logic_vnext.json` 已经恢复了 34 个指标叙事和 34 个推理过程块。但这次恢复来自 `legacy_adapter.py`。

代码证据：

- `legacy_adapter.py` 的 `_build_indicator_narrative()` 会把指标值、LayerCard 的 `local_conclusion`、Thesis、Bridge 的 claim/conflict 拼成 `narrative`。
- `_build_reasoning_process()` 会把指标值、层级结论、notes、hook、Bridge conflict 和 risk text 拼成 `reasoning_process`。
- 在主循环里，它遍历 `data_json.indicators`，为每个指标生成 legacy `indicator_narratives`。

这次修复解决了报告展示问题，但没有解决更深的认知来源问题。

准确说：

- 报告现在有指标级推理了。
- 但这些推理不是 L1-L5 analyst 原生写出的。
- 它们是兼容层基于已有产物和规则拼装出来的。

这比没有强很多，但还不能等同于“每个专业 agent 都做了逐指标深度研究”。 （批注：这导致根本没有发挥出来vnext架构威力吧？最终分析的大任不都到了兼容层头上？那不就又变成“职责不单一”了？甚至只有l1-l5 分析师的似是而非的没有结论只有黑箱化判读的垃圾污染？？？）

### 4.4 prompt_examples.py 在 vNext 中只被校验，没有被有效注入

vNext 的 `llm_engine.py` 在导入时会执行 `validate_prompt_examples(PROMPT_EXAMPLES)`。这能保证范例文件结构没有坏。

但目前没有看到 vNext 像老版 `analyzer.py` 那样，在每个 layer 调用前根据该层 `function_id` 动态注入对应的 4C 范例。

换句话说：

- 老版：运行时检测指标，动态注入该指标的 4C 范例和 reasoning 范例。
- vNext：启动时校验范例存在，但 layer prompt 调用时没有把对应范例放进 prompt。

这正是用户指出的“既然分工到 L1-L5，上下文更干净，就更应该注入对应顶级金融范例”的问题。

这个判断成立。vNext 当前没有充分利用这个架构优势。

### 4.5 Bridge 的输入材料不够深

当前 Bridge Agent 读取的是 LayerCards，核心材料是：

- `core_facts`
- `local_conclusion`
- `risk_flags`
- `cross_layer_hooks`

这可以支持基本冲突识别，例如：

- L4 高估值 vs L1 高实际利率
- L3 集中度极端 vs L5 趋势强劲
- L2 情绪乐观 vs L1 宏观限制性

但如果 Layer Analyst 没有逐指标展开推理，Bridge 就缺少很多可拆解的“中间逻辑”。它看到的是压缩后的结论，而不是原始研究员如何从 VIX、HY OAS、XLY/XLP、Crowdedness、Fear & Greed 一步步推导出风险偏好的完整链条。

这会限制 Bridge 的深度。现实中的投资委员会不会只看每个研究员的一句话摘要；它会追问每个判断背后的证据和假设。vNext 当前的 Bridge 也应该看到这些材料。

## 5. 是否“架构领先，但 agent 质量和职责严重不足”

结论是：有这个风险，而且当前实现已经露出症状。

但要精确表述：

> vNext 的顶层架构不是错的；问题在于 layer analyst 的职责定义和输出合约还没有升级到与该架构匹配的专业研究深度。

目前 vNext 像一个组织架构已经搭好的投资团队，但每个行业/宏观/估值专家只交了一页 summary card。Bridge、Thesis 和 Risk 角色都存在，但它们没有拿到足够厚的上游研究底稿。

老版则相反：组织分工较粗，但 Analyst 初稿非常厚，指标级推理完整，few-shot 注入强。这使得老版在“第一稿研究密度”上仍然占优。

因此不能说 vNext 已经全面优于老版。更准确的判断是：

- vNext 优于老版：分工、审计、治理、跨层显式化、产物落盘。
- 老版优于 vNext：指标级初稿完整度、4C 注入、每个指标的原生叙事质量、报告所需材料天然生成。
- 当前 vNext 报告修复：恢复了展示层信息量，但很多文本仍是 adapter 合成，不是 layer agent 原生研究。

## 6. 应该如何修 vNext

### P0：扩展 LayerCard 合约

建议新增 `IndicatorAnalysis` 合约，例如：

```json
{
  "metric": "10Y Real Rate",
  "function_id": "get_10y_real_rate",
  "level_summary": "当前10Y实际利率为1.92%。",
  "momentum_summary": "位于短期均线下方，边际压力略有缓和。",
  "relativity_summary": "处于10年85%分位。",
  "narrative": "完整的指标级叙事。",
  "reasoning_process": "自然语言推理过程。",
  "causal_chain": ["实际利率高位", "贴现率上升", "成长股估值承压"],
  "evidence_refs": ["L1.get_10y_real_rate.level", "L1.get_10y_real_rate.relativity.percentile_10y"],
  "confidence": "medium",
  "caveats": ["短期回落不等于政策宽松"]
}
```

然后 `LayerCard` 应包含：

- `indicator_analyses`
- `core_facts`
- `local_conclusion`
- `internal_conflict_analysis`
- `risk_flags`
- `cross_layer_hooks`

这样，Layer Analyst 才真正拥有“逐指标研究员”的职责。（批注：而且每个研究员都要做到顶级水平，根据每个layer的特点进行各自的深度分析？）

### P1：把 4C few-shot 注入迁移到每个 layer agent

vNext 应复用老版 `analyzer.py` 的动态范例注入逻辑，但按 layer 做隔离。

例如：

- L1 agent 只注入 L1 指标范例：10Y-2Y、Fed Funds、Real Rate、Net Liquidity、M2、Copper/Gold。
- L2 agent 只注入 L2 指标范例：VIX、VXN、HY OAS、XLY/XLP、Crowdedness、Fear & Greed。
- L3 agent 只注入广度和集中度范例。
- L4 agent 只注入估值、ERP、盈利预期范例。
- L5 agent 只注入趋势、ADX、RSI、MACD、OBV、Donchian 范例。

这会比老版更干净，因为老版一次性给 Analyst 注入所有出现指标的范例；vNext 可以做到“每个专家只看自己领域的典范”，减少风格和概念污染。（批注：同意）

### P2：让 Bridge 消费完整 `indicator_analyses`

Bridge 不应只看 `local_conclusion`。它应该看到每层中每个指标的：

- narrative
- reasoning_process
- causal_chain
- caveats
- evidence_refs

这样它才能做真正的深拆：

- 哪些指标在同层内互相矛盾。
- 哪些指标跨层共振。
- 哪些推理依赖同一个脆弱前提。
- 哪些结论是“数据强、推理弱”。
- 哪些结论是“数据缺失但叙事过度”。

### P3：Schema Guard 增加质量门槛

当前 Schema Guard 主要看结构是否完整、冲突是否保留。下一步应加入报告质量约束：

- 每个输入指标必须有一个 `IndicatorAnalysis`，除非显式标记缺失或排除原因。
- `metric` 必须等于 `data_json.indicators[].metric_name`。
- 每个 `IndicatorAnalysis` 必须包含 `narrative` 和 `reasoning_process`。
- `reasoning_process` 不得只是复述 narrative。
- 每个跨层结论必须引用至少两个 `evidence_refs`。
- Bridge 的每个 conflict 必须指向具体指标级分析，而不是只指向 layer summary。

### P4：让 legacy_adapter 回归“薄转换器”

修复后的 `legacy_adapter.py` 当前承担了太多写作职责。长期看，它应该只做格式转换：

- 从 `LayerCard.indicator_analyses` 复制 `narrative` 和 `reasoning_process`。
- 从 `LayerCard.internal_conflict_analysis` 复制层内冲突。
- 从 `BridgeMemo` 和 `ThesisDraft` 复制跨层结论。

它不应该继续作为主要推理文本生成者。兼容层可以兜底，但不能成为认知主力。

## 7. 推荐的新 vNext 分工

一个更合理的 vNext 应该是：

1. Context Loader：整理数据完整性、缺失项、日期、宏观背景，只做上下文，不做结论。
2. L1-L5 Specialist Analysts：每个专家逐指标写 `IndicatorAnalysis`，再给出本层综合结论。
3. Layer Internal Critic：可选，每层内部先自查本层指标是否互相矛盾。
4. Cross-Layer Bridge：基于完整指标级分析，识别跨层支撑、冲突、共振和失效条件。
5. Thesis Builder：只整合，不重新发明证据。
6. Critic：审查从指标到层级、从层级到 regime 的逻辑链。
7. Risk Sentinel：给出失效条件和风险边界。
8. Schema Guard：检查结构、覆盖率、引用和输出质量。
9. Reviser：修订，但保留冲突。
10. Final Adjudicator：独立放行或驳回。

这才真正对应现实投资团队：

- 专家先做深度研究。
- 策略负责人再做综合。
- 风控和反方角色做压力测试。
- 最终裁决者不允许抹平冲突。

## 8. 最终判断

用户提出的担忧成立。

vNext 的核心优势确实是把 Command V9 的三 agent 长链条拆成多 agent 分工，从而获得更清晰的职责边界、更强的审计能力和更显式的跨层逻辑。这一点方向正确，也更接近现实顶级投资团队。

但当前 vNext 的实现有一个关键短板：Layer Analyst 没有像真正的专业研究员一样，对每个指标输出深刻、完整、4C 约束下的原生研究文本。它现在输出的是结构化事实卡和层级摘要。最新报告补回的指标级叙事和推理过程，主要是 `legacy_adapter.py` 事后合成，而不是 L1-L5 agent 的原生思考。

所以当前最准确的诊断是：

> vNext 已经搭好了更正确的投资团队组织结构，但还没有把老版 Command V9 的“指标级深度研究能力”迁移进每个专家 agent。下一阶段的重点不是再增加 agent 数量，而是提高每个 Layer Analyst 的职责厚度、输出合约和 few-shot 专业范例注入。

如果不修这个问题，vNext 会出现一种危险状态：架构看起来更现代，报告看起来也能补齐，但真正的原始研究深度反而不如老版。

下一步应进入：

> Layer Analyst Fidelity Repair：把每个 L1-L5 agent 从“事实卡片生成器”升级为“指标级专业研究员”。（批注：这一步是必须必须做的，但还要看我的批注，进行回答和分析，然后再决定下一步做什么。我完全同意你的这些看法。我认为这个升级必须是彻底的，由于现在的每一个agent都可能是垃圾，所以必要时完全重写！）
