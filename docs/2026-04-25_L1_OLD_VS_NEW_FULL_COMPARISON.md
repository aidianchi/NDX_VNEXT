# L1 Old vs New Full Prompt Comparison

日期：2026-04-25

目的：在完成 `context_brief` 层级隔离之后，正式对比旧版 L1 prompt 正文与新版 L1 prompt 正文，判断下一步 L1 应该回滚、保留、还是融合重写。

## 1. 实验定义

这不是“旧系统 vs 新系统”的全量对照，而是更有决策价值的 prompt-body 对照：

- 旧 L1 正文：`C:\ndx_agent\src\agent_analysis\prompts\l1_analyst.md`
- 新 L1 正文：`C:\ndx_vnext\src\agent_analysis\prompts\l1_analyst.md`
- 两者都运行在当前 vNext 框架下。

固定条件：

- 数据：`output/data/data_collected_v9_live.json`
- 模型：`deepseek-v4-flash`，`deepseek-v4-pro` 作为 fallback
- Layer context：已隔离后的 L1-only context brief
- Raw data：只给 L1 的 8 个原始指标
- Few-shot：只给 L1 相关 4C 范例
- Schema：同一套 v2 `LayerCard`，必须输出 `indicator_analyses`、`layer_synthesis`、`internal_conflict_analysis`、`quality_self_check`

实验目录：

`output/experiments/l1_old_vs_new_full_20260425_104010`

说明：两组都使用当前 orchestrator 注入的 v2 contract，因此旧 L1 不是“旧系统原样运行”，而是“旧 L1 正文放入新 vNext 骨架后运行”。这是我们当前最需要回答的问题：在 vNext 里，哪个 L1 正文更适合作为下一步基底。

## 2. 结构结果

| Variant | Runs | Valid | Indicator Coverage | Missing | Extra |
|---|---:|---:|---:|---:|---:|
| old_l1_body | 3 | 3/3 | 8/8 | 0 | 0 |
| new_l1_body | 3 | 3/3 | 8/8 | 0 | 0 |

两者结构上都合格。说明 v2 contract、layer-local context、few-shot 和 normalization 已经能把旧 prompt 和新 prompt 都约束到 v2 产物里。

## 3. 定量对比

| Metric | Old L1 Avg | New L1 Avg | 判断 |
|---|---:|---:|---|
| prompt_tokens | 8831 | 7885 | 新版更省 token，约少 10.7% |
| completion_tokens | 3393 | 2886 | 新版输出更稳定、更短 |
| avg_narrative_chars | 40.1 | 44.8 | 新版指标叙事略更充分 |
| avg_reasoning_chars | 45.3 | 46.7 | 接近，新版略高 |
| avg_chain_items | 3.93 | 4.00 | 接近 |
| layer_synthesis_chars | 150.7 | 194.0 | 新版层级综合更稳定充足 |
| internal_conflict_chars | 184.7 | 178.3 | 接近，旧版略高 |
| required hooks | L4/L2/L5 | L4/L2 | 旧版跨层触觉更广 |

初步结论：

- 新版更高效、更稳定，特别是 `layer_synthesis`。
- 旧版 token 更重，但天然会提出 L5 hook，这对宏观约束和趋势验证是有价值的。
- 二者都没有结构性失败，问题在质量偏好而不是可运行性。

## 4. 金融质量评估

优秀 L1 应抓住五条主线：

1. 高政策利率、实际利率、名义利率仍构成限制性环境。
2. 净流动性动量转正、M2 正增长、实际利率低于均线说明边际改善。
3. 实际利率通过 DCF 折现率压制成长股远期现金流现值。
4. 净流动性改善要拆开看 RRP、TGA、Fed assets，不能机械等同于宽松。
5. 通胀预期高位上行会限制政策宽松空间，并影响名义利率。

### 4.1 旧版 L1 的表现

优点：

- 专业角色感更自然，语言像“宏观流动性分析师”而不是数据转换器。
- 三轮都主动生成 L5 hook，说明它保留了宏观约束与趋势验证的直觉。
- `internal_conflict_analysis` 往往更像投研讨论，能讲清“实际利率高位 vs 净流动性改善”、“铜金比极低 vs 期限利差转正”。
- 第一轮和第二轮对 RRP、TGA、通胀预期、DCF 折现率的理解都合格。

