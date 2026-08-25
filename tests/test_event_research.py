# -*- coding: utf-8 -*-
"""src/event_research/ 事件层二档研究部的单元测试。

全部离线：agenda/budget/reconcile/runner 纯函数用 tmp_path 合成数据；
hooks 用 subprocess 起脚本进程，喂合成 stdin 载荷，不触真实 dsh、不联网。
"""

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
HOOKS_DIR = REPO_ROOT / "src" / "event_research" / "hooks"

from src.event_research import agenda as agenda_mod
from src.event_research import budget as budget_mod
from src.event_research import card as card_mod
from src.event_research import reconcile as reconcile_mod
from src.event_research import runner as runner_mod


# ---------------------------------------------------------------------------
# 合成数据工具
# ---------------------------------------------------------------------------

def _write_jsonl(path: Path, lines) -> Path:
    """lines 元素可以是 dict（序列化）或 str（原样写入，用于坏行）。"""
    with path.open("w", encoding="utf-8") as f:
        for line in lines:
            if isinstance(line, str):
                f.write(line + "\n")
            else:
                f.write(json.dumps(line, ensure_ascii=False) + "\n")
    return path


def _usage_event(input_tokens=0, output_tokens=0, cache_read=0, cache_write=0):
    return {
        "type": "assistant/message",
        "data": {
            "usage": {
                "inputTokens": input_tokens,
                "outputTokens": output_tokens,
                "cacheReadTokens": cache_read,
                "cacheWriteTokens": cache_write,
            }
        },
    }


def _tool_call(call_id, name, url):
    return {
        "type": "tool/call",
        "data": {
            "callId": call_id,
            "name": name,
            # dsh 落盘里 arguments 是 JSON 字符串
            "arguments": json.dumps({"url": url}, ensure_ascii=False),
        },
    }


def _tool_result(call_id, text):
    return {
        "type": "tool/result",
        "data": {
            "callId": call_id,
            "message": {"content": [{"type": "text", "text": text}]},
        },
    }


# 对账用小号白名单（不读真 config）
MINI_WHITELIST = {
    "tiers": {
        "official": ["sec.gov"],
        "mainstream_finance": ["reuters.com"],
        "transcript": ["fool.com"],
        "sell_side": ["goldmansachs.com"],
        "social": ["x.com"],
    }
}


def _valid_card():
    """原型 9 字段 + governance_note + 合法 source_pointer，应零错误。"""
    return {
        "card_id": "card-1",
        "agenda_id": "EV-20260801-abcdef",
        "fact_summary": "美联储在 2026 年 1 月议息会议维持联邦基金利率不变。",
        "interpretation": "假设该立场延续到下次会议，则对 NDX 的贴现率压力中性。",
        "source_tier": "official",
        "source_url": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260128a.htm",
        "collected_at_utc": "2026-08-01T00:00:00+00:00",
        "needs_data_confirmation": ["用第一层利率数据复核会议决议"],
        "limitations": ["单一官方来源"],
        "governance_note": card_mod.GOVERNANCE_NOTE,
        "source_pointer": {"url": "https://www.federalreserve.gov/newsevents/pressreleases/monetary20260128a.htm",
                           "quote": "维持联邦基金利率不变"},
    }


FIXED_NOW = datetime(2026, 8, 20, tzinfo=timezone.utc)


def _run_hook(script_name: str, payload: dict) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(HOOKS_DIR / script_name)],
        input=json.dumps(payload, ensure_ascii=False) + "\n",
        capture_output=True,
        text=True,
        timeout=60,
    )


# ---------------------------------------------------------------------------
# 1. agenda：议程账本
# ---------------------------------------------------------------------------

class TestAgenda:
    def test_initial_status_by_source(self, tmp_path):
        ledger = tmp_path / "agenda.jsonl"
        charter = agenda_mod.append_agenda("宪章巡逻题", "charter", ["①已发生的事"], ledger_path=ledger)
        gap = agenda_mod.append_agenda("底账缺口题", "gap", ["①已发生的事"], ledger_path=ledger)
        boss = agenda_mod.append_agenda("老板命题", "boss", ["①已发生的事"], ledger_path=ledger)
        assert charter["status"] == "active"
        assert gap["status"] == "candidate"
        assert boss["status"] == "active"

    def test_current_agendas_fold(self, tmp_path):
        ledger = tmp_path / "agenda.jsonl"
        a = agenda_mod.append_agenda("题一", "charter", ["①已发生的事"], ledger_path=ledger)
        b = agenda_mod.append_agenda("题二", "gap", ["②将发生的事"], ledger_path=ledger)
        folded = agenda_mod.current_agendas(ledger)
        assert set(folded) == {a["agenda_id"], b["agenda_id"]}
        assert folded[a["agenda_id"]]["question"] == "题一"
        assert folded[b["agenda_id"]]["status"] == "candidate"

    def test_status_change_overrides(self, tmp_path):
        ledger = tmp_path / "agenda.jsonl"
        gap = agenda_mod.append_agenda("待激活", "gap", ["①已发生的事"], ledger_path=ledger)
        agenda_mod.append_status_change(gap["agenda_id"], "active", note="老板激活", ledger_path=ledger)
        current = agenda_mod.get_agenda(gap["agenda_id"], ledger)
        assert current["status"] == "active"
        assert current["status_notes"] == ["老板激活"]

    def test_invalid_source_raises(self, tmp_path):
        with pytest.raises(ValueError):
            agenda_mod.append_agenda("题", "internet", ["①已发生的事"], ledger_path=tmp_path / "a.jsonl")

    def test_empty_question_raises(self, tmp_path):
        with pytest.raises(ValueError):
            agenda_mod.append_agenda("   ", "charter", ["①已发生的事"], ledger_path=tmp_path / "a.jsonl")

    def test_invalid_material_classes_raises(self, tmp_path):
        with pytest.raises(ValueError):
            agenda_mod.append_agenda("题", "charter", ["⑨不存在的事"], ledger_path=tmp_path / "a.jsonl")
        with pytest.raises(ValueError):
            agenda_mod.append_agenda("题", "charter", [], ledger_path=tmp_path / "a.jsonl")

    def test_non_positive_budget_cap_raises(self, tmp_path):
        for bad in (0, -1):
            with pytest.raises(ValueError):
                agenda_mod.append_agenda("题", "charter", ["①已发生的事"], budget_cap=bad,
                                         ledger_path=tmp_path / "a.jsonl")

    def test_default_budget_cap(self, tmp_path):
        record = agenda_mod.append_agenda("题", "charter", ["①已发生的事"], ledger_path=tmp_path / "a.jsonl")
        assert record["budget_cap"] == 30_000_000

    def test_agenda_ids_unique(self, tmp_path):
        ledger = tmp_path / "a.jsonl"
        a = agenda_mod.append_agenda("题一", "charter", ["①已发生的事"], ledger_path=ledger)
        b = agenda_mod.append_agenda("题二", "charter", ["①已发生的事"], ledger_path=ledger)
        assert a["agenda_id"] != b["agenda_id"]

    def test_tracking_key_recorded_when_given(self, tmp_path):
        ledger = tmp_path / "a.jsonl"
        record = agenda_mod.append_agenda(
            "AI capex 巡逻", "charter", ["③被相信的事"],
            tracking_key="ai_capex", ledger_path=ledger,
        )
        assert record["tracking_key"] == "ai_capex"
        # 折叠后仍在
        folded = agenda_mod.get_agenda(record["agenda_id"], ledger)
        assert folded["tracking_key"] == "ai_capex"

    def test_tracking_key_absent_by_default(self, tmp_path):
        record = agenda_mod.append_agenda("题", "charter", ["①已发生的事"], ledger_path=tmp_path / "a.jsonl")
        assert "tracking_key" not in record


