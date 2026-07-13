# 施工断点台账（2026-07-11 起）

用途：额度中断 / 会话切换后的无损续接。任何 agent 接手前先读本文件 + `NEXT_STEPS.md` 锚点。
维护规则：每完成一项就更新本文件；单线程小步走（同一时间最多一个子任务在飞）；子agent 工单必须自包含并引用本文件。

## 已完成（截至 2026-07-11 深夜）

- 北极星改写 + 冻结解除：`13e8b77`（CLAUDE.md/PRODUCT.md）
- Codex 未提交 4,500 行全部完成"分包审核→修复→提交"：
  - `35a7d57` checker 单层及格线（含 7/9 run 回放验证）
  - `dd81c58` 文档包 + .codex 配置
  - `49df8b2` 包③ 采集修复（含 A/D off-by-one、FRED 载荷矛盾等 3 项审后修复）
  - `860971d` 包④+② L4 权限链与 PIT 契约（含 MetricAuthority 错位、闸门回退等 5 项审后修复）
  - `7c6f908` 包⑤ 报告呈现（含"补偿越厚"违规脚注清理）
  - `18fec6d` 包⑥+② 编排与 prompt（layer_scope 按法典放宽、prompt 缺失显式报错、嵌套旧 prompt 目录删除）
  - `b6d4532` 五份第一性原理审计报告归档
- 全量测试 522 通过。
- **首次推送 main（2026-07-12）**：`323bc88` 快进合并至 main 并推送 origin，推送前全量 523 测试通过。此后每个里程碑（一批工单验收完）合并推送一次。
- U1 一阶段结论：层级证据敏感（强阳性）、Bridge 矛盾识别真实、**最终动作层黏性存疑（谨慎吸引子假说，待二阶段判定）**；DataIntegrity 对数值篡改零反应（重算校验带的依据）；P1 的 claim_gate 通过率 1/8 显示 claim 校验能抓数据内部矛盾。

## U1 实验与 prompt 重写：已完结（2026-07-12 凌晨）

- **U1 全部 10 个 run 完成，完整结论见本目录 `U1_RESULTS.md`**（脚本与改动清单在 `u1/`）。要点：层级证据驱动强阳性；旧 prompt 动作层被"五重合取门 × 盈利数据永久缺失"结构性锁死在谨慎区，叠加范文姿态锚定。
- **Prompt 重写已应用并提交（`2443be5`），A/B 验证双达标**：新 prompt × 利多世界 → 主导面 opportunity、"赔率中性偏有利"、持仓+对冲的建设性动作；新 prompt × 真实快照 → 仍防御且更果断，无过度矫正。赔率判断变为具名记分卡，矛盾 ID 摆脱范例锚定。
- **注意（下一次正式 run 的观察点）**：新 prompt 在真实数据下的动作比旧版更果断（"降高贝塔、20-30% 现金" vs 旧"维持纪律"）——姿态校准让两个方向都更敢下结论，正式使用时需人工确认这种果断与用户风险偏好匹配（`config/user_decision_profile.json` 阈值仍是草案，工单队列已有）。

## 工单队列（按优先级；每单一提交）

**2026-07-13 用户拍板与新事实**：① 死代码拍板砍除 → #8 已派 Codex（先证明零引用再删，范围四处，inquiry 子系统明确排除）；② 档案馆定时 → launchd `com.ndx.vintage-archiver` 已装（每日 09:30 本地，日志 output/logs/vintage_archiver.log，当日点火实测 15/15 成功；机器睡眠会补跑、关机则跳过当日）；③ SEC 代理 → 用户拍板"暂缓、要教程"，教程已在对话给出，通了之后再做 SEC 主路验证+capex 官方源升级+回测 PIT 解锁；④ #17 决策画像 → 权威来源改为用户 IPS（个人投资政策书 2026-06-29 草案），设计冻结：真实参数只进 gitignored `config/user_decision_profile.local.json`，展示层不渲染金额，翻译为确定性模板（无 LLM）——已派 Sonnet；⑤ **新发现：GitHub 仓库为 PUBLIC**——个人金额入库为红线（已写进 #17 设计）；是否转 private 待用户拍板（`gh repo edit aidianchi/NDX_VNEXT --visibility private --accept-visibility-change-consequences` 一条命令）。
18. **Forward PE 双路恢复（2026-07-13 立案，用户方向确认）**：用户问"HoM 是最可行的 forward PE 来源，就该以它为准？"——判决：升级但不独尊。① History of Market forward PE 从 `validation_only` 升为"第三方参考锚"（authority 仍 `third_party_bloomberg_attribution_unverified`，usage 升 supporting/core 视交叉验证结果，不得冒充官方）；② 自算第二路：NDX 价格 ÷ 前 15 权重股 yfinance forward EPS 聚合（vintage 档案已每日采集该原料），方法透明可重算（recompute belt 配方同步）；③ 两路互相咬合（偏差<容差）→ 置信度升级规则；持续背离→报告如实呈现分歧。待开工。

