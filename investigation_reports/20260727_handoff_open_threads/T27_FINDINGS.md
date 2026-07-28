# T27 调查结论：`price_reflection_map` 从"偏未反映"倒向"偏已反映"

> 对应 `investigation_reports/20260727_handoff_open_threads/HANDOFF.md` T27 一节。
> 本文档只讲结论与证据，不声明现状（现状以 `现在.md` 为准）。

## 一、现象重述

对照两次同一数据日（2026-07-25）的真实 run：

| run | credit | rates | valuation | technical_panic | liquidity | not_reflected 数 |
|---|---|---|---|---|---|---|
| `20260725_145833`（14:58，瘦身前） | not_reflected | partially_reflected | partially_reflected | not_reflected | not_reflected | **3** |
| `20260725_232410`（23:24，瘦身后） | partially_reflected | partially_reflected | partially_reflected | partially_reflected | largely_reflected | **0** |

（直接读取两份 `bridge_memos/bridge_0.json` 复核一致，且经脚本核对 `thesis_draft.json`、
`final_adjudication.json` 的 `price_reflection_map` 与 bridge 逐字相同——倒向 100% 发生在
bridge 生成，thesis/final 只是原样继承，这一点与主对话已确认事实完全吻合。）

## 二、已证伪的假设

**假设："2026-07-25 输入瘦身"改动导致 bridge 输入变薄，模型看到的信息变少，从而倾向乐观判断。**
这是 HANDOFF 给出的优先假设，本次调查将其证伪：

1. `src/agent_analysis/orchestrator.py:238-274`（`NARRATIVE_STAGE_PROMPT_DROP_FIELDS`）
   的注释明确写着"Thesis / Counter-Thesis prompt 瘦身"，字典的 key 只有 `"thesis"` 和
   `"counter_thesis"` 两个，没有 `"bridge"`。
2. `_sanitize_prompt_payload`（`orchestrator.py:5883-5911`）里，`stage_key == "bridge"` 分支
   （5884-5885 行）只调用 `self._strip_empty_event_prompt_fields(payload)`，不做任何
   evidence_index 压缩、字段丢弃或 L4 摘要化；而 `"thesis"` / `"counter_thesis"` 分支
   （5886-5900 行）才会依次调用 `_slim_object_run_gate_for_prompt`、
   `_drop_low_value_synthesis_fields_for_prompt`、`_slim_evidence_index_for_prompt`。
3. 实测两次 run 的 `prompt_audit/bridge/attempt_1.payload.json`：`payload` 顶层键
   （`candidate_cross_layer_links` / `context_brief` / `layer_cards`）完全一致，
   `layer_cards[i]` 的字段结构（`core_facts` / `indicator_analyses` / `local_conclusion` 等）
   完全一致，五个 layer card 都存在、都完整。
4. 实测两次 run 的 `attempt_1.prompt.txt`：从文件开头到 `## Runtime Input` 标记
   （前 10838 字符）**逐字节相同**（Python 字符串比较 `True`）——即桥接阶段的
   instruction 模板本身没有任何改动。

**结论：bridge 阶段的 prompt 输入根本没有被这批瘦身工作触碰过，"输入瘦身导致判断倒向"
这条线索到此为止，不需要再查。**

## 三、逐步证据

### 3.1 prompt 说明书是否变了（HANDOFF 步骤 2）

```
git log --follow -p --since=2026-07-01 --until=2026-07-27 -- src/agent_analysis/prompts/cross_layer_bridge.md
```

最近一次改动是 `2026-07-12`（commit `2443be5`），早于两次 run（均为 `2026-07-25`）。
`git log --since="2026-07-25 00:00" --until="2026-07-26 00:00" --oneline` 显示
**2026-07-25 全天只有一个提交**：`9f8d484`（`Sat Jul 25 12:22:25 2026 +0800`）——
早于两次 run（14:58 和 23:24）。查看该提交内容（L4 yfinance 句柄/缓存修复 +
reviser 证据引用净化 + `get_ndx_earnings_revision_metrics` 的 MetricAuthority 登记），
**不涉及** bridge prompt 构造、`price_reflection_map` 相关代码，或 L1-L5 layer card 的
prompt/契约。

