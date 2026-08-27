"""T47 常设检查 B 包（PC-11 ~ PC-28）的合成用例。

全部用例在 tmp_path 里手工构造 run_dir 子集，不依赖 output/ 真实产物。
每个检查一条"该过"用例 + 一条"该红"用例；另加一个缺失 artifact 用例。
"""

from __future__ import annotations

import json
import os
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent_analysis.persistent_checks_b import _check_pc20, run_checks_b


# --------------------------------------------------------------------------
# 合成 run_dir 构造工具
# --------------------------------------------------------------------------

def _write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _layer_payload(
    *,
    raw_data: Dict[str, Any] | None = None,
    manual_overrides: Dict[str, Any] | None = None,
    data_summary: str = (
        "运行时点 2026-07-30，L1 本层 1/1 个指标成功。"
        "各指标实际数据日期以各自 data_quality.data_date / effective_date 为准："
        "早于运行时点属正常时点纪律（月度指标滞后发布等），不要求与运行时点同一天。"
    ),
    layer_facts: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "context_brief": {"generated_at": "2026-07-30T16:26:10Z", "data_summary": data_summary},
        "layer": "L1",
        "layer_facts": layer_facts if layer_facts is not None else {"core_signals": [], "state": "neutral", "key_metrics": []},
        "layer_raw_data": raw_data if raw_data is not None else {},
        "manual_overrides": manual_overrides if manual_overrides is not None else {"active": False, "date": "2026-07-15", "metrics": {}},
    }
    return payload


def _add_layer(run_dir: Path, layer: str, payload: Dict[str, Any]) -> None:
    _write_json(
        run_dir / "prompt_audit" / layer / "attempt_1.payload.json",
        {"stage_key": f"{layer.lower()}_analyst", "stage_name": layer.lower(), "attempt": 1, "payload": payload, "retry_feedback": ""},
    )


def _add_prompt(run_dir: Path, station: str, text: str) -> None:
    _write_text(run_dir / "prompt_audit" / station / "attempt_1.prompt.txt", text)


def _add_all_layers_minimal(run_dir: Path) -> None:
    """为 L1-L5 写最小有效 payload + prompt，避免"该过"用例被其他层缺失 artifact 误伤。"""
    for layer in ["L1", "L2", "L3", "L4", "L5"]:
        _add_layer(run_dir, layer, _layer_payload())
        _add_prompt(run_dir, layer, f"### IndicatorCanon for {layer}\n[]\n\n# {layer} Analyst\n")


def _metric(function_id: str, metric_name: str, **extra: Any) -> Dict[str, Any]:
    item: Dict[str, Any] = {
        "name": metric_name,
        "function_id": function_id,
        "metric_name": metric_name,
        "availability": "available",
        "data_quality": {
            "contract_version": "data_evidence_v1",
            "provider": "synthetic",
            "source_name": "synthetic",
            "source_tier": "official",
            "as_of_date": "2026-07-30",
            "effective_date": "2026-07-30",
            "data_date": "2026-07-30",
            "vintage_date": "not_available",
            "collected_at_utc": "2026-07-30T16:17:05Z",
            "availability": "available",
            "fallback_reason": "none",
            "fallback_chain": [],
            "license_note": "official_public",
            "coverage": {},
        },
        "error": None,
        "manual_override_used": False,
    }
    item.update(extra)
    return item


def _find(results: List[Dict[str, Any]], check_id: str) -> Dict[str, Any]:
    for item in results:
        if item["check_id"] == check_id:
            return item
    raise AssertionError(f"{check_id} not found in results")


# --------------------------------------------------------------------------
# PC-11 输出示例指标本层存在性
# --------------------------------------------------------------------------

def test_pc11_example_ids_in_layer_pass(tmp_path: Path) -> None:
    _add_all_layers_minimal(tmp_path)
    payload = _layer_payload(raw_data={"get_aaa": _metric("get_aaa", "AAA")})
    _add_layer(tmp_path, "L1", payload)
    _add_prompt(
        tmp_path,
        "L1",
        "### Example: get_aaa\nINPUT: {\"function_id\": \"get_aaa\"}\n\n"
        "### 结构示例\n{\n  \"indicator_analyses\": [\n    {\"function_id\": \"get_aaa\"}\n  ],\n"
        "  \"quality_self_check\": {\"covered_function_ids\": [\"get_aaa\"]}\n}\n",
    )
    result = _find(run_checks_b(tmp_path), "PC-11")
    assert result["passed"] is True


def test_pc11_example_id_from_other_layer_fails(tmp_path: Path) -> None:
    _add_all_layers_minimal(tmp_path)
    payload = _layer_payload(raw_data={"get_aaa": _metric("get_aaa", "AAA")})
    _add_layer(tmp_path, "L1", payload)
    _add_prompt(
        tmp_path,
        "L1",
        "### 结构示例\n{\n  \"indicator_analyses\": [\n    {\"function_id\": \"get_bbb\"}\n  ],\n"
        "  \"quality_self_check\": {\"covered_function_ids\": [\"get_bbb\"]}\n}\n",
    )
    result = _find(run_checks_b(tmp_path), "PC-11")
    assert result["passed"] is False
    assert "get_bbb" in result["detail"]


