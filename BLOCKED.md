# BLOCKED.md —— T49 第二件 · 正文上链（2026-08-12 交付）

## 待领导裁决（任务书点名不修，只记录）

1. **三个报废源，均不修，待裁决**（来源：任务书"我替领导拍的板"；数据位置 `output/analysis/vnext/20260731_002156/news_event_ledger.json` 顶层键 `source_errors`，共 3 条，error 字段逐字如下）：
   - `nasdaq_index_announcements`：error 字段原文 = `HTTPSConnectionPool(host='www.nasdaq.com', port=443): Read timed out. (read timeout=12)`（超时）。
   - `alpha_vantage_news_sentiment`：error 字段原文 = `skipped_alpha_vantage_disabled_or_missing_key`（缺 key，需要领导的 key，执行者无权拍）。
   - `wind_company_announcements_m7`：error 字段原文 = `dropped_no_entity_match`（公告实体匹配丢；另见上轮条目 5，`dropped_no_entity_match, count=1`）。
   - 影响：渠道真空三态口径下这 3 个源记"失败"，覆盖率 0.8（12/15），不再冒充覆盖。

2. **`synthesis_packet.json` 的 `event_index` 为空字典（len 0）**：synthesis 阶段事件卡没有索引进 packet；IA 是通过 `integrated_synthesis_report.json` 的 `source_artifacts` 路径引用事件卡的。若本意是 packet 应内联事件索引，则此为空实现。**不修，待裁决**（任务书点名）。来源：上轮 BLOCKED.md 条目 3（引文见上，字段位置 `output/analysis/vnext/20260731_002156/synthesis_packet.json` 顶层键 `event_index`）。

## 上轮记录状态更新（T49 第一件 BLOCKED.md 条目）

3. **【已修复·本任务】正文被硬截断在 2200 字符**：上轮引文（原文）＝`src/news_event_ledger.py` 中 `_extract_readable_text(raw, 2200)`（约 L1074）与 `_write_source_raw` 的 `raw_text_excerpt: _clean_text(event.raw_text, 2200)`（约 L847）。本任务已改为命名常量 `RAW_TEXT_EXCERPT_LIMIT = 8000`（`src/news_event_ledger.py:42`），四处全部引用常量（:259/:328/:850/:1077），`grep -n "2200" src/news_event_ledger.py` 输出为空。

4. **【已修复·本任务】事件卡传入 IA 输入时正文结构性缺失**：上轮引文（原文）＝`event_interpretation_cards.json`（事件卡源文件）与 `integrated_synthesis_report.json`（IA 输入）中的事件卡均无任何正文字段。本任务修复：①orchestrator 落盘副本注入 `evidence_excerpt`/`raw_text_available`（`src/agent_analysis/orchestrator.py` 模块级函数 `_inject_evidence_fields`/`_with_evidence_injected_artifact`；内存 artifact 保持契约纯净，`EventInterpretationCard` 为 `extra="forbid"`，见 `src/agent_analysis/contracts.py:408-410`）；②IA 压缩器 `_compact_card_for_prompt` 增加 `evidence_excerpt`（截断 500）与 `raw_text_available`（`src/integrated_synthesis_report.py:730` 附近）。离线重装配演示 `scripts/layer2_baseline/demo_relay.py`：新口径 IA 可用率 0.3（旧口径 0%），逐字校验 ALL_OK。

5. **口径差异（非 bug，记录备查，未动）**：任务书称 source_type "七档"，代码 `governance.source_tiers` 实际声明 9 档（含 official_macro/company_disclosure/aggregator_report/unverified_signal）。本报告按代码 9 档为准统计。已向领导说明。

## 本任务新增（环境/外部状态，白名单外不可修，仅记录）

6. **`tests/test_docs_consistency.py::test_board_stays_glanceable` 失败**：`现在.md` 的「📋 全部未完成」表格中 T49 行"一句话"格子 74 字符，超 50 上限（断言原文：`f"{task_id} 的「一句话」有 {len(one_liner)} 字符（上限 50）——它该是标题，不是段落"`，位置 `tests/test_docs_consistency.py:204`）。该行内容（逐字）＝`第二层成熟度工程（第一件基线测量已完成并验收 08-11：全文缺失 80.23%、IA 卡正文可用率 0%、3/15 源报废；剩补采原型与镣铐落地）`，系 2026-08-11 16:01 外部更新写入（`git status --porcelain -- 现在.md` 为 M，非本任务改动）。`现在.md` 不在本任务可改白名单，未修，仅记录；全量测试 failed 数 = 3（console_run_all 两败为本任务书既知既有失败 + 本条），与任务 0 复跑基线一致，未劣化。

## 无法测量的指标（如实声明）

- 无。本任务全部验收项均完成实测（测试、脚本输出、反向验证红→绿证据见 PROGRESS.md 与交付汇报）。
