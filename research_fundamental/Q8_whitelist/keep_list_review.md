# 白名单保留清单 · 功能复审

> **状态横幅（2026-09-21 追加）：本文件的结论已并入 `白名单_终版.md`；明细证据（28 项常设检查逐项裁决、14 份历史 run 的拦截实绩）仍然有效，供抽查。**
>
> 本文是研究战役 Q8 白名单的第二轮复核交付物。第一轮（`component_inventory.md`）回答的是"结构健康"（谁依赖谁、有没有死代码）；本文回答老板不敢认的那一半——**功能复审**：这些组件做的事是不是新系统需要的、历史上真拦到过东西吗、边界有没有重叠漏洞。
>
> **复审刀**：`research_fundamental/answers/QE.md` 废物五问（第一性/道器/分界/成本/替代）。
> **基准**：`research_fundamental/Q8_whitelist/ideal_blueprint.md`（理想蓝图="该有的样子"）。
> **证据口径**：系统行为论断全部带 `文件:行号`；历史有效性另用两类硬证据——git 提交史与 14 份历史 run 的机器落盘 `persistent_checks_report.json`（落盘 JSON 是系统产出数据，不是 AI 成稿文档，符合任务书信任来源第二条）。查不到历史证据的标"未核实"。
> **只研究不改代码**：本文不改 `src/` 任何文件。

---

## 第一节 · 事件层整套（`src/event_research/`）

**一句话裁决：保留——功能上它正是蓝图要的样子，无功能冗余；唯一功能缺口（反向提问回路）在包外、蓝图已登记接管；对外接口全是文件契约加一个注入点，重建主编排器不会断。**

### 1.1 它做的事是不是新系统需要的：逐件对照蓝图

蓝图 2.0 第 3 段要求事件层并行线做"巡逻 → 出题官出题 → 调研员调研 → 事件卡 → 事件总结"，并注明"事件层是红队认证的健康器官，整套保留"。实测包内 12 个 Python 文件（2,339 行）+ hooks/（215 行）+ 2 份 md，逐件对得上：

| 蓝图要的 | 实况 | 证据 |
|---|---|---|
| 巡逻（软暂停圈题、当场调研、成果上架） | `sync_patrol.py`：终端/控制台两种圈题形态，回测整体跳过（时点纪律），成果两份落盘（run 内 artifact + 跨 run 研究架） | sync_patrol.py:331-480；时点纪律 358-361；上架 473-477 |
| 出题官（读对抗残局出题） | `topic_composer.py`：读 bridge 未解题 + 跨层开放题 + 终审主要矛盾 + 家里能力清单，产 0-2 份任务书；失败降级为空题单不炸主链 | topic_composer.py:82-120（输入面）、176-237（主流程） |
| 调研员（按议程自主调研外部世界） | `runner.py`：DSH 底盘 + persona.md 注入 + 锁 deepseek-flash；机械字段（治理行/议程 ID/采集时间）代码装配，不让模型抄 | runner.py:171-289；装配纪律 221-228 |
| 议程账本（三来源） | `agenda.py`：charter/gap/boss 三来源、append-only、编号永不复用 | agenda.py:8-12、25-29 |
| 缺口桥（任务书→候选议程） | `gap_bridge.py`：gap_ref=topic 哈希去重，老板关闭的题不复活 | gap_bridge.py:47-102 |
| （蓝图未点名但属边界治理）词表活化 | `term_activation.py`：机器只出候选、老板圈选、双账留痕 | term_activation.py:1-14、181-227 |
| 塔基"数字出生证"精神 | `reconcile.py`：每张卡的引文必须对回 session 抓取原文（3-gram 锚点 + 编辑距离，阈值 0.8 是老板 08-26 拍板）；`budget.py`+`hooks/budget_gate.py`：经费卡预扣硬停 | reconcile.py:203-239；budget.py:60-80 |
| 形制层金字塔 | `brief.py`：第一屏三行（变没变/本期判断/认错条件），代码装配不经模型 | brief.py:30-89 |
| 留痕位质检 | `narrative_check.py`：叙事数字核对只标黄灯不拦截（老板 08-24"避免乱拦"） | narrative_check.py:1-13、81-122 |

注意一件容易被误读的事：**蓝图菜单里的"事件卡/事件总结"两站不住在 event_research/ 包内**——它们是主编排器里的 AI 站（`_build_event_interpretation_cards` orchestrator.py:1851-2001、`_build_event_section_summary` orchestrator.py:2003-2156，见 Q6 审计第 5、6 站）。event_research/ 包是"主动调研"线（出题→巡逻→调研→对账），新闻主线聚类与跨层出题在 `src/event_narrative_ledger.py`（第二节对象）。三处合起来才是完整事件层，复审按这个分界理解，不把"包内缺事件卡站"当缺口。

