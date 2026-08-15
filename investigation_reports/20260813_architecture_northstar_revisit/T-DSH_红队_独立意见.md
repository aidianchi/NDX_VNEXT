# T-DSH 红队 · 独立意见（外部 AI）

> 身份声明：本意见由外部 AI 红队出具，对"现有 Python 编排器""DSH（DeepSeek Harness）""要用 DSH 改造的主张"三方均不预设立场。
> 日期：2026-08-15（材料读取日）。
> 范围：只读评估；不修改任何现有文件；只新建本文件。
> 材料：工单骨架 04、六问定案 06、`系统说明书.md` 第一节与 4.1–4.7、三明治重决策对照稿、本机 `~/.dsh/` 源码与配置、`~/Downloads/dsh-session-session-db0ea455-a678-4e78-902b-5e6fed75e2a9.zip`（已解压到 `/tmp/dsh-session-redteam/` 只读）、`src/agent_analysis/orchestrator.py`。
> 引用纪律：所有 DSH 判断附本机文件路径或可复跑命令；拿不准处写"未证实"；不引用网络材料。

---

## 0. 结论先行（TL;DR）

**三选一结论：② —— DSH 只适合某层（第二层 agentic 补采的候选运行时），不能当 v1 数据链 / 治理链的编排器；v1 继续用现有 Python 编排器。**

三条失效条件见第五节。最重要的三个风险见第六节。

一句话理由：现有 Python 编排器的最硬资产不是"会调用 LLM"，而是**把 LLM 关进固定 DAG、合约 schema、落盘 prompt 审计、sha256 断点、`effective_date` 时间闸门**这一整套"LLM 外面的确定性骨架"。DSH 本机源码证明：它原生产出的是**会话级、事件溯源、挂钟时间、自由工具调用**的 agent 运行时——前两者是资产，后两者与这套系统的骨架**方向相反**。换 DSH 当编排器，等于把系统最值钱的确定性骨架拆掉，换回一个必须重新自造这些骨架的会话运行时。

---

## 1. A 面：编排层最不能丢的三件事（第一性原理）

按北极星（可靠 NDX 判断、覆盖短中长期、帮所有者做比"长期持有"更好的买卖决策）推导，编排层最不能丢的三件事是：

### 1.1 可复现：同一 `effective_date` 重跑，产物可对比、可回测

- 这是不是硬需求？**是。** 三支柱第三条"校准闭环后置"要求判断可评分、被事后评分、评分结果修正方法。如果同一时点重跑不可对比，回测与打分就是空转，"系统是否在可测量地变好"无从回答。
- 可复现的含义要说清：不是"LLM 逐字复读"（模型采样天然非确定），而是**结构级可复现**——同输入走同一条链、过同一套 schema、产物落在可比较的目录、中间态可重放、断点可续跑、降级与失败可被识别。现有系统做的正是这个层次。

### 1.2 可审计隔离：每站实际看到了什么，能落盘、能 grep 出来

- 这是不是硬需求？**是。** 五层"互不知情"、正反双方同一份证据菜单、事件不进第一层——这些隔离如果不可事后证明，就只是提示词里的口号。系统 4.1 节"轨道 > 导出 > 规矩"和 4.3 节"静态规则共享、运行时状态不共享"都建立在这条可证明性上。
- 等价手段存在吗？存在但降级：可以用"运行时由代码物理打包、模型无工具可看别的"来**事前构造**隔离，再用"每次请求的完整 prompt 落盘"来**事后证明**。二者缺一不可。

### 1.3 时间窗口纪律：`effective_date` / 不得用未来信息

- 这是不是硬需求？**是，且是最硬的一条。** 回测模式下晚于回测日的材料不得进上下文；缺口写入数据边界，不得用当前网页伪装历史。这条一旦失守，系统产出的不是"回测"而是"偷看答案"，校准闭环会系统性高估能力，所有者会基于虚假证据做买卖决策。
- 有没有等价手段？现有系统里它是显式代码实现的（`collector.py` 的 `backtest_data_boundaries` / `strict_backtest_invariants`，`orchestrator.py` 的 `_effective_date`，提示词里的 `must_not_exceed_effective_date`）。任何新编排器必须提供同等级或更强的等价物。

### 1.4 哪一条丢了会直接毁掉系统

**时间窗口纪律。** 理由：

