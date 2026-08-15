# P4 隔离真实性 · 进度

## 任务 0 开工回执（2026-08-14）

1. `ls` 三文件：`packet_builder.py` / `prompt_inspector.py` / `prompts/l1_analyst.md` 均存在（输出原文见最终回复）。
2. 已读 l1_analyst.md 全文（100 行）。
3. 已读 packet_builder.py 全文（1080 行）。
4. **指路偏差**：`_build_layer_input_policy` 实际在 `orchestrator.py:975`，不在 packet_builder.py（packet_builder 只有 `AnalysisPacketBuilder.build/_group_raw_data/_build_layer_facts/_build_candidate_links/_build_event_refs`）。已读 orchestrator.py 该函数与 `_build_layer_context_brief`、`_sanitize_prompt_payload`、`_capture_prompt_attempt`。已记 BLOCKED。
5. 已读任务书 / 01 底稿 / 系统说明书（第四、2.1、2.10、2.11）。
6. 已用真实 run `output/analysis/vnext/20260731_002156/prompt_audit/` 实证：L1 prompt 的 `layer_raw_data` 仅含本层 9 指标，`apparent_cross_layer_signals=[]`；其他层指标名（get_vix 等）只出现在静态法典清单与格式示例中、不带数值。
7. 下一步：联网查证文献 → 写备忘录 → 落盘 BLOCKED。

## 待办（全部完成 2026-08-14 13:37）
- [x] 任务 0 + 读必读三份
- [x] 任务 1 隔离机制代码/产物盘点（含真实 run 产物 grep 实证）
- [x] 任务 2 文献查证（4 条 A 级：contamination ×3 + lookahead/backtest overfitting ×1）
- [x] 任务 3 两个误判场景（宽松vs衰退 / 价值陷阱）
- [x] 任务 4 裁决（保持）+ 失效条件（3 条可测）
- [x] 备忘录 + BLOCKED 落盘
