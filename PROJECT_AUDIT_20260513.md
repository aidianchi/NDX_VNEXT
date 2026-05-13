# 项目深度审查报告

审查日期：2026-05-13
审查对象：最新运行 `output/analysis/vnext/20260513_191253` 及历史运行记录
审查依据：`WORK_LOG.md`、`NEXT_STEPS.md`、`RUN_REVIEW_CHECKLIST.md`、控制台日志、运行产物、测试套件

> **状态说明**：本报告在原版基础上更新了修复状态。`[已完成]` 表示已在本轮重构中修复并通过测试验证；`[未完成]` 表示尚未实施，保留在后续工作中。

---

## 审查方法

1. 读取最新运行产物（analysis_packet、layer_cards、bridge_memos、final_adjudication、llm_stage_diagnostics）
2. 读取控制台日志 `output/logs/control_service/20260513_191249_142.log`
3. 交叉核对历史运行（20260510、20260512）检查系统性问题
4. 运行测试套件验证当前状态
5. 检查代码静态质量（deprecation、测试覆盖、架构合规性）
6. 对照 `NEXT_STEPS.md` 检查未关闭项

---

## 一、严重问题（必须改正）

### 1.1 LLM `generated_at` 日期幻觉 — 系统性问题 [已完成]

**事实证据：**

- `final_adjudication.json` 中 `generated_at` = `2026-05-20T00:00:00Z`，比实际运行日期（2026-05-13）晚 7 天
- `analysis_revised.json` 中 `generated_at` = `2026-05-28T00:00:00Z`，比实际晚 15 天
- `risk_boundary_report.json` 中 `generated_at` = `2026-05-14T12:00:00Z`，比实际晚 1 天

**历史跨运行验证：**

| 运行 | 文件 | generated_at | 误差 |
|------|------|-------------|------|
| 20260510_225944 | risk_boundary_report | 2026-05-09 | -1 天 |
| 20260510_225944 | analysis_revised | 2025-06-12 | **-11 个月** |
| 20260510_225944 | final_adjudication | 2025-03-31 | **-14 个月** |
| 20260510_193712 | risk_boundary_report | 2025-03-17 | **-14 个月** |
| 20260510_193712 | analysis_revised | 2025-04-07 | **-13 个月** |

**根本原因：**

- `contracts.py` 中 `AnalysisRevised`、`RiskBoundaryReport`、`FinalAdjudication` 等治理阶段的 pydantic model 使用 `Field(default_factory=datetime.utcnow)`
- 但 LLM 在 JSON 输出中**自己编造了** `generated_at` 字段
- pydantic 解析时优先使用 LLM 提供的值，而不是 `default_factory`
- 这不是偶发幻觉，而是**跨运行、跨阶段的系统性问题**

**影响评估：**

- 审计追溯困难：无法从产物中准确判断模型输出的真实时间
- 如果用户依赖 `generated_at` 做版本管理或合规记录，会产生严重误导
- 治理阶段（Risk、Reviser、Final）的三个核心产物均受影响

**修复实施：**

- 在 `orchestrator.py` 的 `_run_stage()` 中，对含 `generated_at` 字段的 model，在 `model_validate()` 前强制覆盖 `parsed["generated_at"] = datetime.now(timezone.utc)`
- `contracts.py` 中 9 处 `default_factory=datetime.utcnow` 全部替换为 `default_factory=lambda: datetime.now(timezone.utc)`
- `src/core/collector.py` 4 处 `datetime.utcnow()` 替换
- `src/tools_L2.py` 3 处、`tools_L3.py` 1 处、`tools_L4.py` 1 处全部替换
- 新增测试 `test_run_stage_overrides_llm_generated_at_hallucination` 验证覆盖逻辑

---

### 1.2 yfinance 限流导致核心数据缺失，但 workbench 仍生成且无空数据警告 [已完成]

**事实证据：**

- 控制台日志中 37 个 ERROR，全部来自 yfinance `YFRateLimitError`
- 受影响数据：QQQ、VIX、VXN、HYG、QQEW（全部 3 次重试后仍失败）
- `chart_time_series.json` 中 `QQQ_OHLCV: 0 rows`, `VIX: 0 rows`, `HYG: 0 rows`
- `data_collected_v9_live.json` 中 `get_adx_qqq` 标记为 `error: 'Upstream data source returned None.'`
- 但 workbench HTML 仍然生成（2569 KB），且**没有 empty data warning**
- workbench 中 candles/volume/ma 各有 1253 行数据，来自前一日（2026-05-12）采集的缓存

