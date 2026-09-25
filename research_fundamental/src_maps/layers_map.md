# 数据层 L1–L5 源码取证地图

> 取证人：三层源码取证员。取证日期见本文件创建提交。
> 读法：`RESEARCH_CANON.md` 是教义（系统应该测什么），`src/` 下的代码是行为（系统实际测什么）。两者不一致的地方，本图同时给两条行号并标【教义≠行为】。分层的唯一真相来源是采集器注册表 `src/core/collector.py:147-203` 的 `LAYER_FUNCTIONS`，工具注册表 `src/tools.py` 里的 "Layer 1/2/3" 注释分组与采集器实际分层不一致，只是历史注释，不作数。
> 铁律执行说明：本图每个论断带 `文件:行号`；没读到的代码不评论；只研究，未改任何代码。

---

## 一、五层实况表

### L1 宏观经济状况

- **教义要求**：测增长、通胀与货币政策背景——10 年名义/实际利率（DGS10/DFII10）、通胀预期（T10YIE）、联邦基金利率与利率路径（`RESEARCH_CANON.md:113-143`）。
- **实际采集**：9 个函数（`src/core/collector.py:150-160`）：10Y-2Y 利差、联邦基金利率、利率路径、M2 同比、净流动性动量、铜金比、10Y 名义、10Y 实际、10Y 盈亏平衡。
- **实际数据源**：利率与利差类全部走 FRED 官方序列（T10Y2Y/FEDFUNDS/M2SL/DGS10/DFII10/T10YIE，source_name="FRED"，见 `src/tools_L1.py` 各函数）；利率路径用 yfinance 的 ZQ 联邦基金期货，自我标注 third_party_unofficial 且 supporting_only（`src/tools_L1.py:198-543`，权限条款在 `src/tools_L1.py:476`）；净流动性 = WALCL − TGA − RRP，带单位自动修正（`src/tools_L1.py:868`）；铜金比用 yfinance 的 HG=F/GC=F 期货，是代理（`src/tools_L1.py:1009`）。
- **更新频率**：FRED 日频/月频序列为主；ZQ 期货与铜金比日频。
- **教义≠行为**：教义把 DTWEXBGS 美元指数判读卡放在 L2（`RESEARCH_CANON.md:329-333`），代码里 `get_dxy_index` 是注释明说"从未接入运行时"的废弃孤儿（`src/tools_L1.py:1119-1126` 附近）；MOVE 指数教义有判读卡（`RESEARCH_CANON.md:341-345`），代码完全没有实现；10Y-3M 利差代码没有，只有 10Y-2Y。

### L2 市场风险偏好

- **教义要求**：测信用利差（HY/IG OAS）、波动率（VIX/VXN）、期限结构与 VRP、仓位（CFTC、FINRA 保证金）、情绪（`RESEARCH_CANON.md:147-179`、`RESEARCH_CANON.md:303-345`）。
- **实际采集**：13 个函数（`src/core/collector.py:164`）：VIX、VXN、HY OAS、IG OAS、HY 质量利差、HYG 动量、XLY/XLP、拥挤度仪表盘、CFTC 纳指仓位、FINRA 保证金、VXN/VIX、VIX 期限结构、CNN 恐惧贪婪指数。
- **实际数据源**：VIX/VXN 实际用 yfinance 拉 `^VIX` 序列（`src/tools_L2.py:190`；VXN 同文件 VXN 函数），**不是**教义判读卡写的"来源：Cboe"（`RESEARCH_CANON.md:155-156`）【教义≠行为，且 tier 只是 third_party_estimate】；HY/IG OAS 用 FRED 官方 BAML 系列（`src/tools_L2.py:664`、`src/tools_L2.py:689`，单位是 percent 不是 bp）；HY 质量利差也是 FRED 官方（`src/tools_L2.py:999`）；HYG 动量显式标 proxy（`src/tools_L2.py:737`）；拥挤度仪表盘 = SKEW + QQQ 期权链 put/call + 空头兴趣三合一身（`src/tools_L2.py:860-996`），回测下后两者 unavailable；CFTC 走官方 API（`src/tools_L2.py:1277`）、FINRA 走官方 XLSX（`src/tools_L2.py:1432`），两者都只有 120 天近期可见窗，更早的历史日期直接 unavailable、理由是历史 PIT 档案未接入（`src/tools_L2.py:1194-1200`）；CNN 恐惧贪婪指数用伪装浏览器头打 CNN 接口（`src/tools_L2.py:1563`），属第三方。
- **VRP（隐含减已实现波动差）**：教义明说"当前未实现，留作后续工单"（`RESEARCH_CANON.md:165` 附近的期限结构实现细节段），代码确实没有。
- **更新频率**：VIX/OAS 日频；CFTC 周频（周二快照+3 天可见）；FINRA 月频（月末+约 21 天可见估计）；CNN 日频。

