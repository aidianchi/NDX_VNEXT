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
