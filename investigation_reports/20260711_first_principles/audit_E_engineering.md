# ndx_vnext 工程质量横切面调查报告

调查方式：只读。运行了 `pytest`（全绿，无网络/无 LLM 调用）；其余全部基于 `wc`、`grep`、AST 解析、`git log`/`git diff` 等静态检查。所有结论标注验证方式；未运行验证的部分明确标"推测"。

---

## ① 健康度总览（量化，已验证）

| 维度 | 数值 | 来源 |
|---|---|---|
| src/ 总行数 | 49,420 行，42 个 .py 文件 | `find src -name "*.py" \| xargs wc -l` |
| tests/ 总行数 | 17,053 行，49 个 test_*.py 文件 | 同上，tests/ |
| 三大巨型文件占比 | `orchestrator.py` 5,672 + `tools_L4.py` 5,031 + `vnext_reporter.py` 5,019 = 15,722 行，占 src 的 31.8% | 同上 |
| 次大文件 | `chart_generator.py` 2,410 / `agent_analysis/contracts.py` 2,086 / `interactive_chart_workbench.py` 1,888 / `tools_common.py` 1,765 / `event_narrative_ledger.py` 1,711 | 同上 |
| pytest 结果 | **519 passed, 0 failed, 0 skipped, 0 xfail**，用时 73.34s | 实际运行 `python -m pytest -q` |
| 测试红旗模式 | `assert True` / `@pytest.mark.skip` / `xfail` 全部 0 处 | grep 全量扫描 |
| 循环依赖 | 未发现（AST 解析全部内部 import 边） | 自写 Python AST 依赖图脚本 |
| 类型标注覆盖率 | 1,153 / 1,338 个函数带返回类型标注，约 86% | grep 统计 |
| 宽泛异常捕获 | `except Exception` 216 处，其中静默吞掉（`except...: pass`）64 处，集中在 `tools_L4.py`（47 处宽泛捕获，5 处静默吞） | grep 统计 |
| print vs logging | print 96 处 / logging 203 处 | grep 统计 |
| 全局可变缓存 | 仅 3 处显式模块级缓存字典（`_CONFIG_CACHE`、`_VOL_LEVEL_CACHE`、`_NDX100_PRICE_PANEL_RUN_CACHE`），未泛滥 | grep 统计 |
| git 提交历史 | 94 次提交，2026-04-27 至今约 2.5 个月；近 20 次提交均值 ~1,251 行改动/提交 | `git log --numstat` |
| 当前分支未提交改动 | 37 个文件，+4,529 / -487 行，混合 prompts + 核心代码 + 测试 | `git diff --stat` |
| 密钥管理 | `.env` 正确 gitignore，历史上从未被提交；正则扫描 src/ 未发现硬编码密钥 | `git log --all -- .env` 为空；grep 扫描 |
| data_cache/、node_modules/ | 磁盘存在但 **均未被 git 追踪**（0 文件） | `git ls-files data_cache node_modules` |
| 根目录审计/调试文件 | 39 个 md/txt，其中 35 个已提交入库 | `ls` + `git ls-files` |
| 依赖 | requirements.txt 20 个直接依赖，无 lock 文件；venv 实际安装 233 个包（openbb[all] 拖入的传递依赖占大头，且该模块注释明确写着"不接入生产 L1-L5 路径"） | `cat requirements.txt`；`pip freeze \| wc -l` |

---

## ② 关键发现（按严重度）

### 严重（影响可演进性 / 数据可信度）

