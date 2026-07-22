# docs/archive — 历史材料索引

**这里的每一份文件都是"当时的事实"，不是现状。**

可以引用它们说明"当时为什么那样判断""这个决定的来龙去脉"，**不得**当作当前系统行为、当前数据覆盖或当前待办的依据。判断现状请读 `现在.md`；长期架构看 `ARCHITECTURE.md`；已完成记录看 `WORK_LOG.md`。

归档动作发生在 2026-07-22 的文档结构收敛（见 `WORK_LOG.md` 当日条目）。归档用 `git mv`，全部历史可回溯。

---

## 2026-05/

2026 年 5 月期的一次性审查报告与旧版通俗说明。当时 vNext 还在早期重构阶段，其中描述的架构、数据源状态和待办清单**大部分已被后续工作取代**。

| 文件 | 是什么 | 为什么归档 |
|---|---|---|
| `2026-05/PROJECT_AUDIT_20260513.md` | 5-13 全项目审查报告 | 一次性审查，其发现已在后续工单中处置完毕 |
| `2026-05/audit_report_20260517.md` | 5-17 审查报告 | 同上 |
| `2026-05/BRIDGE_INPUT_AUDIT_L3_COREFACTS_CONTAMINATION.md` | Bridge 输入污染专项审查 | 问题已修复并有测试锁定 |
| `2026-05/2026-05-18_0409_BACKTEST_FORENSIC_AUDIT.md` | 0409 回测取证审查 | 一次性取证，回测原则已沉淀进 `回测原则.md` |
| `2026-05/2026-05-18_PLAIN_LANGUAGE_0409_BACKTEST_INVESTIGATION.md` | 上一份的白话版 | 同上 |
| `2026-05/2026-05-19_0409_BACKTEST_SYNTHESIS_AUDIT.md` | 0409 回测综合审查 | 其中未完成事项已重新核对，仍需做的统一收进 `现在.md` |
| `2026-05/OUTPUT_EXPERIENCE_DESIGN_REPORT.md` | 早期输出体验设计报告 | 报告形态已经历 R1-R8 重构，内容整体过时 |
| `2026-05/PLAIN_LANGUAGE_OUTPUT_EXPERIENCE_REVIEW.md` | 上一份的白话版 | 同上 |
| `2026-05/PLAIN_LANGUAGE_AGENT_PIPELINE_REVIEW.md` | agent 主链路白话说明 | 链路已随 R/W 两批工单变化，描述不再准确 |
| `2026-05/PLAIN_LANGUAGE_L4_DATA_SOURCE_REVIEW.md` | L4 数据源白话说明 | 数据源现状以 `DATA_COVERAGE_REVIEW.md` 为准 |
| `2026-05/PLAIN_LANGUAGE_CHANGE_REPORT.md` | 早期改动白话说明 | 已被 `人话进度报告.md` 的信件体系取代 |
| `2026-05/PLAIN_LANGUAGE_GITHUB_REPO_RESEARCH.md` | 同类开源仓库调研 | 一次性调研 |

**没有归档、仍然有效的同期文件**：`回测原则.md`（第一性原理推导的回测必要条件，仍是现行准则）、`DESIGN.md`（`$impeccable` 技能的设计寄存器输入，仍被读取）。
