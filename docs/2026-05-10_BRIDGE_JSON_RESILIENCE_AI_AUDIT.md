# Bridge 阶段 JSON 容错与 DeepSeek /beta 接入审阅报告

**写作日期**：2026-05-10
**面向读者**：审阅本次改动的 AI 与人类工程师
**分支**：`claude/20260510-bridge-event-refs-resilience`（main 未合并）
**关联日志**：`output/logs/control_service/20260510_132806_164.log`
**关联 run 目录**：`output/analysis/vnext/20260510_132807/`

> 本文档是审计性质的事实记录，不替代 [ARCHITECTURE.md](../ARCHITECTURE.md) 与 [NEXT_STEPS.md](../NEXT_STEPS.md)。所有数字与字段名均来自源码、log、run artifacts 或 DeepSeek 官方文档；不包含任何编造或推断的统计量。

---

## 1. 起点：观察到的 Bug

用户提供的 [`output/logs/control_service/20260510_132806_164.log`](../output/logs/control_service/20260510_132806_164.log) 在 bridge 阶段抛出 `RuntimeError: bridge failed after 2 attempts`，导致整条 pipeline 终止：

```
2026-05-10 13:39:42,296 - WARNING - bridge validation failed on attempt 2:
  1 validation error for BridgeMemo
  event_refs
    Input should be a valid list [type=list_type, input_value={'event:6479503280a4bf43'..., '盈利分化风险'}}, input_type=dict]

Traceback (most recent call last):
  File "/Users/aidianchi/Desktop/ndx_mac/src/console_run_all.py", line 85, in <module>
    raise SystemExit(main())
  ...
  File "/Users/aidianchi/Desktop/ndx_mac/src/agent_analysis/orchestrator.py", line 776, in _run_stage
    raise RuntimeError(f"{stage_name} failed after {self.max_node_retries} attempts: {last_error}")
```

L1–L5 五层全部成功，问题集中在 bridge 单一阶段。

## 2. 直接根因（两次 attempt 不同错因）

