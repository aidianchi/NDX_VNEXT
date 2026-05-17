import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from news_layer_analyzer import NewsLayerAnalyzer, write_news_layer_analysis


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
                "layers": ["L1", "L2", "L4"],
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
