# NDX vNext 数据与事实层审计（Audit A：数据层）

审计范围：`src/core/collector.py`、`src/tools_L1~L5.py`、`src/tools_common.py`、`src/tools.py`、
`src/tools_finnhub.py`、`src/tools_simfin.py`、`src/data_evidence.py`、`src/data_manager.py`、
`src/manual_data.py`、`src/api_config.py`、`src/browser_sidecar.py`、`data_cache/`、
`output/analysis/vnext/20260709_233816/`、`output/analysis/vnext/20260710_auditfix/`。

方法：只读代码 + artifact 抽样核实，不采信 codex 审计的结论、不采信项目自述文档（DATA_COVERAGE_REVIEW.md /
WORK_LOG.md）的自我评价。所有结论标注 file:line 或 artifact 路径；无法在本次调查中独立核实的地方明确标"未核实"。

---

## ① 理想形态（先给基准，后面对照）

对"给 NDX 做可靠投资判断"这个目的，数据层的理想形态大致是：

1. **一个统一的、带类型的观测 schema**，在每个数据函数的出口强制校验（而不是事后靠约定+尾部补丁校验）。
2. **一个规范的 point-in-time 时间序列存储**，以 `(series_id, vintage_date, observation_date)` 为键，对可修订序列（FRED 类宏观数据）保留首次发布版本，而不是"最新 CSV 快照 + 追加"。
3. **来源选择有一张显式的、代码外可核对的权威表**，并有自动化测试断言"每个函数声明的 source_tier 与它真实的抓取机制相符"（这一点如果做到，能自动挡住下面发现 4 那类问题）。
4. **一套缓存**，而不是两套；陈旧度（staleness）必须作为返回值的一部分随数据流走，而不是只打印日志。
5. **发布闸门以"最弱达标层"为准，而不是全局加权平均**——因为项目自己的北极星就是"每一层回答一个独立的、有分量的问题"，一层被打穿而报告仍显示"整体可发布"在语义上是错的。

下面的现状评估，就是拿这五条对照检查。

---

## ② 现状实际如何运作

### 数据源总表（逐层，基于代码核实，不是文档自述）