1. **discipline_side 渲染区分 ✅ 完成（2026-07-12，`7531721`）**：读者纪律清单已按 side×status 分别渲染（risk/sell 满足 → 红色"风险已触发/卖出条件已成立"，buy 满足 → 绿，hold → watch），含测试。
2. **校准闭环通电 ✅ 完成（2026-07-12，Fable 验收）**：`outcome_scoring_runner.py` 批量打分器（扫描 vNext run → ≥20 天成熟门槛 → 复用 outcome_review 判定 → per-run `claim_outcome_scores.json` + 幂等 append `output/state_ledger/claim_outcome_ledger.jsonl`）+ 7 项离线测试，530 全绿（Fable 亲跑复核）。实树验证：15 个候选 run 全部"太年轻"被诚实跳过（未编造判定）；判定语义经受控 fixture 三样例复核（bullish 遇 T+20 -20% → falsifier_triggered；risk 主张 → consistent；无方向陈述 → not_scorable）。**遗留**：首次真实成熟 run 打分待 2026-07-27 后执行（`20260707_163359` 过门槛时）并人工复核；注意 20 为自然日、T+20 为交易日（≈28 自然日），pending 标注已正确处理该差异。
3. **独立重算校验带 ✅ 完成（2026-07-12，Fable 验收）**：`src/recompute_belt.py`（纯 stdlib 第二本账，零管线 import）重算分位/比率/均线/动量 + 量级哨兵；checker 接入硬闸门（critical deviation → blocked；standard 只记录；`RECOMPUTE_BELT_ENABLED` 总开关；Fable 加固：带自身崩溃不炸闸门、留修带 note）；`main.py` 落盘 `recompute_report.json`。实跑 live 快照：checked=95, matched=34, deviations=0, missing_raw=61（诚实清单）, coverage=35.8%；Damodaran 分位（25.0/43.3）与净流动性（5955.78）两本账咬合；注入式验证（分位篡改、单位混用）均被抓获。546 测试全绿。**遗留（后续工单）**：RSI/MACD/ADX 等 15 项技术指标与 SMA50-200 因快照只存 30 天收盘价无法重算——若要覆盖需采集层把更长原始序列写入快照。
4. **证据菜单再平衡**（金融层最大缺口，见 audit_B）：AI 资本开支周期代理 ✅ **完成（2026-07-12，Fable 验收）**——`get_m7_capex_cycle` 双通道（SEC XBRL 主路 filed_date 级 PIT + yfinance 季度现金流备胎 `pit_safe=false` 仅限 live、回测禁用），全链接线（collector/packet/canon/l4 prompt/data_evidence/recompute 量级哨兵）+ RESEARCH_CANON 判读卡；实跑 7/7 公司出数，M7 2026Q1 合计 $135.5B、YoY +75.52%（可比 6/7，NVDA 财季错位正确排除），权限诚实降级 supporting_only 直至 SEC 复活；565 测试全绿。VIX 期限结构 ✅ **完成（2026-07-12，Fable 验收）**——`get_vix_term_structure`（^VIX/^VIX3M 比值+状态判定±0.5%缓冲带+5y/10y 分位，^VIX6M 观察腿；payload 自带 2513 天原始序列，recompute_belt 配方独立重算命中 93.6/87.5；权限双重编码：倒挂=supporting_only 风险确认、正挂=not_bullish_evidence 防越权；2024-08-05 套息平仓日回测验证倒挂 0.874/1.7 分位吻合史实）；--collect-only 全链实跑通过，577 测试全绿。
   fed funds futures 探源结论（2026-07-12）：yfinance ZQ 单月合约可行（18 个月远期、单合约历史回溯多年）但远月流动性极薄（第 18 月日均 2 张=挂牌价），FRED 无前瞻序列，CME 官网（含 FedWatch）全机不可达（同 SEC 模式）；建议先做缩水版（N月隐含平均利率+曲线斜率，复杂度≈VIX 期限结构），FedWatch 级概率算法留独立工单，MetricAuthority 须按月份距离/成交量分级。
   遗留：fed funds futures 缩水版、回购与财报静默期日历；完成后做多空证据源对称性审计。
   **盈利预期数据源判决（2026-07-12 凌晨实测，Fable 亲测）**：Wind 路线判死——NDX.GI 指数级"没找到数据"；成分股级对照实验证明机制通（茅台返回真实双时点一致预测 EPS 31.7446/31.7267）但美股无权限（AAPL 同问法返回 null）。PIT 契约代码保留（防伪门槛正确），数据源改道：① **立即启动自建 vintage 档案**——每日/每周快照 yfinance+FMP 的当前一致预期（.env 已有 FMP key），30-90 天后即有可用的自产时点序列，零成本且完全可控；② 评估 FMP/Finnhub 现成的预期历史端点覆盖度（tools_finnhub.py 死码正好是这个用途，可部分复活）；③ Wind 继续做估值主锚（PE/PB/PS 正常），只放弃其美股盈利预期。
   **追加（2026-07-12 Fable 亲测）：修正斜率不必等档案积累**——yfinance `Ticker.eps_trend` 免费返回每只美股"current / 7d / 30d / 60d / 90d ago"的一致预期 EPS（实测 AAPL/MSFT/NVDA 数据完好，NVDA +1y EPS 90 天内 11.11→12.76），`eps_revisions` 另给上/下修分析师家数。指数级做法：取 NDX 前十大权重股聚合（权重覆盖 >50%）。定位：yfinance eps_trend = 立即可用的 90 天后视镜（authority 标 third_party_unofficial，需防字段漂移）；自建 vintage 档案降级为加固层（对冲雅虎黑箱/断供 + 未来把后视镜延长到 90 天以上）；深回测所需的多年期历史 vintage 仍无免费来源（IBES 收费），评估 FMP/Finnhub earnings-surprise 历史作部分替代。
   **档案已启动（2026-07-12，Fable 验收）**：`src/vintage_archiver.py` 独立脚本 + 5 项离线测试；首日快照 `output/vintage_archive/20260712/`（15/15 yfinance、11/15 FMP，MU/GOOG/AVGO/AMAT 免费层 402；Invesco 持仓 406 → 静态 top15 回退如实标注）。隔离观察数据，未升级数据源、不得作 evidence_ref。**定时任务未安装**——建议 crontab：`30 21 * * 1-5 cd /Users/aidianchi/Desktop/ndx_mac && .venv/bin/python -m src.vintage_archiver >> output/logs/vintage_archiver.log 2>&1`（美股收盘后，时区自行校准）；装不装由用户拍板。注意点：AAPL eps_trend `60daysAgo=0.0` 是 yfinance 原始值——第三方非官方源的字段漂移风险实例，档案原样保存不粉饰。
