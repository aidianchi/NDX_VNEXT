import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from main import _schema_guard_summary, build_run_dir, parse_args


def test_main_disables_legacy_charts_by_default(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py"])

    args = parse_args()

    assert args.disable_charts is True


def test_main_can_enable_legacy_charts_explicitly(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py", "--enable-legacy-charts"])

    args = parse_args()

    assert args.disable_charts is False


def test_main_accepts_independent_news_sidecar_flag(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py", "--enable-news"])

    args = parse_args()

    assert args.enable_news is True


def test_main_accepts_resume_from_existing_flag(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py", "--resume-from-existing"])

    args = parse_args()

    assert args.resume_from_existing is True


def test_main_accepts_run_id_and_output_dir(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["main.py", "--date", "2025-04-09", "--run-id", "20250409_outcome_test_unit"])

    args = parse_args()

    assert args.run_id == "20250409_outcome_test_unit"
    assert args.output_dir is None


def test_build_run_dir_for_backtest_creates_unique_experiment_dirs(tmp_path, monkeypatch):
    class _PathConfig:
        analysis_dir = str(tmp_path)

    monkeypatch.setattr("main.path_config", _PathConfig())

    first = build_run_dir("2025-04-09")
    second = build_run_dir("2025-04-09")

    assert first != second
    assert "20250409_outcome_test_" in first
    assert "20250409_outcome_test_" in second
    assert os.path.isdir(first)
    assert os.path.isdir(second)


def test_build_run_dir_allows_existing_output_dir_for_resume(tmp_path):
    existing = tmp_path / "resume_run"
    existing.mkdir()

    run_dir = build_run_dir(None, output_dir=str(existing), allow_existing=True)

    assert run_dir == str(existing)


def test_build_run_dir_allows_existing_run_id_for_resume(tmp_path, monkeypatch):
    class _PathConfig:
        analysis_dir = str(tmp_path)

    monkeypatch.setattr("main.path_config", _PathConfig())
    existing = tmp_path / "vnext" / "resume_run"
    existing.mkdir(parents=True)

    run_dir = build_run_dir(None, run_id="resume_run", allow_existing=True)

    assert run_dir == str(existing)


def test_schema_guard_summary_surfaces_review_required_issues():
    class _SchemaReport:
        passed = False
        quality_status = "review_required"
        structural_issues = []
        consistency_issues = ["Bridge supporting_facts invalid"]
        missing_fields = []

    summary = _schema_guard_summary({"schema_guard_report": _SchemaReport()})

    assert summary["passed"] is False
    assert summary["quality_status"] == "review_required"
    assert summary["issue_count"] == 1
    assert summary["consistency_issues"] == ["Bridge supporting_facts invalid"]
