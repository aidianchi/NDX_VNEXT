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

    def _manual_template_json(self) -> str:
        template = json.loads(json.dumps(DEFAULT_MANUAL_DATA, ensure_ascii=False))
        template["active"] = True
        template["date"] = datetime.now().strftime("%Y-%m-%d")
        return json.dumps(template, ensure_ascii=False, indent=2)

    def _render(self) -> str:
        manual_template = self._manual_template_json()
        reports = self._latest_reports()
        latest_report = reports[0] if reports else None
        report_links = "".join(
            f'<a href="{_escape(path.resolve().as_uri())}">{_escape(path.name)}</a>'
            for path in reports
        )
        latest_href = latest_report.resolve().as_uri() if latest_report else "#"
        manual_path = get_manual_data_local_path()
        payload = json.dumps(
            {
                "manualTemplate": manual_template,
                "manualPath": manual_path,
                "latestReport": str(latest_report or ""),
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
        <p>把人工数据、模型选择、数据源健康、运行命令和报告入口放在同一屏。它先服务研究动作，不抢报告本身的注意力。</p>
      </div>
      <aside class="status-card">
        <span>默认路径</span>
        <strong>brief 报告</strong>
        <a class="primary-link" href="{_escape(latest_href)}">打开最新报告</a>
      </aside>
    </section>

    <section class="control-grid">
      <article class="panel manual-panel">
        <div class="panel-head">
          <span>01</span>
          <div>
            <h2>人工 / Wind 输入</h2>
            <p>只填有把握的字段。空字段不会触发人工覆盖。</p>
          </div>
        </div>
        <label>数据日期 <input id="dataDate" type="date"></label>
        <label>手工模板
          <textarea id="manualJson" spellcheck="false">{_escape(manual_template)}</textarea>
        </label>
        <div class="button-row">
          <button type="button" id="downloadManual">保存人工模板</button>
          <button type="button" id="resetManual">恢复模板</button>
        </div>
        <p class="path-note">目标文件：{_escape(manual_path)}</p>
      </article>

      <article class="panel">
        <div class="panel-head">
          <span>02</span>
          <div>
            <h2>模型选择</h2>
            <p>默认先快后稳；需要更审慎时可直接使用 pro。</p>
          </div>
        </div>
        <div class="segmented" role="radiogroup" aria-label="模型选择">
          <label><input type="radio" name="modelMode" value="deepseek-v4-flash,deepseek-v4-pro" checked> flash 优先</label>
          <label><input type="radio" name="modelMode" value="deepseek-v4-pro"> pro only</label>
          <label><input type="radio" name="modelMode" value="deepseek-v4-flash"> flash only</label>
        </div>
        <div class="health-list" aria-label="数据源健康">
          <h3>数据源健康</h3>
          <div><b>Manual/Wind</b><span class="watch">可选高信任输入</span></div>
          <div><b>Damodaran ERPbymonth.xlsx</b><span class="good">官方月度优先</span></div>
          <div><b>WorldPERatio</b><span class="good">相对位置辅助</span></div>
          <div><b>Trendonify</b><span class="watch">不可用时只记录缺口</span></div>
        </div>
      </article>

      <article class="panel run-panel">
        <div class="panel-head">
          <span>03</span>
          <div>
            <h2>运行与报告</h2>
            <p>浏览器不直接执行本地命令，但会生成清晰、可复制的运行指令。</p>
          </div>
        </div>
        <div class="toggle-line">
          <label><input id="skipLegacyReport" type="checkbox" checked> 跳过 legacy HTML</label>
          <label><input id="disableCharts" type="checkbox" checked> 关闭 legacy charts</label>
        </div>
        <button class="command-button" type="button" id="buildCommand">生成运行命令</button>
        <pre id="runCommandPreview">python3 src/main.py --models deepseek-v4-flash,deepseek-v4-pro --skip-report --disable-charts</pre>
        <div class="report-list">
          <h3>报告入口</h3>
          {report_links or '<span>还没有生成过 native 报告。</span>'}
        </div>
      </article>
    </section>
  </main>
  <script type="application/json" id="console-data">{_escape(payload)}</script>
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
.control-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(280px, .8fr);
  gap: 16px;
  margin-top: 18px;
}
@media (max-width: 900px) { .control-grid { grid-template-columns: 1fr; } }
.run-panel { grid-column: 1 / -1; }
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
textarea {
  width: 100%;
  border: 1px solid var(--rule);
  border-radius: 4px;
  background: #fffefa;
  color: var(--ink);
  padding: 9px 10px;
  font: 12px var(--mono);
}
textarea {
  min-height: 360px;
  resize: vertical;
  line-height: 1.45;
}
.button-row,
.toggle-line {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}
.button-row button:not(:first-child),
.command-button {
  background: transparent;
  color: var(--ink);
}
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
.toggle-line label {
  display: flex;
  align-items: center;
  gap: 8px;
  border: 1px solid var(--rule);
  border-radius: 4px;
  background: #fffefa;
  padding: 10px 12px;
  margin: 0;
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
.report-list h3 {
  flex-basis: 100%;
}
.report-list a,
.report-list span {
  border: 1px solid var(--rule);
  border-radius: 4px;
  color: var(--ink);
  background: #fffefa;
  padding: 6px 8px;
  font: 12px var(--mono);
  text-decoration: none;
}
"""

    def _js(self) -> str:
        return """
const data = JSON.parse(document.getElementById('console-data').textContent);
const manualJson = document.getElementById('manualJson');
const dataDate = document.getElementById('dataDate');
const preview = document.getElementById('runCommandPreview');

dataDate.value = new Date().toISOString().slice(0, 10);

function currentModels() {
  const selected = document.querySelector('input[name="modelMode"]:checked');
  return selected ? selected.value : 'deepseek-v4-flash,deepseek-v4-pro';
}

function buildCommand() {
  const parts = ['python3 src/main.py', `--models ${currentModels()}`];
  if (document.getElementById('skipLegacyReport').checked) parts.push('--skip-report');
  if (document.getElementById('disableCharts').checked) parts.push('--disable-charts');
  preview.textContent = parts.join(' ');
}

document.querySelectorAll('input[name="modelMode"], #skipLegacyReport, #disableCharts')
  .forEach((node) => node.addEventListener('change', buildCommand));

document.getElementById('buildCommand').addEventListener('click', buildCommand);
document.getElementById('resetManual').addEventListener('click', () => {
  manualJson.value = data.manualTemplate;
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