- 它最隐蔽：可复现丢了，你会立刻发现"重跑不一样"；隔离丢了，你会立刻发现"材料串了"。时间窗口失守时，**一切看起来都正常**——报告完整、引用合法、闸门通过，只有"未来信息"悄悄混进回测，让差的判断看起来好。系统不会报警，因为被污染的就是报警器自己。
- 它污染的是整个校准闭环的底账：回测收益、胜率、失效条件全部建立在一批被未来信息污染的样本上，之后所有"方法修正"都在拟合一个作弊过的数据集。
- 可复现和可审计隔离丢了，系统是"不可信"或"不可比"；时间窗口丢了，系统是"自信地错"，这是唯一会直接让人把钱亏掉的那种失败。

---

## 2. B 面：DSH 本机源码证据逐条对照

判定档位：**原生满足 / 可等价达成 / 需自造 / 根本冲突**。

### 2.1 可复现 → 判"需自造"（审计日志部分原生，管线复现不自带）

DSH 原生满足的部分：

- 会话持久化是**事件溯源、仅追加**的："持久化单元就是现有 `SessionEvent`（事件溯源模型：日志是唯一真源）"；"仅追加；崩溃轮次会被关闭，而非截断"（`~/.dsh/profiles/node_modules/@deepseek-ai/dsh-session-persistence/README.zh.md`）。
- 磁盘上每个会话一个 `.jsonl.zstd` 日志，可解压逐行读（`@deepseek-ai/dsh-session-persistence-jsonl/README.zh.md` 的磁盘布局；实测 `~/.dsh/sessions/` 下 36 个会话日志，zip 内 session.jsonl 1118 行，含 `turn/start`、`step/start`、`tool/call`、`tool/result`、`assistant/message`）。
- headless 模式可一次性跑任务并打印最终答案、以 0/1 退出（`@deepseek-ai/dsh-headless/README.zh.md`）。

DSH 不自带、需要自造的部分：

- **没有固定 DAG 和阶段 schema。** DSH 的编排模型是"agent 循环 + 工具调用 + 可选的模型写 JS 脚本扇出"。`dsh-tool-workflow` 让模型自己写脚本编排子代理——编排逻辑本身由 LLM 生成，每一次都可能不同。
- **workflow 无断点/恢复。** `dsh-workflow` README 明确："没有日志化或恢复：脚本、子 agent 进度和中间值均不设检查点，因此进程重启后无法继续运行"（`@deepseek-ai/dsh-workflow/README.zh.md` 已知限制）。对比现有 Python 编排器的 `stage_manifest.json` + sha256 断点续跑（`orchestrator.py` `_load_stage_checkpoint` / `_record_stage_artifact`），DSH 这条是空白。
- **自动压缩会替换模型可见表面。** `dsh-compaction-basic` 默认在上下文 0.8 阈值处自动触发，把旧历史替换成 `<compacted-summary>`（`@deepseek-ai/dsh-compaction-basic/README.zh.md`）。原始事件仍留在仅追加日志里（可事后读），但**模型实际看到的是摘要**——"重放它当时看到了什么"必须额外折叠压缩边界，不是逐字 grep 就够。
- 结论：DSH 原生产出的是"完整会话考古层"，不是"可复现批处理管线"。可复现需要把现有 Python 骨架（固定阶段、schema、断点、校验器）在 DSH 里重新造一遍。

### 2.2 可审计隔离 → 判"需自造"（通用会话隔离部分可等价，域材料隔离没有）

DSH 可等价的部分：

- 子代理有 fork/spawn 两种隔离：fork 继承父对话历史，spawn 不继承；`inheritsParentContext` 字段"只用于描述，不能强制执行"（`@deepseek-ai/dsh-subagent/README.zh.md`）。
- 可继续子代理有独立持久会话，日志可单独 grep；一次性子代理"保留尽力执行的会话检查点"（同上）——注意：一次性子代理的会话在 dispose 后**可能**查不到，审计上不如可继续子代理可靠。
- 子代理可限制工具集与深度（`toolFilter`、`depthLimit`、`persona` 能力，同上），可固定继承自父级的沙箱策略。

DSH 没有、需要自造的部分：

