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

# ---------------------------------------------------------------------------
# Slate Editorial design tokens — locked with user 2026-05-03.
# ---------------------------------------------------------------------------
SLATE_TOKENS = {
    "paper": "#F4F4F5",
    "paper_raised": "#FFFFFF",
    "ink": "#18181B",
    "ink_soft": "#3F3F46",
    "muted": "#71717A",
    "rule": "#D4D4D8",
    "rule_strong": "#A1A1AA",
    "accent": "#C2410C",
    "severity_low": "#15803D",
    "severity_watch": "#B45309",
    "severity_high": "#B91C1C",
}

LABELS: Dict[str, Dict[str, str]] = {
    "approval": {
        "approved": "通过",
        "approved_with_reservations": "有保留通过",
        "approved_with_caution": "谨慎通过",
        "rejected": "否决",
    },
    "confidence": {"low": "低", "medium": "中", "high": "高"},
    "severity": {"low": "低", "medium": "中", "high": "高"},
    "availability": {"available": "可用", "unavailable": "不可用"},
    "boundary": {
        "valuation_compression": "估值压缩",
        "earnings_miss": "盈利不达预期",
        "liquidity_shock": "流动性冲击",
        "concentration_collapse": "集中度回撤",
        "breadth_deterioration": "广度恶化",
        "sentiment_reversal": "情绪反转",
        "trend_breakdown": "趋势破坏",
    },
    "risk_flag": {
        "valuation_compression": "估值压缩",
        "earnings_miss": "盈利不达预期",
        "liquidity_shock": "流动性冲击",
        "concentration_collapse": "集中度回撤",
        "breadth_deterioration": "广度恶化",
        "sentiment_reversal": "情绪反转",
        "trend_breakdown": "趋势破坏",
    },
}


_ICONS = {
    "chevron": '<svg class="chevron" width="{size}" height="{size}" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="6 4 10 8 6 12"/></svg>',
    "copy": '<svg width="{size}" height="{size}" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="5" y="5" width="9" height="9" rx="1"/><path d="M3 11V3a1 1 0 0 1 1-1h8"/></svg>',
    "external": '<svg width="{size}" height="{size}" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M11 8.5V13H3V5h4.5"/><polyline points="9 2 13 2 13 6"/><line x1="13" y1="2" x2="7" y2="8"/></svg>',
    "info": '<svg width="{size}" height="{size}" viewBox="0 0 16 16" fill="none" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="8" cy="8" r="6.5"/><line x1="8" y1="11" x2="8" y2="7.5"/><circle cx="8" cy="5" r="0.7" fill="currentColor"/></svg>',
}


def _icon(name: str, *, size: int = 16) -> str:
    template = _ICONS.get(name, "")
    return template.format(size=size) if template else ""


def _label(value: Any, kind: str) -> str:
    table = LABELS.get(kind, {})
    return table.get(str(value), str(value or ""))


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _escape(value: Any) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


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


def _slug(ref: str) -> str:
    canonical = _canonical_ref(ref)
    return re.sub(r"[./ :]+", "-", canonical) or "ref"


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


# ---------------------------------------------------------------------------
# CSS template
# ---------------------------------------------------------------------------
_CSS_ROOT = "\n".join(f"  --{k.replace('_', '-')}: {v};" for k, v in SLATE_TOKENS.items())

