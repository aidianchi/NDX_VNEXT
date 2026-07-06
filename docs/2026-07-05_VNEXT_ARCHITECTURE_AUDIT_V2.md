# vNext 架构差距审计 V2

审计日期：2026-07-05  
重构日期：2026-07-06

本文是 `ndx_vnext` 后续架构讨论的独立基准文档。读者不需要先读其他审计版本。本文覆盖 7 月 3 日两篇目标文档提出的全部 30 个检查项，并按主次重新组织：先讲系统现在是什么，再讲真正缺什么，最后给出完整条目索引。

---

## 1. 一句话结论

现有 vNext 的底盘是干净的：固定主链、L1-L5 隔离、数据闸门和事件侧链都已经成形。它现在最缺的不是更多报告字段，也不是让 Agent 自由发挥，而是一个**受控研究反馈环**：发现疑点后，系统能按规则追问、补查、保留反证、生成竞争假说，并在新证据足够强时版本化改判。

换成人话：

- 现在系统像一套纪律很强的固定体检流程：该查的层都会查，新闻不会乱塞进正式数据，严重数据问题会阻断发布。
- 但体检发现疑点后，系统还不太会继续查：谁来发问、谁能看什么、查到什么程度停、调查结果怎么回到综合判断，这些运行结构还没有。
- 第二层事件材料已经有账本雏形，但像一个安静资料库，还不能主动挑战综合层，也不能被第一层数据异常定向追问。
- 综合层有“主要矛盾”“价格反映”等字段，但字段可能由代码兜底补齐，不能证明模型真的完成了高质量裁决。
- 竞争假说、非单调重判、最终 claim 台账还没成体系，所以反证容易被塞回单一故事里，而不是触发新假说或版本化改判。

本文的主判断是：

> 下一阶段应先搭一个最小闭环：守住 L1-L5 隔离和 no-backflow，同时建立受控追问消息、研究任务路由、AgentSpec、InvestigationReport、最小证据字段和最小竞争假说。反馈环和竞争假说要一起长出来，不能一个完全等另一个。

---

## 2. 先把词说清楚

本文会使用一些架构词。这里先翻译成人话，避免后文变成概念堆叠。

| 术语 | 人话解释 | 为什么重要 |
| --- | --- | --- |
| 地基 | 系统不能破坏的底层纪律：固定主链、L1-L5 隔离、no-backflow、DataIntegrity、effective_date、指标发言权 | 没有这些纪律，动态研究会变成污染源 |
| 反馈环 | 系统发现疑点后，能受控地追问、补查、再判断 | 让系统不只是写“未解决”，而是能继续研究 |
| L2 催化账本 | 第二层不是新闻堆，而是外部世界事件、制度、政策、产业叙事和因果线索的结构化账本 | 它提供“可能触发状态变化”的现实语境，但不能自己宣布状态已经变化 |
| Inquiry Router | 研究任务调度员。决定问题值不值得查、谁去查、能看哪些材料、不能看哪些材料、预算多少、什么时候停 | 防止 Thesis 或临时 Agent 直接回头污染 L1-L5 |
| AgentSpec | 临时研究任务说明书 | 没有它，动态 Agent 就容易自由发挥 |
| InvestigationReport | 临时调查结果单 | 没有它，补查结果无法被 Bridge V2 或综合层稳定读取 |
| 竞争假说 | 同时保留几种可能解释，让证据和反证去比较它们 | 防止系统过早只相信一个故事 |
| 非单调重判 | 新证据可以推翻旧结论，旧版本必须保留，改判原因必须可审计 | 金融判断不是信息越多旧结论越强，很多时候新信息会让旧结论失效 |
| Evidence Passport | 每条材料的证据护照：来源、时间、能证明什么、不能证明什么、支持/反驳哪些 claim | 防止代理指标、新闻标题、市场价格越权发言 |
| Claim Ledger | 最终自然语言结论台账：每句话对应哪些证据、反证、推理步骤和失效条件 | 让读者看到的结论可以逐条追问 |

---

## 3. 审计依据与判断口径

本文依据三类材料：

