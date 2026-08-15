# -*- coding: utf-8 -*-
"""T49-3 第二层补采原型验收测试（新建文件，不改任何既有断言）。

覆盖：
- 用 FakeLLMEngine / SequencedFakeLLMEngine 跑通一轮真实循环：
  planner 选工具 → 工具返回 → reader 出卡 → 四条镣铐校验通过。
- 四条镣铐反例：fact 带"可能"、source_tier 非法、缺 needs_data_confirmation、
  时间戳超前，全部被拒。
- 工具白名单外调用被拒；网络工具失败如实返回。
- 三性脚本：合成 audit 输入，断言 verdict 名单正确、撤出源进 sources_to_remove。
"""
import json
import sys
import urllib.error
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from layer2_supplement_prototype import prototype_loop, three_tests  # noqa: E402


# ---------------------------------------------------------------------------
# Fake LLM engines（与 test_vnext_orchestrator.py 的 FakeLLMEngine 同款契约）
# ---------------------------------------------------------------------------

class FakeLLMEngine:
    available_models = ["fake"]
    successful_model = None

    def __init__(self, responses):
        self.responses = responses
        self.token_usage = {"total": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}}

    def call_with_fallback(self, prompt, stage_name="", preferred_models=None):
        response = self.responses[stage_name]
        if response is not None:
            self.successful_model = "fake"
        return response

    def extract_json(self, text, stage):
        return json.loads(text)

    def get_token_report(self):
        return self.token_usage


class SequencedFakeLLMEngine(FakeLLMEngine):
    """同一 stage 按调用次数依次返回列表里的响应；超出后停在最后一个。"""

    def __init__(self, responses):
        super().__init__(responses)
        self.calls = {}

    def call_with_fallback(self, prompt, stage_name="", preferred_models=None):
        self.calls[stage_name] = self.calls.get(stage_name, 0) + 1
        response = self.responses[stage_name]
        if isinstance(response, list):
            index = min(self.calls[stage_name] - 1, len(response) - 1)
            response = response[index]
        if response is not None:
            self.successful_model = "fake"
        return response


# ---------------------------------------------------------------------------
# 合成材料卡 / 响应
# ---------------------------------------------------------------------------

def _valid_card(**overrides):
    card = {
        "card_id": "ag1_r01_c1",
        "agenda_id": "ag1",
        "fact_summary": "原文称美联储宣布维持利率不变。",
        "interpretation": "这可能是利率路径保持的信号，若数据确认。",
        "source_tier": "official",
        "source_url": "material.txt",
        "collected_at_utc": datetime.now(timezone.utc).isoformat(),
        "needs_data_confirmation": ["第一层利率数据确认"],
        "limitations": ["单条材料不能证明指数方向。"],
        "governance_note": prototype_loop.GOVERNANCE_NOTE,
    }
    card.update(overrides)
    return card


def _reader_response(
    fact="原文称美联储宣布维持利率不变。",
    interpretation="这可能是利率路径保持的信号，若数据确认。",
    tier="official",
    url="material.txt",
    needs=None,
    limitations=None,
):
    needs = needs if needs is not None else ["第一层利率数据确认"]
    limitations = limitations if limitations is not None else ["单条材料不能证明指数方向。"]
    return json.dumps(
        {
            "cards": [
                {
                    "fact_summary": fact,
                    "interpretation": interpretation,
                    "source_tier": tier,
                    "source_url": url,
                    "needs_data_confirmation": needs,
                    "limitations": limitations,
                }
            ]
        },
        ensure_ascii=False,
    )


def _planner_response(tool_name="read_local_material", args=None):
    return json.dumps(
        {"tools": [{"tool": tool_name, "args": args or {"path": "material.txt"}}]},
        ensure_ascii=False,
    )


def _make_run(tmp_path, name="ag1"):
    """按 run_dir 强制约束创建 run 目录：必须位于 runs_root 下。"""
    runs_root = tmp_path / "runs"
    run_dir = runs_root / name
    run_dir.mkdir(parents=True)
    return run_dir, runs_root


# ---------------------------------------------------------------------------
# 一、自焊小循环
# ---------------------------------------------------------------------------

