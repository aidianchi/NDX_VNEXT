# tools_L2.py
# -*- coding: utf-8 -*-
"""
NDX Agent · 第2层数据获取函数
"""

try:
    from .tools_common import *
except ImportError:
    from tools_common import *

from datetime import date, datetime, timedelta, timezone
from io import BytesIO
from copy import deepcopy
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple

try:
    from .tools_common import _fetch_yf_history
    from .tools_L1 import (
        _attach_recompute_value_series,
        _fred_unavailable_payload,
        _get_series_for_effective_date,
    )
    from .tools_L3 import (
        _attach_recompute_value_series as _attach_breadth_recompute_value_series,
    )
    from .data_evidence import build_data_quality
except ImportError:
    from tools_common import _fetch_yf_history
    from tools_L1 import (
        _attach_recompute_value_series,
        _fred_unavailable_payload,
        _get_series_for_effective_date,
    )
    from tools_L3 import (
        _attach_recompute_value_series as _attach_breadth_recompute_value_series,
    )
    from data_evidence import build_data_quality


# =====================================================
# 第2层函数
# =====================================================

_VOL_LEVEL_CACHE = {}


def _get_yf_series_with_analysis(
    ticker: str,
    name: str,
    end_date: Optional[str] = None,
    use_ma20_trend: bool = False,
    *,
    auto_adjust: bool = False,
) -> Dict[str, Any]:
    """
    (内部函数) 使用yfinance获取时间序列数据。use_ma20_trend=True 时（如 VIX/VXN）
    输出 spot_over_ma20_ratio 替代日度动量，用于分层降噪。
    """
    if not YF_AVAILABLE:
        return {"name": name, "value": None, "notes": "yfinance library not available."}

    try:
        if end_date:
            effective_date = datetime.strptime(end_date, "%Y-%m-%d")
        else:
            effective_date = datetime.now()

        request_end_date = effective_date + timedelta(days=1)
        # 获取至少10年的历史数据，用于计算10年百分位
        request_start_date = effective_date - timedelta(days=365 * 11)

        df = cached_yf_download(
            ticker,
            start=request_start_date.strftime("%Y-%m-%d"),
            end=request_end_date.strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=auto_adjust
        )
        
        if df.empty:
             raise ValueError(f"yfinance returned an empty DataFrame for {ticker}.")
        
        df = clean_yfinance_dataframe(df)
        df.index = pd.to_datetime(df.index)
        df = df[df.index.date <= effective_date.date()]
        
        if df.empty:
            raise ValueError(f"No data available on or before {effective_date.date()}")

        # 移除 tail(365) 限制，保留全部历史数据用于百分位计算 
        if len(df) < 3:
             raise ValueError(f"Insufficient data points ({len(df)}) for analysis.")
        
        series_for_analysis = df.rename(columns={'close': 'value'})

        if use_ma20_trend and len(df) >= 20:
            level = float(df["close"].iloc[-1])
            ma20 = float(df["close"].rolling(20, min_periods=20).mean().iloc[-1])
            
            # 【修复】：正确处理 reset_index() 后的列名
            stats_df = series_for_analysis.reset_index()
            if "index" in stats_df.columns:
                stats_df = stats_df.rename(columns={"index": "date"})
            elif "Date" in stats_df.columns:
                stats_df = stats_df.rename(columns={"Date": "date"})
            # 确保有 date 列
            if "date" not in stats_df.columns:
                stats_df["date"] = stats_df.index
            
            stats = calculate_long_term_stats(stats_df[["date", "value"]], level)
            analysis = {
                "level": round(level, 4),
                "date": df.index[-1].strftime("%Y-%m-%d"),
                "spot_over_ma20_ratio": round(level / ma20, 4) if ma20 > 0 else None,
                "ma20": round(ma20, 4),
                "historical_stats": stats,
            }
        else:
            analysis = analyze_series_momentum_relativity(series_for_analysis)
        if not analysis or analysis.get("level") is None:
            raise ValueError("Analysis function returned empty results.")

        return _attach_recompute_value_series({
            "name": name, "series_id": ticker, "value": analysis,
            "unit": "level", "source_name": "yfinance",
            "notes": f"Successfully fetched data as of {analysis['date']}." + (" 分层降噪：Spot/MA20。" if use_ma20_trend else "")
        }, stats_df[["date", "value"]] if use_ma20_trend and len(df) >= 20 else series_for_analysis)
    except Exception as e:
        error_note = f"Failed to get {ticker} data: {str(e)}"
        logging.warning(f"  - {name}: {error_note}")
        return {
            "name": name, "series_id": ticker, "value": None,
            "notes": error_note
        }


def _vix_payload_from_frame(vix_df: pd.DataFrame, *, source_name: str) -> Optional[Dict[str, Any]]:
    if vix_df is None or vix_df.empty or len(vix_df) < 3:
        return None
    latest_row = vix_df.iloc[-1]
    latest_level = float(latest_row["value"])
    latest_date_str = latest_row["date"].strftime("%Y-%m-%d")
    historical_stats = calculate_long_term_stats(vix_df[["date", "value"]], latest_level)
    value_out = {"level": round(latest_level, 4), "historical_stats": historical_stats, "date": latest_date_str}
    if len(vix_df) >= 20:
        vix_s = vix_df.set_index("date")["value"].sort_index()
        ma20 = float(vix_s.rolling(20, min_periods=20).mean().iloc[-1])
        value_out["spot_over_ma20_ratio"] = round(latest_level / ma20, 4) if ma20 > 0 else None
        value_out["ma20"] = round(ma20, 4)
    return _attach_recompute_value_series({
        "name": "VIX Index",
        "series_id": "^VIX",
        "value": value_out,
        "unit": "index level",
        "source_name": source_name,
        "notes": "VIX 恐慌指数；分层降噪：现值 + 趋势比(Spot/MA20)。",
    }, vix_df[["date", "value"]])


def get_vix(end_date: str = None) -> Dict[str, Any]:
    """获取VIX恐慌指数，使用持久化缓存并返回历史统计。V5.8修复版：增强错误处理和Alpha Vantage备用。"""
    if not end_date and "VIX" in _VOL_LEVEL_CACHE:
        return deepcopy(_VOL_LEVEL_CACHE["VIX"])
    if not YF_AVAILABLE:
        logging.warning("yfinance 不可用，尝试 Alpha Vantage 备用方案")
        return _get_vix_from_alphavantage(end_date=end_date)

    # 尝试使用 TimeSeriesManager 获取数据
    try:
        vix_df = _get_series_for_effective_date("VIX", _fetch_vix_history, end_date)
        if not vix_df.empty:
            if end_date:
                effective_date = datetime.strptime(end_date, "%Y-%m-%d")
                vix_df = vix_df[vix_df["date"] <= effective_date]
            payload = _vix_payload_from_frame(
                vix_df,
                source_name="yfinance (cached historical)" if end_date else "yfinance (cached)",
            )
            if payload:
                logging.info(f"成功从缓存获取 VIX 数据: {payload['value']['level']} (日期: {payload['value']['date']})")
                if not end_date:
                    _VOL_LEVEL_CACHE["VIX"] = deepcopy(payload)
                return payload
    except Exception as e:
        logging.warning(f"TimeSeriesManager 获取 VIX 数据失败: {e}，尝试直接获取")

    # 回退到直接使用 yfinance 获取数据（分层降噪：Spot/MA20）
    result = _get_yf_series_with_analysis(ticker="^VIX", name="VIX Index", end_date=end_date, use_ma20_trend=True)
    
    # 如果yfinance也失败，尝试Alpha Vantage
    if result.get("value") is None:
        logging.warning("yfinance 直接获取 VIX 失败，尝试 Alpha Vantage 备用方案")
        result = _get_vix_from_alphavantage(end_date=end_date)
        if not end_date and result.get("value") is not None:
            _VOL_LEVEL_CACHE["VIX"] = deepcopy(result)
        return result
    
    if not end_date:
        _VOL_LEVEL_CACHE["VIX"] = deepcopy(result)
    return result


