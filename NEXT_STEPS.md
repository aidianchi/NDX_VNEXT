# vNext 下一步

更新日期：2026-07-10（完成 L1-L5 数据与推理链第一性原理审计后更新）

阅读方式：本文件只记录两类内容：

1. 当前仍未完成、需要后续执行的事项。
2. 尚未排进施工队列、但值得保留的后续方向思考。

已经完成的事项不在这里维护，统一看 `WORK_LOG.md`。架构原则看 `ARCHITECTURE.md`，运行复盘看 `RUN_REVIEW_CHECKLIST.md`，数据边界看 `DATA_COVERAGE_REVIEW.md`。

## 当前状态锚点

2026-07-11 用户决策：**解除 2026-07-07 宣布的架构冻结**；北极星改写为"做出可靠的 NDX 投资判断，并让判断质量随时间可测量地变好"（见 CLAUDE.md / PRODUCT.md，可审计推理链降为手段）。依据：五路第一性原理体检（报告见 `investigation_reports/20260711_first_principles/`）。新施工路线按优先级：

1. U1 证据敏感性扰动实验：检验"改了证据数字，结论会不会变"——结果将重排后续优先级。
2. Codex 未提交改动分包审核，逐包提交（checker 闸门包已于 2026-07-11 审核+回放验证后提交）。
3. 校准闭环通电：live run 也产出 claim 打分并落盘台账；数据层验收前打分仅作数据问题探测器；跨 run 展示层仍等运行质量稳定后解锁。
4. 证据菜单再平衡：补 AI 资本开支周期代理、利率预期路径、波动率期限结构、回购/财报日历；做多空证据源对称性审计。
5. 独立重算校验带：每个派生数字（分位/增速/比率/单位）用第二条独立路径重算，容差外自动报警并入闸门。
6. orchestrator / tools_L4 巨型文件分模块手术；砍除恒零产出的受控调查子系统与死代码链（tools.py/finnhub/simfin）。

---

## 当前待完成