# ---------------------------------------------------------------------------
# 2. budget：经费卡
# ---------------------------------------------------------------------------

class TestBudget:
    def _transcript(self, tmp_path) -> Path:
        return _write_jsonl(tmp_path / "session.jsonl", [
            _usage_event(100, 50, 10, 5),          # 165
            {"type": "tool/call", "data": {}},      # 其他事件类型忽略
            "这不是 JSON 坏行 {",                     # 半截行跳过
            _usage_event(100, 20),                  # 120，缺省缓存字段按 0
            {"type": "assistant/message", "data": "not-a-dict"},   # data 非 dict 忽略
            {"type": "assistant/message", "data": {}},             # 无 usage 忽略
            "",                                                    # 空行跳过
        ])

    def test_fold_usage_sums_assistant_messages(self, tmp_path):
        transcript = self._transcript(tmp_path)
        assert budget_mod.fold_usage_from_transcript(transcript) == 285

    def test_fold_usage_missing_file_returns_zero(self, tmp_path):
        assert budget_mod.fold_usage_from_transcript(tmp_path / "nonexistent.jsonl") == 0

    def test_check_budget_writes_state(self, tmp_path):
        transcript = self._transcript(tmp_path)
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "budget.json").write_text(json.dumps({"budget_cap": 1000}), encoding="utf-8")
        state = budget_mod.check_budget(run_dir, transcript)
        assert state == {"budget_cap": 1000, "spent": 285, "remaining": 715, "exhausted": False}
        # 状态落盘且 read_budget_state 可读回
        on_disk = json.loads((run_dir / "budget_state.json").read_text(encoding="utf-8"))
        assert on_disk == state
        assert budget_mod.read_budget_state(run_dir) == state

    def test_check_budget_exhausted_boundary(self, tmp_path):
        transcript = self._transcript(tmp_path)
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        # spent == cap 即耗尽
        (run_dir / "budget.json").write_text(json.dumps({"budget_cap": 285}), encoding="utf-8")
        assert budget_mod.check_budget(run_dir, transcript)["exhausted"] is True
        # cap - 1 不耗尽
        (run_dir / "budget.json").write_text(json.dumps({"budget_cap": 286}), encoding="utf-8")
        assert budget_mod.check_budget(run_dir, transcript)["exhausted"] is False

    def test_check_budget_missing_card_raises(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            budget_mod.check_budget(tmp_path, tmp_path / "session.jsonl")

    def test_read_budget_state_missing_returns_none(self, tmp_path):
        assert budget_mod.read_budget_state(tmp_path) is None


# ---------------------------------------------------------------------------
# 3. card：材料卡校验
# ---------------------------------------------------------------------------

class TestCard:
    def test_valid_extended_card_passes(self):
        assert card_mod.validate_research_card(_valid_card(), now_utc=FIXED_NOW) == []

    def test_missing_source_pointer(self):
        card = _valid_card()
        del card["source_pointer"]
        assert "source_pointer_missing" in card_mod.validate_research_card(card, now_utc=FIXED_NOW)

    def test_pointer_not_object(self):
        card = _valid_card()
        card["source_pointer"] = "call-1"
        assert "source_pointer_not_object" in card_mod.validate_research_card(card, now_utc=FIXED_NOW)

    def test_empty_url_and_quote(self):
        card = _valid_card()
        card["source_pointer"] = {"url": "  ", "quote": ""}
        errors = card_mod.validate_research_card(card, now_utc=FIXED_NOW)
        assert "source_pointer_url_empty" in errors
        assert "source_pointer_quote_empty" in errors

    def test_unknown_pointer_field(self):
        """call_id 已是旧契约的未知字段（08-24 修订后 pointer 只认 url+quote）。"""
        card = _valid_card()
        card["source_pointer"] = {"url": "https://www.sec.gov/x", "quote": "原文", "call_id": "c1"}
        errors = card_mod.validate_research_card(card, now_utc=FIXED_NOW)
        assert "source_pointer_unknown_field:call_id" in errors

    def test_prototype_hedge_word_still_enforced(self):
        """复用原型校验仍生效：fact_summary 含"可能" → fact_summary_hedge_word:可能。"""
        card = _valid_card()
        card["fact_summary"] = "美联储可能在下一次会议降息。"
        errors = card_mod.validate_research_card(card, now_utc=FIXED_NOW)
        assert "fact_summary_hedge_word:可能" in errors

    def test_card_not_object(self):
        assert card_mod.validate_research_card("not a dict") == ["card_not_object"]

    def test_optional_fields_present_and_valid(self):
        """G4 可选字段：falsification / counter_one_liner 出现且非空 → 零错误，
        且不再触发原型校验器的 unknown_field。"""
        card = _valid_card()
        card["falsification"] = "若下季 capex 指引下调则改判"
        card["counter_one_liner"] = "最强反方：capex 已透支未来两年需求"
        errors = card_mod.validate_research_card(card, now_utc=FIXED_NOW)
        assert errors == []

    def test_optional_fields_absent_is_fine(self):
        card = _valid_card()
        assert "falsification" not in card and "counter_one_liner" not in card
        assert card_mod.validate_research_card(card, now_utc=FIXED_NOW) == []

    @pytest.mark.parametrize("field", ["falsification", "counter_one_liner"])
    @pytest.mark.parametrize("bad_value", ["", "   ", 123])
    def test_optional_field_empty(self, field, bad_value):
        card = _valid_card()
        card[field] = bad_value
        errors = card_mod.validate_research_card(card, now_utc=FIXED_NOW)
        assert f"optional_field_empty:{field}" in errors

    def test_whitelist_domain_not_rejected_by_prototype_rule(self):
        """source_url 在事件层新白名单（任一档，如 transcript 档 fool.com）时，
        原型的 source_url_domain_not_allowed（写死 9 个官方域）被滤掉。"""
        card = _valid_card()
        card["source_tier"] = "primary_news"
        card["source_url"] = "https://www.fool.com/earnings/call-transcripts/2026/08/01/nvda-q2.aspx"
        errors = card_mod.validate_research_card(card, now_utc=FIXED_NOW)
        assert errors == []
        assert "source_url_domain_not_allowed" not in errors

    def test_quoted_cn_hedge_word_exempt(self):
        """引号豁免（真实事故）：引号内的"可能"是官方原话，不是作者 hedging → 不报。"""
        card = _valid_card()
        card["fact_summary"] = 'NVIDIA 官方博客披露"可能"对单个机会提供最高 25% 残值支持'
        errors = card_mod.validate_research_card(card, now_utc=FIXED_NOW)
        assert "fact_summary_hedge_word:可能" not in errors

    def test_unquoted_cn_hedge_word_still_flagged(self):
        card = _valid_card()
        card["fact_summary"] = "这可能是个泡沫"
        errors = card_mod.validate_research_card(card, now_utc=FIXED_NOW)
        assert "fact_summary_hedge_word:可能" in errors

    def test_quoted_en_hedge_word_exempt(self):
        card = _valid_card()
        card["fact_summary"] = 'reports say spending "could" slow'
        errors = card_mod.validate_research_card(card, now_utc=FIXED_NOW)
        assert "fact_summary_hedge_word_en:could" not in errors

    def test_unquoted_en_hedge_word_still_flagged(self):
        card = _valid_card()
        card["fact_summary"] = "spending could slow"
        errors = card_mod.validate_research_card(card, now_utc=FIXED_NOW)
        assert "fact_summary_hedge_word_en:could" in errors


# ---------------------------------------------------------------------------
# 4. reconcile：对账器
# ---------------------------------------------------------------------------

class TestReconcile:
    def _events(self):
        return [
            _tool_call("call-official", "web_fetch", "https://www.sec.gov/Archives/edgar/x.htm"),
            _tool_result("call-official", "前言。美联储宣布 维持利率 不变。\n后文。"),
            _tool_call("call-sellside", "web_fetch", "https://www.goldmansachs.com/insights/x"),
            _tool_result("call-sellside", "我们预计降息在即。"),
            _tool_call("call-transcript", "web_fetch", "https://www.fool.com/earnings/call-transcripts/x.aspx"),
            _tool_result("call-transcript", "管理层表示资本开支指引维持不变。"),
            _tool_call("call-search", "web_search", "https://www.sec.gov/"),
            _tool_result("call-search", "搜索结果摘要若干条"),
            # 无配对的 result 与缺 callId 的 call 不应崩
            _tool_result("orphan-result", "孤儿"),
            {"type": "tool/call", "data": {"name": "web_fetch"}},
        ]

    def test_index_tool_calls_pairs_call_and_result(self):
        calls = reconcile_mod.index_tool_calls(self._events())
        assert set(calls) == {"call-official", "call-sellside", "call-transcript", "call-search"}
        assert calls["call-official"]["name"] == "web_fetch"
        assert calls["call-official"]["url"] == "https://www.sec.gov/Archives/edgar/x.htm"
        assert "维持利率" in calls["call-official"]["result_text"]
        assert calls["call-search"]["name"] == "web_search"

    # 各抓取记录对应的 url（见 _events）
    URL_OFFICIAL = "https://www.sec.gov/Archives/edgar/x.htm"
    URL_SELLSIDE = "https://www.goldmansachs.com/insights/x"
    URL_TRANSCRIPT = "https://www.fool.com/earnings/call-transcripts/x.aspx"
    URL_SEARCH_ONLY = "https://www.sec.gov/"  # 只被 web_search 碰过，无 web_fetch 记录

    def _card_pointing(self, url, quote):
        return {"source_pointer": {"url": url, "quote": quote}}

    def test_verified_transcript_tier(self):
        """G5 transcript 档（fool.com）可进正文 → verified，映射 source_tier=primary_news。"""
        calls = reconcile_mod.index_tool_calls(self._events())
        card = self._card_pointing(self.URL_TRANSCRIPT, "管理层表示资本开支指引维持不变")
        result = reconcile_mod.reconcile_card(card, calls, MINI_WHITELIST)
        assert result["status"] == reconcile_mod.STATUS_VERIFIED
        assert result["source_tier_expected"] == "primary_news"

    def test_verified_official_domain(self):
        calls = reconcile_mod.index_tool_calls(self._events())
        # quote 与原文有空白差异：去空白子串匹配应命中
        card = self._card_pointing(self.URL_OFFICIAL, "美联储宣布维持利率不变")
        result = reconcile_mod.reconcile_card(card, calls, MINI_WHITELIST)
        assert result["status"] == reconcile_mod.STATUS_VERIFIED
        assert result["source_tier_expected"] == "official"

    def test_verified_when_quote_hits_any_fetch_of_same_url(self):
        """同一 url 被抓多次，quote 只命中其中一条也算 verified。"""
        events = [
            _tool_call("fetch-1", "web_fetch", self.URL_OFFICIAL),
            _tool_result("fetch-1", "第一次抓取的内容，没有那句话。"),
            _tool_call("fetch-2", "web_fetch", self.URL_OFFICIAL),
            _tool_result("fetch-2", "第二次抓取：美联储宣布维持利率不变。"),
        ]
        calls = reconcile_mod.index_tool_calls(events)
        card = self._card_pointing(self.URL_OFFICIAL, "美联储宣布维持利率不变")
        result = reconcile_mod.reconcile_card(card, calls, MINI_WHITELIST)
        assert result["status"] == reconcile_mod.STATUS_VERIFIED

    def test_quote_not_found(self):
        calls = reconcile_mod.index_tool_calls(self._events())
        card = self._card_pointing(self.URL_OFFICIAL, "原文里根本不存在的一句话")
        result = reconcile_mod.reconcile_card(card, calls, MINI_WHITELIST)
        assert result["status"] == reconcile_mod.STATUS_QUOTE_NOT_FOUND

    def test_pointer_missing_url_never_fetched(self):
        calls = reconcile_mod.index_tool_calls(self._events())
        card = self._card_pointing("https://www.sec.gov/never-fetched.htm", "随便")
        result = reconcile_mod.reconcile_card(card, calls, MINI_WHITELIST)
        assert result["status"] == reconcile_mod.STATUS_POINTER_MISSING

    def test_pointer_missing_when_url_only_seen_by_web_search(self):
        """web_search 碰过的 url 不算抓取记录（绑定只认 web_fetch）→ pointer_missing。"""
        calls = reconcile_mod.index_tool_calls(self._events())
        card = self._card_pointing(self.URL_SEARCH_ONLY, "搜索结果摘要")
        result = reconcile_mod.reconcile_card(card, calls, MINI_WHITELIST)
        assert result["status"] == reconcile_mod.STATUS_POINTER_MISSING

    def test_weak_tier_sell_side(self):
        calls = reconcile_mod.index_tool_calls(self._events())
        card = self._card_pointing(self.URL_SELLSIDE, "我们预计降息在即")
        result = reconcile_mod.reconcile_card(card, calls, MINI_WHITELIST)
        assert result["status"] == reconcile_mod.STATUS_WEAK_TIER

    def test_reconcile_cards_pass_rate(self, tmp_path):
        session_root = tmp_path / "sessions"
        (session_root / "s1").mkdir(parents=True)
        _write_jsonl(session_root / "s1" / "session.jsonl", self._events())
        cards = [
            self._card_pointing(self.URL_OFFICIAL, "美联储宣布维持利率不变"),   # verified
            self._card_pointing(self.URL_OFFICIAL, "不存在的引文"),             # quote_not_found
            self._card_pointing("https://www.sec.gov/nope.htm", "随便"),       # pointer_missing
            self._card_pointing(self.URL_SELLSIDE, "我们预计降息在即"),          # weak_tier
        ]
        result = reconcile_mod.reconcile_cards(cards, session_root, MINI_WHITELIST)
        assert result["total"] == 4
        assert result["verified"] == 1
        assert result["pass_rate"] == pytest.approx(0.25)
        assert all("reconciliation" in c for c in result["cards"])

    def test_reconcile_cards_empty(self, tmp_path):
        result = reconcile_mod.reconcile_cards([], tmp_path, MINI_WHITELIST)
        assert result["total"] == 0
        assert result["pass_rate"] is None


# ---------------------------------------------------------------------------
# 5. hooks：subprocess 跑桥协议
# ---------------------------------------------------------------------------

class TestFetchGate:
    def _payload(self, url):
        return {"hook_event_name": "PreToolUse", "tool_input": {"url": url}}

    def test_whitelisted_https_passes_silently(self):
        proc = _run_hook("fetch_gate.py", self._payload("https://www.sec.gov/cgi-bin/browse-edgar"))
        assert proc.returncode == 0
        assert proc.stdout.strip() == ""

    def test_http_denied(self):
        proc = _run_hook("fetch_gate.py", self._payload("http://www.sec.gov/x"))
        assert proc.returncode == 0
        decision = json.loads(proc.stdout)
        assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_domain_outside_whitelist_denied(self):
        proc = _run_hook("fetch_gate.py", self._payload("https://not-in-whitelist.example.com/x"))
        assert proc.returncode == 0
        decision = json.loads(proc.stdout)
        assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_transcript_tier_fool_com_allowed(self):
        """G5 新 transcript 档：fool.com 在白名单内 → 静默放行。"""
        proc = _run_hook("fetch_gate.py", self._payload("https://www.fool.com/earnings/call-transcripts/x"))
        assert proc.returncode == 0
        assert proc.stdout.strip() == ""

    def test_seekingalpha_still_allowed_after_tier_move(self):
        """seekingalpha.com 从 sell_side 挪到 transcript 档，但仍在白名单内 → 放行。"""
        proc = _run_hook("fetch_gate.py", self._payload("https://seekingalpha.com/article/123"))
        assert proc.returncode == 0
        assert proc.stdout.strip() == ""


class TestBudgetGate:
    def _setup_run(self, tmp_path, cap, usage):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        (run_dir / "budget.json").write_text(json.dumps({"budget_cap": cap}), encoding="utf-8")
        transcript = _write_jsonl(tmp_path / "session.jsonl", [_usage_event(*usage)])
        payload = {
            "transcript_path": str(transcript),
            "cwd": str(run_dir),
            "hook_event_name": "UserPromptSubmit",
        }
        return run_dir, payload

    def test_exhausted_blocks_with_exit_2(self, tmp_path):
        run_dir, payload = self._setup_run(tmp_path, cap=100, usage=(80, 30, 0, 0))  # spent=110
        proc = _run_hook("budget_gate.py", payload)
        assert proc.returncode == 2
        assert "经费卡耗尽" in proc.stderr
        state = json.loads((run_dir / "budget_state.json").read_text(encoding="utf-8"))
        assert state["exhausted"] is True
        assert state["spent"] == 110

    def test_not_exhausted_passes(self, tmp_path):
        run_dir, payload = self._setup_run(tmp_path, cap=1000, usage=(80, 30, 0, 0))
        proc = _run_hook("budget_gate.py", payload)
        assert proc.returncode == 0
        assert proc.stdout.strip() == ""
        state = json.loads((run_dir / "budget_state.json").read_text(encoding="utf-8"))
        assert state["exhausted"] is False


class TestSourceTagger:
    def test_web_fetch_post_tool_use_emits_tier_label(self):
        payload = {
            "hook_event_name": "PostToolUse",
            "tool_input": {"url": "https://www.goldmansachs.com/insights/x"},
        }
        proc = _run_hook("source_tagger.py", payload)
        assert proc.returncode == 0
        output = json.loads(proc.stdout)
        context = output["hookSpecificOutput"]["additionalContext"]
        assert "sell_side" in context

    def test_official_domain_label(self):
        payload = {
            "hook_event_name": "PostToolUse",
            "tool_input": {"url": "https://www.sec.gov/Archives/x.htm"},
        }
        proc = _run_hook("source_tagger.py", payload)
        assert proc.returncode == 0
        context = json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]
        assert "official" in context

    def test_transcript_tier_label(self):
        """G5 transcript 档标签：fool.com → 标签含 transcript 且提示可进正文。"""
        payload = {
            "hook_event_name": "PostToolUse",
            "tool_input": {"url": "https://www.fool.com/earnings/call-transcripts/x.aspx"},
        }
        proc = _run_hook("source_tagger.py", payload)
        assert proc.returncode == 0
        context = json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]
        assert "transcript" in context

    def test_seekingalpha_no_longer_sell_side(self):
        """seekingalpha.com 已挪入 transcript 档 → 标签不再含 sell_side。"""
        payload = {
            "hook_event_name": "PostToolUse",
            "tool_input": {"url": "https://seekingalpha.com/article/123"},
        }
        proc = _run_hook("source_tagger.py", payload)
        assert proc.returncode == 0
        context = json.loads(proc.stdout)["hookSpecificOutput"]["additionalContext"]
        assert "transcript" in context
        assert "sell_side" not in context


