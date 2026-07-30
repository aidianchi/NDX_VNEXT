# 交接：严格模式扩围之后的四条待办（2026-07-30）

> **读这份文件的顺序**：先读本文件"必读的三条教训"，再读 `现在.md` 拿当前状态，需要历史细节时才翻 `WORK_LOG.md` 的 2026-07-29 / 07-30 两天。
>
> 本文件**不声明事项状态**——状态唯一权威是 `现在.md`。这里只记调查结论、踩过的坑和可执行线索。

---

## 一、必读的三条教训（不读会重复踩）

### 1. 不要要求模型"逐字复制字符串"——2026-07-30 三处同时失败

这一天做了三处改造，都基于同一个假设：**告诉模型"把 X 原样抄进某字段"，它就会照抄**。真实 run `20260730_114704` 里三处全部失败：

| 改造 | 要求 | 模型实际给的 | 现状 |
|---|---|---|---|
| `EventInterpretationCard.attribution_quote` | 必须是 `interpretation` 首句的原文片段 | 语义正确但字面不同 | **已随规则删除** |
| `EventSectionSummary.citation_caveats[].quote` | 必须是 `summary_text` 原文且落在该引用所在句 | 同上，两次尝试用尽 → 整站 failed | **已随规则删除** |
| `Conflict.conflict_id` | 必须原样沿用 bridge 的 `conflict_id` | `TC1_restrictive_macro_vs_moderate_valuation` → `C1_…`（后缀一字不差、前缀自行改写） | **仍在，T34 待修** |

**这不是模型能力差，是机制选错了。** 模型会概括、缩写、换说法、重新编号——这是它的默认行为，不是偶发失误。

前两行的字段已经不存在了（连同它们要服务的规则一起删掉，见教训 4）；留着这张表是因为**教训本身仍然有效**，而 `conflict_id` 就是它还没被修掉的那个活例子。

**修正后的判据（重要）**：

> 结构化槽位之所以能让闸门"不判意思"，是因为**槽位内容可以拿去和"不是散文的东西"核对**。
> `evidence_refs` 能对证据册、`conflict_id` 能对 bridge 清单——这叫身份比对。
> 让模型把一段散文摘进槽位、再要求它和另一段散文逐字相符——**那叫听写，不叫身份比对**。

有效的做法不是"让它抄"，而是**"让它选"**：把候选值写成严格模式 schema 里的 `enum`，模型物理上打不出清单外的值。这是 T34 的核心。

### 2. 严格模式是概率性保证，不是铁保证

`llm_engine.py` 里 `tool_choice="auto"`。这不是随手写的——**思考模式下 DeepSeek 拒绝 `required` 和具名 function**（两者都已用真实 API 探针复现，见下表）。

`auto` 意味着**模型可以选择不调用工具、直接返回普通文本**，此时 `strict: True` 的 schema 约束**完全失效**，退回老失败模式。本跑实测到一次：某事件卡返回带 markdown 围栏的文本，里面有未转义双引号，`parse_error`。

**所以：严格模式后面的校验器和闸门必须保留，不能因为"有严格模式了"就撤掉。**

### 3. 报告某节留空，先分清是闸门尽职还是模型被卡死

`event_section_summary` 连挂五跑。前四次是引用编号的 `event:` 前缀陷阱（模型删前缀→正文与清单不一致→按反馈两边都删前缀→又落到 allowed_ids 之外，两条规则互相卡死），第五次是词表误判，第六次是上面第 1 条的听写失败。

`CLAUDE.md` 的"常见误判"原本写着"报告某节留空 = 宁缺毋滥闸门在工作"，已因此改写。**看到空白先查 `llm_stage_diagnostics.json` 里该站的失败原因；连续多跑同样失败就是模型被卡死，不是闸门尽职。**

### 4. 闸门该管什么、不该管什么——2026-07-30 已按实测裁决

把最近四次真实 run 的 28 条重试/失败按"约束了什么"分类：

| 拦的是什么 | 条数 | 裁决 |
|---|---|---|
| **形状**（能不能被机器读） | 4 (14%) | 硬约束，正确。严格模式强化它 |
| **出处**（数字与引用能不能被追溯） | 7 (25%) | 硬约束，最重要的一条 |
| **完整性**（该交代的有没有交代） | 3 (11%) | 该约束，但只约束"必须回应/必须交代"，**不要约束"必须产出 N 条"** |
| **措辞**（必须用哪个词、怎么开头） | **14 (50%)** | **已全部删除** |

分界线：**好的约束限制"你必须交代什么"，不限制"你必须怎么说"。** 前者让模型无处藏拙，后者让模型无法思考。

措辞类之所以能删干净，是因为它们**多余**——想保护的"读者别把仅标题的弱来源当确凿事实"，报告本来就由代码渲染：`「Yahoo Finance M7 Headlines · 可靠媒体转述 · 仅标题与片段 · 降级阅读」`（`vnext_reporter.py` 的 `event_row`，取自 `source_tier` 与 `raw_text_excerpt`）。代码版本比"靠模型记得写某个词"更强，一条不漏。

