# -*- coding: utf-8 -*-
"""词表活化机制（T67/W7）单测：候选收集 / 增量词合并 / 双账留痕 / 三账闸门。

边界归老板：机器只出候选不出决定——测试锁定"未圈选=行为与历史一致"与
"圈选后增量生效、全程留痕"两条主线。
"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from event_research import term_activation as ta


def _write_json(path: Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def _mk_run_dir(tmp_path: Path) -> Path:
    run_dir = tmp_path / "run_001"
    run_dir.mkdir()
    return run_dir


def _clear_override_cache() -> None:
    ta.load_keyword_overrides._cache = None  # type: ignore[attr-defined]


# --------------------------------------------------------------------------
# 第 1 步：候选收集（机械搬运，幂等）
# --------------------------------------------------------------------------

def test_collect_term_candidates_harvests_two_sources(tmp_path):
    run_dir = _mk_run_dir(tmp_path)
    _write_json(run_dir / "narrative_state.json", {
        "absence_signals": [
            "官方对某事件的澄清声明至今缺席",
            "",   # 空串必须被滤掉
            "  首席财务官交接的正式公告缺席  ",
        ],
    })
    _write_json(run_dir / "research_topics.json", {
        "data_gaps": ["90日盈利修正数据验证状态缺失"],
    })

    result = ta.collect_term_candidates(run_dir, ledger_path=tmp_path / "cand.jsonl")
    assert result["status"] == "ok"
    assert result["candidates_added"] == 3
    assert result["by_source"] == {"absence_signal": 2, "topic_data_gap": 1}
    records = ta.load_candidates(tmp_path / "cand.jsonl")
    raws = {r["raw_text"] for r in records}
    assert "官方对某事件的澄清声明至今缺席" in raws
    # 收集时做空白规范化
    assert any(r["raw_text"] == "首席财务官交接的正式公告缺席" and r["source"] == "absence_signal" for r in records)


def test_collect_term_candidates_is_idempotent(tmp_path):
    run_dir = _mk_run_dir(tmp_path)
    _write_json(run_dir / "research_topics.json", {"data_gaps": ["缺口甲", "缺口乙"]})
    ledger = tmp_path / "cand.jsonl"

    first = ta.collect_term_candidates(run_dir, ledger_path=ledger)
    second = ta.collect_term_candidates(run_dir, ledger_path=ledger)
    assert first["candidates_added"] == 2
    assert second["status"] == "ok"
    assert second["candidates_added"] == 0
    assert second["skipped_duplicates"] == 2


def test_collect_term_candidates_truncates_long_sentences(tmp_path):
    run_dir = _mk_run_dir(tmp_path)
    long_sentence = "很" * 500
    _write_json(run_dir / "narrative_state.json", {"absence_signals": [long_sentence]})
    result = ta.collect_term_candidates(run_dir, ledger_path=tmp_path / "cand.jsonl")
    assert result["candidates_added"] == 1
    record = ta.load_candidates(tmp_path / "cand.jsonl")[0]
    assert len(record["raw_text"]) == ta.MAX_RAW_TEXT_LEN


def test_collect_term_candidates_skips_when_no_sources(tmp_path):
    run_dir = _mk_run_dir(tmp_path)
    result = ta.collect_term_candidates(run_dir, ledger_path=tmp_path / "cand.jsonl")
    assert result["status"] == "skipped"
    assert result["reason"] == "no_candidate_sources"


def test_collect_term_candidates_survives_corrupt_artifacts(tmp_path):
    run_dir = _mk_run_dir(tmp_path)
    (run_dir / "narrative_state.json").write_text("{broken json", encoding="utf-8")
    result = ta.collect_term_candidates(run_dir, ledger_path=tmp_path / "cand.jsonl")
    assert result["status"] in ("skipped", "ok")   # 坏产物不抛异常即合格


# --------------------------------------------------------------------------
# 第 2 步：增量词表读取与合并
# --------------------------------------------------------------------------

def test_load_keyword_overrides_missing_file_means_disabled(tmp_path):
    overrides = ta.load_keyword_overrides(tmp_path / "none.json")
    assert overrides == {"pool": [], "body_fetch": []}


def test_load_keyword_overrides_sorts_and_normalizes(tmp_path):
    path = tmp_path / "overrides.json"
    _write_json(path, {"schema_version": "keyword_table_overrides_v1", "terms": [
        {"term": "Robotaxi", "use": "body_fetch"},
        {"term": "ROBOTAXI", "use": "body_fetch"},      # 同词去重（大小写规范后）
        {"term": "quantum computing", "use": "pool"},
        {"term": "", "use": "pool"},                     # 空词忽略
        {"term": "x", "use": "track_only"},              # 非法 use 忽略
    ]})
    _clear_override_cache()
    overrides = ta.load_keyword_overrides(path)
    assert overrides == {"pool": ["quantum computing"], "body_fetch": ["robotaxi"]}
    _clear_override_cache()


def test_load_keyword_overrides_cache_invalidates_on_mtime_change(tmp_path):
    path = tmp_path / "overrides.json"
    path.write_text(json.dumps({"terms": [{"term": "aaa", "use": "pool"}]}), encoding="utf-8")
    _clear_override_cache()
    assert ta.load_keyword_overrides(path)["pool"] == ["aaa"]
    future = time.time() + 10
    import os
    os.utime(path, (future, future))
    path.write_text(json.dumps({"terms": [{"term": "bbb", "use": "body_fetch"}]}), encoding="utf-8")
    assert ta.load_keyword_overrides(path)["pool"] == []
    assert ta.load_keyword_overrides(path)["body_fetch"] == ["bbb"]
    _clear_override_cache()


# --------------------------------------------------------------------------
# 第 3 步：圈选双账（adopt / reject / remove）
# --------------------------------------------------------------------------

def _seed_candidate(tmp_path, text="官方澄清声明缺席"):
    from event_research.term_activation import _append_record, _candidate_id
    ledger = tmp_path / "cand.jsonl"
    _append_record({
        "record_type": "candidate",
        "candidate_id": _candidate_id(text),
        "raw_text": text,
        "source": "absence_signal",
        "suggested_use": "manual_review",
        "status": "candidate",
        "proposed_at_utc": "2026-08-27T00:00:00+00:00",
    }, ledger)
    return ledger, _candidate_id(text)


def test_adopt_term_writes_both_ledgers_atomically(tmp_path):
    cand_path, cid = _seed_candidate(tmp_path)
    ov_path = tmp_path / "overrides.json"
    log_path = tmp_path / "change_log.jsonl"

    change = ta.adopt_term(cid, "澄清声明", "body_fetch",
                           candidates_path=cand_path, overrides_path=ov_path, change_log_path=log_path)
    assert change["action"] == "adopt"

    doc = json.loads(ov_path.read_text(encoding="utf-8"))
    assert [(t["term"], t["use"]) for t in doc["terms"]] == [("澄清声明", "body_fetch")]
    assert doc["terms"][0]["decided_by"] == "owner"
    log_lines = [json.loads(l) for l in log_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    assert len(log_lines) == 1 and log_lines[0]["action"] == "adopt"
    statuses = [r for r in ta.load_candidates(cand_path) if r["candidate_id"] == cid]
    assert statuses[0]["status"] == "adopted"


def test_adopt_term_same_word_same_use_is_idempotent_in_overrides(tmp_path):
    _, cid = _seed_candidate(tmp_path)
    ov_path = tmp_path / "overrides.json"
    kwargs = dict(candidates_path=tmp_path / "cand.jsonl", overrides_path=ov_path,
                  change_log_path=tmp_path / "change_log.jsonl")
    ta.adopt_term(cid, "澄清声明", "pool", **kwargs)
    ta.adopt_term(cid, "澄清声明", "pool", **kwargs)
    doc = json.loads(ov_path.read_text(encoding="utf-8"))
    assert len(doc["terms"]) == 1


def test_adopt_term_validates_inputs(tmp_path):
    _, cid = _seed_candidate(tmp_path)
    kwargs = dict(candidates_path=tmp_path / "cand.jsonl", overrides_path=tmp_path / "o.json",
                  change_log_path=tmp_path / "log.jsonl")
    try:
        ta.adopt_term("tc_ghost", "词", "pool", **kwargs)
        raise AssertionError("应当拒绝不存在的 candidate_id")
    except ValueError as exc:
        assert "tc_ghost" in str(exc)
    try:
        ta.adopt_term(cid, "词", "track_only", **kwargs)
        raise AssertionError("应当拒绝非法 use")
    except ValueError:
        pass


def test_reject_term_marks_never_revive_and_logs(tmp_path):
    cand_path, cid = _seed_candidate(tmp_path)
    change = ta.reject_term(cid, candidates_path=cand_path, change_log_path=tmp_path / "log.jsonl")
    assert change["action"] == "reject"
    assert ta.load_candidates(cand_path)[0]["status"] == "rejected"


def test_remove_term_deletes_override_and_logs(tmp_path):
    _, cid = _seed_candidate(tmp_path)
    ov_path = tmp_path / "overrides.json"
    kwargs = dict(candidates_path=tmp_path / "cand.jsonl", overrides_path=ov_path,
                  change_log_path=tmp_path / "change_log.jsonl")
    ta.adopt_term(cid, "旧词", "body_fetch", **kwargs)
    change = ta.remove_term("旧词", "body_fetch", overrides_path=ov_path,
                            change_log_path=tmp_path / "change_log.jsonl")
    assert change["removed_existed"] is True
    assert json.loads(ov_path.read_text(encoding="utf-8"))["terms"] == []


# --------------------------------------------------------------------------
# 第 4 步：三账闸门 verify_keyword_ledgers
# --------------------------------------------------------------------------

def test_verify_returns_none_when_mechanism_disabled(tmp_path):
    assert ta.verify_keyword_ledgers(
        candidates_path=tmp_path / "a.jsonl",
        overrides_path=tmp_path / "b.json",
        change_log_path=tmp_path / "c.jsonl",
    ) is None


def test_verify_passes_consistent_ledgers(tmp_path):
    _, cid = _seed_candidate(tmp_path)
    kwargs = dict(candidates_path=tmp_path / "cand.jsonl", overrides_path=tmp_path / "o.json",
                  change_log_path=tmp_path / "log.jsonl")
    ta.adopt_term(cid, "澄清声明", "body_fetch", **kwargs)
    problems = ta.verify_keyword_ledgers(**kwargs)
    assert problems is None


def test_verify_catches_silent_override_edit(tmp_path):
    _, cid = _seed_candidate(tmp_path)
    ov_path = tmp_path / "o.json"
    _write_json(ov_path, {"schema_version": "keyword_table_overrides_v1", "terms": [
        {"term": "偷偷加的词", "use": "pool", "decided_by": "nobody"},
    ]})
    problems = ta.verify_keyword_ledgers(
        candidates_path=tmp_path / "cand.jsonl", overrides_path=ov_path,
        change_log_path=tmp_path / "log.jsonl")
    assert problems and any("静默增删嫌疑" in p for p in problems)


def test_verify_catches_ghost_candidate_ref_and_bad_shape(tmp_path):
    cand_path, _ = _seed_candidate(tmp_path)
    log_path = tmp_path / "log.jsonl"
    ta._append_record({"action": "reject", "candidate_id": "tc_nope", "logged_at_utc": ""}, log_path)
    problems = ta.verify_keyword_ledgers(
        candidates_path=cand_path, overrides_path=tmp_path / "missing.json", change_log_path=log_path)
    joined = ";".join(problems or [])
    assert "candidate_id 不存在" in joined
    assert "缺 logged_at_utc" in joined
    assert "action 非法" not in joined   # reject 是合法 action


# --------------------------------------------------------------------------
# 消费端：news_event_ledger 合并判定随 override 生效/失效
# --------------------------------------------------------------------------

def test_news_event_ledger_consumes_overrides(monkeypatch, tmp_path):
    import news_event_ledger as nel

    _clear_override_cache()
    monkeypatch.setattr(nel, "load_keyword_overrides",
                        lambda: {"pool": ["robotaxi"], "body_fetch": ["quantumcompute"]})
    builder = nel.NewsEventLedgerBuilder()
    # 未启用前抓不到正文的标题，增量词进来后命中
    assert builder._should_fetch_article_body("QuantumCompute milestone announced",
                                              "https://example.com/a") is True
    assert builder._should_fetch_article_body("Unrelated sports score", "https://example.com/b") is False
    # pool 用途：相关度打分升 high
    title_l = "robotaxi expansion slows".lower()
    assert any(k in title_l for k in nel._merged_pool_keywords()) is True
    _clear_override_cache()


def test_news_event_ledger_without_overrides_matches_legacy_behavior():
    import news_event_ledger as nel

    _clear_override_cache()
    builder = nel.NewsEventLedgerBuilder()
    assert builder._should_fetch_article_body("Robotaxi expansion slows",
                                              "https://example.com/a") is False
    title_l = "robotaxi expansion slows".lower()
    assert any(k in title_l for k in nel._merged_pool_keywords()) is False
    _clear_override_cache()
