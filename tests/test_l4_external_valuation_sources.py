import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tools_L4


def test_trendonify_pe_parser_extracts_value_percentile_and_date():
    html = """
    <html><body>
      <h1>Nasdaq 100 PE Ratio</h1>
      <div>34.12</div>
      <p>Last Updated: May 01, 2026</p>
      <section>
        <h2>Valuation Percentile Rank</h2>
        <div>86.4%</div>
      </section>
      <section>
        <h2>Historical P/E Comparison</h2>
        <table>
          <tr><th>Time Period</th><th>Median PE Ratio</th><th>Percentile Rank</th><th>Valuation</th></tr>
          <tr><td>1 Year</td><td>33.1</td><td>52.4</td><td>Fair Value</td></tr>
          <tr><td>5 Year</td><td>30.2</td><td>74.1</td><td>Overvalued</td></tr>
          <tr><td>10 Year</td><td>26.9</td><td>86.4</td><td>Expensive</td></tr>
          <tr><td>20 Year</td><td>22.4</td><td>92.5</td><td>Expensive</td></tr>
          <tr><td>Since May 1990</td><td>21.2</td><td>88.8</td><td>Expensive</td></tr>
        </table>
      </section>
    </body></html>
    """

    parsed = tools_L4._parse_trendonify_ndx_pe(html, forward=False)

    assert parsed["source_name"] == "Trendonify"
    assert parsed["metric"] == "ndx_trailing_pe"
    assert parsed["value"] == 34.12
    assert parsed["percentile_10y"] == 86.4
    assert parsed["historical_percentile"] == 86.4
    assert parsed["historical_percentiles"]["1y"]["percentile"] == 52.4
    assert parsed["historical_percentiles"]["5y"]["percentile"] == 74.1
    assert parsed["historical_percentiles"]["20y"]["median_pe"] == 22.4
    assert parsed["percentile_5y"] == 74.1
    assert parsed["percentile_20y"] == 92.5
    assert parsed["percentile_since_inception"] == 88.8
    assert parsed["data_date"] == "May 01, 2026"
    assert parsed["availability"] == "available"


def test_trendonify_forward_pe_parser_extracts_value_percentile_and_date():
    html = """
    <html><body>
      <h1>Nasdaq 100 Forward PE Ratio</h1>
      <div>24.8</div>
      <p>Last Updated: May 01, 2026</p>
      <section>
        <h2>Valuation Percentile Rank</h2>
        <div>71.5%</div>
      </section>
      <section>
        <h2>Historical P/E Comparison</h2>
        <p>TIME PERIOD MEDIAN PE RATIO PERCENTILE RANK VALUATION</p>
        <p>1 Year 25.33 16.7 Attractive</p>
        <p>5 Year 24.92 35 Undervalued</p>
        <p>10 Year 22.6 71.5 Overvalued</p>
        <p>20 Year 20.27 71.2 Overvalued</p>
        <p>Since Jun 2002 21.23 64.9 Overvalued</p>
      </section>
    </body></html>
    """

    parsed = tools_L4._parse_trendonify_ndx_pe(html, forward=True)

    assert parsed["source_name"] == "Trendonify"
    assert parsed["metric"] == "ndx_forward_pe"
    assert parsed["value"] == 24.8
    assert parsed["percentile_10y"] == 71.5
    assert parsed["historical_percentile"] == 71.5
    assert parsed["historical_percentiles"]["1y"]["valuation"] == "Attractive"
    assert parsed["historical_percentiles"]["5y"]["percentile"] == 35.0
    assert parsed["historical_percentiles"]["since_inception"]["percentile"] == 64.9
    assert parsed["data_date"] == "May 01, 2026"
    assert parsed["availability"] == "available"


def test_trendonify_403_returns_unavailable_without_yfinance_fallback(tmp_path, monkeypatch):
    monkeypatch.setattr(tools_L4.path_config, "output_dir", str(tmp_path))

    def fake_fetch(url, timeout=8):
        if "trendonify" in url:
            return None, "403 Forbidden"
        return None, "skip other source"

    monkeypatch.setattr(tools_L4, "_fetch_text", fake_fetch)

    checks = tools_L4.get_ndx_valuation_third_party_checks()
    trendonify = [item for item in checks if str(item.get("source_id", "")).startswith("trendonify")]

    assert trendonify
    assert all(item["availability"] == "unavailable" for item in trendonify)
    assert all(item["source_tier"] == "unavailable" for item in trendonify)
    assert all("403" in item["unavailable_reason"] for item in trendonify)
    assert all(item["value"] is None for item in trendonify)