### 1.2 功能冗余排查

包内无重复职能模块。唯一形似冗余的是 `narrative_check.py`（事件层叙事数字核对）与主链终审数字逐字核对闸（orchestrator.py:7034-7046）：两者都查"数字有没有依据"，但对象不同（事件层叙事 vs 终审判决），且形态恰好相反——事件层是**标注不拦**（黄灯随产物走，runner.py:245-251 注释），主链那道是**拦截位**且被蓝图判"故意放弃"（ideal_blueprint.md 4.1 表 orchestrator ⑤）。不构成冗余；事件层这个恰是蓝图认可的留痕位形态。

唯一结构瑕疵（component_inventory 6.5 已登记，本文复核确认）：`card.py:23-26` 反向 import `scripts/layer2_supplement_prototype/prototype_loop.py` 的校验器——src 依赖 scripts，校验器本体住在 src 外。蓝图表态"校验器内收"，复审无异议。

### 1.3 功能缺口排查

包内无缺口。蓝图 2.3 登记的反向回路缺口（事件层给数据层的题止步于裁决桌、没变成数据层家庭作业）产地在 `src/event_narrative_ledger.py:1088-1134`，不在本包；接管挂点（inquiry_router 等四个）component_inventory 6.5 已按现成程度排序，蓝图已接管。复审确认现状描述属实：`_build_cross_layer_questions` 产出带 `direction="event_to_data"` 标记的问题（event_narrative_ledger.py:1107-1115），消费端只有 IA 当场答与出题官当残局读（topic_composer.py:86、115）。

### 1.4 接口在重建主编排器时会不会断：逐个接触面实测

事件层对主编排器的接触面只有一处代码级依赖，其余全是文件契约：

1. **唯一的代码级接触面是 llm_caller 注入**：`main.py:884` 把 `orchestrator.llm_engine.call_with_fallback` 传给 `compose_topics`，`main.py:921` 同款传给 IA。重建编排器时，只要新器官仍暴露同签名的调用引擎，事件层不断；否则只需改 main.py 这两处接线。风险等级：低，且接线点就两处。
2. **runner.py 依赖外部包 deepseek_harness**（runner.py:200），不在 src 内，与编排器零耦合。
3. **文件接口全部与编排器实现解耦**：`research_topics.json`（topic_composer.py:38）、`event_research_patrols.json`（sync_patrol.py:44）、`output/event_research/research_shelf.json`（sync_patrol.py:49；IA 默认读它，integrated_synthesis_report.py:1582-1586）、`output/state_ledger/event_agenda.jsonl`（agenda.py:25）、词表三账（term_activation.py:22-24）。新编排器不动这些文件名与 schema，事件层无感。
4. **反向读者都在包外且与编排器无关**：control_service.py:22/37（老板圈词表）、news_event_ledger.py:25/30（采集读词表）、persistent_checks_b.py:1281-1286（PC-29 查三账）。
5. **调度位置**：事件层三个入口都由 main.py 调（main.py:24-26/44-46 导入、882-912 调用），不经 orchestrator。编排器重建天然不动它。

### 1.5 意外发现：三处注释与代码时序打架（文档纪律问题，非功能病）

- `sync_patrol.py:5-7` 说"出题和巡逻都在综合裁决之前……本次 IA 从架上取（含本次新巡逻的成果）"；同文件 `sync_patrol.py:46-49` 却说"同一 run 的 IA 来不及用（出题官必须看过 IA 残局才出题）"。两段注释互相矛盾。
- `integrated_synthesis_report.py:1580-1581` 注释说"IA 不再读本 run 的巡逻 artifact（出题官在 IA 之后才出题、巡逻更晚）"——括号里的时序理由在现行代码下不成立。
- 代码实况（以此为准）：main.py:882（出题）→ 892（巡逻）→ 916（IA），巡逻成果先上架（sync_patrol.py:473-477）再由 IA 从架上读（integrated_synthesis_report.py:1582-1586）——**本次巡逻成果本次 IA 能用上**，5-7 行的口径是对的，46-49 行与 IA 侧注释是 08-26 时序回摆前的残留。功能无恙，但三处注释足以误导下一个读代码的人，归建时顺手修。

---

## 第二节 · 契约台账（五个文件）

