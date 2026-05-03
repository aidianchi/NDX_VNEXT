# -*- coding: utf-8 -*-
"""
Manual data compatibility layer.

Runtime data now lives in JSON files:
- config/manual_data.local.json
- config/manual_data.example.json

This module keeps the old import surface intact:
    from manual_data import MANUAL_DATA
"""

from __future__ import annotations

import json
import logging
import os
from copy import deepcopy
from typing import Any, Dict, Optional

try:
    from .config import path_config
except ImportError:
    from config import path_config

ManualData = Dict[str, Any]

DEFAULT_MANUAL_DATA: ManualData = {
    "active": False,
    "date": "",
    "metrics": {
        "get_ndx_pe_and_earnings_yield": {
            "name": "NDX Valuation (Manual)",
            "series_id": "NDX_MANUAL",
            "value": {
                "PE_TTM": None,
                "ForwardPE": None,
                "EarningsYield": None,
                "ForwardEarningsYield": None,
                "FCFYield": None,
                "PB": None,
                "PS_TTM": None,
                "PCF_TTM": None,
                "PE_TTM_percentile_5y": None,
                "ForwardPE_percentile_5y": None,
                "FCFYield_percentile_5y": None,
                "PB_percentile_5y": None,
            },
            "unit": "ratio/percent",
            "source_tier": "licensed_manual/Wind",
            "source_name": "Manual Input (optional high-trust source)",
            "data_quality": {
                "source_tier": "licensed_manual/Wind",
                "data_date": "",
                "collected_at_utc": "",
                "update_frequency": "user supplied",
                "formula": "Optional Wind/manual valuation fields; PE and ForwardPE should be index-level or aggregate-earnings based, not simple constituent averages",
                "coverage": {"note": "Manual source coverage must be supplied or reviewed by user."},
                "anomalies": [],
                "fallback_chain": ["licensed_manual/Wind", "official", "component_model", "third_party_estimate", "proxy", "unavailable"],
                "source_disagreement": {},
            },
            "notes": "Optional high-trust manual valuation input. When inactive or blank, live sources are used.",
        },
        "get_equity_risk_premium": {
            "name": "NDX Simple Yield Gap (Manual)",
            "series_id": "SIMPLE_YIELD_GAP_MANUAL",
            "value": {
                "level": None,
                "method": "earnings_yield_minus_10y_or_fcf_yield_minus_10y",
                "yield_type": None,
                "ndx_yield": None,
                "treasury_10y": None,
                "percentile_5y": None,
                "not_implied_erp_warning": "Simple yield gap only; not Damodaran implied ERP",
                "damodaran_reference": "get_damodaran_us_implied_erp",
            },
            "unit": "percent",
            "source_tier": "licensed_manual/Wind",
            "source_name": "Manual Input (optional high-trust source)",
            "data_quality": {
                "source_tier": "licensed_manual/Wind",
                "data_date": "",
                "collected_at_utc": "",
                "update_frequency": "user supplied",
                "formula": "earnings_yield - 10Y or fcf_yield - 10Y; not Damodaran implied ERP",
                "coverage": {"note": "Manual source coverage must be supplied or reviewed by user."},
                "anomalies": [],
                "fallback_chain": ["licensed_manual/Wind", "component_model", "proxy", "unavailable"],
                "source_disagreement": {},
            },
            "notes": "Optional manual simple yield gap input. This is not Damodaran-style implied ERP.",
        },
        "get_damodaran_us_implied_erp": {
            "name": "Manual/Wind ERP Reference",
            "series_id": "MANUAL_ERP_REFERENCE",
            "value": {
                "manual_erp": None,
                "implied_erp_fcfe": None,
                "implied_erp_ddm": None,
                "tbond_rate": None,
                "scope": "manual/Wind ERP reference; specify US market, NDX, or other scope when used",
                "not_ndx_valuation_warning": "Manual ERP reference is not NDX PE/Forward PE/PB historical percentile.",
            },
            "unit": "percent",
            "source_tier": "licensed_manual/Wind",
            "source_name": "Manual Input (optional high-trust ERP reference)",
            "data_quality": {
                "source_tier": "licensed_manual/Wind",
                "data_date": "",
                "collected_at_utc": "",
                "update_frequency": "user supplied",
                "formula": "User-supplied manual ERP/reference risk premium; not NDX simple yield gap unless explicitly calculated that way",
                "coverage": {"note": "Manual ERP scope must be supplied or reviewed by user."},
                "anomalies": [],
                "fallback_chain": ["licensed_manual/Wind", "official", "unavailable"],
                "source_disagreement": {},
            },
            "notes": "Optional manual ERP reference; not NDX simple yield gap and not a substitute for NDX PE/Forward PE/PB percentile.",
        },
        "get_crowdedness_dashboard": {
            "name": "Crowdedness Dashboard (Manual)",
            "series_id": "CROWDEDNESS_MANUAL",
            "value": {
                "positioning_z_score": None,
                "sentiment_index": None,
                "flow_data_mm": None,
            },
            "unit": "various",
            "source_name": "Manual Input",
            "notes": "Manual crowdedness override.",
        },
    },
}

