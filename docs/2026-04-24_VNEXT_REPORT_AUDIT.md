# vNext 报告质量审计

日期：2026-04-24
审计对象：

- 新版 smoke 报告：`C:\ndx_vnext\output\reports\ndx_report_v9_20260424_075418.html`
- 新版开启图表报告：`C:\ndx_vnext\output\reports\ndx_report_v9_20260424_203256.html`
- 修复后新版报告：`C:\ndx_vnext\output\reports\ndx_report_v9_20260424_205109.html`
- 旧版基线报告：`C:\ndx_agent\output\reports\ndx_report_v9_20260323_222444.html`

## 结论

结论分两层：

1. `ndx_report_v9_20260424_075418.html` 确实是低质量产物，而且**不能**作为新版最终质量基线，因为它是我在 smoke test 时以 `--disable-charts` 生成的测试产物。
2. 但即使补跑了开启图表的 `ndx_report_v9_20260424_203256.html`，新版报告质量仍然明显落后于旧版。这说明问题**不只是测试时偷懒关图表**，而是 vNext 认知链到 legacy 展示层之间发生了真实回归。

换句话说：

- `075418` 是“人为降低展示质量后的测试产物”
- `203256` 才是更公平的新旧对比对象
- 但 `203256` 依然不达标

## 修复结果更新

在完成兼容层修复后，重新使用默认 DeepSeek 主链路生成了：

- `C:\ndx_vnext\output\reports\ndx_report_v9_20260424_205109.html`

这次产物和旧版基线相比，关键展示指标已经回到同一量级：

| 报告 | 文件大小 | script 数 | details/summary 数 | 指标叙事数 | 推理过程块数 |
|---|---:|---:|---:|---:|---:|
| 修复前 `203256` | 5,248,058 B | 50 | 23 | 25 | 0 |
| 修复后 `205109` | 5,353,517 B | 50 | 57 | 34 | 34 |
| 旧版基线 `222444` | 5,951,940 B | 50 | 57 | 34 | 34 |

这说明本次修复已经解决了最主要的报告回归：

- `indicator_narratives` 恢复为全量 34 个指标
- `reasoning_process` 通道恢复，旧报告里的折叠推理块重新出现
- `details` 交互层级从 23 恢复到 57，和旧版基线持平

结论更新为：

> `075418` 和 `203256` 的质量批评成立；但在 `205109` 这次修复后，vNext 报告已经从“只能证明跑通”提升到了“可与旧版做同层级对比”的状态。

## 关键证据

### 1. 体量与展示资产

| 报告 | 文件大小 | script 数 | details/summary 数 | 文本长度 |
|---|---:|---:|---:|---:|
| 新版 smoke `075418` | 35,582 B | 0 | 7 | 5,644 |
| 新版开图表 `203256` | 5,248,058 B | 50 | 23 | 10,452 |
| 旧版基线 `222444` | 5,951,940 B | 50 | 57 | 17,974 |

判断：

- `075418` 的确“垃圾”，因为图表、脚本、展开层级几乎被砍空了。
- 但 `203256` 与旧版相比，虽然脚本和图表已经回来了，文本密度和交互层级仍明显不足。

### 2. 推理过程块完全丢失

旧版报告里：

- `indicator_narratives` 的单项结构包含 `metric`、`narrative`、`reasoning_process`
- `reasoning_process` 总计 34 条
- HTML 中有 34 个“查看AI的推理过程”折叠块

新版报告里：

- `logic_vnext.json` 的 `indicator_narratives` 只有 `metric` 和 `narrative`
- `reasoning_process` 数量为 0
- 开图表后的新报告里“查看AI的推理过程”数量仍为 0

这不是观感问题，而是**旧展示层的核心信息通道被直接断掉了**。

### 3. 指标覆盖数量回退

旧版 `logic`：

- `layer_1`: 8
- `layer_2`: 9
- `layer_3`: 6
- `layer_4`: 2
- `layer_5`: 9
- 合计：34

新版 `logic_vnext.json`：

- `layer_1`: 6
- `layer_2`: 7
- `layer_3`: 2
- `layer_4`: 2
- `layer_5`: 8
- 合计：25

判断：

- 新版报告并不只是“少了图表”，它连可展示的指标叙事总量也减少了。
- 尤其是 L3 从 6 降到 2，L2 从 9 降到 7，信息密度明显下降。

## 根因分析

### A. smoke test 时人为关闭图表

这是 `075418` 特别差的直接原因。

我当时为了先打通认知链，使用了：

```powershell
python src\main.py --models deepseek-chat,kimi-for-coding --skip-report --disable-charts
```

这会直接让报告生成器不嵌入 Plotly 图表。

所以：

