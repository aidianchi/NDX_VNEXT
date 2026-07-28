# 交接文档：两条独立未决线索（T27 / T28）

> 写给**新对话**。这两条互不依赖，可并行，也可只做其中一条。
> 每条都给了：现象是什么、已经排除了什么、下一步该怎么查、什么算做完。
> 状态以 `现在.md` 为准；本文件只讲技术细节，不声明状态。

---

## 背景（两条线索共同的来龙去脉）

2026-07-25 之后做了一批 reviser / counter_thesis / 输入瘦身相关的修复（见 `WORK_LOG.md`
2026-07-25 ~ 2026-07-27 条目）。收尾时用**同一数据日的两次真实 run** 做受控对照：

- `output/analysis/vnext/20260725_145833/` —— 瘦身前
- `output/analysis/vnext/20260725_232410/` —— 瘦身后

（**注意**：不要用 `20260719_130534` 做对照——数据日不同，市场状态本身就变了，无法隔离变量。）

对照中发现的差异，绝大多数已经定位并修复。**剩下两条没查清，就是本文件的内容。**

---

## T27：`price_reflection_map` 全面倒向"已反映"，原因不明

### 现象

`price_reflection_map` 是"某类风险有没有被价格消化"的判断地图，五个类别各给一个
`reflection_level`（`not_reflected` / `partially_reflected` / `largely_reflected`）。

| 样本 | `not_reflected` 类别数 |
|---|---|
| 瘦身前 `20260725_145833` | **3**（credit / technical_panic / liquidity） |
| 瘦身后 `20260725_232410` | **0** |
| 重复采样 A 组（现状瘦身，n=3） | **0, 0, 0** |
| 重复采样 B 组（恢复 disputes 字段，n=3） | **0, 0, 0** |

系统性地从"还有风险没被定价"倒向"都已经反映了"，**6/6 采样稳定复现，不是方差**。

### 为什么重要

这直接影响赔率判断。如果系统总认为"风险已经反映在价格里"，就会系统性低估
下行空间、倾向于给出更乐观的 payoff 判断。这是**判断偏移**，不是格式问题。

### 已经排除的（不要重复做）

- **不是 `hypothesis_competition_summary` 被丢弃造成的。** 恢复该字段后 B 组三次
  采样仍然全部是 0。（该字段的恢复解决的是另一个问题——改判条件，见 WORK_LOG 2026-07-27。）
- **不是数据缺失造成的。** 两次 run 数据日相同、`function_availability_percent` 均 93.9%。

### 下一步建议怎么查

1. 先定位 `price_reflection_map` 的生成与继承链路：
   - `orchestrator.py` 的 `_normalize_price_reflection_assessment` /
     `_derive_price_reflection_map` / `_ensure_price_reflection_categories`
   - bridge 阶段生成 → thesis 消费/修正 → final 继承，三段都要看
   - 注意 `_ensure_price_reflection_categories` 会**补齐缺失类别**，补出来的默认
     `reflection_level` 是什么？如果代码补齐时默认给的不是 `not_reflected`，
     那么"模型少写几条 → 代码补齐 → 全变成已反映"就是一条完整的机制解释，
     应优先验证这条。
2. 对照两次 run 的 `bridge_memos/bridge_0.json` 与 `thesis_draft.json` 里
   `price_reflection_map` 的原始值，确认倒向发生在哪一段（bridge 生成时？thesis 修正时？还是 final？）。
3. 若定位到是"代码补齐"造成的，检查补齐默认值的合理性——从第一性原理，
   "没有判断"不等于"已经反映"，缺省应偏保守（`not_reflected` 或显式标记未评估）。

### 什么算做完

- 能说清 6/6 全为 0 的机制（是模型行为、还是代码补齐、还是两者叠加），有代码位置佐证。
- 若是缺陷则修复，并有红灯测试锁定（改前该复现、改后不复现）。
- 若判定为合理行为，写清依据，并在 `RESEARCH_CANON.md` 留判读说明，避免下次又被当 bug 查一遍。

### 关键材料

- 采样脚本与原始结果：见 `WORK_LOG.md` 2026-07-27 条目引用的实验方法（脚本为一次性产物，
  可按同法重建：复用 `_compose_prompt("thesis", ThesisDraft, payload)` 真实组装路径，
  固定 `deepseek-v4-pro`，对同一份 `synthesis_packet.json` 重复采样）
- `contracts.py` 的 `PriceReflectionAssessment` 定义

---

## T28：越有争议的假说越不会被要求回应（合约触发条件逻辑倒置）

### 现象

