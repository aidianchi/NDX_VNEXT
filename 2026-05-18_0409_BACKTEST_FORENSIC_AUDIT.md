# 2025-04-09 回测产物取证审查

调查日期：2026-05-18
调查对象：[output/analysis/vnext/20250409/](output/analysis/vnext/20250409/) 及对应原生报告 [vnext_brief_20260518_1940_20250409_0000.html](output/reports/vnext_brief_20260518_1940_20250409_0000.html)
调查目的：在不修改任何代码或数据的前提下，把这次 0409 回测产生的全部问题分门别类列清楚，给后续修复留下完整证据。

> 本报告是按"调查研究"原则、从 `log + JSON artifact + 原生 HTML + 源码`这四条独立证据链交叉重写的取证清单，与根目录其他同主题文件无关，不沿用其结论。

---

## 0. 摘要

这次 0409 回测的产物**不可作为研究报告对外发布**。问题不是文案瑕疵，而是四条独立链路同时被破坏：

1. **回测前瞻信息泄露**：至少 3 个进入 L1-L5 prompt 的指标使用了 2025-04-09 之后的数据，其中包含 2026-05-15 的净流动性、2026-05-15 的 SKEW、2026-05-18 到期的 QQQ 期权链，以及 Damodaran 月度序列中 13 个月的未来行。
2. **manual override 隔离失败**：`manual_overrides.active=false`、`manual_override_count=0`，但完整的 PE 36.6 等 metrics 仍被注入 L4 prompt，并通过 L4 → Synthesis → Thesis → Risk → Reviser → Final 一条链全部污染到最终风险表述。
3. **质量闸门只报告不阻断**：DataIntegrity 自己识别出"1 个指标存在晚于回测日的数据日期"并把置信度降到 84.6%，但仍生成可发布报告；同时 schema_guard 显示 `passed=true`，对 bridge 多处空字段和重复 id 视而不见。
4. **运行环境失稳**：log 中出现大量 `OperationalError('unable to open database file')`、`Too many open files`、`getaddrinfo() thread failed to start`、yfinance silent rate limit，导致 L3 四个广度指标全部失败，但 stage 仍显示 `✔`。

最终报告 `final_stance = 中性偏谨慎`、`approval_status = approved_with_reservations`，但论据链严重污染：
- "宏观收紧 → 信用恶化 → 下跌趋势强化" 共振链的关键证据 `L1.get_net_liquidity_momentum` 是 2026-05-15 数据。
- "极端恐惧和空头拥挤支撑短期反弹条件" 的关键证据 `QQQ put/call 2.64` 来自 2026-05-18 到期的期权链。
- "估值压缩风险" 的核心数字 `PE 36.6（90%分位）` 来自一份用户已经禁用的 manual override。

---

## 1. 调查方法

按 `qiushi-skill:investigation-first` 提纲执行，七项注意全部落地：

| 调查动作 | 一手证据 |
| --- | --- |
| 必读文档建立基线 | [CLAUDE.md](CLAUDE.md)、[AGENTS.md](AGENTS.md)、[ARCHITECTURE.md](ARCHITECTURE.md)、[NEXT_STEPS.md](NEXT_STEPS.md)、[RUN_REVIEW_CHECKLIST.md](RUN_REVIEW_CHECKLIST.md)、[WORK_LOG.md](WORK_LOG.md) |
| 完整阅读 run 产物 | 全部 5 个 layer_cards、bridge_memos/bridge_0.json、synthesis_packet.json、analysis_packet.json、thesis_draft、critique、risk_boundary_report、analysis_revised、final_adjudication、llm_stage_diagnostics、run_summary、console_run_summary、context_brief、logic_vnext、chart_time_series.json |
| 原生 brief HTML 对照 | [vnext_brief_20260518_1940_20250409_0000.html](output/reports/vnext_brief_20260518_1940_20250409_0000.html)（重点核 evidence ref 按钮、风险卡片、置信度展示、时间戳暴露） |
| 控制台日志 | [output/logs/control_service/20260518_193311_613.log](output/logs/control_service/20260518_193311_613.log)（81 KB，覆盖采集、L1-L5、Bridge、Thesis、Critic、Risk、Reviser、Final 全链路） |
| 关键源码 | [src/agent_analysis/packet_builder.py](src/agent_analysis/packet_builder.py)、[src/agent_analysis/orchestrator.py](src/agent_analysis/orchestrator.py)（manual_overrides 注入路径） |
| 工作树校对 | 仅一份未跟踪 md，无其他改动；本审查不修改任何文件 |

下述结论均可在上述材料中复现。本报告所有数字、字段、时间均直接来自上述 artifact，没有任何估算。

---

## 2. P0 致命问题（直接破坏回测语义，必须立刻阻断报告发布）

### P0-1：L1 净流动性使用 2026-05-15 数据（前瞻 13 个月）

