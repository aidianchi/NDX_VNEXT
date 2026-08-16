# T45 变体 A / A′ / B 比较证据包（证据版本 = git HEAD c66e405）

> 收集日期：2026-08-16。只读代码与文档，未改任何代码；只写本文件。
> 可信度分四档：**官方**（供应商文档/官网）、**第三方**（论文、GitHub issue、社区报告、可靠媒体）、**实测**（本仓库代码与 run 产物、本机命令复跑）、**未证实**（无公开证据）。
> 外部证据按任务要求给 URL + 日期；无法确认发布日期的官方文档给"访问日期"。
> 代码行号为当前 HEAD（c66e405）的行号。HANDOFF 中旧行号（`_run_stage` :5230、`_compose_prompt` :6384、`llm_engine.py:519-523`）在当前 HEAD 已漂移，本文件以当前行为准。

---

## 1. 三变体代价与可审计性（A / A′ / B）

### 1.1 A（代码侧检索）的留痕内容

| 证据 | 来源 | 可信度 |
|---|---|---|
| A 的可审计所得按 T38 设计原则应为"代码筛了哪 K 条、依据、排除了哪些"，筛选留痕三要素（选中 K 条 / 依据 / 被排除编号）必须全部落盘 | `investigation_reports/20260804_seven_way_audit/HANDOFF.md:109`；`:131-135` | 本地设计文件（原则，尚未实现） |
| A 目前没有实现：仓库内不存在"按该站声明问题做相关性排序再取 top-K"的代码；现有 `_sanitize_prompt_payload` 只做两类**规则性**裁剪——`_drop_low_value_synthesis_fields_for_prompt`（按黑名单删字段）与 `_slim_evidence_index_for_prompt`（压缩超长审计明细，不删任何 ref key） | `src/agent_analysis/orchestrator.py:7128-7159`（入口）、`:7187-7207`（删字段）、`:7209-7265`（压缩 evidence_index 明细） | 实测 |
| A 若实现，留痕落点已有现成管道：`prompt_audit` 每 attempt 落盘 prompt 全文、payload、原始响应、解析归一化 JSON、校验后 JSON 与 stage meta | `src/agent_analysis/orchestrator.py:5848-5894`（`_capture_prompt_attempt` / `_save_prompt_audit_text` / `_save_prompt_audit_json`）；`_run_stage` 内 `:5675,5738,5791` | 实测 |

### 1.2 A′（代码侧深度分档 + 输出 schema 必填 `unmet_information_needs` ref 枚举）在 DeepSeek 严格模式下的可强制性与限定

| 证据 | 来源 | 可信度 |
|---|---|---|
| **枚举/必填字段能放进现有输出 schema**：现有 stage 契约就是用 pydantic `Field(..., ...)` 表达必填、`Literal` 表达枚举（如 `FinalAdjudication.approval_status`、`confidence`）；给模型加必填 `unmet_information_needs`（ref 枚举）与现有机制同类，不改运行框架 | `src/agent_analysis/contracts.py:2090-2208`（FinalAdjudication 示例）；`:2106-2109`（必填枚举字段先例） | 实测 |
| **新字段自动进提示词**：`_render_contract_field_spec` 由 `model_fields` 自动生成输出字段规格（必填/形状/描述），新增 pydantic 字段无需手改提示词模板 | `src/agent_analysis/orchestrator.py:7096-7126` | 实测 |
| **严格模式能强制必填+枚举（在工具被调用时）**：`sanitize_json_schema_for_strict_tool_calling` 把每个 object 节点改成 `additionalProperties: false` 且 `required` 覆盖全部 properties；`enum` 在 DeepSeek strict 官方支持类型清单内 | `src/agent_analysis/llm_engine.py:126-157`（sanitize 核心）；`tests/test_governance_input.py:1180-1250`（红灯测试穷举 provider 硬要求） | 实测（本地）+ 官方（类型清单，见 2.5） |
| **已有"给输出 schema 动态注入 enum"的生产先例**：`_strict_tool_schema_for_stage` 接受 `schema_postprocess` 钩子；thesis / reviser 已用它把 `retained_conflicts[].conflict_id` 的取值域收紧成本轮 bridge 实际给出的编号 enum，模型物理上打不出清单外的值 | `src/agent_analysis/orchestrator.py:4425-4455`（钩子入口）、`:4664-4700`（thesis conflict_id enum 注入）、`:4691+`（reviser 同款） | 实测 |
| **重要限定：严格模式不是"必调用工具"保证**。当前代码用 `tool_choice="auto"`（因 DeepSeek 思考模式拒绝强制函数名，见 2.2），`auto` 下模型可以不调用工具、直接返回文本；此时 strict tool schema 不生效，代码回退 content 后靠 `model_cls.model_validate`（pydantic 必填校验）与 `_run_stage` 重试兜底。即 A′ 的必填/枚举是"工具被调用时严格 schema 强制 + 任何路径 pydantic 校验兜底强制"，不是单靠 DeepSeek strict 的绝对强制 | `src/agent_analysis/llm_engine.py:555-572`（tools + strict + `tool_choice="auto"`）、`:616-622`（无 tool_calls 回退 content）、`src/agent_analysis/orchestrator.py:5675-5788`（解析→pydantic 校验→重试） | 实测 |
| **A′ 零往返、零新增失败面成立**（相对 A 只加一个输出字段；相对 B 不加循环与工具结果回灌）：现有 `_run_stage` 每 attempt 只调用一次 `call_with_fallback`，取 `tool_calls[0].function.arguments` 当输出，无工具结果回灌 | `src/agent_analysis/orchestrator.py:5591-5675`（`_run_stage` 单次调用路径）、`src/agent_analysis/llm_engine.py:616-622`（工具调用结果直接当输出，无回灌） | 实测 |