### L3 指数内部健康度

- **教义要求**：测广度（A/D 线、%Above MA、New High/Low）、市值加权与等权的裂口（NDX/NDXE）、集中度（Top10）（`RESEARCH_CANON.md:239-267`）。
- **实际采集**：6 个函数（`src/core/collector.py:168`）：A/D 线、%Above MA、NDX/NDXE、QQQ Top10 集中度、New High/Low、McClellan 振荡器。
- **实际数据源**：广度类四个指标全部从**同一份** yfinance 成分股价格面板算出（`src/tools_L3.py:595` 的 `_get_ndx100_common_price_data`），日覆盖率低于 80% 的日子剔除（`src/tools_L3.py:288` 的 `NDX100_BREADTH_MIN_DAILY_COVERAGE`），source_tier=component_model；NDX/NDXE 用 yfinance 的 `^NDX`/`^NDXE`（`src/tools_L3.py:771`）；QQQ Top10 用 Invesco 官方页面（`src/tools_L3.py:1418`）加本地快照兜底，回测直接 unavailable 且 anomaly 写明 live_current_holdings_not_used（`src/tools_L3.py:1638`）；历史集中度变化是价格反推的代理，代码自己声明"not official historical weights"（`src/tools_L3.py:1520-1573`）。
- **幸存者防线**：回测的成分股宇宙只用 nasdaq-100-ticker-history 库，拿不到就硬失败，绝不落回当前名单（`src/tools_L3.py:19-259`；同样的纪律在 L4 成分快照 `src/tools_L4.py:3120-3141`）。
- **更新频率**：日频。教义自己承认"L3 单源依赖 yfinance 成分面板是已知弱点"（`RESEARCH_CANON.md:550` 附近）。

### L4 估值盈利

- **教义要求**：测 PE/Forward PE（含全成分 NTM Forward PE 正式链）、盈利修正动力学、FCF Yield、ERP、M7 资本开支/静默期/回购（`RESEARCH_CANON.md:183-235`）。
- **实际采集**：11 个函数（`src/core/collector.py:172-184`）。
- **实际数据源（按链主次）**：
  - Wind 快照是生产锚，但**只在实时模式可用**，回测直接返回 `backtest_skipped_current_wind_snapshot_not_point_in_time`（`src/tools_L4.py:972-973`），tier 是 licensed_provider；Wind 的 PE/PB/PS 字段标 core_allowed，RiskPremium 字段因自然语言响应没有稳定字段代码标 supporting_only（`src/tools_L4.py:1083-1092`）。
  - Wind PIT 盈利预期要求显式 vintage 且新鲜度 ≤7 天，超期直接 unavailable（`src/tools_L4.py:1362-1364`）。
  - History of Market 第三方 JSON 接口是 PE 主锚（URL 在 `src/tools_L4.py:4326`），自称 Bloomberg BEst 归属但未独立核验（`src/tools_L4.py:58` 附近的 caveat 常量）；回测时强制 `not_point_in_time_verified` → decision_eligible=False，注释明说"fail closed"（`src/tools_L4.py:4629-4645`）。
  - 成分自算模型默认关闭，要环境变量 `NDX_ENABLE_COMPONENT_MODEL` 显式开（`src/tools_L4.py:4715`）；Alpha Vantage 的 QQQ OVERVIEW 是实时备胎、latest-only，回测直接 `latest_only_fallback_rejected_in_backtest`（`src/tools_L4.py:5072-5082`）。
  - 全成分 NTM Forward PE 用 Invesco 官方权重 + yfinance FY1/FY2 一致预期，亏损成分保留在加总里，实时专用，回测返回 `no_point_in_time_consensus_for_backtest`（`src/tools_L4.py:6636-6707`）；权重覆盖率低于 90% 或持仓快照超过 10 天不出数（`src/tools_L4.py:6977-6986`）。
  - 盈利修正动力学走双轨：自建的 PIT 快照档案（`output/vintage_archive/*/eps_consensus.json`，2026-07-12 起，见 `src/tools_L4.py:7457-7468` 与 7210-7216 的回测拒绝）优先，雅虎自带的 30/90 天回看列只补档案缺口，且凡混入回看列的窗口保守地标 supplier_lookback（`src/tools_L4.py:7579-7587`、7744-7753）；所有字段 supporting_only（`src/tools_L4.py:8112-8158`）。
  - M7 资本开支与回购主路是 SEC XBRL 官方披露事实、按 filed_date 逐条卡点（PIT 安全），yfinance 现金流是**只在实时上下文**允许的备胎且 pit_safe=false（资本开支 `src/tools_L4.py:5631-6062`，备胎禁令在 5720-5721；回购 `src/tools_L4.py:6062-6479`，stale 判定在 6188-6194）。M7 名单在 `src/tools_common.py:292`。
  - Damodaran 隐含 ERP 是美股市场参考锚（不是 NDX 估值），月频 Excel 主路、年度历史兜底，带 5y/10y 分位（`src/tools_L4.py:4196-4323`）。
  - 简式收益差距（盈利收益率 − 10Y）被老板裁决为只能当诊断辅助、不得独立支撑强结论（`src/tools_L4.py:6602-6611`，O13 裁决原文在注释里）。
  - 第三方校验源（WorldPERatio/Trendonify/Danjuan 网页抓取）只做 validation_only/audit_only，注释明说浏览器 sidecar 不得偷渡进 L1-L5 运行时载荷（`src/tools_L4.py:3773-3775`）；成分模型与第三方中位数偏差超过 30%（PB 是 75%）时 PE/ForwardPE 直接 blocks_publish（`src/tools_L4.py:1861-2024`，阈值在 1864-1866）。
