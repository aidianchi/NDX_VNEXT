# vNext 工作记录

阅读方式：最新完成事项放在最上面。这里记录已经完成的事；未来要做的事写在 `NEXT_STEPS.md`。

---

## 2026-04-29

### 合并 DeepSeek-only 运行基准

提交：

- `412f8fa Default to DeepSeek v4 runtime`

完成内容：

- 默认启用 DeepSeek，默认关闭 ChatAI、Kimi 和 Gemini。
- 默认模型顺序保持为 `deepseek-v4-flash` -> `deepseek-v4-pro`。
- DeepSeek V4 调用对齐官方 OpenAI-compatible 参数：`stream=False`、`reasoning_effort="high"`、`thinking` enabled。
- Risk Sentinel 和 Final Adjudicator 新增护栏：不得编造无证据支持的点位、跌幅、估值倍数、盈利阈值或其他定量影响幅度。
- 新增 DeepSeek 运行配置测试和 prompt 护栏测试。

验证结果：

- worktree 分支：`39 passed, 133 warnings`
- 合并后的 `main`：`39 passed, 133 warnings`
- 已推送到 `https://github.com/aidianchi/NDX_VNEXT`

### 完成 2026-04-29 真实运行与数据覆盖复盘

基线 run：

- `output/analysis/vnext/20260429_001955`

完成内容：

- 使用 `deepseek-v4-flash` 完成全链路真实运行，`deepseek-v4-pro` 未触发。
- 复盘治理输入压缩后的 Critic / Risk / Reviser / Final，确认高严重度冲突和最终证据链仍可追溯。
- 发现 L3 广度数据仍是当前最薄弱环节，新增 `DATA_COVERAGE_REVIEW.md` 记录数据稳定项、弱项和下一步。
- 用 2026-04-29 run 生成默认 `brief`：`output/reports/vnext_research_ui_brief_20260423.html`。
- 清理 `.env.example` 的编码损坏，并补充 macOS / Linux 启动路径。

---

## 2026-04-28

### 重整根目录文档

完成内容：

- 把日期型根目录文档改成更容易理解的长期文件名。
- 把过期执行计划移入 `docs/archive/`。
- 新增 `NEXT_STEPS.md`，按“核心系统、数据基础、输出体验”三类组织下一步。
- 新增 `WORK_LOG.md`，用时间倒序记录完成事项。
- 更新 `README.md`，让新读者知道先读什么。

验证方式：

- 检查根目录文档名是否能直接表达用途。
- 检查旧文件名引用是否被更新。

### 合并治理阶段输入压缩

提交：

- Claude 分支提交：`c138a96 Compress governance inputs with support evidence`
- main 合并提交：`2f0a1fd Merge governance input compression`

完成内容：

- 新增 `GovernanceInputPacket`，让 Critic / Risk / Reviser / Final 消费更窄的治理输入。
- 明确保留 `thesis_key_support_chains`。
- `key_evidence_refs` 同时保留高严重度冲突证据和 thesis 支撑链证据。
- 更新治理阶段 prompt，要求检查支撑链证据，不再只看主论点文字。
- 新增治理输入测试，覆盖“支撑证据不在高严重度冲突里也不能丢”。

验证结果：

- `35 passed, 133 warnings`

---

## 2026-04-27

### 建立 Claude Code 独立分支协作规则

完成内容：

- 新增 `CLAUDE.md`。
- 要求 Claude Code 不直接改 `main`，只能在 `claude/YYYYMMDD-short-task-name` 分支提交。
- 规定交付时必须说明分支、改动文件、测试结果和风险。

### 推送 GitHub 备份仓库

完成内容：

- 建立并推送远端仓库：`https://github.com/aidianchi/NDX_VNEXT`。
- 补充 `.gitignore`，避免提交 `.env`、`.venv/`、`output/`、缓存和密钥。

### 补充通俗解释报告风格

完成内容：

- 在 `AGENTS.md` 中写入“架构文档”和“通俗解释报告”并行的规则。
- 明确当用户要求“解释给普通人听”时，要少黑话、少中英夹杂、保留风险和不确定性。

### 完成第二轮真实运行观察

基线 run：

- `output/analysis/vnext/20260427_190347`

结论：

- 指标说明书、typed map、Objective Firewall 和 native UI 已跑通。
- 发现 Risk / Final 会模仿 prompt 示例，生成无证据支持的历史概率。
- 已增加 prompt 护栏和测试，禁止编造历史胜率、回测收益、样本区间或概率数字。

---

## 2026-04-26

### 接入 Deep Research 法典第一轮

完成内容：

- 将 `RESEARCH_CANON.md` 定位为指标判读、市场状态诊断、跨层级推理和少文本提示的权威语料。
- 增加 ObjectCanon、IndicatorCanon、RegimeScenarioCanon、ObjectiveFirewallSummary 等核心概念。
- 让 L1-L5 开始具备指标发言权、误读护栏、反证条件和交叉验证意识。

原则：

- 不把整份研究材料硬塞进 prompt。
- 不破坏 L1-L5 运行时上下文隔离。

---

## 2026-04-24 至 2026-04-25

### 建立 vNext 第一版架构基线

完成内容：

- 明确 `Context-first, role-second`。
- 建立 L1-L5、Bridge、Thesis、Critic、Risk、Reviser、Final 的基本链路。
- 建立 native vNext UI 原型。
- 保留 legacy adapter 作为兼容路径，但不再让它承担主要推理。
