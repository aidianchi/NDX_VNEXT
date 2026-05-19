import os
import sys

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
        },
    )

    updated = (run_dir / "run_summary.json").read_text(encoding="utf-8")
    assert '"final_stance": "test"' in updated
    assert '"report_path": "/tmp/native_brief.html"' in updated
    assert '"native_brief": "/tmp/native_brief.html"' in updated
    assert '"workbench": "/tmp/workbench.html"' in updated
    assert "console_run_summary.json" in updated
