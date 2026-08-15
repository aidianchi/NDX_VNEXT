# T-DSH B面 · DSH 到底是什么（只读源码/本机材料剖析）

> 日期：2026-08-15（会话当天）
> 性质：只读调研。未改动任何现有文件；只新建本文件。
> 材料来源（全部为本机文件，未引用任何网络材料）：
> - DSH 安装目录：`/Users/aidianchi/.dsh/`。其中 `profiles/node_modules/@deepseek-ai/*` 是符号链接，真实路径指向 `/Users/aidianchi/.npm/_npx/1e7f6d9597241db0/node_modules/@deepseek-ai/*`；本文引用的行号按该真实路径读出，经 `~/.dsh/profiles/node_modules/@deepseek-ai/...` 读同一文件。
> - DSH 会话记录：`/Users/aidianchi/Downloads/dsh-session-session-db0ea455-a678-4e78-902b-5e6fed75e2a9.zip`，已解压到 `/tmp/dsh_session_readonly/session.jsonl`（只读检查）。
> - 本仓库：`investigation_reports/20260813_architecture_northstar_revisit/01_架构校准探讨底稿.md` Q5、`04_T-DSH_DSH当编排器_工单骨架.md`；`src/agent_analysis/orchestrator.py`；`src/main.py`。
> - 版本：所有 @deepseek-ai 包版本 `0.1.0-rc.6`；Cordis `4.0.1`（可由 `node -e "console.log(require('<pkg>/package.json').version)"` 复跑）。

---

## 0. 一句话总判断（供快速阅读）

DSH 是一个 **Cordis 插件框架上的"会话式 Agent 运行时"**：核心只有一个"调模型→跑工具→重复"的 Agent Loop，编排能力（子代理、工作流、目标循环、Ralph、定时、后台任务）全部是挂在事件/服务扩展点上的**插件**。它原生提供的是**上下文可见性隔离 + 文件写效果沙箱 + 事件溯源会话日志**，不是"同一 effective_date 重跑可对比"的**批处理管线**，也没有 `effective_date`/回测/时间窗口概念。它可以用 `dsh --profile headless "任务"` 做一次性无人值守运行，但"产物落 timestamped 目录、事后逐站 grep 隔离证明"要靠外部脚本或自定义插件补。

---

## 1. B面1：编排模型、隔离边界、可复现性

### 1.1 底层：Cordis 插件/服务/事件框架

DSH 不是一段固定流水线，而是 **Cordis 插件树**。证据：

- `cordis/README.md:3`：*"Cordis is a TypeScript plugin framework for applications that need explicit dependency injection, scoped services, lifecycle-managed cleanup, and optional configuration-driven loading."*
- `dsh-base/README.md:5`：`cordis.patch.yml` 作为每个 profile 的第一层 patch，"inserts every base plugin row — model adapters, … tools, persistence, policy, settings/credentials, telemetry, and host-level subagent providers"。
- `dsh-base/cordis.patch.yml:15` 起是全部基础插件行的 `insert` 清单；关键行：`99`（session-persistence-jsonl）、`118-119`（session-query-sqlite 默认 `path: ':memory:'` + `openAt: never`）、`170-176`（sandbox-local + sandbox-policy 默认 `workspace-write`、`workspaceRoot: process.cwd()`）、`179`（bash-sandbox）、`211`（tool-bash）、`257`（goal）、`260`（goal-round-driver）。
- `dsh-agent-loop/README.md:7`：*"This is the only package in the harness that contains concrete loop logic. Everything else is an abstract service or a plugin against extension points — new behavior goes into plugins, not here."*
- `dsh-agent-loop/README.md:74-82`：所有超出"call the model, run the tools, repeat"的机制——压缩、重试、沙箱/权限、**子代理**、**持久化**、UI——都是监听 `agent/*`/`session/event` 等事件的插件。子代理明确"implemented outside the loop as `ctx.subagents` providers"。

结论：DSH 的"编排模型"不是单一模型，而是**插件/服务/事件总线上的一组可选编排插件**（见下）。

### 1.2 六种编排机制盘点

