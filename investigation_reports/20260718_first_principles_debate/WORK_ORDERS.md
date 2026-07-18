# 第一性原理发现施工工单包（W1-W8）

日期：2026-07-18。依据：本目录 `DEBATE.md` 终审结论（用户已拍板：按序全立案）。
优先序（即施工序）：**W1(F8闸门) → W2(F8反馈) → W3(F7长期层) → W4(F2定价测量) → W5(F6归因台账) → W6(F1类比审计) → W7(F4仓位覆盖) → W8(F3远期冻结)**。

## 施工纪律（每单适用）

- 逐单顺序施工，完成一单更新该单状态行再进下一单；**不提交 git**（Fable 验收后统一提交）。
- 测试基线 **800 全绿**（`.venv/bin/python -m pytest -q`）。每单交付时全量测试必须全绿；新增行为必须带新测试。
- 外科手术式修改：只动本单列出的文件与必要的测试 fixture；不顺手重构。
- 常驻边界不可破：新闻/事件不进 evidence_ref；不编造数字/分位/历史胜率；PIT 纪律；弱权限指标不越权。
- 诚实上报：做不了、有歧义、发现工单本身有错，写进状态行，不许硬凑通过。
- 涉及 LLM 提示词的文本一律使用本文档内 Fable 亲笔的版本，逐字采用，不得自行改写语义（格式适配允许）。

---

## W1｜层间时点契约硬闸门（F8-a，骨架级，最优先）

**目标**：同一份综合报告的所有输入必须来自同一个 as_of 日期；对不上就不许发布正式结论。堵住 DEBATE.md 终审核查 2 的真实漏洞（7-14 数据 + 7-18 事件卡仍判 `publishable_integrated_report`）。

**改动点**（主文件 `src/integrated_synthesis_report.py`）：

1. 新增 `_check_time_consistency()`：收集以下日期（存在哪个收哪个，统一取日历日）：
   - `analysis_packet.meta.data_date`
   - `final_adjudication.generated_at`（取日期部分；ISO 时间戳如 `2026-07-14T00:00:00Z` → `2026-07-14`）
   - 事件卡顶层 `effective_date`
   - `cross_layer_questions` 顶层 `effective_date`（若存在）
   - 各调查报告的 `effective_date` 或等价日期字段（若存在）
2. 规则：可收集到的日期 **≥2 个且全部相等** → consistent；任何不等 → inconsistent；可收集 <2 个 → inconsistent（原因 `missing_as_of`）。容差由 `NDX_INTEGRATED_TIME_TOLERANCE_DAYS` 控制，默认 0；设置非 0 时结果仍要在 note 里写明"容差放行"。
3. 报告 JSON 新增顶层 `time_consistency` 块：`{"as_of": <一致时的日期或 null>, "members": [{"artifact": ..., "date": ...}], "consistent": bool, "notes": [...]}`。
4. `_publish_gate()` 合并该检查：inconsistent → `status=audit_only`、`formal_investment_conclusion_allowed=false`、`blocking_reasons` 加一条形如 `time_inconsistency: analysis_packet=2026-07-14, event_cards=2026-07-18` 的**带具体日期**的原因。既有闸门逻辑（DataIntegrity / claim ledger / final approval）不动，新检查是叠加的第四道。
5. `_llm_adjudication()` 已有 `formal_investment_conclusion_allowed` 检查，确认 inconsistent 时 LLM 裁决被跳过且降级 note 写明时点不一致（不要新开旁路）。
6. `src/agent_analysis/vnext_reporter.py`：第三层区块渲染 `time_consistency`——inconsistent 时在区块顶部显示警示条（复用现有 severity 样式类，不新造 CSS），文案："本报告输入时点不一致（列出成员日期），已降级为审计参考，不构成正式结论"。

