# vNext 工作记录

阅读方式：最新完成事项放在最上面。这里记录已经完成的事；未来要做的事写在 `NEXT_STEPS.md`。

---

## 2026-07-07

### 跨 run 对比定案 + 状态台账记录层上线 + 个人决策档案草案

完成内容：

- 跨 run 对比设计定案并写入 `docs/2026-07-06_STAGE0-4_REVIEW_AND_DIRECTION.md` 修正一：对比轴从"上一份报告"改为"上一个市场状态"；只比确定性状态变量和稳定条件 ID，`claim:<hash>` 回声条目与 LLM 派生项永不参与报警；`git_sha` 不同带系统版本横幅；报警白名单只含条件翻转/失效条件触发/闸门变化；展示层等三闸门（谓词化、≥5 条 official 记录、代码稳定），记录层先行。
- 新增 `src/state_ledger.py`：从 run 目录提取约 20 个确定性状态变量（估值 PE、净流动性、VIX/HYG 分位、广度、NDX/NDXE 分位、趋势与唐奇安回撤等）+ profile 条件状态 + 发布闸门，附 `git_sha` 与 schema 版本，append-only 写入 `output/state_ledger/state_ledger.jsonl`，同 run_id 去重；缺失变量如实记入 `missing_variables`（Wind 离线时不冒充）。
- `src/main.py` 接入：新增 `--official` 参数标记正式日度 run；run_pipeline 结束时自动追加台账（失败不阻断 run），结果写入 `run_summary.state_ledger`。
- 新增 `config/user_decision_profile.json` 草案：价值买入-趋势卖出纪律写成 metric 谓词（估值买入区、黄金坑回撤+恐慌确认、趋势破坏、信用恶化），全部阈值标注 `draft_needs_user_confirmation`；该文件会被编排器自动加载替换内置占位档案。
- 修复 codex 第 4 步测试的隔离缺陷：`test_stage5_golden_pit_checklist_defers_cross_run_diff_even_if_previous_exists` 原本调用 `_load_user_decision_profile()` 隐式依赖仓库 config 全局状态，改为显式构造档案。
- `NEXT_STEPS.md` 新增 P1（状态台账展示层三闸门）与 P2（认知阶段模型路由 + Final 引用源头校验）。

验证结果：

- `python -m pytest -q`：456 通过（含新增 `tests/test_state_ledger.py` 3 条）。
- 用真实 run `fable_counter_thesis_fix_validation_2` 干跑台账：19 个非空确定性变量、Wind 两项如实记缺、闸门状态正确、重复追加被拒。
- `config/user_decision_profile.json` 通过 `UserDecisionProfile.model_validate` 加载校验。

剩余风险：

- 决策档案阈值全部是草案（Forward PE ≤ 20、回撤 ≥ 15% + VIX 分位 ≥ 70% 等），需用户逐条确认；Wind 估值分位谓词在 Wind 源接通前记 insufficient_evidence。
- 台账的唐奇安回撤是"距通道上轨"口径，不等于距 52 周高点的标准回撤；启用展示层前应确认口径或补 52 周高点变量。
- 谓词化状态判定（展示层闸门 ①）尚未实现，黄金坑清单当前仍是关键词启发式判定。

### 完成第 4 步：阶段 5 读者出口（决策稀疏版）+ 对抗式审查

完成内容：

- 新增阶段 5 合同：`UserDecisionProfile` / `UserDecisionCondition` 与 `GoldenPitChecklist` / `GoldenPitChecklistItem`。个人决策档案只描述持仓状态、目标、风险承受、买入纪律和卖出纪律；黄金坑清单只在 Final / Claim Ledger 之后生成。
- 编排器在 `final_claim_ledger.json` 之后落盘 `user_decision_profile.json` 与 `golden_pit_checklist.json`。清单来源限定为 `final_claim_ledger` 中 `valuation` / `timing` / `risk_boundary` claim + 个人买卖纪律；`changed_since_last_run` 当前只保留预留字段并标记 `deferred_until_run_quality_stable`，暂不读取上一 run 做 diff。
- Claim 台账补出 `valuation` 与 `timing` 类型条目，供黄金坑清单读取；个人纪律聚合采用保守语义，不能把“估值 claim 证据完整”误判成“买入条件满足”。例如“估值安全垫仍不足”即使 verified，也只会让买入纪律显示 `not_met`。
- Runtime Boundary Manifest 增加 reader-exit 边界；Prompt Inspector 增加硬检查：`user_decision_profile` / `golden_pit_checklist` / 个人决策档案 / 黄金坑清单 一旦进入任意分析 prompt，标记违规。
- Native brief 首屏改为阶段 5A 定调：30 秒版回答“当前状态、距离买入/卖出纪律还差哪些证据”；“上次 run 以来变化”暂缓前置，报告内明确四层阅读入口：30 秒裁决、5 分钟简报、深度研究、审计重放。
- Run Review 增加阶段 5 读者出口检查：缺 `golden_pit_checklist` 记 observe；字段不完整记 fail；完整且声明 no-backflow 记 pass。

对抗式审查结论：

- 上游污染检查：个人档案和黄金坑清单只在 Final / Claim Ledger 之后生成；Prompt Inspector 对所有 LLM 分析阶段加拦截，未发现现有 prompt 注入路径。
- 伪确定性检查：黄金坑清单不输出交易指令，只输出 `met / not_met / insufficient_evidence` 和失效条件；买入纪律聚合对负面估值文本保守判 `not_met`。
- 跨 run 边界检查：真实上一 run diff 已退回，`changed_since_last_run` 只写暂缓状态；未来启用时仍不得进入 L1-L5、Bridge、Thesis、Critic、Risk、Reviser、Final 或竞争裁决。

验证结果：

- 聚焦测试：`python3 -m pytest tests/test_contracts.py tests/test_vnext_orchestrator.py::test_stage4_evidence_registry_and_final_claim_ledger_are_auditable tests/test_vnext_orchestrator.py::test_stage5_golden_pit_checklist_defers_cross_run_diff_even_if_previous_exists tests/test_vnext_reporter.py::test_vnext_reporter_generates_native_ui tests/test_vnext_reporter.py::test_prompt_inspector_flags_user_decision_profile_in_analysis_prompt tests/test_run_review.py::test_run_review_passes_stage5_golden_pit_checklist_when_complete -q`：27 通过。
- 全量测试：`python3 -m pytest -q`：453 通过，4 个环境/依赖 warning。

剩余风险：

- 默认 `UserDecisionProfile` 是保守占位；正式使用前应在 `config/user_decision_profile.json` 写入真实持仓状态、风险承受和纪律参数。
- 黄金坑清单的条件满足判断仍依赖 claim 文本语义和保守关键词；后续如果 Final claim 语言风格变化，需要继续补测试，避免把“证据完整”当成“条件满足”。
- 跨 run 变化对比已主动暂缓；等 claim schema、数据源覆盖、Run Review 通过历史和多轮 run 行为稳定后再启用。
- 第 5 步 claim 级结果记分尚未开始；阶段 5 读者出口已可用，但学习闭环仍需后续 `claim_outcome_scores.json`。

### 第 0-3 步验收审核 + Counter-Thesis schema 摩擦与 claim 闸门误伤修复

完成内容：

- 审核 codex 第 0-3 步全部提交（`fe2f154`..`a46b5a0`）与计划外 L4 超时提交 `4e14316`：验收合格，L4 改动未弱化数据闸门（跳过项记入 `skipped`/`degraded`，SEC 角色诚实降级为 cross-check）。
- 用 fresh run `codex_external_timeout_validation` 做行为验证：stub 不再触发降级、竞争裁决出现主导假说、principal/price reflection 均 native、claim 反证已按类型区分、Run Review 零 fail。
- 修复该 run 暴露的两个新问题：
  1. Counter-Thesis LLM 两次尝试均死于 schema 摩擦（漏 `hypothesis_id`；`cannot_establish` 写成字符串；`what_it_cannot_explain`/`failure_conditions` 字段变体），高质量反方内容被整体丢弃。`contracts.py` 为 `CompetingHypothesis.hypothesis_id` 加默认工厂，加字符串→列表 coercion 与已观测字段别名吸收；`orchestrator.py` 保留 `fallback_reason` 不被审计覆写。
  2. Final 支撑链混入说明性 token `known_data_gaps`，导致全部 claim 被 `evidence_refs_not_in_registry` 误标 blocked。台账构建改为只保留 `L#.func` 形式或注册表内的真实引用，剔除项记入 `dropped_non_evidence_tokens`；真实引用缺失仍照常阻断。
- `docs/2026-07-06_STAGE0-4_REVIEW_AND_DIRECTION.md` 写入修正一（黄金坑清单 + 决策稀疏定调）、修正二（claim 级结果记分）、停机准则和 2026-07-07 审核记录。

验证结果：

- `python -m pytest -q`：449 通过。
- 用 `codex_external_timeout_validation` run 中两份被拒绝的原始 LLM 返回回放合约：修复后均通过校验（意味着当时两次尝试本可成功）。
- 启动 `fable_counter_thesis_fix_validation` 验证 run（复用 2026-07-07 数据快照），验证 LLM 反方端到端落地。

第二轮（同日）：验证 run `fable_counter_thesis_fix_validation` 复盘与追加修复：

- 该 run 确认竞争裁决行为正常（主导假说成立、stub 豁免生效、Run Review 零 fail），但 Counter-Thesis 再次以两个**新的**形状变体失败退回 fallback：attempt 1 用 `falsifiers`（正是本库 TypedConflict 等合同的正式字段名，模型从 payload 学来，必然复发）和 `explains_poorly`；attempt 2 把 `principal_counterargument` 写成 `{"summary": ...}` dict。两次的内容质量都很高（失效条件具体到"净流动性 4 周动量 < -50B""铜金比跌破 MA50"级别的可观察阈值）。
- Final 阶段幻觉出 `L5.get_ta_indicators`（真名 `get_qqq_technical_indicators`），经共享 refs 池把全部 6 条 claim 拉黑为 blocked——闸门第二次喊狼来了。
- 追加修复：合约层吸收 `falsifiers`/`explains_poorly` 别名与 dict 反方论点；`_verify_claim_entry` 改为比例原则——无法核验的引用点名降级（`unverifiable_evidence_refs:`），仅当没有任何可核验引用时才阻断。
- 回放验证：两份新失败返回经修复后合约 + 编排器验证器均通过；至此两次真实 run 的全部 4 次 LLM 尝试在修复后都会成功。
- `python -m pytest -q`：449 通过。启动第三次验证 run `fable_counter_thesis_fix_validation_2` 做最终收口。

第三轮（同日）：验证 run `fable_counter_thesis_fix_validation_2` 最终验收通过：

- counter_thesis LLM 阶段 1 次尝试即成功（仍是 flash 模型，证明别名吸收是关键瓶颈）。产出两个真反方假说：其一挑战估值压力（Trailing PE 高分位是低基数效应，Forward PE 分位 58.3% 说明压力已部分吸收），其二挑战趋势弱化判断（头部向等权的健康轮动 vs 趋势反转）；支持/反证 refs 不重叠且语义合理，失效条件具体到"HY OAS 扩大至 500bp 以上""NDX/NDXE 跌破 2.85"级别的可观察阈值。
- 竞争裁决：主线 leading、两个反方 candidate、9 条保留争议、无虚假降级——输出不再是常量。
- claim 台账：publish gate `pass`，6/6 verified，无幻觉引用误伤。
- Run Review 零 fail；`prompt_input_audit.thesis_read=false` 实测成立。
- 阶段 3（Counter-Thesis 真 LLM 化）的行为验收在本 run 内达成；跨市场状态方差验收（历史回测日 run）仍留待后续。

剩余风险：

- 字段别名吸收只覆盖已观测变体；后续新变体应继续在合约层吸收并补测试，而不是放宽 validator 语义。更根治的方向是给 counter_thesis 等认知阶段做按阶段模型路由（当前引擎"上次成功者优先"，反方阶段常落在最弱的 flash 上），已列为 codex 后续项。
- Final/Reviser 阶段目前不校验 evidence_refs 是否在 evidence_index 内，幻觉引用在源头就该被打回（像 counter_thesis validator 那样），已列为 codex 后续项。
- 步骤 2 的"不同市场状态下反方假说有真实差异"验收仍需一个历史回测日 run 确认。

---

## 2026-07-06

### 阶段 0-4 审查后更正：合同关闭，行为未关闭

完成内容：

- 按 `docs/2026-07-06_STAGE0-4_REVIEW_AND_DIRECTION.md` 更正阶段 2/3/4 的完成语义：此前记录的“完成”只代表合同、artifact 管道和最小审计链完成，不代表调查、反方假说和 claim 台账已经具备充分行为质量。
- `InvestigationReport` 增加 `is_deterministic_stub`；当前确定性调查如实标注“未执行真实调查，仅登记缺口”，不得作为真实反证触发竞争裁决降级。
- Counter-Thesis 改为优先走独立 LLM 阶段；确定性构建器只作为失败兜底，并在假说来源中标记为 `deterministic_fallback`。
- Claim 台账改为按 claim 类型匹配反证和失效条件；无法逐条对应时写入降级原因，不再用全局反证池冒充逐条反证。
- Bridge V2 在 SynthesisPacket 中只贡献反馈摘要和未解决问题，不再把 Bridge V1 的冲突和主要矛盾重复计入 Thesis 输入。

状态更正：

- EPI-08 / EPI-10 / EPI-12 / EPI-13：合同与运行管道已关闭，真实行为质量未关闭。
- HAR-05 / HAR-06 / HAR-07 / HAR-08 / HAR-09 / HAR-13：合同、边界和最小 artifact 已关闭，真实调查质量、反方认知质量和跨 run 方差仍需后续 fresh run 验收。
- 阶段 4 的 Evidence Passport / Claim Ledger 合同已关闭；claim-specific 反证已开始落地，但仍需真实 run 检查每条 claim 的语义对应是否足够强。

验证结果：

- 聚焦测试：`python3 -m pytest tests/test_contracts.py tests/test_vnext_orchestrator.py tests/test_run_review.py -q`：64 通过，4 个环境/依赖 warning。
- 全量测试：`python3 -m pytest -q`：444 通过，4 个环境/依赖 warning。
- fresh run 尝试：`python3 src/main.py --models deepseek-v4-flash,deepseek-v4-pro --skip-report --disable-charts --run-id codex_stage1_3_validation` 在实时 L4 成分股 SEC CIK map HTTPS 握手处长时间无输出后中断；中断发生在 vNext artifacts 生成前，本轮不能作为真实产物验收。

剩余风险：

- Counter-Thesis 的真实质量取决于 LLM 输出和证据引用校验；本轮已接入阶段和 fallback，但尚未用两个不同真实市场状态 fresh run 验收方差。
- 动态调查仍不是真工具调查；stub 已诚实标注，后续应在真实反方假说暴露关键分歧后再接动态调查工具。
- 实时 fresh run 还需要处理 SEC CIK map / 外部 HTTPS 卡住时的超时或缓存兜底，否则 L4 多源成分股补全可能阻塞后续 LLM 验收。

---

### vNext 阶段 3：最小竞争裁决落地

完成内容：

- 新增竞争裁决合同：`CompetingHypothesis`、`CounterThesisDraft`、`HypothesisCompetition`、`AdjudicationChangeRecord` 和 `AdjudicationHistory`。
- 在 Bridge V2 之后、Thesis 之前生成 `counter_thesis.json`、`hypothesis_competition.json`、`adjudication_history.json` 和 `competition_adjudication_manifest.json`。
- Counter-Thesis 首次生成只读取 `synthesis_packet.json`、`bridge_memos/bridge_v2.json` 和 `investigation_reports/*.json`，并显式禁止读取 `thesis_draft.json`、`analysis_revised.json`、`final_adjudication.json`。
- `SynthesisPacket` 增加竞争假说摘要，让 Thesis 正式综合前能看到至少主线解释和反方解释；调查结果只能改变假说状态、保留争议或触发重判记录，不回写 L1-L5 layer card。
- 新增非单调重判记录：当 InvestigationReport 挑战强单一路径裁决，或主要矛盾/价格反映来自代码兜底时，保留旧假说、触发证据和降级/保留争议原因。
- Run Review 新增 `competition` 归因检查：缺竞争卷宗会 fail，Counter-Thesis 未禁读 Thesis 会 fail，兜底生成的 principal_contradiction / price_reflection 会 observe，降级/分叉/保留争议记录会被审计。

验证结果：

- 语法检查：`python3 -m py_compile src/agent_analysis/contracts.py src/agent_analysis/orchestrator.py src/agent_analysis/run_review.py` 通过。
- 聚焦测试：`python3 -m pytest tests/test_contracts.py tests/test_run_review.py tests/test_vnext_orchestrator.py -q`：58 通过，4 个环境/依赖 warning。

对抗式审查结论：

- 反方独立性：测试确认 `counter_thesis.json` 在 Thesis 生成前出现，`prompt_input_audit.thesis_read=false`，并把 `thesis_draft.json` 放入 forbidden context。
- 反证不被吞：受控调查的 `claims_challenged` / `cannot_establish` 会进入竞争假说的反证、不能解释项和 `downgrade_or_split_events`，不会直接强化主线。
- 改判可审计：`adjudication_history.json` 保留旧假说、新假说、触发证据、变化类型和原因。
- 兜底可见：Bridge 的 `normalization_notes` 中只要出现主要矛盾或价格反映兜底，竞争卷宗会记录 `fallback_warnings`，Run Review 标记为 observe。
- 隔离边界：新增竞争产物只被 Thesis / governance 读取；L1-L5 输入策略仍禁止 `investigation_reports`、Bridge、Thesis、Final 和事件侧链进入。

剩余风险：

- 2026-07-06 审查后更正：Counter-Thesis 已改为优先走独立 LLM 阶段，确定性构建器只作为失败兜底；解释质量仍需 fresh run 验收。
- 当前重判逻辑以调查报告挑战项和兜底痕迹为触发条件，尚未做更细的证据权重模型；阶段 4 的统一 Evidence Passport / claim 台账会继续增强证据级追踪。

---

## 2026-07-01

### 第二层新闻事件研报重构落地

完成内容：

- 将第二层正式从“事件账本 + 窗口观察”升级为“新闻事件研报 + 跨层问题交付”。
- 新增 `event_mechanism_report.json`、`cross_layer_questions.json`、`event_mechanism_cards.json` 和 `event_mechanism_report.html`。
- 新闻按主线组织，不再按标题列表堆叠；默认主线包括 AI/半导体盈利、宏观利率估值压力、指数结构/广度、信用/流动性，以及其他观察。
- 每条新闻卡生成读者可读字段：标题、来源、日期、摘要、AI 分析、能支持什么、不能支持什么、还要确认什么、缺失证据和置信度。
- 旧 `event_market_validation.json` 保留兼容，但窗口观察降级为 `background_market_observation`，不再写成市场确认新闻，也不在读者页作为验证结论展示。
- 新增第二层独立 HTML 报告，结构对齐样张：新闻事件初步判断、事件快照、主线新闻卡、点击弹窗、事件研究卡、新闻给数据层的问题、主张台账、给综合研报的一句话。
- 综合 vNext brief 优先读取 `event_mechanism_report.json`，事件区改为展示新闻解释、数据待确认问题、证据缺口和给综合研报的交付，不再只是旧 04 标题列表。
- 控制台 `/latest-product` 和 event-only 模式优先打开新版新闻事件 HTML。
- 纯数据 manifest 禁止输入新增 `event_mechanism_report` 和 `cross_layer_questions`，继续防止第二层污染 L1-L5。

验证结果：

- 已用新规则刷新 `output/analysis/vnext/20260701_131914` 的第二层产物、`integrated_synthesis_report.json`、`vnext_brief_20260701_1319.html` 和 `vnext_workbench_20260701_1319.html`。
- 独立新闻事件 HTML 静态验收通过：包含“新闻事件初步判断”“可以说”“不能说”“data-detail”“AI 分析”“给综合研报的一句话”“新闻事件给数据层出的题”；不包含 `earnings_path`、`discount_rate`、`risk_premium`、`Layer 2 Event Mechanism Report`、“第二层可以说”、“新闻导致价格变化”。
- 全量测试：`python3 -m pytest -q`：417 通过，4 个环境/依赖 warning。

剩余风险：

- 新闻分析仍主要基于现有标题、摘要和来源字段；缺 URL、未读全文的材料已降级，但还没有自动追原文、找反方全文或安装专项深度事件研究 workflow。
- 综合 brief 底部嵌入的完整 vNext 数据 JSON 仍包含部分内部 evidence/ref 字段，这是全站审计数据，不属于新版新闻事件区；若未来要彻底面向非技术读者，需要单独做“隐藏审计 JSON / 懒加载审计”的前端治理。

### 综合报告实跑审查与质量修复

完成内容：

- 对 `output/analysis/vnext/20260701_131914` 做三路审查：第一层数据质量、第二层事件研究、第三层综合报告/HTML 可读性。
- 结论：本次 run 没有被 DataIntegrity 闸门挡住，`publish_status=publishable`，最终判断“估值偏高、宏观约束偏紧、只支持战术试探”基本合理；事件材料没有进入 L1-L5 / Bridge / Thesis / Risk / Reviser / Final 的运行 prompt。
- 修复第二层措辞越权：媒体标题不再写成“官方事件”，标题-only claim 的 `fact_part/fact_summary` 只记录“某来源在某时发布某标题”，解释和叙事部分明确未读全文不能推出强解释。
- 修复市场验证措辞：`partly_confirmed` 改为 `temporal_association_observed`，保留“只代表时间关联，不构成因果证明”的边界。
- 修复事件摘要排序：标题-only 不能高置信，ETF NPORT/N-CSR 这类基金文件不会再挤占高重要性事件位。
- 修复 legacy 导出里的“数值冒充分位”：只有字段名明确是 percentile 的值才显示为“分位”，普通价格、ADL、RSI、ATR 不再被写成历史分位。
- Native brief 主文新增“事件与叙事层”小节，用户打开 HTML 就能看到第二层只做解释线索、不能做主证据；审计入口新增 `event_layer_summary.json`。
- 为控制台就绪检测补回兼容标记，避免新旧 launcher 文案造成测试误判。

验证结果：

- 已用新规则刷新本次 run 的派生产物：`event_narrative_ledger.json`、`event_claim_ledger.json`、`event_market_validation.json`、`event_layer_summary.json`、`integrated_synthesis_report.json`、`logic_vnext.json`、`vnext_brief_20260701_1319.html`、`vnext_workbench_20260701_1319.html`。
- 回查确认不再出现 `官方事件`、`partly_confirmed`、`736.4% 分位`、`439.0% 分位`、`106.0% 分位` 等旧问题。
- 全量测试：`python3 -m pytest -q`：415 通过，4 个环境/依赖 warning。

剩余风险：

- 第一层数据证据元信息仍有大量 `source_url`、`coverage`、`vintage_date` 缺口；本轮只修了最误导读者的表达层问题，没有全面补齐数据合约。
- 第二层仍是规则化事件研究，不是全文原文核验和反方材料检索；标题-only 材料现在会降级，但还没有自动深读全文。

### 第二层事件研究 Agent 五段式流水线落地

完成内容：

- 将第二层从旧的“新闻/事件标题侧栏”升级为五段式事件研究流水线：采集与时间闸门、事件聚类与 claim 拆解、事件研究包、市场验证、账本/报告/综合层交付。
- `NewsEventLedgerBuilder` 新增 `event_source_raw.jsonl`，每条材料记录来源、发布时间、信息可见时间、正文可用性、hash、采集状态和第二层边界；历史 run 中未来材料和无日期材料不会进入事件账本。
- `EventNarrativeLedgerBuilder` 现在除 `event_narrative_ledger.json` 外，还会写出 `event_clusters.json`、`event_claim_ledger.json`、`event_research_packets/*.json`、`event_market_validation.json`、`event_layer_summary.json`、`event_adversarial_review.json` 和 `event_narrative_report.md`。
- claim 枚举收敛为计划要求的 7 类：`official_fact`、`company_disclosure`、`data_release_claim`、`interpretation_claim`、`view_claim`、`narrative_claim`、`rumor_claim`；标题-only 材料自动低置信，社媒/未验证信号不能变成官方事实。
- 市场验证器只输出确认程度和时间邻近观察，固定声明不构成因果证明；缺少验证数据时降级为 `insufficient_data`。
- 第三层综合报告显式读取 `event_layer_summary.json`，同时保留 `event_narrative_ledger.json` 兼容旧入口；第二层仍禁止反向流入 L1-L5 / Bridge / Thesis / Risk / Reviser / Final data-only prompts。
- `run_summary.json` 增加完整第二层卷宗路径，方便控制台和后续审计入口读取。
- 顺手修复全量测试暴露的两个既有兼容缺口：恢复 `VNextReportGenerator._data_quality_box`，并为 L3 Top10 集中度补回 `_qqq_equal_weight_performance_spread` 兼容别名（内部仍使用 NDX/NDXE 底层口径）。

验证结果：

- 聚焦测试：`tests/test_news_event_ledger.py tests/test_news_event_data_linker.py tests/test_news_layer_analyzer.py tests/test_three_layer_artifacts.py`：15 通过。
- 主链相关测试：`tests/test_main_cli.py tests/test_main_collect_only.py tests/test_vnext_packet_builder.py tests/test_control_service.py tests/test_research_console.py tests/test_vnext_reporter.py tests/test_prompt_guardrails.py`：64 通过。
- 全量测试：`python3 -m pytest -q`：410 通过，4 个环境/依赖 warning。

对抗式审查结论：

- 未来函数：历史 `effective_date` 下未来材料和无日期材料被排除；实时模式保留但标注日期不确定。
- 标题党：`raw_text_available=false` 的 claim 只能低置信，研究包会记录降级原因。
- 情绪源越权：`unverified_signal` 固定降为 `rumor_claim`，不能生成 `official_fact`。
- 事后讲故事：市场验证只写 `temporal association only; no causal proof`，不允许把新闻写成价格原因。
- 第一层污染：新增产物只由第二层/第三层读取；纯数据 manifest 仍声明禁止 `event_refs`、news/event ledger 和 browser sidecar。

剩余风险：

- Wind financial docs、Yahoo/Alpha Vantage、社媒等 adapter 目前是结构预留，尚未完成真实自动接入；当前真实采集仍以官方 RSS 和 SEC EDGAR 为主。
- 事件研究包目前是规则化研究包，不是 LLM 深度调查；重大事件的原文追踪、全文公告/filing 阅读和反方材料检索仍属于后续深度模式。

## 2026-06-30

### 三层研报架构工程接入第一版

完成内容：

- 实施第一层 data-only 隔离：`AnalysisPacketBuilder` 默认不再把 `event_refs` 写入分析包；`--enable-news` 仍可生成新闻/事件材料，但不再传给纯数据 Bridge / Thesis 主链。
- 新增 `event_narrative_ledger.json` 第二层产物：把现有 `news_event_ledger`、`news_event_data_links`、`news_layer_analysis` 整理成 claim 级事件与叙事账本，写清来源、发布时间、信息可见时间、影响链路、能力边界和待验证条件。
- 新增 `pure_data_report.json` 第一层 manifest：明确纯数据报告的 artifact 入口和禁止输入，包括 news sidecar、browser sidecar、event refs 等。
- 新增 `integrated_synthesis_report.json` 第三层产物：读取纯数据报告和事件账本，输出综合判断、冲突矩阵、未解释项、降级 claim 和发布闸门；DataIntegrity blocked 时只允许 audit-only，不输出正式综合主判断。
- 控制台、`/latest-product` 和 native brief 审计入口增加三层产物链接：纯数据研报、事件与叙事账本、综合总报告。
- 调研 Wind skill 后采用保守接入策略：已装 `wind-mcp-skill` 可作为未来第二层公告/新闻/宏观候选来源；本轮不安装额外 Wind 工作流 skill，不让 Wind 新闻事件进入第一层正式数据证据链。

验证结果：

- 语法检查：`py_compile` 覆盖 `src/main.py`、新增三层产物模块、packet builder、reporter、console 和 control service，通过。
- 聚焦测试 1：`tests/test_three_layer_artifacts.py tests/test_vnext_packet_builder.py tests/test_news_layer_analyzer.py tests/test_news_event_data_linker.py -q`：26 通过。
- 聚焦测试 2：`tests/test_main_cli.py tests/test_main_collect_only.py tests/test_control_service.py tests/test_research_console.py -q`：20 通过。
- 聚焦测试 3：`tests/test_vnext_reporter.py tests/test_vnext_orchestrator.py tests/test_bridge_v2.py tests/test_run_review.py -q`：61 通过。

剩余风险：

- 第三层综合报告第一版是规则化 JSON 裁决，不是新的 LLM 长文报告；后续可在 data-only 边界稳定后再增加更强的可读正文。
- Wind 公告/新闻来源尚未工程化为自动采集器；当前只是为第二层保留明确边界和接入位置。

### 三层研报架构第一性原理审查与对抗式修复

完成内容：

- 新增 `docs/2026-06-30_THREE_LAYER_ARCHITECTURE_FIRST_PRINCIPLES_REVIEW.md`，对 6 月 27 日三篇三层架构想法文档做第一性原理审查、对抗式挑错和修复版架构整理。
- 明确总体结论：三层架构方向正确，但不能只理解成“三份报告”；更稳健的定义是数据、事件、综合判断三种证据状态隔离生产、分级升级、受控交叉。
- 找出关键破口：当前代码里 `event_refs` 已可进入 Bridge / Thesis，因此若要严格实现“第一层纯数据研报”，需要 data-only Bridge / Thesis / Final 运行路径，不能让事件材料进入数据侧综合。
- 建议把第二层从“新闻摘要”升级为“事件与叙事账本”，按 claim 粒度记录来源、发布日期、事件日期、信息可见时间、金融链路、能力边界和待验证条件。
- 建议把第三层从“综合长文”升级为“综合矛盾裁决报告”，每个重要判断必须有判断对象、解释等级、数据支持、事件支持、价格反映、反证、未解决张力、失效条件和发布闸门。

验证结果：

- 文档审查和研究结论沉淀，无运行链路修改；后续工程接入仍需按 `NEXT_STEPS.md` 的三层研报架构攻坚拆分实施。

## 2026-06-27

### 三层研报架构文档与后续路线重写

完成内容：

- 新增 `docs/2026-06-27_THREE_LAYER_REPORT_ARCHITECTURE_PLAIN.md`，用通俗语言说明三层结构：纯数据研报、新闻/事件简报、综合总报告。
- 明确三份报告独立生成、独立入口、独立阅读：纯数据研报继续保持现有 vNext 正式数据链，新闻/事件简报单独解释外部世界，综合总报告读取前两者后做交叉质询并给出谨慎但明确的解释。
- 更新 `NEXT_STEPS.md`，把 P1 后续攻坚改为“三层研报架构接入攻坚”，完成标准聚焦三份报告独立落盘、互相引用但不互相覆盖。
- 删除不合适的旧研究 skill 文件；同时撤回新建 skill 的尝试。当前阶段先不新建 skill，优先把产品结构、阅读入口和工程路线讲清楚。

验证结果：

- 文档和路线变更，无运行链路修改；后续仍需工程化接入 `news_event_brief` 与 `integrated_synthesis_report`。

## 2026-06-26

### L3 集中度口径：从 QQQ/QQEW 迁移到 NDX/NDXE

完成内容：

- 新增 `get_ndx_ndxe_ratio`，使用 `^NDX / ^NDXE` 日线收盘价计算市值加权 Nasdaq-100 相对等权 Nasdaq-100 的强弱、MA20 趋势和 5 年 / 10 年分位。
- 将主采集链、packet builder、canon、Prompt、报告核心图册、workbench、chart_time_series、demo 脚本和测试迁移到 `get_ndx_ndxe_ratio` / `NDX_NDXE_RATIO`。
- 保留 `get_qqq_qqew_ratio` 和 `QQQ_QQEW_RATIO` 作为旧 run 兼容入口；新 run 不再把 QQEW 当作纯 NDXE 代理。
- 更新 `RESEARCH_CANON.md`、`ARCHITECTURE.md`、`NEXT_STEPS.md` 和权威证据研究文档，明确底层研究口径优先用 NDX/NDXE，ETF 代理只能作为交易实现或辅助核对。

验证结果：

- `scripts/probe_ndx_ndxe_ratio.py --end-date 2025-04-09`：可用，`latest_ratio=2.657693`，5 年分位 `94.59%`，10 年分位 `97.30%`，共同交易日 `2773`。
- 真实函数轻测：`get_ndx_ndxe_ratio("2025-04-09")` 返回 `series_id=NDX_NDXE_RATIO`，旧 `get_qqq_qqew_ratio` 返回同一新口径并标记 `replacement_function_id=get_ndx_ndxe_ratio`。
- 聚焦测试：`.venv/bin/python -m pytest tests/test_l3_breadth_data.py::test_ndx_ndxe_ratio_yfinance_request_includes_effective_date tests/test_chart_time_series_artifacts.py tests/test_interactive_chart_workbench.py tests/test_deep_research_canon.py tests/test_vnext_packet_builder.py tests/test_tools_smoke.py tests/test_objective_firewall.py tests/test_vnext_orchestrator.py -q`：79 通过，5 个 warning。
- 语法检查：`py_compile` 覆盖本次触及的主要 Python 文件，通过。
- 备注：包含 `tests/test_data_evidence_contract.py` 的更宽测试组合中仍有 1 个既有失败：`VNextReportGenerator` 缺少 `_data_quality_box`；该失败不属于本次 NDX/NDXE 迁移路径。

### 双轨研究路线修正：替代“数据先行、新闻后行”

完成内容：

- 重写 `docs/2026-06-24_AUTHORITATIVE_EVIDENCE_RESEARCH_PLAIN.md`：把旧的“数据先发现问题、新闻后补语境”改为“数据轨道与事件轨道独立观察、受控交叉、分级升级”。
- 更新 `NEXT_STEPS.md`：P1 攻坚项改为“数据与事件双轨研究接入攻坚”，完成标准改为分开产出 `cross_track_questions.json`、`event_track_observations.json`，再由受控交叉层输出候选语境。
- 改造本地 skill `/Users/aidianchi/.codex/skills/authoritative-evidence-research/`：保留来源分级、候选状态、人工复核和升级规则；删除“从数据提出的问题开始”的单向流程，改为 `event_track_scan`、`data_track_question_intake`、`controlled_cross_review`、`formal_source_gap` 四种模式。

验证结果：

- 文档和 skill 变更，无运行链路修改；后续仍需工程化接入 run 目录、控制台和 brief。

## 2026-06-24

### AGENTS.md 入口重写与通俗沟通前置

完成内容：

- 重写 `AGENTS.md`，把“先跟用户讲清楚”放到最前面，明确默认用通俗语言说明改什么、为什么、影响和验证结果。
- 将 AGENTS.md 从 67 行压缩到 35 行，只保留通俗沟通要求、项目一句话目标、硬红线和按需读取入口。
- 删除常用命令清单和通用执行纪律；命令仍由 `README.md` 承担，具体验证流程由任务相关文档按需提供。

验证结果：

- 文档变更，无运行链路修改；已人工复读 `AGENTS.md`，确认通俗沟通要求在最前，关键架构红线仍保留，常用命令不再常驻。

### 权威证据研究助理通俗说明文档

完成内容：

- 新增 `docs/2026-06-24_AUTHORITATIVE_EVIDENCE_RESEARCH_PLAIN.md`，用通俗语言梳理新闻源降级、问题驱动研究助理、skill 当前能力和后续接入路线。
- 明确当前推荐分工：L1-L5 / Bridge / Thesis / Risk / DataIntegrity 负责提出问题，Research Intake 负责整理问题，`authoritative-evidence-research` skill 负责候选研究，不直接进入 L1-L5 或 `evidence_ref`。
- 明确下一步不是扩大新闻功能，而是先做 `external_context_requests` 问题出口，再接控制台调用 skill，最后建立候选材料升级规则。

验证结果：

- 文档变更，无运行链路修改；已人工复读确认覆盖“用户想法、已做 skill、当前功能、下一步计划”四项。

### 数据源可用性：修复 L5/Twelve Data 来源标记、Clash 规则与发布闸门