5. **报告层小修 ✅ 完成（2026-07-12，Codex gpt-5.4 施工 / Fable diff 级验收）**：`shared_falsifiers` 改严格全等（部分重合不再冒充"共用"）；`missing_groups` 市场状态组缺图同等提示（未发现旧行为的书面理由，径直改对称）；leading 假设卡加"领先仅表示当前证据权重，非确定结论"固定提示。583 全绿 + 用 E2E run 实际重生成 brief 验证不崩。
6. **checker 可观测性 ✅ 完成（2026-07-12，Codex 施工 gpt-5.4 / Fable 验收）**：`main.py._persist_checker_input` 落盘 `checker_input_snapshot.json` + `checker_input_sha256`（sort_keys 标准化 JSON 哈希，回放工具须沿用同一约定）；三个边界回归测试（恰好 50% 不弱层、total<3 豁免、快照+哈希正确）。580 全绿（Fable 亲跑）。
7. **Manual/Wind ERP 回退通道**：`manual_data.py:99-119` 允许 Damodaran 槽位被 Wind 人工值填充，弱化三槽位独立性——评估收紧或显式标注。
8. **死代码与僵尸子系统 ✅ 部分完成（2026-07-13，用户拍板砍除 / Codex 施工 / Fable 验收）**：tools_finnhub.py（758 行）+ tools_simfin.py（630 行）+ tools.py 死链（75 行）+ smoke 测试例外名单（18 行）共 1,481 行删除，零引用 grep 证明存档；598 全绿（Fable 亲跑）。**重要更正：`data_manager.py` 陈旧度检测不是孤儿**——Codex 实测证明其有真实调用路径（tools_L1:182、chart_generator:1354）且能触发（30 天旧缓存 × 7 天阈值），原体检报告此条为误报，予以保留。**遗留**：受控调查反馈环恒零产出（`orchestrator.py` `is_deterministic_stub` 写死 True）——砍除或修复仍待主审设计决策，不属机械清除范围。
9. **巨型文件手术**：orchestrator.py 按 audit_C 方案拆 stage_runner / prompt_composer / claim_verification / stage_io / payload_normalizer；tools_L4.py 按数据源拆模块。
10. **fresh 完整 vNext E2E 验收 ✅ 完成（2026-07-12，run `20260712_221916`，worker 逐项清单 + Fable 亲审裁决）**：publishable（DataIntegrity 93.2%、blocking 空、belt 0 偏差在闸门内落盘）；claim gate 7/8 verified（唯一 downgrade 为真命中：claim 谈估值/信用而 refs 是两个 L5 技术指标 → `only_weak_or_derived_evidence_refs`）；两个新指标全链权限纪律零越权（capex 被诚实按"低置信、未经 SEC 验证"处理，VIX 期限结构只作防自满信号）；Critic 抓住并修正一次真实过度悲观（低恐慌被误读为风险未定价）；两条 typed conflicts 全程存活；四份报告（brief/workbench/prompt inspector/legacy）正常生成。新 prompt 首次正式姿态"赔率中性偏不利、防御等待"经 Fable 审：证据驱动、双向具名、失效条件明确——合格。遗留观察：`publish_quality_status=review_required`（Schema Guard 两处疑似误报，见 #15）；姿态与用户风险偏好的匹配待用户读报告反馈。
11. **旧快照回放兼容性（工单#2 施工中发现，2026-07-12）**：① `data_collected_v9_20250409.json` / `20240805.json` 回放被 L3 `available_without_meaningful_value` hard block（`data_evidence.py:436`，四个广度函数）——证据合约收紧后与旧快照不兼容，影响历史回测能力与 #10 E2E；② 回测模式下 Wind 估值函数标 `backtest_skipped_unsupported_function` → L4 1/6 跌破单层及格线，任何日期的回测都无法出发布产物（归 #4 处置）；③ `data_collected_v9_20260509.json` 原为旧 collector schema，已用 `--collect-only --date 2026-05-09` 刷新（gitignored）。
12. **SEC 官方数据通道全机不可达（2026-07-12 Fable 实测定性）**：主机 curl `data.sec.gov` SSL_ERROR_SYSCALL（worker 沙箱、WebFetch 同败，而 FRED/Yahoo/GitHub 全通=定向不可达，疑地区封锁）；2026-07-10 真实快照 xbrl/sec_/edgar/10-K 零足迹 → 现有 `_fetch_sec_xbrl_summary`（tools_L4.py:2497）及其 official checks 在生产中从未成功过，"官方申报事实"通道一直是静默空转。短期处置：capex 指标已加 yfinance 诚实降级备胎（pit_safe=false、回测只认 SEC）。**待用户拍板**：是否配置代理/VPN 让 SEC 通道复活（一次性网络决定，能同时救活既有 official checks 与 capex 主路、并解锁回测级 PIT capex 数据）。
13. **claim gate 稳定化 ✅ 完成（2026-07-13，Sonnet 诊断+施工 / Fable 亲自重放验收）**：诊断翻转原假设——`_verify_claim_entry` 本是纯函数，"跳动"实为它对上游 LLM 引用清单噪音过度敏感：顺带多引一条 validation_only 字段（baseline_r2）或裸 mixed 容器 ref（p5）即无条件降级 6/8 条有独立强证据的 claim。修复：比例原则（`has_strong_support`，弱字段不得借父级强 tier 洗白）扩展到 field-authority 三分支；mixed 容器按是否含 rejected 字段硬/软二分；rejected 一律不放行；ref 规范化兜底匹配（笔误/幻觉仍计 missing）。Fable 亲自重放：baseline_r2 / p5（历史 1/8）与 E2E 全部 5 连 7/8 零方差，E2E 真命中降级原样保留。598 全绿。语义只紧不松（弱字段以前可借强 provider tier 中和 only_weak 判定，现在不能）。
14. **DataIntegrity coverage-factor 误读（E2E 钓出，已复现）**：`checker.py:66-76 _coverage_numbers` 用子串匹配 "percent"/"pct" 抓覆盖率——①"percentile" 含 "percent"，VIX 期限结构的 93.6 分位被误当 93.6% 覆盖率（factor 被压到 0.875）；② L3 四个广度函数被抓到的是配置常量 `minimum_daily_coverage_pct: 80.0` 而非实测的 `constituent_coverage_pct` 98-100%（factor 错封 0.8）。净效应：置信度低估约 2 个百分点+"覆盖率不足"叙事失真，不阻断发布。修法：只匹配已知覆盖率字段名（`*_coverage_pct`/`coverage_ratio`），排除 `minimum_`/`required_` 前缀。✅ **完成（2026-07-12，Codex gpt-5.6-luna 施工 / Fable 验收）**：白名单化 + 门槛前缀排除；真实快照置信度 93.2→95.3（Fable 亲测复现），publishable 不变；3 个新测试，586 全绿（亲跑）。
15. **Schema Guard 两处疑似误报 ✅ 完成（2026-07-13 凌晨，Sonnet 施工 / Fable diff 级验收）**：`get_equity_risk_premium` 补 MetricAuthority（level=core_allowed/derived_simple_yield_gap，reason 写死"不得冒充 Damodaran 隐含 ERP"；yield_type=supporting_only 方法元数据）；`_run_schema_guard` retained_conflicts 改两级确定性容忍（ID 并集交集 → (severity, 空白规范化 description) 语义匹配），typed_conflicts 优先避免双列表重复要求；真丢失场景仍报（有测试锁定）。E2E run 重放：两条误报消失、指标值 -1.76 复算一致。594 全绿（Fable 亲跑）。原文：① `get_equity_risk_premium` 无 MetricAuthority 注册，LLM 反复给它的 ref 加 `#level` 后缀被判 invalid（字段真实存在，值 -1.76）——修法二选一：给该老指标补 MetricAuthority 注册，或让 `valid_evidence_refs` 容忍未注册指标的真实字段；② Thesis 把 Bridge 的冲突 ID `L4_expensive_vs_L1_restrictive` 改名 `C1_expensive_vs_restrictive` 导致 exact-match 检查报"高严重度冲突丢失"（内容/严重度/含义逐字保留，Final 甚至两个 ID 都列了）——修法：冲突匹配改语义/ID 容忍。另records：8 个既有弱权限指标（get_vix/get_vxn/get_copper_gold_ratio/get_hyg_momentum/get_xly_xlp_ratio/get_crowdedness_dashboard/get_vxn_vix_ratio/get_cnn_fear_greed_index）缺 downgrade_rules，为先于本轮的存量观察。

