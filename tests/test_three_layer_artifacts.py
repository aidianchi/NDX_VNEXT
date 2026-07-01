import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from event_narrative_ledger import EventNarrativeLedgerBuilder, write_event_narrative_ledger
from integrated_synthesis_report import (
    IntegratedSynthesisReportBuilder,
    build_pure_data_report_manifest,
    write_integrated_synthesis_report,
)


def _event_ledger():
    return {
        "schema_version": "news_event_ledger_v2",
        "events": [
            {
                "event_id": "event:fomc",
                "dedupe_id": "fomc",
                "source_id": "federal_reserve_press_all",
                "source_name": "Federal Reserve Press Releases",
                "source_tier": "official_macro",
                "event_type": "policy_or_financial_conditions",
                "title": "Federal Reserve issues FOMC statement",
                "published_at": "Fri, 08 May 2026 18:00:00 GMT",
                "layers": ["L1", "L2", "L4"],
                "symbols": [],
            },
            {
                "event_id": "event:future",
                "dedupe_id": "future",
                "source_name": "Future News",
                "source_tier": "reliable_mainstream_report",
                "event_type": "market_news",
                "title": "Future event",
                "published_at": "Tue, 12 May 2026 18:00:00 GMT",
            },
        ],
    }


def _news_analysis():
    return {
        "schema_version": "news_layer_analysis_v1",
        "event_summaries": [
            {
                "event_id": "event:fomc",
                "summary_zh": "这是一条来自美联储的政策事件。",
                "possible_equity_impact_zh": "可能通过利率预期影响股市。",
                "pressure_channels": ["利率预期", "风险偏好"],
            }
        ],
    }


def _data_links():
    return {
        "schema_version": "news_event_data_links_v1",
        "links": [
            {
                "event_id": "event:fomc",
                "observations": [
                    {"series_key": "US10Y_REAL", "direction": "up", "needs_bridge_review": True}
                ],
            }
        ],
    }


def test_event_narrative_ledger_builds_claims_and_filters_future_events():
    payload = EventNarrativeLedgerBuilder().build(
        event_ledger=_event_ledger(),
        news_layer_analysis=_news_analysis(),
        news_event_data_links=_data_links(),
        effective_date="2026-05-08",
    )

    assert payload["schema_version"] == "event_narrative_ledger_v1"
    assert "not injected into L1-L5" in payload["policy"]["runtime_context_rule"]
    assert [event["event_id"] for event in payload["events"]] == ["event:fomc"]
    claim = payload["events"][0]["claims"][0]
    assert claim["claim_type"] == "official_fact"
    assert claim["source_type"] == "official_fact"
    assert "discount_rate" in claim["affected_financial_links"]
    assert claim["what_it_cannot_support"].startswith("不能替代 L1-L5")
    assert claim["status"] == "event_fact"


def test_write_event_narrative_ledger_reads_run_dir_artifacts(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "news_event_ledger.json").write_text(json.dumps(_event_ledger()), encoding="utf-8")
    (run_dir / "news_layer_analysis.json").write_text(json.dumps(_news_analysis()), encoding="utf-8")
    (run_dir / "news_event_data_links.json").write_text(json.dumps(_data_links()), encoding="utf-8")

    output = write_event_narrative_ledger(run_dir, effective_date="2026-05-08")
    payload = json.loads(Path(output).read_text(encoding="utf-8"))

    assert Path(output).name == "event_narrative_ledger.json"
    assert payload["claim_count"] == 1
    assert payload["source_artifacts"]["news_event_ledger"].endswith("news_event_ledger.json")


def test_integrated_synthesis_report_blocks_formal_conclusion_when_data_integrity_blocks():
    pure_data = {"schema_version": "pure_data_report_v1", "principal_contradictions": []}
    event_ledger = EventNarrativeLedgerBuilder().build(
        event_ledger=_event_ledger(),
        news_layer_analysis=_news_analysis(),
        news_event_data_links=_data_links(),
        effective_date="2026-05-08",
    )

    payload = IntegratedSynthesisReportBuilder().build(
        pure_data_report=pure_data,
        event_narrative_ledger=event_ledger,
        data_integrity_report={"publish_status": "blocked", "blocking_reasons": ["no_indicators_collected"]},
    )

    assert payload["publish_gate"]["status"] == "audit_only"
    assert payload["publish_gate"]["formal_investment_conclusion_allowed"] is False
    assert payload["integrated_judgments"][0]["explanation_grade"] == "not_explained"
    assert payload["unexplained_items"][0]["item"] == "data_integrity_blocked"


def test_integrated_synthesis_report_downgrades_event_claims_without_data_confirmation(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    pure_path = run_dir / "pure_data_report.json"
    event_path = run_dir / "event_narrative_ledger.json"
    integrity_path = run_dir / "data_integrity_report.json"
    pure_path.write_text(
        json.dumps(
            {
                "schema_version": "pure_data_report_v1",
                "principal_contradictions": [
                    {"evidence_refs": ["L1.get_10y_real_rate", "L4.get_ndx_wind_valuation_snapshot"]}
                ],
            }
        ),
        encoding="utf-8",
    )
    event_path.write_text(json.dumps(EventNarrativeLedgerBuilder().build(event_ledger=_event_ledger(), effective_date="2026-05-08")), encoding="utf-8")
    integrity_path.write_text(json.dumps({"publish_status": "publishable"}), encoding="utf-8")

    output = write_integrated_synthesis_report(run_dir)
    payload = json.loads(Path(output).read_text(encoding="utf-8"))

    assert payload["publish_gate"]["status"] == "publishable_integrated_report"
    assert payload["integrated_judgments"][0]["explanation_grade"] == "integrated_explanation"
    assert payload["integrated_judgments"][0]["data_support"] == [
        "L1.get_10y_real_rate",
        "L4.get_ndx_wind_valuation_snapshot",
    ]
    assert payload["downgraded_claims"][0]["downgraded_to"] == "plausible_hypothesis"


def test_pure_data_report_manifest_declares_forbidden_event_inputs(tmp_path: Path):
    output = tmp_path / "pure_data_report.json"
    payload = build_pure_data_report_manifest(
        run_dir=tmp_path,
        data_integrity_report={"publish_status": "publishable"},
        output_path=output,
    )

    assert output.exists()
    assert payload["schema_version"] == "pure_data_report_v1"
    assert payload["prompt_policy"]["data_only"] is True
    assert "event_refs" in payload["prompt_policy"]["forbidden_runtime_inputs"]