def _get_vix_from_alphavantage(end_date: str = None) -> Dict[str, Any]:
    """Alpha Vantage备用方案获取VIX数据"""
    alphavantage_api_key = get_alphavantage_api_key()
    if not alphavantage_api_key:
        return {
            "name": "VIX Index",
            "value": None,
            "notes": "yfinance 和 Alpha Vantage 均不可用"
        }
    
    try:
        effective_date = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()
        params = {
            "function": "TIME_SERIES_DAILY",
            "symbol": "VIX",
            "apikey": alphavantage_api_key,
            "outputsize": "full"
        }
        data = safe_request(get_alphavantage_base_url(), params)
        if not data or "Time Series (Daily)" not in data:
            raise Exception("Alpha Vantage 无有效 VIX 数据")
        
        df = pd.DataFrame.from_dict(data["Time Series (Daily)"], orient="index")
        df.index = pd.to_datetime(df.index)
        df = df.sort_index()
        df = df[df.index <= effective_date]
        df = df.rename(columns={"4. close": "value"})
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna(subset=["value"])
        
        if len(df) < 3:
            raise Exception("Alpha Vantage VIX 数据不足")
        
        latest_level = float(df["value"].iloc[-1])
        latest_date_str = df.index[-1].strftime("%Y-%m-%d")
        df_for_stats = df.reset_index().rename(columns={"index": "date"})[["date", "value"]]
        historical_stats = calculate_long_term_stats(df_for_stats, latest_level)
        
        value_out = {"level": round(latest_level, 4), "historical_stats": historical_stats, "date": latest_date_str}
        if len(df) >= 20:
            ma20 = float(df["value"].rolling(20, min_periods=20).mean().iloc[-1])
            value_out["spot_over_ma20_ratio"] = round(latest_level / ma20, 4) if ma20 > 0 else None
            value_out["ma20"] = round(ma20, 4)
        
        logging.info(f"成功从 Alpha Vantage 获取 VIX 数据: {latest_level}")
        return _attach_recompute_value_series({
            "name": "VIX Index",
            "series_id": "VIX",
            "value": value_out,
            "unit": "index level",
            "source_name": "Alpha Vantage (fallback)",
            "notes": "VIX 恐慌指数（Alpha Vantage备用）；分层降噪：现值 + 趋势比(Spot/MA20)。"
        }, df_for_stats)
    except Exception as e:
        logging.error(f"Alpha Vantage 获取 VIX 失败: {str(e)}")
        return {
            "name": "VIX Index",
            "value": None,
            "notes": f"所有数据源均失败: {str(e)[:100]}"
        }


def get_vxn(end_date: str = None) -> Dict[str, Any]:
    """获取VXN纳指恐慌指数。分层降噪：现值 + 趋势比(Spot/MA20)。V5.8修复版：增强错误处理。"""
    if not end_date and "VXN" in _VOL_LEVEL_CACHE:
        return deepcopy(_VOL_LEVEL_CACHE["VXN"])
    result = _get_yf_series_with_analysis(ticker="^VXN", name="VXN Index", end_date=end_date, use_ma20_trend=True)
    
    # 如果yfinance失败，记录详细错误
    if result.get("value") is None:
        logging.error(f"VXN 获取失败: {result.get('notes', 'Unknown error')}")
    elif not end_date:
        _VOL_LEVEL_CACHE["VXN"] = deepcopy(result)
    
    return result


def get_vxn_vix_ratio(end_date: str = None) -> Dict[str, Any]:
    """计算VXN/VIX比率 (仅水平)"""
    vxn_data = get_vxn(end_date=end_date)
    vix_data = get_vix(end_date=end_date)
    ratio, date = None, None
    vxn_value = vxn_data.get("value") if isinstance(vxn_data, dict) else None
    vix_value = vix_data.get("value") if isinstance(vix_data, dict) else None
    vxn_level = vxn_value.get("level") if isinstance(vxn_value, dict) else None
    vix_level = vix_value.get("level") if isinstance(vix_value, dict) else None

    if vxn_level and vix_level:
        ratio = round(vxn_level / vix_level, 4)
        date = max(vxn_value.get("date"), vix_value.get("date"))

    if ratio is None:
        return {
            "name": "VXN/VIX Ratio",
            "value": None,
            "unit": "ratio",
            "notes": f"Calculated from latest levels unavailable: VXN={vxn_level}, VIX={vix_level}",
        }

    return {
        "name": "VXN/VIX Ratio", "value": {"level": ratio, "date": date}, "unit": "ratio",
        "notes": f"Calculated from latest levels: VXN={vxn_level}, VIX={vix_level}"
    }


# ---------------------------------------------------------------------------
# VIX term structure (added for investigation_reports/20260711_first_principles/
# WORK_ORDERS.md item 4, task A: RESEARCH_CANON already carried a judgment card
# for "VIX 期限结构与 VRP" -- this implements it. Same L2 risk-appetite/vol
# family as get_vix/get_vxn/get_vxn_vix_ratio above, so it lives next to them.
# ---------------------------------------------------------------------------

VIX_TERM_STRUCTURE_FLAT_BAND = 0.005
"""Half-width of the ratio band around 1.0 treated as neither contango nor
backwardation. A bare ratio==1.0 threshold would flip state on sub-percent
daily noise; 0.5% keeps the state label stable while still being far tighter
than a real term-structure inversion (historically several percent)."""

VIX_TERM_STRUCTURE_PERCENTILE_WINDOWS = {
    # ^VIX3M inception is 2006-07-17, so both windows have full coverage for
    # any effective_date from the mid-2010s onward; requirements are set
    # loose enough to still emit an honest "insufficient_history" status for
    # backtests anchored earlier than that, mirroring
    # HISTORY_OF_MARKET_PERCENTILE_REQUIREMENTS's min_observations/min_span_days
    # pattern in tools_L4.py rather than inventing a new convention.
    "5y": {"years": 5, "min_observations": 750, "min_span_days": 365 * 4},
    "10y": {"years": 10, "min_observations": 1500, "min_span_days": 365 * 8},
}


def _fetch_vix3m_history(start_date: Optional[Any] = None, end_date: Optional[Any] = None) -> pd.DataFrame:
    """原子化获取 VIX3M（3个月隐含波动率）日频历史。"""
    return _fetch_yf_history("^VIX3M", start_date=start_date, end_date=end_date)


def _fetch_vix6m_history(start_date: Optional[Any] = None, end_date: Optional[Any] = None) -> pd.DataFrame:
    """原子化获取 VIX6M（6个月隐含波动率）日频历史，仅作补充观察腿。"""
    return _fetch_yf_history("^VIX6M", start_date=start_date, end_date=end_date)


def _vix_term_structure_state(ratio: Optional[float]) -> str:
    """contango/backwardation/flat classification with a documented flat band."""
    if ratio is None:
        return "unavailable"
    if ratio >= 1.0 + VIX_TERM_STRUCTURE_FLAT_BAND:
        return "contango"
    if ratio <= 1.0 - VIX_TERM_STRUCTURE_FLAT_BAND:
        return "backwardation"
    return "flat"


def _rank_percentile_0_100(values: List[Any], current: float) -> Optional[float]:
    """count(v<=current)/n*100, rounded to 1dp -- same convention already used
    by the Damodaran ERP and Wind PE percentile payloads elsewhere in this
    codebase, so the independent recompute belt can check this one the same
    way (see recompute_belt.check_vix_term_structure_percentile)."""
    clean = [
        float(v) for v in values
        if isinstance(v, (int, float)) and not isinstance(v, bool) and not (isinstance(v, float) and np.isnan(v))
    ]
    if not clean:
        return None
    count = sum(1 for v in clean if v <= current)
    return round(count / len(clean) * 100.0, 1)


def _vix_term_structure_percentile_window(
    merged: pd.DataFrame,
    *,
    anchor: Any,
    years: int,
    current_value: float,
    min_observations: int,
    min_span_days: int,
) -> Dict[str, Any]:
    window_start_ts = anchor - pd.DateOffset(years=years)
    windowed = merged[(merged["date"] >= window_start_ts) & (merged["date"] <= anchor)]
    sample_count = int(len(windowed))
    window_start = windowed["date"].min().strftime("%Y-%m-%d") if sample_count else None
    window_end = windowed["date"].max().strftime("%Y-%m-%d") if sample_count else None
    span_days = int((windowed["date"].max() - windowed["date"].min()).days) if sample_count >= 2 else 0
    base = {
        "current_value": round(float(current_value), 4),
        "sample_count": sample_count,
        "required_min_observations": min_observations,
        "span_days": span_days,
        "required_min_span_days": min_span_days,
        "window_start": window_start,
        "window_end": window_end,
    }
    if sample_count < min_observations or span_days < min_span_days:
        base["percentile"] = None
        base["status"] = "insufficient_history"
        base["reason"] = (
            f"requires >= {min_observations} observations and >= {min_span_days} calendar days; "
            f"got {sample_count} observations over {span_days} days"
        )
        return base
    base["percentile"] = _rank_percentile_0_100(windowed["ratio_vix3m_over_vix"].tolist(), current_value)
    base["status"] = "available"
    base["reason"] = ""
    return base


