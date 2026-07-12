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

1. **discipline_side 渲染区分 ✅ 完成（2026-07-12，`7531721`）**：读者纪律清单已按 side×status 分别渲染（risk/sell 满足 → 红色"风险已触发/卖出条件已成立"，buy 满足 → 绿，hold → watch），含测试。
2. **校准闭环通电 ✅ 完成（2026-07-12，Fable 验收）**：`outcome_scoring_runner.py` 批量打分器（扫描 vNext run → ≥20 天成熟门槛 → 复用 outcome_review 判定 → per-run `claim_outcome_scores.json` + 幂等 append `output/state_ledger/claim_outcome_ledger.jsonl`）+ 7 项离线测试，530 全绿（Fable 亲跑复核）。实树验证：15 个候选 run 全部"太年轻"被诚实跳过（未编造判定）；判定语义经受控 fixture 三样例复核（bullish 遇 T+20 -20% → falsifier_triggered；risk 主张 → consistent；无方向陈述 → not_scorable）。**遗留**：首次真实成熟 run 打分待 2026-07-27 后执行（`20260707_163359` 过门槛时）并人工复核；注意 20 为自然日、T+20 为交易日（≈28 自然日），pending 标注已正确处理该差异。
3. **独立重算校验带**：新模块（不 import 主管线计算代码）对派生字段二次实现重算——分位（锁窗口/插值）、增速、比率、单位量纲（billion/million 混用报警）；产出 `recompute_report.json` 接入 checker 硬闸门。依据：U1 证明 DataIntegrity 对数值篡改零反应；历史上净流动性 10 倍错误穿透全部闸门。
4. **证据菜单再平衡**（金融层最大缺口，见 audit_B）：AI 资本开支周期代理（M7 capex 同比/指引，可复用 `tools_L4.py` XBRL 标签管道）、fed funds futures 隐含利率路径、VIX 期限结构（RESEARCH_CANON 已有判读标准、未实现）、回购与财报静默期日历；完成后做多空证据源对称性审计。
   **盈利预期数据源判决（2026-07-12 凌晨实测，Fable 亲测）**：Wind 路线判死——NDX.GI 指数级"没找到数据"；成分股级对照实验证明机制通（茅台返回真实双时点一致预测 EPS 31.7446/31.7267）但美股无权限（AAPL 同问法返回 null）。PIT 契约代码保留（防伪门槛正确），数据源改道：① **立即启动自建 vintage 档案**——每日/每周快照 yfinance+FMP 的当前一致预期（.env 已有 FMP key），30-90 天后即有可用的自产时点序列，零成本且完全可控；② 评估 FMP/Finnhub 现成的预期历史端点覆盖度（tools_finnhub.py 死码正好是这个用途，可部分复活）；③ Wind 继续做估值主锚（PE/PB/PS 正常），只放弃其美股盈利预期。
   **追加（2026-07-12 Fable 亲测）：修正斜率不必等档案积累**——yfinance `Ticker.eps_trend` 免费返回每只美股"current / 7d / 30d / 60d / 90d ago"的一致预期 EPS（实测 AAPL/MSFT/NVDA 数据完好，NVDA +1y EPS 90 天内 11.11→12.76），`eps_revisions` 另给上/下修分析师家数。指数级做法：取 NDX 前十大权重股聚合（权重覆盖 >50%）。定位：yfinance eps_trend = 立即可用的 90 天后视镜（authority 标 third_party_unofficial，需防字段漂移）；自建 vintage 档案降级为加固层（对冲雅虎黑箱/断供 + 未来把后视镜延长到 90 天以上）；深回测所需的多年期历史 vintage 仍无免费来源（IBES 收费），评估 FMP/Finnhub earnings-surprise 历史作部分替代。
   **档案已启动（2026-07-12，Fable 验收）**：`src/vintage_archiver.py` 独立脚本 + 5 项离线测试；首日快照 `output/vintage_archive/20260712/`（15/15 yfinance、11/15 FMP，MU/GOOG/AVGO/AMAT 免费层 402；Invesco 持仓 406 → 静态 top15 回退如实标注）。隔离观察数据，未升级数据源、不得作 evidence_ref。**定时任务未安装**——建议 crontab：`30 21 * * 1-5 cd /Users/aidianchi/Desktop/ndx_mac && .venv/bin/python -m src.vintage_archiver >> output/logs/vintage_archiver.log 2>&1`（美股收盘后，时区自行校准）；装不装由用户拍板。注意点：AAPL eps_trend `60daysAgo=0.0` 是 yfinance 原始值——第三方非官方源的字段漂移风险实例，档案原样保存不粉饰。
5. **报告层小修**：`shared_falsifiers` 过半即称"这批共用"的语义（改严格全等或标注 N/M 命中）；`missing_groups` 对"市场状态"组静默跳过的不对称；hypothesis-card leading 高亮的过度信任风险（低优先级）。
6. **checker 可观测性**：原始输入 `data_json` 落盘（本次回放只能近似重建）；补"恰好 50%"与"total<3 豁免"边界回归测试。
7. **Manual/Wind ERP 回退通道**：`manual_data.py:99-119` 允许 Damodaran 槽位被 Wind 人工值填充，弱化三槽位独立性——评估收紧或显式标注。
8. **死代码与僵尸子系统**：`tools.py`+`tools_finnhub.py`+`tools_simfin.py` 死链（~1,390 行）；`data_manager.py:99-112` 孤儿陈旧度检测；受控调查反馈环恒零产出（`orchestrator.py:1133` `is_deterministic_stub` 写死 True）——砍除或修复二选一，需用户或主审拍板。
9. **巨型文件手术**：orchestrator.py 按 audit_C 方案拆 stage_runner / prompt_composer / claim_verification / stage_io / payload_normalizer；tools_L4.py 按数据源拆模块。
10. **fresh 完整 vNext E2E 验收**（NEXT_STEPS P0）：最新代码全链跑一轮，人工核对发布状态/主要结论/反证/失效条件。
11. **旧快照回放兼容性（工单#2 施工中发现，2026-07-12）**：① `data_collected_v9_20250409.json` / `20240805.json` 回放被 L3 `available_without_meaningful_value` hard block（`data_evidence.py:436`，四个广度函数）——证据合约收紧后与旧快照不兼容，影响历史回测能力与 #10 E2E；② 回测模式下 Wind 估值函数标 `backtest_skipped_unsupported_function` → L4 1/6 跌破单层及格线，任何日期的回测都无法出发布产物（归 #4 处置）；③ `data_collected_v9_20260509.json` 原为旧 collector schema，已用 `--collect-only --date 2026-05-09` 刷新（gitignored）。
12. **claim gate 稳定化**：同输入下 verified 率在 7/8 与 1/8 间跳动（U1 基线三连 + P5 复现四次）。排查 `_verify_claim_entry` 链路中受 LLM 措辞随机性支配的环节（疑似 claim 文本与 evidence ref 的匹配方式），改为确定性可复核的匹配，或在 claim 生成端约束引用格式；验收=同输入三连 verified 率方差趋近 0。

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