| 层 | 指标（函数） | 真实来源 | 获取方式 | 权威评级（我的判断） | 证据 |
|---|---|---|---|---|---|
| L1 | 10Y2Y利差/联邦基金利率/10Y实际利率/10Y国债/10Y盈亏平衡/HY OAS/IG OAS | FRED | API（有key）→ pandas_datareader FRED → fredgraph.csv 无key兜底，三级降级 | **官方**，多级 fallback 设计良好 | `tools_common.py:1196-1284` |
| L1 | M2 YoY | FRED M2SL | 同上 | 官方 | `tools_L1.py:519-543` |
| L1 | 净流动性动量 (WALCL-TGA-RRP) | FRED WALCL/WTREGEN/RRPONTSYD | 同上，含单位换算（WALCL、TGA 除以1000转十亿美元，RRP 不转换） | 官方；单位换算合理但**本次未独立核对 FRED 官方单位文档**，仅核实了代码注释与换算逻辑自洽 | `tools_L1.py:546-585` |
| L1 | 铜/金比率、XLY/XLP 比率 | yfinance（HG=F/GC=F/XLY/XLP）经 `TimeSeriesManager` 本地 CSV 缓存 | 免费零售数据代理 | **免费代理**，非官方 | `tools_L1.py:600-1080` |
| L2 | VIX、VXN、HYG动量 | yfinance | 同上 | 免费代理 | `tools_L1.py:206-`, 全局 grep |
| L2 | HY OAS/IG OAS/HY quality spread | FRED | 同 L1 | 官方 | — |
| L2 | CNN Fear & Greed Index | CNN 官方生产环境 API（`production.dataviz.cnn.io`，未公开文档的内部端点） | 直接调用其 JSON 端点 | **半官方**：数据确属 CNN，但是未公开/未承诺稳定的内部接口 | `tools_L2.py:1211-1240` |
| L2 | Crowdedness dashboard | 仅人工录入模板，无自动路径 | 人工 | 若填写则"人工授权"；空模板时不可用 | `manual_data.py:189-200` |
| L3 | Advance/Decline、%above MA、New Highs/Lows、McClellan | 用 yfinance 抓取 NDX100 全部成分股价格自算 | 自建代理（component_model） | **自建代理**，不是官方broad-market breadth feed；已被 `data_evidence.py` 标为 `COVERAGE_REQUIRED_FUNCTIONS` | `tools_L2.py:697-1060` |
| L3 | NDX/NDXE 比率、QQQ Top10 集中度 | yfinance / Invesco 官方持仓 API（主） | Invesco 官方 → 本地快照 → yfinance代理 → 不可用，四级链 | 主路径官方，兜底为代理 | 见 `data_integrity_report.json` fallback_chain |
| L4 | NDX Wind 估值快照 / Wind 点时盈利预期 | Wind（经本机 `wind-mcp-skill` Node CLI，向 `aifinmarket.wind.com.cn` 发**自然语言问题**，再用正则/子串匹配从返回表格中解析字段） | "licensed_provider" 标签，但实际是 NL 问答 + 正则解析管线 | **形式上licensed provider，机制上脆弱**（见风险 4） | `tools_L4.py:859-1055, 436-466` |
| L4 | NDX P/E 与盈利收益率（默认路径） | `historyofmarket.com`（自称转载 Bloomberg BEst） | 直接 JSON API 请求，代码自己标注 `third_party_bloomberg_attribution_unverified` | **未经验证署名的第三方小站**，被正确标为 third_party_estimate | `tools_L4.py:3995, 4116-4260` |
| L4 | NDX P/E 与盈利收益率（可选组件模型） | yfinance 全部成分股基本面自算聚合 P/E | 默认**禁用**（需 `NDX_ENABLE_COMPONENT_MODEL=1`），聚合公式正确（Σmcap/Σearnings，非简单平均PE） | 免费代理，默认关闭 | `tools_L4.py:4276-4277, 1725-1854` |
| L4 | Damodaran 隐含 ERP | Damodaran (NYU Stern) 官方月度 Excel | 下载/本地缓存 `data_cache/damodaran/ERP*.xlsx` | **官方/学术权威**，美国大盘口径，非NDX专属 | `data_cache/damodaran/`, `tools_L4.py:3865` |
| L5 | RSI/ATR/ADX/MACD/OBV/唐奇安/多尺度MA等技术指标 | yfinance QQQ OHLCV 自算（部分用 pandas_ta） | 免费代理 | QQQ 是 NDX 的 ETF 代理，非指数本身，已知的结构性基差 | `tools_L5.py` 全文 |
| — | Finnhub / Simfin 全部函数 | Finnhub API / Simfin API | **在 `TOOLS_REGISTRY` 中注册但从未被 `collector.py::LAYER_FUNCTIONS` 或任何 L1-L5 函数调用** | 死代码，非当前生产路径 | `tools.py:19-43,78-160`；`grep` 未命中 `tools_L4.py`/`collector.py`/`main.py` |

结论：来源清单本身相当讲道理——官方源（FRED、Invesco、Damodaran）优先，免费代理（yfinance）诚实标注为 proxy/third_party，人工数据有独立 schema 且默认不覆盖。**问题不在"选错了源"，而在"源到报告之间的管道有具体、可验证的裂缝"**，见下节。

---

## ③ 关键发现（按"污染投资判断"的危险程度排序，均已核实，标注处除外）

### 1.【最高】全局加权置信度会掩盖某一层被打穿——已在真实 run 中发生过
`output/analysis/vnext/20260709_233816/data_integrity_report.json`：
```
layer_breakdown.1 = {total: 8, success: 3, confidence: 37.5}
confidence_percent: 69.3, blocking_reasons: [], publish_status: "publishable"
```
L1（宏观流动性——项目自己定义的"第一层判断"）当次 run 只有 3/8 指标成功（37.5%），但报告仍是"可发布、0 阻断原因"。原因：`src/core/checker.py` 的置信度是 42 个指标的**全局加权平均**，L1 只占 8 个，即使整层近乎失效，加权总分仍可能高于 60% 发布线。

