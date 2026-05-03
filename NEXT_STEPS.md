# vNext 下一步

最近更新：2026-05-03
阅读方式：最新事项放在最上面。完成后把结果写入 `WORK_LOG.md`，同样按时间倒序。

---

## 最新下一步

### 输出体验反馈：当前改造版不是终版

- 用户已查看 `output/reports/vnext_research_ui_brief_20260502.html` 的改造版，并明确表示：当前审美方向不满意，尤其主视觉配色不应作为后续默认方向。
- 五层底稿区域的点击/展开/跳转动效存在问题：用户感知为“似乎无法跳转，动画有问题”。这说明当前交互反馈不够清楚，也可能存在浏览器侧展开状态或滚动定位问题。
- 这版可以作为“输出体验第一轮结构尝试”保留，但不能被视为最终 UI，也不能作为审美定稿。
- 下一阶段输出体验只记录方向：审美方向需要重新指明；五层展开、证据抽屉、跳转反馈和动效需要继续优化；图表/数据/报告的打开方式仍需更自然、更低门槛。

### P1：L5 公式层和轻量数据 fallback

- L5 公式层优先用 `ta` 做标准化计算，同时保留内部 fallback；新增指标必须回答明确问题，不能为了显得全面而堆指标。
- VWAP / MFI / CMF 可作为高价值量价质量验证：它们帮助判断价格上涨是否得到成交量和资金流支持，但不能单独给买卖结论。
- pandas-datareader 先只承担 FRED 公开 CSV fallback：在 FRED API key 缺失或 JSON API 失败时，补强 L1/L2/L4 的宏观、利率、信用和流动性数据。
- pandas-datareader 的 Fama-French、Nasdaq symbols、Stooq 暂不进主流程；当前 pandas 3 环境和部分上游接口不够稳，先记录观察，不硬接。

### L4 估值锚口径确认

- 人工/Wind 是最高信任、可选输入的主锚：当前重点支持 `PE`、`PB`、`PS`、`ERP` 及其 5/10 年分位。
- Trendonify 是有价值的自动分位来源；若普通采集遇到 403，本轮只记录不可用和后续待解决，不硬绕、不静默退回 yfinance。
- WorldPERatio 不只是 PE 校验源；它的 Nasdaq 100 PE、均值、标准差、估值区间和滚动口径可与人工数据互参，用来辅助描述相对位置。但如果页面没有明确 percentile/rank，不能写成历史百分位。
- Damodaran implied ERP 是美国市场风险补偿背景锚，不替代 NDX 自身 PE / PB / PS / Forward PE 分位。
- yfinance component model 保留为当前值、覆盖率和口径校验，不承担历史估值 regime 主判断。

| 顺序 | 类别 | 任务 | 为什么重要 | 完成标准 |
| --- | --- | --- | --- | --- |
| 1 | 数据基础 | 继续观察 Trendonify 的可用路径 | 当前普通 HTTP 访问仍 403；系统已能正确承认不可用，但 Trendonify 的历史分位价值很高 | 决定是否做浏览器采集、缓存、或人工录入路径；不得静默 fallback 成 yfinance |
| 2 | 输出体验 | 暂缓 brief 大改，只记录阅读卡点 | 审美和交互应等证据链稳定后升级 | 只记录来源、覆盖率、更新时间、简式收益差距标签和百分位展示的阅读问题 |

---

## 三类目标是否合理

合理，而且建议固定为以后所有计划的一级分类。

### 1. 核心系统

这是“怎么推理”的问题，也是当前重中之重。

包括：

- L1-L5 是否保持上下文隔离；
- 每层是否有指标级分析、层内综合、内部冲突、自检；
- Bridge 是否生成 typed conflict / resonance / transmission map；
- Thesis 是否只整合，不重新脑补；
- Critic / Risk / Reviser / Final 是否保留冲突、风险和证据边界；
- governance input 是否减少 token，同时不丢关键证据。

判断标准：推理链是否干净、具体、可追溯，不为了顺滑结论抹平张力。

### 2. 数据基础

这是“凭什么推理”的问题。

包括：

- 数据采集是否稳定；
- 指标定义是否清楚；
- 历史频率、发布日期、观测日期是否区分；
- 数据是否需要 fallback；
- 哪些指标只是代理，不能当官方事实；
- L3 广度、成分股、集中度、领导力扩散等结构数据是否足够。

判断标准：系统在不知道时能承认不知道，在数据弱时能降低置信度，而不是用漂亮文字掩盖缺口。

### 3. 输出体验

这是“别人怎么读懂、怎么追问”的问题。

包括：

- 默认报告是 `brief`，还是另一个更适合连续阅读的模板；
- 是否需要正式前端 viewer；
- evidence ref 跳转是否顺手；
- 风险、冲突、反证是否醒目；
- 普通读者是否能从最终判断一路追到证据；
- 页面审美是否专业、克制、耐读。

判断标准：读者不需要懂代码，也能明白结论从哪里来、哪里有风险、什么证据会改变判断。

---

## 三类之间的关系

优先级不是永远固定的，但依赖关系很清楚：

1. 数据基础是地基。数据不准，核心系统越强，越可能严肃地分析错误材料。
2. 核心系统是骨架。没有干净推理链，输出体验只是把混乱包装得更好看。
3. 输出体验是交付面。没有好的阅读和交互，系统再强也很难被人持续使用和审查。

因此当前策略是：

- 核心系统继续作为第一优先级；
- 数据基础作为并行审计线，不能长期欠账；
- 输出体验等 `brief` 经过真实阅读验证后，再决定是否正式前端化。

---

## 当前不优先做

- 不新增更多 agent 角色。
- 不把 L3 立刻升级为 hard fail。
- 不把 `RESEARCH_CANON.md` 大段塞进 prompt。
- 不继续美化 legacy HTML。
- 不在 `brief` 信息架构确认前急着上正式前端框架。
- 不用未经证据支持的历史概率、回测收益、样本期包装判断。

## 靠后观察：外部库启示

- OpenBB 的启示是“数据源要有 provider、口径和可发现工具”，短期先学它的数据治理方式，不急着把整个平台接进来。
- vectorbt 的角色是离线实验室：以后用来检验策略假设和冲突场景，不让回测结果直接污染 L1-L5 的本次运行判断。

---

## 需要用户判断的点

1. `brief` 页面是否真的适合作为默认阅读入口。
2. 数据线优先补 L3，还是先做全量数据覆盖复盘。
3. 输出体验下一阶段是继续 self-contained HTML，还是准备正式 viewer。

---

## 验证命令

全量测试：

macOS / Linux：

```bash
python -m pytest -q
```

Windows PowerShell：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

生成四个 UI 模板：

```powershell
.\.venv\Scripts\python.exe src\agent_analysis\vnext_reporter.py --run-dir output\analysis\vnext\<run_id> --template all --output output\reports\vnext_ui_template.html
```

真实 smoke：

```powershell
.\.venv\Scripts\python.exe src\main.py --models deepseek-v4-flash,deepseek-v4-pro --data-json output\data\data_collected_v9_live.json --skip-report --disable-charts
```
