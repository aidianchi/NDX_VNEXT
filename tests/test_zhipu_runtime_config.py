# -*- coding: utf-8 -*-
"""全链智谱 GLM 选项的运行时配置测试。

边界口径（老板 2026-08-27）：
- 新增"全链 GLM"供应商预设；默认仍是 DeepSeek，逐字节不变。
- 选了 zhipu 就整份名单只有 GLM，绝不混挂、不回落 deepseek。
- dsh 二档调查员走独立 deepseek_harness 管道，锁死 deepseek-v4-flash，不许动。
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def _services():
    from api_config import DEFAULT_API_CONFIG, normalize_api_config

    return normalize_api_config(DEFAULT_API_CONFIG)["services"]


# ---------------------------------------------------------------------------
# 注册表：插座就位，deepseek 原样
# ---------------------------------------------------------------------------


def test_zhipu_service_registered_and_enabled():
    services = _services()
    zhipu = services["zhipu"]
    assert zhipu["enabled"] is True
    assert zhipu["transport"] == "openai_compatible"
    assert zhipu["env_key"] == "ZHIPU_API_KEY"
    assert zhipu["base_url_env_key"] == "ZHIPU_BASE_URL"
    assert zhipu["base_url"] == "https://open.bigmodel.cn/api/paas/v4"


def test_deepseek_service_unchanged():
    services = _services()
    deepseek = services["deepseek"]
    assert deepseek["enabled"] is True
    assert deepseek["base_url"] == "https://api.deepseek.com"
    assert deepseek["env_key"] == "DEEPSEEK_API_KEY"
    model_keys = [m["key"] for m in deepseek["models"]]
    assert model_keys == ["deepseek-v4-flash", "deepseek-v4-pro"]


def test_glm_model_registered_in_model_configs():
    from config import MODEL_CONFIGS

    glm = MODEL_CONFIGS["glm-5.3-flash"]
    assert glm["service"] == "zhipu"
    assert glm["client"] == "openai_compatible"
    assert glm["model"] == "glm-5.3-flash"
    assert glm["max_tokens"] == 65536
    # deepseek 条目必须原样共存
    assert MODEL_CONFIGS["deepseek-v4-flash"]["service"] == "deepseek"
    assert MODEL_CONFIGS["deepseek-v4-pro"]["service"] == "deepseek"


def test_zhipu_coding_line_registered_as_separate_service():
    """编码套餐线：独立服务（独立接入地址/钥匙），同一模型 ID，绝不与标准线混挂。"""
    services = _services()
    coding = services["zhipu_coding"]
    assert coding["enabled"] is True
    assert coding["transport"] == "openai_compatible"
    assert coding["env_key"] == "ZHIPU_CODING_API_KEY"
    assert coding["base_url"] == "https://open.bigmodel.cn/api/coding/paas/v4"

    from config import MODEL_CONFIGS

    entry = MODEL_CONFIGS["glm-5.3-flash-coding"]
    assert entry["service"] == "zhipu_coding"
    # 远端模型 ID 与标准线同名；线路区别只体现在服务/base_url 层
    assert entry["model"] == "glm-5.3-flash"


def test_driver_provider_zhipu_coding_switches_roster_without_mixing(monkeypatch):
    main = _patch_resolver_availability(monkeypatch)
    monkeypatch.setenv("NDX_DRIVER_PROVIDER", "zhipu-coding")

    roster = main.resolve_available_models(None)
    assert roster == ["glm-5.3-flash-coding"]
    for key in roster:
        assert main.MODEL_CONFIGS[key]["service"] == "zhipu_coding"


# ---------------------------------------------------------------------------
# 供应商预设与切换：名单不混挂
# ---------------------------------------------------------------------------


def _patch_resolver_availability(monkeypatch):
    """让所有服务都视为可用——从而证明隔离来自预设表本身，不是 key 缺失。"""
    import main

    monkeypatch.setattr(main, "is_service_enabled", lambda service: True)
    monkeypatch.setattr(main, "get_api_key", lambda service: "fake-key")
    return main


def test_driver_provider_defaults_to_deepseek(monkeypatch):
    import main

    monkeypatch.delenv("NDX_DRIVER_PROVIDER", raising=False)
    assert main.resolve_driver_provider() == "deepseek"
    assert main.default_model_priority() == main.DEFAULT_MODEL_PRIORITY


def test_driver_provider_zhipu_switches_roster_without_mixing(monkeypatch):
    main = _patch_resolver_availability(monkeypatch)
    monkeypatch.setenv("NDX_DRIVER_PROVIDER", "zhipu")

    assert main.resolve_driver_provider() == "zhipu"
    roster = main.resolve_available_models(None)
    assert roster == ["glm-5.3-flash"]
    # 不混铁律：GLM 名单里不允许出现任何非 zhipu 服务模型
    for key in roster:
        assert main.MODEL_CONFIGS[key]["service"] == "zhipu"


def test_driver_provider_unknown_value_falls_back_to_deepseek(monkeypatch):
    main = _patch_resolver_availability(monkeypatch)
    monkeypatch.setenv("NDX_DRIVER_PROVIDER", "not-a-provider")

    assert main.resolve_driver_provider() == "deepseek"
    roster = main.resolve_available_models(None)
    assert roster == main.DEFAULT_MODEL_PRIORITY
    for key in roster:
        assert main.MODEL_CONFIGS[key]["service"] == "deepseek"


def test_explicit_models_override_beats_provider_preset(monkeypatch):
    main = _patch_resolver_availability(monkeypatch)
    monkeypatch.setenv("NDX_DRIVER_PROVIDER", "zhipu")

    assert main.resolve_available_models("deepseek-v4-flash") == ["deepseek-v4-flash"]


# ---------------------------------------------------------------------------
# 引擎闸门：GLM 走 json_object，绝不沾 DeepSeek 专属参数 / 工具调用
# ---------------------------------------------------------------------------


class _FakeUsage:
    prompt_tokens = 10
    completion_tokens = 5
    total_tokens = 15


class _FakeMessage:
    content = '{"ok": true}'


class _FakeChoice:
    message = _FakeMessage()


class _FakeResponse:
    usage = _FakeUsage()
    choices = [_FakeChoice()]


class _FakeCompletions:
    def __init__(self):
        self.kwargs = None

    def create(self, **kwargs):
        self.kwargs = kwargs
        return _FakeResponse()


class _FakeChat:
    def __init__(self):
        self.completions = _FakeCompletions()


class _FakeClient:
    def __init__(self):
        self.chat = _FakeChat()


def _engine_with_client(service_name: str):
    from agent_analysis.llm_engine import LLMEngine

    engine = LLMEngine(available_models=[])
    fake_client = _FakeClient()
    engine.clients[service_name] = fake_client
    return engine, fake_client


_PROBE_SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}


def test_glm_call_sends_json_object_but_never_deepseek_extras():
    engine, fake_client = _engine_with_client("zhipu")

    result, usage = engine._call_ai("{}", "glm-5.3-flash")

    assert result == '{"ok": true}'
    assert usage["total_tokens"] == 15
    sent = fake_client.chat.completions.kwargs
    assert sent["response_format"] == {"type": "json_object"}
    # DeepSeek 专属参数一个都不许出现：thinking/reasoning 会打崩 GLM 请求
    assert "reasoning_effort" not in sent
    assert "extra_body" not in sent
    # 严格工具调用是 DeepSeek Beta 特性，GLM 绝不发 tools
    assert "tools" not in sent
    assert "tool_choice" not in sent


def test_glm_strict_schema_request_still_never_receives_tools():
    """json 白名单扩大后 strict 也不得泄漏给 GLM（泄漏守卫）。"""
    engine, fake_client = _engine_with_client("zhipu")

    result, _ = engine._call_ai(
        "{}",
        "glm-5.3-flash",
        stage="probe",
        strict_tool_schema=_PROBE_SCHEMA,
        strict_tool_name="emit_probe",
    )

    assert result == '{"ok": true}'
    sent = fake_client.chat.completions.kwargs
    assert "tools" not in sent
    assert "tool_choice" not in sent
    assert sent["response_format"] == {"type": "json_object"}


def test_zhipu_coding_call_sends_json_object_but_never_deepseek_extras():
    """编码套餐线走引擎同样只拿 json_object 表单锁，无 DeepSeek 专属参数。"""
    engine, fake_client = _engine_with_client("zhipu_coding")

    result, _ = engine._call_ai("{}", "glm-5.3-flash-coding")

    assert result == '{"ok": true}'
    sent = fake_client.chat.completions.kwargs
    assert sent["response_format"] == {"type": "json_object"}
    assert "reasoning_effort" not in sent
    assert "extra_body" not in sent
    assert "tools" not in sent
    assert "tool_choice" not in sent


def test_deepseek_strict_schema_request_keeps_receiving_tools():
    """对称回归锚：同一调用在 deepseek 上仍走 strict tools（原行为不被误伤）。"""
    engine, fake_client = _engine_with_client("deepseek")

    result, _ = engine._call_ai(
        "{}",
        "deepseek-v4-pro",
        stage="probe",
        strict_tool_schema=_PROBE_SCHEMA,
        strict_tool_name="emit_probe",
    )

    assert result == '{"ok": true}'
    sent = fake_client.chat.completions.kwargs
    assert sent["tools"][0]["function"]["strict"] is True
    assert sent["tools"][0]["function"]["name"] == "emit_probe"
    assert sent["tool_choice"] == "auto"


def test_zhipu_client_endpoint_is_plain_no_beta_promotion(monkeypatch):
    """/beta 提升只属于 deepseek 服务；zhipu 用注册表的开放平台标准地址。"""
    from agent_analysis.llm_engine import LLMEngine

    monkeypatch.setenv("ZHIPU_API_KEY", "fake-zhipu-key")

    engine = LLMEngine(available_models=["glm-5.3-flash"])
    assert "zhipu" in engine.clients
    base_url = str(engine.clients["zhipu"].base_url).rstrip("/")
    assert base_url == "https://open.bigmodel.cn/api/paas/v4"
    assert "/beta" not in base_url
    # beta 特性开关不得被点亮
    assert not engine.service_beta_features.get("zhipu", False)


# ---------------------------------------------------------------------------
# dsh 二档调查员护栏：独立管道锁死 DeepSeek，主链换商不许波及
# ---------------------------------------------------------------------------


def test_dsh_runner_model_lock_untouched():
    from event_research.runner import MODEL

    assert MODEL == "deepseek-v4-flash"
