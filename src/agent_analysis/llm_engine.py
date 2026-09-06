# -*- coding: utf-8 -*-
"""
NDX Agent vNext SubAgent 架构 - LLM 引擎

本模块从 legacy analyzer 中提取了经过实战验证的 LLM 调用逻辑，
供 vNext SubAgent 层复用。

职责：
- 多模型 fallback（带 success memory）
- Token 使用统计
- JSON 提取（支持 __LOGIC__ 块和 debug 持久化）
- 调用前架构校验
"""

import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union, get_args, get_origin

# 尝试导入配置
try:
    from ..config import MODEL_CONFIGS, path_config
    from ..api_config import get_api_key, get_base_url, get_extra_headers, get_requests_proxies
except ImportError:
    from config import MODEL_CONFIGS, path_config
    from api_config import get_api_key, get_base_url, get_extra_headers, get_requests_proxies

# AI 客户端导入
try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logging.warning("OpenAI 库未安装")

try:
    from google import genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
    logging.warning("Google GenAI 库未安装")

try:
    from pydantic import BaseModel
except ImportError:  # pragma: no cover - 与 contracts.py 的降级路径保持一致
    BaseModel = None  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)


# DeepSeek Strict Function Calling（Beta）对 JSON Schema 的硬性要求。
#
# 【2026-07-26 首版曾写"anyOf 官方支持、不需要额外处理"——这条判断错了，已被真实
# API 调用证伪，在这里如实记录教训】：真实试点 run（`codex_strict_bridge_
# 20260726_2032`）里 bridge 两次尝试均 `empty_response`，用户反馈"anyOf 节点缺少
# 顶层 type"。用真实 API 直接复现（非猜测）：
#   `{'error': {'message': 'Invalid tool parameters schema : field `anyOf`:
#   missing field `type`', ...}}`
# 逐个 schema 形态实测（见 WORK_LOG 2026-07-26 记录），确认两类修法：
#   1) Optional[原始类型]（pydantic 生成 anyOf:[{type:T},{type:"null"}]）→
#      collapse 成 `{"type": [T, "null"]}`，整个去掉 anyOf。
#   2) Optional[嵌套模型/枚举]（pydantic 生成 anyOf:[{$ref:...},{type:"null"}]）→
#      把 $ref 解析并内联展开成实际的 object/enum 定义，保留 anyOf 结构，但
#      **不能**再加一个 sibling "type" 兜底（实测会撞另一条"An object with no
#      properties is not allowed"）。
#
# 同一批真实调用还额外发现一条独立问题：DeepSeek 的模型默认开启思考模式（哪怕不
# 显式请求），而思考模式下强制指定单个函数名的 tool_choice
# （`{"type":"function","function":{"name":...}}`）会被拒绝——"Thinking mode does
# not support this tool_choice"。实测 `tool_choice="auto"` 在思考模式下可用，且
# 只注册一个工具时模型会正常调用它；`_call_ai` 已相应改为 "auto"（见其实现），
# 不再强制指定函数名。
#
# 仍然成立、未被推翻的部分：不支持 minLength/maxLength/minItems/maxItems；
# "format" 不在官方支持类型清单内故剥离；每个 object 类型仍需
# additionalProperties:false + 全字段 required。
# 严格模式不接受"没有属性的 object"（实测报错 "An object with no properties is not
# allowed"），而 `Dict[str, Any]` 与 `extra="allow"` 恰好生成这种节点。2026-07-29 的
# 离线体检（T29）扫过全部 8 个 stage 契约，共 7 处命中，全是这一种；下表逐条登记，
# 新增一处而不登记就会被 test_strict_tool_schema_free_form_objects_are_registered 拦下。
#
# 值列写的是"这个字段由谁填"——因为它决定修法：代码填的字段本就不该出现在给模型的
# schema 里（`token_usage` 甚至在 orchestrator 里被强制置空），删掉即可；模型真会填的
# 才需要权衡。
STRICT_SCHEMA_FREE_FORM_OBJECTS: Dict[str, str] = {
    "LayerCard:$.$defs.CoreFact.properties.raw_data.anyOf[0]":
        "模型填。原始数据转存，vNext 主链不消费（只有 legacy_adapter 拿它做指标名匹配）",
    "CounterThesisDraft:$.properties.prompt_input_audit":
        "代码填（orchestrator.py:2544,2717）",
    "FinalAdjudication:$.$defs.ClaimLedger.properties.publish_gate":
        "代码填（orchestrator.py:3326）",
    "FinalAdjudication:$.properties.token_usage.anyOf[0]":
        "代码填（orchestrator.py:666），且模型若擅自填会被 :7187 强制置空",
    "FinalAdjudication:$.properties.claim_ledger.anyOf[0].properties.publish_gate":
        "代码填（同上，内联展开的第二处）",
    "AnalysisRevised:$.properties.rejected_critiques.anyOf[0].items":
        "代码填（orchestrator.py:5429）。2026-07-30：路径从 `.items` 变成"
        "`.anyOf[0].items`——该字段是 default_factory=list 且非必填，②落地后"
        "被包进 anyOf[array, null]，free-form object 挂在 array 分支里面，"
        "只是路径变了，字段身份和填法都没变",
    "AnalysisRevised:$.properties.degraded_fallback.anyOf[0]":
        "代码填（orchestrator.py:5433）",
}


