# Critic / Risk Sentinel 冗余度调查

- 日期：2026-07-25
- 调查者：Sonnet 5 worker（受主对话委托，纯只读调查，未改动任何 `.py` / `.md`（本文件除外））
- 触发问题：用户怀疑 critic 与 risk_sentinel 两个 agent 站点是"按人类职位硬拆、而非按上下文隔离需要拆"的反例，可能违反本项目"Context-first, role-second"的核心架构原则。
- 范围：只回答"这两个站点该不该合并/怎么改"，不涉及其他 agent 站点（thesis/reviser/final_adjudicator 等）的冗余问题。

---

## 一、已知前提（用户提供，未重新验证）

1. `src/agent_analysis/orchestrator.py:394-413`：critic 和 risk 两个 stage 拿到逐字相同的 `payload={"governance_input": _model_dump(gov_input_critic)}`，同一个 `GovernanceInputPacket` 对象序列化后原样发给两边，区别只在 `prompts/critic.md` vs `prompts/risk_sentinel.md` 两份说明书。
2. `orchestrator.py:418-455`：`schema_guard_retry` 分支在 Schema Guard 发现结构问题时，把 critic 和 risk **一起**各重跑一次（`stage_name="critic_retry"` / `"risk_retry"`），不做精细定位。
3. 20260725_145833 这次真实跑里，critic `attempts:2`、risk `attempts:1`，需要核实这次 critic 的重试是不是 schema_guard_retry 触发的。

## 二、代码复核（本次新读，佐证前提，未发现出入）

- `orchestrator.py:394-413` 确认：`gov_input_critic` 在 `critique = self._run_and_save(...)` 之前构建一次，critic 和 risk 两个 `_run_and_save` 调用共享同一个已序列化 payload，字节级相同。
- `orchestrator.py:418-455` 确认：`schema_guard_retry` 分支触发条件是 `not schema_report.passed and (schema_report.structural_issues or schema_report.missing_fields)`，命中后**不做修复目标定位**，直接重建 `gov_input_critic_retry`（同一个 packet，只是多注入 `schema_report` 反馈）并把 critic、risk 都重跑一次，stage_name 分别记为 `critic_retry`、`risk_retry`。这与用户前提二一致。
- `orchestrator.py:4611-4682`（`_run_stage`）确认存在**另一层、更内侧的重试机制**：每个 stage（不只 critic/risk，thesis/reviser 等全部适用）自己有 `for attempt in range(1, self.max_node_retries + 1)` 循环（`max_node_retries` 默认为 2，见 `orchestrator.py:312`），只要该 stage 自己的输出没通过 Pydantic 合约校验（空响应、JSON 解析失败、字段校验失败），就在**同一个 stage_key 内部**原地重试，不涉及其他 stage，stage_name 仍是原名（如 `"critic"`），不会变成 `"critic_retry"`。

## 三、第三条核实结论：critic 那次重试是普通单站点重试，不是 schema_guard_retry

读 `output/analysis/vnext/20260725_145833/llm_stage_diagnostics.json` 里 `stages.critic`：

```json
{
  "stage_key": "critic",
  "stage_name": "critic",
  "attempts": 2,
  "errors": [
    {
      "attempt": 1,
      "kind": "schema_validation_error",
      "message": "1 validation error for Critique\noverall_assessment\n  String should have at most 200 characters [type=string_too_long, ...]"
    }
  ]
}
```

