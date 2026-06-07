# Agent 原文检查器（Prompt Inspector）取代正文 Agent IO Audit 的决策文档

日期：2026-06-06  
状态：用户洞见记录 / 后续实现依据  
适用对象：后续 Codex、Claude 或其他 agent 如果要改造 Agent IO Audit、native brief、run review 或 agent prompt 可视化，应先读本文，再读 `docs/2026-05-20_AGENT_IO_AUDIT_VIEW_RESEARCH.md`、`ARCHITECTURE.md` 和 `NEXT_STEPS.md`。

---

## 0. 一句话结论

现有正文里的 `Agent IO Audit` 应从主报告中删除或默认折叠，只保留极小的健康摘要；真正有价值的能力应改为独立的 `Agent 原文检查器（Prompt Inspector）`：

> 第一优先级是让人看到每个 agent 本轮实际收到的完整原文。Canon、数据摘要、stage 指令、结构化输入渲染结果都不是额外展品，而是这份完整原文的一部分。

用户的核心洞见是：

> 只有看到 agent 真实收到的全文，才能直观判断流程是否合理、上下文是否必要且充分、后续 Bridge / Thesis / Final 有没有被污染。

当前 `Agent IO Audit` 不是这个东西。它只是把“能看到哪些定义字段、哪些 artifact 路径、哪些 evidence ref 字符串出现在下游”摊在报告里。它对维护者有一点调试价值，但对读者不直观，对判断 agent 协作是否合理也远远不够。

本文补充三条硬原则：

1. **完整原文优先。** 用户首先要看的是 agent 实际收到的完整文本，而不是字段摘要。Canon 当然可以单独辅助定位，但它首先属于完整 prompt 原文的一段。
2. **美观不能改写事实。** 页面可以做得清楚、漂亮、适合中文读者阅读，但“完整原文”区域必须保证所见即 agent 所见，不能为了排版重组、改写、删减或摘要化。
3. **中文读者优先。** 面向用户的标题、tab、状态和说明应尽量汉化；英文 stage key 和 artifact 名称可以保留为技术标识，但不应成为主要阅读语言。

---

## 1. 用户洞见原文要点

用户真正想看的不是“字段目录”，而是每个 agent 的真实视野：

- L1 的完整 prompt 真实长什么样。
- L1 到底在这段完整原文里收到了哪些数据字段。
- 这些字段的具体值是什么，例如美债收益率、真实利率、流动性指标。
- L1 收到的 Canon 全文在完整 prompt 里的哪一段。
- L1 输出了哪些字段、哪些 evidence refs、哪些反证和失效条件。
- Bridge / Thesis / Final 各自吃了哪些上游产物。
- 后续 agent 的 prompt 全文里有没有不该出现的前置结论或污染信息。

这比一张“字段可见性表”有价值得多。因为它直接回答：

> 这个 agent 到底看到了什么，又被要求怎么想？

对多 agent 投研系统来说，这是判断流程是否可信的第一手材料。

重要补充：

> Canon 不应被理解成和完整 prompt 并列的另一个对象。真正的审计对象是 agent 收到的完整文本；Canon 只是这段完整文本中非常重要的一部分。页面可以提供“规则原文”分面帮助快速定位，但不能用分面替代完整原文。

---

## 2. 现有 Agent IO Audit 的问题

### 2.1 它不是流程图

现有 `Agent IO Audit` 只是报告中的一段审计区，不是可交互流程图。它把 L1-L5、Bridge、Thesis 等 stage 的 artifact 路径、简要字段、evidence refs 和轻量检查列出来。

这能让维护者知道“某个文件存在、某个字段存在、某个 ref 字符串在下游出现过”，但不能让用户一眼看懂 agent 之间如何协作。

### 2.2 它展示的是字段轮廓，不是 agent 真实输入

现有审计区展示的是被 reporter 二次抽取后的摘要，不是模型真实收到的全文。

它不能展示：

- 完整 prompt。
- 完整 structured payload。
- 完整 prompt 中的 Canon 文本位置。
- 原始数据值如何进入 prompt。
- 每次 retry 时 prompt 是否发生变化。
- 模型原始回答和 schema 修复之间发生了什么。

因此它不能成为判断上下文污染的最终依据。

### 2.3 它的下游使用判断很弱

现有下游使用判断主要依赖 evidence ref 字符串是否出现在下游 artifact 中。这只能说明“字符串出现过”，不能说明：

- 下游是否真正理解并使用了该证据。
- 该证据是支持、反驳、折中，还是只是被复制。
- 上游字段是否改变了 Bridge / Thesis / Final 的判断。
- 某个重要反证是否被下游压扁或丢弃。