def get_vix_term_structure(end_date: str = None) -> Dict[str, Any]:
    """VIX term structure: VIX3M/VIX ratio, contango/backwardation state, and
    the ratio's own historical percentile (5y/10y). VIX6M/VIX is carried as a
    secondary, non-percentiled informational leg when available.

    Implements RESEARCH_CANON.md's existing "VIX 期限结构与 VRP" judgment card
    (投资 investigation_reports/20260711_first_principles/WORK_ORDERS.md item 4,
    task A). Same L2 risk-appetite/volatility family as get_vix/get_vxn -- see
    core.collector.DataCollector.LAYER_FUNCTIONS[2].

    Judgment boundary (per RESEARCH_CANON, enforced via
    value["state_usage_boundary"] and data_quality["metric_authority"]):
    backwardation (VIX3M < VIX) is a panic/risk confirmation-or-alert signal;
    contango is the normal default shape and must NOT be cited as bullish
    evidence -- it only means no extra near-term panic premium is priced in.

    Point-in-time: both legs are fetched through the same
    _get_series_for_effective_date/_fetch_yf_history path get_vix already
    uses, so a backtest end_date only ever sees data on or before that date.
    The raw aligned ratio series (up to 10y, bounded by ^VIX3M's 2006-07-17
    inception) is embedded under value.percentile_context.raw_series so
    src/recompute_belt.py can independently recompute the published
    percentile rather than trusting the stored conclusion number.
    """
    effective_date = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()
    date_str = effective_date.strftime("%Y-%m-%d")
    source_name = "yfinance (^VIX / ^VIX3M / ^VIX6M)"
    source_url = "https://finance.yahoo.com/quote/%5EVIX3M/"

    def _unavailable(reason: str) -> Dict[str, Any]:
        return {
            "name": "VIX Term Structure (VIX3M/VIX)",
            "series_id": "VIX_TERM_STRUCTURE",
            "value": None,
            "unit": "ratio",
            "date": date_str,
            "source_tier": "unavailable",
            "source_name": source_name,
            "availability": "unavailable",
            "unavailable_reason": reason,
            "notes": f"VIX term structure unavailable: {reason}",
        }

    try:
        vix_df = _get_series_for_effective_date("VIX", _fetch_vix_history, end_date)
        vix3m_df = _get_series_for_effective_date("VIX3M", _fetch_vix3m_history, end_date)
        vix6m_df = _get_series_for_effective_date("VIX6M", _fetch_vix6m_history, end_date)

        if vix_df is None or vix_df.empty or vix3m_df is None or vix3m_df.empty:
            return _unavailable("missing_vix_or_vix3m_history")

        if end_date:
            anchor_ts = pd.to_datetime(end_date)
            vix_df = vix_df[vix_df["date"] <= anchor_ts]
            vix3m_df = vix3m_df[vix3m_df["date"] <= anchor_ts]
            if vix6m_df is not None and not vix6m_df.empty:
                vix6m_df = vix6m_df[vix6m_df["date"] <= anchor_ts]

        merged = pd.merge(
            vix_df[["date", "value"]].rename(columns={"value": "vix"}),
            vix3m_df[["date", "value"]].rename(columns={"value": "vix3m"}),
            on="date",
            how="inner",
        ).dropna(subset=["vix", "vix3m"])
        merged = merged[merged["vix"] > 0]
        if merged.empty:
            return _unavailable("no_overlapping_vix_vix3m_trading_dates")
        merged["ratio_vix3m_over_vix"] = merged["vix3m"] / merged["vix"]
        merged = merged.sort_values("date").reset_index(drop=True)

        latest = merged.iloc[-1]
        anchor = latest["date"]
        current_ratio = float(latest["ratio_vix3m_over_vix"])
        current_vix = float(latest["vix"])
        current_vix3m = float(latest["vix3m"])
        current_date_str = anchor.strftime("%Y-%m-%d")

        windows = {
            window_key: _vix_term_structure_percentile_window(
                merged,
                anchor=anchor,
                years=spec["years"],
                current_value=current_ratio,
                min_observations=spec["min_observations"],
                min_span_days=spec["min_span_days"],
            )
            for window_key, spec in VIX_TERM_STRUCTURE_PERCENTILE_WINDOWS.items()
        }

        raw_series_cutoff = anchor - pd.DateOffset(years=10)
        raw_series = [
            {
                "data_date": row["date"].strftime("%Y-%m-%d"),
                "vix": round(float(row["vix"]), 4),
                "vix3m": round(float(row["vix3m"]), 4),
                "ratio_vix3m_over_vix": round(float(row["ratio_vix3m_over_vix"]), 4),
            }
            for _, row in merged[merged["date"] >= raw_series_cutoff].iterrows()
        ]

        vix6m_block: Dict[str, Any] = {
            "availability": "unavailable",
            "reason": "no_vix6m_data_available",
        }
        if vix6m_df is not None and not vix6m_df.empty:
            vix6m_on_date = vix6m_df[vix6m_df["date"] == anchor]
            if not vix6m_on_date.empty:
                vix6m_level = float(vix6m_on_date["value"].iloc[0])
                ratio6 = round(vix6m_level / current_vix, 4) if current_vix else None
                vix6m_block = {
                    "availability": "available",
                    "level": round(vix6m_level, 4),
                    "date": current_date_str,
                    "ratio_vix6m_over_vix": ratio6,
                    "term_structure_state_vix6m_over_vix": _vix_term_structure_state(ratio6),
                    "usage": "supplementary_only",
                    "note": (
                        "VIX6M/VIX 只作长端期限结构补充观察；主判读以 VIX3M/VIX 为准，"
                        "未对该腿做独立历史分位。"
                    ),
                }
            else:
                vix6m_block["reason"] = "no_vix6m_observation_on_latest_common_vix_vix3m_date"

        state = _vix_term_structure_state(current_ratio)
        percentile_5y = windows.get("5y", {}).get("percentile")
        percentile_10y = windows.get("10y", {}).get("percentile")

        value = {
            "date": current_date_str,
            "level": round(current_ratio, 4),
            "vix": {"level": round(current_vix, 4), "date": current_date_str},
            "vix3m": {"level": round(current_vix3m, 4), "date": current_date_str},
            "vix6m": vix6m_block,
            "ratio_vix3m_over_vix": round(current_ratio, 4),
            "term_structure_state": state,
            "state_thresholds": {
                "contango_at_or_above": round(1.0 + VIX_TERM_STRUCTURE_FLAT_BAND, 4),
                "backwardation_at_or_below": round(1.0 - VIX_TERM_STRUCTURE_FLAT_BAND, 4),
                "flat_band_half_width": VIX_TERM_STRUCTURE_FLAT_BAND,
                "note": "±0.5% 缓冲带内视为 flat，避免比值贴近 1.0 时的噪音导致状态频繁跳变。",
            },
            "percentile_5y": percentile_5y,
            "percentile_10y": percentile_10y,
            "percentile_context": {
                "primary_field": "ratio_vix3m_over_vix",
                "method": "count(v<=current)/n*100；与 Damodaran ERP / Wind PE 历史分位算法口径一致",
                "windows": windows,
                "raw_series": raw_series,
                "raw_series_window_note": (
                    "raw_series 覆盖至多10年（受 ^VIX3M 2006-07-17 上市日与 effective_date 双重约束），"
                    "足以独立重算 windows.5y / windows.10y 两个分位。"
                ),
            },
            "state_usage_boundary": {
                "backwardation": {
                    "usage": "supporting_only",
                    "role": "risk_confirmation_or_alert",
                    "reason": (
                        "期限结构倒挂（VIX3M<VIX）是恐慌/风险信号，可作为 L2 风险确认或预警证据之一，"
                        "仍须与 HY OAS/A-D/ATR 等交叉验证，不能单独触发结论。"
                        "按法典 core_vs_tactical_boundary，倒挂可作为战术仓逢恐慌分批布局的确认条件之一"
                        "（仍为 supporting_only，核心仓不因期限结构单独变动仓位）。"
                    ),
                },
                "contango": {
                    "usage": "not_bullish_evidence",
                    "role": "normal_state_baseline",
                    "reason": "正挂是期限结构的常态默认形状，不构成看多证据；只说明近端没有额外恐慌溢价。",
                },
                "flat": {
                    "usage": "not_bullish_evidence",
                    "role": "transition_state",
                    "reason": "比值贴近 1.0 时不携带方向性证据权重。",
                },
            },
            "source_boundary": (
                "VIX term structure 只回答近端相对远端的波动保险费定价关系，不能单独证明估值便宜或市场健康；"
                "期限结构倒挂是恐慌/风险信号，正挂常态不构成看多证据。"
            ),
        }

        data_quality = build_data_quality(
            provider="yfinance",
            source_name=source_name,
            source_url=source_url,
            source_tier="third_party_estimate",
            data_date=current_date_str,
            as_of_date=current_date_str,
            effective_date=date_str,
            vintage_date=current_date_str,
            availability="available",
            fallback_reason="none",
            fallback_chain=["third_party_estimate", "unavailable"],
            license_note="public_endpoint_review_required",
            coverage={
                "primary_window_5y": windows.get("5y", {}),
                "primary_window_10y": windows.get("10y", {}),
                "vix6m_availability": vix6m_block.get("availability"),
                "raw_series_observations": len(raw_series),
            },
            methodology=(
                "ratio_vix3m_over_vix = ^VIX3M close / ^VIX close on the same trading date (inner-joined "
                "by date to avoid holiday/gap misalignment); percentile = count(ratio<=current)/n*100 over "
                "the stated window; state = contango/backwardation/flat via the documented ±0.5% flat band."
            ),
            formula="level = ^VIX3M.close / ^VIX.close",
            anomalies=(["vix6m_unavailable"] if vix6m_block.get("availability") != "available" else []),
        )
        data_quality["metric_authority"] = {
            "term_structure_state": {
                "source": "third_party_estimate",
                "usage": "supporting_only",
                "authority": "asymmetric_risk_signal_only",
                "reason": (
                    "backwardation 可支持风险/恐慌确认或预警（仍需交叉验证）；contango/flat 不得被引用为看多证据，"
                    "只说明近端没有额外恐慌溢价——与 RESEARCH_CANON 的 VIX 期限结构判读边界一致。"
                ),
                "reference_sources": [],
            },
            "percentile_context": {
                "source": "third_party_estimate",
                "usage": "supporting_only",
                "authority": "derived_from_yfinance_daily_closes",
                "reason": "历史分位基于 yfinance ^VIX/^VIX3M 每日收盘计算，不是 Cboe 官方期限结构分位；仅作确认/预警强度参考。",
                "reference_sources": [],
            },
            # T36：真实顶层键是 "vix6m"（曾登记为分组名 vix6m_leg，对不上 value 里
            # 的真实字段名）。
            "vix6m": {
                "source": "third_party_estimate",
                "usage": "supplementary_only",
                "authority": "secondary_confirmation_leg_no_percentile",
                "reason": "VIX6M/VIX 只作长端期限结构补充观察，未做独立历史分位，不得单独驱动结论。",
                "reference_sources": [],
            },
        }

        return {
            "name": "VIX Term Structure (VIX3M/VIX)",
            "series_id": "VIX_TERM_STRUCTURE",
            "value": value,
            "unit": "ratio",
            "date": current_date_str,
            "source_tier": "third_party_estimate",
            "source_name": source_name,
            "source_url": source_url,
            "availability": "available",
            "data_quality": data_quality,
            "notes": "VIX 期限结构：VIX3M/VIX 比值 + contango/backwardation 状态 + 历史分位；VIX6M 作补充观察腿。",
        }
    except Exception as exc:
        return _unavailable(f"vix_term_structure_exception: {str(exc)[:150]}")


