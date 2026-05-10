# tests/test_vnext_llm_engine.py
import sys
import os
from typing import Any, Dict, List

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


def test_llm_engine_importable():
    print("\nTest: llm_engine importable")
    try:
        from agent_analysis.llm_engine import LLMEngine
        assert LLMEngine is not None
        print("[PASS] LLMEngine imported")
        return True
    except Exception as e:
        print(f"[FAIL] {e}")
        return False


def test_token_tracking():
    print("\nTest: token tracking")
    try:
        from agent_analysis.llm_engine import LLMEngine
        engine = LLMEngine(available_models=[])
        engine.token_usage["stage_A"] = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
        engine.token_usage["stage_B"] = {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}
        report = engine.get_token_report()
        assert report["stage_A"]["total_tokens"] == 15
        assert report["stage_B"]["total_tokens"] == 30
        print("[PASS] Token tracking works")
        return True
    except Exception as e:
        print(f"[FAIL] {e}")
        return False


def main():
    results = [
        ("importable", test_llm_engine_importable()),
        ("token_tracking", test_token_tracking()),
    ]
    passed = sum(1 for _, ok in results if ok)
    total = len(results)
    print(f"\nResults: {passed}/{total} passed")
    return passed == total


if __name__ == "__main__":
    exit(0 if main() else 1)


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
    assert len(messages) == 1, "DeepSeek JSON Output calls must not also send prefix completion"
    assert messages[0]["role"] == "user"
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
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
    assert all("prefix" not in message for message in messages)
    assert raw == '{"ok": true}'
