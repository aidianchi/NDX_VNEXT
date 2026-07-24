# L4 盈利预期缺口：ChatGPT 审计 vs WorkBuddy 调查——对比与核验

- 日期：2026-07-23
- 对象：NDX vNext 末次 run（20260719_130534）中 L4 盈利预期家族缺口
- 两份输入：ChatGPT 审计报告（用户提供全文）；WorkBuddy 同日调查报告（对话内交付）
- 方法：双方有分歧或存疑的事实点，全部回到 run 产物、源码和本机环境逐条核验，核验结果标注【属实】【部分属实】【不属实】【存疑】
- 本文不修改任何项目代码、不终止任何进程、不改数据源权限

---

## 一、ChatGPT 看法概述

ChatGPT 的核心立场：

1. **诊断**：L4"估值半边可用，盈利预期半边近乎空缺"。缺口不是单一原因：Wind 返回空 EPS、成分模型按设计关闭、HoM forward 过期且覆盖率异常、自建档案只有 15 只股票 7 天积累。
2. **语义批评**（其最独特的贡献）：末次报告把"盈利证据缺失"写成了"放大下行风险"——缺数据不是利空证据，只应降低置信度；且 `ForwardPE=null` 的同时核心摘要出现过期的 68.5 分位，属展示层漏洞。
3. **方法论**：强调标准 NTM 应由 FY1/FY2 按剩余月份插值（引 MSCI 方法），而不是混用各家"下一财年"；优先级排序为 NTM EPS 现值 > 30/90 日修正 > 修正广度 > 分歧/覆盖 > 质量 > Forward PE 现值 > 分位。
4. **数据源定位**：Wind 继续作估值主锚；yfinance 为自建模型第一输入但须交叉校验；Finviz 作第二校验源；HoM/Trendonify 保持审计区；理想主源是授权一致预期库。
5. **路线**：先修语义与口径（三状态拆分、audit-only 分位不得进核心摘要、缺数据不偏空、claim gate），再建全成分+真实权重的正式代理链（明确反对前 15 近似），最后解决历史分位（授权源或自积累，不硬造十年分位）。
6. **daemon**：定位为"孤儿 daemon 占 19824 端口、认证文件丢失；Chrome 19825 可达"，并指 `browser_sidecar.py:90` 把该失败错误当成可继续。
7. **达成度**：10 项清单 2 达标、2 部分、6 未达，约 30% 覆盖。

## 二、WorkBuddy（我）看法概述

我的核心立场：

1. **诊断**：同意"盈利预期是末次 run 最大短板"，并纠正用户假设——上次失败**不是 yfinance 获取失败**，而是成分模型开关默认关闭、该路径从未被调用。Wind 空壳返数实锤"无美股权限"。
2. **第一性原理**：盈利预期是承重墙——区分"真便宜"与"价值陷阱"；7/12 钓鱼实验证明缺它系统物理上说不出"机会好"。
3. **理想清单五项**：预期水平、30/90 日修正斜率、修正广度、Forward PE+分位、Forward 收益率差；现状 0/5。
4. **发现的捷径**：vintage_archiver 已连续 12 天每日快照（launchd 调度），且 yfinance `eps_trend` 自带 30/90 天前 vintage 值与上修/下修家数——修正斜率与广度**今天就能算**，不必等 30-90 天。
5. **数据源定位**：Finviz 无分位无 vintage，能力严格小于 yfinance，建议不接；Trendonify 修好后作第三方对照（与 danjuan 同级），不进主链。
6. **daemon**：复现失败，假设为 bb-browser 版本过旧（0.11.5 vs 最新 0.14.2），建议升级。
7. **路线**：①自建一致预期修正指标（top15 加权，需用户拍板转正）→ ②开成分模型开关恢复 Forward PE 水平 → ③修 Trendonify 拿分位对照 → ④放弃 Finviz。

## 三、共识区（双方一致，且经核验成立）