# --------------------------------------------------------------------------
# PC-12 manual_overrides 陈旧占位日期
# --------------------------------------------------------------------------

def test_pc12_fresh_override_pass(tmp_path: Path) -> None:
    _add_all_layers_minimal(tmp_path)
    payload = _layer_payload(manual_overrides={"active": False, "date": "2026-07-15", "metrics": {}})
    _add_layer(tmp_path, "L1", payload)
    result = _find(run_checks_b(tmp_path), "PC-12")
    assert result["passed"] is True


def test_pc12_2022_placeholder_fails(tmp_path: Path) -> None:
    _add_all_layers_minimal(tmp_path)
    payload = _layer_payload(manual_overrides={"active": False, "date": "2022-01-04", "metrics": {}})
    _add_layer(tmp_path, "L1", payload)
    result = _find(run_checks_b(tmp_path), "PC-12")
    assert result["passed"] is False
    assert "2022-01-04" in result["detail"]


# --------------------------------------------------------------------------
# PC-13 percentile 取值域混用
# --------------------------------------------------------------------------

def test_pc13_single_scale_pass(tmp_path: Path) -> None:
    _add_all_layers_minimal(tmp_path)
    payload = _layer_payload(raw_data={
        "get_aaa": _metric("get_aaa", "AAA", value={"relativity": {"percentile_10y": 0.52}}),
        "get_bbb": _metric("get_bbb", "BBB", value={"relativity": {"percentile_10y": 0.73}}),
    })
    _add_layer(tmp_path, "L1", payload)
    result = _find(run_checks_b(tmp_path), "PC-13")
    assert result["passed"] is True


def test_pc13_mixed_scale_without_declaration_fails(tmp_path: Path) -> None:
    _add_all_layers_minimal(tmp_path)
    payload = _layer_payload(raw_data={
        "get_aaa": _metric("get_aaa", "AAA", value={"relativity": {"percentile_10y": 0.52}}),
        "get_bbb": _metric("get_bbb", "BBB", value={"relativity": {"percentile_10y": 52.0}}),
    })
    _add_layer(tmp_path, "L1", payload)
    result = _find(run_checks_b(tmp_path), "PC-13")
    assert result["passed"] is False
    assert "0-1" in result["detail"] and "0-100" in result["detail"]


def test_pc13_mixed_scale_with_declaration_pass(tmp_path: Path) -> None:
    _add_all_layers_minimal(tmp_path)
    payload = _layer_payload(raw_data={
        "get_aaa": _metric("get_aaa", "AAA", value={"relativity": {"percentile_10y": 0.52, "percentile_scale": "0-1"}}),
        "get_bbb": _metric("get_bbb", "BBB", value={"relativity": {"percentile_10y": 52.0, "percentile_scale": "0-100"}}),
    })
    _add_layer(tmp_path, "L1", payload)
    result = _find(run_checks_b(tmp_path), "PC-13")
    assert result["passed"] is True


# --------------------------------------------------------------------------
# PC-14 context_brief 日期 vs 指标日期
# --------------------------------------------------------------------------

def test_pc14_same_day_different_timezone_pass(tmp_path: Path) -> None:
    _add_all_layers_minimal(tmp_path)
    payload = _layer_payload(raw_data={
        "get_aaa": _metric("get_aaa", "AAA", data_quality={"data_date": "2026-07-30T12:00:00+00:00"}),
    })
    _add_layer(tmp_path, "L1", payload)
    result = _find(run_checks_b(tmp_path), "PC-14")
    assert result["passed"] is True


def test_pc14_earlier_indicator_date_is_legitimate_lag(tmp_path: Path) -> None:
    # B8 新口径：月度指标等早于运行时点属正常时点纪律，不再判"跨日不一致"。
    _add_all_layers_minimal(tmp_path)
    payload = _layer_payload(raw_data={
        "get_aaa": _metric("get_aaa", "AAA", data_quality={"data_date": "2026-07-29"}),
    })
    _add_layer(tmp_path, "L1", payload)
    result = _find(run_checks_b(tmp_path), "PC-14")
    assert result["passed"] is True


def test_pc14_future_indicator_date_fails(tmp_path: Path) -> None:
    _add_all_layers_minimal(tmp_path)
    payload = _layer_payload(raw_data={
        "get_aaa": _metric("get_aaa", "AAA", data_quality={"data_date": "2026-07-31"}),
    })
    _add_layer(tmp_path, "L1", payload)
    result = _find(run_checks_b(tmp_path), "PC-14")
    assert result["passed"] is False
    assert "2026-07-31" in result["detail"]
    assert "未来数据泄漏" in result["detail"]


