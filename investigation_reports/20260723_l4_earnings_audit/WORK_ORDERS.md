# 盈利预期工单包 E1-E6（已立案）

> **状态权威声明（2026-07-23）**：本文件是调查与施工细节的历史台账。"某件事做没做完"的唯一权威是根目录 `现在.md`；本文件与 `现在.md` 冲突时以 `现在.md` 为准。

日期：2026-07-23。背景：ChatGPT 审计与 WorkBuddy 调查的对比核验见同目录 `COMPARISON.md`，终审裁决见同目录 `DECISION.md`（七项分歧逐条裁决 + P0-P3 施工顺序）。

**用户拍板（2026-07-23）**：
1. 批准 DECISION.md 的 P0-P2 方案拆成工单施工。
2. **Invesco 持仓通道已修复**：Clash Verge 分流调整——仅 Invesco 官网与持仓接口走 YKK 节点，Claude/FRED/默认代理线路不动，AI-Chain 仍为 IPRoyal-US-Exit。实测持仓接口返回 200，**108 条有效持仓，数据日期 2026-07-22**。此前 vintage_archiver 里的 406 静态兜底问题已解除（兜底逻辑仍须保留，防止代理规则日后变动）。
3. 派工模式：worker（Sonnet）或 Codex（参照 codex-first）施工；**关键部分与最终验收由 Fable 把关**。

任务号映射：T13 = E1；T14 = E4（依托 E2 的宇宙抓取）；T15 = E2 + E3 + E5。E6 后排候补，不立 T 号。

状态行（施工中更新）：
- E1 P0 语义与守恒修复：**完工，Fable 已亲验**（worker A 施工，2026-07-23 收口；关单记录见 E1 节，含两处经 Fable 拍板的偏离）
- E2 档案宇宙扩容全成分：**完工，Fable 已亲验**（worker B 施工，2026-07-23 收口；关单记录见 E2 节）
- E3 供应商回看值验证闸门：**产数完成，闸门裁决：有限通过**（worker C 产数、Fable 亲自复核并裁决，2026-07-23；细则见 E3 节闸门裁决）
- E4 全成分 NTM Forward PE 正式链：**完工，Fable 已亲验**（Codex 施工 + Fable 补注册接线，2026-07-24 收口；关单记录见 E4 节）
- E5 修正斜率/广度/分歧/覆盖家族：**完工，Fable 已亲验并做验收轮修正**（Codex 施工，2026-07-24 收口；关单记录见 E5 节，含 Fable 追加的无意义比率防线）
- E6 Trendonify daemon 端口隔离：**后排候补**（审计区对照用，不阻塞主链；禁止直接杀 19824 孤儿进程——属刘甲知识库项目，若端口隔离不可行须用户点头）

---

## E1. P0 语义与守恒修复（T13，优先级最高）

**原则**：证据缺失只能映射为置信度折减与数据边界记录，永远不能映射为方向。

四处修复：

1. **final_stance 缺失≠利空**（`src/agent_analysis/prompts/final_adjudicator.md` + orchestrator 校验器）：
   - 提示词补纪律：缺失/不可用的证据家族只能出现在数据边界与置信度说明，不得作为看多或看空的理由。
   - 代码级 claim gate（沿用 Q3/Q5 校验器先例）：stance/理由文本中"(缺失|缺乏|不可用|没有数据)"与"(放大|加剧|增加|恶化)×(风险|下行|上行)"共现即拦截，留痕 `quality_gate.notes`。
   - 末次 run 实锤样本：`output/analysis/vnext/20260719_130534/run_summary.json` final_stance"盈利证据缺失放大下行风险"。
2. **过期/audit-only 分位退出核心摘要**（`src/agent_analysis/packet_builder.py:644-664`）：
   - 分位状态为 `insufficient_history` 或来源被降级 audit-only 时，摘要行不得输出裸数字"分位=68.5"，改写"分位不可用（历史不足）"；原始值保留在审计区。
3. **`hom_available` 按 decision eligibility 统计**（`src/tools_L4.py:4854`）：原始值存在≠可用；简化路径返回字典补顶层 `availability` 字段。
4. **sidecar 报错归因**（`src/browser_sidecar.py:90-93`）：daemon 初始化失败即报 daemon 病因，不借 "cdp is reachable" 滑到 open 步才爆。fail-closed 行为本身正确，不改。

