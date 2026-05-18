# vNext 工作记录

阅读方式：最新完成事项放在最上面。这里记录已经完成的事；未来要做的事写在 `NEXT_STEPS.md`。

---

## 2026-05-18

### 回测模式 L4 yfinance 成分股代理宁缺勿错

完成内容：

- 按最新拍板，回测模式承认 LLM 有不可完全消除的后验风险，不额外收紧模型表达空间；工程侧只负责保证进入 agent 上下文的数据不晚于回测日，并把缺失、跳过和降级写清楚。
- 回测模式下，未提供人工/Wind 覆盖时，`get_ndx_pe_and_earnings_yield`、`get_ndx_forward_earnings_quality`、`get_equity_risk_premium` 自动跳过，不再触发 yfinance 成分股基本面批量代理，也不再试图在核心股票大面积缺失后给一个看似精确的置信度。
- `DataCollector.run()` 新增 `backtest_data_boundaries`，集中记录本次回测哪些指标被跳过、为什么跳过、对应的 `effective_date`，以及未来需要接入能证明回测日可见性的历史数据源后再启用。
- 保留人工/Wind 高信任覆盖路径：如果 `manual_data.py` 提供了有效的 NDX 估值数据，回测仍可使用人工数据，不会被自动跳过规则挡掉。
- `NEXT_STEPS.md` 已把 yfinance 审计改为实时模式审计，并记录严格回测后续升级边界：ALFRED first-vintage、财报 first-reported、point-in-time universe 和 LLM 训练后验知识后续单列设计。
- 记录历史数据研究助理方向：联网 AI skill 只能先生成 `research_candidate` / `manual_review_required` 候选证据包，并把每次如何找到历史数据的路径、日期字段、失败原因和验证办法沉淀下来；稳定可重复后再升级为正式采集规则。
- 记录采集机 / 快照模式：数据采集和 DeepSeek 推理解耦，先用 `collect-only` 生成不可变数据快照、图表和新闻 sidecar，再由主机消费同一快照运行分析；同机分流和双机采集都可以，但报告必须能追溯到同一数据包。
- 同步 `ARCHITECTURE.md`、`DATA_COVERAGE_REVIEW.md`、`RUN_REVIEW_CHECKLIST.md`、`README.md` 和 `NEXT_STEPS.md`；补充文档瘦身候选，暂不直接删除旧审计/实验材料。

验证结果：

- `python3 -m pytest -q tests/test_collector_manual_valuation_checks.py tests/test_vnext_orchestrator.py::test_backtest_skipped_indicator_is_not_analysis_required tests/test_core_checker.py::test_data_integrity_penalizes_skips_partial_coverage_and_future_dates`：6 passed，4 warnings。

剩余边界：

- 本轮只改变回测采集策略，不解决 yfinance 在实时模式下的字段可靠性；实时模式仍需要后续审计。
- 当前回测目标仍是“数据日期不超过回测日”，不是“每个数据源都还原当时第一版”。后者需要 ALFRED、披露日财报、历史指数成分和更严格数据血缘。

## 2026-05-17

### 2025-04-09 回测前瞻污染 P0 修复

完成内容：

- 修复 CNN Fear & Greed 回测污染：回测模式下只读取 `fear_and_greed_historical.data` 中不晚于 `effective_date` 的最后一点；如果历史点缺失，明确 unavailable，不再回退使用 live `fear_and_greed` 顶层当前值。
- 修复回测跳过项契约不一致：latest-only 指标在回测模式下标记为 `backtest_skipped_unsupported_function`，packet/orchestrator 不再把它们列为 `analysis_required=true`；L4 forward earnings quality 不会再因“已跳过但仍必填”阻断。
- 修复 LLM 把 `historical_percentile` 写成说明文字导致 Pydantic 崩溃的问题：只接受 0-100 数字或百分数字符串，复杂来源说明转入 `raw_data.historical_percentile_note` 并把分位设为 `null`；L4 prompt 同步硬约束。
- 给 `chart_time_series.json`、默认 QQQ/FRED/yfinance supplemental fetchers、Damodaran rows、新闻底账和新闻-数据连接器加 `effective_date` 守门；回测新闻侧栏和 workbench 不再使用回测日之后的事件或市场行。
- 提升 DataIntegrity 口径：回测跳过不再算成功；覆盖率不足、未来数据日期会压低完整性并写入 notes。
- 加强 yfinance frame cache 写入/读取校验：缺少 Close 或 batch ticker 覆盖不完整的 DataFrame 不再写入/命中持久缓存，避免部分失败 batch 被缓存放大。

验证结果：

- `python3 -m pytest -q tests/test_l2_cnn_fgi_backtest.py tests/test_chart_time_series_artifacts.py tests/test_core_checker.py tests/test_vnext_orchestrator.py::test_backtest_skipped_indicator_is_not_analysis_required tests/test_vnext_orchestrator.py::test_historical_percentile_string_is_sanitized tests/test_news_event_ledger.py tests/test_news_event_data_linker.py`：19 passed，4 warnings。
- `python3 -m pytest -q`：286 passed，4 warnings。
- `python3 -m py_compile src/tools_L2.py src/tools_common.py src/chart_adapter_v6.py src/chart_time_series_artifacts.py src/news_event_ledger.py src/news_event_data_linker.py src/core/checker.py src/core/collector.py src/agent_analysis/orchestrator.py src/agent_analysis/packet_builder.py`：通过。

剩余边界：

- 本轮没有解决 ALFRED first-vintage、财报 first-reported、LLM 训练后验知识和 point-in-time universe 建库审计；这些属于严格回测架构项，需要单独设计。
- yfinance cache 现在拒绝明显不完整 batch，但还没有实现 per-ticker normalized cache；重复拉取和并发 SQLite 问题仍可能影响稳定性。

### Workbench Crosshair、流动性早期单位与新闻层中文分析修复

完成内容：

- 修复价格技术 workbench crosshair 读数长期缺失的根因：主价格图内部 key 是 `price`、副图是 `macd/volume/...`，但右侧读数只识别 `price_technical`。现在主图和所有价格技术副图都显式映射回 `price_technical`，hover 后右侧读数稳定显示 OHLC、均线、VWAP、Bollinger、Donchian、Volume、OBV、MACD、RSI、ATR、MFI、CMF。
- 把 MACD 左上角读数从单点范例推广为通用图内读数：价格主图、所有副图、波动信用/利率估值/广度集中度/流动性模块图都会在左上角显示当前 crosshair 对应的可绘制序列值；模块重绘后也会重新注册 crosshair。
- 修复 2009 年前净流动性假负数：WTREGEN/TGA 本地混合缓存中，2007-05-09 到 2008-10-21 一段小于 `10000` 的 FRED 原始“百万美元”值被误当成“十亿美元”。修复后 2008-10-22 前 `WTREGEN > 1000` 的早期混合缓存点统一除以 `1000`，并把原先 pre-2007 的 `/100` 错误修正为 `/1000`。
- 新增 `news_layer_analysis.json` 独立 sidecar：对官方事件生成中文概要、可能对股市的影响、压力通道和新闻层总分析；仍明确不进入 L1-L5，不成为 `evidence_ref`，只作为背景/催化剂/复核线索。
- Native brief 新闻区升级为“新闻中文概要、股市影响与市场连接观察”，顶部展示新闻层总分析，逐条事件展示中文概要和可能影响，原有附近市场序列观察继续作为可展开审计材料。
- 重新生成最新 run 的 `chart_time_series.json`、`news_layer_analysis.json`、`output/reports/vnext_workbench_20260517_1852.html` 和 `output/reports/vnext_brief_20260517_1852.html`。

验证结果：

- `python3 -m pytest -q tests/test_interactive_chart_workbench.py tests/test_tools_calculation.py tests/test_news_layer_analyzer.py tests/test_news_event_data_linker.py tests/test_vnext_reporter.py`：68 passed，4 warnings。
- `python3 -m pytest -q`：278 passed，4 warnings。
- 最新 run 数据复核：`NET_LIQUIDITY` 2009 年前最小值为 `706.10`，不再出现假负数；`2007-05-09` TGA 为 `4.914`、净流动性为 `864.606`；`2008-01-02` TGA 为 `8.693`、净流动性为 `911.994`。
- 浏览器 hover 验证：价格技术 readout 包含 `MA20` / `VWAP20` 且不再显示“该模块暂无”；波动信用 readout 包含 `VIX` 且不再显示“该模块暂无”；页面内共有 10 个 `.chart-inline-legend`。
- `python3 src/report_visual_regression.py --brief-html output/reports/vnext_brief_20260517_1852.html --workbench-html output/reports/vnext_workbench_20260517_1852.html --console-html output/reports/vnext_research_console.html --output-dir output/visual_regression/workbench_news_liquidity_fix`：passed。

剩余边界：

- 新闻层当前为规则化中文解读，不是 LLM 深度新闻分析；它能给出保守影响通道和总分析，但不会也不应声称因果证明。
- 油价尚未进入 `chart_time_series` / 新闻连接器，因此新闻层只能明确提示“无法自动判断油价高企通道”；如要分析该通道，需要后续接入 WTI/Brent。

### Workbench MACD 图内图例与读数补强

完成内容：

- MACD 副图左上角新增图内图例：蓝色 `DIF`、红色 `DEA`、灰色 `Hist`，并直接显示当前同步时间点的数值。
- 图例会跟随十字光标同步更新；没有悬停时显示最新时间点读数。
- 重新生成当前 `output/reports/vnext_workbench_20260517_1852.html`，让浏览器里正在看的 workbench 也能刷新看到新版标注。

验证结果：

- `python3 -m pytest -q tests/test_interactive_chart_workbench.py`：6 passed，4 warnings。
- `python3 -m pytest -q`：275 passed，4 warnings。
- `python3 src/report_visual_regression.py --brief-html output/reports/vnext_brief_20260517_1852.html --workbench-html output/reports/vnext_workbench_20260517_1852.html --console-html output/reports/vnext_research_console.html --output-dir output/visual_regression/macd_legend_fix`：passed。
- `http://127.0.0.1:8765/artifact?...vnext_workbench_20260517_1852.html` 已确认包含 `data-macd-legend`、`DIF`、`DEA`、`Hist`。

### NDX Agent 启动可靠性与研究控制台 demo 重排

完成内容：

- `start.command` / NDX Agent 图标现在每次都会重启本地 control service，而不是复用 8765 上“看起来可用”的旧进程；打开地址附带 `opened_at` 时间戳，避免浏览器缓存旧控制台。
- control service 对 HTML / JSON / artifact 响应补充 `Cache-Control: no-store` 和 `Pragma: no-cache`，保证控制台、最新 brief 和 workbench 链接尽量读取当前文件。
- 研究控制台 demo 按普通用户默认路径重排：首屏优先显示“运行完整报告”、workbench 模块、运行状态、命令预览和最新 brief/workbench/run/log/news 产物；对象日期、模型流程、人工数据和 sidecar 校准保留在后续工作区。
- UI 从“所有功能平铺”改为“先运行与结果，再配置和校准”的操作顺序；移动端自然折成单列，不隐藏原有输入、按钮、开关和 JSON 预览。
- 新增测试覆盖：即使旧 8765 服务已经能返回控制台，启动器也会停止并重新启动，防止点击应用图标继续打开旧页面。

验证结果：

- 真实执行 `./start.command`：打开 `http://127.0.0.1:8765/?opened_at=<timestamp>`；页面返回 `console_logs_entry_v4`、`运行与结果`、`使用人工数据`、`news_event_data_links.json`，且没有旧 `data-manual-field="confidence"`。
- 服务响应头确认 `Cache-Control: no-store, max-age=0`。
- `python3 -m pytest -q`：275 passed，4 warnings。
- `python3 src/report_visual_regression.py --brief-html output/reports/vnext_brief_20260512_2152_20260517_0016.html --workbench-html output/reports/vnext_workbench_20260512_2152_20260517_0016.html --console-html output/reports/vnext_research_console.html --output-dir output/visual_regression/console_interaction_demo`：passed，console/brief/workbench 桌面和移动布局检查均无 issues。

### 控制台启动器旧服务识别与新闻产物入口修复

完成内容：

- 将控制台版本标记升级到 `console_logs_entry_v4`，并把旧人工数据“置信度”表单加入 stale service 判定；`start.command` / 应用图标再次打开时会清理 8765 上的旧服务后重启新版控制台。
- 控制台新闻区从“官方新闻底账”改成“官方事件底账与市场连接观察”，明确完整 vNext 勾选新闻会同时生成 `news_event_ledger.json` 和 `news_event_data_links.json`。
- 控制台新增“最新新闻产物”列表，展示 run 目录里的事件底账和市场连接观察；完整运行完成后的状态链接也会列出事件底账和市场连接观察。
- `/latest-product` API 补充新闻产物 URL，方便前端在运行完成后直接打开相关 JSON。

验证结果：

- 真实执行 `./start.command`：旧 8765 进程被替换，新页面返回 `console_logs_entry_v4`，有“使用人工数据”和“官方事件底账与市场连接观察”，没有 `data-manual-field="confidence"` / “置信度”。
- `python3 -m pytest -q`：274 passed，4 warnings。
- `python3 src/report_visual_regression.py --brief-html output/reports/vnext_brief_20260512_2152_20260517_0016.html --workbench-html output/reports/vnext_workbench_20260512_2152_20260517_0016.html --console-html output/reports/vnext_research_console.html --output-dir output/visual_regression/console_launcher_fix`：passed，console/brief/workbench 桌面和移动布局检查均无 issues。

### Twelve Data 优先与 yfinance 入口收口

完成内容：

- 删除旧 `tools_akshare.py` 后，同步移除 `tools_L4.py` 中 QQQ Put/Call 的 AKShare fallback 残留，并从 `requirements.txt` 移除 `akshare` 依赖，避免继续引用错误备用源。
- `cached_yf_download` 新增 Twelve Data 优先路径：当前只覆盖 `QQQ/HYG/QQEW/XLY/XLP` 的日线 OHLCV，兼容 `.env` 中 `TWELVE_DATA_API_KEY` 与 `twelve_data_api_key`；不把 VIX/VXN、期货、复权序列误接到 Twelve Data。
- `cached_yf_download` 在联网前先读取 12 小时内的持久缓存，降低同日重复运行对 Yahoo 的请求压力；失败时仍保留 7 天 stale cache 兜底。
- `cached_yf_download` 不再把 empty DataFrame 写入同次运行的内存缓存，避免一次限流后把空结果固定住。
- `tools_L1.py` 中 XLY/XLP、HG/GC、CL、GC/CL 的裸 `yf.download` 收口到 `cached_yf_download`；`chart_generator.py` 和 `data_cache.py` 的直接下载入口也收口到共享入口。

验证结果：

- `python3 -m pytest -q tests/test_yfinance_cache_resilience.py`：8 passed。新增覆盖 Twelve Data 优先路径、短时持久缓存优先路径和 empty frame 不写入内存缓存。

剩余边界：

- Twelve Data basic 当前限制为 8 credits/min、800/day，因此只作为关键 ETF 日线优先源，不扩大到成分股全量。
- `^VIX/^VXN` 仍无 Twelve Data / AkShare 免费稳定替代，暂保留 yfinance 与缓存退避。
- yfinance `.Ticker` 基本面和期权链仍无法用 Twelve Data 直接替代，后续需要单独评估 Finnhub / Twelve Fundamentals / 付费源。

### yfinance 限流退避修复（cached_yf_download empty df 路径）

分支：`claude/20260517-yfinance-rate-limit-resilience`