| Attempt | Kind | 失败片段 |
|---|---|---|
| 1 | `parse_error` | `resonance_chains[0].falsifiers` 数组未闭合：`"falsifiers": ["信用利差走阔或风险偏好逆转",` 之后直接出现 `"implication": "..."`，导致 JSON 整体不可解析；原始调试文件为本地运行时产物，不纳入 main |
| 2 | `schema_validation_error` | LLM 把顶层 `event_refs` 输出为 `Dict[event_id, str]`，撞上 `BridgeMemo.event_refs: List[str]`（[contracts.py:569](../src/agent_analysis/contracts.py#L569)） |

证据来自 run 目录 `llm_stage_diagnostics.json` 中 bridge 的 `errors` 数组（见上文 traceback）。

## 3. 系统性根因链

| # | 根因 | 证据位置 | 类别 |
|---|---|---|---|
| R1 | 顶层 `event_refs` 没有 normalize 兜底 | [orchestrator.py 旧版 1253–1284](../src/agent_analysis/orchestrator.py) 仅处理子级 typed_conflicts/resonance_chains/transmission_paths 的 event_refs | 实现缺口 |
| R2 | 输入 `AnalysisPacket.event_refs` 是 `Dict[str, Dict]`（[contracts.py:1078](../src/agent_analysis/contracts.py#L1078)），与输出 schema `List[str]` 形态相反 | run 目录 `analysis_packet.json` 实测 24 项 dict，序列化 15551 字符 | 设计冲突 |
| R3 | `bridge` prompt 既无字段类型说明也无顶层 event_refs 输出示例，第二次重试时 LLM 模仿输入 dict 形态 | 旧版 [`prompts/cross_layer_bridge.md`](../src/agent_analysis/prompts/cross_layer_bridge.md) 三个示例 JSON 均未含顶层 event_refs；`_compose_prompt` 仅说 `JSON 顶层字段必须匹配: <字段名>`（[orchestrator.py:1029](../src/agent_analysis/orchestrator.py#L1029)），不带类型 | Prompt 锚点缺失 |
| R4 | 重试反馈极度笼统：`last_error = "did not return a parseable JSON object"`，下一轮 LLM 不知道前一次错在哪 | 旧版 [orchestrator.py:725–736](../src/agent_analysis/orchestrator.py)；attempt 1 的具体语法错位置（`resonance_chains[0].falsifiers` 末尾）丢失 | 反馈链断裂 |
| R5 | `_light_repair_json` 仅修复"trailing comma"和"`)` slip"两类微错（[llm_engine.py:305–312](../src/agent_analysis/llm_engine.py#L305-L312)），结构性破损（数组未闭合）整片报废 | 已知行为 | 容错过弱 |
| R6 | DeepSeek 当前用 `response_format={"type": "json_object"}`（[llm_engine.py:113–114](../src/agent_analysis/llm_engine.py#L113-L114)）——**只保证合法 JSON、不保证 schema**；官方明言"API 有概率会返回空的 content"（[json_mode 文档](https://api-docs.deepseek.com/zh-cn/guides/json_mode)） | 官方文档 | API 模式选型 |
| R7 | `max_node_retries=2`（[orchestrator.py:105](../src/agent_analysis/orchestrator.py#L105)）：先 parse 错、再 schema 错就到顶 | 配置 | 资源约束 |
| R8 | bridge prompt 长度 175851 字符（diagnostics 记录），`packet.event_refs` 在 prompt 里占 15551 字符 | run 目录数据 | Prompt 容量 |

## 4. DeepSeek 官方约束工具链（事实校核）

依据 [DeepSeek API 文档](https://api-docs.deepseek.com/zh-cn/)（2026-05-10 抓取），**当前主力模型为 `deepseek-v4-flash` 与 `deepseek-v4-pro`**。`deepseek-chat` 与 `deepseek-reasoner` 将于 2026/07/24 弃用，分别等价于 v4-flash 的非思考与思考模式（[pricing](https://api-docs.deepseek.com/zh-cn/quick_start/pricing)）。

可用 JSON 约束机制：

| 工具 | base_url | 模型支持 | 强度 | 关键限制 |
|---|---|---|---|---|
| `response_format={"type":"json_object"}` | 生产 `https://api.deepseek.com` | v4-flash / v4-pro 全部 | 保 JSON 合法、不保 schema；可能返回空 content | 必须在 prompt 中含 `json` 字样并给出格式样例 |
| **Strict Function Calling（Beta）** | `https://api.deepseek.com/beta` | v4-flash / v4-pro，思考与非思考均可（[tool_calls 文档](https://api-docs.deepseek.com/zh-cn/guides/tool_calls)） | 服务端校验 schema、保 100% 命中 | `additionalProperties:false`、所有字段 required；不支持 `min/maxLength`、`min/maxItems` |
| **Prefix Completion（Beta）** | `https://api.deepseek.com/beta` | 全部 | 锚定 assistant 起始字符 | 模型只返回续写部分（不含 prefix），需 client 端拼回 |

思考模式约束：
- 默认 `enabled`；切换参数为 `extra_body={"thinking":{"type":"enabled/disabled"}}`
- `reasoning_effort: high/max`
- **不支持** `temperature` / `top_p` / `presence_penalty` / `frequency_penalty`（设了不报错也不生效）
- 思考模式 + tool calls 在多轮对话中**必须回传 `reasoning_content`**，否则 400

## 5. 本次实施的修复（Fix 1+2+3 + 方案 B）

### 5.1 Fix 1：顶层 `event_refs` normalize 兜底

**文件**：[`src/agent_analysis/orchestrator.py`](../src/agent_analysis/orchestrator.py)
**位置**：`_normalize_payload` bridge 分支末尾接入新增 `_coerce_event_refs_list` helper

**逻辑**：
- `dict` → `list(value.keys())`
- `list[dict]` → 按 `event_id`/`id`/`event_ref`/`ref` 提取
- 标量 → `[str(value)]`
- `None` → `[]`

**测试**：[`tests/test_bridge_v2.py::test_bridge_normalize_coerces_top_level_event_refs_to_list`](../tests/test_bridge_v2.py)

### 5.2 Fix 2：parse_error 反馈携带响应末尾

**文件**：[`src/agent_analysis/orchestrator.py`](../src/agent_analysis/orchestrator.py)
**位置**：`_run_stage` 的 parse_error 分支

**改动**：把 `last_error` 从笼统的 `"did not return a parseable JSON object"` 升级为：

```
{stage_name} did not return a parseable JSON object.
原始响应字符数: {len}.
响应末尾片段（用于定位 JSON 语法错误，请检查最后未闭合的数组、对象或字符串）：
{tail_400_chars}
```

下一轮 LLM 收到这个反馈，能直接看到自己的输出末尾，定位"`falsifiers` 数组未闭合"这种错误。

**测试**：[`tests/test_vnext_orchestrator.py::test_run_stage_parse_error_feedback_includes_response_excerpt`](../tests/test_vnext_orchestrator.py)

**作用面**：对 **所有 stage** 生效（bridge / thesis / critic / risk / reviser / final），不仅 bridge。

### 5.3 Fix 3：bridge prompt 显式锚定 event_refs 类型

**文件**：[`src/agent_analysis/orchestrator.py`](../src/agent_analysis/orchestrator.py) `_compose_bridge_prompt`

**改动**：在 contract 末尾追加约 350 中文字符的强约束段落：

```
## 顶层 BridgeMemo.event_refs 字段类型（强约束）
- BridgeMemo.event_refs 类型固定为 List[str]，只放事件 ID 字符串
  例如：["event:6479503280a4bf43", "event:f71e0fd17b6261c5"]
- 输入里的 event_refs 是 Dict[event_id, 事件元数据]，仅供你引用 ID
- 禁止把这种 dict 形态复制到输出
- 没有要保留的事件请写 []
- typed_conflicts/resonance_chains/transmission_paths 内部 event_refs 同样是 List[str]
```

**测试**：[`tests/test_bridge_v2.py::test_bridge_prompt_anchors_event_refs_as_string_list`](../tests/test_bridge_v2.py)

### 5.4 方案 B-1：DeepSeek base_url 升级到 `/beta`

**文件**：[`src/agent_analysis/llm_engine.py`](../src/agent_analysis/llm_engine.py)
**新增 helper**：`_resolve_deepseek_base_url`（并保留 `_promote_deepseek_base_url` 兼容包装）

**规则**：
- 默认值 `https://api.deepseek.com` → 升级为 `https://api.deepseek.com/beta`
- 已经是 `/beta` → 保持
- 自定义/自托管 endpoint（如 `https://internal.example.com/...`）→ 保持，不静默重写，且不发送 beta-only 的 `prefix: true`

**作用**：解锁（未来的）strict function calling。真实 run 证明 `response_format={"type":"json_object"}` 可在 `/beta` 使用，但不能与 prefix completion 同时使用。

**测试**：
- [`tests/test_vnext_llm_engine.py::test_deepseek_client_promotes_default_base_url_to_beta`](../tests/test_vnext_llm_engine.py)
- [`tests/test_vnext_llm_engine.py::test_deepseek_client_does_not_double_promote_explicit_beta`](../tests/test_vnext_llm_engine.py)
- [`tests/test_vnext_llm_engine.py::test_deepseek_client_respects_self_hosted_base_url`](../tests/test_vnext_llm_engine.py)
- [`tests/test_vnext_llm_engine.py::test_call_ai_does_not_send_beta_prefix_to_custom_deepseek_endpoint`](../tests/test_vnext_llm_engine.py)

### 5.5 方案 B-2：Prefix Completion（AI 审阅后撤回）

**文件**：[`src/agent_analysis/llm_engine.py`](../src/agent_analysis/llm_engine.py)
**原设想**：用 `DEEPSEEK_JSON_PREFIX = "{\n  "` 锚定 JSON 起始。

**实测结果**：真实 run 调用 DeepSeek 官方 `/beta` 时，服务端返回 400：

```
response_format json_object should not be used with prefix
```

因此当前 vNext JSON 主链**不启用 prefix completion**，继续保留 `response_format={"type":"json_object"}` 作为主保护；prefix 只适合作为未来非 `json_object` 路径或专门实验项。

**撤回的做法**：不要在当前 JSON 主链给 `messages` 末尾追加：

```python
{"role": "assistant", "content": DEEPSEEK_JSON_PREFIX, "prefix": True}
```

这一路径与 `response_format=json_object` 冲突，已通过测试禁止组合。

**测试**：
- [`tests/test_vnext_llm_engine.py::test_call_ai_uses_json_output_without_prefix_for_deepseek`](../tests/test_vnext_llm_engine.py)
- [`tests/test_vnext_llm_engine.py::test_call_ai_does_not_send_beta_prefix_to_custom_deepseek_endpoint`](../tests/test_vnext_llm_engine.py)
- [`tests/test_deepseek_runtime_config.py::test_deepseek_v4_calls_use_official_reasoning_parameters`](../tests/test_deepseek_runtime_config.py)（确认 JSON Output 与 thinking 参数保留，且不发送 prefix）

### 5.6 改动文件清单（diff 统计）

```
docs/2026-05-10_BRIDGE_JSON_RESILIENCE_AI_AUDIT.md  | 新增（本文件）
.gitignore                                           | 忽略 ai_response_debug_*.txt 运行时调试文件
src/agent_analysis/llm_engine.py                    | +_resolve_deepseek_base_url helper、/beta 初始化、JSON Output 与 prefix 不组合
src/agent_analysis/orchestrator.py                  | +_coerce_event_refs_list helper、顶层与子级 event_refs 兜底、_run_stage parse_error 反馈强化、_compose_bridge_prompt 强约束段
tests/test_bridge_v2.py                             | +3 个测试（normalize 顶层 + normalize 子级 + prompt 锚点）
tests/test_vnext_orchestrator.py                    | +1 个测试 + 新 fake engine
tests/test_vnext_llm_engine.py                      | +5 个测试（base_url + JSON Output 不发 prefix + custom endpoint 不发 prefix）
tests/test_deepseek_runtime_config.py               | 更新已有测试以确认 thinking 参数与 JSON Output 保留
WORK_LOG.md                                         | +2 段记录
```

## 6. 验证

### 6.1 单元测试

定向测试：

```bash
python -m pytest -q \
  tests/test_bridge_v2.py \
  tests/test_vnext_orchestrator.py::test_run_stage_records_parse_retry_diagnostics \
  tests/test_vnext_orchestrator.py::test_run_stage_parse_error_feedback_includes_response_excerpt \
  tests/test_vnext_llm_engine.py \
  tests/test_deepseek_runtime_config.py
```

全量测试：

```bash
python -m pytest -q
# 138 passed, 164 warnings
```

修改前：3+4=7 个新增测试均按预期 fail；AI 审阅追加的 2 个测试覆盖了子级 event_refs 不 stringify dict 与 JSON Output 路径不发送 prefix。真实 run 暴露 `response_format` 与 prefix 不兼容后，相关测试已改为防止二者组合。

### 6.2 真实 run 验证

AI 审阅时执行：

```bash
.venv/bin/python src/main.py \
  --data-json output/data/data_collected_v9_live.json \
  --models deepseek-v4-flash,deepseek-v4-pro \
  --skip-report --disable-charts
```

结果：

1. 第一次真实 run 暴露 Claude 原方案问题：DeepSeek `/beta` 返回 400，错误为 `response_format json_object should not be used with prefix`。据此撤回 prefix completion 主链方案。
2. 修正后第二次真实 run 成功完成：`output/analysis/vnext/20260510_191820/`，最终 stance 为 `中性偏谨慎`，approval 为 `approved_with_reservations`。
3. `llm_stage_diagnostics.json` 中 bridge 为 `status=ok`、`attempts=1`、`errors=[]`。L5 有一次 metric 名称合约重试后成功，与 JSON/event_refs 问题无关。
4. `bridge_memos/bridge_0.json` 的顶层与子级 `event_refs` 均为 list。

## 7. 仍存的不稳定面（本次未处理）

按风险×影响排序：

| # | 风险 | 状态 |
|---|---|---|
| U1 | 子级 normalize 原本仍保留 `not isinstance(value, list) → [str(value)]`：若 LLM 把 `typed_conflicts/resonance_chains/transmission_paths` 内部 event_refs 写成 dict，会 stringify 成单元素列表（`["{'event:abc': '...'}"]`），过 schema 但语义被毁 | 已在 AI 审阅补丁中修复：子级 event_refs 复用 `_coerce_event_refs_list`，新增回归测试 |
| U2 | bridge prompt 175K 字符；输入 event_refs 占 15.5K 字符，可压缩为 `[(event_id, title, layers)]` 三元组列表 | 未做（避免一次性引入过多变量） |
| U3 | `max_node_retries=2`：先 parse 错、再 schema 错就到顶 | 未调整 |
| U4 | DeepSeek json_object 官方承认"偶发返回空 content"；prefix completion 原本可作为起始锚点，但真实 run 证明它不能与 `response_format=json_object` 组合 | 当前不启用 prefix；根治仍应走 strict function calling |
| U5 | 思考模式忽略 `temperature`/`top_p`：当前代码 `temperature: 0.2` 实际无效 | 已识别，不影响行为，建议下次清理 |
| U6 | 思考模式 + tool calls 多轮拼接需要回传 `reasoning_content`；当前未启用 tool calls，与本次无关，但若走 strict function calling 必须实现 | 待 C 阶段处理 |
| U7 | 调试文件 `ai_response_debug_*.txt` 写入仓库根目录（[llm_engine.py:258](../src/agent_analysis/llm_engine.py#L258), [llm_engine.py:276](../src/agent_analysis/llm_engine.py#L276)），容易污染工作树 | 已在 `.gitignore` 增加 `ai_response_debug_*.txt` |
| U8 | 其它 stage（thesis / critic / final / reviser）也走相同 `_run_stage` 框架，长 JSON 单次输出在它们身上同样可能破损 | Fix 2 的反馈强化对所有 stage 生效，但 schema 锚点（Fix 3 类型）只在 bridge prompt 加了 |

## 8. 下一步建议（按优先级）

### 阶段 C（强约束，3–5 天，**强推荐**）

把 `BridgeMemo` 改造为 **Strict Function Calling tool**：

1. 注册名为 `emit_bridge_memo` 的 strict tool，`tool_choice` 强制必选
2. schema 改造：
   - `BridgeMemo` / `TypedConflict` / `ResonanceChain` / `TransmissionPath` 等的 `model_config = {"extra": "allow"}` 删除（strict 要求 `additionalProperties:false`）
   - `Optional[str]` 字段改为带默认值的 required（如 `mechanism: str = ""`）
   - `Field(..., max_length=300)` 等保留为 Pydantic 业务校验，**不进 JSON Schema**
   - 用 `$ref/$def` 复用 `Layer` / `Confidence` / `ConflictSeverity` 枚举
3. 思考模式保留：reasoning_content 不变，最终结构化结果走 `tool_call.arguments`，**服务端保证 schema 命中**
4. 多轮调用必须回传 `reasoning_content`（参考 [tool_calls 文档](https://api-docs.deepseek.com/zh-cn/guides/tool_calls)）

**先在 bridge stage 单点 PoC**，跑 3–5 个真实 run，对比叙述质量后再决定是否扩散到 thesis/critic/final。

### 阶段 D（结构拆分，按需）

若 C 阶段仍有偶发失败，把 bridge 单次输出拆成 3 次顺序 strict tool call：

1. typed_conflicts（输入：layer cards）
2. resonance_chains（输入：layer cards + typed_conflicts）
3. transmission_paths（输入：以上全部）
4. 顶层汇总：`implication_for_ndx` / `unresolved_questions` / `event_refs` / `key_uncertainties`

**收益**：每次输出短得多，语法错率几何级下降；每次专注子任务，思考深度可能反而提高。
**风险**：可能损失"全局 synthesize"——但 typed_conflicts 输入已有全部 layer cards，全局视角不会丢。

### 阶段 E（基础设施清理，零质量风险）

1. `.gitignore` 增加 `ai_response_debug_*.txt` 与 `output/logs/control_service/*.json`（未跟踪文件污染工作树）
2. `_call_ai` 中 `temperature: 0.2` 在思考模式下无效，建议显式条件化：思考模式不传 temperature
3. `max_node_retries` 从 2 提到 3：DeepSeek 缓存命中价格已降到 1/10，重试若 prompt 不变，缓存命中率应极高，重试成本接近零
4. `prompt 减负`：`packet.event_refs` 在 prompt 里压缩为 `[(event_id, title, layers)]` 三元组列表

## 9. 关键代码位置速查（给 AI 审阅者）

| 主题 | 文件 | 关键 anchors |
|---|---|---|
| BridgeMemo schema | [contracts.py:497–572](../src/agent_analysis/contracts.py#L497-L572) | `event_refs: List[str]` 在 569 行 |
| AnalysisPacket.event_refs（输入形态） | [contracts.py:1078](../src/agent_analysis/contracts.py#L1078) | `Dict[str, Dict[str, Any]]` |
| `_run_bridge` | [orchestrator.py:245–264](../src/agent_analysis/orchestrator.py#L245-L264) | 把 `packet.event_refs` 灌进 payload 在 259 行 |
| `_run_stage` 重试 | [orchestrator.py:689–776](../src/agent_analysis/orchestrator.py#L689-L776) | parse_error 在 724–743，schema_error 在 738–751 |
| `_normalize_payload` bridge 分支 | [orchestrator.py:1249–1276](../src/agent_analysis/orchestrator.py#L1249-L1276) | 顶层 event_refs 兜底在末尾 |
| `_coerce_event_refs_list` helper | [orchestrator.py:1492 附近](../src/agent_analysis/orchestrator.py) | 新增 |
| `_compose_bridge_prompt` 强约束段 | [orchestrator.py:1112 附近](../src/agent_analysis/orchestrator.py) | 末尾 |
| DeepSeek client init + base_url 提升 | [llm_engine.py:59–104](../src/agent_analysis/llm_engine.py#L59-L104) | `_promote_deepseek_base_url` |
| JSON Output 调用约束 | [llm_engine.py:105–145](../src/agent_analysis/llm_engine.py#L105-L145) | 保留 `response_format=json_object`，不发送 `prefix` |
| `_light_repair_json`（容错过弱） | [llm_engine.py:287–312](../src/agent_analysis/llm_engine.py#L287-L312) | 仅修两类微错 |
| Bridge prompt 文件 | [prompts/cross_layer_bridge.md](../src/agent_analysis/prompts/cross_layer_bridge.md) | 业务约束 |

## 10. 审阅检查表（给后续 AI/工程师）

- [ ] Fix 1：dict / list[dict] / scalar / None 四种 event_refs 输入均能 normalize，且不会 stringify 整个 dict 当 ref
- [ ] Fix 2：parse_error 反馈包含响应末尾且不超过 1500 字符上限（避免反馈本身超长）
- [ ] Fix 3：bridge prompt 三个新断言（`BridgeMemo.event_refs` / `List[str]` / `["event:`）都在 contract 字符串内
- [ ] B-1：默认 URL → /beta；显式 /beta → 不重复升级；自定义 endpoint → 不动
- [ ] B-2：JSON Output 路径不发送 `prefix: true`，避免 DeepSeek 400；custom endpoint 也不发送 prefix
- [ ] 思考模式参数：`reasoning_effort: high` + `extra_body={"thinking":{"type":"enabled"}}` 在 v4 模型下保留
- [ ] `response_format={"type":"json_object"}` 仍传给 DeepSeek，且不与 prefix completion 组合
- [ ] 全量 pytest 138 passed（AI 审阅后）
- [ ] CLAUDE.md 硬规则未触碰：L1–L5 隔离 / 高严重度冲突保留 / legacy_adapter 边界
- [ ] 真实 run 已执行：`output/analysis/vnext/20260510_191820/`，bridge 一次通过
