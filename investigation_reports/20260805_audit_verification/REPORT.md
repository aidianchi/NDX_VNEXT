# 2026-08-05 七路审计结论双路复核报告

> **状态权威声明**：本文件是复核结论与证据的台账。"某件事做没做完"的唯一权威是根目录 `现在.md`。

**背景**：用户开工 T38/T45 前要求验证 `investigation_reports/20260804_seven_way_audit/HANDOFF.md` 的结论是否可靠、施工方向是否正确。两路 Opus 并行（红队事实复核 + 独立方向审查），Fable 主对话对全部关键判定做了二次亲手验证。

**总判定**：10 条事实断言中 **5 条证实（数字独立复现）、3 条部分成立需改表述、2 条证伪**。渐进披露大方向成立，但论证与排程需修正四处。用户 2026-08-05 拍板：全部落地。

---

## 一、红队事实复核（10 条判定）

| # | 断言 | 判定 | 要点 |
|---|---|---|---|
| 1 | 教训1 改判依据（下游拦截存在） | 部分成立 | `data_evidence.py:645-646` 硬拦证实；**但 `packet_builder.py:473` 是错锚点**——那是计数器，真正剔除在 `:562-575`（hard_block 指标整条替换为 `{"value": None, "error": "data_evidence_hard_block"}`）。无"既绕 end_date 又绕拦截"的组合路径（`_m7_eps_revision_snapshot` 全仓唯一调用点在硬拦名单函数体内）。**硬拦有两个结构性逃逸口**：`backtest_skipped=True` 或 `availability != "available"` 任一成立即失效——须写进 T39 验收 |
| 2 | 受保护 8 条=全部可发布结论 | 部分成立 | 8 条证实（`orchestrator.py:3427-3437` 恰 8 次 add）；但 **`reasoned_verdict`（本轮 1,472 字符、判断书最长主判决）不在其中**，只有 `_validate_reasoned_verdict_refs`（`:5842`）弱校验。另 `must_preserve_risks[:6]`/`portfolio_actions[:4]` 硬截断、空字段静默缩条。正确表述分两档：深度校验覆盖 8 条；引用合法性校验（`:5773`）覆盖全部带 evidence_refs 字段 |
| 3 | T39 泄漏由 commit 860971d 引入 | **证伪** | `git log -S 'eps_revision_primary_source = "yfinance_fallback"'` → **`5705a71`（2026-06-08，数据源改造）**，非 860971d（2026-07-11，PIT 加固）。`:3323` 的 `and not end_date` 同指向 5705a71。Fable 亲手复验一致。教训 3"加固边界的改动顺手开新口"在此实例**零支撑**；真实规律是"加兜底未配守卫 + 一个月后加固时无人回头复查既有兜底" |
| 4 | 26 许可 20 有名无实 | 证实且低估 | 逐字复现（L5=6/L1=4/L2=4/L3=3/L4=3；30.84/87.2 在提示词出现 0 次）。**追加：所谓 6 条非 hollow 实为格式示例/子串误命中/散文引用——结构化数值供给实为 0/26** |
| 5 | 全系统无一处许可-实发交叉校验 | **证伪** | 反例 `orchestrator.py:1957`：`allowed_refs = list(assembled_refs)`，而 `assembled_refs.append(ref)`（`:2214-2215`）只在材料实际写入提示词后执行——controlled_investigation 的**许可从实发导出，物理不可分叉**。这正是"索引即许可"的既有实现，应作 T38 先例。真实缺口是**不留痕**（被 `max_source_refs` 截掉的 ref 不落盘）与 stub 兜底用声明 refs |
| 6 | 工具通道只交答卷、无回灌 | 证实 | `orchestrator.py:5230/5232` 单次调用；`llm_engine.py:518-524` 取 `tool_calls[0].function.arguments` 即输出；全仓 `role:"tool"`/`tool_call_id` **零命中** |
| 7 | tool_choice="auto" 逃逸已实证 | 证实 | `llm_engine.py:476` + event_section_summary 两次 attempt 的 raw 响应均为 content 通道坏 JSON（裸引号，strict schema 不可能产出）。注意：07-31 的 5 条 parse_error 里 L2 两条是**响应截断**非逃逸，勿混用 |
| 8 | 前缀 0.16%、角色模板在前 | 证实 | `_compose_prompt`（`orchestrator.py:6384-6408`）顺序无条件；六站最长公共前缀 368 字符，站长度端点与 HANDOFF 逐位吻合。**订正：HANDOFF 的 44,022/293,959 是字节非字符（字符 25,056/247,717），双边同单位、6.7 倍结论不变** |
| 9 | 68/102 从未引用 | 部分成立 | 严格字符串口径逐字复现（L2=36/L4=17/L1=9/L5=4/L3=2）。**按指标口径（引用父级即算用到字段子条目）实为 45 条**——68 里 23 条是被引用 ref 的父级/兄弟（含 `L2.get_vxn#level`）。作诊断成立，**作剪枝输入高估约 50%** |
| 10 | 层间隔离机械构造 | 证实 | `_build_layer_stage_payload`（`:931-946`）6 键白名单、唯一构造点 `:896`；`_build_layer_context_brief`（`:5092-5112`）重建非过滤；六份真实提示词全干净。小收窄：`_build_layer_manual_overrides`（`:5131`）是过滤非构造，风险低 |