根因（systematic-debugging Phase 1-2 调查结论）：

- 5/13、5/15、5/16、5/17 连续四次 run 都在启动 8 秒内首请求即 `YFRateLimitError`，但相同代码在 Yahoo 冷却后能正常拉数据（5/17 12:55 复现单 ticker 与 5 ticker burst 均成功）；问题不是项目 burst 模式，而是 Yahoo 对该 IP 的周期性限流策略。
- 放大因素：`cached_yf_download` 在 yfinance 1.3+ 返回 empty df 时直接放弃（**不进入重试**，因为 yfinance 内部 catch 了 `YFRateLimitError`），仅依赖外层 `_fetch_yf_history` 的 2 秒固定间隔重试。2 秒间隔正好落在 Yahoo cooldown 窗口内，反复撞墙。

最小修复内容：

- **`cached_yf_download` empty df 路径合并到 exception 退避路径**：empty df 视同 silent rate-limit，与 exception 共用同一退避循环；优先返回 stale frame cache，否则进入分级退避重试。
- **退避周期从 (2s, 6s) 调到 (10s, 60s)**：让 Yahoo 限流窗口有机会自然恢复。原值在 5/17 真实日志中复现无效，所有 retry 全部 429。
- **`_fetch_yf_history` 不再对 empty df 重复外层 3 次重试**：`cached_yf_download` 已经完成 10s/60s 内部退避，外层继续 2 秒循环只会在无全局缓存时把长退避重复跑 3 轮。
- 调整范围仍收敛在 yfinance 共享入口，不动 `tools_L1.py`、`chart_generator.py`、`data_cache.py` 等绕过 cached_yf_download 的直调点。

验证结果：

- 新增 `test_cached_yf_download_retries_with_long_backoff_when_empty_and_no_stale` 失败测试（empty df + no stale 必须按 10s/60s 退避重试），修复前 red、修复后 green。
- 新增 `test_fetch_yf_history_does_not_repeat_inner_yfinance_backoff`，防止 `_fetch_yf_history` 把内层长退避重复跑 3 轮。
- `python3 -m pytest -q tests/test_yfinance_cache_resilience.py`：5 passed（含 2 个原有 stale-fallback 行为兼容性测试）。
- `python3 -m pytest -q`：270 passed（修复前 268，本次新增 2）。

剩余风险与未完成：

- `tools_L1.py:787/788/897/898/1077/1174/1175`、`chart_generator.py:1836`、`data_cache.py:187`、`tools_L4.py:1808` 仍是裸 `yf.download/yf.Ticker` 直调，不享受这次修复。本次按最小修复原则不动它们；如果 5/18 以后 run 还是首请求即 429 且数据缺失，需要继续把这些入口收口到 `cached_yf_download`。
- yfinance 抛 429 时是 silent return empty，没有专门的"识别为 rate-limit"通道。这次把所有 empty 视同 rate-limit 处理；如果未来出现"ticker 真实不存在"等正常 empty 情况，会被多 retry 一次（成本：单次 70s 退避）。
- Yahoo 若对此 IP 长期严限（>1 小时），本次修复也无法救场，仍需考虑替代源（FRED 部分指标可替代；VIX/VXN/HYG 暂无稳定免费源）。

### 20260517 run 数据完整性审计修复

完成内容：

- **控制台完整运行不再误用旧数据 JSON**：`完整 vNext` 默认重新采集；只有选择“已有数据分析”时才追加 `--data-json`。控制台会解析最新 data JSON 的数据日期和修改时间，并在已有数据分析模式提示“以 JSON 为准，不会重新采集”。
- **人工数据 UI 去掉误导性置信度下拉**：改为真实的“使用人工数据”开关，和 collector/packet builder 的 `active + meaningful value` 逻辑一致。仅有来源、日期或 confidence 元数据不会触发人工覆盖。
- **补齐关键人工估值入口**：控制台表单、回填、保存和校验补齐 Forward PE、Earnings Yield、Forward Earnings Yield、FCF Yield、PCF、Forward PE 分位和 FCF Yield 分位，减少只能手写高级 JSON 的缺口。
- **yfinance 帧缓存增加时效边界**：持久化 pickle frame cache 默认 7 天 TTL；过期缓存不再作为限流 fallback 使用。`cached_yf_download()` 增加短退避重试；L1 的 yfinance 序列读取改走统一缓存路径。
- **ADX 增加内部公式 fallback**：当 QQQ OHLCV 可用但 `ta` / `pandas_ta` 不可用时，L5 仍能用内部 Wilder smoothing 公式产出 ADX、+DI 和 -DI，避免把库缺失误报成趋势强度缺失。
- **Workbench 缓存回退提示增强**：当 QQQ 价格来自旧 run fallback 时，顶部 warning 显示 fallback run、缓存最新日期和当前 run 数据日期，避免误读为本次实时采集。
- **净流动性早期 TGA 异常修复**：对 2007-05-02 前 WTREGEN/TGA 明显异常的大值做窄规则修正，并记录 warning，避免 2003-2008 的历史口径异常污染 `NET_LIQUIDITY` 图表和历史统计。

验证结果：

- `python3 -m pytest -q tests/test_ta_l5_and_pdr_sources.py tests/test_research_console.py tests/test_yfinance_cache_resilience.py tests/test_manual_data_template.py tests/test_collector_manual_valuation_checks.py tests/test_tools_calculation.py tests/test_interactive_chart_workbench.py`：67 passed，4 warnings。
- `python3 -m pytest -q`：268 passed，4 warnings。

剩余边界：

- ADX 仍取决于 QQQ OHLCV 是否能从 live 或未过期缓存拿到；本轮修复提高公式层韧性，但没有新增第三方 OHLCV 主源。
- DeepSeek L3 首次 JSON 解析失败已有重试机制，本轮未改变 LLM 输出治理。
- Workbench 10Y 默认源码和测试已确认生效；用户若仍看到 5Y，大概率是旧 HTML 或浏览器缓存。

### AGENTS 执行准则内化

完成内容：

- 将 `karpathy-guidelines` 的核心纪律内化到 `AGENTS.md`：先暴露假设和取舍，再做最小必要修改，保持外科手术式改动，并以可验证成功标准闭环。
- 收紧 `AGENTS.md` 推荐工作顺序：先确认成功标准和不可破坏原则，再按 L1-L5、Bridge、Thesis/Governance、数据层、UI 等改动范围选择验证方式。

验证结果：

- 文档检查：确认没有引入外部 skill frontmatter 或整段照搬内容，规则以仓库级 agent 行为准则形式存在。

### L4 估值权威、新闻连接器、10 年 workbench 与 yfinance 韧性演进

提交：`b4d1551 Evolve valuation news and workbench resilience`

完成内容：

- **L4 外部估值源新增 DanjuanFunds/蛋卷基金**：接入 `https://danjuanfunds.com/djapi/index_eva/detail/NDX`，使用浏览器 UA 与 Referer 读取 NDX PE/PB/PE percentile/PB percentile/ROE/PEG/eva_type/date/begin_at/updated_at。蛋卷进入 `ThirdPartyChecks`，作为第三方估值校验源，不替代 Manual/Wind，也不覆盖可信 Trendonify。
- **估值发言权重新排序**：L4 prompt 和 packet builder 明确估值分位权威顺序为 Manual/Wind > trusted Trendonify > DanjuanFunds/蛋卷基金 > WorldPERatio std-dev context；yfinance 成分股 PE/PB/Forward PE 降级为 component-model proxy / sanity check，不再作为估值 regime 主锚。
- **yfinance 韧性增强**：`cached_yf_download()` 增加持久化缓存和失败时 stale cache fallback；`get_yf_ticker_info_with_retry()` 为成分股 `.info` 增加 24h 缓存 fallback；QQQ 图表数据改走统一缓存下载路径。目标是减少限流导致的空图、空 L5 或 L4 成分股模型失败。
- **Workbench 历史窗口改为 10 年起步**：`DEFAULT_CHART_LOOKBACK_DAYS` 从 1825 调到 3650；workbench 默认 `updateRange(3650)`，按钮改为 10Y / 15Y / ALL。5 年不再是默认研究窗口。
- **新闻事件-数据连接器落地**：新增 `src/news_event_data_linker.py`，在 `--enable-news` 且写出 `chart_time_series.json` 后生成 `news_event_data_links.json`。连接器只输出 temporal association / co-movement observation / needs_bridge_review，不写因果证明，不进入 L1-L5 runtime context，不成为 `evidence_ref`。
- **Native brief 新闻栏升级**：新闻栏从单纯“官方事件底账”扩展为“官方事件底账与市场连接观察”，展示事件日前后 QQQ、VIX/VXN、10Y、real yield、HY OAS、HYG、Damodaran ERP 等可用序列的轻量观察，并明确这些观察不是因果证明。
- **旧版 HTML 日常入口软删除**：控制台隐藏旧版 HTML/charts 勾选入口，默认只生成 vNext artifacts、native brief 和 workbench；兼容旧报告仅保留给开发命令显式启用。
- **控制台 stale service 修复**：`open_research_console.py` 增加控制台版本标记 `console_logs_entry_v3`，能识别旧的 visual regression / legacy HTML 页面并清理 8765 上所有旧监听进程后重启服务，避免浏览器继续看到旧控制台。

验证结果：

- `python3 -m pytest -q`：263 passed，4 warnings。
- `python3 -m py_compile src/tools_L4.py src/agent_analysis/packet_builder.py src/news_event_data_linker.py src/main.py src/agent_analysis/vnext_reporter.py src/tools_common.py src/chart_adapter_v6.py src/interactive_chart_workbench.py src/research_console.py src/open_research_console.py`：通过。
- 真实蛋卷接口验证：NDX PE `36.51`，PE 分位 `87.0`，PB `10.44`，PB 分位 `99.68`，ROE `0.2859`，PEG `1.8119`，`eva_type=high`，数据日 `2026-05-15`，样本起点 `2016-01-26`。
- 用 `output/analysis/vnext/20260515_113650` 生成 `news_event_data_links.json`，共 25 条事件连接；重新生成 `output/reports/vnext_brief_20260515_113650_newslinks.html`，可检索“官方事件底账与市场连接观察”“附近市场序列观察”“不是因果证明，也不是 evidence_ref”。
- `http://127.0.0.1:8765/` 已确认返回 `console_logs_entry_v3` 控制台，显示“查看日志 / 最新日志”，旧版 HTML 勾选入口消失。

剩余观察：

- yfinance 在估值 regime 中已降权，但 forward earnings quality、EPS revision、利润率/增长代理仍依赖 yfinance；下一步需要专门审计字段来源、公式、覆盖率和 stale cache 标注。
- 新闻连接器目前只作为 sidecar 和 native brief 展示，不进入 L1-L5，也不替代 Bridge；后续可评估是否把压缩后的 `news_event_data_links` 作为 Bridge 后段的只读背景索引，但仍必须禁止其成为数值证据。

## 2026-05-16

### Claude 20260513 审计分支复核、补强与 main 合并准备

完成内容：

- 深入复核 `PROJECT_AUDIT_20260513.md` 与 `claude/20260513-indicator-timestamps` 相对 `main` 的改动，确认主线修复方向合理：治理阶段 `generated_at` 强制由代码覆盖、L4 长序列进入 prompt 前摘要化、反编造约束提升到 system message、DataIntegrity 扩展、workbench 数据时效性警告、指标时间戳与 U7-U10 简化修复均符合 vNext 当前架构目标。
- 补强 objective firewall：`object_clear` 不再只看 `raw_data` 是否存在 L1-L5 key，而是至少 3 层必须包含可用指标 payload；空层容器不再被误判为投资对象清晰。
- 补强 Kimi HTTP fallback：system message 现在会实际调用 `_load_system_constraints()`，并兼容 `get_extra_headers("kimi")` 返回 `None` 的情况，避免 fallback 路径绕过反编造约束。
- 新增/更新回归测试：覆盖空层容器不能通过 `object_clear`，以及 Kimi HTTP 调用必须携带 system constraints。

验证结果：

- `.venv/bin/python -m pytest -q tests/test_vnext_llm_engine.py tests/test_objective_firewall.py`：15 passed，4 warnings。
- `.venv/bin/python -m pytest -q`：253 passed，22 warnings。

## 2026-05-12

### L4 外部估值源稳定收口：Damodaran、WorldPERatio、Trendonify sidecar

完成内容：

- **研究控制台入口微调**：控制台主流程选择不再把“视觉回归”作为用户入口，改为“查看日志”；产物区从 visual regression summary 改成 `output/logs/control_service` 最新日志/状态文件。视觉回归脚本仍保留给开发验 UI，但不占用日常复跑排障入口。
- **Damodaran 根因确认并收口**：官网 `ERPbymonth.xlsx` 可下载，真实抓取约 46KB；不稳定主要来自坏缓存、manual 覆盖和 run 是否 live。当前 `get_damodaran_us_implied_erp("2026-05-11")` 优先使用 `monthly_excel`，`source_file=ERPbymonth.xlsx`，最新 `data_date=2026-05-01`，`monthly_series` 为 120 条。
- **WorldPERatio parser 修复**：适配当前页面的 Last 1Y/5Y/10Y/20Y 表格，结构化 `average_pe`、`std_dev`、`range_low/range_high`、`deviation_vs_mean_sigma` 和 `valuation_label`。真实页面验证：2026-05-11 当前 PE 为 32.66；不把标准差区间或估值标签冒充 historical percentile。
- **Trendonify 稳定路径明确**：普通 requests 仍不作为稳定主链路；`bb-browser` sidecar 是显式、用户信任后才合并的路径。`browser_sidecar.py` 修复 `parse_status` 判断，增强 Forward PE 文本解析，并在刷新遇到 Cloudflare/空页面时按 `page_type` 保留旧的可用 trusted page，避免刷新污染旧 sidecar。
- **L4 合并逻辑增强**：`get_ndx_valuation_third_party_checks()` 会在 direct requests 后合并 `user_trusted=true` 的 Trendonify sidecar，并保留 `browser_sidecar` 采集时间、信任标记和失败刷新保留元数据。
- **manual/Wind 覆盖边界修复**：当 `get_ndx_pe_and_earnings_yield` 使用 manual/Wind 主值时，collector 仍会轻量拉取 live third-party checks，写入 `value.ThirdPartyChecks` 和 `data_quality.source_disagreement`；manual 主值不被替换，第三方源只作为审计交叉校验。
- **控制台刷新容错**：`console_run_all.py` 在用户信任 Trendonify sidecar 时会先尝试刷新；刷新失败或单页解析失败不会中断整条流水线，会保留已有可用 sidecar 或写入 failed payload 供审计。

验证结果：

- `python3 -m pytest tests/test_l4_external_valuation_sources.py tests/test_browser_sidecar.py -q`：10 passed。
- `python3 -m pytest tests/test_l4_external_valuation_sources.py tests/test_l4_data_authority.py tests/test_browser_sidecar.py tests/test_vnext_reporter.py tests/test_console_run_all.py -q`：31 passed。
- `python3 -m pytest -q`：154 passed，6 warnings。
- 真实 WorldPERatio 页面验证：`value=32.66`，`data_date=11 May 2026`，1Y/5Y/10Y/20Y 窗口均解析成功，`historical_percentile=None`。
- 真实 Damodaran 验证：`retrieval_method=monthly_excel`，`source_file=ERPbymonth.xlsx`，`data_date=2026-05-01`，`monthly_series=120`。
- `bb-browser` sidecar 刷新验证：Forward PE 刷新为 23.8 / 2026-05-11 / 10Y percentile 58.3；Trailing PE 当前刷新遇到空/验证页，保留旧 trusted 值 38.07 / 2026-05-08，并写入 `preserved_after_failed_refresh_at_utc`。
- `python3 src/main.py --collect-only --models deepseek-v4-flash,deepseek-v4-pro --skip-report --disable-charts`：采集成功，`output/data/data_collected_v9_live.json` 中 `get_ndx_pe_and_earnings_yield.value.ThirdPartyChecks` 包含 `worldperatio_pe`、`trendonify_pe`、`trendonify_forward_pe`；Damodaran 月度序列为 120 条。
- collect-only packet/brief：`output/analysis/vnext/20260512_215333_collect_only/analysis_packet.json`，`output/reports/vnext_brief_20260512_2153.html`。brief 中可检索 `WorldPERatio`、`Trendonify`、`browser_sidecar`、`ThirdPartyChecks`、`ERPbymonth.xlsx`，且不再出现“未接入 Trendonify 或 WorldPERatio”。