「Thesis 必须逐一回应每个竞争假说」这条治理机制**建过、代码是好的**
（2026-07-17 的 R7 工单，见 `WORK_LOG.md:435`；实现为
`orchestrator._validate_thesis_hypothesis_responses`；`thesis_builder.md` 有
「对竞争假说的强制回应」一节）。

但它的触发条件是「假说的 `status == "candidate"`」。而 `orchestrator.py:2323`
附近有一段降级逻辑：**一旦受控调查提出挑战、或存在证据缺口/兜底痕迹，就把假说从
`candidate` 降级为 `kept_unresolved`**——降级之后，校验器的 `candidate_ids`
收集不到它，合约直接空转。

四次真实 run 实测：

| run | `status == "candidate"` 的假说数 |
|---|---|
| `20260719_130534` | 0 |
| `20260724_223804` | **1**（合约正常触发，并如实崩了——就是 T19 那次事故） |
| `20260725_145833` | 0 |
| `20260725_232410` | 0 |

### 为什么重要（这是北极星层面的问题，不是 bug 级别）

逻辑正好反了：**越是有争议、越需要被正面回应的假说，越容易被降级，也就越不会被要求回应。**

后果具体而言：`20260725_232410` 是 counter_thesis 修复后**第一次真正产出 AI 推理的反方假说**
（`source="counter_thesis"` 而非 `deterministic_fallback`）——然后**没有任何环节被要求回应它**，
`revised_thesis.hypothesis_responses` 为空且完全合法。

对照 `CLAUDE.md` 北极星："**证据面均衡**——多空两侧都有发言权"以及六问的
"哪些反驳它"。目前是"有发言权，但没有被回应的义务"。

### 附带影响（做 T28 时会一并遇到）

`_validate_thesis_hypothesis_responses` 空转还有一个副作用：**T19 的假说回应修复
至今没有真实 run 的实证**。`20260725_232410` 的 `reviser attempts=1` 只证明了
reviser 没崩，**不能证明**"漏字段"那个毛病被治好了——因为那条合约在那次跑里根本没被考到。
目前它只有单元测试覆盖。T28 修好后，下一次有 candidate 的真实 run 才能真正验收 T19。

### 下一步建议怎么查

1. 读 `orchestrator.py:2300-2340` 与 `2660-2690` 两段，搞清 `candidate` →
   `kept_unresolved` 的完整触发条件与设计意图（降级本身**可能是对的**——
   它表达"不能形成单一路径裁决"，这符合"冲突是资产"）。
2. 关键判断题：**降级的语义是"这条假说没有胜出"，还是"这条假说不需要被回应"？**
   从第一性原理，前者才是本意，而当前代码把两者混为一谈。
3. 倾向性方案（待验证，不要直接照抄）：把"必须回应"的触发集合从
   `status == "candidate"` 扩展为「所有**非 rejected** 的竞争假说」，即
   `candidate` + `kept_unresolved` 都要求回应；`kept_unresolved` 的合格回应
   形态可以是 `absorb_partially`（承认张力未解决），不强求 `accept` 或 `reject`。
   **务必同时确认**这不会让"冲突是资产"退化成"逼模型给每条争议硬下结论"。
4. 改动后必须同步登记 `STAGE_CONTRACT_PROMPT_REQUIREMENTS` 并更新
   `thesis_builder.md` / `reviser.md` 的对应说明书章节——这两处的合约—说明书
   一致性闸门在 `tests/test_governance_input.py`，漏改会红。

### 什么算做完

- 有 candidate 或 kept_unresolved 假说的真实 run 里，thesis/reviser 确实逐一回应，
  且回应内容不是敷衍（reject 必须带合法反证 evidence_ref）。
- 红灯测试：改前"有争议假说但零回应"能通过，改后被拦下。
- 顺带完成 T19 的真实 run 验收（见上文"附带影响"）。

### 关键材料

- `orchestrator.py:2323`（降级分支）、`_validate_thesis_hypothesis_responses`
- `WORK_LOG.md:435`（R7 工单原始记录）、`WORK_LOG.md` 2026-07-25 条目（T19 事故全过程）
- `prompts/thesis_builder.md` 的「对竞争假说的强制回应」节

---

## 通用注意事项（两条都适用）

- **不要用 `20260719_130534` 做对照组**，理由见开头。
- **本文件 T27 一节的两条前提在结案时被证伪**（"6/6 采样稳定复现，不是方差"、"代码补齐默认值可能是病根"），细节见文末关单记录与 `T27_FINDINGS.md`。引用本文件时请连同关单记录一起读。
- 涉及真实 API 采样的实验，先说明预计花费再做；一次 thesis 采样约 6.7 万 prompt token。
- 本批改动的完整背景在 `WORK_LOG.md` 的 2026-07-25 ~ 2026-07-27 三条记录里，
  尤其"reviser 连崩两跑的根因诊断"那条给出了本项目反复出现的一类结构性缺陷
  （合约写在代码里、说明书写在 prompt 里、两边无人对账）及其治理机制。
  查这两条线索时如果又撞见同型问题，优先考虑扩展既有的防漂移闸门，而不是单点打补丁。

