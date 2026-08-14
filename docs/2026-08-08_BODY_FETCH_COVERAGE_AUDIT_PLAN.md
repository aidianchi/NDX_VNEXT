# 事件层正文抓取覆盖率审计与改法预案

日期：2026-08-08  
状态：**审计已完成，改法待拍板**（等老大确认后动手）  
关联代码：`src/news_event_ledger.py`  
留证：`output/body_fetch_audit/20260808_110700/audit_result.json`  
审计脚本：`/tmp/ndx_body_fetch_audit.py`（待固化进 `scripts/`）

---

## 0. 一句话摘要

最近一次 run 的 72 条事件里，**76.4%（55 条）没有抓到正文**。用扩充词表模拟重跑证明：词表偏科确实存在，但只解释其中的 18.2%（10 条，且 90% 是 M7 个股）；**更大的漏洞是「官方源也走同一把关键词尺」，把正文价值最高的 SEC filings 拦在了门外**。因此改法的主杠杆不是无脑扩词表，而是「官方源强制抓正文 + 词表补 M7 ticker」两个小改动。

## 1. 背景：这个问题是怎么被发现的

- **T47 上下文根本性审查**（2026-08-07）：事件链通读发现"约 70% 事件仅标题、无正文"，标注为事件层数据质量短板。
- 老大追问「正文抓取怎么判断命中关键词」→ 核对代码后发现一个关键事实：**关键词表（`HIGH_RELEVANCE_BODY_FETCH_KEYWORDS`）只管"要不要花成本抓全文"，不管"事件相不相关、进不进账本"**——相关性由源配置（Yahoo RSS URL 里的 `s=QQQ`/`s=M7`、Wind/Reddit 搜索词）让数据源代劳筛选，与 TradingAgents 的 `yf.Ticker().get_news()` 机制同构。
- 于是提出验证假设：**"70% 仅标题"的病灶是否在词表偏科？** 老大批准跑审计脚本量化。

## 2. 审计方法（可复现）

- 数据：`output/analysis/vnext/20260731_002156/news_event_ledger.json`（最近一次完整 run，72 条 realized 事件）。
- 逻辑复刻：`_should_fetch_article_body`（`news_event_ledger.py` L1060）——① 社媒事件/非法 URL 前置拦截；② 标题+URL 拼串小写；③ 命中 = AI 独立词正则 `(?<![a-z])ai(?![a-z])` 或 35 词关键词表子串匹配。
- 对照：旧 35 词表 vs 扩充词表（新增 44 词：M7 ticker + 权重股公司名/产品名 + 监管/地缘/产业主题）。
- 口径说明：审计脚本对 ticker 词用的是**子串匹配（乐观口径）**；正式实现需改为词边界匹配（见 §6 风险）。

## 3. 审计结果

### 3.1 总览：55 条无正文的去向

| 去向                                  | 数量        | 性质            |
| ----------------------------------- | --------- | ------------- |
| 有正文                                 | 17（23.6%） | —             |
| ① 设计拦截（Reddit 社媒 / 非法 URL）          | 8         | 设计如此，不算问题     |
| ② 尝试抓取但失败 / 为空（`body_fetch_failed`） | 8         | 抓取可靠性问题，与词表无关 |
| ③ 被词表闸门拦下，从未尝试                      | 39        | **词表相关的地盘**   |

### 3.2 词表偏科量化（核心结论）

39 条"从未尝试"用扩充词表模拟重跑：

- **救回 10 条**（25.6% of 从未尝试；18.2% of 全部无正文），**其中 9 条涉及 M7 个股（90%）**。
- 救回来源分布：`official_filing` 7 条 + `reliable_mainstream_report` 3 条。
- **最典型的证据**：SEC filings 标题是 ticker 式——`MSFT 10-K filed 2026-07-29`、`META 8-K filed 2026-07-29`、`TSLA 10-Q filed 2026-07-23`。旧词表里没有任何 ticker 词，导致**正文价值最高的公司披露原文（10-K/8-K 全文）因为 6 个字符的标题被拦在门外**。
- 救回的主流报道示例：`Meta stock poised for a new losing streak: Earnings call takeaways`（靠新词 meta）、`Qualcomm Facing Margin Pressures...`（靠新词 margin）。

### 3.3 诚实的另一半：29 条救不回

- 大头是 **BLS 官方宏观发布**（如 "Usual Weekly Earnings of Wage and Salary Workers"）——标题已说明内容，正文价值有限，不值得为它们扩词；
- 其余是 Yahoo 泛头条（NBIS 个股、巴菲特持仓解读、PCE 数据等），相关性一般，漏了不可惜。
- 结论：**无脑把词表扩到几百词是浪费**，合理边界就是"M7 权重股 + 高频产业主题"。

