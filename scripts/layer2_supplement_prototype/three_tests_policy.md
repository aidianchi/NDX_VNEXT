# 三性判定政策（第二层补采原型 · 常驻脚本配套）

本文件是 `three_tests.py` 的唯一政策来源。脚本从下方「机器可读阈值」JSON 块读取阈值常量；改规则先改这里，再跑 `tests/test_layer2_prototype.py` 确认脚本与政策一致。

## 1. 三性定义

| 性 | 定义 | 机器判定（阈值见下方 JSON） |
|---|---|---|
| 靠谱（reliable） | 来源是否官方 / 一手 | `sources_audit.json` 的 `trust` 字段 ∈ `reliable_trust_values`。默认认「官方」与「授权」。注意：Wind 两源的 pass 来自 `owner_overrides`，机器初判为转agentic。 |
| 必要（necessary） | 是否回答第二层四类问题之一（已发生的事 / 将发生的事 / 被相信的事 / 规则语境；历史语境为第五类，个案处理） | `necessity` 文本包含 `necessary_category_keywords` 任一关键词。 |
| 能死板拿（dead_simple） | 格式稳定、确定性可得、无需登录 / 浏览器 | `scrapable` 字段 ∈ `dead_simple_scrapable_values`。默认只认「能」。 |

三性全过（verdict = pass）的源才配留在确定性流水线；任一性不过的源，verdict 按下方判定顺序落为 `撤出 / 转agentic / 弃用`，并写入 `sources_to_remove.json` 名单（只输出名单，不实际删源）。

## 2. 谁裁决

- 初判由 `three_tests.py` 机器执行，阈值只从本文件 JSON 块读取，不散落在代码里。
- 终判（实际执行删除 / 迁移 / 改注册表）必须经人复核；脚本不触碰 `news_event_ledger.py` 或任何采集注册表。

## 3. 新源先过审

- 任何新增采集源在注册进流水线之前，必须先补入 `sources_audit.json`（或同等底账），并跑 `three_tests.py` 过三性。
- verdict 非 `pass` 的新源不得注册为确定性流水线源；需要 agentic 补采的按 `转agentic` 另行排队。

## 4. 名单与 baseline 差异要人复核

- `three_tests.py` 只输出 `layer2_three_tests_report.json` 与 `sources_to_remove.json`，不实际删源、不改任何既有文件。
- 差异复核口径：与 baseline（`investigation_reports/20260811_layer2_research/baseline/sources_audit.json`）相比，凡 verdict 非 `pass` 的源，以及任何「pass ↔ 非 pass」变化的源，都需要人确认一次，确认后由根线程另行施工。
- `挂起` = 所有者已裁「暂时不管」：不进 `sources_to_remove.json`，也不当 `pass`，留待后续复核。

## 5. 机器可读阈值（脚本从此块读取）

```json
{
  "schema_version": "layer2_three_tests_policy_v1",
  "reliable_trust_values": ["官方", "授权"],
  "necessary_category_keywords": ["已发生", "将发生", "被相信", "规则语境", "历史语境"],
  "dead_simple_scrapable_values": ["能"],
  "verdict_decision": {
    "not_necessary": "弃用",
    "reliable_and_dead_simple": "pass",
    "reliable_not_dead_simple": "转agentic",
    "not_reliable_dead_simple": "撤出",
    "not_reliable_not_dead_simple": "弃用"
  },
  "verdict_order_note": "判定顺序：先 necessary（不过→弃用）；再 reliable 且 dead_simple（→pass）；再 reliable 且 !dead_simple（→转agentic）；再 !reliable 且 dead_simple（→撤出）；最后 !reliable 且 !dead_simple（→弃用）。",
  "owner_overrides": {
    "wind_company_announcements_m7": {"verdict": "pass", "reason": "所有者 08-15 裁：wind 继续用（实体匹配丢已解释，继续观察；三态口径下次真实跑复核）"},
    "wind_financial_news_ndx": {"verdict": "pass", "reason": "所有者 08-15 裁：wind 继续用，保持观察"},
    "alpha_vantage_news_sentiment": {"verdict": "挂起", "reason": "所有者 08-15 裁：暂时不管，挂起"}
  }
}
```
