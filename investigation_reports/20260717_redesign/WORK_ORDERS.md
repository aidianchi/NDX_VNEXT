# 报告与新闻层重构工单包（2026-07-17 立案）

来源：2026-07-17 主对话四问诊断（报告疲劳 / 新闻管线 / 交叉质询 / 推理机制）+ 两轮设计研讨。用户已拍板决议清单 v3。
分工：**Fable 5（主对话）**＝设计、全部 LLM 提示词原文、报告样张与最终 CSS、逐单验收；**Codex**＝全部代码施工；**用户**＝Phase 0 网络放行 + 样张选型两个开关。

## 施工总纪律（每单必须遵守）

1. 外科手术式收敛：只改工单列出的文件与位置；不顺手重构、不清理无关旧代码；本单制造的未使用导入/变量必须同步清理。
2. **工单内的 LLM 提示词文本一律原样使用，一个字都不许改写**。措辞是 Fable 的交付物；Codex 只负责把它接进代码。
3. ~~每单一提交~~ **git 纪律修订（2026-07-18 05:40，Fable）：本波施工一律不做任何 git 提交**——工作树混有前一批次（2026-07-17 方向 1-4 收口）的未提交改动，按单提交会把两批工作搅在一起；改为每单完成后只更新本文件状态行，验收全部通过后由 Fable 与用户确认整批提交方案。测试纪律不变：每单完成跑相关单测 + 全量 `.venv/bin/python -m pytest -q`（当前基线 **721** 全绿，只增不减）；涉及报告的单要用 run `20260715_001617` 实际重新生成 brief 验证不崩。
4. 常驻边界不可破：新闻/事件材料不得进入 L1-L5 主证据链、不得成为 evidence_ref；不得编造数字/分位/阈值；回测尊重 effective_date。
5. 完成后不自行更新 NEXT_STEPS/WORK_LOG 总账——由 Fable 验收时统一记账（本目录各单的"状态"行可以更新）。

## 顺序与依赖

```
R1（模板处置，独立，先行）
R4（受控调查执行器，独立）
R3（判决正文双轨，独立；渲染位与 R2 有弱耦合，先出字段后出渲染即可）
R7（Thesis 回应竞争假说，独立小单）
R2（报告脊柱重排——等用户选定样张风格后开工；CSS 由 Fable 交付）
R5（新闻 Phase 1 官方日历底账——Fed/BLS/BEA 源依赖用户 Phase 0 放行，其余部分可先行）
R6（新闻 Phase 2 LLM 事件卡——依赖 R5 验收）
R8（第三层真裁决——依赖 R4+R6 验收；提示词届时由 Fable 交付，本文件只锁定范围）
```

Phase 0（**已转为 WO-R5 的步骤 0，由 Codex 执行**，2026-07-17 用户改派）：定位本机 Clash Verge 配置（已有 `data.sec.gov → YKK` 规则可作定位参照与格式模板），**先备份原配置**，追加 `www.federalreserve.gov`、`www.bls.gov`、`www.bea.gov` 三条同型路由规则，重载配置后逐一 curl 验证可达。注意：这是仓库外的系统级配置修改——完工报告必须附配置 diff 与备份路径；只加这三条，不得动其他规则（尤其 FRED 与 IPRoyal 默认路由）。验证：`news_event_ledger.json.source_errors` 中这三个源清零。

---

## WO-R1 模板文字三类处置（过渡期止血）

状态：✅ **验收通过（2026-07-18 05:40，Fable 亲验）**。Codex 于 00:28-00:29 完成代码（未提交、未更新状态行即停工，由 Fable 验收时确认）。改动在工作树：`vnext_reporter.py`（罐头区按 stub 隐藏、新闻区降级"事实底账"、决策翻译"无模型参与"对照式）+ `event_narrative_ledger.py`（`_first_sentence` 数字句号修复、模板句废弃）。验收实录：721 测试全绿（基线 714 +7）；重生成 brief 断言全过（美光模板=0、信息背景背景=0、无"反馈复核（第二轮）"、16 张主线卡带来源/tier/日期）。Fable 补修一处：`published_at` 混合格式（RFC/ISO）统一为 YYYY-MM-DD 展示（`_display_date` helper）。**未提交**——工作树同时含前一批次未提交改动，本波改为整批一次提交（见下方 git 纪律修订）。
目标：判断书里不再有"冒充分析的模板文字"和"假装在运转的死循环"；确定性模板重新定性呈现。

改动点（全部在渲染层，不动数据管线）：

