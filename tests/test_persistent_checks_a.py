"""persistent_checks_a 的合成 fixture 测试。

纪律：不依赖 output/ 真实产物；每个检查至少一条"该过的通过"和一条"该红的
不同"路径；另加一个缺失 artifact 用例。反例必须真的红。
"""

import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent_analysis.persistent_checks_a import run_checks_a  # noqa: E402


def _write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def _write_payload(stage_dir: Path, payload: Dict[str, Any], attempt: int = 1) -> None:
    _write_json(
        stage_dir / f"attempt_{attempt}.payload.json",
        {"stage_key": stage_dir.name, "stage_name": stage_dir.name, "attempt": attempt, "payload": payload},
    )


def _write_prompt(stage_dir: Path, text: str, attempt: int = 1) -> None:
    stage_dir.mkdir(parents=True, exist_ok=True)
    (stage_dir / f"attempt_{attempt}.prompt.txt").write_text(text, encoding="utf-8")


def _write_ia_prompt(
    run_dir: Path,
    payload: Dict[str, Any],
    timestamp: str = "20260730T165426Z",
    attempt: int = 1,
) -> None:
    ia_dir = run_dir / "prompt_audit" / "integrated_adjudicator" / timestamp
    ia_dir.mkdir(parents=True, exist_ok=True)
    text = (
        "# 第三层综合裁决人\n"
        + "## 本轮输入\n\n"
        + "```json\n"
        + json.dumps(payload, ensure_ascii=False)
        + "\n```\n"
    )
    (ia_dir / f"attempt_{attempt}.prompt.txt").write_text(text, encoding="utf-8")


def _stage(run_dir: Path, name: str) -> Path:
    path = run_dir / "prompt_audit" / name
    path.mkdir(parents=True, exist_ok=True)
    return path


def _result_by_id(results: List[Dict[str, Any]], check_id: str) -> Dict[str, Any]:
    for result in results:
        if result["check_id"] == check_id:
            return result
    raise AssertionError(f"missing check {check_id}")


# ──────────────────────────────────────────────────────────────────────────
# PC-01 critic/risk 分料身份
# ──────────────────────────────────────────────────────────────────────────

def test_pc01_pass_c3_blind(tmp_path: Path):
    critic_gi = {
        "thesis_main": "主论点：估值压缩正在运行",
        "thesis_key_support_chains": [{"chain_description": "c"}],
        "thesis_hypothesis_responses": [{"hypothesis_id": "h"}],
    }
    # 论证盲形式收尾：risk 包里 thesis_* 键整个移除（不是清空值）。
    risk_gi = {
        "layer_summaries": [{"layer": "L1"}],
    }
    _write_payload(_stage(tmp_path, "critic"), {"governance_input": critic_gi})
    _write_payload(_stage(tmp_path, "risk"), {"governance_input": risk_gi})

    result = _result_by_id(run_checks_a(tmp_path), "PC-01")
    assert result["passed"] is True


def test_pc01_fail_risk_empty_thesis_keys_present(tmp_path: Path):
    # 反例：thesis_* 键以空值形式残留（""/[]）也算分料泄漏——键必须整个不存在。
    critic_gi = {
        "thesis_main": "主论点：估值压缩正在运行",
        "thesis_key_support_chains": [{"chain_description": "c"}],
        "thesis_hypothesis_responses": [{"hypothesis_id": "h"}],
    }
    risk_gi = {
        "thesis_main": "",
        "thesis_key_support_chains": [],
        "thesis_hypothesis_responses": [],
        "layer_summaries": [{"layer": "L1"}],
    }
    _write_payload(_stage(tmp_path, "critic"), {"governance_input": critic_gi})
    _write_payload(_stage(tmp_path, "risk"), {"governance_input": risk_gi})

    result = _result_by_id(run_checks_a(tmp_path), "PC-01")
    assert result["passed"] is False
    assert "thesis_main" in result["detail"]


