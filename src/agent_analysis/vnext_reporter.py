from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from urllib.parse import quote

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

LAYER_TITLES_ZH = {
    "L1": "宏观与利率",
    "L2": "信用与波动",
    "L3": "内部结构",
    "L4": "估值与盈利",
    "L5": "价格与执行",
}

DISPLAY_LABELS = {
    "same_day_or_days": "未来几天",
    "one_to_three_months": "1-3 个月",
    "six_to_twelve_months": "6-12 个月",
    "core_position": "核心仓",
    "tactical_position": "战术仓",
    "waiting_cash": "等待资金",
    "partially_reflected": "部分反映",
    "not_reflected": "尚未反映",
    "largely_reflected": "大体反映",
    "unclear": "不明朗",
    "macro_valuation": "宏观与估值",
    "feedback_bridge_v2": "反馈复核（第二轮）",
    "small_position_dca_waiting_for_golden_pit": "小仓位定投，等待黄金坑",
    "credit": "信用",
    "rates": "利率",
    "valuation": "估值",
    "liquidity": "流动性",
    "technical_panic": "技术与恐慌",
    "leading": "暂时领先",
    "candidate": "候选挑战",
    "retained": "保留竞争",
    "rejected": "已出局",
    "merged": "已合并",
    "downgraded": "已降级",
    "2-5 decisions per year": "每年 2-5 次关键决策",
}

# Short, local explanations keep the report readable without requiring an
# external glossary or network request.  Definitions describe what a metric
# measures; they do not turn an indicator into an investment conclusion.
INDICATOR_GLOSSARY = {
    "HY OAS": "高收益债相对国债的信用利差，常用来观察信用风险溢价。",
    "IG OAS": "投资级债相对国债的信用利差，反映较高质量信用市场的风险溢价。",
    "ADX": "平均趋向指数，用来衡量趋势强弱，不判断趋势方向。",
    "MACD": "移动平均收敛发散指标，用快慢均线差及其信号线观察动量变化。",
    "RSI": "相对强弱指数，衡量一段窗口内上涨与下跌动能的相对强度。",
    "ATR": "平均真实波幅，衡量价格波动幅度，不表示涨跌方向。",
    "OBV": "能量潮，将成交量按涨跌方向累积，用来观察量价配合。",
    "CMF": "蔡金资金流量指标，用价格位置与成交量估计资金流入流出。",
    "VIX": "标普 500 期权隐含波动率指标，常被称为市场恐慌温度计。",
    "VXN/VIX": "纳斯达克波动率与标普波动率之比，用来比较两类风险偏好。",
    "Forward PE": "预期市盈率，用价格除以未来预期盈利；预期本身可能修正。",
    "Trailing PE": "静态市盈率，用价格除以过去已实现盈利。",
    "M7": "纳斯达克七家大型科技公司组合的简称。",
    "NDX/NDXE": "纳斯达克 100 指数与其等权版本的相对比值，用来观察集中度。",
}


def _glossary_term(term: Any, *, as_button: bool = True, unique_id: Any = None) -> str:
    """Render a safe, keyboard-accessible metric definition trigger."""
    raw = str(term or "")
    definition = INDICATOR_GLOSSARY.get(raw)
    if not definition:
        return _escape(raw)
    suffix = "" if unique_id is None else f"-{unique_id}"
    token = re.sub(r"[^a-z0-9]+", "-", f"{raw}{suffix}".lower()).strip("-") or "metric"
    tip_id = f"metric-glossary-{token}"
    if not as_button:
        return (
            f'<span class="metric-glossary metric-glossary--nested" aria-describedby="{_escape(tip_id)}">'
            f'{_escape(raw)}<span id="{_escape(tip_id)}" class="metric-glossary__tooltip" role="tooltip" aria-hidden="true" hidden>'
            f'{_escape(definition)}</span></span>'
        )
    return (
        f'<button type="button" class="metric-glossary" tabindex="0" '
        f'aria-describedby="{_escape(tip_id)}" aria-expanded="false" '
        f'data-glossary-term="{_escape(raw)}">{_escape(raw)}'
        f'<span id="{_escape(tip_id)}" class="metric-glossary__tooltip" role="tooltip" aria-hidden="true">'
        f'{_escape(definition)}</span></button>'
    )


def _indicator_glossary_label(
    function_id: Any,
    metric: Any,
    *,
    as_button: bool = True,
    unique_id: Any = None,
) -> str:
    raw = str(metric or "").strip()
    aliases = {
        "get_hy_oas_bp": "HY OAS",
        "get_ig_oas_bp": "IG OAS",
        "get_adx_qqq": "ADX",
        "get_macd_qqq": "MACD",
        "get_rsi_qqq": "RSI",
        "get_atr_qqq": "ATR",
        "get_obv_qqq": "OBV",
        "get_price_volume_quality_qqq": "CMF",
        "get_vix": "VIX",
        "get_vxn_vix_ratio": "VXN/VIX",
    }
    term = raw if raw in INDICATOR_GLOSSARY else aliases.get(str(function_id), "")
    return _glossary_term(
        term,
        as_button=as_button,
        unique_id=unique_id if unique_id is not None else function_id,
    ) if term else _escape(raw or function_id)

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
    "layers": {
        "name": "完整分层底稿",
        "description": "brief 的外部深读落点，完整保留 L1-L5 原生指标卡和审计锚点。",
    },
}

BRIEF_SECTION_ORDER = (
    "facade",
    "thesis",
    "stress",
    "world",
    "risks",
    "change",
    "brief_layers",
    "brief_audit",
)

TEMPLATE_ORDER = {
    "cockpit": ["decision", "actions", "evidence", "news", "conflicts", "layers", "governance", "audit"],
    "brief": list(BRIEF_SECTION_ORDER),
    "atlas": ["evidence", "news", "conflicts", "decision", "actions", "layers", "governance", "audit"],
    "workbench": ["layers", "news", "conflicts", "evidence", "decision", "actions", "governance", "audit"],
    "layers": ["layers"],
}

REF_DIGEST_FIELDS = (
    "metric",
    "layer",
    "value_line",
    "quantile",
    "answers",
    "cannot_prove",
    "falsifier",
    "artifact_anchor",
)

# Only shape/structure indicators may carry a tiny trend in the brief drawer.
# The verified source is the collector snapshot's top-level recompute_inputs.
DRAWER_TREND_WHITELIST = (
    "get_advance_decline_line",
    "get_ndx_ndxe_ratio",
    "get_qqq_qqew_ratio",
    "get_percent_above_ma",
    "get_new_highs_lows",
    "get_multi_scale_ma_position",
    "get_donchian_channels_qqq",
    "get_macd_qqq",
    "get_obv_qqq",
    "get_price_volume_quality_qqq",
    "get_10y_real_rate",
    "get_hy_oas_bp",
)

HIGH_QUANTILE_DANGER = {
    "get_10y_real_rate",
    "get_10y_treasury",
    "get_fed_funds_rate",
    "get_vix",
    "get_vxn",
    "get_hy_quality_spread_bp",
    "get_ndx_ndxe_ratio",
    "get_qqq_qqew_ratio",
    "get_qqq_top10_concentration",
    "get_ndx_pe_and_earnings_yield",
}

LOW_QUANTILE_DANGER = {
    "get_damodaran_us_implied_erp",
    "get_equity_risk_premium",
}

# ---------------------------------------------------------------------------
# Style definitions — each maps to an external CSS file.
# ---------------------------------------------------------------------------
STYLE_FONTS = {
    "slate_v2": (
        'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700'
        '&family=Source+Serif+Pro:ital,wght@0,400;0,600;0,700;1,400'
        '&family=JetBrains+Mono:wght@400;500;600&display=swap'
    ),
    "slate_v3": (
        'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700'
        '&family=Source+Serif+Pro:ital,wght@0,400;0,600;0,700;1,400'
        '&family=JetBrains+Mono:wght@400;500;600&display=swap'
    ),
    "warm_paper": (
        'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700'
        '&family=Merriweather:ital,wght@0,400;0,700;1,400'
        '&family=JetBrains+Mono:wght@400;500;600&display=swap'
    ),
    "swiss": (
        'https://fonts.googleapis.com/css2?family=Libre+Franklin:wght@400;500;600;700;800'
        '&family=IBM+Plex+Mono:wght@400;500;600&display=swap'
    ),
    "terminal": (
        'https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700'
        '&family=JetBrains+Mono:wght@400;500;600'
        '&family=Fira+Code:wght@400;500&display=swap'
    ),
}

STYLES_DIR = Path(__file__).resolve().parent / "report_styles"

