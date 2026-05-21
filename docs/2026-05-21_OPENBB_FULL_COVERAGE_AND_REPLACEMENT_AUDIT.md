# OpenBB 完整能力与 vNext 五层替换调研

日期：2026-05-21  
分支：`codex/openbb-provider-research`  
状态：研究分支实验报告，不代表主链已替换。

## 一句话结论

OpenBB 已经值得被当成 `ndx_vnext` 的“金融数据底座候选”和“provider 地图”，而不是简单备用源。

但它不能直接一键替换 L1-L5。原因不是 OpenBB 不够强，而是本项目的关键价值不只是拿到数据，还包括：

- 数据日期不能穿越回测日。
- 指标口径必须说清楚。
- fallback 不能静默改口径。
- 代理数据不能冒充官方事实。
- 每条重要证据要能进入 DataIntegrity 和 evidence audit。

因此，正确路线是：先把 OpenBB 装满、配好、盘清楚；再按五层逐项替换或交叉校验；最后把 OpenBB 输出包进 vNext 自己的 `data_quality`、`source_tier`、`fallback_chain` 和 `backtest_data_boundaries`。

## 当前安装状态

本机项目虚拟环境 `/Users/aidianchi/Desktop/ndx_mac/.venv` 已安装 OpenBB：

| 项目 | 状态 |
| --- | --- |
| `openbb` | `4.7.1` |
| `openbb-core` | `1.6.9` |
| `openbb-cli` | `1.4.1` |
| `openbb-platform-api` | `1.3.5` |
| 已识别 provider | 33 个 |
| provider-backed 数据命令 | 197 个 |
| 直接遍历 `obb` 命令树 | 268 个 |
| 本地计算/工具命令 | 约 71 个，主要是 technical / quantitative / econometrics |

本轮已执行：

- `pip install "openbb[all]==4.7.1"`：官方 all extra 已满足。
- `pip install openbb-polygon==1.5.1`：补上 Polygon provider。
- `openbb-build`：已触发 OpenBB 静态资产重建。
- `config/configure_openbb.py`：已把本仓库 `.env` 中已有 key 写入 `~/.openbb_platform/user_settings.json`。

## 凭证状态

只记录是否配置，不记录密钥值。

| credential slot | 对应 provider | 当前状态 |
| --- | --- | --- |
| `fmp_api_key` | FMP | 已配置 |
| `fred_api_key` | FRED | 已配置 |
| `alpha_vantage_api_key` | Alpha Vantage | 已配置 |
| `polygon_api_key` | Polygon | 已配置 |
| `finnhub_api_key` | Finnhub | 已配置，但 OpenBB 当前没有官方 `finnhub` provider |
| `simfin_api_key` | SimFin | 已配置，但 OpenBB 当前没有官方 `simfin` provider |
| `benzinga_api_key` | Benzinga | 未配置 |
| `biztoc_api_key` | Biztoc | 未配置 |
| `bls_api_key` | BLS | 未配置 |
| `cftc_app_token` | CFTC | 未配置 |
| `congress_gov_api_key` | Congress.gov | 未配置 |
| `econdb_api_key` | EconDB | 未配置 |
| `eia_api_key` | EIA | 未配置 |
| `intrinio_api_key` | Intrinio | 未配置 |
| `nasdaq_api_key` | Nasdaq Data Link | 未配置 |
| `tiingo_token` | Tiingo | 未配置 |
| `tradier_api_key` / `tradier_account_type` | Tradier | 未配置 |
| `tradingeconomics_api_key` | Trading Economics | 未配置 |

## 已安装 provider 总览

