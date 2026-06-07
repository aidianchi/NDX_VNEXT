from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from ..config import path_config
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from config import path_config


STAGE_LABELS = {
    "L1": "L1 宏观流动性",
    "L2": "L2 风险偏好",
    "L3": "L3 市场结构",
    "L4": "L4 估值",
    "L5": "L5 技术趋势",
    "bridge": "Bridge 跨层桥",
    "thesis": "Thesis 投资判断",
    "critic": "Critic 反方审查",
    "critic_retry": "Critic 重试",
    "risk": "Risk 风险边界",
    "risk_retry": "Risk 重试",
    "reviser": "Reviser 修订",
    "final_adjudicator": "Final 最终裁决",
}

PIPELINE_ORDER = [
    "L1",
    "L2",
    "L3",
    "L4",
    "L5",
    "bridge",
    "thesis",
    "critic",
    "critic_retry",
    "risk",
    "risk_retry",
    "reviser",
    "final_adjudicator",
]


def _escape(value: Any) -> str:
    return html.escape(str(value if value is not None else ""), quote=True)


def _load_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return fallback


def _json_for_script(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, default=str).replace("</script", "<\\/script")


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _run_stamp(run_path: Path) -> str:
    name = run_path.name.strip()
    if name:
        return re.sub(r"[^A-Za-z0-9_.-]+", "_", name)
    return datetime.now().strftime("%Y%m%d_%H%M")


