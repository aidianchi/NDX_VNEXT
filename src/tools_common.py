# tools_common.py
# -*- coding: utf-8 -*-
"""
NDX Agent · 共享工具模块
包含：API配置、常量定义、通用辅助函数
"""

import os
import time
import json
import hashlib
import logging
import requests
import threading
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

# 尝试导入 pandas-datareader：作为轻量 fallback，不替代主数据源口径
try:
    # pandas-datareader 0.10.0 仍使用 pandas 旧版 deprecate_kwarg 调用形式；
    # 在 pandas 3.x 环境下做窄兼容，避免仅因装饰器签名变化导致整个数据层导入失败。
    try:
        import inspect
        import pandas.util._decorators as _pd_decorators

        _deprecate_kwarg_signature = inspect.signature(_pd_decorators.deprecate_kwarg)
        _deprecate_kwarg_params = list(_deprecate_kwarg_signature.parameters)
        if _deprecate_kwarg_params and _deprecate_kwarg_params[0] == "klass":
            _original_deprecate_kwarg = _pd_decorators.deprecate_kwarg

            def _compat_deprecate_kwarg(*args, **kwargs):
                if args and isinstance(args[0], str):
                    return _original_deprecate_kwarg(FutureWarning, *args, **kwargs)
                return _original_deprecate_kwarg(*args, **kwargs)

            _pd_decorators.deprecate_kwarg = _compat_deprecate_kwarg
    except Exception:
        pass

    from pandas_datareader import data as pdr_data
    PANDAS_DATAREADER_AVAILABLE = True
except Exception as exc:
    pdr_data = None
    PANDAS_DATAREADER_AVAILABLE = False
    print(f"[WARN] pandas-datareader不可用，FRED/Stooq轻量备用源将不可用: {str(exc)[:80]}")

# =====================================================
# 配置与常量
# =====================================================

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

ts_manager = TimeSeriesManager(cache_dir=path_config.cache_dir)

DEFAULT_FRED_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
DEFAULT_ALPHAVANTAGE_BASE_URL = "https://www.alphavantage.co/query"
DEFAULT_TWELVE_DATA_BASE_URL = "https://api.twelvedata.com"
YF_FRAME_CACHE_MAX_AGE_SECONDS = 60 * 60 * 24 * 7
YF_FRAME_CACHE_PREFER_MAX_AGE_SECONDS = 60 * 60 * 12
# 退避周期偏长，是为了让 Yahoo 限流（429）窗口有机会自动恢复。
# 2026-05 多次 run 显示：2 秒间隔的重试都落在 Yahoo cooldown 窗口内，反复撞墙。
YF_DOWNLOAD_RETRY_DELAYS_SECONDS = (10, 60)
TWELVE_DATA_PRIORITY_TICKERS = {"QQQ", "HYG"}
YF_RUNTIME_EVENT_LIMIT = 200

_YF_RUNTIME_EVENTS: List[Dict[str, Any]] = []
_YF_RUNTIME_LOCK = threading.Lock()


def reset_yfinance_runtime_diagnostics() -> None:
    """Clear per-run yfinance diagnostics before a collector run."""
    with _YF_RUNTIME_LOCK:
        _YF_RUNTIME_EVENTS.clear()


def _classify_yfinance_failure(message: Optional[str]) -> str:
    text = str(message or "").lower()
    if not text:
        return "unknown"
    if "too many open files" in text or "errno 24" in text:
        return "file_descriptor_exhausted"
    if "sqlite" in text or "database is locked" in text or "database disk image is malformed" in text:
        return "sqlite_cache_error"
    if "429" in text or "rate limit" in text or "ratelimit" in text or "too many requests" in text:
        return "rate_limited"
    if "nameresolutionerror" in text or "temporary failure in name resolution" in text or "nodename nor servname" in text or "dns" in text:
        return "dns_or_network"
    if "empty frame" in text or "empty dataframe" in text or "empty history" in text or "empty info" in text:
        return "empty_response"
    if "yfinance not available" in text or "yfinance unavailable" in text:
        return "provider_unavailable"
    return "provider_error"


def classify_yfinance_failure(message: Optional[str]) -> str:
    return _classify_yfinance_failure(message)