验收（Fable 亲验）：每处一条以上新测试；相关测试文件全绿；claim gate 用末次 run 的 final_stance 原文作反例测试。注意 claim gate 不得只做相邻词匹配——"盈利证据缺失，同时高估值放大下行风险"这类隔从句写法也须拦截；反事实句（"若数据补齐后风险仍放大"）不得误伤。

**关单记录（2026-07-23）**：worker A 交付四处修复，Fable 亲验后收口。验证：五个相关测试文件 83 passed（Fable 复跑）；全量 `--cache-clear` **944 passed**（前日基线 921 + E1/E2 新增测试；Fable 复跑）；claim gate 由 Fable 用五个边界探针直接调用验证（事故原句拦截、隔从句拦截、反事实放行、正常风险句放行、"缺失已记入数据边界"中性表述放行）。两处偏离字面工单、经 Fable 拍板接受：
1. **claim gate 位置与处置**：真实先例（stance_label 方向冲突检测）在 `contracts.py` 的 pydantic model_validator 而非工单所写的 orchestrator，worker 循真实先例落位；处置用 raise（fail-closed 触发重生成、并使污染的 stage checkpoint 失效）而非"清空+留痕"——因为违规藏在必填自由文本字段里，清空即留空必填字段，代改即代模型编论证。留痕形式为 stage 重试链路的报错回传，不是 quality_gate.notes。副作用：`test_stance_label` 的旧档回放测试原指向 20260719_130534（正是违规 run，现被正确拒绝），已改指干净旧档并注明原因。
2. **`hom_available` 不改定义，另立信号**：回测下 `coverage_sanity` 恒为 not_point_in_time_verified（时点纪律使然），eligibility 恒 False；若把分支选择器改成按 eligibility，一切回测里 HoM 的 Bloomberg BEst 带 caveat 结构化呈报会静默消失、退化成无来源归因的裸 unavailable，违反"诚实降级须可见"。故保留 presence 分支选择器（附注释），新增 `hom_decision_eligible` 与顶层 `availability`（available/stale，循 `get_ndx_valuation_history_of_market` 既有约定），覆盖率统计失真由 availability 字段修复。
另：分位泄漏根因比预想深一层——顶层门控字段本已正确置 null，是深扫描兜底 `_extract_percentile` 绕过门控直读 `HistoryOfMarket` 原始子字段；修复为深扫描排除 `HistoryOfMarket`/`StaleReferences`（对齐既有 `ThirdPartyChecks` 排除）。sidecar 归因修复保持 fail-closed 不变。遗留观察：`_build_simple_source_disagreement`（tools_L4 约 4869 行）系既有死代码，按纪律未动。

## E2. 档案宇宙扩容全成分（T15 子件）

**目标**：`src/vintage_archiver.py` 的采集宇宙从前 15 扩到 Invesco QQQ 全部有效持仓（实测 108 条，含非股票行须过滤），每日快照含全成分 `eps_trend`/`eps_revisions`/`earnings_estimate`/`revenue_estimate` 与官方权重。

规格：
- 持仓接口已可直连（见用户拍板 2）；保留静态兜底并如实记录 `fallback_used` 与持仓生效日期。
- 过滤规则：仅保留有有效 ticker 的股票类持仓；现金/衍生品行剔除并计数留痕。
- yfinance 批量抓取加节流与重试；单 ticker 失败不拖垮整日快照，失败清单写入当日文件。
- 快照 schema 向后兼容（`expectation_vs_realized` 等下游按 ticker 读取不受影响）；`schema_version` 递增；隔离声明（NOT promoted / MUST NOT enter L1-L5）原样保留。
- launchd 调度不动。

验收（Fable 亲验）：本地手动跑一次全量采集成功；产物结构抽查；旧快照可继续被下游读取。

