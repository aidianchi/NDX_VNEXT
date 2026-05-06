import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from report_visual_coverage import audit_visual_coverage


def _write_json(path: Path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_audit_visual_coverage_counts_layer_visuals_and_gaps(tmp_path: Path):
    run_dir = tmp_path / "run"
    _write_json(
        run_dir / "layer_cards" / "L1.json",
        {
            "layer": "L1",
            "indicator_analyses": [
                {"function_id": "get_10y_real_rate", "metric": "10Y real rate"},
                {"function_id": "get_fed_funds_rate", "metric": "Fed funds"},
            ],
        },
    )
    for layer in ["L2", "L3", "L4", "L5"]:
        _write_json(run_dir / "layer_cards" / f"{layer}.json", {"layer": layer, "indicator_analyses": []})
    html_path = tmp_path / "brief.html"
    html_path.write_text(
        '<div data-indicator-visual="L1.get_10y_real_rate"></div>',
        encoding="utf-8",
    )

    summary_path = audit_visual_coverage(run_dir, html_path, tmp_path / "visual_coverage.json")
    payload = json.loads(Path(summary_path).read_text(encoding="utf-8"))

    assert payload["passed"] is True
    assert payload["layers"]["L1"]["indicator_count"] == 2
    assert payload["layers"]["L1"]["visual_count"] == 1
    assert payload["layers"]["L1"]["no_visual_refs"] == ["L1.get_fed_funds_rate"]
