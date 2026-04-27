# L1 Role-First vs Context-First Prompt Experiment

日期：2026-04-25

实验目的：回答一个关键架构问题：在 L1-L5 的上下文范围没有改变的情况下，把 prompt 从“专业角色定义”改成“context-first 认知变换定义”是否真的提升质量，还是可能削弱模型的金融分析能力与报告可读性。

## 1. 实验设计

固定变量：

- 数据：`output/data/data_collected_v9_live.json`
- 层级：只测试 L1 宏观流动性
- 模型：`deepseek-v4-flash`，`deepseek-v4-pro` 作为 fallback
- 输出结构：两组都强制输出同一套 v2 `LayerCard`，包括 `indicator_analyses`、`layer_synthesis`、`internal_conflict_analysis`、`quality_self_check`
- context 范围：完全相同，只给 L1 数据、L1 facts、context brief 和 manual overrides

唯一变化：

- `role_first`：开头强调“你是顶级机构投资团队中的 L1 宏观流动性分析师”
- `context_first`：开头强调“本节点不是角色扮演，而是在干净 L1 上下文中执行受约束认知变换”

实验产物：

- 严格 schema 实验目录：`output/experiments/l1_role_vs_context_strict_20260425_101727`
- 初始实验目录：`output/experiments/l1_role_vs_context_20260425_101316`

说明：初始 3+3 实验中，两组都把 `quality_self_check` 输出为字符串，导致 schema invalid。这说明实验版 common contract 对该字段结构约束不足，不能归因于 role/context framing。随后补强 schema 示例，进行 2+2 严格实验，四次全部 valid。

## 2. 严格实验结果

结构结果：

| Variant | Runs | Valid | Indicator Coverage | Required Hooks |
|---|---:|---:|---:|---:|
| role_first | 2 | 2/2 | 8/8 | L4 + L2 |
| context_first | 2 | 2/2 | 8/8 | L4 + L2 |

文本密度：

| Variant | Avg Narrative Chars | Avg Reasoning Chars | Layer Synthesis Chars | Internal Conflict Chars |
|---|---:|---:|---:|---:|
| role_first run 1 | 37.2 | 37.2 | 164 | 175 |
| role_first run 2 | 38.1 | 57.2 | 228 | 195 |
| context_first run 1 | 64.5 | 85.0 | 247 | 216 |
| context_first run 2 | 46.2 | 63.2 | 148 | 167 |

观察：

- `context_first` 平均文本更长，尤其第一轮更细。
- `role_first` 并没有更差，第一轮的层内综合反而非常强，抓住了“限制性但边际改善”的主线。
- 两组都能覆盖全部指标；决定 schema 稳定性的不是 role/context wording，而是输出结构示例是否足够明确。

## 3. 金融学质量评估

优秀 L1 分析应抓住五个主问题：

1. `actual tightness`: 政策利率、实际利率、名义长端利率仍在限制性区间。
2. `marginal easing`: 实际利率低于 MA、净流动性 4 周动量转正、M2 正增长，说明边际压力缓和。
3. `discount-rate channel`: 实际利率通过 DCF 折现率压制成长股远期现金流现值。
4. `liquidity quality`: 净流动性改善不能机械等同于大宽松，需要看 RRP、TGA、Fed assets 和持续性。
5. `inflation constraint`: breakeven inflation 高位上行可能限制降息空间和名义利率下行空间。

两组表现：

- `role_first run 1` 很好地识别了“限制性但边际改善”，并明确写出高实际利率、净流动性改善、通胀预期高位、铜金比低位的相互关系。它的 `internal_conflict_analysis` 质量高，适合 UI 单独展示。
- `role_first run 2` 也抓住了主线，但有一个小问题：把净流动性绝对水平称为“偏低”，而实际 10 年分位约 48%，更准确应是“中位附近，不宽松”。
- `context_first run 1` 是四个结果中综合质量最高的一个，原因不是“去角色化”，而是它更充分展开了每个指标的因果机制，尤其是实际利率、净流动性、breakeven、铜金比。
- `context_first run 2` 稳定性也不错，但文本更压缩，优势不如 run 1 明显。

因此不能得出“context-first prompt 一定优于 role-first prompt”的结论。更合理的结论是：

> 质量提升来自输出契约、指标级 few-shot、完整指标清单和推理链要求；不是来自否定角色扮演。

## 4. 对用户问题的回答

### 4.1 context 范围没变，改成 context-first 是否必要？

作为 prompt wording，不必要。

如果 L1 的输入 context 没有变化，只把“你是宏观分析师”改成“你不是角色扮演，而是上下文变换”，不会自动获得更干净的上下文。真正的 context-first 应落实在：

- 每个 agent 只获得必要输入；
- 输出结构强制保留证据链；
- Thesis 消费 `SynthesisPacket`，不重新吞原始细节；
- SchemaGuard 检查每个有效指标是否有原生分析；
- Adapter 不再替 L1-L5 脑补叙事。

这些是架构层的 context-first。prompt 里反复说“不是角色扮演”收益有限，甚至可能削弱专业分析风格。

