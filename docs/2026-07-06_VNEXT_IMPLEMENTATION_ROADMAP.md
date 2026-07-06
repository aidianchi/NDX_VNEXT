# vNext 实施路线图

日期：2026-07-06

本文接在 [vNext 架构差距审计 V2](./2026-07-05_VNEXT_ARCHITECTURE_AUDIT_V2.md) 之后，回答一个问题：如何按最合理的顺序，把 EPI-01..16 与 HAR-01..14 一个不漏地落到工程实现、测试和验收里。

本文不是新的审计，也不是哲学讨论。它是施工总图。

---

## 1. 第一性原理

`ndx_vnext` 要生成的不是一篇顺滑评论，而是一条可追问、可审计、可修正的 NDX 投研推理链。

所以实施顺序必须服务五个基本目标：

1. **先防污染**：正式观测层不能被新闻、Bridge、Thesis、Final 或临时调查反向污染。
2. **再让系统会追问**：发现疑点后，系统要能受控地补查，而不是只把“未解决”写进报告。
3. **再让解释会竞争**：补查结果不能被塞进一个既有故事，必须进入竞争假说和反证比较。
4. **再让证据贯穿到底**：材料、调查、假说、最终自然语言结论都要知道自己从哪里来、能证明什么、不能证明什么。
5. **最后让读者读得清楚**：市场判断、风险边界、个人决策翻译必须分开；读者能先看结论，也能展开审计链。

这决定了路线图的核心节奏：

```text
锁住地基
  -> 定义反馈合同
  -> 跑通最小反馈闭环
  -> 建竞争假说和版本化裁决
  -> 统一证据与 claim 台账
  -> 做读者出口和发布闸门
```

注意：这不是“一个阶段完全做完才碰下一个阶段”的瀑布式工程。最小证据字段、最小竞争假说必须和反馈环一起出现，否则反馈环会产生新的散落材料，或者把新材料继续塞进单一主线。

---

## 2. 实施原则

### 2.1 每一步都必须可回滚、可验收

不要一次性重写主链。每一步都应产生一个明确增量：

- 一个新合同。
- 一个新 artifact。
- 一个新路由节点。
- 一个新测试闸门。
- 一个报告输出变化。

每一步完成后，都应该能回答：它关闭了哪些 EPI/HAR？它没有破坏哪些既有红线？

### 2.2 动态研究不能进入 L1-L5

动态研究只能生成补充产物，供 Bridge V2、综合裁决或下一轮使用。不得静默改写 L1-L5 layer card，不得把事件材料直接变成 L1-L5 `evidence_ref`。

### 2.3 先做薄合同，再做聪明行为

先定义消息、任务、调查报告、证据字段、版本字段。之后再让模型或工具变聪明。

原因很简单：没有合同，聪明行为不可审计；没有预算和禁区，动态研究会漂移。

### 2.4 最小闭环优先

第一版不要追求完整 Deep Research。第一版只需要证明：

```text
Bridge V1 发现缺口
  -> Inquiry Router 生成受控任务
  -> 任务产出 InvestigationReport
  -> Bridge V2 或综合层读取
  -> 竞争假说被更新、保留、分叉或降级
```

---

## 3. 总体顺序

| 阶段 | 目标 | 主要关闭项 |
| --- | --- | --- |
| 0. 锁住地基 | 防止后续动态能力污染主链 | EPI-01/06/07/09/11/16，HAR-01/02/10/11/12 |
| 1. 定义反馈合同 | 让追问、任务、调查报告先有稳定外壳 | EPI-10，HAR-05/07/08/09/10，EPI-04/05 最小字段 |
| 2. 跑通最小反馈闭环 | 让系统第一次能受控补查并二次综合 | EPI-08/10，HAR-05/06/07/08/09/10/11 |
| 3. 建最小竞争裁决 | 让补查结果进入假说竞争，而不是单一路径吸收 | EPI-12/13/14，HAR-03/04/13 |
| 4. 统一证据与 claim 台账 | 让材料、调查、假说、最终结论贯穿可追溯 | EPI-02/04/05，HAR-14 |
| 5. 做读者出口与语义发布闸门 | 让最终报告清楚、分层、不过度暗示 | EPI-03/15/16 |
| 6. 全链路硬化 | 用真实 run、回测和失败案例压实质量 | 全部条目复验 |