**这个保证由 `tests/test_wo_r1_reporter.py::test_weak_source_labelling_is_code_driven_not_model_worded` 钉住。删了闸门就只剩这一道——动渲染前先看它。**

保留的是**禁止型**规则（`_HINDSIGHT_OR_CAUSAL_PATTERNS`、方向越权词表）：代码渲染替代不了（标不出"这句是不是事后诸葛"），且实测 0 触发、成本为零。**不要因为"也是判意思"就顺手删掉它们。**

---

## 二、真实 API 探针结论（不是文档推断，是实调）

端点 `/beta`，模型 `deepseek-v4-flash`，`extra_body={"thinking":{"type":"enabled"}}` + `reasoning_effort="high"`：

| 试的是什么 | 结果 |
|---|---|
| `tool_choice="required"` | ❌ 400 `Thinking mode does not support this tool_choice` |
| `tool_choice="auto"` | ✅ 正常，模型确实会走工具通道 |
| `required` 只列真正必填的字段 | ❌ 400 `Required properties must match all properties in the object` |
| `required` 覆盖全部字段 | ✅ |
| `{"anyOf":[{"type":"array","items":…},{"type":"null"}]}` | ✅ 模型实测返回 `"b": null` |
| `type: ["array","null"]` | ❌ 400 `unknown variant 'array', expected one of string, number, integer, boolean, null` |

**由此推出的关键结论**：`required` 全覆盖不可避，但**可空性决定实际压力**。
- 允许 null 的字段 → 模型可以诚实交白卷，无压力。
- 只能是数组的字段（`List[X]` 带 `default_factory=list`，转严格 schema 后无 null 分支）→ **模型必须填非空数组**，这才是"配额压力"的真正来源。

---

## 三、待办（状态见 `现在.md`，这里只给可执行线索）

> **本节不是完整待办清单。** 只写与本次严格模式工作直接相关的几条。台账里还有 T04 / T06 / T09 / T10 / T16 五条更早的积压项，与本文件无关，**去 `现在.md` 看全量**。

### T34｜严格 schema 的两项后处理 —— 优先做，全免费

**① 冲突编号改"选单"**
`ThesisDraft.retained_conflicts[].conflict_id` 目前是自由 `str`。改法：在 `_strict_tool_schema_for_stage` 返回之后，对 thesis 的 schema 做一次后处理，把该字段的取值域限定为**本轮 bridge 的 `typed_conflicts[].conflict_id` ∪ null** 的 `enum`。

- thesis 已在 `_STRICT_TOOL_CALLING_ELIGIBLE_STAGES` 白名单内，前提具备。
- 严格模式是概率性保证（见教训 2），所以 `_run_schema_guard` 里那条后置闸门**必须保留**。
- 注意 schema 需按 run 动态构造，不能再用纯静态的 `model_json_schema()`。

**② 可选容器字段可空**
`llm_engine.py:91` 把全部属性塞进 `required`（provider 强制，改不了）。但可以把**非必填**的容器字段改写成 `{"anyOf":[{原 array schema},{"type":"null"}]}`，模型就重新有了"这次真没有第三条共振链"的表达权。

- **只改发往 API 的 schema，不动 `contracts.py`**。pydantic 收到 `null` 会走 `default_factory=list`，下游逻辑一行不用改。
- **必须避开的雷**：现 `fix_anyof`（`llm_engine.py:125-129`）会把 `Optional[List[...]]` 塌缩成 `type: ["array","null"]`，该形式被 DeepSeek 拒。需把 `"array"` / `"object"` 排除出 `primitive_types`。
- 全仓当前 0 命中（现有列表字段均非 Optional），属**潜伏**风险。

**③ 补一条闸门**
在 `tests/test_governance_input.py` 的严格 schema 测试里加断言：sanitized schema 中任何 `type` 数组不得含 `string/number/integer/boolean/null` 以外的变体。

**④ 改完跑一次真实 run —— 这一跑就是"分辨实验"**
观察 `resonance_chains` / `transmission_paths` 条数：
- 回落到非严格基线带（1-2 / 2-3）⇒ 此前"严格模式让产出变厚"含配额凑数成分。
- 维持 3 / 4 ⇒ 支持"数据本就支持，只是非严格模式下被省略"。

**这比派人读文本更能分辨**，因为它不依赖单个评读者的主观判断。