1. **撤下"反馈复核（第二轮）"区块**：`src/agent_analysis/vnext_reporter.py`（`feedback_bridge_v2` 显示名注册在 :48，渲染在冲突章节内）。条件：当该 run 全部 `investigation_reports` 的 `is_deterministic_stub` 为 True 时，brief 不渲染 feedback bridge 卡片（数据照常落盘，只是不展示）。R4 上线后真调查自动恢复显示，不需要再改。
2. **新闻区降级为纯事实底账**：`_event_layer_summary_section` / `_event_mechanism_report_section`（`vnext_reporter.py:3117/:3011`）不再渲染 `ai_analysis`、每桶固定的"可以说/不能说"模板句和"展开 AI 分析"折叠区；每条新闻只渲染：标题、来源、source_tier、published_at（必须显示日期——现在卡片正面没有日期）、正文摘录（见第 4 点）。保留"新闻事件给数据层出的题"和"下一步追踪"两个子区。章节顶部加一行说明文字（固定文案）："本区当前只提供事实底账；事件解读功能重建中，重建前不提供机器分析。"
3. **"个人决策翻译"重新定性**：保留 `_personal_policy_translation`（:2035）的确定性逻辑不动，但呈现从"伪装成分析的段落"改为"对照清单"样式：标题改为"按你的政策书逐条机械对照（无模型参与）"，正文渲染为"政策条款 → 本轮判断 → 对照结果"的三列/三行结构（`_STANCE_PARAGRAPHS` 的三段文案拆成对照行，语义不变）。
4. **摘录截断修复**：`src/event_narrative_ledger.py:865-871` `_first_sentence` 不得在"数字+句号"处断句（"跌近1。"bug）；改为：优先在第一个不紧跟数字的中英文句号处截断，找不到则 120 字符硬截 + 省略号。顺带删除 :984-985 的"背景信息背景"拼接分支（该模板句整体随第 2 点废弃）。

验收标准：用 run `20260715_001617` 重新生成 brief——① grep "如果美光财测确实上修" 为 0；② grep "信息背景背景" 为 0；③ 不出现"反馈复核（第二轮）"；④ 新闻卡片正面出现日期；⑤ 个人决策翻译区出现"无模型参与"字样且金额零渲染断言测试仍绿。新增/调整对应单测。

## WO-R2 报告脊柱重排 v3

状态：✅ **验收通过 + CSS 已交付（2026-07-18 第二轮验收，Fable 亲验）**。Fable 独立复核 Codex 全部断言（775 测试亲跑、体积/复读/digest/锚点/脊柱顺序逐项过）。`report_styles/slate_v3.css` 已由 Fable 交付（令牌契约与 slate_v2 同名、B 风格取值、深色模式、新钩子+旧类双覆盖、抽屉组件移植），默认样式已切 slate_v3（方法默认+CLI 默认+文件名后缀规则+一处测试同步）。v3 成品 `output/reports/vnext_brief_20260715_001617_v3.html`：**92,198 bytes（较原版 744KB 降 87.6%）**，104 类全覆盖（程序化检查），775 全绿。原 Codex 状态行存档：（2026-07-18 08:52，Codex）brief 已按 style-b class 钩子重排为门脸→正方→反方→外部事实→唯一改判正本→变化→L1-L5→单行审计的固定脊柱，并改走模块级顺序常量与 `_main_sections` renderer；R7 `hypothesis_responses`、fail-closed 发布闸门、每层 3-5 张引用优先卡、显式 hi/lo/neutral 分位方向、8 字段 `ref-digest` 和自动伴生 `layers` artifact 均已落地。真实验收件 `output/reports/vnext_brief_20260715_001617_r2.html` 为 173,092 bytes（较 744,550 缩小 76.75%），digest 23,921 bytes / 42 指标 / 单项最大 968 bytes，目标失效句仅 1 次；`output/reports/vnext_layers_20260715_001617_r2.html` 的 42 个锚点全命中。桌面/手机均无横向溢出，抽屉开关、外链和 JS 控制台检查通过，截图见 `output/reports/wo_r2_{desktop,mobile}{,_top,_drawer}.png`；最终 `775 passed, 58 warnings in 38.92s`，post-review 无剩余 Critical/Important。偏离/诚实降级：目标旧 run 没有可核验 `source_snapshot.json`，故未拿当前 live 文件冒充旧时点，抽屉走势为 0；`slate_v3.css` 未自行创建，按工单继续用 `slate_v2` 双挂兜底。
目标：把"四个阅读层级压扁成滚动条"的结构改为"一根正方先行的推理链脊柱 + 折叠深度"，消灭复读，外移审计负重。

**选型后新增需求（2026-07-17 晚，用户确认）：**