| 机制 | DSH 里的形态 | 隔离边界 | 可复现性 |
|---|---|---|---|
| 插件/服务（Cordis） | 一切功能都是插件，服务经依赖注入，事件驱动 | 插件 fiber 卸载时回收注册；作用域（全局/agent 级） | 配置即 patch 文件，可重建同构 runtime；模型行为不可复现 |
| 子代理 | `ctx.subagents` 服务 + `spawn`（全新会话）/`fork`（继承父已完成轮次）/continuable（可续接子代理） | 上下文可见性由 provider 决定；权限在委派边界固定 | 子代理有独立 session 日志，可事后重放；无确定性重跑保证 |
| 工作流 | `dsh-tool-workflow`（模型可见 `workflow` 工具）+ `dsh-workflow`（seam）+ `dsh-workflow-worker-thread`（每 run 一个 Node worker 执行模型写的 JS 编排脚本，`agent()` 桥接回子代理） | worker 非安全边界；子代理仍走 subagent 隔离；脚本无 fs/网络注入但可逃逸 | **无 journaling/resume**（见下） |
| 目标循环 | `dsh-goal`（事件溯源 same-session goal 状态）+ `dsh-goal-round-driver`（agent 空闲时自动排下一轮 `<goal_round>`） | 同一会话内顺序执行，共享历史与 workspace | goal 状态落 session 日志，可 replay；轮次只按计数预算 |
| Ralph 循环 | `dsh-tool-ralph`：固定工作流，每轮一个 **fresh** 子代理，workspace 是唯一长期记忆 | 每轮全新子代理、不继承父对话；workspace 共享 | 前台一次性；无 checkpoint |
| 后台任务/定时 | `dsh-jobs`/`dsh-jobs-local`（进程内 job registry）+ `dsh-schedule`（after/at/every 提醒，写 session 日志） | 进程内；owner 隔离 | 进程重启即失（jobs 明确 in-process） |

关键证据行：

- 子代理：`dsh-subagent/README.md:5-7`（seam 与 provider 注册表）、`57`（*"`inheritsParentContext` is descriptive rather than enforceable. It says only whether the child sees completed parent conversation history (`fork` does; `spawn` and the out-of-process one-shot providers do not), not whether it inherits tools, services, or authority."*）、`61`（委派边界固定子代理权限：`captureDelegatedPolicyOverrides` 快照父 sandbox override、子代理 approval 钉死 `'never'`）。
- spawn/fork：`dsh-subagent-spawn-in-process/README.md:5`（*"sees no parent conversation history"*）、`:29`（*"receives zero parent conversation messages"*）；`dsh-subagent-fork-in-process/README.md:5`（*"seeded with the parent's completed conversation turns"*）、`:11`（前缀到最后一个 `turn/end`；父无已完成轮次则等同 fresh spawn）、`:60`（seed 是一次性快照，无实时共享）。
- 工作流：`dsh-workflow/README.md:5`（*"executes a model-written orchestration script that can fan out subagents"*）、`:17`（`WorkflowStartRequest { meta, script, args?, subagentProvider?, maxTotalAgents?, parent, signal? }`）、`:55-57`（**"Foreground collection only"**；**"No journaling or resume — scripts, child progress, and intermediate values are not checkpointed, so a process restart cannot continue a run"**；**"No saved or nested workflows"**）。worker 隔离：`dsh-workflow-worker-thread/README.md:13`（*"`node:vm` inside a worker is an API-shaping mechanism, not a security boundary: an escaped script can recover Node capabilities"*）、`:120`（同样结论）。
- 目标循环：`dsh-goal/README.md:5`（event-sourced same-session goal state）、`:28`（activation 不持久化，resume 后不自动续跑，需显式 resume）、`:55-56`（**"Round-count budget only"**；**"No independent evaluator"**）；`dsh-goal-round-driver/README.md:24`（空闲时 reserve `roundsStarted+1` 并排 `<goal_round>` prompt）、`:60`（无独立评估者）。
- Ralph：`dsh-tool-ralph/README.md:5`（固定前台工作流、每轮 fresh 子代理）、`:88-91`（**"Completion is worker self-declaration"**；**"Foreground only — there is no job id, background collection, process-resume checkpoint, scheduler, or wall-clock start policy"**；workspace 是唯一跨轮长期记忆）。
- 后台任务/定时：`dsh-jobs/README.md:40`（**"The contract is in-process"**）；`dsh-schedule/README.md:5`（future live root Agents 的持久提醒工具，`after`/`at`/`every`）。

