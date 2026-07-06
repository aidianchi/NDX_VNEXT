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
    """Generate a self-contained simple launcher for vNext runs."""

    def __init__(self, reports_dir: Optional[str | Path] = None) -> None:
        self.reports_dir = Path(reports_dir or path_config.reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def run(self, output_path: Optional[str | Path] = None) -> str:
        destination = Path(output_path) if output_path else self.reports_dir / "vnext_research_console.html"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(self._render(), encoding="utf-8")
        return str(destination)

    def _latest_reports(self) -> List[Path]:
        candidates = {
            path.resolve(): path
            for path in list(self.reports_dir.glob("vnext_*.html"))
            + list(self.reports_dir.glob("vnext_research_ui_*.html"))
        }
        reports = sorted(candidates.values(), key=lambda path: path.stat().st_mtime, reverse=True)
        return [path for path in reports if "workbench" not in path.name and "console" not in path.name][:6]

    def _latest_workbenches(self) -> List[Path]:
        candidates = {
            path.resolve(): path
            for path in list(self.reports_dir.glob("vnext_workbench_*.html"))
            + list(self.reports_dir.glob("vnext_interactive_charts_*.html"))
        }
        return sorted(candidates.values(), key=lambda path: path.stat().st_mtime, reverse=True)[:4]

    def _latest_runs(self) -> List[Path]:
        run_root = Path(path_config.analysis_dir) / "vnext"
        if not run_root.exists():
            return []
        return sorted([path for path in run_root.iterdir() if path.is_dir()], key=lambda path: path.stat().st_mtime, reverse=True)[:5]

    def _latest_data_jsons(self) -> List[Path]:
        data_root = Path(path_config.data_dir)
        if not data_root.exists():
            return []
        return sorted(data_root.glob("data_collected_v9_*.json"), key=lambda path: path.stat().st_mtime, reverse=True)[:5]

    def _data_json_meta(self, path: Optional[Path]) -> Dict[str, Any]:
        if not path:
            return {}
        meta: Dict[str, Any] = {
            "path": str(path),
            "name": path.name,
            "modified_at": datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
        }
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return meta
        timestamp = payload.get("timestamp_utc") or payload.get("collector_timestamp_utc")
        backtest_date = payload.get("backtest_date")
        data_date = backtest_date or (str(timestamp)[:10] if timestamp else "")
        meta["is_backtest"] = bool(backtest_date)
        if data_date:
            meta["data_date"] = data_date
        if timestamp:
            meta["collector_timestamp_utc"] = timestamp
        return meta

    def _latest_control_logs(self) -> List[Path]:
        log_root = Path(path_config.logs_dir) / "control_service"
        if not log_root.exists():
            return []
        candidates = list(log_root.glob("*.log")) + list(log_root.glob("*.json"))
        return sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)[:5]

    def _artifact_link_attrs(self, path: Optional[Path]) -> str:
        if not path:
            return 'href="#" aria-disabled="true"'
        resolved = path.resolve()
        return f'href="{_escape(resolved.as_uri())}" data-artifact-path="{_escape(str(resolved))}"'

    def _manual_template_json(self) -> str:
        template = json.loads(json.dumps(DEFAULT_MANUAL_DATA, ensure_ascii=False))
        template["active"] = False
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
        data_jsons = self._latest_data_jsons()
        latest_report = reports[0] if reports else None
        latest_workbench = workbenches[0] if workbenches else None
        latest_log = control_logs[0] if control_logs else None
        latest_data_json = data_jsons[0] if data_jsons else None
        manual_path = get_manual_data_local_path()
        initial_manual_data = self._initial_manual_data_json()
        payload = json.dumps(
            {
                "manualTemplate": manual_template,
                "initialManualData": initial_manual_data,
                "manualPath": manual_path,
                "latestReport": str(latest_report or ""),
                "latestWorkbench": str(latest_workbench or ""),
                "latestLog": str(latest_log or ""),
                "latestRun": str(runs[0] if runs else ""),
                "latestDataJson": str(latest_data_json or ""),
                "latestDataJsonMeta": self._data_json_meta(latest_data_json),
            },
            ensure_ascii=False,
        )
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="ndx-console-version" content="console_simple_launcher_v1">
  <title>NDX vNext 研究控制台</title>
  <style>{self._css()}</style>
