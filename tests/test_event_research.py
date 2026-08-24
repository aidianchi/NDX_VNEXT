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
        "source_pointer": {"call_id": "call-1", "quote": "维持联邦基金利率不变"},
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

    def test_empty_call_id_and_quote(self):
        card = _valid_card()
        card["source_pointer"] = {"call_id": "  ", "quote": ""}
        errors = card_mod.validate_research_card(card, now_utc=FIXED_NOW)
        assert "source_pointer_call_id_empty" in errors
        assert "source_pointer_quote_empty" in errors

    def test_unknown_pointer_field(self):
        card = _valid_card()
        card["source_pointer"] = {"call_id": "c1", "quote": "原文", "tool_name": "web_fetch"}
        errors = card_mod.validate_research_card(card, now_utc=FIXED_NOW)
        assert "source_pointer_unknown_field:tool_name" in errors

    def test_prototype_hedge_word_still_enforced(self):
        """复用原型校验仍生效：fact_summary 含"可能" → fact_summary_hedge_word:可能。"""
        card = _valid_card()
        card["fact_summary"] = "美联储可能在下一次会议降息。"
        errors = card_mod.validate_research_card(card, now_utc=FIXED_NOW)
        assert "fact_summary_hedge_word:可能" in errors

    def test_card_not_object(self):
        assert card_mod.validate_research_card("not a dict") == ["card_not_object"]


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
            _tool_call("call-search", "web_search", "https://www.sec.gov/"),
            _tool_result("call-search", "搜索结果摘要若干条"),
            # 无配对的 result 与缺 callId 的 call 不应崩
            _tool_result("orphan-result", "孤儿"),
            {"type": "tool/call", "data": {"name": "web_fetch"}},
        ]

    def test_index_tool_calls_pairs_call_and_result(self):
        calls = reconcile_mod.index_tool_calls(self._events())
        assert set(calls) == {"call-official", "call-sellside", "call-search"}
        assert calls["call-official"]["name"] == "web_fetch"
        assert calls["call-official"]["url"] == "https://www.sec.gov/Archives/edgar/x.htm"
        assert "维持利率" in calls["call-official"]["result_text"]
        assert calls["call-search"]["name"] == "web_search"

    def _card_pointing(self, call_id, quote):
        return {"source_pointer": {"call_id": call_id, "quote": quote}}

    def test_verified_official_domain(self):
        calls = reconcile_mod.index_tool_calls(self._events())
        # quote 与原文有空白差异：去空白子串匹配应命中
        card = self._card_pointing("call-official", "美联储宣布维持利率不变")
        result = reconcile_mod.reconcile_card(card, calls, MINI_WHITELIST)
        assert result["status"] == reconcile_mod.STATUS_VERIFIED
        assert result["source_tier_expected"] == "official"

    def test_quote_not_found(self):
        calls = reconcile_mod.index_tool_calls(self._events())
        card = self._card_pointing("call-official", "原文里根本不存在的一句话")
        result = reconcile_mod.reconcile_card(card, calls, MINI_WHITELIST)
        assert result["status"] == reconcile_mod.STATUS_QUOTE_NOT_FOUND

    def test_pointer_missing(self):
        calls = reconcile_mod.index_tool_calls(self._events())
        card = self._card_pointing("call-does-not-exist", "随便")
        result = reconcile_mod.reconcile_card(card, calls, MINI_WHITELIST)
        assert result["status"] == reconcile_mod.STATUS_POINTER_MISSING

    def test_weak_tier_sell_side(self):
        calls = reconcile_mod.index_tool_calls(self._events())
        card = self._card_pointing("call-sellside", "我们预计降息在即")
        result = reconcile_mod.reconcile_card(card, calls, MINI_WHITELIST)
        assert result["status"] == reconcile_mod.STATUS_WEAK_TIER

    def test_web_search_pointer_unverified(self):
        calls = reconcile_mod.index_tool_calls(self._events())
        card = self._card_pointing("call-search", "搜索结果摘要")
        result = reconcile_mod.reconcile_card(card, calls, MINI_WHITELIST)
        assert result["status"] == reconcile_mod.STATUS_UNVERIFIED_SOURCE

    def test_reconcile_cards_pass_rate(self, tmp_path):
        session_root = tmp_path / "sessions"
        (session_root / "s1").mkdir(parents=True)
        _write_jsonl(session_root / "s1" / "session.jsonl", self._events())
        cards = [
            self._card_pointing("call-official", "美联储宣布维持利率不变"),  # verified
            self._card_pointing("call-official", "不存在的引文"),            # quote_not_found
            self._card_pointing("call-nope", "随便"),                        # pointer_missing
            self._card_pointing("call-sellside", "我们预计降息在即"),          # weak_tier
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