**结论：两次 run 使用的是完全相同的代码提交，两次之间没有任何代码或 prompt 变更。**
这直接排除了裁决 (a)"某个改动系统性削弱了识别能力"——没有改动可以指认。

### 3.2 上游数据差异有多大（HANDOFF 步骤 3）

对 `context_brief`（bridge payload 中携带原始指标读数与分位数的字段）做逐字段递归 diff，
**全文 47 个字段中只有 2 个数值不同**：

- `layer_highlights.L3`：A/D 进退线 275 → 286，McClellan Oscillator -4.73 → -3.51
  （两者都是当日 8.5 小时内可能自然更新的广度指标，量级极小）
- 其余全部字段——10Y 实际利率 2.43%/99.6 分位、10Y 名义利率 4.71%/99.24 分位、
  HY OAS 2.77%/16.8 分位、HY CCC-BB 尾部利差 8.25pp/99.9 分位、NDX PE 30.31/47.08 分位、
  Wind PE 30.27/45.52 分位、VIX 18.58、VXN 28.39、净流动性动量 +105.86B、
  M2 同比 5.58%/43.3 分位、QQQ 收盘价 684.23、Donchian 下轨 682.48、RSI 39.29、
  OBV distribution——**逐字节相同**。

**重要修正**：主对话此前给出的"两次 run 上游数据不同，NDX PE 分位一个写 45%、一个写 47%"
这一佐证需要澄清——45.52%（Wind PE）和 47.08%（非 Wind/"丹诸"口径 PE）**两个数字在两次
run 的原始数据里都同时存在、逐字节相同**（见 `context_brief.layer_highlights.L4`）。
两次 bridge **输出**的冲突描述文本里，一次只提了"45%左右"、一次两个都提了，
这是模型自己在写作时选择引用哪个数字，**不是**上游数据口径发生了变化。

**结论：raw 市场数据本身几乎没有差异，不足以解释五类判断的整体迁移。**

### 3.3 那差异从哪来：L1-L5 layer card 本身是独立重新采样的

虽然 raw 数据相同，但 `layer_cards[i]` 里 LLM 撰写的内容——`local_conclusion`、
`layer_synthesis`、`indicator_analyses[].narrative/reasoning_process/first_principles_chain`、
`risk_flags` 标签、乃至 `core_facts.value` 的格式（例如 L1 的 "2.43%, 10y percentile 99.6"
在 A 里写了分位数文字、B 里只写 "2.43%"）——**两次 run 逐字不同**。每个 layer card 的
`generated_at` 时间戳也不同（L1: 07:04:35 vs 15:31:13；L5: 07:08:36 vs 15:37:05），
证实 L1-L5 五层分析与 bridge 本身在两次 run 里各自是**独立的真实 LLM 采样**，
不是"固定 layer card、只重跑 bridge"。

**关键个案（technical_panic 类别）**：L5 layer card 的 `core_facts`
（QQQ 684.23、Donchian 下轨 682.48、RSI 39.29、OBV distribution）在两次 run **逐字节相同**。
但 bridge 自己的 `price_reflection_map` 叙述：

- A（145833）：「VIX 18.58 中等偏高但未进入恐慌区间...成交量未异常放大」→ `not_reflected`
- B（232410）：「价格已跌至 Donchian 下轨，OBV 派发，RSI 39 未超卖...恐慌尚未完全进入价格」
  → `partially_reflected`

注意 B 所谓"已跌至 Donchian 下轨"其实和 A 自己 L5 layer card 的原话
"价格接近 20 日 Donchian 下轨，存在破位风险"说的是**同一组数字**（684.23 距 682.48 还有
1.75 点，两次都没有真正跌破）——只是 bridge 在两次独立采样里，对同一份可用输入选择了
不同的措辞强度和不同的证据落点（A 选了 VIX/ADX/成交量，B 选了 Donchian/OBV/RSI）。
这是叙事采样方差的直接证据，不是数据变了。