</head>
<body>
  <main class="console-shell">
    <header class="topbar">
      <div>
        <p class="eyebrow">NDX vNext</p>
        <h1>NDX vNext 研究控制台</h1>
      </div>
      <nav class="quick-links" aria-label="最新产物">
        <a class="quiet-link" {self._artifact_link_attrs(latest_report)}>打开最新报告</a>
        <a class="quiet-link" {self._artifact_link_attrs(latest_workbench)}>打开最新 workbench</a>
        <a class="quiet-link" {self._artifact_link_attrs(latest_log)}>打开最新日志</a>
      </nav>
    </header>

    <section class="launcher-grid">
      <article class="panel run-panel" aria-label="运行设置">
        <div class="panel-head">
          <h2>运行模式</h2>
          <p id="modeHelp">重新收集数据，生成纯数据报告、事件新闻报告和综合报告。</p>
        </div>

        <div class="mode-cards" role="radiogroup" aria-label="运行模式">
          <label><input type="radio" name="runMode" value="pure_data"><span>纯数据报告</span></label>
          <label><input type="radio" name="runMode" value="event_only"><span>事件新闻报告</span></label>
          <label><input type="radio" name="runMode" value="integrated" checked><span>综合报告</span></label>
        </div>

        <label class="check-row"><input id="backtestMode" type="checkbox"> 是否回测</label>
        <div id="backtestDateWrap" class="date-row" hidden>
          <label>回测日期 <input id="backtestDate" type="date"></label>
          <p>回测会阻止当前网页、当前 Wind 快照和当前成分股基本面冒充历史当时可见数据。</p>
        </div>

        <p class="boundary-note" id="modeBoundaryNote">综合报告会同时生成纯数据报告和事件新闻报告；事件材料不进入 L1-L5 主证据。</p>

        <button class="run-now-button" type="button" id="runNow">开始综合报告</button>
        <button class="secondary-button hidden" type="button" id="cancelJob">取消任务</button>
        <p id="runStatus" class="run-status is-idle" role="button" tabindex="0" aria-live="polite" title="点击刷新任务状态">状态：尚未运行。</p>
      </article>

      <aside class="panel side-panel" aria-label="数据和入口">
        <div class="panel-head">
          <h2>末次数据</h2>
          <p id="dataUseNote">综合报告和纯数据报告会重新采集；事件新闻报告会优先用这份 JSON 做市场验证。</p>
        </div>
        <dl class="data-summary">
          <div><dt>文件</dt><dd id="latestDataName">暂无可用数据</dd></div>
          <div><dt>数据日期</dt><dd id="latestDataDate">-</dd></div>
          <div><dt>收集时间</dt><dd id="latestDataCollected">-</dd></div>
          <div><dt>回测数据</dt><dd id="latestDataBacktest">-</dd></div>
        </dl>

        <div class="latest-actions">
          <a class="primary-link" {self._artifact_link_attrs(latest_report)}>打开最新报告</a>
          <a class="secondary-link" {self._artifact_link_attrs(latest_workbench)}>打开最新 workbench</a>
          <a class="secondary-link" {self._artifact_link_attrs(latest_log)}>打开最新日志</a>
        </div>
      </aside>
    </section>

    <details class="advanced-panel">
      <summary>高级设置</summary>
      <div class="advanced-grid">
        <section>
          <h2>模型选择</h2>
          <div class="stacked-options" role="radiogroup" aria-label="模型选择">
            <label><input type="radio" name="modelMode" value="deepseek-v4-flash,deepseek-v4-pro" checked> flash 优先</label>
            <label><input type="radio" name="modelMode" value="deepseek-v4-pro"> pro only</label>
            <label><input type="radio" name="modelMode" value="custom"> 自定义顺序</label>
          </div>
          <label class="text-field">自定义模型顺序 <input id="customModels" type="text" value="deepseek-v4-flash,deepseek-v4-pro"></label>
        </section>

        <section>
          <h2>Wind L4 主锚</h2>
          <label class="check-row"><input id="windEnabled" type="checkbox" checked> 开启</label>
          <p id="windNote" class="small-note">开启后会使用 Wind 获取 NDX 估值和风险溢价，可能消耗积分。</p>
        </section>

        <section>
          <h2>人工覆盖</h2>
          <p id="manualSummary" class="small-note">人工覆盖：未启用</p>
          <label class="check-row"><input id="manualActive" type="checkbox"> 启用人工覆盖</label>
          <textarea id="manualJson" spellcheck="false">{_escape(initial_manual_data)}</textarea>
          <div class="button-row">
            <button type="button" id="saveManual">保存人工覆盖</button>
            <button class="secondary-button" type="button" id="resetManual">恢复模板</button>
          </div>
          <p id="manualValidation" class="small-note">等待输入。</p>
          <p class="path-note">目标文件：{_escape(manual_path)}</p>
        </section>

        <section>
          <h2>workbench 模块</h2>
          <div class="module-options">
            <label><input type="checkbox" name="workbenchModule" value="price_technical" checked> 价格技术</label>
            <label><input type="checkbox" name="workbenchModule" value="volatility_credit" checked> 波动信用</label>
            <label><input type="checkbox" name="workbenchModule" value="rates_valuation" checked> 利率估值</label>
            <label><input type="checkbox" name="workbenchModule" value="breadth_concentration" checked> 广度集中度</label>
            <label><input type="checkbox" name="workbenchModule" value="liquidity" checked> 流动性</label>
          </div>
        </section>

        <section class="developer-section">
          <h2>开发者命令</h2>
          <pre id="runCommandPreview">python3 src/console_run_all.py --models deepseek-v4-flash,deepseek-v4-pro --workbench-modules price_technical,volatility_credit,rates_valuation,breadth_concentration,liquidity --skip-legacy-report --enable-news</pre>
          <pre id="jobStatusPreview">尚无任务。</pre>
        </section>
      </div>
    </details>
  </main>
  <script type="application/json" id="console-data">{_safe_script_json(payload)}</script>
  <script>{self._js()}</script>
