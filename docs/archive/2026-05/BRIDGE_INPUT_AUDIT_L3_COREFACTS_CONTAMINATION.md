# Bridge 输入污染审计报告：L3 core_facts 字符串拆分缺陷

> **文档类型**：上游数据管道缺陷审计
> **严重程度**：中高（直接导致 Bridge 层约 25% 输入 token 为无意义噪声）
> **责任模块**：`src/agent_analysis/orchestrator.py` → `_normalize_payload`
> **发现时间**：2026-05-10
> **关联运行**：`20260510_225944`

---

## 1. 问题摘要

L3 LayerCard 的 `core_facts` 字段存在结构性污染：LLM 返回的一段完整中文分析文本（约 200 字）被错误地按字符拆分成了 169 个独立的 `CoreFact` 对象。这些单字符垃圾条目占用了 Bridge 约 5,500+ tokens 的上下文窗口，直接稀释了模型对真正跨层冲突的注意力。

**这不是 Bridge 层的设计问题，而是上游 `_normalize_payload` 对字符串类型输入的处理缺陷。**

---

## 2. 发现路径

1. 用户质疑 Bridge 层任务运行时间过长，怀疑输入量过高导致注意力涣散。
2. 对 `output/analysis/vnext/20260510_225944/layer_cards/` 下五层输出进行逐层体积分析。
3. 发现 L3.json（28,910 字符）显著偏离其他层（L1: 12K, L2: 12K, L4: 8.6K, L5: 14K）。
4. 逐字段拆解后发现 `core_facts` 占 19,266 字符，但 `indicator_analyses` 仅占 7,081 字符。
5. 检查 `core_facts` 内容后发现异常：169 个条目中大量为单字符（`metric="比"`, `value="率"`）。
6. 按字符顺序拼接后还原出一段完整、语义通顺的中文段落，证实为字符串被逐字符迭代所致。
7. 逆向追踪至 `orchestrator.py:_normalize_payload` 第 1231-1235 行，确认为代码逻辑缺陷。

---

## 3. 现象证据

### 3.1 文件位置

```
output/analysis/vnext/20260510_225944/layer_cards/L3.json
```

### 3.2 core_facts 条目统计

| 指标 | 数值 |
|------|------|
| core_facts 总数 | 169 |
| 单字符垃圾条目 | 164 |
| 有效结构化条目 | ~5 |
| core_facts 总字符数 | 19,266 |
| L3.json 总字符数 | 28,910 |

### 3.3 垃圾条目样例（前 20 个）

```json
{"metric": "Q", "value": "Q", "historical_percentile": null, ...}
{"metric": "/", "value": "/", "historical_percentile": null, ...}
{"metric": "Q", "value": "Q", "historical_percentile": null, ...}
{"metric": "比", "value": "比", "historical_percentile": null, ...}
{"metric": "率", "value": "率", "historical_percentile": null, ...}
{"metric": "触", "value": "触", "historical_percentile": null, ...}
{"metric": "及", "value": "及", "historical_percentile": null, ...}
{"metric": "历", "value": "历", "historical_percentile": null, ...}
{"metric": "史", "value": "史", "historical_percentile": null, ...}
{"metric": "极", "value": "极", "historical_percentile": null, ...}
{"metric": "值", "value": "值", "historical_percentile": null, ...}
{"metric": "(", "value": "(", "historical_percentile": null, ...}
{"metric": "4", "value": "4", "historical_percentile": null, ...}
{"metric": ".", "value": ".", "historical_percentile": null, ...}
{"metric": "9", "value": "9", "historical_percentile": null, ...}
```

### 3.4 拼接还原结果

将 169 个 `metric` 字段按列表顺序拼接，得到原始文本（前 200 字符）：

> `QQQ/QQEW比率触及历史极值(4.90, 99.9%分位)，Top10权重47.25%，M7占比39.63%；腾落线趋势上升但最新日涨跌持平；成分股均线以上比例约55-57%；52周新高仅15只(14.85%)；McClellan振荡器微正(0.39)；M7基本面整体强劲(加权ROE 66.4%，PE 34.3)，但特斯拉显著薄弱。`

---

## 4. 根因定位

### 4.1 缺陷代码位置

```
src/agent_analysis/orchestrator.py
方法：_normalize_payload(self, stage_key: str, payload: Dict[str, Any])
行号：1231-1235
```

### 4.2 当前实现

```python
normalized_core_facts = []
for fact in normalized.get("core_facts", []) or []:
    if not isinstance(fact, dict):
        text = str(fact)
        normalized_core_facts.append({"metric": text[:80] or "core_fact", "value": text})
        continue
    # ... 后续 dict 处理
```

### 4.3 触发条件

当 LLM 返回的 `core_facts` 字段为**字符串**（而非列表）时：

