# vNext 目标 Agent 架构与实施路线图

日期：2026-04-24  
最近更新：2026-04-29
状态：主架构文件；以 `RESEARCH_CANON.md` 的研究结论为路线图基准。

---

## 1. 本文定位

本文是 `ndx_vnext` 的主架构文件。后续 agent 如果只读一个路线图，应优先读本文，再读：

- `NEXT_STEPS.md`：当前下一步，按核心系统、数据基础、输出体验三类组织。
- `AGENTS.md`：开发规则、验证命令、上下文隔离要求。
- `RESEARCH_CANON.md`：指标判读与跨层级推理的权威研究语料。
- `RUN_REVIEW_CHECKLIST.md`：真实运行后的复盘标准。

如果本文与更早的计划冲突，以本文为准。

核心目标不变：

> vNext 不是把旧报告换一个模型重跑，而是生成一条可审计、可展开、可交互阅读的 NDX 投研推理链。

这条链必须能回答五个问题：

1. 我们到底在判断什么对象？
2. 每个指标有多大发言权？
3. 哪些证据互相确认？
4. 哪些证据互相冲突？
5. 什么证据会让我们改变判断？

---

## 2. 新结论：Deep Research 是研究法典，不是普通范例

`RESEARCH_CANON.md` 现在被确定为 vNext 的权威研究语料，作用包括：

- 指标判读标准。
- 市场状态诊断模板。
- 跨层级推理规则。
- 少文本提示的高质量范例。
- 优化 L1-L5、Bridge、Thesis、Critic、Risk、Reviser、Final 的参照。

旧路线图曾把 `brief` UI 和 Bridge v2 放在很靠前的位置。现在顺序必须调整。

原因很简单：

> 如果 Layer 输出还没有“指标发言权”意识，Bridge v2 只是把旧推理结构化；UI 再漂亮也只是更漂亮地展示不够成熟的推理。

新的顺序是：

```text
Deep Research 研究法典
  -> L0 投资对象定义
  -> L1-L5 法典感知输出
  -> Bridge v2 typed conflict / resonance / transmission map
  -> Thesis/Governance 客观性防火墙
  -> 最新 full smoke
  -> 原生 vNext UI 迭代
```

---

## 3. 第一性原则

### 3.1 Context-first, role-second

Agent 拆分的第一原因不是“像真实投研团队一样分工”，而是：

- 隔离上下文。
- 避免过早综合。
- 让每个层级先独立完成本层认知变换。
- 把跨层冲突留给 Bridge 显式处理。

一句话：

> Agent 是在干净上下文里完成一次受约束的认知变换，而不是扮演一个职位。

### 3.2 静态规则可以共享，运行时状态不能共享

L1-L5 可以知道：

- 五层框架的静态职责。
- 投资对象定义。
- 本层指标的法典规则。

L1-L5 不能知道：

- 其他层本次看到的运行时数据。
- 其他层本次的结论。
- Python 预生成的跨层候选关系。
- Bridge 或 Thesis 的当前判断。

白话说：

> 允许知道“别人负责什么”，禁止知道“别人这次看到了什么、判断了什么”。

### 3.3 冲突是资产，不是瑕疵

vNext 必须保留以下张力：

- 高真实利率 vs 高估值。
- 价格趋势强 vs 市场广度弱。
- 流动性改善 vs 信用恶化。
- VIX 回落 vs 集中度上升。
- 龙头股强势 vs 等权指数疲弱。
- 降息预期来自软着陆，还是来自经济压力。

报告不能为了读起来顺滑而抹平这些冲突。

### 3.4 原生 v2 artifact 是主产品

主要产品是：

- `layer_cards/L1-L5.json`
- `bridge_memos/*.json`
- `synthesis_packet.json`
- `thesis_draft.json`
- `critique.json`
- `risk_boundary_report.json`
- `schema_guard_report.json`
- `analysis_revised.json`
- `final_adjudication.json`

`legacy_adapter.py` 只做兼容导出，不再承担主要推理生产。

---

## 4. 新增核心概念

### 4.1 ObjectCanon：投资对象法典

先说明“我们到底在分析什么”。

当前默认对象：

- `NDX`：主要判断对象。
- `QQQ`：常用可交易代理。
- `NDXE / QEW`：等权口径参考，用来观察广度和集中度。

关键边界：

- QQQ 不是所有科技股。
- NDX 是市值加权指数，头部公司权重很高。
- 等权参考落后时，不能假装指数内部很健康。
- 如果对象口径不清楚，Final 应该降低置信度甚至拒绝放行。

### 4.2 IndicatorCanon：指标法典

每个指标都要说明：

