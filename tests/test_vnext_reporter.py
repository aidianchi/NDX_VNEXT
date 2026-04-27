import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent_analysis.vnext_reporter import VNextReportGenerator


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_vnext_reporter_generates_native_ui(tmp_path: Path):
    run_dir = tmp_path / "run"
    _write_json(
        run_dir / "final_adjudication.json",
        {
            "approval_status": "approved_with_reservations",
            "final_stance": "中性偏谨慎",
            "confidence": "medium",
            "key_support_chains": [
                {
                    "chain_description": "高实际利率压制估值",
                    "evidence_refs": ["L1.get_10y_real_rate", "L4.get_equity_risk_premium"],
                    "weight": 0.4,
                }
            ],
            "must_preserve_risks": ["估值压缩风险"],
            "adjudicator_notes": "保留核心冲突。",
            "evidence_refs": ["Risk report"],
        },
    )
    _write_json(
        run_dir / "synthesis_packet.json",
        {
            "packet_meta": {
                "data_date": "2026-04-23",
                "indicator_total": 34,
                "indicator_successful": 34,
            },
            "objective_firewall_summary": {
                "object_clear": True,
                "authority_clear": True,
                "timing_clear": True,
                "cross_layer_verified": True,
                "strongest_falsifier": "盈利上修足以抵消折现率压力。",
                "unresolved_tensions": ["real_rate_vs_valuation: 高真实利率与高估值并存。"],
                "warnings": [],
            },
        },
    )
    _write_json(
        run_dir / "layer_cards" / "L1.json",
        {
            "layer": "L1",
            "local_conclusion": "宏观偏紧。",
            "confidence": "medium",
            "risk_flags": ["valuation_compression"],
            "layer_synthesis": "实际利率仍是主约束。",
            "internal_conflict_analysis": "净流动性改善与高实际利率冲突。",
            "cross_layer_hooks": [{"target_layer": "L4", "question": "估值是否已反映折现率压力？"}],
            "indicator_analyses": [
                {
                    "function_id": "get_10y_real_rate",
                    "metric": "10Y Real Rate",
                    "current_reading": "1.92%",
                    "normalized_state": "restrictive",
                    "narrative": "实际利率压制成长股估值。",
                    "reasoning_process": "实际利率上升 -> 折现率上升 -> 估值承压。",
                    "first_principles_chain": ["实际利率上升", "折现率上升", "估值承压"],
                    "cross_layer_implications": ["需要 L4 验证估值"],
                    "risk_flags": ["valuation_compression"],
                    "permission_type": "fact",
                    "canonical_question": "真实贴现率是否正在给 NDX 估值施压？",
                    "misread_guards": ["不是单纯的政策变量。"],
                    "cross_validation_targets": ["get_ndx_pe_and_earnings_yield"],
                    "falsifiers": ["盈利上修足以抵消折现率压力。"],
                    "core_vs_tactical_boundary": "核心框架指标。",
                }
            ],
        },
    )
    for layer in ["L2", "L3", "L4", "L5"]:
        _write_json(
            run_dir / "layer_cards" / f"{layer}.json",
            {
                "layer": layer,
                "local_conclusion": f"{layer} placeholder",
                "confidence": "medium",
                "layer_synthesis": f"{layer} synthesis",
                "internal_conflict_analysis": f"{layer} conflict",
                "indicator_analyses": [],
            },
        )
    _write_json(
        run_dir / "bridge_memos" / "bridge_0.json",
        {
            "bridge_type": "macro_valuation",
            "cross_layer_claims": [],
            "conflicts": [
                {
                    "conflict_type": "L1_vs_L4",
                    "severity": "high",
                    "description": "高利率与高估值冲突。",
                    "implication": "估值压缩。",
                }
            ],
            "typed_conflicts": [
                {
                    "conflict_id": "real_rate_vs_valuation",
                    "conflict_type": "valuation_discount_rate",
                    "severity": "high",
                    "confidence": "medium",
                    "description": "高真实利率与高估值并存。",
                    "mechanism": "真实利率提高折现率。",
                    "implication": "估值压力必须保留。",
                    "involved_layers": ["L1", "L4"],
                    "evidence_refs": ["L1.get_10y_real_rate"],
                    "falsifiers": ["盈利上修足以抵消折现率压力。"],
                }
            ],
            "resonance_chains": [
                {
                    "chain_id": "risk_off_resonance",
                    "layers": ["L1", "L2", "L5"],
                    "description": "宏观约束、信用脆弱和技术节奏同时偏谨慎。",
                    "evidence_refs": ["L1.get_10y_real_rate"],
                    "implication": "反弹需要更强确认。",
                    "confidence": "medium",
                }
            ],
            "transmission_paths": [
                {
                    "path_id": "rates_to_valuation",
                    "source_layer": "L1",
                    "target_layer": "L4",
                    "mechanism": "真实利率通过折现率传导到估值倍数。",
                    "evidence_refs": ["L1.get_10y_real_rate"],
                    "implication": "估值安全边际变薄。",
                    "confidence": "medium",
                }
            ],
            "implication_for_ndx": "谨慎。",
        },
    )
    _write_json(run_dir / "critique.json", {"overall_assessment": "可用", "cross_layer_issues": []})
    _write_json(run_dir / "risk_boundary_report.json", {"failure_conditions": [], "must_preserve_risks": []})
    _write_json(run_dir / "schema_guard_report.json", {"passed": True})

    reporter = VNextReportGenerator(reports_dir=str(tmp_path / "reports"))
    report_path = reporter.run(run_dir)
    html = Path(report_path).read_text(encoding="utf-8")

    assert "NDX vNext Native Artifact UI" in html
    assert "brief · 投研长文" in html
    assert "主论点证据链" in html
    assert "Layer Workbench" in html
    assert "evidence-L1-get_10y_real_rate" in html
    assert "L1_vs_L4" in html
    assert "Objective Firewall" in html
    assert "Permission Type" in html
    assert "Typed Conflicts" in html
    assert "Transmission Paths" in html
    assert "real_rate_vs_valuation" in html
    assert "rates_to_valuation" in html
    assert "risk_off_resonance" in html
    assert 'data-typed-conflict="real_rate_vs_valuation"' in html
    assert 'data-transmission-path="rates_to_valuation"' in html
    assert 'data-resonance-chain="risk_off_resonance"' in html

    atlas_path = reporter.run(run_dir, template="atlas")
    atlas_html = Path(atlas_path).read_text(encoding="utf-8")
    assert "atlas · 证据地图" in atlas_html
    assert "template-atlas" in atlas_html
