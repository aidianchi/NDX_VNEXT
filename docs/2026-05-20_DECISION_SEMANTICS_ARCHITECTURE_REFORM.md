# vNext Decision Semantics 架构改革报告

日期：2026-05-20  
状态：方向性设计报告 / 后续实现依据  
适用对象：后续 Codex、Claude 或其他 AI agent 继续改造 `ndx_vnext` 时，应先读本文，再读 `ARCHITECTURE.md`、`RESEARCH_CANON.md`、`RUN_REVIEW_CHECKLIST.md`。

---

## 0. 一句话结论

vNext 不应继续把所有证据压缩成一个单一市场立场，例如“中性偏谨慎”。下一阶段的核心改革是：

> 从“证据综合成立场”升级为“证据解释价格，价格决定赔率，赔率约束行动”。

这不是给系统加一个“黄金坑识别补丁”。“黄金坑候选”只是新结构自然可能推出的一种市场状态。真正要升级的是最终综合层的决策语义：它必须同时回答市场状态、价格隐含叙事、赔率、时间尺度、行动含义和失效条件。

---

## 1. 为什么必须改

### 1.1 2025-04-09 回测暴露的问题

`output/analysis/vnext/20250409` 这次回测在数据闸门和上下文隔离上已经比早期版本稳健：没有明显把回测日之后的数据直接混入 L1-L5 主证据链，DataIntegrity 也能展示回测边界。但最终报告仍给出“中性偏谨慎”，并且首屏把 `adjudicator_notes` 这类内部审批话术展示给读者。

后验看，2025-04-09 是 NDX / QQQ 的恐慌低点与强反转日之一。系统部分看对了事实：

- L2 看到了信用和波动的 risk-off。
- L4 看到了 NDX PE 30 倍、5 年分位 18%、10 年分位 46%。
- L5 看到了强下跌趋势与放量反弹/OBV 背离并存。
- Bridge 保留了高实际利率 vs 估值修复、集中度极端 vs 趋势脆弱这些冲突。

但系统最终没有把这些事实翻译成正确的投资语义。它把“风险还没解除”误写成“风险收益比不利”，没有识别出“坏消息可能已被价格集中计入、赔率正在改善”的可能。

### 1.2 当前结构的核心偏差

当前治理链条大致是：

```text
Thesis Builder -> Critic -> Risk Sentinel -> Reviser -> Final Adjudicator
```

这条链条更像审稿流程，不像投资判断流程。它奖励：

- 风险有没有保留。
- 冲突有没有保留。
- 证据引用是否能追溯。
- 是否避免过度自信。

这些都重要，但它缺少一个同样重要的问题：

> 当前价格是否已经给风险付出了足够折扣？

结果是系统天然偏向“别错买”，却不够重视“错过高赔率窗口”的风险。市场底部通常不是风险消失的地方，而是风险集中暴露、价格快速下杀、未来补偿突然变厚的地方。现有结构对此没有稳定表达位置。

---

## 2. 金融学第一性原理

本次改革应建立在资产定价与投资决策的基本逻辑上，而不是建立在某个市场形态标签上。

### 2.1 价格是未来现金流与贴现率的共同结果

资产价格不是单纯由“基本面好坏”决定，而是由未来现金流、贴现率和风险补偿共同决定。Cochrane 的资产定价研究强调，预期收益率/贴现率会随时间变化，市场风险溢价不是一个固定常数。  
参考：John Cochrane, *Discount Rates*  
https://igier.unibocconi.eu/sites/default/files/media/attach/AFA_pres_speech.pdf

架构含义：

- L1 利率、L2 信用/波动、L4 估值不能只是各自打标签。
- 关键是判断：当前价格中反映的是现金流恶化、贴现率上升、风险补偿上升，还是三者混合。

### 2.2 估值低不等于低风险，但可能意味着未来补偿变厚

Fama-French、Campbell-Shiller 等长期收益预测研究说明，估值变量对短期收益解释有限，但对长周期收益更有信息量。价格相对基本面越低，常常意味着未来预期收益更高，而不是简单意味着“风险低”。  
参考：

- Fama & French, *Dividend Yields and Expected Stock Returns*  
  https://riskwerk.com/wp-content/uploads/2014/07/fama-french-didivdend-yields-and-expected-stock-returns-1988.pdf