CSS_TEMPLATE = f""":root {{
{_CSS_ROOT}
  --shadow-drawer: 0 4px 12px rgba(24, 24, 27, .08);
  --serif: "Source Serif Pro", "Source Serif 4", "Songti SC", "Noto Serif SC", Charter, Georgia, serif;
  --sans: "Inter", "IBM Plex Sans", "PingFang SC", "Microsoft YaHei", system-ui, sans-serif;
  --mono: "JetBrains Mono", "IBM Plex Mono", "SF Mono", Menlo, Consolas, monospace;
  --z-nav: 10;
  --z-drawer: 100;
  --radius: 6px;
  --radius-chip: 2px;
  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 24px;
  --space-6: 32px;
  --space-7: 48px;
}}

* {{ box-sizing: border-box; }}
html {{ scroll-behavior: smooth; }}

body {{
  margin: 0;
  background: var(--paper);
  color: var(--ink);
  font-family: var(--serif);
  font-size: 16px;
  line-height: 1.65;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}}

.skip-link {{
  position: absolute;
  top: -100px;
  left: 0;
  background: var(--ink);
  color: var(--paper-raised);
  padding: var(--space-2) var(--space-4);
  text-decoration: none;
  font-family: var(--sans);
  font-size: 14px;
  z-index: 1000;
}}
.skip-link:focus {{ top: 0; }}

.sr-only {{
  position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px;
  overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0;
}}

*:focus-visible {{
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}}

.shell {{
  width: min(1080px, calc(100% - 32px));
  margin: 0 auto;
  padding: 24px 0 96px;
}}

.hero {{
  padding: 56px 0 32px;
  border-top: 2px solid var(--ink);
  border-bottom: 1px solid var(--rule);
  margin-bottom: 0;
}}
.hero .eyebrow {{
  font-family: var(--sans);
  font-size: 12px;
  letter-spacing: 0.16em;
  color: var(--accent);
  text-transform: uppercase;
  font-weight: 600;
  margin-bottom: 24px;
}}
.hero-grid {{
  display: grid;
  grid-template-columns: minmax(0, 1.4fr) minmax(280px, 360px);
  gap: 40px;
  align-items: start;
}}
@media (max-width: 720px) {{
  .hero-grid {{ grid-template-columns: 1fr; }}
}}
.hero h1 {{
  font-family: var(--serif);
  font-size: clamp(28px, 4.4vw, 44px);
  line-height: 1.1;
  margin: 0 0 20px;
  font-weight: 600;
  letter-spacing: -0.01em;
  color: var(--ink);
}}
.hero-note {{
  color: var(--ink-soft);
  font-size: 16px;
  line-height: 1.7;
  max-width: 560px;
  margin: 0 0 24px;
}}
.verdict-card {{
  background: var(--paper-raised);
  border: 1px solid var(--rule);
  border-radius: var(--radius);
  padding: 16px 20px;
}}
.verdict-row {{
  display: flex;
  justify-content: space-between;
  gap: 16px;
  padding: 10px 0;
  border-bottom: 1px solid var(--rule);
  font-family: var(--sans);
  font-size: 13px;
}}
.verdict-row:last-child {{ border-bottom: 0; }}
.verdict-row span {{ color: var(--muted); }}
.verdict-row strong {{
  color: var(--ink);
  font-weight: 600;
  text-align: right;
}}
.verdict-row strong.mono {{ font-family: var(--mono); font-size: 13px; }}
.hero-risks {{
  margin-top: 28px;
  padding-top: 20px;
  border-top: 1px solid var(--rule);
}}
.hero-risks > span {{
  display: block;
  font-family: var(--sans);
  font-size: 12px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--accent);
  font-weight: 600;
  margin-bottom: 12px;
}}
.hero-risks ul {{
  list-style: none;
  padding: 0;
  margin: 0;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}}
@media (max-width: 720px) {{
  .hero-risks ul {{ grid-template-columns: 1fr; }}
}}
.hero-risks li {{
  font-size: 14px;
  line-height: 1.55;
  padding: 8px 12px;
  border-left: 3px solid var(--severity-high);
  background: var(--paper-raised);
  color: var(--ink);
}}
.run-path {{
  margin-top: 24px;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--muted);
  word-break: break-all;
}}

.nav {{
  position: sticky;
  top: 12px;
  z-index: var(--z-nav);
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  margin: 16px 0;
  padding: 6px;
  border: 1px solid var(--rule);
  background: rgba(244, 244, 245, 0.92);
  backdrop-filter: blur(8px);
  border-radius: var(--radius);
}}
.nav a {{
  color: var(--ink);
  text-decoration: none;
  padding: 6px 12px;
  border-radius: var(--radius-chip);
  font-family: var(--sans);
  font-size: 13px;
  font-weight: 500;
}}
.nav a:hover {{
  background: var(--ink);
  color: var(--paper-raised);
}}

.template-intro {{
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(260px, .7fr);
  gap: 16px;
  align-items: center;
  margin: 16px 0;
  padding: 14px 18px;
  border: 1px solid var(--rule);
  border-radius: var(--radius);
  background: var(--paper-raised);
}}
.template-intro b {{
  font-family: var(--sans);
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
}}
.template-intro p {{
  margin: 4px 0 0;
  color: var(--ink-soft);
  font-size: 13px;
}}
.template-legend {{
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  justify-content: flex-end;
}}
.template-legend span {{
  border: 1px solid var(--rule);
  border-radius: var(--radius-chip);
  padding: 3px 8px;
  font-family: var(--sans);
  font-size: 11px;
  color: var(--muted);
}}

.panel {{
  margin: 28px 0;
  padding: 28px 0 24px;
  border-top: 1px solid var(--rule);
}}
.panel:first-of-type {{ border-top: 0; padding-top: 8px; }}
.section-kicker {{
  font-family: var(--sans);
  font-size: 11px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  font-weight: 600;
  color: var(--accent);
  margin-bottom: 8px;
}}
.panel h2 {{
  font-family: var(--serif);
  font-size: clamp(22px, 2.8vw, 30px);
  line-height: 1.2;
  font-weight: 600;
  letter-spacing: -0.005em;
  color: var(--ink);
  margin: 0 0 12px;
}}
.panel h3 {{
  font-family: var(--serif);
  font-size: 17px;
  line-height: 1.35;
  margin: 0 0 6px;
  font-weight: 600;
}}
.panel h4 {{
  font-family: var(--sans);
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  font-weight: 600;
  color: var(--muted);
  margin: 0 0 8px;
}}
.section-note {{
  color: var(--ink-soft);
  font-size: 15px;
  line-height: 1.65;
  max-width: 720px;
  margin: 0 0 18px;
}}

.decision-layout {{
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(280px, .7fr);
  gap: 24px;
  align-items: start;
}}
@media (max-width: 720px) {{
  .decision-layout {{ grid-template-columns: 1fr; }}
}}
.statement {{
  background: var(--paper-raised);
  border: 1px solid var(--rule);
  border-radius: var(--radius);
  padding: 24px;
}}
.statement > span {{
  font-family: var(--sans);
  font-size: 11px;
  letter-spacing: 0.16em;
  text-transform: uppercase;
  color: var(--muted);
  font-weight: 600;
}}
.statement strong {{
  display: block;
  font-family: var(--serif);
  font-size: clamp(28px, 3.4vw, 38px);
  line-height: 1.15;
  font-weight: 600;
  margin: 8px 0 12px;
  color: var(--ink);
}}
.statement p {{
  font-size: 15px;
  line-height: 1.7;
  color: var(--ink-soft);
  margin: 0 0 12px;
}}
.risk-list {{
  background: var(--paper-raised);
  border: 1px solid var(--rule);
  border-left: 4px solid var(--severity-high);
  border-radius: var(--radius);
  padding: 20px 22px;
}}
.risk-list h3 {{
  font-family: var(--sans);
  font-size: 12px;
  letter-spacing: 0.12em;
  text-transform: uppercase;
  font-weight: 700;
  color: var(--severity-high);
  margin: 0 0 12px;
}}
.risk-list ul, .governance-grid ul {{
  list-style: none;
  margin: 0;
  padding: 0;
}}
.risk-list li, .governance-grid li {{
  font-size: 14px;
  line-height: 1.55;
  padding: 8px 0;
  border-bottom: 1px solid var(--rule);
}}
.risk-list li:last-child, .governance-grid li:last-child {{ border-bottom: 0; }}

.ref-row {{
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}}
.ref-chip {{
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border: 1px solid var(--rule-strong);
  background: var(--paper-raised);
  color: var(--ink);
  border-radius: var(--radius-chip);
  padding: 3px 8px;
  font-family: var(--mono);
  font-size: 12px;
  cursor: pointer;
  font-weight: 500;
  transition: background 120ms ease, color 120ms ease;
}}
.ref-chip:hover {{
  background: var(--ink);
  color: var(--paper-raised);
  border-color: var(--ink);
}}
.ref-chip.muted {{
  border-color: var(--rule);
  color: var(--muted);
  cursor: default;
  background: transparent;
}}
.ref-chip.muted:hover {{
  background: transparent;
  color: var(--muted);
  border-color: var(--rule);
}}

.chain-grid {{ display: grid; gap: 14px; }}
.chain-card {{
  display: grid;
  grid-template-columns: 56px minmax(0, 1fr);
  gap: 18px;
  background: var(--paper-raised);
  border: 1px solid var(--rule);
  border-radius: var(--radius);
  padding: 18px 20px;
}}
@media (max-width: 720px) {{
  .chain-card {{ grid-template-columns: 1fr; }}
}}
.chain-index {{
  display: grid;
  place-items: center;
  background: var(--ink);
  color: var(--paper-raised);
  font-family: var(--mono);
  font-size: 18px;
  font-weight: 600;
  border-radius: var(--radius);
  height: 56px;
  width: 56px;
}}
.weight-bar {{
  height: 4px;
  background: var(--rule);
  border-radius: 0;
  overflow: hidden;
  margin: 12px 0 4px;
}}
.weight-bar span {{
  display: block;
  height: 100%;
  background: var(--accent);
}}
.chain-meta {{
  font-family: var(--sans);
  color: var(--muted);
  font-size: 12px;
  letter-spacing: 0.04em;
}}

.pill, .state-pill {{
  display: inline-flex;
  align-items: center;
  gap: 4px;
  border-radius: var(--radius-chip);
  border: 1px solid var(--rule-strong);
  padding: 2px 8px;
  font-family: var(--sans);
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--ink-soft);
  background: var(--paper-raised);
}}
.pill.good {{ color: var(--severity-low); border-color: var(--severity-low); }}
.pill.bad {{ color: var(--severity-high); border-color: var(--severity-high); }}
.pill.watch {{ color: var(--severity-watch); border-color: var(--severity-watch); }}
.state-pill {{
  font-family: var(--mono);
  font-size: 11px;
}}
.pill::before, .state-pill::before {{
  content: "";
  display: inline-block;
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: currentColor;
  flex-shrink: 0;
}}

.risk-board {{
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(280px, 1.1fr);
  gap: 24px;
  margin-bottom: 18px;
}}
@media (max-width: 720px) {{
  .risk-board {{ grid-template-columns: 1fr; }}
}}
.boundary-grid {{
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}}
.boundary-card {{
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border: 1px solid var(--rule);
  background: var(--paper-raised);
  border-radius: var(--radius);
  font-family: var(--sans);
  font-size: 13px;
}}
.boundary-card span {{ color: var(--muted); }}
.boundary-card b {{
  color: var(--ink);
  font-weight: 600;
  font-family: var(--mono);
  font-size: 12px;
}}
.boundary-card.bad {{ border-left: 4px solid var(--severity-high); }}
.boundary-card.watch {{ border-left: 4px solid var(--severity-watch); }}
.boundary-card.good {{ border-left: 4px solid var(--severity-low); }}
.trigger-grid {{
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 14px;
}}
@media (max-width: 720px) {{
  .trigger-grid {{ grid-template-columns: 1fr; }}
}}
.trigger-card {{
  background: var(--paper-raised);
  border: 1px solid var(--rule);
  border-radius: var(--radius);
  padding: 16px 18px;
}}
.trigger-card h3 {{
  font-family: var(--serif);
  font-size: 15px;
  line-height: 1.35;
  margin: 0 0 6px;
  font-weight: 600;
}}
.trigger-card p {{
  font-size: 13px;
  line-height: 1.6;
  color: var(--ink-soft);
  margin: 0 0 8px;
}}

.bridge-card {{
  background: var(--paper-raised);
  border: 1px solid var(--rule);
  border-radius: var(--radius);
  padding: 22px;
  margin-bottom: 18px;
}}
.bridge-card > p {{
  font-size: 14px;
  line-height: 1.7;
  color: var(--ink-soft);
}}
.typed-map-grid {{
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
  margin: 18px 0;
}}
@media (max-width: 720px) {{
  .typed-map-grid {{ grid-template-columns: 1fr; }}
}}
.typed-map-grid section {{ min-width: 0; }}
.bridge-columns {{
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
  margin-top: 18px;
}}
@media (max-width: 720px) {{
  .bridge-columns {{ grid-template-columns: 1fr; }}
}}
.claim, .conflict-card, .typed-map-card {{
  background: var(--paper);
  border: 1px solid var(--rule);
  border-radius: var(--radius);
  padding: 14px 16px;
  margin-bottom: 10px;
  font-size: 13px;
  line-height: 1.6;
}}
.claim p, .conflict-card p, .typed-map-card p {{
  margin: 6px 0;
  color: var(--ink-soft);
  overflow-wrap: anywhere;
}}
.claim strong, .conflict-card strong, .typed-map-card strong {{
  font-family: var(--serif);
  font-size: 14px;
  font-weight: 600;
  color: var(--ink);
}}
.conflict-card.bad {{ border-left: 4px solid var(--severity-high); }}
.conflict-card.watch {{ border-left: 4px solid var(--severity-watch); }}
.conflict-card.good {{ border-left: 4px solid var(--severity-low); }}
.conflict-head {{
  display: flex;
  justify-content: space-between;
  gap: 10px;
  font-family: var(--sans);
  font-weight: 600;
  font-size: 12px;
}}
.conflict-head span {{ overflow-wrap: anywhere; color: var(--ink); }}
.conflict-head b {{
  font-family: var(--mono);
  font-size: 11px;
  color: var(--muted);
}}
.typed-map-card small {{
  display: block;
  margin-top: 4px;
  color: var(--muted);
  font-family: var(--mono);
  font-size: 11px;
  overflow-wrap: anywhere;
}}
.conflict-axis {{
  display: grid;
  grid-template-columns: minmax(64px, auto) minmax(64px, 1fr) minmax(64px, auto);
  align-items: center;
  gap: 10px;
  margin: 10px 0;
  color: var(--muted);
  font: 600 11px var(--sans);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}}
.conflict-axis i {{
  height: 1px;
  background: linear-gradient(90deg, var(--rule-strong), var(--accent), var(--severity-high));
}}
.path-line {{
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 8px 0;
  color: var(--muted);
  font-family: var(--sans);
  font-size: 12px;
}}
.path-line b {{
  background: var(--paper-raised);
  border: 1px solid var(--rule);
  border-radius: var(--radius-chip);
  padding: 3px 8px;
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink);
  font-weight: 500;
}}
details summary {{
  cursor: pointer;
  font-family: var(--sans);
  font-size: 12px;
  font-weight: 600;
  color: var(--ink-soft);
  margin-top: 8px;
}}
details[open] summary {{ color: var(--ink); }}
details ul {{ font-size: 13px; padding-left: 18px; margin: 6px 0; }}

.layer-summary-grid {{
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
  margin: 16px 0 28px;
}}
@media (max-width: 980px) {{
  .layer-summary-grid {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
}}
@media (max-width: 720px) {{
  .layer-summary-grid {{ grid-template-columns: 1fr; }}
}}
.layer-summary-tile {{
  background: var(--paper-raised);
  border: 1px solid var(--rule);
  border-radius: var(--radius);
  padding: 14px 16px;
  cursor: pointer;
  text-align: left;
  font: inherit;
  color: inherit;
  display: flex;
  flex-direction: column;
  gap: 8px;
  transition: border-color 120ms ease;
}}
.layer-summary-tile:hover {{ border-color: var(--rule-strong); }}
.layer-summary-tile > div b {{
  display: block;
  font-family: var(--mono);
  font-size: 18px;
  font-weight: 600;
  color: var(--ink);
}}
.layer-summary-tile > div span {{
  display: block;
  font-family: var(--sans);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--muted);
}}
.layer-summary-tile p {{
  flex-grow: 1;
  font-size: 13px;
  line-height: 1.55;
  color: var(--ink-soft);
  margin: 0;
  display: -webkit-box;
  -webkit-line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
}}
.layer-summary-tile footer {{
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}}
.mini-risks {{
  display: inline-flex;
  flex-wrap: wrap;
  gap: 4px;
}}
.mini-risks span {{
  display: inline-flex;
  align-items: center;
  font-family: var(--sans);
  font-size: 10px;
  color: var(--severity-high);
  border: 1px solid var(--rule);
  border-radius: var(--radius-chip);
  padding: 1px 5px;
}}

.layer-stack {{
  display: flex;
  flex-direction: column;
}}
.layer-card {{
  border-top: 1px solid var(--rule);
  scroll-margin-top: 80px;
}}
.layer-card:last-child {{ border-bottom: 1px solid var(--rule); }}
.layer-card__head {{
  width: 100%;
  display: grid;
  grid-template-columns: auto 1fr auto auto auto;
  gap: 16px;
  align-items: baseline;
  padding: 18px 4px;
  background: transparent;
  border: 0;
  cursor: pointer;
  text-align: left;
  font: inherit;
  color: inherit;
}}
.layer-card__head:hover {{ background: rgba(228, 228, 231, 0.3); }}
.layer-card__head .layer-no {{
  font-family: var(--mono);
  font-size: 13px;
  font-weight: 700;
  color: var(--ink);
  letter-spacing: 0.06em;
}}
.layer-card__head .layer-title {{
  font-family: var(--serif);
  font-size: 17px;
  font-weight: 600;
  color: var(--ink);
}}
.layer-card__head .layer-summary {{
  font-family: var(--serif);
  font-size: 14px;
  color: var(--ink-soft);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 1;
  -webkit-box-orient: vertical;
  overflow: hidden;
  text-overflow: ellipsis;
}}
.layer-card__head .chevron {{
  transition: transform 200ms ease;
  color: var(--muted);
}}
.layer-card__head[aria-expanded="true"] .chevron {{
  transform: rotate(90deg);
  color: var(--ink);
}}
.layer-card__head[aria-expanded="true"] {{
  background: rgba(228, 228, 231, 0.4);
}}
.layer-card__body {{
  display: grid;
  grid-template-rows: 0fr;
  transition: grid-template-rows 240ms ease;
}}
.layer-card__head[aria-expanded="true"] + .layer-card__body {{
  grid-template-rows: 1fr;
}}
.layer-card__body > div {{ overflow: hidden; }}
.layer-card__body-inner {{
  padding: 8px 4px 28px;
}}

@media (max-width: 720px) {{
  .layer-card__head {{
    grid-template-columns: auto 1fr auto;
    gap: 10px;
  }}
  .layer-card__head .layer-summary,
  .layer-card__head .mini-risks {{ display: none; }}
}}

.layer-grid {{
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
  margin: 18px 0;
}}
@media (max-width: 720px) {{
  .layer-grid {{ grid-template-columns: 1fr; }}
}}
.layer-grid section h4 {{ color: var(--accent); }}
.layer-grid section p {{
  font-size: 14px;
  line-height: 1.7;
  color: var(--ink-soft);
  margin: 0;
}}

.risk-chip-row {{
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 12px 0;
}}
.risk-chip-row span {{
  font-family: var(--sans);
  font-size: 11px;
  font-weight: 600;
  color: var(--severity-high);
  border: 1px solid var(--rule);
  border-radius: var(--radius-chip);
  padding: 2px 8px;
  background: var(--paper-raised);
}}

.hook-box {{
  background: var(--paper-raised);
  border: 1px solid var(--rule);
  border-radius: var(--radius);
  padding: 12px 16px;
  margin: 14px 0;
}}
.hook-box ul {{ list-style: none; padding: 0; margin: 8px 0 0; }}
.hook-box li {{
  font-size: 13px;
  line-height: 1.6;
  padding: 6px 0;
  border-bottom: 1px solid var(--rule);
}}
.hook-box li:last-child {{ border-bottom: 0; }}
.hook-box li b {{
  font-family: var(--mono);
  font-size: 12px;
  color: var(--accent);
  margin-right: 6px;
}}

.indicator-grid {{
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-top: 18px;
}}
@media (max-width: 720px) {{
  .indicator-grid {{ grid-template-columns: 1fr; }}
}}
.indicator-card {{
  background: var(--paper-raised);
  border: 1px solid var(--rule);
  border-radius: var(--radius);
  padding: 16px 18px;
  position: relative;
}}
.indicator-card.target {{
  outline: 2px solid var(--accent);
  outline-offset: 2px;
  animation: targetPulse 1400ms ease;
}}
@keyframes targetPulse {{
  0% {{ box-shadow: 0 0 0 0 rgba(194, 65, 12, 0.4); }}
  100% {{ box-shadow: 0 0 0 12px rgba(194, 65, 12, 0); }}
}}
.indicator-top {{
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: flex-start;
  margin-bottom: 8px;
}}
.indicator-top h4 {{
  font-family: var(--serif);
  font-size: 15px;
  font-weight: 600;
  color: var(--ink);
  text-transform: none;
  letter-spacing: 0;
  margin: 4px 0 0;
}}
.metric-ref {{
  font-family: var(--mono);
  font-size: 11px;
  font-weight: 500;
  color: var(--accent);
}}
.reading {{
  font-family: var(--mono);
  font-size: 13px;
  color: var(--ink-soft);
  margin: 4px 0 8px;
}}
.indicator-card > p {{
  font-size: 14px;
  line-height: 1.65;
  color: var(--ink-soft);
  margin: 8px 0;
}}
.position-ruler {{
  position: relative;
  margin: 14px 0;
  height: 32px;
  border-bottom: 1px solid var(--rule-strong);
}}
.position-ruler:before {{
  content: "";
  position: absolute;
  left: 0; right: 0; top: 14px;
  height: 4px;
  background: linear-gradient(90deg, var(--severity-low), var(--severity-watch) 50%, var(--severity-high));
  opacity: 0.7;
}}
.position-ruler > span {{
  position: absolute;
  top: 8px;
  width: 2px;
  height: 16px;
  background: var(--ink);
  transform: translateX(-50%);
}}
.position-ruler div {{
  display: flex;
  justify-content: space-between;
  padding: 0 0 6px;
  font-family: var(--sans);
  font-size: 11px;
  color: var(--muted);
}}
.position-ruler div strong {{
  font-family: var(--mono);
  font-size: 11px;
  color: var(--ink);
  font-weight: 600;
}}

.data-quality-box {{
  margin: 14px 0;
  padding: 14px;
  border: 1px solid var(--rule);
  background: var(--paper);
  border-radius: var(--radius);
}}
.data-quality-box h5 {{
  font-family: var(--sans);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-weight: 700;
  color: var(--accent);
  margin: 6px 0 4px;
}}
.data-quality-box p {{
  font-size: 13px;
  line-height: 1.55;
  margin: 0 0 6px;
  color: var(--ink-soft);
  font-family: var(--mono);
  word-break: break-all;
}}
.data-quality-box pre {{
  max-height: 160px;
  overflow: auto;
  margin: 4px 0 8px;
  padding: 8px 10px;
  background: var(--paper-raised);
  border: 1px solid var(--rule);
  border-radius: var(--radius-chip);
  font-family: var(--mono);
  font-size: 11px;
  line-height: 1.5;
  white-space: pre-wrap;
  overflow-wrap: anywhere;
  color: var(--ink);
}}
.valuation-source-list {{
  list-style: none;
  padding: 0;
  margin: 8px 0 0;
}}
.valuation-source-list li {{
  font-family: var(--mono);
  font-size: 11px;
  padding: 6px 0;
  border-bottom: 1px solid var(--rule);
  color: var(--ink);
}}
.valuation-source-list li:last-child {{ border-bottom: 0; }}
.valuation-source-list li b {{
  font-family: var(--sans);
  font-weight: 600;
  color: var(--ink);
  margin-right: 6px;
}}
.valuation-source-list li span {{
  font-family: var(--sans);
  font-size: 10px;
  text-transform: uppercase;
  color: var(--muted);
  margin-right: 6px;
}}
.valuation-source-list li small {{
  display: block;
  color: var(--muted);
  margin-top: 2px;
}}

.canon-box {{
  margin: 12px 0;
  padding: 14px;
  background: var(--paper);
  border: 1px solid var(--rule);
  border-radius: var(--radius);
}}
.canon-box h5 {{
  font-family: var(--sans);
  font-size: 11px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-weight: 700;
  color: var(--accent);
  margin: 8px 0 2px;
}}
.canon-box p {{
  font-size: 13px;
  line-height: 1.6;
  margin: 0 0 4px;
  color: var(--ink-soft);
}}
.canon-box ul {{
  list-style: disc;
  padding-left: 18px;
  margin: 4px 0 4px;
  font-size: 13px;
  line-height: 1.55;
}}
.canon-box li {{ margin: 2px 0; color: var(--ink-soft); }}
.reasoning {{
  margin: 10px 0;
  padding: 10px 12px;
  background: var(--paper);
  border: 1px solid var(--rule);
  border-radius: var(--radius-chip);
  font-family: var(--mono);
  font-size: 12px;
  line-height: 1.6;
  white-space: pre-wrap;
  color: var(--ink);
}}

.governance-grid {{
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
}}
@media (max-width: 720px) {{
  .governance-grid {{ grid-template-columns: 1fr; }}
}}
.governance-grid article {{
  background: var(--paper-raised);
  border: 1px solid var(--rule);
  border-radius: var(--radius);
  padding: 18px 20px;
}}
.governance-grid article p {{
  font-size: 13px;
  line-height: 1.6;
  color: var(--ink-soft);
  margin: 4px 0 8px;
}}
.schema-status {{
  display: inline-flex;
  align-items: center;
  font-family: var(--mono);
  font-size: 12px;
  font-weight: 600;
  padding: 4px 10px;
  border-radius: var(--radius-chip);
  border: 1px solid var(--rule-strong);
}}
.schema-status.good {{ color: var(--severity-low); border-color: var(--severity-low); }}
.schema-status.bad {{ color: var(--severity-high); border-color: var(--severity-high); }}

.audit-grid {{
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 14px;
  margin-bottom: 16px;
}}
@media (max-width: 720px) {{
  .audit-grid {{ grid-template-columns: 1fr; }}
}}
.audit-grid > div {{
  background: var(--paper-raised);
  border: 1px solid var(--rule);
  border-radius: var(--radius);
  padding: 16px 18px;
}}
.audit-grid b {{
  font-family: var(--sans);
  font-size: 11px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  color: var(--accent);
  font-weight: 600;
  display: block;
  margin-bottom: 4px;
}}
.audit-grid p {{
  font-family: var(--mono);
  font-size: 11px;
  word-break: break-all;
  color: var(--ink-soft);
  margin: 0;
}}
.raw-json {{
  margin-top: 16px;
  border: 1px solid var(--rule);
  border-radius: var(--radius);
  background: var(--paper-raised);
  padding: 12px 16px;
}}
.raw-json summary {{
  font-family: var(--sans);
  font-size: 13px;
  font-weight: 600;
  color: var(--ink);
  cursor: pointer;
}}
.raw-json pre {{
  max-height: 480px;
  overflow: auto;
  margin: 12px 0 0;
  padding: 12px;
  background: #18181B;
  color: #E4E4E7;
  border-radius: var(--radius);
  font-family: var(--mono);
  font-size: 11px;
  line-height: 1.5;
}}

.evidence-drawer {{
  position: fixed;
  inset: 0;
  pointer-events: none;
  z-index: var(--z-drawer);
}}
.evidence-drawer.open {{ pointer-events: auto; }}
.drawer-backdrop {{
  position: absolute;
  inset: 0;
  background: rgba(24, 24, 27, 0.32);
  opacity: 0;
  transition: opacity 200ms ease;
}}
.evidence-drawer.open .drawer-backdrop {{ opacity: 1; }}
.drawer-panel {{
  position: absolute;
  top: 0;
  right: 0;
  width: min(540px, calc(100vw - 24px));
  height: 100%;
  overflow: auto;
  background: var(--paper-raised);
  border-left: 1px solid var(--rule);
  box-shadow: var(--shadow-drawer);
  padding: 24px 28px;
  transform: translateX(102%);
  transition: transform 240ms ease;
}}
.evidence-drawer.open .drawer-panel {{ transform: translateX(0); }}
.drawer-close {{
  float: right;
  border: 1px solid var(--rule);
  background: var(--paper-raised);
  padding: 6px 12px;
  font-family: var(--sans);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  border-radius: var(--radius-chip);
  color: var(--ink);
}}
.drawer-close:hover {{
  background: var(--ink);
  color: var(--paper-raised);
}}
.drawer-ref {{
  font-family: var(--mono);
  font-size: 12px;
  color: var(--accent);
  word-break: break-all;
  margin: 12px 0 4px;
}}
.drawer-panel h2 {{
  font-family: var(--serif);
  font-size: 22px;
  font-weight: 600;
  color: var(--ink);
  margin: 4px 0 12px;
}}
.drawer-panel .reading {{ margin: 4px 0 8px; }}
.drawer-section {{
  border-top: 1px solid var(--rule);
  padding-top: 14px;
  margin-top: 16px;
}}
.drawer-section h3 {{
  font-family: var(--sans);
  font-size: 12px;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  font-weight: 700;
  color: var(--accent);
  margin: 0 0 8px;
}}
.drawer-section p, .drawer-section ul, .drawer-section ol {{
  font-size: 14px;
  line-height: 1.6;
  color: var(--ink-soft);
  margin: 0 0 8px;
  padding-left: 0;
}}
.drawer-section ul, .drawer-section ol {{ padding-left: 18px; }}
.drawer-empty {{
  padding: 18px;
  border: 1px dashed var(--rule-strong);
  border-radius: var(--radius);
  color: var(--muted);
  font-size: 13px;
}}

@media (max-width: 720px) {{
  .drawer-panel {{
    top: auto;
    bottom: 0;
    width: 100%;
    height: min(80vh, 720px);
    border-left: 0;
    border-top: 1px solid var(--rule);
    transform: translateY(102%);
  }}
  .evidence-drawer.open .drawer-panel {{ transform: translateY(0); }}
}}

@media (prefers-reduced-motion: reduce) {{
  *, *::before, *::after {{
    transition: none !important;
    animation: none !important;
  }}
  .layer-card__body {{ grid-template-rows: 1fr !important; }}
  .layer-card__head[aria-expanded="false"] + .layer-card__body {{ display: none !important; }}
  .layer-card__head[aria-expanded="true"] + .layer-card__body {{ display: block !important; }}
}}

.template-atlas .chain-grid,
.template-atlas .indicator-grid {{
  grid-template-columns: repeat(2, minmax(0, 1fr));
}}
.template-workbench .indicator-grid {{
  grid-template-columns: repeat(3, minmax(0, 1fr));
}}
@media (max-width: 720px) {{
  .template-atlas .chain-grid,
  .template-atlas .indicator-grid {{
    grid-template-columns: 1fr;
  }}
  .template-workbench .indicator-grid {{
    grid-template-columns: 1fr;
  }}
}}
"""