- **ref 抽屉（替代原"ref-chip 改外链"方案）**：判决正文与支撑链中的证据标签点击后从右侧滑出抽屉，显示该指标的最小摘要（交互样式照样张的 drawer 实现）。数据来源：brief 内嵌一个**瘦身版** `<script type="application/json" id="ref-digest">`，每个指标只含 8 个字段：`metric`（人话名）、`layer`、`value_line`（读数一句话）、`quantile`（数值或 null）、`answers`（它回答什么）、`cannot_prove`（不能证明什么）、`falsifier`（反证/改判条件）、`artifact_anchor`（全量底稿锚点）。**预算硬约束：单指标 ≤ 1KB、全量 ≤ 50KB，超限即测试失败**（对照：旧抽屉 payload 约 398KB、占文件 53%，本方案是它的瘦身替代而不是复活）。抽屉底部"查看完整底稿"链接跳外部 layers artifact 对应锚点。
- **微图（2026-07-18 定稿）**：**卡内只放分位标尺，走势线全部移入抽屉**。规则：① aside 数据卡统一只渲染分位标尺（纯 CSS，只消费 payload 已有分位数，样式照样张 `.gauge`，含 `zone.hi`/`zone.lo` 危险方向着色；无分位的指标不渲染标尺、不用其他数字冒充——卡片框体靠 grid stretch 自动等高，不预留空槽）；② 迷你走势线只出现在 ref 抽屉内（白名单 ≤15 个走势/结构类指标：腾落线、NDX/NDXE、均线结构类等；序列从快照顶层 `recompute_inputs` 降采样 ≤60 点，随 `ref-digest` 内嵌，走势线序列部分单独预算 ≤12KB，超限测试失败；白名单外的指标抽屉只有标尺）。理由：卡片网格里混排高矮不一会产生破碎空白（用户 2026-07-18 反馈）；抽屉是全宽独占面板，无等高竞争，且"看形状"本来就是追问动作而非扫视动作。

脊柱顺序（固定）：

1. 门脸卡：判断对象 + `reasoned_verdict` 判决正文（R3 产出；字段缺失时回退渲染现有 `final_stance`+`reader_final.one_liner`）+ 姿态/赔率/可信度徽章 + 一句"最强异议"（取 `hypothesis_competition` 中首个 candidate 的一句话）+ 三个锚点链接（正方论证/反方压力测试/改判条件）。
2. 正方主论证：`principal_contradiction` 整卡（summary/why_principal/action_implication）→ 三条支撑链 → `price_reflection_map` → 时间尺度三视图。
3. 反方压力测试：`_hypothesis_competition_block`（:3513）移到此处升为一级章节；每个 candidate 渲染"它的主张 / 它最强的证据 / 为什么本轮暂时不采纳 / 什么会让它赢（falsification_conditions）"。R7 落地后"为什么暂时不采纳"改读 `hypothesis_responses`。
4. 外部世界对照：R1 降级后的事实底账区整体移到此处。
5. 改判条件唯一正本：`_risks_section`（:3454）保留全部内容；hero/30秒区/赔率区对失效条件的整句复读全部改为锚点链接（允许保留一条 ≤20 字的摘要引子）。"和上次判断比，什么变了"保留在本章之后。
6. L1-L5 分层证据：每层渲染"层级摘要段落 + 该层 3-5 个关键指标卡"，其余指标进 `<details>` 折叠；折叠内保留现有指标卡结构。
7. 审计：缩为一行链接区（运行目录、workbench、prompt inspector、底稿 artifact）。

工程要求：

- brief 章节装配改走 `_main_sections` 的 renderers 字典（:1777-1819），废除写死的调用序列；章节顺序用模块级列表常量声明。
- `<script id="vnext-data">`（HTML 单行约 40 万字符）从 brief 移除，替换为上述 ≤50KB 的 `ref-digest`。新增 `--template layers` 输出（复用现有 `_layers_section` 全量渲染逻辑生成独立 self-contained HTML，含锚点 `#<function_id>`）作为"完整底稿"落点。主 brief 保持 self-contained（不引入 fetch/外部 JSON）。
- 整句标题修复：支撑链、改判条件等处的 H3 改为"支撑链 n · 主导指标名"/"【转多】条件 n"式短标签，整句内容降为正文段落。
- CSS：Codex 只负责结构与 class 钩子（class 命名按样张选定风格的 demo 文件为准）；`report_styles/slate_v3.css` 由 Fable 交付后替换引用（`_css`，:5260）。交付前用 slate_v2 兜底不阻塞本单。

验收标准：用 run `20260715_001617` 重新生成——① "若 10 年期实际利率快速回落至 2.0%" 全文出现次数 ≤ 2（正本一处 + 门脸摘要至多一处）；② brief 文件体积较 744KB 下降 ≥ 45%；③ `vnext_layers_*.html` 生成且锚点可跳；④ 章节顺序与上述脊柱一致；⑤ 桌面 + 移动断点目视检查；⑥ 既有 reporter 单测按新结构更新后全绿。

## WO-R3 判决正文双轨（合约 + 渲染由 Codex；提示词已定稿）

