import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from main import parse_args


def test_main_disables_legacy_charts_by_default(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py"])

    args = parse_args()

    assert args.disable_charts is True


def test_main_can_enable_legacy_charts_explicitly(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py", "--enable-legacy-charts"])

    args = parse_args()

    assert args.disable_charts is False


def test_main_accepts_independent_news_sidecar_flag(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py", "--enable-news"])

    args = parse_args()

    assert args.enable_news is True
