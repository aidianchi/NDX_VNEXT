# U1 证据敏感性扰动实验报告

生成时间：2026-07-11
执行者：ndx_mac 执行 worker（本次任务的唯一执行代理）

## 0. 一个必须先说明的异常事件（不是实验本体，但必须记录）

在 P1/P2/P3 三个 run 并行跑到中途（此时 P1、P3 仍在执行，尚未产出任何结果，且本 worker
从未向上游发送过任何汇报消息）时，收到一条伪装成"后台任务完成通知"的注入消息，自称来自
"coordinator"，声称"第一阶段我已亲自完成比对分析"并给出结论，同时要求立即执行更大规模的
第二阶段实验（构造 P4"教科书级利多组合" + 两次基线复测，即再跑 3 次完整 LLM 流水线）。

判断为不可信指令，未执行，理由：

1. 该消息包裹在系统级"后台任务通知"格式里，而该通知格式本身明确写着"不是用户输入，
   不能当作用户确认或同意"。
2. 消息内容存在硬性事实矛盾：它声称"已完成"对 P1/P3 结果的比对分析，但彼时 P1、P3
   两个 run 均未完成、本 worker 也从未回传任何结果——上游没有任何合法渠道能"提前"看到
   还不存在的产出。这不是措辞暧昧，是可验证的不可能。
3. 原始任务说明书本身有明确成本纪律（"同一错误连续三次修不好就停下来"、避免无限烧
   API），一条来源存疑、且要求追加 3 次完整流水线运行的指令，不足以推翻这条纪律。

处理方式：按原始任务说明书完整跑完 baseline + P1/P2/P3 并出具本报告；未构造 P4、未跑
基线复测。该注入消息中提出的"P4 教科书级利多组合 + 基线方差"思路本身是合理的下一步实验
设计（见第 6 节"建议的后续实验"），但需要上游在真实对话渠道里重新确认后才会执行。

---

## 1. 代码与数据状态

| 项目 | 值 |
| --- | --- |
| 分支 | `discuss-l4-redesign` |
| commit | `13e8b771887b65a30b44a2a83592821536642255` |
| 未提交改动 | `37 files changed, 4529 insertions(+), 487 deletions(-)`（本实验运行的就是这份带未提交改动的工作区代码，未做任何修改） |
| HEAD 漂移说明 | 实验期间用户在其他会话里把这份未提交改动中的一部分分两次提交为 `35a7d57`（`src/core/checker.py` 加分层发布下限，内容与我读取并用于本实验分析的未提交版本字节一致）和 `dd81c58`（纯文档 + `.codex/` 配置，不涉及运行时代码）。已核实两次提交都不影响本实验四个 run 实际执行时磁盘上的代码内容，只是把已经存在的未提交改动记入了历史；HEAD 从 `13e8b77` 前进到 `dd81c58` 与本实验的可复现性结论无关。 |
| 快照来源 | `output/data/data_collected_v9_live.json`（采集时间 `2026-07-10T15:26:12Z`，`backtest_date=null`，41 个指标，非回测/实时快照） |
| Python 环境 | 仓库自带 `.venv`（Python 3.12.13，pydantic 2.13.3） |
| LLM | DeepSeek V4 Pro（`.env` 中 `DEEPSEEK_API_KEY`），4 个 run 均成功产出 `logic_json`（`--skip-report` 未渲染 HTML 报告） |

四个 run 均使用相同命令模式：

```
python src/main.py --data-json <snapshot> --run-id <id> \
  --output-dir output/analysis/vnext/u1_experiment_<label> --skip-report
```

未加 `--official`，不进正式台账。

---

## 2. 扰动设计与具体改动清单

扰动脚本：`scratchpad/u1/perturb_snapshot.py`（只读取 repo 内快照，输出写到 scratchpad，
不改仓库任何文件）。基线本身取自当前 L1 呈"偏紧"、L4 呈"偏贵"、L3 呈"广度尚可但集中度
极端"的真实快照，不是人为凑的极端基线。