关键判据：
1. **`stage_name` 是 `"critic"`，不是 `"critic_retry"`**。若是 schema_guard_retry 触发，orchestrator.py:432-433 会把 stage_name 写成 `"critic_retry"`，产物文件名虽然仍是 `critique.json`（会覆盖），但 diagnostics 里必然多出一条 `critic_retry` 记录。本次 diagnostics 的 stage 列表里没有 `critic_retry` / `risk_retry`，只有一条 `critic`（`attempts:2`）和一条 `risk`（`attempts:1`）。
2. **报错内容是 Pydantic 字段级校验失败**：`Critique.overall_assessment` 字段有 `max_length=200`（见 `contracts.py:1774`），attempt 1 实测原文（`prompt_audit/critic/attempt_1.response.raw.txt`）：

   > "Thesis 在结构上逻辑清晰，主要矛盾抓取准确。但一个 major 问题是：盈利修正数据（L4.get_ndx_earnings_revision_metrics#slope_30d）有 pending_validation 标签且 44.96% 权重被标志……若未察觉此风险，则"脆弱平衡"可能比写得更脆弱。"

   这段文字实测超过 `max_length=200`，触发 `_run_stage` 内部的 Pydantic 校验失败分支，`_run_stage` 把报错文本回注提示词（"上一次返回未通过结构校验……"）后原地重试，attempt 2 生成了更短的 `overall_assessment`（即最终 `critique.json` 里"结论方向与证据合计不完全一致：……"这一版）并通过校验。
3. risk 没有跟着重试，是因为它自己 attempt 1 就一次性通过了 Pydantic 校验（`risk.attempts=1, errors=[]`），schema_guard_retry 分支根本没有被触发（此次 run 若 `schema_guard_report.json` 已通过或没有 structural_issues/missing_fields，就不会进入 418-455 行的联动重跑；即便进入，也应该同时看到 critic_retry 和 risk_retry 两条记录，而不是只有 critic 单独多一次 attempt）。

**结论：这次 critic 的 `attempts:2` 是"某个字段写超长"引发的普通单站点自愈重试，与用户前提二描述的 schema_guard_retry 联动重跑是两套完全不同的机制，本次没有证据显示后者被触发过。** 对比基线 run（`20260724_223804`）：critic 和 risk 都是 `attempts:1, errors:[]`，也印证 145833 这次是偶发的字段超长，不是常态。

---

## 四、实质内容比对：critic 与 risk 在说不同的事，还是同一件事换了个说法？

用两次真实跑（`20260724_223804`、`20260725_145833`）逐条对照，结论是**部分真实不重叠，部分是同一观察换了个 schema 外壳**，证据如下。

### 4.1 强重叠证据（20260725_145833 run，最清楚的一组）

`critique.json` 的 `overall_assessment`：

> "结论方向与证据合计不完全一致：利多证据（**流动性改善、盈利修正向上**）被低估，需重新校正赔率评估。"

`critique.json` 的 `cross_layer_issues[0]`：

> "L1**流动性改善（净流动性动量转正、M2回升）**→ L5价格反弹的传导机制被忽略，仅强调利率对估值的压制，缺乏对流动性支撑作用的讨论。"

对照 `risk_boundary_report.json` 的 `opportunity_costs[1]`：

> "condition": "若**流动性改善信号（净流动性动量转正、M2 回升）**被低估，且市场保持对利率压力的过度关注"
> "missed_payoff": "当利率环境稳定后，流动性支撑可能推动估值修复，但等待确认可能错过最佳配置时机"
> "evidence_refs": ["L1.get_net_liquidity_momentum", "L1.get_m2_yoy", "L2.get_hy_oas_bp"]

两份文件用**几乎相同的措辞**（"净流动性动量转正、M2 回升"逐字重复）描述**同一个底层事实**（流动性改善信号被低估），只是 critic 把它包装成"逻辑一致性缺陷"（cross_layer_issues：传导机制被忽略），risk 把它包装成"机会成本"（opportunity_costs：等待确认可能错过配置时机）。这不是两个视角看到了不同的东西，是**同一个观察，套了两层不同的 schema 外壳**。

再看 `critique.json` 的 `issues[0]`（target=`thesis_payoff_assessment`）：

> "赔率评估声称赔率不利，但未充分加权**流动性改善和盈利修正向上**的正面因素；技术面长期结构未破，短期下跌可能提供赔率改善机会，而非单纯不利。"

这条与上面 risk 的 `opportunity_costs[1]` 本质上是同一句话的两种写法：Critic 说"payoff_assessment 没有加权正面因素"，Risk 说"低估流动性改善信号会错过配置时机"——都是在指出"thesis 对流动性利多信号权重不足"这一件事。

