import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from report_visual_regression import (
    ReportTarget,
    Viewport,
    build_default_targets,
    run_visual_regression,
)


def test_build_default_targets_names_desktop_and_mobile_outputs(tmp_path: Path):
    brief = tmp_path / "brief.html"
    workbench = tmp_path / "workbench.html"
    targets = build_default_targets(brief, workbench, tmp_path / "shots")

    names = {(target.name, viewport.name, target.output_path.name) for target in targets for viewport in target.viewports}

    assert ("brief", "desktop", "brief_desktop.png") in names
    assert ("brief", "mobile", "brief_mobile.png") in names
    assert ("workbench", "desktop", "workbench_desktop.png") in names
    assert ("workbench", "mobile", "workbench_mobile.png") in names


def test_run_visual_regression_writes_summary_with_fake_runner(tmp_path: Path):
    html = tmp_path / "brief.html"
    html.write_text("<html><body>ok</body></html>", encoding="utf-8")
    target = ReportTarget(
        name="brief",
        html_path=html,
        output_path=tmp_path / "shots" / "brief_desktop.png",
        viewports=[Viewport("desktop", 1440, 1100)],
    )

    def fake_runner(command):
        screenshot_arg = next(item for item in command if item.startswith("--screenshot="))
        output = Path(screenshot_arg.split("=", 1)[1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 2048)
        return 0, "", ""

    summary_path = run_visual_regression([target], chrome_path="/Applications/Fake Chrome", runner=fake_runner)
    payload = json.loads(Path(summary_path).read_text(encoding="utf-8"))

    assert payload["passed"] is True
    assert payload["captures"][0]["target"] == "brief"
    assert payload["captures"][0]["viewport"] == "desktop"
    assert payload["captures"][0]["status"] == "ok"
    assert payload["layout_checks"][0]["status"] == "ok"


def test_run_visual_regression_does_not_duplicate_viewport_suffix(tmp_path: Path):
    html = tmp_path / "brief.html"
    html.write_text("<html><body>ok</body></html>", encoding="utf-8")
    target = ReportTarget(
        name="brief",
        html_path=html,
        output_path=tmp_path / "shots" / "brief_mobile.png",
        viewports=[Viewport("mobile", 390, 1100)],
    )

    def fake_runner(command):
        screenshot_arg = next(item for item in command if item.startswith("--screenshot="))
        output = Path(screenshot_arg.split("=", 1)[1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 2048)
        return 0, "", ""

    summary_path = run_visual_regression([target], chrome_path="/Applications/Fake Chrome", runner=fake_runner)
    payload = json.loads(Path(summary_path).read_text(encoding="utf-8"))

    assert payload["captures"][0]["output_path"].endswith("brief_mobile.png")
    assert "mobile_mobile" not in payload["captures"][0]["output_path"]


def test_run_visual_regression_flags_static_overflow_risk(tmp_path: Path):
    html = tmp_path / "workbench.html"
    html.write_text(
        '<html><body><div style="width: 1800px; white-space: nowrap">too wide</div></body></html>',
        encoding="utf-8",
    )
    target = ReportTarget(
        name="workbench",
        html_path=html,
        output_path=tmp_path / "shots" / "workbench_mobile.png",
        viewports=[Viewport("mobile", 390, 1100)],
    )

    def fake_runner(command):
        screenshot_arg = next(item for item in command if item.startswith("--screenshot="))
        output = Path(screenshot_arg.split("=", 1)[1])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"\x89PNG\r\n\x1a\n" + b"x" * 2048)
        return 0, "", ""

    summary_path = run_visual_regression([target], chrome_path="/Applications/Fake Chrome", runner=fake_runner)
    payload = json.loads(Path(summary_path).read_text(encoding="utf-8"))

    assert payload["passed"] is False
    assert payload["layout_checks"][0]["status"] == "failed"
    assert "fixed_width_exceeds_viewport" in payload["layout_checks"][0]["issues"][0]["kind"]