</body>
</html>
"""

    def _css(self) -> str:
        return """
:root {
  --paper: #f6f6f1;
  --raised: #fffefa;
  --ink: #1d2428;
  --soft: #465158;
  --muted: #6c7478;
  --rule: #d8d8ce;
  --accent: #215f8f;
  --accent-strong: #184b72;
  --good: #24724d;
  --watch: #986b1b;
  --risk: #a43f32;
  --radius: 8px;
  --mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  --sans: ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", PingFang SC, system-ui, sans-serif;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: var(--sans);
  overflow-x: hidden;
}
p, li, h1, h2, h3, label, strong, span, a, dd { overflow-wrap: anywhere; }
.console-shell {
  width: min(1120px, calc(100% - 28px));
  margin: 0 auto;
  padding: 20px 0 72px;
}
.topbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 16px;
  padding: 0 0 18px;
  border-bottom: 1px solid var(--rule);
}
.eyebrow {
  margin: 0 0 6px;
  color: var(--accent);
  text-transform: uppercase;
  font: 700 12px var(--sans);
}
h1 {
  margin: 0;
  font: 740 30px/1.12 var(--sans);
}
.quick-links, .latest-actions, .button-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.quiet-link, .primary-link, .secondary-link, button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--ink);
  border-radius: 6px;
  background: var(--ink);
  color: var(--raised);
  padding: 8px 12px;
  text-decoration: none;
  font: 700 13px var(--sans);
  cursor: pointer;
  min-height: 38px;
}
.quiet-link, .secondary-link, .secondary-button {
  background: transparent;
  color: var(--ink);
}
.quiet-link {
  border-color: var(--rule);
  color: var(--soft);
  background: var(--raised);
}
.launcher-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(320px, .9fr);
  gap: 14px;
  margin-top: 18px;
  align-items: start;
}
.panel, .advanced-panel {
  background: var(--raised);
  border: 1px solid var(--rule);
  border-radius: var(--radius);
  padding: 16px;
}
.run-panel {
  border-color: #abc4d8;
}
.panel-head {
  margin-bottom: 12px;
}
h2 {
  margin: 0 0 4px;
  font: 720 19px var(--sans);
}
.panel-head p {
  margin: 0;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.5;
}
.mode-cards {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}
.mode-cards label, .stacked-options label, .module-options label, .check-row {
  border: 1px solid var(--rule);
  border-radius: 6px;
  background: #fbfaf4;
  padding: 10px 12px;
  color: var(--soft);
  font: 700 13px var(--sans);
}
.mode-cards label {
  display: grid;
  grid-template-columns: auto minmax(0, 1fr);
  align-items: center;
  gap: 8px;
  min-height: 50px;
}
.mode-cards input, .check-row input, .stacked-options input, .module-options input { margin: 0; }
.check-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
}
.date-row {
  margin-top: 10px;
  border-left: 3px solid var(--accent);
  padding-left: 12px;
}
.date-row label, .text-field {
  display: grid;
  gap: 6px;
  color: var(--soft);
  font: 700 13px var(--sans);
}
input[type="date"], input[type="text"], textarea {
  width: 100%;
  border: 1px solid var(--rule);
  border-radius: 6px;
  background: #fbfaf4;
  color: var(--ink);
  padding: 9px 10px;
  font: 12px var(--mono);
  min-height: 38px;
  min-width: 0;
}
input:focus, textarea:focus {
  outline: 2px solid #84b4d9;
  outline-offset: 1px;
}
.boundary-note, .date-row p, .small-note, .path-note {
  color: var(--muted);
  font-size: 12px;
  line-height: 1.55;
}
.is-warning { color: var(--watch); }
.run-now-button {
  width: 100%;
  margin-top: 16px;
  background: var(--accent);
  border-color: var(--accent);
  color: var(--raised);
  font-size: 15px;
  min-height: 48px;
}
.run-now-button:hover { background: var(--accent-strong); border-color: var(--accent-strong); }
.run-now-button:disabled {
  cursor: not-allowed;
  opacity: .55;
}
.secondary-button.hidden { display: none; }
.run-status {
  margin: 12px 0 0;
  border: 1px solid var(--rule);
  border-radius: 6px;
  background: #fbfaf4;
  padding: 10px 12px;
  color: var(--soft);
  font: 13px/1.55 var(--sans);
  cursor: pointer;
  user-select: none;
  transition: border-color .16s ease, background .16s ease, box-shadow .16s ease, transform .16s ease;
}
.run-status:hover { border-color: #94a5ac; background: #fffdf5; }
.run-status:focus-visible {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(33, 95, 143, .14);
}
.run-status.is-refreshing {
  transform: translateY(-1px);
  box-shadow: 0 8px 20px rgba(29, 36, 40, .08);
}
.run-status.is-running { border-color: #91b9d8; color: var(--accent); }
.run-status.is-good { border-color: #9ac4aa; color: var(--good); }
.run-status.is-warning { border-color: #d9bd7b; color: var(--watch); }
.run-status.is-risk { border-color: #d99a91; color: var(--risk); }
.data-summary {
  display: grid;
  gap: 8px;
  margin: 0;
}
.data-summary div {
  display: grid;
  grid-template-columns: 82px minmax(0, 1fr);
  gap: 10px;
  border-top: 1px solid var(--rule);
  padding-top: 8px;
}
dt {
  color: var(--muted);
  font: 700 12px var(--sans);
}
dd {
  margin: 0;
  font: 12px/1.45 var(--mono);
}
.latest-actions { margin-top: 16px; }
.latest-actions a { flex: 1 1 150px; }
.advanced-panel {
  margin-top: 14px;
}
.advanced-panel > summary {
  cursor: pointer;
  font: 740 15px var(--sans);
  color: var(--accent);
  list-style-position: inside;
}
.advanced-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
  margin-top: 14px;
}
.advanced-grid section {
  min-width: 0;
}
.advanced-grid h2 {
  font-size: 15px;
  margin-bottom: 10px;
}
.stacked-options, .module-options {
  display: grid;
  gap: 8px;
}
.text-field { margin-top: 10px; }
textarea {
  min-height: 210px;
  resize: vertical;
  line-height: 1.45;
}
.button-row { margin-top: 10px; }
.developer-section { grid-column: 1 / -1; }
pre {
  overflow: auto;
  border: 1px solid var(--rule);
  border-radius: 6px;
  background: #20272b;
  color: #f3f1e8;
  padding: 12px;
  font: 12px/1.55 var(--mono);
  max-height: 220px;
}
.hidden { display: none !important; }
@media (max-width: 820px) {
  .topbar { align-items: flex-start; flex-direction: column; }
  .launcher-grid, .advanced-grid { grid-template-columns: minmax(0, 1fr); }
  .quick-links, .latest-actions { width: 100%; }
  .quick-links a, .latest-actions a { flex: 1 1 100%; }
}
@media (max-width: 520px) {
  .console-shell { width: min(100% - 20px, 1120px); padding-top: 14px; }
  h1 { font-size: 24px; }
  .mode-cards { grid-template-columns: 1fr; }
  .panel, .advanced-panel { padding: 13px; }
  .data-summary div { grid-template-columns: 1fr; gap: 3px; }
}
"""

    def _js(self) -> str:
        return """
const data = JSON.parse(document.getElementById('console-data').textContent);
const manualJson = document.getElementById('manualJson');
const preview = document.getElementById('runCommandPreview');
const validation = document.getElementById('manualValidation');
const runStatus = document.getElementById('runStatus');
const jobStatusPreview = document.getElementById('jobStatusPreview');
const runButton = document.getElementById('runNow');
const cancelButton = document.getElementById('cancelJob');
const backtestDate = document.getElementById('backtestDate');
let activeJobId = '';
let runPollTimer = null;
let openedArtifactForJob = '';
let manualDirty = false;
let initialManualActive = false;
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

function applyManualPayloadToForm(payload) {
  document.getElementById('manualActive').checked = Boolean(payload.active);
  manualJson.value = JSON.stringify(payload, null, 2);
  updateManualSummary();
}

const initialManualPayload = parseJson(data.initialManualData, parseJson(data.manualTemplate, {}));
initialManualActive = Boolean(initialManualPayload.active);
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
  return selected ? selected.value : 'integrated';
}

function selectedModules() {
  const modules = Array.from(document.querySelectorAll('input[name="workbenchModule"]:checked')).map(node => node.value);
  return modules.length ? modules.join(',') : 'price_technical,volatility_credit,rates_valuation,breadth_concentration,liquidity';
}

function modeCommand(mode, models) {
  const modules = selectedModules();
  const dataReport = ['python3 src/console_run_all.py', `--models ${models}`, `--workbench-modules ${modules}`, '--skip-legacy-report'];
  const integrated = ['python3 src/console_run_all.py', `--models ${models}`, `--workbench-modules ${modules}`, '--skip-legacy-report', '--enable-news'];
  const eventOnly = ['python3 src/main.py', '--event-only'];
  if (document.getElementById('backtestMode').checked && backtestDate.value) {
    dataReport.push(`--date ${backtestDate.value}`);
    integrated.push(`--date ${backtestDate.value}`);
    eventOnly.push(`--date ${backtestDate.value}`);
  }
  if (data.latestDataJson) eventOnly.push(`--data-json ${data.latestDataJson}`);
  if (mode === 'pure_data') return dataReport.join(' ');
  if (mode === 'event_only') return eventOnly.join(' ');
  return integrated.join(' ');
}

function buildManualPayload() {
  const payload = parseJson(manualJson.value, parseJson(data.manualTemplate, {}));
  payload.active = document.getElementById('manualActive').checked;
  return payload;
}

function validateManualPayload(payload) {
  const warnings = [];
  if (!payload || typeof payload !== 'object') warnings.push('人工覆盖 JSON 无法解析');
  if (payload && typeof payload === 'object' && !payload.metrics) warnings.push('人工覆盖 JSON 缺少 metrics');
  return warnings;
}

function updateManualSummary() {
  const active = document.getElementById('manualActive').checked;
  document.getElementById('manualSummary').textContent = `人工覆盖：${active ? '已启用' : '未启用'}`;
}

function syncManualPreview() {
  let payload;
  try {
    payload = buildManualPayload();
    manualJson.value = JSON.stringify(payload, null, 2);
  } catch (error) {
    validation.textContent = `人工覆盖 JSON 无法解析：${error.message || error}`;
    validation.className = 'small-note is-warning';
    updateManualSummary();
    return;
  }
  const warnings = validateManualPayload(payload);
  validation.textContent = warnings.length ? warnings.join('；') : '人工覆盖预览已同步。';
  validation.className = warnings.length ? 'small-note is-warning' : 'small-note';
  updateManualSummary();
}

function shouldSendManualJson() {
  return document.getElementById('manualActive').checked || initialManualActive || manualDirty;
}

function dataJsonWarning(mode) {
  if (mode !== 'event_only' || !data.latestDataJson) return '';
  const meta = data.latestDataJsonMeta || {};
  const jsonDate = meta.data_date || '';
  const modified = meta.modified_at || '';
  if (!jsonDate && !modified) return '';
  const selectedDate = document.getElementById('backtestMode').checked ? backtestDate.value : '';
  const mismatch = selectedDate && jsonDate && selectedDate !== jsonDate;
  const bits = [`已有数据日期 ${jsonDate || '未知'}`];
  if (modified) bits.push(`文件修改 ${modified}`);
  if (mismatch) bits.push(`与回测日期 ${selectedDate} 不一致`);
  return bits.join('；');
}

function envOverrides() {
  return document.getElementById('windEnabled').checked ? {} : { NDX_DISABLE_WIND_L4: '1' };
}

function updateLatestDataSummary() {
  const meta = data.latestDataJsonMeta || {};
  document.getElementById('latestDataName').textContent = meta.name || (data.latestDataJson ? data.latestDataJson.split('/').pop() : '暂无可用数据');
  document.getElementById('latestDataDate').textContent = meta.data_date || '-';
  document.getElementById('latestDataCollected').textContent = meta.collector_timestamp_utc || meta.modified_at || '-';
  document.getElementById('latestDataBacktest').textContent = meta.is_backtest ? '是' : (data.latestDataJson ? '否' : '-');
}

function buildCommand() {
  const mode = selectedRunMode();
  const models = currentModels();
  preview.textContent = modeCommand(mode, models);
  const labels = {
    pure_data: ['开始纯数据报告', '重新收集正式数据，运行 L1-L5 和数据侧报告；不收集事件新闻。'],
    event_only: ['开始事件新闻报告', '只收集新闻、公告和市场叙事；如有末次数据，会做市场邻近验证。'],
    integrated: ['开始综合报告', '重新收集正式数据，同时生成事件新闻报告，再输出综合报告。'],
  };
  runButton.textContent = labels[mode][0];
  document.getElementById('modeHelp').textContent = labels[mode][1];
  document.getElementById('dataUseNote').textContent = mode === 'event_only'
    ? '事件新闻报告会优先用这份 JSON 做市场验证；没有数据也能生成事件报告。'
    : '综合报告和纯数据报告会重新采集；事件新闻报告会优先用这份 JSON 做市场验证。';
  const boundary = {
    pure_data: '纯数据报告不收集事件新闻，继续保持 L1-L5 上下文隔离。',
    event_only: '事件新闻报告只产出第二层材料；不能作为 L1-L5 evidence_ref。',
    integrated: '综合报告会同时生成纯数据报告和事件新闻报告；事件材料不进入 L1-L5 主证据。',
  };
  document.getElementById('modeBoundaryNote').textContent = boundary[mode];
  document.getElementById('windNote').textContent = document.getElementById('windEnabled').checked
    ? '开启后会使用 Wind 获取 NDX 估值和风险溢价，可能消耗积分。'
    : '本次不会调用 Wind L4 主锚，将使用降级路径。';
  runButton.disabled = false;
  const warning = dataJsonWarning(mode);
  if (warning && !activeJobId) {
    runStatus.textContent = `注意：${warning}。事件新闻报告会以该 JSON 做市场验证；新闻收集仍会重新执行。`;
    runStatus.className = 'run-status is-warning';
  } else if (!activeJobId) {
    runStatus.textContent = '状态：尚未运行。';
    runStatus.className = 'run-status is-idle';
  }
}

document.querySelectorAll('input[name="modelMode"], input[name="runMode"], #customModels, #backtestMode, #backtestDate, #windEnabled, input[name="workbenchModule"]')
  .forEach((node) => node.addEventListener('change', buildCommand));
document.getElementById('backtestMode').addEventListener('change', () => {
  document.getElementById('backtestDateWrap').hidden = !document.getElementById('backtestMode').checked;
  buildCommand();
});
document.getElementById('manualActive').addEventListener('change', () => {
  manualDirty = true;
  syncManualPreview();
});
manualJson.addEventListener('input', () => {
  manualDirty = true;
  updateManualSummary();
});
document.getElementById('customModels').addEventListener('input', buildCommand);

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
    manualDirty = false;
    initialManualActive = Boolean(buildManualPayload().active);
    if (statusNode) {
      statusNode.textContent = `人工覆盖已保存：${result.path || data.manualPath}`;
      statusNode.className = 'run-status is-good';
    }
    return true;
  } catch (error) {
    if (statusNode) {
      statusNode.textContent = '未连接 control service，人工覆盖未保存。';
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
  statusNode.className = 'run-status is-running';
  try {
    const confirmed = window.confirm('确认通过本机 control service 执行这条白名单命令？');
    if (!confirmed) {
      statusNode.textContent = '已取消，未执行命令。';
      statusNode.className = 'run-status is-warning';
      return null;
    }
    const response = await fetch(`${controlOrigin}/run`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        command,
        confirmed: true,
        env_overrides: envOverrides(),
        manual_json: shouldSendManualJson() ? JSON.stringify(buildManualPayload(), null, 2) : '',
      }),
    });
    const result = await response.json();
    if (!response.ok || !result.ok) throw new Error(result.message || `HTTP ${response.status}`);
    const job = result.job || {};
    statusNode.textContent = `${result.message || '已提交运行。'} job_id=${job.job_id || ''}`;
    statusNode.className = 'run-status is-running';
    cancelButton.classList.remove('hidden');
    return job.job_id || null;
  } catch (error) {
    statusNode.textContent = `没有执行命令：${error.message || '未检测到本机 control service。请先启动受控服务。'}`;
    statusNode.className = 'run-status is-warning';
    return null;
  }
}