### 4.2 中度重叠证据（20260724_223804 run）

`critique.json` 的 `cross_layer_issues[0]`：

> "L1 边际流动性改善信号（净流动性动量转正）在 thesis_environment 中被提及，但在 payoff_assessment 和 portfolio_actions 中未被整合，导致正面信号与最终防守动作之间的因果链断裂。"

`risk_boundary_report.json` 的 `opportunity_costs[0]`：

> "condition": "若价格已反映利率见顶和盈利韧性而系统仍等待所有确认"
> "missed_payoff": "可能错过利率意外下行或M7财报超预期引发的快速反弹，赔率在恐惧区间可能已改善"

这一组比 4.1 松散一些——critic 讲的是"L1 流动性信号没被整合进最终动作"，risk 讲的是"若价格已部分反映利多而系统仍等确认，会错过反弹"——主题同属"上行信号被低估/未整合"这一大类，但触发的具体证据链（L1 流动性 vs 利率见顶+盈利韧性）不完全一致，比 4.1 的逐字重复弱一档。这说明**重叠程度不是稳定的，会随 run 波动**，但方向是一致的：只要 thesis 存在"利多信号未被充分体现"这类特征，critic 和 risk 大概率会各自独立地抓到它，只是抓取的具体证据组合不完全相同。

### 4.3 Risk 独有、Critic 完全没有覆盖的内容

两次 run 里，risk_boundary_report.json 都包含 critic 从未产出过的三类结构化内容：

1. **`boundary_status`**：7 个风险边界的 safe/warning/breached 三态标注（如 `"breadth_deterioration": "breached"`），这是一个固定分类体系的枚举校验，critic 的自由文本 `issues` 列表里没有对应物。
2. **`conflict_matrix_check`**：13 种冲突矩阵（A-M）的布尔值显式检查（`"C_expensive_valuation_vs_strong_trend": false` 等），这是 `RESEARCH_CANON.md`/`NDX_COMMAND_V9.txt` 定义的固定跨层冲突分类法，critic 完全不检查。
3. **`failure_conditions`**：带 `probability`（medium/low/low-medium）和 `triggered_by`（evidence_ref 列表）的前瞻情景枚举，格式化程度远高于 critic 的散文式批评。例如 145833 run 里 risk 列出"若 QQQ 跌破 200 日均线（643.17）且成交量显著放大，同时广度未改善"这类具体价位+成交量条件，critic 在同一次 run 里完全没有触及任何具体点位或均线条件。

`risk_boundary_report.json`（145833）`must_preserve_risks` 里还有一条纯技术面细节：

> "短期技术破裂风险：价格紧贴 20 日 Donchian 下轨（682.48），MACD 死叉且 OBV 派发，若放量跌破可能测试 200 日均线；RSI 39 未超卖，下跌动能未衰竭"

这条在两次 run 的 critique.json 里都没有对应内容——critic 从未提及 Donchian、MACD、OBV、RSI 这类具体技术指标数值。

### 4.4 Critic 独有、Risk 完全没有覆盖的内容

两次 run 里，critique.json 都包含 risk 从未产出的一类内容：**证据引用完整性审计**——检查 thesis 文本里的定量表述是否真的有 `evidence_ref` 支撑。例如 20260724_223804 run：

> "target": "thesis_valuation"
> "issue": "声称 '回购大幅收缩（同比-69%）' 但对应证据 L4.get_m7_buyback_flow#m7_aggregate_and_yoy 的 field_value 为 null，无可引用数据支撑该定量描述。"

以及同一次 run：

> "target": "thesis_environment"
> "issue": "引用 '净流动性4周动量显著转正（+99.4B）'、'M2恢复正增长（5.58%）' 等具体数字，但 key_evidence_refs 中未提供对应证据，读者无法验证。"

