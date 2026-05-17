import os
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tools_common


def test_cached_yf_download_uses_stale_persistent_cache_when_live_fetch_empty(tmp_path: Path, monkeypatch):
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