# ---------------------------------------------------------------------------
# 6. runner 纯函数
# ---------------------------------------------------------------------------

class TestRenderTemplates:
    def test_all_placeholders_replaced_with_absolute_paths(self, tmp_path):
        run_dir = tmp_path / "run"
        run_dir.mkdir()
        runner_mod._render_templates(run_dir)

        cordis = (run_dir / "cordis.yml").read_text(encoding="utf-8")
        hooks = (run_dir / "hooks.json").read_text(encoding="utf-8")

        assert "{{" not in cordis
        assert "{{" not in hooks
        # HOOKS_JSON_PATH → run_dir 下 hooks.json 的绝对路径
        assert str(run_dir / "hooks.json") in cordis
        # hooks.json 渲染后仍是合法 JSON，且 PYTHON/HOOKS_DIR 均为绝对路径
        hooks_obj = json.loads(hooks)
        python_bin = str(runner_mod.REPO_ROOT / ".venv" / "bin" / "python")
        hooks_dir = str(runner_mod.PACKAGE_DIR / "hooks")
        assert python_bin in hooks
        assert hooks_dir in hooks
        assert Path(python_bin).is_absolute() and Path(hooks_dir).is_absolute()
        commands = [
            h["command"]
            for entries in hooks_obj.values()
            for entry in entries
            for h in entry["hooks"]
        ]
        assert len(commands) == 3
        assert all("{{" not in c for c in commands)