### 1.3 B（模型侧循环取用）的事前取用意图审计价值

| 证据 | 来源 | 可信度 |
|---|---|---|
| B 的审计所得是"模型**事前**主动要了哪几条"（取用意图日志）；A′ 得到的是**事后**缺料回报（`unmet_information_needs`），两者时点不同，A′ 可直接反哺筛选器 | `HANDOFF.md:131-135`（2026-08-05 订正后的三变体定义） | 本地设计文件 |
| 当前架构工具通道是"交答卷"的载体，不是"要材料"的能力：站点无法自主取用，B 需要把单次调用改成循环并加工具结果回灌 | `HANDOFF.md:119-121`；代码同 1.2 末行 | 实测（本地） |
| VXN 事件显示模型"缺料自白"的现状：模型在散文里说出"本轮输入未提供 VXN 数值和分位"，是诚实救了系统而非机制救了系统；A′ 就是把这类散文自白搬进 schema | `HANDOFF.md:68-76`（含 MAST 论文 FM-2.4 Information withholding 的转引） | 本地转引论文（MAST 原文未在本包复核） |

### 1.4 本仓库当前全量推送的输入成本实测数字与重复率

| 证据 | 来源 | 可信度 |
|---|---|---|
| 最近真实 run `20260731_002156` 全量输入 **963,419** token / 输出 **124,313** token / 总计 1,087,732 token，输入占 88.6% | `output/analysis/vnext/20260731_002156/final_adjudication.json` → `token_usage.total`；与 `HANDOFF.md:211` 数字逐位一致 | 实测 |
| L1-L5 五层合计输入 440,691 token，占全量输入 **45.7%**（HANDOFF 写"约 44%"，差异为逐站复算口径） | 同上 `token_usage.l1..l5` 求和；`HANDOFF.md:211` | 实测 |
| 治理四站（critic / risk / reviser / final_adjudicator）合计输入 292,470 token，占全量输入 **30.4%** | 同上 `token_usage.critic/risk/reviser/final_adjudicator` 求和 | 实测 |
| 治理四站提示词长度 235,479 / 236,788 / 242,402 / 247,717 字符；两两 SequenceMatcher 相似度 **95.2%–97.8%**；逐字符最长公共前缀仅 **387–388 字符（约 0.16%）**——角色模板在前、数据在后，前缀缓存基本吃不到 | `output/analysis/vnext/20260731_002156/prompt_audit/{critic,risk,reviser,final_adjudicator}/attempt_1.prompt.txt` 本机复算；`HANDOFF.md:209-210` | 实测 |
| 治理四站 `governance_input.key_evidence_refs` 四站**完全相同**，JSON 序列化 **116,150 字符 × 4 = 464,600 字符**重复传输 | 同上 `attempt_1.payload.json` 本机复算（critic/risk/reviser/final 四份相等） | 实测 |
| thesis↔counter_thesis 提示词相似度本机复算 **87.2%**（HANDOFF 写 88.0%，差异为复算口径） | 同上 `thesis` 与 `counter_thesis` 的 `attempt_1.prompt.txt` 本机复算 | 实测 |
| **前缀缓存当前不可测**：`token_usage` 新记 `prompt_cache_hit_tokens`，但 provider 未给时记 `None` 不记 0；任何"靠缓存省钱"的估算在补到真实命中数之前都是空的 | `src/agent_analysis/llm_engine.py:608-610`、`:696-702`、`:874-886`；`HANDOFF.md:265` | 实测 |

