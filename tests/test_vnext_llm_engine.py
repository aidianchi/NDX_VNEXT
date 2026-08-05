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
            # 真实 API 明确拒绝"anyOf 但同级没有 type"的形态。object/array 分支
            # 都属于"探针验证过保留 anyOf 即可接受"的一类（object 分支来自解析
            # 后的嵌套模型，array 分支来自②新增的非必填容器可空处理）。
            if "anyOf" in node:
                assert node.get("type") is not None or any(
                    isinstance(b, dict)
                    and (b.get("type") in ("object", "array") or "properties" in b)
                    for b in node["anyOf"]
                ), f"裸 anyOf 且无 object/array 分支必须被 collapse: {node}"
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


def test_sanitize_marks_default_factory_list_fields_nullable():
    """红灯：`required` 必须覆盖 object 全部 properties 是 DeepSeek 硬要求，改不了，
    但这把每个 `List[X] = Field(default_factory=list)` 字段都逼成"必须交出非空
    数组"——模型没有真实第三条跨层支撑关系时，也只能为这个字段编一条凑数。
    放开这些字段可取 null，模型返回 null 时 pydantic 端 `default_factory=list`
    会兜回 `[]`，contracts.py 和下游消费代码不用改一行。

    用 BridgeMemo.cross_layer_claims（真实契约里的 default_factory=list 字段）
    做端到端断言：原始 schema 里它不在 required、且是裸 array；sanitize 之后必须
    仍在 required 里（硬要求不能违反），但字段本身的 schema 必须从裸 array 变成
    `anyOf: [原 array schema, {"type": "null"}]`。"""
    from agent_analysis.contracts import BridgeMemo
    from agent_analysis.llm_engine import sanitize_json_schema_for_strict_tool_calling

    raw_schema = BridgeMemo.model_json_schema()
    # 前提核实：cross_layer_claims 确实是 default_factory=list 字段——pydantic
    # 没把它列进 required，且它的原始类型是裸 array（不是 anyOf）。
    assert "cross_layer_claims" not in raw_schema.get("required", [])
    assert raw_schema["properties"]["cross_layer_claims"].get("type") == "array"

    sanitized = sanitize_json_schema_for_strict_tool_calling(raw_schema)

    assert "cross_layer_claims" in sanitized["required"], (
        "DeepSeek strict schema 硬要求 required 覆盖全部 properties，这条改不了"
    )
    field_schema = sanitized["properties"]["cross_layer_claims"]
    assert "anyOf" in field_schema, "非必填数组字段必须可取 null，否则模型被逼为空数组凑数"
    branch_types = {b.get("type") for b in field_schema["anyOf"] if isinstance(b, dict)}
    assert branch_types == {"array", "null"}, f"应恰好是 array/null 两个分支，实际 {branch_types}"

    # 原本就必填的数组字段（layers_connected，Field(..., min_length=2)）不应被
    # 放开成可空——只有 default_factory=list 的非必填字段才该变。
    layers_field = sanitized["properties"]["layers_connected"]
    assert "anyOf" not in layers_field
    assert layers_field.get("type") == "array"


