# O10 专审：OBV 同名两值——身世、归因与处置建议

- 工单：O10（老板 2026-08-16 裁决：先查数据获取环节为何出现两个数，再定以谁为准）
- 对应病灶：A11（同名指标多值），常设检查 PC-08 在裁决前保持红灯
- 审查人：专审子代理（只读；未触碰后台运行中的 `t53_acceptance_20260816`）
- 证据 run：`output/analysis/vnext/c6_baseline_20260815/`（effective_date 2026-08-15，数据截止 2026-08-14）

---

## 一、结论先行

1. **两个值来自同一个文件、同一个计算公式、同一个数据源，唯一的差别是采样窗口长度**：确定性快照用 420 天窗口（`src/tools_L5.py:276`），综合技术指标用 365 天窗口（`src/tools_L5.py:634`）。OBV 是从窗口第一根 K 线开始累加的"带符号成交量累计和"，**它的绝对值天然依赖累加起点**，窗口不同则起点不同，绝对值必然不同。
2. **这是口径差异，不是 bug**。我用快照自带的 `raw_ohlcv`（289 根日 K，2025-06-23 至 2026-08-14）截断到 365 天窗口起点（2025-08-15，251 根）重算，**逐位复现了 493,790,400**；全窗口重算则逐位复现 901,260,500。差异 407,470,100 恰好等于两窗口起点之间那段日子的净带符号成交量。
3. **两个值各自内部都是自洽的**：快照值被重算带（recompute belt）以零容差独立复算通过；综合指标值也可从同一批原始数据复现。不存在缓存陈旧、单位错位或重复累加。
4. **建议：绝对值以确定性快照（901,260,500 这一支）为准；另一支的处置首选"统一为一个来源"——把 `get_qqq_technical_indicators` 的窗口对齐 420 天（一行改动），或让它直接复用快照结果**。理由见第五节。更深一层的建议：OBV 绝对水位本身没有跨窗口可比性，系统真正有语义的是 OBV 的变化量与趋势词，值得在契约层面把"绝对水位"降级为审计字段。
5. PC-08 应在修复落地（同一来源只算一次，或窗口对齐后两值自然一致）后再转绿。

---

## 二、两个值的身世（文件:行号）

### 值 A：901,260,500 —— 确定性快照

- 计算入口：`get_l5_deterministic_snapshot`（`src/tools_L5.py:273`）
  - 窗口：`start_date = effective_date - timedelta(days=420)`（`src/tools_L5.py:276`）
  - 取数：`cached_yf_download("QQQ", start=…, end=…, interval="1d", auto_adjust=False)`（`src/tools_L5.py:281-288`），本次 run 实际来源 **Twelve Data**（artifact `source_name=Twelve Data`）
  - 时点纪律：`_filter_daily_frame_to_effective_date` 剔除晚于 effective_date 的行（`src/tools_L5.py:104-110`，调用点 `:292`）
  - 装配：`_build_l5_snapshot_from_frame`（`src/tools_L5.py:153`），其中 `indicators = calculate_technical_indicators_yf(df)`（`:166`），`exact_values["obv"] = indicators.get("obv")`（`:190`）
- artifact 事实（`prompt_audit/L5/attempt_1.payload.json` → `layer_raw_data.get_l5_deterministic_snapshot`）：
  - `row_count=289`，首行 2025-06-23，末行 2026-08-14；`formula_engine=ta`
  - 快照自带 `ohlcv_sha256` 与审计专用 `recompute_input.raw_ohlcv`（`src/tools_L5.py:234,263-269`）
- 独立复算：重算带 `_l5_recompute_values` 的 OBV 段（`src/recompute_belt.py:1450-1456`）以 `EPSILON_EXACT` 零容差比对（`src/recompute_belt.py:1507-1510`），`recompute_report.json` 实测 `pipeline_value=901260500, recomputed=901260500.0, status=match`。

### 值 B：493,790,400 —— 综合技术指标（及其分身）

- 计算入口：`get_qqq_technical_indicators`（`src/tools_L5.py:627`）
  - 窗口：`start_date = effective_date - timedelta(days=365)`（`src/tools_L5.py:634`）
  - 取数：同一个 `cached_yf_download('QQQ', …)`（`src/tools_L5.py:640`），同一次 run 同样标 **Twelve Data**，同一 effective_date，同样过 `_filter_daily_frame_to_effective_date`（`:645`）
  - 计算：**同一个函数** `calculate_technical_indicators_yf(df)`（`:650`）
- OBV 公式本体（两个值共用）：`src/tools_L5.py:486-492`
  - ta 库可用时：`OnBalanceVolumeIndicator(df["close"], df["volume"]).on_balance_volume()`（`:489`）
  - 否则内部实现：`(np.sign(df['close'].diff()) * df['volume']).fillna(0).cumsum()`（`:491`）
  - 取末位：`indicators["obv"] = int(obv.iloc[-1])`（`:492`）
  - 关键性质：OBV 是 **cumsum**，其绝对水位 = 窗口内每一天"涨加量、跌减量"的累计，**起点任取，水位随之平移**。
