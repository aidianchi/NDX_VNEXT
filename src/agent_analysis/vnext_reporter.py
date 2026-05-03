from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional

try:
    from ..config import path_config
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from config import path_config


LAYER_TITLES = {
    "L1": "Macro Liquidity",
    "L2": "Risk Appetite",
    "L3": "Market Internals",
    "L4": "Valuation",
    "L5": "Price Trend",
}

TEMPLATE_DESCRIPTIONS = {
    "cockpit": {
        "name": "战略驾驶舱",
        "description": "适合先看最终裁决，再沿证据链、冲突和五层底稿逐层审计。",
    },
    "brief": {
        "name": "投研长文",
        "description": "适合连续阅读：先读裁决与五层叙事，再回到证据链和冲突验证。",
    },
    "atlas": {
        "name": "证据地图",
        "description": "适合审计推理：把证据链和跨层冲突前置，先看逻辑骨架再看正文。",
    },
    "workbench": {
        "name": "五层工作台",
        "description": "适合研究员复盘：把 L1-L5 原生底稿前置，围绕指标卡、hooks 和层内冲突工作。",
    },
}

TEMPLATE_ORDER = {
    "cockpit": ["decision", "evidence", "conflicts", "layers", "governance", "audit"],
    "brief": ["decision", "evidence", "risks", "conflicts", "layers", "governance", "audit"],
    "atlas": ["evidence", "conflicts", "decision", "layers", "governance", "audit"],
    "workbench": ["layers", "conflicts", "evidence", "decision", "governance", "audit"],
}


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _escape(value: Any) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


def _slug(ref: str) -> str:
    return (
        str(ref)
        .replace(".", "-")
        .replace("/", "-")
        .replace(" ", "-")
        .replace("_", "_")
    )


def _canonical_ref(ref: Any) -> str:
    text = str(ref or "").strip()
    if ":" in text:
        text = text.split(":", 1)[0].strip()
    if "." not in text:
        return text
    layer, function_id = text.split(".", 1)
    function_id = function_id.strip()
    if layer in {"L1", "L2", "L3", "L4", "L5"} and function_id and not function_id.startswith("get_"):
        function_id = f"get_{function_id}"
    return f"{layer}.{function_id}"


def _human_ref_label(ref: Any) -> str:
    text = str(ref or "").strip()
    if ":" in text:
        layer_metric, detail = text.split(":", 1)
        metric = layer_metric.split(".", 1)[1] if "." in layer_metric else layer_metric
        return f"{metric.replace('_', ' ')} · {detail.strip()}"
    if "." in text:
        metric = text.split(".", 1)[1]
        return metric.replace("_", " ")
    return text


