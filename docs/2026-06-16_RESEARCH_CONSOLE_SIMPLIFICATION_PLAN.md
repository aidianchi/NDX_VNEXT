# 研究控制台重做计划：从参数面板改成用户启动器

更新日期：2026-06-16

本文用于在全新对话中直接实施控制台重做。目标不是修补旧页面，而是把 `NDX vNext 研究控制台` 改成一个普通用户可以放心使用的简洁启动器。

## 一句话目标

控制台第一屏只回答六个问题：

1. 本次怎么运行。
2. 用不用已有数据。
3. 是否回测。
4. 是否收集新闻材料。
5. 什么时候开始。
6. 跑完去哪里看报告和日志。

除这些以外的开发者细节、命令预览、人工覆盖、Trendonify、workbench 模块多选、sidecar 和数据源健康表，都不得在主界面常驻。

## 背景判断

当前控制台的问题不是局部排版问题，而是产品定位混乱：

- 它把用户启动器、开发命令面板、人工数据表、sidecar 管理器、产物索引和安全说明混在一页。
- `运行模式`、`对象日期`、`模型流程`、`人工数据`、`健康审计` 的编号和显示顺序不一致。
- 首屏同时展示主按钮、多个辅助按钮、命令黑框、workbench 模块、最新 brief、workbench、run、日志和新闻产物，用户难以判断“现在该按哪个”。
- 最新 L4 Wind 主锚接入后，控制台没有明确显示 Wind 是否会触发、是否可能消耗积分、如何关闭。

因此本次应重做主界面，而不是继续在旧结构上增加说明。

## 目标用户体验

理想第一屏大致如下：

```text
NDX vNext 研究控制台

运行模式：[完整运行 / 仅收集数据 / 用已有数据分析]

末次数据：
数据日期：2026-06-16
收集时间：2026-06-16 15:20
文件：data_collected_xxx.json

[ ] 是否回测
    回测日期：[ yyyy-mm-dd ]

[ ] 收集新闻材料

[开始运行]

状态：尚未运行

[打开最新报告] [打开最新 workbench] [打开最新日志]
```

用户不需要理解 Trendonify、sidecar、manual JSON、命令白名单、legacy HTML、workbench modules 才能跑系统。

## 主界面保留内容

### 1. 运行模式

主界面只保留三种模式：

| 模式 | 含义 | 主按钮文案 |
| --- | --- | --- |
| 完整运行 | 重新收集数据，运行完整 vNext，生成 native brief 和 workbench | 开始完整运行 |
| 仅收集数据 | 只更新数据快照，不跑模型，不生成报告 | 开始收集数据 |
| 用已有数据分析 | 使用末次收集的数据继续分析，不重新采集 | 开始分析已有数据 |

不要把以下内容作为主运行模式：

- 只生成 brief
- 只生成 workbench
- 查看日志
- 视觉回归
- Trendonify sidecar

这些属于结果入口、开发工具或高级功能。

### 2. 末次数据摘要

当存在最新数据 JSON 时，主界面必须显示：

- 数据文件名。
- 数据日期。
- 收集时间。
- 是否为回测数据。

选择 `用已有数据分析` 时，要明确提示：

```text
将使用这份数据，不会重新采集。
```

如果没有可用数据，`用已有数据分析` 应显示不可用或要求先运行 `仅收集数据`。

### 3. 是否回测

回测不是运行模式，而是运行条件。

主界面放一个清楚的开关：

```text
[ ] 是否回测
```

关闭时隐藏日期选择。

打开后显示：

```text
回测日期：[日期选择]
```

旁边用短句说明：

```text
回测会阻止当前网页、当前 Wind 快照和当前成分股基本面冒充历史当时可见数据。
```

这句话很重要，因为它体现 vNext 的数据边界，不是普通日期过滤器。

### 4. 收集新闻材料

主界面只保留一个新闻选项：

```text
[ ] 收集新闻材料
```

默认不勾选。

说明文字：

```text
新闻材料只作为旁证，不直接进入 L1-L5 主证据。
```

不要把新闻写成“增强分析”或“解释市场原因”，避免越权。

### 5. 开始运行按钮

主界面只保留一个最醒目的主按钮，文案随运行模式变化：

- 完整运行：`开始完整运行`
- 仅收集数据：`开始收集数据`
- 用已有数据分析：`开始分析已有数据`

`刷新状态` 默认自动进行，不作为主按钮。

`取消任务` 只在任务运行中出现。

`生成运行命令` 放入高级设置，不放在主按钮旁边。

### 6. 运行状态

状态区紧跟主按钮，显示：

- 尚未运行。
- 正在运行。
- 当前步骤。
- 成功。
- 失败原因。
- 日志路径。

颜色只承担辅助作用：

