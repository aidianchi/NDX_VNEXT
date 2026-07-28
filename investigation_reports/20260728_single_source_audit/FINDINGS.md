# 单一事实源全仓审计（2026-07-28）

> 目标：把"同一件事实分两处各存一份、没人负责对账"这一类结构性缺陷穷举出来。
> 触发背景：同一天内该模式连续制造三次真实代价——`claim_ledger` 说明书零覆盖打崩终审、
> `confirming_indicators` 未写进说明书让 bridge 白重试一次、报告层假说过滤倒置让读者
> 看到"本轮没有结构化竞争假说"。
> 本文件只讲结论与证据，不声明现状（现状以 `现在.md` 为准）。

## 一、已修（含红灯测试）

### 1. `usage_rank` 漏收 `validation_only` —— 唯一一条"活跃 bug"

`_field_authority_from_payload`（`orchestrator.py`）里的 `usage_rank` **既当排序表又当白名单**，
而 36 行之后的 `_field_authority_usages` 另写了一份 `allowed` 集合。两份已经漂移：
`usage_rank` 缺 `validation_only`（"经第三方交叉校验的值"），`allowed` 有。

后果实测复现（直接调真实函数，不经 run）：

```
输入 {"usage": "validation_only"} → 输出 {"usage": "audit_only"}
```

`tools_L4.py` 有 6 处真实产出 `usage="validation_only"`（Wind PE 与 Yahoo 交叉校验等）。
下游 `packet_builder.py:796,831`、`vnext_reporter.py:4331` 都把 `validation_only` 与
`core_allowed` 同等对待，`orchestrator._downgrade_reason_for_claim` 则把它归入弱证据集合
——标签被改写后，报告里解释"这条证据为什么被降级"的审计文案与工具本意对不上，
直接戳中北极星的"可审计推理链"。

**当时没有翻转 verified/downgraded 判定，是因为 `audit_only` 与 `validation_only` 恰好
落在同一档弱证据集合里——侥幸，不是设计保证。**

既有两条测试（`test_vnext_orchestrator.py` 的 claim_gate 系列）手工构造 passport
**绕过了** `_field_authority_from_payload`，所以一直显示通过，其实没保护真实路径。

**修法**：合并为唯一常量 `METRIC_AUTHORITY_USAGE_RANK`，白名单由其键派生
（`allowed = set(METRIC_AUTHORITY_USAGE_RANK)`）。`validation_only` 与 `audit_only` 同档，
与既有弱证据口径一致，因此本次修复**只恢复标签真实性，不改变任何既有强弱判定**。
红灯测试 `test_metric_authority_usage_vocabulary_has_exactly_one_source`：删掉
`validation_only` 一行即报 `assert 'audit_only' == 'validation_only'`。

### 2. 五类价格反映名单两处硬编码

`orchestrator.PRICE_REFLECTION_CATEGORIES`（富字典，含 target/label/hint）与
`run_review.REQUIRED_PRICE_REFLECTION_CATEGORIES`（裸集合）各存一份。当时内容一致，
但没有任何机制保证它们一起变——改一处漏一处，复盘检查会开始要求或放过错误的类别，
且不报错。

依赖方向核实：`orchestrator` 顶层 import `run_review`，反向不成立；`contracts.py`
被双方引用且不依赖任何一方，是唯一不造成循环导入的落点。

**修法**：`contracts.PRICE_REFLECTION_CATEGORY_KEYS` 立为唯一名单，`run_review` 派生，
`orchestrator` 富字典由测试强制键一致。红灯测试
`test_price_reflection_category_list_has_exactly_one_source`（含"每类必须写全
target/label/hint"，防止代码补齐时拼出空文案）。

## 二、已核实、需用户决定（未动手）

### 3. MetricAuthority 条目名 vs 工具真实字段名（台账 T20）

抽查 `tools_L4.py` 全部 7 处 MetricAuthority 构造点：**5 处 key 就是真实字段名**；
**2 处是概念分组名**——`get_m7_buyback_flow`（`actual_buyback_spending` /
`m7_aggregate_and_yoy`）与 `get_m7_capex_cycle`（`companies_sec_xbrl` /
`companies_yfinance_fallback` / `m7_aggregate` / `yoy_acceleration`），不对应 `value`
里任何真实 key。