**liquidity 类别的结构性放大器**：`PRICE_REFLECTION_CATEGORIES["liquidity"]["hint"]`
（`orchestrator.py:330-334`）写的是"政策/市场流动性冲击与修复是否已被价格反映"——
这条 hint 把"冲击"（风险，该被读作 `not_reflected` 才对）和"修复"（利好，也可以被读作
`not_reflected`——即"改善还没被定价"）两个**方向相反**的含义捆绑在同一个
`reflected_state` 轴上。`cross_layer_bridge.md:200` 的正文同样只说"每类必须写
`reflected_state`"，没有进一步规定 liquidity 类目到底该按哪个方向读。对同一组 L1 原始
数据（实际利率/名义利率极端高位 + 净流动性 4 周动量转正 + M2 回升），两次 run 的 bridge
各自选了不同方向：

- A：liquidity target = "净流动性改善对风险资产的支撑"，判 `not_reflected`
  （"改善尚未推动 NDX 上涨"）
- B：liquidity target = "系统流动性环境"，判 `largely_reflected`
  （"紧缩路径已被市场广泛讨论...主要部分已反映"）

这条 hint 从 2026-07-12 至今未变过（两次 run 都读到同一份说明书），**不是本次瘦身或
任何近期改动引入的新问题**，但它确实是五类里唯一出现"整类反向"的类别，且恰好是本次
波动最大的一类，值得记为一个待改进的合约设计弱点（见下文"机制裁决"）。

### 3.4 是否存在证据面缺失的连锁反应

已排查：两次 run `function_availability_percent` 均 93.9%（主对话已确认），本次复核
的 `context_brief.data_summary` 字段也写着相同的 "47/50 个指标成功"。没有发现任何
指标在其中一次 run 里缺失、导致另一侧证据面更单薄的情况。

## 四、机制裁决

**裁决：(b) 采样方差 + 一个既有（非本次改动引入）的合约设计弱点叠加，不是缺陷（a），
也不能简单归为"纯属正常、无需改进"（c）。**

依据：

1. 两次 run 之间代码提交为零差异（3.1），prompt 说明书为零差异（3.1），
   原始市场数据差异可忽略（3.2）——**没有任何可指认的"改动"能支撑裁决 (a)**。
2. 差异的真实来源是 L1-L5 + bridge **六个独立 LLM 采样阶段**各自的叙事选择
   （3.3），这本质上是"两次完整 pipeline 的独立实现"之间的差异，而不是
   "同一 bridge 输入、resample 出不同结果"——HANDOFF 里"6/6 采样稳定复现"的实验
   测的是 thesis 继承 bridge 现成 map 是否稳定（继承路径上确实是恒等映射，逐 case
   验证见二.开头），**不能**当作"bridge 判断本身稳定"的证据，主对话已指出、本次复核
   确认无误。
3. 但 liquidity 类别的 `reflected_state` 语义本身允许"改善未定价"和"紧缩已定价"
   两种方向相反的合法读法（3.3 末），这不是纯粹的采样噪声，而是合约/说明书里一个
   可以被收紧的定义空隙，会系统性放大这一类的方差。这条弱点从 7 月 12 日说明书写定
   以来就存在，与本次两次 run 的时间窗口无关，因此不构成"缺陷回归"，但值得独立记一笔
   改进建议（不属于本次裁决的必需修复项）。

**因此不建议按裁决 (a) 的路径去改 `orchestrator.py`——没有可定位的回归代码。**
真正能证伪"这是不是系统性倾向"的实验，只能是下面这个真实采样实验。

## 四之二、终局验证实测结果（2026-07-28 已执行，裁决 (b) 成立且方向被反转）

用户批准后已真实执行第五节的重复采样实验，方法比原设计更严格：**直接回放两次真实 run
已落盘的 `prompt_audit/bridge/attempt_1.prompt.txt` 原文**（与当时真正发给模型的字节
完全一致，零组装漂移），固定模型 `deepseek-v4-flash`，每组 n=4，共 8 次真实调用；
统计口径复用 `orchestrator._ensure_price_reflection_categories`，与真实 run 一致。

| payload | 历史那一次的 `not_reflected` 数 | 本次重复采样 4 次 |
|---|---|---|
| A = `20260725_145833` | **3** | **0, 1, 1, 0** |
| B = `20260725_232410` | **0** | **1, 1, 1, 2** |

三条结论：

1. **两次历史值都无法在自己的 payload 上复现。** A 的 payload 重采 4 次没有一次达到 3；
   B 的 payload 重采 4 次没有一次落到 0。历史上那组 3 vs 0 的强对比，是两个尾部样本
   刚好撞在一起，不是 payload 的系统性差异。
