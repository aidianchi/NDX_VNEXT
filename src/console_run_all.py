from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Dict, List

try:
    from .agent_analysis.vnext_reporter import VNextReportGenerator
    from .browser_sidecar import (
        collect_trendonify_valuation_sidecar,
        has_available_trendonify_sidecar_payload,
        merge_trendonify_sidecar_payload,
    )
    from .config import path_config
    from .interactive_chart_workbench import InteractiveChartWorkbenchGenerator
    from .main import run_pipeline, setup_logging
    from .manual_data import load_manual_data
except ImportError:
    from agent_analysis.vnext_reporter import VNextReportGenerator
    from browser_sidecar import (
        collect_trendonify_valuation_sidecar,
        has_available_trendonify_sidecar_payload,
        merge_trendonify_sidecar_payload,
    )
    from config import path_config
    from interactive_chart_workbench import InteractiveChartWorkbenchGenerator
    from main import run_pipeline, setup_logging
    from manual_data import load_manual_data


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the full console product flow.")
    parser.add_argument("--date", help="Analysis date in YYYY-MM-DD format.")
    parser.add_argument("--data-json", help="Use an existing collector output JSON.")
    parser.add_argument("--models", default="deepseek-v4-flash,deepseek-v4-pro")
    parser.add_argument(
        "--workbench-modules",
        default="price_technical,volatility_credit,rates_valuation,breadth_concentration,liquidity",
    )
    parser.add_argument("--skip-legacy-report", action="store_true")
    parser.add_argument("--enable-legacy-charts", action="store_true")
    parser.add_argument("--enable-news", action="store_true")
    return parser.parse_args()


def _modules(raw: str) -> List[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _write_json(path: str, payload: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)
        handle.write("\n")


def _sync_run_summary(run_dir: str, console_summary: Dict[str, Any]) -> None:
    summary_path = os.path.join(run_dir, "run_summary.json")
    existing: Dict[str, Any] = {}
    if os.path.exists(summary_path):
        try:
            with open(summary_path, "r", encoding="utf-8") as handle:
                loaded = json.load(handle)
            if isinstance(loaded, dict):
                existing = loaded
        except Exception:
            existing = {}
    merged = {
        **existing,
        "report_path": console_summary.get("report_path") or console_summary.get("native_brief") or existing.get("report_path", ""),
        "native_brief": console_summary.get("native_brief", existing.get("native_brief", "")),
        "workbench": console_summary.get("workbench", existing.get("workbench", "")),
        "console_run_summary": os.path.join(run_dir, "console_run_summary.json"),
    }
    _write_json(summary_path, merged)


def _maybe_refresh_trendonify_sidecar() -> str:
    manual = load_manual_data()
    sidecar = manual.get("browser_sidecar") if isinstance(manual, dict) else {}
    if not isinstance(sidecar, dict) or sidecar.get("source") != "trendonify_ndx_valuation" or not sidecar.get("user_trusted"):
        return ""
    output_path = Path(sidecar.get("output_path") or (Path(path_config.output_dir) / "browser_sidecar" / "trendonify_ndx_valuation.json"))
    logging.info("Trendonify trusted sidecar refresh started: %s", output_path)
    try:
        payload = collect_trendonify_valuation_sidecar(trusted=True)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        existing_payload = None
        if output_path.exists():
            try:
                existing_payload = json.loads(output_path.read_text(encoding="utf-8"))
            except Exception:
                existing_payload = None
            payload = merge_trendonify_sidecar_payload(existing_payload, payload)
        if output_path.exists() and not has_available_trendonify_sidecar_payload(payload):
            failed_output = output_path.with_suffix(".failed.json")
            failed_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            logging.warning(
                "Trendonify trusted sidecar refresh produced no available parsed values; preserving existing sidecar: %s",
                output_path,
            )
            return str(output_path)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        logging.info(
            "Trendonify trusted sidecar refresh complete: %s (%s pages, %s errors)",
            output_path,
            len(payload.get("pages", [])),
            len(payload.get("source_errors", [])),
        )
        return str(output_path)
    except Exception as exc:
        logging.warning(
            "Trendonify trusted sidecar refresh failed; continuing with existing sidecar if present: %s",
            str(exc)[:300],
        )
        return str(output_path) if output_path.exists() else ""


def main() -> int:
    args = parse_args()
    setup_logging()
    trendonify_sidecar_path = _maybe_refresh_trendonify_sidecar()

    pipeline_args = SimpleNamespace(
        date=args.date,
        data_json=args.data_json,
        models=args.models,
        enable_news=args.enable_news,
        skip_report=args.skip_legacy_report,
        disable_charts=not args.enable_legacy_charts,
    )
    summary = run_pipeline(pipeline_args)
    run_dir = summary["run_dir"]
    logging.info("Native brief generation started.")
    brief_path = VNextReportGenerator().run(run_dir, template="brief")
    logging.info("Native brief generated: %s", brief_path)
    logging.info("Workbench generation started.")
    workbench_path = InteractiveChartWorkbenchGenerator().run(run_dir, modules=_modules(args.workbench_modules))
    logging.info("Workbench generated: %s", workbench_path)

    # report_path is legacy HTML report; when skipped, fall back to native_brief
    # so API consumers never see an empty report_path.
    report_path = summary.get("report_path") or brief_path
    console_summary = {
        **summary,
        "report_path": report_path,
        "native_brief": brief_path,
        "workbench": workbench_path,
        "manual_data_path": path_config.manual_data_local_path,
        "trendonify_sidecar_path": trendonify_sidecar_path,
        "workbench_modules": _modules(args.workbench_modules),
    }
    run_summary_path = os.path.join(run_dir, "console_run_summary.json")
    latest_summary_path = os.path.join(path_config.logs_dir, "control_service", "latest_console_run.json")
    _write_json(run_summary_path, console_summary)
    _sync_run_summary(run_dir, console_summary)
    _write_json(latest_summary_path, console_summary)
    logging.info("Console product flow complete: %s", json.dumps(console_summary, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