16. **报告可读性批次二（2026-07-12 用户通读 E2E brief 后的十点反馈，真实读者校准信号）**：① hero 区"可信度"下方裸渲染 `invalidation_conditions[0]`（reporter:1723 `primary_break`）无标签——加"改判条件："前缀；② 失效条件混合双向（转多/转空）无方向标注——已改 final_adjudicator prompt 要求【转多】/【转空】前缀（Fable 亲改），reporter 需解析前缀渲染方向徽章并分组；③"跨 run 对比"改名"和上次判断比，什么变了"；④ 读者纪律清单 side="claim" 映射"研究结论"（reporter:753）读者不解——改"观察确认项（不直接触发买卖）"并加一行说明；⑤"如果发生这些事，我就改判断"区的"边界状态/必须保留（风险）"术语人话化；⑥ 该区全是风险反证、无机会侧并列——增设"上行触发"子栏（数据源=带【转多】标签的失效条件 + counter_thesis 机会项）；⑦"价格已计入什么"加"（推断，非事实——每条附证据与反证）"标注；⑧ 核心证据图固定动线（市场状态→硬约束→信用→宽度）确认为写死——保留稳定动线为设计选择，低优先级考虑"按本轮主要矛盾重排首位"。
17. **个人决策画像接线**：`config/user_decision_profile.json` 仍是草案、"个人决策翻译"区静态；需用户填三题口味问卷（见 2026-07-12 深夜对话）后把画像接入 reader 翻译区（"结合市场判断和你的画像，本轮对你意味着什么"）。阻塞在用户输入。