- 它真正回答什么问题。
- 它能证明什么。
- 它不能证明什么。
- 它需要哪些指标确认。
- 什么证据会反驳它。
- 它是长期框架指标、短线执行指标，还是风险提醒指标。

例子：

- RSI 只能说明短线交易节奏，不能证明估值便宜。
- VIX 说明保险价格，不等于买入信号。
- 净流动性是代理指标，不是官方真理。
- 高估值不是自动看空，但高估值加高真实利率是核心冲突。

### 4.3 PermissionType：指标发言权

指标按发言权分成五类：

- `fact`：事实型。
- `proxy`：代理型。
- `composite`：合成型。
- `technical`：技术型。
- `structural`：结构型。

这个分类的目的不是复杂化，而是防止越权推理。

例如：

- 技术型指标不能替估值层下结论。
- 代理型指标不能被当成官方事实。
- 结构型指标主要判断广度和集中度，不负责短线买卖点。

### 4.4 RegimeScenarioCanon：市场状态情景法典

情景法典保存可复用的市场状态模板，例如：

- 软着陆延续。
- 狭窄龙头牛市。
- 高真实利率压制估值。
- 流动性修复。
- 信用压力市场。
- 黄金坑候选。

情景只是模板，不是自动结论。必须由本次 evidence refs 验证。

### 4.5 ObjectiveFirewallSummary：客观性防火墙

强结论前必须检查：

- 投资对象是否清楚。
- 指标发言权是否正确。
- 数据时间和频率是否匹配。
- 是否有跨层验证。
- 最强反证是什么。
- 哪些张力仍未解决。

如果这些问题答不清，就不应使用“大买”“大卖”“顶部”“黄金坑”等强标签。

---

## 5. 当前目标架构

第一版仍采用“少量模型调用 + 强合约 + 高质量中间产物”。

推荐调用链：

1. Data Collect：代码执行。
2. Data Audit：代码执行。
3. Context Build：代码拼接，不调用模型。
4. L0 Object Canon：静态规则注入，不调用模型。
5. L1 Layer Analyst：只吃 L1 runtime context + ObjectCanon + L1 IndicatorCanon。
6. L2 Layer Analyst：只吃 L2 runtime context + ObjectCanon + L2 IndicatorCanon。
7. L3 Layer Analyst：只吃 L3 runtime context + ObjectCanon + L3 IndicatorCanon。
8. L4 Layer Analyst：只吃 L4 runtime context + ObjectCanon + L4 IndicatorCanon。
9. L5 Layer Analyst：只吃 L5 runtime context + ObjectCanon + L5 IndicatorCanon。
10. Bridge：消费 L1-L5 artifact，识别冲突、共振、传导。
11. SynthesisPacket：代码压缩和证据索引。
12. Thesis Builder：只整合压缩后的证据图。
13. Critic：攻击越权推理和弱逻辑。
14. Risk Sentinel：定义可观察风险触发器。
15. Schema / Trace Guard：代码校验。
16. Reviser：修订但不抹平冲突。
17. Final Adjudicator：独立裁决。
18. Native vNext UI：直接消费 v2 artifacts。
19. Legacy HTML：兼容输出。

---

## 6. 已完成基线

### 6.1 v2 LayerCard 基线

L1-L5 必须输出：

- `indicator_analyses`
- `layer_synthesis`
- `internal_conflict_analysis`
- `cross_layer_hooks`
- `quality_self_check`
- `risk_flags`
- `confidence`

旧式薄 LayerCard 会在 Bridge 消费前被拒绝并触发重试。

### 6.2 Layer-local context isolation

已经明确：

- L1-L5 只接收本层运行时数据。
- L1-L5 不接收其他层运行时摘要。
- `manual_overrides` 按本层 `function_id` 过滤。
- 静态五层本体只用于路由问题，不代表其他层当前状态。

### 6.3 Native vNext UI 原型

已经有四个 self-contained HTML 模板：

- `cockpit`
- `brief`
- `atlas`
- `workbench`

当前默认模板是 `brief`。但 UI 现在降为 P2：等研究法典、Bridge v2 和治理输入更稳定后再重点迭代。

### 6.4 Deep Research 法典第一切口

截至 2026-04-26，第一切口已经开始落地：

- 新增 `ObjectCanon`、`IndicatorCanon`、`RegimeScenarioCanon`、`ObjectiveFirewallSummary` 合约。
- 新增 `PermissionType`。
- 新增静态 `deep_research_canon.py`。
- L1-L5 prompt 开始注入当前层的静态法典块。
- `IndicatorAnalysis` 增加软法典字段。

---

## 7. 当前优先级与实施状态

### 7.1 2026-04-26 实施验收摘要