真实运行观察：

- `python3 src/main.py --models deepseek-v4-flash,deepseek-v4-pro --skip-report --disable-charts` 完成数据采集并写出 `output/analysis/vnext/20260512_211406/analysis_packet.json`，但 LLM 分析阶段因 DeepSeek flash/pro 多次 `APIConnectionError` / timeout，最终 `l1 received empty response` 失败；这属于模型连接稳定性问题，不是本轮三个数据源解析/合并失败。
- 该失败 run 不能作为完整 vNext 叙事验收；数据源验收以 collect-only JSON、collect-only packet/brief、单源真实抓取和测试为准。

## 2026-05-11

### 20260510_225944 报告自查：微图误导、空底稿文案与 Crosshair 读数修复

完成内容：

- 复核用户批注和 `20260510_225942_913.log`：确认本次 run 没有实际执行 live Damodaran / WorldPERatio / Trendonify 采集，报告中“已并入 L4 微图”的说法会误导读者。
- 移除 brief 中 demo/模板说明式文案和“市场图谱”空图谱入口，改为官方事件底账占位；无新闻底账时明确说明事件不进入 L1-L5 数值证据。
- L4 估值微图在没有 WorldPERatio/Trendonify 时改为中性标题，并显示 PE_TTM、PB 等主来源字段；人工/Wind ERP 不再冒充 Damodaran 官网月度序列。
- 底稿数据质量区不再渲染裸 `[]` / `{}`；source value 摘要不再输出整块 dict。
- 修复 L5 静态微图的横向溢出：MACD 与 VWAP 偏离条限制为半轴宽度，避免条形穿出卡片。
- 修复价格技术 workbench crosshair：默认展示最新交易日读数，鼠标移动时兼容不同时间格式，并补齐 MA、Bollinger、Donchian、VWAP、MACD/Signal 等具体指标。

验证结果：

- `python3 -m pytest tests/test_interactive_chart_workbench.py tests/test_vnext_reporter.py tests/test_research_console.py -q`：13 passed，4 warnings。
- 生成修复版 brief：`output/reports/vnext_brief_20260510_225944_reviewfix.html`。
- 生成修复版 workbench：`output/reports/vnext_workbench_20260510_225944_reviewfix.html`。
- `python3 src/report_visual_regression.py ...`：desktop/mobile brief 与 workbench 截图均 OK，布局扫描 passed。
- 本地浏览器打开新 workbench：标题正常，控制台无 error/warning，读数区包含最新日期、MA20、VWAP20、Donchian 等具体指标。

### Bridge 输入污染复核：L3 core_facts 字符串拆分修复

完成内容：

- 复核 [BRIDGE_INPUT_AUDIT_L3_COREFACTS_CONTAMINATION.md](BRIDGE_INPUT_AUDIT_L3_COREFACTS_CONTAMINATION.md)：确认 `_normalize_payload()` 在 `core_facts` 为字符串时会逐字符迭代，导致单字符 `CoreFact` 噪声污染 Bridge 输入；问题属于上游归一化缺陷，不是 Bridge 设计问题。
- `src/agent_analysis/orchestrator.py` 在遍历前先规整 `core_facts`：字符串、bytes、单个 dict 或其他非 list 值都会包装为单元素列表，避免未来任何 L1-L5 输出同类格式偏差时被拆碎。
- L1-L5 prompt 的 Output Discipline 补充 `core_facts` 对象数组约束，作为模型输出层辅助防线；代码兜底仍是主防线。
- 新增两个 orchestrator 回归测试，覆盖 `core_facts` 纯文本字符串和单个对象 dict 两种异常形态。

验证结果：

- 修复前手动复现：`core_facts="QQQ/QQEW比率触及历史极值"` 被拆成 16 条单字符 fact。
- 修复后手动复核：同一字符串归一化为 1 条 fact。
- `python3 -m pytest tests/test_vnext_orchestrator.py::test_layer_payload_normalization_wraps_core_facts_string tests/test_vnext_orchestrator.py::test_layer_payload_normalization_wraps_single_core_fact_dict tests/test_vnext_orchestrator.py::test_layer_payload_normalization_backfills_indicator_evidence_refs -q`：3 passed。
- `python3 -m pytest tests/test_vnext_orchestrator.py -q`：9 passed。
- `python3 -m pytest -q`：142 passed，6 warnings。

## 2026-05-10

### AI 复核补丁：Workbench 时间轴收口与 Damodaran 缓存防污染

分支：`claude/20260510-debug-run-issues`

完成内容：

- **Workbench 时间轴收口**：复核发现 Claude 报告称已移除子图/module 独立 `fitContent()`，但代码中仍残留。补丁后初始化和模块重绘都不再各自 `fitContent()`，统一由主价格图时间轴决定全局范围。
- **模块图重绘清理**：`renderModuleChart()` 在归一化/双轴切换时会创建新图表，但旧图表仍留在同步列表中。新增 `moduleCharts` 与 `unregisterChart()`，重绘前清除旧实例，避免幽灵图表继续参与时间轴和 crosshair 同步。
- **Damodaran 缓存防污染**：复核发现本地 1-2KB 的 stub `.xlsx` 会被 24h 缓存信任，导致新 run 仍可能只得到极短 `monthly_series`。新增缓存 payload 校验，官方月度/当月 xlsx 过小或非 ZIP-xlsx 时自动丢弃并重新抓取。
- **测试补强**：新增 Workbench JS 断言、Damodaran 坏缓存剔除测试、manual ERP 描述字段不触发 override 测试。

验证结果：

- 直接绕过坏缓存后重新抓取 Damodaran 官方文件：`ERPbymonth.xlsx` 约 46KB、`ERPMay26.xlsx` 约 1.46MB，解析出 120 条月度序列，最新 `data_date=2026-05-01`。

### 20260510_193710 Run Debug: Damodaran ERP 缓存、图表对齐、Crosshair、Reviser Prompt 修复

分支：`claude/20260510-debug-run-issues`

完成内容：

- **Damodaran ERP 月度序列为空（P0）**：根因是 `collector.py` 中手动覆盖逻辑会跳过 live `get_damodaran_us_implied_erp()`，导致 `monthly_series` 不生成。修复：Damodaran 总是调用 live 函数，手动值作为补充合并而非替换。
- **Damodaran 文件本地缓存**：`tools_L4.py` 新增 `_fetch_bytes_cached()`，在 `data_cache/damodaran/` 下缓存 `ERPbymonth.xlsx` 和当月 calculator xlsx，TTL 24 小时。
- **`has_meaningful_manual_override()` 误判**：`manual_data.py` 将 `"scope"`、`"not_ndx_valuation_warning"` 加入忽略键列表，避免纯描述性字符串触发手动覆盖。
- **OBV 子图横轴未对齐（P1）**：根因是初始化时每个子图独立 `fitContent()` 导致 "last writer wins"。修复：初始化时 `syncLocked = false`，所有图表创建完成后统一设 `syncLocked = true`，由主图 `fitContent()` 单向传播。
- **Crosshair 右侧读数不正确（P1）**：根因是 `priceReadoutHtml` 和 `syncCrosshair` 使用 `findPoint`（精确时间匹配），子图因指标预热期数据点数较少导致匹配失败。修复：全部替换为 `findPointAtOrBefore`。
- **Reviser 校验失败（P2）**：`contracts.py` 中 `environment_assessment` 等字段有 `max_length=300`，但 prompt 未注明字符限制。修复：在两个 `reviser.md` 中添加长度约束和质量检查项。
- **测试更新**：`tests/test_l4_data_authority.py` 中 4 个 monkeypatch 测试补上 `_fetch_bytes_cached` mock。

验证结果：

- `python -m pytest -q`：138 passed，164 warnings。

剩余观察：

- WTREGEN 警告（log 中 million-dollar unit mixing）：待调查。

---

### 市场图谱布局重构：Damodaran ERP 与 WorldPERatio 并入 L4

分支：`claude/20260510-debug-run-issues`（同一分支）

完成内容：

- **`_damodaran_indicator_visual` 增强**：从 atlas 移入 SVG 月度线图（ERP T12M / 10Y Treasury / Expected return 三条路径）、8 项 ERP 透镜指标、data_date/source 脚注。L4 微图现在是 atlas 的超集。
- **`_valuation_indicator_visual` 增强**：从 atlas 移入 WorldPERatio 窗口标签表（1y/5y/10y/20y 均值 PE、标准差、区间、偏离 σ、估值标签）及 SMA50/SMA200 趋势语境。
- **Atlas section 精简**：移除 `_damodaran_erp_chart`、`_worldperatio_window_chart`、`_worldperatio_relative_position` 三个方法（~100 行）。Atlas 保留估值相对位置尺和 L1-L4 利率估值压力图两张图表。Section 描述更新为"跨层压力与估值位置"。
- **测试更新**：`test_vnext_reporter.py` 中 5 个断言更新为新的 L4 微图标题和属性。

验证结果：

- `python -m pytest -q`：138 passed，164 warnings。

---

### Bridge 阶段 JSON 容错升级 — event_refs 兜底与 DeepSeek /beta 校验

分支：`claude/20260510-bridge-event-refs-resilience`（继续在同一分支上做方案 B）

完成内容：

- AI 审阅后补齐两个边界：子级 `typed_conflicts` / `resonance_chains` / `transmission_paths` 内部的 `event_refs` 现在也复用 `_coerce_event_refs_list`，避免 dict 被整段 stringify 后“过 schema 但丢语义”；真实 run 证明 DeepSeek 不允许 `response_format=json_object` 与 `prefix: true` 组合，因此当前 JSON 主链明确不发送 prefix。
- 重新核对 DeepSeek 官方文档（`https://api-docs.deepseek.com/zh-cn/`，2026-05-10 抓取）：当前主力模型为 `deepseek-v4-flash` 与 `deepseek-v4-pro`；`deepseek-chat` 与 `deepseek-reasoner` 将于 2026/07/24 弃用，分别等价于 v4-flash 的非思考 / 思考模式。文档明确 v4 全系列同时支持 Json Output 与 Tool Calls，且思考模式与 Tool Calls / Strict Mode 兼容。
- `src/agent_analysis/llm_engine.py` 新增 `_resolve_deepseek_base_url`：当 `get_base_url("deepseek")` 是默认生产值 `https://api.deepseek.com` 时升级为 `https://api.deepseek.com/beta`，为（未来的）strict function calling 做准备；显式 /beta 保持；自定义自托管 endpoint 不被重写。
- `src/agent_analysis/llm_engine.py` 保留 `response_format={"type":"json_object"}` 作为当前 JSON 主链保护，并增加测试确保不与 prefix completion 组合。Claude 原报告中的 prefix 方案经真实 run 证伪后已撤回。
- 新增 5 个 llm_engine 测试：`tests/test_vnext_llm_engine.py` 的 `test_deepseek_client_promotes_default_base_url_to_beta` / `test_deepseek_client_does_not_double_promote_explicit_beta` / `test_deepseek_client_respects_self_hosted_base_url` / `test_call_ai_uses_json_output_without_prefix_for_deepseek` / `test_call_ai_does_not_send_beta_prefix_to_custom_deepseek_endpoint`。更新已有的 `tests/test_deepseek_runtime_config.py::test_deepseek_v4_calls_use_official_reasoning_parameters`，确认 thinking 参数与 JSON Output 保留，且不发送 prefix。
- 新增 AI 审阅报告 [docs/2026-05-10_BRIDGE_JSON_RESILIENCE_AI_AUDIT.md](docs/2026-05-10_BRIDGE_JSON_RESILIENCE_AI_AUDIT.md)：完整记录 bug → 系统性根因 → DeepSeek 官方约束工具链事实校核 → 本次实施（Fix 1+2+3 + 方案 B-1+B-2）→ 验证 → 仍存在的 8 类不稳定面 → 阶段 C/D/E 下一步建议 → 关键代码位置速查 → 审阅检查表，供其他 AI 审阅。

验证结果：

- 修改前：4 个新增 llm_engine 测试中 1 个按预期 fail（`/beta` 升级）；AI 审阅后追加并调整测试，覆盖 JSON Output 不发送 prefix 与自定义 endpoint 边界。
- 修改后：`python -m pytest -q tests/test_vnext_llm_engine.py tests/test_deepseek_runtime_config.py tests/test_bridge_v2.py tests/test_vnext_orchestrator.py` 全绿。
- `python -m pytest -q`：138 passed，164 warnings。
- 真实 run 验证：`.venv/bin/python src/main.py --data-json output/data/data_collected_v9_live.json --models deepseek-v4-flash,deepseek-v4-pro --skip-report --disable-charts` 成功生成 `output/analysis/vnext/20260510_191820/`；`llm_stage_diagnostics.json` 显示 bridge `status=ok`、`attempts=1`、`errors=[]`，最终 stance 为 `中性偏谨慎`，approval 为 `approved_with_reservations`。

剩余观察：

- 阶段 C（强约束）仍是根治路径：把 BridgeMemo 改造为 strict function calling tool。文档明确思考模式与 strict 兼容，但需要 contracts 层移除 `extra="allow"`、把 Optional 字段改为带默认值的 required、用 $ref/$def 复用枚举。建议先在 bridge stage 单点 PoC。
- 阶段 E 基础设施清理：`.gitignore` 增加 `ai_response_debug_*.txt`（当前仓库根有两个未跟踪的 debug 文件）；思考模式下 `temperature: 0.2` 实际无效，建议条件化；`max_node_retries` 可考虑提到 3（缓存命中价格 1/10，重试成本接近零）。
- 子级 normalize "过校验、坏语义" 地雷（U1）已处理；prompt 减负（U2）仍未处理，等真实 run 数据决定优先级。

### Bridge 阶段 event_refs 类型容错与重试反馈强化

分支：`claude/20260510-bridge-event-refs-resilience`

完成内容：

