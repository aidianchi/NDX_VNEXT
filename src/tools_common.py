# tools_common.py
# -*- coding: utf-8 -*-
"""
NDX Agent · 共享工具模块
包含：API配置、常量定义、通用辅助函数
"""

import os
import time
import json
import logging
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple
from functools import wraps
from cachetools import cached, TTLCache
try:
    from .data_manager import (
        TimeSeriesManager,
        calculate_long_term_stats,
        align_and_calculate_ratio,
    )
    from .config import path_config
    from .api_config import get_api_key, get_base_url, get_requests_proxies, is_service_enabled
except ImportError:
    from data_manager import (
        TimeSeriesManager,
        calculate_long_term_stats,
        align_and_calculate_ratio,
    )
    from config import path_config
    from api_config import get_api_key, get_base_url, get_requests_proxies, is_service_enabled

try:
    try:
        from .data_cache import get_global_cache
    except ImportError:
        from data_cache import get_global_cache
    CACHE_AVAILABLE = True
except ImportError:
    CACHE_AVAILABLE = False
    get_global_cache = None

from dotenv import load_dotenv
load_dotenv()

# 尝试导入yfinance
try:
    import yfinance as yf
    YF_AVAILABLE = True
except ImportError:
    YF_AVAILABLE = False
    print("[WARN] yfinance未安装，将仅使用Alpha Vantage")

# 尝试导入pandas_ta
try:
    import pandas_ta as ta
    PANDAS_TA_AVAILABLE = True
except ImportError:
    PANDAS_TA_AVAILABLE = False
    print("[WARN] pandas_ta未安装，ADX等高级技术指标将不可用")

# =====================================================
# 配置与常量
# =====================================================

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

ts_manager = TimeSeriesManager(cache_dir=path_config.cache_dir)

DEFAULT_FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
DEFAULT_ALPHAVANTAGE_BASE_URL = "https://www.alphavantage.co/query"


def get_fred_api_key() -> str:
    """统一读取 FRED Key；若服务被禁用，则视为不可用。"""
    if not is_service_enabled("fred"):
        return ""
    return get_api_key("fred")


def get_alphavantage_api_key() -> str:
    """统一读取 Alpha Vantage Key；若服务被禁用，则视为不可用。"""
    if not is_service_enabled("alphavantage"):
        return ""
    return get_api_key("alphavantage")


def get_fred_base_url() -> str:
    return get_base_url("fred") or DEFAULT_FRED_BASE_URL


def get_alphavantage_base_url() -> str:
    return get_base_url("alphavantage") or DEFAULT_ALPHAVANTAGE_BASE_URL

# M7成分股列表
M7_TICKERS = ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA", "META", "TSLA"]

# V6.0 更新：静态后备列表
NDX100_COMPONENTS_FALLBACK = [
    "AAPL", "ABNB", "ADBE", "ADI", "ADP", "ADSK", "AEP", "ALNY", "AMAT", "AMD",
    "AMGN", "AMZN", "APP", "ARM", "ASML", "AVGO", "AXON", "BKNG", "BKR", "CCEP",
    "CDNS", "CEG", "CHTR", "CMCSA", "COST", "CPRT", "CRWD", "CSCO", "CSGP", "CSX",
    "CTAS", "CTSH", "DASH", "DDOG", "DXCM", "EA", "EXC", "FANG", "FAST", "FER",
    "FTNT", "GEHC", "GILD", "GOOG", "GOOGL", "HON", "IDXX", "INSM", "INTC", "INTU",
    "ISRG", "KDP", "KHC", "KLAC", "LIN", "LRCX", "MAR", "MCHP", "MDLZ", "MELI",
    "META", "MNST", "MPWR", "MRVL", "MSFT", "MSTR", "MU", "NFLX", "NVDA", "NXPI",
    "ODFL", "ORLY", "PANW", "PAYX", "PCAR", "PDD", "PEP", "PLTR", "PYPL", "QCOM",
    "REGN", "ROP", "ROST", "SBUX", "SHOP", "SNPS", "STX", "TEAM", "TMUS", "TRI",
    "TSLA", "TTWO", "TXN", "VRSK", "VRTX", "WBD", "WDAY", "WDC", "WMT", "XEL", "ZS"
]

# 问题股票替换映射
TICKER_REPLACEMENTS = {
    'ANSS': None,
    'WBA': None,
    'GOOGL': 'GOOG',
}

# =====================================================
# 通用辅助函数
# =====================================================