所以它最多是轻量 trace，不是语义级审计。

### 2.4 它让报告变丑，且挤占读者注意力

主报告应该服务阅读和判断。大段 `Agent IO Audit` 把内部字段、路径、状态 chip 和 artifact 摘要摊在正文里，会打断报告叙事。

严格说，现有 Audit 多数情况下不消耗本轮 LLM 调用 token，因为它是 reporter 后处理生成的 HTML。但它会消耗：

- 报告阅读注意力。
- HTML 体积。
- 后续把报告再次喂给 LLM 时的上下文 token。
- 用户对系统是否“真的直观”的信任。

因此它在正文里属于低价值噪音。

---

## 3. 当前功能有没有证明流程合理

结论：**没有充分证明。**

它只能提供有限证据：

- L1-L5 的 `layer_context_briefs/Lx.json` 看起来只包含本层 runtime highlights。
- 禁止输入检查可以初步显示其他层 runtime highlights、Bridge、Thesis、Final 是否缺席。
- L1-L5 产物、Bridge、Thesis、Final 等 artifact 是否存在。
- evidence refs 是否至少在下游 artifact 字符串中出现过。
- `llm_stage_diagnostics.json` 中每个 stage 的状态、重试次数、prompt 长度和错误摘要。

这些东西有用，但只能证明“管线大体跑通，隔离检查没有发现明显违规”。它不能证明：

- 每个 agent 的上下文必要且充分。
- prompt 本体没有埋入不该出现的信息。
- 下游 agent 正确消费了上游结论。
- 上游反证没有被压扁。
- Bridge / Thesis / Final 的结论是从 evidence chain 推出来的，而不是模型自由发挥。
- 当前 agent 分工是最合理的。

所以现有 Audit 更像验收仪表盘的早期草稿，不是最终审计产品。

---

## 4. 决策：正文中怎么处理现有 Agent IO Audit

### 4.1 主报告默认不再展示大块 Agent IO Audit

native brief 正文应删除或默认折叠当前 `Agent IO Audit` 大段内容。

推荐替代为一个很小的 `Agent Health` 摘要区，只展示：

- L1-L5 context isolation：通过 / 有风险。
- Prompt capture：已保存 / 未保存。
- Stage validation：是否有重试、失败或 schema repair。
- Prompt size：是否存在异常过大的 stage。
- Evidence trace：关键 evidence refs 是否能追到上游。
- Prompt Inspector 链接。

这部分应该是报告的审计入口，不是审计全文。

### 4.2 旧 Audit 保留为开发开关

旧 `Agent IO Audit` 可以暂时保留，但应放在开发模式或显式开关后面：

- 默认 brief 不展示。
- 需要内部排查时可打开。
- 不作为普通读者报告的一部分。
- 不继续在旧结构上堆复杂评分。

推荐命名方式：

```text
show_legacy_agent_io_audit = false
```

或：

```text
--include-legacy-agent-io-audit
```

### 4.3 不要把旧 Audit 美化成最终产品

旧 Audit 的问题不是 CSS 不够好，而是信息对象错了。

它展示的是“抽取后的字段和路径”，用户要看的是“agent 真实收到的全文”。继续美化旧 Audit，只会把一个不直观的字段目录变成更漂亮的字段目录。

---

## 5. 真正有用的 Prompt Inspector 应该是什么

### 5.1 产品定位

`Agent 原文检查器（Prompt Inspector）` 是一个独立调试 artifact，不是主报告正文。

它的目标用户是：

- 系统设计者。
- 维护 agent prompt 的人。
- 做 run review 的人。
- 想确认上下文隔离和污染风险的人。
- 想判断每层上下文是否必要且充分的人。

它不负责给最终投资结论背书。它负责让人看见 agent 的真实输入原文、真实指令原文和真实输出。

核心体验应该是：

> 我点开 L1，第一眼看到的是“L1 本轮实际收到的完整文本”。我可以美观地阅读、搜索、折叠、定位，但我知道这段文字没有被改写，和 agent 看到的是同一份东西。

### 5.2 核心问题

Prompt Inspector 必须让用户能回答：

1. 这个 stage 本轮实际收到的完整原文是什么。
2. 这段完整原文由哪些部分组成：系统指令、stage 指令、Canon、数据、上游 artifact、输出格式约束、重试反馈。
3. 它收到的数据值具体是什么，以及这些值在完整原文中的位置。
4. 它收到的 Canon 和规则原文在完整 prompt 中的哪一段。
5. 它输出了哪些结构化字段。
6. 它的哪些输出被下游使用、忽略、反驳或压缩。
7. 它是否看到了不该看的运行时上下文。
8. 如果它重试过，每次错误和修正是什么。