- **更新频率**：Wind 日频（实时）；HoM 日频（但历史分位有 7 天/45 天新鲜度闸门）；盈利修正日频档案；SEC 季频；Damodaran 月频。

### L5 价格趋势与波动

- **教义要求**：教义**没有**独立的 L5 章节——均线/ATR/ADX/RSI/MACD 被判读卡标成"L4 技术型"（`RESEARCH_CANON.md:271-299`），情绪型指标 FGI/PCR 被标成"L4 情绪型"（`RESEARCH_CANON.md:323-327`）。代码却把技术指标单列第五层、把 CNN FGI 放在 L2【教义≠行为，两处】。
- **实际采集**：11 个函数（`src/core/collector.py:190-202`）：确定性快照、综合技术指标、RSI、ATR、ADX、MACD、OBV、成交量分析、量价质量、唐奇安通道、多尺度均线。
- **实际数据源**：全部 11 个函数读**同一份** QQQ OHLCV（yfinance 主、Twelve Data 优先通道、Alpha Vantage 备胎），指标用 ta 库或内部等价公式；`get_l5_deterministic_snapshot` 带 `ohlcv_sha256` 哈希和重算输入，供重算带独立复算（`src/tools_L5.py:131`、`src/tools_L5.py:235`）；用途边界写明"exact_l5_price_and_indicator_source_of_truth"且禁止从 L5 推估值或广度（`src/tools_L5.py:249-250`）。
- **更新频率**：日频；有 future_rows_dropped 时点纪律。
- **共线性提示**：证据家族表里 L5 全部 11 个函数共享同一个 `qqq_ohlcv_technical` 家族（`src/core/evidence_families.py:44-193`），意味着它们在置信度上加权重、不当 11 份独立证据。

---

## 二、证据资格现状（Q-B：一份数据要满足什么才有资格当证据）

**资格体系是"来源分级 + 字段级权限 + 硬阻断规则"三层。**