**一句话裁决：五文件全部保留——职责无一重叠，contracts.py 实测 80 个类零死类、没有只服务旧编排器的部分；两个真漏洞是"expectation_ledger 的判断消费者为零"和"读者出口契约面蓝图未表态"，都是登记事项不是删除理由。**

### 2.1 每个文件一句话职责

| 文件 | 行数 | 一句话职责 | 关键证据 |
|---|---|---|---|
| `src/agent_analysis/contracts.py` | 2,807 | 全部 AI 站输出与跨 artifact 的 pydantic 数据形状定义，加 LLM 边界宽容归一化校验 | 80 个类（枚举 6 + 模型 74）；文件头自述 1-16 |
| `src/state_ledger.py` | 318 | 跨 run 确定性状态变量台账（append-only JSONL，26 个状态键提取表 33-59），兼方法修正台账（含全仓唯一"查 git 提交真伪"的闸门 `_validate_method_revision_entry` 236-303） | 禁回流禁令内嵌 199-203 |
| `src/expectation_ledger.py` | 604 | 预期-兑现台账：从 vintage 档案与 packet 装盈利/利率/波动三本账，supporting-only 身份四条铁律锁死 | DOWNGRADE_RULES 20-25；入口 build/write 521/563 |
| `src/event_narrative_ledger.py` | 1,729 | 新闻主线聚类（四条主线各带"能说/不能说"边界，1168-1205）+ 跨层出题工厂（纯代码不调 AI，双向 direction 标记，上限 8 题） | `_build_cross_layer_questions` 1088-1134 |
| `src/news_event_ledger.py` | 1,455 | RSS 新闻采集与事件卡落盘（词表 overrides 与 M7 财报 blackout 日历的采集侧消费点） | import 25-31；官方源清单 56 起 |

### 2.2 职责边界：重叠与漏洞

**重叠：无职能重叠。** 五文件各管一摊——contracts 管内存里的数据形状，state_ledger 管跨 run 状态簿记，expectation_ledger 管预期兑现簿记，event_narrative_ledger 管事件主线与跨层题，news_event_ledger 管新闻采集。有一处**代码重复**（不是职责重叠）：append-only 台账的"读全部→折叠→追加"基建在 agenda.py:131-156、term_activation.py:49-69、state_ledger.py:213-233 各写了一遍。重建时可考虑共用台账基建，非必须，不拦重建。

另有一对容易误判为重叠的并行身份体系，实测不重叠：contracts.py 的 `InquiryMessageType`（106-120，数据层问询三类型，注释 114-116 明说 EVENT_CHALLENGE 已拆给二档研究部）与 agenda.py 的 `source` 枚举（27 行，charter/gap/boss，事件层巡逻三来源）——一个管数据层问询路由，一个管事件层议程入账，各守各的边界。

**漏洞一（真漏洞，登记）：expectation_ledger 的判断消费者为零。** 治理站消费已于 08-15 切断（orchestrator.py:5845-5848 注释"配餐单 v0"+喂空字典），配套摘要函数 `_pricing_expectation_ledger_summary`（orchestrator.py:5954-6043）已成死代码（component_inventory 死物 #8）；现在只剩 vnext_reporter.py:2715 的展示层读它。按 QE 第一问"没有它深度分析还能交付吗"，当前答案是"能"——但它是校准闭环"预期 vs 兑现"的建成前半截，老板 2026-09-20 裁决闭环延后、器官封存（ideal_blueprint.md 3.3），所以这是**封存状态的如实登记，不是删除候选**。重建时要防止顺手接通（蓝图 3.3 明令）。

**漏洞二（蓝图未表态的契约面，待裁决）：读者出口。** contracts.py 的 `UserDecisionProfile`/`UserDecisionCondition`（274-320）与 `GoldenPitChecklist`（321-362）是"读者出口翻译产物"的形状——orchestrator.py:1388-1401 自述"reader-exit translation artifacts only"，生产者 orchestrator.py:1012/4512，消费者 vnext_reporter.py:1938-1939/2931 起、run_review.py:513-551、state_ledger.py:162/187。蓝图形制层（三层楼）没有明确登记读者出口的去留。复审建议：归建前请总研究员把"读者出口保留/并入塔尖/放弃"列为待老板拍板项，契约面随决定走。

**非漏洞（澄清一个疑点）：contracts.py 内两个语义 validator 现状合规。** stance_label 方向冲突（2486-2494）与"缺失证据定方向"探针（2512-2536）已按 2026-08-31 T69 从 raise 降级为留痕不拦（注释链完整自述降级理由），与蓝图"意思层归提示词、代码只留痕"一致，不是残留的拦截闸。

