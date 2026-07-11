import os
import sys
import json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest
import pandas as pd

import tools_L4


@pytest.fixture(autouse=True)
def _disable_live_danjuan_fetch(monkeypatch):
    monkeypatch.setattr(tools_L4, "_fetch_json", lambda *args, **kwargs: (None, "danjuan disabled in unit test"))


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


def test_danjuan_ndx_valuation_parser_extracts_percentiles_and_dates():
    payload = {
        "data": {
            "index_code": "NDX",
            "name": "纳指100",
            "pe": 36.508,
            "pb": 10.4366,
            "pe_percentile": 0.87,
            "pb_percentile": 0.9968,
            "roe": 0.2859,
            "peg": 1.8119,
            "eva_type": "high",
            "eva_type_int": 2,
            "ts": 1778774400000,
            "begin_at": 1453737600000,
            "updated_at": 1778895120349,
            "date": "05-15",
        },
        "result_code": 0,
    }

    parsed = tools_L4._parse_danjuan_ndx_valuation(payload)

    assert parsed["source_id"] == "danjuan_ndx_valuation"
    assert parsed["source_name"] == "DanjuanFunds"
    assert parsed["source_tier"] == "third_party_estimate"
    assert parsed["metric"] == "ndx_trailing_pe"
    assert parsed["value"] == 36.51
    assert parsed["pb"] == 10.44
    assert parsed["historical_percentile"] == 87.0
    assert parsed["percentile_10y"] == 87.0
    assert parsed["pb_percentile"] == 99.68
    assert parsed["roe"] == 0.2859
    assert parsed["peg"] == 1.8119
    assert parsed["eva_type"] == "high"
    assert parsed["date"] == "05-15"
    assert parsed["sample_start"] == "2016-01-26"
    assert parsed["updated_at"].endswith("Z")
    assert parsed["source_url"] == tools_L4.DANJUAN_NDX_VALUATION_URL
    assert "pe_percentile * 100" in parsed["formula"]


def test_wind_ndx_valuation_parser_normalizes_percentiles_and_rank():
    payload = {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "columns": [
                            "指数代码",
                            "指数名称",
                            "日期",
                            "市盈率",
                            "市净率",
                            "市销率",
                            "市盈率历史分位",
                            "市净率历史分位",
                            "市销率历史分位",
                            "风险溢价",
                            "风险溢价历史分位",
                            "风险溢价排名",
                            "最早成分日期",
                        ],
                        "data": [
                            [
                                "NDX.GI",
                                "纳斯达克100",
                                "2026-06-16",
                                35.2454,
                                10.3394,
                                7.4105,
                                0.8464,
                                0.9927,
                                0.9767,
                                1.0926,
                                0.5554,
                                "1770/3186",
                                "2011-04-01",
                            ]
                        ],
                    },
                    ensure_ascii=False,
                ),
            }
        ]
    }

    parsed = tools_L4._parse_wind_ndx_valuation_payload(payload)

    assert parsed["index_code"] == "NDX.GI"
    assert parsed["index_name"] == "纳斯达克100"
    assert parsed["data_date"] == "2026-06-16"
    assert parsed["pe"] == 35.2454
    assert parsed["pb"] == 10.3394
    assert parsed["ps"] == 7.4105
    assert parsed["risk_premium"] == 1.0926
    assert parsed["pe_historical_percentile"] == 84.64
    assert parsed["pb_historical_percentile"] == 99.27
    assert parsed["ps_historical_percentile"] == 97.67
    assert parsed["risk_premium_historical_percentile"] == 55.54
    assert parsed["risk_premium_rank"] == {"rank": 1770, "sample_count": 3186}
    assert parsed["sample_start"] == "2011-04-01"