**测试**（新增 `tests/test_time_consistency.py` 或并入 `test_integrated_adjudication.py`）：
- 错配 fixture（数据 7-14 + 事件卡 7-18）→ gate `audit_only`、blocking_reason 含两个日期、LLM caller 未被调用。
- 全一致 → 原行为不变（publishable）。
- 缺 as_of（只有 1 个日期可收集）→ inconsistent + `missing_as_of`。
- 容差 env=4 → 放行但 note 记录容差。
- 既有测试 fixture 若因日期不一致而挂，修 fixture 日期使其一致（这是 fixture 缺陷，不是放宽闸门）。

**明确不做**：不回改 `wo_r8_live_verify` 历史产物；不做"重大事件触发重跑"的调度器（那在 W2 之外另议）；不动 L1-L5。

**状态**：✅ 已完成（2026-07-18；新增综合报告时点一致性硬闸门、具体日期阻断原因、LLM 跳过说明及第三层页面警示；坏日期与日期不足均 fail-closed，非零容差放行会留痕；全量 808 passed、58 条既有 warning；reviewer 复核无阻断问题；未提交 git）

---

## W2｜第三层缺口受控反馈通道（F8-b）

**目标**：第三层发现"答不了/缺数据"时，产出一份机器可读的**补采需求清单**，供下一轮 run 的采集参考——只许说"缺什么"，绝不许携带多空预设（保 Context-first 隔离，DEBATE.md Codex 答3 + Fable 终审采纳）。

**改动点**：

1. `src/integrated_synthesis_report.py` 新增 `_build_recollection_requests()`，在 write 阶段落盘 `recollection_requests.json`：
   - 来源仅限三处结构化字段：`question_answers` 中 `answer_status` 为 `partially_answered`/`cannot_answer_yet` 条目的 `missing_evidence`；`conflict_matrix` 中 `not_yet_testable` 行的 `note`；调查报告中已有的"缺什么数据"结构化字段（只取字段值，不取报告正文）。
   - 每条 request：`{"source_type": "question|conflict_card|investigation", "source_id": ..., "missing": <原文摘录>, "candidate_function_ids": [...], "trigger_reason": "cannot_answer_yet 等状态值"}`。`candidate_function_ids` 用 evidence registry 的函数名做保守匹配（missing 文本里出现的 `L*.get_*` 直接提取；无法确定就留空数组，禁止猜）。
   - 顶层 policy 块写明：`"no_stance_rule": "requests carry only missing-data descriptions; verdict text must never be copied here"`。
2. 实现上**只允许**从上述字段复制文本；禁止读取 `integrated_verdict`、`reasoned_verdict` 等正文字段（用代码结构保证，不靠自觉）。
3. 报告审计区新增一小节"下轮建议补采清单"，逐条列出（复用现有审计区样式）。
4. 本单不做自动执行/调度：清单是给下一轮 run 的人或调度器看的输入，消费方式写进本文件状态行即可。

**测试**：含 cannot_answer_yet 的 fixture → 清单生成且 `missing` 与源字段逐字一致；request 全文里不出现 stance/verdict 字符串（用 fixture 里埋的哨兵短语断言）；无缺口 run → 空清单文件照常落盘（`requests: []`）。

**状态**：✅ 已完成（2026-07-18；新增 `recollection_requests.json` 与报告“下轮建议补采清单”；仅复制问答缺口、不可检验冲突 note、调查报告明确缺数据字段，判决/问答/调查正文哨兵均未泄漏；候选函数只直接提取并经 Evidence Registry 核验，未知项留空；无缺口也落空文件；消费方式为下一轮 run 的人工或调度器参考输入，本单不自动执行、不回灌旧 run；全量 812 passed、58 条既有 warning；reviewer 复核无阻断问题；未提交 git）

---

## W3｜长期资产评估层与个人决策政策分离（F7）

**目标**：把"3-5 年以上这笔资产值不值得长期持有"从周期姿态（最长 6-12 月）里分离出来；核心仓动作必须显式让位给个人投资政策书。DEBATE.md F7。

**改动点**：

1. `src/agent_analysis/contracts.py`：新增 `LongTermAssessment`（挂在 `FinalAdjudication.long_term_assessment: Optional[LongTermAssessment]`）：
   - `object_quality: str`、`earnings_compounding: str`、`valuation_implied_return: str`、`permanent_loss_hypotheses: List[str]`、`evidence_refs: List[str]`、`uncertainty_notes: List[str]`。
   - validator：`valuation_implied_return` 里出现 `%` 数字时必须有 evidence_refs（防凭空年化收益）；四个正文字段全空则整个对象视为未提供（None 等价）。
