from __future__ import annotations

import argparse
import json
import logging
import mimetypes
import os
import signal
import shlex
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import parse_qs, quote, urlparse

try:
    from .config import path_config
    from .manual_data import get_manual_data_local_path, load_manual_data, save_manual_data
    from .research_console import ResearchConsoleGenerator
except ImportError:
    from config import path_config
    from manual_data import get_manual_data_local_path, load_manual_data, save_manual_data
    from research_console import ResearchConsoleGenerator

logger = logging.getLogger(__name__)

ALLOWED_ENTRYPOINTS = {
    "src/main.py": {
        "--date": "value",
        "--data-json": "path",
        "--models": "value",
        "--collect-only": "flag",
        "--skip-report": "flag",
        "--disable-charts": "flag",
        "--enable-legacy-charts": "flag",
        "--enable-news": "flag",
        "--event-only": "flag",
    },
    "src/agent_analysis/vnext_reporter.py": {
        "--run-dir": "path",
        "--template": "value",
        "--output": "path",
    },
    "src/interactive_chart_workbench.py": {
        "--run-dir": "path",
        "--modules": "value",
        "--output": "path",
    },
    "src/report_visual_regression.py": {
        "--brief-html": "path",
        "--workbench-html": "path",
        "--console-html": "path",
        "--output-dir": "path",
    },
    "src/browser_sidecar.py": {
        "--source": "value",
        "--output": "path",
        "--timeout": "value",
        "--wait-seconds": "value",
        "--trusted": "flag",
    },
    "src/news_event_ledger.py": {
        "--output": "path",
        "--no-sec": "flag",
        "--no-rss": "flag",
        "--max-events-per-source": "value",
        "--lookback-days": "value",
        "--effective-date": "value",
        "--no-market-news": "flag",
        "--no-social": "flag",
        "--no-wind": "flag",
    },
    "src/console_run_all.py": {
        "--date": "value",
        "--data-json": "path",
        "--models": "value",
        "--workbench-modules": "value",
        "--skip-legacy-report": "flag",
        "--enable-legacy-charts": "flag",
        "--enable-news": "flag",
    },
}

ALLOWED_ENV_OVERRIDES = {
    "NDX_DISABLE_WIND_L4": {"", "1"},
}


def _repo_root() -> Path:
    return Path(path_config.base_dir).resolve()


def _is_safe_relative_path(value: str) -> bool:
    if value.startswith("-"):
        return False
    path = Path(value)
    if path.is_absolute():
        try:
            path.resolve().relative_to(_repo_root())
        except ValueError:
            return False
        return True
    return ".." not in path.parts


def validate_command(command: str) -> List[str]:
    parts = shlex.split(command)
    if len(parts) < 2:
        raise ValueError("Command is too short.")
    if Path(parts[0]).name not in {"python", "python3"}:
        raise ValueError("Only python/python3 commands are allowed.")
    entrypoint = parts[1]
    allowed_args = ALLOWED_ENTRYPOINTS.get(entrypoint)
    if allowed_args is None:
        raise ValueError(f"Entrypoint is not allowed: {entrypoint}")

    idx = 2
    while idx < len(parts):
        arg = parts[idx]
        if arg not in allowed_args:
            raise ValueError(f"Argument is not allowed: {arg}")
        arg_type = allowed_args[arg]
        if arg_type == "flag":
            idx += 1
            continue
        if idx + 1 >= len(parts):
            raise ValueError(f"Missing value for {arg}")
        value = parts[idx + 1]
        if arg_type == "path" and not _is_safe_relative_path(value):
            raise ValueError(f"Unsafe path value for {arg}: {value}")
        idx += 2
    return parts


def validate_env_overrides(raw_overrides: Any) -> Dict[str, str]:
    if raw_overrides in (None, "", {}):
        return {}
    if not isinstance(raw_overrides, dict):
        raise ValueError("env_overrides must be an object.")
    overrides: Dict[str, str] = {}
    for key, raw_value in raw_overrides.items():
        if key not in ALLOWED_ENV_OVERRIDES:
            raise ValueError(f"Environment override is not allowed: {key}")
        value = "" if raw_value is None else str(raw_value)
        if value not in ALLOWED_ENV_OVERRIDES[key]:
            raise ValueError(f"Invalid value for {key}: {value}")
        overrides[key] = value
    return overrides