145833 run 里也有一条同类型的："声称'M7 实际回购同比收缩近 70%'，该数据未出现在 thesis_key_support_chains 或 key_evidence_refs 中，缺少证据来源。"这种"数字有没有据可查"的逐句核对，risk_sentinel.md 的检查清单里完全没有对应条目——risk 的输出模式是"基于 thesis 陈述的内容做风险外推"，不做"这句话有没有编造数据"这类文本级审计。

### 4.5 一处值得记录的分歧（不是重叠，是矛盾）——两个视角互不知情的代价

20260724_223804 run 里出现一个耐人寻味的现象：critic 明确指出"回购大幅收缩（同比-69%）"这个数字**没有证据支撑**（`field_value` 为 null），但同一次 run 的 `risk_boundary_report.json` 的 `must_preserve_risks[2]` 却原样引用了这个数字，当作既定事实来强化风险论证：

> "盈利增速放缓风险（中）：盈利修正30日斜率+3%但置信度低（supplier_lookback），**回购收缩（同比-69%）**削弱EPS支撑。"

由于 critic 和 risk 拿到的是完全相同的 payload，且互不知晓对方的输出（`gov_input_critic` 只构建一次，两边各自独立推理，risk 的 payload 里没有 critique 的结果），这暴露出一个当前架构下**两个"独立视角"并未真正互相校验**的实况：一个 agent 标记为"编造/无证据"的数字，另一个 agent 完全没有察觉地把它当成风险论据继续使用。这个矛盾要到下游 reviser（同时读到 critique 和 risk_report）才有机会被发现和调和，但 reviser 是否真的会调和、schema_guard 是否会拦截这种"两份治理产物互相打架"的情况，本次调查未验证（不在任务范围内，值得另立工单）。

这条证据对本次问题的意义是双面的：一方面它说明两个 agent **确实是独立运作**（不是简单的复读），另一方面它也说明当前"两个独立视角"的设计**没有让两个视角互相纠错**——risk 完全没有借助 critic 的证据审计能力去质疑自己引用的数字，说明"两个视角互相把关"这个潜在好处目前并没有被架构兑现，只是巧合地各自输出、事后堆在一起交给 reviser。

---

## 五、根因：prompt 层面的设计漂移，不完全是架构层面的"按职位硬拆"

`ARCHITECTURE.md:230-231` 记录的原始分工是：

> 13. Critic：攻击越权推理和弱逻辑。
> 14. Risk Sentinel：定义可观察风险触发器。

以及 `ARCHITECTURE.md:492-499` 的更细分工：

> Critic 的重点应包括：指标越权、数据频率错配、代理指标被当成事实、情绪或技术指标压倒信用/估值/结构证据。
> Risk 的重点应是可观察触发器，而不是编造历史概率。

按这份文档，两者理论上边界清楚：Critic 管"论证方式对不对"，Risk 管"有哪些可观察的风险触发器"。**但 `prompts/critic.md` 第 54-96 行的"攻击重点 6：过度谨慎与错过赔率"这一节，把 Risk 的地盘明确纳入了 Critic 的职责范围**：

> "Critic 必须对称攻击：不仅攻击乐观跳跃，也要攻击'为了不犯错而过度谨慎'。检查：是否把'风险存在'误等同于'风险收益比差'？是否把确认信号当成入场前提，却没有说明等待确认的成本？……"

这段文字与 `prompts/risk_sentinel.md` 第 138-146 行的"3.5 双向风险与确认成本"几乎是同一件事的镜像表述：

> "Risk Sentinel 必须额外列出：`opportunity_costs`：过度等待、过度谨慎、错过高赔率窗口的风险。`confirmation_costs`：等待哪些确认、降低什么风险、付出什么机会成本。"