def test_pc01_fail_pre_c3_identical(tmp_path: Path):
    gi = {
        "thesis_main": "主论点",
        "thesis_key_support_chains": [{"chain_description": "c"}],
        "thesis_hypothesis_responses": [{"hypothesis_id": "h"}],
    }
    _write_payload(_stage(tmp_path, "critic"), {"governance_input": gi})
    _write_payload(_stage(tmp_path, "risk"), {"governance_input": gi})

    result = _result_by_id(run_checks_a(tmp_path), "PC-01")
    assert result["passed"] is False
    assert "逐字节相同" in result["detail"]


# ──────────────────────────────────────────────────────────────────────────
# PC-02 治理站引用全集对账
# ──────────────────────────────────────────────────────────────────────────

def _write_pc02_artifacts(tmp_path: Path, critic_keys, reviser_keys, final_keys, risk_keys) -> None:
    _write_json(
        tmp_path / "thesis_draft.json",
        {
            "key_support_chains": [{"evidence_refs": ["R1"]}],
            "hypothesis_responses": [],
            "portfolio_actions": [],
            "time_horizon_views": [],
            "reader_conclusion": {},
            "principal_contradiction": {},
            "secondary_contradictions": [],
            "price_reflection_map": [
                {"evidence_refs": ["R2"], "counterevidence_refs": ["R5"]}
            ],
        },
    )
    _write_json(
        tmp_path / "synthesis_packet.json",
        {
            "evidence_index": {"R1": {}, "R2": {}, "R3": {}, "R4": {}, "R5": {}},
            "competing_hypotheses": [
                {
                    "source": "counter_thesis",
                    "support_evidence_refs": ["R3"],
                    "counter_evidence_refs": [],
                    "diagnostic_evidence_refs": [],
                }
            ],
            "high_severity_typed_conflicts": [{"evidence_refs": ["R4"]}],
            "high_severity_conflicts": [],
            "principal_contradictions": [],
            "layer_summaries": [{"indicator_refs": ["R4"]}],
        },
    )
    for station, keys in [
        ("critic", critic_keys),
        ("reviser", reviser_keys),
        ("final_adjudicator", final_keys),
        ("risk", risk_keys),
    ]:
        _write_payload(
            _stage(tmp_path, station),
            {"governance_input": {"key_evidence_refs": {ref: {} for ref in keys}}},
        )


def test_pc02_pass_full_union(tmp_path: Path):
    _write_pc02_artifacts(
        tmp_path,
        critic_keys=["R1", "R2", "R3", "R4", "R5"],
        reviser_keys=["R1", "R2", "R3", "R4", "R5"],
        final_keys=["R1", "R2", "R3", "R4", "R5"],
        risk_keys=["R4"],
    )
    result = _result_by_id(run_checks_a(tmp_path), "PC-02")
    assert result["passed"] is True


def test_pc02_fail_missing_counterevidence_and_risk_polluted(tmp_path: Path):
    _write_pc02_artifacts(
        tmp_path,
        critic_keys=["R1", "R2", "R3", "R4"],  # 缺 R5 counterevidence
        reviser_keys=["R1", "R2", "R3", "R4", "R5"],
        final_keys=["R1", "R2", "R3", "R4", "R5"],
        risk_keys=["R1"],  # 缺 R4，且 R1 是 thesis-only 引用
    )
    result = _result_by_id(run_checks_a(tmp_path), "PC-02")
    assert result["passed"] is False
    assert "critic 缺 1 条" in result["detail"]
    assert "R5" in result["detail"]
    assert "risk 缺 1 条" in result["detail"]
    assert "risk 混入非冲突/层摘要引用" in result["detail"]


# ──────────────────────────────────────────────────────────────────────────
# PC-03 final 只收修订稿+修订说明+机器对账（08-16 重裁）
# ──────────────────────────────────────────────────────────────────────────