| provider | commands | 对 vNext 的主要价值 |
| --- | ---: | --- |
| `fred` | 36 | L1/L2 利率、通胀、信用、经济序列 |
| `federal_reserve` | 13 | L1 货币、利率、国债曲线 |
| `fmp` | 69 | L3/L4 股票基本面、估值、盈利预期、日历、ETF/指数部分数据 |
| `polygon` | 13 | L5 价格、成交量、VWAP、NBBO；L4 部分财报表 |
| `alpha_vantage` | 3 | 价格 fallback；ETF/基础数据需要进一步测 OpenBB 暴露范围 |
| `cboe` | 11 | VIX、指数价格、期权链 |
| `finviz` | 7 | L4 单股估值/盈利质量交叉校验 |
| `sec` | 17 | 官方财报事实、13F、filings、company facts |
| `finra` | 2 | short interest / dark pool 线索 |
| `yfinance` | 29 | 当前主链相近的免费价格/基本面入口，但回测日期风险仍在 |
| `tiingo` | 7 | 价格、新闻、dividend yield 候选；未配 key |
| `tradier` | 5 | 期权/报价候选；未配 key |
| `intrinio` | 38 | 基本面、预期、期权、机构级候选；未配 key，多为付费 |
| `nasdaq` | 9 | 日历、filings、数据集候选；未配 key |
| `benzinga` / `biztoc` | 4 / 1 | 新闻候选；未配 key |
| `bls` / `eia` / `congress_gov` / `cftc` | 2 / 2 / 3 / 2 | 公共数据候选；未配 key 或 token |
| `ecb` / `imf` / `oecd` / `government_us` / `famafrench` | 3 / 8 / 9 / 6 / 6 | 无 key 或公共数据，适合扩展宏观和研究特征 |

## 官方配置判断

OpenBB 官方文档说明：OpenBB 不托管数据，本质是 provider connector；多数 provider 是否可用取决于 provider 自己的 API key 和订阅级别。OpenBB 读取本地 `~/.openbb_platform/user_settings.json` 的 `credentials`。

| provider | 官方状态 | 我们该怎么做 |
| --- | --- | --- |
| BLS | 官方公共 API 可不注册使用；注册 key 可提升使用能力 | 先无 key 测试；如遇限制，再用邮箱注册 `bls_api_key` |
| EIA | API key 需要注册，bulk download 不需要 key | 需要用户邮箱注册 `eia_api_key`；能源数据不是 NDX 主线优先级 |
| Congress.gov | 需要 api.data.gov key | 需要用户注册 `congress_gov_api_key`；默认只能做事件/监管候选，不进主证据 |
| Nasdaq Data Link | 免费账号可拿 API key，但数据集分免费/付费 | 需要用户注册 `nasdaq_api_key`；重点测试日历、指数/ETF、历史数据集 |
| Tiingo | 免费账号可拿 token | 建议注册 `tiingo_token`；价格/新闻/dividend yield 值得测 |
| Tradier | 登录 Tradier 后拿 sandbox/live token | 若要系统化期权链，可注册 sandbox token |
| Intrinio | 有 trial，但核心数据偏商业订阅 | 先不视为免费完全体；如要替 L4/L3 深度基本面，需评估预算 |
| Benzinga | 新闻 API 需要 token，官网有 free key 入口但具体权限看计划 | 可注册试用；新闻进入主链前仍需升级为正式数据源 |
| Trading Economics | 官方要求订阅 plan 后获取 API key | 不属于免费优先项 |

## 五层覆盖矩阵

### L1：宏观、流动性、利率

人话问题：大环境是在给 NDX 松绑，还是在加压？

| 当前数据 | 当前来源 | OpenBB 候选 | 第一批实测 | 判断 |
| --- | --- | --- | --- | --- |
| 10Y、2Y、10Y-2Y | FRED / H.15 | `economy.fred_series`, `fixedincome.government.treasury_rates`, `fixedincome.government.yield_curve` | FRED `DGS10` 可返回；Federal Reserve treasury rates 可返回 | 高优先级替换/统一入口 |
| 10Y real rate / breakeven | FRED | `fixedincome.government.tips_yields`, `economy.fred_series` | TIPS yields 可返回，但字段口径需确认是否等价当前序列 | 可替换，但要先做字段映射 |
| Fed funds / SOFR / M2 / WALCL / TGA / RRP | FRED / Federal Reserve | `fixedincome.rate.*`, `economy.money_measures`, `economy.fred_series` | OpenBB coverage 已包含 | 高优先级，适合先做 OpenBB adapter |
| 铜金比、油金比 | yfinance 期货代理/FRED commodity | `commodity.price.spot`, `equity.price.historical` 或 `yfinance` provider | 尚未逐项测 | 可交叉校验，先不急着替换 |

L1 结论：最适合先接 OpenBB。因为 FRED / Federal Reserve 本来就是官方或准官方序列，OpenBB 能减少我们自己维护 URL、参数、字段清洗的重复劳动。