| 材料 | 用途 |
| --- | --- |
| [2026-07-03_NDX_VNEXT_EPISTEMIC_ARCHITECTURE_REPORT.md](./2026-07-03_NDX_VNEXT_EPISTEMIC_ARCHITECTURE_REPORT.md) | 明确三层架构、证据权限、竞争假说、非单调推理、主要矛盾和报告形式 |
| [2026-07-03_harness讨论.md](./2026-07-03_harness讨论.md) | 明确固定主链与动态研究单元的关系，提出 Gap Planner、AgentSpec、InvestigationReport、Bridge V2 |
| 当前源码、测试和真实产物抽样 | 判断哪些已实现、哪些只是字段存在、哪些完全缺失 |

判断等级：

| 等级 | 含义 |
| --- | --- |
| 已做到 | 代码、测试或产物已经能支撑该要求 |
| 部分做到 | 有结构或局部实现，但覆盖不足 |
| 语义不足 | 字段存在，但无法证明真实分析质量成立 |
| 未做到 | 没有对应合同、运行结构或产物 |
| 原则已成立 / 尚无对象可验收 | 约束方向正确，但相关新机制尚未实现，无法实测 |

角色分类：

| 角色 | 含义 |
| --- | --- |
| 原则 | 违反后系统会失真或污染 |
| 机制 | 实现原则的工程载体，例如合同、路由器、产物结构 |
| 验收字段 | 用来检查机制是否真的落地 |
| 读者出口 | 面向最终读者的表达与呈现方式 |

---

## 4. 目标架构：四个主层 + 一个读者出口

目标不是把 vNext 改成自由 Agent 系统，而是在现有固定主链上加一个受控研究闭环。

```text
读者出口
  把市场判断、风险边界、个人决策翻译分开呈现
  支持 30 秒、5 分钟、深度研究、审计重放四种阅读深度

横向证据层
  Evidence Passport / Claim Ledger / 权威等级
  贯穿数据、事件、调查、假说和最终结论

综合裁决层
  主要矛盾与主导面
  竞争假说与 Counter-Thesis
  非单调重判和版本记录

研究反馈环
  L2 催化账本
  四类受控消息
  Inquiry Router
  AgentSpec / InvestigationReport

地基
  固定主链
  L1-L5 隔离
  no-backflow
  DataIntegrity / effective_date
  对象定义 / 指标发言权
```

四个主层的关系：

1. **地基不可破坏**：任何反馈、补查、重判，都不能让 L1-L5 读取其他层运行时结论，不能让新闻或浏览器材料直接变成 L1-L5 主证据。
2. **反馈环是主战场**：系统要从“发现问题后写下来”升级为“发现问题后能受控追问”。
3. **综合裁决是收敛和分叉的地方**：调查结果不能只是塞进原故事，而要进入竞争假说比较；反证足够强时要分叉新假说。
4. **横向证据层要从一开始给最小约束**：统一大注册表可以分阶段做，但 AgentSpec 和 InvestigationReport 从第一版起就必须带来源、时间、证据权限、支持/反驳对象等最小字段。
5. **读者出口不是核心推理层**：它负责把上游结论讲清楚。上游语义质量不够时，UI 不能靠包装制造确定性。

---

## 5. 当前系统强在哪里

现有系统不是坏系统。它已经有一套很重要的纪律：

| 已有能力 | 当前判断 | 证据 |
| --- | --- | --- |
| 固定主链 | 已做到。L1-L5、Bridge、SynthesisPacket、Thesis/Critic/Risk/Reviser/Final、Run Review 顺序固定，不由自由 Agent 临场编排 | `src/agent_analysis/orchestrator.py:213`、`:224` |
| L1-L5 运行时隔离 | 已做到。每层只拿本层 context brief、本层 facts、本层 raw data | `src/agent_analysis/orchestrator.py:463`、`:1000`、`tests/test_vnext_orchestrator.py:452` |
| no-backflow | 已做到。pure data / integrated synthesis / event mechanism 报告分离，综合不回写 | `src/integrated_synthesis_report.py:91`、`:122`、`tests/test_three_layer_artifacts.py:533` |
| DataIntegrity 硬闸门 | 已做到。blocked/unpublishable 时主链不继续生成正式结论 | `src/core/checker.py:351`、`src/main.py:453` |
| event_ref 与 evidence_ref 分离 | 已做到。新闻/事件默认不进入 L1-L5 AnalysisPacket | `src/agent_analysis/packet_builder.py:287`、`src/news_event_ledger.py:553`、`tests/test_vnext_packet_builder.py:198` |
| 事件侧结构化 | 部分做到且偏强。有事件簇、claim、研究包、市场验证、机制报告、跨层问题和降级规则 | `src/event_narrative_ledger.py:1291`、`:1300`、`:1316`、`tests/test_three_layer_artifacts.py:374` |
| Bridge 跨层综合 | 已有骨架。能输出冲突、共振、传导、主要矛盾、价格反映等结构 | `src/agent_analysis/contracts.py:560`、`:599`、`:614` |
| 主链可一键跑通 | 已做到。artifact 链完整，控制台入口可用 | `src/main.py:455`、`:520`、`src/control_service.py:400` |

