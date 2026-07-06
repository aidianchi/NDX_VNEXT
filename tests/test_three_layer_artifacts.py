import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from event_narrative_ledger import EventNarrativeLedgerBuilder, write_event_narrative_ledger
from integrated_synthesis_report import (
    IntegratedSynthesisReportBuilder,
    build_pure_data_report_manifest,
    write_integrated_synthesis_report,
)


def _event_ledger():
    return {
        "schema_version": "news_event_ledger_v2",
        "events": [
            {
                "event_id": "event:fomc",
                "dedupe_id": "fomc",
                "source_id": "federal_reserve_press_all",
                "source_name": "Federal Reserve Press Releases",
                "source_tier": "official_macro",
                "event_type": "policy_or_financial_conditions",
                "title": "Federal Reserve issues FOMC statement",
                "published_at": "Fri, 08 May 2026 18:00:00 GMT",
                "layers": ["L1", "L2", "L4"],
                "symbols": [],
            },
            {
                "event_id": "event:future",
                "dedupe_id": "future",
                "source_name": "Future News",
                "source_tier": "reliable_mainstream_report",
                "event_type": "market_news",
                "title": "Future event",
                "published_at": "Tue, 12 May 2026 18:00:00 GMT",
            },
        ],
    }


def _news_analysis():
    return {
        "schema_version": "news_layer_analysis_v1",
        "event_summaries": [
            {
                "event_id": "event:fomc",
                "summary_zh": "这是一条来自美联储的政策事件。",
                "possible_equity_impact_zh": "可能通过利率预期影响股市。",
                "pressure_channels": ["利率预期", "风险偏好"],
            }
        ],
    }


def _data_links():
    return {
        "schema_version": "news_event_data_links_v1",
        "links": [
            {
                "event_id": "event:fomc",
                "observations": [
                    {"series_key": "US10Y_REAL", "direction": "up", "needs_bridge_review": True}
                ],
            }
        ],
    }


def test_event_narrative_ledger_builds_claims_and_filters_future_events():
    payload = EventNarrativeLedgerBuilder().build(
        event_ledger=_event_ledger(),
        news_layer_analysis=_news_analysis(),
        news_event_data_links=_data_links(),
        effective_date="2026-05-08",
    )

    assert payload["schema_version"] == "event_narrative_ledger_v1"
    assert "not injected into L1-L5" in payload["policy"]["runtime_context_rule"]
    assert [event["event_id"] for event in payload["events"]] == ["event:fomc"]
    claim = payload["events"][0]["claims"][0]
    assert claim["claim_type"] == "official_fact"
    assert claim["source_type"] == "official_fact"
    assert "discount_rate" in claim["affected_financial_links"]
    assert claim["what_it_cannot_support"].startswith("不能替代 L1-L5")
    assert claim["status"] == "event_fact"


def test_write_event_narrative_ledger_reads_run_dir_artifacts(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "news_event_ledger.json").write_text(json.dumps(_event_ledger()), encoding="utf-8")
    (run_dir / "news_layer_analysis.json").write_text(json.dumps(_news_analysis()), encoding="utf-8")
    (run_dir / "news_event_data_links.json").write_text(json.dumps(_data_links()), encoding="utf-8")

    output = write_event_narrative_ledger(run_dir, effective_date="2026-05-08")
    payload = json.loads(Path(output).read_text(encoding="utf-8"))

    assert Path(output).name == "event_narrative_ledger.json"
    assert payload["claim_count"] == 1
    assert payload["source_artifacts"]["news_event_ledger"].endswith("news_event_ledger.json")