---

## 4. 阶段 0：锁住地基

**目标**：确认后续任何动态能力都不能破坏现有主链纪律。

这一步不追求新增功能，追求“后面怎么扩都不能越界”。

### 要做什么

1. 把 L1-L5 输入边界写成可测试规则：每层只读本层事实、本层 raw data、本层 context brief。
2. 把 no-backflow 规则扩展到未来动态调查：InvestigationReport 不能回写 layer card。
3. 把 event_ref / evidence_ref 分离继续硬化：事件、新闻、浏览器、sidecar 默认不能成为 L1-L5 主证据。
4. 把对象定义补成更明确的 run gate：判断对象、口径、日期、指数范围、方法边界必须可见。
5. 把指标发言权补成发布前检查：代理指标、技术指标、价格行为不能越权证明估值、基本面或官方事实。

### 主要改动区域

- `src/agent_analysis/contracts.py`
- `src/agent_analysis/orchestrator.py`
- `src/agent_analysis/packet_builder.py`
- `src/agent_analysis/prompt_inspector.py`
- `tests/test_vnext_orchestrator.py`
- `tests/test_vnext_packet_builder.py`
- `tests/test_three_layer_artifacts.py`

### 验收标准

| 验收项 | 通过标准 |
| --- | --- |
| L1-L5 隔离 | 测试能证明每层 prompt 不含其他层运行时结论、Bridge/Thesis/Final 当前判断、事件侧链结论 |
| no-backflow | 综合报告、事件报告、未来 InvestigationReport 都不能修改 L1-L5 layer card |
| 证据边界 | event_ref 不会变成 L1-L5 evidence_ref |
| 对象定义 | run artifact 中能看到判断对象、口径、时间边界、数据边界 |
| 指标权限 | 越权 claim 被降级、阻断或标记为不可发布 |

### 覆盖条目

`EPI-01`、`EPI-06`、`EPI-07`、`EPI-09`、`EPI-11`、`EPI-16`  
`HAR-01`、`HAR-02`、`HAR-10`、`HAR-11`、`HAR-12`

---

## 5. 阶段 1：定义反馈合同

**目标**：先让“追问”有统一格式，让“临时研究”有任务书和结果单。

这一阶段可以先不调用复杂 Agent。重点是合同先稳定。

### 要做什么

1. 定义四类受控消息：
   - `observation_inquiry`：L1 或 Bridge 发现数据异常，向 L2 查询背景、历史类似和反证。
   - `event_challenge`：L2 发现外部事件尚未反映到数据，向综合层提出观察清单或情景压力测试。
   - `adjudication_gap`：综合层发现关键证据缺口，请 L1/L2 定向补查。
   - `evidence_upgrade_request`：申请把外部材料升级为正式数据源或可信 sidecar。
2. 定义 `InquiryRouter` 的输入输出：接收消息，判断是否需要调查，生成任务或拒绝任务。
3. 定义 `AgentSpec`：任务、允许上下文、禁止上下文、工具、预算、停止条件、成功标准。
4. 定义 `InvestigationReport`：发现、证据、反证、置信度、限制、失效条件、来源、effective_date。
5. 在 `AgentSpec` 和 `InvestigationReport` 里内置最小证据字段，不等待完整 Evidence Passport。

### 最小字段

```yaml
InquiryMessage:
  message_id:
  message_type:
  sender_stage:
  target_stage:
  trigger:
  question:
  allowed_context_refs:
  forbidden_context_refs:
  effective_date:

AgentSpec:
  agent_id:
  originating_message_id:
  research_question:
  allowed_context_refs:
  forbidden_context_refs:
  allowed_tools:
  budget:
  stop_conditions:
  required_output:

InvestigationReport:
  investigation_id:
  originating_agent_id:
  finding:
  evidence_refs:
  counter_evidence_refs:
  claims_supported:
  claims_challenged:
  cannot_establish:
  confidence:
  limits:
  effective_date:
```

