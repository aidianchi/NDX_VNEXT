from __future__ import annotations

import argparse
import json
import logging
import os
from types import SimpleNamespace
from typing import Any, Dict, List

try:
    from .agent_analysis.vnext_reporter import VNextReportGenerator
    from .config import path_config
    from .interactive_chart_workbench import InteractiveChartWorkbenchGenerator
    from .main import run_pipeline, setup_logging
except ImportError:
    from agent_analysis.vnext_reporter import VNextReportGenerator
    from config import path_config
    from interactive_chart_workbench import InteractiveChartWorkbenchGenerator
    from main import run_pipeline, setup_logging


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


def main() -> int:
    args = parse_args()
    setup_logging()

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

    console_summary = {
        **summary,
        "native_brief": brief_path,
        "workbench": workbench_path,
        "manual_data_path": path_config.manual_data_local_path,
        "workbench_modules": _modules(args.workbench_modules),
    }
    run_summary_path = os.path.join(run_dir, "console_run_summary.json")
    latest_summary_path = os.path.join(path_config.logs_dir, "control_service", "latest_console_run.json")
    _write_json(run_summary_path, console_summary)
    _write_json(latest_summary_path, console_summary)
    logging.info("Console product flow complete: %s", json.dumps(console_summary, ensure_ascii=False, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
