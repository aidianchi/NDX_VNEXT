# O12 专审报告：supplier_lookback 待验证数据能否撑 L4 主斜率

- 日期：2026-08-16
- 工单：老板 08-16 裁决 O12（病 C2），`investigation_reports/20260816_新对话交接_清空待办计划.md` L48/L72
- 审查方式：只读审查 + 从真实 run 产物复算数值；未改任何代码、未动后台在跑的 `t53_acceptance_20260816`
- 裁决前状态：PC-25 保持红灯（刻意，`src/agent_analysis/persistent_checks_b.py:1098-1130`）

---

## 一、结论先行

**30 日主斜率：有条件能撑。90 日主斜率：不能撑主结论，应降级为背景参考。**

- 这批数据不是来源不明的黑料：它是雅虎财经 `eps_trend` 的回看字段（`30daysAgo`/`90daysAgo`），2026-07-23 已经过一次正式验证闸门（E3），裁决是"**有限通过**"——7 天窗已验证可用，30/60/90 天窗明确挂"pending，届期补验后升级"。所以"待验证数据进主链"本身是**有裁决依据的权宜安排**，不是违规偷渡。
- 真正的问题有两个：① 30 天窗的补验到期日 2026-08-11 **已经过了五天，没人补验**（验证脚本只实现了 7 天窗，从未扩展到 30 天窗）；② 90 天窗至今 100% 来自待验证数据、零自产档案覆盖，且 2026-10-10 之前在原理上就无法核验。
- 最新真实 run（c6_baseline_20260815）里，30 天斜率已不再是 T47 审计时（07-30 run）的"100% 待验证"——自产档案已自然接管 14 只权重股（官方权重 55.72%），且这 14 只上两轨同向（自产 +6.47% vs 供应商 +5.29%），方向已被同窗佐证；但整个窗口仍被保守地整体标为 pending_validation。
- 拿掉这批数据的后果（用 run 内真实成分数据复算）：30 天斜率从 +5.60% 变为 +6.47%（只剩 14 只、55.72% 权重覆盖，方向不变、数值更高）；90 天斜率**直接归零——一只都不剩，指标不可用**。

---

## 二、这批数据是谁（文件证据）

**身份**：雅虎财经 `eps_trend` 字段里的供应商回看列——`30daysAgo` 与 `90daysAgo`，即雅虎"声称的 N 天前"的 FY1（`0y`）/FY2（`+1y`）一致预期 EPS。

- **来源与采集**：live run 时通过 yfinance 对 Invesco QQQ 官方持仓的 103 只成分股逐只抓取，采集时间 2026-08-15T13:11:19Z（c6_baseline_20260815 run，`prompt_audit/L4/attempt_1.payload.json` 内 `get_ndx_earnings_revision_metrics.data_quality.collected_at_utc`）。
- **覆盖**：NDX 全成分（103 只，官方权重覆盖 99.86%）。30 天窗实际入算 80 只 supplier（37.84% 权重）+ 14 只自产档案（55.72% 权重）；90 天窗 81 只全部 supplier（76.48% 权重）。
- **为什么标"待验证"**：2026-07-23 的 E3 验证闸门（`investigation_reports/20260723_l4_earnings_audit/WORK_ORDERS.md:72-81`）用自产 vintage 档案对雅虎 `7daysAgo` 字段做了对账（292 个有效对子，|相对偏差| 中位数 0.0034%、p95 0.54%、96.92% 在 1% 容差内；离群 9 条集中在 TSLA/GOOG/GOOGL 财报周），裁决"有限通过"：7 天窗 = `verified_with_earnings_week_caveat`；**30/60/90 天窗 = pending_validation，届期用同一脚本补验后升级**，届期分别是 2026-08-11 / 09-10 / 10-10（`E3_lookback_validation.md:72-84`）。标 pending 的直接原因：自产档案 2026-07-12 才起建，当时没有足够长的历史去核验 30/90 天回看值——"尚未核验"，不是"已证伪"（canon 原文，`src/agent_analysis/deep_research_canon.py:343`）。
- **自产档案现状**（`output/vintage_archive/`）：2026-07-12 起每日快照，至今 36 天；07-25 起从 15 只扩到全成分 103 只（E2 扩容，`WORK_ORDERS.md:59` 关单记录）。这是"待验证"状态正在自然消退的原因。

