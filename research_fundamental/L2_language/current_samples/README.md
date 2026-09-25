# 现有研报语言缺陷取样（Q3 病人样本）

## 样本是什么、从哪里来

系统的最终研报（内部叫 brief）由 `src/agent_analysis/vnext_reporter.py` 生成，类名
`VNextReportGenerator`（`src/agent_analysis/vnext_reporter.py:1877`），输出文件名规则为
`vnext_{template}_{stamp}.html`（`src/agent_analysis/vnext_reporter.py:1995`），落盘目录是
`output/reports/`。最近一次完整系统运行是 `output/analysis/vnext/20260911_233648`，其
`console_run_summary.json` 记录该运行于 2026-09-12 01:37 产出报告。
本目录三份样本全部取自已发布的 `vnext_brief_*.html`，按时间拉开跨度，原样复制、未改一字。

## 样本清单

| 本目录文件名 | 原始路径 | 判断对象数据截至 | 生成运行 | 文件落盘时间 |
|---|---|---|---|---|
| vnext_brief_20260831_2138.html | /Users/aidianchi/Desktop/ndx_mac/output/reports/vnext_brief_20260831_2138.html | 2026-08-31 | 20260831_213827 | 2026-09-01 02:34 |
| vnext_brief_20260905_2310.html | /Users/aidianchi/Desktop/ndx_mac/output/reports/vnext_brief_20260905_2310.html | 2026-09-05 | 20260905_231019 | 2026-09-06 01:45 |
| vnext_brief_20260906_1059_20260911_2336.html | /Users/aidianchi/Desktop/ndx_mac/output/reports/vnext_brief_20260906_1059_20260911_2336.html | 2026-09-06 | 20260911_233648（断点续跑自 20260906_105915） | 2026-09-12 01:37 |

第三份是系统当前最新的一份研报。

## 辅助文件

`extracted_text/` 下是同名的纯文本提取版，由
`research_fundamental/L2_language/extract_samples.py` 生成，只用于逐句审读和定位行号；
一切以 `.html` 原件为准。缺陷清单中标注的"行号"指 `extracted_text/` 里对应 `.txt` 的行号，
"章节"指研报内的版面章节（如"判断先行""01·正方主论证""05·改判条件"）。
