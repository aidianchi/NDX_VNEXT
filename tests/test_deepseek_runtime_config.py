"""DeepSeek-only runtime configuration tests."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def test_default_ai_services_are_deepseek_only():
    from api_config import DEFAULT_API_CONFIG, normalize_api_config

    services = normalize_api_config(DEFAULT_API_CONFIG)["services"]

    assert services["deepseek"]["enabled"] is True
    assert services["chatai"]["enabled"] is False
    assert services["kimi"]["enabled"] is False


def test_deepseek_v4_calls_use_official_reasoning_parameters():
    from agent_analysis.llm_engine import LLMEngine

    class FakeUsage:
        prompt_tokens = 10
        completion_tokens = 5
        total_tokens = 15

    class FakeMessage:
        content = '{"ok": true}'

    class FakeChoice:
        message = FakeMessage()

    class FakeResponse:
        usage = FakeUsage()
        choices = [FakeChoice()]

    class FakeCompletions:
        def __init__(self):
            self.kwargs = None

        def create(self, **kwargs):
            self.kwargs = kwargs
            return FakeResponse()

    class FakeChat:
        def __init__(self):
            self.completions = FakeCompletions()

    class FakeClient:
        def __init__(self):
            self.chat = FakeChat()

    fake_client = FakeClient()
    engine = LLMEngine(available_models=[])
    engine.clients["deepseek"] = fake_client

    result, usage = engine._call_ai("{}", "deepseek-v4-pro")

    assert result == '{"ok": true}'
    assert usage["total_tokens"] == 15
    assert fake_client.chat.completions.kwargs["stream"] is False
    assert fake_client.chat.completions.kwargs["reasoning_effort"] == "high"
    assert fake_client.chat.completions.kwargs["extra_body"] == {"thinking": {"type": "enabled"}}