- Campbell & Shiller, *Stock Prices, Earnings, and Expected Dividends*  
  https://www.bauer.uh.edu/rsusmel/phd/campbellshiller88.pdf

架构含义：

- “便宜”应进入赔率判断，而不是直接进入买入结论。
- “风险高”也不应直接压倒估值修复，因为高风险可能已经对应高风险补偿。

### 2.3 ERP 是股权风险价格，不是孤立估值标签

Damodaran 的 implied ERP 框架本质上是用当前价格、未来现金流、无风险利率反推市场要求的股权风险补偿。ERP 是市场风险价格，不是一个可以随意和 NDX PE、简式收益差距混用的标签。  
参考：Aswath Damodaran, *Equity Risk Premiums: Determinants, Estimation and Implications*  
https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4751941

架构含义：

- L4 必须区分 NDX 自身估值、美国市场 implied ERP、手动/Wind ERP、简式收益差距。
- 缺少 EarningsYield / ForwardPE / FCFYield 时，不能把“简式收益差距大概率偏薄”写成强结论。

### 2.4 价值、动量、流动性和情绪是不同维度

Asness, Moskowitz, Pedersen 的 value + momentum 研究说明，价值与动量不是彼此替代的单一信号。它们经常方向不同，并且这种冲突本身就是投资决策的一部分。  
参考：*Value and Momentum Everywhere*  
https://papers.ssrn.com/sol3/papers.cfm?abstract_id=1363476

架构含义：

- L4 “赔率改善”和 L5 “趋势未确认”可以同时成立。
- 这不应被压缩成“中性偏谨慎”，而应表达为“高风险高赔率、需要分批与失效条件”的决策面。

### 2.5 投资决策不是判断对错，而是风险预算

Markowitz 的均值-方差框架和 Merton 的跨期资产定价都提醒：投资动作必须同时考虑预期收益、风险、相关性、时间变化和投资机会集。  
参考：

- Markowitz, *Portfolio Selection*  
  https://studylib.net/doc/28235570/markowitz-portfolioselection-1952
- Merton, *An Intertemporal Capital Asset Pricing Model*  
  https://tesnewdev.econometricsociety.org/publications/econometrica/browse/1973/09/01/intertemporal-capital-asset-pricing-model

架构含义：

- 最终输出不能只给一个“看多/中性/谨慎”。
- 必须区分核心仓、战术仓、等待者，以及不同时间尺度的动作含义。

---

## 3. 当前架构诊断

### 3.1 应保留的部分

以下部分是 vNext 的核心资产，不应推倒：

- L1-L5 context isolation。
- ObjectCanon / IndicatorCanon / PermissionType。
- DataIntegrity 和回测有效日期闸门。
- Bridge typed conflicts / resonance / transmission paths。
- Risk boundary 的可观察触发器意识。
- Native brief / workbench 直接消费 vNext artifacts 的方向。

这些机制让系统能看见证据、保留冲突、追溯数据。2025-04-09 的失败不是因为这些底层全错，而是因为最终综合层没有正确使用这些证据。

### 3.2 需要重塑的部分

Thesis / Final 的当前定位有错配：

- Thesis 被要求“综合成主论点”，但没有被要求解释价格隐含叙事和赔率。
- Critic 主要攻击乐观跳跃，却没有对“过度谨慎导致错过赔率”形成对称攻击。
- Risk Sentinel 主要列 downside risk，却没有列 opportunity cost / confirmation cost。
- Reviser 容易把 Critic 和 Risk 的意见合并成更谨慎、更像审稿合格的文字。
- Final Adjudicator 是内部审批员，却被 UI 当成读者摘要展示。

这造成一个系统性偏差：

> 越往后越重视“风险是否被保留”，越忽视“价格是否已为风险提供足够补偿”。

---

## 4. 目标架构

目标架构不是增加一个孤立 agent，而是重新定义最终综合层的职责。

推荐的概念结构：

```text
Data Collect / Data Audit
  -> L1-L5 Evidence State
  -> Bridge Typed Relationships
  -> Decision Thesis
  -> Quality Gate
  -> Reader Brief
```

### 4.1 Evidence State：事实状态

由现有 L1-L5 和 Bridge 承担。

它回答：