能挡住这个问题的"每层最低及格线"逻辑（`MIN_FORMAL_LAYER_CONFIDENCE_PERCENT = 50.0` + `weak_layers` 检查，`src/core/checker.py:23,233-245,351`）**目前只存在于当前分支的未提交改动里**：
```
git diff src/core/checker.py
+ MIN_FORMAL_LAYER_CONFIDENCE_PERCENT = 50.0
+ weak_layers = [...]
+ if weak_layers: blocking_reasons.append("critical_layer_below_publish_floor...")
```
即：产生 `20260709_233816` 那份"可发布"报告时，这道闸门根本不存在。今天（`20260710_auditfix`）的新 run 各层都接近满分，看不出问题，但这恰恰说明——**这个系统此前允许"核心层近乎失效仍标可发布"这种情况真实发生过**，现在才刚打上补丁，且补丁本身只有 50% 的层内及格线（8个指标里对4个就算过），仍偏宽松。已用 `pytest tests/test_core_checker.py tests/test_data_evidence_contract.py`（28 passed）验证新逻辑单测层面自洽，但未看到用这次真实历史 run 数据重放验证。

### 2.【高】TimeSeriesManager 的陈旧度检测是"孤儿代码"，从未被下游读取
`src/data_manager.py:64-112`：增量更新失败时把 `stale_info`/`was_stale` 写入 DataFrame 的 `.attrs`。
全仓库 `grep -rn "was_stale\|attrs\[.stale.\]\|attrs.get(.stale.)"` 只在 `data_manager.py` 自身命中——**没有任何调用方读取它**。VIX、XLY/XLP、铜/金比率（L1/L2 风险偏好输入）都走 `_get_series_for_effective_date → ts_manager.get_or_update_series`（`tools_L1.py:166-180`），返回值统一被标成 `"source_name": "yfinance (cached)"`，无论这次是不是刚好命中了陈旧缓存。这意味着：如果 yfinance 连续几天限流/网络故障，这些指标可以悄悄地把陈旧数据当作当期数据交给分析层，而 `data_quality.anomalies` 里完全看不到这件事。

### 3.【高】`cached_yf_download` 的陈旧缓存兜底容忍 7 天静默，且未被所有调用方消费
`src/tools_common.py:772,829` 在网络失败时调用 `_read_yf_frame_cache(cache_key, requested_tickers=...)`，**未传 `max_age_seconds`**，因此使用默认值 `YF_FRAME_CACHE_MAX_AGE_SECONDS = 7*24*3600`（`tools_common.py:108`）——即最多 7 天前的缓存都会被无条件接受。系统确实会记一条 `cache_fallback` 运行事件并汇总进 `data_integrity_report.notes`（"yfinance 运行诊断: ... cache_fallback=N"），这点比我最初预期的要好；但这只是一句笼统的运行诊断，**不指向具体哪个指标、不进入该指标自己的 `data_quality.anomalies`、也不参与发布闸门**。而且只有 `tools_L5.py:122-123` 和 `tools_L2.py:248` 真正检查了 `frame.attrs.get("market_data_source")`，L1 的铜/金、XLY/XLP 路径完全没有消费这个标记（`grep` 核实，见下）。

### 4.【中高】Wind"licensed_provider"数据实际是自然语言问答+正则解析管线，且同一机制下不同字段的权威评级不一致
`tools_L4.py:436-466` (`_call_wind_cli`)：向本机 `~/.agents/skills/wind-mcp-skill` 的 Node CLI 发送**中文自然语言问题**（如 `"纳斯达克100指数最新市盈率市净率市销率风险溢价"`），目标是 `aifinmarket.wind.com.cn`，返回的是自然语言/表格文本，再靠 `_extract_wind_rows`/`_wind_row_value` 的字符串包含匹配（`tools_L4.py:561-573`）从中"猜"出字段。代码自己对 `RiskPremium` 字段标了非常诚实的免责声明：`"provider_label_definition_unverified"`——"这是自然语言响应，不保留字段代码/公式/单位，不要解读绝对值，直到验证字段定义"（`tools_L4.py:986-995`）。但**同一次 NL 往返里解析出来的 PE/PB/PS**，被标成 `"core_allowed"` / `"licensed_provider_wind_index_fundamentals"`，没有等价的免责声明（`tools_L4.py:967-985`）。同一个抓取机制，风险评级却不一致——这不是"权威表本身错了"，而是"权威表没有跟机制的脆弱性对齐"。

