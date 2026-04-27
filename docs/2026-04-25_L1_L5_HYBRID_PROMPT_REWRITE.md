# L1-L5 Hybrid Prompt Rewrite Implementation

日期：2026-04-25

## 目标

根据 `2026-04-25_L1_OLD_VS_NEW_FULL_COMPARISON.md` 的结论，把 L1-L5 从纯 context-transform prompt 改为：

> Context-bounded professional analyst

核心原则：

- context boundary 负责隔离输入，不让 Layer 提前看到其他层状态。
- professional lens 负责保留顶级金融专家的分析语感和判断优先级。
- v2 schema 负责强制指标级叙事、推理链、层内综合、质量自检。
- UI quality 负责确保 L1-L5 未来可单独展示。

## 已修改文件

- `src/agent_analysis/prompts/l1_analyst.md`
- `src/agent_analysis/prompts/l2_analyst.md`
- `src/agent_analysis/prompts/l3_analyst.md`
- `src/agent_analysis/prompts/l4_analyst.md`
- `src/agent_analysis/prompts/l5_analyst.md`
- `src/agent_analysis/orchestrator.py`

## Prompt 改写方式

每个 Layer 统一采用以下结构：

1. `Context Boundary`: 明确本层只能接收本层上下文，不得引用其他层当前状态。
2. `Professional Lens`: 恢复顶级专业分析师镜头。
3. `Cognitive Transform`: 固定为 raw indicators -> indicator_analyses -> layer_synthesis -> internal_conflict_analysis -> cross_layer_hooks。
4. `Indicator Semantics`: 每层列出 function_id 的金融语义。
5. `Mechanism Grammar`: 强制指标进入因果链。
6. `Layer Synthesis`: 要求可作为 UI 独立摘要展示。
7. `Internal Conflict Analysis`: 要求像投研讨论，而不是 checklist。
8. `Cross-Layer Hooks`: 每层定义必问对象和条件触发对象。
9. `UI Quality Requirements`: 明确 narrative、reasoning、synthesis、internal conflict 的展示标准。
10. `Output Discipline`: 保持 JSON、覆盖、不可越权、不可给最终买卖建议。

同时，orchestrator 注入的通用合约已从：

> Context-First Layer Contract / 不是扮演某个职位

改为：

> Context-Bounded Professional Layer Contract / 角色是专业认知镜头，context boundary 是信息隔离边界

## 验证结果

### 单元测试

命令：

```powershell
C:\ndx_vnext\.venv\Scripts\python.exe -m pytest -q
```

结果：

```text
7 passed
```

### Prompt Inspection

目录：

`output/experiments/_prompt_inspect_hybrid_l1_l5`

结果：

| Layer | Context Keys | Cross Signals | Negative Role Wording |
|---|---|---:|---|
| L1 | L1 | 0 | false |
| L2 | L2 | 0 | false |
| L3 | L3 | 0 | false |
| L4 | L4 | 0 | false |
| L5 | L5 | 0 | false |

### DeepSeek Full Smoke

命令：

```powershell
C:\ndx_vnext\.venv\Scripts\python.exe C:\ndx_vnext\src\main.py --data-json C:\ndx_vnext\output\data\data_collected_v9_live.json --skip-report --disable-charts
```

Run 目录：

`output/analysis/vnext/20260425_105237`

模型：

- `deepseek-v4-flash`
- `deepseek-v4-pro` fallback

结果：

- `schema_guard_report.passed = true`
- `final_stance = 中性偏谨慎`
- `approval_status = approved_with_reservations`
- `evidence_index = 34`

Layer 输出检查：

| Layer | indicator_analyses | layer_synthesis chars | internal_conflict chars | hooks |
|---|---:|---:|---:|---|
| L1 | 8 | 351 | 285 | L4, L2, L5 |
| L2 | 9 | 296 | 334 | L4, L3, L5 |
| L3 | 6 | 394 | 394 | L5, L4, L2 |
| L4 | 2 | 201 | 209 | L1, L2, L5 |
| L5 | 9 | 292 | 318 | L3, L4, L2 |

说明：

- L3 的 `quality_self_check.coverage_complete = false` 是因为它诚实标注广度数据缺失；实际 `indicator_analyses` 已覆盖 6/6 个 L3 指标，SchemaGuard 通过。
- Reviser 第一次因 `environment_assessment` 超过 300 字触发重试，第二次成功。这说明后续应考虑放宽 ThesisDraft 的短字段长度，或在 Reviser prompt 中更明确压缩字段长度。

### HTML Report

已用本次 `logic_vnext.json` 生成 legacy HTML：

`output/reports/ndx_report_v9_20260425_105806.html`

## 当前结论

Hybrid prompt 方向成立：

- 层级隔离保持干净。
- 专业角色感恢复。
- 每层均产出足够长的 `layer_synthesis` 和 `internal_conflict_analysis`。
- Cross-layer hooks 更完整，尤其 L1/L2/L3/L4/L5 都按条件触发了第三个验证对象。
- Legacy adapter 和 HTML 报告链路可继续消费。

## 后续建议

1. 把同样的 hybrid 原则扩展到 Bridge 和 Thesis prompt，但不要让 Bridge 拆成多个 API 调用。
2. 为 L2、L3、L4、L5 补齐更多 function_id 级 4C few-shot，当前 few-shot 覆盖仍明显不足。
3. 处理 Reviser/Thesis 字段长度风险，避免长 synthesis 进入短字段后触发重试。
4. 下一轮重点不是继续改 L1-L5，而是让 Bridge 更好消费五层的 `indicator_analyses`，生成更强的冲突/共振图。
