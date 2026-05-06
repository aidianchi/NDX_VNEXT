from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


LAYERS = ["L1", "L2", "L3", "L4", "L5"]


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _layer_refs(run_dir: Path, layer: str) -> List[str]:
    card = _load_json(run_dir / "layer_cards" / f"{layer}.json")
    refs = []
    for item in card.get("indicator_analyses", []) or []:
        function_id = item.get("function_id")
        if function_id:
            refs.append(f"{layer}.{function_id}")
    return refs


def _visual_refs(html_text: str) -> set:
    return set(re.findall(r'data-indicator-visual="([^"]+)"', html_text))


def audit_visual_coverage(run_dir: str | Path, html_path: str | Path, output_path: str | Path) -> str:
    run_path = Path(run_dir)
    html = Path(html_path).read_text(encoding="utf-8")
    visuals = _visual_refs(html)
    layers: Dict[str, Any] = {}
    for layer in LAYERS:
        refs = _layer_refs(run_path, layer)
        with_visual = [ref for ref in refs if ref in visuals]
        no_visual = [ref for ref in refs if ref not in visuals]
        layers[layer] = {
            "indicator_count": len(refs),
            "visual_count": len(with_visual),
            "no_visual_count": len(no_visual),
            "visual_refs": with_visual,
            "no_visual_refs": no_visual,
        }
    payload = {
        "schema_version": "vnext_visual_coverage_v1",
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "run_dir": str(run_path),
        "html_path": str(html_path),
        "passed": any(item["visual_count"] > 0 for item in layers.values()),
        "layers": layers,
        "notes": [
            "No-visual refs are not automatically defects. Single-point indicators without history, structure, range, or pressure context should remain text-only.",
        ],
    }
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return str(destination)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit indicator-level visual coverage in a vNext brief report.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--html", required=True)
    parser.add_argument("--output", required=True)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(audit_visual_coverage(args.run_dir, args.html, args.output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
