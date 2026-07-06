import os
import sys
import logging
from pathlib import Path

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tools_common


def _disable_twelve_data(monkeypatch):
    monkeypatch.delenv("TWELVE_DATA_API_KEY", raising=False)
    monkeypatch.delenv("twelve_data_api_key", raising=False)
    monkeypatch.setattr(tools_common, "get_twelve_data_api_key", lambda: "")


def test_cached_yf_download_uses_stale_persistent_cache_when_live_fetch_empty(tmp_path: Path, monkeypatch):
    _disable_twelve_data(monkeypatch)
    tools_common.reset_yfinance_runtime_diagnostics()
    monkeypatch.setattr(tools_common.path_config, "cache_dir", str(tmp_path))
    monkeypatch.setattr(tools_common, "YF_AVAILABLE", True)
    monkeypatch.setattr(tools_common, "CACHE_AVAILABLE", False)

    stale = pd.DataFrame({"Close": [100.0]})
    cache_key = ":".join(["yf.download", "QQQ", "2026-01-01", "2026-01-02", "1d", "raw"])
    tools_common._write_yf_frame_cache(cache_key, stale)

    class _YF:
        @staticmethod
        def download(*args, **kwargs):
            return pd.DataFrame()

    monkeypatch.setattr(tools_common, "yf", _YF)

    result = tools_common.cached_yf_download("QQQ", start="2026-01-01", end="2026-01-02")

    assert not result.empty
    assert result.iloc[0]["Close"] == 100.0


def test_cached_yf_download_ignores_expired_persistent_cache_when_live_fetch_empty(tmp_path: Path, monkeypatch):
    _disable_twelve_data(monkeypatch)
    monkeypatch.setattr(tools_common.path_config, "cache_dir", str(tmp_path))
    monkeypatch.setattr(tools_common, "YF_AVAILABLE", True)
    monkeypatch.setattr(tools_common, "CACHE_AVAILABLE", False)
    monkeypatch.setattr(tools_common, "YF_DOWNLOAD_RETRY_DELAYS_SECONDS", ())

    stale = pd.DataFrame({"Close": [100.0]})
    cache_key = ":".join(["yf.download", "QQQ", "2026-01-01", "2026-01-02", "1d", "raw"])
    tools_common._write_yf_frame_cache(cache_key, stale)
    cache_path = Path(tools_common._yf_frame_cache_path(cache_key))
    expired = cache_path.stat().st_mtime - tools_common.YF_FRAME_CACHE_MAX_AGE_SECONDS - 60
    os.utime(cache_path, (expired, expired))

    class _YF:
        @staticmethod
        def download(*args, **kwargs):
            return pd.DataFrame()

    monkeypatch.setattr(tools_common, "yf", _YF)

    result = tools_common.cached_yf_download("QQQ", start="2026-01-01", end="2026-01-02")

    assert result.empty


def test_cached_yf_download_retries_with_long_backoff_when_empty_and_no_stale(
    tmp_path: Path, monkeypatch
):
    """限流场景：yfinance 静默返回 empty df 且无 stale 缓存时，
    cached_yf_download 应进入长退避重试，而不是 2 秒撞墙后立即放弃。"""
    _disable_twelve_data(monkeypatch)
    tools_common.reset_yfinance_runtime_diagnostics()
    monkeypatch.setattr(tools_common.path_config, "cache_dir", str(tmp_path))
    monkeypatch.setattr(tools_common, "YF_AVAILABLE", True)
    monkeypatch.setattr(tools_common, "CACHE_AVAILABLE", False)

    sleeps: list[float] = []
    monkeypatch.setattr(tools_common.time, "sleep", lambda s: sleeps.append(s))

    call_count = {"n": 0}

    class _YF:
        @staticmethod
        def download(*args, **kwargs):
            call_count["n"] += 1
            return pd.DataFrame()

    monkeypatch.setattr(tools_common, "yf", _YF)

    result = tools_common.cached_yf_download("QQQ", start="2026-01-01", end="2026-01-02")

    assert result.empty
    assert call_count["n"] == 3
    assert sleeps == [10, 60]
    diag = tools_common.get_yfinance_runtime_diagnostics()["yfinance"]
    assert diag["by_status"]["retry_scheduled"] == 2
    assert diag["by_status"]["failed"] == 1
    assert diag["by_failure_type"]["rate_limited"] == 3
    assert diag["total_backoff_seconds"] == 70