状态：✅ **验收通过（2026-07-18 充值后收尾，Fable 亲读裁决）**。提示词经三轮实证迭代定稿（v2 风险点名制/audit-only 禁令 → v3 标注聚焦制 → 终版字数带 600-1200，机器校验带同步放宽 300-1300+两处测试 fixture 更新）：三轮样本各差一项（396 字漏风险 / 788 字零标注 / 1198 字超我拍脑袋的旧上限），证明完整判决的自然长度即 1000-1200 字，字数带按现实修正而实质要求（结构/五风险全点名/主要理由带可解析标注/权限纪律）全部保持。**终验样本 1198 字、10 个标注全解析、五风险全点名、权限内联自标（"第三方数据，仅审计级别""supporting_only 不能作核心估值依据"）、失效条件双向**，Fable 亲读合格，存档 `investigation_reports/20260717_redesign/r3_v3_acceptance_sample.json`。775 测试全绿。原 Codex 状态行存档：（2026-07-18 06:20 施工完成，语义阻塞如实上报）Codex 施工（06:20）的合约/校验/渲染全部通过验收。Fable 亲读 396 字失败样本后裁定：内容质量接近合格，三项不满足（差 4 字符不到 400、5 条风险未全点名、用了 audit-only 数值）均为提示词约束交互过紧所致，非模型能力问题。处置：定稿提示词升 **v2**（已改 `prompts/final_adjudicator.md`，下方引文已同步）——字数 450-800、风险"短语点名即可但一条不许漏"、数字优先分位且 audit-only/supporting_only 禁作数值依据。验证驱动 `investigation_reports/20260717_redesign/r3v2_verdict_driver.py`（复用审计 prompt 直连 final 阶段）已就绪，但执行时 DeepSeek API 返回 **402 Insufficient Balance**（Codex 凌晨 8 次重试耗尽余额）——**充值后跑该驱动 + Fable 亲读即可关单**。
目标：最终裁决在保留全部结构化字段的同时，输出一段可审计的总分总判决正文，成为门脸卡主体。

改动点：

1. `contracts.py`：`FinalAdjudication` 增加字段 `reasoned_verdict: str`（校验：长度 300-900 字符；允许为空字符串时整卡不失败，但写入 `quality_gate.notes` 一条"判决正文缺失"）。schema guard 与 legacy adapter 对新字段做透传/容忍。
2. `prompts/final_adjudicator.md`：在输出要求部分插入以下提示词（**原样粘贴，不得改写**）：

> ## 判决正文（reasoned_verdict）【终版，2026-07-18 三轮实证迭代定稿，与 prompts/final_adjudicator.md 现行文本一致】
> 完成所有结构化字段之后，再写一段 600-1200 字的连贯判决正文，放进 `reasoned_verdict` 字段。这段话是给读者看的主文，要求：
>
> - 结构为总-分-总：开头两三句话给出完整判断（判断对象、姿态、赔率、时间尺度）；中间按"最有分量的三条理由"展开，每条理由必须点名具体证据，并且写出它对应的反面证据或局限；结尾回到赔率与等待的代价，并明确说出"当前最强的反对解释是什么、为什么本轮证据不足以让它改变判断"。
> - must_preserve_risks 的每一条都必须在正文中出现，但一条只需一个短语点名（例如"广度分化"四个字即算点名），不必逐条展开；一条都不许漏，也禁止弱化任何一条的严重性。
> - 只允许使用本次输入中已经出现的数字、分位和 evidence refs；不得引入任何新的数据、阈值或概率。引用数字时优先使用分位表述；输入中标记为 audit-only 或 supporting_only 的字段不得作为正文中的数值依据。三条主要理由每条必须至少带一个方括号标注的 evidence_ref（例如 [L1.get_10y_real_rate]）——这是硬要求，一个都没有等于整段作废；其余断言可以不标，但凡是标了的必须真实存在于输入中。
> - 语言像一位克制的研究员向同事口头汇报：完整句子、因果连贯；不用列表、不用小标题、不堆术语；专业术语第一次出现时用半句话解释它是什么。
> - 不确定的就写不确定。
>
> （机器校验带 300-1300 字符，`contracts.py::_validate_reasoned_verdict_length`；宽于提示词规范带，作绊线不作风格尺。）

3. 正文校验（claim-gate 同款纪律，新函数，接在 final 校验链上）：解析 `reasoned_verdict` 中全部 `[...]` 标注 → 每个必须能在本 run 的 evidence registry / valid refs 中解析（复用工单 #13 的 ref 规范化兜底）；出现无法解析的 ref → 不阻断发布，写入降级 note `reasoned_verdict_unresolved_refs`；正文中出现"输入字段外的新数字"不做机器判定（无可靠手段），由 Fable 验收时人工抽查。
4. 渲染：门脸卡渲染 `reasoned_verdict` 为正文段落，`[ref]` 标注渲染为可点击 ref 链接（R2 未完成时先渲染为现有 ref-chip 样式）。

