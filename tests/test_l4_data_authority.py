import os
import sys
from io import BytesIO
from xml.sax.saxutils import escape
from zipfile import ZipFile, ZIP_DEFLATED

import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import tools_L4


def _minimal_xlsx(rows):
    """Build a tiny inline-string XLSX without relying on openpyxl in test env."""
    def cell_ref(row_idx, col_idx):
        col = ""
        n = col_idx
        while n:
            n, rem = divmod(n - 1, 26)
            col = chr(65 + rem) + col
        return f"{col}{row_idx}"

    row_xml = []
    for row_idx, row in enumerate(rows, start=1):
        cells = []
        for col_idx, value in enumerate(row, start=1):
            ref = cell_ref(row_idx, col_idx)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                cells.append(f'<c r="{ref}"><v>{value}</v></c>')
            else:
                cells.append(f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(value))}</t></is></c>')
        row_xml.append(f'<row r="{row_idx}">{"".join(cells)}</row>')

    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>
  <Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>
</Types>""",
        )
        zf.writestr(
            "_rels/.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>
</Relationships>""",
        )
        zf.writestr(
            "xl/workbook.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"
          xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <sheets><sheet name="Historical ERP" sheetId="1" r:id="rId1"/></sheets>
</workbook>""",
        )
        zf.writestr(
            "xl/_rels/workbook.xml.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>
</Relationships>""",
        )
        zf.writestr(
            "xl/worksheets/sheet1.xml",
            f"""<?xml version="1.0" encoding="UTF-8"?>
<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">
  <sheetData>{''.join(row_xml)}</sheetData>
</worksheet>""",
        )
    return buffer.getvalue()


def test_weighted_metrics_use_aggregate_earnings_and_fcf_with_coverage():
    df = pd.DataFrame(
        [
            {
                "ticker": "AAA",
                "market_cap": 100.0,
                "trailing_pe": 10.0,
                "forward_pe": 20.0,
                "fcf": 8.0,
                "weight": 0.2,
            },
            {
                "ticker": "BBB",
                "market_cap": 300.0,
                "trailing_pe": 30.0,
                "forward_pe": 15.0,
                "fcf": 12.0,
                "weight": 0.6,
            },
            {
                "ticker": "CCC",
                "market_cap": 100.0,
                "trailing_pe": -5.0,
                "forward_pe": None,
                "fcf": None,
                "weight": 0.2,
            },
        ]
    )

    metrics = tools_L4.calculate_weighted_metrics(df)

    assert metrics["weighted_trailing_pe"] == 20.0
    assert metrics["weighted_forward_pe"] == 16.0
    assert metrics["weighted_earnings_yield"] == 5.0
    assert metrics["weighted_forward_earnings_yield"] == 6.25
    assert metrics["weighted_fcf_yield"] == 5.0
    assert metrics["coverage"]["trailing_pe"]["market_cap_coverage_pct"] == 80.0
    assert metrics["coverage"]["forward_pe"]["constituent_coverage_pct"] == 66.67
    assert any(item["ticker"] == "CCC" for item in metrics["anomalies"])


def test_simple_yield_gap_is_not_labeled_as_implied_erp(monkeypatch):
    monkeypatch.setattr(
        tools_L4,
        "get_ndx_pe_and_earnings_yield",
        lambda end_date=None: {
            "name": "NDX Valuation",
            "value": {"EarningsYield": 4.0, "FCFYield": 3.5},
            "data_quality": {"source_tier": "component_model"},
        },
    )
    monkeypatch.setattr(
        tools_L4,
        "get_10y_treasury",
        lambda end_date=None: {"value": {"level": 4.25}},
    )

    result = tools_L4.get_equity_risk_premium("2026-04-30")

    assert result["name"] == "NDX Simple Yield Gap"
    assert result["series_id"] == "SIMPLE_YIELD_GAP"
    assert result["value"]["level"] == -0.75
    assert result["value"]["method"] == "fcf_yield_minus_10y"
    assert result["data_quality"]["formula"] == "NDX FCF yield - 10Y Treasury yield"
    assert "Damodaran" in result["value"]["not_implied_erp_warning"]