1. **来源分级（source_tier）**：七档权威模型——official / licensed_provider / licensed_manual / proxy / candidate_external_material / derived_inference / unknown（`src/data_evidence.py:262-291` 的 `SOURCE_TIER_AUTHORITY_MODEL`）。按名字推断的规则在 `src/data_evidence.py:397-409`：fred/invesco/nasdaq/sec/damodaran → official；wind → licensed_provider；yfinance/yahoo/alpha vantage → third_party_estimate。
2. **字段级权限**：`WEAK_METRIC_AUTHORITY_POLICIES`（`src/data_evidence.py:147-216`）给 VIX/VXN/铜金比/HYG/XLY-XLP/拥挤度/CFTC/FINRA/VXN-VIX/CNN FGI 这些弱来源字段逐条发 supporting_only 或 audit_only 牌照——能当旁证，不能单独定案。L4 内部还有一套平行的 `metric_authority` 登记（如成分模型 PE 的 core_allowed 前提是通过第三方交叉校验，`src/tools_L4.py:1861-2024`）。
3. **硬阻断（hard_block）**：代理冒充官方、latest-only 源进回测、数据日期晚于有效日期、有字段名无实质值，这四类直接硬阻断（`src/data_evidence.py:636-653`）。发布闸门的量化门槛是整体置信度 ≥60%、每个正式层成功率 ≥50%（`src/core/checker.py:32-33`），估值源冲突 blocks_publish 是阻断理由之一（`src/core/checker.py:303-355`）。
4. **隔离带**：新闻层是 sidecar，政策硬编码"never evidence_ref"、"not injected into L1-L5 layer-local prompts"（`src/news_layer_analyzer.py:216-218`；采集器也不混入，`src/core/collector.py:659`）；浏览器 sidecar 与当前网页线索未正式升级前不得成为 L1-L5 的 evidence_ref（`src/core/collector.py:344-346` 的 research_candidate_policy）。
5. **手工数据通道（合法的例外开口）**：`src/manual_data.py` 的模板可以让 Wind 人工抄数以 licensed_manual 身份进主链，默认 `active: False`（`src/manual_data.py:29`）；120 天新鲜度检查只标注 anomaly、不阻断（`src/core/collector.py:74`、`src/core/collector.py:97-122`，标注动作在 541-544）。回测时手工估值会剥离实时第三方校验、避免当前网页污染历史（`src/core/collector.py:205-217`）。
6. **缓存纪律**：本地 CSV 缓存超过 7 天只打印警告仍返回旧数据（`src/data_manager.py:25`、`src/data_manager.py:96-106`）；asof 合并用 backward 方向防前视（`src/data_manager.py:261-265`）。

**多空对称性结论**：代码层面没有发现"只收利好"或"只收利空"的采集偏差——每个指标都是中性测量，多空两侧用同一份菜单。真正的不对称是**权限条款的方向性约束**，而且是刻意设计的：VIX 期限结构的 contango/flat 被标 `not_bullish_evidence`、不得引用为看多证据（`src/tools_L2.py:575-580`，中文说明在 624）；利率路径的 easing_priced 状态被注明"不是流动性利多，须与 HY OAS 和增长数据交叉验证"（`src/tools_L1.py:261`，权限块在 476）。也就是说，系统对"看起来像利好"的信号额外加了镣铐，对利空信号没有对应的镣铐——方向是防多头自欺，不是防空头。

---

## 三、缺口清单（对照黄金坑 / 逃顶 / 中途风控的证据需求）

黄金坑的教义定义是"VIX 高、情绪极恐、RSI 极冷，但信用未穿透"（`RESEARCH_CANON.md:368`），判定要领是"恐慌先爆、信用未穿、内部先修"（`RESEARCH_CANON.md:632`），且下结论前必须答出信用坏没坏、真实利率升没升、广度修没修（`RESEARCH_CANON.md:370`）。逃顶的教义线索是假突破（指数新高但 A/D、%AboveMA、New Highs 不跟，`RESEARCH_CANON.md:366`）与集中度失控（`RESEARCH_CANON.md:637`）。对照下来：

