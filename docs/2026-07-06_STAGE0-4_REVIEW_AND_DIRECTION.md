# 阶段 0-4 施工审查与下一步方向（Fable 审查）

审查日期：2026-07-06
审查范围：`docs/2026-07-05_VNEXT_ARCHITECTURE_AUDIT_V2.md`、`docs/2026-07-06_VNEXT_IMPLEMENTATION_ROADMAP.md`、未提交的阶段 0-4 全部改动（约 3350 行新增，16 个文件 + 2 个新文件）。
验证基线：`python -m pytest -q` 441 通过；31 个历史 run 的 bridge memo 实测抽样。

---

## 1. 总体判断

审计 V2 的诊断是对的，路线图的顺序也是对的。阶段 0-4 的施工守住了全部红线：L1-L5 隔离没有被破坏，no-backflow 成立，新增反馈产物都在 Bridge 之后、layer card 之外。合同层（InquiryMessage / AgentSpec / InvestigationReport / CompetingHypothesis / EvidencePassport / ClaimLedger）是真资产，质量不低。

但有一个必须直说的核心问题：

> **阶段 2-4 的"行为"部分目前全部由固定模板代码扮演。系统看起来会追问、会对抗、会记台账，实际上每次 run 输出的判断内容是常量。**

这不是施工偷懒——路线图本来就写了"先做薄合同，再做聪明行为"。问题在于 WORK_LOG 把阶段 2/3/4 记成"完成"，覆盖矩阵会让人以为 EPI-08/10/12/13、HAR-05..09/13 已关闭。正确的记法是：**合同已关闭，行为未开始**。审计 V2 批评的"字段存在 ≠ 质量成立"（缺口三），在阶段 2-4 的新产物里被原样复制到了更高一层。

## 2. 最重要的实证发现：竞争裁决恒定输出"保留争议"

链条如下（全部已实证）：

1. 抽样全部 31 个历史 run：**每个 run 的 `bridge_0.json` 都有 2-5 条 `unresolved_questions`**。
2. `orchestrator._build_feedback_inquiry_messages` 把 unresolved questions 转成 `adjudication_gap` 消息 → 路由器接单 → `_build_investigation_report` 生成模板调查。
3. 模板调查的 `claims_challenged` 恒非空（写死在三个分支里）。
4. `_build_adjudication_change_records`：只要任何调查带 challenge → 生成降级记录 → `leading_id = ""` → 全部假说 `kept_unresolved`。

结论：**新代码下 100% 的 run 都会输出"无主导假说、保留争议"。** 恒定输出等于零信息量。它把审计想消灭的"永远一个顺滑故事"翻转成了"永远没有故事"——同样是常量，不是判断。对"价值买入-趋势卖出、等黄金坑"的真实决策场景，这个输出永远不会告诉用户"买入条件成立"，且会造成狼来了效应：读者很快学会忽略"保留争议"。

## 3. 各项发现（按严重度）

### P0（阻断"把阶段 2-4 当完成"的认定，需在阶段 5 之前处理）

| # | 发现 | 位置 | 说明 |
| --- | --- | --- | --- |
| P0-1 | 竞争裁决恒定 kept_unresolved | `orchestrator.py` `_build_adjudication_change_records` + `_build_investigation_report` | 见第 2 节。短期修法：模板调查显式标记 `is_deterministic_stub`，stub 不得生成降级记录、不得清空 leading_id；只有真实反证（当前只有 fallback_warnings 是真信号）才影响裁决 |
| P0-2 | 调查报告是罐头文本 | `orchestrator.py` `_build_investigation_report` | 三个 message_type 各对应一段写死的 finding；`claims_supported=[message.question]`（问题不是 claim）；`evidence_refs` 是 allowed_context 文件路径而非证据。"系统会追问"目前只是形式成立 |
| P0-3 | Counter-Thesis 是固定怀疑论样板 | `orchestrator.py` `_build_counter_thesis` | 每次 run 同一段反方文本。"独立于 Thesis"是平凡真（因为它根本不思考）。`prompt_input_audit.thesis_read=False` 是断言不是测量。Run Review 对它的 pass 检查属于审计剧场 |
| P0-4 | Bridge V1+V2 双份进入 SynthesisPacket，冲突/主要矛盾重复计数 | `orchestrator.py:160`（`bridge_memos = [bridge_v1, bridge_v2]`）、`_build_synthesis_packet` 1979-2010 行循环、2983 行 `total_conflicts`、2103/2108、3044 | Bridge V2 整体复制 V1 的 conflicts/typed_conflicts/principal_contradiction，循环 extend 后 Thesis 看到全部张力 ×2、两个几乎相同的"主要矛盾候选"。这是真回归，会污染 Thesis 输入并加倍 prompt 噪音 |