def test_full_loop_one_round_planner_tool_reader_card_passes(tmp_path):
    run_dir, runs_root = _make_run(tmp_path)
    (run_dir / "material.txt").write_text("美联储宣布维持利率不变。", encoding="utf-8")

    repo_root = tmp_path / "repo"
    (repo_root / "investigation_reports").mkdir(parents=True)

    engine = SequencedFakeLLMEngine(
        {
            prototype_loop.PLANNER_STAGE: _planner_response("read_local_material", {"path": "material.txt"}),
            prototype_loop.READER_STAGE: _reader_response(),
        }
    )

    summary = prototype_loop.run_prototype(
        {"agenda_id": "ag1", "question": "利率路径是否变化？", "max_rounds": 1},
        run_dir=run_dir,
        llm_engine=engine,
        repo_root=repo_root,
        runs_root=runs_root,
    )

    assert summary["status"] == "completed"
    assert summary["total_cards"] == 1
    assert summary["rounds"][0]["planner_ok"] is True
    assert summary["rounds"][0]["reader_ok"] is True
    assert summary["rounds"][0]["reader_retries"] == 0
    assert summary["rejected_tool_calls"] == []
    assert summary["models"]["engine_available_models"] == ["fake"]
    assert summary["models"]["planner_success_model"] == "fake"
    assert summary["models"]["reader_success_model"] == "fake"

    material_lines = [
        line for line in (run_dir / "materials.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    assert len(material_lines) == 1
    card = json.loads(material_lines[0])

    assert card["card_id"].startswith("ag1_r01_c")
    assert card["agenda_id"] == "ag1"
    assert card["governance_note"] == prototype_loop.GOVERNANCE_NOTE
    assert card["fact_summary"] == "原文称美联储宣布维持利率不变。"
    assert card["interpretation"] == "这可能是利率路径保持的信号，若数据确认。"
    assert card["source_tier"] == "official"
    assert card["needs_data_confirmation"] == ["第一层利率数据确认"]
    assert prototype_loop.parse_utc_iso(card["collected_at_utc"]) is not None

    audit_dir = run_dir / "prototype_audit"
    assert (audit_dir / "round_001_planner_prompt.md").is_file()
    assert (audit_dir / "round_001_reader_prompt.md").is_file()
    assert (run_dir / "run_summary.json").is_file()


def test_loop_rejects_unknown_tool_and_reader_can_output_zero_cards(tmp_path):
    run_dir, runs_root = _make_run(tmp_path)
    repo_root = tmp_path / "repo"
    (repo_root / "investigation_reports").mkdir(parents=True)

    engine = SequencedFakeLLMEngine(
        {
            prototype_loop.PLANNER_STAGE: _planner_response("write_file", {"path": "evil.txt"}),
            prototype_loop.READER_STAGE: json.dumps({"cards": []}),
        }
    )

    summary = prototype_loop.run_prototype(
        {"agenda_id": "ag1", "question": "测试问题", "max_rounds": 1},
        run_dir=run_dir,
        llm_engine=engine,
        repo_root=repo_root,
        runs_root=runs_root,
    )

    assert summary["status"] == "failed"  # 有校验错误且 0 张卡 → 按实际成败记 failed
    assert summary["total_cards"] == 0
    assert len(summary["rejected_tool_calls"]) == 1
    assert summary["rejected_tool_calls"][0]["tool"] == "write_file"
    assert summary["rejected_tool_calls"][0]["error_code"] == "tool_not_whitelisted"
    assert not (run_dir / "evil.txt").exists()

    material_lines = [
        line for line in (run_dir / "materials.jsonl").read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    assert material_lines == []


def test_execute_tool_call_rejects_non_whitelisted_tool(tmp_path):
    result = prototype_loop.execute_tool_call(
        "write_file",
        {"path": "evil.txt"},
        run_dir=tmp_path,
        repo_root=tmp_path,
    )
    assert result["ok"] is False
    assert result["error_code"] == "tool_not_whitelisted"
    assert not (tmp_path / "evil.txt").exists()


def test_reader_validation_failure_retries_then_succeeds(tmp_path):
    run_dir, runs_root = _make_run(tmp_path)
    (run_dir / "material.txt").write_text("美联储宣布维持利率不变。", encoding="utf-8")
    repo_root = tmp_path / "repo"
    (repo_root / "investigation_reports").mkdir(parents=True)

    bad_reader = _reader_response(fact="原文称美联储可能降息。")  # fact 带"可能" → 镣铐打回
    good_reader = _reader_response()

    engine = SequencedFakeLLMEngine(
        {
            prototype_loop.PLANNER_STAGE: _planner_response("read_local_material", {"path": "material.txt"}),
            prototype_loop.READER_STAGE: [bad_reader, good_reader],
        }
    )

    summary = prototype_loop.run_prototype(
        {"agenda_id": "ag1", "question": "利率路径是否变化？", "max_rounds": 1},
        run_dir=run_dir,
        llm_engine=engine,
        repo_root=repo_root,
        runs_root=runs_root,
    )

    assert summary["rounds"][0]["reader_retries"] == 1
    assert summary["total_cards"] == 1
    assert summary["status"] == "completed"  # 重试后全绿 → completed

    retry_prompt = (run_dir / "prototype_audit" / "round_001_reader_prompt_retry_1.md").read_text(encoding="utf-8")
    assert "fact_summary_hedge_word" in retry_prompt  # 校验错误要能被 grep 到


def test_task_max_rounds_over_limit_rejected(tmp_path):
    import pytest

    run_dir, runs_root = _make_run(tmp_path)
    with pytest.raises(ValueError, match="max_rounds_out_of_range"):
        prototype_loop.run_prototype(
            {"agenda_id": "ag1", "question": "q", "max_rounds": 5},
            run_dir=run_dir,
            llm_engine=FakeLLMEngine({}),
            runs_root=runs_root,
        )


def test_run_dir_outside_runs_root_rejected(tmp_path):
    import pytest

    runs_root = tmp_path / "runs"
    runs_root.mkdir()
    outside = tmp_path / "elsewhere"
    outside.mkdir()
    with pytest.raises(ValueError, match="run_dir_outside_runs_root"):
        prototype_loop.run_prototype(
            {"agenda_id": "ag1", "question": "q", "max_rounds": 1},
            run_dir=outside,
            llm_engine=FakeLLMEngine({}),
            runs_root=runs_root,
        )


# ---------------------------------------------------------------------------
# 二、四条镣铐反例
# ---------------------------------------------------------------------------

def test_shackle_rejects_fact_with_hedge_word():
    errors = prototype_loop.validate_material_card(_valid_card(fact_summary="原文称美联储可能降息。"))
    assert any(error.startswith("fact_summary_hedge_word:") for error in errors)


def test_shackle_rejects_illegal_source_tier():
    errors = prototype_loop.validate_material_card(_valid_card(source_tier="official_but_typo"))
    assert "source_tier_illegal" in errors


def test_shackle_rejects_missing_needs_data_confirmation():
    errors = prototype_loop.validate_material_card(_valid_card(needs_data_confirmation=[]))
    assert "needs_data_confirmation_empty_or_invalid" in errors


def test_shackle_rejects_future_timestamp():
    future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    errors = prototype_loop.validate_material_card(
        _valid_card(collected_at_utc=future),
        now_utc=datetime.now(timezone.utc),
    )
    assert "collected_at_utc_in_future" in errors


def test_shackle_accepts_valid_card():
    errors = prototype_loop.validate_material_card(_valid_card())
    assert errors == []


def test_shackle_rejects_fact_with_spaced_hedge_word():
    # 归一化去空白后，"可 能" 也必须命中禁言词。
    errors = prototype_loop.validate_material_card(_valid_card(fact_summary="原文称美联储可 能降息。"))
    assert any(error.startswith("fact_summary_hedge_word:") for error in errors)

    # "也许" 是补齐的禁言词。
    errors = prototype_loop.validate_material_card(_valid_card(fact_summary="原文称美联储也许降息。"))
    assert any(error == "fact_summary_hedge_word:也许" for error in errors)


def test_shackle_rejects_fact_with_english_hedge_words():
    for fact in ("Fed may cut rates.", "Fed could cut rates.", "Fed is likely to cut.", "A cut is expected."):
        errors = prototype_loop.validate_material_card(_valid_card(fact_summary=fact))
        assert any(error.startswith("fact_summary_hedge_word_en:") for error in errors), fact


def test_shackle_rejects_empty_fact_and_interpretation():
    errors = prototype_loop.validate_material_card(_valid_card(fact_summary=""))
    assert "fact_summary_empty" in errors

    errors = prototype_loop.validate_material_card(_valid_card(interpretation=""))
    assert "interpretation_empty" in errors


def test_shackle_rejects_interpretation_missing_hypothesis_marker():
    errors = prototype_loop.validate_material_card(
        _valid_card(interpretation="原文称美联储宣布维持利率不变。")  # 无假设标记
    )
    assert "interpretation_missing_hypothesis_marker" in errors


def test_shackle_rejects_fact_equals_or_prefix_of_interpretation():
    # fact == interpretation
    text = "美联储宣布维持利率不变。"
    errors = prototype_loop.validate_material_card(_valid_card(fact_summary=text, interpretation=text))
    assert "fact_interpretation_not_separated" in errors

    # fact 是 interpretation 的前缀（只查全等会被绕过）
    errors = prototype_loop.validate_material_card(
        _valid_card(
            fact_summary="美联储宣布维持利率不变。",
            interpretation="美联储宣布维持利率不变。这可能利好风险资产，若数据确认。",
        )
    )
    assert "fact_interpretation_not_separated" in errors


def test_shackle_rejects_non_string_fact_and_interpretation():
    errors = prototype_loop.validate_material_card(_valid_card(fact_summary=123))
    assert "fact_summary_not_string" in errors

    errors = prototype_loop.validate_material_card(_valid_card(interpretation=["可能"]))
    assert "interpretation_not_string" in errors


def test_shackle_rejects_unknown_fields():
    errors = prototype_loop.validate_material_card(_valid_card(event_id="evt:001"))
    assert any(error.startswith("unknown_field:") for error in errors)


def test_shackle_validates_source_url_scheme_and_domain():
    # http(s) URL 必须过 https + 域名白名单；本地相对路径不受此限。
    errors = prototype_loop.validate_material_card(_valid_card(source_url="http://www.sec.gov/x"))
    assert "source_url_url_not_https" in errors

    errors = prototype_loop.validate_material_card(_valid_card(source_url="https://evil.example.com/x"))
    assert "source_url_domain_not_allowed" in errors

    errors = prototype_loop.validate_material_card(_valid_card(source_url="material.txt"))
    assert errors == []


# ---------------------------------------------------------------------------
# 三、网络工具与本地读取工具
# ---------------------------------------------------------------------------

def test_fetch_official_url_rejects_non_https_and_non_whitelisted_domain(tmp_path):
    def fail_if_called(url, timeout):
        raise AssertionError(f"域名/协议校验失败前不应发起真实请求：{url}")

    http_result = prototype_loop.execute_tool_call(
        "fetch_official_url",
        {"url": "http://www.sec.gov/Archives/edgar/data/1"},
        run_dir=tmp_path,
        repo_root=tmp_path,
        http_get=fail_if_called,
    )
    assert http_result["ok"] is False
    assert http_result["error_code"] == "url_not_https"

    domain_result = prototype_loop.execute_tool_call(
        "fetch_official_url",
        {"url": "https://example.com/some/page"},
        run_dir=tmp_path,
        repo_root=tmp_path,
        http_get=fail_if_called,
    )
    assert domain_result["ok"] is False
    assert domain_result["error_code"] == "domain_not_allowed"


def test_fetch_official_url_network_failure_returns_truthful_error(tmp_path):
    def failing_get(url, timeout):
        raise urllib.error.URLError("boom")

    result = prototype_loop.execute_tool_call(
        "fetch_official_url",
        {"url": "https://www.sec.gov/Archives/edgar/data/1"},
        run_dir=tmp_path,
        repo_root=tmp_path,
        http_get=failing_get,
    )
    assert result["ok"] is False
    assert result["error_code"] == "network_error"
    assert "boom" in result["error"]
    cache_dir = tmp_path / "fetched_cache"
    assert not cache_dir.exists() or list(cache_dir.glob("*.txt")) == []


def test_fetch_official_url_caches_with_utc_timestamp(tmp_path):
    def fake_get(url, timeout):
        return "abcd" * 2500  # 10000 字符，超过默认 6000 上限

    result = prototype_loop.execute_tool_call(
        "fetch_official_url",
        {"url": "https://www.sec.gov/Archives/edgar/data/1"},
        run_dir=tmp_path,
        repo_root=tmp_path,
        http_get=fake_get,
    )
    assert result["ok"] is True
    assert result["char_count"] == prototype_loop.FETCH_DEFAULT_MAX_CHARS
    assert result["truncated"] is True
    assert len(result["text"]) == prototype_loop.FETCH_DEFAULT_MAX_CHARS

    cache_dir = tmp_path / "fetched_cache"
    txt_files = list(cache_dir.glob("*.txt"))
    meta_files = list(cache_dir.glob("*.meta.json"))
    assert len(txt_files) == 1
    assert len(meta_files) == 1
    meta = json.loads(meta_files[0].read_text(encoding="utf-8"))
    assert meta["url"] == "https://www.sec.gov/Archives/edgar/data/1"
    assert prototype_loop.parse_utc_iso(meta["fetched_at_utc"]) is not None


def test_fetch_official_url_redirect_to_non_whitelisted_domain_rejected(tmp_path):
    def redirecting_get(url, timeout):
        return ("正文", "https://evil.example.com/landing")

    result = prototype_loop.execute_tool_call(
        "fetch_official_url",
        {"url": "https://www.sec.gov/Archives/edgar/data/1"},
        run_dir=tmp_path,
        repo_root=tmp_path,
        http_get=redirecting_get,
    )
    assert result["ok"] is False
    assert result["error_code"] == "redirect_domain_not_allowed"
    assert "evil.example.com" in result["error"]
    cache_dir = tmp_path / "fetched_cache"
    assert not cache_dir.exists() or list(cache_dir.glob("*.txt")) == []


def test_fetch_official_url_records_final_url_for_allowed_redirect(tmp_path):
    final_url = "https://www.federalreserve.gov/new/press"

    def redirecting_get(url, timeout):
        return ("正文", final_url)

    result = prototype_loop.execute_tool_call(
        "fetch_official_url",
        {"url": "https://www.sec.gov/Archives/edgar/data/1"},
        run_dir=tmp_path,
        repo_root=tmp_path,
        http_get=redirecting_get,
    )
    assert result["ok"] is True
    assert result["final_url"] == final_url

    meta_files = list((tmp_path / "fetched_cache").glob("*.meta.json"))
    assert len(meta_files) == 1
    meta = json.loads(meta_files[0].read_text(encoding="utf-8"))
    assert meta["final_url"] == final_url


def test_reader_too_many_cards_rejected_for_retry_not_truncated(tmp_path):
    run_dir, runs_root = _make_run(tmp_path)
    (run_dir / "material.txt").write_text("美联储宣布维持利率不变。", encoding="utf-8")
    repo_root = tmp_path / "repo"
    (repo_root / "investigation_reports").mkdir(parents=True)

    def reader_response_with_cards(count):
        cards = [
            {
                "fact_summary": "原文称美联储宣布维持利率不变。",
                "interpretation": "这可能是利率路径保持的信号，若数据确认。",
                "source_tier": "official",
                "source_url": "material.txt",
                "needs_data_confirmation": ["第一层利率数据确认"],
                "limitations": ["单条材料不能证明指数方向。"],
            }
            for _ in range(count)
        ]
        return json.dumps({"cards": cards}, ensure_ascii=False)

    engine = SequencedFakeLLMEngine(
        {
            prototype_loop.PLANNER_STAGE: _planner_response("read_local_material", {"path": "material.txt"}),
            prototype_loop.READER_STAGE: [reader_response_with_cards(3), reader_response_with_cards(2)],
        }
    )

    summary = prototype_loop.run_prototype(
        {"agenda_id": "ag1", "question": "利率路径是否变化？", "max_rounds": 1},
        run_dir=run_dir,
        llm_engine=engine,
        repo_root=repo_root,
        runs_root=runs_root,
    )

    # 3 张那批必须整批打回重试，不得静默截断成 2 张；重试后 2 张通过。
    assert summary["rounds"][0]["reader_retries"] == 1
    assert summary["total_cards"] == 2
    retry_prompt = (run_dir / "prototype_audit" / "round_001_reader_prompt_retry_1.md").read_text(encoding="utf-8")
    assert "reader_too_many_cards" in retry_prompt


def test_read_local_material_allowed_and_rejected(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "data.txt").write_text("run 目录数据", encoding="utf-8")

    repo_root = tmp_path / "repo"
    inv_dir = repo_root / "investigation_reports"
    inv_dir.mkdir(parents=True)
    (inv_dir / "ok.md").write_text("调查材料", encoding="utf-8")
    (inv_dir / "bad.py").write_text("不该读", encoding="utf-8")
    (repo_root / "src").mkdir(parents=True)
    (repo_root / "src" / "secret.py").write_text("外部秘密", encoding="utf-8")

    run_ok = prototype_loop.execute_tool_call(
        "read_local_material", {"path": "data.txt"}, run_dir=run_dir, repo_root=repo_root
    )
    assert run_ok["ok"] is True and run_ok["text"] == "run 目录数据"

    inv_ok = prototype_loop.execute_tool_call(
        "read_local_material", {"path": "investigation_reports/ok.md"}, run_dir=run_dir, repo_root=repo_root
    )
    assert inv_ok["ok"] is True and inv_ok["text"] == "调查材料"

    ext_bad = prototype_loop.execute_tool_call(
        "read_local_material", {"path": "investigation_reports/bad.py"}, run_dir=run_dir, repo_root=repo_root
    )
    assert ext_bad["ok"] is False and ext_bad["error_code"] == "extension_not_whitelisted"

    # 相对路径先按 run 目录解析；run 目录内不存在如实报 file_not_found_in_run_dir。
    missing_in_run = prototype_loop.execute_tool_call(
        "read_local_material", {"path": "src/secret.py"}, run_dir=run_dir, repo_root=repo_root
    )
    assert missing_in_run["ok"] is False and missing_in_run["error_code"] == "file_not_found_in_run_dir"

    # `..` 逃出 run 目录 → outside_allowed_roots。
    escape = prototype_loop.execute_tool_call(
        "read_local_material", {"path": "../outside.txt"}, run_dir=run_dir, repo_root=repo_root
    )
    assert escape["ok"] is False and escape["error_code"] == "outside_allowed_roots"

    absolute = prototype_loop.execute_tool_call(
        "read_local_material", {"path": "/etc/passwd"}, run_dir=run_dir, repo_root=repo_root
    )
    assert absolute["ok"] is False and absolute["error_code"] == "absolute_path_denied"


def test_read_local_material_rejects_file_over_size_limit(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "large.txt").write_text("x" * (prototype_loop.READ_LOCAL_MAX_BYTES + 1), encoding="utf-8")

    result = prototype_loop.execute_tool_call(
        "read_local_material", {"path": "large.txt"}, run_dir=run_dir, repo_root=tmp_path
    )
    assert result["ok"] is False
    assert result["error_code"] == "file_too_large"


# ---------------------------------------------------------------------------
# 四、三性判定转常驻
# ---------------------------------------------------------------------------

def _synthetic_audit():
    def src(source_id, trust, necessity, scrapable):
        return {"source_id": source_id, "trust": trust, "necessity": necessity, "scrapable": scrapable}

    return {
        "sources": [
            src("official_pass", "官方", "已发生（宏观数据发布）", "能"),
            src("official_agentic", "官方", "将发生（官方日历）", "不能"),
            src("mainstream_remove", "主流", "已发生 + 被相信（市场新闻）", "能"),
            src("weak_drop", "弱", "被相信（社交叙事）", "存疑"),
            src("useless_drop", "官方", "其他无关供给", "能"),
        ]
    }


def _write_policy(tmp_path):
    policy_md = (
        "# 测试政策\n"
        "```json\n"
        + json.dumps(
            {
                "schema_version": "layer2_three_tests_policy_v1",
                "reliable_trust_values": ["官方"],
                "necessary_category_keywords": ["已发生", "将发生", "被相信", "规则语境", "历史语境"],
                "dead_simple_scrapable_values": ["能"],
                "verdict_decision": {
                    "not_necessary": "弃用",
                    "reliable_and_dead_simple": "pass",
                    "reliable_not_dead_simple": "转agentic",
                    "not_reliable_dead_simple": "撤出",
                    "not_reliable_not_dead_simple": "弃用",
                },
            },
            ensure_ascii=False,
        )
        + "\n```\n"
    )
    policy_path = tmp_path / "three_tests_policy.md"
    policy_path.write_text(policy_md, encoding="utf-8")
    return policy_path


def test_three_tests_synthetic_audit_verdicts_and_removals(tmp_path):
    output_dir = tmp_path / "out"
    report = three_tests.run_three_tests(
        _synthetic_audit(),
        output_dir=output_dir,
        policy_path=_write_policy(tmp_path),
    )

    by_source = {item["source"]: item for item in report["sources"]}
    assert by_source["official_pass"]["verdict"] == "pass"
    assert by_source["official_agentic"]["verdict"] == "转agentic"
    assert by_source["mainstream_remove"]["verdict"] == "撤出"
    assert by_source["weak_drop"]["verdict"] == "弃用"
    assert by_source["useless_drop"]["verdict"] == "弃用"

    assert by_source["official_pass"]["reliable"] is True
    assert by_source["official_pass"]["necessary"] is True
    assert by_source["official_pass"]["dead_simple"] is True

    removal = json.loads((output_dir / "sources_to_remove.json").read_text(encoding="utf-8"))
    removed_sources = {item["source"] for item in removal["sources"]}
    assert "official_pass" not in removed_sources
    assert "mainstream_remove" in removed_sources  # 撤出源必须进名单
    assert {"official_agentic", "weak_drop", "useless_drop"} <= removed_sources
    assert (output_dir / "layer2_three_tests_report.json").is_file()


def test_three_tests_policy_is_machine_readable():
    policy_path = SCRIPTS_DIR / "layer2_supplement_prototype" / "three_tests_policy.md"
    policy = three_tests.load_policy(policy_path)
    assert policy["reliable_trust_values"] == ["官方", "授权"]
    assert "已发生" in policy["necessary_category_keywords"]
    assert policy["dead_simple_scrapable_values"] == ["能"]
    assert policy["verdict_decision"]["reliable_and_dead_simple"] == "pass"
    assert policy["verdict_decision"]["not_reliable_dead_simple"] == "撤出"
    assert policy["owner_overrides"]["alpha_vantage_news_sentiment"]["verdict"] == "挂起"


def test_three_tests_load_policy_rejects_bad_owner_override(tmp_path):
    import pytest

    bad_policy = tmp_path / "bad_policy.md"
    bad_policy.write_text(
        "# 坏政策\n```json\n"
        + json.dumps(
            {
                "reliable_trust_values": ["官方"],
                "necessary_category_keywords": ["已发生"],
                "dead_simple_scrapable_values": ["能"],
                "verdict_decision": {
                    "not_necessary": "弃用",
                    "reliable_and_dead_simple": "pass",
                    "reliable_not_dead_simple": "转agentic",
                    "not_reliable_dead_simple": "撤出",
                    "not_reliable_not_dead_simple": "弃用",
                },
                "owner_overrides": {"bad_source": {"verdict": "非法处置"}},
            },
            ensure_ascii=False,
        )
        + "\n```\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="owner_overrides"):
        three_tests.load_policy(bad_policy)


def test_three_tests_real_policy_wind_pass_and_alpha_suspended(tmp_path):
    audit_path = (
        SCRIPTS_DIR.parents[0]
        / "investigation_reports"
        / "20260811_layer2_research"
        / "baseline"
        / "sources_audit.json"
    )
    policy_path = SCRIPTS_DIR / "layer2_supplement_prototype" / "three_tests_policy.md"
    output_dir = tmp_path / "out"

    report = three_tests.run_three_tests(audit_path, output_dir=output_dir, policy_path=policy_path)
    by_source = {item["source"]: item for item in report["sources"]}

    # Wind 两源 pass 来自 owner_overrides，机器初判为转agentic。
    assert by_source["wind_company_announcements_m7"]["verdict"] == "pass"
    assert by_source["wind_financial_news_ndx"]["verdict"] == "pass"
    assert by_source["wind_company_announcements_m7"]["machine_verdict"] == "转agentic"
    assert by_source["wind_financial_news_ndx"]["machine_verdict"] == "转agentic"

    # alpha_vantage 挂起，且挂起不进 sources_to_remove。
    assert by_source["alpha_vantage_news_sentiment"]["verdict"] == "挂起"

    removal = json.loads((output_dir / "sources_to_remove.json").read_text(encoding="utf-8"))
    removed_sources = {item["source"] for item in removal["sources"]}
    assert "alpha_vantage_news_sentiment" not in removed_sources
    assert "wind_company_announcements_m7" not in removed_sources
    assert "wind_financial_news_ndx" not in removed_sources