class PromptInspectorGenerator:
    """Generate a standalone Agent 原文检查器 from prompt_audit artifacts."""

    def __init__(self, reports_dir: Optional[str] = None) -> None:
        self.reports_dir = Path(reports_dir or path_config.reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def run(self, run_dir: str | Path, output_path: Optional[str | Path] = None) -> str:
        run_path = Path(run_dir)
        payload = self._load_payload(run_path)
        html_text = self._render(run_path, payload)
        destination = Path(output_path) if output_path else self._default_output_path(run_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(html_text, encoding="utf-8")
        return str(destination)

    def _default_output_path(self, run_path: Path) -> Path:
        return self.reports_dir / f"vnext_prompt_inspector_{_run_stamp(run_path)}.html"

    def _load_payload(self, run_path: Path) -> Dict[str, Any]:
        diagnostics = _load_json(run_path / "llm_stage_diagnostics.json", {})
        stages = self._load_stages(run_path, diagnostics)
        return {
            "run_dir": str(run_path),
            "diagnostics": diagnostics,
            "stages": stages,
            "summary": self._build_summary(stages),
        }

    def _load_stages(self, run_path: Path, diagnostics: Dict[str, Any]) -> List[Dict[str, Any]]:
        prompt_dir = run_path / "prompt_audit"
        stage_names = []
        if prompt_dir.exists():
            stage_names.extend(path.name for path in prompt_dir.iterdir() if path.is_dir())
        diag_stages = diagnostics.get("stages", {}) if isinstance(diagnostics, dict) else {}
        for stage_name, record in diag_stages.items():
            audit = record.get("prompt_audit", {}) if isinstance(record, dict) else {}
            stage_dir = Path(str(audit.get("stage_dir", ""))).name if isinstance(audit, dict) else ""
            stage_names.append(stage_dir or self._stage_dir_name(stage_name))
        unique = sorted(set(stage_names), key=self._stage_sort_key)
        return [self._load_stage(run_path, stage_name, diag_stages) for stage_name in unique]

    def _load_stage(self, run_path: Path, stage_dir_name: str, diag_stages: Dict[str, Any]) -> Dict[str, Any]:
        stage_dir = run_path / "prompt_audit" / stage_dir_name
        meta = _load_json(stage_dir / "meta.json", {})
        diag_name = meta.get("stage_name") or self._diag_name_for_stage(stage_dir_name, diag_stages)
        diagnostics = diag_stages.get(diag_name, {}) if isinstance(diag_stages, dict) else {}
        attempts = []
        for prompt_file in sorted(stage_dir.glob("attempt_*.prompt.txt")):
            match = re.search(r"attempt_(\d+)\.prompt\.txt$", prompt_file.name)
            attempt = int(match.group(1)) if match else len(attempts) + 1
            prompt_text = prompt_file.read_text(encoding="utf-8")
            payload_file = stage_dir / f"attempt_{attempt}.payload.json"
            raw_file = stage_dir / f"attempt_{attempt}.response.raw.txt"
            parsed_file = stage_dir / f"attempt_{attempt}.parsed.normalized.json"
            attempts.append(
                {
                    "attempt": attempt,
                    "prompt_file": str(prompt_file.relative_to(run_path)),
                    "prompt_text": prompt_text,
                    "prompt_sha256": _sha256(prompt_text),
                    "meta_prompt_sha256": meta.get("prompt_sha256") if meta.get("attempt") == attempt else None,
                    "hash_matches_meta": (not meta.get("prompt_sha256")) or meta.get("attempt") != attempt or meta.get("prompt_sha256") == _sha256(prompt_text),
                    "payload_file": str(payload_file.relative_to(run_path)) if payload_file.exists() else "",
                    "payload": _load_json(payload_file, {}),
                    "raw_response_file": str(raw_file.relative_to(run_path)) if raw_file.exists() else "",
                    "raw_response": raw_file.read_text(encoding="utf-8") if raw_file.exists() else "",
                    "parsed_response_file": str(parsed_file.relative_to(run_path)) if parsed_file.exists() else "",
                    "parsed_response": _load_json(parsed_file, {}),
                }
            )
        prompt_text = attempts[-1]["prompt_text"] if attempts else ""
        validated_file = stage_dir / "output.validated.json"
        boundary = self._scan_boundary(stage_dir_name, prompt_text)
        return {
            "stage": stage_dir_name,
            "label": STAGE_LABELS.get(stage_dir_name, stage_dir_name),
            "stage_name": diag_name,
            "meta": meta,
            "diagnostics": diagnostics,
            "attempts": attempts,
            "latest_prompt": prompt_text,
            "validated_output_file": str(validated_file.relative_to(run_path)) if validated_file.exists() else "",
            "validated_output": _load_json(validated_file, {}),
            "boundary": boundary,
            "rule_hits": self._rule_hits(prompt_text),
            "downstream": self._downstream_summary(stage_dir_name),
        }

    def _build_summary(self, stages: List[Dict[str, Any]]) -> Dict[str, Any]:
        attempts = sum(len(stage.get("attempts", [])) for stage in stages)
        with_prompts = sum(1 for stage in stages if stage.get("attempts"))
        failed = sum(1 for stage in stages if (stage.get("meta") or {}).get("status") == "failed")
        boundary_counts: Dict[str, int] = {}
        for stage in stages:
            status = (stage.get("boundary") or {}).get("status", "missing")
            boundary_counts[status] = boundary_counts.get(status, 0) + 1
        return {
            "stage_count": len(stages),
            "prompt_stage_count": with_prompts,
            "attempt_count": attempts,
            "failed_stage_count": failed,
            "boundary_counts": boundary_counts,
        }

    def _stage_sort_key(self, stage: str) -> tuple:
        if stage in PIPELINE_ORDER:
            return (PIPELINE_ORDER.index(stage), stage)
        return (len(PIPELINE_ORDER), stage)

    def _stage_dir_name(self, stage_name: str) -> str:
        match = re.fullmatch(r"l([1-5])", str(stage_name).lower())
        if match:
            return f"L{match.group(1)}"
        return str(stage_name)

    def _diag_name_for_stage(self, stage: str, diag_stages: Dict[str, Any]) -> str:
        lower = stage.lower()
        for name in diag_stages:
            if self._stage_dir_name(name).lower() == lower:
                return name
        if stage.startswith("L") and len(stage) == 2:
            return stage.lower()
        return stage

    def _scan_boundary(self, stage: str, prompt_text: str) -> Dict[str, Any]:
        checks = []
        if stage in {"L1", "L2", "L3", "L4", "L5"}:
            checks = [
                ("其他层 layer card 输出", r"layer_cards/(?!%s\b)L[1-5]\.json" % re.escape(stage)),
                ("Bridge 当前 memo", r"bridge_memos/bridge_0\.json|\"bridge_memos\""),
                ("Thesis 当前判断", r"thesis_draft\.json|\"thesis_draft\""),
                ("Final 当前判断", r"final_adjudication\.json|\"final_adjudication\""),
                ("全局跨层运行时信号", r"apparent_cross_layer_signals\"\s*:\s*\[[^\]]*\S"),
                ("新闻候选 sidecar", r"news_layer_analysis|news_event_ledger|browser_sidecar"),
            ]
        elif stage == "bridge":
            checks = [
                ("Thesis / Final 当前判断", r"thesis_draft\.json|final_adjudication\.json|\"final_adjudication\""),
                ("未标注新闻候选", r"browser_sidecar"),
            ]
        elif stage in {"thesis", "critic", "risk", "reviser", "final_adjudicator"}:
            checks = [
                ("Final 当前判断提前出现", r"final_adjudication\.json|\"final_adjudication\""),
                ("未标注新闻候选", r"browser_sidecar"),
            ]
        findings = []
        for rule, pattern in checks:
            for match in re.finditer(pattern, prompt_text, flags=re.I | re.S):
                start = max(0, match.start() - 80)
                end = min(len(prompt_text), match.end() + 80)
                findings.append(
                    {
                        "rule": rule,
                        "severity": "违规",
                        "excerpt": prompt_text[start:end],
                        "offset": match.start(),
                    }
                )
                break
        if not prompt_text:
            status = "未保存"
        elif findings:
            status = "违规"
        else:
            status = "干净"
        return {"status": status, "findings": findings}

    def _rule_hits(self, prompt_text: str) -> List[Dict[str, Any]]:
        targets = [
            ("ObjectCanon", "ObjectCanon"),
            ("IndicatorCanon", "IndicatorCanon"),
            ("PermissionType", "PermissionType"),
            ("Decision Semantics", "Decision Semantics"),
            ("回测 / snapshot 数据边界", "backtest|snapshot|effective_date|数据边界|回测"),
            ("输出格式约束", "Response Rules|JSON 顶层字段|只返回一个 JSON 对象"),
        ]
        hits = []
        for label, pattern in targets:
            match = re.search(pattern, prompt_text, flags=re.I)
            if not match:
                continue
            start = max(0, match.start() - 160)
            end = min(len(prompt_text), match.end() + 360)
            hits.append({"label": label, "offset": match.start(), "excerpt": prompt_text[start:end]})
        return hits

    def _downstream_summary(self, stage: str) -> List[str]:
        if stage in {"L1", "L2", "L3", "L4", "L5"}:
            return ["Bridge 读取 layer card", "Thesis 通过 synthesis_packet 消费摘要与 evidence refs", "Final 通过治理包继承或修正结论"]
        if stage == "bridge":
            return ["Thesis 读取 synthesis_packet / bridge_summaries", "Risk / Reviser / Final 通过治理包保留冲突与反证"]
        if stage == "thesis":
            return ["Critic / Risk 审查", "Reviser 修订", "Final 生成读者结论"]
        if stage in {"critic", "risk"}:
            return ["Reviser 和 Final 必须消费治理反馈"]
        if stage == "reviser":
            return ["Final 读取 revised thesis"]
        return ["最终报告读取该产物"]

    def _render(self, run_path: Path, payload: Dict[str, Any]) -> str:
        data_json = _json_for_script(payload)
        first_stage = payload["stages"][0]["stage"] if payload.get("stages") else ""
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Agent 原文检查器 · {_escape(run_path.name)}</title>
  <style>{self._css()}</style>
</head>
<body>
  <div class="app">
    <header class="topbar">
      <div>
        <p class="eyebrow">NDX vNext Prompt Inspector</p>
        <h1>Agent 原文检查器</h1>
        <p>第一事实源是 <code>prompt_audit/*/attempt_N.prompt.txt</code>；完整原文区域只做渲染、搜索和复制，不改写 prompt 文本。</p>
      </div>
      <div class="summary">
        <div><span>Stage</span><strong>{_escape(payload['summary']['stage_count'])}</strong></div>
        <div><span>已保存原文</span><strong>{_escape(payload['summary']['prompt_stage_count'])}</strong></div>
        <div><span>Attempts</span><strong>{_escape(payload['summary']['attempt_count'])}</strong></div>
        <div><span>边界</span><strong>{_escape(payload['summary']['boundary_counts'])}</strong></div>
      </div>
    </header>
    <main class="layout">
      <aside class="pipeline" aria-label="Pipeline">
        <h2>流程图</h2>
        <div id="stage-list"></div>
      </aside>
      <section class="detail">
        <div class="detail-head">
          <div>
            <p class="eyebrow" id="stage-key">{_escape(first_stage)}</p>
            <h2 id="stage-title">选择一个 stage</h2>
          </div>
          <div class="toolbar">
            <input id="search" type="search" placeholder="搜索完整原文">
            <button id="copy-prompt" type="button" title="复制完整原文">复制</button>
          </div>
        </div>
        <nav class="tabs" aria-label="Stage tabs">
          <button data-tab="overview" class="active" type="button">总览</button>
          <button data-tab="prompt" type="button">完整原文</button>
          <button data-tab="input" type="button">输入数据</button>
          <button data-tab="rules" type="button">规则定位</button>
          <button data-tab="output" type="button">输出结果</button>
          <button data-tab="downstream" type="button">下游流向</button>
        </nav>
        <div id="tab-content" class="tab-content"></div>
      </section>
    </main>
  </div>
  <script type="application/json" id="inspector-data">{data_json}</script>
  <script>{self._js()}</script>
</body>
</html>
"""

    def _css(self) -> str:
        return """
:root {
  --bg: #f5f7f4;
  --ink: #17201c;
  --muted: #66736d;
  --line: #d8ded8;
  --panel: #ffffff;
  --accent: #176b61;
  --warn: #9c5a00;
  --bad: #a33a32;
  --code: #111816;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: Inter, ui-sans-serif, system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}
code, pre { font-family: "JetBrains Mono", ui-monospace, SFMono-Regular, Menlo, monospace; }
.app { min-height: 100vh; }
.topbar {
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 24px;
  padding: 28px 32px 22px;
  border-bottom: 1px solid var(--line);
  background: #fbfcfa;
}
.eyebrow { margin: 0 0 6px; color: var(--accent); font-size: 12px; font-weight: 700; letter-spacing: 0; text-transform: uppercase; }
h1, h2 { margin: 0; letter-spacing: 0; }
.topbar h1 { font-size: 34px; line-height: 1.08; }
.topbar p:last-child { max-width: 860px; color: var(--muted); line-height: 1.65; }
.summary { display: grid; grid-template-columns: repeat(2, 150px); gap: 8px; align-content: start; }
.summary div, .metric, .boundary-row, .rule-row, .output-box {
  border: 1px solid var(--line);
  background: var(--panel);
  border-radius: 8px;
  padding: 12px;
}
.summary span, .metric span { display: block; color: var(--muted); font-size: 12px; }
.summary strong, .metric strong { display: block; margin-top: 4px; font-size: 18px; }
.layout { display: grid; grid-template-columns: 320px minmax(0, 1fr); min-height: calc(100vh - 150px); }
.pipeline { border-right: 1px solid var(--line); padding: 22px; background: #eef3ef; }
.pipeline h2 { font-size: 16px; margin-bottom: 14px; }
.stage-button {
  width: 100%;
  display: grid;
  grid-template-columns: 1fr auto;
  gap: 8px;
  align-items: center;
  margin-bottom: 8px;
  padding: 11px 12px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--panel);
  color: var(--ink);
  text-align: left;
  cursor: pointer;
}
.stage-button.active { border-color: var(--accent); box-shadow: inset 3px 0 0 var(--accent); }
.stage-button small { color: var(--muted); }
.status { border-radius: 999px; padding: 3px 8px; font-size: 12px; background: #e8f2ef; color: var(--accent); }
.status.bad { background: #f8e7e5; color: var(--bad); }
.status.warn { background: #f7ead7; color: var(--warn); }
.detail { padding: 24px 30px 36px; overflow: auto; }
.detail-head { display: flex; justify-content: space-between; gap: 18px; align-items: start; margin-bottom: 18px; }
.toolbar { display: flex; gap: 8px; }
input[type="search"] { width: 260px; border: 1px solid var(--line); border-radius: 8px; padding: 10px 12px; background: #fff; }
button { font: inherit; }
.toolbar button, .tabs button {
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fff;
  padding: 10px 12px;
  cursor: pointer;
}
.tabs { display: flex; gap: 8px; flex-wrap: wrap; margin-bottom: 16px; }
.tabs button.active { background: var(--accent); color: #fff; border-color: var(--accent); }
.metric-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-bottom: 14px; }
.boundary-list, .rule-list, .downstream-list { display: grid; gap: 10px; }
.prompt-pre {
  white-space: pre-wrap;
  word-break: break-word;
  background: var(--code);
  color: #eef6f0;
  border-radius: 8px;
  padding: 18px;
  line-height: 1.55;
  min-height: 420px;
  border: 1px solid #0f1f1a;
}
.prompt-pre mark { background: #ffe08a; color: #111; padding: 0 2px; border-radius: 3px; }
.json-pre, .response-pre {
  white-space: pre-wrap;
  word-break: break-word;
  background: #fff;
  border: 1px solid var(--line);
  border-radius: 8px;
  padding: 14px;
  line-height: 1.5;
  max-height: 520px;
  overflow: auto;
}
.fileline { color: var(--muted); margin: 0 0 10px; }
.hash { color: var(--muted); overflow-wrap: anywhere; }
.empty { color: var(--muted); border: 1px dashed var(--line); border-radius: 8px; padding: 18px; }
@media (max-width: 880px) {
  .topbar, .layout, .detail-head { grid-template-columns: 1fr; display: block; }
  .summary, .metric-grid { grid-template-columns: 1fr 1fr; }
  .pipeline { border-right: 0; border-bottom: 1px solid var(--line); }
  .toolbar { margin-top: 12px; }
  input[type="search"] { width: 100%; }
}
"""

    def _js(self) -> str:
        return r"""
const payload = JSON.parse(document.getElementById('inspector-data').textContent);
const stages = payload.stages || [];
let selected = stages[0] || null;
let activeTab = 'overview';

const stageList = document.getElementById('stage-list');
const tabContent = document.getElementById('tab-content');
const stageTitle = document.getElementById('stage-title');
const stageKey = document.getElementById('stage-key');
const search = document.getElementById('search');
const copyPrompt = document.getElementById('copy-prompt');

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
}

function statusClass(status) {
  if (status === '违规' || status === 'failed') return 'bad';
  if (status === '可疑' || status === '未保存') return 'warn';
  return '';
}

function renderStageList() {
  stageList.innerHTML = stages.map(stage => {
    const status = stage.boundary?.status || stage.meta?.status || '未保存';
    const active = selected && selected.stage === stage.stage ? 'active' : '';
    return `<button class="stage-button ${active}" type="button" data-stage="${escapeHtml(stage.stage)}">
      <span><strong>${escapeHtml(stage.label)}</strong><br><small>${escapeHtml(stage.stage_name || stage.stage)}</small></span>
      <span class="status ${statusClass(status)}">${escapeHtml(status)}</span>
    </button>`;
  }).join('');
}

function selectStage(stageKeyValue) {
  selected = stages.find(stage => stage.stage === stageKeyValue) || stages[0] || null;
  renderStageList();
  renderDetail();
}

function currentAttempt() {
  if (!selected || !selected.attempts || !selected.attempts.length) return null;
  return selected.attempts[selected.attempts.length - 1];
}

function renderDetail() {
  if (!selected) {
    tabContent.innerHTML = '<div class="empty">没有找到 prompt_audit artifact。</div>';
    return;
  }
  stageTitle.textContent = selected.label;
  stageKey.textContent = selected.stage;
  if (activeTab === 'overview') renderOverview();
  if (activeTab === 'prompt') renderPrompt();
  if (activeTab === 'input') renderInput();
  if (activeTab === 'rules') renderRules();
  if (activeTab === 'output') renderOutput();
  if (activeTab === 'downstream') renderDownstream();
}

function renderOverview() {
  const attempt = currentAttempt();
  const meta = selected.meta || {};
  const boundary = selected.boundary || {};
  const findings = (boundary.findings || []).map(item => `<div class="boundary-row"><strong>${escapeHtml(item.rule)}</strong><p>${escapeHtml(item.excerpt)}</p></div>`).join('');
  tabContent.innerHTML = `
    <div class="metric-grid">
      <div class="metric"><span>运行模式</span><strong>${escapeHtml(meta.mode || '')}</strong></div>
      <div class="metric"><span>effective date</span><strong>${escapeHtml(meta.effective_date || '')}</strong></div>
      <div class="metric"><span>model</span><strong>${escapeHtml(meta.model || '')}</strong></div>
      <div class="metric"><span>attempts</span><strong>${escapeHtml(meta.attempts || selected.attempts.length || 0)}</strong></div>
      <div class="metric"><span>prompt chars</span><strong>${escapeHtml(meta.prompt_chars || attempt?.prompt_text?.length || 0)}</strong></div>
      <div class="metric"><span>status</span><strong>${escapeHtml(meta.status || selected.diagnostics?.status || '')}</strong></div>
      <div class="metric"><span>边界检查</span><strong>${escapeHtml(boundary.status || '')}</strong></div>
      <div class="metric"><span>output</span><strong>${escapeHtml(meta.output_artifact || selected.validated_output_file || '')}</strong></div>
    </div>
    <p class="fileline">Prompt 文件：${escapeHtml(attempt?.prompt_file || '')}</p>
    <p class="hash">SHA256：${escapeHtml(attempt?.prompt_sha256 || meta.prompt_sha256 || '')}</p>
    <div class="boundary-list">${findings || '<div class="empty">未发现命中的越权片段。</div>'}</div>`;
}

function highlightedPrompt(text, term) {
  const safe = escapeHtml(text);
  if (!term) return safe;
  const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return safe.replace(new RegExp(escaped, 'gi'), match => `<mark>${match}</mark>`);
}

function renderPrompt() {
  const attempt = currentAttempt();
  if (!attempt) {
    tabContent.innerHTML = '<div class="empty">这个 stage 没有保存完整原文。</div>';
    return;
  }
  tabContent.innerHTML = `
    <p class="fileline">${escapeHtml(attempt.prompt_file)} · hash ${attempt.hash_matches_meta ? '一致' : '不一致'}</p>
    <pre class="prompt-pre">${highlightedPrompt(attempt.prompt_text || '', search.value.trim())}</pre>`;
}

function renderInput() {
  const attempt = currentAttempt();
  const data = attempt?.payload || {};
  tabContent.innerHTML = `
    <p class="fileline">${escapeHtml(attempt?.payload_file || '')}</p>
    <pre class="json-pre">${escapeHtml(JSON.stringify(data, null, 2))}</pre>`;
}

function renderRules() {
  const rows = (selected.rule_hits || []).map(hit => `
    <div class="rule-row">
      <strong>${escapeHtml(hit.label)}</strong>
      <p class="fileline">offset ${escapeHtml(hit.offset)}</p>
      <pre class="response-pre">${escapeHtml(hit.excerpt)}</pre>
    </div>`).join('');
  tabContent.innerHTML = `<div class="rule-list">${rows || '<div class="empty">未定位到规则关键词；请直接查看完整原文。</div>'}</div>`;
}

function renderOutput() {
  const attempt = currentAttempt();
  tabContent.innerHTML = `
    <div class="output-box">
      <h3>Raw response</h3>
      <p class="fileline">${escapeHtml(attempt?.raw_response_file || '')}</p>
      <pre class="response-pre">${escapeHtml(attempt?.raw_response || '')}</pre>
    </div>
    <div class="output-box">
      <h3>Validated JSON</h3>
      <p class="fileline">${escapeHtml(selected.validated_output_file || '')}</p>
      <pre class="json-pre">${escapeHtml(JSON.stringify(selected.validated_output || {}, null, 2))}</pre>
    </div>`;
}

function renderDownstream() {
  const rows = (selected.downstream || []).map(item => `<div class="boundary-row">${escapeHtml(item)}</div>`).join('');
  tabContent.innerHTML = `<div class="downstream-list">${rows || '<div class="empty">暂无下游追踪。</div>'}</div>`;
}

stageList.addEventListener('click', event => {
  const button = event.target.closest('[data-stage]');
  if (button) selectStage(button.dataset.stage);
});
document.querySelectorAll('[data-tab]').forEach(button => {
  button.addEventListener('click', () => {
    activeTab = button.dataset.tab;
    document.querySelectorAll('[data-tab]').forEach(node => node.classList.toggle('active', node === button));
    renderDetail();
  });
});
search.addEventListener('input', () => {
  if (activeTab === 'prompt') renderPrompt();
});
copyPrompt.addEventListener('click', async () => {
  const attempt = currentAttempt();
  if (!attempt || !navigator.clipboard) return;
  await navigator.clipboard.writeText(attempt.prompt_text || '');
  copyPrompt.textContent = '已复制';
  setTimeout(() => { copyPrompt.textContent = '复制'; }, 1000);
});

renderStageList();
renderDetail();
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate Agent Prompt Inspector from a vNext run directory.")
    parser.add_argument("--run-dir", required=True, help="Path to output/analysis/vnext/<run_id>.")
    parser.add_argument("--output", help="Optional output HTML path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output = PromptInspectorGenerator().run(args.run_dir, output_path=args.output)
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
