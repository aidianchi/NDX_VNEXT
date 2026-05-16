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
    assert "data-indicator-toggle=\"ma20\"" in html
    assert "data-preset=\"simple_price\"" in html
    assert "时间轴锁定" in html
    assert "统一时间轴" in html
    assert "moduleSummaries" in html
    assert "PRICE_SCALE_WIDTH = 112" in html
    assert "minimumWidth: PRICE_SCALE_WIDTH" in html
    assert "updateActiveModuleChrome" in html
    assert "moduleReadoutHtml" in html
    assert "findPointAtOrBefore" in html
    assert "function timeKey(value)" in html
    assert "Latest · " in html
    assert "<dt>MA20</dt>" in html
    assert "<dt>VWAP20</dt>" in html


def test_interactive_chart_workbench_renders_research_modules_and_l5_subpanels(tmp_path: Path):
    run_dir = tmp_path / "run"
    _write_json(run_dir / "layer_cards" / "L5.json", {"layer": "L5", "local_conclusion": "价格技术模块。"})
    _write_json(run_dir / "analysis_packet.json", {})
    rows = []
    for index in range(40):
        rows.append(
            {
                "time": f"2026-04-{index + 1:02d}",
                "open": 100 + index,
                "high": 103 + index,
                "low": 98 + index,
                "close": 101 + index,
                "volume": 1000 + index,
                "ma5": 99 + index,
                "ma20": 95 + index,
                "ma60": 90 + index,
                "ma200": 80 + index,
                "bb_upper": 105 + index,
                "bb_lower": 93 + index,
                "donchian_upper": 106 + index,
                "donchian_lower": 92 + index,
                "vwap20": 97 + index,
                "obv": index * 1000,
                "macd": 1.2,
                "macd_signal": 1.0,
                "macd_histogram": 0.2,
                "rsi14": 61,
                "atr14": 4.4,
                "mfi14": 58,
                "cmf20": 0.12,
            }
        )
    _write_json(
        run_dir / "chart_time_series.json",
        {
            "schema_version": "vnext_chart_time_series_v1",
            "workbench_modules": {
                "price_technical": {"title": "价格技术", "series": ["QQQ_OHLCV"], "layer_tags": ["L5"]},
                "volatility_credit": {"title": "波动信用", "series": ["VIX", "VXN", "HY_OAS", "IG_OAS"], "layer_tags": ["L2"]},
                "rates_valuation": {"title": "利率估值", "series": ["US10Y", "DAMODARAN_ERP_MONTHLY"], "layer_tags": ["L1", "L4"]},
                "breadth_concentration": {"title": "广度集中度", "series": ["QQQ_QQEW_RATIO"], "layer_tags": ["L3"]},
                "liquidity": {"title": "流动性", "series": ["NET_LIQUIDITY", "WALCL", "TGA", "RRP"], "layer_tags": ["L1"]},
            },
            "series": {
                "QQQ_OHLCV": {"source_file": "chart_time_series.json", "rows": rows},
                "VIX": {"rows": [{"time": "2026-04-01", "value": 18}]},
                "VXN": {"rows": [{"time": "2026-04-01", "value": 23}]},
                "HY_OAS": {"rows": [{"time": "2026-04-01", "value": 2.8}]},
                "IG_OAS": {"rows": [{"time": "2026-04-01", "value": 0.8}]},
                "US10Y": {"rows": [{"time": "2026-04-01", "value": 4.4}]},
                "DAMODARAN_ERP_MONTHLY": {"rows": [{"time": "2026-04-01", "value": 4.2}]},
                "QQQ_QQEW_RATIO": {"rows": [{"time": "2026-04-01", "value": 4.8}]},
                "NET_LIQUIDITY": {"rows": [{"time": "2026-04-01", "value": 6100}]},
                "WALCL": {"rows": [{"time": "2026-04-01", "value": 7600}]},
                "TGA": {"rows": [{"time": "2026-04-01", "value": 600}]},
                "RRP": {"rows": [{"time": "2026-04-01", "value": 900}]},
            },
        },
    )
    generator = InteractiveChartWorkbenchGenerator(
        reports_dir=str(tmp_path / "reports"),
        bundle_js="window.LightweightCharts={createChart:function(){return {addSeries:function(){return {setData:function(){},priceScale:function(){return {applyOptions:function(){}}}}},timeScale:function(){return {fitContent:function(){},setVisibleLogicalRange:function(){}}},subscribeCrosshairMove:function(){},applyOptions:function(){}}},CandlestickSeries:function(){},LineSeries:function(){},HistogramSeries:function(){},AreaSeries:function(){}};",
    )

    report_path = generator.run(run_dir, modules=["price_technical", "volatility_credit", "rates_valuation", "breadth_concentration", "liquidity"])
    html = Path(report_path).read_text(encoding="utf-8")

    assert 'data-module-tab="price_technical"' in html
    assert 'data-module="volatility_credit"' in html
    assert 'subpanel-grid is-time-synced' in html
    assert 'data-panel-root="macd"' in html
    assert 'data-panel-root="money-flow"' in html
    assert 'data-pane-toggle="macd"' in html
    assert 'data-module-normalize="rates_valuation"' in html
    assert 'data-module-dual-axis="liquidity"' in html
    assert 'data-module-legend="volatility_credit"' in html
    assert "Bollinger" in html
    assert "Donchian" in html
    assert "VWAP" in html
    assert "overlay_volume" in html
    assert "subscribeVisibleLogicalRangeChange" in html
    assert "setVisibleTimeRangeAll" in html
    assert "updateRange(3650)" in html
    assert "if (!item.primaryData || !item.primaryData.length) return;" in html
    assert "try {\n        timeScale.setVisibleRange({ from, to });" in html
    assert "setCrosshairPosition" in html
    assert "timeFromCrosshair" in html
    assert "Donchian H" in html
    assert "MACD</dt>" in html
    assert "Signal</dt>" in html
    assert "let syncLocked = false" in html
    assert "syncLocked = true;\nchart.timeScale().fitContent();" in html
    assert "function unregisterChart(chart)" in html
    assert "unregisterChart(moduleCharts[moduleKey]);" in html
    assert "syncedCharts.forEach(item => item.timeScale().fitContent())" not in html
    assert 'data-price-module-only' in html
    assert 'id="summaryValueB"' in html
    assert "VIX" in html
    assert "Damodaran ERP" in html
    assert "QQQ/QQEW" in html
    assert "Net Liquidity" in html