完成内容：

- 复查 `20260618_215209` 最新失败 run，确认 L5 全部无有效指标、L4 Wind 与 L5/yfinance/Twelve Data 在 Clash 全局模式下可恢复，根因偏向网络路由与 fallback 可观测性不足。
- 修复 `cached_yf_download`：Twelve Data / yfinance / 持久缓存 / 内存缓存会给 DataFrame 写入真实来源标签；Twelve Data 优先路径失败会进入运行诊断，不再被静默吞掉。
- 修复 L5 输出：`get_l5_deterministic_snapshot`、`get_qqq_technical_indicators`、`get_multi_scale_ma_position` 不再写死 `source_name="yfinance"`，而是透传真实数据源；yfinance 未安装但 Twelve Data 可用时仍可取 QQQ 日线。
- 加严 DataIntegrity 发布闸门：真实多指标 run 总体置信度低于 60% 时阻断；L1-L5 任一正式层在至少 3 个指标下成功数为 0 时阻断，避免 L5 全挂仍被标成 publishable。
- 修复 Clash 规则模式：保持 DeepSeek 直连在最前，新增 NDX 数据源代理规则，包括 Yahoo/yfinance、Twelve Data、Alpha Vantage、FRED/StLouisFed、Nasdaq、Invesco、SEC、Finnhub、SimFin、CNN/Fed/BLS/BEA、Damodaran/WorldPERatio/Trendonify 等；保留配置备份 `clash-verge.yaml.bak_20260624_2000`。

验证结果：

- 规则模式运行态确认：Clash controller 返回 `mode=rule`，TUN 开启，新增规则已进入运行态。
- 网络轻测：DeepSeek 直连返回 401（网络通，未带鉴权）、Yahoo chart 返回 200、Twelve Data 返回 200。
- 真实数据轻测：`cached_yf_download("QQQ", 2026-06-01..2026-06-24)` 返回 16 行，最后日期 `2026-06-23`，来源标签为 `Twelve Data`。
- Wind L4 轻测：`get_ndx_wind_valuation_snapshot()` 返回可用，来源为 `Wind index_data.get_index_fundamentals`。
- 聚焦测试：`.venv/bin/python -m pytest tests/test_yfinance_cache_resilience.py tests/test_ta_l5_and_pdr_sources.py tests/test_l4_external_valuation_sources.py tests/test_core_checker.py tests/test_run_review.py -q`：58 通过。

## 2026-06-18

### 正式 reporter：修复核心图册居中留白与目录对齐

完成内容：

- 按用户在浏览器批注中指出的“右边留空 / 左右留空 / 导航居中是否合理”继续返修核心阅读区。
- 将 brief 顶部章节导航从居中装饰改为与正文左边线对齐，符合研报目录的阅读习惯。
- 核心证据图册的 sparkline 从 420×92 小画布改为 760×132 宽画布，避免宽屏卡片里 SVG 使用默认等比居中而产生大面积左右空白。
- 图册里的 SVG 左对齐显示，保留仅 10px 的图内安全边距；正文段落仍保留合理行长限制，避免长行影响阅读。

验证结果：

- `.venv/bin/python -m py_compile src/agent_analysis/vnext_reporter.py`：通过。
- `.venv/bin/python -m pytest tests/test_vnext_reporter.py -q`：19 通过，4 个第三方库 deprecation warnings。
- `.venv/bin/python src/agent_analysis/vnext_reporter.py --run-dir output/analysis/vnext/20260617_024610 --template brief`：成功重新生成 `output/reports/vnext_brief_20260617_0230_20260617_0246.html`。
- Chrome 877×763 视口复验：导航左边线与正文 shell 左边线差值为 0；QQQ 与 ERP 图在 SVG 内左右空白各约 10px；页面横向溢出为 0。

### 正式 reporter：返修 L1-L5 展开态宽屏排版硬伤

完成内容：

- 按用户截图复核并返修三处仍不合格的桌面排版：微图标签压住折线、证据/发言权说明占据错误窄栏、L4 估值宽表被挤成半栏。
- 微图生成逻辑增加顶部标签安全区；标签不再和折线路径共享同一垂直区域，并用文字描边提高可读性。
- L1-L5 展开底稿里的复杂指标可视化改为整行铺开；估值交叉校验表从窄栏恢复为 1110px 左右的可读宽表。
- “证据发言权”改为默认折叠的一行说明，避免普通阅读时被审计解释盒撑开；同时修正 `.layer-detail summary` 选择器过宽导致嵌套 summary 继承大标题 grid 的问题。
- 指标 ref 芯片放宽并覆盖断词规则，避免长函数名最后一个字母单独掉行。

验证结果：

- `.venv/bin/python -m py_compile src/agent_analysis/vnext_reporter.py`：通过。
- `.venv/bin/python -m pytest tests/test_vnext_reporter.py -q`：19 通过，4 个第三方库 deprecation warnings。
- `.venv/bin/python src/agent_analysis/vnext_reporter.py --run-dir output/analysis/vnext/20260617_024610 --template brief`：成功重新生成 `output/reports/vnext_brief_20260617_0230_20260617_0246.html`。
- Chrome 1440×1000 桌面复验：`bodyOverflowX=0`；5 个 layer 全部展开；41 个证据合约按钮；41 个“证据发言权”默认折叠；微图标签垂直遮挡数为 0。
- 重点截图复验：`get_vxn_vix_ratio` 卡片高度从过度展开收至 255px；L4 估值表容器宽 1110px、无内部横向裁切；长 ref `get_ndx_pe_and_earnings_yield` 一行显示。
- 证据合约抽屉交互复验：点击 `L2.get_vxn_vix_ratio` 的“证据合约”后右侧抽屉打开，显示 8 行合约字段，并包含数据日期字段。

### 正式 reporter：证据合约改为抽屉，修复 L1-L5 桌面展开排版

完成内容：

- 按用户确认的阅读策略，将指标正文里的完整“证据合约”从默认展开底稿中移除，改为轻量证据状态条：`数据时间｜来源｜缺口｜证据合约`。
- `数据时间` 优先使用数据本身对应的 `data_date / as_of_date / effective_date / vintage_date`，不再把 run 采集时间作为正文第一信息；`collected_at_utc` 保留在抽屉中供审计排查。
- 每个指标新增“证据合约”按钮，点击后复用右侧证据抽屉展示完整合约，包括合约版本、来源、来源等级、数据日期、采集时间、可用性、授权边界、方法口径、估值来源对照、异常与缺口。
- 修复 L1-L5 展开底稿桌面排版根因：去掉 `.indicator-list li.no-micro` 的窄栏限制，指标主行和详情行在 1440px 桌面视口下铺满约 1134px，不再被压成约 500px 窄列。
- 指标详情区改为“相对位置/可视化”和“证据发言权”并排；完整数据质量不再参与正文网格占位，避免右侧大面积空白和审计盒竖排。
- 清理旧静态 `data-quality-box` 渲染路径、估值来源静态列表渲染函数和对应 CSS，避免两套证据展示逻辑并存。

验证结果：

- `.venv/bin/python -m py_compile src/agent_analysis/vnext_reporter.py`：通过。
- `.venv/bin/python -m pytest tests/test_vnext_reporter.py -q`：19 通过，4 个第三方库 deprecation warnings。
- `.venv/bin/python src/agent_analysis/vnext_reporter.py --run-dir output/analysis/vnext/20260617_024610 --template brief`：成功重新生成 `output/reports/vnext_brief_20260617_0230_20260617_0246.html`。
- 本机 Chrome 以 1440×1000 桌面视口打开最新 HTML、展开全部五层底稿：41 个指标、41 个证据状态条、41 个证据合约按钮；旧 `.data-quality-box` 渲染数为 0；检测到的窄栏指标数为 0。
- 抽屉交互验证：点击第一条 `证据合约` 后右侧抽屉成功打开；抽屉内显示完整数据证据合约，`missing / not_available / available / official` 等机器值已转成人话。

### 正式 reporter：修复 L1-L5 展开态微图占位浪费

完成内容：

- 按用户在 `get_qqq_qqew_ratio` 展开底稿处的批注，修复 L1-L5 指标展开态的布局。
- 指标展开态改为两层结构：第一层放指标名、可信度、时间戳、当前读数和微图；第二层再铺开相对位置、数据质量、证据合约和误读防线。
- 微图不再独占右侧整列，也不再与大量数据质量文字错位；审计细节改为横向使用整行空间。
- 指标名列加宽并改为上下排布，避免长函数名被压成竖排。

验证结果：

- `.venv/bin/python src/agent_analysis/vnext_reporter.py --run-dir output/analysis/vnext/20260617_024610 --template brief`：成功重新生成正式报告。
- `.venv/bin/python -m pytest tests/test_vnext_reporter.py`：19 通过，4 个第三方库 deprecation warnings。
- 使用本机 Chrome 打开生成后的 HTML，展开 L3 并裁切 `#evidence-L3-get_qqq_qqew_ratio`：页面无横向溢出；指标主行宽度约为 `190 / 568 / 340`，微图贴近读数，审计细节下方铺满约 1134px 宽度。

### 正式 reporter：桌面版排版深修与视觉验收

完成内容：

- 针对最新正式 `brief` 的电脑浏览器阅读问题继续收口：去掉左侧 sticky rail 遗留逻辑，主体固定为居中纸面宽度，避免内容被挤到右侧。
- 主判断区改为更克制的买方图册 memo：压缩重复动作层，保留“本页读法 / 价格定价 / 赔率判断 / 优先复核”四格摘要，减少开头冗余。
- 六张核心图卡保留，但把 evidence refs 默认折叠，正文先读判断和图，审计入口按需展开。
- 冲突区改成读者语言：主要冲突、互相确认、压力传导、Bridge 判断、需保留的旧口径冲突；raw id 收进审计细节，避免正文像后台字段。
- L1-L5 底稿摘要改为分行叙事和中文置信度；增加“置信度不是模型自信程度”的解释，避免黑箱误解。
- 修复桌面排版硬伤：删除悬浮导航遮挡正文、清理 12px 以下小字、修复标题层级跳级、加深弱文字对比度、移除多处英文后台标签。
- 字体栈从 Inter 优先改为 Mac 中文阅读更自然的 Avenir Next / PingFang / Hiragino，降低产品后台感。

验证结果：

- `.venv/bin/python src/agent_analysis/vnext_reporter.py --run-dir output/analysis/vnext/20260617_024610 --template brief`：成功生成 `output/reports/vnext_brief_20260617_0230_20260617_0246.html`。
- `.venv/bin/python -m pytest tests/test_vnext_reporter.py`：19 通过，4 个第三方库 deprecation warnings。
- `impeccable --json output/reports/vnext_brief_20260617_0230_20260617_0246.html`：低对比、过小字号、标题跳级、裁切等硬伤清零；仅剩章节编号/section kicker 重复这类刻意保留的阅读顺序建议项。
- 使用本机 Chrome 以 1280×900 桌面视口重新渲染并裁切检查：页面无横向溢出，主体宽 1180px 居中，导航为普通流式位置不再遮挡中段内容，所有可见文字不低于 12px，6 个 proof refs 默认折叠。
- 肉眼复核首屏、主判断图册、冲突与共振、L1-L5 底稿：核心阅读链条成立，右侧拥挤和无效留白问题已显著缓解。

## 2026-06-17

### 正式 reporter 收口：墨兰纸面 · 可审计买方投资判断书

完成内容：

- 将正式 `brief` 从 demo 迁移阶段进一步收口为五个并列阅读入口：主判断、风险与反证、冲突与共振、L1-L5 底稿、数据与审计。
- 首屏改为买方 memo 结构：一句主判断、三条仓位动作、最大反证、中文置信度解释、审批状态、发布状态、指标覆盖和输入跨度。
- 核心图册固定为 6 张证据卡：QQQ 价格趋势、估值赔率、10Y 实际利率、HY OAS 总量利差、CCC-BB 质量利差、QQQ/QQEW 内部结构。
- 图册和底稿微图修正金融语义：正式 10年/5年分位只来自指标读数或正式历史统计；技术指标显示动量、距离、ATR、MACD柱、CMF 等语义读数，不再默认展示短窗口“图内位置/分位”。
- 正式 `brief` 不再把全量运行包塞入主 HTML。页面脚本只保留 evidence drawer 所需的轻量 indicator 索引；完整大 JSON 留在 run 目录，并新增报告旁的 `_audit_index.json` 指向 DataIntegrity、run summary、Prompt Inspector、L1-L5、Bridge、chart series 和 sidecar 新闻材料。
- 新闻源与治理区不再作为主阅读章节出现，改为数据与审计里的侧边材料入口；避免主报告退化为后台展示页。
- 版式改为墨兰纸面：克制蓝墨 accent、首屏左右结构、双证据段改为左文右侧纵向证据卡，避免两张信息密集卡片并排挤压。
- 更新 `tests/test_vnext_reporter.py`，把旧“新闻源/治理主章节/大 JSON 展开”的契约改为“轻量 brief + 外部审计索引”的新契约。

验证结果：

- `.venv/bin/python -m py_compile src/agent_analysis/vnext_reporter.py`：通过。
- `.venv/bin/python -m pytest tests/test_vnext_reporter.py`：19 通过，4 个第三方库 deprecation warnings。
- `.venv/bin/python src/agent_analysis/vnext_reporter.py --run-dir output/analysis/vnext/20260617_024610 --template brief`：成功生成 `output/reports/vnext_brief_20260617_0230_20260617_0246.html`。
- 主 HTML 体积从上一轮约 23.8MB 降至约 0.43MB；旁路审计索引 `output/reports/vnext_brief_20260617_0230_20260617_0246_audit_index.json` 约 4.8KB。
- HTML 结构检查：导航为 `主判断 / 风险与反证 / 冲突与共振 / L1-L5 底稿 / 数据与审计`；章节编号为 01-05；包含 6 张 proof card、5 个 layer detail、26 个 indicator micro chart；无 `新闻源` 主章节、无 `Governance` 主章节、无 raw JSON 展开。
- 金融语义检查：未出现 `近90日分位`、`近1年分位`、`图内位置`、`页面使用的原生 JSON`。
- `impeccable` 禁用项扫描：未发现 `#000` / `#fff`、渐变文字、粗侧边色条、负字距或流式字体缩放。
- 使用本机 Chrome headless 打开本地 HTML 截图检查：页面可渲染，首屏可见主判断/动作/反证/置信度，无横向溢出，6 张证据卡、5 层底稿和 26 个微图均存在。

### 正式 reporter：迁移买方图册 Memo 为默认 brief 报告

完成内容：

- 将已确认的“买方图册 Memo”从 demo 迁入正式 `vnext_reporter.py`，最新 run 生成 `brief` 时直接输出新的主阅读层，而不是继续生成旧版总览。
- 正式报告阅读顺序调整为：买方图册 Memo、风险与反证、新闻源、冲突与共振、L1-L5 底稿、数据与审计、总览。
- 主报告保留买方动作层、三段动作含义、主判断、优先反证和四段图册式推理链：市场状态、硬约束、信用信号、市场宽度。
- L1-L5 底稿迁入正式报告：每层保留可展开审计、分条叙事、风险旗标、跨层钩子、关键指标读数、数据质量、权限类型和误读防线。
- 主图册和底稿微图统一使用正式金融语义口径：能读到 `10年分位` / `5年分位` 的指标用对应窗口；覆盖不足时显式显示 `图自YY.MM.DD`；技术指标则展示更合适的动量、距离、方向或风险读数。
- 置信度标签改为中文高/中/低，并保留为提示性信息；底层审计仍以数据质量、反证和权限边界为准。

验证结果：

- `.venv/bin/python -m py_compile src/agent_analysis/vnext_reporter.py`：通过。
- `.venv/bin/python -m pytest tests/test_vnext_reporter.py`：19 通过。
- `.venv/bin/python src/agent_analysis/vnext_reporter.py --run-dir output/analysis/vnext/20260617_024610 --template brief`：成功生成正式报告 `output/reports/vnext_brief_20260617_0230_20260617_0246.html`。
- HTML 检查：正式报告包含 `买方图册 Memo`、`新闻源`、`L1-L5 可展开审计层`、`Permission Type`、`Agent Health`；未发现 `近90日分位` 或 `近1年分位` 作为页面标签。
- `impeccable` 禁用项扫描：未发现 `#000` / `#fff`、渐变文字、粗侧边色条、负字距或流式字体缩放。
- 浏览器插件因本地 `file://` 跳转安全策略阻止打开新页面；未绕过该限制。本次以生成器、测试和 HTML 结构检查完成验证。

### 买方图册 Memo demo：10年分位对应10年微图，覆盖不足必须显式标注

完成内容：

- 按用户反馈继续修正微图语义：凡图上标注 `10年分位` 或 `5年分位`，微图自动改为对应年份窗口，而不是默认近 90 个点。
- `sparkline` 新增按年份取样逻辑；同时对长日频序列做降采样，避免 10 年日频 path 让 HTML 过度膨胀。
- 主报告中实际利率、VXN、QQQ/QQEW、Damodaran ERP 等具备 10 年图表序列的指标，微图起始时间现在回到 2016 年附近。
- HY OAS、CCC-BB 质量利差的 `chart_time_series` 当前仅从 2023-06 开始；页面不伪装为 10 年图，而是在标签里显式显示 `图自23.06.19`，同时仍保留正式 10 年分位。
- L1-L5 底稿微图继承同一规则：正式 10年/5年分位对应长窗口图；技术指标仍保持短窗口语义图。

验证结果：

- `.venv/bin/python -m py_compile scripts/generate_report_demos.py`：通过。
- `.venv/bin/python scripts/generate_report_demos.py`：成功重新生成 12 个页面。
- HTML 检查：`demo_memo_chartbook.html` 中 `近90日分位` 为 0、`近1年分位` 为 0；存在 2016 起始的 10年图；HY OAS / CCC-BB 等覆盖不足图显示 `图自23.06.19`。
- 输出体积检查：`demo_memo_chartbook.html` 约 104KB，`demo_layers.html` 约 102KB，降采样后没有因 10 年日频图造成异常膨胀。
- `impeccable` 禁用项扫描：未发现 `#000` / `#fff`、渐变文字、粗侧边色条、负字距或流式字体缩放。

### 买方图册 Memo demo：分位口径从短窗口修正为金融语义口径

完成内容：

- 按用户质疑修正买方图册主报告的分位使用原则：不再把小图最后 90 个点或近 1 年位置称为历史分位。
- 主报告证据卡优先使用最后一次 run 中 L1-L5 已计算的正式 10 年历史分位。
- QQQ 价格卡取消价格分位，改为价格、20日动量、距SMA60、Donchian通道位置和 MACD柱。原因是价格本身长期漂移，价格分位容易误导。
- VXN、10Y实际利率、HY OAS、CCC-BB质量利差、QQQ/QQEW 改为正式 10年分位：分别约 72%、96%、4%、95%、99%。
- 小图默认标签从 `近90日分位` 降级为 `图内位置`，并优先被正式分位或语义标签覆盖。
- L1-L5 底稿微图也优先从本层读数中提取正式 10年/5年分位；技术指标继续显示 RSI、ATR、MACD柱、成交量、CMF 等语义读数。

验证结果：

- `.venv/bin/python -m py_compile scripts/generate_report_demos.py`：通过。
- `.venv/bin/python scripts/generate_report_demos.py`：成功重新生成 12 个页面。
- HTML 检查：`demo_memo_chartbook.html` 中 `近90日分位` 为 0、`近1年分位` 为 0；主报告出现 `10年分位 96% / 72% / 4% / 95% / 99%`。
- 全部 demo HTML 检查：未发现 `近90日分位` 或 `近1年分位` 残留。

### 买方图册 Memo demo：修复双图段落拥挤与置信度黑箱感

完成内容：

- 按浏览器批注修复买方图册主报告中 `01 / Market state`、`03 / Credit signal` 的版式错误：两张证据卡不再挤在右侧窄栏，而是文字在上、两张图卡横向铺满。
- 保留 `02 / Hard constraint`、`04 / Market breadth` 的单图左右结构，因为一张图时该结构顺读性较好。
- 图卡数字 chip 改为自适应最小宽度，避免被压成竖牌，解决“右边拥挤错位”的根因。
- 所有置信度标签从 `high/medium/low` 改为中文 `高/中/低`。
- 在 L1-L5 审计层增加置信度说明：当前置信度是各层 agent 对本层证据覆盖、数据质量和反证压力的自评，页面只作提示；正式版应拆成可审计评分项。

验证结果：

- `.venv/bin/python -m py_compile scripts/generate_report_demos.py`：通过。
- `.venv/bin/python scripts/generate_report_demos.py`：成功重新生成 12 个页面。
- HTML 检查：`demo_memo_chartbook.html` 有 2 个双证据 `memo-pair` 段落、6 张证据卡；`置信度 medium` 已为 0，`置信度 中` 出现 6 处。
- 877px 桌面截图检查：双证据段落两张卡片宽度约 408px，数字 chip 最小宽度约 119px；单图段落卡片宽度约 503px。
- `impeccable` 禁用项扫描：未发现 `#000` / `#fff`、渐变文字、粗侧边色条、负字距或流式字体缩放。

### 买方图册 Memo demo：底稿指标改为左文右图

完成内容：

- 按浏览器批注调整 `demo_layers.html` 的指标底稿布局：有微图的指标改为左侧读数与叙事、右侧微图，减少纵向拖沓。
- 没有可靠微图的指标保持单列文本，不为了版式整齐留下空白图位，也不伪造走势。
- 右侧微图高度略放大，保留左下角起始时间和语义化标签，使它更像“审计图”而不是正文下面的一条装饰线。
- 移动端继续回到上下排列，避免窄屏左右挤压。

验证结果：

- `.venv/bin/python -m py_compile scripts/generate_report_demos.py`：通过。
- `.venv/bin/python scripts/generate_report_demos.py`：成功重新生成 12 个页面。
- HTML 检查：`demo_layers.html` 有 26 个 `has-micro` 左文右图条目、15 个 `no-micro` 单列条目；保留 26 个起始时间标注；`当前分位` 仍为 0。
- `impeccable` 禁用项扫描：未发现 `#000` / `#fff`、渐变文字、粗侧边色条、负字距或流式字体缩放。

### 买方图册 Memo demo：微图标注改为“按指标语义发言”

完成内容：

- 按浏览器批注修正 L1-L5 底稿页微图标注逻辑：不再把“分位”当作所有微图的默认答案。
- 微图左下角新增小号起始时间，读者可以一眼知道这段走势从什么时候开始，而不需要猜测窗口长度。
- 保留分位只给真正适合用分位解释的指标，例如实际利率、信用利差、VIX/VXN、QQQ/QQEW、ERP 等。
- ATR、RSI、MACD、OBV、成交量、CMF、价格等指标改为展示各自最该看的核心读数，例如 `ATR 15.69`、`RSI 62.5`、`MACD柱 -3.10`，避免错误暗示。
- 移除 ADX 等缺少合适独立时间序列时的伪微图；没有可靠图就只保留当前读数和叙事，不为了美观伪造证据。
- 顺手把底稿页里仍像机器字段的质量自检内容压成普通句子，减少阅读噪音。

验证结果：

- `.venv/bin/python -m py_compile scripts/generate_report_demos.py`：通过。
- `.venv/bin/python scripts/generate_report_demos.py`：成功重新生成 12 个页面。
- HTML 检查：`demo_layers.html` 中 `当前分位` 已为 0；保留 26 个起始时间标注、12 个近 90 日分位标注；ATR/RSI/MACD 显示语义化读数。
- 证据边界检查：未发现 ADX 区块继续使用 QQQ 价格假微图；未发现 `coverage_complete` 等内部字段泄漏。
- `impeccable` 禁用项扫描：未发现 `#000` / `#fff`、渐变文字、粗侧边色条、负字距或流式字体缩放。

### 买方图册 Memo demo：优化墨蓝纸面版 L1-L5 摘要与底稿微图

完成内容：

- 按浏览器批注优化墨蓝纸面版底部 L1-L5 展开层：把每层长段摘要拆成 3 条可扫读摘要，并对关键指标名、百分比、bp、SMA/MACD/RSI 等读数做克制加粗。
- 展开后的层结论改为分句叙事列表，避免大段灰字造成阅读疲劳。
- 独立 `demo_layers.html` 的指标区从“函数名 + 单句读数”升级为“指标名 / 置信度 / 当前读数 / narrative 解释 / 可用微图”。
- 从本次 run 已有 `chart_time_series.json` 恢复可用微图；没有独立时间序列的指标不伪造图，只保留读数和解释。
- 清理跨层钩子里嵌套 JSON 字符串的展示问题，避免底稿页暴露内部字段结构。

验证结果：

- `.venv/bin/python -m py_compile scripts/generate_report_demos.py`：通过。
- `.venv/bin/python scripts/generate_report_demos.py`：成功重新生成 12 个页面。
- HTML 结构检查：`demo_memo_chartbook.html` 保留 5 个 L1-L5 展开层、5 个分行摘要、5 个分句叙事列表、23 个底稿微图；`demo_layers.html` 保留 5 个展开层、5 个分行摘要、5 个分句叙事列表、27 个底稿微图。
- 页面文本检查：不再暴露 `target_layer` / 嵌套 JSON 字符串；L1/L2 指标叙事中可检索到“曲线已从倒挂修复”“VXN 处于历史偏高百分位”等 narrative 内容。

### 买方图册 Memo demo：按 impeccable 深度美化，新增三种审美方向

完成内容：

- 按 `impeccable` 的产品界面规则重做买方图册 Memo 的视觉系统：保留浅底纸面和研究工具气质，但强化标题层级、段落换行、分条动作、证据卡色彩含义和数字标签。
- 新增三种同内容审美版本：`demo_memo_chartbook.html`（A 墨蓝纸面）、`demo_memo_chartbook_warm.html`（B 暖纸投委）、`demo_memo_chartbook_crisp.html`（C 清爽研究台）。
- 三版共享同一套最后一次 run 数据、同一套章节、同一套 6 张核心图、24 个佐证数据标签和 L1-L5 可展开审计入口，避免因换风格造成信息缺失。
- 图表证据卡按语义区分颜色：价格、宏观约束、风险、信用确认、内部结构分别使用不同强调色；颜色只承担状态和证据类型，不做装饰性炫技。
- 标题改为“小编号 / 中文标题 / 分条观点”的顺读节奏，使主文更像买方研报，而不是连续堆叠的页面卡片。

验证结果：

- `.venv/bin/python -m py_compile scripts/generate_report_demos.py`：通过。
- `.venv/bin/python scripts/generate_report_demos.py`：成功生成 12 个页面，新增 2 个买方图册 Memo 审美备选版。
- HTML 结构检查：三版均为 1 个 H1、6 个 SVG、6 条图表 path、24 个佐证数据 chip、6 个当前分位标注、5 个 L1-L5 展开层；动作含义保留“核心仓 / 战术仓 / 等待资金”三行。
- `impeccable` 禁用项扫描：未发现 `#000` / `#fff`、渐变文字、粗侧边色条、负字距或流式字体缩放。

### 买方图册 Memo demo：改为并列章节导航，完整信息按阅读任务分房间

完成内容：

- 按浏览器批注调整 demo 信息架构：主导航不再把多个候选形态并列在前，而是以“买方图册 Memo”为第一入口，后续并列放置“风险与反证”“冲突与共振”“L1-L5 底稿”“数据与审计”“总览”。
- 新增 `demo_risks.html`：集中展示动作分层、三段时间框架、失效条件、价格反映地图和必须保留的风险。
- 新增 `demo_conflicts.html`：集中展示主要矛盾、typed conflicts、resonance chains、传导路径和未解决问题。
- 新增 `demo_layers.html`：按 L1-L5 展开每层 agent 底稿，包含本层结论、风险旗标、层内冲突、质量自检、跨层钩子和指标读数。
- 新增 `demo_audit.html`：集中展示发布闸门、DataIntegrity、Schema Guard、Run Review、fallback 和证据合同提示。
- 旧候选 demo 仍保留在总览页作为对照，不再抢占主阅读顺序。

验证结果：

- `.venv/bin/python -m py_compile scripts/generate_report_demos.py`：通过。
- `.venv/bin/python scripts/generate_report_demos.py`：成功生成 10 个页面，新增 4 个并列章节页。
- HTML 结构检查：主导航顺序为 `买方图册 Memo -> 风险与反证 -> 冲突与共振 -> L1-L5 底稿 -> 数据与审计 -> 总览`；主报告页保留 6 张图、24 个佐证数据标签、5 个可展开层；底稿页保留 5 个展开层。

### 买方图册 Memo demo：把顺读正文、证据图册和 L1-L5 展开审计合成一版

完成内容：

- 在现有一次性 demo 生成器中新增 `demo_memo_chartbook.html`，作为“买方 memo + 图册式证据 + L1-L5 可展开审计”的合体候选版。
- 新 demo 用买方 memo 组织阅读顺序：主判断、动作含义、优先反证，然后按市场状态、实际利率约束、信用确认/分化、内部结构四段展开。
- 每个关键判断旁嵌入图册证据卡：图表保留简洁视觉，同时补充近1年分位、20日动量/变化、均线距离、MACD柱、阈值距离等轻量佐证数字。
- 保留 L1-L5 agent 价值：正文下方提供 5 个可展开层，包含本层结论、风险旗标和关键指标读数，不把底稿噪音塞入主阅读流。
- 同步给原图册小图增加“当前分位”左侧标注，回应浏览器批注中“只有图不够，需要分位/动量等佐证”的问题。

验证结果：

- `.venv/bin/python -m py_compile scripts/generate_report_demos.py`：通过。
- `.venv/bin/python scripts/generate_report_demos.py`：成功生成 6 个页面，新增 `demo_memo_chartbook.html`。
- HTML 结构检查：合体 demo 有 1 个 H1、6 个 SVG、6 条图表 path、24 个佐证数据 chip、5 个 L1-L5 可展开审计层；图册页也包含“当前分位”标注。
- 内置浏览器自动打开本地 `file://` 页面被 Browser 安全策略拦截；未绕过该限制。当前结果已完成静态结构校验，需人工刷新/打开本地 HTML 做最终视觉确认。

### Native brief 重构前 demo 组：用最后一次 run 数据生成 4 种研报形态候选

完成内容：

- 基于最新 publishable run `output/analysis/vnext/20260617_024610` 的既有 artifacts，新增一次性 demo 生成器 `scripts/generate_report_demos.py`。
- 生成 4 个候选研报形态和总览页：买方 Memo、投委会 Briefing、证据阶梯、图册式报告，输出在 `output/reports/report_demos_20260617_024610/`。
- demo 只重排最后一次 run 的 Final / Bridge / Risk / L1-L5 agent 内容和 chart time series，不重新推理、不引入新数据源。
- 按前序输出体验审计结论，demo 主阅读流避免展开完整指标底稿、Audit Trail、原生 JSON 和内部字段名；底稿感保留为证据 ref / 层级入口。

验证结果：

- `.venv/bin/python -m py_compile scripts/generate_report_demos.py`：通过。
- `.venv/bin/python scripts/generate_report_demos.py`：成功生成 `index.html`、`demo_memo.html`、`demo_briefing.html`、`demo_evidence_ladder.html`、`demo_chartbook.html`。
- HTML 结构检查：5 个页面均有 H1 和导航链接；图册式报告包含 6 个 SVG 图表。
- Chrome 本地预览检查：`index.html` 与 `demo_chartbook.html` 可打开；`scrollWidth == clientWidth == 980`，无横向溢出；图册页 6 个 SVG 均含 path。

### L4 Wind PE 分位窗口修复：10年分位回到主锚，forward PE 仍不可由 Wind 直接升级

完成内容：

- 复查最新 brief `vnext_brief_20260617_0230_20260617_0246.html` 背后的 L4 artifact，确认报告把 Wind 返回的短窗口 PE 分位当作泛称历史分位使用，导致 Wind 与 Trendonify / 蛋卷口径差异被误读。
- 按 Wind MCP 实测：`get_index_fundamentals` 在显式询问“最新市盈率在过去1年2年5年10年中的分位数”时返回 PE 1年 39.20%、2年 41.40%、5年 67.22%、10年 76.55%；`PEHistoricalPercentile` 现在优先使用 10年窗口，并把完整窗口写入 `PEPercentileWindows`。
- 保留 Wind NDX 指数级 PE/PB/PS/风险溢价主锚，同时新增一次专门的 PE 分位窗口查询；报告 UI 标签显示 PE percentile 的窗口，L4 prompt 明确禁止把 1年/2年或窗口不明的分位写成 10年分位。
- 实测 Wind 对 NDX 指数级 forward PE / 一致预期 EPS / FY1 预测净利润有字段识别，但返回值为空；因此当前不能把 forward PE 升级为 Wind 指数级正式主锚，仍只能使用现有成分股总量口径代理并保留 source boundary。

验证结果：

- `.venv/bin/python -m pytest -q tests/test_l4_external_valuation_sources.py tests/test_l4_data_authority.py tests/test_l4_forward_earnings_quality.py`：45 passed，6 warnings。
- `.venv/bin/python -m py_compile src/tools_L4.py src/agent_analysis/vnext_reporter.py`：通过。
- 直接调用 `get_ndx_wind_valuation_snapshot()`：返回 `availability=available`、`PE=35.24`、`PEHistoricalPercentile=76.55`、`PEHistoricalPercentileWindow=10y`、`PEPercentileWindows={1y:39.2,2y:41.4,5y:67.22,10y:76.55}`。

### 最新完整 run 验收：Schema Guard 通过，报告与 Prompt Inspector 清洁

完成内容：

- 连续排查并修复最新完整 run 暴露的问题：L4 代理估值字段缺 fallback 解释、Bridge `supporting_facts` 写成自然语言、Schema Guard 状态未进入 `run_summary`、未完成美国日线被误打成 ERROR、L4 结论过长触发重试、Reviser 空冲突对象触发重试。
- `src/agent_analysis/orchestrator.py` 加固 Bridge / Reviser / Layer 输出清洗：Bridge claim 的 `supporting_facts` 只保留 evidence refs，自然语言说明转入 notes；过长 `local_conclusion` 自动截断；空 `retained_conflicts` 丢弃，半空冲突补齐最低结构。
- `src/main.py` 在 `run_summary.json` 写入 `schema_guard_summary` 和 `publish_quality_status`，避免报告可发布状态与 Run Review / Schema Guard 脱节。
- `src/tools_common.py` 将“美国当天日线尚未完成”的空增量请求从 ERROR 降为 INFO，同时继续保留 `runtime_diagnostics.yfinance.by_failure_type.no_completed_daily_bar` 作为数据边界。
- 用最新完整采集 run 验证数据和报告链路：`output/analysis/vnext/20260617_023048` 跑通、DataIntegrity 96.2%、Wind NDX 成功、Schema Guard passed、native brief / workbench / Prompt Inspector 均生成。
- 用同一份最新数据快照做最终分析+报告验证：`output/analysis/vnext/20260617_024610` 所有 LLM stage attempts=1、errors=[]，Schema Guard passed，Run Review 全部 pass，`publish_quality_status=publishable`。

验证结果：

- `.venv/bin/python -m pytest tests/test_vnext_orchestrator.py tests/test_main_cli.py tests/test_run_review.py tests/test_yfinance_cache_resilience.py tests/test_console_run_all.py`：60 passed，28 warnings。
- `.venv/bin/python -m py_compile src/agent_analysis/orchestrator.py src/main.py src/tools_common.py tests/test_vnext_orchestrator.py tests/test_main_cli.py tests/test_yfinance_cache_resilience.py`：通过。
- 完整 run：`.venv/bin/python src/console_run_all.py --models deepseek-v4-flash,deepseek-v4-pro --workbench-modules price_technical,volatility_credit,rates_valuation,breadth_concentration,liquidity --skip-legacy-report`：生成 `output/analysis/vnext/20260617_023048`，最终 `approval_status=approved_with_reservations`、`publish_quality_status=publishable`。
- 最终快照验证 run：`.venv/bin/python src/console_run_all.py --data-json output/data/data_collected_v9_live.json --models deepseek-v4-flash,deepseek-v4-pro --workbench-modules price_technical,volatility_credit,rates_valuation,breadth_concentration,liquidity --skip-legacy-report`：生成 `output/analysis/vnext/20260617_024610`，所有 stage 一次通过，Run Review 无 fail/observe。
- 仍保留的非阻断日志边界：TGA 早期历史缓存存在百万美元/十亿美元混合，代码已逐点转换修复；未完成美国日线被记录为 INFO 和 `no_completed_daily_bar`，不是数据失败。

