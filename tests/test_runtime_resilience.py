import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent_analysis.contracts import LayerCard
from agent_analysis.llm_engine import LLMEngine
from agent_analysis.orchestrator import VNextOrchestrator
import tools_L1


class _NoopEngine:
    def call_with_fallback(self, prompt, stage_name=""):
        return "{}"

    def extract_json(self, text, stage):
        return json.loads(text)

    def get_token_report(self):
        return {}


def test_extract_json_light_repairs_model_array_closing_typo():
    engine = LLMEngine(available_models=[])
    malformed = '{"cross_layer_implications": ["需L3验证广度是否确认"), "ok": true}'

    parsed = engine.extract_json(malformed, stage="l2")

    assert parsed == {"cross_layer_implications": ["需L3验证广度是否确认"], "ok": True}


def test_layer_validation_derives_quality_coverage_from_indicator_analyses(tmp_path):
    orchestrator = VNextOrchestrator(
        available_models=[],
        output_dir=str(tmp_path),
        llm_engine=_NoopEngine(),
    )
    card = LayerCard.model_validate(
        {
            "layer": "L2",
            "core_facts": [{"metric": "VIX", "value": 17.2}],
            "local_conclusion": "风险偏好中性。",
            "confidence": "medium",
            "indicator_analyses": [
                {
                    "function_id": "get_vix",
                    "metric": "VIX Index",
                    "current_reading": "17.2",
                    "narrative": "VIX 处于中性区间。",
                    "reasoning_process": "先看水平，再看均线位置，判断隐含波动并未显示恐慌。",
                    "evidence_refs": ["L2.get_vix"],
                    "confidence": "medium",
                }
            ],
            "layer_synthesis": "L2 以 VIX 为唯一有效输入时，只能判断波动率风险偏好。",
            "internal_conflict_analysis": "本层只有一个有效指标，无法形成多指标内部冲突分析。",
            "quality_self_check": {
                "coverage_complete": False,
                "covered_function_ids": [],
            },
        }
    )

    errors = orchestrator._validate_layer_card_v2(card, "L2", {"get_vix": "VIX Index"})

    assert errors == []
    assert card.quality_self_check.coverage_complete is True
    assert card.quality_self_check.covered_function_ids == ["get_vix"]


def test_vxn_vix_ratio_returns_missing_data_instead_of_raising(monkeypatch):
    monkeypatch.setattr(tools_L1, "get_vxn", lambda end_date=None: {"name": "VXN", "value": None})
    monkeypatch.setattr(
        tools_L1,
        "get_vix",
        lambda end_date=None: {"name": "VIX", "value": {"level": 17.19, "date": "2026-05-08"}},
    )

    result = tools_L1.get_vxn_vix_ratio(end_date="2026-05-09")

    assert result["value"] is None
    assert "VXN=None" in result["notes"]
