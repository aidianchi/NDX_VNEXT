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


# ---------------------------------------------------------------------------
# DeepSeek Strict Function Calling（Beta）试点：bridge 站点单点验证
#
# 背景（2026-07-26）：docs/2026-05-10_BRIDGE_JSON_RESILIENCE_AI_AUDIT.md 早已诊断
# 出 response_format=json_object 只保证合法 JSON、不保证 schema；DeepSeek 官方另有
# 一种 "Strict Function Calling (Beta)" 能让服务端 100% 保证输出符合 schema，但
# 当时只做了前置的 /beta 端点切换（`service_beta_features`），真正启用它的那一步
# 被搁置了两个半月。这批测试验证捡起来的实现：只在调用方显式传入 schema 时才
# 启用，其余路径逐字节不变。
# ---------------------------------------------------------------------------


def test_sanitize_json_schema_for_strict_tool_calling_meets_deepseek_requirements():
    """核实点：每个 object 类型必须 additionalProperties:false 且 properties 里
    的字段全部进 required；不支持 minLength/maxLength/minItems/maxItems。用
    BridgeMemo 的真实 schema（含 7 层嵌套 $defs）做端到端断言，不是只测一个
    简化的玩具 schema。

    2026-07-26 真实事故修正：首版曾以为"anyOf 原样保留即可"，被真实 API 调用
    证伪（run codex_strict_bridge_20260726_2032 两次尝试均因此 empty_response）。
    真实报错原文："Invalid tool parameters schema : field 'anyOf': missing
    field 'type'"。这条测试现在锁定修正后的真实规则，而不是最初的错误推断：
    Optional[原始类型] collapse 成 type 数组去掉 anyOf；Optional[嵌套模型] 保留
    anyOf 但 $ref 必须被解析内联，不能留着裸 $ref。"""
    from agent_analysis.contracts import BridgeMemo
    from agent_analysis.llm_engine import sanitize_json_schema_for_strict_tool_calling

    raw_schema = BridgeMemo.model_json_schema()
    # 核实测试的前提本身成立：原始 schema 确实带着 strict 模式不支持的东西，
    # 不是在测一个已经干净的输入。
    assert raw_schema.get("additionalProperties") is True
    assert "minItems" in raw_schema["properties"]["layers_connected"]
    # 核实修正前提：原始 schema 里 Optional[str] 字段确实是裸 anyOf（这正是
    # 被真实 API 拒绝的形态）。
    assert "anyOf" in raw_schema["$defs"]["TransmissionPath"]["properties"]["lag_hint"]

    sanitized = sanitize_json_schema_for_strict_tool_calling(raw_schema)

    def walk(node):
        if isinstance(node, dict):
            if node.get("type") == "object" and "properties" in node:
                assert node.get("additionalProperties") is False, node.get("title")
                assert set(node["required"]) == set(node["properties"].keys()), node.get("title")
            for banned in ("minLength", "maxLength", "minItems", "maxItems", "format"):
                assert banned not in node, f"{banned} survived in {node.get('title', node)}"
            # 裸 anyOf 节点（没有同级 type）不能survive——要么被 collapse 成
            # type 数组，要么其余分支已被解析成不含 anyOf 自身歧义的具体结构；
            # 真实 API 明确拒绝"anyOf 但同级没有 type"的形态。
            if "anyOf" in node:
                assert node.get("type") is not None or any(
                    isinstance(b, dict) and (b.get("type") == "object" or "properties" in b)
                    for b in node["anyOf"]
                ), f"裸 anyOf 且无 object 分支必须被 collapse: {node}"
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(sanitized)

    def find_ref_inside_anyof(node):
        """`$ref` 本身在 strict 模式下完全合法（普通 property 定义、array items
        引用 $defs 都没问题，真实 API 调用已验证）——只有出现在 anyOf 分支里的
        裸 $ref 才是问题，必须被解析内联。"""
        if isinstance(node, dict):
            branches = node.get("anyOf")
            if isinstance(branches, list) and any(isinstance(b, dict) and "$ref" in b for b in branches):
                return True
            return any(find_ref_inside_anyof(v) for v in node.values())
        if isinstance(node, list):
            return any(find_ref_inside_anyof(item) for item in node)
        return False

    assert not find_ref_inside_anyof(sanitized), "anyOf 分支里的 $ref 必须被解析内联，不能留着裸引用"

    # Optional[str]（lag_hint）：真实 API 验证过，collapse 成 type 数组、去掉 anyOf。
    transmission_path = sanitized["$defs"]["TransmissionPath"]
    lag_hint = transmission_path["properties"]["lag_hint"]
    assert "anyOf" not in lag_hint
    assert set(lag_hint["type"]) == {"string", "null"}
    assert "lag_hint" in transmission_path["required"]

    # Optional[PrincipalContradiction]（$ref + null）：保留 anyOf，$ref 已解析
    # 内联成实际 object 定义，且该内联对象本身也满足 additionalProperties:false。
    principal = sanitized["properties"]["principal_contradiction"]
    assert "anyOf" in principal
    object_branches = [b for b in principal["anyOf"] if isinstance(b, dict) and b.get("type") == "object"]
    assert len(object_branches) == 1
    assert object_branches[0]["additionalProperties"] is False
    assert "principal_contradiction" in sanitized["required"]


