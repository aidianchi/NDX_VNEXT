from __future__ import annotations

import argparse
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .config import path_config
    from .manual_data import DEFAULT_MANUAL_DATA, get_active_manual_data_path, get_manual_data_local_path, load_manual_data
except ImportError:
    from config import path_config
    from manual_data import DEFAULT_MANUAL_DATA, get_active_manual_data_path, get_manual_data_local_path, load_manual_data


def _escape(value: Any) -> str:
    return html.escape(str(value or ""), quote=True)


def _safe_script_json(value: str) -> str:
    """Keep embedded JSON parseable inside a raw script tag."""
    return (
        value.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


class ResearchConsoleGenerator:
    """Generate a self-contained first-screen control console for vNext runs."""

    def __init__(self, reports_dir: Optional[str | Path] = None) -> None:
        self.reports_dir = Path(reports_dir or path_config.reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def run(self, output_path: Optional[str | Path] = None) -> str:
        destination = Path(output_path) if output_path else self.reports_dir / "vnext_research_console.html"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(self._render(), encoding="utf-8")
        return str(destination)

    def _latest_reports(self) -> List[Path]:
        candidates = {path.resolve(): path for path in list(self.reports_dir.glob("vnext_*.html")) + list(self.reports_dir.glob("vnext_research_ui_*.html"))}
        reports = sorted(
            candidates.values(),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        return [path for path in reports if "workbench" not in path.name and "console" not in path.name][:6]

    def _latest_workbenches(self) -> List[Path]:
        candidates = {path.resolve(): path for path in list(self.reports_dir.glob("vnext_workbench_*.html")) + list(self.reports_dir.glob("vnext_interactive_charts_*.html"))}
        workbenches = sorted(
            candidates.values(),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        return workbenches[:4]

    def _latest_runs(self) -> List[Path]:
        run_root = Path(path_config.analysis_dir) / "vnext"
        if not run_root.exists():
            return []
        runs = sorted([path for path in run_root.iterdir() if path.is_dir()], key=lambda path: path.stat().st_mtime, reverse=True)
        return runs[:5]

    def _latest_data_jsons(self) -> List[Path]:
        data_root = Path(path_config.data_dir)
        if not data_root.exists():
            return []
        return sorted(data_root.glob("data_collected_v9_*.json"), key=lambda path: path.stat().st_mtime, reverse=True)[:5]

    def _latest_control_logs(self) -> List[Path]:
        log_root = Path(path_config.logs_dir) / "control_service"
        if not log_root.exists():
            return []
        candidates = list(log_root.glob("*.log")) + list(log_root.glob("*.json"))
        return sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)[:5]

    def _latest_browser_sidecars(self) -> List[Path]:
        sidecar_root = Path(path_config.output_dir) / "browser_sidecar"
        if not sidecar_root.exists():
            return []
        return sorted(sidecar_root.glob("*.json"), key=lambda path: path.stat().st_mtime, reverse=True)[:4]

    def _links(self, paths: List[Path], empty_text: str) -> str:
        if not paths:
            return f'<span class="empty-link">{_escape(empty_text)}</span>'
        return "".join(
            f'<a href="{_escape(path.resolve().as_uri())}" data-artifact-path="{_escape(str(path.resolve()))}">{_escape(path.name)}</a>'
            for path in paths
        )

    def _artifact_link_attrs(self, path: Optional[Path]) -> str:
        if not path:
            return 'href="#"'
        resolved = path.resolve()
        return f'href="{_escape(resolved.as_uri())}" data-artifact-path="{_escape(str(resolved))}"'

    def _manual_template_json(self) -> str:
        template = json.loads(json.dumps(DEFAULT_MANUAL_DATA, ensure_ascii=False))
        template["active"] = True
        template["date"] = datetime.now().strftime("%Y-%m-%d")
        return json.dumps(template, ensure_ascii=False, indent=2)

    def _initial_manual_data_json(self) -> str:
        active_path = get_active_manual_data_path()
        if not active_path:
            return self._manual_template_json()
        data = load_manual_data(active_path)
        if not data.get("date"):
            data["date"] = datetime.now().strftime("%Y-%m-%d")
        return json.dumps(data, ensure_ascii=False, indent=2)

    def _render(self) -> str:
        manual_template = self._manual_template_json()
        reports = self._latest_reports()
        workbenches = self._latest_workbenches()
        runs = self._latest_runs()
        control_logs = self._latest_control_logs()
        browser_sidecars = self._latest_browser_sidecars()
        latest_report = reports[0] if reports else None
        latest_workbench = workbenches[0] if workbenches else None
        data_jsons = self._latest_data_jsons()
        latest_data_json = data_jsons[0] if data_jsons else None
        latest_href = latest_report.resolve().as_uri() if latest_report else "#"
        latest_workbench_href = latest_workbench.resolve().as_uri() if latest_workbench else "#"
        manual_path = get_manual_data_local_path()
        initial_manual_data = self._initial_manual_data_json()
        payload = json.dumps(
            {
                "manualTemplate": manual_template,
                "initialManualData": initial_manual_data,
                "manualPath": manual_path,
                "latestReport": str(latest_report or ""),
                "latestWorkbench": str(latest_workbench or ""),
                "latestRun": str(runs[0] if runs else ""),
                "latestDataJson": str(latest_data_json or ""),
                "browserSidecarPath": str((Path(path_config.output_dir) / "browser_sidecar" / "trendonify_ndx_valuation.json")),
            },
            ensure_ascii=False,
        )
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>NDX vNext 研究控制台</title>
  <style>{self._css()}</style>
</head>
<body>
  <main class="console-shell">
    <section class="hero">
      <div>
        <p class="eyebrow">NDX vNext</p>
        <h1>研究控制台</h1>
        <p>把运行对象、人工数据、模型策略、功能开关、输出入口和健康状态放在同一屏。它是研究动作的总控台，不替代最终报告。</p>
      </div>
      <aside class="status-card">
        <span>默认路径</span>
        <strong>brief 报告</strong>
        <div class="status-actions">
          <a class="primary-link" {self._artifact_link_attrs(latest_report)}>打开最新报告</a>
          <a class="secondary-link" {self._artifact_link_attrs(latest_workbench)}>打开 workbench</a>
        </div>
      </aside>
    </section>

    <nav class="workflow-rail" aria-label="研究控制台流程">
      <a href="#setup-panel"><b>01</b><span>对象与日期</span></a>
      <a href="#manual-panel"><b>02</b><span>数据校准</span></a>
      <a href="#run-panel"><b>03</b><span>运行报告</span></a>
      <a href="#health-panel"><b>04</b><span>健康审计</span></a>
    </nav>

    <section class="control-grid">
      <article class="panel setup-panel" id="setup-panel">
        <div class="panel-head">
          <span>01</span>
          <div>
            <h2>运行对象与日期</h2>
            <p>先确定研究对象和时点，再决定是否使用已有数据。</p>
          </div>
        </div>
        <div class="field-grid">
          <label>标的 <input id="ticker" type="text" value="NDX / QQQ"></label>
          <label>分析日期 <input id="dataDate" type="date"></label>
          <label class="checkbox-field"><input id="historicalDateMode" type="checkbox"> 历史日期 / 回测</label>
          <label>已有数据 JSON <input id="dataJsonPath" type="text" value="{_escape(str(latest_data_json or ''))}" placeholder="output/data/data_collected_YYYYMMDD_live.json"></label>
          <label>已有 run 目录 <input id="runDirPath" type="text" value="{_escape(str(runs[0]) if runs else '')}" placeholder="output/analysis/vnext/<run_id>"></label>
        </div>
      </article>

      <article class="panel manual-panel" id="manual-panel">
        <div class="panel-head">
          <span>02</span>
          <div>
            <h2>人工数据与数据源校准</h2>
            <p>上次保存的人工锚会自动带入；这里同时决定哪些外部来源可以进入本轮校准。</p>
          </div>
        </div>
        <div class="manual-form">
          <label>数据日期 <input data-manual-field="date" type="date"></label>
          <label>来源 <input data-manual-field="source" type="text" placeholder="Wind / manual"></label>
          <label>置信度
            <select data-manual-field="confidence">
              <option value="">不覆盖</option>
              <option value="high">high</option>
              <option value="medium">medium</option>
              <option value="low">low</option>
            </select>
          </label>
          <fieldset class="metric-pair">
            <legend>ERP</legend>
            <label>ERP % <input data-manual-field="erp" type="number" step="0.01"></label>
            <label>ERP 5Y 分位 <input data-manual-field="erp_percentile_5y" type="number" step="0.1" min="0" max="100"></label>
            <label>ERP 10Y 分位 <input data-manual-field="erp_percentile_10y" type="number" step="0.1" min="0" max="100"></label>
          </fieldset>
          <fieldset class="metric-pair">
            <legend>PE</legend>
            <label>当前 PE <input data-manual-field="pe" type="number" step="0.01" min="0"></label>
            <label>PE 5Y 分位 <input data-manual-field="pe_percentile_5y" type="number" step="0.1" min="0" max="100"></label>
            <label>PE 10Y 分位 <input data-manual-field="pe_percentile_10y" type="number" step="0.1" min="0" max="100"></label>
          </fieldset>
          <fieldset class="metric-pair">
            <legend>PB</legend>
            <label>当前 PB <input data-manual-field="pb" type="number" step="0.01" min="0"></label>
            <label>PB 5Y 分位 <input data-manual-field="pb_percentile_5y" type="number" step="0.1" min="0" max="100"></label>
            <label>PB 10Y 分位 <input data-manual-field="pb_percentile_10y" type="number" step="0.1" min="0" max="100"></label>
          </fieldset>
          <fieldset class="metric-pair">
            <legend>PS</legend>
            <label>当前 PS <input data-manual-field="ps" type="number" step="0.01" min="0"></label>
            <label>PS 5Y 分位 <input data-manual-field="ps_percentile_5y" type="number" step="0.1" min="0" max="100"></label>
            <label>PS 10Y 分位 <input data-manual-field="ps_percentile_10y" type="number" step="0.1" min="0" max="100"></label>
          </fieldset>
        </div>
        <p id="manualValidation" class="validation-note">等待输入。</p>
        <details class="advanced-json">
          <summary>高级 JSON 预览</summary>
          <textarea id="manualJson" spellcheck="false">{_escape(manual_template)}</textarea>
        </details>
        <div class="button-row">
          <button type="button" id="downloadManual">保存人工数据</button>
          <button type="button" id="resetManual">恢复模板</button>
        </div>
        <div class="source-calibration" aria-label="数据源校准">
          <div>
            <h3>数据源选择</h3>
            <p>人工/Wind 是最高信任校准源；Trendonify 和新闻只作为显式 sidecar 或人工确认来源。</p>
          </div>
          <div class="toggle-line">
            <label><input id="enableNews" type="checkbox"> 运行时生成官方新闻底账</label>
            <label><input id="trustBbBrowser" type="checkbox"> Trendonify sidecar 标记为信任</label>
          </div>
          <div class="browser-sidecar">
            <h3>Trendonify 估值 sidecar</h3>
            <div class="browser-actions">
              <a href="https://trendonify.com/united-states/stock-market/nasdaq-100/pe-ratio">查看 PE 页</a>
              <a href="https://trendonify.com/united-states/stock-market/nasdaq-100/forward-pe-ratio">查看 Forward PE 页</a>
              {self._links(browser_sidecars, '还没有 browser sidecar JSON。')}
            </div>
            <pre id="browserCommandPreview">python3 src/browser_sidecar.py --source trendonify_valuation --output output/browser_sidecar/trendonify_ndx_valuation.json --trusted</pre>
            <div class="button-row">
              <button type="button" id="runBrowserSidecar">采集 Trendonify</button>
              <button type="button" id="openBrowserSidecar">打开输出位置</button>
            </div>
            <p id="browserStatus" class="run-status">勾选只影响 sidecar 输出的信任标记；采集需点击“采集 Trendonify”，结果不会静默进入 L1-L5。</p>
          </div>
          <div class="browser-sidecar">
            <h3>官方新闻 sidecar</h3>
            <pre id="newsCommandPreview">python3 src/news_event_ledger.py --output output/analysis/news_event_ledger.json</pre>
            <div class="button-row">
              <button type="button" id="runNewsLedger">采集新闻数据</button>
            </div>
            <p id="newsStatus" class="run-status">新闻底账只记录官方宏观 RSS 和 M7 SEC filings；作为背景，不替代指标证据。</p>
          </div>
        </div>
        <p class="path-note">目标文件：{_escape(manual_path)}</p>
      </article>

      <article class="panel model-panel">
        <div class="panel-head">
          <span>03</span>
          <div>
            <h2>模型与 vNext 流程</h2>
            <p>按 vNext 当前架构组织：采集、五层分析、native brief、workbench 和运行日志。</p>
          </div>
        </div>
        <div class="segmented" role="radiogroup" aria-label="模型策略">
          <label><input type="radio" name="modelMode" value="deepseek-v4-flash,deepseek-v4-pro" checked> flash 优先</label>
          <label><input type="radio" name="modelMode" value="deepseek-v4-pro"> pro only</label>
          <label><input type="radio" name="modelMode" value="custom"> 自定义顺序</label>
        </div>
        <label class="custom-models">自定义模型顺序 <input id="customModels" type="text" value="deepseek-v4-flash,deepseek-v4-pro"></label>
        <div class="mode-grid" role="radiogroup" aria-label="vNext 流程">
          <label><input type="radio" name="runMode" value="vnext_full" checked> 完整 vNext</label>
          <label><input type="radio" name="runMode" value="collect_data"> 只采集数据</label>
          <label><input type="radio" name="runMode" value="analyze_existing"> 已有数据分析</label>
          <label><input type="radio" name="runMode" value="native_brief"> 只生成 brief</label>
          <label><input type="radio" name="runMode" value="workbench_only"> 只生成 workbench</label>
          <label><input type="radio" name="runMode" value="logs_only"> 查看日志</label>
        </div>
      </article>

      <article class="panel run-panel" id="run-panel">
        <div class="panel-head">
          <span>04</span>
          <div>
            <h2>运行完整报告</h2>
            <p>一次运行会保存人工数据，执行 vNext，生成 native brief，并生成 workbench。</p>
          </div>
        </div>
        <div class="toggle-line">
          <label><input id="skipLegacyReport" type="checkbox" checked> 不生成旧版 HTML</label>
          <label><input id="disableCharts" type="checkbox" checked> 不生成旧版 charts</label>
          <label><input id="enableLegacyCharts" type="checkbox"> 临时启用旧版 charts</label>
        </div>
        <p class="legacy-note">旧版 HTML 是过渡期兼容产物；默认只生成 vNext artifacts、native brief 和 workbench。</p>
        <div class="module-picker" aria-label="交互工作台模块">
          <h3>交互工作台模块</h3>
          <label><input type="checkbox" name="workbenchModule" value="price_technical" checked> 价格技术</label>
          <label><input type="checkbox" name="workbenchModule" value="volatility_credit" checked> 波动信用</label>
          <label><input type="checkbox" name="workbenchModule" value="rates_valuation" checked> 利率估值</label>
          <label><input type="checkbox" name="workbenchModule" value="breadth_concentration" checked> 广度集中度</label>
          <label><input type="checkbox" name="workbenchModule" value="liquidity" checked> 流动性</label>
        </div>
        <div class="run-actions">
          <button class="command-button" type="button" id="buildCommand">生成运行命令</button>
          <button class="run-now-button" type="button" id="runNow">运行完整报告</button>
          <button type="button" id="refreshJob">刷新状态</button>
          <button type="button" id="cancelJob">取消任务</button>
        </div>
        <p id="runStatus" class="run-status">运行按钮会调用本机 127.0.0.1 的 vNext control service；它会先保存人工数据，再串联生成报告。</p>
        <pre id="jobStatusPreview">尚无任务。</pre>
        <pre id="runCommandPreview">python3 src/main.py --models deepseek-v4-flash,deepseek-v4-pro --skip-report --disable-charts</pre>
        <pre id="workbenchCommandPreview">python3 src/interactive_chart_workbench.py --run-dir output/analysis/vnext/&lt;run_id&gt; --modules price_technical,volatility_credit,rates_valuation,breadth_concentration,liquidity</pre>
        <div class="artifact-grid">
          <div class="report-list">
            <h3>最新 brief</h3>
            {self._links(reports, '还没有生成过 native 报告。')}
          </div>
          <div class="report-list">
            <h3>最新 workbench</h3>
            {self._links(workbenches, '还没有生成过 workbench。')}
          </div>
          <div class="report-list">
            <h3>最新 run</h3>
            {self._links(runs, '还没有 vNext run 目录。')}
          </div>
          <div class="report-list">
            <h3>最新日志</h3>
            {self._links(control_logs, '还没有 control service 日志。')}
          </div>
        </div>
      </article>

      <article class="panel health-panel" id="health-panel">
        <div class="panel-head">
          <span>05</span>
          <div>
            <h2>运行日志 / 健康 / 安全</h2>
            <p>一键运行通过本地 control service 执行白名单命令；新闻只生成独立事件底账，不进入 L1-L5 输入上下文。</p>
          </div>
        </div>
        <div class="health-list" aria-label="数据源健康">
          <h3>数据源健康</h3>
          <div><b>Manual/Wind</b><span class="watch">可选高信任输入</span></div>
          <div><b>Damodaran ERPbymonth.xlsx</b><span class="good">官方月度优先</span></div>
          <div><b>WorldPERatio</b><span class="good">相对位置辅助</span></div>
          <div><b>Trendonify / bb-browser</b><span class="watch">隔离 sidecar，人工信任</span></div>
          <div><b>LLM diagnostics</b><span class="good">run 内写入诊断</span></div>
        </div>
        <div class="safety-box">
          <h3>一键运行安全方案</h3>
          <p>本地 control service 只接受项目白名单命令，日志写入 output/logs/control_service。静态页面仍不能绕过服务直接执行本地任务。</p>
        </div>
      </article>
    </section>
  </main>
  <script type="application/json" id="console-data">{_safe_script_json(payload)}</script>
  <script>{self._js()}</script>
</body>
</html>
"""

    def _css(self) -> str:
        return """
:root {
  --paper: oklch(0.967 0.008 86);
  --paper-quiet: oklch(0.94 0.012 86);
  --raised: oklch(0.992 0.005 86);
  --ink: oklch(0.19 0.014 80);
  --soft: oklch(0.37 0.018 80);
  --muted: oklch(0.50 0.018 80);
  --rule: oklch(0.82 0.014 82);
  --rule-strong: oklch(0.66 0.018 82);
  --accent: oklch(0.51 0.14 31);
  --accent-strong: oklch(0.42 0.13 31);
  --good: oklch(0.45 0.11 150);
  --watch: oklch(0.58 0.12 76);
  --risk: oklch(0.50 0.15 28);
  --radius: 8px;
  --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  --sans: Avenir Next, Helvetica Neue, PingFang SC, system-ui, sans-serif;
  --serif: Charter, Georgia, Songti SC, serif;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background:
    linear-gradient(180deg, var(--raised) 0, var(--paper) 420px, var(--paper) 100%);
  color: var(--ink);
  font-family: var(--sans);
  overflow-x: hidden;
}
p, li, h1, h2, h3, label, strong, span, a {
  overflow-wrap: anywhere;
}
p {
  word-break: break-word;
}
.console-shell {
  width: min(1240px, calc(100% - 32px));
  margin: 0 auto;
  padding: 24px 0 80px;
}
.hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 360px);
  gap: 32px;
  align-items: end;
  padding: 28px 0 22px;
  border-top: 2px solid var(--ink);
  border-bottom: 1px solid var(--rule);
}
.hero > * { min-width: 0; }
@media (max-width: 780px) { .hero { grid-template-columns: 1fr; } }
.eyebrow {
  margin: 0 0 8px;
  color: var(--accent);
  letter-spacing: .14em;
  text-transform: uppercase;
  font: 700 12px var(--sans);
}
h1 {
  margin: 0 0 10px;
  font: 650 58px/.98 var(--serif);
}
@media (max-width: 780px) { h1 { font-size: 38px; line-height: 1.04; } }
.hero p:last-child {
  max-width: 70ch;
  color: var(--soft);
  font-size: 16px;
  line-height: 1.7;
  line-break: anywhere;
  word-break: break-all;
}
.status-card,
.panel {
  background: var(--raised);
  border: 1px solid var(--rule);
  border-radius: var(--radius);
}
.status-card {
  padding: 18px 20px 20px;
  box-shadow: 0 1px 0 color-mix(in oklch, var(--ink) 7%, transparent);
}
.status-card span {
  color: var(--muted);
  font-size: 12px;
}
.status-card strong {
  display: block;
  margin: 4px 0 14px;
  font: 650 24px var(--serif);
}
.primary-link,
.secondary-link,
button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--ink);
  border-radius: 4px;
  background: var(--ink);
  color: var(--raised);
  padding: 8px 12px;
  text-decoration: none;
  font: 700 13px var(--sans);
  cursor: pointer;
  min-height: 38px;
  transition: background-color 160ms ease-out, border-color 160ms ease-out, color 160ms ease-out, transform 160ms ease-out;
}
.primary-link:hover,
.secondary-link:hover,
button:hover {
  transform: translateY(-1px);
}
.secondary-link {
  background: transparent;
  color: var(--ink);
  text-decoration: none;
}
.status-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.workflow-rail {
  position: sticky;
  top: 10px;
  z-index: 5;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0;
  margin: 16px 0 18px;
  border: 1px solid var(--rule);
  border-radius: var(--radius);
  background: color-mix(in oklch, var(--raised) 92%, transparent);
  backdrop-filter: blur(10px);
}
.workflow-rail a {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  gap: 8px;
  align-items: center;
  min-height: 48px;
  padding: 10px 14px;
  color: var(--soft);
  text-decoration: none;
  border-right: 1px solid var(--rule);
}
.workflow-rail a:last-child { border-right: 0; }
.workflow-rail b {
  font: 700 11px var(--mono);
  color: var(--accent);
}
.workflow-rail span {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font: 700 13px var(--sans);
}
.workflow-rail a:hover {
  background: var(--paper-quiet);
  color: var(--ink);
}
@media (max-width: 760px) {
  .workflow-rail {
    position: static;
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .workflow-rail a:nth-child(2) { border-right: 0; }
  .workflow-rail a:nth-child(-n + 2) { border-bottom: 1px solid var(--rule); }
}
.control-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 16px;
  margin-top: 18px;
  align-items: start;
}
.setup-panel { order: 1; grid-column: span 1; }
.model-panel { order: 2; grid-column: span 2; }
.manual-panel { order: 3; grid-column: 1 / -1; }
.run-panel { order: 4; grid-column: span 2; }
.health-panel { order: 5; }
@media (max-width: 1080px) {
  .control-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .model-panel,
  .manual-panel,
  .run-panel,
  .health-panel { grid-column: 1 / -1; }
}
@media (max-width: 760px) {
  .control-grid { grid-template-columns: minmax(0, 1fr); }
  .control-grid > * {
    grid-column: 1 / 2;
    grid-row: auto;
  }
}
.panel {
  padding: 18px 20px 20px;
  scroll-margin-top: 92px;
}
.run-panel {
  background:
    linear-gradient(180deg, color-mix(in oklch, var(--accent) 8%, var(--raised)), var(--raised) 35%);
}
.panel-head {
  display: flex;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 14px;
}
.panel-head > span {
  display: grid;
  place-items: center;
  width: 34px;
  height: 34px;
  border: 1px solid var(--ink);
  border-radius: 4px;
  font: 700 12px var(--mono);
}
h2 {
  margin: 0 0 3px;
  font: 650 22px var(--serif);
}
.panel-head p {
  margin: 0;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.5;
}
label {
  display: grid;
  gap: 6px;
  margin: 12px 0;
  color: var(--soft);
  font-size: 13px;
  font-weight: 650;
}
input[type="date"],
input[type="text"],
input[type="number"],
select,
textarea {
  width: 100%;
  border: 1px solid var(--rule);
  border-radius: 4px;
  background: oklch(0.987 0.006 86);
  color: var(--ink);
  padding: 9px 10px;
  font: 12px var(--mono);
  min-height: 38px;
  min-width: 0;
}
input:focus,
select:focus,
textarea:focus {
  outline: 2px solid color-mix(in oklch, var(--accent) 62%, transparent);
  outline-offset: 1px;
}
.field-grid,
.manual-form {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.field-grid label,
.manual-form label {
  margin: 0;
}
.field-grid .checkbox-field {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 8px;
  min-height: 38px;
  padding-top: 20px;
}
.field-grid .checkbox-field input {
  width: auto;
}
.metric-pair {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  border: 1px solid var(--rule);
  border-radius: 4px;
  background: oklch(0.987 0.006 86);
  padding: 10px;
  margin: 0;
}
.metric-pair legend {
  padding: 0 6px;
  color: var(--accent);
  font: 800 12px var(--sans);
  letter-spacing: .08em;
}
@media (max-width: 640px) {
  .field-grid,
  .manual-form,
  .metric-pair { grid-template-columns: 1fr; }
}
textarea {
  min-height: 240px;
  resize: vertical;
  line-height: 1.45;
}
.advanced-json {
  margin-top: 12px;
  border: 1px solid var(--rule);
  background: oklch(0.987 0.006 86);
  border-radius: 4px;
  padding: 8px;
}
.advanced-json summary {
  cursor: pointer;
  font: 700 13px var(--sans);
  color: var(--accent);
}
.validation-note {
  margin: 10px 0 0;
  color: var(--muted);
  font: 12px var(--mono);
}
.validation-note.is-warning { color: var(--watch); }
.button-row,
.run-actions,
.toggle-line,
.module-picker,
.mode-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.button-row button:not(:first-child),
.command-button {
  background: transparent;
  color: var(--ink);
}
.run-now-button {
  background: var(--accent);
  border-color: var(--accent);
  color: var(--raised);
}
.run-now-button:hover {
  background: var(--accent-strong);
  border-color: var(--accent-strong);
}
.run-status {
  margin: 10px 0 0;
  color: var(--muted);
  font: 12px var(--mono);
  line-height: 1.55;
}
.run-status.is-warning { color: var(--watch); }
.run-status.is-good { color: var(--good); }
.path-note {
  margin: 10px 0 0;
  color: var(--muted);
  font: 12px var(--mono);
  overflow-wrap: anywhere;
}
.segmented {
  display: grid;
  gap: 8px;
}
.segmented label,
.toggle-line label,
.module-picker label,
.mode-grid label {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--rule);
  border-radius: 4px;
  background: oklch(0.987 0.006 86);
  padding: 10px 12px;
  margin: 0;
}
.mode-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
.mode-grid label {
  min-height: 58px;
}
.custom-models { margin-top: 12px; }
.module-picker {
  margin: 14px 0;
}
.module-picker h3 {
  flex-basis: 100%;
}
.health-list {
  margin-top: 18px;
  display: grid;
  gap: 8px;
}
h3 {
  margin: 0 0 4px;
  font: 700 12px var(--sans);
  letter-spacing: .1em;
  text-transform: uppercase;
  color: var(--accent);
}
.health-list div {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  border-top: 1px solid var(--rule);
  padding-top: 8px;
  font-size: 13px;
}
.health-list span {
  font-family: var(--mono);
  font-size: 11px;
}
.good { color: var(--good); }
.watch { color: var(--watch); }
.legacy-note {
  margin: 10px 0 0;
  border: 1px solid color-mix(in oklch, var(--watch) 42%, var(--rule));
  border-radius: 4px;
  padding: 10px 12px;
  background: color-mix(in oklch, var(--watch) 10%, var(--raised));
  color: var(--soft);
  font-size: 12px;
  line-height: 1.6;
}
.source-calibration {
  margin-top: 14px;
  border-top: 1px solid var(--rule);
  padding-top: 14px;
}
.source-calibration p {
  margin: 2px 0 10px;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.55;
}
pre {
  overflow: auto;
  border: 1px solid var(--rule);
  border-radius: 4px;
  background: oklch(0.22 0.014 80);
  color: oklch(0.94 0.012 86);
  padding: 12px;
  font: 12px/1.55 var(--mono);
}
.report-list {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 14px;
}
.artifact-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 12px;
  margin-top: 14px;
}
@media (max-width: 760px) { .artifact-grid { grid-template-columns: 1fr; } }
.report-list h3 {
  flex-basis: 100%;
}
.report-list a,
.report-list span,
.empty-link {
  border: 1px solid var(--rule);
  border-radius: 4px;
  color: var(--ink);
  background: oklch(0.987 0.006 86);
  padding: 6px 8px;
  font: 12px var(--mono);
  text-decoration: none;
  overflow-wrap: anywhere;
}
.empty-link {
  color: var(--muted);
}
.safety-box {
  margin-top: 18px;
  border: 1px solid var(--rule);
  border-radius: 4px;
  padding: 12px;
  background: oklch(0.987 0.006 86);
}
.safety-box p {
  margin: 0;
  color: var(--soft);
  line-height: 1.65;
  font-size: 13px;
}
.browser-sidecar {
  margin-top: 16px;
  border: 1px solid var(--rule);
  border-radius: 6px;
  padding: 12px;
  background: oklch(0.987 0.006 86);
}
.browser-sidecar h3 {
  margin: 0 0 10px;
  font-size: 14px;
}
.browser-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
}
.browser-actions a {
  color: var(--accent);
  font-size: 13px;
}
"""

    def _js(self) -> str:
        return """
