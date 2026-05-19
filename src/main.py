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
    from .news_event_data_linker import write_news_event_data_links
    from .news_event_ledger import NewsEventLedgerBuilder
    from .news_layer_analyzer import write_news_layer_analysis
except ImportError:
    from agent_analysis import adapt_vnext_to_legacy
    from agent_analysis.orchestrator import VNextOrchestrator
    from agent_analysis.packet_builder import AnalysisPacketBuilder
    from api_config import get_api_key, is_service_enabled
    from chart_time_series_artifacts import write_chart_time_series_artifact
    from config import MODEL_CONFIGS, path_config
    from core import DataCollector, DataIntegrity, ReportGenerator
    from news_event_data_linker import write_news_event_data_links
    from news_event_ledger import NewsEventLedgerBuilder
    from news_layer_analyzer import write_news_layer_analysis


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
    parser.add_argument("--collect-only", action="store_true", help="Only collect market data JSON, then exit before any LLM calls.")
    parser.add_argument("--enable-news", action="store_true", help="Write an independent official news/event sidecar artifact.")
    parser.add_argument("--skip-report", action="store_true", help="Stop after logic_json generation.")
    chart_group = parser.add_mutually_exclusive_group()
    chart_group.add_argument(
        "--disable-charts",
        dest="disable_charts",
        action="store_true",
        default=True,
        help="Disable legacy Plotly chart rendering. This is the vNext default.",
    )
    chart_group.add_argument(
        "--enable-legacy-charts",
        dest="disable_charts",
        action="store_false",
        help="Opt in to legacy Plotly charts for old HTML reports.",
    )
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


def collector_output_path(backtest_date: Optional[str]) -> str:
    if backtest_date:
        return os.path.join(path_config.data_dir, f"data_collected_v9_{backtest_date.replace('-', '')}.json")
    return os.path.join(path_config.data_dir, "data_collected_v9_live.json")


def _runtime_diagnostics_summary(data_json: Dict[str, Any]) -> Dict[str, Any]:
    diagnostics = data_json.get("runtime_diagnostics") if isinstance(data_json, dict) else {}
    yf_diag = diagnostics.get("yfinance") if isinstance(diagnostics, dict) else {}
    if not isinstance(yf_diag, dict):
        return {}
    events = yf_diag.get("events") if isinstance(yf_diag.get("events"), list) else []
    notable = [
        {
            "operation": event.get("operation"),
            "ticker": event.get("ticker"),
            "status": event.get("status"),
            "failure_type": event.get("failure_type"),
            "backoff_seconds": event.get("backoff_seconds"),
            "elapsed_ms": event.get("elapsed_ms"),
        }
        for event in events
        if isinstance(event, dict) and event.get("status") in {"retry_scheduled", "cache_fallback", "failed"}
    ]
    return {
        "yfinance": {
            "event_count": yf_diag.get("event_count", len(events)),
            "by_status": yf_diag.get("by_status", {}),
            "by_failure_type": yf_diag.get("by_failure_type", {}),
            "total_backoff_seconds": yf_diag.get("total_backoff_seconds", 0),
            "notable_events": notable[-12:],
        }
    }


def _data_quality_summary(data_json: Dict[str, Any]) -> Dict[str, Any]:
    indicators = data_json.get("indicators", []) if isinstance(data_json, dict) else []
    failure_breakdown: Dict[str, int] = {}
    slowest: List[Dict[str, Any]] = []
    total_duration = 0.0
    degraded = []
    for item in indicators:
        if not isinstance(item, dict):
            continue
        raw = item.get("raw_data") if isinstance(item.get("raw_data"), dict) else {}
        data_quality = raw.get("data_quality") if isinstance(raw.get("data_quality"), dict) else {}
        duration = raw.get("collection_duration_ms") or data_quality.get("collection_duration_ms")
        if isinstance(duration, (int, float)):
            total_duration += float(duration)
            slowest.append({
                "function_id": item.get("function_id"),
                "metric_name": item.get("metric_name"),
                "duration_ms": round(float(duration), 1),
            })
        failure_type = raw.get("failure_type") or data_quality.get("failure_type")
        if failure_type:
            key = str(failure_type)
            failure_breakdown[key] = failure_breakdown.get(key, 0) + 1
            degraded.append({
                "function_id": item.get("function_id"),
                "metric_name": item.get("metric_name"),
                "failure_type": key,
                "failure_reason": raw.get("error") or data_quality.get("failure_reason"),
            })
    slowest = sorted(slowest, key=lambda item: item.get("duration_ms", 0), reverse=True)[:10]
    return {
        "collection_duration_ms": round(total_duration, 1),
        "failure_breakdown_by_type": failure_breakdown,
        "slowest_indicators": slowest,
        "degraded_indicators": degraded[:20],
    }