- 利率/流动性是什么状态。
- 信用/波动/情绪是什么状态。
- 广度/集中度是什么状态。
- 估值/盈利/风险补偿是什么状态。
- 趋势/量价/波动位置是什么状态。
- 哪些证据互相确认，哪些证据冲突。

它不直接回答：

- 该不该买。
- 是不是黄金坑。
- 应不应该加仓。

### 4.2 Pricing & Payoff：定价与赔率

这是新 Thesis 合同的核心，不一定是新 agent。

它回答：

1. 当前价格隐含了什么叙事？
   - 软着陆？
   - 衰退？
   - 政策冲击？
   - 利率高位长期化？
   - 盈利下修？
   - 恐慌过度？

2. 坏消息被价格吸收了多少？
   - 估值是否已经明显压缩？
   - 波动和信用是否已经进入极端区间？
   - 技术面是否显示抛售后承接？
   - 政策/事件冲击是否出现边际变化？

3. 当前风险补偿是否变厚？
   - 不是问“环境好不好”。
   - 而是问“现在承担风险，得到的补偿是否比之前更好”。

4. 等待确认的代价是什么？
   - 等信用利差收窄、广度改善、均线站稳，可能降低错误率。
   - 但也可能错过主要反弹。
   - 系统必须显式表达这个 trade-off。

### 4.3 Decision Surface：决策面

最终结论应输出一个“决策面”，而不是单一 stance。

建议固定字段：

1. `state_diagnosis`  
   当前市场状态，例如：risk-off、恐慌反转、趋势破坏、估值修复、流动性修复、抱团脆弱等。

2. `priced_narrative`  
   当前价格正在定价什么，哪些坏消息已反映，哪些还没反映。

3. `payoff_assessment`  
   赔率判断，例如：高风险高赔率、高风险低赔率、低风险低赔率、趋势好但赔率差。

4. `time_horizon_views`  
   至少拆成：
   - 当天/数日。
   - 1-3 个月。
   - 6-12 个月。

5. `portfolio_actions`  
   至少拆成：
   - 核心仓。
   - 战术仓。
   - 空仓/等待者。

6. `confirmation_cost`  
   等待更多确认会降低什么风险、付出什么机会成本。

7. `invalidation_conditions`  
   哪些可观察证据出现，说明当前判断错了。

8. `reader_conclusion`  
   给普通读者的一句话结论和三条理由。

---

## 5. 关键设计原则

### 5.1 不增加形态补丁

不要新增“黄金坑识别器”“顶部识别器”“牛市识别器”这类形态补丁。它们会让系统越来越像规则堆叠。

正确做法是让同一套 Pricing & Payoff 结构自然推出不同情景：

- 高风险高赔率：恐慌低点、估值急压缩、坏消息边际缓和。
- 高风险低赔率：利率/信用/盈利都恶化，但价格仍未给足折扣。
- 低风险低赔率：环境温和但估值贵、预期充分。
- 趋势好但赔率差：动量强，长期预期收益下降。
- 估值便宜但价值陷阱：价格便宜来自现金流永久恶化，而不是风险补偿上升。

### 5.2 不再输出单一未分解立场

`final_stance = 中性偏谨慎` 这类标签只能作为摘要，不得成为唯一结论。

任何最终结论都必须同时说明：

- 对什么时间尺度而言。
- 对核心仓还是战术仓而言。
- 是低风险、低赔率，还是高风险、高赔率。
- 需要哪些确认。
- 错了看什么信号。

### 5.3 缺少确认不自动等于谨慎

当前系统最大错误之一，是把“尚未确认”自动降级成“中性偏谨慎”。后续应改成：

- 缺少确认会降低仓位和执行速度。
- 缺少确认不必然否定赔率改善。
- “等待确认”必须同时说明可能错过什么。

### 5.4 风险边界必须对称

Risk Sentinel 不应只列 downside risk，还应列：

- `opportunity_cost`：过度等待导致错过高赔率窗口。
- `confirmation_cost`：等所有信号确认后，赔率是否已明显下降。
- `false_safety_risk`：风险看似消失，但价格也不再便宜。

### 5.5 Final 不能再展示内部审批语言

Final 的内部质量闸门和读者结论必须分离。

内部质量闸门可以说：

- approved / approved_with_reservations / needs_revision。
- 哪些 evidence refs 有问题。
- 哪些 risks 必须保留。

读者结论必须说：