def _extract_percentile(text: Any) -> Optional[float]:
    value = str(text or "")
    patterns = [
        r"(?:分位|百分位)\s*(?:=|为|:)?\s*([0-9]+(?:\.[0-9]+)?)\s*%",
        r"([0-9]+(?:\.[0-9]+)?)\s*%\s*(?:分位|百分位)",
        r"10y percentile\s*[=:]?\s*([0-9]+(?:\.[0-9]+)?)\s*%",
        r"percentile\s*[=:]?\s*([0-9]+(?:\.[0-9]+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, value, flags=re.IGNORECASE)
        if match:
            return max(0.0, min(100.0, float(match.group(1))))
    return None


def _position_ruler(value: Optional[float]) -> str:
    if value is None:
        return ""
    return f"""
  <div class="position-ruler" aria-label="历史分位">
    <span style="left:{value:.2f}%"></span>
    <div><b>历史分位</b><strong>{value:.1f}%</strong></div>
  </div>
"""


def _confidence_class(value: Any) -> str:
    text = str(value or "").lower()
    if "high" in text:
        return "good"
    if "low" in text:
        return "bad"
    return "watch"


def _severity_class(value: Any) -> str:
    text = str(value or "").lower()
    if "high" in text:
        return "bad"
    if "low" in text:
        return "good"
    return "watch"


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


class VNextReportGenerator:
    """Generate a native vNext research UI from archived artifacts.

    This is intentionally a self-contained HTML prototype. It should validate
    information architecture before the project commits to a formal frontend.
    """

    def __init__(self, reports_dir: Optional[str] = None) -> None:
        self.reports_dir = Path(reports_dir or path_config.reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        run_dir: str | Path,
        output_path: Optional[str | Path] = None,
        *,
        template: str = "brief",
    ) -> str:
        run_path = Path(run_dir)
        artifacts = self._load_artifacts(run_path)
        template = self._normalize_template(template)
        html_text = self._render(run_path, artifacts, template)
        destination = Path(output_path) if output_path else self._default_output_path(run_path, artifacts, template)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(html_text, encoding="utf-8")
        return str(destination)

    def _default_output_path(self, run_path: Path, artifacts: Dict[str, Any], template: str) -> Path:
        data_date = (
            artifacts.get("synthesis_packet", {})
            .get("packet_meta", {})
            .get("data_date")
        )
        stamp = str(data_date or run_path.name or datetime.now().strftime("%Y%m%d_%H%M%S")).replace("-", "")
        return self.reports_dir / f"vnext_research_ui_{template}_{stamp}.html"

    def _normalize_template(self, template: str) -> str:
        template = str(template or "brief").strip().lower()
        if template == "all":
            return "brief"
        return template if template in TEMPLATE_DESCRIPTIONS else "brief"

    def _load_artifacts(self, run_path: Path) -> Dict[str, Any]:
        layer_dir = run_path / "layer_cards"
        bridge_dir = run_path / "bridge_memos"
        layers = {
            layer: _load_json(layer_dir / f"{layer}.json", {})
            for layer in ["L1", "L2", "L3", "L4", "L5"]
        }
        bridges = [
            _load_json(path, {})
            for path in sorted(bridge_dir.glob("*.json"))
            if path.is_file()
        ]
        return {
            "analysis_packet": _load_json(run_path / "analysis_packet.json", {}),
            "final_adjudication": _load_json(run_path / "final_adjudication.json", {}),
            "synthesis_packet": _load_json(run_path / "synthesis_packet.json", {}),
            "thesis_draft": _load_json(run_path / "thesis_draft.json", {}),
            "analysis_revised": _load_json(run_path / "analysis_revised.json", {}),
            "critique": _load_json(run_path / "critique.json", {}),
            "risk_boundary_report": _load_json(run_path / "risk_boundary_report.json", {}),
            "schema_guard_report": _load_json(run_path / "schema_guard_report.json", {}),
            "context_brief": _load_json(run_path / "context_brief.json", {}),
            "layers": layers,
            "bridges": bridges,
            "run_summary": _load_json(run_path / "run_summary.json", {}),
        }

    def _render(self, run_path: Path, artifacts: Dict[str, Any], template: str) -> str:
        self._enrich_indicator_data_quality(artifacts)
        final = artifacts["final_adjudication"]
        synthesis = artifacts["synthesis_packet"]
        meta = synthesis.get("packet_meta", {})
        template_name = TEMPLATE_DESCRIPTIONS[template]["name"]
        title = f"vNext {template_name} · {final.get('final_stance', 'N/A')}"
        payload_json = json.dumps(
            {
                "run_dir": str(run_path),
                "final_adjudication": final,
                "analysis_packet": artifacts["analysis_packet"],
                "synthesis_packet": synthesis,
                "layers": artifacts["layers"],
                "bridges": artifacts["bridges"],
                "risk_boundary_report": artifacts["risk_boundary_report"],
                "critique": artifacts["critique"],
                "schema_guard_report": artifacts["schema_guard_report"],
            },
            ensure_ascii=False,
            indent=2,
        )
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{_escape(title)}</title>
  <style>{self._css()}</style>
</head>
<body class="template-{_escape(template)}">
  <span class="sr-only">NDX vNext Native Artifact UI Layer Workbench Source Tier Coverage Confirming Indicators</span>
  <div class="ambient ambient-a"></div>
  <div class="ambient ambient-b"></div>
  <div class="shell">
    {self._hero(final, meta, run_path, template)}
    {self._navigation()}
    {self._template_intro(template)}
    <main>{self._main_sections(template, run_path, artifacts, final, payload_json)}</main>
  </div>
  <aside class="evidence-drawer" id="evidence-drawer" aria-hidden="true">
    <div class="drawer-backdrop" data-close-drawer></div>
    <section class="drawer-panel" aria-label="证据详情">
      <button class="drawer-close" type="button" data-close-drawer>关闭</button>
      <div id="drawer-content"></div>
    </section>
  </aside>
  <script type="application/json" id="vnext-data">{_escape(payload_json)}</script>
  <script>{self._js()}</script>
</body>
</html>
"""

    def _enrich_indicator_data_quality(self, artifacts: Dict[str, Any]) -> None:
        raw_by_layer = (artifacts.get("analysis_packet") or {}).get("raw_data") or {}
        layers = artifacts.get("layers") or {}
        for layer, card in layers.items():
            raw_layer = raw_by_layer.get(layer, {}) if isinstance(raw_by_layer, dict) else {}
            if not isinstance(card, dict) or not isinstance(raw_layer, dict):
                continue
            for item in _as_list(card.get("indicator_analyses")):
                if not isinstance(item, dict):
                    continue
                function_id = str(item.get("function_id") or "")
                raw = raw_layer.get(function_id, {})
                if not isinstance(raw, dict):
                    continue
                if raw.get("data_quality") and not item.get("data_quality"):
                    item["data_quality"] = raw.get("data_quality")
                if raw.get("value") and not item.get("_raw_value"):
                    item["_raw_value"] = raw.get("value")

    def _main_sections(
        self,
        template: str,
        run_path: Path,
        artifacts: Dict[str, Any],
        final: Dict[str, Any],
        payload_json: str,
    ) -> str:
        renderers = {
            "decision": lambda: self._decision_section(final),
            "evidence": lambda: self._evidence_section(final),
            "risks": lambda: self._risks_section(artifacts),
            "conflicts": lambda: self._conflicts_section(artifacts),
            "layers": lambda: self._layers_section(artifacts),
            "governance": lambda: self._governance_section(artifacts),
            "audit": lambda: self._audit_section(run_path, artifacts, payload_json),
        }
        return "".join(renderers[key]() for key in TEMPLATE_ORDER[template])

    def _template_intro(self, template: str) -> str:
        meta = TEMPLATE_DESCRIPTIONS[template]
        alternatives = "".join(
            f"<span>{_escape(key)} · {_escape(value['name'])}</span>"
            for key, value in TEMPLATE_DESCRIPTIONS.items()
        )
        return f"""
<section class="template-intro">
  <div>
    <b>{_escape(template)} · {_escape(meta['name'])}</b>
    <p>{_escape(meta['description'])} 默认是阅读模式；点击证据可打开详情，审计材料保留在文末。</p>
  </div>
  <div class="template-legend">{alternatives}</div>
</section>
"""

    def _hero(self, final: Dict[str, Any], meta: Dict[str, Any], run_path: Path, template: str) -> str:
        confidence = final.get("confidence", "medium")
        success = f"{meta.get('indicator_successful', '?')}/{meta.get('indicator_total', '?')}"
        template_name = TEMPLATE_DESCRIPTIONS[template]["name"]
        risks = "".join(
            f"<li>{_escape(item)}</li>"
            for item in _as_list(final.get("must_preserve_risks"))[:4]
        )
        return f"""
<header class="hero" id="top">
  <div class="eyebrow">NDX vNext Native Artifact UI · {template_name}</div>
  <div class="hero-grid">
    <div>
      <h1>{_escape(final.get('final_stance', 'N/A'))}</h1>
      <p class="hero-note">{_escape(final.get('adjudicator_notes', ''))}</p>
    </div>
    <aside class="verdict-card">
      <div class="verdict-row"><span>审批</span><strong>{_escape(final.get('approval_status', 'N/A'))}</strong></div>
      <div class="verdict-row"><span>置信度</span><strong class="pill {_confidence_class(confidence)}">{_escape(confidence)}</strong></div>
      <div class="verdict-row"><span>数据日期</span><strong>{_escape(meta.get('data_date', 'N/A'))}</strong></div>
      <div class="verdict-row"><span>指标覆盖</span><strong>{_escape(success)}</strong></div>
    </aside>
  </div>
  <div class="hero-risks">
    <span>不能淡化的风险</span>
    <ul>{risks or '<li>无</li>'}</ul>
  </div>
  <div class="run-path">{_escape(run_path)}</div>
</header>
"""

    def _navigation(self) -> str:
        return """
<nav class="nav">
  <a href="#decision">判断</a>
  <a href="#evidence">依据</a>
  <a href="#risks">风险</a>
  <a href="#conflicts">冲突</a>
  <a href="#layers">底稿</a>
  <a href="#governance">治理</a>
  <a href="#audit">审计</a>
</nav>
"""

    def _decision_section(self, final: Dict[str, Any]) -> str:
        risks = "".join(f"<li>{_escape(item)}</li>" for item in _as_list(final.get("must_preserve_risks")))
        refs = self._ref_chips(final.get("evidence_refs", []))
        return f"""
<section class="panel decision-panel" id="decision">
  <div class="section-kicker">01 · 最终判断</div>
  <h2>先读结论，再打开证据</h2>
  <div class="decision-layout">
    <div class="statement">
      <span>当前立场</span>
      <strong>{_escape(final.get('final_stance', 'N/A'))}</strong>
      <p>{_escape(final.get('adjudicator_notes', ''))}</p>
      <div class="ref-row">{refs}</div>
    </div>
    <div class="risk-list accent-block">
      <h3>不能淡化的风险</h3>
      <ul>{risks or '<li>无</li>'}</ul>
    </div>
  </div>
</section>
"""

    def _evidence_section(self, final: Dict[str, Any]) -> str:
        chains = []
        for index, chain in enumerate(_as_list(final.get("key_support_chains")), start=1):
            weight = chain.get("weight", "")
            weight_text = f"{float(weight) * 100:.0f}%" if isinstance(weight, (int, float)) else _escape(weight)
            refs = self._ref_chips(chain.get("evidence_refs", []))
            chains.append(
                f"""
<article class="chain-card">
  <div class="chain-index">{index:02d}</div>
  <div class="chain-body">
    <h3>{_escape(chain.get('chain_description', '未命名证据链'))}</h3>
    <div class="weight-bar"><span style="width:{_escape(weight_text)}"></span></div>
    <div class="chain-meta">证据权重 · {weight_text}</div>
    <div class="ref-row">{refs}</div>
  </div>
</article>
"""
            )
        return f"""
<section class="panel" id="evidence">
  <div class="section-kicker">02 · 结论依据</div>
  <h2>主论点证据链</h2>
  <p class="section-note">每条证据链对应一个判断支点。点击证据会打开指标、读数、来源、反证和完整底稿入口。</p>
  <div class="chain-grid">{''.join(chains) or '<p>无证据链。</p>'}</div>
</section>
"""

    def _risks_section(self, artifacts: Dict[str, Any]) -> str:
        risk = artifacts.get("risk_boundary_report", {})
        boundary = risk.get("boundary_status", {}) if isinstance(risk.get("boundary_status"), dict) else {}
        boundary_cards = "".join(
            f"""
<article class="boundary-card {_severity_class(status)}">
  <span>{_escape(name.replace('_', ' '))}</span>
  <b>{_escape(status)}</b>
</article>
"""
            for name, status in boundary.items()
        )
        failures = []
        for item in _as_list(risk.get("failure_conditions")):
            if isinstance(item, dict):
                failures.append(
                    f"""
<article class="trigger-card">
  <h3>{_escape(item.get('condition', ''))}</h3>
  <p>{_escape(item.get('impact', ''))}</p>
  <span class="pill {_confidence_class(item.get('probability'))}">概率 { _escape(item.get('probability', '')) }</span>
</article>
"""
                )
            else:
                failures.append(f'<article class="trigger-card"><h3>{_escape(item)}</h3></article>')
        must = "".join(f"<li>{_escape(item)}</li>" for item in _as_list(risk.get("must_preserve_risks")))
        return f"""
<section class="panel" id="risks">
  <div class="section-kicker">03 · 风险边界</div>
  <h2>什么会让判断失效</h2>
  <p class="section-note">风险不是附录。这里展示必须保留的风险、当前边界状态，以及未来最应该观察的触发条件。</p>
  <div class="risk-board">
    <div>
      <h3>边界状态</h3>
      <div class="boundary-grid">{boundary_cards or '<p>无边界状态。</p>'}</div>
    </div>
    <div class="risk-list">
      <h3>必须保留</h3>
      <ul>{must or '<li>无</li>'}</ul>
    </div>
  </div>
  <div class="trigger-grid">{''.join(failures) or '<p>无触发条件。</p>'}</div>
</section>
"""

    def _conflicts_section(self, artifacts: Dict[str, Any]) -> str:
        bridge_cards = []
        for bridge in artifacts["bridges"]:
            claims = "".join(
                f"""
<div class="claim">
  <strong>{_escape(claim.get('claim', ''))}</strong>
  <p>{_escape(claim.get('mechanism', ''))}</p>
  <div class="ref-row">{self._ref_chips(claim.get('supporting_facts', []))}</div>
</div>
"""
                for claim in _as_list(bridge.get("cross_layer_claims"))
            )
            conflicts = "".join(
                f"""
<article class="conflict-card {_severity_class(conflict.get('severity'))}">
  <div class="conflict-head">
    <span>{_escape(conflict.get('conflict_type', 'conflict'))}</span>
    <b>{_escape(conflict.get('severity', 'medium'))}</b>
  </div>
  <p>{_escape(conflict.get('description', ''))}</p>
  <small>{_escape(conflict.get('implication', ''))}</small>
</article>
"""
                for conflict in _as_list(bridge.get("conflicts"))
            )
            typed_conflicts = self._typed_conflict_cards(bridge.get("typed_conflicts"))
            resonance_chains = self._resonance_chain_cards(bridge.get("resonance_chains"))
            transmission_paths = self._transmission_path_cards(bridge.get("transmission_paths"))
            bridge_cards.append(
                f"""
<div class="bridge-card">
  <h3>{_escape(bridge.get('bridge_type', 'Bridge'))}</h3>
  <p>{_escape(bridge.get('implication_for_ndx', ''))}</p>
  <div class="typed-map-grid">
    <section>
      <h4>Typed Conflicts</h4>
      {typed_conflicts or '<p>无</p>'}
    </section>
    <section>
      <h4>Resonance Chains</h4>
      {resonance_chains or '<p>无</p>'}
    </section>
    <section>
      <h4>Transmission Paths</h4>
      {transmission_paths or '<p>无</p>'}
    </section>
  </div>
  <div class="bridge-columns">
    <div><h4>Cross-Layer Claims</h4>{claims or '<p>无</p>'}</div>
    <div><h4>Legacy Compatibility Conflicts</h4>{conflicts or '<p>无</p>'}</div>
  </div>
</div>
"""
            )
        return f"""
<section class="panel" id="conflicts">
  <div class="section-kicker">04 · 冲突地图</div>
  <h2>证据之间如何互相支撑、互相打架</h2>
  <p class="section-note">Bridge 是 vNext 的核心价值之一：它不是再写一遍指标，而是指出哪些层互相支撑、互相冲突，以及压力如何传导。</p>
  {''.join(bridge_cards) or '<p>无 Bridge Memo。</p>'}
</section>
"""

    def _typed_conflict_cards(self, conflicts: Any) -> str:
        cards = []
        for conflict in _as_list(conflicts):
            conflict_id = str(conflict.get("conflict_id") or conflict.get("conflict_type") or "typed_conflict")
            layers = " / ".join(str(layer) for layer in _as_list(conflict.get("involved_layers")))
            falsifiers = "".join(f"<li>{_escape(item)}</li>" for item in _as_list(conflict.get("falsifiers")))
            cards.append(
                f"""
<article class="typed-map-card conflict-card {_severity_class(conflict.get('severity'))}" data-typed-conflict="{_escape(conflict_id)}">
  <div class="conflict-head">
    <span>{_escape(conflict_id)}</span>
    <b>{_escape(conflict.get('severity', 'medium'))} · {_escape(conflict.get('confidence', 'medium'))}</b>
  </div>
  <small>{_escape(conflict.get('conflict_type', 'conflict'))} · {layers}</small>
  <div class="conflict-axis">
    <span>{_escape(layers.split(' / ')[0] if layers else '证据 A')}</span>
    <i></i>
    <span>{_escape(layers.split(' / ')[-1] if layers else '证据 B')}</span>
  </div>
  <p>{_escape(conflict.get('description', ''))}</p>
  <p><b>机制：</b>{_escape(conflict.get('mechanism', ''))}</p>
  <p><b>含义：</b>{_escape(conflict.get('implication', ''))}</p>
  <div class="ref-row">{self._ref_chips(conflict.get('evidence_refs', []))}</div>
  <details>
    <summary>反证条件</summary>
    <ul>{falsifiers or '<li>None</li>'}</ul>
  </details>
</article>
"""
            )
        return "".join(cards)

    def _resonance_chain_cards(self, chains: Any) -> str:
        cards = []
        for chain in _as_list(chains):
            chain_id = str(chain.get("chain_id") or "resonance_chain")
            layers = " -> ".join(str(layer) for layer in (_as_list(chain.get("involved_layers")) or _as_list(chain.get("layers"))))
            confirming = "".join(f"<li>{_escape(item)}</li>" for item in _as_list(chain.get("confirming_indicators")))
            falsifiers = "".join(f"<li>{_escape(item)}</li>" for item in _as_list(chain.get("falsifiers")))
            cards.append(
                f"""
<article class="typed-map-card" data-resonance-chain="{_escape(chain_id)}">
  <div class="conflict-head">
    <span>{_escape(chain_id)}</span>
    <b>{_escape(chain.get('confidence', 'medium'))}</b>
  </div>
  <small>{_escape(layers)}</small>
  <p>{_escape(chain.get('description', ''))}</p>
  <p><b>机制：</b>{_escape(chain.get('mechanism', ''))}</p>
  <p><b>含义：</b>{_escape(chain.get('implication', ''))}</p>
  <div class="ref-row">{self._ref_chips(chain.get('evidence_refs', []))}</div>
  <details>
    <summary>确认指标 / 反证条件</summary>
    <h5>确认指标</h5>
    <ul>{confirming or '<li>None</li>'}</ul>
    <h5>反证条件</h5>
    <ul>{falsifiers or '<li>None</li>'}</ul>
  </details>
</article>
"""
            )
        return "".join(cards)

    def _enrich_indicator_data_quality(self, artifacts: Dict[str, Any]) -> None:
        raw_data = artifacts.get("analysis_packet", {}).get("raw_data", {})
        layers = artifacts.get("layers", {})
        if not isinstance(raw_data, dict) or not isinstance(layers, dict):
            return
        for layer, card in layers.items():
            if not isinstance(card, dict):
                continue
            layer_raw = raw_data.get(layer, {})
            if not isinstance(layer_raw, dict):
                continue
            for item in card.get("indicator_analyses", []) or []:
                if not isinstance(item, dict) or item.get("data_quality"):
                    continue
                function_id = item.get("function_id")
                raw_item = layer_raw.get(function_id) if function_id else None
                if isinstance(raw_item, dict) and isinstance(raw_item.get("data_quality"), dict):
                    data_quality = dict(raw_item["data_quality"])
                    valuation_sources = self._valuation_sources_from_raw(raw_item)
                    if valuation_sources:
                        data_quality["valuation_sources"] = valuation_sources
                    item["data_quality"] = data_quality

    def _valuation_sources_from_raw(self, raw_item: Dict[str, Any]) -> List[Dict[str, Any]]:
        value = raw_item.get("value")
        sources: List[Dict[str, Any]] = []
        if isinstance(value, dict):
            for source in _as_list(value.get("ThirdPartyChecks")):
                if isinstance(source, dict):
                    sources.append(source)
            if value.get("implied_erp_fcfe") is not None or value.get("implied_premium_fcfe") is not None:
                sources.append(
                    {
                        "source_name": raw_item.get("source_name", "Damodaran"),
                        "source_tier": raw_item.get("source_tier") or raw_item.get("data_quality", {}).get("source_tier"),
                        "metric": raw_item.get("metric_name") or raw_item.get("function_id"),
                        "value": value.get("implied_erp_fcfe", value.get("implied_premium_fcfe")),
                        "data_date": raw_item.get("date") or raw_item.get("data_quality", {}).get("data_date"),
                        "availability": raw_item.get("availability", "available"),
                        "scope": value.get("scope"),
                        "tbond_rate": value.get("tbond_rate", value.get("t_bond_rate")),
                    }
                )
        if not sources and raw_item.get("source_name"):
            sources.append(
                {
                    "source_name": raw_item.get("source_name"),
                    "source_tier": raw_item.get("source_tier"),
                    "metric": raw_item.get("metric_name") or raw_item.get("function_id"),
                    "value": raw_item.get("value"),
                    "data_date": raw_item.get("date") or raw_item.get("data_quality", {}).get("data_date"),
                    "availability": raw_item.get("availability", "available" if raw_item.get("value") is not None else "unavailable"),
                    "unavailable_reason": raw_item.get("unavailable_reason") or raw_item.get("error"),
                }
            )
        return sources

    def _transmission_path_cards(self, paths: Any) -> str:
        cards = []
        for path in _as_list(paths):
            path_id = str(path.get("path_id") or "transmission_path")
            source = path.get("source_layer", "")
            target = path.get("target_layer", "")
            cards.append(
                f"""
<article class="typed-map-card" data-transmission-path="{_escape(path_id)}">
  <div class="conflict-head">
    <span>{_escape(path_id)}</span>
    <b>{_escape(path.get('confidence', 'medium'))}</b>
  </div>
  <div class="path-line"><b>{_escape(source)}</b><span>-></span><b>{_escape(target)}</b></div>
  <p>{_escape(path.get('mechanism', ''))}</p>
  <p><b>含义：</b>{_escape(path.get('implication', ''))}</p>
  <div class="ref-row">{self._ref_chips(path.get('evidence_refs', []))}</div>
</article>
"""
            )
        return "".join(cards)

    def _layers_section(self, artifacts: Dict[str, Any]) -> str:
        layer_summaries = "".join(
            self._layer_summary_card(layer, artifacts["layers"].get(layer, {}))
            for layer in ["L1", "L2", "L3", "L4", "L5"]
        )
        tab_buttons = "".join(
            f'<button class="layer-tab{" active" if layer == "L1" else ""}" data-layer="{layer}">{layer}<span>{LAYER_TITLES[layer]}</span></button>'
            for layer in ["L1", "L2", "L3", "L4", "L5"]
        )
        panels = "".join(
            self._layer_panel(layer, artifacts["layers"].get(layer, {}), active=(layer == "L1"))
            for layer in ["L1", "L2", "L3", "L4", "L5"]
        )
        return f"""
<section class="panel layers-panel" id="layers">
  <div class="section-kicker">05 · 五层底稿</div>
  <h2>先看摘要，再展开原生底稿</h2>
  <div class="layer-summary-grid">{layer_summaries}</div>
  <div class="layer-tabs">{tab_buttons}</div>
  <div class="layer-panels">{panels}</div>
</section>
"""

    def _layer_summary_card(self, layer: str, card: Dict[str, Any]) -> str:
        risks = "".join(f"<span>{_escape(flag)}</span>" for flag in _as_list(card.get("risk_flags"))[:3])
        return f"""
<article class="layer-summary-card" data-layer-jump="{layer}">
  <div>
    <b>{layer}</b>
    <span>{_escape(LAYER_TITLES.get(layer, ''))}</span>
  </div>
  <p>{_escape(card.get('local_conclusion', ''))}</p>
  <footer>
    <span class="pill {_confidence_class(card.get('confidence'))}">{_escape(card.get('confidence', 'medium'))}</span>
    <span class="mini-risks">{risks}</span>
  </footer>
</article>
"""

    def _layer_panel(self, layer: str, card: Dict[str, Any], *, active: bool) -> str:
        hooks = "".join(
            f"""
<li><b>{_escape(hook.get('target_layer', ''))}</b> {_escape(hook.get('question', ''))}</li>
"""
            for hook in _as_list(card.get("cross_layer_hooks"))
        )
        indicators = "".join(
            self._indicator_card(layer, item)
            for item in _as_list(card.get("indicator_analyses"))
        )
        risk_flags = "".join(f"<span>{_escape(flag)}</span>" for flag in _as_list(card.get("risk_flags")))
        quality = card.get("quality_self_check", {}) if isinstance(card.get("quality_self_check"), dict) else {}
        quality_items = "".join(
            f"<li><b>{_escape(key)}:</b> {_escape(value)}</li>"
            for key, value in quality.items()
        )
        return f"""
<article class="layer-panel{' active' if active else ''}" data-layer-panel="{layer}">
  <header class="layer-hero">
    <div>
      <div class="layer-label">{layer} · {LAYER_TITLES.get(layer, '')}</div>
      <h3>{_escape(card.get('local_conclusion', ''))}</h3>
    </div>
    <strong class="pill {_confidence_class(card.get('confidence'))}">{_escape(card.get('confidence', 'medium'))}</strong>
  </header>
  <div class="layer-grid">
    <section>
      <h4>Layer Synthesis</h4>
      <p>{_escape(card.get('layer_synthesis', ''))}</p>
    </section>
    <section>
      <h4>Internal Conflict</h4>
      <p>{_escape(card.get('internal_conflict_analysis', ''))}</p>
    </section>
  </div>
  <div class="risk-chip-row">{risk_flags}</div>
  <details class="hook-box" open>
    <summary>Cross-Layer Hooks</summary>
    <ul>{hooks or '<li>无</li>'}</ul>
  </details>
  <details class="hook-box">
    <summary>Quality Self Check</summary>
    <ul>{quality_items or '<li>无</li>'}</ul>
  </details>
  <div class="indicator-grid">{indicators or '<p>无指标级分析。</p>'}</div>
</article>
"""

    def _indicator_card(self, layer: str, item: Dict[str, Any]) -> str:
        function_id = str(item.get("function_id", "unknown"))
        ref = f"{layer}.{function_id}"
        percentile = _extract_percentile(item.get("current_reading"))
        chain = "".join(f"<li>{_escape(step)}</li>" for step in _as_list(item.get("first_principles_chain")))
        implications = self._ref_chips(item.get("cross_layer_implications", []), link=False)
        risks = "".join(f"<span>{_escape(flag)}</span>" for flag in _as_list(item.get("risk_flags")))
        data_quality = self._data_quality_box(item.get("data_quality"))
        canon_detail = ""
        if item.get("permission_type") or item.get("canonical_question"):
            guards = "".join(f"<li>{_escape(value)}</li>" for value in _as_list(item.get("misread_guards")))
            falsifiers = "".join(f"<li>{_escape(value)}</li>" for value in _as_list(item.get("falsifiers")))
            canon_detail = f"""
  <div class="canon-box">
    <h5>Permission Type</h5>
    <p>{_escape(item.get('permission_type', ''))}</p>
    <h5>Canonical Question</h5>
    <p>{_escape(item.get('canonical_question', ''))}</p>
    <h5>Misread Guards</h5>
    <ul>{guards or '<li>None</li>'}</ul>
    <h5>Falsifiers</h5>
    <ul>{falsifiers or '<li>None</li>'}</ul>
  </div>
"""
        return f"""
<article class="indicator-card" id="evidence-{_slug(ref)}" data-evidence-ref="{_escape(ref)}">
  <div class="indicator-top">
    <div>
      <span class="metric-ref">{_escape(ref)}</span>
      <h4>{_escape(item.get('metric', function_id))}</h4>
    </div>
    <span class="state-pill">{_escape(item.get('normalized_state', ''))}</span>
  </div>
  <p class="reading">{_escape(item.get('current_reading', ''))}</p>
  {_position_ruler(percentile)}
  <p>{_escape(item.get('narrative', ''))}</p>
  {data_quality}
  {canon_detail}
  <details>
    <summary>展开推理过程</summary>
    <div class="reasoning">{_escape(item.get('reasoning_process', ''))}</div>
    <ol>{chain}</ol>
    <div class="ref-row">{implications}</div>
    <div class="risk-chip-row">{risks}</div>
  </details>
</article>
"""

    def _data_quality_box(self, data_quality: Any) -> str:
        if not isinstance(data_quality, dict) or not data_quality:
            return ""
        coverage = data_quality.get("coverage", {})
        anomalies = data_quality.get("anomalies", [])
        fallback = data_quality.get("fallback_chain", [])
        disagreement = data_quality.get("source_disagreement", {})
        valuation_sources = self._valuation_source_rows(data_quality.get("valuation_sources", []))
        return f"""
  <div class="data-quality-box">
    <h5>来源等级</h5>
    <p>{_escape(data_quality.get('source_tier', ''))}</p>
    <h5>数据日期 / 采集时间</h5>
    <p>{_escape(data_quality.get('data_date', ''))} · {_escape(data_quality.get('collected_at_utc', ''))}</p>
    <h5>公式口径</h5>
    <p>{_escape(data_quality.get('formula', ''))}</p>
    <h5>覆盖率</h5>
    <pre>{_escape(json.dumps(coverage, ensure_ascii=False, indent=2, default=str))}</pre>
    {valuation_sources}
    <h5>异常与缺口</h5>
    <pre>{_escape(json.dumps(anomalies, ensure_ascii=False, indent=2, default=str))}</pre>
    <h5>备用路径</h5>
    <p>{_escape(' -> '.join(str(item) for item in _as_list(fallback)))}</p>
    <h5>来源分歧</h5>
    <pre>{_escape(json.dumps(disagreement, ensure_ascii=False, indent=2, default=str))}</pre>
  </div>
"""

    def _valuation_source_rows(self, sources: Any) -> str:
        rows = []
        for source in _as_list(sources):
            if not isinstance(source, dict):
                continue
            percentile = source.get("historical_percentile", source.get("percentile_10y"))
            percentile_text = "No Historical Percentile" if percentile is None else str(percentile)
            details = [
                f"metric={source.get('metric', '')}",
                f"value={source.get('value', '')}",
                f"percentile={percentile_text}",
                f"date={source.get('data_date', '')}",
                f"availability={source.get('availability', '')}",
            ]
            if source.get("tbond_rate") is not None:
                details.append(f"tbond_rate={source.get('tbond_rate')}")
            if source.get("scope"):
                details.append(str(source.get("scope")))
            if source.get("unavailable_reason"):
                details.append(f"unavailable_reason={source.get('unavailable_reason')}")
            rows.append(
                "<li>"
                f"<b>{_escape(source.get('source_name', source.get('source_id', '')))}</b> "
                f"<span>{_escape(source.get('source_tier', ''))}</span>"
                f"<small>{_escape(' | '.join(details))}</small>"
                "</li>"
            )
        if not rows:
            return ""
        return f"""
    <h5>Valuation Sources</h5>
    <ul class="valuation-source-list">{''.join(rows)}</ul>
"""

    def _governance_section(self, artifacts: Dict[str, Any]) -> str:
        critique = artifacts["critique"]
        risk = artifacts["risk_boundary_report"]
        schema = artifacts["schema_guard_report"]
        firewall = artifacts.get("synthesis_packet", {}).get("objective_firewall_summary", {})
        failures = "".join(
            f"<li>{_escape(item.get('condition', item))} <span>{_escape(item.get('impact', '')) if isinstance(item, dict) else ''}</span></li>"
            for item in _as_list(risk.get("failure_conditions"))
        )
        must = "".join(f"<li>{_escape(item)}</li>" for item in _as_list(risk.get("must_preserve_risks")))
        issues = "".join(f"<li>{_escape(item)}</li>" for item in _as_list(critique.get("cross_layer_issues")))
        tensions = "".join(f"<li>{_escape(item)}</li>" for item in _as_list(firewall.get("unresolved_tensions")))
        firewall_warnings = "".join(f"<li>{_escape(item)}</li>" for item in _as_list(firewall.get("warnings")))
        return f"""
<section class="panel" id="governance">
  <div class="section-kicker">05 · Governance</div>
  <h2>Critic / Risk / Schema Guard</h2>
  <div class="governance-grid">
    <article>
      <h3>Critic</h3>
      <p>{_escape(critique.get('overall_assessment', ''))}</p>
      <ul>{issues or '<li>无</li>'}</ul>
      <b>{_escape(critique.get('revision_direction', ''))}</b>
    </article>
    <article>
      <h3>Risk Sentinel</h3>
      <h4>Failure Conditions</h4>
      <ul>{failures or '<li>无</li>'}</ul>
      <h4>Must Preserve</h4>
      <ul>{must or '<li>无</li>'}</ul>
    </article>
    <article>
      <h3>Schema Guard</h3>
      <div class="schema-status {'good' if schema.get('passed') else 'bad'}">{_escape(schema.get('passed'))}</div>
      <p>Structural: {_escape(schema.get('structural_issues', []))}</p>
      <p>Consistency: {_escape(schema.get('consistency_issues', []))}</p>
      <p>Missing: {_escape(schema.get('missing_fields', []))}</p>
    </article>
    <article>
      <h3>Objective Firewall</h3>
      <p>Object: {_escape(firewall.get('object_clear'))} · Authority: {_escape(firewall.get('authority_clear'))} · Cross-Layer: {_escape(firewall.get('cross_layer_verified'))}</p>
      <h4>Strongest Falsifier</h4>
      <p>{_escape(firewall.get('strongest_falsifier', ''))}</p>
      <h4>Unresolved Tensions</h4>
      <ul>{tensions or '<li>None</li>'}</ul>
      <h4>Warnings</h4>
      <ul>{firewall_warnings or '<li>None</li>'}</ul>
    </article>
  </div>
</section>
"""

    def _audit_section(self, run_path: Path, artifacts: Dict[str, Any], payload_json: str) -> str:
        token_usage = artifacts["final_adjudication"].get("token_usage", {})
        return f"""
<section class="panel" id="audit">
  <div class="section-kicker">06 · Audit Trail</div>
  <h2>审计与原始 artifact</h2>
  <div class="audit-grid">
    <div><b>Run Dir</b><p>{_escape(run_path)}</p></div>
    <div><b>Token Usage</b><p>{_escape(token_usage)}</p></div>
  </div>
  <details class="raw-json">
    <summary>展开页面使用的原生 JSON</summary>
    <pre>{_escape(payload_json)}</pre>
  </details>
</section>
"""

    def _ref_chips(self, refs: Any, *, link: bool = True) -> str:
        chips = []
        for ref in _as_list(refs):
            text = str(ref)
            canonical = _canonical_ref(text)
            label = _human_ref_label(text)
            if link and "." in canonical:
                chips.append(
                    f'<button class="ref-chip" data-ref="{_escape(canonical)}" '
                    f'data-label="{_escape(label)}">{_escape(label)}</button>'
                )
            else:
                chips.append(f'<span class="ref-chip muted">{_escape(text)}</span>')
        return "".join(chips)

    def _css(self) -> str:
        return """
:root {
  --ink: #17201b;
  --muted: #6c756f;
  --paper: #f4efe4;
  --panel: rgba(255, 252, 244, 0.88);
  --line: rgba(23, 32, 27, 0.12);
  --green: #1f7a4d;
  --amber: #b56a12;
  --red: #a63d2a;
  --blue: #315f72;
  --shadow: 0 22px 70px rgba(37, 31, 18, 0.16);
}
* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }
body {
  margin: 0;
  color: var(--ink);
  background:
    radial-gradient(circle at 10% 0%, rgba(207, 147, 63, 0.24), transparent 34rem),
    radial-gradient(circle at 90% 20%, rgba(49, 95, 114, 0.20), transparent 32rem),
    linear-gradient(135deg, #efe3ce 0%, #f7f3eb 48%, #e3ede7 100%);
  font-family: "Noto Serif SC", "Source Han Serif SC", "Songti SC", "Microsoft YaHei", serif;
  line-height: 1.68;
}
.ambient { position: fixed; inset: auto; pointer-events: none; filter: blur(50px); opacity: .42; z-index: -1; }
.ambient-a { width: 24rem; height: 24rem; left: -6rem; top: 18rem; background: #dba04a; border-radius: 50%; }
.ambient-b { width: 26rem; height: 26rem; right: -8rem; top: 4rem; background: #7aa0a8; border-radius: 48%; }
.shell { width: min(1440px, calc(100% - 32px)); margin: 0 auto; padding: 24px 0 80px; }
.hero {
  min-height: 330px;
  padding: 44px;
  border: 1px solid var(--line);
  border-radius: 34px;
  background: linear-gradient(135deg, rgba(28, 42, 35, .95), rgba(42, 65, 60, .88));
  color: #fff8ea;
  box-shadow: var(--shadow);
  overflow: hidden;
  position: relative;
}
.hero:after { content: ""; position: absolute; right: -7rem; bottom: -8rem; width: 28rem; height: 28rem; border-radius: 50%; border: 1px solid rgba(255,255,255,.18); }
.eyebrow, .section-kicker { text-transform: uppercase; letter-spacing: .18em; font-size: .78rem; color: #a96a26; font-weight: 800; }
.hero .eyebrow { color: #e5bd7e; }
.hero-grid { display: grid; grid-template-columns: minmax(0, 1fr) 360px; gap: 32px; align-items: end; position: relative; z-index: 1; }
h1 { font-size: clamp(3.5rem, 9vw, 8rem); line-height: .9; margin: 28px 0; letter-spacing: -.08em; }
h2 { font-size: clamp(1.8rem, 3.2vw, 3.4rem); line-height: 1; margin: .35rem 0 1.2rem; letter-spacing: -.06em; }
h3, h4 { margin: .2rem 0 .6rem; line-height: 1.35; }
.hero-note { max-width: 820px; color: #e8ddc8; font-size: 1.04rem; }
.verdict-card {
  background: rgba(255, 248, 234, .10);
  border: 1px solid rgba(255,255,255,.18);
  border-radius: 22px;
  padding: 22px;
  backdrop-filter: blur(18px);
}
.verdict-row { display: flex; justify-content: space-between; gap: 18px; padding: 13px 0; border-bottom: 1px solid rgba(255,255,255,.12); }
.verdict-row:last-child { border-bottom: 0; }
.run-path { margin-top: 26px; color: #c9bea8; font-size: .82rem; word-break: break-all; position: relative; z-index: 1; }
.nav {
  position: sticky; top: 12px; z-index: 10;
  display: flex; gap: 8px; flex-wrap: wrap;
  margin: 18px 0;
  padding: 10px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: rgba(249, 244, 233, .82);
  backdrop-filter: blur(18px);
  box-shadow: 0 14px 36px rgba(37, 31, 18, .09);
}
.nav a { color: var(--ink); text-decoration: none; padding: 9px 16px; border-radius: 999px; font-weight: 750; }
.nav a:hover { background: #23332b; color: #fff8ea; }
.template-intro {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(260px, .72fr);
  gap: 18px;
  align-items: center;
  margin: 18px 0;
  padding: 18px 22px;
  border: 1px solid var(--line);
  border-radius: 24px;
  background: rgba(255, 252, 244, .68);
  box-shadow: 0 12px 32px rgba(37, 31, 18, .08);
}
.template-intro b { font-size: 1.15rem; }
.template-intro p { margin: .35rem 0 0; color: var(--muted); }
.template-legend { display: flex; flex-wrap: wrap; gap: 8px; justify-content: flex-end; }
.template-legend span {
  border-radius: 999px;
  padding: 5px 10px;
  background: rgba(35, 51, 43, .07);
  color: var(--muted);
  font-size: .78rem;
  font-weight: 800;
}
.panel {
  margin: 22px 0;
  padding: clamp(22px, 4vw, 44px);
  background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 30px;
  box-shadow: var(--shadow);
}
.section-note { color: var(--muted); max-width: 900px; }
.decision-grid, .bridge-columns, .layer-grid, .governance-grid, .audit-grid {
  display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px;
}
.typed-map-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
  margin: 18px 0;
}
.typed-map-grid section {
  min-width: 0;
}
.statement, .risk-list, .bridge-card, .governance-grid article, .audit-grid div {
  background: rgba(255,255,255,.52);
  border: 1px solid var(--line);
  border-radius: 22px;
  padding: 22px;
}
.statement strong { display: block; font-size: clamp(2.2rem, 5vw, 5rem); letter-spacing: -.08em; line-height: .95; margin: .4rem 0; }
.risk-list li, .governance-grid li { margin-bottom: .65rem; }
.chain-grid { display: grid; gap: 14px; }
.chain-card {
  display: grid; grid-template-columns: 72px minmax(0, 1fr); gap: 18px;
  background: linear-gradient(135deg, rgba(255,255,255,.74), rgba(245,237,220,.76));
  border: 1px solid var(--line);
  border-radius: 24px;
  padding: 18px;
}
.chain-index { display: grid; place-items: center; border-radius: 18px; background: #22332b; color: #fff8ea; font-size: 1.4rem; font-weight: 900; }
.weight-bar { height: 8px; border-radius: 999px; background: rgba(23,32,27,.12); overflow: hidden; margin: 12px 0 4px; }
.weight-bar span { display: block; height: 100%; background: linear-gradient(90deg, var(--amber), var(--green)); border-radius: inherit; }
.chain-meta { color: var(--muted); font-size: .88rem; }
.ref-row { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 12px; }
.ref-chip {
  border: 1px solid rgba(31,122,77,.28);
  background: rgba(31,122,77,.08);
  color: #175a38;
  border-radius: 999px;
  padding: 5px 10px;
  font: inherit;
  font-size: .84rem;
  cursor: pointer;
}
.ref-chip:hover { background: #175a38; color: #fff; }
.ref-chip.muted { border-color: var(--line); color: var(--muted); cursor: default; }
.claim, .conflict-card, .indicator-card, .typed-map-card {
  background: rgba(255,255,255,.62);
  border: 1px solid var(--line);
  border-radius: 20px;
  padding: 18px;
  margin-bottom: 14px;
}
.typed-map-card { font-size: .92rem; }
.typed-map-card small {
  display: block;
  margin-top: 6px;
  color: var(--muted);
  overflow-wrap: anywhere;
}
.typed-map-card p { overflow-wrap: anywhere; }
.conflict-card.bad { border-color: rgba(166,61,42,.32); background: rgba(166,61,42,.08); }
.conflict-card.watch { border-color: rgba(181,106,18,.32); background: rgba(181,106,18,.08); }
.conflict-card.good { border-color: rgba(31,122,77,.30); background: rgba(31,122,77,.07); }
.conflict-head { display: flex; justify-content: space-between; gap: 14px; font-weight: 900; }
.conflict-head span { overflow-wrap: anywhere; }
.path-line {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 10px;
  color: var(--muted);
}
.path-line b {
  background: rgba(35, 51, 43, .08);
  border-radius: 999px;
  padding: 4px 9px;
  color: var(--ink);
}
.layer-tabs { display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px; margin: 20px 0; }
.layer-tab {
  border: 1px solid var(--line);
  background: rgba(255,255,255,.52);
  border-radius: 18px;
  padding: 14px 10px;
  text-align: left;
  cursor: pointer;
  color: var(--ink);
  font: inherit;
  font-weight: 900;
}
.layer-tab span { display: block; color: var(--muted); font-size: .74rem; font-weight: 700; }
.layer-tab.active { background: #22332b; color: #fff8ea; transform: translateY(-2px); }
.layer-tab.active span { color: #e1cba5; }
.layer-panel { display: none; }
.layer-panel.active { display: block; animation: rise .28s ease-out; }
@keyframes rise { from { opacity: 0; transform: translateY(12px); } to { opacity: 1; transform: none; } }
.layer-hero {
  display: flex; justify-content: space-between; gap: 18px; align-items: flex-start;
  background: linear-gradient(135deg, #23332b, #38524b);
  color: #fff8ea;
  border-radius: 24px;
  padding: 24px;
  margin-bottom: 18px;
}
.layer-label { color: #e5bd7e; letter-spacing: .12em; text-transform: uppercase; font-size: .76rem; font-weight: 900; }
.layer-hero h3 { font-size: 1.25rem; font-weight: 650; }
.pill, .state-pill {
  display: inline-flex; align-items: center;
  border-radius: 999px; padding: 5px 11px;
  font-weight: 900; font-size: .82rem;
  background: rgba(181,106,18,.14); color: var(--amber);
}
.pill.good { background: rgba(31,122,77,.14); color: var(--green); }
.pill.bad { background: rgba(166,61,42,.14); color: var(--red); }
.pill.watch { background: rgba(181,106,18,.14); color: var(--amber); }
.risk-chip-row { display: flex; flex-wrap: wrap; gap: 8px; margin: 12px 0; }
.risk-chip-row span { background: rgba(166,61,42,.10); color: var(--red); border-radius: 999px; padding: 5px 10px; font-size: .82rem; font-weight: 800; }
.hook-box {
  background: rgba(255,255,255,.42);
  border: 1px solid var(--line);
  border-radius: 18px;
  padding: 14px 18px;
  margin: 14px 0;
}
summary { cursor: pointer; font-weight: 900; }
.indicator-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 14px; margin-top: 18px; }
.indicator-card.target { outline: 3px solid rgba(31,122,77,.38); box-shadow: 0 0 0 8px rgba(31,122,77,.08); }
.indicator-top { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
.metric-ref { color: var(--blue); font-size: .78rem; font-weight: 900; }
.reading { color: var(--muted); font-weight: 750; }
.reasoning { margin: 12px 0; padding: 14px; background: rgba(35,51,43,.06); border-radius: 14px; white-space: pre-wrap; }
.data-quality-box {
  margin: 14px 0;
  padding: 14px;
  border: 1px solid rgba(49,95,114,.18);
  border-radius: 14px;
  background: rgba(49,95,114,.06);
}
.data-quality-box h5 { margin: .35rem 0 .15rem; color: var(--blue); }
.data-quality-box p { margin: 0 0 .35rem; overflow-wrap: anywhere; }
.data-quality-box pre {
  max-height: 180px;
  overflow: auto;
  margin: .25rem 0 .5rem;
  padding: 10px;
  border-radius: 10px;
  background: rgba(255,255,255,.58);
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  font-size: .78rem;
}
.schema-status { display: inline-flex; padding: 8px 14px; border-radius: 999px; font-weight: 900; }
.schema-status.good { background: rgba(31,122,77,.14); color: var(--green); }
.schema-status.bad { background: rgba(166,61,42,.14); color: var(--red); }
.raw-json pre { max-height: 520px; overflow: auto; background: #17201b; color: #fff8ea; border-radius: 18px; padding: 18px; font-size: .82rem; }
.template-brief {
  background:
    linear-gradient(90deg, rgba(92, 74, 46, .06) 1px, transparent 1px),
    linear-gradient(#f7f0e2, #fbf7ef);
  background-size: 42px 42px, auto;
}
.template-brief .shell { width: min(1120px, calc(100% - 36px)); }
.template-brief .hero {
  min-height: 260px;
  background: linear-gradient(135deg, rgba(92, 74, 46, .97), rgba(153, 105, 41, .84));
}
.template-brief .panel {
  border-radius: 18px;
  box-shadow: 0 14px 42px rgba(86, 59, 25, .12);
}
.template-brief .indicator-grid,
.template-brief .governance-grid,
.template-brief .bridge-columns {
  grid-template-columns: 1fr;
}
.template-brief .layer-hero {
  background: linear-gradient(135deg, #5c4a2e, #866335);
}
.template-atlas {
  background:
    radial-gradient(circle at 8% 20%, rgba(49, 95, 114, .18), transparent 28rem),
    linear-gradient(135deg, #e8f0ee, #f8f6ee 42%, #e6e1d2);
}
.template-atlas .hero {
  background: linear-gradient(135deg, rgba(21, 42, 51, .97), rgba(49, 95, 114, .88));
}
.template-atlas .chain-grid,
.template-atlas .indicator-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.template-atlas .chain-card {
  grid-template-columns: 52px minmax(0, 1fr);
}
.template-atlas .panel {
  border-radius: 26px;
}
.template-atlas .ref-chip {
  border-color: rgba(49,95,114,.28);
  background: rgba(49,95,114,.08);
  color: #254e60;
}
.template-atlas .ref-chip:hover {
  background: #254e60;
  color: #fff;
}
.template-workbench {
  background:
    linear-gradient(135deg, rgba(31, 122, 77, .10), transparent 26rem),
    linear-gradient(225deg, rgba(181, 106, 18, .12), transparent 26rem),
    #f2efe6;
}
.template-workbench .hero {
  min-height: 240px;
  background: linear-gradient(135deg, rgba(30, 56, 42, .98), rgba(31, 122, 77, .80));
}
.template-workbench .layers-panel {
  border: 2px solid rgba(31,122,77,.18);
}
.template-workbench .layer-tabs {
  position: sticky;
  top: 76px;
  z-index: 9;
  background: rgba(242, 239, 230, .86);
  border-radius: 22px;
  padding: 10px;
  backdrop-filter: blur(12px);
}
.template-workbench .indicator-grid {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}
@media (max-width: 900px) {
  .hero-grid, .decision-grid, .bridge-columns, .typed-map-grid, .layer-grid, .governance-grid, .audit-grid, .indicator-grid, .template-intro, .template-atlas .chain-grid, .template-atlas .indicator-grid, .template-workbench .indicator-grid { grid-template-columns: 1fr; }
  .layer-tabs { grid-template-columns: 1fr; }
  .template-legend { justify-content: flex-start; }
  .hero { padding: 28px; }
  .nav { border-radius: 22px; }
  .chain-card { grid-template-columns: 1fr; }
}

/* vNext report redesign: quiet institutional editorial */
:root {
  --ink: #161a1d;
  --ink-soft: #30363a;
  --muted: #697177;
  --paper: #f7f5ef;
  --paper-warm: #ede7d9;
  --panel: rgba(255, 255, 252, 0.9);
  --panel-solid: #fffefa;
  --line: rgba(22, 26, 29, 0.12);
  --line-strong: rgba(22, 26, 29, 0.22);
  --green: #176646;
  --amber: #9a6418;
  --red: #9c332b;
  --blue: #22566f;
  --graphite: #262c2f;
  --shadow: 0 26px 80px rgba(24, 28, 31, 0.12);
  --mono: "SF Mono", "Cascadia Mono", "Menlo", monospace;
  --serif: "Songti SC", "Noto Serif SC", "Source Han Serif SC", "STSong", serif;
  --sans: "Avenir Next", "Gill Sans", "PingFang SC", "Microsoft YaHei", sans-serif;
}

body {
  background:
    linear-gradient(90deg, rgba(22,26,29,.035) 1px, transparent 1px),
    linear-gradient(rgba(22,26,29,.025) 1px, transparent 1px),
    radial-gradient(circle at 12% 0%, rgba(34,86,111,.12), transparent 30rem),
    radial-gradient(circle at 88% 12%, rgba(154,100,24,.10), transparent 32rem),
    linear-gradient(180deg, #f8f6f0 0%, #f1eee5 100%);
  background-size: 34px 34px, 34px 34px, auto, auto, auto;
  font-family: var(--serif);
  line-height: 1.72;
}

.ambient { display: none; }
.shell { width: min(1180px, calc(100% - 40px)); padding: 28px 0 96px; }
.hero {
  min-height: auto;
  padding: clamp(28px, 5vw, 56px);
  border-radius: 4px;
  background:
    linear-gradient(90deg, rgba(255,255,255,.08) 1px, transparent 1px),
    linear-gradient(135deg, #20272b, #384044 48%, #65513a);
  color: #fffaf0;
  border: 1px solid rgba(255,255,255,.2);
  box-shadow: var(--shadow);
}
.hero:after {
  right: clamp(18px, 7vw, 90px);
  bottom: clamp(18px, 5vw, 60px);
  width: min(42vw, 30rem);
  height: min(42vw, 30rem);
  border-radius: 0;
  transform: rotate(8deg);
  border-color: rgba(255,255,255,.14);
}
.hero-grid { grid-template-columns: minmax(0, 1fr) minmax(280px, 360px); align-items: start; }
.eyebrow, .section-kicker {
  font-family: var(--sans);
  letter-spacing: .16em;
  color: var(--blue);
}
.hero .eyebrow { color: #d7c194; }
h1 {
  max-width: 880px;
  font-size: clamp(2.6rem, 7vw, 6.6rem);
  line-height: .98;
  letter-spacing: 0;
  margin: 24px 0 24px;
}
h2 {
  font-size: clamp(1.9rem, 4vw, 4.2rem);
  line-height: 1.05;
  letter-spacing: 0;
}
h3, h4 { letter-spacing: 0; }
.hero-note { font-size: 1.06rem; color: rgba(255,250,240,.82); max-width: 820px; }
.verdict-card {
  border-radius: 2px;
  background: rgba(255,255,255,.075);
  border-color: rgba(255,255,255,.24);
  box-shadow: inset 0 1px rgba(255,255,255,.10);
}
.verdict-row { font-family: var(--sans); font-size: .9rem; }
.verdict-row strong { text-align: right; }
.hero-risks {
  position: relative;
  z-index: 1;
  margin-top: 34px;
  padding-top: 20px;
  border-top: 1px solid rgba(255,255,255,.18);
  display: grid;
  grid-template-columns: 160px minmax(0,1fr);
  gap: 18px;
}
.hero-risks > span {
  font-family: var(--sans);
  color: #d7c194;
  font-weight: 800;
}
.hero-risks ul {
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.hero-risks li {
  border-left: 3px solid #d6a252;
  background: rgba(255,255,255,.08);
  padding: 10px 12px;
  font-size: .9rem;
}
.run-path { color: rgba(255,250,240,.55); font-family: var(--mono); }

.nav {
  top: 14px;
  border-radius: 2px;
  padding: 8px;
  background: rgba(255, 254, 250, .86);
  box-shadow: 0 16px 44px rgba(30, 32, 33, .10);
}
.nav a {
  border-radius: 2px;
  font-family: var(--sans);
  font-size: .9rem;
}
.nav a:hover { background: var(--graphite); color: #fffaf0; }

.template-intro {
  border-radius: 2px;
  box-shadow: none;
  background: rgba(255,254,250,.68);
}
.template-legend span, .pill, .state-pill, .ref-chip, .risk-chip-row span {
  border-radius: 2px;
  font-family: var(--sans);
}
.panel {
  border-radius: 2px;
  background: var(--panel);
  box-shadow: 0 18px 54px rgba(24, 28, 31, .09);
}
.section-note { font-size: 1.02rem; }
.decision-layout {
  display: grid;
  grid-template-columns: minmax(0, 1.05fr) minmax(300px, .78fr);
  gap: 22px;
}
.statement, .risk-list, .bridge-card, .governance-grid article, .audit-grid div,
.claim, .conflict-card, .indicator-card, .typed-map-card, .trigger-card {
  border-radius: 2px;
  background: rgba(255,255,252,.72);
  box-shadow: none;
}
.statement strong {
  font-size: clamp(2.1rem, 4.6vw, 4.8rem);
  letter-spacing: 0;
  color: #1b2428;
}
.accent-block { border-left: 5px solid var(--red); }
.risk-board {
  display: grid;
  grid-template-columns: minmax(0, .9fr) minmax(300px, 1.1fr);
  gap: 22px;
}
.boundary-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
}
.boundary-card {
  padding: 14px;
  border: 1px solid var(--line);
  background: rgba(255,255,252,.7);
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-family: var(--sans);
}
.boundary-card.bad { border-left: 4px solid var(--red); }
.boundary-card.watch { border-left: 4px solid var(--amber); }
.boundary-card.good { border-left: 4px solid var(--green); }
.trigger-grid {
  margin-top: 18px;
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}
.trigger-card h3 { font-size: 1rem; }

.chain-grid { gap: 12px; }
.chain-card {
  grid-template-columns: 56px minmax(0,1fr);
  border-radius: 2px;
  background: linear-gradient(90deg, rgba(255,255,252,.92), rgba(245,244,238,.72));
}
.chain-index {
  border-radius: 2px;
  background: var(--graphite);
  font-family: var(--mono);
}
.weight-bar { border-radius: 0; height: 7px; }
.weight-bar span {
  border-radius: 0;
  background: linear-gradient(90deg, var(--blue), var(--amber), var(--red));
}
.chain-meta { font-family: var(--sans); }
.ref-chip {
  border-color: rgba(34,86,111,.25);
  background: rgba(34,86,111,.07);
  color: #18445b;
  max-width: 100%;
  overflow-wrap: anywhere;
}
.ref-chip:hover { background: #18445b; color: #fff; }

.typed-map-grid {
  grid-template-columns: minmax(0, 1.08fr) minmax(0, .96fr) minmax(0, .96fr);
}
.conflict-head { font-family: var(--sans); }
.conflict-card.bad { border-left: 5px solid var(--red); }
.conflict-card.watch { border-left: 5px solid var(--amber); }
.conflict-card.good { border-left: 5px solid var(--green); }
.conflict-axis {
  display: grid;
  grid-template-columns: minmax(64px, auto) minmax(64px, 1fr) minmax(64px, auto);
  align-items: center;
  gap: 10px;
  margin: 12px 0;
  color: var(--muted);
  font: 800 .72rem var(--sans);
  text-transform: uppercase;
}
.conflict-axis i {
  height: 2px;
  background: linear-gradient(90deg, var(--blue), var(--red));
}
.path-line b { border-radius: 2px; font-family: var(--mono); }

.layer-summary-grid {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 12px;
  margin: 18px 0 22px;
}
.layer-summary-card {
  border: 1px solid var(--line);
  background: rgba(255,255,252,.68);
  padding: 16px;
  min-height: 220px;
  cursor: pointer;
}
.layer-summary-card b {
  display: block;
  font: 900 1.5rem var(--mono);
}
.layer-summary-card > div span {
  display: block;
  color: var(--muted);
  font-family: var(--sans);
  font-size: .78rem;
}
.layer-summary-card p {
  max-height: 7.6em;
  overflow: hidden;
}
.layer-summary-card footer {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}
.mini-risks span {
  display: inline-flex;
  margin: 2px;
  color: var(--red);
  font-size: .72rem;
}
.layer-tabs { grid-template-columns: repeat(5, minmax(0, 1fr)); }
.layer-tab {
  border-radius: 2px;
  font-family: var(--sans);
}
.layer-tab.active {
  background: var(--graphite);
  transform: none;
}
.layer-hero {
  border-radius: 2px;
  background: linear-gradient(135deg, #2a3034, #465057);
}
.indicator-grid {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}
.indicator-card {
  position: relative;
  overflow: hidden;
}
.indicator-card:before {
  content: "";
  position: absolute;
  inset: 0 auto 0 0;
  width: 3px;
  background: var(--blue);
  opacity: .45;
}
.metric-ref { font-family: var(--mono); }
.position-ruler {
  position: relative;
  margin: 14px 0;
  height: 34px;
  border-bottom: 1px solid var(--line-strong);
  background:
    linear-gradient(90deg, rgba(23,102,70,.14), rgba(154,100,24,.16), rgba(156,51,43,.16));
}
.position-ruler > span {
  position: absolute;
  top: -4px;
  width: 2px;
  height: 42px;
  background: var(--ink);
}
.position-ruler div {
  display: flex;
  justify-content: space-between;
  padding: 6px 9px;
  font: 800 .76rem var(--sans);
}
.data-quality-box, .reasoning {
  border-radius: 2px;
}
.data-quality-box pre, .raw-json pre {
  border-radius: 2px;
  font-family: var(--mono);
}

.evidence-drawer {
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: 60;
}
.evidence-drawer.open {
  pointer-events: auto;
}
.drawer-backdrop {
  position: absolute;
  inset: 0;
  background: rgba(16,20,22,.28);
  opacity: 0;
  transition: opacity .22s ease;
}
.evidence-drawer.open .drawer-backdrop { opacity: 1; }
.drawer-panel {
  position: absolute;
  top: 0;
  right: 0;
  width: min(560px, calc(100vw - 24px));
  height: 100%;
  overflow: auto;
  background: #fffefa;
  border-left: 1px solid var(--line-strong);
  box-shadow: -28px 0 70px rgba(16,20,22,.18);
  padding: 26px;
  transform: translateX(102%);
  transition: transform .25s ease;
}
.evidence-drawer.open .drawer-panel { transform: translateX(0); }
.drawer-close {
  float: right;
  border: 1px solid var(--line);
  background: transparent;
  padding: 8px 11px;
  font: 800 .82rem var(--sans);
  cursor: pointer;
}
.drawer-ref {
  font-family: var(--mono);
  color: var(--blue);
  overflow-wrap: anywhere;
}
.drawer-section {
  border-top: 1px solid var(--line);
  padding-top: 14px;
  margin-top: 16px;
}
.drawer-empty {
  padding: 20px;
  border: 1px dashed var(--line-strong);
  color: var(--muted);
}

.template-brief .shell { width: min(1180px, calc(100% - 40px)); }
.template-brief .hero,
.template-brief .layer-hero {
  background: linear-gradient(135deg, #20272b, #3d464b 54%, #62513d);
}
.template-brief .indicator-grid,
.template-brief .governance-grid,
.template-brief .bridge-columns {
  grid-template-columns: repeat(2, minmax(0, 1fr));
}

@media (max-width: 1050px) {
  .hero-grid, .decision-layout, .risk-board, .typed-map-grid,
  .template-brief .indicator-grid, .template-brief .governance-grid,
  .template-brief .bridge-columns, .trigger-grid {
    grid-template-columns: 1fr;
  }
  .layer-summary-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .hero-risks { grid-template-columns: 1fr; }
  .hero-risks ul { grid-template-columns: 1fr; }
}
@media (max-width: 680px) {
  .shell { width: min(100% - 24px, 1180px); padding-top: 12px; }
  .hero, .panel { padding: 22px; }
  h1 { font-size: clamp(2.3rem, 14vw, 4.2rem); }
  .nav { overflow-x: auto; flex-wrap: nowrap; }
  .nav a { white-space: nowrap; }
  .layer-summary-grid, .boundary-grid, .layer-tabs, .indicator-grid {
    grid-template-columns: 1fr;
  }
  .chain-card { grid-template-columns: 1fr; }
  .drawer-panel {
    top: auto;
    bottom: 0;
    width: 100%;
    height: min(84vh, 760px);
    border-left: 0;
    border-top: 1px solid var(--line-strong);
    transform: translateY(102%);
  }
  .evidence-drawer.open .drawer-panel { transform: translateY(0); }
}
"""

    def _js(self) -> str:
        return """
const tabs = document.querySelectorAll('.layer-tab');
const panels = document.querySelectorAll('.layer-panel');
const drawer = document.getElementById('evidence-drawer');
const drawerContent = document.getElementById('drawer-content');
const payloadNode = document.getElementById('vnext-data');
const payload = payloadNode ? JSON.parse(payloadNode.textContent) : {};
const indicatorIndex = new Map();
Object.entries(payload.layers || {}).forEach(([layer, card]) => {
  (card.indicator_analyses || []).forEach(item => {
    const ref = `${layer}.${item.function_id}`;
    indicatorIndex.set(ref, { layer, item });
  });
});

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll(\"'\", '&#039;');
}

function canonicalRef(ref) {
  let text = String(ref || '').trim();
  if (text.includes(':')) text = text.split(':')[0].trim();
  if (!text.includes('.')) return text;
  const [layer, rawFunction] = text.split('.', 2);
  let functionId = rawFunction.trim();
  if (/^L[1-5]$/.test(layer) && functionId && !functionId.startsWith('get_')) {
    functionId = `get_${functionId}`;
  }
  return `${layer}.${functionId}`;
}

function positionRuler(reading) {
  const text = String(reading || '');
  const patterns = [
    /(?:分位|百分位)\\s*(?:=|为|:)?\\s*([0-9]+(?:\\.[0-9]+)?)\\s*%/,
    /([0-9]+(?:\\.[0-9]+)?)\\s*%\\s*(?:分位|百分位)/,
    /10y percentile\\s*[=:]?\\s*([0-9]+(?:\\.[0-9]+)?)\\s*%?/i,
    /percentile\\s*[=:]?\\s*([0-9]+(?:\\.[0-9]+)?)/i,
  ];
  for (const pattern of patterns) {
    const match = text.match(pattern);
    if (match) {
      const value = Math.max(0, Math.min(100, Number(match[1])));
      return `<div class="position-ruler"><span style="left:${value}%"></span><div><b>历史分位</b><strong>${value.toFixed(1)}%</strong></div></div>`;
    }
  }
  return '';
}

function listItems(items) {
  const values = Array.isArray(items) ? items : [];
  return values.length ? values.map(item => `<li>${escapeHtml(item)}</li>`).join('') : '<li>无</li>';
}

function showLayer(layer) {
  tabs.forEach(tab => tab.classList.toggle('active', tab.dataset.layer === layer));
  panels.forEach(panel => panel.classList.toggle('active', panel.dataset.layerPanel === layer));
}

function openDrawer(ref, label) {
  const canonical = canonicalRef(ref);
  const entry = indicatorIndex.get(canonical);
  if (!entry) {
    drawerContent.innerHTML = `
      <p class="drawer-ref">${escapeHtml(label || ref)}</p>
      <div class="drawer-empty">这条证据没有命中指标卡。原始 ref：${escapeHtml(ref)}</div>
    `;
    drawer.classList.add('open');
    drawer.setAttribute('aria-hidden', 'false');
    return;
  }
  const { layer, item } = entry;
  const targetId = `evidence-${canonical.replaceAll('.', '-').replaceAll('/', '-').replaceAll(' ', '-')}`;
  const risks = (item.risk_flags || []).map(flag => `<span>${escapeHtml(flag)}</span>`).join('');
  drawerContent.innerHTML = `
    <p class="drawer-ref">${escapeHtml(canonical)}</p>
    <h2>${escapeHtml(item.metric || item.function_id)}</h2>
    <span class="state-pill">${escapeHtml(item.normalized_state || '')}</span>
    <p class="reading">${escapeHtml(item.current_reading || '')}</p>
    ${positionRuler(item.current_reading)}
    <p>${escapeHtml(item.narrative || '')}</p>
    <div class="drawer-section">
      <h3>它回答什么问题</h3>
      <p>${escapeHtml(item.canonical_question || '未提供')}</p>
      <h3>它不能证明什么</h3>
      <ul>${listItems(item.misread_guards)}</ul>
    </div>
    <div class="drawer-section">
      <h3>推理过程</h3>
      <p>${escapeHtml(item.reasoning_process || '')}</p>
      <ol>${listItems(item.first_principles_chain)}</ol>
    </div>
    <div class="drawer-section">
      <h3>反证条件</h3>
      <ul>${listItems(item.falsifiers)}</ul>
      <div class="risk-chip-row">${risks}</div>
    </div>
    <div class="drawer-section">
      <button class="ref-chip" data-jump-target="${escapeHtml(targetId)}" data-layer-target="${escapeHtml(layer)}">跳到完整底稿</button>
      <button class="ref-chip" data-copy-ref="${escapeHtml(canonical)}">复制 ref</button>
    </div>
  `;
  drawer.classList.add('open');
  drawer.setAttribute('aria-hidden', 'false');
}

function closeDrawer() {
  drawer.classList.remove('open');
  drawer.setAttribute('aria-hidden', 'true');
}

tabs.forEach(tab => tab.addEventListener('click', () => showLayer(tab.dataset.layer)));
document.querySelectorAll('[data-layer-jump]').forEach(card => {
  card.addEventListener('click', () => {
    showLayer(card.dataset.layerJump);
    document.querySelector('#layers .layer-tabs')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  });
});
document.querySelectorAll('[data-ref]').forEach(button => {
  button.addEventListener('click', () => {
    openDrawer(button.dataset.ref, button.dataset.label || button.textContent);
  });
});
document.querySelectorAll('[data-close-drawer]').forEach(node => node.addEventListener('click', closeDrawer));
document.addEventListener('keydown', event => {
  if (event.key === 'Escape') closeDrawer();
});
drawerContent.addEventListener('click', event => {
  const jump = event.target.closest('[data-jump-target]');
  if (jump) {
    const layer = jump.dataset.layerTarget;
    showLayer(layer);
    const target = document.getElementById(jump.dataset.jumpTarget);
    closeDrawer();
    if (target) {
      target.classList.add('target');
      target.scrollIntoView({ behavior: 'smooth', block: 'center' });
      setTimeout(() => target.classList.remove('target'), 1800);
    }
  }
  const copy = event.target.closest('[data-copy-ref]');
  if (copy && navigator.clipboard) {
    navigator.clipboard.writeText(copy.dataset.copyRef);
    copy.textContent = '已复制';
    setTimeout(() => copy.textContent = '复制 ref', 1200);
  }
});
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate native vNext research UI from a run directory.")
    parser.add_argument("--run-dir", required=True, help="Path to output/analysis/vnext/<run_id>.")
    parser.add_argument("--output", help="Optional output HTML path.")
    parser.add_argument(
        "--template",
        default="brief",
        choices=[*TEMPLATE_DESCRIPTIONS.keys(), "all"],
        help="UI template to generate. Use 'all' to generate every prototype.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    reporter = VNextReportGenerator()
    if args.template == "all":
        for template in TEMPLATE_DESCRIPTIONS:
            output_path = None
            if args.output:
                base = Path(args.output)
                output_path = base.with_name(f"{base.stem}_{template}{base.suffix or '.html'}")
            print(reporter.run(args.run_dir, output_path=output_path, template=template))
    else:
        report_path = reporter.run(args.run_dir, output_path=args.output, template=args.template)
        print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
