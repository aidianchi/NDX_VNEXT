# 事件层与校准闭环源码取证地图（Q-D / Q-F）

取证范围：`src/event_research/` 全部、`src/agent_analysis/outcome_scoring_runner.py`、`outcome_review.py`、`run_review.py`、`src/expectation_ledger.py`、`state_ledger.py`、`event_narrative_ledger.py`、`news_event_ledger.py`，以及所有消费这些产物的下游代码。本文每个论断都带 `文件:行号`。

**名词对齐（先立尺，防止后文混淆）**：代码里"事件层"其实是两套独立子系统。

- **新闻事件层**：`news_event_ledger.py` 用 RSS 采集官方/媒体/社媒新闻（`src/news_event_ledger.py:56-110`），`event_narrative_ledger.py` 把新闻聚成"主线"、出题、落盘 `cross_layer_questions.json` 等八个产物（`src/event_narrative_ledger.py:1362-1401`）。
- **DSH 二档巡逻**：`src/event_research/` 是用 DeepSeek Harness（dsh）底盘搭的自主小 agent，老板命题后它自己上网搜、抓、写材料卡。这就是任务书说的"自造的 DeepSeek 自主小 agent 框架"。
- **IA**（Integrated Adjudicator，第三层综合裁决人）：`src/integrated_synthesis_report.py` 里的 `_llm_adjudication`，提示词在 `src/agent_analysis/prompts/integrated_adjudicator.md`。

---

## 1. DSH 全图：这个自主 agent 怎么运转

### 1.1 一句话画像

DSH 是一个"带镣铐的临时调研员"：老板（或宪章）出一道题、给一张 token 经费卡，它用 deepseek-flash 自主搜索抓网页，交出一叠带"出生证"（每条事实必须指回某次抓取原文）的材料卡和一段层内结论，机器事后逐条对账，产物以"候选材料"身份流向第三层对质，永远不进数据主链（红线写在 `src/event_research/__init__.py:6` 和 `src/event_research/runner.py:274`）。

### 1.2 议程从哪来（出题口）

议程账本：`output/state_ledger/event_agenda.jsonl`，只追加不改写（`src/event_research/agenda.py:25`、`agenda.py:125-128`）。

三个来源，初始状态不同（`agenda.py:41`）：

| 来源 | 含义 | 初始状态 | 代码位置 |
|---|---|---|---|
| `charter` | 宪章常备巡逻职责 | active（即跑） | `agenda.py:8-11` |
| `gap` | 出题官从主链残局酿的课题 | candidate（老板圈选后才激活） | `agenda.py:39-41` |
| `boss` | 老板临时命题 | active | `agenda.py:11` |

`gap` 来源的实际链路：主链 run 收尾时出题官 `topic_composer.compose_topics` 读"六站对抗残局"（bridge 未解问题 + 跨层开放题 + 最终判决主要矛盾 + 家里数据能力清单）写 0-2 份研究任务书，落盘 `research_topics.json`（`src/event_research/topic_composer.py:82-120`、`176-237`）；缺口桥 `gap_bridge.harvest_gap_candidates` 把任务书转成候选议程，用 `gap_ref=topic:<标题哈希>` 去重（`src/event_research/gap_bridge.py:47-94`）。**注意**：出题官读的是 IA 之前的产物（`topic_composer.py:83-88` 读 `final_adjudication.json`、`bridge_0.json`、`cross_layer_questions.json`、`event_layer_summary.json`、`evidence_registry.json`），老板 08-26 裁决"出题和巡逻都在综合裁决之前"（`topic_composer.py:9-11`）。

出题官有过一次失败重构：旧版把 `needs_data_confirmation` 等内部钩子直接搬进题库，08-26 真实 run 把 20 条"家里数据能答"的内向题端给老板被当场否决，现已废除旧货源，只收出题官判过"家里答不了"的课题（`gap_bridge.py:6-12`）。

### 1.3 怎么花钱（经费卡）