也就是说，**这不是"两个 agent 因为各自站在人类职位视角、天然会想到类似的事"这种偶然重叠，而是 critic.md 的作者在某次迭代里主动把"过度谨慎/错过赔率"检查项写进了 Critic 的攻击清单，与 risk_sentinel.md 里本来就存在的 opportunity_costs/confirmation_costs/false_safety_risks 三个字段在设计意图上直接对撞**。第四节的实测重叠（尤其 4.1）几乎可以视为这一段 prompt 设计漂移的必然产物：两份说明书都明确要求模型检查"利多证据是否被低估、等待确认的代价是什么"，模型在拿到完全相同的输入时，自然会各自独立地抓到同一批利多信号（如本次的"净流动性动量转正、M2 回升"）。

需要说明：`critic.md` 第 4 节（"证据引用问题"）和第 3 节（"冲突处理不当"）**不**与 risk 重叠——这两部分对应 4.4 节展示的"证据审计"能力，risk_sentinel.md 完全没有对应检查项。所以问题不是"critic 整体上是 risk 的复制品"，而是**"攻击重点 6"这一节具体制造了重叠**，其余部分（证据引用审计、逻辑跳跃检查、循环论证检查）是 risk 完全没有触及的独有价值。

---

## 六、成本视角（不是决定性因素，但用户要求"不能只算钱不算账"里"钱"这一半也要摆出来）

145833 run 的 `llm_stage_diagnostics.json`：critic 的 prompt 是 152,875 字符（attempt 1），risk 的 prompt 是 153,951 字符（attempt 1）。两者相差不到 0.7%，说明 `governance_input` 这个共享 payload 占了两次调用输入 token 的绝大部分（说明书本身只占几百到一千多字符的差异）。也就是说，**当前架构下，"两次独立调用"约等于把同一份 15 万字符的大 payload 完整发送两遍**，只是各花几百字符的说明书不同。这是一笔实打实的重复输入 token 成本，且与"两个视角能不能互相纠错"（第四节 4.5 的负面发现）无关——目前多花的这份钱并没有换来两个视角互相校验的架构收益。

---

## 七、三个选项：利弊对照

### 选项 (a)：合并成一个"对抗性复核"agent

**做法**：把 critic.md 和 risk_sentinel.md 的检查清单合并进一个新说明书，输出一个合并后的 contract（或者 `Critique` + `RiskBoundaryReport` 两个 model 但只调一次模型、一次性产出两份结构）。

**利**：
- 消除 4.1/4.2 节实测到的真实重叠——不会再让模型对同一批证据做两遍推理。
- 省一次约 15 万字符的重复输入（第六节），如果按 run 频率计算，是持续性的 token 节省。
- 消除 4.5 节暴露的"两个视角互不知情导致自相矛盾"问题的一种可能诱因——合并后模型在同一次推理里能同时看到自己的证据审计结论和风险论证，理论上不会既标记某数字"无证据"又拿它当风险论据。
- schema_guard_retry 的联动重跑逻辑自然简化成"重跑一次"，不用再纠结"两个一起重跑"是否浪费。

**弊（用户明确要求必须摆出来的一半）**：
- **直接抵触"证据面均衡——多空两侧都有发言权，菜单不得先天偏科"这条常驻边界**。当前设计里，critic 和 risk 即便有重叠，仍然保留着两套独立的失败模式：critic 可能因为过度关注"逻辑严谨性"而放过一个真实存在但表述规范的风险；risk 可能因为聚焦"风险触发器"而对论证本身的漏洞视而不见。合并成一个 agent 意味着**这两种独立的失败模式会被同一次采样、同一个上下文窗口、同一次模型调用的随机性合并成一种失败模式**——如果这次合并后的调用注意力被某一类问题占满（比如证据审计占了大半篇幅），风险枚举（尤其是 conflict_matrix_check 这种需要完整遍历 13 种矩阵的机械检查）可能被挤占或简化，属于"减少一个独立评审视角"的真实代价，不是空话。
- 4.3 节的结构化产出（`boundary_status`/`conflict_matrix_check`/`failure_conditions`）和 4.4 节的证据审计是两种截然不同的输出模式（前者是"对固定分类体系做机械遍历"，后者是"对自由文本做批判性阅读"），合并成一个 contract 要求模型在一次输出里同时保持两种注意力模式，存在输出质量被稀释的风险，需要用真实 A/B 测试验证，不能想当然认为"合并=省钱不减质"。
- 4.5 节的"分歧"目前虽然没被架构利用，但如果未来把 critic 输出接回 risk 的 payload（做真正的顺序依赖校验，而不是本次调查发现的"两边各自独立、互不知情"），分歧本身可以变成有价值的交叉校验信号——合并成一个 agent 会永久失去这条路径。