const data = JSON.parse(document.getElementById('console-data').textContent);
const manualJson = document.getElementById('manualJson');
const dataDate = document.getElementById('dataDate');
const preview = document.getElementById('runCommandPreview');
const workbenchPreview = document.getElementById('workbenchCommandPreview');
const validation = document.getElementById('manualValidation');
const runStatus = document.getElementById('runStatus');
const jobStatusPreview = document.getElementById('jobStatusPreview');
const browserStatus = document.getElementById('browserStatus');
const browserCommandPreview = document.getElementById('browserCommandPreview');
const newsStatus = document.getElementById('newsStatus');
const newsCommandPreview = document.getElementById('newsCommandPreview');
let activeJobId = '';
let activeBrowserJobId = '';
let activeNewsJobId = '';
let runPollTimer = null;
let openedArtifactForJob = '';
const controlOrigin = window.location.protocol.startsWith('http') ? window.location.origin : 'http://127.0.0.1:8765';

function artifactUrl(path) {
  if (!path) return '#';
  if (window.location.protocol.startsWith('http')) {
    return `${controlOrigin}/artifact?path=${encodeURIComponent(path)}`;
  }
  return path.startsWith('file://') ? path : `file://${path}`;
}

function wireArtifactLinks() {
  document.querySelectorAll('[data-artifact-path]').forEach(link => {
    const path = link.getAttribute('data-artifact-path') || '';
    link.href = artifactUrl(path);
    link.target = '_blank';
    link.rel = 'noopener';
  });
}

