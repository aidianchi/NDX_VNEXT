# vNext Agent 流水线通俗审查报告

写作日期：2026-05-20

## 一句话结论

这个系统不是“一个 AI 直接写报告”，而是一条分阶段的投研推理流水线：先让 L1-L5 各自只看自己的材料，再让 Bridge 找跨层关系，再让 Thesis 写主论点，最后由 Critic、Risk、Schema Guard、Reviser、Final 做审查和放行。

这套结构总体是合理的，尤其合理在三点：

1. L1-L5 没有互相偷看本轮数据，可以减少“大家互相带节奏”。
2. 每层不只输出一个标签，还输出指标级解释、推理过程、证据引用、层内冲突和质量自检。
3. 后面有专门的批评、风险、结构校验和最终裁决，不是写稿的人自己给自己盖章。

但它也不是天然可靠。最需要继续盯的不是“agent 名字够不够专业”，而是每个字段有没有保留真实信息。你担心的那种垃圾输出，例如“VIX 分析半天，最后只传给下游一个 fear”，当前主链路已经做了一些防护，但仍有类似风险存在：`normalized_state`、`risk_flags`、`local_conclusion` 这类短标签如果被下游单独使用，就会变成低价值符号；真正有价值的是 `narrative`、`reasoning_process`、`evidence_refs`、`layer_synthesis`、`internal_conflict_analysis`、`typed_conflicts` 和 `must_preserve_risks`。

## 怎么读这份报告

我会对每一段流水线都按同一套问题说明：

- 它收到什么。
- 它具体怎么分析。
- 它输出什么字段。
- 这些字段有什么价值。
- 哪些字段容易变成垃圾。
- 我对结构合理性的判断。

这里的“垃圾”不是骂模型，而是指：字段看起来有内容，但下游拿到以后不能做严肃判断，不能追证据，不能解释机制，不能指出反证。

典型垃圾字段包括：

- 只有 `fear`、`risk_on`、`expensive` 这种标签，没有数值、机制、证据。
- 只有“偏谨慎”“偏乐观”，没有说为什么。
- 只说“高风险”，没有触发条件。
- 只说“需要关注”，没有说明关注哪个指标、什么变化会改变判断。
- 用一堆漂亮话覆盖冲突，把不确定性洗掉。
- 引用了新闻或当前网页，却没有说明是否符合回测日期。
- 把代理指标当成官方事实，把技术指标当成估值证明。

## 总览：整条链路在做什么

当前主链路大致是：

```text
数据采集 / AnalysisPacket
  -> Context Brief / Layer Context Brief
  -> L0 Object Canon
  -> L1 Layer Analyst
  -> L2 Layer Analyst
  -> L3 Layer Analyst
  -> L4 Layer Analyst
  -> L5 Layer Analyst
  -> Bridge
  -> SynthesisPacket
  -> Thesis Builder
  -> Critic
  -> Risk Sentinel
  -> Schema / Trace Guard
  -> Reviser
  -> Final Adjudicator
  -> Native brief / workbench / legacy output
```

这条链路的核心思想是：

> 先让每个局部专家把自己那一层讲清楚，再让跨层 agent 处理关系，最后让治理 agent 审查它有没有胡说。

这比“一个大 prompt 直接写报告”好，因为市场判断最怕两种东西：

1. 过早综合。比如趋势强，就把估值贵的风险轻轻带过。
2. 证据污染。比如新闻、网页、当前数据、其他层结论提前灌进 L1-L5，让它们看起来都同意一个故事。

## 0. 数据采集与 AnalysisPacket

### 它收到什么

这一段不是 LLM agent，主要是代码阶段。它把原始市场数据、人工覆盖数据、新闻 sidecar、回测日期和数据质量信息整理成 `analysis_packet.json`。

它的输入包括：

- L1-L5 的原始指标数据。
- 每个指标的 `function_id`、数值、日期、数据质量、是否需要分析。
- 人工/Wind 输入。
- 回测日期或 effective date。
- 新闻事件底账，但新闻默认不进入 L1-L5 主证据链。
- `backtest_data_boundaries` 和 `strict_backtest_invariants`。

### 它具体干什么

它相当于“资料管理员”。它不应该做深度投研结论，而是要保证资料包干净：

- 哪些指标成功。
- 哪些指标失败。
- 哪些指标在回测模式下必须跳过。
- 哪些数据日期不能晚于回测日。
- 哪些来源只是 sidecar，不能当作正式证据。
- 哪些人工数据是 active，哪些是 inactive。

### 主要输出字段

`AnalysisPacket` 里重要字段：

- `meta`：本次 run 的元信息，例如数据日期、生成时间、回测日期、指标数量、数据边界。
- `raw_data`：原始数据，按 L1-L5 分组。
- `facts_by_layer`：按层整理的事实摘要。
- `candidate_cross_layer_links`：代码预生成的候选跨层关系。注意，这只是候选，不等于结论。
- `event_refs`：事件底账索引。它和 evidence refs 分开，不能直接证明数值结论。
- `manual_overrides`：人工输入。
- `context`：额外上下文，例如回测、有效日期。

### 字段价值

最有价值的是 `meta`、`raw_data`、`facts_by_layer`、`backtest_data_boundaries`、`strict_backtest_invariants`。

原因很简单：AI 后面说的一切，都应该能追到这里。如果这里混入了未来数据、当前网页、无效指标或 inactive manual 值，后面所有 agent 都可能严肃地分析错误材料。

### 垃圾风险

这一段最大的垃圾风险不是“文字空洞”，而是“脏数据被包装成证据”：

- 回测日是 2025-04-09，但数据里混进 2026 年网页或当前成分股基本面。
- 指标失败了，但仍被写进 `analysis_required=true`。
- 新闻只是 sidecar，却被写成 `evidence_ref`。
- 代理数据缺少覆盖率，却被写成官方事实。
- 当前成分股 universe 被用于历史回测，却没有声明 point-in-time 限制。

### 结构判断

结构合理，而且是整个系统的地基。现在已经有 DataIntegrity、回测日期守门、inactive manual 隔离、sidecar policy，这些都是必要的。

但这段仍然应该被长期视为最高风险区域。因为只要数据包错了，后面的 agent 越聪明，越会把错误分析得很漂亮。

## 1. Context Brief / Layer Context Brief

### 它收到什么

它收到 `AnalysisPacket`，然后给后续 agent 生成摘要。这里也主要是代码和 prompt 组织阶段，不是最终投研判断者。

### 它具体干什么

它把大包材料压缩成两类东西：

- 全局任务说明。
- 每一层自己的上下文。

注意，这里要分清两个文件：

- `context_brief.json` 是全局简报，会包含五层的 `layer_highlights` 和候选跨层线索，给 Bridge 和后续综合阶段使用。
- `layer_context_briefs/L1-L5.json` 是层内简报，给 L1-L5 分别使用。实际代码会把它过滤成只包含本层 highlights，并把 `apparent_cross_layer_signals` 置空。

所以按当前实现，L1-L5 没有提前看到其他层本轮状态。L2 不能看到 L4 本轮估值判断；L4 不能看到 L5 本轮趋势判断。

### 主要输出字段

`ContextBrief` 重要字段：

- `data_summary`：本次数据概况。
- `layer_highlights`：关键信号摘要。全局 brief 里是五层摘要；层内 brief 里只保留本层摘要。
- `apparent_cross_layer_signals`：表面上看起来可能有关联的跨层线索。
- `task_description`：任务说明。
- `special_attention`：特别注意事项。

Layer context brief 则是每层自己的输入简报。