验收标准：① mock 引擎单测（合法正文通过、超长/无 ref 正文触发对应 note）；② fresh run 或重放中 `final_adjudication.json.reasoned_verdict` 非空且 ref 全部可解析；③ Fable 人工审读正文质量（总分总、承认最强异议、无编造数字）。

## WO-R4 受控调查执行器（stage-2 去 stub 化）

状态：✅ **验收通过（2026-07-18 第二轮验收，Fable 裁决）**。Fable 亲读三份真实调查报告：两份（AI 新闻确认 `inv_e75e`、盈利消化估值 `inv_f999`）完全合格——诚实、逐条带材料编号、"无法确认"清单精确。信用报告 `inv_36056cb391a3` 的"语义倒置"裁定为**格式歧义而非实质错误**：该条实际是"扩散恐惧被材料削弱"的合法挑战，只是先写了反驳结论、后名被挑战主张，且下游降级事件为保守的 kept_unresolved（主线降为争议状态，方向正确，无污染）。处置：接受本单；调查员提示词已由 Fable 加一行澄清（claims_supported/challenged 须先点名原主张再接材料依据，challenged 放被削弱的主张而非反驳结论——`prompts/controlled_investigator.md` 已改），下次 live run 验证。历史意义记录：`downgrade_or_split_events` 自机制建成以来**首次开火**（17 个 run 恒零 → 1）。原 Codex 状态行存档：（2026-07-18 07:10，Codex）代码与测试已完成：固定提示词逐字一致；仅装配成功读取且实际被 `[M#]` 引用的 run 内 JSON（单份 ≤4000、总量 ≤12000，带闭合边界）；forbidden/越界、默认开关、两次失败回退、来源权限、引用与 limits 诚实性、Bridge V2/competition 降级链均有测试，`743 passed, 58 warnings in 54.34s`。真实验收件 `output/analysis/vnext/20260715_001617_r4_ship` 的三份报告均为 non-stub，审计无残留 error，Bridge V2 `changed_judgment_count=3`，competition `downgrade_or_split_events=1`；但信用报告 `inv_36056cb391a3.json` 两轮真实生成仍把受材料支持的“尚未扩散/扩散风险可能被高估”写进 `claims_challenged`，字段语义倒置，未通过 Fable 人工审读标准。偏离：为保留固定提示词且避免问题特化硬编码，未继续放宽/改写合约，建议 Fable 决定是否接受该报告、调整提示词或另开通用语义判别工单；本单按总纪律记录阻塞并继续后续工单。
目标：三份"本轮未执行真实调查"的罐头报告变成真实的受限调查，激活非单调降级链路。

改动点：

1. 新建 `prompts/controlled_investigator.md`，内容如下（**原样使用，不得改写**）：

> 你是一名受控调查员。综合链在推理时遇到了一个它自己无法裁决的问题，把这个问题和一小包允许你阅读的材料交给你。你的任务只有一个：根据这包材料，诚实回答这个问题能确认什么、能挑战什么、无法确认什么。
>
> 铁律：
> - 你只能依据下面给出的材料原文推理。材料里没有的事实，一律写进"无法确认"，不许猜、不许补、不许用你的常识填空。
> - 你不知道、也不需要知道系统当前的判断是什么。不要试图讨好任何立场。
> - 数字、分位、日期只能从材料里逐字引用；禁止创造任何新数字、新阈值、新概率。
> - 每条发现都要标注它依据的材料编号。支持性发现和挑战性发现分开列，不许合并成"总体来看"式的和稀泥。
> - 如果材料整体不足以回答问题，最有价值的输出就是把"缺什么才能回答"写清楚。
>
> 输出 JSON，字段与含义：
> - `finding`：两三句话的核心回答（能确认什么/挑战什么/都不能则明说）。
> - `claims_supported`：材料确实支持的具体主张列表（每条附材料编号）。
> - `claims_challenged`：材料确实挑战的具体主张列表（每条附材料编号）。
> - 这两个字段里的每一条，都必须先原样写出【被支持/被挑战的那个主张本身】（原话或紧凑转述），再用破折号接材料如何支持/削弱它。claims_challenged 放的是被材料削弱的主张，不是你自己的反驳结论。【v2 澄清行，2026-07-18 Fable 增补，与 prompts/controlled_investigator.md 现行文本一致】
> - `counter_evidence_refs`：构成挑战的材料引用列表。
> - `cannot_establish`：无法确认的事项列表（含"缺什么才能确认"）。
> - `confidence`：low / medium / high，以材料的直接程度为准，不以措辞气势为准。
> - `limits`：本次调查的边界（材料范围、时效、你没有做什么）。