def get_hy_oas_bp(end_date: str = None) -> Dict[str, Any]:
    """获取高收益企业债OAS。分层降噪：用 MA5 vs MA20 趋势替代日度动量。"""
    series = get_fred_series("BAMLH0A0HYM2", end_date=end_date)
    if series is None or len(series) < 20:
        return _fred_unavailable_payload(
            name="High Yield OAS",
            series_id="BAMLH0A0HYM2",
            unit="percent",
            minimum_points=20,
            series=series,
            calculation="ma5_ma20_trend",
        )
    analysis = analyze_series_ma_trend(series, short_period=5, long_period=20)
    stats = calculate_long_term_stats(series[["date", "value"]], analysis["level"])
    analysis["relativity"] = stats
    return _attach_recompute_value_series({
        "name": "High Yield OAS", "series_id": "BAMLH0A0HYM2", "value": analysis,
        "unit": "percent", "source_name": "FRED",
        "notes": (
            "ICE BofA US High Yield OAS；分层降噪：MA5 vs MA20 趋势方向。"
            "注：函数名含 _bp 系历史命名，数值与 unit 字段以 percent 为准（如 2.71 即 2.71%≈271bp）。"
        )
    }, series[["date", "value"]])


def get_ig_oas_bp(end_date: str = None) -> Dict[str, Any]:
    """获取投资级企业债OAS。分层降噪：用 MA5 vs MA20 趋势替代日度动量。"""
    series = get_fred_series("BAMLC0A0CM", end_date=end_date)
    if series is None or len(series) < 20:
        return _fred_unavailable_payload(
            name="Investment Grade OAS",
            series_id="BAMLC0A0CM",
            unit="percent",
            minimum_points=20,
            series=series,
            calculation="ma5_ma20_trend",
        )
    analysis = analyze_series_ma_trend(series, short_period=5, long_period=20)
    stats = calculate_long_term_stats(series[["date", "value"]], analysis["level"])
    analysis["relativity"] = stats
    return _attach_recompute_value_series({
        "name": "Investment Grade OAS", "series_id": "BAMLC0A0CM", "value": analysis,
        "unit": "percent", "source_name": "FRED",
        "notes": (
            "ICE BofA US Corporate OAS；分层降噪：MA5 vs MA20 趋势方向。"
            "注：函数名含 _bp 系历史命名，数值与 unit 字段以 percent 为准（如 1.20 即 1.20%≈120bp）。"
        )
    }, series[["date", "value"]])


def _fetch_vix_history(start_date: Optional[Any] = None, end_date: Optional[Any] = None) -> pd.DataFrame:
    """原子化获取 VIX 日频历史。"""
    return _fetch_yf_history("^VIX", start_date=start_date, end_date=end_date)


def _fetch_xly_history(start_date: Optional[Any] = None, end_date: Optional[Any] = None) -> pd.DataFrame:
    """原子化获取 XLY 日频历史。"""
    return _fetch_yf_history("XLY", start_date=start_date, end_date=end_date)


def _fetch_xlp_history(start_date: Optional[Any] = None, end_date: Optional[Any] = None) -> pd.DataFrame:
    """原子化获取 XLP 日频历史。"""
    return _fetch_yf_history("XLP", start_date=start_date, end_date=end_date)


def get_hyg_momentum(end_date: str = None) -> Dict[str, Any]:
    """获取高收益公司债ETF(HYG)的价格动量，作为信用利差的实时代理"""
    result = _get_yf_series_with_analysis(
        ticker="HYG",
        name="High Yield Corp Bond (HYG) Adjusted-Price Momentum",
        end_date=end_date,
        auto_adjust=True,
    )
    result["source_tier"] = "proxy"
    result["notes"] = (
        str(result.get("notes") or "")
        + " Uses dividend-adjusted prices so bond ETF distributions do not masquerade as credit deterioration. "
        "This remains a tradable-price proxy; HY OAS is the primary credit-spread measure."
    ).strip()
    return result

# =====================================================
# 第二层：市场内部结构
# =====================================================