---

## 6. Agent 原文检查器的页面形态

推荐使用独立 HTML 或 workbench 子页面。

页面设计原则：

- **原文不变形。** “完整原文”区域从保存的 prompt 原文文件直接渲染，允许换行、折叠、高亮和搜索，但不允许改写、重排、删减或摘要化。
- **辅助视图可美化。** 数据、规则、输出、下游流向可以做成漂亮的卡片、表格或流程图，但必须明确它们是从完整原文和 artifacts 中抽取出的辅助视图。
- **中文优先。** 面向用户的主标题、tab 和状态名使用中文；英文 stage key、文件名、schema 字段作为副标题或技术标识保留。
- **可校验一致。** 页面应显示 prompt 文件路径和 hash。用户复制“完整原文”区域时，复制出的文本应与 agent 实际收到的 prompt 一致。

### 6.1 总览图

顶部先展示 pipeline 图：

```text
Data / Context
  -> L1 Macro
  -> L2 Earnings / Credit / Volatility
  -> L3 Market Structure
  -> L4 Valuation
  -> L5 Technical
  -> Bridge
  -> Thesis
  -> Critic / Risk
  -> Reviser
  -> Final
```

图上每个节点显示：

- 中文 stage 名称和英文 stage key。
- prompt chars / tokens。
- 输入 artifact 数量。
- 输出 artifact。
- 状态：通过 / 重试 / 失败。
- 边界检查：干净 / 可疑 / 违规。

### 6.2 点击节点后的详情页

每个 stage 至少有六个中文 tab，英文只作为括号里的技术辅助：

```text
总览
完整原文
输入数据
规则定位
输出结果
下游流向
```

#### 总览

展示：

- stage 中文名称和英文 key。
- 运行模式：最新 / 回测 / 快照。
- effective date。
- model。
- attempts。
- validation errors。
- prompt size。
- output artifact path。
- 数据边界摘要。

#### 完整原文

展示模型实际收到的完整 prompt 原文。

这是 Prompt Inspector 的灵魂。没有完整 prompt，就不能叫 Prompt Inspector。

要求：

- 必须是发给模型前的最终文本。
- 包含系统指令、stage 指令、Canon、structured payload 渲染结果。
- 如果有 retry，保存每次 attempt 的 prompt 或至少保存 retry feedback 如何拼接进 prompt。
- 支持搜索和复制。
- 支持高亮疑似越权内容，例如其他层 runtime 结论、Bridge 判断、Thesis 判断、Final 判断。
- 支持漂亮阅读，但漂亮只能来自样式层：字体、留白、折叠、目录、搜索、高亮、行号；不能来自改写原文。
- 显示 `prompt_sha256` 或等价 hash，帮助确认页面展示的原文和保存文件一致。

#### 输入数据

展示 prompt 拼接前的结构化输入，并尽量提供“跳转到完整原文对应位置”的锚点。

对 L1-L5，要能看到具体数据值，而不是只看字段名。例如：

```text
10Y yield: ...
real yield: ...
net liquidity proxy: ...
USD / DXY proxy: ...
rate volatility: ...
data_date: ...
source: ...
```

对 Bridge，要能看到：

- L1-L5 layer cards。
- 每层 evidence refs。
- 每层反证。
- 每层失效条件。
- 禁止输入边界。

对 Thesis / Final，要能看到：

- Bridge memo。
- synthesis packet。
- critique。
- risk boundary report。
- revised analysis。
- final adjudication 前置输入。

#### 规则定位

展示本 stage 收到的规则在完整 prompt 中的位置和摘录：

- ObjectCanon。
- 本层 IndicatorCanon。
- PermissionType 规则。
- Decision Semantics 规则。
- 回测 / snapshot 数据边界规则。
- stage 专属 prompt 规则。

注意：这个 tab 只是快速定位规则，不是替代完整原文。Canon 的最终审计依据仍是“完整原文”tab 中 agent 实际收到的那段文本。

#### 输出结果

展示模型输出：

- raw response。
- repaired response，如果发生过修复。
- validated JSON。
- schema / contract validation 结果。
- evidence refs。
- claims。
- falsifiers。
- uncertainty。
- invalidation conditions。

#### 下游流向

展示上游输出如何进入下游：