def _python_bound_args(args: Sequence[str]) -> List[str]:
    """Run console-submitted python commands in the service interpreter.

    The console intentionally displays portable `python3 ...` commands, but the
    service is the trusted executor. Binding here prevents macOS from launching
    system Python 3.9 when the service itself was started from `.venv`.
    """
    normalized = list(args)
    if normalized and Path(normalized[0]).name in {"python", "python3"}:
        normalized[0] = sys.executable
    return normalized


def _resolve_repo_path(value: str) -> Path:
    if not value:
        raise ValueError("Missing path.")
    path = Path(value)
    if not path.is_absolute():
        path = _repo_root() / path
    resolved = path.resolve()
    resolved.relative_to(_repo_root())
    return resolved


def _read_latest_console_summary() -> Dict[str, Any]:
    path = Path(path_config.logs_dir) / "control_service" / "latest_console_run.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


class JobStore:
    def __init__(self, root: str | Path | None = None) -> None:
        self.root = Path(root or Path(path_config.logs_dir) / "control_service")
        self.root.mkdir(parents=True, exist_ok=True)
        self.processes: Dict[str, subprocess.Popen[str]] = {}

    def _state_path(self, job_id: str) -> Path:
        return self.root / f"{job_id}.json"

    def _log_path(self, job_id: str) -> Path:
        return self.root / f"{job_id}.log"

    def _write_state(self, state: Dict[str, Any]) -> Dict[str, Any]:
        self._state_path(str(state["job_id"])).write_text(
            json.dumps(state, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return state

    def _read_state(self, job_id: str) -> Dict[str, Any]:
        state_path = self._state_path(job_id)
        if not state_path.exists():
            raise KeyError(f"Unknown job_id: {job_id}")
        return json.loads(state_path.read_text(encoding="utf-8"))

    def _tail_log(self, log_path: str | Path, max_bytes: int = 8000) -> str:
        path = Path(log_path)
        if not path.exists():
            return ""
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - max_bytes), os.SEEK_SET)
            return handle.read().decode("utf-8", errors="replace")

    def _pid_exists(self, pid: Optional[int]) -> bool:
        if not pid:
            return False
        try:
            os.kill(pid, 0)
            return True
        except OSError:
            return False

    def create_job(self, args: Sequence[str], env_overrides: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
        job_id = time.strftime("%Y%m%d_%H%M%S") + f"_{int((time.time() % 1) * 1000):03d}"
        log_path = self._log_path(job_id)
        actual_args = _python_bound_args(args)
        process_env = os.environ.copy()
        normalized_env_overrides = dict(env_overrides or {})
        for key, value in normalized_env_overrides.items():
            if value:
                process_env[key] = value
            else:
                process_env.pop(key, None)
        with open(log_path, "w", encoding="utf-8") as log:
            process = subprocess.Popen(
                actual_args,
                cwd=str(_repo_root()),
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                env=process_env,
            )
        self.processes[job_id] = process
        state = {
            "job_id": job_id,
            "pid": process.pid,
            "status": "running",
            "command": actual_args,
            "requested_command": list(args),
            "env_overrides": normalized_env_overrides,
            "log_path": str(log_path),
            "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "exit_code": None,
            "failure_reason": "",
        }
        return self._write_state(state)

    def status(self, job_id: str, *, include_log_tail: bool = True) -> Dict[str, Any]:
        state = self._read_state(job_id)
        status = str(state.get("status") or "")
        if status not in {"completed", "failed", "canceled"}:
            process = self.processes.get(job_id)
            if process is not None:
                return_code = process.poll()
                if return_code is None:
                    state["status"] = "running"
                else:
                    state["exit_code"] = return_code
                    state["completed_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
                    state["status"] = "completed" if return_code == 0 else "failed"
                    if return_code != 0 and not state.get("failure_reason"):
                        state["failure_reason"] = f"Process exited with code {return_code}."
                    self.processes.pop(job_id, None)
                    self._write_state(state)
            elif self._pid_exists(state.get("pid")):
                state["status"] = "running"
            else:
                state["status"] = "unknown"
                state.setdefault("failure_reason", "Service was restarted or process state is no longer available.")
        if include_log_tail:
            state["log_tail"] = self._tail_log(state.get("log_path", ""))
        return state

    def cancel(self, job_id: str) -> Dict[str, Any]:
        state = self.status(job_id, include_log_tail=False)
        if state.get("status") in {"completed", "failed", "canceled"}:
            state["message"] = "任务已经结束，无需取消。"
            return self.status(job_id)

        process = self.processes.get(job_id)
        pid = state.get("pid")
        try:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
            elif self._pid_exists(pid):
                os.kill(int(pid), signal.SIGTERM)
            state["status"] = "canceled"
            state["exit_code"] = None
            state["completed_at_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
            state["failure_reason"] = "Canceled by user request."
            self.processes.pop(job_id, None)
            self._write_state(state)
            state["message"] = "已请求取消任务。"
            return self.status(job_id)
        except Exception as exc:
            state["failure_reason"] = f"Cancel failed: {exc}"
            self._write_state(state)
            raise


def _json_response(handler: BaseHTTPRequestHandler, status: int, payload: Dict[str, Any]) -> None:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "application/json; charset=utf-8")
    handler.send_header("Cache-Control", "no-store, max-age=0")
    handler.send_header("Pragma", "no-cache")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _html_response(handler: BaseHTTPRequestHandler, status: int, body_text: str) -> None:
    body = body_text.encode("utf-8")
    handler.send_response(status)
    handler.send_header("Content-Type", "text/html; charset=utf-8")
    handler.send_header("Cache-Control", "no-store, max-age=0")
    handler.send_header("Pragma", "no-cache")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _bytes_response(handler: BaseHTTPRequestHandler, status: int, body: bytes, content_type: str) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Cache-Control", "no-store, max-age=0")
    handler.send_header("Pragma", "no-cache")
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


def _artifact_url(handler: BaseHTTPRequestHandler, path: str) -> str:
    return f"http://{handler.headers.get('Host', '127.0.0.1:8765')}/artifact?path={quote(path)}"


def _directory_listing(path: Path) -> str:
    links = []
    for child in sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
        href = f"/artifact?path={quote(str(child))}"
        label = f"{child.name}/" if child.is_dir() else child.name
        links.append(f'<li><a href="{href}">{label}</a></li>')
    return (
        "<!doctype html><html><head><meta charset=\"utf-8\"><title>vNext artifacts</title>"
        "<style>body{font-family:-apple-system,BlinkMacSystemFont,Segoe UI,sans-serif;padding:24px;}"
        "a{color:#2563eb;}li{margin:8px 0;}</style></head><body>"
        f"<h1>{path.name}</h1><ul>{''.join(links)}</ul></body></html>"
    )


def _save_manual_json(raw_manual_json: str) -> Dict[str, Any]:
    if not raw_manual_json:
        raise ValueError("manual_json is empty.")
    payload = json.loads(raw_manual_json)
    return save_manual_data(payload)


class ControlServiceHandler(BaseHTTPRequestHandler):
    store = JobStore()

    def do_OPTIONS(self) -> None:  # noqa: N802
        _json_response(self, 200, {"ok": True})

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path in {"", "/", "/console"}:
            try:
                _html_response(self, 200, ResearchConsoleGenerator()._render())
            except Exception as exc:
                _json_response(self, 500, {"ok": False, "message": str(exc)})
            return
        if parsed.path == "/health":
            _json_response(self, 200, {"ok": True, "service": "vnext_control_service"})
            return
        if parsed.path == "/latest-product":
            try:
                summary = _read_latest_console_summary()
                payload = {"ok": True, "summary": summary}
                for key in [
                    "native_brief",
                    "workbench",
                    "report_path",
                    "pure_data_report",
                    "event_mechanism_report_html",
                    "event_mechanism_report",
                    "cross_layer_questions",
                    "event_mechanism_cards",
                    "event_narrative_ledger",
                    "integrated_synthesis_report",
                    "news_event_ledger",
                    "news_event_data_links",
                ]:
                    if summary.get(key):
                        payload[f"{key}_url"] = _artifact_url(self, str(summary[key]))
                _json_response(self, 200, payload)
            except Exception as exc:
                _json_response(self, 500, {"ok": False, "message": str(exc)})
            return
        if parsed.path == "/artifact":
            try:
                raw_path = parse_qs(parsed.query).get("path", [""])[0]
                artifact_path = _resolve_repo_path(raw_path)
                if not artifact_path.exists():
                    _json_response(self, 404, {"ok": False, "message": f"Artifact not found: {artifact_path}"})
                    return
                if artifact_path.is_dir():
                    _html_response(self, 200, _directory_listing(artifact_path))
                    return
                content_type = mimetypes.guess_type(str(artifact_path))[0] or "application/octet-stream"
                if artifact_path.suffix.lower() in {".html", ".htm"}:
                    content_type = "text/html; charset=utf-8"
                elif artifact_path.suffix.lower() == ".json":
                    content_type = "application/json; charset=utf-8"
                _bytes_response(self, 200, artifact_path.read_bytes(), content_type)
            except ValueError as exc:
                _json_response(self, 400, {"ok": False, "message": str(exc)})
            except Exception as exc:
                _json_response(self, 500, {"ok": False, "message": str(exc)})
            return
        if parsed.path == "/manual-data":
            try:
                _json_response(
                    self,
                    200,
                    {
                        "ok": True,
                        "path": get_manual_data_local_path(),
                        "manual_data": load_manual_data(),
                    },
                )
            except Exception as exc:
                _json_response(self, 500, {"ok": False, "message": str(exc)})
            return
        if parsed.path.startswith("/status/"):
            job_id = parsed.path.rsplit("/", 1)[-1]
            try:
                _json_response(self, 200, {"ok": True, "job": self.store.status(job_id)})
            except KeyError as exc:
                _json_response(self, 404, {"ok": False, "message": str(exc)})
            except Exception as exc:
                _json_response(self, 500, {"ok": False, "message": str(exc)})
            return
        _json_response(self, 404, {"ok": False, "message": "Not found"})

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if parsed.path == "/manual-data":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length).decode("utf-8")
            try:
                payload = json.loads(raw or "{}")
                manual_data = _save_manual_json(str(payload.get("manual_json", "")))
                _json_response(
                    self,
                    200,
                    {"ok": True, "path": get_manual_data_local_path(), "manual_data": manual_data},
                )
            except Exception as exc:
                _json_response(self, 400, {"ok": False, "message": str(exc)})
            return
        if parsed.path.startswith("/cancel/"):
            job_id = parsed.path.rsplit("/", 1)[-1]
            try:
                _json_response(self, 200, {"ok": True, "job": self.store.cancel(job_id)})
            except KeyError as exc:
                _json_response(self, 404, {"ok": False, "message": str(exc)})
            except Exception as exc:
                _json_response(self, 500, {"ok": False, "message": str(exc)})
            return
        if parsed.path != "/run":
            _json_response(self, 404, {"ok": False, "message": "Not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        try:
            payload = json.loads(raw or "{}")
            if not payload.get("confirmed"):
                raise ValueError("Run request must include confirmed=true after an explicit user confirmation.")
            manual_json = str(payload.get("manual_json", "") or "")
            if manual_json:
                _save_manual_json(manual_json)
            command = str(payload.get("command", "")).strip()
            args = validate_command(command)
            env_overrides = validate_env_overrides(payload.get("env_overrides"))
            job = self.store.create_job(args, env_overrides=env_overrides)
            _json_response(
                self,
                202,
                {
                    "ok": True,
                    "message": "已提交运行。日志会写入本地 control_service 目录。",
                    "job": job,
                },
            )
        except Exception as exc:
            _json_response(self, 400, {"ok": False, "message": str(exc)})

    def log_message(self, format: str, *args: Any) -> None:
        logger.info("control-service: " + format, *args)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the local vNext control service.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    server = ThreadingHTTPServer((args.host, args.port), ControlServiceHandler)
    logger.info("vNext control service listening on http://%s:%s", args.host, args.port)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("vNext control service stopped.")
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