2. `src/agent_analysis/prompts/final_adjudicator.md`：追加以下 Fable 亲笔提示词块（逐字采用）：

> ## 长期资产评估（3-5 年以上，独立于周期姿态）
>
> - `long_term_assessment` 与 `time_horizon_views` 回答不同的问题：后者是周期判断（最长 6-12 个月），前者回答"这笔资产本身值不值得长期持有"。二者不得互相推导：周期姿态谨慎不自动等于长期不值得持有，反之亦然。
> - `object_quality`：判断对象的结构性质（集中度、成分质量、盈利能力），只用输入 refs。
> - `earnings_compounding`：盈利与自由现金流的复利证据（资本开支转化、回购执行、盈利预期方向），只用输入 refs。
> - `valuation_implied_return`：当前估值分位隐含的长期回报边界；只许引用输入的估值分位与收益率差 refs，禁止给出具体年化收益数字，除非输入 refs 明确提供。
> - `permanent_loss_hypotheses`：会造成永久性资本损失（而非波动）的假说清单，每条注明当前证据状态（有支持／无证据／被反驳）。
> - 核心仓（core_position）的任何加减动作建议，必须注明"须经个人投资政策书与再平衡带确认"；系统不得代替政策书给出具体金额或比例。
> - 不确定就写不确定；输入证据不足以支撑某字段时写明缺什么，不许硬编。

3. `portfolio_actions` 的 core_position 渲染处（vnext_reporter）：若 rationale/conditions 中无"政策书"字样，程序化追加一行固定文案"核心仓动作须经个人投资政策书与再平衡带确认"（不改模型输出，只加展示层护栏）。
4. reporter：第一层判决区新增"长期资产评估"折叠小节渲染四字段 + 假说清单（沿用现有卡片样式）；字段缺席时整节不渲染。
5. 排队中的"买卖纪律阈值"工单未来归入此框架（本单不做阈值，阈值仍 fail-closed 等用户数字）。

**测试**：合约 validator 两条（%无 refs 拒收、全空归 None）；prompt 含新块断言；reporter 渲染/缺席两态；existing final fixtures 不带新字段仍通过（向后兼容）。

**状态**：✅ 已完成（2026-07-18；新增 `LongTermAssessment` 合约并与 6-12 月周期判断分离，数字百分比回报无有效 refs 会拒收、四项正文全空归 None；Fable 提示词逐字追加；默认 brief 与其他报告入口均有长期评估折叠小节；core_position 展示层缺政策书说明时固定追加“核心仓动作须经个人投资政策书与再平衡带确认”，不改模型原始输出；全量 817 passed、58 条既有 warning；reviewer 复核无阻断问题；未做真实 LLM 在线抽样或浏览器视觉回归，属剩余低风险；未提交 git）

---

## W4｜"已定价"从断言变测量：预期-兑现台账（F2）

**目标**：把 `priced_narrative` 从模型断言升级为有测量支撑的判断。原料已在（vintage 档案日更、利率期货路径、VIX 序列），本单建台账 + 裁决纪律。

**改动点**：

1. 新模块 `src/expectation_ledger.py`，生成 run 产物 `expectation_vs_realized.json`，三个分册（全部 PIT 安全——只用 ≤effective_date 的数据回看过去的"当时预期 vs 后来兑现"）：
   - **盈利预期**：读 `output/vintage_archive/YYYYMMDD/eps_consensus.json` 历史快照，对交集 ticker 计算 30/90 天修正斜率（当前快照 vs 30/90 天前快照的 forward EPS 变化方向与幅度）；覆盖不足如实标注。
   - **利率路径**：把本轮 `get_fed_funds_rate_path` 的定价路径存入分册；对 ≥30 天前 run 产物中存过的路径（若可在 `output/analysis/vnext/*/` 或 state ledger 中找到），对照 FRED EFFR/DFF 实际值算"当时定价 vs 实际兑现"偏差；找不到历史路径就只存现值并注明"对照样本积累中"。
   - **波动溢价**：用图表时间序列里的 VIX 与 QQQ 日收益，计算过去每个 t-21 交易日的 VIX 对 [t-21, t] 实现波动的溢价序列（隐含-实现），输出近期分位。
   - 顶层 `metric_authority: supporting_only`，附 `downgrade_rules`；不进 L1-L5 raw prompt，作为综合层/审计侧材料。
