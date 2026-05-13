# Run Review Checklist：真实运行复盘清单

最近更新：2026-05-13
用途：每次跑完真实模型后，用同一套标准判断系统是否真的变稳，而不是只看“有没有生成报告”。

阅读方式：最新运行记录放在最上面；通用检查表放在后面。

---

## 最新运行记录

### 2026-05-13 / `20260513_191253`

| 项目 | 内容 |
| --- | --- |
| run 目录 | `output/analysis/vnext/20260513_191253` |
| 数据文件 | `output/data/data_collected_v9_live.json`（2026-05-12 采集缓存） |
| 运行时间 | 约 2026-05-13 19:12 起 |
| 使用模型 | `deepseek-v4-flash`（备用 `deepseek-v4-pro` 未触发） |
| 最终判断 | 中性偏谨慎 |
| 最终审批状态 | 有保留地通过 |
| 当时测试结果 | `155 passed`（本轮修改后） |
| 生成的 brief 页面 | `output/reports/vnext_brief_20260512_20260513.html` |
| 生成的 workbench | `output/reports/vnext_workbench_20260512_20260513.html` |

本轮结论：

| 观察项 | 结论 | 证据 |
| --- | --- | --- |
| 治理输入压缩是否丢证据 | 通过 | Final support refs 均能在 evidence index 中找到；4 个 key_support_chains 均有 evidence_refs，权重分配合理。 |
| 跨层冲突是否稳定、具体、可追溯 | 通过 | Bridge 生成 3 个 typed conflicts（2 high + 1 medium），均有层级、机制、反证。 |
| 客观性防火墙是否拦住过度自信 | 通过 | Schema guard 通过；Final 未输出无证据的固定跌幅、点位或估值阈值。 |
| L3 是否应升级为硬要求 | 观察 | L3 广度指标有数据，但 yfinance 限流导致 ADX 完全缺失；继续观察。 |
| brief / workbench 是否适合连续阅读 | 通过 | Native brief 左侧 sticky 导航 + 右侧长文；workbench 数据时效性横幅已添加。 |

本轮问题（本轮修复）：

- `generated_at` 日期幻觉：LLM 在 governance 阶段编造未来日期，已在 `orchestrator.py` 中强制覆盖。
- yfinance 限流（37 个 ERROR）导致 QQQ/VIX/HYG 空数据，workbench 静默使用缓存；已添加缓存回退和空序列警告横幅。
- L4 prompt 230K 字符：Damodaran 120 条月度序列完整塞入；已添加 `_summarize_l4_raw_data_for_prompt` 压缩为统计摘要。

---

### 2026-05-12 / `20260512_215333_collect_only`

| 项目 | 内容 |
| --- | --- |
| run 目录 | `output/analysis/vnext/20260512_215333_collect_only` |
| 数据文件 | `output/data/data_collected_v9_live.json` |
| 运行时间 | 约 2026-05-12 21:53 起 |
| 使用模型 | `--collect-only`，无 LLM 调用 |
| 最终判断 | N/A（仅数据采集验证） |
| 最终审批状态 | N/A |
| 当时测试结果 | `154 passed` |
| 验证目标 | L4 外部估值源稳定收口后的数据验证 |

本轮结论：

| 观察项 | 结论 | 证据 |
| --- | --- | --- |
| Damodaran 月度 ERP 采集 | 通过 | `data_collected_v9_live.json` 中包含 120 条月度序列，`ERPbymonth.xlsx` 优先。 |
| WorldPERatio 窗口数据 | 通过 | 1Y/5Y/10Y/20Y 标准差窗口可结构化解析，不冒充 historical percentile。 |
| Trendonify sidecar | 通过 | `bb-browser` sidecar 可用，带 `browser_sidecar` 元数据；403 不硬修为主链路。 |
| ThirdPartyChecks 交叉校验 | 通过 | Manual/Wind ERP 仍为主值，collector 附加 live ThirdPartyChecks。 |

---

### 2026-05-10 / `20260510_225944`

| 项目 | 内容 |
| --- | --- |
| run 目录 | `output/analysis/vnext/20260510_225944` |
| 数据文件 | `output/data/data_collected_v9_live.json` |
| 运行时间 | 约 2026-05-10 22:59 起 |
| 使用模型 | `deepseek-v4-flash`（备用 `deepseek-v4-pro` 未触发） |
| 最终判断 | 中性偏谨慎 |
| 最终审批状态 | 有保留地通过 |
| 当时测试结果 | `154 passed` |
| 生成的 brief 页面 | `output/reports/vnext_brief_20260510_20260510.html` |

本轮结论：

| 观察项 | 结论 | 证据 |
| --- | --- | --- |
| 治理输入压缩是否丢证据 | 通过 | Bridge JSON 容错升级后，所有 stage attempts=1, errors=[]。 |
| 跨层冲突是否稳定、具体、可追溯 | 通过 | Bridge 生成 typed conflicts，resonance chains 有证据字段。 |
| 客观性防火墙是否拦住过度自信 | 通过 | 无历史概率幻觉。 |
| L3 是否应升级为硬要求 | 观察 | 广度数据有值，但仍有薄弱项。 |
| brief / workbench 命名简化 | 通过 | `vnext_brief_<data>_<run>.html` 格式落地。 |

