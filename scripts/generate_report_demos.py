from __future__ import annotations

import argparse
import html
import json
import math
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


LAYERS = ["L1", "L2", "L3", "L4", "L5"]
LAYER_NAMES = {
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
    "unclear": "不清楚",
    "credit": "信用",
    "rates": "利率",
    "valuation": "估值",
    "technical_panic": "技术与恐慌",
    "liquidity": "流动性",
}

CONFIDENCE_LABELS = {
    "high": "高",
    "medium": "中",
    "low": "低",
    "very_high": "很高",
    "very_low": "很低",
}


def esc(value: Any) -> str:
    return html.escape("" if value is None else str(value), quote=True)


def load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def text(value: Any, limit: Optional[int] = None) -> str:
    raw = re.sub(r"\s+", " ", "" if value is None else str(value)).strip()
    if limit and len(raw) > limit:
        return raw[: limit - 1].rstrip() + "…"
    return raw


def sentence(value: Any, limit: int = 180) -> str:
    raw = text(value)
    if len(raw) <= limit:
        return raw
    for mark in "。；;，,":
        pos = raw.rfind(mark, 0, limit)
        if pos > 48:
            return raw[: pos + 1]
    return raw[: limit - 1].rstrip() + "…"


def split_sentences(value: Any, max_items: int = 3, item_limit: int = 84) -> List[str]:
    raw = text(value)
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
        snippets.append(sentence(clean, item_limit))
        if len(snippets) >= max_items:
            break
    return snippets or [sentence(raw, item_limit)]


def rich_text(value: Any) -> str:
    rendered = esc(value)
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


def summary_fragments(value: Any, max_items: int = 3) -> str:
    return "".join(
        f"<span>{rich_text(item)}</span>"
        for item in split_sentences(value, max_items=max_items, item_limit=96)
    )


def narrative_list(value: Any, max_items: int = 5) -> str:
    return "<ul class=\"narrative-list\">" + "".join(
        f"<li>{rich_text(item)}</li>"
        for item in split_sentences(value, max_items=max_items, item_limit=150)
    ) + "</ul>"


def format_hook(value: Any) -> str:
    if isinstance(value, dict):
        question = value.get("question")
        if isinstance(question, str) and question.strip().startswith("{"):
            try:
                nested = json.loads(question)
            except json.JSONDecodeError:
                nested = None
            if isinstance(nested, dict):
                question = nested.get("hook") or nested.get("question") or question
        parts = [
            value.get("target_layer"),
            question,
            value.get("rationale"),
        ]
        return sentence("，".join(str(part) for part in parts if part), 180)
    return sentence(value, 180)


def readable_structured(value: Any, limit: int = 420) -> str:
    if isinstance(value, dict):
        parts = []
        for key, item in value.items():
            if key == "covered_function_ids" and isinstance(item, list):
                parts.append(f"已覆盖指标 {len(item)} 个")
            elif isinstance(item, list):
                preview = "；".join(sentence(x, 80) for x in item[:3])
                if preview:
                    parts.append(f"{display_label(key)}：{preview}")
            elif isinstance(item, dict):
                nested = readable_structured(item, 120)
                if nested:
                    parts.append(f"{display_label(key)}：{nested}")
            elif item is not None:
                parts.append(f"{display_label(key)}：{item}")
        return sentence("；".join(parts), limit)
    if isinstance(value, list):
        return sentence("；".join(sentence(item, 90) for item in value[:4]), limit)
    return sentence(value, limit)


def metric_number(raw: Any) -> Optional[float]:
    if isinstance(raw, bool) or raw is None:
        return None
    if isinstance(raw, (int, float)):
        return float(raw)
    m = re.search(r"-?\d+(?:\.\d+)?", str(raw).replace(",", ""))
    return float(m.group(0)) if m else None


def numeric_series(rows: Sequence[Dict[str, Any]], field: str = "value") -> List[float]:
    values: List[float] = []
    for row in rows:
        value = metric_number(row.get(field))
        if value is not None and math.isfinite(value):
            values.append(value)
    return values


def percentile_rank(values: Sequence[float], current: float) -> Optional[float]:
    clean = [value for value in values if math.isfinite(value)]
    if not clean:
        return None
    return 100 * sum(value <= current for value in clean) / len(clean)


def fmt_pct(value: Optional[float], digits: int = 0, signed: bool = False) -> str:
    if value is None or not math.isfinite(value):
        return "N/A"
    sign = "+" if signed and value > 0 else ""
    return f"{sign}{value:.{digits}f}%"


def fmt_num(value: Optional[float], digits: int = 2) -> str:
    if value is None or not math.isfinite(value):
        return "N/A"
    return f"{value:.{digits}f}"


def fmt_bps(value: Optional[float]) -> str:
    if value is None or not math.isfinite(value):
        return "N/A"
    bps = value * 100
    return f"{bps:+.0f}bp"


def normalize_percentile(value: Any) -> Optional[float]:
    number = metric_number(value)
    if number is None or not math.isfinite(number):
        return None
    return number * 100 if 0 <= number <= 1 else number


def fmt_percentile(value: Any, digits: int = 0) -> str:
    percentile = normalize_percentile(value)
    if percentile is None:
        return "N/A"
    return f"{percentile:.{digits}f}%"


def raw_indicator(bundle: Dict[str, Any], layer: str, function_id: str) -> Dict[str, Any]:
    raw = bundle.get("packet", {}).get("raw_data", {})
    item = raw.get(layer, {}).get(function_id, {}) if isinstance(raw, dict) else {}
    value = item.get("value") if isinstance(item, dict) else {}
    return value if isinstance(value, dict) else {}


def historical_percentile(
    bundle: Dict[str, Any],
    layer: str,
    function_id: str,
    window: str = "10y",
) -> Optional[float]:
    value = raw_indicator(bundle, layer, function_id)
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
        percentile = normalize_percentile(candidate)
        if percentile is not None:
            return percentile
    return None


def reading_percentile_label(reading: Any) -> Optional[str]:
    raw = str(reading or "")
    match = re.search(r"(10\s*年(?:分位|百分位))\s*[:：]?\s*(\d+(?:\.\d+)?)%", raw)
    if match:
        return f"10年分位 {float(match.group(2)):.0f}%"
    match = re.search(r"(5\s*年(?:分位|百分位))\s*[:：]?\s*(\d+(?:\.\d+)?)%", raw)
    if match:
        return f"5年分位 {float(match.group(2)):.0f}%"
    return None


def ref_label(ref: str) -> str:
    label = str(ref or "")
    if "." in label:
        label = label.split(".", 1)[1]
    if ":" in label:
        label = label.split(":", 1)[0]
    return label.replace("get_", "").replace("_", " ")


def display_label(value: Any) -> str:
    raw = str(value or "")
    return DISPLAY_LABELS.get(raw, raw.replace("_", " "))


def confidence_label(value: Any) -> str:
    raw = str(value or "")
    return CONFIDENCE_LABELS.get(raw.lower(), display_label(raw))


def ref_chips(refs: Iterable[Any]) -> str:
    chips = []
    for ref in list(refs)[:6]:
        chips.append(f"<span class=\"ref\">{esc(ref_label(str(ref)))}</span>")
    return "".join(chips)


def read_bundle(run_dir: Path) -> Dict[str, Any]:
    layers = {
        layer: load_json(run_dir / "layer_cards" / f"{layer}.json", {})
        for layer in LAYERS
    }
    return {
        "run_dir": run_dir,
        "final": load_json(run_dir / "final_adjudication.json", {}),
        "synthesis": load_json(run_dir / "synthesis_packet.json", {}),
        "risk": load_json(run_dir / "risk_boundary_report.json", {}),
        "critique": load_json(run_dir / "critique.json", {}),
        "bridge": load_json(run_dir / "bridge_memos" / "bridge_0.json", {}),
        "review": load_json(run_dir / "run_review_report.json", {}),
        "integrity": load_json(run_dir / "data_integrity_report.json", {}),
        "schema": load_json(run_dir / "schema_guard_report.json", {}),
        "charts": load_json(run_dir / "chart_time_series.json", {}),
        "packet": load_json(run_dir / "analysis_packet.json", {}),
        "layers": layers,
    }