wireArtifactLinks();

function parseJson(text, fallback) {
  try { return JSON.parse(text || ''); } catch (error) { return fallback; }
}

function setManualField(name, value) {
  const node = document.querySelector(`[data-manual-field="${name}"]`);
  if (!node) return;
  node.value = value === null || value === undefined ? '' : String(value);
}

function manualMetric(payload, key) {
  return ((payload.metrics || {})[key] || {});
}

function applyManualPayloadToForm(payload) {
  const dateValue = payload.date || new Date().toISOString().slice(0, 10);
  dataDate.value = dateValue;
  setManualField('date', dateValue);
  const valuation = manualMetric(payload, 'get_ndx_pe_and_earnings_yield');
  const erp = manualMetric(payload, 'get_damodaran_us_implied_erp');
  const quality = valuation.data_quality || {};
  setManualField('source', valuation.source_name || erp.source_name || '');
  setManualField('confidence', ((quality.coverage || {}).confidence) || '');
  const valuationValue = valuation.value || {};
  const erpValue = erp.value || {};
  setManualField('pe', valuationValue.PE_TTM);
  setManualField('pe_percentile_5y', valuationValue.PE_TTM_percentile_5y);
  setManualField('pe_percentile_10y', valuationValue.PE_TTM_percentile_10y);
  setManualField('pb', valuationValue.PB);
  setManualField('pb_percentile_5y', valuationValue.PB_percentile_5y);
  setManualField('pb_percentile_10y', valuationValue.PB_percentile_10y);
  setManualField('ps', valuationValue.PS_TTM);
  setManualField('ps_percentile_5y', valuationValue.PS_TTM_percentile_5y);
  setManualField('ps_percentile_10y', valuationValue.PS_TTM_percentile_10y);
  setManualField('erp', erpValue.manual_erp);
  setManualField('erp_percentile_5y', erpValue.manual_erp_percentile_5y);
  setManualField('erp_percentile_10y', erpValue.manual_erp_percentile_10y);
}