本轮已按 Deep Research 法典路线从 P0 推进到 P3。当前状态：

| 优先级 | 状态 | 已落地内容 |
| --- | --- | --- |
| P0 | 已实施并通过测试 | 薄 LayerCard 拒绝进入 Bridge；L1-L5 prompt 运行时输入会过滤其他层指标；legacy adapter 明确降为兼容映射。 |
| P1A | 已实施第一版 | `deep_research_canon.py` 覆盖当前 `packet_builder` 中 L1-L5 指标；每个指标具备发言权、误读护栏、交叉验证和反证字段。 |
| P1B | 已实施第一版 | Layer 输出缺失软法典字段时由 orchestrator 按本层 `function_id` 回填；当前仍是软约束，不 hard fail。 |
| P1C | 已实施，保持审慎 | L3 结构指标被加入 schema guard 的建议项；只在覆盖不足时提示，不作为硬失败条件，避免过度上调 L3。 |
| P1D | 已实施第一版 | Bridge v2 typed map 已进入合约、prompt、orchestrator、synthesis packet 与 UI：`typed_conflicts`、`resonance_chains`、`transmission_paths`、`unresolved_questions`。 |
| P1E | 已实施第一版 | SynthesisPacket 新增 `objective_firewall_summary`，Thesis 阶段必须消费客观性防火墙。 |
| P2 | 已实施第一版并 smoke | 使用真实 DeepSeek run 生成 vNext artifacts，并生成四套 native UI；UI 已展示指标发言权、反证条件、typed map 与 Objective Firewall。 |
| P3 | 已实施第一版 | `legacy_adapter.py` 输出 `adapter_policy`，声明旧 HTML 只是兼容导出，质量基线转向 native vNext artifacts。 |

本轮真实 smoke run：

- run 目录：`output/analysis/vnext/20260426_235800`
- native UI：`output/reports/vnext_ui_20260426_235800_brief.html`
- 全量测试：`28 passed`
- schema guard：通过
- final stance：`中性偏谨慎（风险偏向下行）`
- final approval：`approved_with_reservations`

后续迭代重点不是继续堆 UI，而是观察几轮真实 run 后再决定是否把软约束收紧为 hard fail，尤其是 L3 结构覆盖、Objective Firewall 警告与 typed map 质量。

### 7.2 2026-04-27 真实运行观察

本轮按观察表又跑了一次真实 smoke：

- run 目录：`output/analysis/vnext/20260427_190347`
- native UI：`output/reports/vnext_ui_20260427_190347_brief.html`
- schema guard：通过
- final stance：`谨慎`
- final approval：`approved_with_reservations`
- Bridge v2 输出：5 个 typed conflicts、3 个 resonance chains、4 条 transmission paths。
- Objective Firewall：`object_clear`、`authority_clear`、`timing_clear`、`cross_layer_verified` 均为 true，无 warning。

关键观察：

- L3 第一次尝试漏掉 4 个结构指标，被 validator 拦下后重试成功。最终 L3 明确保留“广度数据缺失”的限制，因此当前仍不建议把 L3 结构覆盖升级为 hard fail。
- Risk / Final 输出曾出现未经 evidence refs 支持的历史概率、样本期和回测收益表述。根因是治理阶段 prompt 示例里带有类似写法。
- 已补上 prompt 护栏：Risk Sentinel 和 Final Adjudicator 禁止编造历史胜率、回测收益、样本区间或概率数字，除非输入 evidence refs 明确提供。
- 新增 `tests/test_prompt_guardrails.py` 防止这类示例回流。

下一阶段优先级：

1. 继续观察 typed map 和 Objective Firewall 的多轮稳定性。
2. 继续压缩 Critic / Risk / Reviser / Final 的输入，降低 token 膨胀。
3. L3 保持“强提示、非硬失败”。
4. `brief` 继续等待真实读者反馈后再做信息架构调整。

### 7.3 2026-04-29 DeepSeek-only 基准

2026-04-29 已将默认运行基准收敛到 DeepSeek：

- 首选模型：`deepseek-v4-flash`
- 备用模型：`deepseek-v4-pro`
- 其他模型不再作为常规验证路径。

本轮真实 run：

- run 目录：`output/analysis/vnext/20260429_001955`
- 实际使用模型：`deepseek-v4-flash`
- final stance：`中性偏谨慎`
- final approval：`approved_with_reservations`
- 全量测试：`39 passed, 133 warnings`

关键观察：

- Governance input 压缩后，Final 的支撑证据仍能追到 evidence index。
- Risk / Final 的新增护栏阻止了无证据点位、跌幅、估值倍数和盈利阈值表述继续扩散。
- Bridge typed conflicts 已较稳，但 resonance chain 还需要更硬的证据字段要求。
- L3 数据仍是最大薄弱点：原始采集成功不代表语义质量足够，广度与内部扩散指标需要补数据源或 fallback。