### 数据合同与行情源降噪：避免已解释降级和未收盘日线导致频繁 fail

完成内容：

- 调整 `src/data_evidence.py` 的 fallback 缺原因判定：`fallback_reason` 仍是首选字段，但 `degraded_reason`、`unavailable_reason`、`no_data_reason`、payload notes 等有效解释也会被认可。真正没有解释的核心 fallback 仍会 hard block。
- `src/tools_common.py` 为实时日线下载增加美国市场日期夹取：当本机日期已经进入新一天、但纽约市场日线尚未完成时，自动把 Yahoo/Twelve 日线请求的 `end` 限制到最近已完成的美国日线，减少 `Data doesn't exist for startDate` 和 10s/60s 重试。
- 将 `XLY/XLP` 移出 Twelve Data 优先通道；这两个标的在日志中 Twelve Data 返回 400，后续走 Yahoo/缓存路径，避免多一次已知不稳定请求。`QQQ/HYG/QQEW` 保留 Twelve Data 优先，因为日志中这些路径正常。
- 新增测试覆盖：已写明 `degraded_reason` 的核心 fallback 不再被误拦；未完成美国日线请求会被夹取；`XLY` 不再走 Twelve Data 优先路径。

验证结果：

- `.venv/bin/python -m pytest tests/test_data_evidence_contract.py tests/test_yfinance_cache_resilience.py tests/test_l4_forward_earnings_quality.py tests/test_runtime_resilience.py`：38 passed，28 warnings。
- `.venv/bin/python -m py_compile src/data_evidence.py src/tools_common.py tests/test_data_evidence_contract.py tests/test_yfinance_cache_resilience.py`：通过。

### 最新 run failed：补齐 L4 估值代理口径的 fallback_reason

完成内容：

- 复查 `output/logs/control_service/20260617_002637_792.log`，确认本次失败不是 Wind 缺数据，也不是 `resume_from_existing`；Wind NDX 快照已成功返回。
- 真正阻断点是 DataIntegrity 发布闸门：`get_ndx_pe_and_earnings_yield` 和 `get_ndx_forward_earnings_quality` 在成分股模型口径被标记为 degraded 时，带有 fallback 链但 `fallback_reason` 仍为 `none`，触发 `fallback_without_reason` 硬拦截。
- `src/tools_L4.py` 为两项 L4 核心估值/盈利质量代理补齐可审计的 fallback 原因：说明它们是用于收益率、覆盖率、盈利质量和修正趋势的成分股模型/代理上下文；Wind/官方汇总锚点仍独立采集，不被冒充。
- 新增回归测试，模拟成分股来源分歧导致 degraded 的场景，确认这两项不会再因缺 fallback 原因被 DataEvidence 合同硬拦。

验证结果：

- `.venv/bin/python -m pytest tests/test_l4_forward_earnings_quality.py tests/test_data_evidence_contract.py tests/test_l4_external_valuation_sources.py tests/test_vnext_packet_builder.py`：50 passed，6 warnings。
- `.venv/bin/python -m py_compile src/tools_L4.py tests/test_l4_forward_earnings_quality.py`：通过。

## 2026-06-16

### 最新失败日志复查：减少 VXN/VIX 重复拉取并加固 Invesco 请求

完成内容：

- 复查 `20260616_220040_725.log` 中除硬失败和 Wind 解析外的异常：VIX/VXN 重复拉取导致 Yahoo 空结果重试约 79 秒；QQQ Top10 集中度的 Invesco 官方接口返回 406；宏观缓存过期和 yfinance 成分覆盖不足为数据边界/降级问题。
- `src/tools_L1.py` 新增本进程内 VIX/VXN 现值缓存：同一轮 live run 里 `get_vix` / `get_vxn` 已经成功取过时，`get_vxn_vix_ratio` 会复用结果，避免重复触发 Yahoo 重试；回测模式不使用该 live 缓存。
- `src/tools_L3.py` 将 Invesco QQQ holdings 请求头对齐为普通浏览器请求形态，包含浏览器 UA、`Accept: application/json, text/plain, */*`、`Accept-Language`、`Origin` 和官方页面 `Referer`。现场复测 Invesco 仍可能返回 406，说明还有对方接口风控/临时拒绝风险，不能把它当作已完全解决。
- 新增回归测试覆盖 VXN live 缓存和 Invesco 请求头。

验证结果：

- `.venv/bin/python -m pytest -q tests/test_runtime_resilience.py tests/test_l3_top10_concentration.py tests/test_data_layer_integrity_fixes.py::test_qqq_top10_concentration_does_not_use_current_holdings_for_backtest`：10 passed，4 warnings。
- `.venv/bin/python -m py_compile src/tools_L1.py src/tools_L3.py`：通过。

### 控制台任务状态框刷新交互

完成内容：

- 将控制台主界面的任务状态框改为可点击刷新区域：状态框本身带 `role=button`、键盘焦点和提示文案。
- 点击状态框会刷新当前任务状态；没有活动任务时会给出“尚无可刷新的任务”的明确反馈。
- 刷新成功时会在状态文案后追加“已刷新 HH:MM:SS”，并带有轻量按下反馈。

验证结果：

- `.venv/bin/python -m pytest -q tests/test_research_console.py tests/test_open_research_console.py tests/test_control_service.py tests/test_console_run_all.py`：18 passed，4 warnings。
- `.venv/bin/python -m py_compile src/research_console.py`：通过。
- `.venv/bin/python src/open_research_console.py` 重新生成控制台后，浏览器检查确认状态框 `role=button`、`tabindex=0`、鼠标指针为 `pointer`，点击后显示“尚无可刷新的任务”。

### Wind NDX 快照解析修复：识别多段 step 表格和新分位字段

完成内容：

- 修复 `src/tools_L4.py` 的 Wind NDX 估值解析：支持 Wind 返回的多段 `Step` 表格结构，能继续进入内层 `rows` 读取数据。
- 支持 `columns` 为对象列表的格式，优先读取 `columns[].name` 作为真实列名。
- 支持 Wind 新字段名：`最新市盈率在过去一年中的分位数`、`最新市净率在过去一年中的分位数`、`最新市销率在过去一年中的分位数`、`最新风险溢价在过去一年中的分位数`。
- 支持用 `过去一年风险溢价序号` / `过去一年风险溢价最大序号` 还原风险溢价排名。
- 用 2026-06-16 实际采集文件中的 Wind payload 验证，已能解析出 PE 35.2443、PB 10.3391、PS 7.4103、风险溢价 1.1049、PE 分位 39.2、PB 分位 88.4、PS 分位 64.0、风险溢价分位 68.4。

验证结果：

- `.venv/bin/python -m pytest -q tests/test_l4_external_valuation_sources.py tests/test_l4_data_authority.py tests/test_vnext_packet_builder.py tests/test_data_evidence_contract.py`：55 passed，4 warnings。
- `.venv/bin/python -m py_compile src/tools_L4.py`：通过。
- 直接调用 `get_ndx_wind_valuation_snapshot()`：返回 `availability=available`、`source_tier=licensed_provider/Wind`，并解析出 PE 35.24、PB 10.34、PS 7.41、风险溢价 1.1049、风险溢价分位 68.4。

### 最新 run 失败排查：控制台入口补齐 resume 参数合同

完成内容：

- 排查 `/Users/aidianchi/Desktop/ndx_mac/output/logs/control_service/20260616_220040_725.log`，确认数据采集已完成并写出 `output/data/data_collected_v9_live.json`，真正导致任务退出的是 `src/console_run_all.py` 调用 `run_pipeline` 时缺少 `resume_from_existing` 字段。
- 修正 `src/console_run_all.py`：控制台完整流程显式传入 `resume_from_existing=False`。
- 加固 `src/main.py`：`run_pipeline` 对缺失的 `resume_from_existing` 默认按 `False` 处理，避免薄包装入口漏传可选字段时直接崩溃。
- 新增控制台回归测试，锁定 `console_run_all` 会把 resume 默认值传给主流程。

验证结果：

- `.venv/bin/python -m pytest -q tests/test_console_run_all.py tests/test_main_cli.py`：13 passed，4 warnings。
- `.venv/bin/python -m py_compile src/main.py src/console_run_all.py`：通过。

### 研究控制台重做实施：从混合参数面板改为简洁启动器

完成内容：

- 重写 `src/research_console.py`：主界面只保留三种运行模式、末次数据摘要、回测开关、新闻材料开关、单一开始按钮、运行状态，以及最新报告 / workbench / 日志入口。
- 将模型选择、Wind L4 主锚开关、人工覆盖、workbench 模块和开发者命令移入默认折叠的高级设置；主界面不再常驻 Trendonify、workbench 模块多选、人工数据大表、命令黑框和数据源健康表。
- `用已有数据分析` 改为走 `src/console_run_all.py --data-json ...`，因此会继续生成 native brief、workbench 和日志，而不是只跑半截分析。
- `src/control_service.py` 新增 `env_overrides` 白名单，只允许 `NDX_DISABLE_WIND_L4` 为空或 `"1"`；关闭 Wind L4 时通过受控环境覆盖传入子进程，不拼接任意环境变量。
- 更新 `src/open_research_console.py` ready / stale markers，要求新版本 `console_simple_launcher_v1`，并拒绝旧控制台主界面标记。
- 更新控制台、启动脚本和 control service 测试，锁定新启动器合同和 Wind 环境覆盖安全边界。

验证结果：

- `.venv/bin/python -m py_compile src/research_console.py src/control_service.py src/open_research_console.py`：通过。
- `.venv/bin/python -m pytest -q tests/test_research_console.py tests/test_open_research_console.py tests/test_control_service.py tests/test_console_run_all.py`：17 passed，4 warnings。
- `.venv/bin/python src/open_research_console.py` 打开 `http://127.0.0.1:8765` 成功，页面版本为 `console_simple_launcher_v1`。
- Chrome 桌面首屏检查：主界面只显示三种运行模式、回测、新闻、开始按钮和末次数据；命令预览不在首屏；未发现 Trendonify 主入口。
- Chrome 390px 宽度检查：`scrollWidth=390`、`clientWidth=390`，无横向滚动；顶部入口和主按钮完整显示。
- 交互命令检查：完整运行、仅收集数据、用已有数据分析、回测、新闻和关闭 Wind L4 生成的命令 / 环境覆盖符合设计。

### 研究控制台重做计划：从参数面板改成用户启动器

完成内容：

- 新增 `docs/2026-06-16_RESEARCH_CONSOLE_SIMPLIFICATION_PLAN.md`，把控制台重做目标、主界面保留/移除内容、Wind L4 开关、安全环境覆盖、代码改动范围和验收标准写成可在全新对话中直接实施的计划。
- 更新 `NEXT_STEPS.md`，把控制台重做列为 P1 输出体验待办，并指向该计划文档。

验证结果：

- 文档变更，无代码执行路径修改；后续实施时按计划运行控制台测试和 Chrome 桌面/手机宽度检查。

### L4 Wind 主锚接入：NDX 风险溢价、估值分位和旧替代项降权

完成内容：

- 新增 `get_ndx_wind_valuation_snapshot`：通过本地 `wind-mcp-skill` CLI 调用 `index_data.get_index_fundamentals`，获取 Wind NDX 指数级 PE/PB/PS、历史分位和 NDX 专属风险溢价；Wind 返回 0-1 分位会统一转换为 0-100。
- 新增 Wind 解析、缓存和降级边界：每轮 live 只缓存一次；`NDX_DISABLE_WIND_L4=1` 可显式关闭；回测模式跳过当前 Wind 快照并写入边界，避免把运行时数据伪装成历史可见事实。
- L4 采集、工具注册、data evidence、packet builder 和 deep research canon 全部接入新函数；`licensed_provider/Wind` 成为独立来源等级，和 `licensed_manual/Wind` 区分。
- L4 状态判断优先读取 Wind：PE/PB/PS 分位高表示估值压力，Wind 风险溢价分位低表示风险补偿偏薄；风险溢价分位方向不再按 PE 分位误读。
- L4 prompt 与 fallback prompt 更新：Wind NDX 风险溢价是 NDX 专属主锚；Damodaran 保留为美国市场 ERP 背景；WorldPERatio 保留标准差/滚动均值参照；Danjuan/Trendonify/人工输入降为 fallback 或审计材料；简式收益差距降为 Wind 不可用时的诊断/回退。
- Native brief 图表更新：L4 估值尺和 L1-L4 压力图优先展示 Wind NDX 风险溢价；`get_equity_risk_premium` 仍保留为兼容和回退诊断。
- 更新 `DATA_COVERAGE_REVIEW.md`，记录 L4 实时主锚从多源拼接升级为 Wind 主锚 + Damodaran/WorldPERatio/yfinance 分工。

验证结果：

- `.venv/bin/python -m pytest -q tests/test_l4_external_valuation_sources.py tests/test_vnext_packet_builder.py tests/test_deep_research_canon.py tests/test_tools_smoke.py`：48 passed，4 warnings。
- `.venv/bin/python -m pytest -q tests/test_data_evidence_contract.py tests/test_data_availability.py tests/test_l4_data_authority.py tests/test_l4_forward_earnings_quality.py tests/test_vnext_reporter.py tests/test_prompt_guardrails.py tests/test_chart_time_series_artifacts.py tests/test_collector_manual_valuation_checks.py`：75 passed，6 warnings。
- `.venv/bin/python -m py_compile src/tools_L4.py src/core/collector.py src/agent_analysis/packet_builder.py src/agent_analysis/vnext_reporter.py src/agent_analysis/deep_research_canon.py src/data_evidence.py src/tools.py`：通过。
- `.venv/bin/python -m pytest -q`：372 passed，49 warnings。

### 数据证据合约迁移：data_evidence_v1、分级闸门与报告展示

完成内容：

- 新增统一数据证据合约模块 `src/data_evidence.py`：所有 Collector 输出会归一化为 `data_quality.contract_version = data_evidence_v1`，补齐 provider、source、日期、vintage、fallback、license、coverage、methodology、anomalies 等字段框架。
- Collector 接入 normalizer：自动数据和 manual/Wind 输入都走同一证据合约；缺 `source_url`、缺 coverage、缺 first-vintage 不再导致采集失败，而是进入 degraded/audit warn。
- DataIntegrity 增加合约分级：日期越界、latest-only 混入回测、proxy 冒充 official、available 但无有效值、核心 fallback 缺原因会 hard block；普通元数据缺口只记录为 degraded/audit warn，不误拦本来能获取的数据。
- Packet Builder 会过滤 hard-blocked 指标的观测值，不送入 L1-L5 事实层；degraded 指标继续保留，并把质量边界带入 packet meta/context。
- Reporter 数据质量区展示证据合约、provider/source_url、data/as-of/effective/vintage 日期、fallback_reason、license_note、coverage 和 anomalies。
- L4 `_quality_block` 改接共享 helper；manual data 模板补齐 data evidence 字段。

验证结果：

- `.venv/bin/python -m pytest -q tests/test_data_evidence_contract.py tests/test_data_availability.py tests/test_manual_data_template.py tests/test_vnext_packet_builder.py tests/test_vnext_reporter.py::test_enrich_indicator_data_quality_injects_collection_timestamp tests/test_vnext_reporter.py::test_enrich_indicator_data_quality_with_existing_dq`：32 passed，4 warnings。
- `.venv/bin/python -m pytest -q tests/test_core_checker.py tests/test_runtime_resilience.py tests/test_l3_breadth_data.py tests/test_l3_top10_concentration.py tests/test_l4_data_authority.py tests/test_l4_forward_earnings_quality.py tests/test_l4_external_valuation_sources.py tests/test_ta_l5_and_pdr_sources.py tests/test_data_layer_integrity_fixes.py tests/test_chart_time_series_artifacts.py tests/test_vnext_packet_builder.py tests/test_vnext_reporter.py tests/test_data_evidence_contract.py`：125 passed，7 warnings。
- `.venv/bin/python -m pytest -q`：368 passed，49 warnings。
- `git diff --check`：通过。

---

## 2026-06-09

### 数据获取层严审：回测时间锚、L3/L5 口径和情绪越权修补

完成内容：

- 修正长期分位统计窗口：`calculate_long_term_stats` 不再用系统当前日期锚定 5Y/10Y，而是用传入 `as_of_date` 或输入序列最新观测日，并丢弃锚点之后的数据。
- 收紧图表技术序列：OHLCV / 补充序列先按日期排序；MA、布林带、Donchian、ATR、VWAP、CMF 等滚动指标必须满足完整窗口，不再用不满窗口的早期样本冒充有效指标。
- 取消 `GOOGL -> GOOG` 静默替换，避免 Alphabet 两类股混用或双计。
- L3 回测模式下 `get_qqq_top10_concentration` 不再请求当前 Invesco 持仓作为历史证据，改为明确 unavailable 和数据边界。
- 统一 M7 Alpha Vantage fallback 的 ROE / margin 百分比口径：兼容 `0.25`、`25`、`25%`，输出统一为百分点。
- 降权 CNN Fear & Greed：文案去掉“买入信号”，Packet Builder 不允许 FGI 单独把 L2 判为 risk_on / risk_off；risk_on 需要低 VIX + 信用平静，risk_off 需要波动/信用压力或情绪压力被硬信号确认。
- 修正 SOFR 文案为“以美国国债为抵押的隔夜回购融资成本”；Donchian 文案改为技术观察，不再写成独立买卖信号。

验证结果：

- `.venv/bin/python -m pytest -q tests/test_data_layer_integrity_fixes.py tests/test_chart_time_series_artifacts.py tests/test_l3_top10_concentration.py tests/test_vnext_packet_builder.py`：26 passed，4 warnings。
- `.venv/bin/python -m pytest -q tests/test_l3_breadth_data.py tests/test_l4_data_authority.py tests/test_l4_forward_earnings_quality.py tests/test_ta_l5_and_pdr_sources.py tests/test_core_checker.py tests/test_runtime_resilience.py tests/test_data_layer_integrity_fixes.py tests/test_chart_time_series_artifacts.py tests/test_l3_top10_concentration.py tests/test_vnext_packet_builder.py`：87 passed，7 warnings。
- `git diff --check`：通过。

---

## 2026-06-08

### TradingAgents 借鉴后代码审视修补：no-data、object firewall 与 checkpoint 入口

完成内容：

- 收紧 `ObjectiveFirewallSummary.object_clear` 的 raw data 覆盖判断：空 dict、`NO_DATA_AVAILABLE` 哨兵、失败/跳过 payload、只有日期/来源/`data_quality` 的元信息，不再算作有效观察层。
- 修正 `normalize_no_data_payload`：no-data 归一化会同步把顶层和 `data_quality.availability` 置为 no-data 状态，避免保留旧的 `available` 标记。
- 打通 checkpoint 复用入口：CLI 新增 `--resume-from-existing`，主流程会传给 `VNextOrchestrator`；当用户明确指定 `--output-dir` 或 `--run-id` 并开启 resume 时，不再自动改写到 `_02` 新目录。
- 补充回归测试：覆盖 no-data sentinel 不可作为 object coverage、metadata-only payload 不可作为观察值、CLI resume 参数与目录复用行为。

验证结果：

- `python3 -m pytest -q tests/test_objective_firewall.py tests/test_data_availability.py tests/test_main_cli.py tests/test_vnext_orchestrator.py tests/test_core_checker.py`：51 passed，4 warnings。
- `python3 -m pytest -q tests/test_vnext_orchestrator.py tests/test_vnext_packet_builder.py tests/test_core_checker.py tests/test_ta_l5_and_pdr_sources.py tests/test_run_review.py tests/test_objective_firewall.py tests/test_main_cli.py tests/test_data_availability.py`：77 passed，4 warnings。
- `python3 -m pytest -q`：352 passed，4 warnings。
- `python3 -m py_compile src/agent_analysis/orchestrator.py src/data_availability.py src/main.py`：通过。
- `git diff --check`：通过。

---

### TradingAgents 借鉴 Phase 0-5：no-data、L5 确定性快照、schema 边界、checkpoint 与反思库

完成内容：

- 新增共享 no-data 语义模块 `src/data_availability.py`，统一 `NO_DATA_AVAILABLE`、缺数据原因识别和 fallback 失败后的结构化 payload；DataIntegrity / Collector / Packet Builder 不再把空 dict 或空 value 误当成有效观察。
- L5 新增 `get_l5_deterministic_snapshot`：对 QQQ OHLCV 先做确定性快照，冻结价格、均线、RSI、MACD、ATR、ADX、OBV、VWAP/MFI/CMF、Donchian、row_count、effective_date 和 `ohlcv_sha256`；精确技术数字优先来自该底稿。
- L5 prompt、system constraints 和 Deep Research Canon 同步补边界：精确价格/均线/RSI/MACD 不能凭模型记忆补；`NO_DATA_AVAILABLE` 只能作为数据边界，不能围绕空数据编故事。
- Bridge / Schema Guard / Run Review 加强：Bridge 归一化补齐会写入 `normalization_notes`；Schema Guard 增加 `quality_status`；Run Review 会把 schema guard 失败作为 fail，并提示哪些字段来自代码兜底而非模型原生理解。
- Orchestrator 新增轻量 `stage_manifest.json` checkpoint：每个关键 artifact 落盘时记录阶段、路径、哈希、输入包稳定哈希、阶段 payload 稳定哈希、状态和可恢复标记；显式 `resume_from_existing=True` 时，仅复用同一输入包且同一阶段输入 payload 下已完整落盘的 L1-L5 / Bridge / Thesis / Critic / Risk / Reviser / Final 产物。
- Orchestrator 新增 `post_run_reflection_library.json`：只在 Final 之后生成，沉淀 Run Review / Outcome Review 的学习点和下一轮检查项，并明确不得回灌本轮 L1-L5、Bridge、Thesis、Risk、Reviser 或 Final prompt。
- 工具注册、采集清单和测试补齐：`get_l5_deterministic_snapshot` 已进入 L5 collection、tools registry 和指标法典。

验证结果：

- `python3 -m py_compile src/agent_analysis/orchestrator.py src/agent_analysis/run_review.py src/agent_analysis/contracts.py src/data_availability.py src/core/checker.py src/core/collector.py src/agent_analysis/packet_builder.py src/tools_L5.py src/tools.py`：通过。
- `python3 -m pytest -q tests/test_run_review.py tests/test_vnext_orchestrator.py tests/test_core_checker.py tests/test_vnext_packet_builder.py tests/test_ta_l5_and_pdr_sources.py tests/test_tools_smoke.py`：68 passed，4 warnings。
- `python3 -m pytest -q`：345 passed，4 warnings。
- `git diff --check`：通过。

---

### NEXT_STEPS 细致审计与待办瘦身

完成内容：

- 逐条复核 `NEXT_STEPS.md` 当前待办，并对照 `WORK_LOG.md`、`README.md`、`src/main.py`、`src/agent_analysis/run_review.py`、Bridge / Thesis prompt 和 `src/core/collector.py` 的实际状态。
- 将 P0 从“第二轮重构”改为“最新验收与薄点修复”：主要矛盾、五类价格反映、踏空/确认成本和 Run Review 检查已经落地，下一步应通过最新 fresh run 验证表达质量和链路稳定性。
- 移除独立的「yfinance 盈利质量代理实时模式审计」待办：6 月 7-8 日已经完成 L4 多源快照、字段级主源规则、冲突闸门、权限降级和 full test 验证。
- 将「权威证据研究助理」与「历史数据研究助理」合并为 P1 一期待办：统一走问题清单、候选证据包、`research_candidate` / `manual_review_required` 和升级闸门。
- 新增 P1「L3 广度、集中度和历史成分数据补强」：当前更真实的数据薄点已经从 L4 转回 L3。
- 将「采集机 / 快照模式产品化」改为「收尾」：`--collect-only`、`--data-json`、控制台入口和 README 两段式说明已存在，剩余重点是同一快照贯穿报告和审计痕迹。
- 更新后续方向与暂缓边界：Prompt Inspector 已取代正文 Agent IO Audit；L4 yfinance/Yahoo/SEC/东财审计不再作为当前独立 P1。

验证结果：

- 文档审计和修订完成；本次为文档维护，未运行代码测试。

---

### NEXT_STEPS 补充：权威证据研究助理替代泛新闻源

完成内容：

- 更新 `NEXT_STEPS.md` 日期，并新增 P1「权威证据研究助理原型」待办。
- 明确该模块是独立研究助理：L1-L5 先根据正式数据独立分析，遇到“不知道为什么”时提出具体问题，再由研究助理去找 Fed、SEC、Nasdaq、Invesco、公司财报、官方新闻稿等权威来源。
- 明确边界：候选材料默认标记 `research_candidate` / `manual_review_required`，不得直接进入 L1-L5，不得直接成为 `evidence_ref`；只有经过人工确认、规则确认，或沉淀成可重复采集器后，才允许升级为正式数据源。
- 在数据基础和暂缓边界中补充通俗说明：后续不是做更大的新闻摘要器，而是用问题驱动的权威证据研究助理逐步替代泛新闻源。

验证结果：

- 文档修改完成；本次为待办和架构边界记录更新，未运行代码测试。

---

### L4 数据源上位：Yahoo 管预期，SEC 管事实，yfinance 做对照，东财做质检

完成内容：

- 新增 L4 字段级主源规则：EPS estimate / EPS revision 明确由 Yahoo quoteSummary 主导；SEC XBRL 明确为官方已披露财报事实源；yfinance 保留为估值字段主对照和 fallback；东财固定为中文第三方交叉校验源，不直接进入核心证据链。
- 升级组件源冲突闸门：yfinance 与 Yahoo 在单票 trailing PE / forward PE 出现高冲突时，不再硬选 yfinance，而是把该 ticker 的冲突字段剔出核心 component aggregate，并在 `component_conflict_gate` 标记 degraded。
- SEC XBRL 输出补齐事实审计元数据：每个已命中字段带 `filed_date`、`period_end`、`form`、`source_accession`、`xbrl_tag`；未命中字段明确标为 `unavailable`，不填假值。
- L4 输出新增/强化 `primary_source_by_field`、`sec_official_facts`、`component_conflict_gate`；`get_ndx_forward_earnings_quality` 输出 `eps_revision_source=yahoo_quote_summary`，并明确 EPS revision 只能说明盈利预期变化，不能单独证明估值便宜。
- DataIntegrity 可看到组件级高冲突：非阻断但扣减置信度；若后续聚合 PE / Forward PE 与指数级第三方源严重冲突，仍由已有 publish gate 阻断。

验证结果：

- `python3 -m pytest -q tests/test_l4_forward_earnings_quality.py tests/test_l4_data_authority.py tests/test_core_checker.py`：40 passed，4 warnings。
- `python3 -m pytest -q`：344 passed，4 warnings。
- `python3 src/main.py --collect-only --models deepseek-v4-flash,deepseek-v4-pro --skip-report --disable-charts`：通过；L4 三个函数均成功。
- 最新 `output/data/data_collected_v9_live.json`：yfinance 101/101，Yahoo 101/101，SEC 20/20，东财 20/20；PDD `forward_pe` 源冲突 576.58%，该字段已从核心 Forward PE 计算剔除，Forward PE 覆盖为 99/101、99.57% market-cap coverage。
- DataIntegrity 复核：`publish_status=publishable`、`blocked=false`、`confidence_percent=97.7`；PDD 冲突作为 quality issue 披露，不误阻断发布。

---

## 2026-06-07

### L4 多源成分股快照：yfinance / Yahoo / SEC / 东财并跑对账

完成内容：

- 新增 L4 run-local 成分股 fundamentals 快照：`get_ndx_component_fundamentals_snapshot` 并跑 yfinance 与 Yahoo quoteSummary，SEC XBRL 和东财 GMAININDICATOR 做 M7 + NDX 前 20 大权重抽样对账。
- 保持 yfinance 为实时主路径，不盲目替换；Yahoo quoteSummary 作为候选/补位源，逐字段记录 `field_sources`、`source_switches` 和 component-level source disagreements。
- SEC XBRL 新增 filed-date 过滤能力和常用 GAAP 指标别名，用来支撑后续历史可见财报事实；东财当前页面只作为实时交叉校验源。
- `get_ndx_pe_and_earnings_yield`、`get_ndx_forward_earnings_quality`、`get_equity_risk_premium` 共享同一 L4 快照，避免同一轮重复拉 101 只成分股。
- L4 产物新增 `SourceReconciliation`、`source_counts`、`official_checks`、`source_switches` 和 `component_source_disagreement_issues`，让报告和 DataIntegrity 能看到多源对账情况。

验证结果：

- `python3 -m pytest -q tests/test_l4_forward_earnings_quality.py tests/test_l4_data_authority.py tests/test_core_checker.py`：39 passed，4 warnings。
- `python3 -m pytest -q`：343 passed，4 warnings。
- L4 直接 smoke：101/101 yfinance、100/101 Yahoo、SEC 20/20、东财 20/20，PE / Forward PE / Simple Yield Gap 均返回有效值。
- `python3 src/main.py --collect-only --models deepseek-v4-flash,deepseek-v4-pro --skip-report --disable-charts`：通过；最新 `output/data/data_collected_v9_live.json` 中 L4 三个函数均成功，`get_ndx_forward_earnings_quality` 复用快照耗时约 33.6ms。

---

### yfinance component-model 根因审计：PB 与 Forward EPS growth 聚合修正

完成内容：

- 精确复现 PB 异常根因：用同一批 yfinance 成分股数据，旧算法 `sum(weight * component_price_to_book)` 得到 `41.18`；新总量口径 `covered_market_cap / sum(market_cap / component_price_to_book)` 得到 `10.11`，与 DanjuanFunds `10.02` 接近。
- 确认 `41.18` 不是单一 yfinance 字段拉错，而是旧代码把 PB 这种 ratio 做了错误的算术加权聚合。ASML component PB 约 `1453.31`，仅 `1.49%` 权重就在旧公式里贡献约 `21.59` 个 PB 点。
- 审查类似口径后发现 `ForwardEPSGrowthProxyPct` 也存在“平均公司增长率”偏差：旧 component-weighted forward EPS growth 为 `74.63%`；按总 forward earnings / 总 trailing earnings 的指数级代理口径为 `48.15%`。
- 修正 `ForwardEPSGrowthProxyPct` 计算为 `sum(market_cap / forward_pe) / sum(market_cap / trailing_pe) - 1`，并输出 `ForwardEPSGrowthProxyMethod` / `forward_eps_growth_proxy_method`。
- 明确审计结论：`PE`、`ForwardPE`、`PB`、`FCFYield`、`ForwardEPSGrowthProxyPct` 已改为尽量使用总量口径；`WeightedEarningsGrowthPct`、`WeightedRevenueGrowthPct` 和 margin 字段仍是 yfinance component proxy，只能旁证，不能当官方 NDX 指数事实。
- 新增根因审计文档 `docs/2026-06-07_YFINANCE_COMPONENT_MODEL_ROOT_CAUSE_AUDIT.md`，记录复现结果、根因、类似指标审计状态和后续风险。

验证结果：

- `python3 src/main.py --collect-only --models deepseek-v4-flash,deepseek-v4-pro --skip-report --disable-charts`：通过；新 `output/data/data_collected_v9_live.json` 中 `ForwardEPSGrowthProxyPct=48.15`，`ForwardEPSGrowthProxyMethod=sum(market_cap / forward_pe) / sum(market_cap / trailing_pe) - 1`。
- 同次采集显示 L4 三个成分股函数重复拉取同一批 101 只成分股，分别耗时约 135-140 秒；后续应做 run 内 component snapshot 共享，减少不一致和等待时间。
- `python3 -m pytest -q`：341 passed，4 warnings。
- `git diff --check`：通过。

---

## 2026-06-07

### yfinance 成分股模型严审：指标权限、源冲突闸门与最新 run

完成内容：

- 对 L4 yfinance 成分股估值模型做了严审：PE / Forward PE 只有在第三方 PE / Forward PE 交叉校验通过时才有 `core_allowed` 权限；FCF yield、增长、利润率、PB 默认降为 `supporting_only` 或 `proxy_only`，不能单独证明估值便宜/昂贵或安全边际充足/不足。
- 新增 `audit_component_valuation_metrics`：自动比较 component-model PE、Forward PE、PB 与 WorldPERatio / Trendonify / DanjuanFunds 等第三方源；核心 PE/Forward PE 严重冲突会阻断发布，PB 严重冲突会从核心证据剔除并保留原因。
- 修正 `get_equity_risk_premium`：当 FCFYield 不是 `core_allowed` 时，不再优先使用 FCF yield，而改用已通过 PE 交叉校验的 EarningsYield；输出 `yield_authority` 和 `rejected_yield_inputs`。
- 修正 `get_ndx_forward_earnings_quality` 中原本写在 `return` 后的无效权限标记，使 forward EPS、margin、M7 修正等字段明确为 supporting proxy。
- DataIntegrity 新增 `source_disagreement_issues` 汇总：非阻断冲突进入 `quality_issues` 和 notes；核心估值源冲突会写入 `blocking_reasons` 并把 `publish_status` 置为 `blocked`。
- L4 prompt 新增 `MetricAuthority` 硬纪律：`supporting_only` 只能旁证，不能进入核心因果链；`rejected` 必须说明剔除，不得无保留进入读数。
- Native brief 估值指标条同步降权：FCF 显示为 `FCF (proxy)`；PB 在 component-model 仅为 supporting-only 时优先显示第三方 PB，并加脚注说明。

验证结果：

- Fresh 数据 run：`output/analysis/vnext/20260607_152856` 完整完成。该轮 PB 为 `10.11`，DanjuanFunds PB 为 `10.02`，未触发 PB 剔除；DataIntegrity `99.0%`，`publish_status=publishable`。
- 复用同一数据快照、Pro 优先重跑分析：`output/analysis/vnext/20260607_1542_authority_rerun_pro` 完整完成。L4 输出不再把 FCFYield 当核心安全垫，简式收益差距使用 `earnings_yield_minus_10y`；`FCFYield` 进入 `rejected_yield_inputs`。
- 生成最新 brief：`output/reports/vnext_brief_20260607_1528_20260607_1542.html`，估值条显示 `FCF (proxy) 1.40%` 和 `PB (3P) 10.02x`。
- 生成最新 Prompt Inspector：`output/reports/vnext_prompt_inspector_20260607_1542_authority_rerun_pro.html`；11 个 stage 均为 `干净`，Risk 第一次 JSON 失败后第二次通过。
- `python3 -m pytest -q`：340 passed，4 warnings。
- `git diff --check`：通过。

---

## 2026-06-07

### 最新 run 复盘：PB 口径、日期跨度与 Prompt Inspector 误报修正

完成内容：

- 复盘 `20260607_141610` run，确认正文 `PB 41.18x` 来自 yfinance 成分股 `priceToBook` 的市值加权平均，且与 DanjuanFunds 发布 PB `10.02` 明显冲突；旧报告正文虽然在数据质量区保留了异常信息，但仍把异常 PB 当作普通核心指标展示。
- 修正 L4 PB 聚合口径：改为 `covered_market_cap / sum(market_cap / component_price_to_book)`，并把 `PriceToBookMethod` 写入估值产物。
- Native brief 的估值微图新增 PB 冲突防呆：当 component-model PB 与第三方发布 PB 严重背离时，正文指标条显示第三方 PB，并用脚注说明 component 原始值留在 raw data 中。
- 将报告中的“观察日期范围 / Observation Range”改为“输入数据日期跨度 / Input Date Span”，避免误导为所有指标都拥有同一完整 10 年窗口；本次 `2016-07-01` 实际来自 Damodaran ERP 10 年月度窗口，其他指标历史长度并不一致。
- 修正 Prompt Inspector 边界检查误报：空的 `apparent_cross_layer_signals: []` 不再判违规；Trendonify 等 user-trusted 估值 sidecar 的来源说明不再被误判为新闻 sidecar 污染。
- Prompt Inspector 总览新增“输入质量”提示：可标记 L4 prompt 过长、PB 口径冲突等问题，同时保持 L1-L5 真正边界状态独立展示。