- 排查 `output/logs/control_service/20260510_132806_164.log`：bridge 阶段两次 attempt 不同错因导致 `RuntimeError: bridge failed after 2 attempts`。Attempt 1 是 `resonance_chains[0].falsifiers` 数组未闭合，`_light_repair_json` 修不了结构性破损；attempt 2 是 LLM 把顶层 `event_refs` 输出成 dict（模仿了 `AnalysisPacket.event_refs: Dict[str, Dict]` 输入形态），与 `BridgeMemo.event_refs: List[str]` 撞型。`llm_stage_diagnostics.json` 印证了两次错误属于不同 kind（parse_error → schema_validation_error）。
- `src/agent_analysis/orchestrator.py::_normalize_payload` 在 bridge 分支末尾新增 `_coerce_event_refs_list` 兜底：dict→keys、list[dict]→提取 `event_id`/`id`/`event_ref`/`ref`、scalar→`[str(value)]`、None→`[]`。子级别 typed_conflicts/resonance_chains/transmission_paths 的 event_refs 已有归一化，本次只补顶层缺口，不动既有路径。
- `src/agent_analysis/orchestrator.py::_run_stage` 的 parse_error 反馈从 "did not return a parseable JSON object" 升级为「错误描述 + 原始响应字符数 + 末尾 400 字符片段」，给下一轮 LLM 提供可定位的语法错误线索；`raw_excerpt` 仍只在 diagnostics 里保留 500 字符，不外泄。
- `src/agent_analysis/orchestrator.py::_compose_bridge_prompt` 增加 "顶层 BridgeMemo.event_refs 字段类型（强约束）" 段落，显式说明 List[str] 类型 + 字符串 ID 数组示例，并指出输入 dict 形态不得复制到输出，杜绝 LLM 模仿输入格式。
- 新增 3 个失败先行测试：`tests/test_bridge_v2.py` 的 `test_bridge_normalize_coerces_top_level_event_refs_to_list` 与 `test_bridge_prompt_anchors_event_refs_as_string_list`，`tests/test_vnext_orchestrator.py` 的 `test_run_stage_parse_error_feedback_includes_response_excerpt`。

验证结果：

- 修改前：3 个新测试均按预期 fail（normalize 留下 dict、prompt 缺锚点、last_error 不含响应末尾）。
- 修改后：`python -m pytest -q tests/test_bridge_v2.py tests/test_vnext_orchestrator.py::test_run_stage_records_parse_retry_diagnostics tests/test_vnext_orchestrator.py::test_run_stage_parse_error_feedback_includes_response_excerpt` 全绿。
- `python -m pytest -q`：132 passed，163 warnings。

剩余观察：

- 本次仅修补顶层 event_refs；L1-L5 隔离、bridge 高严重度冲突保留、legacy_adapter 边界均未触动。
- 子级别 normalize 仍保留 `not isinstance(value, list) → [str(value)]` 行为：若 LLM 把 typed_conflicts/resonance_chains/transmission_paths 内部 event_refs 写成 dict，会 stringify 成单元素列表，能过 schema 但语义被毁。这是潜在的"过校验、坏语义"地雷，未在本轮处理；后续若发现下游 evidence 追溯失败，再单独修。
- 重试反馈强化对所有 stage 生效（不只是 bridge），有助于其它 stage 在长 JSON 偶发语法错误时收敛；监控下次 run 的 `llm_stage_diagnostics.json`。
- bridge prompt 长度此次基本不变（仅追加约 350 中文字符的强约束段落）；本次未做 prompt 减负（备选项 #4），避免一次性引入过多变量。

### 修复控制台运行环境、产物跳转、命名和实时数据链路

完成内容：

- 排查最新 control service run `20260510_001423_727`：LLM 主链完成，核心异常不是 DeepSeek，而是控制台任务用系统 `python3` 启动，实际落到 macOS Python 3.9，导致 `pandas_ta` 缺失；`.venv` 中 `pandas_ta` 与 `pandas_datareader` 均可用。
- `src/control_service.py` 现在把白名单里的 `python/python3` 命令绑定为服务自身的 `sys.executable`，确保从 `start.command` / `open_research_console.command` 启动后，后续任务都跑在同一个虚拟环境。
- `control_service` 新增 `/artifact?path=...` 和 `/latest-product`：控制台里的“打开最新报告 / workbench”和底部最新产物不再依赖浏览器从 `http://127.0.0.1` 跳 `file://`，而是由本地服务安全读取仓库内产物。
- 控制台任务完成后会轮询状态；完整运行成功会自动打开最新 native brief，workbench-only 成功会自动打开 workbench。
- 简化新产物命名：native brief 改为 `vnext_brief_<数据采集分钟>_<运行分钟>.html`，workbench 改为 `vnext_workbench_<数据采集分钟>_<运行分钟>.html`；旧命名仍可被控制台识别为历史产物。
- `src/open_research_console.py` 的版本探针增加新 artifact 跳转标记；旧 control service 若仍占用端口，会被判定为过期并重启。
- 修复 M2 YoY 只有水平没有分位：新增 `calculate_yoy_series()`，M2 的相对位置现在基于同比序列本身计算 1Y/10Y 分位。
- 修复净流动性：WTREGEN 缓存存在百万美元/十亿美元混合口径，现逐点转换到十亿美元；`calculate_long_term_stats()` 强制数值化，避免 pandas/numpy object dtype 异常。
- 修复默认实时模式误用历史成分股：L2 breadth、L4 component model、`get_equity_risk_premium` 不再把当前日期隐式传给 `get_ndx100_components(end_date=...)`；只有显式历史日期才使用历史成分。
- `requirements.txt` 将 pandas 约束为 `<3.0.0`，因为 pandas-datareader 0.10.0 对 pandas 3 需要兼容补丁；当前代码仍保留窄兼容，但新装环境优先避免踩坑。

验证结果：

- `.venv/bin/python` 环境探针：`pandas_ta=True`，`pandas_datareader=True`。
- `python src/main.py --collect-only` 真实采集：生成 `output/data/data_collected_v9_live.json`，39 个指标全部有值，0 缺失，0 错误。
- 单点验证：`get_qqq_technical_indicators` 和 `get_adx_qqq` 成功，ADX 使用 `ta` 公式层；`get_net_liquidity_momentum` 成功输出 5830.96 十亿美元并带 5Y/10Y 分位。
- `python src/agent_analysis/vnext_reporter.py --run-dir output/analysis/vnext/20260510_001425 --template brief`：生成 `output/reports/vnext_brief_20260509_2215_20260510_0014.html`。
- `python src/interactive_chart_workbench.py --run-dir output/analysis/vnext/20260510_001425 --modules price_technical,volatility_credit,rates_valuation,breadth_concentration,liquidity`：生成 `output/reports/vnext_workbench_20260509_2215_20260510_0014.html`。
- `./start.command`：打开 `http://127.0.0.1:8765`；`/artifact` 可直接服务新 brief HTML；当前只保留一个 8765 control service。
- 定向测试：`python -m pytest tests/test_l3_breadth_data.py tests/test_l4_forward_earnings_quality.py tests/test_l1_m2_relativity.py tests/test_control_service.py tests/test_research_console.py tests/test_vnext_reporter.py -q`：28 passed。

结论：

- VPN/yfinance/DeepSeek 分开排查是正确方法，但这次“数据大量缺失”的主因不是 DeepSeek，而是控制台任务跑错 Python 环境，加上少数数据函数把实时模式误切成历史成分路径。
- OpenBB 可以继续作为后续数据覆盖研究对象，但不应在本轮作为第一修复手段；当前主链自身已恢复到 39/39 指标可用。

## 2026-05-09

### 修复控制台分段验证与 yfinance 缺数下的 workbench 崩溃

完成内容：

- 排查 `output/logs/control_service/20260509_220522_366.log`：本轮 DeepSeek 从 L1 到 Final 全部成功，实际失败点是 workbench 生成阶段；yfinance 限流导致 L5 技术指标值为 `None`，`src/interactive_chart_workbench.py` 直接 `.get()` 触发崩溃。
- `src/interactive_chart_workbench.py` 增加 L5 原始指标空值保护：`get_multi_scale_ma_position` 和 `get_qqq_technical_indicators` 的 value 为 `None` 时降级为空字典，workbench 继续生成，缺失指标在 payload 中保持 `null`。
- `src/main.py` 新增 `--collect-only`，用于只采集市场数据 JSON，不进入 DeepSeek / vNext LLM 链路；便于 VPN 开关下把 yfinance 与 DeepSeek 分开排查。
- `src/control_service.py` 白名单允许 `src/main.py --collect-only`。
- `src/research_console.py` 自动填入最近的 `output/data/data_collected_v9_*.json`；“已有数据分析”改为只运行 `src/main.py --data-json ... --skip-report --disable-charts`，不再串联 native brief 和 workbench；“只采集数据”现在生成真正的 `--collect-only` 命令。
- 修正控制台日期语义：普通“分析日期”不再自动触发 `--date`；只有显式勾选“历史日期 / 回测”时才把日期传给 `src/main.py` / `src/console_run_all.py`，避免把最新周末日期误当历史时点分析。
- 保留上一轮 L2 韧性修复：`VXN/VIX` 上游缺数不再抛异常；Layer 自检覆盖字段可从实际 `indicator_analyses` 派生校正；LLM JSON 解析器可修复模型偶发的数组错括号和尾逗号。

验证结果：

- `python3 -m pytest tests/test_control_service.py tests/test_research_console.py tests/test_main_collect_only.py tests/test_interactive_chart_workbench.py tests/test_runtime_resilience.py -q`：15 passed。
- `python3 src/research_console.py`：重新生成 `output/reports/vnext_research_console.html`。
- `rg -n "historicalDateMode|--date|modeCommand" output/reports/vnext_research_console.html`：确认控制台只在历史回测开关勾选时拼接 `--date`。
- `python3 src/interactive_chart_workbench.py --run-dir output/analysis/vnext/20260509 --modules price_technical,volatility_credit,rates_valuation,breadth_concentration,liquidity`：在 QQQ 仍被 yfinance 限流的情况下成功生成 `output/reports/vnext_interactive_charts_20260509.html`。
- `python3 -m pytest -q`：124 passed，6 warnings。

结论：

- VPN / 网络路径对 yfinance 与 DeepSeek 产生相反影响是合理的现实假设；当前系统已支持先在适合 yfinance 的网络下“只采集数据”，再切到适合 DeepSeek 的网络下用“已有数据分析”消费同一份 JSON。
- 本轮 DeepSeek 没有在 L2 JSON 输出处失败；上一轮 L2 格式问题是大上下文、强约束 JSON 与模型偶发语法失误叠加，不能简单归因于单个示范或模型“完全不行”。系统已增加窄口径解析修复和合约自校正。

### 产品化研究控制台启动与完整运行闭环

完成内容：

- 新增 `open_research_console.command` 和 `src/open_research_console.py`：双击或运行 Python 启动器即可生成控制台、启动本地 control service，并打开 `http://127.0.0.1:8765`。
- `src/control_service.py` 的根地址 `/` 和 `/console` 现在直接返回研究控制台，不再让用户看到 `{"ok": false, "message": "Not found"}`；新增 `/manual-data` GET/POST，用于读取和保存 `config/manual_data.local.json`。
- 新增 `src/console_run_all.py`：控制台“运行完整报告”会保存人工数据，执行 vNext 主链，生成 native brief，并生成 interactive workbench；运行摘要写入 run 目录和 `output/logs/control_service/latest_console_run.json`。
- 控制台把“人工数据”和“数据源选择”合并为“人工数据与数据源校准”：上次保存的人工 PE/PB/PS/ERP 与分位会自动回填，官方事件底账和 bb-browser 信任选择与人工校准放在同一区域。
- 控制台运行命令现在携带分析日期、模型、数据 JSON、workbench modules 和 legacy 开关；默认主路径从单步 `src/main.py` 改为完整产品流 `src/console_run_all.py`。
- README 增加明确开启方式：双击 `open_research_console.command`，或命令行运行 `python src/open_research_console.py`，或手动启动 service 后访问 `http://127.0.0.1:8765`。

验证结果：

- `python3 -m py_compile src/control_service.py src/research_console.py src/console_run_all.py src/open_research_console.py`：通过。
- `python3 -m pytest -q tests/test_research_console.py tests/test_control_service.py`：6 passed。
- 临时启动 `python3 src/control_service.py --port 8766`：`GET /` 返回控制台 HTML，`GET /manual-data` 返回当前人工数据 JSON；验证后已关闭临时服务。
- `python3 src/report_visual_regression.py --brief-html output/reports/vnext_research_ui_brief_20260505_20260506_075229.html --workbench-html output/reports/vnext_interactive_charts_20260506.html --console-html output/reports/vnext_research_console.html --output-dir output/reports/visual_regression/20260509_console_product_flow`：通过。
- `python3 -m pytest -q`：118 passed，6 warnings。

### 完成 NEXT_STEPS P2：用 Impeccable shape/craft 打磨控制台与 brief

完成内容：

- 按 `$impeccable` 流程读取 `PRODUCT.md` / `DESIGN.md`，确认本轮是 product register。shape 结论：控制台是“运行仪器”，brief 是“可审计长文”；采用浅色纸面、克制 OKLCH、清晰规则线和少量状态色，不走深色终端、SaaS 卡片堆叠或纯铁锈单色系。
- 对 Claude 排版报告做取舍：采纳“编辑室/仪器面板分工”“sticky 阅读导航”“引用视觉语法”“避免类别反射”；不采纳“控制台改成阶段向导隐藏复杂度”和“风险/良好都用同一铁锈明度表达”，因为 vNext 需要一屏复跑审阅和清晰状态语义。
- 控制台新增流程锚点：设定对象、校准输入、生成命令、审计边界；运行区和人工输入区权重提升，面板不再被网格强行拉成等高，移动端强制单列，避免 span grid 造成窄屏裁切。
- 控制台视觉系统改为 OKLCH tokens，去掉旧版/sidecar 警示的彩色侧边条，改用完整边界和轻色底；补齐按钮 hover/focus、输入断行、长路径/命令预览的窄屏保护。
- brief 默认 `slate_v2` 改成更适合连续阅读的形态：桌面 brief 使用左侧 sticky 章节导航、右侧正文；风险、冲突和边界卡从彩色侧边条改为完整边界和语义底色；证据引用 chip 加入小型视觉语法，长文和长 ref 增加断行保护。
- `src/report_visual_regression.py` 支持可选 `--console-html`，把研究控制台纳入同一轮桌面/移动截图回归；同时修正静态扫描对 `@media (min-width: ...)` 的误报，并处理 macOS Chrome headless 窄屏截图会裁掉 500px 最小布局视口的问题。
- 重新生成：
  - `output/reports/vnext_research_console.html`
  - `output/reports/vnext_research_ui_brief_20260505_20260506_075229.html`
  - `output/reports/vnext_interactive_charts_20260506.html`
  - `output/reports/visual_regression/20260509_p2_console_brief_full_run/`

验证结果：

- `node /Users/aidianchi/.agents/skills/impeccable/scripts/load-context.mjs`：`hasProduct=true`，`hasDesign=true`，`register=product`。
- `python3 -m pytest -q tests/test_research_console.py tests/test_vnext_reporter.py tests/test_report_visual_regression.py tests/test_control_service.py`：15 passed。
- `python3 -m pytest -q`：117 passed，6 warnings。
- `python3 src/report_visual_regression.py --brief-html output/reports/vnext_research_ui_brief_20260505_20260506_075229.html --workbench-html output/reports/vnext_interactive_charts_20260506.html --console-html output/reports/vnext_research_console.html --output-dir output/reports/visual_regression/20260509_p2_console_brief_full_run`：passed，brief / workbench / console 的 desktop 和 mobile captures 均 ok，layout checks 均 ok。

剩余观察：

- 本轮完成控制台和 brief 的 shape/craft/polish，不处理 workbench 的进一步视觉重构；workbench 只作为视觉回归配套目标继续验证。
- 2026-05-09 数据验证 run 缺少最终裁决 artifacts，因此 brief craft 使用更完整的 `output/analysis/vnext/20260506_075229` 作为长文排版验证对象；2026-05-09 run 仍保留为 HY 真实数据验证对象。

### 清理历史输出样本，保留输出体验优化基线

完成内容：