## Prompt 偏误审计（2026-07-11 深夜，Fable 亲自逐份审读，先于 P4 结果完成 = 盲测预测）

**总判定**：指令层意外地清醒（反模板约束、对称禁令、"双向风险"条款、干净的 system_constraints、层级 prompt 无姿态锚定），但**范例层在系统性拆台**。病不是"没原理"，是"原理写在指令里、偏误藏在范文里"，而 LLM 对上下文范例的锚定强于对指令的服从。

五个具体偏误机制（按严重度）：

1. **单一姿态范文横贯综合链**：cross_layer_bridge / thesis_builder / final_adjudicator 三份 prompt 的 JSON"结构示例"全部是恐慌市谨慎姿态的完整文案（"风险未解除，核心仓不能升级""只适合小比例试探""维持纪律，不因恐慌被动砍掉核心仓"——最后这句在 thesis 和 final 两处逐字出现）。final 示例的 three_reasons 与真实 run 输出几乎一比一。范例只教了一种"好答案的形状"。
2. **非对称举证负担**：thesis_builder 与 final_adjudicator 均规定"高赔率"须价格反映/估值ERP/信用/趋势/盈利五类证据**共同**支持才可使用；"赔率不利"零门槛。说空免费，说多要五重合取。
3. **Critic 配额制**：critic.md 质量检查强制"至少 2 个 major 问题"→ 论点真没问题也必须编；永远无法输出"该论点成立"。且两个攻击示例全是攻击乐观论断（"盈利增长强劲""已充分定价"）。
4. **置信度单尾检查**：只查"是否避免过度自信"，不查过度骑墙；且全部示例 confidence="medium" → 模式坍缩（实证：U1 七个 run 几乎全 medium）。
5. **示例矛盾 ID 锚定**：thesis/final 示例中具体写了 `valuation_discount_rate` / `panic_priced_vs_unconfirmed_risk`，而 U1 全部四个 run 输出的主要矛盾 ID 都落在 valuation_* 家族——"动态主要矛盾"疑似部分被范例 ID 锚定。