def sanitize_json_schema_for_strict_tool_calling(schema: Dict[str, Any]) -> Dict[str, Any]:
    """把 pydantic `model_json_schema()` 的输出转换成 DeepSeek strict tool calling
    真实接受的形态（不是文档字面推断的形态——上面注释记录了两者的出入）。只改
    JSON Schema 本身（发给 API、用于约束模型输出的那份契约），不改任何 pydantic
    模型定义——`extra="allow"` 和 `Optional` 字段在 contracts.py 里保持原样，
    校验响应时 pydantic 仍按自己的规则走，两边互不影响。

    这个函数把"非必填的 array 字段"的 schema 放开成可空（见下方 `required` 分支
    的注释）；`normalize_none_list_fields_for_strict_schema_validation`（就在本
    文件下方）负责在 `model_cls.model_validate(...)` 之前把模型真返回的 `null`
    收回成 `[]`——两边是配对的一体两面，**删任何一半都会让另一半失效**：只放开
    这半边、不做那半边的归一化，模型一旦真的返回 `null`，pydantic 校验会直接
    炸（`default_factory=list` 不认显式 `None`），比不放开还差。
    """
    import copy

    def strip_and_require(node: Any) -> Any:
        if isinstance(node, dict):
            cleaned = {key: strip_and_require(value) for key, value in node.items()}
            for unsupported_key in ("minLength", "maxLength", "minItems", "maxItems", "format"):
                cleaned.pop(unsupported_key, None)
            if cleaned.get("type") == "object" and isinstance(cleaned.get("properties"), dict):
                # `required` 必须覆盖全部 properties 是 DeepSeek strict schema 的硬要求
                # （少列会 400），这条改不了。但覆盖之前记下原始 required——pydantic
                # 对 `List[X] = Field(default_factory=list)` 字段不会列进 required，
                # 这正是可以还给模型的空间：这些字段本来就允许"这次没有"，只是严格
                # schema 把"required + 只能是 array"这两条捆在一起，逼模型为空
                # 结果也要凑一条内容出来。
                #
                # 只处理原本非 required 的 array 容器字段：把它的 schema 从裸 array
                # 改写成 anyOf[原 array schema, {"type":"null"}]。DeepSeek 探针实测
                # 接受这种形态、且模型确实会返回 null；pydantic 端字段仍是
                # `default_factory=list`，收到 null 会走 default 变回 []——不用改
                # contracts.py 一行，只改发往 API 的 schema。
                #
                # 只处理 array，不处理 object：自由形态 object 由
                # STRICT_SCHEMA_FREE_FORM_OBJECTS 登记表单独管，这里不动它。
                original_required = set(cleaned.get("required") or [])
                properties = cleaned["properties"]
                for prop_name, prop_schema in properties.items():
                    if (
                        prop_name not in original_required
                        and isinstance(prop_schema, dict)
                        and prop_schema.get("type") == "array"
                    ):
                        properties[prop_name] = {"anyOf": [prop_schema, {"type": "null"}]}
                cleaned["additionalProperties"] = False
                cleaned["required"] = list(properties.keys())
            return cleaned
        if isinstance(node, list):
            return [strip_and_require(item) for item in node]
        return node

    basic = strip_and_require(schema)
    defs = basic.get("$defs", {}) if isinstance(basic.get("$defs"), dict) else {}

    def resolve_ref(ref: str) -> Any:
        name = ref.rsplit("/", 1)[-1]
        return copy.deepcopy(defs.get(name, {}))

    def fix_anyof(node: Any) -> Any:
        if isinstance(node, dict):
            fixed = {key: fix_anyof(value) for key, value in node.items()}
            branches = fixed.get("anyOf")
            if isinstance(branches, list):
                resolved: List[Any] = []
                for branch in branches:
                    if isinstance(branch, dict) and "$ref" in branch:
                        resolved.append(fix_anyof(resolve_ref(branch["$ref"])))
                    else:
                        resolved.append(branch)
                primitive_types: List[str] = []
                has_ref_or_object_branch = False
                for branch in resolved:
                    branch_type = branch.get("type") if isinstance(branch, dict) else None
                    # "array" 和 "object" 都必须排除出"可 collapse 的原始类型"认定。
                    # 潜伏雷（2026-07-30 修复）：这条 collapse 逻辑原本只为
                    # Optional[原始类型] 设计，但把 "array" 也当成了原始类型——
                    # Optional[List[X]] 产出的 `anyOf:[{type:array,...},{type:null}]`
                    # 会被塌缩成 `{"type":["array","null"]}`，探针实测被 DeepSeek 400
                    # 拒绝："unknown variant 'array', expected one of string, number,
                    # integer, boolean, null"。而 `{"anyOf":[{"type":"array",...},
                    # {"type":"null"}]}` 保留 anyOf 结构探针验证过是被接受的。全仓
                    # 当前对 array 分支是 0 命中（现有列表字段均非 Optional），是本
                    # 次改动②（非必填容器字段可空）之前就存在的潜伏风险，②落地后
                    # 就会真命中，所以必须同一次改掉。
                    if branch_type in ("object", "array") or (
                        isinstance(branch, dict) and "properties" in branch
                    ):
                        has_ref_or_object_branch = True
                    elif isinstance(branch_type, str):
                        primitive_types.append(branch_type)
                    else:
                        has_ref_or_object_branch = True
                if not has_ref_or_object_branch and primitive_types:
                    # Optional[原始类型/枚举] 且没有嵌套 object/array：collapse 成
                    # type 数组，整个去掉 anyOf——DeepSeek 对裸 anyOf 节点要求同级
                    # 必须有 type。
                    fixed.pop("anyOf")
                    fixed["type"] = primitive_types if len(primitive_types) > 1 else primitive_types[0]
                else:
                    # 含嵌套 object/array 的分支：保留 anyOf 结构、$ref 已内联展开，
                    # 不额外加 sibling type（object 分支会撞"object with no
                    # properties"；array 分支的 type 数组形态会被 400 拒绝）。
                    fixed["anyOf"] = resolved
            return fixed
        if isinstance(node, list):
            return [fix_anyof(item) for item in node]
        return node

    fixed = fix_anyof(basic)
    # 登记表里"代码填"的自由形态 object 本就不该出现在发给模型的 schema 里
    # （模型没机会填，DeepSeek 还会因 object 无 properties 直接 400）。这里按
    # 登记表的"代码填"标注，在 sanitize 后的树上按路径剪掉；"模型填"的自由对象
    # 原样保留（它们所在的 stage 要么不在严格白名单，要么需要进一步权衡）。
    _REMOVED = object()

    def prune(node: Any, path: str) -> Any:
        if isinstance(node, dict):
            cleaned = dict(node)
            if isinstance(cleaned.get("properties"), dict):
                props = dict(cleaned["properties"])
                for prop_name in list(props):
                    prop_path = f"{path}.properties.{prop_name}"
                    pruned = prune(props[prop_name], prop_path)
                    if pruned is _REMOVED:
                        props.pop(prop_name, None)
                    else:
                        props[prop_name] = pruned
                cleaned["properties"] = props
                # 剪掉字段后 required 必须与剩余 properties 同步，否则 provider 会拒
                # "required 未覆盖全部 properties"。
                if props:
                    cleaned["required"] = list(props.keys())
                else:
                    cleaned.pop("required", None)
            if isinstance(cleaned.get("anyOf"), list):
                branches = []
                for index, branch in enumerate(cleaned["anyOf"]):
                    pruned = prune(branch, f"{path}.anyOf[{index}]")
                    if pruned is not _REMOVED:
                        branches.append(pruned)
                if not branches:
                    return _REMOVED
                if len(branches) == 1 and isinstance(branches[0], dict) and branches[0].get("type") == "null":
                    return _REMOVED
                cleaned["anyOf"] = branches
            # 其余键（含 $defs 等嵌套定义）也要递归剪枝，路径与登记表逐段对齐。
            for key in list(cleaned):
                if key in {"properties", "anyOf"}:
                    continue
                pruned = prune(cleaned[key], f"{path}.{key}")
                if pruned is _REMOVED:
                    cleaned.pop(key, None)
                else:
                    cleaned[key] = pruned
            if cleaned.get("type") == "object" and "properties" not in cleaned:
                reason = next(
                    (
                        value
                        for key, value in STRICT_SCHEMA_FREE_FORM_OBJECTS.items()
                        if key.split(":", 1)[1] == path
                    ),
                    None,
                )
                if isinstance(reason, str) and reason.startswith("代码填"):
                    return _REMOVED
            return cleaned
        if isinstance(node, list):
            pruned_items = []
            for index, item in enumerate(node):
                pruned = prune(item, f"{path}[{index}]")
                if pruned is not _REMOVED:
                    pruned_items.append(pruned)
            return pruned_items
        return node

    return prune(fixed, "$")