def test_wind_ndx_valuation_parser_handles_nested_step_tables_with_column_metadata():
    payload = {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "data": {
                            "data": [
                                {
                                    "columns": [
                                        {"name": "Wind代码", "type": "string"},
                                        {"name": "证券简称", "type": "string"},
                                        {"name": "最新市盈率", "type": "number", "unit": "倍"},
                                        {"name": "日期", "type": "date"},
                                        {"name": "过去一年市净率", "type": "number", "unit": "倍"},
                                        {"name": "过去一年市销率", "type": "number"},
                                        {"name": "过去一年风险溢价", "type": "number"},
                                        {"name": "过去一年市盈率序号", "type": "number"},
                                        {"name": "过去一年市盈率最大序号", "type": "number"},
                                        {"name": "最新市盈率在过去一年中的分位数", "type": "number"},
                                    ],
                                    "rows": [["NDX.GI", "纳斯达克100", 35.2443, "2026-06-16", 10.3391, 7.4103, 1.1049, 99, 251, 0.392]],
                                    "step": "Step1",
                                },
                                {
                                    "columns": [
                                        {"name": "Wind代码", "type": "string"},
                                        {"name": "证券简称", "type": "string"},
                                        {"name": "过去一年市盈率", "type": "number", "unit": "倍"},
                                        {"name": "日期", "type": "date"},
                                        {"name": "最新市净率", "type": "number", "unit": "倍"},
                                        {"name": "过去一年市销率", "type": "number"},
                                        {"name": "过去一年风险溢价", "type": "number"},
                                        {"name": "过去一年市净率序号", "type": "number"},
                                        {"name": "过去一年市净率最大序号", "type": "number"},
                                        {"name": "最新市净率在过去一年中的分位数", "type": "number"},
                                    ],
                                    "rows": [["NDX.GI", "纳斯达克100", 35.2443, "2026-06-16", 10.3391, 7.4103, 1.1049, 222, 251, 0.884]],
                                    "step": "Step2",
                                },
                                {
                                    "columns": [
                                        {"name": "Wind代码", "type": "string"},
                                        {"name": "证券简称", "type": "string"},
                                        {"name": "过去一年市盈率", "type": "number", "unit": "倍"},
                                        {"name": "日期", "type": "date"},
                                        {"name": "过去一年市净率", "type": "number", "unit": "倍"},
                                        {"name": "最新市销率", "type": "number"},
                                        {"name": "过去一年风险溢价", "type": "number"},
                                        {"name": "过去一年市销率序号", "type": "number"},
                                        {"name": "过去一年市销率最大序号", "type": "number"},
                                        {"name": "最新市销率在过去一年中的分位数", "type": "number"},
                                    ],
                                    "rows": [["NDX.GI", "纳斯达克100", 35.2443, "2026-06-16", 10.3391, 7.4103, 1.1049, 161, 251, 0.64]],
                                    "step": "Step3",
                                },
                                {
                                    "columns": [
                                        {"name": "Wind代码", "type": "string"},
                                        {"name": "证券简称", "type": "string"},
                                        {"name": "过去一年市盈率", "type": "number", "unit": "倍"},
                                        {"name": "日期", "type": "date"},
                                        {"name": "过去一年市净率", "type": "number", "unit": "倍"},
                                        {"name": "过去一年市销率", "type": "number"},
                                        {"name": "最新风险溢价", "type": "number"},
                                        {"name": "过去一年风险溢价序号", "type": "number"},
                                        {"name": "过去一年风险溢价最大序号", "type": "number"},
                                        {"name": "最新风险溢价在过去一年中的分位数", "type": "number"},
                                    ],
                                    "rows": [["NDX.GI", "纳斯达克100", 35.2443, "2026-06-16", 10.3391, 7.4103, 1.1049, 172, 251, 0.684]],
                                    "step": "Step4",
                                },
                            ]
                        },
                        "error": None,
                    },
                    ensure_ascii=False,
                ),
            }
        ],
        "isError": False,
    }

    parsed = tools_L4._parse_wind_ndx_valuation_payload(payload)

    assert parsed["index_code"] == "NDX.GI"
    assert parsed["index_name"] == "纳斯达克100"
    assert parsed["data_date"] == "2026-06-16"
    assert parsed["pe"] == 35.2443
    assert parsed["pb"] == 10.3391
    assert parsed["ps"] == 7.4103
    assert parsed["risk_premium"] == 1.1049
    assert parsed["pe_historical_percentile"] == 39.2
    assert parsed["pe_percentile_windows"]["1y"]["percentile"] == 39.2
    assert parsed["pe_percentile_windows"]["1y"]["rank"] == 99
    assert parsed["pe_percentile_windows"]["1y"]["sample_count"] == 251
    assert parsed["pb_historical_percentile"] == 88.4
    assert parsed["pb_percentile_windows"]["1y"]["percentile"] == 88.4
    assert parsed["ps_historical_percentile"] == 64.0
    assert parsed["risk_premium_historical_percentile"] == 68.4
    assert parsed["risk_premium_percentile_windows"]["1y"]["percentile"] == 68.4
    assert parsed["risk_premium_rank"] == {"rank": 172, "sample_count": 251}


