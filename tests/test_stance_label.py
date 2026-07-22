"""Q5: FinalAdjudication.stance_label — controlled short posture enum for the
report facade badge, replacing brittle keyword extraction from judgment prose.

LLM boundary tolerant normalization mirrors the W3 precedent
(_normalize_long_term_assessment_payload): strict core untouched, LLM-boundary
values get full/half-width + whitespace cleanup and synonym mapping, and
values that map to nothing are field-level fail-closed (cleared, not raised)
with a trace note in quality_gate.notes.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent_analysis.contracts import (  # noqa: E402
    ApprovalStatus,
    Confidence,
    FinalAdjudication,
    STANCE_LABEL_ENUM,
)

_ARCHIVE_PATH = (
    Path(__file__).resolve().parents[1]
    / "output" / "analysis" / "vnext" / "20260719_130534" / "final_adjudication.json"
)


def _final(**overrides):
    payload = {
        "approval_status": ApprovalStatus.APPROVED_WITH_RESERVATIONS,
        "final_stance": "测试姿态",
        "confidence": Confidence.MEDIUM,
        "must_preserve_risks": ["测试风险"],
        "adjudicator_notes": "测试说明",
    }
    payload.update(overrides)
    return FinalAdjudication(**payload)


def test_stance_label_enum_has_five_values():
    assert STANCE_LABEL_ENUM == ("防守等待", "偏防守", "中性观察", "偏进攻", "进攻")


def test_legal_value_passes_through_unchanged():
    for value in STANCE_LABEL_ENUM:
        final = _final(stance_label=value)
        assert final.stance_label == value
        # No spurious quality_gate note should be created for legal values.
        assert final.quality_gate is None or "stance_label" not in final.quality_gate.notes


def test_missing_field_defaults_to_none():
    final = _final()
    assert final.stance_label is None


def test_synonym_normalization_maps_to_canonical_enum():
    cases = {
        "防御等待": "防守等待",
        "防御": "偏防守",
        "防守": "偏防守",
        "观望": "中性观察",
        "中性": "中性观察",
        "看多": "偏进攻",
        "偏多": "偏进攻",
    }
    for raw, expected in cases.items():
        final = _final(stance_label=raw)
        assert final.stance_label == expected, f"{raw} should normalize to {expected}"


def test_full_width_and_whitespace_are_cleaned_before_matching():
    final = _final(stance_label="　偏进攻　")
    assert final.stance_label == "偏进攻"


def test_illegal_value_is_cleared_and_traced_without_failing_the_run():
    final = _final(stance_label="暴涨预警")
    assert final.stance_label is None
    assert final.quality_gate is not None
    assert "stance_label 非法值已清空（原文见 prompt_audit）" in final.quality_gate.notes


def test_illegal_value_appends_to_existing_quality_gate_notes():
    final = _final(
        stance_label="暴涨预警",
        quality_gate={
            "approval_status": "approved_with_reservations",
            "notes": "既有说明",
        },
    )
    assert final.stance_label is None
    assert "既有说明" in final.quality_gate.notes
    assert "stance_label 非法值已清空（原文见 prompt_audit）" in final.quality_gate.notes


def test_empty_string_normalizes_to_none_without_note():
    final = _final(stance_label="   ")
    assert final.stance_label is None
    # Blank input is not an "illegal value" — it must not trigger the
    # stance_label fail-closed trace note (unlike a genuinely bogus value).
    assert final.quality_gate is None or "stance_label" not in final.quality_gate.notes


def test_legacy_archive_without_stance_label_replays_cleanly():
    """Real archived run (predates this field) must still validate as-is."""
    if not _ARCHIVE_PATH.exists():
        return
    data = json.loads(_ARCHIVE_PATH.read_text(encoding="utf-8"))
    assert "stance_label" not in data
    model = FinalAdjudication.model_validate(data)
    assert model.stance_label is None


def test_serialization_roundtrip_preserves_stance_label():
    final = _final(stance_label="偏进攻")
    dumped = final.model_dump(mode="json")
    assert dumped["stance_label"] == "偏进攻"
    restored = FinalAdjudication.model_validate(dumped)
    assert restored.stance_label == "偏进攻"


def test_stance_label_cleared_when_it_contradicts_verdict_direction():
    """codex P2 修复：徽章不能和判决正文方向相反（"进攻"标签配全篇防守正文）。
    这只是粗粒度关键词校验，不是语义证明——目的是拦住最危险的两端矛盾，
    不对"中性观察"这类本就宽松的标签做二次揣测。"""
    final = _final(
        stance_label="进攻",
        final_stance="市场应全面防守，建议大幅减仓、保持谨慎。",
    )
    assert final.stance_label is None
    assert final.quality_gate is not None
    assert "与判决正文方向冲突" in final.quality_gate.notes

    final2 = _final(
        stance_label="防守等待",
        final_stance="风险出清，建议积极进攻、大举加仓。",
    )
    assert final2.stance_label is None
    assert "与判决正文方向冲突" in final2.quality_gate.notes


def test_stance_label_kept_when_direction_matches_or_is_neutral():
    """方向一致或没有强方向词时，正常枚举值不应被误伤。"""
    final = _final(stance_label="防守等待", final_stance="市场应防守等待，回避风险。")
    assert final.stance_label == "防守等待"

    final2 = _final(stance_label="偏进攻", final_stance="盈利超预期，可考虑加仓。")
    assert final2.stance_label == "偏进攻"

    # 中性观察不做方向二次校验，即使正文含防守/进攻词也不清空。
    final3 = _final(
        stance_label="中性观察",
        final_stance="多空因素交织，防守与进攻信号并存。",
    )
    assert final3.stance_label == "中性观察"


def test_stance_direction_check_understands_common_negations():
    final = _final(
        stance_label="进攻",
        final_stance="市场应全面防守，不宜加仓，保持谨慎。",
    )
    assert final.stance_label is None
    assert "与判决正文方向冲突" in final.quality_gate.notes

    final2 = _final(
        stance_label="防守等待",
        final_stance="风险出清，可以加仓，而非继续防守。",
    )
    assert final2.stance_label is None
    assert "与判决正文方向冲突" in final2.quality_gate.notes


def test_prompt_requires_stance_label_enum_and_direction_consistency():
    prompt = (
        Path(__file__).resolve().parents[1]
        / "src" / "agent_analysis" / "prompts" / "final_adjudicator.md"
    ).read_text(encoding="utf-8")
    assert "stance_label" in prompt
    for value in STANCE_LABEL_ENUM:
        assert value in prompt
    assert "与 `final_stance` 的方向一致" in prompt
