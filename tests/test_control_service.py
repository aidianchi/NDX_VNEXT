import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from control_service import JobStore, _python_bound_args, validate_command, validate_env_overrides


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


def test_control_service_allows_event_only_command():
    args = validate_command(
        "python3 src/main.py --event-only --date 2026-05-09 --data-json output/data/data_collected_v9_live.json"
    )

    assert args[:2] == ["python3", "src/main.py"]
    assert "--event-only" in args


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


def test_control_service_allows_only_wind_l4_env_override():
    assert validate_env_overrides({"NDX_DISABLE_WIND_L4": "1"}) == {"NDX_DISABLE_WIND_L4": "1"}
    assert validate_env_overrides({"NDX_DISABLE_WIND_L4": ""}) == {"NDX_DISABLE_WIND_L4": ""}

    with pytest.raises(ValueError):
        validate_env_overrides({"PYTHONPATH": "/tmp"})

    with pytest.raises(ValueError):
        validate_env_overrides({"NDX_DISABLE_WIND_L4": "true"})


def test_control_service_records_env_overrides_for_job(tmp_path, monkeypatch):
    monkeypatch.setattr("control_service._repo_root", lambda: tmp_path)
    script = tmp_path / "noop.py"
    script.write_text("print('ok')\n", encoding="utf-8")
    store = JobStore(root=tmp_path / "logs")

    state = store.create_job(
        ["python3", str(script)],
        env_overrides={"NDX_DISABLE_WIND_L4": "1"},
    )
    job = store.status(state["job_id"], include_log_tail=True)

    assert job["env_overrides"] == {"NDX_DISABLE_WIND_L4": "1"}
    assert "noop.py" in " ".join(job["requested_command"])


def test_control_service_allows_console_resume_command():
    args = validate_command(
        "python3 src/console_run_all.py --resume-run-dir output/analysis/vnext/20260719_130534 --enable-news"
    )

    assert args[:2] == ["python3", "src/console_run_all.py"]
    assert "--resume-run-dir" in args


def test_resumable_candidates_list_incomplete_runs_and_verify_snapshot(tmp_path):
    import hashlib
    import json as json_module

    from control_service import _resumable_candidates

    source = tmp_path / "data.json"
    source.write_text('{"ok": true}', encoding="utf-8")
    sha = hashlib.sha256(source.read_bytes()).hexdigest()

    def make_run(name, sha256_value, complete=False):
        run_dir = tmp_path / "vnext" / name
        run_dir.mkdir(parents=True)
        (run_dir / "resume_hint.json").write_text(json_module.dumps({
            "created_utc": "2026-07-19T05:10:00Z",
            "source_path": str(source),
            "source_sha256": sha256_value,
            "console_command": f"python3 src/console_run_all.py --resume-run-dir {run_dir}",
        }), encoding="utf-8")
        if complete:
            (run_dir / "final_adjudication.json").write_text("{}", encoding="utf-8")
            (run_dir / "run_summary.json").write_text("{}", encoding="utf-8")
        return run_dir

    make_run("complete_run", sha, complete=True)
    make_run("broken_run", sha)
    make_run("stale_snapshot_run", "deadbeef")

    candidates = _resumable_candidates(root=tmp_path / "vnext")
    by_id = {item["run_id"]: item for item in candidates}

    assert "complete_run" not in by_id
    assert by_id["broken_run"]["data_snapshot_intact"] is True
    assert "final_adjudication.json" in by_id["broken_run"]["missing_artifacts"]
    assert by_id["broken_run"]["console_command"].startswith("python3 src/console_run_all.py --resume-run-dir")
    assert by_id["stale_snapshot_run"]["data_snapshot_intact"] is False
