import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from control_service import _python_bound_args, validate_command


def test_control_service_allows_main_news_command():
    args = validate_command(
        "python3 src/main.py --models deepseek-v4-flash,deepseek-v4-pro --skip-report --disable-charts --enable-news"
    )

    assert args[:2] == ["python3", "src/main.py"]
    assert "--enable-news" in args


def test_control_service_allows_collect_only_command():
    args = validate_command(
        "python3 src/main.py --date 2026-05-09 --models deepseek-v4-flash,deepseek-v4-pro --collect-only"
    )

    assert args[:2] == ["python3", "src/main.py"]
    assert "--collect-only" in args


def test_control_service_rejects_unlisted_entrypoint():
    with pytest.raises(ValueError):
        validate_command("python3 src/unknown.py")


def test_control_service_rejects_unsafe_path():
    with pytest.raises(ValueError):
        validate_command("python3 src/agent_analysis/vnext_reporter.py --run-dir ../../secret --template brief")


def test_control_service_allows_browser_sidecar_command():
    args = validate_command(
        "python3 src/browser_sidecar.py --source trendonify_valuation --output output/browser_sidecar/trendonify_ndx_valuation.json --trusted"
    )

    assert args[:2] == ["python3", "src/browser_sidecar.py"]
    assert "--trusted" in args


def test_control_service_allows_full_console_flow_command():
    args = validate_command(
        "python3 src/console_run_all.py --date 2026-05-09 --models deepseek-v4-flash,deepseek-v4-pro --workbench-modules price_technical,liquidity --skip-legacy-report --enable-news"
    )

    assert args[:2] == ["python3", "src/console_run_all.py"]
    assert "--workbench-modules" in args


def test_control_service_binds_python_to_service_interpreter():
    args = _python_bound_args(["python3", "src/main.py", "--models", "deepseek-v4-flash"])

    assert args[0] == sys.executable
    assert args[1:] == ["src/main.py", "--models", "deepseek-v4-flash"]