def test_interactive_chart_workbench_prefers_run_time_series_artifact(tmp_path: Path, monkeypatch):
    run_dir = tmp_path / "run"
    _write_json(run_dir / "layer_cards" / "L5.json", {"layer": "L5", "local_conclusion": "artifact 同源。"})
    _write_json(run_dir / "analysis_packet.json", {})
    _write_json(
        run_dir / "chart_time_series.json",
        {
            "schema_version": "vnext_chart_time_series_v1",
            "series": {
                "QQQ_OHLCV": {
                    "source_file": "chart_time_series.json",
                    "rows": [
                        {"time": "2026-05-01", "open": 100, "high": 102, "low": 98, "close": 101, "volume": 1000},
                        {"time": "2026-05-04", "open": 101, "high": 105, "low": 100, "close": 104, "volume": 1500},
                    ],
                }
            },
        },
    )
    generator = InteractiveChartWorkbenchGenerator(
        reports_dir=str(tmp_path / "reports"),
        bundle_js="window.LightweightCharts={createChart:function(){return {addSeries:function(){return {setData:function(){}}},timeScale:function(){return {fitContent:function(){}}},subscribeCrosshairMove:function(){},applyOptions:function(){}}},CandlestickSeries:function(){},LineSeries:function(){},HistogramSeries:function(){}};",
    )
    monkeypatch.setattr(generator, "_fetch_price_rows", lambda lookback_days: (_ for _ in ()).throw(AssertionError("should use artifact rows")))

    report_path = generator.run(run_dir)
    html = Path(report_path).read_text(encoding="utf-8")

    assert "chart_time_series.json" in html
    assert "artifact 同源" in html
    assert '"time": "2026-05-04"' in html
    assert '"close": 104.0' in html