def test_cached_yf_download_prefers_recent_persistent_cache_before_network(tmp_path: Path, monkeypatch):
    _disable_twelve_data(monkeypatch)
    monkeypatch.setattr(tools_common.path_config, "cache_dir", str(tmp_path))
    monkeypatch.setattr(tools_common, "YF_AVAILABLE", True)
    monkeypatch.setattr(tools_common, "CACHE_AVAILABLE", False)

    cached = pd.DataFrame({"Close": [101.0]})
    cache_key = ":".join(["yf.download", "QQQ", "2026-01-01", "2026-01-02", "1d", "raw"])
    tools_common._write_yf_frame_cache(cache_key, cached)

    class _YF:
        @staticmethod
        def download(*args, **kwargs):
            raise AssertionError("recent persistent cache should avoid live yfinance")

    monkeypatch.setattr(tools_common, "yf", _YF)

    result = tools_common.cached_yf_download("QQQ", start="2026-01-01", end="2026-01-02")

    assert not result.empty
    assert result.iloc[0]["Close"] == 101.0


def test_cached_yf_download_refreshes_unattributed_priority_cache_with_twelve_data(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(tools_common.path_config, "cache_dir", str(tmp_path))
    monkeypatch.setattr(tools_common, "YF_AVAILABLE", True)
    monkeypatch.setattr(tools_common, "CACHE_AVAILABLE", False)
    monkeypatch.setattr(tools_common, "get_twelve_data_api_key", lambda: "test-key")

    cached = pd.DataFrame({"Close": [101.0]})
    cache_key = ":".join(["yf.download", "QQQ", "2026-01-01", "2026-01-03", "1d", "raw"])
    tools_common._write_yf_frame_cache(cache_key, cached)

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "status": "ok",
                "values": [
                    {
                        "datetime": "2026-01-02",
                        "open": "200",
                        "high": "203",
                        "low": "199",
                        "close": "202",
                        "volume": "1234",
                    }
                ],
            }

    class _YF:
        @staticmethod
        def download(*args, **kwargs):
            raise AssertionError("Twelve Data should refresh unattributed priority cache first")

    monkeypatch.setattr(tools_common.requests, "get", lambda *args, **kwargs: _Response())
    monkeypatch.setattr(tools_common, "yf", _YF)

    result = tools_common.cached_yf_download("QQQ", start="2026-01-01", end="2026-01-03")

    assert not result.empty
    assert float(result.iloc[0]["Close"]) == 202.0
    assert result.attrs["source_name"] == "Twelve Data"


def test_cached_yf_download_prefers_twelve_data_for_priority_etf(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(tools_common.path_config, "cache_dir", str(tmp_path))
    monkeypatch.setattr(tools_common, "YF_AVAILABLE", True)
    monkeypatch.setattr(tools_common, "CACHE_AVAILABLE", False)
    monkeypatch.setattr(tools_common, "get_twelve_data_api_key", lambda: "test-key")

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "status": "ok",
                "values": [
                    {
                        "datetime": "2026-01-02",
                        "open": "100",
                        "high": "102",
                        "low": "99",
                        "close": "101",
                        "volume": "1234",
                    }
                ],
            }

    requests_seen = []

    def _fake_get(url, params=None, **kwargs):
        requests_seen.append((url, params))
        return _Response()

    class _YF:
        @staticmethod
        def download(*args, **kwargs):
            raise AssertionError("Twelve Data priority path should avoid yfinance")

    monkeypatch.setattr(tools_common.requests, "get", _fake_get)
    monkeypatch.setattr(tools_common, "yf", _YF)

    result = tools_common.cached_yf_download("QQQ", start="2026-01-01", end="2026-01-03")

    assert not result.empty
    assert float(result.iloc[0]["Close"]) == 101.0
    assert result.attrs["source_name"] == "Twelve Data"
    assert result.attrs["market_data_source"] == "twelve_data_priority"
    assert requests_seen
    assert requests_seen[0][1]["symbol"] == "QQQ"


