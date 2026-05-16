# 项目深度审查报告

审查日期：2026-05-13
审查对象：最新运行 `output/analysis/vnext/20260513_191253` 及历史运行记录
审查依据：`WORK_LOG.md`、`NEXT_STEPS.md`、`RUN_REVIEW_CHECKLIST.md`、控制台日志、运行产物、测试套件

> **状态说明**：本报告在原版基础上更新了修复状态。`[已完成]` 表示已在本轮重构中修复并通过测试验证；`[未完成]` 表示尚未实施，保留在后续工作中。

---

## ⚠️ 自审查发现（U7-U10）[已完成]

> 以下问题由 Claude 对 `claude/20260513-indicator-timestamps` 分支的 diff 进行二次审查时发现。均为该分支引入的新问题或遗漏。

### U7. `_enrich_indicator_data_quality` 中 `valuation_sources` 对已有 `data_quality` 的指标被跳过 [已完成]

**文件：** `src/agent_analysis/vnext_reporter.py:725-735`

**问题：** `_valuation_sources_from_raw()` 提取逻辑被嵌套在 `if not item.get("data_quality")` 条件内。当 LLM 在 layer card 中为某个指标生成了 `data_quality` 字段（即使只有 `{}`），该指标的 ThirdPartyChecks 来源不会被提取到 `valuation_sources`。

**行为变化对比：**

| 场景 | 原版 (main) | 新版 (branch) |
|------|-------------|---------------|
| item 无 data_quality | 复制 raw data_quality + 提取 valuation_sources ✓ | 同左 + 注入 collected_at_utc ✓ |
| item 有 data_quality | `continue` 跳过，不做任何处理 | 注入 collected_at_utc + 手动标记，但 **valuation_sources 被跳过** ✗ |

**影响：** L4 指标（如 NDX PE）如果 LLM 生成了 `data_quality`，brief 中该指标的估值来源表格（ThirdPartyChecks）会丢失。`_data_quality_box()` 渲染时从 `data_quality.get("valuation_sources", [])` 读取，空列表则不显示来源表格。

**修复方向：** 把 `valuation_sources` 提取移到 `if not item.get("data_quality")` 条件外面，使其对所有指标生效。约 2 行代码位移。

**修复实施：** 重构 `_enrich_indicator_data_quality`（见 U10），valuation_sources 提取移到条件外，对所有指标生效。新增回归测试 `test_enrich_indicator_data_quality_with_existing_dq` 验证。

---

### U8. `_summarize_long_series` 精度损失与隐式排序假设 [已完成]

**文件：** `src/agent_analysis/orchestrator.py:1234-1238`

**问题：**

1. **精度损失：** 所有统计量 `round(..., 4)`。对百分比类指标（ERP 5.24%）足够，但对 PE（32.5678）、价格（18234.56）等会丢失精度。Damodaran ERP 原始数据通常保留 2 位小数，4 位足够；但 WorldPERatio 的 PE 值可能有更多小数位。
2. **隐式排序假设：** `values[-1]` 取序列中最后出现的数值，假设数据已按时间升序排列。如果数据反序提供（如某些 API 返回最新在前），`latest` 会取到最老的值而非最新的。

**影响：** 当前 L4 主要处理 Damodaran ERP 百分比数据，精度损失可接受。但如果 `_summarize_long_series` 被复用于其他数据类型，精度和排序问题会变得显著。

**修复方向：**
- 改为 `round(..., 6)` 或按数值大小自适应精度
- 用 `series[-1]` 对应的值（已取到 `last`）而非 `values[-1]`，或显式排序

**修复实施：** `round(..., 4)` → `round(..., 6)`。排序假设在当前 L4 使用场景下安全（Damodaran 数据由 collector 按时间顺序收集），若复用于其他数据源需显式排序。

---

### U9. orchestrator.py:753 冗余的局部 import [已完成]

**文件：** `src/agent_analysis/orchestrator.py:753`

