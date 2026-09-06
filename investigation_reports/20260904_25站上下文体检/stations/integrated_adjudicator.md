# integrated_adjudicator（第三层综合裁决人）上下文体检报告

> run：t70_glm_check_20260902 / 20260902T201627Z / attempt_1（仅 1 次 attempt，A4 不适用）
> 原文 61,468 字符；投影 54,922（89.4%）；共 35 处中段省略标记（19×120 字符、8×320 字符等）。

## 结论

**总体判定：编排与输出端基本健康，未发现 P0 病灶。**「## 本轮输入」占 91.6%（56,293 字符）但内容名副其实——全部是给裁决人的对质材料（第一层数据判决 + 10 张事件卡 + 3 份调查报告 + 6 道题 + 证据权限表），没有混入其他站的完整输出。最重的两个问题：①「本轮输入」内 43/53 个被引用 event_id（81%）没有随附事件卡，题单与材料清单脱节，直接迫使输出 6 题中 5 题只能 partially_answered（P1）；②投影的「超长字符串中段省略」把承诺保留的数值拦腰截断（22.92 → 只剩 ".92"；52周 → 只剩 "2周"），且截断残留文本是错的而非缺失（P1，工具 bug 线索，见「投影缺口线索」节）。

## 体检明细

### A. 顺序

- **A1 段落编排** — 判定：合理。任务定义（开头 275 字符：三件只有裁决人能做的事）→ 输入清单 → 边界 → 输出字段规格（2,261 字符）→ 降级规矩 → 输出格式，全部在数据（91.6%）之前，主干未被切散（投影 8-68 行）。输出字段规格距任务描述近；唯一的注意力风险是 56k 数据之后再无输出要求重申，但本站输出 18 个顶层键全部齐备、字段名零错误，未造成实际伤害。
- **A2 数据时序** — 判定：合理。10 张事件卡按 event_date 新→旧排列：09-02×6 → 09-01（Oracle, 投影 589 行）→ 08-28（Wind, 投影 620 行）→ 08-27（美联储执法, 投影 643 行）。effective_date=2026-09-02 声明在数据块第一位（投影 77 行）。滞后数据有显式标注（如「官方持仓锚（截至2026-08-14，滞后运行时点19天）」投影 956 行）。无过期段落冒充当前状态。
- **A3 few-shot 打断** — 判定：合理。无示例段（无 Example: get_xxx），不存在打断。
- **A4 重试差异** — 不适用：本站仅 attempt_1。

### B. 体量与冗余

- **B1 体量账本** — 「本轮输入」内部（按原文行段实测，UTF-8 字符）：
  | 块 | 字符 | 占输入比 |
  |---|---|---|
  | 事件卡 ×10（fact_summary+interpretation+mechanism+needs_data_confirmation+limitations+evidence_excerpt） | 21,298 | 37.9% |
  | ref_authority ×32（canonical_question+current_reading+usage） | 8,939 | 15.9% |
  | 调查报告 ×3 | 5,385 | 9.6% |
  | payoff/priced_narrative/evidence_refs/key_support_chains | 3,408 | 6.1% |
  | principal_contradiction | 3,703 | 6.6% |
  | 其余（stance 2,500 / hypotheses 2,837 / questions 2,470 / risks+invalidation 1,697 / secondary 1,968 / allowed_refs 1,161） | 12,633 | 22.5% |

  最大三段对「裁决」是否必要：事件卡（必要——conflict_matrix 要求每卡一行，输出 10 行全数覆盖）与调查报告（必要——question_answers 的 inv_refs 直接消费）成立。**ref_authority 的 8.9k 存疑**：其中 current_reading 多数与数据判决正文重复（见 B2），32 条 canonical_question 里 12 条 current_reading 为空串（如 ERP#level、slope_30d，投影 851/858 行）——对裁决人而言「canonical_question」信息量低，是唯一可整体瘦身的大块。