def safe_request(
    url: str,
    params: dict = None,
    timeout: int = 15,
    retry_count: int = 2,
    proxies: Optional[Dict[str, str]] = None,
) -> Optional[dict]:
    """安全的HTTP请求包装器"""
    for _ in range(retry_count):
        try:
            response = requests.get(
                url,
                params=params,
                timeout=timeout,
                proxies=proxies if proxies is not None else get_requests_proxies(),
            )
            response.raise_for_status()
            return response.json()
        except Exception:
            time.sleep(0.5)
    return None


def _format_yf_cache_value(value: Optional[Any]) -> str:
    """灏?yfinance 鍙傛暟杞崲涓虹ǔ瀹氱殑缂撳瓨閿€?"""
    if value is None:
        return "none"
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    try:
        return pd.to_datetime(value).strftime("%Y-%m-%d")
    except Exception:
        return str(value)


def cached_yf_download(
    tickers: Any,
    start: Optional[Any] = None,
    end: Optional[Any] = None,
    interval: str = "1d",
    progress: bool = False,
    auto_adjust: bool = False,
) -> pd.DataFrame:
    """
    缂撳瓨 yfinance.download 鐨勫師濮嬭繑鍥烇紝浣嗕笉鏀瑰彉涓婂眰鍑芥暟鐨勮绠楅€昏緫銆?
    鐪熸鐨勪紭鍖栧彧鍙戠敓鍦ㄢ€滃悓涓€娆¤繍琛屽唴涓嶉噸澶嶄笅杞解€濊繖涓眰闈紝
    鑰屼笉鍘绘敼鍙樻寚鏍囧叕寮忋€佹暟鎹簮鎴栬緭鍑虹粨鏋勩€?
    """
    if not YF_AVAILABLE:
        return pd.DataFrame()

    if isinstance(tickers, (list, tuple, set)):
        ticker_key = ",".join(sorted(str(ticker) for ticker in tickers))
    else:
        ticker_key = str(tickers)

    cache_key = ":".join(
        [
            "yf.download",
            ticker_key,
            _format_yf_cache_value(start),
            _format_yf_cache_value(end),
            interval,
            "adj" if auto_adjust else "raw",
        ]
    )

    def _fetch() -> pd.DataFrame:
        try:
            return yf.download(
                tickers,
                start=start,
                end=end,
                interval=interval,
                progress=progress,
                auto_adjust=auto_adjust,
            )
        except Exception as exc:
            logging.warning(f"yfinance download failed for {ticker_key}: {exc}")
            return pd.DataFrame()

    if not CACHE_AVAILABLE or get_global_cache is None:
        return _fetch()

    cache = get_global_cache()
    if cache is None:
        return _fetch()

    cached_value = cache.get_or_fetch(cache_key, _fetch)
    if isinstance(cached_value, pd.DataFrame):
        return cached_value.copy()
    return pd.DataFrame()


def get_yf_ticker_info_with_retry(ticker: str, attempts: int = 2, pause_seconds: float = 0.8) -> Dict[str, Any]:
    """涓哄鏄撳け璐ョ殑 yfinance.Ticker.info 鎻愪緵杞婚噺閲嶈瘯銆?"""
    if not YF_AVAILABLE:
        raise RuntimeError("yfinance not available")

    last_error: Optional[Exception] = None
    for attempt in range(attempts):
        try:
            info = yf.Ticker(ticker).info
            if info and isinstance(info, dict):
                return info
            raise ValueError(f"Empty info for {ticker}")
        except Exception as exc:
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(pause_seconds)

    raise last_error or RuntimeError(f"Failed to fetch info for {ticker}")


def get_yf_ticker_history_with_retry(
    ticker: str,
    period: str = "5d",
    attempts: int = 2,
    pause_seconds: float = 0.8,
) -> pd.DataFrame:
    """涓哄崟涓?Ticker.history 鎻愪緵杞婚噺閲嶈瘯銆?"""
    if not YF_AVAILABLE:
        return pd.DataFrame()

    last_error: Optional[Exception] = None
    for attempt in range(attempts):
        try:
            history = yf.Ticker(ticker).history(period=period)
            if not history.empty:
                return history
            raise ValueError(f"Empty history for {ticker}")
        except Exception as exc:
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(pause_seconds)

    logging.warning(f"Ticker.history failed for {ticker}: {last_error}")
    return pd.DataFrame()