def test_interactive_chart_workbench_falls_back_to_latest_cached_price_rows(tmp_path: Path, monkeypatch):
    run_root = tmp_path / "vnext"
    run_dir = run_root / "20260513_191253"
    cached_run = run_root / "20260512_215333_collect_only"
    _write_json(run_dir / "layer_cards" / "L5.json", {"layer": "L5", "local_conclusion": "当前 run 价格序列为空。"})
    _write_json(run_dir / "analysis_packet.json", {})
    _write_json(
        run_dir / "chart_time_series.json",
        {"series": {"QQQ_OHLCV": {"source_file": "chart_time_series.json", "rows": []}}},
    )
    _write_json(
        cached_run / "chart_time_series.json",
        {
            "series": {
                "QQQ_OHLCV": {
                    "source_file": "chart_time_series.json",
                    "rows": [
                        {"time": "2026-05-01", "open": 100, "high": 102, "low": 98, "close": 101, "volume": 1000},
                        {"time": "2026-05-04", "open": 101, "high": 105, "low": 100, "close": 104, "volume": 1500},
                    ],
                }
            }
        },
    )
    generator = InteractiveChartWorkbenchGenerator(
        reports_dir=str(tmp_path / "reports"),
        bundle_js="window.LightweightCharts={createChart:function(){return {addSeries:function(){return {setData:function(){}}},timeScale:function(){return {fitContent:function(){}}},subscribeCrosshairMove:function(){},applyOptions:function(){}}},CandlestickSeries:function(){},LineSeries:function(){},HistogramSeries:function(){}};",
    )
    monkeypatch.setattr(generator, "_fetch_price_rows", lambda lookback_days: [])

    report_path = generator.run(run_dir)
    html = Path(report_path).read_text(encoding="utf-8")

    assert "cached fallback: 20260512_215333_collect_only/chart_time_series.json" in html
    assert '"candles": [{"time": "2026-05-01"' in html
    assert '"close": 104.0' in html
    assert "data-warning-banner" in html
    assert "价格数据来自缓存回退" in html
    assert "data-warning-warn" in html


def test_interactive_chart_workbench_shows_empty_series_warnings(tmp_path: Path):
    run_dir = tmp_path / "run"
    _write_json(run_dir / "layer_cards" / "L5.json", {"layer": "L5", "local_conclusion": "价格技术模块。"})
    _write_json(run_dir / "analysis_packet.json", {})
    rows = [
        {"time": "2026-05-01", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 1000, "ma5": 99, "ma20": 95, "ma60": 90, "ma200": 80},
    ]
    _write_json(
        run_dir / "chart_time_series.json",
        {
            "schema_version": "vnext_chart_time_series_v1",
            "workbench_modules": {
                "price_technical": {"title": "价格技术", "series": ["QQQ_OHLCV", "VIX"], "layer_tags": ["L5"]},
            },
            "series": {
                "QQQ_OHLCV": {"source_file": "chart_time_series.json", "rows": rows},
                "VIX": {"rows": []},
                "HYG": {"rows": []},
            },
        },
    )
    generator = InteractiveChartWorkbenchGenerator(
        reports_dir=str(tmp_path / "reports"),
        bundle_js="window.LightweightCharts={createChart:function(){return {addSeries:function(){return {setData:function(){}}},timeScale:function(){return {fitContent:function(){}}},subscribeCrosshairMove:function(){},applyOptions:function(){}}},CandlestickSeries:function(){},LineSeries:function(){},HistogramSeries:function(){}};",
    )

    report_path = generator.run(run_dir)
    html = Path(report_path).read_text(encoding="utf-8")

    assert "data-warning-banner" in html
    assert "以下序列无数据" in html
    assert "VIX" in html
    assert "HYG" in html


def test_interactive_chart_workbench_tolerates_missing_l5_indicator_values(tmp_path: Path):
    run_dir = tmp_path / "run"
    _write_json(run_dir / "layer_cards" / "L5.json", {"layer": "L5", "local_conclusion": "L5 数据缺口。"})
    _write_json(
        run_dir / "analysis_packet.json",
        {
            "raw_data": {
                "L5": {
                    "get_multi_scale_ma_position": {"value": None},
                    "get_qqq_technical_indicators": {"value": None},
                }
            }
        },
    )
    rows = [
        {"time": "2026-05-01", "open": 100, "high": 102, "low": 99, "close": 101, "volume": 1000},
        {"time": "2026-05-04", "open": 101, "high": 103, "low": 100, "close": 102, "volume": 1100},
    ]

    generator = InteractiveChartWorkbenchGenerator(
        reports_dir=str(tmp_path / "reports"),
        bundle_js="window.LightweightCharts={createChart:function(){return {addSeries:function(){return {setData:function(){}}},timeScale:function(){return {fitContent:function(){}}},subscribeCrosshairMove:function(){},applyOptions:function(){}}},CandlestickSeries:function(){},LineSeries:function(){},HistogramSeries:function(){}};",
    )

    report_path = generator.run(run_dir, price_rows=rows)
    html = Path(report_path).read_text(encoding="utf-8")

    assert "L5 数据缺口" in html
    assert '"current_price": null' in html
