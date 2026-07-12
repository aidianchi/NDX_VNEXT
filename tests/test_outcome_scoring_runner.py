import json
import os
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent_analysis import outcome_scoring_runner as osr


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _make_run_dir(
    root: Path,
    run_id: str,
    *,
    backtest_date: str,
    entries: list,
    data_date: str | None = None,
) -> Path:
    run_dir = root / run_id
    meta = {}
    if backtest_date:
        meta["backtest_date"] = backtest_date
    if data_date:
        meta["data_date"] = data_date
    _write_json(run_dir / "analysis_packet.json", {"meta": meta})
    _write_json(run_dir / "final_claim_ledger.json", {"entries": entries})
    _write_json(
        run_dir / "evidence_registry.json",
        {"passports": {"L5.get_qqq_technical_indicators": {"source_tier": "formal_data_source"}}},
    )
    return run_dir


def _declining_price_rows(start: str, count: int, start_close: float = 100.0, daily_step: float = -1.0) -> list:
    """count 条合成行情行，按 list 下标当交易日偏移量用（不依赖真实日历/周末）。"""
    year, month, day = [int(part) for part in start.split("-")]
    base = date(year, month, day)
    rows = []
    for index in range(count):
        d = base.toordinal() + index
        rows.append({"date": date.fromordinal(d).isoformat(), "close": start_close + index * daily_step})
    return rows


BULLISH_CLAIM = {
    "claim_id": "claim:final:buy",
    "source_stage": "final",
    "claim_type": "timing",
    "claim_text": "趋势未破坏，可以小幅进攻。",
    "evidence_refs": ["L5.get_qqq_technical_indicators"],
}

BEARISH_CLAIM = {
    "claim_id": "claim:final:risk",
    "source_stage": "final",
    "claim_type": "risk_boundary",
    "claim_text": "风险边界仍需保留。",
    "evidence_refs": ["L2.get_vix"],
}


def test_score_run_marks_unrealized_windows_pending_and_scores_available_window(tmp_path, monkeypatch):
    """T+20 已实现（25 行情行覆盖到 idx 20），T+60/T+120 尚未到期：必须如实 pending，
    不得对未到期窗口编造 consistent/falsifier 结论。"""
    run_dir = _make_run_dir(
        tmp_path,
        "run_pending_demo",
        backtest_date="2025-01-06",
        entries=[BULLISH_CLAIM, BEARISH_CLAIM],
    )
    price_rows = _declining_price_rows("2025-01-06", count=25, daily_step=-1.0)
    monkeypatch.setattr(osr, "_fetch_qqq_rows", lambda backtest_date, ticker="QQQ": (price_rows, "fixture_fake_source"))

    result = osr.score_run(run_dir, min_age_days=20, as_of=date(2025, 2, 5))

    assert result["status"] == "scored"
    doc = result["claim_outcome_scores"]

    assert doc["pending_windows"] == ["T+120", "T+60"]
    window_status = {w["window"]: w["data_status"] for w in doc["windows"]}
    assert window_status["T+20"] == "available"
    assert window_status["T+60"] == "incomplete"
    assert window_status["T+120"] == "incomplete"

    # A falling price path falsifies the bullish claim off T+20 alone (falsifier bar is single-window),
    # but the bearish/risk claim is genuinely confirmed by the same falling T+20 window.
    verdicts = {s["claim_id"]: s["verdict"] for s in doc["scores"]}
    assert verdicts["claim:final:buy"] == "falsifier_triggered"
    assert verdicts["claim:final:risk"] == "consistent"
    assert doc["verdict_totals"] == {"consistent": 1, "falsifier_triggered": 1, "not_scorable": 0}

    # Honesty requirement B: every score carries a data-quality caveat, no fabricated confidence.
    for score in doc["scores"]:
        assert score["data_quality_caveat"] == osr.DATA_QUALITY_CAVEAT

    on_disk = json.loads((run_dir / "claim_outcome_scores.json").read_text(encoding="utf-8"))
    assert on_disk == doc


def test_score_run_skips_runs_younger_than_min_age(tmp_path, monkeypatch):
    run_dir = _make_run_dir(
        tmp_path,
        "run_too_young",
        backtest_date="2025-01-30",
        entries=[BEARISH_CLAIM],
    )
    called = {"count": 0}

    def _boom(*args, **kwargs):
        called["count"] += 1
        raise AssertionError("must not fetch prices for a run that fails the age gate")

    monkeypatch.setattr(osr, "_fetch_qqq_rows", _boom)

    result = osr.score_run(run_dir, min_age_days=20, as_of=date(2025, 2, 5))  # 6 calendar days old

    assert result["status"] == "skipped_too_young"
    assert called["count"] == 0
    assert not (run_dir / "claim_outcome_scores.json").exists()


