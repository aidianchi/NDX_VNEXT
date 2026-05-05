import os
import sys

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
    </body></html>
    """

    parsed = tools_L4._parse_trendonify_ndx_pe(html, forward=False)

    assert parsed["source_name"] == "Trendonify"
    assert parsed["metric"] == "ndx_trailing_pe"
    assert parsed["value"] == 34.12
    assert parsed["percentile_10y"] == 86.4
    assert parsed["historical_percentile"] == 86.4
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
    </body></html>
    """

    parsed = tools_L4._parse_trendonify_ndx_pe(html, forward=True)

    assert parsed["source_name"] == "Trendonify"
    assert parsed["metric"] == "ndx_forward_pe"
    assert parsed["value"] == 24.8
    assert parsed["percentile_10y"] == 71.5
    assert parsed["historical_percentile"] == 71.5
    assert parsed["data_date"] == "May 01, 2026"
    assert parsed["availability"] == "available"


def test_trendonify_403_returns_unavailable_without_yfinance_fallback(monkeypatch):
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
