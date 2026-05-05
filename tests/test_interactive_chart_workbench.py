import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from interactive_chart_workbench import InteractiveChartWorkbenchGenerator


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_interactive_chart_workbench_generates_lightweight_chart_html(tmp_path: Path):
    run_dir = tmp_path / "run"
    _write_json(
        run_dir / "layer_cards" / "L5.json",
        {
            "layer": "L5",
            "local_conclusion": "趋势偏强但超买。",
            "indicator_analyses": [
                {
                    "function_id": "get_multi_scale_ma_position",
                    "metric": "QQQ Multi-Scale MA Position",
                    "current_reading": "价格674.15，均线多头排列",
                    "normalized_state": "bullish_alignment",
                    "narrative": "趋势结构偏强。",
                    "reasoning_process": "",
                    "first_principles_chain": [],
                    "cross_layer_implications": [],
                    "risk_flags": [],
                }
            ],
        },
    )
    _write_json(
        run_dir / "analysis_packet.json",
        {
            "raw_data": {
                "L5": {
                    "get_multi_scale_ma_position": {
                        "value": {
                            "current_price": 106,
                            "ma_positions": {
                                "ma5": {"value": 104, "deviation_pct": 1.9},
                                "ma20": {"value": 101, "deviation_pct": 5.0},
                            },
                        }
                    }
                }
            }
        },
    )
    price_rows = [
        {"time": "2026-05-01", "open": 100, "high": 106, "low": 99, "close": 105, "volume": 1000},
        {"time": "2026-05-02", "open": 105, "high": 108, "low": 104, "close": 106, "volume": 1200},
    ]

    generator = InteractiveChartWorkbenchGenerator(
        reports_dir=str(tmp_path / "reports"),
        bundle_js="window.LightweightCharts={createChart:function(){return {addSeries:function(){return {setData:function(){}}},timeScale:function(){return {fitContent:function(){}}},subscribeCrosshairMove:function(){},applyOptions:function(){}}},CandlestickSeries:function(){},LineSeries:function(){},HistogramSeries:function(){}};",
    )
    report_path = generator.run(run_dir, price_rows=price_rows)
    html = Path(report_path).read_text(encoding="utf-8")

    assert "vNext Interactive Chart Workbench" in html
    assert 'data-chart-root="qqq-price-action"' in html
    assert "LightweightCharts.createChart" in html
    assert '"candles"' in html
    assert '"volume"' in html
    assert '"ma5"' in html
    assert "趋势偏强但超买" in html
    assert "artifact + QQQ OHLCV" in html