2. `main.py` 在综合报告阶段前生成该产物（失败不阻断主链，落 note）。
3. `src/agent_analysis/prompts/final_adjudicator.md` 的 priced_narrative 要求处，追加 Fable 亲笔纪律（逐字采用）：

> - `priced_narrative` 必须包含一句明确的**分歧声明**：本判断与市场当前定价共识的分歧点是什么。若判断与定价方向一致，如实写"本判断与市场定价方向一致，超额观点为零"；无法判断定价状态时写 unclear 并说明缺哪条证据。分歧声明只能引用输入 refs（利率路径、盈利预期、波动溢价、预期-兑现台账），禁止凭空断言"市场认为"。

4. reporter：外部对照区或审计区新增"预期与兑现"小节渲染三分册摘要。

**测试**：三分册各一条构造样本测试（含覆盖不足的诚实降级）；prompt 新纪律断言；supporting_only 权限断言（不得出现在核心结论支撑 refs——沿用既有权限测试模式）。

**状态**：✅ 已完成（2026-07-19；新增 `expectation_vs_realized.json` 三分册：盈利只比较 PIT 自建 vintage 的 `+1y current`，30/90 天覆盖不足不借供应商回看字段冒充；利率只接纳 DataIntegrity 可发布且 packet/path/旧台账日期一致的历史 run，实际兑现使用 FRED EFFR、异常时回退 DFF，并按美国联邦营业日、发布可见日和整月应有观察完整性 fail-closed；波动溢价使用 VIX 与后续 21 个 QQQ 交易日实现波动，样本少于 20 不报分位。台账为 `supporting_only`，不进 L1-L5，只有同日且权限匹配的精简摘要可进入治理阶段定价叙事，错日/越权均降级或拒绝；主流程及失败说明双重失败也不阻断；Fable 分歧声明逐字加入提示词，报告外部对照与审计区展示三分册摘要。全量 832 passed、58 条既有 warning；reviewer 最终复核 no findings；未做真实 FRED 在线抽样，属剩余低风险；未提交 git）

---

## W5｜评分→方法修正归因台账（F6）

**目标**：让校准闭环的后半段有形：错误类型 → 改了哪个方法要素 → 之后效果如何。7-27 首批成熟评分前把容器建好。

**改动点**：

1. `src/agent_analysis/outcome_scoring_runner.py`：给每条已评分 claim 附 `error_taxonomy` 字段，取值 `direction_wrong | magnitude_wrong | condition_never_triggered | correct | not_scorable`（由现有判定逻辑映射，不新造判定）。
2. 新文件 `output/state_ledger/method_revision_ledger.jsonl` 及写入工具（`src/state_ledger.py` 加一个 append 函数）：每条 `{date, error_pattern, affected_element (prompt|contract|authority|threshold + 文件路径), change_ref (commit hash), expected_effect, review_after (日期)}`。本单只建 schema + 写入函数 + 空台账，**不生成任何虚构条目**。
3. `RUN_REVIEW_CHECKLIST.md` 加一节"评分复盘流程"：拿到成熟批次评分后，按 error_taxonomy 聚类 → 人工裁决是否指向方法要素 → 写 revision ledger → 下批评分回看 expected_effect。三段以内，写清"由 Fable/用户主持，不自动改方法"。

**测试**：taxonomy 映射三样例；ledger append 幂等/追加语义。