def run_collect_only(args: argparse.Namespace) -> Dict[str, Any]:
    backtest_date = validate_date(args.date)
    if args.data_json:
        raise RuntimeError("--collect-only cannot be combined with --data-json.")
    collector = DataCollector()
    data_json = collector.run(backtest_date=backtest_date, enable_news=args.enable_news)
    summary = {
        "mode": "collect_only",
        "data_json": collector_output_path(backtest_date),
        "indicator_count": len(data_json.get("indicators", [])),
        "backtest_date": backtest_date,
        "strict_backtest_invariants": data_json.get("strict_backtest_invariants", {}),
        "runtime_diagnostics": _runtime_diagnostics_summary(data_json),
        "data_quality_summary": _data_quality_summary(data_json),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


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
    news_event_ledger_path = ""
    news_event_ledger_payload = None
    if args.enable_news:
        news_event_ledger_path = os.path.join(run_dir, "news_event_ledger.json")
        news_event_ledger_payload = NewsEventLedgerBuilder(effective_date=backtest_date).build(news_event_ledger_path)

    integrity_report = DataIntegrity().run(data_json)
    os.makedirs(run_dir, exist_ok=True)
    integrity_path = os.path.join(run_dir, "data_integrity_report.json")
    with open(integrity_path, "w", encoding="utf-8") as handle:
        json.dump(integrity_report, handle, ensure_ascii=False, indent=2, default=str)
        handle.write("\n")
    if integrity_report.get("blocked") or integrity_report.get("unpublishable"):
        summary = {
            "run_dir": run_dir,
            "data_integrity_report": integrity_path,
            "report_path": "",
            "chart_time_series": "",
            "final_stance": "",
            "approval_status": "blocked_by_data_integrity",
            "models": available_models,
            "blocked": True,
            "blocking_reasons": integrity_report.get("blocking_reasons", []),
            "strict_backtest_invariants": data_json.get("strict_backtest_invariants", {}),
            "runtime_diagnostics": _runtime_diagnostics_summary(data_json),
            "data_quality_summary": _data_quality_summary(data_json),
        }
        with open(os.path.join(run_dir, "run_summary.json"), "w", encoding="utf-8") as handle:
            json.dump(summary, handle, ensure_ascii=False, indent=2, default=str)
            handle.write("\n")
        raise RuntimeError("DataIntegrity blocked this run: " + "；".join(summary["blocking_reasons"]))
    builder = AnalysisPacketBuilder()
    packet = builder.build(
        data_json,
        event_ledger=news_event_ledger_payload,
        event_ledger_path=news_event_ledger_path or None,
        context={"news_event_ledger_path": news_event_ledger_path} if news_event_ledger_path else None,
        output_path=os.path.join(run_dir, "analysis_packet.json"),
    )
    chart_time_series_path = write_chart_time_series_artifact(
        run_dir,
        analysis_packet=packet,
        effective_date=backtest_date,
    )
    news_event_data_links_path = ""
    news_layer_analysis_path = ""
    if args.enable_news and news_event_ledger_payload:
        news_event_data_links_path = write_news_event_data_links(
            run_dir,
            event_ledger=news_event_ledger_payload,
            analysis_packet=packet,
            event_ledger_path=news_event_ledger_path,
            chart_time_series_path=chart_time_series_path,
        )
        with open(news_event_data_links_path, "r", encoding="utf-8") as handle:
            news_event_data_links_payload = json.load(handle)
        news_layer_analysis_path = write_news_layer_analysis(
            run_dir,
            event_ledger=news_event_ledger_payload,
            news_event_data_links=news_event_data_links_payload,
            event_ledger_path=news_event_ledger_path,
            news_event_data_links_path=news_event_data_links_path,
        )

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
        "news_event_ledger": news_event_ledger_path,
        "news_event_data_links": news_event_data_links_path,
        "news_layer_analysis": news_layer_analysis_path,
        "final_stance": getattr(artifacts["final_adjudication"], "final_stance", ""),
        "approval_status": _enum_value(getattr(artifacts["final_adjudication"], "approval_status", "")),
        "models": available_models,
        "strict_backtest_invariants": data_json.get("strict_backtest_invariants", {}),
        "runtime_diagnostics": _runtime_diagnostics_summary(data_json),
        "data_quality_summary": _data_quality_summary(data_json),
    }
    with open(os.path.join(run_dir, "run_summary.json"), "w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2, default=str)
        handle.write("\n")
    return summary


def main() -> int:
    args = parse_args()
    setup_logging()
    if args.collect_only:
        run_collect_only(args)
        return 0
    summary = run_pipeline(args)
    logging.info("vNext run complete: %s", summary["run_dir"])
    logging.info("Final stance: %s | Approval: %s", summary["final_stance"], summary["approval_status"])
    if summary["report_path"]:
        logging.info("HTML report: %s", summary["report_path"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