因此下一阶段优先级调整为：

1. 补 Bridge resonance chain 的证据字段约束。
2. 补 L3 广度数据源和 fallback。
3. 评审 2026-04-29 run 生成的 `brief` 输出体验。

### P0：保留安全门

已实施，后续必须持续保证：

- 薄 LayerCard 不能进入 Bridge。
- L1-L5 不能看到其他层运行时数据。
- `legacy_adapter.py` 不能重新成为主要认知生产者。

### P1A：扩展 Deep Research 法典

第一版已经补全当前 L1-L5 指标覆盖。后续还可继续扩展：

- 更多 L1-L5 指标。
- 每个指标的误读护栏。
- 每个指标的反证条件。
- 少文本提示卡。
- 情景法典。

完成标准：

- 可以按 `layer + function_id` 精确选出当前层法典。
- prompt 中不出现其他层运行时数据。
- 测试覆盖法典选择和 prompt 注入。

### P1B：让 L1-L5 稳定输出法典感知分析

`IndicatorAnalysis` 已经有软字段：

- `permission_type`
- `canonical_question`
- `misread_guards`
- `cross_validation_targets`
- `falsifiers`
- `core_vs_tactical_boundary`

第一阶段仍然只 warning，不 hard fail。等几轮 smoke 稳定后再收紧。

### P1C：修正对象定义，并提高 L3 数据优先级

L3 数据要谨慎上调优先级，因为它决定系统有没有读对 NDX：

- NDX vs QQQ。
- NDXE vs QEW。
- Top10 权重。
- 广度。
- 集中度。
- 龙头贡献质量。

这不是“多补几个指标”，而是避免把少数龙头的强势误读成整个指数健康。但它目前仍是建议项，不是硬失败项。

### P1D：Bridge v2 typed map

已在 Layer 输出具备法典意识的基础上落地第一版。

目标结构：

- `typed_conflicts`
- `resonance_chains`
- `transmission_paths`
- `unresolved_questions`
- `evidence_refs`
- `involved_layers`
- `severity`
- `confidence`

Bridge 不重新分析单指标，只建模跨层关系。

### P1E：治理阶段客观性防火墙

Thesis、Critic、Risk、Reviser、Final 需要消费更干净的输入包：

- typed Bridge map。
- high-severity conflicts。
- objective firewall summary。
- must-preserve risks。
- evidence refs。

Critic 的重点应包括：

- 指标越权。
- 数据频率错配。
- 代理指标被当成事实。
- 情绪或技术指标压倒信用、估值或结构证据。

Risk 的重点应是可观察触发器，而不是编造历史概率。

当前已由 SynthesisPacket 生成 `objective_firewall_summary`，Thesis prompt 会要求模型显式读取它。Critic、Risk、Reviser、Final 后续可继续加更细的消费约束。

### P2：full smoke 与原生 UI

已完成 P1A-P1E 后的 full smoke，并迭代 native UI。

UI 需要展示：

- 投资对象定义。
- 指标发言权。
- 反证条件。
- typed conflicts。
- 风险触发器。
- evidence refs。

### P3：legacy adapter 降责

已完成第一版降责：

- legacy adapter 只保留兼容映射。
- legacy HTML 不再作为质量基线。

---

## 8. 不要做什么

不要：

- 把整个 `RESEARCH_CANON.md` 硬塞进每个 prompt。
- 让 L1-L5 看到其他层运行时结论。
- 用技术指标证明估值便宜。
- 用情绪指标覆盖信用恶化。
- 把代理指标当成官方真理。
- 在客观性防火墙没通过时使用强标签。
- 为了报告顺滑抹平高严重度冲突。
- 在推理标准升级前优先做 UI 美化。

---

## 9. 验证命令

单元测试：

macOS / Linux：

```bash
python -m pytest -q
```

Windows PowerShell：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

生成默认 `brief` 模板：

```powershell
.\.venv\Scripts\python.exe src\agent_analysis\vnext_reporter.py --run-dir output\analysis\vnext\<run_id> --template brief
```

生成全部 UI 模板：

```powershell
.\.venv\Scripts\python.exe src\agent_analysis\vnext_reporter.py --run-dir output\analysis\vnext\<run_id> --template all --output output\reports\vnext_ui_template.html
```

---

## 10. 一句话北极星

vNext 应该成为这样一个系统：

> 每个市场结论都能说明：判断对象是什么，哪些证据有发言权，哪些证据确认它，哪些证据反驳它，以及出现什么情况我们会改变判断。