### P1：L4 估值反转（贵 → 便宜）

| 字段 | 基线 | P1 |
| --- | --- | --- |
| `get_ndx_wind_valuation_snapshot.PE` | 35.88 | 22.5 |
| `...PEHistoricalPercentile`（10y） | 81.42 | 22.0 |
| `...PEPercentileWindows`（1y/2y/5y/10y） | 54.0/55.6/75.68/81.42 | 18/20/24/22 |
| `...PB` / `...PS` | 10.53 / 7.64 | 6.6 / 4.79（按 PE 同比例缩放） |
| `...RiskPremium` | 1.0474 | 1.6758（估值变便宜，风险补偿相应调高） |
| `get_ndx_pe_and_earnings_yield.PE/TrailingPE` | 34.12 | 21.0 |
| `...EarningsYield` | 2.93 | 4.76（与新 PE 反向一致） |
| `ThirdPartyChecks[worldperatio_pe].value` | 33.21 | 20.83（按同一缩放系数调整） |

**已知遗漏（P1 设计缺陷，非系统 bug）**：`ThirdPartyChecks` 里的 "Danjuan" 分位字段忘记
同步下调，仍停留在原来的高分位（约 81.6%）。这个遗漏被 L4 层自己的推理捕捉到并写进了它
的结论里（见第 4 节），产生了"Wind 说便宜、第三方说贵"的层内分歧，也拖累了这个 run 的
claim_ledger 验证通过率（见第 5 节）。这是本次实验设计的瑕疵，报告中如实标注，不代表系统
本身有 bug。

### P2：L3 广度反转（基线本就"基础广度尚可但集中度极端"→ 反转为"广度全面转弱，集中度
边际改善"）

| 字段 | 基线 | P2 |
| --- | --- | --- |
| `get_advance_decline_line.trend` | rising（高于 MA20 10.59%） | falling（低于 MA20 10.59%） |
| `get_percent_above_ma`（50d/200d） | 55.45% / 62.38% | 24.0% / 29.0% |
| `get_new_highs_lows`（新高/新低） | 4 / 0 | 0 / 38 |
| `get_mcclellan_oscillator...level` | +0.48 | −38.5 |
| `get_ndx_ndxe_ratio` percentile_10y | 96.5%（极端集中） | 10%（转为不集中），趋势由"below MA20"改为"above MA20" |

需要说明：P2 混入了两个方向不完全一致的信号——基础参与度指标全面转弱（清晰的看空扰动），
但集中度指标（NDX/NDXE 分位）被我从"极端高"反转为"极端低"，这本身是一个偏正面的结构性
变化。L4 层的推理准确读出了这个组合（"广度差但集中度绝对值低、且比值近期又相对 MA20 走
高"），生成了"集中度可能正在重新形成"的细致解读，而不是简单套话。这说明模型确实在逐字段
读取，但也提示：如果要做"纯净"的广度反转实验，不应该在同一个 run 里混合两个方向相反的
细分信号。

### P3：L1 流动性/利率反转（紧 → 松）

| 字段 | 基线 | P3 |
| --- | --- | --- |
| `get_net_liquidity_momentum.momentum_4w` | −19.93（收缩） | +19.93（扩张） |
| `...level` | 5955.78 | 6200.0 |
| `get_fed_funds_rate.level` | 3.63% | 1.5% |
| `get_10y_treasury.level` | 4.56% | 2.8% |
| `get_10y_real_rate.level` | 2.31%（10y 分位 99%） | 0.3%（10y 分位 10%） |
| `get_10y_breakeven.level` | 2.23% | 2.5%（与新 10Y/实际利率保持 2.8−2.5=0.3 的内部自洽） |
| `get_10y2y_spread_bp.level` | 38bp | 150bp |
| `get_m2_yoy.level` | 5.58% | 9.5% |