验证结果：

- 重新生成 `output/reports/vnext_prompt_inspector_20260607_141610.html`：边界汇总为 `{'干净': 11}`；L4 仅保留 sidecar 来源提示，并标出 `Prompt 过长`、`PB 口径冲突`。
- 重新生成 `output/reports/vnext_brief_20260607_1416.html`：正文估值条显示 `PB (3P) 10.02x`，不再显示异常 `41.18x`；日期字段显示“输入数据日期跨度”。
- `python3 -m py_compile src/tools_L4.py src/agent_analysis/vnext_reporter.py src/agent_analysis/prompt_inspector.py`：通过。
- `python3 -m pytest -q`：334 passed，4 warnings。
- `git diff --check`：通过。

---

## 2026-06-07

### Prompt 污染清理：去除旧立场锚点与 fallback 回流风险

完成内容：

- 清理 active prompts 与 `src/agent_analysis/prompts/prompts/` fallback prompts 中的旧立场锚点、固定动作口号和方向性反面教材，包括 `中性偏谨慎`、`建议等待更好的入场时机`、`能不能涨` 等表达。
- 将可照抄的投资结论示例改成中性字段占位，要求模型按当日证据生成主论点、读者结论、动作条件和复核触发器。
- 扩展 prompt guardrail 测试，递归扫描 active 与 fallback prompts，防止污染短语回流。
- 保留必要硬边界，例如禁止编造历史统计/点位、evidence_refs 约束、Damodaran ERP 与 NDX 估值分位区分等。

验证结果：

- `python3 -m pytest -q tests/test_prompt_guardrails.py`：9 passed。
- `python3 -m pytest -q tests/test_run_review.py tests/test_vnext_orchestrator.py tests/test_vnext_reporter.py`：43 passed，4 warnings。
- `git diff --check`：通过。
- 污染短语静态搜索无命中；必要硬边界静态搜索仍有命中。

---

## 2026-06-07

### Final 结论反模板与赔率一致性闸门

完成内容：

- 移除 Bridge / Thesis / Final prompts 中会诱导模型照抄的“高风险高赔率候选”强示例，改为要求当日证据生成、点名主导矛盾、不得复用示例短语。
- Thesis / Final prompts 新增赔率语言一致性约束：如果 `payoff_assessment` 写赔率不利、风险收益比不利或不支持重仓，`main_thesis` / `final_stance` / `reader_final.one_liner` 不得再写“高赔率”。
- `run_review.py` 新增 Final 赔率语言自相矛盾检查，发现高赔率表达与负面赔率判断并存时输出 `final/fail`。
- 新增 prompt guardrail 和 run_review 测试，防止模板短语回流。

验证结果：

- `python3 -m pytest -q tests/test_prompt_guardrails.py tests/test_run_review.py`：15 passed，4 warnings。
- `python3 -m py_compile src/agent_analysis/run_review.py`：通过。
- `rg -n "高风险高赔率候选|这不是低风险环境，但可能是高风险高赔率候选|核心仓守纪律，战术仓分批" src/agent_analysis/prompts -S`：无命中。

---

## 2026-06-06

### Prompt Inspector 第一版实现

完成内容：

- Orchestrator 新增 `prompt_audit/` 事实源：每个 LLM stage 在调用前保存完整 prompt 原文、structured payload、raw response、normalized parsed response、validated output 和 `meta.json`；retry attempt 分开保存，并在 `llm_stage_diagnostics.json` 中写入 prompt audit 路径。
- 完整 prompt 文件包含 system message 与 user prompt 的实际文本，并计算 `prompt_sha256`，供页面校验“看到的”和保存的 prompt 文件一致。
- 新增独立 `src/agent_analysis/prompt_inspector.py`，生成 `vnext_prompt_inspector_<run_id>.html`，提供中文 pipeline、总览 / 完整原文 / 输入数据 / 规则定位 / 输出结果 / 下游流向 tab、搜索、复制、hash 展示和第一版污染检查。
- Native brief 默认不再展示大块 legacy `Agent IO Audit`，改为小型 `Agent Health` 摘要；旧 Audit 保留在 `--include-legacy-agent-io-audit` 开发开关后。
- Console 一键流程会生成 Prompt Inspector，并把 `prompt_inspector` 路径写回 `run_summary.json`，方便 brief 健康摘要链接到独立检查器。

验证结果：

- `python3 -m py_compile src/agent_analysis/orchestrator.py src/agent_analysis/vnext_reporter.py src/agent_analysis/prompt_inspector.py src/console_run_all.py`：通过。
- `python3 -m pytest -q tests/test_vnext_reporter.py tests/test_vnext_orchestrator.py tests/test_console_run_all.py`：41 passed，4 warnings。

---

## 2026-06-06

### Prompt Inspector 取代正文 Agent IO Audit 决策记录

完成内容：

- 新增 `docs/2026-06-06_PROMPT_INSPECTOR_REPLACES_AGENT_IO_AUDIT.md`，记录用户关于 Agent IO Audit 的核心洞见：现有正文 Audit 展示的是字段摘要和 artifact 路径，不是 agent 真实收到的完整上下文，因此不直观，也不足以判断上下文隔离、必要充分性和下游污染。
- 文档明确建议：默认 brief 删除或折叠大块 legacy `Agent IO Audit`，只保留小型 `Agent Health` 摘要；真正有价值的能力应做成独立 `Prompt Inspector`，保存并展示每个 stage 的完整 prompt、structured payload、Canon、raw response、validated output 和 downstream use。
- 文档给出后续实施路线：正文减负、保存真实 prompt、生成 Prompt Inspector 页面、语义级下游追踪，并列出回测边界、L1-L5 禁止输入、Bridge/Thesis 允许项和验收标准。
- 按用户补充意见修订文档：强调第一优先级是查看 agent 实际收到的完整 prompt 原文，Canon 是完整原文的一部分而不是并列替代品；`完整原文` 展示必须保证和 agent 所见文本一致，并通过 prompt 文件与 hash 校验；页面可美观、可搜索、可折叠，但不得改写原文；面向用户的标题、tab 和状态应中文优先。

验证结果：

- 文档写入与修订完成；本次仅做文档记录和工作日志索引，未修改运行代码。

---

## 2026-06-05

### Damodaran 官方月度 ERP 历史分位补齐

完成内容：

- 基于 Damodaran 官方 `ERPbymonth.xlsx` 月度序列新增 `damodaran_erp_percentile_5y`、`damodaran_erp_percentile_10y` 与 `damodaran_erp_historical_percentiles.windows`，主口径为 `erp_t12m_adjusted_payout`。
- 最新模式使用最新可用官方月度行；回测模式先按目标日裁剪月度序列，再计算 5Y/10Y 分位，防止回测日之后的 ERP 行进入 L1-L5 / Bridge / Thesis / Final 当日分析。
- 样本不足时标记 `insufficient_history`，年度 fallback 标记 `unavailable`，不伪造分位。
- vNext artifact、chart series metadata、brief 和 run_review 展示当前 ERP、5Y/10Y 分位、样本窗口、样本数、数据截止日和边界说明。
- L4 prompt、prompt examples 和 packet builder 明确区分 Damodaran US implied ERP historical percentile 与 NDX PE/PB/Forward PE historical percentile，避免把美国市场 ERP 分位混写成 NDX 估值分位。

验证结果：

- `python3 -m pytest -q tests/test_l4_data_authority.py tests/test_prompt_guardrails.py tests/test_vnext_reporter.py tests/test_run_review.py tests/test_chart_time_series_artifacts.py tests/test_vnext_packet_builder.py`：59 passed，4 warnings。
- `python3 -m pytest -q tests/test_core_checker.py tests/test_vnext_orchestrator.py::test_l4_prompt_summarizes_long_series tests/test_vnext_orchestrator.py::test_historical_percentile_string_is_sanitized tests/test_vnext_orchestrator.py::test_backtest_skipped_indicator_is_not_analysis_required`：13 passed，4 warnings。
- `python3 -m py_compile src/tools_L4.py src/chart_time_series_artifacts.py src/agent_analysis/vnext_reporter.py src/agent_analysis/run_review.py src/agent_analysis/packet_builder.py`：通过。
- `git diff --check`：通过。

## 2026-05-21

### vNext Outcome Review + 五类价格反映地图 + 历史实验目录隔离

完成内容：

- 新增 Outcome Review 合同与实现：`OutcomeWindowPerformance` / `OutcomeReviewReport` 和 `src/agent_analysis/outcome_review.py`，在 Final 之后单独接入 QQQ 后续 `+1w/+1m/+3m/+6m/+12m` 表现，只用于事后复盘，不进入 L1-L5 / Bridge / Thesis / Risk / Reviser / Final prompt。
- Orchestrator 现在会在历史回测 run 末尾写出 `outcome_review_report.json`；非回测语境跳过后验市场表现，避免 live run 误拉未来窗口。
- 扩展 `PriceReflectionAssessment` 合同：新增 `category`、`counterevidence`、`counterevidence_refs`、`action_implication`，并在归一化层保证价格反映地图至少覆盖 `credit`、`rates`、`valuation`、`technical_panic`、`liquidity` 五类。模型若输出过薄，会补成 `unclear + missing_evidence`，不假装分析充分。
- 强化 Bridge / Thesis / Final prompts：要求五类价格反映分别说明价格是否已反映、证据、反证和动作影响；Thesis 示例补全 `reader_conclusion.time_horizon_summary` 和 `reader_conclusion.action_summary` 的对象数组，避免模型第一次输出字符串列表。
- 增强 Thesis / Final 归一化：常见字符串列表会被稳健转换成 `TimeHorizonView` / `PortfolioAction`，保留原语义并留下证据待补足痕迹；不会把缺证据包装成高置信结论。
- `run_review.py` 增加五类价格反映质量检查；native brief 的 Decision 和 Governance 区现在展示扩展价格反映地图、Outcome Review 窗口收益和复盘结论。
- `src/main.py` 新增 `--run-id` / `--output-dir`，并把默认历史 run 目录改成独立实验目录形态，如 `20250409_outcome_test_YYYYMMDD_HHMM`，同名时自动追加后缀，避免覆盖 `output/analysis/vnext/20250409` 基准 run。

验证结果：

- `python3 -m pytest -q`：320 passed，4 warnings。
- `python3 src/main.py --date 2025-04-09 --data-json output/data/data_collected_v9_20250409.json --models deepseek-v4-flash --skip-report --disable-charts --enable-news --run-id 20250409_outcome_test_20260521_codex`：通过，独立目录为 `output/analysis/vnext/20250409_outcome_test_20260521_codex`，未覆盖基准 run。
- Fresh run 最终立场：`高风险高赔率候选，核心仓维持纪律，战术仓分批试探，等待者需确认代价`，`approval_status=approved_with_reservations`。
- Fresh run 产物检查：Bridge / Thesis / Final 的 `price_reflection_map` 均覆盖 `credit`、`rates`、`valuation`、`technical_panic`、`liquidity`；Thesis 覆盖 `same_day_or_days`、`one_to_three_months`、`six_to_twelve_months` 和 `core_position`、`tactical_position`、`waiting_cash`。
- `run_review_report.json` 对 data / bridge / thesis / risk / final / expression 均为 pass，其中 Bridge 五类价格反映检查为 pass。
- `outcome_review_report.json` 后验 QQQ 窗口：`+1w -4.68%`、`+1m +4.71%`、`+3m +19.06%`、`+6m +31.35%`、`+12m +33.13%`，标签为 `strong_follow_through_rally`；复盘结论要求检查原判断是否低估确认成本和踏空成本。
- `python3 src/agent_analysis/vnext_reporter.py --run-dir output/analysis/vnext/20250409_outcome_test_20260521_codex --template brief`：通过，生成 `output/reports/vnext_brief_20260519_2233_20250409_2026.html`，brief 可见五类价格反映地图和 Outcome Review。
- 后验隔离检查：`analysis_packet.json`、`context_brief.json`、`synthesis_packet.json`、`thesis_draft.json`、`risk_boundary_report.json`、`analysis_revised.json`、`final_adjudication.json` 均未出现 `outcome_review`、`post_hoc_outcome`、`return_pct`、`+12m` 后验标记。

剩余边界：

- Outcome Review 当前用 QQQ 后验价格做窗口复盘；它能检查过度谨慎/过度冒进方向，但不会把后验自动写回当日判断。
- 2025-04-09 run 仍沿用既有数据快照，L3 历史成分股下载存在 yfinance 限流诊断；DataIntegrity 未阻断，但 point-in-time universe 仍是长期数据缺口。

### OpenBB vNext 五层覆盖测绘实验

完成内容：

- 切到 `codex/openbb-provider-research` 分支施工，未在 `main` 上继续改动。
- 将 OpenBB 研究依赖写入 `requirements.txt`：`openbb[all]==4.7.1` 与 `openbb-polygon==1.5.1`。
- 更新 `config/configure_openbb.py`：从项目 `.env` 同步 API key 到 legacy OpenBB settings 和 OpenBB Platform `user_settings.json`，只打印脱敏信息。
- 新增非生产脚本 `scripts/openbb_vnext_coverage_probe.py`：按 L1-L5 `function_id` 输出 OpenBB 候选 provider、命令、运行状态、字段、日期、替代评级和回测适配边界。
- 生成本地运行产物：`output/openbb_coverage/openbb_vnext_coverage_matrix.json`、`.csv`、`openbb_vnext_coverage_report.md`。
- 新增研究记录 `docs/2026-05-21_OPENBB_VNEXT_COVERAGE_PROBE.md`，说明 42 行覆盖矩阵的结论和下一步路线。

验证结果：

- `.venv/bin/python -m py_compile scripts/openbb_vnext_coverage_probe.py config/configure_openbb.py`：通过。
- `.venv/bin/python config/configure_openbb.py`：通过；确认已配置 OpenBB 可识别的现有 key，未把完整 key 写入仓库。
- `.venv/bin/python scripts/openbb_vnext_coverage_probe.py --effective-date 2026-05-20 --lookback-days 45`：通过，生成 42 行覆盖矩阵；结果为 38 `ok`、2 `error`、2 `not_probed`。

剩余边界：

- OpenBB 结果仍未接入生产 L1-L5 主证据链；本轮只是覆盖测绘和候选验证。
- QQQ top-10 concentration 的 OpenBB FMP 路径当前返回订阅限制，TMX 路径未找到结果；L3 集中度仍需单独找历史持仓或 point-in-time 权重来源。
- L3 广度的真正难点仍是 point-in-time NDX universe，不是单纯价格数据。
- L4 估值/盈利可以从 OpenBB 获得更多实时交叉校验和 SEC facts 线索，但 first-reported / historical visibility 仍需 vNext 自己审计。

### 历史日期全量试跑：2024-08-05 闸门阻断 + 2025-04-09 对照通过

完成内容：

- 按历史压测样本池先尝试 `2024-08-05` 全量两段式运行：先 collect-only 生成 `output/data/data_collected_v9_20240805.json`，再用该快照进入分析。
- `2024-08-05` collect-only 成功，但暴露真实数据边界：L3 最新成分股历史价格批量下载被 yfinance 限流拖慢，且 `SNDK` 等当前成分股在回测日没有价格史；`runtime_diagnostics.yfinance.total_backoff_seconds=280.0`，4 个 latest-only 指标在回测中被跳过。
- `2024-08-05` 分析阶段被 DataIntegrity 正确阻断：`NDX Valuation (Manual)` 的 `data_quality.data_date=2025-04-09` 晚于回测日 `2024-08-05`，触发 `future_data_after_backtest_date`。这说明回测有效日期闸门在工作，不能强行把报告当作可发布结论。
- 为完成主链试跑，用已知数据边界可通过的 `2025-04-09` 作为对照，使用 `output/data/data_collected_v9_20250409.json` 重新跑完整 vNext 主链。
- `2025-04-09` 对照 run 输出最终判断：`中性偏谨慎。宏观限制与估值安全边际拉锯，核心仓防守，战术仓轻仓试探。`
- Final 的主要矛盾为：NDX 估值相对便宜且 ERP 厚，但高实际利率、信用压力等宏观限制仍主导；价格反映为 `partially_reflected`。
- Risk Sentinel 输出双向风险：包含踏空/确认成本和 false safety risk；Run Review 对 data / bridge / thesis / risk / final / expression 均为 pass。
- 重新生成 native brief 和 workbench：`output/reports/vnext_brief_20260519_2233_20250409_0000.html`、`output/reports/vnext_workbench_20260519_2233_20250409_0000.html`。

验证结果：

- `python3 src/main.py --collect-only --date 2024-08-05 --models deepseek-v4-flash --skip-report --disable-charts --enable-news`：collect-only 通过，写出 `output/data/data_collected_v9_20240805.json`。
- `python3 src/main.py --date 2024-08-05 --data-json output/data/data_collected_v9_20240805.json --models deepseek-v4-flash --skip-report --disable-charts --enable-news`：被 DataIntegrity 阻断，原因是未来日期估值数据进入 2024-08-05 回测。
- `python3 src/main.py --date 2025-04-09 --data-json output/data/data_collected_v9_20250409.json --models deepseek-v4-flash --skip-report --disable-charts --enable-news`：通过，`publish_status=publishable`，`approval_status=approved_with_reservations`。
- `python3 src/agent_analysis/vnext_reporter.py --run-dir output/analysis/vnext/20250409 --template brief`：通过。
- `python3 src/interactive_chart_workbench.py --run-dir output/analysis/vnext/20250409 --modules price_technical,volatility_credit,rates_valuation,breadth_concentration,liquidity`：通过。
- `python3 src/report_visual_regression.py --brief-html output/reports/vnext_brief_20260519_2233_20250409_0000.html --workbench-html output/reports/vnext_workbench_20260519_2233_20250409_0000.html --console-html output/reports/vnext_research_console.html --output-dir output/visual_regression/test_run_20250409_20260521`：passed；desktop/mobile brief/workbench/console layout checks 均无 issues。

剩余边界：

- `2024-08-05` 要成为正式 P0 样本，必须先解决或显式替换晚于回测日的手工估值输入；否则只能作为“DataIntegrity 应阻断”的负样本。
- L3 point-in-time universe 仍是主要数据缺口；当前成分股代理会在历史回测中制造幸存者偏差和无价格史问题。

### vNext 历史压测日期事实调查

完成内容：

- 新增 `docs/2026-05-21_VNEXT_HISTORICAL_TEST_DATES_RESEARCH.md`，作为后续 Mao 思想路线主链、Outcome Review 和历史数据研究助理的日期样本池。
- 基于 `QQQ` 可交易代理、`^NDX` 指数参照和 `^VIX` 波动参照，量化多个候选日期之后约 1 周、1 个月、3 个月、6 个月、12 个月的表现和后续最大下探。
- 将样本分为 P0 最小压测、P1 扩展压测和 P2 长历史/数据覆盖压测，避免只围绕 `2025-04-09` 过拟合。
- 覆盖典型样本与不典型反例：恐慌反转、趋势顶部、下跌后风险未释放、政策流动性转向、局部信用压力与政策兜底、龙头抱团与集中度脆弱、VIX 机制性冲击等。
- 明确边界：本文的后续收益是后验事实，只能用于测试和 Outcome Review，不得泄露进历史回测当日 prompt；事件背景仍需单独证明发布时间和数据日期。

验证结果：

- 使用 Yahoo Finance 历史日线经 `yfinance` 下载，覆盖 1999-03-10 至 2026-05-20。
- 人工复读新增文档，确认其把价格后验事实、事件背景和正式回测证据边界分开。

剩余边界：

- 尚未为这些日期批量运行 collect-only / vNext fresh run。
- 早期样本如 2000、2002、2008、2009 的 L3/L4 point-in-time 数据覆盖可能不足，正式纳入前需要先跑数据边界检查。

## 2026-05-20

### Mao 思想路线主链第二轮第二段：Review 复盘闭环

完成内容：

- 新增 `RunReviewFinding` / `RunReviewReport` 合同，建立运行后复盘 artifact 的稳定结构：把问题归因到 `data`、`bridge`、`thesis`、`risk`、`final`、`expression` 六类。
- 新增 `src/agent_analysis/run_review.py`：可从 run artifacts 生成 `run_review_report.json`，检查 DataIntegrity、回测边界、Bridge 主要矛盾、价格反映地图、Thesis 价格/赔率语义、Risk 双向风险、Final 主要矛盾保留和 reader_final 内部审批话术。
- 接入 `VNextOrchestrator.run()`：以后新 run 会自动保存 `run_review_report.json`，并在返回 artifacts 中包含 `run_review_report`。
- 接入 native brief：Governance 区展示 Run Review 的归因发现；Agent IO Audit 阶段链路新增 Review artifact。
- 为现有 `2025-04-09` run 生成复盘产物：`output/analysis/vnext/20250409/run_review_report.json`。由于该 run 来自本轮字段落地前，Review 正确归因出 Bridge / Thesis / Risk / Final / expression 缺少新主链字段，数据边界与 DataIntegrity 则为通过。
- 使用真实 DeepSeek Flash 在独立目录 `output/analysis/vnext/20250409_mao_fresh` 跑通 fresh LLM 主链；Bridge 原生输出 `principal_contradiction` 与 `price_reflection_map`，Thesis / Final 保留主要矛盾，Risk 输出踏空/确认成本，Review 对 fresh run 的 data / bridge / thesis / risk / final / expression 六类检查均为 pass。
- fresh run 暴露相对路径 output_dir 下 Layer/Bridge 子目录会被重复拼接的问题；已将 `VNextOrchestrator.output_dir` 统一 resolve 为绝对路径，并新增回归测试。
- 增加 `tests/test_run_review.py`，覆盖缺字段归因和主链字段齐备时的通过路径；扩展 orchestrator 测试，确认新 run 会写出 `run_review_report.json`。

验证结果：

- `python3 -m py_compile src/agent_analysis/contracts.py src/agent_analysis/orchestrator.py src/agent_analysis/run_review.py src/agent_analysis/vnext_reporter.py src/main.py`：通过。
- `python3 -m pytest tests/test_run_review.py tests/test_vnext_orchestrator.py tests/test_vnext_reporter.py -q`：34 passed，4 warnings。
- `python3 src/agent_analysis/run_review.py --run-dir output/analysis/vnext/20250409`：通过，写出 `output/analysis/vnext/20250409/run_review_report.json`。
- `python3 src/agent_analysis/vnext_reporter.py --run-dir output/analysis/vnext/20250409 --template brief`：通过，brief 中可见 `Run Review` 区块。
- `python3 src/interactive_chart_workbench.py --run-dir output/analysis/vnext/20250409 --modules price_technical,volatility_credit,rates_valuation,breadth_concentration,liquidity`：通过。
- `python3 src/report_visual_regression.py --brief-html output/reports/vnext_brief_20260519_2233_20250409_0000.html --workbench-html output/reports/vnext_workbench_20260519_2233_20250409_0000.html --console-html output/reports/vnext_research_console.html --output-dir output/visual_regression/mao_review_loop`：passed；desktop/mobile brief/workbench/console layout checks 均无 issues。
- `python3 - <<'PY' ... VNextOrchestrator(... output_dir='output/analysis/vnext/20250409_mao_fresh').run(packet) ... PY`：真实 DeepSeek Flash fresh run 通过；最终 `final_stance=中性偏谨慎：风险未解除但估值低位，核心守纪律，战术分批，等待者接受确认成本。`。
- `python3 src/agent_analysis/vnext_reporter.py --run-dir output/analysis/vnext/20250409_mao_fresh --template brief`：通过。
- `python3 src/report_visual_regression.py --brief-html output/reports/vnext_brief_20260519_2233_20250409_0000.html --workbench-html output/reports/vnext_workbench_20260519_2233_20250409_0000.html --console-html output/reports/vnext_research_console.html --output-dir output/visual_regression/mao_fresh_run`：passed；desktop/mobile brief/workbench/console layout checks 均无 issues。
- `python3 -m pytest tests/test_vnext_orchestrator.py tests/test_run_review.py -q`：22 passed，4 warnings。
- `python3 -m pytest -q`：313 passed，4 warnings。

剩余边界：

- Review 当前是 artifact self-review，能检查本轮产物是否满足主链语义；还不是带后续市场结果的 outcome review。真正“错判后归因到数据/Bridge/Thesis/Risk/Final/表达层并沉淀规则”的市场结果复盘，仍需要后续接入结果窗口或人工输入后再扩展。
- Fresh run 使用既有 `2025-04-09` analysis packet，没有重新采集数据；这是对主链语义的模型验收，不是一次新的数据采集验收。

### Mao 思想路线主链第二轮第一段：Bridge / Thesis / Risk / Final

完成内容：

- 扩展 `src/agent_analysis/contracts.py`：新增 `PrincipalContradiction`、`SecondaryContradiction`、`PriceReflectionAssessment`、`ContradictionTransformationSignal`，并接入 `BridgeMemo`、`SynthesisPacket`、`ThesisDraft`、`GovernanceInputPacket`、`FinalAdjudication`。
- 改造 `src/agent_analysis/orchestrator.py`：Bridge 输出缺少主要矛盾时，会从最高严重度 typed conflict 兜底推导；SynthesisPacket / GovernanceInputPacket 会把主要矛盾、次要矛盾和价格反映地图传给 Thesis、Risk、Reviser、Final。
- 强化 `cross_layer_bridge.md`、`thesis_builder.md`、`risk_sentinel.md`、`reviser.md`、`final_adjudicator.md`：主链必须回答主要矛盾、价格是否反映风险、赔率、行动和失效条件；Risk 必须检查主要矛盾缺失、主要方面误判、价格反映不确定和双向风险；Final 必须把主要矛盾写进读者结论而不是内部审批话术。
- 更新 `vnext_reporter.py`：native brief 的 Decision Surface 新增“主要矛盾”和“价格反映地图”，优先展示 Final 字段，缺失时回退 Thesis 字段。
- 增加测试覆盖：合同 roundtrip、Bridge v3 字段、legacy Bridge 兜底推导、SynthesisPacket 传递、GovernanceInputPacket 传递和 prompt 护栏。

验证结果：

- `python3 -m py_compile src/agent_analysis/contracts.py src/agent_analysis/orchestrator.py src/agent_analysis/vnext_reporter.py`：通过。
- `python3 -m pytest tests/test_contracts.py tests/test_bridge_v2.py tests/test_governance_input.py tests/test_prompt_guardrails.py -q`：36 passed，4 warnings。
- `python3 -m pytest tests/test_vnext_reporter.py tests/test_vnext_orchestrator.py -q`：32 passed，4 warnings。
- `python3 -m pytest -q`：310 passed，4 warnings。
- `python3 src/agent_analysis/vnext_reporter.py --run-dir output/analysis/vnext/20250409 --template brief`：通过，生成 `output/reports/vnext_brief_20260519_2233_20250409_0000.html`。
- `python3 src/interactive_chart_workbench.py --run-dir output/analysis/vnext/20250409 --modules price_technical,volatility_credit,rates_valuation,breadth_concentration,liquidity`：通过，生成 `output/reports/vnext_workbench_20260519_2233_20250409_0000.html`。
- `python3 src/report_visual_regression.py --brief-html output/reports/vnext_brief_20260519_2233_20250409_0000.html --workbench-html output/reports/vnext_workbench_20260519_2233_20250409_0000.html --console-html output/reports/vnext_research_console.html --output-dir output/visual_regression/mao_main_chain_steps_1_4`：passed；desktop/mobile brief/workbench/console layout checks 均无 issues。

剩余边界：

- 本轮完成用户指定的第一至四步：Bridge、Thesis、Risk、Final 主链语义和展示面；尚未新增独立 Review artifact / prompt。当前仓库没有独立 Review 运行时形态，后续应在进入实践复盘闭环时单独落地，避免和 Critic/Reviser 职责混杂。
- 本轮使用现有 `2025-04-09` artifact 验证 reporter 与布局；尚未重新跑完整 LLM fresh run 生成带新字段的 2025-04-09 分析链。

### NEXT_STEPS 收敛到 Mao 思想路线第二轮

完成内容：

- 更新 `NEXT_STEPS.md`：移除已经完成的 `Decision Semantics 架构改革第一轮` 和 `Agent 输入/输出审计视图原型` 当前待办，避免后续 AI 把已完成事项重复施工。
- 新增当前 P0：`Mao 思想路线主链第二轮重构`，把下一阶段主攻对象收敛到 Bridge / Thesis / Risk / Final / Review 这条决策指挥链。
- 明确 Agent IO Audit 最小只读原型已完成；下一阶段先作为 context isolation、字段产生和下游消费的验收仪表盘，暂缓复杂语义评分、字段评分和发布闸门化。

验证结果：

- 人工复读 `NEXT_STEPS.md`，确认当前待办只保留未完成事项，完成事实仍由 `WORK_LOG.md` 承担。

### AGENTS.md 瘦身与协作偏好校准

完成内容：

- 将 `AGENTS.md` 的“不可破坏红线”改为“常驻边界”，保留 L1-L5 隔离、vNext artifacts 主来源、冲突保留、指标不越权、sidecar 不入主证据链、回测有效日期、禁止编造历史数字和 DataIntegrity 发布闸门等项目级约束。
- 删除原“工作取向”任务分类型 checklist，避免仓库级提示词变成僵硬操作手册。
- 保留原“执行纪律”整节，继续要求先判断、最小修改、验证和说明剩余风险。
- 新增“协作偏好”：复杂任务必要时可用多 agent / 多子任务隔离上下文；解释风格要求通俗、准确、到位，减少中英夹杂和黑话，但不降低分析深度。

验证结果：

- 人工复读 `AGENTS.md`，确认其继续保持短、稳定、高信号；易变任务信息仍路由到 `NEXT_STEPS.md` / `WORK_LOG.md` / 复盘与设计文档。

### Decision Semantics 第一轮实现 + Agent IO Audit 最小原型

完成内容：

- 扩展 `src/agent_analysis/contracts.py`：新增 `TimeHorizonView`、`PortfolioAction`、`ReaderFinal`、`QualityGate`；`ThesisDraft` 现在可表达 `state_diagnosis`、`priced_narrative`、`payoff_assessment`、分时间尺度视图、组合动作、确认成本、失效条件和读者结论。
- 扩展 `RiskBoundaryReport` 与 `GovernanceInputPacket`：治理链现在会携带 `opportunity_costs`、`confirmation_costs`、`false_safety_risks`，并把 Decision Thesis 新字段传给 Critic / Risk / Reviser / Final。
- 改写/增强 `thesis_builder.md`、`critic.md`、`risk_sentinel.md`、`reviser.md`、`final_adjudicator.md`：从“单一立场”升级为状态、价格、赔率、时间尺度、动作和失效条件；Critic 增加过度谨慎/错过赔率检查；Final 分离 `quality_gate` 与 `reader_final`。
- 改造 native brief 首屏：优先展示 `reader_final` 和 Decision Surface，不再把 `adjudicator_notes` 当作首屏读者文案；动作层优先展示核心仓/战术仓/等待者的结构化动作。
- 在 `vnext_reporter.py` 实现只读 `Agent IO Audit` 最小原型：加载 `layer_context_briefs/Lx.json` 和 `llm_stage_diagnostics.json`，在审计区展示 L1-L5 输入边界卡、禁止输入检查、输出 evidence refs、下游痕迹和主 pipeline artifact 摘要。
- 增加测试覆盖：contracts 新字段 roundtrip、governance packet 新字段传递、native brief 展示 reader_final 与 Agent IO Audit。

验证结果：

- `python3 -m pytest tests/test_contracts.py tests/test_governance_input.py tests/test_vnext_reporter.py -q`：34 passed，4 warnings。
- `python3 -m pytest tests/test_vnext_orchestrator.py tests/test_prompt_guardrails.py tests/test_objective_firewall.py tests/test_deep_research_canon.py -q`：43 passed，4 warnings。
- `python3 -m pytest -q`：310 passed，4 warnings。
- `python3 src/agent_analysis/vnext_reporter.py --run-dir output/analysis/vnext/20250409 --template brief`：通过，生成 `output/reports/vnext_brief_20260519_2233_20250409_0000.html`。
- 文本检查确认该 brief 包含 `Agent IO Audit`、`layer_context_briefs/L1.json`、L1-L5 `other layer runtime highlights absent` 与 `global apparent_cross_layer_signals absent`。
- `python3 src/report_visual_regression.py --brief-html output/reports/vnext_brief_20260519_2233_20250409_0000.html --workbench-html output/reports/vnext_workbench_20260519_2233_20250409_0000.html --console-html output/reports/vnext_research_console.html --output-dir output/visual_regression/decision_semantics_agent_io_audit`：passed；desktop/mobile brief/workbench/console layout checks 均无 issues。

剩余边界：

- 本轮实现了合同、prompt、治理输入、reader brief 优先展示和只读审计原型；尚未重新跑完整 LLM 分析链生成带新字段的 fresh `2025-04-09` run。
- Agent IO Audit 的下游使用判断仍是第一版轻量追踪，不是复杂语义相似度裁判，也不是发布闸门。

### Agent 输入/输出审计视图研究文档

完成内容：

- 新增 `docs/2026-05-20_AGENT_IO_AUDIT_VIEW_RESEARCH.md`，把 Agent 输入/输出审计视图的目的、好处、产品形态、判断标准和后续实现边界写成面向人类与后续 AI 的 research 文档。
- 明确该视图第一版应优先做只读透明链路，而不是复杂自动审计脚本：先让人看到每个 agent 收到了什么、输出了什么、下游用了什么。
- 定义第一版最小展示：run 总览、pipeline 节点、agent 输入清单、输出摘要、evidence refs、字段质量提示、下游消费状态和 L1-L5 禁止输入检查。
- 明确 L1-L5 context isolation 的可见证明方式：`允许输入 / 实际输入 / 禁止输入检查` 三栏，不依赖模型自述。
- 定义“有价值字段”和“垃圾标签字段”的白话判断标准，并要求字段去向区分 direct / merged / counterevidence / not used。
- 同步 `NEXT_STEPS.md`，把该 research 文档作为 P1 审计视图原型的方向依据。

验证结果：

- 人工复读新增文档，确认它是产品方向与判断标准文档，不要求后续 AI 立即写复杂自动审计规则。
- 人工确认文档没有改变 L1-L5 context isolation、sidecar policy、DataIntegrity 发布闸门等现有架构红线。

剩余边界：

- 本轮只完成 research 文档和待办链接，尚未实现审计页面、字段追踪逻辑或 UI。

### 毛泽东思想与反脆弱性通俗架构总纲

完成内容：

- 新增 `docs/2026-05-20_MAO_THOUGHT_ANTIFRAGILE_FRAMEWORK_PLAIN.md`，作为 `Decision Semantics` 改革的通俗思想总纲。
- 明确以毛泽东思想为主：实事求是、矛盾论、实践论、持久战、集中优势兵力、群众路线、批评与自我批评；塔勒布反脆弱性作为现代风险语言补充，不喧宾夺主。
- 把 2025-04-09 回测问题重新表述为思想路线问题：系统看见风险，但没有抓住“风险是否已被价格反映、赔率是否变厚、等待确认是否有成本”这个主要矛盾。
- 定义目标架构的通俗链路：调查研究 -> 分层侦察 -> 矛盾地图 -> 主要矛盾 -> 价格与赔率 -> 作战方案 -> 纪律检查 -> 读者报告 -> 实践复盘。
- 给后续 AI 写明工作指令：不要新增孤立“黄金坑 agent”；优先改 Thesis / Final / Risk / Review 的决策语义；Final 禁止内部审批话术进入读者报告；回测复盘必须把错误归因写回架构规则。

验证结果：

- 人工复读全文，确认它以通俗语言服务架构改革，不替代已有技术设计报告；与 `NEXT_STEPS.md` 中 P0 `Decision Semantics 架构改革第一轮` 方向一致。

剩余边界：

- 本轮是思想总纲和后续施工指导，尚未修改 prompts、contracts、reporter 或回测评估逻辑。

### Decision Semantics 架构改革方向报告

完成内容：

