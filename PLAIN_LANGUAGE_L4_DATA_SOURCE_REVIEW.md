# L4 估值数据源复盘报告

写作日期：2026-05-04

## 一句话说明

这次复盘的核心结论是：你的判断基本正确。WorldPERatio 不应只被当成一个 PE 数字校验源；Damodaran ERP 当前实现也确实用窄了，应该优先补上官方月度 ERP 文件和当月计算器文件。

## 为什么要重新看

L4 估值层回答的是一个朴素但很难的问题：现在的纳斯达克100贵不贵，贵到什么程度，市场给股票相对美债的补偿够不够。

这个问题不能只靠一个数字。PE 是当前价格相对盈利的倍数，ERP 是股票相对无风险利率需要给出的风险补偿。它们都不是单独的买卖按钮，但它们会决定系统对“高估值是否脆弱”的判断边界。

按照 `RESEARCH_CANON.md` 的原则，指标必须先分清发言权：

- 当前值可以说明“现在是多少”。
- 历史分位可以说明“在历史中处于什么位置”。
- 均值和标准差可以说明“相对自身历史均衡偏离多远”。
- 模型预测只能作为情景参考，不能包装成确定结论。
- 大盘 ERP 是美国权益市场背景，不等于 NDX 自身估值。

## 你的四个问题梳理

### 1. WorldPERatio 不只是 PE 校验源

你这个判断成立。

当前代码对 WorldPERatio 的使用偏窄，主要抓了 Nasdaq 100 PE、日期和 methodology。官网页面实际提供了更多有用信息：

- Nasdaq 100 当前 PE。
- 数据日期。
- QQQ ETF 代理口径。
- 1 年、5 年、10 年、20 年滚动均值。
- 1 倍和 2 倍标准差区间。
- 当前 PE 相对均值的标准差偏离。
- 不同窗口下的估值标签，例如 Fair、Overvalued、Expensive。
- 50 日、200 日均线趋势边际。
- PE 与未来收益的简单回归和预测区间，并且官网自己提示这些预测不能作为投资策略依据。

这说明 WorldPERatio 可以成为“第三方相对位置辅助源”，而不是只做“当前 PE 是否差不多”的校验。

但边界也要说清楚：它提供的是均值、标准差、估值标签和回归模型，不等于历史百分位。除非页面明确给出 percentile 或 rank，否则系统不能写成“历史第 x 分位”。

更合适的表达是：

> WorldPERatio 显示，2026-05-01 Nasdaq 100 PE 为 32.27；在 5 年窗口内处于 1 倍标准差区间内，标签为 Fair；但在 10 年和 20 年窗口内高于 1 倍标准差，标签为 Overvalued。它说明当前估值对长期窗口仍偏高，但不能替代真实历史分位。

### 2. Damodaran ERP 当前实现用窄了

这个判断也成立，而且比第一点更重要。

当前代码优先读取的是 `histimpl.xls`。这个文件是年度历史 implied ERP 表，适合看长期历史，但不适合作为“当前 ERP”的最新来源。本次检查确认，`histimpl.xls` 的表内更新时间为 2024-01-05，行数据最新到 2025，因此把它作为 2026 年 5 月的最新 ERP 明显不够。

Damodaran 官网同时提供了更近的月度文件：

- `ERPbymonth.xlsx`：从 2008-09 到最新月份的月度 ERP 汇总。
- `ERPMay26.xlsx`：2026-05-01 当月 implied ERP 计算器。
- `ERPApril26.xlsx`：2026-04-01 当月 implied ERP 计算器。
- 每月历史计算器文件目录：`/pc/implprem/`。

我下载并读取了 `ERPbymonth.xlsx`，确认最新行是 2026-05-01：

| 字段 | 2026-05-01 数值 |
| --- | --- |
| S&P 500 | 7209 |
| 10 年期美国国债利率 | 4.40% |
| ERP，Trailing 12 month cash yield | 4.36% |
| ERP，Trailing 12 month with adjusted payout | 4.24% |
| ERP，Adjusted riskfree rate | 4.62% |
| ERP，Average CF yield last 10 years | 6.36% |
| ERP，Normalized earnings & payout | 3.73% |
| ERP，Net cash yield | 4.15% |
| Expected return | 8.76% |