class TestParseFinalPayload:
    def test_valid_json_block(self):
        message = '正文若干。\n```json\n{"cards": [{"card_id": "c1"}], "leads": []}\n```\n'
        payload = runner_mod.parse_final_payload(message)
        assert payload is not None
        assert payload["cards"][0]["card_id"] == "c1"

    def test_no_block_returns_none(self):
        assert runner_mod.parse_final_payload("没有代码块的纯文本") is None
        assert runner_mod.parse_final_payload("") is None

    def test_bad_json_returns_none(self):
        assert runner_mod.parse_final_payload("```json\n{bad json\n```") is None

    def test_missing_cards_key_returns_none(self):
        assert runner_mod.parse_final_payload('```json\n{"leads": []}\n```') is None

    def test_multiple_blocks_takes_last_valid(self):
        # 最后一个块坏掉 → 回退取前一个合法的
        message = (
            '```json\n{"cards": [{"card_id": "good"}]}\n```\n'
            "中间解释。\n"
            "```json\n{坏掉了\n```\n"
        )
        payload = runner_mod.parse_final_payload(message)
        assert payload["cards"][0]["card_id"] == "good"
        # 两个都合法 → 取最后一个
        message2 = (
            '```json\n{"cards": [{"card_id": "first"}]}\n```\n'
            '```json\n{"cards": [{"card_id": "second"}]}\n```\n'
        )
        assert runner_mod.parse_final_payload(message2)["cards"][0]["card_id"] == "second"