- **文件沙箱只挡写，不挡读。** `dsh-fs-sandbox` README 原话："读取始终直接通过：所有模式都允许读取"（`@deepseek-ai/dsh-fs-sandbox/README.zh.md`）。也就是说，DSH 的 `read-only` 模式挡不住"L4 去读 L5 的数据文件"——它只阻止修改。现有系统靠的是"模型根本拿不到文件工具，只有代码打包好的 prompt 包"（`orchestrator.py` `_build_layer_input_policy` 的 forbidden 清单 + `packet_builder.py` 的 `allow_event_refs=False`）。DSH 里要达到同等隔离，只能**删除子代理的全部读文件工具**并喂预打包材料——这等于把 packet_builder 的活重新做一遍。
- **没有"证据菜单 / 允许引用名单 / 层级输入政策"概念。** 全 DSH 包内 grep `effective_date`、`backtest`、`deterministic` 零命中；`allow_event_refs`、`evidence_ref`、`layer input policy` 这类域概念零命中（本机 `~/.dsh/profiles/node_modules/@deepseek-ai/` 下检索，可复跑）。
- 结论：DSH 的隔离是"通用 agent 上下文隔离"，现有系统的隔离是"域材料隔离"。前者能证明"子代理 A 没看过父代理 B 的对话"，后者能证明"L4 没看过 L5 本次的估值以外材料"。换 DSH 后，后一种隔离必须整体自造。

### 2.3 时间窗口 → 判"根本冲突"（当主编排器）；当"被包住的工具"可降为需自造

- DSH 唯一的时间概念是**当前挂钟时间**：`dsh-time-context` 给模型注入"带时区的当前时间与经过时长"（`@deepseek-ai/dsh-time-context/README.zh.md`），默认组合还不启用，Schedule Web overlay 才挂载。
- 全 DSH 包内检索 `effective_date` / `backtest` / `point-in-time`：**零命中**（`grep -rl "effective_date\|backtest" ~/.dsh/profiles/node_modules/@deepseek-ai/` 无输出）。
- DSH 的 agent 本性是"现在去看"：bash、web、fs 工具都以当前世界为对象。回测要的是"回到过去那一天的视野"。这二者不是差一个插件，而是方向相反。
- 若硬用 DSH 当主编排器：要么把 collector 的时间边界逻辑在 TS 里重写（重写核心资产），要么让 Python 包住 DSH、把每个动作的日期边界喂进去并事后校验（那 DSH 已不是编排器，只是被编排的会话运行时）。
- 结论：**DSH 当 v1 主编排器与时间窗口纪律根本冲突**；DSH 当第二层补采运行时，时间窗口压力小（第二层当前只做"现在"的事件采集，不做历史回测，T48 已裁），但仍须自造"每条来源带采集时间戳"的镣铐。

### 2.4 附加两条（骨架 A 面第 4、5 条，简判）

- **数据层 Python 生态（Wind/pandas/SEC）**：可等价达成，但只能 shell out。DSH 宿主语言是 Node.js（`dsh` 包入口、`pnpm` profile），调用 Wind/pandas/SEC 要么每调用一次起一个 Python 子进程，要么重写。对 v1 主链（高频、大包数据）这是纯开销；对第二层补采（低频、少量工具调用）可接受。
- **治理纪律（弱来源不进主链、证据分级、发布闸门）**：需自造。这些规则现在住在 Python 的 `contracts.py` / `packet_builder.py` / schema guard / 证据注册表里；DSH 没有任何对应物。换 DSH 当编排器，要么在 TS 里重建，要么保留 Python 闸门（后者等于现有编排器继续在位）。

### 2.5 汇总表

| A 面必须能力 | DSH 本机证据 | 档位 |
|---|---|---|
| 可复现 | 事件溯源仅追加会话日志（原生）；headless 一次性跑（原生）；workflow 无检查点/恢复（缺失）；固定 DAG/schema/断点续跑（缺失）；压缩替换模型可见表面（需折叠） | **需自造** |
| 可审计隔离 | fork/spawn 子代理 + 独立子会话日志（可等价）；toolFilter/depthLimit（部分可等价）；文件沙箱"所有模式都允许读取"（挡不住读）；无证据菜单/层级输入政策（缺失） | **需自造** |
| 时间窗口 | 唯一时间概念是当前挂钟（`dsh-time-context`）；`effective_date`/`backtest` 全包零命中 | **根本冲突（当主编排器）** |

---

## 3. 对两个主张的红队攻击（各三个最强反证）

### 3.1 攻击"换 DSH 当编排器"