**关单记录（2026-07-23）**：worker B 交付，Fable 亲验产物与测试后收口。实跑（写临时路径，未覆盖当日正式快照——mtime/大小/schema=1/15 只均确认原样）：Invesco 实时直连成功（fallback_used=False，持仓生效日 2026-07-22），108 条持仓过滤 5 条（2 条非股票类 + 3 条无 ticker）得 **103 只**（含 ASML/ARM/PDD 三只 ADR），权重覆盖合计 **99.86%**；yfinance 103/103 全部成功、零失败零缺字段；耗时 383.87s。schema_version 1→2（per_ticker 结构不变，新增 collection_summary 留痕块；README 已更新），隔离声明原样保留。静态兜底扩为 103 只实测清单（含 stale 风险注释）。下游兼容：`test_vintage_archiver.py`(14) + `test_expectation_ledger.py`(15) 共 **29 passed**（Fable 复跑确认）；grep 证实档案读取方仅 expectation_ledger 与 E3 脚本，均按键动态读取。遗留观察（非本单范围）：FMP 侧 84 只报 402（订阅不覆盖），系既有行为非回归。下一次 launchd 定时跑将首次产出全成分正式快照，次日应抽查。

## E3. 供应商回看值验证闸门（T15 子件，D4 裁决的执行）

**目标**：用自建档案给雅虎 `eps_trend` 回看字段做真实性对账，产出验证报告供 Fable 裁决"live 决策可否使用供应商回看值"。

规格：
- 纯档案分析，无需联网：对每个 D ∈ {20260719..20260723}，比较 `archive[D].eps_trend.7daysAgo` vs `archive[D-7].eps_trend.current`，逐 ticker × 周期（0q/+1q/0y/+1y）。
- 输出相对偏差分布、逐 ticker 通过率、离群清单；建议容差 |相对偏差| ≤ 1%。
- 30/60/90 天窗口档案尚不够长，最早可补验日期为 2026-08-11 / 09-10 / 10-10（工单初稿把 90 天误写为 10-20，worker 复核纠正，此处已按正确算术更新），不得外推。
- 新脚本放 `scripts/`，产物写 `investigation_reports/20260723_l4_earnings_audit/`。
- 只产报告，不改主链代码；闸门裁决由 Fable 基于真实产数做。

**闸门裁决（2026-07-23，Fable，基于真实产数）**：

产数（worker C 脚本 `scripts/validate_supplier_lookback.py`，Fable 亲自复跑脚本 + 手工复算最大离群对，全部对上）：候选 300 对 = 有效 292 + 采集失败跳过 8；|相对偏差| 中位数 0.0034%、p95 0.54%、最大 12.99%；≤1% 容差占比 96.92%；离群 9 条**非随机分布**——7 条集中在 07-23、8 条来自 TSLA/GOOG/GOOGL，恰逢财报周。典型案例：TSLA +1q 的雅虎"7 天前"值（0.62163）比我们 7 天前实拍值（0.55016）高 12.99%，说明雅虎回看锚点在密集修正期已部分吸收新修正——用它算修正斜率会**低估**斜率（偏保守方向，不是夸大方向）。

裁决：**有限通过**。
1. **档案优先原则**：自建档案覆盖到的回看窗口，一律以档案值为准计算修正指标；雅虎回看值只填补档案尚未覆盖的窗口（30d 至 08-11、60d 至 09-10、90d 至 10-10），此后逐窗口切换自产。
2. 供应商回看值进主链须带 `supplier_lookback` 溯源标签 + 逐窗口验证状态（7d=verified_with_earnings_week_caveat；30/60/90d=pending，届期用同一脚本补验后升级）。
3. **财报周防护**：ticker 处于财报窗口或隐含修正幅度异常时，该 ticker 的 supplier-lookback 派生值打低置信标记（标记不剔除），聚合指标须披露被标记权重占比。
4. 回测端永远只用自建档案（时点纪律，不变）。
5. E5 据此放行（仍等 E4 落地后派工）。

## E4. 全成分 NTM Forward PE 正式链（T14，P1 主体）

**排队中，等 E1/E2 收口后派工（Codex 或 worker，派工时按 codex-first 流程）。**