async function refreshJob(jobId, statusNode) {
  if (!jobId) {
    statusNode.textContent = '尚无可刷新的任务。';
    statusNode.className = 'run-status is-warning';
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
    env_overrides: job.env_overrides,
    failure_reason: job.failure_reason,
    log_tail: job.log_tail
  }, null, 2);
  statusNode.textContent = `任务状态：${job.status || 'unknown'}；日志：${job.log_path || '无'}`;
  statusNode.className = 'run-status';
  if (job.status === 'running') statusNode.classList.add('is-running');
  if (job.status === 'completed') statusNode.classList.add('is-good');
  if (job.status === 'failed' || job.status === 'canceled' || job.status === 'unknown') statusNode.classList.add('is-warning');
  if (['completed', 'failed', 'canceled', 'unknown'].includes(job.status)) cancelButton.classList.add('hidden');
  return job;
}

function refreshedAtText() {
  return new Date().toLocaleTimeString('zh-CN', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

async function refreshStatusFromBox() {
  if (runStatus.querySelector('a')) return;
  runStatus.classList.add('is-refreshing');
  if (activeJobId) {
    const job = await refreshJob(activeJobId, runStatus);
    if (job) {
      runStatus.textContent = `${runStatus.textContent}；已刷新 ${refreshedAtText()}`;
    }
  } else {
    await refreshJob(activeJobId, runStatus);
  }
  window.setTimeout(() => runStatus.classList.remove('is-refreshing'), 240);
}

async function openLatestProductForMode(jobId) {
  if (!jobId || openedArtifactForJob === jobId) return;
  try {
    const response = await fetch(`${controlOrigin}/latest-product`);
    const result = await response.json();
    const summary = result.summary || {};
    const mode = selectedRunMode();
    const preferred = mode === 'event_only'
      ? (summary.event_mechanism_report_html || summary.event_narrative_report || summary.event_narrative_ledger || summary.native_brief || summary.report_path || summary.workbench)
      : (summary.native_brief || summary.report_path || summary.workbench || summary.event_mechanism_report_html || summary.event_narrative_report);
    if (!preferred) return;
    openedArtifactForJob = jobId;
    const reports = [];
    if (summary.native_brief) reports.push({ label: 'Brief 报告', path: summary.native_brief });
    if (summary.workbench) reports.push({ label: 'Workbench', path: summary.workbench });
    if (summary.report_path && summary.report_path !== summary.native_brief) reports.push({ label: '完整报告', path: summary.report_path });
    if (summary.pure_data_report) reports.push({ label: '纯数据研报', path: summary.pure_data_report });
    if (summary.event_mechanism_report_html) reports.push({ label: '新闻事件研报', path: summary.event_mechanism_report_html });
    if (summary.event_narrative_report) reports.push({ label: '事件新闻报告', path: summary.event_narrative_report });
    if (summary.event_mechanism_report) reports.push({ label: '新闻事件研报数据', path: summary.event_mechanism_report });
    if (summary.cross_layer_questions) reports.push({ label: '跨层问题', path: summary.cross_layer_questions });
    if (summary.event_narrative_ledger) reports.push({ label: '事件与叙事账本', path: summary.event_narrative_ledger });
    if (summary.integrated_synthesis_report) reports.push({ label: '综合总报告', path: summary.integrated_synthesis_report });
    if (summary.news_event_ledger) reports.push({ label: '旧事件底账', path: summary.news_event_ledger });
    if (summary.news_event_data_links) reports.push({ label: '市场连接观察', path: summary.news_event_data_links });
    const linksHtml = reports.map(r =>
      `<a href="${artifactUrl(r.path)}" target="_blank" rel="noopener" style="margin-left:8px;padding:2px 8px;border:1px solid #215f8f;border-radius:4px;text-decoration:none;color:#215f8f;font-size:13px;">${r.label}</a>`
    ).join('');
    runStatus.innerHTML = `任务已完成。可用报告：${linksHtml}`;
    const w = window.open(artifactUrl(preferred), '_blank', 'noopener');
    if (!w || w.closed || typeof w.closed === 'undefined') {
      runStatus.innerHTML += `<br><span style="color:#986b1b;font-size:12px;">弹窗可能被浏览器拦截，请点击上方链接手动打开。</span>`;
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
runStatus.addEventListener('click', (event) => {
  if (event.target.closest('a')) return;
  refreshStatusFromBox();
});
runStatus.addEventListener('keydown', (event) => {
  if (event.key !== 'Enter' && event.key !== ' ') return;
  event.preventDefault();
  refreshStatusFromBox();
});
document.getElementById('cancelJob').addEventListener('click', async () => {
  if (!activeJobId) {
    runStatus.textContent = '尚无可取消的任务。';
    runStatus.className = 'run-status is-warning';
    return;
  }
  await fetch(`${controlOrigin}/cancel/${encodeURIComponent(activeJobId)}`, { method: 'POST' });
  refreshJob(activeJobId, runStatus);
});
document.getElementById('resetManual').addEventListener('click', () => {
  applyManualPayloadToForm(parseJson(data.manualTemplate, {}));
  manualDirty = true;
  syncManualPreview();
});
document.getElementById('saveManual').addEventListener('click', async () => {
  await saveManualData(runStatus);
});

async function loadManualDataFromService() {
  try {
    const response = await fetch(`${controlOrigin}/manual-data`);
    const result = await response.json();
    if (response.ok && result.ok && result.manual_data) {
      initialManualActive = Boolean(result.manual_data.active);
      applyManualPayloadToForm(result.manual_data);
      manualDirty = false;
      validation.textContent = `已载入上次人工数据：${result.path || data.manualPath}`;
    }
  } catch (error) {
    // Static file fallback: embedded data from generation time is already applied.
  }
}

loadManualDataFromService().finally(() => {
  updateLatestDataSummary();
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