**反证一：DSH 是会话式 agent 运行时，不是批处理管线；它甚至不承诺工作流可恢复。**
v1 编排层是一段固定代码（`orchestrator.py` 的 `run()`），LLM 只被关在每个阶段里"按 schema 答题"。DSH 的原生单元是"一个带工具的 agent 对话"，唯一的扇出编排工具 `workflow` 让模型写 JS 脚本，且官方 README 写明"没有日志化或恢复：脚本、子 agent 进度和中间值均不设检查点，进程重启后无法继续运行"。把 v1 搬上去，等于放弃已有的 `stage_manifest.json` sha256 断点续跑，去换一个不承诺恢复的运行时。

**反证二：DSH 没有 `effective_date`，时间窗口纪律会被它自己的工具天性破坏。**
全 DSH 包零命中 `effective_date`/`backtest`；它的时间插件给的是"现在几点"。而 v1 的命门恰恰是"回到过去那一天的视野"。一个带 bash/web 工具、原生朝向"现在"的 agent，与"不得用未来信息"的回测纪律方向相反；要约束它，得在 DSH 外面再包一层 Python 时间闸门——那 DSH 就不是编排器，只是被包住的工具。

**反证三：域材料隔离必须整体重造，且 DSH 的文件沙箱只挡写不挡读。**
现有系统靠"模型无工具、只收代码打包好的 prompt 包"来隔离 L1-L5；DSH 的文件沙箱"所有模式都允许读取"，它的隔离是"子代理没看过父代理的对话"，不是"L4 没看过 L5 本次数据"。换 DSH 后，`packet_builder`、`_build_layer_input_policy`、`schema_guard`、证据注册表这一整套必须用 TS 重写。这是重写核心资产，且目前没有证据显示重写后在哪一点上会更好（未证实有收益）。

### 3.2 攻击"继续用现有 Python 编排器"

**反证一：固定 DAG 表达不了"动态补采与多轮对质"，而第二层恰恰需要这种形状。**
`orchestrator.py` 是固定顺序的链（L1-L5 → Bridge → … → Final），受控调查员被预算锁死（`max_tool_calls=1`、`max_minutes=1`，见 `_build_feedback_contract_manifest`）。第二层 agentic 补采（T48 形态 C：三档议程化补采、自由深挖专题）需要"持续探索、随时中止、会话级记忆"的运行时，Python 编排器原生不提供。这是现状主张最真实的一处硬伤。

**反证二：编排规则全在代码里，迭代成本高。**
每加一站要写 contract + packet + stage + 校验 + 测试（`contracts.py` / `packet_builder.py` / `orchestrator.py` / 测试四件套）。critic/risk 分料这类小改动都要动 `orchestrator.py` 并跑回归。agent 时代的对照实验（如论证盲 A/B）在固定代码链上以天计，在 DSH 式工作流里可能以小时计。长期看，Python 编排器有变成"自研 harness"的维护包袱。

**反证三：现有编排器自身的"可复现"也是打了折扣的，不能假装完美。**
LLM 采样非确定：同 `effective_date` 重跑，逐字产物必然不同；checkpoint 机制保证的是"已校验产物被复用"，不是"重算一致"。`_load_stage_checkpoint` 只在 `--resume-from-existing` 下生效；`_run_stage` 的多模型 fallback（`call_with_fallback`）意味着"同一份代码"在不同模型可用时产出可能来自不同模型。这些裂缝说明：现状的复现是结构级复现，不是严格重算复现；DSH 的事件溯源日志在这方面反而是更强的考古层——现状主张不应把这点当成"我们已经赢了"。

---

## 4. 特别必答：若 DSH 不能当编排器，DSH 当 v1/v2 一部分（第二层 agentic 补采）的可行性

**结论：可行，但只是"候选运行时"，且有硬条件；条件不满足就不可行，应退回自建 Python 小循环。**

### 4.1 可行的理由（DSH 与第二层天然对得上）

- 第二层要做的是**当前世界的事件采集与深挖**：查渠道、读网页、记录来源、打标签、必要时多轮补采。这正是 DSH 的强项——带工具（web/bash/fs）、持久会话、子代理扇出、每步留痕。
- 第二层**当前不做历史回测**（T48 Q4 已裁：第一层回测纪律不受影响；第二层历史研究未立项）。因此"时间窗口根本冲突"这一条在第二层被绕开，只剩下"每条来源必须带采集时间戳"的镣铐。
- DSH 的仅追加会话日志天然满足"第二层若引入主动查询，必须全程留痕（查了什么、抓到哪个 URL、什么时候）"这条调研共识（见 `investigation_reports/20260811_layer2_research/01_顶级harness与agent架构调研.md` 第 5 条）。

