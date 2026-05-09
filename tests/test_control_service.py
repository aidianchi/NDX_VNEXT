import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from control_service import validate_command


def test_control_service_allows_main_news_command():
    args = validate_command(
        "python3 src/main.py --models deepseek-v4-flash,deepseek-v4-pro --skip-report --disable-charts --enable-news"
    )

    assert args[:2] == ["python3", "src/main.py"]
    assert "--enable-news" in args


def test_control_service_rejects_unlisted_entrypoint():
    with pytest.raises(ValueError):
        validate_command("python3 src/unknown.py")


def test_control_service_rejects_unsafe_path():
    with pytest.raises(ValueError):
        validate_command("python3 src/agent_analysis/vnext_reporter.py --run-dir ../../secret --template brief")