- 新增 `docs/2026-05-20_DECISION_SEMANTICS_ARCHITECTURE_REFORM.md`，把 2025-04-09 回测暴露出的核心问题收敛成一份可交给后续 AI 执行的方向性设计报告。
- 明确改革不是新增“黄金坑候选”补丁，而是把最终综合层从“证据综合成立场”升级为“证据解释价格、价格决定赔率、赔率约束行动”。
- 报告基于资产定价第一性原理组织：价格由现金流、贴现率和风险补偿共同决定；估值低不等于低风险，但可能意味着未来补偿变厚；价值、动量、流动性和情绪必须在不同维度上共同解释。
- 明确保留 L1-L5 context isolation、DataIntegrity、IndicatorCanon、Bridge typed conflicts 等底层资产；重塑 Thesis / Final 的职责边界。
- 提出目标架构：Evidence State -> Bridge Typed Relationships -> Decision Thesis -> Quality Gate -> Reader Brief。
- 定义 Decision Thesis 应输出状态诊断、价格隐含叙事、赔率判断、分时间尺度视图、核心仓/战术仓/等待者动作、确认成本、失效条件和读者结论。
- 同步 `NEXT_STEPS.md`，新增 P0 `Decision Semantics 架构改革第一轮`，把报告设为后续实现依据。

验证结果：

- 人工复读新增报告，确认它定方向和功能，不写逐函数施工单；后续 AI 可按报告先改 contracts/prompts，再改 native brief。

剩余边界：

- 本轮只完成架构方向报告和待办登记，尚未修改 contracts、prompts、Final 输出或 brief UI。
- 后续实现必须避免为 2025-04-09 过拟合；至少用报告中的多情景样本集压测。

---

## 2026-05-20

### vNext Agent 流水线通俗审查报告

完成内容：

- 新增 `PLAIN_LANGUAGE_AGENT_PIPELINE_REVIEW.md`，用非技术读者能读懂的方式逐段说明 vNext 主链路：数据包、Context Brief、Object Canon、L1-L5、Bridge、SynthesisPacket、Objective Firewall、Thesis、Critic、Risk Sentinel、Schema Guard、GovernanceInputPacket、Reviser、Final、DataIntegrity 和输出层。
- 每个阶段都按“收到什么、怎么分析、输出什么字段、字段价值、垃圾风险、结构判断”展开，重点回应“上游详细分析后下游只收到 fear 这类低价值标签”的担忧。
- 结合最近 `2025-04-09` run 的真实 artifact 观察，记录当前系统并未只传状态标签，而是保留了 `narrative`、`reasoning_process`、`evidence_refs`、`layer_synthesis`、`internal_conflict_analysis` 等高价值字段；同时点名 `normalized_state`、`risk_flags`、重复 `implication`、空 `description`、泛化 `evidence_refs` 等仍需治理的垃圾风险。
- 复核 `ContextBrief` 实际生成逻辑：全局 `context_brief.json` 包含五层 `layer_highlights`，但 L1-L5 使用的是 `layer_context_briefs/Lx.json`，只保留本层 highlights 且清空 `apparent_cross_layer_signals`；报告已补充这一点，避免误判为当前实现越权。
- 在 `NEXT_STEPS.md` 新增 “Agent 输入/输出审计视图原型”，作为低复杂度优先方向：先做只读可视化审计，让用户直观看到每个 agent 的输入、输出、字段价值和下游消费去向，再决定是否做更复杂的自动审计规则。
- 瘦身 `NEXT_STEPS.md`：删除“已完成快照”、长期流水账和验证命令，只保留当前待完成事项、后续方向思考和暂缓边界；已完成事实继续由 `WORK_LOG.md` 承担。

验证结果：

- 人工复核报告结构，确认覆盖 L1、L2、L3、L4、L5、Bridge、Thesis、Critic、Risk、Schema Guard、Reviser、Final 等主 agent / 主阶段。
- 用文本搜索确认报告包含关键字段：`indicator_analyses`、`reasoning_process`、`evidence_refs`、`typed_conflicts`、`resonance_chains`、`transmission_paths`、`must_preserve_risks`、`blocking_issues`。
- 人工复核 `src/agent_analysis/orchestrator.py` 中 `_build_context_brief()`、`_build_layer_context_brief()` 和 `_run_layer_cards()`，确认 L1-L5 payload 使用 layer-local brief。
- 人工复核 `NEXT_STEPS.md`，确认不再包含“已完成快照”章节。

## 2026-05-19

### 2025-04-09 新 run 复盘与 yfinance 回测稳定性窄修

完成内容：

- 按审计剩余项重新生成 `2025-04-09` 数据和 vNext artifacts：`output/analysis/vnext/20250409/analysis_packet.json`、`data_integrity_report.json`、`logic_vnext.json`、`chart_time_series.json`、`news_event_ledger.json`、`news_event_data_links.json`、`news_layer_analysis.json`。
- 修复真实采集暴露的 `get_crowdedness_dashboard(end_date=...)` 异常：yfinance 单 ticker 返回 MultiIndex 时先用 `clean_yfinance_dataframe()` 标准化，再读取 `close`，避免 pandas Series truth-value 报错；回测模式仍不使用当前期权链和当前 short interest。
- 修复回测模式下不必要的当前 yfinance 刷新：VIX、铜/金、XLY/XLP 在有覆盖回测日的本地历史缓存时直接读取历史缓存；只有缓存缺失或明显未覆盖 effective date 时，才按 `end_date` 拉取历史窗口，避免为了历史日触发当前日期的 10s/60s 长退避。
- 真实复盘结果：修复前 `2025-04-09 --collect-only` 中 Crowdedness 失败，铜/金触发 HG=F / GC=F rate-limit retry，yfinance backoff 合计 `140.0s`；修复后同一采集只有 `cache_hit_recent=20`、`total_backoff_seconds=0.0`，且没有 failed / retry。
- 新 `2025-04-09` vNext run 通过 DataIntegrity：`publish_status=publishable`，`future_date_violations={}`，最终 `final_stance=中性偏谨慎`、`approval_status=approved_with_reservations`。
- 生成 native 产物：`output/reports/vnext_brief_20260519_1849_20250409_0000.html` 和 `output/reports/vnext_workbench_20260519_1849_20250409_0000.html`；brief 已展示 DataIntegrity、YF Diagnostics、`backtest_data_boundaries`、`strict_backtest_invariants` 和买方动作层。
- `--enable-news` 完整 run 复盘：`news_event_data_links.json` 保持 sidecar policy，未进入 L1-L5，不成为 `evidence_ref`；本次 2025-04-09 run 的 `links=[]`，没有噪声连接需要调阈值。

验证结果：

- `python3 -m pytest tests/test_l4_data_authority.py::test_crowdedness_dashboard_backtest_does_not_use_current_option_or_info_snapshots tests/test_l4_data_authority.py::test_crowdedness_dashboard_backtest_handles_yfinance_multiindex_skew tests/test_runtime_resilience.py::test_get_vix_backtest_reads_historical_cache_without_current_refresh tests/test_runtime_resilience.py::test_copper_gold_backtest_reads_historical_cache_without_current_refresh -q`：通过。
- `python3 -m py_compile src/tools_L1.py src/tools_L4.py`：通过。
- `python3 src/main.py --collect-only --date 2025-04-09 --enable-news`：通过；yfinance diagnostics 为 `cache_hit_recent=20`，`total_backoff_seconds=0.0`。
- `python3 src/main.py --date 2025-04-09 --data-json output/data/data_collected_v9_20250409.json --models deepseek-v4-flash --skip-report --disable-charts --enable-news`：通过。
- `python3 src/agent_analysis/vnext_reporter.py --run-dir output/analysis/vnext/20250409 --template brief`：通过。
- `python3 src/interactive_chart_workbench.py --run-dir output/analysis/vnext/20250409 --modules price_technical,volatility_credit,rates_valuation,breadth_concentration,liquidity`：通过。
- 递归检查 `analysis_packet.json`、`chart_time_series.json`、`news_event_ledger.json`、`news_event_data_links.json`：排除采集/生成时间戳后，未发现晚于 `2025-04-09` 的业务日期引用。
- `python3 -m pytest -q`：308 passed，4 warnings。

剩余边界：

- 本次真实 run 没有复现 SQLite / 文件句柄异常；runtime diagnostics 已能识别这类失败，后续若在实时或高并发采集中再次出现，应基于具体日志继续收敛 cache 写入和批量下载策略。
- L3 回测仍使用最新成分股作为 proxy，并由 `strict_backtest_invariants.declared_limitations.point_in_time_universe_not_enforced` 明示；这不是完整 point-in-time universe 数据源接入。

### 严格回测 invariant 第一版：强制项与明示限制入包

完成内容：

- Collector 在回测模式写出 `strict_backtest_invariants`：把已工程化强制的 observation date 递归闸门、latest-only 成分股基本面/持仓自动跳过、inactive manual 隔离列入 `hard_enforced`。
- ALFRED first-vintage、财报 first-reported、point-in-time NDX universe 和 LLM 后验知识列入 `declared_limitations`，明确它们不是 `2026-05-15` 这类硬未来数据污染，但必须在发布审计中保留，不能伪装成完整 point-in-time 回测。
- DataIntegrity 把 strict invariant metadata 原样写入报告，并在 notes 中提示这些限制已明示；它们不会单独阻断发布，真正晚于回测日的观察日期仍由 existing blocking gate 阻断。
- AnalysisPacket 的 `meta/context`、`run_summary.json` / collect-only summary 和 native brief 审计区都携带 strict invariant metadata，方便重新生成 `2025-04-09` run 时直接检查。
- 同步 `NEXT_STEPS.md`、`RUN_REVIEW_CHECKLIST.md`、`DATA_COVERAGE_REVIEW.md` 和本次审计文档，把严格回测 invariant 从未完成项移出，留下 L3/yfinance 真实日志复盘和重新生成 2025-04-09 run。

验证结果：

- `python3 -m pytest tests/test_main_collect_only.py tests/test_collector_manual_valuation_checks.py tests/test_core_checker.py tests/test_vnext_packet_builder.py::test_packet_builder_hides_inactive_manual_metric_values_and_carries_backtest_boundaries tests/test_vnext_reporter.py::test_vnext_reporter_generates_native_ui -q`：17 passed，4 warnings。
- `python3 -m py_compile src/core/collector.py src/core/checker.py src/agent_analysis/packet_builder.py src/agent_analysis/vnext_reporter.py src/main.py`：通过。
- `python3 -m pytest -q`：305 passed，4 warnings。

剩余边界：

- 本轮是 invariant 方案和 metadata 闭环，不是 ALFRED / first-reported / point-in-time universe 数据源接入；后者仍需独立数据工程。
- 尚未重新生成新的 `2025-04-09` 完整 run；下一步应使用当前代码生成并复盘 DataIntegrity、analysis packet、native brief 和 workbench。

### audit 剩余项第二轮：yfinance 诊断产品化与买方动作层

完成内容：

- 新增 yfinance 运行诊断：`cached_yf_download()` 和 `get_yf_ticker_info_with_retry()` 记录 provider success、memory/recent cache hit、stale cache fallback、retry scheduled、failed、退避秒数和耗时。
- yfinance 失败类型结构化：区分 `rate_limited`、`empty_response`、`dns_or_network`、`sqlite_cache_error`、`file_descriptor_exhausted`、`provider_unavailable`、`provider_error`，避免只在日志里留下难复盘的文本。
- Collector 每次 run 会重置并收集 `runtime_diagnostics`；单指标结果写入 `collection_duration_ms`、`failure_type`、`failure_stage`，并同步到 `data_quality` 的 availability / anomalies / failure_reason。
- `run_summary.json` 和 collect-only summary 新增 `runtime_diagnostics`、`data_quality_summary`、`failure_breakdown_by_type`、`slowest_indicators`、`degraded_indicators`；DataIntegrity notes 也会汇总 yfinance retry/cache fallback/failed 和 backoff 秒数。
- Native brief 审计区展示 YF Diagnostics；指标 data quality box 展示可用性、采集耗时和失败类型。
- Native brief 新增“买方动作层”：把上游风险边界和失效条件映射到加仓、减仓、等待、观察窗口四个动作桶，并明确不新增未经 evidence refs 支持的点位、概率或历史胜率。

验证结果：

- `python3 -m pytest tests/test_yfinance_cache_resilience.py tests/test_core_checker.py tests/test_vnext_reporter.py -q`：31 passed，4 warnings。
- `python3 -m pytest -q`：304 passed，4 warnings。

剩余边界：

- 本轮把 yfinance/SQLite/文件句柄问题产品化为可审计诊断，但没有通过真实失败日志证明根因已经消除；L3 数据源系统性失败仍需真实 run 复盘和必要的采集策略调整。
- 严格回测 invariant、新闻事件连接器真实 run 复盘、重新生成 2025-04-09 run 仍未完成。

### AGENTS.md 仓库级提示词瘦身

完成内容：

- 按第一性原理重写 `AGENTS.md`：明确它是每次加载的仓库级提示词，只保留稳定、高信号的北极星、红线、文档路由、执行纪律、工作取向和验证原则。
- 删除当前优先级摘要、重要路径长清单、通俗报告模板全文、验证命令大全和 Windows PowerShell 环境问题，避免把易变信息和低频调试信息塞进常驻上下文。
- 将新闻/sidecar 隔离、回测有效日期、DataIntegrity 发布闸门、指标越权和无证据历史概率等高代价错误收敛为不可破坏红线。
- 明确当前任务、架构、复盘、数据边界和完成记录分别路由到 `NEXT_STEPS.md`、`ARCHITECTURE.md`、`RUN_REVIEW_CHECKLIST.md`、`DATA_COVERAGE_REVIEW.md` 和 `WORK_LOG.md`。

验证结果：

- 人工复读 `AGENTS.md`，确认已无 Windows / PowerShell / `8009001d` 环境问题段，也不再维护命令大全。

### 2025-04-09 回测综合审计剩余项第一轮收敛

完成内容：

- L3 缺口识别集中化：AnalysisPacket 现在统一识别 `source_tier=unavailable`、`availability=unavailable`、`data_quality.availability=unavailable/backtest_skipped`、notes 中失败信息，以及嵌套 `value` 全 None 的 payload；这类指标不再计入成功、不进入 `key_metrics`，也不会在 context brief / layer prompt 中被当成 `analysis_required=true`。
- L3 状态不再把证据不足包装成 `neutral`：缺少可用结构证据且没有明确健康/恶化信号时，状态落到 `insufficient_data`，summary 写缺口而不是写 `值={'level': None...}`。
- L5 / QQQ / QQEW 回测日频口径统一：yfinance 日频 `end` 按排他边界处理，请求 `effective_date + 1 day` 后再过滤到 `effective_date`；覆盖 QQQ 技术指标、多尺度均线、ADX 备用路径、QQQ/QQEW、L2/L3 成分股批量价格和 chart adapter 的 QQQ OHLCV。
- Native brief 信息架构第一轮修复：首屏显示发布状态、分析目标日、回测日、观察日期范围、采集时间、生成时间和指标覆盖；`safe/warning/breached` 中文化；token usage 改为阶段数和输入/输出/合计摘要，不再展示原始 dict；必须保留风险只在“风险边界”主展示，首屏/判断/Governance 改成数量摘要。
- console full run 会把 `native_brief`、`workbench` 和 native fallback `report_path` 回写同目录 `run_summary.json`，外部脚本不再只能从 `console_run_summary.json` 找 native 产物。
- 复合指标升格治理：Bridge prompt 明确 CNN Fear & Greed / Crowdedness 等复合指标要先读总分/总状态；Schema Guard 对 high severity typed conflict 增加检查，若只围绕 `L2.get_cnn_fear_greed_index` 子项如 Market Momentum 展开、没有说明总分语义，则判为 composite sub-metric over-promotion。
- L2 schema retry 稳定性：Layer prompt 明确 `indicator_analyses[].evidence_refs` 必须是字符串数组；normalizer 会把模型偶发输出的 dict / dict 列表收敛为标准字符串 ref，减少首轮 `string_type` 失败。

验证结果：

- `python3 -m pytest tests/test_vnext_packet_builder.py tests/test_vnext_orchestrator.py::test_unavailable_nested_none_indicator_is_not_analysis_required tests/test_vnext_orchestrator.py::test_backtest_skipped_indicator_is_not_analysis_required tests/test_ta_l5_and_pdr_sources.py tests/test_l3_breadth_data.py::test_qqq_qqew_ratio_yfinance_request_includes_effective_date tests/test_vnext_reporter.py::test_vnext_reporter_generates_native_ui tests/test_console_run_all.py -q`：26 passed，4 warnings。
- `python3 -m pytest tests/test_vnext_orchestrator.py::test_schema_guard_rejects_cnn_submetric_high_conflict_without_aggregate_semantics -q`：1 passed，4 warnings。
- `python3 -m pytest tests/test_vnext_orchestrator.py::test_layer_payload_normalization_coerces_dict_evidence_refs tests/test_vnext_orchestrator.py::test_layer_payload_normalization_backfills_indicator_evidence_refs -q`：2 passed，4 warnings。

剩余边界：

- `2026-05-19_0409_BACKTEST_SYNTHESIS_AUDIT.md` 仍未完成：L3/yfinance/SQLite/文件句柄运行稳定性专项、报告买方动作层、yfinance 长退避和 cache 异常产品化、first-reported / vintage 严格回测 invariant。

### 2025-04-09 回测综合审计 P0/P1 闸门修复

完成内容：

- 修复 `get_net_liquidity_momentum(end_date=...)`：净流动性主值、组件、4 周动量和历史统计都先裁剪到回测日可见序列，再进入 raw packet / agent prompt。
- 修复 `get_crowdedness_dashboard(end_date=...)`：SKEW 回测只取不晚于回测日的历史行；QQQ 当前期权链 OI 和当前 `Ticker.info` short interest 在回测模式下明确 `backtest_unavailable`，不再伪标为回测日证据。
- 修复 Damodaran monthly series：`monthly_series` 与主 `data_date` 一样按 `target_date` 裁剪，避免 2025-04-09 回测看到 2025-05 至 2026-05 的后续月份。
- 修复 inactive manual 泄漏：`manual_overrides.active=false` 时，AnalysisPacket 和各层 prompt 只保留 inactive 计数/隐藏标记，不暴露 PE、分位等具体人工数值；active=true 时仍按 layer-local 过滤。
- DataIntegrity 从浅层提示器升级为递归闸门：递归扫描 dict/list 中的数据观察日期，解析 notes/reason 里的 `YYYY-MM-DD`，发现晚于回测日的数据即标记 `blocked/unpublishable`，并在主流程中停止 LLM/报告生成，同时写出 `data_integrity_report.json` 和 blocked `run_summary.json`。
- `backtest_data_boundaries` 进入 `analysis_packet.meta/context` 和 native report 审计区；brief 审计面板现在展示回测日期、DataIntegrity 状态、跳过项、原因和 future upgrade。
- Schema Guard 补强 Bridge 可审计性：校验 `supporting_facts`、typed conflict / resonance / transmission path 的 evidence refs 必须是可定位的 `LX.function_id`；校验 transmission path 重复 `path_id`、空 `evidence_refs`、空 `implication`。

验证结果：

- `python3 -m pytest -q`：294 passed，4 warnings。
- 旧污染采集包 `output/data/data_collected_v9_20250409.json` 经新 DataIntegrity 复核为 `blocked=true` / `publish_status=blocked`，阻断原因覆盖 Net Liquidity `2026-05-15`、Crowdedness SKEW / 期权 notes 未来日期、Damodaran `monthly_series` 未来月份。
- `python3 -m pytest -q tests/test_vnext_reporter.py`：13 passed，4 warnings；native audit section 已覆盖回测数据边界展示。

剩余边界：

- 本轮堵住硬未来数据、inactive manual 泄漏和 Bridge ref 死链闸门；尚未完整重做报告首页信息架构、买方动作层、L3 数据源稳定性和 yfinance/SQLite 文件句柄问题。
- 严格 point-in-time 回测仍需后续设计 ALFRED vintage、财报 first-reported、历史成分股 universe 和数据发布时间语义；这不与本轮硬未来泄漏修复混为一谈。

## 2026-05-18

### 回测模式 L4 yfinance 成分股代理宁缺勿错

完成内容：

- 按最新拍板，回测模式承认 LLM 有不可完全消除的后验风险，不额外收紧模型表达空间；工程侧只负责保证进入 agent 上下文的数据不晚于回测日，并把缺失、跳过和降级写清楚。
- 回测模式下，未提供人工/Wind 覆盖时，`get_ndx_pe_and_earnings_yield`、`get_ndx_forward_earnings_quality`、`get_equity_risk_premium` 自动跳过，不再触发 yfinance 成分股基本面批量代理，也不再试图在核心股票大面积缺失后给一个看似精确的置信度。
- `DataCollector.run()` 新增 `backtest_data_boundaries`，集中记录本次回测哪些指标被跳过、为什么跳过、对应的 `effective_date`，以及未来需要接入能证明回测日可见性的历史数据源后再启用。
- 保留人工/Wind 高信任覆盖路径：如果 `manual_data.py` 提供了有效的 NDX 估值数据，回测仍可使用人工数据，不会被自动跳过规则挡掉。
- `NEXT_STEPS.md` 已把 yfinance 审计改为实时模式审计，并记录严格回测后续升级边界：ALFRED first-vintage、财报 first-reported、point-in-time universe 和 LLM 训练后验知识后续单列设计。
- 记录历史数据研究助理方向：联网 AI skill 只能先生成 `research_candidate` / `manual_review_required` 候选证据包，并把每次如何找到历史数据的路径、日期字段、失败原因和验证办法沉淀下来；稳定可重复后再升级为正式采集规则。
- 记录采集机 / 快照模式：数据采集和 DeepSeek 推理解耦，先用 `collect-only` 生成不可变数据快照、图表和新闻 sidecar，再由主机消费同一快照运行分析；同机分流和双机采集都可以，但报告必须能追溯到同一数据包。
- 同步 `ARCHITECTURE.md`、`DATA_COVERAGE_REVIEW.md`、`RUN_REVIEW_CHECKLIST.md`、`README.md` 和 `NEXT_STEPS.md`；补充文档瘦身候选，暂不直接删除旧审计/实验材料。

验证结果：

- `python3 -m pytest -q tests/test_collector_manual_valuation_checks.py tests/test_vnext_orchestrator.py::test_backtest_skipped_indicator_is_not_analysis_required tests/test_core_checker.py::test_data_integrity_penalizes_skips_partial_coverage_and_future_dates`：6 passed，4 warnings。

剩余边界：

- 本轮只改变回测采集策略，不解决 yfinance 在实时模式下的字段可靠性；实时模式仍需要后续审计。
- 当前回测目标仍是“数据日期不超过回测日”，不是“每个数据源都还原当时第一版”。后者需要 ALFRED、披露日财报、历史指数成分和更严格数据血缘。

## 2026-05-17

### 2025-04-09 回测前瞻污染 P0 修复

完成内容：

- 修复 CNN Fear & Greed 回测污染：回测模式下只读取 `fear_and_greed_historical.data` 中不晚于 `effective_date` 的最后一点；如果历史点缺失，明确 unavailable，不再回退使用 live `fear_and_greed` 顶层当前值。
- 修复回测跳过项契约不一致：latest-only 指标在回测模式下标记为 `backtest_skipped_unsupported_function`，packet/orchestrator 不再把它们列为 `analysis_required=true`；L4 forward earnings quality 不会再因“已跳过但仍必填”阻断。
- 修复 LLM 把 `historical_percentile` 写成说明文字导致 Pydantic 崩溃的问题：只接受 0-100 数字或百分数字符串，复杂来源说明转入 `raw_data.historical_percentile_note` 并把分位设为 `null`；L4 prompt 同步硬约束。
- 给 `chart_time_series.json`、默认 QQQ/FRED/yfinance supplemental fetchers、Damodaran rows、新闻底账和新闻-数据连接器加 `effective_date` 守门；回测新闻侧栏和 workbench 不再使用回测日之后的事件或市场行。
- 提升 DataIntegrity 口径：回测跳过不再算成功；覆盖率不足、未来数据日期会压低完整性并写入 notes。
- 加强 yfinance frame cache 写入/读取校验：缺少 Close 或 batch ticker 覆盖不完整的 DataFrame 不再写入/命中持久缓存，避免部分失败 batch 被缓存放大。

验证结果：

- `python3 -m pytest -q tests/test_l2_cnn_fgi_backtest.py tests/test_chart_time_series_artifacts.py tests/test_core_checker.py tests/test_vnext_orchestrator.py::test_backtest_skipped_indicator_is_not_analysis_required tests/test_vnext_orchestrator.py::test_historical_percentile_string_is_sanitized tests/test_news_event_ledger.py tests/test_news_event_data_linker.py`：19 passed，4 warnings。
- `python3 -m pytest -q`：286 passed，4 warnings。
- `python3 -m py_compile src/tools_L2.py src/tools_common.py src/chart_adapter_v6.py src/chart_time_series_artifacts.py src/news_event_ledger.py src/news_event_data_linker.py src/core/checker.py src/core/collector.py src/agent_analysis/orchestrator.py src/agent_analysis/packet_builder.py`：通过。

剩余边界：

- 本轮没有解决 ALFRED first-vintage、财报 first-reported、LLM 训练后验知识和 point-in-time universe 建库审计；这些属于严格回测架构项，需要单独设计。
- yfinance cache 现在拒绝明显不完整 batch，但还没有实现 per-ticker normalized cache；重复拉取和并发 SQLite 问题仍可能影响稳定性。

### Workbench Crosshair、流动性早期单位与新闻层中文分析修复

完成内容：

- 修复价格技术 workbench crosshair 读数长期缺失的根因：主价格图内部 key 是 `price`、副图是 `macd/volume/...`，但右侧读数只识别 `price_technical`。现在主图和所有价格技术副图都显式映射回 `price_technical`，hover 后右侧读数稳定显示 OHLC、均线、VWAP、Bollinger、Donchian、Volume、OBV、MACD、RSI、ATR、MFI、CMF。
- 把 MACD 左上角读数从单点范例推广为通用图内读数：价格主图、所有副图、波动信用/利率估值/广度集中度/流动性模块图都会在左上角显示当前 crosshair 对应的可绘制序列值；模块重绘后也会重新注册 crosshair。
- 修复 2009 年前净流动性假负数：WTREGEN/TGA 本地混合缓存中，2007-05-09 到 2008-10-21 一段小于 `10000` 的 FRED 原始“百万美元”值被误当成“十亿美元”。修复后 2008-10-22 前 `WTREGEN > 1000` 的早期混合缓存点统一除以 `1000`，并把原先 pre-2007 的 `/100` 错误修正为 `/1000`。
- 新增 `news_layer_analysis.json` 独立 sidecar：对官方事件生成中文概要、可能对股市的影响、压力通道和新闻层总分析；仍明确不进入 L1-L5，不成为 `evidence_ref`，只作为背景/催化剂/复核线索。
- Native brief 新闻区升级为“新闻中文概要、股市影响与市场连接观察”，顶部展示新闻层总分析，逐条事件展示中文概要和可能影响，原有附近市场序列观察继续作为可展开审计材料。
- 重新生成最新 run 的 `chart_time_series.json`、`news_layer_analysis.json`、`output/reports/vnext_workbench_20260517_1852.html` 和 `output/reports/vnext_brief_20260517_1852.html`。

验证结果：

- `python3 -m pytest -q tests/test_interactive_chart_workbench.py tests/test_tools_calculation.py tests/test_news_layer_analyzer.py tests/test_news_event_data_linker.py tests/test_vnext_reporter.py`：68 passed，4 warnings。
- `python3 -m pytest -q`：278 passed，4 warnings。
- 最新 run 数据复核：`NET_LIQUIDITY` 2009 年前最小值为 `706.10`，不再出现假负数；`2007-05-09` TGA 为 `4.914`、净流动性为 `864.606`；`2008-01-02` TGA 为 `8.693`、净流动性为 `911.994`。
- 浏览器 hover 验证：价格技术 readout 包含 `MA20` / `VWAP20` 且不再显示“该模块暂无”；波动信用 readout 包含 `VIX` 且不再显示“该模块暂无”；页面内共有 10 个 `.chart-inline-legend`。
- `python3 src/report_visual_regression.py --brief-html output/reports/vnext_brief_20260517_1852.html --workbench-html output/reports/vnext_workbench_20260517_1852.html --console-html output/reports/vnext_research_console.html --output-dir output/visual_regression/workbench_news_liquidity_fix`：passed。

剩余边界：

- 新闻层当前为规则化中文解读，不是 LLM 深度新闻分析；它能给出保守影响通道和总分析，但不会也不应声称因果证明。
- 油价尚未进入 `chart_time_series` / 新闻连接器，因此新闻层只能明确提示“无法自动判断油价高企通道”；如要分析该通道，需要后续接入 WTI/Brent。

### Workbench MACD 图内图例与读数补强

完成内容：

- MACD 副图左上角新增图内图例：蓝色 `DIF`、红色 `DEA`、灰色 `Hist`，并直接显示当前同步时间点的数值。
- 图例会跟随十字光标同步更新；没有悬停时显示最新时间点读数。
- 重新生成当前 `output/reports/vnext_workbench_20260517_1852.html`，让浏览器里正在看的 workbench 也能刷新看到新版标注。

验证结果：

- `python3 -m pytest -q tests/test_interactive_chart_workbench.py`：6 passed，4 warnings。
- `python3 -m pytest -q`：275 passed，4 warnings。
- `python3 src/report_visual_regression.py --brief-html output/reports/vnext_brief_20260517_1852.html --workbench-html output/reports/vnext_workbench_20260517_1852.html --console-html output/reports/vnext_research_console.html --output-dir output/visual_regression/macd_legend_fix`：passed。
- `http://127.0.0.1:8765/artifact?...vnext_workbench_20260517_1852.html` 已确认包含 `data-macd-legend`、`DIF`、`DEA`、`Hist`。

### NDX Agent 启动可靠性与研究控制台 demo 重排

完成内容：

- `start.command` / NDX Agent 图标现在每次都会重启本地 control service，而不是复用 8765 上“看起来可用”的旧进程；打开地址附带 `opened_at` 时间戳，避免浏览器缓存旧控制台。
- control service 对 HTML / JSON / artifact 响应补充 `Cache-Control: no-store` 和 `Pragma: no-cache`，保证控制台、最新 brief 和 workbench 链接尽量读取当前文件。
- 研究控制台 demo 按普通用户默认路径重排：首屏优先显示“运行完整报告”、workbench 模块、运行状态、命令预览和最新 brief/workbench/run/log/news 产物；对象日期、模型流程、人工数据和 sidecar 校准保留在后续工作区。
- UI 从“所有功能平铺”改为“先运行与结果，再配置和校准”的操作顺序；移动端自然折成单列，不隐藏原有输入、按钮、开关和 JSON 预览。
- 新增测试覆盖：即使旧 8765 服务已经能返回控制台，启动器也会停止并重新启动，防止点击应用图标继续打开旧页面。

验证结果：

- 真实执行 `./start.command`：打开 `http://127.0.0.1:8765/?opened_at=<timestamp>`；页面返回 `console_logs_entry_v4`、`运行与结果`、`使用人工数据`、`news_event_data_links.json`，且没有旧 `data-manual-field="confidence"`。
- 服务响应头确认 `Cache-Control: no-store, max-age=0`。
- `python3 -m pytest -q`：275 passed，4 warnings。
- `python3 src/report_visual_regression.py --brief-html output/reports/vnext_brief_20260512_2152_20260517_0016.html --workbench-html output/reports/vnext_workbench_20260512_2152_20260517_0016.html --console-html output/reports/vnext_research_console.html --output-dir output/visual_regression/console_interaction_demo`：passed，console/brief/workbench 桌面和移动布局检查均无 issues。

### 控制台启动器旧服务识别与新闻产物入口修复

完成内容：

- 将控制台版本标记升级到 `console_logs_entry_v4`，并把旧人工数据“置信度”表单加入 stale service 判定；`start.command` / 应用图标再次打开时会清理 8765 上的旧服务后重启新版控制台。
- 控制台新闻区从“官方新闻底账”改成“官方事件底账与市场连接观察”，明确完整 vNext 勾选新闻会同时生成 `news_event_ledger.json` 和 `news_event_data_links.json`。
- 控制台新增“最新新闻产物”列表，展示 run 目录里的事件底账和市场连接观察；完整运行完成后的状态链接也会列出事件底账和市场连接观察。
- `/latest-product` API 补充新闻产物 URL，方便前端在运行完成后直接打开相关 JSON。

验证结果：

- 真实执行 `./start.command`：旧 8765 进程被替换，新页面返回 `console_logs_entry_v4`，有“使用人工数据”和“官方事件底账与市场连接观察”，没有 `data-manual-field="confidence"` / “置信度”。
- `python3 -m pytest -q`：274 passed，4 warnings。
- `python3 src/report_visual_regression.py --brief-html output/reports/vnext_brief_20260512_2152_20260517_0016.html --workbench-html output/reports/vnext_workbench_20260512_2152_20260517_0016.html --console-html output/reports/vnext_research_console.html --output-dir output/visual_regression/console_launcher_fix`：passed，console/brief/workbench 桌面和移动布局检查均无 issues。

### Twelve Data 优先与 yfinance 入口收口

完成内容：

- 删除旧 `tools_akshare.py` 后，同步移除 `tools_L4.py` 中 QQQ Put/Call 的 AKShare fallback 残留，并从 `requirements.txt` 移除 `akshare` 依赖，避免继续引用错误备用源。
- `cached_yf_download` 新增 Twelve Data 优先路径：当前只覆盖 `QQQ/HYG/QQEW/XLY/XLP` 的日线 OHLCV，兼容 `.env` 中 `TWELVE_DATA_API_KEY` 与 `twelve_data_api_key`；不把 VIX/VXN、期货、复权序列误接到 Twelve Data。
- `cached_yf_download` 在联网前先读取 12 小时内的持久缓存，降低同日重复运行对 Yahoo 的请求压力；失败时仍保留 7 天 stale cache 兜底。
- `cached_yf_download` 不再把 empty DataFrame 写入同次运行的内存缓存，避免一次限流后把空结果固定住。
- `tools_L1.py` 中 XLY/XLP、HG/GC、CL、GC/CL 的裸 `yf.download` 收口到 `cached_yf_download`；`chart_generator.py` 和 `data_cache.py` 的直接下载入口也收口到共享入口。

验证结果：

- `python3 -m pytest -q tests/test_yfinance_cache_resilience.py`：8 passed。新增覆盖 Twelve Data 优先路径、短时持久缓存优先路径和 empty frame 不写入内存缓存。

剩余边界：

- Twelve Data basic 当前限制为 8 credits/min、800/day，因此只作为关键 ETF 日线优先源，不扩大到成分股全量。
- `^VIX/^VXN` 仍无 Twelve Data / AkShare 免费稳定替代，暂保留 yfinance 与缓存退避。
- yfinance `.Ticker` 基本面和期权链仍无法用 Twelve Data 直接替代，后续需要单独评估 Finnhub / Twelve Fundamentals / 付费源。

### yfinance 限流退避修复（cached_yf_download empty df 路径）

分支：`claude/20260517-yfinance-rate-limit-resilience`

根因（systematic-debugging Phase 1-2 调查结论）：

- 5/13、5/15、5/16、5/17 连续四次 run 都在启动 8 秒内首请求即 `YFRateLimitError`，但相同代码在 Yahoo 冷却后能正常拉数据（5/17 12:55 复现单 ticker 与 5 ticker burst 均成功）；问题不是项目 burst 模式，而是 Yahoo 对该 IP 的周期性限流策略。
- 放大因素：`cached_yf_download` 在 yfinance 1.3+ 返回 empty df 时直接放弃（**不进入重试**，因为 yfinance 内部 catch 了 `YFRateLimitError`），仅依赖外层 `_fetch_yf_history` 的 2 秒固定间隔重试。2 秒间隔正好落在 Yahoo cooldown 窗口内，反复撞墙。

最小修复内容：