### P1（应修，不阻断）

| # | 发现 | 位置 |
| --- | --- | --- |
| P1-1 | 运算符优先级 bug：`quality.get("source_tier") or item.get("source_tier") if isinstance(item, dict) else ""`，item 非 dict 时 quality 的 tier 被丢弃（已用最小复现证实） | `orchestrator.py:1494` |
| P1-2 | Claim 台账的反证与失效条件是"全局同一份"贴到每条 claim：`common_counter_refs` / `common_falsifiers` 与 claim 内容无关。"每条 claim 可追问"形式成立、语义空洞（EPI-02 的病复制到台账层） | `orchestrator.py` `_build_final_claim_ledger` |
| P1-3 | `feedback_contract_manifest.json` 里的 router 预算（0/0/0，来自默认构造）与运行时真实预算（1/1/3）不一致，审计产物和实际策略对不上 | `orchestrator.py` `_build_feedback_contract_manifest` vs `_route_feedback_inquiries` |
| P1-4 | `no_backflow_verified: True` 写死在 Bridge V2 payload 里——把断言记录成了验证结果。要么真的校验（比较 layer card 前后哈希），要么改名 `no_backflow_asserted` | `orchestrator.py` `_build_bridge_v2` |
| P1-5 | `NEXT_STEPS.md` 停在 2026-06-27，完全没有路线图阶段的踪迹。按 CLAUDE.md 文档路由规则它是"当前任务"的事实源，现在指向错误的地图 | `NEXT_STEPS.md` |

### P2（记录在案）

- 调查的 evidence id 空间（`bridge_memos/bridge_0.json` 这类 artifact 路径）与主链 `L1.xxx` 空间只是并存在同一个注册表里，"统一 evidence id"只完成了一半。
- `scripts/generate_trial_theater_demo.py`（922 行，未跟踪）硬编码了具体 run 目录和 chartbook 文件路径。作为阶段 5 读者出口的原型有价值，但不要接入主链；阶段 5 施工时吸收其构思后归档或参数化。
- `tools_L2.py` 的 `cached_yf_download` 替换与路线图无关，混在同一批未提交改动里。提交时单独成 commit。
- 指标越权 regex 守卫（`_AUTHORITY_OVERREACH_RULES`）作为第一道语义闸门合格，但中英文 pattern 容易漏报，长期应视为 observe 级信号而不是完整防线。

## 4. 施工指引（交接给 codex 的顺序）

原则：**下一阶段的目标不是更多 schema，而是把已有骨架里第一块真肌肉接上。** 每步独立提交、可回滚。

### 第 0 步：先提交现有工作

阶段 0-4 改动按逻辑拆分提交（至少：阶段 0+1 合同、阶段 2 管道、阶段 3 竞争、阶段 4 证据台账、tools_L2 单独）。验证：`python -m pytest -q` 441 通过后提交。

### 第 1 步：诚实化（把"假装"改成"如实"）

1. `InvestigationReport` 加 `is_deterministic_stub: bool`（合同 + 生成处）。stub 报告的 finding 改为如实陈述："本轮未执行真实调查，仅登记缺口"；`claims_challenged` 置空或改为 `["no_real_investigation_performed"]` 一类中性标记。
2. `_build_adjudication_change_records` 忽略 stub 报告；leading hypothesis 只被真实反证或 fallback_warnings 影响。
3. 修 P0-4：Bridge V2 不再复制 V1 的 conflicts/principal_contradiction 进 `bridge_memos` 汇总路径。最简单做法：`_build_synthesis_packet` 只消费 V1 的结构字段，V2 只贡献 `investigation_effects` / `feedback_loop_summary` / 合并后的 unresolved_questions；或 V2 复制字段置空并在 summary 引用 V1。
4. 修 P1-1 优先级 bug、P1-3 manifest 预算不一致、P1-4 改名。
5. WORK_LOG 追加更正记录：阶段 2/3/4 的完成定义降级为"合同与管道完成，行为质量未完成"；路线图加一页附录，把 EPI-08/10/12/13、HAR-05..09/13 重标为"合同关闭 / 行为未关闭"。

验收：跑一次真实 run，`hypothesis_competition.json` 不再出现由 stub 触发的降级；存在主导假说或有真实理由的 kept_unresolved；Thesis prompt 中主要矛盾候选不再成对重复。

### 第 2 步：Counter-Thesis 变成真 LLM 阶段（全局性价比最高的一步）

理由：合同（`CounterThesisDraft`）、隔离边界（forbidden thesis_draft.json）、Run Review 检查、测试全部已就位；缺的只是一个提示词文件和一次 LLM 调用，模式完全照抄现有 critic/thesis 阶段。这是让"竞争假说"从表格变成认知的最短路径。

