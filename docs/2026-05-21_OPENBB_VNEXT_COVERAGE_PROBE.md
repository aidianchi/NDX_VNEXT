# OpenBB vNext 五层覆盖测绘

日期：2026-05-21

本文记录一次非生产实验：用 OpenBB 对 vNext 现有 L1-L5 数据函数做覆盖测绘。它回答的不是“OpenBB 能不能立刻替代全部数据源”，而是：

1. 每个现有 `function_id` 能不能找到 OpenBB 候选入口。
2. 候选入口是否真实跑通。
3. 它适合直接替代、只提供原料、只做实时交叉校验，还是没有覆盖。
4. 它是否适合历史回测，尤其是否满足有效日期和历史可见性边界。

运行产物在本地忽略目录：

- `output/openbb_coverage/openbb_vnext_coverage_matrix.json`
- `output/openbb_coverage/openbb_vnext_coverage_matrix.csv`
- `output/openbb_coverage/openbb_vnext_coverage_report.md`

生成脚本：

- `scripts/openbb_vnext_coverage_probe.py`

## 本轮结果

探测参数：

- OpenBB：`4.7.1`
- provider 数量：`33`
- provider-backed commands：本地 OpenBB coverage 显示 `197`
- effective date：`2026-05-20`
- 探测窗口：`2026-04-05` 至 `2026-05-20`
- 覆盖行数：`42`

结果汇总：

| 类别 | 数量 | 通俗解释 |
| --- | ---: | --- |
| `ok` | 38 | OpenBB 候选入口真实跑通，返回了数据或可计算结果 |
| `error` | 2 | 接口存在但本地权限或 provider 覆盖不满足 |
| `not_probed` | 2 | 没找到合理 OpenBB 候选，保留现有外部路径 |

替代评级：

| 评级 | 数量 | 含义 |
| --- | ---: | --- |
| `candidate_direct` | 20 | 可以作为直接替代候选，但仍需字段和数值等价验证 |
| `candidate_partial` | 14 | OpenBB 能提供原始数据，vNext 仍保留本地公式、语义和审计包装 |
| `cross_check_only` | 6 | 适合实时旁路校验，暂不进入历史主证据链 |
| `not_covered` | 2 | OpenBB 暂未覆盖，继续使用现有外部来源 |

真实失败项：

- `get_qqq_top10_concentration` / FMP：OpenBB 能调到接口，但当前 FMP 订阅返回 `402 Restricted Endpoint`。这说明 QQQ 持仓/集中度不能指望“装了 OpenBB 就免费解决”。
- `get_qqq_top10_concentration` / TMX：返回 `Results not found`，对 QQQ 持仓不构成可用替代。

未覆盖项：

- `get_cnn_fear_greed_index`：OpenBB 没有明显等价入口。
- `get_damodaran_us_implied_erp`：OpenBB 没有替代 Damodaran implied ERP 的明显入口，现有 Damodaran 路径应保留。

## 五层判断

L1 宏观流动性：OpenBB 覆盖很好。FRED、Federal Reserve 能覆盖利率、M2、净流动性原料、TIPS 实际利率、通胀预期等。注意：这仍是 observation date 口径，不等于已经解决 ALFRED first-vintage。

L2 信用与压力：覆盖很好。VIX/VXN 可用 CBOE，HY/IG OAS 可用 FRED，HYG、XLY/XLP 可用 OpenBB 的价格入口。但 QQQ options chain 目前是当前链，不能默认用于历史回测。

L3 市场结构：OpenBB 能明显改善价格数据入口，但不能单独解决 point-in-time NDX universe。广度、MA 以上比例、新高新低、McClellan 这类函数，真正难点不是“拿价格”，而是“当时指数里有哪些股票”。

L4 估值与盈利：OpenBB 有价值，但最需要审计。FMP/Finviz 可做实时交叉校验，SEC facts 对 first-reported 审计很有潜力；但 NDX 聚合估值、盈利预期 vintage、报告可见日期仍不能直接交给 OpenBB 自动决定。

L5 技术与资金流：OpenBB 很适合作为价格和技术公式候选。RSI、ATR、ADX、MACD、OBV、VWAP、Donchian、SMA 都跑通。下一步应做数值等价测试，而不是直接替换。

## 下一步建议

1. 先做 L1/L2 的 OpenBB adapter 原型，但只放在实验开关后面，输出仍包成现有 vNext `raw_data` 形状。
2. 做 L5 公式等价测试：同一段 QQQ OHLCV 下，对比现有 `ta/internal` 与 OpenBB technical 的最后值、缺失值策略和列名。
3. 做 L3 point-in-time universe 专题：OpenBB 可以负责价格，不能负责历史成分股真实性。
4. 做 L4 SEC facts / FMP / Finviz 三源对照：目标不是漂亮估值，而是把 `reported_date`、`period_ending`、字段单位和可见日期说清楚。
5. 暂不把 OpenBB 输出直接写入 L1-L5 主证据链；每个候选源必须先通过日期、单位、字段语义和 DataIntegrity 边界。

## 结论

OpenBB 值得继续推进，而且价值比早期点状测试更大：它确实能显著扩大 vNext 的候选数据地图。

但 OpenBB 不是“完全体真理机器”。它解决的是“去哪拿”和“怎样统一调用”的大部分问题；它没有自动解决“历史当时是否可见”“这个字段能不能代表我们要的投资含义”“是否能进入 evidence_ref”这些 vNext 的审计问题。

因此最优路线是：让 OpenBB 成为五层数据底座候选和公式引擎候选，但由 vNext 的有效日期、数据质量、字段语义和发布闸门来决定是否升级为正式证据。
