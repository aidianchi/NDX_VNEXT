# vNext 下一步

更新日期：2026-05-20

阅读方式：本文件只记录两类内容：

1. 当前仍未完成、需要后续执行的事项。
2. 尚未排进施工队列、但值得保留的后续方向思考。

已经完成的事项不在这里维护，统一看 `WORK_LOG.md`。架构原则看 `ARCHITECTURE.md`，运行复盘看 `RUN_REVIEW_CHECKLIST.md`，数据边界看 `DATA_COVERAGE_REVIEW.md`。

---

## 当前待完成

| 优先级 | 类别 | 待办 | 为什么重要 | 完成标准 |
| --- | --- | --- | --- | --- |
| P0 | 核心系统 | Decision Semantics 架构改革第一轮 | 2025-04-09 回测说明最终综合层把“风险未解除”误写成“赔率不利”；需要从单一 stance 升级为“证据解释价格、价格决定赔率、赔率约束行动”。方向见 `docs/2026-05-20_DECISION_SEMANTICS_ARCHITECTURE_REFORM.md` | Thesis / Final contracts 和 prompts 能输出状态诊断、价格隐含叙事、赔率判断、分时间尺度结论、核心/战术动作、确认成本和失效条件；brief 首屏不再展示 adjudicator notes；2025-04-09 样本不再被压扁成无解释的“中性偏谨慎” |
| P1 | 核心系统 / 输出体验 | Agent 输入/输出审计视图原型 | 用只读方式让人直观看到每个 agent 收到什么、输出什么、下游用了什么；先验证 context isolation 和字段价值，避免过早堆复杂自动审计规则 | Native brief 或独立审计页按阶段展示 input 摘要、output 核心字段、evidence refs、字段质量提示和下游消费去向；明确全局 `context_brief` 与 `layer_context_briefs/Lx` 的区别，证明 L1-L5 没有看到其他层运行时 highlights |
| P1 | 数据基础 | yfinance 盈利质量代理实时模式审计 | 回测模式已自动跳过 yfinance 成分股基本面批量代理；实时模式仍可把它作为 sanity check 使用，但必须确认字段来源、公式和 stale cache 边界 | 针对 `get_ndx_pe_and_earnings_yield`、`get_ndx_forward_earnings_quality` 输出审计结论；字段覆盖率、公式、缓存新鲜度、失败 fallback 和不能证明什么都写入 data_quality / prompt / brief |
| P1 | 数据基础 | 历史数据研究助理 skill 原型 | 回测缺口不能靠主分析链临场补；需要独立联网研究助理持续寻找候选历史数据源，并把“如何找到”的经验沉淀成可复用规则 | 读取 `backtest_data_boundaries` 生成候选证据包；输出链接、发布时间、数据日期、摘录/截图、适用风险和置信度；默认标记 `research_candidate` / `manual_review_required`，不得直接进入 L1-L5 |
| P2 | 数据基础 | 采集机 / 快照模式产品化 | yfinance/Yahoo 与 DeepSeek 的最佳网络路径可能不同；采集与推理解耦能减少半截数据、半截分析、难复现的问题 | `collect-only` 产物包含不可变数据快照、chart/news sidecar、校验摘要和数据边界；主电脑可选择快照只跑 LLM/报告；文档说明同机分流与双机采集两种运行法 |
| P2 | 文档治理 | 文档归档与入口瘦身 | 根目录主文档仍可用，但 `docs/` 中多份 4 月旧审计/实验材料已不是当前事实，容易让后续 agent 误读 | 列出保留/归档/删除候选；历史材料优先移入 `docs/archive/` 并加索引；根目录通俗报告保留索引，避免散落文档互相抢入口 |

---

## 后续方向思考

这些不是当前施工清单。只有当它们被拆成明确完成标准后，才移入“当前待完成”。

### 核心推理

- 保持 L1-L5 context isolation 为硬红线：L1-L5 可以知道静态职责边界，但不能看到其他层本轮运行时数据、摘要、结论、候选跨层关系或 Thesis / Bridge 当前判断。
- Decision Semantics 改造应服务读者判断，而不是新增更多术语：最终报告要解释“市场已经定价了什么、什么还没解除、赔率和行动如何分层”。
- Bridge v2 的 typed map 继续强化字段质量：`typed_conflicts`、`resonance_chains`、`transmission_paths` 必须有具体 evidence refs、机制、反证和未解决问题。
- 自动字段质量扫描可以作为第二步，不应先于只读审计视图。先让人看清 agent 链路，再决定哪些检查值得自动化。

### 数据基础

- L3 仍是关键薄弱层：广度、集中度、point-in-time universe 和历史结构数据需要继续补源；不能用价格强弱替代内部健康度。
- 严格回测仍有长期升级空间：ALFRED first-vintage、财报 first-reported、point-in-time NDX universe 和 LLM 后验知识都已明示为限制，但尚未工程化解决。
- 新闻、浏览器、登录态工具和 sidecar 结果默认只做隔离观察或候选证据；未升级为正式数据源前，不得进入 L1-L5 evidence refs。
- yfinance 成分股代理在实时模式可做 sanity check，但不应承担高信任估值 regime 判断。

### 输出体验

- `brief` 是连续阅读报告；workbench 是看盘式探索页面；控制台是运行前配置面板。三者不要互相替代。
- Agent 输入/输出审计视图如果验证有效，可以成为最终报告的一种“审计层”：读者不只看结论，也能看到每个 agent 的输入边界、输出字段和下游消费。
- 图表应继续绑定 evidence refs。图表负责暴露位置、趋势、分歧和压力，不替代文字推理。

### 文档治理

- `NEXT_STEPS.md` 只放未完成和方向思考。
- `WORK_LOG.md` 只放已完成事实和验证结果。
- `ARCHITECTURE.md` 放长期原则和架构边界。
- `RUN_REVIEW_CHECKLIST.md` 放真实 run / 回测复盘流程。
- `DATA_COVERAGE_REVIEW.md` 放数据源覆盖、fallback、有效日期和置信度边界。

---

## 暂缓或边界

- OpenBB：暂缓整个平台接入，只吸收 provider metadata、coverage discovery 和数据治理思路。
- Trendonify：真实浏览器 sidecar 已落地；主链仍不硬绕 403，不静默退回 yfinance。
- 正式前端框架化：在 brief / console / workbench 信息架构稳定前继续保持 self-contained HTML。
- 新闻 LLM 解读：当前只做官方事件底账和事件-数据时间邻近连接，不做泛新闻情绪和摘要。
- 交易执行、组合建议、自动下单：不属于 vNext 当前范围。
