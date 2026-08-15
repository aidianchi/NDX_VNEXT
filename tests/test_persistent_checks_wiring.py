"""T47 装配点⑦：常设检查接线的单元测试。

只测 orchestrator._run_persistent_checks 的接线与容错，不测 A/B 两包内部逻辑
（那两包由各自的 test_persistent_checks_a.py / test_persistent_checks_b.py 负责）。
"""

import builtins
import json
import os
import sys
import types
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent_analysis.orchestrator import VNextOrchestrator


def _orchestrator(tmp_path: Path) -> VNextOrchestrator:
    return VNextOrchestrator(
        available_models=["fake"],
        output_dir=str(tmp_path),
        llm_engine=object(),
    )


def _install_fake_checks(monkeypatch, results_a, results_b) -> None:
    """向 sys.modules 注入假的 run_checks_a / run_checks_b。"""
    mod_a = types.ModuleType("agent_analysis.persistent_checks_a")
    mod_a.run_checks_a = lambda run_dir: results_a
    mod_b = types.ModuleType("agent_analysis.persistent_checks_b")
    mod_b.run_checks_b = lambda run_dir: results_b
    monkeypatch.setitem(sys.modules, "agent_analysis.persistent_checks_a", mod_a)
    monkeypatch.setitem(sys.modules, "agent_analysis.persistent_checks_b", mod_b)


def test_persistent_checks_wiring_merges_results_and_counts(tmp_path: Path, monkeypatch):
    results_a = [
        {"check_id": "PC-01", "name": "检查一", "passed": True, "detail": "ok", "evidence": "e1"},
        {"check_id": "PC-02", "name": "检查二", "passed": False, "detail": "bad", "evidence": "e2"},
    ]
    results_b = [
        {"check_id": "PC-11", "name": "检查十一", "passed": True, "detail": "ok", "evidence": "e3"},
    ]
    _install_fake_checks(monkeypatch, results_a, results_b)
    orchestrator = _orchestrator(tmp_path)

    report = orchestrator._run_persistent_checks()

    output_path = tmp_path / "persistent_checks_report.json"
    assert output_path.exists()
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert report == saved
    assert report["schema_version"] == "vnext_persistent_checks_v1"
    assert report["passed_count"] == 2
    assert report["failed_count"] == 1
    assert report["checks"] == results_a + results_b


def test_persistent_checks_wiring_modules_missing(tmp_path: Path, monkeypatch):
    real_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name.startswith("agent_analysis.persistent_checks"):
            raise ImportError("persistent checks package not delivered yet")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    orchestrator = _orchestrator(tmp_path)

    report = orchestrator._run_persistent_checks()

    assert report["status"] == "modules_missing"
    assert report["passed_count"] == 0
    assert report["failed_count"] == 0
    assert report["checks"] == []
    output_path = tmp_path / "persistent_checks_report.json"
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["status"] == "modules_missing"


def test_persistent_checks_wiring_exception_writes_failed_summary(tmp_path: Path, monkeypatch):
    """任何异常只写 failed 汇总，不得让主链崩溃。"""

    def _boom(run_dir):
        raise RuntimeError("check exploded")

    _install_fake_checks(
        monkeypatch,
        results_a=[],
        results_b=[],
    )
    # 注入一个会在调用时爆炸的 B 包。
    mod_b = types.ModuleType("agent_analysis.persistent_checks_b")
    mod_b.run_checks_b = _boom
    monkeypatch.setitem(sys.modules, "agent_analysis.persistent_checks_b", mod_b)

    orchestrator = _orchestrator(tmp_path)
    report = orchestrator._run_persistent_checks()

    assert report["status"] == "failed"
    assert report["passed_count"] == 0
    assert report["failed_count"] == 0
    assert report["checks"] == []
    assert "check exploded" in report["error"]
    output_path = tmp_path / "persistent_checks_report.json"
    saved = json.loads(output_path.read_text(encoding="utf-8"))
    assert saved["status"] == "failed"