2. **两组分布重叠，且方向与"倒向已反映"的担忧相反。** A 组落在 0–1，B 组落在 1–2——
   被怀疑"系统性倒向已反映"的 B payload，重复采样下反而比 A payload **更偏向
   `not_reflected`**。裁决 (b) 不仅成立，原假设的方向本身也不成立。
3. **判读标准按第五节事先写定的两条对照，结论唯一。** 事先约定"两组各自内部有分散 →
   采样方差可解释"，实测 A 组内部分散（0/1）、B 组内部分散（1/2），落在这一支；
   "A 稳定高、B 稳定 0 → payload 驱动"的那一支未出现。

**附带实测观察（都与三.3 的分析互相印证）：**

- 8 个样本**全部**是模型原生写满五类（`native_categories == 5`），一次都没触发
  `_ensure_price_reflection_categories` 补齐——所以下面第六节的 `run_review` 占位盲点，
  在本批样本里同样没有被触发，与两次历史 run 一致。
- 出现的 4 次 `unclear` **全部是模型原生输出**，不是代码填的；其中 3 次落在 `liquidity`。
  **订正**：初稿在这里写"正面印证了三.3 的『liquidity 定义两头堵』"，这个推断经不起
  同一批样本的检验。逐条看 8 个样本的 `target`：`整体流动性收紧与边际改善` /
  `Net liquidity / margin debt` / `净流动性边际改善` / `净流动性边际改善但绝对水平中位` /
  `边际流动性改善…尚未完全传导` / `系统流动性` / `净流动性及M2` / `净流动性边际改善`
  ——**7/8 评估的是同一个方向**（净流动性边际改善是否已被定价），只有 `系统流动性`
  那一次偏向紧缩侧框法。模型并没有在两个方向之间摇摆。
  三次 `unclear` 的 rationale 也高度一致，说的是同一件事：净流动性 4 周动量转正（利好）
  被 RRP 耗尽与实际利率极端高位抵消，**对 NDX 的净影响判不出来**。这是数据层面的真实
  矛盾，`unclear` 是诚实读数，不是定义缺陷。三.3 指出的定义空间确实存在，但按本批证据
  它是罕见尾部（1/8），不是这一类高方差的主因。
- `technical_panic` 在**完全相同的 payload** 上，4 次采样里在 `not_reflected` 和
  `partially_reflected` 之间来回跳，是三.3 那个个案（同一组 QQQ/Donchian/RSI 数字、
  两种措辞强度）在受控条件下的直接复现。

原始产物：8 份 `raw.txt` 与 `summary.json`（会话临时目录，未入库；关键数值已全部
誊录在上表与本节，可按第五节方法完整重跑复现）。实测消耗：8 次调用，
单次 prompt 111831 / 112254 字符，合计输入约 89.6 万字符（约 45 万 token 量级，
与第五节事前估算一致）。

## 五、可证伪实验设计（原方案；已于 2026-07-28 按此执行，结果见四之二）

**目的**：区分"bridge 对同一输入的判断本身就有方差"（支持裁决 b）和
"某一份 payload 本身系统性更容易被读成"已反映""（如果成立，需要回头细查该 payload
具体哪个字段在起作用）。

**做法**：复用 `_compose_prompt("bridge", BridgeMemo, payload)` 真实组装路径
（`orchestrator.py:5861-5882`），分别加载两次真实 run 已经落盘的
`prompt_audit/bridge/attempt_1.payload.json`（A = `20260725_145833`，
B = `20260725_232410`）作为**固定 payload**，绕开 L1-L5 重新生成，只对 bridge 阶段
本身发起真实 LLM 调用，重复采样：

- A 组（145833 payload）× n=4
- B 组（232410 payload）× n=4
- 共 8 次真实调用，模型固定为 `deepseek-v4-flash`（与两次历史 run 一致，见
  `prompt_audit/bridge/meta.json`）

**判读标准**：
- 若 A 组样本内 `not_reflected` 计数有 0～3 的内部分散（不总是 3），且 B 组样本内也有
  分散（不总是 0），说明纯采样方差可以解释历史两次 run 的差异，裁决 (b) 成立，无需
  进一步动代码。