def test_pc03_pass_without_thesis_original(tmp_path: Path):
    _write_json(
        tmp_path / "analysis_revised.json",
        {
            "revision_summary": "根据批评修订了主论点",
            "revision_claimed_fields": ["main_thesis"],
            "revised_thesis": {"main_thesis": "REVISED", "environment_assessment": "E"},
            "degraded_fallback": None,
        },
    )
    _write_payload(
        _stage(tmp_path, "final_adjudicator"),
        {
            "governance_input": {
                "thesis_main": "REVISED",
                "thesis_environment": "E",
                "revision_summary": "根据批评修订了主论点",
            }
        },
    )
    result = _result_by_id(run_checks_a(tmp_path), "PC-03")
    assert result["passed"] is True
    assert "全部命中修订稿实物" in result["detail"]
    assert "已从 final governance_input 移除" in result["detail"]


def test_pc03_pass_claimed_nested_field_present(tmp_path: Path):
    # 前科场景的反面：修订说明声称改了 why_retained，修订稿实物里确实有。
    _write_json(
        tmp_path / "analysis_revised.json",
        {
            "revision_summary": "补了保留冲突的 why_retained 解释",
            "revision_claimed_fields": ["main_thesis", "why_retained"],
            "revised_thesis": {
                "main_thesis": "REVISED",
                "retained_conflicts": [{"why_retained": "张力必须保留"}],
            },
            "degraded_fallback": None,
        },
    )
    _write_payload(
        _stage(tmp_path, "final_adjudicator"),
        {
            "governance_input": {
                "thesis_main": "REVISED",
                "revision_summary": "补了保留冲突的 why_retained 解释",
            }
        },
    )
    result = _result_by_id(run_checks_a(tmp_path), "PC-03")
    assert result["passed"] is True
    assert "全部命中修订稿实物" in result["detail"]


def test_pc03_fail_claimed_field_missing_from_revised_thesis(tmp_path: Path):
    # 前科场景：修订说明自称"添加 why_retained 解释"，修订稿实物里没有——必须拦下。
    _write_json(
        tmp_path / "analysis_revised.json",
        {
            "revision_summary": "添加了 why_retained 解释",
            "revision_claimed_fields": ["main_thesis", "why_retained"],
            "revised_thesis": {"main_thesis": "REVISED"},
            "degraded_fallback": None,
        },
    )
    _write_payload(
        _stage(tmp_path, "final_adjudicator"),
        {
            "governance_input": {
                "thesis_main": "REVISED",
                "revision_summary": "添加了 why_retained 解释",
            }
        },
    )
    result = _result_by_id(run_checks_a(tmp_path), "PC-03")
    assert result["passed"] is False
    assert "why_retained" in result["detail"]
    assert "不在实物中" in result["detail"]


def test_pc03_fail_claimed_fields_bad_shape(tmp_path: Path):
    _write_json(
        tmp_path / "analysis_revised.json",
        {
            "revision_summary": "修订了",
            "revision_claimed_fields": "main_thesis",
            "revised_thesis": {"main_thesis": "REVISED"},
            "degraded_fallback": None,
        },
    )
    _write_payload(
        _stage(tmp_path, "final_adjudicator"),
        {
            "governance_input": {
                "thesis_main": "REVISED",
                "revision_summary": "修订了",
            }
        },
    )
    result = _result_by_id(run_checks_a(tmp_path), "PC-03")
    assert result["passed"] is False
    assert "形状非法" in result["detail"]


def test_pc03_fail_thesis_original_leaked_back_into_final(tmp_path: Path):
    # 08-16 重裁后：thesis_original 再出现在 final governance_input 就是供给回潮。
    _write_json(
        tmp_path / "analysis_revised.json",
        {
            "revision_summary": "修订了",
            "revised_thesis": {"main_thesis": "REVISED"},
            "degraded_fallback": None,
        },
    )
    _write_payload(
        _stage(tmp_path, "final_adjudicator"),
        {
            "governance_input": {
                "thesis_original": {"main_thesis": "ORIGINAL"},
                "thesis_main": "REVISED",
                "revision_summary": "修订了",
            }
        },
    )
    result = _result_by_id(run_checks_a(tmp_path), "PC-03")
    assert result["passed"] is False
    assert "供给回潮" in result["detail"]