规格要点（细节见 DECISION.md P1 节）：
- 逐 ticker NTM EPS = FY1/FY2 按财年剩余月份插值，财历感知（NDX 成分股财年结尾各不相同，这是必须插值的数学理由）。
- 聚合：指数 Forward PE = 1/Σ(wᵢ × NTM盈利收益率ᵢ)，亏损成分自然进入，消除剔除偏差；权重用 Invesco 官方持仓，权重生效日随值记录并做新鲜度门。
- 覆盖率（Σw）必须随值披露；缺失成分列清单。
- 治理：正式 L4 源升级流程——RESEARCH_CANON 指标法典条目、availability 语义、DataIntegrity、单测。不复用审计用成分模型开关的旧语义（其自述"生产首选是 PIT 指数一致预期序列"，本实现即该生产路径）。
- 与 HoM（audit-only）、worldperatio/danjuan 做第三方对照，不做主锚互换。
- **用户否决边界**：前 15 算 forward PE 水平仍然禁止；本单是全成分实现，恰好消解原否决理由（重估条件"HoM 断源"已触发，见 DECISION.md）。

**关单记录（2026-07-24）**：Codex（gpt-5.6-sol，workspace-write 沙箱）施工核心实现：`src/tools_L4.py` 新增 `get_ndx_forward_pe_full_constituent`（约 545 行含 payload 治理）、持仓抓取抽为共享模块 `src/qqq_holdings.py`（vintage_archiver 改导入、14 条测试零调整全绿）、法典条目、8 条全 mock 新测试。Codex 因领地清单禁入而如实搁置采集注册（规格是 Fable 画小了领地，非施工失误）；注册接线由 Fable 亲手补齐：`tools.py` 注册表、`core/collector.py` L4 清单 + 回测跳过表（latest_only_consensus_not_used_in_backtest）、`core/evidence_families.py` 新家族 `ndx_full_constituent_forward_pe`。Fable 验收：diff 逐段审读（PIT 拒绝、NTM 插值、含负 EPS 调和聚合、新鲜度门全部符合冻结规格）；NVDA 一对 NTM 数学手工复算精确吻合（fy1_weight 差值恰为跨午夜一天的 1/365）；亲跑 live 冒烟 **value=21.698、live 直连成功 fallback_used=false、覆盖 100%、零排除、approx 占比 0%、21.4s**（Codex 冒烟中的 Invesco 406 判定为其沙箱不继承代理环境所致，非代码问题）；数值与陈旧 HoM forward 24.29（2026-05-18）同邻域、方向自洽。全量测试 **952 passed**（Fable 复跑，含注册后完整性校验）。法典条目 Fable 审读通过。

## E5. 修正斜率/广度/分歧/覆盖家族（T15 主体，P2）

**排队中，等 E3 闸门裁决 + E4 落地后派工。**

规格要点（细节见 DECISION.md P2 节）：
- 四指标：NTM 口径 30/90 日修正斜率；上修/下修广度（家数聚合）；分歧（low/high/std）；覆盖（分析师家数）。
- live 原料：雅虎回看字段（前提：E3 闸门裁决通过，带 `supplier_lookback` 标签 + 逐窗口验证状态）；回测原料：只用自建档案（时点纪律）。
- `expectation_vs_realized` 的"未使用供应商回看字段替代"注记按 D4 裁决改为双轨表述。
- 短期内全成分档案历史不足时，修正指标可用前 15 官方权重作**动量代理**（带 proxy 标签 + 覆盖率披露）——方向信号不做水平断言，不触犯前 15 否决（该否决只针对 forward PE 水平）。
- 治理：与 E4 同格的正式源升级流程。

**关单记录（2026-07-24）**：Codex（gpt-5.6-sol）施工 `get_ndx_earnings_revision_metrics`：双轨锚（±2 天档案优先/供应商回看补窗）、剥离日历漂移的冻结斜率公式、财年滚动防护、财报周双触发标记、7 天仅作两轨对照、PIT 拒绝、注册三件套自接、档案 purpose 范围化升格、expectation_ledger 注记双轨化、法典条目、8 条 mock 测试；全量 960 passed。Fable 亲验：公式/锚/滚动代码逐段审读，TSLA 斜率手工复算精确吻合（混合权重 161/365、FY1/FY2 修正率对上供应商回看原始值），冒烟数值可复现。