## 三、怎么进主斜率的（文件:行号）

计算入口：`src/tools_L4.py:7257` `get_ndx_earnings_revision_metrics()`。链路：

1. **逐股取锚点值**：`tools_L4.py:7712-7715`——对每个窗口（7/30/90 天，`:7691-7693` 生成 `supplier_key = "{window}daysAgo"`），先查自产档案（`archive_then_values`，锚日 ±2 天内，`tools_L4.py:7617-7649`）；查不到才退用雅虎回看字段（`:7720-7723`），并逐股记 `material = "self_archive" / "supplier_lookback"`（`:7715`）。
2. **逐股斜率**：`:7746-7748`，`w×(FY1_now/FY1_then−1)+(1−w)×(FY2_now/FY2_then−1)`；无效剔除（财年滚动、基数近零/符号穿越）`:7733-7774`；±50% 温莎化 `:7776-7782`。
3. **聚合主斜率**：`:7856-7864`，按 Invesco 官方权重归一加权。
4. **整窗标签（关键设计）**：`:7880-7889`——只要窗口里有**任何一只**用了 supplier，整个窗口块就保守地标 `material="supplier_lookback"` + `verification_status="pending_validation"`（注释 `:8320-8335` 明说"A mixed window is conservatively labelled supplier_lookback"）。这就是为什么 30 天窗已有 55.72% 权重来自自产档案，整体仍挂 pending。
5. **留痕与对撞**：`:8310-8311` 写 anomaly `30d/90d_supplier_lookback_pending_validation`；`:8387` 输出 divergence 两轨对比。
6. **进 L4 分析**：指标块进 `prompt_audit/L4` payload 的 `layer_raw_data.get_ndx_earnings_revision_metrics`；提示词规则 `src/agent_analysis/prompts/l4_analyst.md:32` 告诉 L4 分析员 supplier_lookback = 待验证补位、财报周只降置信不剔除；canon 规则 `RESEARCH_CANON.md:199`（双轨档案优先、pending 不得伪装已验证、验证闸门后才可升级）。L4 产物 `layer_cards/L4.json` 把它 surfaced 为 "NDX Earnings Revision Slope (30d/90d)"（值 0.056 / 0.0964，trend=rising），confidence=medium，risk_flags 含 `earnings_revision_supplier_lookback`。
7. **常设检查**：PC-25（`src/agent_analysis/persistent_checks_b.py:1116-1122`）专盯这个组合——slope_30d/slope_90d 出现 `supplier_lookback + pending_validation` 即报警。

## 四、拿掉它会怎样（c6_baseline_20260815 实测 + 复算）

数据源：run 内 `prompt_audit/L4/attempt_1.payload.json`，逐股成分表复算（权重加权，与代码 `:7856-7864` 同口径）。

| 窗口 | 现状（混合） | 拿掉 supplier 后 | 依据 |
|---|---|---|---|
| 30 天 | +5.60%（94 只，权重覆盖 93.69%） | **+6.47%（14 只，权重覆盖 55.72%）**，指标仍可用 | 成分表复算：self_archive-only 聚合 = 0.064664；run 内 divergence.30d 块同窗对撞自产 +6.47% vs 供应商 +5.29%，差 −1.17pp |
| 90 天 | +9.64%（81 只，权重覆盖 76.59%） | **0 只，指标直接 unavailable** | 90 天锚日（≈2026-05-17）早于档案起点 07-12，`self_archive_constituents=0`（coverage 块实测） |

补充事实：

- 7 天窗两轨已对撞：98 只 / 97.21% 权重，自产 +0.61% vs 供应商 +1.00%，差 +0.39pp，状态 `verified_with_earnings_week_caveat`（run 内 divergence.7d）。
- 30 天两轨差 −1.17pp 的方向与 E3 已知偏差模式一致（雅虎回看锚在财报密集期部分吸收新修正→低估斜率，偏保守不夸大，`E3_lookback_validation.md:64-70`、`tools_L4.py:8331-8334`）。
- 本 run 另有次要 caveat：Invesco 持仓直连 406 走兜底、权重已陈旧 24 天（anomalies：`holdings_fallback_used` / `holdings_stale:24d`），影响的是权重而非回看值本身。