要点：
- 新增 `src/agent_analysis/prompts/counter_thesis.md`；输入只给 SynthesisPacket（去掉 competing_hypotheses 自引用字段）+ Bridge V1 结构 + InvestigationReport（非 stub）。
- 要求输出 1-2 个真反方假说：各自的支持证据 refs、反证 refs、诊断力证据（最能区分它和主线的观测）、解释不了什么、失效条件。evidence_refs 必须来自 evidence_index，沿用现有 refs 校验。
- 确定性构建器降级为 LLM 失败时的 fallback，且标记 `source: deterministic_fallback`（合同里已有该枚举值）。
- `prompt_input_audit` 由 prompt inspector 真实测量，不再手写 False。

验收：两次不同市场状态的 run 里，反方假说文本、证据和失效条件确实不同且引用真实 evidence refs；Run Review competition 项无 fail。

### 第 3 步：Claim 台账反证逐条化

把 `common_counter_refs`/`common_falsifiers` 的全局贴法改为逐条生成：market_state claim 的反证来自竞争假说中对立假说的支持证据 + 相关 typed_conflicts；risk_boundary claim 的失效条件来自 Risk Sentinel 对应项；action_translation 的反证来自 invalidation_conditions。做不到逐条对应的，`downgrade_reason` 如实写 `counter_evidence_not_claim_specific` 并降级，不许用全局池冒充。

验收：任选两条不同类型的 claim，其 counter_evidence_refs 集合不同且能讲出为什么是这几条。

### 第 4 步：阶段 5 读者出口（此时才做）【修正一：按"决策稀疏"现实定调】

按路线图三类分栏 + 四层阅读，但主视图定调修正：使用者的真实决策频率是每年 2-5 次，不是每天一次。读者出口的 30 秒版不应是"今日观点"，而应回答三件事：**当前状态是什么、上次 run 以来什么变了、距离你的买入/卖出条件还差哪几项证据**。

为此新增一个产物 `golden_pit_checklist.json`（黄金坑清单，claim 台账的直接应用）：

- 来源：从 `final_claim_ledger.json` 筛 `claim_type in {valuation, timing, risk_boundary}` 的条目 + UserDecisionProfile 的买入/卖出纪律条件。
- 每条：`condition / evidence_refs / current_status(met | not_met | insufficient_evidence) / falsification_conditions / changed_since_last_run`。
- `changed_since_last_run` 通过读取上一个 run 的同名产物做 diff——这是第一个跨 run 产物，只属于读者出口层，同样不得回流 L1-L5。

补充一个路线图没有的关键件：

**UserDecisionProfile（个人决策翻译档案）**。用户的真实买卖纪律（价值买入-趋势卖出、NDX 为复利基地、小额定投等待黄金坑）目前不在架构里。正确落点：

- 一份版本化合同/配置（持仓状态、目标、风险承受、买入纪律、卖出纪律），只被 Final 的"个人决策翻译"栏消费。
- **硬边界：绝不进入 L1-L5、Bridge、Thesis、Critic、竞争裁决的任何输入。** 否则系统会变成确认偏误机器——上游先知道用户想等黄金坑，就会倾向把证据讲成"还没到坑"。这条要写进 prompt inspector 检查。
- 个人决策翻译只输出条件式规则（"若你的纪律是 X，当前状态映射为 Y，触发改判的条件是 Z"），不输出指令。
- "黄金坑清单"是 claim ledger 的天然应用：把"价值买入条件成立"定义为一组可追问的 claim（估值分位 + 广度/集中度状态 + 风险溢价 + 失效条件），每次 run 逐条给出证据状态。这比任何 UI 都更接近用户的真实目的。

### 第 5 步：claim 级结果记分【修正二：把学习回路接上】

系统现有 `outcome_review.py` 只做单 run 的"措辞谨慎/激进 vs 之后 QQQ 窗口涨跌"语言级对照。一台判断机器只有在判断被逐条、跨期打分时才会变好。阶段 4 的 claim 台账正是升级它的底座：

1. 扩展 `outcome_review.py`：输入改为 `final_claim_ledger.json`（不再只拼接 Final 文本）；对每条 claim 在 T+20/60/120 交易日窗口输出 `verdict(consistent | falsifier_triggered | not_scorable)` 和 `scoring_evidence`；落盘 `claim_outcome_scores.json`。
2. 跨 run 纵向台账（可先放 `scripts/`）：按 `claim_type` 和证据 `source_tier` 聚合一致率，回答"哪类判断、哪类证据真正有诊断力"。
3. 边界：打分器在裁决之后运行，读取打分时点的市场数据是合法的；但打分产物禁止进入后续 run 的 L1-L5 输入。
4. 验收：任选一个历史回测 run（如 `20250409`）能产出逐条打分，`not_scorable` 必须写明原因。