- 清理 `output/reports/` 中 2026-04-23、2026-05-02、2026-05-06 生成的历史 brief / redesign / workbench 样本，只保留当前输出体验继续优化需要的入口：
  - `output/reports/vnext_research_console.html`
  - `output/reports/vnext_research_ui_brief_20260502.html`
  - `output/reports/vnext_interactive_charts_20260509_hy_quality.html`
- 删除旧视觉回归截图目录 `output/reports/visual_regression/`，避免后续 polish 时把历史截图误当当前设计基线。
- 清理旧 vNext run 目录，只保留完整可复用 run `output/analysis/vnext/20260506_075229` 和 P1 数据验证 run `output/analysis/vnext/20260509_134942`。
- 清理旧数据快照，只保留最新 `output/data/data_collected_v9_live.json`；保留 `output/browser_sidecar/trendonify_ndx_valuation.json` 作为当前 bb-browser sidecar smoke 结果。
- 删除仓库内 `.DS_Store`，并重新生成 `output/reports/vnext_research_console.html`，让控制台链接列表反映清理后的干净输出目录。

验证结果：

- `find . -name '.DS_Store' -print`：无输出。
- `output/` 体积从约 39M 降到约 17M。

### 完成所有 P1：运行控制、事件底账治理、event_ref、HY 真实验证与 bb-browser sidecar

完成内容：

- `control_service` 增加 `/status/<job_id>` 与 `/cancel/<job_id>`，任务状态持久化到 `output/logs/control_service/*.json`，状态响应包含日志路径、日志尾部、退出码和失败原因；`/run` 现在要求显式 `confirmed=true`，继续保留命令白名单。
- 研究控制台新增运行状态刷新、取消任务、日志/失败原因展示；运行前会弹出确认。控制台还新增 `bb-browser` 估值 sidecar 区：可跳转 Trendonify PE / Forward PE 页面，可通过 control service 单独拿数据，可勾选“信任 bb-browser 来源”并把来源标记写入人工模板。
- 新增 `src/browser_sidecar.py`：只采集明确允许的 Trendonify NDX Trailing PE 与 Forward PE 页面，输出 `schema_version=browser_sidecar_v1`、source tier、采集时间、URL、解析字段、页面摘要、失败模式和 `user_trusted` 标记；主 L4 requests 链仍不自动调用浏览器。
- `browser_sidecar` 真实 smoke：输出 `output/browser_sidecar/trendonify_ndx_valuation.json`，两页均可用。Trailing PE 38.07，1Y/5Y/10Y/20Y 分位均为 100；Forward PE 23.73，1Y 分位 33.3、5Y 分位 40、10Y 分位 57.5、20Y 分位 71.2。
- 新闻事件底账升级为 `news_event_ledger_v2`：新增 `source_tier`、`layers`、`dedupe_id`，保留 `event_type`、`published_at`、`symbols` 和 `source_errors`，并增加 45 天时间窗口与去重治理；新闻仍不注入 L1-L5 prompt。
- `AnalysisPacket` 新增独立 `event_refs`；Bridge payload 可选接收事件索引；`SynthesisPacket` 新增 `event_index`；Bridge / Thesis / governance 合约新增 `event_refs` 字段和约束。`event_ref` 与 `evidence_ref` 分离，只能写成解释、触发或观察背景，不能写成证明。
- 真实数据 run 验证 `HY CCC & Lower - BB OAS`：`output/analysis/vnext/20260509_134942/analysis_packet.json` 中 `get_hy_quality_spread_bp` 成功，最新数据日 2026-05-07，值 7.44，CCC OAS 9.15、BB OAS 1.71，`data_quality` 包含官方源、公式、覆盖 786 个共同观测和 fallback chain。
- 同一 run 的 `chart_time_series.json` 已包含 `HY_QUALITY_SPREAD`，786 行，覆盖 2023-05-09 至 2026-05-07；生成波动信用 workbench：`output/reports/vnext_interactive_charts_20260509_hy_quality.html`，HTML 内嵌该序列。

验证结果：

- `python3 -m pytest -q tests/test_control_service.py tests/test_news_event_ledger.py tests/test_browser_sidecar.py tests/test_vnext_packet_builder.py tests/test_bridge_v2.py tests/test_research_console.py`：20 passed。
- `python3 -m py_compile src/control_service.py src/news_event_ledger.py src/browser_sidecar.py src/research_console.py src/main.py src/agent_analysis/contracts.py src/agent_analysis/packet_builder.py src/agent_analysis/orchestrator.py`：通过。
- `python3 src/research_console.py`：重新生成 `output/reports/vnext_research_console.html`。
- `python3 src/browser_sidecar.py --source trendonify_valuation --output output/browser_sidecar/trendonify_ndx_valuation.json --trusted --wait-seconds 10 --timeout 60`：2 pages，0 errors。
- `python3 src/interactive_chart_workbench.py --run-dir output/analysis/vnext/20260509_134942 --modules volatility_credit --output output/reports/vnext_interactive_charts_20260509_hy_quality.html`：通过。
- `python3 -m pytest -q`：117 passed，6 warnings。

剩余观察：

- 2026-05-09 真实 run 的数据采集、事件底账、analysis packet 与 chart time-series 已完成；模型阶段因 DeepSeek 长响应期间多次 `APIConnectionError` 被手动中止，未生成完整 `run_summary.json`。本轮 HY P1 验证依赖已生成的真实数据 artifacts，而不是完整模型报告。
- `bb-browser` sidecar 仍是人工确认/sidecar 路径；即使勾选“信任”，也只是给人工模板打来源标记，不会让 L4 主链静默绕过 Cloudflare。

### 增强人工 ERP 分位与 Trendonify / bb-browser 估值百分位研究

完成内容：

- 研究控制台的人工 / Wind 数据区新增 ERP 5Y 分位和 ERP 10Y 分位，写入 `get_damodaran_us_implied_erp.value.manual_erp_percentile_5y/10y`。
- 调整控制台人工 ERP 写入边界：ERP 输入只作为 Manual/Wind ERP reference，不再同步写入 `get_equity_risk_premium` 的简式收益差距，避免把外部 ERP 和 NDX yield gap 混在一起。
- `DEFAULT_MANUAL_DATA` 补齐 PE / Forward PE / PB / PS 的 10Y 分位字段，以及 ERP reference 的 5Y / 10Y 分位字段。
- 增强 Trendonify parser：除 `Valuation Percentile Rank` 的 10Y 主分位外，额外解析 Historical P/E Comparison 表中的 1Y / 5Y / 10Y / 20Y / since-inception median、percentile 和 valuation label。
- Trendonify 可行性结论：普通 `requests` 浏览器头、Jina Reader 文本代理都仍返回 Cloudflare 验证页；`bb-browser daemon start` 后可用真实浏览器打开页面并通过 `document.body.innerText` 读取公开文本，适合作为隔离 sidecar / 人工调研辅助，不适合作为默认主数据链。
- `bb-browser` 真实页面 smoke：2026-05-08 Trendonify Trailing PE 页面显示 PE 38.07、10Y percentile 100；Forward PE 页面显示 Forward PE 23.73、5Y percentile 40、10Y percentile 57.5、20Y percentile 71.2。
- 自动 PE/PB/PS 百分位来源初筛：
  - Trendonify：当前最有价值，覆盖 NDX PE / Forward PE 及多窗口分位，但有 Cloudflare，建议 sidecar。
  - WorldPERatio：可自动读取 NDX PE、均值和标准差区间，但不是 percentile。
  - Koyfin：有历史 percentile rank 概念，偏登录/付费，适合人工或未来授权 connector，不宜伪装成公开自动源。
  - FinanceCharts：能看到 NDX 成分股 PE/PB/PS rank，偏横截面 rank，不是指数自身历史 PE/PB/PS percentile。

验证结果：

- `python3 -m pytest -q tests/test_l4_external_valuation_sources.py tests/test_research_console.py tests/test_manual_data_template.py`：12 passed。
- `python3 -m py_compile src/tools_L4.py src/research_console.py src/manual_data.py`：通过。
- `python3 src/research_console.py`：重新生成 `output/reports/vnext_research_console.html`。
- `python3 -m pytest -q`：114 passed，6 warnings。

剩余观察：

- 下一步若接入 `bb-browser`，应做成显式 sidecar：输出 URL、采集时间、页面文本摘要、解析字段、失败模式和人工确认标记；不得让 L4 主链在无提示情况下启动浏览器或绕过 Cloudflare。
- PB / PS 的可靠指数历史百分位仍未找到公开稳定自动源；当前更现实路径是 licensed/manual 或未来从成分股历史基本面构建自有指数级时间序列。

### 完成 NEXT_STEPS P0：L3 官方权重锚与 L4 forward earnings 质量

完成内容：

- 新增 L3 指标 `get_qqq_top10_concentration`：读取 Invesco QQQ 官方持仓 JSON，输出 Top10 / Top5 / Top3 / M7 权重、Top10 相对等权基准的超额权重、官方 `effective_date`、持仓来源和数据质量。
- 同一指标补充 QQQ 相对 QQEW 的 1M/3M/6M 表现差，用来明确区分“多数成分参与弱”和“头部权重股推动强”；集中度历史变化只作为价格回推 proxy，明确不伪装成官方历史权重。
- 新增 L4 指标 `get_ndx_forward_earnings_quality`：基于 yfinance 成分股模型输出 forward earnings yield、Forward EPS 增长代理、盈利/收入增长、利润率质量；M7 额外读取 next-year EPS trend，给出 30 日分析师修正方向。
- `get_ndx_pe_and_earnings_yield` 同步暴露 ForwardEarningsProxyUSD、ForwardEPSGrowthProxyPct、WeightedProfitMarginPct / GrossMargin / OperatingMargin 等字段，让既有估值指标也能带上未来盈利和 margin 质量。
- 更新 `TOOLS_REGISTRY`、DataCollector、packet builder、manual data 模板、IndicatorCanon、L3/L4 prompts 和 native brief 指标视觉，保证 v2 artifacts 与 brief 能直接消费新数据，不经过 legacy adapter。
- 检查已安装的 `bb-browser`：CLI 可用，支持 `fetch`、页面快照和登录态浏览器操作；本轮 Invesco 官方 JSON 端点可直接访问，因此没有把 `bb-browser` 接入主数据链。它仍适合后续 P2 隔离调研/sidecar 试验，不能绕过数据治理。

验证结果：

- `python3 -m pytest -q tests/test_l3_top10_concentration.py tests/test_l4_forward_earnings_quality.py tests/test_vnext_packet_builder.py tests/test_l4_external_valuation_sources.py`：17 passed。
- `python3 -m py_compile src/tools_L3.py src/tools_L4.py src/tools.py src/core/collector.py src/agent_analysis/packet_builder.py src/agent_analysis/vnext_reporter.py src/agent_analysis/deep_research_canon.py src/manual_data.py`：通过。
- `python3 -m pytest -q`：114 passed。
- 工具注册检查：`get_qqq_top10_concentration` 与 `get_ndx_forward_earnings_quality` 均已进入 `TOOLS_REGISTRY`。
- 真实 L3 smoke：Invesco QQQ 官方接口返回 `effective_date=2026-05-07`，Top10 权重 46.91%，M7 权重 40.16%，QQQ 近 1M 相对 QQEW 超额 4.68pct。

剩余观察：

- L4 全成分股 forward quality 仍依赖 yfinance 最新基本面和 M7 EPS trend，属于 component_model / proxy，不是官方 NDX aggregate EPS revision；若未来有 Wind/manual 高信任源，应优先覆盖。
- `bb-browser` 可以作为反爬或登录态页面的人工调研辅助，但不得直接进入主指标链。

### 完成本地运行服务、官方事件底账、L2 信用分层利差与 Impeccable 上下文

完成内容：

- 新增本地 `vNext control service` MVP：`src/control_service.py` 提供 `/health` 和 `/run`，只接受项目白名单 Python 命令，运行日志写入 `output/logs/control_service/`，避免静态 HTML 任意执行本地命令。
- 修复研究控制台“运行”按钮脚本初始化问题：`console-data` 改为可被 `JSON.parse` 正确读取的安全嵌入格式，避免按钮监听没有挂上。
- 控制台新增官方事件底账开关：勾选后命令追加 `--enable-news`，由主流水线写入独立 `news_event_ledger.json`。
- 新增 `src/news_event_ledger.py`：MVP 采集 Federal Reserve / BLS / BEA 官方 RSS 与 M7 SEC submissions，输出独立 sidecar artifact；不写入 L1-L5 runtime context。
- 移除旧 collector 内部新闻整合路径：新闻不再混入 `data_json["indicators"]`，保持数值指标与事件背景分离。
- 新增 L2 指标 `get_hy_quality_spread_bp`：计算 FRED / ICE BofA `BAMLH0A3HYC - BAMLH0A1HYBB`，即 CCC & Lower 高收益 OAS 减 BB 高收益 OAS。
- 将该指标纳入 `TOOLS_REGISTRY`、DataCollector L2、packet builder L2、IndicatorCanon、L2 prompt 和 workbench 波动信用模块。
- 补齐 `$impeccable` 所需 `PRODUCT.md` 与 `DESIGN.md`，并通过 context loader 确认 product/design 上下文可读取。register 明确为 `product`。
- 重新生成 `output/reports/vnext_research_console.html`。

验证结果：

- `python3 -m py_compile src/control_service.py src/news_event_ledger.py src/main.py src/tools_L2.py src/chart_time_series_artifacts.py src/research_console.py`：通过。
- `python3 -m pytest -q tests/test_control_service.py tests/test_news_event_ledger.py tests/test_l2_credit_quality.py tests/test_main_cli.py tests/test_research_console.py tests/test_chart_time_series_artifacts.py tests/test_deep_research_canon.py`：24 passed。
- `python3 -m pytest -q`：110 passed。
- `python3 src/news_event_ledger.py --output /tmp/news_event_ledger_test.json --no-sec --max-events-per-source 1`：生成 1 条官方 RSS 事件。
- `node /Users/aidianchi/.agents/skills/impeccable/scripts/load-context.mjs`：`hasProduct=true`，`hasDesign=true`。

剩余观察：

- `control_service` 现在是本机 MVP，还没有浏览器侧二次确认弹窗、任务取消、运行状态轮询和历史任务 UI。
- 新闻事件底账当前只做权威来源访问与结构化，不做摘要、情绪、LLM 解读，也不进入 Bridge/Thesis。
- L4 prompt 约 18 万字符在 1M 上下文模型中可接受，但仍有重复和成本问题；后续应做 prompt 专用摘要，而不是把完整月度序列重复塞入 manifest 与 raw payload。
- OpenBB 本轮按用户判断暂缓，不纳入主链路。

## 2026-05-07

### 修复 workbench 对齐、模块切换读数和 QQQ 数据窗口

完成内容：

- 修复 L5 workbench 主图与 Volume、OBV、MACD、RSI/ATR、MFI/CMF 副图纵向轴线不齐：所有 Lightweight chart 统一右侧价格刻度最小宽度，绘图区右边界现在保持一致。
- 修复模块切换后的上下文错位：切换到波动信用、利率估值、广度集中度、流动性时，顶部摘要改为对应 layer 的精简分析，不再停留在 L5。
- 修复模块 crosshair 读数：L5 继续显示 OHLC、Volume、OBV、MACD、RSI、ATR、MFI、CMF；非 L5 模块显示当前模块序列读数，并对低频序列显示最近可用值。
- QQQ 图表数据默认窗口从约 420 天扩展到 1825 天；最新 `chart_time_series.json` 中 QQQ 为 1254 行，覆盖 2021-05-10 至 2026-05-06。页面仍默认显示 1Y，ALL 可查看完整 5 年窗口。
- 控制台新增“运行”按钮：按钮调用本机 `127.0.0.1:8765` vNext control service；服务未启动时明确提示没有执行命令，保留安全边界。
- 重新生成 `output/reports/vnext_interactive_charts_20260506_controls.html`、`output/reports/vnext_research_console.html` 和 `output/reports/visual_regression/20260507_workbench_fix/`。