问题：

- prompt 本身较长，输入 token 更高。
- 有些输出偏短，第三轮 `layer_synthesis` 只有 129 字，不够适合未来 UI 单独展示。
- 旧 prompt 里保留大量旧 schema 示例，会和 v2 contract 形成认知噪音。
- 旧版指标说明较“阈值表”化，对 `indicator_analyses` 的 UI-ready 叙事要求不如新版明确。

### 4.2 新版 L1 的表现

优点：

- 更稳定，每轮 `layer_synthesis` 都在 180-200 字左右，适合 UI 单独展示。
- 对“主信号 / 确认信号 / 噪声”的要求更清晰。
- 对通胀预期、名义利率驱动、净流动性质量、曲线正常化 vs 铜金比低位的讨论更一致。
- token 更省，运行成本更低。

问题：

- 专业角色感被削弱。虽然输出结构好，但 prompt 开头的“不是角色扮演”没有必要。
- 三轮都只生成 L4/L2 hooks，没有主动给 L5。对 L1 来说，宏观约束是否会压制当前趋势是重要问题，L5 hook 不应完全丢掉。
- 新版有时更像受控结构化分析，不如旧版有“顶级宏观研究员”的报告气质。

## 5. 代表性片段对比

旧版较好的片段：

> 主要冲突在于：高实际利率与净流动性改善之间的背离。实际利率高位压制估值，但净流动性动量转正提供资金面支撑。此外，铜金比极低（增长悲观）与期限利差转正（衰退担忧消退）存在矛盾，可能反映市场对增长的分歧。

这个片段接近真实投研讨论，能直接放进 L1 UI。

新版较好的片段：

> L1总体状态为restrictive，但存在边际改善信号。核心约束：1）实际利率1.92%处于10年高分位，持续压制成长股估值；2）政策利率3.64%维持限制性，现金机会成本高；3）通胀预期2.42%上行，限制政策宽松预期。边际改善：净流动性4周动量转正（+100.65B），铜金比站上50日均线，M2同比转正。

这个片段更稳定、更清晰，更适合作为结构化 UI 摘要。

## 6. 结论

不应直接回滚旧版，也不应直接保留当前新版。

更准确的判断是：

> 旧版强在“专业角色镜头”和跨层直觉；新版强在“机制化结构”和 UI-ready 稳定性。下一版 L1 应融合二者。

建议下一步 L1 prompt 采用：

> Context-Bounded Macro Liquidity Analyst

具体策略：

- 开头恢复专业角色：`你是顶级机构投资团队中的 L1 宏观流动性分析专家`。
- 紧接着加 context boundary：`你只接收 L1 数据，不读取 L2-L5 当前状态，不给最终投资建议`。
- 保留新版的指标语义、因果语法、层内综合要求。
- 删除“不是角色扮演”这种负面定义，改成正面定义：`角色是专业认知镜头，context boundary 是信息隔离边界`。
- 将 L5 hook 从 optional 提升为 recommended：若 L1 判断为 restrictive 或 mixed，必须询问 L5 当前趋势是否只是滞后反应。
- 增加 UI 展示要求：`layer_synthesis` 和 `internal_conflict_analysis` 要能作为 L1 独立报告段落展示。
- 删除旧版中与 v2 schema 冲突或重复的旧输出示例，避免 prompt 噪音。

## 7. 推荐决策

下一步不要再做纯比较，应直接重写 L1 为 hybrid prompt，然后做三组最终验证：

1. old_l1_body under vNext scaffold
2. new_l1_body under vNext scaffold
3. hybrid_l1_body under vNext scaffold

如果 hybrid 在 2-3 次运行中同时满足：

- 8/8 指标覆盖；
- `layer_synthesis` 稳定超过 180 字；
- `internal_conflict_analysis` 稳定超过 160 字；
- hooks 至少包含 L4、L2，并在 restrictive/mixed 环境下包含 L5；
- 对实际利率、净流动性、通胀预期、曲线、铜金比均有机制化解释；
- UI 可读性强；

则用 hybrid 替换当前 L1 prompt，并按同一方法改写 L2-L5。