def test_pc03_fail_mismatch(tmp_path: Path):
    _write_json(
        tmp_path / "analysis_revised.json",
        {
            "revision_summary": "修订了",
            "revised_thesis": {"main_thesis": "REVISED"},
            "degraded_fallback": None,
        },
    )
    _write_payload(
        _stage(tmp_path, "final_adjudicator"),
        {
            "governance_input": {
                "thesis_main": "OLD",
                "revision_summary": "修订了",
            }
        },
    )
    result = _result_by_id(run_checks_a(tmp_path), "PC-03")
    assert result["passed"] is False
    assert "thesis_main" in result["detail"]


def test_pc03_pass_claimed_fields_match_code_recomputed_diff(tmp_path: Path):
    # T54 批 2 新口径：thesis_draft.json 在场时，revision_claimed_fields 必须与代码
    # 重算的顶层字段 diff 一致（身份比对，不读散文）。
    _write_json(
        tmp_path / "thesis_draft.json",
        {"main_thesis": "OLD", "environment_assessment": "E", "generated_at": "2026-08-16T00:00:00Z"},
    )
    _write_json(
        tmp_path / "analysis_revised.json",
        {
            "revision_summary": "改了主论点",
            "revision_claimed_fields": ["main_thesis"],
            "revised_thesis": {"main_thesis": "NEW", "environment_assessment": "E"},
            "degraded_fallback": None,
        },
    )
    _write_payload(
        _stage(tmp_path, "final_adjudicator"),
        {
            "governance_input": {
                "thesis_main": "NEW",
                "thesis_environment": "E",
                "revision_summary": "改了主论点",
            }
        },
    )
    result = _result_by_id(run_checks_a(tmp_path), "PC-03")
    assert result["passed"] is True
    assert "代码重算 diff 一致" in result["detail"]


def test_pc03_fail_claimed_fields_diverge_from_code_diff(tmp_path: Path):
    # 反例：记录声称只改了 main_thesis，代码重算发现 environment_assessment 也变了
    # （少报/谎报）——必须判红。
    _write_json(
        tmp_path / "thesis_draft.json",
        {"main_thesis": "OLD", "environment_assessment": "E"},
    )
    _write_json(
        tmp_path / "analysis_revised.json",
        {
            "revision_summary": "改了主论点",
            "revision_claimed_fields": ["main_thesis"],
            "revised_thesis": {"main_thesis": "NEW", "environment_assessment": "E2"},
            "degraded_fallback": None,
        },
    )
    _write_payload(
        _stage(tmp_path, "final_adjudicator"),
        {
            "governance_input": {
                "thesis_main": "NEW",
                "thesis_environment": "E2",
                "revision_summary": "改了主论点",
            }
        },
    )
    result = _result_by_id(run_checks_a(tmp_path), "PC-03")
    assert result["passed"] is False
    assert "代码重算" in result["detail"]
    assert "environment_assessment" in result["detail"]


def test_pc03_fail_claimed_fields_missing_when_thesis_draft_present(tmp_path: Path):
    # 新口径下 claimed 由代码装配、必然在场；thesis_draft.json 在场而 claimed 缺失即病
    # （老产物宽容只适用于 thesis_draft.json 缺席的旧 fixture/旧 run 场景）。
    _write_json(
        tmp_path / "thesis_draft.json",
        {"main_thesis": "OLD", "environment_assessment": "E"},
    )
    _write_json(
        tmp_path / "analysis_revised.json",
        {
            "revision_summary": "改了主论点",
            "revised_thesis": {"main_thesis": "NEW", "environment_assessment": "E"},
            "degraded_fallback": None,
        },
    )
    _write_payload(
        _stage(tmp_path, "final_adjudicator"),
        {
            "governance_input": {
                "thesis_main": "NEW",
                "thesis_environment": "E",
                "revision_summary": "改了主论点",
            }
        },
    )
    result = _result_by_id(run_checks_a(tmp_path), "PC-03")
    assert result["passed"] is False
    assert "缺失" in result["detail"]


# ──────────────────────────────────────────────────────────────────────────
# PC-04 IA ref_authority unknown 占比
# ──────────────────────────────────────────────────────────────────────────