def test_pc14_missing_date_disclaimer_fails(tmp_path: Path) -> None:
    _add_all_layers_minimal(tmp_path)
    payload = _layer_payload(
        data_summary="运行时点 2026-07-30，L1 本层 1/1 个指标成功。",
        raw_data={"get_aaa": _metric("get_aaa", "AAA", data_quality={"data_date": "2026-07-30"})},
    )
    _add_layer(tmp_path, "L1", payload)
    result = _find(run_checks_b(tmp_path), "PC-14")
    assert result["passed"] is False
    assert "未声明" in result["detail"]


# --------------------------------------------------------------------------
# PC-15 high_severity 容器 severity
# --------------------------------------------------------------------------

def test_pc15_high_medium_severity_pass(tmp_path: Path) -> None:
    _write_json(tmp_path / "synthesis_packet.json", {
        "high_severity_conflicts": [
            {"conflict_id": "c1", "severity": "high"},
            {"conflict_id": "c2", "severity": "medium"},
        ],
        "high_severity_typed_conflicts": [
            {"conflict_id": "t1", "severity": "high"},
        ],
    })
    result = _find(run_checks_b(tmp_path), "PC-15")
    assert result["passed"] is True


def test_pc15_missing_severity_fails(tmp_path: Path) -> None:
    _write_json(tmp_path / "synthesis_packet.json", {
        "high_severity_conflicts": [
            {"conflict_id": "c1", "severity": "high"},
            {"conflict_id": "c2"},
        ],
    })
    result = _find(run_checks_b(tmp_path), "PC-15")
    assert result["passed"] is False
    assert "severity 缺失" in result["detail"]


def test_pc15_low_severity_fails(tmp_path: Path) -> None:
    _write_json(tmp_path / "synthesis_packet.json", {
        "high_severity_conflicts": [
            {"conflict_id": "c1", "severity": "low"},
        ],
    })
    result = _find(run_checks_b(tmp_path), "PC-15")
    assert result["passed"] is False
    assert "low" in result["detail"]


# --------------------------------------------------------------------------
# PC-16 他站产物键/禁用标记进输入
# --------------------------------------------------------------------------

def test_pc16_clean_payload_pass(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "prompt_audit" / "critic" / "attempt_1.payload.json",
        {"stage_key": "critic", "attempt": 1, "payload": {"governance_input": {"thesis_main": "正文", "key_evidence_refs": []}}, "retry_feedback": ""},
    )
    result = _find(run_checks_b(tmp_path), "PC-16")
    assert result["passed"] is True


def test_pc16_counter_forbidden_context_refs_is_legal(tmp_path: Path) -> None:
    """counter_thesis 的 forbidden_context_refs 是独立性边界，不是 B12 病。"""
    _write_json(
        tmp_path / "prompt_audit" / "counter_thesis" / "attempt_1.payload.json",
        {
            "stage_key": "counter_thesis",
            "attempt": 1,
            "payload": {
                "synthesis_packet_without_self_reference": {
                    "forbidden_context_refs": ["thesis_draft.json", "analysis_revised.json", "final_adjudication.json"]
                }
            },
            "retry_feedback": "",
        },
    )
    result = _find(run_checks_b(tmp_path), "PC-16")
    assert result["passed"] is True


def test_pc16_forbidden_as_core_ref_marker_fails(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "prompt_audit" / "final_adjudicator" / "attempt_1.payload.json",
        {
            "stage_key": "final_adjudicator",
            "attempt": 1,
            "payload": {
                "governance_input": {
                    "pricing_expectation_ledger": {
                        "artifact_ref": "expectation_vs_realized.json",
                        "usage_rule": "pricing_narrative_support_only; forbidden_as_core_ref",
                        "status": "audit_only_effective_date_mismatch",
                    }
                }
            },
            "retry_feedback": "",
        },
    )
    result = _find(run_checks_b(tmp_path), "PC-16")
    assert result["passed"] is False
    assert "forbidden_as_core_ref" in result["detail"]


def test_pc16_downstream_artifact_key_fails(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "prompt_audit" / "critic" / "attempt_1.payload.json",
        {"stage_key": "critic", "attempt": 1, "payload": {"thesis_draft": {"非空": True}}, "retry_feedback": ""},
    )
    result = _find(run_checks_b(tmp_path), "PC-16")
    assert result["passed"] is False
    assert "thesis_draft" in result["detail"]


# --------------------------------------------------------------------------
# PC-17 bridge 冲突矩阵行完整性
# --------------------------------------------------------------------------

def _bridge_prompt(rows: List[str]) -> str:
    lines = ["检查冲突矩阵 A-M：", "", "| ID | 冲突 | 你的检查 |", "|----|------|---------|"]
    for row in rows:
        lines.append(f"| {row} | 冲突 {row} | 是否触发？ |")
    return "\n".join(lines)


def test_pc17_full_matrix_pass(tmp_path: Path) -> None:
    _add_prompt(tmp_path, "bridge", _bridge_prompt(list("ABCDEFGHIJKLM")))
    result = _find(run_checks_b(tmp_path), "PC-17")
    assert result["passed"] is True