def test_fix_anyof_does_not_collapse_array_null_into_type_array():
    """红灯：`fix_anyof` 把"anyOf 分支全是原始类型"塌缩成 `{"type": [...]}`
    这条 collapse 逻辑此前把 "array" 也当成原始类型——`Optional[List[str]]`
    （pydantic 输出 `anyOf: [{type:array,...}, {type:null}]`）因此会被塌缩成
    `{"type": ["array", "null"]}`。DeepSeek 探针实测对这个形态直接 400：
    `{"error":{"message":"unknown variant 'array', expected one of string,
    number, integer, boolean, null", ...}}`。而 `{"anyOf":[{"type":"array",
    "items":…},{"type":"null"}]}` 探针验证过是被接受的形态，所以正确修法是
    把 array（以及 object）排除出"可塌缩的原始类型"认定，保留 anyOf 结构，
    不是反过来把 array 也塌缩进 type 数组。

    这条在改 ②（非必填容器可空）之前就已经是潜伏雷——全仓当前没有一个
    `Optional[List[X]]` 字段，所以 0 命中；② 落地后 sanitize 会自己产出这种
    结构，必须先确认 fix_anyof 不会把它塌缩坏。"""
    from agent_analysis.llm_engine import sanitize_json_schema_for_strict_tool_calling

    raw_schema = {
        "type": "object",
        "properties": {
            "maybe_items": {
                "anyOf": [
                    {"type": "array", "items": {"type": "string"}},
                    {"type": "null"},
                ]
            }
        },
        "required": ["maybe_items"],
    }

    sanitized = sanitize_json_schema_for_strict_tool_calling(raw_schema)

    def walk(node):
        if isinstance(node, dict):
            type_value = node.get("type")
            if isinstance(type_value, list):
                assert "array" not in type_value and "object" not in type_value, (
                    f"塌缩出了非法的 type 数组 {type_value}——DeepSeek 探针实测对此类"
                    "形态直接 400：\"unknown variant 'array', expected one of string, "
                    f"number, integer, boolean, null\"。节点：{node}"
                )
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for item in node:
                walk(item)

    walk(sanitized)

    # 且必须仍然可用：anyOf 结构原样保留，array 分支还在。
    field_schema = sanitized["properties"]["maybe_items"]
    assert "anyOf" in field_schema
    assert any(isinstance(b, dict) and b.get("type") == "array" for b in field_schema["anyOf"])


def test_normalize_none_list_fields_turns_default_factory_null_into_empty_list():
    """红灯：`sanitize_json_schema_for_strict_tool_calling` 把
    `BridgeMemo.cross_layer_claims`（`default_factory=list`，非必填）在发往
    DeepSeek 的 schema 里改写成可以取 `null`——但 pydantic 的
    `List[X] = Field(default_factory=list)` **不接受显式 null**：
    `default_factory` 只在字段缺失时生效，收到 `{"cross_layer_claims": None}`
    会直接 `ValidationError`。真实代价：模型一旦老实按新 schema 返回 `null`
    （这正是①想鼓励的诚实留空），`model_cls.model_validate(...)` 会炸，被
    `_run_stage` 的 `except` 捕获记成 `schema_validation_error`，白烧一次
    重试——改动不但没生效，还比改之前更差。这个测试钉住"归一化把 null 收回
    成 []，校验必须通过"这条修复。"""
    from agent_analysis.contracts import BridgeMemo
    from agent_analysis.llm_engine import normalize_none_list_fields_for_strict_schema_validation

    payload = {
        "bridge_type": "macro_valuation",
        "layers_connected": ["L1", "L2"],
        "implication_for_ndx": "test",
        "cross_layer_claims": None,
        "conflicts": None,
    }
    normalized = normalize_none_list_fields_for_strict_schema_validation(BridgeMemo, payload)
    assert normalized["cross_layer_claims"] == []
    assert normalized["conflicts"] == []

    # 归一化之后必须能通过真实校验——这才是这条修复真正要保证的结果，不是
    # 只看归一化函数本身的输出。
    validated = BridgeMemo.model_validate(normalized)
    assert validated.cross_layer_claims == []
    assert validated.conflicts == []


def test_normalize_none_list_fields_recurses_into_nested_contract_lists():
    """红灯：197 处受影响站点大多在 `$defs` 的嵌套契约里——例如
    `BridgeMemo.typed_conflicts[].evidence_refs`（`TypedConflict.evidence_refs`
    同样是 `default_factory=list`）。如果归一化只处理顶层字段、不递归进嵌套
    模型列表，这些嵌套字段收到 `null` 时依然会在校验阶段炸掉，① 的效果只在
    顶层生效、嵌套一层就失效。用真实契约的嵌套层级钉住"必须递归"这条要求。"""
    from agent_analysis.contracts import BridgeMemo
    from agent_analysis.llm_engine import normalize_none_list_fields_for_strict_schema_validation

    payload = {
        "bridge_type": "macro_valuation",
        "layers_connected": ["L1", "L2"],
        "implication_for_ndx": "test",
        "typed_conflicts": [
            {
                "conflict_id": "conflict:1",
                "conflict_type": "valuation_discount_rate",
                "severity": "high",
                "description": "desc",
                "implication": "implication",
                "involved_layers": None,
                "evidence_refs": None,
                "event_refs": None,
                "falsifiers": None,
            }
        ],
    }
    normalized = normalize_none_list_fields_for_strict_schema_validation(BridgeMemo, payload)
    nested = normalized["typed_conflicts"][0]
    assert nested["involved_layers"] == []
    assert nested["evidence_refs"] == []
    assert nested["event_refs"] == []
    assert nested["falsifiers"] == []

    validated = BridgeMemo.model_validate(normalized)
    assert validated.typed_conflicts[0].evidence_refs == []