class TestFindPreviousNarrative:
    """G2 跟踪名单：同 tracking_key 最近一次巡逻的叙事坐标。"""

    def _mk_run(self, runs_root: Path, run_name: str, summary: dict):
        run_dir = runs_root / run_name
        run_dir.mkdir(parents=True)
        (run_dir / "run_summary.json").write_text(
            json.dumps(summary, ensure_ascii=False), encoding="utf-8"
        )

    def _state(self, marker: str):
        return {"conclusion": marker}

    def test_returns_latest_run_with_same_tracking_key(self, tmp_path):
        runs_root = tmp_path / "runs"
        self._mk_run(runs_root, "EV-1_20260101T000000Z",
                     {"tracking_key": "ai_capex", "narrative_state": self._state("旧坐标")})
        self._mk_run(runs_root, "EV-1_20260201T000000Z",
                     {"tracking_key": "ai_capex", "narrative_state": self._state("新坐标")})
        self._mk_run(runs_root, "EV-2_20260301T000000Z",
                     {"tracking_key": "fed_rates", "narrative_state": self._state("别的钥匙")})
        result = runner_mod.find_previous_narrative("ai_capex", runs_root)
        assert result is not None
        assert result["run_name"] == "EV-1_20260201T000000Z"  # 目录名字符串序取最新
        assert result["narrative_state"] == self._state("新坐标")

    def test_skips_empty_narrative_and_bad_json(self, tmp_path):
        runs_root = tmp_path / "runs"
        # 最新目录 narrative_state 为空 → 跳过，取上一个有坐标的
        self._mk_run(runs_root, "EV-1_20260101T000000Z",
                     {"tracking_key": "ai_capex", "narrative_state": self._state("有效坐标")})
        self._mk_run(runs_root, "EV-1_20260201T000000Z",
                     {"tracking_key": "ai_capex", "narrative_state": None})
        # 更最新但 run_summary.json 是坏 json → 跳过
        bad_dir = runs_root / "EV-1_20260301T000000Z"
        bad_dir.mkdir(parents=True)
        (bad_dir / "run_summary.json").write_text("{坏掉了", encoding="utf-8")
        result = runner_mod.find_previous_narrative("ai_capex", runs_root)
        assert result["run_name"] == "EV-1_20260101T000000Z"

    def test_no_match_returns_none(self, tmp_path):
        runs_root = tmp_path / "runs"
        self._mk_run(runs_root, "EV-1_20260101T000000Z",
                     {"tracking_key": "fed_rates", "narrative_state": self._state("x")})
        assert runner_mod.find_previous_narrative("ai_capex", runs_root) is None

    def test_missing_runs_root_returns_none(self, tmp_path):
        assert runner_mod.find_previous_narrative("ai_capex", tmp_path / "nonexistent") is None