### 2.3 contracts.py 2,807 行里有没有只服务旧编排器的部分

**实测结论：没有。** 逐类筛查方法：对全部 80 个类做全仓（src/scripts/tests）引用扫描，8 个"无外部功能引用"的类逐一复核，全部是契约内部嵌套字段类型——EventMechanismHypothesis 被 EventInterpretationCard:423 引用、QualitySelfCheck 被 LayerCard:945 引用（且其字段被 orchestrator.py:7164-7197 的法典覆盖度检查消费）、CrossLayerHook 被 IndicatorAnalysis:924 引用、IntegratedQuestionAnswer 被 IntegratedAdjudication:577 引用、CrossLayerClaim 被 BridgeMemo:1369 引用、TimeHorizonView/PortfolioAction 被 ReaderFinal:1783-1784 等三处引用、CritiqueItem 被 Critique:1956 引用。**零死类。**

最接近"旧编排器专属"的三组：AdjudicationHistory/AdjudicationChangeRecord（1259-1309，假说竞争史簿记形状，唯一生产者是 orchestrator.py:3096-3100/3463-3474）、SchemaGuardReport（2019，orchestrator 装配、main.py:932 消费）、ContextBrief（2694，orchestrator 层站上下文简报）。但它们定义的都是**落盘 artifact 的形状**，不是编排器内部实现——新编排器只要保留同名 artifact（蓝图流程层五段的产物清单不变），这些契约原样有效。真正只服务旧编排器的"合约"不住在 contracts.py，而是 orchestrator.py 内联的四源拼装合约（8066-8230，约 200 行）——那属 C 档重建范围，与本文件无关。

---

## 第三节 · 28 项常设检查逐项过 QE 五问

**一句话裁决：保留 22 / 改造 6 / 废除 0。历史有效性用硬证据说话：14 份历史 run 的机器落盘检查报告（红绿实绩）+ git 提交史 + 代码注释。**

### 3.0 证据基线与两条总判断

证据基线：`output/analysis/vnext/` 下 14 份 `persistent_checks_report.json`（c6_baseline_20260815 至 20260911_233648），逐项统计红绿实绩；git log 两文件共 23 次提交；红队点名的 PC-27 病例见 3.4。

两条总判断先行：

1. **28 项全是留痕位、只读 run_dir、单条异常不崩整包**（persistent_checks_a.py:136-147/939-943；persistent_checks_b.py:1348-1355），校验对象是落盘 artifact 契约而非编排器实现——这是它们集体过 QE 第一问与第四问的结构原因：不占拦截位就不烧 AI 调用，身份对账不误伤意思。
2. **但"留痕位"不等于"有信号价值"。** 实测发现两项检查已陷入 QE 第四环预言的"误报多到读报告的人学会无视"状态：PC-03 连续 6 个 run 因同一机械字段差异报红、PC-08 连续 6 个 run 因两家数据源 PE 合法分歧报红，均无人处理。这是本轮复审最重要的发现，详 3.3。

### 3.1 保留（22 项）

裁决口径：过五问——守的道能一句人话写出、手段是身份/计数对账（不读懂内容即可判）、留痕位成本近零、历史上有真拦截记录或属反回归锁。

