import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent_analysis.outcome_review import build_claim_outcome_scores, build_outcome_review_report


def _price_rows(start="2025-04-09", count=260, start_close=100.0, daily_step=0.2):
    # Synthetic trading-day-like rows are enough for contract tests; dates only need stable ordering.
    rows = []
    year, month, day = [int(part) for part in start.split("-")]
    for index in range(count):
        rows.append({"date": f"{year:04d}-{month:02d}-{day + index:02d}", "close": start_close + index * daily_step})
    return rows


def test_outcome_review_flags_caution_after_strong_follow_through_rally():
    report = build_outcome_review_report(
        run_dir="",
        backtest_date="2025-04-09",
        final_adjudication={
            "final_stance": "中性偏谨慎",
            "reader_final": {"one_liner": "风险仍高，等待确认。"},
        },
        price_rows=_price_rows(daily_step=0.3),
    )

    assert report.review_mode == "post_hoc_outcome_review"
    assert report.market_outcome_label == "strong_follow_through_rally"
    assert any(window.window == "+12m" and window.return_pct is not None for window in report.windows)
    assert "过度谨慎" in report.caution_review or "确认成本" in report.caution_review
    assert report.leakage_boundary.startswith("Outcome Review is generated only after Final")


def test_outcome_review_flags_aggression_after_selloff():
    report = build_outcome_review_report(
        run_dir="",
        backtest_date="2025-04-09",
        final_adjudication={
            "final_stance": "高赔率进攻",
            "reader_final": {"one_liner": "可以加大进攻。"},
        },
        price_rows=_price_rows(daily_step=-0.25),
    )

    assert report.market_outcome_label == "material_follow_through_selloff"
    assert "过度冒进" in report.aggression_review


def test_claim_outcome_scores_use_final_claim_ledger_and_source_tiers():
    ledger = {
        "entries": [
            {
                "claim_id": "claim:final:buy",
                "source_stage": "final",
                "claim_type": "timing",
                "claim_text": "趋势未破坏，可以小幅进攻。",
                "evidence_refs": ["L5.get_qqq_technical_indicators"],
            },
            {
                "claim_id": "claim:final:risk",
                "source_stage": "final",
                "claim_type": "risk_boundary",
                "claim_text": "风险边界仍需保留。",
                "evidence_refs": ["L2.get_vix"],
            },
        ]
    }
    registry = {
        "passports": {
            "L5.get_qqq_technical_indicators": {"source_tier": "formal_data_source"},
            "L2.get_vix": {"source_tier": "official"},
        }
    }

    payload = build_claim_outcome_scores(
        final_claim_ledger=ledger,
        price_rows=_price_rows(daily_step=0.25),
        backtest_date="2025-04-09",
        evidence_registry=registry,
    )

    assert payload["scores"][0]["verdict"] == "consistent"
    assert payload["scores"][0]["scoring_evidence"]["windows"][0]["window"] == "T+20"
    assert payload["scores"][1]["verdict"] == "falsifier_triggered"
    assert payload["summary"]["by_claim_type"]["timing"]["consistent"] == 1
    assert payload["summary"]["by_source_tier"]["official"]["falsifier_triggered"] == 1


def test_outcome_review_embeds_claim_scores_when_ledger_provided():
    report = build_outcome_review_report(
        run_dir="",
        backtest_date="2025-04-09",
        final_adjudication={"final_stance": "中性"},
        final_claim_ledger={
            "entries": [
                {
                    "claim_id": "claim:final:risk",
                    "source_stage": "final",
                    "claim_type": "risk_boundary",
                    "claim_text": "风险边界仍需保留。",
                    "evidence_refs": ["L2.get_vix"],
                }
            ]
        },
        evidence_registry={"passports": {"L2.get_vix": {"source_tier": "official"}}},
        price_rows=_price_rows(daily_step=-0.2),
    )

    assert report.claim_outcome_scores
    assert report.claim_outcome_scores[0]["verdict"] == "consistent"
    assert report.claim_outcome_score_summary["by_claim_type"]["risk_boundary"]["consistent"] == 1
