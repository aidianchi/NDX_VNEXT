# -*- coding: utf-8 -*-
"""
NDX Agent configuration module.

Centralizes:
- API configuration
- model registry
- path configuration
- feature constants
"""

import os
import json
from dataclasses import dataclass
from typing import Dict, List

from dotenv import load_dotenv

load_dotenv()


# =====================================================
# API configuration compatibility layer
# =====================================================

_FALLBACK_MODEL_CONFIGS = {
    "c-gemini-3": {
        "name": "Gemini 3 Pro (ChatAI)",
        "client": "openai_compatible",
        "service": "chatai",
        "model": "gemini-3-pro-preview",
        "max_tokens": 65536,
    },
    "gemini-3-pro": {
        "name": "Gemini 3 Pro (Official)",
        "client": "gemini_sdk",
        "service": "gemini",
        "model": "gemini-3-pro-preview",
        "max_tokens": 65536,
    },
    "c-flash": {
        "name": "Gemini 2.5 Flash (ChatAI)",
        "client": "openai_compatible",
        "service": "chatai",
        "model": "gemini-2.5-flash",
        "max_tokens": 65536,
    },
    "c-pro": {
        "name": "Gemini 2.5 Pro (ChatAI)",
        "client": "openai_compatible",
        "service": "chatai",
        "model": "gemini-2.5-pro",
        "max_tokens": 65536,
    },
    "gemini-2.5-flash": {
        "name": "Gemini 2.5 Flash",
        "client": "gemini_sdk",
        "service": "gemini",
        "model": "gemini-2.5-flash",
        "max_tokens": 65536,
    },
    "gemini-2.5-pro": {
        "name": "Gemini 2.5 Pro",
        "client": "gemini_sdk",
        "service": "gemini",
        "model": "gemini-2.5-pro",
        "max_tokens": 65536,
    },
    "deepseek-chat": {
        "name": "DeepSeek Chat",
        "client": "openai_compatible",
        "service": "deepseek",
        "model": "deepseek-chat",
        "max_tokens": 8000,
    },
    "deepseek-reasoner": {
        "name": "DeepSeek Reasoner",
        "client": "openai_compatible",
        "service": "deepseek",
        "model": "deepseek-reasoner",
        "max_tokens": 64000,
    },
    "deepseek-v4-flash": {
        "name": "DeepSeek V4 Flash",
        "client": "openai_compatible",
        "service": "deepseek",
        "model": "deepseek-v4-flash",
        "max_tokens": 65536,
    },
    "deepseek-v4-pro": {
        "name": "DeepSeek V4 Pro",
        "client": "openai_compatible",
        "service": "deepseek",
        "model": "deepseek-v4-pro",
        "max_tokens": 64000,
    },
    "kimi-for-coding": {
        "name": "Kimi for Coding (K2.5)",
        "client": "openai_compatible",
        "service": "kimi",
        "model": "kimi-for-coding",
        "max_tokens": 32768,
    },
}

try:
    from .api_config import get_model_configs
except ImportError:
    from api_config import get_model_configs

MODEL_CONFIGS = get_model_configs() or _FALLBACK_MODEL_CONFIGS


# =====================================================
# Path configuration
# =====================================================


@dataclass
class PathConfig:
    """Runtime path configuration."""

    base_dir: str
    config_dir: str
    output_dir: str
    reports_dir: str
    data_dir: str
    analysis_dir: str
    logs_dir: str
    cache_dir: str
    manual_data_example_path: str
    manual_data_local_path: str
    api_config_example_path: str
    api_config_local_path: str


BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
CONFIG_DIR = os.path.join(BASE_DIR, "config")

path_config = PathConfig(
    base_dir=BASE_DIR,
    config_dir=CONFIG_DIR,
    output_dir=OUTPUT_DIR,
    reports_dir=os.path.join(OUTPUT_DIR, "reports"),
    data_dir=os.path.join(OUTPUT_DIR, "data"),
    analysis_dir=os.path.join(OUTPUT_DIR, "analysis"),
    logs_dir=os.path.join(OUTPUT_DIR, "logs"),
    cache_dir=os.path.join(BASE_DIR, "data_cache"),
    manual_data_example_path=os.path.join(CONFIG_DIR, "manual_data.example.json"),
    manual_data_local_path=os.path.join(CONFIG_DIR, "manual_data.local.json"),
    api_config_example_path=os.path.join(CONFIG_DIR, "api_config.example.json"),
    api_config_local_path=os.path.join(CONFIG_DIR, "api_config.local.json"),
)

for directory in [
    path_config.config_dir,
    path_config.reports_dir,
    path_config.data_dir,
    path_config.analysis_dir,
    path_config.logs_dir,
    path_config.cache_dir,
]:
    os.makedirs(directory, exist_ok=True)


