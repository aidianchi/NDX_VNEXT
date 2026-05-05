import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from chart_time_series_artifacts import write_chart_time_series_artifact


class _MiniFrame:
    empty = False

    def __init__(self):
        self.rows = [
            {
                "date": _Date("2026-05-01"),
                "open": 100,
                "high": 103,
                "low": 99,
                "close": 102,
                "volume": 1000,
            },
            {
                "date": _Date("2026-05-04"),
                "open": 102,
                "high": 106,
                "low": 101,
                "close": 105,
                "volume": 1400,
            },
        ]

    def iterrows(self):
        for index, row in enumerate(self.rows):
            yield index, row


class _Date:
    def __init__(self, text):
        self.text = text

    def strftime(self, _format):
        return self.text


def test_write_chart_time_series_artifact_persists_qqq_rows(tmp_path: Path):
    output_path = write_chart_time_series_artifact(
        tmp_path,
        fetcher=lambda lookback_days: _MiniFrame(),
        generated_at="2026-05-05T00:00:00Z",
    )
    payload = json.loads(Path(output_path).read_text(encoding="utf-8"))

    assert output_path == str(tmp_path / "chart_time_series.json")
    assert payload["schema_version"] == "vnext_chart_time_series_v1"
    assert payload["generated_at_utc"] == "2026-05-05T00:00:00Z"
    assert payload["series"]["QQQ_OHLCV"]["source_file"] == "chart_time_series.json"
    assert payload["series"]["QQQ_OHLCV"]["rows"][1]["time"] == "2026-05-04"
    assert payload["series"]["QQQ_OHLCV"]["rows"][1]["ma5"] == 103.5