def _optional_inner_type(annotation: Any) -> Tuple[Any, bool]:
    """把 `Optional[X]`（即 `Union[X, None]`）拆成 `(X, True)`；非 Optional 原样
    返回 `(annotation, False)`。只识别恰好两个分支且其中一个是 NoneType 的
    Union——这是 pydantic 对 `Optional[X]` 的标准展开形态。"""
    if get_origin(annotation) is Union:
        branches = [arg for arg in get_args(annotation) if arg is not type(None)]
        if len(branches) == 1 and type(None) in get_args(annotation):
            return branches[0], True
    return annotation, False


def _bare_list_item_type(annotation: Any) -> Optional[Any]:
    """`annotation` 是裸 `List[X]` / `list[X]`（未被 `Optional` 包裹）时返回 `X`，
    否则返回 `None`。`Optional[List[X]]` 的 `get_origin` 是 `Union` 而不是
    `list`，所以天然被排除——这正是判据要的"非 Optional 的 list 类型"。"""
    if get_origin(annotation) is list:
        args = get_args(annotation)
        return args[0] if args else Any
    return None


def _is_pydantic_model_type(candidate: Any) -> bool:
    return BaseModel is not None and isinstance(candidate, type) and issubclass(candidate, BaseModel)


def normalize_none_list_fields_for_strict_schema_validation(model_cls: Any, payload: Any) -> Any:
    """`sanitize_json_schema_for_strict_tool_calling` 那半边把"非必填的 array
    字段"（`default_factory=list`，因而不在原始 `required` 里）在发往 DeepSeek 的
    schema 里改写成 `anyOf[原 array schema, {"type":"null"}]`，让模型能诚实地
    返回 `null` 表示"这次真没有"。这半边负责把模型真返回的 `null` 收回来——
    **删掉任一半都会让另一半失效**：只放开 schema、不做这层归一化，模型一旦真
    按新 schema 返回 `null`，`model_cls.model_validate(...)` 会直接炸（`List[X] =
    Field(default_factory=list)` 只在字段**缺失**时走 default，显式 `None` 会被
    pydantic 拒绝——`default_factory` 不认 `None`），且被 `_run_stage` 的
    `except` 捕获记成 `schema_validation_error`，白烧一次重试，比改动前更差。

    判据（必须与 schema 侧那半边精确对齐，不多不少）：只对**同时满足**下列两条
    的字段做 `None -> []`——
      1) 该字段在 pydantic 模型里有默认值（`FieldInfo.is_required()` 为 False，
         覆盖 `default_factory=list` 和 `default=[]` 两种写法）；
      2) 其注解是**非 Optional** 的 `List[X]` / `list[X]`。
    必填数组字段（如 `BridgeMemo.layers_connected`，`Field(..., min_length=2)`）
    收到 `null` 必须仍然报错——那是模型输出坏了，不是"诚实留空"，不能被悄悄吞掉。

    无条件生效，不做"仅严格模式开启时才归一化"的开关：非严格模式下模型本来
    也偶尔会返回 `null` 表示"没有内容"，那是同一种合法表达；加开关只会让两条
    路径行为分叉、更难验证，所以两条路径统一走这一层归一化。

    递归处理嵌套模型和模型列表（197 处站点大多在 `$defs` 的嵌套契约里，例如
    `BridgeMemo.typed_conflicts[].evidence_refs`）——完全靠遍历
    `model_cls.model_fields` 的类型注解往下走，不靠字段名硬编码，因此新增字段
    不需要在这里登记。
    """
    if not isinstance(payload, dict):
        return payload
    model_fields = getattr(model_cls, "model_fields", None)
    if not model_fields:
        return payload

    normalized = dict(payload)
    for field_name, field_info in model_fields.items():
        if field_name not in normalized:
            continue
        value = normalized[field_name]
        annotation = field_info.annotation

        bare_item_type = _bare_list_item_type(annotation)
        if bare_item_type is not None:
            # 裸（非 Optional）List[X] 字段：满足判据条件②。条件①（非必填）
            # 决定 None 是否可以收回成 []；必填字段收到 None 原样放行，让
            # pydantic 去报错（这就是 layers_connected 反例要的行为）。
            if value is None:
                if not field_info.is_required():
                    normalized[field_name] = []
                continue
            if isinstance(value, list) and _is_pydantic_model_type(bare_item_type):
                normalized[field_name] = [
                    normalize_none_list_fields_for_strict_schema_validation(bare_item_type, item)
                    if isinstance(item, dict)
                    else item
                    for item in value
                ]
            continue

        if value is None:
            continue

        inner_type, was_optional = _optional_inner_type(annotation)
        if was_optional:
            optional_item_type = _bare_list_item_type(inner_type)
            if optional_item_type is not None:
                # Optional[List[X]]：null 在这里本来就是合法值（pydantic 天然
                # 接受），不需要、也不应该被收回成 []；但列表内部若是嵌套模型
                # 仍要继续往下递归。
                if isinstance(value, list) and _is_pydantic_model_type(optional_item_type):
                    normalized[field_name] = [
                        normalize_none_list_fields_for_strict_schema_validation(optional_item_type, item)
                        if isinstance(item, dict)
                        else item
                        for item in value
                    ]
                continue

        if _is_pydantic_model_type(inner_type) and isinstance(value, dict):
            normalized[field_name] = normalize_none_list_fields_for_strict_schema_validation(inner_type, value)

    return normalized