def test_normalize_none_list_fields_does_not_swallow_required_array_null():
    """红灯反例（这条最重要，判据不能放宽）：`BridgeMemo.layers_connected` 是
    必填数组（`Field(..., min_length=2)`），不在 `sanitize_json_schema_for_
    strict_tool_calling` 放开 null 的字段集合里——它从未被允许在 schema 里取
    null。模型如果对它返回 `null`，说明输出本身坏了（不是"诚实留空"，跨层
    分析必须至少连两层），必须仍然校验失败，不能被这层归一化悄悄吞成 `[]`。
    判据是"该字段有默认值 + 非 Optional 的 list 类型"两者同时满足，
    `layers_connected` 没有默认值（必填），天然不落进这个集合。"""
    from agent_analysis.contracts import BridgeMemo
    from agent_analysis.llm_engine import normalize_none_list_fields_for_strict_schema_validation

    payload = {
        "bridge_type": "macro_valuation",
        "layers_connected": None,
    }
    normalized = normalize_none_list_fields_for_strict_schema_validation(BridgeMemo, payload)
    assert normalized["layers_connected"] is None, (
        "必填数组字段收到 null 必须原样保留（不能被吞成 []），让 pydantic 去报错"
    )

    import pytest
    with pytest.raises(Exception):
        BridgeMemo.model_validate(normalized)


def test_normalize_none_list_fields_leaves_missing_fields_for_default_factory():
    """回归护栏：payload 里字段本来就缺失（模型没提这个 key，而不是显式给
    null）时，归一化不能替它补上任何值——必须原样让 pydantic 的
    `default_factory=list` 接管，这是改动前就有的行为，不该被这次改动动到。"""
    from agent_analysis.contracts import BridgeMemo
    from agent_analysis.llm_engine import normalize_none_list_fields_for_strict_schema_validation

    payload = {
        "bridge_type": "macro_valuation",
        "layers_connected": ["L1", "L2"],
        "implication_for_ndx": "test",
        # cross_layer_claims 字段完全缺失，不是 null
    }
    normalized = normalize_none_list_fields_for_strict_schema_validation(BridgeMemo, payload)
    assert "cross_layer_claims" not in normalized, "缺失字段不应被归一化函数补写"

    validated = BridgeMemo.model_validate(normalized)
    assert validated.cross_layer_claims == []


def test_call_ai_uses_strict_tool_calling_when_schema_provided(monkeypatch):
    """`strict_tool_schema` 传入时：走 tools/tool_choice 路径；返回值取自
    tool_calls[0].function.arguments，不是 message.content——这样上游
    `_run_stage` 的 JSON 解析/pydantic 校验管线完全不用改，strict 模式只影响
    "怎么拿到合法文本"这一步。

    2026-07-31 任务 B 改判：两把锁必须叠加，不是二选一。旧版本这里断言
    "不应同时发送 response_format"——但 tool_choice="auto" 允许模型不调用工具、
    径直改回普通文本作答，这一放行恰好摘掉了表单锁，若语法锁
    （response_format=json_object）也被 elif 摘掉，就是一层保护都不剩：
    event_section_summary 真实事故（run 20260731_002156）连续两次因未转义
    半角双引号 parse_error，走的正是这条路。真实 API 探针验证 tools+strict+
    tool_choice=auto 同时带 response_format=json_object 会被接受，唯一硬条件是
    system+user 消息合并后必须含 "json" 字样——系统约束文件本身就含
    "JSON"（见 test_system_constraints_loaded_from_file），所以这里必然满足。"""
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
    assert sent.get("response_format") == {"type": "json_object"}, (
        "两把锁必须叠加：strict 工具锁不放松，同时必须叠加语法锁，否则"
        "tool_choice='auto' 让模型不调用工具时会一层保护都不剩"
    )
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