def indicator_lookup(bundle: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    index: Dict[str, Dict[str, Any]] = {}
    for layer, card in bundle["layers"].items():
        for item in as_list(card.get("indicator_analyses")):
            if isinstance(item, dict):
                index[f"{layer}.{item.get('function_id')}"] = item
    return index


def chart_rows(bundle: Dict[str, Any], key: str) -> List[Dict[str, Any]]:
    series = bundle.get("charts", {}).get("series", {})
    item = series.get(key) if isinstance(series, dict) else None
    rows = item.get("rows") if isinstance(item, dict) else None
    return rows if isinstance(rows, list) else []


def stat_chip(label: str, value: str, tone: str = "neutral") -> str:
    return (
        f"<span class=\"stat-chip {esc(tone)}\">"
        f"<b>{esc(label)}</b><strong>{esc(value)}</strong>"
        "</span>"
    )


def series_delta(rows: Sequence[Dict[str, Any]], field: str, periods: int) -> Optional[float]:
    values = numeric_series(rows, field)
    if len(values) <= periods:
        return None
    return values[-1] - values[-1 - periods]


def series_return(rows: Sequence[Dict[str, Any]], field: str, periods: int) -> Optional[float]:
    values = numeric_series(rows, field)
    if len(values) <= periods or abs(values[-1 - periods]) < 0.000001:
        return None
    return (values[-1] / values[-1 - periods] - 1) * 100


def series_percentile(rows: Sequence[Dict[str, Any]], field: str, lookback: int = 252) -> Optional[float]:
    values = numeric_series(rows, field)
    if not values:
        return None
    return percentile_rank(values[-lookback:], values[-1])


def short_date(value: Any) -> str:
    raw = str(value or "")
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", raw)
    if match:
        return f"{match.group(1)[2:]}.{match.group(2)}.{match.group(3)}"
    match = re.search(r"(\d{4})-(\d{2})", raw)
    if match:
        return f"{match.group(1)[2:]}.{match.group(2)}"
    return raw[:8]


def parse_row_date(value: Any) -> Optional[datetime]:
    raw = str(value or "")
    for fmt, length in (("%Y-%m-%d", 10), ("%Y-%m", 7)):
        try:
            return datetime.strptime(raw[:length], fmt)
        except ValueError:
            continue
    return None


def spark_sample(rows: Sequence[Dict[str, Any]], years: Optional[float]) -> List[Dict[str, Any]]:
    all_rows = list(rows)
    if not all_rows:
        return []
    if years is None:
        return all_rows[-90:]
    end_date = next((parse_row_date(row.get("time")) for row in reversed(all_rows) if parse_row_date(row.get("time"))), None)
    if end_date is None:
        return all_rows
    cutoff = end_date - timedelta(days=int(365.25 * years))
    sample = [row for row in all_rows if (parse_row_date(row.get("time")) or end_date) >= cutoff]
    return sample if len(sample) >= 2 else all_rows


def downsample_rows(rows: Sequence[Dict[str, Any]], max_points: int) -> List[Dict[str, Any]]:
    items = list(rows)
    if len(items) <= max_points:
        return items
    if max_points < 2:
        return items[-max_points:]
    last_index = len(items) - 1
    indexes = sorted({round(i * last_index / (max_points - 1)) for i in range(max_points)})
    return [items[index] for index in indexes]


def years_from_annotation(annotation: Optional[str]) -> Optional[int]:
    raw = annotation or ""
    if "10年分位" in raw or "10 年分位" in raw:
        return 10
    if "5年分位" in raw or "5 年分位" in raw:
        return 5
    return None


def sparkline(
    rows: Sequence[Dict[str, Any]],
    field: str = "value",
    width: int = 420,
    height: int = 92,
    annotation: Optional[str] = None,
    show_guide: bool = True,
    window_years: Optional[float] = None,
    max_points: int = 180,
) -> str:
    values: List[Tuple[int, float]] = []
    sample = downsample_rows(
        spark_sample(rows, window_years if window_years is not None else years_from_annotation(annotation)),
        max_points,
    )
    for i, row in enumerate(sample):
        value = metric_number(row.get(field))
        if value is not None and math.isfinite(value):
            values.append((i, value))
    if len(values) < 2:
        return "<svg class=\"spark\" viewBox=\"0 0 420 92\" role=\"img\"></svg>"
    low = min(v for _, v in values)
    high = max(v for _, v in values)
    if abs(high - low) < 0.0001:
        high = low + 1
    pad = 10
    denom = max(1, len(sample) - 1)
    path = []
    for i, value in values:
        x = pad + (width - pad * 2) * i / denom
        y = pad + (height - pad * 2) * (1 - (value - low) / (high - low))
        path.append(("M" if not path else "L") + f"{x:.1f},{y:.1f}")
    first = values[0][1]
    last = values[-1][1]
    direction = "up" if last >= first else "down"
    pct = percentile_rank([value for _, value in values], last)
    last_i = values[-1][0]
    last_x = pad + (width - pad * 2) * last_i / denom
    last_y = pad + (height - pad * 2) * (1 - (last - low) / (high - low))
    label_y = max(18, min(height - 18, last_y - 8))
    start = short_date(next((row.get("time") for row in sample if row.get("time")), ""))
    requested_years = window_years if window_years is not None else years_from_annotation(annotation)
    first_date = next((parse_row_date(row.get("time")) for row in sample if parse_row_date(row.get("time"))), None)
    end_date = next((parse_row_date(row.get("time")) for row in reversed(sample) if parse_row_date(row.get("time"))), None)
    coverage_years = ((end_date - first_date).days / 365.25) if first_date and end_date else None
    label = annotation or (f"图内位置 {pct:.0f}%" if pct is not None else "图内位置 N/A")
    if annotation and requested_years and coverage_years is not None and coverage_years < requested_years * 0.8:
        label = f"{label} · 图自{start}"
    guide = (
        f"<line class=\"pct-guide\" x1=\"10\" x2=\"{last_x:.1f}\" y1=\"{last_y:.1f}\" y2=\"{last_y:.1f}\"/>"
        if show_guide
        else ""
    )
    return (
        f"<svg class=\"spark {direction}\" viewBox=\"0 0 {width} {height}\" role=\"img\">"
        f"{guide}"
        f"<text class=\"pct-label\" x=\"10\" y=\"{label_y:.1f}\">{esc(label)}</text>"
        f"<path d=\"{' '.join(path)}\"/>"
        f"<text class=\"spark-start\" x=\"10\" y=\"{height - 6}\">{esc(start)}</text>"
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
    "get_qqq_qqew_ratio": ("QQQ_QQEW_RATIO", "value"),
    "get_equity_risk_premium": ("DAMODARAN_ERP_MONTHLY", "value"),
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


def compact_value(value: Optional[float], digits: int = 2, suffix: str = "") -> str:
    if value is None or not math.isfinite(value):
        return "N/A"
    if abs(value) >= 1_000_000_000:
        return f"{value / 1_000_000_000:.1f}B{suffix}"
    if abs(value) >= 1_000_000:
        return f"{value / 1_000_000:.1f}M{suffix}"
    return f"{value:.{digits}f}{suffix}"


def indicator_value_from_reading(function_id: str, reading: Any, fallback: Optional[float]) -> Optional[float]:
    raw = str(reading or "")
    if function_id == "get_macd_qqq":
        match = re.search(r"柱\s*(-?\d+(?:\.\d+)?)", raw)
        if match:
            return float(match.group(1))
    value = metric_number(raw)
    return value if value is not None else fallback


def micro_annotation(function_id: str, rows: Sequence[Dict[str, Any]], field: str, reading: Any = None) -> Tuple[Optional[str], bool]:
    values = numeric_series(rows[-90:], field)
    last = values[-1] if values else None
    current = indicator_value_from_reading(function_id, reading, last)
    pct = percentile_rank(values, last) if last is not None else None
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
        "get_qqq_qqew_ratio",
        "get_damodaran_us_implied_erp",
    }:
        return (reading_percentile_label(reading) or (f"图内位置 {pct:.0f}%" if pct is not None else None), True)
    if function_id == "get_net_liquidity_momentum":
        delta20 = series_delta(rows, field, 20)
        return (f"20日变化 {compact_value(delta20, 1, 'B')}", False)
    if function_id == "get_hyg_momentum":
        return (f"20日变化 {fmt_pct(series_return(rows, field, 20), 1, signed=True)}", True)
    if function_id == "get_vxn_vix_ratio":
        return (f"比值 {compact_value(last, 2)}", True)
    if function_id in {"get_l5_deterministic_snapshot", "get_qqq_technical_indicators", "get_donchian_channels_qqq", "get_multi_scale_ma_position"}:
        return (f"价格 {compact_value(current, 2)}", True)
    if function_id == "get_rsi_qqq":
        return (f"RSI {compact_value(current, 1)}", True)
    if function_id == "get_atr_qqq":
        return (f"ATR {compact_value(current, 2)}", False)
    if function_id == "get_macd_qqq":
        return (f"MACD柱 {compact_value(current, 2)}", True)
    if function_id == "get_obv_qqq":
        return (f"OBV {compact_value(last, 1)}", False)
    if function_id == "get_volume_analysis_qqq":
        return (f"成交量 {compact_value(last, 1)}", False)
    if function_id == "get_price_volume_quality_qqq":
        return (f"CMF {compact_value(last, 2)}", True)
    if function_id == "get_equity_risk_premium":
        return (f"ERP {compact_value(last, 2, '%')}", True)
    return (None, True)


def indicator_micro_chart(bundle: Dict[str, Any], indicator: Any) -> str:
    if isinstance(indicator, dict):
        fid = str(indicator.get("function_id") or "")
        reading = indicator.get("current_reading")
    else:
        fid = str(indicator or "")
        reading = None
    mapping = INDICATOR_CHARTS.get(fid)
    if not mapping:
        return ""
    key, field = mapping
    rows = chart_rows(bundle, key)
    if len(rows) < 2:
        return ""
    annotation, show_guide = micro_annotation(fid, rows, field, reading)
    return f"<div class=\"indicator-micro\">{sparkline(rows, field, width=260, height=76, annotation=annotation, show_guide=show_guide)}</div>"


def kpi_from_indicator(index: Dict[str, Dict[str, Any]], ref: str, fallback: str = "N/A") -> str:
    item = index.get(ref, {})
    return sentence(item.get("current_reading") or fallback, 76)


def theme_tokens(mode: str) -> str:
    themes = {
        "warm": """
  --bg: oklch(0.968 0.012 78);
  --paper: oklch(0.992 0.006 82);
  --paper-2: oklch(0.946 0.014 78);
  --ink: oklch(0.18 0.018 72);
  --soft: oklch(0.34 0.024 72);
  --muted: oklch(0.54 0.024 72);
  --rule: oklch(0.81 0.018 76);
  --blue: oklch(0.42 0.105 226);
  --red: oklch(0.49 0.16 30);
  --amber: oklch(0.58 0.13 74);
  --green: oklch(0.43 0.105 156);
  --violet: oklch(0.44 0.075 292);
  --cyan: oklch(0.48 0.09 205);
  --panel-tint: oklch(0.936 0.018 76);
""",
        "crisp": """
  --bg: oklch(0.972 0.007 218);
  --paper: oklch(0.992 0.004 220);
  --paper-2: oklch(0.948 0.010 218);
  --ink: oklch(0.18 0.014 236);
  --soft: oklch(0.35 0.020 236);
  --muted: oklch(0.54 0.020 236);
  --rule: oklch(0.82 0.014 228);
  --blue: oklch(0.43 0.12 244);
  --red: oklch(0.52 0.15 28);
  --amber: oklch(0.61 0.12 76);
  --green: oklch(0.46 0.11 160);
  --violet: oklch(0.45 0.09 292);
  --cyan: oklch(0.48 0.10 198);
  --panel-tint: oklch(0.936 0.016 224);
""",
    }
    return themes.get(
        mode,
        """
  --bg: oklch(0.97 0.010 86);
  --paper: oklch(0.993 0.005 86);
  --paper-2: oklch(0.948 0.012 86);
  --ink: oklch(0.18 0.015 80);
  --soft: oklch(0.34 0.020 80);
  --muted: oklch(0.54 0.018 80);
  --rule: oklch(0.81 0.015 84);
  --blue: oklch(0.42 0.115 238);
  --red: oklch(0.51 0.16 28);
  --amber: oklch(0.61 0.13 78);
  --green: oklch(0.45 0.11 154);
  --violet: oklch(0.44 0.085 292);
  --cyan: oklch(0.48 0.095 205);
  --panel-tint: oklch(0.936 0.016 84);
""",
    )


def base_css(mode: str) -> str:
    type_mode = """
  --font-body: ui-serif, "Songti SC", "STSong", "Noto Serif SC", Georgia, serif;
  --font-heading: ui-serif, "Songti SC", "STSong", "Noto Serif SC", Georgia, serif;
""" if mode != "crisp" else """
  --font-body: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Noto Sans SC", sans-serif;
  --font-heading: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Noto Sans SC", sans-serif;
"""
    return f"""
:root {{
{theme_tokens(mode)}
{type_mode}
  --font-ui: -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Noto Sans SC", sans-serif;
  --font-mono: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  --radius: 7px;
  --shadow-soft: 0 18px 45px color-mix(in oklch, var(--ink) 8%, transparent);
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: var(--font-body);
  font-size: 16px;
  line-height: 1.74;
  font-kerning: normal;
  text-rendering: optimizeLegibility;
}}
a {{ color: inherit; }}
.page {{ width: min(1180px, calc(100% - 40px)); margin: 0 auto; padding: 42px 0 88px; }}
.topline {{ font-family: var(--font-ui); color: var(--muted); font-size: 12px; letter-spacing: .08em; text-transform: uppercase; }}
h1, h2, h3 {{ margin: 0; line-height: 1.16; letter-spacing: 0; }}
h1 {{ font-family: var(--font-heading); font-size: 2.45rem; max-width: 900px; font-weight: 680; line-height: 1.14; }}
h2 {{ font-family: var(--font-heading); font-size: 1.68rem; margin-bottom: 14px; font-weight: 680; }}
h3 {{ font-family: var(--font-heading); font-size: 1.08rem; font-weight: 680; }}
p {{ margin: 0; }}
.deck {{ display: grid; gap: 20px; }}
.section {{ border-top: 1px solid var(--rule); padding-top: 28px; margin-top: 34px; }}
.lede {{ color: var(--soft); max-width: 70ch; font-size: 1.08rem; }}
.meta {{ display: flex; gap: 8px; flex-wrap: wrap; margin-top: 18px; font-family: var(--font-ui); }}
.pill, .ref {{
  display: inline-flex; align-items: center; min-height: 24px; padding: 3px 8px;
  border: 1px solid var(--rule); border-radius: 999px; background: color-mix(in oklch, var(--paper) 82%, transparent);
  color: var(--soft); font-size: 12px; font-family: var(--font-ui);
}}
.ref {{ border-radius: 4px; font-family: var(--font-mono); color: var(--blue); }}
.grid-2 {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 18px; }}
.grid-3 {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 16px; }}
.box {{ background: var(--paper); border: 1px solid var(--rule); border-radius: var(--radius); padding: 18px; }}
.box p, .box li {{ color: var(--soft); }}
.small {{ color: var(--muted); font-size: 13px; font-family: var(--font-ui); }}
ul.clean {{ list-style: none; padding: 0; margin: 0; display: grid; gap: 10px; }}
ul.clean li {{ padding-left: 18px; position: relative; }}
ul.clean li::before {{ content: ""; position: absolute; left: 0; top: .74em; width: 6px; height: 6px; background: var(--blue); border-radius: 50%; }}
.metric {{ display: grid; gap: 6px; padding: 14px 0; border-bottom: 1px solid var(--rule); }}
.metric:last-child {{ border-bottom: 0; }}
.metric b {{ font-family: var(--font-ui); font-size: 12px; color: var(--muted); text-transform: uppercase; letter-spacing: .06em; }}
.metric strong {{ font-size: 22px; line-height: 1.2; }}
.spark {{ width: 100%; height: 92px; overflow: visible; }}
.spark path {{ fill: none; stroke: var(--blue); stroke-width: 2.2; }}
.spark.down path {{ stroke: var(--red); }}
.spark text {{ font: 10px var(--font-mono); fill: var(--muted); }}
.spark .pct-guide {{ stroke: color-mix(in oklch, var(--blue) 32%, transparent); stroke-width: 1; stroke-dasharray: 3 4; }}
.spark .pct-label {{ font: 10px var(--font-ui); fill: var(--blue); }}
.memo-flow {{ display: grid; grid-template-columns: minmax(280px, .75fr) minmax(390px, 1.25fr); gap: 32px; align-items: start; }}
.memo-flow.memo-pair {{ grid-template-columns: 1fr; gap: 20px; }}
.memo-copy {{ display: grid; gap: 13px; max-width: 66ch; padding-top: 2px; }}
.memo-flow.memo-pair .memo-copy {{ max-width: 74ch; }}
.memo-flow.memo-pair > .grid-2 {{ grid-template-columns: repeat(2, minmax(300px, 1fr)); gap: 22px; }}
.memo-copy h2 {{ margin-bottom: 0; }}
.kicker {{ color: var(--blue); font: 12px var(--font-ui); letter-spacing: .04em; margin-bottom: -4px; }}
.proof-card {{ --card-accent: var(--blue); min-width: 0; background: linear-gradient(180deg, color-mix(in oklch, var(--card-accent) 7%, var(--paper)) 0%, var(--paper) 42%); border: 1px solid color-mix(in oklch, var(--card-accent) 32%, var(--rule)); border-radius: var(--radius); padding: 17px; display: grid; gap: 12px; box-shadow: var(--shadow-soft); }}
.proof-card.tone-macro {{ --card-accent: var(--violet); }}
.proof-card.tone-risk {{ --card-accent: var(--red); }}
.proof-card.tone-credit {{ --card-accent: var(--green); }}
.proof-card.tone-structure {{ --card-accent: var(--cyan); }}
.proof-card.tone-price {{ --card-accent: var(--blue); }}
.proof-head {{ display: flex; align-items: baseline; justify-content: space-between; gap: 12px; }}
.proof-head h3 {{ font-size: 1.16rem; overflow-wrap: anywhere; }}
.proof-layer {{ color: var(--card-accent); font: 12px var(--font-mono); white-space: nowrap; }}
.stat-rail {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(94px, 1fr)); gap: 8px; }}
.stat-chip {{ min-height: 56px; border: 1px solid color-mix(in oklch, var(--card-accent) 18%, var(--rule)); border-radius: 6px; padding: 8px 9px; background: color-mix(in oklch, var(--card-accent) 6%, var(--paper-2)); display: grid; align-content: center; gap: 2px; }}
.stat-chip b {{ color: var(--muted); font: 11px var(--font-ui); }}
.stat-chip strong {{ color: var(--ink); font: 16px var(--font-mono); line-height: 1.15; font-variant-numeric: tabular-nums; }}
.stat-chip.risk {{ background: color-mix(in oklch, var(--red) 8%, var(--paper-2)); border-color: color-mix(in oklch, var(--red) 30%, var(--rule)); }}
.stat-chip.risk strong {{ color: var(--red); }}
.stat-chip.good {{ background: color-mix(in oklch, var(--green) 8%, var(--paper-2)); border-color: color-mix(in oklch, var(--green) 30%, var(--rule)); }}
.stat-chip.good strong {{ color: var(--green); }}
.stat-chip.watch {{ background: color-mix(in oklch, var(--amber) 9%, var(--paper-2)); border-color: color-mix(in oklch, var(--amber) 34%, var(--rule)); }}
.stat-chip.watch strong {{ color: var(--amber); }}
.proof-card p {{ color: var(--soft); }}
.thesis-strip {{ display: grid; grid-template-columns: 1.08fr .92fr .88fr; gap: 1px; background: var(--rule); border: 1px solid var(--rule); border-radius: var(--radius); overflow: hidden; box-shadow: var(--shadow-soft); }}
.thesis-cell {{ background: color-mix(in oklch, var(--paper) 92%, var(--panel-tint)); padding: 18px; }}
.thesis-cell b {{ display: block; color: var(--muted); font: 12px var(--font-ui); margin-bottom: 7px; }}
.action-mini {{ list-style: none; margin: 0; padding: 0; display: grid; gap: 7px; }}
.action-mini li {{ display: grid; grid-template-columns: 62px minmax(0, 1fr); gap: 8px; align-items: baseline; }}
.action-mini b {{ margin: 0; color: var(--blue); font: 12px var(--font-ui); }}
.action-mini span {{ color: var(--soft); }}
.layer-stack {{ display: grid; gap: 10px; }}
.layer-detail {{ border: 1px solid var(--rule); border-radius: var(--radius); background: var(--paper); overflow: hidden; }}
.layer-detail summary {{ cursor: pointer; display: grid; grid-template-columns: 132px minmax(0, 1fr) auto auto; gap: 18px; align-items: start; padding: 18px 20px; font-family: var(--font-ui); }}
.layer-detail summary::-webkit-details-marker {{ display: none; }}
.layer-detail summary::after {{ content: "+"; color: var(--blue); font: 18px var(--font-mono); }}
.layer-detail[open] summary::after {{ content: "−"; }}
.layer-title {{ font-weight: 700; color: var(--ink); padding-top: 2px; }}
.layer-summary {{ display: grid; gap: 7px; color: var(--soft); max-width: 78ch; }}
.layer-summary span {{ display: block; }}
.layer-summary strong, .narrative-list strong, .indicator-copy strong {{ color: var(--ink); font-weight: 720; }}
.layer-body {{ border-top: 1px solid var(--rule); padding: 16px; display: grid; gap: 14px; }}
.narrative-list {{ list-style: none; margin: 0; padding: 0; display: grid; gap: 8px; max-width: 78ch; }}
.narrative-list li {{ color: var(--soft); padding-left: 18px; position: relative; }}
.narrative-list li::before {{ content: ""; position: absolute; left: 0; top: .76em; width: 6px; height: 6px; border-radius: 50%; background: var(--blue); }}
.indicator-list {{ list-style: none; margin: 0; padding: 0; display: grid; gap: 12px; }}
.indicator-list li {{ padding: 15px 0; border-top: 1px solid var(--rule); }}
.indicator-list li.has-micro {{ display: grid; grid-template-columns: minmax(0, 1fr) minmax(270px, .34fr); column-gap: 22px; row-gap: 8px; align-items: center; }}
.indicator-list li.no-micro {{ display: grid; gap: 8px; max-width: 78ch; }}
.indicator-id {{ display: flex; gap: 9px; align-items: center; align-content: start; min-width: 0; }}
.indicator-id b {{ color: var(--blue); font: 12px var(--font-mono); overflow-wrap: anywhere; }}
.indicator-copy {{ display: grid; gap: 8px; color: var(--soft); min-width: 0; max-width: 76ch; }}
.indicator-copy p {{ margin: 0; }}
.indicator-copy small {{ display: block; color: var(--muted); font-family: var(--font-ui); }}
.indicator-micro {{ min-width: 0; align-self: center; }}
.indicator-list li.has-micro .indicator-micro {{ grid-column: 2; grid-row: 1 / span 2; }}
.indicator-micro .spark {{ height: 82px; }}
.indicator-micro .spark path {{ stroke-width: 2; }}
.indicator-micro .spark text {{ font-size: 9px; }}
.fact-grid {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }}
.fact {{ background: var(--paper); border: 1px solid var(--rule); border-radius: var(--radius); padding: 14px; }}
.fact b {{ display: block; color: var(--muted); font: 12px var(--font-ui); margin-bottom: 4px; }}
.fact strong {{ font: 20px var(--font-mono); }}
.long-list {{ list-style: none; margin: 0; padding: 0; display: grid; gap: 12px; }}
.long-list li {{ background: var(--paper); border: 1px solid var(--rule); border-radius: var(--radius); padding: 14px; }}
.long-list b {{ display: block; margin-bottom: 5px; }}
.long-list small {{ display: block; color: var(--muted); margin-top: 8px; font-family: var(--font-ui); }}
.two-tone {{ display: grid; grid-template-columns: minmax(0, .9fr) minmax(0, 1.1fr); gap: 18px; align-items: start; }}
.summary-band {{ background: var(--paper); border: 1px solid var(--rule); border-radius: var(--radius); padding: 18px; display: grid; gap: 10px; }}
.nav {{ position: sticky; top: 0; z-index: 5; background: color-mix(in oklch, var(--bg) 92%, transparent); backdrop-filter: blur(10px); border-bottom: 1px solid var(--rule); }}
.nav-inner {{ width: min(1180px, calc(100% - 40px)); margin: 0 auto; display: flex; gap: 18px; padding: 10px 0; overflow-x: auto; font: 13px var(--font-ui); }}
.nav a {{ text-decoration: none; color: var(--soft); white-space: nowrap; }}
.tagline {{ margin-top: 16px; color: var(--muted); max-width: 74ch; }}
.mode-mark {{ color: var(--blue); }}
.variant-note {{ margin-top: 18px; padding: 14px 16px; border: 1px solid color-mix(in oklch, var(--blue) 24%, var(--rule)); border-radius: var(--radius); background: color-mix(in oklch, var(--blue) 5%, var(--paper)); color: var(--soft); max-width: 74ch; }}
.variant-switch {{ display: flex; gap: 10px; flex-wrap: wrap; margin-top: 22px; font-family: var(--font-ui); }}
.variant-switch a {{ text-decoration: none; border: 1px solid var(--rule); border-radius: 999px; padding: 5px 10px; color: var(--soft); background: var(--paper); }}
.variant-switch a.active {{ color: var(--blue); border-color: color-mix(in oklch, var(--blue) 45%, var(--rule)); background: color-mix(in oklch, var(--blue) 7%, var(--paper)); }}
@media (max-width: 780px) {{
  .page {{ width: min(100% - 28px, 1180px); padding-top: 28px; }}
  h1 {{ font-size: 1.82rem; }}
  .grid-2, .grid-3, .memo-flow, .thesis-strip, .fact-grid, .two-tone {{ grid-template-columns: 1fr; }}
  .stat-rail {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  .layer-detail summary {{ grid-template-columns: 1fr auto; }}
  .layer-summary, .layer-detail summary .small {{ grid-column: 1 / -1; }}
  .indicator-list li.has-micro {{ grid-template-columns: 1fr; align-items: start; }}
  .indicator-list li.has-micro .indicator-micro {{ grid-column: auto; grid-row: auto; width: 100%; }}
}}
"""


def html_page(title: str, body: str, mode: str = "demo") -> str:
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(title)}</title>
<style>{base_css(mode)}</style>
</head>
<body>{body}</body>
</html>
"""


def nav(current: str) -> str:
    links = [
        ("demo_memo_chartbook.html", "买方图册 Memo"),
        ("demo_risks.html", "风险与反证"),
        ("demo_conflicts.html", "冲突与共振"),
        ("demo_layers.html", "L1-L5 底稿"),
        ("demo_audit.html", "数据与审计"),
        ("index.html", "总览"),
    ]
    return "<nav class=\"nav\"><div class=\"nav-inner\">" + "".join(
        f"<a href=\"{href}\"{' class=\"mode-mark\"' if label == current else ''}>{label}</a>"
        for href, label in links
    ) + "</div></nav>"


def header(bundle: Dict[str, Any], eyebrow: str, title: str, note: str) -> str:
    meta = bundle["synthesis"].get("packet_meta", {})
    final = bundle["final"]
    return f"""
