import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent_analysis.vnext_reporter import VNextReportGenerator


def _feedback_bridge(label: str):
    return {
        "bridge_type": "feedback_bridge_v2",
        "implication_for_ndx": label,
        "typed_conflicts": [],
        "resonance_chains": [],
        "transmission_paths": [],
        "conflicts": [],
        "cross_layer_claims": [],
    }


def test_conflicts_section_hides_stub_feedback_and_keeps_real_feedback():
    reporter = VNextReportGenerator()
    bridge = _feedback_bridge("feedback result")

    stub_html = reporter._conflicts_section(
        {
            "bridges": [bridge],
            "investigation_reports": [
                {"is_deterministic_stub": True},
                {"is_deterministic_stub": True},
            ],
        }
    )
    real_html = reporter._conflicts_section(
        {
            "bridges": [bridge],
            "investigation_reports": [
                {"is_deterministic_stub": True},
                {"is_deterministic_stub": False},
            ],
        }
    )

    assert "反馈复核（第二轮）" not in stub_html
    assert "feedback result" not in stub_html
    assert "反馈复核（第二轮）" in real_html
    assert "feedback result" in real_html


def test_event_mechanism_report_brief_renders_facts_only():
    reporter = VNextReportGenerator()
    mechanism = {
        "headline_judgment": {"title": "旧机器判断", "plain_text": "旧机器总评"},
        "delivery_to_integrated_report": {
            "one_sentence": "旧机器交付句",
            "watchlist": ["继续追踪官方披露"],
        },
        "mainlines": [
            {
                "title": "旧机器主线",
                "plain_summary": "旧机器主线摘要",
                "can_say": "固定可以说模板",
                "cannot_say": "固定不能说模板",
                "news_card_ids": ["news:abc"],
            }
        ],
        "news_cards": [
            {
                "news_id": "news:abc",
                "title": "美光财测发布",
                "source_name": "Wind Financial News",
                "published_at": "2026-06-25",
                "raw_text_excerpt": "股价跌近1。随后公司发布正式财测。",
                "one_line_summary": "机器摘要",
                "ai_analysis": "如果美光财测确实上修，机器作出解释。",
                "needs_data_confirmation": ["机器待确认项"],
            }
        ],
        "cross_layer_questions": [
            {"direction": "event_to_data", "question": "新闻事件给数据层出的题"}
        ],
    }
    artifacts = {
        "news_event_ledger": {
            "events": [
                {
                    "event_id": "event:abc",
                    "title": "美光财测发布",
                    "source_name": "Wind Financial News",
                    "source_tier": "reliable_mainstream_report",
                }
            ]
        }
    }

    html = reporter._event_mechanism_report_section(mechanism, artifacts)

    for expected in (
        "本区当前只提供事实底账；事件解读功能重建中，重建前不提供机器分析。",
        "美光财测发布",
        "Wind Financial News",
        "reliable_mainstream_report",
        "2026-06-25",
        "股价跌近1。随后公司发布正式财测",
        "新闻事件给数据层出的题",
        "继续追踪官方披露",
    ):
        assert expected in html
    for removed in (
        "如果美光财测确实上修",
        "机器摘要",
        "旧机器总评",
        "旧机器主线摘要",
        "旧机器交付句",
        "固定可以说模板",
        "固定不能说模板",
        "展开 AI 分析",
    ):
        assert removed not in html


def test_event_fact_excerpt_uses_numeric_safe_120_character_limit():
    reporter = VNextReportGenerator()
    raw_excerpt = "股价跌近1。" + "甲" * 200
    mechanism = {
        "news_cards": [
            {
                "news_id": "news:long",
                "title": "长正文测试",
                "source_name": "Test Source",
                "source_tier": "official",
                "published_at": "2026-07-18",
                "raw_text_excerpt": raw_excerpt,
            }
        ]
    }

    html = reporter._event_mechanism_report_section(mechanism, {})
    expected = raw_excerpt[:120] + "…"

    assert expected in html
    assert raw_excerpt[:121] not in html


def test_event_layer_summary_fallback_remains_facts_only():
    reporter = VNextReportGenerator()
    artifacts = {
        "event_mechanism_report": {},
        "event_layer_summary": {
            "most_important_events": [{"minimum_fact": "旧 summary 机器判断"}],
            "most_important_claims": [{"claim_text": "旧 claim 机器判断"}],
            "strongest_counterevidence": ["旧反证机器判断"],
        },
        "news_event_ledger": {
            "events": [
                {
                    "event_id": "event:fallback",
                    "title": "官方日历事实",
                    "source_name": "Official Source",
                    "source_tier": "official",
                    "published_at": "2026-07-18",
                    "raw_text_excerpt": "官方发布一项日历安排。",
                }
            ]
        },
    }

    html = reporter._event_layer_summary_section(artifacts)

    assert "本区当前只提供事实底账；事件解读功能重建中，重建前不提供机器分析。" in html
    assert all(value in html for value in ("官方日历事实", "Official Source", "official", "2026-07-18"))
    assert "旧 summary 机器判断" not in html
    assert "旧 claim 机器判断" not in html
    assert "旧反证机器判断" not in html


def test_personal_policy_translation_is_three_row_checklist_without_amounts():
    reporter = VNextReportGenerator()
    profile = {
        "schema_version": "user_decision_profile_ips_v1",
        "net_worth_snapshot": {"approx_total_cny": 777777},
        "buckets": {"liquidity": {"floor_cny": 555555}},
    }
    html = reporter._personal_policy_translation(
        {
            "final_stance": "市场宜防御减仓",
            "invalidation_conditions": ["【转多】盈利预期上修", "【转空】信用利差扩大"],
        },
        profile,
    )

    assert "按你的政策书逐条机械对照（无模型参与）" in html
    assert html.count('class="policy-check-row"') == 3
    assert all(label in html for label in ("政策条款", "本轮判断", "对照结果"))
    assert ".policy-check-row" in html
    assert "grid-template-columns" in html
    assert "555555" not in html
    assert "777777" not in html