**状态**：✅ 已完成（2026-07-19；每条已评分 claim 新增 `error_taxonomy`，只把既有评分已明确判定的 `consistent → correct`、反向走势触发 falsifier → `direction_wrong`，其余归 `not_scorable`；当前规则不能区分 `magnitude_wrong` / `condition_never_triggered`，故保留合法枚举但不猜测填充。`src/state_ledger.py` 新增方法修正台账写入与严格 schema 校验，`change_ref` 必须同时满足哈希格式并真实解析到仓库 commit；精确重复幂等跳过、不同记录追加。`output/state_ledger/method_revision_ledger.jsonl` 已建立且为 0 字节，无虚构条目；该路径被 `output/` 忽略，未来 Fable 统一提交时须显式 `git add -f output/state_ledger/method_revision_ledger.jsonl`。复盘流程已写入 `RUN_REVIEW_CHECKLIST.md`，明确由 Fable/用户主持、系统不自动改方法。全量 837 passed、58 条既有 warning；reviewer 最终复核 no findings；未提交 git）

---

## W6｜历史状态类比：数据史审计（F1 第一阶段，只审计不入链）

**目标**：在建任何类比引擎之前，先诚实回答"我们到底有多少干净的 PIT 历史可用"。DEBATE.md 终审给 F1 定的六道防线是准入条件；本单只做防线之前的**数据史审计**。

**改动点**：

1. 新脚本 `src/analog_history_audit.py`（独立运行，不进主链）：对候选状态变量 DFII10（实际利率）、HY OAS、NDX 估值分位来源（Wind/HoM 谱系）、VIX，输出各自：可用历史起点与长度、已知修订风险、数据源换代断点，以及**独立政权事件簇的粗计数**（相邻同向状态间隔 ≥63 个交易日才算独立簇）。
2. 输出 `investigation_reports/20260718_first_principles_debate/analog_history_audit.json` + 同名 `.md` 人读摘要。结论允许是"样本不足以支撑任何类比引擎"——这是合格产出，不是失败。
3. **明确禁止**：本单不计算任何"状态→后续收益"的条件分布，不产出任何胜率/收益数字。那属于第二阶段，且必须先过预注册（下方草案冻结后另立单）。

**预注册草案（Fable 亲笔，冻结待审计结果修订一次后生效，本单不实现）**：状态变量=DFII10 分位×NDX 估值分位×HY OAS 分位；持有期=21/63/252 交易日；事件簇间隔 ≥63 交易日；只报分布+有效样本数+相对无条件基准增量；有效簇 <8 即弃权；走步样本外+留一政权检验后方可申请 supporting_only 权限。

**测试**：脚本冒烟（构造小样本序列断点/簇计数各一例）。

**状态**：✅ 已完成（2026-07-19；新增独立脚本 `src/analog_history_audit.py` 及 JSON/Markdown 审计产物，只统计数据覆盖、来源断点和“同向观察至少间隔 63 个清洗后交易日位置”的机械簇上界，明确它不是经济政权定义；未计算状态后的收益、条件分布、胜率、收益估计或类比信号，也未接入主链或 L1-L5。`as_of` 已作为硬过滤剔除未来观察并记录剔除数；DFII10、HY OAS、VIX 均披露 PIT vintage 缺失及修订风险；Wind 快照与 History of Market trailing/forward 谱系分别审计、禁止拼接。FRED 官方自 2026-04 起仅开放 `BAMLH0A0HYM2` 最近三年，产物已把 2023 起点标为访问窗口而非序列起点并记录来源断点。审计结论为 `rejected_insufficient_clean_pit_history`，不准入任何类比引擎；全量 841 passed、58 条既有 warning；reviewer 最终复核 no findings；未提交 git）

---

## W7｜直接仓位证据补齐：CFTC 持仓 + FINRA 融资余额（F4）

**目标**：补两条**官方**仓位数据源，权限 supporting_only。ETF 申赎资金流无官方免费源，本轮诚实不做（记入数据边界）。

**改动点**：