### 4.2 可行的硬条件（缺一条则不可行）

1. **三明治红线不变**：DSH 只在第二层内部跑，产物只进 IA 与"外部世界"展示位，且必须带认识论标签；绝不进第一层任何站（含治理链）。这条由 Python 侧把关，不由 DSH 自觉。
2. **镣铐外置到 Python**：四条镣铐（事实/解读分离、来源等级、时间戳、needs_data_confirmation 钩子）在 DSH 里没有原生物。必须把 DSH 的产出交给现有 Python 侧校验（schema + 对账），DSH 只当"会探索的手"，不当"裁判"。
3. **会话日志要导出进 run_dir**：DSH 默认把会话写在 `~/.dsh/sessions/<workspace>/<session-id>/session.jsonl.zstd`，不在本项目的 timestamped run_dir 里。要满足"落盘可 grep、可随 run 归档"，必须加一道导出/归档桥；没有这道桥，审计边界破。
4. **沙箱降级**：本机 `~/.dsh/settings.yaml` 当前默认 `danger-full-access`。第二层若用 DSH，必须至少降到 `workspace-write` 或 `read-only`，且禁掉能改写项目文件的能力；`danger-full-access` 不可接受。
5. **先过原型门槛**：T48 已裁"原型自建小循环（复用 llm_engine），harness 选型留到原型后"。只有原型证明需要"持久会话、自主探索半小时级、工具生态"时，才轮到评估 DSH；在此之前引入 DSH 违反已定裁决。

### 4.3 不可行的情形

- 若第二层最终形态被证明不需要 agentic 循环（固定流水线 + 受控调查就够），DSH 在第二层也无必要。
- 若 DSH 会话日志导出桥接的成本高到接近重写（例如要自己折叠压缩边界、解析工具结果、对上 needs_data_confirmation 的消费闭环），或 macOS 上沙箱无法可靠约束其读/写边界（未证实，需原型实测），则不应采用。
- 若第二层开始做历史研究（把时间窗口压力重新引入），DSH 的"挂钟时间本性"会再次变成根本冲突，必须先解决时间约束，再谈 DSH。

---

## 5. 三选一结论与失效条件

**结论：② —— DSH 只适合某层（第二层 agentic 补采的候选运行时），不可当 v1 数据链 / 治理链的编排器；v1 编排器维持 Python。**

**失效条件（出现任何一条，就推翻本结论）：**

1. **"DSH 不能当编排器"失效条件**：若有人证明能把现有 Python 骨架（固定 DAG、阶段 schema、sha256 断点、`effective_date` 闸门、证据注册表）在 DSH 侧**完整重建**，且 DSH 只跑这条固定 DAG、不做自由 agent 循环——则"不能当编排器"被推翻。但到那一步，DSH 只是进程容器，收益仍待证（我认为不划算，但这是推翻条件）。
2. **"DSH 在第二层只是候选"失效条件**：若第二层原型（自建 Python 小循环）被证明**无法**满足三档补采（议程化补采 / 自由深挖 / 持久会话），且 DSH 原型跑通并**通过**五项度量与四条镣铐的 Python 侧验收——则第二层采用 DSH 从"候选"升级为"采用"。
3. **"连第二层也不该用 DSH"失效条件**：若 DSH 会话日志导出到 run_dir 的审计桥接被证明不可行或成本过高，或 macOS 上 DSH 沙箱无法可靠限制写边界/工作区（实测失败），或第二层最终不需要 agentic 循环——则连第二层也退回自建小循环，结论整体走向 ③。

---

## 6. 最重要的三个风险（无论选哪边都要盯）