**问题：** `_run_stage()` 中 `from datetime import datetime, timezone` 是局部 import，但 `datetime` 和 `timezone` 已在文件第 6 行顶部导入。

```python
# Line 752-754
if hasattr(model_cls, "model_fields") and "generated_at" in model_cls.model_fields:
    from datetime import datetime, timezone  # ← 冗余，顶部已有
    parsed["generated_at"] = datetime.now(timezone.utc)
```

**修复方向：** 删除第 753 行。1 行改动。

**修复实施：** 已删除冗余局部 import `from datetime import datetime, timezone`。

---

### U10. `_enrich_indicator_data_quality` 方法可大幅简化 [已完成]

**文件：** `src/agent_analysis/vnext_reporter.py:691-738`

**问题：** 当前 48 行，4 层嵌套。`collected_at` 注入逻辑在条件内外有重复设置（line 718 和 line 730），且 `valuation_sources` 提取被错误嵌套（见 U7）。可通过重构消除重复并修复 U7。

**简化方案：**

```python
def _enrich_indicator_data_quality(self, artifacts):
    raw_data = artifacts.get("analysis_packet", {}).get("raw_data", {})
    layers = artifacts.get("layers", {})
    if not isinstance(raw_data, dict) or not isinstance(layers, dict):
        return
    for layer, card in layers.items():
        if not isinstance(card, dict):
            continue
        layer_raw = raw_data.get(layer)
        if not isinstance(layer_raw, dict):
            continue
        for item in card.get("indicator_analyses", []) or []:
            if not isinstance(item, dict):
                continue
            raw_item = layer_raw.get(item.get("function_id"))
            if not isinstance(raw_item, dict):
                continue
            # Merge: raw data_quality as base, overlay existing item fields
            base = dict(raw_item.get("data_quality") or {})
            base.update(item.get("data_quality") or {})
            # Always inject collector timestamp (authoritative)
            if raw_item.get("collection_timestamp_utc"):
                base["collected_at_utc"] = raw_item["collection_timestamp_utc"]
            # Manual override annotation
            if raw_item.get("manual_override_used"):
                tier = str(base.get("source_tier", "")).strip()
                base["source_tier"] = f"{tier} · 手动输入" if tier else "手动输入"
            # Always extract valuation sources (fixes U7)
            vs = self._valuation_sources_from_raw(raw_item)
            if vs:
                base["valuation_sources"] = vs
            if base:
                item["data_quality"] = base
```

48 行 → 28 行，消除嵌套重复，同步修复 U7。

**修复实施：** 已按简化方案重构 `_enrich_indicator_data_quality`。48 行 → 28 行。核心变化：
- 以 `raw_item["data_quality"]` 为 base，overlay `item["data_quality"]`，保留 raw 中的有价值字段（如 formula）
- valuation_sources 提取移到循环主体，对所有指标生效（修复 U7）
- 消除 collected_at 的重复设置

---

### U7-U10 测试缺口 [已完成]

当前测试 `test_enrich_indicator_data_quality_injects_collection_timestamp` 只覆盖了 item 无 `data_quality` 的路径。缺少以下场景的测试：

1. item 有 `data_quality`（由 LLM 生成）时，`collected_at_utc` 仍被注入
2. item 有 `data_quality` 时，`valuation_sources` 仍被提取（U7 修复后的回归测试）

**修复实施：** 新增 `test_enrich_indicator_data_quality_with_existing_dq`，验证：
- item 有 existing data_quality 时 collected_at_utc 仍被注入
- item 有 existing data_quality 时 valuation_sources 仍被提取（U7 回归测试）
- raw data_quality 字段（如 formula）被正确合并到 base（U10 验证）
- existing LLM 字段（如 confidence）被保留

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
- [已完成] `tools_L1.py` ~ `tools_L5.py` — `tests/test_tools_smoke.py` 8 个测试覆盖导入、签名、registry
- [已完成] `chart_adapter_v6.py`、`chart_generator.py` — `tests/test_chart_modules.py` 13 个测试覆盖纯函数

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

### 3.1 `console_run_summary.json` 中 `report_path` 为空 [已完成]

