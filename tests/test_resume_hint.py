"""断点续跑档案：run 中断时凭 resume_hint.json 只补跑缺失阶段。"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from main import _write_resume_hint  # noqa: E402


def test_resume_hint_records_commands_and_snapshot_fingerprint(tmp_path):
    source = tmp_path / "data_collected.json"
    source.write_text('{"ok": true}', encoding="utf-8")
    sha = hashlib.sha256(source.read_bytes()).hexdigest()
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    args = SimpleNamespace(
        date=None,
        models="deepseek-v4-flash,deepseek-v4-pro",
        enable_news=True,
        skip_report=True,
        official=False,
        enable_component_model=False,
        data_json=None,
    )
    data_json = {
        "source_snapshot": {
            "source_path": str(source),
            "source_sha256": sha,
            "effective_date": "live",
        }
    }

    hint_path = _write_resume_hint(str(run_dir), args, data_json)
    hint = json.loads(open(hint_path, encoding="utf-8").read())

    assert hint["source_path"] == str(source)
    assert hint["source_sha256"] == sha
    assert "--resume-run-dir" in hint["console_command"]
    assert str(run_dir) in hint["console_command"]
    assert "--enable-news" in hint["console_command"]
    assert "--skip-legacy-report" in hint["console_command"]
    assert "--resume-from-existing" in hint["main_command"]
    assert "--data-json" in hint["main_command"]


def test_resume_hint_computes_missing_sha_from_data_json_arg(tmp_path):
    source = tmp_path / "snapshot.json"
    source.write_text('{"ok": 1}', encoding="utf-8")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    args = SimpleNamespace(
        date="2026-05-09",
        models=None,
        enable_news=False,
        skip_report=False,
        official=True,
        enable_component_model=False,
        data_json=str(source),
    )

    hint_path = _write_resume_hint(str(run_dir), args, {})
    hint = json.loads(open(hint_path, encoding="utf-8").read())

    assert hint["source_sha256"] == hashlib.sha256(source.read_bytes()).hexdigest()
    assert "--date 2026-05-09" in hint["console_command"]
    assert "--official" in hint["main_command"]
    assert hint["effective_date"] == "2026-05-09"