def test_cached_yf_download_records_twelve_data_fallback_before_yfinance(tmp_path: Path, monkeypatch):
    tools_common.reset_yfinance_runtime_diagnostics()
    monkeypatch.setattr(tools_common.path_config, "cache_dir", str(tmp_path))
    monkeypatch.setattr(tools_common, "YF_AVAILABLE", True)
    monkeypatch.setattr(tools_common, "CACHE_AVAILABLE", False)
    monkeypatch.setattr(tools_common, "get_twelve_data_api_key", lambda: "test-key")

    class _Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {"status": "error", "message": "temporary provider issue"}

    def _fake_get(*args, **kwargs):
        return _Response()

    class _YF:
        @staticmethod
        def download(*args, **kwargs):
            index = pd.to_datetime(["2026-01-02"])
            return pd.DataFrame({"Close": [101.0]}, index=index)

    monkeypatch.setattr(tools_common.requests, "get", _fake_get)
    monkeypatch.setattr(tools_common, "yf", _YF)

    result = tools_common.cached_yf_download("QQQ", start="2026-01-01", end="2026-01-03")

    assert not result.empty
    assert result.attrs["source_name"] == "yfinance"
    diag = tools_common.get_yfinance_runtime_diagnostics()["yfinance"]
    assert diag["by_status"]["fallback_scheduled"] == 1
    assert diag["by_status"]["provider_success"] == 1
    assert diag["events"][0]["source"] == "twelve_data_priority"