1. `src/tools_L2.py`（或 L3，按现有族归属就近）新增：
   - `get_cftc_nq_positioning`：CFTC 官方每周 COT 报告（Legacy Futures-Only，NASDAQ-100 合约），杠杆基金/非商业净头寸及其变化。**必须建模发布时滞**：数据为周二快照、周五发布，PIT 可见日 = report_date + 3 天起；`effective_date` 早于可见日的快照一律不可见。来源标 official。
   - `get_finra_margin_debt`：FINRA 月度融资余额，发布滞后约 3 周，同样建模 PIT 可见日；来源标 official。
2. 两函数 field-level `metric_authority: supporting_only` + `downgrade_rules`（沿用 8 个弱权限指标的既有模式，见 WORK_LOG 2026-07-17 条目），进 Evidence Passport；不可用时诚实 unavailable。
3. `RESEARCH_CANON.md` 判读卡两张（Fable 亲笔，逐字采用）：

> #### CFTC NQ 期货持仓（COT）
> **判读卡**：名称/代码：CFTC Commitments of Traders, NASDAQ-100；对应 `get_cftc_nq_positioning`。层级与性质：L2 事实型仓位；周频，发布滞后 3 天；仅支持。真正问题：**投机性仓位在纳指期货上是否极端拥挤，脆弱度是否抬升？** 本质：这是官方申报的持仓事实，但只覆盖期货一角，不等于全市场仓位。正确读法：看净头寸的历史分位与变化速度，不看绝对值；极端拥挤+价格反向是挤仓风险信号。误读：把净多头高企直接当看空信号（拥挤可以持续很久）。必须交叉验证：拥挤度面板、VXN、广度。行动边界：只作脆弱度佐证，不做方向依据，不做择时。反证条件：若净头寸极端但价格对利空钝化，说明承接力强于仓位表象。**B版短提示**：COT 告诉你"船的一侧站了多少人"，不告诉你船什么时候翻。
>
> #### FINRA 融资余额（Margin Debt）
> **判读卡**：名称/代码：FINRA Margin Statistics；对应 `get_finra_margin_debt`。层级与性质：L2 事实型杠杆；月频，发布滞后约 3 周；仅支持。真正问题：**全市场股票杠杆处于扩张还是收缩周期？** 本质：融资余额是官方申报的杠杆事实，同比拐点比绝对值有信息；历史上大顶附近常见同比高位回落，但滞后发布使它不适合短线。误读：拿单月环比做择时；拿绝对值创新高当见顶信号（名义值长期随市值增长）。必须交叉验证：净流动性、HY OAS、拥挤度。行动边界：只作杠杆周期背景，不做买卖依据。反证条件：同比回落但信用与广度健康，则更可能是良性去杠杆。**B版短提示**：看同比方向，别看创没创新高；它是月度后视镜，不是雷达。

4. 回测边界：两源均有官方历史档案，但本单只接 live+近期；历史 PIT 档案接入写入 `DATA_COVERAGE_REVIEW.md` 的升级路径，不冒充已完成。

**测试**：发布时滞 PIT 各一条（effective_date 早于可见日 → 不可见）；权限标签断言；断源 unavailable 断言。

**状态**：✅ 已完成（2026-07-19；新增 CFTC Legacy Futures-Only Nasdaq-100 非商业持仓与 FINRA Margin Statistics 两条 L2 官方事实源，均按字段限制为 `supporting_only` 并接入 Evidence Passport、注册表、证据族和 Fable 逐字判读卡。CFTC 按周二快照、周五起可见建模，只在恰有前一周数据时计算周变化；Legacy 不含 TFF leveraged funds，未混称、未计算无 PIT 档案支撑的历史分位。本机真实 CFTC API 抽样因 TLS/SSL 失败而诚实返回 unavailable，构造样本已验证解析、发布时滞和异常值 fail-closed；FINRA 官方 Excel 实连可用，按月末后 21 个自然日保守放行，严格绑定列名与月份格式并拒绝未来、非有限或负数余额。两源仅支持 live + 近期，超过 120 天的历史日期在接入不可变 publication vintage 前拒绝；升级路径已写入 `DATA_COVERAGE_REVIEW.md`。ETF 申赎资金流因没有本项目可接受的官方免费源，本轮未接入。定向 66 passed、4 条既有 warning；全量 868 passed、58 条既有 warning；`git diff --check` 通过；reviewer 最终复核无 findings；未提交 git）

