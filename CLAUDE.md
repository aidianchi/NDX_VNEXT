# CLAUDE.md

本文件是 Claude Code 在本仓库工作的硬规则。保持简洁，优先服从。

## 必读顺序

1. `AGENTS.md`
2. `NEXT_STEPS.md`
3. `ARCHITECTURE.md`
4. `RUN_REVIEW_CHECKLIST.md`
5. `WORK_LOG.md`

## 分支规则

- 禁止直接在 `main` 上开发。
- 每次实施前必须新建分支：`claude/YYYYMMDD-short-task-name`。
- 只提交到该分支；不得 merge 到 `main`。
- 推送时只推送自己的分支，等待人工或 Codex 审查。

## 不可破坏的架构原则

- 不得回退 L1-L5 上下文隔离。
- L1-L5 不得接收其他层运行时数据、摘要、结论或候选跨层关系。
- Bridge 只建模跨层冲突、共振和传导，不重新分析单指标。
- Thesis / Critic / Risk / Reviser / Final 必须保留高严重度冲突和风险边界。
- `legacy_adapter.py` 只能做兼容映射，不得重新成为主要推理生产者。
- 不得为了报告顺滑而抹平冲突。
- L3 结构指标当前保持“强提示、非硬失败”，不得擅自升级为 hard fail。

## 文件与安全规则

- 禁止提交 `.env`、`.venv/`、`output/`、`data_cache/`、缓存文件和真实密钥。
- 不得修改或删除用户未要求处理的文件。
- 不得执行破坏性 Git 命令，例如 `git reset --hard`、强制覆盖用户改动。
- 如果工作树有不属于自己的改动，先说明并避开。

## 实施规则

- 小步提交，避免混入无关重构。
- 改代码必须加或更新测试。
- 改 prompt 必须考虑是否会诱导无证据推断。
- 不得编造历史胜率、回测收益、样本区间或概率数字，除非 evidence refs 明确提供。
- 重要改动后运行：`.\.venv\Scripts\python.exe -m pytest -q`。
- UI 相关改动后，用最新 run 生成 native UI。

## 文档规则

- 架构变化更新 `ARCHITECTURE.md` 或 `NEXT_STEPS.md`。
- 完成事项写入 `WORK_LOG.md`，最新在上。
- 面向普通读者的解释写入通俗报告，不替代架构文档。
- 中文优先，少黑话，少中英夹杂。

## 交付规则

每次结束必须说明：

- 分支名。
- 改了哪些文件。
- 运行了哪些验证。
- 仍有哪些风险或未完成事项。