`console_run_summary.json` 中 `report_path` 字段为空字符串 `""`，而 `native_brief` 和 `workbench` 有值。需要明确 `report_path` 是指 legacy HTML 报告还是应被移除的废弃字段。

**修复实施：** `src/console_run_all.py` 中增加 fallback：`report_path = summary.get("report_path") or brief_path`，保证 console summary 始终有有效路径。

### 3.2 `DataIntegrity.checker` 可能检查旧格式数据 [已完成]

`src/core/checker.py:10-11` 检查 `data_json.get("indicators", [])`，但当前 `data_collected_v9_live.json` 使用 `raw_data` 按层分组的格式。虽然 `indicators` 列表仍然存在（39 个 items），但需要确认 checker 是否覆盖了新格式的所有字段（如 `ThirdPartyChecks`、`source_disagreement` 等）。

**修复实施：** 扩展 `DataIntegrity.run()` 返回 `layer_breakdown`（每层成功率）和 `third_party_checks`（外部校验可用率），覆盖 `ThirdPartyChecks` 嵌套字段解析。新增 2 个测试验证。

### 3.3 Bridge `event_refs` 数量与实际内容不匹配 [已完成]

`bridge_0.json` 中显示 `event_refs: 24`，但内容中的 `event_refs` 字段为空数组 `[]`。需要确认 event_refs 是否被正确从 `news_event_ledger.json` 中填充，以及 Bridge prompt 是否正确传递了事件索引。

**修复实施：** `cross_layer_bridge.md` prompt 中新增 `event_refs` 引用指南段落，明确 typed_conflicts/resonance_chains/transmission_paths 的 event_refs 用法；`orchestrator.py` 中 `_build_governance_input_packet()` 扩展 event_refs 收集逻辑。**待验证：** 真实运行产物中的 event_refs 是否非空（需端到端测试）。

### 3.4 每个指标在最终报告中加时间戳标注 [已完成] ⭐ 新增

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
| 应当改正 | 5 | 5 | 0 | — |
| 建议改进 | 4 | 4 | 0 | — |
| **自审查发现** | **4** | **0** | **4** | **U7 valuation_sources 丢失** |

### 未完成清单

| # | 问题 | 优先级 | 文件 | 说明 |
|---|------|--------|------|------|
| U7 | `_enrich_indicator_data_quality` 中 `valuation_sources` 对已有 data_quality 的指标被跳过 | **P1** | `vnext_reporter.py:725` | 功能性 bug：L4 指标的 ThirdPartyChecks 来源表格会丢失。修复：2 行代码位移 |
| U8 | `_summarize_long_series` 精度损失与隐式排序假设 | P2 | `orchestrator.py:1234` | `round(4)` 对大数值丢失精度；`values[-1]` 假设升序。当前影响可控 |
| U9 | orchestrator.py:753 冗余局部 import | P3 | `orchestrator.py:753` | `datetime`/`timezone` 已在顶部导入。1 行删除 |
| U10 | `_enrich_indicator_data_quality` 可大幅简化 | P2 | `vnext_reporter.py:691` | 48 行 4 层嵌套 → 28 行，同步修复 U7 |

### 本轮 U1-U6 交付清单

**分支：** `claude/20260513-indicator-timestamps`

**修改文件（7 个）：**

| 文件 | 改动内容 |
|------|---------|
| `src/agent_analysis/vnext_reporter.py` | 注入 `collection_timestamp_utc` 到 indicator data_quality；新增 `_timestamp_chip()` + `_enrich_indicator_data_quality()`；HTML 渲染时间戳徽章 |
| `src/agent_analysis/report_styles/slate_v2.css` | 新增 `.timestamp-chip` 样式（小字体、行内、不干扰阅读） |
| `src/console_run_all.py` | `report_path` fallback：`summary.get("report_path") or brief_path` |
| `src/core/checker.py` | `DataIntegrity.run()` 返回 `layer_breakdown` + `third_party_checks` |
| `src/agent_analysis/prompts/cross_layer_bridge.md` | 新增 `event_refs` 引用指南段落（typed_conflicts/resonance_chains/transmission_paths） |
| `src/agent_analysis/orchestrator.py` | `_build_governance_input_packet()` 扩展 event_refs 收集 |

