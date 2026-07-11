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
- U1 一阶段结论：层级证据敏感（强阳性）、Bridge 矛盾识别真实、**最终动作层黏性存疑（谨慎吸引子假说，待二阶段判定）**；DataIntegrity 对数值篡改零反应（重算校验带的依据）；P1 的 claim_gate 通过率 1/8 显示 claim 校验能抓数据内部矛盾。

## 进行中（后台管线，不耗 Claude 额度）

- `output/analysis/vnext/u1_experiment_baseline_r2` / `_r3`：基线重复，测同输入随机漂移（噪音标尺）
- `output/analysis/vnext/u1_experiment_p4`：教科书级全面利多组合（快照 `scratchpad/u1/data_p4.json`，改动清单 `change_log_p4.json`——估值便宜+流动性宽松+广度健康+集中度正常+收益差距转正+Damodaran 充足+第三方一致）
- **收割方法**：对 7 个 run（baseline×3、P1-P4）提取 L1/L3/L4 local_conclusion+confidence、bridge principal_contradiction id/summary、final_stance、reader_final 动作字段、claim_gate 通过率。判定：P4 下最终动作仍是"赔率不利/极小试探"→ 谨慎吸引子实锤；转向建设性 → 综合层证据敏感成立。变化须超过 baseline×3 自然漂移。一阶段完整报告：`scratchpad/u1/u1_report.md`（scratchpad 会话易失，重要结论须回写本目录）。

## 工单队列（按优先级；每单一提交）

1. **discipline_side 渲染区分**：`vnext_reporter.py` ~1805-1995 读者纪律清单不区分买入/卖出/风险条目（字段在 `contracts.py:315`，赋值 `orchestrator.py:2391,2410`），风险描述与买入触发共用绿色"已满足"pill 易误读。按 side 分别渲染+测试。
2. **校准闭环通电**：`outcome_review.py` 解除 `not_run_for_live_or_non_backtest_context`（live run 也产出 T+N claim 打分并落盘）；打分结果标注 `data_quality_caveat`，数据层验收前只作数据问题探测器；跨 run 展示层（`orchestrator.py` 硬编码 deferred）继续保持关闭。
3. **独立重算校验带**：新模块（不 import 主管线计算代码）对派生字段二次实现重算——分位（锁窗口/插值）、增速、比率、单位量纲（billion/million 混用报警）；产出 `recompute_report.json` 接入 checker 硬闸门。依据：U1 证明 DataIntegrity 对数值篡改零反应；历史上净流动性 10 倍错误穿透全部闸门。
4. **证据菜单再平衡**（金融层最大缺口，见 audit_B）：AI 资本开支周期代理（M7 capex 同比/指引，可复用 `tools_L4.py` XBRL 标签管道）、fed funds futures 隐含利率路径、VIX 期限结构（RESEARCH_CANON 已有判读标准、未实现）、回购与财报静默期日历；完成后做多空证据源对称性审计。
5. **报告层小修**：`shared_falsifiers` 过半即称"这批共用"的语义（改严格全等或标注 N/M 命中）；`missing_groups` 对"市场状态"组静默跳过的不对称；hypothesis-card leading 高亮的过度信任风险（低优先级）。
6. **checker 可观测性**：原始输入 `data_json` 落盘（本次回放只能近似重建）；补"恰好 50%"与"total<3 豁免"边界回归测试。
7. **Manual/Wind ERP 回退通道**：`manual_data.py:99-119` 允许 Damodaran 槽位被 Wind 人工值填充，弱化三槽位独立性——评估收紧或显式标注。
8. **死代码与僵尸子系统**：`tools.py`+`tools_finnhub.py`+`tools_simfin.py` 死链（~1,390 行）；`data_manager.py:99-112` 孤儿陈旧度检测；受控调查反馈环恒零产出（`orchestrator.py:1133` `is_deterministic_stub` 写死 True）——砍除或修复二选一，需用户或主审拍板。
9. **巨型文件手术**：orchestrator.py 按 audit_C 方案拆 stage_runner / prompt_composer / claim_verification / stage_io / payload_normalizer；tools_L4.py 按数据源拆模块。
10. **fresh 完整 vNext E2E 验收**（NEXT_STEPS P0）：最新代码全链跑一轮，人工核对发布状态/主要结论/反证/失效条件。

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