def test_pc17_partial_matrix_fails(tmp_path: Path) -> None:
    _add_prompt(tmp_path, "bridge", _bridge_prompt(["A", "B", "C", "K"]))
    result = _find(run_checks_b(tmp_path), "PC-17")
    assert result["passed"] is False
    assert "D" in result["detail"]


# --------------------------------------------------------------------------
# PC-18 L4 数据陈旧 + 回购逐字重复行
# --------------------------------------------------------------------------

def _l4_buyback_payload(per_company: Dict[str, Any], raw_series: Dict[str, Any]) -> Dict[str, Any]:
    return _layer_payload(raw_data={
        "get_m7_buyback_flow": _metric(
            "get_m7_buyback_flow",
            "M7 Actual Buyback Flow",
            value={
                "as_of_date": "2026-07-31",
                "per_company": per_company,
                "raw_quarterly_series": raw_series,
            },
        ),
    })


def test_pc18_fresh_and_unique_rows_pass(tmp_path: Path) -> None:
    _write_json(tmp_path / "context_brief.json", {"data_summary": "数据日期 2026-07-30"})
    payload = _l4_buyback_payload(
        per_company={
            "MSFT": {"availability": "available", "latest_period_end": "2026-03-31", "quarters": []},
        },
        raw_series={
            "MSFT": [
                {"calendar_quarter": "2026Q1", "period_end": "2026-03-31", "value_usd_bn": 4.627},
                {"calendar_quarter": "2025Q4", "period_end": "2025-12-31", "value_usd_bn": 7.415},
            ],
        },
    )
    _add_layer(tmp_path, "L4", payload)
    result = _find(run_checks_b(tmp_path), "PC-18")
    assert result["passed"] is True


def test_pc18_stale_amzn_and_duplicate_rows_fail(tmp_path: Path) -> None:
    _write_json(tmp_path / "context_brief.json", {"data_summary": "数据日期 2026-07-30"})
    dup_row = {"calendar_quarter": "2026Q1", "period_end": "2026-03-31", "value_usd_bn": 4.627}
    payload = _l4_buyback_payload(
        per_company={
            "AMZN": {"availability": "available", "latest_period_end": "2024-12-31", "quarters": []},
        },
        raw_series={
            "MSFT": [dict(dup_row), dict(dup_row)],
        },
    )
    _add_layer(tmp_path, "L4", payload)
    result = _find(run_checks_b(tmp_path), "PC-18")
    assert result["passed"] is False
    assert "AMZN" in result["detail"]
    assert "逐字重复行" in result["detail"]


# --------------------------------------------------------------------------
# PC-19 canon 名 vs 输入 metric_name
# --------------------------------------------------------------------------

def _canon_prompt(layer: str, entries: List[Dict[str, str]]) -> str:
    return f"### IndicatorCanon for {layer}\n" + json.dumps(entries, ensure_ascii=False) + "\n\n# {layer} Analyst\n"


def test_pc19_canon_name_matches_input_pass(tmp_path: Path) -> None:
    _add_all_layers_minimal(tmp_path)
    payload = _layer_payload(raw_data={"get_m2_yoy": _metric("get_m2_yoy", "M2 YoY")})
    _add_layer(tmp_path, "L1", payload)
    _add_prompt(tmp_path, "L1", _canon_prompt("L1", [{"function_id": "get_m2_yoy", "metric_name": "M2 YoY"}]))
    result = _find(run_checks_b(tmp_path), "PC-19")
    assert result["passed"] is True


def test_pc19_canon_name_mismatch_fails(tmp_path: Path) -> None:
    _add_all_layers_minimal(tmp_path)
    payload = _layer_payload(raw_data={"get_m2_yoy": _metric("get_m2_yoy", "M2 YoY Growth")})
    _add_layer(tmp_path, "L1", payload)
    _add_prompt(tmp_path, "L1", _canon_prompt("L1", [{"function_id": "get_m2_yoy", "metric_name": "M2 YoY"}]))
    result = _find(run_checks_b(tmp_path), "PC-19")
    assert result["passed"] is False
    assert "M2 YoY" in result["detail"] and "M2 YoY Growth" in result["detail"]


# --------------------------------------------------------------------------
# PC-20 已落地三件复核
# --------------------------------------------------------------------------

def _ess_payload(with_field: bool) -> Dict[str, Any]:
    cards = []
    for i in range(3):
        card = {"event_id": f"event_{i}", "citation": "x"}
        if with_field:
            card["needs_data_confirmation"] = []
        cards.append(card)
    return {
        "stage_key": "event_section_summary",
        "stage_name": "event_section_summary",
        "attempt": 1,
        "payload": {"effective_date": "2026-07-30", "event_cards": cards},
        "retry_feedback": "",
    }


