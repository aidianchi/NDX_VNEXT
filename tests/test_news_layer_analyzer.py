import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from news_layer_analyzer import NewsLayerAnalyzer, _event_family, write_news_layer_analysis


def _ledger():
    return {
        "schema_version": "news_event_ledger_v2",
        "events": [
            {
                "event_id": "event:fomc",
                "dedupe_id": "fomc",
                "source_name": "Federal Reserve Press Releases",
                "source_tier": "official_macro",
                "event_type": "policy_or_financial_conditions",
                "title": "Federal Reserve issues FOMC statement",
                "published_at": "Fri, 08 May 2026 18:00:00 GMT",
                "symbols": [],
                "relevance_tags": ["topic:macro_rates", "topic:credit_vol", "topic:valuation_earnings"],
                "layers": ["topic:macro_rates", "topic:credit_vol", "topic:valuation_earnings"],
            }
        ],
    }


def _links():
    return {
        "schema_version": "news_event_data_links_v1",
        "links": [
            {
                "event_id": "event:fomc",
                "observations": [
                    {
                        "series_key": "US10Y_REAL",
                        "series_label": "10Y Real Yield",
                        "direction": "up",
                        "needs_bridge_review": True,
                    },
                    {
                        "series_key": "VIX",
                        "series_label": "VIX",
                        "direction": "up",
                        "needs_bridge_review": True,
                    },
                ],
            }
        ],
    }


def test_news_layer_analyzer_writes_chinese_summary_without_layer_injection():
    payload = NewsLayerAnalyzer().build(event_ledger=_ledger(), news_event_data_links=_links())

    assert payload["schema_version"] == "news_layer_analysis_v1"
    assert "not injected into L1-L5" in payload["policy"]["runtime_context_rule"]
    assert "evidence_ref" in payload["policy"]["evidence_rule"]
    assert "新闻层总分析" not in payload["aggregate_analysis"]["market_state_zh"]
    summary = payload["event_summaries"][0]
    assert summary["event_ref"] == "event:fomc"
    assert "中文解读" in summary["boundary_note"]
    assert "可能通过" in summary["possible_equity_impact_zh"]
    assert "利率上行压力" in summary["pressure_channels"]
    assert "风险溢价上升" in summary["pressure_channels"]
    assert "油价序列" in payload["aggregate_analysis"]["oil_pressure_zh"]


def test_write_news_layer_analysis_reads_run_dir_artifacts(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "news_event_ledger.json").write_text(json.dumps(_ledger()), encoding="utf-8")
    (run_dir / "news_event_data_links.json").write_text(json.dumps(_links()), encoding="utf-8")

    output = write_news_layer_analysis(run_dir)
    payload = json.loads(Path(output).read_text(encoding="utf-8"))

    assert Path(output).name == "news_layer_analysis.json"
    assert payload["source_artifacts"]["news_event_ledger"].endswith("news_event_ledger.json")
    assert payload["event_summaries"][0]["summary_zh"]


def test_scheduled_future_events_are_separate_from_realized_event_analysis():
    ledger = _ledger()
    ledger["events"].append(
        {
            "event_id": "event:fomc_future",
            "source_name": "Federal Reserve FOMC Meeting Calendar",
            "source_tier": "official",
            "event_type": "official_calendar",
            "title": "FOMC meeting (July 28-29, 2026)",
            "published_at": "2026-07-18T01:00:00Z",
            "event_date": "2026-07-29",
            "collection_status": "scheduled_future",
            "relevance_tags": ["topic:macro_rates"],
            "symbols": [],
        }
    )

    payload = NewsLayerAnalyzer().build(event_ledger=ledger)

    assert [item["event_id"] for item in payload["event_summaries"]] == ["event:fomc"]
    assert [item["event_id"] for item in payload["scheduled_future_events"]] == ["event:fomc_future"]
    assert "计划于 2026-07-29" in payload["scheduled_future_events"][0]["summary_zh"]


def test_macro_release_titles_take_priority_over_broad_macro_topic():
    base = {
        "source_id": "official_calendar",
        "event_type": "official_calendar",
        "relevance_tags": ["topic:macro_rates"],
    }

    assert _event_family({**base, "title": "Consumer Price Index"}) == "inflation"
    assert _event_family({**base, "title": "Employment Situation"}) == "labor"
    assert _event_family({**base, "title": "Gross Domestic Product"}) == "growth"


def test_aggregator_report_summary_does_not_call_it_company_disclosure():
    event = {
        "event_id": "event:wind_msft",
        "source_name": "Wind Company Announcements",
        "source_tier": "aggregator_report",
        "event_type": "issuer_announcement_or_filing",
        "title": "Microsoft updates earnings guidance",
        "published_at": "2026-07-17T01:00:00Z",
        "symbols": ["MSFT"],
        "relevance_tags": ["topic:valuation_earnings"],
    }

    summary = NewsLayerAnalyzer().build(event_ledger={"events": [event]})["event_summaries"][0]["summary_zh"]

    assert "聚合平台转述" in summary
    assert "公司披露事件" not in summary


def test_macro_calendar_and_media_earnings_are_not_called_company_disclosures():
    events = [
        {
            "event_id": "event:bls_real_earnings",
            "source_id": "bls_release_calendar",
            "source_name": "BLS Release Calendar",
            "source_tier": "official",
            "event_type": "official_calendar",
            "title": "Real Earnings",
            "published_at": "2026-07-01T12:00:00Z",
            "event_date": "2026-07-14",
            "relevance_tags": ["topic:macro_rates"],
            "symbols": [],
        },
        {
            "event_id": "event:yahoo_earnings",
            "source_id": "yahoo_finance_qqq_headlines",
            "source_name": "Yahoo Finance QQQ Headlines",
            "source_tier": "reliable_mainstream_report",
            "event_type": "market_news_report",
            "title": "Travelers earnings beat estimates",
            "published_at": "2026-07-17T12:00:00Z",
            "relevance_tags": ["topic:valuation_earnings"],
            "symbols": [],
        },
    ]

    payload = NewsLayerAnalyzer().build(event_ledger={"events": events})
    summaries = {item["event_id"]: item["summary_zh"] for item in payload["event_summaries"]}

    assert "公司披露事件" not in summaries["event:bls_real_earnings"]
    assert "就业相关事件" in summaries["event:bls_real_earnings"]
    assert "公司披露事件" not in summaries["event:yahoo_earnings"]
    assert "媒体报道或聚合线索" in summaries["event:yahoo_earnings"]
    assert "大型权重公司" not in summaries["event:yahoo_earnings"]
    assert "未确认与 M7 实体直接相关" in summaries["event:yahoo_earnings"]
    yahoo_boundary = next(
        item["boundary_note"] for item in payload["event_summaries"] if item["event_id"] == "event:yahoo_earnings"
    )
    assert "媒体材料" in yahoo_boundary
    assert "官方事件" not in yahoo_boundary
