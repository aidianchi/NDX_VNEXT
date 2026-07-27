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
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# 尝试导入配置
try:
    from ..config import MODEL_CONFIGS
    from ..api_config import get_api_key, get_base_url, get_extra_headers, get_requests_proxies
except ImportError:
    from config import MODEL_CONFIGS
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
def sanitize_json_schema_for_strict_tool_calling(schema: Dict[str, Any]) -> Dict[str, Any]:
    """把 pydantic `model_json_schema()` 的输出转换成 DeepSeek strict tool calling
    真实接受的形态（不是文档字面推断的形态——上面注释记录了两者的出入）。只改
    JSON Schema 本身（发给 API、用于约束模型输出的那份契约），不改任何 pydantic
    模型定义——`extra="allow"` 和 `Optional` 字段在 contracts.py 里保持原样，
    校验响应时 pydantic 仍按自己的规则走，两边互不影响。
    """
    import copy

    def strip_and_require(node: Any) -> Any:
        if isinstance(node, dict):
            cleaned = {key: strip_and_require(value) for key, value in node.items()}
            for unsupported_key in ("minLength", "maxLength", "minItems", "maxItems", "format"):
                cleaned.pop(unsupported_key, None)
            if cleaned.get("type") == "object" and isinstance(cleaned.get("properties"), dict):
                cleaned["additionalProperties"] = False
                cleaned["required"] = list(cleaned["properties"].keys())
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
                    if branch_type == "object" or (isinstance(branch, dict) and "properties" in branch):
                        has_ref_or_object_branch = True
                    elif isinstance(branch_type, str):
                        primitive_types.append(branch_type)
                    else:
                        has_ref_or_object_branch = True
                if not has_ref_or_object_branch and primitive_types:
                    # Optional[原始类型/枚举] 且没有嵌套 object：collapse 成 type 数组，
                    # 整个去掉 anyOf——DeepSeek 对裸 anyOf 节点要求同级必须有 type。
                    fixed.pop("anyOf")
                    fixed["type"] = primitive_types if len(primitive_types) > 1 else primitive_types[0]
                else:
                    # 含嵌套 object 的分支：保留 anyOf 结构、$ref 已内联展开，
                    # 不额外加 sibling type（会撞"object with no properties"）。
                    fixed["anyOf"] = resolved
            return fixed
        if isinstance(node, list):
            return [fix_anyof(item) for item in node]
        return node

    return fix_anyof(basic)


class LLMEngine:
    """可复用的 LLM 调用引擎（从 legacy analyzer 提取）"""

    def __init__(self, available_models: List[str]):
        self.available_models = available_models
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
                use_json_output = service_name == "deepseek"
                # 严格工具调用（DeepSeek Beta strict function calling）只在 deepseek 服务、
                # 且调用方显式传入 schema 时启用；未传入时走原有 json_object 路径，逐字节
                # 不变——这是本次试点唯一的分叉点，其余所有 stage 不受影响。
                use_strict_tools = use_json_output and strict_tool_schema is not None
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
                        "total_tokens": getattr(response.usage, 'total_tokens', 0)
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
                        "total_tokens": getattr(response.usage_metadata, 'total_token_count', 0)
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
        usage = {
            "prompt_tokens": int(usage_raw.get("prompt_tokens", 0) or 0),
            "completion_tokens": int(usage_raw.get("completion_tokens", 0) or 0),
            "total_tokens": int(usage_raw.get("total_tokens", 0) or 0),
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
                            "total_tokens": usage.get("total_tokens", 0)
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
                debug_filename = f"ai_response_debug_{stage}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                try:
                    with open(debug_filename, "w", encoding="utf-8") as f:
                        f.write(f"=== {stage} Stage Debug Info ===\n")
                        f.write(f"Error: {e}\n\n")
                        f.write(f"Extracted JSON block:\n{json_block}\n\n")
                        f.write(f"Full response:\n{text}")
                    logger.warning(f"  原始响应已保存至: {debug_filename}")
                except Exception as save_error:
                    logger.error(f"  无法保存调试文件: {save_error}")
                return None

        raw_text = text.strip()
        parsed = self._loads_json_with_light_repair(raw_text, stage)
        if parsed is not None:
            return parsed

        logger.warning(f"  ! [Stage: {stage}] 在AI响应中未找到任何有效的JSON块。")
        debug_filename = f"ai_response_debug_{stage}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        try:
            with open(debug_filename, "w", encoding="utf-8") as f:
                f.write(f"=== {stage} Stage Debug Info ===\n")
                f.write("No valid JSON block found.\n\n")
                f.write(f"Full response:\n{text}")
            logger.warning(f"  原始响应已保存至: {debug_filename}")
        except Exception as save_error:
            logger.error(f"  无法保存调试文件: {save_error}")
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
            except json.JSONDecodeError:
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
        for key, usage in self.token_usage.items():
            if key == "total":
                continue
            for field in ["prompt_tokens", "completion_tokens", "total_tokens"]:
                total[field] += usage.get(field, 0)
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