| 优先级 | 类别 | 待办 | 为什么重要 | 完成标准 |
| --- | --- | --- | --- | --- |
| P0 | L4 盈利预期 | 取得 Wind point-in-time 指数级 NTM/FY1 真实数据并做 live 验收 | 接入契约、同口径修正斜率、历史日期/财年防混淆门槛和测试已于 2026-07-10 完成；但 Wind 标准指数接口本轮对历史时点一致预期返回“没找到数据”，不能声称已生产可用 | 与 Wind 确认 NDX.GI 可用的确定性字段代码/导出表和历史观察日语义；真实返数后必须通过相同 horizon、相同 fiscal period end、有效日不越界、30/90 日快照和分析师覆盖审计 |
| P0 | 历史回测 | 禁止历史成分源失败后退回当前成分名单 | 当前名单会把后来入选或存活的公司带回历史，形成幸存者偏差；这是 point-in-time 红线，不是普通降级 | 历史 universe 不可用时明确 unavailable；只接受目标日当时可见的正式快照，并记录快照日期、与目标日间隔和成分变动 |
| P0 | 证据权限 | 字段级 `MetricAuthority` 进入 Evidence Passport 与 Claim Ledger（正在修、待验收） | 同一来源里的 PE 可以是主锚，定义未核实的 RiskPremium 只能辅助；若权限只停留在原始 payload，具体 claim 仍可能借同来源其他字段越权 | 每条 claim 引用到具体字段；`core_allowed` / `supporting_only` / `rejected` 在 claim gate 生效，并有 Wind PE 与 RiskPremium 混合场景测试 |
| P0 | 全链验收 | 用最新代码完成 fresh vNext E2E | 7 月 10 日后的修复只有 collect-only 或聚焦测试；最新完整 vNext 仍是 7 月 9 日旧代码，不能用来追认当前发布质量 | 同一 fresh snapshot 贯穿 packet、L1-L5、Bridge、Final 与报告；人工核对发布状态、主要结论、支持证据、反证、失效条件和未解决张力 |
| P1 | 使用期 | 历史回测 fresh run 验收 claim 打分器 | 7/7 审核遗留使用期事项①：claim outcome 打分器（T+20/60/120 verdict）只做过离线烟测，未经真实历史回测 run 验收真实判定质量 | 选一个历史回测日跑完整两段式 run，`claim_outcome_scores.json` 产出非空且 verdict/scoring_evidence 经人工抽查合理；不可评分项如实标注原因 |
| P1 | 使用期 | 用户确认个人决策档案阈值 | 7/7 审核遗留使用期事项②：`config/user_decision_profile.json` 的买入/卖出 metric_predicates 阈值仍是草案，未经用户逐条确认 | 用户逐条确认或修改阈值；黄金坑清单条目状态判定以确认后的谓词为准 |
| P1 | 数据基础 | L3 广度、集中度和稀疏日修复做 live 验收 | 稀疏日选择、内部缺口定向补抓、run cache 清理和三个广度算法已经修复并通过模拟测试；但尚未证明真实网络环境下能把目标日补齐 | fresh collect 中逐项记录目标日覆盖、实际采用日、补抓成功/失败和排除原因；A/D、% Above MA、新高新低、McClellan 不因单个稀疏日整列归零 |
| P1 | L4 外部校验 | History of Market 低样本分位做 live 展示验收 | 代码已要求 trailing 至少 200 点/270 天、forward 至少 60 点/约 4.5 年；不足时撤回分位，但尚未在 fresh 完整报告中检查展示 | fresh run 中 trailing 低样本显示 `insufficient_history` 且无伪分位；forward 的观察日、API 更新时间、freshness 和样本跨度分别展示 |
| P1 | 发布治理 | DataIntegrity 从函数计数升级为证据家族计数 | L5 的 11 个函数共用同一套 QQQ OHLCV，却被计成 11 项独立成功；总分会高估证据多样性 | 按政策利率、名义利率、真实利率、信用、广度、估值、价格行情等证据家族验收；同源派生函数共享家族权重；报告同时展示函数可用率与证据家族覆盖率 |
| P2 | 使用期 | 日常 `--official` run 攒 claim 台账 | 7/7 审核遗留使用期事项③：跨 run 展示层（跨 run diff、打分汇总）需要 ≥5 条真实台账才解锁 | 累计 ≥5 个带 `claim_outcome_scores.json` 的正式 run；期间不新增展示层功能 |
| P2 | 输出体验 | 术语悬浮/点击解释层 | 用户 2026-07-08 确认：英文指标名（HY OAS、ADX、MACD、ERP）希望点击/悬浮弹出通俗解释，而非全文中文化；报告已有证据抽屉交互可复用 | 指标术语字典（是什么、回答什么问题、怎么误读）；正文术语可点击弹层；桌面+移动检查通过 |
| P2 | 数据基础 | 上游产物粒度修复（2026-07-08 报告进化时发现） | ① `golden_pit_checklist.json` 生成阶段把全量 evidence_refs 和反证整包写进每个条目，条目间无区分，报告层只能做共用块兜底；② `event_mechanism_report.json` 新闻正文片段在小数点处截断（如"利率在3。"），且主线归类偏机械（结构事件被归入折现率线） | checklist 每条只携带真正相关的 refs 和反证；新闻片段改为句边界安全截断；主线归类错误率经抽查下降；报告层共用块兜底逻辑可随之简化 |
| P2 | 输出体验 | 研究控制台重做为简洁用户启动器 | 控制台仍把运行启动、开发命令、人工数据、sidecar、产物索引混在一页；用户真正需要的是选运行模式、是否回测、是否收集新闻，然后开始并看状态。计划见 `docs/2026-06-16_RESEARCH_CONSOLE_SIMPLIFICATION_PLAN.md` | 主界面只保留完整运行/仅收集数据/用已有数据分析、末次数据摘要、是否回测、收集新闻材料、开始运行、状态、最新报告/workbench/日志入口；桌面和 390px 手机宽度检查通过 |
| P2 | 数据基础 | 采集机 / 快照模式审计痕迹收尾 | `--collect-only`、`--data-json`、控制台入口已存在并在回测中实跑过；剩余是"同一数据快照贯穿采集、分析、报告、复盘"的审计痕迹补齐 | 一轮真实两段式 run 验证：分析阶段只消费同一快照；`run_summary.json`、brief、Prompt Inspector、Run Review 都能清楚显示用了哪份快照、采集时间、有效日期、跳过项和缺口 |
| P2 | 文档治理 | 文档归档与入口瘦身 | `docs/` 中多份 4 月旧审计/实验材料已不是当前事实，容易让后续 agent 误读（本文件重写是该项的一部分，docs/ 归档仍未做） | 列出保留/归档/删除候选；历史材料移入 `docs/archive/` 并加索引；根目录通俗报告保留索引 |