### 主要改动区域

- `src/agent_analysis/contracts.py`
- `src/agent_analysis/orchestrator.py`
- `src/agent_analysis/run_review.py`
- 新增反馈环相关测试文件

### 验收标准

| 验收项 | 通过标准 |
| --- | --- |
| 四类消息存在 | 四类消息都有强类型结构、序列化输出和测试 |
| 任务受控 | AgentSpec 必须声明 allowed_context 与 forbidden_context |
| 预算可见 | 每个任务都有预算和停止条件 |
| 证据不散落 | InvestigationReport 第一版就带最小证据字段 |
| 不执行也可审计 | 即使任务被拒绝，也记录拒绝原因和触发来源 |

### 覆盖条目

`EPI-04`（最小证据字段）、`EPI-05`（最小权威字段）、`EPI-10`  
`HAR-05`、`HAR-07`、`HAR-08`、`HAR-09`、`HAR-10`

---

## 6. 阶段 2：跑通最小反馈闭环

**目标**：让系统第一次真正完成“发现疑点 -> 受控调查 -> 二次综合”。

第一版要克制。最多支持少量任务，优先做最容易验收的路径。

### 要做什么

1. 在 Bridge V1 后接入 Inquiry Router。
2. 让 Bridge 的 unresolved questions / principal contradiction gaps 能转成 `adjudication_gap`。
3. 让 L2 催化账本能生成 `event_challenge`，不再只是被动材料库。
4. 让 L1 或 Bridge 能生成 `observation_inquiry`，用于数据异常问语境。
5. 第一版可以限制最多 3 个 AgentSpec，防止成本失控。
6. 生成 `investigation_reports/*.json`，不回写 L1-L5。
7. 增加 Bridge V2：读取原 L1-L5、Bridge V1、InvestigationReport，输出二次综合。

### 第一版建议只支持三类调查

| 调查类型 | 为什么先做 |
| --- | --- |
| L3 结构调查 | NDX/NDXE、Top10 贡献、广度背离容易结构化计算 |
| 数据异常调查 | 直接服务 DataIntegrity 和 effective_date |
| 事件挑战调查 | 激活 L2 催化账本，验证 `event_challenge` |

### 主要改动区域

- `src/agent_analysis/orchestrator.py`
- `src/event_narrative_ledger.py`
- `src/integrated_synthesis_report.py`
- `src/agent_analysis/contracts.py`
- `tests/test_vnext_orchestrator.py`
- `tests/test_three_layer_artifacts.py`

### 验收标准

| 验收项 | 通过标准 |
| --- | --- |
| 闭环可跑 | 一个 run 能产出 InquiryMessage、AgentSpec、InvestigationReport、Bridge V2 |
| no-backflow 成立 | L1-L5 layer card 不因调查结果改变 |
| L2 可主动挑战 | 至少一个事件簇能生成 event_challenge 或明确拒绝生成并记录原因 |
| 调查有限 | 任务数量、工具、预算、停止条件被执行 |
| 二次综合可审计 | Bridge V2 明确说明哪些调查改变了判断，哪些没有改变 |

### 覆盖条目

`EPI-08`、`EPI-10`、`EPI-11`  
`HAR-05`、`HAR-06`、`HAR-07`、`HAR-08`、`HAR-09`、`HAR-10`、`HAR-11`

---

## 7. 阶段 3：建立最小竞争裁决

**目标**：让补查结果进入多假说比较，而不是被原有主线吸收。

这一阶段和阶段 2 应该交错推进。最小竞争假说不需要等反馈环完美后才做；它可以先基于现有 L1-L5 和 L2 材料生成，再由反馈环补强。

### 要做什么