### 5.【中】默认自动路径的 NDX 市盈率主来源是一个不知名第三方网站，署名不可验证
`tools_L4.py:3995`：`HISTORY_OF_MARKET_NDX_URL = "https://historyofmarket.com/api/ndx/forward-pe.json"`。代码正确地把它标为 `third_party_estimate`，并且自己注明 `"third_party_bloomberg_attribution_unverified"`（`tools_L4.py:4547-4552`）——自我认知是诚实的。但它仍然是 `get_ndx_pe_and_earnings_yield`（L4 六个核心估值指标之一）**默认、免配置**的主路径（`tools_L4.py:4280-4297` 注释明确写"Primary source: History of Market"），组件模型兜底默认关闭。一个没有 SLA、没有版本保证、无法独立审计的小站长期作为核心估值判断的默认主来源，这是结构性脆弱，即使代码已经诚实标注。

### 6.【中】回测下 NDX 成分股列表可能"幸存者偏差"地退化为当前成分股
`tools_L3.py:60-86`：`get_ndx100_components(end_date=...)` 优先用 `nasdaq_100_ticker_history` 包按日期取历史成分股；若该年份无数据，向前最多回溯 5 个年末尝试；**全部失败后**，日志打印 `"历史数据不可用，使用最新成分股（可能存在幸存者偏差）"`，然后继续往下走实时模式的抓取策略（Nasdaq 官网 API / Wikipedia）——也就是说，一次回测到 2015 年之前的 run，理论上可能拿到接近"今天"的成分股列表。日志写清楚了警告，但**我没有在本次审计中核实这个具体分支是否会把"当前成分股用于历史回测"这件事写入 `backtest_data_boundaries`**（collector.py 的 `strict_backtest_invariants.declared_limitations` 里有笼统的 `point_in_time_universe_not_enforced` 声明，但没看到专门标记这条分支触发过）——**此条标"部分未核实"**。

### 7.【中】两套互不感知的缓存子系统，陈旧度口径不一致
- `SharedDataCache` + `cached_yf_download` 持久化 pickle 缓存（`tools_common.py:365-524`）：12 小时"优先新鲜"，7 天"仍可接受"。
- `TimeSeriesManager` 本地 CSV 缓存（`data_manager.py`）：7 天警告阈值，但只打印不阻断，且陈旧标记是孤儿代码（见发现2）。
两套系统互相不知道对方的存在，同一个 ticker（如 VIX）可能同时被两套缓存以不同策略、不同陈旧口径管理，人工排查"这个数字到底新不新鲜"需要同时读两处代码。

### 8.【中低】`data_cache/yfinance/` 下 393+ 个哈希命名的 pkl/json 文件，无可读索引
`tools_common.py:371-380`：缓存文件名是 `sha1(cache_key)[:24]`，没有任何映射表能告诉人类"这个文件对应哪个 ticker、哪个日期区间、抓取于何时"。对一个把"可审计"当作北极星的项目，这是一个具体的、可修复的可审计性缺口。

### 9.【低】Finnhub / Simfin 模块（约1,388行）已注册但零调用
`tools.py:19-43,78-160` 把两个模块的十几个函数全部注册进 `TOOLS_REGISTRY`，但 `grep -n "get_stock_quote\|get_m7_finnhub_analysis\|..." src/tools_L4.py src/core/collector.py src/main.py` 全部无命中。不是正确性风险，但是死代码维护负担，且容易让人误以为"有 Finnhub 兜底"而实际没有。

### 10.【低，卫生问题】大量乱码（编码损坏）注释/日志字符串
例如 `tools.py:168-169`、`tools_common.py:353-354,682-684`、`core/collector.py:436`（一条乱码日志紧跟着一条正常日志，明显是自动化编辑重复插入所致）。目测只污染了注释/日志文本，**未发现污染到实际数据字段**，但这种规模的编码损坏说明某个自动化编辑工具在这个仓库的历史上曾经反复破坏 UTF-8 编码——对一个几乎全靠 LLM 辅助迭代的仓库，这是一个值得警惕的一般性卫生信号。

---

## ④ point-in-time 纪律：代码实际执行情况

比我基于"用户没有工程背景+反复打补丁"的先验预期要扎实。具体核实到的机制：