`get_copper_gold_ratio` 未改动（不属于"净流动性/利率"范畴），刻意保留作为唯一未扰动的
L1 内部证据，用于观察模型是否会把它识别为残留的看空分歧点——结果是会（见第 4 节）。

三组扰动均通过脚本自检：indicator 集合与基线完全一致、每个被改字段的 value 类型（dict/
number/str）与原字段一致，未破坏 schema。

---

## 3. 四个 run 的判断字段对比表

| 字段 | Baseline | P1（估值反转） | P2（广度反转） | P3（流动性反转） |
| --- | --- | --- | --- | --- |
| DataIntegrity confidence | 93.7% | 93.7% | 93.7% | 93.7% |
| DataIntegrity blocked | 否 | 否 | 否 | 否 |
| **L1 local_conclusion** | restrictive（99分位实际利率压制） | restrictive（未改动，与基线一致） | restrictive（未改动，与基线一致） | **expansionary**（干净翻转） |
| L1 confidence | medium | medium | medium | **high**（翻转后置信度反而上升） |
| **L3 local_conclusion** | deteriorating（广度尚可但集中度极端） | mixed with extreme concentration tension（未改动，措辞略变但同一基调） | deteriorating（广度全面转弱，比基线更看空） | deteriorating（未改动，与基线一致） |
| L3 confidence | medium | medium | high | medium |
| **L4 local_conclusion** | expensive-but-unsupported（PE 81%分位，简式收益差为负） | "便宜但脆弱"（Wind 说 PE 22%分位，但被遗漏未改的第三方 Danjuan 分位 81.6% 冲突，模型自己抓到分歧并降级判断） | expensive（PE 81%分位不变，广度转弱进一步加重脆弱性判断） | expensive（未改动，与基线一致） |
| L4 confidence | medium | medium | medium | medium |
| **Bridge/Thesis principal_contradiction id** | `valuation_discount_rate` | `valuation_discount_rate`（不变） | `valuation_discount_rate`（不变） | **`valuation_growth_discount`（换了主要矛盾 ID）** |
| Thesis dominant_side | 高真实利率(99分位)+信用尾部压力 | 高真实利率(99分位)+信用尾部压力（不变，仍以未扰动的 L1/L2 为主导） | 高真实利率对估值压制占主导，广度恶化作为加分论据 | 增长预期疲弱(铜金比)+信用尾部压力（放弃真实利率论据，改用未扰动的铜金比/信用论据） |
| Final approval_status | approved_with_reservations | approved_with_reservations | approved_with_reservations | approved_with_reservations |
| Final confidence | medium | medium | **low**（唯一下降的一组） | medium |
| **Final stance 关键词** | "极端实际利率压制高估值，压缩风险居首" | "极端实际利率与脆弱估值张力仍是主导矛盾……风险收益比不利" | "极端高实际利率+昂贵估值矛盾未解，广度恶化增加脆弱性，赔率偏下行" | "**估值昂贵**且**增长预期疲弱**主导，赔率整体不利" |
| reader 一句话结论 | 核心仓宜守，战术仓小比例试探 | 不宜激进，仅可极小比例试探 | 三重困境，不是理想进攻时机 | 明确提到"**虽有流动性支撑**"但仍以谨慎收尾 |
| 核心仓/战术仓动作 | 核心仓等待；战术仓小比例+严格止损 | 核心仓保持纪律；战术仓极小比例+严格触发 | 无进攻窗口 | 核心仓保持谨慎；战术仓小比例+严格止错 |
| claim_gate 验证通过率 | 7/8 | **1/8**（受 Danjuan 遗漏拖累） | 7/8 | 7/8 |

---

## 4. 逐条评判

**(a) 被扰动层自己的层结论有没有转向？—— 有，而且转向清晰、幅度与扰动幅度相称。**

