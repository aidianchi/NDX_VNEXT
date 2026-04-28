# vNext 顶级推进计划表

基础文档：`2026-04-24_VNEXT_TARGET_AGENT_ARCHITECTURE_PLAN.md`  
最近更新：2026-04-27  
用途：作为日常推进路线板。架构原则和详细解释以基础文档为准。

## 0. 当前总目标

把 vNext 打磨成高质量第一版：

> 干净上下文中的专业底稿 + 显式跨层冲突 + 可追溯证据链 + 可交互阅读界面。

当前主线不是继续堆 prompt，而是让 Deep Research 法典真正进入指标判读、跨层推理、治理校验和 native UI。

## 1. 当前状态快照

| 模块 | 当前状态 | 结论 |
|---|---|---|
| L1-L5 prompt | 已完成 hybrid 重写，并注入本层 Deep Research 法典 | 可作为当前基线 |
| Layer context isolation | 已完成本层 context、data_summary、manual_overrides 隔离，并过滤跨层 runtime 指标 | 可作为当前基线 |
| few-shot 覆盖 | 34 指标已结构性覆盖 | 后续继续提质，不是 blocker |
| DeepSeek 模型 | 默认 `deepseek-v4-flash`，`deepseek-v4-pro` fallback | 已配置方向 |
| v2 artifact | LayerCard、Bridge typed map、SynthesisPacket、Objective Firewall、SchemaGuard 已落地 | 可继续扩展 |
| legacy HTML | 可用但不是目标形态 | 已降为兼容路径 |
| native UI | self-contained HTML 默认 `brief`，已展示法典字段、typed map 和 Objective Firewall | 当前基线 |
| Bridge | 已升级 typed conflict / resonance / transmission map | 继续观察真实 run 质量 |
| Governance | 已接入 Objective Firewall，并补上禁止编造历史概率的 prompt 护栏 | 后续继续压缩 Critic/Risk/Reviser/Final 输入 |
| L3 数据 | 结构优先级已加入建议项 | 审慎上调，不作为硬失败 |

## 2. 推进顺序总览

```text
P0 安全门与上下文隔离
  -> P1 Deep Research 法典覆盖与软回填
  -> P1 Bridge v2 typed conflict / resonance / transmission map
  -> P1 Objective Firewall
  -> P2 full smoke 与 native UI 展示
  -> P3 legacy_adapter 降责
  -> 后续：多轮 smoke 后再决定是否收紧软约束
```

原则：

- 先保证 Layer 不被污染，指标不越权。
- 再增强跨层逻辑结构。
- 再让治理层消费更窄、更干净的输入。
- UI 只展示已被 v2 artifacts 支撑的推理，不承担认知生产。

## 3. P0：UI 评审与最新 smoke

状态：已完成第二轮真实观察。最新真实 run 为 `output/analysis/vnext/20260427_190347`，四套 UI 已生成到 `output/reports/vnext_ui_20260427_190347_*.html`。

### 3.1 生成并评审四个 UI 模板

目标：确定 `brief` 是否作为正式信息架构基线。

任务：

- 生成四个 self-contained HTML：
  - `cockpit`
  - `brief`
  - `atlas`
  - `workbench`
- 用户重点审阅 `brief`。
- 对阅读顺序、视觉密度、证据跳转、Layer 展开、风险展示做反馈。
- 把确认后的方向沉淀为 `VNEXT_NATIVE_UI_SPEC.md`。

命令：

```powershell
.\.venv\Scripts\python.exe src\agent_analysis\vnext_reporter.py --run-dir output\analysis\vnext\20260427_190347 --template all --output output\reports\vnext_ui_20260427_190347.html
```

完成标准：

- 用户确认主模板方向。
- 页面能完整承载 Final、Evidence、Bridge、Layer、Governance。
- evidence ref 跳转可用。
- L1-L5 可作为独立阅读区块。

当前注意：

- PowerShell 若继续报 `8009001d`，先用 `cmd.exe` 绕过。