### 字段价值

有价值，但要小心。它能降低 prompt 混乱度，让每个 agent 更快知道自己该看什么。

真正重要的是它不能破坏隔离。当前实现用 layer-local brief 规避了这个问题：L1-L5 只拿本层 highlights，不拿全局 `apparent_cross_layer_signals`。

### 垃圾风险

风险是“摘要替代证据”：

- 摘要写成“市场恐惧”，但不给 VIX、信用利差、趋势、证据引用。
- 摘要把跨层关系提前下结论，例如“流动性支持估值”，导致 Bridge 只是复述。
- 摘要把新闻当证据。
- 如果未来有人把全局 `context_brief.json` 直接喂给 L1-L5，就会越权。必须继续使用 `layer_context_briefs/Lx.json`。

### 结构判断

结构合理，但它应该永远是“导航”，不是“证据本身”。当前 layer-local 过滤是必要设计，应保留为红线。下游强结论必须追 `evidence_refs`，不能只追 brief 里的短句。

## 2. L0 Object Canon

### 它收到什么

这是静态规则，不是本轮市场数据。它告诉所有 agent：我们到底在分析什么。

当前默认对象：

- `NDX`：主要判断对象。
- `QQQ`：常用可交易代理。
- `NDXE / QEW / QQEW`：等权参考，用来看广度和集中度。

### 它具体干什么

它防止对象混乱。

比如：

- QQQ 不是“所有科技股”。
- NDX 是市值加权指数。
- NDX 上涨可能只是少数巨头上涨，不代表整个纳指内部健康。
- QQQ 是 ETF 代理，和指数本身不是完全等价。

### 主要输出字段

`ObjectCanon` 字段：

- `primary_object`：主要对象，例如 NDX。
- `tradable_proxy`：可交易代理，例如 QQQ。
- `equal_weight_reference`：等权参考。
- `object_summary`：对象定义。
- `methodology_boundaries`：方法学边界。
- `analysis_boundaries`：系统不该越权判断的地方。
- `falsifiers`：会削弱对象口径的反证。

### 字段价值

非常有价值。金融分析里很多错误不是算错，而是对象搞错：

- 用 QQQ 技术图替代 NDX 基本面。
- 用 Mag7 基本面替代整个 NDX。
- 用等权弱直接说 NDX 一定跌。
- 用 NDX 结论推广到所有科技股。

### 垃圾风险

如果 Object Canon 只是一段模板说明，而 Final 不真的检查对象口径，它会变成装饰品。

所以关键不是有这个字段，而是 Final 和 objective firewall 是否真的使用它。

### 结构判断

必要且合理。建议以后在最终报告首屏或审计区明确显示“本报告判断对象是什么，不是什么”，这样普通读者不会误读。

## 3. L1 宏观流动性 Agent

### 它收到什么

L1 只收到宏观和流动性相关数据：

- 政策利率。
- 10 年期名义利率。
- 10 年期实际利率。
- 通胀预期。
- 期限利差。
- 净流动性。
- M2。
- 铜金比等增长预期代理。

它可以知道五层框架里其他层“负责什么”，但不能知道其他层本轮“看到了什么、判断了什么”。

### 它具体怎么分析

L1 回答一个问题：

> 宏观和流动性环境是在给 NDX 成长股估值提供燃料，还是在抽走燃料？

它的分析方式应该是机制链，不是贴标签。

例如：

- 实际利率高 -> 折现率高 -> 远期现金流现值下降 -> 成长股估值承压。
- 净流动性改善 -> 边际资金压力缓解 -> 风险资产短期获得支撑。
- 期限利差转正 -> 可能是衰退压力缓和，也可能是熊陡压力。
- 铜金比低 -> 增长预期弱，不能因为略有反弹就说经济恢复。

### 它输出什么字段

L1 输出 `LayerCard`，字段和其他 L 层一样：

- `layer`：这里是 L1。
- `generated_at`：生成时间。
- `core_facts`：核心事实，例如 10Y real rate 的值、分位、趋势。
- `local_conclusion`：本层局部结论，不是买卖建议。
- `confidence`：本层置信度。
- `risk_flags`：本层风险标签，例如 `valuation_compression`。
- `cross_layer_hooks`：请其他层验证的问题。
- `indicator_analyses`：每个指标的详细分析。
- `layer_synthesis`：本层综合段落。
- `internal_conflict_analysis`：本层内部冲突。
- `quality_self_check`：本层自检。
- `notes`：补充说明。

`indicator_analyses` 里面又有：

- `function_id`：指标函数名，例如 `get_10y_real_rate`。
- `metric`：展示名称。
- `current_reading`：当前读数。
- `normalized_state`：状态标签。
- `narrative`：可放进报告的指标解释。
- `reasoning_process`：从数据到判断的推理。
- `first_principles_chain`：机制链。
- `evidence_refs`：证据引用。
- `cross_layer_implications`：可能影响其他层的地方。
- `risk_flags`：该指标暴露的风险。
- `permission_type`：指标发言权类型。
- `canonical_question`：这个指标真正回答什么问题。
- `misread_guards`：常见误读。
- `cross_validation_targets`：需要哪些指标交叉验证。
- `falsifiers`：什么证据会推翻它。
- `confidence`：单指标置信度。

### 哪些字段有深刻价值

最有价值的是：

- `indicator_analyses[].reasoning_process`
- `indicator_analyses[].first_principles_chain`
- `indicator_analyses[].evidence_refs`
- `layer_synthesis`
- `internal_conflict_analysis`
- `quality_self_check.confidence_limitations`

因为它们不是一句“宏观偏紧”，而是说明：

- 哪个指标在发言。
- 它为什么能发言。
- 它不能证明什么。
- 它和本层其他指标有没有矛盾。
- 它需要 L4/L5 等其他层验证什么。

### 哪些字段容易变垃圾

- `normalized_state`：例如 `restrictive`。单独看没有太大价值。
- `risk_flags`：例如 `valuation_compression`。如果没有证据和机制，只是标签。
- `local_conclusion`：有用但容易过短，不能替代指标级推理。

### 结构判断

L1 结构合理。它不直接给买卖建议，这是对的。高实际利率、净流动性、期限结构这些东西不能直接推出“买/卖”，只能告诉后面：环境是顺风还是逆风。

建议：L1 的 `cross_layer_hooks` 要尽量具体，比如“请 L4 验证 earnings yield 与 real rate 的差距”，不要写泛泛的“请 L4 验证估值”。

## 4. L2 风险偏好 Agent

### 它收到什么

L2 只收到风险偏好、情绪、信用和仓位数据：

- VIX。
- VXN。
- VXN/VIX。
- 高收益债 OAS。
- 投资级 OAS。
- HY CCC vs BB 质量利差。
- HYG 动量。
- XLY/XLP。
- Crowdedness Dashboard。
- CNN Fear & Greed。

### 它具体怎么分析

L2 回答：

> 市场现在愿不愿意承担风险？这个风险承担健康吗，还是恐慌、贪婪、自满、拥挤或信用压力？

它不能判断估值合理，也不能判断趋势有效。

好的 L2 分析必须区分：

- 低 VIX 可能是稳定，也可能是自满。
- 高 VIX 可能是恐慌，也可能是反向机会。
- 信用利差比单纯股票情绪更硬。
- 恐贪指数是复合指标，必须先看总状态，再解释子项。
- HYG 反弹不能直接说明信用风险消失。

### 它输出什么字段

同样是 `LayerCard`。

对你担心的例子，关键在这里：L2 不应该只输出 `fear`。它应该输出：