- 分身 1：`get_obv_qqq`（`src/tools_L5.py:907-927`）不重新取数，直接复用 `get_qqq_technical_indicators` 的结果（`:909`），`level` 即 493,790,400（`:914`），并携带 `change_20d_pct=-10.88%`、`trend=distribution`（`:915-916`）。
- 分身 2：`get_qqq_technical_indicators` 内嵌 `obv` 字段本身。

### 历史对照（A11 原始证据）

- T47 run（2026-07-31 快照）：快照 OBV=670,737,927 vs 分项 353,656,127，差约 1.9 倍——`investigation_reports/20260806_t47_context_review/phase1/L5.md:30-43`（F-01，14 项跨块核对中唯一不一致项）；汇总见 `investigation_reports/20260806_t47_context_review/02_复核与收口.md:24,49` 与 `03_根本审查总报告.md:94`（A11 行）、`:206`（常设检查第 8 条立项）。
- 两次 run 的差值（407,470,100 / 317,081,800）不同，但结构完全一致：都是"快照 420 天窗 vs 分项 365 天窗"。差值逐日变动恰是窗口长度差那段区间净成交量的滚动结果，进一步印证窗口假说。
- 说明：任务书提示的 `investigation_reports/20260814_total_reorg/01_总梳理报告.md` 中实际检索不到 "OBV"/"A11" 字样（该文件 335 行，已对全文做大小写不敏感检索），A11 的原始带行号证据在上一段所列 2026-08-06 报告组内；`20260816_新对话交接_清空待办计划.md:46,70` 有 O10 的裁决原文。

---

## 三、差异归因：口径差异，非 bug

数值实验（基于 run 内 `checker_input_snapshot.json` → `recompute_inputs.get_l5_deterministic_snapshot.raw_ohlcv`）：

| 实验 | 结果 | 对应 artifact 值 | 是否逐位一致 |
|---|---|---|---|
| 全窗口 289 根（2025-06-23 起）按 OBV 定义累加 | 901,260,500 | 快照 `exact_technical_values.obv` | ✅ |
| 截断到 ≥2025-08-15 的 251 根（= 365 天窗）同法累加 | 493,790,400 | `get_qqq_technical_indicators.obv` / `get_obv_qqq.level` | ✅ |

结论：**两值之差 407,470,100 恰好是 2025-06-23 至 2025-08-14 这 38 个交易日的净带符号成交量**。数据源（Twelve Data）、价格序列（不复权日频收盘）、公式引擎（ta）、时点过滤全部相同，唯一变量是 `timedelta(days=420)` vs `timedelta(days=365)`（`src/tools_L5.py:276` vs `:634`）。

补充一个口径细节：20 日变化率 `obv_20d_change_pct` 的分母是 `|obv[-20]|`（`src/tools_L5.py:496-498`），而 `obv[-20]` 本身也随窗口起点平移，所以**变化率的百分数同样是锚点敏感的**；真正窗口无关的量是"OBV 在 N 日内的净增减股数"（cumsum 的差分）。本次两值对应的 20 日增减方向一致（同为下降、同为 distribution），未造成方向性误判。

---

## 四、下游流向

两个值都只在 **L5 层**出现（PC-08 扫描 L1-L5 全部 payload 与 layer_cards，仅 L5 命中；`output/analysis/vnext/c6_baseline_20260815/persistent_checks_report.json:57-61`）。

- 入口：`src/core/collector.py:190-202` 把 `get_l5_deterministic_snapshot`、`get_qqq_technical_indicators`、`get_obv_qqq` 同时列入 L5 采集清单，三者全部进入 L5 的 `layer_raw_data`，即同一份材料里 OBV 出现三次（901,260,500 一次、493,790,400 两次）。
- L5 层卡（`layer_cards/L5.json`）：
  - `get_l5_deterministic_snapshot` 的 `current_reading` 引用 901,260,500；
  - `get_obv_qqq` 的 `current_reading` 引用 493,790,400 + "-10.88% + distribution"；
  - L5 模型自己在 `missing_or_weak_indicators` 中显式标记："OBV 数值在 deterministic snapshot (901260500) 与 get_obv_qqq (493790400) 之间存在不一致，已标记为数据冲突"（`prompt_audit/L5/attempt_1.parsed.normalized.json`）。即本次模型按规则选择了快照为锚，并把冲突挂了出来。
- 更下游（`thesis_draft.json`、`final_adjudication.json`、`risk_boundary_report.json` 等）：全文检索确认**没有任何一处引用 OBV 绝对水位数字**，只引用定性量——"OBV 派发"、"OBV 20日 -10.88%"，且终审把"OBV 快照不一致"列为数据质量保留项。本次 run 中双值未污染最终判断；但 T47 时代的证据（`phase1/L5.md:32-33`）表明模型曾被逼着"二选一"，且当时 `obv_20d_change_pct=-45.32%` 挂在分项值那一支上，规则与材料互相打架。
- 规则侧现状：`src/agent_analysis/prompts/l5_analyst.md:27` 已指定 `get_l5_deterministic_snapshot` 为精确数值唯一优先来源，但 canon 与 Indicator Semantics 对优先权覆盖范围的列举不一致（canon 含 OBV、semantics 不含，`phase1/L5.md:117-122` F-10），且对"分项与快照冲突"没有明文出口（`配餐单_v0_余站_红队稿.md:31`）。