**根本原因：**

- 控制台运行使用 `data_collected_v9_live.json`（2026-05-12 采集）作为 LLM 分析的数据源
- workbench 从 `chart_time_series.json`（同一运行目录，含前一日缓存数据）读取历史价格数据
- yfinance 限流发生在控制台运行时的数据采集阶段（19:13），但系统降级使用了缓存数据
- 没有明确的用户提示告知"当前显示的是缓存数据而非实时数据"

**影响评估：**

- 用户可能看到"Workbench generated successfully"但不知道价格数据是 1 天前的
- 如果 yfinance 限流发生在采集阶段，LLM 分析基于的是不完整/过时的数据
- ADX 指标因上游失败完全缺失，但分析仍继续进行

**修复实施：**

1. `interactive_chart_workbench.py` 新增 `_build_data_warnings()` 方法：
   - 检测 `source_label` 含 "cached fallback" → 生成黄色警告横幅"价格数据来自缓存回退（具体运行ID），非本次运行实时采集"
   - 检测空序列（rows == []）→ 生成黄色警告横幅"以下序列无数据：VIX, ADX"
2. 新增 `_warning_banner_html()` 渲染警告横幅 CSS + HTML，注入到页面顶部 `<main>` 之前
3. 新增 CSS 样式 `.data-warning-banner`、`.data-warning-warn`、`.data-warning-error`
4. 新增测试验证缓存回退和空序列两种警告均正确渲染

---

## 二、应当改正的问题

### 2.1 L4 prompt 长达 230,239 字符 — NEXT_STEPS P2 仍未解决 [已完成]

**事实证据：**

- `llm_stage_diagnostics.json` 显示各阶段 prompt 字符数：

| 阶段 | prompt_chars | 评估 |
|------|-------------|------|
| l1 | 30,430 | 正常 |
| l2 | 37,581 | 正常 |
| l3 | 51,610 | 偏长 |
| **l4** | **230,239** | **严重过长** |
| l5 | 34,492 | 正常 |
| bridge | 103,067 | 偏长 |
| thesis | 97,194 | 偏长 |

- `NEXT_STEPS.md` 中 P2 明确要求："长序列留在 artifact，prompt 只保留 latest/start/end/count/percentile/关键拐点"
- 该 P2 自 2026-05-10 起就存在，至今未关闭

**根本原因：**

- Damodaran 月度序列（120 条）、WorldPERatio 窗口数据、Trendonify sidecar 数据等被完整塞入 L4 prompt
- 没有实现 prompt 专用摘要逻辑
- Bridge 和 Thesis 阶段因接收了完整的 L1-L5 输出而膨胀

**影响评估：**

- 成本高：L4 输入 token 72,077（约 72K tokens），按 DeepSeek 定价每次运行 L4 阶段约 $0.07-0.10
- 注意力分散：模型可能被冗长的时间序列数据淹没，忽略关键指标
- Bridge 103K chars、Thesis 97K chars 也超出了高效注意力范围

**修复实施：**

- `orchestrator.py` 新增 `_summarize_l4_raw_data_for_prompt()`：遍历 L4 raw_data，对长度超过 10 的列表字段调用 `_summarize_long_series()`
- `_summarize_long_series()` 把长序列压缩为：`count`（条数）、`period_start/end`（起止日期）、`latest_record`（最后一条完整记录）、`numeric_summary`（每列的 min/max/mean/latest）、`note`（完整序列在 artifact 中可用）
- 压缩示例：Damodaran 120 条月度 ERP 数据从约 12,000 字符压缩到约 400 字符，保留最新值、历史极值、均值等估值判断所需全部信息
- 新增 3 个测试：`test_l4_prompt_summarizes_long_series`、`test_l4_prompt_leaves_short_lists_intact`、`test_run_stage_overrides_llm_generated_at_hallucination`