const initialManualPayload = parseJson(data.initialManualData, parseJson(data.manualTemplate, {}));
applyManualPayloadToForm(initialManualPayload);

function currentModels() {
  const selected = document.querySelector('input[name="modelMode"]:checked');
  if (selected && selected.value === 'custom') {
    return document.getElementById('customModels').value.trim() || 'deepseek-v4-flash,deepseek-v4-pro';
  }
  return selected ? selected.value : 'deepseek-v4-flash,deepseek-v4-pro';
}

function selectedRunMode() {
  const selected = document.querySelector('input[name="runMode"]:checked');
  return selected ? selected.value : 'vnext_full';
}

function pathValue(id) {
  return document.getElementById(id).value.trim();
}

function modeCommand(mode, models) {
  const dataPath = pathValue('dataJsonPath') || data.latestDataJson || '';
  const runDir = pathValue('runDirPath') || 'output/analysis/vnext/<run_id>';
  const modules = Array.from(document.querySelectorAll('input[name="workbenchModule"]:checked')).map(node => node.value).join(',') || 'price_technical';
  const base = ['python3 src/main.py', `--models ${models}`];
  const full = ['python3 src/console_run_all.py', `--models ${models}`, `--workbench-modules ${modules}`];
  if (document.getElementById('historicalDateMode').checked && dataDate.value) {
    base.push(`--date ${dataDate.value}`);
    full.push(`--date ${dataDate.value}`);
  }
  if (dataPath && mode !== 'collect_data') {
    base.push(`--data-json ${dataPath}`);
    full.push(`--data-json ${dataPath}`);
  }
  if (document.getElementById('skipLegacyReport').checked) {
    base.push('--skip-report');
    full.push('--skip-legacy-report');
  }
  if (document.getElementById('disableCharts').checked && !document.getElementById('enableLegacyCharts').checked) base.push('--disable-charts');
  if (document.getElementById('enableLegacyCharts').checked) {
    base.push('--enable-legacy-charts');
    full.push('--enable-legacy-charts');
  }
  if (document.getElementById('enableNews').checked) {
    base.push('--enable-news');
    full.push('--enable-news');
  }
  if (mode === 'native_brief') {
    return `python3 src/agent_analysis/vnext_reporter.py --run-dir ${runDir} --template brief`;
  }
  if (mode === 'workbench_only') {
    return `python3 src/interactive_chart_workbench.py --run-dir ${runDir} --modules ${modules}`;
  }
  if (mode === 'logs_only') {
    return '# 日志位置：output/logs/control_service/*.log；运行任务后，下方状态区会显示最新日志尾部。';
  }
  if (mode === 'analyze_existing') {
    return dataPath ? base.join(' ') : '# 请先填写“已有数据 JSON”，再基于同源数据进入 vNext 五层分析。';
  }
  if (mode === 'collect_data') {
    return base.concat(['--collect-only']).join(' ');
  }
  return full.join(' ');
}