## 五、建议与理由

### 30 天主斜率：**有条件能撑** —— 保留入算，限期补验转正

理由：① 进主链有 07-23 正式裁决依据，标签诚实（pending 标注 + anomaly + divergence 三处留痕，无伪装）；② 方向已被自产档案在 55.72% 权重上同窗佐证，且偏差方向偏保守；③ 拿掉它覆盖反而掉到 55.72%，剩余供应商部分只让数值更保守（+5.60% vs +6.47%），不存在"用它夸大信号"的风险。

处置：

1. **立即补做 30 天窗验证**（已逾期 5 天）：扩展 `scripts/validate_supplier_lookback.py`（现只比 `7daysAgo`，见 `:137`）支持 `30daysAgo`，对 15 只早期宇宙自 08-11 起可验，08-24 起全成分可验（D 与 D−30 都有全成分快照）。通过则 30 天窗升 `verified_with_earnings_week_caveat`。
2. 补验通过或 08-24 全成分自产档案接管 30 天锚点后，PC-25 的 30 天半才有转绿依据。

### 90 天主斜率：**不能撑主结论** —— 降级为背景参考

理由：100% 待验证、零自产覆盖、10-10 前**原理上无法核验**（档案不够长）；拿掉即空。让它当主结论依据，等于把改判触发器立在一根无法对账的柱子上。按 DECISION.md 的元规则"证据缺失只能映射为不确定性变宽，永远不能映射为方向"（`20260723_l4_earnings_audit/DECISION.md:19`），90 天斜率可作为语境参考保留展示，但不应作为改判/确认方向的依据；报告层引用它时必须带低置信声明。

### 关于"是否违规"

不算违规，是**有裁决、有标签、有退出计划的权宜**——但退出计划的第二步（届期补验）逾期未完成，这是管理欠账而非设计错误。PC-25 红灯判的就是这个超期状态，建议维持红灯直到上面两条处置落地，由老板据本报告裁决后转绿。

## 六、未能证实的事（如实声明）

1. **雅虎 30/90 天回看字段的内部口径**（日历日 vs 交易日 vs 批处理时点）从未验证——实测数据只有 7 天窗的 292 对；本报告对 30 天窗的判断依据是 run 内 14 只的两轨对撞，不是正式闸门复跑。
2. **30 天窗正式补验尚不存在**：验证脚本 `:40` 写死只比 7 天窗，`:229-247` 把 30/60/90 天窗标为 `not_yet_verifiable`（该判断写于 07-23，如今 30 天部分已到期可验，脚本未跟进）。
3. **90 天窗数据的可靠性完全无证据**——既不能证真也不能证伪。
4. 08-16 档案为 102 只而非 103 只（少了哪只、是抓取失败还是成分变动）未查。
5. 持仓权重 24 天陈旧对斜率聚合的量化影响未评估（影响权重，不影响回看值真实性）。
6. 后台在跑的 `t53_acceptance_20260816` 产物未纳入本审查（按要求未动）。

---

### 附：关键证据位置速查

- C2 原始证据：`investigation_reports/20260806_t47_context_review/03_根本审查总报告.md:121`；`phase1/L4.md:155-160`（第 17 条，07-30 run 时 30/90 天 100% supplier）
- 验证闸门裁决：`investigation_reports/20260723_l4_earnings_audit/WORK_ORDERS.md:72-81`；产数 `E3_lookback_validation.md`；脚本 `scripts/validate_supplier_lookback.py`
- 计算代码：`src/tools_L4.py:7257`（入口）、`:7712-7715`（选材）、`:7856-7864`（聚合）、`:7880-7889`（整窗标签）、`:8310-8311`（anomaly）
- 规矩：`RESEARCH_CANON.md:197-201`；`src/agent_analysis/deep_research_canon.py:334-364`；`src/agent_analysis/prompts/l4_analyst.md:32`
- PC-25：`src/agent_analysis/persistent_checks_b.py:1098-1130`
- 实测 run：`output/analysis/vnext/c6_baseline_20260815/prompt_audit/L4/attempt_1.payload.json`（数值经逐股复算核对）