> **【关单记录 T34｜2026-07-31】** 四项全部完成并经真实 run `20260731_002156` 验收，详见 `WORK_LOG.md` 2026-07-31。
>
> 三条留给后来者的更正，**本文件上文的表述据此作废**：
> 1. 上文 ② 写"pydantic 收到 `null` 会走 `default_factory=list`，下游逻辑一行不用改"——**这句是错的**，已实测证伪：`default_factory` 只在字段缺失时生效，显式 `null` 直接 `list_type` ValidationError。② 必须配一个 `null→[]` 归一化才成立，判据须与 schema 侧同一集合（`is_required()` 为 False 且注解为非 Optional list）。
> 2. 上文 ① 写"限定为本轮 bridge 的 `typed_conflicts[].conflict_id`"——实现取的是 `synthesis_packet` 里模型**真看得见**的全部编号，含 bridge 的 `conflicts` 与 `typed_conflicts` 两条通道。核对产出时只比对 `typed_conflicts` 会误判成"模型自造编号"（我核对时踩过一次）。
> 3. 上文 ④ 的分辨实验判据"条数不掉就是真货"**不够严谨**：三次跑条数一致本身不构成证据（推理方向问题，2026-07-30 已犯过一次）。真正成立的判据是**同一跑内配额压力确实被卸掉**——本跑确认那四个字段在 schema 里可空，且兄弟站点 `event_card_interpreter` 真的返回了 `null`，而 bridge 在有权说"没有"时仍填满 3/4。
>
> 另：教训 2（严格模式是概率性保证）在本跑再次被实测到，`event_section_summary` 第七次连挂，病因已变为"走文本通道 + 未转义半角双引号"，已立 T36。

### T35｜桥接引用了一个不存在的证据编号

`schema_guard` 报 `BridgeMemo[0].typed_conflicts[TC1_…].evidence_refs invalid: L4.get_damodaran_us_implied_erp#erp_t12m_adjusted_payout`。

需查清是**子引用命名空间与工具真实字段名对不上**（与台账 T20 同类病）还是该指标本轮确实缺失。入口：`_run_schema_guard` 的 ref 校验、`src/tools_L4.py` 里该函数的 `MetricAuthority` 登记。

### ~~T33~~｜已于 2026-07-30 结案，不要重开

用户裁决："这类规则本来就可以删。"三条措辞闸门已删除，保证移交报告渲染（见教训 4）。禁止型规则保留。**不要因为看到 `_HINDSIGHT_OR_CAUSAL_PATTERNS` 还在就以为这条没做完。**

> **【关单记录 T35｜2026-07-31】** 已结案，答案是"命名空间错位"，不是指标缺失——该字段本轮 `availability=available`、`source_tier=official`、值 4.3。用户批准方案 A：合法性改判真实字段名（纯身份），权限分级保持只由 `MetricAuthority` 决定。合法 ref 104→459 条、零丢失，全量 1040 passed。详见 `WORK_LOG.md` 2026-07-31。
>
> **上文"与台账 T20 同类病"这句要补一句**：同源没错，但**一次并没有修掉两条**。T35 修的是 `_run_schema_guard` 那道闸门（bridge 段）；thesis / final / reviser 三站走的是 `_validate_stage_evidence_refs`，白名单来自 `synthesis_packet.evidence_index`，那里的 `#field` 条目仍只由登记表构造。T20 剩下的一半是独立决定，见 `现在.md`。

### T20｜台账旧项，与 T35 同源

`MetricAuthority` 条目名用的是概念分组名而非工具真实字段名，导致底层数据完好也被判"证据缺失"。已复现具体后果，见 `investigation_reports/20260728_single_source_audit/FINDINGS.md`。

---

## 四、当前代码状态

- 最近提交：`1f1f697`（删除三条措辞闸门）。全量 `pytest --cache-clear -q` **1024 passed**。
- `_STRICT_TOOL_CALLING_ELIGIBLE_STAGES = {bridge, thesis, event_card_interpreter, event_section_summary}`，四处 `_run_stage` 调用点均已接线。`critic` / `final` 仍在白名单外（`FinalAdjudication` 有 3 处自由形态 object，开了会被拒）。
- 严格模式**默认不启用**，需环境变量逐个点名：`NDX_STRICT_TOOL_CALLING_STAGES=...`。
- 最近一次真实 run：`output/analysis/vnext/20260730_114704`，`publish_quality_status=review_required`，**不可作为发布结论**。

## 五、验证命令

```bash
# 全量
.venv/bin/python -m pytest --cache-clear -q
# 文档纪律（改 现在.md / WORK_LOG 必跑）
.venv/bin/python -m pytest tests/test_docs_consistency.py -q
# 严格 schema 离线体检
.venv/bin/python -m pytest tests/test_governance_input.py -q -k strict_tool_schema
# 真实跑（花钱）
NDX_STRICT_TOOL_CALLING_STAGES=bridge,thesis,event_card_interpreter,event_section_summary \
  .venv/bin/python src/console_run_all.py --models deepseek-v4-flash,deepseek-v4-pro \
  --enable-news --skip-legacy-report
```

## 六、协作提醒

- 用户**不读技术细节**，只读 `现在.md` 与 `人话进度报告.md`。回复必须按 `CLAUDE.md` 的"人话版写法"：一句话先答、先搭心智模型、按事情发生顺序讲、**判断失误单列一节**、结尾给"只记这几句"。
- 用户对"不优雅"的容忍度低，且**多次凭直觉指出过我的错误结论**（"是不是本来就说不准"、"变厚就是变好吗"）。他的怀疑值得当证据对待，不要急着辩护。
- 本次会话我犯的错，已在 `WORK_LOG.md` 2026-07-30 条目里自陈：把"两次跑条数一致"当成反凑数证据（推理方向反了）、把模型自编编号判为"无害"（后来咬人了）、用 `&&` 接管道导致带红提交。