def test_wind_ndx_valuation_parser_extracts_pe_percentile_windows():
    payload = {
        "content": [
            {
                "type": "text",
                "text": json.dumps(
                    {
                        "data": {
                            "data": [
                                {
                                    "columns": [
                                        {"name": "Wind代码"},
                                        {"name": "证券简称"},
                                        {"name": "近1年每日市盈率"},
                                        {"name": "日期"},
                                        {"name": "近1年每日市盈率序号"},
                                        {"name": "近1年市盈率最大序号"},
                                        {"name": "最新市盈率在过去1年中的分位数"},
                                    ],
                                    "rows": [["NDX.GI", "纳斯达克100", 35.2443, "2026-06-17", 99, 251, 0.392]],
                                },
                                {
                                    "columns": [
                                        {"name": "Wind代码"},
                                        {"name": "证券简称"},
                                        {"name": "近2年每日市盈率"},
                                        {"name": "日期"},
                                        {"name": "近2年每日市盈率排名"},
                                        {"name": "近2年市盈率最大排名"},
                                        {"name": "最新市盈率在过去2年中的分位数"},
                                    ],
                                    "rows": [["NDX.GI", "纳斯达克100", 35.2443, "2026-06-17", 208, 501, 0.414]],
                                },
                                {
                                    "columns": [
                                        {"name": "Wind代码"},
                                        {"name": "证券简称"},
                                        {"name": "近5年每日市盈率"},
                                        {"name": "日期"},
                                        {"name": "近5年每日市盈率序号"},
                                        {"name": "近5年市盈率最大序号"},
                                        {"name": "最新市盈率在过去5年中的分位数"},
                                    ],
                                    "rows": [["NDX.GI", "纳斯达克100", 35.2443, "2026-06-17", 844, 1255, 0.6722]],
                                },
                                {
                                    "columns": [
                                        {"name": "Wind代码"},
                                        {"name": "证券简称"},
                                        {"name": "近10年每日市盈率"},
                                        {"name": "日期"},
                                        {"name": "近10年每日市盈率序号"},
                                        {"name": "近10年市盈率最大序号"},
                                        {"name": "最新市盈率在过去10年中的分位数"},
                                    ],
                                    "rows": [["NDX.GI", "纳斯达克100", 35.2443, "2026-06-17", 1924, 2513, 0.7655]],
                                },
                            ]
                        }
                    },
                    ensure_ascii=False,
                ),
            }
        ]
    }

    parsed = tools_L4._parse_wind_ndx_valuation_payload(payload)

    assert parsed["pe"] == 35.2443
    assert parsed["pe_percentile_windows"]["1y"]["percentile"] == 39.2
    assert parsed["pe_percentile_windows"]["2y"]["percentile"] == 41.4
    assert parsed["pe_percentile_windows"]["5y"]["percentile"] == 67.22
    assert parsed["pe_percentile_windows"]["10y"]["percentile"] == 76.55
    assert parsed["pe_percentile_windows"]["10y"]["rank"] == 1924
    assert parsed["pe_percentile_windows"]["10y"]["sample_count"] == 2513