---

## W8｜事件研究（F3）——条件性远期，冻结

**状态**：🧊 冻结，不施工。

激活条件（全部满足才解冻）：①事件全集只来自预注册官方日历（FOMC/CPI/NFP/财报日，W5 之后 R5 底账已具雏形）；②先定全集后看价格，零反应事件必须入样；③窗口/基准/对照/多重检验事前固定；④升级路径仅限"测量值成为受限数据族"，事件叙事永不入 evidence_ref。任何提前实现视为违规。现有 `news_event_data_linker.py` 保持审计侧不动。

---

## 验收记录区（Fable 填写）

**2026-07-19 凌晨，Fable 逐单亲验，W1-W7 全部通过，统一提交（W8 维持冻结，未发现越界实现）。**

- 全量测试亲跑：**868 passed、58 条既有 warning**（基线 800，新增 68 条全部随单交付），与各单状态行自报一致。
- **W1**：亲读 `_check_time_consistency` / `_publish_gate` / `_llm_adjudication` 全部改动。日期收集范围、"≥2 且全等"规则、容差放行留痕、无效日期 fail-closed、时点不一致时 LLM 裁决跳过、reporter 警示条（复用 `boundary-card bad`）逐项与工单一致；8 条新测试覆盖错配/一致/缺日期/容差/无效日期/调查报告参与/跳过裁决仍警示。
- **W2**：`_build_recollection_requests` 只接收窄参数 + 调查报告字段白名单，代码结构上够不到判决正文；候选函数经 Evidence Registry 核验、未知不猜；哨兵泄漏与空清单落盘测试在 `test_integrated_adjudication.py`。
- **W3**：`LongTermAssessment` 合约（% 数字无 refs 拒收、四正文全空归 None）；Fable 提示词块与工单原文逐字比对一致；报告折叠小节 + core_position 缺"政策书"字样时程序化追加固定文案，只动展示层不改模型输出。
- **W4**：`expectation_ledger.py` 三分册 PIT 纪律亲读——vintage 只取 ≤effective_date 快照并明确拒用供应商回看字段（`eps_trend.30daysAgo/90daysAgo`）；利率对照只接纳可发布历史 run，FRED 实际值按可见日过滤、按营业日完整性 fail-closed；波动溢价样本 <20 不报分位。主链失败不阻断；治理侧摘要有"同日 + supporting_only"双闸；分歧声明纪律逐字入提示词。
- **W5**：error_taxonomy 映射保守（consistent→correct、价格反向触发 falsifier→direction_wrong、其余 not_scorable，不猜幅度/条件类）；`append_method_revision_entry` 严格校验（commit 必须真实存在、日期次序、要素枚举）+ 精确重复幂等；空台账 0 字节已建并 `git add -f` 入库；复盘流程三段入 `RUN_REVIEW_CHECKLIST.md`。
- **W6**：审计脚本独立于主链；产物无任何收益/胜率/条件分布数字；结论 `rejected_insufficient_clean_pit_history` 属合格产出；HY OAS 的 FRED 三年访问窗如实标为访问边界而非序列起点；Wind/HoM 谱系分开审计、禁止拼接。
- **W7**：CFTC（周二快照 +3 天可见）与 FINRA（月末 +21 天保守可见）PIT 建模、field-level `supporting_only`、Legacy 不冒充 TFF、断源诚实 unavailable，16 条定向测试全绿；判读卡与工单原文逐字一致入 `RESEARCH_CANON.md`；升级路径入 `DATA_COVERAGE_REVIEW.md`；packet_builder/collector/evidence_families/data_evidence/deep_research_canon 五处登记齐全。
- **剩余低风险**（各单状态行已如实申报）：W3 未做真实 LLM 在线抽样与视觉回归；W4 未做 FRED 在线抽样；W7 本机 CFTC API TLS 失败（fail-closed 为 unavailable，非造假路径）。均不阻断验收，留待下一次 live run 自然覆盖。