---

## 2. B 的失败面证据（重点）

### 2.1 DeepSeek API 官方 tool_choice 取值与行为

| 证据 | 来源 | 可信度 |
|---|---|---|
| DeepSeek Chat Completions API 的 `tool_choice` 取值：`none`（模型不调用工具，直接生成消息）、`auto`（模型可在"生成消息"与"调用一个或多个工具"之间选择）、`required`（模型必须调用一个或多个工具）；指定函数名 `{"type":"function","function":{"name":"my_function"}}` 强制调用该工具；**`auto` 是 tools 存在时的默认值**，`none` 是 tools 不存在时的默认值 | https://api-docs.deepseek.com/api/create-chat-completion/ （访问日期 2026-08-16） | 官方 |
| 官方文档明确 `auto` 下模型可以选择不调用工具——"不调用工具、直接返回"是**设计内行为**，不是偶发故障；官方文档不提供该选择的发生率数字 | 同上 URL | 官方 |
| `required` 的官方语义是"必须调用一个或多个工具"，看起来可收紧 B 的失败面；但 DeepSeek 思考模式下的实际行为见 2.3，`required` 当前被 400 拒绝 | 同上 URL + 2.3 证据 | 官方 + 第三方 |

### 2.2 tool_choice=auto 下"不调用工具、直接返回"的已知发生率

| 证据 | 来源 | 可信度 |
|---|---|---|
| 官方文档只描述 `auto` 的行为（可生成消息或调用工具），**不给出不调用工具的概率数字**；公开可靠的发生率数据未找到——**精确发生率：未证实** | https://api-docs.deepseek.com/api/create-chat-completion/ （访问日期 2026-08-16） | 官方（行为描述）/ 未证实（发生率） |
| 本地代码基于 2026-07-26 真实 API 复现承认该失败分支存在：`_call_ai` 在 strict 路径下若 `tool_calls` 为空，记 warning 并退回 `message.content`；注释写明 `auto` 下模型可选择不调用 | `src/agent_analysis/llm_engine.py:566-571`（注释，真实 API 复现记录）、`:616-622`（空 tool_calls 回退分支） | 实测（现象存在，本仓库未记发生率） |
| 社区报告：DeepSeek-V3 在 Continue（VSCode 工具代理）中启用 `tool_use` 后不主动使用内置工具完成任务（定性报告，无发生率数字） | https://github.com/continuedev/continue/issues/4800 （创建 2025-03-25，关闭 2025-08-06） | 第三方 |
| vLLM 社区（针对自托管 DeepSeek-V3）：`tool_choice="auto"` 下"是否调用工具"完全交给模型，模型行为不可靠（该帖描述的是过度调用方向，佐证 auto 下行为不可控） | https://discuss.vllm.ai/t/deepseek-v3-tool-choice-auto-not-working-but-tool-choice-required-is-working/1006/4 （2025-08-25） | 第三方 |

### 2.3 DeepSeek 思考模式与 tool_choice 的真实限制（官方 repo issue，B 的强制收紧路线被封死）