## 4. 根因拆解（三层）

1. **词表偏科**：35 词集中在宏观 + AI 半导体 + 财报；无 M7 ticker、无权重股公司名、无监管/地缘词。→ 漏 M7 个股新闻正文 + 漏 SEC filing 标题。
2. **官方源与市场源同一把尺**：`official_fact` / `company_disclosure` / `official_filing`（SEC）这些**正文价值最高、页面最稳**的来源，也按标题关键词筛，导致"MSFT 10-K filed"这种标题被拦。这是本次审计发现的最大问题。
3. **抓取失败无重试**：8 条 `body_fetch_failed`/空，一次性失败即降级，没有第二次机会。

## 5. 准备的改法（按优先级）

### 方案 1：官方源强制抓正文（主杠杆，优先做）

- **改什么**：`_should_fetch_article_body` / 调用点（`_collect_rss_events`、`_collect_sec_events`、`_collect_market_news_events` 等）。当事件的来源等级属于官方系（`source_tier` / `authority_tier` ∈ {`official_fact`, `official_macro`, `official_filing`, `company_disclosure`, `primary_market_data_release`}）时，**无条件放行抓正文，不走关键词闸门**。
- **为什么**：本次无正文里官方系共 19 条（official 8 + official_macro 7 + official_filing 4），正文价值最高、抓取成功率最高（页面稳定无 paywall），却被词表拦了一半以上。
- **影响范围**：只影响事件层自身的正文抓取决策；不改隔离红线（事件仍是第二层材料）、不改相关性、不进 L1-L5。
- **风险**：官方源数量可控（Fed/BLS/BEA/SEC/日历），抓取成本增加有限；个别官方页抓取失败仍走 `body_fetch_failed` 降级，不阻塞。

### 方案 2：词表补 M7 ticker + 权重股词（优先做）

- **改什么**：`HIGH_RELEVANCE_BODY_FETCH_KEYWORDS`（L193）按分组扩充。新增词清单已写入 `audit_result.json` 的 `new_keyword_list` 字段（44 词）。
- **关键实现细节**：**ticker 类词（MSFT/GOOGL/TSLA/AVGO…）必须用词边界正则匹配，不能子串匹配**——`meta` 会误伤 `metadata`，`tsm` 会误伤 `tsmc`，`crm` 会误伤任意含 crm 的词。全名/产品词（apple/microsoft/azure…）可维持子串。
- **为什么**：救回 10 条中的 9 条 M7 个股新闻，其中 7 条是 SEC filing ticker 标题。
- **影响范围**：同上，只影响正文抓取决策。
- **风险**：词边界匹配引入少量"全名命中但实际无关"的抓取浪费（如 "Tesla" 出现在任何语境），属安全侧，可接受。

### 方案 3（后续）：抓取失败重试

- 对 `body_fetch_failed` 的 8 条做一次镜像/备用路径重试（如无头浏览器或阅读器镜像），或至少记录失败原因分布。
- 中成本，建议在 1+2 验证后再做。

### 方案 4（后续）：mainline 两阶段补抓

- 账本先出 → 机制报告算出 mainlines → 对 mainline 引用的事件做第二轮正文补抓。与方案 1 有重叠，优先级低于 1。

## 6. 验证方案（改前改后对比）

1. 改前基线（已有）：`raw_text_available` 覆盖 23.6%（72 事件 / 17 有正文）。
2. 改后：重新运行同一 run 的事件采集（或直接跑账本构建），再用同一审计脚本重跑，对比：
   - `raw_text_available` 覆盖率（预期显著提升）；
   - 方案 1 是否覆盖全部官方系 19 条；
   - 方案 2 是否救回 M7 个股新闻正文。
3. 全量测试（`python -m pytest -q`）确认不破坏现有事件层测试（`test_news_event_ledger.py` 等）。
4. 剩余风险：审计脚本的"乐观口径"（子串）与正式实现的差异，改完后以真实 run 数字为准，不以上一轮模拟为准。

## 7. 决策点（等老大拍板）

- [ ] 是否按「方案 1 + 方案 2」动手改？（建议：是）
- [ ] 方案 2 的最终词表清单是否以 `new_keyword_list` 为准？（可增删）
- [ ] 审计脚本是否固化进 `scripts/audit_body_fetch_coverage.py` 以便每轮 run 后可复跑？（建议：是）

## 8. 附：改法完成后的验收标准

- 官方系事件（official_fact / company_disclosure / official_filing）正文抓取率 → 100%（排除抓取失败降级）。
- M7 个股新闻（Yahoo M7 头条 + SEC filing）正文抓取率显著提升。
- 全量测试通过；无事件层隔离红线变化；`audit_result.json` 留证可追溯。