我也直接下载了 `ERPMay26.xlsx`，确认它真实存在，服务器最后修改时间是 2026-05-01。文件内计算器显示：

- US 10-year treasury rate：4.40%。
- Default spread for Aa1 rating：0.26%。
- Default-risk-adjusted US dollar riskfree rate：4.14%。
- Implied expected return on S&P 500：约 8.55%。
- Implied Equity Risk Premium with US treasury rate as riskfree rate：约 4.15%。
- Implied Equity Risk Premium with default-risk adjusted riskfree rate：约 4.41%。

这和你看到的官网文字高度一致。差异主要来自选择哪个 cash yield / payout 口径作为“主 ERP”。因此系统后续不应只输出一个 `implied_erp_fcfe`，而应保留 Damodaran 自己并列给出的几种口径。

### 3. 下一步该做什么

我建议下一步不要直接一口气大改所有数据源，而是分三条线并行，但先后轻重很清楚。

第一优先级是数据基础，尤其是 L4：

- 把 Damodaran 官方月度 ERP 接入为首选。
- 保留 `histimpl.xls`，但降级为年度历史背景，不再冒充最新数据。
- 把 WorldPERatio 的均值、标准差、估值标签和窗口口径结构化。
- L4 prompt 明确要求区分“百分位”和“标准差区间”。

第二优先级是用户操作界面：

- 输入人工/Wind 数据。
- 选择 DeepSeek flash 或 pro。
- 看每个数据源是否可用、更新时间、口径和置信边界。
- 一键运行分析。
- 运行后打开报告。
- 保存人工输入模板。

但这个界面一开始不应该做成复杂交易终端。更好的第一版是“研究控制台”：让用户知道自己填了什么、系统自动抓到了什么、哪些数据过期、哪些来源冲突。

第三优先级是输出体验：

- 图表应该进入最终给用户看的报告。
- 但图表不能只是装饰，而要回答具体问题。
- 第一批最值得进入报告的图表是：L4 估值相对位置尺、Damodaran ERP 时间序列、WorldPERatio PE 相对均值区间、L1-L4 利率估值压力图、Bridge 冲突传导路径图。

### 4. 图表是否应该集成在最终报告

应该。

vNext 的目标不是生成一段漂亮文字，而是生成可审计、可展开、可交互阅读的投研推理链。图表是这条推理链的一等公民。

但图表的权限要明确：

- 图表帮助读者看见位置、趋势、背离和冲突。
- 图表不自动生成结论。
- 图表必须能追到数据来源、日期、公式和缺口。
- 图表要和 evidence ref 绑定，而不是孤立展示。

最理想的最终报告形态是：

> 先让读者读懂结论，再能打开图表看到证据，最后能追到原始数据和来源边界。

## 第一性原理判断

估值判断的底层问题不是“PE 是多少”，而是：

> 投资者今天支付的价格，需要未来现金流、增长和风险补偿共同证明它合理。

所以 L4 至少要同时回答四个问题：

1. 当前估值绝对值是多少。
2. 当前估值相对自身历史处于什么位置。
3. 当前现金流或盈利收益率相对美债有没有安全垫。
4. 美国整体权益风险补偿是偏高、正常还是偏低。

WorldPERatio主要补第 2 点，Damodaran 主要补第 4 点。人工/Wind 可以补第 1、2、3 点的高信任口径。yfinance 成分股模型补当前值和覆盖率校验。它们不应该互相替代，而应该互相约束。

## 工程建议

### L4 数据源优先级建议

1. 人工/Wind：最高信任，可输入 PE、PB、PS、ERP、5/10 年分位。
2. Damodaran 月度 ERP：美国市场 implied ERP 背景锚，优先读 `ERPbymonth.xlsx` 和当月 `ERP<Month><YY>.xlsx`。
3. WorldPERatio：Nasdaq 100 PE 相对位置辅助源，解析均值、标准差区间、估值标签、趋势边际。
4. Trendonify：若可用，继续作为真实历史分位来源；403 时只记录不可用。
5. yfinance 成分股模型：当前值、覆盖率、source disagreement，不承担历史 regime 主判断。

