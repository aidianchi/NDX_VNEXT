# AGENTS.md

本文件用于指导 Codex 和其他代码 agent 在 `ndx_vnext` 仓库中工作。

## 项目目标

`ndx_vnext` 是 NDX 研究系统的下一代流水线。它的目标不是简单生成一份 HTML 报告，而是生成一条可审计、可展开、可交互阅读的投研推理链：

1. 采集并标准化市场数据。
2. 隔离 L1-L5 五层上下文。
3. 让每层产出原生指标级分析。
4. 显式识别跨层冲突、共振和传导机制。
5. 构建最终 thesis，同时保留未解决张力。
6. 用原生 vNext UI 展示完整证据链，而不是只依赖 legacy HTML。

核心架构原则：

> Context-first, role-second.

Agent 拆分的理由是上下文隔离和认知变换边界，而不是模仿人类职位分工。

## 当前优先级

当前阶段目标是把 vNext 打磨成高质量第一版：

- L1-L5 必须产出原生 `indicator_analyses`、`layer_synthesis`、`internal_conflict_analysis`、`cross_layer_hooks` 和 `quality_self_check`。
- Bridge 必须消费 Layer 输出，并生成显式跨层冲突、共振和传导逻辑。
- Thesis、Critic、Risk、Reviser、Final 必须保留高严重度冲突和风险边界。
- 原生 vNext UI 必须直接消费 v2 artifacts，不能继续依赖 legacy adapter 拼出的主要叙事。

后续工作按三类组织：

1. 核心系统：推理链、上下文隔离、跨层关系、治理校验。
2. 数据基础：数据采集、标准化、数据源覆盖、缺口和置信度边界。
3. 输出体验：native HTML、未来交互系统、审美、排版和连续阅读体验。

最新任务以 `NEXT_STEPS.md` 为准；完成记录写入 `WORK_LOG.md`，两者都按最新在上排列。

## 重要路径

- `src/agent_analysis/orchestrator.py`：vNext 编排逻辑和 prompt 注入。
- `src/agent_analysis/contracts.py`：所有 vNext artifact 的 Pydantic 合约。
- `src/agent_analysis/prompts/`：L1-L5、Bridge、Thesis、Critic、Risk、Reviser、Final prompts。
- `src/agent_analysis/few_shot.py`：按 layer-local function_id 注入 few-shot。
- `src/prompt_examples.py`：按 `function_id` 组织的 4C 范例。
- `src/agent_analysis/vnext_reporter.py`：原生 vNext self-contained HTML UI 原型。
- `src/agent_analysis/legacy_adapter.py`：过渡期兼容路径，不应承担主要推理。
- `NEXT_STEPS.md`：当前下一步计划，按核心系统、数据基础、输出体验三类组织。
- `ARCHITECTURE.md`：当前主架构与不可破坏原则。
- `RESEARCH_CANON.md`：指标判读、市场状态诊断和跨层级推理的权威研究语料。
- `DATA_COVERAGE_REVIEW.md`：数据覆盖、弱项和 fallback 优先级复盘。
- `RUN_REVIEW_CHECKLIST.md`：真实运行后的复盘表。
- `WORK_LOG.md`：已完成事项，按时间倒序记录。
- `output/analysis/vnext/<run_id>/`：每次 vNext run 的完整 artifacts。
- `output/reports/`：生成的 HTML 报告和 UI 原型。

## 文档分层与解释风格

本仓库同时维护两类文档：

1. 架构与实施文档  
   面向代码 agent、开发者和未来维护者，用来定义系统结构、合约、优先级和实现路线。  
   代表文档：`ARCHITECTURE.md`、`NEXT_STEPS.md`。

2. 通俗解释报告  
   面向非金融、非软件工程背景读者，用来解释“这次到底做了什么、为什么重要、怎么验证、普通人该怎么看”。  
   代表文档：`PLAIN_LANGUAGE_CHANGE_REPORT.md`。

两类文档必须并行存在，不能互相替代：

- 架构文档必须保持准确、完整、可执行。
- 通俗报告必须保持清楚、克制、少黑话、少中英夹杂。
- 通俗报告可以简化表达，但不能简化事实，不能抹平风险、冲突和不确定性。

当完成跨模块重要改动，或用户要求“解释给普通人听”“写一份说明”“不要行业黑话”时，agent 应优先使用通俗解释报告风格。

