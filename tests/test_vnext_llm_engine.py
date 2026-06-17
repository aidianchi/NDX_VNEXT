# tests/test_vnext_llm_engine.py
import sys
import os
from typing import Any, Dict, List
import requests

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


def test_llm_engine_importable():
    from agent_analysis.llm_engine import LLMEngine


def test_system_constraints_loaded_from_file():
    """SYSTEM_CONSTRAINTS must be loaded from external prompt file, not hardcoded."""
    from agent_analysis.llm_engine import LLMEngine
    # Reset cached value to force reload from file
    LLMEngine.SYSTEM_CONSTRAINTS = ""
    constraints = LLMEngine._load_system_constraints()
    assert len(constraints) > 100, "SYSTEM_CONSTRAINTS should be loaded from file"
    assert "编造" in constraints
    assert "evidence_refs" in constraints
    assert "JSON" in constraints


def test_system_constraints_contains_five_rules():
    """SYSTEM_CONSTRAINTS must contain all 5 anti-fabrication rules."""
    from agent_analysis.llm_engine import LLMEngine
    constraints = LLMEngine._load_system_constraints()
    assert "历史胜率" in constraints or "回测收益" in constraints
    assert "点位" in constraints or "跌幅" in constraints
    assert "条件语言" in constraints or "若" in constraints
    assert "evidence_refs" in constraints
    assert "JSON" in constraints
    assert LLMEngine is not None


def test_token_tracking():
    from agent_analysis.llm_engine import LLMEngine
    engine = LLMEngine(available_models=[])
    engine.token_usage["stage_A"] = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
    engine.token_usage["stage_B"] = {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}
    report = engine.get_token_report()
    assert report["stage_A"]["total_tokens"] == 15
    assert report["stage_B"]["total_tokens"] == 30


# ---------------------------------------------------------------------------
# DeepSeek /beta + JSON Output regression tests
# ---------------------------------------------------------------------------


class _RecordingChatCompletions:
    def __init__(self):
        self.last_kwargs: Dict[str, Any] = {}
        self.response_content = '"bridge_type": "macro_valuation"\n}'

    def create(self, **kwargs):
        self.last_kwargs = kwargs

        class _Msg:
            def __init__(self, content: str):
                self.content = content

        class _Choice:
            def __init__(self, content: str):
                self.message = _Msg(content)

        class _Usage:
            def __init__(self):
                self.prompt_tokens = 1
                self.completion_tokens = 1
                self.total_tokens = 2

        class _Resp:
            def __init__(self, content: str):
                self.choices = [_Choice(content)]
                self.usage = _Usage()

        return _Resp(self.response_content)


class _RecordingClient:
    def __init__(self, base_url: str):
        self.base_url = base_url
        chat = type("Chat", (), {})()
        chat.completions = _RecordingChatCompletions()
        self.chat = chat


def _patch_engine_dependencies(monkeypatch, fake_base_url: str):
    """Make LLMEngine init succeed without a real network or API key."""
    from agent_analysis import llm_engine as engine_mod

    monkeypatch.setattr(engine_mod, "get_api_key", lambda service: "fake-key")
    monkeypatch.setattr(engine_mod, "get_base_url", lambda service: fake_base_url)
    monkeypatch.setattr(engine_mod, "get_extra_headers", lambda service: None)
    monkeypatch.setattr(engine_mod, "get_requests_proxies", lambda service: None)

    captured: List[Dict[str, Any]] = []

    def fake_openai(**kwargs):
        captured.append(kwargs)
        return _RecordingClient(kwargs.get("base_url", ""))

    monkeypatch.setattr(engine_mod, "OpenAI", fake_openai)
    return captured


def test_deepseek_client_promotes_default_base_url_to_beta(monkeypatch):
    captured = _patch_engine_dependencies(monkeypatch, "https://api.deepseek.com")
    from agent_analysis.llm_engine import LLMEngine

    engine = LLMEngine(available_models=["deepseek-v4-flash"])

    assert "deepseek" in engine.clients
    assert engine.clients["deepseek"].base_url == "https://api.deepseek.com/beta", (
        "DeepSeek client must initialize with /beta so strict tool calls"
        " are available; the production URL alone disables every Beta capability."
    )
    assert any(c.get("base_url") == "https://api.deepseek.com/beta" for c in captured)