- **`cached_yf_download` empty df 路径合并到 exception 退避路径**：empty df 视同 silent rate-limit，与 exception 共用同一退避循环；优先返回 stale frame cache，否则进入分级退避重试。
- **退避周期从 (2s, 6s) 调到 (10s, 60s)**：让 Yahoo 限流窗口有机会自然恢复。原值在 5/17 真实日志中复现无效，所有 retry 全部 429。
- **`_fetch_yf_history` 不再对 empty df 重复外层 3 次重试**：`cached_yf_download` 已经完成 10s/60s 内部退避，外层继续 2 秒循环只会在无全局缓存时把长退避重复跑 3 轮。
- 调整范围仍收敛在 yfinance 共享入口，不动 `tools_L1.py`、`chart_generator.py`、`data_cache.py` 等绕过 cached_yf_download 的直调点。

验证结果：

- 新增 `test_cached_yf_download_retries_with_long_backoff_when_empty_and_no_stale` 失败测试（empty df + no stale 必须按 10s/60s 退避重试），修复前 red、修复后 green。
- 新增 `test_fetch_yf_history_does_not_repeat_inner_yfinance_backoff`，防止 `_fetch_yf_history` 把内层长退避重复跑 3 轮。
- `python3 -m pytest -q tests/test_yfinance_cache_resilience.py`：5 passed（含 2 个原有 stale-fallback 行为兼容性测试）。
- `python3 -m pytest -q`：270 passed（修复前 268，本次新增 2）。

剩余风险与未完成：

- `tools_L1.py:787/788/897/898/1077/1174/1175`、`chart_generator.py:1836`、`data_cache.py:187`、`tools_L4.py:1808` 仍是裸 `yf.download/yf.Ticker` 直调，不享受这次修复。本次按最小修复原则不动它们；如果 5/18 以后 run 还是首请求即 429 且数据缺失，需要继续把这些入口收口到 `cached_yf_download`。
- yfinance 抛 429 时是 silent return empty，没有专门的"识别为 rate-limit"通道。这次把所有 empty 视同 rate-limit 处理；如果未来出现"ticker 真实不存在"等正常 empty 情况，会被多 retry 一次（成本：单次 70s 退避）。
- Yahoo 若对此 IP 长期严限（>1 小时），本次修复也无法救场，仍需考虑替代源（FRED 部分指标可替代；VIX/VXN/HYG 暂无稳定免费源）。

### 20260517 run 数据完整性审计修复

完成内容：

- **控制台完整运行不再误用旧数据 JSON**：`完整 vNext` 默认重新采集；只有选择“已有数据分析”时才追加 `--data-json`。控制台会解析最新 data JSON 的数据日期和修改时间，并在已有数据分析模式提示“以 JSON 为准，不会重新采集”。
- **人工数据 UI 去掉误导性置信度下拉**：改为真实的“使用人工数据”开关，和 collector/packet builder 的 `active + meaningful value` 逻辑一致。仅有来源、日期或 confidence 元数据不会触发人工覆盖。
- **补齐关键人工估值入口**：控制台表单、回填、保存和校验补齐 Forward PE、Earnings Yield、Forward Earnings Yield、FCF Yield、PCF、Forward PE 分位和 FCF Yield 分位，减少只能手写高级 JSON 的缺口。
- **yfinance 帧缓存增加时效边界**：持久化 pickle frame cache 默认 7 天 TTL；过期缓存不再作为限流 fallback 使用。`cached_yf_download()` 增加短退避重试；L1 的 yfinance 序列读取改走统一缓存路径。
- **ADX 增加内部公式 fallback**：当 QQQ OHLCV 可用但 `ta` / `pandas_ta` 不可用时，L5 仍能用内部 Wilder smoothing 公式产出 ADX、+DI 和 -DI，避免把库缺失误报成趋势强度缺失。
- **Workbench 缓存回退提示增强**：当 QQQ 价格来自旧 run fallback 时，顶部 warning 显示 fallback run、缓存最新日期和当前 run 数据日期，避免误读为本次实时采集。
- **净流动性早期 TGA 异常修复**：对 2007-05-02 前 WTREGEN/TGA 明显异常的大值做窄规则修正，并记录 warning，避免 2003-2008 的历史口径异常污染 `NET_LIQUIDITY` 图表和历史统计。

验证结果：

- `python3 -m pytest -q tests/test_ta_l5_and_pdr_sources.py tests/test_research_console.py tests/test_yfinance_cache_resilience.py tests/test_manual_data_template.py tests/test_collector_manual_valuation_checks.py tests/test_tools_calculation.py tests/test_interactive_chart_workbench.py`：67 passed，4 warnings。
- `python3 -m pytest -q`：268 passed，4 warnings。

剩余边界：

- ADX 仍取决于 QQQ OHLCV 是否能从 live 或未过期缓存拿到；本轮修复提高公式层韧性，但没有新增第三方 OHLCV 主源。
- DeepSeek L3 首次 JSON 解析失败已有重试机制，本轮未改变 LLM 输出治理。
- Workbench 10Y 默认源码和测试已确认生效；用户若仍看到 5Y，大概率是旧 HTML 或浏览器缓存。

### AGENTS 执行准则内化

完成内容：

- 将 `karpathy-guidelines` 的核心纪律内化到 `AGENTS.md`：先暴露假设和取舍，再做最小必要修改，保持外科手术式改动，并以可验证成功标准闭环。
- 收紧 `AGENTS.md` 推荐工作顺序：先确认成功标准和不可破坏原则，再按 L1-L5、Bridge、Thesis/Governance、数据层、UI 等改动范围选择验证方式。

验证结果：

- 文档检查：确认没有引入外部 skill frontmatter 或整段照搬内容，规则以仓库级 agent 行为准则形式存在。

### L4 估值权威、新闻连接器、10 年 workbench 与 yfinance 韧性演进

提交：`b4d1551 Evolve valuation news and workbench resilience`

完成内容：

- **L4 外部估值源新增 DanjuanFunds/蛋卷基金**：接入 `https://danjuanfunds.com/djapi/index_eva/detail/NDX`，使用浏览器 UA 与 Referer 读取 NDX PE/PB/PE percentile/PB percentile/ROE/PEG/eva_type/date/begin_at/updated_at。蛋卷进入 `ThirdPartyChecks`，作为第三方估值校验源，不替代 Manual/Wind，也不覆盖可信 Trendonify。
- **估值发言权重新排序**：L4 prompt 和 packet builder 明确估值分位权威顺序为 Manual/Wind > trusted Trendonify > DanjuanFunds/蛋卷基金 > WorldPERatio std-dev context；yfinance 成分股 PE/PB/Forward PE 降级为 component-model proxy / sanity check，不再作为估值 regime 主锚。
- **yfinance 韧性增强**：`cached_yf_download()` 增加持久化缓存和失败时 stale cache fallback；`get_yf_ticker_info_with_retry()` 为成分股 `.info` 增加 24h 缓存 fallback；QQQ 图表数据改走统一缓存下载路径。目标是减少限流导致的空图、空 L5 或 L4 成分股模型失败。
- **Workbench 历史窗口改为 10 年起步**：`DEFAULT_CHART_LOOKBACK_DAYS` 从 1825 调到 3650；workbench 默认 `updateRange(3650)`，按钮改为 10Y / 15Y / ALL。5 年不再是默认研究窗口。
- **新闻事件-数据连接器落地**：新增 `src/news_event_data_linker.py`，在 `--enable-news` 且写出 `chart_time_series.json` 后生成 `news_event_data_links.json`。连接器只输出 temporal association / co-movement observation / needs_bridge_review，不写因果证明，不进入 L1-L5 runtime context，不成为 `evidence_ref`。
- **Native brief 新闻栏升级**：新闻栏从单纯“官方事件底账”扩展为“官方事件底账与市场连接观察”，展示事件日前后 QQQ、VIX/VXN、10Y、real yield、HY OAS、HYG、Damodaran ERP 等可用序列的轻量观察，并明确这些观察不是因果证明。
- **旧版 HTML 日常入口软删除**：控制台隐藏旧版 HTML/charts 勾选入口，默认只生成 vNext artifacts、native brief 和 workbench；兼容旧报告仅保留给开发命令显式启用。
- **控制台 stale service 修复**：`open_research_console.py` 增加控制台版本标记 `console_logs_entry_v3`，能识别旧的 visual regression / legacy HTML 页面并清理 8765 上所有旧监听进程后重启服务，避免浏览器继续看到旧控制台。

验证结果：

- `python3 -m pytest -q`：263 passed，4 warnings。
- `python3 -m py_compile src/tools_L4.py src/agent_analysis/packet_builder.py src/news_event_data_linker.py src/main.py src/agent_analysis/vnext_reporter.py src/tools_common.py src/chart_adapter_v6.py src/interactive_chart_workbench.py src/research_console.py src/open_research_console.py`：通过。
- 真实蛋卷接口验证：NDX PE `36.51`，PE 分位 `87.0`，PB `10.44`，PB 分位 `99.68`，ROE `0.2859`，PEG `1.8119`，`eva_type=high`，数据日 `2026-05-15`，样本起点 `2016-01-26`。
- 用 `output/analysis/vnext/20260515_113650` 生成 `news_event_data_links.json`，共 25 条事件连接；重新生成 `output/reports/vnext_brief_20260515_113650_newslinks.html`，可检索“官方事件底账与市场连接观察”“附近市场序列观察”“不是因果证明，也不是 evidence_ref”。
- `http://127.0.0.1:8765/` 已确认返回 `console_logs_entry_v3` 控制台，显示“查看日志 / 最新日志”，旧版 HTML 勾选入口消失。

剩余观察：

- yfinance 在估值 regime 中已降权，但 forward earnings quality、EPS revision、利润率/增长代理仍依赖 yfinance；下一步需要专门审计字段来源、公式、覆盖率和 stale cache 标注。
- 新闻连接器目前只作为 sidecar 和 native brief 展示，不进入 L1-L5，也不替代 Bridge；后续可评估是否把压缩后的 `news_event_data_links` 作为 Bridge 后段的只读背景索引，但仍必须禁止其成为数值证据。

## 2026-05-16

### Claude 20260513 审计分支复核、补强与 main 合并准备

完成内容：

- 深入复核 `PROJECT_AUDIT_20260513.md` 与 `claude/20260513-indicator-timestamps` 相对 `main` 的改动，确认主线修复方向合理：治理阶段 `generated_at` 强制由代码覆盖、L4 长序列进入 prompt 前摘要化、反编造约束提升到 system message、DataIntegrity 扩展、workbench 数据时效性警告、指标时间戳与 U7-U10 简化修复均符合 vNext 当前架构目标。
- 补强 objective firewall：`object_clear` 不再只看 `raw_data` 是否存在 L1-L5 key，而是至少 3 层必须包含可用指标 payload；空层容器不再被误判为投资对象清晰。
- 补强 Kimi HTTP fallback：system message 现在会实际调用 `_load_system_constraints()`，并兼容 `get_extra_headers("kimi")` 返回 `None` 的情况，避免 fallback 路径绕过反编造约束。
- 新增/更新回归测试：覆盖空层容器不能通过 `object_clear`，以及 Kimi HTTP 调用必须携带 system constraints。

验证结果：

- `.venv/bin/python -m pytest -q tests/test_vnext_llm_engine.py tests/test_objective_firewall.py`：15 passed，4 warnings。
- `.venv/bin/python -m pytest -q`：253 passed，22 warnings。

## 2026-05-12

### L4 外部估值源稳定收口：Damodaran、WorldPERatio、Trendonify sidecar

完成内容：

- **研究控制台入口微调**：控制台主流程选择不再把“视觉回归”作为用户入口，改为“查看日志”；产物区从 visual regression summary 改成 `output/logs/control_service` 最新日志/状态文件。视觉回归脚本仍保留给开发验 UI，但不占用日常复跑排障入口。
- **Damodaran 根因确认并收口**：官网 `ERPbymonth.xlsx` 可下载，真实抓取约 46KB；不稳定主要来自坏缓存、manual 覆盖和 run 是否 live。当前 `get_damodaran_us_implied_erp("2026-05-11")` 优先使用 `monthly_excel`，`source_file=ERPbymonth.xlsx`，最新 `data_date=2026-05-01`，`monthly_series` 为 120 条。
- **WorldPERatio parser 修复**：适配当前页面的 Last 1Y/5Y/10Y/20Y 表格，结构化 `average_pe`、`std_dev`、`range_low/range_high`、`deviation_vs_mean_sigma` 和 `valuation_label`。真实页面验证：2026-05-11 当前 PE 为 32.66；不把标准差区间或估值标签冒充 historical percentile。
- **Trendonify 稳定路径明确**：普通 requests 仍不作为稳定主链路；`bb-browser` sidecar 是显式、用户信任后才合并的路径。`browser_sidecar.py` 修复 `parse_status` 判断，增强 Forward PE 文本解析，并在刷新遇到 Cloudflare/空页面时按 `page_type` 保留旧的可用 trusted page，避免刷新污染旧 sidecar。
- **L4 合并逻辑增强**：`get_ndx_valuation_third_party_checks()` 会在 direct requests 后合并 `user_trusted=true` 的 Trendonify sidecar，并保留 `browser_sidecar` 采集时间、信任标记和失败刷新保留元数据。
- **manual/Wind 覆盖边界修复**：当 `get_ndx_pe_and_earnings_yield` 使用 manual/Wind 主值时，collector 仍会轻量拉取 live third-party checks，写入 `value.ThirdPartyChecks` 和 `data_quality.source_disagreement`；manual 主值不被替换，第三方源只作为审计交叉校验。
- **控制台刷新容错**：`console_run_all.py` 在用户信任 Trendonify sidecar 时会先尝试刷新；刷新失败或单页解析失败不会中断整条流水线，会保留已有可用 sidecar 或写入 failed payload 供审计。

验证结果：

- `python3 -m pytest tests/test_l4_external_valuation_sources.py tests/test_browser_sidecar.py -q`：10 passed。
- `python3 -m pytest tests/test_l4_external_valuation_sources.py tests/test_l4_data_authority.py tests/test_browser_sidecar.py tests/test_vnext_reporter.py tests/test_console_run_all.py -q`：31 passed。
- `python3 -m pytest -q`：154 passed，6 warnings。
- 真实 WorldPERatio 页面验证：`value=32.66`，`data_date=11 May 2026`，1Y/5Y/10Y/20Y 窗口均解析成功，`historical_percentile=None`。
- 真实 Damodaran 验证：`retrieval_method=monthly_excel`，`source_file=ERPbymonth.xlsx`，`data_date=2026-05-01`，`monthly_series=120`。
- `bb-browser` sidecar 刷新验证：Forward PE 刷新为 23.8 / 2026-05-11 / 10Y percentile 58.3；Trailing PE 当前刷新遇到空/验证页，保留旧 trusted 值 38.07 / 2026-05-08，并写入 `preserved_after_failed_refresh_at_utc`。
- `python3 src/main.py --collect-only --models deepseek-v4-flash,deepseek-v4-pro --skip-report --disable-charts`：采集成功，`output/data/data_collected_v9_live.json` 中 `get_ndx_pe_and_earnings_yield.value.ThirdPartyChecks` 包含 `worldperatio_pe`、`trendonify_pe`、`trendonify_forward_pe`；Damodaran 月度序列为 120 条。
- collect-only packet/brief：`output/analysis/vnext/20260512_215333_collect_only/analysis_packet.json`，`output/reports/vnext_brief_20260512_2153.html`。brief 中可检索 `WorldPERatio`、`Trendonify`、`browser_sidecar`、`ThirdPartyChecks`、`ERPbymonth.xlsx`，且不再出现“未接入 Trendonify 或 WorldPERatio”。

真实运行观察：

- `python3 src/main.py --models deepseek-v4-flash,deepseek-v4-pro --skip-report --disable-charts` 完成数据采集并写出 `output/analysis/vnext/20260512_211406/analysis_packet.json`，但 LLM 分析阶段因 DeepSeek flash/pro 多次 `APIConnectionError` / timeout，最终 `l1 received empty response` 失败；这属于模型连接稳定性问题，不是本轮三个数据源解析/合并失败。
- 该失败 run 不能作为完整 vNext 叙事验收；数据源验收以 collect-only JSON、collect-only packet/brief、单源真实抓取和测试为准。

## 2026-05-11

### 20260510_225944 报告自查：微图误导、空底稿文案与 Crosshair 读数修复

完成内容：

- 复核用户批注和 `20260510_225942_913.log`：确认本次 run 没有实际执行 live Damodaran / WorldPERatio / Trendonify 采集，报告中“已并入 L4 微图”的说法会误导读者。
- 移除 brief 中 demo/模板说明式文案和“市场图谱”空图谱入口，改为官方事件底账占位；无新闻底账时明确说明事件不进入 L1-L5 数值证据。
- L4 估值微图在没有 WorldPERatio/Trendonify 时改为中性标题，并显示 PE_TTM、PB 等主来源字段；人工/Wind ERP 不再冒充 Damodaran 官网月度序列。
- 底稿数据质量区不再渲染裸 `[]` / `{}`；source value 摘要不再输出整块 dict。
- 修复 L5 静态微图的横向溢出：MACD 与 VWAP 偏离条限制为半轴宽度，避免条形穿出卡片。
- 修复价格技术 workbench crosshair：默认展示最新交易日读数，鼠标移动时兼容不同时间格式，并补齐 MA、Bollinger、Donchian、VWAP、MACD/Signal 等具体指标。

验证结果：

- `python3 -m pytest tests/test_interactive_chart_workbench.py tests/test_vnext_reporter.py tests/test_research_console.py -q`：13 passed，4 warnings。
- 生成修复版 brief：`output/reports/vnext_brief_20260510_225944_reviewfix.html`。
- 生成修复版 workbench：`output/reports/vnext_workbench_20260510_225944_reviewfix.html`。
- `python3 src/report_visual_regression.py ...`：desktop/mobile brief 与 workbench 截图均 OK，布局扫描 passed。
- 本地浏览器打开新 workbench：标题正常，控制台无 error/warning，读数区包含最新日期、MA20、VWAP20、Donchian 等具体指标。

### Bridge 输入污染复核：L3 core_facts 字符串拆分修复

完成内容：

- 复核 [BRIDGE_INPUT_AUDIT_L3_COREFACTS_CONTAMINATION.md](BRIDGE_INPUT_AUDIT_L3_COREFACTS_CONTAMINATION.md)：确认 `_normalize_payload()` 在 `core_facts` 为字符串时会逐字符迭代，导致单字符 `CoreFact` 噪声污染 Bridge 输入；问题属于上游归一化缺陷，不是 Bridge 设计问题。
- `src/agent_analysis/orchestrator.py` 在遍历前先规整 `core_facts`：字符串、bytes、单个 dict 或其他非 list 值都会包装为单元素列表，避免未来任何 L1-L5 输出同类格式偏差时被拆碎。
- L1-L5 prompt 的 Output Discipline 补充 `core_facts` 对象数组约束，作为模型输出层辅助防线；代码兜底仍是主防线。
- 新增两个 orchestrator 回归测试，覆盖 `core_facts` 纯文本字符串和单个对象 dict 两种异常形态。

验证结果：

- 修复前手动复现：`core_facts="QQQ/QQEW比率触及历史极值"` 被拆成 16 条单字符 fact。
- 修复后手动复核：同一字符串归一化为 1 条 fact。
- `python3 -m pytest tests/test_vnext_orchestrator.py::test_layer_payload_normalization_wraps_core_facts_string tests/test_vnext_orchestrator.py::test_layer_payload_normalization_wraps_single_core_fact_dict tests/test_vnext_orchestrator.py::test_layer_payload_normalization_backfills_indicator_evidence_refs -q`：3 passed。
- `python3 -m pytest tests/test_vnext_orchestrator.py -q`：9 passed。
- `python3 -m pytest -q`：142 passed，6 warnings。

## 2026-05-10

### AI 复核补丁：Workbench 时间轴收口与 Damodaran 缓存防污染

分支：`claude/20260510-debug-run-issues`

完成内容：

- **Workbench 时间轴收口**：复核发现 Claude 报告称已移除子图/module 独立 `fitContent()`，但代码中仍残留。补丁后初始化和模块重绘都不再各自 `fitContent()`，统一由主价格图时间轴决定全局范围。
- **模块图重绘清理**：`renderModuleChart()` 在归一化/双轴切换时会创建新图表，但旧图表仍留在同步列表中。新增 `moduleCharts` 与 `unregisterChart()`，重绘前清除旧实例，避免幽灵图表继续参与时间轴和 crosshair 同步。
- **Damodaran 缓存防污染**：复核发现本地 1-2KB 的 stub `.xlsx` 会被 24h 缓存信任，导致新 run 仍可能只得到极短 `monthly_series`。新增缓存 payload 校验，官方月度/当月 xlsx 过小或非 ZIP-xlsx 时自动丢弃并重新抓取。
- **测试补强**：新增 Workbench JS 断言、Damodaran 坏缓存剔除测试、manual ERP 描述字段不触发 override 测试。

验证结果：

- 直接绕过坏缓存后重新抓取 Damodaran 官方文件：`ERPbymonth.xlsx` 约 46KB、`ERPMay26.xlsx` 约 1.46MB，解析出 120 条月度序列，最新 `data_date=2026-05-01`。

### 20260510_193710 Run Debug: Damodaran ERP 缓存、图表对齐、Crosshair、Reviser Prompt 修复

分支：`claude/20260510-debug-run-issues`

完成内容：

- **Damodaran ERP 月度序列为空（P0）**：根因是 `collector.py` 中手动覆盖逻辑会跳过 live `get_damodaran_us_implied_erp()`，导致 `monthly_series` 不生成。修复：Damodaran 总是调用 live 函数，手动值作为补充合并而非替换。
- **Damodaran 文件本地缓存**：`tools_L4.py` 新增 `_fetch_bytes_cached()`，在 `data_cache/damodaran/` 下缓存 `ERPbymonth.xlsx` 和当月 calculator xlsx，TTL 24 小时。
- **`has_meaningful_manual_override()` 误判**：`manual_data.py` 将 `"scope"`、`"not_ndx_valuation_warning"` 加入忽略键列表，避免纯描述性字符串触发手动覆盖。
- **OBV 子图横轴未对齐（P1）**：根因是初始化时每个子图独立 `fitContent()` 导致 "last writer wins"。修复：初始化时 `syncLocked = false`，所有图表创建完成后统一设 `syncLocked = true`，由主图 `fitContent()` 单向传播。
- **Crosshair 右侧读数不正确（P1）**：根因是 `priceReadoutHtml` 和 `syncCrosshair` 使用 `findPoint`（精确时间匹配），子图因指标预热期数据点数较少导致匹配失败。修复：全部替换为 `findPointAtOrBefore`。
- **Reviser 校验失败（P2）**：`contracts.py` 中 `environment_assessment` 等字段有 `max_length=300`，但 prompt 未注明字符限制。修复：在两个 `reviser.md` 中添加长度约束和质量检查项。
- **测试更新**：`tests/test_l4_data_authority.py` 中 4 个 monkeypatch 测试补上 `_fetch_bytes_cached` mock。

验证结果：

- `python -m pytest -q`：138 passed，164 warnings。

剩余观察：

- WTREGEN 警告（log 中 million-dollar unit mixing）：待调查。

---

### 市场图谱布局重构：Damodaran ERP 与 WorldPERatio 并入 L4

分支：`claude/20260510-debug-run-issues`（同一分支）

完成内容：

- **`_damodaran_indicator_visual` 增强**：从 atlas 移入 SVG 月度线图（ERP T12M / 10Y Treasury / Expected return 三条路径）、8 项 ERP 透镜指标、data_date/source 脚注。L4 微图现在是 atlas 的超集。
- **`_valuation_indicator_visual` 增强**：从 atlas 移入 WorldPERatio 窗口标签表（1y/5y/10y/20y 均值 PE、标准差、区间、偏离 σ、估值标签）及 SMA50/SMA200 趋势语境。
- **Atlas section 精简**：移除 `_damodaran_erp_chart`、`_worldperatio_window_chart`、`_worldperatio_relative_position` 三个方法（~100 行）。Atlas 保留估值相对位置尺和 L1-L4 利率估值压力图两张图表。Section 描述更新为"跨层压力与估值位置"。
- **测试更新**：`test_vnext_reporter.py` 中 5 个断言更新为新的 L4 微图标题和属性。

验证结果：

- `python -m pytest -q`：138 passed，164 warnings。

---

### Bridge 阶段 JSON 容错升级 — event_refs 兜底与 DeepSeek /beta 校验

分支：`claude/20260510-bridge-event-refs-resilience`（继续在同一分支上做方案 B）

完成内容：

- AI 审阅后补齐两个边界：子级 `typed_conflicts` / `resonance_chains` / `transmission_paths` 内部的 `event_refs` 现在也复用 `_coerce_event_refs_list`，避免 dict 被整段 stringify 后“过 schema 但丢语义”；真实 run 证明 DeepSeek 不允许 `response_format=json_object` 与 `prefix: true` 组合，因此当前 JSON 主链明确不发送 prefix。
- 重新核对 DeepSeek 官方文档（`https://api-docs.deepseek.com/zh-cn/`，2026-05-10 抓取）：当前主力模型为 `deepseek-v4-flash` 与 `deepseek-v4-pro`；`deepseek-chat` 与 `deepseek-reasoner` 将于 2026/07/24 弃用，分别等价于 v4-flash 的非思考 / 思考模式。文档明确 v4 全系列同时支持 Json Output 与 Tool Calls，且思考模式与 Tool Calls / Strict Mode 兼容。
- `src/agent_analysis/llm_engine.py` 新增 `_resolve_deepseek_base_url`：当 `get_base_url("deepseek")` 是默认生产值 `https://api.deepseek.com` 时升级为 `https://api.deepseek.com/beta`，为（未来的）strict function calling 做准备；显式 /beta 保持；自定义自托管 endpoint 不被重写。
- `src/agent_analysis/llm_engine.py` 保留 `response_format={"type":"json_object"}` 作为当前 JSON 主链保护，并增加测试确保不与 prefix completion 组合。Claude 原报告中的 prefix 方案经真实 run 证伪后已撤回。
- 新增 5 个 llm_engine 测试：`tests/test_vnext_llm_engine.py` 的 `test_deepseek_client_promotes_default_base_url_to_beta` / `test_deepseek_client_does_not_double_promote_explicit_beta` / `test_deepseek_client_respects_self_hosted_base_url` / `test_call_ai_uses_json_output_without_prefix_for_deepseek` / `test_call_ai_does_not_send_beta_prefix_to_custom_deepseek_endpoint`。更新已有的 `tests/test_deepseek_runtime_config.py::test_deepseek_v4_calls_use_official_reasoning_parameters`，确认 thinking 参数与 JSON Output 保留，且不发送 prefix。
- 新增 AI 审阅报告 [docs/2026-05-10_BRIDGE_JSON_RESILIENCE_AI_AUDIT.md](docs/2026-05-10_BRIDGE_JSON_RESILIENCE_AI_AUDIT.md)：完整记录 bug → 系统性根因 → DeepSeek 官方约束工具链事实校核 → 本次实施（Fix 1+2+3 + 方案 B-1+B-2）→ 验证 → 仍存在的 8 类不稳定面 → 阶段 C/D/E 下一步建议 → 关键代码位置速查 → 审阅检查表，供其他 AI 审阅。

验证结果：

- 修改前：4 个新增 llm_engine 测试中 1 个按预期 fail（`/beta` 升级）；AI 审阅后追加并调整测试，覆盖 JSON Output 不发送 prefix 与自定义 endpoint 边界。
- 修改后：`python -m pytest -q tests/test_vnext_llm_engine.py tests/test_deepseek_runtime_config.py tests/test_bridge_v2.py tests/test_vnext_orchestrator.py` 全绿。
- `python -m pytest -q`：138 passed，164 warnings。
- 真实 run 验证：`.venv/bin/python src/main.py --data-json output/data/data_collected_v9_live.json --models deepseek-v4-flash,deepseek-v4-pro --skip-report --disable-charts` 成功生成 `output/analysis/vnext/20260510_191820/`；`llm_stage_diagnostics.json` 显示 bridge `status=ok`、`attempts=1`、`errors=[]`，最终 stance 为 `中性偏谨慎`，approval 为 `approved_with_reservations`。

剩余观察：

- 阶段 C（强约束）仍是根治路径：把 BridgeMemo 改造为 strict function calling tool。文档明确思考模式与 strict 兼容，但需要 contracts 层移除 `extra="allow"`、把 Optional 字段改为带默认值的 required、用 $ref/$def 复用枚举。建议先在 bridge stage 单点 PoC。
- 阶段 E 基础设施清理：`.gitignore` 增加 `ai_response_debug_*.txt`（当前仓库根有两个未跟踪的 debug 文件）；思考模式下 `temperature: 0.2` 实际无效，建议条件化；`max_node_retries` 可考虑提到 3（缓存命中价格 1/10，重试成本接近零）。
- 子级 normalize "过校验、坏语义" 地雷（U1）已处理；prompt 减负（U2）仍未处理，等真实 run 数据决定优先级。

### Bridge 阶段 event_refs 类型容错与重试反馈强化

分支：`claude/20260510-bridge-event-refs-resilience`

完成内容：

- 排查 `output/logs/control_service/20260510_132806_164.log`：bridge 阶段两次 attempt 不同错因导致 `RuntimeError: bridge failed after 2 attempts`。Attempt 1 是 `resonance_chains[0].falsifiers` 数组未闭合，`_light_repair_json` 修不了结构性破损；attempt 2 是 LLM 把顶层 `event_refs` 输出成 dict（模仿了 `AnalysisPacket.event_refs: Dict[str, Dict]` 输入形态），与 `BridgeMemo.event_refs: List[str]` 撞型。`llm_stage_diagnostics.json` 印证了两次错误属于不同 kind（parse_error → schema_validation_error）。
- `src/agent_analysis/orchestrator.py::_normalize_payload` 在 bridge 分支末尾新增 `_coerce_event_refs_list` 兜底：dict→keys、list[dict]→提取 `event_id`/`id`/`event_ref`/`ref`、scalar→`[str(value)]`、None→`[]`。子级别 typed_conflicts/resonance_chains/transmission_paths 的 event_refs 已有归一化，本次只补顶层缺口，不动既有路径。
- `src/agent_analysis/orchestrator.py::_run_stage` 的 parse_error 反馈从 "did not return a parseable JSON object" 升级为「错误描述 + 原始响应字符数 + 末尾 400 字符片段」，给下一轮 LLM 提供可定位的语法错误线索；`raw_excerpt` 仍只在 diagnostics 里保留 500 字符，不外泄。
- `src/agent_analysis/orchestrator.py::_compose_bridge_prompt` 增加 "顶层 BridgeMemo.event_refs 字段类型（强约束）" 段落，显式说明 List[str] 类型 + 字符串 ID 数组示例，并指出输入 dict 形态不得复制到输出，杜绝 LLM 模仿输入格式。
- 新增 3 个失败先行测试：`tests/test_bridge_v2.py` 的 `test_bridge_normalize_coerces_top_level_event_refs_to_list` 与 `test_bridge_prompt_anchors_event_refs_as_string_list`，`tests/test_vnext_orchestrator.py` 的 `test_run_stage_parse_error_feedback_includes_response_excerpt`。

验证结果：

- 修改前：3 个新测试均按预期 fail（normalize 留下 dict、prompt 缺锚点、last_error 不含响应末尾）。
- 修改后：`python -m pytest -q tests/test_bridge_v2.py tests/test_vnext_orchestrator.py::test_run_stage_records_parse_retry_diagnostics tests/test_vnext_orchestrator.py::test_run_stage_parse_error_feedback_includes_response_excerpt` 全绿。
- `python -m pytest -q`：132 passed，163 warnings。

剩余观察：

- 本次仅修补顶层 event_refs；L1-L5 隔离、bridge 高严重度冲突保留、legacy_adapter 边界均未触动。
- 子级别 normalize 仍保留 `not isinstance(value, list) → [str(value)]` 行为：若 LLM 把 typed_conflicts/resonance_chains/transmission_paths 内部 event_refs 写成 dict，会 stringify 成单元素列表，能过 schema 但语义被毁。这是潜在的"过校验、坏语义"地雷，未在本轮处理；后续若发现下游 evidence 追溯失败，再单独修。
- 重试反馈强化对所有 stage 生效（不只是 bridge），有助于其它 stage 在长 JSON 偶发语法错误时收敛；监控下次 run 的 `llm_stage_diagnostics.json`。
- bridge prompt 长度此次基本不变（仅追加约 350 中文字符的强约束段落）；本次未做 prompt 减负（备选项 #4），避免一次性引入过多变量。

### 修复控制台运行环境、产物跳转、命名和实时数据链路

完成内容：

- 排查最新 control service run `20260510_001423_727`：LLM 主链完成，核心异常不是 DeepSeek，而是控制台任务用系统 `python3` 启动，实际落到 macOS Python 3.9，导致 `pandas_ta` 缺失；`.venv` 中 `pandas_ta` 与 `pandas_datareader` 均可用。
- `src/control_service.py` 现在把白名单里的 `python/python3` 命令绑定为服务自身的 `sys.executable`，确保从 `start.command` / `open_research_console.command` 启动后，后续任务都跑在同一个虚拟环境。
- `control_service` 新增 `/artifact?path=...` 和 `/latest-product`：控制台里的“打开最新报告 / workbench”和底部最新产物不再依赖浏览器从 `http://127.0.0.1` 跳 `file://`，而是由本地服务安全读取仓库内产物。
- 控制台任务完成后会轮询状态；完整运行成功会自动打开最新 native brief，workbench-only 成功会自动打开 workbench。
- 简化新产物命名：native brief 改为 `vnext_brief_<数据采集分钟>_<运行分钟>.html`，workbench 改为 `vnext_workbench_<数据采集分钟>_<运行分钟>.html`；旧命名仍可被控制台识别为历史产物。
- `src/open_research_console.py` 的版本探针增加新 artifact 跳转标记；旧 control service 若仍占用端口，会被判定为过期并重启。
- 修复 M2 YoY 只有水平没有分位：新增 `calculate_yoy_series()`，M2 的相对位置现在基于同比序列本身计算 1Y/10Y 分位。
- 修复净流动性：WTREGEN 缓存存在百万美元/十亿美元混合口径，现逐点转换到十亿美元；`calculate_long_term_stats()` 强制数值化，避免 pandas/numpy object dtype 异常。
- 修复默认实时模式误用历史成分股：L2 breadth、L4 component model、`get_equity_risk_premium` 不再把当前日期隐式传给 `get_ndx100_components(end_date=...)`；只有显式历史日期才使用历史成分。
- `requirements.txt` 将 pandas 约束为 `<3.0.0`，因为 pandas-datareader 0.10.0 对 pandas 3 需要兼容补丁；当前代码仍保留窄兼容，但新装环境优先避免踩坑。

验证结果：

- `.venv/bin/python` 环境探针：`pandas_ta=True`，`pandas_datareader=True`。
- `python src/main.py --collect-only` 真实采集：生成 `output/data/data_collected_v9_live.json`，39 个指标全部有值，0 缺失，0 错误。
- 单点验证：`get_qqq_technical_indicators` 和 `get_adx_qqq` 成功，ADX 使用 `ta` 公式层；`get_net_liquidity_momentum` 成功输出 5830.96 十亿美元并带 5Y/10Y 分位。
- `python src/agent_analysis/vnext_reporter.py --run-dir output/analysis/vnext/20260510_001425 --template brief`：生成 `output/reports/vnext_brief_20260509_2215_20260510_0014.html`。
- `python src/interactive_chart_workbench.py --run-dir output/analysis/vnext/20260510_001425 --modules price_technical,volatility_credit,rates_valuation,breadth_concentration,liquidity`：生成 `output/reports/vnext_workbench_20260509_2215_20260510_0014.html`。
- `./start.command`：打开 `http://127.0.0.1:8765`；`/artifact` 可直接服务新 brief HTML；当前只保留一个 8765 control service。
- 定向测试：`python -m pytest tests/test_l3_breadth_data.py tests/test_l4_forward_earnings_quality.py tests/test_l1_m2_relativity.py tests/test_control_service.py tests/test_research_console.py tests/test_vnext_reporter.py -q`：28 passed。

结论：

