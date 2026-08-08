# ndx_vnext

`ndx_vnext` 是一条给纳指 100 做投资判断的自动流水线：五个分析员各自独立看自己那摊数据（利率与宏观 / 信用与波动 / 资金行为 / 盈利与估值 / 结构与叙事）→ 跨层对质找冲突 → 正反双方拿同一份证据辩论 → 终审写成判断书。每个数字可追来源，每个判断事后要被打分。产出是一条可追问、可审计、可展开阅读的投研推理链。

## 先读什么

1. `系统说明书.md`：系统全景、逐站点说明、长期原则（先读它建立全局）。
2. `现在.md`：现在什么状态、下一步做什么、什么在等你拍板（唯一状态源）。
3. `RESEARCH_CANON.md`：指标怎么读、市场状态怎么诊断的权威研究语料。
4. `WORK_LOG.md`：已经完成了什么，按最新在上排列。
5. 工作规则：`AGENTS.md`（Codex 和通用 agent）、`CLAUDE.md`（Claude Code 独立分支）。

## 常用命令

当前默认只使用 DeepSeek：首选 `deepseek-v4-flash`，备用 `deepseek-v4-pro`。

真实运行：

```bash
python src/main.py --models deepseek-v4-flash,deepseek-v4-pro --skip-report --disable-charts
```

只采集数据快照（与分析解耦）：

```bash
python src/main.py --collect-only --models deepseek-v4-flash,deepseek-v4-pro --skip-report --disable-charts
```

生成默认 `brief` 报告：

```bash
python src/agent_analysis/vnext_reporter.py --run-dir output/analysis/vnext/<run_id> --template brief
```

运行测试：

```bash
python -m pytest -q
```

首次安装与 `.env` 配置见 `requirements.txt` 与 `.env.example`。

## 当前输出入口

- 默认阅读入口：`output/reports/vnext_brief_*.html`
- 研究控制台：`output/reports/vnext_research_console.html`（一键开启：`python src/open_research_console.py` 或双击 `open_research_console.command`）
- 交互 workbench：`output/reports/vnext_workbench_*.html`
- 同源图表数据：`output/analysis/vnext/<run_id>/chart_time_series.json`

`brief` 是连续阅读报告；workbench 是看盘式探索页面；控制台是运行前配置面板。三者不要互相替代。

## 采集与分析解耦

支持两段式运行：先用 `--collect-only` 生成不可变数据快照和 sidecar，再在主机上选择这个数据包只跑 DeepSeek 分析和报告生成。这样可以让 yfinance/Yahoo 走更适合的网络路径、DeepSeek API 走更稳定的直连路径；关键是报告必须能追溯到同一个数据快照。
