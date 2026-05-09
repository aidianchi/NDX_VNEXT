from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Iterable, List, Optional, Sequence, Tuple


Runner = Callable[[Sequence[str]], Tuple[int, str, str]]


@dataclass(frozen=True)
class Viewport:
    name: str
    width: int
    height: int


@dataclass(frozen=True)
class ReportTarget:
    name: str
    html_path: Path
    output_path: Path
    viewports: List[Viewport]


DEFAULT_VIEWPORTS = [
    Viewport("desktop", 1440, 1100),
    Viewport("mobile", 390, 1100),
]


def _default_chrome_path() -> Optional[str]:
    candidates = [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        shutil.which("google-chrome"),
        shutil.which("chromium"),
        shutil.which("chromium-browser"),
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return str(candidate)
    return None


def _run_subprocess(command: Sequence[str]) -> Tuple[int, str, str]:
    completed = subprocess.run(command, text=True, capture_output=True, check=False)
    return completed.returncode, completed.stdout, completed.stderr


def _file_url(path: Path) -> str:
    return path.resolve().as_uri()


def _is_png_nonempty(path: Path, min_bytes: int = 1024) -> bool:
    if not path.exists() or path.stat().st_size < min_bytes:
        return False
    with path.open("rb") as handle:
        return handle.read(8) == b"\x89PNG\r\n\x1a\n"


def _scan_static_overflow_risk(html_path: Path, viewport: Viewport) -> dict:
    """Catch obvious layout risks before a human opens screenshots.

    This is intentionally conservative: it does not try to replace visual QA,
    but it flags fixed-width/nowrap patterns that commonly create mobile
    horizontal scrolling in self-contained HTML reports.
    """
    issues = []
    try:
        html_text = html_path.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        return {"status": "failed", "issues": [{"kind": "html_read_error", "detail": str(exc)[:200]}]}

    for match in re.finditer(r"(?<![-\w])(?:min-)?width\s*:\s*(\d{3,5})px", html_text, flags=re.IGNORECASE):
        prefix = html_text[max(0, match.start() - 96) : match.start()]
        if re.search(r"@media[^{]*$", prefix, flags=re.IGNORECASE):
            continue
        width = int(match.group(1))
        if width > viewport.width:
            issues.append(
                {
                    "kind": "fixed_width_exceeds_viewport",
                    "value": width,
                    "viewport_width": viewport.width,
                    "snippet": html_text[max(0, match.start() - 60) : match.end() + 60],
                }
            )
    if viewport.width <= 480:
        inline_nowrap = r"<[^>]+style=[\"'][^\"']*white-space\s*:\s*nowrap[^\"']*[\"'][^>]*>"
        for match in re.finditer(inline_nowrap, html_text, flags=re.IGNORECASE):
            issues.append(
                {
                    "kind": "mobile_nowrap_overflow_risk",
                    "viewport_width": viewport.width,
                    "snippet": html_text[max(0, match.start() - 60) : match.end() + 60],
                }
            )
    return {"status": "failed" if issues else "ok", "issues": issues[:12]}


def build_default_targets(
    brief_html: str | Path,
    workbench_html: str | Path,
    output_dir: str | Path,
    *,
    viewports: Optional[List[Viewport]] = None,
    console_html: Optional[str | Path] = None,
) -> List[ReportTarget]:
    output = Path(output_dir)
    selected_viewports = viewports or DEFAULT_VIEWPORTS
    targets: List[ReportTarget] = []
    html_targets = [("brief", Path(brief_html)), ("workbench", Path(workbench_html))]
    if console_html:
        html_targets.append(("console", Path(console_html)))
    for name, html_path in html_targets:
        for viewport in selected_viewports:
            targets.append(
                ReportTarget(
                    name=name,
                    html_path=html_path,
                    output_path=output / f"{name}_{viewport.name}.png",
                    viewports=[viewport],
                )
            )
    return targets


def _output_for_viewport(target: ReportTarget, viewport: Viewport) -> Path:
    stem = target.output_path.stem
    for suffix in [f"_{item.name}" for item in DEFAULT_VIEWPORTS]:
        if stem.endswith(suffix):
            stem = stem[: -len(suffix)]
            break
    return target.output_path.with_name(f"{stem}_{viewport.name}.png")


def _capture_command(chrome_path: str, target: ReportTarget, viewport: Viewport, output_path: Path) -> List[str]:
    # macOS Chrome headless keeps a roughly 500px minimum layout viewport.
    # Capturing a narrower screenshot crops that layout instead of testing it.
    capture_width = max(viewport.width, 500)
    return [
        chrome_path,
        "--headless=new",
        "--hide-scrollbars",
        "--disable-gpu",
        "--no-first-run",
        f"--window-size={capture_width},{viewport.height}",
        f"--screenshot={output_path}",
        _file_url(target.html_path),
    ]


def run_visual_regression(
    targets: Iterable[ReportTarget],
    *,
    chrome_path: Optional[str] = None,
    runner: Runner = _run_subprocess,
    summary_path: Optional[str | Path] = None,
) -> str:
    chrome = chrome_path or _default_chrome_path()
    if not chrome:
        raise RuntimeError("Chrome/Chromium not found; cannot capture visual regression screenshots.")

    captures = []
    layout_checks = []
    for target in targets:
        for viewport in target.viewports:
            output_path = _output_for_viewport(target, viewport)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            command = _capture_command(chrome, target, viewport, output_path)
            returncode, stdout, stderr = runner(command)
            ok = returncode == 0 and _is_png_nonempty(output_path)
            captures.append(
                {
                    "target": target.name,
                    "viewport": viewport.name,
                    "html_path": str(target.html_path),
                    "output_path": str(output_path),
                    "width": viewport.width,
                    "height": viewport.height,
                    "status": "ok" if ok else "failed",
                    "returncode": returncode,
                    "stdout": stdout[-1000:],
                    "stderr": stderr[-1000:],
                }
            )
            layout_scan = _scan_static_overflow_risk(target.html_path, viewport)
            layout_checks.append(
                {
                    "target": target.name,
                    "viewport": viewport.name,
                    "html_path": str(target.html_path),
                    **layout_scan,
                }
            )

    first_output = Path(next(iter(captures))["output_path"]).parent if captures else Path("output/reports/visual_regression")
    destination = Path(summary_path) if summary_path else first_output / "visual_regression_summary.json"
    payload = {
        "schema_version": "vnext_visual_regression_v1",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "passed": all(item["status"] == "ok" for item in captures) and all(item["status"] == "ok" for item in layout_checks),
        "captures": captures,
        "layout_checks": layout_checks,
    }
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(destination)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Capture vNext report visual regression screenshots.")
    parser.add_argument("--brief-html", required=True)
    parser.add_argument("--workbench-html", required=True)
    parser.add_argument("--console-html", help="Optional research console HTML to include in desktop/mobile captures.")
    parser.add_argument("--output-dir", default="output/reports/visual_regression")
    parser.add_argument("--chrome-path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    targets = build_default_targets(
        args.brief_html,
        args.workbench_html,
        args.output_dir,
        console_html=args.console_html,
    )
    summary = run_visual_regression(targets, chrome_path=args.chrome_path)
    print(summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