<header class="page">
  <div class="topline">{esc(eyebrow)}</div>
  <h1>{esc(title)}</h1>
  <p class="tagline">{esc(note)}</p>
  <div class="meta">
    <span class="pill">目标日 {esc(meta.get('data_date', 'N/A'))}</span>
    <span class="pill">覆盖 {esc(meta.get('indicator_successful', '?'))}/{esc(meta.get('indicator_total', '?'))}</span>
    <span class="pill">发布 {esc(bundle['review'].get('publish_status', 'N/A'))}</span>
    <span class="pill">审批 {esc(final.get('approval_status', 'N/A'))}</span>
    <span class="pill">置信度 {esc(confidence_label(final.get('confidence', 'N/A')))}</span>
  </div>
</header>
"""


def demo_memo(bundle: Dict[str, Any]) -> str:
    final = bundle["final"]
    reader = final.get("reader_final", {})
    index = indicator_lookup(bundle)
    reasons = "".join(f"<li>{esc(item)}</li>" for item in as_list(reader.get("three_reasons")))
    actions = "".join(
        f"<article class=\"box\"><h3>{esc(display_label(item.get('bucket')))}</h3><p><b>{esc(item.get('action'))}</b></p><p>{esc(item.get('rationale'))}</p><div class=\"meta\">{ref_chips(item.get('evidence_refs', []))}</div></article>"
        for item in as_list(final.get("portfolio_actions"))
        if isinstance(item, dict)
    )
    price_map = "".join(
        f"<article class=\"metric\"><b>{esc(display_label(item.get('category')))}</b><strong>{esc(display_label(item.get('reflected_state')))}</strong><p>{esc(item.get('rationale'))}</p></article>"
        for item in as_list(final.get("price_reflection_map"))[:5]
        if isinstance(item, dict)
    )
    layer_rows = "".join(
        f"<article class=\"box\"><h3>{layer} · {esc(LAYER_NAMES[layer])}</h3><p>{esc(sentence(bundle['layers'][layer].get('layer_synthesis'), 260))}</p></article>"
        for layer in LAYERS
    )
    body = nav("买方 Memo") + header(
        bundle,
        "Demo 01 · Buy-side memo",
        reader.get("one_liner") or final.get("final_stance", ""),
        "目标是让读者一口气读完：先判断，再动作，再证据，再反证。底稿只作为脚注入口出现。",
    )
    body += f"""