def test_wind_ndx_snapshot_fetches_pe_windows_and_marks_authority(monkeypatch):
    tools_L4.L4_WIND_NDX_VALUATION_CACHE.clear()

    def fake_wind_cli(server_type, tool_name, params, timeout=45):
        assert server_type == "index_data"
        assert tool_name == "get_index_fundamentals"
        assert "纳斯达克100" in params["question"]
        if "市盈率在过去" in params["question"]:
            window_payloads = {
                "1年": ("近1年每日市盈率", "近1年每日市盈率序号", "近1年市盈率最大序号", "最新市盈率在过去1年中的分位数", 99, 251, 0.392),
                "2年": ("近2年每日市盈率", "近2年每日市盈率序号", "近2年市盈率最大序号", "最新市盈率在过去2年中的分位数", 208, 501, 0.414),
                "5年": ("近5年每日市盈率", "近5年每日市盈率序号", "近5年市盈率最大序号", "最新市盈率在过去5年中的分位数", 844, 1255, 0.6722),
                "10年": ("近10年每日市盈率", "近10年每日市盈率序号", "近10年市盈率最大序号", "最新市盈率在过去10年中的分位数", 1924, 2513, 0.7655),
            }
            period, rank_col, max_rank_col, pct_col, rank, sample_count, percentile = next(
                payload for token, payload in window_payloads.items() if token in params["question"]
            )
            return (
                {
                    "content": [
                        {
                            "text": json.dumps(
                                {
                                    "data": {
                                        "data": [
                                            {
                                                "columns": [
                                                    {"name": "Wind代码"},
                                                    {"name": "证券简称"},
                                                    {"name": period},
                                                    {"name": "日期"},
                                                    {"name": rank_col},
                                                    {"name": max_rank_col},
                                                    {"name": pct_col},
                                                ],
                                                "rows": [["NDX.GI", "纳斯达克100", 35.2454, "2026-06-17", rank, sample_count, percentile]],
                                            },
                                        ]
                                    }
                                },
                                ensure_ascii=False,
                            )
                        }
                    ]
                },
                None,
            )
        if "风险溢价在过去" in params["question"]:
            is_10y = "10年" in params["question"]
            return (
                {
                    "content": [
                        {
                            "text": json.dumps(
                                {
                                    "data": {
                                        "data": [
                                            {
                                                "columns": [
                                                    {"name": "Wind代码"},
                                                    {"name": "证券简称"},
                                                    {"name": "过去10年每日风险溢价" if is_10y else "过去1年每日风险溢价"},
                                                    {"name": "日期"},
                                                    {"name": "风险溢价序号"},
                                                    {"name": "风险溢价最大序号"},
                                                    {"name": "最新风险溢价在过去10年的分位数" if is_10y else "最新风险溢价在过去1年的分位数"},
                                                ],
                                                "rows": [["NDX.GI", "纳斯达克100", 1.0926, "2026-06-17", 1770 if is_10y else 172, 3186 if is_10y else 251, 0.5554 if is_10y else 0.684]],
                                            },
                                        ]
                                    }
                                },
                                ensure_ascii=False,
                            )
                        }
                    ]
                },
                None,
            )
        return (
            {
                "content": [
                    {
                        "text": json.dumps(
                            {
                                "columns": ["指数代码", "指数名称", "日期", "市盈率", "风险溢价"],
                                "data": [["NDX.GI", "纳斯达克100", "2026-06-16", 35.2454, 1.0926]],
                            },
                            ensure_ascii=False,
                        )
                    }
                ]
            },
            None,
        )

    monkeypatch.setattr(tools_L4, "_call_wind_cli", fake_wind_cli)

    result = tools_L4.get_ndx_wind_valuation_snapshot()

    assert result["source_tier"] == "licensed_provider/Wind"
    assert result["value"]["PE"] == 35.25
    assert result["value"]["RiskPremium"] == 1.0926
    assert result["value"]["PEHistoricalPercentile"] == 76.55
    assert result["value"]["PEHistoricalPercentileWindow"] == "10y"
    assert result["value"]["PEPercentileWindows"]["5y"]["percentile"] == 67.22
    assert result["value"]["PEPercentileWindows"]["10y"]["sample_count"] == 2513
    assert result["value"]["RiskPremiumHistoricalPercentile"] == 55.54
    assert result["value"]["RiskPremiumHistoricalPercentileWindow"] == "10y"
    assert result["value"]["RiskPremiumRank"] == {"rank": 1770, "sample_count": 3186}
    assert result["value"]["MetricAuthority"]["RiskPremium"]["usage"] == "supporting_only"
    assert result["value"]["MetricAuthority"]["RiskPremium"]["authority"] == "provider_label_definition_unverified"
    assert result["data_quality"]["license_note"] == "licensed_provider"
    assert "数据来源于万得 Wind 金融数据服务" in result["notes"]