1. 在 Thesis 前或 Thesis 内引入 `CompetingHypothesis` 结构。
2. 每个假说至少包含：
   - 假说文本。
   - 支持证据。
   - 反证。
   - 诊断力强的证据。
   - 不能解释的现象。
   - 失效条件。
3. 增加 Counter-Thesis Builder：第一次生成时不能看 Thesis，只看 SynthesisPacket / Bridge V2。
4. 建立非单调重判记录：新证据改变判断时，保留旧版本、触发证据、改判原因。
5. 强化主要矛盾和 price reflection：禁止只靠兜底字段伪装成真实裁决。

### 主要改动区域

- `src/agent_analysis/contracts.py`
- `src/agent_analysis/orchestrator.py`
- `src/agent_analysis/prompts/`
- `src/agent_analysis/run_review.py`
- `tests/test_vnext_orchestrator.py`

### 验收标准

| 验收项 | 通过标准 |
| --- | --- |
| 至少两个假说 | 正式综合前至少有 2 个可竞争解释，除非明确说明证据不足 |
| 反方独立 | Counter-Thesis 首次生成不读取 Thesis |
| 反证不被吞 | 强反证能触发假说降级、分叉或保留争议 |
| 改判可审计 | 新证据改变判断时保留旧判断和改判原因 |
| 兜底可见 | principal_contradiction / price_reflection 若来自兜底，必须降级或标记 |

### 覆盖条目

`EPI-12`、`EPI-13`、`EPI-14`  
`HAR-03`、`HAR-04`、`HAR-13`

---

## 8. 阶段 4：统一证据与最终 claim 台账

**目标**：让所有材料、调查、假说、最终结论都能被追问。

阶段 1 已经要求最小证据字段。阶段 4 做的是统一注册表和最终 claim 台账。

### 要做什么

1. 统一 Evidence Passport schema。
2. 把数据侧 `data_quality`、事件侧 claim ledger、主链 evidence index 接入统一证据注册。
3. 统一 source tier / authority model / downgrade rules。
4. 为 Thesis / Final 自然语言结论生成 Claim Ledger。
5. 每条重要 claim 必须有：
   - `claim_id`
   - `claim_text`
   - `claim_type`
   - `evidence_refs`
   - `counter_evidence_refs`
   - `inference_steps`
   - `falsification_conditions`
   - `verified`

### 主要改动区域

- `src/data_evidence.py`
- `src/event_narrative_ledger.py`
- `src/agent_analysis/contracts.py`
- `src/agent_analysis/orchestrator.py`
- `src/integrated_synthesis_report.py`
- `tests/test_three_layer_artifacts.py`
- 新增 claim ledger 测试

### 验收标准

| 验收项 | 通过标准 |
| --- | --- |
| 证据统一 | 数据、事件、调查、假说、最终 claim 都能引用同一种 evidence id |
| 权限统一 | 标题新闻、社交传闻、代理指标、市场价格都不能越权发言 |
| claim 可追问 | 最终重要自然语言结论可追到证据、反证和推理步骤 |
| 缺证据可降级 | 缺反证、缺失效条件或证据权限不足时，结论降级或阻断发布 |

### 覆盖条目

`EPI-02`、`EPI-04`、`EPI-05`、`EPI-16`  
`HAR-14`

---

## 9. 阶段 5：读者出口与语义发布闸门

**目标**：让最终报告既好读，又不越权。

读者出口不是装饰。它必须把研究结论、风险边界和个人决策翻译分开，避免把市场判断写成交易指令。

### 要做什么

1. Final 输出强制分为三类：
   - 市场判断：系统认为 NDX 当前处在什么状态。
   - 风险边界：哪些证据会让判断失效。
   - 个人决策翻译：只在用户仓位、目标、风险承受能力明确时给条件式翻译。
2. 报告 UI 改成一份报告内四层阅读：
   - 30 秒裁决。
   - 5 分钟简报。
   - 深度研究。
   - 审计重放。