本轮问题（已记录）：

- `generated_at` 日期幻觉在本轮已出现：`final_adjudication` = 2025-03-31（-14 个月），`analysis_revised` = 2025-04-07（-13 个月）。
- `datetime.utcnow()` deprecation 在代码和 contracts 中大量存在。

---

### 2026-04-29 / `20260429_001955`

| 项目 | 内容 |
| --- | --- |
| run 目录 | `output/analysis/vnext/20260429_001955` |
| 数据文件 | `output/data/data_collected_v9_live.json` |
| 运行时间 | 约 2026-04-29 00:19:55 起，约 8.5 分钟 |
| 使用模型 | 实际使用 `deepseek-v4-flash`；`deepseek-v4-pro` 为备用但未触发 |
| 最终判断 | 中性偏谨慎 |
| 最终审批状态 | 有保留地通过 |
| 当时测试结果 | `39 passed, 133 warnings` |
| 生成的 brief 页面 | `output/reports/vnext_research_ui_brief_20260423.html` |

本轮结论：

| 观察项 | 结论 | 证据 |
| --- | --- | --- |
| 治理输入压缩是否丢证据 | 通过 | Final support refs 均能在 evidence index 中找到；高严重度风险和冲突仍被保留。 |
| 跨层冲突是否稳定、具体、可追溯 | 通过但继续观察 | Bridge 生成 2 个 typed conflicts，均有层级、证据、机制和反证；resonance chain 仍需加强证据字段要求。 |
| 客观性防火墙是否拦住过度自信 | 通过但继续观察 | Schema guard 通过；Risk / Final 经 prompt 护栏后未再输出无证据的固定跌幅、点位或估值阈值。 |
| L3 是否应升级为硬要求 | 观察 | 原始采集 34 个函数均有返回，但 L3 仍有 4 个广度指标被质量自检标为缺失或薄弱；暂不 hard fail。 |
| brief 是否适合普通读者连续阅读 | 待评审 | 本 run 已生成 `brief` 页面，下一步需要做人工阅读复盘。 |

本轮后续：

- 先补 Bridge resonance chain 的证据字段要求。
- 优先处理 L3 广度数据源和 fallback。
- 评审本 run 的 `brief` 输出体验。

---

### 2026-04-27 / `20260427_190347`

| 项目 | 内容 |
| --- | --- |
| run 目录 | `output/analysis/vnext/20260427_190347` |
| 数据文件 | `output/data/data_collected_v9_live.json` |
| 运行时间 | 约 2026-04-27 19:03:47 到 19:09:54 |
| 使用模型 | `deepseek-v4-flash`, `deepseek-v4-pro` |
| 最终判断 | 谨慎 |
| 最终审批状态 | 有保留地通过 |
| 当时测试结果 | `30 passed, 97 warnings` |
| 生成的 brief 页面 | `output/reports/vnext_ui_20260427_190347_brief.html` |

本轮结论：

| 观察项 | 结论 | 证据 |
| --- | --- | --- |
| 指标说明书是否减少误读 | 通过 | L1-L5 共 34 条指标分析均有 `permission_type`，反证条件未缺失。 |
| 跨层冲突是否稳定、具体、可追溯 | 通过 | Bridge 生成 5 个 typed conflicts、3 个 resonance chains、4 条 transmission paths。 |
| 客观性防火墙是否拦住过度自信 | 观察 | `objective_firewall_summary` 通过；但 Risk / Final 出现未经证据支持的历史概率，已补 prompt 护栏。 |
| L3 是否应升级为硬要求 | 观察 | L3 重试后成功，但仍说明广度数据缺失；暂不建议 hard fail。 |
| brief 是否适合普通读者连续阅读 | 通过但继续观察 | 页面已展示指标发言权、typed map 和客观性防火墙；仍需真实阅读反馈。 |

本轮后续：

- L3 继续保持“强提示、非硬失败”。
- Objective Firewall 有效，但下游 prompt 仍需要护栏。
- Governance token 偏重的问题已在 2026-04-28 通过 `GovernanceInputPacket` 第一版处理，下一轮真实运行要验证效果。

---

## 历史运行摘要

