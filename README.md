# ndx_vnext

`ndx_vnext` 是 NDX 研究系统的下一代流水线。

它的目标不是简单生成一份 HTML 报告，而是生成一条可以追问、可以审计、可以展开阅读的投研推理链。

## 先读什么

新读者或新 agent 按这个顺序读：

1. `NEXT_STEPS.md`：现在下一步做什么，按最新在上排列。
2. `ARCHITECTURE.md`：系统为什么这样设计，哪些原则不能破坏。
3. `RESEARCH_CANON.md`：指标怎么读、市场状态怎么诊断的权威研究语料。
4. `DATA_COVERAGE_REVIEW.md`：哪些数据已经稳定，哪些数据仍然薄弱。
5. `RUN_REVIEW_CHECKLIST.md`：每次真实运行后如何复盘。
6. `WORK_LOG.md`：已经完成了什么，按最新在上排列。

如果你是代码 agent，还必须读：

- `AGENTS.md`：Codex 和通用 agent 工作规则。
- `CLAUDE.md`：Claude Code 独立分支工作规则。

## 当前三条主线

1. 核心系统：L1-L5、Bridge、Thesis、Critic、Risk、Reviser、Final 是否形成干净、可追溯、不抹平冲突的推理链。
2. 数据基础：采集、标准化、数据源覆盖、缺口和置信度边界是否可靠。
3. 输出体验：最终是 self-contained HTML、正式前端，还是更高级交互系统；阅读顺序、审美和可审计性都要逐步打磨。

这三条主线不能互相替代。核心系统决定“怎么想”，数据基础决定“凭什么想”，输出体验决定“别人能不能顺着读懂并追问”。

## 常用命令

当前默认只使用 DeepSeek：

- 首选：`deepseek-v4-flash`
- 备用：`deepseek-v4-pro`

### macOS / Linux

首次安装：

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -U pip setuptools wheel
python -m pip install -r requirements.txt
cp .env.example .env
```

在 `.env` 中填写：

```bash
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DEEPSEEK_BASE_URL=https://api.deepseek.com
```

运行测试：

```bash
python -m pytest -q
```

真实运行：

```bash
python src/main.py --models deepseek-v4-flash,deepseek-v4-pro --skip-report --disable-charts
```

生成默认 `brief` 报告：

```bash
python src/agent_analysis/vnext_reporter.py --run-dir output/analysis/vnext/<run_id> --template brief
```

### Windows PowerShell

运行测试：

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

生成默认 `brief` 报告：

```powershell
.\.venv\Scripts\python.exe src\agent_analysis\vnext_reporter.py --run-dir output\analysis\vnext\<run_id> --template brief
```
