import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import console_run_all


def test_trusted_trendonify_sidecar_refresh_failure_does_not_abort(tmp_path, monkeypatch):
    sidecar_path = tmp_path / "browser_sidecar" / "trendonify_ndx_valuation.json"
    monkeypatch.setattr(console_run_all.path_config, "output_dir", str(tmp_path))
    monkeypatch.setattr(
        console_run_all,
        "load_manual_data",
        lambda: {
            "browser_sidecar": {
                "source": "trendonify_ndx_valuation",
                "user_trusted": True,
            }
        },
    )
    monkeypatch.setattr(
        console_run_all,
        "collect_trendonify_valuation_sidecar",
        lambda trusted=True: (_ for _ in ()).throw(RuntimeError("bb-browser missing")),
    )

    assert console_run_all._maybe_refresh_trendonify_sidecar() == ""

    sidecar_path.parent.mkdir(parents=True)
    sidecar_path.write_text("{}", encoding="utf-8")

    assert console_run_all._maybe_refresh_trendonify_sidecar() == str(sidecar_path)


def test_trusted_trendonify_sidecar_refresh_preserves_existing_when_parse_empty(tmp_path, monkeypatch):
    sidecar_path = tmp_path / "browser_sidecar" / "trendonify_ndx_valuation.json"
    sidecar_path.parent.mkdir(parents=True)
    sidecar_path.write_text('{"pages":[{"parsed":{"value":38.07}}]}', encoding="utf-8")
    monkeypatch.setattr(console_run_all.path_config, "output_dir", str(tmp_path))
    monkeypatch.setattr(
        console_run_all,
        "load_manual_data",
        lambda: {
            "browser_sidecar": {
                "source": "trendonify_ndx_valuation",
                "user_trusted": True,
            }
        },
    )
    monkeypatch.setattr(
        console_run_all,
        "collect_trendonify_valuation_sidecar",
        lambda trusted=True: {"pages": [{"parsed": {"availability": "unavailable", "value": None}}]},
    )

    assert console_run_all._maybe_refresh_trendonify_sidecar() == str(sidecar_path)
    assert sidecar_path.read_text(encoding="utf-8") == '{"pages":[{"parsed":{"value":38.07}}]}'
    assert sidecar_path.with_suffix(".failed.json").exists()


def test_trusted_trendonify_sidecar_refresh_merges_partial_success(tmp_path, monkeypatch):
    sidecar_path = tmp_path / "browser_sidecar" / "trendonify_ndx_valuation.json"
    sidecar_path.parent.mkdir(parents=True)
    sidecar_path.write_text(
        '{"pages":[{"page_type":"trailing_pe","parsed":{"availability":"available","value":38.07}}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(console_run_all.path_config, "output_dir", str(tmp_path))
    monkeypatch.setattr(
        console_run_all,
        "load_manual_data",
        lambda: {
            "browser_sidecar": {
                "source": "trendonify_ndx_valuation",
                "user_trusted": True,
            }
        },
    )
    monkeypatch.setattr(
        console_run_all,
        "collect_trendonify_valuation_sidecar",
        lambda trusted=True: {
            "generated_at_utc": "2026-05-12T13:00:00Z",
            "pages": [
                {"page_type": "trailing_pe", "parsed": {"availability": "unavailable", "value": None}},
                {"page_type": "forward_pe", "parsed": {"availability": "available", "value": 23.8}},
            ],
        },
    )

    assert console_run_all._maybe_refresh_trendonify_sidecar() == str(sidecar_path)
    refreshed = sidecar_path.read_text(encoding="utf-8")
    assert '"value": 38.07' in refreshed
    assert '"value": 23.8' in refreshed
    assert "preserved_existing_page_types" in refreshed


def test_console_summary_syncs_native_paths_back_to_run_summary(tmp_path):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "run_summary.json").write_text(
        '{"run_dir":"' + str(run_dir) + '","report_path":"","final_stance":"test"}',
        encoding="utf-8",
    )

    console_run_all._sync_run_summary(
        str(run_dir),
        {
            "report_path": "/tmp/native_brief.html",
            "native_brief": "/tmp/native_brief.html",
            "workbench": "/tmp/workbench.html",
            "prompt_inspector": "/tmp/prompt_inspector.html",
        },
    )

    updated = (run_dir / "run_summary.json").read_text(encoding="utf-8")
    assert '"final_stance": "test"' in updated
    assert '"report_path": "/tmp/native_brief.html"' in updated
    assert '"native_brief": "/tmp/native_brief.html"' in updated
    assert '"workbench": "/tmp/workbench.html"' in updated
    assert '"prompt_inspector": "/tmp/prompt_inspector.html"' in updated
    assert "console_run_summary.json" in updated