2. `orchestrator.py::_build_investigation_report`（:1103-1154）改造：
   - 新增材料装配：把 `spec.allowed_context_refs` 指向的 run 内 JSON 做**内容摘录**（替换现在只读顶层 key 名的 `_read_allowed_context_notes`）：每个 ref 摘录 ≤ 4000 字符（优先取与 `message.question` 关键词命中的顶层块，无命中则取文件头部），总量 ≤ 12000 字符，材料按 `[M1]`/`[M2]` 编号。forbidden refs 绝不装配（沿用现有 resolve 校验，:1156-1178 的越界拒绝逻辑保留）。
   - LLM 调用：`self.llm_engine.call_with_fallback(prompt, stage_name="controlled_investigation")`（调用模式对齐 :3601-3607）；输出按 `InvestigationReport` 合约解析，`is_deterministic_stub=False`；解析失败重试一次，再失败则**回退现有 stub 报告**并在 `limits` 追加 `llm_investigation_failed_fell_back_to_stub`（管线永不因调查失败而崩）。
   - 总开关：环境变量 `CONTROLLED_INVESTIGATION_LLM_ENABLED`（默认开），关闭时行为与现状完全一致（保留 stub 路径就是关闭态实现）。
   - 每 run 上限沿用 router 的 `max_agent_specs=3`，每份调查一次 LLM 调用、零外部工具（v1 只做 run 内 artifact 调查）。
3. 下游自动激活确认（不需要改代码，需要测试锁定）：`_build_adjudication_change_records`（:1660-1694）在收到非 stub 且 `claims_challenged` 非空的报告时生成降级记录；`_build_bridge_v2`（:1225-1269）吸收真实 `cannot_establish`。

验收标准：① mock 引擎单测四件套：合法输出→`is_deterministic_stub=false`；含 `claims_challenged` 的 fixture→`downgrade_or_split_events` 首次非空（历史 17 run 恒零的机制首次开火）；引擎两次失败→回退 stub 且带 fallback note；forbidden ref 出现在装配请求→拒绝。② fresh run：`investigation_reports/*.json` 中 `limits` 不再含 `no_real_investigation_performed`（除非真回退）；`prompt_audit` 落盘调查 prompt 供 Fable 复查。③ Fable 亲读三份真实调查报告裁决质量。

## WO-R5 新闻层 Phase 1：官方事件日历级底账 + 三处硬伤修复

状态：✅ **施工完成（2026-07-18 08:21，Codex；按本波整批纪律未提交）**。Phase 0 已先备份 Clash Verge 原配置至 `clash-verge.yaml.backup_20260718_075019`，且只在 `data.sec.gov` 规则后追加 `www.federalreserve.gov` / `www.bls.gov` / `www.bea.gov` 三条同路由规则，配置校验、热重载和运行规则表核对均通过，FRED、IPRoyal 与其他规则未动。代码已闭环 45 天 `collected_at` 锚、无默认 symbols、Wind M7 实体门与 `aggregator_report`、Fed/BLS/BEA/M7/Nasdaq 日历、`topic:*` 标签、来源性质分级、ICS 时间依据、过去/未来配额，以及 `scheduled_future_events` 与通用 `events` 的物理隔离；最终 live 产物 `output/analysis/vnext/wo_r5_live_20260718_0823` 中 Fed/BLS/BEA `source_errors=0`、2024 泄漏=0、通用 events 未来项=0、独立未来日程=21（BLS/BEA 各保留 4 条未来项）、无默认实体误标，reviewer 无剩余 Critical/Important。最终 `767 passed, 58 warnings in 36.80s`，`git diff --check` 通过。偏离/如实记录：Nasdaq 候选源超时、Alpha Vantage 未启用、Wind 实体门丢弃 7 条无匹配材料；均保留在 `source_errors`，未吞错，未改 R6/R8。
目标："官方事件底账"名副其实；时间纪律与实体纪律的三个真 bug 修死。

改动点（主文件 `src/news_event_ledger.py`，涉及 `event_narrative_ledger.py` 消费端）：

