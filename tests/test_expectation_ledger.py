"""W4 expectation-versus-realized supporting-only ledger."""
from __future__ import annotations

import json
import math
import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import main as pipeline_main  # noqa: E402
from agent_analysis.contracts import Confidence, SynthesisPacket, ThesisDraft  # noqa: E402
from agent_analysis.orchestrator import VNextOrchestrator  # noqa: E402
from agent_analysis.vnext_reporter import VNextReportGenerator  # noqa: E402
from expectation_ledger import (  # noqa: E402
    _fetch_fred_actual_rate_series,
    _historical_rate_inputs,
    _next_business_day,
    build_expectation_ledger,
)


EXPECTED_DIVERGENCE_RULE = '- `priced_narrative` 必须包含一句明确的**分歧声明**：本判断与市场当前定价共识的分歧点是什么。若判断与定价方向一致，如实写"本判断与市场定价方向一致，超额观点为零"；无法判断定价状态时写 unclear 并说明缺哪条证据。分歧声明只能引用输入 refs（利率路径、盈利预期、波动溢价、预期-兑现台账），禁止凭空断言"市场认为"。'


def _write_vintage(root: Path, day: str, values: dict[str, float]) -> None:
    payload = {
        "archive_date": day.replace("-", ""),
        "per_ticker": {
            ticker: {"yfinance": {"fields": {"eps_trend": {"records": [
                {"period": "+1y", "current": value, "30daysAgo": 9999, "90daysAgo": 9999}
            ]}}}}
            for ticker, value in values.items()
        },
    }
    path = root / day.replace("-", "") / "eps_consensus.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _packet(effective_date: str, implied_rate: float = 4.0) -> dict:
    return {"raw_data": {"L1": {"get_fed_funds_rate_path": {"value": {
        "effective_date": effective_date,
        "status": "available",
        "path": [{"months_ahead": 0, "implied_rate": implied_rate}],
        "state": "flat_path",
    }}}}}


def test_earnings_book_uses_cross_snapshot_forward_eps_only(tmp_path: Path):
    vintage = tmp_path / "vintage"
    _write_vintage(vintage, "2026-01-01", {"AAA": 8.0, "BBB": 20.0})
    _write_vintage(vintage, "2026-03-01", {"AAA": 9.0, "BBB": 20.0})
    _write_vintage(vintage, "2026-04-01", {"AAA": 10.0, "BBB": 18.0})

    ledger = build_expectation_ledger(
        effective_date="2026-04-01",
        vintage_root=vintage,
        analysis_root=tmp_path / "none",
        historical_paths=[],
        actual_rate_series=[],
    )

    earnings = ledger["earnings_expectations"]
    window30 = next(item for item in earnings["windows"] if item["window_days"] == 30)
    window90 = next(item for item in earnings["windows"] if item["window_days"] == 90)
    assert window30["status"] == "available" and window90["status"] == "available"
    assert window30["ticker_changes"][0]["prior_forward_eps"] == 9.0
    assert window30["ticker_changes"][0]["current_forward_eps"] == 10.0
    assert window30["ticker_changes"][0]["change_pct"] == 11.111111
    assert all(row["current_forward_eps"] != 9999 for row in window30["ticker_changes"])


def test_rate_book_compares_old_pricing_with_dated_actuals(tmp_path: Path):
    january_dff = [
        {"date": date(2026, 1, day).isoformat(), "rate": 4.05, "series_id": "DFF"}
        for day in range(1, 32)
    ]
    ledger = build_expectation_ledger(
        effective_date="2026-02-15",
        vintage_root=tmp_path / "none",
        analysis_root=tmp_path / "none2",
        current_analysis_packet=_packet("2026-02-15", 3.8),
        historical_paths=[_packet("2026-01-01", 4.25)["raw_data"]["L1"]["get_fed_funds_rate_path"]["value"]],
        actual_rate_series=january_dff,
    )

    rate = ledger["rate_path"]
    assert rate["status"] == "available"
    assert rate["current_path_status"] == "available"
    assert rate["current_path"]["effective_date"] == "2026-02-15"
    assert rate["comparisons"][0]["realized_rate"] == 4.05
    assert rate["comparisons"][0]["priced_minus_realized_pp"] == 0.2
    assert rate["comparisons"][0]["actual_observation_count"] == 31