<main class="page">
  <section class="section" id="view">
    <h2>House View</h2>
    <p class="lede">{esc(final.get('state_diagnosis'))}</p>
  </section>
  <section class="section">
    <h2>三条足以改变仓位的理由</h2>
    <ul class="clean">{reasons}</ul>
  </section>
  <section class="section">
    <h2>动作分层</h2>
    <div class="grid-3">{actions}</div>
  </section>
  <section class="section grid-2">
    <div>
      <h2>价格已经反映了什么</h2>
      <div class="box">{price_map}</div>
    </div>
    <div>
      <h2>关键读数</h2>
      <div class="box">
        <div class="metric"><b>实际利率</b><strong>{esc(kpi_from_indicator(index, 'L1.get_10y_real_rate'))}</strong></div>
        <div class="metric"><b>信用质量利差</b><strong>{esc(kpi_from_indicator(index, 'L2.get_hy_quality_spread_bp'))}</strong></div>
        <div class="metric"><b>技术位置</b><strong>{esc(kpi_from_indicator(index, 'L5.get_qqq_technical_indicators'))}</strong></div>
      </div>
    </div>
  </section>
  <section class="section">
    <h2>五层只保留结论，不展开底稿</h2>
    <div class="grid-2">{layer_rows}</div>
  </section>