def test_wind_ndx_snapshot_rejects_declared_long_window_with_one_year_sample(monkeypatch):
    tools_L4.L4_WIND_NDX_VALUATION_CACHE.clear()

    def fake_wind_cli(server_type, tool_name, params, timeout=45):
        if "市盈率在过去" in params["question"]:
            requested_window = "10年" if "10年" in params["question"] else "1年"
            pct_column = f"最新市盈率在过去{requested_window}中的分位数"
            rank_column = f"过去{requested_window}市盈率序号"
            max_rank_column = f"过去{requested_window}市盈率最大序号"
            return (
                {
                    "content": [
                        {
                            "text": json.dumps(
                                {
                                    "data": {
                                        "data": [
                                            {
                                                "columns": [
                                                    {"name": "Wind代码"},
                                                    {"name": "证券简称"},
                                                    {"name": f"过去{requested_window}市盈率"},
                                                    {"name": "日期"},
                                                    {"name": rank_column},
                                                    {"name": max_rank_column},
                                                    {"name": pct_column},
                                                ],
                                                "rows": [["NDX.GI", "纳斯达克100", 35.2443, "2026-06-16", 15, 251, 0.056]],
                                            },
                                        ]
                                    }
                                },
                                ensure_ascii=False,
                            )
                        }
                    ],
                    "isError": False,
                },
                None,
            )
        if "风险溢价在过去" in params["question"]:
            return None, "not_available_in_test"
        return (
            {
                "content": [
                    {
                        "text": json.dumps(
                            {
                                "data": {
                                    "data": [
                                        {
                                            "columns": [
                                                {"name": "Wind代码"},
                                                {"name": "证券简称"},
                                                {"name": "最新市盈率"},
                                                {"name": "日期"},
                                                {"name": "过去一年风险溢价"},
                                                {"name": "最新市盈率在过去一年中的分位数"},
                                            ],
                                            "rows": [["NDX.GI", "纳斯达克100", 35.2443, "2026-06-16", 1.1049, 0.392]],
                                        },
                                        {
                                            "columns": [
                                                {"name": "Wind代码"},
                                                {"name": "证券简称"},
                                                {"name": "日期"},
                                                {"name": "最新风险溢价"},
                                                {"name": "过去一年风险溢价序号"},
                                                {"name": "过去一年风险溢价最大序号"},
                                                {"name": "最新风险溢价在过去一年中的分位数"},
                                            ],
                                            "rows": [["NDX.GI", "纳斯达克100", "2026-06-16", 1.1049, 172, 251, 0.684]],
                                        },
                                    ]
                                }
                            },
                            ensure_ascii=False,
                        )
                    }
                ],
                "isError": False,
            },
            None,
        )

    monkeypatch.setattr(tools_L4, "_call_wind_cli", fake_wind_cli)

    result = tools_L4.get_ndx_wind_valuation_snapshot()

    assert result["availability"] == "available"
    assert result["source_tier"] == "licensed_provider/Wind"
    assert result["value"]["PE"] == 35.24
    assert result["value"]["RiskPremium"] == 1.1049
    assert result["value"]["PEHistoricalPercentile"] is None
    assert "10y" not in result["value"]["PEPercentileWindows"]
    assert any(
        item["metric"] == "市盈率" and item["window"] == "10y" and item["reason"] == "sample_count_too_small_for_declared_window"
        for item in result["value"]["WindPercentileIssues"]
    )
    assert result["data_quality"]["availability"] == "available"


def test_danjuan_check_is_included_with_required_headers(monkeypatch):
    captured = {}

    def fake_fetch_text(url, timeout=8):
        return None, "skip html source"

    def fake_fetch_json(url, timeout=8, headers=None):
        captured["url"] = url
        captured["headers"] = headers or {}
        return (
            {
                "data": {
                    "index_code": "NDX",
                    "name": "纳指100",
                    "pe": 35.2,
                    "pb": 9.8,
                    "pe_percentile": 0.73,
                    "pb_percentile": 0.91,
                    "roe": 0.26,
                    "peg": 1.7,
                    "eva_type": "high",
                    "ts": 1778774400000,
                    "begin_at": 1453737600000,
                    "updated_at": 1778895120349,
                    "date": "05-15",
                },
                "result_code": 0,
            },
            None,
        )

    monkeypatch.setattr(tools_L4, "_fetch_text", fake_fetch_text)
    monkeypatch.setattr(tools_L4, "_fetch_json", fake_fetch_json)

    checks = tools_L4.get_ndx_valuation_third_party_checks()
    by_id = {item["source_id"]: item for item in checks}

    assert by_id["danjuan_ndx_valuation"]["availability"] == "stale"
    assert by_id["danjuan_ndx_valuation"]["usage"] == "audit_only"
    assert by_id["danjuan_ndx_valuation"]["historical_percentile"] == 73.0
    assert captured["url"] == tools_L4.DANJUAN_NDX_VALUATION_URL
    assert "Mozilla/5.0" in captured["headers"]["User-Agent"]
    assert captured["headers"]["Referer"] == tools_L4.DANJUAN_NDX_VALUATION_REFERER


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