class TestBuildPrompt:
    def test_no_previous_is_utc_plus_question(self):
        agenda = {"question": "巡逻 AI capex 叙事"}
        prompt = runner_mod._build_prompt(agenda, None)
        # 机械字段代码喂：prompt 以当前 UTC 行开头（collected_at_utc 不许模型估），
        # 然后是议程问题原文。
        assert prompt.startswith("当前 UTC 时间：")
        assert prompt.endswith("巡逻 AI capex 叙事")

    def test_with_previous_injects_narrative(self):
        agenda = {"question": "巡逻 AI capex 叙事"}
        previous = {
            "run_name": "EV-1_20260101T000000Z",
            "narrative_state": {"conclusion": "标记字符串-上期结论"},
        }
        prompt = runner_mod._build_prompt(agenda, previous)
        assert prompt.startswith("当前 UTC 时间：")
        assert "巡逻 AI capex 叙事" in prompt
        assert "上期坐标" in prompt
        assert "EV-1_20260101T000000Z" in prompt
        assert "标记字符串-上期结论" in prompt
        assert "previous_position_delta" in prompt


class TestValidateNarrativeState:
    def _valid_state(self):
        return {
            "framework_position": "叙事处于扩张中段",
            "conclusion": "capex 上行但增速放缓",
            "bull_strongest": "云厂商指引全线上调",
            "bear_strongest": "折旧年限拉长美化利润",
            "falsification": "若两大云厂下调指引则改判",
            "absence_signals": ["未见供应链砍单报道"],
            "previous_position_delta": "首期，无上期",
        }

    def test_valid_state_passes(self):
        assert runner_mod.validate_narrative_state({"narrative_state": self._valid_state()}) == []

    def test_missing_narrative_state(self):
        assert runner_mod.validate_narrative_state(None) == ["narrative_state_missing"]
        assert runner_mod.validate_narrative_state({}) == ["narrative_state_missing"]
        assert runner_mod.validate_narrative_state({"narrative_state": "not-a-dict"}) == [
            "narrative_state_missing"
        ]

    @pytest.mark.parametrize("field", [
        "framework_position", "conclusion", "bull_strongest",
        "bear_strongest", "falsification", "previous_position_delta",
    ])
    def test_string_field_empty_or_missing(self, field):
        for bad in (None, "", "   "):
            state = self._valid_state()
            if bad is None:
                del state[field]
            else:
                state[field] = bad
            errors = runner_mod.validate_narrative_state({"narrative_state": state})
            assert f"narrative_state_field_empty:{field}" in errors

    def test_absence_signals_must_be_non_empty_list(self):
        for bad in ([], "不是列表", None):
            state = self._valid_state()
            state["absence_signals"] = bad
            errors = runner_mod.validate_narrative_state({"narrative_state": state})
            assert "narrative_state_absence_signals_empty" in errors
        # 缺失也算
        state = self._valid_state()
        del state["absence_signals"]
        errors = runner_mod.validate_narrative_state({"narrative_state": state})
        assert "narrative_state_absence_signals_empty" in errors

    def test_unknown_field(self):
        state = self._valid_state()
        state["extra_field"] = "多出来的"
        errors = runner_mod.validate_narrative_state({"narrative_state": state})
        assert "narrative_state_unknown_field:extra_field" in errors


class TestTierDistribution:
    def test_counts_and_first_hand_rate(self):
        cards = [
            {"source_tier": "official"},
            {"source_tier": "official"},
            {"source_tier": "primary_news"},
            {"source_tier": "aggregator_news"},
        ]
        dist = runner_mod.tier_distribution(cards)
        assert dist["by_source_tier"] == {"official": 2, "primary_news": 1, "aggregator_news": 1}
        assert dist["first_hand_rate"] == pytest.approx(0.5)

    def test_empty_cards(self):
        dist = runner_mod.tier_distribution([])
        assert dist["by_source_tier"] == {}
        assert dist["first_hand_rate"] is None

    def test_missing_source_tier_counted_as_missing(self):
        dist = runner_mod.tier_distribution([{"fact_summary": "没写来源档"}])
        assert dist["by_source_tier"] == {"missing": 1}
        assert dist["first_hand_rate"] == 0.0


# ---------------------------------------------------------------------------
# 7. narrative_check：G7 判断段数字核对（纯标注不拦截）
# ---------------------------------------------------------------------------

from src.event_research import narrative_check as ncheck_mod
from src.event_research import brief as brief_mod