</main>
"""
    return html_page("Demo 01 买方 Memo", body)


def demo_briefing(bundle: Dict[str, Any]) -> str:
    final = bundle["final"]
    reader = final.get("reader_final", {})
    index = indicator_lookup(bundle)
    horizons = "".join(
        f"<article class=\"box\"><h3>{esc(display_label(item.get('horizon')))}</h3><p>{esc(item.get('view'))}</p><p><b>{esc(item.get('action_implication'))}</b></p></article>"
        for item in as_list(final.get("time_horizon_views"))
        if isinstance(item, dict)
    )
    risks = "".join(
        f"<article class=\"box\"><h3>{esc(item.get('condition'))}</h3><p>{esc(item.get('impact'))}</p><span class=\"pill\">概率 {esc(item.get('probability'))}</span></article>"
        for item in as_list(bundle["risk"].get("failure_conditions"))
        if isinstance(item, dict)
    )
    body = nav("投委会 Briefing") + header(
        bundle,
        "Demo 02 · Investment committee briefing",
        "先决定会不会动仓位，再决定看哪些证据。",
        "适合投委会或每日晨会：把结论压缩成一屏，所有展开都围绕动作、风险、确认条件。",
    )
    body += f"""
<main class="page">
  <section class="section grid-3">
    <div class="box"><h3>结论</h3><p>{esc(reader.get('one_liner'))}</p></div>
    <div class="box"><h3>主要矛盾</h3><p>{esc(final.get('principal_contradiction', {}).get('summary'))}</p></div>
    <div class="box"><h3>等待成本</h3><p>{esc(final.get('confirmation_cost'))}</p></div>
  </section>
  <section class="section">
    <h2>三段时间框架</h2>
    <div class="grid-3">{horizons}</div>
  </section>
  <section class="section grid-2">
    <div class="box">
      <h2>核心监控仪表</h2>
      <div class="metric"><b>L1 实际利率</b><strong>{esc(kpi_from_indicator(index, 'L1.get_10y_real_rate'))}</strong></div>
      <div class="metric"><b>L2 HY 内部分层</b><strong>{esc(kpi_from_indicator(index, 'L2.get_hy_quality_spread_bp'))}</strong></div>
      <div class="metric"><b>L3 集中度</b><strong>{esc(kpi_from_indicator(index, 'L3.get_qqq_top10_concentration'))}</strong></div>
      <div class="metric"><b>L4 盈利质量</b><strong>{esc(kpi_from_indicator(index, 'L4.get_ndx_forward_earnings_quality'))}</strong></div>
      <div class="metric"><b>L5 MACD</b><strong>{esc(kpi_from_indicator(index, 'L5.get_macd_qqq'))}</strong></div>
    </div>
    <div>
      <h2>失效条件</h2>
      <div class="deck">{risks}</div>
    </div>
  </section>
</main>
"""
    return html_page("Demo 02 投委会 Briefing", body)


def demo_evidence_ladder(bundle: Dict[str, Any]) -> str:
    final = bundle["final"]
    bridge = bundle["bridge"]
    conflicts = "".join(
        f"<article class=\"box\"><h3>{esc(item.get('conflict_id'))}</h3><p>{esc(item.get('description'))}</p><p><b>机制：</b>{esc(item.get('mechanism'))}</p><div class=\"meta\">{ref_chips(item.get('evidence_refs', []))}</div></article>"
        for item in as_list(bridge.get("typed_conflicts"))
        if isinstance(item, dict)
    )
    chains = "".join(
        f"<article class=\"box\"><h3>{esc(item.get('chain_id'))}</h3><p>{esc(item.get('description'))}</p><p><b>含义：</b>{esc(item.get('implication'))}</p><div class=\"meta\">{ref_chips(item.get('evidence_refs', []))}</div></article>"
        for item in as_list(bridge.get("resonance_chains"))
        if isinstance(item, dict)
    )
    layer_cards = "".join(
        f"<article class=\"box\"><h3>{layer} · {esc(LAYER_NAMES[layer])}</h3><p>{esc(sentence(bundle['layers'][layer].get('local_conclusion'), 190))}</p><div class=\"meta\">{ref_chips([f'{layer}.{i.get('function_id')}' for i in as_list(bundle['layers'][layer].get('indicator_analyses'))[:3] if isinstance(i, dict)])}</div></article>"
        for layer in LAYERS
    )
    body = nav("证据阶梯") + header(
        bundle,
        "Demo 03 · Evidence ladder",
        "从判断对象到反证条件，一层一层向下展开。",
        "适合保留 vNext 的审计优势：不是把底稿塞进正文，而是让读者沿着证据阶梯主动下钻。",
    )
    body += f"""
<main class="page">
  <section class="section">
    <h2>顶层判断</h2>
    <p class="lede">{esc(final.get('final_stance'))}</p>
  </section>
  <section class="section">
    <h2>五层证据入口</h2>
    <div class="grid-2">{layer_cards}</div>
  </section>
  <section class="section">
    <h2>冲突，不被抹平</h2>
    <div class="deck">{conflicts}</div>
  </section>
  <section class="section">
    <h2>共振链</h2>
    <div class="grid-2">{chains}</div>
  </section>
</main>
"""
    return html_page("Demo 03 证据阶梯", body)


def demo_chartbook(bundle: Dict[str, Any]) -> str:
    final = bundle["final"]
    panels = [
        ("QQQ 价格", "QQQ_OHLCV", "close", "价格仍在上升趋势内，但短期动量已经转弱。"),
        ("VXN 纳指波动", "VXN", "value", "科技股隐含波动率仍高于大盘风险温度。"),
        ("HY OAS", "HY_OAS", "value", "整体信用利差极低，显示风险偏好仍宽。"),
        ("CCC-BB 质量利差", "HY_QUALITY_SPREAD", "value", "信用内部质量分层仍是风险暗线。"),
        ("10Y 实际利率", "US10Y_REAL", "value", "真实折现率维持高位，是估值压力主轴。"),
        ("QQQ/QQEW", "QQQ_QQEW_RATIO", "value", "等权补涨改善，但集中度绝对位置仍高。"),
    ]
    cards = "".join(
        f"<article class=\"box\"><h3>{esc(title)}</h3>{sparkline(chart_rows(bundle, key), field)}<p>{esc(note)}</p></article>"
        for title, key, field, note in panels
    )
    body = nav("图册式报告") + header(
        bundle,
        "Demo 04 · Chartbook narrative",
        "每张图只回答一个问题。",
        "借鉴图册式研报：图表推动判断，段落只解释图表如何支持或反驳主结论。",
    )
    body += f"""
<main class="page">
  <section class="section">
    <h2>主结论</h2>
    <p class="lede">{esc(final.get('state_diagnosis'))}</p>
  </section>
  <section class="section">
    <h2>六张核心图</h2>
    <div class="grid-2">{cards}</div>
  </section>
  <section class="section grid-2">
    <div class="box"><h3>如何改变判断</h3><ul class="clean">{''.join(f'<li>{esc(item)}</li>' for item in as_list(final.get('invalidation_conditions')))}</ul></div>
    <div class="box"><h3>审计状态</h3><p>Run Review: {esc(bundle['review'].get('review_mode'))}</p><p>Data Integrity: {esc(bundle['review'].get('publish_status'))}</p><p>Schema Guard 与 DataIntegrity 不在正文展开，作为附录入口保留。</p></div>
  </section>
</main>
"""
    return html_page("Demo 04 图册式报告", body)


def proof_card(
    bundle: Dict[str, Any],
    *,
    title: str,
    layer: str,
    key: str,
    field: str,
    takeaway: str,
    stats: Sequence[Tuple[str, str, str]],
    refs: Sequence[str],
    tone: str = "price",
    spark_annotation: Optional[str] = None,
    show_guide: bool = True,
) -> str:
    stat_html = "".join(stat_chip(label, value, tone) for label, value, tone in stats)
    return f"""
<article class="proof-card tone-{esc(tone)}">
  <div class="proof-head"><h3>{esc(title)}</h3><span class="proof-layer">{esc(layer)}</span></div>
  {sparkline(chart_rows(bundle, key), field, annotation=spark_annotation, show_guide=show_guide)}
  <div class="stat-rail">{stat_html}</div>
  <p>{esc(takeaway)}</p>
  <div class="meta">{ref_chips(refs)}</div>