def test_damodaran_reference_parser_extracts_latest_fcfe_premium():
    html = """
    <table>
      <tr><th>Year</th><th>Implied Premium (FCFE)</th><th>T.Bond Rate</th></tr>
      <tr><td>2024</td><td>4.60%</td><td>4.00%</td></tr>
      <tr><td>2025</td><td>4.33%</td><td>4.58%</td></tr>
    </table>
    """

    parsed = tools_L4._parse_damodaran_implied_erp_html(html)

    assert parsed["year"] == 2025
    assert parsed["implied_premium_fcfe"] == 4.33
    assert parsed["t_bond_rate"] == 4.58


def test_damodaran_excel_parser_extracts_latest_row_from_official_dataset():
    excel_like_bytes = b"""
    <table>
      <tr><th>Year</th><th>Implied Premium (FCFE)</th><th>Implied Premium (DDM)</th><th>T.Bond Rate</th></tr>
      <tr><td>2024</td><td>4.60%</td><td>4.40%</td><td>4.00%</td></tr>
      <tr><td>2025</td><td>4.33%</td><td>4.20%</td><td>4.58%</td></tr>
    </table>
    """

    parsed = tools_L4._parse_damodaran_implied_erp_excel(excel_like_bytes)

    assert parsed["year"] == 2025
    assert parsed["implied_erp_fcfe"] == 4.33
    assert parsed["implied_erp_ddm"] == 4.2
    assert parsed["tbond_rate"] == 4.58


def test_damodaran_monthly_erp_parser_extracts_latest_current_row():
    content = _minimal_xlsx(
        [
            [
                "Date",
                "S&P 500",
                "T.Bond Rate",
                "$ Riskfree Rate",
                "ERP (T12 m with sustainable Payout)",
                "ERP (T12m)",
                "ERP (Smoothed)",
                "ERP (Normalized)",
                "ERP (Net Cash Yield)",
                "Expected Return",
            ],
            ["2026-04-01", 6950, 0.043, 0.0404, 0.0431, 0.0440, 0.0640, 0.0380, 0.0420, 0.0871],
            ["2026-05-01", 7209, 0.044, 0.0414, 0.0424, 0.0436, "6,36%", 0.0373, 0.0415, 0.0876],
        ]
    )

    parsed = tools_L4._parse_damodaran_monthly_erp_excel(content)

    assert parsed["data_date"] == "2026-05-01"
    assert parsed["sp500_level"] == 7209.0
    assert parsed["us_10y_treasury_rate"] == 4.4
    assert parsed["adjusted_riskfree_rate"] == 4.14
    assert parsed["default_spread"] == 0.26
    assert parsed["erp_t12m_adjusted_payout"] == 4.24
    assert parsed["erp_t12m_cash_yield"] == 4.36
    assert parsed["erp_avg_cf_yield_10y"] == 6.36
    assert parsed["erp_normalized_earnings_payout"] == 3.73
    assert parsed["erp_net_cash_yield"] == 4.15
    assert parsed["expected_return"] == 8.76
    assert parsed["source_file"] == "ERPbymonth.xlsx"


def test_damodaran_current_calculator_parser_extracts_default_spread_and_expected_return():
    content = _minimal_xlsx(
        [
            ["Label", "Value"],
            ["Current 10-year US treasury bond rate", 0.044],
            ["Default spread for Aa1", 0.0026],
            ["Adjusted $ riskfree rate", 0.0414],
            ["Implied expected return on stocks", 0.0855043176],
            ["Implied premium with T.Bond rate", 0.0415043176],
        ]
    )

    parsed = tools_L4._parse_damodaran_current_erp_calculator_excel(content, source_file="ERPMay26.xlsx")

    assert parsed["source_file"] == "ERPMay26.xlsx"
    assert parsed["us_10y_treasury_rate"] == 4.4
    assert parsed["default_spread"] == 0.26
    assert parsed["adjusted_riskfree_rate"] == 4.14
    assert parsed["expected_return"] == 8.55
    assert parsed["erp_net_cash_yield"] == 4.15