function numberOrNull(value) {
  if (value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function buildManualPayload() {
  const payload = parseJson(data.manualTemplate, {});
  payload.active = true;
  const fields = {};
  document.querySelectorAll('[data-manual-field]').forEach(input => {
    const raw = input.value.trim();
    fields[input.dataset.manualField] = input.type === 'number' ? numberOrNull(raw) : raw;
  });
  if (document.getElementById('trustBbBrowser').checked && !fields.source) {
    fields.source = 'Trendonify sidecar (user trusted)';
    payload.browser_sidecar = {
      source: 'trendonify_ndx_valuation',
      output_path: data.browserSidecarPath,
      user_trusted: true,
      usage_boundary: 'Manual confirmation source only; not an automatic L4 main-chain source.'
    };
  }
  payload.date = fields.date || dataDate.value || payload.date || '';
  const valuation = payload.metrics.get_ndx_pe_and_earnings_yield;
  const gap = payload.metrics.get_equity_risk_premium;
  const erp = payload.metrics.get_damodaran_us_implied_erp;
  const setMetricSource = (metric) => {
    if (fields.source) metric.source_name = fields.source;
    if (fields.date && metric.data_quality) metric.data_quality.data_date = fields.date;
    if (fields.confidence && metric.data_quality) {
      metric.data_quality.coverage = metric.data_quality.coverage || {};
      metric.data_quality.coverage.confidence = fields.confidence;
    }
  };
  [valuation, gap, erp].forEach(setMetricSource);
  valuation.value.PE_TTM = fields.pe;
  valuation.value.PB = fields.pb;
  valuation.value.PS_TTM = fields.ps;
  valuation.value.PE_TTM_percentile_5y = fields.pe_percentile_5y;
  valuation.value.PE_TTM_percentile_10y = fields.pe_percentile_10y;
  valuation.value.PB_percentile_5y = fields.pb_percentile_5y;
  valuation.value.PB_percentile_10y = fields.pb_percentile_10y;
  valuation.value.PS_TTM_percentile_5y = fields.ps_percentile_5y;
  valuation.value.PS_TTM_percentile_10y = fields.ps_percentile_10y;
  erp.value.manual_erp = fields.erp;
  erp.value.manual_erp_percentile_5y = fields.erp_percentile_5y;
  erp.value.manual_erp_percentile_10y = fields.erp_percentile_10y;
  return payload;
}

function validateManualPayload(payload) {
  const warnings = [];
  const valuation = payload.metrics.get_ndx_pe_and_earnings_yield.value;
  ['PE_TTM_percentile_5y', 'PE_TTM_percentile_10y', 'PB_percentile_5y', 'PB_percentile_10y', 'PS_TTM_percentile_5y', 'PS_TTM_percentile_10y'].forEach(key => {
    const value = valuation[key];
    if (value !== undefined && value !== null && (value < 0 || value > 100)) warnings.push(`${key} 应在 0-100`);
  });
  ['manual_erp_percentile_5y', 'manual_erp_percentile_10y'].forEach(key => {
    const value = payload.metrics.get_damodaran_us_implied_erp.value[key];
    if (value !== undefined && value !== null && (value < 0 || value > 100)) warnings.push(`${key} 应在 0-100`);
  });
  ['PE_TTM', 'PB', 'PS_TTM'].forEach(key => {
    const value = valuation[key];
    if (value !== undefined && value !== null && value < 0) warnings.push(`${key} 不应为负数`);
  });
  return warnings;
}

function syncManualPreview() {
  const payload = buildManualPayload();
  const warnings = validateManualPayload(payload);
  manualJson.value = JSON.stringify(payload, null, 2);
  validation.textContent = warnings.length ? warnings.join('；') : '人工数据预览已同步，空值会清除对应人工覆盖。';
  validation.classList.toggle('is-warning', Boolean(warnings.length));
}

function buildCommand() {
  const mode = selectedRunMode();
  const models = currentModels();
  preview.textContent = modeCommand(mode, models);
  const modules = Array.from(document.querySelectorAll('input[name="workbenchModule"]:checked')).map(node => node.value);
  const runDir = pathValue('runDirPath') || 'output/analysis/vnext/<run_id>';
  workbenchPreview.textContent = `python3 src/interactive_chart_workbench.py --run-dir ${runDir} --modules ${modules.join(',') || 'price_technical'}`;
  browserCommandPreview.textContent = `python3 src/browser_sidecar.py --source trendonify_valuation --output output/browser_sidecar/trendonify_ndx_valuation.json${document.getElementById('trustBbBrowser').checked ? ' --trusted' : ''}`;
  newsCommandPreview.textContent = 'python3 src/news_event_ledger.py --output output/analysis/news_event_ledger.json';
}

document.querySelectorAll('input[name="modelMode"], input[name="runMode"], #customModels, #dataJsonPath, #runDirPath, #historicalDateMode, #skipLegacyReport, #disableCharts, #enableLegacyCharts, #enableNews, #trustBbBrowser, input[name="workbenchModule"]')
  .forEach((node) => node.addEventListener('change', buildCommand));
document.getElementById('trustBbBrowser').addEventListener('change', syncManualPreview);
document.querySelectorAll('#customModels, #dataJsonPath, #runDirPath').forEach((node) => node.addEventListener('input', buildCommand));
document.querySelectorAll('[data-manual-field]').forEach((node) => node.addEventListener('input', syncManualPreview));
dataDate.addEventListener('change', () => {
  document.querySelector('[data-manual-field="date"]').value = dataDate.value;
  syncManualPreview();
  buildCommand();
});

document.getElementById('buildCommand').addEventListener('click', buildCommand);
async function saveManualData(statusNode) {
  syncManualPreview();
  try {
    const response = await fetch(`${controlOrigin}/manual-data`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ manual_json: manualJson.value }),
    });
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.message || `HTTP ${response.status}`);
    if (statusNode) {
      statusNode.textContent = `人工数据已保存：${result.path || data.manualPath}`;
      statusNode.className = 'run-status is-good';
    }
    return true;
  } catch (error) {
    if (statusNode) {
      statusNode.textContent = '未连接 control service，已保留页面预览；运行时会再次尝试保存。';
      statusNode.className = 'run-status is-warning';
    }
    return false;
  }
}