### L2：风险偏好、信用、波动

人话问题：市场是在拥抱风险，还是在买保险、躲风险？

| 当前数据 | 当前来源 | OpenBB 候选 | 第一批实测 | 判断 |
| --- | --- | --- | --- | --- |
| HY OAS / IG OAS / HY CCC-BB | FRED / ICE BofA | `economy.fred_series`, `fixedincome.spreads.*` | HY OAS 可返回 | 高优先级替换/统一入口 |
| VIX / VXN | yfinance + Alpha Vantage fallback | `index.price.historical(provider="cboe")` | CBOE VIX 可返回 open/high/low/close | VIX 可优先替换；VXN 需单独测 symbol |
| QQQ options chain | 当前主链未系统化 | `derivatives.options.chains(provider="cboe")` | QQQ options chain 可返回 11326 行 | 很有价值，但默认是当前链，回测只能做 live 观察或另找历史期权源 |
| HYG momentum / XLY-XLP | yfinance | `equity.price.historical` / `etf.historical` | price provider 已测 QQQ，需扩 HYG/XLY/XLP | 可替换，日期语义要一致 |
| CNN Fear & Greed | CNN 接口 | OpenBB 无明显等价 | 未测 | 保留现有，或降为 sidecar |

L2 结论：信用和 VIX 可以优雅替；期权链对实时观察价值大，但历史回测不能直接用当前链。

### L3：指数内部健康度、广度、集中度

人话问题：指数强，是很多股票一起强，还是少数巨头撑着？

| 当前数据 | 当前来源 | OpenBB 候选 | 第一批实测 | 判断 |
| --- | --- | --- | --- | --- |
| NDX 成分股 | `nasdaq-100-ticker-history` / Nasdaq API / Wikipedia / 静态兜底 | `index.constituents` | `NDX` 在 FMP/CBOE provider 下不直接通过；FMP 接受 `nasdaq` 这类枚举口径 | 不能直接替换，需 symbol/口径适配和历史 as-of 证明 |
| advance/decline、% above MA、新高新低、McClellan | 当前用 NDX 成分股 + yfinance 批量价格自算 | OpenBB 可取价格，但不直接提供 point-in-time NDX breadth | 未完整测 | 可用 OpenBB 取价，但广度逻辑仍应保留在项目内 |
| QQQ/QQEW 比率 | yfinance / Alpha Vantage fallback | `equity.price.historical`, `etf.historical` | QQQ price 可返回；QQEW 未测 | 可替换取价，不替换解释逻辑 |
| QQQ Top10 concentration | Invesco holdings + price proxy | `etf.holdings(provider=fmp/tmx/intrinio)` | FMP QQQ holdings 402 订阅受限；TMX 返回 0 行 | 当前 OpenBB 不能替换现有 Invesco 路线 |
| M7 fundamentals | yfinance latest-only | `equity.fundamental.metrics`, `equity.fundamental.income/cash/balance`, SEC company facts | FMP / Finviz / SEC 均能拿单股数据 | 实时模式可大幅改善；回测必须解决 first-reported / as-of |

L3 结论：这是最需要 OpenBB 但也最不能粗暴替换的一层。OpenBB 能帮我们拿更多成分股价格和基本面，但 point-in-time universe、ETF 持仓日期、成分股历史口径仍必须由 vNext 自己把关。

### L4：估值、盈利、权益风险溢价

人话问题：现在价格相对盈利、现金流和无风险利率，划不划算？

| 当前数据 | 当前来源 | OpenBB 候选 | 第一批实测 | 判断 |
| --- | --- | --- | --- | --- |
| 成分股 PE / Forward PE / FCF yield | yfinance 成分模型 + manual/Wind + third-party checks | `equity.fundamental.metrics`, `equity.estimates.*`, `equity.historical_market_cap` | FMP AAPL metrics、Finviz AAPL metrics、FMP consensus 均可返回 | 实时模式非常值得替换/交叉校验 |
| 盈利预期 | yfinance trend / 当前值 | `equity.estimates.consensus`, `forward_eps`, `historical` | consensus 可返回 | 有希望，但要验证覆盖率和时间戳 |
| SEC 官方财报事实 | 目前不是主 L4 底座 | `equity.compare.company_facts`, `regulators.sec.*` | AAPL Revenues 可返回 reported_date / period_ending / accession | 很适合补审计和 first-reported 线索 |
| Damodaran ERP | 自写下载解析 | OpenBB `economy.risk_premium(provider=fmp)` 可能是替代；Damodaran 本身不在 OpenBB 核心 | 未测 | 保留现有，OpenBB 只做交叉校验 |
| WorldPERatio / Trendonify / 蛋卷 | 网页/sidecar | OpenBB 无明确等价 | 未测 | 保留为实时交叉校验，不进严格回测主证据 |

