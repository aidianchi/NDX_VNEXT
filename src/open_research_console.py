from __future__ import annotations

import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

try:
    from .config import path_config
    from .research_console import ResearchConsoleGenerator
except ImportError:
    from config import path_config
    from research_console import ResearchConsoleGenerator


DEFAULT_PORT = 8765


def _service_is_ready(url: str) -> bool:
    try:
        with urllib.request.urlopen(f"{url}/health", timeout=0.8) as response:
            return response.status == 200
    except (OSError, urllib.error.URLError):
        return False


def _console_is_ready(url: str) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=1.2) as response:
            body = response.read(4096).decode("utf-8", errors="replace")
            return response.status == 200 and "NDX vNext 研究控制台" in body
    except (OSError, urllib.error.URLError):
        return False


def _start_service(repo_root: Path, port: int) -> None:
    logs_dir = Path(path_config.logs_dir) / "control_service"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = logs_dir / "launcher_control_service.log"
    log = log_path.open("a", encoding="utf-8")
    subprocess.Popen(
        [sys.executable, "src/control_service.py", "--port", str(port)],
        cwd=str(repo_root),
        stdout=log,
        stderr=subprocess.STDOUT,
        stdin=subprocess.DEVNULL,
        start_new_session=True,
    )


def _choose_service(repo_root: Path) -> str | None:
    for port in range(DEFAULT_PORT, DEFAULT_PORT + 10):
        url = f"http://127.0.0.1:{port}"
        if _console_is_ready(url):
            return url
        if _service_is_ready(url):
            continue
        _start_service(repo_root, port)
        for _ in range(40):
            if _console_is_ready(url):
                return url
            time.sleep(0.2)
    return None


def main() -> int:
    repo_root = Path(path_config.base_dir).resolve()
    console_path = ResearchConsoleGenerator().run()
    service_url = _choose_service(repo_root)
    target_url = service_url or Path(console_path).resolve().as_uri()
    webbrowser.open(target_url)
    print(f"NDX vNext 控制台已打开：{target_url}")
    if target_url.startswith("file:"):
        print("提示：control service 未启动成功，只打开了静态控制台。运行按钮需要后台服务。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