</article>
"""


def qqq_price_stats(bundle: Dict[str, Any]) -> List[Tuple[str, str, str]]:
    rows = chart_rows(bundle, "QQQ_OHLCV")
    last = rows[-1] if rows else {}
    close = metric_number(last.get("close"))
    ma60 = metric_number(last.get("ma60"))
    macd_hist = metric_number(last.get("macd_histogram"))
    dist_ma60 = (close / ma60 - 1) * 100 if close is not None and ma60 else None
    raw = raw_indicator(bundle, "L5", "get_qqq_technical_indicators")
    donchian = raw.get("donchian_position_pct")
    return [
        ("价格", fmt_num(close, 2), "neutral"),
        ("20日动量", fmt_pct(series_return(rows, "close", 20), 1, signed=True), "good"),
        ("距SMA60", fmt_pct(dist_ma60, 1, signed=True), "good"),
        ("通道位置", fmt_pct(metric_number(donchian), 1), "watch"),
        ("MACD柱", fmt_num(macd_hist, 2), "risk" if macd_hist is not None and macd_hist < 0 else "neutral"),
    ]


def formal_value_stats(
    bundle: Dict[str, Any],
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
    rows = chart_rows(bundle, chart_key)
    values = numeric_series(rows, field)
    last = values[-1] if values else None
    delta20 = series_delta(rows, field, 20)
    ret20 = series_return(rows, field, 20)
    if change_kind == "bps":
        change = fmt_bps(delta20)
    elif change_kind == "points":
        change = f"{delta20:+.1f}点" if delta20 is not None else "N/A"
    else:
        change = fmt_pct(ret20, 1, signed=True)
    stats = [
        (value_label, f"{fmt_num(last, 2)}{value_suffix}" if last is not None else "N/A", "neutral"),
        (f"{percentile_window.replace('y', '年')}分位", fmt_percentile(historical_percentile(bundle, layer, function_id, percentile_window)), percentile_tone),
        ("20日变化", change, "risk" if (delta20 or 0) > 0 else "good"),
    ]
    stats.extend(extra)
    return stats


def simple_value_stats(
    bundle: Dict[str, Any],
    key: str,
    field: str,
    value_label: str,
    value_suffix: str = "",
    change_kind: str = "pct",
) -> List[Tuple[str, str, str]]:
    rows = chart_rows(bundle, key)
    values = numeric_series(rows, field)
    last = values[-1] if values else None
    delta20 = series_delta(rows, field, 20)
    ret20 = series_return(rows, field, 20)
    if change_kind == "bps":
        change = fmt_bps(delta20)
    elif change_kind == "points":
        change = f"{delta20:+.2f}点" if delta20 is not None else "N/A"
    else:
        change = fmt_pct(ret20, 1, signed=True)
    value = f"{fmt_num(last, 2)}{value_suffix}" if last is not None else "N/A"
    return [
        (value_label, value, "neutral"),
        ("近1年分位", fmt_pct(series_percentile(rows, field)), "watch"),
        ("20日变化", change, "risk" if (delta20 or 0) > 0 else "good"),
    ]


def layer_detail(bundle: Dict[str, Any], layer: str) -> str:
    card = bundle["layers"].get(layer, {})
    full_conclusion = card.get("layer_synthesis") or card.get("local_conclusion")
    confidence = card.get("confidence", "N/A")
    indicators = []
    for item in as_list(card.get("indicator_analyses"))[:8]:
        if isinstance(item, dict):
            fid = item.get("function_id")
            reading = sentence(item.get("current_reading"), 150)
            narrative = sentence(item.get("narrative"), 180)
            micro = indicator_micro_chart(bundle, item)
            row_class = "has-micro" if micro else "no-micro"
            indicators.append(
                f"<li class=\"{row_class}\">"
                f"<div class=\"indicator-id\"><b>{esc(fid)}</b><span class=\"pill\">{esc(confidence_label(item.get('confidence', 'N/A')))}</span></div>"
                f"<div class=\"indicator-copy\"><p>{rich_text(reading)}</p><small>{rich_text(narrative)}</small></div>"
                f"{micro}"
                "</li>"
            )
    risks = "".join(
        f"<span class=\"pill\">{esc(sentence(flag, 70))}</span>"
        for flag in as_list(card.get("risk_flags"))[:4]
    )
    return f"""
<details class="layer-detail">
  <summary>
    <span class="layer-title">{esc(layer)} · {esc(LAYER_NAMES[layer])}</span>
    <span class="layer-summary">{summary_fragments(full_conclusion)}</span>
    <span class="pill">置信度 {esc(confidence_label(confidence))}</span>
  </summary>
  <div class="layer-body">
    {narrative_list(full_conclusion)}
    <div class="meta">{risks}</div>
    <ul class="indicator-list">{''.join(indicators)}</ul>
  </div>
</details>
"""


def variant_links(active: str) -> str:
    variants = [
        ("demo_memo_chartbook.html", "A 墨蓝纸面", "demo"),
        ("demo_memo_chartbook_warm.html", "B 暖纸投委", "warm"),
        ("demo_memo_chartbook_crisp.html", "C 清爽研究台", "crisp"),
    ]
    return "<div class=\"page\" style=\"padding-top:0;padding-bottom:0\"><div class=\"variant-switch\">" + "".join(
        f"<a href=\"{href}\"{' class=\"active\"' if key == active else ''}>{label}</a>"
        for href, label, key in variants
    ) + "</div></div>"


def demo_memo_chartbook(bundle: Dict[str, Any], mode: str = "demo") -> str:
    final = bundle["final"]
    reader = final.get("reader_final", {})
    variant_copy = {
        "demo": (
            "Demo 05A · Memo chartbook",
            "墨蓝纸面版",
            "主版：更像正式研报，标题有报纸感，蓝色负责证据路径，红绿琥珀负责风险、确认和观察。",
        ),
        "warm": (
            "Demo 05B · Memo chartbook",
            "暖纸投委版",
            "备选：更像投委会材料，纸面更暖、色彩更沉，适合长时间顺读和打印。",
        ),
        "crisp": (
            "Demo 05C · Memo chartbook",
            "清爽研究台版",
            "备选：全部换成系统无衬线，信息密度更高，更像日常研究工作台。",
        ),
    }
    eyebrow, style_label, variant_note = variant_copy.get(mode, variant_copy["demo"])
    actions = as_list(final.get("portfolio_actions"))
    action_rows = "".join(
        f"<li><b>{esc(display_label(item.get('bucket')))}</b><span>{esc(item.get('action'))}</span></li>"
        for item in actions[:3]
        if isinstance(item, dict)
    ) or f"<li><b>动作</b><span>{esc(final.get('payoff_assessment'))}</span></li>"
    invalidations = as_list(final.get("invalidation_conditions"))
    primary_break = invalidations[0] if invalidations else "等待新的反证条件。"

    rate_values = numeric_series(chart_rows(bundle, "US10Y_REAL"), "value")
    rate_stats = formal_value_stats(
        bundle,
        chart_key="US10Y_REAL",
        field="value",
        layer="L1",
        function_id="get_10y_real_rate",
        value_label="实际利率",
        value_suffix="%",
        change_kind="bps",
        percentile_tone="risk",
        extra=[("距2.30%", fmt_bps((rate_values[-1] - 2.30) if rate_values else None), "watch")],
    )

    vxn_stats = formal_value_stats(
        bundle,
        chart_key="VXN",
        field="value",
        layer="L2",
        function_id="get_vxn",
        value_label="当前VXN",
        change_kind="points",
        percentile_tone="risk",
        extra=[("风险温度", "偏高", "risk")],
    )

    hy_stats = formal_value_stats(
        bundle,
        chart_key="HY_OAS",
        field="value",
        layer="L2",
        function_id="get_hy_oas_bp",
        value_label="HY OAS",
        value_suffix="%",
        change_kind="bps",
        percentile_tone="good",
        extra=[("信用总量", "极宽", "good")],
    )

    quality_stats = formal_value_stats(
        bundle,
        chart_key="HY_QUALITY_SPREAD",
        field="value",
        layer="L2",
        function_id="get_hy_quality_spread_bp",
        value_label="CCC-BB",
        value_suffix="%",
        change_kind="bps",
        percentile_tone="risk",
        extra=[("内部分化", "极高", "risk")],
    )

    ratio_stats = formal_value_stats(
        bundle,
        chart_key="QQQ_QQEW_RATIO",
        field="value",
        layer="L3",
        function_id="get_qqq_qqew_ratio",
        value_label="QQQ/QQEW",
        change_kind="pct",
        percentile_tone="risk",
        extra=[("5年分位", fmt_percentile(historical_percentile(bundle, "L3", "get_qqq_qqew_ratio", "5y")), "risk")],
    )

    cards_top = "".join(
        [
            proof_card(
                bundle,
                title="QQQ 价格趋势",
                layer="L5 价格与执行",
                key="QQQ_OHLCV",
                field="close",
                takeaway="价格处于上升趋势，但 MACD 柱转负，说明趋势没有被破坏，短线追涨回报变差。",
                stats=qqq_price_stats(bundle),
                refs=["L5.get_l5_deterministic_snapshot", "L5.get_macd_qqq"],
                tone="price",
                spark_annotation="价格趋势",
            ),
            proof_card(
                bundle,
                title="VXN 科技波动",
                layer="L2 波动与情绪",
                key="VXN",
                field="value",
                takeaway="纳指隐含波动仍高，说明风险不是全面恐慌，而是科技股内部压力没有完全消失。",
                stats=vxn_stats,
                refs=["L2.get_vxn", "L2.get_vxn_vix_ratio"],
                tone="risk",
                spark_annotation=f"10年分位 {fmt_percentile(historical_percentile(bundle, 'L2', 'get_vxn'))}",
            ),
        ]
    )

    cards_rates = proof_card(
        bundle,
        title="10Y 实际利率",
        layer="L1 宏观约束",
        key="US10Y_REAL",
        field="value",
        takeaway="真实折现率仍是估值压力主轴。只要它维持高位，NDX 的上涨更依赖盈利和流动性支撑。",
        stats=rate_stats,
        refs=["L1.get_10y_real_rate", "L1.get_10y_treasury"],
        tone="macro",
        spark_annotation=f"10年分位 {fmt_percentile(historical_percentile(bundle, 'L1', 'get_10y_real_rate'))}",
    )

    cards_credit = "".join(
        [
            proof_card(
                bundle,
                title="HY OAS 总量利差",
                layer="L2 信用总量",
                key="HY_OAS",
                field="value",
                takeaway="整体信用利差很低，说明市场仍愿意承担风险，这是 risk-on 的重要确认。",
                stats=hy_stats,
                refs=["L2.get_hy_oas_bp"],
                tone="credit",
                spark_annotation=f"10年分位 {fmt_percentile(historical_percentile(bundle, 'L2', 'get_hy_oas_bp'))}",
            ),
            proof_card(
                bundle,
                title="CCC-BB 质量利差",
                layer="L2 信用分层",
                key="HY_QUALITY_SPREAD",
                field="value",
                takeaway="低质信用没有同步乐观，说明宽松风险偏好下仍有一条质量分化暗线。",
                stats=quality_stats,
                refs=["L2.get_hy_quality_spread_bp"],
                tone="risk",
                spark_annotation=f"10年分位 {fmt_percentile(historical_percentile(bundle, 'L2', 'get_hy_quality_spread_bp'))}",
            ),
        ]
    )

    cards_structure = proof_card(
        bundle,
        title="QQQ / QQEW",
        layer="L3 内部结构",
        key="QQQ_QQEW_RATIO",
        field="value",
        takeaway="等权补涨改善了市场宽度，但集中度绝对位置仍然很高，不能把广度改善误读成结构风险消失。",
        stats=ratio_stats,
        refs=["L3.get_qqq_qqew_ratio", "L3.get_qqq_top10_concentration"],
        tone="structure",
        spark_annotation=f"10年分位 {fmt_percentile(historical_percentile(bundle, 'L3', 'get_qqq_qqew_ratio'))}",
    )

    layers = "".join(layer_detail(bundle, layer) for layer in LAYERS)
    reasons = "".join(f"<li>{esc(item)}</li>" for item in as_list(reader.get("three_reasons")))

    body = nav("买方图册 Memo") + header(
        bundle,
        eyebrow,
        reader.get("one_liner") or final.get("final_stance", ""),
        f"{style_label}：买方 memo 的顺读骨架，图册的直观证据，L1-L5 的可展开审计入口，三者合成一个页面。",
    )
    body += variant_links(mode)
    body += f"""