def _record_yfinance_runtime_event(event: Dict[str, Any]) -> None:
    payload = {
        "timestamp_utc": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        **event,
    }
    with _YF_RUNTIME_LOCK:
        _YF_RUNTIME_EVENTS.append(payload)
        if len(_YF_RUNTIME_EVENTS) > YF_RUNTIME_EVENT_LIMIT:
            del _YF_RUNTIME_EVENTS[: len(_YF_RUNTIME_EVENTS) - YF_RUNTIME_EVENT_LIMIT]


def _recent_yfinance_event_matches(ticker: str, *, status: str, failure_type: str) -> bool:
    with _YF_RUNTIME_LOCK:
        recent_events = list(_YF_RUNTIME_EVENTS[-8:])
    for event in reversed(recent_events):
        if str(event.get("ticker") or "") != str(ticker):
            continue
        if str(event.get("status") or "") == status and str(event.get("failure_type") or "") == failure_type:
            return True
    return False


def get_yfinance_runtime_diagnostics() -> Dict[str, Any]:
    """Return a compact, serializable summary of yfinance/cache behavior."""
    with _YF_RUNTIME_LOCK:
        events = [dict(item) for item in _YF_RUNTIME_EVENTS]
    by_status: Dict[str, int] = {}
    by_failure_type: Dict[str, int] = {}
    total_backoff_seconds = 0.0
    for event in events:
        status = str(event.get("status") or "unknown")
        by_status[status] = by_status.get(status, 0) + 1
        failure_type = event.get("failure_type")
        if failure_type:
            failure_key = str(failure_type)
            by_failure_type[failure_key] = by_failure_type.get(failure_key, 0) + 1
        delay = event.get("backoff_seconds")
        if isinstance(delay, (int, float)):
            total_backoff_seconds += float(delay)
    return {
        "yfinance": {
            "event_count": len(events),
            "by_status": by_status,
            "by_failure_type": by_failure_type,
            "total_backoff_seconds": round(total_backoff_seconds, 2),
            "events": events,
        }
    }


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


def get_twelve_data_api_key() -> str:
    return (
        os.getenv("TWELVE_DATA_API_KEY", "").strip()
        or os.getenv("twelve_data_api_key", "").strip()
        or get_api_key("twelve_data")
    )


def get_twelve_data_base_url() -> str:
    return get_base_url("twelve_data") or DEFAULT_TWELVE_DATA_BASE_URL

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


def _yf_persistent_cache_dir() -> str:
    cache_dir = os.path.join(path_config.cache_dir, "yfinance")
    os.makedirs(cache_dir, exist_ok=True)
    return cache_dir


def _yf_cache_slug(cache_key: str) -> str:
    return hashlib.sha1(cache_key.encode("utf-8")).hexdigest()[:24]


def _yf_frame_cache_path(cache_key: str) -> str:
    return os.path.join(_yf_persistent_cache_dir(), f"{_yf_cache_slug(cache_key)}.pkl")


def _yf_info_cache_path(cache_key: str) -> str:
    return os.path.join(_yf_persistent_cache_dir(), f"{_yf_cache_slug(cache_key)}.json")


def _requested_ticker_list(tickers: Any) -> List[str]:
    if isinstance(tickers, (list, tuple, set)):
        return sorted(str(ticker).upper() for ticker in tickers)
    ticker = str(tickers).upper()
    return [ticker] if ticker else []


def _yf_close_frame(frame: pd.DataFrame) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return pd.DataFrame()
    if isinstance(frame.columns, pd.MultiIndex):
        for level in range(frame.columns.nlevels):
            labels = [str(item).lower() for item in frame.columns.get_level_values(level)]
            if "close" in labels:
                try:
                    return frame.xs(frame.columns.get_level_values(level)[labels.index("close")], axis=1, level=level)
                except Exception:
                    return pd.DataFrame()
    for column in frame.columns:
        if str(column).lower() == "close":
            return frame[[column]]
    return pd.DataFrame()