def test_call_ai_strict_tool_calling_skips_response_format_without_json_keyword(monkeypatch):
    """任务 B 的防御分支：真实 API 探针证实叠加 response_format=json_object 有一个
    硬条件——system+user 两条消息合并后必须出现 "json" 字样（不区分大小写），
    否则 400 `Prompt must contain the word 'json' in some form...`。生产环境里
    系统约束文件与四个真实 stage 提示词都天然满足这个条件，但代码不能假设"永远
    满足"，必须在发请求前真的检查，不满足就不加这把锁、退回现状——绝不能让这个
    改动本身直接把某一站打成 400。这里用一个不含 "json" 字样的假 system 约束
    + 不含 "json" 的 prompt，验证 response_format 确实被跳过，tools/tool_choice
    这把表单锁不受影响。"""
    _patch_engine_dependencies(monkeypatch, "https://api.deepseek.com")
    from agent_analysis.llm_engine import LLMEngine

    monkeypatch.setattr(
        LLMEngine,
        "SYSTEM_CONSTRAINTS",
        "你不得编造历史胜率、点位或概率数字，必须使用条件语言。",
    )

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
    raw, _usage = engine._call_ai(
        "没有那个词的用户提示", "deepseek-v4-flash", stage="bridge",
        strict_tool_schema=schema, strict_tool_name="emit_bridge_memo",
    )

    sent = engine.clients["deepseek"].chat.completions.last_kwargs
    assert "response_format" not in sent, (
        "system+user 都不含 'json' 字样时必须跳过 response_format，否则真实 API 会 400"
    )
    assert sent["tool_choice"] == "auto", "防御分支不能连带摘掉表单锁"
    assert sent["tools"][0]["function"]["name"] == "emit_bridge_memo"
    assert raw == '{"bridge_type": "macro_valuation"}'


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


# ---------------------------------------------------------------------------
# T44④：prompt cache 命中留痕。0 的语义是"确认没命中"，None 的语义是"provider
# 根本没告诉我们"——两者不可混淆，未提供时必须记 None，不能悄悄填 0 冒充。
# ---------------------------------------------------------------------------


def test_call_ai_records_prompt_cache_hit_tokens_when_provider_returns_it(monkeypatch):
    _patch_engine_dependencies(monkeypatch, "https://api.deepseek.com")
    from agent_analysis.llm_engine import LLMEngine

    engine = LLMEngine(available_models=["deepseek-v4-flash"])
    completions = engine.clients["deepseek"].chat.completions
    completions.response_content = '{"ok": true}'

    def create_with_cache(**kwargs):
        completions.last_kwargs = kwargs

        class _Msg:
            def __init__(self, content: str):
                self.content = content

        class _Choice:
            def __init__(self, content: str):
                self.message = _Msg(content)

        class _Usage:
            def __init__(self):
                self.prompt_tokens = 100
                self.completion_tokens = 20
                self.total_tokens = 120
                self.prompt_cache_hit_tokens = 64

        class _Resp:
            def __init__(self, content: str):
                self.choices = [_Choice(content)]
                self.usage = _Usage()

        return _Resp(completions.response_content)

    monkeypatch.setattr(completions, "create", create_with_cache)
    _raw, usage = engine._call_ai("hello", "deepseek-v4-flash", stage="bridge")

    assert usage.get("prompt_cache_hit_tokens") == 64


def test_call_ai_prompt_cache_hit_tokens_is_none_when_provider_omits_it(monkeypatch):
    """provider 没返回缓存命中字段时必须记 None，不能悄悄填 0 冒充"确认没命中"。"""
    _patch_engine_dependencies(monkeypatch, "https://api.deepseek.com")
    from agent_analysis.llm_engine import LLMEngine

    engine = LLMEngine(available_models=["deepseek-v4-flash"])
    # 默认 _RecordingChatCompletions._Usage 不带 prompt_cache_hit_tokens 属性，
    # 模拟"这个 provider/这次响应压根没给这个字段"。
    engine.clients["deepseek"].chat.completions.response_content = '{"ok": true}'
    _raw, usage = engine._call_ai("hello", "deepseek-v4-flash", stage="bridge")

    assert "prompt_cache_hit_tokens" in usage
    assert usage["prompt_cache_hit_tokens"] is None
