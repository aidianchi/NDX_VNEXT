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
from typing import Dict, List, Optional, Tuple

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
                client_kwargs = {
                    "api_key": api_key,
                    "base_url": get_base_url(service_name),
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
                kwargs = {
                    "model": model_name,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.2,
                    "max_tokens": config["max_tokens"],
                    "stream": False,
                }
                if service_name == "deepseek":
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

        headers = get_extra_headers("kimi")
        headers["Authorization"] = f"Bearer {api_key}"
        headers["Content-Type"] = "application/json"

        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt}],
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
            try:
                return json.loads(match.group(1).strip())
            except json.JSONDecodeError as e:
                logger.error(f"  ! [Stage: {stage}] AI返回了格式错误的JSON: {e}")
                debug_filename = f"ai_response_debug_{stage}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
                try:
                    with open(debug_filename, "w", encoding="utf-8") as f:
                        f.write(f"=== {stage} Stage Debug Info ===\n")
                        f.write(f"Error: {e}\n\n")
                        f.write(f"Extracted JSON block:\n{match.group(1).strip()}\n\n")
                        f.write(f"Full response:\n{text}")
                    logger.warning(f"  原始响应已保存至: {debug_filename}")
                except Exception as save_error:
                    logger.error(f"  无法保存调试文件: {save_error}")
                return None

        try:
            return json.loads(text.strip())
        except json.JSONDecodeError:
            pass

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