---

## 五、建议与理由

**裁定：绝对水位以确定性快照（值 A 一支）为准。** 理由：

1. 提示词法典本就这么规定（`l5_analyst.md:27`），裁定只是追认现状，改动最小；
2. 快照一支带完整审计链：`ohlcv_sha256`、`row_count`、`future_exclusion`、`recompute_input`（`src/tools_L5.py:226-269`），且被重算带零容差独立复算通过——"数字可独立重算"这根支柱只有它满足；
3. 420 天窗口是 365 天的超集，回溯期更长，对 SMA200 等长窗指标本来就必需（`get_qqq_technical_indicators` 自己也在 `:647` 要求至少 200 根，365 天窗只留 ~52 根余量，更脆）。

**处置：统一为一个来源，而不是改名分账。** 具体两档，按工作量从小到大：

- 最小修复（一行）：把 `src/tools_L5.py:634` 的 `timedelta(days=365)` 改成 420，与快照对齐。两值自然一致，PC-08 转绿。代价是"同源重复计算"仍在，只是不再露馅。
- 根治（推荐排期做）：`get_qqq_technical_indicators` 与快照 14 项可比对字段中 13 项逐字节相同（`phase1/L5.md:107`），本质是同一套数据的第二次计算。让综合指标函数复用快照结果，或把快照没有的字段（布林带系、`atr_stop_loss_2_5x`、`sma_position` 等派生态）并入快照，然后 L5 采集清单（`collector.py:190-202`）只留一个计算入口。`get_obv_qqq` 作为"OBV 专项视图"可以保留，但 `level` 应取自快照同一帧。
- 不建议改名分账（如 `obv_420d` / `obv_365d`）：OBV 绝对水位随累加起点平移，两个窗口的水位差没有任何经济学含义，分账等于把噪声制度化成两个"指标"，还会给下游留下"该引用哪个"的永久歧义。

**附带建议（契约层面）**：OBV 对判断有语义的是方向与变化量，不是水位。建议在指标契约里把 `obv`（水位）标注为审计/对账字段，把 `obv_20d_change_pct` 的口径改为窗口无关的"20 日净增减股数"（或至少在 notes 里声明百分数锚点敏感），趋势词（accumulation/distribution）作为主语义出口。这样即使未来窗口再变，语义字段不变，PC-08 也不会再为无意义的水位平移报警。

**PC-08 处置**：保持红灯直到上述修复落地（最小修复即可转绿）；转绿条件建议加一条机器判据——同一 run 内 `get_l5_deterministic_snapshot.exact_technical_values.obv == get_qqq_technical_indicators.obv == get_obv_qqq.level`。

---

## 六、未能证实的事

1. **未与站外数据对表**：没有拿 Nasdaq/第三方行情商的"官方 OBV"来验证哪个水位"对"。但这不影响结论——OBV 水位本无官方锚点，各平台起点各异，"对"的定义本身就是"同一锚点自洽"。
2. **ta 库与内部 fallback 的水位差异未量化**：`src/tools_L5.py:489` 与 `:491` 对首日与平盘日的处理略有不同（ta 首日计 +volume、平盘计 +volume；fallback 首日计 0、平盘计 0）。本次 run `formula_engine=ta`，未走 fallback，差异未触发；一旦某台机器缺 ta 库，水位会再变一次（仍属锚点问题）。
3. **T47 run 的旧值（670,737,927 / 353,656,127）未逐位复现**：旧 run 的 raw_ohlcv 未在本次审查范围内重新演算，但其差值结构与本次完全一致，窗口假说对两次 run 同时成立。
4. **`get_qqq_technical_indicators` 窗口为何写成 365 天**：代码与注释未说明动机（`src/tools_L5.py:634-636` 只写"1年日频数据"），无法确认是刻意口径还是历史遗留；从功能看它要算 SMA200，365 天只是勉强够用，倾向判断为"写快照时（V7.x）另定了更稳妥的 420 天，旧函数没有跟进"。
5. **修改窗口对 `obv_20d_change_pct` 数值的影响**：已实测——同一段资金流，快照 420 天口径下 20 日变化率为 **-6.27%**，365 天口径下为 **-10.88%**（分母分别是 961,522,600 与 554,052,500），而窗口无关的"20 日净增减股数"两者完全相同（**-60,262,100 股**）；趋势词不变（同为 distribution）。窗口对齐后分项的百分数会从 -10.88% 变为 -6.27%，若采纳"改用净增减股数"建议则此问题消失；不采纳则需在变更说明里交代百分数口径变了。