- **B2 站内重复** — 判定：P2。同一数字在数据判决散文、must_preserve_risks、transformation_signals、ref_authority.current_reading 之间反复出现：`99.6`（分位）×8、`8.97`（CCC-BB pp）×6、`718` ×9、`45.75%` ×4、`11.91`（ADX）×5（grep 实测）。例：hy_quality 的「8.97个百分点、z≈2.61、MA5/MA20」既在 principal_contradiction（原文 91 行）、must_preserve_risks（233 行）、调查报告 inv_ef5f875d5ac2（投影 702 行）出现，又整句复刻在 ref_authority.current_reading（投影 872 行）。数据判决是锚、必须整段随行，重复有其结构性理由，但 ref_authority 的 current_reading 属可裁剪的第三份拷贝。
- **B3 粒度错配** — 判定：P2。evidence_excerpt 是网页整页抓取的开头 320 字符，内容是站点导航与行情条：「Oops, something went wrong Skip to navigation Skip to main content…Russell 2000 2,943.05 +22.92 +0.78% VIX 15.45…」（原文 363 行）、「Benzinga España Italia 대한민국 日本 Français My Acc…」（原文 410 行附近）。10 张卡带 8 段此类 excerpt ≈ 3k 字符，几乎全是与裁决无关的页面杂物，还夹带无关行情数字；另 event_layer_summary（原文 328 行）本身就是英文标题串拼接。卡片结构化字段（fact_summary/limitations）已覆盖其有用信息，excerpt 是被推给模型注意力的预处理欠账。

### C. 质量

- **C1 指令冲突** — 判定：P2（一处规格缺口，非硬冲突）。「数据判决是锚，你无权改判」（投影 40 行）与六档归档、objections 唯一出口等规则自洽，未发现互相打架的纪律对。规格缺口：ref_authority 有 audit_only / supporting_only / validation_only 三档 usage（实测 30×supporting_only、1×validation_only、1×core_allowed），但边界段只定义了 audit_only 与 supporting_only 的禁区（投影 43 行），**validation_only 无任何语义定义**。后果：输出把 validation_only 的 `L4.get_ndx_pe_and_earnings_yield#ForwardPE` 放进了 data_support（输出 data_support 第 26 项），模型靠自己在 notes 里补写「仅作交叉核对、不独立支撑结论」——规则空档由模型自行解释。
- **C2 死指令** — 判定：合理（抽查 6 项全活）。①输出 18 个顶层键与规格一一对应；②conflict_matrix 10 行、字段名恰为规格要求的 card_id/event_side/relation/data_side_refs/note；③question_answers 6 条对 6 问、question_ordinal 1-6、按纪律未填 question_id（系统回填）；④partially_answered ×5 全部带 113-181 字符的具体 missing_evidence（如「缺 NVDA 2026Q2 财报公布后的营收同比修订值」式具体度）；⑤data_support 26 个 ref 全部 ∈ allowed_data_refs 32 个（程序核验，0 越权）；⑥event_support 9 个 event_id 全部 ∈ 输入 10 卡。无死指令。
- **C3 黑话词典** — 判定：「4C」排除嫌疑；发现 1 处真黑话。**「4C」在原文 5 次命中全部是 event_id 十六进制哈希片段**（`event:4c46665e1c0dbd9e` 原文 711 行、`7df03f4ce8689c7a` 766 行、`271b4c79178e1077` 723 行等），大小写不敏感匹配均为 ID 子串，**不是内部黑话，不列传染源**。真黑话 1 处：**「O10纪律」**（原文 903 行，ref_authority 中 L5.get_obv_qqq 的 current_reading：「绝对水位按O10纪律不作判读、仅审计对账」）——prompt 全文无解释，属 L5 层导入的内部纪律代号；好在其未进入输出叙事。系统性措辞（「研究架」「巡逻」「对账升格」「亮红灯」）在输入清单/边界段均有当场解释（投影 32、40 行），新分析师模型可读懂。
- **C4 数据新鲜度** — 判定：合理。effective_date=2026-09-02 且边界明令「晚于该日期的信息不存在」（投影 42 行）；事件日期 08-27~09-02 全部 ≤ 生效日；读数日期 08-28~09-02；唯一显著滞后（持仓锚 08-14）被显式标注滞后 19 天（投影 956 行）。输出 notes[7] 还主动重申了 effective_date 纪律。