def _yf_frame_cache_usable(frame: pd.DataFrame, requested_tickers: Optional[List[str]] = None) -> bool:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return False
    close = _yf_close_frame(frame)
    if close.empty or close.dropna(how="all").empty:
        return False
    requested = [ticker.upper() for ticker in (requested_tickers or [])]
    if len(requested) <= 1:
        return True
    available = {str(column).upper() for column in close.columns if not close[column].dropna().empty}
    return set(requested).issubset(available)


def _tag_yf_frame_source(
    frame: pd.DataFrame,
    *,
    source_name: str,
    source_code: str,
    cache_layer: Optional[str] = None,
    preserve_existing: bool = False,
) -> pd.DataFrame:
    if not isinstance(frame, pd.DataFrame):
        return frame
    tagged = frame.copy()
    if preserve_existing:
        tagged.attrs.setdefault("source_name", source_name)
        tagged.attrs.setdefault("market_data_source", source_code)
    else:
        tagged.attrs["source_name"] = source_name
        tagged.attrs["market_data_source"] = source_code
    if cache_layer:
        tagged.attrs["cache_layer"] = cache_layer
    return tagged


def _read_yf_frame_cache(
    cache_key: str,
    max_age_seconds: Optional[int] = YF_FRAME_CACHE_MAX_AGE_SECONDS,
    requested_tickers: Optional[List[str]] = None,
) -> pd.DataFrame:
    path = _yf_frame_cache_path(cache_key)
    if not os.path.exists(path):
        return pd.DataFrame()
    try:
        if max_age_seconds is not None:
            age = (datetime.utcnow() - datetime.utcfromtimestamp(os.path.getmtime(path))).total_seconds()
            if age > max_age_seconds:
                logging.warning(
                    "Ignoring expired yfinance frame cache for %s: age %.1f hours exceeds %.1f hours",
                    cache_key,
                    age / 3600,
                    max_age_seconds / 3600,
                )
                return pd.DataFrame()
        cached_df = pd.read_pickle(path)
        if _yf_frame_cache_usable(cached_df, requested_tickers=requested_tickers):
            logging.warning(f"Using recent yfinance frame cache for {cache_key}")
            return _tag_yf_frame_source(
                cached_df,
                source_name="persistent cache",
                source_code="persistent_cache",
                cache_layer="persistent_cache",
                preserve_existing=True,
            )
        logging.warning(f"Ignoring incomplete yfinance frame cache for {cache_key}")
    except Exception as exc:
        logging.warning(f"Failed reading yfinance frame cache {path}: {exc}")
    return pd.DataFrame()


def _write_yf_frame_cache(cache_key: str, frame: pd.DataFrame, requested_tickers: Optional[List[str]] = None) -> None:
    if not _yf_frame_cache_usable(frame, requested_tickers=requested_tickers):
        logging.warning(f"Skipping incomplete yfinance frame cache write for {cache_key}")
        return
    path = _yf_frame_cache_path(cache_key)
    try:
        frame.to_pickle(path)
    except Exception as exc:
        logging.warning(f"Failed writing yfinance frame cache {path}: {exc}")


def _read_yf_info_cache(cache_key: str, max_age_seconds: Optional[int] = None) -> Dict[str, Any]:
    path = _yf_info_cache_path(cache_key)
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            payload = json.load(handle)
        if max_age_seconds is not None:
            cached_at = pd.to_datetime(payload.get("cached_at_utc"), utc=True, errors="coerce")
            if pd.isna(cached_at):
                return {}
            age = (pd.Timestamp.now(tz="UTC") - cached_at).total_seconds()
            if age > max_age_seconds:
                return {}
        value = payload.get("value")
        if isinstance(value, dict) and value:
            logging.warning(f"Using cached yfinance info for {cache_key}")
            return dict(value)
    except Exception as exc:
        logging.warning(f"Failed reading yfinance info cache {path}: {exc}")
    return {}


def _write_yf_info_cache(cache_key: str, value: Dict[str, Any]) -> None:
    if not isinstance(value, dict) or not value:
        return
    path = _yf_info_cache_path(cache_key)
    payload = {
        "cached_at_utc": datetime.utcnow().replace(microsecond=0).isoformat() + "Z",
        "value": value,
    }
    try:
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, default=str)
            handle.write("\n")
    except Exception as exc:
        logging.warning(f"Failed writing yfinance info cache {path}: {exc}")


