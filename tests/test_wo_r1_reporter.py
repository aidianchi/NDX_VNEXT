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
        "美光财测发布",
        "Wind Financial News",
        "可靠媒体转述",
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
        "事件解读功能重建中",
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

    assert "事件解读功能重建中" not in html
    assert all(value in html for value in ("官方日历事实", "Official Source", "官方源", "2026-07-18"))
    assert "旧 summary 机器判断" not in html
    assert "旧 claim 机器判断" not in html
    assert "旧反证机器判断" not in html


def test_event_mechanism_report_renders_full_interpretation_card_and_keeps_other_events_as_facts():
    reporter = VNextReportGenerator()
    mechanism = {
        "news_cards": [
            {
                "news_id": "news:with_card",
                "title": "有解读卡事件",
                "source_name": "Federal Reserve",
                "published_at": "2026-07-18",
                "raw_text_excerpt": "官方发布声明。",
            },
            {
                "news_id": "news:facts_only",
                "title": "仅事实事件",
                "source_name": "Other Source",
                "published_at": "2026-07-18",
                "raw_text_excerpt": "另一条事实。",
            },
        ]
    }
    artifacts = {
        "event_interpretation_cards": {
            "cards": [
                {
                    "event_id": "event:with_card",
                    "fact_summary": "官方发布声明。",
                    "interpretation": "该事件可能改变利率预期。",
                    "mechanism_hypothesis": {
                        "financial_link": "discount_rate",
                        "hypothesis": "该事件可能通过折现率渠道影响纳指100估值。",
                    },
                    "needs_data_confirmation": ["实际利率是否同步变化"],
                    "limitations": ["不能证明指数必须涨跌"],
                }
            ]
        }
    }

    html = reporter._event_mechanism_report_section(mechanism, artifacts)

    assert all(
        text in html
        for text in (
            "有解读卡事件",
            "事实摘要",
            "官方发布声明",
            "事件解读",
            "该事件可能改变利率预期",
            "机制假设",
            "该事件可能通过折现率渠道影响纳指100估值",
            "需要数据确认",
            "实际利率是否同步变化",
            "仅事实事件",
            "另一条事实",
        )
    )
    assert html.count('class="ev-detail"') == 1


def test_event_mechanism_report_prioritizes_generated_cards_within_display_budget():
    reporter = VNextReportGenerator()
    news_cards = []
    mainlines = []
    for line_index in range(4):
        ids = []
        for card_index in range(6):
            news_id = f"news:{line_index}_{card_index}"
            ids.append(news_id)
            news_cards.append(
                {
                    "news_id": news_id,
                    "title": f"事件 {line_index}-{card_index}",
                    "source_name": "Source",
                    "published_at": "2026-07-18",
                    "raw_text_excerpt": "事实。",
                }
            )
        mainlines.append({"mainline_id": f"line_{line_index}", "news_card_ids": ids})
    target_id = "event:3_5"

    html = reporter._event_mechanism_report_section(
        {"mainlines": mainlines, "news_cards": news_cards},
        {
            "event_interpretation_cards": {
                "cards": [
                    {
                        "event_id": target_id,
                        "fact_summary": "目标事实。",
                        "interpretation": "目标解读必须展示。",
                        "mechanism_hypothesis": {"hypothesis": "该事件可能通过盈利路径影响纳指100。"},
                        "needs_data_confirmation": ["盈利数据"],
                    }
                ]
            }
        },
    )

    assert "目标解读必须展示" in html
    assert html.count('class="ev-detail"') == 1


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