def test_trendonify_403_uses_user_trusted_browser_sidecar(tmp_path, monkeypatch):
    monkeypatch.setattr(tools_L4.path_config, "output_dir", str(tmp_path))
    sidecar_path = tmp_path / "browser_sidecar" / "trendonify_ndx_valuation.json"
    sidecar_path.parent.mkdir(parents=True)
    sidecar_path.write_text(
        json.dumps(
            {
                "schema_version": "browser_sidecar_v1",
                "source": "trendonify_ndx_valuation",
                "generated_at_utc": "2026-05-11T12:00:00Z",
                "pages": [
                    {
                        "page_type": "trailing_pe",
                        "collected_at_utc": "2026-05-11T12:00:00Z",
                        "user_trusted": True,
                        "preserved_after_failed_refresh_at_utc": "2026-05-12T13:05:40Z",
                        "latest_failed_refresh": {"parse_status": "unavailable"},
                        "parsed": {
                            "source_id": "trendonify_pe",
                            "source_name": "Trendonify",
                            "source_url": "https://trendonify.com/united-states/stock-market/nasdaq-100/pe-ratio",
                            "source_tier": "third_party_estimate",
                            "metric": "ndx_trailing_pe",
                            "value": 38.07,
                            "unit": "ratio",
                            "percentile_10y": 100.0,
                            "historical_percentile": 100.0,
                            "availability": "available",
                            "methodology": "Published PE",
                        },
                    },
                    {
                        "page_type": "forward_pe",
                        "collected_at_utc": "2026-05-11T12:00:00Z",
                        "user_trusted": True,
                        "parsed": {
                            "source_id": "trendonify_forward_pe",
                            "source_name": "Trendonify",
                            "source_url": "https://trendonify.com/united-states/stock-market/nasdaq-100/forward-pe-ratio",
                            "source_tier": "third_party_estimate",
                            "metric": "ndx_forward_pe",
                            "value": 23.73,
                            "unit": "ratio",
                            "percentile_10y": 57.5,
                            "historical_percentile": 57.5,
                            "availability": "available",
                            "methodology": "Published forward PE",
                        },
                    },
                ],
                "source_errors": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    def fake_fetch(url, timeout=8):
        if "trendonify" in url:
            return None, "403 Forbidden"
        return None, "skip other source"

    monkeypatch.setattr(tools_L4, "_fetch_text", fake_fetch)

    checks = tools_L4.get_ndx_valuation_third_party_checks()
    by_id = {item["source_id"]: item for item in checks}

    assert by_id["trendonify_pe"]["availability"] == "available"
    assert by_id["trendonify_pe"]["value"] == 38.07
    assert by_id["trendonify_pe"]["historical_percentile"] == 100.0
    assert by_id["trendonify_pe"]["browser_sidecar"]["user_trusted"] is True
    assert by_id["trendonify_pe"]["browser_sidecar"]["preserved_after_failed_refresh_at_utc"] == "2026-05-12T13:05:40Z"
    assert by_id["trendonify_forward_pe"]["value"] == 23.73


def test_untrusted_trendonify_browser_sidecar_is_ignored(tmp_path, monkeypatch):
    monkeypatch.setattr(tools_L4.path_config, "output_dir", str(tmp_path))
    sidecar_path = tmp_path / "browser_sidecar" / "trendonify_ndx_valuation.json"
    sidecar_path.parent.mkdir(parents=True)
    sidecar_path.write_text(
        json.dumps(
            {
                "schema_version": "browser_sidecar_v1",
                "source": "trendonify_ndx_valuation",
                "pages": [
                    {
                        "page_type": "trailing_pe",
                        "user_trusted": False,
                        "parsed": {
                            "source_id": "trendonify_pe",
                            "source_name": "Trendonify",
                            "value": 38.07,
                            "availability": "available",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(tools_L4, "_fetch_text", lambda url, timeout=8: (None, "403 Forbidden"))

    checks = tools_L4.get_ndx_valuation_third_party_checks()
    trendonify = [item for item in checks if item.get("source_id") == "trendonify_pe"][0]

    assert trendonify["availability"] == "unavailable"
    assert trendonify["value"] is None


def test_worldperatio_parser_extracts_pe_date_and_methodology_without_fake_percentile():
    html = """
    <html><body>
      <h1>Nasdaq 100 PE Ratio</h1>
      <div>P/E Ratio</div>
      <div>32.27</div>
      <p>01 May 2026</p>
      <p>The estimated P/E Ratio is based on the QQQ ETF.</p>
      <p>Rolling average and outlier normalization are used to smooth unusual readings.</p>
      <p>Valuation range: low, fair, high.</p>
    </body></html>
    """

    parsed = tools_L4._parse_worldperatio_ndx_pe(html)

    assert parsed["source_name"] == "WorldPERatio"
    assert parsed["metric"] == "ndx_trailing_pe"
    assert parsed["value"] == 32.27
    assert parsed["data_date"] == "01 May 2026"
    assert "rolling average" in parsed["methodology"].lower()
    assert parsed["percentile_10y"] is None
    assert parsed["historical_percentile"] is None
    assert "does not provide explicit percentile" in parsed["unavailable_reason"]


def test_worldperatio_parser_structures_stddev_windows_and_trend_context():
    html = """
    <html><body>
      <h1>Nasdaq 100 PE Ratio</h1>
      <div>P/E Ratio</div>
      <div>32.27</div>
      <p>01 May 2026</p>
      <section>
        <h2>1 Year Rolling Average</h2>
        <p>Average PE: 31.5</p>
        <p>Standard Deviation: 2.1</p>
        <p>Fair Value Range: 29.4 - 33.6</p>
        <p>Deviation from mean: 0.37 sigma</p>
        <p>Valuation: Fair</p>
      </section>
      <section>
        <h2>10 Year Rolling Average</h2>
        <p>Average PE: 26.8</p>
        <p>Standard Deviation: 3.2</p>
        <p>Fair Value Range: 23.6 - 30.0</p>
        <p>Deviation from mean: 1.71 sigma</p>
        <p>Valuation: Overvalued</p>
      </section>
      <p>50 Day SMA margin: 3.4%</p>
      <p>200 Day SMA margin: 12.6%</p>
    </body></html>
    """

    parsed = tools_L4._parse_worldperatio_ndx_pe(html)
    relative_position = parsed["relative_position"]

    assert relative_position["position_type"] == "std_dev_context_not_percentile"
    assert relative_position["percentile_is_explicit"] is False
    assert relative_position["valuation_windows"]["1y"]["average_pe"] == 31.5
    assert relative_position["valuation_windows"]["1y"]["std_dev"] == 2.1
    assert relative_position["valuation_windows"]["1y"]["range_low"] == 29.4
    assert relative_position["valuation_windows"]["1y"]["range_high"] == 33.6
    assert relative_position["valuation_windows"]["1y"]["deviation_vs_mean_sigma"] == 0.37
    assert relative_position["valuation_windows"]["1y"]["valuation_label"] == "Fair"
    assert relative_position["valuation_windows"]["10y"]["valuation_label"] == "Overvalued"
    assert relative_position["trend_context"]["sma50_margin_pct"] == 3.4
    assert relative_position["trend_context"]["sma200_margin_pct"] == 12.6
    assert parsed["historical_percentile"] is None


def test_worldperatio_parser_handles_current_last_periods_table():
    html = """
    <html><body>
      <h1>Nasdaq 100 Index: current P/E Ratio</h1>
      <div>P/E Ratio</div>
      <div>32.54</div>
      <p>11 May 2026</p>
      <section>
        <h2>Last Periods metrics</h2>
        <p>Period Average P/E (μ) Std Dev (σ) Std Dev Range vs Current P/E Deviation vs μ Valuation</p>
        <p>Last 1Y 33.16 0.74 [31.68 · 32.42 , 33.89 · 34.63] -0.84 σ Fair</p>
        <p>Last 5Y 30.21 2.92 [24.38 · 27.30 , 33.13 · 36.04] +0.80 σ Fair</p>
        <p>Last 10Y 26.95 4.03 [18.90 · 22.92 , 30.98 · 35.01] +1.39 σ Overvalued</p>
        <p>Last 20Y 22.44 5.38 [11.69 · 17.07 , 27.82 · 33.19] +1.88 σ Overvalued</p>
      </section>
    </body></html>
    """

    parsed = tools_L4._parse_worldperatio_ndx_pe(html)
    windows = parsed["relative_position"]["valuation_windows"]

    assert parsed["value"] == 32.54
    assert parsed["data_date"] == "11 May 2026"
    assert windows["1y"]["average_pe"] == 33.16
    assert windows["1y"]["std_dev"] == 0.74
    assert windows["1y"]["range_low"] == 32.42
    assert windows["1y"]["range_high"] == 33.89
    assert windows["1y"]["range_2std_low"] == 31.68
    assert windows["10y"]["deviation_vs_mean_sigma"] == 1.39
    assert windows["10y"]["valuation_label"] == "Overvalued"


def test_worldperatio_parser_only_uses_explicit_percentile_when_present():
    html = """
    <html><body>
      <h1>Nasdaq 100 PE Ratio</h1>
      <div>P/E Ratio</div>
      <div>32.27</div>
      <p>01 May 2026</p>
      <p>The estimated P/E Ratio is based on the QQQ ETF.</p>
      <p>Historical Percentile Rank</p>
      <strong>74.2%</strong>
    </body></html>
    """

    parsed = tools_L4._parse_worldperatio_ndx_pe(html)

    assert parsed["percentile_10y"] == 74.2
    assert parsed["historical_percentile"] == 74.2
    assert parsed["unavailable_reason"] is None