- 卡面额度：默认 3000 万 token（`agenda.py:22-23`）；同步巡逻场景用日常档 300 万（`src/event_research/sync_patrol.py:59-61`）。
- 查账方式：`budget.fold_usage_from_transcript` 遍历 dsh session 落盘日志里的 `assistant/message` 事件，把 input/output/cacheRead/cacheWrite 四类 token 求和（`src/event_research/budget.py:20-57`）。dsh 自己的 tokenMeter 只管单次请求上下文压力，累计账由本模块自己 fold（`budget.py:10-12`）。
- 硬停机制：dsh 每发一次模型请求前经过 Python 钩子 `hooks/budget_gate.py`，超额即 exit 2 硬停，请求根本不发出去（`src/event_research/hooks/budget_gate.py:21-36`）。
- 耗尽后果：已采材料照常落盘，`run_summary` 标 `budget_exhausted=true`，产物算"半成品"（`runner.py:238-239`、`runner.py:271`）。

### 1.4 跑一条议程的完整流程

入口 `runner.run_agenda`（`src/event_research/runner.py:171-289`），逐步：

1. 查议程状态，只跑 active（`runner.py:177-181`）。
2. 建 run 目录 `output/event_research/runs/<agenda_id>_<时间戳>/`，写 `budget.json` 卡面（`runner.py:183-191`）。
3. 渲染 dsh 组合：`cordis.yml.tmpl` + `hooks.json.tmpl` 按 run 填绝对路径（`runner.py:53-63`）。组合内容：dsh 官方 SDK 的 agent 骨架 + deepseek LLM + session JSONL 持久化（明文不压缩，供对账器逐行读）+ web 搜索/抓取 + Python hooks 桥（`src/event_research/dsh_profile/cordis.yml.tmpl` 全文）。
4. 注入人设：`persona.md`（四条纪律：事实/解读分离、来源分级、时间纪律、承认不知道）+ 本次议程（`runner.py:66-74`；`persona.md` 全文）。
5. G2 跟踪名单：议程带 `tracking_key` 时，把同一 key 最近一次巡逻的 narrative_state 作为"上期坐标"喂进 prompt，本期必须更新同一口径并写差异（`runner.py:77-97`、`100-112`）。这是事件层唯一的"跨 run 同口径序列"机制。
6. 锁 `deepseek-flash` 跑（`runner.py:48`、`204-214`）。
7. 解析产出：取最后一条消息里的最后一个 ```json 块，要求含 `cards` 键；解析失败也收下原文（`runner.py:158-168`）。
8. 机械字段代码装配：`governance_note`、`agenda_id`、`collected_at_utc` 一律代码回填，不让模型写（`runner.py:221-227`；注释说这是实测教训——模型抄 30 位随机编号能编得以假乱真）。
9. 机器校验三连：材料卡四镣铐+出生证形状 `validate_research_card`（`runner.py:228`）；层内结论块字段齐全 `validate_narrative_state`（`runner.py:126-142`）；判断段数字必须能在证据卡里找到 `check_narrative_numbers`（`runner.py:246`，纯黄灯标注不拦截，`src/event_research/narrative_check.py:1-13`）。
10. 对账：`reconcile_cards` 把每张卡的 `source_pointer`（url+quote）对回 session 日志的 web_fetch 抓取记录（`runner.py:237`；算法见第 4 节）。
11. 落盘：`material_cards.jsonl`、`narrative_state.json`、`brief.md`（金字塔简报，第一屏三行：变没变/本期判断/认错条件，`src/event_research/brief.py:30-89`）、`run_summary.json`（`runner.py:241-281`）。
12. 账本记 done（`runner.py:283-288`）。

**重要口径**：二档没有发布闸门——老板 08-25 裁决"闸门既然乱拦就不要有"，一切机器校验都是标注层随产物走，不存在"不可发布"状态（`runner.py:248-251`）。

### 1.5 产物写到哪、谁消费

| 产物 | 位置 | 消费者 |
|---|---|---|
| 单次巡逻全套产物 | `output/event_research/runs/<id>_<ts>/` | 对账器、简报 |
| `event_research_patrols.json` | 主链 run_dir 内 | 本次留痕（`sync_patrol.py:44`、`372-378`） |
| 研究成果架 `research_shelf.json` | `output/event_research/research_shelf.json`，跨 run 累积、最多 20 条 | **IA 的唯一巡逻材料来源**（`sync_patrol.py:49-50`、`213-242`；消费处在 `src/integrated_synthesis_report.py:1580-1586`） |
| `brief.md` | 巡逻 run_dir | 老板 |

消费端过滤在装配时做：对账通过的卡入 `verified_cards` 可当事实，降级卡入 `downgraded_cards` 只带"仅解读"资格、各带原因码（`sync_patrol.py:143-210`，消费规则明文写在 `sync_patrol.py:204-208`）。

---

## 2. 对质点取证（Q-D）

### 2.1 结论：唯一对质点真实存在，且基本唯一

事件层两套产物进入综合裁决的**确切位置**是同一个函数：`IntegratedSynthesisReportBuilder._llm_adjudication`（`src/integrated_synthesis_report.py:288` 起），由 `build()` 在第 219 行调用；主链调用点在 `src/main.py:916-922`（`write_integrated_synthesis_report`，带真实 `llm_caller`）。提示词 `src/agent_analysis/prompts/integrated_adjudicator.md:3-7` 自述三件任务：把数据判决和外部世界放进同一张桌子对质、逐条回答事件给数据层出的题、写综合判决正文。

进入 IA 的事件侧数据形态（`integrated_synthesis_report.py:380-397` 的 prompt payload）：

- `event_research_patrols`：DSH 巡逻成果，读自跨 run 研究架 `research_shelf.json`（`integrated_synthesis_report.py:1580-1586`），按本轮 effective_date 做时点过滤，晚于该日期的条目对本次"不存在"（`integrated_synthesis_report.py:181-192`）。
- `event_interpretation_cards`：新闻事件解读卡，由编排器在 run 内用 `event_card_interpreter` 站逐条生成，上限 10 张（`src/agent_analysis/orchestrator.py:729-733`、`321`、`1851-1910`）。
- `event_layer_summary`、`cross_layer_questions`：新闻事件层产物（`event_narrative_ledger.py:1380`、`1387-1391`）。

### 2.2 冲突裁决规则：有，且是"数据判决为锚"的单向规则

规则清单（全部有代码/提示词锚点）：

1. **数据判决是基准，事件层无权改判。** IA 提示词明文（`integrated_adjudicator.md:23`）；报告 policy 字段同样写死 `stance_anchor_rule`："第三层裁决不得偏离第一层 final_stance；张力只登记，不再裁决"（`integrated_synthesis_report.py:250`）。合约层面 `IntegratedAdjudication.stance_echo` 由代码装配，"模型不填写——它觉得数据判决错了只能写异议通道"（`src/agent_analysis/contracts.py:557-561`）。
2. **逐卡对质记录 `conflict_matrix`**：每张事件卡一行，三态 `confirmed_by_data / challenged_by_data / not_yet_testable`，数据侧必须给具体 ref（`integrated_adjudicator.md:39`；合约 `contracts.py:578`）。LLM 版对质存在时，旧的确定性兜底矩阵逐行标 `superseded_by: integrated_adjudication`（`integrated_synthesis_report.py:269-272`；兜底版形状在 `integrated_synthesis_report.py:1513-1524`）。
3. **抗诉通道 `data_verdict_objections`**：外部材料怀疑数据判决本身时的唯一合法出口（`integrated_adjudicator.md:40`；合约 `contracts.py:523-547`，material 异议必须点名被挑战的数据点，否则校验拒收）。
4. **亮红灯上老板**：常设检查 PC-28 三条件同时满足才亮——①source_ref 命中本报告研究架 verified_cards 的 source_url（代码核验）；②contradicted_data 非空（模型判）；③materiality=material（模型判）——亮灯含义"经核实的外部事实与数据判决正面冲突，需老板人工裁决"（`src/agent_analysis/persistent_checks_b.py:1191-1260`）。报告第一屏置顶横幅用同一口径（`src/agent_analysis/vnext_reporter.py:2605-2645`，横幅原文"改判与否由你裁决，数据判决为锚、系统不改"）。
5. **事件卡挑战不亮灯只记录**；`challenged_by_data` 方向曾经装反（PC-27 把"数据削弱事件"当成"事件挑战数据"），自 08-19 落地起从未按原意生效，08-27 退役，由 PC-28 正确承接（`persistent_checks_b.py:1184-1188`）。

**冲突记录机制**：全部落进 `integrated_synthesis_report.json` 的 `integrated_adjudication` 块（`integrated_synthesis_report.py:267-272`），报告页有专区"数据与外部世界的对质记录"展示逐条矩阵与问答（`vnext_reporter.py:4445-4479`）。

**事件侧不碰发布闸门**：IA 的 `_publish_gate` 只听数据侧信号（DataIntegrity、claim 台账闸门、final 审批状态），事件材料无权阻断发布（`integrated_synthesis_report.py:1133-1163`）。

### 2.3 其他入口排查（有没有第二个对质点）

- 第一层终判 `final_adjudicator.md` 全文 grep `event|事件|新闻` **零命中**——第一层判决是纯数据的，设计上不见事件。
- 编排器存在一条 `packet.event_refs → synthesis_packet.event_index → key_event_refs → critic/reviser/final 治理包` 的通道（`orchestrator.py:5468`、`5782-5786`、`5941`；thesis 站校验器也提到 event_index，`orchestrator.py:8168-8185`）。**但它是空管道**：`AnalysisPacketBuilder.build` 的 `allow_event_refs` 默认 False（`src/agent_analysis/packet_builder.py:367`、`379-383`），全仓没有任何调用方传 True，主链实建 packet 时没传（`src/main.py:795-799`），且 context 明示 `event_material_policy: layer_2_only_not_in_prompt`。结论：管道在、水没通。
- 降级情形：IA 的 LLM 裁决失败时返回 None、其余产物保持确定性拼装（`integrated_synthesis_report.py:283-286`），此时对质只剩兜底矩阵，PC-28 对 `llm_adjudicated=false` 直接跳过（`persistent_checks_b.py:1225-1230`）。

---

## 3. 校准闭环取证（Q-F）

### 3.1 给谁打分、按什么标准

打分对象是**每次 run 的 `final_claim_ledger.json` 里的每条最终 claim**（不是五层、不是事件层）。

- 方向判定：`_claim_direction` 用关键词启发式——claim 文本含"进攻/买入/加仓/低估……"判多，含"谨慎/防守/减仓/风险触发……"判空，都不含判 `not_directional`（`src/agent_analysis/outcome_review.py:221-239`）。
- 兑现窗口：QQQ 价格的 T+20/T+60/T+120 自然日窗口收益与最大回撤（`outcome_review.py:24-28`、`_performance_for_days` 154-198）；价格来自 yfinance（`outcome_review.py:80-104`）。
- 判定阈值（写死在 `outcome_review.py:271-276`）：多方 claim——T+60 或 T+120 收益 ≥5% 且回撤 >-12% 算 consistent，T+20 ≤-8% 或中期 ≤-10% 或回撤 ≤-12% 算 falsifier_triggered；空方/风险 claim 镜像。两不沾 = not_scorable。
- 错误分类：`map_error_taxonomy` 只映射三档（correct / direction_wrong / not_scorable），magnitude_wrong 和 condition_never_triggered 是保留位、永远不被判出（`src/agent_analysis/outcome_scoring_runner.py:69-91`）。
- 打分器自带坦白：每份产物嵌 `DATA_QUALITY_CAVEAT`——"本分数优先作为数据问题探测器使用，不代表对判断质量的最终结论"（`outcome_scoring_runner.py:59-62`）。

### 3.2 打分怎么触发、结果流向哪里

两条触发路径：

1. **run 内**：`orchestrator._build_outcome_review_report`（`src/agent_analysis/orchestrator.py:1111-1133`）——**只对回测 run 打分**；live run 直接返回 `source="not_run_for_live_or_non_backtest_context"`（`orchestrator.py:1119-1128`）。产物 `outcome_review_report.json` + `claim_outcome_scores.json`（`outcome_review.py:512-529`）。
2. **离线批跑**：`outcome_scoring_runner.run_score_outcomes_batch` 扫 `output/analysis/vnext/*/final_claim_ledger.json`，满 20 自然日才打，逐 run 写 `claim_outcome_scores.json`，汇总追加 `output/state_ledger/claim_outcome_ledger.jsonl`（`outcome_scoring_runner.py:152-159`、`363-402`）。该模块边界明文：不许碰 orchestrator、不许碰 run 内的 outcome_review_report（`outcome_scoring_runner.py:21-28`）。

**流向取证（grep 全仓的结果）**：

- `claim_outcome_scores.json` / `claim_outcome_ledger.jsonl`：**只有写入者，没有任何 src/ 读者**（grep 命中全部是写入点与契约描述）。
- `outcome_review_report.json` 的读者只有两类：报告展示层 `vnext_reporter.py:2039-2040`、`6230-6296`（复盘页展示）；常设检查的 artifact 键名单 `persistent_checks_b.py:45`（PC-16 名单，非评分消费）。
- `run_review_report.json`（run 内复盘，产出 `learning_updates` 和 `next_run_checks`，`run_review.py:1003-1013`）：读者同样只有 vnext_reporter 展示层。

### 3.3 回灌路径：闭环的最后一截有没有

逐一排查"评分/复盘结果 → 提示词/方法/权重/议程"的每条候选路径：

| 候选路径 | 取证结果 | 锚点 |
|---|---|---|
| 分数进 L1-L5/Bridge/Thesis/Risk/Reviser/Final 提示词 | **制度性禁止**，且每个产物内部嵌着禁令明文 `no_backflow_rule` | `outcome_scoring_runner.py:29-31`、`64-67`；`outcome_review.py:365`、`523`；`state_ledger.py:199-203` |
| 主动防泄露扫描 | `_leakage_checks` 扫 7 个 prompt artifacts 里有没有 outcome 相关 token | `outcome_review.py:369-384` |
| 学习点回流 | `post_run_reflection_library.json` 把 learning_updates 打成条目，每条标 `allowed_use="manual_rule_update_or_test_design_for_future_runs"`、`runtime_prompt_use="forbidden_for_current_run"`，归宿清单是 `["tests", "documentation", "future prompt/manual rule revisions"]`；该文件在全仓只出现在**禁止清单**里 | `orchestrator.py:1135-1170`；禁止清单 `src/agent_analysis/inquiry_router.py:32`、`orchestrator.py:1362`、`1556` |
| 方法修正台账 | `method_revision_ledger.jsonl` 存在，但每条要老板批准、挂真实 git commit、带 review_after，**没有任何代码自动执行或回读它进提示词** | `state_ledger.py:236-303` |
| 状态台账进提示词 | 明文禁止（reader-exit / outcome-scoring material only） | `state_ledger.py:199-203` |
| 预期-兑现台账进治理站 | 08-15 起四站（critic/risk/reviser/final）一律不给，"台账留磁盘审计" | `orchestrator.py:5845-5848`（`pricing_expectation_ledger={}`） |
| 事件层自身判断被评分 | **没有任何机制**。DSH 的 `narrative_state` 全仓消费者只有 IA 提示词、brief、词表候选收集；`event_market_validation` 是新闻的市场窗口观察，policy 明文"不得证明新闻导致价格变化"，不是对系统判断的打分 | grep `narrative_state` 全仓；`event_narrative_ledger.py:780-783` |

### 3.4 结论：闭环断

**断在"评分 → 方法修正"这一截。** 分段说：

- **通的部分**：判断落账（final_claim_ledger 每条 claim 带证据/反证/失效条件）→ 事后打分（run 内回测打分 + 离线批跑，能产出 consistent/falsifier_triggered 判决）→ 分数落盘落账。这一段代码齐全、能跑。
- **断的部分**：分数到此为止。没有任何代码路径把评分或复盘结论注入任何提示词、调整任何权重、修改任何议程；唯一的承接物 `post_run_reflection_library.json` 被打上"本 run 禁用、只能手工用于未来规则修订"的烙印，且全仓无运行时读者；方法修正的唯一通道是老板手工写 `method_revision_ledger`。
- **断点锚点**：`orchestrator.py:1154-1156`（reflection 条目的 allowed_use / runtime_prompt_use 两字段）；`outcome_scoring_runner.py:29-31`（No score-backflow 边界条文）。

**必须如实补充**：这个断是**有意设计**，不是烂尾——防前视泄露、防打分器粗糙（关键词定方向）反而污染判断。但按北极星"校准闭环：判断可评分、评分修正方法"的字面要求，自动闭环在代码里不存在；现在的形态是"前半截自动 + 最后一截全手工"。

---

## 4. 事件层自身的闸门（hooks/ + 层内机器校验）

### 4.1 hooks/ 三个钩子（dsh 运行时卡口）

绑定关系见 `src/event_research/dsh_profile/hooks.json.tmpl`；协议：stdin 一行 JSON，exit 2=硬停，stdout 结构化 JSON=deny/附加上下文（`src/event_research/hooks/common.py:1-7`）。

| 钩子 | 触发点 | 作用 | 失败后果 | 分类 |
|---|---|---|---|---|
| `hooks/budget_gate.py:21-37` | UserPromptSubmit（每次发模型请求前） | 折叠 session 日志累计 token，超经费卡 exit 2 硬停 | agent 当场停，产物标"半成品" | **A**（纯账目核验；注意：经费卡文件缺失时宁可放行不错杀，`budget_gate.py:27-29`） |
| `hooks/fetch_gate.py:17-28` | PreToolUse，matcher=web_fetch | 非 https 或域名不在 `config/event_source_whitelist.json` → deny | 该次抓取被拒，模型换源 | **A**（域名身份比对） |
| `hooks/source_tagger.py:24-34` | PostToolUse，matcher=web_fetch | 给模型贴来源档位标签（"可进正文/只进线索"） | 无拦截，纯提示 | **A**（机械域名比对） |

### 4.2 层内机器校验（非 hook，但同属闸门层）

| 校验 | 位置 | 作用 | 失败后果 | 分类 |
|---|---|---|---|---|
| 材料卡四镣铐+出生证 | `src/event_research/card.py:37-85` | 事实/解读分离、来源分级、时间戳、needs_data_confirmation 非空、source_pointer 形状 | 错误码标注随卡走，不拦截（二档无发布闸门） | **A** |
| 对账器 | `src/event_research/reconcile.py:203-239` | url 必须真实被抓过；quote 对回抓取原文（逐字或 3-gram 锚点+编辑距离，相似度阈值 0.8，`reconcile.py:86`）；弱档来源降级 | 降级标注（4 种原因码），降级卡只带"仅解读"资格进 IA | **A**（判的是文本同一性=身份；0.8 是启发式阈值但不判意思，是最接近 B 的一个，仍归 A） |
| 数字核对 G7 | `src/event_research/narrative_check.py:81-122` | 判断段带单位数字必须能在证据卡找到同值 | 黄灯标注 ungrounded_number，不拦截（`narrative_check.py:6-8`） | **A**（确定性算术） |
| narrative_state 形状 | `runner.py:126-142` | 七字段齐全且非空、无未知字段 | 错误码进 run_summary 的 narrative_observations | **A** |
| 出题官形状校验 | `topic_composer.py:123-155` | 任务书六字段非空、material_classes 合法 | 不合格进 dropped 留痕，不拒收 | **A** |
| 词表三账一致 PC-29 | `src/event_research/term_activation.py:324-398`；挂 `persistent_checks_b.py:1270-1296` | overrides↔change_log↔candidates 三本账互相说得通 | 常设检查亮灯 | **A**（明文"闸门不判意思"，`term_activation.py:329`） |

### 4.3 分类汇总

- **A（形状/身份校验）：全部 9 个。** 事件层闸门无一例外是机械校验。
- **B（意思判断）：0 个。**
- **C（拿不准）：0 个。** reconcile 的 0.8 相似度阈值是唯一带"判断味"的，但它判的是"两段文字是否同一段引文"（身份问题），不是"这段话什么意思"，归 A。

这与总纲"闸门不判意思"原则完全一致；代价是二档没有任何语义拦截，全靠"标注随产物走 + IA 消费端过滤 + 老板看简报"。

---

## 5. 附：本文没有回答的

- DSH 真实巡逻的产出质量（对账通过率、一手率的实际数值）——那是 `output/` 运行数据，本文只取证机制。验证方法：读最新 `output/event_research/runs/*/run_summary.json`。
- 打分机 20 天成熟期内积累的分数分布——同上，验证方法：读 `output/state_ledger/claim_outcome_ledger.jsonl`（若存在）。
- RESEARCH_CANON 教义与上述行为的逐条比对——超出本文范围。