1. **时间窗旁路修死**（:599-616）：`effective_date` 为空时不再跳过窗口过滤；改用"采集时刻"作锚执行同样的 45 天回看截断，并在 governance 里写明 `window_anchor: collected_at`。新增反向断言测试：无 effective_date 时，两年前的事件必须被过滤。
2. **实体兜底误标修死**（:928 及各采集分支）：`_symbols_from_text` 无命中时不再回退到 source 配置的默认 symbols；`symbols=[]` 并把 relevance 降为最低档。Wind 公司公告查询结果新增实体门：标题或正文必须命中 M7 公司名/代码之一，否则整条丢弃并计入 `dropped_no_entity_match`。Mountview 案例做成回归 fixture。
3. **source_tier 纠偏**：Wind 公司公告查询的产物不得再标 `company_disclosure`（那是 SEC/官方披露的档位）；改标 `aggregator_report`。`event_narrative_ledger._materiality`（:654-664）同步调整：`aggregator_report` 不再凭 family 关键词自动拿 high。
4. **官方事件日历采集**（新增函数，进同一底账）：FOMC 会议日历（federalreserve.gov FOMC calendars 页）、BLS 发布日历（bls.gov/schedule/news_release）、BEA 发布日历、M7 财报日（复用 `get_m7_earnings_blackout_calendar` 的日程来源，转为事件条目）、Nasdaq 指数公告（候选源，失败要如实进 source_errors，不硬保证）。日历事件字段：`event_type=official_calendar`、`event_date`（事件发生日，与 `published_at` 分开）、`source_tier=official`。PIT：`event_date > effective_date` 的未来日历项要保留但标 `scheduled_future`，不得被当作已发生事件计入 mainline。
5. **标签重命名**：源配置 `relevance_tags` 中的 `L1`-`L5` 值全部改为 `topic:macro_rates` / `topic:credit_vol` / `topic:index_structure` / `topic:valuation_earnings` / `topic:trend_execution`；grep 全部消费方同步（`news_layer_analyzer.py` 的 `_event_family` 等）。此后新闻子系统里不再出现 L1-L5 字样。

验收标准：① 单测覆盖 1-3 的三个反向断言 + 日历事件 PIT 分界；② Phase 0 完成后 live 跑一次：`source_errors` 中 Fed/BLS/BEA 清零、底账出现 `official_calendar` 事件、无 2024 年泄漏、无默认 symbols 误标；③ 全库 grep 确认新闻文件零 `L1`-`L5` 标签残留。

## WO-R6 新闻层 Phase 2：LLM 事件卡（采集轻、裁决深）

状态：✅ **验收通过（2026-07-18 晚，Fable 亲验）**。786 测试亲跑全绿；`event_refs={}` 与三隔离闸门亲验未动；7 张合格卡中亲读 5 张——事实/推断分离、机制假设化（九渠道枚举）、弱来源"据报道"降档、纯标题材料"未读全文降级阅读"、无关联材料诚实输出"关联不足"，纪律全部到位；最富数字的 Robinhood 卡 5 个数字逐一核对全部存在于源材料（无编造）；被拒 Kimi 卡亲验拒收正当（事实层混入材料外二选一分类，绊线精确命中）。supports/refutes 引用的假说 ID（hyp_base/CTH_01）与本 run 真实假说对应。原 Codex 状态行存档：（2026-07-18 18:24 施工完成）`EventInterpretationCard`、逐字提示词、三触发/每 run 10 张上限、逐卡+汇总 artifact、第三层只携带不裁决、外部对照完整卡渲染与三条隔离回归均已落地；唯一 live（DeepSeek Flash，10 次、22,467 tokens）最终收口为 7 张合格、3 张因弱来源首句未归因或事实摘要加入材料外分类而拒绝，`analysis_packet.event_refs={}`，live/指定旧 run brief 均实际重生成，最终 `786 passed, 58 warnings in 55.32s`，reviewer 无剩余 Critical/Important。偏离/如实记录：live 首轮因过窄 validator 仅收 1 张，修正英文月份/单位换算假阳性后只复用同轮 raw response 离线重校验，另在复核中剔除 1 张事实层混入推断的 Kimi 卡，additional API calls=0；未采用不可靠的通用“新增数字”字符串裁决，仅保留显式正负号反转与材料外二选一分类绊线，所有自然语言卡仍需 Fable 人工抽读。
目标：进入主线或被追问的事件获得真正的模型解读卡；其余事件保持事实底账。

改动点：

1. `contracts.py` 新增 `EventInterpretationCard`：`event_id`、`fact_summary`（事实与解读分离）、`interpretation`、`entities`、`event_type`、`mechanism_hypothesis`（复用 `affected_financial_links` 九值枚举 + 一句机制假设）、`supports_hypotheses` / `refutes_hypotheses`（引用 hypothesis_id）、`limitations`、`needs_data_confirmation`、`upgrade_candidate: bool`、护照块（source/tier/published_at/event_date/effective_date）。
2. 触发规则（不是全量解读）：仅对 ① 进入 mainline 的事件、② 被 `event_challenge`/`observation_inquiry` 消息引用的事件、③ `official_calendar` 当日落地事件，生成解读卡；每 run 上限 10 张。
3. 新建 `prompts/event_card_interpreter.md`（**原样使用，不得改写**）：