def get_yf_option_chain_with_retry(
    ticker: str,
    attempts: int = 2,
    pause_seconds: float = 0.8,
) -> Tuple[str, Any]:
    """涓哄崟涓?Ticker 鏈熸潈閾炬彁渚涜交閲嶈瘯銆?"""
    if not YF_AVAILABLE:
        raise RuntimeError("yfinance not available")

    last_error: Optional[Exception] = None
    for attempt in range(attempts):
        try:
            ticker_obj = yf.Ticker(ticker)
            options = ticker_obj.options
            if not options:
                raise ValueError(f"No option chain data for {ticker}")
            opt_date = options[0]
            return opt_date, ticker_obj.option_chain(opt_date)
        except Exception as exc:
            last_error = exc
            if attempt < attempts - 1:
                time.sleep(pause_seconds)

    raise last_error or RuntimeError(f"Failed to fetch option chain for {ticker}")


# =====================================================
# 数据获取原子函数（支持增量 start_date）
# =====================================================


def _normalize_start_date(start_date: Optional[Any]) -> Optional[str]:
    """
    将传入的 start_date 规范化为 YYYY-MM-DD 字符串。
    - None 返回 None
    - datetime/str 均转为日期字符串
    """
    if start_date is None:
        return None
    if isinstance(start_date, datetime):
        return start_date.strftime("%Y-%m-%d")
    try:
        # 允许传入 pandas 时间类型或字符串
        return pd.to_datetime(start_date).strftime("%Y-%m-%d")
    except Exception:
        return None



def _fetch_fred_series(series_id: str, start_date: Optional[Any] = None) -> pd.DataFrame:
    """
    原子化：从 FRED 获取序列，支持 start_date 增量。
    返回包含 ['date', 'value'] 的 DataFrame。
    """
    fred_api_key = get_fred_api_key()
    if not fred_api_key:
        return pd.DataFrame(columns=["date", "value"])

    start_date_str = _normalize_start_date(start_date)
    params = {
        "series_id": series_id,
        "api_key": fred_api_key,
        "file_type": "json",
        "sort_order": "asc",
    }
    if start_date_str:
        params["observation_start"] = start_date_str

    data = safe_request(get_fred_base_url(), params)
    if not data or "observations" not in data:
        return pd.DataFrame(columns=["date", "value"])

    df = pd.DataFrame(data["observations"])
    if df.empty:
        return pd.DataFrame(columns=["date", "value"])

    df = df[df["value"] != "."]
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df["date"] = pd.to_datetime(df["date"])
    df = df.dropna(subset=["value"])
    return df[["date", "value"]]



def _fetch_yf_history(ticker: str, start_date: Optional[Any] = None, end_date: Optional[Any] = None, retry_count: int = 3) -> pd.DataFrame:
    """
    原子化：使用 yfinance 获取日频历史，支持 start_date 增量。
    返回包含 ['date', 'value'] 列（value=收盘价）。
    V5.8.1 紧急修复：彻底解决 reset_index() 后的列名问题。
    """
    if not YF_AVAILABLE:
        logging.warning(f"yfinance 不可用，无法获取 {ticker} 数据")
        return pd.DataFrame(columns=["date", "value"])

    # 确保至少回溯11年以获取足够的10年百分位样本
    if start_date is None:
        end_dt = pd.to_datetime(end_date) if end_date else datetime.now()
        start_str = (end_dt - timedelta(days=365 * 11)).strftime("%Y-%m-%d")
    else:
        start_str = _normalize_start_date(start_date) or "2000-01-01"
    
    end_dt = pd.to_datetime(end_date) if end_date else datetime.now()
    end_str = (end_dt + timedelta(days=1)).strftime("%Y-%m-%d")

    # 重试机制
    for attempt in range(retry_count):
        try:
            logging.info(f"正在获取 {ticker} 数据（尝试 {attempt + 1}/{retry_count}）...")
            df = yf.download(ticker, start=start_str, end=end_str, progress=False, auto_adjust=False)
            df = clean_yfinance_dataframe(df)
            
            if df.empty or "close" not in df.columns:
                if attempt < retry_count - 1:
                    logging.warning(f"{ticker} 返回空数据，{2}秒后重试...")
                    time.sleep(2)
                    continue
                else:
                    logging.error(f"{ticker} 在 {retry_count} 次尝试后仍返回空数据")
                    return pd.DataFrame(columns=["date", "value"])

            # 【核心修复】：先提取close列并重命名，保持DatetimeIndex
            df = df[["close"]].rename(columns={"close": "value"})
            df.index = pd.to_datetime(df.index)
            
            # 【关键】：使用 reset_index() 时，DatetimeIndex 会自动变成名为 "Date" 的列（首字母大写）
            # 不要尝试重命名 "index"，因为它不存在
            df = df.reset_index()
            
            # 统一列名：无论是 "Date" 还是其他，都重命名为 "date"
            if "Date" in df.columns:
                df = df.rename(columns={"Date": "date"})
            elif "index" in df.columns:
                df = df.rename(columns={"index": "date"})
            else:
                # 兜底：如果既没有Date也没有index，说明索引没有被正确重置
                # 手动创建date列
                logging.warning(f"{ticker}: reset_index() 后未找到预期的列名，手动创建date列")
                df["date"] = df.index
            
            # 确保date列是datetime类型
            df["date"] = pd.to_datetime(df["date"])
            df = df[df["date"] <= end_dt]
            result = df[["date", "value"]].dropna()
            
            logging.info(f"成功获取 {ticker} 数据：{len(result)} 条记录")
            return result
            
        except Exception as e:
            if attempt < retry_count - 1:
                logging.warning(f"{ticker} 获取失败: {str(e)}，{2}秒后重试...")
                time.sleep(2)
            else:
                logging.error(f"{ticker} 在 {retry_count} 次尝试后仍失败: {str(e)}")
                return pd.DataFrame(columns=["date", "value"])
    
    return pd.DataFrame(columns=["date", "value"])