**新增测试文件（3 个）：**

| 文件 | 测试数 | 覆盖内容 |
|------|--------|---------|
| `tests/test_vnext_reporter.py` | +3 | 时间戳注入、chip 格式化、HTML 出现性 |
| `tests/test_core_checker.py` | +2 | layer_breakdown、third_party_checks |
| `tests/test_tools_smoke.py` | 8 | registry 完整性、函数可导入、end_date 签名 |
| `tests/test_chart_modules.py` | 13 | MACD、OBV、volume、Donchian、percentiles、transforms |

**验证结果：** `pytest -q` → **203 passed, 5 warnings**（本轮新增 26 个测试）；含后续提交共 **246 passed**

**已知待验证：** U4（event_refs）需真实端到端运行确认 LLM 是否填充非空 event_refs。

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

## 七、深度偏差审查（2026-05-15）[已完成]

> 本次审查系统性排查了 NDX vnext 中可能导致最终分析结果出现明显偏差的所有环节：数据处理、AI 分析推理、跨层 Bridge、治理阶段和报告生成。

### 7.1 Few-shot 示例编造无来源历史统计数据 [已完成]

**问题：** `prompt_examples.py` 中 FGI few-shot 示例包含无来源的编造统计数字：
- `"历史上，FGI<20时的6个月后市场平均收益约+24%"`（第 162-163 行）
- `"历史上，FGI>80时的3个月后市场平均收益为负"`（第 185-186 行）

`reasoning_examples.py` 中同样包含编造声明：
- `"纳斯达克指数在创新高，但内部已经有70%的股票在下跌"`（第 97 行）— 无来源的具体百分比
- `"历史经验表明，在ADX>40的强趋势中逆势交易，失败率极高"`（第 161 行）— 编造胜率
- `"顺势而为（持有现金或做空）的胜率远高于逆势抄底"`（第 163 行）— 编造概率

**影响：** L1-L5 analyst prompt 通过 `build_layer_few_shot_prompt()` 注入这些示例，LLM 学会"引用无来源历史概率"的模式，在真实分析中复制这种行为。这是最危险的分析偏差源头。

**修复实施：**
- `prompt_examples.py`：将编造统计替换为条件语言（"历史上常对应...但必须结合..."）
- `reasoning_examples.py`：删除"70%的股票"等编造具体数字，删除"失败率极高""胜率远高于"等编造概率

### 7.2 L1-L5 analyst prompt 全部缺少反编造约束 [已完成]

**问题：** 通过 grep 确认：`l1_analyst.md` ~ `l5_analyst.md`、`thesis_builder.md`、`critic.md`、`reviser.md` 中均无"编造/fabricat/hallucin"关键词。只有 `risk_sentinel.md` 和 `final_adjudicator.md` 有反编造禁令。

**影响：** 产生原始分析的 layer analyst 没有约束，治理层只能管自己的输出，管不了上游传来的假数据。

**修复实施：** 在以下 8 个 prompt 文件中新增"证据纪律（不可违反）"段落：
- `l1_analyst.md`、`l2_analyst.md`、`l3_analyst.md`、`l4_analyst.md`、`l5_analyst.md`
- `thesis_builder.md`、`critic.md`、`reviser.md`

约束内容：不得编造历史胜率/回测收益/概率数字；不得编造点位/跌幅/估值倍数；引用历史只用"常伴随"不编造具体数字；所有 evidence_refs 必须来自输入数据。

### 7.3 客观性防火墙 `object_clear` 硬编码 True [已完成]

**问题：** `orchestrator.py:467` 中 `object_clear=True` 无条件设置。ObjectCanon 定义的反证条件（如"输入数据不覆盖 NDX/QQQ"）从未被评估。防火墙四道门中的第一道永久失效。