> 你是外部世界材料层的解读员。给你一条已经采集好的事件材料（标题、来源、日期、正文摘录），你的任务是把它变成一张对投研有用的结构化卡片。
>
> 铁律：
> - 事实和解读必须分开写。`fact_summary` 里只许出现材料里逐字有的东西；你的推断全部放进 `interpretation` 和 `mechanism_hypothesis`。
> - 机制只能写成假设："该事件可能通过××渠道影响××"，并从给定的九个金融传导渠道里选择；禁止写成已经发生的因果。
> - 这张卡永远不能证明市场必须涨或必须跌。它能做的最多是：为某个竞争假说提供一条解释线索，或者对某个假说提出一个待验证的挑战。把这一点落实在 supports/refutes 字段里，并在 `needs_data_confirmation` 写清"要哪条数据来确认"。
> - 来源不是官方披露的，解读措辞必须降一档（"据报道""该媒体称"）。材料只有标题没有正文的，卡片必须在 `limitations` 声明"未读全文，降级阅读"。
> - 与纳指 100 没有可说明关联的事件，诚实输出 `interpretation: 与判断对象关联不足`，不要硬找联系。

4. 渲染：外部对照章节中，有解读卡的事件渲染完整卡（事实/解读/机制假设/需要确认），无卡事件保持 R1 的事实行。R1 加的"重建中"说明文案撤下。
5. 边界不变：解读卡进 `event_*` artifact 与第三层，不进 L1-L5 packet，不成为 evidence_ref（三处闸门不动）。

验收标准：① mock 单测（字段完整性、事实/解读分离断言、九渠道枚举校验、上限 10 张）；② live 跑一次，Fable 抽读 ≥5 张卡：无编造、无越权措辞、弱来源降档到位；③ `analysis_packet.json.event_refs` 仍为空。

## WO-R7 Thesis 强制回应竞争假说（小单）

状态：✅ **施工完成（2026-07-18 07:23，Codex）**。`HypothesisResponse` 合约、Thesis candidate 逐一回应校验、reject 正式 ref 校验、旧 checkpoint 拒绝复用、治理窄包/Reviser 全链透传与固定提示词均已落地；真实 fresh Thesis 产物 `output/analysis/vnext/20260715_001617_r7_thesis` 中 2 个 candidate 各有且仅有 1 个 response，唯一 reject 带 5 条且均属于 `evidence_index`，最终全量 `748 passed, 58 warnings in 55.28s`。偏离：为保护原 run，真实验证采用原 `synthesis_packet.json` 的独立 Thesis 重放；按工单约定未提前修改 R2 报告渲染。
改动点：① `contracts.py` `ThesisDraft` 增加 `hypothesis_responses: List[HypothesisResponse]`（`hypothesis_id`、`verdict`: `accept_and_revise`/`absorb_partially`/`reject`、`reasoning`、`evidence_refs`）；② `prompts/thesis_builder.md` 输出要求处插入（**原样使用**）：

> ## 对竞争假说的强制回应
> `synthesis_packet.competing_hypotheses` 里每一个 status 为 candidate 的假说，你必须在 `hypothesis_responses` 里逐一回应，三选一：接受并修正判断（accept_and_revise）、部分吸收（absorb_partially）、驳回（reject）。驳回必须引用具体的反证 evidence_ref，不许用"证据不足"四个字一笔带过——证据不足时的诚实选项是 absorb_partially 并写明缺哪条证据。你的主论点如果无法回应某个假说最强的那条证据，就不许假装没看见它。

③ orchestrator 透传 + schema guard 容忍；④ R2 的反方章节改读该字段（若 R2 未开工，渲染留待 R2）。
验收标准：单测 + fresh run 中每个 candidate 都有对应 response 且 reject 均带 refs。

## WO-R8 第三层真裁决（范围锁定，暂不开工）

依赖 R4 + R6 验收。范围：`integrated_synthesis_report.py::_main_judgment`（:238-274）从两句模板改为 LLM 阶段，消费纯数据 final + 事件卡 + 调查回答，按认识论报告 §8.2 标准判断结构输出，显式区分数据支持/事件支持/综合解释/未解释项；`conflict_matrix` 的 `data_side` 从常量改为具体数据引用；降级分支保留（事件材料不足→声明并以数据为主）。提示词由 Fable 在 R4/R6 验收后交付。门脸卡署名从 final_adjudication 切换到第三层裁决的开关也在本单（切换条件：R4+R6+R8 全部验收）。

---

## 验收协议

每单完成 → Codex 在本文件对应"状态"行更新并附提交号 → Fable 按各单验收标准逐项复核（含亲跑测试、亲读 LLM 产物）→ 通过后由 Fable 统一更新 WORK_LOG/NEXT_STEPS/人话进度报告。R2 的 CSS（slate_v3.css）与 R8 的提示词是 Fable 的交付物，Codex 遇到缺失时留钩子继续，不要代写。
