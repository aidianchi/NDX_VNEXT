from __future__ import annotations

import argparse
import json
import logging
import os
import signal
import shlex
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence
from urllib.parse import urlparse

try:
    from .config import path_config
except ImportError:
    from config import path_config

logger = logging.getLogger(__name__)

ALLOWED_ENTRYPOINTS = {
    "src/main.py": {
        "--date": "value",
        "--data-json": "path",
        "--models": "value",
        "--skip-report": "flag",
        "--disable-charts": "flag",
        "--enable-legacy-charts": "flag",
        "--enable-news": "flag",
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
    },
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

    def create_job(self, args: Sequence[str]) -> Dict[str, Any]:
        job_id = time.strftime("%Y%m%d_%H%M%S") + f"_{int((time.time() % 1) * 1000):03d}"
        log_path = self._log_path(job_id)
        with open(log_path, "w", encoding="utf-8") as log:
            process = subprocess.Popen(
                list(args),
                cwd=str(_repo_root()),
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
        self.processes[job_id] = process
        state = {
            "job_id": job_id,
            "pid": process.pid,
            "status": "running",
            "command": list(args),
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
    handler.send_header("Access-Control-Allow-Origin", "*")
    handler.send_header("Access-Control-Allow-Headers", "Content-Type")
    handler.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
    handler.send_header("Content-Length", str(len(body)))
    handler.end_headers()
    handler.wfile.write(body)


class ControlServiceHandler(BaseHTTPRequestHandler):
    store = JobStore()

    def do_OPTIONS(self) -> None:  # noqa: N802
        _json_response(self, 200, {"ok": True})

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health":
            _json_response(self, 200, {"ok": True, "service": "vnext_control_service"})
            return
        parsed = urlparse(self.path)
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
            command = str(payload.get("command", "")).strip()
            args = validate_command(command)
            job = self.store.create_job(args)
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