验证结果：

- `python3 -m pytest -q tests/test_interactive_chart_workbench.py tests/test_research_console.py tests/test_chart_time_series_artifacts.py`：6 passed。
- `python3 src/report_visual_regression.py --brief-html output/reports/vnext_research_ui_brief_20260505_20260506_075229.html --workbench-html output/reports/vnext_interactive_charts_20260506_controls.html --output-dir output/reports/visual_regression/20260507_workbench_fix`：passed。
- 额外生成 tall workbench 截图确认纵轴和副图对齐：`output/reports/visual_regression/20260507_workbench_fix/workbench_tall.png`。
- 额外生成控制台截图确认运行按钮位置：`output/reports/visual_regression/20260507_workbench_fix/console_desktop.png`。

剩余观察：

- 控制台已有运行入口，但本地 control service 本体尚未实现；下一步若继续做一键运行，应先做 allowlist、显式确认、运行日志和失败恢复。
- workbench 现在解决了对齐和读数语义；后续更专业的方向是增加 navigator、pane 高度调整和指标参数编辑。

---

## 2026-05-06

### 修复 workbench 与研究控制台页面批注

完成内容：

- 修复 workbench 副图布局：Volume、OBV、MACD、RSI/ATR、MFI/CMF 从并列小图改为全宽纵向 pane，避免不同副图横轴宽度和起止日期观感不一致。
- 修复 workbench 默认时间窗口：所有 pane 初始化后统一到同一 1Y 时间窗口；ALL/3M/6M/1Y 按真实日期范围同步，而不是让各副图按自身数据 fitContent。
- 修复副图对齐：去掉副图容器内边距，把标题浮在图内左上角，主图和副图的绘图区宽度更接近。
- 修正研究控制台“运行模式”语言：从 full/data only/report only 等旧式流程词，改为完整 vNext、只采集数据、已有数据分析、只生成 brief、只生成 workbench、视觉回归。
- 重排人工估值字段：PE、PB、PS 分别成组，每组把当前值、5Y 分位和 10Y 分位放在一起；JSON 预览同步写入对应字段。
- 明确 legacy HTML 边界：控制台改为“不生成旧版 HTML / 不生成旧版 charts”，并标注旧版 HTML 是过渡期兼容产物，默认入口应是 native brief 和 workbench。

验证结果：

- `python3 -m pytest -q tests/test_interactive_chart_workbench.py tests/test_research_console.py`：4 passed。
- 重新生成 `output/reports/vnext_interactive_charts_20260506_controls.html` 和 `output/reports/vnext_research_console.html`。
- `python3 src/report_visual_regression.py --brief-html output/reports/vnext_research_ui_brief_20260505_20260506_075229.html --workbench-html output/reports/vnext_interactive_charts_20260506_controls.html --output-dir output/reports/visual_regression/20260506_review_fix`：passed。
- 额外生成 tall workbench 截图确认副图全宽纵向对齐：`output/reports/visual_regression/20260506_review_fix/workbench_tall.png`。

剩余观察：

- workbench 的时间轴同步已经按日期范围统一，但更接近 TradingView 的独立 pane 管理还可以继续加入拖拽排序、pane 高度调整和指标参数编辑。

---

### 完成 workbench 操作化与研究控制台总控重构

完成内容：

- 先将既有成果快进合入 `main` 并推送到 GitHub，提交为 `e1a6f5b Advance vNext workbench and console planning`。
- 按用户对 workbench 的两个批注，重构 L5 价格技术工作台交互：默认只显示 Candles、MA20、MA200，避免主图全指标过载。
- 新增 L5 指标显隐和图例点击切换：Candles、MA5/20/60/200、Bollinger、Donchian、VWAP、Volume overlay 可独立启停。
- 新增指标预设：简洁价格、趋势均线、波动区间、量价确认、全部指标；预设写入 localStorage，不改变 run artifact。
- 新增时间轴锁定/解锁和统一时间轴：锁定时主图、副图和模块图共享 visible logical range；解锁后可局部检查，再一键统一。
- 新增跨 pane readout：主图或副图移动 crosshair 时，右侧统一展示 OHLC、Volume、OBV、MACD hist、RSI、ATR、MFI、CMF。
- 新增副图启停：Volume、OBV、MACD、RSI/ATR、MFI/CMF 均可折叠，移动端保持单列。
- 非 L5 模块新增序列图例显隐、归一化和双轴控制，覆盖波动信用、利率估值、广度集中度、流动性模块。
- 重构研究控制台为六区总控：运行对象与日期、人工/Wind 数据、模型与运行模式、数据源/功能开关、输出与工作台、运行日志/健康/安全。
- 人工数据输入从纯 JSON 文本升级为结构化表单，支持 PE/PB/PS/ERP/percentile/date/source/confidence；保留高级 JSON 预览和下载。
- 控制台新增 full、data only、analysis only、draft only、report only、quick report 运行模式，新增 flash 优先、pro only、自定义顺序模型策略。
- 控制台纳入新闻源预留、Trendonify 暂缓、legacy charts opt-in、workbench 模块、L5 默认预设、最新 brief/workbench/run/visual regression 入口。
- 控制台明确一键运行安全方案：后续若做本地 control service，必须有 allowlist、显式确认、日志、失败恢复和项目路径白名单。

验证结果：

- `python3 -m pytest -q tests/test_interactive_chart_workbench.py tests/test_research_console.py`：4 passed。
- 重新生成 workbench：`output/reports/vnext_interactive_charts_20260506_controls.html`。
- 重新生成控制台：`output/reports/vnext_research_console.html`。
- `python3 src/report_visual_regression.py --brief-html output/reports/vnext_research_ui_brief_20260505_20260506_075229.html --workbench-html output/reports/vnext_interactive_charts_20260506_controls.html --output-dir output/reports/visual_regression/20260506_controls`：passed，desktop/mobile 截图和 layout checks 均 ok。
- 额外生成控制台 desktop/mobile 截图：`output/reports/visual_regression/20260506_controls/console_desktop.png`、`output/reports/visual_regression/20260506_controls/console_mobile.png`。

剩余观察：

- data only 运行模式在控制台已有入口，但当前 `src/main.py` 还没有真正拆出独立 collector-only 命令；控制台已明确标注需要后续本地 control service 或 CLI 拆分。
- 非 L5 模块已经可控，但更专业的宏观图还可以继续引入 navigator、收益差距专用面板和单位标注增强。

---

### 完成阶段收尾知识同步

完成内容：

- 使用 `neat-freak` 盘点 Codex 全局配置、项目根 Markdown、`docs/` 历史文档和当前输出体验文档；确认 `~/.codex/AGENTS.md` 为空，当前没有独立记忆索引需要同步。
- 更新 `README.md`，补充研究控制台、交互 workbench、视觉回归命令和当前输出入口。
- 更新 `AGENTS.md`，补充 `chart_time_series_artifacts.py`、`interactive_chart_workbench.py`、`research_console.py`、`report_visual_regression.py` 等关键路径，并明确 UI 改动要区分 brief、图表层和 workbench。
- 更新 `ARCHITECTURE.md`，记录 2026-05-06 多模块 workbench、控制台边界和下一轮交互重点。
- 更新 `DATA_COVERAGE_REVIEW.md`，把数据覆盖复盘推进到 2026-05-06 最新 run，明确 Damodaran 月度 ERP、WorldPERatio、L5 量价质量和 Trendonify 缺口。
- 更新 `PLAIN_LANGUAGE_OUTPUT_EXPERIENCE_REVIEW.md`，补充多模块 workbench、控制台总控方向、视觉回归布局检查和下一轮观察点。
- 清理当前受审文档中的相对时间词，改为绝对日期或“当日/目标日期”。

剩余观察：

- `docs/` 下多份 2026-04-24/2026-04-25 文档是历史研究记录，本轮只修正相对时间词，不把后续实现倒灌进历史报告。
- 本轮是文档同步，没有修改运行代码。

---

### 完成 workbench 与研究控制台下一轮设计复盘

完成内容：

- 复核用户对 `vnext_interactive_charts_20260506_modules.html` 的两个批注：主图指标全开导致视觉过载；主图和副图需要更强的共享时间轴、联动读数和“一键统一”能力。
- 查阅一手图表资料后形成取舍：当前继续以 Lightweight Charts 为主，因为它足以支持 visible range 控制和 pane 同步；TradingView Advanced Charts 虽然指标/模板能力强，但官方限制不适合作为当前默认依赖；Highcharts Stock 和 ECharts 分别作为 navigator/range selector、多轴宏观图的后续参照。
- 审阅旧 `/Users/aidianchi/Desktop/launcher.py`，提取有价值功能线索：人工 L4 输入、历史日期、运行模式、模型顺序、API 配置、新闻开关、图表叠加模式和本地任务启动。
- 更新 `NEXT_STEPS.md`，新增两组下一步：
  - workbench：指标显隐、预设模板、时间轴锁定/解锁、统一时间轴、联动 crosshair、副图折叠、非 L5 模块 legend/normalize/dual-axis、交互回归测试。
  - 研究控制台：信息架构重构、结构化人工数据输入、运行模式、模型策略、功能开关、报告/artifact 入口、一键运行安全方案、视觉重设计。

剩余观察：

- 这次只做规划与审视，未修改 workbench/控制台运行代码。
- 下一轮若进入实现，建议先做 workbench 的指标显隐和时间轴锁定，因为它直接回应用户批注，也能最快验证“看盘台”方向是否成立。

---

### 完成 NEXT_STEPS 2-7：多模块 workbench、同源时序数据和回归增强

完成内容：

- 按用户指示暂缓 Trendonify 可用性问题，只推进 NEXT_STEPS 2-7。
- 固化 workbench 双层分类原则：底稿/审计继续按 L1-L5；交互 workbench 按价格技术、波动信用、利率估值、广度集中度、流动性组织，同时保留每条序列的 Layer、function_id、provider 和 frequency。
- 扩展 `chart_time_series.json`：除 QQQ OHLCV 外，新增 VIX、VXN、VXN/VIX、HY/IG OAS、HYG、10Y、10Y real、10Y breakeven、Fed funds、Damodaran ERP monthly、QQQ/QQEW、net liquidity、WALCL、TGA、RRP、M2 YoY。
- 升级 L5 价格技术工作台：主图支持 K 线、MA5/20/60/200、Bollinger、Donchian、VWAP；副图支持 Volume、OBV、MACD、RSI、ATR、MFI、CMF；区间按钮同步主图和副图。
- 重构 workbench 为研究模块选择器：页面提供模块 tabs；控制台新增模块勾选，并生成 `--modules` workbench 命令。
- 增加 DeepSeek/LLM 阶段诊断：`llm_stage_diagnostics.json` 会记录 stage、attempts、parse/schema/contract errors、raw_excerpt、prompt_chars，后续可直接复盘 JSON parse retry 和 coverage retry。
- 增强视觉回归：`visual_regression_summary.json` 新增 `layout_checks`，检测明显固定宽度超视口和移动端内联 nowrap 风险。
- 生成最新多模块 workbench：`output/reports/vnext_interactive_charts_20260506_modules.html`；重新生成控制台：`output/reports/vnext_research_console.html`。

验证结果：

- 测试先行：新增失败测试覆盖多面板 artifact、workbench 模块与副图、控制台模块选择、视觉回归布局检查、LLM retry diagnostics。
- `python3 -m pytest tests/test_chart_time_series_artifacts.py tests/test_interactive_chart_workbench.py tests/test_research_console.py tests/test_report_visual_regression.py tests/test_vnext_orchestrator.py::test_run_stage_records_parse_retry_diagnostics -q`：11 passed，4 warnings。
- `python3 -m py_compile src/chart_time_series_artifacts.py src/interactive_chart_workbench.py src/research_console.py src/report_visual_regression.py src/agent_analysis/orchestrator.py src/main.py`：通过。
- 使用最新 run `output/analysis/vnext/20260506_075229` 重新写入 `chart_time_series.json`，确认多模块序列均落盘，Damodaran monthly 为 120 行。
- `python3 src/report_visual_regression.py --brief-html output/reports/vnext_research_ui_brief_20260505_20260506_075229.html --workbench-html output/reports/vnext_interactive_charts_20260506_modules.html --output-dir output/reports/visual_regression/20260506_modules`：passed，desktop/mobile 截图和 layout checks 均 ok。

剩余观察：

- Trendonify 仍按用户要求暂停，不在本轮解决。
- 新 workbench 已能表达 5 个研究模块，但非 L5 模块目前以多线图为主，后续可继续增加双轴、归一化切换、drawdown overlay 和更强的 crosshair 联动。
- L4 token 膨胀已开始被 diagnostics 量化，但真正压缩 L4 prompt/packet 仍是后续工作。

---

### 完成 NEXT_STEPS：最新真实 run、视觉回归、legacy chart 降为显式 opt-in

完成内容：

- 修复 Damodaran 默认日期选择：当目标日期不是月初时，`ERPbymonth.xlsx` 会选择不晚于目标日期的最新月度行；2026-05-06 默认可正确落到 2026-05-01。
- 重新采集实时数据并保存 `output/data/data_collected_20260506_live.json`；确认 Damodaran `ERPbymonth.xlsx` / `ERPMay26.xlsx`、`monthly_series=120` 和 WorldPERatio 结构化相对位置进入 packet。
- 用新采集数据完成真实 DeepSeek smoke：`output/analysis/vnext/20260506_075229`，Final 为“中性偏谨慎”，审批状态 `approved_with_reservations`。
- 生成最新 native brief：`output/reports/vnext_research_ui_brief_20260505_20260506_075229.html`；生成最新交互 workbench：`output/reports/vnext_interactive_charts_20260506.html`。
- 新增 L5 `get_price_volume_quality_qqq` 指标微图，展示 VWAP 偏离、MFI 和 CMF，最新 brief 指标级微图数量从 29/30 提升到 30。
- 新增 `src/report_visual_coverage.py`，输出每层指标级微图覆盖审计；最新覆盖为 L1 7/8、L2 8/9、L3 5/6、L4 3/3、L5 7/9。
- 新增 `src/report_visual_regression.py`，用 Chrome headless 对 brief/workbench 做 desktop/mobile 截图回归；同时修复移动端 verdict card 和长风险文本挤压。
- 调整 native brief 默认文件名：当 `data_date` 重复时追加 run id，避免不同 run 覆盖同名报告。
- legacy Plotly charts 从默认主路径退出：`src/main.py` 默认关闭 legacy charts，只有显式 `--enable-legacy-charts` 才开启旧 HTML 图表。

验证结果：

- `python3 src/main.py --models deepseek-v4-flash,deepseek-v4-pro --data-json output/data/data_collected_20260506_live.json --skip-report`：完成真实 DeepSeek run。
- `python3 src/report_visual_coverage.py --run-dir output/analysis/vnext/20260506_075229 --html output/reports/vnext_research_ui_brief_20260505_20260506_075229.html --output output/reports/visual_regression/20260506_final/visual_coverage_20260506_075229.json`：通过，输出 30 个指标级微图覆盖。
- `python3 src/report_visual_regression.py --brief-html output/reports/vnext_research_ui_brief_20260505_20260506_075229.html --workbench-html output/reports/vnext_interactive_charts_20260506.html --output-dir output/reports/visual_regression/20260506_final`：passed。
- in-app browser 检查：`#evidence-L5-get_price_volume_quality_qqq` 自动展开 L5 并高亮；workbench 显示数据源 `chart_time_series.json · yfinance via chart_adapter_v6`，主图可见。