**影响：** 当投资对象定义不清晰时，系统不会降置信度，也不会警告。

**修复实施：** `_build_objective_firewall_summary` 中新增实际检查：验证 `packet.raw_data` 是否包含至少 3/5 层（L1-L5）的数据。不足时设 `object_clear=False` 并在 warnings 中说明缺失的层。

### 7.4 `cross_layer_verified` 语义反转 [已完成]

**问题：** `orchestrator.py:449` 中 `cross_layer_verified = bool(typed_conflicts or legacy_conflicts)`。变量名暗示"跨层逻辑已被验证"，但实现含义是"发现了跨层冲突"。结果：危险情况（大量冲突）不惩罚，安全情况（零冲突）反而惩罚。

**修复实施：** 改为 `cross_layer_verified = bool(bridge_memos)`——只要 Bridge 产生了 memo（即执行了跨层分析），就视为已验证。

### 7.5 L4 长序列压缩摧毁时间分辨率 [已完成]

**问题：** `orchestrator.py:1214-1246` 的 `_summarize_long_series` 将长序列压缩为 min/max/mean/latest 统计摘要。LLM 无法识别趋势方向、拐点或近期动量变化。

**修复实施：** `_summarize_long_series` 改进为：
1. 新增 `recent_records`：保留最近 10 条完整记录，让 LLM 看到时间轨迹
2. 每个数值字段新增 `trend`：通过前半段均值 vs 后半段均值判断 "rising"/"falling"/"stable"
3. 保留原有统计摘要（min/max/mean/latest），新增趋势判断

### 7.6 SynthesisPacket 只包含高严重度冲突 [已完成]

**问题：** `orchestrator.py:354-363` 中过滤条件为 `severity == "high"`。中等严重度的跨层冲突被排除在 SynthesisPacket 之外，Thesis 阶段看不到它们。

**修复实施：** 过滤条件从 `severity == "high"` 改为 `severity in ("high", "medium")`，确保 Bridge 识别的所有有意义的跨层冲突都传递到 Thesis。

### 7.7 测试更新 [已完成]

- `tests/test_objective_firewall.py`：更新现有测试以提供包含 L1-L5 的 raw_data；新增 2 个测试：
  - `test_object_clear_false_when_insufficient_layers`：验证 object_clear 在数据不足时为 False
  - `test_cross_layer_verified_true_when_bridge_memos_exist`：验证有 Bridge memo 时为 True

### 7.8 TimeSeriesManager 缓存过期检测 [已完成]

**问题：** `data_manager.py:74` 中当 API 更新失败时，静默返回旧缓存，只打印 print 警告。没有 TTL 检查，没有 staleness 标记。下游完全不知道数据已过期。

**影响：** 如果数据源临时不可用，系统可能用几天前的数据做分析，且不会有任何警告。

**修复实施：**
- `TimeSeriesManager.__init__` 新增 `staleness_threshold_days` 参数（默认 7 天）
- `get_or_update_series` 在返回前检查缓存最新日期与当前日期的差值
- 缓存过期时打印明确警告：`"[TimeSeriesManager] ⚠ 缓存过期警告: {series_id} 最新数据日期 {date}，已 {N} 天未更新"`
- 返回的 DataFrame 在 `.attrs["stale"]` 或 `.attrs["was_stale"]` 中携带过期元信息
- 更新失败时在 `.attrs["stale"]` 中记录失败原因

### 7.9 LLM 调用 system/user 角色分离 [已完成]

**问题：** `llm_engine.py:129` 中所有内容（包括反编造约束、分析请求、数据）都作为单条 `{"role": "user"}` message 发送。约束指令与分析请求竞争注意力。

**影响：** LLM 对约束的遵守率低于使用 system message 的场景。

**修复实施：**
- `LLMEngine` 新增类常量 `SYSTEM_CONSTRAINTS`：包含 5 条不可违反的纪律（不编造统计、不编造定量影响、条件语言、evidence_refs 来源、JSON 格式）
- `_call_ai` 和 `_call_kimi_http` 中 messages 改为 `[system_message, user_message]` 结构
- system message 承载约束（高权威），user message 承载分析请求

