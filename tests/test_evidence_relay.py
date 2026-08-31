# -*- coding: utf-8 -*-
"""T49 第二件「正文上链」验收测试（新增文件，不改任何既有断言）。

- 任务 1：正文摘录截断上限 2200 → 8000（RAW_TEXT_EXCERPT_LIMIT）
- 任务 2：事件卡落盘时注入 evidence_excerpt / raw_text_available（逐字一致；契约零改动）
- 任务 3：IA 压缩器 _compact_card_for_prompt 携带新字段（excerpt 截断到 500）
"""
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import news_event_ledger
from agent_analysis.contracts import (
    CompetingHypothesis,
    EventInterpretationCard,
    HypothesisCompetition,
)
from integrated_synthesis_report import IntegratedSynthesisReportBuilder
from agent_analysis.orchestrator import VNextOrchestrator

# 6000 字符正文：> 2200（旧上限）且 ≤ 8000（新上限）
LONG_BODY = "材料正文。" * 1000
assert len(LONG_BODY) > 2200
assert len(LONG_BODY) <= 8000


class FakeLLMEngine:
    def __init__(self, responses):
        self.responses = responses
        self.token_usage = {"total": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}

    def call_with_fallback(self, prompt, stage_name="", preferred_models=None):
        return self.responses[stage_name]

    def extract_json(self, text, stage):
        return json.loads(text)

    def get_token_report(self):
        return self.token_usage


class UniformEventCardFakeLLMEngine(FakeLLMEngine):
    def __init__(self, response):
        super().__init__({})
        self.response = response
        self.calls = []
        self.prompts = []

    def call_with_fallback(self, prompt, stage_name="", preferred_models=None):
        self.calls.append(stage_name)
        self.prompts.append(prompt)
        return self.response


def _event_card_response(event_id="event:abc", tier="official"):
    return json.dumps(
        {
            "event_id": event_id,
            "fact_summary": "材料称公司发布了更新。",
            "interpretation": "该事件可能改变折现率预期，但仍需数据确认。",
            "entities": ["NVDA"],
            "event_type": "company_news",
            "mechanism_hypothesis": {
                "financial_link": "discount_rate",
                "hypothesis": "该事件可能通过折现率渠道影响纳指100估值。",
            },
            "supports_hypotheses": ["hyp_rates"],
            "refutes_hypotheses": [],
            "limitations": ["事件材料不能证明指数必须涨跌。"],
            "needs_data_confirmation": ["正式数据是否同步确认"],
            "upgrade_candidate": False,
            "passport": {
                "source": "x",
                "tier": "official",
                "published_at": "p",
                "event_date": "d",
                "effective_date": "e",
            },
        },
        ensure_ascii=False,
    )