- 灰色：尚未运行。
- 蓝色：运行中。
- 绿色：成功。
- 黄色或红色：需要注意或失败。

不要让黑色命令框成为主状态。

### 7. 最新入口

主界面保留三个跳转：

- 打开最新报告。
- 打开最新 workbench。
- 打开最新日志。

历史列表、更多报告、更多 run 目录默认折叠到 `更多产物`。

## 主界面移除内容

### Trendonify

Trendonify 暂时不出现在主界面。

原因：

- Wind 已经成为 L4 实时主锚。
- Trendonify 当前不再是主流程必需数据。
- 继续放在控制台会误导用户，以为它仍是关键步骤。

如果保留入口，只能放入高级工具，并且默认折叠。

### workbench 模块多选

交互工作台模块默认全选，不在主界面提供逐项勾选。

原因：

- workbench 是标准配套输出。
- 普通用户不应每次思考价格技术、波动信用、利率估值、广度集中度、流动性是否要选。
- 如确需调整，放入高级设置。

### 人工数据大表

人工数据不在主界面展开。

主界面最多显示：

```text
人工覆盖：未启用 / 已启用
```

详细 PE/PB/PS/ERP/收益率输入全部放入 `高级设置 > 人工覆盖`，默认折叠。

### 命令预览

命令预览放入 `高级设置 > 开发者命令`，默认折叠。

普通用户不需要阅读 `python3 src/...` 才能运行。

## 高级设置

高级设置默认折叠，包含：

1. 模型选择。
2. Wind L4 开关。
3. 人工覆盖。
4. workbench 模块。
5. 命令预览。

### Wind L4 开关

默认开启：

```text
Wind L4 主锚：开启
```

说明：

```text
开启后会使用 Wind 获取 NDX 估值和风险溢价，可能消耗积分。
关闭后使用降级路径。
```

关闭时对应：

```text
NDX_DISABLE_WIND_L4=1
```

技术实现建议不要把环境变量拼进命令字符串。更好的做法是让 control service 的 `/run` 请求支持白名单环境覆盖，只允许 `NDX_DISABLE_WIND_L4` 这一个变量。

## 技术改动范围

### `src/research_console.py`

主要重写：

- HTML 结构。
- CSS 布局。
- 前端 JS 状态逻辑。

保留：

- self-contained HTML 生成方式。
- artifact 链接逻辑。
- manual data 读写能力，但移入高级设置。
- control service 调用方式。

删除或移入高级区：

- Trendonify 主界面入口。
- workbench 模块主界面多选。
- 命令黑框主界面常驻。
- 大面积人工数据输入表主界面常驻。
- 数据源健康主界面常驻。

### `src/control_service.py`

增加安全环境覆盖能力：

- `/run` payload 可包含 `env_overrides`。
- 只允许白名单变量：`NDX_DISABLE_WIND_L4`。
- 只允许值：`"1"` 或空值。
- 执行子进程时把该变量合入环境。

不得开放任意环境变量，避免把本地执行入口变成危险接口。

### `src/console_run_all.py`

原则上不需要新增 Wind 参数；它继承 control service 传入的环境即可。

如果后续希望命令行也能显式关闭 Wind，可以再加 `--disable-wind-l4`，但第一轮不必做。

### `tests/test_research_console.py`

更新断言：

- 断言主界面有三种运行模式。
- 断言有末次数据摘要。
- 断言有 `是否回测` 和回测日期。
- 断言新闻选项默认存在但不默认启用。
- 断言主界面有一个主要开始按钮。
- 断言 Trendonify 不在主界面常驻。
- 断言 workbench 模块多选不在主界面常驻。
- 断言命令预览在高级设置中。
- 断言 Wind L4 开关在高级设置中。

### `tests/test_open_research_console.py`

更新 ready markers，避免旧控制台误判为可用。

新 ready markers 应包含：

- `NDX vNext 研究控制台`
- 新控制台版本号，例如 `console_simple_launcher_v1`
- `运行模式`
- `开始完整运行`
- `是否回测`
- `收集新闻材料`
- `打开最新报告`

旧版 stale markers 应包含：

- `采集 Trendonify`
- `Trendonify sidecar 标记为信任`
- `交互工作台模块`
- `高级 JSON 预览` 出现在主界面常驻时

### 新增或更新 control service 测试

需要测试：

- `env_overrides={"NDX_DISABLE_WIND_L4": "1"}` 可通过。
- 其他环境变量被拒绝。
- `NDX_DISABLE_WIND_L4` 的非法值被拒绝。
- 子进程执行时环境变量被传入。

## 视觉设计要求

控制台应该像一个安静、可靠的研究启动台，而不是参数后台。

设计方向：