def test_pc04_pass_under_threshold(tmp_path: Path):
    _write_ia_prompt(
        tmp_path,
        {
            "ref_authority": {
                "R1": {"usage": "core_allowed"},
                "R2": {"usage": "supporting_only"},
                "R3": {"usage": "unknown"},
            }
        },
    )
    result = _result_by_id(run_checks_a(tmp_path), "PC-04")
    assert result["passed"] is True


def test_pc04_fail_over_threshold(tmp_path: Path):
    _write_ia_prompt(
        tmp_path,
        {
            "ref_authority": {
                "R1": {"usage": "unknown"},
                "R2": {"usage": "unknown"},
                "R3": {"usage": "unknown"},
                "R4": {"usage": "core_allowed"},
            }
        },
    )
    result = _result_by_id(run_checks_a(tmp_path), "PC-04")
    assert result["passed"] is False
    assert "75.0%" in result["detail"]


# ──────────────────────────────────────────────────────────────────────────
# PC-05 委托调查 vs 进 IA 报告数对账
# ──────────────────────────────────────────────────────────────────────────

def test_pc05_pass_counts_match(tmp_path: Path):
    _write_json(tmp_path / "inquiry_router_output.json", {"agent_specs": [{"agent_id": "a"}, {"agent_id": "b"}]})
    _write_ia_prompt(
        tmp_path,
        {
            "allowed_investigation_ids": ["inv_a", "inv_b"],
            "investigation_reports": [
                {"investigation_id": "inv_a"},
                {"investigation_id": "inv_b"},
            ],
        },
    )
    result = _result_by_id(run_checks_a(tmp_path), "PC-05")
    assert result["passed"] is True


def test_pc05_pass_with_explicit_gap_placeholder(tmp_path: Path):
    """C8 后：失败调查以 investigation_gaps 显性占位，不得再当静默缺席。"""
    _write_json(
        tmp_path / "inquiry_router_output.json",
        {"agent_specs": [{"agent_id": "a"}, {"agent_id": "b"}, {"agent_id": "c"}]},
    )
    _write_ia_prompt(
        tmp_path,
        {
            "allowed_investigation_ids": ["inv_a", "inv_b"],
            "investigation_reports": [
                {"investigation_id": "inv_a"},
                {"investigation_id": "inv_b"},
            ],
            "investigation_gaps": [
                {"investigation_id": "inv_c", "status": "deterministic_stub"}
            ],
        },
    )
    result = _result_by_id(run_checks_a(tmp_path), "PC-05")
    assert result["passed"] is True
    assert "investigation_gaps=1" in result["detail"]


def test_pc05_fail_silent_absence(tmp_path: Path):
    _write_json(
        tmp_path / "inquiry_router_output.json",
        {"agent_specs": [{"agent_id": "a"}, {"agent_id": "b"}, {"agent_id": "c"}]},
    )
    _write_ia_prompt(
        tmp_path,
        {
            "allowed_investigation_ids": ["inv_a", "inv_b"],
            "investigation_reports": [
                {"investigation_id": "inv_a"},
                {"investigation_id": "inv_b"},
            ],
        },
    )
    result = _result_by_id(run_checks_a(tmp_path), "PC-05")
    assert result["passed"] is False
    assert "调查数对不上" in result["detail"]


# ──────────────────────────────────────────────────────────────────────────
# PC-06 CI 材料闭合性 + 立场字段
# ──────────────────────────────────────────────────────────────────────────

def _write_ci_prompt(ci_dir: Path, investigation: str, text: str, attempt: int = 1) -> None:
    ci_dir.mkdir(parents=True, exist_ok=True)
    (ci_dir / f"{investigation}.attempt_{attempt}.prompt.txt").write_text(text, encoding="utf-8")


def test_pc06_pass_closed_clean_material(tmp_path: Path):
    ci_dir = _stage(tmp_path, "controlled_investigation")
    _write_ci_prompt(
        ci_dir,
        "inv_aaaa",
        '[M1] artifact=bridge_memos/bridge_0.json\n{"unresolved_questions": ["q1"]}\n[/M1]\n',
    )
    result = _result_by_id(run_checks_a(tmp_path), "PC-06")
    assert result["passed"] is True


