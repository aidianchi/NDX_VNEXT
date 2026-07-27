# Thesis / Counter-Thesis 输入瘦身方案

- 日期：2026-07-25
- 施工者：Sonnet worker（受主对话委托，两阶段任务：先方案后实施）
- 触发：`output/analysis/vnext/20260725_145833/final_adjudication.json` 的 `token_usage` —— thesis 读入 278,764 prompt tokens，counter_thesis 读入 282,286，两站合计占全跑总读入（1,250,568）的 44.9%
- 范围边界：只改"喂给模型看什么"，不改 `_validate_stage_evidence_refs` 校验逻辑本身，不改 counter_thesis 的独立性边界（`forbidden_context_refs`），不碰 `thesis_builder.md` / `counter_thesis.md` 的合约纪律段落
- 结论：方案预估达标（单站 70%+ 读入量下降，远超 30% 门槛），且没有高风险字段被砍 —— **已进入阶段二并完成实施**

---

## 一、方法：用真实 run 数据实测，不拍脑袋

用 `output/analysis/vnext/20260725_145833/synthesis_packet.json`（真实 run 产物，被前述真实结算单引用的同一次 run）做实测抓取，逐字段统计序列化后的字符数占比作为 token 消耗的代理指标（两者高度线性相关；本文档不使用第三方 tokenizer，因为本机 venv 没装 `tiktoken`，字符数是可复现、可审计的度量，且能直接解释"before/after 差多少"）。

同时对照读了：
- `src/agent_analysis/prompts/thesis_builder.md`（350 行）—— "## 输入" 一节明确列出 thesis 的"重点字段"清单，另有"对竞争假说的强制回应"一节明确要求 `competing_hypotheses`
- `src/agent_analysis/prompts/counter_thesis.md`（88 行）—— "## 输入边界" 一节明确列出 counter_thesis 允许读取的 5 个 payload 顶层 key
- `orchestrator.py` 的 `_run_thesis`、`_counter_thesis_prompt_payload`、`_build_governance_input_packet`（治理站的窄输入参照范式）、`_build_synthesis_packet`（evidence_index 的构建源头）
- `contracts.py` 的 `SynthesisPacket`、`GovernanceInputPacket` 两个 contract 类定义

---

## 二、核心发现：瓶颈不在 SynthesisPacket 的顶层字段，在 `evidence_index` 内部

对真实 `synthesis_packet.json`（总大小 518,813 字符）逐顶层字段测量：

| 顶层字段 | 字符数 | 占比 |
|---|---:|---:|
| `evidence_index` | 480,246 | **92.57%** |
| `bridge_summaries` | 13,336 | 2.57% |
| `layer_summaries` | 11,815 | 2.28% |
| `competing_hypotheses` | 3,341 | 0.64% |
| `high_severity_typed_conflicts` | 2,020 | 0.39% |
| `principal_contradictions` | 1,553 | 0.30% |
| `packet_meta` | 1,385 | 0.27% |
| `objective_firewall_summary` | 735 | 0.14% |
| `synthesis_guidance` | 827 | 0.16% |
| `hypothesis_competition_summary` | 933 | 0.18% |
| `high_severity_conflicts` | 961 | 0.19% |
| `evidence_registry_summary` | 381 | 0.07% |
| `adjudication_history` | 480 | 0.09% |
| `counter_thesis_boundary` | 236 | 0.05% |
| `context_summary` | 99 | 0.02% |
| `event_index` | 2 | 0.00% |
| `generated_at` | 29 | 0.01% |

**结论一**：如果只在 SynthesisPacket 顶层做"字段级砍减"（brief 里举的例子，也是 counter_thesis 现有 pop 逻辑的做法），理论上限是 7.4%（除 evidence_index 外全部字段之和），远够不到 30% 门槛。真正的杠杆必须动 `evidence_index` 内部。

继续下钻 `evidence_index`（94 条 ref，平均每条 5,071 字符）：按条目大小排序，前 6 条就吃掉 389,724 字符（占 evidence_index 的 81.8%）：

| evidence_ref | 字符数 |
|---|---:|
| `L2.get_vix_term_structure#percentile_context` | 228,941 |
| `L4.get_ndx_earnings_revision_metrics#slope_30d` | 55,392 |
| `L4.get_ndx_earnings_revision_metrics#slope_90d` | 54,930 |
| `L4.get_ndx_earnings_revision_metrics#breadth_30d` | 23,895 |
| `L4.get_ndx_earnings_revision_metrics#dispersion_ntm` | 18,280 |
| `L4.get_ndx_earnings_revision_metrics#analyst_coverage` | 8,286 |

逐条打开检查内容，发现统一模式：每条 `evidence_index` 记录的 `field_value` 里，除了 `value` / `unit` / `coverage` / `windows` / `winsorized_weight_pct` / `flagged_weight_pct` 等**聚合统计字段**（叙事推理真正需要的东西）之外，还原样内嵌了一份**审计级全量明细**：