def test_volatility_premium_uses_forward_21_day_window(tmp_path: Path):
    start = date(2026, 1, 1)
    qqq_rows, vix_rows = [], []
    close = 100.0
    for index in range(55):
        day = start + timedelta(days=index)
        close *= math.exp(0.008 if index % 2 == 0 else -0.004)
        qqq_rows.append({"time": day.isoformat(), "close": close})
        vix_rows.append({"time": day.isoformat(), "value": 22.0 + (index % 5)})
    ledger = build_expectation_ledger(
        effective_date="2026-02-24",
        vintage_root=tmp_path / "none",
        analysis_root=tmp_path / "none2",
        chart_time_series={"series": {"QQQ_OHLCV": {"rows": qqq_rows}, "VIX": {"rows": vix_rows}}},
        historical_paths=[],
        actual_rate_series=[],
    )

    vol = ledger["volatility_premium"]
    assert vol["status"] == "available"
    assert vol["sample_count"] == 34
    assert vol["premium_series"][0]["start_date"] == "2026-01-01"
    assert vol["premium_series"][0]["end_date"] == "2026-01-22"
    assert vol["recent_percentile"] is not None


def test_coverage_shortfalls_and_supporting_only_are_explicit(tmp_path: Path):
    ledger = build_expectation_ledger(
        effective_date="2026-07-18",
        vintage_root=tmp_path / "missing",
        analysis_root=tmp_path / "missing2",
        historical_paths=[],
        actual_rate_series=[],
    )
    assert ledger["metric_authority"] == "supporting_only"
    assert "must_not_enter_l1_l5_raw_prompt_or_evidence_ref" in ledger["downgrade_rules"]
    assert ledger["earnings_expectations"]["status"] == "insufficient_coverage"
    assert ledger["rate_path"]["status"] == "accumulating"
    assert ledger["rate_path"]["current_path_status"] == "missing"
    assert ledger["rate_path"]["note"] == "对照样本积累中"
    assert ledger["volatility_premium"]["status"] == "insufficient_coverage"
    assert "evidence_refs" not in json.dumps(ledger)
    assert "core_allowed" not in json.dumps(ledger)


def test_final_adjudicator_requires_explicit_pricing_divergence_statement():
    prompt_path = Path(__file__).resolve().parents[1] / "src" / "agent_analysis" / "prompts" / "final_adjudicator.md"
    assert EXPECTED_DIVERGENCE_RULE in prompt_path.read_text(encoding="utf-8")


def test_reporter_renders_all_three_supporting_books_and_escapes_content(tmp_path: Path):
    ledger = build_expectation_ledger(
        effective_date="2026-07-18",
        vintage_root=tmp_path / "missing",
        analysis_root=tmp_path / "missing2",
        historical_paths=[],
        actual_rate_series=[],
    )
    ledger["rate_path"]["note"] = "对照样本积累中<script>alert(1)</script>"
    html = VNextReportGenerator(reports_dir=str(tmp_path / "reports"))._expectation_ledger_block(
        {"expectation_vs_realized": ledger}
    )
    assert "预期与兑现" in html
    assert "盈利预期" in html and "利率路径" in html and "波动溢价" in html
    assert "supporting_only" in html
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html
    assert "<script>alert(1)</script>" not in html


def test_main_ledger_failure_is_non_blocking_and_writes_failure_note(monkeypatch, tmp_path: Path):
    def fail(*args, **kwargs):
        raise RuntimeError("constructed ledger failure")

    captured = {}

    def fallback(run_dir, *, effective_date, error):
        captured.update({"run_dir": run_dir, "effective_date": effective_date, "error": str(error)})
        return str(Path(run_dir) / "expectation_vs_realized.json")

    monkeypatch.setattr(pipeline_main, "write_expectation_ledger", fail)
    monkeypatch.setattr(pipeline_main, "write_expectation_ledger_failure", fallback)
    result = pipeline_main._write_expectation_ledger_non_blocking(str(tmp_path), "2026-07-18")
    assert result == str(tmp_path / "expectation_vs_realized.json")
    assert captured == {
        "run_dir": str(tmp_path),
        "effective_date": "2026-07-18",
        "error": "constructed ledger failure",
    }