def test_trendonify_403_does_not_promote_browser_sidecar_into_l4(tmp_path, monkeypatch):
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

    assert by_id["trendonify_pe"]["availability"] == "unavailable"
    assert by_id["trendonify_pe"]["value"] is None
    assert by_id["trendonify_forward_pe"]["availability"] == "unavailable"
    assert by_id["trendonify_forward_pe"]["value"] is None
    assert "browser_sidecar" not in by_id["trendonify_pe"]


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


def _install_history_of_market_fixture(monkeypatch):
    payload = {
        "updated": "2026-07-09",
        "current": {
            "trailing": 33.95,
            "forward": 24.29,
            "trailingCoverage": 100.0,
            "forwardCoverage": 100.0,
        },
        "trailing": [
            {"date": "2026-05-11", "value": 34.50},
            {"date": "2026-07-09", "value": 33.95},
        ],
        "forward": [
            {"date": "2008-10-31", "value": 15.0},
            {"date": "2020-03-31", "value": 20.0},
            {"date": "2022-01-31", "value": 24.0},
            {"date": "2023-10-31", "value": 20.0},
            {"date": "2026-05-18", "value": 24.29},
        ],
        "historyStarts": {"trailing": "2026-05-11", "forward": "2008-10-31"},
        "source": {"method": "fixed test fixture"},
        "note": "deterministic fixture; no live network dependency",
    }

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return payload

    monkeypatch.setattr(tools_L4.requests, "get", lambda *args, **kwargs: Response())


@pytest.mark.parametrize("end_date,expected_forward_min,expected_forward_max", [
    (None, 20.0, 30.0),
    ("2026-07-09", 20.0, 30.0),
    ("2026-07-08", 20.0, 30.0),
])
def test_get_ndx_valuation_history_of_market_returns_valid_forward_pe(monkeypatch, end_date, expected_forward_min, expected_forward_max):
    _install_history_of_market_fixture(monkeypatch)
    result = tools_L4.get_ndx_valuation_history_of_market(end_date=end_date)
    value = result.get("value", {})
    fwd_pe = value.get("forward_pe")
    assert fwd_pe is not None, f"forward_pe is None for end_date={end_date}"
    assert expected_forward_min <= fwd_pe <= expected_forward_max, (
        f"forward_pe={fwd_pe} outside [{expected_forward_min}, {expected_forward_max}] for {end_date}"
    )
    if end_date:
        assert value.get("forward_coverage_pct") is None
        assert value.get("forward_decision_eligible") is False
    else:
        assert value.get("forward_coverage_pct") == 100.0
    assert value.get("forward_percentile") is None
    assert value.get("forward_percentile_status") == "insufficient_history"
    assert value.get("forward_percentile_context", {}).get("sample_count") == 5
    assert len(value.get("forward_percentile_context", {}).get("raw_series", [])) == 5


@pytest.mark.parametrize("backtest_date,expected_min,expected_max", [
    ("2022-01-31", 18.0, 30.0),
    ("2008-10-31", 10.0, 25.0),
    ("2020-03-31", 15.0, 30.0),
    ("2023-10-31", 15.0, 25.0),
])
def test_get_ndx_valuation_history_of_market_backtest_returns_reasonable_values(monkeypatch, backtest_date, expected_min, expected_max):
    _install_history_of_market_fixture(monkeypatch)
    result = tools_L4.get_ndx_valuation_history_of_market(end_date=backtest_date)
    value = result.get("value", {})
    fwd_pe = value.get("forward_pe")
    assert fwd_pe is not None, f"forward_pe is None for backtest_date={backtest_date}"
    assert expected_min <= fwd_pe <= expected_max, (
        f"forward_pe={fwd_pe} outside [{expected_min}, {expected_max}] for {backtest_date}"
    )


