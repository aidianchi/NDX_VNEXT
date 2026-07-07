# tools_L4.py
# -*- coding: utf-8 -*-
"""
NDX Agent · 第4层数据获取函数
"""

try:
    from .tools_common import *
except ImportError:
    from tools_common import *

try:
    from .data_evidence import build_data_quality
except ImportError:
    from data_evidence import build_data_quality

from datetime import timezone
from copy import deepcopy

try:
    from .tools_L1 import get_10y_treasury
except ImportError:
    try:
        from tools_L1 import get_10y_treasury
    except ImportError:
        get_10y_treasury = None

try:
    from .tools_L3 import get_ndx100_components
except ImportError:
    from tools_L3 import get_ndx100_components

from io import BytesIO, StringIO
import json
import queue
import re
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple
from zipfile import ZipFile
from xml.etree import ElementTree as ET

# =====================================================
# 第4层函数
# =====================================================

SOURCE_TIER_LICENSED_MANUAL = "licensed_manual/Wind"
SOURCE_TIER_LICENSED_PROVIDER = "licensed_provider/Wind"
SOURCE_TIER_OFFICIAL = "official"
SOURCE_TIER_COMPONENT_MODEL = "component_model"
SOURCE_TIER_THIRD_PARTY = "third_party_estimate"
SOURCE_TIER_PROXY = "proxy"
SOURCE_TIER_UNAVAILABLE = "unavailable"
NDX_COMPONENT_VALUATION_FALLBACK_REASON = (
    "component_model_used_for_yield_and_coverage_detail_while_licensed_or_official_ndx_aggregate_is_collected_separately"
)
NDX_FORWARD_QUALITY_FALLBACK_REASON = (
    "official_ndx_forward_earnings_quality_series_not_available_automatically_component_and_yahoo_revision_proxies_used_as_supporting_context"
)

VALUATION_FALLBACK_CHAIN = [
    SOURCE_TIER_LICENSED_PROVIDER,
    SOURCE_TIER_LICENSED_MANUAL,
    SOURCE_TIER_OFFICIAL,
    SOURCE_TIER_COMPONENT_MODEL,
    SOURCE_TIER_THIRD_PARTY,
    SOURCE_TIER_PROXY,
    SOURCE_TIER_UNAVAILABLE,
]

L4_COMPONENT_SNAPSHOT_CACHE: Dict[str, Tuple[pd.DataFrame, Dict[str, Any]]] = {}
L4_WIND_NDX_VALUATION_CACHE: Dict[str, Dict[str, Any]] = {}
_YAHOO_QUOTE_SUMMARY_SESSION: Optional[requests.Session] = None
L4_COMPONENT_SOURCE_DISAGREEMENT_THRESHOLDS = {
    "market_cap": 15.0,
    "trailing_pe": 25.0,
    "forward_pe": 25.0,
    "price_to_book": 60.0,
}
WIND_PERCENTILE_WINDOW_MIN_SAMPLES = {
    "1y": 200,
    "2y": 450,
    "5y": 1000,
    "10y": 1900,
}
L4_COMPONENT_FIELD_SOURCE_POLICY = {
    "market_cap": "yfinance_primary_yahoo_cross_check",
    "current_price": "yfinance_primary_yahoo_cross_check",
    "trailing_pe": "component_model_multi_source_cross_checked",
    "forward_pe": "component_model_multi_source_cross_checked",
    "price_to_book": "component_model_multi_source_cross_checked_supporting_only",
    "forward_eps": "yfinance_primary_yahoo_cross_check",
    "trailing_eps": "yfinance_primary_yahoo_cross_check",
    "earnings_growth": "supporting_proxy_yfinance_primary",
    "revenue_growth": "supporting_proxy_yfinance_primary",
    "profit_margin": "supporting_proxy_yfinance_primary",
    "gross_margin": "supporting_proxy_yfinance_primary",
    "operating_margin": "supporting_proxy_yfinance_primary",
    "fcf": "supporting_proxy_yfinance_primary",
    "fcf_yield": "supporting_proxy_yfinance_primary",
    "eps_estimate_current": "yahoo_quote_summary_primary",
    "eps_estimate_30d_ago": "yahoo_quote_summary_primary",
    "eps_estimate_60d_ago": "yahoo_quote_summary_primary",
    "eps_estimate_90d_ago": "yahoo_quote_summary_primary",
    "eps_revision_30d_pct": "yahoo_quote_summary_primary",
    "eps_revision_period": "yahoo_quote_summary_primary",
    "eps_estimate_analyst_count": "yahoo_quote_summary_primary",
    "sec_official_facts": "sec_xbrl_official_facts_primary",
    "eastmoney": "eastmoney_cross_check_only",
}
L4_YAHOO_PRIMARY_FIELDS = {
    "eps_estimate_current",
    "eps_estimate_30d_ago",
    "eps_estimate_60d_ago",
    "eps_estimate_90d_ago",
    "eps_revision_30d_pct",
    "eps_revision_period",
    "eps_estimate_analyst_count",
}
L4_CORE_COMPONENT_VALUATION_FIELDS = {"trailing_pe", "forward_pe"}
SEC_L4_METRIC_ALIASES = {
    "revenue": ["RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "SalesRevenueNet"],
    "net_income": ["NetIncomeLoss", "ProfitLoss"],
    "diluted_eps": ["EarningsPerShareDiluted"],
    "operating_cash_flow": [
        "NetCashProvidedByUsedInOperatingActivities",
        "NetCashProvidedByOperatingActivities",
    ],
    "capex": ["PaymentsToAcquirePropertyPlantAndEquipment", "CapitalExpenditures"],
    "share_repurchase": ["PaymentsForRepurchaseOfCommonStock", "PaymentsForRepurchaseOfEquity"],
    "research_development": ["ResearchAndDevelopmentExpense"],
    "assets": ["Assets"],
    "liabilities": ["Liabilities"],
}
SEC_HEADERS = {"User-Agent": "ndx-vnext/1.0 research contact@example.com"}
SEC_REQUEST_TIMEOUT = (4, 6)
SEC_CIK_MAP_WAIT_SECONDS = 6
SEC_COMPANY_FACTS_WAIT_SECONDS = 6
SEC_OFFICIAL_CHECK_TOTAL_BUDGET_SECONDS = 20
YFINANCE_INFO_WAIT_SECONDS = 6
YAHOO_QUOTE_SUMMARY_WAIT_SECONDS = 6
L4_COMPONENT_LIVE_SOURCE_TOTAL_BUDGET_SECONDS = 60


def _utc_timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _safe_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, str):
        value = value.strip().replace("%", "")
        if "," in value and "." not in value and re.search(r"\d,\d{1,2}$", value):
            value = value.replace(",", ".")
        else:
            value = value.replace(",", "")
        if not value:
            return None
    try:
        return float(value)
    except Exception:
        return None


def _round_or_none(value: Optional[float], digits: int = 2) -> Optional[float]:
    return round(value, digits) if value is not None and np.isfinite(value) else None


def _quality_block(
    *,
    source_tier: str,
    data_date: str,
    update_frequency: str,
    formula: str,
    coverage: Any = None,
    anomalies: Optional[List[Any]] = None,
    fallback_chain: Optional[List[str]] = None,
    source_disagreement: Any = None,
) -> Dict[str, Any]:
    return build_data_quality(
        provider=source_tier,
        source_name=source_tier,
        source_tier=source_tier,
        data_date=data_date,
        as_of_date=data_date,
        effective_date=data_date,
        collected_at_utc=_utc_timestamp(),
        update_frequency=update_frequency,
        formula=formula,
        methodology=formula,
        coverage=coverage or {},
        anomalies=anomalies or [],
        fallback_chain=fallback_chain or [],
        source_disagreement=source_disagreement or {},
    )


def _valuation_source_result(
    *,
    source_id: str,
    source_name: str,
    source_url: str,
    source_tier: str,
    metric: str,
    value: Optional[float],
    unit: str = "ratio",
    percentile_10y: Optional[float] = None,
    data_date: Optional[str] = None,
    methodology: str = "",
    availability: Optional[str] = None,
    unavailable_reason: Optional[str] = None,
    coverage: Any = None,
    formula: str = "",
    fallback_chain: Optional[List[str]] = None,
    source_disagreement: Any = None,
) -> Dict[str, Any]:
    """Normalize one L4 valuation source without inventing missing percentiles."""
    historical_percentile = _round_or_none(percentile_10y) if percentile_10y is not None else None
    normalized_availability = availability or ("available" if value is not None else "unavailable")
    result = {
        "source_id": source_id,
        "source": source_id,
        "source_name": source_name,
        "url": source_url,
        "source_url": source_url,
        "source_tier": source_tier,
        "metric": metric,
        "value": _round_or_none(value) if value is not None else None,
        "unit": unit,
        "percentile_10y": historical_percentile,
        "historical_percentile": historical_percentile,
        "data_date": data_date,
        "collected_at_utc": _utc_timestamp(),
        "methodology": methodology,
        "availability": normalized_availability,
        "unavailable_reason": unavailable_reason,
        "coverage": coverage or {},
        "formula": formula,
        "fallback_chain": fallback_chain or VALUATION_FALLBACK_CHAIN,
        "source_disagreement": source_disagreement or {},
    }
    return result


def _unavailable_valuation_source(
    *,
    source_id: str,
    source_name: str,
    source_url: str,
    metric: str,
    reason: str,
    methodology: str = "",
) -> Dict[str, Any]:
    return _valuation_source_result(
        source_id=source_id,
        source_name=source_name,
        source_url=source_url,
        source_tier=SOURCE_TIER_UNAVAILABLE,
        metric=metric,
        value=None,
        methodology=methodology,
        availability="unavailable",
        unavailable_reason=reason,
    )


def _wind_l4_disabled() -> bool:
    return str(os.environ.get("NDX_DISABLE_WIND_L4", "")).strip().lower() in {"1", "true", "yes", "on"}


def _wind_skill_dir() -> Path:
    return Path.home() / ".agents" / "skills" / "wind-mcp-skill"


def _wind_unavailable_snapshot(reason: str, *, date_str: Optional[str] = None) -> Dict[str, Any]:
    data_date = date_str or datetime.now().strftime("%Y-%m-%d")
    return {
        "name": "Wind NDX Valuation and Risk Premium Snapshot",
        "series_id": "WIND_NDX_VALUATION_RISK_PREMIUM",
        "value": None,
        "unit": "ratio/percent",
        "date": data_date,
        "source_tier": SOURCE_TIER_UNAVAILABLE,
        "source_name": "Wind index_data.get_index_fundamentals",
        "source_url": "https://aifinmarket.wind.com.cn",
        "availability": "unavailable",
        "unavailable_reason": reason,
        "error": reason,
        "data_quality": build_data_quality(
            provider="Wind",
            source_name="Wind index_data.get_index_fundamentals",
            source_url="https://aifinmarket.wind.com.cn",
            source_tier=SOURCE_TIER_UNAVAILABLE,
            data_date=data_date,
            as_of_date=data_date,
            effective_date=data_date,
            collected_at_utc=_utc_timestamp(),
            availability="unavailable",
            fallback_reason=reason,
            fallback_chain=[SOURCE_TIER_LICENSED_PROVIDER, SOURCE_TIER_COMPONENT_MODEL, SOURCE_TIER_THIRD_PARTY, SOURCE_TIER_UNAVAILABLE],
            license_note="licensed_provider",
            coverage={"index_code": "NDX.GI", "index_name": "Nasdaq 100"},
            methodology="Wind NDX index fundamentals snapshot unavailable this run",
            formula="Wind NDX PE/PB/PS and risk premium historical percentiles when licensed provider access is available",
            anomalies=[reason],
        ),
    }


def _call_wind_cli(server_type: str, tool_name: str, params: Dict[str, Any], *, timeout: int = 45) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    skill_dir = _wind_skill_dir()
    cli_path = skill_dir / "scripts" / "cli.mjs"
    if not cli_path.exists():
        return None, "wind_mcp_skill_cli_not_found"
    try:
        completed = subprocess.run(
            ["node", "scripts/cli.mjs", "call", server_type, tool_name, json.dumps(params, ensure_ascii=False)],
            cwd=str(skill_dir),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return None, "wind_cli_timeout"
    except Exception as exc:
        return None, f"wind_cli_runtime_error:{str(exc)[:120]}"

    stdout = (completed.stdout or "").strip()
    stderr = (completed.stderr or "").strip()
    if completed.returncode != 0:
        detail = stdout or stderr or f"exit_code={completed.returncode}"
        return None, f"wind_cli_failed:{detail[:240]}"
    if not stdout:
        return None, "wind_cli_empty_stdout"
    try:
        payload = json.loads(stdout)
        return payload if isinstance(payload, dict) else {"payload": payload}, None
    except Exception:
        return {"text": stdout}, None


def _json_from_text(text: Any) -> Any:
    if not isinstance(text, str):
        return text
    stripped = text.strip()
    if not stripped:
        return text
    try:
        return json.loads(stripped)
    except Exception:
        pass
    match = re.search(r"(\{.*\}|\[.*\])", stripped, flags=re.S)
    if match:
        try:
            return json.loads(match.group(1))
        except Exception:
            return text
    return text


def _wind_payload_body(payload: Any) -> Any:
    if isinstance(payload, dict) and isinstance(payload.get("content"), list) and payload["content"]:
        first = payload["content"][0]
        if isinstance(first, dict) and "text" in first:
            return _json_from_text(first.get("text"))
    if isinstance(payload, dict) and "text" in payload:
        return _json_from_text(payload.get("text"))
    return payload


def _rows_from_table_dict(payload: Dict[str, Any]) -> List[Dict[str, Any]]:
    columns = None
    rows = None
    for c_key in ("columns", "headers", "fields"):
        if isinstance(payload.get(c_key), list):
            columns = payload.get(c_key)
            break
    for r_key in ("data", "rows", "values"):
        if isinstance(payload.get(r_key), list):
            rows = payload.get(r_key)
            break
    if not rows:
        return []
    if columns and all(isinstance(row, list) for row in rows):
        labels = [
            str(column.get("name") or column.get("field") or column.get("title") or column)
            if isinstance(column, dict)
            else str(column)
            for column in columns
        ]
        return [
            {labels[idx]: row[idx] if idx < len(row) else None for idx in range(len(labels))}
            for row in rows
        ]
    return [row for row in rows if isinstance(row, dict)]


def _extract_wind_rows(payload: Any) -> List[Dict[str, Any]]:
    body = _wind_payload_body(payload)
    rows: List[Dict[str, Any]] = []

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            table_rows = _rows_from_table_dict(node)
            if table_rows:
                rows.extend(table_rows)
            elif any("风险溢价" in str(key) or "市盈率" in str(key) or str(key).lower() in {"pe", "pb", "ps"} for key in node):
                rows.append(node)
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(body)
    deduped: List[Dict[str, Any]] = []
    seen: Set[str] = set()
    for row in rows:
        key = json.dumps(row, ensure_ascii=False, sort_keys=True, default=str)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(row)
    return deduped


def _norm_wind_key(value: Any) -> str:
    return re.sub(r"[\s_()/（）:：-]+", "", str(value or "").strip().lower())


def _wind_row_value(row: Dict[str, Any], *labels: str, exclude: Iterable[str] = ()) -> Any:
    normalized = {_norm_wind_key(key): value for key, value in row.items()}
    excludes = tuple(_norm_wind_key(item) for item in exclude)
    for label in labels:
        needle = _norm_wind_key(label)
        for key, value in normalized.items():
            if needle and needle in key and not any(ex in key for ex in excludes):
                return value
    return None


def _wind_percent(value: Any) -> Optional[float]:
    number = _safe_float(value)
    if number is None:
        return None
    if abs(number) <= 1:
        number *= 100
    return _round_or_none(number, 2)


def _wind_parse_rank(value: Any) -> Dict[str, Any]:
    text = str(value or "").strip()
    match = re.search(r"([0-9]+)\s*/\s*([0-9]+)", text)
    if not match:
        return {}
    return {"rank": int(match.group(1)), "sample_count": int(match.group(2))}


def _wind_percentile_window_key(label: Any) -> Optional[str]:
    text = str(label or "")
    normalized = _norm_wind_key(text)
    match = re.search(r"(?:近|过去)([0-9]+)年", normalized)
    if match:
        return f"{int(match.group(1))}y"
    chinese_years = {
        "一年": "1y",
        "二年": "2y",
        "两年": "2y",
        "五年": "5y",
        "十年": "10y",
    }
    for token, key in chinese_years.items():
        if f"过去{token}" in normalized or f"近{token}" in normalized:
            return key
    if "历史分位" in normalized or "分位" in normalized:
        return None
    return None


def _wind_key_matches_window(label: Any, window: str) -> bool:
    if window == "unspecified":
        return True
    parsed_window = _wind_percentile_window_key(label)
    if parsed_window:
        return parsed_window == window
    normalized = _norm_wind_key(label)
    window_tokens = {
        "1y": ("1年", "一年"),
        "2y": ("2年", "二年", "两年"),
        "5y": ("5年", "五年"),
        "10y": ("10年", "十年"),
    }
    return any(token in normalized for token in window_tokens.get(window, ()))


def _wind_metric_percentile_windows(row: Dict[str, Any], metric_labels: Iterable[str]) -> Dict[str, Dict[str, Any]]:
    windows: Dict[str, Dict[str, Any]] = {}
    normalized_labels = tuple(_norm_wind_key(label) for label in metric_labels)
    for key, value in row.items():
        normalized_key = _norm_wind_key(key)
        if "分位" not in normalized_key:
            continue
        if not any(label and label in normalized_key for label in normalized_labels):
            continue
        window = _wind_percentile_window_key(key) or "unspecified"
        percentile = _wind_percent(value)
        if percentile is None:
            continue
        windows[window] = {
            "percentile": percentile,
            "source_column": str(key),
        }

    for window, payload in windows.items():
        window_token = window[:-1] if window.endswith("y") else None
        rank = None
        sample_count = None
        for key, value in row.items():
            normalized_key = _norm_wind_key(key)
            if not any(label and label in normalized_key for label in normalized_labels):
                continue
            if "序号" not in normalized_key and "排名" not in normalized_key and "rank" not in normalized_key:
                continue
            # Single-window Wind results often return generic rank columns such
            # as "市盈率序号" without repeating "过去10年". Accept that only when
            # the row exposes exactly one percentile window.
            key_window = _wind_percentile_window_key(key)
            if window_token and not _wind_key_matches_window(key, window):
                if len(windows) != 1 or key_window is not None:
                    continue
            elif window_token and key_window is None and len(windows) != 1:
                continue
            numeric_value = _safe_float(value)
            if numeric_value is None:
                continue
            if "最大" in normalized_key:
                sample_count = int(numeric_value)
            else:
                rank = int(numeric_value)
        if rank is not None:
            payload["rank"] = rank
        if sample_count is not None:
            payload["sample_count"] = sample_count
    return windows


def _wind_window_payload_valid(window: str, payload: Dict[str, Any]) -> bool:
    sample_count = payload.get("sample_count") if isinstance(payload, dict) else None
    floor = WIND_PERCENTILE_WINDOW_MIN_SAMPLES.get(window)
    if floor is None:
        return True
    return isinstance(sample_count, int) and sample_count >= floor


def _filter_wind_percentile_windows(
    windows: Dict[str, Dict[str, Any]],
) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]]]:
    accepted: Dict[str, Dict[str, Any]] = {}
    rejected: List[Dict[str, Any]] = []
    for window, payload in (windows or {}).items():
        if window == "unspecified" or _wind_window_payload_valid(window, payload):
            accepted[window] = payload
        else:
            rejected.append(
                {
                    "window": window,
                    "percentile": payload.get("percentile") if isinstance(payload, dict) else None,
                    "sample_count": payload.get("sample_count") if isinstance(payload, dict) else None,
                    "min_sample_count": WIND_PERCENTILE_WINDOW_MIN_SAMPLES.get(window),
                    "reason": "sample_count_too_small_for_declared_window",
                    "source_column": payload.get("source_column") if isinstance(payload, dict) else None,
                }
            )
    return accepted, rejected


