# Run 20260517_001618 数据完整性审核报告

**审核日期**：2026-05-17  
**审核对象**：`output/analysis/vnext/20260517_001618/` 及关联产物  
**审核依据**：run 日志 `20260517_001616_441.log`、`analysis_packet.json`、`chart_time_series.json`、`manual_data.local.json`、workbench HTML、相关源代码

---

## 第一部分：用户自主发现的问题

用户在运行最新 run（20260517_001618）后，自行发现以下 7 个问题。AI 对每个问题进行了事实核实和根因分析。

---

### U1. 报告数据日期为 5-12，而非用户选择的 5-17

**核实结果**：确认存在。

**事实**：
- 控制台执行命令：`src/console_run_all.py --data-json output/data/data_collected_v9_live.json ...`
- `data_collected_v9_live.json` 文件修改时间为 **2026-05-12 21:52:12**（5 天前）
- `analysis_packet.json` 中 `meta.data_date = "2026-05-12"`，`collector_timestamp_utc = "2026-05-12T13:52:12"`
- 报告顶部显示"数据日期 2026-05-12"

**根因**：控制台在"已有数据分析"模式下，自动选择了最新的 `data_collected_v9_*.json` 文件（5/12 的旧文件），未触发重新采集。这是控制台的默认行为——`research_console.py` 第 128-129 行自动选取最新数据 JSON，第 1014-1016 行将其传入 `--data-json` 参数。用户选择 5-17 作为分析日期，但控制台未检测数据 JSON 的年龄，仍使用 5 天前的数据。

**严重度**：**高**。投资研究系统的数据时效性是核心要求，5 天的数据滞后不可接受。

---

### U2. ADX（Average Directional Index）缺失

**核实结果**：确认缺失。

**事实**：
- `analysis_packet.json` 中 L5 `get_adx_qqq`：`value = null`，`error = "Upstream data source returned None."`
- `notes = "ta公式层未产出ADX，且 yfinance 或 pandas_ta 不可用。"`
- 日志显示 QQQ 数据获取 3 次重试全部失败：`YFRateLimitError('Too Many Requests. Rate limited.')`

**根因**：ADX 计算有两条路径，均依赖 QQQ OHLCV 数据：
1. 主路径：`ta` 公式层调用 `get_qqq_technical_indicators()`，需 QQQ OHLCV
2. Fallback 路径：`pandas_ta` 的 `df.ta.adx()`，也需通过 `cached_yf_download()` 获取 QQQ 数据

两条路径均因 yfinance 限流而失败。这是 yfinance 全面限流的连带影响（详见 AI1）。

**严重度**：**中**。L5 分析用均线排列和 MACD 替代了 ADX，但趋势强度判断的置信度下降。

---

### U3. 多个成分股 trailing_pe 为 invalid、fcf_yield 为 missing

**核实结果**：确认存在。

**事实**：
- 8 个成分股 `trailing_pe` 被标记为 `invalid_trailing_pe`：INTC, TTWO, MSTR, INSM, KHC, ZS, CRWD, WBD
- 多个成分股 `fcf_yield` 被标记为 `missing_fcf`
- 系统仍从 93/101 个有效成分股计算了加权 trailing PE（成分覆盖率 92.08%，市值覆盖率 97.66%）
- 聚合 FCF yield 为 1.44%（基于部分数据）

**根因分析**：
- **INTC**（Intel）：近年持续亏损，trailing PE 为负或 undefined，属于真实财务状况
- **MSTR**（MicroStrategy）：大量比特币持仓导致会计处理特殊，yfinance `trailingPE` 返回异常值
- **CRWD**（CrowdStrike）：近期安全事件可能影响 yfinance 数据
- **ZS**、**TTWO**、**KHC**、**INSM**、**WBD**：可能处于亏损或微利状态

`missing_fcf` 同理——部分公司 yfinance 未返回 `freeCashflow` 字段。

**严重度**：**低-中**。系统已正确排除异常值并标注覆盖率，属于 yfinance 数据源的固有限制。但 `manual_data.local.json` 中 `ForwardPE`、`EarningsYield`、`FCFYield` 全部为 null，意味着关键估值字段未手动补全。