- `L2.get_vix_term_structure#percentile_context.field_value.raw_series`：2,508 条原始日频数据点（VIX3M/VIX 比值近 10 年序列），用途是"足以独立重算 windows.5y / windows.10y 两个分位"（`raw_series_window_note` 原话）——这是给审计和独立重算用的，不是给叙事引用用的。
- `L4.get_ndx_earnings_revision_metrics#slope_30d/#slope_90d.field_value.constituents/flagged/invalid`：90+ 只 NDX 成分股逐票明细（ticker、weight_pct、slope、fiscal_year_end、anchor_date……），是刚落地的"全成分" 盈利修正数据（commit `3c6baad`）的逐票审计底稿。
- `#breadth_30d.field_value.periods.{0y,+1y}.constituents`、`#dispersion_ntm.field_value.constituents`、`#analyst_coverage.field_value.constituents`：同类逐票明细。

**结论二**：这些逐票 / 逐日明细在 evidence_index 的引用体系里**不可能被合法引用**——合法 sub-ref 只到 `parent#field_name` 一层（如 `L4.get_ndx_earnings_revision_metrics#slope_30d`），不存在 `#slope_30d#NVDA` 这种再下钻一层的 ref。thesis_builder.md 和 counter_thesis.md 都只要求模型引用到 `#field_name` 这一级，从未要求、也没有合法引用路径能让模型精确指到某一只股票或某一天。换句话说：**这部分内容模型看了也用不上、用了也不合法**，是货真价实的审计专用材料，被 `_build_synthesis_packet`（`orchestrator.py:3947` 一带，`"field_value": value.get(field)` 原样整体转储）无差别地和聚合统计一起塞进了 evidence_index。

---

## 三、逐字段判定表（brief 要求的"候选删除 / 高风险不能动 / 保守保留"三分类）

### 高风险，不能动（哪怕看起来冗余也不碰）

| 字段 | 理由 |
|---|---|
| `evidence_index` 的 **ref key 集合**（含 `#field` 子 ref） | 两站的证据引用合法性校验（`_validate_stage_evidence_refs`、counter_thesis 的 `allowed_evidence_refs`）逐字比对 key 是否存在；砍掉任何一个 key 都会让本该合法的引用被打回。方案**不删除任何 key**，只压缩 value 里的超长嵌套明细。 |
| `evidence_index` 每条记录的**聚合字段**（`value`/`unit`/`coverage`/`windows`/`winsorized_weight_pct`/`flagged_weight_pct`/`availability`/`material`/`verification_status` 等） | 这是叙事推理和引用真正依赖的内容，逐条核对后确认全部原样保留。 |
| `competing_hypotheses` | thesis_builder.md"对竞争假说的强制回应"一节明确要求逐一回应每个 candidate 假说；counter_thesis 已经出于"自我循环"原因排除（它是 counter_thesis 自己参与产出的竞争结果），维持现状。 |
| `high_severity_conflicts` / `high_severity_typed_conflicts` / `principal_contradictions` | CLAUDE.md"冲突是资产"边界；thesis_builder.md 明确列为重点输入字段，且 Step 2"抓主要矛盾"直接依赖它们。 |
| `objective_firewall_summary` | thesis_builder.md 重点字段清单列出；强结论前的越权与证据检查，属于"指标不越权"边界的执行机制。 |
| counter_thesis 的 `forbidden_context_refs` / `allowed_evidence_refs` / 独立性边界文案 | 本次任务明确禁止改动，且这是另一批工作里刚加固过的反事故机制，未做任何触碰。 |

### 候选删除 / 已删除（说明书从未要求过，判定为纯冗余）

| 字段 | 说明书要求过吗 | 判定 |
|---|---|---|
| `hypothesis_competition_summary` | thesis_builder.md 未提；counter_thesis.md 未提（且 counter_thesis 早已 pop 掉） | thesis 侧新增剔除（只在喂给模型的 prompt 层剔除，见下方"实施方式"） |
| `adjudication_history` | 同上未提 | 同上剔除 |
| `counter_thesis_boundary` | 同上未提 | 同上剔除 |
| `evidence_registry_summary` | 两份说明书都没提；`contracts.py` 里明确标注"阶段 4：统一 Evidence Passport 注册表摘要"，且 `_build_governance_input_packet`（`orchestrator.py`）明确把它单独接给 Critic/Risk/Reviser/Final 四个治理站，是给治理阶段用的字段，不是给 thesis/counter_thesis 用的 | thesis、counter_thesis 两侧都剔除 |
| `evidence_index` 内部的逐票/逐日审计明细（`raw_series`、`constituents`、`flagged`、`invalid` 等） | 见"结论二"：不存在合法引用路径能指到这一层 | 压缩为 `{count, sample(前2+末1), note}`，ref key 和聚合字段保持 100% 不变 |