- 若 A 组稳定复现高 `not_reflected` 计数、B 组稳定复现 0，则说明差异是 payload 驱动
  而非采样噪声——需要回头逐字段比对两份 payload，定位到底哪个具体差异（很可能是
  3.2 提到的两个 L3 广度数值，或 3.3 提到的 layer card 措辞差异）在起系统性作用。

**预计花费（token 数为主要依据，$ 成本请按账户实际 DeepSeek 计费核实，本仓库未找到
`deepseek-v4-flash`/`deepseek-v4-pro` 的公开计价配置）**：

- 单次 bridge prompt 约 11.2 万字符（见两份 `meta.json` 的 `prompt_chars`：
  111831 / 112254），按中英文混排 JSON 的粗略换算（约 2 字符/token），
  **单次输入约 5.6 万 token**。
- 单次响应约 1.8～2.1 万字符（`attempt_1.response.raw.txt` 实测），
  **单次输出约 0.9～1.0 万 token**。
- 8 次调用合计：输入约 **44.8 万 token**，输出约 **7.6 万 token**。
- 这个量级与 HANDOFF 提到的"一次 thesis 采样约 6.7 万 prompt token"同一数量级，
  8 次 bridge 调用的输入总量约为其 6～7 倍。具体美元成本取决于账户当前的
  DeepSeek 计费费率，本次调查未在仓库配置中找到该费率，无法给出可靠的美元数字，
  建议核实后再决定是否执行。

## 六、独立发现（第一性原理审计：`unclear` 会不会被下游静默当作"无风险"）

按任务要求，无论上面的裁决是什么，都独立审计了"没有判断"是否被下游当作
"没有风险"。结论分三层：

**1. 代码填充默认值本身是保守的。** `_ensure_price_reflection_categories`
（`orchestrator.py:7272-7300`）为缺失类别补齐时，`reflected_state` 写死为
`"unclear"`（7290 行），`rationale` 写明"未被 {stage} 原生拆出；保留为待复核项，
不能当作已分析充分"（7291 行）——这不是任何"已反映"值，符合"没有判断不等于已经
反映"的第一性原理，主对话此前的核实结论成立。

**2. 报告渲染层没有把 `unclear` 静默算作"无风险"。** `vnext_reporter.py:2938-2943`
的 `state_tone` 映射：`not_reflected` → `"risk"`，`largely_reflected` → `"good"`，
`partially_reflected` 和 `unclear` 同为 `"watch"`——`unclear` 与"已反映"的"good"档
明确区分开，落在和"部分反映"同一档的中性提示色，不会被误读成"风险已排除"。
全仓搜索也没有发现任何位置对 `reflected_state` 做计数式打分（例如"统计
`not_reflected` 数量作为风险分"）——这种具体的计数逻辑目前不存在于代码中，
HANDOFF 假设的"静默降级"机制没有以这种形式出现。

**3. 但发现了一个更窄、真实存在的审计盲点，与 HANDOFF 的担忧同源。**
`run_review.py:717-770` 对 `price_reflection_map` 的复盘检查分两步：
先看"是否覆盖五类"（`missing_categories`，728-750 行），再看"覆盖了的类别是否
`rationale`/`counterevidence`/`action_implication` 齐全"（`thin_items`，
730-761 行）。但 `_ensure_price_reflection_categories` 补齐的占位条目**恒定**会
把这三个字段全部填上非空的模板文案（"降低该类别对动作升级/降级的确定性；等待下游
或人工复盘补足"等，见 `orchestrator.py:7292-7299`）——所以 `thin_items` 检查
**永远不会**把代码占位条目识别为"单薄"，`run_review.py:762-770` 会照常给出
`"Bridge price_reflection_map 已覆盖信用、利率、估值、技术恐慌、流动性五类，
并包含反证与动作含义"`这条 `pass` 结论，即使其中一两类其实从未被模型真正分析过。