- 当前市场到底是什么局面。
- 为什么。
- 该如何行动或等待。
- 哪些条件会改变判断。

`adjudicator_notes` 不应进入 brief 首屏或“当前立场”正文。

---

## 6. 推荐职责边界

### 6.1 L1-L5：不变

职责：

- 层内证据分析。
- 指标权限说明。
- 层内冲突与限制。
- 输出 evidence refs。

禁止：

- 直接给买卖结论。
- 知道其他层运行时数据。
- 跨层综合。

### 6.2 Bridge：小幅升级

职责仍是跨层关系，但应额外标记每个 typed conflict 的决策含义：

- 是 cash-flow risk？
- 是 discount-rate risk？
- 是 risk-premium repricing？
- 是 positioning / liquidity shock？
- 是 confirmation / timing conflict？

Bridge 不做最终结论，只为 Decision Thesis 提供关系图。

### 6.3 Decision Thesis：重塑

现有 Thesis Builder 应升级为 Decision Thesis。它不只是写主论点，而是把证据转成定价与赔率判断。

它必须输出：

- 状态诊断。
- 价格隐含叙事。
- 赔率判断。
- 分时间尺度视图。
- 核心仓/战术仓/等待者动作含义。
- 等待确认的成本。
- 失效条件。
- 面向读者的一句话结论。

### 6.4 Critic：对称化

Critic 不只攻击乐观跳跃，也要攻击过度谨慎。

新增审查问题：

- 是否把“风险存在”误等同于“风险收益比差”？
- 是否忽略价格已经大幅调整？
- 是否把确认信号当成入场前提，而没有说明等待确认的成本？
- 是否把短期趋势判断错误外推到 1-3 个月或 6-12 个月？
- 是否对核心仓和战术仓使用了同一个结论？

### 6.5 Risk Sentinel：扩展为 Boundary & Trade-off Sentinel

Risk Sentinel 不应改名也可以，但功能上要覆盖双向边界：

- Downside failure conditions。
- Upside miss / opportunity cost。
- Confirmation cost。
- False confidence / false safety。
- 发布状态边界。

### 6.6 Reviser：考虑收缩或合并

Reviser 当前容易把审稿意见合并成更保守文本。后续有两种选择：

1. 保留，但只允许修复结构与证据错误，不允许重新改变 Decision Thesis 的核心语义。
2. 合并进 Decision Thesis 的一次自检与 Critic 后重试，减少治理链复杂度。

优先建议：先不新增 agent，先改合同和 prompt；如果治理链仍过长，再考虑合并 Reviser。

### 6.7 Final：拆分质量闸门和读者结论

Final 应输出两个明确区块：

1. `quality_gate`
   - 是否发布。
   - 是否存在阻塞项。
   - 是否保留关键风险。
   - 是否存在证据引用错误。

2. `reader_final`
   - 一句话结论。
   - 三条理由。
   - 分时间尺度判断。
   - 行动含义。
   - 失效条件。

UI 只展示 `reader_final`，内部审计区才展示 `quality_gate`。

---

## 7. 输出形态建议

后续 native brief 的首屏不应再是：

```text
中性偏谨慎
分析框架完整，跨层关系识别充分...
```

而应是类似：

```text
恐慌反转候选：风险未解除，但赔率明显改善

2025-04-09 的 NDX/QQQ 不是低风险环境，而是高风险高赔率窗口。信用和趋势仍未确认修复，因此不适合无条件满仓追涨；但估值已被快速压缩、波动和情绪进入极端、量价出现承接，若信用利差不再加速走阔，1-3 个月风险收益比已明显好于暴跌前。
```

注意：这只是示例，不是固定模板。真正模板应来自 `reader_final` 字段。

---

## 8. 回测与验证标准

新架构不能只用 2025-04-09 一个样本证明。必须用情景集压测。

建议最小回测/复盘集：

1. **2025-04-09**  
   恐慌反转 / 高风险高赔率候选。应避免简单输出“中性偏谨慎”。

2. **2021 年末 / 2022 年初**  
   趋势仍强或刚转弱，但估值和利率赔率恶化。应识别“趋势好但赔率差”。

3. **2022 年高通胀杀估值阶段**  
   价格下跌但利率和盈利压力未充分释放。应避免把所有下跌都叫黄金坑。

4. **2020 年疫情低点附近**  
   极端风险 + 政策流动性急转向。应识别政策反转对赔率的改变。