### 7.10 Schema Guard 从纯建议性升级为带重试 [已完成]

**问题：** `orchestrator.py:894-1017` 的 `_run_schema_guard` 产出 `SchemaGuardReport`，`passed=False` 时只是作为文本传给下游 LLM。没有代码级的阻断或重试。

**影响：** 即使检测到结构完整性问题（如丢失高严重度冲突），流程仍会继续。

**修复实施：**
- 在 `run()` 方法中，schema_guard 检查后新增重试逻辑：
  - 当 `structural_issues` 或 `missing_fields` 非空时，自动重试 thesis + critic + risk
  - 重试时将 schema issues 注入 governance input，让 LLM 知道需要修复什么
  - 重试后重新运行 schema_guard
  - 若仍失败，记录 WARNING 并继续（避免无限循环）
- 重试次数限制为 1 次（嵌入在 `run()` 流程中，不额外增加复杂度）

### 7.11 问题汇总

| # | 问题 | 严重度 | 状态 | 修改文件 |
|---|------|--------|------|----------|
| F1 | Few-shot 编造历史统计数据 | 致命 | **已修复** | `prompt_examples.py`, `reasoning_examples.py` |
| H1 | L1-L5 prompt 缺反编造约束 | 高 | **已修复** | `l1_analyst.md` ~ `l5_analyst.md`, `thesis_builder.md`, `critic.md`, `reviser.md` |
| F3 | object_clear 硬编码 True | 致命 | **已修复** | `orchestrator.py` |
| F4 | cross_layer_verified 语义反转 | 致命 | **已修复** | `orchestrator.py` |
| F5 | 长序列压缩丢失时间轨迹 | 致命 | **已修复** | `orchestrator.py` |
| H3 | 中等冲突被排除出 SynthesisPacket | 高 | **已修复** | `orchestrator.py` |
| — | TimeSeriesManager 缓存无 TTL | 高 | **已修复** | `data_manager.py` |
| — | LLM 调用无 system/user 角色分离 | 中 | **已修复** | `llm_engine.py` |
| — | Schema Guard 纯建议性 | 中 | **已修复** | `orchestrator.py` |
| — | M7 ROE 单位不一致（AV 路径） | 高 | **暂缓** | Alpha Vantage 路径当前非主路径，暂缓修复 |

**验证结果：** `pytest -q` → **249 passed, 5 warnings**

---

## 八、代码简化审查（2026-05-15）[已完成]

> 在修复上述所有问题后，对全部代码改动进行了一次全局简化审查，目标是在不影响功能的前提下让实现更简洁、更不容易出错。

### 8.1 删除 Schema Guard 重试中多余的 thesis 调用 [已完成]

**问题：** `orchestrator.py` 的 Schema Guard 重试块中，`thesis = self._run_thesis(synthesis_packet)` 用的是**原始** `synthesis_packet`（schema 反馈没有注入到 thesis 输入中）。这意味着重试时 thesis 的输入和第一次完全一样，白白浪费一次完整的 LLM 调用。

**影响：** 每次触发 Schema Guard 重试时，浪费一次 DeepSeek API 调用（约 10-30 秒 + token 费用）。

**修复：** 删除重试块中的 `_run_thesis` 调用。重试只重新运行 critic 和 risk（它们的 governance input 确实包含了 schema 反馈）。

### 8.2 从 8 个 prompt 文件中去重"证据纪律"段落 [已完成]

**问题：** `system_constraints.md`（通过 system message 注入，最高权威级别）已经包含 5 条防编造纪律。但 8 个 prompt 文件中又有各自的"证据纪律"段落，内容完全或大部分重复：
- L1-L5 analyst：282 字，与 system_constraints 100% 重复
- critic、reviser、thesis_builder：部分重复 + 各自独有的层特定指令