- VIX 当前值、分位、趋势。
- VIX 为什么代表保护成本和恐慌。
- VIX 高位为什么不能自动等于买入机会。
- HY OAS 是否确认恐慌。
- CNN Fear & Greed 总分与子项是否背离。
- 本层内部是信用硬信号主导，还是情绪软信号主导。

在最近真实 run 里，L2 的产物不是只给了下游一个 `fear`。它保留了：

- `get_vix` 的 `narrative`：说明 VIX 处于极端高位，保护成本昂贵，但不能直接当买入信号。
- `get_vix` 的 `reasoning_process`：说明 VIX 水平、百分位、Spot/MA20 和恐慌加速。
- `layer_synthesis`：说明信用利差、VIX/VXN、HYG 反弹、恐贪子项之间的矛盾。
- `quality_self_check`：说明拥挤度、恐贪子项、HYG 反弹的置信度边界。

所以当前设计已经避免了“只传 fear”这个最差形态。

### 哪些字段有深刻价值

最有价值的是：

- `indicator_analyses[].reasoning_process`
- `internal_conflict_analysis`
- `quality_self_check.unresolved_internal_tensions`
- `cross_layer_hooks`

L2 最需要“内部冲突分析”。因为风险偏好本来就经常矛盾：

- VIX 高，但 HYG 反弹。
- 恐贪指数极恐，但某些子项贪婪。
- 信用利差走阔，但股票开始反弹。

如果 L2 能把这些矛盾讲清楚，它就有价值。

### 哪些字段容易变垃圾

- `normalized_state = fear` 或 `risk_off`：单独没有价值。
- `risk_flags = extreme_fear`：如果没有信用、波动、仓位的确认，就是空标签。
- CNN Fear & Greed 的子项：如果绕过总分，直接被 Bridge 升格成 high conflict，就会误导。

### 结构判断

L2 结构合理，但也是最容易产出“漂亮废话”的层。因为情绪指标天然诱人，容易写成“恐惧就是机会”“贪婪就是风险”这种二元句。

当前 schema guard 已经针对 CNN Fear & Greed 这类复合指标做了约束：子项不能绕过总分语义直接升格为高严重度跨层冲突。这是很必要的。

建议：L2 后续可以把“硬信号”和“软信号”分得更明确。硬信号如信用利差、IG/HY OAS；软信号如恐贪、put/call、情绪分项。下游应该优先消费硬信号。

## 5. L3 指数内部结构 Agent

### 它收到什么

L3 只收到指数内部健康度数据：

- A/D Line。
- 成分股高于均线比例。
- QQQ/QQEW 或 NDX/NDXE。
- Top10 / M7 集中度。
- M7 基本面。
- 新高新低。
- McClellan Oscillator。

### 它具体怎么分析

L3 回答：

> 指数运动是否由广泛成分股参与，还是少数权重股硬撑？

这是很关键的一层，因为 NDX 是市值加权。指数涨，不代表大多数股票都健康。

L3 应该区分：

- 广度：多数股票有没有参与。
- 集中度：头部股票占比多高。
- 领导力：是头部优质公司强，还是只有少数股票撑指数。
- 数据缺口：A/D、新高新低、McClellan 不可用时，不能假装有结论。

### 它输出什么字段

还是 `LayerCard`。

L3 的关键字段特别包括：

- `indicator_analyses`：每个广度/集中度指标的解释。
- `layer_synthesis`：结构健康、恶化、集中但有支撑，还是数据不足。
- `internal_conflict_analysis`：集中度高到底是优质龙头支撑，还是空心上涨。
- `quality_self_check.missing_or_weak_indicators`：缺哪些广度证据。
- `confidence_limitations`：因为数据缺失必须降低置信度的地方。

### 哪些字段有深刻价值

最有价值的是：

- `quality_self_check`
- `internal_conflict_analysis`
- `indicator_analyses[].falsifiers`
- `cross_layer_hooks` 对 L5 和 L4 的提问

L3 的价值不只是给一个 `healthy` 或 `deteriorating`，而是告诉系统：

- 趋势是否有广度支撑。
- 估值是否过度依赖少数巨头。
- 当前结构证据是否不足，需要降置信度。

### 哪些字段容易变垃圾

- `healthy` / `deteriorating` 标签。
- 用 QQQ/QQEW 一个指标直接代表全部广度。
- M7 强就说结构健康。
- 数据缺失时硬写结论。

### 结构判断

L3 结构非常必要，但当前也是最薄弱的一层。文档和 work log 已多次说明：L3 数据覆盖和 point-in-time universe 是长期风险。

好的地方是：系统现在允许 L3 明说“广度数据不足”，而不是强迫它产出假确定结论。Schema Guard 对 L3 是“强提示、非硬失败”，这比较合理。因为如果把 L3 缺口直接 hard fail，很多历史 run 会无法跑；但如果完全不提示，又会让报告假装结构证据充分。

建议：L3 是最值得继续补数据源的一层。因为它决定系统有没有读对 NDX：到底是整个指数健康，还是少数头部撑着。

## 6. L4 估值 Agent

### 它收到什么

L4 只收到估值、盈利收益率、风险补偿和基本面估值数据：

- NDX PE / Forward PE / PB / PS。
- 盈利收益率。
- FCF yield。
- 简式收益差距。
- Damodaran 美国 implied ERP。
- WorldPERatio / Trendonify / DanjuanFunds 等第三方估值校验。
- Forward earnings quality。
- 手动/Wind 估值输入。

### 它具体怎么分析

L4 回答：

> 当前价格相对于盈利、现金流、无风险资产和风险补偿有没有吸引力？

L4 不能因为价格趋势强就合理化估值，也不能因为情绪好就说估值合理。

它必须区分：

- 绝对估值：PE 多少。
- 历史位置：分位多少，来源是谁。
- 债券替代：盈利收益率相对 10Y 是否有安全垫。
- 风险补偿：ERP 是否足够。
- 盈利质量：Forward EPS 和 margin 是否支撑估值。
- 来源权限：人工/Wind、Trendonify、Danjuan、WorldPERatio、yfinance 各自能证明什么。

### 它输出什么字段

也是 `LayerCard`，但 L4 的 `indicator_analyses` 特别需要包含数据来源和发言权。

关键字段：

- `core_facts[].historical_percentile`：只能是数字或 null，不能塞说明文字。
- `indicator_analyses[].current_reading`：要写清楚 PE、分位、日期、来源。
- `indicator_analyses[].narrative`：估值相对什么贵或便宜。
- `indicator_analyses[].reasoning_process`：为什么从 PE/ERP/利率推到安全边际。
- `quality_self_check.missing_or_weak_indicators`：缺 forward earnings、简式收益差距等要明说。
- `cross_layer_hooks`：请 L1 验证利率，请 L2 验证风险偏好，请 L5 验证失速风险，请 L3 验证集中度依赖。

### 哪些字段有深刻价值

L4 最有价值的是：

- `permission_type`
- `canonical_question`
- `misread_guards`
- `data_quality`
- `reasoning_process`
- `quality_self_check`

因为估值层最容易越权：

- yfinance 成分股当前 PE 不能冒充官方 NDX 历史分位。
- WorldPERatio 标准差区间不能冒充 percentile。
- Damodaran 美国市场 ERP 不能替代 NDX 自身 ERP。
- 简式收益差距不能写成 Damodaran implied ERP。
- PE 分位低不等于一定便宜，还要看利率和盈利。

### 哪些字段容易变垃圾