这些能力应该被守住，不应因为引入动态研究单元而被改松。

---

## 6. 核心缺口是什么

### 6.1 缺口一：反馈环的运行机制基本没有

第二层事件材料已经有结构，但反馈环本身还没有跑起来。更准确地说：

- L2 材料账本已有基础。
- 四类受控消息还没有强类型协议。
- Inquiry Router / Gap Planner 没有实现。
- AgentSpec 没有实现。
- InvestigationReport 没有实现。
- 预算、停止条件、allowed_context、forbidden_context 没有运行主体。

四类消息应该分别解决不同方向的问题：

| 消息 | 方向 | 用途 | 当前状态 |
| --- | --- | --- | --- |
| `observation_inquiry` | L1 或 Bridge → L2 | 数据发现异常后，问外部世界有没有背景、历史类似、反证 | 未做到 |
| `event_challenge` | L2 → 综合层 | 外部事件尚未进入数据时，建立观察清单或情景压力测试 | 未做到 |
| `adjudication_gap` | 综合层 → L1 + L2 | 综合层发现关键缺口，要求补查 | 未做到 |
| `evidence_upgrade_request` | L2 或综合层 → 治理层 | 申请把外部材料升级为正式数据源或可信 sidecar | 未做到 |

风险：如果只做 Bridge 后补查，只实现 `adjudication_gap`，系统会变成“加长版单向链”，不是反馈环。

### 6.2 缺口二：竞争假说还没有成为发散机制

当前 Critic 是看过 Thesis 后挑错，不是独立 Counter-Thesis。ThesisDraft 有主论点和支撑链，但没有强类型的 2-4 个竞争假说结构，也没有每个假说的支持证据、反证、诊断力、胜出理由和保留理由。证据：`src/agent_analysis/contracts.py:817`、`:862`、`:918`、`src/agent_analysis/orchestrator.py:217`、`:219`。

这不是小字段缺口。没有竞争假说，动态调查结果很容易被吸收进原来的单一故事。正确做法是：

```text
旧假说遇到强反证
  -> 不直接硬塞回原故事
  -> 分叉出新假说
  -> 比较支持证据、反证、诊断力
  -> 保留未解释项和失效条件
  -> 必要时版本化改判
```

### 6.3 缺口三：主要矛盾和价格反映字段存在，但语义不稳

Bridge 有 `principal_contradiction`、`dominant_side`、`price_reflection_map` 等字段。但这些字段可由代码兜底生成：

- `principal_contradiction` 可按最高严重度冲突兜底生成：`src/agent_analysis/orchestrator.py:3104`。
- `dominant_side` 可补 `unclear_until_thesis`：`src/agent_analysis/orchestrator.py:3130`。
- `price_reflection_map` 缺项可自动补 `unclear`：`src/agent_analysis/orchestrator.py:2954`、`:2967`。
- Run Review 会检查 principal_contradiction 是否原生生成而非 normalize 兜底：`src/agent_analysis/run_review.py:495`。

所以这里的问题不是“没有字段”，而是字段背后的判断质量没有稳定证明。

### 6.4 缺口四：证据注册是局部的，不是贯穿的

现有系统有三个局部证据结构：

- 数据侧 `data_quality`：`src/data_evidence.py:15`、`:226`。
- 事件侧 claim ledger：`src/event_narrative_ledger.py:440`、`:1305`。
- 主链 SynthesisPacket evidence index：`src/agent_analysis/orchestrator.py:595`。