- 被哪个 stage 使用。
- 用在什么字段。
- 是支持、反驳、合并、降权，还是未使用。
- 是否在 Final 中保留。
- 是否被压缩成低价值标签。

第一版可以先做证据级 trace，后续再升级为语义级 trace。

---

## 7. 需要新增的 artifact 合约

当前系统只保存 `prompt_chars`，不足以支持 Prompt Inspector。必须新增 prompt capture。

建议每个 run 增加目录：

```text
prompt_audit/
  L1/
    attempt_1.prompt.txt
    attempt_1.payload.json
    attempt_1.response.raw.txt
    output.validated.json
    meta.json
  L2/
  L3/
  L4/
  L5/
  bridge/
  thesis/
  critic/
  risk/
  reviser/
  final/
```

`attempt_1.prompt.txt` 是事实源，必须保存 agent 实际收到的完整 prompt 原文。页面可以把它渲染得好看，但不能用另一个被改写过的 markdown 文件替代它。

每个 `meta.json` 至少包含：

```json
{
  "stage": "L1",
  "attempt": 1,
  "model": "...",
  "status": "ok",
  "prompt_chars": 32361,
  "prompt_tokens_estimate": null,
  "prompt_sha256": "...",
  "prompt_file": "prompt_audit/L1/attempt_1.prompt.txt",
  "effective_date": "2026-06-05",
  "mode": "latest",
  "input_artifacts": [],
  "output_artifact": "layer_cards/L1.json",
  "validation_errors": [],
  "data_boundary": {
    "effective_date": "...",
    "max_input_date": "...",
    "backtest_cutoff_respected": true
  }
}
```

对隐私和体积的处理：

- 默认保存本地 artifact，不上传。
- 可以提供清理开关。
- 可以对超大 prompt 做折叠展示，但文件里必须保留全文。
- 如果未来引入敏感凭证、cookie、浏览器登录态材料，必须先做 redaction，不能原样写入。

对展示一致性的要求：

- `完整原文` tab 必须从 `attempt_N.prompt.txt` 读取。
- 页面显示的 hash 应和文件 hash 一致。
- “复制完整原文”按钮复制出的内容应和文件内容一致。
- 任何高亮、折叠、目录、中文辅助标题都只能作为 overlay，不得插入到原文文本中。

---

## 8. 污染检查应该如何做

Prompt Inspector 应把污染检查做成“可见证据”，不是只给一句通过。

### 8.1 L1-L5 禁止项

L1-L5 的完整 prompt 中不应出现：

- 其他层本轮 runtime highlights。
- 其他层本轮 layer card 输出。
- Bridge 当前 memo。
- Thesis 当前判断。
- Final 当前判断。
- 全局 apparent cross-layer signals。
- 新闻 sidecar 中未升级为正式证据的材料。
- 回测日之后的数据、新闻、图表行或网页材料。

### 8.2 Bridge / Thesis 允许项

Bridge 可以看：

- L1-L5 产物。
- evidence refs。
- layer-level falsifiers。
- layer-level uncertainty。
- 静态 Canon。

Bridge 不应看：

- Thesis / Final 当前判断。
- 人工事后解释。
- 回测日之后材料。

Thesis 可以看：

- Bridge / synthesis packet。
- objective firewall summary。
- 允许的上游 artifacts。

Thesis 不应看：

- Final 当前判断。
- 回测日之后材料。
- 未标注为正式证据的浏览器或新闻候选材料。

### 8.3 检查结果展示

每个节点都应显示：

```text
边界检查：干净 / 可疑 / 违规
```

并列出证据：

- 命中的文本片段。
- 所在 prompt 文件。
- 规则名称。
- 严重程度。

这样用户不用相信系统自称“隔离”，而是能看到隔离检查依据。

---

## 9. 实施路线

### Phase 1：正文减负

目标：先把报告从旧 Audit 噪音里解放出来。

改动：

- native brief 默认不展示大块 `Agent IO Audit`。
- 新增小型 `Agent Health` 摘要。
- 旧 Audit 放到显式开发开关后。
- brief 文案明确：完整 prompt 审计见独立 `Agent 原文检查器`。

完成标准：

- 默认 brief 不再出现大段 legacy Audit。
- brief 仍能看到 isolation / retry / prompt size / validation 的摘要。
- 测试确认旧 Audit 不会默认污染主报告正文。

### Phase 2：保存真实 prompt

目标：让系统拥有 Prompt Inspector 的事实基础。

改动：

