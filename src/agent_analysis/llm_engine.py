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

    def _call_ai(self, prompt: str, model_key: str, stage: str = "") -> Tuple[Optional[str], Dict]:
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
                if use_json_output:
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

    def call_with_fallback(self, prompt: str, stage_name: str = "") -> Optional[str]:
        models_to_try = []
        if self.successful_model and self.successful_model in self.available_models:
            models_to_try.append(self.successful_model)
            logger.info(f"  -> [{stage_name}] 优先使用之前成功的模型: {MODEL_CONFIGS[self.successful_model]['name']}")

        for model_key in self.available_models:
            if model_key not in models_to_try:
                models_to_try.append(model_key)

        for model_key in models_to_try:
            for attempt in range(2):
                result, usage = self._call_ai(prompt, model_key, stage_name)
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