def _write_event_card_inputs(run_dir, events, news_card_ids):
    (run_dir / "news_event_ledger.json").write_text(
        json.dumps({"events": events}, ensure_ascii=False), encoding="utf-8"
    )
    (run_dir / "event_mechanism_report.json").write_text(
        json.dumps(
            {
                "mainlines": [
                    {
                        "mainline_id": "macro_rate_valuation_pressure",
                        "news_card_ids": news_card_ids,
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _competition():
    return HypothesisCompetition(
        hypotheses=[
            CompetingHypothesis(
                hypothesis_id="hyp_rates",
                hypothesis_text="利率约束仍是主线。",
                support_evidence_refs=["L1.rate"],
                diagnostic_evidence_refs=["L1.rate"],
                falsification_conditions=["利率回落"],
            )
        ]
    )


def _event(available=True, excerpt=LONG_BODY):
    return {
        "event_id": "event:abc",
        "title": "Company update",
        "source_name": "Mainstream Media",
        "source_tier": "reliable_mainstream_report",
        "event_type": "company_news",
        "published_at": "2026-07-18T09:00:00Z",
        "event_date": "2026-07-18",
        "symbols": ["NVDA"],
        "raw_text_available": available,
        "raw_text_excerpt": excerpt,
    }


# ---------------------------------------------------------------------------
# 任务 1：截断上限 2200 → 8000
# ---------------------------------------------------------------------------


def test_task1_excerpt_limit_constant_is_8000():
    assert news_event_ledger.RAW_TEXT_EXCERPT_LIMIT == 8000


def test_task1_to_dict_excerpt_exceeds_old_limit():
    event = news_event_ledger.NewsEvent(
        event_id="event:t1",
        dedupe_id="t1",
        source_id="s1",
        source_name="S",
        source_tier="official",
        authority_tier="official",
        event_type="policy_news",
        title="T",
        url="http://example.com/x",
        published_at="2026-07-18T09:00:00Z",
        relevance_tags=[],
        layers=[],
        symbols=[],
        confidence="medium",
        notes="",
        raw_text_available=True,
        raw_text=LONG_BODY,
    )
    excerpt = event.to_dict()["raw_text_excerpt"]
    # 落盘 excerpt 长度 > 2200（旧上限）
    assert len(excerpt) > 2200
    # 且不超过新上限，且是正文逐字前缀（_clean_text 只折叠空白+截断）
    assert len(excerpt) <= news_event_ledger.RAW_TEXT_EXCERPT_LIMIT
    assert excerpt == LONG_BODY[:news_event_ledger.RAW_TEXT_EXCERPT_LIMIT]


def test_task1_extract_readable_text_default_limit_keeps_long_body():
    body = news_event_ledger._extract_readable_text(LONG_BODY)
    assert len(body) > 2200
    assert body == LONG_BODY


# T68-W4：Yahoo 文章页会在侧边/模块里嵌一块 "Oops, something went wrong" 错误模块，
# 页面其余部分是完整正文（2026-08-31 实测）。否决守卫只应杀"纯错误页"，
# 不得把带真正文的文章页一并误杀。
OOPS_MODULE_WITH_ARTICLE = (
    "<html><body>"
    "<div class='error-module'>Oops, something went wrong</div>"
    "<div class='links'>Skip to navigation Skip to main content</div>"
    "<article><p>" + ("Broad-market exchange-traded funds were lower. " * 40) + "</p></article>"
    "</body></html>"
)

PURE_OOPS_ERROR_PAGE = (
    "<html><body>"
    "<div>Oops, something went wrong</div>"
    "<div>Skip to navigation</div>"
    "</body></html>"
)


def test_extract_readable_text_keeps_article_with_embedded_oops_module():
    body = news_event_ledger._extract_readable_text(OOPS_MODULE_WITH_ARTICLE)
    assert "Broad-market exchange-traded funds" in body


def test_extract_readable_text_still_vetoes_pure_oops_error_page():
    # 纯错误页（无实质正文）仍须判空——守卫防的是错误页进正文链，不是防这个词
    assert news_event_ledger._extract_readable_text(PURE_OOPS_ERROR_PAGE) == ""


# ---------------------------------------------------------------------------
# 任务 2：卡落盘注入证据字段（逐字一致；契约零改动）
# ---------------------------------------------------------------------------


def test_task2_injected_evidence_excerpt_verbatim_on_disk(tmp_path: Path):
    event = _event(available=True, excerpt=LONG_BODY)
    _write_event_card_inputs(tmp_path, [event], ["news:abc"])
    engine = UniformEventCardFakeLLMEngine(_event_card_response())
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=engine
    )
    artifact = orchestrator._build_event_interpretation_cards(
        effective_date="2026-07-18",
        feedback_messages=[],
        hypothesis_competition=_competition(),
    )

    # 契约零改动：内存 artifact 的卡仍能被 EventInterpretationCard 严格校验（无 extra 字段）
    assert "evidence_excerpt" not in artifact["cards"][0]
    EventInterpretationCard.model_validate(artifact["cards"][0])

    # 落盘（event_interpretation_cards.json）逐字带正文
    disk = json.loads((tmp_path / "event_interpretation_cards.json").read_text(encoding="utf-8"))
    card = disk["cards"][0]
    assert card["evidence_excerpt"] == LONG_BODY
    assert card["raw_text_available"] is True

    # per-card 落盘同样逐字带正文
    per = json.loads(
        (tmp_path / "event_interpretation_cards" / "event_abc.json").read_text(encoding="utf-8")
    )
    assert per["evidence_excerpt"] == LONG_BODY
    assert per["raw_text_available"] is True


def test_task2_title_only_event_gets_empty_evidence_excerpt(tmp_path: Path):
    event = _event(available=False, excerpt="")
    _write_event_card_inputs(tmp_path, [event], ["news:abc"])
    engine = UniformEventCardFakeLLMEngine(_event_card_response())
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=engine
    )
    artifact = orchestrator._build_event_interpretation_cards(
        effective_date="2026-07-18",
        feedback_messages=[],
        hypothesis_competition=_competition(),
    )
    assert len(artifact["cards"]) == 1
    disk = json.loads((tmp_path / "event_interpretation_cards.json").read_text(encoding="utf-8"))
    card = disk["cards"][0]
    # 空正文纪律：raw_text_available=false 时 evidence_excerpt 必须为空字符串
    assert card["evidence_excerpt"] == ""
    assert card["raw_text_available"] is False


def test_task2_excerpt_is_material_not_model_output(tmp_path: Path):
    # 防作弊点名②：注入必须来自源材料 raw_text_excerpt，而不是模型响应内容。
    # 模型响应（_event_card_response）里没有任何字段与正文相同，落盘 excerpt 只能来自事件底账。
    event = _event(available=True, excerpt="仅材料底账里的这一句正文。")
    _write_event_card_inputs(tmp_path, [event], ["news:abc"])
    engine = UniformEventCardFakeLLMEngine(_event_card_response())
    orchestrator = VNextOrchestrator(
        available_models=["fake"], output_dir=str(tmp_path), llm_engine=engine
    )
    orchestrator._build_event_interpretation_cards(
        effective_date="2026-07-18",
        feedback_messages=[],
        hypothesis_competition=_competition(),
    )
    disk = json.loads((tmp_path / "event_interpretation_cards.json").read_text(encoding="utf-8"))
    card = disk["cards"][0]
    assert card["evidence_excerpt"] == "仅材料底账里的这一句正文。"
    assert card["evidence_excerpt"] != card["fact_summary"]  # 不是 fact_summary 冒充


# ---------------------------------------------------------------------------
# 任务 3：IA 压缩器带新字段（excerpt 截断 500）
# ---------------------------------------------------------------------------


def test_task3_compact_card_carries_evidence_fields():
    long_excerpt = "长正文。" * 300  # 1200 字符 > 500
    card = {
        "event_id": "event:x",
        "fact_summary": "事实。",
        "interpretation": "解读。",
        "mechanism_hypothesis": {"financial_link": "earnings_path", "hypothesis": "假设。"},
        "supports_hypotheses": ["hyp_rates"],
        "refutes_hypotheses": [],
        "needs_data_confirmation": [],
        "limitations": ["仅标题。"],
        "passport": {
            "tier": "reliable_mainstream_report",
            "event_date": "2026-07-18",
            "published_at": "2026-07-18T09:00:00Z",
        },
        "evidence_excerpt": long_excerpt,
        "raw_text_available": True,
    }
    compact = IntegratedSynthesisReportBuilder()._compact_card_for_prompt(card)
    # IA prompt 负载里的卡带两个新字段；excerpt 截断到 500
    assert compact["raw_text_available"] is True
    assert compact["evidence_excerpt"] == long_excerpt[:500]
    assert len(compact["evidence_excerpt"]) == 500
    # 既有字段不被破坏
    assert compact["fact_summary"] == "事实。"
    assert compact["source_tier"] == "reliable_mainstream_report"


def test_task3_compact_card_absent_fields_default_safe():
    compact = IntegratedSynthesisReportBuilder()._compact_card_for_prompt({"event_id": "event:y"})
    assert compact["evidence_excerpt"] == ""
    assert compact["raw_text_available"] is False


def test_task3_prompt_payload_cards_are_compacted_with_fields():
    # 模拟 _llm_adjudication 的 payload 组装（integrated_synthesis_report.py:326 同款压缩）
    cards = [
        {
            "event_id": "event:z",
            "fact_summary": "事实。",
            "interpretation": "解读。",
            "passport": {"tier": "official", "event_date": "2026-07-18"},
            "evidence_excerpt": LONG_BODY,
            "raw_text_available": True,
        }
    ]
    builder = IntegratedSynthesisReportBuilder()
    compact_cards = [builder._compact_card_for_prompt(card) for card in cards]
    assert compact_cards[0]["evidence_excerpt"] == LONG_BODY[:500]
    assert compact_cards[0]["raw_text_available"] is True