_ALLOWED_METRIC_FIELDS = (
    "name",
    "series_id",
    "value",
    "unit",
    "source_tier",
    "source_name",
    "source_url",
    "date",
    "data_quality",
    "notes",
)


def get_manual_data_example_path() -> str:
    return path_config.manual_data_example_path


def get_manual_data_local_path() -> str:
    return path_config.manual_data_local_path


def get_active_manual_data_path() -> Optional[str]:
    for candidate in (get_manual_data_local_path(), get_manual_data_example_path()):
        if os.path.exists(candidate):
            return candidate
    return None


def _load_raw_json(path: str) -> ManualData:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        logging.warning("Failed to parse manual data config %s: %s", path, exc)
        return {}
    except Exception as exc:  # noqa: BLE001
        logging.warning("Failed to load manual data config %s: %s", path, exc)
        return {}


def _sanitize_metric(metric_key: str, metric_value: Any) -> Optional[Dict[str, Any]]:
    if not isinstance(metric_key, str) or not metric_key.startswith("get_"):
        return None
    if not isinstance(metric_value, dict):
        return None

    cleaned = deepcopy(DEFAULT_MANUAL_DATA["metrics"].get(metric_key, {}))
    for field in _ALLOWED_METRIC_FIELDS:
        if field in metric_value:
            cleaned[field] = deepcopy(metric_value[field])

    if not cleaned:
        return None

    cleaned.setdefault("name", metric_key.replace("_", " ").title())
    cleaned.setdefault("series_id", metric_key.upper())
    cleaned.setdefault("value", {})
    cleaned.setdefault("unit", "")
    cleaned.setdefault("source_name", "Manual Input")
    cleaned.setdefault("source_tier", "licensed_manual/Wind")
    cleaned.setdefault("notes", "")
    return cleaned


def _has_meaningful_value(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip() != ""
    if isinstance(value, dict):
        return any(_has_meaningful_value(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(_has_meaningful_value(item) for item in value)
    return True


_MEANINGFUL_VALUE_IGNORED_KEYS = {
    "method",
    "formula",
    "yield_type",
    "components",
    "not_implied_erp_warning",
    "damodaran_reference",
}


def has_meaningful_manual_override(metric: Optional[Dict[str, Any]]) -> bool:
    if not isinstance(metric, dict):
        return False
    value = metric.get("value")
    if isinstance(value, dict):
        value = {
            key: item
            for key, item in value.items()
            if key not in _MEANINGFUL_VALUE_IGNORED_KEYS
        }
    return _has_meaningful_value(value)


def normalize_manual_data(
    raw_data: Optional[ManualData],
    *,
    include_default_metrics: bool = False,
) -> ManualData:
    normalized: ManualData = {
        "active": DEFAULT_MANUAL_DATA["active"],
        "date": DEFAULT_MANUAL_DATA["date"],
        "metrics": {},
    }

    if not isinstance(raw_data, dict):
        return normalized

    normalized["active"] = bool(raw_data.get("active", normalized["active"]))

    date_value = raw_data.get("date")
    if isinstance(date_value, str):
        normalized["date"] = date_value

    normalized_metrics: Dict[str, Any] = {}
    raw_metrics = raw_data.get("metrics", {})
    if isinstance(raw_metrics, dict):
        for metric_key, metric_value in raw_metrics.items():
            cleaned_metric = _sanitize_metric(metric_key, metric_value)
            if cleaned_metric is not None:
                normalized_metrics[metric_key] = cleaned_metric

    if include_default_metrics:
        for metric_key, metric_template in DEFAULT_MANUAL_DATA["metrics"].items():
            normalized_metrics.setdefault(metric_key, deepcopy(metric_template))

    normalized["metrics"] = normalized_metrics
    return normalized


def load_manual_data(path: Optional[str] = None) -> ManualData:
    resolved_path = path or get_active_manual_data_path()
    if not resolved_path:
        return normalize_manual_data(DEFAULT_MANUAL_DATA, include_default_metrics=True)
    include_default_metrics = os.path.normcase(resolved_path) == os.path.normcase(get_manual_data_example_path())
    return normalize_manual_data(
        _load_raw_json(resolved_path),
        include_default_metrics=include_default_metrics,
    )


def save_manual_data(data: ManualData, path: Optional[str] = None) -> ManualData:
    resolved_path = path or get_manual_data_local_path()
    include_default_metrics = os.path.normcase(resolved_path) == os.path.normcase(get_manual_data_example_path())
    normalized = normalize_manual_data(data, include_default_metrics=include_default_metrics)
    os.makedirs(os.path.dirname(resolved_path), exist_ok=True)
    with open(resolved_path, "w", encoding="utf-8") as handle:
        json.dump(normalized, handle, ensure_ascii=False, indent=2)
        handle.write("\n")
    return normalized


MANUAL_DATA = load_manual_data()
