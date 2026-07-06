from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional


Fetcher = Callable[[int], Any]
DEFAULT_CHART_LOOKBACK_DAYS = 3650


WORKBENCH_MODULES: Dict[str, Dict[str, Any]] = {
    "price_technical": {
        "title": "价格技术",
        "question": "价格突破、回撤、动量和量价确认是否同向？",
        "layer_tags": ["L5"],
        "function_ids": [
            "get_qqq_technical_indicators",
            "get_volume_analysis_qqq",
            "get_obv_qqq",
            "get_macd_qqq",
            "get_atr_qqq",
            "get_price_volume_quality_qqq",
            "get_donchian_channels_qqq",
            "get_multi_scale_ma_position",
        ],
        "series": ["QQQ_OHLCV"],
    },
    "volatility_credit": {
        "title": "波动信用",
        "question": "价格强势是否被波动率或信用风险提前否定？",
        "layer_tags": ["L2", "L5"],
        "function_ids": ["get_vix", "get_vxn", "get_vxn_vix_ratio", "get_hy_oas_bp", "get_ig_oas_bp", "get_hy_quality_spread_bp", "get_hyg_momentum"],
        "series": ["VIX", "VXN", "VXN_VIX_RATIO", "HY_OAS", "IG_OAS", "HY_QUALITY_SPREAD", "HYG", "QQQ_OHLCV"],
    },
    "rates_valuation": {
        "title": "利率估值",
        "question": "高估值是否遇到高真实利率和低风险补偿的双重挤压？",
        "layer_tags": ["L1", "L4"],
        "function_ids": [
            "get_10y_treasury",
            "get_10y_real_rate",
            "get_10y_breakeven",
            "get_fed_funds_rate",
            "get_ndx_wind_valuation_snapshot",
            "get_ndx_pe_and_earnings_yield",
            "get_equity_risk_premium",
            "get_damodaran_us_implied_erp",
        ],
        "series": ["US10Y", "US10Y_REAL", "US10Y_BREAKEVEN", "FED_FUNDS", "DAMODARAN_ERP_MONTHLY"],
    },
    "breadth_concentration": {
        "title": "广度集中度",
        "question": "指数上涨是扩散，还是少数头部权重硬撑？",
        "layer_tags": ["L3", "L5"],
        "function_ids": ["get_ndx_ndxe_ratio", "get_percent_above_ma", "get_advance_decline_line", "get_new_highs_lows"],
        "series": ["NDX_NDXE_RATIO", "QQQ_OHLCV"],
    },
    "liquidity": {
        "title": "流动性",
        "question": "资金面改善是否真的传导到风险偏好？",
        "layer_tags": ["L1", "L2", "L5"],
        "function_ids": ["get_net_liquidity_momentum", "get_m2_yoy", "get_hy_oas_bp", "get_qqq_technical_indicators"],
        "series": ["NET_LIQUIDITY", "WALCL", "TGA", "RRP", "M2_YOY", "QQQ_OHLCV", "HY_OAS"],
    },
}