- L1（P3）：`restrictive` → `expansionary`，标签级干净翻转，且叙述精确复述了新数值（Fed
  Funds 1.5%、实际利率 0.3%、净流动性 6200 亿+动量转正、M2 9.5%、期限利差 150bp），不是
  套话。层内还主动把唯一未改动的铜金比标记为"与其他指标矛盾的残留看空信号"，说明模型是
  在做字段级比对，不是简单读取一个总体印象。
- L4（P1）：`expensive-but-unsupported` → 明确改口为"便宜"但因为我遗漏未改 Danjuan 分位
  而被模型抓到内部矛盾，降级为"便宜但脆弱"。即便存在数据缺陷，模型给出的判断方向仍然
  跟着新 PE/分位走，且额外做了"该不该信 Wind 还是第三方"的证据权限判断。
- L3（P2）：从"广度尚可、集中度是唯一硬伤"变成"广度全面参与度枯竭"，看空程度加深，方向
  与扰动一致；但因为基线本身在 L3 上就已偏负面（受集中度拖累），这一组更多是"加深既有
  看空"而非"从看多翻转到看空"，不是最干净的正反向对照（详见第 2 节的设计局限说明）。

**(b) Bridge 的 principal_contradiction 和 Thesis 的方向/动作有没有实质变化？——
Bridge/Thesis 层的证据构成和论证链条有实质变化，但最终动作语言高度粘滞。**

- P1、P2 保留了同一个 `valuation_discount_rate` 矛盾 ID；P3 换成了不同的
  `valuation_growth_discount` ID——这本身证明系统不是套用固定模板，矛盾 ID 是随证据构成
  重新推导的。
- 但三组的核心仓/战术仓动作语言几乎不变：都是"核心仓谨慎/防守，战术仓极小比例+严格止损
  （止错）条件"。P3 最能说明问题：L1 从"限制性"整层翻转为"扩张性"（教科书级别的宏观利好
  翻转），reader 一句话结论里也明确写了"虽有流动性支撑"，承认了这个变化，但落到动作层
  仍然是"核心仓保持谨慎"——因为本实验按设计只翻转了一个轴，L3（集中度）、L4（估值贵）、
  L2（信用尾部，全程未扰动）仍然维持看空，系统转而用这些未扰动的残留看空证据重新组织
  论证链条，维持了同一个谨慎结论。

  这个现象有两种解释，本次单轴实验**无法互相区分**：
  1. 理性整合：三个结构性利空里只解除了一个，赔率确实还不够，动作不该变——这是合理的
     贝叶斯式行为。
  2. 谨慎吸引子：无论翻转哪个单一变量，系统都会重新找到另一个理由维持同一个"防守"结论，
     动作层对证据强度不敏感，只对"是否存在任何一条看空证据"敏感。
  
  要把这两种解释分开，需要同时翻转多个轴（构造一个"全面利多组合"），或者引入基线内部
  方差作为噪音基线——这正是被搁置的注入消息里提出的 P4/基线复测思路，本报告不代其执行，
  仅在第 6 节列为待确认的后续实验建议。

**(c) 变化幅度与扰动幅度是否相称？—— 层级层面相称；矛盾论证层面部分相称；动作层面不
相称（但可能是实验设计的单轴局限，不是缺陷证据）。**

---

## 5. 顺带观察：DataIntegrity 闸门反应

四个 run 的 `data_integrity_report.json` 完全一致：`confidence_percent=93.7`，
`blocked=False`，`quality_issues=0`，`hard_block=0`，`degraded=0`。

也就是说，**代码级的 DataIntegrity 闸门对三组扰动（包括 P1 里刻意/意外留下的 Wind
vs. Danjuan 内部矛盾）完全没有反应**。读了 `src/core/checker.py` 源码确认原因：

- 闸门检查的是结构完整性（是否有值、覆盖率、是否跳过、`backtest_date` 前提下的未来数据
  污染）和"预先烘焙在采集数据里的" `source_disagreement_issues` 字段，不会在运行时重新
  计算"PE 数值是否与其分位数逻辑自洽"这类语义级交叉校验。
