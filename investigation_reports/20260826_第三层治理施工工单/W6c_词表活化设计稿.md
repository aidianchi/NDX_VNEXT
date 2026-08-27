# T67/W6c · 词表活化机制设计稿（含 W6a/b 诊断与结论）

> 状态：设计稿，等老板拍板后施工。W6a 即时补丁已落地（见 §2），W6b Reddit 结论见 §4。
> 落盘：`investigation_reports/20260826_第三层治理施工工单/WORK_ORDERS.md` 的 W6 一节。

---

## 1. 根因诊断：W6 三个子项是同一个病灶的三张脸

实测（20260826_124855 run，63 条事件 + 16 条 Yahoo）：

| 子项 | 表象 | 真相 |
|---|---|---|
| W6a Yahoo 正文率 44% | 16 条里 7 条有正文 | **7 条是"关键词闸门故意不抓"（`body_fetch_not_attempted`），2 条真失败（`empty_or_unreadable`），7 条成功**。缺口主因不是抓取失败，是**关键词表太窄** |
| W6b Reddit 0/4 | 社媒全无正文 | `social=True` 默认不抓正文是**设计**（`_should_fetch_article_body` 第 1064 行：`if social ... return False`），不是 bug |
| W6c 关键词表写死 | 新主题不自动进池 | `HIGH_RELEVANCE_KEYWORDS` / `HIGH_RELEVANCE_BODY_FETCH_KEYWORDS` 是静态清单，且**漏掉 M7 大部分公司名** |

**核心病灶**：采集器的相关性判定靠**三张静态关键词表**（`news_event_ledger.py` 的 `HIGH_RELEVANCE_KEYWORDS`、`HIGH_RELEVANCE_BODY_FETCH_KEYWORDS`、`M7_ENTITY_ALIASES`）。正文抓取表只有芯片名（nvidia/amd/intc），漏了 TSLA/META/AAPL/AMZN/MSFT/GOOGL——所以 16 条 Yahoo 里 7 条 M7 相关标题被"not_attempted"。

## 2. 已落地的即时补丁（W6a）

- `news_event_ledger.py`：新增 `M7_BODY_FETCH_TERMS`（M7_ENTITY_ALIASES 的扁平小写化），`_should_fetch_article_body` 把它并入判定。
- 理由：M7 占 NDX 权重约四成，任何 M7 公司新闻都是高相关，正文值得抓。
- 效果：Yahoo 正文率应从 7/16 明显抬升（那些 not_attempted 的 TSLA/META/AAPL 标题现在会去抓正文）。
- 附带测试：`test_body_fetch_gate_recognizes_m7_entity_names`（先红后绿）。

## 3. 词表活化机制（W6c 的核心，等拍板）

即时补丁只是把 M7 补进去，**没有解决"写死"这个根**——将来市场上冒出新的主导主题（比如某年的新叙事），词表还是不会自己长出来。这正是体检里说的"传感器焦距固定"。

**设计原则（老板口径）**：词表是采集边界，归老板管；任何自动机制**只出候选，不出决定**。

**机制（四步）**：
1. **候选来源**：出题官研究任务书（缺口驱动）、巡逻 narrative_state 的"缺席信号"、data_gaps 清单——这三处已经在产"系统现在够不着的新主题"。
2. **候选词落账**：新增 `output/event_research/term_candidates.jsonl`（只追加不改写），每条带：词、来源（哪道题/哪个缺口）、提出时间、建议用途（入池/入正文抓取/仅跟踪）。
3. **老板圈定**：控制台复用圈题面板（或一个轻量页面），老板勾选 → 词进入 `HIGH_RELEVANCE_*` 词表；不勾的留在候选账里、不复活。
4. **机器闸门**：词表变更落盘留痕（谁、何时、加了什么词），防静默增删。

**为什么不做全自动**：关键词决定"什么进底账"，是采集边界；全自动会把模型自己造的噪声词灌进边界。和经费卡、白名单同一逻辑——边界归老板。

**不做的事**：不做"语义向量召回"替代关键词（那是 L3 范畴的语义层，采集层保持死板、可审计）。

## 4. W6b Reddit 结论（如实）

- Reddit 正文抓取**默认关闭是设计**：社媒叙事档的价值在"情绪温度"，不在原文事实；抓正文成本高（反爬、接口变化）收益低。
- **建议维持不抓 + 如实标注**（`raw_text_available=False` 且 notes 写明 social 语义，已有）。
- 若老板要补：加一个 `include_social_body` 开关（默认关），仅当某类社媒信号被证明有正文价值时再开——**不现在做，留老板裁决**。

## 5. 完成状态

| 项 | 状态 |
|---|---|
| W6a Yahoo 正文（M7 别名补丁） | ✅ 已落地（`67d8472` 之后的新提交，本批） |
| W6b Reddit 正文 | 结论：维持不抓+如实标注，开关留老板 |
| W6c 词表活化 | 设计稿完成（本文）；施工等老板拍板 |