### 选项 (b)：保持两个独立 agent，但把 schema_guard_retry 改成只重跑真正需要修的那个

**做法**：`orchestrator.py:420-444` 的 schema_guard_retry 分支目前不区分"是 critic 的输出有结构问题还是 risk 的输出有结构问题"，一律两个都重跑。改成先定位 `schema_report.structural_issues`/`missing_fields` 具体指向哪个 stage 的产物，只重跑那一个。

**利**：
- 精确针对用户前提二描述的浪费点：如果 Schema Guard 只是嫌 risk 的某个字段缺失，没有理由把 critic 也拉去重跑一次（重跑意味着再发一次 15 万字符的 payload）。
- 不改变"两个独立视角"的设计初衷，不触碰"证据面均衡"这条边界。
- 改动范围小，风险可控，容易验证（造一个只有 risk 结构问题的 fixture，断言 critic 的 stage_name 没有变成 critic_retry）。

**弊**：
- 不解决第四节实测到的**内容级重叠**（4.1/4.2）——两个 agent 在没有结构问题、正常走一次的情况下，仍然会各自独立地重复分析同一批利多信号，这部分 token 成本和"重叠而非互补"的问题原样保留。
- 不解决第五节指出的根因（critic.md 攻击重点 6 与 risk_sentinel.md 3.5 节的设计对撞）——这是 prompt 内容层面的问题，只改 orchestrator 的重试路由逻辑碰不到它。
- 判断"schema_report 的问题该算在 critic 头上还是 risk 头上"本身需要新写归因逻辑（`structural_issues`/`missing_fields` 目前是否带字段级来源标注，需要额外确认；如果目前的 `SchemaGuardReport` 不区分来源 stage，这条选项的实施成本比看起来更高，需要先补归因能力）。

### 选项 (c)：保持现状，不动 critic/risk 拆分，也不改 schema_guard_retry

**利（本次证据能支撑的部分）**：
- 4.3/4.4 节证明两者确有互不可替代的独有价值：Risk 的 `boundary_status`/`conflict_matrix_check` 是对固定分类体系的机械遍历，Critic 的证据引用审计是对自由文本的批判性阅读，二者是两种不同的认知任务，合并成一次调用有被稀释的风险（见选项 a 弊端）。
- 保留"证据面均衡"原则要求的两个独立失败模式（宁可有重叠浪费，也不因为一次调用的注意力局限性丢失某一类检查）。
- 4.5 节的分歧提醒我们，"两个独立视角"并非无意义——即便当前架构没有主动利用这种分歧来交叉校验，分歧本身的存在证明两个 agent **不是在做同一件事的复读**，而是各自基于相同输入产出了不完全一致的判断，这本身就是"多空两侧都有发言权"原则的一种（不完美的）体现。

**弊**：
- 4.1/4.2 节的重叠是本次实测到的、无法回避的事实：至少在"利多信号是否被低估"这一类问题上，两个 agent 确实在重复劳动，且第五节已经定位到这不是巧合而是 prompt 设计层面主动造成的重叠（critic.md 攻击重点 6）。"现状完全没有浪费"这个说法不成立。
- 第六节的 token 成本是持续性的，且 4.5 节证明"两个独立视角互相纠错"这个理论收益目前并未被架构兑现（risk 没有利用 critic 对同一数字的证据审计结论）——现状是"多花钱但没拿到应有的交叉校验收益"的中间状态，既不是最省钱的方案，也不是把两个视角用到极致的方案。

---

## 八、推荐意见