---

### U4. 人工数据置信度选择器设计不合理

**核实结果**：确认当前 UI 设计不合理。

**事实**：
- `src/research_console.py` 第 210-216 行：置信度下拉框含"不覆盖 / high / medium / low"四个选项
- `confidence` 字段写入 `metric.data_quality.coverage.confidence`
- 但 `manual_data.local.json` 中 `coverage.confidence` 从未被系统逻辑实际读取或使用
- 系统判断手动数据是否生效的逻辑是 `active` 布尔值 + `source_tier`（`licensed_manual/Wind`），与 `confidence` 无关

**结论**：置信度选项在当前架构中无实际作用。手动数据的权威性由 `source_tier` 和 `active` 决定。用户建议简化为"使用人工数据"勾选框是合理的。

**严重度**：**低**（UI 改善）。不影响数据准确性，但误导用户以为置信度选择有实际效果。

---

### U5. Workbench 价格技术模块 crosshair 不显示数据

**核实结果**：代码层面已修复，本次 run 可能因数据问题触发。

**事实**：
- `chart_time_series.json` 中 `QQQ_OHLCV.rows` 为空数组（`[]`），因 yfinance 限流无法获取数据
- workbench HTML 的 source 标签为 `"cached fallback: 20260512_215333_collect_only/chart_time_series.json · QQQ OHL CV"`——从旧 run 缓存获取 chart 数据
- crosshair 代码逻辑（`findPointAtOrBefore`、`handleCrosshair`、`subscribeCrosshairMove`）在源码层面正确
- 但当 chart 数据来自 cached fallback 时，数据时间范围可能与当前时间轴不匹配，导致 crosshair 找不到对应数据点

**需要进一步确认**：用户看到的 crosshair 问题是"完全没有数据"还是"部分时间点没有数据"。如果是前者，可能是 cached fallback 数据与时间轴不匹配导致。

**严重度**：**中**。需在有完整数据的 run 中复现确认。

---

### U6. Workbench 默认历史窗口 10Y 未生效

**核实结果**：代码已改为 10Y，本次生成的 HTML 确认包含 10Y 按钮。

**事实**：
- `src/interactive_chart_workbench.py` 第 559-561 行：按钮为 `10Y (3650)` / `15Y (5475)` / `ALL`
- 第 1635 行：`updateRange(3650)` 初始化为 10Y
- 本次生成的 workbench HTML 确认包含 `<button data-range="3650">10Y</button>` 和 `updateRange(3650)`

**可能原因**：用户打开的是旧版 workbench HTML（浏览器缓存或控制台跳转到旧文件）。本次生成的文件名为 `vnext_workbench_20260512_2152_20260517_0016.html`。

**严重度**：**低**。代码层面已生效，可能是浏览器缓存问题。

---

### U7. 流动性历史数据为负（特别早的时候）

**核实结果**：确认存在，根因是 FRED WTREGEN（TGA）历史数据质量问题。

**事实**：
- `chart_time_series.json` 中 `NET_LIQUIDITY` 共 8499 行，其中 **2077 行为负值**
- 负值时间范围：2003-02-07 至 2008-10-21
- 最小值：-8197.03（十亿美元）
- 2009 年后转为正值，当前值 5830.61

**根因分析**：
- Net Liquidity = WALCL（Fed 资产） - TGA（财政部一般账户） - RRP（隔夜逆回购）
- 2002-2008 年 TGA 数据异常偏高：2002 年 TGA = 5959（十亿美元），而同期 WALCL 仅 719（十亿美元）
- 真实 TGA 在 2002 年约 50-100 亿美元量级，不可能达到 5.9 万亿美元
- 2007-05-02 后 TGA 降至合理水平（14.89B）
- 这是 **FRED WTREGEN 系列的历史数据质量问题**——2007 年之前的 TGA 数据单位或口径与后期不一致
- `src/tools_L1.py` 中的 `_normalize_billions()` 函数尝试自动检测并转换单位，但无法处理 2002-2008 的异常值