def test_pc06_fail_truncated_and_forbidden(tmp_path: Path):
    ci_dir = _stage(tmp_path, "controlled_investigation")
    _write_ci_prompt(
        ci_dir,
        "inv_aaaa",
        '[M1] artifact=bridge_memos/bridge_0.json\n{"unresolved_questions": ["q1",\n[/M1]\n',
    )
    result = _result_by_id(run_checks_a(tmp_path), "PC-06")
    assert result["passed"] is False
    assert "JSON 不闭合" in result["detail"]


def test_pc06_fail_forbidden_stance_field(tmp_path: Path):
    ci_dir = _stage(tmp_path, "controlled_investigation")
    _write_ci_prompt(
        ci_dir,
        "inv_aaaa",
        '[M1] artifact=bridge_memos/bridge_0.json\n{"dominant_side": "估值压缩风险", "action_implication": "不宜重仓"}\n[/M1]\n',
    )
    result = _result_by_id(run_checks_a(tmp_path), "PC-06")
    assert result["passed"] is False
    assert "立场/仓位字段" in result["detail"]
    assert "待 C6 装配点" in result["detail"]


def test_pc06_fail_event_side_artifact(tmp_path: Path):
    """拆洞（老板 2026-08-25）：调查员材料块引用事件侧 artifact 必须亮红灯。"""
    ci_dir = _stage(tmp_path, "controlled_investigation")
    _write_ci_prompt(
        ci_dir,
        "inv_aaaa",
        '[M1] artifact=cross_layer_questions.json\n{"questions": []}\n[/M1]\n',
    )
    result = _result_by_id(run_checks_a(tmp_path), "PC-06")
    assert result["passed"] is False
    assert "事件侧 artifact" in result["detail"]


# ──────────────────────────────────────────────────────────────────────────
# PC-07 事件字段恒空
# ──────────────────────────────────────────────────────────────────────────

def test_pc07_pass_empty_event_fields(tmp_path: Path):
    for station in ["bridge", "critic", "risk", "reviser", "final_adjudicator"]:
        payload = {"governance_input": {"key_event_refs": {}}} if station != "bridge" else {"layer_cards": []}
        _write_payload(_stage(tmp_path, station), payload)
    result = _result_by_id(run_checks_a(tmp_path), "PC-07")
    assert result["passed"] is True


def test_pc07_fail_nonempty_key_event_refs(tmp_path: Path):
    for station in ["bridge", "critic", "risk", "reviser", "final_adjudicator"]:
        payload = {"governance_input": {"key_event_refs": {}}} if station != "critic" else {"governance_input": {"key_event_refs": {"evt1": {}}}}
        _write_payload(_stage(tmp_path, station), payload)
    result = _result_by_id(run_checks_a(tmp_path), "PC-07")
    assert result["passed"] is False
    assert "非空" in result["detail"]


# ──────────────────────────────────────────────────────────────────────────
# PC-08 同名指标多值检测
# ──────────────────────────────────────────────────────────────────────────

def _write_pc08_layers(tmp_path: Path, l4_payload: Dict[str, Any]) -> None:
    for station in ["L1", "L2", "L3", "L4", "L5"]:
        payload = l4_payload if station == "L4" else {"layer_raw_data": {}}
        _write_payload(_stage(tmp_path, station), payload)
    cards_dir = tmp_path / "layer_cards"
    for station in ["L1", "L2", "L3", "L4", "L5"]:
        _write_json(cards_dir / f"{station}.json", {})


def test_pc08_pass_consistent_values(tmp_path: Path):
    _write_pc08_layers(tmp_path, {"layer_raw_data": {}})
    result = _result_by_id(run_checks_a(tmp_path), "PC-08")
    assert result["passed"] is True


