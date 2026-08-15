# P4 隔离真实性 · 待裁决 / 阻塞

## 状态：无待裁决项（不阻塞交付）

## 顺手发现（非阻塞，供所有者知悉）

1. **任务书指路偏差**：P4_任务书.md 任务 0 写"读 `packet_builder.py` 的层级输入政策（`_build_layer_input_policy`）"，但该函数实际位于 `src/agent_analysis/orchestrator.py:975`，`packet_builder.py` 全文（1080 行）无此函数。
   - 已自行定位到 orchestrator.py 并读完（含 `_build_layer_input_policy` / `_build_layer_context_brief` / `_sanitize_prompt_payload` / `_capture_prompt_attempt`），不影响结论。
   - `packet_builder.py` 里与"隔离"直接相关的实际函数是 `AnalysisPacketBuilder.build`、`_group_raw_data`、`_build_layer_facts`、`_build_candidate_links`、`_build_event_refs`（`allow_event_refs` 开关）。
   - 不构成裁决阻塞；是否需修正任务书措辞由所有者定。