def _merge_wind_percentile_windows(base: Dict[str, Dict[str, Any]], extra: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    merged = dict(base or {})
    for window, payload in (extra or {}).items():
        if window == "unspecified" and window in merged:
            continue
        merged[window] = payload
    return merged


def _fetch_wind_metric_percentile_windows(
    metric_label: str,
    windows: Iterable[str],
) -> Tuple[Dict[str, Dict[str, Any]], List[Dict[str, Any]], Optional[str]]:
    merged: Dict[str, Dict[str, Any]] = {}
    issues: List[Dict[str, Any]] = []
    data_date: Optional[str] = None
    for window in windows:
        years = window[:-1] if window.endswith("y") else window
        question = f"纳斯达克100指数最新{metric_label}在过去{years}年中的分位数"
        payload, error = _call_wind_cli(
            "index_data",
            "get_index_fundamentals",
            {"question": question},
        )
        if error or payload is None:
            issues.append({"metric": metric_label, "window": window, "reason": error or "wind_empty_payload"})
            continue
        parsed = _parse_wind_ndx_valuation_payload(payload)
        data_date = data_date or parsed.get("data_date")
        source_key = {
            "市盈率": "pe_percentile_windows",
            "市净率": "pb_percentile_windows",
            "市销率": "ps_percentile_windows",
            "风险溢价": "risk_premium_percentile_windows",
        }.get(metric_label)
        parsed_windows = parsed.get(source_key, {}) if source_key else {}
        window_payload = parsed_windows.get(window)
        if not window_payload:
            issues.append({"metric": metric_label, "window": window, "reason": "window_not_returned"})
            continue
        merged[window] = window_payload
    accepted, rejected = _filter_wind_percentile_windows(merged)
    issues.extend({"metric": metric_label, **item} for item in rejected)
    return accepted, issues, data_date


def _parse_wind_ndx_valuation_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    rows = _extract_wind_rows(payload)
    parsed: Dict[str, Any] = {
        "index_code": None,
        "index_name": None,
        "data_date": None,
        "pe": None,
        "pb": None,
        "ps": None,
        "risk_premium": None,
        "pe_historical_percentile": None,
        "pb_historical_percentile": None,
        "ps_historical_percentile": None,
        "risk_premium_historical_percentile": None,
        "risk_premium_rank": {},
        "sample_start": None,
        "pe_percentile_windows": {},
        "pb_percentile_windows": {},
        "ps_percentile_windows": {},
        "risk_premium_percentile_windows": {},
    }

    for row in rows:
        if not isinstance(row, dict):
            continue
        parsed["index_code"] = parsed["index_code"] or _wind_row_value(row, "指数代码", "证券代码", "windcode", "wind代码")
        parsed["index_name"] = parsed["index_name"] or _wind_row_value(row, "指数简称", "指数名称", "证券简称", "名称")
        parsed["data_date"] = parsed["data_date"] or _wind_row_value(row, "日期", "交易日期", "数据日期", "截止日期")
        parsed["sample_start"] = parsed["sample_start"] or _wind_row_value(row, "最早成分日期", "样本开始", "开始日期", "begin")

        parsed["pe"] = parsed["pe"] if parsed["pe"] is not None else _safe_float(_wind_row_value(row, "市盈率", "pe", "pet_ttm", exclude=("分位", "排名", "rank")))
        parsed["pb"] = parsed["pb"] if parsed["pb"] is not None else _safe_float(_wind_row_value(row, "市净率", "pb", exclude=("分位", "排名", "rank")))
        parsed["ps"] = parsed["ps"] if parsed["ps"] is not None else _safe_float(_wind_row_value(row, "市销率", "ps", exclude=("分位", "排名", "rank")))
        parsed["risk_premium"] = parsed["risk_premium"] if parsed["risk_premium"] is not None else _safe_float(
            _wind_row_value(row, "风险溢价", exclude=("分位", "排名", "rank"))
        )

        parsed["pe_historical_percentile"] = parsed["pe_historical_percentile"] if parsed["pe_historical_percentile"] is not None else _wind_percent(
            _wind_row_value(row, "市盈率历史分位", "市盈率分位", "市盈率在过去一年中的分位数", "pe历史分位", "pe分位")
        )
        parsed["pb_historical_percentile"] = parsed["pb_historical_percentile"] if parsed["pb_historical_percentile"] is not None else _wind_percent(
            _wind_row_value(row, "市净率历史分位", "市净率分位", "市净率在过去一年中的分位数", "pb历史分位", "pb分位")
        )
        parsed["ps_historical_percentile"] = parsed["ps_historical_percentile"] if parsed["ps_historical_percentile"] is not None else _wind_percent(
            _wind_row_value(row, "市销率历史分位", "市销率分位", "市销率在过去一年中的分位数", "ps历史分位", "ps分位")
        )
        parsed["risk_premium_historical_percentile"] = (
            parsed["risk_premium_historical_percentile"]
            if parsed["risk_premium_historical_percentile"] is not None
            else _wind_percent(_wind_row_value(row, "风险溢价历史分位", "风险溢价分位", "风险溢价在过去一年中的分位数"))
        )
        parsed["pe_percentile_windows"] = _merge_wind_percentile_windows(
            parsed["pe_percentile_windows"],
            _wind_metric_percentile_windows(row, ("市盈率", "pe")),
        )
        parsed["pb_percentile_windows"] = _merge_wind_percentile_windows(
            parsed["pb_percentile_windows"],
            _wind_metric_percentile_windows(row, ("市净率", "pb")),
        )
        parsed["ps_percentile_windows"] = _merge_wind_percentile_windows(
            parsed["ps_percentile_windows"],
            _wind_metric_percentile_windows(row, ("市销率", "ps")),
        )
        parsed["risk_premium_percentile_windows"] = _merge_wind_percentile_windows(
            parsed["risk_premium_percentile_windows"],
            _wind_metric_percentile_windows(row, ("风险溢价",)),
        )
        if not parsed["risk_premium_rank"]:
            rank_text = _wind_row_value(row, "风险溢价排名", "风险溢价rank", "排名", "rank")
            parsed["risk_premium_rank"] = _wind_parse_rank(rank_text)
            if not parsed["risk_premium_rank"]:
                rank = _safe_float(_wind_row_value(row, "风险溢价序号", exclude=("最大",)))
                sample_count = _safe_float(_wind_row_value(row, "风险溢价最大序号"))
                if rank is not None and sample_count is not None:
                    parsed["risk_premium_rank"] = {"rank": int(rank), "sample_count": int(sample_count)}

    if parsed["data_date"]:
        try:
            parsed["data_date"] = pd.to_datetime(parsed["data_date"], errors="coerce").strftime("%Y-%m-%d")
        except Exception:
            parsed["data_date"] = str(parsed["data_date"])
    if parsed["sample_start"]:
        try:
            parsed["sample_start"] = pd.to_datetime(parsed["sample_start"], errors="coerce").strftime("%Y-%m-%d")
        except Exception:
            parsed["sample_start"] = str(parsed["sample_start"])

    parsed["index_code"] = parsed["index_code"] or "NDX.GI"
    parsed["index_name"] = parsed["index_name"] or "Nasdaq 100"
    return parsed


def _merge_wind_ndx_valuation_parse(base: Dict[str, Any], extra: Dict[str, Any]) -> Dict[str, Any]:
    merged = dict(base)
    for key, value in extra.items():
        if key.endswith("_percentile_windows") and isinstance(value, dict):
            merged[key] = _merge_wind_percentile_windows(merged.get(key, {}), value)
        elif merged.get(key) in (None, {}, []) and value not in (None, {}, []):
            merged[key] = value
    return merged


def get_ndx_wind_valuation_snapshot(end_date: str = None) -> Dict[str, Any]:
    """Wind NDX-specific valuation and risk-premium snapshot.

    Live mode calls Wind once per run through the local wind-mcp-skill CLI.
    Backtests do not use current Wind data unless a dated historical contract is
    added later.
    """
    date_str = end_date or datetime.now().strftime("%Y-%m-%d")
    cache_key = f"wind_ndx_valuation:{end_date or 'live'}"
    cached = L4_WIND_NDX_VALUATION_CACHE.get(cache_key)
    if cached is not None:
        result = deepcopy(cached)
        result["cache_hit"] = True
        return result
    if _wind_l4_disabled():
        return _wind_unavailable_snapshot("wind_l4_disabled_by_NDX_DISABLE_WIND_L4", date_str=date_str)
    if end_date:
        return _wind_unavailable_snapshot("backtest_skipped_current_wind_snapshot_not_point_in_time", date_str=date_str)

    question = "纳斯达克100指数最新市盈率市净率市销率风险溢价"
    payload, error = _call_wind_cli(
        "index_data",
        "get_index_fundamentals",
        {"question": question},
    )
    if error or payload is None:
        result = _wind_unavailable_snapshot(error or "wind_empty_payload", date_str=date_str)
        L4_WIND_NDX_VALUATION_CACHE[cache_key] = deepcopy(result)
        return result

    parsed = _parse_wind_ndx_valuation_payload(payload)
    percentile_issues: List[Dict[str, Any]] = []
    pe_windows, pe_window_issues, pe_window_date = _fetch_wind_metric_percentile_windows(
        "市盈率",
        ("1y", "2y", "5y", "10y"),
    )
    percentile_issues.extend(pe_window_issues)
    risk_premium_windows, risk_window_issues, risk_window_date = _fetch_wind_metric_percentile_windows(
        "风险溢价",
        ("1y", "10y"),
    )
    percentile_issues.extend(risk_window_issues)
    parsed["pe_percentile_windows"] = _merge_wind_percentile_windows(parsed.get("pe_percentile_windows", {}), pe_windows)
    parsed["risk_premium_percentile_windows"] = _merge_wind_percentile_windows(
        parsed.get("risk_premium_percentile_windows", {}),
        risk_premium_windows,
    )
    parsed["data_date"] = parsed.get("data_date") or pe_window_date or risk_window_date
    value_keys = ("pe", "pb", "ps", "risk_premium", "pe_historical_percentile", "risk_premium_historical_percentile")
    if not any(parsed.get(key) is not None for key in value_keys):
        result = _wind_unavailable_snapshot("wind_payload_missing_ndx_valuation_fields", date_str=date_str)
        result["raw_wind_payload_compact"] = _compact_wind_payload(payload)
        L4_WIND_NDX_VALUATION_CACHE[cache_key] = deepcopy(result)
        return result

    data_date = str(parsed.get("data_date") or date_str)
    pe_windows, rejected_pe_windows = _filter_wind_percentile_windows(parsed.get("pe_percentile_windows") or {})
    percentile_issues.extend({"metric": "市盈率", **item} for item in rejected_pe_windows)
    pe_historical_percentile = (
        pe_windows.get("10y", {}).get("percentile")
        if isinstance(pe_windows.get("10y"), dict)
        else None
    )
    pe_historical_window = "10y" if pe_historical_percentile is not None else None
    risk_windows, rejected_risk_windows = _filter_wind_percentile_windows(parsed.get("risk_premium_percentile_windows") or {})
    percentile_issues.extend({"metric": "风险溢价", **item} for item in rejected_risk_windows)
    risk_premium_historical_percentile = (
        risk_windows.get("10y", {}).get("percentile")
        if isinstance(risk_windows.get("10y"), dict)
        else None
    )
    risk_premium_historical_window = "10y" if risk_premium_historical_percentile is not None else None
    value = {
        "index_code": parsed.get("index_code"),
        "index_name": parsed.get("index_name"),
        "data_date": data_date,
        "PE": _round_or_none(parsed.get("pe")),
        "PB": _round_or_none(parsed.get("pb")),
        "PS": _round_or_none(parsed.get("ps")),
        "RiskPremium": _round_or_none(parsed.get("risk_premium"), 4),
        "PEHistoricalPercentile": pe_historical_percentile,
        "PEHistoricalPercentileWindow": pe_historical_window,
        "PEPercentileWindows": pe_windows,
        "PBHistoricalPercentile": parsed.get("pb_historical_percentile"),
        "PBPercentileWindows": parsed.get("pb_percentile_windows") or {},
        "PSHistoricalPercentile": parsed.get("ps_historical_percentile"),
        "PSPercentileWindows": parsed.get("ps_percentile_windows") or {},
        "RiskPremiumHistoricalPercentile": risk_premium_historical_percentile,
        "RiskPremiumHistoricalPercentileWindow": risk_premium_historical_window,
        "RiskPremiumPercentileWindows": risk_windows,
        "RiskPremiumRank": (
            {
                "rank": risk_windows["10y"].get("rank"),
                "sample_count": risk_windows["10y"].get("sample_count"),
            }
            if isinstance(risk_windows.get("10y"), dict)
            and risk_windows["10y"].get("rank") is not None
            and risk_windows["10y"].get("sample_count") is not None
            else {}
        ),
        "WindPercentileIssues": percentile_issues,
        "sample_start": parsed.get("sample_start"),
        "comparison_targets": ["get_ndx_pe_and_earnings_yield", "get_damodaran_us_implied_erp", "get_equity_risk_premium"],
        "authority_boundary": (
            "Wind is the primary licensed provider snapshot for NDX-specific PE/PB/PS and risk premium. "
            "Damodaran remains a US market ERP background reference; simple yield gap is fallback/diagnostic only."
        ),
        "data_source_note": "数据来源于万得 Wind 金融数据服务。",
        "MetricAuthority": {
            "PE": _component_metric_authority(
                usage="core_allowed",
                authority="licensed_provider_wind_index_fundamentals",
                reason="Wind returns an NDX index-level valuation field, not a yfinance component proxy.",
                source=SOURCE_TIER_LICENSED_PROVIDER,
            ),
            "PB": _component_metric_authority(
                usage="core_allowed",
                authority="licensed_provider_wind_index_fundamentals",
                reason="Wind returns an NDX index-level PB field; use before component-model PB.",
                source=SOURCE_TIER_LICENSED_PROVIDER,
            ),
            "PS": _component_metric_authority(
                usage="core_allowed",
                authority="licensed_provider_wind_index_fundamentals",
                reason="Wind returns an NDX index-level PS field.",
                source=SOURCE_TIER_LICENSED_PROVIDER,
            ),
            "RiskPremium": _component_metric_authority(
                usage="core_allowed",
                authority="licensed_provider_wind_ndx_specific_risk_premium",
                reason="NDX-specific Wind risk premium; do not mix it with Damodaran US ERP or simple yield gap.",
                source=SOURCE_TIER_LICENSED_PROVIDER,
            ),
        },
    }
    result = {
        "name": "Wind NDX Valuation and Risk Premium Snapshot",
        "series_id": "WIND_NDX_VALUATION_RISK_PREMIUM",
        "value": value,
        "unit": "ratio/percent",
        "date": data_date,
        "source_tier": SOURCE_TIER_LICENSED_PROVIDER,
        "source_name": "Wind index_data.get_index_fundamentals",
        "source_url": "https://aifinmarket.wind.com.cn",
        "availability": "available",
        "notes": "Wind NDX-specific valuation and risk premium primary snapshot. 数据来源于万得 Wind 金融数据服务。",
        "data_quality": build_data_quality(
            provider="Wind",
            source_name="Wind index_data.get_index_fundamentals",
            source_url="https://aifinmarket.wind.com.cn",
            source_tier=SOURCE_TIER_LICENSED_PROVIDER,
            data_date=data_date,
            as_of_date=data_date,
            effective_date=data_date,
            collected_at_utc=_utc_timestamp(),
            availability="available",
            fallback_reason="none",
            fallback_chain=[SOURCE_TIER_LICENSED_PROVIDER, SOURCE_TIER_COMPONENT_MODEL, SOURCE_TIER_THIRD_PARTY, SOURCE_TIER_UNAVAILABLE],
            license_note="licensed_provider",
            coverage={
                "index_code": parsed.get("index_code"),
                "index_name": parsed.get("index_name"),
                "sample_start": parsed.get("sample_start"),
                "provider_question": question,
                "pe_percentile_window_queries": ["1y", "2y", "5y", "10y"],
                "risk_premium_percentile_window_queries": ["1y", "10y"],
                "pe_historical_percentile_window": pe_historical_window,
                "risk_premium_historical_percentile_window": risk_premium_historical_window,
            },
            methodology=(
                "Wind index fundamentals natural-language query for Nasdaq 100 PE/PB/PS and NDX-specific risk premium; "
                "separate explicit single-window queries request PE and risk-premium percentiles to avoid ambiguous multi-window NL tables."
            ),
            formula=(
                "Provider-published index-level PE/PB/PS and risk premium; percentiles normalized to 0-100 when Wind returns 0-1 ratios. "
                "10Y percentile fields are accepted only when the returned sample count is consistent with the declared window."
            ),
            anomalies=[item["reason"] for item in percentile_issues if item.get("reason")],
            source_disagreement={
                "compare_against": {
                    "component_model": "get_ndx_pe_and_earnings_yield",
                    "us_market_background_erp": "get_damodaran_us_implied_erp",
                    "fallback_diagnostic": "get_equity_risk_premium",
                },
                "interpretation_boundary": (
                    "RiskPremium is NDX-specific Wind data; Damodaran is US market background and simple yield gap is a fallback diagnostic."
                ),
            },
            metric_authority=value["MetricAuthority"],
        ),
    }
    L4_WIND_NDX_VALUATION_CACHE[cache_key] = deepcopy(result)
    return result


def _compact_wind_payload(payload: Any) -> Any:
    if isinstance(payload, dict):
        compact = {}
        for key, value in payload.items():
            if key in {"content", "data", "rows", "result"}:
                compact[key] = _compact_wind_payload(value)
            elif isinstance(value, (str, int, float)) or value is None:
                compact[key] = value
            if len(compact) >= 5:
                break
        return compact
    if isinstance(payload, list):
        return [_compact_wind_payload(item) for item in payload[:3]]
    return str(payload)[:200]


def _html_text(html: str) -> str:
    try:
        from bs4 import BeautifulSoup

        return BeautifulSoup(html, "html.parser").get_text("\n", strip=True)
    except Exception:
        return re.sub(r"<[^>]+>", "\n", html)


def _first_number(pattern: str, text: str) -> Optional[float]:
    match = re.search(pattern, text, flags=re.I | re.S)
    return _safe_float(match.group(1)) if match else None


def _first_date(pattern: str, text: str) -> Optional[str]:
    match = re.search(pattern, text, flags=re.I | re.S)
    return match.group(1).strip() if match else None


def _percent_or_none(value: Any, digits: int = 2) -> Optional[float]:
    number = _safe_float(value)
    if number is None:
        return None
    if abs(number) <= 1:
        number *= 100
    return _round_or_none(number, digits)


def _excel_serial_to_date(value: Any, *, date1904: bool = False) -> Optional[str]:
    number = _safe_float(value)
    if number is None or number < 20000:
        return None
    try:
        if date1904:
            number += 1462
        return (datetime(1899, 12, 30) + timedelta(days=int(number))).strftime("%Y-%m-%d")
    except Exception:
        return None


def _normalize_label(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _xlsx_cell_text(cell: ET.Element, shared_strings: List[str]) -> Any:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return "".join(text.text or "" for text in cell.findall(".//{*}t")).strip()

    raw_value = cell.findtext("{*}v")
    if raw_value is None:
        return ""
    raw_value = raw_value.strip()
    if cell_type == "s":
        idx = int(_safe_float(raw_value) or 0)
        return shared_strings[idx] if 0 <= idx < len(shared_strings) else ""
    if cell_type == "str":
        return raw_value
    number = _safe_float(raw_value)
    return number if number is not None else raw_value


def _xlsx_col_index(cell_ref: str) -> int:
    match = re.match(r"([A-Z]+)", str(cell_ref or "A1").upper())
    letters = match.group(1) if match else "A"
    value = 0
    for char in letters:
        value = value * 26 + (ord(char) - ord("A") + 1)
    return value - 1


def _parse_xlsx_tables(content: bytes) -> List[pd.DataFrame]:
    """Parse simple XLSX sheets with stdlib so official Damodaran files do not require openpyxl."""
    with ZipFile(BytesIO(content)) as zf:
        shared_strings: List[str] = []
        if "xl/sharedStrings.xml" in zf.namelist():
            root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
            for item in root.findall(".//{*}si"):
                shared_strings.append("".join(text.text or "" for text in item.findall(".//{*}t")).strip())

        rels: Dict[str, str] = {}
        rels_root = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
        for rel in rels_root.findall("{*}Relationship"):
            target = rel.attrib.get("Target", "")
            if target.startswith("/"):
                path = target.lstrip("/")
            else:
                path = f"xl/{target}"
            rels[rel.attrib.get("Id", "")] = path.replace("\\", "/")

        workbook = ET.fromstring(zf.read("xl/workbook.xml"))
        workbook_pr = workbook.find("{*}workbookPr")
        date1904 = bool(workbook_pr is not None and str(workbook_pr.attrib.get("date1904", "")).lower() in {"1", "true"})
        tables: List[pd.DataFrame] = []
        for sheet in workbook.findall(".//{*}sheet"):
            rel_id = sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
            sheet_path = rels.get(rel_id or "")
            if not sheet_path or sheet_path not in zf.namelist():
                continue
            sheet_root = ET.fromstring(zf.read(sheet_path))
            rows: List[List[Any]] = []
            for row in sheet_root.findall(".//{*}sheetData/{*}row"):
                values: List[Any] = []
                for cell in row.findall("{*}c"):
                    idx = _xlsx_col_index(cell.attrib.get("r", ""))
                    while len(values) <= idx:
                        values.append("")
                    values[idx] = _xlsx_cell_text(cell, shared_strings)
                rows.append(values)
            if not rows:
                continue
            width = max(len(row) for row in rows)
            normalized_rows = [row + [""] * (width - len(row)) for row in rows]
            header_idx = next((i for i, row in enumerate(normalized_rows) if any(str(item).strip() for item in row)), 0)
            headers = [str(item).strip() or f"column_{idx}" for idx, item in enumerate(normalized_rows[header_idx])]
            data_rows = normalized_rows[header_idx + 1 :]
            frame = pd.DataFrame(data_rows, columns=headers)
            frame.attrs["date1904"] = date1904
            tables.append(frame)
        return tables


def _read_excel_tables(content: bytes) -> List[pd.DataFrame]:
    try:
        sheets = pd.read_excel(BytesIO(content), sheet_name=None)
        return list(sheets.values())
    except Exception:
        return _parse_xlsx_tables(content)


def _find_column(columns: Iterable[Any], *needles: str, any_needles: Iterable[str] = ()) -> Optional[Any]:
    any_needles_l = tuple(item.lower() for item in any_needles)
    for col in columns:
        label = _normalize_label(col)
        if all(needle.lower() in label for needle in needles) and (
            not any_needles_l or any(needle in label for needle in any_needles_l)
        ):
            return col
    return None


def _latest_row_by_date(table: pd.DataFrame, date_col: Any, *, max_date: Optional[str] = None) -> Optional[pd.Series]:
    working = table.copy()
    date1904 = bool(table.attrs.get("date1904"))

    def sort_key(value: Any) -> str:
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d")
        serial_date = _excel_serial_to_date(value, date1904=date1904)
        if serial_date:
            return serial_date
        parsed = pd.to_datetime(value, errors="coerce")
        if pd.isna(parsed):
            return ""
        return parsed.strftime("%Y-%m-%d")

    working["_date_key"] = working[date_col].map(sort_key)
    working = working[working["_date_key"].astype(bool)].sort_values("_date_key")
    if max_date:
        working = working[working["_date_key"] <= max_date]
    if working.empty:
        return None
    return working.iloc[-1]


def get_crowdedness_dashboard(end_date: str = None) -> Dict[str, Any]:
    """
    获取拥挤度仪表盘 - V3精简版（专注仓位拥挤度）

    核心指标（移除VIX/VXN重复，专注仓位拥挤度）：
    1. SKEW指数：尾部风险溢价（黑天鹅担忧程度）
    2. QQQ Put/Call比率：期权市场的看空/看多情绪对比
    3. QQQ空仓率：做空仓位的拥挤程度

    数据源策略：
    - SKEW: yfinance (^SKEW) - 可靠
    - Put/Call: yfinance期权链
    - 空仓率: yfinance info - 通常为None（ETF不提供）

    架构说明：
    - VIX和VXN/VIX已在第二层独立存在，此处不再重复
    - 遵循"单一事实来源"原则（PROJECT_ARCHITECTURE.md 原则2）
    """
    if end_date:
        effective_date = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        effective_date = datetime.now()

    crowdedness_data = {}
    print("  - 获取拥挤度仪表盘...", end="", flush=True)

    # 1. SKEW Index (尾部风险指标) - 回测模式只取回测日可见的历史行。
    skew_val = None
    skew_date = None
    if YF_AVAILABLE:
        try:
            if end_date:
                skew_start = effective_date - timedelta(days=30)
                skew_hist = cached_yf_download(
                    "^SKEW",
                    start=skew_start,
                    end=effective_date + timedelta(days=1),
                    interval="1d",
                    progress=False,
                    auto_adjust=False,
                )
                if not skew_hist.empty:
                    skew_hist = clean_yfinance_dataframe(skew_hist)
                    skew_hist = skew_hist[skew_hist.index <= effective_date]
            else:
                skew_hist = get_yf_ticker_history_with_retry("^SKEW", period="5d", attempts=3, pause_seconds=1.0)
                skew_hist = clean_yfinance_dataframe(skew_hist)
            if not skew_hist.empty and "close" in skew_hist.columns:
                skew_val = round(float(skew_hist["close"].iloc[-1]), 2)
                skew_date = skew_hist.index[-1].strftime("%Y-%m-%d")
        except Exception as e:
            logging.warning(f"SKEW from yfinance failed: {e}")

    crowdedness_data["skew_index"] = {
        "value": skew_val,
        "date": skew_date,
        "source": "yfinance (^SKEW)" if skew_val is not None else "unavailable",
        "interpretation": ">150: 尾部风险溢价高 (市场担忧黑天鹅); <120: 尾部风险溢价低"
    }

    # 2. QQQ Put/Call Ratio (基于期权持仓量) - yfinance期权链
    pc_ratio = None
    pc_source = "unavailable"
    pc_notes = ""

    if end_date:
        pc_source = "backtest_unavailable"
        pc_notes = "回测模式未接入历史可见的 QQQ 期权 OI 快照；当前期权链不得伪标为回测日证据。"
    elif YF_AVAILABLE:
        try:
            opt_date, opt_chain = get_yf_option_chain_with_retry("QQQ", attempts=3, pause_seconds=1.0)

            # 取最近到期的期权合约

            put_oi = opt_chain.puts['openInterest'].sum()
            call_oi = opt_chain.calls['openInterest'].sum()

            if call_oi > 0 and put_oi > 0:
                pc_ratio = round(put_oi / call_oi, 2)
                pc_source = "yfinance"
                pc_notes = f"基于到期日: {opt_date} 的期权持仓量"
            else:
                raise Exception("OpenInterest data is zero")
        except Exception as e:
            logging.warning(f"yfinance Put/Call failed: {e}")
            pc_notes = f"yfinance期权链失败: {str(e)[:50]}"

    crowdedness_data["qqq_put_call_ratio_oi"] = {
        "value": pc_ratio,
        "date": None if end_date else effective_date.strftime("%Y-%m-%d"),
        "source": pc_source,
        "notes": pc_notes if pc_notes else "期权数据获取失败",
        "interpretation": ">1.2: 看空情绪主导; <0.8: 看多情绪主导"
    }

    # 3. QQQ空仓率 (Short Interest)
    if end_date:
        crowdedness_data["qqq_short_interest_percent"] = {
            "value": None,
            "date": None,
            "source": "backtest_unavailable",
            "interpretation": ">2%: 空仓拥挤 (看空情绪浓); <1%: 空仓稀少 (看空情绪弱)",
            "notes": "回测模式未接入历史可见的 ETF short-interest 快照；当前 info 不进入回测证据。"
        }
    elif YF_AVAILABLE:
        try:
            qqq_info = get_yf_ticker_info_with_retry("QQQ", attempts=3, pause_seconds=1.0)
            short_percent = qqq_info.get("shortPercentOfFloat")
            crowdedness_data["qqq_short_interest_percent"] = {
                "value": round(short_percent * 100, 2) if short_percent else None,
                "date": effective_date.strftime("%Y-%m-%d"),
                "source": "yfinance",
                "interpretation": ">2%: 空仓拥挤 (看空情绪浓); <1%: 空仓稀少 (看空情绪弱)",
                "notes": "ETF通常不提供空仓数据，此字段可能为空"
            }
        except Exception as e:
            crowdedness_data["qqq_short_interest_percent"] = {
                "value": None,
                "error": f"Failed to fetch: {str(e)[:30]}",
                "source": "failed",
                "notes": "ETF通常不提供空仓数据"
            }
    else:
        crowdedness_data["qqq_short_interest_percent"] = {
            "value": None,
            "source": "unavailable",
            "notes": "yfinance未安装"
        }

    print(" [OK]")
    return {
        "name": "Crowdedness Dashboard",
        "value": crowdedness_data,
        "date": effective_date.strftime("%Y-%m-%d"),
        "source_name": "Mixed (yfinance)",
        "notes": "拥挤度核心指标：SKEW(尾部风险)、VIX(恐慌程度)、VXN/VIX(科技股相对压力)、Put/Call比率、空仓率"
    }


def calculate_weighted_metrics(df: pd.DataFrame) -> Dict[str, Any]:
    """计算NDX成分股聚合估值，避免把PE做简单平均。"""
    if df.empty:
        return {}

    working = df.copy()
    if "ticker" not in working.columns:
        working["ticker"] = working.index.astype(str)
    if "market_cap" not in working.columns:
        return {}

    working["market_cap"] = working["market_cap"].map(_safe_float)
    total_constituents = len(working)
    total_market_cap = float(working["market_cap"].dropna().clip(lower=0).sum())
    if total_market_cap <= 0:
        return {}

    anomalies: List[Dict[str, Any]] = []
    coverage: Dict[str, Dict[str, Any]] = {}
    metrics: Dict[str, Any] = {"coverage": coverage, "anomalies": anomalies}

    def _metric_coverage(metric_key: str, valid: pd.DataFrame, excluded: List[Dict[str, Any]]) -> None:
        covered_market_cap = float(valid["market_cap"].sum()) if not valid.empty else 0.0
        coverage[metric_key] = {
            "constituents_used": int(len(valid)),
            "total_constituents": int(total_constituents),
            "constituent_coverage_pct": round(len(valid) / total_constituents * 100, 2) if total_constituents else 0.0,
            "market_cap_coverage_pct": round(covered_market_cap / total_market_cap * 100, 2) if total_market_cap else 0.0,
            "excluded": excluded[:20],
        }

    def _valid_pe_frame(column: str, metric_key: str) -> pd.DataFrame:
        excluded: List[Dict[str, Any]] = []
        pe_values = working[column].map(_safe_float) if column in working.columns else pd.Series([None] * len(working))
        frame = working.assign(_pe=pe_values)
        valid = frame[(frame["market_cap"] > 0) & (frame["_pe"] > 0)].copy()
        for _, row in frame.loc[~frame.index.isin(valid.index)].iterrows():
            reason = "missing_or_nonpositive_market_cap" if not row.get("market_cap") or row.get("market_cap") <= 0 else f"invalid_{column}"
            item = {"ticker": row.get("ticker"), "metric": metric_key, "reason": reason}
            excluded.append(item)
            anomalies.append(item)
        _metric_coverage(metric_key, valid, excluded)
        return valid

    trailing = _valid_pe_frame("trailing_pe", "trailing_pe")
    if not trailing.empty:
        earnings = trailing["market_cap"] / trailing["_pe"]
        covered_cap = float(trailing["market_cap"].sum())
        total_earnings = float(earnings.sum())
        if total_earnings > 0:
            metrics["weighted_trailing_pe"] = round(covered_cap / total_earnings, 2)
            metrics["weighted_earnings_yield"] = round(total_earnings / covered_cap * 100, 2)

    forward = _valid_pe_frame("forward_pe", "forward_pe")
    if not forward.empty:
        forward_earnings = forward["market_cap"] / forward["_pe"]
        covered_cap = float(forward["market_cap"].sum())
        total_forward_earnings = float(forward_earnings.sum())
        if total_forward_earnings > 0:
            metrics["weighted_forward_pe"] = round(covered_cap / total_forward_earnings, 2)
            metrics["weighted_forward_earnings_yield"] = round(total_forward_earnings / covered_cap * 100, 2)
            metrics["forward_earnings_proxy_usd"] = round(total_forward_earnings, 2)
            metrics["forward_earnings_coverage_market_cap_usd"] = round(covered_cap, 2)

    if "forward_pe" in working.columns and "trailing_pe" in working.columns:
        growth_frame = working.assign(
            _forward_pe=working["forward_pe"].map(_safe_float),
            _trailing_pe=working["trailing_pe"].map(_safe_float),
        )
        valid_growth = growth_frame[
            (growth_frame["market_cap"] > 0)
            & (growth_frame["_forward_pe"] > 0)
            & (growth_frame["_trailing_pe"] > 0)
        ].copy()
        growth_excluded = [
            {"ticker": row.get("ticker"), "metric": "forward_eps_growth_proxy", "reason": "missing_forward_or_trailing_pe"}
            for _, row in growth_frame.loc[~growth_frame.index.isin(valid_growth.index)].iterrows()
        ]
        _metric_coverage("forward_eps_growth_proxy", valid_growth, growth_excluded)
        if not valid_growth.empty:
            trailing_earnings = valid_growth["market_cap"] / valid_growth["_trailing_pe"]
            forward_earnings = valid_growth["market_cap"] / valid_growth["_forward_pe"]
            total_trailing_earnings = float(trailing_earnings.sum())
            total_forward_earnings = float(forward_earnings.sum())
            if total_trailing_earnings > 0:
                metrics["weighted_forward_eps_growth_proxy_pct"] = round((total_forward_earnings / total_trailing_earnings - 1.0) * 100.0, 2)
                metrics["forward_eps_growth_proxy_method"] = "sum(market_cap / forward_pe) / sum(market_cap / trailing_pe) - 1"

    for source_column, metric_key, output_key in [
        ("earnings_growth", "earnings_growth", "weighted_earnings_growth_pct"),
        ("revenue_growth", "revenue_growth", "weighted_revenue_growth_pct"),
        ("profit_margin", "profit_margin", "weighted_profit_margin_pct"),
        ("gross_margin", "gross_margin", "weighted_gross_margin_pct"),
        ("operating_margin", "operating_margin", "weighted_operating_margin_pct"),
    ]:
        if source_column not in working.columns:
            continue
        values = working[source_column].map(_safe_float)
        frame = working.assign(_metric=values)
        valid_metric = frame[(frame["market_cap"] > 0) & frame["_metric"].notna()].copy()
        metric_excluded = [
            {"ticker": row.get("ticker"), "metric": metric_key, "reason": f"missing_{source_column}"}
            for _, row in frame.loc[~frame.index.isin(valid_metric.index)].iterrows()
        ]
        _metric_coverage(metric_key, valid_metric, metric_excluded)
        if not valid_metric.empty:
            weights = valid_metric["market_cap"] / valid_metric["market_cap"].sum()
            number = float(np.average(valid_metric["_metric"], weights=weights))
            if abs(number) <= 1.0:
                number *= 100.0
            metrics[output_key] = round(number, 2)

    fcf_values = working["fcf"].map(_safe_float) if "fcf" in working.columns else pd.Series([None] * len(working))
    if fcf_values.isna().all() and "fcf_yield" in working.columns:
        fcf_yield_values = working["fcf_yield"].map(_safe_float)
        fcf_values = working["market_cap"] * fcf_yield_values / 100.0
    fcf_frame = working.assign(_fcf=fcf_values)
    valid_fcf = fcf_frame[(fcf_frame["market_cap"] > 0) & fcf_frame["_fcf"].notna()].copy()
    fcf_excluded: List[Dict[str, Any]] = []
    for _, row in fcf_frame.loc[~fcf_frame.index.isin(valid_fcf.index)].iterrows():
        reason = "missing_or_nonpositive_market_cap" if not row.get("market_cap") or row.get("market_cap") <= 0 else "missing_fcf"
        item = {"ticker": row.get("ticker"), "metric": "fcf_yield", "reason": reason}
        fcf_excluded.append(item)
        anomalies.append(item)
    _metric_coverage("fcf_yield", valid_fcf, fcf_excluded)
    if not valid_fcf.empty:
        covered_cap = float(valid_fcf["market_cap"].sum())
        total_fcf = float(valid_fcf["_fcf"].sum())
        if covered_cap > 0:
            metrics["weighted_fcf_yield"] = round(total_fcf / covered_cap * 100, 2)

    if "price_to_book" in working.columns:
        pb_values = working["price_to_book"].map(_safe_float)
        pb_frame = working.assign(_pb=pb_values)
        valid_pb = pb_frame[(pb_frame["market_cap"] > 0) & (pb_frame["_pb"] > 0)].copy()
        pb_excluded = [
            {"ticker": row.get("ticker"), "metric": "price_to_book", "reason": "invalid_price_to_book"}
            for _, row in pb_frame.loc[~pb_frame.index.isin(valid_pb.index)].iterrows()
        ]
        _metric_coverage("price_to_book", valid_pb, pb_excluded)
        if not valid_pb.empty:
            covered_cap = float(valid_pb["market_cap"].sum())
            implied_book_equity = valid_pb["market_cap"] / valid_pb["_pb"]
            total_book_equity = float(implied_book_equity.sum())
            if covered_cap > 0 and total_book_equity > 0:
                metrics["weighted_price_to_book"] = round(covered_cap / total_book_equity, 2)
                metrics["price_to_book_method"] = "covered_market_cap / sum(market_cap / component_price_to_book)"

    return metrics


def _median(values: List[float]) -> Optional[float]:
    clean = sorted(value for value in values if value is not None and np.isfinite(value))
    if not clean:
        return None
    mid = len(clean) // 2
    if len(clean) % 2:
        return clean[mid]
    return (clean[mid - 1] + clean[mid]) / 2.0


def _component_metric_authority(
    *,
    usage: str,
    authority: str,
    reason: str,
    source: str = SOURCE_TIER_COMPONENT_MODEL,
    reference_sources: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    return {
        "source": source,
        "usage": usage,
        "authority": authority,
        "reason": reason,
        "reference_sources": reference_sources or [],
    }


def audit_component_valuation_metrics(metrics: Dict[str, Any], third_party_checks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Decide which yfinance component-model fields may speak as core L4 evidence."""
    metric_specs = {
        "PE": {"component_key": "weighted_trailing_pe", "third_party_metric": "ndx_trailing_pe", "threshold_pct": 30.0, "blocks_publish": True},
        "ForwardPE": {"component_key": "weighted_forward_pe", "third_party_metric": "ndx_forward_pe", "threshold_pct": 30.0, "blocks_publish": True},
        "PriceToBook": {"component_key": "weighted_price_to_book", "third_party_field": "pb", "threshold_pct": 75.0, "blocks_publish": False},
    }
    authority: Dict[str, Any] = {
        "PE": _component_metric_authority(
            usage="core_allowed",
            authority="component_model_cross_checked",
            reason="Component aggregate PE is computed as covered market cap / covered trailing earnings and must remain close to published PE checks.",
        ),
        "TrailingPE": _component_metric_authority(
            usage="core_allowed",
            authority="component_model_cross_checked",
            reason="Alias of PE; same authority as PE.",
        ),
        "ForwardPE": _component_metric_authority(
            usage="core_allowed",
            authority="component_model_cross_checked",
            reason="Component aggregate Forward PE is computed as covered market cap / covered forward earnings and must remain close to published Forward PE checks.",
        ),
        "EarningsYield": _component_metric_authority(
            usage="core_allowed",
            authority="derived_from_cross_checked_pe",
            reason="Derived from aggregate trailing earnings / covered market cap; usable only while PE cross-check is clean.",
        ),
        "ForwardEarningsYield": _component_metric_authority(
            usage="core_allowed",
            authority="derived_from_cross_checked_forward_pe",
            reason="Derived from aggregate forward earnings / covered market cap; usable only while Forward PE cross-check is clean.",
        ),
        "FCFYield": _component_metric_authority(
            usage="supporting_only",
            authority="component_model_uncross_checked",
            reason="Uses yfinance freeCashflow fields with no official NDX aggregate or third-party cross-check; do not use as the primary yield-gap input.",
        ),
        "ForwardEPSGrowthProxyPct": _component_metric_authority(
            usage="supporting_only",
            authority="proxy_only",
            reason="Aggregate forward/trailing earnings proxy derived from component PE fields; not an official NDX earnings growth estimate.",
        ),
        "WeightedEarningsGrowthPct": _component_metric_authority(
            usage="supporting_only",
            authority="proxy_only",
            reason="Market-cap weighted yfinance earningsGrowth field; may mix quarterly/annual conventions across tickers.",
        ),
        "WeightedRevenueGrowthPct": _component_metric_authority(
            usage="supporting_only",
            authority="proxy_only",
            reason="Market-cap weighted yfinance revenueGrowth field; use only as a broad proxy.",
        ),
        "WeightedProfitMarginPct": _component_metric_authority(
            usage="supporting_only",
            authority="proxy_only",
            reason="Market-cap weighted yfinance profitMargins field; not an official NDX aggregate margin.",
        ),
        "WeightedGrossMarginPct": _component_metric_authority(
            usage="supporting_only",
            authority="proxy_only",
            reason="Market-cap weighted yfinance grossMargins field; sector and accounting differences make it supporting-only.",
        ),
        "WeightedOperatingMarginPct": _component_metric_authority(
            usage="supporting_only",
            authority="proxy_only",
            reason="Market-cap weighted yfinance operatingMargins field; not an official NDX aggregate margin.",
        ),
        "PriceToBook": _component_metric_authority(
            usage="supporting_only",
            authority="component_model_cross_check_required",
            reason="PB is highly sensitive to accounting and negative/low book equity; must be cross-checked before any narrative use.",
        ),
    }
    issues: List[Dict[str, Any]] = []
    rejected: Dict[str, Any] = {}
    checked_refs: Dict[str, List[Dict[str, Any]]] = {}

    def reference_values(spec: Dict[str, Any]) -> List[Dict[str, Any]]:
        refs = []
        for item in third_party_checks:
            if not isinstance(item, dict) or item.get("availability") != "available":
                continue
            value = None
            if spec.get("third_party_field"):
                value = _safe_float(item.get(spec["third_party_field"]))
            elif item.get("metric") == spec.get("third_party_metric"):
                value = _safe_float(item.get("value"))
            if value is None or value <= 0:
                continue
            refs.append(
                {
                    "source_id": item.get("source_id") or item.get("source") or item.get("source_name"),
                    "source_name": item.get("source_name"),
                    "metric": item.get("metric"),
                    "value": _round_or_none(value),
                    "data_date": item.get("data_date") or item.get("date"),
                }
            )
        return refs

    for public_key, spec in metric_specs.items():
        component_value = _safe_float(metrics.get(spec["component_key"]))
        refs = reference_values(spec)
        checked_refs[public_key] = refs
        if public_key in authority:
            authority[public_key]["reference_sources"] = refs
        if public_key == "PE":
            authority["TrailingPE"]["reference_sources"] = refs
        if component_value is None or not refs:
            continue
        ref_median = _median([_safe_float(item.get("value")) for item in refs])
        if not ref_median or ref_median <= 0:
            continue
        diff_pct = abs(component_value - ref_median) / ref_median * 100.0
        if diff_pct <= spec["threshold_pct"]:
            continue
        issue = {
            "issue_type": "valuation_source_disagreement",
            "metric": public_key,
            "severity": "high",
            "component_value": _round_or_none(component_value),
            "reference_median": _round_or_none(ref_median),
            "relative_diff_pct": _round_or_none(diff_pct),
            "threshold_pct": spec["threshold_pct"],
            "reference_sources": refs,
            "blocks_publish": bool(spec.get("blocks_publish")),
            "action": "reject_metric_from_core_evidence" if not spec.get("blocks_publish") else "block_publish_until_manual_or_official_override",
        }
        issues.append(issue)
        rejected[public_key] = issue
        authority[public_key] = _component_metric_authority(
            usage="rejected",
            authority="failed_cross_check",
            reason=f"Component value differs from third-party median by {round(diff_pct, 2)}%, above {spec['threshold_pct']}% threshold.",
            reference_sources=refs,
        )
        if public_key == "PE":
            authority["TrailingPE"] = authority[public_key]
            authority["EarningsYield"] = _component_metric_authority(
                usage="rejected",
                authority="derived_from_failed_pe_cross_check",
                reason="EarningsYield is rejected because its PE source failed cross-check.",
                reference_sources=refs,
            )
        if public_key == "ForwardPE":
            authority["ForwardEarningsYield"] = _component_metric_authority(
                usage="rejected",
                authority="derived_from_failed_forward_pe_cross_check",
                reason="ForwardEarningsYield is rejected because its Forward PE source failed cross-check.",
                reference_sources=refs,
            )

    return {
        "schema_version": "l4_component_model_authority_v1",
        "metric_authority": authority,
        "source_disagreement_issues": issues,
        "rejected_metrics": rejected,
        "reference_sources": checked_refs,
        "core_usage_rule": (
            "Only metrics with usage=core_allowed may support L4 core claims. "
            "supporting_only metrics can contextualize but cannot independently prove valuation attractiveness."
        ),
    }


def reset_l4_component_snapshot_cache() -> None:
    """Clear the run-local L4 component snapshot cache."""
    L4_COMPONENT_SNAPSHOT_CACHE.clear()
    L4_WIND_NDX_VALUATION_CACHE.clear()


def _raw_yahoo_value(container: Dict[str, Any], key: str) -> Any:
    value = container.get(key) if isinstance(container, dict) else None
    if isinstance(value, dict):
        return value.get("raw")
    return value


def _component_row_from_yfinance(ticker: str, info: Dict[str, Any]) -> Dict[str, Any]:
    market_cap = _safe_float(info.get("marketCap"))
    fcf = _safe_float(info.get("freeCashflow"))
    return {
        "ticker": ticker,
        "market_cap": market_cap,
        "current_price": _safe_float(info.get("currentPrice") or info.get("regularMarketPrice")),
        "forward_eps": _safe_float(info.get("forwardEps")),
        "trailing_eps": _safe_float(info.get("trailingEps")),
        "forward_pe": _safe_float(info.get("forwardPE")),
        "trailing_pe": _safe_float(info.get("trailingPE")),
        "price_to_book": _safe_float(info.get("priceToBook")),
        "earnings_growth": _safe_float(info.get("earningsGrowth") or info.get("earningsQuarterlyGrowth")),
        "revenue_growth": _safe_float(info.get("revenueGrowth")),
        "profit_margin": _safe_float(info.get("profitMargins")),
        "gross_margin": _safe_float(info.get("grossMargins")),
        "operating_margin": _safe_float(info.get("operatingMargins")),
        "fcf": fcf,
        "fcf_yield": (fcf / market_cap) * 100 if fcf is not None and market_cap else None,
    }


def _run_l4_best_effort(
    label: str,
    *,
    wait_seconds: int,
    fn: Callable[[], Any],
) -> Tuple[Optional[Any], Optional[str]]:
    result_queue: "queue.Queue[Tuple[Optional[Any], Optional[str]]]" = queue.Queue(maxsize=1)

    def worker() -> None:
        try:
            result_queue.put((fn(), None))
        except Exception as exc:
            result_queue.put((None, str(exc)[:160]))

    thread = threading.Thread(target=worker, daemon=True, name=f"l4-best-effort-{label}")
    thread.start()
    try:
        return result_queue.get(timeout=wait_seconds)
    except queue.Empty:
        return None, f"{label}_timeout_after_{wait_seconds}s"


def _fetch_yfinance_info_best_effort(ticker: str) -> Tuple[Dict[str, Any], Optional[str]]:
    info, error = _run_l4_best_effort(
        "yfinance_info",
        wait_seconds=YFINANCE_INFO_WAIT_SECONDS,
        fn=lambda: get_yf_ticker_info_with_retry(ticker, attempts=2, pause_seconds=0.5),
    )
    if isinstance(info, dict):
        return info, None
    return {}, error or "empty_info"


def _fetch_yahoo_quote_summary_direct(symbol: str) -> Tuple[Dict[str, Any], Optional[str]]:
    """Direct Yahoo quoteSummary fetch; used as a parallel check, not a blind replacement."""
    try:
        session_obj, session_error = _run_l4_best_effort(
            "yahoo_quote_summary_session",
            wait_seconds=YAHOO_QUOTE_SUMMARY_WAIT_SECONDS,
            fn=_get_yahoo_quote_summary_session,
        )
        if session_error or session_obj is None:
            return {}, session_error or "missing_session"
        session = session_obj
        modules = [
            "financialData",
            "defaultKeyStatistics",
            "summaryDetail",
            "earningsTrend",
            "recommendationTrend",
        ]
        response, request_error = _run_l4_best_effort(
            "yahoo_quote_summary",
            wait_seconds=YAHOO_QUOTE_SUMMARY_WAIT_SECONDS,
            fn=lambda: session.get(
                f"https://query2.finance.yahoo.com/v10/finance/quoteSummary/{symbol}",
                params={"modules": ",".join(modules), "crumb": getattr(session, "_crumb", "")},
                timeout=(4, 6),
                proxies=get_requests_proxies(),
            ),
        )
        if request_error or response is None:
            return {}, request_error or "missing_response"
        response.raise_for_status()
        result = response.json().get("quoteSummary", {}).get("result", [{}])
        return (result[0] if result else {}), None
    except Exception as exc:
        return {}, str(exc)[:160]


def _get_yahoo_quote_summary_session() -> requests.Session:
    global _YAHOO_QUOTE_SUMMARY_SESSION
    if _YAHOO_QUOTE_SUMMARY_SESSION is not None and getattr(_YAHOO_QUOTE_SUMMARY_SESSION, "_crumb", None):
        return _YAHOO_QUOTE_SUMMARY_SESSION
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
    session.get("https://fc.yahoo.com", timeout=10, proxies=get_requests_proxies())
    crumb_response = session.get(
        "https://query2.finance.yahoo.com/v1/test/getcrumb",
        timeout=10,
        proxies=get_requests_proxies(),
    )
    crumb_response.raise_for_status()
    session._crumb = crumb_response.text
    _YAHOO_QUOTE_SUMMARY_SESSION = session
    return session


def _component_row_from_yahoo_quote_summary(ticker: str, data: Dict[str, Any]) -> Dict[str, Any]:
    fd = data.get("financialData", {}) if isinstance(data, dict) else {}
    ks = data.get("defaultKeyStatistics", {}) if isinstance(data, dict) else {}
    sd = data.get("summaryDetail", {}) if isinstance(data, dict) else {}
    market_cap = _safe_float(_raw_yahoo_value(sd, "marketCap") or _raw_yahoo_value(ks, "enterpriseValue"))
    fcf = _safe_float(_raw_yahoo_value(fd, "freeCashflow"))
    eps_trend = _extract_yahoo_eps_revision(data)
    return {
        "ticker": ticker,
        "market_cap": market_cap,
        "current_price": _safe_float(_raw_yahoo_value(fd, "currentPrice") or _raw_yahoo_value(sd, "regularMarketPrice")),
        "forward_eps": _safe_float(_raw_yahoo_value(ks, "forwardEps")),
        "trailing_eps": _safe_float(_raw_yahoo_value(ks, "trailingEps")),
        "forward_pe": _safe_float(_raw_yahoo_value(ks, "forwardPE")),
        "trailing_pe": _safe_float(_raw_yahoo_value(sd, "trailingPE")),
        "price_to_book": _safe_float(_raw_yahoo_value(ks, "priceToBook")),
        "earnings_growth": _safe_float(_raw_yahoo_value(fd, "earningsGrowth")),
        "revenue_growth": _safe_float(_raw_yahoo_value(fd, "revenueGrowth")),
        "profit_margin": _safe_float(_raw_yahoo_value(ks, "profitMargins")),
        "gross_margin": _safe_float(_raw_yahoo_value(fd, "grossMargins")),
        "operating_margin": _safe_float(_raw_yahoo_value(fd, "operatingMargins")),
        "fcf": fcf,
        "fcf_yield": (fcf / market_cap) * 100 if fcf is not None and market_cap else None,
        **eps_trend,
    }


def _extract_yahoo_eps_revision(data: Dict[str, Any]) -> Dict[str, Any]:
    trends = data.get("earningsTrend", {}).get("trend", []) if isinstance(data, dict) else []
    chosen = None
    for preferred in ("+1y", "0y", "+1q", "0q"):
        chosen = next((item for item in trends if item.get("period") == preferred), None)
        if chosen:
            break
    if not isinstance(chosen, dict):
        return {}
    estimate = chosen.get("earningsEstimate", {}) if isinstance(chosen.get("earningsEstimate"), dict) else {}
    eps_trend = chosen.get("epsTrend", {}) if isinstance(chosen.get("epsTrend"), dict) else {}
    current = _safe_float(_raw_yahoo_value(eps_trend, "current") or _raw_yahoo_value(estimate, "avg"))
    days_30 = _safe_float(_raw_yahoo_value(eps_trend, "30daysAgo"))
    days_60 = _safe_float(_raw_yahoo_value(eps_trend, "60daysAgo"))
    days_90 = _safe_float(_raw_yahoo_value(eps_trend, "90daysAgo"))
    revision_30d = (current / days_30 - 1.0) * 100.0 if current and days_30 else None
    return {
        "eps_estimate_current": current,
        "eps_estimate_30d_ago": days_30,
        "eps_estimate_60d_ago": days_60,
        "eps_estimate_90d_ago": days_90,
        "eps_revision_30d_pct": _round_or_none(revision_30d),
        "eps_revision_period": chosen.get("period"),
        "eps_estimate_analyst_count": _safe_float(_raw_yahoo_value(estimate, "numberOfAnalysts")),
    }


def _relative_diff_pct(left: Any, right: Any) -> Optional[float]:
    left_f = _safe_float(left)
    right_f = _safe_float(right)
    if left_f is None or right_f is None or right_f == 0:
        return None
    return abs(left_f - right_f) / abs(right_f) * 100.0


def _merge_component_source_rows(
    ticker: str,
    yfinance_row: Dict[str, Any],
    yahoo_row: Dict[str, Any],
    source_errors: Dict[str, str],
) -> Dict[str, Any]:
    output_keys = [
        "market_cap",
        "current_price",
        "forward_eps",
        "trailing_eps",
        "forward_pe",
        "trailing_pe",
        "price_to_book",
        "earnings_growth",
        "revenue_growth",
        "profit_margin",
        "gross_margin",
        "operating_margin",
        "fcf",
        "fcf_yield",
        "eps_estimate_current",
        "eps_estimate_30d_ago",
        "eps_estimate_60d_ago",
        "eps_estimate_90d_ago",
        "eps_revision_30d_pct",
        "eps_revision_period",
        "eps_estimate_analyst_count",
    ]
    merged: Dict[str, Any] = {"ticker": ticker}
    field_sources: Dict[str, str] = {}
    source_switches: List[Dict[str, Any]] = []
    disagreements: List[Dict[str, Any]] = []

    for key in output_keys:
        yf_value = yfinance_row.get(key)
        yahoo_value = yahoo_row.get(key)
        selected_source = None
        if key in L4_YAHOO_PRIMARY_FIELDS and yahoo_value is not None:
            merged[key] = yahoo_value
            field_sources[key] = "yahoo_quote_summary"
            selected_source = "yahoo_quote_summary"
            source_switches.append(
                {
                    "field": key,
                    "selected_source": "yahoo_quote_summary",
                    "previous_source": "yfinance" if yf_value is not None else None,
                    "reason": "field_policy_yahoo_primary",
                }
            )
        elif yf_value is not None:
            merged[key] = yf_value
            field_sources[key] = "yfinance"
            selected_source = "yfinance"
        elif yahoo_value is not None:
            merged[key] = yahoo_value
            field_sources[key] = "yahoo_quote_summary"
            selected_source = "yahoo_quote_summary"
            source_switches.append(
                {
                    "field": key,
                    "selected_source": "yahoo_quote_summary",
                    "previous_source": None,
                    "reason": "yfinance_missing",
                }
            )
        else:
            merged[key] = None

        threshold = L4_COMPONENT_SOURCE_DISAGREEMENT_THRESHOLDS.get(key)
        diff_pct = _relative_diff_pct(yf_value, yahoo_value)
        if threshold is not None and diff_pct is not None and diff_pct > threshold:
            severity = "high" if diff_pct > threshold * 2 else "medium"
            action = "field_rejected_from_core_component_calculation" if (
                severity == "high" and key in L4_CORE_COMPONENT_VALUATION_FIELDS
            ) else "field_marked_for_review"
            if action == "field_rejected_from_core_component_calculation":
                merged[key] = None
                field_sources[key] = "rejected_source_disagreement"
            disagreements.append(
                {
                    "ticker": ticker,
                    "field": key,
                    "yfinance_value": _round_or_none(_safe_float(yf_value)),
                    "yahoo_value": _round_or_none(_safe_float(yahoo_value)),
                    "relative_diff_pct": _round_or_none(diff_pct),
                    "threshold_pct": threshold,
                    "severity": severity,
                    "selected_source_before_gate": selected_source,
                    "blocks_publish": False,
                    "action": action,
                }
            )

    merged["field_sources"] = field_sources
    merged["component_source_switches"] = source_switches
    merged["component_source_disagreements"] = disagreements
    merged["component_source_errors"] = source_errors
    return merged


def _sec_request_get_best_effort(
    url: str,
    *,
    wait_seconds: int,
) -> Tuple[Optional[Any], Optional[str]]:
    result_queue: "queue.Queue[Tuple[Optional[Any], Optional[str]]]" = queue.Queue(maxsize=1)

    def worker() -> None:
        try:
            response = requests.get(
                url,
                headers=SEC_HEADERS,
                timeout=SEC_REQUEST_TIMEOUT,
                proxies=get_requests_proxies(),
            )
            result_queue.put((response, None))
        except Exception as exc:
            result_queue.put((None, str(exc)[:160]))

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    try:
        return result_queue.get(timeout=wait_seconds)
    except queue.Empty:
        return None, f"sec_request_timeout_after_{wait_seconds}s"


def _sec_cik_map_cache_path() -> Path:
    cache_dir = Path(path_config.cache_dir) / "sec"
    cache_dir.mkdir(parents=True, exist_ok=True)
    return cache_dir / "company_tickers_map.json"


def _parse_sec_cik_mapping(payload: Any) -> Dict[str, str]:
    if not isinstance(payload, dict):
        return {}
    mapping: Dict[str, str] = {}
    for key, item in payload.items():
        if isinstance(item, dict):
            ticker = item.get("ticker") or key
            cik_value = item.get("cik_str") or item.get("cik")
        else:
            ticker = key
            cik_value = item
        if ticker and cik_value is not None:
            mapping[str(ticker).upper()] = str(cik_value).zfill(10)
    return mapping


def _load_sec_cik_map_cache() -> Optional[Dict[str, str]]:
    path = _sec_cik_map_cache_path()
    if not path.exists():
        return None
    try:
        mapping = _parse_sec_cik_mapping(json.loads(path.read_text(encoding="utf-8")))
    except Exception:
        return None
    return mapping or None


def _write_sec_cik_map_cache(mapping: Dict[str, str]) -> None:
    if not mapping:
        return
    try:
        _sec_cik_map_cache_path().write_text(
            json.dumps(mapping, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except Exception:
        return


def _sec_cik_map() -> Dict[str, str]:
    cache_key = "_l4_sec_cik_map"
    cached = getattr(_sec_cik_map, cache_key, None)
    if isinstance(cached, dict):
        return cached
    cached_mapping = _load_sec_cik_map_cache()
    if isinstance(cached_mapping, dict):
        setattr(_sec_cik_map, cache_key, cached_mapping)
        setattr(_sec_cik_map, "_l4_sec_cik_map_error", "")
        return cached_mapping
    try:
        response, request_error = _sec_request_get_best_effort(
            "https://www.sec.gov/files/company_tickers.json",
            wait_seconds=SEC_CIK_MAP_WAIT_SECONDS,
        )
        if request_error or response is None:
            setattr(_sec_cik_map, "_l4_sec_cik_map_error", request_error or "missing_response")
            setattr(_sec_cik_map, cache_key, {})
            return {}
        response.raise_for_status()
        mapping = _parse_sec_cik_mapping(response.json())
        setattr(_sec_cik_map, cache_key, mapping)
        setattr(_sec_cik_map, "_l4_sec_cik_map_error", "")
        _write_sec_cik_map_cache(mapping)
        return mapping
    except Exception as exc:
        setattr(_sec_cik_map, "_l4_sec_cik_map_error", str(exc)[:160])
        setattr(_sec_cik_map, cache_key, {})
        return {}


def _latest_sec_fact_before(units: Dict[str, Any], *, end_date: Optional[str]) -> Optional[Dict[str, Any]]:
    candidates: List[Dict[str, Any]] = []
    for unit_key in ("USD", "USD/shares", "shares"):
        for item in units.get(unit_key, []) if isinstance(units.get(unit_key), list) else []:
            if item.get("form") not in {"10-K", "10-Q"}:
                continue
            filed = item.get("filed")
            if end_date and filed and str(filed) > end_date:
                continue
            candidate = dict(item)
            candidate["unit"] = unit_key
            candidates.append(candidate)
    if not candidates:
        return None
    return sorted(candidates, key=lambda item: (str(item.get("filed") or ""), str(item.get("end") or "")))[-1]


def _fetch_sec_xbrl_summary(ticker: str, *, end_date: Optional[str] = None) -> Tuple[Dict[str, Any], Optional[str]]:
    cik = _sec_cik_map().get(ticker.upper())
    if not cik:
        cik_error = getattr(_sec_cik_map, "_l4_sec_cik_map_error", "")
        return {}, cik_error or "missing_cik"
    try:
        response, request_error = _sec_request_get_best_effort(
            f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json",
            wait_seconds=SEC_COMPANY_FACTS_WAIT_SECONDS,
        )
        if request_error or response is None:
            return {}, request_error or "missing_response"
        response.raise_for_status()
        facts = response.json().get("facts", {}).get("us-gaap", {})
        summary: Dict[str, Any] = {"cik": cik, "facts": {}}
        filed_dates: List[str] = []
        for public_key, aliases in SEC_L4_METRIC_ALIASES.items():
            selected = None
            selected_alias = None
            for alias in aliases:
                metric = facts.get(alias, {})
                fact = _latest_sec_fact_before(metric.get("units", {}), end_date=end_date) if isinstance(metric, dict) else None
                if fact:
                    selected = fact
                    selected_alias = alias
                    break
            if selected:
                summary[public_key] = selected.get("val")
                summary[f"{public_key}_filed_date"] = selected.get("filed")
                summary[f"{public_key}_period_end"] = selected.get("end")
                summary[f"{public_key}_form"] = selected.get("form")
                summary[f"{public_key}_source_accession"] = selected.get("accn")
                summary[f"{public_key}_xbrl_tag"] = selected_alias
                summary["facts"][public_key] = {
                    "availability": "available",
                    "value": selected.get("val"),
                    "filed_date": selected.get("filed"),
                    "period_end": selected.get("end"),
                    "form": selected.get("form"),
                    "source_accession": selected.get("accn"),
                    "xbrl_tag": selected_alias,
                    "unit": selected.get("unit"),
                }
                if selected.get("filed"):
                    filed_dates.append(str(selected.get("filed")))
            else:
                summary["facts"][public_key] = {
                    "availability": "unavailable",
                    "aliases_checked": list(aliases),
                }
        summary["latest_filed_date"] = max(filed_dates) if filed_dates else None
        summary["availability"] = "available" if filed_dates else "unavailable"
        return summary, None
    except Exception as exc:
        return {}, str(exc)[:160]


def _fetch_eastmoney_gmain_indicator(secucode: str) -> Tuple[Dict[str, Any], Optional[str]]:
    try:
        response = requests.get(
            "https://datacenter-web.eastmoney.com/api/data/v1/get",
            params={
                "reportName": "RPT_USF10_FN_GMAININDICATOR",
                "columns": "ALL",
                "filter": f'(SECUCODE="{secucode}")',
                "pageNumber": "1",
                "pageSize": "2",
                "sortColumns": "REPORT_DATE",
                "sortTypes": "-1",
                "source": "WEB",
                "client": "WEB",
            },
            headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"},
            timeout=12,
            proxies=get_requests_proxies(),
        )
        response.raise_for_status()
        rows = response.json().get("result", {}).get("data", [])
        row = rows[0] if rows else {}
        if not isinstance(row, dict):
            return {}, "empty_response"
        return {
            "report_date": row.get("REPORT_DATE"),
            "revenue": row.get("OPERATE_INCOME"),
            "basic_eps": row.get("BASIC_EPS"),
            "roe_avg": row.get("ROE_AVG"),
            "roa": row.get("ROA"),
            "gross_margin": row.get("GROSS_PROFIT_RATIO"),
            "debt_asset_ratio": row.get("DEBT_ASSET_RATIO"),
            "availability": "available",
        }, None
    except Exception as exc:
        return {}, str(exc)[:160]


def _select_audit_tickers(df: pd.DataFrame, total_tickers: int = 20) -> Set[str]:
    tickers = set(M7_TICKERS)
    if not df.empty and "market_cap" in df.columns:
        by_cap = df.copy()
        by_cap["market_cap"] = by_cap["market_cap"].map(_safe_float)
        by_cap = by_cap.sort_values("market_cap", ascending=False)
        tickers.update(str(ticker).upper() for ticker in by_cap["ticker"].head(total_tickers).tolist())
    return {ticker for ticker in tickers if ticker}


def _m7_eps_revision_snapshot_from_frame(m7_frame: pd.DataFrame) -> Dict[str, Any]:
    if m7_frame.empty or "eps_revision_30d_pct" not in m7_frame.columns:
        return {"availability": "unavailable", "reason": "snapshot_missing_eps_revision", "members": {}}
    snapshots: Dict[str, Any] = {}
    weighted_changes: List[Tuple[float, float]] = []
    analyst_counts: List[int] = []
    for _, row in m7_frame.iterrows():
        ticker = str(row.get("ticker") or "").upper()
        if not ticker:
            continue
        revision = _safe_float(row.get("eps_revision_30d_pct"))
        current = _safe_float(row.get("eps_estimate_current"))
        days_30 = _safe_float(row.get("eps_estimate_30d_ago"))
        days_90 = _safe_float(row.get("eps_estimate_90d_ago"))
        analyst_count = _safe_float(row.get("eps_estimate_analyst_count"))
        if analyst_count is not None:
            analyst_counts.append(int(analyst_count))
        weight = _safe_float(row.get("market_cap")) or 0.0
        if weight > 0 and revision is not None:
            weighted_changes.append((weight, revision))
        snapshots[ticker] = {
            "next_year_eps_current": _round_or_none(current),
            "next_year_eps_30d_ago": _round_or_none(days_30),
            "next_year_eps_90d_ago": _round_or_none(days_90),
            "revision_30d_pct": _round_or_none(revision),
            "revision_90d_pct": _round_or_none((current / days_90 - 1.0) * 100.0) if current and days_90 else None,
            "revision_direction_30d": _direction_from_change(revision),
            "next_year_analyst_count": int(analyst_count) if analyst_count is not None else None,
            "source": "yahoo_quote_summary earningsTrend via L4 component snapshot",
        }
    weighted_revision = None
    if weighted_changes:
        total_weight = sum(weight for weight, _ in weighted_changes)
        weighted_revision = sum(weight * change for weight, change in weighted_changes) / total_weight if total_weight else None
    available = [item for item in snapshots.values() if item.get("revision_30d_pct") is not None]
    return {
        "availability": "available" if available else "unavailable",
        "coverage": {"available_members": len(available), "total_members": len(M7_TICKERS)},
        "weighted_next_year_eps_revision_30d_pct": _round_or_none(weighted_revision),
        "revision_direction_30d": _direction_from_change(weighted_revision),
        "median_next_year_analyst_count": int(np.median(analyst_counts)) if analyst_counts else None,
        "members": snapshots,
        "methodology": "M7 analyst revision proxy from Yahoo earningsTrend in the shared L4 component snapshot.",
    }


def _weighted_eps_revision_from_frame(df: pd.DataFrame) -> Optional[float]:
    if df.empty or "eps_revision_30d_pct" not in df.columns or "market_cap" not in df.columns:
        return None
    values: List[float] = []
    weights: List[float] = []
    for _, row in df.iterrows():
        revision = _safe_float(row.get("eps_revision_30d_pct"))
        market_cap = _safe_float(row.get("market_cap"))
        if revision is None or market_cap is None or market_cap <= 0:
            continue
        values.append(revision)
        weights.append(market_cap)
    if not values or not weights or sum(weights) <= 0:
        return None
    return _round_or_none(float(np.average(values, weights=weights)))


def _enrich_component_rows_with_official_checks(
    df: pd.DataFrame,
    *,
    end_date: Optional[str],
    include_current_web_checks: bool,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    if df.empty:
        return df, {"sec_xbrl": {"checked": 0, "available": 0}, "eastmoney": {"checked": 0, "available": 0}}
    enriched = df.copy()
    if "sec_xbrl" not in enriched.columns:
        enriched["sec_xbrl"] = None
    if "eastmoney" not in enriched.columns:
        enriched["eastmoney"] = None
    audit_tickers = _select_audit_tickers(enriched)
    sec_started_at = time.monotonic()
    sec_available = 0
    sec_skipped = 0
    eastmoney_available = 0
    sec_errors: Dict[str, str] = {}
    eastmoney_errors: Dict[str, str] = {}

    for ticker in audit_tickers:
        row_idx = enriched.index[enriched["ticker"] == ticker]
        if row_idx.empty:
            continue
        idx = row_idx[0]
        if time.monotonic() - sec_started_at >= SEC_OFFICIAL_CHECK_TOTAL_BUDGET_SECONDS:
            sec_skipped += 1
            sec_errors[ticker] = "sec_official_check_total_budget_exhausted"
        else:
            sec_summary, sec_error = _fetch_sec_xbrl_summary(ticker, end_date=end_date)
            if sec_summary:
                sec_available += 1
                enriched.at[idx, "sec_xbrl"] = dict(sec_summary)
            elif sec_error:
                sec_errors[ticker] = sec_error

        if include_current_web_checks:
            eastmoney_summary, eastmoney_error = _fetch_eastmoney_gmain_indicator(f"{ticker}.O")
            if eastmoney_summary:
                eastmoney_available += 1
                enriched.at[idx, "eastmoney"] = dict(eastmoney_summary)
            elif eastmoney_error:
                eastmoney_errors[ticker] = eastmoney_error

    return enriched, {
        "sec_xbrl": {
            "checked": len(audit_tickers),
            "available": sec_available,
            "skipped": sec_skipped,
            "scope": "M7 plus top market-cap NDX constituents",
            "role": "official_cross_check_for_component_model",
            "allowed_claims": "official disclosed facts only; not a standalone valuation-cheapness signal",
            "errors": dict(list(sec_errors.items())[:10]),
            "total_budget_seconds": SEC_OFFICIAL_CHECK_TOTAL_BUDGET_SECONDS,
            "degraded": bool(sec_errors),
            "historical_filter": "filed_date <= effective_date" if end_date else "latest filed facts",
        },
        "eastmoney": {
            "checked": len(audit_tickers) if include_current_web_checks else 0,
            "available": eastmoney_available,
            "scope": "current web cross-check only",
            "role": "third_party_chinese_cross_check_only",
            "errors": dict(list(eastmoney_errors.items())[:10]),
            "research_candidate_only": True,
        },
    }


def _sec_official_facts_from_frame(df: pd.DataFrame) -> Dict[str, Any]:
    if df.empty or "sec_xbrl" not in df.columns:
        return {"availability": "unavailable", "facts_by_ticker": {}, "field_coverage": {}}
    facts_by_ticker: Dict[str, Any] = {}
    field_counts = {key: 0 for key in SEC_L4_METRIC_ALIASES}
    checked = 0
    for _, row in df.iterrows():
        ticker = str(row.get("ticker") or "").upper()
        sec_summary = row.get("sec_xbrl")
        if not ticker or not isinstance(sec_summary, dict):
            continue
        checked += 1
        ticker_facts = sec_summary.get("facts") if isinstance(sec_summary.get("facts"), dict) else {}
        facts_by_ticker[ticker] = {
            "cik": sec_summary.get("cik"),
            "latest_filed_date": sec_summary.get("latest_filed_date"),
            "facts": ticker_facts,
        }
        for field, fact in ticker_facts.items():
            if isinstance(fact, dict) and fact.get("availability") == "available":
                field_counts[field] = field_counts.get(field, 0) + 1
    return {
        "availability": "available" if facts_by_ticker else "unavailable",
        "role": "official_disclosed_financial_facts_primary",
        "allowed_claims": "SEC facts answer what has been filed, not whether NDX is cheap.",
        "checked_tickers": checked,
        "field_coverage": {
            field: {"available": count, "checked": checked}
            for field, count in field_counts.items()
        },
        "facts_by_ticker": facts_by_ticker,
    }


def get_ndx_component_fundamentals_snapshot(end_date: str = None) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Collect a run-local L4 component fundamentals snapshot with parallel source checks."""
    cache_key = f"l4_component_snapshot:{end_date or 'live'}"
    cached = L4_COMPONENT_SNAPSHOT_CACHE.get(cache_key)
    if cached is not None:
        cached_df, cached_stats = cached
        stats = dict(cached_stats)
        stats["cache_hit"] = True
        return cached_df.copy(), stats

    if end_date:
        effective_date = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        effective_date = datetime.now()
    ndx100_components = get_ndx100_components(end_date=end_date)
    data_list: List[Dict[str, Any]] = []
    failed_tickers: List[str] = []
    source_disagreements: List[Dict[str, Any]] = []
    source_switches: List[Dict[str, Any]] = []
    source_counts = {
        "yfinance": {"attempted": 0, "available": 0, "skipped": 0},
        "yahoo_quote_summary": {"attempted": 0, "available": 0, "skipped": 0},
    }
    live_source_started_at = time.monotonic()

    print(f"开始获取 {len(ndx100_components)} 支NDX100成分股多源L4快照...")
    for i, original_ticker in enumerate(ndx100_components):
        ticker = original_ticker
        if ticker in TICKER_REPLACEMENTS and TICKER_REPLACEMENTS[ticker] is None:
            continue

        source_errors: Dict[str, str] = {}
        yfinance_row: Dict[str, Any] = {}
        yahoo_row: Dict[str, Any] = {}

        if not end_date and YF_AVAILABLE:
            if time.monotonic() - live_source_started_at >= L4_COMPONENT_LIVE_SOURCE_TOTAL_BUDGET_SECONDS:
                source_counts["yfinance"]["skipped"] += 1
                source_errors["yfinance"] = "l4_component_live_source_total_budget_exhausted"
            else:
                source_counts["yfinance"]["attempted"] += 1
                info, info_error = _fetch_yfinance_info_best_effort(ticker)
                if (not info or not info.get("marketCap")) and ticker in TICKER_REPLACEMENTS and TICKER_REPLACEMENTS[ticker]:
                    replacement_ticker = TICKER_REPLACEMENTS[ticker]
                    replacement_info, replacement_error = _fetch_yfinance_info_best_effort(replacement_ticker)
                    if replacement_info:
                        ticker = replacement_ticker
                        info = replacement_info
                        info_error = None
                    elif replacement_error:
                        info_error = replacement_error
                if info:
                    yfinance_row = _component_row_from_yfinance(ticker, info)
                    if yfinance_row.get("market_cap"):
                        source_counts["yfinance"]["available"] += 1
                else:
                    source_errors["yfinance"] = info_error or "empty_info"
        elif end_date:
            source_errors["yfinance"] = "backtest_skipped_latest_only_source"

        if not end_date:
            if time.monotonic() - live_source_started_at >= L4_COMPONENT_LIVE_SOURCE_TOTAL_BUDGET_SECONDS:
                source_counts["yahoo_quote_summary"]["skipped"] += 1
                source_errors["yahoo_quote_summary"] = "l4_component_live_source_total_budget_exhausted"
            else:
                source_counts["yahoo_quote_summary"]["attempted"] += 1
                yahoo_payload, yahoo_error = _fetch_yahoo_quote_summary_direct(ticker)
                if yahoo_payload:
                    yahoo_row = _component_row_from_yahoo_quote_summary(ticker, yahoo_payload)
                    if yahoo_row.get("market_cap"):
                        source_counts["yahoo_quote_summary"]["available"] += 1
                elif yahoo_error:
                    source_errors["yahoo_quote_summary"] = yahoo_error
        else:
            source_errors["yahoo_quote_summary"] = "backtest_skipped_latest_only_source"

        merged = _merge_component_source_rows(ticker, yfinance_row, yahoo_row, source_errors)
        if not merged.get("market_cap") and not end_date:
            failed_tickers.append(original_ticker)
            continue
        if merged.get("component_source_disagreements"):
            source_disagreements.extend(merged["component_source_disagreements"])
        if merged.get("component_source_switches"):
            source_switches.extend({"ticker": ticker, **item} for item in merged["component_source_switches"])
        data_list.append(merged)

        if (i + 1) % 20 == 0:
            print(f"  已处理 {i + 1}/{len(ndx100_components)} 个NDX成分股")
        time.sleep(0.02)

    df = pd.DataFrame(data_list)
    if not df.empty and "market_cap" in df.columns:
        df["market_cap"] = df["market_cap"].map(_safe_float)
        total_market_cap = df["market_cap"].dropna().clip(lower=0).sum()
        if total_market_cap > 0:
            df["weight"] = df["market_cap"] / total_market_cap
            weight_by_ticker = {
                str(row.get("ticker") or "").upper(): _round_or_none((_safe_float(row.get("weight")) or 0.0) * 100.0)
                for _, row in df.iterrows()
            }
            for issue in source_disagreements:
                ticker = str(issue.get("ticker") or "").upper()
                issue["market_cap_weight_pct"] = weight_by_ticker.get(ticker)

    df, official_stats = _enrich_component_rows_with_official_checks(
        df,
        end_date=end_date,
        include_current_web_checks=not bool(end_date),
    )
    high_core_disagreements = [
        issue for issue in source_disagreements
        if issue.get("severity") == "high" and issue.get("field") in L4_CORE_COMPONENT_VALUATION_FIELDS
    ]
    component_conflict_gate = {
        "status": "degraded" if high_core_disagreements else "clean",
        "rule": "High yfinance/Yahoo disagreement in component trailing_pe or forward_pe rejects that ticker field from core component calculation.",
        "high_core_component_disagreements": high_core_disagreements[:20],
        "blocks_publish": False,
    }
    sec_official_facts = _sec_official_facts_from_frame(df)
    stats = {
        "successful": len(df),
        "total_tickers": len(ndx100_components),
        "failed": len(failed_tickers),
        "coverage": round(len(df) / len(ndx100_components), 3) if ndx100_components else 0,
        "failed_tickers": failed_tickers,
        "source_counts": source_counts,
        "official_checks": official_stats,
        "source_disagreement_issues": source_disagreements,
        "source_switches": source_switches,
        "primary_source": "field_policy",
        "primary_source_by_field": dict(L4_COMPONENT_FIELD_SOURCE_POLICY),
        "candidate_sources": ["yahoo_quote_summary", "sec_xbrl", "eastmoney"],
        "live_source_total_budget_seconds": L4_COMPONENT_LIVE_SOURCE_TOTAL_BUDGET_SECONDS,
        "component_conflict_gate": component_conflict_gate,
        "sec_official_facts": sec_official_facts,
        "data_date": effective_date.strftime("%Y-%m-%d"),
        "backtest_mode": bool(end_date),
        "cache_hit": False,
    }
    L4_COMPONENT_SNAPSHOT_CACHE[cache_key] = (df.copy(), dict(stats))
    print(
        "NDX成分股多源L4快照完成："
        f"成功{len(df)}/{len(ndx100_components)}，"
        f"yfinance={source_counts['yfinance']['available']}/{source_counts['yfinance']['attempted']}，"
        f"Yahoo={source_counts['yahoo_quote_summary']['available']}/{source_counts['yahoo_quote_summary']['attempted']}"
    )
    return df, stats


def get_ndx_components_data_yf_v5(end_date: str = None) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    V5.7版：获取NDX100成分股L4快照。
    实时模式并跑 yfinance 与 Yahoo quoteSummary；SEC/东财只做对账补充。
    回测模式跳过最新 fundamentals，只允许 SEC filed-date 合格事实作为候选。
    """
    return get_ndx_component_fundamentals_snapshot(end_date=end_date)


def get_ndx_pe_and_earnings_yield_av(end_date: str = None) -> Dict[str, Any]:
    """
    备用方案：用Alpha Vantage的QQQ数据代理NDX基本面（简化版）
    注意：此函数获取最新的基本面数据，end_date参数仅用于保持签名一致性。
    """
    alphavantage_api_key = get_alphavantage_api_key()
    if not alphavantage_api_key:
        return {
            "name": "NDX P/E and Earnings Yield",
            "value": None,
            "notes": "Alpha Vantage API Key not available"
        }

    if end_date:
        effective_date = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        effective_date = datetime.now()

    try:
        # 获取QQQ基本面数据（代理NDX）
        params = {
            "function": "OVERVIEW",
            "symbol": "QQQ",
            "apikey": alphavantage_api_key
        }
        data = safe_request(get_alphavantage_base_url(), params)
        if not data or "PERatio" not in data:
            raise Exception("No QQQ data from Alpha Vantage")

        # 提取核心指标
        pe = float(data.get("PERatio")) if data.get("PERatio") else None
        forward_pe = float(data.get("ForwardPE")) if data.get("ForwardPE") else None
        earnings_yield = (1 / forward_pe) * 100 if forward_pe and forward_pe > 0 else None

        return {
            "name": "NDX P/E and Earnings Yield (QQQ Proxy)",
            "series_id": "NDX_PROXY_QQQ",
            "value": {
                "PE": pe,
                "TrailingPE": pe,
                "ForwardPE": forward_pe,
                "EarningsYield": round(earnings_yield, 2) if earnings_yield else None,
                "FCFYield": None,  # Alpha Vantage无QQQ FCF数据
                "Coverage": {"note": "QQQ代理NDX，非完整成分股计算"}
            },
            "unit": "ratio/percent",
            "date": effective_date.strftime("%Y-%m-%d"),
            "source_tier": SOURCE_TIER_PROXY,
            "source_name": "Alpha Vantage (QQQ Proxy)",
            "data_quality": _quality_block(
                source_tier=SOURCE_TIER_PROXY,
                data_date=effective_date.strftime("%Y-%m-%d"),
                update_frequency="latest QQQ overview when Alpha Vantage updates",
                formula="QQQ proxy PE/ForwardPE; earnings yield = 1 / ForwardPE",
                coverage={"note": "QQQ proxy, not component-level NDX coverage"},
                anomalies=["FCF yield unavailable from Alpha Vantage QQQ overview"],
                fallback_chain=VALUATION_FALLBACK_CHAIN,
            ),
            "notes": "因yfinance不可用，使用QQQ数据代理NDX基本面"
        }
    except Exception as e:
        return {
            "name": "NDX P/E and Earnings Yield",
            "value": None,
            "notes": f"Alpha Vantage fallback failed: {str(e)[:50]}"
        }


DAMODARAN_CACHE_TTL_SECONDS = 86400  # 24 hours


def _damodaran_cache_dir() -> str:
    cache_dir = os.path.join(path_config.cache_dir, "damodaran")
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


def _damodaran_cache_path(url: str) -> str:
    safe_name = re.sub(r"[^a-zA-Z0-9_.-]", "_", url.rsplit("/", 1)[-1]) if "/" in url else url
    return os.path.join(_damodaran_cache_dir(), safe_name)


def _is_valid_damodaran_cache_payload(url: str, content: bytes) -> bool:
    if not content:
        return False
    lower_url = url.lower()
    if lower_url.endswith(".xlsx"):
        if not content.startswith(b"PK\x03\x04"):
            return False
        # The official Damodaran workbooks are materially larger than a stub
        # workbook. Tiny ZIP-valid files are usually synthetic test fixtures or
        # upstream placeholder/error payloads and should not poison the 24h cache.
        if "erpbymonth.xlsx" in lower_url or re.search(r"/erp[a-z]+\d{2}\.xlsx$", lower_url):
            return len(content) >= 4096
    return True


def _read_cache(path: str, url: str) -> Optional[bytes]:
    try:
        mtime = os.path.getmtime(path)
        if time.time() - mtime > DAMODARAN_CACHE_TTL_SECONDS:
            return None
        with open(path, "rb") as f:
            content = f.read()
        if not _is_valid_damodaran_cache_payload(url, content):
            try:
                os.remove(path)
            except Exception:
                pass
            return None
        return content
    except Exception:
        return None


def _write_cache(path: str, content: bytes) -> None:
    try:
        with open(path, "wb") as f:
            f.write(content)
    except Exception:
        pass


def _fetch_bytes_cached(url: str, timeout: int = 12) -> Tuple[Optional[bytes], Optional[str]]:
    cache_path = _damodaran_cache_path(url)
    cached = _read_cache(cache_path, url)
    if cached is not None:
        return cached, None
    content, error = _fetch_bytes(url, timeout=timeout)
    if content is not None and _is_valid_damodaran_cache_payload(url, content):
        _write_cache(cache_path, content)
    return content, error


def _fetch_text(url: str, timeout: int = 8) -> Tuple[Optional[str], Optional[str]]:
    try:
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; ndx-vnext/1.0)"},
            timeout=timeout,
            proxies=get_requests_proxies(),
        )
        response.raise_for_status()
        return response.text, None
    except Exception as exc:
        return None, str(exc)[:120]


def _fetch_json(url: str, timeout: int = 8, *, headers: Optional[Dict[str, str]] = None) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    try:
        request_headers = {"User-Agent": "Mozilla/5.0 (compatible; ndx-vnext/1.0)"}
        if headers:
            request_headers.update(headers)
        response = requests.get(
            url,
            headers=request_headers,
            timeout=timeout,
            proxies=get_requests_proxies(),
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            return None, "json_response_not_object"
        return payload, None
    except Exception as exc:
        return None, str(exc)[:120]


def _fetch_bytes(url: str, timeout: int = 12) -> Tuple[Optional[bytes], Optional[str]]:
    try:
        response = requests.get(
            url,
            headers={"User-Agent": "Mozilla/5.0 (compatible; ndx-vnext/1.0)"},
            timeout=timeout,
            proxies=get_requests_proxies(),
        )
        response.raise_for_status()
        return response.content, None
    except Exception as exc:
        return None, str(exc)[:120]


def _epoch_ms_to_china_date(value: Any) -> Optional[str]:
    number = _safe_float(value)
    if number is None:
        return None
    try:
        return datetime.fromtimestamp(number / 1000, tz=timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    except Exception:
        return None


def _epoch_ms_to_utc(value: Any) -> Optional[str]:
    number = _safe_float(value)
    if number is None:
        return None
    try:
        return datetime.fromtimestamp(number / 1000, tz=timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    except Exception:
        return None


def _parse_worldperatio_ndx_pe(html: str) -> Dict[str, Any]:
    text = _html_text(html)
    value = _first_number(r"P/E Ratio\s*\n\s*([0-9]+(?:\.[0-9]+)?)", text)
    data_date = _first_date(r"([0-9]{2}\s+[A-Za-z]+\s+[0-9]{4})(?:\s*\n|\s+)", text)
    percentile = _first_number(
        r"(?:Historical\s+)?(?:Percentile(?:\s+Rank)?|Rank)\s*\n\s*([0-9]+(?:\.[0-9]+)?)\s*%?",
        text,
    )
    lower_text = text.lower()
    methodology_bits = ["QQQ ETF proxy"]
    if "rolling average" in lower_text:
        methodology_bits.append("rolling average")
    if "outlier" in lower_text:
        methodology_bits.append("outlier normalization")
    if len(methodology_bits) == 1:
        methodology_bits.append("published WorldPERatio methodology text")
    unavailable_reason = None if percentile is not None else "historical percentile unavailable: source does not provide explicit percentile/rank"
    result = _valuation_source_result(
        source_id="worldperatio_pe",
        source_name="WorldPERatio",
        source_url="https://worldperatio.com/index/nasdaq-100/",
        source_tier=SOURCE_TIER_THIRD_PARTY,
        metric="ndx_trailing_pe",
        value=value,
        percentile_10y=percentile,
        data_date=data_date,
        methodology="; ".join(methodology_bits),
        unavailable_reason=unavailable_reason,
        formula="Published Nasdaq 100 PE; no historical percentile unless explicit percentile/rank is published",
    )
    relative_position = _parse_worldperatio_relative_position(text, percentile_is_explicit=percentile is not None)
    if relative_position:
        result["relative_position"] = relative_position
        result["methodology"] = f"{result['methodology']}; std-dev / z-score relative context is not percentile"
    return result


def _parse_worldperatio_relative_position(text: str, *, percentile_is_explicit: bool) -> Dict[str, Any]:
    windows: Dict[str, Dict[str, Any]] = {}
    for years in (1, 5, 10, 20):
        window_key = f"{years}y"
        row_match = re.search(
            rf"Last\s+{years}Y\s+"
            r"([-+]?[0-9]+(?:\.[0-9]+)?)\s+"
            r"([-+]?[0-9]+(?:\.[0-9]+)?)\s+"
            r"\[\s*([-+]?[0-9]+(?:\.[0-9]+)?)\s*[·\s]+"
            r"([-+]?[0-9]+(?:\.[0-9]+)?)\s*,\s*"
            r"([-+]?[0-9]+(?:\.[0-9]+)?)\s*[·\s]+"
            r"([-+]?[0-9]+(?:\.[0-9]+)?)\s*\]\s*"
            r"([-+]?[0-9]+(?:\.[0-9]+)?)\s*σ\s*"
            r"([A-Za-z][A-Za-z -]+)",
            text,
            flags=re.I | re.S,
        )
        if row_match:
            windows[window_key] = {
                "average_pe": _round_or_none(_safe_float(row_match.group(1))),
                "std_dev": _round_or_none(_safe_float(row_match.group(2))),
                "range_low": _round_or_none(_safe_float(row_match.group(4))),
                "range_high": _round_or_none(_safe_float(row_match.group(5))),
                "range_2std_low": _round_or_none(_safe_float(row_match.group(3))),
                "range_2std_high": _round_or_none(_safe_float(row_match.group(6))),
                "deviation_vs_mean_sigma": _round_or_none(_safe_float(row_match.group(7))),
                "valuation_label": row_match.group(8).strip(),
            }
            continue

        summary_match = re.search(
            rf"{years}Y\s+Average:\s*([-+]?[0-9]+(?:\.[0-9]+)?).*?"
            r"1\s+Std\s+Dev\s+range:\s*\[\s*([-+]?[0-9]+(?:\.[0-9]+)?)\s*,\s*([-+]?[0-9]+(?:\.[0-9]+)?)\s*\].*?"
            r"2\s+Std\s+Dev\s+range:\s*\[\s*([-+]?[0-9]+(?:\.[0-9]+)?)\s*,\s*([-+]?[0-9]+(?:\.[0-9]+)?)\s*\]",
            text,
            flags=re.I | re.S,
        )
        if summary_match:
            average = _safe_float(summary_match.group(1))
            range_low = _safe_float(summary_match.group(2))
            range_high = _safe_float(summary_match.group(3))
            std_dev = None
            if average is not None and range_high is not None:
                std_dev = range_high - average
            windows[window_key] = {
                "average_pe": _round_or_none(average),
                "std_dev": _round_or_none(std_dev),
                "range_low": _round_or_none(range_low),
                "range_high": _round_or_none(range_high),
                "range_2std_low": _round_or_none(_safe_float(summary_match.group(4))),
                "range_2std_high": _round_or_none(_safe_float(summary_match.group(5))),
                "deviation_vs_mean_sigma": None,
                "valuation_label": None,
            }
            continue

        block_match = re.search(
            rf"{years}\s+Year.*?(?=\n\s*(?:1|5|10|20)\s+Year|\n\s*(?:50|200)\s+Day|$)",
            text,
            flags=re.I | re.S,
        )
        if not block_match:
            continue
        block = block_match.group(0)
        average_pe = _first_number(r"Average\s+PE\s*:?\s*\n?\s*([0-9]+(?:\.[0-9]+)?)", block)
        std_dev = _first_number(r"(?:Standard\s+Deviation|Std\.?\s*Dev\.?)\s*:?\s*\n?\s*([0-9]+(?:\.[0-9]+)?)", block)
        range_match = re.search(
            r"(?:Fair\s+Value\s+Range|Range)\s*:?\s*\n?\s*([0-9]+(?:\.[0-9]+)?)\s*[-–]\s*([0-9]+(?:\.[0-9]+)?)",
            block,
            flags=re.I,
        )
        deviation = _first_number(r"Deviation\s+from\s+mean\s*:?\s*\n?\s*([-+]?[0-9]+(?:\.[0-9]+)?)\s*(?:sigma|σ)?", block)
        label = _first_date(r"Valuation\s*:?\s*\n?\s*([A-Za-z][A-Za-z\s-]+?)(?:\n|$)", block)
        if not any(value is not None for value in (average_pe, std_dev, deviation)) and not range_match and not label:
            continue
        windows[window_key] = {
            "average_pe": _round_or_none(average_pe),
            "std_dev": _round_or_none(std_dev),
            "range_low": _round_or_none(_safe_float(range_match.group(1)) if range_match else None),
            "range_high": _round_or_none(_safe_float(range_match.group(2)) if range_match else None),
            "deviation_vs_mean_sigma": _round_or_none(deviation),
            "valuation_label": label.strip() if label else None,
        }

    trend_context = {
        "sma50_margin_pct": _round_or_none(_first_number(r"50\s+Day\s+SMA\s+margin\s*:?\s*\n?\s*([-+]?[0-9]+(?:\.[0-9]+)?)\s*%?", text)),
        "sma200_margin_pct": _round_or_none(_first_number(r"200\s+Day\s+SMA\s+margin\s*:?\s*\n?\s*([-+]?[0-9]+(?:\.[0-9]+)?)\s*%?", text)),
    }
    trend_context = {key: value for key, value in trend_context.items() if value is not None}

    if not windows and not trend_context:
        return {}
    return {
        "position_type": "std_dev_context_not_percentile",
        "percentile_is_explicit": percentile_is_explicit,
        "valuation_windows": windows,
        "trend_context": trend_context,
        "interpretation_boundary": "WorldPERatio rolling averages/std-dev labels describe relative position but are not historical percentile/rank.",
    }


def _trendonify_sidecar_default_path() -> Path:
    return Path(path_config.output_dir) / "browser_sidecar" / "trendonify_ndx_valuation.json"


def _trusted_trendonify_sidecar_sources(path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Load user-trusted Trendonify browser sidecar values for L4 cross-checks.

    Direct HTTP requests to Trendonify often return 403. The browser sidecar is
    intentionally explicit and opt-in, but once the user marked it trusted it
    should be visible in ThirdPartyChecks rather than stranded in output/.
    """
    sidecar_path = Path(path) if path else _trendonify_sidecar_default_path()
    if not sidecar_path.exists():
        return []
    try:
        payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    if payload.get("source") != "trendonify_ndx_valuation":
        return []

    sources: List[Dict[str, Any]] = []
    for page in payload.get("pages", []):
        if not isinstance(page, dict) or not page.get("user_trusted"):
            continue
        parsed = page.get("parsed")
        if not isinstance(parsed, dict):
            continue
        if parsed.get("availability") != "available" and parsed.get("value") is None:
            continue
        item = dict(parsed)
        item["source_tier"] = SOURCE_TIER_THIRD_PARTY
        item["browser_sidecar"] = {
            "path": str(sidecar_path),
            "page_type": page.get("page_type"),
            "collected_at_utc": page.get("collected_at_utc") or payload.get("generated_at_utc"),
            "user_trusted": True,
            "collection_method": "bb-browser",
        }
        if page.get("preserved_after_failed_refresh_at_utc"):
            item["browser_sidecar"]["preserved_after_failed_refresh_at_utc"] = page.get("preserved_after_failed_refresh_at_utc")
        if page.get("latest_failed_refresh"):
            item["browser_sidecar"]["latest_failed_refresh"] = page.get("latest_failed_refresh")
        item["methodology"] = f"{item.get('methodology', '')}; user-trusted bb-browser sidecar".strip("; ")
        item["availability"] = "available"
        sources.append(item)
    return sources


def _parse_trendonify_ndx_pe(html: str, *, forward: bool = False) -> Dict[str, Any]:
    text = _html_text(html)
    title = "Nasdaq 100 Forward PE Ratio" if forward else "Nasdaq 100 PE Ratio"
    metric = "ndx_forward_pe" if forward else "ndx_trailing_pe"
    value = _first_number(rf"{re.escape(title)}\s*\n\s*([0-9]+(?:\.[0-9]+)?)", text)
    if value is None:
        value = _trendonify_value_after_label(
            text,
            ["Nasdaq 100 Forward PE Ratio", "Forward PE Ratio"] if forward else ["Nasdaq 100 PE Ratio", "PE Ratio"],
        )
    data_date = _first_date(r"Last Updated:\s*([A-Za-z]+\s+[0-9]{2},\s+[0-9]{4})", text)
    percentile = _first_number(r"Valuation\s+Percentile\s+Rank\s*([0-9]+(?:\.[0-9]+)?)\s*%?", text)
    historical_percentiles = _parse_trendonify_historical_percentiles(text)
    if percentile is None:
        percentile = historical_percentiles.get("10y", {}).get("percentile")
    url = (
        "https://trendonify.com/united-states/stock-market/nasdaq-100/forward-pe-ratio"
        if forward
        else "https://trendonify.com/united-states/stock-market/nasdaq-100/pe-ratio"
    )
    result = _valuation_source_result(
        source_id="trendonify_forward_pe" if forward else "trendonify_pe",
        source_name="Trendonify",
        source_url=url,
        source_tier=SOURCE_TIER_THIRD_PARTY,
        metric=metric,
        value=value,
        percentile_10y=percentile,
        data_date=data_date,
        methodology="QQQ-derived third-party estimate with explicit valuation percentile rank when available",
        formula=f"Published {title}; percentile only from explicit Valuation Percentile Rank",
    )
    if historical_percentiles:
        result["historical_percentiles"] = historical_percentiles
        result["percentile_1y"] = historical_percentiles.get("1y", {}).get("percentile")
        result["percentile_5y"] = historical_percentiles.get("5y", {}).get("percentile")
        result["percentile_20y"] = historical_percentiles.get("20y", {}).get("percentile")
        result["percentile_since_inception"] = historical_percentiles.get("since_inception", {}).get("percentile")
        result["methodology"] = (
            f"{result['methodology']}; historical comparison table includes "
            "1Y/5Y/10Y/20Y/since-inception percentiles when published"
        )
    return result


def _trendonify_value_after_label(text: str, labels: List[str]) -> Optional[float]:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    normalized_labels = {label.lower() for label in labels}
    numeric_pattern = re.compile(r"^([0-9]+(?:\.[0-9]+)?)$")
    for idx, line in enumerate(lines):
        if line.lower() not in normalized_labels:
            continue
        for candidate in lines[idx + 1 : idx + 5]:
            match = numeric_pattern.match(candidate.replace(",", ""))
            if match:
                return _safe_float(match.group(1))
    return None


def _parse_trendonify_historical_percentiles(text: str) -> Dict[str, Dict[str, Any]]:
    """Extract Trendonify's published comparison-table percentiles without inferring missing values."""
    period_keys = {
        "1 year": "1y",
        "1 years": "1y",
        "5 year": "5y",
        "5 years": "5y",
        "10 year": "10y",
        "10 years": "10y",
        "20 year": "20y",
        "20 years": "20y",
    }
    percentiles: Dict[str, Dict[str, Any]] = {}
    row_pattern = re.compile(
        r"(?im)^\s*(1\s+Years?|5\s+Years?|10\s+Years?|20\s+Years?|Since\s+[A-Za-z]+\s+[0-9]{4})"
        r"\s+([0-9]+(?:\.[0-9]+)?)"
        r"\s+([0-9]+(?:\.[0-9]+)?)"
        r"\s*%?\s+([A-Za-z][A-Za-z -]*)(?:\s*$|\n)",
    )
    for match in row_pattern.finditer(text):
        label = re.sub(r"\s+", " ", match.group(1).strip()).lower()
        key = "since_inception" if label.startswith("since ") else period_keys.get(label)
        if not key:
            continue
        percentiles[key] = {
            "period": match.group(1).strip(),
            "median_pe": _round_or_none(_safe_float(match.group(2))),
            "percentile": _round_or_none(_safe_float(match.group(3))),
            "valuation": match.group(4).strip(),
        }
    return percentiles


DANJUAN_NDX_VALUATION_URL = "https://danjuanfunds.com/djapi/index_eva/detail/NDX"
DANJUAN_NDX_VALUATION_REFERER = "https://danjuanfunds.com/dj-valuation-table-detail/NDX"


def _parse_danjuan_ndx_valuation(payload: Dict[str, Any]) -> Dict[str, Any]:
    data = payload.get("data") if isinstance(payload, dict) else None
    if not isinstance(data, dict):
        raise ValueError("Danjuan response missing data object")

    pe_percentile = _percent_or_none(data.get("pe_percentile"))
    pb_percentile = _percent_or_none(data.get("pb_percentile"))
    data_date = _epoch_ms_to_china_date(data.get("ts")) or data.get("date")
    sample_start = _epoch_ms_to_china_date(data.get("begin_at"))
    updated_at = _epoch_ms_to_utc(data.get("updated_at"))
    result = _valuation_source_result(
        source_id="danjuan_ndx_valuation",
        source_name="DanjuanFunds",
        source_url=DANJUAN_NDX_VALUATION_URL,
        source_tier=SOURCE_TIER_THIRD_PARTY,
        metric="ndx_trailing_pe",
        value=_safe_float(data.get("pe")),
        percentile_10y=pe_percentile,
        data_date=data_date,
        methodology=(
            "DanjuanFunds index valuation detail/NDX JSON; PE/PB percentiles are published ratios "
            "converted from 0-1 scale to 0-100 scale; used as third-party validation, not the Manual/Wind primary value"
        ),
        formula="Published NDX PE/PB/ROE/PEG/eva_type with PE percentile from pe_percentile * 100",
        coverage={"index_code": data.get("index_code"), "index_name": data.get("name"), "sample_start": sample_start},
    )
    result.update(
        {
            "pb": _round_or_none(_safe_float(data.get("pb"))),
            "pe_percentile_raw": _round_or_none(_safe_float(data.get("pe_percentile")), 4),
            "pb_percentile": pb_percentile,
            "pb_percentile_raw": _round_or_none(_safe_float(data.get("pb_percentile")), 4),
            "roe": _round_or_none(_safe_float(data.get("roe")), 4),
            "peg": _round_or_none(_safe_float(data.get("peg")), 4),
            "eva_type": data.get("eva_type"),
            "eva_type_int": data.get("eva_type_int"),
            "date": data.get("date"),
            "sample_start": sample_start,
            "begin_at": sample_start,
            "updated_at": updated_at,
            "updated_at_utc": updated_at,
            "source_url": DANJUAN_NDX_VALUATION_URL,
        }
    )
    return result


def get_ndx_valuation_third_party_checks() -> List[Dict[str, Any]]:
    """读取第三方NDX估值页面，作为校验源，不作为主估值源。"""
    checks: List[Dict[str, Any]] = []
    sources = [
        ("worldperatio_pe", "https://worldperatio.com/index/nasdaq-100/", _parse_worldperatio_ndx_pe),
        (
            "trendonify_pe",
            "https://trendonify.com/united-states/stock-market/nasdaq-100/pe-ratio",
            lambda html: _parse_trendonify_ndx_pe(html, forward=False),
        ),
        (
            "trendonify_forward_pe",
            "https://trendonify.com/united-states/stock-market/nasdaq-100/forward-pe-ratio",
            lambda html: _parse_trendonify_ndx_pe(html, forward=True),
        ),
    ]
    for source_id, url, parser in sources:
        html, error = _fetch_text(url)
        if error or not html:
            checks.append(
                _unavailable_valuation_source(
                    source_id=source_id,
                    source_name="Trendonify" if source_id.startswith("trendonify") else "WorldPERatio",
                    source_url=url,
                    metric="ndx_forward_pe" if source_id.endswith("forward_pe") else "ndx_trailing_pe",
                    reason=error or "empty_response",
                )
            )
            continue
        try:
            parsed = parser(html)
            checks.append(parsed)
        except Exception as exc:
            checks.append(
                _unavailable_valuation_source(
                    source_id=source_id,
                    source_name="Trendonify" if source_id.startswith("trendonify") else "WorldPERatio",
                    source_url=url,
                    metric="ndx_forward_pe" if source_id.endswith("forward_pe") else "ndx_trailing_pe",
                    reason=str(exc)[:120],
                )
            )
    payload, error = _fetch_json(
        DANJUAN_NDX_VALUATION_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": DANJUAN_NDX_VALUATION_REFERER,
        },
    )
    if error or not payload:
        checks.append(
            _unavailable_valuation_source(
                source_id="danjuan_ndx_valuation",
                source_name="DanjuanFunds",
                source_url=DANJUAN_NDX_VALUATION_URL,
                metric="ndx_trailing_pe",
                reason=error or "empty_response",
                methodology="DanjuanFunds detail/NDX JSON requires browser User-Agent and valuation detail Referer",
            )
        )
    else:
        try:
            checks.append(_parse_danjuan_ndx_valuation(payload))
        except Exception as exc:
            checks.append(
                _unavailable_valuation_source(
                    source_id="danjuan_ndx_valuation",
                    source_name="DanjuanFunds",
                    source_url=DANJUAN_NDX_VALUATION_URL,
                    metric="ndx_trailing_pe",
                    reason=str(exc)[:120],
                    methodology="DanjuanFunds detail/NDX JSON requires browser User-Agent and valuation detail Referer",
                )
            )
    sidecar_sources = _trusted_trendonify_sidecar_sources()
    if sidecar_sources:
        by_id = {item.get("source_id"): item for item in checks if isinstance(item, dict)}
        for item in sidecar_sources:
            by_id[item.get("source_id")] = item
        ordered_ids = [source_id for source_id, _, _ in sources] + ["danjuan_ndx_valuation"]
        checks = [by_id[source_id] for source_id in ordered_ids if source_id in by_id]
        checks.extend(item for key, item in by_id.items() if key not in set(ordered_ids))
    return checks


def _damodaran_table_candidates(table: pd.DataFrame) -> List[pd.DataFrame]:
    candidates = [table]
    for idx, row in table.iterrows():
        values = [str(value).strip().lower() for value in row.tolist()]
        if "year" not in values:
            continue
        promoted = table.iloc[idx + 1 :].copy()
        promoted.columns = [str(value).strip() for value in row.tolist()]
        candidates.append(promoted)
        break
    return candidates


def _parse_damodaran_implied_erp_tables(tables: List[pd.DataFrame]) -> Dict[str, Any]:
    for raw_table in tables:
        for table in _damodaran_table_candidates(raw_table):
            parsed = _parse_damodaran_implied_erp_table(table)
            if parsed:
                return parsed
    raise ValueError("No Damodaran implied ERP table found")


def _parse_damodaran_implied_erp_table(table: pd.DataFrame) -> Optional[Dict[str, Any]]:
    normalized_columns = [str(col).strip() for col in table.columns]
    lower_columns = [col.lower() for col in normalized_columns]
    year_col = next((col for col, lower in zip(normalized_columns, lower_columns) if lower == "year"), None)
    fcfe_col = next(
        (
            col
            for col, lower in zip(normalized_columns, lower_columns)
            if "implied" in lower and "fcfe" in lower
        ),
        None,
    )
    ddm_col = next(
        (
            col
            for col, lower in zip(normalized_columns, lower_columns)
            if "implied" in lower and "ddm" in lower
        ),
        None,
    )
    bond_col = next((col for col, lower in zip(normalized_columns, lower_columns) if "t.bond" in lower), None)
    if not year_col or not (fcfe_col or ddm_col):
        return None
    table = table.copy()
    table["_year"] = table[year_col].map(_safe_float)
    table = table.dropna(subset=["_year"]).sort_values("_year")
    if table.empty:
        return None
    latest = table.iloc[-1]

    def percent_value(column: Optional[str]) -> Optional[float]:
        if not column:
            return None
        value = _safe_float(latest.get(column))
        if value is not None and abs(value) <= 1:
            value *= 100
        return _round_or_none(value)

    result = {
        "year": int(latest["_year"]),
        "implied_premium_fcfe": percent_value(fcfe_col),
        "implied_premium_ddm": percent_value(ddm_col),
        "t_bond_rate": percent_value(bond_col),
    }
    result["implied_erp_fcfe"] = result["implied_premium_fcfe"]
    result["implied_erp_ddm"] = result["implied_premium_ddm"]
    result["tbond_rate"] = result["t_bond_rate"]
    if result["implied_premium_fcfe"] is not None or result["implied_premium_ddm"] is not None:
        return result
    return None


def _parse_damodaran_implied_erp_html(html: str) -> Dict[str, Any]:
    tables = pd.read_html(StringIO(html))
    return _parse_damodaran_implied_erp_tables(tables)


def _format_damodaran_date(value: Any, *, date1904: bool = False) -> Optional[str]:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    serial_date = _excel_serial_to_date(value, date1904=date1904)
    if serial_date:
        return serial_date
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.strftime("%Y-%m-%d")


def _parse_damodaran_monthly_erp_excel(content: bytes, *, target_date: Optional[str] = None) -> Dict[str, Any]:
    """Parse Damodaran ERPbymonth.xlsx for the latest monthly current ERP row."""
    tables = _read_excel_tables(content)
    for table in tables:
        if table.empty:
            continue
        date_col = _find_column(table.columns, "date")
        if not date_col:
            date_col = _find_column(table.columns, "start", any_needles=("month",))
        if not date_col:
            continue
        latest = _latest_row_by_date(table, date_col, max_date=target_date)
        if latest is None:
            continue

        columns = list(table.columns)
        sp500_col = _find_column(columns, "s&p")
        tbond_col = _find_column(columns, "t.bond")
        if not tbond_col:
            tbond_col = _find_column(columns, "treasury")
        riskfree_col = _find_column(columns, "riskfree")
        sustainable_col = _find_column(columns, "erp", any_needles=("sustainable", "adjusted payout"))
        cash_yield_col = next(
            (
                col
                for col in columns
                if "erp" in _normalize_label(col)
                and "t12" in _normalize_label(col).replace(" ", "")
                and "sustainable" not in _normalize_label(col)
                and "net" not in _normalize_label(col)
            ),
            None,
        )
        smoothed_col = _find_column(columns, "erp", any_needles=("smoothed", "average cf", "average"))
        normalized_col = _find_column(columns, "erp", any_needles=("normalized",))
        net_cash_col = _find_column(columns, "erp", any_needles=("net cash",))
        expected_return_col = _find_column(columns, "expected", "return")

        result = {
            "data_date": latest.get("_date_key") or _format_damodaran_date(latest.get(date_col), date1904=bool(table.attrs.get("date1904"))),
            "sp500_level": _round_or_none(_safe_float(latest.get(sp500_col))) if sp500_col else None,
            "us_10y_treasury_rate": _percent_or_none(latest.get(tbond_col)) if tbond_col else None,
            "adjusted_riskfree_rate": _percent_or_none(latest.get(riskfree_col)) if riskfree_col else None,
            "erp_t12m_adjusted_payout": _percent_or_none(latest.get(sustainable_col)) if sustainable_col else None,
            "erp_t12m_cash_yield": _percent_or_none(latest.get(cash_yield_col)) if cash_yield_col else None,
            "erp_avg_cf_yield_10y": _percent_or_none(latest.get(smoothed_col)) if smoothed_col else None,
            "erp_normalized_earnings_payout": _percent_or_none(latest.get(normalized_col)) if normalized_col else None,
            "erp_net_cash_yield": _percent_or_none(latest.get(net_cash_col)) if net_cash_col else None,
            "expected_return": _percent_or_none(latest.get(expected_return_col)) if expected_return_col else None,
            "source_file": "ERPbymonth.xlsx",
        }
        series_frame = table.copy()
        if "_date_key" not in series_frame.columns:
            series_frame["_date_key"] = series_frame[date_col].apply(
                lambda value: _format_damodaran_date(value, date1904=bool(table.attrs.get("date1904")))
            )
        series_frame = series_frame.dropna(subset=["_date_key"])
        if target_date:
            series_frame = series_frame[series_frame["_date_key"] <= target_date]
        series_frame = series_frame.tail(120)
        monthly_series = []
        for _, row in series_frame.iterrows():
            monthly_series.append(
                {
                    "data_date": str(row.get("_date_key")),
                    "sp500_level": _round_or_none(_safe_float(row.get(sp500_col))) if sp500_col else None,
                    "us_10y_treasury_rate": _percent_or_none(row.get(tbond_col)) if tbond_col else None,
                    "adjusted_riskfree_rate": _percent_or_none(row.get(riskfree_col)) if riskfree_col else None,
                    "erp_t12m_adjusted_payout": _percent_or_none(row.get(sustainable_col)) if sustainable_col else None,
                    "erp_t12m_cash_yield": _percent_or_none(row.get(cash_yield_col)) if cash_yield_col else None,
                    "erp_avg_cf_yield_10y": _percent_or_none(row.get(smoothed_col)) if smoothed_col else None,
                    "erp_normalized_earnings_payout": _percent_or_none(row.get(normalized_col)) if normalized_col else None,
                    "erp_net_cash_yield": _percent_or_none(row.get(net_cash_col)) if net_cash_col else None,
                    "expected_return": _percent_or_none(row.get(expected_return_col)) if expected_return_col else None,
                }
            )
        result["monthly_series"] = monthly_series
        percentiles = _damodaran_erp_percentile_block(
            monthly_series,
            current_value=result.get("erp_t12m_adjusted_payout"),
            current_date=result.get("data_date"),
            source_file="ERPbymonth.xlsx",
        )
        result["damodaran_erp_historical_percentiles"] = percentiles
        result["damodaran_erp_percentile_5y"] = percentiles["windows"]["5y"].get("percentile")
        result["damodaran_erp_percentile_10y"] = percentiles["windows"]["10y"].get("percentile")
        if result["us_10y_treasury_rate"] is not None and result["adjusted_riskfree_rate"] is not None:
            result["default_spread"] = _round_or_none(result["us_10y_treasury_rate"] - result["adjusted_riskfree_rate"])
        else:
            result["default_spread"] = None
        if result["data_date"] and any(value is not None for key, value in result.items() if key.startswith("erp_")):
            return result
    raise ValueError("No monthly Damodaran ERP row found")


def _damodaran_erp_percentile_block(
    monthly_series: List[Dict[str, Any]],
    *,
    current_value: Optional[float],
    current_date: Optional[str],
    source_file: str,
) -> Dict[str, Any]:
    """Calculate Damodaran ERP percentiles from the already date-bounded monthly series."""
    rows = [
        row
        for row in monthly_series
        if isinstance(row, dict)
        and row.get("data_date")
        and _safe_float(row.get("erp_t12m_adjusted_payout")) is not None
    ]
    rows = sorted(rows, key=lambda row: str(row.get("data_date")))
    data_cutoff = str(current_date or (rows[-1].get("data_date") if rows else ""))
    block = {
        "metric": "Damodaran US implied ERP historical percentile",
        "scope": "US equity market reference, not NDX PE/PB/Forward PE historical percentile",
        "primary_field": "erp_t12m_adjusted_payout",
        "method": "count(values <= current_value) / sample_count * 100",
        "data_cutoff_date": data_cutoff or None,
        "source_file": source_file,
        "windows": {},
    }

    for label, required_months in (("5y", 60), ("10y", 120)):
        window_rows = rows[-required_months:]
        sample_count = len(window_rows)
        values = [_safe_float(row.get("erp_t12m_adjusted_payout")) for row in window_rows]
        clean_values = [value for value in values if value is not None]
        percentile = None
        status = "available"
        reason = ""
        if current_value is None:
            status = "unavailable"
            reason = "current ERP value unavailable"
        elif sample_count < required_months:
            status = "insufficient_history"
            reason = f"requires at least {required_months} monthly observations"
        elif len(clean_values) < required_months:
            status = "insufficient_history"
            reason = f"requires at least {required_months} non-null monthly ERP observations"
        else:
            percentile = round(sum(1 for value in clean_values if value <= current_value) / len(clean_values) * 100.0, 1)
        block["windows"][label] = {
            "current_value": current_value,
            "percentile": percentile,
            "status": status,
            "sample_count": len(clean_values),
            "required_min_months": required_months,
            "window_start": str(window_rows[0].get("data_date")) if window_rows else None,
            "window_end": str(window_rows[-1].get("data_date")) if window_rows else None,
            "data_cutoff_date": data_cutoff or None,
            "source_file": source_file,
            "reason": reason,
        }
    return block


def _damodaran_erp_percentile_unavailable_block(*, data_cutoff_date: Optional[str], source_file: Optional[str]) -> Dict[str, Any]:
    block = {
        "metric": "Damodaran US implied ERP historical percentile",
        "scope": "US equity market reference, not NDX PE/PB/Forward PE historical percentile",
        "primary_field": "erp_t12m_adjusted_payout",
        "method": "count(values <= current_value) / sample_count * 100",
        "data_cutoff_date": data_cutoff_date,
        "source_file": source_file,
        "windows": {},
    }
    for label, required_months in (("5y", 60), ("10y", 120)):
        block["windows"][label] = {
            "current_value": None,
            "percentile": None,
            "status": "unavailable",
            "sample_count": 0,
            "required_min_months": required_months,
            "window_start": None,
            "window_end": None,
            "data_cutoff_date": data_cutoff_date,
            "source_file": source_file,
            "reason": "Damodaran monthly ERPbymonth.xlsx series unavailable; annual fallback cannot support monthly percentile",
        }
    return block


def _parse_damodaran_current_erp_calculator_excel(content: bytes, *, source_file: str) -> Dict[str, Any]:
    """Parse the current monthly Damodaran ERP calculator workbook for current assumptions."""
    tables = _read_excel_tables(content)
    observations: List[Tuple[str, Any]] = []
    for table in tables:
        for _, row in table.iterrows():
            cells = [cell for cell in row.tolist() if str(cell).strip()]
            if len(cells) < 2:
                continue
            for idx, cell in enumerate(cells):
                label = _normalize_label(cell)
                if not label or _safe_float(cell) is not None:
                    continue
                value = next((_safe_float(candidate) for candidate in cells[idx + 1 :] if _safe_float(candidate) is not None), None)
                if value is not None:
                    observations.append((label, value))

    def find_value(*needles: str, any_needles: Iterable[str] = ()) -> Optional[float]:
        any_needles_l = tuple(item.lower() for item in any_needles)
        for label, value in observations:
            if all(needle.lower() in label for needle in needles) and (
                not any_needles_l or any(needle in label for needle in any_needles_l)
            ):
                return value
        return None

    treasury = find_value("treasury", any_needles=("10-year", "10 year", "t.bond"))
    default_spread = find_value("default", "spread")
    adjusted_riskfree = find_value("riskfree", any_needles=("adjusted", "$"))
    expected_return = find_value("expected", "return")
    erp_tbond = find_value("implied", any_needles=("premium", "erp"))

    result = {
        "source_file": source_file,
        "us_10y_treasury_rate": _percent_or_none(treasury),
        "default_spread": _percent_or_none(default_spread),
        "adjusted_riskfree_rate": _percent_or_none(adjusted_riskfree),
        "expected_return": _percent_or_none(expected_return),
        "erp_net_cash_yield": _percent_or_none(erp_tbond),
    }
    if not any(value is not None for key, value in result.items() if key != "source_file"):
        raise ValueError("No current Damodaran ERP calculator assumptions found")
    return result


def _parse_damodaran_implied_erp_excel(content: bytes) -> Dict[str, Any]:
    """Parse Damodaran histimpl.xls bytes, falling back to HTML-table xls payloads."""
    errors: List[str] = []
    try:
        return _parse_damodaran_implied_erp_tables(_read_excel_tables(content))
    except Exception as exc:
        errors.append(str(exc)[:120])

    for encoding in ("utf-8", "latin1"):
        try:
            html = content.decode(encoding, errors="ignore")
            tables = pd.read_html(StringIO(html))
            parsed = _parse_damodaran_implied_erp_tables(tables)
            parsed["excel_parse_fallback"] = "html_table"
            return parsed
        except Exception as exc:
            errors.append(str(exc)[:120])

    raise ValueError("; ".join(error for error in errors if error) or "No Damodaran implied ERP Excel table found")


def get_damodaran_us_implied_erp(end_date: str = None) -> Dict[str, Any]:
    """Damodaran US implied ERP reference anchor; not an NDX-specific valuation metric."""
    date_str = end_date or datetime.now().strftime("%Y-%m-%d")
    html_url = "https://pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/implpr.html"
    annual_download_url = "http://www.stern.nyu.edu/~adamodar/pc/datasets/histimpl.xls"
    monthly_url = "https://pages.stern.nyu.edu/~adamodar/pc/implprem/ERPbymonth.xlsx"
    try:
        current_dt = datetime.strptime(date_str, "%Y-%m-%d")
    except Exception:
        current_dt = datetime.now()
    current_source_file = f"ERP{current_dt.strftime('%B')}{current_dt.strftime('%y')}.xlsx"
    current_url = f"https://pages.stern.nyu.edu/~adamodar/pc/implprem/{current_source_file}"
    parsed: Optional[Dict[str, Any]] = None
    retrieval_method = ""
    errors: List[str] = []

    content, monthly_error = _fetch_bytes_cached(monthly_url)
    if content:
        try:
            parsed = _parse_damodaran_monthly_erp_excel(content, target_date=date_str)
            retrieval_method = "monthly_excel"
            current_content, current_error = _fetch_bytes_cached(current_url)
            if current_content:
                try:
                    current_parsed = _parse_damodaran_current_erp_calculator_excel(
                        current_content,
                        source_file=current_source_file,
                    )
                    parsed["current_calculator_source_file"] = current_source_file
                    parsed["current_calculator_url"] = current_url
                    for key in ("default_spread", "expected_return"):
                        if current_parsed.get(key) is not None:
                            parsed[key] = current_parsed[key]
                except Exception as exc:
                    parsed["current_calculator_error"] = str(exc)[:120]
            elif current_error:
                parsed["current_calculator_error"] = current_error
        except Exception as exc:
            errors.append(f"monthly_excel_parse_failed: {str(exc)[:120]}")
    else:
        errors.append(f"monthly_excel_fetch_failed: {monthly_error or 'empty_response'}")

    if parsed is None:
        annual_content, annual_excel_error = _fetch_bytes(annual_download_url)
    else:
        annual_content, annual_excel_error = None, None

    if parsed is None and annual_content:
        try:
            parsed = _parse_damodaran_implied_erp_excel(annual_content)
            parsed["source_file"] = "histimpl.xls"
            retrieval_method = "annual_excel_fallback"
        except Exception as exc:
            errors.append(f"annual_excel_parse_failed: {str(exc)[:120]}")
    elif parsed is None:
        errors.append(f"annual_excel_fetch_failed: {annual_excel_error or 'empty_response'}")

    if parsed is None:
        html, html_error = _fetch_text(html_url)
        if html:
            try:
                parsed = _parse_damodaran_implied_erp_html(html)
                parsed["source_file"] = "implpr.html"
                retrieval_method = "annual_html_fallback"
            except Exception as exc:
                errors.append(f"html_parse_failed: {str(exc)[:120]}")
        else:
            errors.append(f"html_fetch_failed: {html_error or 'empty_response'}")

    if parsed is None:
        unavailable_reason = "; ".join(errors)
        return {
            "name": "Damodaran US Implied ERP Reference",
            "series_id": "DAMODARAN_US_IMPLIED_ERP",
            "value": None,
            "unit": "percent",
            "source_tier": SOURCE_TIER_UNAVAILABLE,
            "source_name": "Damodaran",
            "source_url": monthly_url,
            "download_url": monthly_url,
            "availability": "unavailable",
            "unavailable_reason": unavailable_reason,
            "error": unavailable_reason,
            "data_quality": _quality_block(
                source_tier=SOURCE_TIER_UNAVAILABLE,
                data_date=date_str,
                update_frequency="Damodaran dataset/page update cadence",
                formula="Damodaran implied ERP model for US market; unavailable this run",
                fallback_chain=[SOURCE_TIER_OFFICIAL, SOURCE_TIER_UNAVAILABLE],
            ),
        }

    data_date_out = str(parsed.get("data_date") or parsed.get("year") or date_str)
    if retrieval_method != "monthly_excel":
        parsed["damodaran_erp_historical_percentiles"] = _damodaran_erp_percentile_unavailable_block(
            data_cutoff_date=data_date_out,
            source_file=parsed.get("source_file"),
        )
        parsed["damodaran_erp_percentile_5y"] = None
        parsed["damodaran_erp_percentile_10y"] = None

    value = {
        **parsed,
        "scope": "US equity market reference, not NDX-specific",
        "download_url": monthly_url if retrieval_method == "monthly_excel" else annual_download_url,
        "retrieval_method": retrieval_method,
    }
    return {
        "name": "Damodaran US Implied ERP Reference",
        "series_id": "DAMODARAN_US_IMPLIED_ERP",
        "value": value,
        "unit": "percent",
        "date": data_date_out,
        "source_tier": SOURCE_TIER_OFFICIAL,
        "source_name": "Damodaran",
        "source_url": monthly_url if retrieval_method == "monthly_excel" else (annual_download_url if retrieval_method == "annual_excel_fallback" else html_url),
        "download_url": monthly_url if retrieval_method == "monthly_excel" else annual_download_url,
        "availability": "available",
        "notes": "美国市场 implied ERP 参考锚，不替代 NDX 自身估值或简式收益差距。",
        "data_quality": _quality_block(
            source_tier=SOURCE_TIER_OFFICIAL,
            data_date=data_date_out,
            update_frequency="monthly current ERP when ERPbymonth.xlsx is available; annual history fallback otherwise",
            formula="Damodaran US implied ERP model; monthly current ERP preferred, histimpl.xls annual history only as fallback",
            coverage={"scope": "US market/S&P 500 reference"},
            fallback_chain=[SOURCE_TIER_OFFICIAL, SOURCE_TIER_UNAVAILABLE],
        ),
    }


def get_ndx_pe_and_earnings_yield(end_date: str = None) -> Dict[str, Any]:
    """获取NDX100的P/E、盈利收益率与FCF收益率（V5.6修复版）"""
    if end_date:
        effective_date = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        effective_date = datetime.now()

    # 优先使用yfinance完整成分股计算
    if YF_AVAILABLE:
        try:
            df, stats = get_ndx_components_data_yf_v5(end_date=end_date)
            if df.empty:
                raise Exception(f"无有效NDX成分股数据：{stats.get('error', 'Unknown')}")

            # 计算加权指标
            metrics = calculate_weighted_metrics(df)
            if not metrics:
                raise Exception("无法计算加权指标（数据不足）")

            coverage_pct = stats['coverage'] * 100
            third_party_checks = get_ndx_valuation_third_party_checks()
            valuation_audit = audit_component_valuation_metrics(metrics, third_party_checks)
            rejected_metrics = valuation_audit.get("rejected_metrics", {})
            source_disagreement = {
                "component_model": {
                    "metric": "ndx_component_model_current_values",
                    "PE": metrics.get("weighted_trailing_pe"),
                    "ForwardPE": metrics.get("weighted_forward_pe"),
                    "FCFYield": metrics.get("weighted_fcf_yield"),
                    "PriceToBook": metrics.get("weighted_price_to_book"),
                    "source_tier": SOURCE_TIER_COMPONENT_MODEL,
                    "historical_percentile": None,
                    "note": "current component aggregate only; not a historical valuation percentile anchor",
                    "source_counts": stats.get("source_counts", {}),
                    "source_switches": stats.get("source_switches", [])[:20],
                    "component_source_disagreements": stats.get("source_disagreement_issues", [])[:20],
                },
                **{
                item.get("source_id") or item.get("source"): {
                    "metric": item.get("metric"),
                    "value": item.get("value"),
                    "data_date": item.get("data_date"),
                    "percentile_10y": item.get("percentile_10y"),
                    "historical_percentile": item.get("historical_percentile"),
                    "pb": item.get("pb"),
                    "pb_percentile": item.get("pb_percentile"),
                    "source_tier": item.get("source_tier"),
                    "availability": item.get("availability"),
                    "unavailable_reason": item.get("unavailable_reason") or item.get("error"),
                }
                for item in third_party_checks
                }
            }
            component_source_disagreements = list(stats.get("source_disagreement_issues", []))
            component_conflict_gate = stats.get("component_conflict_gate", {})
            component_gate_issues = list(component_conflict_gate.get("high_core_component_disagreements", []))
            anomalies = (
                list(metrics.get("anomalies", []))
                + list(valuation_audit.get("source_disagreement_issues", []))
                + component_source_disagreements[:20]
            )
            data_quality = _quality_block(
                source_tier=SOURCE_TIER_COMPONENT_MODEL,
                data_date=effective_date.strftime("%Y-%m-%d"),
                update_frequency="latest component fundamentals; shared once per run and refreshed on collection",
                formula=(
                    "Trailing PE = covered market cap / covered trailing earnings; "
                    "Forward PE = covered market cap / covered forward earnings; "
                    "FCF yield = covered FCF / covered market cap; "
                    "PB = covered market cap / covered implied book equity"
                ),
                coverage=metrics.get("coverage", {}),
                anomalies=anomalies,
                fallback_chain=VALUATION_FALLBACK_CHAIN,
                source_disagreement=source_disagreement,
            )
            data_quality["fallback_reason"] = NDX_COMPONENT_VALUATION_FALLBACK_REASON
            if component_conflict_gate.get("status") == "degraded":
                data_quality["availability"] = "degraded"
                data_quality["degraded_reason"] = (
                    "High yfinance/Yahoo component valuation disagreement; affected ticker fields were rejected from core aggregate calculation."
                )
            data_quality["metric_authority"] = valuation_audit.get("metric_authority", {})
            data_quality["source_disagreement_issues"] = (
                list(valuation_audit.get("source_disagreement_issues", []))
                + [
                    {
                        "issue_type": "component_source_disagreement",
                        "metric": item.get("field"),
                        "ticker": item.get("ticker"),
                        "severity": item.get("severity"),
                        "relative_diff_pct": item.get("relative_diff_pct"),
                        "threshold_pct": item.get("threshold_pct"),
                        "market_cap_weight_pct": item.get("market_cap_weight_pct"),
                        "blocks_publish": item.get("blocks_publish", False),
                        "action": item.get("action"),
                    }
                    for item in component_gate_issues
                ]
            )
            data_quality["component_source_disagreement_issues"] = component_source_disagreements
            data_quality["source_counts"] = stats.get("source_counts", {})
            data_quality["official_checks"] = stats.get("official_checks", {})
            data_quality["source_switches"] = stats.get("source_switches", [])
            data_quality["primary_source_by_field"] = stats.get("primary_source_by_field", {})
            data_quality["component_conflict_gate"] = component_conflict_gate
            data_quality["sec_official_facts"] = stats.get("sec_official_facts", {})
            data_quality["rejected_metrics"] = rejected_metrics
            data_quality["core_usage_rule"] = valuation_audit.get("core_usage_rule")
            return {
                "name": "NDX P/E and Earnings Yield",
                "series_id": "NDX_WEIGHTED",
                "value": {
                    "PE": metrics.get('weighted_trailing_pe'),
                    "TrailingPE": metrics.get('weighted_trailing_pe'),
                    "ForwardPE": metrics.get('weighted_forward_pe'),
                    "EarningsYield": metrics.get('weighted_earnings_yield'),
                    "ForwardEarningsYield": metrics.get('weighted_forward_earnings_yield'),
                    "ForwardEarningsProxyUSD": metrics.get('forward_earnings_proxy_usd'),
                    "ForwardEPSGrowthProxyPct": metrics.get('weighted_forward_eps_growth_proxy_pct'),
                    "ForwardEPSGrowthProxyMethod": metrics.get("forward_eps_growth_proxy_method"),
                    "WeightedEarningsGrowthPct": metrics.get('weighted_earnings_growth_pct'),
                    "WeightedRevenueGrowthPct": metrics.get('weighted_revenue_growth_pct'),
                    "WeightedProfitMarginPct": metrics.get('weighted_profit_margin_pct'),
                    "WeightedGrossMarginPct": metrics.get('weighted_gross_margin_pct'),
                    "WeightedOperatingMarginPct": metrics.get('weighted_operating_margin_pct'),
                    "FCFYield": metrics.get('weighted_fcf_yield'),
                    "PriceToBook": None if "PriceToBook" in rejected_metrics else metrics.get('weighted_price_to_book'),
                    "PriceToBookMethod": metrics.get("price_to_book_method"),
                    "MetricAuthority": valuation_audit.get("metric_authority", {}),
                    "RejectedMetrics": rejected_metrics,
                    "Coverage": {
                        "stocks_analyzed": stats['successful'],
                        "total_stocks": stats['total_tickers'],
                        "market_cap_coverage": f"{coverage_pct:.1f}%",
                        "metric_coverage": metrics.get("coverage", {}),
                        "failed_tickers": stats['failed_tickers'][:5] + ["..."] if len(stats['failed_tickers']) > 5 else stats['failed_tickers'],
                        "source_counts": stats.get("source_counts", {}),
                        "official_checks": stats.get("official_checks", {}),
                        "source_switches": stats.get("source_switches", [])[:20],
                    },
                    "Anomalies": anomalies,
                    "ThirdPartyChecks": third_party_checks,
                    "SourceReconciliation": {
                        "primary_source": stats.get("primary_source"),
                        "primary_source_by_field": stats.get("primary_source_by_field", {}),
                        "candidate_sources": stats.get("candidate_sources", []),
                        "source_counts": stats.get("source_counts", {}),
                        "official_checks": stats.get("official_checks", {}),
                        "source_switches": stats.get("source_switches", [])[:20],
                        "component_source_disagreements": component_source_disagreements[:20],
                        "component_conflict_gate": component_conflict_gate,
                        "sec_official_facts": stats.get("sec_official_facts", {}),
                    },
                },
                "unit": "ratio/percent",
                "date": effective_date.strftime("%Y-%m-%d"),
                "source_tier": SOURCE_TIER_COMPONENT_MODEL,
                "source_name": "field-policy L4 snapshot: Yahoo expectations, SEC facts, yfinance valuation cross-check, Eastmoney QA",
                "data_quality": data_quality,
                "notes": f"市值加权计算，覆盖{coverage_pct:.1f}%的NDX成分股"
            }
        except Exception as e:
            print(f"yfinance计算NDX基本面失败：{str(e)[:50]}，尝试Alpha Vantage备用方案")
            return get_ndx_pe_and_earnings_yield_av(end_date=effective_date.strftime("%Y-%m-%d"))
    else:
        # yfinance不可用时直接降级到Alpha Vantage
        return get_ndx_pe_and_earnings_yield_av(end_date=effective_date.strftime("%Y-%m-%d"))


def _direction_from_change(change_pct: Optional[float]) -> str:
    if change_pct is None:
        return "unavailable"
    if change_pct >= 1.0:
        return "upward"
    if change_pct <= -1.0:
        return "downward"
    return "flat"


def _m7_eps_revision_snapshot(market_caps: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    market_caps = market_caps or {}
    snapshots: Dict[str, Any] = {}
    weighted_changes: List[Tuple[float, float]] = []
    analyst_counts: List[int] = []
    if not YF_AVAILABLE:
        return {"availability": "unavailable", "reason": "yfinance unavailable", "members": snapshots}

    for ticker in M7_TICKERS:
        try:
            stock = yf.Ticker(ticker)
            trend = stock.get_eps_trend()
            estimate = stock.get_earnings_estimate()
            if trend is None or trend.empty or "+1y" not in trend.index:
                raise Exception("missing +1y eps trend")
            row = trend.loc["+1y"]
            current = _safe_float(row.get("current"))
            days_30 = _safe_float(row.get("30daysAgo"))
            days_90 = _safe_float(row.get("90daysAgo"))
            change_30 = ((current / days_30 - 1) * 100) if current and days_30 else None
            change_90 = ((current / days_90 - 1) * 100) if current and days_90 else None
            analyst_count = None
            if estimate is not None and not estimate.empty and "+1y" in estimate.index:
                analyst_count = estimate.loc["+1y"].get("numberOfAnalysts")
                try:
                    analyst_counts.append(int(analyst_count))
                except Exception:
                    pass
            weight = float(market_caps.get(ticker) or 0.0)
            if weight > 0 and change_30 is not None:
                weighted_changes.append((weight, change_30))
            snapshots[ticker] = {
                "next_year_eps_current": _round_or_none(current),
                "next_year_eps_30d_ago": _round_or_none(days_30),
                "next_year_eps_90d_ago": _round_or_none(days_90),
                "revision_30d_pct": _round_or_none(change_30),
                "revision_90d_pct": _round_or_none(change_90),
                "revision_direction_30d": _direction_from_change(change_30),
                "next_year_analyst_count": int(analyst_count) if analyst_count is not None and not pd.isna(analyst_count) else None,
                "source": "yfinance eps_trend / earnings_estimate",
            }
            time.sleep(0.05)
        except Exception as exc:
            snapshots[ticker] = {"error": str(exc)[:80], "source": "yfinance eps_trend"}

    weighted_revision = None
    if weighted_changes:
        total_weight = sum(weight for weight, _ in weighted_changes)
        weighted_revision = sum(weight * change for weight, change in weighted_changes) / total_weight if total_weight else None
    available = [item for item in snapshots.values() if isinstance(item, dict) and not item.get("error")]
    return {
        "availability": "available" if available else "unavailable",
        "coverage": {"available_members": len(available), "total_members": len(M7_TICKERS)},
        "weighted_next_year_eps_revision_30d_pct": _round_or_none(weighted_revision),
        "revision_direction_30d": _direction_from_change(weighted_revision),
        "median_next_year_analyst_count": int(np.median(analyst_counts)) if analyst_counts else None,
        "members": snapshots,
        "methodology": "M7 representative analyst revision proxy from yfinance EPS trend: +1y current estimate vs 30 days ago, market-cap weighted when caps are available.",
    }


def get_ndx_forward_earnings_quality(end_date: str = None) -> Dict[str, Any]:
    """Forward earnings, analyst revision and margin-quality proxy for NDX/M7 valuation support."""
    effective_date = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()
    date_str = effective_date.strftime("%Y-%m-%d")
    if not YF_AVAILABLE:
        return {
            "name": "NDX Forward Earnings Quality",
            "series_id": "NDX_FORWARD_EARNINGS_QUALITY",
            "value": None,
            "unit": "mixed",
            "source_tier": SOURCE_TIER_UNAVAILABLE,
            "source_name": "yfinance",
            "notes": "yfinance unavailable; forward earnings quality cannot be collected.",
        }

    try:
        df, stats = get_ndx_components_data_yf_v5(end_date=end_date)
        if df.empty:
            raise Exception(f"no valid component data: {stats.get('error', 'unknown')}")
        metrics = calculate_weighted_metrics(df)
        market_caps = {
            str(row["ticker"]).upper(): float(row["market_cap"])
            for _, row in df.iterrows()
            if str(row.get("ticker", "")).upper() in M7_TICKERS and _safe_float(row.get("market_cap"))
        }
        m7_frame = df[df["ticker"].isin(M7_TICKERS)].copy() if "ticker" in df.columns else pd.DataFrame()
        m7_revisions = _m7_eps_revision_snapshot_from_frame(m7_frame)
        eps_revision_primary_source = "yahoo_quote_summary"
        if m7_revisions.get("availability") != "available":
            yahoo_unavailable_reason = m7_revisions.get("reason") or "yahoo_snapshot_missing_eps_revision"
            m7_revisions = _m7_eps_revision_snapshot(market_caps)
            eps_revision_primary_source = "yfinance_fallback"
            m7_revisions["fallback_reason"] = yahoo_unavailable_reason
        m7_revisions["primary_source"] = eps_revision_primary_source
        weighted_eps_revision = _weighted_eps_revision_from_frame(df)
        m7_metrics = calculate_weighted_metrics(m7_frame) if not m7_frame.empty else {}
        coverage_pct = stats.get("coverage", 0) * 100
        value = {
            "data_date": date_str,
            "ndx": {
                "weighted_forward_pe": metrics.get("weighted_forward_pe"),
                "forward_earnings_yield_pct": metrics.get("weighted_forward_earnings_yield"),
                "forward_earnings_proxy_usd": metrics.get("forward_earnings_proxy_usd"),
                "forward_eps_growth_proxy_pct": metrics.get("weighted_forward_eps_growth_proxy_pct"),
                "forward_eps_growth_proxy_method": metrics.get("forward_eps_growth_proxy_method"),
                "weighted_earnings_growth_pct": metrics.get("weighted_earnings_growth_pct"),
                "weighted_revenue_growth_pct": metrics.get("weighted_revenue_growth_pct"),
                "weighted_profit_margin_pct": metrics.get("weighted_profit_margin_pct"),
                "weighted_gross_margin_pct": metrics.get("weighted_gross_margin_pct"),
                "weighted_operating_margin_pct": metrics.get("weighted_operating_margin_pct"),
                "weighted_eps_revision_30d_pct": weighted_eps_revision,
                "eps_revision_source": eps_revision_primary_source,
                "eps_revision_usage": "earnings_expectation_change_only_not_valuation_cheapness",
                "coverage": metrics.get("coverage", {}),
            },
            "m7": {
                "weighted_forward_pe": m7_metrics.get("weighted_forward_pe"),
                "forward_earnings_yield_pct": m7_metrics.get("weighted_forward_earnings_yield"),
                "forward_eps_growth_proxy_pct": m7_metrics.get("weighted_forward_eps_growth_proxy_pct"),
                "forward_eps_growth_proxy_method": m7_metrics.get("forward_eps_growth_proxy_method"),
                "weighted_profit_margin_pct": m7_metrics.get("weighted_profit_margin_pct"),
                "weighted_gross_margin_pct": m7_metrics.get("weighted_gross_margin_pct"),
                "weighted_operating_margin_pct": m7_metrics.get("weighted_operating_margin_pct"),
                "eps_revisions": m7_revisions,
            },
            "source_boundary": (
                "NDX forward earnings and margin quality are component-model proxies from a shared L4 snapshot. "
                "EPS revisions use Yahoo quoteSummary as the primary analyst-trend source when available; "
                "they describe earnings expectation changes only and are not an official Nasdaq aggregate revision series."
            ),
        }
        component_conflict_gate = stats.get("component_conflict_gate", {})
        result = {
            "name": "NDX Forward Earnings Quality",
            "series_id": "NDX_FORWARD_EARNINGS_QUALITY",
            "value": value,
            "unit": "ratio/percent/mixed",
            "date": date_str,
            "source_tier": SOURCE_TIER_COMPONENT_MODEL,
            "source_name": "shared L4 component snapshot + Yahoo EPS revisions",
            "data_quality": _quality_block(
                source_tier=SOURCE_TIER_COMPONENT_MODEL,
                data_date=date_str,
                update_frequency="latest component fundamentals; Yahoo EPS trend refreshed with quoteSummary",
                formula=(
                    "Forward earnings yield = covered forward earnings / covered market cap; "
                    "margin quality = market-cap weighted profit/gross/operating margins; "
                    "EPS revisions = Yahoo earningsTrend current estimate vs 30 days ago."
                ),
                coverage={
                    "component_coverage_pct": round(coverage_pct, 2),
                    "components_successful": stats.get("successful"),
                    "total_tickers": stats.get("total_tickers"),
                    "metric_coverage": metrics.get("coverage", {}),
                    "m7_revision_coverage": m7_revisions.get("coverage", {}),
                    "source_counts": stats.get("source_counts", {}),
                    "official_checks": stats.get("official_checks", {}),
                    "primary_source_by_field": stats.get("primary_source_by_field", {}),
                },
                anomalies=metrics.get("anomalies", []),
                fallback_chain=[SOURCE_TIER_LICENSED_MANUAL, SOURCE_TIER_COMPONENT_MODEL, SOURCE_TIER_PROXY, SOURCE_TIER_UNAVAILABLE],
                source_disagreement={
                    "official_ndx_revision_series": "not available in automated source; use manual/Wind if supplied",
                    "component_source_disagreements": stats.get("source_disagreement_issues", [])[:20],
                    "source_switches": stats.get("source_switches", [])[:20],
                },
            ),
            "notes": "补充 Forward EPS、盈利修正和利润率质量代理，避免 L4 只看当前 PE/ERP。",
        }
        result["data_quality"]["fallback_reason"] = NDX_FORWARD_QUALITY_FALLBACK_REASON
        if component_conflict_gate.get("status") == "degraded":
            result["data_quality"]["availability"] = "degraded"
            result["data_quality"]["degraded_reason"] = (
                "High yfinance/Yahoo component valuation disagreement; affected ticker fields were rejected from core aggregate calculation."
            )
        result["data_quality"]["metric_authority"] = {
            "weighted_forward_pe": _component_metric_authority(
                usage="supporting_only",
                authority="duplicate_component_proxy",
                reason="Use get_ndx_pe_and_earnings_yield for cross-checked Forward PE; this field is kept only as context.",
            ),
            "forward_eps_growth_proxy_pct": _component_metric_authority(
                usage="supporting_only",
                authority="proxy_only",
                reason="Aggregate forward/trailing earnings proxy derived from component PE fields; not an official NDX aggregate earnings growth estimate.",
            ),
            "weighted_earnings_growth_pct": _component_metric_authority(
                usage="supporting_only",
                authority="proxy_only",
                reason="Market-cap weighted yfinance earningsGrowth field; may mix quarterly/annual conventions across tickers.",
            ),
            "weighted_profit_margin_pct": _component_metric_authority(
                usage="supporting_only",
                authority="proxy_only",
                reason="Market-cap weighted yfinance margin field; supporting context only.",
            ),
            "m7_eps_revisions": _component_metric_authority(
                usage="supporting_only",
                authority="proxy_only",
                reason="M7 representative analyst revision proxy from Yahoo quoteSummary when available; not an official NDX-wide revision series.",
                source="yahoo_quote_summary" if eps_revision_primary_source == "yahoo_quote_summary" else SOURCE_TIER_COMPONENT_MODEL,
            ),
            "ndx_weighted_eps_revision_30d_pct": _component_metric_authority(
                usage="supporting_only",
                authority="earnings_expectation_change_only",
                reason="Yahoo EPS revision can describe whether earnings expectations are moving up or down, but cannot independently prove valuation attractiveness.",
                source="yahoo_quote_summary" if eps_revision_primary_source == "yahoo_quote_summary" else SOURCE_TIER_COMPONENT_MODEL,
            ),
        }
        result["data_quality"]["source_counts"] = stats.get("source_counts", {})
        result["data_quality"]["official_checks"] = stats.get("official_checks", {})
        result["data_quality"]["component_source_disagreement_issues"] = stats.get("source_disagreement_issues", [])
        result["data_quality"]["source_switches"] = stats.get("source_switches", [])
        result["data_quality"]["primary_source_by_field"] = stats.get("primary_source_by_field", {})
        result["data_quality"]["component_conflict_gate"] = component_conflict_gate
        result["data_quality"]["sec_official_facts"] = stats.get("sec_official_facts", {})
        result["data_quality"]["core_usage_rule"] = (
            "Forward earnings quality fields are supporting proxies. They may explain whether high valuation has some support, "
            "but cannot independently prove NDX valuation is attractive."
        )
        return result
    except Exception as exc:
        return {
            "name": "NDX Forward Earnings Quality",
            "series_id": "NDX_FORWARD_EARNINGS_QUALITY",
            "value": None,
            "unit": "mixed",
            "source_tier": SOURCE_TIER_UNAVAILABLE,
            "source_name": "yfinance component model + M7 EPS trend",
            "notes": f"Forward earnings quality unavailable: {str(exc)[:120]}",
        }


def get_equity_risk_premium(end_date: str = None) -> Dict[str, Any]:
    """计算NDX简式收益差距：收益率 - 10Y，美股implied ERP另列参考。"""
    if end_date:
        effective_date = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        effective_date = datetime.now()

    date_str = effective_date.strftime("%Y-%m-%d")

    # 获取NDX收益率数据
    ndx_data = get_ndx_pe_and_earnings_yield(end_date=end_date)
    if not ndx_data.get("value"):
        return {
            "name": "NDX Simple Yield Gap",
            "value": None,
            "source_tier": SOURCE_TIER_UNAVAILABLE,
            "notes": "无法获取NDX收益率数据，计算失败"
        }

    # 优先使用FCF收益率，其次用盈利收益率
    yield_to_use = None
    yield_type = None
    ndx_value = ndx_data["value"]

    metric_authority = ndx_value.get("MetricAuthority") if isinstance(ndx_value.get("MetricAuthority"), dict) else {}
    fcf_usage = (metric_authority.get("FCFYield") or {}).get("usage") if isinstance(metric_authority.get("FCFYield"), dict) else None
    earnings_usage = (metric_authority.get("EarningsYield") or {}).get("usage") if isinstance(metric_authority.get("EarningsYield"), dict) else None
    if ndx_value.get("FCFYield") is not None and (not metric_authority or fcf_usage == "core_allowed"):
        yield_to_use = ndx_value["FCFYield"]
        yield_type = "fcf_yield"
    elif ndx_value.get("EarningsYield") is not None and (not metric_authority or earnings_usage == "core_allowed"):
        yield_to_use = ndx_value["EarningsYield"]
        yield_type = "earnings_yield"
    else:
        return {
            "name": "NDX Simple Yield Gap",
            "value": None,
            "source_tier": SOURCE_TIER_UNAVAILABLE,
            "notes": "NDX无有效且具备核心发言权的收益率数据（FCF/盈利）"
        }

    # 获取10年期美债收益率（无风险利率）
    if get_10y_treasury is None:
        treasury_data = {"value": None}
    else:
        treasury_data = get_10y_treasury(end_date=date_str)
    treasury_value = treasury_data.get("value") if isinstance(treasury_data, dict) else None
    treasury_yield = treasury_value.get("level") if isinstance(treasury_value, dict) else None
    if treasury_yield is None:
        treasury_reason = (
            treasury_data.get("unavailable_reason")
            or treasury_data.get("error")
            or treasury_data.get("notes")
            if isinstance(treasury_data, dict)
            else None
        )
        return {
            "name": "NDX Simple Yield Gap",
            "value": None,
            "source_tier": SOURCE_TIER_UNAVAILABLE,
            "notes": "无法获取10年期美债收益率（无风险利率）",
            "unavailable_reason": treasury_reason or "missing_10y_treasury_level",
        }

    gap = round(yield_to_use - treasury_yield, 2)
    method = f"{yield_type}_minus_10y"
    formula = "NDX FCF yield - 10Y Treasury yield" if yield_type == "fcf_yield" else "NDX earnings yield - 10Y Treasury yield"
    source_tier = ndx_data.get("source_tier") or ndx_data.get("data_quality", {}).get("source_tier") or SOURCE_TIER_COMPONENT_MODEL
    data_quality = _quality_block(
        source_tier=source_tier,
        data_date=date_str,
        update_frequency="daily when NDX valuation and Treasury sources update",
        formula=formula,
        coverage=ndx_data.get("data_quality", {}).get("coverage", ndx_value.get("Coverage", {})),
        anomalies=ndx_data.get("data_quality", {}).get("anomalies", []),
        fallback_chain=[source_tier, SOURCE_TIER_OFFICIAL, SOURCE_TIER_UNAVAILABLE],
        source_disagreement=ndx_data.get("data_quality", {}).get("source_disagreement", {}),
    )
    return {
        "name": "NDX Simple Yield Gap",
        "series_id": "SIMPLE_YIELD_GAP",
        "value": {
            "level": gap,
            "date": date_str,
            "method": method,
            "yield_type": yield_type,
            "components": {
                f"NDX {yield_type}": f"{yield_to_use}%",
                "10Y Treasury Yield (Risk-Free)": f"{treasury_yield}%"
            },
            "not_implied_erp_warning": "This is a simple yield gap, not Damodaran-style implied ERP.",
            "yield_authority": (metric_authority.get("FCFYield") if yield_type == "fcf_yield" else metric_authority.get("EarningsYield")) or {},
            "rejected_yield_inputs": {
                key: item
                for key, item in metric_authority.items()
                if key in {"FCFYield", "EarningsYield"} and isinstance(item, dict) and item.get("usage") != "core_allowed"
            },
            "damodaran_reference": {
                "function_id": "get_damodaran_us_implied_erp",
                "scope": "US equity market reference, not NDX-specific",
            },
        },
        "unit": "percent",
        "source_tier": SOURCE_TIER_COMPONENT_MODEL,
        "source_name": "Calculated simple yield gap (NDX valuation + 10Y Treasury)",
        "data_quality": data_quality,
        "notes": "该指标只衡量当前盈利/现金流收益率相对10年期美债的简式差距，未包含未来增长、回购、现金流路径或终值假设，不能当作 Damodaran 式 implied ERP。"
    }

# =====================================================
# 第五层：技术指标（*本轮修改部分*）
# =====================================================