SUPPLEMENTAL_SERIES_META: Dict[str, Dict[str, Any]] = {
    "VIX": {"label": "VIX", "provider": "yfinance/FRED-compatible", "frequency": "daily", "layer": "L2", "function_id": "get_vix"},
    "VXN": {"label": "VXN", "provider": "yfinance", "frequency": "daily", "layer": "L2", "function_id": "get_vxn"},
    "VXN_VIX_RATIO": {"label": "VXN/VIX", "provider": "calculated", "frequency": "daily", "layer": "L2", "function_id": "get_vxn_vix_ratio"},
    "HY_OAS": {"label": "HY OAS", "provider": "FRED", "frequency": "daily", "layer": "L2", "function_id": "get_hy_oas_bp"},
    "IG_OAS": {"label": "IG OAS", "provider": "FRED", "frequency": "daily", "layer": "L2", "function_id": "get_ig_oas_bp"},
    "HY_QUALITY_SPREAD": {"label": "CCC & Lower - BB OAS", "provider": "FRED / ICE BofA calculated", "frequency": "daily", "layer": "L2", "function_id": "get_hy_quality_spread_bp"},
    "HYG": {"label": "HYG", "provider": "yfinance", "frequency": "daily", "layer": "L2", "function_id": "get_hyg_momentum"},
    "US10Y": {"label": "10Y Treasury", "provider": "FRED", "frequency": "daily", "layer": "L1", "function_id": "get_10y_treasury"},
    "US10Y_REAL": {"label": "10Y Real Rate", "provider": "FRED", "frequency": "daily", "layer": "L1", "function_id": "get_10y_real_rate"},
    "US10Y_BREAKEVEN": {"label": "10Y Breakeven", "provider": "FRED", "frequency": "daily", "layer": "L1", "function_id": "get_10y_breakeven"},
    "FED_FUNDS": {"label": "Fed Funds", "provider": "FRED", "frequency": "monthly", "layer": "L1", "function_id": "get_fed_funds_rate"},
    "NDX_NDXE_RATIO": {"label": "NDX/NDXE", "provider": "calculated from yfinance/Yahoo index closes", "frequency": "daily", "layer": "L3", "function_id": "get_ndx_ndxe_ratio"},
    "QQQ_QQEW_RATIO": {"label": "QQQ/QQEW (legacy)", "provider": "legacy calculated series", "frequency": "daily", "layer": "L3", "function_id": "get_qqq_qqew_ratio"},
    "NET_LIQUIDITY": {"label": "Net Liquidity", "provider": "FRED calculated", "frequency": "daily/weekly forward-filled", "layer": "L1", "function_id": "get_net_liquidity_momentum"},
    "WALCL": {"label": "WALCL", "provider": "FRED", "frequency": "weekly", "layer": "L1", "function_id": "get_net_liquidity_momentum"},
    "TGA": {"label": "TGA", "provider": "FRED", "frequency": "daily", "layer": "L1", "function_id": "get_net_liquidity_momentum"},
    "RRP": {"label": "RRP", "provider": "FRED", "frequency": "daily", "layer": "L1", "function_id": "get_net_liquidity_momentum"},
    "M2_YOY": {"label": "M2 YoY", "provider": "FRED calculated", "frequency": "monthly", "layer": "L1", "function_id": "get_m2_yoy"},
}