def test_main_ledger_double_failure_still_does_not_block(monkeypatch, tmp_path: Path):
    def fail(*args, **kwargs):
        raise RuntimeError("constructed failure")

    monkeypatch.setattr(pipeline_main, "write_expectation_ledger", fail)
    monkeypatch.setattr(pipeline_main, "write_expectation_ledger_failure", fail)
    assert pipeline_main._write_expectation_ledger_non_blocking(str(tmp_path), "2026-07-18") == ""


def test_governance_gets_pit_matched_compact_ledger_without_core_refs(tmp_path: Path):
    ledger = build_expectation_ledger(
        effective_date="2026-07-18",
        vintage_root=tmp_path / "missing",
        analysis_root=tmp_path / "missing2",
        historical_paths=[],
        actual_rate_series=[],
    )
    (tmp_path / "expectation_vs_realized.json").write_text(json.dumps(ledger), encoding="utf-8")
    orchestrator = VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=object(),
    )
    thesis = ThesisDraft(
        main_thesis="构造样本。",
        environment_assessment="不判断。",
        valuation_assessment="不判断。",
        timing_assessment="不判断。",
        overall_confidence=Confidence.LOW,
    )
    governance = orchestrator._build_governance_input_packet(
        synthesis_packet=SynthesisPacket(packet_meta={"data_date": "2026-07-18"}),
        thesis=thesis,
    )
    summary = governance.pricing_expectation_ledger
    assert summary["metric_authority"] == "supporting_only"
    assert summary["artifact_ref"] == "expectation_vs_realized.json"
    assert summary["usage_rule"] == "pricing_narrative_support_only; forbidden_as_core_ref"
    assert "premium_series" not in json.dumps(summary)
    assert "ticker_changes" not in json.dumps(summary)
    assert "evidence_refs" not in json.dumps(summary)


def test_governance_rejects_mismatched_or_overclaimed_ledger(tmp_path: Path):
    base = build_expectation_ledger(
        effective_date="2026-07-17",
        vintage_root=tmp_path / "missing",
        analysis_root=tmp_path / "missing2",
        historical_paths=[],
        actual_rate_series=[],
    )
    (tmp_path / "expectation_vs_realized.json").write_text(json.dumps(base), encoding="utf-8")
    orchestrator = VNextOrchestrator(available_models=["fake"], output_dir=str(tmp_path), llm_engine=object())
    synthesis = SynthesisPacket(packet_meta={"data_date": "2026-07-18"})
    summary = orchestrator._pricing_expectation_ledger_summary(synthesis)
    assert summary["status"] == "audit_only_effective_date_mismatch"
    assert "earnings_expectations" not in summary

    base["effective_date"] = "2026-07-18"
    base["metric_authority"] = "core_allowed"
    (tmp_path / "expectation_vs_realized.json").write_text(json.dumps(base), encoding="utf-8")
    summary = orchestrator._pricing_expectation_ledger_summary(synthesis)
    assert summary["status"] == "rejected_authority_mismatch"
    assert "earnings_expectations" not in summary


def test_future_dated_current_rate_path_is_rejected_at_build_and_governance_boundaries(tmp_path: Path):
    ledger = build_expectation_ledger(
        effective_date="2026-07-14",
        vintage_root=tmp_path / "missing",
        analysis_root=tmp_path / "missing2",
        current_analysis_packet=_packet("2026-07-15", 3.8),
        historical_paths=[],
        actual_rate_series=[],
    )
    assert ledger["rate_path"]["current_path"] is None
    assert ledger["rate_path"]["current_path_status"] == "rejected_future_effective_date"

    ledger["rate_path"]["current_path"] = _packet("2026-07-15", 3.8)["raw_data"]["L1"]["get_fed_funds_rate_path"]["value"]
    (tmp_path / "expectation_vs_realized.json").write_text(json.dumps(ledger), encoding="utf-8")
    orchestrator = VNextOrchestrator(available_models=["fake"], output_dir=str(tmp_path), llm_engine=object())
    summary = orchestrator._pricing_expectation_ledger_summary(
        SynthesisPacket(packet_meta={"data_date": "2026-07-14"})
    )
    assert summary["status"] == "audit_only_nested_rate_path_date_mismatch"
    assert "earnings_expectations" not in summary