### D. 隔离

- **D1 越权扫描** — 判定：未发现越权。关键词全文 0 命中：`final_adjudication` / `thesis_draft` / `browser_sidecar` / `user_decision_profile` / `golden_pit` / `apparent_cross_layer_signals` / `门脸` / `三明治` / `恒空`。本站看到的 final_stance/reasoned_verdict 是输入清单明示的「第一层数据判决本体」（投影 28 行），属设计内输入而非 final 站结论泄漏；事件卡与研究部巡逻归第二层、调查员报告独立于事件层，均与开头声明的分工一致（投影 20 行）。

### E. 输出闭环

> 输出文件：`output.validated.json` 与 `attempt_1.parsed.normalized.json` **均不存在**，按清单降级读 `attempt_1.response.raw.txt`（38,865 字节，合法 JSON，可直接解析）。

- **E1 叙事字段体检**：
  - **黑话传染**：未发现。叙事里出现的 OBV、A/D 线均为首次出现给半句解释（「OBV（能量潮，量能累积指标）」「A/D线（涨跌家数累计的广度指标）」）；C3 清单里唯一的 O10 未被带出。
  - **复读机检测**：轻度，不算背题。剔除 ref/ID 后叙事散文与 prompt 有 27 处 ≥15 字符相同，但绝大多数是引锚定数字的事实短语（「Top10权重45.75%、NVDA单一8.51%」「30日上修斜率+3.93%、capex同比+84%」）；最长的整句级重复是「接冲击准备金，对边际资金最敏感的高估值资产先受压」（24 字，源自 must_preserve_risks）与「CCC-BB分层利差8.97个百分点处统计窗口100分位且继续走阔，」。引用锚定判决的内容属裁决人职责内，未发现整段背题。
  - **簿记语言密度**：健康。ref 与 [card:event:…] 标注嵌在因果链里服务比较（每个数字带 ref 且有判断句收尾），无裸列 ref 清单的段落。
  - **长度纪律**：规格只要求「写完整、不凑字」无字数上限；integrated_verdict 3,358 字符、7 段结构化论证，判定合规。
  - 一处小瑕疵：事件卡引用格式输出为 `[card:event:c5ee0104915b5fcf]`（双冒号），规格示例是 `[card:event_xxxx]`（下划线，投影 49 行）。模型选择了与 data_verdict_objections 规格一致的 `event:<event_id>` 冒号式（投影 57 行），更可能是 prompt 自身示例笔误，但格式分叉值得统一。
- **E2 因果对**：
  - **成立的一对**：材料缺陷 = cross_layer_questions 共 53 个 event_refs，43 个（81%）不随附事件卡（输入只带 10 张卡，程序核验）→ 输出效应 = 6 题中 5 题 partially_answered、0 题 cannot_answer_yet，且模型在 notes[2] 主动坦白「约三十个未随解读卡提供…缺口已在各 missing_evidence 中列明」。材料缺口被诚实吸收为 hedge，未诱发编造——这正是该站纪律设计的预期效果。
  - 另一对（弱）：材料缺陷 = evidence_excerpt 页面杂物含无关行情数字（B3）→ 输出效应 = 未发现任何杂物流入输出（数字全部可溯源到结构化字段或 ref_authority），说明不可信材料隔离起了作用，**未连成实际因果**。
  - 投影数字截断（22.92/52）只影响体检投影，不影响模型实际收到的原文，与输出无因果。

## 病灶清单（按严重度排序）