L4 结论：OpenBB 对实时 L4 很有吸引力，尤其 FMP / Finviz / SEC。但历史回测最容易被“今天的基本面”污染，所以必须先建 `as_of` 规则和 DataIntegrity 检查，再进入主证据。

### L5：价格趋势、波动、量价

人话问题：价格路径强不强、动量是否确认、交易是否拥挤？

| 当前数据 | 当前来源 | OpenBB 候选 | 第一批实测 | 判断 |
| --- | --- | --- | --- | --- |
| QQQ OHLCV | yfinance | `equity.price.historical(provider=polygon/yfinance/fmp/tiingo/...)` | Polygon 和 yfinance 均可返回；Polygon 多 `vwap/transactions` | 高优先级替换/交叉校验 |
| RSI / MACD / ADX / Donchian / VWAP | 项目自算 + `ta` | `technical.rsi/macd/adx/donchian/vwap/...` | 用 OpenBB prices 计算 RSI/MACD/VWAP/Donchian/ADX 均通过 | 可把 OpenBB technical 作为公式引擎候选 |
| OBV / MFI / CMF | 项目自算 + `ta` | `technical.obv`, `technical.ad`, `technical.adosc` 等 | 尚未逐项测完 | 值得继续测 |

L5 结论：这是最容易优雅接入的一层。OpenBB 可以负责统一取价，本项目保留“技术指标不能越权证明估值便宜”的解释纪律。

## 第一批实测结果摘要

| 测试 | 结果 | 说明 |
| --- | --- | --- |
| `obb.economy.fred_series("DGS10")` | 通过 | FRED 10Y 可取 |
| `obb.fixedincome.government.treasury_rates(provider="federal_reserve")` | 通过 | 国债曲线可取 |
| `obb.fixedincome.government.tips_yields(provider="fred")` | 通过 | 字段口径需映射 |
| `obb.economy.fred_series("BAMLH0A0HYM2")` | 通过 | HY OAS 可取 |
| `obb.index.price.historical("VIX", provider="cboe")` | 通过 | CBOE VIX 可取 |
| `obb.derivatives.options.chains("QQQ", provider="cboe")` | 通过 | 当前期权链可取，但历史回测不能直接用 |
| `obb.index.constituents("NDX", provider="fmp")` | 失败 | OpenBB/FMP 要求枚举如 `nasdaq`，不是 `NDX` |
| `obb.index.constituents("NDX", provider="cboe")` | 失败 | CBOE symbol 集合不是 NDX 直觉口径 |
| `obb.etf.holdings("QQQ", provider="fmp")` | 失败 | 当前 FMP subscription 不含该 endpoint |
| `obb.etf.holdings("QQQ", provider="tmx")` | 返回 0 行 | 不可作为 QQQ holdings 来源 |
| `obb.equity.fundamental.metrics("AAPL", provider="fmp")` | 通过 | 有 market cap、EV、估值和质量字段 |
| `obb.equity.fundamental.metrics("AAPL", provider="finviz")` | 通过 | 有 PE、forward PE、margin、ROA/ROE 等 |
| `obb.equity.estimates.consensus("AAPL", provider="fmp")` | 通过 | 有 target consensus 等字段 |
| `obb.equity.compare.company_facts("AAPL", fact="Revenues", provider="sec")` | 通过 | 有 reported_date、period_ending、accession |
| `obb.equity.price.historical("QQQ", provider="polygon")` | 通过 | OHLCV + VWAP + transactions |
| OpenBB technical on QQQ prices | 通过 | RSI、MACD、VWAP、Donchian、ADX 均可算 |

## 替换路线

### 第一阶段：OpenBB 作为统一入口和交叉校验

优先做：