# ---------------------------------------------------------------------------
# JS template
# ---------------------------------------------------------------------------
JS_TEMPLATE = """
const drawer = document.getElementById('evidence-drawer');
const drawerContent = document.getElementById('drawer-content');
const payloadNode = document.getElementById('vnext-data');
const payload = payloadNode ? JSON.parse(payloadNode.textContent) : {};

const indicatorIndex = new Map();
Object.entries(payload.layers || {}).forEach(([layer, card]) => {
  (card.indicator_analyses || []).forEach((item) => {
    if (!item || !item.function_id) return;
    const ref = `${layer}.${item.function_id}`;
    indicatorIndex.set(ref, { layer, item });
  });
});

let lastDrawerTrigger = null;

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#039;');
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

function slug(ref) {
  return canonicalRef(ref).replace(/[./ :]+/g, '-');
}

function listItems(items) {
  const values = Array.isArray(items) ? items : [];
  return values.length ? values.map((item) => `<li>${escapeHtml(item)}</li>`).join('') : '<li>无</li>';
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

function toggleLayerCard(btn) {
  const open = btn.getAttribute('aria-expanded') === 'true';
  btn.setAttribute('aria-expanded', String(!open));
  if (!open) {
    requestAnimationFrame(() => {
      const rect = btn.getBoundingClientRect();
      if (rect.top < 96 || rect.top > window.innerHeight - 200) {
        btn.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }
    });
  }
}

function expandLayerCard(layer) {
  const btn = document.querySelector(`#layer-card-${layer} .layer-card__head`);
  if (!btn) return null;
  if (btn.getAttribute('aria-expanded') !== 'true') {
    btn.setAttribute('aria-expanded', 'true');
  }
  return btn;
}

function showDrawer() {
  drawer.classList.add('open');
  drawer.setAttribute('aria-hidden', 'false');
  const closeBtn = drawer.querySelector('[data-close-drawer]');
  if (closeBtn) closeBtn.focus();
}

function closeDrawer() {
  drawer.classList.remove('open');
  drawer.setAttribute('aria-hidden', 'true');
  if (lastDrawerTrigger && document.contains(lastDrawerTrigger)) {
    lastDrawerTrigger.focus();
  }
  lastDrawerTrigger = null;
}

function openDrawer(ref, label, triggerEl) {
  lastDrawerTrigger = triggerEl || null;
  const canonical = canonicalRef(ref);
  const entry = indicatorIndex.get(canonical);
  if (!entry) {
    drawerContent.innerHTML = `
      <p class="drawer-ref">${escapeHtml(label || ref)}</p>
      <div class="drawer-empty">这条证据没有命中具体的指标卡。原始 ref：${escapeHtml(ref)}</div>
    `;
    showDrawer();
    return;
  }
  const { layer, item } = entry;
  const targetId = `evidence-${slug(canonical)}`;
  const risks = (item.risk_flags || []).map((flag) => `<span>${escapeHtml(flag)}</span>`).join('');
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
  showDrawer();
}

document.querySelectorAll('[data-layer-jump]').forEach((tile) => {
  tile.addEventListener('click', () => {
    const layer = tile.dataset.layerJump;
    expandLayerCard(layer);
    requestAnimationFrame(() => {
      const card = document.getElementById(`layer-card-${layer}`);
      if (card) card.scrollIntoView({ behavior: 'smooth', block: 'start' });
    });
  });
});

document.querySelectorAll('[data-ref]').forEach((button) => {
  button.addEventListener('click', () => {
    openDrawer(button.dataset.ref, button.dataset.label || button.textContent, button);
  });
});

document.querySelectorAll('[data-close-drawer]').forEach((node) => {
  node.addEventListener('click', closeDrawer);
});
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && drawer.classList.contains('open')) closeDrawer();
});

drawerContent.addEventListener('click', (event) => {
  const jump = event.target.closest('[data-jump-target]');
  if (jump) {
    const layer = jump.dataset.layerTarget;
    const targetId = jump.dataset.jumpTarget;
    expandLayerCard(layer);
    requestAnimationFrame(() => {
      closeDrawer();
      const target = document.getElementById(targetId);
      if (target) {
        target.classList.add('target');
        target.scrollIntoView({ behavior: 'smooth', block: 'center' });
        setTimeout(() => target.classList.remove('target'), 1400);
      }
    });
  }
  const copy = event.target.closest('[data-copy-ref]');
  if (copy && navigator.clipboard) {
    navigator.clipboard.writeText(copy.dataset.copyRef);
    const original = copy.textContent;
    copy.textContent = '已复制';
    setTimeout(() => { copy.textContent = original; }, 1200);
  }
});

// Expose toggleLayerCard for inline onclick handlers
window.toggleLayerCard = toggleLayerCard;
"""