### Damodaran 结构化字段建议

建议后续把 `get_damodaran_us_implied_erp` 输出改成：

- `as_of_date`
- `sp500_level`
- `us_10y_treasury_rate`
- `default_spread`
- `adjusted_riskfree_rate`
- `erp_t12m_adjusted_payout`
- `erp_t12m_cash_yield`
- `erp_avg_cf_yield_10y`
- `erp_net_cash_yield`
- `erp_normalized_earnings_payout`
- `expected_return`
- `source_file`
- `retrieval_method`
- `data_quality`

这样 L4 不会再把一个年度历史值误当成最新状态。

### WorldPERatio 结构化字段建议

建议后续把 WorldPERatio 输出扩展为：

- `pe`
- `data_date`
- `proxy`
- `windows`
- `average_pe`
- `std_dev`
- `std_dev_ranges`
- `deviation_vs_mean_sigma`
- `valuation_label`
- `trend_sma200_margin`
- `trend_sma50_margin`
- `forward_return_model`
- `model_warning`

其中 `valuation_label` 可以用，但必须写清楚是 WorldPERatio 的标准差标签，不是历史百分位。

## 这次刻意没有做什么

这次没有直接改代码，因为 Damodaran 和 WorldPERatio 都需要比较谨慎的 parser 设计和测试：

- Damodaran 有 `.xls`、`.xlsx`、HTML 表、月度汇总、当月计算器多种入口。
- WorldPERatio 页面是 HTML 文本和图表混合，字段容易因为页面结构变化而漂移。
- 如果直接改，很容易把“初步调查”变成“半成品采集器”。

更稳妥的做法是先把结论写入 `NEXT_STEPS.md`，下一轮单独做 L4 数据源补丁和测试。

## 普通读者该怎么看

可以把这次复盘理解成：系统原来已经知道要查“估值”，但有两个地方还查得不够细。

WorldPERatio 原来像是只被用来看“今天 PE 是不是差不多”；现在发现它还可以告诉我们“这个 PE 相对过去几年算不算偏高”。

Damodaran 原来像是只翻了年度历史表；现在发现官网每个月都有更新表，2026-05-01 已经有最新 ERP，因此系统应该用月度表看最新情况。

这不会让系统立刻变成预测机器，但会让它更诚实：知道哪些结论有强数据，哪些只是辅助判断，哪些还不能说。

## 简单词汇表

- PE：市盈率，价格相对盈利的倍数。
- Forward PE：远期市盈率，价格相对未来预期盈利的倍数。
- ERP：股权风险溢价，股票相对无风险债券需要多给的补偿。
- 简式收益差距：NDX 盈利或自由现金流收益率减 10 年期美债收益率，是粗略安全垫，不等于 Damodaran ERP。
- 均值：过去一段时间的平均水平。
- 标准差：衡量偏离均值有多远。
- 历史分位：在历史样本中排在什么位置，和标准差标签不是同一件事。
- 数据发言权：每个数据源只能在自己的口径范围内支持结论。

## 后续最重要观察点

下一轮最重要的是把 L4 数据源补丁做实：

1. Damodaran 月度 ERP 首选接入。
2. WorldPERatio 相对位置字段结构化。
3. L4 prompt 和 few-shot 防止把标准差标签写成历史分位。
4. 报告中加入第一批真正有解释力的图表。
5. 用户操作界面先做研究控制台，不先做复杂前端大系统。

## 来源

- WorldPERatio Nasdaq 100 PE 页面：https://worldperatio.com/index/nasdaq-100/
- Damodaran current data 页面：https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datacurrent.html
- Damodaran historical implied ERP 页面：https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/implpr.html
- Damodaran monthly implied ERP directory：https://pages.stern.nyu.edu/~adamodar/pc/implprem/
- Damodaran monthly ERP file：https://pages.stern.nyu.edu/~adamodar/pc/implprem/ERPbymonth.xlsx
- Damodaran May 2026 calculator：https://pages.stern.nyu.edu/~adamodar/pc/implprem/ERPMay26.xlsx