def test_get_ndx_valuation_history_of_market_trailing_only_after_may_2026(monkeypatch):
    _install_history_of_market_fixture(monkeypatch)
    result_before = tools_L4.get_ndx_valuation_history_of_market(end_date="2026-05-10")
    assert result_before.get("value", {}).get("trailing_pe") is None

    result_after = tools_L4.get_ndx_valuation_history_of_market(end_date="2026-05-11")
    trailing = result_after.get("value", {}).get("trailing_pe")
    assert trailing is not None and trailing > 0, f"trailing_pe should exist on 2026-05-11, got {trailing}"


def test_get_ndx_valuation_history_of_market_handles_invalid_date():
    result = tools_L4.get_ndx_valuation_history_of_market(end_date="not-a-date")
    assert result.get("availability") == "unavailable"
    reason = result.get("unavailable_reason", "")
    assert "invalid_end_date_format" in reason


def test_get_ndx_valuation_history_of_market_handles_too_early_date(monkeypatch):
    _install_history_of_market_fixture(monkeypatch)
    result = tools_L4.get_ndx_valuation_history_of_market(end_date="1999-01-01")
    assert result.get("availability") == "unavailable"
    assert "no_valid_trailing_or_forward_pe" in result.get("unavailable_reason", "")


def test_history_percentile_edge_cases():
    history = [
        {"date": "2020-01-01", "value": 10.0},
        {"date": "2020-02-01", "value": 20.0},
        {"date": "2020-03-01", "value": 30.0},
    ]
    assert tools_L4._history_percentile(10.0, history) == 33.3
    assert tools_L4._history_percentile(5.0, history) == 0.0
    assert tools_L4._history_percentile(40.0, history) == 100.0
    assert tools_L4._history_percentile(15.0, history) == 33.3
    assert tools_L4._history_percentile(25.0, history) == 66.7
    assert tools_L4._history_percentile(20.0, []) is None


def test_history_of_market_percentile_requires_observations_and_span():
    sparse_long_span = [
        {"date": "2001-01-31", "value": 20.0},
        {"date": "2026-01-31", "value": 25.0},
    ]
    context = tools_L4._history_percentile_context(25.0, sparse_long_span, series_kind="forward")
    assert context["percentile"] is None
    assert context["status"] == "insufficient_history"
    assert context["sample_count"] == 2
    assert context["span_days"] > context["required_min_span_days"]
    assert context["relative_context"] == {"minimum": 20.0, "median": 22.5, "maximum": 25.0}
    assert context["raw_series"] == sparse_long_span


def test_history_of_market_forward_percentile_available_with_five_year_monthly_history():
    history = [
        {
            "date": (pd.Timestamp("2021-01-31") + pd.offsets.MonthEnd(index)).strftime("%Y-%m-%d"),
            "value": float(20 + index),
        }
        for index in range(60)
    ]
    context = tools_L4._history_percentile_context(79.0, history, series_kind="forward")
    assert context["status"] == "available"
    assert context["percentile"] == 100.0
    assert context["sample_count"] == 60
    assert context["span_days"] >= context["required_min_span_days"]


def test_closest_in_history():
    history = [
        {"date": "2020-01-01", "value": 10.0},
        {"date": "2020-06-01", "value": 20.0},
        {"date": "2020-12-01", "value": 30.0},
    ]
    assert tools_L4._closest_in_history(history, "2020-01-01") == 10.0
    assert tools_L4._closest_in_history(history, "2020-03-01") == 10.0
    assert tools_L4._closest_in_history(history, "2020-07-01") == 20.0
    assert tools_L4._closest_in_history(history, "2021-01-01") == 30.0
    assert tools_L4._closest_in_history(history, "2019-12-31") is None
    assert tools_L4._closest_in_history([], "2020-01-01") is None


def test_history_up_to():
    history = [
        {"date": "2020-06-01", "value": 20.0},
        {"date": "2020-01-01", "value": 10.0},
        {"date": "2020-12-01", "value": 30.0},
    ]
    filtered = tools_L4._history_up_to(history, "2020-06-15")
    assert len(filtered) == 2
    assert filtered[0]["date"] == "2020-01-01"
    assert filtered[1]["date"] == "2020-06-01"
    filtered = tools_L4._history_up_to(history, "2020-01-01")
    assert len(filtered) == 1
    assert filtered[0]["date"] == "2020-01-01"
    assert tools_L4._history_up_to([], "2020-01-01") == []