1. **【代码有能力受限】回测模式下 L4 估值证据几乎全灭。** Wind 快照 live-only（`src/tools_L4.py:972-973`）、HoM 主锚回测 fail-closed 成 stale（`src/tools_L4.py:4629-4645`）、Alpha Vantage 备胎回测拒绝（`src/tools_L4.py:5072-5082`）、全成分 Forward PE 回测拒绝（`src/tools_L4.py:6698-6707`）、盈利修正档案 2026-07-12 才开始积累（`src/tools_L4.py:7210-7216`）；此外回测跳过清单还点名跳过一批 L4 函数（`src/core/collector.py:256-289`）。回测里能站住的 L4 只剩 Damodaran 月频 ERP 和 SEC XBRL 的 M7 资本开支/回购。→ 历史"逃顶"复盘时，估值分位这条腿基本靠不上。
2. **【代码有能力受限】极端拥挤度没有历史分位锚。** CFTC 与 FINRA 是官方源但只有 120 天近期窗，超窗直接 unavailable、无历史 PIT 档案（`src/tools_L2.py:1194-1200`）；拥挤度仪表盘的 put/call 与空头兴趣回测下 unavailable（`src/tools_L2.py:860-996`）。→ "情绪极端拥挤"这个逃顶信号在历史和实时都缺分位刻度，实时只有原始值。
3. **【教义有要求·代码未实现】VRP 波动风险溢价未实现。** 教义有判读卡并写明"当前未实现，留作后续工单"（`RESEARCH_CANON.md:165` 附近），代码无对应函数。
4. **【教义有要求·代码未实现】MOVE 债市波动指数、DTWEXBGS 美元指数、10Y-3M 利差均未接入。** MOVE 与 DTWEXBGS 教义有判读卡（`RESEARCH_CANON.md:341-345`、`RESEARCH_CANON.md:329-333`），代码里 `get_dxy_index` 是废弃孤儿（`src/tools_L1.py:1119-1126` 附近），MOVE 与 10Y-3M 完全没有。→ 黄金坑判定要的"MOVE 三坏印证"之一（`RESEARCH_CANON.md:368` 最右列）缺料。
5. **【代码有能力受限】信用利差的长历史分位受限。** HY/IG OAS 走 FRED 官方日频、资格没问题，但教义自己承认 FRED 现行可见的 ICE/BofA OAS 历史只从 2023-04-24 起（`RESEARCH_CANON.md:424`）。→ "信用未穿透"能测当下，做不了 20 年尺度的信用周期分位。
6. **【代码有能力受限】L3 广度是单源单家族。** 四个广度指标同一份 yfinance 成分面板（`src/tools_L3.py:595`）、同一证据家族（`src/core/evidence_families.py:44-193`），教义自认是已知弱点（`RESEARCH_CANON.md:550` 附近）。→ "内部先修"这个黄金坑要件系在一条数据源上，面板哪天出问题，四个指标一起瞎。
7. **【教义≠行为】VIX/VXN 来源不是教义指定的 Cboe，而是 yfinance**（`src/tools_L2.py:190` vs `RESEARCH_CANON.md:155-156`），tier 只是 third_party_estimate 且在弱来源政策表里被限权（`src/data_evidence.py:147-216`）。行为比教义诚实，但"恐慌先爆"这个黄金坑第一要件的分位锚建立在第三方镜像上。
8. **【代码有·待激活】手工数据通道是弱来源进主链的合法开口。** licensed_manual 身份 + 120 天只标注不阻断（`src/manual_data.py:29`、`src/core/collector.py:97-122`）。设计上 tier 标注齐全，不算漏洞，但它是目前唯一能填补缺口 1（回测估值）的管道，前提是有人定期手工维护 Wind 数。
9. **【孤儿函数】三个注册函数没有层采集它们**：`get_m7_fundamentals`（注册于 `src/tools.py:66`，定义在 `src/tools_L3.py:1857`）、`get_qqq_net_liquidity_ratio`（注册于 `src/tools.py:49`，定义在 `src/tools_L1.py:948`）不在 `LAYER_FUNCTIONS` 任何一层里（对照 `src/core/collector.py:147-203`）；`get_qqq_qqew_ratio` 是 legacy 别名（`src/tools.py:55`）。→ 注册了 ≠ 上桌，查"系统能测什么"时别看注册表，看采集器。
10. **【教义本身没要求】Put/Call 比率只有 QQQ 期权持仓量近似，且回测不可用**（`src/tools_L2.py:860-996`）；CNN FGI 是第三方综合情绪（`src/tools_L2.py:1563`）。教义把 PCR/FGI 列为"L4 情绪型"判读卡（`RESEARCH_CANON.md:323-327`），但没有规定必须官方源，故标"教义没提硬性要求"而非违规。

---

## 四、每层一句话体检结论

- **L1**：利率主线是 FRED 官方日频、资格最干净的一层，但利率路径靠 yfinance 期货且被限权、美元与 MOVE 两张教义牌缺位，是"主干结实、侧枝缺席"。
- **L2**：指标菜单最全（13 个），但 VIX/VXN/FGI 都是第三方镜像且被刻意限权、CFTC/FINRA 只有 120 天窗，实时够用、历史分位瘸腿，是"能测当下恐慌，量不了历史极端"。
- **L3**：幸存者防线（历史宇宙硬失败不落回当前名单）是全线最严的纪律，但广度四指标共用一份 yfinance 面板是单点故障，Top10 回测干脆缺席，是"防线很硬、命脉很细"。
- **L4**：资格体系最精密（字段级权限、交叉校验、fail-closed 回测），代价是回测模式下估值证据近乎全灭、全靠手工通道和 SEC 季报撑着，是"规则最严、历史最穷"。
- **L5**：单一家族单一价格源、带哈希可重算，定位老实（only price truth，不许越权谈估值），是"份内事做得最扎实，份外事一点没有"。