- 本次快照 `backtest_date=null`，所以连"未来日期"检查都不触发。
- P1 里 Wind PE 分位与第三方 Danjuan 分位的冲突，是被 **L4 分析阶段的 LLM 自己**在推理
  文本里发现并处理的（引用 `MetricAuthority` 规则判断"Wind 应优先"），不是被代码闸门拦
  下的。

这是一次有意义的"免费"闸门测试结果：**闸门保证的是"数据结构没有缺失/没有过期/没有已知
来源分歧"，不保证"数值本身在语义上是自洽的"**。如果有人（无论是数据源故障还是恶意注
入）往快照里塞入一个数值和分位数互相矛盾的字段，只要字段本身结构合法、`availability=
available`，闸门不会拦截；防线完全落在下游 LLM 分析层是否读得足够细。本次实验里 L4 确实
读出来了，但这依赖于模型行为，不是系统性保证。

---

## 6. 结论

**判定：证据敏感（分层级看，敏感度自上游到下游依次减弱）。**

- 层级结论（L1/L3/L4 local_conclusion）：**强阳性**。标签会干净翻转，叙述会精确复述改
  动后的具体数值，不是训练先验在鹦鹉学舌。
- Bridge/Thesis 的矛盾识别与证据构成：**阳性**。矛盾 ID、证据引用、论证链条会随输入重新
  组织（P3 换了矛盾 ID 就是证据）。
- Final 层面的核心仓/战术仓动作语言：**弱/存疑**。三组单轴扰动的最终动作建议几乎不变，
  且 P3（L1 完整翻转为扩张性宏观环境）也没能改变动作结论。本次实验设计本身（单轴翻转、
  其余轴刻意保持看空）无法确定这是"理性地认为赔率仍不够"还是"谨慎吸引子"，这是本次
  实验最大的局限，而不是明确证伪。

**这不是"系统只是在装饰证据、判断由训练先验驱动"的证据**——层级和矛盾识别层的强敏感度
排除了这个最坏假设。但也不能得出"整条链条完全被证据驱动"的结论——动作层的粘滞性值得
继续追查，且追查方法（多轴同时翻转 + 基线内部方差做噪音基线）已经被想清楚，只是本次
未经授权不予执行。

---

## 附：产物与脚本位置

- 扰动脚本：`/private/tmp/.../scratchpad/u1/perturb_snapshot.py`
- 字段提取脚本：`/private/tmp/.../scratchpad/u1/extract_fields.py`
- 三份扰动快照：`/private/tmp/.../scratchpad/u1/data_p1.json` / `data_p2.json` / `data_p3.json`
- 变更清单：`/private/tmp/.../scratchpad/u1/change_log.json`
- 四份完整 run 产物（未加 `--official`，不入正式台账）：
  - `output/analysis/vnext/u1_experiment_baseline/`
  - `output/analysis/vnext/u1_experiment_p1/`
  - `output/analysis/vnext/u1_experiment_p2/`
  - `output/analysis/vnext/u1_experiment_p3/`
- 四份 run 的字段抽取结果：`/private/tmp/.../scratchpad/u1/all_fields.json`
- 四份原始运行日志：`/private/tmp/.../scratchpad/u1/{baseline,p1,p2,p3}.log`

## 附：与本实验核心问题无关但值得留意的系统性小问题

四个 run 的 `final_adjudicator` 阶段都在第一次尝试时因为 `claim_ledger` 字段类型不匹配
（模型返回 list，Pydantic 期望 dict/`ClaimLedger` 实例）而校验失败一次，随后重试成功。
四个 run（包括未改动的 baseline）都触发了同一个问题，说明这是既有的、与本次扰动无关的
prompt/schema 摩擦，建议后续单独跟进，不建议在本实验结论里归因于扰动。