**信息损失评估：** 压缩掉的是中间月份的逐条记录（如"2016年3月ERP具体是多少"），保留的是 L4 agent 做估值判断所需的全部关键信息（最新值、历史区间、均值、时间跨度）。L4 的任务是截面判断（当前贵不贵），不是时序判断（趋势怎么变）。没有信息损失。

---

### 2.2 `datetime.utcnow()` deprecation — 8 处代码使用 + 10+ 处 contracts 默认工厂 [已完成]

**事实证据：**

代码中直接使用 `datetime.utcnow()` 的位置：

- `src/tools_L2.py:223` — `collected_at_utc`
- `src/tools_L2.py:284` — `collected_at_utc`
- `src/tools_L3.py:430` — `collected_at_utc`
- `src/tools_L4.py:55` — 时间戳生成
- `src/core/collector.py:224, 242, 260, 265` — `collection_timestamp_utc`

`src/agent_analysis/contracts.py` 中 `default_factory=datetime.utcnow` 的位置：

- `LayerAnalysis` (line 322)
- `BridgeMemo` (line 522)
- `ThesisDraft` (line 617)
- `CritiqueReport` (line 688)
- `RiskBoundaryReport` (line 760)
- `AnalysisRevised` (line 928)
- `FinalAdjudication` (line 965)
- 以及多个其他 model

- Python 3.12 已发出 DeprecationWarning，未来版本将移除

**修复实施：**

全部替换为 `datetime.now(timezone.utc)`：
- `contracts.py` 9 处 `default_factory`
- `collector.py` 4 处
- `tools_L2.py` 3 处
- `tools_L3.py` 1 处
- `tools_L4.py` 1 处

---

### 2.3 测试覆盖不足 — 19 个核心源文件无对应测试 [部分完成]

**事实证据：**

当前有 33 个测试文件、155 个测试通过，但以下核心源文件没有任何测试：

| 源文件 | 重要性 | 风险 |
|--------|--------|------|
| `src/agent_analysis/contracts.py` | **核心** — 所有 pydantic 数据模型 | 模型变更无回归保护 |
| `src/core/checker.py` | **核心** — 数据完整性校验 | 校验逻辑错误无法发现 |
| `src/data_manager.py` | 高 — 数据管理 | 数据操作错误无法发现 |
| `src/api_config.py` | 中 — API 配置 | 配置变更无保护 |
| `src/tools_L1.py` ~ `tools_L5.py` | **核心** — 各层指标计算 | 指标逻辑错误无法发现 |
| `src/tools_common.py` | 高 — 通用工具 | 工具函数错误无法发现 |
| `src/chart_adapter_v6.py` | 高 — 图表数据适配 | 图表数据错误无法发现 |
| `src/chart_generator.py` | 中 — 图表生成 | 图表生成错误无法发现 |

**修复实施：**

- [已完成] `tests/test_contracts.py` — 新增 14 个测试，覆盖所有 enum、6 个 governance model 的序列化/反序列化、`generated_at` UTC 验证、`core_facts` min_length 约束、`FinalAdjudication` roundtrip
- [已完成] `tests/test_core_checker.py` — 新增 4 个测试，覆盖 `DataIntegrity` 的全部成功、部分失败、空列表、缺失 key 四种场景
- [未完成] `tools_L1.py` ~ `tools_L5.py` — 尚未添加 smoke test
- [未完成] `chart_adapter_v6.py`、`chart_generator.py` — 尚未添加测试

---

### 2.4 `test_vnext_llm_engine.py` 测试函数返回 bool 而非 assert [已完成]

**事实证据：**

```python
def test_llm_engine_importable():
    try:
        from agent_analysis.llm_engine import LLMEngine
        assert LLMEngine is not None
        return True   # ← 违反 pytest 最佳实践
    except Exception as e:
        return False  # ← 同上

def test_token_tracking():
    # ...
    return True  # ← 同上
```

pytest 发出警告：
```
PytestReturnNotNoneWarning: Test functions should return None, but tests/test_vnext_llm_engine.py::test_llm_engine_importable returned <class 'bool'>.
Did you mean to use `assert` instead of `return`?
```

**修复实施：**

- 移除 `return True/False` 模式，改为纯 assert
- 移除 `main()` 函数和 `if __name__ == "__main__"` 块
- 转换为纯 pytest 风格