class TestExtractNumbers:
    def _values(self, text):
        return ncheck_mod._extract_numbers(text)

    def test_amounts_with_units(self):
        found = self._values("$500B 2200亿 1.5万亿美元 $4.1万亿")
        # raw 片段会带上单位后的尾随空白（正则 \s* 所致），比对前 strip
        by_raw = {raw.strip(): (v, k) for v, k, raw in found}
        assert by_raw["$500B"] == (5000.0, "currency_usd")        # 500 × 10亿
        assert by_raw["2200亿"] == (2200.0, "currency")            # 裸记 currency
        assert by_raw["1.5万亿美元"] == (15000.0, "currency_usd")   # 1.5 × 万亿
        assert by_raw["$4.1万亿"] == (41000.0, "currency_usd")

    def test_percent_and_bp(self):
        found = self._values("上涨 39.4%，利差收窄 90bp，降息 100bp")
        by_raw = {raw.strip(): (v, k) for v, k, raw in found}
        assert by_raw["39.4%"] == (39.4, "percent")
        assert by_raw["90bp"] == (0.9, "percent")    # 100bp = 1%
        assert by_raw["100bp"] == (1.0, "percent")

    def test_unit_normalization(self):
        # $1B = 10亿；$1T = 1万亿 = 10000亿
        assert (10.0, "currency_usd", "$1B") in self._values("$1B")
        assert (10000.0, "currency_usd", "$1T") in self._values("$1T")
        assert (10000.0, "currency", "1万亿") in self._values("1万亿")

    def test_bare_numbers_not_extracted(self):
        # 年份、日期这类无单位裸数字不查（查了必乱拦）
        assert self._values("2026 年 8/26 的会议，第 3 季度") == []


class TestCheckNarrativeNumbers:
    def _cards(self):
        return [
            {
                "fact_summary": "管理层称本季资本开支达 2200亿美元，毛利率 73.4%。",
                "interpretation": "假设 capex 指引延续，则投入强度未见拐点。",
                "limitations": ["单一季度数据"],
                "needs_data_confirmation": ["用第一层 capex 数据复核"],
                "source_pointer": {"url": "https://www.sec.gov/x.htm", "quote": "回购规模 600亿"},
            }
        ]

    def _narrative(self, **overrides):
        state = {
            "framework_position": "叙事处于扩张中段",
            "conclusion": "capex 强度延续",
            "bull_strongest": "指引上调",
            "bear_strongest": "折旧美化",
            "falsification": "若指引下调则改判",
            "absence_signals": ["未见砍单"],
            "previous_position_delta": "首期无上期",
        }
        state.update(overrides)
        return state

    def test_none_or_non_dict_narrative(self):
        for bad in (None, "not-a-dict", 42):
            report = ncheck_mod.check_narrative_numbers(bad, self._cards())
            assert report == {"checked": 0, "ungrounded": [], "card_refs": [], "anchored": False}

    def test_grounded_number_not_ungrounded(self):
        narrative = self._narrative(conclusion="本季 capex 2200亿美元，投入强度延续")
        report = ncheck_mod.check_narrative_numbers(narrative, self._cards())
        assert report["checked"] == 1
        assert report["ungrounded"] == []

    def test_ungrounded_number_flagged_with_field_and_text(self):
        narrative = self._narrative(conclusion="毛利率冲到 81.2%，创新高")
        report = ncheck_mod.check_narrative_numbers(narrative, self._cards())
        assert report["checked"] == 1
        assert len(report["ungrounded"]) == 1
        entry = report["ungrounded"][0]
        assert entry["field"] == "conclusion"
        assert "81.2%" in entry["text"]

    def test_currency_and_currency_usd_interchangeable(self):
        # 卡写"2200亿美元"，判断写 "$220B"（= 220×10亿）→ 算有依据
        narrative = self._narrative(conclusion="capex 达 $220B")
        report = ncheck_mod.check_narrative_numbers(narrative, self._cards())
        assert report["ungrounded"] == []

    def test_number_grounded_via_pointer_quote(self):
        # 数字只出现在 source_pointer.quote 里也算有依据
        narrative = self._narrative(conclusion="回购规模 600亿，力度未减")
        report = ncheck_mod.check_narrative_numbers(narrative, self._cards())
        assert report["ungrounded"] == []

    def test_card_refs_and_anchor(self):
        narrative = self._narrative(conclusion="强度延续（见 c1、c2）")
        report = ncheck_mod.check_narrative_numbers(narrative, self._cards())
        assert report["card_refs"] == ["c1", "c2"]
        assert report["anchored"] is True

    def test_no_card_ref_means_unanchored(self):
        narrative = self._narrative()
        report = ncheck_mod.check_narrative_numbers(narrative, self._cards())
        assert report["card_refs"] == []
        assert report["anchored"] is False


# ---------------------------------------------------------------------------
# 8. brief：金字塔简报
# ---------------------------------------------------------------------------