<main class="page">
  <p class="variant-note">{esc(variant_note)}</p>
  <section class="section thesis-strip">
    <div class="thesis-cell"><b>主判断</b><p>{esc(final.get('state_diagnosis'))}</p></div>
    <div class="thesis-cell"><b>动作含义</b><ul class="action-mini">{action_rows}</ul></div>
    <div class="thesis-cell"><b>优先反证</b><p>{esc(primary_break)}</p></div>
  </section>

  <section class="section memo-flow memo-pair">
    <div class="memo-copy">
      <p class="kicker">01 / Market state</p>
      <h2>先判断市场状态</h2>
      <p class="lede">{esc(final.get('final_stance'))}</p>
      <ul class="clean">{reasons}</ul>
    </div>
    <div class="grid-2">{cards_top}</div>
  </section>

  <section class="section memo-flow">
    <div class="memo-copy">
      <p class="kicker">02 / Hard constraint</p>
      <h2>再看最硬的约束</h2>
      <p>本轮报告的核心矛盾不是单纯“涨多了”，而是高实际利率与价格趋势同时存在。价格能继续走强，但估值容错率被利率压住。</p>
      <p class="small">这类图旁边必须放分位和阈值距离，因为它要回答的是“压力有多硬”，不是“线往哪走”。</p>
    </div>
    {cards_rates}
  </section>

  <section class="section memo-flow memo-pair">
    <div class="memo-copy">
      <p class="kicker">03 / Credit signal</p>
      <h2>信用给出确认，也给出警告</h2>
      <p>总量信用利差极低，确认风险偏好仍然宽；但质量利差维持高位，说明资金并没有无差别追逐低质资产。</p>
      <p class="small">这里保留两张图，是因为“总量宽松”和“内部分化”同时成立，任何一张图单独出现都会误导。</p>
    </div>
    <div class="grid-2">{cards_credit}</div>
  </section>

  <section class="section memo-flow">
    <div class="memo-copy">
      <p class="kicker">04 / Market breadth</p>
      <h2>结构改善，但不能把风险抹平</h2>
      <p>等权补涨是好消息，它降低了“只有少数巨头上涨”的脆弱性；但集中度仍在极高分位，组合仍然暴露于头部权重和盈利兑现风险。</p>
    </div>
    {cards_structure}
  </section>

  <section class="section">
    <h2>L1-L5 可展开审计层</h2>
    <p class="lede">正文只呈现影响判断的内容。每一层 agent 的原始价值保留在这里：读者可以展开看本层结论、风险旗标和关键指标读数。</p>
    <p class="small">置信度是各层 agent 对本层证据覆盖、数据质量和反证压力的自评，页面只作高/中/低提示；正式版应继续拆成可审计评分项。</p>
    <div class="layer-stack">{layers}</div>
  </section>
</main>
"""
    return html_page(f"买方图册 Memo {style_label}", body, mode)


def demo_risks(bundle: Dict[str, Any]) -> str:
    final = bundle["final"]
    risk = bundle["risk"]
    actions = "".join(
        f"""
<article class="box">
  <h3>{esc(display_label(item.get('bucket')))}</h3>
  <p><b>{esc(item.get('action'))}</b></p>
  <p>{esc(item.get('rationale'))}</p>
  <ul class="clean">{''.join(f'<li>{esc(condition)}</li>' for condition in as_list(item.get('conditions')))}</ul>
  <div class="meta">{ref_chips(item.get('evidence_refs', []))}</div>
</article>
"""
        for item in as_list(final.get("portfolio_actions"))
        if isinstance(item, dict)
    )
    horizons = "".join(
        f"""
<article class="box">
  <h3>{esc(display_label(item.get('horizon')))}</h3>
  <p>{esc(item.get('view'))}</p>
  <p><b>{esc(item.get('action_implication'))}</b></p>
</article>
"""
        for item in as_list(final.get("time_horizon_views"))
        if isinstance(item, dict)
    )
    failures = "".join(
        f"""
<li>
  <b>{esc(item.get('condition'))}</b>
  <span>{esc(item.get('impact'))}</span>
  <small>概率 {esc(item.get('probability'))} · {esc(', '.join(str(ref) for ref in as_list(item.get('triggered_by'))))}</small>
</li>
"""
        for item in as_list(risk.get("failure_conditions"))
        if isinstance(item, dict)
    )
    price_map = "".join(
        f"""
<li>
  <b>{esc(display_label(item.get('category')))} · {esc(display_label(item.get('reflected_state')))}</b>
  <span>{esc(item.get('rationale'))}</span>
</li>
"""
        for item in as_list(final.get("price_reflection_map"))
        if isinstance(item, dict)
    )
    preserved = "".join(f"<li>{esc(item)}</li>" for item in as_list(risk.get("must_preserve_risks") or final.get("must_preserve_risks")))
    body = nav("风险与反证") + header(
        bundle,
        "Parallel chapter · Risk and falsifiers",
        "先看怎么做，再看什么会证明我们错了。",
        "这是主报告之后最应该并列打开的一章：动作、时间框架、失效条件和价格反映地图放在一起，避免漂亮主文把风险藏起来。",
    )
    body += f"""
<main class="page">
  <section class="section">
    <h2>动作分层</h2>
    <div class="grid-3">{actions}</div>
  </section>
  <section class="section">
    <h2>三段时间框架</h2>
    <div class="grid-3">{horizons}</div>
  </section>
  <section class="section two-tone">
    <div>
      <h2>失效条件</h2>
      <ul class="long-list">{failures}</ul>
    </div>
    <div>
      <h2>价格已经反映了什么</h2>
      <ul class="long-list">{price_map}</ul>
    </div>
  </section>
  <section class="section">
    <h2>必须保留的风险</h2>
    <div class="box"><ul class="clean">{preserved}</ul></div>
  </section>
</main>
"""
    return html_page("风险与反证", body)


def demo_conflicts(bundle: Dict[str, Any]) -> str:
    final = bundle["final"]
    bridge = bundle["bridge"]
    principal = final.get("principal_contradiction", {}) if isinstance(final.get("principal_contradiction"), dict) else {}
    conflicts = "".join(
        f"""
<article class="box">
  <h3>{esc(item.get('conflict_id'))}</h3>
  <p>{esc(item.get('description'))}</p>
  <p><b>机制：</b>{esc(item.get('mechanism'))}</p>
  <p><b>含义：</b>{esc(item.get('implication'))}</p>
  <div class="meta"><span class="pill">严重度 {esc(item.get('severity'))}</span><span class="pill">置信度 {esc(confidence_label(item.get('confidence')))}</span>{ref_chips(item.get('evidence_refs', []))}</div>
</article>
"""
        for item in as_list(bridge.get("typed_conflicts"))
        if isinstance(item, dict)
    )
    chains = "".join(
        f"""
<article class="box">
  <h3>{esc(item.get('chain_id'))}</h3>
  <p>{esc(item.get('description'))}</p>
  <p><b>机制：</b>{esc(item.get('mechanism'))}</p>
  <p><b>含义：</b>{esc(item.get('implication'))}</p>
  <div class="meta">{ref_chips(item.get('evidence_refs', []))}</div>
</article>
"""
        for item in as_list(bridge.get("resonance_chains"))
        if isinstance(item, dict)
    )
    paths = "".join(
        f"""
<li>
  <b>{esc(item.get('path_id'))}</b>
  <span>{esc(item.get('description') or item.get('mechanism'))}</span>
  <small>{esc(item.get('implication'))}</small>
</li>
"""
        for item in as_list(bridge.get("transmission_paths"))
        if isinstance(item, dict)
    )
    questions = "".join(f"<li>{esc(item)}</li>" for item in as_list(bridge.get("unresolved_questions")))
    body = nav("冲突与共振") + header(
        bundle,
        "Parallel chapter · Conflicts and resonance",
        principal.get("summary") or "冲突不是瑕疵，而是这份报告最重要的可审计资产。",
        "主报告负责顺读，这一章负责解释证据之间如何互相支撑、互相打架，以及哪些张力仍未解决。",
    )
    body += f"""
<main class="page">
  <section class="section summary-band">
    <h2>主要矛盾</h2>
    <p class="lede">{esc(principal.get('summary') or final.get('principal_contradiction', ''))}</p>
    <p>{esc(principal.get('dominant_side') or principal.get('why_it_matters') or '')}</p>
  </section>
  <section class="section">
    <h2>冲突矩阵</h2>
    <div class="deck">{conflicts}</div>
  </section>
  <section class="section">
    <h2>共振链</h2>
    <div class="grid-2">{chains}</div>
  </section>
  <section class="section grid-2">
    <div>
      <h2>传导路径</h2>
      <ul class="long-list">{paths}</ul>
    </div>
    <div>
      <h2>仍未解决的问题</h2>
      <div class="box"><ul class="clean">{questions}</ul></div>
    </div>
  </section>