- 在 orchestrator 生成 prompt 后、调用 LLM 前，保存完整 prompt。
- 保存 structured payload。
- 保存 raw response、修复后 response、validated output。
- `llm_stage_diagnostics.json` 增加 prompt audit 文件路径。
- 为 prompt 原文保存 hash，保证页面展示和 agent 所见文本可校验一致。

完成标准：

- 每个 LLM stage 都有 prompt audit 文件。
- retry attempt 有独立记录。
- 回测模式 prompt audit 中没有回测日之后数据。
- prompt audit 文件路径能从 run summary 或 diagnostics 找到。

### Phase 3：生成 Agent 原文检查器页面

目标：让用户真正直观看到 agent 协作。

改动：

- 新增独立 HTML：`prompt_inspector_<run_id>.html`。
- 左侧 pipeline 图，右侧 stage 详情。
- 支持中文 tab：总览 / 完整原文 / 输入数据 / 规则定位 / 输出结果 / 下游流向。
- 支持搜索。
- 支持污染检查结果高亮。
- UI 可以美观，但完整原文必须和 agent 实际收到的文本一模一样。

完成标准：

- 用户点击 L1 能看到 L1 完整 prompt、输入值、Canon、输出。
- 用户在“完整原文”中看到的文本，和 agent 实际收到的 prompt 文件 hash 一致。
- 用户点击 Bridge 能看到它吃了哪些 L1-L5 artifact。
- 用户点击 Thesis / Final 能看到上游输入是否合理。
- 页面能直接暴露越权输入、prompt 过大、retry、schema error。

### Phase 4：语义级下游追踪

目标：从“字符串出现”升级到“证据如何改变结论”。

改动：

- 对 claims / evidence refs / falsifiers 建立 typed trace。
- 标记支持、反驳、合并、降权、丢弃。
- 展示上游重要字段是否进入 Final。
- 对未使用的重要反证打 warning。

完成标准：

- Final 的核心结论能追溯到上游 claims 和 evidence refs。
- 重要反证若被丢弃，页面能显示在哪一步丢弃。
- 下游强结论如果追不到上游证据，页面能提示风险。

---

## 10. 验收标准

Prompt Inspector 第一版完成后，用户应能做以下检查：

1. 打开某个 run，点击 L1，首先看到 L1 实际收到的完整 prompt 原文。
2. 确认 L1 prompt 中没有 L2-L5 本轮结论、Bridge、Thesis 或 Final。
3. 在同一份完整原文中定位 Canon、数据值、输出格式约束和回测边界，而不是只看分离后的摘要。
4. 点击 L4，看到估值数据、Damodaran ERP、NDX PE/PB/Forward PE 等字段如何进入 prompt，并确认两类分位没有混写。
5. 确认页面显示的 prompt hash 与保存的 prompt 文件一致，保证“我看到的”和 agent 看到的是同一份文本。
6. 点击 Bridge，看到它只吃 L1-L5 产物，而不是偷看 Thesis / Final。
7. 点击 Thesis，看到它基于 Bridge / synthesis，而不是回头读取不该读的材料。
8. 点击 Final，看到最终判断如何继承、修正或拒绝上游结论。
9. 如果某 stage 有 retry，看到失败原因、修复提示和下一次 attempt。
10. 如果 prompt 过大，看到是哪类材料导致膨胀。
11. 如果回测运行，看到所有 prompt 的数据边界都不晚于回测日。

---

## 11. 非目标

Prompt Inspector 第一版不需要：

- 自动判断每个 agent 是否聪明。
- 给每个字段打复杂质量分。
- 用语义相似度替代人工判断。
- 作为发布闸门。
- 替代 run review。
- 替代 native brief。

它第一版最重要的任务只有一个：

> 把 agent 真实看到的完整文本摊开，并在不改写原文的前提下做得足够清楚、漂亮、可搜索、可定位，让污染、冗余、缺口和误用变得一眼可见。

---

## 12. 对现有 Agent IO Audit 的最终评价

现有 `Agent IO Audit` 是一次有价值的原型，但它成功证明的不是“这个方向已经做对了”，而是：

> 只展示字段摘要和 artifact 路径，不足以让人理解 agent 协作。

它暴露了真正需求：

- 不要只看字段名，要看字段值。
- 不要只看摘要，要看 agent 实际收到的完整 prompt 原文。
- 不要把 Canon 当成另一个孤立模块，Canon 应该首先作为完整 prompt 原文的一部分被看到。
- 不要只看“是否有 ref”，要看 ref 如何改变下游判断。
- 不要把内部审计硬塞进读者报告，要把审计做成独立、可点击、可追溯、中文友好的原文检查器。

这就是本次洞见的价值。