- VPN/yfinance/DeepSeek 分开排查是正确方法，但这次“数据大量缺失”的主因不是 DeepSeek，而是控制台任务跑错 Python 环境，加上少数数据函数把实时模式误切成历史成分路径。
- OpenBB 可以继续作为后续数据覆盖研究对象，但不应在本轮作为第一修复手段；当前主链自身已恢复到 39/39 指标可用。

## 2026-05-09

### 修复控制台分段验证与 yfinance 缺数下的 workbench 崩溃

完成内容：

- 排查 `output/logs/control_service/20260509_220522_366.log`：本轮 DeepSeek 从 L1 到 Final 全部成功，实际失败点是 workbench 生成阶段；yfinance 限流导致 L5 技术指标值为 `None`，`src/interactive_chart_workbench.py` 直接 `.get()` 触发崩溃。
- `src/interactive_chart_workbench.py` 增加 L5 原始指标空值保护：`get_multi_scale_ma_position` 和 `get_qqq_technical_indicators` 的 value 为 `None` 时降级为空字典，workbench 继续生成，缺失指标在 payload 中保持 `null`。
- `src/main.py` 新增 `--collect-only`，用于只采集市场数据 JSON，不进入 DeepSeek / vNext LLM 链路；便于 VPN 开关下把 yfinance 与 DeepSeek 分开排查。
- `src/control_service.py` 白名单允许 `src/main.py --collect-only`。
- `src/research_console.py` 自动填入最近的 `output/data/data_collected_v9_*.json`；“已有数据分析”改为只运行 `src/main.py --data-json ... --skip-report --disable-charts`，不再串联 native brief 和 workbench；“只采集数据”现在生成真正的 `--collect-only` 命令。
- 修正控制台日期语义：普通“分析日期”不再自动触发 `--date`；只有显式勾选“历史日期 / 回测”时才把日期传给 `src/main.py` / `src/console_run_all.py`，避免把最新周末日期误当历史时点分析。
- 保留上一轮 L2 韧性修复：`VXN/VIX` 上游缺数不再抛异常；Layer 自检覆盖字段可从实际 `indicator_analyses` 派生校正；LLM JSON 解析器可修复模型偶发的数组错括号和尾逗号。

验证结果：

- `python3 -m pytest tests/test_control_service.py tests/test_research_console.py tests/test_main_collect_only.py tests/test_interactive_chart_workbench.py tests/test_runtime_resilience.py -q`：15 passed。
- `python3 src/research_console.py`：重新生成 `output/reports/vnext_research_console.html`。
- `rg -n "historicalDateMode|--date|modeCommand" output/reports/vnext_research_console.html`：确认控制台只在历史回测开关勾选时拼接 `--date`。
- `python3 src/interactive_chart_workbench.py --run-dir output/analysis/vnext/20260509 --modules price_technical,volatility_credit,rates_valuation,breadth_concentration,liquidity`：在 QQQ 仍被 yfinance 限流的情况下成功生成 `output/reports/vnext_interactive_charts_20260509.html`。
- `python3 -m pytest -q`：124 passed，6 warnings。

结论：

- VPN / 网络路径对 yfinance 与 DeepSeek 产生相反影响是合理的现实假设；当前系统已支持先在适合 yfinance 的网络下“只采集数据”，再切到适合 DeepSeek 的网络下用“已有数据分析”消费同一份 JSON。
- 本轮 DeepSeek 没有在 L2 JSON 输出处失败；上一轮 L2 格式问题是大上下文、强约束 JSON 与模型偶发语法失误叠加，不能简单归因于单个示范或模型“完全不行”。系统已增加窄口径解析修复和合约自校正。

### 产品化研究控制台启动与完整运行闭环

完成内容：

- 新增 `open_research_console.command` 和 `src/open_research_console.py`：双击或运行 Python 启动器即可生成控制台、启动本地 control service，并打开 `http://127.0.0.1:8765`。
- `src/control_service.py` 的根地址 `/` 和 `/console` 现在直接返回研究控制台，不再让用户看到 `{"ok": false, "message": "Not found"}`；新增 `/manual-data` GET/POST，用于读取和保存 `config/manual_data.local.json`。
- 新增 `src/console_run_all.py`：控制台“运行完整报告”会保存人工数据，执行 vNext 主链，生成 native brief，并生成 interactive workbench；运行摘要写入 run 目录和 `output/logs/control_service/latest_console_run.json`。
- 控制台把“人工数据”和“数据源选择”合并为“人工数据与数据源校准”：上次保存的人工 PE/PB/PS/ERP 与分位会自动回填，官方事件底账和 bb-browser 信任选择与人工校准放在同一区域。
- 控制台运行命令现在携带分析日期、模型、数据 JSON、workbench modules 和 legacy 开关；默认主路径从单步 `src/main.py` 改为完整产品流 `src/console_run_all.py`。
- README 增加明确开启方式：双击 `open_research_console.command`，或命令行运行 `python src/open_research_console.py`，或手动启动 service 后访问 `http://127.0.0.1:8765`。

验证结果：

- `python3 -m py_compile src/control_service.py src/research_console.py src/console_run_all.py src/open_research_console.py`：通过。
- `python3 -m pytest -q tests/test_research_console.py tests/test_control_service.py`：6 passed。
- 临时启动 `python3 src/control_service.py --port 8766`：`GET /` 返回控制台 HTML，`GET /manual-data` 返回当前人工数据 JSON；验证后已关闭临时服务。
- `python3 src/report_visual_regression.py --brief-html output/reports/vnext_research_ui_brief_20260505_20260506_075229.html --workbench-html output/reports/vnext_interactive_charts_20260506.html --console-html output/reports/vnext_research_console.html --output-dir output/reports/visual_regression/20260509_console_product_flow`：通过。
- `python3 -m pytest -q`：118 passed，6 warnings。

### 完成 NEXT_STEPS P2：用 Impeccable shape/craft 打磨控制台与 brief

完成内容：

- 按 `$impeccable` 流程读取 `PRODUCT.md` / `DESIGN.md`，确认本轮是 product register。shape 结论：控制台是“运行仪器”，brief 是“可审计长文”；采用浅色纸面、克制 OKLCH、清晰规则线和少量状态色，不走深色终端、SaaS 卡片堆叠或纯铁锈单色系。
- 对 Claude 排版报告做取舍：采纳“编辑室/仪器面板分工”“sticky 阅读导航”“引用视觉语法”“避免类别反射”；不采纳“控制台改成阶段向导隐藏复杂度”和“风险/良好都用同一铁锈明度表达”，因为 vNext 需要一屏复跑审阅和清晰状态语义。
- 控制台新增流程锚点：设定对象、校准输入、生成命令、审计边界；运行区和人工输入区权重提升，面板不再被网格强行拉成等高，移动端强制单列，避免 span grid 造成窄屏裁切。
- 控制台视觉系统改为 OKLCH tokens，去掉旧版/sidecar 警示的彩色侧边条，改用完整边界和轻色底；补齐按钮 hover/focus、输入断行、长路径/命令预览的窄屏保护。
- brief 默认 `slate_v2` 改成更适合连续阅读的形态：桌面 brief 使用左侧 sticky 章节导航、右侧正文；风险、冲突和边界卡从彩色侧边条改为完整边界和语义底色；证据引用 chip 加入小型视觉语法，长文和长 ref 增加断行保护。
- `src/report_visual_regression.py` 支持可选 `--console-html`，把研究控制台纳入同一轮桌面/移动截图回归；同时修正静态扫描对 `@media (min-width: ...)` 的误报，并处理 macOS Chrome headless 窄屏截图会裁掉 500px 最小布局视口的问题。
- 重新生成：
  - `output/reports/vnext_research_console.html`
  - `output/reports/vnext_research_ui_brief_20260505_20260506_075229.html`
  - `output/reports/vnext_interactive_charts_20260506.html`
  - `output/reports/visual_regression/20260509_p2_console_brief_full_run/`

验证结果：

- `node /Users/aidianchi/.agents/skills/impeccable/scripts/load-context.mjs`：`hasProduct=true`，`hasDesign=true`，`register=product`。
- `python3 -m pytest -q tests/test_research_console.py tests/test_vnext_reporter.py tests/test_report_visual_regression.py tests/test_control_service.py`：15 passed。
- `python3 -m pytest -q`：117 passed，6 warnings。
- `python3 src/report_visual_regression.py --brief-html output/reports/vnext_research_ui_brief_20260505_20260506_075229.html --workbench-html output/reports/vnext_interactive_charts_20260506.html --console-html output/reports/vnext_research_console.html --output-dir output/reports/visual_regression/20260509_p2_console_brief_full_run`：passed，brief / workbench / console 的 desktop 和 mobile captures 均 ok，layout checks 均 ok。

剩余观察：

- 本轮完成控制台和 brief 的 shape/craft/polish，不处理 workbench 的进一步视觉重构；workbench 只作为视觉回归配套目标继续验证。
- 2026-05-09 数据验证 run 缺少最终裁决 artifacts，因此 brief craft 使用更完整的 `output/analysis/vnext/20260506_075229` 作为长文排版验证对象；2026-05-09 run 仍保留为 HY 真实数据验证对象。

### 清理历史输出样本，保留输出体验优化基线

完成内容：

- 清理 `output/reports/` 中 2026-04-23、2026-05-02、2026-05-06 生成的历史 brief / redesign / workbench 样本，只保留当前输出体验继续优化需要的入口：
  - `output/reports/vnext_research_console.html`
  - `output/reports/vnext_research_ui_brief_20260502.html`
  - `output/reports/vnext_interactive_charts_20260509_hy_quality.html`
- 删除旧视觉回归截图目录 `output/reports/visual_regression/`，避免后续 polish 时把历史截图误当当前设计基线。
- 清理旧 vNext run 目录，只保留完整可复用 run `output/analysis/vnext/20260506_075229` 和 P1 数据验证 run `output/analysis/vnext/20260509_134942`。
- 清理旧数据快照，只保留最新 `output/data/data_collected_v9_live.json`；保留 `output/browser_sidecar/trendonify_ndx_valuation.json` 作为当前 bb-browser sidecar smoke 结果。
- 删除仓库内 `.DS_Store`，并重新生成 `output/reports/vnext_research_console.html`，让控制台链接列表反映清理后的干净输出目录。

验证结果：

- `find . -name '.DS_Store' -print`：无输出。
- `output/` 体积从约 39M 降到约 17M。

### 完成所有 P1：运行控制、事件底账治理、event_ref、HY 真实验证与 bb-browser sidecar

完成内容：

- `control_service` 增加 `/status/<job_id>` 与 `/cancel/<job_id>`，任务状态持久化到 `output/logs/control_service/*.json`，状态响应包含日志路径、日志尾部、退出码和失败原因；`/run` 现在要求显式 `confirmed=true`，继续保留命令白名单。
- 研究控制台新增运行状态刷新、取消任务、日志/失败原因展示；运行前会弹出确认。控制台还新增 `bb-browser` 估值 sidecar 区：可跳转 Trendonify PE / Forward PE 页面，可通过 control service 单独拿数据，可勾选“信任 bb-browser 来源”并把来源标记写入人工模板。
- 新增 `src/browser_sidecar.py`：只采集明确允许的 Trendonify NDX Trailing PE 与 Forward PE 页面，输出 `schema_version=browser_sidecar_v1`、source tier、采集时间、URL、解析字段、页面摘要、失败模式和 `user_trusted` 标记；主 L4 requests 链仍不自动调用浏览器。
- `browser_sidecar` 真实 smoke：输出 `output/browser_sidecar/trendonify_ndx_valuation.json`，两页均可用。Trailing PE 38.07，1Y/5Y/10Y/20Y 分位均为 100；Forward PE 23.73，1Y 分位 33.3、5Y 分位 40、10Y 分位 57.5、20Y 分位 71.2。
- 新闻事件底账升级为 `news_event_ledger_v2`：新增 `source_tier`、`layers`、`dedupe_id`，保留 `event_type`、`published_at`、`symbols` 和 `source_errors`，并增加 45 天时间窗口与去重治理；新闻仍不注入 L1-L5 prompt。
- `AnalysisPacket` 新增独立 `event_refs`；Bridge payload 可选接收事件索引；`SynthesisPacket` 新增 `event_index`；Bridge / Thesis / governance 合约新增 `event_refs` 字段和约束。`event_ref` 与 `evidence_ref` 分离，只能写成解释、触发或观察背景，不能写成证明。
- 真实数据 run 验证 `HY CCC & Lower - BB OAS`：`output/analysis/vnext/20260509_134942/analysis_packet.json` 中 `get_hy_quality_spread_bp` 成功，最新数据日 2026-05-07，值 7.44，CCC OAS 9.15、BB OAS 1.71，`data_quality` 包含官方源、公式、覆盖 786 个共同观测和 fallback chain。
- 同一 run 的 `chart_time_series.json` 已包含 `HY_QUALITY_SPREAD`，786 行，覆盖 2023-05-09 至 2026-05-07；生成波动信用 workbench：`output/reports/vnext_interactive_charts_20260509_hy_quality.html`，HTML 内嵌该序列。

验证结果：

- `python3 -m pytest -q tests/test_control_service.py tests/test_news_event_ledger.py tests/test_browser_sidecar.py tests/test_vnext_packet_builder.py tests/test_bridge_v2.py tests/test_research_console.py`：20 passed。
- `python3 -m py_compile src/control_service.py src/news_event_ledger.py src/browser_sidecar.py src/research_console.py src/main.py src/agent_analysis/contracts.py src/agent_analysis/packet_builder.py src/agent_analysis/orchestrator.py`：通过。
- `python3 src/research_console.py`：重新生成 `output/reports/vnext_research_console.html`。
- `python3 src/browser_sidecar.py --source trendonify_valuation --output output/browser_sidecar/trendonify_ndx_valuation.json --trusted --wait-seconds 10 --timeout 60`：2 pages，0 errors。
- `python3 src/interactive_chart_workbench.py --run-dir output/analysis/vnext/20260509_134942 --modules volatility_credit --output output/reports/vnext_interactive_charts_20260509_hy_quality.html`：通过。
- `python3 -m pytest -q`：117 passed，6 warnings。

剩余观察：

- 2026-05-09 真实 run 的数据采集、事件底账、analysis packet 与 chart time-series 已完成；模型阶段因 DeepSeek 长响应期间多次 `APIConnectionError` 被手动中止，未生成完整 `run_summary.json`。本轮 HY P1 验证依赖已生成的真实数据 artifacts，而不是完整模型报告。
- `bb-browser` sidecar 仍是人工确认/sidecar 路径；即使勾选“信任”，也只是给人工模板打来源标记，不会让 L4 主链静默绕过 Cloudflare。

### 增强人工 ERP 分位与 Trendonify / bb-browser 估值百分位研究

完成内容：

- 研究控制台的人工 / Wind 数据区新增 ERP 5Y 分位和 ERP 10Y 分位，写入 `get_damodaran_us_implied_erp.value.manual_erp_percentile_5y/10y`。
- 调整控制台人工 ERP 写入边界：ERP 输入只作为 Manual/Wind ERP reference，不再同步写入 `get_equity_risk_premium` 的简式收益差距，避免把外部 ERP 和 NDX yield gap 混在一起。
- `DEFAULT_MANUAL_DATA` 补齐 PE / Forward PE / PB / PS 的 10Y 分位字段，以及 ERP reference 的 5Y / 10Y 分位字段。
- 增强 Trendonify parser：除 `Valuation Percentile Rank` 的 10Y 主分位外，额外解析 Historical P/E Comparison 表中的 1Y / 5Y / 10Y / 20Y / since-inception median、percentile 和 valuation label。
- Trendonify 可行性结论：普通 `requests` 浏览器头、Jina Reader 文本代理都仍返回 Cloudflare 验证页；`bb-browser daemon start` 后可用真实浏览器打开页面并通过 `document.body.innerText` 读取公开文本，适合作为隔离 sidecar / 人工调研辅助，不适合作为默认主数据链。
- `bb-browser` 真实页面 smoke：2026-05-08 Trendonify Trailing PE 页面显示 PE 38.07、10Y percentile 100；Forward PE 页面显示 Forward PE 23.73、5Y percentile 40、10Y percentile 57.5、20Y percentile 71.2。
- 自动 PE/PB/PS 百分位来源初筛：
  - Trendonify：当前最有价值，覆盖 NDX PE / Forward PE 及多窗口分位，但有 Cloudflare，建议 sidecar。
  - WorldPERatio：可自动读取 NDX PE、均值和标准差区间，但不是 percentile。
  - Koyfin：有历史 percentile rank 概念，偏登录/付费，适合人工或未来授权 connector，不宜伪装成公开自动源。
  - FinanceCharts：能看到 NDX 成分股 PE/PB/PS rank，偏横截面 rank，不是指数自身历史 PE/PB/PS percentile。

验证结果：

- `python3 -m pytest -q tests/test_l4_external_valuation_sources.py tests/test_research_console.py tests/test_manual_data_template.py`：12 passed。
- `python3 -m py_compile src/tools_L4.py src/research_console.py src/manual_data.py`：通过。
- `python3 src/research_console.py`：重新生成 `output/reports/vnext_research_console.html`。
- `python3 -m pytest -q`：114 passed，6 warnings。

剩余观察：

- 下一步若接入 `bb-browser`，应做成显式 sidecar：输出 URL、采集时间、页面文本摘要、解析字段、失败模式和人工确认标记；不得让 L4 主链在无提示情况下启动浏览器或绕过 Cloudflare。
- PB / PS 的可靠指数历史百分位仍未找到公开稳定自动源；当前更现实路径是 licensed/manual 或未来从成分股历史基本面构建自有指数级时间序列。

### 完成 NEXT_STEPS P0：L3 官方权重锚与 L4 forward earnings 质量

完成内容：

- 新增 L3 指标 `get_qqq_top10_concentration`：读取 Invesco QQQ 官方持仓 JSON，输出 Top10 / Top5 / Top3 / M7 权重、Top10 相对等权基准的超额权重、官方 `effective_date`、持仓来源和数据质量。
- 同一指标补充 QQQ 相对 QQEW 的 1M/3M/6M 表现差，用来明确区分“多数成分参与弱”和“头部权重股推动强”；集中度历史变化只作为价格回推 proxy，明确不伪装成官方历史权重。
- 新增 L4 指标 `get_ndx_forward_earnings_quality`：基于 yfinance 成分股模型输出 forward earnings yield、Forward EPS 增长代理、盈利/收入增长、利润率质量；M7 额外读取 next-year EPS trend，给出 30 日分析师修正方向。
- `get_ndx_pe_and_earnings_yield` 同步暴露 ForwardEarningsProxyUSD、ForwardEPSGrowthProxyPct、WeightedProfitMarginPct / GrossMargin / OperatingMargin 等字段，让既有估值指标也能带上未来盈利和 margin 质量。
- 更新 `TOOLS_REGISTRY`、DataCollector、packet builder、manual data 模板、IndicatorCanon、L3/L4 prompts 和 native brief 指标视觉，保证 v2 artifacts 与 brief 能直接消费新数据，不经过 legacy adapter。
- 检查已安装的 `bb-browser`：CLI 可用，支持 `fetch`、页面快照和登录态浏览器操作；本轮 Invesco 官方 JSON 端点可直接访问，因此没有把 `bb-browser` 接入主数据链。它仍适合后续 P2 隔离调研/sidecar 试验，不能绕过数据治理。

验证结果：

- `python3 -m pytest -q tests/test_l3_top10_concentration.py tests/test_l4_forward_earnings_quality.py tests/test_vnext_packet_builder.py tests/test_l4_external_valuation_sources.py`：17 passed。
- `python3 -m py_compile src/tools_L3.py src/tools_L4.py src/tools.py src/core/collector.py src/agent_analysis/packet_builder.py src/agent_analysis/vnext_reporter.py src/agent_analysis/deep_research_canon.py src/manual_data.py`：通过。
- `python3 -m pytest -q`：114 passed。
- 工具注册检查：`get_qqq_top10_concentration` 与 `get_ndx_forward_earnings_quality` 均已进入 `TOOLS_REGISTRY`。
- 真实 L3 smoke：Invesco QQQ 官方接口返回 `effective_date=2026-05-07`，Top10 权重 46.91%，M7 权重 40.16%，QQQ 近 1M 相对 QQEW 超额 4.68pct。

剩余观察：

- L4 全成分股 forward quality 仍依赖 yfinance 最新基本面和 M7 EPS trend，属于 component_model / proxy，不是官方 NDX aggregate EPS revision；若未来有 Wind/manual 高信任源，应优先覆盖。
- `bb-browser` 可以作为反爬或登录态页面的人工调研辅助，但不得直接进入主指标链。

### 完成本地运行服务、官方事件底账、L2 信用分层利差与 Impeccable 上下文

完成内容：

- 新增本地 `vNext control service` MVP：`src/control_service.py` 提供 `/health` 和 `/run`，只接受项目白名单 Python 命令，运行日志写入 `output/logs/control_service/`，避免静态 HTML 任意执行本地命令。
- 修复研究控制台“运行”按钮脚本初始化问题：`console-data` 改为可被 `JSON.parse` 正确读取的安全嵌入格式，避免按钮监听没有挂上。
- 控制台新增官方事件底账开关：勾选后命令追加 `--enable-news`，由主流水线写入独立 `news_event_ledger.json`。
- 新增 `src/news_event_ledger.py`：MVP 采集 Federal Reserve / BLS / BEA 官方 RSS 与 M7 SEC submissions，输出独立 sidecar artifact；不写入 L1-L5 runtime context。
- 移除旧 collector 内部新闻整合路径：新闻不再混入 `data_json["indicators"]`，保持数值指标与事件背景分离。
- 新增 L2 指标 `get_hy_quality_spread_bp`：计算 FRED / ICE BofA `BAMLH0A3HYC - BAMLH0A1HYBB`，即 CCC & Lower 高收益 OAS 减 BB 高收益 OAS。
- 将该指标纳入 `TOOLS_REGISTRY`、DataCollector L2、packet builder L2、IndicatorCanon、L2 prompt 和 workbench 波动信用模块。
- 补齐 `$impeccable` 所需 `PRODUCT.md` 与 `DESIGN.md`，并通过 context loader 确认 product/design 上下文可读取。register 明确为 `product`。
- 重新生成 `output/reports/vnext_research_console.html`。

验证结果：

- `python3 -m py_compile src/control_service.py src/news_event_ledger.py src/main.py src/tools_L2.py src/chart_time_series_artifacts.py src/research_console.py`：通过。
- `python3 -m pytest -q tests/test_control_service.py tests/test_news_event_ledger.py tests/test_l2_credit_quality.py tests/test_main_cli.py tests/test_research_console.py tests/test_chart_time_series_artifacts.py tests/test_deep_research_canon.py`：24 passed。
- `python3 -m pytest -q`：110 passed。
- `python3 src/news_event_ledger.py --output /tmp/news_event_ledger_test.json --no-sec --max-events-per-source 1`：生成 1 条官方 RSS 事件。
- `node /Users/aidianchi/.agents/skills/impeccable/scripts/load-context.mjs`：`hasProduct=true`，`hasDesign=true`。

剩余观察：

- `control_service` 现在是本机 MVP，还没有浏览器侧二次确认弹窗、任务取消、运行状态轮询和历史任务 UI。
- 新闻事件底账当前只做权威来源访问与结构化，不做摘要、情绪、LLM 解读，也不进入 Bridge/Thesis。
- L4 prompt 约 18 万字符在 1M 上下文模型中可接受，但仍有重复和成本问题；后续应做 prompt 专用摘要，而不是把完整月度序列重复塞入 manifest 与 raw payload。
- OpenBB 本轮按用户判断暂缓，不纳入主链路。

## 2026-05-07

### 修复 workbench 对齐、模块切换读数和 QQQ 数据窗口

完成内容：

- 修复 L5 workbench 主图与 Volume、OBV、MACD、RSI/ATR、MFI/CMF 副图纵向轴线不齐：所有 Lightweight chart 统一右侧价格刻度最小宽度，绘图区右边界现在保持一致。
- 修复模块切换后的上下文错位：切换到波动信用、利率估值、广度集中度、流动性时，顶部摘要改为对应 layer 的精简分析，不再停留在 L5。
- 修复模块 crosshair 读数：L5 继续显示 OHLC、Volume、OBV、MACD、RSI、ATR、MFI、CMF；非 L5 模块显示当前模块序列读数，并对低频序列显示最近可用值。
- QQQ 图表数据默认窗口从约 420 天扩展到 1825 天；最新 `chart_time_series.json` 中 QQQ 为 1254 行，覆盖 2021-05-10 至 2026-05-06。页面仍默认显示 1Y，ALL 可查看完整 5 年窗口。
- 控制台新增“运行”按钮：按钮调用本机 `127.0.0.1:8765` vNext control service；服务未启动时明确提示没有执行命令，保留安全边界。
- 重新生成 `output/reports/vnext_interactive_charts_20260506_controls.html`、`output/reports/vnext_research_console.html` 和 `output/reports/visual_regression/20260507_workbench_fix/`。

验证结果：

- `python3 -m pytest -q tests/test_interactive_chart_workbench.py tests/test_research_console.py tests/test_chart_time_series_artifacts.py`：6 passed。
- `python3 src/report_visual_regression.py --brief-html output/reports/vnext_research_ui_brief_20260505_20260506_075229.html --workbench-html output/reports/vnext_interactive_charts_20260506_controls.html --output-dir output/reports/visual_regression/20260507_workbench_fix`：passed。
- 额外生成 tall workbench 截图确认纵轴和副图对齐：`output/reports/visual_regression/20260507_workbench_fix/workbench_tall.png`。
- 额外生成控制台截图确认运行按钮位置：`output/reports/visual_regression/20260507_workbench_fix/console_desktop.png`。

剩余观察：

- 控制台已有运行入口，但本地 control service 本体尚未实现；下一步若继续做一键运行，应先做 allowlist、显式确认、运行日志和失败恢复。
- workbench 现在解决了对齐和读数语义；后续更专业的方向是增加 navigator、pane 高度调整和指标参数编辑。

---

## 2026-05-06

### 修复 workbench 与研究控制台页面批注

完成内容：

- 修复 workbench 副图布局：Volume、OBV、MACD、RSI/ATR、MFI/CMF 从并列小图改为全宽纵向 pane，避免不同副图横轴宽度和起止日期观感不一致。
- 修复 workbench 默认时间窗口：所有 pane 初始化后统一到同一 1Y 时间窗口；ALL/3M/6M/1Y 按真实日期范围同步，而不是让各副图按自身数据 fitContent。
- 修复副图对齐：去掉副图容器内边距，把标题浮在图内左上角，主图和副图的绘图区宽度更接近。
- 修正研究控制台“运行模式”语言：从 full/data only/report only 等旧式流程词，改为完整 vNext、只采集数据、已有数据分析、只生成 brief、只生成 workbench、视觉回归。
- 重排人工估值字段：PE、PB、PS 分别成组，每组把当前值、5Y 分位和 10Y 分位放在一起；JSON 预览同步写入对应字段。
- 明确 legacy HTML 边界：控制台改为“不生成旧版 HTML / 不生成旧版 charts”，并标注旧版 HTML 是过渡期兼容产物，默认入口应是 native brief 和 workbench。

验证结果：

- `python3 -m pytest -q tests/test_interactive_chart_workbench.py tests/test_research_console.py`：4 passed。
- 重新生成 `output/reports/vnext_interactive_charts_20260506_controls.html` 和 `output/reports/vnext_research_console.html`。
- `python3 src/report_visual_regression.py --brief-html output/reports/vnext_research_ui_brief_20260505_20260506_075229.html --workbench-html output/reports/vnext_interactive_charts_20260506_controls.html --output-dir output/reports/visual_regression/20260506_review_fix`：passed。
- 额外生成 tall workbench 截图确认副图全宽纵向对齐：`output/reports/visual_regression/20260506_review_fix/workbench_tall.png`。

剩余观察：

- workbench 的时间轴同步已经按日期范围统一，但更接近 TradingView 的独立 pane 管理还可以继续加入拖拽排序、pane 高度调整和指标参数编辑。

---

### 完成 workbench 操作化与研究控制台总控重构

完成内容：

- 先将既有成果快进合入 `main` 并推送到 GitHub，提交为 `e1a6f5b Advance vNext workbench and console planning`。
- 按用户对 workbench 的两个批注，重构 L5 价格技术工作台交互：默认只显示 Candles、MA20、MA200，避免主图全指标过载。
- 新增 L5 指标显隐和图例点击切换：Candles、MA5/20/60/200、Bollinger、Donchian、VWAP、Volume overlay 可独立启停。
- 新增指标预设：简洁价格、趋势均线、波动区间、量价确认、全部指标；预设写入 localStorage，不改变 run artifact。
- 新增时间轴锁定/解锁和统一时间轴：锁定时主图、副图和模块图共享 visible logical range；解锁后可局部检查，再一键统一。
- 新增跨 pane readout：主图或副图移动 crosshair 时，右侧统一展示 OHLC、Volume、OBV、MACD hist、RSI、ATR、MFI、CMF。
- 新增副图启停：Volume、OBV、MACD、RSI/ATR、MFI/CMF 均可折叠，移动端保持单列。
- 非 L5 模块新增序列图例显隐、归一化和双轴控制，覆盖波动信用、利率估值、广度集中度、流动性模块。
- 重构研究控制台为六区总控：运行对象与日期、人工/Wind 数据、模型与运行模式、数据源/功能开关、输出与工作台、运行日志/健康/安全。
- 人工数据输入从纯 JSON 文本升级为结构化表单，支持 PE/PB/PS/ERP/percentile/date/source/confidence；保留高级 JSON 预览和下载。
- 控制台新增 full、data only、analysis only、draft only、report only、quick report 运行模式，新增 flash 优先、pro only、自定义顺序模型策略。
- 控制台纳入新闻源预留、Trendonify 暂缓、legacy charts opt-in、workbench 模块、L5 默认预设、最新 brief/workbench/run/visual regression 入口。
- 控制台明确一键运行安全方案：后续若做本地 control service，必须有 allowlist、显式确认、日志、失败恢复和项目路径白名单。

验证结果：

- `python3 -m pytest -q tests/test_interactive_chart_workbench.py tests/test_research_console.py`：4 passed。
- 重新生成 workbench：`output/reports/vnext_interactive_charts_20260506_controls.html`。
- 重新生成控制台：`output/reports/vnext_research_console.html`。
- `python3 src/report_visual_regression.py --brief-html output/reports/vnext_research_ui_brief_20260505_20260506_075229.html --workbench-html output/reports/vnext_interactive_charts_20260506_controls.html --output-dir output/reports/visual_regression/20260506_controls`：passed，desktop/mobile 截图和 layout checks 均 ok。
- 额外生成控制台 desktop/mobile 截图：`output/reports/visual_regression/20260506_controls/console_desktop.png`、`output/reports/visual_regression/20260506_controls/console_mobile.png`。

剩余观察：

- data only 运行模式在控制台已有入口，但当前 `src/main.py` 还没有真正拆出独立 collector-only 命令；控制台已明确标注需要后续本地 control service 或 CLI 拆分。
- 非 L5 模块已经可控，但更专业的宏观图还可以继续引入 navigator、收益差距专用面板和单位标注增强。

---

### 完成阶段收尾知识同步

完成内容：

- 使用 `neat-freak` 盘点 Codex 全局配置、项目根 Markdown、`docs/` 历史文档和当前输出体验文档；确认 `~/.codex/AGENTS.md` 为空，当前没有独立记忆索引需要同步。
- 更新 `README.md`，补充研究控制台、交互 workbench、视觉回归命令和当前输出入口。
- 更新 `AGENTS.md`，补充 `chart_time_series_artifacts.py`、`interactive_chart_workbench.py`、`research_console.py`、`report_visual_regression.py` 等关键路径，并明确 UI 改动要区分 brief、图表层和 workbench。
- 更新 `ARCHITECTURE.md`，记录 2026-05-06 多模块 workbench、控制台边界和下一轮交互重点。
- 更新 `DATA_COVERAGE_REVIEW.md`，把数据覆盖复盘推进到 2026-05-06 最新 run，明确 Damodaran 月度 ERP、WorldPERatio、L5 量价质量和 Trendonify 缺口。
- 更新 `PLAIN_LANGUAGE_OUTPUT_EXPERIENCE_REVIEW.md`，补充多模块 workbench、控制台总控方向、视觉回归布局检查和下一轮观察点。
- 清理当前受审文档中的相对时间词，改为绝对日期或“当日/目标日期”。

剩余观察：

- `docs/` 下多份 2026-04-24/2026-04-25 文档是历史研究记录，本轮只修正相对时间词，不把后续实现倒灌进历史报告。
- 本轮是文档同步，没有修改运行代码。

---

### 完成 workbench 与研究控制台下一轮设计复盘

完成内容：

- 复核用户对 `vnext_interactive_charts_20260506_modules.html` 的两个批注：主图指标全开导致视觉过载；主图和副图需要更强的共享时间轴、联动读数和“一键统一”能力。
- 查阅一手图表资料后形成取舍：当前继续以 Lightweight Charts 为主，因为它足以支持 visible range 控制和 pane 同步；TradingView Advanced Charts 虽然指标/模板能力强，但官方限制不适合作为当前默认依赖；Highcharts Stock 和 ECharts 分别作为 navigator/range selector、多轴宏观图的后续参照。
- 审阅旧 `/Users/aidianchi/Desktop/launcher.py`，提取有价值功能线索：人工 L4 输入、历史日期、运行模式、模型顺序、API 配置、新闻开关、图表叠加模式和本地任务启动。
- 更新 `NEXT_STEPS.md`，新增两组下一步：
  - workbench：指标显隐、预设模板、时间轴锁定/解锁、统一时间轴、联动 crosshair、副图折叠、非 L5 模块 legend/normalize/dual-axis、交互回归测试。
  - 研究控制台：信息架构重构、结构化人工数据输入、运行模式、模型策略、功能开关、报告/artifact 入口、一键运行安全方案、视觉重设计。

剩余观察：

- 这次只做规划与审视，未修改 workbench/控制台运行代码。
- 下一轮若进入实现，建议先做 workbench 的指标显隐和时间轴锁定，因为它直接回应用户批注，也能最快验证“看盘台”方向是否成立。

---

### 完成 NEXT_STEPS 2-7：多模块 workbench、同源时序数据和回归增强

完成内容：

- 按用户指示暂缓 Trendonify 可用性问题，只推进 NEXT_STEPS 2-7。
- 固化 workbench 双层分类原则：底稿/审计继续按 L1-L5；交互 workbench 按价格技术、波动信用、利率估值、广度集中度、流动性组织，同时保留每条序列的 Layer、function_id、provider 和 frequency。
- 扩展 `chart_time_series.json`：除 QQQ OHLCV 外，新增 VIX、VXN、VXN/VIX、HY/IG OAS、HYG、10Y、10Y real、10Y breakeven、Fed funds、Damodaran ERP monthly、QQQ/QQEW、net liquidity、WALCL、TGA、RRP、M2 YoY。
- 升级 L5 价格技术工作台：主图支持 K 线、MA5/20/60/200、Bollinger、Donchian、VWAP；副图支持 Volume、OBV、MACD、RSI、ATR、MFI、CMF；区间按钮同步主图和副图。
- 重构 workbench 为研究模块选择器：页面提供模块 tabs；控制台新增模块勾选，并生成 `--modules` workbench 命令。
- 增加 DeepSeek/LLM 阶段诊断：`llm_stage_diagnostics.json` 会记录 stage、attempts、parse/schema/contract errors、raw_excerpt、prompt_chars，后续可直接复盘 JSON parse retry 和 coverage retry。
- 增强视觉回归：`visual_regression_summary.json` 新增 `layout_checks`，检测明显固定宽度超视口和移动端内联 nowrap 风险。
- 生成最新多模块 workbench：`output/reports/vnext_interactive_charts_20260506_modules.html`；重新生成控制台：`output/reports/vnext_research_console.html`。

验证结果：