但它们还没有统一为一套 Evidence Passport，也没有覆盖最终自然语言 claim。最终读者看到的每条重要结论，还不能稳定追到：

```text
claim_id
claim_text
evidence_refs
counter_evidence_refs
inference_steps
falsification_conditions
verified
```

### 6.5 缺口五：读者出口还不是一份可折叠裁决工作台

报告 UI 已经有 cockpit/brief/atlas/workbench 四种模板、L1-L5 accordion、证据抽屉和审计索引。但四种模板不等于“一份报告内四层阅读深度”。代码中还没有明确的：

- 30 秒裁决。
- 5 分钟简报。
- 深度研究。
- 审计重放。

证据：`src/agent_analysis/vnext_reporter.py:50`、`:1134`、`tests/test_vnext_reporter.py:638`。

---

## 7. 分层审计

### 7.1 地基：不重建，但必须继续守住

地基负责“系统不乱说、不污染、不越权”。它包括固定主链、L1-L5 隔离、no-backflow、DataIntegrity、effective_date、对象定义和指标发言权。

现状：

- 固定主链、L1-L5 隔离、no-backflow、DataIntegrity、event_ref/evidence_ref 分离已经较强。
- 对象定义有 ObjectCanon 和 objective firewall，但对象、口径、成分、方法、时间边界还没有统一成为完整 run gate。证据：`src/agent_analysis/contracts.py:105`、`src/agent_analysis/orchestrator.py:710`。
- 指标发言权有 permission、canonical question、misread guard、falsifier 字段，但部分字段可兜底补齐，语义质量仍需守门。证据：`src/agent_analysis/contracts.py:123`、`:219`、`src/agent_analysis/orchestrator.py:2617`。

结论：

| 项目 | 判断 |
| --- | --- |
| 是否需要重建地基 | 不需要 |
| 是否需要加强 | 需要，主要是对象定义和指标发言权的语义闸门 |
| 最大风险 | 动态反馈环引入后破坏 L1-L5 隔离或 no-backflow |

### 7.2 研究反馈环：主战场

反馈环负责“发现疑点后继续研究”。它由 L2 催化账本、四类消息、Inquiry Router、AgentSpec、InvestigationReport 构成。

现状：

- L2 催化账本有基础，但主要覆盖新闻/事件，其他二层材料类型覆盖不足。
- 四类受控消息没有强类型合同。证据：`src/agent_analysis/contracts.py:634`、`src/agent_analysis/run_review.py:495`。
- Bridge 后没有 Gap Planner / Inquiry Router。证据：`src/agent_analysis/orchestrator.py:213`、`:214`。
- AgentSpec、InvestigationReport、预算和停止条件未实现。

关键要求：

| 机制 | 最小要求 |
| --- | --- |
| Inquiry Router | 统一接收四类消息，判断是否要查，生成任务，控制预算和停止条件 |
| AgentSpec | 必须有 question、originating_gap、allowed_context、forbidden_context、tools、budget、stop_conditions、required_output |
| InvestigationReport | 必须有 finding、evidence、counter_evidence、confidence、limits、source_refs、effective_date |
| no-backflow | 调查结果只能进入补充版本、Bridge V2 或综合层，不得静默改写 L1-L5 |

结论：

| 项目 | 判断 |
| --- | --- |
| 是否是最主要缺口 | 是 |
| 是否完全从零 | 不是。L2 材料账本有基础，但反馈环运行机制基本为空 |
| 最大风险 | 做成“Bridge 后挂几个自由 Agent”，反而引入污染和漂移 |

### 7.3 综合裁决：要和反馈环一起长

综合裁决负责“怎么判断”。它不能只是把材料总结成一个故事，而要让多个解释竞争，并在新证据出现时允许改判。

现状：

- Bridge 已有跨层结构，但主要矛盾和价格反映语义不稳。
- Thesis/Critic/Risk/Reviser/Final 固定阶段存在，但 Critic 不是独立 Counter-Thesis。
- 竞争假说、Counter-Thesis、版本化重判协议未成体系。

这里要修正一个容易误解的点：竞争假说不应完全等反馈环建完再做。最小竞争假说可以先基于现有 L1-L5 + L2 材料生成；随后反馈环再针对假说之间最关键的分歧去补查。两者是互相喂养的关系：