| 日期 | run 目录 | 最终判断 | 审批状态 | 总体结论 |
| --- | --- | --- | --- | --- |
| 2026-05-13 | `output/analysis/vnext/20260513_191253` | 中性偏谨慎 | 有保留地通过 | generated_at 幻觉已修复；L4 prompt 已压缩；workbench 新增缓存/空数据警告；yfinance 限流问题待观察。 |
| 2026-05-12 | `output/analysis/vnext/20260512_215333_collect_only` | N/A | N/A | L4 外部估值源稳定收口验证通过；Damodaran/WorldPERatio/Trendonify 均可用。 |
| 2026-05-10 | `output/analysis/vnext/20260510_225944` | 中性偏谨慎 | 有保留地通过 | Bridge JSON 容错升级验证通过；所有 stage 一次通过；generated_at 幻觉和 utcnow deprecation 已记录。 |
| 2026-04-29 | `output/analysis/vnext/20260429_001955` | 中性偏谨慎 | 有保留地通过 | DeepSeek-only 基准通过；治理压缩未丢关键证据；L3 广度数据仍需补强。 |
| 2026-04-27 | `output/analysis/vnext/20260427_190347` | 谨慎 | 有保留地通过 | 第二轮真实运行通过；发现并修复治理 prompt 中诱导历史概率幻觉的问题。 |
| 2026-04-26 | `output/analysis/vnext/20260426_235800` | 中性偏谨慎，风险偏向下行 | 有保留地通过 | 第一版法典、typed map、客观性防火墙和 native UI 跑通；仍需观察多轮稳定性。 |

---

## 每次运行先填这里

| 项目 | 内容 |
| --- | --- |
| run 目录 |  |
| 数据文件 |  |
| 运行时间 |  |
| 使用模型 |  |
| 最终判断 |  |
| 最终审批状态 |  |
| 全量测试结果 |  |
| 生成的 brief 页面 |  |

判断分三档：

- 通过：证据清楚，结果可追溯。
- 观察：能用，但有明显瑕疵，下一轮要继续看。
- 未通过：会误导读者，或破坏 vNext 的核心原则。

---

## 五项复盘

### 1. 指标说明书是否减少误读

检查目标：每个指标都在自己的能力范围内说话。

| 检查项 | 通过 / 观察 / 未通过 | 证据位置 | 备注 |
| --- | --- | --- | --- |
| 指标分析是否填写或回填了“指标发言权” |  | `layer_cards/L*.json` |  |
| 技术指标是否避免替估值、基本面下结论 |  |  |  |
| 代理指标是否避免被当成官方事实 |  |  |  |
| 反证条件是否具体，而不是空泛套话 |  |  |  |
| 交叉验证对象是否和指标问题相关 |  |  |  |

### 2. 跨层冲突是否稳定、具体、可追溯

检查目标：Bridge 不是泛泛总结，而是在建模不同层之间的关系。

| 检查项 | 通过 / 观察 / 未通过 | 证据位置 | 备注 |
| --- | --- | --- | --- |
| 是否生成 typed conflicts |  | `bridge_memos/*.json` |  |
| 每个冲突是否包含涉及层级 |  |  |  |
| 每个冲突是否包含证据引用 |  |  |  |
| 冲突机制是否说清楚“为什么冲突” |  |  |  |
| 高严重度冲突是否被后续报告保留 |  | `synthesis_packet.json` / `final_adjudication.json` |  |

### 3. 客观性防火墙是否拦住过度自信

检查目标：报告下结论前，先检查对象、证据、时间、反证和未解决矛盾。

| 检查项 | 通过 / 观察 / 未通过 | 证据位置 | 备注 |
| --- | --- | --- | --- |
| 是否生成客观性防火墙摘要 |  | `synthesis_packet.json` |  |
| 投资对象是否清楚 |  |  |  |
| 指标发言权是否清楚 |  |  |  |
| 是否有最强反证 |  |  |  |
| 是否列出未解决张力 |  |  |  |
| 最终报告是否避免无证据强标签 |  | `final_adjudication.json` |  |

### 4. 第三层结构指标是否应该升级为硬要求

检查目标：审慎看待 L3，不因为它重要就过早一票否决。

| 检查项 | 通过 / 观察 / 未通过 | 证据位置 | 备注 |
| --- | --- | --- | --- |
| L3 是否能说明 NDX 内部结构 |  | `layer_cards/L3.json` |  |
| 是否区分指数上涨和市场广度 |  |  |  |
| 是否区分龙头贡献和整体健康 |  |  |  |
| schema guard 是否只提示而非硬失败 |  | `schema_guard_report.json` |  |
| 是否有足够证据支持把 L3 从提示升级为硬要求 |  |  |  |

### 5. brief 页面是否适合普通读者连续阅读

检查目标：页面不只是“信息齐全”，还要让非专业读者能顺着读下去。

| 检查项 | 通过 / 观察 / 未通过 | 证据位置 | 备注 |
| --- | --- | --- | --- |
| 最终判断是否容易找到 |  | `output/reports/*_brief.html` |  |
| 主要证据链是否容易理解 |  |  |  |
| 跨层冲突是否可见 |  |  |  |
| 指标发言权和反证条件是否可见 |  |  |  |
| 客观性防火墙是否可见 |  |  |  |
| 证据跳转是否可用 |  |  |  |

---

## 是否可以收紧规则

每轮结束后，只回答三个问题：

1. 哪些软约束已经稳定，可以考虑变成硬约束？
2. 哪些地方仍然应该保持提示，不应硬失败？
3. 有没有发现会误导普通读者的展示或措辞？