</main>
"""
    return html_page("冲突与共振", body)


def full_layer_detail(bundle: Dict[str, Any], layer: str) -> str:
    card = bundle["layers"].get(layer, {})
    full_conclusion = card.get("layer_synthesis") or card.get("local_conclusion")
    indicators = []
    for item in as_list(card.get("indicator_analyses")):
        if isinstance(item, dict):
            fid = item.get("function_id")
            reading = sentence(item.get("current_reading"), 190)
            stance = item.get("local_stance") or item.get("permission") or ""
            narrative = sentence(item.get("narrative"), 260)
            micro = indicator_micro_chart(bundle, item)
            row_class = "has-micro" if micro else "no-micro"
            indicators.append(
                f"<li class=\"{row_class}\">"
                f"<div class=\"indicator-id\"><b>{esc(fid)}</b><span class=\"pill\">{esc(confidence_label(item.get('confidence', 'N/A')))}</span></div>"
                f"<div class=\"indicator-copy\"><p>{rich_text(reading)}</p><small>{rich_text(narrative or stance)}</small></div>"
                f"{micro}"
                "</li>"
            )
    risk_flags = "".join(f"<span class=\"pill\">{esc(sentence(flag, 90))}</span>" for flag in as_list(card.get("risk_flags")))
    hooks = "".join(f"<li>{rich_text(format_hook(hook))}</li>" for hook in as_list(card.get("cross_layer_hooks")))
    internal = card.get("internal_conflict_analysis")
    quality = card.get("quality_self_check")
    return f"""
<details class="layer-detail" open>
  <summary>
    <span class="layer-title">{esc(layer)} · {esc(LAYER_NAMES[layer])}</span>
    <span class="layer-summary">{summary_fragments(full_conclusion)}</span>
    <span class="pill">置信度 {esc(confidence_label(card.get('confidence', 'N/A')))}</span>
  </summary>
  <div class="layer-body">
    {narrative_list(full_conclusion)}
    <div class="meta">{risk_flags}</div>
    <div class="grid-2">
      <div class="box"><h3>层内冲突</h3><p>{esc(readable_structured(internal, 420))}</p></div>
      <div class="box"><h3>质量自检</h3><p>{esc(readable_structured(quality, 420))}</p></div>
    </div>
    <div class="box"><h3>跨层待验证钩子</h3><ul class="clean">{hooks}</ul></div>
    <ul class="indicator-list">{''.join(indicators)}</ul>
  </div>
</details>
"""


def demo_layers_full(bundle: Dict[str, Any]) -> str:
    layers = "".join(full_layer_detail(bundle, layer) for layer in LAYERS)
    body = nav("L1-L5 底稿") + header(
        bundle,
        "Parallel chapter · L1-L5 source deck",
        "每个 agent 的东西仍然有价值，但它应该成为可审计底稿，不打断主报告。",
        "这一章按五层顺序完整展开：本层结论、风险旗标、层内冲突、质量自检、跨层钩子和指标读数。",
    )
    body += f"""
<main class="page">
  <section class="section">
    <h2>五层底稿</h2>
    <div class="layer-stack">{layers}</div>
  </section>
</main>
"""
    return html_page("L1-L5 底稿", body)


def demo_audit(bundle: Dict[str, Any]) -> str:
    review = bundle["review"]
    integrity = bundle["integrity"]
    schema = bundle["schema"]
    critique = bundle["critique"]
    packet_meta = bundle["synthesis"].get("packet_meta", {})
    facts = [
        ("发布状态", review.get("publish_status") or integrity.get("publish_status")),
        ("DataIntegrity", f"{integrity.get('confidence_percent', 'N/A')}%"),
        ("Schema Guard", "passed" if schema.get("passed") else schema.get("quality_status", "N/A")),
        ("指标覆盖", f"{packet_meta.get('indicator_successful', '?')}/{packet_meta.get('indicator_total', '?')}"),
    ]
    fact_html = "".join(f"<div class=\"fact\"><b>{esc(label)}</b><strong>{esc(value)}</strong></div>" for label, value in facts)
    review_items = "".join(
        f"<li><b>{esc(item.get('check') or item.get('area') or 'review')}</b><span>{esc(item.get('finding') or item.get('summary') or item)}</span></li>"
        for item in as_list(review.get("attribution_findings"))[:9]
        if isinstance(item, dict)
    )
    fallback_items = "".join(
        f"<li><b>{esc(item)}</b><span>需要在正式报告里保留数据口径或 fallback 边界。</span></li>"
        for item in as_list(integrity.get("fallback_indicators"))[:12]
    )
    issues = "".join(
        f"<li><b>{esc(item.get('issue_type') or item.get('code') or 'issue')}</b><span>{esc(item.get('detail') or item.get('message') or item)}</span></li>"
        for item in as_list(integrity.get("data_evidence_contract_issues"))[:10]
        if isinstance(item, dict)
    )
    critique_rows = "".join(
        f"<li><b>{esc(key)}</b><span>{esc(sentence(value, 180))}</span></li>"
        for key, value in critique.items()
        if key not in {"token_usage"} and not isinstance(value, (dict, list))
    )
    body = nav("数据与审计") + header(
        bundle,
        "Parallel chapter · Data and audit",
        "这章不抢主报告阅读，但决定报告能不能被信任。",
        "正式版不能把审计内容删掉。它应该以并列章节存在：发布闸门、数据完整性、Schema Guard、fallback、审计发现都在这里。",
    )
    body += f"""
<main class="page">
  <section class="section">
    <h2>发布闸门</h2>
    <div class="fact-grid">{fact_html}</div>
  </section>
  <section class="section grid-2">
    <div>
      <h2>Run Review</h2>
      <ul class="long-list">{review_items}</ul>
    </div>
    <div>
      <h2>Fallback 与证据合同提示</h2>
      <ul class="long-list">{fallback_items or issues}</ul>
    </div>
  </section>
  <section class="section grid-2">
    <div class="box"><h3>Schema Guard</h3><p>结构问题 {esc(len(as_list(schema.get('structural_issues'))))}；一致性问题 {esc(len(as_list(schema.get('consistency_issues'))))}；缺失字段 {esc(len(as_list(schema.get('missing_fields'))))}。</p></div>
    <div class="box"><h3>Critic / Governance</h3><ul class="clean">{critique_rows}</ul></div>
  </section>
</main>
"""
    return html_page("数据与审计", body)


def demo_index(bundle: Dict[str, Any]) -> str:
    final = bundle["final"]
    demos = [
        ("demo_memo_chartbook.html", "买方图册 Memo A · 墨蓝纸面", "正式第一章主版：memo 顺读、图册佐证、关键判断一口气看完。"),
        ("demo_memo_chartbook_warm.html", "买方图册 Memo B · 暖纸投委", "同一内容的暖色纸面版，更像投委会材料和可打印研报。"),
        ("demo_memo_chartbook_crisp.html", "买方图册 Memo C · 清爽研究台", "同一内容的无衬线研究台版，信息密度更高，更偏日常工作流。"),
        ("demo_risks.html", "风险与反证", "动作、时间框架、失效条件、价格反映地图并列展示。"),
        ("demo_conflicts.html", "冲突与共振", "保留 typed conflicts、resonance chains、传导路径和未解问题。"),
        ("demo_layers.html", "L1-L5 底稿", "每个 agent 的原始价值作为并列底稿，而不是塞进正文。"),
        ("demo_audit.html", "数据与审计", "DataIntegrity、Schema Guard、Run Review、fallback 边界集中查看。"),
        ("demo_memo.html", "Demo 01 · 买方 Memo", "最像传统投研长文：判断、动作、证据、反证。适合一口气阅读。"),
        ("demo_briefing.html", "Demo 02 · 投委会 Briefing", "最适合晨会和投委会：一屏定方向，后面只看动作和触发条件。"),
        ("demo_evidence_ladder.html", "Demo 03 · 证据阶梯", "最保留 vNext 特色：冲突、共振、证据 refs 有层级地展开。"),
        ("demo_chartbook.html", "Demo 04 · 图册式报告", "最像 J.P. Morgan Guide to the Markets：一图一问题，一图一结论。"),
    ]
    cards = "".join(
        f"<a class=\"box\" href=\"{href}\" style=\"text-decoration:none;display:block\"><h3>{esc(title)}</h3><p>{esc(desc)}</p></a>"
        for href, title, desc in demos
    )
    body = nav("总览") + header(
        bundle,
        "Report demo set",
        "并列章节版研报 demo，全部基于最后一次 run 的同一批数据。",
        "主导航按阅读任务排序：先看买方图册 Memo，再看风险、冲突、底稿和审计；旧候选保留在总览里作为对照。",
    )
    body += f"""
<main class="page">
  <section class="section">
    <h2>当前 run 的共同结论</h2>
    <p class="lede">{esc(final.get('final_stance'))}</p>
  </section>
  <section class="section">
    <h2>可选 demo</h2>
    <div class="grid-2">{cards}</div>
  </section>
</main>
"""
    return html_page("研报 Demo 总览", body)


def write_demos(run_dir: Path, out_dir: Path) -> List[Path]:
    bundle = read_bundle(run_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    pages = {
        "index.html": demo_index(bundle),
        "demo_memo_chartbook.html": demo_memo_chartbook(bundle),
        "demo_memo_chartbook_warm.html": demo_memo_chartbook(bundle, "warm"),
        "demo_memo_chartbook_crisp.html": demo_memo_chartbook(bundle, "crisp"),
        "demo_risks.html": demo_risks(bundle),
        "demo_conflicts.html": demo_conflicts(bundle),
        "demo_layers.html": demo_layers_full(bundle),
        "demo_audit.html": demo_audit(bundle),
        "demo_memo.html": demo_memo(bundle),
        "demo_briefing.html": demo_briefing(bundle),
        "demo_evidence_ladder.html": demo_evidence_ladder(bundle),
        "demo_chartbook.html": demo_chartbook(bundle),
    }
    written = []
    for name, content in pages.items():
        path = out_dir / name
        path.write_text(content, encoding="utf-8")
        written.append(path)
    return written


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate experimental vNext report demos from an existing run.")
    parser.add_argument("--run-dir", default="output/analysis/vnext/20260617_024610")
    parser.add_argument("--out-dir", default="output/reports/report_demos_20260617_024610")
    args = parser.parse_args()
    written = write_demos(Path(args.run_dir), Path(args.out_dir))
    print("\n".join(str(path) for path in written))


if __name__ == "__main__":
    main()