```text
最小竞争假说
  -> 暴露关键分歧
  -> 触发受控追问
  -> InvestigationReport 回来
  -> 假说分叉、淘汰或版本化改判
```

结论：

| 项目 | 判断 |
| --- | --- |
| 是否应紧随反馈环 | 是 |
| 是否可以先做最小版 | 可以，且建议与反馈环 MVP 同步设计 |
| 最大风险 | 动态调查结果被吸收进单一主线，反证没有触发新假说 |

### 7.4 横向证据层：大注册表可分期，最小证据字段必须前置

横向证据层负责“每个材料和每句话从哪里来、能证明什么”。它贯穿数据、事件、调查、假说和最终结论。

现状：

- 数据侧、事件侧、主链各有局部证据结构。
- 统一 Evidence Passport 未完成。
- 最终 Claim Ledger 未完成。
- 证据权威等级和降级规则分散在各侧。

这里也要修正一个容易误解的点：统一大注册表可以分阶段做，但动态调查第一天就必须带最小证据字段。否则新增的 InvestigationReport 会再次变成散落 artifact。

最小证据字段建议：

```yaml
source_ref:
source_type:
material_form:
observed_at:
published_at:
effective_date:
claims_supported:
claims_challenged:
cannot_establish:
quality_risks:
```

结论：

| 项目 | 判断 |
| --- | --- |
| 是否替代反馈环 | 不能 |
| 是否可以完全后置 | 不能。统一注册表可后置，最小证据字段要前置 |
| 最大风险 | 新调查产物不可追溯，重复当前局部证据系统割裂 |

### 7.5 读者出口：四层阅读，不是四种模板

读者出口负责“怎么给人看”。它不参与主推理，但会决定最终报告是否可读、可追问、可审计。

现状：

- Final 已区分 `quality_gate` 和 `reader_final`。证据：`src/agent_analysis/contracts.py:1262`、`src/agent_analysis/prompts/final_adjudicator.md:5`。
- `portfolio_actions`、`invalidation_conditions`、`state_diagnosis` 已存在，但市场判断、风险边界、个人决策翻译没有强制分栏。证据：`src/agent_analysis/contracts.py:783`、`:1275`。
- cockpit/brief/atlas/workbench 是多种模板，不是一份报告内的四层阅读深度。

结论：

| 项目 | 判断 |
| --- | --- |
| 是否主轴 | 不是 |
| 是否重要 | 重要。它是读者真正接触系统的出口 |
| 最大风险 | 上游语义不足时，UI 把不确定性包装成确定性 |

---

## 8. 优先级：先搭最小闭环，不做线性大工程

正确顺序不是“一个层完全做完再做下一层”。更合适的是先搭最小闭环，让反馈环、竞争假说和最小证据字段一起工作。

### 8.1 第一阶段：最小闭环

目标：让系统第一次具备“发现疑点、受控补查、多假说再判断”的能力。

| 步骤 | 内容 | 解决什么 |
| --- | --- | --- |
| 1 | 明确反馈环不得破坏 L1-L5 隔离、no-backflow、event_ref/evidence_ref 分离 | 防污染 |
| 2 | 定义四类消息的最小 schema | 让追问有入口 |
| 3 | 实现 Inquiry Router 的最小版 | 让追问有中间人 |
| 4 | 定义 AgentSpec 与 InvestigationReport | 让动态研究有身体 |
| 5 | 在 AgentSpec / InvestigationReport 中内置最小证据字段 | 防止新产物散落 |
| 6 | 做最小竞争假说结构 | 让调查结果能分叉，而不是塞回单一故事 |

### 8.2 第二阶段：增强裁决

目标：让系统能把新证据转化为清晰的版本化判断。

| 步骤 | 内容 |
| --- | --- |
| 1 | 加 Counter-Thesis Builder |
| 2 | 建立非单调重判协议 |
| 3 | 强化 principal_contradiction / dominant_side / price_reflection_map 的原生生成和审查 |
| 4 | 明确 Bridge V2 如何读取 InvestigationReport |

### 8.3 第三阶段：统一证据和读者出口

目标：把局部证据结构统一起来，并让读者能按不同深度展开。