- 盈利预期是末次 run 的最大缺口家族；L4 三个相关位（Wind PIT、Forward PE、盈利质量）全空。
- 失败主因不是 yfinance；是 Wind 空壳 + HoM 过期 + 成分模型未启用 + sidecar 未运行四因叠加。
- 现有防伪治理（新鲜度门、audit_only 降级、unavailable 哨兵、不编数）工作正常，缺口在获取层而非逻辑层。
- Wind 美股一致预期已死，不再试；Wind 估值主锚（PE=35.38、10Y 分位=71.07）正常。
- Trendonify 只能当审计区对照，不进 L1-L5 主证据；分位短期内没有干净的正式来源。
- 盈利预期的重要性毋庸置疑，且它不能越权证明估值便宜。

## 四、分歧区（保留差异，未强行调和）

| # | 分歧点 | ChatGPT | WorkBuddy |
|---|---|---|---|
| D1 | FY1/FY2 口径 | 应插值成统一 NTM（MSCI 方法）再算水平与修正 | 建议 0y 与 +1y 分开算、同口径比较 |
| D2 | 成分覆盖 | 明确反对前 15 近似，要求全成分+真实指数权重 | 把 top15 加权当"快速止血"代理（标代理指标） |
| D3 | Finviz | 有交叉校验价值，建议作第二校验源 | 建议不接（无增量能力） |
| D4 | 修正斜率的原料 | 未提；倾向"积累自己的 vintage" | 主张今天就用 yfinance 自带的 30/90 天前回看字段 |
| D5 | daemon 病因 | 孤儿进程占 19824 端口、认证文件丢失 | 版本过旧（0.11.5→0.14.2） |
| D6 | sidecar 容错逻辑 | `browser_sidecar.py:90` 把 daemon 失败错误当成可继续（隐含需修） | 未评价该逻辑 |
| D7 | 语义层问题 | 重点批评：缺数据被写成利空、过期分位进核心摘要 | 未覆盖（我的调查聚焦数据获取） |

## 五、逐条核验：谁有明显错误

### 5.1 ChatGPT 说对、我没说或不准确的

1. **"缺数据被写成放大下行风险"【属实】**。`run_summary.json:32` final_stance 原文："赔率不利：高实际利率与高估值形成估值压缩主矛盾，**盈利证据缺失放大下行风险**……"。缺失证据被当成了看空证据，违反"缺失≠利空"的对称性原则。这是两份报告里最重要的单一发现，我的调查漏了。
2. **过期 68.5 分位进入核心摘要【属实，但有缓冲】**。`analysis_packet.json` 指标摘要行确实并排放着 `ForwardPE: null` 与 `historical_percentile: 68.5`，摘要文本"分位=68.5 | 状态=insufficient_history"。有状态标注，但"分位=68.5"字样足以误导速读者。展示层缺陷成立。
3. **孤儿 daemon 占端口【属实】**。实测：`node` 进程 PID 50473 监听 127.0.0.1:19824（daemon 控制口），Google Chrome 监听 19825（CDP），而 `bb-browser daemon status` 报 not running——正是"进程活着但不被认领"的孤儿态。该进程 cwd 是另一个项目目录（`~/Desktop/刘甲知识库`），高度疑似跨项目遗留。"认证文件丢失"未能直接核验，但与症状自洽。我的"版本病"假设**不够准确**：升级是健壮性改进，杀掉孤儿进程才是对症修复。
4. **percentile 算法口径【属实】**。`tools_L4.py:4479-4486` 确为 `count(v <= current)/N`（最大秩）。是否与项目他处 mid-rank 口径冲突，未逐一核验，记为待查。
5. **`hom_available` 只看原始值存在【属实】**。`tools_L4.py:4854`：`hom_available = hom_forward_pe is not None or hom_trailing_pe is not None`，不查 decision eligibility；简化路径返回字典确实无顶层 `availability`。这解释了"采集成功但决策字段全空"的覆盖率失真。
6. **76 passed【属实】**。复跑三个测试文件：`76 passed, 6 warnings in 27.39s`。
7. **MSCI NTM 插值方法【属实，金融学正确】**。FY1/FY2 按剩余月份加权是行业标准做法，且与 Canon 的"同口径"要求兼容。我的"0y/+1y 分开"建议不如它标准。
8. **排除亏损成分会使聚合 PE 偏低【属实，金融学正确】**。亏损公司盈利为负，剔除后总盈利变大、聚合 PE 变小，估值显得比实际便宜。我的报告未覆盖这一偏差。
9. **自建档案"7 天"【属实时点、现已过时】**。run 日（7/19）确为 7 天（`expectation_vs_realized.json`：available_days=7）；今天已 12 天连续。ChatGPT 按 run 时点陈述，不算错。

