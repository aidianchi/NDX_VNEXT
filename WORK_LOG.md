# vNext 工作记录

阅读方式：最新完成事项放在最上面。这里记录已经完成的事；未来要做的事写在 `NEXT_STEPS.md`。

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