- 文件：[analysis_packet.json](output/analysis/vnext/20250409/analysis_packet.json) `raw_data.L1.get_net_liquidity_momentum.value`
- 内容：
  ```
  level=5889.27, momentum_4w=-107.17
  components: fed_assets=6728.5, tga=838.58, rrp=0.65
  date="2026-05-15"
  ```
- 性质：回测日是 2025-04-09，但这一指标的 value.date 是 2026-05-15，比回测日晚 13 个月。
- 危害链：
  - [L1.json](output/analysis/vnext/20250409/layer_cards/L1.json) `indicator_analyses.get_net_liquidity_momentum.reasoning_process` 写道："首先注意数据日期（2026-05-15）比大部分指标晚约13个月，视为后续情景"——LLM 已经识别出错位，但仍然把它纳入推理。
  - [synthesis_packet.json](output/analysis/vnext/20250409/synthesis_packet.json) `evidence_index.L1.get_net_liquidity_momentum.reasoning_process` 同样保留这段话。
  - [bridge_0.json](output/analysis/vnext/20250409/bridge_memos/bridge_0.json) `resonance_chains[0]` 把它列为"宏观收紧 → 信用恶化 → 下跌趋势强化"链的第一证据：`evidence_refs[0] = L1.get_net_liquidity_momentum`，mechanism 直接引用 `净流动性收缩（4周动量-107B）`。
  - [thesis_draft.json](output/analysis/vnext/20250409/thesis_draft.json) `environment_assessment` 写 `净流动性4周动量-107B抽水`。
  - [final_adjudication.json](output/analysis/vnext/20250409/final_adjudication.json) `key_support_chains[0].evidence_refs` 包含 `L1.get_net_liquidity_momentum`，weight=0.35。
- 关键事实：这条数据在 2025-04-09 当时根本不存在，其推导出的"三重抽水（Fed 缩表 + TGA 回补 + RRP 耗尽）"完全是 2026 年的状态。把它写进 2025-04-09 的回测，等于让模型用未来 13 个月的事实给当时下结论。

### P0-2：L2 SKEW 数据时间戳为 2026-05-15

- 文件：[analysis_packet.json](output/analysis/vnext/20250409/analysis_packet.json) `raw_data.L2.get_crowdedness_dashboard.value.skew_index`
- 内容：`{value: 145.77, date: "2026-05-15", source: "yfinance (^SKEW)"}`
- 性质：父级 date="2025-04-09"，但 SKEW 子项内部 date=2026-05-15——典型的"父级标签合规、子级实际穿越"。
- 危害链：
  - [L2.json](output/analysis/vnext/20250409/layer_cards/L2.json) `indicator_analyses.get_crowdedness_dashboard.current_reading` 直接使用 `SKEW=145.77（接近150阈值）`。
  - L2 `layer_synthesis` 把 SKEW 写入 `拥挤度方面，SKEW 接近 150 黑天鹅阈值`。
  - 通过 synthesis_packet 进入下游所有阶段。

### P0-3：L2 QQQ Put/Call OI 用的是 2026-05-18 到期期权链

- 文件：[analysis_packet.json](output/analysis/vnext/20250409/analysis_packet.json) `raw_data.L2.get_crowdedness_dashboard.value.qqq_put_call_ratio_oi`
- 内容：
  ```
  value=2.64
  date="2025-04-09"  ← 伪标签
  notes="基于到期日: 2026-05-18 的期权持仓量"
  ```
- 性质：notes 自己说明数据来自 2026-05-18 到期的期权链 OI 快照，但 date 被标成 2025-04-09。即使采集时是 2026 年，2025-04-09 当时根本无法看到这条 2026 年 5 月到期的期权链未平仓数据。
- 危害链：
  - L2 写入 `QQQ 看空/看多比率 2.64，极端看空仓位可能构成反向条件`。
  - bridge `cross_layer_claims[1]` 直接拿它做 supporting_facts `L2.QQQ put/call 2.64`，进入 `极端恐惧和空头拥挤可能引发短期反弹` 链。
  - final_adjudication `key_support_chains[1].evidence_refs` 引用 `L2.get_crowdedness_dashboard`，weight=0.25。

### P0-4：Damodaran 月度序列包含 2025-05 至 2026-05 共 13 个月未来行

- 文件：[analysis_packet.json](output/analysis/vnext/20250409/analysis_packet.json) `raw_data.L4.get_damodaran_us_implied_erp.value.monthly_series`
- 主行：`data_date=2025-04-01, sp500_level=5581.0, us_10y=4.24, erp_t12m_adjusted_payout=4.43, expected_return=8.85` ——**主值正确**。
- 越界子项（脚本扫描结果）：

  ```
  monthly_series[107].data_date = 2025-05-01
  monthly_series[108].data_date = 2025-06-01
  monthly_series[109].data_date = 2025-07-01
  ...
  monthly_series[119].data_date = 2026-05-01  (SP500=7209, expected_return=8.76)
  ```