### 1.3 隔离边界：三层，但都不是"分析站"级隔离

DSH 原生隔离有三层：

1. **上下文可见性（子代理 spawn/fork）**：只决定"孩子看不看得到父对话"，见上。它不提供"L1-L5 各站只能看到自己那一层材料"的领域级隔板——那要模型自己守 prompt 或外挂插件过滤。
2. **文件写效果沙箱**：`dsh-sandbox/README.md:5` 定义三档 `SandboxMode`：`read-only` / `workspace-write` / `danger-full-access`，**file effects only**；`:11` **"Same-world confinement only"**（bwrap/Landlock/Seatbelt，共享宿主内核）；`:39-40` 明确不覆盖网络/进程/syscall/设备/凭据。`dsh-fs-sandbox/README.md:15-17`（fs 写 fence 三档行为）、`:19` 标题 **"a policy fence, not a kernel boundary"**（可信代码检查模型控制的路径，非安全边界）。`dsh-bash-sandbox/README.md:14-15`（workspace-write 只写 `workspaceRoot` + `/tmp`；danger-full-access 不设防）、`:22`（**"File effects only."**）。
3. **进程/worker 隔离**：`dsh-code-runtime-worker-thread` 每 run 一个 fresh worker（README:5，"Containment, not a security boundary"）；`dsh-workflow-worker-thread` 每 run 一个 worker thread（README:5，同样非安全边界）。

本机实例：会话记录 `/tmp/dsh_session_readonly/session.jsonl` 第 1-5 行显示该会话 `session` header（cwd `/Users/aidianchi`、agentPreset `anchored-standard`）→ `permission/preset: danger-full-access` → `sandbox/mode: danger-full-access` → `approval/policy: never` → `agent-preset/selected: zero-anchored-standard`。与 `/Users/aidianchi/.dsh/settings.yaml` 的 `permission.defaultPreset: danger-full-access`、`agent-presets.default: zero-anchored-standard` 一致——**本机 DSH 实际运行在最大放权档**，文件沙箱在此配置下不设防。

### 1.4 可复现性

DSH 的"可复现"分两层：

- **强的：会话日志可重放。** `dsh-session/README.md:5`（session 是 append-only 事件源，LLM 历史是 derived）、`dsh-session-persistence-jsonl/README.md:5`（append-only JSONL，`.jsonl.zstd`）、`:45`（崩溃恢复保留有效尾部）、`dsh-session/README.md:61-63`（`request/header` 记录完整非历史请求信封，可重建"系统提示词+工具 schema+会话前缀"）。压缩后 raw log 里的影子事件仍在：`dsh-compaction/README.md:53`（*"The shadowed events remain in the raw log, so replay is deterministic."*）。
- **弱的：模型计算本身不可复现。** 没有固定 seed、没有"同输入重跑产出逐字节可比"的机制；同一 task 用 headless 跑两次得到两个新 session（`dsh-headless/README.md:7`：*"creates one fresh persisted Agent"*）。工作流明确无 checkpoint/resume（`dsh-workflow/README.md:56`），Ralph 前台一次性（`dsh-tool-ralph/README.md:89`）。

---

## 2. B面2：子代理上下文隔离 vs 本系统"落盘-grep 隔离证明"——不是同一类保证

### 2.1 DSH 的保证：运行时的"可见性/权限边界"

- spawn 子代理：全新会话，零父对话（`dsh-subagent-spawn-in-process/README.md:5,29`）。
- fork 子代理：仅继承父**已完成轮次**的前缀，一次性快照（`dsh-subagent-fork-in-process/README.md:5,11,60`）。
- 权限在委派边界固定：子代理 approval 钉 `never`，sandbox override 从父快照并写成子日志 `source:'delegation'` 事件（`dsh-subagent/README.md:61`）。
- 子代理有独立 session 日志，可事后查（`dsh-subagent/README.md:69`：local run 发布子 session id；`:91`：`subagent/start`/`subagent/end` 事件）。

这是**"孩子被允许看到/写到什么"的事前边界**（context visibility + file-effect policy）。

### 2.2 本系统的保证：事后的"每站实际收到什么"落盘证据