def _repo_test_file(repo_root: Path, test_count: int) -> None:
    lines = ["import pytest\n"]
    for i in range(test_count):
        lines.append(f"def test_{i:02d}():\n    assert True\n")
    path = repo_root / "tests" / "test_context_spread.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def test_pc20_all_three_fixes_pass(tmp_path: Path) -> None:
    _write_json(tmp_path / "prompt_audit" / "event_section_summary" / "attempt_1.payload.json", _ess_payload(with_field=True))
    _write_json(
        tmp_path / "prompt_audit" / "L2" / "attempt_2.payload.json",
        {
            "stage_key": "l2_analyst",
            "attempt": 2,
            "payload": {"layer": "L2", "layer_raw_data": {}},
            "retry_feedback": "JSON 语法错误定位: Expecting ',' delimiter（提取出的 JSON 块内第 3 行第 5 列）。",
        },
    )
    repo = tmp_path / "repo"
    _repo_test_file(repo, 15)
    result = _check_pc20(tmp_path, repo)
    assert result["passed"] is True


def test_pc20_missing_field_bad_feedback_few_tests_fail(tmp_path: Path) -> None:
    _write_json(tmp_path / "prompt_audit" / "event_section_summary" / "attempt_1.payload.json", _ess_payload(with_field=False))
    _write_json(
        tmp_path / "prompt_audit" / "L2" / "attempt_2.payload.json",
        {
            "stage_key": "l2_analyst",
            "attempt": 2,
            "payload": {"layer": "L2", "layer_raw_data": {}},
            "retry_feedback": "请检查最后未闭合的数组、对象或字符串。",
        },
    )
    repo = tmp_path / "repo"
    _repo_test_file(repo, 3)
    result = _check_pc20(tmp_path, repo)
    assert result["passed"] is False
    assert "needs_data_confirmation" in result["detail"]
    assert "无行/列、JSONDecodeError、字段路径、validation error 或规则路径定位" in result["detail"]
    assert "< 15" in result["detail"]


def test_pc20_field_path_localization_passes(tmp_path: Path) -> None:
    # 契约/模式校验错误的真实定位是字段路径（形如 L1.get_vix.metric），
    # JSON 行/列号只有解析错误才有——字段路径定位必须算数。
    _write_json(tmp_path / "prompt_audit" / "event_section_summary" / "attempt_1.payload.json", _ess_payload(with_field=True))
    _write_json(
        tmp_path / "prompt_audit" / "L1" / "attempt_2.payload.json",
        {
            "stage_key": "l1_analyst",
            "attempt": 2,
            "payload": {"layer": "L1", "layer_raw_data": {}},
            "retry_feedback": "L1.get_vix.metric must equal input metric_name 'VIX Index'.",
        },
    )
    repo = tmp_path / "repo"
    _repo_test_file(repo, 15)
    result = _check_pc20(tmp_path, repo)
    assert result["passed"] is True


def test_pc20_pydantic_validation_error_localization_passes(tmp_path: Path) -> None:
    # pydantic 模式错误反馈含 "validation error" 字样，同样是真实错误定位。
    _write_json(tmp_path / "prompt_audit" / "event_section_summary" / "attempt_1.payload.json", _ess_payload(with_field=True))
    _write_json(
        tmp_path / "prompt_audit" / "L4" / "attempt_2.payload.json",
        {
            "stage_key": "l4_analyst",
            "attempt": 2,
            "payload": {"layer": "L4", "layer_raw_data": {}},
            "retry_feedback": "1 validation error for LayerOutput\ncore_facts.0.metric\n  Field required",
        },
    )
    repo = tmp_path / "repo"
    _repo_test_file(repo, 15)
    result = _check_pc20(tmp_path, repo)
    assert result["passed"] is True


def test_pc20_rule_path_localization_passes(tmp_path: Path) -> None:
    # 内容规则违例（禁句/数字锚定等）的真实定位是规则身份——统一发放的
    # "dotted.rule.path: 消息" 前缀必须算数（2026-08-17 确认跑实测：事件卡禁句、
    # ESS 事后归因、final 数字锚定四条反馈全是这种形态，缺它就误红）。
    _write_json(tmp_path / "prompt_audit" / "event_section_summary" / "attempt_1.payload.json", _ess_payload(with_field=True))
    _write_json(
        tmp_path / "prompt_audit" / "event_card_interpreter.event_x" / "attempt_2.payload.json",
        {
            "stage_key": "event_card_interpreter",
            "attempt": 2,
            "payload": {},
            "retry_feedback": "event_card.direction_overreach: must not claim mandatory market direction",
        },
    )
    repo = tmp_path / "repo"
    _repo_test_file(repo, 15)
    result = _check_pc20(tmp_path, repo)
    assert result["passed"] is True


def test_pc20_feedback_without_any_localization_still_fails(tmp_path: Path) -> None:
    # 反例：完全没有定位信息的反馈仍必须判红。
    _write_json(tmp_path / "prompt_audit" / "event_section_summary" / "attempt_1.payload.json", _ess_payload(with_field=True))
    _write_json(
        tmp_path / "prompt_audit" / "L2" / "attempt_2.payload.json",
        {
            "stage_key": "l2_analyst",
            "attempt": 2,
            "payload": {"layer": "L2", "layer_raw_data": {}},
            "retry_feedback": "输出不符合契约要求，请重新生成。",
        },
    )
    repo = tmp_path / "repo"
    _repo_test_file(repo, 15)
    result = _check_pc20(tmp_path, repo)
    assert result["passed"] is False
    assert "无行/列、JSONDecodeError、字段路径、validation error 或规则路径定位" in result["detail"]