```python
normalized["core_facts"] = "QQQ/QQEW比率触及历史极值(...)"
```

Python 中 `for fact in "QQQ/QQEW...":` 会**按字符迭代**，导致每个字符都被视为一个 `fact`，触发 `not isinstance(fact, dict)` 分支，生成独立的单字符 core_fact。

### 4.4 为什么其他层没触发

其他层（L1/L2/L4/L5）的 LLM 输出中，`core_facts` 碰巧返回了正确的列表格式，因此未触发该缺陷。L3 的某次返回中该字段为字符串，触发了拆分。

---

## 5. 影响评估

### 5.1 对 Bridge 层的直接影响

| 维度 | 影响 |
|------|------|
| 输入 token 污染 | L3 core_facts 约 19K 字符 ≈ 5,500 tokens 中，有效信息仅占约 1.5%（300 tokens），其余为噪声 |
| Bridge 总输入膨胀 | 五层 layer_cards 从应有的 ~55K 字符膨胀到 ~75K 字符，增幅约 36% |
| 注意力稀释 | Bridge prompt 要求模型在 169 个 core_facts 中识别跨层关系，其中 164 个为无意义单字符 |
| 冲突识别风险 | 模型可能因噪声过载而忽略真正重要的 L3 内部冲突或跨层 hooks |

### 5.2 对下游模块的传导

- **SynthesisPacket**：`evidence_index` 会索引这些垃圾条目，进一步污染 Thesis、Critic、Risk 等治理阶段的输入。
- **Schema Guard**：若 Schema Guard 检查 core_facts 的结构性，169 个条目中的大量 null 字段可能触发误报。
- **vNext UI**：`brief` 模板若展示 core_facts，会渲染出无意义的单字符列表，破坏阅读体验。

### 5.3 为什么现在必须处理

该缺陷具有**非确定性**：它取决于 LLM 返回 `core_facts` 时的格式是否恰好为字符串。当前 L3 触发了一次，未来任何层在任何运行中都可能触发，导致 Bridge 输入质量不可控。

---

## 6. 修复建议

### 6.1 方案 A：在 `_normalize_payload` 中增加字符串兜底（推荐）

在遍历 `core_facts` 之前，先检测其类型：

```python
raw_core_facts = normalized.get("core_facts", []) or []

# 新增：如果 LLM 返回的是字符串，将其包装为单元素列表
if isinstance(raw_core_facts, str):
    raw_core_facts = [raw_core_facts]

normalized_core_facts = []
for fact in raw_core_facts:
    if not isinstance(fact, dict):
        text = str(fact)
        normalized_core_facts.append({"metric": text[:80] or "core_fact", "value": text})
        continue
    # ... 原有逻辑不变
```

### 6.2 方案 B：在 prompt 层面强制格式

在 `l3_analyst.md` 中加强 `core_facts` 的输出格式约束，明确要求：

```
core_facts 必须是对象列表，每个对象包含 metric、value、historical_percentile 等字段。
严禁将 core_facts 输出为纯文本字符串。
```

**注意**：方案 B 作为辅助手段，不能完全替代方案 A，因为 LLM 的格式遵循率并非 100%。

### 6.3 方案 C：在合约校验层拦截

在 `contracts.py` 或 `_normalize_payload` 之后增加校验：

```python
# 若 core_facts 中超过 50% 的条目字符长度 <= 1，视为异常，触发重试或告警
```

---

## 7. 验证方法

修复完成后，应按以下步骤验证：

1. **复现运行**：使用相同输入（`--data-json output/data/data_collected_v9_live.json`）重新运行一次。
2. **检查 L3.json**：`core_facts` 条目数应从 169 降至合理范围（<10），`L3.json` 总字符数应从 29K 降至 <12K。
3. **检查 Bridge 输入**：观察 Bridge 阶段的 token 使用日志，prompt_tokens 应下降约 5,000-6,000。
4. **质量对比**：对比修复前后 Bridge 输出的 `typed_conflicts` 数量、`severity=high` 冲突的识别完整性。
5. **回归测试**：运行 `python -m pytest -q` 确保没有破坏现有测试。

---

## 8. 相关文件索引

| 文件 | 作用 |
|------|------|
| `src/agent_analysis/orchestrator.py:1231-1242` | 缺陷代码位置 |
| `src/agent_analysis/prompts/l3_analyst.md` | 可在 prompt 中增加格式约束 |
| `src/agent_analysis/contracts.py:328` | `CoreFact` 合约定义 |
| `output/analysis/vnext/20260510_225944/layer_cards/L3.json` | 污染样本 |
| `output/logs/control_service/20260510_225942_913.log` | 本次运行的完整日志 |

---

*本报告由审计 Agent 生成，供修复 Agent 核实并执行。请勿在未确认根因的情况下直接修改其他层逻辑。*