| 编号 | 检查名 | 历史有效性证据 | 一句话理由 |
|---|---|---|---|
| PC-01 | critic/risk 分料身份 | 14 绿 0 红 | 风险哨兵论证盲（thesis_* 整键移除，orchestrator.py:374-386）的反回归锁；零误伤记录 |
| PC-02 | 治理站引用全集对账 | **2 次真红且都是近期**：20260911 final 缺引用 1 条、t70_glm_check 缺 9 条 | 仍在拦真装配缺口；注释自述收集了 counterevidence_refs 反证位（persistent_checks_a.py:235-263），是吃过 A2 病教训的检查 |
| PC-05 | 委托调查 vs 进 IA 报告数对账 | 12 绿；2 红均为 IA 缺席（见 PC-04 改造注） | 计数恒等式（委托数=非 stub 报告数+占位数，persistent_checks_a.py:661-663），纯身份对账 |
| PC-07 | 事件字段恒空（三明治反向断言） | 14 绿 0 红 | 三明治隔离的看门狗，罩 bridge/critic/risk/reviser/final 五站（persistent_checks_a.py:738-755）；零成本 |
| PC-09 | 约束/指令引用键存在性 | **2 次真红**（c6_baseline、t53：提示词点名 raw_data/NO_DATA_AVAILABLE 而 payload 无此键） | 拦过真病；近期全绿说明病愈，留作反回归 |
| PC-11 | 输出示例指标本层存在性 | **1 次真红**（c6_baseline：示例点名本层不存在指标 get_10y_real_rate） | 示例与层 payload 的身份对账 |
| PC-12 | manual_overrides 陈旧占位日期 | **1 次真红**（2022-01-04 占位，c6_baseline）+ 2 次误伤已修（git 0e5d81e：inactive 配置不带 date 键） | 误伤类已修，当前形态 11 绿 |
| PC-13 | percentile 0-1/0-100 混用 | **1 次真红**（c6_baseline：L1 双口径共存） | 数值域对账，带 unit/scale 声明豁免（persistent_checks_b.py:357-370），豁免设计已防误伤 |
| PC-14 | context_brief 日期 vs 指标日期 | **1 次真红**（c6_baseline：跨日不一致） | 时点纪律闸；disclaimer 子条查的是代码装配的模板文本（persistent_checks_b.py:461/479-481），属模板身份检查不是词表 |
| PC-15 | high_severity 容器 severity 枚举一致 | 14 绿 0 红 | 枚举身份检查 |
| PC-16 | 他站产物键/禁用标记进输入 | **1 次真红**（c6_baseline：C6 前形态 pricing_expectation_ledger 残留） | 递归键名身份扫描；注释已把两类合法标记排除在病定义外（persistent_checks_b.py:594-596） |
| PC-17 | bridge 冲突矩阵 A-M 行完整性 | **1 次真红**（c6_baseline：缺 D-M 九行） | 提示词模板完整性检查；提示词归建改模板时本检查需同步改（登记） |
| PC-18 | L4 数据陈旧 + 回购逐字重复行 | **1 次真红**（c6_baseline：AMZN 陈旧 592 天、MSFT 逐字重复行——正是 C3/C5 原案） | 数据层供给侧检查，阈值 365 天出处已写明（persistent_checks_b.py:50-53） |
| PC-19 | canon 名 vs 输入 metric_name | **1 次真红**（c6_baseline：canon 注册名与输入名多处不符） | 法典身份对账 |
| PC-21 | 事件站 output_contract 去重 | 13 绿 0 红 | B3 回潮锁 |
| PC-22 | 指标清单与 Runtime Input 去重 | 13 绿 0 红 | B6 回潮锁 |
| PC-23 | 高严重度冲突容器条目集一致 | **1 次真红**（t53：typed_conflicts 缺 3 条编号） | 集合恒等对账 |
| PC-24 | L3 持仓锚计数与滞后声明 | 13 绿 0 红 | 分名分账对账（持仓解析数 vs provider 总数不得裸并存） |
| PC-25 | supplier_lookback 待验证仍撑主斜率 | **13 红 0 绿——设计内常红**：docstring 写明老板 08-16 裁决"审核结论出来前不许悄悄转绿"，08-17 补验未通过（persistent_checks_b.py:1109-1115） | 这不是误报是债务标记；保留但登记观察：常驻红会稀释红色语义（详 3.5 注） |
| PC-26 | yield gap 身份锁（supporting_only） | 13 绿 0 红 | 老板 O13 裁决的身份锁，防回潮 |
| PC-28 | 抗诉通道亮灯三条件 | 8 绿 0 红；docstring 载 104 个历史 run 离线校准零误亮（persistent_checks_b.py:1191-1200） | 代码核验来源（对回 verified_cards 的 source_url）+ 模型判实质（materiality）的分工样板；QD 答卷认定的"全系统唯一承认数据层可能错"的通道，按设计少亮 |
| PC-29 | 词表活化三账一致 | 8 绿 0 红 | 三本账身份互查（term_activation.py:324-398），防静默增删；机制未启用时跳过不扰（persistent_checks_b.py:1301-1306） |

### 3.2 改造（6 项）

