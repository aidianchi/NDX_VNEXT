#!/usr/bin/env python3
"""
配置 OpenBB API keys
从 .env 文件读取现有 key 并配置到 OpenBB settings
"""

import json
import os
from pathlib import Path

# 加载 .env 文件
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / '.env')

# OpenBB 配置目录
OPENBB_DIR = Path.home() / '.openbb'
OPENBB_DIR.mkdir(exist_ok=True)
OPENBB_PLATFORM_DIR = Path.home() / '.openbb_platform'
OPENBB_PLATFORM_DIR.mkdir(exist_ok=True)

# 从 .env 读取 API keys
api_keys = {
    "fmp_api_key": os.getenv('FMP_API_KEY', ''),
    "fred_api_key": os.getenv('FRED_API_KEY', ''),
    "alpha_vantage_api_key": os.getenv('ALPHA_VANTAGE_API_KEY', ''),
    "polygon_api_key": os.getenv('POLYGON_API_KEY', ''),
    "finnhub_api_key": os.getenv('FINNHUB_API_KEY', ''),
    "simfin_api_key": os.getenv('SIMFIN_API_KEY', ''),
}

# 过滤掉空值
api_keys = {k: v for k, v in api_keys.items() if v}

print("Found API keys:")
for key in api_keys:
    print(f"  {key}: {'*' * 8}{api_keys[key][-4:] if len(api_keys[key]) > 4 else '****'}")

# OpenBB settings 格式
settings = {
    "api_keys": api_keys,
    "data_directories": {
        "cache": str(OPENBB_DIR / "cache"),
    }
}

# 写入 settings.json
settings_file = OPENBB_DIR / "settings.json"
with open(settings_file, 'w') as f:
    json.dump(settings, f, indent=2)

print(f"\nOpenBB settings written to: {settings_file}")
platform_settings_file = OPENBB_PLATFORM_DIR / "user_settings.json"
if platform_settings_file.exists():
    with open(platform_settings_file) as f:
        platform_settings = json.load(f)
else:
    platform_settings = {}

platform_settings.setdefault("credentials", {})
platform_settings.setdefault("preferences", {})
platform_settings.setdefault("defaults", {"commands": {}})
platform_settings["credentials"].update(api_keys)

with open(platform_settings_file, 'w') as f:
    json.dump(platform_settings, f, indent=2)

print(f"OpenBB Platform user settings written to: {platform_settings_file}")
print("\nYou can also set environment variables with OPENBB_ prefix:")
print("  export OPENBB_API_FMP_KEY=your_key")
print("  export OPENBB_API_FRED_KEY=your_key")
