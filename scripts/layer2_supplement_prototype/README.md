# 第二层补采原型（T49-3 / C7）

自焊小循环 + 三性常驻脚本。只实现 + 单元测试；真实任务由根线程另行执行，原型不实际联网跑任务。

## 文件

- `prototype_loop.py`：planner（LLM）→ 白名单工具执行器（`read_local_material` / `fetch_official_url`）→ reader（LLM）→ 四条镣铐机器校验 → 失败重试 ≤2 次 → 下一轮。产物：`materials.jsonl`、`run_summary.json`、`prototype_audit/`（每轮 prompt 可 grep）、`fetched_cache/`。
- `three_tests.py`：读 `investigation_reports/20260811_layer2_research/baseline/sources_audit.json`，按「靠谱 / 必要 / 能死板拿」三性判定，输出 `layer2_three_tests_report.json` 与 `sources_to_remove.json`（只输出名单，不实际删源）。
- `three_tests_policy.md`：三性定义、谁裁决、新源先过审、名单与 baseline 差异要人复核；内含机器可读 JSON 阈值块，`three_tests.py` 从这里读阈值。
- `output/`：`three_tests.py` 的默认输出目录（运行后生成）。

## 怎么跑

真实补采任务由根线程执行，不在本原型里联网跑；产物在 `scripts/layer2_supplement_prototype/runs/<agenda_id>/` 下（`materials.jsonl`、`run_summary.json`、`prototype_audit/`、`fetched_cache/`）。

```bash
.venv/bin/python scripts/layer2_supplement_prototype/prototype_loop.py \
  --task /path/to/task.json \
  --run-dir scripts/layer2_supplement_prototype/runs/<agenda_id>
```

task.json 形如 `{"agenda_id": "ag1", "question": "...", "max_rounds": 2}`（max_rounds ≤ 4）。

三性常驻判定（只读 baseline，输出到本目录 `output/`）：

```bash
.venv/bin/python scripts/layer2_supplement_prototype/three_tests.py
```

测试：

```bash
.venv/bin/python -m pytest tests/test_layer2_prototype.py -q
```

## 关键约束（机器可查）

- 域名白名单：`prototype_loop.ALLOWED_FETCH_DOMAINS`（SEC/FRB/FederalReserve/NASDAQ/CFTC/FINRA/BEA/BLS/Treasury 等，https only）。
- 工具白名单：`prototype_loop.TOOL_WHITELIST`（`read_local_material` / `fetch_official_url`）；白名单外调用返回 `tool_not_whitelisted`。
- 四条镣铐：`prototype_loop.validate_material_card` 返回固定错误码（`fact_summary_hedge_word:*`、`source_tier_illegal`、`needs_data_confirmation_empty_or_invalid`、`collected_at_utc_in_future` 等）。
- 每张材料卡带治理行：`本材料是第二层候选材料，判断以第一层数据为准`。

## BLOCKED

无。