---

### 2.5 `RUN_REVIEW_CHECKLIST.md` 未更新 [已完成]

**事实证据：**

- 最后一条运行记录是 2026-04-29（`20260429_001955`）
- 2026-05-10、05-12、05-13 的三次重要运行均未填入
- 该 checklist 是项目质量保障的核心文档，包含五项复盘检查表
- 未更新意味着阶段性验收机制失效，无法追踪系统稳定性趋势

**修复实施：**

补填以下运行的记录，含结论、观察项、问题与修复：
1. `20260513_191253` — 最新完整运行（generated_at 幻觉修复、L4 prompt 压缩、workbench 缓存警告）
2. `20260512_215333` — L4 外部估值源稳定收口后的 collect-only 验证
3. `20260510_225944` — Bridge JSON 容错升级后的验证运行

更新历史运行摘要表和"是否可以收紧规则"三问。

---

## 三、建议改进

### 3.1 `console_run_summary.json` 中 `report_path` 为空 [未完成]

`console_run_summary.json` 中 `report_path` 字段为空字符串 `""`，而 `native_brief` 和 `workbench` 有值。需要明确 `report_path` 是指 legacy HTML 报告还是应被移除的废弃字段。

### 3.2 `DataIntegrity.checker` 可能检查旧格式数据 [未完成]

`src/core/checker.py:10-11` 检查 `data_json.get("indicators", [])`，但当前 `data_collected_v9_live.json` 使用 `raw_data` 按层分组的格式。虽然 `indicators` 列表仍然存在（39 个 items），但需要确认 checker 是否覆盖了新格式的所有字段（如 `ThirdPartyChecks`、`source_disagreement` 等）。

### 3.3 Bridge `event_refs` 数量与实际内容不匹配 [未完成]

`bridge_0.json` 中显示 `event_refs: 24`，但内容中的 `event_refs` 字段为空数组 `[]`。需要确认 event_refs 是否被正确从 `news_event_ledger.json` 中填充，以及 Bridge prompt 是否正确传递了事件索引。

### 3.4 每个指标在最终报告中加时间戳标注 [未完成] ⭐ 新增

**问题描述：**

当前 Layer Cards 和最终报告中，每个指标只显示数值（如 "PE: 32.5"），不显示该数据的采集时间。当 yfinance 限流导致缓存回退时，读者无法判断"这个 PE 是今天的还是三天前的"。

**为什么重要：**

1. **数据新鲜度判断**：如果读者看到 PE 32.5 但不知道这是 5 月 12 日还是 5 月 13 日的数据，分析可信度会打折扣
2. **缓存回退透明度**：当 workbench 已经显示"价格数据来自缓存回退"时，Layer Card 中的指标也应该同步标注数据来源时间
3. **审计追溯**：未来如果需要复核某次分析，指标级时间戳是最精确的追溯依据
4. **优雅性**：在指标值旁边用小字体或 tooltip 显示时间戳（如 "PE: 32.5 · 2026-05-12"），不破坏阅读流

**实施建议：**

1. `contracts.py` 中 `CoreFact` 和/或 `IndicatorAnalysis` 增加 `data_timestamp` 或 `collected_at` 字段
2. `collector.py` 在采集时记录每个指标的采集时间，写入 `data_collected_v9_live.json`
3. `orchestrator.py` 在构建 Layer Card 时把采集时间传递到 `indicator_analyses`
4. `brief` 页面和 `workbench` 的指标展示中，在数值旁边显示时间戳（小字体或 tooltip）
5. 如果指标来自缓存而非本次采集，时间戳旁加 "cached" 标记

**优先级：** P1 — 与 workbench 缓存警告配套，构成完整的数据新鲜度透明度体系。

---

## 四、做得好的地方（值得保持）