1. **三个 5,000+ 行"上帝文件"占 src 三分之一，其中两个是单类god object。**
   `agent_analysis/orchestrator.py:256` 的 `VNextOrchestrator` 类有 **164 个方法**，混杂了：prompt 组装（`_compose_layer_prompt`/`_compose_bridge_prompt`/`_compose_thesis_prompt`）、JSON 规整校验（约 30 个 `_normalize_*`）、证据登记簿构建（`_build_evidence_registry`）、claim ledger、stage 检查点/manifest 文件 I/O（`_save_json`/`_load_stage_checkpoint`）、哈希缓存（`_stable_json_file_sha256`）、文本截断/摘要等至少 6-7 类职责在同一个类里。改一个 stage 的行为，理论上要在这 164 个方法里定位正确的边界，认知负荷很高。
   `tools_L4.py` 是 **0 个 class、125 个顶层函数**的过程式大杂烩：Wind/Damodaran/SEC/Yahoo/Eastmoney 五套外部数据源的 HTTP 抓取、HTML/Excel 解析、缓存、历史分位计算全部堆在一个命名空间里（如 `_fetch_wind_metric_percentile_windows`、`_parse_damodaran_implied_erp_excel`、`_component_row_from_yfinance` 并列）。这不是分层，是"把能想到的都塞进一个文件"。

2. **无正式包结构，靠 sys.path hack 支撑双重 import 风格。**
   几乎每个内部 import 都写成
   ```python
   try:
       from .tools_common import *
   except ImportError:
       from tools_common import *
   ```
   （`src/tools_L2.py:7-10` 等，全仓库 102 处 `except ImportError`，覆盖 38/42 个 src 文件）。这说明项目从未真正被当作可安装 package 处理——没有 `pyproject.toml`/`setup.py`，靠"猜相对还是绝对导入哪个能成功"来跑。副作用是 **49 个 test 文件里 50 个手写 `sys.path.insert(0, ...)`**（如 `tests/test_core_checker.py:1-4`），且全仓库没有一个 `conftest.py` 集中处理——每个测试文件都在重复这段样板。

3. **L4 直接跨层 import L1 和 L3（`tools_L4.py -> tools_L1`, `tools_L4.py -> tools_L3`）。**
   AST 依赖图显示 `tools_L4` 依赖 `data_evidence`、`tools_L1`、`tools_L3`、`tools_common`。CLAUDE.md 明确的常驻边界是"L1-L5 运行时上下文必须隔离"，指的是运行时数据/结论不能跨层；这条不直接违反该原则（那是关于 agent 运行时上下文，不是 Python import），但它说明"L1-L5"在代码层面并不是五个平行、可独立替换的模块，而是有硬编码的横向耦合，重写时如果照搬"每层一个文件"的直觉设计，会撞上这层真实存在的耦合。

4. **未提交改动体量大、批次大，属于高风险协作模式（已验证，非推测）。**
   当前分支 37 个文件、+4,529/-487 行未提交，混合了 prompts、核心 orchestrator/reporter 代码、测试改动在一起；近 20 次提交均值约 1,251 行/提交。这种"大批量、混合关注点"的提交习惯意味着：一旦某次改动引入问题，`git bisect` 定位成本高，且回滚会连带撤销无关的合法改动。这是当前工作方式（AI 辅助 + 无工程背景开发者）最直接可观测的风险，不是代码本身的问题，而是变更管理习惯的问题。

### 中等

5. **`except Exception` 宽泛捕获集中在数据采集层，`tools_L4.py` 单文件 47 处。**
   其中 64 处是纯 `except: pass` 静默吞掉（如 `tools_L4.py:174-175`、`tools_L4.py:3013-3014`、`tools_L4.py:4629-4630`）。抽查后这些多数是"某个可选来源解析失败就跳过，继续尝试下一个来源"的合理降级逻辑，不是掩盖真实 bug；但因为分散在 47 处而非集中封装成一个"try_source" helper，审查一次新 bug 时无法一眼确认某次失败是被合理降级还是被意外吞掉。

6. **仓库根目录 35 个已提交的审计/调试 md 文件，构成认知噪音。**
   包括多份 `PLAIN_LANGUAGE_*.md`、`2026-05-*_BACKTEST_*.md`、`PROJECT_AUDIT_20260513.md`、`audit_report_20260517.md` 等，与当前生效文档（`ARCHITECTURE.md`/`NEXT_STEPS.md`/`RESEARCH_CANON.md`/`WORK_LOG.md`）混在根目录，没有 `archive/` 归档。新读者或新 agent 第一眼看到仓库根目录，无法立刻分清哪些是当前权威文档、哪些是历史一次性调查快照。`data_cache/`、`node_modules/`、`.venv/` 本身倒是干净地被 gitignore 排除，没有入库——这点做得对，值得肯定。

