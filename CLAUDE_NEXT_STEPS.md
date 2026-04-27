# Claude Code 下一步推进计划

日期：2026-04-27
用途：给 Claude Code 在独立分支上执行。不得直接改 `main`。

---

## 0. 开始前

1. 阅读 `CLAUDE.md`。
2. 新建分支：`claude/20260427-governance-input-compression`。
3. 确认工作树干净。

---

## 1. 当前目标

压缩 Critic / Risk / Reviser / Final 的输入，降低 token 膨胀，同时不丢失：

- high severity typed conflicts；
- Objective Firewall；
- must-preserve risks；
- evidence refs；
- Schema Guard summary；
- L3 广度缺失这类关键限制。

不要大改 L1-L5 prompt。不要把 L3 升级为 hard fail。

---

## 2. 推荐实施顺序

### Step 1：读现状

重点阅读：

- `src/agent_analysis/orchestrator.py`
- `src/agent_analysis/contracts.py`
- `src/agent_analysis/prompts/critic.md`
- `src/agent_analysis/prompts/risk_sentinel.md`
- `src/agent_analysis/prompts/reviser.md`
- `src/agent_analysis/prompts/final_adjudicator.md`
- `tests/test_objective_firewall.py`
- `tests/test_prompt_guardrails.py`

### Step 2：建立 governance 输入包

在不破坏现有 artifact 的前提下，增加一个更窄的治理输入结构。

建议包含：

- `thesis_summary`
- `high_severity_typed_conflicts`
- `objective_firewall_summary`
- `must_preserve_risks`
- `schema_guard_summary`
- `key_evidence_refs`
- `known_data_gaps`

### Step 3：让 Critic / Risk / Reviser / Final 使用窄输入

目标不是让它们知道更少，而是让它们只看到该看的重点。

必须保留：

- 高严重度冲突；
- L3 数据缺口；
- 风险触发器；
- 反证条件；
- evidence refs。

### Step 4：加测试

至少覆盖：

- governance 输入包不会丢失 high severity typed conflicts；
- governance 输入包包含 Objective Firewall；
- governance 输入包包含 L3 数据缺口；
- prompt 中继续禁止编造历史概率、样本期、回测收益。

### Step 5：验证

必须运行：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

如果改动会影响报告展示，再生成最新 native UI。

---

## 3. 不要做

- 不要重写整个 orchestrator。
- 不要引入新的 agent 角色。
- 不要做正式前端化。
- 不要让 legacy adapter 承担主推理。
- 不要把 `deep-research-report.md` 大段塞进 prompt。
- 不要用“概率”“样本”“回测”包装没有证据支持的判断。

---

## 4. 完成后交付

Claude Code 完成后必须汇报：

- 分支名。
- 改动文件。
- 测试结果。
- 是否生成 UI。
- token 是否有下降迹象。
- 是否有需要 Codex 或用户审查的风险点。