def get_fred_series(series_id: str, days: int = 5475, end_date: str = None) -> Optional[pd.DataFrame]:
    """
    从FRED获取指定长度的时间序列数据（V5.1核心函数）
    默认获取15年（5475天）历史数据，确保有足够样本计算10年百分位。
    """
    fred_api_key = get_fred_api_key()
    if not fred_api_key:
        return None

    if end_date:
        effective_date = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        effective_date = datetime.now()
    
    start_date_obj = effective_date - timedelta(days=days)

    params = {
        "series_id": series_id, "api_key": fred_api_key, "file_type": "json",
        "observation_start": start_date_obj.strftime("%Y-%m-%d"),
        "observation_end": effective_date.strftime("%Y-%m-%d"),
        "sort_order": "asc"
    }

    data = safe_request(get_fred_base_url(), params)
    if data and "observations" in data:
        df = pd.DataFrame(data["observations"])
        df = df[df["value"] != "."]
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df["date"] = pd.to_datetime(df["date"])
        return df.dropna(subset=["value"])
    return None


def analyze_series_momentum_relativity(series: pd.DataFrame) -> Dict[str, Any]:
    """
    从时间序列中计算水平、动量和相对性。(V5.12：增加10年历史百分位)
    - 兼容索引为日期（如yfinance）和索引为整数并带有'date'列（如FRED）的DataFrame。
    - 相对性部分现在同时返回 1 年与 10 年（或全部可用历史）百分位。
    """
    if series is None or 'value' not in series.columns or len(series) < 3:
        return {"level": None, "momentum": None, "relativity": None}

    latest_row = series.iloc[-1]
    level = latest_row["value"]

    # 统一日期获取方式
    if isinstance(series.index, pd.DatetimeIndex):
        latest_date = series.index[-1]
    else:
        latest_date = pd.to_datetime(latest_row["date"])
    date_str = latest_date.strftime("%Y-%m-%d")

    # 动量 (Momentum) —— 仍然采用最近3个观察值的1日速度与加速度
    previous_row = series.iloc[-2]
    pre_previous_row = series.iloc[-3]
    mom_1d = level - previous_row["value"]
    prev_mom_1d = previous_row["value"] - pre_previous_row["value"]
    accel_1d = mom_1d - prev_mom_1d

    momentum = {
        "velocity_1d": round(mom_1d, 4),
        "acceleration_1d": round(accel_1d, 4),
        "direction": "rising" if mom_1d > 0 else "falling" if mom_1d < 0 else "flat"
    }

    # 相对性 (Relativity)
    latest_value = latest_row["value"]

    # 1年窗口：若索引为日期，则按时间截取，否则退化为全部可用样本
    if isinstance(series.index, pd.DatetimeIndex):
        one_year_ago = latest_date - pd.DateOffset(years=1)
        series_1y = series[series.index >= one_year_ago]
        if len(series_1y) < 3:  # 数据太短则退化为全样本
            series_1y = series
    else:
        series_1y = series

    percentile_1y = (series_1y["value"] < latest_value).mean() * 100.0

    # 10年窗口：若历史不足10年，则用全部可用样本并在notes中注明
    if isinstance(series.index, pd.DatetimeIndex):
        first_date = series.index[0]
        last_date = series.index[-1]
    else:
        first_date = pd.to_datetime(series["date"].iloc[0])
        last_date = pd.to_datetime(series["date"].iloc[-1])

    history_years = max((last_date - first_date).days / 365.25, 0.0)
    
    # 10年百分位：只有当历史数据>=9.5年时才计算，否则返回None
    if history_years >= 9.5:
        percentile_10y = (series["value"] < latest_value).mean() * 100.0
        notes = f"percentile_10y 基于约 {history_years:.1f} 年历史数据计算。"
    else:
        # 历史不足10年，不计算10年百分位，避免误导
        percentile_10y = None
        notes = f"历史样本长度约 {history_years:.1f} 年，不足10年，未计算 percentile_10y（避免误导）。"

    relativity = {
        "percentile_1y": round(percentile_1y, 1),
        "min_1y": series_1y["value"].min(),
        "max_1y": series_1y["value"].max(),
        "mean_1y": series_1y["value"].mean(),
        "percentile_10y": round(percentile_10y, 1) if percentile_10y is not None else None,
        "history_years": round(history_years, 1),
        "notes": notes,
    }

    return {"level": level, "date": date_str, "momentum": momentum, "relativity": relativity}