7. **依赖健康度：无 lock 文件 + 引入了未使用的重量级依赖。**
   `requirements.txt` 用的是宽松的 `>=` 版本区间，无 `pip-compile`/`poetry.lock`，"换一台机器能不能装出同一个环境"没有强保证。`openbb[all]==4.7.1` + `openbb-polygon` 被列为直接依赖，但注释明确写着"这些不接入生产 L1-L5 数据路径"（`requirements.txt` 第 15-17 行），却仍会把 venv 拉到 233 个包——这是为了"探针/候选源调研"目的引入的重依赖，长期挂在 requirements.txt 里增加安装体积和潜在版本冲突面。另外 README 未声明 Python 版本要求，而实际验证用的 `.venv` 跑的是 Python 3.12，与本机 `python3 --version` 显示的系统 Python 3.9.6 不一致（未验证在 3.9 上是否能装起来，只是标记出这个潜在的复现盲点）。

### 轻微 / 正面信号

8. **测试诚实度总体良好（抽查 8 个文件后的判断）。**
   - `tests/test_core_checker.py`（342 行，全部读完）：无 mock，直接构造真实 indicator 字典输入，断言 `DataIntegrity().run()` 计算出的置信度、阻断原因（`blocking_reasons`）、未来日期检测等真实业务逻辑输出，是货真价实的单元测试。
   - `tests/test_vnext_orchestrator.py`（2,546 行，40 个测试函数，仅 2 处 mock）：通过依赖注入 `FakeLLMEngine`/`SequencedFakeLLMEngine`/`RoutingFakeLLMEngine` 向 orchestrator 注入可控的 LLM 响应，测试的是编排状态机的真实控制流（stage 路由、重试、evidence_ref 校验、claim gate），而不是在断言"mock 被调用过"。
   - `tests/test_l4_external_valuation_sources.py`：只在网络边界打桩（`monkeypatch.setattr(tools_L4, "_fetch_json", ...)`），断言的是解析函数从真实结构 HTML/JSON payload 里提取数值、百分位、日期是否正确（如 `test_wind_ndx_valuation_parser_handles_nested_step_tables_with_column_metadata`），属于"验证解析正确性"而非"验证 mock 自己"。
   - 全仓库扫描未发现 `assert True`、`pytest.skip`、`xfail`，也未发现测试里直接调用未打桩的 `requests.get`/`yf.download`——测试套件本身对"不联网""不调用真实 LLM"这条纪律执行得很干净。
   - 唯一的结构性缺口：**没有 conftest.py**，共享 fixture、路径处理、mock helper 全靠每个文件各自复制，是可维护性上的技术债，但不影响测试当前的正确性。

9. **契约耦合面是可控的，不是"到处裸字典"。**
   `agent_analysis/contracts.py`（2,086 行，69 个 Pydantic 模型）被 16 个 src 文件 + 9 个 test 文件引用；`evidence_ref` 字段贯穿 34 个文件，`IndicatorAnalysis` 贯穿 7 个文件。改一个契约字段的爆炸半径是可枚举、可 grep 定位的（不是靠约定的裸 dict key 命名），这是这个代码库比"纯 AI 一把梭"项目更扎实的地方。但 orchestrator 内部仍有大量 `_normalize_*` 方法在原始 dict 和 Pydantic 契约之间做人工搬运校验，说明collector 输出的 raw JSON 和契约层之间没有一层干净的适配边界，都堆在 orchestrator 里做。

10. **isolation/firewall 类架构原则不是纸面文档，有对应测试锁定。**
    `tests/test_objective_firewall.py` 用真实的 `VNextOrchestrator` + `AnalysisPacket`/`LayerCard` 契约对象验证"objective_firewall_summary"这类跨层隔离机制的行为，说明 CLAUDE.md 里"L1-L5 运行时隔离"这条原则在代码里有实际实现和回归测试锁定，不只是写在文档里希望人自觉遵守。

---

## ③ 改良 vs 重写判决