def _is_twelve_data_priority_download(tickers: Any, interval: str, auto_adjust: bool) -> bool:
    if auto_adjust or interval != "1d":
        return False
    if isinstance(tickers, (list, tuple, set)):
        return False
    ticker = str(tickers).strip().upper()
    return ticker in TWELVE_DATA_PRIORITY_TICKERS


def _previous_weekday(day: pd.Timestamp) -> pd.Timestamp:
    while day.weekday() >= 5:
        day = day - pd.Timedelta(days=1)
    return day


def _latest_completed_us_daily_date(now: Optional[Any] = None) -> pd.Timestamp:
    if now is None:
        current = pd.Timestamp.now(tz="America/New_York")
    else:
        current = pd.Timestamp(now)
        current = current.tz_localize("America/New_York") if current.tzinfo is None else current.tz_convert("America/New_York")

    day = pd.Timestamp(current.date())
    if current.weekday() >= 5:
        return _previous_weekday(day)
    if current.hour < 17:
        return _previous_weekday(day - pd.Timedelta(days=1))
    return day


def _clamp_live_daily_download_end(end: Optional[Any], interval: str) -> Optional[Any]:
    if end is None or interval != "1d":
        return end
    try:
        requested_end = pd.to_datetime(end)
    except Exception:
        return end
    if pd.isna(requested_end):
        return end
    safe_exclusive_end = _latest_completed_us_daily_date() + pd.Timedelta(days=1)
    if requested_end.normalize() > safe_exclusive_end.normalize():
        clamped = safe_exclusive_end.strftime("%Y-%m-%d")
        logging.info("Clamping daily market-data end date from %s to %s until US daily bar is complete", end, clamped)
        return clamped
    return end


def _daily_download_window_has_no_rows(start: Optional[Any], end: Optional[Any], interval: str) -> bool:
    if interval != "1d" or start is None or end is None:
        return False
    try:
        start_day = pd.to_datetime(start).normalize()
        end_day = pd.to_datetime(end).normalize()
    except Exception:
        return False
    if pd.isna(start_day) or pd.isna(end_day):
        return False
    # yfinance treats daily end as exclusive. After live-date clamping, an
    # incremental cache refresh may have no completed daily bar left to fetch.
    return start_day >= end_day


def _format_twelve_date(value: Optional[Any]) -> Optional[str]:
    if value is None:
        return None
    try:
        return pd.to_datetime(value).strftime("%Y-%m-%d")
    except Exception:
        return str(value)