def get_xly_xlp_ratio(end_date: str = None) -> Dict[str, Any]:
    """获取非必需消费品ETF(XLY)与必需消费品ETF(XLP)的比率及其动量与相对性。"""
    if not YF_AVAILABLE:
        return {
            "name": "XLY/XLP Ratio",
            "value": None,
            "notes": "yfinance library is not available."
        }

    effective_date = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()

    # 尝试使用 TimeSeriesManager 获取数据
    try:
        xly_df = _get_series_for_effective_date("XLY", _fetch_xly_history, end_date)
        xlp_df = _get_series_for_effective_date("XLP", _fetch_xlp_history, end_date)

        if not xly_df.empty and not xlp_df.empty:
            xly_df = xly_df[xly_df["date"] <= effective_date]
            xlp_df = xlp_df[xlp_df["date"] <= effective_date]

            if not xly_df.empty and not xlp_df.empty:
                ratio_df = align_and_calculate_ratio(
                    numerator_series=xly_df[["date", "value"]],
                    denominator_series=xlp_df[["date", "value"]],
                    date_col="date",
                    value_col="value",
                )

                if not ratio_df.empty:
                    ratio_for_ma = ratio_df[["date", "ratio"]].rename(columns={"ratio": "value"})
                    latest_ratio = float(ratio_df.iloc[-1]["ratio"])
                    latest_date_str = ratio_df.iloc[-1]["date"].strftime("%Y-%m-%d")
                    historical_stats = calculate_long_term_stats(ratio_for_ma, latest_ratio)
                    ma_analysis = analyze_series_ratio_vs_ma(ratio_for_ma, ma_period=20) if len(ratio_df) >= 20 else {}
                    value_out = {
                        "level": round(latest_ratio, 4),
                        "historical_stats": historical_stats,
                        "date": latest_date_str,
                    }
                    if ma_analysis:
                        value_out["position_vs_ma20"] = ma_analysis.get("position_vs_ma")
                        value_out["ma20"] = ma_analysis.get("ma")
                    return _attach_recompute_value_series({
                        "name": "XLY/XLP Ratio",
                        "value": value_out,
                        "unit": "ratio",
                        "source_name": "yfinance (cached)",
                        "notes": "XLY/XLP 风险偏好；分层降噪：比值相对 MA20 位置。"
                    }, ratio_for_ma)
    except Exception as e:
        logging.warning(f"TimeSeriesManager 获取 XLY/XLP 数据失败: {e}")

    # 回退到直接使用 yfinance 获取数据
    # 使用分单标的下载避免 MultiIndex 结构问题及 clean_yfinance_dataframe 破坏 ticker 信息
    try:
        start_date = effective_date - timedelta(days=365 * 11)
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = (effective_date + timedelta(days=1)).strftime("%Y-%m-%d")
        xly_df = cached_yf_download("XLY", start=start_str, end=end_str, progress=False, auto_adjust=False)
        xlp_df = cached_yf_download("XLP", start=start_str, end=end_str, progress=False, auto_adjust=False)
        xly_df = clean_yfinance_dataframe(xly_df)
        xlp_df = clean_yfinance_dataframe(xlp_df)
        if xly_df.empty or "close" not in xly_df.columns:
            raise ValueError("No data returned from yfinance for XLY.")
        if xlp_df.empty or "close" not in xlp_df.columns:
            raise ValueError("No data returned from yfinance for XLP.")
        xly_close = xly_df["close"].rename("xly")
        xlp_close = xlp_df["close"].rename("xlp")
        aligned_df = pd.concat([xly_close, xlp_close], axis=1).dropna()
        aligned_df.columns = ['xly', 'xlp']
        aligned_df['ratio'] = aligned_df['xly'] / aligned_df['xlp']
        
        if len(aligned_df) < 3:
            raise ValueError("Not enough valid data points for XLY/XLP ratio calculation.")
        
        # 转换为标准格式用于分析
        ratio_series = aligned_df[['ratio']].rename(columns={'ratio': 'value'})
        ratio_series.index = pd.to_datetime(ratio_series.index)
        ratio_series = ratio_series[ratio_series.index.date <= effective_date.date()]
        
        if ratio_series.empty:
            raise ValueError("No data available on or before the specified date.")
        
        # 分层降噪：比值相对 MA20 位置，替代日度动量
        ratio_for_analysis = ratio_series.reset_index()
        ratio_for_analysis.columns = ['date', 'value']
        analysis = analyze_series_ratio_vs_ma(ratio_for_analysis, ma_period=20) if len(ratio_for_analysis) >= 20 else {}
        latest_ratio = float(ratio_series.iloc[-1]['value'])
        latest_date_val = ratio_series.index[-1].strftime("%Y-%m-%d")
        stats = calculate_long_term_stats(ratio_for_analysis, latest_ratio)
        value_out = {"level": round(latest_ratio, 4), "date": latest_date_val, "historical_stats": stats}
        if analysis:
            value_out["position_vs_ma20"] = analysis.get("position_vs_ma")
            value_out["ma20"] = analysis.get("ma")

        return _attach_recompute_value_series({
            "name": "XLY/XLP Ratio",
            "value": value_out,
            "unit": "ratio",
            "source_name": "yfinance",
            "notes": f"XLY/XLP 风险偏好；分层降噪：比值相对 MA20 位置。Raw: XLY={aligned_df['xly'].iloc[-1]:.2f}, XLP={aligned_df['xlp'].iloc[-1]:.2f}"
        }, ratio_for_analysis)
    except Exception as e:
        return {
            "name": "XLY/XLP Ratio",
            "value": None,
            "notes": f"Failed to calculate: {str(e)}"
        }


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


def get_hy_quality_spread_bp(end_date: str = None) -> Dict[str, Any]:
    """低质高收益债相对高质高收益债的信用压力差。"""
    ccc_series = get_fred_series("BAMLH0A3HYC", end_date=end_date)
    bb_series = get_fred_series("BAMLH0A1HYBB", end_date=end_date)
    if ccc_series is None or bb_series is None or len(ccc_series) < 20 or len(bb_series) < 20:
        return {
            "name": "HY CCC & Lower minus BB OAS",
            "series_id": "BAMLH0A3HYC-BAMLH0A1HYBB",
            "value": None,
            "unit": "percentage points",
            "source_name": "FRED / ICE BofA",
            "source_tier": "official_provider",
            "notes": "数据不足，无法计算低质高收益债相对 BB 的信用分层压力。",
        }

    ccc = ccc_series[["date", "value"]].rename(columns={"value": "ccc_oas"})
    bb = bb_series[["date", "value"]].rename(columns={"value": "bb_oas"})
    aligned = pd.merge(ccc, bb, on="date", how="inner").dropna()
    if len(aligned) < 20:
        return {
            "name": "HY CCC & Lower minus BB OAS",
            "series_id": "BAMLH0A3HYC-BAMLH0A1HYBB",
            "value": None,
            "unit": "percentage points",
            "source_name": "FRED / ICE BofA",
            "source_tier": "official_provider",
            "notes": "CCC & Lower 和 BB OAS 共同日期不足，无法计算分层利差。",
        }

    spread_series = aligned.copy()
    spread_series["value"] = spread_series["ccc_oas"] - spread_series["bb_oas"]
    analysis = analyze_series_ma_trend(spread_series[["date", "value"]], short_period=5, long_period=20)
    stats = calculate_long_term_stats(spread_series[["date", "value"]], analysis["level"])
    latest = aligned.iloc[-1]
    analysis.update(
        {
            "ccc_oas": round(float(latest["ccc_oas"]), 2),
            "bb_oas": round(float(latest["bb_oas"]), 2),
            "relativity": stats,
        }
    )
    payload = {
        "name": "HY CCC & Lower minus BB OAS",
        "series_id": "BAMLH0A3HYC-BAMLH0A1HYBB",
        "value": analysis,
        "unit": "percentage points",
        "source_name": "FRED / ICE BofA",
        "source_tier": "official_provider",
        "data_quality": {
            "source_tier": "official_provider",
            "data_date": analysis.get("date"),
            "collected_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
            "update_frequency": "daily market close",
            "formula": "ICE BofA CCC & Lower US High Yield OAS minus ICE BofA BB US High Yield OAS",
            "coverage": {
                "series": ["BAMLH0A3HYC", "BAMLH0A1HYBB"],
                "common_observations": int(len(spread_series)),
            },
            "anomalies": [],
            "fallback_chain": ["FRED / ICE BofA", "unavailable"],
            "source_disagreement": {},
        },
        "notes": (
            "低质高收益债相对 BB 的分层压力。FRED 可得口径是 CCC & Lower，"
            "不是精确 CCC+；应与 HY OAS、IG OAS 和 VIX 联合阅读。"
            "注：函数名含 _bp 系历史命名，数值与 unit 字段以 percentage points 为准"
            "（如 8.09 即 8.09 个百分点≈809bp）。"
        ),
    }
    return _attach_breadth_recompute_value_series(payload, spread_series[["date", "value"]])


# =====================================================
# L2 official positioning / leverage context (supporting only)
# =====================================================

CFTC_LEGACY_FUTURES_ONLY_API = "https://publicreporting.cftc.gov/resource/6dca-aqww.json"
CFTC_NQ_CONSOLIDATED_CODE = "20974+"
FINRA_MARGIN_STATISTICS_PAGE = "https://www.finra.org/rules-guidance/key-topics/margin-accounts/margin-statistics"
FINRA_MARGIN_STATISTICS_XLSX = "https://www.finra.org/sites/default/files/2021-03/margin-statistics.xlsx"
OFFICIAL_POSITIONING_RECENT_WINDOW_DAYS = 120


def _official_supporting_rule(reason: str, requires: Optional[List[str]] = None) -> Dict[str, Any]:
    return {
        "usage": "supporting_only",
        "authority": "official_positioning_fact",
        "reason": reason,
        "requires_confirmation": list(requires or []),
    }


CFTC_NQ_METRIC_AUTHORITY = {
    "noncommercial_long_contracts": _official_supporting_rule(
        "Official Legacy futures-only long positions remain partial-market positioning context only."
    ),
    "noncommercial_short_contracts": _official_supporting_rule(
        "Official Legacy futures-only short positions remain partial-market positioning context only."
    ),
    "noncommercial_net_contracts": _official_supporting_rule(
        "Official CFTC Legacy futures-only fact, but it covers only reported Nasdaq-100 futures positions.",
        ["get_crowdedness_dashboard", "get_vxn", "get_advance_decline_line"],
    ),
    "weekly_change_net_contracts": _official_supporting_rule(
        "Week-to-week change in a partial futures universe is not a direction or timing signal.",
        ["get_vxn", "get_advance_decline_line"],
    ),
    "open_interest_contracts": _official_supporting_rule(
        "Official contract open interest provides scale context only."
    ),
    "historical_percentile": _official_supporting_rule(
        "No percentile may be reported before a point-in-time history archive is connected."
    ),
    "leveraged_funds_net_contracts": _official_supporting_rule(
        "Legacy COT has no TFF leveraged-funds category; it must remain unavailable rather than aliasing non-commercial positions."
    ),
}
CFTC_NQ_DOWNGRADE_RULES = [
    "cftc_futures_cover_only_one_part_of_total_market_positioning",
    "legacy_noncommercial_must_not_be_relabelled_as_tff_leveraged_funds",
    "positioning_extreme_cannot_independently_drive_direction_or_timing",
    "historical_percentile_requires_point_in_time_archive",
]