1. L1 FRED / Federal Reserve adapter。
2. L2 FRED credit + CBOE VIX adapter。
3. L5 QQQ price + OpenBB technical formula engine experiment。
4. L4 单股 FMP / Finviz / SEC coverage probe，只进实时交叉校验，不进严格回测主证据。

完成标准：

- 每个 adapter 输出项目现有字段形状，不让下游 agent 感知 provider 变化。
- 每个 OpenBB 输出都补 `source_name`、`source_tier`、`data_date`、`collected_at_utc`、`fallback_chain`。
- 若 OpenBB 返回当前值但无法证明历史可见，回测模式必须跳过或写入 limitation。

### 第二阶段：覆盖率实验

优先测：

1. 对完整 NDX 成分股跑 FMP / Finviz / SEC 单股 coverage。
2. 比较 yfinance 当前 L4 成分模型 vs OpenBB FMP / Finviz / SEC 字段覆盖率。
3. 找出 `index.constituents` 的正确 Nasdaq-100 口径，以及它是否支持历史 as-of。
4. 针对 Tiingo / Nasdaq Data Link / Tradier 注册 key 后补测。

完成标准：

- 产出 `function_id -> OpenBB candidate -> coverage -> date semantics -> replacement verdict` 矩阵。
- 对 L3/L4 每个候选标记：`replace`、`cross_check_only`、`live_only`、`research_candidate`、`not_suitable`。

### 第三阶段：谨慎替换主链

优先替换：

- L1 官方序列。
- L2 信用和 VIX。
- L5 价格数据和公式引擎。

暂不直接替换：

- L3 point-in-time universe。
- QQQ holdings / top10 concentration。
- L4 历史基本面和估值分位。
- 新闻和事件类数据。

## 需要用户手工注册的 key

我不能代替用户完成邮箱注册、验证码、登录或付费授权。建议按优先级注册：

1. `tiingo_token`：免费账号，适合测试价格和新闻补源。
2. `nasdaq_api_key`：免费账号可拿 key，但数据集分免费/付费，适合测日历和 Nasdaq Data Link 数据。
3. `tradier_api_key` + `tradier_account_type=sandbox`：适合系统化测试期权链。
4. `eia_api_key` / `congress_gov_api_key` / `bls_api_key`：公共数据 key，主线优先级低于金融市场数据。
5. `benzinga_api_key`：新闻/分析 API，进入主链前必须先作为 sidecar。
6. `intrinio_api_key`：更像商业升级项，适合预算评估后再接。

## 风险边界

- OpenBB 标准化了接口和字段，但不等于替我们完成所有单位换算、投资语义、数据新鲜度和 point-in-time 审计。
- OpenBB 里同一个 command 的不同 provider 可能口径不同；不能因为都叫 `metrics` 就当成同一事实。
- provider 返回成功不等于能用于回测。`period_ending`、`reported_date`、`collected_at_utc`、`effective_date` 要分开。
- 当前 `.env` 里已有 Finnhub / SimFin key，但 OpenBB 4.7.1 官方 provider 列表没有对应扩展；这些仍属于项目现有独立数据源，不应误记为 OpenBB 覆盖。

## 资料来源

- OpenBB provider 官方列表：<https://docs.openbb.co/odp/python/extensions/providers>
- OpenBB credentials 官方说明：<https://docs.openbb.co/platform/settings/user_settings/api_keys/>
- OpenBB data source / default provider 官方说明：<https://docs.openbb.co/odp/cli/data-sources>
- BLS API 官方说明：<https://www.bls.gov/bls/api_features.htm>
- EIA API key 注册说明：<https://www.eia.gov/opendata/register.php>
- Congress.gov API 官方说明：<https://www.loc.gov/apis/additional-apis/congress-dot-gov-api/>
- Nasdaq Data Link getting started：<https://docs.data.nasdaq.com/docs/getting-started>
- Tiingo token 说明：<https://www.tiingo.com/kb/article/where-to-find-your-tiingo-api-token/>
- Tradier token 说明：<https://docs.tradier.com/docs/endpoints>
- Alpha Vantage API 文档：<https://www.alphavantage.co/documentation/>
- Polygon pricing/free tier：<https://polygon.io/pricing/>
- Trading Economics API authentication：<https://docs.tradingeconomics.com/get_started/>