class TestRenderBrief:
    def _narrative(self):
        return {
            "framework_position": "叙事处于扩张中段",
            "conclusion": "capex 上行但增速放缓",
            "bull_strongest": "云厂商指引全线上调",
            "bear_strongest": "折旧年限拉长美化利润",
            "falsification": "若两大云厂下调指引则改判",
            "absence_signals": ["未见供应链砍单报道"],
            "previous_position_delta": "判断不变，证据加强",
        }

    def _summary(self, **overrides):
        summary = {
            "agenda_id": "EV-20260824-abc123",
            "run_dir": "/repo/output/event_research/runs/EV-20260824-abc123_20260824T000000Z",
            "narrative_state": self._narrative(),
            "cards_verified": 1,
            "cards_total": 2,
            "tier_distribution": {"by_source_tier": {"official": 1, "aggregator_news": 1},
                                  "first_hand_rate": 0.5},
            "narrative_number_check": {"checked": 3, "ungrounded": [],
                                       "card_refs": ["c1"], "anchored": True},
            "budget": {"spent": 12345, "budget_cap": 30_000_000},
            "budget_exhausted": False,
            "cards_downgraded": 1,
            "cards_with_shackle_labels": 1,
        }
        summary.update(overrides)
        return summary

    def _cards(self):
        return [
            {
                "card_id": "c1",
                "fact_summary": "管理层称本季资本开支达 2200亿美元。",
                "interpretation": "假设指引延续，则投入强度未见拐点。",
                "falsification": "若下季指引下调则改判",
                "counter_one_liner": "capex 已透支未来两年需求",
                "source_tier": "official",
                "source_url": "https://www.sec.gov/Archives/x.htm",
                "collected_at_utc": "2026-08-24T00:00:00+00:00",
                "needs_data_confirmation": ["用第一层数据复核"],
                "reconciliation": {"status": "verified"},
            },
            {
                "card_id": "c2",
                "fact_summary": "某卖方预计 capex 见顶。",
                "interpretation": "假设卖方口径可信，则与官方指引冲突。",
                "source_tier": "aggregator_news",
                "source_url": "https://www.goldmansachs.com/insights/x",
                "collected_at_utc": "2026-08-24T00:00:00+00:00",
                "needs_data_confirmation": [],
                "reconciliation": {"status": "downgraded_weak_tier"},
            },
        ]

    def test_first_screen_three_lines_before_why(self):
        md = brief_mod.render_brief(self._summary(), self._cards())
        # 三行来自 narrative_state 对应字段
        assert "**变没变**：判断不变，证据加强" in md
        assert "**本期判断**：capex 上行但增速放缓" in md
        assert "**认错条件**：若两大云厂下调指引则改判" in md
        # 出现在"为什么"小节之前
        assert md.index("**变没变**") < md.index("## 为什么")
        assert md.index("**本期判断**") < md.index("## 为什么")
        assert md.index("**认错条件**") < md.index("## 为什么")

    def test_evidence_cards_content(self):
        md = brief_mod.render_brief(self._summary(), self._cards())
        # 每张卡含 fact_summary 与来源行（tier 中文标签 + 对账状态标签）
        assert "管理层称本季资本开支达 2200亿美元。" in md
        assert "某卖方预计 capex 见顶。" in md
        assert "（官方；✓ 已对回原文；" in md
        assert "（卖方；✗ 弱来源进了正文；" in md

    def test_optional_card_fields_shown_only_when_present(self):
        md = brief_mod.render_brief(self._summary(), self._cards())
        # c1 有 falsification/counter_one_liner → 显示；c2 没有 → 只有一行
        assert md.count("改判条件：") == 1
        assert "改判条件：若下季指引下调则改判" in md
        assert md.count("最强反方：") == 1
        assert "最强反方：capex 已透支未来两年需求" in md

    def test_machine_check_section(self):
        md = brief_mod.render_brief(self._summary(), self._cards())
        assert "对账通过率：1/2" in md
        # 张张标价：降级与镣铐标注计数随质检行展示（标注随卡走不连坐）
        assert "降级 1 张；镣铐标注 1 张" in md
        assert "一手率：0.5" in md
        assert "判断数字核对：查了 3 个，无据 0 个" in md
        # 08-25 裁决：二档撤发布闸门，质检行不再有"发布闸门"
        assert "发布闸门" not in md

    def test_budget_exhausted_marks_half_finished(self):
        # 经费耗尽 → 经费行追加半成品标注；未耗尽 → 无
        md = brief_mod.render_brief(self._summary(budget_exhausted=True), self._cards())
        assert "（耗尽，本期为半成品）" in md
        md_ok = brief_mod.render_brief(self._summary(), self._cards())
        assert "（耗尽，本期为半成品）" not in md_ok

    def test_shackle_annotation_line_shown_only_when_errors(self):
        cards = self._cards()
        cards[1]["validation_errors"] = ["source_pointer_url_empty", "optional_field_empty:falsification"]
        md = brief_mod.render_brief(self._summary(), cards)
        assert md.count("镣铐标注：") == 1
        assert "镣铐标注：source_pointer_url_empty、optional_field_empty:falsification" in md
        # 默认卡无 validation_errors → 不出带冒号的卡级标注行（质检行的"镣铐标注 N 张"无冒号）
        md_clean = brief_mod.render_brief(self._summary(), self._cards())
        assert "镣铐标注：" not in md_clean

    def test_machine_check_section_lists_ungrounded(self):
        summary = self._summary(narrative_number_check={
            "checked": 2,
            "ungrounded": [{"field": "conclusion", "text": "81.2%", "normalized": "81.2|percent"}],
            "card_refs": [], "anchored": False,
        })
        md = brief_mod.render_brief(summary, self._cards())
        assert "无据 1 个" in md
        assert "conclusion" in md and "81.2%" in md
        assert "未挂任何证据卡" in md

    def test_charter_feedback_marked_unverified(self):
        summary = self._summary(charter_feedback="建议把电力瓶颈纳入常备巡逻")
        md = brief_mod.render_brief(summary, self._cards())
        assert "宪章反馈" in md
        assert "未经核实" in md
        assert "建议把电力瓶颈纳入常备巡逻" in md
        # 无 charter_feedback 时不出该小节
        md_no = brief_mod.render_brief(self._summary(), self._cards())
        assert "宪章反馈" not in md_no

    def test_missing_narrative_state_does_not_crash(self):
        summary = self._summary(narrative_state=None)
        md = brief_mod.render_brief(summary, self._cards())
        assert "**本期判断**：（缺失）" in md
        assert "**认错条件**：（缺失）" in md
        assert "**变没变**：（首期无上期）" in md


class TestRunSummaryContract:
    """08-25 撤发布闸门后的 run_summary 字段契约。

    run_agenda 需要真实 API 不可测，这里用 AST 直接读 runner.py 里
    run_summary 字典字面量的键，锁定：闸门字段全删、标注字段在位。
    """

    def _summary_keys(self):
        import ast
        tree = ast.parse(
            (REPO_ROOT / "src" / "event_research" / "runner.py").read_text(encoding="utf-8")
        )
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Assign)
                and any(isinstance(t, ast.Name) and t.id == "run_summary" for t in node.targets)
                and isinstance(node.value, ast.Dict)
            ):
                return {k.value for k in node.value.keys if isinstance(k, ast.Constant)}
        raise AssertionError("runner.py 里找不到 run_summary 字典字面量")

    def test_gate_fields_removed(self):
        keys = self._summary_keys()
        for gone in (
            "publishable",
            "unpublishable_reason",
            "shackles_failed",
            "narrative_errors",
            "cards_with_shackle_errors",
        ):
            assert gone not in keys, f"已撤销的闸门字段仍在 run_summary：{gone}"

    def test_label_fields_present(self):
        keys = self._summary_keys()
        for want in ("narrative_observations", "cards_with_shackle_labels", "cards_downgraded"):
            assert want in keys, f"标注层字段缺失：{want}"