没有这一步，系统可以永远流程完美、判断平庸。

### 停机准则

诚实化 + 阶段 5（读者出口）验收通过后，**架构冻结一个季度**：每月跑一次、大回撤时加跑，期间唯一新增记录是使用日志（run 日期、是否改变了使用者决策、事后对错）。下一轮施工选题由使用日志决定，不由审美决定。冻结期正好用于补 L3 广度数据源（判断质量的最大数据瓶颈）。

### 第 6 步之后（明确推迟）

- 真动态调查（真工具、真预算执行、真停止条件）：等真反方假说暴露出"最关键分歧"之后再做，否则调查没有靶子。这与路线图 8.1 的互喂逻辑一致。
- 统一 evidence id 空间的第二半、L3 广度数据补强（NEXT_STEPS P1，仍是最大数据短板）。

## 5. 不要做的事（在既有六条之上追加）

7. **不要再新增确定性 JSON 产物。** 每 run 已有约 30 个 artifact；在行为质量跟上之前，每个新 schema 都是负资产。
8. **不要让 Run Review 给模板产物发 pass。** 阶段 6 硬化时给 Run Review 加"跨 run 方差检查"：调查 finding、反方文本、竞争裁决若与上一 run 逐字相同，标 observe——常量输出本身就是需要被审计的信号。
9. **不要把个人决策偏好放进上游任何阶段。**（见第 4 步硬边界。）

## 6. 本次审查的验证与边界

- 已运行全量测试：441 passed（当前工作区，含全部未提交改动）。
- 实证抽样：31 个历史 run 的 bridge_0.json（unresolved_questions 全部非空）；P1-1 优先级 bug 已最小复现。
- 未做：真实 fresh run（本次是静态审查 + 历史产物抽样）；第 1 步完成后应立即跑一次 fresh run 验证竞争裁决行为变化。
- 本文不是重新审计 30 条 EPI/HAR，只修正其"关闭"状态的语义：合同层关闭属实，行为层未关闭。

---

## 7. 2026-07-07 审核记录：codex 第 0-3 步验收 + 后续修复

### 验收结论

codex 的第 0-3 步实施**总体合格**：提交按逻辑拆分（合同/管道/审计/台账/tools_L2 各自成 commit）；P0-1..4、P1-1..5 全部落实；WORK_LOG 和路线图 11A 的"合同关闭/行为未关闭"更正到位；全量测试 448 通过。计划外的 `4e14316`（L4 外部检查超时/缓存/预算）经审查合规：跳过项如实记入 `skipped`/`degraded`，SEC 角色从 primary 诚实降级为 `official_cross_check_for_component_model`，未弱化数据闸门。

fresh run `codex_external_timeout_validation` 行为验证：stub 调查不再触发降级，竞争裁决出现主导假说（恒定 kept_unresolved 已消除），principal_contradiction / price_reflection 均为 native，claim 台账不同类型 claim 的反证已不同，Run Review 零 fail。

### 该 run 暴露的两个新问题（已于 2026-07-07 修复）

1. **Counter-Thesis LLM 两次尝试均死于 schema 摩擦并退回确定性 fallback**：attempt 1 漏 `hypothesis_id`；attempt 2 把 `cannot_establish` 写成字符串、用了 `what_it_cannot_explain`/`failure_conditions` 变体字段名。attempt 2 的内容质量其实很高（挑战"净流动性转负=折现率上行"的等价假设），被管道整体丢弃属于收割损失。修复：`CompetingHypothesis.hypothesis_id` 加默认工厂；两个合同加字符串→列表 coercion 和已观测字段别名吸收（`contracts.py`）；`fallback_reason` 不再被审计覆写丢失（`orchestrator.py::_build_counter_thesis`）。用两份真实失败返回回放验证：修复后均通过校验。
2. **claim 闸门被垃圾 token 全线误伤**：Final 的一条支撑链混入说明性 token `known_data_gaps`，导致全部 6 条 claim 被 `evidence_refs_not_in_registry` 标记 blocked——闸门在喊狼来了。修复：台账构建时只保留形如 `L#.func` 或注册表内的真实引用，剔除项记入 `dropped_non_evidence_tokens`（可审计，不冒充缺失证据）；真实引用缺失仍照常阻断，闸门未被弱化。

### 修复后状态

- 全量测试 449 通过；两份真实失败 LLM 返回通过合约回放。
- 步骤 2 的最终验收（LLM 反方在真实 run 中成功产出有区分力假说）以修复后的验证 run `fable_counter_thesis_fix_validation` 为准。
- 修正一（黄金坑清单 + 决策稀疏定调）、修正二（claim 级结果记分）、停机准则已写入第 4 节。
