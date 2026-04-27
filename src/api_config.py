# -*- coding: utf-8 -*-
"""
API configuration compatibility layer.

This module centralizes:
- local JSON config loading
- .env fallback
- dynamic AI model registry
- proxy application
- simple service connectivity tests
"""

from __future__ import annotations

import copy
import json
import logging
import os
import re
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

ApiConfigDict = Dict[str, Any]

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_DIR = os.path.join(BASE_DIR, "config")
API_CONFIG_EXAMPLE_PATH = os.path.join(CONFIG_DIR, "api_config.example.json")
API_CONFIG_LOCAL_PATH = os.path.join(CONFIG_DIR, "api_config.local.json")


def _default_validation_entry() -> Dict[str, Any]:
    return {
        "last_tested": None,
        "result": None,
        "response_time_ms": None,
        "error_message": None,
    }


DEFAULT_API_CONFIG: ApiConfigDict = {
    "version": "1.1",
    "last_updated": "",
    "services": {
        "fred": {
            "category": "data_source",
            "transport": "fred_http",
            "name": "FRED",
            "enabled": True,
            "key": "",
            "base_url": "https://api.stlouisfed.org/fred/series/observations",
            "env_key": "FRED_API_KEY",
            "env_key_aliases": [],
            "base_url_env_key": "",
            "required": True,
            "docs_url": "https://fred.stlouisfed.org/docs/api/api_key.html",
            "models": [],
        },
        "alphavantage": {
            "category": "data_source",
            "transport": "alphavantage_http",
            "name": "Alpha Vantage",
            "enabled": False,
            "key": "",
            "base_url": "https://www.alphavantage.co/query",
            "env_key": "ALPHA_VANTAGE_API_KEY",
            "env_key_aliases": ["ALPHAVANTAGE_API_KEY"],
            "base_url_env_key": "",
            "required": False,
            "docs_url": "https://www.alphavantage.co/support/#api-key",
            "models": [],
        },
        "chatai": {
            "category": "ai_service",
            "transport": "openai_compatible",
            "name": "ChatAI",
            "enabled": True,
            "key": "",
            "base_url": "https://www.chataiapi.com/v1",
            "env_key": "CHATAI_API_KEY",
            "env_key_aliases": [],
            "base_url_env_key": "CHATAI_BASE_URL",
            "required": False,
            "docs_url": "",
            "models": [
                {
                    "key": "c-gemini-3",
                    "name": "Gemini 3 Pro (ChatAI)",
                    "model": "gemini-3-pro-preview",
                    "max_tokens": 65536,
                },
                {
                    "key": "c-flash",
                    "name": "Gemini 2.5 Flash (ChatAI)",
                    "model": "gemini-2.5-flash",
                    "max_tokens": 65536,
                },
                {
                    "key": "c-pro",
                    "name": "Gemini 2.5 Pro (ChatAI)",
                    "model": "gemini-2.5-pro",
                    "max_tokens": 65536,
                },
            ],
        },
        "gemini": {
            "category": "ai_service",
            "transport": "gemini_sdk",
            "name": "Gemini Official",
            "enabled": False,
            "key": "",
            "base_url": "https://generativelanguage.googleapis.com/v1beta",
            "env_key": "GOOGLE_API_KEY",
            "env_key_aliases": ["GEMINI_API_KEY"],
            "base_url_env_key": "GEMINI_BASE_URL",
            "required": False,
            "docs_url": "https://ai.google.dev/gemini-api/docs/quickstart",
            "models": [
                {
                    "key": "gemini-3-pro",
                    "name": "Gemini 3 Pro (Official)",
                    "model": "gemini-3-pro-preview",
                    "max_tokens": 65536,
                },
                {
                    "key": "gemini-2.5-flash",
                    "name": "Gemini 2.5 Flash",
                    "model": "gemini-2.5-flash",
                    "max_tokens": 65536,
                },
                {
                    "key": "gemini-2.5-pro",
                    "name": "Gemini 2.5 Pro",
                    "model": "gemini-2.5-pro",
                    "max_tokens": 65536,
                },
            ],
        },
        "deepseek": {
            "category": "ai_service",
            "transport": "openai_compatible",
            "name": "DeepSeek",
            "enabled": False,
            "key": "",
            "base_url": "https://api.deepseek.com",
            "env_key": "DEEPSEEK_API_KEY",
            "env_key_aliases": [],
            "base_url_env_key": "DEEPSEEK_BASE_URL",
            "required": False,
            "docs_url": "https://api-docs.deepseek.com/zh-cn/",
            "models": [
                {
                    "key": "deepseek-v4-flash",
                    "name": "DeepSeek V4 Flash",
                    "model": "deepseek-v4-flash",
                    "max_tokens": 65536,
                },
                {
                    "key": "deepseek-v4-pro",
                    "name": "DeepSeek V4 Pro",
                    "model": "deepseek-v4-pro",
                    "max_tokens": 64000,
                },
            ],
        },
        "kimi": {
            "category": "ai_service",
            "transport": "openai_compatible",
            "name": "Kimi (Moonshot AI)",
            "enabled": True,
            "key": "",
            "base_url": "https://api.kimi.com/coding/v1",
            "env_key": "KIMI_API_KEY",
            "env_key_aliases": [],
            "base_url_env_key": "KIMI_BASE_URL",
            "required": False,
            "docs_url": "https://www.kimi.com/code/docs/",
            "extra_headers": {
                "User-Agent": "KimiCLI/1.11.0 (kimi-agent-sdk/0.1.2 kimi-code-for-vs-code/0.3.7 0.1.2)",
            },
            "models": [
                {
                    "key": "kimi-for-coding",
                    "name": "Kimi for Coding (K2.5)",
                    "model": "kimi-for-coding",
                    "max_tokens": 32768,
                },
            ],
        },
        "finnhub": {
            "category": "data_source",
            "transport": "finnhub_http",
            "name": "Finnhub",
            "enabled": False,
            "key": "",
            "base_url": "https://finnhub.io/api/v1",
            "env_key": "FINNHUB_API_KEY",
            "env_key_aliases": [],
            "base_url_env_key": "FINNHUB_BASE_URL",
            "required": False,
            "docs_url": "https://finnhub.io/docs/api",
            "models": [],
        },
        "simfin": {
            "category": "data_source",
            "transport": "simfin_http",
            "name": "Simfin",
            "enabled": False,
            "key": "",
            "base_url": "https://backend.simfin.com/api/v3",
            "env_key": "SIMFIN_API_KEY",
            "env_key_aliases": [],
            "base_url_env_key": "SIMFIN_BASE_URL",
            "required": False,
            "docs_url": "https://www.simfin.com/en/fundamental-data-download/",
            "models": [],
        },
    },
    "proxy": {
        "enabled": False,
        "http": "",
        "https": "",
    },
    "validation": {
        "services": {
            "fred": _default_validation_entry(),
            "alphavantage": _default_validation_entry(),
            "chatai": _default_validation_entry(),
            "gemini": _default_validation_entry(),
            "deepseek": _default_validation_entry(),
            "kimi": _default_validation_entry(),
            "finnhub": _default_validation_entry(),
            "simfin": _default_validation_entry(),
        }
    },
}