FINRA_MARGIN_METRIC_AUTHORITY = {
    "margin_debt_millions": _official_supporting_rule(
        "Official aggregate FINRA margin debit balance is broad-market, monthly, and lagging.",
        ["get_hy_oas_bp", "get_net_liquidity_momentum", "get_advance_decline_line"],
    ),
    "month_over_month_pct": _official_supporting_rule(
        "One-month change is noisy and publication-lagged; it must not be used for timing."
    ),
    "year_over_year_pct": _official_supporting_rule(
        "Year-over-year direction is leverage-cycle context only.",
        ["get_hy_oas_bp", "get_advance_decline_line"],
    ),
    "cash_account_free_credit_millions": _official_supporting_rule(
        "Official broad-market free-credit balance used only as context."
    ),
    "margin_account_free_credit_millions": _official_supporting_rule(
        "Official broad-market free-credit balance used only as context."
    ),
}
FINRA_MARGIN_DOWNGRADE_RULES = [
    "finra_margin_debt_is_broad_market_not_ndx_specific",
    "monthly_publication_lag_precludes_short_term_timing",
    "nominal_level_high_cannot_be_interpreted_as_market_top",
    "historical_backtest_requires_retained_finra_publication_vintages",
]

FINRA_MARGIN_COLUMNS = {
    "reference_month": "Year-Month",
    "margin_debt": "Debit Balances in Customers' Securities Margin Accounts",
    "cash_credit": "Free Credit Balances in Customers' Cash Accounts",
    "margin_credit": "Free Credit Balances in Customers' Securities Margin Accounts",
}


def _positioning_data_quality(
    *, provider: str, source_name: str, source_url: str, effective_date: str,
    data_date: Optional[str], visible_date: Optional[str], availability: str,
    methodology: str, coverage: Dict[str, Any], metric_authority: Dict[str, Dict[str, Any]],
    downgrade_rules: List[str], anomalies: Optional[List[str]] = None, fallback_reason: str = "",
) -> Dict[str, Any]:
    return {
        "provider": provider,
        "source_name": source_name,
        "source_url": source_url,
        "source_tier": "official",
        "as_of_date": effective_date,
        "effective_date": effective_date,
        "data_date": data_date or "not_available",
        "vintage_date": visible_date,
        "collected_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "availability": availability,
        "fallback_reason": fallback_reason,
        "fallback_chain": [source_name, "unavailable"],
        "license_note": "Official public data; source terms and attribution remain applicable.",
        "coverage": coverage,
        "methodology": methodology,
        "formula": methodology,
        "anomalies": list(anomalies or []),
        "metric_authority": metric_authority,
        "downgrade_rules": downgrade_rules,
    }


def _parse_positioning_effective_date(end_date: Optional[str]) -> Tuple[Optional[date], Optional[str]]:
    text = end_date or date.today().isoformat()
    try:
        return datetime.strptime(text, "%Y-%m-%d").date(), None
    except (TypeError, ValueError):
        return None, f"invalid_effective_date:{text}"


def _recent_positioning_date_error(effective: date) -> Optional[str]:
    today = date.today()
    if effective > today:
        return "effective_date_is_in_the_future"
    if effective < today - timedelta(days=OFFICIAL_POSITIONING_RECENT_WINDOW_DAYS):
        return "historical_pit_archive_not_connected"
    return None


def _cftc_unavailable(effective_date: str, reason: str) -> Dict[str, Any]:
    return {
        "name": "CFTC Nasdaq-100 Futures Positioning",
        "series_id": "CFTC_LEGACY_FUTURES_ONLY_20974+",
        "value": None,
        "unit": "contracts",
        "source_name": "U.S. Commodity Futures Trading Commission",
        "source_tier": "official",
        "source_url": CFTC_LEGACY_FUTURES_ONLY_API,
        "availability": "unavailable",
        "unavailable_reason": reason,
        "data_quality": _positioning_data_quality(
            provider="CFTC Public Reporting Environment", source_name="CFTC Legacy Futures Only",
            source_url=CFTC_LEGACY_FUTURES_ONLY_API, effective_date=effective_date,
            data_date=None, visible_date=None, availability="unavailable",
            methodology="Legacy futures-only non-commercial long minus short for code 20974+; Tuesday snapshot visible no earlier than Friday.",
            coverage={"contract_market_code": CFTC_NQ_CONSOLIDATED_CODE, "scope": "Nasdaq-100 consolidated futures only"},
            metric_authority=CFTC_NQ_METRIC_AUTHORITY, downgrade_rules=CFTC_NQ_DOWNGRADE_RULES,
            anomalies=[reason], fallback_reason=reason,
        ),
        "notes": "Unavailable is retained as a data boundary; no positioning value or percentile is estimated.",
    }


def _fetch_cftc_nq_legacy_rows() -> List[Dict[str, Any]]:
    response = requests.get(
        CFTC_LEGACY_FUTURES_ONLY_API,
        params={
            "$limit": 20,
            "$order": "report_date_as_yyyy_mm_dd DESC",
            "$where": f"cftc_contract_market_code='{CFTC_NQ_CONSOLIDATED_CODE}'",
        },
        headers={"User-Agent": "ndx-vnext/1.0"}, timeout=20, proxies=get_requests_proxies(),
    )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("cftc_response_not_list")
    return [row for row in payload if isinstance(row, dict)]


def _cftc_visible_rows(rows: Iterable[Dict[str, Any]], effective: date) -> List[Dict[str, Any]]:
    parsed: List[Dict[str, Any]] = []
    for row in rows:
        try:
            report_date = pd.to_datetime(row.get("report_date_as_yyyy_mm_dd"), errors="raise").date()
            market_code = str(row.get("cftc_contract_market_code") or "").strip()
            long_positions = float(row.get("noncomm_positions_long_all"))
            short_positions = float(row.get("noncomm_positions_short_all"))
            open_interest = float(row.get("open_interest_all"))
        except (TypeError, ValueError, KeyError):
            continue
        if not all(
            np.isfinite(value) and value >= 0
            for value in (long_positions, short_positions, open_interest)
        ):
            continue
        if market_code != CFTC_NQ_CONSOLIDATED_CODE:
            continue
        visible_date = report_date + timedelta(days=3)
        if visible_date > effective:
            continue
        parsed.append({
            "report_date": report_date,
            "visible_date": visible_date,
            "market_name": str(row.get("market_and_exchange_names") or row.get("contract_market_name") or ""),
            "open_interest": open_interest,
            "noncommercial_long": long_positions,
            "noncommercial_short": short_positions,
            "noncommercial_net": long_positions - short_positions,
        })
    return sorted(parsed, key=lambda item: item["report_date"], reverse=True)