# --------------------------------------------------------------------------
# PC-21~26 补病检查（08-16）
# --------------------------------------------------------------------------

def _add_event_station_payload(run_dir: Path, station: str, body: Dict[str, Any]) -> None:
    _write_json(
        run_dir / "prompt_audit" / station / "attempt_1.payload.json",
        {"stage_key": "event", "stage_name": station, "attempt": 1, "payload": body, "retry_feedback": ""},
    )


def test_pc21_event_output_contract_removed_pass(tmp_path: Path) -> None:
    _add_event_station_payload(tmp_path, "event_card_interpreter.event_x", {"event_material": {}})
    _add_event_station_payload(tmp_path, "event_section_summary", {"event_cards": []})
    result = _find(run_checks_b(tmp_path), "PC-21")
    assert result["passed"] is True


def test_pc21_event_output_contract_leak_fails(tmp_path: Path) -> None:
    _add_event_station_payload(
        tmp_path, "event_card_interpreter.event_x",
        {"event_material": {}, "output_contract": {"fact_summary": "只写材料事实"}},
    )
    _add_event_station_payload(tmp_path, "event_section_summary", {"event_cards": []})
    result = _find(run_checks_b(tmp_path), "PC-21")
    assert result["passed"] is False
    assert "output_contract" in result["detail"]


def _layer_prompt_with_manifest(run_dir: Path, layer: str, manifest_json: str) -> None:
    _add_all_layers_minimal(run_dir)
    for each in ["L1", "L2", "L3", "L4", "L5"]:
        _add_prompt(
            run_dir,
            each,
            "### 当前层指标清单\n[]\n\n### 结构示例\n{\n}\n",
        )
    _add_prompt(
        run_dir,
        layer,
        f"### 当前层指标清单\n{manifest_json}\n\n### 结构示例\n{{\n}}\n",
    )


def test_pc22_manifest_without_data_quality_pass(tmp_path: Path) -> None:
    _layer_prompt_with_manifest(tmp_path, "L1", '[{"function_id": "get_aaa", "analysis_required": true}]')
    result = _find(run_checks_b(tmp_path), "PC-22")
    assert result["passed"] is True


def test_pc22_manifest_duplicate_data_quality_fails(tmp_path: Path) -> None:
    _layer_prompt_with_manifest(
        tmp_path,
        "L1",
        '[{"function_id": "get_aaa", "data_quality": {"provider": "synthetic"}}]',
    )
    result = _find(run_checks_b(tmp_path), "PC-22")
    assert result["passed"] is False
    assert "重复供给" in result["detail"]


def _write_conflict_containers(tmp_path: Path, hs: list, ht: list, retained: list) -> None:
    _write_json(tmp_path / "synthesis_packet.json", {
        "high_severity_conflicts": hs,
        "high_severity_typed_conflicts": ht,
    })
    _write_json(tmp_path / "thesis_draft.json", {"retained_conflicts": retained})


def test_pc23_conflict_container_sets_match_and_thesis_keeps_all(tmp_path: Path) -> None:
    _write_conflict_containers(
        tmp_path,
        [{"conflict_id": "c1"}, {"conflict_id": "c2"}],
        [{"conflict_id": "c1"}, {"conflict_id": "c2"}],
        [{"conflict_id": "c1"}, {"conflict_id": "c2"}],
    )
    result = _find(run_checks_b(tmp_path), "PC-23")
    assert result["passed"] is True


def test_pc23_conflict_container_set_mismatch_fails(tmp_path: Path) -> None:
    _write_conflict_containers(
        tmp_path,
        [{"conflict_id": "c1"}, {"conflict_id": "c2"}],
        [{"conflict_id": "c1"}],
        [{"conflict_id": "c1"}],
    )
    result = _find(run_checks_b(tmp_path), "PC-23")
    assert result["passed"] is False
    assert "typed_conflicts 缺" in result["detail"]
    assert "retained_conflicts 缺" in result["detail"]


def _holdings_metric(value: Dict[str, Any], coverage: Dict[str, Any]) -> Dict[str, Any]:
    return _metric(
        "get_qqq_top10_concentration",
        "QQQ Top10 Concentration",
        value=value,
        data_quality={"coverage": coverage, "source_tier": "official_provider"},
    )


def test_pc24_holdings_counts_and_lag_declared_pass(tmp_path: Path) -> None:
    _add_all_layers_minimal(tmp_path)
    payload = _layer_payload(raw_data={
        "get_qqq_top10_concentration": _holdings_metric(
            {
                "holdings_as_of": "2026-07-15",
                "holdings_lag_days": 15,
                "holdings_parsed": 105,
                "total_holdings": 108,
                "holdings_lag_note": "持仓锚滞后 15 天。",
            },
            {"holdings_reported": 105, "total_holdings": 108, "holdings_lag_days": 15},
        )
    })
    _add_layer(tmp_path, "L3", payload)
    result = _find(run_checks_b(tmp_path), "PC-24")
    assert result["passed"] is True