class VNextReportGenerator:
    """Generate a native vNext research UI from archived artifacts.

    Self-contained single-file HTML with Slate Editorial tokens and
    inline accordion semantics for L1–L5.
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
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Source+Serif+Pro:ital,wght@0,400;0,600;0,700;1,400&family=JetBrains+Mono:wght@400;500;600&display=swap" rel="stylesheet">
  <style>{self._css()}</style>
</head>
<body class="template-{_escape(template)}">
  <a class="skip-link" href="#main">跳到主内容</a>
  <span class="sr-only">NDX vNext Native Artifact UI Layer Workbench Source Tier Coverage Confirming Indicators</span>
  <div class="shell">
    {self._hero(final, meta, run_path, template)}
    {self._navigation()}
    {self._template_intro(template)}
    <main id="main">{self._main_sections(template, run_path, artifacts, final, payload_json)}</main>
  </div>
  <aside class="evidence-drawer" id="evidence-drawer" aria-hidden="true" role="dialog" aria-modal="true" aria-label="证据详情">
    <div class="drawer-backdrop" data-close-drawer></div>
    <section class="drawer-panel">
      <button class="drawer-close" type="button" data-close-drawer aria-label="关闭抽屉">关闭</button>
      <div id="drawer-content" aria-live="polite"></div>
    </section>
  </aside>
  <script type="application/json" id="vnext-data">{_escape(payload_json)}</script>
  <script>{self._js()}</script>
</body>
</html>
"""

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
<section class="template-intro" aria-label="模板说明">
  <div>
    <b>{_escape(template)} · {_escape(meta['name'])}</b>
    <p>{_escape(meta['description'])} 默认是阅读模式；点击证据可打开详情，审计材料保留在文末。</p>
  </div>
  <div class="template-legend">{alternatives}</div>
