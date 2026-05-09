from __future__ import annotations

import argparse
import html
import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .config import path_config
    from .manual_data import DEFAULT_MANUAL_DATA, get_manual_data_local_path
except ImportError:
    from config import path_config
    from manual_data import DEFAULT_MANUAL_DATA, get_manual_data_local_path


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
        reports = sorted(
            self.reports_dir.glob("vnext_research_ui_*.html"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        return reports[:6]

    def _latest_workbenches(self) -> List[Path]:
        workbenches = sorted(
            self.reports_dir.glob("vnext_interactive_charts_*.html"),
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

    def _latest_visual_summaries(self) -> List[Path]:
        visual_root = self.reports_dir / "visual_regression"
        if not visual_root.exists():
            return []
        return sorted(visual_root.glob("**/visual_regression_summary.json"), key=lambda path: path.stat().st_mtime, reverse=True)[:4]

    def _links(self, paths: List[Path], empty_text: str) -> str:
        if not paths:
            return f'<span class="empty-link">{_escape(empty_text)}</span>'
        return "".join(f'<a href="{_escape(path.resolve().as_uri())}">{_escape(path.name)}</a>' for path in paths)

    def _manual_template_json(self) -> str:
        template = json.loads(json.dumps(DEFAULT_MANUAL_DATA, ensure_ascii=False))
        template["active"] = True
        template["date"] = datetime.now().strftime("%Y-%m-%d")
        return json.dumps(template, ensure_ascii=False, indent=2)

    def _render(self) -> str:
        manual_template = self._manual_template_json()
        reports = self._latest_reports()
        workbenches = self._latest_workbenches()
        runs = self._latest_runs()
        visual_summaries = self._latest_visual_summaries()
        latest_report = reports[0] if reports else None
        latest_workbench = workbenches[0] if workbenches else None
        latest_href = latest_report.resolve().as_uri() if latest_report else "#"
        latest_workbench_href = latest_workbench.resolve().as_uri() if latest_workbench else "#"
        manual_path = get_manual_data_local_path()
        payload = json.dumps(
            {
                "manualTemplate": manual_template,
                "manualPath": manual_path,
                "latestReport": str(latest_report or ""),
                "latestRun": str(runs[0] if runs else ""),
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
          <a class="primary-link" href="{_escape(latest_href)}">打开最新报告</a>
          <a class="secondary-link" href="{_escape(latest_workbench_href)}">打开 workbench</a>
        </div>
      </aside>
    </section>

    <section class="control-grid">
      <article class="panel">
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
          <label>已有数据 JSON <input id="dataJsonPath" type="text" placeholder="output/data/data_collected_YYYYMMDD_live.json"></label>
          <label>已有 run 目录 <input id="runDirPath" type="text" value="{_escape(str(runs[0]) if runs else '')}" placeholder="output/analysis/vnext/<run_id>"></label>
        </div>
      </article>

      <article class="panel manual-panel">
        <div class="panel-head">
          <span>02</span>
          <div>
            <h2>人工 / Wind 数据</h2>
            <p>结构化录入高信任锚。空字段不会覆盖自动采集结果。</p>
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
          <button type="button" id="downloadManual">保存人工模板</button>
          <button type="button" id="resetManual">恢复模板</button>
        </div>
        <p class="path-note">目标文件：{_escape(manual_path)}</p>
      </article>

      <article class="panel">
        <div class="panel-head">
          <span>03</span>
          <div>
            <h2>模型与 vNext 流程</h2>
            <p>按 vNext 当前架构组织：采集、五层分析、native brief、workbench 和视觉回归。</p>
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
          <label><input type="radio" name="runMode" value="visual_check"> 视觉回归</label>
        </div>
      </article>

      <article class="panel">
        <div class="panel-head">
          <span>04</span>
          <div>
            <h2>数据源 / 功能开关</h2>
            <p>把可选功能集中管理；旧版 HTML 仅保留兼容入口，默认不建议使用。</p>
          </div>
        </div>
        <div class="toggle-line">
          <label><input id="skipLegacyReport" type="checkbox" checked> 不生成旧版 HTML</label>
          <label><input id="disableCharts" type="checkbox" checked> 不生成旧版 charts</label>
          <label><input id="enableNews" type="checkbox"> 生成官方事件底账</label>
          <label><input id="enableTrendonify" type="checkbox" disabled> Trendonify 暂缓</label>
          <label><input id="enableLegacyCharts" type="checkbox"> 临时启用旧版 charts</label>
        </div>
        <p class="legacy-note">旧版 HTML 是过渡期兼容产物：线性长页、审计跳转弱、审美已过时。vNext 默认入口应是 native brief 和 workbench。</p>
        <div class="module-picker" aria-label="交互工作台模块">
          <h3>交互工作台模块</h3>
          <label><input type="checkbox" name="workbenchModule" value="price_technical" checked> 价格技术</label>
          <label><input type="checkbox" name="workbenchModule" value="volatility_credit" checked> 波动信用</label>
          <label><input type="checkbox" name="workbenchModule" value="rates_valuation" checked> 利率估值</label>
          <label><input type="checkbox" name="workbenchModule" value="breadth_concentration" checked> 广度集中度</label>
          <label><input type="checkbox" name="workbenchModule" value="liquidity" checked> 流动性</label>
        </div>
        <label>L5 默认预设
          <select id="l5Preset">
            <option value="simple_price">简洁价格</option>
            <option value="trend_ma">趋势均线</option>
            <option value="volatility_bands">波动区间</option>
            <option value="volume_confirmation">量价确认</option>
            <option value="full_stack">全部指标</option>
          </select>
        </label>
      </article>

      <article class="panel run-panel">
        <div class="panel-head">
          <span>05</span>
          <div>
            <h2>输出与工作台</h2>
            <p>浏览器默认不执行本地任务，只生成可审计命令和入口。</p>
          </div>
        </div>
        <div class="run-actions">
          <button class="command-button" type="button" id="buildCommand">生成运行命令</button>
          <button class="run-now-button" type="button" id="runNow">运行</button>
        </div>
        <p id="runStatus" class="run-status">运行按钮会调用本机 127.0.0.1 的 vNext control service；未启动服务时不会执行任何命令。</p>
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
            <h3>视觉回归</h3>
            {self._links(visual_summaries, '还没有 visual regression summary。')}
          </div>
        </div>
      </article>

      <article class="panel health-panel">
        <div class="panel-head">
          <span>06</span>
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
          <div><b>Trendonify</b><span class="watch">暂缓，不静默 fallback</span></div>
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
  --paper: #f3f2ee;
  --raised: #fbfaf7;
  --ink: #171714;
  --soft: #4b4841;
  --muted: #777166;
  --rule: #d6d0c3;
  --accent: #9a3412;
  --good: #17633a;
  --watch: #9a5b12;
  --radius: 8px;
  --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  --sans: Avenir Next, Helvetica Neue, PingFang SC, system-ui, sans-serif;
  --serif: Charter, Georgia, Songti SC, serif;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: var(--sans);
}
.console-shell {
  width: min(1180px, calc(100% - 32px));
  margin: 0 auto;
  padding: 28px 0 80px;
}
.hero {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(260px, 340px);
  gap: 24px;
  align-items: end;
  padding: 32px 0 24px;
  border-top: 2px solid var(--ink);
  border-bottom: 1px solid var(--rule);
}
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
  font: 650 clamp(34px, 7vw, 76px)/.95 var(--serif);
}
.hero p:last-child {
  max-width: 680px;
  color: var(--soft);
  font-size: 16px;
  line-height: 1.7;
}
.status-card,
.panel {
  background: var(--raised);
  border: 1px solid var(--rule);
  border-radius: var(--radius);
}
.status-card {
  padding: 18px 20px;
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
.control-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(0, 1fr) minmax(300px, .85fr);
  gap: 16px;
  margin-top: 18px;
}
.run-panel { grid-column: span 2; }
.health-panel { grid-row: span 2; }
@media (max-width: 1080px) {
  .control-grid { grid-template-columns: 1fr 1fr; }
  .run-panel,
  .health-panel { grid-column: 1 / -1; }
}
@media (max-width: 760px) {
  .control-grid { grid-template-columns: 1fr; }
}
.panel {
  padding: 18px 20px;
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
  border-radius: 50%;
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
  background: #fffefa;
  color: var(--ink);
  padding: 9px 10px;
  font: 12px var(--mono);
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
.metric-pair {
  grid-column: 1 / -1;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
  border: 1px solid var(--rule);
  border-radius: 4px;
  background: #fffefa;
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
  background: #fffefa;
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
  color: #fffefa;
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
  background: #fffefa;
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
  border-left: 3px solid var(--watch);
  padding-left: 10px;
  color: var(--soft);
  font-size: 12px;
  line-height: 1.6;
}
pre {
  overflow: auto;
  border: 1px solid var(--rule);
  border-radius: 4px;
  background: #20201c;
  color: #f5f1e7;
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
  background: #fffefa;
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
  background: #fffefa;
}
.safety-box p {
  margin: 0;
  color: var(--soft);
  line-height: 1.65;
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

dataDate.value = new Date().toISOString().slice(0, 10);
document.querySelector('[data-manual-field="date"]').value = dataDate.value;

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
  const dataPath = pathValue('dataJsonPath');
  const runDir = pathValue('runDirPath') || 'output/analysis/vnext/<run_id>';
  const base = ['python3 src/main.py', `--models ${models}`];
  if (dataPath) base.push(`--data-json ${dataPath}`);
  if (document.getElementById('skipLegacyReport').checked) base.push('--skip-report');
  if (document.getElementById('disableCharts').checked && !document.getElementById('enableLegacyCharts').checked) base.push('--disable-charts');
  if (document.getElementById('enableLegacyCharts').checked) base.push('--enable-legacy-charts');
  if (document.getElementById('enableNews').checked) base.push('--enable-news');
  if (mode === 'native_brief') {
    return `python3 src/agent_analysis/vnext_reporter.py --run-dir ${runDir} --template brief`;
  }
  if (mode === 'workbench_only') {
    return `python3 src/interactive_chart_workbench.py --run-dir ${runDir} --modules price_technical,volatility_credit,rates_valuation,breadth_concentration,liquidity`;
  }
  if (mode === 'visual_check') {
    return `python3 src/report_visual_regression.py --brief-html output/reports/<brief.html> --workbench-html output/reports/<workbench.html> --output-dir output/reports/visual_regression/<run_id>`;
  }
  if (mode === 'analyze_existing') {
    return dataPath ? base.concat(['--skip-report']).join(' ') : '# 请先填写“已有数据 JSON”，再基于同源数据进入 vNext 五层分析。';
  }
  if (mode === 'collect_data') {
    return '# 只采集数据需要后续拆出 collector-only CLI 或本地 control service；当前 vNext CLI 仍以完整 run 产生同源数据。\\n' + base.join(' ');
  }
  return base.join(' ');
}

function numberOrNull(value) {
  if (value === '') return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function buildManualPayload() {
  const payload = JSON.parse(data.manualTemplate);
  payload.active = true;
  const fields = {};
  document.querySelectorAll('[data-manual-field]').forEach(input => {
    const raw = input.value.trim();
    if (!raw) return;
    fields[input.dataset.manualField] = input.type === 'number' ? numberOrNull(raw) : raw;
  });
  if (fields.date) payload.date = fields.date;
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
  if (fields.pe !== undefined) valuation.value.PE_TTM = fields.pe;
  if (fields.pb !== undefined) valuation.value.PB = fields.pb;
  if (fields.ps !== undefined) valuation.value.PS_TTM = fields.ps;
  if (fields.pe_percentile_5y !== undefined) valuation.value.PE_TTM_percentile_5y = fields.pe_percentile_5y;
  if (fields.pe_percentile_10y !== undefined) valuation.value.PE_TTM_percentile_10y = fields.pe_percentile_10y;
  if (fields.pb_percentile_5y !== undefined) valuation.value.PB_percentile_5y = fields.pb_percentile_5y;
  if (fields.pb_percentile_10y !== undefined) valuation.value.PB_percentile_10y = fields.pb_percentile_10y;
  if (fields.ps_percentile_5y !== undefined) valuation.value.PS_TTM_percentile_5y = fields.ps_percentile_5y;
  if (fields.ps_percentile_10y !== undefined) valuation.value.PS_TTM_percentile_10y = fields.ps_percentile_10y;
  if (fields.erp !== undefined) {
    erp.value.manual_erp = fields.erp;
  }
  if (fields.erp_percentile_5y !== undefined) {
    erp.value.manual_erp_percentile_5y = fields.erp_percentile_5y;
  }
  if (fields.erp_percentile_10y !== undefined) {
    erp.value.manual_erp_percentile_10y = fields.erp_percentile_10y;
  }
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
  validation.textContent = warnings.length ? warnings.join('；') : '人工数据预览已同步，空字段不会覆盖。';
  validation.classList.toggle('is-warning', Boolean(warnings.length));
}

function buildCommand() {
  const mode = selectedRunMode();
  const models = currentModels();
  preview.textContent = modeCommand(mode, models);
  const modules = Array.from(document.querySelectorAll('input[name="workbenchModule"]:checked')).map(node => node.value);
  const runDir = pathValue('runDirPath') || 'output/analysis/vnext/<run_id>';
  workbenchPreview.textContent = `python3 src/interactive_chart_workbench.py --run-dir ${runDir} --modules ${modules.join(',') || 'price_technical'}`;
}

document.querySelectorAll('input[name="modelMode"], input[name="runMode"], #customModels, #dataJsonPath, #runDirPath, #skipLegacyReport, #disableCharts, #enableLegacyCharts, #enableNews, #l5Preset, input[name="workbenchModule"]')
  .forEach((node) => node.addEventListener('change', buildCommand));
document.querySelectorAll('#customModels, #dataJsonPath, #runDirPath').forEach((node) => node.addEventListener('input', buildCommand));
document.querySelectorAll('[data-manual-field]').forEach((node) => node.addEventListener('input', syncManualPreview));
dataDate.addEventListener('change', () => {
  document.querySelector('[data-manual-field="date"]').value = dataDate.value;
  syncManualPreview();
  buildCommand();
});

document.getElementById('buildCommand').addEventListener('click', buildCommand);
document.getElementById('runNow').addEventListener('click', async () => {
  buildCommand();
  const command = preview.textContent.trim();
  runStatus.textContent = '正在尝试连接本机 vNext control service...';
  runStatus.className = 'run-status';
  try {
    const response = await fetch('http://127.0.0.1:8765/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        command,
        workbench_command: workbenchPreview.textContent.trim(),
        manual_json: manualJson.value,
      }),
    });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const result = await response.json();
    runStatus.textContent = result.message || '已提交运行。请在服务日志里查看进度。';
    runStatus.classList.add('is-good');
  } catch (error) {
    runStatus.textContent = '未检测到本机 control service，因此没有执行命令。下一步需要启动受控服务，或使用下方命令手动运行。';
    runStatus.classList.add('is-warning');
  }
});
document.getElementById('resetManual').addEventListener('click', () => {
  manualJson.value = data.manualTemplate;
  document.querySelectorAll('[data-manual-field]').forEach(input => { input.value = ''; });
  document.querySelector('[data-manual-field="date"]').value = dataDate.value;
  syncManualPreview();
});
document.getElementById('downloadManual').addEventListener('click', () => {
  const blob = new Blob([manualJson.value], { type: 'application/json;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = 'manual_data.local.json';
  link.click();
  URL.revokeObjectURL(url);
});
syncManualPreview();
buildCommand();
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
