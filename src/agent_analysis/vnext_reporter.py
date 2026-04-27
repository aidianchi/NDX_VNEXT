from __future__ import annotations

import argparse
import html
import json
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
    "brief": ["decision", "layers", "evidence", "conflicts", "governance", "audit"],
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
        final = artifacts["final_adjudication"]
        synthesis = artifacts["synthesis_packet"]
        meta = synthesis.get("packet_meta", {})
        template_name = TEMPLATE_DESCRIPTIONS[template]["name"]
        title = f"vNext {template_name} · {final.get('final_stance', 'N/A')}"
        payload_json = json.dumps(
            {
                "run_dir": str(run_path),
                "final_adjudication": final,
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
  <div class="ambient ambient-a"></div>
  <div class="ambient ambient-b"></div>
  <div class="shell">
    {self._hero(final, meta, run_path, template)}
    {self._navigation()}
    {self._template_intro(template)}
    <main>{self._main_sections(template, run_path, artifacts, final, payload_json)}</main>
  </div>
  <script type="application/json" id="vnext-data">{_escape(payload_json)}</script>
  <script>{self._js()}</script>
</body>
</html>
"""

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
    <p>{_escape(meta['description'])}</p>
  </div>
  <div class="template-legend">{alternatives}</div>
</section>
"""

    def _hero(self, final: Dict[str, Any], meta: Dict[str, Any], run_path: Path, template: str) -> str:
        confidence = final.get("confidence", "medium")
        success = f"{meta.get('indicator_successful', '?')}/{meta.get('indicator_total', '?')}"
        template_name = TEMPLATE_DESCRIPTIONS[template]["name"]
        return f"""
<header class="hero" id="top">
  <div class="eyebrow">NDX vNext Native Artifact UI · {template_name}</div>
  <div class="hero-grid">
    <div>
      <h1>{_escape(final.get('final_stance', 'N/A'))}</h1>
      <p class="hero-note">{_escape(final.get('adjudicator_notes', ''))}</p>
    </div>
    <aside class="verdict-card">
      <div class="verdict-row"><span>Approval</span><strong>{_escape(final.get('approval_status', 'N/A'))}</strong></div>
      <div class="verdict-row"><span>Confidence</span><strong class="pill {_confidence_class(confidence)}">{_escape(confidence)}</strong></div>
      <div class="verdict-row"><span>Data Date</span><strong>{_escape(meta.get('data_date', 'N/A'))}</strong></div>
      <div class="verdict-row"><span>Indicators</span><strong>{_escape(success)}</strong></div>
    </aside>
  </div>
  <div class="run-path">{_escape(run_path)}</div>
</header>
"""

    def _navigation(self) -> str:
        return """
<nav class="nav">
  <a href="#decision">裁决</a>
  <a href="#evidence">证据链</a>
  <a href="#conflicts">冲突</a>
  <a href="#layers">五层</a>
  <a href="#governance">治理</a>
  <a href="#audit">审计</a>
</nav>
"""

    def _decision_section(self, final: Dict[str, Any]) -> str:
        risks = "".join(f"<li>{_escape(item)}</li>" for item in _as_list(final.get("must_preserve_risks")))
        refs = self._ref_chips(final.get("evidence_refs", []))
        return f"""
<section class="panel decision-panel" id="decision">
  <div class="section-kicker">01 · Final Adjudication</div>
  <h2>最终裁决与必须保留的风险</h2>
  <div class="decision-grid">
    <div class="statement">
      <span>Final Stance</span>
      <strong>{_escape(final.get('final_stance', 'N/A'))}</strong>
      <p>{_escape(final.get('adjudicator_notes', ''))}</p>
    </div>
    <div class="risk-list">
      <h3>Must-Preserve Risks</h3>
      <ul>{risks or '<li>无</li>'}</ul>
    </div>
  </div>
  <div class="ref-row">{refs}</div>
</section>
"""

    def _evidence_section(self, final: Dict[str, Any]) -> str:
        chains = []
        for index, chain in enumerate(_as_list(final.get("key_support_chains")), start=1):
            weight = chain.get("weight", "")
            weight_text = f"{float(weight) * 100:.0f}%" if isinstance(weight, (int, float)) else _escape(weight)
            chains.append(
                f"""
<article class="chain-card">
  <div class="chain-index">{index:02d}</div>
  <div class="chain-body">
    <h3>{_escape(chain.get('chain_description', '未命名证据链'))}</h3>
    <div class="weight-bar"><span style="width:{_escape(weight_text)}"></span></div>
    <div class="chain-meta">Weight · {weight_text}</div>
    <div class="ref-row">{self._ref_chips(chain.get('evidence_refs', []))}</div>
  </div>
</article>
"""
            )
        return f"""
<section class="panel" id="evidence">
  <div class="section-kicker">02 · Evidence Graph</div>
  <h2>主论点证据链</h2>
  <p class="section-note">点击任意证据 ref，可跳转到对应 Layer 的指标卡。这里直接消费 final_adjudication.key_support_chains。</p>
  <div class="chain-grid">{''.join(chains) or '<p>无证据链。</p>'}</div>
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
  <div class="section-kicker">03 · Bridge & Conflict Map</div>
  <h2>跨层共振与冲突</h2>
  <p class="section-note">Bridge 是 vNext 的核心价值之一：它不是再写一遍指标，而是指出哪些层互相支撑、互相打架。</p>
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
  <p>{_escape(conflict.get('description', ''))}</p>
  <p><b>Mechanism:</b> {_escape(conflict.get('mechanism', ''))}</p>
  <p><b>Implication:</b> {_escape(conflict.get('implication', ''))}</p>
  <div class="ref-row">{self._ref_chips(conflict.get('evidence_refs', []))}</div>
  <details>
    <summary>Falsifiers</summary>
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
            layers = " -> ".join(str(layer) for layer in _as_list(chain.get("layers")))
            cards.append(
                f"""
<article class="typed-map-card" data-resonance-chain="{_escape(chain_id)}">
  <div class="conflict-head">
    <span>{_escape(chain_id)}</span>
    <b>{_escape(chain.get('confidence', 'medium'))}</b>
  </div>
  <small>{_escape(layers)}</small>
  <p>{_escape(chain.get('description', ''))}</p>
  <p><b>Implication:</b> {_escape(chain.get('implication', ''))}</p>
  <div class="ref-row">{self._ref_chips(chain.get('evidence_refs', []))}</div>
</article>
"""
            )
        return "".join(cards)

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
  <p><b>Implication:</b> {_escape(path.get('implication', ''))}</p>
  <div class="ref-row">{self._ref_chips(path.get('evidence_refs', []))}</div>
</article>
"""
            )
        return "".join(cards)

    def _layers_section(self, artifacts: Dict[str, Any]) -> str:
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
  <div class="section-kicker">04 · Layer Workbench</div>
  <h2>五层独立研究底稿</h2>
  <div class="layer-tabs">{tab_buttons}</div>
  <div class="layer-panels">{panels}</div>
</section>
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
        chain = "".join(f"<li>{_escape(step)}</li>" for step in _as_list(item.get("first_principles_chain")))
        implications = self._ref_chips(item.get("cross_layer_implications", []), link=False)
        risks = "".join(f"<span>{_escape(flag)}</span>" for flag in _as_list(item.get("risk_flags")))
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
  <p>{_escape(item.get('narrative', ''))}</p>
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
            if link and "." in text:
                chips.append(f'<button class="ref-chip" data-ref="{_escape(text)}">{_escape(text)}</button>')
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
"""

    def _js(self) -> str:
        return """
const tabs = document.querySelectorAll('.layer-tab');
const panels = document.querySelectorAll('.layer-panel');
function showLayer(layer) {
  tabs.forEach(tab => tab.classList.toggle('active', tab.dataset.layer === layer));
  panels.forEach(panel => panel.classList.toggle('active', panel.dataset.layerPanel === layer));
}
tabs.forEach(tab => tab.addEventListener('click', () => showLayer(tab.dataset.layer)));
document.querySelectorAll('[data-ref]').forEach(button => {
  button.addEventListener('click', () => {
    const ref = button.dataset.ref;
    const layer = ref.split('.')[0];
    showLayer(layer);
    const target = document.getElementById('evidence-' + ref.replaceAll('.', '-').replaceAll('/', '-').replaceAll(' ', '-'));
    if (target) {
      target.classList.add('target');
      target.scrollIntoView({ behavior: 'smooth', block: 'center' });
      setTimeout(() => target.classList.remove('target'), 1800);
    }
  });
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