**已复现的具体后果**（不再是理论担忧）：`orchestrator.py:2892-2893` 的
`field_has_value = has_meaningful_observation_value(value_payload.get(field))`，
对这两个函数而言 `value_payload.get("m7_aggregate_and_yoy")` 恒为 `None`，
于是 `field_rules.append("evidence_value_missing")`、`verified` 恒 `False`
——**底层数据完好也被永久判定证据缺失**。

改动波及面：只需改这两个函数的 MetricAuthority 构造；搜索确认无测试/报告代码
硬编码依赖这几个 key 名。T20 是已立项未定案的台账项，不在本次审计内代做决定。

### 4. `CoreFact` 三个低填充字段：删字段 or 排除出规格

`historical_percentile` / `trend` / `magnitude` 在 vNext 主链无"读了据此下结论"的逻辑，
只有写入与透传；**但三者在 `legacy_adapter.py:268,294,328` 都被读取**
（此前"只有 magnitude 一处消费"的说法不准确，已订正）。

四个真实 run 的填充实测（分母为该 run 全部 core_facts）：

| run | core_facts | historical_percentile | trend | magnitude |
|---|---|---|---|---|
| 20260728_110702 | 57 | 8 | 2 | 0 |
| 20260725_232410 | 60 | 0 | 2 | 8 |
| 20260725_145833 | 54 | 1 | 1 | 0 |
| 20260724_223804 | 39 | 0 | 0 | 0 |

**订正一处此前表述**："1/54 与 0/60"是两次不同 run 里同一个字段
（`historical_percentile`）的填充数，不是两个不同字段各一个数；且填充率在 0%~15%
之间跑批波动，不是稳定常数。方向性结论（普遍偏低）成立，引用时不宜死抠某次比例。

**新增变量**：本日上线的 `_render_contract_field_spec` 会把这三个字段列进每次层分析
prompt（实测 `core_facts` 规格行为 `对象 CoreFact{metric, value, historical_percentile,
trend, magnitude, raw_data}`）。它们是可选字段，不构成失败风险；净效果是成本还是收益
（模型看见了可能开始填，而"让极端性进结构化字段"正是用户曾考虑的方向）**只能由下一次
真实 run 的填充率对照来判定**。上表即为对照基线。

## 三、登记在案、暂不处理

5. **`{"high","medium","low"}` 在 `orchestrator.py` 内重复 4 处字面量**
   （`:316,7177,7208,7784`），正式定义在 `contracts.CrossLayerHook.priority` 的 `Literal`。
   当前全部一致，纯维护负担；扩展枚举值时漏改会静默拍扁成默认值。

6. **`AdjudicationChangeRecord.old_status/new_status` 是自由 `str`**
   （`contracts.py:1159-1160`），实际写入过不在 `CompetingHypothesis.status` 枚举里的值
   （`"none"`、`"insufficient_evidence"`，见 `orchestrator.py:2398-2399`）。
   全仓确认**无任何读取方**，纯写入，目前无害。

## 四、明确的阴性结论

- **`CompetingHypothesis.status` 语义判定没有第四处。** 全仓搜索
  `candidate/leading/kept_unresolved/split/downgraded`，覆盖 `src/`、`tests/`、`scripts/`、
  `console_run_all.py`、`legacy_adapter.py`。本日已统一的三处（合约校验器、
  `_run_hypothesis_competition`、`vnext_reporter._hypothesis_competition_block`）口径一致。
  `legacy_adapter.py` 消费的是 `CoreFact` 的 status/magnitude/trend，属另一套概念，
  容易被字面搜索混淆。
- **没有发现"会让真实 run 崩"级别的新问题。** 最严重的第 1 条属于"静默给出失真审计文案"。

## 五、验证记录

- 所有 file:line 在审计时刻工作区状态下用 `grep -n` / 读文件核实。
- `_field_authority_from_payload` 漂移、修复后行为、`_render_contract_field_spec(LayerCard)`
  输出，均由主对话用 `object.__new__(VNextOrchestrator)` 直接调用真实函数复现，
  不依赖 LLM、不跑完整 run。
- CoreFact 填充率由 `output/analysis/vnext/*/layer_cards/*.json` 离线统计。
- 全量 `.venv/bin/python -m pytest --cache-clear -q` → **1017 passed**。