def test_pc08_fail_pe_multi_value(tmp_path: Path):
    _write_pc08_layers(
        tmp_path,
        {
            "layer_raw_data": {
                "get_ndx_wind_valuation_snapshot": {"value": {"PE": 29.4}},
                "get_ndx_pe_and_earnings_yield": {"value": {"PE": 30.31}},
            }
        },
    )
    result = _result_by_id(run_checks_a(tmp_path), "PC-08")
    assert result["passed"] is False
    assert "pe" in result["detail"]
    assert "29.4" in result["detail"]
    assert "30.31" in result["detail"]


def test_pc08_fail_obv_level_multi_value(tmp_path: Path):
    """O10：同源同窗供给里 OBV 绝对水位不一致仍是矛盾供给（窗口再次分叉的看门狗）。"""
    _write_pc08_layers(
        tmp_path,
        {
            "layer_raw_data": {
                "get_l5_deterministic_snapshot": {"value": {"exact_technical_values": {"obv": 901260500}}},
                "get_qqq_technical_indicators": {"value": {"obv": 493790400}},
            }
        },
    )
    result = _result_by_id(run_checks_a(tmp_path), "PC-08")
    assert result["passed"] is False
    assert "obv" in result["detail"]


def test_pc08_fail_obv_20d_net_shares_multi_value(tmp_path: Path):
    """O10：20 日净增减股数是 OBV 的窗口无关语义出口，同名单值同样受 PC-08 对账。"""
    _write_pc08_layers(
        tmp_path,
        {
            "layer_raw_data": {
                "get_l5_deterministic_snapshot": {"value": {"exact_technical_values": {"obv_20d_net_shares": -60262100}}},
                "get_qqq_technical_indicators": {"value": {"obv_20d_net_shares": -60262101}},
            }
        },
    )
    result = _result_by_id(run_checks_a(tmp_path), "PC-08")
    assert result["passed"] is False
    assert "obv_20d_net_shares" in result["detail"]


# ──────────────────────────────────────────────────────────────────────────
# PC-09 约束/指令引用键存在性
# ──────────────────────────────────────────────────────────────────────────

def test_pc09_pass_no_dangling_keys(tmp_path: Path):
    l1 = _stage(tmp_path, "L1")
    _write_payload(l1, {"layer_raw_data": {}})
    _write_prompt(l1, "本提示词没有点名词。")
    result = _result_by_id(run_checks_a(tmp_path), "PC-09")
    assert result["passed"] is True


def test_pc09_fail_dangling_keys(tmp_path: Path):
    l1 = _stage(tmp_path, "L1")
    _write_payload(l1, {"layer_raw_data": {}})
    _write_prompt(
        l1,
        "所有 evidence_refs 必须来自本次输入的 raw_data。\n"
        "若输入出现 NO_DATA_AVAILABLE，只能当数据边界。\n",
    )
    result = _result_by_id(run_checks_a(tmp_path), "PC-09")
    assert result["passed"] is False
    assert "raw_data" in result["detail"]
    assert "NO_DATA_AVAILABLE" in result["detail"]


def test_pc09_manifest_analysis_required_is_not_a_dangling_key(tmp_path: Path):
    # analysis_required 是 prompt 内嵌"当前层指标清单"的数据键，不是对 payload 的
    # 键引用；提示词点名它不构成悬空引用。
    l1 = _stage(tmp_path, "L1")
    _write_payload(l1, {"layer_raw_data": {}})
    _write_prompt(l1, "对每一个 analysis_required=true 的指标输出一条分析。\n")
    result = _result_by_id(run_checks_a(tmp_path), "PC-09")
    assert result["passed"] is True


def test_pc09_runtime_input_and_few_shot_mentions_are_not_dangling(tmp_path: Path):
    # Runtime Input 头之后是 payload 转储与输出契约规格（数据区），4C few-shot 段是
    # 教学示例——两处出现的 raw_data / NO_DATA_AVAILABLE 都不是"约束点名"。
    l1 = _stage(tmp_path, "L1")
    _write_payload(l1, {"layer_raw_data": {}})
    _write_prompt(
        l1,
        "# L1 Analyst\n"
        "本提示词没有点名任何 payload 键。\n"
        "## Layer-Local 4C Few-Shot Examples\n"
        '{"core_facts": [{"metric": "m", "raw_data": {"x": 1}}]}\n'
        "## Runtime Input\n"
        '{"layer_raw_data": {"get_vix": {"status": "NO_DATA_AVAILABLE"}}}\n',
    )
    result = _result_by_id(run_checks_a(tmp_path), "PC-09")
    assert result["passed"] is True