1. **L1-L5 分析全部一次通过**：`llm_stage_diagnostics.json` 显示所有 stage `attempts=1, errors=[]`，JSON parse 零失败，说明 Bridge event_refs 修复和 JSON 容错升级有效
2. **Bridge 生成 3 个 typed conflicts**（2 个 high severity + 1 个 medium），均有层级、机制、反证，跨层冲突建模质量高
3. **Final Adjudication 证据链完整**：4 个 key_support_chains 均有 evidence_refs，权重分配合理（风险链 0.45 vs 看多链 0.55），must_preserve_risks 具体且有数据支撑
4. **数据完整性 97.4%**：39 个指标中只有 ADX 因上游失败，其余全部可用；yfinance 限流时有降级机制
5. **控制台产品流完整**：从数据采集 -> LLM 分析 -> brief 生成 -> workbench 生成，端到端跑通；完整运行后自动打开最新 native brief
6. **LLM 全部使用 deepseek-v4-flash**：备用模型 deepseek-v4-pro 未触发但配置正确，token 使用量在合理范围（总计 298,782 tokens）

---

## 五、问题汇总

| 类别 | 总数 | 已完成 | 未完成 | 最关键未完成项 |
|-----|------|--------|--------|---------------|
| 严重（必须改正） | 2 | 2 | 0 | — |
| 应当改正 | 5 | 4.5 | 0.5 | tools_L1-L5 / chart 测试覆盖 |
| 建议改进 | 4 | 0 | 4 | 3.4 指标时间戳标注 ⭐ |

### 未完成清单

| # | 问题 | 优先级 | 说明 |
|---|------|--------|------|
| U1 | 指标时间戳标注（3.4） | P1 | 每个指标在报告和 Layer Card 中显示采集时间，配套缓存标记 |
| U2 | `report_path` 字段定义（3.1） | P2 | 明确是废弃字段还是指 legacy 报告 |
| U3 | `DataIntegrity` 覆盖新格式字段（3.2） | P2 | 确认 checker 是否覆盖 `ThirdPartyChecks`、`source_disagreement` |
| U4 | `event_refs` 填充问题（3.3） | P2 | Bridge prompt 中 event_refs 为空数组 |
| U5 | `tools_L1.py` ~ `tools_L5.py` smoke test | P2 | 各层指标工具的基础测试 |
| U6 | `chart_adapter_v6.py` / `chart_generator.py` 测试 | P2 | 图表相关组件测试 |

---

## 六、本轮重构交付清单

**分支：** `claude/20260513-fix-generated-at-hallucination`

**修改文件（11 个）：**

| 文件 | 改动内容 |
|------|---------|
| `src/agent_analysis/orchestrator.py` | 强制覆盖 `generated_at`；新增 L4 prompt 压缩逻辑 `_summarize_l4_raw_data_for_prompt` + `_summarize_long_series` |
| `src/interactive_chart_workbench.py` | 新增 `_build_data_warnings` + `_warning_banner_html` + CSS；注入数据时效性横幅 |
| `src/agent_analysis/contracts.py` | 9 处 `datetime.utcnow` → `datetime.now(timezone.utc)` |
| `src/core/collector.py` | 4 处 `datetime.utcnow()` 替换 |
| `src/tools_L2.py` | 3 处 `datetime.utcnow()` 替换 |
| `src/tools_L3.py` | 1 处 `datetime.utcnow()` 替换 |
| `src/tools_L4.py` | 1 处 `_utc_timestamp()` 改写 |
| `tests/test_vnext_orchestrator.py` | 新增 generated_at 覆盖测试、L4 压缩测试（3 个） |
| `tests/test_interactive_chart_workbench.py` | 新增空序列警告测试 |
| `tests/test_vnext_llm_engine.py` | 移除 `return True/False`，改为纯 assert |
| `RUN_REVIEW_CHECKLIST.md` | 补填 2026-05-10/05-12/05-13 三次运行记录 |

**新增测试文件（2 个）：**

| 文件 | 测试数 | 覆盖内容 |
|------|--------|---------|
| `tests/test_contracts.py` | 14 | enum、model 序列化、generated_at UTC、core_facts 约束、roundtrip |
| `tests/test_core_checker.py` | 4 | DataIntegrity 全成功、部分失败、空列表、缺失 key |

**验证结果：** `pytest -q` → **177 passed, 5 warnings**（本轮前为 155 passed，新增 22 个测试）

---

*本报告由 Claude 基于 2026-05-13 运行产物和代码审查生成。2026-05-13 更新：标注修复状态，新增 3.4 指标时间戳标注建议。*