---

## 后续方向思考

这些不是当前施工清单。只有当它们被拆成明确完成标准后，才移入"当前待完成"。

### 核心推理

- L1-L5 context isolation 是硬红线：L1-L5 可以知道静态职责边界，但不能看到其他层本轮运行时数据、摘要、结论、候选跨层关系或 Thesis / Bridge 当前判断。
- Decision Semantics 字段已齐（主要矛盾、价格反映、赔率、动作层）；后续重点是 fresh run 里的表达质量和一致性，防止"字段填了但读者结论退回口号"。
- Prompt Inspector 是审计主入口；可补语义级下游追踪，但不应恢复大块正文审计。
- 冻结期后如重启施工，先重读 7/7 独立审核记录（WORK_LOG）再定路线。

### 数据基础

- L3 稀疏日与补洞代码已经修复，但仍是待 live 验收的关键层；不能用价格强弱替代内部健康度。
- 严格回测长期升级空间：ALFRED first-vintage、财报 first-reported、point-in-time NDX universe、LLM 后验知识均已明示为限制，未工程化解决。
- 新闻、浏览器、登录态工具和 sidecar 结果默认不得进入 L1-L5 evidence refs；外部叙事走三层研报结构（已落地），不回流纯数据链。
- L4 以 Wind NDX 指数级估值为主锚；Wind RiskPremium 在公式、单位和字段定义核实前仅作辅助。Damodaran、WorldPERatio、yfinance/Yahoo/SEC 保留背景、参照和对照校验角色。

### 输出体验

- `brief` 是连续阅读报告；workbench 是看盘式探索页面；控制台是运行前配置面板。三者不互相替代。
- 用户阅读画像（2026-07-08 确认）：桌面大屏通读完整判断书；L1-L5 底稿经常看（保持深度）；审计区几乎不看（维持最小）；术语要悬浮/点击解释。形态决策以此为准。
- 图表继续绑定 evidence refs；图表负责暴露位置、趋势、分歧和压力，不替代文字推理。

### 文档治理

- `NEXT_STEPS.md` 只放未完成和方向思考；`WORK_LOG.md` 只放已完成事实和验证结果；`ARCHITECTURE.md` 放长期原则；`RUN_REVIEW_CHECKLIST.md` 放复盘流程；`DATA_COVERAGE_REVIEW.md` 放数据源覆盖与边界。
- 本文件每次勾掉/新增条目时同步更新"更新日期"；发现与 WORK_LOG 矛盾时，以 WORK_LOG 的完成事实为准并立即修正本文件。

---

## 暂缓或边界

- 架构冻结已于 2026-07-11 由用户解除；新增阶段/artifact/合约改动回到"先审后并"的正常纪律，不再一刀切禁止。
- OpenBB：暂缓平台接入，只吸收 provider metadata 和数据治理思路。
- Trendonify：浏览器 sidecar 只作审计附件；不得进入 L1-L5 raw prompt、主证据、分位选择或当前来源投票。
- Legacy Agent IO Audit 复杂化：不再作为正文主路线；Prompt Inspector 是审计主入口。
- 正式前端框架化：brief / console / workbench 信息架构稳定前继续 self-contained HTML。
- 新闻 LLM 解读：只做官方事件底账和事件-数据时间邻近连接；泛新闻情绪与摘要由三层研报结构承接。
- 交易执行、组合建议、自动下单：不属于 vNext 当前范围。