### 5.2 我说对、ChatGPT 没说或不准确的

1. **yfinance 自带 30/90 天前 vintage 字段【属实，ChatGPT 完全未提】**。今日快照实证：`eps_trend` 含 current/7/30/60/90daysAgo 五档一致预期旧值，`eps_revisions` 含 7/30 日上修/下修家数。这意味着修正斜率与广度**不必等自建档案攒够 30 天**。**但**须补充一个重要事实：`expectation_vs_realized.json` 明确写着"未使用供应商回看字段替代"——项目是有意不用供应商回看值的（担心不可复核）。我的"今天就能算"捷径与这条既定政策冲突，需要用你拍板：是放宽政策（live 决策可用 Yahoo 回看值，回测仍用自建档案），还是坚持纯自积累。ChatGPT 倾向后者但没意识到前者存在。
2. **Finviz 无分位、无 vintage【属实】**。ChatGPT 也承认这一点，分歧只在"要不要当校验源"——这是价值判断不是事实分歧。
3. **Trendonify 修复的实际阻塞点**。两人各说对一半：版本旧是事实，孤儿占端口也是事实；正确修复顺序是先杀孤儿（或改端口），不行再升级。

### 5.3 ChatGPT 的明显错误或不准确

1. **Finviz 提供"部分上调/下调人数"【不属实】**。Finviz 公开字段只有分析师评级均分（Recom）、EPS next Y/Q 等，**没有上修/下修家数**。该字段是 Zacks/IBES 系产品形态。此错误削弱了"Finviz 作第二校验源"的部分论据（但不影响其 Forward PE 现值校验价值）。
2. **"sidecar 会把 daemon 失败错误地当成可继续"【部分属实，表述过重】**。代码确实因错误文本含 "cdp is reachable" 而跳过 daemon 步的 raise（`browser_sidecar.py:90-93`），但下一步 `bb-browser open` 实测返回 RC=1 并抛出 RuntimeError——采集仍然 fail-closed，不会带病继续产出假数据。实际缺陷是**报错归因错位**（daemon 的病在 open 步才爆），不是"错误地继续"。
3. **`analysis_packet.json:30082` 行号偏差【轻微】**。实际"分位=68.5"摘要行在 30088 附近，且同行带有 `insufficient_history` 标注；指控成立，但"放进核心摘要"略重——它出现在指标摘要区并带降级标签，不是无标注地冒充当前分位。

### 5.4 我的明显错误或不准确

1. **daemon 病因判断**："升级大概率能修"是不完整诊断。对症修复是先处理 19824 端口的孤儿进程。ChatGPT 定位更准。
2. **Finviz"解决不了任何真实缺口，不建议接"**：过于绝对。它确实解决不了分位与修正斜率（核心缺口），但作 Forward PE 现值的第二交叉校验与项目现有多源校验设计（worldperatio/danjuan）一致，有边际价值。结论应改为"优先级低，非必需"。
3. **调查盲区**：我聚焦"数据为什么取不到"，漏了 ChatGPT 抓到的三个语义/展示层问题（缺数据被当利空、过期分位进摘要、hom_available 覆盖率失真）和两个方法论问题（NTM 插值、亏损剔除偏差）。这些对报告读者的实际误导风险不低于数据缺口本身。
4. **W-E1 捷径与既定政策冲突未声明**：我建议用 yfinance 回看字段算修正斜率时，没有先发现 expectation_ledger 已明确"不使用供应商回看字段"。