| 证据 | 来源 | 可信度 |
|---|---|---|
| `deepseek-v4-pro` / `deepseek-v4-flash` **默认开启思考模式**，在思考模式下 `tool_choice="required"` 与指定函数名 `tool_choice={"type":"function","function":{"name":...}}` 均被 HTTP 400 拒绝，错误原文 "Thinking mode does not support this tool_choice"；`tool_choice="auto"` 可用；`deepseek-chat`(V3.2) 不受影响 | https://github.com/deepseek-ai/DeepSeek-V3/issues/1376 （创建 2026-05-30，更新 2026-08-14，状态 open） | 第三方（DeepSeek 官方 repo issue，用户复现实测） |
| 该 issue 指出这直接打碎所有主流 agent 框架（LangChain / AutoGen / CrewAI 等）用"指定函数名 tool_choice 绑定结构化输出"的路线——B 若想用 `required` 或命名 tool_choice 把"不调用工具"的概率压到零，当前 DeepSeek V4 上**做不到** | 同上 URL | 第三方 |
| 本地代码与该 issue 独立互证：本仓库注释记录同一条错误，并把 strict 路径定为 `tool_choice="auto"` | `src/agent_analysis/llm_engine.py:566-572` | 实测 |

### 2.4 强制工具调用下的另一失败面：arguments 无效 JSON（长 prompt 下 40–60%）

| 证据 | 来源 | 可信度 |
|---|---|---|
| `deepseek-v4-flash` 在关闭思考模式 + 命名 `tool_choice` 强制调用时，长 prompt（~14k token）下间歇性输出**无效 JSON 的 tool_call arguments**（枚举值不带引号），坏窗口内 **40–60% 的调用失败**；短 prompt + 小 schema 干净；同字节请求的失败率随时间波动（5/10 → 9/10） | https://github.com/deepseek-ai/DeepSeek-V3/issues/1541 （创建 2026-08-02，状态 open） | 第三方（DeepSeek 官方 repo issue，用户实测） |
| 同一 issue 报告思考模式拒绝命名 tool_choice（再次佐证 2.3），且原生 `/chat/completions` 会原样返回损坏字符串、Anthropic 兼容端点会静默吞掉（返回空 input） | 同上 URL | 第三方 |

### 2.5 严格模式（strict: true）与 function calling 的关系

| 证据 | 来源 | 可信度 |
|---|---|---|
| 严格模式**允许 function calling**，且思考/非思考模式都支持；启用条件：base_url 用 `https://api.deepseek.com/beta`，`tools` 参数里所有 function 的 `strict` 设为 true；服务端会校验 JSON Schema，不合规或含不支持类型会返回错误 | https://api-docs.deepseek.com/guides/tool_calls/ （访问日期 2026-08-16） | 官方 |
| 严格模式的作用范围是"模型输出 tool call 时严格遵守 Function 的 JSON Schema"——它是**格式保证，不是调用保证**：官方定义不含"强制模型调用工具"的语义 | 同上 URL | 官方 |
| 严格模式支持的 JSON Schema 类型：object / string / number / integer / boolean / array / **enum** / anyOf；object 必须 `additionalProperties: false` 且 `required` 覆盖全部 properties；不支持 minLength/maxLength/minItems/maxItems（本仓库 sanitizer 与红灯测试已按此实现） | 同上 URL；`src/agent_analysis/llm_engine.py:126-157`；`tests/test_governance_input.py:1180-1250` | 官方 + 实测 |
| 本仓库严格模式是 opt-in 环境变量开关，白名单 7 个 stage（bridge/thesis/event_card_interpreter/event_section_summary/reviser/final/critic），未设置环境变量或不在白名单则逐字节走原 json_object 路径 | `src/agent_analysis/orchestrator.py:4420-4455` | 实测 |

### 2.6 循环化多轮工具调用对前缀缓存 / 成本的影响证据

