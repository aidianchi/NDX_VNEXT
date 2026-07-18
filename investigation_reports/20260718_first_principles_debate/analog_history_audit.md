# 历史状态类比：数据史审计

- 审计截止日：`2026-07-19`
- 权限：`audit_only`（只审计，不进入 L1-L5 或综合结论）
- 禁止项：未计算状态后的收益分布、条件收益、胜率、收益估计或类比信号。

## 结论

类比引擎准入：`rejected_insufficient_clean_pit_history`。
- No candidate has a retained full publication-vintage history proving point-in-time availability.
- NDX valuation history has non-stitchable Wind and History of Market lineages.
- Revision/PIT caveats remain for: dfii10, hy_oas, ndx_valuation_percentile, vix.

## 各候选变量

### 10Y real rate (DFII10)

- 来源：Federal Reserve Bank of St. Louis (FRED)（`official_relay`）
- 可用历史：2003-01-02 至 2026-07-16；5888 条；跨 8596 个日历日。
- 截止日硬过滤：剔除 0 条晚于 `2026-07-19` 的观察。
- 历史口径：candidate level observations。
- 机械独立簇上界：184（上行 92 / 下行 92）；同向至少间隔 63 个清洗后交易日位置。
- 解释边界：mechanical data-density upper bound only; not an economic regime definition。
- 数据源断点：0 个。
- 装载说明：{"availability": "available", "fallback_chain": ["fred_api"], "source_tier": "official_api", "source_url": "https://api.stlouisfed.org/fred/series/observations"}
- 已知风险：
  - No ALFRED vintage was collected, so historical publication vintages are not proven point-in-time.
  - Source corrections, holiday gaps, and metadata changes may alter the downloaded history.

### ICE BofA US High Yield OAS (BAMLH0A0HYM2)

- 来源：ICE BofA via FRED（`official_relay`）
- 可用历史：2023-07-18 至 2026-07-16；787 条；跨 1094 个日历日。
- 截止日硬过滤：剔除 0 条晚于 `2026-07-19` 的观察。
- 历史口径：candidate level observations。
- 机械独立簇上界：26（上行 13 / 下行 13）；同向至少间隔 63 个清洗后交易日位置。
- 解释边界：mechanical data-density upper bound only; not an economic regime definition。
- 数据源断点：1 个。
- 装载说明：{"availability": "available", "fallback_chain": ["fred_api"], "source_tier": "official_api", "source_url": "https://api.stlouisfed.org/fred/series/observations"}
- 覆盖限制：Current FRED relay coverage is limited to three years starting in April 2026. The measured rows are the currently accessible window, not the complete history; older data requires the licensed source and a retained PIT archive.
- 覆盖限制来源：https://fred.stlouisfed.org/series/BAMLH0A0HYM2
- 已知风险：
  - No ALFRED vintage was collected, so historical publication vintages are not proven point-in-time.
  - Provider methodology, bond-universe composition, corrections, or backfills can change history.
  - Starting in April 2026, FRED only exposes three years of this copyrighted ICE series; the accessible start is not the original series inception.
- 断点明细：
  - 2026-04-01：source_access_window_changed_to_three_years；FRED states that starting in April 2026 this copyrighted ICE series only includes three years of observations; the measured start is an access-window boundary, not series inception.

### NDX valuation percentile lineage (Wind / History of Market)

- 来源：Wind snapshots and History of Market histories（`mixed_non_stitchable`）
- 可用历史：2001-04-30 至 2026-05-18；298 条；跨 9149 个日历日。
- 截止日硬过滤：剔除 0 条晚于 `2026-07-19` 的观察。
- 历史口径：Representative underlying History of Market PE observations used to assess the raw history available for percentile calculation; this is not a time series of historical percentile readings, and it is not joined to Wind snapshots.。
- 机械独立簇上界：10（上行 5 / 下行 5）；同向至少间隔 63 个清洗后交易日位置。
- 解释边界：mechanical data-density upper bound only; not an economic regime definition。
- 数据源断点：1 个。
- 装载说明：Wind archive scan found 0 percentile snapshot(s); they are counted as lineage evidence only and are not stitched into the History of Market value series. The longer History of Market component is used only for the mechanical density count; trailing and forward series remain separate in lineages.
- 已知风险：
  - Wind is archived by this project as current/recent snapshots, not as a complete historical point-in-time series.
  - History of Market is a third-party API with no retained publication vintages; its Bloomberg BEst attribution is not independently verified.
  - Trailing PE is daily while forward PE is monthly, and neither History of Market series is the same field or methodology as Wind's percentile snapshot.
  - Index composition and valuation methodology can change through time.
- 断点明细：
  - 无单一日期：non_stitchable_source_and_methodology_lineage；Wind percentile snapshots and History of Market PE histories are separate lineages; no splice is permitted.
- 谱系覆盖（彼此不拼接）：
  - `HOM_TRAILING_PE` / trailing_pe：2026-05-11 至 2026-07-17，48 条；PIT vintages retained=False.
  - `HOM_FORWARD_PE` / forward_pe：2001-04-30 至 2026-05-18，298 条；PIT vintages retained=False.
  - `WIND_NDX_VALUATION_SNAPSHOT` / Wind PEHistoricalPercentile point snapshots：无 至 无，0 条；PIT vintages retained=False.

### CBOE Volatility Index (^VIX)

- 来源：Yahoo Finance relay for Cboe VIX（`third_party_relay`）
- 可用历史：1990-01-02 至 2026-07-17；9203 条；跨 13345 个日历日。
- 截止日硬过滤：剔除 0 条晚于 `2026-07-19` 的观察。
- 历史口径：candidate level observations。
- 机械独立簇上界：288（上行 144 / 下行 144）；同向至少间隔 63 个清洗后交易日位置。
- 解释边界：mechanical data-density upper bound only; not an economic regime definition。
- 数据源断点：0 个。
- 装载说明：project yfinance relay/cache
- 已知风险：
  - Market closes are normally final, but the third-party relay can correct, omit, or remap observations.
  - This audit does not use an official Cboe historical archive and does not retain vendor vintages.

## 准入边界

Do not build or admit an analogy engine from this audit; first establish clean PIT archives and revise the frozen preregistration draft in a separate work order.

本文件只回答数据史是否足够干净，不回答历史状态之后市场会涨还是跌。
