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


def test_create_job_marks_console_launched(tmp_path, monkeypatch):
    """服务启动的 run 子进程必须带 NDX_CONSOLE_LAUNCHED=1（同步巡逻改走控制台圈题）。"""
    import control_service

    captured = {}

    class _FakeProc:
        pid = 424242

        def poll(self):
            return 0

    def _fake_popen(args, **kwargs):
        captured["env"] = kwargs.get("env")
        return _FakeProc()

    monkeypatch.setattr(control_service.subprocess, "Popen", _fake_popen)
    store = JobStore(root=tmp_path / "logs")
    store.create_job(["python3", "noop.py"])

    assert captured["env"]["NDX_CONSOLE_LAUNCHED"] == "1"


def test_gap_selection_endpoints(tmp_path, monkeypatch):
    """GET /gap-candidates 读 pending 文件；POST /gap-selection 校验 run_dir 后写 answer。"""
    import json
    import threading
    import urllib.request
    from http.server import ThreadingHTTPServer

    import control_service

    monkeypatch.setattr(control_service, "_repo_root", lambda: tmp_path)
    server = ThreadingHTTPServer(("127.0.0.1", 0), control_service.ControlServiceHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        def _get(path):
            with urllib.request.urlopen(base + path) as resp:
                return json.loads(resp.read().decode("utf-8"))

        def _post(path, payload):
            req = urllib.request.Request(
                base + path,
                data=json.dumps(payload).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req) as resp:
                    return resp.status, json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                return exc.code, json.loads(exc.read().decode("utf-8"))

        # 无 pending 文件 → pending False
        assert _get("/gap-candidates")["pending"] is False

        ledger_dir = tmp_path / "output" / "state_ledger"
        ledger_dir.mkdir(parents=True)
        (ledger_dir / "gap_selection_pending.json").write_text(json.dumps({
            "run_dir": "R1",
            "deadline_at_utc": "2999-01-01T00:00:00+00:00",
            "candidates": [{"agenda_id": "EV-1", "question": "疑点甲", "tag": "本期新增"}],
        }), encoding="utf-8")

        got = _get("/gap-candidates")
        assert got["pending"] is True
        assert got["candidates"][0]["question"] == "疑点甲"

        # run_dir 不匹配 → 400
        status, _ = _post("/gap-selection", {"run_dir": "WRONG", "selected_agenda_ids": ["EV-1"]})
        assert status == 400

        # 匹配 → answer 落盘，未知 id 被过滤
        status, body = _post("/gap-selection", {"run_dir": "R1", "selected_agenda_ids": ["EV-1", "EV-GHOST"]})
        assert status == 200
        assert body["selected"] == ["EV-1"]
        answer = json.loads((ledger_dir / "gap_selection_answer.json").read_text(encoding="utf-8"))
        assert answer["run_dir"] == "R1"
        assert answer["selected_agenda_ids"] == ["EV-1"]
    finally:
        server.shutdown()
        server.server_close()


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
