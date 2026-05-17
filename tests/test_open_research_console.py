import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import open_research_console


def test_pids_on_port_returns_all_listeners(monkeypatch):
    def fake_run(*args, **kwargs):
        return SimpleNamespace(stdout="2678\n46322\n")

    monkeypatch.setattr(open_research_console.subprocess, "run", fake_run)

    assert open_research_console._pids_on_port(8765) == [2678, 46322]
    assert open_research_console._pid_on_port(8765) == 2678


def test_stale_console_markers_catch_old_manual_confidence_form():
    assert 'data-manual-field="confidence"' in open_research_console.STALE_CONSOLE_MARKERS
    assert "使用人工数据" in open_research_console.CONSOLE_READY_MARKERS
    assert "news_event_data_links.json" in open_research_console.CONSOLE_READY_MARKERS


def test_choose_service_restarts_existing_ready_service(monkeypatch, tmp_path):
    calls = {"started": [], "stopped": []}
    service_checks = iter([True, False])

    monkeypatch.setattr(open_research_console, "_service_is_ready", lambda _url: next(service_checks, False))
    monkeypatch.setattr(open_research_console, "_console_is_ready", lambda _url: True)
    monkeypatch.setattr(open_research_console, "_stop_service_on_port", lambda port: calls["stopped"].append(port) or True)
    monkeypatch.setattr(open_research_console, "_start_service", lambda _root, port: calls["started"].append(port))
    monkeypatch.setattr(open_research_console.time, "sleep", lambda _seconds: None)

    url = open_research_console._choose_service(tmp_path)

    assert url == "http://127.0.0.1:8765"
    assert calls["stopped"] == [8765]
    assert calls["started"] == [8765]