def test_damodaran_getter_prefers_excel_and_marks_it_official(monkeypatch):
    monthly_bytes = _minimal_xlsx(
        [
            [
                "Date",
                "S&P 500",
                "T.Bond Rate",
                "$ Riskfree Rate",
                "ERP (T12 m with sustainable Payout)",
                "ERP (T12m)",
                "ERP (Smoothed)",
                "ERP (Normalized)",
                "ERP (Net Cash Yield)",
                "Expected Return",
            ],
            ["2026-05-01", 7209, 0.044, 0.0414, 0.0424, 0.0436, 0.0636, 0.0373, 0.0415, 0.0876],
        ]
    )
    calculator_bytes = _minimal_xlsx(
        [
            ["Label", "Value"],
            ["Default spread for Aa1", 0.0026],
            ["Implied expected return on stocks", 0.0855043176],
        ]
    )
    annual_bytes = b"""
    <table>
      <tr><th>Year</th><th>Implied Premium (FCFE)</th><th>T.Bond Rate</th></tr>
      <tr><td>2026</td><td>4.10%</td><td>4.55%</td></tr>
    </table>
    """
    html_called = {"value": False}
    fetched_urls = []

    def fake_fetch_bytes(url, timeout=12):
        fetched_urls.append(url)
        if url.endswith("ERPbymonth.xlsx"):
            return monthly_bytes, None
        if url.endswith("ERPMay26.xlsx"):
            return calculator_bytes, None
        if url.endswith("histimpl.xls"):
            return annual_bytes, None
        return None, "unexpected url"

    monkeypatch.setattr(tools_L4, "_fetch_bytes", fake_fetch_bytes)

    def fake_fetch_text(url, timeout=8):
        html_called["value"] = True
        return None, "html should not be needed"

    monkeypatch.setattr(tools_L4, "_fetch_text", fake_fetch_text)

    result = tools_L4.get_damodaran_us_implied_erp("2026-05-01")

    assert result["source_tier"] == "official"
    assert result["value"]["data_date"] == "2026-05-01"
    assert result["value"]["erp_t12m_adjusted_payout"] == 4.24
    assert result["value"]["erp_t12m_cash_yield"] == 4.36
    assert result["value"]["erp_avg_cf_yield_10y"] == 6.36
    assert result["value"]["us_10y_treasury_rate"] == 4.4
    assert result["value"]["default_spread"] == 0.26
    assert result["value"]["adjusted_riskfree_rate"] == 4.14
    assert result["value"]["expected_return"] == 8.55
    assert result["value"]["scope"] == "US equity market reference, not NDX-specific"
    assert result["value"]["source_file"] == "ERPbymonth.xlsx"
    assert result["value"]["current_calculator_source_file"] == "ERPMay26.xlsx"
    assert result["download_url"].endswith("ERPbymonth.xlsx")
    assert fetched_urls[0].endswith("ERPbymonth.xlsx")
    assert any(url.endswith("ERPMay26.xlsx") for url in fetched_urls)
    assert html_called["value"] is False


def test_damodaran_getter_falls_back_to_html_when_excel_fails(monkeypatch):
    html = """
    <table>
      <tr><th>Year</th><th>Implied Premium (FCFE)</th><th>T.Bond Rate</th></tr>
      <tr><td>2025</td><td>4.33%</td><td>4.58%</td></tr>
    </table>
    """

    monkeypatch.setattr(tools_L4, "_fetch_bytes", lambda url, timeout=12: (None, "excel failed"))
    monkeypatch.setattr(tools_L4, "_fetch_text", lambda url, timeout=8: (html, None))

    result = tools_L4.get_damodaran_us_implied_erp("2026-05-01")

    assert result["source_tier"] == "official"
    assert result["value"]["implied_erp_fcfe"] == 4.33
    assert result["value"]["tbond_rate"] == 4.58
    assert result["value"]["retrieval_method"] == "annual_html_fallback"


def test_damodaran_getter_returns_unavailable_when_excel_and_html_fail(monkeypatch):
    monkeypatch.setattr(tools_L4, "_fetch_bytes", lambda url, timeout=12: (None, "excel failed"))
    monkeypatch.setattr(tools_L4, "_fetch_text", lambda url, timeout=8: (None, "html failed"))

    result = tools_L4.get_damodaran_us_implied_erp("2026-05-01")

    assert result["source_tier"] == "unavailable"
    assert result["value"] is None
    assert "excel failed" in result["unavailable_reason"]
    assert "html failed" in result["unavailable_reason"]