def test_batch_run_is_idempotent_no_duplicate_ledger_rows(tmp_path, monkeypatch):
    root = tmp_path / "vnext"
    run_dir = _make_run_dir(
        root,
        "run_idempotent_demo",
        backtest_date="2025-01-06",
        entries=[BEARISH_CLAIM],
    )
    price_rows = _declining_price_rows("2025-01-06", count=25, daily_step=-1.0)
    monkeypatch.setattr(osr, "_fetch_qqq_rows", lambda backtest_date, ticker="QQQ": (price_rows, "fixture_fake_source"))

    ledger_path = tmp_path / "ledger" / "claim_outcome_ledger.jsonl"
    as_of = date(2025, 2, 5)

    first = osr.run_score_outcomes_batch(root, min_age_days=20, as_of=as_of, ledger_path=ledger_path)
    second = osr.run_score_outcomes_batch(root, min_age_days=20, as_of=as_of, ledger_path=ledger_path)

    assert first["scored_run_count"] == 1
    assert second["scored_run_count"] == 1

    lines = [json.loads(line) for line in ledger_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert len(lines) == 1
    assert lines[0]["run_id"] == "run_idempotent_demo"
    assert lines[0]["verdict_totals"] == {"consistent": 1, "falsifier_triggered": 0, "not_scorable": 0}

    # Re-running with the same as_of must reproduce the same scoring facts (pending set, verdicts).
    first_doc = json.loads((run_dir / "claim_outcome_scores.json").read_text(encoding="utf-8"))
    assert first_doc["pending_windows"] == ["T+120", "T+60"]
    assert first_doc["verdict_totals"] == {"consistent": 1, "falsifier_triggered": 0, "not_scorable": 0}


def test_discover_candidate_run_dirs_requires_final_claim_ledger(tmp_path):
    root = tmp_path / "vnext"
    with_ledger = _make_run_dir(root, "has_ledger", backtest_date="2025-01-06", entries=[BEARISH_CLAIM])
    without_ledger_dir = root / "no_ledger"
    _write_json(without_ledger_dir / "analysis_packet.json", {"meta": {"backtest_date": "2025-01-06"}})
    (without_ledger_dir / "final_claim_ledger.json").unlink(missing_ok=True)

    candidates = osr.discover_candidate_run_dirs(root)

    assert with_ledger in candidates
    assert without_ledger_dir not in candidates


def test_score_run_returns_error_status_instead_of_raising_on_fetch_failure(tmp_path, monkeypatch):
    run_dir = _make_run_dir(
        tmp_path,
        "run_fetch_failure",
        backtest_date="2025-01-06",
        entries=[BEARISH_CLAIM],
    )

    def _raise(*args, **kwargs):
        raise RuntimeError("simulated network outage")

    monkeypatch.setattr(osr, "_fetch_qqq_rows", _raise)

    result = osr.score_run(run_dir, min_age_days=20, as_of=date(2025, 2, 5))

    assert result["status"] == "error"
    assert "simulated network outage" in result["error"]
    assert not (run_dir / "claim_outcome_scores.json").exists()

    # A batch containing only this failing run must not raise either.
    summary = osr.run_score_outcomes_batch(tmp_path, min_age_days=20, as_of=date(2025, 2, 5))
    assert summary["status_counts"].get("error") == 1
    assert summary["scored_run_count"] == 0


def test_resolve_run_kind_and_effective_date_distinguish_backtest_from_live(tmp_path):
    backtest_dir = _make_run_dir(tmp_path, "bt", backtest_date="2025-01-06", entries=[])
    live_dir = tmp_path / "live_run"
    _write_json(live_dir / "analysis_packet.json", {"meta": {"data_date": "2025-01-06"}})
    _write_json(live_dir / "final_claim_ledger.json", {"entries": []})

    assert osr.resolve_run_kind(backtest_dir) == "backtest"
    assert osr.resolve_run_effective_date(backtest_dir) == "2025-01-06"
    assert osr.resolve_run_kind(live_dir) == "live"
    assert osr.resolve_run_effective_date(live_dir) == "2025-01-06"


def test_score_run_skips_empty_claim_ledger(tmp_path, monkeypatch):
    run_dir = _make_run_dir(tmp_path, "run_empty_ledger", backtest_date="2025-01-06", entries=[])
    monkeypatch.setattr(
        osr,
        "_fetch_qqq_rows",
        lambda *a, **k: (_ for _ in ()).throw(AssertionError("must not fetch prices when there are no claims")),
    )

    result = osr.score_run(run_dir, min_age_days=20, as_of=date(2025, 2, 5))

    assert result["status"] == "skipped_empty_claim_ledger"