3. 发布闸门加入语义条件：
   - 缺竞争假说时不能给强裁决。
   - 缺最终 Claim Ledger 时不能伪装为可完全审计。
   - 关键反证缺失时必须降级。

### 主要改动区域

- `src/agent_analysis/contracts.py`
- `src/agent_analysis/prompts/final_adjudicator.md`
- `src/agent_analysis/vnext_reporter.py`
- `src/integrated_synthesis_report.py`
- `tests/test_vnext_reporter.py`

### 验收标准

| 验收项 | 通过标准 |
| --- | --- |
| 三类分栏 | 市场判断、风险边界、个人决策翻译在结构和 UI 上分离 |
| 四层阅读 | 同一份报告内支持 30 秒、5 分钟、深度研究、审计重放 |
| 不制造确定性 | 上游语义不足时，报告明确降级，不用 UI 包装成强结论 |
| 发布闸门生效 | 缺竞争假说、claim ledger、关键反证时触发降级或阻断 |

### 覆盖条目

`EPI-03`、`EPI-15`、`EPI-16`

---

## 10. 阶段 6：全链路硬化

**目标**：确认新架构在真实运行中稳定，而不只是单元测试通过。

### 要做什么

1. 用多个真实 run 回放，覆盖不同市场状态：
   - 数据完整、无重大事件。
   - 数据异常。
   - L2 出现强事件挑战。
   - L1-L5 互相冲突。
   - 竞争假说无法胜出。
2. 加 Run Review 检查项：
   - 反馈消息是否过多或过少。
   - InvestigationReport 是否真的被 Bridge V2 使用。
   - 强反证是否触发假说分叉或降级。
   - Claim Ledger 是否覆盖最终重要结论。
3. 加 Prompt Inspector 检查项：
   - 动态调查是否读取了 forbidden context。
   - Counter-Thesis 是否被 Thesis 污染。
   - L1-L5 是否被反馈环污染。

### 验收标准

| 验收项 | 通过标准 |
| --- | --- |
| 多 run 稳定 | 不同市场场景下 artifact 链完整 |
| 成本受控 | 调查数量、预算、停止条件可见且生效 |
| 审计可重放 | 从最终结论能回到 claim、证据、调查、消息、原始阶段 |
| 失败可解释 | 被拒绝的调查、降级的结论、未解决假说都有明确原因 |

### 覆盖条目

全部 EPI / HAR 复验。

---

## 11. 完整覆盖矩阵

### EPI 覆盖

| ID | 关闭阶段 | 完成定义 |
| --- | --- | --- |
| EPI-01 | 阶段 0 | run 明确对象、口径、时间边界、数据边界和方法边界 |
| EPI-02 | 阶段 4 | 重要最终 claim 有证据、反证、推理步骤和失效条件 |
| EPI-03 | 阶段 5 | 市场判断、风险边界、个人决策翻译结构化分离 |
| EPI-04 | 阶段 1 + 4 | 阶段 1 有最小证据字段，阶段 4 统一 Evidence Passport |
| EPI-05 | 阶段 1 + 4 | 阶段 1 有最小 source/authority 字段，阶段 4 统一权威模型 |
| EPI-06 | 阶段 0 | L1-L5 输入隔离有测试保护 |
| EPI-07 | 阶段 0 | 指标越权 claim 被降级、阻断或标记 |
| EPI-08 | 阶段 2 | L2 催化账本可主动 event_challenge，也可响应 observation_inquiry |
| EPI-09 | 阶段 0 | 综合、事件、动态调查均不回写 L1-L5 |
| EPI-10 | 阶段 1 + 2 | 四类受控消息有合同，并在最小闭环中至少有真实路径 |
| EPI-11 | 阶段 0 + 2 | event_ref / evidence_ref 分离在反馈环后仍成立 |
| EPI-12 | 阶段 3 | 2-4 个竞争假说有支持、反证、诊断力和胜出/保留理由 |
| EPI-13 | 阶段 3 | 新证据触发改判时保留旧版本和改判原因 |
| EPI-14 | 阶段 3 | 主要矛盾、主导面、价格反映不靠静默兜底冒充裁决 |
| EPI-15 | 阶段 5 | 同一份报告内支持四层阅读深度 |
| EPI-16 | 阶段 0 + 4 + 5 | 数据闸门、证据闸门、语义闸门共同控制发布状态 |