剩余观察：

- Trendonify 在最新采集里仍不可用，不能宣称自动历史估值分位已完整解决。
- 视觉回归当前能产出桌面/移动截图并验证 PNG 非空，但自动 layout overflow 检测仍可继续加强。
- 两次真实 run 暴露模型输出稳定性问题：旧数据 run 有 L1/L2 JSON parse retry、L5 coverage retry；新数据 run 成功但 L4 输入达到约 59k tokens，应继续压缩。

---

## 2026-05-05

### 推送当前版本，并继续落地指标级可视化后的下一轮观察

完成内容：

- 将当前数据源审计、native brief 图表、指标级微图、研究控制台和 Lightweight workbench 原型提交到 Git，并推送到 GitHub 分支 `claude/20260503-vnext-brief-redesign`。
- 创建草稿 PR：`https://github.com/aidianchi/NDX_VNEXT/pull/1`，方便后续人工或 AI 审查。
- 明确图表三层架构：底稿微图负责指标速读，市场总览图负责跨层压力/共振，Lightweight workbench 负责看盘式交互探索。
- 新增 `chart_time_series.json` artifact 写入路径：vNext run 会保存 QQQ OHLCV、成交量和 MA5/20/60/200；workbench 优先读取同一 run 的 artifact，避免图表与文字来自不同抓取时点。
- 修复 evidence hash 直达：打开 `#evidence-Lx-...` 会自动展开对应 Layer、滚动到指标卡并高亮，证据链接更适合审查和分享。

验证结果：

- 提交前全量测试：`python3 -m pytest -q` 为 89 passed，6 warnings。
- 本轮新增行为先写失败测试，再实现：hash 直达、workbench artifact 优先读取、`chart_time_series.json` 写入均有测试覆盖。
- 定向测试：`python3 -m pytest tests/test_chart_time_series_artifacts.py tests/test_interactive_chart_workbench.py tests/test_vnext_reporter.py::test_vnext_reporter_generates_native_ui -q` 为 4 passed，4 warnings。

---

### 调研并落地交互式看盘图原型：Lightweight Charts Workbench

完成内容：

- 复核当前指标微图边界：它们适合底稿速读，但不适合看盘式探索；需要把“连续阅读报告”和“交互图探索”分成两层。
- 查阅并比较一手资料后，选择 TradingView Lightweight Charts 作为第一版看盘式原型依赖；它比 Plotly 更接近金融主图手感，比 ECharts 更适合 K 线/均线/成交量这类时间序列探索。
- 本地安装 `lightweight-charts@5.2.0`，并把 `node_modules/` 加入 `.gitignore`，避免依赖目录污染版本管理。
- 新增 `src/interactive_chart_workbench.py`，生成独立交互图页面 `output/reports/vnext_interactive_charts_20260502.html`：包含 QQQ K 线、成交量、MA5/20/60/200、区间按钮、crosshair readout 和 L5 摘要。
- 修复 native brief 的 JSON payload 嵌入方式：不再把 `<script type="application/json">` 内的 JSON 转成 HTML entity，避免浏览器端 `JSON.parse` 失败影响证据抽屉和跳转。

验证结果：

- `npm view lightweight-charts version license dist.unpackedSize --json`：确认当前版本 5.2.0，Apache-2.0。
- `npm install --no-save lightweight-charts@5.2.0`：成功安装。
- `python3 -m pytest -q tests/test_vnext_reporter.py tests/test_interactive_chart_workbench.py`：6 passed，4 warnings。
- `python3 -m py_compile src/agent_analysis/vnext_reporter.py src/interactive_chart_workbench.py`：通过。
- `python3 src/interactive_chart_workbench.py --run-dir output/analysis/vnext/20260502_193057 --lookback-days 420`：生成 `output/reports/vnext_interactive_charts_20260502.html`。
- in-app browser 检查：交互图页面无当前页面脚本错误；K 线、均线、成交量和 3M/6M/1Y/ALL 区间按钮可见。

---

### 完成 L1-L5 指标级可视化：底稿旁微图与复杂指标展开图

完成内容：

- 从第一性原理重新审视 L1-L5 的全部指标：优先图表化“相对位置、均线/基准偏离、组成项、广度结构、集中度、估值源分歧、技术区间和资金流确认”，不把没有结构信息的单点文字硬画成图。
- 在 native `brief` 的五层底稿指标卡内新增轻量内联微图，直接消费本次 `analysis_packet.raw_data`，不接回 legacy Plotly chart 管线，也不重新联网拉取另一批数据。
- 覆盖主要图表族：历史分位/5Y/10Y/z-score 位置尺、均线基准对照、净流动性组成项、Fear & Greed 分项、拥挤度组件、广度参与条、M7 基本面热力格、L4 估值源校验、Damodaran 当前 ERP lens、收益差距压力尺、L5 技术 dashboard、MA ladder、MACD、OBV、成交量和 Donchian channel。
- 对复杂指标采用可展开图：例如 Fear & Greed 默认展开，M7 基本面默认折叠，避免五层底稿被大图撑散。
- 旧 run `output/analysis/vnext/20260502_193057` 重新生成后，`output/reports/vnext_research_ui_brief_20260502.html` 包含 29 个指标级可视化。

验证结果：

- 先写失败测试 `test_vnext_reporter_renders_indicator_level_visuals`，确认旧报告没有指标级微图；实现后该测试通过。
- `python3 -m pytest -q tests/test_vnext_reporter.py`：5 passed，4 warnings。
- `python3 -m py_compile src/agent_analysis/vnext_reporter.py`：通过。
- `python3 src/agent_analysis/vnext_reporter.py --run-dir output/analysis/vnext/20260502_193057 --template brief`：重新生成默认 brief 报告。
- in-app browser 检查：报告中存在 29 个 `data-indicator-visual`，L1 底稿指标卡可见分位尺、z-score 和净流动性组成项；复杂指标以 details 呈现。

---

### 完成输出体验 4-5 步：报告图表一等公民和研究控制台第一屏

完成内容：

- 在 native `brief` 报告中新增“市场图谱”章节，直接消费 vNext artifacts 与 `analysis_packet.raw_data`，不回退到 legacy chart 叙事。
- 新增四类报告内原生图表：L4 估值相对位置尺、Damodaran ERP 月度路径、WorldPERatio 窗口标签、L1-L4 利率估值压力图；每张图绑定 evidence refs，可继续打开指标底稿。
- Damodaran 月度解析器保留 `monthly_series`，未来真实 run 可直接画 `ERPbymonth.xlsx` 的 ERP / 10Y / expected return 月度线图；旧 artifact 没有月度序列时会展示单点读数和边界说明。
- 新增 `src/research_console.py`，生成 self-contained 第一屏控制台 `output/reports/vnext_research_console.html`，覆盖人工/Wind 输入、flash/pro 模型选择、数据源健康、运行命令、报告入口和人工模板保存。
- 补充通俗说明：`PLAIN_LANGUAGE_OUTPUT_EXPERIENCE_REVIEW.md`，记录参考 TradingView、Bloomberg、Koyfin 和 FT 图表词汇后的取舍。

验证结果：

- `python3 -m pytest -q tests/test_vnext_reporter.py tests/test_research_console.py tests/test_l4_data_authority.py`：14 passed，4 warnings。
- `python3 -m py_compile src/agent_analysis/vnext_reporter.py src/research_console.py src/tools_L4.py`：通过。
- `python3 src/agent_analysis/vnext_reporter.py --run-dir output/analysis/vnext/20260502_193057 --template brief`：生成 `output/reports/vnext_research_ui_brief_20260502.html`。
- `python3 src/research_console.py`：生成 `output/reports/vnext_research_console.html`。
- Chrome headless 截图检查报告首页和控制台首页可渲染；Python/Node Playwright 均未安装，因此未做 Playwright 自动交互验收。

---

### 完成 L4 数据源复盘 1-3 步：Damodaran 月度 ERP、WorldPERatio 相对位置和 L4 边界

完成内容：

- 重构 Damodaran 官方 ERP 获取优先级：优先读取 `ERPbymonth.xlsx`，并尝试读取当月 `ERP<Month><YY>.xlsx`；`histimpl.xls` 降级为年度历史 fallback。
- 新增无 `openpyxl` 也可工作的轻量 `.xlsx` 解析兜底，并处理 Damodaran 工作簿的 `Start of month` 日期列和 1904 日期系统。
- Damodaran 输出扩展为多口径字段：`erp_t12m_adjusted_payout`、`erp_t12m_cash_yield`、`erp_avg_cf_yield_10y`、`erp_net_cash_yield`、`erp_normalized_earnings_payout`、`us_10y_treasury_rate`、`default_spread`、`adjusted_riskfree_rate`、`expected_return`、`source_file`、`data_date`。
- 扩展 WorldPERatio parser：保留 PE、日期和显式 percentile 规则，同时结构化 rolling average、std dev、range、deviation vs mean、valuation label、SMA50/200 margin；这些字段进入 `relative_position`，明确不是历史分位。
- 更新 L4 packet builder、prompt 和 few-shot：模型可以使用 WorldPERatio 的 `std-dev / z-score relative context` 描述相对位置，但不能写成 percentile；Damodaran 明确区分 monthly current ERP 与 annual history fallback。

验证结果：

- 真实官网 smoke：`get_damodaran_us_implied_erp("2026-05-01")` 成功读取 `ERPbymonth.xlsx` 的 2026-05-01 月度 ERP，并合并 `ERPMay26.xlsx` 的 default spread / expected return。
- 真实 smoke 关键值：T12m adjusted payout 4.24%、T12m cash yield 4.36%、10 年平均 CF yield 6.36%、net cash yield 4.15%、normalized 3.73%、10Y Treasury 4.40%、default spread 0.26%、adjusted riskfree 4.14%、expected return 8.55%。
- `python3 -m pytest tests/test_l4_data_authority.py tests/test_l4_external_valuation_sources.py tests/test_vnext_packet_builder.py tests/test_prompt_guardrails.py -q`：29 passed，4 warnings。
- `python3 -m pytest -q`：86 passed，6 warnings。

---

## 2026-05-04

### 完成 P1：L5 公式层和轻量数据 fallback 收口审阅

完成内容：

- 复核 L5 当前实现，确认主路径仍是稳定的 yfinance 日频 OHLCV，`ta` 只作为公式层标准化引擎；内部 fallback 继续保留，不改变既有数据源优先级。
- 复核 pandas-datareader 轻量 fallback，维持只用于 FRED 公开 CSV/reader 备用路径；不把 Fama-French、Nasdaq symbols 或 Stooq 接入主流程，避免扩大不稳定面。
- 从第一性原理审阅 VWAP / MFI / CMF：三者有必要保留为 L5 量价质量验证，因为它们分别回答“价格相对成交量加权成本”“带成交量的动能拥挤”“收盘位置与成交量形成的积累/派发压力”。但它们只提高或降低趋势质量置信度，不能单独给买卖结论，也不能证明估值合理。
- 补齐 `get_price_volume_quality_qqq` 的 vNext 原生消费路径：进入 `LAYER_FUNCTIONS["L5"]`，加入 deep research canon、L5 prompt 指标语义、few-shot 示例和 legacy alias。
- 修正 packet builder 对 VWAP/MFI/CMF 复合值的压缩方式，确保三件套在 L5 core signal 中不会被截掉。

验证结果：

- `python3 -m py_compile src/tools_L5.py src/tools_common.py src/agent_analysis/packet_builder.py src/agent_analysis/deep_research_canon.py src/prompt_examples.py`：通过。
- `python3 -m pytest tests/test_ta_l5_and_pdr_sources.py tests/test_vnext_packet_builder.py tests/test_deep_research_canon.py -q`：21 passed。
- `python3 -m pytest -q`：81 passed，6 warnings。

---

## 2026-05-03

### 完成输出体验第一轮结构改造，并记录用户验收反馈

完成内容：

- 为默认 `brief` 页面做了一轮原生输出体验改造：阅读顺序调整为判断、依据、风险、冲突、底稿、治理、审计。
- 增加证据详情抽屉、风险边界区、五层摘要卡、历史分位尺和更清晰的证据 ref 归一化，目标是让用户能从结论追到指标、来源、反证和完整底稿。
- 生成并覆盖默认 brief 页面：`output/reports/vnext_research_ui_brief_20260502.html`；未重新运行 DeepSeek，全程沿用已有 run `output/analysis/vnext/20260502_193057`。
- 补充输出体验设计报告：`OUTPUT_EXPERIENCE_DESIGN_REPORT.md`。

用户验收反馈：

- 这版不是终版，距离理想效果仍有明显差距。
- 当前审美方向不被接受，尤其主视觉配色不应继续作为默认方向。
- 五层底稿区域的点击/展开/跳转动效有问题，用户感知为无法顺畅跳转或展开。
- 后续只记录方向：审美美化待重新指明方向；交互、展开、跳转反馈和图表/数据打开体验待继续优化。

验证结果：

- `python3 -m py_compile src/agent_analysis/vnext_reporter.py`：通过。
- `python3 src/agent_analysis/vnext_reporter.py --run-dir output/analysis/vnext/20260502_193057 --template brief`：通过。
- `python3 -m pytest tests/test_vnext_reporter.py -q`：1 passed。
- `python3 -m pytest -q`：76 passed。
- 静态 HTML 检查确认 section 顺序、证据抽屉、风险区和分位尺存在，证据 ref 无缺失匹配。

---

## 2026-05-02

### 创建 P1 分支并落地 L5/数据源补强

完成内容：

- 创建分支 `codex/p1-ta-datareader-l5`，用于后续确认后再合并。
- L5 技术指标公式层优先使用 `ta`：SMA、RSI、Bollinger、ATR、MACD、OBV、Donchian、ADX 等统一进入更标准的公式路径，同时保留内部 fallback。
- 新增 `QQQ Price-Volume Quality`：VWAP(20)、MFI(14)、CMF(20)，用于量价质量验证；它们只辅助判断价格与成交量/资金流是否一致，不单独给买卖结论。
- pandas-datareader 只落地 FRED 公开 CSV fallback：当 FRED API key 缺失或 JSON API 不可用时，L1/L2/L4 的 FRED 序列仍可读。
- 真实试用发现 pandas-datareader 在当前 pandas 3 环境下较老：FRED 路径可用；Fama-French、Nasdaq symbols 和 Stooq 当前不够稳，未纳入主流程。
- `NEXT_STEPS.md` 补入 P1 路线，并用简短语言把 OpenBB 和 vectorbt 的启示放到靠后观察项。

验证结果：

- `.venv/bin/python -m pip install 'ta>=0.11.0' 'pandas-datareader>=0.10.0'`：成功安装。
- `.venv/bin/python -m pytest tests/test_ta_l5_and_pdr_sources.py -q`：3 passed。
- `.venv/bin/python -m pytest tests/test_ta_l5_and_pdr_sources.py tests/test_l3_breadth_data.py tests/test_l4_external_valuation_sources.py -q`：17 passed。
- `.venv/bin/python -m pytest -q`：76 passed。
- 真实导入检查：`ta=True`、`pandas-datareader=True`、`get_price_volume_quality_qqq` 已注册；FRED `DGS10` fallback 可读取 2026-04-01 至 2026-04-10 数据。

---