| 编号 | 裁决 | 五问落点与改造内容 |
|---|---|---|
| PC-03 | **改造** | 守的道真（final 只吃修订稿，08-16 重裁）。7 次红里 **6 次是同一慢性误报**：canonical 逐字节比对把代码装配字段 `hypothesis_ordinal` 的赋值时机差当供给回潮——20260911 实测两侧差异键只有 `hypothesis_ordinal`（终审侧 None vs 修订侧 1），正文全同；**1 次真红**（t70_glm_check 全 18 字段不一致，终审吃了旧稿）。分界之问不过：机械字段差异不是"final 没收修订稿"的充要条件。改造：canonical 比对前剔除代码装配字段（序号、时间戳），只比内容字段。 |
| PC-04 | **改造（小）** | 守的道真（IA 引用权限表不能大面积 unknown，A5 原病 67.6%）。unknown 占比本身 **0 次真红**——20260906 实测 0.0%（32 条），原病已愈；2 次红全是"IA 降级未裁决时找不到 prompt payload"（20260911 实测 `integrated_adjudication=None`，连 `prompt_audit/integrated_adjudicator/` 目录都没有）。同一缺席，PC-28 跳过记绿（persistent_checks_b.py:1218-1224）、PC-04/05 报红——三站口径不一。改造：IA 缺席时对齐 PC-28 跳过语义，把"缺席"与"占比超标"分成两个状态。 |
| PC-06 | **改造（拆子条）** | 主体保留：2 次真红（c6_baseline 材料块 JSON 不闭合、20260905 调查无材料块），git be972ce 载事件侧 artifact 断言"旧 run 实测抓得到"。词组子条不过第三问：`CI_FORBIDDEN_MATERIAL_TOKENS`（persistent_checks_a.py:55）里"不宜重仓""触发核心仓"两个词组是意思层规矩压成词表——误伤案例可构造：调查材料如实引用卖方原文"不宜重仓"四字即被打。改造：删两个词组子条，留字段名子条（dominant_side/action_implication 是身份检查）与全部结构子条。 |
| PC-08 | **改造** | 守的道真（同名指标同值唯一，A11"一处错处处错"）。9 次红 = **2 次真拦截**（OBV 跨窗口分叉 901260500 vs 493790400，直接促成 O10 窗口对齐修复，git fa442cc）+ **7 次慢性误报**：HoM/Bloomberg 口径 PE 28.1 与 Wind 口径 PE 30.41 是两家数据源对同一概念的合法分歧——20260911 实测两条 core_signals 分属 `get_ndx_pe_and_earnings_yield` 与 `get_ndx_wind_valuation_snapshot`，各有独立来源身份。按裸键名跨指标跨源归一比对（persistent_checks_a.py:38-47/762-784），不是"同指标同窗口多值"的充要条件。改造：比对范围收窄到同 function_id/同源同窗口；跨源分歧若要保留观察价值，改成单独的信息项不计红。 |
| PC-10 | **改造（拆子条）** | 两条反向断言保留：旧 A 硬规定回潮拦过 1 次（t54_confirm_r3）、旧 B 元话语矛盾对拦过 1 次（c6_baseline），都是对历史错误措辞的身份比对。正向子条不过第三问："未含统一的来源限定语义"即判红（persistent_checks_a.py:898-900/912-913）是词表冒充语义要求——误伤案例可构造：提示词换一套同义措辞教同一纪律（比如"弱来源标注出处性质"）即被打；漏检案例同样可构造：含了规定措辞但没真教纪律照样过。改造：删正向子条或降级为纯观察。 |
| PC-20 | **改造（三拆）** | 三合一拼盘，三个子条三种命运：①ESS 输入卡带 needs_data_confirmation——artifact 形状检查，保留。②重试反馈含真实定位——6 次红里混着传输类错误（20260831："bridge received empty response"），这类错误天然没有字段路径可给，正则指纹清单（persistent_checks_b.py:62-70）覆盖不了它；改造：传输类/空响应类反馈进豁免清单。③`tests/test_context_spread.py` 收集数 ≥15（persistent_checks_b.py:910-919）——这是仓库健康检查混进了 run 产物检查，QE 第五问归 CI 测试套件守，从 run 检查包拆除。 |

### 3.3 废除（0 项）与为什么一个都不到废除线

28 项没有一项够 QE 废除档：废除要求"第一问答'能'+无人接手"，而这 28 项全部只读落盘产物、互不崩、不占拦截位，废除它们省不下任何 AI 调用成本，只会拆掉反回归锁。最弱的两条词表子条（PC-06 词组、PC-10 正向）走改造出口，规矩移交提示词原则，不悬空。

**本轮最重要发现（单独登记）**：PC-03 与 PC-08 的慢性误报是 QE 第四环预言的实锤——留痕位检查连续 6 个 run 报同一模式的红、无人处理，读报告的人已经学会无视它们。结构健康（红队已判）不等于功能有效；保留清单里躺着"曾经立功、如今失灵"的检查，这正是老板不敢只凭结构健康认清单的直觉的证据。两条的改造都只需收窄比对口径，不需要动守的道。