**影响**：
- workbench 中 NET_LIQUIDITY 图表在 2003-2008 区间显示大幅负值，与真实流动性状况不符
- 历史分位数计算（5Y/10Y percentile）可能被这些异常值污染
- 当前值（5830.61B）和近期数据是正确的

**严重度**：**中**。近期数据正确，但历史图表和分位数计算受污染。

---

## 第二部分：AI 审计额外发现的问题

AI 在核实用户报告的问题后，进一步排查发现以下额外问题。

---

### AI1. yfinance 全面限流导致数据完整性严重受损

**严重度**：**高**

**事实**：
- 本次 run 中 5 个关键 ticker 全部限流失败，每个 ticker 3 次重试均返回 `YFRateLimitError`：

| Ticker | 重试次数 | 错误 |
|--------|---------|------|
| QQQ | 3 | YFRateLimitError |
| ^VIX | 3 | YFRateLimitError |
| ^VXN | 3 | YFRateLimitError |
| HYG | 3 | YFRateLimitError |
| QQEW | 3 | YFRateLimitError |

- workbench 生成时 QQQ 再次限流失败（日志第 164-167 行）

**影响链**：
1. QQQ OHLCV 数据完全缺失 → ADX 失败（U2）、workbench 图表数据为空
2. VIX/VXN 数据缺失 → L2 波动率分析受损
3. HYG 数据缺失 → L2 信用分析受损
4. QQEW 数据缺失 → QQQ/QQEW 比率计算受影响
5. workbench 图表退回到旧 run 缓存数据

**系统应对**：使用了 stale cache fallback（`data_cache/yfinance/` 中的 pickle 文件），但 pickle 缓存**无 TTL**（`src/tools_common.py` 第 209-220 行），可能返回非常旧的数据且无时效性标注。

**建议**：
- 增加替代数据源（如 Alpha Vantage、FRED 直连、Yahoo Finance direct）
- pickle 缓存增加 TTL（如 7 天），超时后拒绝使用
- 限流时增大重试间隔（当前仅 2 秒，应指数退避至 30-60 秒）
- 在报告中明确标注数据来源是 live 还是 stale cache

---

### AI2. 手动数据关键估值字段缺失

**严重度**：**中**

**事实**：`manual_data.local.json` 中以下关键字段为 null：

| 字段 | 当前值 | 影响 |
|------|--------|------|
| `ForwardPE` | null | L4 前瞻估值分析缺少关键输入 |
| `EarningsYield` | null | 简式收益差距无法用手动值覆盖 |
| `ForwardEarningsYield` | null | 前瞻收益分析缺失 |
| `FCFYield` | null | 简式收益差距（FCF yield - 10Y Treasury）依赖自动计算 |
| `PS_TTM` | null | 市销率分析缺失 |
| `PCF_TTM` | null | 市现率分析缺失 |

`PE_TTM`（36.6）和 `PB`（10.49）已手动提供，但 Forward PE 和 FCF yield 的缺失导致：
- 简式收益差距（-2.94%）完全依赖 yfinance 自动计算，无手动覆盖能力
- Forward earnings quality 分析缺少关键输入

---

### AI3. 图表数据源来自旧 run 缓存，非本次采集

**严重度**：**中**

**事实**：
- workbench HTML 的 `source` 标签：`"cached fallback: 20260512_215333_collect_only/chart_time_series.json · QQQ OHL CV"`
- `chart_time_series.json` 中 `QQQ_OHLCV.rows` 为空数组
- workbench 代码（`interactive_chart_workbench.py` 第 179-196 行）在当前 run 无 chart 数据时，自动搜索同目录下其他 run 的 `chart_time_series.json` 作为 fallback

**影响**：用户在 workbench 中看到的图表反映的是 5/12 旧 run 的市场状态，而非 5/17 的最新数据。图表上无任何标注说明数据来自旧缓存。

---

### AI4. L3 第一次 LLM 响应 JSON 解析失败

**严重度**：**低**

**事实**：
- 日志第 114 行：`[Stage: l3] 在AI响应中未找到任何有效的JSON块。`
- 原始响应保存至 `ai_response_debug_l3_20260517_002129.txt`（7317 字符）
- 第二次尝试成功（日志第 117-120 行）