## 六、综合判断

- **两份报告在数据获取层的诊断完全一致且互相印证**（Wind 死、HoM 过期、成分模型关、sidecar 断）。这部分没有争议。
- **ChatGPT 的增量价值在语义层与方法论层**，且经核验基本全部属实：缺数据被写成利空是最值得立即修的一处；NTM 插值与亏损剔除偏差是正式实现时必须遵守的工艺标准。
- **我的增量价值在发现了"今天就能算修正斜率"的原料**（yfinance vintage 字段 + 已连续 12 天的自建档案），但它撞上项目"不用供应商回看值"的既定政策——这不是技术问题，是你需要拍板的方法论选择。
- **谁明显错了**：ChatGPT 错在 Finviz 字段（5.3-1）和对 sidecar 容错后果的过重表述（5.3-2）；我错在 daemon 病因（5.4-1）、Finviz 一刀切（5.4-2）和三个语义盲区（5.4-3）。**按"错误会误导决策"的严重度排序：我的 daemon 误诊会导致修错方向（升级而非杀进程），是两份报告里实际危害最大的一处错误；ChatGPT 的 Finviz 字段错误只影响一条次要论据。**

## 七、需要你拍板的三件事

1. **供应商回看字段能不能用**：yfinance 的"30/90 天前一致预期"是 Yahoo 维护的真实历史 vintage，live 决策用它今天就有修正斜率；但项目既定政策（expectation_ledger）不信任供应商回看值、只信自积累。建议折中：live 用 Yahoo 回看值并标 `supplier_lookback_unverified`，回测只用自建档案；8 月 11 日自建档案满 30 天后主用自产。
2. **语义修复是否排最前**：final_stance 的"盈利证据缺失放大下行风险"改法、过期分位退出核心摘要、`hom_available` 按 eligibility 统计——这三处改动小、风险低、收益直接，ChatGPT 列为第一阶段，我同意。
3. **daemon 修复授权**：杀掉占用 19824 的孤儿 node 进程（PID 50473，cwd 在另一个项目目录）需要你确认——它可能属于另一个项目正在用的东西。

---

### 附：核验证据索引

- `output/analysis/vnext/20260719_130534/run_summary.json:32`（final_stance 原文）
- `output/analysis/vnext/20260719_130534/analysis_packet.json`（Wind 主锚 ~18352；Wind PIT null ~18555；成分模型 disabled ~20374；68.5 分位摘要 ~30088）
- `output/analysis/vnext/20260719_130534/expectation_vs_realized.json`（7 天、15 tickers、不用供应商回看字段）
- `output/data/data_collected_v9_live.json`（idx28 Wind 快照 PE=35.38/71.07；idx29 空壳；idx30 ForwardPE=null + StaleReferences；idx31 disabled）
- `src/tools_L4.py:4479`（max-rank 分位）、`:4854`（hom_available）、`:5094-5112`（Stale 降级）、`:5256-5274`（成分模型开关）
- `src/browser_sidecar.py:90-93`（daemon 容错）
- 本机实测：`lsof -iTCP:19824`（node PID 50473）、`bb-browser daemon start/open`（均报 daemon 初始化失败，open RC=1）、`bb-browser 0.11.5 vs npm 0.14.2`
- `output/vintage_archive/20260712..20260723`（12 天连续）；20260723 快照 NVDA eps_trend 五档 vintage + eps_revisions 家数
- 测试复跑：`tests/test_l4_forward_earnings_quality.py` 等三件，76 passed