### 3.4 PC-27 病例复核（红队点名，任务要求逐项核实）

代码注释自述（persistent_checks_b.py:1184-1188）：O17 原意"事件挑战数据判决才亮灯"，但实现点在 `challenged_by_data`——该枚举的真实语义是"数据削弱事件叙事"，**方向装反，自 08-19 落地起从未按原意生效**；08-27 退役、编号永不复用；异议通道由 PC-28 正确承接。git log 佐证：`59f05e6`（O17 新增 PC-27）→ `51e1398`（PC-27 退役+防复活断言）。14 份历史报告里 PC-27 仅出现 1 次且为绿——与"从未按原意生效"的自述一致。**核实结论：病例属实，退役处置正确，PC-28 的三条件分工（代码核验来源+模型判实质）是对该病例的正确修法。**

### 3.5 两条登记注

1. **PC-25 的常驻红**：老板明文裁决"不许悄悄转绿"，复审不动它；但如实登记——常驻红与 PC-03/PC-08 的慢性误报叠加，会让"红"在报告里整体贬值。重建时建议把"数据债务登记"与"pass/fail 对账"分两栏展示，债务标记不计入红灯总数。此属展示层建议，不动检查本体。
2. **`persistent_checks_report.json` 在 src 内没有代码读者**（component_inventory 6.4 实测，本轮复核确认属实）：28 项检查的产出仅供人读。留痕位设计如此，不是删除理由；但 3.3 的慢性误报问题之所以 6 个 run 无人发现，恰因无人读。重建时给报告配一个聚合展示位（或接入看板），比改检查本身更治本。

---

## 第四节 · AI 站合并候选分析（老板新立原则）

**一句话裁决：按老板三判据逐对排查，13 类站里合并候选为 0 对——现有站间边界几乎全部有对抗职能或隔离纪律撑着；必须隔离的对子 7 组登记在案，其中 counter_thesis × risk 是"看似可合、实则时序互斥"的迷惑对，重点防误合。**

### 4.0 判据与排查方法

老板判据：两个站若 **(a) 上下文构成实质相同、(b) 互相看见对方产物无害、(c) 无对抗职能**，三条件同时满足才具备合并条件。

排查方法：13 类站（Q6 审计清单：L1-L5 层分析师 ×5、bridge、受控调查 ×N、counter_thesis、事件卡解读 ×N、事件总结、thesis、critic、risk、reviser、final、IA、IA 批评者+定稿）按上下文来源分四组——层内五站、主链治理链、事件侧、IA 桌。78 个对子不一一铺陈，先过隔离红线筛（撞红线的直接落"绝不能合"），幸存对子再查三条件。同站型多实例（事件卡 ×N、调查 ×N）按"实例间合并"单列一查。

### 4.1 必须隔离、绝不能合的对子（7 组，带依据）