- `collector.py::BACKTEST_UNSUPPORTED_FUNCTIONS`（`collector.py:169-194`）：明确列出 6 个"回测下不可信"的函数（m7基本面、QQQ Top10、Wind快照、NDX P/E的组件兜底、forward earnings quality、equity risk premium），回测时直接跳过并写入 `backtest_data_boundaries`——这是真代码，不是文档承诺。
- `checker.py::_iter_future_date_candidates`（`checker.py:112-135`）：递归遍历每条指标 payload 的所有 dict/list，对日期类字段名做未来日期检查，**还对 `note/notes/reason` 等自由文本用正则扫描 `\d{4}-\d{2}-\d{2}` 模式**，任何超过 `backtest_date` 的都会硬阻断发布。这个"扫自由文本里的日期"的细节，比大多数同规模项目在这个阶段做得更严格。
- `get_ndx_wind_valuation_snapshot` 在有 `end_date` 时直接拒绝提供 Wind 数据（`tools_L4.py:875-876`），不做"退而求其次"。
- `get_ndx100_components` 对历史成分股有真实的三级尝试（见发现6），不是简单地"假装用了历史数据"。
- `data_manager.calculate_long_term_stats` 的百分位/Z分数窗口锚点默认为**输入序列自身的最大日期**，而不是 `datetime.now()`（`data_manager.py:189`），这避免了最常见的一类回测泄漏（用今天已知的尾部分布去算历史某天的"十年分位"）。

**已披露但未强制**的缺口（`collector.py:219-253`，`declared_limitations`）：FRED 类可修订序列未做 ALFRED 首次发布版本还原（`alfred_first_vintage_not_enforced`）、财报/盈利预期未做"当时可见性"校验（`financials_first_reported_not_enforced`）、无完整 point-in-time NDX 成分股宇宙（`point_in_time_universe_not_enforced`）。这些都被标为 `declared_limitation` / `publishable_with_disclosure`，而不是硬阻断——对早期（大约2015-2020年之前）的回测，可信度应该比绿色对勾看起来的要低，这一点系统自己承认了，但承认的方式是"允许发布并注明"，而不是"拒绝发布"。

---

## ⑤ 架构评估

- **没有统一数据模型**：每层函数直接返回一个 `dict`，形状靠约定 + `data_evidence.py::normalize_data_evidence()` 事后规范化来维持，而不是入口处的强类型 schema。这个选择本身不算差——面对 FRED JSON、yfinance DataFrame、Wind 自然语言响应、人工 JSON、Damodaran Excel 这么异构的来源，"晚绑定校验"是合理权衡——但意味着正确性依赖每个函数作者记得正确调用 `build_data_quality()`，出错只能靠尾部的 `data_evidence_issues()`（`data_evidence.py:401-471`，有 hard_block/degraded/audit_warn 三级分诊，本身设计得相当成熟）兜底。
- **缓存不统一**：两套系统并存（发现7）。
- **错误处理总体一致，但一致性有梯度**：`collector.py::_collect_single_indicator` + `_finalize_indicator_result`（`collector.py:255-353`）对每个指标统一 try/except + 失败分类，这层是扎实的；但具体指标函数内部的错误处理精细度差异很大——Wind、History of Market、FRED 链条的降级诊断非常细，简单的 yfinance 单源指标（铜/金、XLY/XLP）则薄得多。
- **整体判断**：这不是一堆无架构的胡乱拼凑。真实存在一层证据合约（`data_evidence.py`）、一套回测边界系统（`collector.py` 的 `BACKTEST_UNSUPPORTED_FUNCTIONS`/`strict_backtest_invariants`）、一个带递归未来日期扫描的发布闸门（`checker.py`），以及若干处对 point-in-time 很较真的具体实现（NDX 成分股历史包、百分位窗口锚点）。但同时能看到明显的"有机、被动生长"痕迹：两套并行缓存、证据合约被不同文件采纳的程度不一致、一个刚打上但还未经真实数据回放验证的关键发布闸门补丁（发现1，且这个补丁就在当前未提交的工作区里）、编码损坏、约1,400行零调用的死代码。这和用户自述的"非工程背景+高强度 LLM 辅助反复打补丁"的画像是吻合的（这一点是我基于代码模式的推测，不是采信用户自述或 codex 审计的结论）。

