# vNext UI Template Brainstorm

日期：2026-04-25

目标：先用 self-contained HTML 验证 vNext 原生 artifact 的阅读与交互样式。在用户确认信息架构之前，不急于进入正式前端框架。

## 共同原则

所有模板都直接消费 vNext 原生产物，而不是 legacy `logic_vnext.json`：

- `final_adjudication.json`
- `synthesis_packet.json`
- `layer_cards/L1-L5.json`
- `bridge_memos/*.json`
- `critique.json`
- `risk_boundary_report.json`
- `schema_guard_report.json`

共同交互：

- 顶部显示最终 stance、approval、confidence、数据日期、指标成功率。
- `key_support_chains` 显示为证据链。
- 点击 evidence ref 跳转到对应 Layer 指标卡。
- L1-L5 以 tab 工作台形式展开。
- 每个指标卡可展开 `reasoning_process`、`first_principles_chain`、cross-layer implications。
- Bridge conflicts、Risk Sentinel、Critic、Schema Guard 保留为一级可读内容。

## Template A：cockpit / 战略驾驶舱

阅读顺序：

1. 最终裁决
2. 主论点证据链
3. Bridge 冲突
4. L1-L5 底稿
5. Governance / Audit

适合：

- 每天快速判断今天 NDX 状态。
- 先看结论，再追证据。
- 给“投资委员会式”阅读。

风险：

- 如果读者想先看五层细节，cockpit 会显得裁决过于前置。

## Template B：brief / 投研长文

阅读顺序：

1. 最终裁决
2. L1-L5 底稿
3. 主论点证据链
4. Bridge 冲突
5. Governance / Audit

适合：

- 像读一篇研究报告一样连续阅读。
- 强调五层独立叙事，让用户先建立市场图景。
- 适合未来输出 PDF 或长文报告。

风险：

- 证据链和冲突后置，审计效率不如 atlas。

## Template C：atlas / 证据地图

阅读顺序：

1. 主论点证据链
2. Bridge 冲突
3. 最终裁决
4. L1-L5 底稿
5. Governance / Audit

适合：

- 检查模型是否跳步。
- 快速定位“结论到底由哪些 evidence refs 支撑”。
- vNext 最能体现“显式逻辑”的版本。

风险：

- 对普通阅读者不如 brief 顺滑，像审计工具多于报告。

## Template D：workbench / 五层工作台

阅读顺序：

1. L1-L5 底稿
2. Bridge 冲突
3. 主论点证据链
4. 最终裁决
5. Governance / Audit

适合：

- 未来把 L1-L5 单独展示在 UI。
- 研究员复盘每层质量。
- 评估 Layer Analyst 是否真正完成专业职责。

风险：

- 最终结论后置，不适合只想快速看 stance 的读者。

## 当前实现入口

生成单个模板：

```powershell
.\.venv\Scripts\python.exe src\agent_analysis\vnext_reporter.py --run-dir output\analysis\vnext\20260425_105237 --template cockpit
```

生成全部模板：

```powershell
.\.venv\Scripts\python.exe src\agent_analysis\vnext_reporter.py --run-dir output\analysis\vnext\20260425_105237 --template all --output output\reports\vnext_ui_template.html
```

预期输出：

- `output/reports/vnext_ui_template_cockpit.html`
- `output/reports/vnext_ui_template_brief.html`
- `output/reports/vnext_ui_template_atlas.html`
- `output/reports/vnext_ui_template_workbench.html`

## 建议评审问题

1. 第一眼是否能判断今天的市场 stance？
2. 是否能在 30 秒内找到支撑 stance 的 3 条主证据链？
3. 是否能清楚看到“哪些层互相冲突”？
4. L1-L5 是否适合作为独立页面展示？
5. 指标卡展开后，推理密度是否足够但不过载？
6. evidence ref 跳转是否符合你的阅读习惯？
7. 哪个模板最像“未来正式前端”的信息架构？
