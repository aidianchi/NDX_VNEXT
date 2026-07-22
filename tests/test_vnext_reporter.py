import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent_analysis.vnext_reporter import (
    BRIEF_SECTION_ORDER,
    DRAWER_TREND_WHITELIST,
    INDICATOR_CHARTS,
    REF_DIGEST_JS,
    REF_DIGEST_FIELDS,
    VNextReportGenerator,
    _drawer_reading_parts,
    _glossary_term,
    _label,
    _load_local_decision_profile,
    _render_invalidation_item,
    _slug,
)


def test_indicator_glossary_definitions_are_static_and_safe():
    html = _glossary_term('HY OAS')
    assert 'metric-glossary' in html
    assert '高收益债相对国债的信用利差' in html
    assert 'aria-describedby=' in html
    assert 'aria-hidden="true"' in html
    assert ' hidden' not in html
    assert _glossary_term('<script>') == '&lt;script&gt;'


def test_indicator_card_renders_keyboard_glossary_for_common_indicators():
    reporter = VNextReportGenerator()
    html = reporter._indicator_card(
        'L5',
        {'function_id': 'get_macd_qqq', 'metric': 'MACD', 'current_reading': 'MACD柱为正', 'normalized_state': 'bullish'},
        {'layers': {}, 'chart_time_series': {}},
    )
    assert 'metric-glossary' in html
    assert '移动平均收敛发散指标' in html
    assert 'tabindex="0"' in html


def test_glossary_tooltips_have_unique_ids_and_aria_hidden_sync():
    first = _glossary_term('MACD', unique_id='L5-get_macd_qqq')
    second = _glossary_term('MACD', unique_id='L5-get_macd_qqq-brief')
    assert 'id="metric-glossary-macd-l5-get-macd-qqq"' in first
    assert 'id="metric-glossary-macd-l5-get-macd-qqq-brief"' in second
    assert first.count('aria-hidden="true"') == 1
    js = VNextReportGenerator()._js()
    assert 'tooltip.setAttribute(\'aria-hidden\', String(!open))' in js
    nested = _glossary_term('MACD', as_button=False, unique_id='nested')
    assert 'role="button"' not in nested
    assert 'tabindex=' not in nested
    assert "owner.setAttribute('aria-describedby', tooltip.id)" in js
from agent_analysis.prompt_inspector import PromptInspectorGenerator


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_r2_brief_spine_and_layers_template_are_declared():
    from agent_analysis.vnext_reporter import TEMPLATE_DESCRIPTIONS, TEMPLATE_ORDER

    assert TEMPLATE_ORDER["brief"] == list(BRIEF_SECTION_ORDER)
    assert BRIEF_SECTION_ORDER == (
        "facade",
        "thesis",
        "stress",
        "world",
        "brief_integrated",
        "risks",
        "brief_layers",
        "brief_audit",
    )
    assert TEMPLATE_ORDER["layers"] == ["layers"]
    assert "layers" in TEMPLATE_DESCRIPTIONS


def test_r2_ref_digest_has_fixed_fields_and_hard_budgets(tmp_path: Path):
    source = tmp_path / "snapshot.json"
    _write_json(
        source,
        {
            "effective_date": "2026-07-15",
            "recompute_inputs": {
                "get_ndx_ndxe_ratio": {
                    "raw_series": [
                        {"date": f"2026-06-{index + 1:02d}", "value": index / 10}
                        for index in range(30)
                    ] + [{"date": "2026-07-16", "value": 99.0}]
                }
            },
        },
    )
    source_bytes = source.read_bytes()
    artifacts = {
        "analysis_packet": {
            "meta": {"data_date": "2026-07-15"},
            "raw_data": {
                "L3": {
                    "get_ndx_ndxe_ratio": {
                        "value": {"relativity": {"percentile_10y": 86.5}}
                    }
                }
            },
        },
        "source_snapshot": {
            "source_path": str(source),
            "source_sha256": __import__("hashlib").sha256(source_bytes).hexdigest(),
            "effective_date": "2026-07-15",
        },
        "layers": {
            "L3": {
                "indicator_analyses": [
                    {
                        "function_id": "get_ndx_ndxe_ratio",
                        "metric": "NDX/NDXE Ratio",
                        "current_reading": "当前 2.9，10 年分位 86.5%",
                        "canonical_question": "头部集中度是否正在松动？",
                        "misread_guards": ["不能单独证明牛市结束。"],
                        "falsifiers": ["等权指数持续走弱。"],
                    }
                ]
            }
        },
    }

    digest = VNextReportGenerator()._build_ref_digest(
        tmp_path,
        artifacts,
        Path("vnext_layers_unit.html"),
    )

    metric = digest["metrics"]["L3.get_ndx_ndxe_ratio"]
    assert set(metric) == set(REF_DIGEST_FIELDS)
    assert len(json.dumps(metric, ensure_ascii=False).encode("utf-8")) <= 1024
    assert len(json.dumps(digest, ensure_ascii=False).encode("utf-8")) <= 50 * 1024
    assert len(json.dumps(digest["trends"], ensure_ascii=False).encode("utf-8")) <= 12 * 1024
    assert len(digest["trends"]["L3.get_ndx_ndxe_ratio"]) <= 60
    assert all(point[0] <= "2026-07-15" for point in digest["trends"]["L3.get_ndx_ndxe_ratio"])
    assert metric["artifact_anchor"] == "vnext_layers_unit.html#get_ndx_ndxe_ratio"
    assert len(DRAWER_TREND_WHITELIST) <= 15


def test_r2_ref_digest_refuses_unverified_or_mismatched_snapshot(tmp_path: Path):
    source = tmp_path / "snapshot.json"
    _write_json(
        source,
        {
            "effective_date": "2026-07-18",
            "recompute_inputs": {
                "get_ndx_ndxe_ratio": {"raw_series": [{"date": "2026-07-18", "value": 1.0}]}
            },
        },
    )
    artifacts = {
        "analysis_packet": {"meta": {"data_date": "2026-07-15"}, "raw_data": {}},
        "source_snapshot": {
            "source_path": str(source),
            "source_sha256": "wrong-hash",
            "effective_date": "2026-07-18",
        },
        "layers": {
            "L3": {
                "indicator_analyses": [
                    {"function_id": "get_ndx_ndxe_ratio", "metric": "NDX/NDXE Ratio"}
                ]
            }
        },
    }

    digest = VNextReportGenerator()._build_ref_digest(tmp_path, artifacts, Path("layers.html"))

    assert digest["trends"] == {}


def test_r2_ref_digest_refuses_effective_date_mismatch(tmp_path: Path):
    source = tmp_path / "snapshot.json"
    _write_json(
        source,
        {"effective_date": "2026-07-18", "recompute_inputs": {"get_ndx_ndxe_ratio": {"raw_series": []}}},
    )
    artifacts = {
        "analysis_packet": {"meta": {"backtest_date": "2026-07-15", "data_date": "2026-07-15"}, "raw_data": {}},
        "source_snapshot": {
            "source_path": str(source),
            "source_sha256": __import__("hashlib").sha256(source.read_bytes()).hexdigest(),
            "effective_date": "2026-07-18",
        },
        "layers": {"L3": {"indicator_analyses": [{"function_id": "get_ndx_ndxe_ratio"}]}},
    }

    digest = VNextReportGenerator()._build_ref_digest(tmp_path, artifacts, Path("layers.html"))

    assert digest["trends"] == {}


def test_r2_ref_digest_budget_validator_fails_closed():
    reporter = VNextReportGenerator()
    oversize = {
        "metrics": {
            "L1.get_unit": {
                "metric": "x" * 2000,
                "layer": "L1",
                "display_value": "",
                "detail": "",
                "quantile": None,
                "answers": "",
                "cannot_prove": "",
                "falsifier": "",
                "artifact_anchor": "layers.html#get_unit",
            }
        },
        "trends": {},
    }

    with __import__("pytest").raises(ValueError, match="exceeds 1KB"):
        reporter._validate_ref_digest(oversize)


def test_r2_brief_metric_card_only_uses_real_quantile_gauge():
    reporter = VNextReportGenerator()
    with_quantile = reporter._brief_metric_card(
        "L3",
        {"function_id": "get_ndx_ndxe_ratio", "metric": "NDX/NDXE", "current_reading": "10 年分位 86.5%"},
        86.5,
    )
    low_danger = reporter._brief_metric_card(
        "L4",
        {"function_id": "get_damodaran_us_implied_erp", "metric": "ERP", "current_reading": "10 年分位 25%"},
        25.0,
    )
    neutral = reporter._brief_metric_card(
        "L1",
        {"function_id": "get_copper_gold_ratio", "metric": "铜金比", "current_reading": "10 年分位 44%"},
        44.0,
    )
    curve_neutral = reporter._brief_metric_card(
        "L1",
        {"function_id": "get_10y2y_spread_bp", "metric": "10Y-2Y", "current_reading": "10 年分位 51%"},
        51.0,
    )
    dual_tail_neutral = reporter._brief_metric_card(
        "L2",
        {"function_id": "get_hy_oas_bp", "metric": "HY OAS", "current_reading": "10 年分位 8%"},
        8.0,
    )
    without_quantile = reporter._brief_metric_card(
        "L3",
        {"function_id": "get_advance_decline_line", "metric": "腾落线", "current_reading": "402"},
        None,
    )

    assert 'class="gauge"' in with_quantile
    assert "zone hi" in with_quantile and "zone lo" not in with_quantile
    assert "zone lo" in low_danger and "zone hi" not in low_danger
    assert "transform:scaleX(-1)" in low_danger
    assert "zone neutral" in neutral and "zone hi" not in neutral and "zone lo" not in neutral
    assert "zone neutral" in curve_neutral
    assert "zone neutral" in dual_tail_neutral
    assert "spark" not in with_quantile
    assert 'class="gauge"' not in without_quantile
    assert "spark" not in without_quantile


def test_r2_stress_section_uses_r7_hypothesis_response():
    html = VNextReportGenerator()._brief_stress_section(
        {
            "hypothesis_competition": {
                "hypotheses": [
                    {
                        "hypothesis_id": "hyp_counter",
                        "hypothesis_text": "增长可以消化估值。",
                        "status": "candidate",
                        "support_evidence_refs": ["L4.get_m7_capex_cycle"],
                        "falsification_conditions": ["盈利没有兑现。"],
                    }
                ]
            },
            "thesis_draft": {
                "hypothesis_responses": [
                    {
                        "hypothesis_id": "hyp_counter",
                        "verdict": "absorb_partially",
                        "reasoning": "资本开支提供支撑，但盈利证据仍缺失。",
                        "evidence_refs": ["L4.get_m7_capex_cycle"],
                    }
                ]
            },
            "counter_thesis": {},
        }
    )

    assert "它的主张" in html
    assert "最强证据" in html
    assert "暂不采纳" in html
    assert "什么会让它赢" in html
    assert "资本开支提供支撑，但盈利证据仍缺失。" in html
    assert "盈利没有兑现。" in html


def test_r2_facade_keeps_publish_block_visible(tmp_path: Path):
    html = VNextReportGenerator()._brief_facade_section(
        tmp_path,
        {
            "final_adjudication": {"final_stance": "偏多", "confidence": "medium"},
            "analysis_packet": {"meta": {"data_date": "2026-07-15"}},
            "synthesis_packet": {"packet_meta": {}},
            "data_integrity_report": {"publish_status": "blocked", "blocked": True},
        },
    )

    assert "发布闸门未通过" in html
    assert "不能当作可发布结论" in html

    missing_gate = VNextReportGenerator()._brief_facade_section(
        tmp_path,
        {
            "final_adjudication": {"final_stance": "偏多", "confidence": "medium"},
            "analysis_packet": {"meta": {"data_date": "2026-07-15"}},
            "synthesis_packet": {"packet_meta": {}},
        },
    )
    contradictory_gate = VNextReportGenerator()._brief_facade_section(
        tmp_path,
        {
            "final_adjudication": {"final_stance": "偏多", "confidence": "medium"},
            "analysis_packet": {"meta": {"data_date": "2026-07-15"}},
            "synthesis_packet": {"packet_meta": {}},
            "data_integrity_report": {"publish_status": "publishable", "blocking_reasons": ["schema mismatch"]},
        },
    )
    assert "发布闸门未通过" in missing_gate
    assert "发布闸门未通过" in contradictory_gate