- `cheap` / `expensive` 标签。
- “历史低位”但不说明是 5 年、10 年还是哪个来源。
- “ERP 高/低”但不说明口径。
- “估值有安全边际”但没有 earnings yield、real rate 或 FCF yield 支撑。
- “Forward EPS 支撑估值”但只是 yfinance component proxy，且覆盖率不足。

### 结构判断

L4 结构是合理的，而且是整个系统最需要严格数据发言权的一层。

最近真实 run 暴露了一个好现象和一个风险：

- 好现象：L4 没有只写“便宜”，而是写了 PE 5 年分位低、10 年分位中等、Damodaran 官方 ERP 偏低、简式收益差距可能偏薄、缺 forward earnings quality。
- 风险：如果下游只抓“PE 5 年分位低”这一条，就可能误读成“估值安全”。后来 Critic 确实指出了这个问题，Reviser 也修了。这说明治理链有价值。

建议：L4 后续应该继续强化“估值相对什么”的字段展示。普通读者最容易被“便宜/贵”误导，必须写成“相对 5 年历史便宜，但相对利率和风险补偿并不宽松”。

## 7. L5 价格趋势 Agent

### 它收到什么

L5 只收到价格、趋势、动量、波动和成交量数据：

- 价格相对均线。
- 多周期均线结构。
- RSI。
- MACD。
- ADX / +DI / -DI。
- ATR。
- OBV。
- 成交量结构。
- VWAP / MFI / CMF。
- Donchian channels。

### 它具体怎么分析

L5 回答：

> 价格趋势是否仍有效？动量是否确认？是否过热？失效条件在哪里？

它不能说估值合理，也不能说广度健康。

好的 L5 分析应该区分：

- 趋势方向。
- 趋势强度。
- 短期过热或超卖。
- 波动扩张。
- 量价确认。
- 支撑、阻力、失效条件。

### 它输出什么字段

也是 `LayerCard`。

L5 最关键字段：

- `indicator_analyses`：每个技术指标的机制解释。
- `layer_synthesis`：趋势状态，例如 uptrend、downtrend、overextended。
- `internal_conflict_analysis`：趋势强 vs 超买、价格下跌 vs OBV 背离。
- `cross_layer_hooks`：请 L3 验证广度，请 L4 验证估值压缩风险。
- `quality_self_check`：技术指标缺失或相互矛盾的地方。

### 哪些字段有深刻价值

有价值的是：

- `reasoning_process`
- `internal_conflict_analysis`
- 具体触发条件
- 对 L3/L4/L2 的验证问题

L5 的价值不是“涨/跌”，而是给 Final 一个时机边界：

- 趋势还在，但过热。
- 趋势已经破坏，但短期有反弹背离。
- 波动扩大，风险边界要放宽。
- 成交量不确认，趋势质量下降。

### 哪些字段容易变垃圾

- `uptrend` / `downtrend` 标签。
- RSI 超买就直接说要跌。
- MACD 金叉就说买入。
- 价格强就合理化估值。
- 趋势有效就忽略 L3 广度和 L4 估值。

### 结构判断

L5 结构合理。它被限制为“时机层”，不能给最终买卖建议，这是对的。

建议：L5 的输出最好始终包含“趋势失效条件”，而不只是趋势描述。否则它会变成技术指标播报员。

## 8. Bridge 跨层桥接 Agent

### 它收到什么

Bridge 收到 L1-L5 的 `LayerCard`。

它会读：

- 每层 `indicator_analyses`。
- 每层 `layer_synthesis`。
- 每层 `internal_conflict_analysis`。
- 每层 `cross_layer_hooks`。
- 每层 `risk_flags` 和 `confidence`。

它也可以收到 `event_refs`，但事件只能作为背景、催化剂或观察，不能替代 evidence refs。

### 它具体怎么分析

Bridge 不重新分析单指标。它的职责是：

> 把层与层之间的支撑、冲突、共振、传导关系显式建模。

它主要看三类关系：

1. 支撑关系：例如净流动性改善是否支持价格反弹。
2. 冲突关系：例如高实际利率 vs 高估值。
3. 传导路径：例如信用利差恶化如何传到股票趋势。

### 它输出什么字段

`BridgeMemo` 字段：

- `bridge_type`：桥接类型，例如 constraint、macro_valuation、breadth_trend。
- `layers_connected`：连接哪些层。
- `cross_layer_claims`：跨层支撑关系。
- `conflicts`：旧版冲突字段，兼容使用。
- `typed_conflicts`：新版结构化冲突。
- `resonance_chains`：跨层共振链。
- `transmission_paths`：跨层传导路径。
- `unresolved_questions`：下游必须保留的问题。
- `implication_for_ndx`：对 NDX 的综合影响。
- `key_uncertainties`：关键不确定性。
- `event_refs`：事件引用，不能替代证据。

`typed_conflicts` 里面的重要字段：

- `conflict_id`：稳定 ID。
- `conflict_type`：冲突类型。
- `severity`：严重程度。
- `confidence`：置信度。
- `description`：冲突描述。
- `mechanism`：为什么冲突成立。
- `implication`：对 NDX 的影响。
- `involved_layers`：涉及哪些层。
- `evidence_refs`：支撑证据。
- `event_refs`：事件背景。
- `falsifiers`：什么证据会削弱冲突。
- `status`：unresolved、confirmed、weakened。

`resonance_chains` 里面的重要字段：

- `chain_id`
- `description`
- `involved_layers`
- `evidence_refs`
- `confirming_indicators`
- `mechanism`
- `implication`
- `falsifiers`
- `confidence`

`transmission_paths` 里面的重要字段：

- `path_id`
- `source_layer`
- `target_layer`
- `mechanism`
- `evidence_refs`
- `implication`
- `confidence`
- `lag_hint`

### 哪些字段有深刻价值

Bridge 是整套系统最有独特价值的环节之一。真正有价值的是：

- `typed_conflicts`
- `resonance_chains`
- `transmission_paths`
- `unresolved_questions`
- `falsifiers`

这些字段能防止 Thesis 自己脑补关系。

例如不是简单说“宏观不好但估值低”，而是写成：

- L1 实际利率极高。
- L4 PE 从 5 年历史看偏低。
- Damodaran 官方 ERP 偏低。
- 所以这是“高折现率约束 vs 相对估值低位”的冲突。
- 如果真实利率回落且盈利上修，这个冲突会削弱。

这就比一句“中性偏谨慎”有价值多了。

### 哪些字段容易变垃圾

Bridge 的垃圾风险很典型：

- `description` 空着。
- `implication` 和 `description` 重复。
- `key_claims` 只说“支持”“压制”，没有机制。
- `typed_conflicts` 没有 evidence refs。
- `resonance_chains` 没有 confirming indicators。
- `transmission_paths` 没有 source/target 或 lag。
- 把复合指标子项直接升格为 high conflict。

最近真实 run 里就能看到一个小问题：某条 `resonance_chains` 的 `description` 为空，但 `mechanism` 写得比较完整。这说明字段价值有时被挤到别的字段里，结构上还可以更严。

### 结构判断

Bridge 的存在非常必要。没有 Bridge，Thesis 就会变成“总管自己把所有层读一遍然后编故事”，冲突很容易被写顺。

但 Bridge 也应该被持续加强。建议后续把以下字段设为更硬的质量要求：

- `resonance_chains[].description` 不得为空。
- `typed_conflicts[].evidence_refs` 不得为空。
- `transmission_paths[].mechanism` 必须说明传导方向和中间机制。
- `implication` 不得简单复制 `description`。

## 9. SynthesisPacket 综合输入包

