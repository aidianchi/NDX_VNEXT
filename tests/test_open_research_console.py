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