def _to_value_series(series: pd.DataFrame) -> Tuple[pd.Series, str]:
    """
    将 series (DataFrame 含 value 列) 转为按日期索引的 Series，便于计算 MA。
    返回 (value_series, date_str)。
    """
    if series is None or "value" not in series.columns or len(series) < 2:
        return pd.Series(dtype=float), ""
    if isinstance(series.index, pd.DatetimeIndex):
        s = series.set_index(series.index)["value"].sort_index()
        date_str = s.index[-1].strftime("%Y-%m-%d") if hasattr(s.index[-1], "strftime") else str(s.index[-1])
    else:
        series = series.copy()
        series["date"] = pd.to_datetime(series["date"])
        s = series.set_index("date")["value"].sort_index()
        date_str = s.index[-1].strftime("%Y-%m-%d")
    return s, date_str



def analyze_series_ma_deviation(series: pd.DataFrame, ma_period: int = 20) -> Dict[str, Any]:
    """
    分层降噪：计算水平、均线、乖离率及相对均线位置。
    适用于 L1 宏观（利率、利差）等慢变量，替代日度动量。
    """
    s, date_str = _to_value_series(series)
    if s.empty or len(s) < ma_period:
        return {"level": None, "ma": None, "deviation_pct": None, "position_vs_ma": None, "date": date_str}
    level = float(s.iloc[-1])
    ma = float(s.rolling(window=ma_period, min_periods=ma_period).mean().iloc[-1])
    if ma != 0:
        deviation_pct = round((level - ma) / abs(ma) * 100, 2)
    else:
        deviation_pct = None
    position_vs_ma = "above" if level > ma else "below" if level < ma else "on"
    return {
        "level": round(level, 4),
        "ma": round(ma, 4),
        "deviation_pct": deviation_pct,
        "position_vs_ma": position_vs_ma,
        "date": date_str,
    }



def analyze_series_ma_trend(series: pd.DataFrame, short_period: int = 5, long_period: int = 20) -> Dict[str, Any]:
    """
    分层降噪：计算 MA5 vs MA20 趋势方向。
    适用于 L1 利差、L2 情绪等，替代日度动量。
    """
    s, date_str = _to_value_series(series)
    if s.empty or len(s) < long_period:
        return {"level": None, "short_ma": None, "long_ma": None, "trend": None, "date": date_str}
    level = float(s.iloc[-1])
    short_ma = float(s.rolling(window=short_period, min_periods=short_period).mean().iloc[-1])
    long_ma = float(s.rolling(window=long_period, min_periods=long_period).mean().iloc[-1])
    trend = "short_above_long" if short_ma > long_ma else "short_below_long" if short_ma < long_ma else "neutral"
    return {
        "level": round(level, 4),
        "short_ma": round(short_ma, 4),
        "long_ma": round(long_ma, 4),
        "trend": trend,
        "date": date_str,
    }