def get_cftc_nq_positioning(end_date: str = None) -> Dict[str, Any]:
    """CFTC Legacy Futures-Only Nasdaq-100 non-commercial positioning."""
    effective, error = _parse_positioning_effective_date(end_date)
    effective_text = end_date or date.today().isoformat()
    if error or effective is None:
        return _cftc_unavailable(effective_text, error or "invalid_effective_date")
    recency_error = _recent_positioning_date_error(effective)
    if recency_error:
        return _cftc_unavailable(effective.isoformat(), recency_error)
    try:
        visible_rows = _cftc_visible_rows(_fetch_cftc_nq_legacy_rows(), effective)
    except Exception as exc:
        return _cftc_unavailable(effective.isoformat(), f"official_source_unavailable:{type(exc).__name__}:{str(exc)[:120]}")
    if not visible_rows:
        return _cftc_unavailable(effective.isoformat(), "no_cftc_snapshot_visible_by_effective_date")
    latest = visible_rows[0]
    previous = visible_rows[1] if len(visible_rows) > 1 else None
    exact_previous_week = bool(
        previous and (latest["report_date"] - previous["report_date"]).days == 7
    )
    weekly_change = (
        latest["noncommercial_net"] - previous["noncommercial_net"]
        if exact_previous_week
        else None
    )
    value = {
        "report_date": latest["report_date"].isoformat(),
        "visible_date": latest["visible_date"].isoformat(),
        "market_name": latest["market_name"],
        "contract_market_code": CFTC_NQ_CONSOLIDATED_CODE,
        "open_interest_contracts": int(latest["open_interest"]),
        "noncommercial_long_contracts": int(latest["noncommercial_long"]),
        "noncommercial_short_contracts": int(latest["noncommercial_short"]),
        "noncommercial_net_contracts": int(latest["noncommercial_net"]),
        "weekly_change_net_contracts": int(weekly_change) if weekly_change is not None else None,
        "weekly_change_status": "available" if exact_previous_week else "unavailable_missing_exact_prior_week",
        "previous_report_date": previous["report_date"].isoformat() if previous else None,
        "leveraged_funds_net_contracts": None,
        "historical_percentile": None,
        "historical_percentile_status": "not_computed_recent_only_no_pit_archive",
        "pit_archive_status": "current_official_api_rows_only_no_retained_publication_vintages",
        "classification_boundary": "Legacy Futures Only reports non-commercial positions; TFF leveraged-funds positions are not present and are not inferred.",
    }
    return {
        "name": "CFTC Nasdaq-100 Futures Positioning",
        "series_id": "CFTC_LEGACY_FUTURES_ONLY_20974+",
        "value": value,
        "unit": "contracts",
        "source_name": "U.S. Commodity Futures Trading Commission",
        "source_tier": "official",
        "source_url": CFTC_LEGACY_FUTURES_ONLY_API,
        "availability": "available",
        "data_quality": _positioning_data_quality(
            provider="CFTC Public Reporting Environment", source_name="CFTC Legacy Futures Only",
            source_url=CFTC_LEGACY_FUTURES_ONLY_API, effective_date=effective.isoformat(),
            data_date=value["report_date"], visible_date=value["visible_date"], availability="available",
            methodology="Legacy futures-only non-commercial long minus short for code 20974+; Tuesday snapshot visible no earlier than Friday.",
            coverage={"contract_market_code": CFTC_NQ_CONSOLIDATED_CODE, "scope": "Nasdaq-100 consolidated futures only", "visible_recent_rows": len(visible_rows), "historical_pit_archive_connected": False},
            metric_authority=CFTC_NQ_METRIC_AUTHORITY, downgrade_rules=CFTC_NQ_DOWNGRADE_RULES,
            anomalies=([] if exact_previous_week else ["exact_prior_week_missing_weekly_change_unavailable"])
            + ["current_api_rows_not_retained_as_publication_vintages"],
        ),
        "notes": "Official weekly futures-position fact with a three-day publication lag; supporting only, partial-market scope, no historical percentile.",
    }


def _finra_unavailable(effective_date: str, reason: str) -> Dict[str, Any]:
    return {
        "name": "FINRA Margin Debt",
        "series_id": "FINRA_CUSTOMER_MARGIN_BALANCES",
        "value": None,
        "unit": "USD millions",
        "source_name": "Financial Industry Regulatory Authority",
        "source_tier": "official",
        "source_url": FINRA_MARGIN_STATISTICS_PAGE,
        "availability": "unavailable",
        "unavailable_reason": reason,
        "data_quality": _positioning_data_quality(
            provider="FINRA", source_name="FINRA Margin Statistics",
            source_url=FINRA_MARGIN_STATISTICS_PAGE, effective_date=effective_date,
            data_date=None, visible_date=None, availability="unavailable",
            methodology="Monthly customer margin balances; conservative estimated visibility is month-end plus 21 calendar days.",
            coverage={"scope": "aggregate FINRA member-firm customer balances", "historical_pit_archive_connected": False},
            metric_authority=FINRA_MARGIN_METRIC_AUTHORITY, downgrade_rules=FINRA_MARGIN_DOWNGRADE_RULES,
            anomalies=[reason], fallback_reason=reason,
        ),
        "notes": "Unavailable is retained as a data boundary; no monthly balance or change is estimated.",
    }


def _fetch_finra_margin_frame() -> pd.DataFrame:
    response = requests.get(
        FINRA_MARGIN_STATISTICS_XLSX,
        headers={"User-Agent": "ndx-vnext/1.0"}, timeout=20, proxies=get_requests_proxies(),
    )
    response.raise_for_status()
    return pd.read_excel(BytesIO(response.content), sheet_name="Customer Margin Balances")


def _finra_reference_month_end(value: Any) -> date:
    if isinstance(value, (pd.Timestamp, datetime, date)):
        parsed = pd.Timestamp(value)
        year, month = int(parsed.year), int(parsed.month)
    elif isinstance(value, str) and re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", value.strip()):
        year, month = (int(part) for part in value.strip().split("-"))
    else:
        raise ValueError("finra_reference_month_must_be_yyyy_mm_or_date")
    if year < 1997:
        raise ValueError("finra_reference_month_before_official_coverage")
    return pd.Period(f"{year:04d}-{month:02d}", freq="M").end_time.date()


def _finra_visible_rows(frame: pd.DataFrame, effective: date) -> List[Dict[str, Any]]:
    if frame is None or frame.empty:
        return []
    columns = [str(column) for column in frame.columns]
    required_columns = list(FINRA_MARGIN_COLUMNS.values())
    if any(columns.count(column) != 1 for column in required_columns):
        return []
    parsed: List[Dict[str, Any]] = []
    for _, raw in frame.iterrows():
        try:
            reference_month_end = _finra_reference_month_end(raw[FINRA_MARGIN_COLUMNS["reference_month"]])
            margin_debt = float(raw[FINRA_MARGIN_COLUMNS["margin_debt"]])
            cash_credit = float(raw[FINRA_MARGIN_COLUMNS["cash_credit"]])
            margin_credit = float(raw[FINRA_MARGIN_COLUMNS["margin_credit"]])
        except (TypeError, ValueError, KeyError):
            continue
        if not all(
            np.isfinite(value) and value >= 0
            for value in (margin_debt, cash_credit, margin_credit)
        ):
            continue
        if reference_month_end > effective:
            continue
        visible_date = reference_month_end + timedelta(days=21)
        if visible_date > effective:
            continue
        parsed.append({
            "reference_month": reference_month_end.strftime("%Y-%m"),
            "reference_month_end": reference_month_end,
            "visible_date": visible_date,
            "margin_debt": margin_debt,
            "cash_credit": cash_credit,
            "margin_credit": margin_credit,
        })
    return sorted(parsed, key=lambda item: item["reference_month_end"], reverse=True)


def _pct_change(current: float, prior: Optional[float]) -> Optional[float]:
    if prior is None or prior == 0:
        return None
    return round((current / prior - 1.0) * 100.0, 2)


def get_finra_margin_debt(end_date: str = None) -> Dict[str, Any]:
    """FINRA monthly aggregate margin debt with a conservative PIT gate."""
    effective, error = _parse_positioning_effective_date(end_date)
    effective_text = end_date or date.today().isoformat()
    if error or effective is None:
        return _finra_unavailable(effective_text, error or "invalid_effective_date")
    recency_error = _recent_positioning_date_error(effective)
    if recency_error:
        return _finra_unavailable(effective.isoformat(), recency_error)
    try:
        visible_rows = _finra_visible_rows(_fetch_finra_margin_frame(), effective)
    except Exception as exc:
        return _finra_unavailable(effective.isoformat(), f"official_source_unavailable:{type(exc).__name__}:{str(exc)[:120]}")
    if not visible_rows:
        return _finra_unavailable(effective.isoformat(), "no_finra_month_visible_by_conservative_release_gate")

    latest = visible_rows[0]
    by_month = {row["reference_month"]: row for row in visible_rows}
    previous_period = (pd.Period(latest["reference_month"], freq="M") - 1).strftime("%Y-%m")
    year_ago_period = (pd.Period(latest["reference_month"], freq="M") - 12).strftime("%Y-%m")
    previous = by_month.get(previous_period)
    year_ago = by_month.get(year_ago_period)
    value = {
        "reference_month": latest["reference_month"],
        "reference_month_end": latest["reference_month_end"].isoformat(),
        "estimated_visible_date": latest["visible_date"].isoformat(),
        "visibility_rule": "reference_month_end_plus_21_calendar_days_conservative_estimate",
        "margin_debt_millions": int(latest["margin_debt"]),
        "month_over_month_pct": _pct_change(latest["margin_debt"], previous["margin_debt"] if previous else None),
        "year_over_year_pct": _pct_change(latest["margin_debt"], year_ago["margin_debt"] if year_ago else None),
        "cash_account_free_credit_millions": int(latest["cash_credit"]),
        "margin_account_free_credit_millions": int(latest["margin_credit"]),
        "historical_pit_archive_status": "not_connected_current_official_workbook_only",
    }
    anomalies = []
    anomalies.append("current_workbook_not_retained_as_publication_vintage")
    if previous is None:
        anomalies.append("previous_month_missing_month_over_month_unavailable")
    if year_ago is None:
        anomalies.append("year_ago_month_missing_year_over_year_unavailable")
    return {
        "name": "FINRA Margin Debt",
        "series_id": "FINRA_CUSTOMER_MARGIN_BALANCES",
        "value": value,
        "unit": "USD millions",
        "source_name": "Financial Industry Regulatory Authority",
        "source_tier": "official",
        "source_url": FINRA_MARGIN_STATISTICS_PAGE,
        "download_url": FINRA_MARGIN_STATISTICS_XLSX,
        "availability": "available",
        "data_quality": _positioning_data_quality(
            provider="FINRA", source_name="FINRA Margin Statistics",
            source_url=FINRA_MARGIN_STATISTICS_PAGE, effective_date=effective.isoformat(),
            data_date=value["reference_month_end"], visible_date=value["estimated_visible_date"], availability="available",
            methodology="Monthly customer margin balances; conservative estimated visibility is month-end plus 21 calendar days.",
            coverage={"scope": "aggregate FINRA member-firm customer balances", "visible_rows_in_current_workbook": len(visible_rows), "historical_pit_archive_connected": False},
            metric_authority=FINRA_MARGIN_METRIC_AUTHORITY, downgrade_rules=FINRA_MARGIN_DOWNGRADE_RULES,
            anomalies=anomalies,
        ),
        "notes": "Official monthly broad-market leverage context; supporting only, approximately three-week lag, not a short-term timing signal.",
    }