- `orchestrator.py:5478` `_run_stage()`：每次调 LLM 前，`_capture_prompt_attempt()`（`:5735`）把 **System Message + User Message 的完整实际文本**写成 `prompt_audit/<stage>/attempt_N.prompt.txt`（`:5770-5773`），同时落 payload、raw response、parsed/validated JSON；`_actual_prompt_text()`（`:5721`）负责拼系统约束。
- `orchestrator.py:460-494`：初始化时在 `output_dir` 下建 `layer_cards/ layer_context_briefs/ bridge_memos/ investigation_reports/ prompt_audit/` 等目录；`_save_json`（`:7482`）把每个产物写盘并登记 `stage_manifest`。
- `orchestrator.py:1162-1164` `_effective_date()` 与 `:1949-1980`（禁止 `summary_text` 出现晚于 `effective_date` 的日期）等是领域时间纪律，DSH 没有对应物（见 B面3）。
- `orchestrator.py:1044,1074,1152,1655,1991,2766` 多处 `no_backflow_rule`：反馈产物"可被审计/下游消费，但不得改写或注入 L1-L5 layer cards"——这是**信息流向**约束，靠落盘+引用白名单校验实现。

可复跑证据命令（本机已有 run）：

```bash
grep -c "effective_date" output/analysis/vnext/20260724_223804/prompt_audit/L1/attempt_1.prompt.txt
# 结果：23（该文件 2596 行，L1 站实际收到的完整 prompt 落盘可 grep）
```

### 2.3 差在哪

| 维度 | DSH 子代理隔离 | 本系统落盘-grep 隔离证明 |
|---|---|---|
| 保证类型 | 事前：孩子可见/可写的**边界** | 事后：每站**实际收到的 prompt** 可审计 |
| 粒度 | 会话/子代理级（spawn/fork 两档） | 分析站级（L1-L5、bridge、thesis、critic…每个 stage 一个目录） |
| 证据形态 | append-only session 事件日志（`user/message`、`request/header` 可重建请求信封，但**不主动存"每站实际完整 prompt"这一份文件**） | 主动写 `attempt_N.prompt.txt` + payload + raw response + validated output，直接 grep |
| grep 便利度 | 需要 session-query-sqlite FTS5；而 dsh-base 默认 `path: ':memory:'` + `openAt: never`（`dsh-base/cordis.patch.yml:118-119`），**全文检索默认关**；压缩 `.zstd` 默认不可直接行读（`dsh-session-persistence-jsonl/README.md:74`） | 纯 UTF-8 文本按站分目录，`grep` 即用 |
| 领域信息流向 | 无 L1-L5 概念，无 no-backflow 规则 | `no_backflow_rule` 多处硬约束 + 引用白名单校验 |
| 共同点 | 两者都依赖"事件/文件留痕"，都能事后查到发生了什么 | 同左 |

**结论：不是同一类保证。** DSH 给的是"运行时上下文可见性与文件权限的事前隔离"，它让"串供"变难，但不主动证明"每站看到了什么"；本系统的落盘-grep 是"事后可证明每站实际收到什么"的审计装置。两者互补：DSH 的 session 日志是很好的原始素材，但默认配置下（全文检索关、zstd 压缩、无按站目录）达不到本系统 `prompt_audit/` 的审计便利度；要等价，需要自定义插件在每个"分析站"调用前把实际 prompt 主动写成独立文件。

---

## 3. B面3：effective_date / 回测 / 时间窗口——DSH 没有

### 3.1 源码级证据

可复跑命令：

```bash
grep -rn "effective_date\|effectiveDate\|backtest\|as-of\|asof" \
  /Users/aidianchi/.dsh/profiles/node_modules/@deepseek-ai \
  --include="*.md" --include="*.js" --include="*.json" | grep -v "\.map"
# 结果：零命中（本次实测）
```

DSH 与时间相关的只有两样，都不是 `effective_date`：

1. **当前时间上下文**：`dsh-time-context/README.md:5`（*"Opt-in durable context with the current zoned time … Default compositions leave it disabled"*）——只是告诉模型"现在是几点、经过多久"，用于解读用户消息里的自然语言时间；`:15` 明确这是自然语言上下文，"not an input default at another package boundary"。
2. **未来定时提醒**：`dsh-schedule/README.md:5`（`after_seconds`/`at`/`every_seconds` 未来提醒，状态落 session 日志）——方向是"将来"，不是"回到过去某日"。