### 保守保留（有一定冗余嫌疑，但本轮不动）

| 字段 | 冗余嫌疑 | 为什么不动 |
|---|---|---|
| counter_thesis 的 `synthesis_packet_without_self_reference.bridge_summaries` 与同一 payload 里独立算出的 `bridge_v1_structure` | `bridge_v1_structure` 是从 `bridge_summaries` 里过滤出的 `bridge_type != feedback_bridge_v2` 子集（`[:1]`），存在部分重复 | counter_thesis.md"输入边界"把 `synthesis_packet_without_self_reference` 整体列为允许读取项，没有把 `bridge_summaries` 排除在外；且 `bridge_summaries` 里的 `typed_conflicts`/`resonance_chains`/`transmission_paths` 比顶层 `high_severity_typed_conflicts` 更细，贸然砍有丢失冲突资产的风险。相对 evidence_index 的量级（13,336 字符 vs 480,246 字符），性价比低，本轮不碰，留作后续可选项。 |
| `packet_meta` | 含 `object_run_gate`（对象定义、日期边界）——thesis 已有既存机制 `_slim_object_run_gate_for_prompt` 做部分精简，counter_thesis 没有对等处理 | `object_run_gate` 是"判断对象是什么"这一层的边界声明，属于层间隔离/对象定义的基础设施，体量本来就小（1,385 字符，占比 0.27%），动它的收益和风险不成比例，本轮不碰，只记录这个不对称留作后续观察。 |
| `context_summary` / `generated_at` | 几乎没有冗余嫌疑 | 体量太小（99 字符、29 字符），不值得为不到 0.03% 的字符占比引入额外改动面。 |

---

## 四、预估瘦身后 token/字符量对比（真实数据估算）

用真实 run 的三份产物（`synthesis_packet.json`、`bridge_memos/bridge_v2.json`、`investigation_reports/*.json`）完整复现 `_run_thesis` 和 `_counter_thesis_prompt_payload` 现在的 payload 构造逻辑（"改前"），以及叠加本方案的 evidence_index 压缩 + 顶层字段剔除后的等价构造（"改后"），实测序列化字符数：

| 站点 | 改前（字符） | 改后（字符） | 降幅 |
|---|---:|---:|---:|
| thesis payload（`{"synthesis_packet": ...}`） | 518,835 | 142,374 | **72.6%** |
| counter_thesis payload（含 `bridge_v1_structure`/`bridge_v2_feedback_summary`/`non_stub_investigation_reports`/`allowed_evidence_refs` 等全部顶层 key） | 534,150 | 159,429 | **70.2%** |

`evidence_index` 单独看：480,246 → 105,937 字符，降幅 77.9%（94 条 ref 中，长明细超过阈值的约 12 条被压缩，其余 82 条本来就不含超长嵌套列表，原样保留）。

字符数是 token 数的可复现代理指标，不是精确 token 计数（本机没有 `tiktoken`）。但降幅量级（70%+）远超 brief 设定的"30% 才值得动手"门槛一倍以上，且瘦身对象高度集中在几个明确无合法引用路径的审计字段上，方向判断不依赖精确 token 数字。

---

## 五、自我检查：是否满足两条硬门槛

1. **不丢证据可追溯性**：
   - `evidence_index` 的 ref key 集合（含全部 `#field` 子 ref）100% 不变，两站能合法引用的范围没有任何缩小。
   - 每条记录的聚合统计字段（模型写叙事、判断置信度、给出 `windows`/`coverage`/`flagged_weight_pct` 等结论时真正用得到的东西）100% 保留。
   - 被压缩的只是"逐票 / 逐日审计明细"——这部分内容本来就没有合法的 sub-ref 能让模型引用到，压缩前后模型的"能说什么"没有变化。
   - 完整明细继续 100% 保留在持久化的 `synthesis_packet.json`、`evidence_registry.json` 里（构造 payload 用的原始 `SynthesisPacket` 对象和 checkpoint 比对用的 `expected_payload` 完全不受影响，只有最终序列化进 LLM prompt 文本的那一步被压缩），审计、复核、独立重算的入口没有被关闭。
   - 结论：满足。

2. **不破坏层间隔离**：
   - 没有给 thesis / counter_thesis 增加任何新的跨层运行时数据、其他层摘要或结论；只是压缩了已经在两站输入范围内的 evidence_index 明细体量。
   - counter_thesis 的独立性边界（`forbidden_context_refs`、"自我循环"字段排除）完全未改动。
   - `packet_meta.object_run_gate`（对象定义边界）本轮未改动。
   - 结论：满足。

---