def _safe_number(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _row_get(row: Any, key: str) -> Any:
    if isinstance(row, dict):
        return row.get(key)
    getter = getattr(row, "get", None)
    if callable(getter):
        return getter(key)
    return getattr(row, key, None)


def _date_text(value: Any) -> str:
    if hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    return str(value or "")


def _parse_date(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    try:
        parsed = datetime.fromisoformat(str(value)[:10])
        return parsed.replace(tzinfo=None)
    except Exception:
        return None


def _filter_rows_to_effective_date(rows: List[Dict[str, Any]], effective_date: Optional[str]) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    if not effective_date:
        max_date = max((str(row.get("time")) for row in rows if row.get("time")), default=None)
        return rows, {"max_observed_date": max_date, "future_rows_dropped": 0}
    effective = _parse_date(effective_date)
    if effective is None:
        max_date = max((str(row.get("time")) for row in rows if row.get("time")), default=None)
        return rows, {"effective_date": effective_date, "max_observed_date": max_date, "future_rows_dropped": 0}
    kept: List[Dict[str, Any]] = []
    dropped = 0
    max_observed: Optional[str] = None
    for row in rows:
        row_date = _parse_date(row.get("time"))
        if row_date is not None and row_date > effective:
            dropped += 1
            continue
        kept.append(row)
        if row.get("time") and (max_observed is None or str(row["time"]) > max_observed):
            max_observed = str(row["time"])
    return kept, {"effective_date": effective_date, "max_observed_date": max_observed, "future_rows_dropped": dropped}


def _sort_rows_by_time(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    decorated = []
    for index, row in enumerate(rows):
        row_date = _parse_date(row.get("time"))
        decorated.append((row_date is None, row_date or datetime.max, index, row))
    return [row for *_prefix, row in sorted(decorated, key=lambda item: item[:3])]


def _is_finite(value: Any) -> bool:
    number = _safe_number(value)
    return number is not None and math.isfinite(number)


def _round(value: Any, digits: int = 4) -> Optional[float]:
    number = _safe_number(value)
    if number is None or not math.isfinite(number):
        return None
    return round(number, digits)


def _rolling_mean(values: List[Optional[float]], window: int) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    for index in range(len(values)):
        tail = [item for item in values[max(0, index - window + 1) : index + 1] if item is not None]
        out.append(sum(tail) / len(tail) if len(tail) >= window else None)
    return out


def _rolling_std(values: List[Optional[float]], window: int) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    for index in range(len(values)):
        tail = [item for item in values[max(0, index - window + 1) : index + 1] if item is not None]
        if len(tail) < window:
            out.append(None)
            continue
        mean = sum(tail) / len(tail)
        out.append(math.sqrt(sum((item - mean) ** 2 for item in tail) / (len(tail) - 1)))
    return out


def _rolling_min(values: List[Optional[float]], window: int) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    for index in range(len(values)):
        tail = [item for item in values[max(0, index - window + 1) : index + 1] if item is not None]
        out.append(min(tail) if len(tail) >= window else None)
    return out


def _rolling_max(values: List[Optional[float]], window: int) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    for index in range(len(values)):
        tail = [item for item in values[max(0, index - window + 1) : index + 1] if item is not None]
        out.append(max(tail) if len(tail) >= window else None)
    return out


def _ema(values: List[Optional[float]], span: int) -> List[Optional[float]]:
    alpha = 2 / (span + 1)
    out: List[Optional[float]] = []
    current: Optional[float] = None
    for value in values:
        if value is None:
            out.append(current)
            continue
        current = value if current is None else alpha * value + (1 - alpha) * current
        out.append(current)
    return out


def _rsi(values: List[Optional[float]], window: int = 14) -> List[Optional[float]]:
    out: List[Optional[float]] = [None]
    gains: List[float] = []
    losses: List[float] = []
    for index in range(1, len(values)):
        if values[index] is None or values[index - 1] is None:
            gains.append(0.0)
            losses.append(0.0)
        else:
            change = values[index] - values[index - 1]  # type: ignore[operator]
            gains.append(max(change, 0.0))
            losses.append(abs(min(change, 0.0)))
        if len(gains) < window:
            out.append(None)
            continue
        avg_gain = sum(gains[-window:]) / window
        avg_loss = sum(losses[-window:]) / window
        if avg_loss == 0:
            out.append(100.0 if avg_gain > 0 else 50.0)
        else:
            rs = avg_gain / avg_loss
            out.append(100 - (100 / (1 + rs)))
    return out


def _obv(closes: List[Optional[float]], volumes: List[Optional[float]]) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    current = 0.0
    for index, close in enumerate(closes):
        if index == 0 or close is None or closes[index - 1] is None:
            out.append(current)
            continue
        volume = volumes[index] or 0.0
        if close > closes[index - 1]:  # type: ignore[operator]
            current += volume
        elif close < closes[index - 1]:  # type: ignore[operator]
            current -= volume
        out.append(current)
    return out


def _atr(highs: List[Optional[float]], lows: List[Optional[float]], closes: List[Optional[float]], window: int = 14) -> List[Optional[float]]:
    true_ranges: List[Optional[float]] = []
    for index, high in enumerate(highs):
        low = lows[index]
        close = closes[index]
        prev_close = closes[index - 1] if index > 0 else close
        if high is None or low is None:
            true_ranges.append(None)
            continue
        candidates = [high - low]
        if prev_close is not None:
            candidates.extend([abs(high - prev_close), abs(low - prev_close)])
        true_ranges.append(max(candidates))
    return _rolling_mean(true_ranges, window)


def _vwap(highs: List[Optional[float]], lows: List[Optional[float]], closes: List[Optional[float]], volumes: List[Optional[float]], window: int = 20) -> List[Optional[float]]:
    out: List[Optional[float]] = []
    tpv: List[Optional[float]] = []
    for high, low, close, volume in zip(highs, lows, closes, volumes):
        if high is None or low is None or close is None or volume is None:
            tpv.append(None)
        else:
            tpv.append(((high + low + close) / 3) * volume)
    for index in range(len(closes)):
        pv_tail = [item for item in tpv[max(0, index - window + 1) : index + 1] if item is not None]
        vol_tail = [item for item in volumes[max(0, index - window + 1) : index + 1] if item is not None]
        if len(pv_tail) < window or len(vol_tail) < window:
            out.append(None)
            continue
        vol_sum = sum(vol_tail)
        out.append(sum(pv_tail) / vol_sum if vol_sum else None)
    return out


def _mfi(highs: List[Optional[float]], lows: List[Optional[float]], closes: List[Optional[float]], volumes: List[Optional[float]], window: int = 14) -> List[Optional[float]]:
    typical: List[Optional[float]] = []
    for high, low, close in zip(highs, lows, closes):
        typical.append((high + low + close) / 3 if high is not None and low is not None and close is not None else None)
    positive: List[float] = [0.0]
    negative: List[float] = [0.0]
    for index in range(1, len(typical)):
        if typical[index] is None or typical[index - 1] is None:
            flow = 0.0
        else:
            flow = typical[index] * (volumes[index] or 0.0)  # type: ignore[operator]
        if typical[index] is not None and typical[index - 1] is not None and typical[index] > typical[index - 1]:  # type: ignore[operator]
            positive.append(flow)
            negative.append(0.0)
        elif typical[index] is not None and typical[index - 1] is not None and typical[index] < typical[index - 1]:  # type: ignore[operator]
            positive.append(0.0)
            negative.append(abs(flow))
        else:
            positive.append(0.0)
            negative.append(0.0)
    out: List[Optional[float]] = []
    for index in range(len(typical)):
        if index + 1 < window:
            out.append(None)
            continue
        pos_sum = sum(positive[index - window + 1 : index + 1])
        neg_sum = sum(negative[index - window + 1 : index + 1])
        if neg_sum == 0:
            out.append(100.0 if pos_sum > 0 else 50.0)
        else:
            out.append(100 - (100 / (1 + pos_sum / neg_sum)))
    return out


def _cmf(highs: List[Optional[float]], lows: List[Optional[float]], closes: List[Optional[float]], volumes: List[Optional[float]], window: int = 20) -> List[Optional[float]]:
    mfv: List[Optional[float]] = []
    for high, low, close, volume in zip(highs, lows, closes, volumes):
        if high is None or low is None or close is None or volume is None or high == low:
            mfv.append(0.0)
            continue
        multiplier = ((close - low) - (high - close)) / (high - low)
        mfv.append(multiplier * volume)
    out: List[Optional[float]] = []
    for index in range(len(closes)):
        vol_tail = [item for item in volumes[max(0, index - window + 1) : index + 1] if item is not None]
        if len(vol_tail) < window:
            out.append(None)
            continue
        vol_sum = sum(vol_tail)
        mfv_tail = [item for item in mfv[max(0, index - window + 1) : index + 1] if item is not None]
        out.append(sum(mfv_tail) / vol_sum if vol_sum else None)
    return out


def _default_fetcher(lookback_days: int, effective_date: Optional[str] = None) -> Any:
    try:
        from chart_adapter_v6 import get_qqq_price_data
    except ImportError:
        from .chart_adapter_v6 import get_qqq_price_data

    return get_qqq_price_data(lookback_days=lookback_days, end_date=effective_date)


def _frame_to_rows(frame: Any) -> List[Dict[str, Any]]:
    if frame is None or getattr(frame, "empty", False):
        return []
    rows: List[Dict[str, Any]] = []
    for _, row in frame.iterrows():
        close = _safe_number(_row_get(row, "close"))
        if close is None:
            continue
        prepared = {
            "time": _date_text(_row_get(row, "date")),
            "open": _safe_number(_row_get(row, "open")) or close,
            "high": _safe_number(_row_get(row, "high")) or close,
            "low": _safe_number(_row_get(row, "low")) or close,
            "close": close,
            "volume": _safe_number(_row_get(row, "volume")) or 0.0,
        }
        rows.append(prepared)
    return _enrich_ohlcv_rows(_sort_rows_by_time(rows))


def _enrich_ohlcv_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    closes = [_safe_number(row.get("close")) for row in rows]
    highs = [_safe_number(row.get("high")) for row in rows]
    lows = [_safe_number(row.get("low")) for row in rows]
    volumes = [_safe_number(row.get("volume")) for row in rows]
    ma = {window: _rolling_mean(closes, window) for window in [5, 20, 60, 200]}
    std20 = _rolling_std(closes, 20)
    donchian_high = _rolling_max(highs, 20)
    donchian_low = _rolling_min(lows, 20)
    vwap20 = _vwap(highs, lows, closes, volumes, 20)
    obv = _obv(closes, volumes)
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd = [(fast - slow) if fast is not None and slow is not None else None for fast, slow in zip(ema12, ema26)]
    macd_signal = _ema(macd, 9)
    macd_hist = [(line - signal) if line is not None and signal is not None else None for line, signal in zip(macd, macd_signal)]
    rsi14 = _rsi(closes, 14)
    atr14 = _atr(highs, lows, closes, 14)
    mfi14 = _mfi(highs, lows, closes, volumes, 14)
    cmf20 = _cmf(highs, lows, closes, volumes, 20)

    enriched: List[Dict[str, Any]] = []
    for index, row in enumerate(rows):
        prepared = dict(row)
        for window in [5, 20, 60, 200]:
            prepared[f"ma{window}"] = _round(ma[window][index])
        middle = ma[20][index]
        std = std20[index]
        if middle is not None and std is not None:
            prepared["bb_middle"] = _round(middle)
            prepared["bb_upper"] = _round(middle + 2 * std)
            prepared["bb_lower"] = _round(middle - 2 * std)
        upper = donchian_high[index]
        lower = donchian_low[index]
        if upper is not None and lower is not None:
            prepared["donchian_upper"] = _round(upper)
            prepared["donchian_lower"] = _round(lower)
            prepared["donchian_middle"] = _round((upper + lower) / 2)
        prepared["vwap20"] = _round(vwap20[index])
        prepared["obv"] = _round(obv[index], 0)
        prepared["macd"] = _round(macd[index])
        prepared["macd_signal"] = _round(macd_signal[index])
        prepared["macd_histogram"] = _round(macd_hist[index])
        prepared["rsi14"] = _round(rsi14[index])
        prepared["atr14"] = _round(atr14[index])
        prepared["mfi14"] = _round(mfi14[index])
        prepared["cmf20"] = _round(cmf20[index])
        enriched.append({key: value for key, value in prepared.items() if value is not None})
    return enriched


def _frame_to_value_rows(frame: Any) -> List[Dict[str, Any]]:
    if frame is None or getattr(frame, "empty", False):
        return []
    rows: List[Dict[str, Any]] = []
    for _, row in frame.iterrows():
        value = _safe_number(_row_get(row, "value"))
        if value is None:
            value = _safe_number(_row_get(row, "close"))
        if value is None:
            continue
        rows.append({"time": _date_text(_row_get(row, "date")), "value": value})
    return _sort_rows_by_time(rows)


def _packet_dict(packet: Any) -> Dict[str, Any]:
    if packet is None:
        return {}
    if isinstance(packet, dict):
        return packet
    if hasattr(packet, "model_dump"):
        return packet.model_dump(mode="json")
    if hasattr(packet, "dict"):
        return packet.dict()
    return {}


def _damodaran_rows_from_packet(packet: Any) -> List[Dict[str, Any]]:
    packet_data = _packet_dict(packet)
    l4 = packet_data.get("raw_data", {}).get("L4", {}) if isinstance(packet_data, dict) else {}
    item = l4.get("get_damodaran_us_implied_erp", {}) if isinstance(l4, dict) else {}
    value = item.get("value", {}) if isinstance(item, dict) else {}
    monthly = value.get("monthly_series", []) if isinstance(value, dict) else []
    rows: List[Dict[str, Any]] = []
    for row in monthly if isinstance(monthly, list) else []:
        if not isinstance(row, dict):
            continue
        erp = _safe_number(row.get("erp_t12m_adjusted_payout"))
        date = row.get("data_date")
        if erp is None or not date:
            continue
        rows.append(
            {
                "time": str(date),
                "value": erp,
                "erp_t12m_adjusted_payout": erp,
                "erp_t12m_cash_yield": _safe_number(row.get("erp_t12m_cash_yield")),
                "erp_avg_cf_yield_10y": _safe_number(row.get("erp_avg_cf_yield_10y")),
                "erp_net_cash_yield": _safe_number(row.get("erp_net_cash_yield")),
                "expected_return": _safe_number(row.get("expected_return")),
                "us_10y_treasury_rate": _safe_number(row.get("us_10y_treasury_rate")),
            }
        )
    return [{key: value for key, value in row.items() if value is not None} for row in rows]


def _damodaran_meta_from_packet(packet: Any) -> Dict[str, Any]:
    packet_data = _packet_dict(packet)
    l4 = packet_data.get("raw_data", {}).get("L4", {}) if isinstance(packet_data, dict) else {}
    item = l4.get("get_damodaran_us_implied_erp", {}) if isinstance(l4, dict) else {}
    value = item.get("value", {}) if isinstance(item, dict) else {}
    if not isinstance(value, dict):
        return {}
    windows = value.get("damodaran_erp_historical_percentiles", {}).get("windows", {})
    return {
        "current_value": _safe_number(value.get("erp_t12m_adjusted_payout")),
        "data_cutoff_date": value.get("data_date"),
        "damodaran_erp_percentile_5y": _safe_number(value.get("damodaran_erp_percentile_5y")),
        "damodaran_erp_percentile_10y": _safe_number(value.get("damodaran_erp_percentile_10y")),
        "damodaran_erp_historical_percentiles": windows if isinstance(windows, dict) else {},
        "percentile_scope": "Damodaran US implied ERP historical percentile; not NDX PE/PB/Forward PE historical percentile",
    }


def build_chart_time_series_artifact(
    *,
    lookback_days: int = DEFAULT_CHART_LOOKBACK_DAYS,
    effective_date: Optional[str] = None,
    fetcher: Optional[Fetcher] = None,
    supplemental_fetchers: Optional[Dict[str, Fetcher]] = None,
    analysis_packet: Any = None,
    generated_at: Optional[str] = None,
) -> Dict[str, Any]:
    generated_at = generated_at or datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    payload: Dict[str, Any] = {
        "schema_version": "vnext_chart_time_series_v1",
        "generated_at_utc": generated_at,
        "effective_date": effective_date,
        "workbench_modules": WORKBENCH_MODULES,
        "series": {
            "QQQ_OHLCV": {
                "symbol": "QQQ",
                "provider": "yfinance via chart_adapter_v6",
                "source_file": "chart_time_series.json",
                "frequency": "daily",
                "layer": "L5",
                "function_id": "get_qqq_technical_indicators",
                "lookback_days": lookback_days,
                "rows": [],
            }
        },
        "caveats": [
            "This artifact is for native interactive charting and audit alignment. It should not replace L5 indicator interpretation.",
        ],
    }
    try:
        frame = fetcher(lookback_days) if fetcher else _default_fetcher(lookback_days, effective_date=effective_date)
        rows, row_meta = _filter_rows_to_effective_date(_frame_to_rows(frame), effective_date)
        payload["series"]["QQQ_OHLCV"]["rows"] = rows
        payload["series"]["QQQ_OHLCV"].update(row_meta)
    except Exception as exc:  # pragma: no cover - defensive artifact fallback
        payload["series"]["QQQ_OHLCV"]["availability"] = "unavailable"
        payload["series"]["QQQ_OHLCV"]["unavailable_reason"] = str(exc)
    if supplemental_fetchers is None:
        supplemental_fetchers = _default_supplemental_fetchers(effective_date=effective_date) if fetcher is None else {}
    for series_key, series_fetcher in supplemental_fetchers.items():
        meta = dict(SUPPLEMENTAL_SERIES_META.get(series_key, {"label": series_key, "provider": "unknown", "frequency": "mixed"}))
        meta.update({"source_file": "chart_time_series.json", "lookback_days": lookback_days, "rows": []})
        try:
            rows, row_meta = _filter_rows_to_effective_date(_frame_to_value_rows(series_fetcher(lookback_days)), effective_date)
            meta["rows"] = rows
            meta.update(row_meta)
        except Exception as exc:  # pragma: no cover - defensive artifact fallback
            meta["availability"] = "unavailable"
            meta["unavailable_reason"] = str(exc)
        payload["series"][series_key] = meta
    if "VIX" in payload["series"] and "VXN" in payload["series"] and "VXN_VIX_RATIO" not in payload["series"]:
        ratio_rows = _ratio_rows(payload["series"]["VXN"].get("rows", []), payload["series"]["VIX"].get("rows", []))
        payload["series"]["VXN_VIX_RATIO"] = {
            **SUPPLEMENTAL_SERIES_META["VXN_VIX_RATIO"],
            "source_file": "chart_time_series.json",
            "lookback_days": lookback_days,
            "rows": ratio_rows,
        }
    damodaran_rows, damodaran_meta = _filter_rows_to_effective_date(_damodaran_rows_from_packet(analysis_packet), effective_date)
    damodaran_value_meta = _damodaran_meta_from_packet(analysis_packet)
    payload["series"]["DAMODARAN_ERP_MONTHLY"] = {
        "label": "Damodaran ERP",
        "provider": "Damodaran ERPbymonth.xlsx",
        "source_file": "analysis_packet.json",
        "frequency": "monthly",
        "layer": "L4",
        "function_id": "get_damodaran_us_implied_erp",
        "rows": damodaran_rows,
        **damodaran_value_meta,
        **damodaran_meta,
    }
    return payload


def _ratio_rows(numerator_rows: List[Dict[str, Any]], denominator_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    denominator = {row.get("time"): _safe_number(row.get("value")) for row in denominator_rows if isinstance(row, dict)}
    rows: List[Dict[str, Any]] = []
    for row in numerator_rows:
        if not isinstance(row, dict):
            continue
        time_key = row.get("time")
        numerator = _safe_number(row.get("value"))
        divisor = denominator.get(time_key)
        if numerator is None or divisor in (None, 0):
            continue
        rows.append({"time": str(time_key), "value": round(numerator / divisor, 4)})
    return rows


def _default_supplemental_fetchers(effective_date: Optional[str] = None) -> Dict[str, Fetcher]:
    try:
        from tools_common import _fetch_yf_history, get_fred_series
        from tools_L1 import _build_net_liquidity_series
    except ImportError:
        try:
            from .tools_common import _fetch_yf_history, get_fred_series
            from .tools_L1 import _build_net_liquidity_series
        except Exception:
            return {}

    def fred(series_id: str) -> Fetcher:
        def _fetch(lookback_days: int) -> Any:
            frame = get_fred_series(series_id, days=max(lookback_days * 2, 800), end_date=effective_date)
            return frame if frame is not None else []

        return _fetch

    def yf_series(ticker: str) -> Fetcher:
        return lambda lookback_days: _fetch_yf_history(ticker, end_date=effective_date)

    def ndx_ndxe(_lookback_days: int) -> Any:
        try:
            from tools_common import align_and_calculate_ratio
        except ImportError:
            from .tools_common import align_and_calculate_ratio
        ndx = _fetch_yf_history("^NDX", end_date=effective_date)
        ndxe = _fetch_yf_history("^NDXE", end_date=effective_date)
        if ndx.empty or ndxe.empty:
            return []
        return align_and_calculate_ratio(ndx, ndxe).rename(columns={"ratio": "value"})[["date", "value"]]

    def net_component(name: str) -> Fetcher:
        def _fetch(_lookback_days: int) -> Any:
            net_df, walcl, tga, rrp = _build_net_liquidity_series()
            if name == "NET_LIQUIDITY":
                return net_df
            selected = {"WALCL": walcl, "TGA": tga, "RRP": rrp}[name]
            return selected.reset_index().rename(columns={"index": "date", selected.name or "value": "value"})

        return _fetch

    def m2_yoy(lookback_days: int) -> Any:
        frame = get_fred_series("M2SL", days=max(lookback_days + 500, 900), end_date=effective_date)
        if frame is None or getattr(frame, "empty", False):
            return []
        frame = frame.copy()
        frame["value"] = frame["value"].pct_change(12) * 100
        return frame.dropna(subset=["value"])[["date", "value"]]

    def hy_quality_spread(lookback_days: int) -> Any:
        ccc = get_fred_series("BAMLH0A3HYC", days=lookback_days, end_date=effective_date)
        bb = get_fred_series("BAMLH0A1HYBB", days=lookback_days, end_date=effective_date)
        if ccc is None or bb is None or getattr(ccc, "empty", False) or getattr(bb, "empty", False):
            return []
        aligned = ccc[["date", "value"]].rename(columns={"value": "ccc_oas"}).merge(
            bb[["date", "value"]].rename(columns={"value": "bb_oas"}),
            on="date",
            how="inner",
        )
        aligned["value"] = aligned["ccc_oas"] - aligned["bb_oas"]
        return aligned[["date", "value"]]

    return {
        "VIX": yf_series("^VIX"),
        "VXN": yf_series("^VXN"),
        "HY_OAS": fred("BAMLH0A0HYM2"),
        "IG_OAS": fred("BAMLC0A0CM"),
        "HY_QUALITY_SPREAD": hy_quality_spread,
        "HYG": yf_series("HYG"),
        "US10Y": fred("DGS10"),
        "US10Y_REAL": fred("DFII10"),
        "US10Y_BREAKEVEN": fred("T10YIE"),
        "FED_FUNDS": fred("FEDFUNDS"),
        "NDX_NDXE_RATIO": ndx_ndxe,
        "NET_LIQUIDITY": net_component("NET_LIQUIDITY"),
        "WALCL": net_component("WALCL"),
        "TGA": net_component("TGA"),
        "RRP": net_component("RRP"),
        "M2_YOY": m2_yoy,
    }


def write_chart_time_series_artifact(
    run_dir: str | Path,
    *,
    lookback_days: int = DEFAULT_CHART_LOOKBACK_DAYS,
    effective_date: Optional[str] = None,
    fetcher: Optional[Fetcher] = None,
    supplemental_fetchers: Optional[Dict[str, Fetcher]] = None,
    analysis_packet: Any = None,
    generated_at: Optional[str] = None,
) -> str:
    path = Path(run_dir) / "chart_time_series.json"
    payload = build_chart_time_series_artifact(
        lookback_days=lookback_days,
        effective_date=effective_date,
        fetcher=fetcher,
        supplemental_fetchers=supplemental_fetchers,
        analysis_packet=analysis_packet,
        generated_at=generated_at,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(path)