---

## 总判断：保留 / 改良 / 推倒重来？

**改良，不是推倒重来。**

理由：这一层已经具备一个"从零重新设计"大概率也会长成的骨架——证据合约（provider/source_tier/fallback_chain/coverage/anomalies）、回测可见性边界、递归未来日期扫描、point-in-time 百分位锚点。这些不是装饰性的文档承诺，是我在代码里逐条核实过的真实机制。真正找到的问题，几乎都是"管道里具体的裂缝"，而不是"地基选错了"：

- 发现1（全局置信度掩盖单层失效）是**设计缺陷**，但修法是把"最弱层及格线"从生成 notes 提升为真正的发布闸门维度（当前分支已经在做，只是还没有用历史 run 数据验证过，且阈值偏宽松）。
- 发现2、3、7（陈旧度检测孤儿代码 + 两套缓存）是**集成缺口**，不需要重写抓取逻辑，只需要把已经存在的 staleness 信号接到已经存在的 `data_quality.anomalies` 管道里。
- 发现4、5（Wind NL 解析、historyofmarket.com 第三方署名）是**权威评级颗粒度不够细**，代码已经知道这些风险（甚至写了很诚实的免责声明），只是没有把这种诚实度应用得一致。
- 发现6、9、10 都是清理性质，不影响地基。

**真正值得警惕、且不该被"改良"这个判断冲淡的一点**：发现1 说明的不是"某个函数有 bug"，而是"这套系统曾经真实地把一份 L1 几乎失效（37.5%成功率）的报告标记为'69.3%置信度、可发布、零阻断原因'并流向了用户"（`20260709_233816` 是一次真实产生并写入 `run_summary.json` 的 run，`final_stance` 字段里还有一句完整的市场判断文字）。这不是理论风险，是已经发生过的、我在 artifact 里直接核实到的事实。在这类"发布闸门本身会静默失效"的问题被系统性地用测试+历史数据回放验证修复之前，任何"当前 confidence_percent 看起来不错"的单次 run 都不能被直接采信为"这层现在没问题"。

---

## ⑤ 给总报告的核心启示（5条）

1. **不要相信任何单次 run 的"confidence_percent / publishable"标签**——刚刚证实过它可以在核心层近乎失效时仍然显示"可发布、零阻断"（`20260709_233816`）。这个漏洞的修复补丁存在于当前未提交的工作区，尚未经真实历史数据回放验证，阈值也偏宽松（50%）。这应该是所有后续审计（尤其是给 L1-L5 数据质量打分的部分）的第一优先级前提条件。
2. **"licensed_provider"标签不等于机制可靠**——Wind 数据源实际是自然语言问答+正则解析管线，代码对不同字段的风险披露不一致（PE/PB/PS 标"core_allowed"，RiskPremium 标"unverified"，但抓取机制完全相同）。审计其他层时应该系统检查"权威标签"是否真的对应"抓取机制的脆弱性"，而不是只看标签字面。
3. **陈旧数据的"静默替代"是当前最容易被忽视的正确性风险类别**——不是因为没有陈旧度检测，而是检测存在但和展示/阻断链路断开了（发现2、3）。这提示：审计其他层（尤其是B、C分组如果覆盖了报告生成/跨层推理）时，应该专门检查"某个数值被标为 available，但它的 provenance 链条里其实经过了一次 stale fallback"这种情况在 evidence_ref 层面是否可追溯。
4. **默认路径 vs 可选路径的权威差异很大，但报告消费者未必能分辨**——例如 NDX P/E 默认主源是未经验证署名的第三方小站，而更权威的组件模型默认是关闭的（需要环境变量）。如果总报告/最终 brief 没有把"这是默认路径还是加固路径"讲清楚，读者可能高估某个数字的可信度。
5. **这一层的架构底子是好的，值得投入"打通集成缺口"而不是重写**——证据合约、回测边界、递归未来日期扫描这三件事做得比预期扎实，说明团队/工具链在关键的正确性原语上是有认知的；剩下的工作主要是"把已经写好但没接通的信号接通"（陈旧度、层级发布闸门的历史验证）和"清理"（死代码、编码损坏、缓存去重），性价比高于推倒重来。