- 第一屏有明确主按钮。
- 卡片数量少，不嵌套卡片。
- 文案短，按钮含义直接。
- 页面留白足够，不追求把所有信息塞进首屏。
- 不使用大面积花哨渐变。
- 不用一堆同权重按钮。
- 不让命令行黑框成为视觉中心。

桌面布局：

```text
左侧：运行设置
右侧：末次数据、状态、最新入口
底部：高级设置折叠
```

手机布局：

```text
运行模式
末次数据
是否回测
是否收集新闻
开始运行
状态
最新入口
高级设置
```

手机 390px 宽度下不得出现半截按钮、横向滚动或需要读长命令的主流程。

## 交互细节

### 运行模式切换

选择不同模式时：

- 主按钮文案变化。
- 状态说明变化。
- `用已有数据分析` 会强调使用末次数据。
- 如果没有末次数据，`用已有数据分析` 不可直接开始。

### 回测开关

打开回测：

- 显示日期选择。
- 命令加 `--date YYYY-MM-DD`。
- 状态说明显示回测数据边界。

关闭回测：

- 隐藏日期选择。
- 不传 `--date`。

### 新闻开关

打开新闻：

- 命令加 `--enable-news`。
- 状态说明强调新闻只生成旁证。

关闭新闻：

- 不传 `--enable-news`。

### Wind 开关

高级设置里关闭 Wind：

- `/run` payload 加 `env_overrides={"NDX_DISABLE_WIND_L4": "1"}`。
- 页面提示“本次不会调用 Wind L4 主锚”。

开启 Wind：

- 不传 `NDX_DISABLE_WIND_L4`。
- 页面提示“本次可能消耗 Wind 积分”。

## 生成命令规则

三种主模式对应命令：

### 完整运行

```bash
python3 src/console_run_all.py --models deepseek-v4-flash,deepseek-v4-pro --workbench-modules price_technical,volatility_credit,rates_valuation,breadth_concentration,liquidity --skip-legacy-report
```

如果回测：

```bash
--date YYYY-MM-DD
```

如果收集新闻：

```bash
--enable-news
```

### 仅收集数据

```bash
python3 src/main.py --models deepseek-v4-flash,deepseek-v4-pro --collect-only --skip-report --disable-charts
```

如果回测：

```bash
--date YYYY-MM-DD
```

如果收集新闻：

```bash
--enable-news
```

### 用已有数据分析

```bash
python3 src/main.py --models deepseek-v4-flash,deepseek-v4-pro --data-json <latest_data_json> --skip-report --disable-charts
```

如果回测已打开且选择日期，也可以加 `--date`，但必须在 UI 上提示：实际数据边界仍以所选 JSON 为准，不能用日期假装数据已被重新采集。

## 验收标准

功能验收：

- 控制台可由 `python src/open_research_console.py` 打开。
- 三种运行模式都能生成正确命令。
- `是否回测` 打开后能选择日期，并正确传 `--date`。
- `收集新闻材料` 默认关闭，勾选后才传 `--enable-news`。
- Wind 默认开启；高级设置关闭后能安全传入 `NDX_DISABLE_WIND_L4=1`。
- 最新报告、最新 workbench、最新日志入口可见。
- 没有末次数据时，`用已有数据分析` 不允许误跑。

视觉验收：

- 桌面首屏能一眼看懂“怎么运行”和“按哪里开始”。
- 手机 390px 宽度无横向滚动、无半截按钮。
- 主界面没有 Trendonify 常驻入口。
- 主界面没有 workbench 模块多选。
- 主界面没有大段命令黑框。
- 主界面没有人工数据大表。

测试验收：

```bash
.venv/bin/python -m pytest -q tests/test_research_console.py tests/test_open_research_console.py tests/test_console_run_all.py
```

如果改了 control service 环境覆盖，再运行相关 control service 测试。

浏览器验收：

- 用 Chrome 打开 `http://127.0.0.1:8765`。
- 截桌面首屏。
- 截 390px 手机宽度首屏。
- 人眼确认首屏简洁、按钮清楚、无溢出。

## 非目标

本次不要做：

- 重写 vNext 分析主链。
- 改 Wind 数据采集函数。
- 新增 Trendonify 主流程。
- 把新闻升级为 L1-L5 主证据源。
- 把控制台改成完整前端框架项目。
- 修复所有历史报告入口。

## 新对话开工指令

如果在全新对话中实施，可直接使用以下指令：

```text
请阅读 AGENTS.md、NEXT_STEPS.md，以及 docs/2026-06-16_RESEARCH_CONSOLE_SIMPLIFICATION_PLAN.md。
按计划把研究控制台从参数面板重做成简洁用户启动器。
不要修改 vNext 分析主链，不要新增 Trendonify 主流程。
重点改 src/research_console.py、src/control_service.py 和相关测试。
完成后运行控制台测试，并用 Chrome 检查桌面和 390px 手机宽度首屏。
```