</section>
"""

    def _hero(self, final: Dict[str, Any], meta: Dict[str, Any], run_path: Path, template: str) -> str:
        confidence = final.get("confidence", "medium")
        approval = final.get("approval_status", "")
        success = f"{meta.get('indicator_successful', '?')}/{meta.get('indicator_total', '?')}"
        template_name = TEMPLATE_DESCRIPTIONS[template]["name"]
        risks = "".join(
            f"<li>{_escape(_label(item, 'risk_flag'))}</li>"
            for item in _as_list(final.get("must_preserve_risks"))[:4]
        )
        return f"""
<header class="hero" id="top">
  <div class="eyebrow">NDX vNext Native Artifact UI · {_escape(template_name)}</div>
  <div class="hero-grid">
    <div>
      <h1>{_escape(final.get('final_stance', 'N/A'))}</h1>
      <p class="hero-note">{_escape(final.get('adjudicator_notes', ''))}</p>
    </div>
    <aside class="verdict-card" aria-label="最终判断核心字段">
      <div class="verdict-row"><span>审批</span><strong>{_escape(_label(approval, 'approval'))}</strong></div>
      <div class="verdict-row"><span>置信度</span><strong class="pill {_confidence_class(confidence)}">{_escape(_label(confidence, 'confidence'))}</strong></div>
      <div class="verdict-row"><span>数据日期</span><strong class="mono">{_escape(meta.get('data_date', 'N/A'))}</strong></div>
      <div class="verdict-row"><span>指标覆盖</span><strong class="mono">{_escape(success)}</strong></div>
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
<nav class="nav" aria-label="章节导航">
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
        risks = "".join(
            f"<li>{_escape(_label(item, 'risk_flag'))}</li>"
            for item in _as_list(final.get("must_preserve_risks"))
        )
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
    <div class="risk-list">
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
        risk = artifacts.get("risk_boundary_report", {}) or {}
        boundary = risk.get("boundary_status", {}) if isinstance(risk.get("boundary_status"), dict) else {}
        boundary_cards = "".join(
            f"""
<article class="boundary-card {_severity_class(status)}">
  <span>{_escape(_label(name, 'boundary'))}</span>
  <b>{_escape(_label(status, 'severity'))}</b>
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
  <span class="pill {_confidence_class(item.get('probability'))}">概率 {_escape(_label(item.get('probability', ''), 'confidence'))}</span>
</article>
"""
                )
            else:
                failures.append(f'<article class="trigger-card"><h3>{_escape(item)}</h3></article>')
        must = "".join(
            f"<li>{_escape(_label(item, 'risk_flag'))}</li>"
            for item in _as_list(risk.get("must_preserve_risks"))
        )
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
    <b>{_escape(_label(conflict.get('severity', 'medium'), 'severity'))}</b>
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
    <b>{_escape(_label(conflict.get('severity', 'medium'), 'severity'))} · {_escape(_label(conflict.get('confidence', 'medium'), 'confidence'))}</b>
  </div>
  <small>{_escape(conflict.get('conflict_type', 'conflict'))} · {_escape(layers)}</small>
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
    <b>{_escape(_label(chain.get('confidence', 'medium'), 'confidence'))}</b>
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
    <b>{_escape(_label(path.get('confidence', 'medium'), 'confidence'))}</b>
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
        layers = artifacts.get("layers", {}) or {}
        tiles = "".join(
            self._layer_summary_tile(layer, layers.get(layer, {}))
            for layer in ["L1", "L2", "L3", "L4", "L5"]
        )
        cards = "".join(
            self._layer_card(layer, layers.get(layer, {}), default_open=(layer == "L1"))
            for layer in ["L1", "L2", "L3", "L4", "L5"]
        )
        return f"""
<section class="panel layers-panel" id="layers">
  <div class="section-kicker">05 · 五层底稿</div>
  <h2>先看摘要，再展开原生底稿</h2>
  <p class="section-note">五张层级卡纵向常驻；点击卡头展开当层完整底稿，多张可同时展开。摘要永远可见，避免"跳走找不回"。</p>
  <div class="layer-summary-grid">{tiles}</div>
  <div class="layer-stack">{cards}</div>
</section>
"""

    def _layer_summary_tile(self, layer: str, card: Dict[str, Any]) -> str:
        risks = "".join(
            f"<span>{_escape(_label(flag, 'risk_flag'))}</span>"
            for flag in _as_list(card.get("risk_flags"))[:3]
        )
        confidence = card.get("confidence", "medium")
        return f"""
<button class="layer-summary-tile" type="button" data-layer-jump="{layer}" aria-label="跳转到 {layer} 层级卡">
  <div>
    <b>{layer}</b>
    <span>{_escape(LAYER_TITLES.get(layer, ''))}</span>
  </div>
  <p>{_escape(card.get('local_conclusion', '无摘要'))}</p>
  <footer>
    <span class="pill {_confidence_class(confidence)}">{_escape(_label(confidence, 'confidence'))}</span>
    <span class="mini-risks">{risks}</span>
  </footer>
</button>
"""

    def _layer_card(self, layer: str, card: Dict[str, Any], *, default_open: bool) -> str:
        confidence = card.get("confidence", "medium")
        risks_inline = "".join(
            f"<span>{_escape(_label(flag, 'risk_flag'))}</span>"
            for flag in _as_list(card.get("risk_flags"))[:3]
        )
        local_conclusion = card.get("local_conclusion", "无摘要")
        head_id = f"layer-card-head-{layer}"
        body_id = f"layer-card-body-{layer}"
        expanded = "true" if default_open else "false"
        hooks = "".join(
            f"<li><b>{_escape(hook.get('target_layer', ''))}</b> {_escape(hook.get('question', ''))}</li>"
            for hook in _as_list(card.get("cross_layer_hooks"))
        )
        indicators = "".join(
            self._indicator_card(layer, item)
            for item in _as_list(card.get("indicator_analyses"))
        )
        risk_flags_full = "".join(
            f"<span>{_escape(_label(flag, 'risk_flag'))}</span>"
            for flag in _as_list(card.get("risk_flags"))
        )
        quality = card.get("quality_self_check", {}) if isinstance(card.get("quality_self_check"), dict) else {}
        quality_items = "".join(
            f"<li><b>{_escape(key)}:</b> {_escape(value)}</li>"
            for key, value in quality.items()
        )
        return f"""
<article class="layer-card" id="layer-card-{layer}" data-layer="{layer}">
  <button class="layer-card__head"
          type="button"
          id="{head_id}"
          aria-expanded="{expanded}"
          aria-controls="{body_id}"
          onclick="toggleLayerCard(this)">
    <span class="layer-no">{layer}</span>
    <span class="layer-title">{_escape(LAYER_TITLES.get(layer, ''))}</span>
    <span class="layer-summary">{_escape(local_conclusion)}</span>
    <span class="pill {_confidence_class(confidence)}">{_escape(_label(confidence, 'confidence'))}</span>
    <span class="mini-risks" aria-hidden="true">{risks_inline}</span>
    {_icon('chevron')}
  </button>
  <div class="layer-card__body" id="{body_id}" role="region" aria-labelledby="{head_id}">
    <div>
      <div class="layer-card__body-inner">
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
        <div class="risk-chip-row">{risk_flags_full}</div>
        <details class="hook-box" open>
          <summary>Cross-Layer Hooks</summary>
          <ul>{hooks or '<li>无</li>'}</ul>
        </details>
        <details class="hook-box">
          <summary>Quality Self Check</summary>
          <ul>{quality_items or '<li>无</li>'}</ul>
        </details>
        <div class="indicator-grid">{indicators or '<p>无指标级分析。</p>'}</div>
      </div>
    </div>
  </div>
</article>
"""

    def _indicator_card(self, layer: str, item: Dict[str, Any]) -> str:
        function_id = str(item.get("function_id", "unknown"))
        ref = f"{layer}.{function_id}"
        percentile = _extract_percentile(item.get("current_reading"))
        chain = "".join(f"<li>{_escape(step)}</li>" for step in _as_list(item.get("first_principles_chain")))
        implications = self._ref_chips(item.get("cross_layer_implications", []), link=False)
        risks = "".join(
            f"<span>{_escape(_label(flag, 'risk_flag'))}</span>"
            for flag in _as_list(item.get("risk_flags"))
        )
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
        critique = artifacts.get("critique", {}) or {}
        risk = artifacts.get("risk_boundary_report", {}) or {}
        schema = artifacts.get("schema_guard_report", {}) or {}
        firewall = artifacts.get("synthesis_packet", {}).get("objective_firewall_summary", {}) or {}
        failures = "".join(
            f"<li>{_escape(item.get('condition', item))} <span>{_escape(item.get('impact', '')) if isinstance(item, dict) else ''}</span></li>"
            for item in _as_list(risk.get("failure_conditions"))
        )
        must = "".join(
            f"<li>{_escape(_label(item, 'risk_flag'))}</li>"
            for item in _as_list(risk.get("must_preserve_risks"))
        )
        issues = "".join(f"<li>{_escape(item)}</li>" for item in _as_list(critique.get("cross_layer_issues")))
        tensions = "".join(f"<li>{_escape(item)}</li>" for item in _as_list(firewall.get("unresolved_tensions")))
        firewall_warnings = "".join(f"<li>{_escape(item)}</li>" for item in _as_list(firewall.get("warnings")))
        return f"""
<section class="panel" id="governance">
  <div class="section-kicker">06 · Governance</div>
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
  <div class="section-kicker">07 · Audit Trail</div>
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
        return CSS_TEMPLATE

    def _js(self) -> str:
        return JS_TEMPLATE


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