_CONFIG_CACHE: Optional[ApiConfigDict] = None


def _deepcopy_default() -> ApiConfigDict:
    return copy.deepcopy(DEFAULT_API_CONFIG)


def get_api_config_example_path() -> str:
    return API_CONFIG_EXAMPLE_PATH


def get_api_config_local_path() -> str:
    return API_CONFIG_LOCAL_PATH


def get_active_api_config_path() -> Optional[str]:
    for candidate in (API_CONFIG_LOCAL_PATH, API_CONFIG_EXAMPLE_PATH):
        if os.path.exists(candidate):
            return candidate
    return None


def _load_raw_json(path: str) -> ApiConfigDict:
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except json.JSONDecodeError as exc:
        logging.warning("Failed to parse API config %s: %s", path, exc)
        return {}
    except Exception as exc:  # noqa: BLE001
        logging.warning("Failed to load API config %s: %s", path, exc)
        return {}


def _flatten_legacy_services(raw_data: ApiConfigDict) -> Dict[str, Any]:
    flattened: Dict[str, Any] = {}
    apis = raw_data.get("apis", {})
    if not isinstance(apis, dict):
        return flattened

    data_sources = apis.get("data_sources", {})
    if isinstance(data_sources, dict):
        flattened.update(data_sources)

    ai_services = apis.get("ai_services", {})
    if isinstance(ai_services, dict):
        flattened.update(ai_services)

    return flattened