- 测试先行：新增失败测试覆盖多面板 artifact、workbench 模块与副图、控制台模块选择、视觉回归布局检查、LLM retry diagnostics。
- `python3 -m pytest tests/test_chart_time_series_artifacts.py tests/test_interactive_chart_workbench.py tests/test_research_console.py tests/test_report_visual_regression.py tests/test_vnext_orchestrator.py::test_run_stage_records_parse_retry_diagnostics -q`：11 passed，4 warnings。
- `python3 -m py_compile src/chart_time_series_artifacts.py src/interactive_chart_workbench.py src/research_console.py src/report_visual_regression.py src/agent_analysis/orchestrator.py src/main.py`：通过。
- 使用最新 run `output/analysis/vnext/20260506_075229` 重新写入 `chart_time_series.json`，确认多模块序列均落盘，Damodaran monthly 为 120 行。
- `python3 src/report_visual_regression.py --brief-html output/reports/vnext_research_ui_brief_20260505_20260506_075229.html --workbench-html output/reports/vnext_interactive_charts_20260506_modules.html --output-dir output/reports/visual_regression/20260506_modules`：passed，desktop/mobile 截图和 layout checks 均 ok。

剩余观察：

- Trendonify 仍按用户要求暂停，不在本轮解决。
- 新 workbench 已能表达 5 个研究模块，但非 L5 模块目前以多线图为主，后续可继续增加双轴、归一化切换、drawdown overlay 和更强的 crosshair 联动。
- L4 token 膨胀已开始被 diagnostics 量化，但真正压缩 L4 prompt/packet 仍是后续工作。

---

### 完成 NEXT_STEPS：最新真实 run、视觉回归、legacy chart 降为显式 opt-in

完成内容：

- 修复 Damodaran 默认日期选择：当目标日期不是月初时，`ERPbymonth.xlsx` 会选择不晚于目标日期的最新月度行；2026-05-06 默认可正确落到 2026-05-01。
- 重新采集实时数据并保存 `output/data/data_collected_20260506_live.json`；确认 Damodaran `ERPbymonth.xlsx` / `ERPMay26.xlsx`、`monthly_series=120` 和 WorldPERatio 结构化相对位置进入 packet。
- 用新采集数据完成真实 DeepSeek smoke：`output/analysis/vnext/20260506_075229`，Final 为“中性偏谨慎”，审批状态 `approved_with_reservations`。
- 生成最新 native brief：`output/reports/vnext_research_ui_brief_20260505_20260506_075229.html`；生成最新交互 workbench：`output/reports/vnext_interactive_charts_20260506.html`。
- 新增 L5 `get_price_volume_quality_qqq` 指标微图，展示 VWAP 偏离、MFI 和 CMF，最新 brief 指标级微图数量从 29/30 提升到 30。
- 新增 `src/report_visual_coverage.py`，输出每层指标级微图覆盖审计；最新覆盖为 L1 7/8、L2 8/9、L3 5/6、L4 3/3、L5 7/9。
- 新增 `src/report_visual_regression.py`，用 Chrome headless 对 brief/workbench 做 desktop/mobile 截图回归；同时修复移动端 verdict card 和长风险文本挤压。
- 调整 native brief 默认文件名：当 `data_date` 重复时追加 run id，避免不同 run 覆盖同名报告。
- legacy Plotly charts 从默认主路径退出：`src/main.py` 默认关闭 legacy charts，只有显式 `--enable-legacy-charts` 才开启旧 HTML 图表。

验证结果：

- `python3 src/main.py --models deepseek-v4-flash,deepseek-v4-pro --data-json output/data/data_collected_20260506_live.json --skip-report`：完成真实 DeepSeek run。
- `python3 src/report_visual_coverage.py --run-dir output/analysis/vnext/20260506_075229 --html output/reports/vnext_research_ui_brief_20260505_20260506_075229.html --output output/reports/visual_regression/20260506_final/visual_coverage_20260506_075229.json`：通过，输出 30 个指标级微图覆盖。
- `python3 src/report_visual_regression.py --brief-html output/reports/vnext_research_ui_brief_20260505_20260506_075229.html --workbench-html output/reports/vnext_interactive_charts_20260506.html --output-dir output/reports/visual_regression/20260506_final`：passed。
- in-app browser 检查：`#evidence-L5-get_price_volume_quality_qqq` 自动展开 L5 并高亮；workbench 显示数据源 `chart_time_series.json · yfinance via chart_adapter_v6`，主图可见。

剩余观察：

- Trendonify 在最新采集里仍不可用，不能宣称自动历史估值分位已完整解决。
- 视觉回归当前能产出桌面/移动截图并验证 PNG 非空，但自动 layout overflow 检测仍可继续加强。
- 两次真实 run 暴露模型输出稳定性问题：旧数据 run 有 L1/L2 JSON parse retry、L5 coverage retry；新数据 run 成功但 L4 输入达到约 59k tokens，应继续压缩。

---

## 2026-05-05

### 推送当前版本，并继续落地指标级可视化后的下一轮观察

完成内容：

- 将当前数据源审计、native brief 图表、指标级微图、研究控制台和 Lightweight workbench 原型提交到 Git，并推送到 GitHub 分支 `claude/20260503-vnext-brief-redesign`。
- 创建草稿 PR：`https://github.com/aidianchi/NDX_VNEXT/pull/1`，方便后续人工或 AI 审查。
- 明确图表三层架构：底稿微图负责指标速读，市场总览图负责跨层压力/共振，Lightweight workbench 负责看盘式交互探索。
- 新增 `chart_time_series.json` artifact 写入路径：vNext run 会保存 QQQ OHLCV、成交量和 MA5/20/60/200；workbench 优先读取同一 run 的 artifact，避免图表与文字来自不同抓取时点。
- 修复 evidence hash 直达：打开 `#evidence-Lx-...` 会自动展开对应 Layer、滚动到指标卡并高亮，证据链接更适合审查和分享。

验证结果：

- 提交前全量测试：`python3 -m pytest -q` 为 89 passed，6 warnings。
- 本轮新增行为先写失败测试，再实现：hash 直达、workbench artifact 优先读取、`chart_time_series.json` 写入均有测试覆盖。
- 定向测试：`python3 -m pytest tests/test_chart_time_series_artifacts.py tests/test_interactive_chart_workbench.py tests/test_vnext_reporter.py::test_vnext_reporter_generates_native_ui -q` 为 4 passed，4 warnings。

---

### 调研并落地交互式看盘图原型：Lightweight Charts Workbench

完成内容：

- 复核当前指标微图边界：它们适合底稿速读，但不适合看盘式探索；需要把“连续阅读报告”和“交互图探索”分成两层。
- 查阅并比较一手资料后，选择 TradingView Lightweight Charts 作为第一版看盘式原型依赖；它比 Plotly 更接近金融主图手感，比 ECharts 更适合 K 线/均线/成交量这类时间序列探索。
- 本地安装 `lightweight-charts@5.2.0`，并把 `node_modules/` 加入 `.gitignore`，避免依赖目录污染版本管理。
- 新增 `src/interactive_chart_workbench.py`，生成独立交互图页面 `output/reports/vnext_interactive_charts_20260502.html`：包含 QQQ K 线、成交量、MA5/20/60/200、区间按钮、crosshair readout 和 L5 摘要。
- 修复 native brief 的 JSON payload 嵌入方式：不再把 `<script type="application/json">` 内的 JSON 转成 HTML entity，避免浏览器端 `JSON.parse` 失败影响证据抽屉和跳转。

验证结果：

- `npm view lightweight-charts version license dist.unpackedSize --json`：确认当前版本 5.2.0，Apache-2.0。
- `npm install --no-save lightweight-charts@5.2.0`：成功安装。
- `python3 -m pytest -q tests/test_vnext_reporter.py tests/test_interactive_chart_workbench.py`：6 passed，4 warnings。
- `python3 -m py_compile src/agent_analysis/vnext_reporter.py src/interactive_chart_workbench.py`：通过。
- `python3 src/interactive_chart_workbench.py --run-dir output/analysis/vnext/20260502_193057 --lookback-days 420`：生成 `output/reports/vnext_interactive_charts_20260502.html`。
- in-app browser 检查：交互图页面无当前页面脚本错误；K 线、均线、成交量和 3M/6M/1Y/ALL 区间按钮可见。

---

### 完成 L1-L5 指标级可视化：底稿旁微图与复杂指标展开图

完成内容：

- 从第一性原理重新审视 L1-L5 的全部指标：优先图表化“相对位置、均线/基准偏离、组成项、广度结构、集中度、估值源分歧、技术区间和资金流确认”，不把没有结构信息的单点文字硬画成图。
- 在 native `brief` 的五层底稿指标卡内新增轻量内联微图，直接消费本次 `analysis_packet.raw_data`，不接回 legacy Plotly chart 管线，也不重新联网拉取另一批数据。
- 覆盖主要图表族：历史分位/5Y/10Y/z-score 位置尺、均线基准对照、净流动性组成项、Fear & Greed 分项、拥挤度组件、广度参与条、M7 基本面热力格、L4 估值源校验、Damodaran 当前 ERP lens、收益差距压力尺、L5 技术 dashboard、MA ladder、MACD、OBV、成交量和 Donchian channel。
- 对复杂指标采用可展开图：例如 Fear & Greed 默认展开，M7 基本面默认折叠，避免五层底稿被大图撑散。
- 旧 run `output/analysis/vnext/20260502_193057` 重新生成后，`output/reports/vnext_research_ui_brief_20260502.html` 包含 29 个指标级可视化。

验证结果：

- 先写失败测试 `test_vnext_reporter_renders_indicator_level_visuals`，确认旧报告没有指标级微图；实现后该测试通过。
- `python3 -m pytest -q tests/test_vnext_reporter.py`：5 passed，4 warnings。
- `python3 -m py_compile src/agent_analysis/vnext_reporter.py`：通过。
- `python3 src/agent_analysis/vnext_reporter.py --run-dir output/analysis/vnext/20260502_193057 --template brief`：重新生成默认 brief 报告。
- in-app browser 检查：报告中存在 29 个 `data-indicator-visual`，L1 底稿指标卡可见分位尺、z-score 和净流动性组成项；复杂指标以 details 呈现。

---

### 完成输出体验 4-5 步：报告图表一等公民和研究控制台第一屏

完成内容：

- 在 native `brief` 报告中新增“市场图谱”章节，直接消费 vNext artifacts 与 `analysis_packet.raw_data`，不回退到 legacy chart 叙事。
- 新增四类报告内原生图表：L4 估值相对位置尺、Damodaran ERP 月度路径、WorldPERatio 窗口标签、L1-L4 利率估值压力图；每张图绑定 evidence refs，可继续打开指标底稿。
- Damodaran 月度解析器保留 `monthly_series`，未来真实 run 可直接画 `ERPbymonth.xlsx` 的 ERP / 10Y / expected return 月度线图；旧 artifact 没有月度序列时会展示单点读数和边界说明。
- 新增 `src/research_console.py`，生成 self-contained 第一屏控制台 `output/reports/vnext_research_console.html`，覆盖人工/Wind 输入、flash/pro 模型选择、数据源健康、运行命令、报告入口和人工模板保存。
- 补充通俗说明：`PLAIN_LANGUAGE_OUTPUT_EXPERIENCE_REVIEW.md`，记录参考 TradingView、Bloomberg、Koyfin 和 FT 图表词汇后的取舍。

验证结果：

- `python3 -m pytest -q tests/test_vnext_reporter.py tests/test_research_console.py tests/test_l4_data_authority.py`：14 passed，4 warnings。
- `python3 -m py_compile src/agent_analysis/vnext_reporter.py src/research_console.py src/tools_L4.py`：通过。
- `python3 src/agent_analysis/vnext_reporter.py --run-dir output/analysis/vnext/20260502_193057 --template brief`：生成 `output/reports/vnext_research_ui_brief_20260502.html`。
- `python3 src/research_console.py`：生成 `output/reports/vnext_research_console.html`。
- Chrome headless 截图检查报告首页和控制台首页可渲染；Python/Node Playwright 均未安装，因此未做 Playwright 自动交互验收。

---

### 完成 L4 数据源复盘 1-3 步：Damodaran 月度 ERP、WorldPERatio 相对位置和 L4 边界

完成内容：

- 重构 Damodaran 官方 ERP 获取优先级：优先读取 `ERPbymonth.xlsx`，并尝试读取当月 `ERP<Month><YY>.xlsx`；`histimpl.xls` 降级为年度历史 fallback。
- 新增无 `openpyxl` 也可工作的轻量 `.xlsx` 解析兜底，并处理 Damodaran 工作簿的 `Start of month` 日期列和 1904 日期系统。
- Damodaran 输出扩展为多口径字段：`erp_t12m_adjusted_payout`、`erp_t12m_cash_yield`、`erp_avg_cf_yield_10y`、`erp_net_cash_yield`、`erp_normalized_earnings_payout`、`us_10y_treasury_rate`、`default_spread`、`adjusted_riskfree_rate`、`expected_return`、`source_file`、`data_date`。
- 扩展 WorldPERatio parser：保留 PE、日期和显式 percentile 规则，同时结构化 rolling average、std dev、range、deviation vs mean、valuation label、SMA50/200 margin；这些字段进入 `relative_position`，明确不是历史分位。
- 更新 L4 packet builder、prompt 和 few-shot：模型可以使用 WorldPERatio 的 `std-dev / z-score relative context` 描述相对位置，但不能写成 percentile；Damodaran 明确区分 monthly current ERP 与 annual history fallback。

验证结果：

- 真实官网 smoke：`get_damodaran_us_implied_erp("2026-05-01")` 成功读取 `ERPbymonth.xlsx` 的 2026-05-01 月度 ERP，并合并 `ERPMay26.xlsx` 的 default spread / expected return。
- 真实 smoke 关键值：T12m adjusted payout 4.24%、T12m cash yield 4.36%、10 年平均 CF yield 6.36%、net cash yield 4.15%、normalized 3.73%、10Y Treasury 4.40%、default spread 0.26%、adjusted riskfree 4.14%、expected return 8.55%。
- `python3 -m pytest tests/test_l4_data_authority.py tests/test_l4_external_valuation_sources.py tests/test_vnext_packet_builder.py tests/test_prompt_guardrails.py -q`：29 passed，4 warnings。
- `python3 -m pytest -q`：86 passed，6 warnings。

---

## 2026-05-04

### 完成 P1：L5 公式层和轻量数据 fallback 收口审阅

完成内容：

- 复核 L5 当前实现，确认主路径仍是稳定的 yfinance 日频 OHLCV，`ta` 只作为公式层标准化引擎；内部 fallback 继续保留，不改变既有数据源优先级。
- 复核 pandas-datareader 轻量 fallback，维持只用于 FRED 公开 CSV/reader 备用路径；不把 Fama-French、Nasdaq symbols 或 Stooq 接入主流程，避免扩大不稳定面。
- 从第一性原理审阅 VWAP / MFI / CMF：三者有必要保留为 L5 量价质量验证，因为它们分别回答“价格相对成交量加权成本”“带成交量的动能拥挤”“收盘位置与成交量形成的积累/派发压力”。但它们只提高或降低趋势质量置信度，不能单独给买卖结论，也不能证明估值合理。
- 补齐 `get_price_volume_quality_qqq` 的 vNext 原生消费路径：进入 `LAYER_FUNCTIONS["L5"]`，加入 deep research canon、L5 prompt 指标语义、few-shot 示例和 legacy alias。
- 修正 packet builder 对 VWAP/MFI/CMF 复合值的压缩方式，确保三件套在 L5 core signal 中不会被截掉。

验证结果：

- `python3 -m py_compile src/tools_L5.py src/tools_common.py src/agent_analysis/packet_builder.py src/agent_analysis/deep_research_canon.py src/prompt_examples.py`：通过。
- `python3 -m pytest tests/test_ta_l5_and_pdr_sources.py tests/test_vnext_packet_builder.py tests/test_deep_research_canon.py -q`：21 passed。
- `python3 -m pytest -q`：81 passed，6 warnings。

---

## 2026-05-03

### 完成输出体验第一轮结构改造，并记录用户验收反馈

完成内容：

- 为默认 `brief` 页面做了一轮原生输出体验改造：阅读顺序调整为判断、依据、风险、冲突、底稿、治理、审计。
- 增加证据详情抽屉、风险边界区、五层摘要卡、历史分位尺和更清晰的证据 ref 归一化，目标是让用户能从结论追到指标、来源、反证和完整底稿。
- 生成并覆盖默认 brief 页面：`output/reports/vnext_research_ui_brief_20260502.html`；未重新运行 DeepSeek，全程沿用已有 run `output/analysis/vnext/20260502_193057`。
- 补充输出体验设计报告：`OUTPUT_EXPERIENCE_DESIGN_REPORT.md`。

用户验收反馈：

- 这版不是终版，距离理想效果仍有明显差距。
- 当前审美方向不被接受，尤其主视觉配色不应继续作为默认方向。
- 五层底稿区域的点击/展开/跳转动效有问题，用户感知为无法顺畅跳转或展开。
- 后续只记录方向：审美美化待重新指明方向；交互、展开、跳转反馈和图表/数据打开体验待继续优化。

验证结果：

- `python3 -m py_compile src/agent_analysis/vnext_reporter.py`：通过。
- `python3 src/agent_analysis/vnext_reporter.py --run-dir output/analysis/vnext/20260502_193057 --template brief`：通过。
- `python3 -m pytest tests/test_vnext_reporter.py -q`：1 passed。
- `python3 -m pytest -q`：76 passed。
- 静态 HTML 检查确认 section 顺序、证据抽屉、风险区和分位尺存在，证据 ref 无缺失匹配。

---

## 2026-05-02

### 创建 P1 分支并落地 L5/数据源补强

完成内容：

- 创建分支 `codex/p1-ta-datareader-l5`，用于后续确认后再合并。
- L5 技术指标公式层优先使用 `ta`：SMA、RSI、Bollinger、ATR、MACD、OBV、Donchian、ADX 等统一进入更标准的公式路径，同时保留内部 fallback。
- 新增 `QQQ Price-Volume Quality`：VWAP(20)、MFI(14)、CMF(20)，用于量价质量验证；它们只辅助判断价格与成交量/资金流是否一致，不单独给买卖结论。
- pandas-datareader 只落地 FRED 公开 CSV fallback：当 FRED API key 缺失或 JSON API 不可用时，L1/L2/L4 的 FRED 序列仍可读。
- 真实试用发现 pandas-datareader 在当前 pandas 3 环境下较老：FRED 路径可用；Fama-French、Nasdaq symbols 和 Stooq 当前不够稳，未纳入主流程。
- `NEXT_STEPS.md` 补入 P1 路线，并用简短语言把 OpenBB 和 vectorbt 的启示放到靠后观察项。

验证结果：

- `.venv/bin/python -m pip install 'ta>=0.11.0' 'pandas-datareader>=0.10.0'`：成功安装。
- `.venv/bin/python -m pytest tests/test_ta_l5_and_pdr_sources.py -q`：3 passed。
- `.venv/bin/python -m pytest tests/test_ta_l5_and_pdr_sources.py tests/test_l3_breadth_data.py tests/test_l4_external_valuation_sources.py -q`：17 passed。
- `.venv/bin/python -m pytest -q`：76 passed。
- 真实导入检查：`ta=True`、`pandas-datareader=True`、`get_price_volume_quality_qqq` 已注册；FRED `DGS10` fallback 可读取 2026-04-01 至 2026-04-10 数据。

---

### 完成四个 GitHub 金融库对 vNext 的外部能力研究

完成内容：

- 使用 GitHub skill 研究 OpenBB、`ta`、vectorbt、pandas-datareader 四个仓库的 README、核心代码、依赖、数据 provider、MCP/API/回测/指标能力。
- 对照本仓库 `AGENTS.md`、`ARCHITECTURE.md`、`NEXT_STEPS.md`、`DATA_COVERAGE_REVIEW.md` 和当前 `tools_L5.py`，判断四个库应分别作为数据接入架构参考、L5 公式引擎参考、离线实验室和轻量数据 reader。
- 形成通俗但专业的报告：`PLAIN_LANGUAGE_GITHUB_REPO_RESEARCH.md`。

核心结论：

- OpenBB 不宜整体并入主链，但其 provider schema、OBBject metadata、MCP discovery 和扩展机制值得借鉴。
- `ta` 适合帮助 L5 标准化技术指标公式，但不能替代 vNext 对技术信号的解释、边界和跨层 hook。
- vectorbt 适合作为离线实验/回测风洞，不应直接污染 L1-L5 runtime context。
- pandas-datareader 适合补 FRED、Fama-French、Stooq、Nasdaq symbols 等轻量 reader，不适合作总数据平台。

验证方式：

- 通过 GitHub connector 拉取四个仓库元信息和关键文件。
- 对 `ta`、vectorbt、pandas-datareader 做浅克隆并本地检索核心代码结构。
- OpenBB 仓库体量较大，主要使用 GitHub connector 读取 README、Platform/Core/MCP/extension 文档和关键 provider 文件。

---

### 完成 NEXT_STEPS 1/2：DeepSeek 真实 run 与默认 brief 页面

完成内容：

- 使用最新代码完成一轮 DeepSeek 真实数据运行，生成 run：`output/analysis/vnext/20260502_193057`。
- 使用该 run 生成默认 `brief` 页面：`output/reports/vnext_research_ui_brief_20260502.html`。
- L4 数据发言权在真实 artifacts 中生效：WorldPERatio 作为第三方 PE 校验源可用，Trendonify PE / Forward PE 403 被明确记录为 `unavailable`，Damodaran 官方 Excel 作为美国市场 implied ERP 背景锚可用。
- L4 主口径保持克制：yfinance 成分模型给出当前 PE / Forward PE / FCF Yield / PB 和覆盖率，但没有生成历史分位；简式收益差距继续明确标注为 `FCF yield - 10Y`，不是 Damodaran implied ERP。
- L3 四件套在真实运行中均可用，`brief` 页面能展示 A/D Line、% Above MA、New Highs/Lows 和 McClellan 的来源、覆盖率和当前读数。
- `NEXT_STEPS.md` 已移除已完成的真实 run 和 brief 生成事项，保留后续 Trendonify 可用路径观察和 brief 阅读卡点记录。

真实源检查：

- DeepSeek：使用 `deepseek-v4-flash` 完成全链路，`deepseek-v4-pro` 未触发；最终立场为“中性偏谨慎（风险收益比不利）”，审批状态 `approved_with_reservations`。
- WorldPERatio：Nasdaq 100 PE = 32.27，数据日期 `01 May 2026`，无 explicit percentile/rank，因此历史百分位保持缺失。
- Trendonify：Trailing PE 和 Forward PE 页面均返回 403 Forbidden，系统记录不可用原因，没有 fallback 到 yfinance。
- Damodaran：官方 Excel 可用，最新行为 2025，`implied_erp_fcfe = 4.23%`，`implied_erp_ddm = 1.69%`，`tbond_rate = 4.18%`，来源等级 `official`。
- yfinance 成分模型：Trailing PE = 33.83，Forward PE = 23.15，FCF Yield = 1.55%，PB = 35.6；Trailing PE 市值覆盖 97.99%，Forward PE 市值覆盖 99.84%，FCF Yield 市值覆盖 99.63%，PB 市值覆盖 98.99%。
- 简式收益差距：-2.85%，基于 NDX FCF Yield 1.55% 减 10Y Treasury 4.4%。
- L3 广度：A/D Line 488 且趋势 `rising`；50 日线上方 65.35%，200 日线上方 56.44%；52 周新高 14 只、新低 1 只；McClellan 1.52。

验证结果：

- `python3 src/main.py --models deepseek-v4-flash,deepseek-v4-pro --skip-report --disable-charts`：成功生成 `output/analysis/vnext/20260502_193057`。
- `python3 src/agent_analysis/vnext_reporter.py --run-dir output/analysis/vnext/20260502_193057 --template brief`：成功生成 `output/reports/vnext_research_ui_brief_20260502.html`。
- 页面抽查确认包含 WorldPERatio、Trendonify 403、Damodaran、来源等级、覆盖率、不可用原因和“简式收益差距不是 implied ERP”的说明。

---

### 审计并修正 L3 广度四件套

完成内容：

- 确认 L4 口径判断，并写入 `NEXT_STEPS.md`：人工/Wind 的 PE、PB、PS、ERP 及 5/10 年分位是最高信任主锚；Trendonify 是有价值的自动分位来源但 403 时只记录待解决；WorldPERatio 的 PE、均值、标准差和估值区间可与人工数据互参，但不能伪造成历史分位；Damodaran 只做美国市场背景锚；yfinance 只做当前值和覆盖率校验。
- 修正 `New Highs/Lows` 的真实数据窗口：从共享 300 自然日窗口改为请求更长窗口，避免实际只有约 208 个交易日时无法计算 252 日新高新低。
- L3 状态识别现在能把 A/D Line 的 `declining` 视为走弱，也能读取 `% Above MA` 当前实际字段 `percent_above_50d` / `percent_above_200d`。
- A/D Line、% Above MA、New Highs/Lows、McClellan 的数据质量记录增加成分股剔除提示，避免覆盖率看起来完整但实际有缺失原因未说明。
- L3 prompt 明确四件套优先级：A/D Line 和 % Above MA 是第一锚，New Highs/Lows 是第二批扩散确认，McClellan 是广度动能确认；数据缺失不能写成恶化。

真实源检查：

- A/D Line：可用，2026-05-01，趋势 `rising`，覆盖 101/101。
- % Above MA：可用，2026-05-01，50 日线上方 65.35%，200 日线上方 56.44%，覆盖 101/101。
- New Highs/Lows：可用，2026-05-01，52 周新高 14 只、新低 1 只，覆盖 101/101。
- McClellan：可用，2026-05-01，读数 1.43，覆盖 100/101；缺失/剔除会进入 `anomalies`。
- 当前本机未安装 `nasdaq_100_ticker_history`，实时分析使用最新成分股；严格历史回测仍需标注幸存者偏差风险。

验证结果：

- `tests/test_l3_breadth_data.py`：`8 passed, 4 warnings`
- `tests/test_vnext_packet_builder.py tests/test_vnext_orchestrator.py`：`10 passed, 4 warnings`

---

### 落地 L4 外部估值源与百分位优先口径

完成内容：

- 新增统一 L4 估值源结构，外部源统一携带 `metric`、`value`、`percentile_10y`、`historical_percentile`、`data_date`、`collected_at_utc`、`source_tier`、`availability`、`unavailable_reason`、`coverage`、`formula`、`fallback_chain` 和 `source_disagreement`。
- Trendonify PE / Forward PE parser 支持真实百分位；真实联网遇到 403 时明确返回 `unavailable`，不 fallback 到 yfinance。
- WorldPERatio 解析 Nasdaq 100 PE、日期和 methodology；无明确 percentile/rank 时保持 `historical_percentile = None`，只做当前 PE 交叉校验。
- Damodaran US implied ERP 改为优先读取官方 `histimpl.xls`，HTML 只作为 fallback；输出标记为 `official`，并明确是美国市场背景锚，不替代 NDX 自身估值。
- yfinance 成分股模型保留当前 PE / Forward PE / FCF yield 和覆盖率，但 packet builder 不再用当前 PE 单点生成历史估值 regime。
- 人工/Wind 模板新增单独 ERP 参考锚，避免把人工 ERP 混入 NDX 简式收益差距。
- L4 prompt、few-shot、reporter 最小展示同步更新：显示来源等级、当前值、真实分位、数据日期、不可用原因和 source disagreement。
- 补齐 Bridge resonance chain 校验：共振链必须有证据 refs、机制、确认指标、影响和反证条件。
- 新增 `xlrd>=2.0.1` 依赖，以支持 Damodaran 官方 `.xls` 文件解析。

真实源检查：

- WorldPERatio：可用，Nasdaq 100 PE = 32.27，数据日期 = 01 May 2026；未提供明确历史分位，因此不写 percentile。
- Trendonify PE / Forward PE：当前仍返回 403 Forbidden，系统按 `unavailable` 记录原因。
- Damodaran 官方 Excel：可用，最新行为 2025，`implied_erp_fcfe = 4.23%`，`tbond_rate = 4.18%`，来源等级为 `official`。

验证结果：

- L4 外部源 / 数据发言权 / packet builder / reporter / manual template / bridge 针对性测试：`21 passed, 4 warnings` 及 Bridge `5 passed, 4 warnings`
- 全量回归：`67 passed, 6 warnings`
- 已在本机补装 `xlrd 2.0.2` 验证 Damodaran 官方 Excel 可解析。

---

### 补齐 L4 数据发言权收口项

完成内容：

- 补齐手动 Wind 模板：`licensed_manual/Wind` 仍是可选高信任输入，但空模板不会触发人工覆盖。
- 移除模板中的 `ERP_Wind` 字段，统一改为 NDX 简式收益差距口径。
- L4 prompt 明确要求读取 `source_tier`、`data_date`、`collected_at_utc`、`update_frequency`、`formula`、`coverage`、`anomalies`、`fallback_chain`、`source_disagreement`。
- L2/L4/few-shot 文案不再把 NDX 简式收益差距写成低 ERP 或负 ERP。
- 更新 `ARCHITECTURE.md`、`DATA_COVERAGE_REVIEW.md`、`PLAIN_LANGUAGE_CHANGE_REPORT.md` 和 `NEXT_STEPS.md`，记录 L4 数据发言权制度和下一步真实 run 验证。

验证结果：

- 针对性测试：`17 passed, 4 warnings`
- vNext 编排/UI/Bridge 相关测试：`10 passed, 4 warnings`
- 全量回归：`53 passed, 6 warnings`
- `config/manual_data.example.json` 通过 JSON 解析校验。
- 本机 `python` 命令不可用，验证使用 `python3`。

---

## 2026-04-29

### 合并 DeepSeek-only 运行基准

提交：

- `412f8fa Default to DeepSeek v4 runtime`

完成内容：

- 默认启用 DeepSeek，默认关闭 ChatAI、Kimi 和 Gemini。
- 默认模型顺序保持为 `deepseek-v4-flash` -> `deepseek-v4-pro`。
- DeepSeek V4 调用对齐官方 OpenAI-compatible 参数：`stream=False`、`reasoning_effort="high"`、`thinking` enabled。
- Risk Sentinel 和 Final Adjudicator 新增护栏：不得编造无证据支持的点位、跌幅、估值倍数、盈利阈值或其他定量影响幅度。
- 新增 DeepSeek 运行配置测试和 prompt 护栏测试。

验证结果：

- worktree 分支：`39 passed, 133 warnings`
- 合并后的 `main`：`39 passed, 133 warnings`
- 已推送到 `https://github.com/aidianchi/NDX_VNEXT`

### 完成 2026-04-29 真实运行与数据覆盖复盘

基线 run：

- `output/analysis/vnext/20260429_001955`

完成内容：

- 使用 `deepseek-v4-flash` 完成全链路真实运行，`deepseek-v4-pro` 未触发。
- 复盘治理输入压缩后的 Critic / Risk / Reviser / Final，确认高严重度冲突和最终证据链仍可追溯。
- 发现 L3 广度数据仍是当前最薄弱环节，新增 `DATA_COVERAGE_REVIEW.md` 记录数据稳定项、弱项和下一步。
- 用 2026-04-29 run 生成默认 `brief`：`output/reports/vnext_research_ui_brief_20260423.html`。
- 清理 `.env.example` 的编码损坏，并补充 macOS / Linux 启动路径。

---

## 2026-04-28

### 重整根目录文档

完成内容：

- 把日期型根目录文档改成更容易理解的长期文件名。
- 把过期执行计划移入 `docs/archive/`。
- 新增 `NEXT_STEPS.md`，按“核心系统、数据基础、输出体验”三类组织下一步。
- 新增 `WORK_LOG.md`，用时间倒序记录完成事项。
- 更新 `README.md`，让新读者知道先读什么。

验证方式：

- 检查根目录文档名是否能直接表达用途。
- 检查旧文件名引用是否被更新。

### 合并治理阶段输入压缩

提交：

- Claude 分支提交：`c138a96 Compress governance inputs with support evidence`
- main 合并提交：`2f0a1fd Merge governance input compression`

完成内容：

- 新增 `GovernanceInputPacket`，让 Critic / Risk / Reviser / Final 消费更窄的治理输入。
- 明确保留 `thesis_key_support_chains`。
- `key_evidence_refs` 同时保留高严重度冲突证据和 thesis 支撑链证据。
- 更新治理阶段 prompt，要求检查支撑链证据，不再只看主论点文字。
- 新增治理输入测试，覆盖“支撑证据不在高严重度冲突里也不能丢”。

验证结果：

- `35 passed, 133 warnings`

---

## 2026-07-06

### 完成 vNext 实施路线图阶段 4：统一证据与最终 claim 台账

完成内容：

- 新增统一 `EvidencePassport` / `EvidenceRegistry` 合同，覆盖数据、事件、受控调查、竞争假说和最终 claim。
- 新增 `ClaimLedger` / `ClaimLedgerEntry`，为 Thesis / Final 的重要自然语言结论登记证据、反证、推理步骤、失效条件和验证状态。
- 编排器生成并落盘 `evidence_registry.json` 与 `final_claim_ledger.json`；Final 原始检查点保持不被 claim 台账回写污染，恢复运行可继续复用。
- 统一 source tier / authority / downgrade 规则：事件、标题新闻、代理指标、派生假说和最终 claim 不得越权充当强主证据。
- Run Review 新增证据与 claim 台账对抗式审查：缺证据、缺反证、缺失效条件、弱权限证据无降级规则都会被标记。
- Integrated Synthesis Report 读取证据注册表和 claim 台账摘要，但不允许其反向污染 L1-L5 或纯数据主链。

验证结果：

- `python3 -m py_compile src/agent_analysis/contracts.py src/agent_analysis/orchestrator.py src/agent_analysis/run_review.py src/integrated_synthesis_report.py src/data_evidence.py`
- `python3 -m pytest -q`
- 结果：`441 passed, 4 warnings`

剩余风险：

- 当前 claim ledger 为确定性生成，能保证可审计字段完整；后续阶段 5 仍需把读者出口和语义发布闸门做得更细。
- 事件材料进入统一注册表后仍默认弱权限，只能做解释线索；正式升级为主证据仍需要单独数据源升级流程。

---

## 2026-04-27

### 建立 Claude Code 独立分支协作规则

完成内容：

- 新增 `CLAUDE.md`。
- 要求 Claude Code 不直接改 `main`，只能在 `claude/YYYYMMDD-short-task-name` 分支提交。
- 规定交付时必须说明分支、改动文件、测试结果和风险。

### 推送 GitHub 备份仓库

完成内容：

- 建立并推送远端仓库：`https://github.com/aidianchi/NDX_VNEXT`。
- 补充 `.gitignore`，避免提交 `.env`、`.venv/`、`output/`、缓存和密钥。

### 补充通俗解释报告风格

完成内容：

- 在 `AGENTS.md` 中写入“架构文档”和“通俗解释报告”并行的规则。
- 明确当用户要求“解释给普通人听”时，要少黑话、少中英夹杂、保留风险和不确定性。

### 完成第二轮真实运行观察

基线 run：

- `output/analysis/vnext/20260427_190347`

结论：

- 指标说明书、typed map、Objective Firewall 和 native UI 已跑通。
- 发现 Risk / Final 会模仿 prompt 示例，生成无证据支持的历史概率。
- 已增加 prompt 护栏和测试，禁止编造历史胜率、回测收益、样本区间或概率数字。

---

## 2026-04-26

### 接入 Deep Research 法典第一轮

完成内容：

- 将 `RESEARCH_CANON.md` 定位为指标判读、市场状态诊断、跨层级推理和少文本提示的权威语料。
- 增加 ObjectCanon、IndicatorCanon、RegimeScenarioCanon、ObjectiveFirewallSummary 等核心概念。
- 让 L1-L5 开始具备指标发言权、误读护栏、反证条件和交叉验证意识。

原则：

- 不把整份研究材料硬塞进 prompt。
- 不破坏 L1-L5 运行时上下文隔离。

---

## 2026-04-24 至 2026-04-25

### 建立 vNext 第一版架构基线

完成内容：

- 明确 `Context-first, role-second`。
- 建立 L1-L5、Bridge、Thesis、Critic、Risk、Reviser、Final 的基本链路。
- 建立 native vNext UI 原型。
- 保留 legacy adapter 作为兼容路径，但不再让它承担主要推理。