5. **2023 年银行危机**  
   信用压力与政策兜底并存。应表达局部风险和系统流动性支持的冲突。

6. **最新实时 run**  
   验证实时环境下能否区分状态、赔率和行动，而不是套用回测后验。

通过标准：

- 每个样本都能明确区分状态诊断、赔率判断和行动含义。
- 不把“风险高”自动写成“不能买”。
- 不把“估值便宜”自动写成“可以买”。
- 不把“趋势确认”当成所有时间尺度的必要条件。
- 能说明等待确认的成本。
- 能给出可观察失效条件。
- brief 首屏不再出现内部审批话术。

---

## 9. 实施路线

### Phase 1：文档与合约改造

目标：

- 在 `ARCHITECTURE.md` 中吸收本文核心方向。
- 修改 Thesis / Final 相关 contracts，使 Decision Thesis 和 Reader Final 有明确字段。
- 保留旧字段兼容，但新 native brief 优先消费新字段。

完成标准：

- 新合约能表达状态、价格隐含叙事、赔率、时间尺度、行动、确认成本、失效条件。
- 不需要新增“黄金坑”专用字段。

### Phase 2：prompt 改造

目标：

- Thesis prompt 从“综合主论点”改为“定价与赔率判断”。
- Critic prompt 增加“过度谨慎 / 错过赔率”审查。
- Risk prompt 增加 opportunity cost / confirmation cost。
- Final prompt 拆分 quality gate 与 reader final。

完成标准：

- 模型不再把所有冲突统一导向更谨慎。
- 模型能在 2025-04-09 这类样本中表达高风险高赔率，而非只给中性偏谨慎。

### Phase 3：native brief 改造

目标：

- 首屏展示 reader conclusion，而非 adjudicator notes。
- 判断区按状态、赔率、时间尺度、行动、失效条件组织。
- 审计区保留质量闸门、DataIntegrity、Risk Sentinel、Schema Guard。

完成标准：

- 普通读者能一屏看懂“这份报告到底想说什么”。
- 专业读者能下钻验证 evidence refs 和风险边界。

### Phase 4：情景压测

目标：

- 用第 8 节样本集跑回测/复盘。
- 人工审查是否真的区分了低风险、高赔率、趋势确认、估值陷阱等概念。

完成标准：

- 至少 4 个典型样本通过人工复盘。
- 失败样本要记录为 prompt/contract/data 的具体问题，而不是泛泛说模型不行。

---

## 10. 不应做的事

- 不要只加“黄金坑候选”标签。
- 不要继续堆更多治理 agent 来弥补合同不清。
- 不要让 Final 同时当内部审批员和读者摘要作者。
- 不要把“风险完整保留”当作最终报告质量的唯一核心。
- 不要让“等待确认”成为默认答案，除非说明确认成本。
- 不要用当前网页、新闻或后验走势进入 L1-L5 回测主证据链。
- 不要用无证据历史胜率、固定概率、固定点位包装结论。

---

## 11. 给后续 AI 的开工指令

如果你是后续接手的 AI，请按下面顺序行动：

1. 读本文，理解改革目标不是识别某一种行情，而是升级最终综合层的决策语义。
2. 读 `ARCHITECTURE.md`，确认现有 L1-L5 / Bridge / Thesis / Final 职责。
3. 读 `output/analysis/vnext/20250409` 的 `thesis_draft.json`、`critique.json`、`risk_boundary_report.json`、`analysis_revised.json`、`final_adjudication.json`，理解 2025-04-09 失败样本。
4. 先改 contracts 和 prompts，再改 UI。
5. 不要破坏 L1-L5 context isolation。
6. 不要让研究候选、当前网页或后验事实进入回测主证据链。
7. 用 2025-04-09 做第一验收样本，但不要只为它过拟合。

---

## 12. 最终判断

vNext 的底层证据架构仍然值得保留。真正脆弱的是最终综合层：它把复杂投资判断压扁成单一 stance，并把内部审批语言误当成读者结论。

下一阶段最重要的架构改革是：

> 让 Thesis 成为“定价与赔率判断器”，让 Final 拆成“质量闸门”和“读者结论”，让 brief 首屏表达行动语义而不是审批语义。

这会让系统既保留审慎，又不再系统性错过高赔率窗口。
