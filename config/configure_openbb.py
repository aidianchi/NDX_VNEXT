#!/usr/bin/env python3
"""
Configure OpenBB API keys from the project's .env file.

The script writes both the legacy OpenBB settings path and the OpenBB Platform
settings path. It never prints full secrets.
"""

import json
import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")

OPENBB_DIR = Path.home() / ".openbb"
OPENBB_PLATFORM_DIR = Path.home() / ".openbb_platform"
OPENBB_DIR.mkdir(exist_ok=True)
OPENBB_PLATFORM_DIR.mkdir(exist_ok=True)

ENV_TO_OPENBB_KEYS = {
    "FMP_API_KEY": "fmp_api_key",
    "FRED_API_KEY": "fred_api_key",
    "ALPHA_VANTAGE_API_KEY": "alpha_vantage_api_key",
    "POLYGON_API_KEY": "polygon_api_key",
    "FINNHUB_API_KEY": "finnhub_api_key",
    "SIMFIN_API_KEY": "simfin_api_key",
}


def _read_api_keys() -> dict:
    return {
        openbb_key: value
        for env_key, openbb_key in ENV_TO_OPENBB_KEYS.items()
        if (value := os.getenv(env_key, ""))
    }


def _masked(value: str) -> str:
    if not value:
        return ""
    return f"{'*' * 8}{value[-4:] if len(value) > 4 else '****'}"


def _read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def main() -> None:
    api_keys = _read_api_keys()

    print("Found API keys:")
    for key, value in sorted(api_keys.items()):
        print(f"  {key}: {_masked(value)}")

    legacy_settings = {
        "api_keys": api_keys,
        "data_directories": {
            "cache": str(OPENBB_DIR / "cache"),
        },
    }

    legacy_settings_file = OPENBB_DIR / "settings.json"
    legacy_settings_file.write_text(json.dumps(legacy_settings, indent=2), encoding="utf-8")

    platform_settings_file = OPENBB_PLATFORM_DIR / "user_settings.json"
    platform_settings = _read_json(platform_settings_file)
    platform_settings.setdefault("credentials", {})
    platform_settings.setdefault("preferences", {})
    platform_settings.setdefault("defaults", {})
    platform_settings["credentials"].update(api_keys)
    platform_settings_file.write_text(json.dumps(platform_settings, indent=2), encoding="utf-8")

    print(f"\nLegacy OpenBB settings written to: {legacy_settings_file}")
    print(f"OpenBB Platform user settings written to: {platform_settings_file}")
    print("\nOpenBB Platform reads keys from ~/.openbb_platform/user_settings.json.")


if __name__ == "__main__":
    main()