### 它收到什么

SynthesisPacket 是代码压缩阶段，不是 LLM agent。它收到：

- L1-L5 LayerCards。
- BridgeMemo。
- evidence index。
- event index。
- objective firewall summary。
- high severity conflicts。

### 它具体怎么做

它的工作是把前面庞大的材料压成 Thesis 可以安全消费的包。

关键是：Thesis 不应该重新吞原始数据，也不应该替 L1-L5 补做指标分析。

### 它输出什么字段

`SynthesisPacket` 字段：

- `generated_at`：生成时间。
- `packet_meta`：数据包元信息。
- `context_summary`：上下文摘要。
- `layer_summaries`：五层压缩摘要。
- `bridge_summaries`：Bridge 压缩摘要。
- `high_severity_conflicts`：必须保留的高严重度旧式冲突。
- `high_severity_typed_conflicts`：必须保留的高严重度 typed conflicts。
- `objective_firewall_summary`：客观性防火墙。
- `evidence_index`：可追溯证据索引。
- `event_index`：事件索引。
- `synthesis_guidance`：给 Thesis 的约束。

`layer_summaries` 每项包括：

- `layer`
- `local_conclusion`
- `layer_synthesis`
- `indicator_refs`
- `key_evidence`
- `risk_flags`
- `internal_conflict_analysis`
- `cross_layer_hooks`
- `confidence`

### 哪些字段有深刻价值

最有价值的是：

- `evidence_index`
- `high_severity_typed_conflicts`
- `objective_firewall_summary`
- `layer_summaries[].key_evidence`
- `bridge_summaries[].typed_conflicts`

这一步决定下游有没有足够信息，不会退化成只拿一个标签。

最近真实 run 里，SynthesisPacket 对 L2 不是只保留 `risk_off`，而是保留了 VIX、VXN、HY OAS、IG OAS、HYG、XLY/XLP、Crowdedness 的关键证据和 L2 的整段综合。这是对的。

### 哪些字段容易变垃圾

- `context_summary` 太短，只说“31/39 指标成功”，没有质量边界。
- `key_evidence` 只拼字符串，若单位混乱会误导。
- `risk_flags` 只有标签，没有解释。
- `layer_summaries` 如果只保留 `local_conclusion`，就会退化成你担心的“fear 没用”。

### 结构判断

结构合理。它是防止 token 膨胀和上下文污染的关键。

建议：SynthesisPacket 后续可以对 `key_evidence` 做更结构化的单位、日期、来源展示，减少纯字符串造成的歧义。

## 10. Objective Firewall 客观性防火墙

### 它收到什么

它基于 SynthesisPacket 和上游 artifacts 生成摘要，用来提醒 Thesis/Final：

- 对象是否清楚。
- 指标发言权是否清楚。
- 时间和频率是否匹配。
- 是否有跨层验证。
- 最强反证是什么。
- 哪些张力还没解决。

### 它输出什么字段

`ObjectiveFirewallSummary` 字段：

- `object_clear`：对象是否清楚。
- `authority_clear`：指标发言权是否清楚。
- `timing_clear`：时间和频率是否大体匹配。
- `cross_layer_verified`：是否有跨层验证。
- `strongest_falsifier`：最强反证。
- `unresolved_tensions`：未解决张力。
- `warnings`：下游必须保留的警示。

### 字段价值

这个阶段很重要，因为它不是新增观点，而是防止越权。

它提醒后面：

- 你分析的是 NDX，不是所有科技股。
- 你不能让技术指标证明估值便宜。
- 你不能让代理指标冒充事实。
- 你不能在回测里用未来数据。
- 你不能没有跨层验证就下强结论。

### 垃圾风险

如果它只输出 `object_clear=true` 这种布尔值，而没有 `strongest_falsifier` 和 `warnings`，价值会下降。

### 结构判断

合理。建议 Final 的裁决说明里明确引用 objective firewall，而不是只说“分析完整”。

## 11. Thesis Builder 主论点 Agent

### 它收到什么

Thesis 收到的是 SynthesisPacket，而不是完整原始数据。

它应该看到：

- 五层压缩摘要。
- Bridge typed map。
- high severity conflicts。
- objective firewall summary。
- evidence index。
- synthesis guidance。

### 它具体怎么分析

Thesis 不是重新做研究。它的职责是：

> 把已经完成的层级分析和跨层关系组织成一个主论点草稿。

它要回答：

- 环境：L1-L3 看，能不能涨。
- 价值：L4 看，该不该买。
- 时机：L5 看，什么时候风险收益较好。
- 主论点：当前最终倾向是什么。
- 支撑链：哪些证据链支持主论点。
- 保留冲突：哪些冲突还不能解决。
- 依赖前提：什么条件改变会改变判断。

### 它输出什么字段

`ThesisDraft` 字段：

- `environment_assessment`：环境判断，主要整合 L1-L3。
- `valuation_assessment`：估值判断，主要整合 L4。
- `timing_assessment`：时机判断，主要整合 L5。
- `main_thesis`：主论点。
- `key_support_chains`：关键支撑链。
- `retained_conflicts`：必须保留的冲突。
- `dependencies`：论点依赖前提。
- `overall_confidence`：整体置信度。

`key_support_chains` 里包括：

- `chain_description`
- `evidence_refs`
- `event_refs`
- `weight`

### 哪些字段有深刻价值

最有价值的是：

- `key_support_chains`
- `retained_conflicts`
- `dependencies`
- `overall_confidence`

因为这些字段能让你追问：

- 这个观点靠哪几条证据链撑着？
- 权重是不是合理？
- 它承认了哪些反证？
- 什么情况会让它改变判断？

### 哪些字段容易变垃圾

Thesis 最容易变成“漂亮总结”。垃圾风险包括：

- `main_thesis` 写得顺，但没有 evidence refs。
- `key_support_chains` 只列支持自己的证据，不列反证。
- `retained_conflicts` 只是复制 Bridge，但没有说明为什么保留。
- `dependencies` 写成泛泛的“关注盈利、关注利率”。
- `overall_confidence=medium` 永远不变，成了默认装饰。

最近真实 run 里，Critic 就指出 Thesis 初稿有问题：它用“估值 5 年低位”支持安全边际，但没有充分处理 Damodaran ERP 偏低和实际利率高位。这说明 Thesis 仍可能过度顺滑，但后面的治理阶段能抓到。

### 结构判断

Thesis 结构合理，但它不是最可信的最后答案。它更像“初稿总编”。真正可信要看 Critic、Risk、Reviser、Final 后有没有把它打磨过。

建议：Thesis 的 `retained_conflicts` 应增加 `why_retained` 字段进入正式 schema。现在 prompt 要求有这个意思，但合同里仍是旧 `Conflict` 结构，容易丢失“为什么保留”。

## 12. Critic 批评 Agent

### 它收到什么

Critic 收到压缩后的 `governance_input`，不是完整原始数据。

它看到：

- Thesis 核心段落。
- Thesis dependencies。
- Thesis key support chains。
- high severity typed conflicts。
- key evidence refs。
- known data gaps。
- objective firewall summary。
- synthesis guidance。

### 它具体怎么分析

Critic 的工作不是继续写报告，而是挑错。

它重点攻击：

- 逻辑跳跃。
- 证据引用错误。
- 选择性引用。
- 抹平高严重度冲突。
- 过度自信。
- 循环论证。
- 未经证据支持的定量说法。

### 它输出什么字段

`Critique` 字段：

- `overall_assessment`：整体批评。
- `issues`：具体问题列表。
- `cross_layer_issues`：跨层逻辑问题。
- `revision_direction`：修订方向。