def _slugify(value: str, fallback: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", "_", (value or "").strip().lower()).strip("_")
    return normalized or fallback


def _normalize_model_entry(model: Any, service_name: str, service_display_name: str) -> Optional[Dict[str, Any]]:
    if not isinstance(model, dict):
        return None

    remote_model = str(model.get("model", "") or "").strip()
    if not remote_model:
        return None

    model_key = str(model.get("key", "") or "").strip()
    if not model_key:
        model_key = _slugify(f"{service_name}_{remote_model}", f"{service_name}_model")

    display_name = str(model.get("name", "") or "").strip()
    if not display_name:
        display_name = f"{service_display_name} / {remote_model}"

    max_tokens = model.get("max_tokens", 65536)
    try:
        max_tokens = int(max_tokens)
    except (TypeError, ValueError):
        max_tokens = 65536

    return {
        "key": model_key,
        "name": display_name,
        "model": remote_model,
        "max_tokens": max_tokens,
    }


def _normalize_models(service_name: str, raw_models: Any, default_models: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    if raw_models is None:
        source = default_models
    elif isinstance(raw_models, list):
        source = raw_models
    else:
        source = default_models

    normalized: List[Dict[str, Any]] = []
    seen_keys = set()
    service_display_name = DEFAULT_API_CONFIG["services"].get(service_name, {}).get("name", service_name)

    for item in source:
        parsed = _normalize_model_entry(item, service_name, service_display_name)
        if not parsed or parsed["key"] in seen_keys:
            continue
        seen_keys.add(parsed["key"])
        normalized.append(parsed)
    return normalized


def _normalize_service(service_name: str, raw_service: Any) -> Dict[str, Any]:
    default_service = copy.deepcopy(DEFAULT_API_CONFIG["services"].get(service_name, {}))
    if not default_service:
        default_service = {
            "category": "ai_service",
            "transport": "openai_compatible",
            "name": service_name,
            "enabled": False,
            "key": "",
            "base_url": "",
            "env_key": "",
            "env_key_aliases": [],
            "base_url_env_key": "",
            "required": False,
            "docs_url": "",
            "extra_headers": {},
            "models": [],
        }

    if isinstance(raw_service, dict):
        for field in [
            "category",
            "transport",
            "name",
            "enabled",
            "key",
            "base_url",
            "env_key",
            "env_key_aliases",
            "base_url_env_key",
            "required",
            "docs_url",
            "extra_headers",
        ]:
            if field in raw_service:
                default_service[field] = copy.deepcopy(raw_service[field])

    default_service.setdefault("env_key_aliases", [])
    if not isinstance(default_service.get("env_key_aliases"), list):
        default_service["env_key_aliases"] = []
    default_service.setdefault("extra_headers", {})
    if not isinstance(default_service.get("extra_headers"), dict):
        default_service["extra_headers"] = {}

    default_models = DEFAULT_API_CONFIG["services"].get(service_name, {}).get("models", [])
    raw_models = raw_service.get("models") if isinstance(raw_service, dict) else default_service.get("models")

    if service_name == "kimi":
        legacy_kimi_keys = {"kimi-latest", "kimi-k2", "kimi-k1.6"}
        raw_model_keys = {
            str(item.get("key", "")).strip()
            for item in raw_models
            if isinstance(item, dict)
        } if isinstance(raw_models, list) else set()
        if default_service.get("base_url") == "https://api.moonshot.cn/v1":
            default_service["base_url"] = "https://api.kimi.com/coding/v1"
        if raw_model_keys == legacy_kimi_keys:
            raw_models = copy.deepcopy(default_models)

    if service_name == "deepseek":
        legacy_deepseek_keys = {"deepseek-chat", "deepseek-reasoner"}
        raw_model_keys = {
            str(item.get("key", "")).strip()
            for item in raw_models
            if isinstance(item, dict)
        } if isinstance(raw_models, list) else set()
        if default_service.get("base_url") == "https://api.deepseek.com/v1":
            default_service["base_url"] = "https://api.deepseek.com"
        if raw_model_keys == legacy_deepseek_keys:
            raw_models = copy.deepcopy(default_models)

    if service_name == "simfin" and default_service.get("base_url") == "https://simfin.com/api/v3":
        default_service["base_url"] = "https://backend.simfin.com/api/v3"

    default_service["models"] = _normalize_models(service_name, raw_models, default_models)
    return default_service


def _normalize_validation(validation_data: Any, service_names: Any) -> Dict[str, Any]:
    normalized = {"services": {}}
    raw_services = {}
    if isinstance(validation_data, dict):
        raw_services = validation_data.get("services", {})
        if not raw_services and "apis" in validation_data and isinstance(validation_data["apis"], dict):
            raw_services = validation_data["apis"]

    if not isinstance(raw_services, dict):
        raw_services = {}

    for service_name in service_names:
        raw_entry = raw_services.get(service_name, {})
        entry = normalized["services"].setdefault(service_name, _default_validation_entry())
        if isinstance(raw_entry, dict):
            for field in ["last_tested", "result", "response_time_ms", "error_message"]:
                if field in raw_entry:
                    entry[field] = raw_entry[field]
    return normalized


def normalize_api_config(raw_data: Optional[ApiConfigDict]) -> ApiConfigDict:
    normalized = _deepcopy_default()
    if not isinstance(raw_data, dict):
        return normalized

    normalized["version"] = str(raw_data.get("version", normalized["version"]))
    last_updated = raw_data.get("last_updated")
    if isinstance(last_updated, str):
        normalized["last_updated"] = last_updated

    raw_services = raw_data.get("services", {})
    if not raw_services:
        raw_services = _flatten_legacy_services(raw_data)
    if not isinstance(raw_services, dict):
        raw_services = {}

    merged_service_names = set(normalized["services"].keys()) | set(raw_services.keys())
    services: Dict[str, Any] = {}
    for service_name in sorted(merged_service_names):
        services[service_name] = _normalize_service(service_name, raw_services.get(service_name))
    normalized["services"] = services

    proxy_data = raw_data.get("proxy", {})
    if isinstance(proxy_data, dict):
        for field in ["enabled", "http", "https"]:
            if field in proxy_data:
                normalized["proxy"][field] = proxy_data[field]

    normalized["validation"] = _normalize_validation(raw_data.get("validation", {}), normalized["services"].keys())
    return normalized


def load_api_config(path: Optional[str] = None) -> ApiConfigDict:
    resolved_path = path or get_active_api_config_path()
    if not resolved_path:
        return normalize_api_config(DEFAULT_API_CONFIG)
    return normalize_api_config(_load_raw_json(resolved_path))


def _get_config() -> ApiConfigDict:
    global _CONFIG_CACHE
    if _CONFIG_CACHE is None:
        _CONFIG_CACHE = load_api_config()
        apply_proxy_settings(_CONFIG_CACHE)
    return _CONFIG_CACHE


def get_api_config_snapshot() -> ApiConfigDict:
    return copy.deepcopy(_get_config())


def _resolve_env_value(service: Dict[str, Any], *, value_field: str, env_field: str) -> str:
    raw_value = service.get(value_field)
    if isinstance(raw_value, str) and raw_value.strip():
        return raw_value.strip()

    env_names = []
    primary = service.get(env_field)
    if isinstance(primary, str) and primary.strip():
        env_names.append(primary.strip())

    alias_field = f"{env_field}_aliases"
    aliases = service.get(alias_field, [])
    if isinstance(aliases, list):
        env_names.extend(name for name in aliases if isinstance(name, str) and name.strip())

    for env_name in env_names:
        value = os.environ.get(env_name, "")
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def get_service_settings(service_name: str) -> Dict[str, Any]:
    return copy.deepcopy(_get_config()["services"].get(service_name, {}))


def get_service_config(service_name: str) -> Dict[str, Any]:
    service = get_service_settings(service_name)
    service["effective_key"] = _resolve_env_value(service, value_field="key", env_field="env_key")
    base_url = _resolve_env_value(service, value_field="base_url", env_field="base_url_env_key")
    service["effective_base_url"] = base_url or service.get("base_url", "")
    service["effective_enabled"] = bool(service.get("enabled", False))
    return service


def get_api_key(service_name: str) -> str:
    return get_service_config(service_name).get("effective_key", "")


def get_base_url(service_name: str) -> str:
    return get_service_config(service_name).get("effective_base_url", "")


def get_extra_headers(service_name: str) -> Dict[str, str]:
    raw_headers = get_service_settings(service_name).get("extra_headers", {})
    if not isinstance(raw_headers, dict):
        return {}

    headers: Dict[str, str] = {}
    for key, value in raw_headers.items():
        header_name = str(key or "").strip()
        header_value = str(value or "").strip()
        if header_name and header_value:
            headers[header_name] = header_value
    return headers


def is_service_enabled(service_name: str) -> bool:
    return bool(get_service_settings(service_name).get("enabled", False))


def get_proxy_config() -> Dict[str, Any]:
    proxy = copy.deepcopy(_get_config().get("proxy", {}))
    proxy.setdefault("enabled", False)
    proxy.setdefault("http", "")
    proxy.setdefault("https", "")
    return proxy


def get_requests_proxies() -> Optional[Dict[str, str]]:
    proxy = get_proxy_config()
    if not proxy.get("enabled"):
        return None

    proxies: Dict[str, str] = {}
    if isinstance(proxy.get("http"), str) and proxy["http"].strip():
        proxies["http"] = proxy["http"].strip()
    if isinstance(proxy.get("https"), str) and proxy["https"].strip():
        proxies["https"] = proxy["https"].strip()
    return proxies or None


def apply_proxy_settings(config: Optional[ApiConfigDict] = None) -> None:
    active_config = config or _get_config()
    proxy = active_config.get("proxy", {})
    if not isinstance(proxy, dict):
        return

    if proxy.get("enabled"):
        if isinstance(proxy.get("http"), str):
            os.environ["HTTP_PROXY"] = proxy["http"].strip()
        if isinstance(proxy.get("https"), str):
            os.environ["HTTPS_PROXY"] = proxy["https"].strip()
    else:
        os.environ.pop("HTTP_PROXY", None)
        os.environ.pop("HTTPS_PROXY", None)


def save_api_config(data: ApiConfigDict, path: Optional[str] = None) -> ApiConfigDict:
    normalized = normalize_api_config(data)
    normalized["last_updated"] = datetime.now().isoformat(timespec="seconds")
    resolved_path = path or API_CONFIG_LOCAL_PATH
    os.makedirs(os.path.dirname(resolved_path), exist_ok=True)
    with open(resolved_path, "w", encoding="utf-8") as handle:
        json.dump(normalized, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    global _CONFIG_CACHE
    _CONFIG_CACHE = normalized
    apply_proxy_settings(_CONFIG_CACHE)
    return copy.deepcopy(normalized)


def reload_config() -> None:
    global _CONFIG_CACHE
    _CONFIG_CACHE = None
    _get_config()


def update_validation_result(
    service_name: str,
    *,
    success: bool,
    response_time_ms: Optional[int],
    error_message: Optional[str],
    persist: bool = True,
) -> Dict[str, Any]:
    config = get_api_config_snapshot()
    validation = config.setdefault("validation", {}).setdefault("services", {})
    entry = validation.setdefault(service_name, _default_validation_entry())
    entry["last_tested"] = datetime.now().isoformat(timespec="seconds")
    entry["result"] = "success" if success else "failure"
    entry["response_time_ms"] = response_time_ms
    entry["error_message"] = error_message
    if persist:
        save_api_config(config)
    else:
        global _CONFIG_CACHE
        _CONFIG_CACHE = config
    return copy.deepcopy(entry)


def get_validation_snapshot() -> Dict[str, Any]:
    return copy.deepcopy(_get_config().get("validation", {}))


def get_model_configs() -> Dict[str, Dict[str, Any]]:
    configs: Dict[str, Dict[str, Any]] = {}
    for service_name, service in _get_config().get("services", {}).items():
        if service.get("category") != "ai_service":
            continue

        transport = str(service.get("transport", "") or "").strip()
        if transport == "openai_compatible":
            client_type = "openai_compatible"
        elif transport == "gemini_sdk":
            client_type = "gemini_sdk"
        else:
            continue

        for model in service.get("models", []):
            if not isinstance(model, dict):
                continue
            key = str(model.get("key", "") or "").strip()
            remote_model = str(model.get("model", "") or "").strip()
            if not key or not remote_model:
                continue
            configs[key] = {
                "name": str(model.get("name", "") or key),
                "client": client_type,
                "service": service_name,
                "model": remote_model,
                "max_tokens": int(model.get("max_tokens", 65536) or 65536),
            }
    return configs


def _response_result(start_time: float, success: bool, error_message: Optional[str]) -> Dict[str, Any]:
    elapsed_ms = int((time.perf_counter() - start_time) * 1000)
    return {
        "success": success,
        "response_time_ms": elapsed_ms,
        "error_message": error_message,
    }


def _test_fred(service_name: str) -> Dict[str, Any]:
    key = get_api_key(service_name)
    if not key:
        return {"success": False, "response_time_ms": None, "error_message": "FRED API Key 未配置"}

    start = time.perf_counter()
    try:
        response = requests.get(
            get_base_url(service_name),
            params={
                "series_id": "FEDFUNDS",
                "api_key": key,
                "file_type": "json",
                "limit": 1,
                "sort_order": "desc",
            },
            proxies=get_requests_proxies(),
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("observations"):
            return _response_result(start, True, None)
        return _response_result(start, False, "FRED 返回结果为空")
    except Exception as exc:  # noqa: BLE001
        return _response_result(start, False, str(exc)[:200])


def _test_alphavantage(service_name: str) -> Dict[str, Any]:
    key = get_api_key(service_name)
    if not key:
        return {"success": False, "response_time_ms": None, "error_message": "Alpha Vantage API Key 未配置"}

    start = time.perf_counter()
    try:
        response = requests.get(
            get_base_url(service_name),
            params={
                "function": "GLOBAL_QUOTE",
                "symbol": "MSFT",
                "apikey": key,
            },
            proxies=get_requests_proxies(),
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("Global Quote"):
            return _response_result(start, True, None)
        if payload.get("Note"):
            return _response_result(start, False, "Alpha Vantage 触发频率限制")
        return _response_result(start, False, "Alpha Vantage 返回结果无效")
    except Exception as exc:  # noqa: BLE001
        return _response_result(start, False, str(exc)[:200])


def _test_openai_compatible(service_name: str) -> Dict[str, Any]:
    key = get_api_key(service_name)
    base_url = get_base_url(service_name)
    if not key:
        return {"success": False, "response_time_ms": None, "error_message": f"{service_name} API Key 未配置"}
    if not base_url:
        return {"success": False, "response_time_ms": None, "error_message": f"{service_name} Base URL 未配置"}

    start = time.perf_counter()
    try:
        url = base_url.rstrip("/") + "/models"
        headers = get_extra_headers(service_name)
        headers["Authorization"] = f"Bearer {key}"
        proxies = get_requests_proxies()
        session = requests.Session()
        if proxies:
            response = session.get(
                url,
                headers=headers,
                proxies=proxies,
                timeout=20,
            )
        else:
            session.trust_env = False
            response = session.get(
                url,
                headers=headers,
                timeout=20,
            )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, dict):
            return _response_result(start, True, None)
        return _response_result(start, False, "服务返回格式异常")
    except Exception as exc:  # noqa: BLE001
        return _response_result(start, False, str(exc)[:200])


def _test_gemini(service_name: str) -> Dict[str, Any]:
    key = get_api_key(service_name)
    base_url = get_base_url(service_name) or "https://generativelanguage.googleapis.com/v1beta"
    if not key:
        return {"success": False, "response_time_ms": None, "error_message": "Gemini API Key 未配置"}

    start = time.perf_counter()
    try:
        response = requests.get(
            base_url.rstrip("/") + "/models",
            params={"key": key},
            proxies=get_requests_proxies(),
            timeout=20,
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("models"):
            return _response_result(start, True, None)
        return _response_result(start, False, "Gemini 返回结果为空")
    except Exception as exc:  # noqa: BLE001
        return _response_result(start, False, str(exc)[:200])


def _test_finnhub(service_name: str) -> Dict[str, Any]:
    """Test Finnhub API connectivity."""
    key = get_api_key(service_name)
    if not key:
        return {"success": False, "response_time_ms": None, "error_message": "Finnhub API Key 未配置"}

    start = time.perf_counter()
    try:
        base_url = get_base_url(service_name) or "https://finnhub.io/api/v1"
        response = requests.get(
            f"{base_url}/quote",
            params={"symbol": "AAPL", "token": key},
            proxies=get_requests_proxies(),
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        if "c" in payload:  # Current price field
            return _response_result(start, True, None)
        return _response_result(start, False, "Finnhub 返回结果无效")
    except Exception as exc:  # noqa: BLE001
        return _response_result(start, False, str(exc)[:200])


def _test_simfin(service_name: str) -> Dict[str, Any]:
    """Test Simfin API connectivity."""
    key = get_api_key(service_name)
    if not key:
        return {"success": False, "response_time_ms": None, "error_message": "Simfin API Key 未配置"}

    start = time.perf_counter()
    try:
        base_url = get_base_url(service_name) or "https://backend.simfin.com/api/v3"
        # Test by searching for a company
        response = requests.get(
            f"{base_url}/companies/search",
            params={"query": "Apple", "api-key": key},
            proxies=get_requests_proxies(),
            timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, (list, dict)):
            return _response_result(start, True, None)
        return _response_result(start, False, "Simfin 返回结果无效")
    except Exception as exc:  # noqa: BLE001
        return _response_result(start, False, str(exc)[:200])


def test_service(service_name: str, *, persist: bool = True) -> Dict[str, Any]:
    service_name = (service_name or "").strip().lower()
    service = _get_config().get("services", {}).get(service_name)
    if not service:
        result = {
            "success": False,
            "response_time_ms": None,
            "error_message": f"未知服务: {service_name}",
        }
        if persist:
            update_validation_result(service_name, success=False, response_time_ms=None, error_message=result["error_message"])
        return result

    transport = str(service.get("transport", "") or "").strip()
    if transport == "fred_http":
        result = _test_fred(service_name)
    elif transport == "alphavantage_http":
        result = _test_alphavantage(service_name)
    elif transport == "openai_compatible":
        result = _test_openai_compatible(service_name)
    elif transport == "gemini_sdk":
        result = _test_gemini(service_name)
    elif transport == "finnhub_http":
        result = _test_finnhub(service_name)
    elif transport == "simfin_http":
        result = _test_simfin(service_name)
    else:
        result = {
            "success": False,
            "response_time_ms": None,
            "error_message": f"服务暂不支持测试: {service_name}",
        }

    if persist:
        update_validation_result(
            service_name,
            success=bool(result.get("success")),
            response_time_ms=result.get("response_time_ms"),
            error_message=result.get("error_message"),
        )
    return result


def test_all_enabled_services(*, persist: bool = True) -> Dict[str, Dict[str, Any]]:
    results: Dict[str, Dict[str, Any]] = {}
    for service_name, service in _get_config().get("services", {}).items():
        if service.get("enabled"):
            results[service_name] = test_service(service_name, persist=persist)
    return results


reload_config()
