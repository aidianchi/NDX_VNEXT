import os
import sys
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
    assert requests_seen
    assert requests_seen[0][1]["symbol"] == "QQQ"


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