通俗解释报告建议包含：

1. 一句话说明。
2. 为什么要改。
3. 实际做了什么。
4. 修改后有什么变化。
5. 刻意没有做什么。
6. 如何验证有效。
7. 普通读者该怎么看。
8. 简单词汇表。
9. 后续最重要的观察点。
10. 最后总结。

写作要求：

- 默认使用中文。
- 避免不必要的英文术语；无法避免时，第一次出现要用中文解释。
- 少用行业黑话，少用缩写堆叠。
- 用“这解决什么问题”来解释技术改动，而不是只列文件名。
- 对金融判断保持边界感：说明证据、反证、冲突和未解决张力。
- 对工程判断保持透明：说明改了哪里、没改哪里、怎么验证。
- 不为了让文本顺滑而隐藏风险或冲突。

推荐命名：

`PLAIN_LANGUAGE_<主题>.md` 或 `YYYY-MM-DD_PLAIN_LANGUAGE_<主题>.md`

## 开发规则

- 优先做小而清晰的补丁，不要一次性混入无关重构。
- 当前默认只测试和运行 DeepSeek：先 `deepseek-v4-flash`，跑不通再 `deepseek-v4-pro`；不要把其他模型作为常规验证路径。
- 不得回退上下文隔离：L1-L5 可以知道静态五层本体，但不能接收其他层的运行时数据、摘要、结论或候选跨层关系。
- 不得让 `legacy_adapter.py` 成为主要认知生产者。它可以映射和兜底，但主要分析必须来自 vNext artifacts。
- 不得为了报告顺滑而抹平冲突。冲突是 vNext 的核心资产。
- 在信息架构确认之前，UI 原型优先保持 self-contained HTML，不急于正式前端框架化。
- 原生 UI 默认模板为 `brief`，因为它最接近可连续阅读的投研报告，同时保留 evidence ref 跳转和审计能力。

## 推荐工作顺序

1. 先阅读 `NEXT_STEPS.md`，确认当前里程碑和优先级。
2. 再阅读 `ARCHITECTURE.md`，确认不可破坏原则。
3. 如果改 L1-L5，先检查 context isolation 是否仍成立。
4. 如果改 Bridge，重点增强 typed conflict / resonance map，而不是增加泛泛总结。
5. 如果改 Thesis/Governance，重点减少上下文污染和 token 膨胀，同时保留高严重度冲突。
6. 如果改数据层，先说明数据源、频率、fallback 和置信度边界。
7. 如果改 UI，优先围绕 `brief` 模板迭代阅读顺序、证据跳转、Layer 展开和风险展示。
8. 每次重要改动后运行测试，并尽可能用最新 run artifacts 生成 native UI。

## 验证命令

macOS / Linux：

```bash
python -m pytest -q
```

```bash
python src/agent_analysis/vnext_reporter.py --run-dir output/analysis/vnext/<run_id> --template brief
```

```bash
python src/main.py --models deepseek-v4-flash,deepseek-v4-pro --skip-report --disable-charts
```

Windows PowerShell：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

生成全部 native UI 原型：

```powershell
.\.venv\Scripts\python.exe src\agent_analysis\vnext_reporter.py --run-dir output\analysis\vnext\<run_id> --template all --output output\reports\vnext_ui_template.html
```

预期输出：

- `output/reports/vnext_ui_template_cockpit.html`
- `output/reports/vnext_ui_template_brief.html`
- `output/reports/vnext_ui_template_atlas.html`
- `output/reports/vnext_ui_template_workbench.html`

生成默认 `brief` 模板：

```powershell
.\.venv\Scripts\python.exe src\agent_analysis\vnext_reporter.py --run-dir output\analysis\vnext\<run_id> --template brief
```

## 已知环境问题

如果 PowerShell 在命令执行前直接报 `8009001d`，这通常是 Windows PowerShell / Crypto Provider 初始化问题，不是仓库权限问题，也不是 Codex 文件权限不足。

临时绕过方式：用 `cmd.exe` 运行同样的 Python 命令。

长期修复方向：

- 测试 `powershell.exe -NoProfile` 是否可启动。
- 检查 PowerShell profile 是否损坏。
- 检查 Cryptographic Services。
- 必要时运行 `sfc /scannow` 和 `DISM /Online /Cleanup-Image /RestoreHealth`。