1. **P1 | 投影工具 bug：中段省略把承诺保留的数值拦腰截断，残留错误文本**——22.92→".92"（投影 380 行）、52周→"2周"（投影 339 行），详见下节。
2. **P1 | cross_layer_questions 的 53 个 event_refs 中 43 个（81%）无随附事件卡，题单与材料清单脱节**——原文 704-792 行；直接导致输出 5/6 题 partially_answered（输出 question_answers）。
3. **P2 | evidence_excerpt ≈3k 字符为网页导航/行情条杂物**——原文 363、410 行等 8 处；B3 预处理欠账。
4. **P2 | ref_authority 8.9k 字符（输入 15.9%）与判决散文三份复述同一批读数**——如 8.97pp 四处出现；12/32 条 current_reading 为空串。
5. **P2 | validation_only 档 usage 在边界规则中无定义**——投影 43 行只定义了 audit_only/supporting_only；输出把 ForwardPE 放进 data_support。
6. **P2 | 输入 JSON 内残留上游截断痕迹**——hyp_counter_7c11370905 的 hypothesis_text 以「RSI 46」戛然而止（原文 322 行），数字 46 的取值被上游截掉。
7. **P2 | 「O10纪律」黑话无解释**（原文 903 行）；事件卡引用格式 prompt 示例（下划线）与输出实际（双冒号）不一致。

## 投影缺口线索（给摊开工具的 bug 报告）

**现象**：校验器报告 22.92 与 52 两个「承诺保留」数值丢失。实测原文（attempt_1.prompt.txt）中 `22.92` 出现 **1 次**（非任务简报所称 2 次；建议核对校验器计数口径），`52` 作为独立数字出现 **2 次**（均为「52周」）。投影丢失情况：

1. **22.92**（原文 363 行，事件卡 event:c5ee0104915b5fcf 的 evidence_excerpt，网页行情条「Russell 2000 2,943.05 +22.92 +0.78%」）→ 投影 380 行中段省略 320 字符后残留「…Skip to navigat«…省略 320 字符…».92 +0.78% VIX…」——**「+22」落入省略区，「.92」成为孤儿**，`22.92` 消失。
2. **52**（原文 322 行，hyp_counter_7c11370905 的 hypothesis_text「…但200日均线上方仍有69%、52周新低只有1只…」）→ 投影 339 行省略 120 字符后残留「…Top10权重代理63天基本走«…省略 120 字符…»2周新低只有1只…」——**「5」落入省略区，「2」成为孤儿**；该卡的另一处「自52周高点」（原文 412 行，投影 429 行）完好保留。

**根因判断**：两例是同一 bug——「超长散文字符串中段省略」按固定字符数切割边界，**不感知数字 token 边界**，把「承诺内数值」从中间劈开。比纯丢失更糟的是残留物是**错误文本**而非缺失标记：「2周新低只有1只」会被投影读者误读为「2周新低」，「.92 +0.78%」像残缺报价。校验器的「承诺内数值」核对大概率在截断前扫描原文，故能报出丢失。

**修复方向**（不动手实现）：省略边界回退/前进吸附到非字母数字边界（至少避开数字中间）；或对省略区做数字 token 扫描，将跨界数字移入标记（如「«…省略 320 字符（含数值 +22.92）…»」）；残留首尾片段若以半截数字开头/结尾，应并入标记而非留在正文。

## 修复建议

1. （对病灶 2）题单生成时按「随附卡集合」过滤 event_refs，或反向把被引用事件的最小事实摘要一并随行；至少在 prompt 里声明「event_refs 可指向未随卡的已过滤事件」。
2. （对病灶 3）evidence_excerpt 改为去 chrome 后的正文摘要或直接删字段——卡片结构化字段已足够。
3. （对病灶 4）ref_authority 只保留 usage + 权限相关字段，current_reading 与 canonical_question 仅在判决散文未含该读数时填充。
4. （对病灶 5）在边界段补一句 validation_only 的定义（如「仅校验口径，不得进入 data_support/current_phenomena」）。
5. （对病灶 6）上游 payload 生成器对 hypothesis_text 截断时避免切在数字 token 中间，或补「[截断]」标记。
6. （对病灶 7）prompt 内部代号（O10 等）进入跨站材料时随行半句解释；统一事件卡引用格式示例。