### 完成四个 GitHub 金融库对 vNext 的外部能力研究

完成内容：

- 使用 GitHub skill 研究 OpenBB、`ta`、vectorbt、pandas-datareader 四个仓库的 README、核心代码、依赖、数据 provider、MCP/API/回测/指标能力。
- 对照本仓库 `AGENTS.md`、`ARCHITECTURE.md`、`NEXT_STEPS.md`、`DATA_COVERAGE_REVIEW.md` 和当前 `tools_L5.py`，判断四个库应分别作为数据接入架构参考、L5 公式引擎参考、离线实验室和轻量数据 reader。
- 形成通俗但专业的报告：`PLAIN_LANGUAGE_GITHUB_REPO_RESEARCH.md`。

核心结论：

- OpenBB 不宜整体并入主链，但其 provider schema、OBBject metadata、MCP discovery 和扩展机制值得借鉴。
- `ta` 适合帮助 L5 标准化技术指标公式，但不能替代 vNext 对技术信号的解释、边界和跨层 hook。
- vectorbt 适合作为离线实验/回测风洞，不应直接污染 L1-L5 runtime context。
- pandas-datareader 适合补 FRED、Fama-French、Stooq、Nasdaq symbols 等轻量 reader，不适合作总数据平台。

验证方式：

- 通过 GitHub connector 拉取四个仓库元信息和关键文件。
- 对 `ta`、vectorbt、pandas-datareader 做浅克隆并本地检索核心代码结构。
- OpenBB 仓库体量较大，主要使用 GitHub connector 读取 README、Platform/Core/MCP/extension 文档和关键 provider 文件。

---

### 完成 NEXT_STEPS 1/2：DeepSeek 真实 run 与默认 brief 页面

完成内容：

- 使用最新代码完成一轮 DeepSeek 真实数据运行，生成 run：`output/analysis/vnext/20260502_193057`。
- 使用该 run 生成默认 `brief` 页面：`output/reports/vnext_research_ui_brief_20260502.html`。
- L4 数据发言权在真实 artifacts 中生效：WorldPERatio 作为第三方 PE 校验源可用，Trendonify PE / Forward PE 403 被明确记录为 `unavailable`，Damodaran 官方 Excel 作为美国市场 implied ERP 背景锚可用。
- L4 主口径保持克制：yfinance 成分模型给出当前 PE / Forward PE / FCF Yield / PB 和覆盖率，但没有生成历史分位；简式收益差距继续明确标注为 `FCF yield - 10Y`，不是 Damodaran implied ERP。
- L3 四件套在真实运行中均可用，`brief` 页面能展示 A/D Line、% Above MA、New Highs/Lows 和 McClellan 的来源、覆盖率和当前读数。
- `NEXT_STEPS.md` 已移除已完成的真实 run 和 brief 生成事项，保留后续 Trendonify 可用路径观察和 brief 阅读卡点记录。

真实源检查：

- DeepSeek：使用 `deepseek-v4-flash` 完成全链路，`deepseek-v4-pro` 未触发；最终立场为“中性偏谨慎（风险收益比不利）”，审批状态 `approved_with_reservations`。
- WorldPERatio：Nasdaq 100 PE = 32.27，数据日期 `01 May 2026`，无 explicit percentile/rank，因此历史百分位保持缺失。
- Trendonify：Trailing PE 和 Forward PE 页面均返回 403 Forbidden，系统记录不可用原因，没有 fallback 到 yfinance。
- Damodaran：官方 Excel 可用，最新行为 2025，`implied_erp_fcfe = 4.23%`，`implied_erp_ddm = 1.69%`，`tbond_rate = 4.18%`，来源等级 `official`。
- yfinance 成分模型：Trailing PE = 33.83，Forward PE = 23.15，FCF Yield = 1.55%，PB = 35.6；Trailing PE 市值覆盖 97.99%，Forward PE 市值覆盖 99.84%，FCF Yield 市值覆盖 99.63%，PB 市值覆盖 98.99%。
- 简式收益差距：-2.85%，基于 NDX FCF Yield 1.55% 减 10Y Treasury 4.4%。
- L3 广度：A/D Line 488 且趋势 `rising`；50 日线上方 65.35%，200 日线上方 56.44%；52 周新高 14 只、新低 1 只；McClellan 1.52。

验证结果：

- `python3 src/main.py --models deepseek-v4-flash,deepseek-v4-pro --skip-report --disable-charts`：成功生成 `output/analysis/vnext/20260502_193057`。
- `python3 src/agent_analysis/vnext_reporter.py --run-dir output/analysis/vnext/20260502_193057 --template brief`：成功生成 `output/reports/vnext_research_ui_brief_20260502.html`。
- 页面抽查确认包含 WorldPERatio、Trendonify 403、Damodaran、来源等级、覆盖率、不可用原因和“简式收益差距不是 implied ERP”的说明。

---

### 审计并修正 L3 广度四件套

完成内容：

- 确认 L4 口径判断，并写入 `NEXT_STEPS.md`：人工/Wind 的 PE、PB、PS、ERP 及 5/10 年分位是最高信任主锚；Trendonify 是有价值的自动分位来源但 403 时只记录待解决；WorldPERatio 的 PE、均值、标准差和估值区间可与人工数据互参，但不能伪造成历史分位；Damodaran 只做美国市场背景锚；yfinance 只做当前值和覆盖率校验。
- 修正 `New Highs/Lows` 的真实数据窗口：从共享 300 自然日窗口改为请求更长窗口，避免实际只有约 208 个交易日时无法计算 252 日新高新低。
- L3 状态识别现在能把 A/D Line 的 `declining` 视为走弱，也能读取 `% Above MA` 当前实际字段 `percent_above_50d` / `percent_above_200d`。
- A/D Line、% Above MA、New Highs/Lows、McClellan 的数据质量记录增加成分股剔除提示，避免覆盖率看起来完整但实际有缺失原因未说明。
- L3 prompt 明确四件套优先级：A/D Line 和 % Above MA 是第一锚，New Highs/Lows 是第二批扩散确认，McClellan 是广度动能确认；数据缺失不能写成恶化。

真实源检查：

- A/D Line：可用，2026-05-01，趋势 `rising`，覆盖 101/101。
- % Above MA：可用，2026-05-01，50 日线上方 65.35%，200 日线上方 56.44%，覆盖 101/101。
- New Highs/Lows：可用，2026-05-01，52 周新高 14 只、新低 1 只，覆盖 101/101。
- McClellan：可用，2026-05-01，读数 1.43，覆盖 100/101；缺失/剔除会进入 `anomalies`。
- 当前本机未安装 `nasdaq_100_ticker_history`，实时分析使用最新成分股；严格历史回测仍需标注幸存者偏差风险。

验证结果：

- `tests/test_l3_breadth_data.py`：`8 passed, 4 warnings`
- `tests/test_vnext_packet_builder.py tests/test_vnext_orchestrator.py`：`10 passed, 4 warnings`

---

### 落地 L4 外部估值源与百分位优先口径

完成内容：

- 新增统一 L4 估值源结构，外部源统一携带 `metric`、`value`、`percentile_10y`、`historical_percentile`、`data_date`、`collected_at_utc`、`source_tier`、`availability`、`unavailable_reason`、`coverage`、`formula`、`fallback_chain` 和 `source_disagreement`。
- Trendonify PE / Forward PE parser 支持真实百分位；真实联网遇到 403 时明确返回 `unavailable`，不 fallback 到 yfinance。
- WorldPERatio 解析 Nasdaq 100 PE、日期和 methodology；无明确 percentile/rank 时保持 `historical_percentile = None`，只做当前 PE 交叉校验。
- Damodaran US implied ERP 改为优先读取官方 `histimpl.xls`，HTML 只作为 fallback；输出标记为 `official`，并明确是美国市场背景锚，不替代 NDX 自身估值。
- yfinance 成分股模型保留当前 PE / Forward PE / FCF yield 和覆盖率，但 packet builder 不再用当前 PE 单点生成历史估值 regime。
- 人工/Wind 模板新增单独 ERP 参考锚，避免把人工 ERP 混入 NDX 简式收益差距。
- L4 prompt、few-shot、reporter 最小展示同步更新：显示来源等级、当前值、真实分位、数据日期、不可用原因和 source disagreement。
- 补齐 Bridge resonance chain 校验：共振链必须有证据 refs、机制、确认指标、影响和反证条件。
- 新增 `xlrd>=2.0.1` 依赖，以支持 Damodaran 官方 `.xls` 文件解析。

真实源检查：

- WorldPERatio：可用，Nasdaq 100 PE = 32.27，数据日期 = 01 May 2026；未提供明确历史分位，因此不写 percentile。
- Trendonify PE / Forward PE：当前仍返回 403 Forbidden，系统按 `unavailable` 记录原因。
- Damodaran 官方 Excel：可用，最新行为 2025，`implied_erp_fcfe = 4.23%`，`tbond_rate = 4.18%`，来源等级为 `official`。

验证结果：

- L4 外部源 / 数据发言权 / packet builder / reporter / manual template / bridge 针对性测试：`21 passed, 4 warnings` 及 Bridge `5 passed, 4 warnings`
- 全量回归：`67 passed, 6 warnings`
- 已在本机补装 `xlrd 2.0.2` 验证 Damodaran 官方 Excel 可解析。

---

### 补齐 L4 数据发言权收口项

完成内容：

- 补齐手动 Wind 模板：`licensed_manual/Wind` 仍是可选高信任输入，但空模板不会触发人工覆盖。
- 移除模板中的 `ERP_Wind` 字段，统一改为 NDX 简式收益差距口径。
- L4 prompt 明确要求读取 `source_tier`、`data_date`、`collected_at_utc`、`update_frequency`、`formula`、`coverage`、`anomalies`、`fallback_chain`、`source_disagreement`。
- L2/L4/few-shot 文案不再把 NDX 简式收益差距写成低 ERP 或负 ERP。
- 更新 `ARCHITECTURE.md`、`DATA_COVERAGE_REVIEW.md`、`PLAIN_LANGUAGE_CHANGE_REPORT.md` 和 `NEXT_STEPS.md`，记录 L4 数据发言权制度和下一步真实 run 验证。

验证结果：

- 针对性测试：`17 passed, 4 warnings`
- vNext 编排/UI/Bridge 相关测试：`10 passed, 4 warnings`
- 全量回归：`53 passed, 6 warnings`
- `config/manual_data.example.json` 通过 JSON 解析校验。
- 本机 `python` 命令不可用，验证使用 `python3`。

---

## 2026-04-29

### 合并 DeepSeek-only 运行基准

提交：

- `412f8fa Default to DeepSeek v4 runtime`

完成内容：

- 默认启用 DeepSeek，默认关闭 ChatAI、Kimi 和 Gemini。
- 默认模型顺序保持为 `deepseek-v4-flash` -> `deepseek-v4-pro`。
- DeepSeek V4 调用对齐官方 OpenAI-compatible 参数：`stream=False`、`reasoning_effort="high"`、`thinking` enabled。
- Risk Sentinel 和 Final Adjudicator 新增护栏：不得编造无证据支持的点位、跌幅、估值倍数、盈利阈值或其他定量影响幅度。
- 新增 DeepSeek 运行配置测试和 prompt 护栏测试。

验证结果：

- worktree 分支：`39 passed, 133 warnings`
- 合并后的 `main`：`39 passed, 133 warnings`
- 已推送到 `https://github.com/aidianchi/NDX_VNEXT`

### 完成 2026-04-29 真实运行与数据覆盖复盘

基线 run：

- `output/analysis/vnext/20260429_001955`

完成内容：

- 使用 `deepseek-v4-flash` 完成全链路真实运行，`deepseek-v4-pro` 未触发。
- 复盘治理输入压缩后的 Critic / Risk / Reviser / Final，确认高严重度冲突和最终证据链仍可追溯。
- 发现 L3 广度数据仍是当前最薄弱环节，新增 `DATA_COVERAGE_REVIEW.md` 记录数据稳定项、弱项和下一步。
- 用 2026-04-29 run 生成默认 `brief`：`output/reports/vnext_research_ui_brief_20260423.html`。
- 清理 `.env.example` 的编码损坏，并补充 macOS / Linux 启动路径。

---

## 2026-04-28

### 重整根目录文档

完成内容：

- 把日期型根目录文档改成更容易理解的长期文件名。
- 把过期执行计划移入 `docs/archive/`。
- 新增 `NEXT_STEPS.md`，按“核心系统、数据基础、输出体验”三类组织下一步。
- 新增 `WORK_LOG.md`，用时间倒序记录完成事项。
- 更新 `README.md`，让新读者知道先读什么。

验证方式：

- 检查根目录文档名是否能直接表达用途。
- 检查旧文件名引用是否被更新。

### 合并治理阶段输入压缩

提交：

- Claude 分支提交：`c138a96 Compress governance inputs with support evidence`
- main 合并提交：`2f0a1fd Merge governance input compression`

完成内容：

- 新增 `GovernanceInputPacket`，让 Critic / Risk / Reviser / Final 消费更窄的治理输入。
- 明确保留 `thesis_key_support_chains`。
- `key_evidence_refs` 同时保留高严重度冲突证据和 thesis 支撑链证据。
- 更新治理阶段 prompt，要求检查支撑链证据，不再只看主论点文字。
- 新增治理输入测试，覆盖“支撑证据不在高严重度冲突里也不能丢”。

验证结果：

- `35 passed, 133 warnings`

---

## 2026-04-27

### 建立 Claude Code 独立分支协作规则

完成内容：

- 新增 `CLAUDE.md`。
- 要求 Claude Code 不直接改 `main`，只能在 `claude/YYYYMMDD-short-task-name` 分支提交。
- 规定交付时必须说明分支、改动文件、测试结果和风险。

### 推送 GitHub 备份仓库

完成内容：

- 建立并推送远端仓库：`https://github.com/aidianchi/NDX_VNEXT`。
- 补充 `.gitignore`，避免提交 `.env`、`.venv/`、`output/`、缓存和密钥。

### 补充通俗解释报告风格

完成内容：

- 在 `AGENTS.md` 中写入“架构文档”和“通俗解释报告”并行的规则。
- 明确当用户要求“解释给普通人听”时，要少黑话、少中英夹杂、保留风险和不确定性。

### 完成第二轮真实运行观察

基线 run：

- `output/analysis/vnext/20260427_190347`

结论：

- 指标说明书、typed map、Objective Firewall 和 native UI 已跑通。
- 发现 Risk / Final 会模仿 prompt 示例，生成无证据支持的历史概率。
- 已增加 prompt 护栏和测试，禁止编造历史胜率、回测收益、样本区间或概率数字。

---

## 2026-04-26

### 接入 Deep Research 法典第一轮

完成内容：

- 将 `RESEARCH_CANON.md` 定位为指标判读、市场状态诊断、跨层级推理和少文本提示的权威语料。
- 增加 ObjectCanon、IndicatorCanon、RegimeScenarioCanon、ObjectiveFirewallSummary 等核心概念。
- 让 L1-L5 开始具备指标发言权、误读护栏、反证条件和交叉验证意识。

原则：

- 不把整份研究材料硬塞进 prompt。
- 不破坏 L1-L5 运行时上下文隔离。

---

## 2026-04-24 至 2026-04-25

### 建立 vNext 第一版架构基线

完成内容：

- 明确 `Context-first, role-second`。
- 建立 L1-L5、Bridge、Thesis、Critic、Risk、Reviser、Final 的基本链路。
- 建立 native vNext UI 原型。
- 保留 legacy adapter 作为兼容路径，但不再让它承担主要推理。