**红队清单外新发现**：① `LATEST_ONLY_FUNCTIONS` 硬拦名单手工维护、无测试守护完整性（`get_m7_earnings_blackout_calendar` 的 `runtime_today` 用法属明示降级、不在名单，严重度低但名单靠人记）；② capex/buyback 的 yfinance fallback 是同题正确写法（`tools_L4.py:5806-5827`/`:6224-6245`），T39 可照抄；③ 审计单提交归因未做 `git log -S` 十秒检查（已证伪一例）。

## 二、方向审查（六问结论）

1. **治疗配不配得上诊断**：20 条幽灵引用的最小对症疗法是 `integrated_synthesis_report.py:296` 改实参（许可从 payload 导出）+ `_ref_authority_map`（`:356`）捎带 `canonical_question`/`current_reading`（26 条约 2,800 字符）——**不需要整套改革**。渐进披露另有成立理由：**深度轴冗余**。
2. **实测（Fable 独立重算一致）**：`evidence_index` 全量 478,178 字符/102 条；"问题+读数"投影 10,086（2.1%）；中档投影 28,332（5.9%）。**削 94% 而广度一条不砍、无检索、无 A/B、不碰铁律。**"注意力稀释"目前无实测证据；"68 从未引用"应从 T38 论证退出（见断言 9）。
3. **"索引即许可"降格为局部构造技巧**：合并消除"两处漂移"但不消除"一处就错"（后者无声）。须保留独立"应然可见集合"校验 `索引⊆应然 ∧ 索引⊇必备核心`。**索引字段白名单硬要求**：`cross_layer_implications`（L2 条目实测含"需要L4验证估值是否已反映高波动"）、`narrative`、`first_principles_chain` 禁入 L1-L5 可见索引。
4. **A/B 框架漏了中间形态 A′**：代码侧深度分档 + 输出 schema 加 `unmet_information_needs`（ref enum）——零往返拿到"模型还缺什么"，严格模式可强制，把"被诚实救"变"被机制救"。另有"两遍单发"（B 信号、A 失败面）与"按站点切"（治理四站先行）两形态。**B 不需要重建架构**（`_run_stage` 内加回灌循环即可），T45 把 B 与重建并列暗示了不存在的因果。
5. **重建判据补第 0 问（答否即终止）**：本次全部已确认缺陷（幽灵许可/预算截断/PIT 泄漏/L3-L5 零登记/严格模式不留痕）**没有一条根因在 harness 层**——重建修不了任何已知病。另须事前落盘决策规则（调研后不得改）+ 回答退出成本。
6. **验收判据**：`现在.md` T38"四问"与工单 3.5 四条风险是两组问题（仅"缓存顺序"重合）——需在工单里给四问上编号（Q1-Q4），台账只引编号。T44④ 是 T38 前置（工单 L336 明写）但台账不可见。

**方向审查最大发现（Fable 亲手验证属实）**：`GovernanceInputPacket` 41 字段 thesis 相关 20 个、**counter 相关 0 个**；`key_evidence_refs`（`orchestrator.py:4820-4865`）由 thesis 引用 ∪ 高严重度冲突构成，counter_thesis 零命中。**critic/risk/reviser/final_adjudicator 四站的证据集合被正方引用单方圈定**——"代码做不出偏科"只在 thesis/counter_thesis 一对上成立。今天就在跑，非未来风险。已立案 **T46**。

## 三、Fable 亲手复验记录

- 断言 3 证伪：`git log -S` + `git show 860971d` 亲跑，5705a71/2026-06-08 确认。
- 断言 5 证伪：`orchestrator.py:1957`、`:2214-2215` 亲读确认。
- reasoned_verdict 不在 8 条台账：`_build_final_claim_ledger` 函数区间 grep 零命中确认。
- GovernanceInputPacket 0 counter：`model_fields` 枚举 41 字段亲跑；`:4855-4870` 亲读，构造仅用 thesis_* 来源。
- 深度投影数字：独立脚本重算 478,178 / 10,086 / 28,332（与方向审查的 482,196 / 12,754 / 28,516 差异为序列化口径，结论不变）；`L2.get_vxn.current_reading = "30.84，10年百分位87.2%，Spot/MA20=1.12"` 亲眼确认存在于同一 run 产物。
- 两处两函数错位代码（`integrated_synthesis_report.py:296` 附近）亲读确认。

## 四、由此产生的落地清单（用户 2026-08-05 拍板"全部落地"）

1. HANDOFF 教训 3 按更正模式改写；教训 1 行号与"恰好"表述修正；教训 4 补 0/26；第六节字节标签订正；第五节补 A′ 形态、第 0 问、事前决策规则。
2. WORK_ORDERS：3.6 全称断言更正（补 controlled_investigation 反例与先例定位）；3.1 补最小止血方案与 0/26；3.2 补 68→45 口径警告；3.5 四问上编号 Q1-Q4；T39 补两个逃逸口与名单守护测试；T42 三件扩四件（止血为首）；新增 T46 立案节。
3. `现在.md`：T42/T38/T44/T45 行按上述修正；新增 T46 行；打分后先止血再进主方向。