- 性质：虽然 L4 LLM 应当只读主行，但 monthly_series 包含完整的 13 行未来数据，LLM 任何时候若用 "最新" 趋势就会穿越。chart_time_series 这条路径已经有 `future_rows_dropped` 裁剪，但 prompt 这条路径没有同步裁剪。

### P0-5：未启用的 manual_overrides 仍被注入 L4 prompt

- 关键事实：
  - meta：`manual_override_active=false`, `manual_override_count=0`（[analysis_packet.json](output/analysis/vnext/20250409/analysis_packet.json) `meta`）。
  - packet：`manual_overrides.active=false`，但 `manual_overrides.metrics` 完整保留 6 个指标，其中 `get_ndx_pe_and_earnings_yield.value` 含 `PE_TTM=36.6, PE_TTM_percentile_10y=90, PB=10.49, PB_percentile_10y=100`。
- 注入路径（源码核对）：
  - [packet_builder.py:232](src/agent_analysis/packet_builder.py#L232) 直接将完整 `manual_overrides` 对象保存进 `AnalysisPacket`，没有按 active 过滤。
  - [orchestrator.py:286](src/agent_analysis/orchestrator.py#L286) 在每层 prompt 注入 `_build_layer_manual_overrides(packet, layer)`。
  - [orchestrator.py:753-767](src/agent_analysis/orchestrator.py#L753-L767) 实现只按 layer 过滤 function_id，从不在 `active=false` 时清空 metrics：
    ```python
    return {
        "active": bool(overrides.get("active")),
        "date": overrides.get("date", ""),
        "metrics": {
            function_id: metric
            for function_id, metric in metrics.items()
            if function_id in layer_function_ids
        },
    }
    ```
- 污染传播：
  - [L4.json](output/analysis/vnext/20250409/layer_cards/L4.json) `layer_synthesis` 写道："若假定 NDX 估值处于历史高位（参考 manual_overrides 中未启用的数据暗示 PE 36.6，10年分位90）"。
  - L4 这段被原样并入 [synthesis_packet.json](output/analysis/vnext/20250409/synthesis_packet.json) `layer_summaries[3].layer_synthesis`，再喂给 Thesis。
  - [thesis_draft.json](output/analysis/vnext/20250409/thesis_draft.json) `valuation_assessment` 接力：`若假定 NDX 估值偏高（参考 manual_overrides 暗示 PE 36.6，10年分位 90）`。
  - [risk_boundary_report.json](output/analysis/vnext/20250409/risk_boundary_report.json) `failure_conditions[2].condition` 写：`若 NDX 核心盈利增速显著低于当前高估值（PE 36.6 约 90%分位）的假设`。
  - [analysis_revised.json](output/analysis/vnext/20250409/analysis_revised.json) `revised_thesis.valuation_assessment` 仍保留 `manual override 暗示 PE 36.6（90%分位）`。
  - [final_adjudication.json](output/analysis/vnext/20250409/final_adjudication.json) `must_preserve_risks[0]` 写："估值压缩风险：实际利率 2.07% 高位 + PE 36.6（90%分位，manual override）"。
  - HTML 报告 hero 区、风险卡、failure_conditions 三处重复展示此条。
- 性质：违反 CLAUDE.md "不得编造历史胜率、回测收益、样本区间或概率数字，除非 evidence refs 明确提供" 的硬规则。控制台 active=false 应该意味着这条数据完全不存在；现在的实现把它变成了"暗示性事实"，对外行读者就是事实。

### P0-6：DataIntegrity 自己检测到泄露但不阻断

- 文件：[logic_vnext.json](output/analysis/vnext/20250409/logic_vnext.json) `__LOGIC__.data_integrity_report`
- 内容：
  ```
  confidence_percent: 84.6
  notes: "5 个指标因回测前瞻风险被跳过。；1 个指标存在晚于回测日的数据日期，
          示例: Net Liquidity (Fed - TGA - RRP): value.date=2026-05-15；
          数据完整性偏低，最终结论需要更保守。"
  layer_breakdown:
    L1: 8/8=100%
    L2: 10/10=100%
    L3: 5/7=71.4%
    L4: 1/4=25%
    L5: 10/10=100%
  ```
- 性质：检查器看到了 2026-05-15 越界，但只把整体置信度减到 84.6%，没有触发"不可发布"状态；同时它没有递归扫描，没有捕捉 P0-2（SKEW 子项越界）、P0-3（put/call 期权链越界）、P0-4（Damodaran monthly_series 越界）。漏扫范围远大于已扫范围。
- 同时 [schema_guard_report.json](output/analysis/vnext/20250409/schema_guard_report.json) 显示 `passed=true, structural_issues=[], consistency_issues=[], missing_fields=[]`，但本报告 P1 段会列出多个明显的结构问题它都没看到。

### P0-7：L3 全部广度指标失败但 stage 报 ✔（silent failure）

- log 证据（[20260518_193311_613.log](output/logs/control_service/20260518_193311_613.log)）：
  - 49 + 19 + 25 ... 多轮成分股下载失败（`possibly delisted`、`OperationalError('unable to open database file')`、`DNSError`、`Too many open files`、`yfinance returned empty frame (likely silent rate limit)`）。
  - 但每一轮失败后 stage 仍打印：`- 调用 get_advance_decline_line... ✔`、`get_percent_above_ma... ✔`、`get_new_highs_lows... ✔`、`get_mcclellan_oscillator_nasdaq_or_nyse... ✔`。
- 实际产物：
  - [L3.json](output/analysis/vnext/20250409/layer_cards/L3.json) `indicator_analyses` 中 4 个广度指标 `current_reading="数据不可用"`、`normalized_state="unknown"`。
  - [analysis_packet.json](output/analysis/vnext/20250409/analysis_packet.json) `raw_data.L3` 中 4 个广度指标 value=None。
  - 但 `facts_by_layer.L3.core_signals` 仍将 `Advance/Decline Line (NDX100) | 值={'level': None, ...}` 当作"关键事实"展示；context_brief 把它们列入 `layer_highlights.L3`。
- 后果：报告对外说"L3 内部结构呈现极端集中但广度数据缺失"，看起来是诚实的，但 L3 状态在 `context_brief` 中被打成 `neutral`、`facts_by_layer.L3.summary` 写 `内部健康度状态: neutral` — 完全和"数据缺失"自相矛盾。

### P0-8：回测模式仍向 yfinance 请求"当下"日期

- log 证据：
  ```
  ERROR - $^VIX: possibly delisted; no price data found  (1d 2026-05-19 -> 2026-05-19)
  ```
- 性质：在 backtest_date=2025-04-09 的运行中，cached_yf_download 仍试图 fetch `2026-05-19`（今天的 VIX）。失败后回退到 12 小时内的本地缓存，正巧拿回 `(日期: 2025-04-09)`，因此最终 value=33.62 是合规的——但这是 fallback 的运气，不是设计。如果缓存过期，会把 2026-05 的 VIX 当成 2025-04-09 入库，与 P0-1/P0-2/P0-3 完全同构。

---

## 3. P1 严重问题（破坏报告可信度与可审计性）

### P1-1：Bridge 把 CNN FGI 子指标矛盾错配为跨层冲突

- [bridge_0.json](output/analysis/vnext/20250409/bridge_memos/bridge_0.json) `typed_conflicts[1]` 与 `conflicts[1]`：
  - 标题：`L2_market_momentum_greed_vs_L5_downtrend`
  - 描述："L2 CNN Fear & Greed 子指标市场动量评分为 98.2（极端贪婪），但 L5 QQQ 价格处于强劲下跌趋势"。
- 实际数据（[analysis_packet.json](output/analysis/vnext/20250409/analysis_packet.json) `raw_data.L2.get_cnn_fear_greed_index.value.sub_metrics`）：
  - Market Momentum (S&P500) = 98.2
  - Stock Price Strength = 49
  - Stock Price Breadth = 33.2
  - Put/Call Options = 95
  - Market Volatility (VIX) = 50
  - Junk Bond Demand = 26
  - Safe Haven Demand = 89
  - 总分 = 9.5（extreme fear）
- 性质：`Market Momentum 98.2` 是 CNN FGI 内部 7 个子指标之一，本来就和其他子指标在不同方向。Bridge 把这个 sub-metric 单独拎出来与 L5 ADX 37.79 并列，本质是把一个**复合情绪指标的内部子项**升格成"一个 L2 独立读数"，再用来和 L5 形成"跨层冲突"。这是误读。
- 升级路径：
  - thesis_draft / analysis_revised 把它从 bridge 的 `severity=medium` 升级为 `severity=high`，进入 `retained_conflicts`。
  - 最终报告把它列入两大 "high severity" 冲突之一，深度污染对市场状态的判断。

### P1-2：Bridge 的 supporting_facts 用中文短语而非 function_id

- [bridge_0.json](output/analysis/vnext/20250409/bridge_memos/bridge_0.json) `cross_layer_claims[0].supporting_facts`:
  ```
  ["L1.净流动性收缩", "L1.实际利率高位", "L2.HY OAS极端", "L5.ADX强下跌"]
  ```
- 影响 HTML：[vnext_brief_20260518_1940_20250409_0000.html](output/reports/vnext_brief_20260518_1940_20250409_0000.html) 中出现这些 ref 按钮：
  ```
  data-ref="L1.get_净流动性收缩"
  data-ref="L1.get_实际利率高位"
  data-ref="L2.get_HY OAS极端"
  data-ref="L2.get_CNN Fear & Greed 9.5"
  data-ref="L2.get_QQQ put/call 2.64"
  data-ref="L5.get_ADX强下跌"
  data-ref="L5.get_RSI 23.11超卖"
  ```
- 后果：这些按钮无法对应任何真实 function_id，用户点击后**找不到证据卡**，UI 上是死链；且这些短语本质是 LLM 自由文本，模板没有做语义校验。

### P1-3：Bridge transmission_path 多个关键字段为空

- [bridge_0.json](output/analysis/vnext/20250409/bridge_memos/bridge_0.json) `transmission_paths`：
  - 3 条 path 的 `path_id` 全部等于 `"transmission_path"`（违反唯一性）。
  - 3 条 `evidence_refs` 全是 `[]`。
  - 3 条 `implication` 全是 `""`。
- `resonance_chains[0].chain_id="resonance_chain"`、`description=""`。
- schema_guard `passed=true` 没识别这些问题（结构 + 一致性都该报错）。

### P1-4：bridge / thesis 的 description 与 implication 一字不差重复

- 两个 typed_conflict 的 `description == implication`（一致复制）。
- thesis_draft.retained_conflicts、analysis_revised.remaining_conflicts、final 的 retained 全部继承这一重复。
- 视觉上让风险看起来"被反复强调"，但实际信息只有一份。

### P1-5：报告 must_preserve_risks 在 HTML 重复展示 3 次

- 同一组三条风险（含被污染的 PE 36.6）出现在：
  - 首页 hero（`final_stance + must_preserve_risks` 卡片）
  - 最终判断 section
  - failure_conditions section
- 一旦上游被 P0-5 污染，重复展示会把"manual override" 标签变成读者阅读的主旋律。

### P1-6：HTML 上"指标采集时间 2026-05-18"暴露给读者

- 每张指标卡显示：`指标数据采集时间 2026-05-18 11:33 UTC`、`L1.get_10y2y_spread_bp · 2026-05-18T11:33:14.492035+00:00`。
- 报告同时声称 `数据日期 2025-04-09`，但没有一个面板向普通读者解释"采集时间晚于数据日期是正常的、但有些指标 value 的日期本身也穿越到了 2026"。
- 后果：要么读者错以为所有数据都来自 2026 年，要么错以为所有 2026 时间戳都是采集时间。两种误解都背离实际：实际是混合状态。

### P1-7：HTML 报告显示英文 safe/warning，无解释，视觉无差异

- [risk_boundary_report.json](output/analysis/vnext/20250409/risk_boundary_report.json) `boundary_status`：
  ```
  valuation_compression: warning
  earnings_miss: warning
  liquidity_shock: warning
  concentration_collapse: warning
  breadth_deterioration: warning
  sentiment_reversal: warning
  trend_breakdown: safe
  ```
- HTML 直接把英文标签贴出来，没有中文化、没有阈值说明、没有判定依据；`safe` 与 `warning` 视觉差异不足。
- 同时这些状态由 LLM 自填，与 L3 广度数据缺失矛盾（`breadth_deterioration: warning` 是基于没有数据的判断）。

### P1-8：HTML 顶部"置信度 medium"没有依据展示

- final_adjudication `confidence=medium`。
- 但 logic_vnext.data_integrity_report `confidence_percent=84.6%`，L4 `25%`，L3 `71.4%`。
- HTML 没有让读者看到这种差距，只显示一个 `中`，等于把数据缺口和模型自评混为一谈。

### P1-9：QQQ/QQEW 与 L5 技术指标用的是 2025-04-08，不是 2025-04-09

- [analysis_packet.json](output/analysis/vnext/20250409/analysis_packet.json) 中：
  - `L3.get_qqq_qqew_ratio.value.date = 2025-04-08`
  - `L5.get_rsi_qqq.value.date = 2025-04-08`、`get_atr_qqq=2025-04-08`、`get_adx_qqq=2025-04-08`、`get_macd_qqq=2025-04-08`、`get_obv_qqq=2025-04-08`、`get_volume_analysis_qqq=2025-04-08`、`get_price_volume_quality_qqq=2025-04-08`、`get_donchian_channels_qqq=2025-04-08`、`get_multi_scale_ma_position=2025-04-08`
  - `current_price=416.06`（即 4/8 收盘价）
- L5.notes 自己写：`分析基于 2025-04-08 数据`。
- L1 中 FRED 多数指标 `date=2025-04-09`，L2 VIX/VXN/HYG `date=2025-04-09`。
- 同一份报告里至少四种数据日期口径并存：`2025-04-08 / 2025-04-09 / 2025-04-01 / 2026-05-15`。
- 后果：L5 实际是用 4/8 收盘判断 4/9 决策；HTML 没有任何位置把这种"日期窗口"明确告诉读者。读者会以为"价格 416.06 是 4/9 当日收盘"，而 4/9 当日 QQQ 大幅反转（盘后已是另一段历史）。

### P1-10：`backtest_data_boundaries` 字段缺失（文档承诺与实现脱节）

- [NEXT_STEPS.md](NEXT_STEPS.md) 和 [WORK_LOG.md](WORK_LOG.md) 2026-05-18 段宣称："`DataCollector.run()` 新增 `backtest_data_boundaries`，集中记录本次回测哪些指标被跳过、为什么跳过、对应的 effective_date"。
- 实际：在 [analysis_packet.json](output/analysis/vnext/20250409/analysis_packet.json) 中全文搜索 `backtest_data_boundaries`，结果为空；meta 只有 `manual_override_count`、`manual_override_active` 等字段。
- 现状：跳过信息散落在每个指标的 `backtest_skipped: true` 标记中（共 5 个，分布在 L3/L4），没有顶层汇总。
- 后果：后续 prompt 阶段、HTML 报告无法以一处入口告诉读者"本次跳过了什么、为什么"。

### P1-11：context_brief / facts_by_layer 把 None 当作"关键事实"展示

- [context_brief.json](output/analysis/vnext/20250409/context_brief.json) `layer_highlights.L3`：
  ```
  Advance/Decline Line (NDX100) | 值={'level': None, 'date': None, 'momentum': None}
  McClellan Oscillator | 值={'level': None, 'date': None, 'momentum': None}
  ```
- [analysis_packet.json](output/analysis/vnext/20250409/analysis_packet.json) `facts_by_layer.L3.core_signals` 与 `facts_by_layer.L3.summary` 同样收录这些 None 值。
- 后果：进入 prompt 时这些"事实"看起来是有效观察对象，模型可能基于"指标存在"做错误推理；HTML 也按"关键事实"展示，让普通读者以为有数据。

### P1-12：L3 layer state = "neutral" 与实际"4 个广度缺失"自相矛盾

- [context_brief.json](output/analysis/vnext/20250409/context_brief.json)：未直接给 state，但 [analysis_packet.json](output/analysis/vnext/20250409/analysis_packet.json) `facts_by_layer.L3.summary` 写："内部健康度状态: neutral"；`facts_by_layer.L4.summary` 写："估值状态: neutral"。
- 实际：L3 5 个核心广度指标 4 个为 None；L4 4 个核心估值指标 3 个被 skip、剩下 1 个是美国大盘背景锚（非 NDX 专属）。
- 后果：packet_builder 的 layer state fallback 文本不考虑实际数据完整度，把"无法判断"伪装成"中性"，下游 prompt 接收到错误的层状态。

### P1-13：L2 第一次 LayerCard 校验失败，第二次才通过（但 evidence_refs 仍是 dict）

- [llm_stage_diagnostics.json](output/analysis/vnext/20250409/llm_stage_diagnostics.json) `stages.l2.attempts=2`，第 1 次报 10 个 `string_type` 错误（evidence_refs 应为字符串，实际为 dict）。
- 第 2 次成功，但 L2 输出 evidence_refs 仍部分是粗糙短语（e.g. `"get_vix"`），不带 `LX.` 前缀，下游 HTML 拼按钮时会出现 `L2.get_get_vix` 形态的混乱链接。

### P1-14：FedFunds / M2 月度数据 first-reported 风险未处理

- [analysis_packet.json](output/analysis/vnext/20250409/analysis_packet.json) L1：`get_fed_funds_rate.value.date=2025-04-01`、`get_m2_yoy.value.date=2025-04-01`。
- 但这些月度数据真实发布日通常滞后 30-60 天；2025-04-09 当时市场不可能看到 2025-04-01 的最终 M2 YoY、FedFunds 月均。
- WORK_LOG.md 2026-05-18 已经承认 "ALFRED first-vintage、财报 first-reported、point-in-time universe 和 LLM 训练后验知识列为后续严格回测升级"，所以这条不是"修复倒退"，但作为本次审查必须记录的边界事实。

### P1-15：报告路径在两个 summary 中不一致

- [run_summary.json](output/analysis/vnext/20250409/run_summary.json) `report_path = ""`（空）。
- [console_run_summary.json](output/analysis/vnext/20250409/console_run_summary.json) `report_path = ".../vnext_brief_20260518_1940_20250409_0000.html"`、`native_brief` 与 `workbench` 字段齐全。
- 后果：审计/外部脚本如果以 `run_summary.json` 为入口，会拿不到产物路径。

---

## 4. P2 中等问题（影响审计与读者体验，不直接误导结论）

### P2-1：HTML token usage 暴露原始 Python dict

- [final_adjudication.json](output/analysis/vnext/20250409/final_adjudication.json) `token_usage.total = {prompt: 164817, completion: 45297, total: 210114}`。
- HTML 直接渲染 dict 结构而不是审计表格；普通读者只会看到一堆数字，无法判断"高 token 是否意味着 prompt 异常"。

### P2-2：logic_vnext.market_regime_analysis.risk_flags 6 项重复

- [logic_vnext.json](output/analysis/vnext/20250409/logic_vnext.json) `__LOGIC__.market_regime_analysis.risk_flags` 有 6 条，但只有 3 个 unique。
- legacy_adapter 在拼接时没去重。

### P2-3：logic_vnext.conflict_rationale 文本拼接形式拗口

- 同一文本反复出现 "描述句 含义是：描述句 含义是：..."，因为 description 与 implication 相同被串接 2 次。
- 阅读体验差。

### P2-4：bridge `cross_layer_claims[1]` confirming_indicators 与 supporting_facts 都使用"短语+数字"

- 例：`supporting_facts = ["L2.CNN Fear & Greed 9.5", "L2.QQQ put/call 2.64", "L5.RSI 23.11超卖"]`
- 与 P1-2 同类，但更宽：把指标读数也塞进 ref 字段。

### P2-5：HTML 的 evidence_refs chip 与 typed_conflict 描述不去重

- HTML 多处显示同一冲突的同样描述（如铜金比 vs 消费风格冲突）超过两次。

### P2-6：yfinance 长退避循环消耗大量壁钟时间

- log 中可见 60s/10s 退避 × 多轮，单次 L3 指标失败需要 ≥ 120 秒；整个 run（数据采集 6 分钟，LLM 全链路约 10 分钟）相当一部分时间花在"假装重试一个根本拿不到的数据"。
- 同时多线程下载 + SQLite cache 引发 `OperationalError`，进一步放大延迟。

### P2-7：HTML / packet 暴露 collection_timestamp_utc 但无聚合面板

- 每个指标 `collection_timestamp_utc=2026-05-18T11:33:xx`，HTML 单独显示在每张卡上，没有顶部聚合"本次采集窗口 11:33-11:40"或"最后采集时间"。

---

## 5. 根因分类与传播链

下面是 30 条问题的根因归类，可作为后续修复 backlog 的 grouping 索引：

| 根因类别 | 问题编号 | 说明 |
| --- | --- | --- |
| **采集端未对回测日截尾** | P0-1, P0-2, P0-3, P0-4, P0-8, P1-9 | `get_net_liquidity_momentum`、`get_crowdedness_dashboard`、`get_damodaran_us_implied_erp.monthly_series` 等指标函数收到 `end_date` 但在内部数据序列上未做截尾；cached_yf_download 仍以"今天"为锚 |
| **packet → prompt 注入未隔离** | P0-5 | `packet_builder.build` 无条件保存 `manual_overrides`；`orchestrator._build_layer_manual_overrides` 不在 `active=false` 时清空 metrics |
| **质量闸门只报告不阻断** | P0-6, P0-7 | DataIntegrity 算 84.6% 后照常放行；schema_guard `passed=true` 漏检空字段/重复 id/None 当事实 |
| **Bridge / Thesis 推理污染** | P1-1, P1-2, P1-3, P1-4 | LLM 在 supporting_facts、conflict 字段中填中文短语和重复文本，模板没有结构校验 |
| **报告表达放大错误** | P1-5, P1-6, P1-7, P1-8, P2-1, P2-2, P2-3, P2-4, P2-5 | HTML 多处重复、英文标签直出、置信度无依据、ref chip 死链；放大效应来自上游污染 + 模板不做去重 |
| **数据完整度伪装** | P1-11, P1-12, P0-7 | facts_by_layer / context_brief 把 None 当事实展示，layer state 用"neutral"掩盖严重缺口 |
| **文档承诺与实现脱节** | P1-10 | `backtest_data_boundaries` 字段在文档中存在，在产物中不存在 |
| **运行环境失稳** | P2-6 + log 全篇 | yfinance silent rate limit + SQLite 并发 + 文件句柄耗尽 + DNS 线程失败，L3 抓取彻底瘫痪 |
| **未来工作未覆盖（已承认）** | P1-14 | first-reported、ALFRED vintage 等问题 NEXT_STEPS 已列后续，但本次回测产物仍受影响 |
| **审计冗余 / 模板偷懒** | P1-15, P2-2, P2-3, P2-7 | run_summary 与 console_run_summary 不一致，legacy_adapter 拼接不去重 |

### 主要污染传播图（按文本流向）

```
采集端（tools_L1/L2/L4/L5 + cached_yf_download）
    │ 未按 end_date 截尾的指标 / inactive manual_overrides
    ▼
analysis_packet.json
    │ raw_data 含 2026-05-15 / 2026-05-18 / 2026-05-01 等日期
    │ manual_overrides.metrics 含 PE 36.6（active=false）
    ▼
orchestrator → L1-L5 prompt
    │ _build_layer_manual_overrides 把 inactive metrics 注入 L4 prompt
    ▼
layer_cards/L*.json
    │ L1 自承认时间错位但继续推理；L4 写入 "PE 36.6 暗示"
    ▼
synthesis_packet.json
    │ 把 L4 layer_synthesis 原文转给 Thesis prompt
    ▼
bridge_0.json
    │ resonance_chain 用越界 net_liquidity 作首要证据
    │ typed_conflict 把 CNN FGI sub-metric 当独立 L2 读数
    ▼
thesis_draft.json → critique.json → risk_boundary_report.json
    │ failure_conditions 直接写 "PE 36.6 约 90%分位"
    ▼
analysis_revised.json → final_adjudication.json
    │ must_preserve_risks 写 "PE 36.6（90%分位，manual override）"
    ▼
logic_vnext.json + vnext_brief HTML
    │ 多处重复、按钮死链、英文标签未本地化
```

---

## 6. 不可发布判定

按 [RUN_REVIEW_CHECKLIST.md](RUN_REVIEW_CHECKLIST.md) "回测与快照专项检查"：

| 检查项 | 应通过标准 | 实际结果 |
| --- | --- | --- |
| 回测有效日期 | 所有进入 agent 上下文的数据、新闻、图表行都不晚于 backtest_date / effective_date | **未通过**：P0-1, P0-2, P0-3, P0-4 |
| 跳过项是否明示 | `backtest_data_boundaries` 列出被跳过的指标、原因和未来升级路径 | **未通过**：P1-10（字段不存在） |
| 当前网页是否误入回测 | 当前网页数据没有在历史回测中默认充当当时证据 | **未通过**：P0-2（SKEW）、P0-3（期权链）来自当前采集 |
| yfinance 成分股代理 | 回测模式未自动触发 yfinance 成分股基本面批量代理 | **基本通过**：L4 三项已跳过；但 L3 成分股下载未跳过且大规模失败（P0-7） |
| 新闻侧栏 | 新闻只作为辅助 sidecar | **N/A**：本次未启用新闻 |
| LLM 后验风险 | 报告承认新模型可能有后验知识 | **未在 HTML 体现** |
| 数据快照不可变 | 分析消费同一份数据包 | **通过**：单次采集，未切换网络 |
| 研究候选证据 | research_candidate / manual_review_required 未进入核心证据 | **不适用 / 但 inactive manual 被注入** —— 违反类似原则 |

结论：**不通过**，至少 4 个 P0 检查项失败。这份产物若以"2025-04-09 NDX 投研报告"的名义对外发布，会用 13 个月之后的事实 + 一个被用户禁用的人工估值，倒推 2025-04-09 当时的判断，是研究伦理与回测纪律的双重越界。

---

## 7. 本次审查刻意没有做的事

按用户指令 "不要修复或推脱责任"、"不要修改任何内容"：

- 没有动任何源码、prompt、合约、HTML。
- 没有重新跑 collector / orchestrator / reporter。
- 没有删除或重命名 `analysis_packet.json` 等任何产物（即使发现了 P0 越界）。
- 没有更改 `manual_data.local.json` 的 active 状态。
- 没有清理 `data_cache/yfinance/` 中导致 SQLite 并发 / 文件句柄异常的缓存文件。
- 没有合并 / 删除根目录另一份同主题文档。

本报告仅作为**问题清单 + 证据指引**，等待后续按 NEXT_STEPS 节奏统一处理。

---

## 8. 后续修复建议优先级（不在本次执行范围）

只列出顺序，不展开实现细节：

1. **阻断未来数据进入 packet**：补强采集端 end_date 截尾（P0-1 ~ P0-4, P0-8），并把 DataIntegrity 升级为可阻断闸门（P0-6）。
2. **隔离 inactive manual_overrides**：让 `active=false` 时 metrics 真正不进入任何 layer prompt（P0-5）。
3. **修 silent failure → false success**：L3 大规模下载失败时不能打 ✔；context_brief / facts_by_layer 不能把 None 当事实（P0-7、P1-11、P1-12）。
4. **修 Bridge / Thesis prompt 约束**：禁止 supporting_facts、evidence_refs 出现自由文本短语，强制 `LX.function_id` 格式（P1-2, P1-3, P1-4, P1-1）。
5. **修报告表达**：HTML 顶部统一展示数据日期 / 采集时间 / 跳过项 / 数据完整度 / 置信度依据，去重 must_preserve_risks，本地化 safe/warning（P1-5 ~ P1-8、P2-*）。
6. **补 backtest_data_boundaries 顶层字段**（P1-10），让跳过结构可一处审计。
7. **修复运行环境**：cached_yf_download 在回测模式下不再尝试当下日期；SQLite cache / 文件句柄 / DNS 异常根因调查（P0-8、P2-6）。
8. **可选：L5 数据日期对齐**：明确"分析基于 T-1 收盘"语义，HTML 显示窗口（P1-9）。

---

## 9. 一句话结论

这份 2025-04-09 回测报告的可信度问题不是局部瑕疵，而是**采集 → packet → prompt → 报告**四个环节同时被破坏。在 P0 全部修好之前，它不应被当作"2025-04-09 NDX 投研判断"的对外材料；在本次审查范围内，所有问题已经被定位到具体文件、字段和源码行，剩下的是按顺序修复，而不是再去解释。