async function submitControlCommand(command, statusNode) {
  if (!command || command.startsWith('#')) {
    statusNode.textContent = command || '没有可运行命令。';
    statusNode.className = 'run-status is-warning';
    return null;
  }
  statusNode.textContent = '正在尝试连接本机 vNext control service...';
  statusNode.className = 'run-status';
  try {
    const confirmed = window.confirm('确认通过本机 control service 执行这条白名单命令？');
    if (!confirmed) {
      statusNode.textContent = '已取消，未执行命令。';
      statusNode.classList.add('is-warning');
      return null;
    }
    const response = await fetch(`${controlOrigin}/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        command,
        confirmed: true,
        workbench_command: workbenchPreview.textContent.trim(),
        manual_json: manualJson.value,
      }),
    });
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.message || `HTTP ${response.status}`);
    const job = result.job || {};
    statusNode.textContent = `${result.message || '已提交运行。'} job_id=${job.job_id || ''}`;
    statusNode.classList.add('is-good');
    return job.job_id || null;
  } catch (error) {
    statusNode.textContent = `没有执行命令：${error.message || '未检测到本机 control service。请先启动受控服务。'}`;
    statusNode.classList.add('is-warning');
    return null;
  }
}

async function refreshJob(jobId, statusNode) {
  if (!jobId) {
    statusNode.textContent = '尚无可刷新的任务。';
    statusNode.classList.add('is-warning');
    return null;
  }
  let result;
  try {
    const response = await fetch(`${controlOrigin}/status/${encodeURIComponent(jobId)}`);
    result = await response.json();
  } catch (error) {
    statusNode.textContent = '无法连接 control service，状态刷新失败。';
    statusNode.className = 'run-status is-warning';
    return null;
  }
  const job = result.job || {};
  jobStatusPreview.textContent = JSON.stringify({
    job_id: job.job_id,
    status: job.status,
    exit_code: job.exit_code,
    log_path: job.log_path,
    failure_reason: job.failure_reason,
    log_tail: job.log_tail
  }, null, 2);
  statusNode.textContent = `任务状态：${job.status || 'unknown'}；日志：${job.log_path || '无'}`;
  statusNode.className = 'run-status';
  if (job.status === 'completed') statusNode.classList.add('is-good');
  if (job.status === 'failed' || job.status === 'canceled') statusNode.classList.add('is-warning');
  return job;
}

async function openLatestProductForMode(jobId) {
  if (!jobId || openedArtifactForJob === jobId) return;
  try {
    const response = await fetch(`${controlOrigin}/latest-product`);
    const result = await response.json();
    const summary = result.summary || {};
    const mode = selectedRunMode();
    const preferred = mode === 'workbench_only' ? summary.workbench : (summary.native_brief || summary.report_path || summary.workbench);
    if (!preferred) return;
    openedArtifactForJob = jobId;

    // Build links for all available reports
    const reports = [];
    if (summary.native_brief) reports.push({ label: 'Brief 报告', path: summary.native_brief });
    if (summary.workbench) reports.push({ label: 'Workbench', path: summary.workbench });
    if (summary.report_path && summary.report_path !== summary.native_brief) reports.push({ label: '完整报告', path: summary.report_path });

    // Inject clickable links into status area
    const linksHtml = reports.map(r =>
      `<a href="${artifactUrl(r.path)}" target="_blank" rel="noopener" style="margin-left:8px;padding:2px 8px;border:1px solid #2563eb;border-radius:4px;text-decoration:none;color:#2563eb;font-size:13px;">${r.label}</a>`
    ).join('');
    runStatus.innerHTML = `任务已完成。可用报告：${linksHtml}`;

    // Try auto-open primary report (may be blocked by popup blocker)
    const w = window.open(artifactUrl(preferred), '_blank', 'noopener');
    if (!w || w.closed || typeof w.closed === 'undefined') {
      runStatus.innerHTML += `<br><span style="color:#b45309;font-size:12px;">弹窗可能被浏览器拦截，请点击上方链接手动打开。</span>`;
    }
  } catch (error) {
    runStatus.textContent = `${runStatus.textContent}；获取报告失败：${error.message || error}`;
  }
}

function startJobAutoRefresh(jobId, statusNode) {
  if (runPollTimer) window.clearInterval(runPollTimer);
  runPollTimer = window.setInterval(async () => {
    const job = await refreshJob(jobId, statusNode);
    if (!job || !['completed', 'failed', 'canceled', 'unknown'].includes(job.status)) return;
    window.clearInterval(runPollTimer);
    runPollTimer = null;
    if (statusNode === runStatus && job.status === 'completed') {
      openLatestProductForMode(jobId);
    }
  }, 5000);
}

document.getElementById('runNow').addEventListener('click', async () => {
  buildCommand();
  const command = preview.textContent.trim();
  activeJobId = await submitControlCommand(command, runStatus) || activeJobId;
  if (activeJobId) {
    refreshJob(activeJobId, runStatus);
    startJobAutoRefresh(activeJobId, runStatus);
  }
});
document.getElementById('refreshJob').addEventListener('click', () => refreshJob(activeJobId, runStatus));
document.getElementById('cancelJob').addEventListener('click', async () => {
  if (!activeJobId) {
    runStatus.textContent = '尚无可取消的任务。';
    runStatus.classList.add('is-warning');
    return;
  }
  await fetch(`${controlOrigin}/cancel/${encodeURIComponent(activeJobId)}`, { method: 'POST' });
  refreshJob(activeJobId, runStatus);
});
document.getElementById('runBrowserSidecar').addEventListener('click', async () => {
  buildCommand();
  activeBrowserJobId = await submitControlCommand(browserCommandPreview.textContent.trim(), browserStatus) || activeBrowserJobId;
  if (activeBrowserJobId) refreshJob(activeBrowserJobId, browserStatus);
});
document.getElementById('runNewsLedger').addEventListener('click', async () => {
  buildCommand();
  activeNewsJobId = await submitControlCommand(newsCommandPreview.textContent.trim(), newsStatus) || activeNewsJobId;
  if (activeNewsJobId) refreshJob(activeNewsJobId, newsStatus);
});
document.getElementById('openBrowserSidecar').addEventListener('click', () => {
  window.open(`file://${data.browserSidecarPath}`, '_blank');
});
document.getElementById('resetManual').addEventListener('click', () => {
  applyManualPayloadToForm(parseJson(data.manualTemplate, {}));
  syncManualPreview();
});
document.getElementById('downloadManual').addEventListener('click', async () => {
  const saved = await saveManualData(runStatus);
  if (saved) return;
  const blob = new Blob([manualJson.value], { type: 'application/json;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'manual_data.local.json';
  link.click();
  URL.revokeObjectURL(url);
});
async function loadManualDataFromService() {
  try {
    const response = await fetch(`${controlOrigin}/manual-data`);
    const result = await response.json();
    if (response.ok && result.ok && result.manual_data) {
      applyManualPayloadToForm(result.manual_data);
      validation.textContent = `已载入上次人工数据：${result.path || data.manualPath}`;
    }
  } catch (error) {
    // Static file fallback: embedded data from generation time is already applied.
  }
}
loadManualDataFromService().finally(() => {
  syncManualPreview();
  buildCommand();
});
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate the vNext research console HTML.")
    parser.add_argument("--output", help="Optional output HTML path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(ResearchConsoleGenerator().run(output_path=args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