---

## 关单记录

### T27 —— 2026-07-28 关闭（裁决：合理行为，非缺陷）

本文件 T27 一节写下的两条前提，结案时都被证伪：

1. **"6/6 采样稳定复现，不是方差"不成立。** 那 6 次采样打在 thesis 站点，而
   `price_reflection_map` 由 bridge 生成、thesis 与 final 逐字继承（三份产物实测一致）。
   在 thesis 重采测的是"继承是否稳定"。真正做判断的 bridge 站点是 n=1 对 n=1。
2. **"代码补齐默认值是病根"这条优先假设不成立。** `_ensure_price_reflection_categories`
   补齐时写的是 `unclear`，不是任何"已反映"值；两次 run 的五类全部模型原生，
   `normalization_notes` 无补齐痕迹。
3. **"输入瘦身削薄了 bridge"也不成立。** 瘦身只作用于 thesis / counter_thesis；
   bridge prompt 两次逐字节相同；两次 run 之间零代码提交。

**受控重采样（真实 API，n=4×2，用户批准）**：A payload（历史 3 个 `not_reflected`）
重采得 0/1/1/0；B payload（历史 0 个）重采得 1/1/1/2。两次历史值都无法在自己的
payload 上复现，两组分布重叠，B 反而更偏 `not_reflected`——**原假设的方向本身不成立**。

裁决为合理行为，未改 `orchestrator.py`；判读说明写入 `RESEARCH_CANON.md`。
顺带修掉一个审计诚实性缺陷（`run_review.py` 把代码占位类别当作"已覆盖五类"给 pass），
带红灯测试。完整证据见 `T27_FINDINGS.md`。

### T28 —— 2026-07-28 关闭（含 T19 一并验收）

**实现**：`_validate_thesis_hypothesis_responses` 的触发集合从 `status == "candidate"`
扩大为 `status != "downgraded"`。本文件建议的"非 rejected"落到代码上就是"非 `downgraded`"
——`CompetingHypothesis.status` 的 `Literal` 里没有 `"rejected"`。`kept_unresolved` 的
合格回应允许 `absorb_partially`，不强求 `accept_and_revise` 或 `reject`（本文件第 3 点
要求确认的"不会退化成逼模型硬下结论"，已按此实现并由正向用例锁定）。`leading` 也纳入
必答集合。`STAGE_CONTRACT_PROMPT_REQUIREMENTS` 与 `thesis_builder.md` / `reviser.md`
同步登记改写。

**真实 run 验收（`20260728_110702`）**：该 run 因终审站崩溃走了一次断点续跑，续跑重跑了
counter_thesis 起的全部叙事站，因此留下两批独立样本，两批的竞争假说都**全部是
`kept_unresolved`**——正是过去让合约空转的场景，两批也都通过：

- 首跑（已被续跑覆盖）：3 条假说，`thesis`/`reviser` 各 `attempts=1`，回应 3/3，
  verdict = 1×`accept_and_revise` + 2×`absorb_partially`。
- 续跑后（当前 artifacts，可复核）：2 条假说，`thesis`/`reviser` 各 `attempts=1`，
  回应 2/2 完整传导到 `revised_thesis`，verdict = 1×`accept_and_revise` + **1×`reject`**，
  每条 4 个 evidence_ref，逐条比对 `evidence_index` 零越界。

本文件「什么算做完」的两个面因此都被真实触发：`absorb_partially`（承认张力未解决、
不逼硬下结论）由首跑证实；**"reject 必须带合法反证 evidence_ref"由续跑真实考到并通过**。
**扩大合约零重试成本**，本文件担心的"逼模型硬下结论"未发生。T19 由此拿到第一次真实
run 实证（此前四次 run 的 `revised_thesis.hypothesis_responses` 全空，合约根本没被考到），
一并关闭。

**本文件"附带影响"一节点出的洞另有一个真实样本**：run `20260719_130534` 里 thesis 写了
2 条回应、reviser 交出空列表且无人报警。已加专测锁定这一形态。

**顺带**：这次真实 run 现场暴露终审站两处规格漂移（`claim_ledger` 说明书零覆盖；
`reasoned_verdict` 逗号合并引用——2026-07-27 收紧后的真实回归），均已修复并带红灯测试。
正是本文件"通用注意事项"预告的同型问题，修法按其建议扩展既有闸门而非单点打补丁。
详见 `WORK_LOG.md` 2026-07-28 条目。