class LLMEngine:
    """可复用的 LLM 调用引擎（从 legacy analyzer 提取）"""

    def __init__(self, available_models: List[str], debug_dir: Optional[str] = None):
        self.available_models = available_models
        # B25：AI 响应解析失败的调试文件不再写仓库根目录。优先级：
        # 显式参数 > NDX_DEBUG_DIR 环境变量 > output/debug_archive/。
        self.debug_dir = debug_dir
        self.successful_model = None
        self.token_usage = {
            "total": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        }
        self.service_beta_features: Dict[str, bool] = {}
        self.clients = self._initialize_clients()

    def _initialize_clients(self) -> Dict:
        clients = {}
        initialized_services = set()

        for model_key in self.available_models:
            config = MODEL_CONFIGS.get(model_key, {})
            service_name = config.get("service")
            client_type = config.get("client")
            if not service_name or service_name in initialized_services:
                continue

            api_key = get_api_key(service_name)
            if not api_key:
                continue

            if client_type == "openai_compatible":
                base_url = get_base_url(service_name)
                if service_name == "deepseek":
                    base_url, beta_features_enabled = self._resolve_deepseek_base_url(base_url)
                    self.service_beta_features[service_name] = beta_features_enabled
                client_kwargs = {
                    "api_key": api_key,
                    "base_url": base_url,
                    # 2026-09-01（run 20260831_213827 教训）：SDK 默认 600 秒读超时对大桥段
                    # 不够用——bridge 提示词 15-23 万字符，glm-5.3-flash 服务端推理要 9 分钟
                    # 上下（08-27 编码套餐线 540 秒侥幸过关；08-31 开放平台线三次撞 600 秒线
                    # 空响应失败）。超时放宽到 1800 秒，`NDX_LLM_TIMEOUT` 可调。
                    "timeout": float(os.environ.get("NDX_LLM_TIMEOUT", "1800")),
                }
                extra_headers = get_extra_headers(service_name)
                if extra_headers:
                    client_kwargs["default_headers"] = extra_headers
                clients[service_name] = OpenAI(**client_kwargs)
                initialized_services.add(service_name)
            elif client_type == "gemini_sdk":
                try:
                    clients[service_name] = genai.Client(api_key=api_key)
                    initialized_services.add(service_name)
                    logger.info("%s 客户端已准备就绪。", service_name)
                except Exception as e:
                    logger.error(f"初始化 {service_name} 客户端时发生错误: {e}")
        return clients

    @staticmethod
    def _resolve_deepseek_base_url(base_url: Optional[str]) -> Tuple[Optional[str], bool]:
        """Switch the default DeepSeek production URL to /beta so strict tool calls can
        be enabled later. Custom or already-beta endpoints are kept as-is."""
        if not base_url:
            return base_url, False
        normalized = base_url.rstrip("/")
        if normalized == "https://api.deepseek.com":
            return "https://api.deepseek.com/beta", True
        if normalized == "https://api.deepseek.com/beta":
            return base_url, True
        return base_url, False

    @staticmethod
    def _promote_deepseek_base_url(base_url: Optional[str]) -> Optional[str]:
        promoted, _enabled = LLMEngine._resolve_deepseek_base_url(base_url)
        return promoted

    def _debug_dir(self) -> Path:
        """解析 AI 响应解析失败调试文件的落盘目录。

        选择（按优先级）：构造函数显式传入的 `debug_dir` > 环境变量
        `NDX_DEBUG_DIR` > `output/debug_archive/`。这样即使调用方没有 run 目录
        上下文，也不会再把调试文件写进仓库根目录。
        """
        if self.debug_dir:
            return Path(self.debug_dir)
        env_dir = os.environ.get("NDX_DEBUG_DIR")
        if env_dir:
            return Path(env_dir)
        return Path(path_config.output_dir) / "debug_archive"

    def _save_debug_response(self, stage: str, body: str) -> None:
        directory = self._debug_dir()
        debug_filename = f"ai_response_debug_{stage}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        try:
            directory.mkdir(parents=True, exist_ok=True)
            with open(directory / debug_filename, "w", encoding="utf-8") as f:
                f.write(body)
            logger.warning(f"  原始响应已保存至: {directory / debug_filename}")
        except Exception as save_error:
            logger.error(f"  无法保存调试文件: {save_error}")

    # System-level constraints loaded from external prompt file.
    # Falls back to inline string if file is missing.
    _SYSTEM_CONSTRAINTS_PATH = Path(__file__).with_name("prompts") / "system_constraints.md"
    SYSTEM_CONSTRAINTS: str = ""  # loaded in _load_system_constraints

    @classmethod
    def _load_system_constraints(cls) -> str:
        if cls.SYSTEM_CONSTRAINTS:
            return cls.SYSTEM_CONSTRAINTS
        try:
            cls.SYSTEM_CONSTRAINTS = cls._SYSTEM_CONSTRAINTS_PATH.read_text(encoding="utf-8").strip()
        except FileNotFoundError:
            # Fallback: inline constraints if external file is missing
            cls.SYSTEM_CONSTRAINTS = (
                "你是 NDX 投研分析系统的一部分。你必须遵守以下不可违反的纪律：\n"
                "1. 不得编造历史胜率、回测收益、样本区间或概率数字，除非输入数据明确提供。\n"
                "2. 不得编造点位、跌幅、估值倍数、盈利增速阈值或其他定量影响幅度。\n"
                "3. 没有证据时使用条件语言（'可能''若...则...'）或定性表达。\n"
                "4. 所有 evidence_refs 必须来自本次输入的 raw_data，不得凭记忆添加。\n"
                "5. 输出严格合法的 JSON，不要添加任何 JSON 之外的文本。"
            )
        return cls.SYSTEM_CONSTRAINTS

    def _call_ai(
        self,
        prompt: str,
        model_key: str,
        stage: str = "",
        strict_tool_schema: Optional[Dict[str, Any]] = None,
        strict_tool_name: Optional[str] = None,
    ) -> Tuple[Optional[str], Dict]:
        config = MODEL_CONFIGS[model_key]
        client_type = config["client"]
        service_name = config.get("service", "")
        model_name = config["model"]

        logger.info(f"  -> 正在使用 {config['name']} 进行分析...")

        try:
            if client_type == "openai_compatible" and service_name == "kimi":
                return self._call_kimi_http(prompt, model_name, config["max_tokens"])

            if client_type == "openai_compatible" and service_name in self.clients:
                # json_object 表单锁：deepseek / zhipu（开放平台线）/ zhipu_coding（编码套餐线）
                # 都支持 response_format=json_object，共用这条路径保证 JSON 可靠性；
                # 其余 openai 兼容服务维持纯文本+extract_json。
                use_json_output = service_name in ("deepseek", "zhipu", "zhipu_coding")
                # 严格工具调用（DeepSeek Beta strict function calling）是 DeepSeek 专属特性
                # （/beta 端点 + tools 内 strict 标记），显式只认 deepseek 服务——绝不能随
                # json 白名单扩大而泄漏给其他供应商（GLM 等不认这套会直接报错）。未传入
                # schema 时走原有 json_object 路径，逐字节不变。
                use_strict_tools = service_name == "deepseek" and strict_tool_schema is not None
                # Use system message for constraints (higher authority than user message)
                messages: List[Dict[str, Any]] = [
                    {"role": "system", "content": self._load_system_constraints()},
                    {"role": "user", "content": prompt},
                ]
                kwargs = {
                    "model": model_name,
                    "messages": messages,
                    "temperature": 0.2,
                    "max_tokens": config["max_tokens"],
                    "stream": False,
                }
                if use_strict_tools:
                    tool_name = strict_tool_name or "emit_structured_output"
                    kwargs["tools"] = [{
                        "type": "function",
                        "function": {
                            "name": tool_name,
                            "description": f"Emit the structured {stage or 'stage'} output.",
                            "parameters": strict_tool_schema,
                            "strict": True,
                        },
                    }]
                    # 真实 API 复现（2026-07-26）：DeepSeek v4 系列默认开启思考模式
                    # （即使不显式请求），思考模式下强制指定单个函数名的 tool_choice
                    # （{"type":"function","function":{"name":...}}）会被拒绝——
                    # "Thinking mode does not support this tool_choice"。"auto" 在
                    # 思考模式下可用；只注册了这一个工具时模型会正常调用它，若模型
                    # 选择不调用（tool_calls 为空），下方已有 content 兜底分支处理。
                    kwargs["tool_choice"] = "auto"
                    if model_name.startswith("deepseek-v4-"):
                        kwargs["reasoning_effort"] = "high"
                        kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
                    # 两把锁叠加，不是二选一：tool_choice="auto" 允许模型不调用工具、
                    # 改回普通文本作答，这时表单锁（strict tool schema）不生效，若语法锁
                    # （response_format=json_object）此前已被 elif 摘掉，就会出现一层
                    # 保护都不剩的真实事故（event_section_summary 未转义引号连挂两次，
                    # 见 2026-07-30 run 20260731_002156）。真实 API 探针验证：
                    # tools+strict+tool_choice=auto 同时带 response_format=json_object
                    # 会被接受，唯一硬条件是 system+user 两条消息合并后必须出现
                    # "json" 字样（不区分大小写），否则 400
                    # "Prompt must contain the word 'json' in some form..."。这里做防御：
                    # 不满足硬条件就不加这把锁，退回现状，绝不能让这个改动直接导致 400。
                    combined_message_text = f"{messages[0]['content']}\n{messages[1]['content']}"
                    if "json" in combined_message_text.lower():
                        kwargs["response_format"] = {"type": "json_object"}
                    else:
                        logger.warning(
                            "  ! [Stage: %s] strict tool 调用未叠加 response_format=json_object："
                            "system+user 消息都不含 'json' 字样，加上会被 API 判 400，故跳过。",
                            stage,
                        )
                elif use_json_output:
                    kwargs["response_format"] = {"type": "json_object"}
                    if model_name.startswith("deepseek-v4-"):
                        kwargs["reasoning_effort"] = "high"
                        kwargs["extra_body"] = {"thinking": {"type": "enabled"}}
                response = self.clients[service_name].chat.completions.create(**kwargs)

                usage = {}
                if hasattr(response, 'usage') and response.usage:
                    usage = {
                        "prompt_tokens": getattr(response.usage, 'prompt_tokens', 0),
                        "completion_tokens": getattr(response.usage, 'completion_tokens', 0),
                        "total_tokens": getattr(response.usage, 'total_tokens', 0),
                        # T44④：DeepSeek 等 provider 在 usage 里附带缓存命中 token 数；
                        # 没有这个属性时必须是 None（“不知道”），不能填 0（“确认没命中”）。
                        "prompt_cache_hit_tokens": getattr(response.usage, 'prompt_cache_hit_tokens', None),
                    }
                    logger.info(
                        f"  -> Token使用: 输入={usage['prompt_tokens']}, "
                        f"输出={usage['completion_tokens']}, 总计={usage['total_tokens']}"
                    )
                if use_strict_tools:
                    message = response.choices[0].message
                    tool_calls = getattr(message, "tool_calls", None) or []
                    if not tool_calls:
                        logger.warning(f"  ! [Stage: {stage}] strict tool call 未返回 tool_calls，退回 content。")
                        return message.content, usage
                    return tool_calls[0].function.arguments, usage
                return response.choices[0].message.content, usage

            elif client_type == "gemini_sdk" and service_name in self.clients:
                client = self.clients[service_name]
                response = client.models.generate_content(model=model_name, contents=prompt)
                usage = {}
                if hasattr(response, 'usage_metadata') and response.usage_metadata:
                    usage = {
                        "prompt_tokens": getattr(response.usage_metadata, 'prompt_token_count', 0),
                        "completion_tokens": getattr(response.usage_metadata, 'candidates_token_count', 0),
                        "total_tokens": getattr(response.usage_metadata, 'total_token_count', 0),
                        # T44④：Gemini 用 cached_content_token_count 表示上下文缓存命中；
                        # 没有该属性时记 None，不得用 0 冒充“确认没命中”。
                        "prompt_cache_hit_tokens": getattr(response.usage_metadata, 'cached_content_token_count', None),
                    }
                    logger.info(
                        f"  -> Token使用: 输入={usage['prompt_tokens']}, "
                        f"输出={usage['completion_tokens']}, 总计={usage['total_tokens']}"
                    )
                return response.text, usage
            else:
                logger.warning(f"客户端 {client_type} 未初始化或不可用。")
                return None, {}
        except Exception as e:
            logger.error(f"调用 {config['name']} 时出错: {type(e).__name__}: {str(e)[:200]}")
            return None, {}

    def _call_kimi_http(self, prompt: str, model_name: str, max_tokens: int) -> Tuple[Optional[str], Dict]:
        import requests
        api_key = get_api_key("kimi")
        base_url = get_base_url("kimi")
        if not api_key or not base_url:
            return None, {}

        headers = dict(get_extra_headers("kimi") or {})
        headers["Authorization"] = f"Bearer {api_key}"
        headers["Content-Type"] = "application/json"

        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": self._load_system_constraints()},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.2,
            "max_tokens": max_tokens,
            "stream": False,
        }

        proxies = get_requests_proxies()
        session = requests.Session()
        if proxies:
            response = session.post(
                base_url.rstrip("/") + "/chat/completions",
                headers=headers,
                json=payload,
                proxies=proxies,
                timeout=(30, 900),
            )
        else:
            session.trust_env = False
            response = session.post(
                base_url.rstrip("/") + "/chat/completions",
                headers=headers,
                json=payload,
                timeout=(30, 900),
            )
        response.raise_for_status()

        data = response.json()
        choice = ((data.get("choices") or [{}])[0]).get("message", {})
        content = choice.get("content")
        usage_raw = data.get("usage") or {}
        # T44④：字段本身没出现在响应里时必须是 None（“不知道”），不是 0（“确认没命中”）。
        raw_cache_hit = usage_raw.get("prompt_cache_hit_tokens")
        usage = {
            "prompt_tokens": int(usage_raw.get("prompt_tokens", 0) or 0),
            "completion_tokens": int(usage_raw.get("completion_tokens", 0) or 0),
            "total_tokens": int(usage_raw.get("total_tokens", 0) or 0),
            "prompt_cache_hit_tokens": int(raw_cache_hit) if raw_cache_hit is not None else None,
        }
        if usage["total_tokens"]:
            logger.info(
                "  -> Token使用: 输入=%s, 输出=%s, 总计=%s",
                usage["prompt_tokens"],
                usage["completion_tokens"],
                usage["total_tokens"],
            )
        return content, usage

    def call_with_fallback(
        self,
        prompt: str,
        stage_name: str = "",
        preferred_models: Optional[List[str]] = None,
        strict_tool_schema: Optional[Dict[str, Any]] = None,
        strict_tool_name: Optional[str] = None,
    ) -> Optional[str]:
        models_to_try = []
        if preferred_models:
            for model_key in preferred_models:
                if model_key in self.available_models and model_key not in models_to_try:
                    models_to_try.append(model_key)
            if models_to_try:
                readable = ", ".join(MODEL_CONFIGS.get(model, {}).get("name", model) for model in models_to_try)
                logger.info("  -> [%s] 使用阶段模型偏好: %s", stage_name, readable)
        elif self.successful_model and self.successful_model in self.available_models:
            models_to_try.append(self.successful_model)
            logger.info(f"  -> [{stage_name}] 优先使用之前成功的模型: {MODEL_CONFIGS[self.successful_model]['name']}")

        for model_key in self.available_models:
            if model_key not in models_to_try:
                models_to_try.append(model_key)

        for model_key in models_to_try:
            for attempt in range(2):
                result, usage = self._call_ai(
                    prompt,
                    model_key,
                    stage_name,
                    strict_tool_schema=strict_tool_schema,
                    strict_tool_name=strict_tool_name,
                )
                if result:
                    logger.info(f"  ✔ {MODEL_CONFIGS[model_key]['name']} 分析成功。")
                    self.successful_model = model_key
                    if usage and stage_name:
                        stage_key = stage_name.lower()
                        self.token_usage[stage_key] = {
                            "prompt_tokens": usage.get("prompt_tokens", 0),
                            "completion_tokens": usage.get("completion_tokens", 0),
                            "total_tokens": usage.get("total_tokens", 0),
                            # T44④：`usage` 里这个键要么是 provider 给的真实数值，要么是
                            # `_call_ai` 显式写入的 None——这里不给默认值，原样透传，
                            # 不能把"没有这个键"和"provider 说是 0"混成同一件事。
                            "prompt_cache_hit_tokens": usage.get("prompt_cache_hit_tokens"),
                        }
                    return result
                logger.warning(f"  ! {MODEL_CONFIGS[model_key]['name']} 第 {attempt+1} 次尝试失败，稍后重试...")
                time.sleep(1)
        logger.error("所有可用模型均分析失败。")
        return None

    def extract_json(self, text: str, stage: str) -> Optional[Dict]:
        if not text:
            return None

        match = re.search(r'<script type="application/json" id="__LOGIC__">(.*?)</script>', text, re.DOTALL)
        if not match:
            match = re.search(r'```json\s*\n(.*?)\n```', text, re.DOTALL)

        if match:
            json_block = match.group(1).strip()
            parsed = self._loads_json_with_light_repair(json_block, stage)
            if parsed is not None:
                return parsed
            try:
                json.loads(json_block)
            except json.JSONDecodeError as e:
                logger.error(f"  ! [Stage: {stage}] AI返回了格式错误的JSON: {e}")
                self._save_debug_response(
                    stage,
                    f"=== {stage} Stage Debug Info ===\n"
                    f"Error: {e}\n\n"
                    f"Extracted JSON block:\n{json_block}\n\n"
                    f"Full response:\n{text}",
                )
                return None

        raw_text = text.strip()
        parsed = self._loads_json_with_light_repair(raw_text, stage)
        if parsed is not None:
            return parsed

        logger.warning(f"  ! [Stage: {stage}] 在AI响应中未找到任何有效的JSON块。")
        self._save_debug_response(
            stage,
            f"=== {stage} Stage Debug Info ===\n"
            "No valid JSON block found.\n\n"
            f"Full response:\n{text}",
        )
        return None

    def diagnose_json_error(self, text: str) -> Optional[str]:
        """定位原始响应里真实的 JSON 语法错误，供解析失败后的重试反馈使用。

        与 extract_json 同款顺序找 JSON 块（`__LOGIC__` script 块 → ```json 围栏 →
        退化到全文），对找到的块做 `json.loads` 并捕获 `JSONDecodeError`，返回包含
        错误信息、行:列（相对提取出的 JSON 块）和出错点前后各约 200 字符窗口的
        诊断文本。找不到块或拿不到 `JSONDecodeError`（例如块本身是合法 JSON 但不是
        对象）时返回 None——由调用方回退到末尾片段行为。

        只读诊断：不改变 extract_json 的现有行为与接口，自身任何情况下都不抛错。
        """
        try:
            if not text:
                return None
            match = re.search(r'<script type="application/json" id="__LOGIC__">(.*?)</script>', text, re.DOTALL)
            if not match:
                match = re.search(r'```json\s*\n(.*?)\n```', text, re.DOTALL)
            block = match.group(1).strip() if match else text.strip()
            if not block:
                return None
            try:
                json.loads(block)
            except json.JSONDecodeError as e:
                window = block[max(0, e.pos - 200): e.pos + 200]
                return (
                    f"JSON 语法错误定位: {e.msg}（提取出的 JSON 块内第 {e.lineno} 行第 {e.colno} 列）。"
                    f" 错误位置前后各约 200 字符：\n{window}"
                )
            return None
        except Exception:
            return None

    def _loads_json_with_light_repair(self, text: str, stage: str) -> Optional[Dict]:
        """Parse model JSON, with a narrow repair for common single-character slips."""
        if not text:
            return None
        candidates = [text.strip()]
        repaired = self._light_repair_json(candidates[0])
        if repaired != candidates[0]:
            candidates.append(repaired)
        for index, candidate in enumerate(candidates):
            try:
                parsed = json.loads(candidate)
                if index > 0:
                    logger.warning(f"  ! [Stage: {stage}] AI JSON contained minor syntax issues; light repair succeeded.")
                return parsed if isinstance(parsed, dict) else None
            except json.JSONDecodeError as e:
                # T70 P-E（2026-09-03，run t70_glm_check_20260902 终审 attempt_1）：
                # GLM flash 偶发把同一份 JSON 对象首尾串联输出两遍（Extra data）。
                # 取第一个完整对象是安全的收窄——内容仍由下游 schema 校验把守；
                # 首对象残缺时 raw_decode 同样报错，不会 salvage 半截 JSON。
                if e.msg == "Extra data":
                    try:
                        parsed, _ = json.JSONDecoder().raw_decode(candidate)
                        logger.warning(f"  ! [Stage: {stage}] AI emitted concatenated JSON objects; kept the first complete one.")
                        return parsed if isinstance(parsed, dict) else None
                    except json.JSONDecodeError:
                        continue
                continue
        return None

    @staticmethod
    def _light_repair_json(text: str) -> str:
        repaired = text.strip().lstrip("\ufeff")
        # Model occasionally closes a one-item array as ["text") instead of ["text"].
        repaired = re.sub(r'(?<=")\s*\)\s*([,\]])', r']\1', repaired)
        # DeepSeek JSON mode can occasionally end a Chinese string-list item with
        # a full-width bracket instead of the required closing quote/bracket.
        repaired = re.sub(r'(?<!")】\s*([,\r\n])', r'"]\1', repaired)
        # Model occasionally emits a bare percent value like `"value": -26.58%`;
        # JSON requires the percent form to be a quoted string.
        repaired = re.sub(r'(:\s*)(-?\d+(?:\.\d+)?)%(\s*[,}\]])', r'\1"\2%"\3', repaired)
        # Standard JSON does not allow trailing commas.
        repaired = re.sub(r",\s*([}\]])", r"\1", repaired)
        return repaired

    def get_token_report(self) -> Dict:
        """汇总 token 使用情况"""
        total = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        # T44④：prompt_cache_hit_tokens 只汇总"确实知道"的站点；一个站点都没报告过
        # 就整体记 None（"不知道"），不能拿默认值 0 参与求和悄悄冒充"确认没命中"。
        known_cache_hits: List[int] = []
        for key, usage in self.token_usage.items():
            if key == "total":
                continue
            for field in ["prompt_tokens", "completion_tokens", "total_tokens"]:
                total[field] += usage.get(field, 0)
            cache_hit = usage.get("prompt_cache_hit_tokens")
            if cache_hit is not None:
                known_cache_hits.append(cache_hit)
        total["prompt_cache_hit_tokens"] = sum(known_cache_hits) if known_cache_hits else None
        self.token_usage["total"] = total
        return self.token_usage

    def save_token_report(self, path: str) -> None:
        """保存 token 统计到文件"""
        report = self.get_token_report()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report, f, ensure_ascii=False, indent=2)


# ============================================================================
# 导入时架构校验（快速失败原则）
# ============================================================================
try:
    try:
        from ..prompt_examples import PROMPT_EXAMPLES, validate_prompt_examples
    except ImportError:
        from prompt_examples import PROMPT_EXAMPLES, validate_prompt_examples

    if not validate_prompt_examples(PROMPT_EXAMPLES):
        logger.critical("!!! vNext LLMEngine 初始化被阻止：prompt_examples 架构校验未通过 !!!")
        raise SystemExit("架构校验失败，程序终止。")
except SystemExit:
    raise
except Exception as e:
    logger.warning(f"vNext LLMEngine 导入时未能完成架构校验: {e}")