def test_cached_yf_download_does_not_use_twelve_data_for_xly_xlp(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(tools_common.path_config, "cache_dir", str(tmp_path))
    monkeypatch.setattr(tools_common, "YF_AVAILABLE", True)
    monkeypatch.setattr(tools_common, "CACHE_AVAILABLE", False)
    monkeypatch.setattr(tools_common, "get_twelve_data_api_key", lambda: "test-key")

    def _unexpected_twelve_data(*args, **kwargs):
        raise AssertionError("XLY/XLP should use yfinance/cache path instead of Twelve Data priority")

    class _YF:
        @staticmethod
        def download(*args, **kwargs):
            index = pd.to_datetime(["2026-01-02"])
            return pd.DataFrame({"Close": [101.0]}, index=index)

    monkeypatch.setattr(tools_common.requests, "get", _unexpected_twelve_data)
    monkeypatch.setattr(tools_common, "yf", _YF)

    result = tools_common.cached_yf_download("XLY", start="2026-01-01", end="2026-01-03")

    assert not result.empty
    assert float(result.iloc[0]["Close"]) == 101.0
    assert result.attrs["source_name"] == "yfinance"


def test_cached_yf_download_clamps_unfinished_us_daily_end(tmp_path: Path, monkeypatch):
    _disable_twelve_data(monkeypatch)
    monkeypatch.setattr(tools_common.path_config, "cache_dir", str(tmp_path))
    monkeypatch.setattr(tools_common, "YF_AVAILABLE", True)
    monkeypatch.setattr(tools_common, "CACHE_AVAILABLE", False)
    monkeypatch.setattr(tools_common, "_latest_completed_us_daily_date", lambda now=None: pd.Timestamp("2026-06-16"))

    seen = {}

    class _YF:
        @staticmethod
        def download(*args, **kwargs):
            seen["end"] = kwargs.get("end")
            index = pd.to_datetime(["2026-06-16"])
            return pd.DataFrame({"Close": [100.0]}, index=index)

    monkeypatch.setattr(tools_common, "yf", _YF)

    result = tools_common.cached_yf_download("HG=F", start="2025-01-01", end="2026-06-18")

    assert not result.empty
    assert seen["end"] == "2026-06-17"


def test_cached_yf_download_skips_when_clamped_daily_window_has_no_rows(tmp_path: Path, monkeypatch):
    _disable_twelve_data(monkeypatch)
    tools_common.reset_yfinance_runtime_diagnostics()
    monkeypatch.setattr(tools_common.path_config, "cache_dir", str(tmp_path))
    monkeypatch.setattr(tools_common, "YF_AVAILABLE", True)
    monkeypatch.setattr(tools_common, "CACHE_AVAILABLE", False)
    monkeypatch.setattr(tools_common, "_latest_completed_us_daily_date", lambda now=None: pd.Timestamp("2026-06-15"))

    class _YF:
        @staticmethod
        def download(*args, **kwargs):
            raise AssertionError("no provider call is needed when the daily window has no completed rows")

    monkeypatch.setattr(tools_common, "yf", _YF)
    monkeypatch.setattr(tools_common.time, "sleep", lambda s: (_ for _ in ()).throw(AssertionError("no retry needed")))

    result = tools_common.cached_yf_download("HG=F", start="2026-06-17", end="2026-06-18")

    assert result.empty
    diag = tools_common.get_yfinance_runtime_diagnostics()["yfinance"]
    assert diag["by_status"]["skipped"] == 1
    assert diag["by_failure_type"]["no_completed_daily_bar"] == 1


def test_fetch_yf_history_logs_unfinished_daily_bar_as_info(tmp_path: Path, monkeypatch, caplog):
    _disable_twelve_data(monkeypatch)
    tools_common.reset_yfinance_runtime_diagnostics()
    monkeypatch.setattr(tools_common.path_config, "cache_dir", str(tmp_path))
    monkeypatch.setattr(tools_common, "YF_AVAILABLE", True)
    monkeypatch.setattr(tools_common, "CACHE_AVAILABLE", False)
    monkeypatch.setattr(tools_common, "_latest_completed_us_daily_date", lambda now=None: pd.Timestamp("2026-06-15"))

    class _YF:
        @staticmethod
        def download(*args, **kwargs):
            raise AssertionError("no provider call is needed when the daily window has no completed rows")

    monkeypatch.setattr(tools_common, "yf", _YF)

    with caplog.at_level(logging.INFO):
        result = tools_common._fetch_yf_history("HG=F", start_date="2026-06-17", end_date="2026-06-17")

    assert result.empty
    assert "今日尚无已完成的美国日线" in caplog.text
    assert "返回空数据或缺少 close 列" not in caplog.text


def test_cached_yf_download_does_not_store_empty_frame_in_memory_cache(tmp_path: Path, monkeypatch):
    _disable_twelve_data(monkeypatch)
    monkeypatch.setattr(tools_common.path_config, "cache_dir", str(tmp_path))
    monkeypatch.setattr(tools_common, "YF_AVAILABLE", True)
    monkeypatch.setattr(tools_common, "CACHE_AVAILABLE", True)
    monkeypatch.setattr(tools_common, "YF_DOWNLOAD_RETRY_DELAYS_SECONDS", ())

    class _MemoryCache:
        def __init__(self):
            self.values = {}

        def get(self, key):
            return self.values.get(key)

        def set(self, key, value):
            self.values[key] = value

    memory_cache = _MemoryCache()
    monkeypatch.setattr(tools_common, "get_global_cache", lambda: memory_cache)

    class _YF:
        calls = 0

        @staticmethod
        def download(*args, **kwargs):
            _YF.calls += 1
            return pd.DataFrame()

    monkeypatch.setattr(tools_common, "yf", _YF)

    first = tools_common.cached_yf_download("QQQ", start="2026-01-01", end="2026-01-02")
    second = tools_common.cached_yf_download("QQQ", start="2026-01-01", end="2026-01-02")

    assert first.empty and second.empty
    assert _YF.calls == 2
    assert memory_cache.values == {}


def test_fetch_yf_history_does_not_repeat_inner_yfinance_backoff(monkeypatch):
    """_fetch_yf_history 不应在 cached_yf_download 的长退避之后再重复外层空结果重试。"""
    monkeypatch.setattr(tools_common, "YF_AVAILABLE", True)

    calls = {"n": 0}
    sleeps: list[float] = []

    def _empty_download(*args, **kwargs):
        calls["n"] += 1
        return pd.DataFrame()

    monkeypatch.setattr(tools_common, "cached_yf_download", _empty_download)
    monkeypatch.setattr(tools_common.time, "sleep", lambda s: sleeps.append(s))

    result = tools_common._fetch_yf_history(
        "QQQ",
        start_date="2026-01-01",
        end_date="2026-01-02",
        retry_count=3,
    )

    assert result.empty
    assert list(result.columns) == ["date", "value"]
    assert calls["n"] == 1
    assert sleeps == []


def test_ticker_info_retry_uses_recent_persistent_cache(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(tools_common.path_config, "cache_dir", str(tmp_path))
    monkeypatch.setattr(tools_common, "YF_AVAILABLE", True)
    tools_common._write_yf_info_cache("yf.info:MSFT", {"marketCap": 123})

    class _BadTicker:
        @property
        def info(self):
            raise RuntimeError("limited")

    class _YF:
        @staticmethod
        def Ticker(_ticker):
            return _BadTicker()

    monkeypatch.setattr(tools_common, "yf", _YF)

    assert tools_common.get_yf_ticker_info_with_retry("MSFT", attempts=1)["marketCap"] == 123


def test_yfinance_runtime_diagnostics_classify_file_handle_and_sqlite():
    tools_common.reset_yfinance_runtime_diagnostics()

    assert tools_common.classify_yfinance_failure("OSError: [Errno 24] Too many open files") == "file_descriptor_exhausted"
    assert tools_common.classify_yfinance_failure("sqlite3.OperationalError: database is locked") == "sqlite_cache_error"