def analyze_series_ratio_vs_ma(series: pd.DataFrame, ma_period: int) -> Dict[str, Any]:
    """
    分层降噪：计算比值相对 MA 的位置（above/below）。
    适用于铜金比、XLY/XLP 等慢变量。
    """
    s, date_str = _to_value_series(series)
    if s.empty or len(s) < ma_period:
        return {"level": None, "ma": None, "position_vs_ma": None, "date": date_str}
    level = float(s.iloc[-1])
    ma = float(s.rolling(window=ma_period, min_periods=ma_period).mean().iloc[-1])
    position_vs_ma = "above" if level > ma else "below" if level < ma else "on"
    return {
        "level": round(level, 4),
        "ma": round(ma, 4),
        "position_vs_ma": position_vs_ma,
        "date": date_str,
    }



def get_latest_fred_value(series_id: str, end_date: str = None) -> Tuple[Optional[float], Optional[str]]:
    """从FRED获取指定日期或之前的最新数据点"""
    fred_api_key = get_fred_api_key()
    if not fred_api_key:
        return None, None

    if end_date:
        effective_date = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        effective_date = datetime.now()

    params = {
        "series_id": series_id,
        "api_key": fred_api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 1,
        "observation_end": effective_date.strftime("%Y-%m-%d")
    }

    data = safe_request(get_fred_base_url(), params)
    if data and "observations" in data and data["observations"]:
        obs = data["observations"][0]
        try:
            value = float(obs["value"])
            date = obs["date"]
            return value, date
        except (ValueError, KeyError):
            pass
    return None, None


def calculate_yoy_change(series_id: str, lookback_days: int = 800, end_date: str = None) -> Tuple[Optional[float], Optional[str]]:
    """计算FRED序列的年同比变化"""
    fred_api_key = get_fred_api_key()
    if not fred_api_key:
        return None, None

    if end_date:
        effective_date = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        effective_date = datetime.now()

    try:
        start_date_obj = effective_date - timedelta(days=lookback_days)

        params = {
            "series_id": series_id,
            "api_key": fred_api_key,
            "file_type": "json",
            "observation_start": start_date_obj.strftime("%Y-%m-%d"),
            "observation_end": effective_date.strftime("%Y-%m-%d"),
            "sort_order": "asc"
        }

        data = safe_request(get_fred_base_url(), params)
        if not data or "observations" not in data:
            return None, None

        obs = data["observations"]
        if not obs:
            return None, None

        df = pd.DataFrame(obs)
        df["date"] = pd.to_datetime(df["date"])
        df = df[df["value"] != "."]
        df["value"] = pd.to_numeric(df["value"], errors="coerce")
        df = df.dropna(subset=["value"])

        if len(df) < 24:
            return None, None

        latest_row = df.iloc[-1]
        latest_value = latest_row["value"]
        latest_date = latest_row["date"]

        year_ago_date = latest_date - pd.DateOffset(years=1)
        df["days_from_year_ago"] = abs((df["date"] - year_ago_date).dt.days)
        year_ago_row = df.nsmallest(1, "days_from_year_ago").iloc[0]

        if year_ago_row["days_from_year_ago"] > 45:
            return None, None

        year_ago_value = year_ago_row["value"]
        yoy = ((latest_value - year_ago_value) / year_ago_value) * 100

        return round(yoy, 2), latest_date.strftime("%Y-%m-%d")

    except Exception:
        return None, None

# =====================================================
# 辅助函数：处理yfinance数据格式问题
# =====================================================


def clean_yfinance_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    清理yfinance返回的DataFrame，解决MultiIndex等问题。
    V5.8修复：确保索引是DatetimeIndex，不重置索引。
    """
    if df.empty:
        return df

    # 处理MultiIndex列名
    if isinstance(df.columns, pd.MultiIndex):
        # 如果是MultiIndex，取第一层（通常是价格数据）
        df.columns = df.columns.get_level_values(0)

    # 确保所有列名都是字符串
    df.columns = [str(col) for col in df.columns]

    # 标准化列名（转换为小写）
    df.columns = [col.lower() for col in df.columns]

    # 确保索引是DatetimeIndex
    if not isinstance(df.index, pd.DatetimeIndex):
        df.index = pd.to_datetime(df.index)

    # 确保核心列存在且为数值类型
    for col in ['open', 'high', 'low', 'close', 'volume']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    # 删除包含NaN的行
    if 'close' in df.columns:
        df = df.dropna(subset=['close'])

    return df

# =====================================================
# 第一层：宏观环境指标 (已全部升级为V5.1)
# =====================================================