DSH 没有任何"把信息窗口锁死在某个历史日期、拒绝该日期之后材料"的机制；数据取什么日期完全由模型写的 bash/Python 命令自己决定。

### 3.2 补上要动哪一层、代价多大

时间窗口纪律的**权威实现必须在取数层（Python 数据层）**，DSH 侧只能做"上下文注入 + 审计留痕"：

| 层 | 要动的 | 代价 |
|---|---|---|
| Python 数据层（现有 Wind/pandas/SEC 采集） | 取数函数全链接受 `effective_date` 参数并强制执行"不用未来数据"；这是唯一权威闸门 | 中-大：要改采集/回测数据边界，现有 `orchestrator.py:1162-1164` 已证明本系统已这么做 |
| DSH 插件层 | 新增一个 Cordis 插件：`agent/pre-step` 时把 `effective_date` 作为上下文注入，并拦截/标记工具调用中出现的晚于该日期的日期 | 小-中：`agent/pre-step`、`tools/pre-execute` 都是现成扩展点（`dsh-agent/README.md` 与 `dsh-tools` README 有事件面）；但**只能提醒和留痕，拦不住 bash/Python 里读未来数据** |
| DSH 会话/审计层 | 复用 `request/header` 与 session 日志记录本次运行的 `effective_date` | 小：事件日志天然支持追加自定义事件类型 |
| 编排层 | 重跑时把 `effective_date` 作为任务参数传进 headless prompt 或 workflow args | 小：`dsh --profile headless "任务 effective_date=YYYY-MM-DD"` 即可 |

结论：**DSH 没有 effective_date/回测/时间窗口，补上主要动 Python 数据层（大）和 DSH 插件层（小-中）；DSH 不构成阻碍，但也帮不上忙。**

---

## 4. B面4：会话式运行时 vs 可重复批处理管线

### 4.1 DSH 本质：会话式运行时，headless 只是"一条任务的一次性会话"

- 核心是 session/turn/step 的对话循环（`dsh-agent-loop/README.md:87-91`：每步发送"渲染后的系统提示 + 可见工具 schema + 派生消息历史"）。
- 最接近批处理的 `headless` 模式：`dsh/README.md:12`（`dsh --profile headless "job"`：跑一个**fresh persisted session**，打印最终答复退出）；`dsh-headless/README.md:7`（创建全新 agent、提交 task、等 quiescence、stdout 打印最后 assistant 文本）、`:19`（**"One submitted task only"**，无交互续跑）。

### 4.2 对"一键重跑 / timestamped 目录 / 事后审计"的原生支持度

| 需求 | DSH 原生支持 | 证据 | 缺口 |
|---|---|---|---|
| 一键重跑 | 部分（headless 一条命令） | `dsh-headless/README.md:7` | 每次都是新 session；无"同一 run_id 重跑同输入"语义；模型输出不保证一致 |
| 产物落 timestamped 目录 | **无原生机制** | `dsh-tool-fs` 的 write/edit 直接写 workspace（`dsh-tool-fs/README.md:5-9`）；bash 的 workdir 默认 session cwd（`dsh-tool-bash/README.md:27`） | 目录结构完全靠模型自觉或外部包装脚本；没有 `run_dir`/`run_id` 概念 |
| 事后审计 | 中（有原始事件日志） | `dsh-session/README.md:5`、`dsh-session-persistence-jsonl/README.md:7-14`（按 `<cwd>/<session-id>/session.jsonl.zstd` 落盘）、`:45`（append-only + 崩溃恢复） | 会话日志不区分"站"；全文搜索默认关（`dsh-base/cordis.patch.yml:118-119`）；`.zstd` 默认不可直接行读（`:74`）；日志只增不删（`:75`） |
| 工作流断点续跑 | **无** | `dsh-workflow/README.md:56`（*"No journaling or resume"*） | 进程重启无法继续 |
| 后台批处理 | 进程内 jobs | `dsh-jobs/README.md:40`（*"The contract is in-process"*） | 进程重启即失；无持久队列 |

**对比本系统**：`src/main.py:290-329` 的 `build_run_dir()` 已原生支持 `backtest_date`/`run_id`/`output_dir` 生成 timestamped run 目录（实时 `%Y%m%d_%H%M%S`，回测 `{date}_outcome_test_{stamp}`），且 `orchestrator.py:7699-7730` `_load_stage_checkpoint()` 支持 `resume_from_existing` 断点续跑（校验 manifest sha256 / payload_sha256 / input_sha256 后复用产物）。DSH 要达到同等的"批处理管线"体验，需要在 headless 外包一层脚本负责建目录、传 run_id、收产物，或自研插件。