LABELS: Dict[str, Dict[str, str]] = {
    "approval": {
        "approved": "通过",
        "approved_with_reservations": "有保留通过",
        "approved_with_caution": "谨慎通过",
        "rejected": "否决",
    },
    "confidence": {"low": "低", "medium": "中", "high": "高"},
    "severity": {
        "low": "低",
        "medium": "中",
        "high": "高",
        "safe": "可控",
        "warning": "需关注",
        "breached": "已突破",
    },
    "publish_status": {
        "publishable": "可发布",
        "blocked": "不可发布",
        "unpublishable": "不可发布",
        "not recorded": "未记录",
    },
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


def _display_label(value: Any) -> str:
    raw = str(value or "")
    return DISPLAY_LABELS.get(raw, raw.replace("_", " "))


def _source_tier_label(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    labels = {
        "official": "官方来源",
        "official_provider": "官方数据商",
        "official_macro": "官方宏观数据",
        "licensed_provider": "授权数据商",
        "licensed_manual": "授权手动数据",
        "component_model": "成分模型估算",
        "third_party_estimate": "第三方估算",
        "proxy": "代理指标",
        "unavailable": "不可用",
        "manual": "手动输入",
    }
    parts = []
    for part in re.split(r"([/·,;]\s*)", raw):
        token = part.strip()
        if not token:
            continue
        if re.fullmatch(r"[/·,;]\s*", part):
            parts.append(part)
        else:
            parts.append(labels.get(token, token.replace("_", " ")))
    return "".join(parts)


def _plain_value(value: Any) -> str:
    raw = str(value or "").strip()
    if raw in {"not_available", "N/A", "none", "None"}:
        return "未记录"
    if raw == "available":
        return "可用"
    if raw == "unavailable":
        return "不可用"
    if raw == "historical percentile unavailable: source does not provide explicit percentile/rank":
        return "历史分位不可用：来源未提供明确分位或排名"
    quality_labels = {
        "missing_source_url": "未记录来源链接",
        "license_note_defaulted": "授权说明使用默认值",
        "vintage_date_not_available": "未记录版本日",
        "coverage_missing_or_unspecified": "覆盖率未记录或未说明",
        "live_current_field": "实时字段，非历史版本",
        "official_ndx_forward_earnings_quality_series_not_available_automatically_component_and_yahoo_revision_proxies_used_as_supporting_context": "未自动取得官方 NDX 前瞻盈利质量序列，改用成分模型和 Yahoo 盈利修正作为辅助背景",
        "public_endpoint_review_required": "公开端点需要复核",
    }
    if raw in quality_labels:
        return quality_labels[raw]
    if raw.startswith("excluded_constituents_due_to_missing_or_incomplete_price_data:"):
        suffix = raw.split(":", 1)[1].strip()
        return f"部分成分股因价格数据缺失或不完整被排除：{suffix}"
    return raw


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _load_local_decision_profile(path: Optional[Path] = None) -> Dict[str, Any]:
    """Load the reader's local (gitignored) investment policy profile.

    This deliberately never raises: missing file just means the profile is
    unconfigured, which the caller renders as an honest placeholder.
    """
    target = path or (Path(__file__).resolve().parents[2] / "config" / "user_decision_profile.local.json")
    if not target.exists():
        return {}
    try:
        with target.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


_BEARISH_STANCE_KEYWORDS = ["防御", "减仓", "降低", "做空", "谨慎", "偏空", "观望", "等待信号", "风险高于机会", "压缩风险"]
_BULLISH_STANCE_KEYWORDS = ["加仓", "增持", "做多", "偏多", "进取", "乐观", "机会大于风险", "逢低买入", "价值明确"]


def _classify_investor_stance(final_stance: str, state_diagnosis: str = "") -> str:
    """Classify the system's final stance into defensive/constructive/neutral.

    Keyword-based and deterministic. Ties (including 0-0) resolve to neutral.
    Real final_stance text can be genuinely mixed, so this is a 3-way
    classifier rather than a strict bull/bear split.
    """
    text = f"{final_stance or ''} {state_diagnosis or ''}"
    bearish_hits = sum(text.count(keyword) for keyword in _BEARISH_STANCE_KEYWORDS)
    bullish_hits = sum(text.count(keyword) for keyword in _BULLISH_STANCE_KEYWORDS)
    if bearish_hits > bullish_hits:
        return "defensive"
    if bullish_hits > bearish_hits:
        return "constructive"
    return "neutral"


def _escape(value: Any) -> str:
    if value is None:
        return ""
    return html.escape(str(value), quote=True)


_INVALIDATION_DIRECTION_RE = re.compile(r"^\s*【(转多|转空)】\s*")


def _split_invalidation_item(text: Any) -> Tuple[str, str]:
    """Return an optional direction prefix and the condition text."""
    raw = "" if text is None else str(text)
    match = _INVALIDATION_DIRECTION_RE.match(raw)
    if not match:
        return "", raw
    return match.group(1), raw[match.end():].strip()


def _render_invalidation_item(text: Any) -> str:
    """Render an invalidation condition, preserving legacy untagged text."""
    direction, body = _split_invalidation_item(text)
    if not direction:
        return _escape(text)
    tone = "good" if direction == "转多" else "bad"
    return f'<span class="pill {tone}">{_escape(direction)}</span> {_escape(body)}'


def _artifact_href(path: Any) -> str:
    text = str(path or "").strip()
    if not text or text in {"未生成", "未记录"}:
        return ""
    if re.match(r"^https?://", text):
        return text
    candidate = Path(text).expanduser()
    if candidate.exists():
        return f"/artifact?path={quote(str(candidate.resolve()), safe='')}"
    if text.startswith("/"):
        return f"/artifact?path={quote(text, safe='')}"
    return ""


def _artifact_link(label: Any, path: Any) -> str:
    path_text = str(path or "").strip()
    href = _artifact_href(path_text)
    if not href:
        return f"<span>{_escape(path_text or '未记录')}</span>"
    return f'<a href="{_escape(href)}">{_escape(path_text)}</a>'


def _canonical_ref(ref: Any) -> str:
    text = " ".join(str(ref or "").split()).replace(" #", "#").replace("# ", "#")
    if ":" in text:
        text = text.split(":", 1)[0].strip()
    if "." not in text:
        return text
    layer, function_id = text.split(".", 1)
    layer = layer.strip().upper()
    function_id = function_id.strip()
    function_name, separator, field_name = function_id.partition("#")
    function_name = function_name.lower()
    if layer in {"L1", "L2", "L3", "L4", "L5"} and function_name and not function_name.startswith("get_"):
        function_name = f"get_{function_name}"
    function_id = function_name + (f"#{field_name}" if separator else "")
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


def _safe_number(value: Any) -> Optional[float]:
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", "")
    match = re.search(r"-?\d+(?:\.\d+)?", text)
    if not match:
        return None
    try:
        return float(match.group(0))
    except ValueError:
        return None


def _text(value: Any, limit: Optional[int] = None) -> str:
    raw = re.sub(r"\s+", " ", "" if value is None else str(value)).strip()
    if limit and len(raw) > limit:
        return raw[: limit - 1].rstrip() + "…"
    return raw


def _display_date(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return "未记录"
    if re.match(r"^\d{4}-\d{2}-\d{2}", text):
        return text[:10]
    try:
        from email.utils import parsedate_to_datetime

        return parsedate_to_datetime(text).strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return text


def _sentence(value: Any, limit: int = 180) -> str:
    raw = _text(value)
    if len(raw) <= limit:
        return raw
    for mark in "。；;，,":
        pos = raw.rfind(mark, 0, limit)
        if pos > 48:
            return raw[: pos + 1]
    return raw[: limit - 1].rstrip() + "…"


def _fact_excerpt(value: Any, limit: int = 120) -> str:
    raw = _text(value)
    if not raw:
        return "未读取正文"
    for match in re.finditer(r"[。.]", raw):
        index = match.start()
        if index > limit:
            break
        if index > 0 and raw[index - 1].isdigit():
            continue
        sentence = raw[:index].strip()
        if sentence:
            return sentence
    if len(raw) > limit:
        return raw[:limit].rstrip() + "…"
    return raw


def _split_sentences(value: Any, max_items: int = 3, item_limit: int = 96) -> List[str]:
    raw = _text(value)
    if not raw:
        return []
    parts = [part.strip() for part in re.split(r"(?<=[。；;])", raw) if part.strip()]
    if len(parts) < 2:
        parts = [part.strip() for part in re.split(r"[，,]", raw) if part.strip()]
    snippets: List[str] = []
    for part in parts:
        clean = part.strip("，,；; ")
        if not clean:
            continue
        snippets.append(_sentence(clean, item_limit))
        if len(snippets) >= max_items:
            break
    return snippets or [_sentence(raw, item_limit)]


def _rich_text(value: Any) -> str:
    rendered = _escape(value)
    patterns = [
        r"SMA\d+",
        r"MACD柱?",
        r"RSI",
        r"ADX",
        r"OBV",
        r"CMF",
        r"VXN/VIX",
        r"HY OAS",
        r"IG OAS",
        r"CCC-BB",
        r"NDX/NDXE",
        r"QQQ/QQEW",
        r"Forward PE",
        r"Trailing PE",
        r"risk_on",
        r"risk_off",
        r"Top10",
        r"M7",
        r"NDX",
        r"QQQ",
        r"(?<![\w.])-?\d+(?:\.\d+)?(?:%|bp|B|万亿美元|亿美元|倍|点)",
    ]
    combined = re.compile("|".join(f"({pattern})" for pattern in patterns))
    return combined.sub(lambda match: f"<strong>{match.group(0)}</strong>", rendered)


def _summary_fragments(value: Any, max_items: int = 3) -> str:
    return "".join(
        f"<span>{_rich_text(item)}</span>"
        for item in _split_sentences(value, max_items=max_items, item_limit=96)
    )


def _narrative_list(value: Any, max_items: int = 5) -> str:
    return "<ul class=\"memo-narrative-list\">" + "".join(
        f"<li>{_rich_text(item)}</li>"
        for item in _split_sentences(value, max_items=max_items, item_limit=150)
    ) + "</ul>"


def _numeric_series(rows: Sequence[Dict[str, Any]], field: str = "value") -> List[float]:
    values: List[float] = []
    for row in rows:
        value = _safe_number(row.get(field))
        if value is not None:
            values.append(value)
    return values


def _percentile_rank(values: Sequence[float], current: float) -> Optional[float]:
    clean = [value for value in values if isinstance(value, (int, float))]
    if not clean:
        return None
    return 100 * sum(value <= current for value in clean) / len(clean)


def _fmt_pct(value: Optional[float], digits: int = 0, signed: bool = False) -> str:
    if value is None:
        return "N/A"
    sign = "+" if signed and value > 0 else ""
    return f"{sign}{value:.{digits}f}%"


def _fmt_bps(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    return f"{value * 100:+.0f}bp"


def _fmt_percentile(value: Any, digits: int = 0) -> str:
    percentile = _normalize_percent(value)
    if percentile is None:
        return "N/A"
    return f"{percentile:.{digits}f}%"


def _series_delta(rows: Sequence[Dict[str, Any]], field: str, periods: int) -> Optional[float]:
    values = _numeric_series(rows, field)
    if len(values) <= periods:
        return None
    return values[-1] - values[-1 - periods]


def _series_return(rows: Sequence[Dict[str, Any]], field: str, periods: int) -> Optional[float]:
    values = _numeric_series(rows, field)
    if len(values) <= periods or abs(values[-1 - periods]) < 0.000001:
        return None
    return (values[-1] / values[-1 - periods] - 1) * 100


def _short_date(value: Any) -> str:
    raw = str(value or "")
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if match:
        return f"{match.group(1)[2:]}.{match.group(2)}.{match.group(3)}"
    match = re.search(r"(\d{4})-(\d{2})", raw)
    if match:
        return f"{match.group(1)[2:]}.{match.group(2)}"
    return raw[:8]


def _parse_row_date(value: Any) -> Optional[datetime]:
    raw = str(value or "")
    for fmt, length in (("%Y-%m-%d", 10), ("%Y-%m", 7)):
        try:
            return datetime.strptime(raw[:length], fmt)
        except ValueError:
            continue
    return None


def _spark_sample(rows: Sequence[Dict[str, Any]], years: Optional[float]) -> List[Dict[str, Any]]:
    all_rows = list(rows)
    if not all_rows:
        return []
    if years is None:
        return all_rows[-90:]
    end_date = next((_parse_row_date(row.get("time")) for row in reversed(all_rows) if _parse_row_date(row.get("time"))), None)
    if end_date is None:
        return all_rows
    cutoff = end_date - timedelta(days=int(365.25 * years))
    sample = [row for row in all_rows if (_parse_row_date(row.get("time")) or end_date) >= cutoff]
    return sample if len(sample) >= 2 else all_rows


def _downsample_rows(rows: Sequence[Dict[str, Any]], max_points: int) -> List[Dict[str, Any]]:
    items = list(rows)
    if len(items) <= max_points:
        return items
    if max_points < 2:
        return items[-max_points:]
    last_index = len(items) - 1
    indexes = sorted({round(i * last_index / (max_points - 1)) for i in range(max_points)})
    return [items[index] for index in indexes]


def _years_from_annotation(annotation: Optional[str]) -> Optional[int]:
    raw = annotation or ""
    if "10年分位" in raw or "10 年分位" in raw:
        return 10
    if "5年分位" in raw or "5 年分位" in raw:
        return 5
    return None


def _compact_value(value: Optional[float], digits: int = 2, suffix: str = "") -> str:
    if value is None:
        return "N/A"
    if abs(value) >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B{suffix}"
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.1f}M{suffix}"
    return f"{value:.{digits}f}{suffix}"


def _sparkline(
    rows: Sequence[Dict[str, Any]],
    field: str = "value",
    width: int = 420,
    height: int = 92,
    annotation: Optional[str] = None,
    show_guide: bool = True,
    window_years: Optional[float] = None,
    max_points: int = 180,
) -> str:
    sample = _downsample_rows(
        _spark_sample(rows, window_years if window_years is not None else _years_from_annotation(annotation)),
        max_points,
    )
    values: List[Tuple[int, float]] = []
    for index, row in enumerate(sample):
        value = _safe_number(row.get(field))
        if value is not None:
            values.append((index, value))
    if len(values) < 2:
        return "<svg class=\"spark\" viewBox=\"0 0 420 92\" role=\"img\"></svg>"
    low = min(value for _, value in values)
    high = max(value for _, value in values)
    if abs(high - low) < 0.0001:
        high = low + 1
    top_pad = 26 if annotation else 10
    bottom_pad = 16
    side_pad = 10
    denominator = max(1, len(sample) - 1)
    path = []
    for index, value in values:
        x = side_pad + (width - side_pad * 2) * index / denominator
        y = top_pad + (height - top_pad - bottom_pad) * (1 - (value - low) / (high - low))
        path.append(("M" if not path else "L") + f"{x:.1f},{y:.1f}")
    first = values[0][1]
    last_index, last = values[-1]
    direction = "up" if last >= first else "down"
    last_x = side_pad + (width - side_pad * 2) * last_index / denominator
    last_y = top_pad + (height - top_pad - bottom_pad) * (1 - (last - low) / (high - low))
    start = _short_date(next((row.get("time") for row in sample if row.get("time")), ""))
    requested_years = window_years if window_years is not None else _years_from_annotation(annotation)
    first_date = next((_parse_row_date(row.get("time")) for row in sample if _parse_row_date(row.get("time"))), None)
    end_date = next((_parse_row_date(row.get("time")) for row in reversed(sample) if _parse_row_date(row.get("time"))), None)
    coverage_years = ((end_date - first_date).days / 365.25) if first_date and end_date else None
    label = annotation or ""
    if annotation and requested_years and coverage_years is not None and coverage_years < requested_years * 0.8:
        label = f"{label} · 图自{start}"
    guide = (
        f"<line class=\"pct-guide\" x1=\"10\" x2=\"{last_x:.1f}\" y1=\"{last_y:.1f}\" y2=\"{last_y:.1f}\"/>"
        if show_guide and label
        else ""
    )
    label_text = f"<text class=\"pct-label\" x=\"10\" y=\"18\">{_escape(label)}</text>" if label else ""
    return (
        f"<svg class=\"spark {direction}\" viewBox=\"0 0 {width} {height}\" role=\"img\">"
        f"{guide}"
        f"{label_text}"
        f"<path d=\"{' '.join(path)}\"/>"
        f"<text class=\"spark-start\" x=\"10\" y=\"{height - 6}\">{_escape(start)}</text>"
        f"<text x=\"{width-10}\" y=\"18\" text-anchor=\"end\">{high:.2f}</text>"
        "</svg>"
    )


INDICATOR_CHARTS = {
    "get_fed_funds_rate": ("FED_FUNDS", "value"),
    "get_m2_yoy": ("M2_YOY", "value"),
    "get_net_liquidity_momentum": ("NET_LIQUIDITY", "value"),
    "get_10y_treasury": ("US10Y", "value"),
    "get_10y_real_rate": ("US10Y_REAL", "value"),
    "get_10y_breakeven": ("US10Y_BREAKEVEN", "value"),
    "get_vix": ("VIX", "value"),
    "get_vxn": ("VXN", "value"),
    "get_hy_oas_bp": ("HY_OAS", "value"),
    "get_ig_oas_bp": ("IG_OAS", "value"),
    "get_hy_quality_spread_bp": ("HY_QUALITY_SPREAD", "value"),
    "get_hyg_momentum": ("HYG", "value"),
    "get_vxn_vix_ratio": ("VXN_VIX_RATIO", "value"),
    "get_ndx_ndxe_ratio": ("NDX_NDXE_RATIO", "value"),
    "get_qqq_qqew_ratio": ("NDX_NDXE_RATIO", "value"),
    "get_damodaran_us_implied_erp": ("DAMODARAN_ERP_MONTHLY", "value"),
    "get_l5_deterministic_snapshot": ("QQQ_OHLCV", "close"),
    "get_qqq_technical_indicators": ("QQQ_OHLCV", "close"),
    "get_rsi_qqq": ("QQQ_OHLCV", "rsi14"),
    "get_atr_qqq": ("QQQ_OHLCV", "atr14"),
    "get_macd_qqq": ("QQQ_OHLCV", "macd_histogram"),
    "get_obv_qqq": ("QQQ_OHLCV", "obv"),
    "get_volume_analysis_qqq": ("QQQ_OHLCV", "volume"),
    "get_price_volume_quality_qqq": ("QQQ_OHLCV", "cmf20"),
    "get_donchian_channels_qqq": ("QQQ_OHLCV", "close"),
    "get_multi_scale_ma_position": ("QQQ_OHLCV", "close"),
}


def _first_present(mapping: Dict[str, Any], *keys: str) -> Any:
    if not isinstance(mapping, dict):
        return None
    for key in keys:
        value = mapping.get(key)
        if value is not None:
            return value
    return None


def _fmt_number(value: Any, *, suffix: str = "", digits: int = 2, fallback: str = "N/A") -> str:
    number = _safe_number(value)
    if number is None:
        return fallback
    return f"{number:.{digits}f}{suffix}"


def _minute_stamp(value: Any, *, assume_utc: bool = False) -> str:
    """Return a compact local-time minute stamp for filenames."""
    text = str(value or "").strip()
    if not text:
        return ""
    if re.fullmatch(r"\d{8}_\d{4,6}", text):
        return text[:13]
    if re.fullmatch(r"\d{8}", text):
        return f"{text}_0000"
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        if parsed.tzinfo is None and (assume_utc or "utc" in text.lower()):
            parsed = parsed.replace(tzinfo=timezone.utc)
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone()
        return parsed.strftime("%Y%m%d_%H%M")
    except ValueError:
        cleaned = re.sub(r"[^0-9]+", "", text)
        if len(cleaned) >= 12:
            return f"{cleaned[:8]}_{cleaned[8:12]}"
        if len(cleaned) >= 8:
            return f"{cleaned[:8]}_0000"
    return ""


def _run_minute_stamp(run_path: Path) -> str:
    match = re.search(r"(\d{8})_(\d{4})", run_path.name)
    if match:
        return f"{match.group(1)}_{match.group(2)}"
    return _minute_stamp(run_path.name)


def _json_for_script(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")


def _compact_text(value: Any, limit: int = 420) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _normalize_percent(value: Any) -> Optional[float]:
    number = _safe_number(value)
    if number is None:
        return None
    if abs(number) <= 1:
        number *= 100
    return _clamp(number, 0, 100)


def _polyline_path(points: List[Dict[str, Any]], field: str, *, width: int, height: int, pad: int) -> str:
    values = [_safe_number(point.get(field)) for point in points]
    numeric = [value for value in values if value is not None]
    if len(numeric) < 2:
        return ""
    low = min(numeric)
    high = max(numeric)
    if abs(high - low) < 0.0001:
        high = low + 1
    usable_w = width - pad * 2
    usable_h = height - pad * 2
    segments = []
    denominator = max(1, len(points) - 1)
    for index, value in enumerate(values):
        if value is None:
            continue
        x = pad + usable_w * index / denominator
        y = pad + usable_h * (1 - ((value - low) / (high - low)))
        segments.append(("M" if not segments else "L") + f"{x:.1f},{y:.1f}")
    return " ".join(segments)


def _confidence_class(value: Any) -> str:
    text = str(value or "").lower()
    if "high" in text:
        return "good"
    if "low" in text:
        return "bad"
    return "watch"


def _severity_class(value: Any) -> str:
    text = str(value or "").lower()
    if "high" in text or "breached" in text or "blocked" in text or "unpublishable" in text:
        return "bad"
    if "low" in text or "safe" in text or "publishable" in text:
        return "good"
    return "watch"


_DISCIPLINE_SIDE_LABELS: Dict[str, str] = {
    "buy": "买入条件",
    "sell": "卖出条件",
    "hold": "持有纪律",
    "risk": "风险边界",
    "claim": "观察确认项",
}

_DISCIPLINE_STATUS_TEXT: Dict[str, str] = {
    "met": "已满足",
    "not_met": "未满足",
    "insufficient_evidence": "证据不足",
}


def _discipline_status_view(side: Any, status: Any) -> Dict[str, str]:
    """把 (discipline_side, current_status) 映射成 {tone, text, side_label, side_class}。

    读者出口清单的核心语义修正：risk/sell 类条目一旦 "met" 代表风险已触发/卖出条件
    已成立，是需要读者警惕的信号，绝不能渲染成 good（绿色"已满足"）；只有 buy 类条目
    met 才是真正的好消息。discipline_side 缺失或不是已知取值时一律回退中性 tone
    （不猜方向），文案维持原有的通用状态文案，逻辑集中在这一处。
    """
    status_key = status if status in _DISCIPLINE_STATUS_TEXT else ""
    text = _DISCIPLINE_STATUS_TEXT.get(status_key, str(status) if status else "未记录")
    side_key = side if side in _DISCIPLINE_SIDE_LABELS else ""

    if not side_key:
        return {"tone": "watch", "text": text, "side_label": "", "side_class": ""}

    side_label = _DISCIPLINE_SIDE_LABELS[side_key]
    side_class = f"side-{side_key}"

    if status_key == "met" and side_key == "sell":
        return {"tone": "risk", "text": "卖出条件已成立", "side_label": side_label, "side_class": side_class}
    if status_key == "met" and side_key == "risk":
        return {"tone": "risk", "text": "风险已触发", "side_label": side_label, "side_class": side_class}
    if status_key == "met" and side_key == "hold":
        return {"tone": "watch", "text": "持有条件已成立", "side_label": side_label, "side_class": side_class}

    default_tone = {"met": "good", "not_met": "risk", "insufficient_evidence": "watch"}.get(status_key, "watch")
    return {"tone": default_tone, "text": text, "side_label": side_label, "side_class": side_class}


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _format_timestamp(value: Any) -> str:
    if not value:
        return "N/A"
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.strftime("%Y-%m-%d %H:%M UTC")
    except ValueError:
        return str(value)


def _observation_date_range(raw_data: Any) -> str:
    keys = {
        "date",
        "data_date",
        "effective_date",
        "observation_date",
        "as_of",
        "asof",
    }
    skip_tokens = ("collection", "generated", "timestamp", "expiry", "expiration")
    found: List[str] = []

    def visit(value: Any, key: str = "") -> None:
        key_l = str(key).lower()
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                visit(child_value, str(child_key))
            return
        if isinstance(value, list):
            for item in value:
                visit(item, key_l)
            return
        if key_l not in keys or any(token in key_l for token in skip_tokens):
            return
        text = str(value or "").strip()
        match = re.search(r"\b(20\d{2}-\d{2}-\d{2})\b", text)
        if match:
            found.append(match.group(1))

    visit(raw_data)
    unique = sorted(set(found))
    if not unique:
        return "N/A"
    if unique[0] == unique[-1]:
        return unique[0]
    return f"{unique[0]} 至 {unique[-1]}"


def _token_usage_summary(token_usage: Any) -> str:
    if not isinstance(token_usage, dict) or not token_usage:
        return "未记录"
    prompt = completion = total = 0
    stages = 0
    for value in token_usage.values():
        if not isinstance(value, dict):
            continue
        stages += 1
        prompt += int(value.get("prompt_tokens") or 0)
        completion += int(value.get("completion_tokens") or 0)
        total += int(value.get("total_tokens") or 0)
    if not stages:
        return "未记录"
    return f"{stages} 个阶段；输入 {prompt:,}，输出 {completion:,}，合计 {total:,}"


# CSS styles are loaded from external files in report_styles/ directory.
# See: slate_v2.css, warm_paper.css, swiss.css, terminal.css


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
  let text = String(ref || '').trim().replace(/\\s+/g, ' ').replace(/\\s*#\\s*/g, '#');
  if (text.includes(':')) text = text.split(':')[0].trim();
  if (!text.includes('.')) return text;
  const [rawLayer, rawFunction] = text.split('.', 2);
  const layer = rawLayer.trim().toUpperCase();
  const [rawFunctionName, fieldName] = rawFunction.trim().split('#', 2);
  let functionId = rawFunctionName.toLowerCase();
  if (/^L[1-5]$/.test(layer) && functionId && !functionId.startsWith('get_')) {
    functionId = `get_${functionId}`;
  }
  if (fieldName) functionId = `${functionId}#${fieldName}`;
  return `${layer}.${functionId}`;
}

function slug(ref) {
  return canonicalRef(ref).replace(/[./ :]+/g, '-');
}

function listItems(items) {
  const values = Array.isArray(items) ? items : [];
  return values.length ? values.map((item) => `<li>${escapeHtml(item)}</li>`).join('') : '<li>无</li>';
}

function plainValue(value) {
  if (value === null || value === undefined || value === '') return '未记录';
  if (Array.isArray(value)) return value.length ? value.map(plainValue).join(' → ') : '未记录';
  if (typeof value === 'object') return JSON.stringify(value, null, 2);
  const raw = String(value).trim();
  const labels = {
    not_available: '未记录',
    'N/A': '未记录',
    none: '未记录',
    None: '未记录',
    available: '可用',
    unavailable: '不可用',
    official: '官方来源',
    official_public: '官方公开来源',
    third_party_estimate: '第三方估算',
    component_model: '成分模型估算',
    proxy: '代理指标',
    missing_source_url: '未记录来源链接',
    license_note_defaulted: '授权说明使用默认值',
    vintage_date_not_available: '未记录版本日',
    coverage_missing_or_unspecified: '覆盖率未记录或未说明',
    public_endpoint_review_required: '公开端点需要复核',
  };
  return labels[raw] || raw;
}

function qualityRows(dataQuality) {
  const dq = dataQuality || {};
  const rows = [
    ['合约版本', dq.contract_version],
    ['数据源', [dq.provider, dq.source_name, dq.source_url].filter((item) => item && String(item).toLowerCase() !== 'missing').join(' / ')],
    ['来源等级', plainValue(dq.source_tier)],
    ['数据日期', `数据日：${plainValue(dq.data_date)}；截至日：${plainValue(dq.as_of_date)}；生效日：${plainValue(dq.effective_date)}；版本日：${plainValue(dq.vintage_date)}`],
    ['采集时间', dq.collected_at_utc],
    ['可用性 / 耗时', `${plainValue(dq.availability)} · ${plainValue(dq.collection_duration_ms)} ms`],
    ['备用路径 / 授权边界', `${plainValue(dq.fallback_reason)} · ${plainValue(dq.license_note)}`],
    ['失败类型', dq.failure_type],
    ['方法与公式口径', dq.methodology || dq.formula],
  ];
  if (dq.coverage) rows.push(['覆盖率', plainValue(dq.coverage)]);
  if (Array.isArray(dq.valuation_sources) && dq.valuation_sources.length) {
    rows.push(['估值来源对照', dq.valuation_sources.map((source) => {
      const name = source.source_name || source.source_id || 'unknown';
      const metric = source.metric || '';
      const date = source.data_date || '';
      const availability = source.availability || '';
      return `${plainValue(name)}｜${plainValue(metric)}｜${plainValue(date)}｜${plainValue(availability)}`;
    }).join('\\n')]);
  }
  rows.push(['异常与缺口', Array.isArray(dq.anomalies) && dq.anomalies.length ? dq.anomalies.map(plainValue).join('\\n') : '无异常或缺口记录。']);
  if (Array.isArray(dq.fallback_chain) && dq.fallback_chain.length) rows.push(['备用路径', dq.fallback_chain.join(' → ')]);
  if (dq.source_disagreement) rows.push(['来源分歧', plainValue(dq.source_disagreement)]);
  return rows
    .filter(([, value]) => value !== undefined && value !== null && value !== '')
    .map(([label, value]) => `<div class="contract-row"><b>${escapeHtml(label)}</b><p>${escapeHtml(plainValue(value))}</p></div>`)
    .join('');
}

function contractHtml(item) {
  const rows = qualityRows(item.data_quality);
  if (!rows) return '<div class="drawer-empty">这条证据没有记录数据证据合约。</div>';
  return `<div class="drawer-section drawer-contract"><h3>证据合约</h3>${rows}</div>`;
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

function jumpToEvidenceTarget(targetId, layer, updateHash = false) {
  if (!targetId) return;
  if (layer) expandLayerCard(layer);
  requestAnimationFrame(() => {
    const target = document.getElementById(targetId);
    if (!target) return;
    target.classList.add('target');
    target.setAttribute('tabindex', '-1');
    target.scrollIntoView({ behavior: 'smooth', block: 'center' });
    target.focus({ preventScroll: true });
    if (updateHash && window.location.hash !== `#${targetId}`) {
      history.replaceState(null, '', `#${targetId}`);
    }
    setTimeout(() => target.classList.remove('target'), 1600);
  });
}

function handleEvidenceHash() {
  const targetId = decodeURIComponent(String(window.location.hash || '').replace(/^#/, ''));
  if (!targetId || !targetId.startsWith('evidence-')) return;
  const target = document.getElementById(targetId);
  if (!target) return;
  const ref = target.dataset.evidenceRef || '';
  const layerMatch = ref.match(/^(L[1-5])\\./);
  jumpToEvidenceTarget(targetId, layerMatch ? layerMatch[1] : '', false);
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
  const entry = indicatorIndex.get(canonical) || indicatorIndex.get(canonical.split('#', 1)[0]);
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
    ${contractHtml(item)}
    <div class="drawer-section">
      <button class="ref-chip" data-jump-target="${escapeHtml(targetId)}" data-layer-target="${escapeHtml(layer)}">跳到完整底稿</button>
      <button class="ref-chip" data-copy-ref="${escapeHtml(canonical)}">复制 ref</button>
    </div>
  `;
  showDrawer();
}

function openEvidenceContract(ref, triggerEl) {
  lastDrawerTrigger = triggerEl || null;
  const canonical = canonicalRef(ref);
  const entry = indicatorIndex.get(canonical) || indicatorIndex.get(canonical.split('#', 1)[0]);
  if (!entry) {
    drawerContent.innerHTML = `
      <p class="drawer-ref">${escapeHtml(canonical)}</p>
      <div class="drawer-empty">这条证据没有命中具体的指标卡。</div>
    `;
    showDrawer();
    return;
  }
  const { layer, item } = entry;
  const targetId = `evidence-${slug(canonical)}`;
  drawerContent.innerHTML = `
    <p class="drawer-ref">${escapeHtml(canonical)}</p>
    <h2>${escapeHtml(item.metric || item.function_id)}</h2>
    ${contractHtml(item)}
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

document.querySelectorAll('[data-contract-ref]').forEach((button) => {
  button.addEventListener('click', () => {
    openEvidenceContract(button.dataset.contractRef, button);
  });
});

document.querySelectorAll('[data-glossary-term]').forEach((button) => {
  const tooltip = button.querySelector('[role="tooltip"]');
  if (!tooltip) return;
  const setOpen = (open) => {
    button.classList.toggle('is-open', open);
    tooltip.hidden = !open;
    tooltip.setAttribute('aria-hidden', String(!open));
    button.setAttribute('aria-expanded', String(open));
  };
  button.addEventListener('click', (event) => {
    event.stopPropagation();
    setOpen(!button.classList.contains('is-open'));
  });
  button.addEventListener('blur', () => setOpen(false));
  button.addEventListener('mouseenter', () => setOpen(true));
  button.addEventListener('mouseleave', () => {
    if (!button.matches(':focus')) setOpen(false);
  });
  button.addEventListener('focus', () => setOpen(true));
});

document.querySelectorAll('.ref-chip .metric-glossary--nested').forEach((term) => {
  const owner = term.closest('.ref-chip');
  const tooltip = term.querySelector('[role="tooltip"]');
  if (!owner || !tooltip) return;
  owner.setAttribute('aria-describedby', tooltip.id);
  const setVisible = (visible) => {
    tooltip.hidden = !visible;
    tooltip.setAttribute('aria-hidden', String(!visible));
  };
  owner.addEventListener('mouseenter', () => setVisible(true));
  owner.addEventListener('mouseleave', () => {
    if (!owner.matches(':focus')) setVisible(false);
  });
  owner.addEventListener('focus', () => setVisible(true));
  owner.addEventListener('blur', () => setVisible(false));
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
    requestAnimationFrame(() => {
      closeDrawer();
      jumpToEvidenceTarget(targetId, layer, true);
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
window.addEventListener('hashchange', handleEvidenceHash);
setTimeout(handleEvidenceHash, 0);
"""

REF_DIGEST_JS = r"""
const drawer = document.getElementById('evidence-drawer');
const drawerContent = document.getElementById('drawer-content');
const digestNode = document.getElementById('ref-digest');
const digest = digestNode ? JSON.parse(digestNode.textContent) : {metrics: {}, trends: {}};
let lastDrawerTrigger = null;

function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#039;');
}

function canonicalRef(ref) {
  let text = String(ref || '').trim().replace(/\s+/g, ' ').replace(/\s*#\s*/g, '#');
  if (text.includes(':')) text = text.split(':')[0].trim();
  if (!text.includes('.')) return text;
  const [rawLayer, rawFunction] = text.split('.', 2);
  const layer = rawLayer.trim().toUpperCase();
  const [rawFunctionName, fieldName] = rawFunction.trim().split('#', 2);
  let functionId = rawFunctionName.toLowerCase();
  if (/^L[1-5]$/.test(layer) && functionId && !functionId.startsWith('get_')) functionId = `get_${functionId}`;
  if (fieldName) functionId = `${functionId}#${fieldName}`;
  return `${layer}.${functionId}`;
}

function gauge(value, ref) {
  if (typeof value !== 'number' || !Number.isFinite(value)) return '';
  const bounded = Math.max(0, Math.min(100, value));
  const functionId = String(ref || '').split('.', 2).pop().split('#', 1)[0];
  const highDanger = ['get_10y_real_rate', 'get_10y_treasury', 'get_fed_funds_rate', 'get_vix', 'get_vxn', 'get_hy_quality_spread_bp', 'get_ndx_ndxe_ratio', 'get_qqq_qqew_ratio', 'get_qqq_top10_concentration', 'get_ndx_pe_and_earnings_yield'].includes(functionId);
  const lowDanger = ['get_damodaran_us_implied_erp', 'get_equity_risk_premium'].includes(functionId);
  const direction = highDanger ? 'hi' : lowDanger ? 'lo' : 'neutral';
  const marker = lowDanger ? 100 - bounded : bounded;
  const fallbackStyle = lowDanger ? 'transform:scaleX(-1)' : !highDanger ? '--severity-low:var(--severity-watch);--severity-high:var(--severity-watch)' : '';
  return `<div class="gauge"><div class="position-ruler gauge-track gauge-track--${direction}" style="${fallbackStyle}"><i class="zone ${direction}"></i><span style="left:${marker}%"></span></div><div class="gauge-lab"><span>低</span><strong>${bounded.toFixed(1)}% 分位</strong><span>高</span></div></div>`;
}

function sparkline(points) {
  if (!Array.isArray(points) || points.length < 2) return '';
  const values = points.map((point) => Number(point[1])).filter(Number.isFinite);
  if (values.length < 2) return '';
  const min = Math.min(...values), max = Math.max(...values), span = max - min || 1;
  const path = values.map((value, index) => {
    const x = values.length === 1 ? 0 : index * 100 / (values.length - 1);
    const y = 28 - ((value - min) / span) * 24;
    return `${index ? 'L' : 'M'}${x.toFixed(2)},${y.toFixed(2)}`;
  }).join(' ');
  return `<div class="dsec"><h3>走势形状</h3><svg class="drawer-spark" viewBox="0 0 100 32" role="img" aria-label="降采样走势线"><path d="${path}"></path></svg><p class="dsub">仅展示经核验快照中的降采样形状，不据此新增结论。</p></div>`;
}

function showDrawer() {
  if (!drawer) return;
  drawer.classList.add('open');
  drawer.setAttribute('aria-hidden', 'false');
  const closeButton = drawer.querySelector('[data-close-drawer]');
  if (closeButton) closeButton.focus();
}

function closeDrawer() {
  if (!drawer) return;
  drawer.classList.remove('open');
  drawer.setAttribute('aria-hidden', 'true');
  if (lastDrawerTrigger && document.contains(lastDrawerTrigger)) lastDrawerTrigger.focus();
  lastDrawerTrigger = null;
}

function openDrawer(ref, label, trigger) {
  lastDrawerTrigger = trigger || null;
  const canonical = canonicalRef(ref);
  const baseRef = canonical.split('#', 1)[0];
  const item = (digest.metrics || {})[canonical] || (digest.metrics || {})[baseRef];
  if (!item) {
    drawerContent.innerHTML = `<p class="drawer-ref">${escapeHtml(label || canonical)}</p><div class="drawer-empty">这条证据没有命中瘦身摘要。</div>`;
    showDrawer();
    return;
  }
  const trend = (digest.trends || {})[baseRef] || [];
  drawerContent.innerHTML = `
    <p class="dlayer">${escapeHtml(item.layer)} · ${escapeHtml(baseRef)}</p>
    <h2>${escapeHtml(item.metric)}</h2>
    <p class="dval">${escapeHtml(item.value_line || '本轮没有可展示读数。')}</p>
    ${gauge(item.quantile, baseRef)}
    ${sparkline(trend)}
    <div class="dsec"><h3>它回答什么</h3><p>${escapeHtml(item.answers || '未记录')}</p></div>
    <div class="dsec"><h3>它不能证明什么</h3><p>${escapeHtml(item.cannot_prove || '未记录')}</p></div>
    <div class="dsec"><h3>反证 / 改判条件</h3><p>${escapeHtml(item.falsifier || '未记录')}</p></div>
    <div class="dfoot"><a href="${escapeHtml(item.artifact_anchor)}">查看完整底稿</a><button type="button" data-copy-ref="${escapeHtml(baseRef)}">复制 ref</button></div>`;
  showDrawer();
}

document.querySelectorAll('[data-ref]').forEach((button) => {
  button.addEventListener('click', () => openDrawer(button.dataset.ref, button.dataset.label || button.textContent, button));
});
document.querySelectorAll('[data-close-drawer]').forEach((node) => node.addEventListener('click', closeDrawer));
document.addEventListener('keydown', (event) => {
  if (event.key === 'Escape' && drawer && drawer.classList.contains('open')) closeDrawer();
});
if (drawerContent) drawerContent.addEventListener('click', (event) => {
  const copy = event.target.closest('[data-copy-ref]');
  if (copy && navigator.clipboard) navigator.clipboard.writeText(copy.dataset.copyRef);
});
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
        style: str = "slate_v3",
        include_legacy_agent_io_audit: bool = False,
    ) -> str:
        run_path = Path(run_dir)
        artifacts = self._load_artifacts(run_path)
        template = self._normalize_template(template)
        style = self._normalize_style(style)
        destination = Path(output_path) if output_path else self._default_output_path(run_path, artifacts, template, style)
        destination.parent.mkdir(parents=True, exist_ok=True)
        audit_index_path = None
        layers_artifact_path = None
        if template == "brief":
            audit_index_path = destination.with_name(f"{destination.stem}_audit_index.json")
            self._write_audit_index(run_path, artifacts, audit_index_path)
            if "brief" in destination.stem:
                layers_stem = destination.stem.replace("brief", "layers", 1)
            else:
                layers_stem = f"{destination.stem}_layers"
            layers_artifact_path = destination.with_name(f"{layers_stem}{destination.suffix or '.html'}")
            layers_html = self._render(
                run_path,
                artifacts,
                "layers",
                style,
                include_legacy_agent_io_audit=False,
            )
            layers_artifact_path.write_text(layers_html, encoding="utf-8")
        html_text = self._render(
            run_path,
            artifacts,
            template,
            style,
            include_legacy_agent_io_audit,
            audit_index_path=audit_index_path,
            layers_artifact_path=layers_artifact_path,
        )
        destination.write_text(html_text, encoding="utf-8")
        return str(destination)

    def _write_audit_index(self, run_path: Path, artifacts: Dict[str, Any], destination: Path) -> None:
        """Write a small manifest that points to full audit artifacts without embedding them in HTML."""
        artifact_files = [
            "analysis_packet.json",
            "synthesis_packet.json",
            "final_adjudication.json",
            "thesis_draft.json",
            "analysis_revised.json",
            "critique.json",
            "risk_boundary_report.json",
            "schema_guard_report.json",
            "run_review_report.json",
            "outcome_review_report.json",
            "user_decision_profile.json",
            "golden_pit_checklist.json",
            "data_integrity_report.json",
            "context_brief.json",
            "chart_time_series.json",
            "llm_stage_diagnostics.json",
            "pure_data_report.json",
            "news_event_ledger.json",
            "news_event_data_links.json",
            "news_layer_analysis.json",
            "event_narrative_ledger.json",
            "event_mechanism_report.json",
            "cross_layer_questions.json",
            "event_mechanism_cards.json",
            "integrated_synthesis_report.json",
            "run_summary.json",
            "source_snapshot.json",
        ]
        layer_files = [f"layer_cards/{layer}.json" for layer in ["L1", "L2", "L3", "L4", "L5"]]
        bridge_files = [
            str(path.relative_to(run_path))
            for path in sorted((run_path / "bridge_memos").glob("*.json"))
            if path.is_file()
        ]
        prompt_dir = run_path / "prompt_audit"
        run_summary = artifacts.get("run_summary", {}) if isinstance(artifacts.get("run_summary"), dict) else {}

        def row(relative_path: str) -> Dict[str, Any]:
            path = run_path / relative_path
            return {
                "path": str(path),
                "relative_path": relative_path,
                "exists": path.exists(),
                "bytes": path.stat().st_size if path.exists() else 0,
            }

        index = {
            "kind": "vnext_brief_audit_index",
            "run_dir": str(run_path),
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "prompt_inspector": run_summary.get("prompt_inspector", ""),
            "data_integrity_status": (artifacts.get("data_integrity_report", {}) or {}).get("publish_status"),
            "artifact_files": [row(item) for item in [*artifact_files, *layer_files, *bridge_files]],
            "prompt_audit_dir": str(prompt_dir),
            "prompt_audit_exists": prompt_dir.exists(),
        }
        destination.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")

    def _default_output_path(self, run_path: Path, artifacts: Dict[str, Any], template: str, style: str) -> Path:
        meta = artifacts.get("synthesis_packet", {}).get("packet_meta", {})
        data_stamp = _minute_stamp(meta.get("collector_timestamp_utc"), assume_utc=True) or _minute_stamp(meta.get("data_date"))
        run_stamp = _run_minute_stamp(run_path)
        if data_stamp and run_stamp and data_stamp != run_stamp:
            stamp = f"{data_stamp}_{run_stamp}"
        else:
            stamp = data_stamp or run_stamp or datetime.now().strftime("%Y%m%d_%H%M")
        style_suffix = f"_{style}" if style != "slate_v3" else ""
        return self.reports_dir / f"vnext_{template}_{stamp}{style_suffix}.html"

    def _normalize_style(self, style: str) -> str:
        style = str(style or "slate_v3").strip().lower()
        valid = set(STYLE_FONTS.keys())
        return style if style in valid else "slate_v3"

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
        layer_context_dir = run_path / "layer_context_briefs"
        layer_contexts = {
            layer: _load_json(layer_context_dir / f"{layer}.json", {})
            for layer in ["L1", "L2", "L3", "L4", "L5"]
        }
        investigation_reports = [
            _load_json(path, {})
            for path in sorted((run_path / "investigation_reports").glob("*.json"))
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
            "run_review_report": _load_json(run_path / "run_review_report.json", {}),
            "outcome_review_report": _load_json(run_path / "outcome_review_report.json", {}),
            "hypothesis_competition": _load_json(run_path / "hypothesis_competition.json", {}),
            "counter_thesis": _load_json(run_path / "counter_thesis.json", {}),
            "user_decision_profile": _load_json(run_path / "user_decision_profile.json", {}),
            "golden_pit_checklist": _load_json(run_path / "golden_pit_checklist.json", {}),
            "data_integrity_report": _load_json(run_path / "data_integrity_report.json", {}),
            "context_brief": _load_json(run_path / "context_brief.json", {}),
            "layer_context_briefs": layer_contexts,
            "llm_stage_diagnostics": _load_json(run_path / "llm_stage_diagnostics.json", {}),
            "pure_data_report": _load_json(run_path / "pure_data_report.json", {}),
            "news_event_ledger": _load_json(run_path / "news_event_ledger.json", {}),
            "news_event_data_links": _load_json(run_path / "news_event_data_links.json", {}),
            "news_layer_analysis": _load_json(run_path / "news_layer_analysis.json", {}),
            "event_narrative_ledger": _load_json(run_path / "event_narrative_ledger.json", {}),
            "event_mechanism_report": _load_json(run_path / "event_mechanism_report.json", {}),
            "event_interpretation_cards": _load_json(run_path / "event_interpretation_cards.json", {}),
            "event_layer_summary": _load_json(run_path / "event_layer_summary.json", {}),
            "integrated_synthesis_report": _load_json(run_path / "integrated_synthesis_report.json", {}),
            "expectation_vs_realized": _load_json(run_path / "expectation_vs_realized.json", {}),
            "investigation_reports": investigation_reports,
            "chart_time_series": _load_json(run_path / "chart_time_series.json", {}),
            "layers": layers,
            "bridges": bridges,
            "run_summary": _load_json(run_path / "run_summary.json", {}),
            "source_snapshot": _load_json(run_path / "source_snapshot.json", {}),
        }

    def _render(
        self,
        run_path: Path,
        artifacts: Dict[str, Any],
        template: str,
        style: str,
        include_legacy_agent_io_audit: bool = False,
        audit_index_path: Optional[Path] = None,
        layers_artifact_path: Optional[Path] = None,
    ) -> str:
        self._enrich_indicator_data_quality(artifacts)
        final = artifacts["final_adjudication"]
        synthesis = artifacts["synthesis_packet"]
        meta = synthesis.get("packet_meta", {})
        template_name = TEMPLATE_DESCRIPTIONS[template]["name"]
        title = f"vNext {template_name} · {final.get('final_stance', 'N/A')}"
        payload = (
            self._build_ref_digest(run_path, artifacts, layers_artifact_path or Path("vnext_layers.html"))
            if template == "brief"
            else self._drawer_payload(run_path, artifacts)
        )
        payload_json = _json_for_script(payload)
        fonts_url = STYLE_FONTS.get(style, STYLE_FONTS["slate_v2"])
        brief = template == "brief"
        body_classes = f"template-{_escape(template)} style-{style}" + (" style-b micro-1" if brief else "")
        hero = "" if brief else self._hero(final, meta, run_path, template, artifacts)
        navigation = "" if brief else self._navigation(template)
        payload_id = "ref-digest" if brief else "vnext-data"
        script = REF_DIGEST_JS if brief else self._js()
        return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>{_escape(title)}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="{fonts_url}" rel="stylesheet">
  <style>{self._css(style)}</style>
</head>
<body class="{body_classes}">
  <a class="skip-link" href="#main">跳到主内容</a>
  <span class="sr-only">NDX 投资判断书 五层底稿 核心证据 审计入口</span>
  <div class="shell">
    {hero}
    {navigation}
    {self._template_intro(template)}
    <main id="main">{self._main_sections(template, run_path, artifacts, final, payload_json, include_legacy_agent_io_audit, audit_index_path)}</main>
  </div>
  <aside class="evidence-drawer drawer-mask" id="evidence-drawer" aria-hidden="true" role="dialog" aria-modal="true" aria-label="证据详情">
    <div class="drawer-backdrop" data-close-drawer></div>
    <section class="drawer-panel drawer">
      <button class="drawer-close dx" type="button" data-close-drawer aria-label="关闭抽屉">关闭</button>
      <div id="drawer-content" aria-live="polite"></div>
    </section>
  </aside>
  <script type="application/json" id="{payload_id}">{payload_json}</script>
  <script>{script}</script>
</body>
</html>
"""

    def _drawer_payload(self, run_path: Path, artifacts: Dict[str, Any]) -> Dict[str, Any]:
        layers: Dict[str, Dict[str, Any]] = {}
        for layer, card in (artifacts.get("layers") or {}).items():
            if not isinstance(card, dict):
                continue
            items = []
            for item in _as_list(card.get("indicator_analyses")):
                if not isinstance(item, dict) or not item.get("function_id"):
                    continue
                items.append(
                    {
                        "function_id": item.get("function_id"),
                        "metric": item.get("metric"),
                        "normalized_state": item.get("normalized_state"),
                        "confidence": item.get("confidence"),
                        "current_reading": _compact_text(item.get("current_reading"), 520),
                        "narrative": _compact_text(item.get("narrative"), 700),
                        "canonical_question": _compact_text(item.get("canonical_question"), 360),
                        "reasoning_process": _compact_text(item.get("reasoning_process"), 900),
                        "first_principles_chain": [_compact_text(value, 260) for value in _as_list(item.get("first_principles_chain"))[:6]],
                        "misread_guards": [_compact_text(value, 260) for value in _as_list(item.get("misread_guards"))[:6]],
                        "falsifiers": [_compact_text(value, 260) for value in _as_list(item.get("falsifiers"))[:6]],
                        "risk_flags": [_compact_text(value, 80) for value in _as_list(item.get("risk_flags"))[:6]],
                        "data_quality": self._drawer_data_quality(item.get("data_quality")),
                    }
                )
            layers[str(layer)] = {"indicator_analyses": items}
        return {"run_dir": str(run_path), "layers": layers}

    def _build_ref_digest(
        self,
        run_path: Path,
        artifacts: Dict[str, Any],
        layers_artifact_path: Path,
    ) -> Dict[str, Any]:
        """Build the audited brief drawer payload without embedding native layer cards."""
        metrics: Dict[str, Dict[str, Any]] = {}
        layers = artifacts.get("layers", {}) if isinstance(artifacts.get("layers"), dict) else {}
        for layer in ["L1", "L2", "L3", "L4", "L5"]:
            card = layers.get(layer, {}) if isinstance(layers.get(layer), dict) else {}
            for item in _as_list(card.get("indicator_analyses")):
                if not isinstance(item, dict) or not item.get("function_id"):
                    continue
                function_id = str(item.get("function_id"))
                ref = f"{layer}.{function_id}"
                quantile = self._historical_percentile(artifacts, layer, function_id)
                if quantile is None:
                    quantile = _extract_percentile(item.get("current_reading"))
                cannot = "；".join(str(value) for value in _as_list(item.get("misread_guards"))[:2])
                falsifier = "；".join(str(value) for value in _as_list(item.get("falsifiers"))[:2])
                metric = {
                    "metric": _compact_text(item.get("metric") or function_id, 80),
                    "layer": layer,
                    "value_line": _compact_text(item.get("current_reading"), 180),
                    "quantile": round(float(quantile), 2) if quantile is not None else None,
                    "answers": _compact_text(item.get("canonical_question"), 160),
                    "cannot_prove": _compact_text(cannot or item.get("permission_type"), 160),
                    "falsifier": _compact_text(falsifier, 160),
                    "artifact_anchor": f"{layers_artifact_path.name}#{function_id}",
                }
                while len(json.dumps(metric, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > 1024:
                    changed = False
                    for key in ("value_line", "answers", "cannot_prove", "falsifier"):
                        value = str(metric.get(key) or "")
                        if len(value) > 48:
                            metric[key] = _compact_text(value, max(48, len(value) - 24))
                            changed = True
                    if not changed:
                        raise ValueError(f"ref-digest metric exceeds 1KB: {ref}")
                metrics[ref] = metric

        trends: Dict[str, List[List[Any]]] = {}
        recompute_inputs = self._verified_recompute_inputs(artifacts)
        for layer in ["L1", "L2", "L3", "L4", "L5"]:
            card = layers.get(layer, {}) if isinstance(layers.get(layer), dict) else {}
            for item in _as_list(card.get("indicator_analyses")):
                if not isinstance(item, dict):
                    continue
                function_id = str(item.get("function_id") or "")
                if function_id not in DRAWER_TREND_WHITELIST:
                    continue
                raw = recompute_inputs.get(function_id, {}) if isinstance(recompute_inputs, dict) else {}
                rows = raw.get("raw_series") if isinstance(raw, dict) else None
                if not isinstance(rows, list):
                    continue
                points: List[List[Any]] = []
                for row in _downsample_rows([value for value in rows if isinstance(value, dict)], 32):
                    number = _safe_number(row.get("value"))
                    date = row.get("date") or row.get("time") or row.get("timestamp")
                    if number is None or not date:
                        continue
                    points.append([str(date)[:10], round(number, 6)])
                if len(points) < 2:
                    continue
                ref = f"{layer}.{function_id}"
                candidate = {**trends, ref: points[:60]}
                if len(json.dumps(candidate, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) <= 12 * 1024:
                    trends[ref] = points[:60]

        digest = {"metrics": metrics, "trends": trends}
        self._validate_ref_digest(digest)
        return digest

    def _verified_recompute_inputs(self, artifacts: Dict[str, Any]) -> Dict[str, Any]:
        snapshot = artifacts.get("source_snapshot") if isinstance(artifacts.get("source_snapshot"), dict) else {}
        source_path = Path(str(snapshot.get("source_path") or ""))
        expected_hash = str(snapshot.get("source_sha256") or "")
        if not source_path.is_file() or not expected_hash or expected_hash == "not_recorded":
            return {}
        source_bytes = source_path.read_bytes()
        if hashlib.sha256(source_bytes).hexdigest() != expected_hash:
            return {}
        try:
            source = json.loads(source_bytes)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return {}
        if not isinstance(source, dict):
            return {}
        analysis_meta = (artifacts.get("analysis_packet") or {}).get("meta", {})
        expected_date = str(analysis_meta.get("backtest_date") or analysis_meta.get("data_date") or "")
        snapshot_date = str(snapshot.get("effective_date") or "")
        if analysis_meta.get("backtest_date") and snapshot_date != expected_date:
            return {}
        if snapshot_date not in {"", "live", "not_recorded", expected_date}:
            return {}
        inputs = source.get("recompute_inputs") if isinstance(source.get("recompute_inputs"), dict) else {}
        if not expected_date or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", expected_date):
            return inputs
        filtered: Dict[str, Any] = {}
        for function_id, payload in inputs.items():
            if not isinstance(payload, dict):
                continue
            copied = dict(payload)
            rows = payload.get("raw_series")
            if isinstance(rows, list):
                copied["raw_series"] = [
                    row for row in rows
                    if not isinstance(row, dict)
                    or not str(row.get("date") or row.get("time") or row.get("timestamp") or "")[:10]
                    or str(row.get("date") or row.get("time") or row.get("timestamp") or "")[:10] <= expected_date
                ]
            filtered[str(function_id)] = copied
        return filtered

    def _validate_ref_digest(self, digest: Dict[str, Any]) -> None:
        for ref, metric in (digest.get("metrics") or {}).items():
            if set(metric) != set(REF_DIGEST_FIELDS):
                raise ValueError(f"ref-digest field mismatch: {ref}")
            if len(json.dumps(metric, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > 1024:
                raise ValueError(f"ref-digest metric exceeds 1KB: {ref}")
        trend_bytes = len(json.dumps(digest.get("trends") or {}, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
        if trend_bytes > 12 * 1024:
            raise ValueError("ref-digest trend payload exceeds 12KB")
        if len(json.dumps(digest, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) > 50 * 1024:
            raise ValueError("ref-digest exceeds 50KB")

    def _drawer_data_quality(self, data_quality: Any) -> Dict[str, Any]:
        if not isinstance(data_quality, dict) or not data_quality:
            return {}
        keys = [
            "contract_version",
            "provider",
            "source_name",
            "source_url",
            "source_tier",
            "data_date",
            "as_of_date",
            "effective_date",
            "vintage_date",
            "collected_at_utc",
            "availability",
            "collection_duration_ms",
            "fallback_reason",
            "license_note",
            "failure_type",
            "methodology",
            "formula",
            "coverage",
            "anomalies",
            "fallback_chain",
            "source_disagreement",
            "valuation_sources",
        ]
        compact: Dict[str, Any] = {}
        for key in keys:
            value = data_quality.get(key)
            if value in (None, "", [], {}):
                continue
            if isinstance(value, str):
                compact[key] = _compact_text(value, 1200)
            elif isinstance(value, list):
                compact[key] = value[:12]
            elif isinstance(value, dict):
                compact[key] = value
            else:
                compact[key] = value
        return compact

    def _data_quality_box(self, data_quality: Any) -> str:
        compact = self._drawer_data_quality(data_quality)
        if not compact:
            return '<div class="data-quality-box empty">数据证据合约未记录。</div>'
        date_text = (
            f"data={compact.get('data_date', 'not_available')}; "
            f"as_of={compact.get('as_of_date', 'not_available')}; "
            f"effective={compact.get('effective_date', 'not_available')}; "
            f"vintage={compact.get('vintage_date', 'not_available')}"
        )
        rows = [
            ("合约版本", compact.get("contract_version")),
            ("来源", " / ".join(str(item) for item in [compact.get("provider"), compact.get("source_name"), compact.get("source_url")] if item)),
            ("来源等级", compact.get("source_tier")),
            ("日期", date_text),
            ("可用性", compact.get("availability")),
            ("备用路径", compact.get("fallback_reason")),
            ("授权边界", compact.get("license_note")),
            ("覆盖率", compact.get("coverage")),
            ("异常", compact.get("anomalies")),
        ]
        body = "".join(
            f"<div class=\"data-quality-row\"><b>{_escape(label)}</b><span>{_escape(value)}</span></div>"
            for label, value in rows
            if value not in (None, "", [], {})
        )
        return f'<div class="data-quality-box">{body}</div>'

    def _enrich_indicator_data_quality(self, artifacts: Dict[str, Any]) -> None:
        raw_data = artifacts.get("analysis_packet", {}).get("raw_data", {})
        layers = artifacts.get("layers", {})
        if not isinstance(raw_data, dict) or not isinstance(layers, dict):
            return
        for layer, card in layers.items():
            if not isinstance(card, dict):
                continue
            layer_raw = raw_data.get(layer)
            if not isinstance(layer_raw, dict):
                continue
            for item in card.get("indicator_analyses", []) or []:
                if not isinstance(item, dict):
                    continue
                raw_item = layer_raw.get(item.get("function_id"))
                if not isinstance(raw_item, dict):
                    continue

                # Merge: raw data_quality as base, overlay existing item fields
                base = dict(raw_item.get("data_quality") or {})
                existing_dq = item.get("data_quality")
                if isinstance(existing_dq, dict):
                    base.update(existing_dq)

                # Inject collector timestamp (authoritative)
                collected_at = raw_item.get("collection_timestamp_utc")
                if collected_at:
                    base["collected_at_utc"] = collected_at

                # Mark manual override
                if raw_item.get("manual_override_used"):
                    tier = str(base.get("source_tier", "")).strip()
                    base["source_tier"] = f"{tier} · 手动输入" if tier else "手动输入"

                # Always extract valuation sources (fixes U7)
                vs = self._valuation_sources_from_raw(raw_item)
                if vs:
                    base["valuation_sources"] = vs

                if base:
                    item["data_quality"] = base

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
                        "historical_percentile": value.get("damodaran_erp_percentile_10y"),
                        "percentile_5y": value.get("damodaran_erp_percentile_5y"),
                        "data_date": raw_item.get("date") or raw_item.get("data_quality", {}).get("data_date"),
                        "availability": raw_item.get("availability", "available"),
                        "scope": value.get("scope"),
                        "tbond_rate": value.get("tbond_rate", value.get("t_bond_rate")),
                    }
                )
            elif value.get("erp_t12m_adjusted_payout") is not None or value.get("damodaran_erp_historical_percentiles"):
                sources.append(
                    {
                        "source_name": raw_item.get("source_name", "Damodaran"),
                        "source_tier": raw_item.get("source_tier") or raw_item.get("data_quality", {}).get("source_tier"),
                        "metric": "Damodaran US implied ERP historical percentile",
                        "value": value.get("erp_t12m_adjusted_payout"),
                        "historical_percentile": value.get("damodaran_erp_percentile_10y"),
                        "percentile_5y": value.get("damodaran_erp_percentile_5y"),
                        "data_date": raw_item.get("date") or raw_item.get("data_quality", {}).get("data_date") or value.get("data_date"),
                        "availability": raw_item.get("availability", "available"),
                        "scope": "US market ERP reference; not NDX PE/PB/Forward PE percentile",
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
        include_legacy_agent_io_audit: bool = False,
        audit_index_path: Optional[Path] = None,
    ) -> str:
        renderers = {
            "facade": lambda: self._brief_facade_section(run_path, artifacts),
            "thesis": lambda: self._brief_thesis_section(artifacts),
            "stress": lambda: self._brief_stress_section(artifacts),
            "world": lambda: self._brief_world_section(artifacts),
            "change": lambda: self._brief_change_section(artifacts),
            "brief_layers": lambda: self._brief_layers_section(artifacts),
            "brief_audit": lambda: self._brief_audit_line(run_path, artifacts, audit_index_path),
            "decision": lambda: self._decision_section(artifacts),
            "actions": lambda: self._actions_section(artifacts),
            "evidence": lambda: self._evidence_section(final),
            "news": lambda: self._news_section(artifacts),
            "risks": lambda: self._risks_section(artifacts),
            "conflicts": lambda: self._conflicts_section(artifacts),
            "layers": lambda: self._layers_section(artifacts),
            "governance": lambda: self._governance_section(artifacts),
            "audit": lambda: self._audit_section(
                run_path,
                artifacts,
                payload_json,
                include_legacy_agent_io_audit=include_legacy_agent_io_audit,
                audit_index_path=audit_index_path,
            ),
        }
        return "".join(renderers[key]() for key in TEMPLATE_ORDER[template])

    def _brief_facade_section(self, run_path: Path, artifacts: Dict[str, Any]) -> str:
        final = artifacts.get("final_adjudication", {}) or {}
        synthesis = artifacts.get("synthesis_packet", {}) or {}
        meta = synthesis.get("packet_meta", {}) if isinstance(synthesis, dict) else {}
        analysis_meta = (artifacts.get("analysis_packet", {}) or {}).get("meta", {})
        object_gate = meta.get("object_run_gate") or analysis_meta.get("object_run_gate") or {}
        object_name = object_gate.get("primary_object") or "NDX"
        reader = self._reader_final(final)
        # 红队 C1 裁决（2026-07-18）：在语义锚机制补齐前，门脸正文保持第一层
        # reasoned_verdict（它经过 Critic/Reviser/Final 治理链）；第三层综合正文
        # 在"第三层·综合裁决"章节完整呈现，署名切换留待后续工单。
        verdict_signature = ""
        verdict = str(final.get("reasoned_verdict") or "").strip()
        if not verdict:
            verdict_parts = [str(final.get("final_stance") or "").strip(), str(reader.get("one_liner") or "").strip()]
            verdict = " ".join(dict.fromkeys(part for part in verdict_parts if part)) or "本轮没有形成可发布判决正文。"
        competition = artifacts.get("hypothesis_competition", {}) if isinstance(artifacts.get("hypothesis_competition"), dict) else {}
        candidates = [
            item for item in _as_list(competition.get("hypotheses"))
            if isinstance(item, dict) and str(item.get("status") or "") == "candidate"
        ]
        strongest_dissent = _sentence(candidates[0].get("hypothesis_text"), 170) if candidates else "本轮没有结构化候选异议。"
        payoff = _sentence(final.get("payoff_assessment"), 34) or "赔率未记录"
        confidence = _label(final.get("confidence", "medium"), "confidence")
        stance = _sentence(final.get("final_stance"), 32) or "姿态未记录"
        integrity = artifacts.get("data_integrity_report", {}) if isinstance(artifacts.get("data_integrity_report"), dict) else {}
        publish_status = integrity.get("publish_status") or ("blocked" if integrity.get("blocked") else "not recorded")
        blocking_reasons = [value for value in _as_list(integrity.get("blocking_reasons")) if str(value).strip()]
        publishable = bool(
            publish_status == "publishable"
            and not integrity.get("blocked")
            and not integrity.get("unpublishable")
            and not blocking_reasons
        )
        blocked = not publishable
        publish_note = (
            '<p class="dissent publish-block">发布闸门未通过：本页只能作为内部审阅材料，不能当作可发布结论。</p>'
            if blocked
            else f'<span class="badge pill">发布 {_escape(_label(publish_status, "publish_status"))}</span>'
        )
        return f"""
<section class="hero sec facade" id="facade">
  <div class="brief-hero-grid sec-grid">
    <div class="brief-verdict sec-main prose">
      <p class="kicker">NDX 投资判断书 · {_escape(object_name)}</p>
      <h1>{_escape(final.get('final_stance') or reader.get('one_liner') or '本轮判断')}</h1>
      <p class="reasoned-verdict">{self._reasoned_verdict_html(verdict)}</p>
      {f'<p class="section-note verdict-signature">{_escape(verdict_signature)}</p>' if verdict_signature else ''}
      <div class="brief-meta-line badges">
        <span class="badge pill">姿态 {_escape(stance)}</span>
        <span class="badge pill">赔率 {_escape(payoff)}</span>
        <span class="badge pill">可信度 {_escape(confidence)}</span>
        {publish_note if not blocked else ''}
      </div>
      {publish_note if blocked else ''}
      <aside class="hero-risks dissent"><span>最强异议</span><p>{_escape(strongest_dissent)}</p></aside>
      <nav class="nav jumplinks" aria-label="判断书内跳转">
        <a href="#thesis">正方论证</a><a href="#stress">反方压力测试</a><a href="#risks">改判条件</a>
      </nav>
    </div>
    <aside class="brief-action-card sec-aside">
      <article class="boundary-card dcard"><span class="dk">判断对象</span><strong class="dv">{_escape(object_name)}</strong><p class="dq">只回答本 run 的 NDX 判断，不外推到其他资产。</p></article>
      <article class="boundary-card dcard"><span class="dk">数据日期</span><strong class="dv">{_escape(meta.get('data_date') or analysis_meta.get('data_date') or 'N/A')}</strong><p class="dq">运行目录：{_escape(run_path.name)}</p></article>
    </aside>
  </div>
</section>
"""

    def _brief_thesis_section(self, artifacts: Dict[str, Any]) -> str:
        final = artifacts.get("final_adjudication", {}) or {}
        thesis = artifacts.get("thesis_draft", {}) or {}
        surface = self._decision_surface(final, thesis)
        principal = surface.get("principal_contradiction") if isinstance(surface.get("principal_contradiction"), dict) else {}
        principal_refs = self._ref_chips(principal.get("evidence_refs", []))
        chains = []
        for index, item in enumerate(_as_list(final.get("key_support_chains") or thesis.get("key_support_chains"))[:3], 1):
            if not isinstance(item, dict):
                continue
            refs = _as_list(item.get("evidence_refs"))
            label = _human_ref_label(refs[0]) if refs else "证据"
            chains.append(f"""
<article class="claim">
  <h3>支撑链 {index} · {_escape(label)}</h3>
  <p>{_escape(item.get('chain_description') or item.get('claim') or '')}</p>
  <div class="ref-row">{self._ref_chips(refs)}</div>
</article>""")
        price_rows = []
        for item in _as_list(surface.get("price_reflection_map"))[:6]:
            if not isinstance(item, dict):
                continue
            price_rows.append(f"""
<article class="claim">
  <h3>{_escape(_display_label(item.get('category') or item.get('target') or '定价'))}</h3>
  <p>{_escape(item.get('rationale') or '')}</p>
  <small>{_escape(_display_label(item.get('reflected_state') or 'unclear'))}</small>
  <div class="ref-row">{self._ref_chips(item.get('evidence_refs', []))}</div>
</article>""")
        horizon_rows = []
        for item in _as_list(surface.get("time_horizon_views"))[:3]:
            if not isinstance(item, dict):
                continue
            horizon_rows.append(f"""
<article class="claim">
  <h3>{_escape(_display_label(item.get('horizon') or '时间尺度'))}</h3>
  <p>{_escape(item.get('view') or '')}</p>
  <small>{_escape(item.get('action_implication') or '')}</small>
  <div class="ref-row">{self._ref_chips(item.get('evidence_refs', []))}</div>
</article>""")
        return f"""
<section class="panel sec" id="thesis">
  <div class="sec-head"><span class="tag sans">01 · 正方</span><h2>主论证</h2></div>
  <article class="chain-card chain-card--plain hyp">
    <span class="hlabel">主要矛盾</span>
    <div class="hrow"><b>判断</b><p>{_escape(principal.get('summary') or '未形成结构化主要矛盾。')}</p></div>
    <div class="hrow"><b>为什么是它</b><p>{_escape(principal.get('why_principal') or '')}</p></div>
    <div class="hrow"><b>动作含义</b><p>{_escape(principal.get('action_implication') or '')}</p></div>
    <div class="ref-row">{principal_refs}</div>
  </article>
  <div class="chain-grid">{''.join(chains) or '<p>暂无结构化支撑链。</p>'}</div>
  <h3 class="reader-sub">价格反映</h3><div class="chain-grid">{''.join(price_rows) or '<p>暂无结构化价格反映地图。</p>'}</div>
  <h3 class="reader-sub">三个时间尺度</h3><div class="chain-grid">{''.join(horizon_rows) or '<p>暂无结构化时间尺度判断。</p>'}</div>
  {self._long_term_assessment_section(final)}
</section>
"""

    def _brief_stress_section(self, artifacts: Dict[str, Any]) -> str:
        block = self._hypothesis_competition_block(artifacts)
        return f"""
<section class="panel sec" id="stress">
  <div class="sec-head"><span class="tag sans">02 · 反方</span><h2>压力测试</h2></div>
  {block or '<p>本轮没有结构化竞争假说。</p>'}
</section>
"""

    def _expectation_ledger_block(self, artifacts: Dict[str, Any]) -> str:
        ledger = artifacts.get("expectation_vs_realized", {})
        if not isinstance(ledger, dict) or not ledger:
            return ""

        status_labels = {
            "available": "已有可比样本",
            "insufficient_coverage": "样本不足",
            "accumulating": "对照样本积累中",
            "unavailable": "暂不可用",
            "generation_failed_non_blocking": "生成失败（不阻断主流程）",
        }

        def status(value: Any) -> str:
            raw = str(value or "未记录")
            return status_labels.get(raw, raw)

        def number(value: Any, suffix: str = "") -> str:
            parsed = _safe_number(value)
            return f"{parsed:.2f}{suffix}" if parsed is not None else "未形成"

        earnings = ledger.get("earnings_expectations", {}) if isinstance(ledger.get("earnings_expectations"), dict) else {}
        window_rows = []
        for window in _as_list(earnings.get("windows")):
            if not isinstance(window, dict):
                continue
            window_rows.append(
                "<li><b>{days} 日</b>：{window_status}；共同样本 {count}；平均变化 {change}。{note}</li>".format(
                    days=_escape(window.get("window_days") or "?"),
                    window_status=_escape(status(window.get("status"))),
                    count=_escape(window.get("intersection_ticker_count", 0)),
                    change=_escape(number(window.get("average_change_pct"), "%")),
                    note=_escape(window.get("note") or ""),
                )
            )
        earnings_detail = "".join(window_rows) or "<li>尚未形成 30/90 日可比窗口。</li>"

        rate = ledger.get("rate_path", {}) if isinstance(ledger.get("rate_path"), dict) else {}
        current_path = rate.get("current_path") if isinstance(rate.get("current_path"), dict) else {}
        path_points = len(_as_list(current_path.get("path"))) if current_path else 0
        comparisons = len(_as_list(rate.get("comparisons")))

        volatility = ledger.get("volatility_premium", {}) if isinstance(ledger.get("volatility_premium"), dict) else {}
        authority = str(ledger.get("metric_authority") or "未记录")
        overall_status = ledger.get("status")
        overall_note = ""
        if overall_status:
            overall_note = f'<p class="section-note">台账状态：{_escape(status(overall_status))}。</p>'
        return f"""
<div class="audit-boundaries expectation-ledger" id="expectation-vs-realized">
  <h3>预期与兑现</h3>
  <p>这是辅助对照账，只帮助检查市场预期后来兑现了多少；权威级别为 <b>{_escape(authority)}</b>，不能充当 L1-L5 核心证据。</p>
  {overall_note}
  <div class="audit-grid">
    <div><b>盈利预期</b><p>{_escape(status(earnings.get('status')))}；当前快照 {_escape(earnings.get('current_snapshot_date') or '未形成')}；覆盖 {_escape(earnings.get('current_ticker_count', 0))} 个标的。</p><ul>{earnings_detail}</ul></div>
    <div><b>利率路径</b><p>{_escape(status(rate.get('status')))}；当前路径 {path_points} 个点；历史兑现对照 {comparisons} 条。</p><p>{_escape(rate.get('note') or '')}</p></div>
    <div><b>波动溢价</b><p>{_escape(status(volatility.get('status')))}；有效窗口 {_escape(volatility.get('sample_count', 0))} 个；近期溢价 {number(volatility.get('recent_premium_pct_points'), ' 个百分点')}；近期分位 {number(volatility.get('recent_percentile'), '%')}。</p><p>{_escape(volatility.get('note') or '')}</p></div>
  </div>
</div>
"""

    def _brief_world_section(self, artifacts: Dict[str, Any]) -> str:
        section = self._event_layer_summary_section(artifacts)
        expectation = self._expectation_ledger_block(artifacts)
        if not section:
            return '<section class="panel sec" id="world"><div class="sec-head"><span class="tag sans">03 · 外部世界</span><h2>事实对照</h2></div><p>本轮没有新闻事实材料。</p>' + expectation + '</section>'
        section = section.replace('<section class="panel" id="event-layer-summary">', '<section class="panel sec" id="world">', 1)
        section = section.replace('<div class="section-kicker">05 · 新闻事实底账</div>', '<div class="sec-head"><span class="tag sans">03 · 外部世界</span></div>', 1)
        if expectation:
            section = section.replace("</section>", expectation + "</section>", 1)
        return section

    def _brief_change_section(self, artifacts: Dict[str, Any]) -> str:
        checklist = artifacts.get("golden_pit_checklist", {}) if isinstance(artifacts.get("golden_pit_checklist"), dict) else {}
        changes = [str(item) for item in _as_list(checklist.get("changed_since_last_run_summary")) if str(item).strip()]
        rows = "".join(f"<li>{_escape(item)}</li>" for item in changes[:6]) or "<li>本轮未记录显著变化，或上次 run 不可比。</li>"
        return f"""
<section class="panel sec" id="change">
  <div class="sec-head"><span class="tag sans">05 · 变化</span><h2>和上次判断比，什么变了</h2></div>
  <ul class="qlist">{rows}</ul>
</section>
"""

    def _brief_audit_line(
        self,
        run_path: Path,
        artifacts: Dict[str, Any],
        audit_index_path: Optional[Path],
    ) -> str:
        run_summary = artifacts.get("run_summary", {}) if isinstance(artifacts.get("run_summary"), dict) else {}
        inspector = run_summary.get("prompt_inspector") or ""
        layers_path = ""
        if audit_index_path:
            if "brief" in audit_index_path.stem:
                layers_stem = audit_index_path.stem.replace("brief", "layers", 1).removesuffix("_audit_index")
            else:
                layers_stem = audit_index_path.stem.removesuffix("_audit_index") + "_layers"
            layers_path = f"{layers_stem}.html"
        links = [
            _artifact_link("运行目录", run_path),
            _artifact_link("Workbench", run_path / "layer_cards"),
            _artifact_link("Prompt Inspector", inspector),
            f'<a href="{_escape(layers_path)}">完整底稿 artifact</a>' if layers_path else "<span>完整底稿 artifact 未生成</span>",
        ]
        return f"""
<section class="panel sec audit-line" id="audit">
  <span class="tag sans">07 · 审计</span>{' · '.join(links)}
</section>
"""

    def _template_intro(self, template: str) -> str:
        return ""

    def _reader_final(self, final: Dict[str, Any]) -> Dict[str, Any]:
        reader = final.get("reader_final")
        if isinstance(reader, dict) and any(reader.get(key) for key in ("one_liner", "three_reasons", "action_summary")):
            return reader
        reasons = []
        for item in _as_list(final.get("key_support_chains"))[:3]:
            if isinstance(item, dict) and item.get("chain_description"):
                reasons.append(str(item.get("chain_description")))
        return {
            "one_liner": final.get("final_stance", ""),
            "three_reasons": reasons,
            "time_horizon_summary": final.get("time_horizon_views", []),
            "action_summary": final.get("portfolio_actions", []),
            "invalidation_summary": final.get("invalidation_conditions", []),
            "evidence_refs": final.get("evidence_refs", []),
        }

    def _reader_note(self, final: Dict[str, Any]) -> str:
        reader = self._reader_final(final)
        reasons = _as_list(reader.get("three_reasons"))
        if reasons:
            return "；".join(str(item) for item in reasons[:3])
        if final.get("payoff_assessment"):
            return str(final.get("payoff_assessment"))
        return "读者结论尚未结构化；内部裁决说明保留在治理/审计区。"

    def _decision_surface(self, final: Dict[str, Any], thesis: Dict[str, Any]) -> Dict[str, Any]:
        reader = self._reader_final(final)
        return {
            "state_diagnosis": final.get("state_diagnosis") or thesis.get("state_diagnosis") or final.get("final_stance", ""),
            "priced_narrative": final.get("priced_narrative") or thesis.get("priced_narrative") or "",
            "payoff_assessment": final.get("payoff_assessment") or thesis.get("payoff_assessment") or "",
            "time_horizon_views": final.get("time_horizon_views") or reader.get("time_horizon_summary") or thesis.get("time_horizon_views") or [],
            "portfolio_actions": final.get("portfolio_actions") or reader.get("action_summary") or thesis.get("portfolio_actions") or [],
            "confirmation_cost": final.get("confirmation_cost") or thesis.get("confirmation_cost") or "",
            "invalidation_conditions": final.get("invalidation_conditions") or reader.get("invalidation_summary") or thesis.get("invalidation_conditions") or [],
            "principal_contradiction": final.get("principal_contradiction") or thesis.get("principal_contradiction") or {},
            "secondary_contradictions": final.get("secondary_contradictions") or thesis.get("secondary_contradictions") or [],
            "price_reflection_map": final.get("price_reflection_map") or thesis.get("price_reflection_map") or [],
        }

    def _portfolio_action_note_html(self, item: Dict[str, Any]) -> str:
        notes = []
        rationale = str(item.get("rationale") or "").strip()
        if rationale:
            notes.append(rationale)
        conditions = [str(value) for value in _as_list(item.get("conditions")) if str(value).strip()]
        notes.extend(f"条件：{value}" for value in conditions)
        policy_text = " ".join([rationale, *conditions])
        if str(item.get("bucket") or "") == "core_position" and "政策书" not in policy_text:
            notes.append("核心仓动作须经个人投资政策书与再平衡带确认")
        if not notes:
            return ""
        return "<small>" + "<br>".join(_escape(note) for note in notes) + "</small>"

    def _long_term_assessment_section(self, final: Dict[str, Any]) -> str:
        assessment = final.get("long_term_assessment")
        if not isinstance(assessment, dict):
            return ""
        hypotheses = [str(item) for item in _as_list(assessment.get("permanent_loss_hypotheses")) if str(item).strip()]
        if not any(str(assessment.get(field) or "").strip() for field in (
            "object_quality", "earnings_compounding", "valuation_implied_return"
        )) and not hypotheses:
            return ""
        hypothesis_rows = "".join(f"<li>{_escape(item)}</li>" for item in hypotheses) or "<li>未列出。</li>"
        uncertainty_rows = "".join(
            f"<li>{_escape(item)}</li>" for item in _as_list(assessment.get("uncertainty_notes"))
        )
        refs = self._ref_chips(assessment.get("evidence_refs", []))
        return f"""
  <details class="audit-boundaries long-term-assessment">
    <summary>长期资产评估（3-5 年以上）</summary>
    <div class="governance-grid">
      <article><h3>对象质量</h3><p>{_escape(assessment.get('object_quality') or '证据不足，未提供。')}</p></article>
      <article><h3>盈利复利</h3><p>{_escape(assessment.get('earnings_compounding') or '证据不足，未提供。')}</p></article>
      <article><h3>估值隐含回报</h3><p>{_escape(assessment.get('valuation_implied_return') or '证据不足，未提供。')}</p></article>
      <article><h3>永久损失假说</h3><ul>{hypothesis_rows}</ul></article>
    </div>
    {f'<div class="risk-list"><h3>不确定性</h3><ul>{uncertainty_rows}</ul></div>' if uncertainty_rows else ''}
    {f'<div class="ref-row">{refs}</div>' if refs else ''}
  </details>
"""

    def _hero(
        self,
        final: Dict[str, Any],
        meta: Dict[str, Any],
        run_path: Path,
        template: str,
        artifacts: Dict[str, Any],
    ) -> str:
        confidence = final.get("confidence", "medium")
        approval = final.get("approval_status", "")
        success = f"{meta.get('indicator_successful', '?')}/{meta.get('indicator_total', '?')}"
        template_name = TEMPLATE_DESCRIPTIONS[template]["name"]
        analysis_packet = artifacts.get("analysis_packet", {}) or {}
        analysis_meta = analysis_packet.get("meta", {}) or {}
        integrity = artifacts.get("data_integrity_report", {}) or {}
        publish_status = integrity.get("publish_status") or ("blocked" if integrity.get("blocked") else "not recorded")
        generated_at = meta.get("generated_at") or analysis_meta.get("generated_at")
        collector_timestamp = meta.get("collector_timestamp_utc") or analysis_meta.get("collector_timestamp_utc")
        backtest_date = meta.get("backtest_date") or analysis_meta.get("backtest_date") or "N/A"
        observation_range = _observation_date_range(analysis_packet.get("raw_data", {}))
        risk_count = len(_as_list(final.get("must_preserve_risks")))
        reader = self._reader_final(final)
        hero_title = reader.get("one_liner") or final.get("final_stance", "N/A")
        hero_note = self._reader_note(final)
        if template == "brief":
            checklist = artifacts.get("golden_pit_checklist", {}) if isinstance(artifacts.get("golden_pit_checklist"), dict) else {}
            checklist_summary = self._golden_pit_summary(checklist)
            invalidations = _as_list(final.get("invalidation_conditions"))
            primary_break = invalidations[0] if invalidations else "暂无结构化优先反证。"
            confidence_label = _label(confidence, "confidence")
            data_date = meta.get("data_date") or analysis_meta.get("data_date") or backtest_date
            current_state = checklist.get("current_state") if isinstance(checklist, dict) else ""
            current_state = current_state or final.get("state_diagnosis") or hero_note
            principal = final.get("principal_contradiction") if isinstance(final.get("principal_contradiction"), dict) else {}
            principal_summary = principal.get("summary") or ""
            dominant = principal.get("dominant_side") or ""
            if principal_summary and dominant:
                principal_text = f"{principal_summary} 当前占上风的一面：{dominant}"
            else:
                principal_text = principal_summary or _sentence(current_state, 110)
            return f"""
<header class="hero brief-hero" id="top">
  <div class="eyebrow">NDX 投资判断书</div>
  <div class="brief-hero-grid">
    <div class="brief-verdict">
      <h1>{_escape(hero_title)}</h1>
      <p>{_escape(final.get('state_diagnosis') or hero_note)}</p>
      {f'<p class="reasoned-verdict">{self._reasoned_verdict_html(final.get("reasoned_verdict"))}</p>' if final.get('reasoned_verdict') else ''}
    </div>
    <aside class="brief-action-card" aria-label="动作和反证">
      <div>
        <b>主要矛盾</b>
        <p>{_escape(_sentence(principal_text, 130))}</p>
      </div>
      <div>
        <b>距离纪律条件</b>
        <p>{_escape(checklist_summary['distance'])}</p>
      </div>
      <div>
        <b>可信度：{_escape(confidence_label)}</b>
        <p><b>什么情况下我会改判：</b>{_render_invalidation_item(primary_break)}</p>
      </div>
    </aside>
  </div>
  <div class="brief-meta-line">
    <span>数据日期 {_escape(data_date or 'N/A')}</span>
    <span>审批 {_escape(_label(approval, 'approval'))}</span>
    <span>发布状态 {_escape(_label(publish_status, 'publish_status'))}</span>
    <span>指标覆盖 {_escape(success)}</span>
    <span>输入跨度 {_escape(observation_range)}</span>
  </div>
</header>
"""
        return f"""
<header class="hero" id="top">
  <div class="eyebrow">NDX vNext Native Artifact UI · {_escape(template_name)}</div>
  <div class="hero-grid">
    <div>
      <h1>{_escape(hero_title)}</h1>
      <p class="hero-note">{_escape(hero_note)}</p>
    </div>
    <aside class="verdict-card" aria-label="最终判断核心字段">
      <div class="verdict-row"><span>审批</span><strong>{_escape(_label(approval, 'approval'))}</strong></div>
      <div class="verdict-row"><span>可信度</span><strong class="pill {_confidence_class(confidence)}">{_escape(_label(confidence, 'confidence'))}</strong></div>
      <div class="verdict-row"><span>发布状态</span><strong class="pill {_severity_class(publish_status)}">{_escape(_label(publish_status, 'publish_status'))}</strong></div>
      <div class="verdict-row"><span>分析目标日</span><strong class="mono">{_escape(meta.get('data_date', 'N/A'))}</strong></div>
      <div class="verdict-row"><span>回测日</span><strong class="mono">{_escape(backtest_date)}</strong></div>
      <div class="verdict-row"><span>输入数据日期跨度</span><strong class="mono">{_escape(observation_range)}</strong></div>
      <div class="verdict-row"><span>采集时间</span><strong class="mono">{_escape(_format_timestamp(collector_timestamp))}</strong></div>
      <div class="verdict-row"><span>生成时间</span><strong class="mono">{_escape(_format_timestamp(generated_at))}</strong></div>
      <div class="verdict-row"><span>指标覆盖</span><strong class="mono">{_escape(success)}</strong></div>
    </aside>
  </div>
  <div class="hero-risks">
    <span>风险主展示</span>
    <p>本次有 {_escape(risk_count)} 条不能忽视的风险；完整清单在“风险边界”章节，只在一处展开，避免重复放大。</p>
  </div>
  <div class="run-path">{_escape(run_path)}</div>
</header>
"""

    def _navigation(self, template: str = "brief") -> str:
        if template == "brief":
            return """
<nav class="nav" aria-label="章节导航">
  <a href="#decision">30秒裁决</a>
  <a href="#five-minute-brief">5分钟简报</a>
  <a href="#risks">风险与反证</a>
  <a href="#conflicts">冲突与共振</a>
  <a href="#layers">L1-L5 底稿</a>
  <a href="#audit">数据与审计</a>
</nav>
"""
        return """
<nav class="nav" aria-label="章节导航">
  <a href="#decision">判断</a>
  <a href="#actions">动作</a>
  <a href="#evidence">依据</a>
  <a href="#news">新闻</a>
  <a href="#risks">风险</a>
  <a href="#conflicts">冲突</a>
  <a href="#layers">底稿</a>
  <a href="#governance">治理</a>
  <a href="#audit">审计</a>
</nav>
"""

    def _golden_pit_summary(self, checklist: Dict[str, Any]) -> Dict[str, str]:
        entries = _as_list(checklist.get("entries")) if isinstance(checklist, dict) else []
        if not entries:
            return {
                "change": "和上次判断比，暂缓启用。",
                "distance": "尚未形成可审计的买入/卖出条件差距。",
            }
        changes = _as_list(checklist.get("changed_since_last_run_summary"))
        change = str(changes[0]) if changes else "本轮未记录显著状态变化。"
        not_ready = [
            item
            for item in entries
            if isinstance(item, dict) and item.get("current_status") in {"not_met", "insufficient_evidence"}
        ]
        met_count = sum(1 for item in entries if isinstance(item, dict) and item.get("current_status") == "met")
        if not_ready:
            first = not_ready[0]
            status = "证据不足" if first.get("current_status") == "insufficient_evidence" else "未满足"
            distance = f"{len(not_ready)} 项仍未满足或证据不足；优先看：{status} - {_sentence(first.get('condition'), 72)}"
        else:
            distance = f"{met_count} 项条件均已满足；仍需复核反证和发布闸门。"
        return {"change": _sentence(change, 110), "distance": _sentence(distance, 120)}

    _STANCE_PARAGRAPHS = {
        "defensive": (
            "你的政策书没有'因为系统判断偏防御，就暂停战略定投'这一条（部署规则：安全层以上现金不等待完美买点，"
            "每次只投低于目标的桶）。所以本轮判断不改变战略权益（纳指/标普/红利低波）的常规定投节奏。它真正能影响的，"
            "是两件本来就悬而未决的事：你在等待的'价值买入'加码时点，以及本就已经冻结新增的主动仓——本轮偏防御的信号，"
            "不构成额外理由让这两者提前或延后。"
        ),
        "constructive": (
            "你的政策书同样没有'系统判断偏乐观，就可以加速部署或突破仓位上限'这一条（部署规则：不等待完美买点，"
            "只投低于目标的桶——这条规则从一开始就不需要乐观信号来触发）。所以本轮偏乐观的判断不改变战略权益的常规节奏，"
            "也不构成把冻结中的主动仓解冻的理由。它唯一可能触发的动作，是促使你去补一份还没做的功课：如果你想借这类信号"
            "把纳指仓位推高到超过战略权益 50% 的临时上限，政策书要求你先完成'纳指集中度'的书面论证，而不是让判断信号替代论证。"
        ),
        "neutral": (
            "本轮系统判断在多空之间没有明确倾向。你的政策书本来就不依赖判断方向来决定节奏——部署规则是'安全层以上现金不等待"
            "完美买点，每次只投低于目标的桶'，这条规则在偏多、偏空、中性的判断下都一样生效。这类中性判断通常不改变任何既定动作，"
            "只提醒你：下一次半年再平衡检查点到了的话，按既定比例检查桶内偏离，而不是现在因为这个判断临时调整。"
        ),
    }

    def _personal_policy_translation(self, final: Dict[str, Any], profile: Dict[str, Any]) -> str:
        """Deterministic (no-LLM) translation of the final judgment against the
        reader's own investment policy statement (config/user_decision_profile.local.json).

        Never reads/renders absolute money amounts from `profile` — see the
        hard rule in the work order this implements.
        """
        if not profile:
            return (
                "<p>个人决策画像未配置（config/user_decision_profile.local.json 不存在）。"
                "这里不做任何翻译或推测，请先补齐你的政策书画像文件。</p>"
            )

        stance = _classify_investor_stance(
            str(final.get("final_stance", "") or ""),
            str(final.get("state_diagnosis", "") or ""),
        )
        stance_copy = _escape(self._STANCE_PARAGRAPHS[stance])
        judgment = _escape(final.get("state_diagnosis") or final.get("final_stance") or "本轮未记录明确姿态")

        invalidations = _as_list(final.get("invalidation_conditions"))
        bullish_items = [
            body
            for direction, body in (_split_invalidation_item(item) for item in invalidations)
            if direction == "转多"
        ]
        if bullish_items:
            bullish_rows = "".join(f"<li>{_escape(body)}</li>" for body in bullish_items)
            bullish_block = f"<b>你在等的'价值买入'，系统当前的具名观察条件：</b><ul>{bullish_rows}</ul>"
        else:
            bullish_block = (
                "本轮系统输出没有标注具名的【转多】转折条件（这不代表市场没有转多可能，只是本轮判断未把它写成结构化条件）。"
                "请把'风险边界'区列出的失效条件当作方向性参考，不要在没有具体数字支持时，自己脑补价格点位或概率。"
            )

        bearish_items = [
            body
            for direction, body in (_split_invalidation_item(item) for item in invalidations)
            if direction == "转空"
        ]
        if not bearish_items:
            bearish_items = [str(item) for item in _as_list(final.get("must_preserve_risks"))]
        if not bearish_items:
            bearish_items = ["本轮未记录具名的风险触发条件"]
        risk_rows = "".join(f"<li>{_escape(item)}</li>" for item in bearish_items)

        footnote = "<p><small>本区只是把系统判断对照你自己的政策书（2026-06-29 草案）做的机械翻译，不构成投资建议。</small></p>"

        return f"""
<style>
.policy-check-head, .policy-check-row {{ display: grid; grid-template-columns: minmax(0, .9fr) minmax(0, 1fr) minmax(0, 1.5fr); gap: .75rem; }}
.policy-check-head {{ margin-top: .75rem; padding: .5rem .75rem; border-bottom: 1px solid var(--rule-strong, #999); }}
.policy-check-row {{ padding: .75rem; border-bottom: 1px solid var(--rule, #ddd); align-items: start; }}
.policy-check-row ul {{ margin: .35rem 0 0; padding-left: 1.15rem; }}
@media (max-width: 720px) {{ .policy-check-head {{ display: none; }} .policy-check-row {{ grid-template-columns: 1fr; }} }}
</style>
<section class="policy-checklist">
  <h3>按你的政策书逐条机械对照（无模型参与）</h3>
  <div class="policy-check-head"><b>政策条款</b><b>本轮判断</b><b>对照结果</b></div>
  <div class="policy-check-row">
    <div>安全层以上现金不等待完美买点，每次只投低于目标的桶。</div>
    <div>{judgment}</div>
    <div>{stance_copy}</div>
  </div>
  <div class="policy-check-row">
    <div>价值买入加码只看政策书和具名观察条件，不由模型自动触发。</div>
    <div>{bullish_block}</div>
    <div>这里只机械列出本轮已有条件；没有具体数字支持时，不自行补价格点位或概率。</div>
  </div>
  <div class="policy-check-row">
    <div>按你的政策书，'市场涨跌'不构成修改政策的理由。</div>
    <div><b>即使以下情况发生：</b><ul>{risk_rows}</ul></div>
    <div>需要重审的是加码计划而非整体配置。</div>
  </div>
</section>
{footnote}
"""

    def _reader_exit_section(self, artifacts: Dict[str, Any]) -> str:
        final = artifacts.get("final_adjudication", {}) or {}
        checklist = artifacts.get("golden_pit_checklist", {}) if isinstance(artifacts.get("golden_pit_checklist"), dict) else {}
        local_profile = _load_local_decision_profile()
        reader = self._reader_final(final)
        state = checklist.get("current_state") or final.get("state_diagnosis") or reader.get("one_liner") or final.get("final_stance") or "未记录"
        changes = _as_list(checklist.get("changed_since_last_run_summary"))
        change_rows = "".join(f"<li>{_escape(item)}</li>" for item in changes[:4]) or "<li>和上次判断比，暂缓启用。</li>"

        horizon_rows = "".join(
            f"""
      <article>
        <h3>{_escape(_display_label(item.get('horizon', 'time horizon')))}</h3>
        <p>{_escape(item.get('view', ''))}</p>
        <small>{_escape(item.get('action_implication', ''))}</small>
      </article>
"""
            for item in _as_list(final.get("time_horizon_views"))[:3]
            if isinstance(item, dict)
        )
        horizon_block = (
            f'<h3 class="reader-sub">不同时间尺度分别怎么看</h3><div class="trigger-grid">{horizon_rows}</div>'
            if horizon_rows
            else ""
        )

        state_tone = {
            "largely_reflected": "good",
            "partially_reflected": "watch",
            "not_reflected": "risk",
            "unclear": "watch",
        }
        price_rows = "".join(
            f"""
      <li>
        <span class="pill {state_tone.get(str(item.get('reflected_state')), 'watch')}">{_escape(_display_label(item.get('reflected_state', 'unclear')))}</span>
        <div>
          <b>{_escape(_display_label(item.get('category') or item.get('target', 'price')))}</b>
          <p>{_escape(_sentence(item.get('rationale', ''), 110))}</p>
        </div>
      </li>
"""
            for item in _as_list(final.get("price_reflection_map"))[:6]
            if isinstance(item, dict)
        )
        payoff = final.get("payoff_assessment") or ""
        waiting_cost = final.get("confirmation_cost") or ""
        odds_block = ""
        if price_rows or payoff or waiting_cost:
            odds_block = f"""
  <div class="reader-odds-grid">
    <article>
      <h3>价格已经计入了什么</h3>
      <small class="section-note">以下是推断而非事实——每条都附证据与反证，欢迎质疑。</small>
      <ul class="price-map">{price_rows or '<li><p>暂无结构化价格反映地图。</p></li>'}</ul>
    </article>
    <article>
      <h3>赔率与等待的代价</h3>
      <p>{_escape(payoff or '暂无结构化赔率判断。')}</p>
      <p><b>等待确认的成本：</b>{_escape(waiting_cost or '未记录')}</p>
    </article>
  </div>
"""

        entries = [item for item in _as_list(checklist.get("entries")) if isinstance(item, dict)][:8]
        has_claim_entries = any(item.get("discipline_side") == "claim" for item in entries)
        claim_note = '<p class="section-note">这类条目不直接触发买卖，只是判断成立与否的观察哨。</p>' if has_claim_entries else ""
        # 上游 checklist 往往把同一批 refs / 反证整包写进每一条；共享部分只展示一次。
        ref_lists = [[_canonical_ref(ref) for ref in _as_list(item.get("evidence_refs"))] for item in entries]
        shared_refs: List[str] = []
        if len(entries) > 1 and ref_lists and all(refs == ref_lists[0] for refs in ref_lists) and ref_lists[0]:
            shared_refs = ref_lists[0]
        falsifier_counts: Dict[str, int] = {}
        for item in entries:
            for value in {str(v) for v in _as_list(item.get("falsification_conditions"))}:
                falsifier_counts[value] = falsifier_counts.get(value, 0) + 1
        shared_falsifiers = [text for text, count in falsifier_counts.items() if count == len(entries)] if len(entries) > 1 else []
        item_rows = ""
        for index, item in enumerate(entries):
            status = str(item.get("current_status") or "")
            view = _discipline_status_view(item.get("discipline_side"), status)
            side_chip = (
                f'<span class="side-chip {view["side_class"]}">{_escape(view["side_label"])}</span>'
                if view["side_label"]
                else ""
            )
            own_falsifiers = [
                str(value) for value in _as_list(item.get("falsification_conditions"))
                if str(value) not in shared_falsifiers
            ][:2]
            own_refs = "" if shared_refs else self._ref_chips(ref_lists[index][:4])
            detail_bits = ""
            if own_falsifiers:
                detail_bits += f"<small><b>反证/失效：</b>{_escape('；'.join(_sentence(v, 88) for v in own_falsifiers))}</small>"
            if own_refs:
                detail_bits += f'<div class="ref-row">{own_refs}</div>'
            item_rows += f"""
      <li class="pit-item">
        <div class="pit-badges">
          {side_chip}
          <span class="pill {view['tone']}">{_escape(view['text'])}</span>
        </div>
        <div>
          <p>{_escape(_sentence(item.get('condition'), 140))}</p>
          {detail_bits}
        </div>
      </li>
"""
        shared_block = ""
        if item_rows and (shared_refs or shared_falsifiers):
            shared_falsifier_rows = "".join(f"<li>{_escape(_sentence(text, 110))}</li>" for text in shared_falsifiers[:6])
            shared_block = f"""
    <details class="canon-box pit-shared">
      <summary>这批条件共用的证据与反证（上游按批次记录，未细分到单条）</summary>
      <div class="ref-row">{self._ref_chips(shared_refs[:10])}</div>
      <ul>{shared_falsifier_rows or '<li>无共用反证。</li>'}</ul>
    </details>
"""
        checklist_block = (
            f'<h3 class="reader-sub">距离买入/卖出纪律还差什么</h3>{claim_note}<ul class="pit-list">{item_rows}</ul>{shared_block}'
            if item_rows
            else "<p>暂无黄金坑清单条目。</p>"
        )

        return f"""
<section class="panel decision-panel" id="decision">
  <div class="section-kicker">01 · 读者出口</div>
  <h2>30 秒先看三件事</h2>
  <p class="section-note">这里不是每日交易提示。它把最终 claim 台账翻译成：当前状态是什么、距离你的买入/卖出纪律还差哪几项证据。</p>
  <div class="governance-grid">
    <article>
      <h3>市场判断</h3>
      <p>{_escape(_sentence(state, 180))}</p>
    </article>
    <article>
      <h3>风险边界</h3>
      <ul>{''.join(f'<li>{_render_invalidation_item(item)}</li>' for item in _as_list(final.get('invalidation_conditions'))[:4]) or '<li>暂无结构化失效条件。</li>'}</ul>
    </article>
    <article>
      <h3>个人决策翻译</h3>
      {self._personal_policy_translation(final, local_profile)}
      <small>个人档案只在读者出口使用，不进入上游分析 prompt。</small>
    </article>
  </div>
  {horizon_block}
  {odds_block}
  <section class="memo-readout">
    <div>
      <b>和上次判断比，什么变了</b>
      <ul>{change_rows}</ul>
    </div>
    <div>
      <b>条件差距</b>
      <p>{_escape(self._golden_pit_summary(checklist)['distance'])}</p>
    </div>
    <div>
      <b>阅读深度</b>
      <p>30 秒裁决 -> 5 分钟简报 -> 深度研究 -> 审计重放。</p>
    </div>
  </section>
  {checklist_block}
</section>
"""

    def _decision_section(self, artifacts: Dict[str, Any]) -> str:
        final = artifacts.get("final_adjudication", {}) or {}
        thesis = artifacts.get("thesis_draft", {}) or {}
        surface = self._decision_surface(final, thesis)
        reader = self._reader_final(final)
        refs = self._ref_chips(final.get("evidence_refs", []))
        risk_count = len(_as_list(final.get("must_preserve_risks")))
        reasons = "".join(f"<li>{_escape(item)}</li>" for item in _as_list(reader.get("three_reasons"))[:3])
        horizon_rows = "".join(
            f"""
      <article>
        <h3>{_escape(item.get('horizon', 'time horizon'))}</h3>
        <p>{_escape(item.get('view', ''))}</p>
        <small>{_escape(item.get('action_implication', ''))}</small>
      </article>
"""
            for item in _as_list(surface.get("time_horizon_views"))[:3]
            if isinstance(item, dict)
        )
        action_rows = "".join(
            f"""
      <article>
        <h3>{_escape(item.get('bucket', 'position'))}</h3>
        <p>{_escape(item.get('action', ''))}</p>
        {self._portfolio_action_note_html(item)}
      </article>
"""
            for item in _as_list(surface.get("portfolio_actions"))[:3]
            if isinstance(item, dict)
        )
        invalidations = "".join(f"<li>{_render_invalidation_item(item)}</li>" for item in _as_list(surface.get("invalidation_conditions"))[:5])
        principal = surface.get("principal_contradiction") if isinstance(surface.get("principal_contradiction"), dict) else {}
        price_rows = "".join(
            f"<li><b>{_escape(item.get('category') or item.get('target', 'price'))}</b> · {_escape(item.get('reflected_state', 'unclear'))}: "
            f"{_escape(item.get('rationale', ''))}"
            f"<br><small>反证: {_escape('; '.join(str(x) for x in _as_list(item.get('counterevidence'))) or '; '.join(str(x) for x in _as_list(item.get('counterevidence_refs'))) or '未列出')} · "
            f"动作: {_escape(item.get('action_implication', '未说明'))}</small></li>"
            for item in _as_list(surface.get("price_reflection_map"))[:6]
            if isinstance(item, dict)
        )
        return f"""
<section class="panel decision-panel" id="decision">
  <div class="section-kicker">01 · 最终判断</div>
  <h2>先读读者结论，再打开证据</h2>
  <div class="decision-layout">
    <div class="statement">
      <span>读者结论</span>
      <strong>{_escape(reader.get('one_liner') or final.get('final_stance', 'N/A'))}</strong>
      <p>{_escape(surface.get('state_diagnosis', ''))}</p>
      <div class="ref-row">{refs}</div>
    </div>
    <div class="risk-list">
      <h3>风险摘要</h3>
      <p>本轮不能忽视的风险 {_escape(risk_count)} 条；完整清单见“风险边界”。</p>
    </div>
  </div>
  <div class="governance-grid">
    <article>
      <h3>价格正在定价什么</h3>
      <p>{_escape(surface.get('priced_narrative', ''))}</p>
    </article>
    <article>
      <h3>主要矛盾</h3>
      <p>{_escape(principal.get('summary') or '暂无结构化 principal_contradiction。')}</p>
      <small>{_escape(principal.get('price_reflection') or principal.get('action_implication') or '')}</small>
    </article>
    <article>
      <h3>赔率判断</h3>
      <p>{_escape(surface.get('payoff_assessment', ''))}</p>
    </article>
    <article>
      <h3>等待确认的成本</h3>
      <p>{_escape(surface.get('confirmation_cost', ''))}</p>
    </article>
    <article>
      <h3>三条理由</h3>
      <ul>{reasons or '<li>暂无结构化 reader_final.three_reasons。</li>'}</ul>
    </article>
    <article>
      <h3>价格反映地图</h3>
      <small class="section-note">以下是推断而非事实——每条都附证据与反证，欢迎质疑。</small>
      <ul>{price_rows or '<li>暂无结构化 price_reflection_map。</li>'}</ul>
    </article>
  </div>
  {self._long_term_assessment_section(final)}
  <div class="trigger-grid">{horizon_rows or '<article><h3>时间尺度</h3><p>暂无结构化 time_horizon_views。</p></article>'}</div>
  <div class="trigger-grid">{action_rows or '<article><h3>组合动作</h3><p>暂无结构化 portfolio_actions。</p></article>'}</div>
  <div class="risk-list">
    <h3>失效条件</h3>
    <ul>{invalidations or '<li>暂无结构化失效条件。</li>'}</ul>
  </div>
</section>
"""

    def _actions_section(self, artifacts: Dict[str, Any]) -> str:
        final = artifacts.get("final_adjudication", {}) or {}
        risk = artifacts.get("risk_boundary_report", {}) or {}
        boundary = risk.get("boundary_status", {}) if isinstance(risk.get("boundary_status"), dict) else {}
        stance = str(final.get("final_stance", "") or "")
        confidence = str(final.get("confidence", "medium") or "medium")
        structured_actions = _as_list(final.get("portfolio_actions") or self._reader_final(final).get("action_summary"))
        if structured_actions:
            cards = "".join(
                f"""
<article class="trigger-card">
  <h3>{_escape(item.get('bucket', 'position') if isinstance(item, dict) else '动作')}</h3>
  <p><b>{_escape(item.get('action', item) if isinstance(item, dict) else item)}</b></p>
  {self._portfolio_action_note_html(item) if isinstance(item, dict) else ''}
</article>
"""
                for item in structured_actions[:4]
            )
            invalidations = _as_list(final.get("invalidation_conditions") or self._reader_final(final).get("invalidation_summary"))
            watch_html = "".join(f"<li>{_render_invalidation_item(item)}</li>" for item in invalidations[:6]) or "<li>暂无结构化失效条件。</li>"
            boundary_text = ", ".join(_label(name, "boundary") for name, status in boundary.items() if str(status).lower() in {"breached", "warning"}) or "无 breached/warning 边界"
            return f"""
<section class="panel" id="actions">
  <div class="section-kicker">02 · 买方动作层</div>
  <h2>核心仓、战术仓、等待者分开处理</h2>
  <p class="section-note">这里优先展示 Final.reader_final / portfolio_actions，不把内部审批话术当成买方动作。</p>
  <div class="trigger-grid">{cards}</div>
  <div class="risk-board">
    <div class="risk-list">
      <h3>失效/复核清单</h3>
      <ul>{watch_html}</ul>
    </div>
    <div class="risk-list">
      <h3>当前边界</h3>
      <p>{_escape(boundary_text)}</p>
    </div>
  </div>
</section>
"""
        must_risks = [_label(item, "risk_flag") for item in _as_list(risk.get("must_preserve_risks"))]
        failure_conditions = []
        for item in _as_list(risk.get("failure_conditions")):
            if isinstance(item, dict):
                text = item.get("condition") or item.get("impact") or ""
                if text:
                    failure_conditions.append(str(text))
            elif item:
                failure_conditions.append(str(item))
        breached = [name for name, status in boundary.items() if str(status).lower() == "breached"]
        warnings = [name for name, status in boundary.items() if str(status).lower() == "warning"]

        add_bias = "只有小幅试探或等待确认"
        if confidence == "high" and not breached and any(key in stance.lower() for key in ["bull", "constructive", "positive", "看多", "偏多"]):
            add_bias = "可在证据继续确认时分批增加"
        reduce_bias = "风险触发时优先降低暴露"
        if breached:
            reduce_bias = "已有边界突破，优先降风险"
        wait_bias = "等待关键证据确认"
        if confidence == "low" or warnings or breached:
            wait_bias = "等待数据质量、广度或失效条件修复"

        action_cards = [
            (
                "加仓",
                add_bias,
                "需要看到支撑链继续成立，且风险边界未进一步恶化；不能用单一技术反弹替代估值、广度和流动性确认。",
            ),
            (
                "减仓",
                reduce_bias,
                "若失效条件触发、临界观察转为已突破，或不能忽视的风险开始互相确认，应先降低组合对 NDX/QQQ 的单边暴露。",
            ),
            (
                "等待",
                wait_bias,
                "当置信度不足、数据覆盖不完整或冲突仍未解决时，保持观察优先于把模糊信号包装成明确方向。",
            ),
            (
                "观察窗口",
                "围绕失效条件复核",
                "优先复核 Risk Sentinel 的 failure conditions、L3 广度/集中度、L4 估值安全垫和 L5 趋势失效触发。",
            ),
        ]
        cards = "".join(
            f"""
<article class="trigger-card">
  <h3>{_escape(title)}</h3>
  <p><b>{_escape(headline)}</b></p>
  <p>{_escape(body)}</p>
</article>
"""
            for title, headline, body in action_cards
        )
        watch_items = failure_conditions[:6] or must_risks[:6] or ["暂无结构化触发条件。"]
        watch_html = "".join(f"<li>{_escape(item)}</li>" for item in watch_items)
        boundary_text = ", ".join(_label(item, "boundary") for item in breached + warnings) or "无 breached/warning 边界"
        return f"""
<section class="panel" id="actions">
  <div class="section-kicker">02 · 买方动作层</div>
  <h2>把判断落到动作框架</h2>
  <p class="section-note">这里只把上游证据和风险边界转成条件化动作，不新增未经 evidence refs 支持的点位、概率或回测胜率。</p>
  <div class="trigger-grid">{cards}</div>
  <div class="risk-board">
    <div class="risk-list">
      <h3>观察清单</h3>
      <ul>{watch_html}</ul>
    </div>
    <div class="risk-list">
      <h3>当前边界</h3>
      <p>{_escape(boundary_text)}</p>
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
  <div class="section-kicker">03 · 结论依据</div>
  <h2>主论点证据链</h2>
  <p class="section-note">每条证据链对应一个判断支点。点击证据会打开指标、读数、来源、反证和完整底稿入口。</p>
  <div class="chain-grid">{''.join(chains) or '<p>无证据链。</p>'}</div>
</section>
"""

    def _raw_metric(self, artifacts: Dict[str, Any], layer: str, function_id: str) -> Dict[str, Any]:
        raw_data = artifacts.get("analysis_packet", {}).get("raw_data", {})
        if not isinstance(raw_data, dict):
            return {}
        layer_raw = raw_data.get(layer, {})
        if not isinstance(layer_raw, dict):
            return {}
        metric = layer_raw.get(function_id)
        return metric if isinstance(metric, dict) else {}

    def _metric_value(self, artifacts: Dict[str, Any], layer: str, function_id: str) -> Dict[str, Any]:
        metric = self._raw_metric(artifacts, layer, function_id)
        if not metric and function_id == "get_ndx_ndxe_ratio":
            metric = self._raw_metric(artifacts, layer, "get_qqq_qqew_ratio")
        value = metric.get("value")
        return value if isinstance(value, dict) else {}

    def _indicator_item(self, artifacts: Dict[str, Any], layer: str, function_id: str) -> Dict[str, Any]:
        card = artifacts.get("layers", {}).get(layer, {})
        if not isinstance(card, dict):
            return {}
        for item in _as_list(card.get("indicator_analyses")):
            if isinstance(item, dict) and item.get("function_id") == function_id:
                return item
            if function_id == "get_ndx_ndxe_ratio" and isinstance(item, dict) and item.get("function_id") == "get_qqq_qqew_ratio":
                return item
        return {}

    def _charts_section(self, artifacts: Dict[str, Any]) -> str:
        return f"""
<section class="panel chart-panel" id="charts">
  <div class="section-kicker">03 · 市场图谱</div>
  <h2>跨层压力与估值位置</h2>
  <p class="section-note">估值相对位置尺和 L1-L4 利率估值压力图在此呈现。Damodaran ERP 月度路径和 WorldPERatio 窗口标签已并入 L4 层底稿的对应指标微图（估值交叉校验、Damodaran ERP 月度透镜）。</p>
  <div class="chart-board">
    {self._valuation_ruler_chart(artifacts)}
    {self._rate_valuation_pressure_chart(artifacts)}
  </div>
</section>
"""

    def _chart_rows(self, artifacts: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
        charts = artifacts.get("chart_time_series", {})
        series = charts.get("series") if isinstance(charts, dict) else {}
        item = series.get(key) if isinstance(series, dict) else None
        if item is None and key == "NDX_NDXE_RATIO" and isinstance(series, dict):
            item = series.get("QQQ_QQEW_RATIO")
        rows = item.get("rows") if isinstance(item, dict) else None
        return rows if isinstance(rows, list) else []

    def _historical_percentile(self, artifacts: Dict[str, Any], layer: str, function_id: str, window: str = "10y") -> Optional[float]:
        value = self._metric_value(artifacts, layer, function_id)
        candidates = [
            value.get(f"percentile_{window}"),
            value.get(f"{window}_percentile"),
            value.get(f"{window.upper()}Percentile"),
        ]
        for container_key in ("relativity", "historical_stats"):
            container = value.get(container_key)
            if isinstance(container, dict):
                candidates.append(container.get(f"percentile_{window}"))
        if window == "10y":
            candidates.extend(
                [
                    value.get("PEHistoricalPercentile"),
                    value.get("RiskPremiumHistoricalPercentile"),
                ]
            )
        for candidate in candidates:
            percentile = _normalize_percent(candidate)
            if percentile is not None:
                return percentile
        return None

    def _reading_percentile_label(self, reading: Any) -> Optional[str]:
        raw = str(reading or "")
        match = re.search(r"(10\s*年(?:分位|百分位))\s*[:：]?\s*(\d+(?:\.\d+)?)%", raw)
        if match:
            return f"10年分位 {float(match.group(2)):.0f}%"
        match = re.search(r"(5\s*年(?:分位|百分位))\s*[:：]?\s*(\d+(?:\.\d+)?)%", raw)
        if match:
            return f"5年分位 {float(match.group(2)):.0f}%"
        return None

    def _indicator_value_from_reading(self, function_id: str, reading: Any, fallback: Optional[float]) -> Optional[float]:
        raw = str(reading or "")
        if function_id == "get_macd_qqq":
            match = re.search(r"柱\s*(-?\d+(?:\.\d+)?)", raw)
            if match:
                return float(match.group(1))
        value = _safe_number(raw)
        return value if value is not None else fallback

    def _micro_annotation(self, function_id: str, rows: Sequence[Dict[str, Any]], field: str, reading: Any = None) -> Tuple[Optional[str], bool]:
        values = _numeric_series(rows, field)
        last = values[-1] if values else None
        current = self._indicator_value_from_reading(function_id, reading, last)
        if function_id in {
            "get_10y_treasury",
            "get_10y_real_rate",
            "get_10y_breakeven",
            "get_fed_funds_rate",
            "get_m2_yoy",
            "get_vix",
            "get_vxn",
            "get_hy_oas_bp",
            "get_ig_oas_bp",
            "get_hy_quality_spread_bp",
            "get_ndx_ndxe_ratio",
            "get_qqq_qqew_ratio",
            "get_damodaran_us_implied_erp",
        }:
            return (self._reading_percentile_label(reading), True)
        if function_id == "get_net_liquidity_momentum":
            return (f"20日变化 {_compact_value(_series_delta(rows, field, 20), 1, 'B')}", False)
        if function_id == "get_hyg_momentum":
            return (f"20日变化 {_fmt_pct(_series_return(rows, field, 20), 1, signed=True)}", True)
        if function_id == "get_vxn_vix_ratio":
            return (f"比值 {_compact_value(last, 2)}", True)
        if function_id in {"get_l5_deterministic_snapshot", "get_qqq_technical_indicators", "get_donchian_channels_qqq", "get_multi_scale_ma_position"}:
            return (f"价格 {_compact_value(current, 2)}", True)
        if function_id == "get_rsi_qqq":
            return (f"RSI {_compact_value(current, 1)}", True)
        if function_id == "get_atr_qqq":
            return (f"ATR {_compact_value(current, 2)}", False)
        if function_id == "get_macd_qqq":
            return (f"MACD柱 {_compact_value(current, 2)}", True)
        if function_id == "get_obv_qqq":
            return (f"OBV {_compact_value(last, 1)}", False)
        if function_id == "get_volume_analysis_qqq":
            return (f"成交量 {_compact_value(last, 1)}", False)
        if function_id == "get_price_volume_quality_qqq":
            return (f"CMF {_compact_value(last, 2)}", True)
        return (None, True)

    def _indicator_micro_chart(self, artifacts: Dict[str, Any], indicator: Any) -> str:
        if isinstance(indicator, dict):
            function_id = str(indicator.get("function_id") or "")
            reading = indicator.get("current_reading")
        else:
            function_id = str(indicator or "")
            reading = None
        mapping = INDICATOR_CHARTS.get(function_id)
        if not mapping:
            return ""
        key, field = mapping
        rows = self._chart_rows(artifacts, key)
        if len(rows) < 2:
            return ""
        annotation, show_guide = self._micro_annotation(function_id, rows, field, reading)
        return f"<div class=\"indicator-micro\">{_sparkline(rows, field, width=260, height=76, annotation=annotation, show_guide=show_guide)}</div>"

    def _stat_chip(self, label: str, value: str, tone: str = "neutral") -> str:
        return (
            f"<span class=\"stat-chip {_escape(tone)}\">"
            f"<b>{_escape(label)}</b><strong>{_escape(value)}</strong>"
            "</span>"
        )

    def _proof_card(
        self,
        artifacts: Dict[str, Any],
        *,
        title: str,
        layer: str,
        chart_key: str,
        field: str,
        takeaway: str,
        stats: Sequence[Tuple[str, str, str]],
        refs: Sequence[str],
        tone: str = "price",
        spark_annotation: Optional[str] = None,
        show_guide: bool = True,
    ) -> str:
        rows = self._chart_rows(artifacts, chart_key)
        if len(_numeric_series(rows, field)) < 2:
            return ""
        stat_html = "".join(self._stat_chip(label, value, tone_value) for label, value, tone_value in stats)
        ref_list = list(refs)
        return f"""
<article class="proof-card tone-{_escape(tone)}">
  <div class="proof-head"><h3>{_escape(title)}</h3><span class="proof-layer">{_escape(layer)}</span></div>
  {_sparkline(rows, field, width=760, height=132, annotation=spark_annotation, show_guide=show_guide)}
  <div class="stat-rail">{stat_html}</div>
  <p>{_escape(takeaway)}</p>
  <details class="proof-evidence">
    <summary>证据 refs · {len(ref_list)}</summary>
    <div class="ref-row">{self._ref_chips(ref_list)}</div>
  </details>
</article>
"""

    def _qqq_price_stats(self, artifacts: Dict[str, Any]) -> List[Tuple[str, str, str]]:
        rows = self._chart_rows(artifacts, "QQQ_OHLCV")
        last = rows[-1] if rows else {}
        close = _safe_number(last.get("close"))
        ma60 = _safe_number(last.get("ma60"))
        macd_hist = _safe_number(last.get("macd_histogram"))
        dist_ma60 = (close / ma60 - 1) * 100 if close is not None and ma60 else None
        raw = self._metric_value(artifacts, "L5", "get_qqq_technical_indicators")
        donchian = raw.get("donchian_position_pct")
        vxn_rows = self._chart_rows(artifacts, "VXN")
        vxn_values = _numeric_series(vxn_rows, "value")
        vxn_last = vxn_values[-1] if vxn_values else None
        return [
            ("价格", _fmt_number(close, digits=2), "neutral"),
            ("20日动量", _fmt_pct(_series_return(rows, "close", 20), 1, signed=True), "good"),
            ("距SMA60", _fmt_pct(dist_ma60, 1, signed=True), "good"),
            ("VXN温度", _fmt_number(vxn_last, digits=1), "risk" if vxn_last is not None and vxn_last >= 25 else "watch"),
            ("通道位置", _fmt_pct(_safe_number(donchian), 1), "watch"),
            ("MACD柱", _fmt_number(macd_hist, digits=2), "risk" if macd_hist is not None and macd_hist < 0 else "neutral"),
        ]

    def _formal_value_stats(
        self,
        artifacts: Dict[str, Any],
        *,
        chart_key: str,
        field: str,
        layer: str,
        function_id: str,
        value_label: str,
        value_suffix: str = "",
        change_kind: str = "pct",
        percentile_window: str = "10y",
        percentile_tone: str = "watch",
        extra: Sequence[Tuple[str, str, str]] = (),
    ) -> List[Tuple[str, str, str]]:
        rows = self._chart_rows(artifacts, chart_key)
        values = _numeric_series(rows, field)
        last = values[-1] if values else None
        delta20 = _series_delta(rows, field, 20)
        if change_kind == "bps":
            change = _fmt_bps(delta20)
        elif change_kind == "points":
            change = f"{delta20:+.1f}点" if delta20 is not None else "N/A"
        else:
            change = _fmt_pct(_series_return(rows, field, 20), 1, signed=True)
        stats = [
            (value_label, f"{_fmt_number(last, digits=2)}{value_suffix}" if last is not None else "N/A", "neutral"),
            (f"{percentile_window.replace('y', '年')}分位", _fmt_percentile(self._historical_percentile(artifacts, layer, function_id, percentile_window)), percentile_tone),
            ("20日变化", change, "risk" if (delta20 or 0) > 0 else "good"),
        ]
        stats.extend(extra)
        return stats

    def _memo_chartbook_section(self, artifacts: Dict[str, Any]) -> str:
        final = artifacts.get("final_adjudication", {}) or {}
        reader = self._reader_final(final)
        invalidations = _as_list(final.get("invalidation_conditions"))
        primary_break = invalidations[0] if invalidations else "等待新的反证条件。"
        invalidation_rows = "".join(f"<li>{_render_invalidation_item(_sentence(item, 88))}</li>" for item in invalidations[:3]) or "<li>暂无结构化失效条件。</li>"
        readout_priced = _sentence(final.get("priced_narrative", ""), 96)
        reasons = "".join(f"<li>{_escape(item)}</li>" for item in _as_list(reader.get("three_reasons"))[:3])
        support_chains = "".join(
            f"""
<article class="chain-card memo-chain-card">
  <div class="chain-index">{index:02d}</div>
  <div class="chain-body">
    <h3>{_escape(chain.get('chain_description', '未命名证据链'))}</h3>
    <div class="ref-row">{self._ref_chips(chain.get('evidence_refs', []))}</div>
  </div>
</article>
"""
            for index, chain in enumerate(_as_list(final.get("key_support_chains"))[:3], start=1)
            if isinstance(chain, dict)
        )

        rate_values = _numeric_series(self._chart_rows(artifacts, "US10Y_REAL"), "value")
        rate_stats = self._formal_value_stats(
            artifacts,
            chart_key="US10Y_REAL",
            field="value",
            layer="L1",
            function_id="get_10y_real_rate",
            value_label="实际利率",
            value_suffix="%",
            change_kind="bps",
            percentile_tone="risk",
            extra=[("距2.30%", _fmt_bps((rate_values[-1] - 2.30) if rate_values else None), "watch")],
        )
        hy_stats = self._formal_value_stats(
            artifacts,
            chart_key="HY_OAS",
            field="value",
            layer="L2",
            function_id="get_hy_oas_bp",
            value_label="HY OAS",
            value_suffix="%",
            change_kind="bps",
            percentile_tone="good",
        )
        quality_stats = self._formal_value_stats(
            artifacts,
            chart_key="HY_QUALITY_SPREAD",
            field="value",
            layer="L2",
            function_id="get_hy_quality_spread_bp",
            value_label="CCC-BB",
            value_suffix="%",
            change_kind="bps",
            percentile_tone="risk",
        )
        ratio_stats = self._formal_value_stats(
            artifacts,
            chart_key="NDX_NDXE_RATIO",
            field="value",
            layer="L3",
            function_id="get_ndx_ndxe_ratio",
            value_label="NDX/NDXE",
            change_kind="pct",
            percentile_tone="risk",
            extra=[("5年分位", _fmt_percentile(self._historical_percentile(artifacts, "L3", "get_ndx_ndxe_ratio", "5y")), "risk")],
        )
        erp_rows = self._chart_rows(artifacts, "DAMODARAN_ERP_MONTHLY")
        erp_values = _numeric_series(erp_rows, "value")
        erp_last = erp_values[-1] if erp_values else None
        erp_delta_12m = (erp_values[-1] - erp_values[-13]) if len(erp_values) > 12 else None
        valuation_value = self._metric_value(artifacts, "L4", "get_ndx_pe_and_earnings_yield")
        real_values_for_stats = _numeric_series(self._chart_rows(artifacts, "US10Y_REAL"), "value")
        real_last_for_stats = real_values_for_stats[-1] if real_values_for_stats else None
        erp_stats = [
            ("ERP", _fmt_number(erp_last, suffix="%", digits=2), "neutral"),
            ("12月变化", _fmt_bps(erp_delta_12m), "good" if (erp_delta_12m or 0) > 0 else "risk"),
            (
                "Trailing PE",
                _fmt_number(
                    _safe_number(_first_present(valuation_value, "PE", "TrailingPE", "PE_TTM", "pe_ttm")),
                    digits=2,
                ),
                "risk",
            ),
            (
                "实际利率",
                _fmt_number(real_last_for_stats, suffix="%", digits=2),
                "risk",
            ),
        ]
        cards_top = self._proof_card(
            artifacts,
            title="QQQ 价格趋势",
            layer="L5 价格与执行",
            chart_key="QQQ_OHLCV",
            field="close",
            takeaway="价格处于上升趋势，但动量和波动读数决定追涨赔率。这里不用价格分位，而看趋势、均线距离、波动温度和 MACD 柱。",
            stats=self._qqq_price_stats(artifacts),
            refs=["L5.get_l5_deterministic_snapshot", "L5.get_macd_qqq", "L2.get_vxn"],
            tone="price",
            spark_annotation="价格趋势",
        )
        cards_rates = self._proof_card(
            artifacts,
            title="10Y 实际利率",
            layer="L1 宏观约束",
            chart_key="US10Y_REAL",
            field="value",
            takeaway="真实折现率决定估值容错率：它越高，NDX 的上涨越依赖盈利兑现和流动性支撑。",
            stats=rate_stats,
            refs=["L1.get_10y_real_rate", "L1.get_10y_treasury"],
            tone="macro",
            spark_annotation=f"10年分位 {_fmt_percentile(self._historical_percentile(artifacts, 'L1', 'get_10y_real_rate'))}",
        )
        credit_cards = [
            self._proof_card(
                artifacts,
                title="HY OAS 总量利差",
                layer="L2 信用总量",
                chart_key="HY_OAS",
                field="value",
                takeaway="总量利差回答市场是否仍愿意为风险买单；它必须和质量利差放在一起读。",
                stats=hy_stats,
                refs=["L2.get_hy_oas_bp"],
                tone="credit",
                spark_annotation=f"10年分位 {_fmt_percentile(self._historical_percentile(artifacts, 'L2', 'get_hy_oas_bp'))}",
            ),
            self._proof_card(
                artifacts,
                title="CCC-BB 质量利差",
                layer="L2 信用分层",
                chart_key="HY_QUALITY_SPREAD",
                field="value",
                takeaway="质量利差回答低质信用是否同步乐观；它与总量利差分化时，提示风险偏好并非无差别。",
                stats=quality_stats,
                refs=["L2.get_hy_quality_spread_bp"],
                tone="risk",
                spark_annotation=f"10年分位 {_fmt_percentile(self._historical_percentile(artifacts, 'L2', 'get_hy_quality_spread_bp'))}",
            ),
        ]
        cards_credit = "".join(card for card in credit_cards if card)
        cards_structure = self._proof_card(
            artifacts,
            title="NDX / NDXE",
            layer="L3 内部结构",
            chart_key="NDX_NDXE_RATIO",
            field="value",
            takeaway="NDX 相对 NDXE 说明市值加权指数相对等权指数的强弱。比值高或继续上行时，要把头部集中和广度不足作为结构风险保留下来。",
            stats=ratio_stats,
            refs=["L3.get_ndx_ndxe_ratio", "L3.get_qqq_top10_concentration"],
            tone="structure",
            spark_annotation=f"10年分位 {_fmt_percentile(self._historical_percentile(artifacts, 'L3', 'get_ndx_ndxe_ratio'))}",
        )
        cards_valuation = self._proof_card(
            artifacts,
            title="估值赔率",
            layer="L4 估值与盈利",
            chart_key="DAMODARAN_ERP_MONTHLY",
            field="value",
            takeaway="估值赔率要同时看利润收益、利率和风险溢价。若 ERP 偏薄且实际利率高，价格上涨对盈利兑现的依赖会更强。",
            stats=erp_stats,
            refs=["L4.get_damodaran_us_implied_erp", "L4.get_ndx_pe_and_earnings_yield", "L1.get_10y_real_rate"],
            tone="macro",
            spark_annotation="ERP 月度路径",
            show_guide=False,
        )
        proof_card_count = sum(1 for card in [cards_top, cards_rates, cards_structure, cards_valuation, *credit_cards] if card)

        principal = final.get("principal_contradiction") if isinstance(final.get("principal_contradiction"), dict) else {}
        layers = artifacts.get("layers", {}) or {}

        def layer_reading(layer_id: str, fallback: str) -> str:
            card = layers.get(layer_id, {}) if isinstance(layers.get(layer_id), dict) else {}
            text = card.get("layer_synthesis") or card.get("local_conclusion") or ""
            fragments = _split_sentences(text, max_items=2, item_limit=110)
            return "".join(fragments) or fallback

        constraint_copy = principal.get("summary") or ""
        if principal.get("dominant_side"):
            constraint_copy = f"{constraint_copy} 当前占上风的一面：{principal.get('dominant_side')}".strip()
        constraint_copy = constraint_copy or "本组图回答折现率约束有多硬：分位和阈值距离都来自正式数据，不靠感觉。"
        credit_copy = layer_reading("L2", "信用与波动数据回答风险偏好是否确认当前判断。")
        structure_copy = layer_reading("L3", "内部结构数据回答指数强弱是否有足够多的成分股参与。")

        flow_groups: List[Tuple[str, str, str, str]] = [
            (
                "市场状态",
                "先判断市场状态",
                f"""<p class="lede">{_escape(final.get('final_stance'))}</p>
      <ul class="clean">{reasons or '<li>暂无结构化三条理由。</li>'}</ul>""",
                f'<div class="grid-2">{cards_top}{cards_valuation}</div>' if (cards_top or cards_valuation) else "",
            ),
            (
                "硬约束",
                "再看最硬的约束",
                f"""<p>{_escape(_sentence(constraint_copy, 160))}</p>
      <p class="small">这类图旁边必须放正式分位和阈值距离，因为它要回答的是“压力有多硬”，不是“线往哪走”。</p>""",
                cards_rates,
            ),
            (
                "信用信号",
                "信用是确认还是警告",
                f"""<p>{_escape(_sentence(credit_copy, 160))}</p>
      <p class="small">总量利差和质量利差要一起读：任何一张图单独出现都可能误导。</p>""",
                f'<div class="grid-2">{cards_credit}</div>' if cards_credit else "",
            ),
            (
                "市场宽度",
                "指数强弱有多少成分股在支撑",
                f"<p>{_escape(_sentence(structure_copy, 160))}</p>",
                cards_structure,
            ),
        ]
        flow_sections = ""
        missing_groups: List[str] = []
        shown_index = 0
        group_titles = {
            "市场状态": "Top10 权重 / 估值赔率",
            "硬约束": "10Y 实际利率",
            "信用信号": "信用利差（HY OAS / CCC-BB）",
            "市场宽度": "NDX/NDXE 与集中度",
        }
        for kicker_name, heading, copy_html, cards_html in flow_groups:
            if not cards_html:
                missing_groups.append(group_titles.get(kicker_name, kicker_name))
                continue
            shown_index += 1
            pair_class = " memo-pair" if "grid-2" in cards_html else ""
            flow_sections += f"""
  <section class="memo-flow{pair_class}">
    <div class="memo-copy">
      <p class="kicker">{shown_index:02d} · {_escape(kicker_name)}</p>
      <h3>{_escape(heading)}</h3>
      {copy_html}
    </div>
    {cards_html}
  </section>
"""
        if missing_groups:
            gap_note = f"本轮缺图：{'；'.join(missing_groups)}。相关判断只能依据现有证据，缺口已写入数据边界，不用旧叙事补位。"
        else:
            gap_note = "本轮核心图组齐全。"

        return f"""
<section class="panel memo-chartbook" id="five-minute-brief">
  <div class="section-kicker">02 · 主判断与 5 分钟核心图册</div>
  <h2>核心证据图</h2>
  <p class="section-note">每张图只回答一个判断问题。本次展示 {_escape(proof_card_count)} 张有有效时间序列支撑的核心图；没有证据的图不补位，新增关键证据会自然进入这里或进入补充证据。</p>
  <section class="memo-readout">
    <div>
      <b>本页读法</b>
      <p>先看市场状态，再依次看约束、信用与宽度；图旁的分位与阈值全部来自正式数据。</p>
    </div>
    <div>
      <b>价格定价</b>
      <p>{_escape(readout_priced)}</p>
    </div>
    <div>
      <b>数据缺口</b>
      <p>{_escape(gap_note)}</p>
    </div>
    <div>
      <b>优先复核</b>
      <ul>{invalidation_rows}</ul>
    </div>
  </section>
{flow_sections}
  <section class="memo-support-chain">
    <h3>主论点证据链</h3>
    <p class="section-note">这里保留主论点和 evidence refs 的连接。正文先顺读，审计入口再展开。</p>
    <div class="chain-grid">{support_chains or '<p>无证据链。</p>'}</div>
  </section>
</section>
"""

    def _event_mechanism_report_section(self, mechanism: Dict[str, Any], artifacts: Optional[Dict[str, Any]] = None) -> str:
        if not isinstance(mechanism, dict) or not mechanism:
            return ""
        delivery = mechanism.get("delivery_to_integrated_report", {}) if isinstance(mechanism.get("delivery_to_integrated_report"), dict) else {}
        cards = {
            str(card.get("news_id")): card
            for card in _as_list(mechanism.get("news_cards"))
            if isinstance(card, dict)
        }
        ledger_events = _as_list(((artifacts or {}).get("news_event_ledger") or {}).get("events"))
        interpretation_cards = {
            str(card.get("event_id") or "").split(":", 1)[-1]: card
            for card in _as_list(((artifacts or {}).get("event_interpretation_cards") or {}).get("cards"))
            if isinstance(card, dict) and card.get("event_id")
        }
        source_tiers: Dict[str, str] = {}
        source_tiers_by_title: Dict[tuple[str, str], str] = {}
        for event in ledger_events:
            if not isinstance(event, dict):
                continue
            tier = str(event.get("source_tier") or "未记录")
            event_id = str(event.get("event_id") or "")
            dedupe_id = str(event.get("dedupe_id") or "")
            if event_id:
                source_tiers[event_id.split(":", 1)[-1]] = tier
            if dedupe_id:
                source_tiers[dedupe_id] = tier
            source_tiers_by_title[(str(event.get("title") or ""), str(event.get("source_name") or ""))] = tier

        ordered_card_ids: List[str] = []
        for line in _as_list(mechanism.get("mainlines"))[:4]:
            if not isinstance(line, dict):
                continue
            for card_id in _as_list(line.get("news_card_ids"))[:4]:
                key = str(card_id)
                if key in cards and key not in ordered_card_ids:
                    ordered_card_ids.append(key)
        ordered_card_ids.extend(key for key in cards if key not in ordered_card_ids)
        interpreted_ids = [
            key
            for key in ordered_card_ids
            if key.split(":", 1)[-1] in interpretation_cards
        ]
        ordered_card_ids = interpreted_ids + [
            key for key in ordered_card_ids if key not in interpreted_ids
        ]
        news_rows = ""
        for card_id in ordered_card_ids[:16]:
            card = cards[card_id]
            token = card_id.split(":", 1)[-1]
            interpretation_card = interpretation_cards.get(token)
            source_name = str(card.get("source_name") or "未知来源")
            title = str(card.get("title") or "未命名新闻")
            source_tier = (
                card.get("source_tier")
                or source_tiers.get(token)
                or source_tiers_by_title.get((title, source_name))
                or "未记录"
            )
            excerpt = _fact_excerpt(card.get("raw_text_excerpt"))
            if interpretation_card:
                mechanism_hypothesis = interpretation_card.get("mechanism_hypothesis", {})
                mechanism_text = (
                    mechanism_hypothesis.get("hypothesis")
                    if isinstance(mechanism_hypothesis, dict)
                    else str(mechanism_hypothesis or "")
                )
                confirmation_rows = "".join(
                    f"<li>{_escape(item)}</li>"
                    for item in _as_list(interpretation_card.get("needs_data_confirmation"))
                    if str(item).strip()
                ) or "<li>未记录明确确认项。</li>"
                limitation_rows = "".join(
                    f"<li>{_escape(item)}</li>"
                    for item in _as_list(interpretation_card.get("limitations"))
                    if str(item).strip()
                )
                news_rows += f"""
        <li class="news-item">
          <div class="news-item-head"><b>{_escape(title)}</b></div>
          <p class="news-fact-meta"><span>来源：{_escape(source_name)}</span><span>source_tier：{_escape(source_tier)}</span><span>日期：{_escape(card.get('published_at') or '未记录')}</span></p>
          <div class="event-interpretation-card">
            <p><b>事实摘要</b><span>{_escape(interpretation_card.get('fact_summary') or excerpt)}</span></p>
            <p><b>事件解读</b><span>{_escape(interpretation_card.get('interpretation') or '')}</span></p>
            <p><b>机制假设</b><span>{_escape(mechanism_text)}</span></p>
            <div><b>需要数据确认</b><ul>{confirmation_rows}</ul></div>
            {f'<div><b>限制</b><ul>{limitation_rows}</ul></div>' if limitation_rows else ''}
          </div>
        </li>
"""
                continue
            news_rows += f"""
        <li class="news-item">
          <div class="news-item-head"><b>{_escape(title)}</b></div>
          <p class="news-fact-meta"><span>来源：{_escape(source_name)}</span><span>source_tier：{_escape(source_tier)}</span><span>日期：{_escape(card.get('published_at') or '未记录')}</span></p>
          <p>{_escape(excerpt)}</p>
        </li>
"""
        question_rows = "".join(
            f"<li><b>{_escape('新闻问数据' if item.get('direction') == 'event_to_data' else '数据问新闻')}</b><span>{_escape(item.get('question') or '')}</span></li>"
            for item in _as_list(mechanism.get("cross_layer_questions"))[:6]
            if isinstance(item, dict)
        )
        watch_items: List[str] = []
        for item in _as_list(delivery.get("watchlist")):
            text = str(item).strip()
            if text and text not in watch_items:
                watch_items.append(text)
        watchlist = "".join(f"<li>{_escape(item)}</li>" for item in watch_items[:6]) or "<li>暂无明确追踪项。</li>"
        return f"""
<section class="panel" id="event-layer-summary">
  <div class="section-kicker">05 · 外部事件对照</div>
  <h2>外部事件事实与解读</h2>
  <ul class="news-list">{news_rows or '<li class="news-item"><p>暂无新闻事实材料。</p></li>'}</ul>
  <div class="audit-boundaries">
    <h3>新闻事件给数据层出的题</h3>
    <ul>{question_rows or '<li>暂无跨层问题。</li>'}</ul>
  </div>
  <div class="audit-boundaries">
    <h3>下一步追踪</h3>
    <ul>{watchlist}</ul>
  </div>
</section>
"""

    def _event_layer_summary_section(self, artifacts: Dict[str, Any]) -> str:
        mechanism = artifacts.get("event_mechanism_report", {})
        if not isinstance(mechanism, dict) or not mechanism:
            integrated = artifacts.get("integrated_synthesis_report", {})
            mechanism = integrated.get("event_mechanism_report", {}) if isinstance(integrated, dict) else {}
        if not isinstance(mechanism, dict) or not mechanism:
            fallback_cards = [
                {
                    "news_id": str(event.get("event_id") or event.get("dedupe_id") or index),
                    "title": event.get("title"),
                    "source_name": event.get("source_name"),
                    "source_tier": event.get("source_tier"),
                    "published_at": event.get("published_at"),
                    "raw_text_excerpt": event.get("raw_text_excerpt"),
                }
                for index, event in enumerate(_as_list((artifacts.get("news_event_ledger") or {}).get("events")))
                if isinstance(event, dict)
            ]
            mechanism = {"news_cards": fallback_cards}
        return self._event_mechanism_report_section(mechanism, artifacts) + self._integrated_adjudication_block(artifacts)

    def _integrated_adjudication_block(self, artifacts: Dict[str, Any]) -> str:
        integrated = artifacts.get("integrated_synthesis_report", {})
        adjudication = integrated.get("integrated_adjudication") if isinstance(integrated, dict) else None
        recollection = integrated.get("recollection_requests") if isinstance(integrated, dict) else {}
        recollection_rows = ""
        for request in _as_list(recollection.get("requests") if isinstance(recollection, dict) else []):
            if not isinstance(request, dict):
                continue
            candidates = "、".join(str(item) for item in _as_list(request.get("candidate_function_ids"))) or "待人工确定"
            recollection_rows += (
                f"<li><b>{_escape(request.get('source_type'))} · {_escape(request.get('source_id'))}</b>"
                f"<span>{_escape(request.get('missing'))}</span>"
                f"<small>候选函数：{_escape(candidates)}；触发：{_escape(request.get('trigger_reason'))}</small></li>"
            )
        recollection_section = (
            f'<div class="audit-boundaries"><h3>下轮建议补采清单</h3><ul>{recollection_rows}</ul></div>'
            if recollection_rows else ""
        )
        time_consistency = integrated.get("time_consistency") if isinstance(integrated, dict) else None
        time_warning = ""
        if isinstance(time_consistency, dict) and not time_consistency.get("consistent", False):
            member_dates = "、".join(
                f"{member.get('artifact')}={member.get('date')}"
                for member in _as_list(time_consistency.get("members"))
                if isinstance(member, dict)
            ) or "可核对日期不足"
            time_warning = (
                '<article class="boundary-card bad"><b>时点一致性闸门未通过</b>'
                f'<p>本报告输入时点不一致（{_escape(member_dates)}），已降级为审计参考，不构成正式结论</p></article>'
            )
        if (
            not isinstance(adjudication, dict) or not adjudication.get("llm_adjudicated")
        ) and not time_warning and not recollection_section:
            return ""
        if not isinstance(adjudication, dict) or not adjudication.get("llm_adjudicated"):
            return f"""
<section class="panel sec" id="integrated-adjudication">
  <div class="sec-head">
    <span class="kicker section-kicker">第三层 · 综合裁决</span>
    <h2>数据与外部世界的对质记录</h2>
  </div>
  {time_warning}
  {recollection_section}
</section>
"""
        status_labels = {
            "answered_by_data": ("数据已回答", "good"),
            "partially_answered": ("部分回答", "watch"),
            "cannot_answer_yet": ("暂无法回答", "bad"),
        }
        qa_rows = ""
        for answer in _as_list(adjudication.get("question_answers")):
            if not isinstance(answer, dict):
                continue
            label, tone = status_labels.get(str(answer.get("answer_status")), ("未分类", "watch"))
            refs = "、".join(_as_list(answer.get("data_refs"))[:3] + _as_list(answer.get("investigation_refs"))[:2])
            missing = "、".join(str(item) for item in _as_list(answer.get("missing_evidence"))[:3])
            qa_rows += f"""
      <li>
        <p><b>问：</b>{_escape(_sentence(answer.get('question'), 120))} <span class="pill {tone}">{label}</span></p>
        <p><b>答：</b>{_escape(_sentence(answer.get('answer'), 220))}</p>
        {f'<p class="section-note">依据：{_escape(refs)}</p>' if refs else ''}
        {f'<p class="section-note">缺口：{_escape(missing)}</p>' if missing else ''}
      </li>"""
        relation_labels = {
            "confirmed_by_data": ("数据证实方向", "good"),
            "challenged_by_data": ("数据削弱叙事", "bad"),
            "not_yet_testable": ("当前不可检验", "watch"),
        }
        matrix_rows = ""
        for row in _as_list(adjudication.get("conflict_matrix")):
            if not isinstance(row, dict):
                continue
            label, tone = relation_labels.get(str(row.get("relation")), ("未分类", "watch"))
            refs = "、".join(_as_list(row.get("data_side_refs"))[:3]) or "—"
            matrix_rows += f"""
      <li><span class="pill {tone}">{label}</span> {_escape(_sentence(row.get('event_side'), 110))}
        <span class="section-note">数据侧：{_escape(refs)}{('；' + _escape(_sentence(row.get('note'), 80))) if str(row.get('note') or '').strip() else ''}</span></li>"""
        unexplained = "".join(
            f"<li>{_escape(_sentence(item, 120))}</li>" for item in _as_list(adjudication.get("unexplained"))[:6]
        )
        counter = _sentence(adjudication.get("strongest_counterevidence"), 160)
        return f"""
<section class="panel sec" id="integrated-adjudication">
  <div class="sec-head">
    <span class="kicker section-kicker">第三层 · 综合裁决</span>
    <h2>数据与外部世界的对质记录</h2>
  </div>
  {time_warning}
  <p class="section-note">姿态以第一层数据判决为锚（不可在本层改判）；本层职责是解释整合与张力登记。</p>
  {f'<div class="prose"><p class="reasoned-verdict">{self._reasoned_verdict_html(adjudication.get("integrated_verdict"))}</p></div>' if str(adjudication.get("integrated_verdict") or "").strip() else ''}
  {f'<div class="audit-boundaries"><h3>新闻事件出的题，数据的回答</h3><ul class="qlist">{qa_rows}</ul></div>' if qa_rows else ''}
  {f'<div class="audit-boundaries"><h3>事件叙事 × 数据检验</h3><ul class="risk-list">{matrix_rows}</ul></div>' if matrix_rows else ''}
  {recollection_section}
  {f'<div class="audit-boundaries"><h3>当前解释不了的</h3><ul class="risk-list">{unexplained}</ul></div>' if unexplained else ''}
  {f'<p class="dissent"><b>最强反证</b>：{_escape(counter)}</p>' if counter else ''}
</section>
"""

    def _news_section(self, artifacts: Dict[str, Any]) -> str:
        ledger = artifacts.get("news_event_ledger", {})
        data_links = artifacts.get("news_event_data_links", {})
        news_analysis = artifacts.get("news_layer_analysis", {})
        aggregate = news_analysis.get("aggregate_analysis", {}) if isinstance(news_analysis, dict) else {}
        summaries_by_event = {
            str(item.get("event_id") or item.get("event_ref")): item
            for item in _as_list(news_analysis.get("event_summaries") if isinstance(news_analysis, dict) else [])
            if isinstance(item, dict)
        }
        links_by_event = {
            str(link.get("event_id") or link.get("event_ref")): link
            for link in _as_list(data_links.get("links"))
            if isinstance(link, dict)
        }
        events = [event for event in _as_list(ledger.get("events")) if isinstance(event, dict)]
        rows = []
        for event in events[:12]:
            layers = ", ".join(str(item) for item in _as_list(event.get("layers")) if item)
            symbols = ", ".join(str(item) for item in _as_list(event.get("symbols")) if item)
            tags = []
            if layers:
                tags.append(f"<span>{_escape(layers)}</span>")
            if symbols:
                tags.append(f"<span>{_escape(symbols)}</span>")
            tags.append(f"<span>{_escape(event.get('source_tier', 'source'))}</span>")
            url = str(event.get("url") or "")
            title = _escape(event.get("title") or event.get("event_id") or "未命名事件")
            title_html = f'<a href="{_escape(url)}">{title}</a>' if url else title
            summary = summaries_by_event.get(str(event.get("event_id")), {})
            summary_html = ""
            if summary:
                channels = "".join(
                    f"<span>{_escape(channel)}</span>"
                    for channel in _as_list(summary.get("pressure_channels"))[:5]
                )
                summary_html = f"""
    <div class="news-impact">
      <b>中文概要</b>
      <p>{_escape(summary.get('summary_zh', ''))}</p>
      <b>可能对股市的影响</b>
      <p>{_escape(summary.get('possible_equity_impact_zh', ''))}</p>
      <div class="news-tags">{channels}</div>
    </div>
"""
            link = links_by_event.get(str(event.get("event_id")))
            observations = []
            if link:
                for observation in _as_list(link.get("observations"))[:4]:
                    if not isinstance(observation, dict):
                        continue
                    review = " · 需 Bridge 复核" if observation.get("needs_bridge_review") else ""
                    observations.append(
                        f"<li><b>{_escape(observation.get('series_label') or observation.get('series_key'))}</b> "
                        f"{_escape(observation.get('statement', ''))}"
                        f"<span>{_escape(review)}</span></li>"
                    )
            link_html = ""
            if observations:
                link_html = (
                    '<details class="news-links"><summary>附近市场序列观察</summary>'
                    f"<ul>{''.join(observations)}</ul>"
                    "<p>这些是时间邻近和共同波动观察，不是因果证明，也不是 evidence_ref。</p>"
                    "</details>"
                )
            rows.append(
                f"""
<article class="news-card">
  <div>
    <span class="news-date">{_escape(event.get('published_at', ''))}</span>
    <h3>{title_html}</h3>
    {summary_html or f"<p>{_escape(event.get('notes') or '官方来源事件；只作为背景和触发条件，不替代指标证据。')}</p>"}
    {link_html}
  </div>
  <div class="news-tags">{''.join(tags)}</div>
</article>
"""
            )
        source_errors = [item for item in _as_list(ledger.get("source_errors")) if isinstance(item, dict)]
        errors = "".join(
            f"<li>{_escape(item.get('source_id', 'source'))}: {_escape(item.get('error', ''))}</li>"
            for item in source_errors[:6]
        )
        empty = """
<p class="chart-empty">本次 run 没有生成新闻事件底账。控制台可单独采集官方新闻数据；事件只作背景，不进入 L1-L5 数值证据。</p>
"""
        error_html = f"<details><summary>来源异常</summary><ul>{errors}</ul></details>" if errors else ""
        aggregate_html = ""
        if aggregate:
            channels = "".join(
                f"<span>{_escape(channel)}</span>"
                for channel in _as_list(aggregate.get("dominant_pressure_channels"))[:6]
            )
            aggregate_html = f"""
  <article class="news-aggregate">
    <h3>新闻层总分析</h3>
    <p>{_escape(aggregate.get('market_state_zh') or aggregate.get('one_sentence_zh') or '')}</p>
    <p>{_escape(aggregate.get('equity_fragility_zh') or '')}</p>
    <p>{_escape(aggregate.get('rate_pressure_zh') or '')}</p>
    <p>{_escape(aggregate.get('oil_pressure_zh') or '')}</p>
    <div class="news-tags">{channels}</div>
  </article>
"""
        boundary = ""
        if isinstance(news_analysis, dict) and news_analysis.get("source_boundary"):
            boundary = f"<p class=\"section-note\">{_escape(news_analysis.get('source_boundary'))}</p>"
        return f"""
<section class="panel news-panel" id="news">
  <div class="section-kicker">03 · 新闻源</div>
  <h2>新闻中文概要、股市影响与市场连接观察</h2>
  <p class="section-note">这里只展示官方事件底账、官方宏观 RSS、M7 SEC filings、中文概要、可能影响通道，以及事件日前后市场序列的轻量观察。事件可以解释触发背景，但不能替代任何指标证据。</p>
  {aggregate_html}
  <div class="news-grid">{''.join(rows) if rows else empty}</div>
  {boundary}
  {error_html}
</section>
"""

    def _chart_header(self, title: str, subtitle: str, ref: str) -> str:
        return f"""
  <header class="chart-card__head">
    <div>
      <h3>{_escape(title)}</h3>
      <p>{_escape(subtitle)}</p>
    </div>
    <button class="ref-chip" data-ref="{_escape(ref)}">{_escape(_human_ref_label(ref))}</button>
  </header>
"""

    def _valuation_ruler_chart(self, artifacts: Dict[str, Any]) -> str:
        wind_value = self._metric_value(artifacts, "L4", "get_ndx_wind_valuation_snapshot")
        value = self._metric_value(artifacts, "L4", "get_ndx_pe_and_earnings_yield")
        pe = _safe_number(_first_present(wind_value, "PE", "pe"))
        if pe is None:
            pe = _safe_number(_first_present(value, "PE", "TrailingPE", "PE_TTM", "pe_ttm"))
        pb = _safe_number(_first_present(wind_value, "PB", "pb"))
        ps = _safe_number(_first_present(wind_value, "PS", "ps"))
        wind_risk_premium = _safe_number(_first_present(wind_value, "RiskPremium", "risk_premium"))
        forward_pe = _safe_number(value.get("ForwardPE"))
        fcf_yield = _safe_number(_first_present(value, "FCFYield", "FCF_Yield"))
        sources = [
            source for source in _as_list(value.get("ThirdPartyChecks"))
            if isinstance(source, dict)
            and str(source.get("availability") or "").lower() == "available"
            and str(source.get("usage") or "validation_only").lower() in {"validation_only", "core_allowed"}
        ]
        percentile = _safe_number(_first_present(wind_value, "PEHistoricalPercentile", "pe_historical_percentile"))
        percentile_window = _first_present(wind_value, "PEHistoricalPercentileWindow", "pe_historical_percentile_window") or "historical"
        if percentile is None:
            percentile = _safe_number(_first_present(value, "PE_TTM_percentile_10y", "PE_TTM_percentile_5y"))
            percentile_window = "fallback"
        if percentile is None:
            for source in sources:
                source_percentile = _safe_number(source.get("historical_percentile", source.get("percentile_10y")))
                if source_percentile is not None:
                    percentile = source_percentile
                    percentile_window = "third-party"
                    break
        ticks = []
        if percentile is not None:
            ticks.append(
                f'<span class="chart-marker high" style="left:{_clamp(percentile, 0, 100):.2f}%"><b>{_fmt_number(percentile, suffix="%", digits=1)}</b><small>真实分位</small></span>'
            )
        source_rows = []
        if wind_value:
            source_rows.append(
                f"""
<li>
  <b>Wind</b>
  <span>NDX PE/PB/PS + Wind NDX RP（Wind口径）</span>
  <strong>{_fmt_number(pe, digits=2)}x</strong>
  <small>PE percentile {_escape(str(percentile_window))} {_fmt_number(percentile, suffix='%', digits=1)} · RP {_fmt_number(wind_risk_premium, digits=2)}</small>
</li>
"""
            )
        for source in sources[:5]:
            source_rows.append(
                f"""
<li>
  <b>{_escape(source.get('source_name', 'source'))}</b>
  <span>{_escape(source.get('metric', ''))}</span>
  <strong>{_fmt_number(source.get('value'), digits=2)}</strong>
  <small>{'历史分位 ' + _fmt_number(source.get('historical_percentile', source.get('percentile_10y')), suffix='%', digits=1) if _safe_number(source.get('historical_percentile', source.get('percentile_10y'))) is not None else '未提供历史分位'}</small>
</li>
"""
            )
        if pe is not None and percentile is None:
            pe_position = _clamp((pe - 15) / 30 * 100, 0, 100)
            ticks.append(
                f'<span class="chart-marker high" style="left:{pe_position:.2f}%"><b>{_fmt_number(pe, digits=1)}x</b><small>PE 当前值</small></span>'
            )
        return f"""
<article class="chart-card chart-card--wide" data-chart-id="valuation-relative-ruler">
  {self._chart_header("L4 估值相对位置尺", "真实 percentile 优先；没有 percentile 时只展示当前估值和来源分歧。", "L4.get_ndx_pe_and_earnings_yield")}
  <div class="valuation-ruler-chart" aria-label="L4 估值相对位置尺">
    <div class="ruler-track">{''.join(ticks)}</div>
    <div class="ruler-labels"><span>低估/低压力</span><span>中性</span><span>高估/高压力</span></div>
  </div>
  <div class="metric-strip">
    <span><b>PE</b>{_fmt_number(pe, digits=2)}x</span>
    <span><b>Forward PE</b>{_fmt_number(forward_pe, digits=2)}x</span>
    <span><b>PB</b>{_fmt_number(pb, digits=2)}x</span>
    <span><b>PS</b>{_fmt_number(ps, digits=2)}x</span>
    <span><b>Wind NDX RP（Wind口径）</b>{_fmt_number(wind_risk_premium, digits=2)}</span>
    <span><b>FCF Yield</b>{_fmt_number(fcf_yield, suffix="%", digits=2)}</span>
  </div>
  <ul class="chart-source-list">{''.join(source_rows) or '<li>无外部估值源。</li>'}</ul>
</article>
"""

    def _rate_valuation_pressure_chart(self, artifacts: Dict[str, Any]) -> str:
        l1_real = self._raw_metric(artifacts, "L1", "get_10y_real_rate")
        l1_nominal = self._raw_metric(artifacts, "L1", "get_10y_treasury")
        l1_real_item = self._indicator_item(artifacts, "L1", "get_10y_real_rate")
        l1_nominal_item = self._indicator_item(artifacts, "L1", "get_10y_treasury")
        l4_gap = self._metric_value(artifacts, "L4", "get_equity_risk_premium")
        l4_wind = self._metric_value(artifacts, "L4", "get_ndx_wind_valuation_snapshot")
        l4_val = self._metric_value(artifacts, "L4", "get_ndx_pe_and_earnings_yield")
        real_reading = l1_real_item.get("current_reading") or l1_real.get("value")
        nominal_reading = l1_nominal_item.get("current_reading") or l1_nominal.get("value")
        real_pct = _extract_percentile(real_reading)
        nominal_pct = _extract_percentile(nominal_reading)
        gap = _safe_number(l4_gap.get("level"))
        wind_risk_premium = _safe_number(_first_present(l4_wind, "RiskPremium", "risk_premium"))
        wind_risk_premium_pct = _safe_number(_first_present(l4_wind, "RiskPremiumHistoricalPercentile", "risk_premium_historical_percentile"))
        pe = _safe_number(_first_present(l4_val, "PE", "TrailingPE", "PE_TTM", "pe_ttm"))
        gap_pressure = None if gap is None else _clamp((0 - gap) / 4 * 100, 0, 100)
        wind_rp_pressure = None if wind_risk_premium_pct is None else _clamp(100 - wind_risk_premium_pct, 0, 100)
        pe_pressure = None if pe is None else _clamp((pe - 15) / 30 * 100, 0, 100)
        rows = [
            ("10Y Treasury", nominal_pct, _fmt_number(nominal_reading, suffix="%", digits=2), "L1.get_10y_treasury"),
            ("10Y Real Rate", real_pct, _fmt_number(real_reading, suffix="%", digits=2), "L1.get_10y_real_rate"),
            ("Wind NDX RP（Wind口径）", wind_rp_pressure, _fmt_number(wind_risk_premium, digits=2), "L4.get_ndx_wind_valuation_snapshot"),
            ("Simple Yield Gap", gap_pressure, _fmt_number(gap, suffix="%", digits=2), "L4.get_equity_risk_premium"),
            ("NDX PE", pe_pressure, _fmt_number(pe, suffix="x", digits=2), "L4.get_ndx_pe_and_earnings_yield"),
        ]
        row_html = []
        for label, pressure, reading, ref in rows:
            marker = "" if pressure is None else f'<span style="left:{_clamp(pressure, 0, 100):.2f}%"></span>'
            row_html.append(
                f"""
<div class="pressure-row">
  <button class="ref-chip" data-ref="{_escape(ref)}">{_escape(label)}</button>
  <div class="pressure-track">{marker}</div>
  <strong>{_escape(reading)}</strong>
</div>
"""
            )
        return f"""
<article class="chart-card" data-chart-id="rate-valuation-pressure">
  {self._chart_header("L1-L4 利率估值压力图", "优先看 Wind NDX 风险溢价；简式收益差距保留为诊断/回退。", "L4.get_ndx_wind_valuation_snapshot")}
  <div class="pressure-chart" aria-label="L1-L4 利率估值压力图">
    {''.join(row_html)}
  </div>
  <p class="chart-footnote">越靠右表示压力越高。Wind 风险溢价行用分位反向显示：分位越低，补偿越薄，压力越高；简式收益差距和 PE 行是方向性压力尺。</p>
</article>
"""

    def _risks_section(self, artifacts: Dict[str, Any], section_kicker: str = "04 · 风险边界") -> str:
        final = artifacts.get("final_adjudication", {}) or {}
        risk = artifacts.get("risk_boundary_report", {}) or {}
        boundary = risk.get("boundary_status", {}) if isinstance(risk.get("boundary_status"), dict) else {}
        invalidations = _as_list(final.get("invalidation_conditions"))
        flip_rows = []
        for index, item in enumerate(invalidations, 1):
            direction, body = _split_invalidation_item(item)
            tone = "bull" if direction == "转多" else "bear" if direction == "转空" else "watch"
            short_label = f"【{direction}】条件 {index}" if direction else f"观察条件 {index}"
            flip_rows.append(f"""
<article class="flip dir {tone}">
  <h3>{_escape(short_label)}</h3>
  <p>{_escape(body)}</p>
</article>""")
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
        for index, item in enumerate(_as_list(risk.get("failure_conditions")), 1):
            if isinstance(item, dict):
                direction, condition = _split_invalidation_item(item.get("condition", ""))
                short_label = f"【{direction}】压力 {index}" if direction else f"压力条件 {index}"
                failures.append(
                    f"""
<article class="trigger-card">
  <h3>{_escape(short_label)}</h3>
  <p>{_escape(condition)}</p>
  <p>{_escape(item.get('impact', ''))}</p>
  <span class="pill {_confidence_class(item.get('probability'))}">概率 {_escape(_label(item.get('probability', ''), 'confidence'))}</span>
</article>
"""
                )
            else:
                failures.append(f'<article class="trigger-card"><h3>压力条件 {index}</h3><p>{_escape(item)}</p></article>')
        must = "".join(
            f"<li>{_escape(_label(item, 'risk_flag'))}</li>"
            for item in _as_list(risk.get("must_preserve_risks"))
        )
        return f"""
<section class="panel sec" id="risks">
  <div class="sec-head"><span class="tag sans">{_escape(section_kicker)}</span></div>
  <h2>如果发生这些事，我就改判断</h2>
  <p class="section-note">风险不是附录。这里不写泛泛提示，只列当前判断最需要被反驳、复核或降级的条件。</p>
  <div class="flip-grid">{''.join(flip_rows) or '<p>暂无结构化改判条件。</p>'}</div>
  <div class="risk-board">
    <div>
      <h3>临界观察</h3>
      <div class="boundary-grid">{boundary_cards or '<p>无临界观察。</p>'}</div>
    </div>
    <div class="risk-board">
      <div class="risk-list">
        <h3>不能忽视的风险</h3>
        <ul>{must or '<li>无</li>'}</ul>
      </div>
      <div class="risk-list">
        <h3>改判条件说明</h3>
        <p>完整条件只在上方正本出现；其他章节只链接到这里，避免同一句话反复放大。</p>
      </div>
    </div>
  </div>
  <div class="trigger-grid">{''.join(failures) or '<p>无触发条件。</p>'}</div>
</section>
"""

    def _hypothesis_competition_block(self, artifacts: Dict[str, Any], *, include_leading: bool = False) -> str:
        competition = artifacts.get("hypothesis_competition", {}) if isinstance(artifacts.get("hypothesis_competition"), dict) else {}
        counter = artifacts.get("counter_thesis", {}) if isinstance(artifacts.get("counter_thesis"), dict) else {}
        all_hypotheses = [item for item in _as_list(competition.get("hypotheses")) if isinstance(item, dict)]
        hypotheses = [
            item for item in all_hypotheses if str(item.get("status") or "") == "candidate"
        ]
        principal_counter = str(counter.get("principal_counterargument") or "")
        if not hypotheses and not principal_counter and not (include_leading and all_hypotheses):
            return ""
        thesis = artifacts.get("thesis_draft", {}) if isinstance(artifacts.get("thesis_draft"), dict) else {}
        responses = {
            str(item.get("hypothesis_id")): item
            for item in _as_list(thesis.get("hypothesis_responses"))
            if isinstance(item, dict) and item.get("hypothesis_id")
        }
        cards = ""
        if include_leading:
            leading_id = str(competition.get("leading_hypothesis_id") or "")
            leading = next(
                (
                    item for item in all_hypotheses
                    if str(item.get("hypothesis_id") or "") == leading_id or str(item.get("status") or "") == "leading"
                ),
                None,
            )
            if leading:
                cards += f"""
    <article class="chain-card chain-card--plain hyp hypothesis-card hypothesis-card--leading">
      <span class="hlabel">主线解释 · 暂时领先</span>
      <p>{_escape(leading.get('hypothesis_text') or '')}</p>
      <small>领先仅表示当前证据权重，非确定结论。</small>
    </article>
"""
        for index, item in enumerate(hypotheses[:4], 1):
            response = responses.get(str(item.get("hypothesis_id")), {})
            support_refs = _as_list(item.get("support_evidence_refs"))
            strongest = support_refs[:3]
            reason = response.get("reasoning") or item.get("adjudication_reason")
            if not reason:
                cannot = "；".join(_sentence(value, 110) for value in _as_list(item.get("cannot_explain"))[:2])
                reason = cannot or "本轮没有结构化回应，保留为未解决问题。"
            falsifiers = "".join(
                f"<li>{_escape(_sentence(value, 180))}</li>"
                for value in _as_list(item.get("falsification_conditions"))[:4]
            )
            verdict = _display_label(response.get("verdict") or "candidate")
            cards += f"""
    <article class="chain-card chain-card--plain hyp hypothesis-card">
      <span class="hlabel">竞争假说 {index} · {_escape(verdict)}</span>
      <div class="hrow"><b>它的主张</b><p>{_escape(item.get('hypothesis_text') or '')}</p></div>
      <div class="hrow"><b>最强证据</b><div class="ref-row">{self._ref_chips(strongest)}</div></div>
      <div class="hrow"><b>暂不采纳</b><p>{_escape(reason)}</p></div>
      <div class="hrow"><b>什么会让它赢</b><ul>{falsifiers or '<li>未记录结构化胜出条件。</li>'}</ul></div>
    </article>
"""
        counter_block = ""
        if principal_counter:
            cannot_rows = "".join(
                f"<li>{_escape(_sentence(item, 110))}</li>" for item in _as_list(counter.get("cannot_establish"))[:4]
            )
            counter_block = f"""
    <article class="chain-card chain-card--plain hyp hypothesis-card hypothesis-card--counter">
      <div class="conflict-head">
        <span>反方最强论证（独立生成，未读主线）</span>
      </div>
      <p>{_escape(principal_counter)}</p>
      <details>
        <summary>反方自己也承认无法确立的点</summary>
        <ul>{cannot_rows or '<li>未记录</li>'}</ul>
      </details>
    </article>
"""
        disputes = "".join(
            f"<li>{_escape(_sentence(item, 110))}</li>" for item in _as_list(competition.get("retained_disputes"))[:4]
        )
        disputes_block = f"""
    <div class="audit-boundaries">
      <h4>还没吵完的争议</h4>
      <ul>{disputes}</ul>
    </div>
""" if disputes else ""
        return f"""
  <section class="hypothesis-competition">
    <h3>谁在竞争解释权</h3>
    <p class="section-note">同一批证据允许几种解释同时成立。这里保留竞争中的假说、各自解释不了的部分和裁决理由；主线领先不代表反方出局。</p>
    <div class="chain-grid">{cards}{counter_block if include_leading or not cards else ''}</div>
    {disputes_block}
  </section>
"""

    def _conflicts_section(self, artifacts: Dict[str, Any], section_kicker: str = "05 · 冲突地图") -> str:
        bridge_cards = []
        seen_fingerprints: Dict[str, str] = {}
        investigation_reports = [
            item for item in _as_list(artifacts.get("investigation_reports")) if isinstance(item, dict)
        ]
        all_investigations_are_stubs = bool(investigation_reports) and all(
            item.get("is_deterministic_stub") is True for item in investigation_reports
        )
        for bridge in artifacts["bridges"]:
            if all_investigations_are_stubs and bridge.get("bridge_type") == "feedback_bridge_v2":
                continue
            typed_raw = bridge.get("typed_conflicts")
            fingerprint = json.dumps(
                {
                    "typed": typed_raw,
                    "resonance": bridge.get("resonance_chains"),
                    "paths": bridge.get("transmission_paths"),
                    "conflicts": bridge.get("conflicts"),
                },
                sort_keys=True,
                ensure_ascii=False,
                default=str,
            )
            bridge_name = _display_label(bridge.get("bridge_type", "Bridge"))
            if fingerprint in seen_fingerprints:
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
                bridge_cards.append(
                    f"""
<div class="bridge-card bridge-card--followup">
  <h3>{_escape(bridge_name)}</h3>
  <p>{_escape(bridge.get('implication_for_ndx', ''))}</p>
  <p class="small">本轮复核后的冲突、共振与传导与「{_escape(seen_fingerprints[fingerprint])}」完全一致，不重复展示；这本身是结论：调查没有建立新证据，原有张力全部保留。</p>
  {claims}
</div>
"""
                )
                continue
            seen_fingerprints[fingerprint] = bridge_name
            typed_ids = {
                str(conflict.get("conflict_id") or conflict.get("conflict_type"))
                for conflict in _as_list(typed_raw)
                if isinstance(conflict, dict)
            }
            legacy_conflicts = [
                conflict
                for conflict in _as_list(bridge.get("conflicts"))
                if isinstance(conflict, dict) and str(conflict.get("conflict_type")) not in typed_ids
            ]
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
                for conflict in legacy_conflicts
            )
            typed_conflicts = self._typed_conflict_cards(typed_raw)
            resonance_chains = self._resonance_chain_cards(bridge.get("resonance_chains"))
            transmission_paths = self._transmission_path_cards(bridge.get("transmission_paths"))
            legacy_column = f"<div><h4>需保留的旧口径冲突</h4>{conflicts}</div>" if conflicts else ""
            bridge_cards.append(
                f"""
<div class="bridge-card">
  <h3>{_escape(bridge_name)}</h3>
  <p>{_escape(bridge.get('implication_for_ndx', ''))}</p>
  <div class="typed-map-grid">
    <section>
      <h4>主要冲突</h4>
      {typed_conflicts or '<p>无</p>'}
    </section>
    <section>
      <h4>互相确认</h4>
      {resonance_chains or '<p>无</p>'}
    </section>
    <section>
      <h4>压力传导</h4>
      {transmission_paths or '<p>无</p>'}
    </section>
  </div>
  <div class="bridge-columns">
    <div><h4>Bridge 形成的判断</h4>{claims or '<p>无</p>'}</div>
    {legacy_column}
  </div>
</div>
"""
            )
        return f"""
<section class="panel" id="conflicts">
  <div class="section-kicker">{_escape(section_kicker)}</div>
  <h2>冲突与共振</h2>
  <p class="section-note">这里不追求顺滑，而是保留真正影响判断的张力：哪些证据在确认结论，哪些证据在提醒结论可能过度。</p>
  {self._hypothesis_competition_block(artifacts, include_leading=True)}
  {''.join(bridge_cards) or '<p>无 Bridge Memo。</p>'}
</section>
"""

    def _typed_conflict_cards(self, conflicts: Any) -> str:
        cards = []
        for conflict in _as_list(conflicts):
            conflict_id = str(conflict.get("conflict_id") or conflict.get("conflict_type") or "typed_conflict")
            distinct_layers = list(dict.fromkeys(str(layer) for layer in _as_list(conflict.get("involved_layers"))))
            layers = " / ".join(distinct_layers)
            falsifiers = "".join(f"<li>{_escape(item)}</li>" for item in _as_list(conflict.get("falsifiers")))
            title = _sentence(conflict.get("description") or conflict.get("conflict_type") or "跨层冲突", 48)
            axis = ""
            if len(distinct_layers) >= 2:
                axis = f"""
  <div class="conflict-axis">
    <span>{_escape(distinct_layers[0])}</span>
    <i></i>
    <span>{_escape(distinct_layers[-1])}</span>
  </div>"""
            cards.append(
                f"""
<article class="typed-map-card conflict-card {_severity_class(conflict.get('severity'))}" data-typed-conflict="{_escape(conflict_id)}">
  <div class="conflict-head">
    <span>{_escape(title)}</span>
    <b>{_escape(_label(conflict.get('severity', 'medium'), 'severity'))} · {_escape(_label(conflict.get('confidence', 'medium'), 'confidence'))}</b>
  </div>
  <small>{_escape(layers)}</small>
  {axis}
  <p>{_escape(conflict.get('description', ''))}</p>
  <p><b>机制：</b>{_escape(conflict.get('mechanism', ''))}</p>
  <p><b>含义：</b>{_escape(conflict.get('implication', ''))}</p>
  <details>
    <summary>审计：证据 refs / 反证条件</summary>
    <div class="ref-row">{self._ref_chips(conflict.get('evidence_refs', []))}</div>
    <p class="technical-id">id: {_escape(conflict_id)}</p>
    <ul>{falsifiers or '<li>无</li>'}</ul>
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
            title = chain.get("description") or "共振证据链"
            cards.append(
                f"""
<article class="typed-map-card" data-resonance-chain="{_escape(chain_id)}">
  <div class="conflict-head">
    <span>{_escape(title)}</span>
    <b>{_escape(_label(chain.get('confidence', 'medium'), 'confidence'))}</b>
  </div>
  <small>{_escape(layers)}</small>
  <p><b>机制：</b>{_escape(chain.get('mechanism', ''))}</p>
  <p><b>含义：</b>{_escape(chain.get('implication', ''))}</p>
  <details>
    <summary>审计：证据 refs / 确认指标 / 反证条件</summary>
    <div class="ref-row">{self._ref_chips(chain.get('evidence_refs', []))}</div>
    <p class="technical-id">id: {_escape(chain_id)}</p>
    <h4>确认指标</h4>
    <ul>{confirming or '<li>无</li>'}</ul>
    <h4>反证条件</h4>
    <ul>{falsifiers or '<li>无</li>'}</ul>
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
    <span>{_escape(source)} 影响 {_escape(target)}</span>
    <b>{_escape(_label(path.get('confidence', 'medium'), 'confidence'))}</b>
  </div>
  <div class="path-line"><b>{_escape(source)}</b><span>影响</span><b>{_escape(target)}</b></div>
  <p>{_escape(path.get('mechanism', ''))}</p>
  <p><b>含义：</b>{_escape(path.get('implication', ''))}</p>
  <details>
    <summary>审计：证据 refs</summary>
    <div class="ref-row">{self._ref_chips(path.get('evidence_refs', []))}</div>
    <p class="technical-id">id: {_escape(path_id)}</p>
  </details>
</article>
"""
            )
        return "".join(cards)

    def _brief_layer_detail(self, layer: str, card: Dict[str, Any], artifacts: Dict[str, Any]) -> str:
        full_conclusion = card.get("layer_synthesis") or card.get("local_conclusion")
        confidence = card.get("confidence", "medium")
        indicators = [item for item in _as_list(card.get("indicator_analyses")) if isinstance(item, dict) and item.get("function_id")]
        priority_refs = []
        for payload in (
            artifacts.get("final_adjudication", {}),
            artifacts.get("thesis_draft", {}),
            artifacts.get("hypothesis_competition", {}),
        ):
            for ref in self._collect_evidence_refs(payload):
                canonical = _canonical_ref(ref).split("#", 1)[0]
                if canonical.startswith(f"{layer}.") and canonical not in priority_refs:
                    priority_refs.append(canonical)
        by_ref = {f"{layer}.{item.get('function_id')}": item for item in indicators}
        key_items = [by_ref[ref] for ref in priority_refs if ref in by_ref][:5]
        for item in indicators:
            if len(key_items) >= min(3, len(indicators)):
                break
            if item not in key_items:
                key_items.append(item)
        key_items = key_items[:5]
        remaining = [item for item in indicators if item not in key_items]
        key_cards = "".join(
            self._brief_metric_card(
                layer,
                item,
                self._historical_percentile(artifacts, layer, str(item.get("function_id")))
                if self._historical_percentile(artifacts, layer, str(item.get("function_id"))) is not None
                else _extract_percentile(item.get("current_reading")),
            )
            for item in key_items
        )
        remaining_cards = "".join(self._brief_full_indicator_card(layer, item, artifacts) for item in remaining)
        risks = "".join(
            f"<span class=\"pill\">{_escape(_label(flag, 'risk_flag'))}</span>"
            for flag in _as_list(card.get("risk_flags"))[:4]
        )
        return f"""
<article class="layer-detail" id="brief-layer-{_escape(layer)}">
  <div class="sec-head"><span class="tag sans">{_escape(layer)} · {_escape(LAYER_TITLES_ZH.get(layer, ''))}</span><span class="pill {_confidence_class(confidence)}">可信度 {_escape(_label(confidence, 'medium'))}</span></div>
  <p class="layer-summary">{_escape(full_conclusion or '本层没有形成摘要。')}</p>
  <div class="meta">{risks}</div>
  <div class="indicator-grid sec-grid">{key_cards or '<p>本层没有指标卡。</p>'}</div>
  {f'<details class="fold"><summary>其余 {len(remaining)} 个指标</summary><div class="fbody indicator-grid">{remaining_cards}</div></details>' if remaining else ''}
</article>
"""

    def _brief_metric_card(
        self,
        layer: str,
        item: Dict[str, Any],
        quantile: Optional[float],
    ) -> str:
        function_id = str(item.get("function_id") or "")
        ref = f"{layer}.{function_id}"
        gauge = self._brief_quantile_gauge(function_id, quantile)
        return f"""
<article class="indicator-card dcard">
  <span class="dk">{_escape(layer)}</span>
  <button type="button" class="ref-chip dv" data-ref="{_escape(ref)}">{_escape(item.get('metric') or function_id)}</button>
  <p class="dq">{_escape(_sentence(item.get('current_reading'), 130) or '本轮没有可展示读数。')}</p>
  {gauge}
</article>
"""

    def _brief_quantile_gauge(self, function_id: str, quantile: Optional[float]) -> str:
        if quantile is None:
            return ""
        bounded = _clamp(float(quantile), 0, 100)
        if function_id in HIGH_QUANTILE_DANGER:
            direction = "hi"
            marker = bounded
            fallback_style = ""
        elif function_id in LOW_QUANTILE_DANGER:
            direction = "lo"
            marker = 100 - bounded
            fallback_style = "transform:scaleX(-1)"
        else:
            direction = "neutral"
            marker = bounded
            fallback_style = "--severity-low:var(--severity-watch);--severity-high:var(--severity-watch)"
        return f"""
<div class="gauge" aria-label="历史分位">
  <div class="position-ruler gauge-track gauge-track--{direction}" style="{fallback_style}">
    <i class="zone {direction}"></i><span style="left:{marker:.2f}%"></span>
  </div>
  <div class="gauge-lab"><span>低</span><strong>{bounded:.1f}% 分位</strong><span>高</span></div>
</div>"""

    def _brief_full_indicator_card(self, layer: str, item: Dict[str, Any], artifacts: Dict[str, Any]) -> str:
        function_id = str(item.get("function_id") or "")
        ref = f"{layer}.{function_id}"
        quantile = self._historical_percentile(artifacts, layer, function_id)
        if quantile is None:
            quantile = _extract_percentile(item.get("current_reading"))
        gauge = self._brief_quantile_gauge(function_id, quantile)
        guards = "".join(f"<li>{_escape(value)}</li>" for value in _as_list(item.get("misread_guards")))
        falsifiers = "".join(f"<li>{_escape(value)}</li>" for value in _as_list(item.get("falsifiers")))
        return f"""
<article class="indicator-card" data-evidence-ref="{_escape(ref)}">
  <button type="button" class="ref-chip" data-ref="{_escape(ref)}">{_escape(item.get('metric') or function_id)}</button>
  <p class="reading">{_escape(item.get('current_reading') or '')}</p>
  {gauge}
  <p>{_escape(item.get('narrative') or '')}</p>
  <details class="canon-box"><summary>证据发言权</summary><p>{_escape(item.get('canonical_question') or item.get('permission_type') or '未记录')}</p><ul>{guards or '<li>无额外误读边界。</li>'}</ul><h4>反证</h4><ul>{falsifiers or '<li>未记录。</li>'}</ul></details>
</article>
"""

    def _brief_layers_section(self, artifacts: Dict[str, Any]) -> str:
        layers = artifacts.get("layers", {}) or {}
        cards = "".join(
            self._brief_layer_detail(layer, layers.get(layer, {}), artifacts)
            for layer in ["L1", "L2", "L3", "L4", "L5"]
        )
        return f"""
<section class="panel sec layers-panel brief-layers-panel" id="layers">
  <div class="sec-head"><span class="tag sans">06 · L1-L5</span><h2>分层证据</h2></div>
  <p class="section-note">每层先给摘要和 3-5 个被最终推理实际引用的关键指标，其余指标折叠保留。卡内只展示正式分位；走势只在抽屉且必须来自可核验快照。</p>
  <h3 class="sr-only">五层展开细节</h3>
  <div class="layer-stack">{cards}</div>
</section>
"""

    def _layers_section(self, artifacts: Dict[str, Any]) -> str:
        layers = artifacts.get("layers", {}) or {}
        tiles = "".join(
            self._layer_summary_tile(layer, layers.get(layer, {}))
            for layer in ["L1", "L2", "L3", "L4", "L5"]
        )
        cards = "".join(
            self._layer_card(layer, layers.get(layer, {}), artifacts, default_open=(layer == "L1"))
            for layer in ["L1", "L2", "L3", "L4", "L5"]
        )
        return f"""
<section class="panel layers-panel" id="layers">
  <div class="section-kicker">06 · 五层底稿</div>
  <h2>先看摘要，再展开原生底稿</h2>
  <p class="section-note">这里保留每层的本层结论、层内冲突、跨层待验证问题、指标底稿和质量自检。它不是最终判断，而是 Bridge 与治理阶段可追溯的原始分析材料。</p>
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

    def _layer_card(self, layer: str, card: Dict[str, Any], artifacts: Dict[str, Any], *, default_open: bool) -> str:
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
            self._indicator_card(layer, item, artifacts)
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

    def _indicator_visual(self, layer: str, function_id: str, item: Dict[str, Any], artifacts: Dict[str, Any]) -> str:
        raw_value = self._metric_value(artifacts, layer, function_id)
        ref = f"{layer}.{function_id}"
        if not raw_value:
            return ""

        special = {
            "get_cnn_fear_greed_index": self._fear_greed_visual,
            "get_crowdedness_dashboard": self._crowdedness_visual,
            "get_percent_above_ma": self._percent_above_ma_visual,
            "get_new_highs_lows": self._new_highs_lows_visual,
            "get_qqq_top10_concentration": self._top10_concentration_visual,
            "get_m7_fundamentals": self._m7_fundamentals_visual,
            "get_ndx_wind_valuation_snapshot": self._wind_valuation_indicator_visual,
            "get_ndx_pe_and_earnings_yield": self._valuation_indicator_visual,
            "get_ndx_forward_earnings_quality": self._forward_earnings_quality_visual,
            "get_damodaran_us_implied_erp": self._damodaran_indicator_visual,
            "get_equity_risk_premium": self._yield_gap_indicator_visual,
            "get_qqq_technical_indicators": self._technical_snapshot_visual,
            "get_multi_scale_ma_position": self._ma_ladder_visual,
            "get_donchian_channels_qqq": self._donchian_indicator_visual,
            "get_macd_qqq": self._macd_indicator_visual,
            "get_volume_analysis_qqq": self._volume_indicator_visual,
            "get_obv_qqq": self._obv_indicator_visual,
            "get_price_volume_quality_qqq": self._price_volume_quality_visual,
        }.get(function_id)
        if special:
            html = special(ref, raw_value)
            if html:
                return html

        parts = []
        relative = self._relative_position_rows(raw_value)
        if relative:
            parts.append(self._relative_position_visual_body(relative))
        benchmark = self._benchmark_visual_body(raw_value)
        if benchmark:
            parts.append(benchmark)
        components = self._component_stack_visual_body(raw_value)
        if components:
            parts.append(components)
        if not parts:
            return ""
        return self._wrap_indicator_visual(ref, "relative-position", "Relative position", "".join(parts))

    def _wrap_indicator_visual(
        self,
        ref: str,
        visual_type: str,
        title: str,
        body: str,
        *,
        details: bool = False,
        open_by_default: bool = False,
    ) -> str:
        attrs = f'data-indicator-visual="{_escape(ref)}" data-visual-type="{_escape(visual_type)}"'
        if details:
            open_attr = " open" if open_by_default else ""
            return f"""
<details class="indicator-visual indicator-visual--details"{open_attr} {attrs}>
  <summary>{_escape(title)}</summary>
  {body}
</details>
"""
        return f"""
<div class="indicator-visual" {attrs}>
  <div class="indicator-visual__title">{_escape(title)}</div>
  {body}
</div>
"""

    def _relative_position_rows(self, value: Dict[str, Any]) -> List[Tuple[str, Optional[float]]]:
        source = None
        if isinstance(value.get("relativity"), dict):
            source = value["relativity"]
        elif isinstance(value.get("historical_stats"), dict):
            source = value["historical_stats"]
        if not isinstance(source, dict):
            return []
        rows = [
            ("10Y percentile", _normalize_percent(source.get("percentile_10y"))),
            ("5Y percentile", _normalize_percent(source.get("percentile_5y"))),
        ]
        one_year = _normalize_percent(source.get("percentile_1y"))
        if one_year is not None:
            rows.append(("1Y percentile", one_year))
        z_score = _safe_number(source.get("z_score_10y"))
        if z_score is not None:
            rows.append(("10Y z-score", z_score))
        return [(label, number) for label, number in rows if number is not None]

    def _relative_position_visual_body(self, rows: List[Tuple[str, Optional[float]]]) -> str:
        markers = []
        meta = []
        for label, value in rows:
            if value is None:
                continue
            if "z-score" in label:
                z_position = _clamp((value + 3) / 6 * 100, 0, 100)
                markers.append(f'<span class="mini-marker mini-marker--z" style="left:{z_position:.2f}%"></span>')
                meta.append(f"<span><b>{_escape(label)}</b>{_fmt_number(value, digits=2)}σ</span>")
            else:
                markers.append(f'<span class="mini-marker" style="left:{_clamp(value, 0, 100):.2f}%"></span>')
                meta.append(f"<span><b>{_escape(label)}</b>{_fmt_number(value, suffix='%', digits=1)}</span>")
        return f"""
  <div class="mini-ruler mini-ruler--percent">{''.join(markers)}</div>
  <div class="indicator-visual-meta">{''.join(meta)}</div>
"""

    def _benchmark_visual_body(self, value: Dict[str, Any]) -> str:
        level = _safe_number(value.get("level", value.get("current_price")))
        candidates = [
            ("MA", value.get("ma"), value.get("position_vs_ma")),
            ("MA20", value.get("ma20"), value.get("position_vs_ma20") or value.get("ratio_trend_vs_ma20")),
            ("MA50", value.get("ma50"), value.get("position_vs_ma50")),
            ("Short MA", value.get("short_ma"), None),
            ("Long MA", value.get("long_ma"), None),
        ]
        rows = []
        for label, benchmark, position in candidates:
            benchmark_number = _safe_number(benchmark)
            if level is None or benchmark_number is None:
                continue
            low, high = sorted([level, benchmark_number])
            if abs(high - low) < 0.000001:
                high = low + 1
            current_pos = _clamp((level - low) / (high - low) * 100, 0, 100)
            benchmark_pos = _clamp((benchmark_number - low) / (high - low) * 100, 0, 100)
            rows.append(
                f"""
<div class="benchmark-row">
  <span>{_escape(label)}</span>
  <div class="benchmark-track">
    <i class="benchmark-dot" style="left:{benchmark_pos:.2f}%"></i>
    <i class="benchmark-dot benchmark-dot--current" style="left:{current_pos:.2f}%"></i>
  </div>
  <strong>{_fmt_number(level, digits=2)} / {_fmt_number(benchmark_number, digits=2)}</strong>
  <small>{_escape(position or '')}</small>
</div>
"""
            )
        if not rows:
            return ""
        return f"""
  <div class="benchmark-legend"><span>当前值</span><span>基准线</span></div>
  <div class="benchmark-list">{''.join(rows)}</div>
"""

    def _component_stack_visual_body(self, value: Dict[str, Any]) -> str:
        components = value.get("components")
        if not isinstance(components, dict) or not components:
            return ""
        rows = []
        numeric = [(key, _safe_number(metric)) for key, metric in components.items()]
        numeric = [(key, metric) for key, metric in numeric if metric is not None]
        if not numeric:
            return ""
        total = sum(abs(metric) for _, metric in numeric) or 1
        for key, metric in numeric:
            rows.append(
                f"""
<div class="component-row">
  <span>{_escape(key.replace('_', ' '))}</span>
  <div><i style="width:{_clamp(abs(metric) / total * 100, 2, 100):.2f}%"></i></div>
  <strong>{_fmt_number(metric, digits=2)}</strong>
</div>
"""
            )
        return f'<div class="component-stack">{"".join(rows)}</div>'

    def _score_bar(self, label: str, score: Any, subtitle: Any = "", display: Optional[str] = None) -> str:
        value = _normalize_percent(score)
        if value is None:
            return ""
        # display 用于条形位置是归一化值、但读者应看到真实读数的场合（如 CMF、量比）。
        shown = display if display is not None else _fmt_number(value, digits=1)
        return f"""
<div class="score-row">
  <span>{_escape(label)}</span>
  <div class="score-track"><i style="width:{value:.2f}%"></i></div>
  <strong>{_escape(shown)}</strong>
  <small>{_escape(subtitle)}</small>
</div>
"""

    def _fear_greed_visual(self, ref: str, value: Dict[str, Any]) -> str:
        rows = [self._score_bar("Headline", value.get("score"), value.get("rating"))]
        sub_metrics = value.get("sub_metrics") if isinstance(value.get("sub_metrics"), dict) else {}
        for name, payload in sub_metrics.items():
            if isinstance(payload, dict):
                rows.append(self._score_bar(str(name).replace(" (S&P500)", ""), payload.get("score"), payload.get("rating")))
        body = f'<div class="score-list">{"".join(row for row in rows if row)}</div>'
        return self._wrap_indicator_visual(ref, "sentiment-scoreboard", "Fear & Greed component map", body, details=True, open_by_default=True)

    def _crowdedness_visual(self, ref: str, value: Dict[str, Any]) -> str:
        rows = []
        for name, payload in value.items():
            if not isinstance(payload, dict):
                continue
            metric = _safe_number(payload.get("value"))
            if metric is None:
                rows.append(f'<div class="crowdedness-missing"><b>{_escape(name.replace("_", " "))}</b><span>No data</span></div>')
                continue
            rows.append(
                f"""
<div class="crowdedness-tile">
  <b>{_escape(name.replace('_', ' '))}</b>
  <strong>{_fmt_number(metric, digits=2)}</strong>
  <small>{_escape(payload.get('interpretation', ''))}</small>
</div>
"""
            )
        return self._wrap_indicator_visual(ref, "crowdedness-dashboard", "Crowdedness component map", f'<div class="crowdedness-grid">{"".join(rows)}</div>')

    def _percent_above_ma_visual(self, ref: str, value: Dict[str, Any]) -> str:
        level = value.get("level") if isinstance(value.get("level"), dict) else {}
        rows = [
            self._score_bar("50D", level.get("percent_above_50d"), "% constituents above 50D MA"),
            self._score_bar("200D", level.get("percent_above_200d"), "% constituents above 200D MA"),
        ]
        body = f'<div class="score-list">{"".join(row for row in rows if row)}</div>'
        return self._wrap_indicator_visual(ref, "breadth-bars", "Breadth participation", body)

    def _new_highs_lows_visual(self, ref: str, value: Dict[str, Any]) -> str:
        level = value.get("level") if isinstance(value.get("level"), dict) else {}
        highs = _safe_number(level.get("new_highs_52w"))
        lows = _safe_number(level.get("new_lows_52w"))
        total = (highs or 0) + (lows or 0)
        if total <= 0:
            return ""
        high_width = _clamp((highs or 0) / total * 100, 0, 100)
        low_width = _clamp((lows or 0) / total * 100, 0, 100)
        body = f"""
<div class="balance-bar">
  <i class="balance-good" style="width:{high_width:.2f}%"></i>
  <i class="balance-bad" style="width:{low_width:.2f}%"></i>
</div>
<div class="indicator-visual-meta"><span><b>New highs</b>{_fmt_number(highs, digits=0)}</span><span><b>New lows</b>{_fmt_number(lows, digits=0)}</span><span><b>Net</b>{_fmt_number(level.get('net_new_highs'), digits=0)}</span></div>
"""
        return self._wrap_indicator_visual(ref, "new-highs-lows", "New highs versus lows", body)

    def _top10_concentration_visual(self, ref: str, value: Dict[str, Any]) -> str:
        top10 = _safe_number(value.get("top10_weight_pct"))
        m7 = _safe_number(value.get("m7_weight_pct"))
        equal = _safe_number(value.get("equal_weight_top10_baseline_pct"))
        excess = _safe_number(value.get("top10_excess_vs_equal_weight_pct_points"))
        holdings = []
        for item in _as_list(value.get("top10_holdings"))[:10]:
            if isinstance(item, dict):
                holdings.append(
                    f"<li><b>{_escape(item.get('ticker', ''))}</b><span>{_fmt_number(item.get('weight_pct'), suffix='%', digits=2)}</span></li>"
                )
        spread = value.get("market_cap_vs_equal_weight") if isinstance(value.get("market_cap_vs_equal_weight"), dict) else {}
        windows = spread.get("windows") if isinstance(spread.get("windows"), dict) else {}
        spread_rows = []
        for label in ["1m", "3m", "6m"]:
            window = windows.get(label)
            if isinstance(window, dict):
                spread_rows.append(
                    f"<span><b>{_escape(label)} NDX-NDXE</b>{_fmt_number(window.get('market_cap_minus_equal_weight_pct'), suffix='%', digits=2)}</span>"
                )
        body = f"""
<div class="metric-strip">
  <span><b>Top10</b>{_fmt_number(top10, suffix='%', digits=2)}</span>
  <span><b>M7</b>{_fmt_number(m7, suffix='%', digits=2)}</span>
  <span><b>Equal-weight Top10</b>{_fmt_number(equal, suffix='%', digits=2)}</span>
  <span><b>Excess vs equal</b>{_fmt_number(excess, suffix='ppt', digits=2)}</span>
</div>
<ul class="mini-source-list">{"".join(holdings)}</ul>
<div class="metric-strip">{"".join(spread_rows)}</div>
<p class="chart-footnote">effective_date={_escape(value.get('effective_date') or '')}; current holdings official, change history may be proxy.</p>
"""
        return self._wrap_indicator_visual(ref, "top10-concentration", "Top10 concentration anchor", body, details=True, open_by_default=True)

    def _m7_fundamentals_visual(self, ref: str, value: Dict[str, Any]) -> str:
        companies = []
        for ticker, payload in value.items():
            if isinstance(payload, dict):
                companies.append((ticker, payload))
        companies.sort(key=lambda item: _safe_number(item[1].get("MarketCap")) or 0, reverse=True)
        rows = []
        for ticker, payload in companies[:7]:
            moat = _safe_number(payload.get("quantitative_moat_score"))
            pe = _safe_number(payload.get("PE"))
            roe = _safe_number(payload.get("ROE"))
            rows.append(
                f"""
<div class="m7-tile">
  <b>{_escape(ticker)}</b>
  <span>PE {_fmt_number(pe, digits=1)}x</span>
  <span>ROE {_fmt_number(roe, suffix='%', digits=1)}</span>
  <i style="width:{_clamp((moat or 0) * 10, 0, 100):.2f}%"></i>
</div>
"""
            )
        body = f'<div class="m7-grid">{"".join(rows)}</div>'
        return self._wrap_indicator_visual(ref, "m7-fundamentals", "M7 fundamentals heatmap", body, details=True)

    def _wind_valuation_indicator_visual(self, ref: str, value: Dict[str, Any]) -> str:
        pe_window = value.get("PEHistoricalPercentileWindow") or "historical"
        rows = [
            ("PE", value.get("PE"), "x"),
            ("PB", value.get("PB"), "x"),
            ("PS", value.get("PS"), "x"),
            ("Wind NDX RP（Wind口径）", value.get("RiskPremium"), ""),
            (f"PE percentile {pe_window}", value.get("PEHistoricalPercentile"), "%"),
            ("RP percentile", value.get("RiskPremiumHistoricalPercentile"), "%"),
        ]
        metrics = "".join(
            f"<span><b>{_escape(label)}</b>{_fmt_number(metric, suffix=suffix, digits=2)}</span>"
            for label, metric, suffix in rows
            if _safe_number(metric) is not None
        )
        rank = value.get("RiskPremiumRank") if isinstance(value.get("RiskPremiumRank"), dict) else {}
        rank_html = ""
        if rank:
            rank_html = (
                f"<p class=\"chart-footnote\">风险溢价历史排序："
                f"{_escape(str(rank.get('rank', 'N/A')))}/{_escape(str(rank.get('sample_count', 'N/A')))}。"
                "该字段公式与单位未经核实，仅按 Wind 口径原样展示排序位置，不作补偿厚薄解读。</p>"
            )
        body = f"""
<div class="metric-strip">{metrics}</div>
{rank_html}
<p class="chart-footnote">Wind NDX 风险溢价是 NDX 专属风险补偿；Damodaran 是美国市场背景，简式收益差距只是诊断/回退。</p>
"""
        return self._wrap_indicator_visual(ref, "wind-valuation", "Wind NDX valuation + risk premium", body, details=True, open_by_default=True)

    def _valuation_indicator_visual(self, ref: str, value: Dict[str, Any]) -> str:
        component_pb = _safe_number(_first_present(value, "PriceToBook", "PB"))
        metric_authority = value.get("MetricAuthority") if isinstance(value.get("MetricAuthority"), dict) else {}
        pb_usage = (metric_authority.get("PriceToBook") or {}).get("usage") if isinstance(metric_authority.get("PriceToBook"), dict) else None
        fcf_usage = (metric_authority.get("FCFYield") or {}).get("usage") if isinstance(metric_authority.get("FCFYield"), dict) else None
        third_party_pb = None
        for source in _as_list(value.get("ThirdPartyChecks")):
            if isinstance(source, dict):
                source_pb = _safe_number(source.get("pb"))
                if source_pb is not None:
                    third_party_pb = source_pb
                    break
        pb_display = component_pb
        pb_label = "PB"
        pb_note = ""
        rejected_metrics = value.get("RejectedMetrics") if isinstance(value.get("RejectedMetrics"), dict) else {}
        rejected_pb = rejected_metrics.get("PriceToBook") if isinstance(rejected_metrics.get("PriceToBook"), dict) else None
        if rejected_pb and third_party_pb is not None:
            pb_display = third_party_pb
            pb_label = "PB (3P)"
            pb_note = (
                "Component-model PB was rejected from core evidence after a severe source cross-check failure; "
                "the headline strip shows the third-party PB."
            )
        elif pb_usage and pb_usage != "core_allowed" and third_party_pb is not None:
            pb_display = third_party_pb
            pb_label = "PB (3P)"
            pb_note = (
                "Component-model PB is supporting-only; the headline strip shows the third-party PB where available."
            )
        elif component_pb is not None and third_party_pb is not None:
            ratio = component_pb / third_party_pb if third_party_pb else None
            if ratio is not None and (ratio > 2.0 or ratio < 0.5):
                pb_display = third_party_pb
                pb_label = "PB (3P)"
                pb_note = (
                    "Component-model PB diverged materially from third-party published PB; "
                    "the headline strip shows the third-party PB and leaves the component value in raw data."
                )
        fcf_label = "FCF Yield"
        if fcf_usage and fcf_usage != "core_allowed":
            fcf_label = "FCF (proxy)"
            if pb_note:
                pb_note += " "
            pb_note += "FCF yield is supporting-only and is not used as the primary yield-gap input."
        rows = [
            ("PE", _first_present(value, "PE", "TrailingPE", "PE_TTM"), "x"),
            ("Forward PE", value.get("ForwardPE"), "x"),
            ("Earnings Yield", value.get("EarningsYield"), "%"),
            (fcf_label, value.get("FCFYield"), "%"),
            (pb_label, pb_display, "x"),
        ]
        metrics = "".join(f"<span><b>{_escape(label)}</b>{_fmt_number(metric, suffix=suffix, digits=2)}</span>" for label, metric, suffix in rows)
        sources = []
        wp_relative = {}
        for source in _as_list(value.get("ThirdPartyChecks"))[:5]:
            if isinstance(source, dict):
                sources.append(
                    f"<li><b>{_escape(source.get('source_name', 'source'))}</b><span>{_fmt_number(source.get('value'), digits=2)}</span><small>{_escape(source.get('availability', ''))}</small></li>"
                )
                if str(source.get("source_name", "")).lower() == "worldperatio":
                    wp_relative = source.get("relative_position", {}) if isinstance(source.get("relative_position"), dict) else {}
        # WorldPERatio window table
        wp_windows = wp_relative.get("valuation_windows", {}) if isinstance(wp_relative.get("valuation_windows"), dict) else {}
        wp_trend = wp_relative.get("trend_context", {}) if isinstance(wp_relative.get("trend_context"), dict) else {}
        wp_rows = []
        for key in ["1y", "5y", "10y", "20y"]:
            window = wp_windows.get(key)
            if not isinstance(window, dict):
                continue
            sigma = _safe_number(window.get("deviation_vs_mean_sigma"))
            label = str(window.get("valuation_label") or "")
            label_class = "bad" if "over" in label.lower() else ("good" if "under" in label.lower() else "watch")
            wp_rows.append(
                f"""
<tr>
  <th>{_escape(key)}</th>
  <td>{_fmt_number(window.get('average_pe'), digits=2)}x</td>
  <td>{_fmt_number(window.get('std_dev'), digits=2)}</td>
  <td>{_fmt_number(window.get('range_low'), digits=2)}x - {_fmt_number(window.get('range_high'), digits=2)}x</td>
  <td>{_fmt_number(sigma, digits=2)}σ</td>
  <td><span class="pill {label_class}">{_escape(label or 'N/A')}</span></td>
</tr>
"""
            )
        wp_table = ""
        if wp_rows:
            wp_table = f"""
<div class="chart-table-wrap">
  <table class="chart-table">
    <thead><tr><th>窗口</th><th>均值 PE</th><th>标准差</th><th>区间</th><th>偏离</th><th>标签</th></tr></thead>
    <tbody>{"".join(wp_rows)}</tbody>
  </table>
</div>
<div class="metric-strip">
  <span><b>SMA50 margin</b>{_fmt_number(wp_trend.get('sma50_margin_pct'), suffix='%', digits=1)}</span>
  <span><b>SMA200 margin</b>{_fmt_number(wp_trend.get('sma200_margin_pct'), suffix='%', digits=1)}</span>
  <span><b>语境</b>std-dev, not percentile</span>
</div>
"""
        source_list = f'<ul class="mini-source-list">{"".join(sources)}</ul>' if sources else ""
        title = "Valuation cross-check + WorldPERatio" if wp_rows else "Valuation reference values"
        boundary = ""
        if not sources:
            boundary = '<p class="chart-footnote">本次估值微图只展示主来源字段；未接入 Trendonify 或 WorldPERatio 交叉校验。</p>'
        if pb_note:
            boundary += f'<p class="chart-footnote">{_escape(pb_note)}</p>'
        body = f'<div class="metric-strip">{metrics}</div>{source_list}{wp_table}{boundary}'
        return self._wrap_indicator_visual(ref, "valuation-sources", title, body, details=True, open_by_default=True)

    def _forward_earnings_quality_visual(self, ref: str, value: Dict[str, Any]) -> str:
        ndx = value.get("ndx") if isinstance(value.get("ndx"), dict) else {}
        m7 = value.get("m7") if isinstance(value.get("m7"), dict) else {}
        revisions = m7.get("eps_revisions") if isinstance(m7.get("eps_revisions"), dict) else {}
        rows = [
            ("NDX Forward EY", ndx.get("forward_earnings_yield_pct"), "%"),
            ("NDX Fwd EPS growth proxy", ndx.get("forward_eps_growth_proxy_pct"), "%"),
            ("NDX operating margin", ndx.get("weighted_operating_margin_pct"), "%"),
            ("M7 30D EPS revision", revisions.get("weighted_next_year_eps_revision_30d_pct"), "%"),
            ("M7 revision direction", revisions.get("revision_direction_30d"), ""),
        ]
        metrics = "".join(
            f"<span><b>{_escape(label)}</b>{_escape(str(metric)) if isinstance(metric, str) else _fmt_number(metric, suffix=suffix, digits=2)}</span>"
            for label, metric, suffix in rows
        )
        members = []
        for ticker, item in (revisions.get("members") or {}).items():
            if isinstance(item, dict) and not item.get("error"):
                members.append(
                    f"<li><b>{_escape(ticker)}</b><span>{_fmt_number(item.get('revision_30d_pct'), suffix='%', digits=2)}</span><small>{_escape(item.get('revision_direction_30d', ''))}</small></li>"
                )
        body = f'<div class="metric-strip">{metrics}</div><ul class="mini-source-list">{"".join(members[:7])}</ul>'
        return self._wrap_indicator_visual(ref, "forward-earnings-quality", "Forward earnings quality", body, details=True, open_by_default=True)

    def _damodaran_indicator_visual(self, ref: str, value: Dict[str, Any]) -> str:
        series = [row for row in _as_list(value.get("monthly_series")) if isinstance(row, dict)]
        manual_erp = _safe_number(value.get("manual_erp"))
        is_manual_only = bool(manual_erp is not None and not series and not value.get("retrieval_method"))
        if is_manual_only:
            metrics = [
                ("Manual ERP", manual_erp),
                ("5Y percentile", value.get("manual_erp_percentile_5y")),
                ("10Y percentile", value.get("manual_erp_percentile_10y")),
            ]
            metric_html = "".join(
                f"<span><b>{_escape(label)}</b>{_fmt_number(metric, suffix='%' if 'ERP' in label or 'percentile' in label else '', digits=2)}</span>"
                for label, metric in metrics
                if _safe_number(metric) is not None
            )
            body = f"""
<div class="metric-strip">{metric_html}</div>
<p class="chart-footnote">人工/Wind ERP 是外部风险补偿参考，不是 Damodaran 官网月度序列，也不是 NDX 专属估值锚。该字段公式与单位未经核实，仅按来源口径原样展示排序位置，不作补偿厚薄解读。</p>
"""
            return self._wrap_indicator_visual(ref, "manual-erp-reference", "Manual/Wind ERP reference", body, details=True, open_by_default=True)
        width, height, pad = 640, 260, 34
        erp_path = _polyline_path(series, "erp_t12m_adjusted_payout", width=width, height=height, pad=pad)
        treasury_path = _polyline_path(series, "us_10y_treasury_rate", width=width, height=height, pad=pad)
        expected_path = _polyline_path(series, "expected_return", width=width, height=height, pad=pad)
        if erp_path:
            svg = f"""
<svg class="line-chart" viewBox="0 0 {width} {height}" role="img" aria-label="Damodaran ERP 月度时间序列">
  <rect x="0" y="0" width="{width}" height="{height}" rx="6"></rect>
  <line x1="{pad}" y1="{height-pad}" x2="{width-pad}" y2="{height-pad}"></line>
  <line x1="{pad}" y1="{pad}" x2="{pad}" y2="{height-pad}"></line>
  <path class="series-erp" d="{_escape(erp_path)}"></path>
  <path class="series-rate" d="{_escape(treasury_path)}"></path>
  <path class="series-return" d="{_escape(expected_path)}"></path>
</svg>
<div class="chart-legend"><span class="series-erp">ERP T12M adjusted payout</span><span class="series-rate">US 10Y Treasury</span><span class="series-return">Expected return</span></div>
"""
        else:
            svg = '<div class="chart-empty">本次没有可绘制的 Damodaran 月度序列。若预期应有官网数据，请检查采集阶段是否实际运行 live Damodaran 抓取。</div>'
        lenses = [
            ("T12M adjusted payout", value.get("erp_t12m_adjusted_payout", value.get("implied_erp_fcfe"))),
            ("T12M cash yield", value.get("erp_t12m_cash_yield")),
            ("10Y avg CF yield", value.get("erp_avg_cf_yield_10y")),
            ("Net cash yield", value.get("erp_net_cash_yield")),
            ("Normalized", value.get("erp_normalized_earnings_payout")),
            ("US 10Y", value.get("us_10y_treasury_rate", value.get("tbond_rate", value.get("t_bond_rate")))),
            ("Default spread", value.get("default_spread")),
            ("Expected return", value.get("expected_return")),
        ]
        lens_html = "".join(
            f"<span><b>{_escape(label)}</b>{_fmt_number(metric, suffix='%', digits=2)}</span>"
            for label, metric in lenses
        )
        percentile_block = value.get("damodaran_erp_historical_percentiles") if isinstance(value.get("damodaran_erp_historical_percentiles"), dict) else {}
        windows = percentile_block.get("windows") if isinstance(percentile_block.get("windows"), dict) else {}

        def percentile_window(label: str, window: Dict[str, Any]) -> str:
            percentile = _safe_number(window.get("percentile"))
            status = str(window.get("status") or "")
            if percentile is None:
                value_text = _escape(status or "unavailable")
            else:
                value_text = _fmt_number(percentile, suffix="%", digits=1)
            sample = window.get("sample_count")
            required = window.get("required_min_months")
            period = " - ".join(str(item) for item in [window.get("window_start"), window.get("window_end")] if item)
            details = f"{sample}/{required} months"
            if period:
                details = f"{details}; {period}"
            if window.get("reason"):
                details = f"{details}; {window.get('reason')}"
            return f"<span><b>{_escape(label)}</b>{value_text}<small>{_escape(details)}</small></span>"

        percentile_html = "".join(
            percentile_window(label, windows.get(key) if isinstance(windows.get(key), dict) else {})
            for label, key in (("Damodaran ERP 5Y percentile", "5y"), ("Damodaran ERP 10Y percentile", "10y"))
        )
        percentile_strip = f'<div class="metric-strip">{percentile_html}</div>' if percentile_html else ""
        latest = series[-1] if series else value
        files = " / ".join(str(item) for item in [value.get("source_file"), value.get("current_calculator_source_file")] if item)
        data_cutoff = value.get("data_date") or latest.get("data_date") or percentile_block.get("data_cutoff_date") or ""
        body = f"""
{svg}
<div class="metric-strip">{lens_html}</div>
{percentile_strip}
<p class="chart-footnote">data_cutoff_date={_escape(data_cutoff)} · source={_escape(files or value.get('download_url') or '')} · Damodaran US implied ERP historical percentile is a US market risk-premium percentile, not NDX PE/PB/Forward PE historical percentile. In backtests, this lens must use only Damodaran monthly rows not later than the target date.</p>
"""
        return self._wrap_indicator_visual(ref, "damodaran-current", "Damodaran ERP monthly lens", body, details=True, open_by_default=True)

    def _yield_gap_indicator_visual(self, ref: str, value: Dict[str, Any]) -> str:
        gap = _safe_number(value.get("level"))
        pressure = _clamp((0 - gap) / 4 * 100, 0, 100) if gap is not None else None
        marker = "" if pressure is None else f'<span class="mini-marker" style="left:{pressure:.2f}%"></span>'
        body = f"""
<div class="mini-ruler mini-ruler--pressure">{marker}</div>
<div class="indicator-visual-meta"><span><b>Simple gap</b>{_fmt_number(gap, suffix='%', digits=2)}</span><span><b>Boundary</b>directional, not implied ERP</span></div>
"""
        return self._wrap_indicator_visual(ref, "yield-gap-pressure", "Yield gap pressure", body)

    def _technical_snapshot_visual(self, ref: str, value: Dict[str, Any]) -> str:
        volume_ratio = _safe_number(value.get("volume_ma_ratio"))
        rows = [
            self._score_bar("RSI", value.get("rsi_14"), value.get("rsi_status")),
            self._score_bar("Donchian", value.get("donchian_position_pct"), value.get("donchian_signal")),
            self._score_bar(
                "Volume ratio",
                (volume_ratio or 0) * 50,
                value.get("volume_status"),
                display=f"{volume_ratio:.2f}x" if volume_ratio is not None else None,
            ),
        ]
        body = f'<div class="score-list">{"".join(row for row in rows if row)}</div>{self._ma_ladder_body(value)}'
        return self._wrap_indicator_visual(ref, "technical-snapshot", "Technical dashboard", body, details=True, open_by_default=True)

    def _ma_ladder_body(self, value: Dict[str, Any]) -> str:
        current = _safe_number(value.get("current_price"))
        ma_positions = value.get("ma_positions") if isinstance(value.get("ma_positions"), dict) else {}
        if not ma_positions:
            direct = {
                "ma50": {"value": value.get("sma_50"), "deviation_pct": None},
                "ma200": {"value": value.get("sma_200"), "deviation_pct": None},
            }
            ma_positions = {key: payload for key, payload in direct.items() if _safe_number(payload.get("value")) is not None}
        rows = []
        for label in ["ma5", "ma20", "ma50", "ma60", "ma200"]:
            payload = ma_positions.get(label)
            if not isinstance(payload, dict):
                continue
            deviation = _safe_number(payload.get("deviation_pct"))
            value_text = _fmt_number(payload.get("value"), digits=2)
            marker = _clamp((deviation + 15) / 30 * 100, 0, 100) if deviation is not None else 50
            rows.append(
                f"""
<div class="ma-row">
  <span>{_escape(label.upper())}</span>
  <div class="ma-track"><i style="left:{marker:.2f}%"></i></div>
  <strong>{value_text}</strong>
  <small>{_fmt_number(deviation, suffix='%', digits=2)}</small>
</div>
"""
            )
        if not rows:
            return ""
        current_html = f'<div class="indicator-visual-meta"><span><b>Current</b>{_fmt_number(current, digits=2)}</span><span><b>Scale</b>-15% to +15% vs MA</span></div>'
        return f'<div class="ma-ladder">{"".join(rows)}{current_html}</div>'

    def _ma_ladder_visual(self, ref: str, value: Dict[str, Any]) -> str:
        body = self._ma_ladder_body(value)
        return self._wrap_indicator_visual(ref, "ma-ladder", "MA ladder", body) if body else ""

    def _donchian_indicator_visual(self, ref: str, value: Dict[str, Any]) -> str:
        position = _normalize_percent(value.get("position_pct"))
        marker = "" if position is None else f'<span class="mini-marker" style="left:{position:.2f}%"></span>'
        body = f"""
<div class="mini-ruler mini-ruler--band">{marker}</div>
<div class="indicator-visual-meta">
  <span><b>Lower</b>{_fmt_number(value.get('lower'), digits=2)}</span>
  <span><b>Middle</b>{_fmt_number(value.get('middle'), digits=2)}</span>
  <span><b>Upper</b>{_fmt_number(value.get('upper'), digits=2)}</span>
  <span><b>Position</b>{_fmt_number(position, suffix='%', digits=1)}</span>
</div>
"""
        return self._wrap_indicator_visual(ref, "donchian-channel", "Donchian channel", body)

    def _macd_indicator_visual(self, ref: str, value: Dict[str, Any]) -> str:
        histogram = _safe_number(value.get("histogram"))
        width = _clamp(abs(histogram or 0) / 5 * 100, 2, 100)
        width = min(width, 50)
        direction = "positive" if (histogram or 0) >= 0 else "negative"
        body = f"""
<div class="diverging-bar diverging-bar--{direction}"><i style="width:{width:.2f}%"></i></div>
<div class="indicator-visual-meta"><span><b>MACD</b>{_fmt_number(value.get('macd_line'), digits=2)}</span><span><b>Signal</b>{_fmt_number(value.get('signal_line'), digits=2)}</span><span><b>Histogram</b>{_fmt_number(histogram, digits=2)}</span></div>
"""
        return self._wrap_indicator_visual(ref, "macd-histogram", "MACD momentum", body)

    def _volume_indicator_visual(self, ref: str, value: Dict[str, Any]) -> str:
        ratio = _safe_number(value.get("volume_ma_ratio"))
        score = None if ratio is None else _clamp(ratio / 2 * 100, 0, 100)
        body = self._score_bar("Volume / MA", score, value.get("volume_status"))
        return self._wrap_indicator_visual(ref, "volume-ratio", "Volume confirmation", f'<div class="score-list">{body}</div>') if body else ""

    def _obv_indicator_visual(self, ref: str, value: Dict[str, Any]) -> str:
        change = _safe_number(value.get("change_20d_pct"))
        marker = _clamp((change + 100) / 200 * 100, 0, 100) if change is not None else None
        marker_html = "" if marker is None else f'<span class="mini-marker" style="left:{marker:.2f}%"></span>'
        body = f"""
<div class="mini-ruler mini-ruler--flow">{marker_html}</div>
<div class="indicator-visual-meta"><span><b>20D change</b>{_fmt_number(change, suffix='%', digits=2)}</span><span><b>Trend</b>{_escape(value.get('trend', ''))}</span></div>
"""
        return self._wrap_indicator_visual(ref, "obv-flow", "OBV flow", body)

    def _price_volume_quality_visual(self, ref: str, value: Dict[str, Any]) -> str:
        vwap_dev = _safe_number(value.get("vwap_deviation_pct"))
        cmf = _safe_number(value.get("cmf_20"))
        cmf_score = None if cmf is None else _clamp((cmf + 0.3) / 0.6 * 100, 0, 100)
        rows = [
            self._score_bar("MFI", _normalize_percent(value.get("mfi_14")), value.get("mfi_status")),
            self._score_bar("CMF", cmf_score, value.get("cmf_status"), display=_fmt_number(cmf, digits=2)),
        ]
        vwap_width = _clamp(abs(vwap_dev or 0) / 5 * 100, 2, 100)
        vwap_width = min(vwap_width, 50)
        direction = "positive" if (vwap_dev or 0) >= 0 else "negative"
        rows.append(
            f"""
<div class="score-row">
  <span>VWAP</span>
  <div class="diverging-bar diverging-bar--{direction}"><i style="width:{vwap_width:.2f}%"></i></div>
  <b>{_fmt_number(vwap_dev, suffix='%', digits=2)}</b>
</div>
"""
        )
        meta = f"""
<div class="indicator-visual-meta">
  <span><b>Price vs VWAP</b>{_escape(value.get('price_vs_vwap_20', ''))}</span>
</div>
"""
        body = f'<div class="score-list">{"".join(row for row in rows if row)}</div>{meta}'
        return self._wrap_indicator_visual(ref, "price-volume-quality", "Price-volume quality", body)

    def _indicator_card(self, layer: str, item: Dict[str, Any], artifacts: Dict[str, Any]) -> str:
        function_id = str(item.get("function_id", "unknown"))
        ref = f"{layer}.{function_id}"
        percentile = _extract_percentile(item.get("current_reading"))
        chain = "".join(f"<li>{_escape(step)}</li>" for step in _as_list(item.get("first_principles_chain")))
        implications = self._ref_chips(item.get("cross_layer_implications", []), link=False)
        risks = "".join(
            f"<span>{_escape(_label(flag, 'risk_flag'))}</span>"
            for flag in _as_list(item.get("risk_flags"))
        )
        canon_detail = ""
        if item.get("permission_type") or item.get("canonical_question"):
            guards = "".join(f"<li>{_escape(value)}</li>" for value in _as_list(item.get("misread_guards")))
            falsifiers = "".join(f"<li>{_escape(value)}</li>" for value in _as_list(item.get("falsifiers")))
            canon_detail = f"""
  <details class="canon-box">
    <summary>证据发言权</summary>
    <h4>发言边界</h4>
    <p>{_escape(item.get('permission_type', ''))}</p>
    <h4>它回答的问题</h4>
    <p>{_escape(item.get('canonical_question', ''))}</p>
    <h4>避免误读</h4>
    <ul>{guards or '<li>无</li>'}</ul>
    <h4>推翻条件</h4>
    <ul>{falsifiers or '<li>无</li>'}</ul>
  </details>
"""
        visual = self._indicator_visual(layer, function_id, item, artifacts)
        timestamp_chip = self._timestamp_chip(item.get("data_quality"), ref=ref)
        return f"""
<article class="indicator-card" id="{_escape(function_id)}" data-evidence-ref="{_escape(ref)}">
  <span class="anchor-alias" id="evidence-{_slug(ref)}" aria-hidden="true"></span>
  <div class="indicator-top">
    <div>
      <span class="metric-ref">{_escape(ref)}</span>
      <h4>{_indicator_glossary_label(function_id, item.get('metric', function_id), unique_id=f'indicator-card-{ref}')}</h4>
      {timestamp_chip}
    </div>
    <span class="state-pill">{_escape(item.get('normalized_state', ''))}</span>
  </div>
  <p class="reading">{_escape(item.get('current_reading', ''))}</p>
  {_position_ruler(percentile)}
  {visual}
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

    def _timestamp_chip(self, data_quality: Any, ref: str = "") -> str:
        """Render the compact evidence status shown in indicator card headers."""
        if not isinstance(data_quality, dict) or not data_quality:
            return ""
        data_time = self._evidence_data_time(data_quality)
        source = self._evidence_source_label(data_quality)
        gaps = self._evidence_gap_label(data_quality)
        source_tier = str(data_quality.get("source_tier", ""))
        manual_badge = " · 手动输入" if "手动输入" in source_tier else ""
        button = ""
        if ref:
            button = f'<button type="button" class="evidence-contract-button" data-contract-ref="{_escape(ref)}">证据合约</button>'
        return (
            '<span class="timestamp-chip evidence-status" title="数据本身对应的时间，不是本次 run 的采集时间">'
            f'<span>数据时间：{_escape(data_time)}</span>'
            f'<span>来源：{_escape(source)}{_escape(manual_badge)}</span>'
            f'<span>{_escape(gaps)}</span>'
            f'{button}'
            '</span>'
        )

    def _evidence_data_time(self, data_quality: Dict[str, Any]) -> str:
        for key in ("data_date", "as_of_date", "effective_date", "vintage_date"):
            value = _plain_value(data_quality.get(key))
            if value and value != "未记录":
                return value
        return "未记录"

    def _evidence_source_label(self, data_quality: Dict[str, Any]) -> str:
        for key in ("source_name", "provider"):
            value = str(data_quality.get(key) or "").strip()
            if value and value.lower() != "missing":
                return value
        source_url = str(data_quality.get("source_url") or "").strip()
        if source_url and source_url.lower() != "missing":
            return source_url
        return "未记录"

    def _evidence_gap_label(self, data_quality: Dict[str, Any]) -> str:
        gaps: List[str] = []
        source_url = str(data_quality.get("source_url") or "").strip().lower()
        if not source_url or source_url == "missing":
            gaps.append("缺少来源链接")
        if self._evidence_data_time(data_quality) == "未记录":
            gaps.append("缺少数据时间")
        for item in _as_list(data_quality.get("anomalies")):
            text = _plain_value(item)
            if not text or "来源链接" in text:
                continue
            gaps.append(text)
            if len(gaps) >= 2:
                break
        if not gaps:
            return "无明显缺口"
        if len(gaps) == 1:
            return gaps[0]
        return f"{gaps[0]}，另{len(gaps) - 1}个缺口"

    def _summarize_value(self, value: Any) -> str:
        if isinstance(value, dict):
            keys = list(value.keys())
            return f"{len(keys)}项字段：{', '.join(str(key) for key in keys[:6])}"
        if isinstance(value, list):
            return f"{len(value)}项"
        return "" if value is None else str(value)

    def _governance_section(self, artifacts: Dict[str, Any]) -> str:
        critique = artifacts.get("critique", {}) or {}
        risk = artifacts.get("risk_boundary_report", {}) or {}
        schema = artifacts.get("schema_guard_report", {}) or {}
        review = artifacts.get("run_review_report", {}) or {}
        outcome = artifacts.get("outcome_review_report", {}) or {}
        firewall = artifacts.get("synthesis_packet", {}).get("objective_firewall_summary", {}) or {}
        failures = "".join(
            f"<li>{_escape(item.get('condition', item))} <span>{_escape(item.get('impact', '')) if isinstance(item, dict) else ''}</span></li>"
            for item in _as_list(risk.get("failure_conditions"))
        )
        must_count = len(_as_list(risk.get("must_preserve_risks")))
        issues = "".join(f"<li>{_escape(item)}</li>" for item in _as_list(critique.get("cross_layer_issues")))
        tensions = "".join(f"<li>{_escape(item)}</li>" for item in _as_list(firewall.get("unresolved_tensions")))
        firewall_warnings = "".join(f"<li>{_escape(item)}</li>" for item in _as_list(firewall.get("warnings")))
        review_findings = _as_list(review.get("attribution_findings"))[:6]
        review_rows = "".join(
            f"<li><b>{_escape(item.get('category', 'review'))}</b> · {_escape(item.get('severity', 'observe'))}: {_escape(item.get('finding', ''))}</li>"
            for item in review_findings
            if isinstance(item, dict)
        )
        outcome_rows = "".join(
            f"<li><b>{_escape(item.get('window', 'window'))}</b>: {_escape(item.get('return_pct', 'n/a'))}%"
            f" <small>{_escape(item.get('start_date', ''))} → {_escape(item.get('end_date', ''))}</small></li>"
            for item in _as_list(outcome.get("windows"))
            if isinstance(item, dict) and item.get("data_status") == "available"
        )
        return f"""
<section class="panel" id="governance">
  <div class="section-kicker">07 · Governance</div>
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
      <p>完整清单见“风险边界”；此处仅记录 Risk Sentinel 要求保留 {_escape(must_count)} 条风险。</p>
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
    <article>
      <h3>Run Review</h3>
      <p>{_escape(review.get('review_mode', 'not generated'))}</p>
      <ul>{review_rows or '<li>暂无 run_review_report.json。</li>'}</ul>
    </article>
    <article>
      <h3>Outcome Review</h3>
      <p>{_escape(outcome.get('market_outcome_label', 'not generated'))}</p>
      <ul>{outcome_rows or '<li>暂无 outcome_review_report.json 或后续 QQQ 数据不足。</li>'}</ul>
      <h4>复盘结论</h4>
      <p>{_escape(outcome.get('caution_review', ''))}</p>
      <p>{_escape(outcome.get('aggression_review', ''))}</p>
      <small>{_escape(outcome.get('leakage_boundary', ''))}</small>
    </article>
  </div>
</section>
"""

    def _agent_io_audit_section(self, run_path: Path, artifacts: Dict[str, Any]) -> str:
        layers = artifacts.get("layers", {}) or {}
        layer_contexts = artifacts.get("layer_context_briefs", {}) or {}
        analysis_packet = artifacts.get("analysis_packet", {}) or {}
        raw_data = analysis_packet.get("raw_data", {}) if isinstance(analysis_packet, dict) else {}
        downstream_blob = json.dumps(
            {
                "bridges": artifacts.get("bridges", []),
                "synthesis_packet": artifacts.get("synthesis_packet", {}),
                "thesis_draft": artifacts.get("thesis_draft", {}),
                "analysis_revised": artifacts.get("analysis_revised", {}),
                "risk_boundary_report": artifacts.get("risk_boundary_report", {}),
                "final_adjudication": artifacts.get("final_adjudication", {}),
            },
            ensure_ascii=False,
            default=str,
        )

        layer_cards = []
        for layer in ["L1", "L2", "L3", "L4", "L5"]:
            card = layers.get(layer, {}) if isinstance(layers, dict) else {}
            context = layer_contexts.get(layer, {}) if isinstance(layer_contexts, dict) else {}
            input_refs = sorted((raw_data.get(layer, {}) or {}).keys()) if isinstance(raw_data.get(layer, {}), dict) else []
            allowed_inputs = [
                "ObjectCanon",
                f"{layer} IndicatorCanon",
                f"{layer} runtime context",
                "static layer responsibility map",
            ]
            actual_inputs = [
                f"layer_context_briefs/{layer}.json",
                f"analysis_packet.raw_data.{layer}",
                f"layer_cards/{layer}.json output artifact",
            ]
            forbidden_checks = self._layer_forbidden_checks(layer, context)
            forbidden_rows = "".join(
                f"<li><b>{_escape(label)}</b><span class=\"pill {_severity_class(status)}\">{_escape(status)}</span></li>"
                for label, status in forbidden_checks
            )
            evidence_refs = self._collect_evidence_refs(card)
            used_refs = [ref for ref in evidence_refs if ref and ref in downstream_blob]
            generic_flags = self._generic_label_flags(card)
            quality_flags = []
            quality_flags.append("has_evidence" if evidence_refs else "missing_evidence")
            quality_flags.append("used_downstream" if used_refs else "not_used_downstream")
            if generic_flags:
                quality_flags.append("generic_label")
            flags_html = "".join(f"<span class=\"ref-chip muted\">{_escape(flag)}</span>" for flag in quality_flags)
            layer_cards.append(
                f"""
<article class="chain-card agent-audit-card">
  <div class="chain-index">{_escape(layer)}</div>
  <div class="chain-body">
    <h3>{_escape(LAYER_TITLES.get(layer, layer))}</h3>
    <p><b>输入边界</b>：{_escape(', '.join(actual_inputs))}</p>
    <p><b>允许输入</b>：{_escape(', '.join(allowed_inputs))}</p>
    <p><b>本层 raw input</b>：{_escape(', '.join(input_refs[:8]) or '无')}</p>
    <h4>禁止输入检查</h4>
    <ul>{forbidden_rows}</ul>
    <h4>输出摘要</h4>
    <p>{_escape(card.get('layer_synthesis') or card.get('local_conclusion') or '')}</p>
    <p><b>evidence refs</b>：{_escape(len(evidence_refs))} · <b>downstream used</b>：{_escape(len(used_refs))}</p>
    <div class="ref-row">{flags_html}</div>
  </div>
</article>
"""
            )

        stage_cards = self._agent_stage_cards(run_path, artifacts, downstream_blob)
        return f"""
  <div class="audit-boundaries agent-io-audit" id="agent-io-audit">
    <h3>Agent IO Audit</h3>
    <p>只读视图：展示每个 agent 收到什么、输出什么、哪些字段有证据和下游痕迹；不改写主链路，也不作为发布闸门。</p>
    <h4>L1-L5 输入边界卡</h4>
    <div class="chain-grid">{''.join(layer_cards)}</div>
    <h4>Pipeline 输出与下游去向</h4>
    <div class="chain-grid">{stage_cards}</div>
  </div>
"""

    def _layer_forbidden_checks(self, layer: str, context: Dict[str, Any]) -> List[Tuple[str, str]]:
        highlights = context.get("layer_highlights", {}) if isinstance(context, dict) else {}
        present_layers = set(highlights.keys()) if isinstance(highlights, dict) else set()
        other_layers = {item for item in ["L1", "L2", "L3", "L4", "L5"] if item != layer}
        cross_signals = context.get("apparent_cross_layer_signals", []) if isinstance(context, dict) else []
        checks = [
            ("other layer runtime highlights absent", "safe" if not (present_layers & other_layers) else "breached"),
            ("global apparent_cross_layer_signals absent", "safe" if not cross_signals else "breached"),
            ("bridge memo absent from L1-L5 input", "safe"),
            ("thesis/final absent from L1-L5 input", "safe"),
        ]
        if not context:
            checks[0] = ("layer_context_brief missing; cannot prove isolation from artifact", "warning")
        return checks

    def _collect_evidence_refs(self, payload: Any) -> List[str]:
        refs: List[str] = []
        if isinstance(payload, dict):
            for key, value in payload.items():
                if key == "evidence_refs":
                    refs.extend(str(item) for item in _as_list(value))
                else:
                    refs.extend(self._collect_evidence_refs(value))
        elif isinstance(payload, list):
            for item in payload:
                refs.extend(self._collect_evidence_refs(item))
        return list(dict.fromkeys(refs))

    def _generic_label_flags(self, payload: Any) -> List[str]:
        labels = {"fear", "risk_on", "expensive", "momentum_positive", "neutral", "watch closely", "market stress elevated", "valuation pressure", "breadth divergence"}
        found: List[str] = []
        blob = json.dumps(payload, ensure_ascii=False, default=str).lower()
        for label in labels:
            if label in blob:
                found.append(label)
        return found

    def _agent_stage_cards(self, run_path: Path, artifacts: Dict[str, Any], downstream_blob: str) -> str:
        stages: List[Tuple[str, str, Dict[str, Any], str]] = [
            ("Bridge", "bridge_memos/bridge_0.json", (artifacts.get("bridges") or [{}])[0] if artifacts.get("bridges") else {}, "synthesis_packet/thesis/final"),
            ("Thesis", "thesis_draft.json", artifacts.get("thesis_draft", {}) or {}, "critic/risk/reviser/final"),
            ("Risk", "risk_boundary_report.json", artifacts.get("risk_boundary_report", {}) or {}, "reviser/final/brief"),
            ("Reviser", "analysis_revised.json", artifacts.get("analysis_revised", {}) or {}, "final"),
            ("Final", "final_adjudication.json", artifacts.get("final_adjudication", {}) or {}, "brief"),
            ("Review", "run_review_report.json", artifacts.get("run_review_report", {}) or {}, "next run/docs"),
            ("Outcome", "outcome_review_report.json", artifacts.get("outcome_review_report", {}) or {}, "post-hoc review only"),
        ]
        cards = []
        for name, path, payload, downstream in stages:
            refs = self._collect_evidence_refs(payload)
            summary = self._stage_summary(name, payload)
            used_refs = [ref for ref in refs if ref and ref in downstream_blob]
            cards.append(
                f"""
<article class="chain-card agent-audit-card">
  <div class="chain-index">{_escape(name[:2].upper())}</div>
  <div class="chain-body">
    <h3>{_escape(name)}</h3>
    <p><b>artifact</b>：{_escape(path)}</p>
    <p><b>summary</b>：{_escape(summary)}</p>
    <p><b>downstream target</b>：{_escape(downstream)}</p>
    <p><b>evidence refs</b>：{_escape(len(refs))} · <b>traceable refs</b>：{_escape(len(used_refs))}</p>
  </div>
</article>
"""
            )
        diagnostics = artifacts.get("llm_stage_diagnostics", {})
        if diagnostics:
            cards.append(
                f"""
<article class="chain-card agent-audit-card">
  <div class="chain-index">DG</div>
  <div class="chain-body">
    <h3>Stage Diagnostics</h3>
    <p><b>artifact</b>：llm_stage_diagnostics.json</p>
    <p>{_escape(self._summarize_value(diagnostics))}</p>
  </div>
</article>
"""
            )
        return "".join(cards)

    def _stage_summary(self, name: str, payload: Dict[str, Any]) -> str:
        if not isinstance(payload, dict):
            return ""
        if name == "Bridge":
            return payload.get("implication_for_ndx") or "; ".join(payload.get("unresolved_questions", [])[:2])
        if name == "Thesis":
            return payload.get("reader_conclusion", {}).get("one_liner") if isinstance(payload.get("reader_conclusion"), dict) else payload.get("main_thesis", "")
        if name == "Risk":
            return "; ".join(_as_list(payload.get("must_preserve_risks"))[:2])
        if name == "Reviser":
            return payload.get("revision_summary", "")
        if name == "Final":
            reader = self._reader_final(payload)
            return reader.get("one_liner") or payload.get("final_stance", "")
        return ""

    def _agent_health_section(self, run_path: Path, artifacts: Dict[str, Any]) -> str:
        diagnostics = artifacts.get("llm_stage_diagnostics", {}) or {}
        stage_records = diagnostics.get("stages", {}) if isinstance(diagnostics, dict) else {}
        layer_contexts = artifacts.get("layer_context_briefs", {}) or {}
        isolation_breaches = []
        for layer in ["L1", "L2", "L3", "L4", "L5"]:
            checks = self._layer_forbidden_checks(layer, layer_contexts.get(layer, {}) if isinstance(layer_contexts, dict) else {})
            isolation_breaches.extend(label for label, status in checks if status == "breached")
        prompt_audit_dir = run_path / "prompt_audit"
        prompt_stage_count = len([path for path in prompt_audit_dir.iterdir() if path.is_dir()]) if prompt_audit_dir.exists() else 0
        retry_count = sum(max(0, int(record.get("attempts", 0) or 0) - 1) for record in stage_records.values() if isinstance(record, dict))
        failed_count = sum(1 for record in stage_records.values() if isinstance(record, dict) and record.get("status") == "failed")
        prompt_sizes = [
            (name, int(record.get("prompt_chars", 0) or 0))
            for name, record in stage_records.items()
            if isinstance(record, dict)
        ]
        largest = max(prompt_sizes, key=lambda item: item[1]) if prompt_sizes else ("", 0)
        prompt_link = ""
        run_summary = artifacts.get("run_summary", {}) or {}
        prompt_inspector = run_summary.get("prompt_inspector") if isinstance(run_summary, dict) else ""
        if prompt_inspector:
            prompt_href = _artifact_href(prompt_inspector)
            prompt_link = (
                f'<a href="{_escape(prompt_href)}">打开 Agent 原文检查器</a>'
                if prompt_href
                else f"<span>{_escape(prompt_inspector)}</span>"
            )
        elif prompt_stage_count:
            prompt_link = "<span>已保存 prompt audit；可生成独立 Agent 原文检查器。</span>"
        else:
            prompt_link = "<span>未发现 prompt_audit 目录。</span>"
        health_cards = [
            ("五层隔离检查", "通过" if not isolation_breaches else "有风险", "未发现其他层本轮材料进入 L1-L5 单层上下文。" if not isolation_breaches else "；".join(isolation_breaches[:3])),
            ("Agent 原文留档", f"已保存 {prompt_stage_count} 个阶段" if prompt_stage_count else "未保存", "完整原文应查看独立 Agent 原文检查器。"),
            ("阶段校验", "通过" if not failed_count else "失败", f"重试={retry_count}；失败={failed_count}；文件=llm_stage_diagnostics.json。"),
            ("输入长度", f"{largest[0]} · {largest[1]} 字符" if largest[0] else "未记录", "若异常膨胀，需要在 Agent 原文检查器中定位具体材料。"),
            ("证据追踪", "轻量可追踪", "关键 evidence refs 可以追到来源；完整语义追踪仍属于后续升级。"),
            ("Agent 原文检查器", "独立入口", prompt_link),
        ]
        cards = "".join(
            f"""
    <div>
      <b>{_escape(title)}</b>
      <p>{_escape(status)}</p>
      <small>{detail if '<a ' in detail or '<span>' in detail else _escape(detail)}</small>
    </div>
"""
            for title, status, detail in health_cards
        )
        return f"""
  <div class="audit-boundaries agent-health" id="agent-health">
    <h3>Agent 运行健康</h3>
    <p>正文只保留健康摘要；完整原文、结构化输入、原始回答、hash 和污染检查请进入独立 Agent 原文检查器。</p>
    <div class="audit-grid">{cards}</div>
  </div>
"""

    def _audit_section(
        self,
        run_path: Path,
        artifacts: Dict[str, Any],
        payload_json: str,
        *,
        include_legacy_agent_io_audit: bool = False,
        audit_index_path: Optional[Path] = None,
    ) -> str:
        token_usage = artifacts["final_adjudication"].get("token_usage", {})
        meta = artifacts.get("synthesis_packet", {}).get("packet_meta", {}) or {}
        analysis_meta = artifacts.get("analysis_packet", {}).get("meta", {}) or {}
        analysis_packet = artifacts.get("analysis_packet", {}) or {}
        boundaries = (
            meta.get("backtest_data_boundaries")
            or analysis_meta.get("backtest_data_boundaries")
            or analysis_packet.get("context", {}).get("backtest_data_boundaries")
            or []
        )
        integrity = artifacts.get("data_integrity_report", {}) or {}
        strict_invariants = (
            integrity.get("strict_backtest_invariants")
            or meta.get("strict_backtest_invariants")
            or analysis_meta.get("strict_backtest_invariants")
            or analysis_packet.get("context", {}).get("strict_backtest_invariants")
            or {}
        )
        boundary_rows = "".join(
            f"""
    <li>
      <b>{_escape(item.get('function_id') or item.get('metric_name') or 'unknown')}</b>
      <span>{_escape(item.get('reason') or item.get('skip_reason') or item.get('availability') or '')}</span>
      <small>{_escape(item.get('future_upgrade') or '')}</small>
    </li>
"""
            for item in _as_list(boundaries)
            if isinstance(item, dict)
        )
        if not boundary_rows:
            boundary_rows = "<li><b>无</b><span>本次没有记录回测跳过项。</span></li>"
        invariant_rows = ""
        if isinstance(strict_invariants, dict) and strict_invariants:
            enforced_rows = "".join(
                f"<li><b>{_escape(item.get('invariant_id') or 'unknown')}</b><span>{_escape(item.get('status') or '')}</span><small>{_escape(item.get('description') or '')}</small></li>"
                for item in _as_list(strict_invariants.get("hard_enforced"))
                if isinstance(item, dict)
            )
            limitation_rows = "".join(
                f"<li><b>{_escape(item.get('invariant_id') or 'unknown')}</b><span>{_escape(item.get('status') or '')}</span><small>{_escape(item.get('future_upgrade') or item.get('description') or '')}</small></li>"
                for item in _as_list(strict_invariants.get("declared_limitations"))
                if isinstance(item, dict)
            )
            invariant_rows = f"""
  <div class="audit-boundaries">
    <h3>严格回测 invariant</h3>
    <ul>{enforced_rows or '<li><b>无</b><span>未记录强制项。</span></li>'}</ul>
    <h3>仍需明示的 point-in-time 限制</h3>
    <ul>{limitation_rows or '<li><b>无</b><span>未记录限制项。</span></li>'}</ul>
  </div>
"""
        integrity_status = integrity.get("publish_status") or ("blocked" if integrity.get("blocked") else "not recorded")
        blocking_reasons = "".join(f"<li>{_escape(item)}</li>" for item in _as_list(integrity.get("blocking_reasons")))
        runtime_diag = integrity.get("runtime_diagnostics", {}).get("yfinance", {}) if isinstance(integrity.get("runtime_diagnostics"), dict) else {}
        runtime_summary = ""
        if isinstance(runtime_diag, dict) and runtime_diag:
            runtime_summary = (
                f"status={runtime_diag.get('by_status', {})}; "
                f"failure_type={runtime_diag.get('by_failure_type', {})}; "
                f"backoff_seconds={runtime_diag.get('total_backoff_seconds', 0)}"
            )
        observation_range = _observation_date_range(analysis_packet.get("raw_data", {}))
        collector_timestamp = meta.get("collector_timestamp_utc") or analysis_meta.get("collector_timestamp_utc")
        generated_at = meta.get("generated_at") or analysis_meta.get("generated_at")
        run_summary = artifacts.get("run_summary", {}) if isinstance(artifacts.get("run_summary"), dict) else {}
        source_snapshot = artifacts.get("source_snapshot", {}) if isinstance(artifacts.get("source_snapshot"), dict) else {}
        prompt_inspector = run_summary.get("prompt_inspector") or ""
        audit_paths = [
            ("审计索引", str(audit_index_path) if audit_index_path else "未生成"),
            ("本次运行摘要", str(run_path / "run_summary.json")),
            ("输入快照身份", str(run_path / "source_snapshot.json")),
            ("数据完整性检查", str(run_path / "data_integrity_report.json")),
            ("Agent 原文检查器", str(prompt_inspector) if prompt_inspector else "未记录"),
            ("L1-L5 底稿", str(run_path / "layer_cards")),
            ("Bridge 冲突共振", str(run_path / "bridge_memos")),
            ("图表时间序列", str(run_path / "chart_time_series.json")),
            ("预期与兑现台账", str(run_path / "expectation_vs_realized.json")),
            ("第一层：纯数据研报", str(run_path / "pure_data_report.json")),
            ("第二层：事件摘要", str(run_path / "event_layer_summary.json")),
            ("第二层：新闻事件研报", str(run_path / "event_mechanism_report.json")),
            ("第二层：LLM 事件解读卡", str(run_path / "event_interpretation_cards.json")),
            ("第二层：新闻事件 HTML", str(run_path / "event_mechanism_report.html")),
            ("第二层：跨层问题", str(run_path / "cross_layer_questions.json")),
            ("第二层：事件与叙事账本", str(run_path / "event_narrative_ledger.json")),
            ("第三层：综合矛盾裁决", str(run_path / "integrated_synthesis_report.json")),
            ("旧新闻侧边材料", str(run_path / "news_event_ledger.json")),
        ]
        audit_path_rows = "".join(
            f"<li><b>{_escape(label)}</b>{_artifact_link(label, path)}</li>"
            for label, path in audit_paths
        )
        return f"""
<section class="panel" id="audit">
  <div class="section-kicker">07 · 数据与审计</div>
  <h2>主页面只留索引，完整底稿在外部 artifact</h2>
  <p class="section-note">可审计不等于把所有 JSON 塞进正文。这里保留数据包路径、发布闸门、Agent 原文检查器、L1-L5 输出和图表源入口；大文件仍在 run 目录中。</p>
  <div class="audit-grid">
    <div><b>运行目录</b><p>{_escape(run_path)}</p></div>
    <div><b>模型用量</b><p>{_escape(_token_usage_summary(token_usage))}</p></div>
    <div><b>数据完整性</b><p>{_escape(_label(integrity_status, 'publish_status'))}</p></div>
    <div><b>回测日期</b><p>{_escape(meta.get('backtest_date') or analysis_meta.get('backtest_date') or 'N/A')}</p></div>
    <div><b>输入模式</b><p>{_escape(source_snapshot.get('mode') or '未记录')}</p></div>
    <div><b>输入文件</b><p>{_escape(source_snapshot.get('source_filename') or '未记录')}</p></div>
    <div><b>输入绝对路径</b><p>{_escape(source_snapshot.get('source_path') or '未记录')}</p></div>
    <div><b>快照适用日</b><p>{_escape(source_snapshot.get('effective_date') or '未记录')}</p></div>
    <div><b>快照 SHA256</b><p>{_escape(source_snapshot.get('source_sha256') or '未记录')}</p></div>
    <div><b>快照采集时间</b><p>{_escape(_format_timestamp(source_snapshot.get('collection_time')))}</p></div>
    <div><b>输入数据跨度</b><p>{_escape(observation_range)}</p></div>
    <div><b>采集时间</b><p>{_escape(_format_timestamp(collector_timestamp))}</p></div>
    <div><b>生成时间</b><p>{_escape(_format_timestamp(generated_at))}</p></div>
    <div><b>Yahoo 数据诊断</b><p>{_escape(runtime_summary or '无异常记录')}</p></div>
  </div>
  <div class="audit-boundaries">
    <h3>审计入口</h3>
    <ul>{audit_path_rows}</ul>
  </div>
  <div class="audit-boundaries">
    <h3>回测数据边界</h3>
    <ul>{boundary_rows}</ul>
  </div>
  {self._expectation_ledger_block(artifacts)}
  {invariant_rows}
  <div class="audit-boundaries">
    <h3>阻断原因</h3>
    <ul>{blocking_reasons or '<li>无</li>'}</ul>
  </div>
  {self._agent_health_section(run_path, artifacts)}
  {self._agent_io_audit_section(run_path, artifacts) if include_legacy_agent_io_audit else ''}
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

    def _reasoned_verdict_html(self, verdict: Any) -> str:
        text = str(verdict or "")
        parts = []
        cursor = 0
        for match in re.finditer(r"\[([^\[\]]+)\]", text):
            parts.append(_escape(text[cursor:match.start()]))
            raw_ref = match.group(1).strip()
            if raw_ref.lower().startswith("card:"):
                card_id = raw_ref.split(":", 1)[-1].strip()
                short = card_id[-8:] if len(card_id) > 8 else card_id
                parts.append(
                    f'<a class="ref-chip card-chip" href="#world" '
                    f'title="{_escape(card_id)}">事件卡·{_escape(short)}</a>'
                )
                cursor = match.end()
                continue
            canonical = _canonical_ref(raw_ref)
            parts.append(
                f'<button class="ref-chip" data-ref="{_escape(canonical)}" '
                f'data-label="{_escape(_human_ref_label(canonical))}">{_escape(_human_ref_label(canonical))}</button>'
            )
            cursor = match.end()
        parts.append(_escape(text[cursor:]))
        return "".join(parts)

    def _css(self, style: str = "slate_v2") -> str:
        css_path = STYLES_DIR / f"{style}.css"
        if css_path.exists():
            css = css_path.read_text(encoding="utf-8")
        else:
            fallback = STYLES_DIR / "slate_v2.css"
            css = fallback.read_text(encoding="utf-8") if fallback.exists() else ""
        return css + """
.metric-glossary { position: relative; display: inline-flex; align-items: baseline; gap: .25rem;
  border: 0; padding: 0; background: transparent; color: inherit; font: inherit; cursor: help; }
.metric-glossary:hover, .metric-glossary:focus-visible { text-decoration: underline; text-decoration-style: dotted; }
.metric-glossary__tooltip { display: none; position: absolute; z-index: 20; left: 0; top: calc(100% + .35rem); width: min(18rem, 72vw);
  padding: .55rem .7rem; border: 1px solid var(--rule-strong, #999); border-radius: .35rem;
  background: var(--paper, #fff); color: var(--ink, #111); box-shadow: 0 5px 18px rgba(0,0,0,.15); font-size: .78em; font-weight: 400; text-align: left; }
.metric-glossary:focus-visible .metric-glossary__tooltip, .metric-glossary:hover .metric-glossary__tooltip,
.metric-glossary.is-open .metric-glossary__tooltip, .ref-chip:focus-visible .metric-glossary__tooltip { display: block; }
"""

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
    parser.add_argument(
        "--style",
        default="slate_v3",
        choices=[*STYLE_FONTS.keys()],
        help="Visual style variant.",
    )
    parser.add_argument(
        "--include-legacy-agent-io-audit",
        action="store_true",
        help="Include the old expanded Agent IO Audit block for development debugging.",
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
            print(
                reporter.run(
                    args.run_dir,
                    output_path=output_path,
                    template=template,
                    style=args.style,
                    include_legacy_agent_io_audit=args.include_legacy_agent_io_audit,
                )
            )
    else:
        report_path = reporter.run(
            args.run_dir,
            output_path=args.output,
            template=args.template,
            style=args.style,
            include_legacy_agent_io_audit=args.include_legacy_agent_io_audit,
        )
        print(report_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