| 证据 | 来源 | 可信度 |
|---|---|---|
| DeepSeek 官方缓存规则：缓存命中要求后续请求**完整匹配**已持久化的"缓存前缀单元"；公共前缀持久化发生在请求边界、检测到跨请求公共前缀后，以及长输入/输出的固定 token 间隔切块处；命中结果通过 `prompt_cache_hit_tokens` / `prompt_cache_miss_tokens` 返回 | https://api-docs.deepseek.com/guides/kv_cache/ （访问日期 2026-08-16） | 官方 |
| 官方缓存规则对工具循环的含义：工具调用回合中 assistant 的 tool_calls 与 tool 结果消息、思考模式需回传的 `reasoning_content` 都会进入后续请求的前缀；多轮 append-only 也不保证缓存持续增长（见下条第三方实测） | 同上 URL + 下条 | 官方 + 第三方 |
| Azure AI Foundry 上 DeepSeek-V4 多轮工具调用实测（3–6 个模型调用、append-only 历史）出现三种不稳定行为：①逐轮 cached_tokens 全为 0；②缓存正常增长；③缓存停在 1792 不再增长、或首轮命中反而比次轮高——append-only 工具历史**不保证**缓存逐轮累积 | https://learn.microsoft.com/en-au/answers/questions/5969852/azure-ai-foundry-prompt-caching-with-multi-turn-to （提问 2026-08-08） | 第三方（Microsoft Q&A 社区实测） |
| 工具型 agent 的循环成本实测：Hermes-agent 在 Anthropic 系 multi-step 中，工具 schema（~11.8k token）未打缓存断点被每轮全价重发，占输入账单 ~70%；3 轮短任务（read robots.txt and summarize）实测 input_tokens 146,820、成本 $0.45 | https://github.com/NousResearch/hermes-agent/issues/20880 （创建 2026-05-06，关闭 2026-08-01） | 第三方实测 |
| 本仓库当前全量推送"逐字符最长公共前缀仅 368-388 字符"（1.4），说明现状本身几乎无前缀缓存收益；B 循环化会在 `_run_stage` 内新增多轮往返，每轮前缀随工具结果变化，缓存收益更不确定；在 `prompt_cache_hit_tokens` 有真实数据之前，B 的"省 20%"没有任何可测依据 | `HANDOFF.md:210,265`；1.4 实测 | 实测 + 未证实（B 省 20% 无证据） |

---

## 3. A′ 与 B 的替代关系证据（检索 / 上下文工程领域）

| 证据 | 来源 | 可信度 |
|---|---|---|
| Anthropic 上下文工程总纲：当前存在两类上下文策略——**预推理期嵌入检索**（pre-inference embedding-based retrieval，先筛好再进上下文）与 **just-in-time 按需取用**（模型用工具在运行时取用）；两种都在被使用，并明确存在**混合策略**（先预取一部分求速度，再允许自主探索）；运行时探索的代价是更慢，且需要正确的工具与启发式引导 | https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents （访问日期 2026-08-16） | 官方 |
| Claude Code 实践 = 混合模型：`CLAUDE.md` 文件前置注入上下文，`glob` / `grep` 等原语允许 just-in-time 按需取文件；说明"代码预筛 + 按需取用"不是互斥替代，可以组合 | 同上 URL | 官方 |
| Anthropic 对"模型自己取用"的风险提示：运行时探索更慢；若没有正确工具和启发式，agent 会误用工具、追死胡同、漏掉关键信息——这与 B 的失败面同源 | 同上 URL | 官方 |
| 学术证据（事后缺口回报可作为检索回路控制器）：S2G-RAG 提出显式控制器 S2G-Judge，每轮判断当前证据是否充分、不充分则输出**结构化 gap items**（描述缺什么），再把 gap 映射为下一轮检索 query——即"事后缺料回报驱动下一轮筛选"在学术上是成熟可实现的组件，A′ 的 `unmet_information_needs` 与之同构 | https://arxiv.org/abs/2604.23783 （v1 提交 2026-04-26，ACL 2026 主会录用） | 第三方（论文） |
| "模型主动索取 vs 代码预筛 + 事后缺口回报"哪种审计价值更高：**没有找到直接比较两种留痕方式审计价值的论文或产品文档——未证实**。间接证据仅能支持：①Anthropic 认为二者可混合、按任务选择；②事后 gap 回报足以作为筛选器的反馈信号（S2G-RAG）；③事前取用意图日志是 agentic 产品的常见可观测性来源（Anthropic 上下文工程文中以工具调用作为 agent 上下文管理的一等公民），但"不可被事后回报替代"这一强命题无公开证据 | 上述来源综合；强命题本身：未证实 | 未证实 |
| 本仓库 VXN 事件的机制性教训支持 A′ 的事后回报价值：模型已能在散文里准确说出缺什么（"本轮输入未提供 VXN 数值和分位"），把这句话搬进 schema 即"被机制救"；MAST 论文称这类"信息扣留"失败为 FM-2.4 Information withholding | `HANDOFF.md:68-76`（转引 arXiv 2503.13657，本包未读原文） | 本地转引论文 |

---

## 4. 成本估算素材（本仓库 + 外部框架）

### 4.1 本仓库单次 run 的结构与体量（代码事实）

