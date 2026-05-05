from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from .agent_analysis import adapt_vnext_to_legacy
    from .agent_analysis.orchestrator import VNextOrchestrator
    from .agent_analysis.packet_builder import AnalysisPacketBuilder
    from .api_config import get_api_key, is_service_enabled
    from .chart_time_series_artifacts import write_chart_time_series_artifact
    from .config import MODEL_CONFIGS, path_config
    from .core import DataCollector, DataIntegrity, ReportGenerator
except ImportError:
    from agent_analysis import adapt_vnext_to_legacy
    from agent_analysis.orchestrator import VNextOrchestrator
    from agent_analysis.packet_builder import AnalysisPacketBuilder
    from api_config import get_api_key, is_service_enabled
    from chart_time_series_artifacts import write_chart_time_series_artifact
    from config import MODEL_CONFIGS, path_config
    from core import DataCollector, DataIntegrity, ReportGenerator


DEFAULT_MODEL_PRIORITY = [
    "deepseek-v4-flash",
    "deepseek-v4-pro",
]


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ndx_vnext first runnable chain")
    parser.add_argument("--date", type=str, help="Backtest date in YYYY-MM-DD format.")
    parser.add_argument("--data-json", type=str, help="Use an existing collector output JSON.")
    parser.add_argument("--models", type=str, help="Comma-separated model priority override.")
    parser.add_argument("--skip-report", action="store_true", help="Stop after logic_json generation.")
    parser.add_argument("--disable-charts", action="store_true", help="Disable legacy chart rendering.")
    return parser.parse_args()


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )


def validate_date(date_text: Optional[str]) -> Optional[str]:
    if not date_text:
        return None
    datetime.strptime(date_text, "%Y-%m-%d")
    return date_text


def resolve_available_models(raw_models: Optional[str]) -> List[str]:
    requested = []
    if raw_models:
        requested = [item.strip() for item in raw_models.split(",") if item.strip()]
    order = requested or DEFAULT_MODEL_PRIORITY

    available: List[str] = []
    for model_key in order:
        config = MODEL_CONFIGS.get(model_key)
        if not config:
            continue
        service_name = str(config.get("service", "") or "")
        if not service_name:
            continue
        if is_service_enabled(service_name) and get_api_key(service_name):
            available.append(model_key)
    return available


def load_data_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def build_run_dir(backtest_date: Optional[str]) -> str:
    stamp = backtest_date.replace("-", "") if backtest_date else datetime.now().strftime("%Y%m%d_%H%M%S")
    run_dir = os.path.join(path_config.analysis_dir, "vnext", stamp)
    os.makedirs(run_dir, exist_ok=True)
    return run_dir


def run_pipeline(args: argparse.Namespace) -> Dict[str, Any]:
    backtest_date = validate_date(args.date)
    available_models = resolve_available_models(args.models)
    if not available_models:
        raise RuntimeError("No enabled LLM models with effective API keys were found.")

    if args.data_json:
        data_json = load_data_json(args.data_json)
    else:
        collector = DataCollector()
        data_json = collector.run(backtest_date=backtest_date)

    run_dir = build_run_dir(backtest_date)
    integrity_report = DataIntegrity().run(data_json)
    builder = AnalysisPacketBuilder()
    packet = builder.build(data_json, output_path=os.path.join(run_dir, "analysis_packet.json"))
    chart_time_series_path = write_chart_time_series_artifact(run_dir)

    orchestrator = VNextOrchestrator(available_models=available_models, output_dir=run_dir)
    artifacts = orchestrator.run(packet)

    logic_json = adapt_vnext_to_legacy(
        artifacts["final_adjudication"],
        artifacts["analysis_revised"],
        artifacts["layer_cards"],
        artifacts["bridge_memos"],
        integrity_report,
        data_json=data_json,
        analysis_packet=packet,
        context_brief=artifacts["context_brief"],
        thesis_draft=artifacts["thesis_draft"],
        critique=artifacts["critique"],
        risk_boundary_report=artifacts["risk_boundary_report"],
    )
    logic_path = os.path.join(run_dir, "logic_vnext.json")
    with open(logic_path, "w", encoding="utf-8") as handle:
        json.dump(logic_json, handle, ensure_ascii=False, indent=2)
        handle.write("\n")

    report_path = ""
    if not args.skip_report:
        reporter = ReportGenerator(use_charts=not args.disable_charts)
        report_path = reporter.run(logic_json, data_json, backtest_date=backtest_date)

    summary = {
        "run_dir": run_dir,
        "logic_json": logic_path,
        "report_path": report_path,
        "chart_time_series": chart_time_series_path,
        "final_stance": getattr(artifacts["final_adjudication"], "final_stance", ""),
        "approval_status": _enum_value(getattr(artifacts["final_adjudication"], "approval_status", "")),
        "models": available_models,
    }
    with open(os.path.join(run_dir, "run_summary.json"), "w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2, default=str)
        handle.write("\n")
    return summary


def main() -> int:
    args = parse_args()
    setup_logging()
    summary = run_pipeline(args)
    logging.info("vNext run complete: %s", summary["run_dir"])
    logging.info("Final stance: %s | Approval: %s", summary["final_stance"], summary["approval_status"])
    if summary["report_path"]:
        logging.info("HTML report: %s", summary["report_path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