def test_historical_rate_discovery_accepts_only_publishable_date_matched_runs(tmp_path: Path):
    def write_run(name: str, packet_date: str, path_date: str, *, blocked: bool = False) -> None:
        run = tmp_path / name
        run.mkdir()
        (run / "data_integrity_report.json").write_text(json.dumps({
            "blocked": blocked,
            "unpublishable": blocked,
            "publish_status": "blocked" if blocked else "publishable",
        }), encoding="utf-8")
        packet = _packet(path_date, 4.0)
        packet["meta"] = {"data_date": packet_date}
        packet["raw_data"]["L1"]["get_fed_funds_rate_path"]["value"]["effr_anchor"] = {
            "series_id": "EFFR",
            "rate": 3.9,
            "data_date": packet_date,
        }
        (run / "analysis_packet.json").write_text(json.dumps(packet), encoding="utf-8")

    write_run("accepted", "2026-01-01", "2026-01-01")
    write_run("blocked", "2026-01-02", "2026-01-02", blocked=True)
    write_run("mismatched", "2026-01-03", "2026-01-04")
    paths, actuals, audit = _historical_rate_inputs(tmp_path, date(2026, 2, 15))
    assert [item["effective_date"] for item in paths] == ["2026-01-01"]
    assert actuals == [{
        "date": "2026-01-01",
        "available_date": "2026-01-01",
        "rate": 3.9,
        "series_id": "EFFR",
        "source": "qualified_run_effr_anchor",
    }]
    assert audit["qualified_runs"] == 1
    assert audit["rejected_runs"] == 2
    assert audit["rejection_counts"] == {
        "data_integrity_not_publishable": 1,
        "packet_path_date_mismatch": 1,
    }


def test_fred_actual_discovery_uses_effr_and_conservative_next_business_day(monkeypatch):
    calls = []

    def fake_fred(series_id, days=5475, end_date=None):
        calls.append((series_id, days, end_date))
        return pd.DataFrame({
            "date": ["2026-01-08", "2026-01-09", "2026-01-12"],
            "value": [4.1, 4.2, 4.3],
        })

    import tools_common

    monkeypatch.setattr(tools_common, "get_fred_series", fake_fred)
    rows, audit = _fetch_fred_actual_rate_series(date(2026, 1, 12))
    assert calls == [("EFFR", 5475, "2026-01-12")]
    assert [row["date"] for row in rows] == ["2026-01-08", "2026-01-09"]
    assert rows[-1]["available_date"] == "2026-01-12"
    assert audit == {
        "source": "FRED EFFR/DFF",
        "status": "available",
        "series_id": "EFFR",
        "observation_count": 2,
        "attempt_errors": [],
    }
    assert _next_business_day(date(2026, 1, 16)) == date(2026, 1, 20)  # MLK Day is not a release day.


def test_fred_actual_discovery_falls_back_from_effr_to_dff(monkeypatch):
    def fake_fred(series_id, days=5475, end_date=None):
        if series_id == "EFFR":
            raise RuntimeError("EFFR temporarily unavailable")
        return pd.DataFrame({"date": ["2026-01-08"], "value": [4.15]})

    import tools_common

    monkeypatch.setattr(tools_common, "get_fred_series", fake_fred)
    rows, audit = _fetch_fred_actual_rate_series(date(2026, 1, 12))
    assert rows[0]["series_id"] == "DFF"
    assert audit["series_id"] == "DFF"
    assert audit["attempt_errors"] == ["EFFR:RuntimeError:EFFR temporarily unavailable"]


def test_rate_book_does_not_call_month_realized_before_final_observation_is_visible(tmp_path: Path):
    january_effr = [
        {"date": item.isoformat(), "rate": 4.0, "series_id": "EFFR"}
        for item in pd.date_range("2026-01-01", "2026-01-30", freq="B").date
    ]
    ledger = build_expectation_ledger(
        effective_date="2026-01-31",
        vintage_root=tmp_path / "missing",
        analysis_root=tmp_path / "missing2",
        current_analysis_packet=_packet("2026-01-31", 3.8),
        historical_paths=[_packet("2026-01-01", 4.25)["raw_data"]["L1"]["get_fed_funds_rate_path"]["value"]],
        actual_rate_series=january_effr,
    )
    rate = ledger["rate_path"]
    assert rate["comparisons"] == []
    assert rate["status"] == "accumulating"
    assert rate["incomplete_months"][0]["series_checks"]["EFFR"] == {
        "reason": "final_observation_not_yet_visible",
        "final_visible_date": "2026-02-02",
    }
