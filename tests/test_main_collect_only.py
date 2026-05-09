import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import main


class _FakeCollector:
    def run(self, backtest_date=None, enable_news=False):
        return {
            "backtest_date": backtest_date,
            "indicators": [
                {"function_id": "get_vix", "raw_data": {"value": {"level": 17.2}}},
            ],
        }


def test_collect_only_exits_after_data_collection(monkeypatch, tmp_path):
    monkeypatch.setattr(main, "DataCollector", lambda: _FakeCollector())
    monkeypatch.setattr(main.path_config, "data_dir", str(tmp_path))

    summary = main.run_collect_only(
        SimpleNamespace(date="2026-05-09", data_json=None, enable_news=False)
    )

    assert summary["mode"] == "collect_only"
    assert summary["indicator_count"] == 1
    assert summary["data_json"].endswith("data_collected_v9_20260509.json")