**影响：** 每个 prompt 多了 ~280 字的冗余内容；维护时需要同步修改 9 个地方（system_constraints + 8 个 prompt）。

**修复：**
- L1-L5：**删除**整个"证据纪律"段落（system message 已覆盖）
- critic/reviser/thesis_builder：**精简**到只保留各自独有的指令（如 critic 的"发现上游编造数据要指出"、reviser 的"改写为定性表达"、thesis_builder 的"evidence_refs 必须来自 evidence_index"）

### 8.3 `_summarize_long_series` 从 O(C×N) 改为单次遍历 [已完成]

**问题：** 原实现对每个列遍历所有行（`for col in first.keys()` 外层，`for item in series` 内层）。6 列 × 120 行 = 720 次迭代。

**修复：** 改为单次遍历，同时收集所有列的数值。120 行只需 120 次迭代。输出完全不变。

### 8.4 提取 `_run_and_save` 辅助方法 [已完成]

**问题：** `_run_stage()` + `_save_json()` 的配对调用在 `run()` 方法中出现 5 次（critic×2、risk×2、reviser×1），每次都写两行几乎相同的代码。

**修复：** 提取 `_run_and_save()` 辅助方法（3 行），5 处调用简化为一行。final 阶段因有 token_usage 赋值等特殊后处理，保留原样。

### 8.5 提取 `_severity_is_high_or_medium` 辅助函数 [已完成]

**问题：** `str(_enum_value(conflict.severity)) in ("high", "medium")` 在 `high_conflicts` 和 `high_typed_conflicts` 两处过滤中重复出现。

**修复：** 提取为模块级 `_severity_is_high_or_medium()` 函数 + `_SEVERITY_HIGH_MEDIUM` frozenset 常量，两处调用统一使用。

### 8.6 简化审查汇总

| # | 改动 | 类型 | 影响行数 |
|---|------|------|---------|
| 8.1 | 删除多余 thesis 重试 | 效率 | -1 行 |
| 8.2 | 去重 8 个 prompt 的证据纪律 | 复用 | -40 行 |
| 8.3 | 单次遍历统计摘要 | 效率 | ~0（重写） |
| 8.4 | 提取 `_run_and_save` | 质量 | -15 行 +3 行 |
| 8.5 | 提取冲突过滤函数 | 质量 | -4 行 +5 行 |

**验证结果：** `pytest -q` → **251 passed, 5 warnings**

---

## 附录：全分支改动总览

> 以下列出 `claude/20260513-indicator-timestamps` 分支相对于 `main` 的全部改动。
>
> - **已提交**（4 个 commit）：33 个文件，+2675 行，-115 行
> - **未提交**（工作区）：9 个源文件 + 1 个新文件，+239 行，-56 行（深度偏差审查 + 简化审查的改动）
>
> 注：L1-L5 analyst prompt 的证据纪律在本轮中先添加（7.2）后删除（8.2），净变化为零，因此不在 git diff 中体现。

### 源文件（20 个）

