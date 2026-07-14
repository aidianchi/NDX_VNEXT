# tools_L1.py
# -*- coding: utf-8 -*-
"""
NDX Agent · 第1层数据获取函数
"""

from copy import deepcopy

try:
    from .tools_common import *
    from .tools_common import _fetch_fred_series, _fetch_yf_history
    from .data_evidence import build_data_quality
except ImportError:
    from tools_common import *
    from tools_common import _fetch_fred_series, _fetch_yf_history
    from data_evidence import build_data_quality

# =====================================================
# 第1层函数
# =====================================================

_VOL_LEVEL_CACHE = {}

AMOUNT_UNIT_BILLION_USD = "billion_usd"


def _fred_unavailable_payload(
    *,
    name: str,
    series_id: str,
    unit: str,
    minimum_points: int,
    series: Optional[pd.DataFrame] = None,
    calculation: Optional[str] = None,
) -> Dict[str, Any]:
    quality = dict(getattr(series, "attrs", {}).get("data_quality") or get_fred_series_diagnostics(series_id) or {})
    failure_type = quality.get("failure_type") or "insufficient_observations"
    failure_reason = quality.get("failure_reason") or f"FRED returned fewer than {minimum_points} usable observations."
    quality.update(
        {
            "availability": "unavailable",
            "failure_type": failure_type,
            "failure_reason": failure_reason,
            "observations_available": 0 if series is None else len(series),
            "minimum_observations_required": minimum_points,
        }
    )
    if calculation:
        quality["calculation"] = calculation
    return {
        "name": name,
        "series_id": series_id,
        "value": None,
        "unit": unit,
        "source_name": "FRED",
        "notes": f"FRED data unavailable or insufficient: {failure_type} ({failure_reason})",
        "data_quality": quality,
    }


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

        return {
            "name": name, "series_id": ticker, "value": analysis,
            "unit": "level", "source_name": "yfinance",
            "notes": f"Successfully fetched data as of {analysis['date']}." + (" 分层降噪：Spot/MA20。" if use_ma20_trend else "")
        }
    except Exception as e:
        error_note = f"Failed to get {ticker} data: {str(e)}"
        logging.warning(f"  - {name}: {error_note}")
        return {
            "name": name, "series_id": ticker, "value": None,
            "notes": error_note
        }


def _read_cached_series_until(series_id: str, end_date: str) -> pd.DataFrame:
    """Read local TimeSeriesManager cache for historical mode without current-day refresh."""
    try:
        effective_date = pd.to_datetime(end_date)
        path = ts_manager._series_path(series_id)
        frame = ts_manager._read_local(path, date_col="date")
        frame = ts_manager._normalize_df(frame)
        if frame.empty or "value" not in frame.columns:
            return pd.DataFrame(columns=["date", "value"])
        frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
        frame = frame[(frame["date"] <= effective_date)].dropna(subset=["date", "value"])
        return frame.sort_values("date")[["date", "value"]]
    except Exception as exc:
        logging.warning("读取 %s 历史缓存失败: %s", series_id, exc)
        return pd.DataFrame(columns=["date", "value"])