def test_modern_cleared_stance_label_does_not_fall_back_to_negation_blind_legacy_badge(tmp_path: Path):
    reporter = VNextReportGenerator()
    artifacts = {
        "final_adjudication": {
            "final_stance": "风险出清，可以加仓，而非继续防守。",
            "reasoned_verdict": "风险出清，可以加仓，而非继续防守。",
            "stance_label": None,
            "confidence": "medium",
        },
        "analysis_packet": {"meta": {"data_date": "2026-07-15"}},
        "synthesis_packet": {"packet_meta": {}},
        "data_integrity_report": {"publish_status": "publishable"},
    }
    html = reporter._brief_facade_section(tmp_path, artifacts)
    assert '<span class="badge pill">姿态' not in html

    legacy = dict(artifacts)
    legacy["final_adjudication"] = {
        "final_stance": "当前应防守等待。", "confidence": "medium",
    }
    legacy_html = reporter._brief_facade_section(tmp_path, legacy)
    assert '<span class="badge pill">姿态 <b>防守等待</b></span>' in legacy_html


def test_invalidation_item_direction_badges_and_legacy_text():
    assert '<span class="pill good">转多</span> 盈利预期上修' == _render_invalidation_item("【转多】盈利预期上修")
    assert '<span class="pill bad">转空</span> 信用利差扩大' == _render_invalidation_item("【转空】信用利差扩大")
    assert "【转多】" not in _render_invalidation_item("【转多】盈利预期上修")
    assert "实际利率回落" == _render_invalidation_item("实际利率回落")


def test_brief_hero_labels_primary_break_condition():
    reporter = VNextReportGenerator()
    html = reporter._hero(
        {
            "final_stance": "中性",
            "state_diagnosis": "等待确认。",
            "confidence": "medium",
            "invalidation_conditions": ["实际利率回落至 2.0% 以下"],
        },
        {},
        Path("run"),
        "brief",
        {},
    )
    assert "什么情况下我会改判：" in html
    assert "实际利率回落至 2.0% 以下" in html


def test_reader_exit_renames_run_comparison_and_explains_claim_items():
    reporter = VNextReportGenerator()
    html = reporter._reader_exit_section(
        {
            "final_adjudication": {
                "final_stance": "中性",
                "confidence": "medium",
                "price_reflection_map": [
                    {"reflected_state": "partially_reflected", "category": "估值", "rationale": "部分反映。"}
                ],
            },
            "golden_pit_checklist": {
                "entries": [
                    {
                        "discipline_side": "claim",
                        "current_status": "insufficient_evidence",
                        "condition": "盈利预期需要继续观察。",
                        "evidence_refs": [],
                    }
                ]
            },
        }
    )
    assert "和上次判断比，什么变了" in html
    assert "观察确认项" in html
    assert "这类条目不直接触发买卖，只是判断成立与否的观察哨。" in html
    assert "以下是推断而非事实——每条都附证据与反证，欢迎质疑。" in html


def test_risks_section_shows_upside_triggers_or_honest_placeholder():
    reporter = VNextReportGenerator()
    base = {
        "final_adjudication": {"invalidation_conditions": ["信用利差扩大"]},
        "risk_boundary_report": {},
    }
    html = reporter._risks_section(base)
    assert '<div class="flip"><span class="dir watch">观察</span><span>信用利差扩大</span></div>' in html
    assert html.count("信用利差扩大") == 1

    base["final_adjudication"]["invalidation_conditions"] = ["【转多】盈利预期上修并广度改善"]
    html = reporter._risks_section(base)
    assert '<div class="flip"><span class="dir bull">转多</span><span>盈利预期上修并广度改善</span></div>' in html
    assert html.count("盈利预期上修并广度改善") == 1


def test_risks_section_uses_plain_language_labels():
    reporter = VNextReportGenerator()
    html = reporter._risks_section(
        {
            "final_adjudication": {},
            "risk_boundary_report": {
                "boundary_status": {"valuation_compression": "warning"},
                "must_preserve_risks": ["valuation_compression"],
            },
        }
    )
    assert "临界观察" in html
    assert "不能忽视的风险" in html
    assert "边界状态" not in html
    assert "必须保留" not in html


def test_vnext_reporter_news_section_shows_event_data_links():
    reporter = VNextReportGenerator()

    html = reporter._news_section(
        {
            "news_event_ledger": {
                "events": [
                    {
                        "event_id": "event:fomc",
                        "title": "Federal Reserve issues FOMC statement",
                        "published_at": "Fri, 08 May 2026 18:00:00 GMT",
                        "source_tier": "official_macro",
                        "layers": ["L1", "L4"],
                        "symbols": [],
                        "notes": "Official RSS item; treat as catalyst/background only.",
                    }
                ],
                "source_errors": [],
            },
            "news_event_data_links": {
                "links": [
                    {
                        "event_id": "event:fomc",
                        "observations": [
                            {
                                "series_key": "QQQ_OHLCV",
                                "series_label": "QQQ",
                                "statement": "QQQ 在事件日前后 +/-5 天窗口内从 450 变为 468。",
                                "needs_bridge_review": True,
                            }
                        ],
                    }
                ]
            },
            "news_layer_analysis": {
                "aggregate_analysis": {
                    "market_state_zh": "综合看来，新闻背景更偏向利率和政策预期敏感。",
                    "equity_fragility_zh": "若新闻同时对应利率上行和波动率上升，股市脆弱性会增加。",
                    "rate_pressure_zh": "涉及美联储的数据会改变降息/加息预期。",
                    "oil_pressure_zh": "本次新闻连接器尚未接入油价序列。",
                    "dominant_pressure_channels": ["利率预期", "风险溢价上升"],
                },
                "event_summaries": [
                    {
                        "event_id": "event:fomc",
                        "summary_zh": "这是一条来自美联储的政策事件。",
                        "possible_equity_impact_zh": "可能通过利率预期影响股市。",
                        "pressure_channels": ["利率预期"],
                    }
                ],
                "source_boundary": "本新闻层只基于官方事件标题和市场序列观察生成。",
            },
        }
    )

    assert "新闻中文概要、股市影响与市场连接观察" in html
    assert "新闻层总分析" in html
    assert "可能对股市的影响" in html
    assert "附近市场序列观察" in html
    assert "QQQ 在事件日前后" in html
    assert "不是因果证明，也不是 evidence_ref" in html


def test_brief_hero_renders_reasoned_verdict_with_clickable_refs(tmp_path: Path):
    reporter = VNextReportGenerator()
    reporter._brief_ref_labels = {"L1.get_10y_real_rate": "L1·10Y Real Rate"}
    final = {
        "approval_status": "approved_with_reservations",
        "final_stance": "中性偏谨慎",
        "confidence": "medium",
        "reasoned_verdict": "实际利率仍构成压力 [ l1.get_10y_real_rate ]，但趋势尚未破坏。",
        "reader_final": {"one_liner": "中性偏谨慎"},
        "must_preserve_risks": ["估值压缩风险"],
    }
    html = reporter._hero(
        final,
        {"indicator_successful": 1, "indicator_total": 1, "data_date": "2026-07-15"},
        tmp_path,
        "brief",
        {"analysis_packet": {}, "data_integrity_report": {}},
    )

    assert "实际利率仍构成压力" in html
    assert 'class="ref-chip"' in html
    assert 'data-ref="L1.get_10y_real_rate"' in html
    assert "[ l1.get_10y_real_rate ]" not in html
    assert "canonical.split('#', 1)[0]" in reporter._js()


def test_reasoned_verdict_splits_real_multi_ref_incident():
    reporter = VNextReportGenerator()
    reporter._brief_ref_labels = {
        "L1.get_10y_real_rate": "L1·10Y Real Rate",
        "L4.get_ndx_wind_valuation_snapshot": "L4·NDX Wind Valuation",
    }
    html = reporter._reasoned_verdict_html(
        "安全边际极薄 [L1.get_10y_real_rate, L4.get_ndx_wind_valuation_snapshot#PE]。\n\n"
        "调查仍在继续。"
    )

    assert html.count('class="ref-chip" data-ref=') == 2
    assert 'data-ref="L1.get_10y_real_rate"' in html
    assert 'data-ref="L4.get_ndx_wind_valuation_snapshot#PE"' in html
    assert "L4·NDX Wind Valuation" in html
    assert 'data-ref="L1.get_10y_real_rate, L4' not in html
    assert html.count("<p>") == 2


def test_reasoned_verdict_mutes_pseudo_refs():
    reporter = VNextReportGenerator()
    reporter._brief_ref_labels = {"L1.get_10y_real_rate": "L1·10Y Real Rate"}
    html = reporter._reasoned_verdict_html("调查仍在继续 [investigation]，伪造层级 [L9.fake_ref]。")

    # investigation 伪 ref 以人读标签降级展示，不可点击；伪造层级保持原文降级。
    assert '<span class="ref-chip muted">受控调查</span>' in html
    assert '<span class="ref-chip muted">L9.fake_ref</span>' in html
    assert 'data-ref="investigation"' not in html


def test_brief_readers_surface_uses_editorial_layers_and_compact_drawer():
    reporter = VNextReportGenerator()
    artifacts = {
        "layers": {
            "L1": {
                "layer_synthesis": "实际利率仍是主约束。",
                "indicator_analyses": [
                    {"function_id": "get_10y_real_rate", "metric": "10Y Real Rate", "current_reading": "2.35%，10年分位99.3%"},
                    {"function_id": "get_net_liquidity_momentum", "metric": "Net Liquidity", "current_reading": "5986B美元，10年分位64.7%"},
                    {"function_id": "get_m2_yoy", "metric": "M2 YoY Growth", "current_reading": "同比5.58%"},
                ],
            }
        }
    }

    html = reporter._brief_layer_detail("L1", artifacts["layers"]["L1"], artifacts)

    assert 'class="layer-brief"' in html
    assert 'class="layer-detail"' not in html
    assert html.count('class="indicator-card dcard"') == 2
    # Q4（2026-07-20 用户拍板 A+C）：完整指标卡回到 brief 内，默认折叠在 layer-full 里，
    # 关键读数卡之外的完整卡不得出现在默认展开面上。
    assert 'class="fold layer-full"' in html
    assert html.count('class="indicator-card" data-evidence-ref=') == 3
    assert html.index('class="fold layer-full"') < html.index('data-evidence-ref=')
    assert "10年实际利率" in html
    assert "净流动性" in html
    assert "drawerLayerLabel" in REF_DIGEST_JS
    assert "item.display_value" in REF_DIGEST_JS
    assert "item.detail" in REF_DIGEST_JS
    assert _drawer_reading_parts("NO_DATA_AVAILABLE") == ("", "暂无可用数据。")
    assert _drawer_reading_parts("状态：tightening_priced") == ("", "状态：市场定价偏收紧")
    assert _drawer_reading_parts("净流动性5986.71B美元，10年分位64.7%") == ("净流动性5986.71B美元", "10年分位64.7%")
    assert _drawer_reading_parts("555,789,500，20日变化-26.58%") == ("", "555,789,500，20日变化-26.58%")
    assert _drawer_reading_parts("42.0（中性区间，未超卖）") == ("", "42.0（中性区间，未超卖）")
    assert _drawer_reading_parts("VWAP_20=717.73（价格695.33，在其下方-3.12%）") == ("", "VWAP_20=717.73（价格695.33，在其下方-3.12%）")