**结论：DSH 是会话式运行时；"可重复批处理管线"不是它的原生形态，只能以 headless + 外部包装 + 会话日志审计近似达成。**

---

## 5. B面5：Node.js 宿主与 Python 数据层衔接

### 5.1 主路径：bash 工具 shell out（Python 层原样保留）

- `dsh-tool-bash/README.md:19`：*"Run via `bash -c`. No state persists between calls — use `workdir`, not `cd`."*；`:21`（`timeoutMs`）；`:23`（`run_in_background`）；`:27`（workdir 默认取 session cwd，即工作区）。
- 因此 `python`/`.venv/bin/python -m ...`/Wind/SEC 脚本可以完全保留在 Python 生态，作为被 bash 调用的外部工具；DSH 不要求重写。DSH 的沙箱（workspace-write）允许写工作区与 `/tmp`，正好覆盖数据层中间产物。
- 会话环境注入：`dsh-tool-bash/README.md:31`（`DSH_HOME`、`DSH_SESSION_ID`、`DSH_SESSION_JSONL` 等 `DSH_*` 环境变量）——Python 脚本可借此知道"我在哪个 DSH 会话里跑"，便于把产物与会话日志关联。

### 5.2 次路径：Code Mode（run_code）

- `dsh-tools/README.md:16`：Code Mode 保留 `run_code` 工具；TypeScript SDK 随 `dsh-code-runtime-worker-thread` 提供；**Python renderer 内置**（生成 Python SDK 文本），但 *"a first-party `dsh-code-runtime-python` backend is delivered separately"*。
- `dsh-code-runtime/README.md:14`：*"`'typescript'` and `'python'` are the well-known values — those `dsh-tools` presents; only `'typescript'` has a published backend."*
- 本机安装清单里只有 `dsh-code-runtime` 与 `dsh-code-runtime-worker-thread`，**没有 `dsh-code-runtime-python`**（`ls ~/.dsh/profiles/node_modules/@deepseek-ai/ | grep code-runtime` 实测）。所以当前安装的 DSH 跑不了 Python run_code；Python 代码仍走 bash 调用。
- `run_code` 是"一次性程序、无跨 run 状态"（`dsh-code-runtime/README.md:35`），适合工具编排脚本，不适合承载 Wind/pandas 重数据层。

### 5.3 结论

**衔接方式 = shell out（bash 工具）为主，Code Mode 的 Python backend 未安装为辅。** Wind/pandas/SEC 数据层作为"被编排的工具"留在原处完全可行，不需要重写为 Node.js；但 DSH 只负责"调用它"，不负责"教它守 effective_date"（见 B面3）。

---

## 6. 源码缺失清单（只列事实，不拿印象补）

本机可检查的 DSH 源码 = npm 包（README + 编译产物 `lib/*.js` + 少量 `.d.ts`），**不含**：

1. **原始 TypeScript 源码 `src/*.ts`**：所有 @deepseek-ai 包只发布 `lib/` 与 README（实测 `dsh-workflow/`、`dsh-base/`、`dsh-subagent/` 等均只有 `lib/`，无 `src/`）。
2. **仓库内设计文档与 Agent Notes**：README 大量引用 `docs/subsystems/*.md`、`.agents/notes/**`（如 `dsh-workflow/README.md:60` 引用 `dynamic-workflows` note、`dsh-goal/README.md:5` 引用 goal-domain note），这些路径在 npm 安装里**不存在**（实测 `.npm/_npx/1e7f6d9597241db0` 下无 `.agents/`、无 `docs/` 目录）。
3. **`dsh-code-runtime-python` 后端包**：`dsh-tools/README.md:16` 称"delivered separately"，本机未安装。
4. **部分包的完整实现细节**：例如 `dsh-agent-loop` README 明言"package root exports only the plugin/service/config contract"、内部 driver 是 package-internal；这些内部逻辑在 `lib/index.js` 里被编译打包，可读但非原始分层源码。
5. **未证实的部分**：DSH 与 Codex/Claude Code 的 provider 集成具体行为（"load dormant"仅来自 `dsh-base/README.md:5` 一句）、除 `deepseek-official` 外的模型适配器细节，因相关 `docs/` 缺失，标记为**未证实**。