| 步骤 | 内容 |
| --- | --- |
| 1 | 统一 Evidence Passport |
| 2 | 建 Final / Thesis Claim Ledger |
| 3 | 统一证据权威等级和降级规则 |
| 4 | 做一份报告内的四层阅读工作台 |
| 5 | 强制区分市场判断、风险边界、个人决策翻译 |

---

## 9. 全部 30 条检查项

### 9.1 EPI 条目

| ID | 检查问题 | 所属层 | 当前判断 | 说明 |
| --- | --- | --- | --- | --- |
| EPI-01 | 系统是否先定义判断对象，而不是直接给结论？ | 地基 | 部分做到 / 语义不足 | 有 ObjectCanon 和 objective firewall，但对象护照和 run gate 不完整 |
| EPI-02 | 重要结论是否包含对象、证据、反证、失效条件？ | 综合裁决 / 横向证据 | 部分做到 | 指标和综合报告层有字段，最终自然语言 claim 台账不足 |
| EPI-03 | 是否区分市场判断、风险边界、个人决策翻译？ | 读者出口 | 部分做到 | Final 有质量闸门和读者结论，但首屏表达没有强制三类分栏 |
| EPI-04 | 是否有统一 Evidence Passport？ | 横向证据 | 部分做到 | 数据侧、事件侧、主链各有局部系统，未统一 |
| EPI-05 | 是否区分证据权威等级？ | 横向证据 | 部分做到 | source_tier 和降级规则存在，但未形成贯穿所有 claim 的统一模型 |
| EPI-06 | L1-L5 是否运行时隔离？ | 地基 | 已做到 | 每层只读本层材料和本层上下文 |
| EPI-07 | L1-L5 输出是否遵守指标发言权？ | 地基 | 部分做到 / 语义不足 | 有字段，但部分可兜底补齐 |
| EPI-08 | 第二层事件材料是否结构化，而不是新闻堆砌？ | 反馈环 | 部分做到（偏强） | 事件侧链较成熟，但还不能主动发送挑战或接收追问 |
| EPI-09 | 三层是否保持 two-track independence？ | 地基 | 已做到 | pure data 与 integrated synthesis 分离，综合不回写 |
| EPI-10 | 是否有受控追问消息类型？ | 反馈环 | 未做到 | 四类消息没有强类型协议 |
| EPI-11 | 第二层材料是否禁止成为 L1-L5 主证据？ | 地基 | 已做到 | event_ref 与 evidence_ref 分离 |
| EPI-12 | 是否有竞争假说机制？ | 综合裁决 | 未做到 | 缺 2-4 个假说的支持、反证、诊断力和胜出理由结构 |
| EPI-13 | 是否支持非单调推理和版本化重判？ | 综合裁决 | 部分做到 | 有 checkpoint，但不是新证据触发的版本化改判协议 |
| EPI-14 | 主要矛盾是否成为真实分析，而非口号？ | 综合裁决 | 部分做到 / 语义不足 | 字段较全，但可兜底生成 |
| EPI-15 | 报告 UI 是否支持四层阅读工作台？ | 读者出口 | 部分做到 | 有多模板和 accordion，但不是一份报告内四层阅读深度 |
| EPI-16 | 发布闸门是否覆盖数据、证据、反证和可发布性？ | 地基 / 综合裁决 / 横向证据 | 部分做到 | DataIntegrity 强，语义发布闸门弱 |

### 9.2 HAR 条目