def _fetch_twelve_data_daily_frame(
    ticker: str,
    start: Optional[Any] = None,
    end: Optional[Any] = None,
) -> pd.DataFrame:
    api_key = get_twelve_data_api_key()
    if not api_key:
        return pd.DataFrame()

    params: Dict[str, Any] = {
        "symbol": ticker.upper(),
        "interval": "1day",
        "outputsize": 5000,
        "apikey": api_key,
    }
    start_date = _format_twelve_date(start)
    end_date = _format_twelve_date(end)
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date

    try:
        response = requests.get(
            get_twelve_data_base_url().rstrip("/") + "/time_series",
            params=params,
            proxies=get_requests_proxies(),
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
    except Exception as exc:
        logging.warning("Twelve Data fetch failed for %s: %s", ticker, str(exc)[:120])
        return pd.DataFrame()

    if payload.get("status") == "error":
        logging.warning("Twelve Data returned error for %s: %s", ticker, str(payload.get("message", ""))[:160])
        return pd.DataFrame()

    values = payload.get("values")
    if not isinstance(values, list) or not values:
        return pd.DataFrame()

    frame = pd.DataFrame(values)
    if frame.empty or "datetime" not in frame.columns:
        return pd.DataFrame()

    frame["datetime"] = pd.to_datetime(frame["datetime"], errors="coerce")
    frame = frame.dropna(subset=["datetime"]).set_index("datetime").sort_index()
    frame.index.name = "Date"

    column_map = {
        "open": "Open",
        "high": "High",
        "low": "Low",
        "close": "Close",
        "volume": "Volume",
    }
    frame = frame.rename(columns=column_map)
    wanted = [col for col in ["Open", "High", "Low", "Close", "Volume"] if col in frame.columns]
    frame = frame[wanted]
    for col in wanted:
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna(subset=["Close"])
    if frame.empty:
        return pd.DataFrame()
    if "Adj Close" not in frame.columns:
        frame["Adj Close"] = frame["Close"]
    return _tag_yf_frame_source(
        frame[["Open", "High", "Low", "Close", "Adj Close", "Volume"]],
        source_name="Twelve Data",
        source_code="twelve_data_priority",
    )


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
    if not YF_AVAILABLE and not get_twelve_data_api_key():
        return pd.DataFrame()

    end = _clamp_live_daily_download_end(end, interval)
    requested_tickers = _requested_ticker_list(tickers)
    ticker_key = ",".join(requested_tickers) if len(requested_tickers) > 1 else (requested_tickers[0] if requested_tickers else str(tickers))
    if _daily_download_window_has_no_rows(start, end, interval):
        _record_yfinance_runtime_event({
            "operation": "download",
            "ticker": ticker_key,
            "status": "skipped",
            "source": "window_guard",
            "failure_type": "no_completed_daily_bar",
            "failure_reason": f"daily download window has no completed rows after end clamp: start={start}, end={end}",
            "elapsed_ms": 0.0,
        })
        logging.info(
            "Skipping %s daily download because the clamped window has no completed rows: start=%s, end=%s",
            ticker_key,
            start,
            end,
        )
        return pd.DataFrame()

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
        started = time.monotonic()
        recent = _read_yf_frame_cache(
            cache_key,
            max_age_seconds=YF_FRAME_CACHE_PREFER_MAX_AGE_SECONDS,
            requested_tickers=requested_tickers,
        )
        if not recent.empty:
            if (
                _is_twelve_data_priority_download(tickers, interval, auto_adjust)
                and get_twelve_data_api_key()
                and recent.attrs.get("market_data_source") == "persistent_cache"
            ):
                logging.info(
                    "Refreshing unattributed recent cache for %s before using Twelve Data priority path",
                    ticker_key,
                )
            else:
                _record_yfinance_runtime_event({
                    "operation": "download",
                    "ticker": ticker_key,
                    "status": "cache_hit_recent",
                    "source": "persistent_cache",
                    "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
                })
                return recent

        if _is_twelve_data_priority_download(tickers, interval, auto_adjust) and get_twelve_data_api_key():
            frame = _fetch_twelve_data_daily_frame(ticker_key, start=start, end=end)
            if not frame.empty:
                logging.info("Using Twelve Data priority daily frame for %s", ticker_key)
                _write_yf_frame_cache(cache_key, frame, requested_tickers=requested_tickers)
                _record_yfinance_runtime_event({
                    "operation": "download",
                    "ticker": ticker_key,
                    "status": "provider_success",
                    "source": "twelve_data_priority",
                    "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
                })
                return frame
            _record_yfinance_runtime_event({
                "operation": "download",
                "ticker": ticker_key,
                "status": "fallback_scheduled",
                "source": "twelve_data_priority",
                "failure_type": "empty_response",
                "failure_reason": "Twelve Data priority path returned empty or unusable frame",
                "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
            })

        if not YF_AVAILABLE:
            stale = _read_yf_frame_cache(cache_key, requested_tickers=requested_tickers)
            if not stale.empty:
                _record_yfinance_runtime_event({
                    "operation": "download",
                    "ticker": ticker_key,
                    "status": "cache_fallback",
                    "source": "persistent_cache",
                    "failure_type": "provider_unavailable",
                    "failure_reason": "yfinance not available",
                    "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
                })
                return stale
            _record_yfinance_runtime_event({
                "operation": "download",
                "ticker": ticker_key,
                "status": "failed",
                "source": "yfinance",
                "failure_type": "provider_unavailable",
                "failure_reason": "yfinance not available",
                "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
            })
            return pd.DataFrame()

        last_error: Optional[Exception] = None
        for attempt in range(len(YF_DOWNLOAD_RETRY_DELAYS_SECONDS) + 1):
            empty_reason: Optional[str] = None
            try:
                frame = yf.download(
                    tickers,
                    start=start,
                    end=end,
                    interval=interval,
                    progress=progress,
                    auto_adjust=auto_adjust,
                )
                if _yf_frame_cache_usable(frame, requested_tickers=requested_tickers):
                    frame = _tag_yf_frame_source(
                        frame,
                        source_name="yfinance",
                        source_code="yfinance",
                    )
                    _write_yf_frame_cache(cache_key, frame, requested_tickers=requested_tickers)
                    _record_yfinance_runtime_event({
                        "operation": "download",
                        "ticker": ticker_key,
                        "status": "provider_success",
                        "source": "yfinance",
                        "attempt": attempt + 1,
                        "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
                    })
                    return frame
                # yfinance 1.3+ 内部 catch 了 YFRateLimitError 后只返回 empty df 并 log error。
                # 必须把这种 silent 失败视同 exception 来进入退避，否则限流时一次就放弃。
                empty_reason = "yfinance returned empty frame (likely silent rate limit)"
            except Exception as exc:
                last_error = exc
                empty_reason = f"yfinance raised: {exc}"
            stale = _read_yf_frame_cache(cache_key, requested_tickers=requested_tickers)
            if not stale.empty:
                failure_type = _classify_yfinance_failure(empty_reason)
                _record_yfinance_runtime_event({
                    "operation": "download",
                    "ticker": ticker_key,
                    "status": "cache_fallback",
                    "source": "persistent_cache",
                    "attempt": attempt + 1,
                    "failure_type": failure_type,
                    "failure_reason": str(empty_reason)[:240],
                    "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
                })
                return stale
            if attempt < len(YF_DOWNLOAD_RETRY_DELAYS_SECONDS):
                delay = YF_DOWNLOAD_RETRY_DELAYS_SECONDS[attempt]
                failure_type = _classify_yfinance_failure(empty_reason)
                _record_yfinance_runtime_event({
                    "operation": "download",
                    "ticker": ticker_key,
                    "status": "retry_scheduled",
                    "source": "yfinance",
                    "attempt": attempt + 1,
                    "failure_type": failure_type,
                    "failure_reason": str(empty_reason)[:240],
                    "backoff_seconds": delay,
                    "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
                })
                logging.warning(
                    "yfinance fetch unusable for %s: %s; retrying in %ss",
                    ticker_key,
                    empty_reason,
                    delay,
                )
                time.sleep(delay)
                continue
            logging.warning(
                "yfinance fetch unusable for %s after retries: %s",
                ticker_key,
                empty_reason,
            )
            failure_type = _classify_yfinance_failure(empty_reason)
            _record_yfinance_runtime_event({
                "operation": "download",
                "ticker": ticker_key,
                "status": "failed",
                "source": "yfinance",
                "attempt": attempt + 1,
                "failure_type": failure_type,
                "failure_reason": str(empty_reason)[:240],
                "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
            })
            return pd.DataFrame()
        if last_error:
            logging.warning(f"yfinance download failed for {ticker_key}: {last_error}")
        return pd.DataFrame()

    if not CACHE_AVAILABLE or get_global_cache is None:
        return _fetch()

    cache = get_global_cache()
    if cache is None:
        return _fetch()

    cached_value = cache.get(cache_key)
    if _yf_frame_cache_usable(cached_value, requested_tickers=requested_tickers):
        _record_yfinance_runtime_event({
            "operation": "download",
            "ticker": ticker_key,
            "status": "cache_hit_memory",
            "source": "memory_cache",
            "elapsed_ms": 0.0,
        })
        return _tag_yf_frame_source(
            cached_value,
            source_name="memory cache",
            source_code="memory_cache",
            cache_layer="memory_cache",
            preserve_existing=True,
        )

    fetched = _fetch()
    if _yf_frame_cache_usable(fetched, requested_tickers=requested_tickers):
        cache.set(cache_key, fetched)
        return fetched.copy()
    return pd.DataFrame()


def get_yf_ticker_info_with_retry(ticker: str, attempts: int = 2, pause_seconds: float = 0.8) -> Dict[str, Any]:
    """涓哄鏄撳け璐ョ殑 yfinance.Ticker.info 鎻愪緵杞婚噺閲嶈瘯銆?"""
    if not YF_AVAILABLE:
        _record_yfinance_runtime_event({
            "operation": "ticker.info",
            "ticker": ticker,
            "status": "failed",
            "source": "yfinance",
            "failure_type": "provider_unavailable",
            "failure_reason": "yfinance not available",
        })
        raise RuntimeError("yfinance not available")

    cache_key = f"yf.info:{ticker}"
    last_error: Optional[Exception] = None
    started = time.monotonic()
    for attempt in range(attempts):
        try:
            info = yf.Ticker(ticker).info
            if info and isinstance(info, dict):
                _write_yf_info_cache(cache_key, info)
                _record_yfinance_runtime_event({
                    "operation": "ticker.info",
                    "ticker": ticker,
                    "status": "provider_success",
                    "source": "yfinance",
                    "attempt": attempt + 1,
                    "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
                })
                return info
            raise ValueError(f"Empty info for {ticker}")
        except Exception as exc:
            last_error = exc
            _record_yfinance_runtime_event({
                "operation": "ticker.info",
                "ticker": ticker,
                "status": "retry_scheduled" if attempt < attempts - 1 else "failed",
                "source": "yfinance",
                "attempt": attempt + 1,
                "failure_type": _classify_yfinance_failure(exc),
                "failure_reason": str(exc)[:240],
                "backoff_seconds": pause_seconds if attempt < attempts - 1 else 0,
                "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
            })
            if attempt < attempts - 1:
                time.sleep(pause_seconds)

    cached_info = _read_yf_info_cache(cache_key, max_age_seconds=60 * 60 * 24)
    if cached_info:
        _record_yfinance_runtime_event({
            "operation": "ticker.info",
            "ticker": ticker,
            "status": "cache_fallback",
            "source": "persistent_cache",
            "failure_type": _classify_yfinance_failure(last_error),
            "failure_reason": str(last_error)[:240] if last_error else "",
            "elapsed_ms": round((time.monotonic() - started) * 1000, 1),
        })
        return cached_info
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


def _fetch_fred_series_pdr(
    series_id: str,
    start_date: Optional[Any] = None,
    end_date: Optional[Any] = None,
) -> pd.DataFrame:
    """
    使用 pandas-datareader 读取 FRED 公开 CSV。
    价值：当 FRED API key 缺失或官方 JSON API 短暂失败时，仍保留同一 FRED 序列的轻量 fallback。
    """
    if not PANDAS_DATAREADER_AVAILABLE or pdr_data is None:
        return pd.DataFrame(columns=["date", "value"])

    try:
        start_dt = pd.to_datetime(start_date) if start_date is not None else datetime.now() - timedelta(days=365 * 15)
        end_dt = pd.to_datetime(end_date) if end_date is not None else datetime.now()
        df = pdr_data.DataReader(series_id, "fred", start_dt, end_dt)
        if df is None or df.empty or series_id not in df.columns:
            return pd.DataFrame(columns=["date", "value"])

        out = df[[series_id]].rename(columns={series_id: "value"}).reset_index()
        date_col = "DATE" if "DATE" in out.columns else "date" if "date" in out.columns else out.columns[0]
        out = out.rename(columns={date_col: "date"})
        out["date"] = pd.to_datetime(out["date"])
        out["value"] = pd.to_numeric(out["value"], errors="coerce")
        return out.dropna(subset=["value"])[["date", "value"]]
    except Exception as exc:
        logging.warning(f"pandas-datareader FRED fallback failed for {series_id}: {exc}")
        return pd.DataFrame(columns=["date", "value"])


def _fetch_fred_series(series_id: str, start_date: Optional[Any] = None) -> pd.DataFrame:
    """
    原子化：从 FRED 获取序列，支持 start_date 增量。
    返回包含 ['date', 'value'] 的 DataFrame。
    """
    fred_api_key = get_fred_api_key()
    start_date_str = _normalize_start_date(start_date)
    if not fred_api_key:
        return _fetch_fred_series_pdr(series_id, start_date=start_date_str)

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
        return _fetch_fred_series_pdr(series_id, start_date=start_date_str)

    df = pd.DataFrame(data["observations"])
    if df.empty:
        return _fetch_fred_series_pdr(series_id, start_date=start_date_str)

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

    # cached_yf_download 已经负责 yfinance 空结果/异常的退避重试。
    # 这里保留外层循环只兜底清洗阶段的意外异常，避免把内层 10s/60s 退避重复跑 3 轮。
    for attempt in range(retry_count):
        try:
            logging.info(f"正在获取 {ticker} 数据（尝试 {attempt + 1}/{retry_count}）...")
            df = cached_yf_download(ticker, start=start_str, end=end_str, progress=False, auto_adjust=False)
            df = clean_yfinance_dataframe(df)
            
            if df.empty or "close" not in df.columns:
                if _recent_yfinance_event_matches(ticker, status="skipped", failure_type="no_completed_daily_bar"):
                    logging.info(
                        "%s 今日尚无已完成的美国日线；本次增量请求无新行，后续指标会使用可用缓存或写明数据边界",
                        ticker,
                    )
                else:
                    logging.error(f"{ticker} 返回空数据或缺少 close 列；cached_yf_download 已完成内部退避")
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
    if end_date:
        effective_date = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        effective_date = datetime.now()
    
    start_date_obj = effective_date - timedelta(days=days)

    fred_api_key = get_fred_api_key()
    if not fred_api_key:
        df = _fetch_fred_series_pdr(series_id, start_date=start_date_obj, end_date=effective_date)
        return df if not df.empty else None

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
    df = _fetch_fred_series_pdr(series_id, start_date=start_date_obj, end_date=effective_date)
    return df if not df.empty else None


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
    if end_date:
        effective_date = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        effective_date = datetime.now()

    fred_api_key = get_fred_api_key()
    if not fred_api_key:
        series = _fetch_fred_series_pdr(series_id, end_date=effective_date)
        if series.empty:
            return None, None
        row = series.iloc[-1]
        return float(row["value"]), row["date"].strftime("%Y-%m-%d")

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
    if end_date:
        effective_date = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        effective_date = datetime.now()

    try:
        start_date_obj = effective_date - timedelta(days=lookback_days)
        df = get_fred_series(series_id, days=lookback_days, end_date=effective_date.strftime("%Y-%m-%d"))
        if df is None or df.empty:
            return None, None

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


def calculate_yoy_series(series_id: str, lookback_days: int = 5475, end_date: str = None) -> pd.DataFrame:
    """计算 FRED 序列的同比历史，用于对同比本身做分位。"""
    if end_date:
        effective_date = datetime.strptime(end_date, "%Y-%m-%d")
    else:
        effective_date = datetime.now()

    try:
        raw_days = lookback_days + 430
        df = get_fred_series(series_id, days=raw_days, end_date=effective_date.strftime("%Y-%m-%d"))
        if df is None or df.empty or len(df) < 24:
            return pd.DataFrame(columns=["date", "value"])

        work = df[["date", "value"]].copy()
        work["date"] = pd.to_datetime(work["date"])
        work["value"] = pd.to_numeric(work["value"], errors="coerce")
        work = work.dropna(subset=["value"]).sort_values("date")
        rows: List[Dict[str, Any]] = []
        for _, row in work.iterrows():
            year_ago_date = row["date"] - pd.DateOffset(years=1)
            candidates = work[work["date"] <= row["date"]].copy()
            candidates["days_from_year_ago"] = (candidates["date"] - year_ago_date).abs().dt.days
            year_ago = candidates.nsmallest(1, "days_from_year_ago")
            if year_ago.empty or float(year_ago.iloc[0]["days_from_year_ago"]) > 45:
                continue
            base = float(year_ago.iloc[0]["value"])
            if base == 0:
                continue
            yoy = ((float(row["value"]) - base) / base) * 100
            rows.append({"date": row["date"], "value": round(yoy, 4)})
        if not rows:
            return pd.DataFrame(columns=["date", "value"])
        out = pd.DataFrame(rows)
        start_cutoff = effective_date - timedelta(days=lookback_days)
        return out[out["date"] >= start_cutoff][["date", "value"]]
    except Exception as exc:
        logging.warning(f"calculate_yoy_series failed for {series_id}: {exc}")
        return pd.DataFrame(columns=["date", "value"])

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