## 六、实施方式（阶段二，已完成）

### 为什么改 `_sanitize_prompt_payload` 而不是直接改 `_run_thesis` / `_counter_thesis_prompt_payload` 的返回值

brief 允许两种实现方式，由施工者判断哪种更贴近现有代码风格。读代码时发现 `orchestrator.py` 已经存在一个专门的"prompt 序列化前最后一步瘦身"机制：`_sanitize_prompt_payload(stage_key, payload)`，由 `_compose_prompt` 在拼真正发给 LLM 的文本之前调用，thesis 站点已经在用它做 `object_run_gate` 精简（`_slim_object_run_gate_for_prompt`）。这是比"直接改payload 构造函数"更贴近现有架构的插入点，原因：

- **职责分离清楚**：`_run_thesis` / `_counter_thesis_prompt_payload` 构造出的完整 payload 继续被用于 checkpoint 续跑比对（`_load_stage_checkpoint(expected_payload=...)`）、`_record_stage_artifact`（落盘的 stage 输入审计）、counter_thesis 自己的独立性审计（`_counter_thesis_prompt_input_audit`）——这些都应该看到"这一轮实际收到的完整上游输入"，不应该因为 prompt 瘦身而失真。只在 `_sanitize_prompt_payload` 这一步动手，上述审计路径全部保持完整保真，只有真正塞进 LLM 文本、写入 `prompt_audit/*.payload.json` 的那一份是瘦身后的版本（而且 `prompt_audit` 记录的正是"模型实际看到了什么"，如实反映，不是隐藏）。
- **不触碰独立性边界代码**：`_counter_thesis_prompt_payload` 里已有的 4 个 pop（`competing_hypotheses` 等，服务于"自我循环排除"这一硬边界）完全没有改动，新增的裁剪只发生在下游的 `_sanitize_prompt_payload`。
- **不影响 checkpoint 续跑行为**：已有 run 的 checkpoint 命中逻辑不受影响（比对用的还是老的完整 payload 结构）。

### 具体改动

`src/agent_analysis/orchestrator.py`：

1. 新增两个模块级常量：
   - `EVIDENCE_FIELD_LIST_PROMPT_COUNT_THRESHOLD = 8`、`EVIDENCE_FIELD_LIST_PROMPT_CHAR_THRESHOLD = 800` —— evidence_index 里超过这个条数且序列化后超过这个字符数的嵌套列表才判定为"审计明细"，做压缩。
   - `NARRATIVE_STAGE_PROMPT_DROP_FIELDS` —— 记录 thesis / counter_thesis 各自要在 prompt 层丢弃的顶层字段集合。
2. 新增 `_slim_evidence_index_for_prompt(payload, synthesis_key)`：定位 payload 里嵌套的 synthesis 字典（thesis 用 `synthesis_packet`，counter_thesis 用 `synthesis_packet_without_self_reference`），对其中 `evidence_index` 的每条记录的 `field_value` 做递归压缩，ref key 和非超长字段一律原样保留。
3. 新增 `_drop_low_value_synthesis_fields_for_prompt(payload, synthesis_key, drop_fields)`：按 `NARRATIVE_STAGE_PROMPT_DROP_FIELDS` 剔除对应站点的顶层冗余字段。
4. 修改 `_sanitize_prompt_payload`：`stage_key == "thesis"` 分支叠加调用上述两个新函数；新增 `stage_key == "counter_thesis"` 分支（此前 counter_thesis 没有走任何瘦身，直接透传）。

### 验证

- 新增单测（`tests/test_vnext_orchestrator.py`）：用真实结构的 mini synthesis_packet 断言——
  - 大列表（>8 条且 >800 字符）被压缩为 `{_prompt_summary, count, sample, note}`，小列表原样保留；
  - `evidence_index` 压缩前后 ref key 集合完全一致（含 `#field` 子 ref）；
  - 聚合字段（`value`/`coverage` 等）压缩后仍然存在且值不变；
  - thesis 输出里 `hypothesis_competition_summary`/`adjudication_history`/`counter_thesis_boundary`/`evidence_registry_summary` 被剔除，而 `competing_hypotheses`/`layer_summaries`/`high_severity_typed_conflicts`/`principal_contradictions`/`objective_firewall_summary`/`synthesis_guidance` 保留；
  - counter_thesis 输出里 `evidence_registry_summary` 被剔除，`allowed_evidence_refs`/`forbidden_context_refs`/`bridge_v1_structure`/`bridge_v2_feedback_summary`/`non_stub_investigation_reports` 不受影响；
  - 端到端用 FakeLLMEngine 跑一次 `_run_thesis`，确认 stage 仍能正常产出并通过既有 validator。
- 全量 `.venv/bin/python -m pytest --cache-clear -q` 跑绿（结果见 WORK_LOG 风格的交付简报）。