**判决：(b) 保留概念 + 分模块重写为主，辅以对最脏的两三个文件做外科手术式拆分。不建议 (c) 全部推倒，也不建议 (a) 纯原地改良。**

理由：

- 支持"不是 (c) 全推倒"：契约层（`contracts.py`）设计合理、耦合面可枚举；测试诚实、519/519 全绿、且明确锁定了业务规则（置信度计算、阻断规则、隔离防火墙、编排状态机）；依赖方向没有循环；密钥管理干净；README 与实际 CLI 参数一致，可复现性问题只是"无 lock 文件 + 未声明 python 版本"这类小修复，不是根本性缺陷。这些都是需要人工重新积累的资产，推倒会把这些隐性知识全部损失掉。
- 支持"不是 (a) 纯原地改良"：三个 5,000+ 行文件里，`orchestrator.py`（164 方法单类）和 `tools_L4.py`（125 顶层函数无分组）已经到了"改一处要通读大半个文件才敢下手"的程度。原地改良（只加不拆）只会让这两个文件继续膨胀；`tools_L4.py` 从 May 3 的某版本到现在已经涨到 232KB/5,031 行（对比 `tools_L1.py` 1,419 行、`tools_L2.py` 1,372 行、`tools_L3.py` 788 行），是唯一明显失控的一层，说明"新数据源就往这个文件里加函数"是现有模式，不主动拆分会持续恶化。
- 因此判决是"分模块重写"：以现有 `contracts.py` 契约、`data_evidence.py`/`data_availability.py` 边界模型、5 层 `tools_L*.py` 的整体分层思路为骨架保留，但对 `orchestrator.py`（拆成 prompt 组装 / 归一化校验 / evidence registry / stage 生命周期管理 4-5 个协作对象）和 `tools_L4.py`（按数据源拆成 `wind_source.py`/`damodaran_source.py`/`sec_source.py`/`yahoo_source.py` 等，用统一的 fetch-parse-cache 接口而不是 125 个平铺函数）做结构性拆分重写。`vnext_reporter.py` 优先级低于前两者——它虽然也 5,019 行，但主要是"一个类 + 52 个纯格式化小函数"，内聚度和风险都低于另外两个文件，可以留到后面再拆。

### 值得带走的具体资产

| 资产 | 位置 | 带走理由 |
|---|---|---|
| Pydantic 契约模型 | `src/agent_analysis/contracts.py`（69 个 model） | 耦合面可枚举、被广泛复用，是整个推理链的"骨架"，重写应该以此为不动点 |
| 数据边界/口径模型 | `src/data_evidence.py`、`src/data_availability.py` | 体量小（479+207 行）、职责单一、有专门契约测试（`test_data_evidence_contract.py`），是"缺口不能装成事实"这条铁律的落地代码 |
| 测试里的 Fake/Stub 基础设施 | `tests/test_vnext_orchestrator.py` 里的 `FakeLLMEngine`/`SequencedFakeLLMEngine`/`RoutingFakeLLMEngine`/`ParseRetryFakeLLMEngine` | 已验证的、不联网不调真实 LLM 的编排测试范式，重写时应直接复用这套依赖注入思路，而不是重新发明 |
| L4 数据源解析测试的 fixture 样本 | `tests/test_l4_external_valuation_sources.py`、`test_l4_forward_earnings_quality.py` 里的真实结构 HTML/JSON payload | 这些样本payload 是从真实响应里提炼出来的解析回归用例，比源码本身更难重新积累（需要重新去外部网站抓样本），拆 `tools_L4.py` 时必须先把这些 fixture 保住再动手 |
| Prompt 文件 | `src/agent_analysis/prompts/*.md`（`l3_analyst.md`/`l4_analyst.md`/`cross_layer_bridge.md`/`final_adjudicator.md`/`thesis_builder.md` 等） | 与源码解耦、经过多轮迭代（当前分支仍在改），是业务知识的浓缩，属于"重写代码但不重写认知"的核心保留对象 |
| 架构文档 | `ARCHITECTURE.md`、`RESEARCH_CANON.md`、`CLAUDE.md` 常驻边界 | 已验证有对应测试锁定（firewall、置信度阻断规则等），不是空文档 |
| `DataIntegrity`（`core/checker.py`）的阻断规则 | `src/core/checker.py:1-421` + `tests/test_core_checker.py` | 全部本地纯函数、无 mock、逻辑清晰、测试覆盖扎实，可以近乎原样迁移 |