| 证据 | 来源 | 可信度 |
|---|---|---|
| **16 个 stage 类型**：L1-L5 分析师（5 个，`stage_key` 运行时拼 `l1_analyst..l5_analyst`）、bridge、thesis、counter_thesis、critic、risk、reviser、final、event_card_interpreter（每事件一实例）、event_section_summary、controlled_investigation、integrated_adjudicator；其中 `controlled_investigation` 与 `integrated_adjudicator` **不走 `_run_stage`** | `src/agent_analysis/orchestrator.py:498-787`（`run()` 主流程）、`:959-999`（五层）、`:2053-2136`（controlled_investigation 直呼 call_with_fallback）、`src/main.py:800-806`（integrated_adjudicator 经 llm_caller）；stage_key 清单见 `:557,573,597,613,646,692,714,967,1659,1825,2805,2861,4478,4513` | 实测 |
| 最近 run 实际 22 个 stage 实例（10 个 event_card_interpreter 实例 + 12 个固定站），见 stage 诊断清单 | `output/analysis/vnext/20260731_002156/llm_stage_diagnostics.json`（stages 键逐站列出） | 实测 |
| **3 个 LLM 调用入口**：①`_run_stage` → `call_with_fallback`（全部主流程站点）；②`_run_controlled_investigations` 直呼 `call_with_fallback`；③`write_integrated_synthesis_report` 经 `main.py` 传入的 `llm_caller` 调用（`stage_name="integrated_adjudicator"`） | `src/agent_analysis/orchestrator.py:5671`（入口①）、`:2136`（入口②）；`src/main.py:805`（入口③接线）；`src/integrated_synthesis_report.py:398`（入口③实际调用点） | 实测 |
| **治理四站共享包大小**：`governance_input.key_evidence_refs` 四站完全相同的 JSON 块 **116,150 字符**，累计传输 464,600 字符；四站提示词全文 235,479–247,717 字符，两两相似度 95.2–97.8%，公共大块（thesis 摘要到 evidence registry 摘要一段）约 197,133 字符 | 1.4 同源实测 | 实测 |
| 单次 run 全量输入 963,419 token / 输出 124,313 token；L1-L5 占输入 45.7%，治理四站占 30.4%，thesis+counter_thesis 占 15.5% | 1.4 同源实测 | 实测 |

### 4.2 外部框架循环式工具调用的典型额外往返成本

| 证据 | 来源 | 可信度 |
|---|---|---|
| 工具型 agent 循环的额外输入成本可量化：3 轮短任务（Anthropic 系）实测 input 146,820 token、成本 $0.45，其中 ~70% 输入账单是每轮全价重发的工具 schema（11.8k token × 未缓存） | https://github.com/NousResearch/hermes-agent/issues/20880 （2026-05-06） | 第三方实测 |
| 多轮工具调用的前缀缓存收益不稳定（DeepSeek-V4 经 Azure）：append-only 历史下 cached_tokens 出现全 0 / 停增 / 首轮高于次轮三种模式，不能假设"循环化后前缀缓存会兜住增量成本" | https://learn.microsoft.com/en-au/answers/questions/5969852/azure-ai-foundry-prompt-caching-with-multi-turn-to （2026-08-08） | 第三方实测 |
| DeepSeek 官方缓存命中规则（完整匹配缓存前缀单元）可用于估算 B 的往返成本上限，但本仓库 `prompt_cache_hit_tokens` 尚无真实命中数据，任何具体百分比估算都属未证实 | https://api-docs.deepseek.com/guides/kv_cache/ （访问日期 2026-08-16）；`llm_engine.py:610,636,702,885` | 官方 + 实测 |

---

## 5. 对预注册规则逐条的原始证据映射（不给最终建议）

> 规则原文见 `00_预注册决策规则.md` 第三、四节。这里只列"哪些证据支撑、哪些反驳"，最终结论由报告按规则得出。