`issues` 每项包括：

- `target`：批评哪个字段。
- `issue`：问题是什么。
- `severity`：major、minor、suggestion。
- `suggestion`：怎么改。

### 哪些字段有深刻价值

最有价值的是：

- `issues[].target`
- `issues[].issue`
- `cross_layer_issues`
- `revision_direction`

Critic 的价值在于它能指出“哪一句错了，为什么错，应该怎么修”。

最近真实 run 里，Critic 指出：

- 主论点说中性偏谨慎，但支撑链偏向短期反弹。
- “估值历史低位”只抓 5 年低位，忽略 10 年中位和 ERP 偏低。
- 净流动性改善到 NDX 反弹的传导跳过 L2 信用利差。

这些都不是空话，是有价值的。

### 哪些字段容易变垃圾

- `overall_assessment` 只说“逻辑不够严谨”。
- `issues` 没有 target。
- `suggestion` 只是“加强论证”。
- 永远要求至少 2 个 major，导致没问题也硬挑问题。

### 结构判断

Critic 必要且有价值。它是防止 AI 自我陶醉的关键。

但有一点要注意：prompt 要求“至少包含 2 个 major 问题”，这有利于严格，但也可能导致模型在确实较好的报告里硬造 major。建议后续改成“如果存在问题，优先列 major；若无 major，必须说明没有 major 并列 residual risk”，这样更客观。

## 13. Risk Sentinel 风险哨兵 Agent

### 它收到什么

Risk Sentinel 也收到 `governance_input`。

它看到：

- Thesis 核心。
- dependencies。
- support chains。
- high severity conflicts。
- key evidence refs。
- known data gaps。
- objective firewall summary。
- unresolved questions。

### 它具体怎么分析

Risk Sentinel 不是判断最终立场，而是列风险边界。

它回答：

- 哪些条件会让主论点失效？
- 哪些风险已经 safe、warning、breached？
- 哪些风险必须保留在最终报告里？
- 冲突矩阵 A-M 中哪些触发？

### 它输出什么字段

`RiskBoundaryReport` 字段：

- `failure_conditions`：失效条件。
- `boundary_status`：风险边界状态。
- `must_preserve_risks`：最终报告必须保留的风险。
- `conflict_matrix_check`：冲突矩阵检查。

`failure_conditions` 每项通常包含：

- `condition`：什么条件发生。
- `impact`：会造成什么影响。
- `probability`：低/中/高，但不能编造具体概率。
- `triggered_by`：由哪些证据触发。

`boundary_status` 典型键：

- `valuation_compression`
- `earnings_miss`
- `liquidity_shock`
- `concentration_collapse`
- `breadth_deterioration`
- `sentiment_reversal`
- `trend_breakdown`

### 哪些字段有深刻价值

最有价值的是：

- `failure_conditions`
- `must_preserve_risks`
- `boundary_status`

因为它们把“观点”变成“条件判断”：

- 如果盈利无法抵消实际利率，估值压缩风险保留。
- 如果信用利差继续走阔，风险偏好不能说修复。
- 如果广度缺失，不能把趋势强当成健康上涨。

这比“市场可能有风险”强很多。

### 哪些字段容易变垃圾

- `probability=medium` 这种字段，如果没有样本依据，容易变成伪精确。
- `boundary_status=safe/warning/breached` 如果没有触发证据，也只是红黄绿灯。
- `must_preserve_risks` 如果写太长，可能变成重复 Thesis。
- 编造历史胜率、回测收益、点位、跌幅，这是红线。

### 结构判断

Risk Sentinel 很必要。它把“结论”翻译成“什么情况下错”。

但建议后续弱化 `probability` 的表面精确性。没有明确统计证据时，可以用 `likelihood_language` 或 `evidence_strength` 替代，避免读者误以为这是历史概率。

## 14. Schema / Trace Guard 结构与追踪校验

### 它收到什么

这是代码校验阶段，不是 LLM agent。它看到：

- SynthesisPacket。
- LayerCards。
- BridgeMemo。
- ThesisDraft。
- Critique。
- RiskBoundaryReport。

### 它具体怎么检查

它检查：

- JSON 结构是否正确。
- 必填字段是否缺失。
- evidence refs 是否存在。
- Bridge 是否引用死链。
- high severity conflicts 是否被 Thesis 保留。
- Risk 是否为空。
- L1-L5 是否输出足够的 v2 字段。
- 复合指标子项是否被过度升格。
- L3 结构覆盖是否薄弱。

### 它输出什么字段

`SchemaGuardReport` 字段：

- `passed`：是否通过。
- `structural_issues`：结构问题。
- `consistency_issues`：一致性问题。
- `missing_fields`：缺失字段。
- `suggested_fixes`：建议修复。

### 哪些字段有深刻价值

最有价值的是：

- `passed`
- `consistency_issues`
- `suggested_fixes`

它不是研究洞察，但它能防止“断链报告”发布。

### 哪些字段容易变垃圾

- `passed=true` 可能让人误会内容一定正确。它只能说明结构和引用较好，不说明投资判断一定对。
- `suggested_fixes` 如果长期只是软提示，可能被忽略。

### 结构判断

必要，而且应该保留。尤其对你担心的“下游只拿到标签”问题，Schema Guard 可以进一步升级：检查 SynthesisPacket 是否保留每层 `indicator_refs`、`key_evidence`、`layer_synthesis`，而不是只保留 `local_conclusion`。

## 15. GovernanceInputPacket 治理阶段窄输入

### 它收到什么

它是给 Critic、Risk、Reviser、Final 的压缩包。

### 它具体怎么做

它减少治理阶段的 token 膨胀，避免后面几个 agent 重新吞入所有原始数据。

### 主要字段

- `thesis_main`
- `thesis_environment`
- `thesis_valuation`
- `thesis_timing`
- `thesis_confidence`
- `thesis_dependencies`
- `thesis_key_support_chains`
- `retained_conflict_types`
- `high_severity_typed_conflicts`
- `objective_firewall_summary`
- `schema_passed`
- `schema_structural_issues`
- `schema_consistency_issues`
- `schema_missing_fields`
- `must_preserve_risks`
- `key_evidence_refs`
- `key_event_refs`
- `known_data_gaps`
- `unresolved_questions`
- `synthesis_guidance`
- `critique_overall`
- `critique_cross_layer_issues`
- `revision_summary`

### 字段价值

价值在于“只给治理阶段需要的信息”。这样 Reviser 和 Final 不会重新自由发挥，也不会重新分析所有原始指标。

### 垃圾风险

如果压缩过度，它会丢掉关键证据。

比如只保留：

```text
thesis_valuation = 估值偏低
```

却不保留：

```text
L4 PE 5年分位18%，10年分位46%，Damodaran官方ERP偏低，简式收益差距薄
```

那 Final 就没法真正审。

### 结构判断

合理，但要持续检查“压缩没有压掉证据”。现在它有 `key_evidence_refs`，这是正确方向。

## 16. Reviser 修订 Agent

### 它收到什么

Reviser 收到 governance input，里面已经包含：

- 原 Thesis。
- Critic 的整体批评和跨层问题。
- Risk Sentinel 的 must preserve risks。
- Schema Guard 的问题。
- 高严重度冲突。
- key evidence refs。
- known data gaps。

### 它具体怎么分析

Reviser 是编辑，不是新分析师。

它要做：