def test_pc24_holdings_bare_duplicate_counts_fail(tmp_path: Path) -> None:
    _add_all_layers_minimal(tmp_path)
    payload = _layer_payload(raw_data={
        "get_qqq_top10_concentration": _holdings_metric(
            {"holdings_as_of": "2026-07-15", "holdings_parsed": 105, "total_holdings": 108},
            {"holdings_reported": 105},
        )
    })
    _add_layer(tmp_path, "L3", payload)
    result = _find(run_checks_b(tmp_path), "PC-24")
    assert result["passed"] is False
    assert "holdings_lag_note" in result["detail"] or "holdings_lag_days" in result["detail"]


def test_pc25_supplier_lookback_pending_validation_fails(tmp_path: Path) -> None:
    _add_all_layers_minimal(tmp_path)
    payload = _layer_payload(raw_data={
        "get_ndx_earnings_revision_metrics": _metric(
            "get_ndx_earnings_revision_metrics",
            "NDX Earnings Revision Metrics",
            value={
                "slope_30d": {"material": "supplier_lookback", "verification_status": "pending_validation"},
                "slope_90d": {"material": "self_archive", "verification_status": "verified"},
            },
        )
    })
    _add_layer(tmp_path, "L4", payload)
    result = _find(run_checks_b(tmp_path), "PC-25")
    assert result["passed"] is False
    assert "slope_30d" in result["detail"]
    assert "slope_90d" not in result["detail"]
    # 08-17 30d 补验未通过 E3 同口径闸门，红灯文案须如实指向该事实
    assert "30d 补验 08-17 未通过" in result["detail"]


def test_pc26_yield_gap_core_allowed_still_fails(tmp_path: Path) -> None:
    _write_json(tmp_path / "evidence_registry.json", {
        "passports": {
            "L4.get_equity_risk_premium#level": {
                "authority_model": {
                    "field_authority": {
                        "usage": "core_allowed",
                        "reason": "可作为估值-利率张力的诊断性证据",
                    }
                }
            }
        }
    })
    result = _find(run_checks_b(tmp_path), "PC-26")
    assert result["passed"] is False
    assert "core_allowed" in result["detail"]


def test_pc26_yield_gap_diagnostic_supporting_only_passes(tmp_path: Path) -> None:
    _write_json(tmp_path / "evidence_registry.json", {
        "passports": {
            "L4.get_equity_risk_premium#level": {
                "authority_model": {
                    "field_authority": {
                        "usage": "supporting_only",
                        "reason": "诊断性辅助证据，不得独立支撑强结论。",
                    }
                }
            }
        }
    })
    result = _find(run_checks_b(tmp_path), "PC-26")
    assert result["passed"] is True


# --------------------------------------------------------------------------
# 缺失 artifact 用例
# --------------------------------------------------------------------------

def test_missing_artifact_reports_failed(tmp_path: Path) -> None:
    results = run_checks_b(tmp_path)
    pc15 = _find(results, "PC-15")
    assert pc15["passed"] is False
    assert "缺失 artifact" in pc15["detail"]


# --------------------------------------------------------------------------
# PC-27：已退役（2026-08-27 老板裁决）。原 O17 灯装反方向（challenged_by_data 实为
# "数据削弱事件叙事"），异议通道由 PC-28 正确承接；编号永不复用。此节只留退役
# 防复活断言，防止将来误把 PC-27 加回 B 包。
# --------------------------------------------------------------------------

def _ia_report(adjudication: Any) -> Dict[str, Any]:
    return {"schema_version": "integrated_synthesis_report_v1", "integrated_adjudication": adjudication}


def test_pc27_retired_not_in_b_pack(tmp_path: Path) -> None:
    """PC-27 不应出现在 B 包结果里；即便 IA 记录了 challenged_by_data 行（数据削弱
    事件叙事，正常情形）也不再触发任何 PC-27 亮灯——异议由 PC-28 独立判定。"""
    _write_json(tmp_path / "integrated_synthesis_report.json", _ia_report({
        "llm_adjudicated": True,
        "conflict_matrix": [
            {"card_id": "event_a", "relation": "not_yet_testable"},
            {"card_id": "event_c", "relation": "challenged_by_data"},
        ],
        "unexplained": [],
    }))
    results = run_checks_b(tmp_path)
    assert all(r["check_id"] != "PC-27" for r in results)
    assert any(r["check_id"] == "PC-28" for r in results)


# --------------------------------------------------------------------------
# PC-28：抗诉通道亮灯（T67/W4，2026-08-26 老板六件全批）
# --------------------------------------------------------------------------

def _ia_report_with_objections(objections: Any, verified_urls: List[str]) -> Dict[str, Any]:
    """带研究架 verified_cards 与 data_verdict_objections 的 IA 产物合成。"""
    patrols = {
        "patrols": [{"verified_cards": [{"source_url": u} for u in verified_urls]}],
    }
    return {
        "schema_version": "integrated_synthesis_report_v1",
        "event_research_patrols": patrols,
        "integrated_adjudication": {
            "llm_adjudicated": True,
            "data_verdict_objections": objections,
        },
    }