def test_call_ai_uses_strict_tool_calling_when_schema_provided(monkeypatch):
    """`strict_tool_schema` 传入时：走 tools/tool_choice 路径，不发送
    response_format；返回值取自 tool_calls[0].function.arguments，不是
    message.content——这样上游 `_run_stage` 的 JSON 解析/pydantic 校验管线完全
    不用改，strict 模式只影响"怎么拿到合法文本"这一步。"""
    _patch_engine_dependencies(monkeypatch, "https://api.deepseek.com")
    from agent_analysis.llm_engine import LLMEngine

    class _ToolCallChatCompletions(_RecordingChatCompletions):
        def create(self, **kwargs):
            self.last_kwargs = kwargs

            class _Function:
                def __init__(self, arguments):
                    self.arguments = arguments

            class _ToolCall:
                def __init__(self, arguments):
                    self.function = _Function(arguments)

            class _Msg:
                def __init__(self):
                    self.content = None
                    self.tool_calls = [_ToolCall('{"bridge_type": "macro_valuation"}')]

            class _Choice:
                def __init__(self):
                    self.message = _Msg()

            class _Usage:
                prompt_tokens = 3
                completion_tokens = 2
                total_tokens = 5

            class _Resp:
                def __init__(self):
                    self.choices = [_Choice()]
                    self.usage = _Usage()

            return _Resp()

    engine = LLMEngine(available_models=["deepseek-v4-flash"])
    engine.clients["deepseek"].chat.completions = _ToolCallChatCompletions()

    schema = {"type": "object", "properties": {"bridge_type": {"type": "string"}}, "additionalProperties": False, "required": ["bridge_type"]}
    raw, usage = engine._call_ai(
        "hello", "deepseek-v4-flash", stage="bridge",
        strict_tool_schema=schema, strict_tool_name="emit_bridge_memo",
    )

    sent = engine.clients["deepseek"].chat.completions.last_kwargs
    assert "response_format" not in sent, "strict 模式下不应同时发送 response_format=json_object"
    # 真实事故复现（2026-07-26，run codex_strict_bridge_20260726_2032）：强制指定
    # 单个函数名的 tool_choice 在 DeepSeek 默认开启的思考模式下会被拒绝
    # （"Thinking mode does not support this tool_choice"，真实 API 直接复现）。
    # "auto" 才是思考模式下可用的形态；只注册了一个工具时模型会正常调用它。
    assert sent["tool_choice"] == "auto"
    assert sent["tools"][0]["function"]["name"] == "emit_bridge_memo"
    assert sent["tools"][0]["function"]["strict"] is True
    assert sent["tools"][0]["function"]["parameters"] == schema
    assert raw == '{"bridge_type": "macro_valuation"}'
    assert usage["total_tokens"] == 5


def test_call_ai_without_strict_schema_is_byte_identical_to_before(monkeypatch):
    """不传 strict_tool_schema（默认值 None，绝大多数 stage 的真实调用方式）时，
    行为必须与试点之前完全一致——回归防护，试点改动不能悄悄影响其余任何 stage。"""
    _patch_engine_dependencies(monkeypatch, "https://api.deepseek.com")
    from agent_analysis.llm_engine import LLMEngine

    engine = LLMEngine(available_models=["deepseek-v4-flash"])
    engine.clients["deepseek"].chat.completions.response_content = '{"ok": true}'
    raw, _usage = engine._call_ai("hello", "deepseek-v4-flash", stage="critic")

    sent = engine.clients["deepseek"].chat.completions.last_kwargs
    assert sent["response_format"] == {"type": "json_object"}
    assert "tools" not in sent
    assert "tool_choice" not in sent
    assert raw == '{"ok": true}'


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


def test_extract_json_repairs_bare_percent_value_slip():
    from agent_analysis.llm_engine import LLMEngine

    engine = LLMEngine(available_models=[])
    # 真实事故样本：run 20260719_130534 续跑时 L5 输出裸百分比，两次尝试全灭。
    payload = '{\n  "core_facts": [\n    {\n      "metric": "QQQ OBV 20d Change",\n      "value": -26.58%\n    }\n  ]\n}'

    parsed = engine.extract_json(payload, stage="l5")

    assert parsed == {"core_facts": [{"metric": "QQQ OBV 20d Change", "value": "-26.58%"}]}