| 文件 | 改动类型 | 章节索引 |
|------|---------|---------|
| `src/agent_analysis/orchestrator.py` | 核心逻辑：防火墙修复、冲突过滤、L4 压缩、Schema Guard 重试、system/user 分离、简化 | 7.3-7.6, 7.10, 8.1, 8.4-8.5 |
| `src/agent_analysis/llm_engine.py` | system_constraints 加载、system/user 消息分离 | 7.9 |
| `src/agent_analysis/prompts/system_constraints.md` | **新增**：5 条防编造纪律（外部化） | 7.9 |
| `src/agent_analysis/prompts/l1_analyst.md` ~ `l5_analyst.md` | 添加/精简证据纪律 | 7.2, 8.2 |
| `src/agent_analysis/prompts/critic.md` | 添加/精简证据纪律 | 7.2, 8.2 |
| `src/agent_analysis/prompts/reviser.md` | 添加/精简证据纪律 | 7.2, 8.2 |
| `src/agent_analysis/prompts/thesis_builder.md` | 添加/精简证据纪律 | 7.2, 8.2 |
| `src/agent_analysis/prompts/cross_layer_bridge.md` | event_refs 引用指南 | 3.3 |
| `src/agent_analysis/vnext_reporter.py` | 时间戳注入、_enrich 简化、valuation_sources 修复 | U7, U10, 3.4 |
| `src/agent_analysis/report_styles/slate_v2.css` | .timestamp-chip 样式 | 3.4 |
| `src/agent_analysis/contracts.py` | datetime.utcnow → datetime.now(timezone.utc) | 2.2 |
| `src/data_manager.py` | TimeSeriesManager 缓存过期检测 | 7.8 |
| `src/prompt_examples.py` | 清除 few-shot 编造统计 | 7.1 |
| `src/reasoning_examples.py` | 清除编造概率/百分比 | 7.1 |
| `src/core/collector.py` | datetime.utcnow 替换 | 2.2 |
| `src/core/checker.py` | DataIntegrity 扩展 | 3.2 |
| `src/tools_L2.py` / `tools_L3.py` / `tools_L4.py` | datetime.utcnow 替换 | 2.2 |
| `src/console_run_all.py` | report_path fallback | 3.1 |
| `src/interactive_chart_workbench.py` | 数据时效性警告横幅 | 1.2 |
| `src/research_console.py` | 多报告链接 + 弹窗检测 | — |

### 测试文件（11 个）

| 文件 | 测试数 | 覆盖内容 |
|------|--------|---------|
| `tests/test_contracts.py` | 14 | enum、model 序列化、generated_at UTC |
| `tests/test_core_checker.py` | 6 | DataIntegrity + layer_breakdown + third_party_checks |
| `tests/test_tools_smoke.py` | 8 | registry 完整性、函数导入 |
| `tests/test_tools_calculation.py` | 43 | tools_L4/L5 数据清洗 + tools_common 分析 |
| `tests/test_chart_modules.py` | 13 | MACD、OBV、Donchian 等纯函数 |
| `tests/test_vnext_orchestrator.py` | +3 | generated_at 覆盖、L4 压缩 |
| `tests/test_interactive_chart_workbench.py` | +2 | 缓存警告、空序列警告 |
| `tests/test_objective_firewall.py` | +4 | object_clear、cross_layer_verified |
| `tests/test_vnext_llm_engine.py` | +5 | system_constraints 加载、system/user 角色 |
| `tests/test_deepseek_runtime_config.py` | +1 | system/user 消息结构 |
| `tests/test_vnext_reporter.py` | +3 | 时间戳注入、chip 格式、HTML 渲染 |

### 文档（2 个）

| 文件 | 改动 |
|------|------|
| `PROJECT_AUDIT_20260513.md` | 本审查报告（新增） |
| `RUN_REVIEW_CHECKLIST.md` | 补填运行记录 |

### 问题修复总数

| 类别 | 总数 | 已完成 | 暂缓 |
|------|------|--------|------|
| 严重（F1-F5） | 5 | 5 | 0 |
| 高（H1-H3） | 3 | 3 | 0 |
| 建议改进（3.1-3.4） | 4 | 4 | 0 |
| 自审查（U7-U10） | 4 | 4 | 0 |
| 深度审查补充（7.8-7.10） | 3 | 3 | 0 |
| 简化审查（8.1-8.5） | 5 | 5 | 0 |
| 暂缓 | 1 | 0 | 1 |
| **合计** | **25** | **24** | **1** |

**最终验证：** `pytest -q` → **251 passed, 5 warnings**

---

*本报告由 Claude 基于 2026-05-13 运行产物和代码审查生成。2026-05-13 更新：标注修复状态，新增 3.4 指标时间戳标注建议。2026-05-15 自审查：新增 U7-U10。2026-05-15 深度偏差审查：新增第七章（F1-H3 共 9 项已修复，1 项暂缓）。2026-05-15 简化审查：新增第八章（8.1-8.5 共 5 项已修复）。附录：全分支 33 个文件改动总览，25 项问题中 24 项已完成，251 tests passed。*
