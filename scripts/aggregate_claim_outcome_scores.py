from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict


def _load_json(path: Path) -> Dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _empty_bucket() -> Dict[str, int]:
    return {"total": 0, "consistent": 0, "falsifier_triggered": 0, "not_scorable": 0}


def aggregate_scores(root: str | Path) -> Dict[str, Any]:
    root_path = Path(root)
    files = sorted(root_path.glob("**/claim_outcome_scores.json"))
    by_claim_type: Dict[str, Dict[str, int]] = {}
    by_source_tier: Dict[str, Dict[str, int]] = {}
    run_count = 0
    score_count = 0
    for path in files:
        payload = _load_json(path)
        scores = payload.get("scores") if isinstance(payload.get("scores"), list) else []
        if not scores:
            continue
        run_count += 1
        for score in scores:
            if not isinstance(score, dict):
                continue
            score_count += 1
            verdict = str(score.get("verdict") or "not_scorable")
            if verdict not in {"consistent", "falsifier_triggered", "not_scorable"}:
                verdict = "not_scorable"
            claim_type = str(score.get("claim_type") or "other")
            claim_bucket = by_claim_type.setdefault(claim_type, _empty_bucket())
            claim_bucket["total"] += 1
            claim_bucket[verdict] += 1
            tiers = score.get("source_tiers") if isinstance(score.get("source_tiers"), list) else ["unknown"]
            for tier in tiers or ["unknown"]:
                tier_bucket = by_source_tier.setdefault(str(tier or "unknown"), _empty_bucket())
                tier_bucket["total"] += 1
                tier_bucket[verdict] += 1
    return {
        "schema_version": "claim_outcome_aggregate_v1",
        "root": str(root_path),
        "run_count": run_count,
        "score_count": score_count,
        "by_claim_type": by_claim_type,
        "by_source_tier": by_source_tier,
        "no_backflow_rule": "Aggregated outcome scores are post-run learning material only and must not feed future L1-L5 runtime inputs.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Aggregate claim_outcome_scores.json files by claim_type and source_tier.")
    parser.add_argument("root", nargs="?", default="output/analysis/vnext", help="Root directory containing vNext run dirs")
    parser.add_argument("--output", default="", help="Optional JSON output path")
    args = parser.parse_args()
    result = aggregate_scores(args.root)
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
