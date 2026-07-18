"""W1: integrated report inputs must share one auditable as-of date."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_analysis.vnext_reporter import VNextReportGenerator  # noqa: E402
from integrated_synthesis_report import IntegratedSynthesisReportBuilder  # noqa: E402


def _build(*, data_date: str = "2026-07-14", event_date: str = "2026-07-14", caller=None):
    return IntegratedSynthesisReportBuilder().build(
        pure_data_report={"principal_contradictions": []},
        analysis_packet={"meta": {"data_date": data_date}},
        event_narrative_ledger={"events": [{"claims": []}]},
        event_interpretation_cards={"effective_date": event_date, "cards": []},
        data_integrity_report={"publish_status": "publishable"},
        final_adjudication={
            "generated_at": f"{data_date}T00:00:00Z",
            "approval_status": "approved",
            "final_stance": "测试姿态",
        },
        llm_caller=caller,
    )


def test_mismatched_dates_block_publish_and_skip_llm():
    calls = []

    def caller(prompt, stage_name=""):
        calls.append(prompt)
        return "{}"

    payload = _build(data_date="2026-07-14", event_date="2026-07-18", caller=caller)

    assert payload["time_consistency"]["consistent"] is False
    assert payload["publish_gate"]["status"] == "audit_only"
    reason = " ".join(payload["publish_gate"]["blocking_reasons"])
    assert "analysis_packet=2026-07-14" in reason
    assert "event_cards=2026-07-18" in reason
    assert payload["policy"]["llm_note"] == "time_inconsistency_publish_gate_audit_only"
    assert not calls


def test_matching_dates_preserve_publishable_behavior():
    payload = _build()

    assert payload["time_consistency"] == {
        "as_of": "2026-07-14",
        "members": [
            {"artifact": "analysis_packet", "date": "2026-07-14"},
            {"artifact": "final_adjudication", "date": "2026-07-14"},
            {"artifact": "event_cards", "date": "2026-07-14"},
        ],
        "consistent": True,
        "notes": [],
    }
    assert payload["publish_gate"]["status"] == "publishable_integrated_report"


def test_only_one_collectable_date_fails_closed_as_missing_as_of():
    payload = IntegratedSynthesisReportBuilder().build(
        pure_data_report={},
        analysis_packet={"meta": {"data_date": "2026-07-14"}},
        data_integrity_report={"publish_status": "publishable"},
    )

    assert payload["time_consistency"]["consistent"] is False
    assert "missing_as_of" in payload["time_consistency"]["notes"]
    assert payload["publish_gate"]["status"] == "audit_only"


def test_tolerance_allows_small_drift_and_records_note(monkeypatch):
    monkeypatch.setenv("NDX_INTEGRATED_TIME_TOLERANCE_DAYS", "4")
    payload = _build(data_date="2026-07-14", event_date="2026-07-18")

    assert payload["time_consistency"]["consistent"] is True
    assert payload["time_consistency"]["as_of"] == "2026-07-18"
    assert any("容差放行" in note for note in payload["time_consistency"]["notes"])
    assert payload["publish_gate"]["status"] == "publishable_integrated_report"


def test_reporter_warns_even_when_time_gate_skips_adjudication():
    generator = VNextReportGenerator(reports_dir="/tmp/w1_time_consistency")
    html = generator._integrated_adjudication_block({
        "integrated_synthesis_report": {
            "integrated_adjudication": None,
            "time_consistency": {
                "as_of": None,
                "members": [
                    {"artifact": "analysis_packet", "date": "2026-07-14"},
                    {"artifact": "event_cards", "date": "2026-07-18"},
                ],
                "consistent": False,
                "notes": ["date_mismatch"],
            },
        }
    })

    assert "本报告输入时点不一致" in html
    assert "analysis_packet=2026-07-14" in html
    assert "event_cards=2026-07-18" in html
    assert "不构成正式结论" in html
    assert 'class="boundary-card bad"' in html


def test_all_investigation_dates_participate_in_gate():
    payload = IntegratedSynthesisReportBuilder().build(
        pure_data_report={},
        analysis_packet={"meta": {"data_date": "2026-07-14"}},
        final_adjudication={"generated_at": "2026-07-14T12:00:00Z"},
        event_interpretation_cards={"effective_date": "2026-07-14"},
        investigation_reports=[
            {"investigation_id": "one", "effective_date": "2026-07-14"},
            {"investigation_id": "two", "as_of_date": "2026-07-14"},
            {"investigation_id": "three", "meta": {"data_date": "2026-07-14"}},
            {"investigation_id": "four", "effective_date": "2026-07-18"},
        ],
        data_integrity_report={"publish_status": "publishable"},
    )

    assert payload["time_consistency"]["consistent"] is False
    assert payload["time_consistency"]["members"][-1] == {
        "artifact": "investigation:four",
        "date": "2026-07-18",
    }
    assert "investigation:four=2026-07-18" in " ".join(payload["publish_gate"]["blocking_reasons"])


def test_invalid_present_date_fails_closed_instead_of_being_ignored():
    payload = IntegratedSynthesisReportBuilder().build(
        pure_data_report={},
        analysis_packet={"meta": {"data_date": "not-a-date"}},
        final_adjudication={"generated_at": "2026-07-14T00:00:00Z"},
        event_interpretation_cards={"effective_date": "2026-07-14"},
        data_integrity_report={"publish_status": "publishable"},
    )

    assert payload["time_consistency"]["consistent"] is False
    assert "invalid_as_of:analysis_packet=not-a-date" in payload["time_consistency"]["notes"]
    assert "invalid_as_of:analysis_packet=not-a-date" in " ".join(
        payload["publish_gate"]["blocking_reasons"]
    )
    assert payload["publish_gate"]["status"] == "audit_only"


def test_time_note_has_priority_even_without_llm_caller():
    payload = _build(data_date="2026-07-14", event_date="2026-07-18", caller=None)

    assert payload["policy"]["llm_note"] == "time_inconsistency_publish_gate_audit_only"