- `075418` 的糟糕程度，有一部分是我故意把图表层关掉了
- 这个产物适合作为“链路通了”的证明，不适合作为“报告质量合格”的证明

### B. `legacy_adapter.py` 过薄，破坏了旧报告契约

当前 `src/agent_analysis/legacy_adapter.py` 只做了最薄映射：

- 把 `LayerCard.core_facts` 拼成 `metric + narrative`
- 没有提供 `reasoning_process`
- 没有补齐旧展示层真正依赖的更丰富叙事字段

这导致：

- 旧报告页面中最重要的“AI 推理过程”区域完全失效
- 页面虽然能渲染，但只剩“结论摘要”，缺少“为什么”

这是当前最主要的回归根因。

### C. vNext 中间产物本身不携带“报告级解释粒度”

当前 vNext 的主产物重点是：

- `LayerCard`
- `BridgeMemo`
- `ThesisDraft`
- `FinalAdjudication`

它们更偏“结构化推理链”，而旧版 HTML 展示层吃的是更细的“指标级叙事 + 指标级 reasoning_process”。

现在的问题不是模型一定分析差，而是：

- vNext 产物适合做治理和裁决
- 但不直接适合喂给旧版富展示 HTML

这属于**展示契约断层**。

### D. packet / orchestrator 当前更偏“先跑通”，而不是“先喂满报告”

本次第一版实现的目标优先级是：

1. 链路可执行
2. JSON 结构合法
3. 中间产物完整落盘
4. legacy HTML 先能吃进去

所以当前实现策略偏保守：

- `packet_builder.py` 对事实做了收缩整理
- `orchestrator.py` 的约束是先把 `LayerCard/Bridge/Thesis/Final` 稳定产出来
- 还没有针对“旧报告需要多少可视化解释材料”做专门优化

这不是 bug，而是阶段性取舍；但对“报告质量”来说，它现在就是不够。

### E. 数据层仍有非展示性问题，但不是本次报告崩坏的主因

这次运行里还看到几个数据面问题：

- `WTREGEN` 单位/范围校验仍持续报警
- `^VIX` 在图表生成时出现边界日期抓取异常
- L4 很大程度依赖 `manual_data` 覆盖，而非纯自动采集

这些会影响报告可信度，但它们不是“新版 HTML 看起来远弱于旧版”的第一根因。
第一根因仍然是：**展示层所需的解释资产没有被传回来。**

## 判断：这是“为了先跑通而简化”，还是“版本出了大问题”？

答案是：两者都有，但权重不同。

### 属于“为了先跑通而简化”的部分

- smoke 报告 `075418` 关掉了图表
- 主链路先追求结构合法与落盘完整
- adapter 先做了最小兼容，而不是高保真兼容

### 属于“当前版本确实存在真实问题”的部分

- 即使开启图表，报告仍明显弱于旧版
- `reasoning_process` 全量丢失
- 指标叙事覆盖减少
- `legacy_adapter.py` 远没有达到“高保真 legacy 兼容”的程度

所以不能用“只是测试产物”来为当前 vNext 报告质量开脱。
更准确的说法是：

> 第一版主链路已经跑通，但报告层兼容只做到了“能渲染”，还远没做到“可替代旧版”。

## 整改优先级

### P0：修复 legacy 报告契约

目标：让新版逻辑重新喂回旧报告最重要的解释字段。

必须补：

- `indicator_narratives[].reasoning_process`
- 更丰富的 `market_regime_analysis`
- 更完整的 layer 级 key drivers 和冲突说明

### P1：把“报告级解释资产”前移到 vNext 产物

不要再指望 `legacy_adapter.py` 事后脑补。
应该在 layer / bridge / thesis 阶段就直接产出：

- 指标级 narrative
- 指标级 reasoning_process
- layer 级 key drivers
- 冲突解释文本

### P2：把 chart-disabled 产物从质量对比中剔除

今后 smoke test 可以继续关图表，但：

- 这类产物必须明确标记为 smoke-only
- 不能再拿来当质量完成版

### P3：加入报告回归测试

至少增加以下检查：

- `indicator_narratives` 总数不得低于基线阈值
- `reasoning_process` 不得为空
- 开图表报告必须包含 Plotly script
- HTML `details` 数量不能退化到明显异常水平

## 我的判断

这次用户的质疑是成立的。

如果把 `075418` 当成新版报告成品，那它确实“不堪”；
如果把 `203256` 当成公平对比对象，它也仍然显著弱于旧版。

因此当前状态应被定义为：

> vNext 第一版主链路已跑通，但 report compatibility 只完成了最低可用级，尚未达到旧版质量基线。

下一步不应该再假装“已经兼容完成”，而应该明确进入：

> **report fidelity repair（报告保真修复）阶段**