def test_console_run_all_supplies_resume_default_to_pipeline(tmp_path, monkeypatch):
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    captured = {}

    monkeypatch.setattr(
        console_run_all,
        "parse_args",
        lambda: SimpleNamespace(
            date=None,
            data_json=None,
            models="deepseek-v4-flash",
            workbench_modules="price_technical",
            skip_legacy_report=True,
            enable_legacy_charts=False,
            enable_news=False,
        ),
    )
    monkeypatch.setattr(console_run_all, "setup_logging", lambda: None)
    monkeypatch.setattr(console_run_all, "_maybe_refresh_trendonify_sidecar", lambda: "")

    def fake_run_pipeline(args):
        captured["resume_from_existing"] = getattr(args, "resume_from_existing", None)
        return {"run_dir": str(run_dir), "report_path": ""}

    monkeypatch.setattr(console_run_all, "run_pipeline", fake_run_pipeline)
    monkeypatch.setattr(console_run_all.PromptInspectorGenerator, "run", lambda self, run_dir: "/tmp/prompt.html")
    monkeypatch.setattr(console_run_all.VNextReportGenerator, "run", lambda self, run_dir, template="brief": "/tmp/brief.html")
    monkeypatch.setattr(console_run_all.InteractiveChartWorkbenchGenerator, "run", lambda self, run_dir, modules: "/tmp/workbench.html")
    monkeypatch.setattr(console_run_all.path_config, "logs_dir", str(tmp_path / "logs"))

    assert console_run_all.main() == 0
    assert captured["resume_from_existing"] is False


def test_resolve_resume_source_verifies_snapshot_fingerprint(tmp_path):
    import hashlib
    import json

    import pytest

    source = tmp_path / "data.json"
    source.write_text('{"ok": true}', encoding="utf-8")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    hint = {
        "source_path": str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    }
    (run_dir / "resume_hint.json").write_text(json.dumps(hint), encoding="utf-8")

    assert console_run_all._resolve_resume_source(str(run_dir)) == str(source)

    source.write_text('{"ok": false}', encoding="utf-8")
    with pytest.raises(ValueError, match="校验和"):
        console_run_all._resolve_resume_source(str(run_dir))

    (run_dir / "resume_hint.json").unlink()
    with pytest.raises(ValueError, match="找不到"):
        console_run_all._resolve_resume_source(str(run_dir))


def test_console_run_all_resume_run_dir_reuses_run_and_snapshot(tmp_path, monkeypatch):
    import hashlib
    import json

    source = tmp_path / "data.json"
    source.write_text('{"ok": true}', encoding="utf-8")
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    (run_dir / "resume_hint.json").write_text(json.dumps({
        "source_path": str(source),
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    }), encoding="utf-8")
    captured = {}

    monkeypatch.setattr(
        console_run_all,
        "parse_args",
        lambda: SimpleNamespace(
            date=None,
            data_json=None,
            models="deepseek-v4-flash",
            workbench_modules="price_technical",
            skip_legacy_report=True,
            enable_legacy_charts=False,
            enable_news=False,
            resume_run_dir=str(run_dir),
        ),
    )
    monkeypatch.setattr(console_run_all, "setup_logging", lambda: None)
    monkeypatch.setattr(console_run_all, "_maybe_refresh_trendonify_sidecar", lambda: "")

    def fake_run_pipeline(args):
        captured["resume_from_existing"] = getattr(args, "resume_from_existing", None)
        captured["output_dir"] = getattr(args, "output_dir", None)
        captured["data_json"] = getattr(args, "data_json", None)
        return {"run_dir": str(run_dir), "report_path": ""}

    monkeypatch.setattr(console_run_all, "run_pipeline", fake_run_pipeline)
    monkeypatch.setattr(console_run_all.PromptInspectorGenerator, "run", lambda self, run_dir: "/tmp/prompt.html")
    monkeypatch.setattr(console_run_all.VNextReportGenerator, "run", lambda self, run_dir, template="brief": "/tmp/brief.html")
    monkeypatch.setattr(console_run_all.InteractiveChartWorkbenchGenerator, "run", lambda self, run_dir, modules: "/tmp/workbench.html")
    monkeypatch.setattr(console_run_all.path_config, "logs_dir", str(tmp_path / "logs"))

    assert console_run_all.main() == 0
    assert captured["resume_from_existing"] is True
    assert captured["output_dir"] == str(run_dir)
    assert captured["data_json"] == str(source)