### 3.2 重新跑 DeepSeek full smoke

目标：验证最近的 context isolation 和 static ontology 改动没有诱发跨层污染。

任务：

- 用最新代码跑真实 API。
- 检查 L1-L5 是否仍只依据本层数据形成分析。
- 检查 `schema_guard_report.passed`。
- 用最新 run 生成 `brief` UI。
- 与最近一次已通过的 run 对比，当前基线为 `output/analysis/vnext/20260427_190347`。

命令：

```powershell
.\.venv\Scripts\python.exe src\main.py --data-json output\data\data_collected_v9_live.json --skip-report --disable-charts
```

完成标准：

- 5 个 LayerCard 全部生成。
- 34 个成功指标全部有 `indicator_analyses`。
- SchemaGuard 通过。
- Bridge 至少保留核心冲突。
- Final stance 与证据链可追溯。

## 4. P1：Bridge v2

目标：把 Bridge 从“自然语言 memo”升级成 typed conflict / resonance map。

状态：已完成第一版。合约、prompt、orchestrator、synthesis packet 和 native UI 已接入。

### 4.1 合约升级

新增或扩展结构：

- `TypedConflict`
- `ResonanceChain`
- `TransmissionPath`
- `UnresolvedQuestion`

每条结构至少包含：

- `id`
- `type`
- `involved_layers`
- `evidence_refs`
- `mechanism`
- `severity`
- `confidence`
- `implication`

完成标准：

- Bridge 输出不再只是段落，而是可被 UI 和 Thesis 精确消费的结构。

### 4.2 Prompt 升级

任务：

- Bridge prompt 明确读取 `indicator_analyses`、`layer_synthesis`、`internal_conflict_analysis`、`cross_layer_hooks`。
- 要求引用具体 `function_id`。
- 要求区分：
  - 共振；
  - 冲突；
  - 传导；
  - 未解决问题；
  - 数据缺口。

完成标准：

- Bridge 不重新解释单指标。
- Bridge 必须指出冲突来自哪些层、哪些指标、哪些机制。

### 4.3 UI 消费

任务：

- `vnext_reporter.py` 的 conflicts 区改为消费 typed map。
- 支持按 severity、layer、type 过滤。
- 点击 conflict 能跳到涉及的 Layer 和 indicator。

完成标准：

- 用户能一眼看到 vNext 的核心冲突图。

## 5. P1：Governance 上下文压缩

目标：降低 token、减少下游污染，同时保留关键冲突。

状态：已完成第一版 Objective Firewall；更细的 Critic / Risk / Reviser / Final 输入压缩留作后续优化。

2026-04-27 观察补充：

- Risk / Final 曾输出未经证据支持的历史概率、样本期和回测收益。
- 根因是治理 prompt 示例中含有类似写法。
- 已新增 prompt 护栏和 `tests/test_prompt_guardrails.py`，禁止编造历史胜率、回测收益、样本区间或概率数字，除非 evidence refs 明确提供。

### 5.1 定义 governance input packet

任务：

- 为 Critic / Risk / Reviser / Final 构造更窄的输入。
- 不再把过多原始 artifact 全量塞给每个治理阶段。

建议输入：

- ThesisDraft
- SynthesisPacket 摘要
- high severity conflicts
- must-preserve risks
- schema summary
- evidence refs

完成标准：

- 下游 token 明显下降。
- 高严重度冲突不丢失。

### 5.2 字段长度处理

问题：

- Reviser 曾因 `environment_assessment` 超过 300 字触发重试。

任务：

- 决定是放宽 Pydantic 字段，还是在 prompt 中强制短字段摘要。
- 长叙事应放到专门字段，短字段只保留摘要。

完成标准：

- 不再因合理长文本频繁触发 schema retry。

## 6. P2：L3 数据补齐

目标：让 L3 不再主要依赖 QQQ/QQEW 和 M7 判断内部结构。

状态：审慎推进。当前只把 L3 结构覆盖加入 schema guard 建议项，不作为 hard fail。

任务：