def test_world_section_renders_governed_summary_only_when_present():
    reporter = VNextReportGenerator()
    mechanism = {
        "news_cards": [
            {
                "news_id": "news:abc",
                "title": "样例事件",
                "source_name": "Federal Reserve",
                "published_at": "2026-07-18",
                "raw_text_excerpt": "官方发布声明。",
            }
        ],
        # 模板拼接句必须继续被拒绝冒充总结（R1 裁决）。
        "headline_judgment": {"plain_text": "今天最值得盯的是模板句"},
    }
    summary_artifacts = {
        "event_interpretation_cards": {
            "section_summary": {
                "summary_text": "据报道，本轮事件围绕利率与AI资本开支 [card:event_abc]。以上事件材料不构成主证据，判断以数据层为准。",
                "cited_event_ids": ["event_abc"],
            }
        }
    }

    with_summary = reporter._event_mechanism_report_section(mechanism, summary_artifacts)
    without_summary = reporter._event_mechanism_report_section(mechanism, {})

    assert 'class="prose event-summary"' in with_summary
    assert "事件卡·abc" in with_summary
    assert "以上事件材料不构成主证据" in with_summary
    assert "今天最值得盯的是" not in with_summary
    assert 'class="prose event-summary"' not in without_summary
    assert "今天最值得盯的是" not in without_summary


def test_brief_world_keeps_expectation_ledger_inside_its_section():
    reporter = VNextReportGenerator()
    html = reporter._brief_world_section(
        {
            "event_mechanism_report": {"news_cards": []},
            "expectation_vs_realized": {"status": "available"},
        }
    )

    assert html.count("<section") == html.count("</section>") == 1
    assert html.index('id="expectation-vs-realized"') < html.rindex("</section>")


def test_reader_exit_checklist_renders_compact_rows_with_shared_dedup():
    reporter = VNextReportGenerator()

    html = reporter._reader_exit_section(
        {
            "final_adjudication": {
                "final_stance": "中性",
                "confidence": "medium",
                "must_preserve_risks": ["风险边界"],
            },
            "golden_pit_checklist": {
                "current_state": "状态说明",
                "entries": [
                    {
                        "current_status": "met",
                        "condition": "这是一条很长的条件说明，用来确认普通证据卡不会被压进编号列。",
                        "falsification_conditions": ["共用失效条件", "独有失效条件 A"],
                        "evidence_refs": ["L1.get_net_liquidity_momentum"],
                    },
                    {
                        "current_status": "not_met",
                        "condition": "第二条纪律条件。",
                        "falsification_conditions": ["共用失效条件"],
                        "evidence_refs": ["L1.get_net_liquidity_momentum"],
                    },
                ],
            },
        }
    )
    css = reporter._css("slate_v2")

    # 条目渲染为紧凑清单，不再逐卡重复整包 refs/反证。
    assert 'class="pit-item"' in html
    assert "已满足" in html
    assert "未满足" in html
    # 上游整包写入的共用 refs / 反证只展示一次。
    assert html.count("get_net_liquidity_momentum") == 1
    assert "这批条件共用的证据与反证" in html
    assert html.count("共用失效条件") == 1
    assert "独有失效条件 A" in html
    assert ".pit-list" in css
    assert ".chain-card--plain" in css
    assert "@media (max-width: 720px)" in css
    assert "min-width: 0;" in css


def test_reader_exit_checklist_encodes_discipline_side_semantics():
    reporter = VNextReportGenerator()

    html = reporter._reader_exit_section(
        {
            "final_adjudication": {"final_stance": "中性", "confidence": "medium"},
            "golden_pit_checklist": {
                "current_state": "状态说明",
                "entries": [
                    {
                        "discipline_side": "buy",
                        "current_status": "met",
                        "condition": "买入触发条件已经出现，估值和情绪同时进入历史低位区间。",
                        "falsification_conditions": [],
                        "evidence_refs": [],
                    },
                    {
                        "discipline_side": "risk",
                        "current_status": "met",
                        "condition": "信用利差已经确认恶化，风险边界条件被触发。",
                        "falsification_conditions": [],
                        "evidence_refs": [],
                    },
                    {
                        "current_status": "met",
                        "condition": "这条历史遗留条目没有携带 discipline_side 字段。",
                        "falsification_conditions": [],
                        "evidence_refs": [],
                    },
                ],
            },
        }
    )

    # 拆出每条 <li class="pit-item">...</li>，逐条断言，避免不同条目互相干扰。
    items = re.findall(r'<li class="pit-item">.*?</li>', html, flags=re.S)
    assert len(items) == 3
    buy_item, risk_item, missing_item = items

    # buy 类条目 met -> good（绿色），这是唯一应当出现绿色徽章的场景。
    assert 'class="pill good"' in buy_item
    assert "side-chip side-buy" in buy_item
    assert "已满足" in buy_item

    # 语义修正核心：risk 类条目 met 绝不能渲染成 good（绿）；
    # 应为警示色（risk）且文案改写为"风险已触发"，不能用通用的"已满足"。
    assert "good" not in risk_item
    assert 'class="pill risk"' in risk_item
    assert "side-chip side-risk" in risk_item
    assert "风险已触发" in risk_item

    # discipline_side 缺失：中性兜底（不猜方向），不渲染类型 chip，文案维持现状。
    assert "side-chip" not in missing_item
    assert 'class="pill watch"' in missing_item
    assert "good" not in missing_item
    assert "已满足" in missing_item


def test_reader_exit_without_entries_keeps_empty_note():
    reporter = VNextReportGenerator()
    html = reporter._reader_exit_section(
        {
            "final_adjudication": {"final_stance": "中性", "confidence": "medium"},
            "golden_pit_checklist": {},
        }
    )
    assert "暂无黄金坑清单条目" in html


def test_reader_exit_checklist_does_not_call_partial_falsifiers_shared():
    reporter = VNextReportGenerator()

    html = reporter._reader_exit_section(
        {
            "final_adjudication": {"final_stance": "中性", "confidence": "medium"},
            "golden_pit_checklist": {
                "current_state": "状态说明",
                "entries": [
                    {
                        "current_status": "met",
                        "condition": "第一条条件。",
                        "falsification_conditions": ["两条命中的失效条件"],
                        "evidence_refs": [],
                    },
                    {
                        "current_status": "not_met",
                        "condition": "第二条条件。",
                        "falsification_conditions": ["两条命中的失效条件"],
                        "evidence_refs": [],
                    },
                    {
                        "current_status": "met",
                        "condition": "第三条条件。",
                        "falsification_conditions": ["第三条独有失效条件"],
                        "evidence_refs": [],
                    },
                ],
            },
        }
    )

    assert "这批条件共用的证据与反证" not in html
    assert html.count("两条命中的失效条件") == 2
    assert "第三条独有失效条件" in html


def test_memo_chartbook_omits_groups_without_chart_data_and_reports_gap():
    reporter = VNextReportGenerator()
    artifacts = {
        "final_adjudication": {
            "final_stance": "中性",
            "confidence": "medium",
            "principal_contradiction": {"summary": "估值与流动性矛盾。", "dominant_side": "流动性收紧"},
        },
        "layers": {
            "L2": {"local_conclusion": "信用与波动读数缺失。"},
            "L3": {"local_conclusion": "集中度高但广度改善。"},
        },
        "chart_time_series": {"series": {}},
    }
    html = reporter._memo_chartbook_section(artifacts)

    # 没有任何图组数据：不渲染死板块，不引用旧叙事，缺口写明。
    assert "再看最硬的约束" not in html
    assert "信用是确认还是警告" not in html
    assert "本轮缺图" in html
    assert "总量信用利差极低" not in html
    assert "等权补涨是好消息" not in html


def test_memo_chartbook_constraint_copy_comes_from_principal_contradiction():
    reporter = VNextReportGenerator()
    rows = [{"date": f"2026-0{month}-01", "value": 2.0 + month / 10} for month in range(1, 7)]
    artifacts = {
        "final_adjudication": {
            "final_stance": "中性",
            "confidence": "medium",
            "principal_contradiction": {"summary": "估值与流动性矛盾。", "dominant_side": "流动性收紧"},
        },
        "layers": {},
        "chart_time_series": {"series": {"US10Y_REAL": {"rows": rows}}},
    }
    html = reporter._memo_chartbook_section(artifacts)

    assert "再看最硬的约束" in html
    assert "估值与流动性矛盾" in html
    assert "当前占上风的一面" in html
    assert "本轮报告的核心矛盾不是单纯" not in html


def test_memo_chartbook_reports_market_state_gap_when_overview_cards_missing():
    reporter = VNextReportGenerator()
    rows = [{"date": f"2026-0{month}-01", "value": 2.0 + month / 10} for month in range(1, 7)]
    artifacts = {
        "final_adjudication": {
            "final_stance": "中性",
            "confidence": "medium",
            "principal_contradiction": {"summary": "估值与流动性矛盾。", "dominant_side": "流动性收紧"},
        },
        "layers": {},
        "chart_time_series": {"series": {"US10Y_REAL": {"rows": rows}}},
    }

    html = reporter._memo_chartbook_section(artifacts)

    assert "本轮缺图：Top10 权重 / 估值赔率；信用利差（HY OAS / CCC-BB）；NDX/NDXE 与集中度。" in html
    assert "再看最硬的约束" in html


def test_conflicts_section_deduplicates_identical_bridges():
    reporter = VNextReportGenerator()
    typed = [
        {
            "conflict_id": "L4_vs_L1",
            "severity": "high",
            "confidence": "medium",
            "description": "估值与流动性冲突。",
            "mechanism": "折现率上升。",
            "implication": "估值承压。",
            "involved_layers": ["L1", "L4"],
            "evidence_refs": ["L1.get_net_liquidity_momentum"],
            "falsifiers": ["流动性转正。"],
        }
    ]
    legacy = [
        {
            "conflict_type": "L4_vs_L1",
            "severity": "high",
            "description": "旧口径同一冲突。",
            "implication": "重复。",
        }
    ]
    bridge_base = {
        "bridge_type": "macro_valuation",
        "implication_for_ndx": "谨慎。",
        "typed_conflicts": typed,
        "resonance_chains": [],
        "transmission_paths": [],
        "conflicts": legacy,
        "cross_layer_claims": [{"claim": "首轮判断", "mechanism": "机制", "supporting_facts": []}],
    }
    bridge_v2 = dict(bridge_base)
    bridge_v2["bridge_type"] = "feedback_bridge_v2"
    bridge_v2["cross_layer_claims"] = []
    html = reporter._conflicts_section({"bridges": [bridge_base, bridge_v2]})

    # 第二轮与第一轮完全一致：折叠成跟进卡，不整段重复。
    assert html.count('data-typed-conflict="L4_vs_L1"') == 1
    assert "不重复展示" in html
    assert "反馈复核（第二轮）" in html
    # 旧口径冲突与 typed 冲突同 id 时不再第三次渲染。
    assert "旧口径同一冲突" not in html


def test_conflicts_section_renders_hypothesis_competition_and_counter_thesis():
    reporter = VNextReportGenerator()
    artifacts = {
        "bridges": [],
        "hypothesis_competition": {
            "leading_hypothesis_id": "hyp_a",
            "hypotheses": [
                {
                    "hypothesis_id": "hyp_a",
                    "hypothesis_text": "主线解释：估值压缩风险主导。",
                    "status": "leading",
                    "confidence": "medium",
                    "cannot_explain": ["信用数据缺失。"],
                    "adjudication_reason": "证据未触发改判。",
                },
                {
                    "hypothesis_id": "hyp_b",
                    "hypothesis_text": "挑战解释：流动性才是定价核心。",
                    "status": "candidate",
                    "confidence": "low",
                    "cannot_explain": ["无法解释高位维持。"],
                },
            ],
            "retained_disputes": ["信用利差数据何时可用？"],
        },
        "counter_thesis": {
            "principal_counterargument": "市场可能双重误判。",
            "cannot_establish": ["无法确定信用利差真实水平。"],
        },
    }
    html = reporter._conflicts_section(artifacts)

    assert "谁在竞争解释权" in html
    assert "主线解释：估值压缩风险主导。" in html
    assert "暂时领先" in html
    assert "候选挑战" in html
    assert "反方最强论证" in html
    assert "市场可能双重误判。" in html
    assert "还没吵完的争议" in html