def test_pc28_lights_on_verified_material_objection(tmp_path: Path) -> None:
    """核实事实（source_ref 命中 verified source_url）+ 实质矛盾 → 亮灯。"""
    _write_json(tmp_path / "integrated_synthesis_report.json", _ia_report_with_objections(
        [{"source_ref": "https://example.com/fact", "claim": "外部核实事实与数据姿态相反",
          "contradicted_data": ["L1.get_10y_real_rate"], "materiality": "material"}],
        verified_urls=["https://example.com/fact"],
    ))
    result = _find(run_checks_b(tmp_path), "PC-28")
    assert result["passed"] is False
    assert "不是系统故障" in result["detail"]
    assert "抗诉 1 条" in result["detail"]


def test_pc28_passes_on_tangential_or_unverified(tmp_path: Path) -> None:
    """擦边（tangential）或未核实来源（event 卡 / 不在 verified 里）→ 不亮灯。"""
    _write_json(tmp_path / "integrated_synthesis_report.json", _ia_report_with_objections(
        [
            {"source_ref": "https://example.com/fact", "claim": "擦边",
             "contradicted_data": ["L1.get_10y_real_rate"], "materiality": "tangential"},
            {"source_ref": "event:abc", "claim": "事件卡挑战（弱来源）",
             "contradicted_data": ["L1.get_10y_real_rate"], "materiality": "material"},
        ],
        verified_urls=["https://example.com/fact"],
    ))
    result = _find(run_checks_b(tmp_path), "PC-28")
    assert result["passed"] is True
    assert "该抗诉才抗诉" in result["detail"]


def test_pc28_passes_when_no_objections(tmp_path: Path) -> None:
    _write_json(tmp_path / "integrated_synthesis_report.json", _ia_report_with_objections(
        [], verified_urls=["https://example.com/fact"],
    ))
    result = _find(run_checks_b(tmp_path), "PC-28")
    assert result["passed"] is True


# --------------------------------------------------------------------------
# PC-29：词表活化三账一致（T67/W7）
# --------------------------------------------------------------------------

def test_pc29_passes_when_mechanism_disabled(tmp_path: Path) -> None:
    """三本词表账全缺 = 机制未启用，跳过通过，不打扰。"""
    with _pc29_cwd(tmp_path):
        result = _find(run_checks_b(tmp_path), "PC-29")
        assert result["passed"] is True
        assert "未启用" in result["detail"]


@contextmanager
def _pc29_cwd(tmp_path: Path):
    """PC-29 按仓库根相对路径读全局词表账（output/state_ledger/），测试切到 tmp。"""
    old = os.getcwd()
    os.chdir(tmp_path)
    try:
        yield
    finally:
        os.chdir(old)


def test_pc29_catches_silent_override(tmp_path: Path) -> None:
    """overrides 有词但没有 adopt 留痕 → 静默增删嫌疑，亮红。"""
    with _pc29_cwd(tmp_path):
        raw = '{"record_type":"candidate","candidate_id":"tc_a","status":"candidate"}\n'
        target = tmp_path / "output/state_ledger/term_candidates.jsonl"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(raw, encoding="utf-8")
        overrides_path = tmp_path / "output/state_ledger/keyword_table_overrides.json"
        overrides_path.write_text(json.dumps({
            "schema_version": "keyword_table_overrides_v1",
            "terms": [{"term": "幽灵词", "use": "pool", "decided_by": "owner"}],
        }, ensure_ascii=False), encoding="utf-8")
        pc29s = [r for r in run_checks_b(tmp_path) if r["check_id"] == "PC-29"]
        assert len(pc29s) == 1
        assert pc29s[0]["passed"] is False
        assert "静默增删嫌疑" in pc29s[0]["detail"]


def test_pc29_passes_consistent_ledgers(tmp_path: Path) -> None:
    from event_research.term_activation import adopt_term
    with _pc29_cwd(tmp_path):
        cand_raw = ('{"record_type":"candidate","candidate_id":"tc_b","raw_text":"某重组公告缺席",'
                    '"source":"absence_signal","status":"candidate",'
                    '"proposed_at_utc":"2026-08-27T00:00:00+00:00"}\n')
        cand_path = tmp_path / "output/state_ledger/term_candidates.jsonl"
        cand_path.parent.mkdir(parents=True, exist_ok=True)
        cand_path.write_text(cand_raw, encoding="utf-8")
        adopt_term("tc_b", "重组公告", "body_fetch",
                   candidates_path=cand_path,
                   overrides_path=tmp_path / "output/state_ledger/keyword_table_overrides.json",
                   change_log_path=tmp_path / "output/state_ledger/keyword_change_log.jsonl")
        pc29s = [r for r in run_checks_b(tmp_path) if r["check_id"] == "PC-29"]
        assert pc29s[0]["passed"] is True
