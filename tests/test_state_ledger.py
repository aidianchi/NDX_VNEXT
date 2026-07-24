import json
import os
import sys
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from state_ledger import (
    _git_sha,
    append_method_revision_entry,
    STATE_VARIABLE_SPEC_BY_KEY,
    append_state_ledger_entry,
    build_state_ledger_entry,
    extract_state_variables,
)


def _write_run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "20260707_test_run"
    run_dir.mkdir()
    analysis_packet = {
        "meta": {"schema_version": "1.0", "data_date": "2026-07-07", "backtest_date": None},
        "raw_data": {
            "L4": {
                "get_ndx_pe_and_earnings_yield": {"value": {"TrailingPE": 32.84, "ForwardPE": 22.52, "ForwardEarningsYield": 4.44}},
                "get_ndx_wind_valuation_snapshot": {"value": None},
            },
            "L2": {
                "get_vix": {"value": {"level": 15.57, "historical_stats": {"percentile_10y": 0.389}}},
                "get_hyg_momentum": {"value": {"level": 79.87, "relativity": {"percentile_1y": 15.9}}},
            },
            "L3": {
                "get_advance_decline_line": {"value": {"level": 380, "trend": "rising"}},
                "get_ndx_ndxe_ratio": {"value": {"level": 2.905, "relativity": {"percentile_10y": 0.959}}},
            },
            "L5": {
                "get_multi_scale_ma_position": {"value": {"current_price": 722.82, "cross_scale_divergence": {"short_vs_long": 13.91}}},
                "get_donchian_channels_qqq": {"value": {"upper": 736.0, "position_pct": 62.0}},
            },
            "L1": {
                "get_net_liquidity_momentum": {"value": {"level": 5815.95, "momentum_4w": -25.89}},
            },
        },
    }
    (run_dir / "analysis_packet.json").write_text(json.dumps(analysis_packet, ensure_ascii=False), encoding="utf-8")
    (run_dir / "golden_pit_checklist.json").write_text(json.dumps({
        "schema_version": "golden_pit_checklist_v1",
        "entries": [
            {"condition_id": "buy_valuation_entry_zone", "current_status": "not_met"},
            {"condition_id": "sell_trend_break_confirmed", "current_status": "not_met"},
            {"condition_id": "claim:claim:final:abc123", "current_status": "met"},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    (run_dir / "final_claim_ledger.json").write_text(json.dumps({
        "schema_version": "claim_ledger_v1",
        "publish_gate": {"status": "pass"},
    }, ensure_ascii=False), encoding="utf-8")
    (run_dir / "hypothesis_competition.json").write_text(json.dumps({
        "leading_hypothesis_id": "hyp_base_x",
        "hypotheses": [{"hypothesis_id": "hyp_base_x"}, {"hypothesis_id": "hyp_counter_y"}],
    }, ensure_ascii=False), encoding="utf-8")
    (run_dir / "data_integrity_report.json").write_text(json.dumps({"blocked": False, "unpublishable": False}), encoding="utf-8")
    return run_dir


def test_extract_state_variables_records_values_and_missing():
    packet = {
        "raw_data": {
            "L2": {"get_vix": {"value": {"level": 20.0, "historical_stats": {"percentile_10y": 0.8}}}},
        }
    }
    variables, missing = extract_state_variables(packet)
    assert variables["risk_appetite.vix_level"] == 20.0
    assert variables["risk_appetite.vix_percentile_10y"] == 0.8
    assert STATE_VARIABLE_SPEC_BY_KEY["risk_appetite.vix_percentile_10y"]["unit"] == "percentile_0_1"
    assert variables["valuation.trailing_pe"] is None
    assert "valuation.trailing_pe" in missing
    # 缺 donchian/price 时派生回撤也必须显式记缺，不得静默编造。
    assert variables["trend.drawdown_from_donchian_upper_pct"] is None
    assert "trend.drawdown_from_donchian_upper_pct" in missing


def test_wind_percentile_uses_real_payload_path_and_declares_scale_and_ref():
    packet = {
        "raw_data": {
            "L4": {
                "get_ndx_wind_valuation_snapshot": {
                    "value": {"PEHistoricalPercentile": 83.2}
                }
            }
        }
    }
    variables, _ = extract_state_variables(packet)
    spec = STATE_VARIABLE_SPEC_BY_KEY["valuation.wind_pe_percentile"]

    assert variables["valuation.wind_pe_percentile"] == 83.2
    assert spec["unit"] == "percentile_0_100"
    assert spec["evidence_ref"] == "L4.get_ndx_wind_valuation_snapshot#PEHistoricalPercentile"
    assert "<=" in spec["allowed_operators"]


def test_nested_and_derived_state_variables_declare_complete_evidence_refs():
    assert STATE_VARIABLE_SPEC_BY_KEY["risk_appetite.vix_percentile_10y"]["evidence_refs"] == [
        "L2.get_vix#historical_stats.percentile_10y"
    ]
    assert STATE_VARIABLE_SPEC_BY_KEY["trend.drawdown_from_donchian_upper_pct"]["evidence_refs"] == [
        "L5.get_donchian_channels_qqq#upper",
        "L5.get_multi_scale_ma_position#current_price",
    ]


def test_new_l4_state_variables_follow_actual_payload_paths_and_units():
    packet = {
        "raw_data": {
            "L4": {
                "get_ndx_forward_pe_full_constituent": {
                    "value": 24.5,
                    "forward_earnings_yield": 0.0408163265,
                },
                "get_ndx_earnings_revision_metrics": {
                    "value": {
                        "slope_30d": {"value": 0.025},
                        "slope_90d": {"value": -0.01},
                    }
                },
            }
        }
    }

    variables, missing = extract_state_variables(packet)

    assert variables["valuation.ndx_forward_pe_full_constituent"] == 24.5
    assert (
        variables["valuation.ndx_forward_earnings_yield_full_constituent"]
        == 0.0408163265
    )
    assert variables["earnings_revision.ndx_slope_30d"] == 0.025
    assert variables["earnings_revision.ndx_slope_90d"] == -0.01
    assert "valuation.ndx_forward_pe_full_constituent" not in missing
    assert (
        STATE_VARIABLE_SPEC_BY_KEY[
            "valuation.ndx_forward_earnings_yield_full_constituent"
        ]["unit"]
        == "decimal"
    )
    assert (
        STATE_VARIABLE_SPEC_BY_KEY["earnings_revision.ndx_slope_30d"][
            "evidence_ref"
        ]
        == "L4.get_ndx_earnings_revision_metrics#value.slope_30d.value"
    )


def test_build_state_ledger_entry_is_deterministic_and_bounded(tmp_path: Path):
    run_dir = _write_run_dir(tmp_path)
    entry = build_state_ledger_entry(run_dir, official=True)

    assert entry["schema_version"] == "state_ledger_v1"
    assert entry["run_id"] == run_dir.name
    assert entry["data_date"] == "2026-07-07"
    assert entry["official"] is True
    assert entry["state_variables"]["valuation.forward_pe"] == 22.52
    assert entry["state_variables"]["trend.drawdown_from_donchian_upper_pct"] == 1.79
    # Wind 离线时如实记缺，不冒充。
    assert entry["state_variables"]["valuation.wind_pe_percentile"] is None
    assert "valuation.wind_pe_percentile" in entry["missing_variables"]
    # claim 回声条目（内容哈希 ID）永不入台账。
    assert set(entry["profile_condition_statuses"]) == {"buy_valuation_entry_zone", "sell_trend_break_confirmed"}
    assert entry["gates"]["claim_ledger_publish_gate"] == "pass"
    assert entry["llm_derived"]["llm_derived"] is True
    assert entry["llm_derived"]["hypothesis_count"] == 2
    assert "must not be injected" in entry["no_backflow_rule"]


def test_append_state_ledger_entry_appends_once_per_run_id(tmp_path: Path):
    run_dir = _write_run_dir(tmp_path)
    ledger_path = tmp_path / "state_ledger.jsonl"

    first = append_state_ledger_entry(run_dir, official=False, ledger_path=ledger_path)
    second = append_state_ledger_entry(run_dir, official=True, ledger_path=ledger_path)

    assert first["status"] == "appended"
    assert second["status"] == "skipped_duplicate_run_id"
    lines = [line for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 1
    stored = json.loads(lines[0])
    assert stored["run_id"] == run_dir.name
    assert stored["official"] is False


def test_method_revision_ledger_exact_duplicate_is_idempotent_and_distinct_change_appends(tmp_path: Path):
    ledger_path = tmp_path / "method_revision_ledger.jsonl"
    real_commit = _git_sha()
    entry = {
        "date": "2026-07-27",
        "error_pattern": "direction_wrong clustered in timing claims",
        "affected_element": {"type": "prompt", "path": "src/agent_analysis/prompts/final_adjudicator.md"},
        "change_ref": real_commit,
        "expected_effect": "reduce unsupported directional timing claims",
        "review_after": "2026-08-27",
    }
    first = append_method_revision_entry(entry, ledger_path=ledger_path)
    duplicate = append_method_revision_entry(dict(entry), ledger_path=ledger_path)
    changed = dict(entry, error_pattern="direction_wrong clustered in valuation claims", review_after="2026-09-27")
    third = append_method_revision_entry(changed, ledger_path=ledger_path)
    assert [first["status"], duplicate["status"], third["status"]] == [
        "appended",
        "skipped_exact_duplicate",
        "appended",
    ]
    rows = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines()]
    assert rows == [entry, changed]


def test_method_revision_ledger_rejects_uncommitted_or_malformed_entries(tmp_path: Path):
    entry = {
        "date": "2026-07-27",
        "error_pattern": "direction_wrong",
        "affected_element": {"type": "prompt", "path": "prompt.md"},
        "change_ref": "deadbee",
        "expected_effect": "improve calibration",
        "review_after": "2026-08-27",
    }
    with pytest.raises(ValueError, match="existing git commit"):
        append_method_revision_entry(entry, ledger_path=tmp_path / "ledger.jsonl")