CNN_FGI_BASE_URL = "https://production.dataviz.cnn.io/index/fearandgreed/graphdata"


def _get_cnn_headers() -> Dict[str, str]:
    """构建CNN API请求头，模拟浏览器访问"""
    return {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'application/json',
        'Referer': 'https://edition.cnn.com/',
        'Accept-Language': 'en-US,en;q=0.9',
    }


def _cnn_safe_float(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _cnn_fgi_timestamp_to_date(value: Any) -> Optional[str]:
    if value is None:
        return None
    try:
        number = float(value)
        if number > 10_000_000_000:
            number = number / 1000.0
        return datetime.fromtimestamp(number, tz=timezone.utc).strftime("%Y-%m-%d")
    except Exception:
        pass
    try:
        return pd.to_datetime(value, utc=True, errors="coerce").strftime("%Y-%m-%d")
    except Exception:
        return None


def _select_cnn_fgi_historical_point(data: Dict[str, Any], end_date: str) -> Optional[Dict[str, Any]]:
    historical = data.get("fear_and_greed_historical")
    rows = historical.get("data") if isinstance(historical, dict) else None
    if not isinstance(rows, list):
        return None
    effective = pd.to_datetime(end_date, utc=True, errors="coerce")
    if pd.isna(effective):
        return None
    selected: Optional[Dict[str, Any]] = None
    selected_date = None
    for row in rows:
        if not isinstance(row, dict):
            continue
        row_date_text = row.get("date") or row.get("x") or row.get("timestamp")
        row_date = pd.to_datetime(
            _cnn_fgi_timestamp_to_date(row_date_text) or row_date_text,
            utc=True,
            errors="coerce",
        )
        if pd.isna(row_date) or row_date > effective:
            continue
        if selected_date is None or row_date > selected_date:
            selected = row
            selected_date = row_date
    if selected is not None and selected_date is not None:
        selected = dict(selected)
        selected["_selected_date"] = selected_date.strftime("%Y-%m-%d")
    return selected


def get_cnn_fear_greed_index(end_date: str = None) -> Dict[str, Any]:
    """
    获取CNN恐贪指数 (Fear & Greed Index)

    数据源：CNN Business官方API
    URL：https://production.dataviz.cnn.io/index/fearandgreed/graphdata/{date}

    核心价值：
    - 综合性市场情绪指标，整合7个子指标
    - 极端值是反向情绪观察（<25极度恐惧、>75极度贪婪），必须结合价格、波动率和信用确认
    - 提供历史对比数据（前一日/周/月/年）

    返回结构：
    - score: 恐贪指数得分 (0-100)
    - rating: 情绪评级 (extreme fear/fear/neutral/greed/extreme greed)
    - previous_close/week/month/year: 历史对比
    - sub_metrics: 7个子指标详情

    投资逻辑（第一性原理）：
    - 极端恐惧（<25）：市场过度悲观的候选观察，不能单独推出价格低于内在价值或买入结论
    - 极端贪婪（>75）：市场过度乐观的候选观察，不能单独推出卖出结论
    """
    headers = _get_cnn_headers()

    if end_date:
        start_date = end_date
    else:
        start_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")

    url = f"{CNN_FGI_BASE_URL}/{start_date}"

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        data = response.json()

        historical_point = _select_cnn_fgi_historical_point(data, end_date) if end_date else None
        if end_date and not historical_point:
            return {
                "name": "CNN Fear & Greed Index",
                "value": None,
                "source_tier": "unavailable",
                "source_name": "CNN Business",
                "notes": "Historical CNN Fear & Greed data unavailable for effective_date; live field was not used in backtest mode.",
                "data_quality": {
                    "data_date": end_date,
                    "anomalies": ["historical_point_missing"],
                    "fallback_chain": ["CNN fear_and_greed_historical.data", "unavailable"],
                },
            }

        fear_greed = historical_point or data.get('fear_and_greed', {})
        if not fear_greed:
            return {
                "name": "CNN Fear & Greed Index",
                "value": None,
                "notes": "No fear and greed data in response"
            }

        score = fear_greed.get('score')
        if score is None:
            score = fear_greed.get("y")
        if score is None:
            score = fear_greed.get("value")
        score = _cnn_safe_float(score)
        rating = fear_greed.get('rating')

        result = {
            "name": "CNN Fear & Greed Index",
            "series_id": "CNN_FGI",
            "value": {
                "score": round(score, 2) if score is not None else None,
                "rating": rating,
                "timestamp": fear_greed.get('timestamp') or fear_greed.get("x"),
                "data_date": fear_greed.get("_selected_date") or _cnn_fgi_timestamp_to_date(fear_greed.get('timestamp') or fear_greed.get("x")),
                "previous_close": fear_greed.get('previous_close'),
                "previous_1_week": fear_greed.get('previous_1_week'),
                "previous_1_month": fear_greed.get('previous_1_month'),
                "previous_1_year": fear_greed.get('previous_1_year'),
            },
            "unit": "index (0-100)",
            "source_name": "CNN Business",
            "notes": "Score range: 0-100. <25=Extreme Fear, >75=Extreme Greed. This is sentiment evidence only and requires confirmation from volatility, credit, price, and valuation."
        }
        if end_date:
            result["data_quality"] = {
                "data_date": result["value"].get("data_date") or end_date,
                "effective_date": end_date,
                "source_path": "fear_and_greed_historical.data",
                "anomalies": [],
            }
        else:
            result["data_quality"] = {
                "data_date": result["value"].get("data_date"),
                "source_path": "fear_and_greed",
                "anomalies": ["live_current_field"],
            }

        sub_metrics = {}
        sub_metric_names = {
            "market_momentum_sp500": "Market Momentum (S&P500)",
            "stock_price_strength": "Stock Price Strength",
            "stock_price_breadth": "Stock Price Breadth",
            "put_call_options": "Put/Call Options",
            "market_volatility_vix": "Market Volatility (VIX)",
            "junk_bond_demand": "Junk Bond Demand",
            "safe_haven_demand": "Safe Haven Demand"
        }

        for key, display_name in sub_metric_names.items():
            if key in data:
                metric_data = data[key]
                sub_metrics[display_name] = {
                    "score": metric_data.get('score'),
                    "rating": metric_data.get('rating')
                }

        if sub_metrics:
            result["value"]["sub_metrics"] = sub_metrics

        trend = "neutral"
        if score is not None:
            if score < 25:
                trend = "extreme_fear"
            elif score < 45:
                trend = "fear"
            elif score < 55:
                trend = "neutral"
            elif score < 75:
                trend = "greed"
            else:
                trend = "extreme_greed"
        result["value"]["trend"] = trend

        logging.info(f"CNN FGI: {score:.2f} ({rating})" if score is not None else f"CNN FGI: unavailable ({rating})")
        return result

    except requests.exceptions.HTTPError as e:
        logging.warning(f"CNN FGI HTTP error: {e}")
        return {
            "name": "CNN Fear & Greed Index",
            "value": None,
            "notes": f"HTTP error: {str(e)[:50]}"
        }
    except requests.exceptions.RequestException as e:
        logging.warning(f"CNN FGI request error: {e}")
        return {
            "name": "CNN Fear & Greed Index",
            "value": None,
            "notes": f"Request error: {str(e)[:50]}"
        }
    except Exception as e:
        logging.warning(f"CNN FGI unexpected error: {e}")
        return {
            "name": "CNN Fear & Greed Index",
            "value": None,
            "notes": f"Error: {str(e)[:50]}"
        }