综合第四、五、六节的实测证据：**推荐选项 (b) 作为立即可做的改动，选项 (a) 作为需要额外 A/B 验证后再考虑的中期选项，不建议维持纯粹的选项 (c)（"完全不动"）**，理由：

1. 选项 (b) 精确对应用户前提二指出的浪费点（schema_guard_retry 不分青红皂白两个一起重跑），且不触碰"证据面均衡"这条常驻边界，是本次证据链里唯一"改了就一定是净收益、没有需要权衡的代价"的选项，值得优先做。
2. 第五节的根因分析（critic.md 攻击重点 6 与 risk_sentinel.md 3.5 节设计对撞）建议单独作为 prompt 层面的问题登记，不属于本次"要不要合并两个 agent"的决策范围，但值得记录：**即便最终决定保留两个独立 agent，也应该考虑收窄 critic.md 攻击重点 6 的范围（比如只保留"结论方向与证据合计方向是否一致"这类纯逻辑一致性检查，去掉"是否说明等待确认的成本"这类明显是 risk 地盘的检查项），减少非必要的重叠，同时不牺牲第四节证明的两者独有价值**。这是一个 prompt 微调选项，比"合并成一个 agent"代价小得多，但本次调查未把它列为用户要求的三选项之一，故只作为附加建议，不替代三选项的决策。
3. 选项 (a)（合并）不是不能做，但用户明确要求的"证据面均衡"原则确实构成真实代价——4.3/4.4 节证明的"两种认知任务分离"和"独立失败模式"是这套系统的设计基石之一，合并前必须用真实 A/B run（同一批输入，分别跑"两个独立 agent"和"合并后的单一 agent"）验证输出质量没有被稀释，尤其是 `conflict_matrix_check` 这类需要完整遍历 13 项矩阵的机械检查会不会被合并后的自由文本任务挤占篇幅。本次调查没有做这个 A/B 测试，不能替用户拍这个板。

**最终决定权在用户。** 这个决定的实质是"要不要减少一个独立评审视角换取更低成本和更少重复"，而"证据面均衡"是本项目明确写在 `CLAUDE.md` 常驻边界里、不可被普通待办覆盖的原则之一。本报告的职责是把利弊摆全，不替用户做这笔"省钱 vs 保留独立视角"的取舍。

---

## 九、引用文件清单（供复核）

- `src/agent_analysis/orchestrator.py:394-455`（critic/risk 调用与 schema_guard_retry 分支）
- `src/agent_analysis/orchestrator.py:4611-4682`（`_run_stage` 单站点内部重试循环）
- `src/agent_analysis/orchestrator.py:312`（`max_node_retries` 默认值 2）
- `src/agent_analysis/prompts/critic.md`（全文，尤其第 54-96 行"攻击重点 6"）
- `src/agent_analysis/prompts/risk_sentinel.md`（全文，尤其第 138-146 行"3.5 双向风险与确认成本"）
- `src/agent_analysis/contracts.py:1755-1836`（`CritiqueItem` / `Critique` / `RiskBoundaryReport` 定义，含 `overall_assessment` 的 `max_length=200`）
- `ARCHITECTURE.md:220-238`（vNext 流水线站点清单，含"Critic：攻击越权推理和弱逻辑""Risk Sentinel：定义可观察风险触发器"的原始分工）
- `ARCHITECTURE.md:482-501`（P1E 治理阶段客观性防火墙，Critic/Risk 的细分职责）
- `output/analysis/vnext/20260724_223804/critique.json`
- `output/analysis/vnext/20260724_223804/risk_boundary_report.json`
- `output/analysis/vnext/20260724_223804/llm_stage_diagnostics.json`
- `output/analysis/vnext/20260725_145833/critique.json`
- `output/analysis/vnext/20260725_145833/risk_boundary_report.json`
- `output/analysis/vnext/20260725_145833/llm_stage_diagnostics.json`
- `output/analysis/vnext/20260725_145833/prompt_audit/critic/attempt_1.response.raw.txt`（`overall_assessment` 超长的实测原文）