# =====================================================
# Global configuration instances
# =====================================================

class _ResolvedAPIConfig:
    """Late-bound compatibility access for legacy imports."""

    @property
    def chatai_api_key(self) -> str:
        try:
            from .api_config import get_api_key
        except ImportError:
            from api_config import get_api_key
        return get_api_key("chatai")

    @property
    def chatai_base_url(self) -> str:
        try:
            from .api_config import get_base_url
        except ImportError:
            from api_config import get_base_url
        return get_base_url("chatai") or "https://www.chataiapi.com/v1"

    @property
    def gemini_api_key(self) -> str:
        try:
            from .api_config import get_api_key
        except ImportError:
            from api_config import get_api_key
        return get_api_key("gemini")

    @property
    def gemini_base_url(self) -> str:
        try:
            from .api_config import get_base_url
        except ImportError:
            from api_config import get_base_url
        return get_base_url("gemini") or "https://generativelanguage.googleapis.com/v1beta"

    @property
    def deepseek_api_key(self) -> str:
        try:
            from .api_config import get_api_key
        except ImportError:
            from api_config import get_api_key
        return get_api_key("deepseek")

    @property
    def deepseek_base_url(self) -> str:
        try:
            from .api_config import get_base_url
        except ImportError:
            from api_config import get_base_url
        return get_base_url("deepseek") or "https://api.deepseek.com/v1"

    @property
    def kimi_api_key(self) -> str:
        try:
            from .api_config import get_api_key
        except ImportError:
            from api_config import get_api_key
        return get_api_key("kimi")

    @property
    def kimi_base_url(self) -> str:
        try:
            from .api_config import get_base_url
        except ImportError:
            from api_config import get_base_url
        return get_base_url("kimi") or "https://api.kimi.com/coding/v1"

    @property
    def finnhub_api_key(self) -> str:
        try:
            from .api_config import get_api_key
        except ImportError:
            from api_config import get_api_key
        return get_api_key("finnhub")

    @property
    def finnhub_base_url(self) -> str:
        try:
            from .api_config import get_base_url
        except ImportError:
            from api_config import get_base_url
        return get_base_url("finnhub") or "https://finnhub.io/api/v1"

    @property
    def simfin_api_key(self) -> str:
        try:
            from .api_config import get_api_key
        except ImportError:
            from api_config import get_api_key
        return get_api_key("simfin")

    @property
    def simfin_base_url(self) -> str:
        try:
            from .api_config import get_base_url
        except ImportError:
            from api_config import get_base_url
        return get_base_url("simfin") or "https://backend.simfin.com/api/v3"

    @property
    def fred_api_key(self) -> str:
        try:
            from .api_config import get_api_key
        except ImportError:
            from api_config import get_api_key
        return get_api_key("fred")

    @property
    def alphavantage_api_key(self) -> str:
        try:
            from .api_config import get_api_key
        except ImportError:
            from api_config import get_api_key
        return get_api_key("alphavantage")


_api_config_instance = _ResolvedAPIConfig()


def get_api_config() -> _ResolvedAPIConfig:
    return _api_config_instance


class _APIConfigProxy:
    """Preserve legacy attribute-style access."""

    def __getattr__(self, name: str):
        return getattr(get_api_config(), name)


api_config = _APIConfigProxy()


CHART_OVERLAY_PRESETS = {
    "vix_vs_vxn": {
        "title": "Risk Volatility Spread (VIX vs VXN)",
        "series": [
            {"name": "VIX", "cache_key": "VIX"},
            {"name": "VXN", "cache_key": "VXN"},
        ],
        "transform": "raw",
    },
    "rates_decomposition": {
        "title": "Rates Decomposition (Nominal / Real / Breakeven)",
        "series": [
            {"name": "10Y Nominal", "cache_key": "DGS10"},
            {"name": "10Y Real", "cache_key": "DFII10"},
            {"name": "10Y Breakeven", "cache_key": "T10YIE"},
        ],
        "transform": "raw",
    },
}


def _load_overlay_selection() -> Dict[str, List[str]]:
    raw = os.environ.get("CHART_OVERLAY_SELECTION", "")
    default_selection = {
        "get_vix": ["vix_vs_vxn"],
        "get_10y_treasury": ["rates_decomposition"],
    }
    if not raw:
        return default_selection
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
    except Exception:
        return default_selection
    return default_selection


CHART_OVERLAY_BY_FUNCTION = _load_overlay_selection()


# =====================================================
# Availability checks
# =====================================================


try:
    from openai import OpenAI  # noqa: F401

    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    from google import genai  # noqa: F401

    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False