def test_event_research_pipeline_writes_required_layer_two_artifacts(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    ledger = {
        "schema_version": "news_event_ledger_v2",
        "events": [
            {
                "event_id": "event:official",
                "dedupe_id": "official",
                "source_id": "federal_reserve_press_all",
                "source_name": "Federal Reserve Press Releases",
                "source_tier": "official_macro",
                "event_type": "policy_or_financial_conditions",
                "title": "Federal Reserve issues FOMC statement",
                "published_at": "Fri, 08 May 2026 18:00:00 GMT",
                "layers": ["L1", "L2", "L4"],
                "symbols": [],
                "raw_text_available": False,
            },
            {
                "event_id": "event:media",
                "dedupe_id": "media",
                "source_id": "market_news",
                "source_name": "Market News",
                "source_tier": "reliable_mainstream_report",
                "event_type": "policy_or_financial_conditions",
                "title": "Federal Reserve issues FOMC statement",
                "published_at": "Fri, 08 May 2026 18:05:00 GMT",
                "layers": ["L1", "L2", "L4"],
                "symbols": [],
                "raw_text_available": False,
            },
            {
                "event_id": "event:social",
                "dedupe_id": "social",
                "source_id": "stocktwits",
                "source_name": "StockTwits",
                "source_tier": "unverified_signal",
                "event_type": "market_chatter",
                "title": "Traders are excited about QQQ",
                "published_at": "Fri, 08 May 2026 18:10:00 GMT",
                "layers": [],
                "symbols": ["QQQ"],
                "raw_text_available": False,
            },
        ],
    }
    links = {
        "schema_version": "news_event_data_links_v1",
        "links": [
            {
                "event_id": "event:official",
                "observations": [
                    {
                        "series_key": "VIX",
                        "direction": "up",
                        "needs_bridge_review": True,
                        "start_time": "2026-05-08",
                        "end_time": "2026-05-11",
                    }
                ],
            }
        ],
    }

    output = write_event_narrative_ledger(
        run_dir,
        event_ledger=ledger,
        news_event_data_links=links,
        effective_date="2026-05-11",
    )
    payload = json.loads(Path(output).read_text(encoding="utf-8"))
    clusters = json.loads((run_dir / "event_clusters.json").read_text(encoding="utf-8"))
    claim_ledger = json.loads((run_dir / "event_claim_ledger.json").read_text(encoding="utf-8"))
    validation = json.loads((run_dir / "event_market_validation.json").read_text(encoding="utf-8"))
    review = json.loads((run_dir / "event_adversarial_review.json").read_text(encoding="utf-8"))
    summary = json.loads((run_dir / "event_layer_summary.json").read_text(encoding="utf-8"))

    assert payload["event_cluster_count"] == 2
    assert len(clusters["clusters"]) == 2
    assert any(len(cluster["supporting_sources"]) == 2 for cluster in clusters["clusters"])
    claim_types = {claim["source_event_id"]: claim["claim_type"] for claim in claim_ledger["claims"]}
    assert claim_types["event:official"] == "official_fact"
    assert claim_types["event:media"] == "interpretation_claim"
    assert claim_types["event:social"] == "rumor_claim"
    media_claim = next(claim for claim in claim_ledger["claims"] if claim["source_event_id"] == "event:media")
    assert media_claim["source_nature"] == "媒体报道"
    assert "官方事件" not in media_claim["claim_text"]
    assert "发布标题" in media_claim["fact_part"]
    assert "未读取全文" in media_claim["interpretation_part"]
    assert all(claim["confidence_before_market_validation"] == "low" for claim in claim_ledger["claims"])
    assert validation["summary"] == {"background_market_observation": 1, "insufficient_data": 1}
    assert any(item["validation_label"] == "background_market_observation" for item in validation["validations"])
    assert all(item["causality_statement"] == "background market observation only; not causal evidence" for item in validation["validations"])
    assert review["overall_status"] == "pass"
    assert "禁止进入 L1-L5" in summary["forbidden_for_l1_l5_statement"]
    assert (run_dir / "event_narrative_report.md").exists()
    assert any((run_dir / "event_research_packets").iterdir())
    mechanism = json.loads((run_dir / "event_mechanism_report.json").read_text(encoding="utf-8"))
    questions = json.loads((run_dir / "cross_layer_questions.json").read_text(encoding="utf-8"))
    cards = json.loads((run_dir / "event_mechanism_cards.json").read_text(encoding="utf-8"))
    html = (run_dir / "event_mechanism_report.html").read_text(encoding="utf-8")
    assert mechanism["schema_version"] == "event_mechanism_report_v1"
    assert mechanism["headline_judgment"]["title"] == "新闻事件初步判断"
    assert mechanism["headline_judgment"]["cannot_be_used_as_primary_evidence"] is True
    assert questions["schema_version"] == "cross_layer_questions_v1"
    assert cards["schema_version"] == "event_mechanism_cards_v1"
    assert "新闻事件初步判断" in html
    assert "可以说" in html
    assert "不能说" in html
    assert "data-detail" in html
    assert "AI 分析" in html
    assert "给综合研报的一句话" in html
    assert "earnings_path" not in html
    assert "discount_rate" not in html
    assert "第二层可以说" not in html
    assert "新闻导致价格变化" not in html


def test_event_research_packet_without_market_validation_cannot_be_high_confidence(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    output = write_event_narrative_ledger(
        run_dir,
        event_ledger=_event_ledger(),
        news_layer_analysis={},
        news_event_data_links={},
        effective_date="2026-05-08",
    )

    payload = json.loads(Path(output).read_text(encoding="utf-8"))
    packets = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in (run_dir / "event_research_packets").iterdir()
    ]
    assert payload["research_packet_count"] == 1
    assert payload["market_validation_summary"] == {"insufficient_data": 1}
    assert packets[0]["agent_confidence"] != "high"
    assert any("缺少市场验证观察" in reason for reason in packets[0]["downgrade_reasons"])


def test_event_mechanism_report_groups_news_into_plain_language_mainlines(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    ledger = {
        "schema_version": "news_event_ledger_v2",
        "events": [
            {
                "event_id": "event:micron",
                "source_id": "wind_news",
                "source_name": "Wind Financial News",
                "source_tier": "reliable_mainstream_report",
                "event_type": "licensed_financial_news",
                "title": "美光财测点燃AI信心 半导体链条走强",
                "published_at": "Fri, 08 May 2026 09:00:00 GMT",
                "symbols": ["NDX", "QQQ"],
                "raw_text_available": False,
            },
            {
                "event_id": "event:fed",
                "source_id": "wind_news",
                "source_name": "Wind Financial News",
                "source_tier": "reliable_mainstream_report",
                "event_type": "licensed_financial_news",
                "title": "美联储政策预期分歧 科技股估值承压",
                "published_at": "Fri, 08 May 2026 09:05:00 GMT",
                "symbols": ["NDX", "QQQ"],
                "raw_text_available": False,
            },
        ],
    }

    write_event_narrative_ledger(run_dir, event_ledger=ledger, effective_date="2026-05-08")
    mechanism = json.loads((run_dir / "event_mechanism_report.json").read_text(encoding="utf-8"))
    html = (run_dir / "event_mechanism_report.html").read_text(encoding="utf-8")

    mainlines = {item["mainline_id"]: item for item in mechanism["mainlines"]}
    assert "ai_semiconductor_earnings" in mainlines
    assert "macro_rate_valuation_pressure" in mainlines
    ai_cards = [
        card for card in mechanism["news_cards"]
        if card["mainline_id"] == "ai_semiconductor_earnings"
    ]
    assert ai_cards
    assert ai_cards[0]["missing_evidence"] == ["缺 URL", "未读取全文", "媒体解释不能当官方事实"]
    assert "美光和半导体指数是否相对纳指100继续走强" in ai_cards[0]["needs_data_confirmation"]
    assert "美光财测" in ai_cards[0]["one_line_summary"]
    assert len({card["news_id"] for card in mechanism["news_cards"]}) == len(mechanism["news_cards"])
    assert any(item["direction"] == "event_to_data" for item in mechanism["cross_layer_questions"])
    assert any(item["direction"] == "data_to_event" for item in mechanism["cross_layer_questions"])
    assert "Layer 2 Event Mechanism Report" not in html
    assert "risk_premium" not in html


def test_event_mechanism_report_keeps_weak_announcements_out_of_headline(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    ledger = {
        "schema_version": "news_event_ledger_v2",
        "events": [
            {
                "event_id": "event:nport",
                "source_id": "wind_announcement",
                "source_name": "Wind Company Announcements",
                "source_tier": "company_disclosure",
                "event_type": "company_filing",
                "title": "YieldMax AAPL Option Income Strategy ETF:Form NPORT-P Monthly Portfolio Investments Report on Form N-PORT (Public)",
                "published_at": "Fri, 08 May 2026 10:00:00 GMT",
                "symbols": ["AAPL"],
                "raw_text_available": True,
            },
            {
                "event_id": "event:micron",
                "source_id": "wind_news",
                "source_name": "Wind Financial News",
                "source_tier": "reliable_mainstream_report",
                "event_type": "licensed_financial_news",
                "title": "美光财测点燃AI信心 主要指数开高科技股领涨",
                "published_at": "Fri, 08 May 2026 09:00:00 GMT",
                "symbols": ["NDX", "QQQ"],
                "raw_text_available": False,
            },
        ],
    }

    write_event_narrative_ledger(run_dir, event_ledger=ledger, effective_date="2026-05-08")
    mechanism = json.loads((run_dir / "event_mechanism_report.json").read_text(encoding="utf-8"))

    headline = mechanism["headline_judgment"]["plain_text"]
    nport = next(card for card in mechanism["news_cards"] if "NPORT" in card["title"])
    micron = next(card for card in mechanism["news_cards"] if "美光" in card["title"])
    assert "NPORT" not in headline
    assert nport["relevance_band"] == "background"
    assert micron["relevance_band"] == "core"
    assert mechanism["news_cards"][0]["title"] == micron["title"]


def test_event_mechanism_report_caps_market_narrative_materiality(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    ledger = {
        "schema_version": "news_event_ledger_v2",
        "events": [
            {
                "event_id": "event:reddit_rates",
                "source_id": "reddit",
                "source_name": "Reddit r/stocks QQQ Search",
                "source_tier": "market_narrative",
                "event_type": "social_discussion",
                "title": "Kevin Warsh will cut rates this year. IMO and here is why",
                "published_at": "Fri, 08 May 2026 09:00:00 GMT",
                "symbols": ["NDX", "QQQ"],
                "raw_text_available": False,
                "url": "https://www.reddit.com/example",
            }
        ],
    }

    write_event_narrative_ledger(run_dir, event_ledger=ledger, effective_date="2026-05-08")
    mechanism = json.loads((run_dir / "event_mechanism_report.json").read_text(encoding="utf-8"))

    card = mechanism["news_cards"][0]
    assert card["mainline_id"] == "macro_rate_valuation_pressure"
    assert card["relevance_band"] != "core"
    assert card["source_quality"] == "有限材料：只有标题"


def test_event_mechanism_report_analyzes_each_news_card_separately(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    ledger = {
        "schema_version": "news_event_ledger_v2",
        "events": [
            {
                "event_id": "event:micron",
                "source_id": "wind_news",
                "source_name": "Wind Financial News",
                "source_tier": "reliable_mainstream_report",
                "event_type": "licensed_financial_news",
                "title": "美光财测点燃AI信心 半导体链条走强",
                "published_at": "Fri, 08 May 2026 09:00:00 GMT",
                "symbols": ["NDX", "QQQ"],
                "raw_text_available": False,
            },
            {
                "event_id": "event:burry",
                "source_id": "yahoo",
                "source_name": "Yahoo Finance M7 Headlines",
                "source_tier": "reliable_mainstream_report",
                "event_type": "market_news",
                "title": "Michael Burry Is Short NVDA, AMAT, SOXX — Sees Big Korea Chip Spending As Beginning Of The End",
                "published_at": "Fri, 08 May 2026 09:05:00 GMT",
                "symbols": ["NDX", "QQQ"],
                "raw_text_available": False,
                "url": "https://finance.yahoo.com/example",
            },
        ],
    }

    write_event_narrative_ledger(run_dir, event_ledger=ledger, effective_date="2026-05-08")
    mechanism = json.loads((run_dir / "event_mechanism_report.json").read_text(encoding="utf-8"))
    micron = next(card for card in mechanism["news_cards"] if "美光" in card["title"])
    burry = next(card for card in mechanism["news_cards"] if "Burry" in card["title"])

    assert micron["one_line_summary"] != burry["one_line_summary"]
    assert micron["ai_analysis"] != burry["ai_analysis"]
    assert "盈利" in micron["one_line_summary"]
    assert "反向线索" in burry["one_line_summary"]


def test_event_mechanism_report_does_not_match_ai_inside_words(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    ledger = {
        "schema_version": "news_event_ledger_v2",
        "events": [
            {
                "event_id": "event:india",
                "source_id": "yahoo",
                "source_name": "Yahoo Finance QQQ Headlines",
                "source_tier": "reliable_mainstream_report",
                "event_type": "market_news",
                "title": "Apple's India supply-chain bet has hidden risk",
                "published_at": "Fri, 08 May 2026 09:00:00 GMT",
                "symbols": ["AAPL"],
                "raw_text_available": False,
                "url": "https://finance.yahoo.com/example",
            }
        ],
    }

    write_event_narrative_ledger(run_dir, event_ledger=ledger, effective_date="2026-05-08")
    mechanism = json.loads((run_dir / "event_mechanism_report.json").read_text(encoding="utf-8"))

    assert mechanism["news_cards"][0]["mainline_id"] != "ai_semiconductor_earnings"


def test_integrated_synthesis_report_blocks_formal_conclusion_when_data_integrity_blocks():
    pure_data = {"schema_version": "pure_data_report_v1", "principal_contradictions": []}
    event_ledger = EventNarrativeLedgerBuilder().build(
        event_ledger=_event_ledger(),
        news_layer_analysis=_news_analysis(),
        news_event_data_links=_data_links(),
        effective_date="2026-05-08",
    )

    payload = IntegratedSynthesisReportBuilder().build(
        pure_data_report=pure_data,
        event_narrative_ledger=event_ledger,
        data_integrity_report={"publish_status": "blocked", "blocking_reasons": ["no_indicators_collected"]},
    )

    assert payload["publish_gate"]["status"] == "audit_only"
    assert payload["publish_gate"]["formal_investment_conclusion_allowed"] is False
    assert payload["integrated_judgments"][0]["explanation_grade"] == "not_explained"
    assert payload["unexplained_items"][0]["item"] == "data_integrity_blocked"


def test_integrated_synthesis_report_downgrades_event_claims_without_data_confirmation(tmp_path: Path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    pure_path = run_dir / "pure_data_report.json"
    event_path = run_dir / "event_narrative_ledger.json"
    integrity_path = run_dir / "data_integrity_report.json"
    pure_path.write_text(
        json.dumps(
            {
                "schema_version": "pure_data_report_v1",
                "principal_contradictions": [
                    {"evidence_refs": ["L1.get_10y_real_rate", "L4.get_ndx_wind_valuation_snapshot"]}
                ],
            }
        ),
        encoding="utf-8",
    )
    event_path.write_text(json.dumps(EventNarrativeLedgerBuilder().build(event_ledger=_event_ledger(), effective_date="2026-05-08")), encoding="utf-8")
    integrity_path.write_text(json.dumps({"publish_status": "publishable"}), encoding="utf-8")

    output = write_integrated_synthesis_report(run_dir)
    payload = json.loads(Path(output).read_text(encoding="utf-8"))

    assert payload["publish_gate"]["status"] == "publishable_integrated_report"
    assert payload["integrated_judgments"][0]["explanation_grade"] == "integrated_explanation"
    assert payload["integrated_judgments"][0]["data_support"] == [
        "L1.get_10y_real_rate",
        "L4.get_ndx_wind_valuation_snapshot",
    ]
    assert payload["downgraded_claims"][0]["downgraded_to"] == "plausible_hypothesis"


def test_integrated_synthesis_report_reads_event_mechanism_report():
    pure_data = {
        "schema_version": "pure_data_report_v1",
        "principal_contradictions": [{"evidence_refs": ["L1.get_10y_real_rate"]}],
    }
    event_ledger = EventNarrativeLedgerBuilder().build(
        event_ledger=_event_ledger(),
        effective_date="2026-05-08",
    )
    mechanism = {
        "schema_version": "event_mechanism_report_v1",
        "headline_judgment": {
            "title": "新闻事件初步判断",
            "plain_text": "新闻只能作为解释线索。",
            "confidence": "low",
            "cannot_be_used_as_primary_evidence": True,
        },
        "mainlines": [{"mainline_id": "macro_rate_valuation_pressure", "title": "宏观约束有没有被市场低估？"}],
        "cross_layer_questions": [{"direction": "event_to_data", "question": "利率是否确认？"}],
        "delivery_to_integrated_report": {
            "one_sentence": "新闻事件暂时不支持高把握看多。",
            "watchlist": ["实际利率"],
        },
    }

    payload = IntegratedSynthesisReportBuilder().build(
        pure_data_report=pure_data,
        event_narrative_ledger=event_ledger,
        event_mechanism_report=mechanism,
        data_integrity_report={"publish_status": "publishable"},
    )

    assert payload["event_mechanism_report"]["headline_judgment"]["title"] == "新闻事件初步判断"
    assert payload["event_mechanism_report"]["delivery_to_integrated_report"]["one_sentence"] == "新闻事件暂时不支持高把握看多。"


def test_pure_data_report_manifest_declares_forbidden_event_inputs(tmp_path: Path):
    output = tmp_path / "pure_data_report.json"
    payload = build_pure_data_report_manifest(
        run_dir=tmp_path,
        data_integrity_report={"publish_status": "publishable"},
        output_path=output,
    )

    assert output.exists()
    assert payload["schema_version"] == "pure_data_report_v1"
    assert payload["prompt_policy"]["data_only"] is True
    assert "event_refs" in payload["prompt_policy"]["forbidden_runtime_inputs"]
    assert "event_mechanism_report" in payload["prompt_policy"]["forbidden_runtime_inputs"]
    assert "cross_layer_questions" in payload["prompt_policy"]["forbidden_runtime_inputs"]