**根因**：DeepSeek V4 Flash 模型偶尔输出格式不规范的 JSON（可能是截断或包含非 JSON 文本）。系统已有重试机制，第二次成功完成。

---

### AI5. yfinance frame cache（pickle）无 TTL

**严重度**：**中**（潜在风险）

**事实**：
- `src/tools_common.py` 第 209-220 行：`cached_yf_download()` 将 yfinance 下载结果写入 pickle 文件
- pickle 文件**无过期时间**——一旦写入，后续任何失败都会使用该 pickle 作为 stale fallback
- 与之对比，info cache（JSON 格式）有 24 小时 TTL（第 358 行）

**风险**：如果 yfinance 长时间限流，系统可能使用数天甚至数周前的 pickle 数据，且用户无法从报告中得知数据实际时效。

---

## 第三部分：问题优先级汇总

| 编号 | 问题 | 来源 | 严重度 | 修复复杂度 | 建议 |
|------|------|------|--------|-----------|------|
| U1 | 数据日期 5/12 而非 5/17 | 用户 | **高** | 中 | 控制台检测数据 JSON 年龄，超过阈值时提示重新采集 |
| AI1 | yfinance 全面限流 | AI | **高** | 高 | 增加替代数据源、stale cache TTL、指数退避重试 |
| U7 | 流动性历史数据为负 | 用户 | **中** | 中 | 修复 FRED WTREGEN 历史数据的单位转换，或截断 2007 年前的异常数据 |
| U2 | ADX 缺失 | 用户 | **中** | 低 | 依赖 AI1 修复；可考虑增加本地预缓存 |
| U5 | Crosshair 不显示数据 | 用户 | **中** | 中 | 需在完整数据 run 中复现确认 |
| AI2 | 手动数据关键字段缺失 | AI | **中** | 低 | 提示用户补全 ForwardPE/FCFYield |
| AI3 | 图表用旧缓存数据 | AI | **中** | 中 | workbench 应标注数据时效性警告 |
| AI5 | pickle cache 无 TTL | AI | **中** | 低 | 为 pickle 缓存增加 TTL（如 7 天） |
| U6 | 10Y 窗口未生效 | 用户 | **低** | 低 | 确认用户打开的是最新 HTML |
| U4 | 置信度 UI 改为勾选框 | 用户 | **低** | 低 | 移除下拉框，改为 checkbox |
| AI4 | L3 JSON 解析失败 | AI | **低** | 无 | 已有重试机制，无需额外处理 |
| U3 | trailing_pe/fcf 异常 | 用户 | **低** | 低 | yfinance 固有限制，系统已正确处理 |

---

## 第四部分：核心结论

本次 run 的**根本问题是数据采集层的脆弱性**，具体表现为三个层面：

1. **数据获取层**：yfinance 对本机 IP 全面限流，5 个关键 ticker 全部失败，导致 QQQ OHLCV、VIX、VXN、HYG、QQEW 数据缺失，连带 ADX 失败、workbench 图表为空。

2. **数据管理层**：控制台默认使用旧数据 JSON（5/12）而非触发新采集；pickle 缓存无 TTL，可能返回陈旧数据且无时效标注。

3. **数据展示层**：workbench 图表退回到旧 run 缓存但未标注数据来源时效；流动性历史数据因 FRED WTREGEN 单位问题在 2003-2008 区间显示异常负值。

这三个层面的问题叠加，导致用户在 5/17 看到的分析报告实际基于 5/12 的数据，图表反映的也是 5 天前的市场状态，且历史流动性图表存在数据质量问题。

**建议修复优先级**：
1. P0：解决 yfinance 限流问题（AI1）——这是所有数据问题的根因
2. P0：控制台增加数据时效性检测（U1）——防止使用过期数据
3. P1：修复 FRED WTREGEN 历史数据单位转换（U7）
4. P1：为 pickle 缓存增加 TTL（AI5）
5. P2：workbench 标注数据时效性警告（AI3）
6. P2：简化手动数据置信度 UI（U4）