**盲测预测（写于 P4 结果揭晓前）**：P-a P4 最终动作仍落"谨慎/分批试探"桶（范例词汇表里没有建设性姿态的模板）；P-b confidence 仍是 medium；P-c 主要矛盾仍在 valuation_* 家族或凭空造出张力；P-d Critic 在 P4 上仍产出 ≥2 个 major（配额所迫）。若 P4 实际转向建设性 → 指令战胜范例，机制 1 降级，修复重心转向证据菜单。

**修复方向（待 P4 判定后立工单）**：① 三份综合 prompt 的范文改为 2-3 个对照 regime 的最小示例（恐慌-谨慎 / 教科书利多-建设性 / 混合-分歧），或退化为纯 schema 骨架+占位符；② "赔率不利"同样设具名证据合取门，或改为强制五类赔率记分卡字段；③ Critic 取消 ≥2 major 配额，允许"无重大问题"判定但强制填"幸存的最强反对意见"，补一个攻击过度谨慎论点的示例；④ confidence 定义证据语义并双尾检查；⑤ 示例中的具体 contradiction_id 改为 `<placeholder>`。

## 续接协议

撞 limit 或会话中断后：读本文件"进行中"与队列 → 检查后台进程/产物是否已完成（`ps aux | grep main.py`；`ls output/analysis/vnext/u1_*`）→ 从最小未完成项恢复。子agent 被中断时优先 SendMessage 续跑（上下文还在），失败再重开。