def _get_series_for_effective_date(series_id: str, update_func, end_date: Optional[str]) -> pd.DataFrame:
    """Use historical cache in backtests; only fetch through the requested effective date if cache is missing."""
    if end_date:
        effective_date = pd.to_datetime(end_date)
        cached = _read_cached_series_until(series_id, end_date)
        if not cached.empty:
            latest_date = cached["date"].max()
            if not pd.isna(latest_date) and latest_date >= effective_date - timedelta(days=7):
                return cached
        try:
            return update_func(start_date=None, end_date=end_date)
        except TypeError as exc:
            logging.warning("%s historical fetch does not support end_date safely: %s", series_id, exc)
            return pd.DataFrame(columns=["date", "value"])
    return ts_manager.get_or_update_series(series_id, update_func)


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
    return {
        "name": "VIX Index",
        "series_id": "^VIX",
        "value": value_out,
        "unit": "index level",
        "source_name": source_name,
        "notes": "VIX 恐慌指数；分层降噪：现值 + 趋势比(Spot/MA20)。",
    }


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
        return {
            "name": "VIX Index",
            "series_id": "VIX",
            "value": value_out,
            "unit": "index level",
            "source_name": "Alpha Vantage (fallback)",
            "notes": "VIX 恐慌指数（Alpha Vantage备用）；分层降噪：现值 + 趋势比(Spot/MA20)。"
        }
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
            "vix6m_leg": {
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


FED_FUNDS_FUTURES_MONTH_CODES = {
    1: "F", 2: "G", 3: "H", 4: "J", 5: "K", 6: "M",
    7: "N", 8: "Q", 9: "U", 10: "V", 11: "X", 12: "Z",
}
FED_FUNDS_PATH_MONTHS = 13
FED_FUNDS_PATH_MINIMUM_CURVE_MONTHS = 4
FED_FUNDS_PATH_FLAT_BAND_PP = 0.125
FED_FUNDS_PATH_LIQUIDITY_THRESHOLDS = {
    "negligible_below_avg_volume_10d": 5.0,
    "thin_below_avg_volume_10d": 100.0,
}


def _fed_funds_contract_for_month(year: int, month: int) -> str:
    return f"ZQ{FED_FUNDS_FUTURES_MONTH_CODES[month]}{year % 100:02d}.CBT"


def _fed_funds_month_at_offset(anchor: datetime, months_ahead: int) -> tuple:
    absolute_month = anchor.year * 12 + (anchor.month - 1) + months_ahead
    return absolute_month // 12, absolute_month % 12 + 1


def _fed_funds_path_state(slope_pp: Optional[float]) -> str:
    """Classify the implied-rate curve with the canon's ±12.5bp buffer."""
    if slope_pp is None:
        return "unavailable"
    if slope_pp <= -FED_FUNDS_PATH_FLAT_BAND_PP:
        return "easing_priced"
    if slope_pp >= FED_FUNDS_PATH_FLAT_BAND_PP:
        return "tightening_priced"
    return "flat_path"


def _fed_funds_liquidity_tier(avg_volume_10d: Optional[float]) -> str:
    if avg_volume_10d is None or avg_volume_10d < FED_FUNDS_PATH_LIQUIDITY_THRESHOLDS["negligible_below_avg_volume_10d"]:
        return "negligible"
    if avg_volume_10d < FED_FUNDS_PATH_LIQUIDITY_THRESHOLDS["thin_below_avg_volume_10d"]:
        return "thin"
    return "adequate"


def get_fed_funds_rate_path(end_date: str = None) -> Dict[str, Any]:
    """Return a compact Fed funds futures implied-rate path for L1.

    This is the deliberately reduced implementation from
    investigation_reports/20260711_first_principles/WORK_ORDERS.md item 4
    (fed funds 缩水版): 13 monthly ZQ contracts, an implied average-rate
    slope/state, and an EFFR/DFF reference anchor. It does not attempt CME
    FedWatch meeting probabilities or stitched historical percentiles.

    Point-in-time contract: the contract set is generated from the month of
    ``end_date`` and every contract's history is explicitly truncated to
    observations on or before ``end_date``. Futures settlement closes are
    non-revisable market facts and therefore backtest-eligible, but Yahoo's
    relay is marked ``third_party_unofficial`` because it is not verified
    against the official CME settlement file.
    """
    effective_date = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()
    effective_date_str = effective_date.strftime("%Y-%m-%d")
    request_start = effective_date - timedelta(days=35)
    request_end = effective_date + timedelta(days=1)
    source_name = "yfinance (Yahoo Finance ZQ monthly futures) + FRED (EFFR/DFF anchor)"
    source_url = "https://finance.yahoo.com/quote/ZQ%3DF/"

    state_thresholds = {
        "easing_priced_at_or_below_slope_pp": -FED_FUNDS_PATH_FLAT_BAND_PP,
        "tightening_priced_at_or_above_slope_pp": FED_FUNDS_PATH_FLAT_BAND_PP,
        "flat_path_abs_slope_below_pp": FED_FUNDS_PATH_FLAT_BAND_PP,
        "note": "斜率绝对值小于0.125个百分点（12.5bp）视为 flat；边界值归入 easing/tightening。",
    }
    liquidity_thresholds = {
        **FED_FUNDS_PATH_LIQUIDITY_THRESHOLDS,
        "negligible_action": "exclude_from_formal_path_and_curve_calculation",
        "thin_action": "retain_with_field_authority_downgrade",
        "far_month_rule": "months_ahead > 6 is always low_liquidity_far_month",
    }

    def _metric_authority() -> Dict[str, Any]:
        return {
            "path_0_6m": {
                "source": "third_party_unofficial",
                "usage": "supporting_only",
                "authority": "supporting",
                "reason": "近端月度结算价可支持市场定价观察；thin 月按单项 field_authority 继续降级，不能视为 Fed 承诺。",
                "reference_sources": [],
            },
            "path_7_12m": {
                "source": "third_party_unofficial",
                "usage": "supporting_only",
                "authority": "low_liquidity_far_month",
                "reason": "7-12月合约无论当日成交量如何均属远月低置信观察，不能单独支撑方向结论。",
                "reference_sources": [],
            },
            "state": {
                "source": "third_party_unofficial",
                "usage": "supporting_only",
                "authority": "supporting",
                "reason": (
                    "easing_priced 不是流动性利多，须与 HY OAS 和增长数据交叉验证；"
                    "tightening_priced 只作贴现率逆风风险确认。"
                ),
                "reference_sources": ["get_hy_oas_bp"],
            },
            "slope_12m_and_cuts_priced_bps": {
                "source": "third_party_unofficial",
                "usage": "supporting_only",
                "authority": "derived_curve_summary",
                "reason": "由首个合格月和最远合格月推导；horizon_used 若短于12月必须按实际期限解释。",
                "reference_sources": [],
            },
            "effr_anchor": {
                "source": "official_fred_reference_when_available",
                "usage": "cross_check_only",
                "authority": "non_blocking_anchor",
                "reason": "EFFR/DFF 是时点实施利率，而期货合约隐含整月平均利率；偏差只标注 anomaly，不阻断曲线判读。",
                "reference_sources": ["FRED EFFR", "FRED DFF"],
            },
        }

    def _unavailable(reason: str, raw_series: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        quality = build_data_quality(
            provider="yfinance",
            source_name=source_name,
            source_url=source_url,
            source_tier="third_party_unofficial",
            data_date="not_available",
            as_of_date=effective_date_str,
            effective_date=effective_date_str,
            vintage_date="not_available",
            availability="unavailable",
            fallback_reason=reason,
            fallback_chain=["third_party_unofficial", "unavailable"],
            license_note="public_endpoint_review_required",
            coverage={"contracts_requested": FED_FUNDS_PATH_MONTHS, "contracts_observed": 0},
            methodology="implied_rate = 100 - ZQ monthly futures close; curve requires at least four non-negligible months",
            formula="implied_rate = 100 - close",
            anomalies=[reason],
        )
        quality["metric_authority"] = _metric_authority()
        return {
            "name": "Fed Funds Futures Implied Rate Path",
            "series_id": "ZQ_MONTHLY_PATH",
            "value": None,
            "unit": "percent",
            "date": effective_date_str,
            "source_tier": "third_party_unofficial",
            "source_name": source_name,
            "source_url": source_url,
            "availability": "unavailable",
            "unavailable_reason": reason,
            "data_quality": quality,
            "notes": f"Fed funds futures rate path unavailable: {reason}",
        }

    raw_series: List[Dict[str, Any]] = []
    path: List[Dict[str, Any]] = []
    try:
        for months_ahead in range(FED_FUNDS_PATH_MONTHS):
            contract_year, contract_month = _fed_funds_month_at_offset(effective_date, months_ahead)
            contract = _fed_funds_contract_for_month(contract_year, contract_month)
            observations: List[Dict[str, Any]] = []
            try:
                frame = cached_yf_download(
                    contract,
                    start=request_start.strftime("%Y-%m-%d"),
                    end=request_end.strftime("%Y-%m-%d"),
                    progress=False,
                    auto_adjust=False,
                )
                frame = clean_yfinance_dataframe(frame)
                if frame is not None and not frame.empty and "close" in frame.columns:
                    frame = frame.copy()
                    frame.index = pd.to_datetime(frame.index)
                    if getattr(frame.index, "tz", None) is not None:
                        frame.index = frame.index.tz_localize(None)
                    frame = frame[frame.index <= pd.Timestamp(effective_date)].sort_index().tail(10)
                    for data_date, row in frame.iterrows():
                        close_value = row.get("close")
                        volume_value = row.get("volume")
                        if pd.isna(close_value):
                            continue
                        observations.append({
                            "data_date": pd.Timestamp(data_date).strftime("%Y-%m-%d"),
                            "close": round(float(close_value), 4),
                            "volume": None if pd.isna(volume_value) else round(float(volume_value), 2),
                        })
            except Exception as contract_exc:
                logging.warning("Fed funds contract %s unavailable: %s", contract, contract_exc)

            volumes = [item["volume"] for item in observations if isinstance(item.get("volume"), (int, float))]
            avg_volume = (sum(volumes) / len(volumes)) if volumes else None
            liquidity_tier = _fed_funds_liquidity_tier(avg_volume)
            raw_entry = {
                "months_ahead": months_ahead,
                "contract": contract,
                "contract_year": contract_year,
                "contract_month": contract_month,
                "observations": observations,
                "avg_volume_10d": None if avg_volume is None else round(avg_volume, 2),
                "liquidity_tier": liquidity_tier if observations else "unavailable",
                "included_in_path": bool(observations and liquidity_tier != "negligible"),
            }
            raw_series.append(raw_entry)
            if not observations or liquidity_tier == "negligible":
                continue

            latest = observations[-1]
            item_authority = (
                "low_liquidity_far_month" if months_ahead > 6
                else "supporting_thin_liquidity" if liquidity_tier == "thin"
                else "supporting"
            )
            path.append({
                "months_ahead": months_ahead,
                "contract": contract,
                "implied_rate": round(100.0 - float(latest["close"]), 4),
                "close": latest["close"],
                "last_trade_date": latest["data_date"],
                "avg_volume_10d": round(float(avg_volume), 2),
                "liquidity_tier": liquidity_tier,
                "field_authority": item_authority,
            })

        observed_contracts = sum(1 for entry in raw_series if entry["observations"])
        if observed_contracts == 0:
            return _unavailable("no_zq_contract_observations_on_or_before_effective_date", raw_series)

        curve_status = "available" if len(path) >= FED_FUNDS_PATH_MINIMUM_CURVE_MONTHS else "insufficient_curve"
        front_month = deepcopy(path[0]) if path else None
        far_month = deepcopy(path[-1]) if path else None
        slope_12m: Optional[float] = None
        cuts_priced_bps: Optional[int] = None
        state: Optional[str] = None
        horizon_used: Optional[Dict[str, Any]] = None
        if front_month and far_month:
            actual_curve_months = far_month["months_ahead"] - front_month["months_ahead"]
            horizon_used = {
                "requested_months_ahead": 12,
                "front_months_ahead": front_month["months_ahead"],
                "far_months_ahead": far_month["months_ahead"],
                "actual_months_ahead": actual_curve_months,
                "contract": far_month["contract"],
                "fallback_used": actual_curve_months != 12,
                "reason": (
                    "front_or_requested_12m_contract_excluded_or_unavailable_used_actual_qualified_span"
                    if actual_curve_months != 12 else "requested_12m_curve_span_qualified"
                ),
            }
        if curve_status == "available" and front_month and far_month:
            slope_raw = float(far_month["implied_rate"]) - float(front_month["implied_rate"])
            slope_12m = round(slope_raw, 4)
            cuts_priced_bps = round(-slope_raw * 100)
            state = _fed_funds_path_state(slope_raw)

        anomalies: List[str] = []
        effr_anchor: Optional[Dict[str, Any]] = None
        for anchor_series_id in ("EFFR", "DFF"):
            try:
                anchor_series = get_fred_series(anchor_series_id, days=60, end_date=end_date)
                if anchor_series is None or anchor_series.empty or not {"date", "value"}.issubset(anchor_series.columns):
                    continue
                anchor_frame = anchor_series.copy()
                anchor_frame["date"] = pd.to_datetime(anchor_frame["date"], errors="coerce")
                anchor_frame["value"] = pd.to_numeric(anchor_frame["value"], errors="coerce")
                anchor_frame = anchor_frame[
                    anchor_frame["date"].notna()
                    & (anchor_frame["date"] <= pd.Timestamp(effective_date))
                ].dropna(subset=["value"])
                if anchor_frame.empty:
                    continue
                anchor_row = anchor_frame.sort_values("date").iloc[-1]
                anchor_rate = float(anchor_row["value"])
                front_gap = None if front_month is None else round(float(front_month["implied_rate"]) - anchor_rate, 4)
                effr_anchor = {
                    "series_id": anchor_series_id,
                    "rate": round(anchor_rate, 4),
                    "data_date": anchor_row["date"].strftime("%Y-%m-%d"),
                    "front_month_minus_anchor_pp": front_gap,
                    "availability": "available",
                    "usage": "non_blocking_cross_check",
                }
                if front_gap is not None and abs(front_gap) > 0.35:
                    anomalies.append(f"front_month_vs_{anchor_series_id.lower()}_gap_gt_0.35pp:{front_gap:+.4f}pp")
                break
            except Exception as anchor_exc:
                logging.warning("Optional FRED anchor %s ignored: %s", anchor_series_id, anchor_exc)
                continue
        if effr_anchor is None:
            anomalies.append("effr_anchor_unavailable_non_blocking")

        data_dates = [entry["observations"][-1]["data_date"] for entry in raw_series if entry["observations"]]
        latest_data_date = max(data_dates) if data_dates else effective_date_str
        value = {
            "effective_date": effective_date_str,
            "status": curve_status,
            "front_month": front_month,
            "path": path,
            "slope_12m": slope_12m,
            "horizon_used": horizon_used,
            "cuts_priced_bps": cuts_priced_bps,
            "state": state,
            "state_thresholds": state_thresholds,
            "liquidity_thresholds": liquidity_thresholds,
            "effr_anchor": effr_anchor,
            "raw_series": raw_series,
            "state_usage_boundary": {
                "easing_priced": {
                    "usage": "supporting_only",
                    "reason": "深度降息定价可能反映衰退恐惧；必须与 HY OAS 和增长数据交叉验证后才能讨论方向，禁止单独作为流动性利多。",
                },
                "tightening_priced": {
                    "usage": "supporting_only",
                    "reason": "只可作为贴现率逆风的风险确认，不能单独推出 NDX 方向。",
                },
                "flat_path": {
                    "usage": "supporting_only",
                    "reason": "缓冲带内没有足够曲线斜率信号，不携带方向性结论。",
                },
            },
            "source_boundary": (
                "ZQ 结算价反映市场对合约月份平均联邦基金利率的定价，不是 Fed 承诺；Yahoo 为未经 CME 官方核验的第三方转发。"
                "本缩水版不拼接历史合约、不计算历史分位，也不输出会议概率；升级路径是在官方 CME/FedWatch 可达后核验结算价并增加会议级概率与严格 PIT 合约档案。"
            ),
        }
        quality = build_data_quality(
            provider="yfinance",
            source_name=source_name,
            source_url=source_url,
            source_tier="third_party_unofficial",
            data_date=latest_data_date,
            as_of_date=latest_data_date,
            effective_date=effective_date_str,
            vintage_date=latest_data_date,
            availability="available",
            fallback_reason=("none" if curve_status == "available" else "fewer_than_four_non_negligible_contract_months"),
            fallback_chain=["third_party_unofficial", "unavailable"],
            license_note="public_endpoint_review_required",
            coverage={
                "contracts_requested": FED_FUNDS_PATH_MONTHS,
                "contracts_observed": observed_contracts,
                "contracts_in_formal_path": len(path),
                "negligible_contracts_excluded": sum(1 for entry in raw_series if entry["liquidity_tier"] == "negligible"),
                "curve_status": curve_status,
                "minimum_curve_months_required": FED_FUNDS_PATH_MINIMUM_CURVE_MONTHS,
                "horizon_used": horizon_used,
            },
            methodology=(
                "For each of 13 monthly ZQ contracts from the effective-date month: select the latest close on/before effective_date, "
                "implied_rate=100-close, average the available last 10 daily volumes, exclude avg_volume<5, retain 5<=volume<100 as thin, "
                "then slope=farthest qualified implied rate-front qualified implied rate."
            ),
            formula="implied_rate = 100 - close; slope_12m = farthest_qualified_rate - front_qualified_rate; cuts_priced_bps = round(-slope_12m * 100)",
            anomalies=anomalies,
            point_in_time_note="Contract set and every observation are truncated to effective_date; settlement closes are non-revisable market facts.",
        )
        quality["metric_authority"] = _metric_authority()
        return {
            "name": "Fed Funds Futures Implied Rate Path",
            "series_id": "ZQ_MONTHLY_PATH",
            "value": value,
            "unit": "percent",
            "date": latest_data_date,
            "source_tier": "third_party_unofficial",
            "source_name": source_name,
            "source_url": source_url,
            "availability": "available",
            "data_quality": quality,
            "notes": (
                "ZQ 月合约隐含的是整月平均利率，而 EFFR/DFF 锚是最近时点实施利率；二者超过0.35个百分点只记异常、不阻断。"
                + (" 合格月份不足4个，曲线结论已诚实降级。" if curve_status == "insufficient_curve" else "")
            ),
        }
    except Exception as exc:
        return _unavailable(f"fed_funds_rate_path_exception:{str(exc)[:150]}", raw_series)


def get_10y2y_spread_bp(end_date: str = None) -> Dict[str, Any]:
    """获取10年-2年期美债利差。分层降噪：用 MA20 乖离率替代日度动量。"""
    series = get_fred_series("T10Y2Y", end_date=end_date)
    if series is None or len(series) < 20:
        return _fred_unavailable_payload(
            name="10Y-2Y Treasury Spread",
            series_id="T10Y2Y",
            unit="basis points",
            minimum_points=20,
            series=series,
            calculation="ma20_deviation",
        )
    series = series.copy()
    series['value'] = series['value'] * 100  # Convert to BPS
    analysis = analyze_series_ma_deviation(series, ma_period=20)
    stats = calculate_long_term_stats(series[["date", "value"]], analysis["level"])
    analysis["relativity"] = stats
    return {
        "name": "10Y-2Y Treasury Spread", "series_id": "T10Y2Y", "value": analysis,
        "unit": "basis points", "source_name": "FRED",
        "notes": "10Y-2Y 利差；分层降噪：用距离 MA20 乖离率衡量趋势，替代日度动量。"
    }


def get_hy_oas_bp(end_date: str = None) -> Dict[str, Any]:
    """获取高收益企业债OAS。分层降噪：用 MA5 vs MA20 趋势替代日度动量。"""
    series = get_fred_series("BAMLH0A0HYM2", end_date=end_date)
    if series is None or len(series) < 20:
        return _fred_unavailable_payload(
            name="High Yield OAS",
            series_id="BAMLH0A0HYM2",
            unit="basis points",
            minimum_points=20,
            series=series,
            calculation="ma5_ma20_trend",
        )
    analysis = analyze_series_ma_trend(series, short_period=5, long_period=20)
    stats = calculate_long_term_stats(series[["date", "value"]], analysis["level"])
    analysis["relativity"] = stats
    return {
        "name": "High Yield OAS", "series_id": "BAMLH0A0HYM2", "value": analysis,
        "unit": "basis points", "source_name": "FRED",
        "notes": "ICE BofA US High Yield OAS；分层降噪：MA5 vs MA20 趋势方向。"
    }


def get_ig_oas_bp(end_date: str = None) -> Dict[str, Any]:
    """获取投资级企业债OAS。分层降噪：用 MA5 vs MA20 趋势替代日度动量。"""
    series = get_fred_series("BAMLC0A0CM", end_date=end_date)
    if series is None or len(series) < 20:
        return _fred_unavailable_payload(
            name="Investment Grade OAS",
            series_id="BAMLC0A0CM",
            unit="basis points",
            minimum_points=20,
            series=series,
            calculation="ma5_ma20_trend",
        )
    analysis = analyze_series_ma_trend(series, short_period=5, long_period=20)
    stats = calculate_long_term_stats(series[["date", "value"]], analysis["level"])
    analysis["relativity"] = stats
    return {
        "name": "Investment Grade OAS", "series_id": "BAMLC0A0CM", "value": analysis,
        "unit": "basis points", "source_name": "FRED",
        "notes": "ICE BofA US Corporate OAS；分层降噪：MA5 vs MA20 趋势方向。"
    }


def get_10y_real_rate(end_date: str = None) -> Dict[str, Any]:
    """获取10年期实际利率。分层降噪：L1宏观层使用MA20乖离率替代日度动量。"""
    series = get_fred_series("DFII10", end_date=end_date)
    if series is None or len(series) < 20:
        return _fred_unavailable_payload(
            name="10Y Real Rate",
            series_id="DFII10",
            unit="percent",
            minimum_points=20,
            series=series,
            calculation="ma20_deviation",
        )
    analysis = analyze_series_ma_deviation(series, ma_period=20)
    stats = calculate_long_term_stats(series[["date", "value"]], analysis["level"])
    analysis["relativity"] = stats
    return {
        "name": "10Y Real Rate", "series_id": "DFII10", "value": analysis,
        "unit": "percent", "source_name": "FRED",
        "notes": "10年期实际利率；分层降噪：用距离 MA20 乖离率衡量趋势，替代日度动量。"
    }


def get_10y_treasury(end_date: str = None) -> Dict[str, Any]:
    """获取10年期美债名义收益率。分层降噪：L1宏观层使用MA20乖离率替代日度动量。"""
    series = get_fred_series("DGS10", end_date=end_date)
    if series is None or len(series) < 20:
        return _fred_unavailable_payload(
            name="10Y Treasury Yield",
            series_id="DGS10",
            unit="percent",
            minimum_points=20,
            series=series,
            calculation="ma20_deviation",
        )
    analysis = analyze_series_ma_deviation(series, ma_period=20)
    stats = calculate_long_term_stats(series[["date", "value"]], analysis["level"])
    analysis["relativity"] = stats
    return {
        "name": "10Y Treasury Yield", "series_id": "DGS10", "value": analysis,
        "unit": "percent", "source_name": "FRED",
        "notes": "10年期美债收益率；分层降噪：用距离 MA20 乖离率衡量趋势，替代日度动量。"
    }


def get_10y_breakeven(end_date: str = None) -> Dict[str, Any]:
    """获取10年期盈亏平衡通胀率。分层降噪：L1宏观层使用MA20乖离率替代日度动量。"""
    series = get_fred_series("T10YIE", end_date=end_date)
    if series is None or len(series) < 20:
        return _fred_unavailable_payload(
            name="10Y Breakeven Inflation",
            series_id="T10YIE",
            unit="percent",
            minimum_points=20,
            series=series,
            calculation="ma20_deviation",
        )
    analysis = analyze_series_ma_deviation(series, ma_period=20)
    stats = calculate_long_term_stats(series[["date", "value"]], analysis["level"])
    analysis["relativity"] = stats
    return {
        "name": "10Y Breakeven Inflation", "series_id": "T10YIE", "value": analysis,
        "unit": "percent", "source_name": "FRED",
        "notes": "10年期盈亏平衡通胀率；分层降噪：用距离 MA20 乖离率衡量趋势，替代日度动量。"
    }


def get_fed_funds_rate(end_date: str = None) -> Dict[str, Any]:
    """获取联邦基金利率 (V5.1升级)"""
    series = get_fred_series("FEDFUNDS", end_date=end_date)
    if series is None or len(series) < 3:
        return _fred_unavailable_payload(
            name="Fed Funds Rate",
            series_id="FEDFUNDS",
            unit="percent",
            minimum_points=3,
            series=series,
            calculation="momentum_relativity",
        )
    analysis = analyze_series_momentum_relativity(series)
    if not analysis or analysis.get("level") is None:
        return _fred_unavailable_payload(
            name="Fed Funds Rate",
            series_id="FEDFUNDS",
            unit="percent",
            minimum_points=3,
            series=series,
            calculation="momentum_relativity",
        )
    return {
        "name": "Fed Funds Rate", "series_id": "FEDFUNDS", "value": analysis,
        "unit": "percent", "source_name": "FRED",
        "notes": "Effective Federal Funds Rate with momentum and relativity."
    }


def get_m2_yoy(end_date: str = None) -> Dict[str, Any]:
    """获取M2货币供应量年同比增速 (保留月度动量特性)"""
    yoy, date = calculate_yoy_change("M2SL", lookback_days=800, end_date=end_date)
    yoy_history = calculate_yoy_series("M2SL", lookback_days=5475, end_date=end_date)
    relativity = None
    if yoy_history is not None and not yoy_history.empty:
        analysis = analyze_series_momentum_relativity(yoy_history)
        relativity = analysis.get("relativity")
    if yoy is None or not date:
        return {
            "name": "M2 YoY Growth",
            "series_id": "M2SL",
            "value": None,
            "unit": "percent",
            "source_name": "FRED",
            "availability": "unavailable",
            "unavailable_reason": "m2_yoy_level_or_observation_date_missing",
            "notes": "M2 YoY cannot be used because the level or observation date is missing.",
        }
    return {
        "name": "M2 YoY Growth", "series_id": "M2SL",
        "value": {"level": yoy, "date": date, "momentum": "monthly", "relativity": relativity},
        "unit": "percent", "source_name": "FRED",
        "notes": "M2 Money Supply Year-over-Year Growth (monthly momentum); relativity is calculated on the YoY series itself."
    }


def _fetch_walcl_history(start_date: Optional[Any] = None) -> pd.DataFrame:
    """
    原子化获取 WALCL 历史，单位归一到十亿美元。
    注意：FRED API返回的WALCL单位是百万美元，必须除以1000转换为十亿美元。
    """
    df = _fetch_fred_series("WALCL", start_date=start_date)
    if df.empty:
        return df
    # WALCL在FRED中单位是百万美元，必须除以1000转换为十亿美元
    # 典型值范围：7,000,000-9,000,000百万美元 -> 7,000-9,000十亿美元
    df["value"] = df["value"] / 1000.0
    return df



def _fetch_tga_history(start_date: Optional[Any] = None) -> pd.DataFrame:
    """
    原子化获取财政部现金账户 WTREGEN，单位十亿美元。
    注意：FRED WTREGEN 原始值是百万美元，需除以1000转换为十亿美元。
    """
    df = _fetch_fred_series("WTREGEN", start_date=start_date)
    if df.empty:
        return df
    df["value"] = pd.to_numeric(df["value"], errors="coerce") / 1000.0
    return df



def _fetch_rrp_history(start_date: Optional[Any] = None) -> pd.DataFrame:
    """
    原子化获取隔夜逆回购 RRPONTSYD，单位十亿美元。
    注意：FRED API返回的RRPONTSYD单位已经是十亿美元，不需要转换。
    """
    df = _fetch_fred_series("RRPONTSYD", start_date=start_date)
    if df.empty:
        return df
    # RRPONTSYD在FRED中单位已经是十亿美元，不需要转换
    # 典型值范围：几百到几千十亿美元，不应该>10,000
    return df



def _fetch_qqq_history(start_date: Optional[Any] = None) -> pd.DataFrame:
    """原子化获取 QQQ 历史收盘价，返回 ['date', 'value']。"""
    return _fetch_yf_history("QQQ", start_date=start_date)



def _fetch_vix_history(start_date: Optional[Any] = None, end_date: Optional[Any] = None) -> pd.DataFrame:
    """原子化获取 VIX 日频历史。"""
    return _fetch_yf_history("^VIX", start_date=start_date, end_date=end_date)



def _fetch_xly_history(start_date: Optional[Any] = None, end_date: Optional[Any] = None) -> pd.DataFrame:
    """原子化获取 XLY 日频历史。"""
    return _fetch_yf_history("XLY", start_date=start_date, end_date=end_date)



def _fetch_xlp_history(start_date: Optional[Any] = None, end_date: Optional[Any] = None) -> pd.DataFrame:
    """原子化获取 XLP 日频历史。"""
    return _fetch_yf_history("XLP", start_date=start_date, end_date=end_date)



def _fetch_copper_history(start_date: Optional[Any] = None, end_date: Optional[Any] = None) -> pd.DataFrame:
    """原子化获取铜期货 HG=F 日频历史。"""
    return _fetch_yf_history("HG=F", start_date=start_date, end_date=end_date)



def _fetch_gold_history(start_date: Optional[Any] = None, end_date: Optional[Any] = None) -> pd.DataFrame:
    """原子化获取黄金期货 GC=F 日频历史。"""
    return _fetch_yf_history("GC=F", start_date=start_date, end_date=end_date)



def _build_net_liquidity_series() -> Tuple[pd.DataFrame, pd.Series, pd.Series, pd.Series]:
    """
    构建净流动性日频序列与组件。
    V5.8 修复版：增加数值合理性检查，确保单位一致性。
    """
    walcl_df = ts_manager.get_or_update_series("WALCL", _fetch_walcl_history)
    tga_df = ts_manager.get_or_update_series("WTREGEN", _fetch_tga_history)
    rrp_df = ts_manager.get_or_update_series("RRPONTSYD", _fetch_rrp_history)

    def _repair_wtregen_early_mixed_cache(series: pd.Series) -> pd.Series:
        if series.empty:
            return series
        index = pd.to_datetime(series.index, errors="coerce")
        early_mask = (index < pd.Timestamp("2008-10-22")) & (series > 1000)
        if not early_mask.any():
            return series
        repaired = series.copy()
        repaired.loc[early_mask] = repaired.loc[early_mask] / 1000.0
        logging.warning(
            "WTREGEN early-history mixed-cache anomaly repaired for %s rows before 2008-10-22; "
            "cached historical TGA values appear to mix raw million-dollar and normalized billion-dollar units.",
            int(early_mask.sum()),
        )
        return repaired

    def _normalize_billions(series: pd.Series, series_id: str) -> pd.Series:
        """
        兜底归一到十亿美元，根据序列ID采用不同的转换策略。
        V5.8 增强：增加详细的数值合理性检查和自动修正。
        
        参数:
            series: 待归一化的序列
            series_id: 序列标识符（"WALCL", "WTREGEN", "RRPONTSYD"）
        
        返回:
            归一化到十亿美元单位的序列
        """
        if series.empty:
            return series
        
        max_val = series.max()
        min_val = series.min()
        
        if series_id == "WALCL":
            # WALCL在FRED中单位是百万美元
            # 正常范围：7,000,000-9,000,000百万美元（未转换）或 7,000-9,000十亿美元（已转换）
            if max_val > 100_000:
                # 检测到可能是百万美元单位（>100,000说明未转换）
                logging.warning(f"检测到WALCL数据可能为百万美元单位（最大值={max_val:.2f}），自动转换为十亿美元")
                return series / 1000.0
            elif max_val > 10_000:
                # 异常大值，可能是数据错误
                logging.error(f"WALCL数据异常：最大值={max_val:.2f}，超出合理范围（应在7,000-9,000十亿美元）")
                # 尝试修正：假设是百万美元未转换
                return series / 1000.0
            elif max_val < 1000:
                # 异常小值，可能是重复转换
                logging.error(f"WALCL数据异常：最大值={max_val:.2f}，远低于合理范围（应在7,000-9,000十亿美元）")
                # 可能是千美元单位，需要乘以1000
                return series * 1000.0
            else:
                # 数值在合理范围内（1000-10000），认为已正确转换
                logging.info(f"WALCL数据范围正常：{min_val:.2f} - {max_val:.2f} 十亿美元")
                return series
        
        elif series_id in ["WTREGEN", "RRPONTSYD"]:
            # WTREGEN 原始口径可能是百万美元；RRPONTSYD 通常已经是十亿美元。
            if max_val > 10_000:
                logging.warning(f"{series_id}检测到百万美元口径或混合缓存（最大值={max_val:.2f}），逐点转换为十亿美元")
                normalized = series.where(series <= 10_000, series / 1000.0)
            elif max_val < 10:
                # 异常小值
                logging.error(f"{series_id}数据异常：最大值={max_val:.2f}，远低于合理范围（应在几百到几千十亿美元）")
                # 可能是万亿美元单位，需要乘以1000
                normalized = series * 1000.0
            else:
                # 数值在合理范围内
                logging.info(f"{series_id}数据范围正常：{min_val:.2f} - {max_val:.2f} 十亿美元")
                normalized = series
            if series_id == "WTREGEN":
                normalized = _repair_wtregen_early_mixed_cache(normalized)
            return normalized
        
        return series

    if walcl_df.empty or tga_df.empty or rrp_df.empty:
        logging.error("净流动性组件数据缺失，无法构建序列")
        return pd.DataFrame(), pd.Series(dtype=float), pd.Series(dtype=float), pd.Series(dtype=float)

    for frame in (walcl_df, tga_df, rrp_df):
        frame["date"] = pd.to_datetime(frame["date"])
        frame["value"] = pd.to_numeric(frame["value"], errors="coerce")
        frame.dropna(subset=["date", "value"], inplace=True)

    walcl_s = walcl_df.set_index("date")["value"].astype(float).resample("D").ffill()
    tga_s = tga_df.set_index("date")["value"].astype(float).resample("D").ffill()
    rrp_s = rrp_df.set_index("date")["value"].astype(float).resample("D").ffill()

    # 再次保证单位一致：全部校正到十亿美元（兜底机制）
    walcl_s = _normalize_billions(walcl_s, "WALCL")
    tga_s = _normalize_billions(tga_s, "WTREGEN")
    rrp_s = _normalize_billions(rrp_s, "RRPONTSYD")

    common_index = walcl_s.index.union(tga_s.index).union(rrp_s.index)
    walcl_s = walcl_s.reindex(common_index).ffill()
    tga_s = tga_s.reindex(common_index).ffill()
    rrp_s = rrp_s.reindex(common_index).ffill()

    net_liquidity = walcl_s - tga_s - rrp_s
    
    # 最终合理性检查
    net_liq_latest = net_liquidity.iloc[-1]
    if abs(net_liq_latest) > 20_000:
        logging.error(f"净流动性最终值异常：{net_liq_latest:.2f}，超出合理范围（应在-10,000到+10,000十亿美元）")
    else:
        logging.info(f"净流动性计算完成：最新值 {net_liq_latest:.2f} 十亿美元（Fed={walcl_s.iloc[-1]:.2f}, TGA={tga_s.iloc[-1]:.2f}, RRP={rrp_s.iloc[-1]:.2f}）")
    
    net_liq_df = net_liquidity.reset_index().rename(columns={"index": "date"})
    net_liq_df = net_liq_df.rename(columns={net_liq_df.columns[1]: "value"})
    return net_liq_df, walcl_s, tga_s, rrp_s



def get_net_liquidity_momentum(end_date: str = None) -> Dict[str, Any]:
    """
    计算“美元净流动性”及历史统计：
    Net Liquidity = WALCL(Fed Assets) - WTREGEN(TGA) - RRPONTSYD(Overnight RRP)
    - 使用 TimeSeriesManager 进行增量持久化。
    - 返回值包含 historical_stats。
    """
    if not get_fred_api_key():
        return {
            "name": "Net Liquidity (Fed - TGA - RRP)",
            "value": None,
            "notes": "FRED_API_KEY 不可用，无法计算净流动性。"
        }

    effective_date = pd.to_datetime(end_date, errors="coerce") if end_date else None
    net_liq_df, walcl_s, tga_s, rrp_s = _build_net_liquidity_series()

    if net_liq_df.empty:
        return {
            "name": "Net Liquidity (Fed - TGA - RRP)",
            "value": None,
            "notes": "无法获取完整的 WALCL/WTREGEN/RRPONTSYD 序列。"
        }
    if effective_date is not None and not pd.isna(effective_date):
        net_liq_df = net_liq_df[net_liq_df["date"] <= effective_date]
        walcl_s = walcl_s[walcl_s.index <= effective_date]
        tga_s = tga_s[tga_s.index <= effective_date]
        rrp_s = rrp_s[rrp_s.index <= effective_date]

    if net_liq_df.empty or walcl_s.empty or tga_s.empty or rrp_s.empty:
        return {
            "name": "Net Liquidity (Fed - TGA - RRP)",
            "value": None,
            "notes": f"净流动性在 {end_date} 之前没有完整可见数据。"
        }

    latest_date = net_liq_df["date"].iloc[-1]
    latest_level = float(net_liq_df["value"].iloc[-1])

    # 历史统计
    historical_stats = calculate_long_term_stats(net_liq_df, latest_level)

    # 4周动量（保持向后兼容）
    net_liquidity_series = net_liq_df.set_index("date")["value"]
    net_liq_ma20 = net_liquidity_series.rolling(window=20, min_periods=5).mean()
    momentum_4w = None
    if len(net_liq_ma20.dropna()) >= 25:
        try:
            current_ma = net_liq_ma20.iloc[-1]
            past_ma = net_liq_ma20.iloc[-21]
            momentum_4w = float(current_ma - past_ma)
        except Exception:
            momentum_4w = None

    components = {
        "fed_assets": float(walcl_s.iloc[-1]),
        "tga": float(tga_s.iloc[-1]),
        "rrp": float(rrp_s.iloc[-1]),
    }

    return {
        "name": "Net Liquidity (Fed - TGA - RRP)",
        "series_id": "WALCL-WTREGEN-RRPONTSYD",
        "value": {
            "level": round(latest_level, 2),
            "level_unit": AMOUNT_UNIT_BILLION_USD,
            "momentum_4w": round(momentum_4w, 2) if momentum_4w is not None else None,
            "momentum_4w_unit": AMOUNT_UNIT_BILLION_USD,
            "components": {k: round(v, 2) for k, v in components.items()},
            "components_unit": AMOUNT_UNIT_BILLION_USD,
            "component_units": {k: AMOUNT_UNIT_BILLION_USD for k in components},
            "historical_stats": historical_stats,
            "date": latest_date.strftime("%Y-%m-%d"),
        },
        "unit": "USD Billions",
        "source_name": "FRED",
        "notes": "净流动性；分层降噪：4周滚动动量（月度/周度趋势），替代日度动量。"
    }



def get_qqq_net_liquidity_ratio(end_date: str = None) -> Dict[str, Any]:
    """
    新指标：QQQ / Net Liquidity 比率（防前视偏差）。
    - 分子：QQQ 日频收盘价（yfinance）
    - 分母：净流动性（WALCL - WTREGEN - RRP），日频前向填充
    - 使用 TimeSeriesManager 对齐并持久化缓存。
    """
    if end_date:
        effective_date = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        effective_date = datetime.now()

    qqq_df = ts_manager.get_or_update_series("QQQ", _fetch_qqq_history)
    net_liq_df, _, _, _ = _build_net_liquidity_series()

    if qqq_df.empty or net_liq_df.empty:
        return {
            "name": "QQQ / Net Liquidity Ratio",
            "value": None,
            "notes": "分子或分母数据缺失，无法计算比率。"
        }

    # 过滤到指定日期之前，防止未来值
    qqq_df = qqq_df[qqq_df["date"] <= effective_date]
    net_liq_df = net_liq_df[net_liq_df["date"] <= effective_date]

    ratio_df = align_and_calculate_ratio(
        numerator_series=qqq_df[["date", "value"]],
        denominator_series=net_liq_df[["date", "value"]],
        date_col="date",
        value_col="value",
    )

    if ratio_df.empty:
        return {
            "name": "QQQ / Net Liquidity Ratio",
            "value": None,
            "notes": "对齐后序列为空，可能是日期缺口导致。"
        }

    latest_row = ratio_df.iloc[-1]
    latest_ratio = float(latest_row["ratio"])
    latest_date_str = latest_row["date"].strftime("%Y-%m-%d")

    stats_df = ratio_df.rename(columns={"ratio": "value"})
    historical_stats = calculate_long_term_stats(stats_df[["date", "value"]], latest_ratio)

    return {
        "name": "QQQ / Net Liquidity Ratio",
        "series_id": "QQQ_NET_LIQ_RATIO",
        "value": {
            "level": round(latest_ratio, 4),
            "historical_stats": historical_stats,
            "date": latest_date_str,
        },
        "unit": "ratio",
        "source_name": "yfinance + FRED (cached)",
        "notes": "分母采用向后对齐（backward）避免前视偏差。"
    }


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
                    return {
                        "name": "XLY/XLP Ratio",
                        "value": value_out,
                        "unit": "ratio",
                        "source_name": "yfinance (cached)",
                        "notes": "XLY/XLP 风险偏好；分层降噪：比值相对 MA20 位置。"
                    }
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

        return {
            "name": "XLY/XLP Ratio",
            "value": value_out,
            "unit": "ratio",
            "source_name": "yfinance",
            "notes": f"XLY/XLP 风险偏好；分层降噪：比值相对 MA20 位置。Raw: XLY={aligned_df['xly'].iloc[-1]:.2f}, XLP={aligned_df['xlp'].iloc[-1]:.2f}"
        }
    except Exception as e:
        return {
            "name": "XLY/XLP Ratio",
            "value": None,
            "notes": f"Failed to calculate: {str(e)}"
        }


def get_copper_gold_ratio(end_date: str = None) -> Dict[str, Any]:
    """获取铜期货(HG=F)与黄金期货(GC=F)的价格比率及其动量与相对性。"""
    if not YF_AVAILABLE:
        return {
            "name": "Copper/Gold Ratio",
            "value": None,
            "notes": "yfinance library is not available."
        }

    effective_date = datetime.strptime(end_date, "%Y-%m-%d") if end_date else datetime.now()

    # 尝试使用 TimeSeriesManager 获取数据
    try:
        copper_df = _get_series_for_effective_date("HG=F", _fetch_copper_history, end_date)
        gold_df = _get_series_for_effective_date("GC=F", _fetch_gold_history, end_date)

        if not copper_df.empty and not gold_df.empty:
            copper_df = copper_df[copper_df["date"] <= effective_date]
            gold_df = gold_df[gold_df["date"] <= effective_date]

            if not copper_df.empty and not gold_df.empty:
                ratio_df = align_and_calculate_ratio(
                    numerator_series=copper_df[["date", "value"]],
                    denominator_series=gold_df[["date", "value"]],
                    date_col="date",
                    value_col="value",
                )

                if not ratio_df.empty:
                    ratio_for_ma = ratio_df[["date", "ratio"]].rename(columns={"ratio": "value"})
                    latest_ratio = float(ratio_df.iloc[-1]["ratio"])
                    latest_date_str = ratio_df.iloc[-1]["date"].strftime("%Y-%m-%d")
                    historical_stats = calculate_long_term_stats(ratio_for_ma, latest_ratio)
                    ma_analysis = analyze_series_ratio_vs_ma(ratio_for_ma, ma_period=50) if len(ratio_df) >= 50 else {}
                    value_out = {
                        "level": round(latest_ratio, 4),
                        "historical_stats": historical_stats,
                        "date": latest_date_str,
                    }
                    if ma_analysis:
                        value_out["position_vs_ma50"] = ma_analysis.get("position_vs_ma")
                        value_out["ma50"] = ma_analysis.get("ma")
                    return {
                        "name": "Copper/Gold Ratio",
                        "value": value_out,
                        "unit": "ratio",
                        "source_name": "yfinance (cached)",
                        "notes": "铜/金比率；分层降噪：比值相对 MA50 位置，替代日度动量。"
                    }
    except Exception as e:
        logging.warning(f"TimeSeriesManager 获取铜/金数据失败: {e}")

    # 回退到直接使用 yfinance 获取数据
    # 使用分单标的下载避免 MultiIndex 结构问题及 clean_yfinance_dataframe 破坏 ticker 信息
    try:
        start_date = effective_date - timedelta(days=365 * 11)
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = (effective_date + timedelta(days=1)).strftime("%Y-%m-%d")
        copper_df = cached_yf_download("HG=F", start=start_str, end=end_str, progress=False, auto_adjust=False)
        gold_df = cached_yf_download("GC=F", start=start_str, end=end_str, progress=False, auto_adjust=False)
        copper_df = clean_yfinance_dataframe(copper_df)
        gold_df = clean_yfinance_dataframe(gold_df)
        if copper_df.empty or "close" not in copper_df.columns:
            raise ValueError("No data returned from yfinance for HG=F (copper).")
        if gold_df.empty or "close" not in gold_df.columns:
            raise ValueError("No data returned from yfinance for GC=F (gold).")
        copper_close = copper_df["close"].rename("copper")
        gold_close = gold_df["close"].rename("gold")
        aligned_df = pd.concat([copper_close, gold_close], axis=1).dropna()
        aligned_df.columns = ['copper', 'gold']
        aligned_df['ratio'] = aligned_df['copper'] / aligned_df['gold']
        
        if len(aligned_df) < 3:
            raise ValueError("Not enough valid data points for Copper/Gold ratio calculation.")
        
        # 转换为标准格式用于分析
        ratio_series = aligned_df[['ratio']].rename(columns={'ratio': 'value'})
        ratio_series.index = pd.to_datetime(ratio_series.index)
        ratio_series = ratio_series[ratio_series.index.date <= effective_date.date()]
        
        if ratio_series.empty:
            raise ValueError("No data available on or before the specified date.")
        
        # 分层降噪：比值相对 MA50 位置，替代日度动量
        ratio_for_analysis = ratio_series.reset_index()
        ratio_for_analysis.columns = ['date', 'value']
        analysis = analyze_series_ratio_vs_ma(ratio_for_analysis, ma_period=50) if len(ratio_for_analysis) >= 50 else {}
        latest_ratio = float(ratio_series.iloc[-1]['value'])
        latest_date_val = ratio_series.index[-1].strftime("%Y-%m-%d")
        stats = calculate_long_term_stats(ratio_for_analysis, latest_ratio)
        value_out = {"level": round(latest_ratio, 4), "date": latest_date_val, "historical_stats": stats}
        if analysis:
            value_out["position_vs_ma50"] = analysis.get("position_vs_ma")
            value_out["ma50"] = analysis.get("ma")

        return {
            "name": "Copper/Gold Ratio",
            "value": value_out,
            "unit": "ratio",
            "source_name": "yfinance",
            "notes": f"铜/金比率；分层降噪：比值相对 MA50 位置。Raw: Copper={aligned_df['copper'].iloc[-1]:.2f}, Gold={aligned_df['gold'].iloc[-1]:.2f}"
        }
    except Exception as e:
        return {
            "name": "Copper/Gold Ratio",
            "value": None,
            "notes": f"Failed to calculate: {str(e)}"
        }


# =====================================================
# 新增指标 (任务2.2): DXY, SOFR, WTI, Gold/WTI Ratio
# =====================================================

def get_dxy_index(end_date: str = None) -> Dict[str, Any]:
    """
    获取美元指数 (DXY) - V6.0新增

    第一性原理:
    - 美元是全球储备货币，DXY衡量美元对一篮子主要货币(欧元、日元、英镑等)的强弱
    - 强美元(>100)通常压制新兴市场和美国出口企业盈利，利好进口和美国消费者
    - 弱美元(<90)利好美国出口商、大宗商品，通常伴随风险偏好上升

    数据来源: FRED (DTWEXBGS)
    分层降噪: MA20乖离率

    Args:
        end_date: 分析截止日期 (YYYY-MM-DD)

    Returns:
        DXY数据字典，包含水平值、历史百分位、趋势
    """
    series = get_fred_series("DTWEXBGS", end_date=end_date)
    if series is None or len(series) < 20:
        return _fred_unavailable_payload(
            name="DXY Dollar Index",
            series_id="DTWEXBGS",
            unit="index level",
            minimum_points=20,
            series=series,
            calculation="ma20_deviation",
        )

    analysis = analyze_series_ma_deviation(series, ma_period=20)
    stats = calculate_long_term_stats(series[["date", "value"]], analysis["level"])
    analysis["relativity"] = stats

    return {
        "name": "DXY Dollar Index",
        "series_id": "DTWEXBGS",
        "value": analysis,
        "unit": "index level",
        "source_name": "FRED",
        "notes": "美元指数；分层降噪：MA20乖离率。>100强势，<90弱势。强美元压制出口和新兴市场。"
    }


def get_sofr_rate(end_date: str = None) -> Dict[str, Any]:
    """
    获取SOFR担保隔夜融资利率 - V6.0新增

    第一性原理:
    - SOFR (Secured Overnight Financing Rate) 是LIBOR的替代基准利率
    - 基于真实交易（美国国债回购市场），比LIBOR更难操纵，更可靠
    - 反映以美国国债为抵押的隔夜回购融资成本，是衡量美元融资和抵押品流动性的关键指标
    - SOFR飙升 = 流动性紧张（如2019年9月回购危机）

    数据来源: FRED (SOFR)
    分层降噪: MA20乖离率

    Args:
        end_date: 分析截止日期 (YYYY-MM-DD)

    Returns:
        SOFR数据字典
    """
    series = get_fred_series("SOFR", end_date=end_date)
    if series is None or len(series) < 20:
        return _fred_unavailable_payload(
            name="SOFR Rate",
            series_id="SOFR",
            unit="percent",
            minimum_points=20,
            series=series,
            calculation="ma20_deviation",
        )

    analysis = analyze_series_ma_deviation(series, ma_period=20)
    stats = calculate_long_term_stats(series[["date", "value"]], analysis["level"])
    analysis["relativity"] = stats

    return {
        "name": "SOFR Rate",
        "series_id": "SOFR",
        "value": analysis,
        "unit": "percent",
        "source_name": "FRED",
        "notes": "SOFR担保隔夜融资利率；分层降噪：MA20乖离率。LIBOR的可靠替代品。SOFR飙升=流动性紧张。"
    }


def get_wti_oil(end_date: str = None) -> Dict[str, Any]:
    """
    获取WTI原油价格 - V6.0新增

    第一性原理:
    - WTI (West Texas Intermediate) 是美国基准原油，反映能源成本和通胀预期
    - 油价上升 → 通胀压力 → 美联储鹰派 → 股市承压（尤其消费股）
    - 油价下降 → 通缩风险 → 经济衰退担忧（尤其能源股）
    - 对纳斯达克而言，油价波动影响主要通过通胀预期传导

    数据来源: yfinance (CL=F)
    分层降噪: MA20乖离率 + 历史百分位

    Args:
        end_date: 分析截止日期 (YYYY-MM-DD)

    Returns:
        WTI数据字典
    """
    if not YF_AVAILABLE:
        return {
            "name": "WTI Crude Oil",
            "value": None,
            "unit": "USD/barrel",
            "source_name": "yfinance",
            "notes": "yfinance not available."
        }

    try:
        if end_date:
            effective_date = datetime.strptime(end_date, "%Y-%m-%d")
        else:
            effective_date = datetime.now()

        # 获取11年历史用于10年百分位
        start_date = effective_date - timedelta(days=365 * 11)

        df = cached_yf_download(
            "CL=F",
            start=start_date.strftime("%Y-%m-%d"),
            end=(effective_date + timedelta(days=1)).strftime("%Y-%m-%d"),
            progress=False,
            auto_adjust=False
        )

        if df.empty:
            raise ValueError("yfinance returned empty dataframe for CL=F")

        df = clean_yfinance_dataframe(df)
        df.index = pd.to_datetime(df.index)
        df = df[df.index.date <= effective_date.date()]

        if len(df) < 20:
            raise ValueError(f"Insufficient data points: {len(df)}")

        current_price = float(df["close"].iloc[-1])
        latest_date = df.index[-1].strftime("%Y-%m-%d")

        # 计算MA20
        ma20 = float(df["close"].rolling(20, min_periods=20).mean().iloc[-1])

        # 计算历史统计
        series_for_stats = df[["close"]].reset_index()
        series_for_stats.columns = ["date", "value"]
        stats = calculate_long_term_stats(series_for_stats, current_price)

        analysis = {
            "level": round(current_price, 2),
            "date": latest_date,
            "ma20": round(ma20, 2),
            "deviation_pct": round((current_price - ma20) / ma20 * 100, 2) if ma20 > 0 else None,
            "position_vs_ma": "above" if current_price > ma20 else "below",
            "relativity": stats
        }

        return {
            "name": "WTI Crude Oil",
            "series_id": "CL=F",
            "value": analysis,
            "unit": "USD/barrel",
            "source_name": "yfinance",
            "notes": f"WTI原油价格；分层降噪：MA20乖离率。影响通胀预期。当前: ${current_price:.2f}"
        }

    except Exception as e:
        return {
            "name": "WTI Crude Oil",
            "value": None,
            "unit": "USD/barrel",
            "source_name": "yfinance",
            "notes": f"Failed to fetch WTI: {str(e)[:100]}"
        }


def get_gold_wti_ratio(end_date: str = None) -> Dict[str, Any]:
    """
    获取黄金/WTI原油比率 - V6.0新增

    第一性原理:
    - 黄金 = 避险资产 + 通胀对冲
    - WTI = 周期资产 + 通胀代理
    - Gold/WTI比率上升 → 避险需求 > 周期需求 → 衰退预期
    - Gold/WTI比率下降 → 周期需求 > 避险需求 → 复苏预期
    - 这是铜金比的替代/补充指标，尤其在铜数据不可靠时

    数据来源: yfinance (GC=F / CL=F)
    分层降噪: MA50相对位置

    Args:
        end_date: 分析截止日期 (YYYY-MM-DD)

    Returns:
        Gold/WTI比率数据字典
    """
    if not YF_AVAILABLE:
        return {
            "name": "Gold/WTI Ratio",
            "value": None,
            "unit": "ratio",
            "source_name": "yfinance",
            "notes": "yfinance not available."
        }

    try:
        if end_date:
            effective_date = datetime.strptime(end_date, "%Y-%m-%d")
        else:
            effective_date = datetime.now()

        start_date = effective_date - timedelta(days=365 * 11)
        start_str = start_date.strftime("%Y-%m-%d")
        end_str = (effective_date + timedelta(days=1)).strftime("%Y-%m-%d")

        # 下载黄金和WTI数据
        gold_df = cached_yf_download("GC=F", start=start_str, end=end_str, progress=False, auto_adjust=False)
        wti_df = cached_yf_download("CL=F", start=start_str, end=end_str, progress=False, auto_adjust=False)

        gold_df = clean_yfinance_dataframe(gold_df)
        wti_df = clean_yfinance_dataframe(wti_df)

        if gold_df.empty or "close" not in gold_df.columns:
            raise ValueError("No data for Gold (GC=F)")
        if wti_df.empty or "close" not in wti_df.columns:
            raise ValueError("No data for WTI (CL=F)")

        # 对齐数据
        gold_close = gold_df["close"].rename("gold")
        wti_close = wti_df["close"].rename("wti")
        aligned = pd.concat([gold_close, wti_close], axis=1).dropna()

        if len(aligned) < 50:
            raise ValueError(f"Insufficient aligned data: {len(aligned)} days")

        # 计算比率
        aligned["ratio"] = aligned["gold"] / aligned["wti"]

        # 获取最新值
        latest_ratio = float(aligned["ratio"].iloc[-1])
        latest_gold = float(aligned["gold"].iloc[-1])
        latest_wti = float(aligned["wti"].iloc[-1])
        latest_date = aligned.index[-1].strftime("%Y-%m-%d")

        # 计算MA50和统计
        ma50 = float(aligned["ratio"].rolling(50, min_periods=50).mean().iloc[-1])

        series_for_stats = aligned[["ratio"]].reset_index()
        series_for_stats.columns = ["date", "value"]
        stats = calculate_long_term_stats(series_for_stats, latest_ratio)

        value_out = {
            "level": round(latest_ratio, 4),
            "date": latest_date,
            "ma50": round(ma50, 4),
            "position_vs_ma50": "above" if latest_ratio > ma50 else "below",
            "relativity": stats
        }

        return {
            "name": "Gold/WTI Ratio",
            "series_id": "GC_F_CL_F_RATIO",
            "value": value_out,
            "unit": "ratio (oz/barrel)",
            "source_name": "yfinance",
            "notes": f"黄金/WTI比率；分层降噪：MA50相对位置。衰退/周期代理。Gold=${latest_gold:.2f}, WTI=${latest_wti:.2f}"
        }

    except Exception as e:
        return {
            "name": "Gold/WTI Ratio",
            "value": None,
            "unit": "ratio",
            "source_name": "yfinance",
            "notes": f"Failed to calculate: {str(e)[:100]}"
        }


# =====================================================
# 工具注册表（整合所有层级函数）
# =====================================================