| 规则 | 支撑证据 | 反驳/缺口证据 | 本包证据状态 |
|---|---|---|---|
| 规则1：A′ 优先于 A（A′ 能进现有输出 schema、不加往返、不新增失败面） | 必填+枚举可入 pydantic 契约（`contracts.py:2106-2109` 先例）；`_render_contract_field_spec` 自动渲染新字段（`orchestrator.py:7096-7126`）；strict sanitize 强制 `required` 全覆盖 + enum 支持（`llm_engine.py:126-157`）；已有 schema_postprocess 动态 enum 注入先例（`orchestrator.py:4664-4700`）；`_run_stage` 单次调用、无回灌（`orchestrator.py:5671`，`llm_engine.py:616-622`） | "严格模式可强制"须加限定：`tool_choice="auto"` 下模型可不调用工具，strict schema 不生效，最终靠 pydantic 校验+重试兜底（`llm_engine.py:566-622`）——不新增失败面仍成立，但"严格模式绝对强制"不成立 | 支撑成立（含限定） |
| 规则2(a)：B 的"事前取用意图"审计价值无法被 A′"事后缺料回报+代码筛选留痕"替代 | Anthropic 上下文工程支持混合策略（预筛+按需取用），事前工具调用日志是 agent 可观测性的一等公民（Anthropic 文）；S2G-RAG 证明事后结构化 gap 能作为检索回路控制信号（arXiv 2604.23783） | **无任何直接研究证明"事前意图不可被事后回报替代"——未证实**；Anthropic 与 S2G-RAG 反而支持事后缺口回报是有效替代组件 | 不足以满足 (a)（强命题未证实） |
| 规则2(b)：`tool_choice="auto"` 下模型不走工具通道的失败概率能被代码/严格模式约束到可忽略 | 官方 `required` 语义"必须调用工具"（api-docs create-chat-completion） | DeepSeek V4 思考模式 400 拒绝 `required` 与命名 tool_choice（GitHub issue #1376，2026-05-30）；强制命名时 v4-flash 长 prompt 下 40–60% 无效 JSON（issue #1541，2026-08-02）；官方 `auto` 允许不调用且无概率数字；精确不调用率未证实 | 不利于 (b) |
| 规则2(c)：B 循环化增量成本比当前全量推送省 ≥20% | 全量推送实测 963,419 input token；治理四站共享 116,150×4、相似度 95.2–97.8%（可压缩空间存在） | 官方缓存规则 + Azure 实测显示多轮工具调用缓存不稳定；Hermes-agent 实测工具循环有 ~70% 工具 schema 重放开销；本仓库 `prompt_cache_hit_tokens` 无真实数据，"省 20%"不可测（`HANDOFF.md:265`） | 无证据支持省 20%；有反向成本风险证据 |
| 规则2(d)：B 不破坏五层隔离与 prompt_audit 字节级审计 | prompt_audit 现有落盘管道完备（`orchestrator.py:5848-5894`）；隔离是构造侧机械导出（`HANDOFF.md:160-175`） | B 循环化需在 `_run_stage` 内新增工具回灌与每轮审计落盘，当前无此机制；能否保持字节级审计取决于设计，自动满足未证实 | 可设计但未证实自动满足 |
| 迁移规则1–5（00 文件第二节） | 第0问已另案结清：五缺陷 harness 层根因 = 0 → 按规则不建议迁移，重建第3/4问终止 | 本包不重复第0问；本包无目标 harness 关闭机制/增益/迁移成本证据（按规则无需展开） | 依 01 文件结论 |

---

## 6. 未证实清单（如实交代）

1. `tool_choice="auto"` 下 DeepSeek 模型"不调用工具、直接返回"的**精确发生率**：未证实（官方只描述行为，社区只有定性报告；本仓库代码承认分支存在但未记录发生率）。
2. "模型事前取用意图的审计价值**不可**被 A′ 事后缺料回报 + 代码筛选留痕替代"这一强命题：未证实。
3. B 循环化相对当前全量推送能省 ≥20% 输入成本：未证实（缓存命中无真实数据，外部证据反而提示循环有额外开销）。
4. MAST 论文 FM-2.4 Information withholding 原文细节：本包未读原文，仅转引 HANDOFF。
5. 外部框架（目标 harness）自动上下文注入机制、迁移成本、等价审计落盘：本包未调研（第0问为 0，按预注册规则重建第3/4问终止展开）。

---

## 附：证据版本

- git HEAD 短哈希：**c66e405**（分支 `docs/consolidation`）
- 本包收集日期：2026-08-16
- 只读纪律：未改代码、未改 `00_预注册决策规则.md`、未提交 git；只写本文件。