区分"这类是不是代码占位"的唯一线索落在**另一条独立的 finding**里——
`run_review.py:706-716` 检查 `normalization_notes` 是否非空，如果补齐发生过，
会显示 `"Bridge 有代码归一化/兜底补全痕迹...: price_reflection_categories_added_by_code:
<类别名>"`。这条 finding 和"五类覆盖"那条 `pass` finding 是**并列但不互相引用**的
两条独立记录——复盘者如果只看"五类覆盖，pass"就以为五类都被认真分析过，是完全可能
发生的误读。这是本次审计发现的真实、独立的下游一致性缺口：不是"unclear 被算成
无风险"，而是"代码占位的 unclear 在结构完整性检查里会伪装成实质分析"。

**这一缺口在本次调查的两个 run 里都没有实际触发**（两次 bridge 都是五类原生齐全，
`normalization_notes` 里都没有 `price_reflection_categories_added_by_code`），
因此不构成本次 T27 现象的成因，但作为独立发现如实记录，供后续治理参考
（例如：`run_review.py` 的"五类覆盖" finding 未来可以直接读取
`normalization_notes` 里的 `price_reflection_categories_added_by_code` 列表，
把被代码占位的类别名从"覆盖五类"的措辞里明确减掉，而不是让两条 finding 各说各话）。

## 六之二、主对话复核补充：分位数进入 bridge 最显眼输入的路径是随机的

三.3 里以"格式差异"一句带过的 `core_facts.value` 现象，复核时做了量化，结论值得单独记一笔：

| run | layer_cards 全部 `core_facts` 条数 | 其中 `historical_percentile` 字段有值 |
|---|---|---|
| `20260725_145833` | 54 | **1** |
| `20260725_232410` | 60 | **0** |

`CoreFact` 契约（`contracts.py:674-692`）本来就为"有多极端"准备了三个结构化字段
（`historical_percentile` / `trend` / `magnitude`），但 L1-L5 分析卡几乎从不填它们；
分位数实际是被层级模型**自由裁量地写进 `value` 这个自由文本里**。两次 run 的 L1 恰好
走了相反的路：

- A（145833）：`{'metric': '10Y Real Rate', 'value': '2.43%, 10y percentile 99.6'}`，
  九条 L1 核心事实条条带分位数文字。
- B（232410）：`{'metric': '10Y Real Rate', 'value': '2.43%'}`，分位数文字**全部消失**。

后果需要如实界定，不要夸大：**这是显著性差异，不是信息丢失。** 分位数仍然通过
`context_brief.layer_highlights`（两次逐字节相同，含 10Y 实际利率 99.6 分位、
HY OAS 16.77 分位、HY 尾部利差 99.87 分位）和 `indicator_analyses` 到达 bridge——
全 payload 中 "percentile"/"分位" 出现次数 A 为 77/110、B 为 70/93，同一量级。
但极端值在最显眼位置的复述频次确实降了（"99.6" A 出现 6 次、B 只有 2 次）。

为什么值得记：`price_reflection_map` 判"某类风险还没被定价"最直接的依据就是"这个指标
有多极端"。目前这条极端性信号能否出现在 bridge 最显眼的输入里，取决于层级模型当次
写作时的随手选择，而不是由结构化字段稳定保证——这是三.3 那种"叙事采样方差能产生方向性
后果"的具体机制之一。

补充核实：`historical_percentile` 在 vNext 主链里目前**没有任何消费方**
（全仓 grep 只在 `contracts.py` 定义处和 `tools_L4.py` 的同名工具字段命中，
后者是另一套字段，不是这个契约字段）；`magnitude` 只有 `legacy_adapter.py:328-329`
一处消费。所以字段空着不会让某段代码读到 `None` 而静默出错，属于 prompt 层的显著性
问题，不是代码缺陷。是否值得让 L1-L5 强制填充结构化分位字段，是一个独立的改进议题，
不在 T27 的必需修复范围内。

## 七、交付清单核对

- [x] 现象重述（一）
- [x] 已证伪假设（二，输入瘦身未触碰 bridge）
- [x] 逐步证据，带文件/行号（三）
- [x] 机制裁决 (b) 及依据（四）
- [x] 裁决为 (b)：可证伪实验方案 + 预计花费，未执行（五）
- [x] 第五点独立发现（六）
- [x] 主对话复核补充：分位数显著性路径随机（六之二）
- [x] `RESEARCH_CANON.md` 判读说明已追加（见该文件"跨层级情景矩阵"章节之后新增小节）