1. **时间窗口被工具天性侵蚀（最高风险）**。只要 DSH 以任何形式进入系统，它的 agent 就会想"现在去网上/终端看一眼"；一旦回测样本混进未来信息，系统不是"变差"，而是"自信地错"，且污染校准闭环的底账。防线：DSH 只允许出现在第二层"现在"场景；回测/第一层禁止出现 DSH 或任何挂钟时间工具。
2. **隔离从"构造性"退化为"自觉性"**。现有 L1-L5 隔离靠"无工具 + 代码打包"物理保证；DSH 的隔离靠"删工具 + 提示词 + 事后日志"。若把主链任何一站交给 DSH，隔离强度降级，且文件沙箱"所有模式都允许读取"意味着读侧隔离名存实亡。防线：主链各站继续无工具、只收 Python 打包材料。
3. **审计边界断裂**。DSH 会话日志默认在 `~/.dsh/sessions/`（zstd JSONL，含压缩摘要边界），不在 run_dir；不导出归档，就会出现"一部分审计在项目里、一部分审计在用户主目录"的分裂状态，事后复盘找不到全貌。防线：任何 DSH 会话必须在同批 run 内导出进 timestamped 目录，否则不用。

---

## 附：本意见使用的关键证据清单

项目侧：

- `investigation_reports/20260813_architecture_northstar_revisit/04_T-DSH_DSH当编排器_工单骨架.md`
- `investigation_reports/20260813_architecture_northstar_revisit/06_六问定案_定案与施工说明.md`
- `系统说明书.md` 第一节、4.1–4.7（隔离、轨道>导出>规矩、三层架构）
- `investigation_reports/20260811_sandwich_redecision/三明治重决策对照稿.md`（第二层形态、IA 唯一对质点、镣铐四条）
- `investigation_reports/20260811_layer2_research/02_第二层形态探讨稿.md`（T48：原型自建、harness 选型留后）
- `src/agent_analysis/orchestrator.py`：`run()`、`_run_stage`、`_save_json`、`_record_stage_artifact`、`_load_stage_checkpoint`、`_build_layer_input_policy`、`_build_runtime_boundary_manifest`、`_build_feedback_contract_manifest`、`_effective_date`
- `src/main.py`：`build_run_dir`（timestamped 唯一目录）、`_write_resume_hint`（source_sha256、跨日续跑降级）
- `src/core/collector.py`：`backtest_data_boundaries`、`strict_backtest_invariants`
- `src/agent_analysis/packet_builder.py`：`allow_event_refs` 默认 False

DSH 侧（均在 `~/.dsh/` 下，只读）：

- `settings.yaml`：`permission.defaultPreset: danger-full-access`
- `profiles/node_modules/@deepseek-ai/dsh-agent-loop/README.zh.md`：agent 循环驱动器、会话/轮次/步骤生命周期
- `profiles/node_modules/@deepseek-ai/dsh-workflow/README.zh.md`：工作流 seam；已知限制"没有日志化或恢复"
- `profiles/node_modules/@deepseek-ai/dsh-tool-workflow/README.zh.md`：模型写 JS 编排脚本
- `profiles/node_modules/@deepseek-ai/dsh-session-persistence/README.zh.md`：事件溯源、仅追加、日志唯一真源
- `profiles/node_modules/@deepseek-ai/dsh-session-persistence-jsonl/README.zh.md`：`.jsonl.zstd` 磁盘布局
- `profiles/node_modules/@deepseek-ai/dsh-compaction-basic/README.zh.md`：自动压缩、`<compacted-summary>` 替换模型可见表面
- `profiles/node_modules/@deepseek-ai/dsh-subagent/README.zh.md`：fork/spawn、toolFilter/depthLimit、一次性与可继续子代理
- `profiles/node_modules/@deepseek-ai/dsh-fs-sandbox/README.zh.md`："读取始终直接通过：所有模式都允许读取"
- `profiles/node_modules/@deepseek-ai/dsh-sandbox-policy/README.zh.md`：read-only / workspace-write / danger-full-access
- `profiles/node_modules/@deepseek-ai/dsh-time-context/README.zh.md`：当前挂钟时间上下文
- `profiles/node_modules/@deepseek-ai/dsh-goal/README.zh.md`：同会话目标、仅 Round 预算、无独立评估器
- `profiles/node_modules/@deepseek-ai/dsh-headless/README.zh.md`：一次性任务、打印最终答案、0/1 退出
- 可复跑检索：`grep -rl "effective_date\|backtest\|deterministic" ~/.dsh/profiles/node_modules/@deepseek-ai/` → 零命中
- `~/Downloads/dsh-session-session-db0ea455-a678-4e78-902b-5e6fed75e2a9.zip` → 解压 `/tmp/dsh-session-redteam/session.jsonl`：1118 行，事件类型含 `turn/start`、`step/start`、`tool/call`、`tool/result`、`assistant/message`，仅追加