- 修复或替换 NDX100 成分股获取。
- 补齐：
  - Advance/Decline Line；
  - % Stocks Above MA；
  - New Highs-Lows；
  - McClellan Oscillator。
- 为每个数据源定义 fallback 和置信度边界。

完成标准：

- L3 能稳定判断 breadth、concentration、leadership、momentum diffusion。
- 数据缺失不再是 L3 的主要结论限制。

## 7. P2：brief UI 迭代

目标：把 `brief` 从原型打磨成可长期使用的 native report。

状态：已完成第一版 Deep Research 法典展示。页面已显示指标发言权、误读护栏、反证条件、typed conflicts、resonance chains、transmission paths 和 Objective Firewall。

任务：

- 调整阅读顺序和信息密度。
- 优化五层展开方式。
- 优化指标卡默认折叠策略。
- 增加 risk / conflict / low confidence 快速筛选。
- 增加图表入口。
- 改善移动端阅读。

完成标准：

- 用户能用 `brief` 完成日常阅读。
- 用户能用 `brief` 审计模型证据链。
- legacy HTML 不再是主要阅读入口。

## 8. P3：正式前端化

前提：

- `brief` 信息架构被确认。
- artifact schema 基本稳定。

可能路线：

- 继续强化 self-contained HTML；
- React/Vite 本地 artifact viewer；
- 后续服务化。

任务：

- 定义前端消费的 artifact schema。
- 实现 routing / tabs / evidence jump / raw JSON inspector。
- 接入图表。
- 支持选择 run directory。

完成标准：

- 前端直接读取 `output/analysis/vnext/<run_id>`。
- 不依赖 legacy adapter。

## 9. P3：legacy_adapter 降责

目标：让 legacy path 成为兼容输出，而不是主产品。

状态：已完成第一版。legacy adapter 输出 `adapter_policy`，声明旧路径只做兼容映射。

任务：

- 保留 legacy HTML 生成能力。
- 删除或弱化 adapter 中的主要叙事生成职责。
- 只做字段映射、兜底和兼容。

完成标准：

- vNext 原生 UI 成为主要阅读入口。
- legacy HTML 只是可选导出。

## 10. 每轮工作检查清单

每完成一个实质改动，检查：

- 是否破坏 L1-L5 context isolation？
- 是否让某个下游阶段重新吞入过多上下文？
- 是否丢失 high severity conflicts？
- 是否让 legacy_adapter 承担了不该承担的认知职责？
- 是否有测试覆盖？
- 是否能生成 native UI？
- 是否能追溯 evidence refs？

## 11. 当前推荐立即行动

优先级从高到低：

1. 用户审阅 `output/reports/vnext_ui_20260427_190347_brief.html`，判断阅读顺序是否顺手。
2. 继续观察下一轮真实 run 的 typed map、Objective Firewall 和治理 prompt 护栏是否稳定。
3. 优先压缩 Critic / Risk / Reviser / Final 输入，降低 token 膨胀。
4. 继续补充少文本高质量范例，而不是把 `deep-research-report.md` 大段塞进 prompt。
5. 暂不把 L3 升级为 hard fail，等待更多真实运行证据。

当前不要优先做：

- 继续大改 L1-L5 prompt；
- 过早上正式前端框架；
- 继续美化 legacy HTML；
- 增加更多 agent 角色；
- 多空辩论 agent。

## 12. 关键命令

测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

生成四个 UI 模板：

```powershell
.\.venv\Scripts\python.exe src\agent_analysis\vnext_reporter.py --run-dir output\analysis\vnext\20260427_190347 --template all --output output\reports\vnext_ui_20260427_190347.html
```

生成默认 `brief`：

```powershell
.\.venv\Scripts\python.exe src\agent_analysis\vnext_reporter.py --run-dir output\analysis\vnext\20260427_190347 --template brief
```

真实 smoke：

```powershell
.\.venv\Scripts\python.exe src\main.py --data-json output\data\data_collected_v9_live.json --skip-report --disable-charts
```