def test_deepseek_client_does_not_double_promote_explicit_beta(monkeypatch):
    _patch_engine_dependencies(monkeypatch, "https://api.deepseek.com/beta")
    from agent_analysis.llm_engine import LLMEngine

    engine = LLMEngine(available_models=["deepseek-v4-flash"])
    assert engine.clients["deepseek"].base_url == "https://api.deepseek.com/beta"


def test_deepseek_client_respects_self_hosted_base_url(monkeypatch):
    _patch_engine_dependencies(monkeypatch, "https://internal.example.com/deepseek")
    from agent_analysis.llm_engine import LLMEngine

    engine = LLMEngine(available_models=["deepseek-v4-flash"])
    # Custom endpoints must NOT be silently rewritten to /beta — operators may have routed
    # through a proxy or a self-hosted gateway.
    assert engine.clients["deepseek"].base_url == "https://internal.example.com/deepseek"
    assert engine.service_beta_features["deepseek"] is False


def test_call_ai_uses_json_output_without_prefix_for_deepseek(monkeypatch):
    _patch_engine_dependencies(monkeypatch, "https://api.deepseek.com")
    from agent_analysis.llm_engine import LLMEngine

    engine = LLMEngine(available_models=["deepseek-v4-flash"])
    engine.clients["deepseek"].chat.completions.response_content = '{"bridge_type": "macro_valuation"}'
    raw, _usage = engine._call_ai("hello", "deepseek-v4-flash", stage="bridge")

    sent = engine.clients["deepseek"].chat.completions.last_kwargs
    messages = sent["messages"]
    assert len(messages) == 2, "DeepSeek calls must have system + user messages"
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert all("prefix" not in message for message in messages)
    assert sent["response_format"] == {"type": "json_object"}

    assert raw is not None
    assert raw.lstrip().startswith("{"), (
        "Returned raw text should remain a complete JSON object from JSON Output mode."
    )


def test_call_ai_does_not_send_beta_prefix_to_custom_deepseek_endpoint(monkeypatch):
    _patch_engine_dependencies(monkeypatch, "https://internal.example.com/deepseek")
    from agent_analysis.llm_engine import LLMEngine

    engine = LLMEngine(available_models=["deepseek-v4-flash"])
    engine.clients["deepseek"].chat.completions.response_content = '{"ok": true}'
    raw, _usage = engine._call_ai("hello", "deepseek-v4-flash", stage="bridge")

    sent = engine.clients["deepseek"].chat.completions.last_kwargs
    messages = sent["messages"]
    assert len(messages) == 2
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert all("prefix" not in message for message in messages)
    assert raw == '{"ok": true}'


def test_extract_json_repairs_fullwidth_bracket_string_list_slip():
    from agent_analysis.llm_engine import LLMEngine

    engine = LLMEngine(available_models=[])
    payload = '{\n  "falsifiers": ["分层利差收窄且总量利差继续低位】\n}'

    parsed = engine.extract_json(payload, stage="bridge")

    assert parsed == {"falsifiers": ["分层利差收窄且总量利差继续低位"]}


def test_kimi_http_call_loads_system_constraints(monkeypatch):
    from agent_analysis import llm_engine as engine_mod
    from agent_analysis.llm_engine import LLMEngine

    monkeypatch.setattr(engine_mod, "get_api_key", lambda service: "fake-key")
    monkeypatch.setattr(engine_mod, "get_base_url", lambda service: "https://kimi.example.com")
    monkeypatch.setattr(engine_mod, "get_extra_headers", lambda service: {})
    monkeypatch.setattr(engine_mod, "get_requests_proxies", lambda: None)

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [{"message": {"content": '{"ok": true}'}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }

    class FakeSession:
        def __init__(self):
            self.last_payload = None
            self.trust_env = True

        def post(self, _url, **kwargs):
            self.last_payload = kwargs["json"]
            return FakeResponse()

    fake_session = FakeSession()
    monkeypatch.setattr(requests, "Session", lambda: fake_session)

    LLMEngine.SYSTEM_CONSTRAINTS = ""
    engine = LLMEngine(available_models=[])
    raw, usage = engine._call_kimi_http("{}", "kimi-test", 100)

    assert raw == '{"ok": true}'
    assert usage["total_tokens"] == 2
    messages = fake_session.last_payload["messages"]
    assert messages[0]["role"] == "system"
    assert "不得编造" in messages[0]["content"]
    assert messages[1] == {"role": "user", "content": "{}"}