- 接受有效批评。
- 拒绝不合理批评并说明原因。
- 修复证据引用错误。
- 弱化过度自信。
- 把风险哨兵必须保留的风险写回。
- 保留未解决冲突。
- 生成修订后的 Thesis。

### 它输出什么字段

`AnalysisRevised` 字段：

- `revision_summary`：修订说明。
- `accepted_critiques`：采纳哪些批评。
- `rejected_critiques`：拒绝哪些批评，理由是什么。
- `revised_thesis`：修订后的 ThesisDraft。
- `remaining_conflicts`：仍然保留的冲突。

### 哪些字段有深刻价值

最有价值的是：

- `revision_summary`
- `accepted_critiques`
- `rejected_critiques`
- `remaining_conflicts`

这些字段能让你看到 AI 是否真的听了批评，还是只是重新写了一遍。

最近真实 run 里，Reviser 明确采纳了 Critic 对净流动性传导链、估值安全边际、趋势风险的批评，并修订主论点。这说明 Reviser 不是纯装饰。

### 哪些字段容易变垃圾

- `revision_summary` 写成“已优化表达”。
- `accepted_critiques` 全部采纳，但实际 revised_thesis 没改。
- `rejected_critiques` 永远为空，说明模型不敢坚持判断。
- `remaining_conflicts` 只是复制上游，没有解释为什么仍未解决。

### 结构判断

结构合理。它是 AI 系统里很重要的“第二遍写作”。

建议：Reviser 输出可以增加一个字段 `material_changes`，逐条说明原句怎么改成新句。这样更方便审查它是否真的修了。

## 17. Final Adjudicator 最终裁决 Agent

### 它收到什么

Final 收到压缩治理输入，不重新看原始数据自由发挥。

它看到：

- 修订后的 Thesis 核心。
- 修订后的支撑链。
- retained conflict types。
- high severity typed conflicts。
- objective firewall summary。
- Schema Guard 结果。
- must preserve risks。
- key evidence refs。
- known data gaps。
- Critic 意见。
- revision summary。

### 它具体怎么分析

Final 是裁判，不是写手。

它回答：

1. 能不能批准进入最终报告。
2. 最终立场是什么。
3. 置信度是什么。
4. 哪些风险必须保留。
5. 如果不能批准，阻塞项是什么。

### 它输出什么字段

`FinalAdjudication` 字段：

- `approval_status`：批准状态。
- `final_stance`：最终立场。
- `confidence`：置信度。
- `key_support_chains`：采纳的关键支撑链。
- `must_preserve_risks`：必须保留的风险。
- `blocking_issues`：阻塞问题。
- `adjudicator_notes`：裁决说明。
- `evidence_refs`：支撑裁决的关键证据。
- `token_usage`：token 使用统计。

`approval_status` 可能是：

- `approved`
- `approved_with_reservations`
- `needs_revision`
- `rejected`

### 哪些字段有深刻价值

最有价值的是：

- `approval_status`
- `must_preserve_risks`
- `blocking_issues`
- `adjudicator_notes`
- `evidence_refs`

Final 的价值不是给一句“中性偏谨慎”，而是告诉你：

- 为什么可以发布。
- 有哪些保留意见。
- 哪些风险不准在最终成稿中淡化。
- 如果不能发布，具体卡在哪里。

### 哪些字段容易变垃圾

- `final_stance = 中性偏谨慎`：单独看信息量很低。
- `confidence = medium`：如果没有解释，就是默认值。
- `adjudicator_notes` 只说“分析完整，批准”，没有具体证据。
- `evidence_refs` 写“Bridge Memo”这种泛引用，而不是具体指标 refs。
- `approved_with_reservations` 长期变成默认状态，失去区分度。

最近真实 run 里，Final 输出了 `approved_with_reservations`、`中性偏谨慎`、4 条 must preserve risks、无 blocking issues。这个比单独立场有价值。但它的 `evidence_refs` 仍有点泛，例如“Bridge Memo: macro_valuation 识别的 L1-L4 冲突”，未来可以更具体到 `L1.get_10y_real_rate` 和 `L4.get_damodaran_us_implied_erp`。

### 结构判断

Final 必要且合理。最重要的原则是：写稿的人不能给自己放行。

建议：

- Final 的 `evidence_refs` 应该尽量引用具体 evidence refs，而不是只引用阶段名。
- 如果 `approval_status=approved_with_reservations`，必须说明 reservations 是什么，并确保它们进入 final report 首屏或风险区。
- 如果 DataIntegrity blocked，Final 不应该继续输出可发布立场。

## 18. DataIntegrity 发布闸门

### 它收到什么

DataIntegrity 收到采集数据、日期、数据质量、未来日期检查、回测边界等。

### 它具体怎么做

它决定数据层面是否允许发布：

- 是否存在晚于回测日的业务日期。
- 是否有严重 future data contamination。
- 是否有不可发布数据缺口。
- 是否需要 blocked / unpublishable。

### 输出字段

典型字段：

- `blocked`
- `unpublishable`
- `publish_status`
- `blocking_reasons`
- `future_date_violations`
- `notes`
- `strict_backtest_invariants`

### 字段价值

这是红线闸门。它比 Final 更底层。

如果 DataIntegrity blocked，哪怕 Final 写得再好，也不能当作可发布结论。

### 垃圾风险

- 只输出一个百分比完整度，让人误以为 90% 就可靠。
- 不递归检查嵌套日期。
- 只检查指标主日期，不检查 notes、chart sidecar、news sidecar。

### 结构判断

非常必要。它应该在报告首屏显示，不应该藏在审计区最下面。

## 19. Native brief / Workbench / Legacy HTML

### 它收到什么

它们消费 vNext artifacts：

- layer cards。
- bridge memos。
- synthesis packet。
- thesis。
- critique。
- risk report。
- schema guard。
- final adjudication。
- data integrity report。
- chart time series。
- news sidecar。

### 它具体做什么

这不是新的研究 agent，而是输出层：

- `brief`：连续阅读报告。
- `workbench`：看盘式交互探索。
- legacy HTML：兼容旧输出。

### 字段价值

输出层的价值是让你能审查系统，而不是只看结论。

好的输出应该让你：

- 看到最终立场。
- 看到发布状态。
- 看到风险边界。
- 展开每层指标。
- 点击 evidence refs。
- 看到图表和数据日期。
- 看到 DataIntegrity 和回测边界。

### 垃圾风险

- 页面很好看，但只展示最终结论。
- 图表没有 evidence ref。
- 风险藏得太深。
- token usage 原始 dict 直接展示给普通用户。
- legacy adapter 把 vNext artifacts 拼成旧式漂亮叙事，反而掩盖原生推理链。

### 结构判断

Native brief 是正确主方向。legacy HTML 只能兼容，不能成为主要认知生产者。

## 20. 回到你最担心的问题：会不会只传一个 useless 标签？

我的判断：

> 当前主设计已经意识到这个问题，并且大部分关键链路没有退化到只传标签。但仍要防止某些 UI、压缩包或下游 agent 偷懒只消费短字段。

以 L2/VIX 为例，坏设计会这样：

```text
VIX -> fear -> Thesis 写“市场恐惧”
```

这种确实没什么用。

当前设计更像这样：

```text
VIX 指标:
  current_reading: VIX=33.62，高于 MA20，10年百分位 97%
  normalized_state: high_and_rising
  narrative: 隐含波动率定价恐慌，但高 VIX 本身不构成买入信号
  reasoning_process: 水平、分位、Spot/MA20 共同说明恐慌加速
  evidence_refs: L2.get_vix

L2 综合:
  信用利差、VIX/VXN、HYG、恐贪子项互相验证或冲突

Bridge:
  信用和波动压力如何传导到趋势和估值

Risk:
  如果信用利差继续恶化，风险偏好不能说修复
```