def test_conflicts_section_leading_hypothesis_carries_caution_note():
    reporter = VNextReportGenerator()
    artifacts = {
        "bridges": [],
        "hypothesis_competition": {
            "leading_hypothesis_id": "hyp_a",
            "hypotheses": [
                {
                    "hypothesis_id": "hyp_a",
                    "hypothesis_text": "主线解释：估值压缩风险主导。",
                    "status": "leading",
                    "confidence": "medium",
                    "cannot_explain": ["信用数据缺失。"],
                },
                {
                    "hypothesis_id": "hyp_b",
                    "hypothesis_text": "挑战解释：流动性才是定价核心。",
                    "status": "candidate",
                    "confidence": "low",
                    "cannot_explain": ["无法解释高位维持。"],
                },
            ],
        },
    }

    html = reporter._conflicts_section(artifacts)

    assert html.count("领先仅表示当前证据权重，非确定结论。") == 1
    assert "hypothesis-card--leading" in html


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
            "state_diagnosis": "高风险但赔率可能改善。",
            "priced_narrative": "价格已反映部分坏消息。",
            "payoff_assessment": "高风险高赔率候选。",
            "time_horizon_views": [
                {
                    "horizon": "one_to_three_months",
                    "view": "赔率改善但趋势未确认。",
                    "action_implication": "战术仓分批。",
                    "evidence_refs": ["L4.get_ndx_pe_and_earnings_yield"],
                }
            ],
            "portfolio_actions": [
                {
                    "bucket": "tactical_position",
                    "action": "分批试探。",
                    "rationale": "等待确认有机会成本。",
                    "evidence_refs": ["L5.get_ta_indicators"],
                }
            ],
            "confirmation_cost": "等待全部确认可能错过主要反弹段。",
            "invalidation_conditions": ["信用继续恶化"],
            "reader_final": {
                "one_liner": "这不是低风险环境，但可能是高风险高赔率候选。",
                "three_reasons": [
                    "风险仍在。",
                    "估值已有压缩。",
                    "等待确认有机会成本。",
                ],
                "invalidation_summary": ["信用继续恶化"],
                "evidence_refs": ["L4.get_ndx_pe_and_earnings_yield"],
            },
            "token_usage": {
                "l1": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                "bridge": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
            },
        },
    )
    _write_json(
        run_dir / "context_brief.json",
        {
            "data_summary": "global brief",
            "layer_highlights": {
                "L1": ["global L1"],
                "L2": ["global L2"],
                "L3": ["global L3"],
                "L4": ["global L4"],
                "L5": ["global L5"],
            },
            "apparent_cross_layer_signals": ["global cross-layer signal"],
            "task_description": "global task",
        },
    )
    for layer in ["L1", "L2", "L3", "L4", "L5"]:
        _write_json(
            run_dir / "layer_context_briefs" / f"{layer}.json",
            {
                "data_summary": f"{layer} local brief",
                "layer_highlights": {layer: [f"{layer} local highlight"]},
                "apparent_cross_layer_signals": [],
                "task_description": f"{layer} local task",
            },
        )
    prompt_text = "## System Message\n系统约束\n\n## User Message\nObjectCanon\nIndicatorCanon\nPermissionType\nResponse Rules\nL1 runtime prompt"
    prompt_dir = run_dir / "prompt_audit" / "L1"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "attempt_1.prompt.txt").write_text(prompt_text, encoding="utf-8")
    _write_json(prompt_dir / "attempt_1.payload.json", {"payload": {"layer": "L1"}})
    (prompt_dir / "attempt_1.response.raw.txt").write_text('{"layer":"L1"}', encoding="utf-8")
    _write_json(prompt_dir / "output.validated.json", {"layer": "L1", "local_conclusion": "干净"})
    _write_json(
        prompt_dir / "meta.json",
        {
            "stage": "L1",
            "stage_name": "l1",
            "status": "ok",
            "prompt_chars": len(prompt_text),
            "prompt_sha256": __import__("hashlib").sha256(prompt_text.encode("utf-8")).hexdigest(),
            "prompt_file": "prompt_audit/L1/attempt_1.prompt.txt",
            "output_artifact": "layer_cards/L1.json",
            "attempts": 1,
        },
    )
    _write_json(
        run_dir / "run_summary.json",
        {"prompt_inspector": str(tmp_path / "reports" / "vnext_prompt_inspector_run.html")},
    )
    _write_json(
        run_dir / "llm_stage_diagnostics.json",
        {
            "stages": {
                "l1": {
                    "status": "ok",
                    "attempts": 1,
                    "prompt_chars": len(prompt_text),
                    "prompt_audit": {"stage_dir": "prompt_audit/L1"},
                }
            }
        },
    )
    _write_json(
        run_dir / "synthesis_packet.json",
        {
            "packet_meta": {
                "data_date": "2026-04-23",
                "backtest_date": "2025-04-09",
                "indicator_total": 34,
                "indicator_successful": 34,
                "backtest_data_boundaries": [
                    {
                        "function_id": "get_ndx_forward_earnings_quality",
                        "reason": "latest-only source",
                        "future_upgrade": "historical source required",
                    }
                ],
                "strict_backtest_invariants": {
                    "hard_enforced": [
                        {
                            "invariant_id": "observation_dates_lte_effective_date",
                            "status": "enforced_by_data_integrity_gate",
                            "description": "dates are gated",
                        }
                    ],
                    "declared_limitations": [
                        {
                            "invariant_id": "alfred_first_vintage_not_enforced",
                            "status": "declared_limitation",
                            "future_upgrade": "ALFRED vintage required",
                        }
                    ],
                },
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
        run_dir / "layer_cards" / "L4.json",
        {
            "layer": "L4",
            "local_conclusion": "估值偏高。",
            "confidence": "medium",
            "layer_synthesis": "估值需要盈利和利率共同验证。",
            "internal_conflict_analysis": "PE 与简式收益差距均提示安全边际偏薄。",
            "indicator_analyses": [
                {
                    "function_id": "get_ndx_pe_and_earnings_yield",
                    "metric": "NDX Valuation",
                    "current_reading": "PE 34.0",
                    "normalized_state": "expensive",
                    "narrative": "Trendonify 有历史分位，WorldPERatio 只做 PE 交叉校验。",
                    "reasoning_process": "真实历史分位优先；WorldPERatio rolling range 不当作分位。",
                    "first_principles_chain": ["PE", "historical percentile", "source disagreement"],
                    "cross_layer_implications": ["需要 L1 验证利率"],
                    "risk_flags": ["valuation_compression"],
                    "permission_type": "fact",
                    "canonical_question": "估值是否给未来回报留下安全边际？",
                },
                {
                    "function_id": "get_equity_risk_premium",
                    "metric": "NDX Simple Yield Gap",
                    "current_reading": "-0.75%",
                    "normalized_state": "thin_margin",
                    "narrative": "这是收益率与 10 年期美债的简式差距，不是 Damodaran 式 implied ERP。",
                    "reasoning_process": "FCF yield 3.5% - 10Y 4.25% = -0.75%。",
                    "first_principles_chain": ["FCF yield", "10Y Treasury", "simple gap"],
                    "cross_layer_implications": ["需要 L1 验证利率"],
                    "risk_flags": ["thin_margin"],
                    "permission_type": "composite",
                },
                {
                    "function_id": "get_damodaran_us_implied_erp",
                    "metric": "Damodaran US Implied ERP",
                    "current_reading": "4.33%",
                    "normalized_state": "background_anchor",
                    "narrative": "这是美国市场 implied ERP 背景锚，不替代 NDX 自身估值。",
                    "reasoning_process": "Damodaran 官方数据只解释美国市场风险补偿背景。",
                    "first_principles_chain": ["US market ERP", "background anchor"],
                    "cross_layer_implications": ["不能替代 NDX PE 分位"],
                    "risk_flags": [],
                    "permission_type": "context",
                }
            ],
        },
    )
    _write_json(
        run_dir / "analysis_packet.json",
        {
            "raw_data": {
                "L4": {
                    "get_ndx_pe_and_earnings_yield": {
                        "function_id": "get_ndx_pe_and_earnings_yield",
                        "metric_name": "NDX Valuation",
                        "value": {
                            "PE": 34.0,
                            "ThirdPartyChecks": [
                                {
                                    "source_name": "Trendonify",
                                    "source_tier": "third_party_estimate",
                                    "metric": "ndx_trailing_pe",
                                    "value": 34.1,
                                    "percentile_10y": 86.0,
                                    "historical_percentile": 86.0,
                                    "data_date": "May 01, 2026",
                                    "availability": "available",
                                },
                                {
                                    "source_name": "WorldPERatio",
                                    "source_tier": "third_party_estimate",
                                    "metric": "ndx_trailing_pe",
                                    "value": 32.27,
                                    "percentile_10y": None,
                                    "historical_percentile": None,
                                    "data_date": "01 May 2026",
                                    "availability": "available",
                                    "unavailable_reason": "historical percentile unavailable: source does not provide explicit percentile/rank",
                                    "relative_position": {
                                        "position_type": "std_dev_context_not_percentile",
                                        "valuation_windows": {
                                            "5y": {
                                                "average_pe": 31.2,
                                                "std_dev": 5.1,
                                                "range_low": 26.1,
                                                "range_high": 36.3,
                                                "deviation_vs_mean_sigma": 0.21,
                                                "valuation_label": "Fair",
                                            },
                                            "10y": {
                                                "average_pe": 27.4,
                                                "std_dev": 4.0,
                                                "range_low": 23.4,
                                                "range_high": 31.4,
                                                "deviation_vs_mean_sigma": 1.22,
                                                "valuation_label": "Overvalued",
                                            },
                                            "20y": {
                                                "average_pe": 25.8,
                                                "std_dev": 4.2,
                                                "range_low": 21.6,
                                                "range_high": 30.0,
                                                "deviation_vs_mean_sigma": 1.54,
                                                "valuation_label": "Overvalued",
                                            },
                                        },
                                        "trend_context": {
                                            "sma50_margin_pct": 8.7,
                                            "sma200_margin_pct": 12.4,
                                        },
                                    },
                                },
                                {
                                    "source_name": "Trendonify",
                                    "source_tier": "unavailable",
                                    "metric": "ndx_forward_pe",
                                    "value": None,
                                    "availability": "unavailable",
                                    "unavailable_reason": "403 Forbidden",
                                },
                            ],
                        },
                        "data_quality": {
                            "source_tier": "component_model",
                            "data_date": "2026-04-30",
                            "collected_at_utc": "2026-05-01T00:00:00Z",
                            "update_frequency": "daily when sources update",
                            "formula": "component model current value; third-party checks for PE/percentile",
                            "coverage": {"market_cap_coverage_pct": 92.5},
                            "anomalies": [],
                            "fallback_chain": ["licensed_manual/Wind", "official", "component_model", "third_party_estimate", "proxy"],
                            "source_disagreement": {"WorldPERatio PE": 32.27, "Trendonify PE": 34.1},
                        },
                    },
                    "get_damodaran_us_implied_erp": {
                        "function_id": "get_damodaran_us_implied_erp",
                        "metric_name": "Damodaran US Implied ERP Reference",
                        "value": {
                            "erp_t12m_adjusted_payout": 4.24,
                            "erp_t12m_cash_yield": 4.36,
                            "erp_avg_cf_yield_10y": 6.36,
                            "erp_net_cash_yield": 4.15,
                            "erp_normalized_earnings_payout": 3.73,
                            "implied_erp_fcfe": 4.24,
                            "tbond_rate": 4.40,
                            "adjusted_riskfree_rate": 4.14,
                            "default_spread": 0.26,
                            "expected_return": 8.55,
                            "scope": "US equity market reference, not NDX-specific",
                            "source_file": "ERPbymonth.xlsx",
                            "current_calculator_source_file": "ERPMay26.xlsx",
                            "monthly_series": [
                                {"data_date": "2026-01-01", "erp_t12m_adjusted_payout": 4.10, "us_10y_treasury_rate": 4.05, "expected_return": 8.15},
                                {"data_date": "2026-02-01", "erp_t12m_adjusted_payout": 4.18, "us_10y_treasury_rate": 4.18, "expected_return": 8.36},
                                {"data_date": "2026-03-01", "erp_t12m_adjusted_payout": 4.31, "us_10y_treasury_rate": 4.31, "expected_return": 8.62},
                                {"data_date": "2026-04-01", "erp_t12m_adjusted_payout": 4.29, "us_10y_treasury_rate": 4.25, "expected_return": 8.54},
                                {"data_date": "2026-05-01", "erp_t12m_adjusted_payout": 4.24, "us_10y_treasury_rate": 4.40, "expected_return": 8.55},
                            ],
                        },
                        "data_quality": {
                            "source_tier": "official",
                            "data_date": "2026-05-01",
                            "collected_at_utc": "2026-05-01T00:00:00Z",
                            "update_frequency": "monthly current ERP when ERPbymonth.xlsx is available",
                            "formula": "Damodaran US implied ERP model; monthly current ERP preferred",
                            "coverage": {"scope": "US market/S&P 500 reference"},
                            "anomalies": [],
                            "fallback_chain": ["official", "unavailable"],
                            "source_disagreement": {},
                        },
                    },
                    "get_equity_risk_premium": {
                        "function_id": "get_equity_risk_premium",
                        "metric_name": "NDX Simple Yield Gap",
                        "data_quality": {
                            "source_tier": "component_model",
                            "data_date": "2026-04-30",
                            "collected_at_utc": "2026-05-01T00:00:00Z",
                            "update_frequency": "daily when sources update",
                            "formula": "NDX FCF yield - 10Y Treasury yield",
                            "coverage": {"market_cap_coverage_pct": 92.5},
                            "anomalies": ["2 constituents excluded from FCF coverage"],
                            "fallback_chain": ["licensed_manual/Wind", "component_model", "proxy"],
                            "source_disagreement": {"WorldPERatio PE": 32.27, "Trendonify PE": 34.51},
                        },
                    }
                }
            }
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
                    "confirming_indicators": ["get_10y_real_rate", "get_vix"],
                    "mechanism": "利率和风险偏好共同压低估值容忍度。",
                    "implication": "反弹需要更强确认。",
                    "falsifiers": ["风险偏好改善且利率回落。"],
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
    _write_json(
        run_dir / "risk_boundary_report.json",
        {
            "failure_conditions": [],
            "must_preserve_risks": ["valuation_compression"],
            "boundary_status": {
                "liquidity_shock": "safe",
                "valuation_compression": "warning",
            },
        },
    )
    _write_json(run_dir / "schema_guard_report.json", {"passed": True})
    _write_json(run_dir / "data_integrity_report.json", {"publish_status": "publishable", "blocking_reasons": []})

    reporter = VNextReportGenerator(reports_dir=str(tmp_path / "reports"))
    report_path = reporter.run(run_dir)
    html = Path(report_path).read_text(encoding="utf-8")

    # Brief is now a single fixed spine with depth moved to a companion layers artifact.
    assert "NDX 投资判断书" in html
    assert "主论证" in html
    assert "压力测试" in html
    assert "事实对照" in html
    assert "如果发生这些事，我就改判断" in html
    assert "和上次判断比，什么变了" in html
    assert "分层证据" in html
    assert "完整底稿 artifact" in html
    spine_ids = [html.index(f'id="{section_id}"') for section_id in ("facade", "thesis", "stress", "world", "integrated-adjudication", "risks", "change", "layers", "audit")]
    assert spine_ids == sorted(spine_ids)
    assert "这不是低风险环境，但可能是高风险高赔率候选。" in html
    assert "高风险高赔率候选。" in html
    assert "战术仓" in html
    assert "可发布" in html
    assert "Agent IO Audit" not in html
    assert "L1-L5 输入边界卡" not in html
    assert "style-b style-b-light micro-1" in html
    assert 'class="sec facade-section"' in html
    assert 'class="facade"' in html
    assert ".sec.facade-section { margin-top: 6px; }" in html
    assert ".facade-section > .facade { margin-top: 0; }" in html
    assert '--sans: "PingFang SC", "Helvetica Neue", "Noto Sans SC", sans-serif;' in html
    assert "--card-line: #e6e0d5;" in html
    assert "body.style-b-light .ref-chip:not(.dv)" in html
    assert 'class="brief-hero-grid"' not in html
    assert "L1·10年实际利率" in html
    assert 'class="sec-main prose thesis-prose"' in html
    assert 'class="layer-brief"' in html
    assert '<div class="chain-grid">' not in html
    assert " dcard" in html
    assert "skip-link" in html
    assert "Source Serif Pro" in html
    assert "JetBrains Mono" in html
    assert "Inter" in html
    assert 'id="vnext-data"' not in html
    payload_match = re.search(r'<script type="application/json" id="ref-digest">(.*?)</script>', html, re.S)
    assert payload_match
    assert "&quot;" not in payload_match.group(1)
    payload = json.loads(payload_match.group(1))
    assert set(payload) == {"metrics", "trends"}
    assert set(payload["metrics"]["L1.get_10y_real_rate"]) == set(REF_DIGEST_FIELDS)
    assert len(payload_match.group(1).encode("utf-8")) <= 50 * 1024

    layers_path = Path(report_path).with_name(Path(report_path).stem.replace("brief", "layers", 1) + ".html")
    assert layers_path.exists()
    layers_html = layers_path.read_text(encoding="utf-8")
    assert "template-layers" in layers_html
    assert 'id="get_10y_real_rate"' in layers_html
    assert 'id="evidence-L1-get_10y_real_rate"' in layers_html
    assert "data-contract-ref" in layers_html
    assert "Valuation cross-check + WorldPERatio" in layers_html
    assert "ERPbymonth.xlsx" in layers_html
    assert "ERPMay26.xlsx" in layers_html
    assert "std-dev, not percentile" in layers_html
    assert "Overvalued" in layers_html
    assert "toggleLayerCard" in layers_html
    assert "layer-card__head" in layers_html
    assert "layer-summary-tile" in layers_html
    audit_index = Path(report_path).with_name(f"{Path(report_path).stem}_audit_index.json")
    assert audit_index.exists()
    audit_payload = json.loads(audit_index.read_text(encoding="utf-8"))
    assert audit_payload["kind"] == "vnext_brief_audit_index"
    assert any(item["relative_path"] == "analysis_packet.json" for item in audit_payload["artifact_files"])
    assert any(item["relative_path"] == "golden_pit_checklist.json" for item in audit_payload["artifact_files"])

    atlas_path = reporter.run(run_dir, template="atlas")
    atlas_html = Path(atlas_path).read_text(encoding="utf-8")
    assert "template-atlas" in atlas_html

    legacy_path = reporter.run(run_dir, template="brief", include_legacy_agent_io_audit=True)
    legacy_html = Path(legacy_path).read_text(encoding="utf-8")
    assert "Agent IO Audit" not in legacy_html
    assert 'id="ref-digest"' in legacy_html


def test_prompt_inspector_renders_complete_prompt_and_hash(tmp_path: Path):
    run_dir = tmp_path / "run"
    prompt_text = "## System Message\n系统约束\n\n## User Message\nObjectCanon\nIndicatorCanon\nPermissionType\nResponse Rules\n完整原文_SENTINEL"
    prompt_dir = run_dir / "prompt_audit" / "L1"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "attempt_1.prompt.txt").write_text(prompt_text, encoding="utf-8")
    _write_json(prompt_dir / "attempt_1.payload.json", {"payload": {"layer": "L1", "value": 5.25}})
    (prompt_dir / "attempt_1.response.raw.txt").write_text('{"layer":"L1"}', encoding="utf-8")
    _write_json(prompt_dir / "output.validated.json", {"layer": "L1", "local_conclusion": "ok"})
    prompt_hash = __import__("hashlib").sha256(prompt_text.encode("utf-8")).hexdigest()
    _write_json(
        prompt_dir / "meta.json",
        {
            "stage": "L1",
            "stage_name": "l1",
            "status": "ok",
            "prompt_sha256": prompt_hash,
            "prompt_file": "prompt_audit/L1/attempt_1.prompt.txt",
            "output_artifact": "layer_cards/L1.json",
            "attempts": 1,
        },
    )
    _write_json(
        run_dir / "llm_stage_diagnostics.json",
        {"stages": {"l1": {"status": "ok", "attempts": 1, "prompt_audit": {"stage_dir": "prompt_audit/L1"}}}},
    )

    path = PromptInspectorGenerator(reports_dir=str(tmp_path / "reports")).run(run_dir)
    html = Path(path).read_text(encoding="utf-8")

    assert "Agent 原文检查器" in html
    assert "完整原文_SENTINEL" in html
    assert prompt_hash in html
    assert "总览" in html
    assert "完整原文" in html
    assert "输入数据" in html
    assert "规则定位" in html
    assert "输出结果" in html
    assert "下游流向" in html


def test_prompt_inspector_empty_cross_layer_signals_are_clean(tmp_path: Path):
    run_dir = tmp_path / "run"
    prompt_text = '## System Message\n系统约束\n\n## User Message\n{"context_brief":{"apparent_cross_layer_signals":[]}}'
    prompt_dir = run_dir / "prompt_audit" / "L1"
    prompt_dir.mkdir(parents=True)
    (prompt_dir / "attempt_1.prompt.txt").write_text(prompt_text, encoding="utf-8")
    _write_json(
        prompt_dir / "attempt_1.payload.json",
        {
            "payload": {
                "layer": "L1",
                "context_brief": {"apparent_cross_layer_signals": [], "layer_highlights": {"L1": ["ok"]}},
                "layer_raw_data": {},
                "layer_facts": {},
            }
        },
    )
    (prompt_dir / "attempt_1.response.raw.txt").write_text('{"layer":"L1"}', encoding="utf-8")
    _write_json(prompt_dir / "output.validated.json", {"layer": "L1"})
    _write_json(prompt_dir / "meta.json", {"stage": "L1", "stage_name": "l1", "status": "ok", "attempts": 1})
    _write_json(run_dir / "llm_stage_diagnostics.json", {"stages": {}})

    payload = PromptInspectorGenerator(reports_dir=str(tmp_path / "reports"))._load_payload(run_dir)

    assert payload["stages"][0]["boundary"]["status"] == "干净"


def test_prompt_inspector_flags_user_decision_profile_in_analysis_prompt(tmp_path: Path):
    inspector = PromptInspectorGenerator(reports_dir=str(tmp_path / "reports"))

    result = inspector._scan_boundary(
        "thesis",
        '## User Message\n{"user_decision_profile":{"objective":"wait for golden pit"}}',
    )

    assert result["status"] == "违规"
    assert any("个人决策档案" in item["rule"] for item in result["findings"])


def test_l4_valuation_visual_uses_third_party_pb_when_component_pb_diverges(tmp_path: Path):
    reporter = VNextReportGenerator(reports_dir=str(tmp_path / "reports"))

    html = reporter._valuation_indicator_visual(
        "L4.get_ndx_pe_and_earnings_yield",
        {
            "PE": 33.3,
            "ForwardPE": 22.72,
            "PriceToBook": 41.18,
            "ThirdPartyChecks": [
                {"source_name": "DanjuanFunds", "value": 34.16, "pb": 10.02, "availability": "available"},
            ],
        },
    )

    assert "PB (3P)</b>10.02x" in html
    assert "Component-model PB diverged materially" in html


def test_l4_valuation_visual_explains_rejected_component_pb(tmp_path: Path):
    reporter = VNextReportGenerator(reports_dir=str(tmp_path / "reports"))

    html = reporter._valuation_indicator_visual(
        "L4.get_ndx_pe_and_earnings_yield",
        {
            "PE": 33.3,
            "ForwardPE": 22.72,
            "PriceToBook": None,
            "RejectedMetrics": {
                "PriceToBook": {
                    "component_value": 41.18,
                    "reference_median": 10.02,
                    "relative_diff_pct": 311.0,
                }
            },
            "ThirdPartyChecks": [
                {"source_name": "DanjuanFunds", "value": 34.16, "pb": 10.02, "availability": "available"},
            ],
        },
    )

    assert "PB (3P)</b>10.02x" in html
    assert "Component-model PB was rejected from core evidence" in html


def test_l4_valuation_visual_marks_supporting_only_component_metrics(tmp_path: Path):
    reporter = VNextReportGenerator(reports_dir=str(tmp_path / "reports"))

    html = reporter._valuation_indicator_visual(
        "L4.get_ndx_pe_and_earnings_yield",
        {
            "PE": 33.3,
            "ForwardPE": 22.72,
            "FCFYield": 1.4,
            "PriceToBook": 10.11,
            "MetricAuthority": {
                "FCFYield": {"usage": "supporting_only"},
                "PriceToBook": {"usage": "supporting_only"},
            },
            "ThirdPartyChecks": [
                {"source_name": "DanjuanFunds", "value": 34.16, "pb": 10.02, "availability": "available"},
            ],
        },
    )

    assert "FCF (proxy)</b>1.40%" in html
    assert "PB (3P)</b>10.02x" in html
    assert "FCF yield is supporting-only" in html
    assert "Component-model PB is supporting-only" in html


def test_vnext_reporter_slug_stable_with_colon_ref():
    assert _slug("L1.get_10y_real_rate") == _slug("L1.get_10y_real_rate: 1.94% 高分位") == "L1-get_10y_real_rate"


def test_vnext_reporter_renders_indicator_level_visuals(tmp_path: Path):
    run_dir = tmp_path / "run"
    _write_json(
        run_dir / "final_adjudication.json",
        {
            "approval_status": "approved_with_reservations",
            "final_stance": "中性偏谨慎",
            "confidence": "medium",
            "key_support_chains": [],
            "must_preserve_risks": [],
            "adjudicator_notes": "",
            "evidence_refs": [],
        },
    )
    _write_json(
        run_dir / "synthesis_packet.json",
        {
            "packet_meta": {"data_date": "2026-05-01", "indicator_total": 6, "indicator_successful": 6},
            "objective_firewall_summary": {
                "object_clear": True,
                "authority_clear": True,
                "timing_clear": True,
                "cross_layer_verified": True,
                "strongest_falsifier": "",
                "unresolved_tensions": [],
                "warnings": [],
            },
        },
    )

    layer_payloads = {
        "L1": [
            {
                "function_id": "get_10y_real_rate",
                "metric": "10Y Real Rate",
                "current_reading": "1.94%, 10年分位86%",
                "normalized_state": "restrictive",
                "narrative": "实际利率处在高位。",
                "reasoning_process": "",
                "first_principles_chain": [],
                "cross_layer_implications": [],
                "risk_flags": [],
            }
        ],
        "L2": [
            {
                "function_id": "get_cnn_fear_greed_index",
                "metric": "CNN Fear & Greed Index",
                "current_reading": "66.6, greed",
                "normalized_state": "greed",
                "narrative": "情绪偏贪婪但分项不一致。",
                "reasoning_process": "",
                "first_principles_chain": [],
                "cross_layer_implications": [],
                "risk_flags": [],
            }
        ],
        "L3": [
            {
                "function_id": "get_percent_above_ma",
                "metric": "% Stocks Above MA",
                "current_reading": "50D 65.35%, 200D 56.44%",
                "normalized_state": "neutral",
                "narrative": "广度中性偏好。",
                "reasoning_process": "",
                "first_principles_chain": [],
                "cross_layer_implications": [],
                "risk_flags": [],
            },
            {
                "function_id": "get_m7_fundamentals",
                "metric": "M7 Fundamentals",
                "current_reading": "market cap weighted PE 32.84, ROE 65.78%",
                "normalized_state": "strong",
                "narrative": "龙头质量较强但估值分散。",
                "reasoning_process": "",
                "first_principles_chain": [],
                "cross_layer_implications": [],
                "risk_flags": [],
            },
        ],
        "L4": [],
        "L5": [
            {
                "function_id": "get_multi_scale_ma_position",
                "metric": "QQQ Multi-Scale MA Position",
                "current_reading": "价格674.15，均线多头排列",
                "normalized_state": "bullish_alignment",
                "narrative": "趋势结构偏强。",
                "reasoning_process": "",
                "first_principles_chain": [],
                "cross_layer_implications": [],
                "risk_flags": [],
            },
            {
                "function_id": "get_donchian_channels_qqq",
                "metric": "QQQ Donchian Channels",
                "current_reading": "价格在98.1%分位",
                "normalized_state": "near_upper_band",
                "narrative": "价格贴近通道上沿。",
                "reasoning_process": "",
                "first_principles_chain": [],
                "cross_layer_implications": [],
                "risk_flags": [],
            },
            {
                "function_id": "get_price_volume_quality_qqq",
                "metric": "QQQ Price Volume Quality",
                "current_reading": "VWAP above, MFI 72, CMF 0.08",
                "normalized_state": "constructive_flow",
                "narrative": "价格和资金流确认度偏正面。",
                "reasoning_process": "",
                "first_principles_chain": [],
                "cross_layer_implications": [],
                "risk_flags": [],
            },
        ],
    }
    for layer, indicators in layer_payloads.items():
        _write_json(
            run_dir / "layer_cards" / f"{layer}.json",
            {
                "layer": layer,
                "local_conclusion": f"{layer} conclusion",
                "confidence": "medium",
                "risk_flags": [],
                "layer_synthesis": "",
                "internal_conflict_analysis": "",
                "indicator_analyses": indicators,
            },
        )
    _write_json(
        run_dir / "analysis_packet.json",
        {
            "raw_data": {
                "L1": {
                    "get_10y_real_rate": {
                        "value": {
                            "level": 1.94,
                            "ma": 1.931,
                            "deviation_pct": 0.47,
                            "position_vs_ma": "above",
                            "relativity": {"percentile_5y": 0.7238, "percentile_10y": 0.862, "z_score_10y": 1.22},
                        }
                    }
                },
                "L2": {
                    "get_cnn_fear_greed_index": {
                        "value": {
                            "score": 66.6,
                            "rating": "greed",
                            "sub_metrics": {
                                "Market Momentum (S&P500)": {"score": 99.8, "rating": "extreme greed"},
                                "Put/Call Options": {"score": 37.6, "rating": "fear"},
                                "Market Volatility (VIX)": {"score": 50, "rating": "neutral"},
                            },
                        }
                    }
                },
                "L3": {
                    "get_percent_above_ma": {
                        "value": {"level": {"percent_above_50d": 65.35, "percent_above_200d": 56.44}}
                    },
                    "get_m7_fundamentals": {
                        "value": {
                            "AAPL": {"PE": 33.9, "ROE": 141.5, "quantitative_moat_score": 9, "MarketCap": 4100},
                            "MSFT": {"PE": 24.7, "ROE": 34.0, "quantitative_moat_score": 10, "MarketCap": 3078},
                        }
                    },
                },
                "L5": {
                    "get_multi_scale_ma_position": {
                        "value": {
                            "current_price": 674.15,
                            "ma_positions": {
                                "ma5": {"value": 665.05, "deviation_pct": 1.37},
                                "ma20": {"value": 638.2, "deviation_pct": 5.63},
                                "ma60": {"value": 611.53, "deviation_pct": 10.24},
                                "ma200": {"value": 604.08, "deviation_pct": 11.6},
                            },
                        }
                    },
                    "get_donchian_channels_qqq": {
                        "value": {"upper": 675.97, "middle": 627.18, "lower": 578.4, "position_pct": 98.1}
                    },
                    "get_price_volume_quality_qqq": {
                        "value": {
                            "price_vs_vwap_20": "above",
                            "vwap_deviation_pct": 1.2,
                            "mfi_14": 72.0,
                            "mfi_status": "neutral",
                            "cmf_20": 0.08,
                            "cmf_status": "accumulation",
                        }
                    },
                },
            }
        },
    )
    _write_json(run_dir / "bridge_memos" / "bridge_0.json", {"bridge_type": "test", "cross_layer_claims": [], "conflicts": []})
    _write_json(run_dir / "critique.json", {"overall_assessment": "", "cross_layer_issues": []})
    _write_json(run_dir / "risk_boundary_report.json", {"failure_conditions": [], "must_preserve_risks": []})
    _write_json(run_dir / "schema_guard_report.json", {"passed": True})

    reporter = VNextReportGenerator(reports_dir=str(tmp_path / "reports"))
    report_path = reporter.run(run_dir)
    layers_path = Path(report_path).with_name(Path(report_path).stem.replace("brief", "layers", 1) + ".html")
    html = layers_path.read_text(encoding="utf-8")

    assert 'data-indicator-visual="L1.get_10y_real_rate"' in html
    assert 'data-visual-type="relative-position"' in html
    assert "10Y percentile" in html
    assert 'data-indicator-visual="L2.get_cnn_fear_greed_index"' in html
    assert "Market Momentum" in html
    assert 'data-indicator-visual="L3.get_percent_above_ma"' in html
    assert "50D" in html
    assert "200D" in html
    assert 'data-indicator-visual="L3.get_m7_fundamentals"' in html
    assert "M7 fundamentals heatmap" in html
    assert 'data-indicator-visual="L5.get_multi_scale_ma_position"' in html
    assert "MA ladder" in html
    assert 'data-indicator-visual="L5.get_donchian_channels_qqq"' in html
    assert "Donchian channel" in html
    assert 'data-indicator-visual="L5.get_price_volume_quality_qqq"' in html
    assert "Price-volume quality" in html
    assert "MFI" in html


def test_vnext_reporter_handles_missing_data_quality(tmp_path: Path):
    run_dir = tmp_path / "run"
    _write_json(
        run_dir / "final_adjudication.json",
        {
            "approval_status": "approved_with_reservations",
            "final_stance": "中性偏谨慎",
            "confidence": "medium",
            "key_support_chains": [],
            "must_preserve_risks": [],
            "adjudicator_notes": "",
            "evidence_refs": [],
        },
    )
    _write_json(
        run_dir / "synthesis_packet.json",
        {
            "packet_meta": {
                "data_date": "2026-04-23",
                "indicator_total": 1,
                "indicator_successful": 1,
            },
            "objective_firewall_summary": {
                "object_clear": True,
                "authority_clear": True,
                "timing_clear": True,
                "cross_layer_verified": True,
                "strongest_falsifier": "",
                "unresolved_tensions": [],
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
            "risk_flags": [],
            "layer_synthesis": "",
            "internal_conflict_analysis": "",
            "indicator_analyses": [
                {
                    "function_id": "get_10y_real_rate",
                    "metric": "10Y Real Rate",
                    "current_reading": "1.92%",
                    "normalized_state": "restrictive",
                    "narrative": "实际利率压制成长股估值。",
                    "reasoning_process": "",
                    "first_principles_chain": [],
                    "cross_layer_implications": [],
                    "risk_flags": [],
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
                "layer_synthesis": "",
                "internal_conflict_analysis": "",
                "indicator_analyses": [],
            },
        )
    # No analysis_packet.raw_data → no data_quality enrichment
    _write_json(run_dir / "analysis_packet.json", {})
    _write_json(run_dir / "bridge_memos" / "bridge_0.json", {"bridge_type": "test", "cross_layer_claims": [], "conflicts": []})
    _write_json(run_dir / "critique.json", {"overall_assessment": "", "cross_layer_issues": []})
    _write_json(run_dir / "risk_boundary_report.json", {"failure_conditions": [], "must_preserve_risks": []})
    _write_json(run_dir / "schema_guard_report.json", {"passed": True})

    reporter = VNextReportGenerator(reports_dir=str(tmp_path / "reports"))
    report_path = reporter.run(run_dir)
    layers_path = Path(report_path).with_name(Path(report_path).stem.replace("brief", "layers", 1) + ".html")
    html = layers_path.read_text(encoding="utf-8")

    # Should NOT render an inline data quality box when data_quality is absent.
    assert '<div class="data-quality-box">' not in html
    assert "data-contract-ref=\"L1.get_10y_real_rate\"" not in html
    # But layer cards should still render
    assert "layer-card" in html
    assert "evidence-L1-get_10y_real_rate" in html


def test_vnext_reporter_label_mapping():
    assert _label("approved_with_reservations", "approval") == "有保留通过"
    assert _label("medium", "confidence") == "中"
    assert _label("high", "severity") == "高"
    assert _label("valuation_compression", "risk_flag") == "估值压缩"
    assert _label("unknown_key", "approval") == "unknown_key"


def test_l4_manual_erp_visual_does_not_claim_damodaran_monthly(tmp_path: Path):
    reporter = VNextReportGenerator(reports_dir=str(tmp_path / "reports"))

    html = reporter._damodaran_indicator_visual(
        "L4.get_damodaran_us_implied_erp",
        {
            "manual_erp": 0.96,
            "manual_erp_percentile_5y": 67.3,
            "manual_erp_percentile_10y": 71.4,
            "scope": "manual/Wind ERP reference",
        },
    )

    assert "Manual/Wind ERP reference" in html
    assert "人工/Wind ERP 是外部风险补偿参考" in html
    assert "Damodaran ERP monthly lens" not in html
    assert "暂无月度序列" not in html
    assert "T12M adjusted payout" not in html
    assert "不是 Damodaran 官网月度序列，也不是 NDX 专属估值锚" in html
    assert "补偿越厚" not in html
    assert "补偿更厚" not in html
    assert "不作补偿厚薄解读" in html


def test_l4_damodaran_visual_shows_official_percentile_windows(tmp_path: Path):
    reporter = VNextReportGenerator(reports_dir=str(tmp_path / "reports"))

    html = reporter._damodaran_indicator_visual(
        "L4.get_damodaran_us_implied_erp",
        {
            "data_date": "2026-05-01",
            "erp_t12m_adjusted_payout": 4.24,
            "erp_t12m_cash_yield": 4.36,
            "source_file": "ERPbymonth.xlsx",
            "retrieval_method": "monthly_excel",
            "monthly_series": [
                {"data_date": "2026-04-01", "erp_t12m_adjusted_payout": 4.1, "us_10y_treasury_rate": 4.05, "expected_return": 8.15},
                {"data_date": "2026-05-01", "erp_t12m_adjusted_payout": 4.24, "us_10y_treasury_rate": 4.4, "expected_return": 8.55},
            ],
            "damodaran_erp_historical_percentiles": {
                "data_cutoff_date": "2026-05-01",
                "windows": {
                    "5y": {"percentile": 42.7, "status": "available", "sample_count": 60, "required_min_months": 60, "window_start": "2021-06-01", "window_end": "2026-05-01"},
                    "10y": {"percentile": 37.5, "status": "available", "sample_count": 120, "required_min_months": 120, "window_start": "2016-06-01", "window_end": "2026-05-01"},
                },
            },
        },
    )

    assert "Damodaran ERP monthly lens" in html
    assert "Damodaran ERP 5Y percentile" in html
    assert "42.7%" in html
    assert "60/60 months" in html
    assert "2021-06-01 - 2026-05-01" in html
    assert "data_cutoff_date=2026-05-01" in html
    assert "not NDX PE/PB/Forward PE historical percentile" in html


def test_l4_simple_yield_gap_does_not_reuse_damodaran_monthly_chart(tmp_path: Path):
    reporter = VNextReportGenerator(reports_dir=str(tmp_path / "reports"))
    artifacts = {
        "chart_time_series": {
            "series": {
                "DAMODARAN_ERP_MONTHLY": {
                    "rows": [
                        {"time": "2026-04-01", "value": 4.10},
                        {"time": "2026-05-01", "value": 4.24},
                    ]
                }
            }
        },
        "analysis_packet": {"raw_data": {}},
        "layers": {},
        "final_adjudication": {},
    }

    html = reporter._memo_chartbook_section(artifacts)

    assert "get_equity_risk_premium" not in INDICATOR_CHARTS
    assert INDICATOR_CHARTS["get_damodaran_us_implied_erp"] == ("DAMODARAN_ERP_MONTHLY", "value")
    assert 'data-ref="L4.get_damodaran_us_implied_erp"' in html
    assert 'data-ref="L4.get_equity_risk_premium"' not in html


def test_l4_wind_risk_premium_keeps_unverified_unit_unformatted(tmp_path: Path):
    reporter = VNextReportGenerator(reports_dir=str(tmp_path / "reports"))
    artifacts = {
        "analysis_packet": {
            "raw_data": {
                "L4": {
                    "get_ndx_wind_valuation_snapshot": {
                        "value": {
                            "PE": 32.5,
                            "RiskPremium": 1.0474,
                            "RiskPremiumHistoricalPercentile": 42.0,
                            "RiskPremiumRank": {"rank": 210, "sample_count": 500},
                        }
                    },
                    "get_equity_risk_premium": {"value": {"level": -1.77}},
                }
            }
        },
        "layers": {},
        "chart_time_series": {"series": {}},
    }

    html = "".join(
        [
            reporter._valuation_ruler_chart(artifacts),
            reporter._rate_valuation_pressure_chart(artifacts),
            reporter._wind_valuation_indicator_visual(
                "L4.get_ndx_wind_valuation_snapshot",
                artifacts["analysis_packet"]["raw_data"]["L4"]["get_ndx_wind_valuation_snapshot"]["value"],
            ),
        ]
    )

    assert "Wind NDX RP（Wind口径）" in html
    assert "1.05" in html
    assert "1.05%" not in html
    assert "Simple Yield Gap" in html
    assert "-1.77%" in html
    assert "补偿越厚" not in html
    assert "补偿更厚" not in html
    assert "不作补偿厚薄解读" in html


def test_l3_prompt_keeps_m7_as_concentration_fact_and_delegates_earnings_to_l4():
    prompt = (
        Path(__file__).parents[1] / "src" / "agent_analysis" / "prompts" / "l3_analyst.md"
    ).read_text(encoding="utf-8")

    assert "get_m7_fundamentals" not in prompt
    assert "M7 盈利质量" not in prompt
    assert "集中度有盈利支撑" not in prompt
    assert "Top10 / M7 权重" in prompt
    assert "L3 本层不得回答这个问题" in prompt


def test_l4_valuation_visual_without_worldperatio_uses_neutral_title(tmp_path: Path):
    reporter = VNextReportGenerator(reports_dir=str(tmp_path / "reports"))

    html = reporter._valuation_indicator_visual(
        "L4.get_ndx_pe_and_earnings_yield",
        {
            "PE_TTM": 36.6,
            "PB": 10.49,
            "PE_TTM_percentile_10y": 88,
        },
    )

    assert "Valuation reference values" in html
    assert "Valuation cross-check + WorldPERatio" not in html
    assert "PE</b>36.60x" in html
    assert "PB</b>10.49x" in html
    assert "未接入 Trendonify 或 WorldPERatio" in html


def test_vnext_reporter_default_output_keeps_run_id_when_data_date_repeats(tmp_path: Path):
    run_dir = tmp_path / "20260506_061216"
    _write_json(
        run_dir / "synthesis_packet.json",
        {"packet_meta": {"data_date": "2026-05-02", "indicator_total": 0, "indicator_successful": 0}},
    )
    reporter = VNextReportGenerator(reports_dir=str(tmp_path / "reports"))

    output = reporter._default_output_path(run_dir, reporter._load_artifacts(run_dir), "brief", "slate_v3")

    assert output.name == "vnext_brief_20260502_0000_20260506_0612.html"


def test_enrich_indicator_data_quality_injects_collection_timestamp():
    """collection_timestamp_utc from collector is injected into every indicator's data_quality."""
    artifacts = {
        "analysis_packet": {
            "raw_data": {
                "L1": {
                    "get_fed_funds_rate": {
                        "value": 5.25,
                        "collection_timestamp_utc": "2026-05-13T19:12:34+00:00",
                    },
                    "get_vix": {
                        "value": 18.0,
                        "collection_timestamp_utc": "2026-05-13T19:12:35+00:00",
                        "manual_override_used": True,
                    },
                }
            }
        },
        "layers": {
            "L1": {
                "indicator_analyses": [
                    {
                        "function_id": "get_fed_funds_rate",
                        "metric": "Fed Funds",
                        "current_reading": "5.25%",
                    },
                    {
                        "function_id": "get_vix",
                        "metric": "VIX",
                        "current_reading": "18.0",
                    },
                ]
            }
        },
    }
    reporter = VNextReportGenerator(reports_dir="/tmp")
    reporter._enrich_indicator_data_quality(artifacts)

    l1_items = artifacts["layers"]["L1"]["indicator_analyses"]
    fed = l1_items[0]
    vix = l1_items[1]

    assert fed["data_quality"]["collected_at_utc"] == "2026-05-13T19:12:34+00:00"
    assert vix["data_quality"]["collected_at_utc"] == "2026-05-13T19:12:35+00:00"
    assert "手动输入" in vix["data_quality"]["source_tier"]


def test_enrich_indicator_data_quality_with_existing_dq():
    """When item already has data_quality (e.g. from LLM), valuation_sources
    and collected_at_utc must still be extracted / injected (U7 fix)."""
    artifacts = {
        "analysis_packet": {
            "raw_data": {
                "L4": {
                    "get_ndx_pe": {
                        "value": {
                            "ThirdPartyChecks": [
                                {"source_name": "Bloomberg", "availability": "available"},
                                {"source_name": "Wind", "availability": "available"},
                            ]
                        },
                        "collection_timestamp_utc": "2026-05-13T19:12:36+00:00",
                        "data_quality": {
                            "source_tier": "third_party_estimate",
                            "formula": "PE = price / earnings",
                        },
                    }
                }
            }
        },
        "layers": {
            "L4": {
                "indicator_analyses": [
                    {
                        "function_id": "get_ndx_pe",
                        "metric": "NDX PE",
                        "current_reading": "32.5",
                        # LLM generated a data_quality dict
                        "data_quality": {
                            "source_tier": "third_party_estimate",
                            "confidence": "medium",
                        },
                    }
                ]
            }
        },
    }
    reporter = VNextReportGenerator(reports_dir="/tmp")
    reporter._enrich_indicator_data_quality(artifacts)

    item = artifacts["layers"]["L4"]["indicator_analyses"][0]
    dq = item["data_quality"]

    # collected_at_utc must be injected even when item had existing dq
    assert dq["collected_at_utc"] == "2026-05-13T19:12:36+00:00"
    # valuation_sources must be extracted even when item had existing dq (U7)
    assert "valuation_sources" in dq
    assert len(dq["valuation_sources"]) == 2
    assert dq["valuation_sources"][0]["source_name"] == "Bloomberg"
    # Existing LLM fields must be preserved
    assert dq["confidence"] == "medium"
    # Raw data_quality fields must be merged in (U10: raw as base)
    assert dq["formula"] == "PE = price / earnings"


def test_timestamp_chip_formatting():
    """_timestamp_chip renders the data date, source, and contract drawer entry."""
    reporter = VNextReportGenerator(reports_dir="/tmp")

    chip = reporter._timestamp_chip(
        {
            "data_date": "2026-05-13",
            "provider": "FRED",
            "source_name": "FRED",
            "source_url": "",
            "collected_at_utc": "2026-05-13T19:12:34+00:00",
        },
        ref="L1.get_fed_funds_rate",
    )
    assert "数据时间：2026-05-13" in chip
    assert "来源：FRED" in chip
    assert "缺少来源链接" in chip
    assert "data-contract-ref" in chip
    assert "timestamp-chip" in chip

    chip_effective = reporter._timestamp_chip({"effective_date": "2026-05-12", "provider": "manual"})
    assert "数据时间：2026-05-12" in chip_effective

    chip_manual = reporter._timestamp_chip({
        "data_date": "2026-05-13",
        "provider": "Manual",
        "source_tier": "official · 手动输入",
    })
    assert "手动输入" in chip_manual

    # Missing timestamp
    chip_empty = reporter._timestamp_chip({})
    assert chip_empty == ""


def test_timestamp_chip_appears_in_brief_html(tmp_path: Path):
    """Timestamp chip is rendered in the final brief HTML for each indicator."""
    run_dir = tmp_path / "run"
    _write_json(
        run_dir / "final_adjudication.json",
        {
            "approval_status": "approved_with_reservations",
            "final_stance": "中性偏谨慎",
            "confidence": "medium",
            "must_preserve_risks": ["估值压缩风险"],
            "adjudicator_notes": "保留核心冲突。",
            "evidence_refs": [],
        },
    )
    _write_json(
        run_dir / "synthesis_packet.json",
        {"packet_meta": {"data_date": "2026-05-13", "indicator_total": 1, "indicator_successful": 1}},
    )
    _write_json(
        run_dir / "layer_cards" / "L1.json",
        {
            "layer": "L1",
            "local_conclusion": "宏观偏紧。",
            "confidence": "medium",
            "indicator_analyses": [
                {
                    "function_id": "get_fed_funds_rate",
                    "metric": "Fed Funds",
                    "current_reading": "5.25%",
                    "normalized_state": "restrictive",
                    "narrative": "实际利率压制成长股估值。",
                    "reasoning_process": "实际利率上升 -> 折现率上升 -> 估值承压。",
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
                "indicator_analyses": [],
            },
        )
    _write_json(
        run_dir / "analysis_packet.json",
        {
            "raw_data": {
                "L1": {
                    "get_fed_funds_rate": {
                        "value": 5.25,
                        "collection_timestamp_utc": "2026-05-13T19:12:34+00:00",
                    }
                }
            }
        },
    )
    _write_json(run_dir / "bridge_memos" / "bridge_0.json", {"bridge_type": "test", "cross_layer_claims": [], "conflicts": []})
    _write_json(run_dir / "critique.json", {"overall_assessment": "", "cross_layer_issues": []})
    _write_json(run_dir / "risk_boundary_report.json", {"failure_conditions": [], "must_preserve_risks": []})
    _write_json(run_dir / "schema_guard_report.json", {"passed": True})

    reporter = VNextReportGenerator(reports_dir=str(tmp_path / "reports"))
    report_path = reporter.run(run_dir)
    layers_path = Path(report_path).with_name(Path(report_path).stem.replace("brief", "layers", 1) + ".html")
    html = layers_path.read_text(encoding="utf-8")

    # Evidence status should appear in the HTML with data time, not run collection time.
    assert "timestamp-chip" in html
    assert "数据时间：未记录" in html
    assert "来源：未记录" in html
    assert "证据合约" in html


# --- 个人决策翻译 (personal policy translation) ---
# Fixture profile uses obviously-fake, clearly-synthetic amounts (never the
# real IPS numbers, which only live in config/user_decision_profile.local.json
# and must never appear in a git-tracked test file).
_FAKE_DECISION_PROFILE = {
    "schema_version": "user_decision_profile_ips_v1",
    "net_worth_snapshot": {"approx_total_cny": 777777, "as_of": "2099-01-01"},
    "buckets": {
        "liquidity": {"floor_cny": 555555, "monthly_expense_estimate_cny": [111, 222]},
        "long_term_layer": {"growth_bucket_pct_of_long_term_layer": 80, "diversification_bucket_pct_of_long_term_layer": 20},
    },
}


def test_personal_policy_translation_defensive_stance_uses_defensive_copy():
    reporter = VNextReportGenerator()
    html = reporter._personal_policy_translation(
        {"final_stance": "市场宜防御减仓，等待信号确认", "state_diagnosis": "风险高于机会"},
        _FAKE_DECISION_PROFILE,
    )
    assert "本轮判断不改变战略权益（纳指/标普/红利低波）的常规定投节奏" in html
    assert "本轮偏乐观的判断不改变战略权益的常规节奏" not in html
    assert "本轮系统判断在多空之间没有明确倾向" not in html


def test_personal_policy_translation_constructive_stance_uses_constructive_copy():
    reporter = VNextReportGenerator()
    html = reporter._personal_policy_translation(
        {"final_stance": "机会大于风险，可以加仓，价值明确", "state_diagnosis": "偏多"},
        _FAKE_DECISION_PROFILE,
    )
    assert "本轮偏乐观的判断不改变战略权益的常规节奏" in html
    assert "本轮判断不改变战略权益（纳指/标普/红利低波）的常规定投节奏" not in html
    assert "本轮系统判断在多空之间没有明确倾向" not in html


def test_personal_policy_translation_neutral_stance_uses_neutral_copy():
    reporter = VNextReportGenerator()
    html = reporter._personal_policy_translation(
        {"final_stance": "多空力量大致平衡，暂无明确方向", "state_diagnosis": ""},
        _FAKE_DECISION_PROFILE,
    )
    assert "本轮系统判断在多空之间没有明确倾向" in html
    assert "本轮判断不改变战略权益（纳指/标普/红利低波）的常规定投节奏" not in html
    assert "本轮偏乐观的判断不改变战略权益的常规节奏" not in html


def test_personal_policy_translation_renders_bullish_tagged_invalidation_body():
    reporter = VNextReportGenerator()
    html = reporter._personal_policy_translation(
        {
            "final_stance": "中性",
            "invalidation_conditions": ["【转多】盈利预期上修并广度改善", "【转空】信用利差扩大"],
        },
        _FAKE_DECISION_PROFILE,
    )
    assert "你在等的'价值买入'，系统当前的具名观察条件" in html
    assert "盈利预期上修并广度改善" in html
    assert "【转多】" not in html


def test_personal_policy_translation_no_bullish_tags_shows_honest_placeholder():
    reporter = VNextReportGenerator()
    html = reporter._personal_policy_translation(
        {"final_stance": "中性", "invalidation_conditions": ["【转空】信用利差扩大"]},
        _FAKE_DECISION_PROFILE,
    )
    assert "本轮系统输出没有标注具名的【转多】转折条件" in html


def test_personal_policy_translation_risk_block_falls_back_to_must_preserve_risks():
    reporter = VNextReportGenerator()
    html = reporter._personal_policy_translation(
        {"final_stance": "中性", "invalidation_conditions": [], "must_preserve_risks": ["估值压缩风险"]},
        _FAKE_DECISION_PROFILE,
    )
    assert "估值压缩风险" in html
    assert "按你的政策书，'市场涨跌'不构成修改政策的理由" in html


def test_personal_policy_translation_risk_block_honest_placeholder_when_both_empty():
    reporter = VNextReportGenerator()
    html = reporter._personal_policy_translation(
        {"final_stance": "中性", "invalidation_conditions": [], "must_preserve_risks": []},
        _FAKE_DECISION_PROFILE,
    )
    assert "本轮未记录具名的风险触发条件" in html


def test_personal_policy_translation_empty_profile_shows_only_unconfigured_placeholder():
    reporter = VNextReportGenerator()
    html = reporter._personal_policy_translation(
        {"final_stance": "市场宜防御减仓", "invalidation_conditions": ["【转多】盈利预期上修"]},
        {},
    )
    assert "个人决策画像未配置" in html
    assert "config/user_decision_profile.local.json 不存在" in html
    # Nothing from parts (a)-(d) should leak in when the profile is unconfigured.
    assert "本轮判断不改变战略权益" not in html
    assert "价值买入" not in html
    assert "本区只是把系统判断对照你自己的政策书" not in html


def test_personal_policy_translation_footnote_present_when_profile_configured():
    reporter = VNextReportGenerator()
    html = reporter._personal_policy_translation({"final_stance": "中性"}, _FAKE_DECISION_PROFILE)
    assert "本区只是把系统判断对照你自己的政策书（2026-06-29 草案）做的机械翻译，不构成投资建议。" in html


def test_personal_policy_translation_never_leaks_profile_amounts():
    reporter = VNextReportGenerator()
    html = reporter._personal_policy_translation(
        {"final_stance": "市场宜防御减仓", "invalidation_conditions": ["【转多】盈利预期上修"]},
        _FAKE_DECISION_PROFILE,
    )
    assert "555555" not in html
    assert "777777" not in html
    assert "111" not in html
    assert "222" not in html


def test_load_local_decision_profile_missing_file_returns_empty_dict(tmp_path: Path):
    missing = tmp_path / "nope" / "user_decision_profile.local.json"
    assert _load_local_decision_profile(missing) == {}


def test_load_local_decision_profile_reads_override_path(tmp_path: Path):
    fixture_path = tmp_path / "user_decision_profile.local.json"
    _write_json(fixture_path, _FAKE_DECISION_PROFILE)
    loaded = _load_local_decision_profile(fixture_path)
    assert loaded == _FAKE_DECISION_PROFILE


def test_user_decision_profile_local_json_is_gitignored():
    repo_root = Path(__file__).resolve().parents[1]
    git_binary = None
    for candidate in ("git",):
        try:
            subprocess.run([candidate, "--version"], capture_output=True, check=True)
            git_binary = candidate
        except (OSError, subprocess.CalledProcessError):
            git_binary = None
    if git_binary is None:
        import pytest

        pytest.skip("git binary not available in this environment")
    result = subprocess.run(
        [git_binary, "check-ignore", "config/user_decision_profile.local.json"],
        cwd=repo_root,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        "config/user_decision_profile.local.json must be covered by .gitignore; "
        f"git check-ignore stdout={result.stdout!r} stderr={result.stderr!r}"
    )


def test_audit_section_displays_snapshot_identity_and_hash(tmp_path: Path):
    reporter = VNextReportGenerator(reports_dir=str(tmp_path / "reports"))
    snapshot = {
        "mode": "snapshot_replay",
        "source_filename": "data_collected_v9_20250409.json",
        "source_path": "/private/audit/data_collected_v9_20250409.json",
        "source_sha256": "abc123def456",
        "collection_time": "2025-04-10T01:02:03Z",
        "effective_date": "2025-04-09",
    }
    artifacts = {
        "final_adjudication": {},
        "synthesis_packet": {},
        "analysis_packet": {},
        "data_integrity_report": {},
        "run_summary": {},
        "llm_stage_diagnostics": {},
        "layer_context_briefs": {},
        "source_snapshot": snapshot,
    }

    html = reporter._audit_section(tmp_path, artifacts, "{}")

    assert "data_collected_v9_20250409.json" in html
    assert "/private/audit/data_collected_v9_20250409.json" in html
    assert "snapshot_replay" in html
    assert "abc123def456" in html
    assert "2025-04-09" in html
    assert "source_snapshot.json" in html