### 重写最大的坑

1. **`tools_L4.py` 里 125 个函数之间存在隐性调用顺序/缓存依赖**（如 `_damodaran_cache_dir`/`_damodaran_cache_path`/`_is_valid_damodaran_cache_payload` 这类三件套模式重复出现在多个数据源上），拆分时如果不先画出真实调用图，很容易在拆分后漏掉某个源特有的缓存失效/重试细节，导致数据静默变差而不报错（因为很多失败路径本来就是 `except: pass` 降级，拆分引入的新 bug 会被这层降级掩盖，不会立刻在测试或运行时报错）。
2. **orchestrator 的 164 个方法之间共享大量隐式状态**（通过 `self.xxx` 而非参数传递），重写成多个协作对象时，如果只是机械地把方法搬到新类却不重新梳理数据流，很容易把"god class"问题原样平移成"god class 拆成三个仍然互相持有对方引用"的假拆分。
3. **无 lock 文件 + openbb 重依赖**：重写若选择新的包管理（poetry/uv），要先决定 openbb 这类"仅用于探针调研、未接入生产路径"的重依赖是否继续保留在主依赖里，否则会把新项目的安装体积和 CI 时间继续背上旧包袱。
4. **519 个测试目前是唯一的回归安全网**，且诚实度已验证良好；重写过程中如果不能保持"新代码跑通等价的契约测试"这条纪律，会在过程中失去唯一能验证"重写没有引入行为倒退"的手段。

---

## ④ 给总报告的核心启示

1. **这不是一个"AI 写的烂代码"典型案例——测试是真的、契约是真的、密钥管理是真的、依赖方向没有循环。** 如果总报告要下"这个项目能不能信"的判断，工程横切面给出的信号是偏正面的：519/519 测试全绿且抽查后确认在验证真实业务逻辑而非自我复读 mock，这个信号应该被认真采信，不要因为"没有工程背景的人写的"这个先验就假设代码质量差。
2. **真正的风险集中在 3 个文件、不到代码量三分之一的范围内**，尤其是 `orchestrator.py` 的单类 164 方法和 `tools_L4.py` 的 125 个无分组顶层函数——这是"改一处动全身"风险的实际来源，而不是整个仓库都风险均匀分布。总报告如果要给"能不能安全扩展新功能"的判断，答案是"看往哪扩"：加新的 L4 数据源大概率继续膨胀 `tools_L4.py`；改编排逻辑大概率要在 orchestrator 164 个方法里定位边界，两者都是高风险区，其余层（L1/L2/L3/L5、契约层、数据边界层）风险可控。
3. **协作方式（大批量未提交改动、大颗粒度提交）比代码本身更需要立刻纠正**，且成本极低：当前分支 37 文件 4,500+ 行混合改动尚未拆分提交，这是唯一"今天就能改善、不需要重写"的风险点，建议在总报告里单独强调"先把当前未提交改动按关注点拆成小提交，再谈要不要重写"。
4. **重写的取舍不是"要不要重写"而是"重写多少"**：契约层、数据边界层、prompt 文件、测试基础设施（尤其是 Fake LLM 引擎和 L4 解析 fixture）都值得原样或近乎原样带走，真正需要推倒重来的是 orchestrator 和 tools_L4 两个文件的内部结构，其余可以在保留对外接口的前提下逐步替换实现——这是一个可以分阶段、可回滚地做的重构项目，不需要停机式重写整个仓库。
5. **可复现性有几个廉价但真实的缺口**：无依赖 lock 文件、README 未声明 Python 版本、`openbb[all]` 这种"仅调研用"的重依赖长期挂在生产 requirements 里。这些不影响"代码写得好不好"的判断，但直接影响"换一台机器/换一个人能不能跑起来"，建议作为重写窗口期顺手解决的低成本项，而不是单独立项。
