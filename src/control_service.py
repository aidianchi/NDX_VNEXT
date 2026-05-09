from __future__ import annotations

import argparse
import json
import logging
import os
import shlex
import subprocess
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Sequence

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

    def create_job(self, args: Sequence[str]) -> Dict[str, Any]:
        job_id = time.strftime("%Y%m%d_%H%M%S")
        log_path = self.root / f"{job_id}.log"
        state_path = self.root / f"{job_id}.json"
        with open(log_path, "w", encoding="utf-8") as log:
            process = subprocess.Popen(
                list(args),
                cwd=str(_repo_root()),
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
            )
        state = {
            "job_id": job_id,
            "pid": process.pid,
            "status": "started",
            "command": list(args),
            "log_path": str(log_path),
            "started_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return state


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
        _json_response(self, 404, {"ok": False, "message": "Not found"})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/run":
            _json_response(self, 404, {"ok": False, "message": "Not found"})
            return
        length = int(self.headers.get("Content-Length", "0"))
        raw = self.rfile.read(length).decode("utf-8")
        try:
            payload = json.loads(raw or "{}")
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