### HAR 覆盖

| ID | 关闭阶段 | 完成定义 |
| --- | --- | --- |
| HAR-01 | 阶段 0 | 固定主链仍由 orchestrator 控制 |
| HAR-02 | 阶段 0 | L1-L5 不被动态化 |
| HAR-03 | 阶段 3 | Bridge 继续承担跨层关系发现，并被 Bridge V2 扩展 |
| HAR-04 | 阶段 3 | price reflection 不能用走势直接证明基本面或估值结论 |
| HAR-05 | 阶段 1 + 2 | Inquiry Router / Gap Planner 有合同并进入运行链 |
| HAR-06 | 阶段 2 | 动态 agent 只出现在受控补查或审计侧，不进入 L1-L5 主分析 |
| HAR-07 | 阶段 1 | AgentSpec 有任务、上下文、禁区、预算和停止条件 |
| HAR-08 | 阶段 1 + 2 | InvestigationReport 有强类型输出并被 Bridge V2 或综合层读取 |
| HAR-09 | 阶段 1 + 2 | 预算和停止条件在任务执行中生效 |
| HAR-10 | 阶段 0 + 2 | 动态调查 no-backflow 有测试和 artifact 证明 |
| HAR-11 | 阶段 0 + 2 | 新闻/事件侧链保持隔离，新增材料类型同样受控 |
| HAR-12 | 阶段 0 + 6 | 主链升级后仍可一键跑通 |
| HAR-13 | 阶段 3 | Counter-Thesis 独立生成，不被 Thesis 锚定 |
| HAR-14 | 阶段 4 | Final / Thesis 自然语言结论有 claim-level ledger |

---

## 12. 最小可施工切片

如果只允许先做一个切片，建议做这个：

```text
阶段 0 的地基测试
  + 阶段 1 的四类消息 / AgentSpec / InvestigationReport 合同
  + 阶段 3 的最小 CompetingHypothesis 合同
```

它不一定马上让系统变聪明，但会把未来所有施工的轨道铺好。完成这个切片后，后续每个功能都能被问：

- 它是否破坏 L1-L5 隔离？
- 它通过哪类消息触发？
- 它的 AgentSpec 允许看什么、禁止看什么？
- 它的 InvestigationReport 证据在哪里？
- 它改变了哪个竞争假说？
- 它是否需要版本化改判？
- 它最后进入了哪条 claim？

这就是最小架构闭环的价值。

---

## 13. 不建议做的事

1. **不要先做自由动态 Agent**：没有合同和边界，动态能力越强，污染越快。
2. **不要只做 UI**：上游语义不足时，UI 只会把不确定性包装得更漂亮。
3. **不要把 Evidence Passport 完全后置**：大注册表可以后做，最小证据字段必须前置。
4. **不要等反馈环完美后才做竞争假说**：没有假说分流，反馈环的调查结果会被单一路径吸收。
5. **不要让 Thesis 直接回拨 L1/L2**：所有反向追问必须经过 Inquiry Router。
6. **不要把字段存在当作质量成立**：兜底生成的 principal_contradiction、dominant_side、price_reflection_map 必须显式标记或降级。

---

## 14. 最终判断

最合理的实施路线不是“先补所有字段”，也不是“先接一堆 Agent”。正确路线是：

> 先守住干净地基，再定义受控追问合同；用最小反馈闭环让系统能补查；用竞争假说让补查结果能分叉和收敛；用证据护照和 claim 台账贯穿到底；最后把结果做成读者能展开、能审计、不会被误导的报告。

这样做的好处是：每一步都能关闭一组明确的 EPI/HAR，每一步都能测试，每一步都不需要牺牲现有主链的清洁性。

