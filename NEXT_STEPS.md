# vNext 下一步

最近更新：2026-04-29
阅读方式：最新事项放在最上面。完成后把结果写入 `WORK_LOG.md`，同样按时间倒序。

---

## 最新下一步

| 顺序 | 类别 | 任务 | 为什么重要 | 完成标准 |
| --- | --- | --- | --- | --- |
| 1 | 核心系统 | 加强 Bridge `resonance_chains` 的证据要求 | 2026-04-29 run 中 typed conflicts 已较稳，但 resonance chain 仍可能缺少 evidence refs、confirming indicators 或机制说明 | Bridge prompt 和测试要求 resonance chain 必须能追到证据和确认指标 |
| 2 | 数据基础 | 优先补 L3 广度数据源和 fallback | 数据覆盖复盘显示 L3 是当前最薄弱层，尤其广度和内部扩散指标 | `DATA_COVERAGE_REVIEW.md` 中列出的 4 个 L3 弱项有稳定来源、fallback 或明确降级说明 |
| 3 | 输出体验 | 评审 2026-04-29 run 的默认 `brief` 页面 | 核心 artifacts 已有新 run，页面也已生成，但普通读者的连续阅读体验还没有跟着复盘 | 记录阅读卡点、证据跳转问题和版式修改建议 |
| 4 | 核心系统 | 继续观察治理输入压缩后的多轮稳定性 | 单轮 DeepSeek run 已通过，但还不足以证明长期稳定 | 至少再跑 2 轮真实数据，确认 Critic / Risk / Reviser / Final 不丢高严重度冲突 |
| 5 | 输出体验 | 判断下一阶段是继续强化 self-contained HTML，还是启动正式前端 viewer | 前端框架化只有在信息架构稳定后才值得做 | 有明确选择标准：读者体验、证据跳转、run 切换、图表接入、维护成本 |

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