| ID | 检查问题 | 所属层 | 当前判断 | 说明 |
| --- | --- | --- | --- | --- |
| HAR-01 | 是否保留固定主链，而不是自由 agent 全权编排？ | 地基 | 已做到 | 主链由 orchestrator 固定 |
| HAR-02 | L1-L5 是否不做动态化？ | 地基 | 已做到 | 五层固定，只在层内分析 |
| HAR-03 | Bridge 是否承担跨层关系发现？ | 综合裁决 | 已做到 / 部分做到 | 结构层已强，语义层待加强 |
| HAR-04 | Bridge 是否正确处理 price reflection？ | 综合裁决 | 语义不足 | 有字段，但缺项可自动补 `unclear` |
| HAR-05 | Bridge 后是否有 Gap Planner / Inquiry Router？ | 反馈环 | 未做到 | Bridge 后没有受控补查环节 |
| HAR-06 | 动态 agent 是否只用于 Bridge 后补缺口？ | 反馈环 | 原则方向明确 / 尚无对象可验收 | 动态调查链未实现，位置约束尚无运行对象 |
| HAR-07 | 是否有 AgentSpec？ | 反馈环 | 未做到 | 缺任务、上下文、禁区、预算、停止条件 |
| HAR-08 | 是否有 InvestigationReport？ | 反馈环 | 未做到 | 缺可被 Bridge V2 或综合层读取的强类型调查输出 |
| HAR-09 | 是否有预算和停止条件？ | 反馈环 | 未做到 | 应作为 AgentSpec 的内嵌字段一体设计 |
| HAR-10 | 动态调查是否禁止回写 L1-L5？ | 反馈环 / 地基 | 原则已在事件侧成立 / 调查链尚无对象可验收 | 事件侧 no-backflow 不能自动证明未来调查侧 no-backflow |
| HAR-11 | 新闻/事件侧链是否保持隔离？ | 地基 | 已做到 / 部分做到 | 当前事件侧隔离较强，未来新增材料类型仍需同等边界 |
| HAR-12 | 主链是否仍可一键跑通？ | 地基 | 已做到 | artifact 链和入口可用 |
| HAR-13 | 是否有 Counter-Thesis Builder？ | 综合裁决 | 未做到 | Critic 不是独立盲写反方 |
| HAR-14 | 是否有最终 Claim Ledger？ | 横向证据 | 未做到 | 事件侧有 claim ledger，Final/Thesis 自然语言结论没有逐条台账 |

---

## 10. 关键风险

1. **把反馈环做成自由 Agent**：如果没有 Inquiry Router、AgentSpec、allowed_context、forbidden_context、预算和停止条件，动态研究会破坏现有地基。
2. **只做 Bridge 后补查**：如果只实现 `adjudication_gap`，会把多向反馈压回加长单向链，漏掉数据异常问语境、事件挑战综合层这两支。
3. **竞争假说后置过久**：没有最小竞争假说，调查结果缺少分流入口，反证会继续被塞进单一主线。
4. **证据字段后置过久**：没有最小证据字段，新增 InvestigationReport 会变成新一批散落材料。
5. **语义字段被兜底掩盖**：principal_contradiction、dominant_side、price_reflection_map 等字段存在，不等于裁决质量成立。
6. **读者出口制造伪确定性**：上游语义不足时，报告 UI 不能把不确定判断包装成强结论。

---

## 11. 建议的验收口径

后续每次架构升级，至少按下面几条验收：

| 验收项 | 通过标准 |
| --- | --- |
| 地基未被污染 | L1-L5 prompt 和产物不包含其他层运行时结论、Bridge/Thesis/Final 当前判断、未升级事件材料 |
| 消息可追踪 | 每条追问消息有发起方、接收方、触发原因、允许上下文、禁止上下文、时间和版本 |
| 任务可约束 | 每个 AgentSpec 有预算、停止条件、工具白名单、证据要求 |
| 调查可读取 | 每个 InvestigationReport 有 finding、evidence、counter、confidence、limits、effective_date |
| 假说可竞争 | 至少 2 个可竞争解释，有支持、反证、诊断力和保留理由 |
| 改判可审计 | 新证据触发改判时保留旧版本、改判原因和失效条件 |
| claim 可追问 | 最终重要自然语言结论可追到 evidence_refs、counter_evidence_refs、inference_steps |

---

## 12. 剩余风险

1. 真实产物只抽样了一个 run（`output/analysis/vnext/20260701_131914`），足以证明产物链存在，不足以证明所有 run 质量稳定。
2. 本报告没有运行全量测试，测试证据来自已有源码、测试和审计线索，不代表当前工作区全部测试通过。
3. 本报告是架构差距审计，不是精确施工计划；它给出依赖关系和最小闭环顺序，但没有估算工作量。
4. 反馈环相关机制当前主要来自目标文档要求，缺少真实实现后的风险日志、成本数据和失败案例。
5. Bridge V2 消费 InvestigationReport 的集成功能，因为 InvestigationReport 当前未实现，尚无对象可验收。