### 4.2 是否会负面影响 AI 思考能力？

可能会，尤其对 L1-L5 这种需要专业语感和金融直觉的层。

“角色”对模型不是单纯 cosplay。它是一个有用的认知先验，会激活：

- 该领域的术语体系；
- 常见因果链；
- 风险优先级；
- 写作语气；
- 面向读者的报告感。

如果完全去角色化，模型可能更像数据转换器，结构更稳，但金融叙事的锋利度下降。未来 L1-L5 要单独在 UI 展示，这一点更重要。

### 4.3 role-first 和 context-first 谁更好？

实证结论：二者不是互斥关系，最佳方案是 hybrid。

建议写法：

1. 先定义 context boundary：本层只看 L1 数据，不越权做最终投资建议。
2. 再定义 professional lens：你是顶级 L1 宏观流动性分析专家。
3. 再定义 cognitive transform：L1 raw indicators -> indicator analyses -> layer synthesis -> bridge hooks。
4. 最后定义 UI-quality output：每个指标的 `narrative` 和 `reasoning_process` 必须可单独展示。

这比“不是角色扮演”更准确。

## 5. 下一步 prompt 修改原则

不应继续把 L1-L5 写成纯 context-transform 机器。应改成：

> Context-bounded professional analyst.

也就是：

- context-first 是架构原则；
- role-first 是 prompt 层的认知引擎；
- schema-first 是质量闸门；
- few-shot 是风格与推理校准；
- UI-first 是最终可读性标准。

下一步应重写 L1-L5 prompt，但方向不是删除角色，而是把角色从“人类组织模仿”改为“专业认知镜头”。

建议新标题模板：

```text
# L1 Context-Bounded Macro Liquidity Analyst

## Context Boundary
你只接收 L1 宏观流动性上下文，不读取 L2-L5 原始数据，不给最终买卖建议。

## Professional Lens
你是顶级宏观流动性分析专家，任务是判断利率、实际利率、期限结构、货币量、净流动性和增长预期如何共同约束 NDX。

## Cognitive Transform
L1 raw indicators -> indicator_analyses -> layer_synthesis -> internal_conflict_analysis -> cross_layer_hooks。
```

## 6. 结论

用户的质疑成立：如果 context 范围没有变，只在 prompt 中把“角色定义”替换成“context-first 定义”，并不是充分必要的改进。

本轮实验支持一个更精确的架构判断：

> vNext 不应反角色化，而应反“空洞角色化”。真正目标是：干净上下文 + 专业角色镜头 + 强结构合约 + 指标级 few-shot + 可 UI 展示的叙事。

因此，后续 L1-L5 prompt 重写应保留并强化“顶级金融专家”的语气和职责，只是把它限制在清晰的 context boundary 内。

## 7. 2026-04-25 补充：ContextBrief 泄露与隔离修复

复查运行时 prompt 后发现：此前 L1-L5 的 `layer_raw_data` 已经按层隔离，但 `context_brief` 仍是全局摘要。

`ContextBrief` 字段含义：

- `data_summary`: 数据日期、指标成功率等全局元信息。
- `layer_highlights`: L1-L5 各层的关键摘要。
- `apparent_cross_layer_signals`: Python 基于各层状态预生成的跨层线索。
- `task_description`: 当前节点任务说明。
- `special_attention`: 需要特别关注的事项。

问题在于，旧 L1 payload 的 `context_brief` 会包含：

- L2 当前情绪摘要，例如 CNN Fear & Greed、HY OAS、crowdedness。
- L3 当前结构摘要，例如 QQQ/QQEW、M7 fundamentals。
- L4 当前估值摘要，例如 ERP、PE/PB/PS。
- L5 当前技术摘要，例如 ADX、Donchian、ATR。
- 数据派生的跨层判断，例如“流动性收紧与高估值并存”。

这会让 L1 在形成自己的宏观判断前提前知道 L4 估值和 L5 趋势状态，削弱独立性。严格说，这不符合 context-first 的第一性原理。

已完成修复：

- `orchestrator.py` 新增 layer-local context brief。
- L1-L5 analyst 现在收到的 `context_brief` 只包含本层 highlights、全局数据元信息和通用隔离提醒。
- `apparent_cross_layer_signals` 对 L1-L5 清空。
- 全局 `context_brief` 仍保存，并继续供 Bridge / Thesis / Governance 使用。
- 每次运行会保存 `layer_context_briefs/L1.json` 到 `layer_context_briefs/L5.json`，便于审计。
- 测试已增加回归断言：L1 的 layer context 只能包含 `L1` highlights，且 cross-layer signals 为空。

prompt inspection 结果：

- 新 L1 runtime prompt 不含 `get_vix`。
- 不含 `Equity Risk Premium`。
- 不含 `QQQ/QQEW`。
- 不含 `QQQ ADX`。
- 不含“流动性收紧与高估值并存”这类跨层状态判断。

下一轮“新 L1 vs 老 L1”完整对照应在这个隔离修复之后进行，否则旧实验会混入全局摘要污染，结论不干净。
