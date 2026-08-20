# T61 调研报告：DeepSeek Harness（dsh）源码实读

> 2026-08-20。方法：克隆仓库（0.1.0-rc.8，MIT）读源码与文档，逐条回答工单六问。证据全部带文件路径。
> 老板预给两答案已验证：①breaking changes 不计入否决（官方明示预览期随意 rename/repackage，仅记录）；②**模型可自配、可锁 flash——源码证实**（`packages/bundle/base/cordis.patch.yml:63-67` 默认就是 `deepseek-v4-flash`；Python SDK 默认值同为 flash，`python/sdk/.../api.py:23`；还能锁思考档，配错直接加载失败）。

---

## 六问的答案

### 1. 插件机制实况——"一切皆插件"属实，且颗粒度极细

没有特权核心：模型适配器、工具注册表、session 日志、agent loop 本身全是插件（`docs/architecture.md:11-13`）。定制"专用调研智能体"的实际长相：一个 profile = 基础包 + 一份 patch 文件——写调研人设、挂搜索/抓取工具、钉死 flash、关掉不要的工具、加自写的白名单策略插件。拦截点齐全且不靠改主循环：工具执行前可 allow/deny/ask、执行后可改写结果、agent 每步前可拒发请求（`docs/tool-execution-pipeline.md`）。**插件须用 TS/JS 写；但 Python 也能坐上拦截点**——官方有 hooks 桥，把外部 Python 脚本映射进工具执行前/每步前等卡口（`packages/hooks/hooks-claude-code/README.md:37-49`）。

### 2. 三圈制度兼容性

- **议程注入 ✓**：CLI 一次性任务、Python SDK（`Session.run()` 返回完整结果与事件流）、进程内 inject、还有原生 `schedule` 包（durable 定时任务回到原 session——"持续追踪名单"有原生载体）。
- **预算闸 △（机制都在，现成插件没有）**：调用前可查（tokenMeter 预算压强，`docs/subsystems/token-meter.md`）、可硬停（pre-step 里 reject 即不发请求）——自写"经费卡插件"几十行 TS 或一个 Python hook。全仓无内置预算帽插件。
- **产出对账 ✓（最强的一圈）**：铁律"模型可见即已落盘"，append-only 事件日志（含 raw chunk 级）、JSONL/SQLite 持久化、崩溃不截断恢复、SQLite 全文检索血缘。比我们"主张-原文对账"需要的粒度还细；缺的只是对账器本身（我们的领域逻辑，本就该我们写）。

### 3. 接线方式——官方 Python SDK，目标机不需要装 Node

`python/` 是官方 SDK：`deepseek-harness-sdk`（PyPI）+ runtime wheel（打平的单文件 Node 可执行）。通信 = 子进程 stdio 上的 JSON-RPC。平台注意：wheel 只有 linux x86_64/aarch64 和 **macOS arm64**（本机 MacBook Air 正好适用）。运维面≈一个外部命令。

### 4. 镣铐承接

- **可靠代码强制**：工具白名单（组合即白名单 + 执行前按名/按域名 deny）、来源分级打标（执行后插件自动贴标签）、Python 校验器经 hooks 桥直接坐卡口。
- **只能进提示词**：事实/解读分离、时点纪律语义、needs_data_confirmation——这些是领域语义，两条路线下都得我们自己写（dsh 里是 prompt section，自建里是校验器；无差别）。

### 5. 风险面（除老板已豁免项）

- 遥测**默认关闭**，需显式开；但 llm-deepseek 每次请求向目标网关发匿名归因头（指官方 API 无所谓，指自建网关会收到）。
- 供应链：npm 传递闭包大（lock 两万行），缓解件齐（Cordis 源码 vendor 钉 SHA、CI 门禁含 per-file 100% 覆盖率、Dependabot 带 cooldown）。
- 预览期 session 存档格式无兼容承诺——我们的对账若依赖它的 JSONL 格式，升级可能要适配（老板已豁免，记录备查）。
- 维护活跃度：浅克隆看不到提交史，只有 CI/Dependabot/Discord 存在作证——**未找到**可靠证据，留作开放点。
- 成本口径新项：dsh 的搜索本身是一次完整模型调用（比纯检索端点贵），预算卡要把搜索算进去。

### 6. 对比自建小循环的真实增量

dsh 给的是**运行时底盘**：持久化、上下文压缩、子代理、定时调度、沙箱、审计日志、双语言 SDK、三个搜索 provider。它没有也不该有的是**调研方法论**——四条镣铐、对账器、框架映射这些语义层，两条路线都得我们自己写，区别只是写成 TS 插件/Python hook（dsh）还是长在自己循环里（自建）。我们原型已有的 planner→工具→reader→校验循环，dsh 的泛化 loop + plan-mode + subagent 全部覆盖且更深（自带长程上下文治理：压缩、外置、修剪——这正是原型到"长程调研"最缺的一段）。

---

## 对 T60 设计稿的影响评估

**三圈制度一圈都不用改设计**——议程账本是我们的账本（dsh 只是被注入任务），经费卡换个实现位置（dsh 插件/hook，几十行），对账器读 dsh 的 session 日志（粒度比原型自落盘还细）。T60 的纸上考卷与机制设计在两条路线下都成立；变的只是"循环谁来转"：自建循环（几百行但长程治理要自己写）vs dsh 底盘（自带长程治理，插件要写 TS 或走 Python 桥）。

## 方向建议（供老板裁决，不代拍板）

**倾向：混合——事件层 agentic 运行时用 dsh 底盘，语义层（镣铐、对账、框架映射）保持我们的 Python 资产，经 hooks 桥/MCP 接入。**

理由三条：
1. 我们最缺的是"长程多轮调研的上下文治理"（压缩/外置/子代理/调度）——这是 dsh 的主业、自建的最大工程量；语义镣铐两边都要自己写，不构成选自建的理由。
2. 老板担心的"重复造轮子"准确命中：自建要重写的恰恰是 dsh 已经写好的通用底盘。
3. 接线成本实测很低（官方 Python SDK、本机平台支持、一个子进程）。

**收尾前建议先做一个探针**（半天量级、花一次小钱）：用 Python SDK 跑一个迷你真实任务（如"Anthropic ARR 最新披露是多少、出处在哪"），验证三件事——接线真能转、session 日志够我们对账用、经费卡插件能拦住。探针过了再正式定方向，比纯纸面拍板稳。

## 开放点

- 维护活跃度证据不足（建议探针期间观察其 Discord/提交频率）。
- 遥测归因头在自建网关场景的外发面，接线设计时回避（指官方 API 即无此虑）。