---

## 7. B面五问各一句结论

1. **编排模型**：DSH = Cordis 插件总线上的会话式 Agent 运行时；子代理（spawn/fork/continuable）、工作流（模型写 JS、worker 执行）、目标循环（same-session goal rounds）、Ralph（fresh-agent 循环）、jobs/schedule 都是插件，隔离边界只有"上下文可见性（spawn/fork）+ 文件写沙箱（file effects only）+ 进程内 worker"，可复现性仅到"会话日志可重放"，不到"同输入重跑产物可比"。
2. **隔离证明**：DSH 的子代理隔离是**事前**可见性/权限边界，本系统落盘-grep 是**事后**逐站 prompt 审计，不是同一类保证；DSH 有 session 日志但默认全文检索关、zstd 压缩、无按站目录，达不到 `prompt_audit/` 的 grep 便利度。
3. **effective_date / 回测 / 时间窗口**：DSH 源码零命中，只有"当前时间上下文"与"未来定时提醒"；补上主要动 Python 数据层（大），DSH 侧只需新增上下文注入/审计插件（小-中）。
4. **会话式 vs 批处理**：DSH 是会话式运行时；headless 只是"一条任务的一次性会话"，对 timestamped 产物目录、断点续跑、一键重跑基本无原生支持（workflow 明确 No journaling or resume）。
5. **Node 与 Python 衔接**：主路径是 bash 工具 shell out 调 Python（Wind/pandas/SEC 留在原处不必重写）；Code Mode 的 Python renderer 内置但 Python backend 包本机未安装。

---

## 8. 最重要的三个风险（供 A×B 对质）

1. **时间纪律会从编排层漏掉**：DSH 没有 effective_date/回测概念，且本机 DSH 设置与历史会话均为 `danger-full-access`（`settings.yaml` + `/tmp/dsh_session_readonly/session.jsonl:2-3`）；若用 DSH 当编排器，最容易发生"模型随手用 bash 读当天数据冒充历史"的污染，且 DSH 侧拦不住。
2. **"隔离证明"降级为"只有会话记录"**：DSH 默认全文搜索关闭、zstd 压缩、无按分析站落盘；若不加自研插件，现有的"每站实际 prompt 可 grep"审计能力会退化成"翻整段会话日志"，发布闸门和时点纪律的验收手段失效。
3. **批处理/重跑/断点续跑缺失**：workflow 无 journaling/resume、jobs 进程内、Ralph 前台一次性；"一键重跑、产物 timestamped、事后审计"这条北极星配套能力需要外部脚本或新插件才能等价，否则重跑与审计成本会显著上升。

---

## 附：可复跑命令索引

```bash
# 0) 版本
node -e "console.log(require('/Users/aidianchi/.dsh/profiles/node_modules/@deepseek-ai/dsh/package.json').version)"

# 1) DSH 源码里没有任何 effective_date / backtest / as-of 概念
grep -rn "effective_date\|effectiveDate\|backtest\|as-of\|asof" \
  /Users/aidianchi/.dsh/profiles/node_modules/@deepseek-ai \
  --include="*.md" --include="*.js" --include="*.json" | grep -v "\.map"

# 2) DSH 会话记录（解压后的原始 JSONL）前 5 行 = session header + 权限/沙箱
head -n 5 /tmp/dsh_session_readonly/session.jsonl

# 3) 会话里所有 bash 工具调用（15 次）
python3 - <<'EOF'
import json
for i,line in enumerate(open('/tmp/dsh_session_readonly/session.jsonl'),1):
    ev=json.loads(line)
    if ev.get('type')=='tool/call':
        print(i, ev['data'].get('name'))
EOF

# 4) 本系统 prompt_audit 落盘可 grep（真实 run 示例）
grep -c "effective_date" output/analysis/vnext/20260724_223804/prompt_audit/L1/attempt_1.prompt.txt
ls output/analysis/vnext/20260724_223804/prompt_audit/

# 5) 本系统 timestamped run 目录与断点续跑
sed -n '306,329p' src/main.py
sed -n '7699,7730p' src/agent_analysis/orchestrator.py
```