这个结构是有信息量的。

但必须守住一个原则：

> `normalized_state` 和 `risk_flags` 只能当索引标签，不能当判断本身。

真正判断必须来自：

- 数值。
- 日期。
- 来源。
- 分位或相对位置。
- 机制链。
- 证据引用。
- 反证条件。
- 跨层验证。

## 21. 当前结构最有价值的部分

我认为最有价值的是这几块：

1. `indicator_analyses`

这是最重要的底稿。它把每个指标从“数值”变成“有证据、有机制、有边界的判断”。

2. `internal_conflict_analysis`

这能防止每层内部变成单一标签。例如 L2 可以承认“信用很差，但 HYG 反弹”；L4 可以承认“PE 5 年分位低，但 ERP 和利率不友好”。

3. `cross_layer_hooks`

这是每层主动提出“我需要其他层验证什么”。这比后面硬凑跨层关系好。

4. `typed_conflicts`

这是 Bridge 的核心资产。它把跨层冲突结构化，避免 Thesis 抹平冲突。

5. `objective_firewall_summary`

它提醒下游不要指标越权、对象错位、时间错配。

6. `must_preserve_risks`

这是最终报告里不准淡化的风险清单。

7. `blocking_issues`

如果 Final 不批准，必须给具体阻塞项。这比含糊说“需要修订”有价值。

## 22. 当前最像“垃圾风险”的部分

这些字段不是没用，但如果单独使用就很危险：

1. `normalized_state`

例如 `risk_off`、`expensive`、`uptrend`。它适合做筛选标签，不适合做结论。

2. `risk_flags`

例如 `valuation_compression`。没有机制和证据时只是标签。

3. `local_conclusion`

有用，但太短。下游不能只读它。

4. `overall_confidence=medium`

如果大多数阶段默认 medium，区分度会下降。

5. `probability=medium`

如果没有统计证据，容易让人误解为概率估计。

6. `implication` 重复 `description`

最近真实 run 里部分 retained conflict 就有这个问题。说明字段之间还需要去重和分工。

7. 空的 `description`

Bridge resonance chain 如果 description 空，但 mechanism 有内容，说明模型没有完全遵守字段意图。

8. 泛化 `evidence_refs`

Final 里如果写“Bridge Memo 识别的冲突”，不如直接写具体 `L1.get_10y_real_rate`、`L4.get_ndx_pe_and_earnings_yield`。

## 23. 我建议的结构改进

### 改进 1：下游禁止只消费标签字段

明确规则：

- `normalized_state`
- `risk_flags`
- `local_conclusion`

只能作为索引或摘要，不能作为主证据。

Thesis、Bridge、Final 必须优先消费：

- `indicator_analyses[].reasoning_process`
- `indicator_analyses[].evidence_refs`
- `layer_synthesis`
- `internal_conflict_analysis`
- `quality_self_check`

### 改进 2：给每个阶段加“字段质量红线”

例如：

- `Bridge.resonance_chains[].description` 不得为空。
- `Conflict.implication` 不得复制 `description`。
- `Final.evidence_refs` 必须包含具体 evidence refs，不能只有阶段名。
- `Risk.failure_conditions[].probability` 若无统计证据，应改为 `evidence_strength`。

### 改进 3：把“好字段”和“标签字段”在 UI 上分层

报告里不要让读者只看到：

```text
L2: risk_off
```

应该看到：

```text
L2: risk_off
主证据：HY OAS 处于高分位并走阔，VIX/VXN 极高
反向信号：HYG 反弹、恐贪子项分裂
需要验证：信用利差是否收窄，L3 广度是否改善
```

### 改进 4：给每个 agent 增加“本阶段有没有垃圾输出”的自动审计

可以做一个简单 quality scanner：

- 只输出状态标签但没有 evidence refs：警告。
- `narrative` 很长但 `reasoning_process` 为空：警告。
- `evidence_refs` 不存在：阻断。
- `description` 和 `implication` 高度重复：警告。
- `probability` 出现具体百分比但 evidence refs 没有统计字段：阻断。

### 改进 5：做一份“字段价值地图”

把字段分成三类：

- 一等证据字段：`evidence_refs`、数值、日期、来源、data_quality。
- 推理字段：`reasoning_process`、`first_principles_chain`、`mechanism`、`falsifiers`。
- 摘要标签字段：`normalized_state`、`risk_flags`、`confidence`。

下游使用时必须知道自己拿的是哪一类。

## 24. 每个 agent 的结构评分

这是我的主观审查，不是测试结果。

| 阶段 | 结构合理性 | 当前价值 | 垃圾风险 | 重点建议 |
| --- | --- | --- | --- | --- |
| Data / AnalysisPacket | 高 | 高 | 高 | 继续严守日期、来源、sidecar、inactive manual |
| Context Brief | 中高 | 中 | 中 | 不能让摘要替代证据 |
| Object Canon | 高 | 高 | 低 | Final 要显式消费 |
| L1 | 高 | 高 | 中 | hooks 要继续具体化 |
| L2 | 高 | 高 | 中高 | 防止情绪标签化，硬信号优先 |
| L3 | 高 | 中 | 高 | 数据源和 point-in-time universe 是关键 |
| L4 | 高 | 高 | 高 | 数据发言权必须继续最严格 |
| L5 | 高 | 中高 | 中 | 必须输出失效条件，不只描述趋势 |
| Bridge | 高 | 高 | 中 | 强化 typed map 字段完整性 |
| SynthesisPacket | 高 | 高 | 中 | 防止压缩过度 |
| Objective Firewall | 高 | 中高 | 中 | Final 应更显式引用 |
| Thesis | 中高 | 中 | 中高 | 初稿角色，不应被当最终答案 |
| Critic | 高 | 高 | 中 | 避免硬造 major 问题 |
| Risk Sentinel | 高 | 高 | 中 | 避免伪概率 |
| Schema Guard | 高 | 高 | 低 | 可增加字段质量扫描 |
| Reviser | 高 | 中高 | 中 | 增加 material changes 更好审 |
| Final | 高 | 中高 | 中 | evidence refs 要更具体 |
| Native brief | 高 | 高 | 中 | 保留可追溯底稿，不只展示结论 |

## 25. 最终判断

这套 agent 架构总体不是花架子。它的核心设计有真实价值：

- L1-L5 负责局部认知。
- Bridge 负责跨层关系。
- Thesis 负责组织论点。
- Critic/Risk/Schema/Reviser/Final 负责治理。

它已经避免了最粗糙的“一个 fear 标签传到底”的问题，因为主链路保留了指标级叙事、推理过程、证据引用、层内冲突和质量自检。

但是，它仍然需要继续警惕“字段看起来多，但下游只消费短标签”的退化。真正的判断标准应该是：

> 下游每一个重要结论，都能不能追到具体 evidence ref、机制链、反证条件和数据边界。

如果能，这个 agent 有价值。

如果不能，再专业的 agent 名字也只是包装。

我建议下一步优先做两件事：

1. 写一个自动审计脚本，检查每个 artifact 是否存在“标签化输出、空字段、重复字段、死链 evidence ref、无证据概率”。
2. 在 native brief 中增加“每个 agent 的输入/输出审计视图”，让你能点开看到：这个 agent 到底收到了什么、输出了什么、下游用了什么。

这样你就不需要相信 AI 自称“分析得很深”，而是能直接看到它有没有真的留下可审计的推理链。