def test_pc09_instruction_area_dangling_key_still_fails(tmp_path: Path):
    # 反例：Runtime Input 头之前的指令区真的点名悬空键，仍必须判红。
    l1 = _stage(tmp_path, "L1")
    _write_payload(l1, {"layer_raw_data": {}})
    _write_prompt(
        l1,
        "# L1 Analyst\n"
        "所有 evidence_refs 必须来自本次输入的 raw_data。\n"
        "## Runtime Input\n"
        '{"layer_raw_data": {}}\n',
    )
    result = _result_by_id(run_checks_a(tmp_path), "PC-09")
    assert result["passed"] is False
    assert "raw_data" in result["detail"]


# ──────────────────────────────────────────────────────────────────────────
# PC-10 事件站措辞矛盾共存
# ──────────────────────────────────────────────────────────────────────────

def test_pc10_pass_unified_semantic_wording(tmp_path: Path):
    station = _stage(tmp_path, "event_card_interpreter.event_test")
    _write_prompt(station, '弱来源或仅标题材料，用"据报道"或"该媒体称"这类限定语说清分寸。')
    result = _result_by_id(run_checks_a(tmp_path), "PC-10")
    assert result["passed"] is True
    assert "口径已统一" in result["detail"]


def test_pc10_fail_old_mandatory_wording(tmp_path: Path):
    station = _stage(tmp_path, "event_card_interpreter.event_test")
    _write_prompt(station, "弱来源必须以据报道或该媒体称开头。")
    result = _result_by_id(run_checks_a(tmp_path), "PC-10")
    assert result["passed"] is False
    assert "硬规定" in result["detail"]


def test_pc10_model_wording_in_data_area_is_not_our_wording(tmp_path: Path):
    # 2026-08-17 确认跑 r3 误伤实证：模型写在事件卡 limitations 里的旧 A 式措辞会随
    # payload 进入下游提示词的数据区——那是数据（模型产物），不是我们的措辞规定。
    # PC-10 只查指令区；指令区含统一语义、数据区有旧 A 措辞时必须判绿。
    station = _stage(tmp_path, "event_section_summary")
    _write_prompt(
        station,
        '弱来源或仅标题材料，用"据报道"或"该媒体称"这类限定语说清分寸。\n'
        "## Runtime Input\n"
        '{"cards": [{"limitations": ["不是官方披露，解读必须以“据报道”“该媒体称”限定。"]}]}\n',
    )
    result = _result_by_id(run_checks_a(tmp_path), "PC-10")
    assert result["passed"] is True


def test_pc10_fail_old_no_rules_meta(tmp_path: Path):
    station = _stage(tmp_path, "event_card_interpreter.event_test")
    _write_prompt(station, "措辞完全由你决定，没有固定说法要套。")
    result = _result_by_id(run_checks_a(tmp_path), "PC-10")
    assert result["passed"] is False
    assert "元话语" in result["detail"]


# ──────────────────────────────────────────────────────────────────────────
# 缺失 artifact + 整包结构
# ──────────────────────────────────────────────────────────────────────────

def test_missing_artifact_reports_false(tmp_path: Path):
    results = run_checks_a(tmp_path)
    pc01 = _result_by_id(results, "PC-01")
    assert pc01["passed"] is False
    assert "缺失 artifact" in pc01["detail"]


def test_run_checks_a_returns_ten_results(tmp_path: Path):
    results = run_checks_a(tmp_path)
    assert [r["check_id"] for r in results] == [
        "PC-01", "PC-02", "PC-03", "PC-04", "PC-05",
        "PC-06", "PC-07", "PC-08", "PC-09", "PC-10",
    ]
    for result in results:
        assert set(result.keys()) == {"check_id", "name", "passed", "detail", "evidence"}
        assert isinstance(result["passed"], bool)