**验收轮抓到并修正一处真实设计缺陷（Fable 亲改）**：首版 live 冒烟 30d 斜率 −1.35%，但逐股分解发现被数据残缺统治——LIN 的 FY1"修正"为精确 −100%（现值归零残缺）、SPCX 的 FY2 为穿零 −514%、WBD 为近零基数 +216%；SPCX 一只（权重 ~1%）即独自贡献 −3.5 个百分点，把指数符号拉反。病根：比率型修正在近零基数、符号穿越处数学上无定义，原规格"标记不剔除"误把'无意义'与'真实但嘈杂'混同（该规格系 Fable 所冻结，非施工失误）。修正三道防线：①基数 < $0.25、窗口内符号穿越、或单腿变动 ≥ ±100% → `ill_defined_ratio_base` 记无效清单不入聚合（`>=`/`<=` 边界特意覆盖精确 −100% 的实况）；②幸存极端斜率按 ±50% 温莎化（保留 slope_raw，披露数量与权重占比）；③财报周低置信标记机制不变。修正后 live 复跑：**30d +2.25%（剔 5 只、温莎化 1 只、覆盖 85.7%）、90d +8.57%（剔 4 只、温莎化 4 只、覆盖 82.6%）**——符号翻正后与广度（FY1 净上修 +56.9pp）及已知上修周期方向一致。新增 2 条防线测试 + 1 条既有测试 mock 数据修正（其"翻倍"恰撞 ±100% 界，测试目的在锚日逻辑不受影响）；法典条目补"无效剔除 vs 低置信标记不得混同"段。全量 **962 passed**（Fable 复跑）。另两处 Fable 顺手治理：archiver 内部 README 模板同步范围化升格文本（否则下次归档会覆盖 Codex 写入的 README 说明，Codex 已如实上报该风险）、模板边界节与新事实对齐。遗留观察：HON 类分拆/重述导致的 −60% 级结构性断点仍以温莎化+标记形式入聚合，是否需要"结构性断点"独立识别留给真实 run 校准；SPCX/NBIS/RKLB 等新上市成分的近零基数会长期依赖该防线。

## 返工轮：只读终审退回五处发布级缺口（2026-07-24，全部修复）

用户让 Codex 对 E4/E5 做只读终审，判"主体完成、验收未通过"，退回五条。Fable 逐条对代码亲验后裁决：四条属实（#1 治理接线缺口经全库反查比终审报告所列更大——七处登记点全缺，其中 packet L4 成员表缺席意味着数据可能根本到不了 L4 分析员面前；#2 覆盖率硬门缺失；#3 ±100% 一刀切误杀可靠基数上的真实修正，与法典自己的"无意义 vs 极端但真实"分类矛盾；#5 divergence 逐股 difference 混用温莎化值，系 Fable 上轮修一半的遗留），一条（#4 Invesco 406）裁为环境差异非代码缺陷——live 直连依赖带系统代理的运行环境（本机正常环境多次实测 200，终审方沙箱无系统代理必 406 走兜底，兜底链路即为此设计）。**补充事实（终验冒烟）**：带代理环境也存在时段性 406——终验最后一跑 fallback_used=true，兜底持仓 2 天新鲜、门内可用；结论是实际健壮性保障为"静态兜底 + 新鲜度门"而非 live 必达，每日 launchd 全成分快照是持续验证点。

修复（Codex 施工、Fable 终验）：治理接线九文件齐（data_evidence 四表、packet L4 成员、deep_research_canon 双判读卡+交叉引用、l4_analyst 菜单、state_ledger 四键含 path_root=payload 机制）；E4 覆盖 <90% 硬门（unavailable 优先于 stale，value/收益率同步置空）；E5 五子块各 <70% 硬门 + 顶层 availability 仅由双斜率块决定；ill-defined 判定删 ±100% 腿、保留近零基数与符号穿越（精确 −100% 仍被符号规则覆盖，有测试锁定）；divergence difference 改原始值口径。RESEARCH_CANON 同步。新增 5 组测试，全量 **967 passed**（Fable 复跑）。live 终验由 Fable 亲跑（两指标 availability/覆盖/温莎化数正常）。经用户授权提交推送。

## E6. Trendonify daemon 端口隔离（后排候补，不立 T 号）

- 病因（已核验）：孤儿 node 进程（PID 50473，cwd `~/Desktop/刘甲知识库`）占 19824 端口；bb-browser 版本旧（0.11.5）是次要健壮性问题。
- 处置纪律：**首选本项目 daemon 换端口**；bb-browser 不支持端口配置时，杀进程须用户点头（可能是另一项目在用资源）。
- 价值定位：Trendonify 只是审计区分位对照（`现在.md` 明确不做升级为正式源），不阻塞 E1-E5 任何工作。