| # | 对子 | 依据 |
|---|---|---|
| 1 | **thesis × counter_thesis（正反方，典型）** | 对抗职能本体：反方的存在就是为了造最强反对解释（Q2 第五环"多空必须同一份菜单"）。隔离有代码审计：counter_thesis 禁读 thesis_draft/analysis_revised/final_adjudication（orchestrator.py:3309-3339）。且时序互斥：假说竞争跑在 thesis 之前（orchestrator.py:714 vs 743），ThesisDraft 契约含 hypothesis_responses 逐条回应字段（contracts.py:1810 起）——thesis 的产品形态就建立在"回应已存在的假说"上 |
| 2 | **L1–L5 两两（10 对）** | 宪法级层间隔离（AGENTS.md 常驻边界第一条"L1-L5 运行时上下文不得互通"）；Q6 审计实测 payload 不含他层任何东西（orchestrator.py:1221-1241），隔离是提示词+payload 双重保证。合并任意两层 = 拆干扰项的物理拆除被撤销（Q6 C3） |
| 3 | **主链治理链五站 × IA/事件侧任意站** | 三明治隔离：bridge/critic/risk/reviser/final 的事件字段恒空有常设检查罩着（PC-07，persistent_checks_a.py:738-755）；事件材料唯一合法入口是 IA 那张桌（Q5"全身只留一张汇合桌"）。合并 = 事件材料绕桌直入数据主链 |
| 4 | **thesis × critic、critic/risk × reviser、reviser × final（反馈链相邻站）** | 合并任一相邻对 = 让模型在没有外部反馈的情况下自我纠正，Q6 特性六实证（Huang et al. ICLR 2024）判这条路不可靠甚至越改越错；系统的有效回路恰是"外部校验器/外部批评给具体意见 → 带材料重写" |
| 5 | **critic × risk** | 同包异盲：两者共用治理输入构造器，但 risk 刻意论证盲——thesis_* 字段序列化时整键移除（orchestrator.py:374-386），提示词明示"不得脑补一个论点出来攻击"（prompts/risk_sentinel.md:30，经 Q6 审计引述）。合并即毁掉盲区设计（风险哨兵被论据说服即失去独立判断）；PC-01（persistent_checks_a.py:196-228）就是这条分料身份的看门狗 |
| 6 | **IA × IA 批评者 × IA 定稿（三者两两）** | 同一桌内的作者-批评者-定稿三角；批评者拿草稿+同一输入面核对"草稿 vs 材料"（integrated_synthesis_report.py:487-555），合并任一对都退化为自我纠错，同 #4 的 C6 依据 |
| 7 | **counter_thesis × risk（迷惑对，重点登记防误合）** | 表面极像合并候选：两者都是"不见 thesis 论证的反对派"，上下文构成在 Q6 瘦身落地后会收敛（结论面+冲突面+证据菜单），互见无害、彼此之间无对抗职能——三条件看似全过。**但时序互斥**：counter_thesis 必须在 thesis 不存在时出题（假说先于论点，thesis 逐条回应）；risk 必须评估已存在的结论——"什么会让我们错"里的"我们"是 thesis（蓝图 2.1 风险哨兵菜单"结论与数据面"）。一个要求 thesis 尚不存在，一个要求 thesis 已经存在，物理上不能同站。判据 (a) 在时序维度不成立 |

### 4.2 合并候选对（三条件全过）：0 对

逐组排查结论：

- **层内五站**：撞隔离红线（4.1 #2），免谈。
- **主链治理链**：thesis/counter_thesis/critic/risk/reviser/final 六站之间的关系不是对抗就是反馈链相邻或刻意异盲（4.1 #1/#4/#5/#7），无一幸存。
- **事件侧**：出题官（读残局出题）与调研员（按议程调研）时序先后、上下文完全不同；事件卡（一次一件事，12-20K）与事件总结（看全部压缩卡）合并会让逐卡解读看见其他事件——C3 交叉污染，条件 (b) 不过。
- **IA 桌**：4.1 #6。
- **跨组**：全部撞 4.1 #3 的三明治红线。
- **同站型多实例合并**（事件卡 N 张并一次调用、调查 N 个委托并一次调用）：各实例上下文不同（条件 a 不过），互见即污染（条件 b 不过），且受控调查的 12K 字符硬顶（orchestrator.py:2633/2642/2654）是全场体量控制样板（Q6 第 3 站"大致得当"），合并即拆样板。不合。

### 4.3 给老板的含义

站数减不了——13 类站的边界不是架构洁癖，是对抗职能、隔离纪律、时序依赖三样真东西撑着的。若目标是减负，正确方向是 Q6 已开出的**菜单化瘦身**（counter_thesis 32.4 万字符、thesis 30.2 万、bridge 13.8 万、reviser 20.3 万，证据索引全量换证据菜单），不是并站。合并这条路在现有站划上走不通，硬走会拆掉的恰是对抗与隔离这两个产生判断质量的机关。

---

## 附：本次复审的证据文件清单

- 源码锚点：全部 `文件:行号` 内联于上文，行号以本次复审工作区为准。
- 历史红绿实绩：`output/analysis/vnext/` 下 14 份 `persistent_checks_report.json`（c6_baseline_20260815 至 20260911_233648），逐次红绿与 detail 摘要在第三节 3.1/3.2 表中浓缩。
- git 提交史：`be972ce`（PC-06 拆洞加牙）、`c5c194b`（PC-10 误伤修复）、`e95672e`（PC-21~26 补病）、`54e72d6`（T53 验收 4 项 PC 红修复）、`0e5d81e`（PC-12 误伤修复）、`fa442cc`（O10：OBV 窗口对齐，PC-08 真拦截促成的修复）、`00b463e`（PC-28 上线）、`51e1398`（PC-27 退役、PC-29 上线）。
- 未核实事项：PC-01/07/15/21/22/24/26/28/29 九项历史上零红灯，"拦到过东西吗"的答案是"没有实证拦截记录"——它们的价值定位是反回归锁（病愈后防复发），此定位已在 3.1 逐条注明，不靠编造拦截史撑腰。
