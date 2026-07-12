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
    from .event_narrative_ledger import write_event_narrative_ledger
    from .integrated_synthesis_report import build_pure_data_report_manifest, write_integrated_synthesis_report
    from .news_event_data_linker import write_news_event_data_links
    from .news_event_ledger import NewsEventLedgerBuilder
    from .news_layer_analyzer import write_news_layer_analysis
    from .state_ledger import append_state_ledger_entry
except ImportError:
    from agent_analysis import adapt_vnext_to_legacy
    from agent_analysis.orchestrator import VNextOrchestrator
    from agent_analysis.packet_builder import AnalysisPacketBuilder
    from api_config import get_api_key, is_service_enabled
    from chart_time_series_artifacts import write_chart_time_series_artifact
    from config import MODEL_CONFIGS, path_config
    from core import DataCollector, DataIntegrity, ReportGenerator
    from event_narrative_ledger import write_event_narrative_ledger
    from integrated_synthesis_report import build_pure_data_report_manifest, write_integrated_synthesis_report
    from news_event_data_linker import write_news_event_data_links
    from news_event_ledger import NewsEventLedgerBuilder
    from news_layer_analyzer import write_news_layer_analysis
    from state_ledger import append_state_ledger_entry


DEFAULT_MODEL_PRIORITY = [
    "deepseek-v4-flash",
    "deepseek-v4-pro",
]


def _enum_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _schema_guard_summary(artifacts: Dict[str, Any]) -> Dict[str, Any]:
    schema_guard = artifacts.get("schema_guard_report")
    if not schema_guard:
        return {}
    structural_issues = list(getattr(schema_guard, "structural_issues", []) or [])
    consistency_issues = list(getattr(schema_guard, "consistency_issues", []) or [])
    missing_fields = list(getattr(schema_guard, "missing_fields", []) or [])
    passed = bool(getattr(schema_guard, "passed", False))
    return {
        "passed": passed,
        "quality_status": str(getattr(schema_guard, "quality_status", "") or ""),
        "issue_count": len(structural_issues) + len(consistency_issues) + len(missing_fields),
        "structural_issues": structural_issues[:5],
        "consistency_issues": consistency_issues[:5],
        "missing_fields": missing_fields[:5],
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="ndx_vnext first runnable chain")
    parser.add_argument("--date", type=str, help="Backtest date in YYYY-MM-DD format.")
    parser.add_argument("--data-json", type=str, help="Use an existing collector output JSON.")
    parser.add_argument("--run-id", type=str, help="Run id under output/analysis/vnext. Use for isolated historical experiments.")
    parser.add_argument("--output-dir", type=str, help="Exact output directory for this vNext run.")
    parser.add_argument("--models", type=str, help="Comma-separated model priority override.")
    parser.add_argument("--collect-only", action="store_true", help="Only collect market data JSON, then exit before any LLM calls.")
    parser.add_argument("--enable-news", action="store_true", help="Write an independent official news/event sidecar artifact.")
    parser.add_argument("--enable-component-model", action="store_true", help="Enable yfinance component-model PE computation (default OFF; use Wind + History of Market instead).")
    parser.add_argument("--official", action="store_true", help="Mark this run as an official daily entry in the cross-run state ledger.")
    parser.add_argument("--event-only", action="store_true", help="Only build the independent event/news report artifacts; do not run L1-L5 or LLM synthesis.")
    parser.add_argument("--skip-report", action="store_true", help="Stop after logic_json generation.")
    parser.add_argument(
        "--resume-from-existing",
        action="store_true",
        help="Reuse complete vNext stage artifacts in this output dir when input hashes match.",
    )
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


def _unique_run_dir(path: str) -> str:
    if not os.path.exists(path):
        os.makedirs(path, exist_ok=True)
        return path
    index = 2
    while True:
        candidate = f"{path}_{index:02d}"
        if not os.path.exists(candidate):
            os.makedirs(candidate, exist_ok=True)
            return candidate
        index += 1


def build_run_dir(
    backtest_date: Optional[str],
    *,
    run_id: Optional[str] = None,
    output_dir: Optional[str] = None,
    allow_existing: bool = False,
) -> str:
    if output_dir:
        if allow_existing:
            os.makedirs(output_dir, exist_ok=True)
            return output_dir
        return _unique_run_dir(output_dir)
    if run_id:
        safe_run_id = run_id.strip().replace("/", "_")
        if not safe_run_id:
            raise ValueError("--run-id cannot be empty.")
        run_dir = os.path.join(path_config.analysis_dir, "vnext", safe_run_id)
        if allow_existing:
            os.makedirs(run_dir, exist_ok=True)
            return run_dir
        return _unique_run_dir(run_dir)
    if backtest_date:
        date_part = backtest_date.replace("-", "")
        stamp = datetime.now().strftime("%Y%m%d_%H%M")
        return _unique_run_dir(os.path.join(path_config.analysis_dir, "vnext", f"{date_part}_outcome_test_{stamp}"))
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return _unique_run_dir(os.path.join(path_config.analysis_dir, "vnext", stamp))


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


def run_event_only(args: argparse.Namespace) -> Dict[str, Any]:
    backtest_date = validate_date(args.date)
    run_dir = build_run_dir(
        backtest_date,
        run_id=getattr(args, "run_id", None),
        output_dir=getattr(args, "output_dir", None),
        allow_existing=getattr(args, "resume_from_existing", False),
    )
    os.makedirs(run_dir, exist_ok=True)

    news_event_ledger_path = os.path.join(run_dir, "news_event_ledger.json")
    news_event_ledger_payload = NewsEventLedgerBuilder(effective_date=backtest_date).build(news_event_ledger_path)
    news_event_data_links_path = ""
    news_layer_analysis_path = ""
    chart_time_series_path = ""
    data_json_path = getattr(args, "data_json", None)
    data_json: Dict[str, Any] = {}

    if data_json_path:
        data_json = load_data_json(data_json_path)
        packet = AnalysisPacketBuilder().build(
            data_json,
            context={"news_event_ledger_path": news_event_ledger_path, "event_material_policy": "event_only_market_validation_not_l1_l5"},
            output_path=os.path.join(run_dir, "analysis_packet.json"),
        )
        chart_time_series_path = write_chart_time_series_artifact(
            run_dir,
            analysis_packet=packet,
            effective_date=backtest_date,
        )
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
    else:
        news_layer_analysis_path = write_news_layer_analysis(
            run_dir,
            event_ledger=news_event_ledger_payload,
            event_ledger_path=news_event_ledger_path,
        )

    event_narrative_ledger_path = write_event_narrative_ledger(
        run_dir,
        event_ledger=news_event_ledger_payload,
        event_ledger_path=news_event_ledger_path,
        news_layer_analysis_path=news_layer_analysis_path,
        news_event_data_links_path=news_event_data_links_path or None,
        effective_date=backtest_date,
    )
    summary = {
        "mode": "event_only",
        "run_dir": run_dir,
        "data_json": data_json_path or "",
        "chart_time_series": chart_time_series_path,
        "news_event_ledger": news_event_ledger_path,
        "news_event_data_links": news_event_data_links_path,
        "news_layer_analysis": news_layer_analysis_path,
        "event_narrative_ledger": event_narrative_ledger_path,
        "event_source_raw": os.path.join(run_dir, "event_source_raw.jsonl"),
        "event_clusters": os.path.join(run_dir, "event_clusters.json"),
        "event_claim_ledger": os.path.join(run_dir, "event_claim_ledger.json"),
        "event_research_packets": os.path.join(run_dir, "event_research_packets"),
        "event_market_validation": os.path.join(run_dir, "event_market_validation.json"),
        "event_narrative_report": os.path.join(run_dir, "event_narrative_report.md"),
        "event_adversarial_review": os.path.join(run_dir, "event_adversarial_review.json"),
        "event_layer_summary": os.path.join(run_dir, "event_layer_summary.json"),
        "event_mechanism_report": os.path.join(run_dir, "event_mechanism_report.json"),
        "event_mechanism_report_html": os.path.join(run_dir, "event_mechanism_report.html"),
        "cross_layer_questions": os.path.join(run_dir, "cross_layer_questions.json"),
        "event_mechanism_cards": os.path.join(run_dir, "event_mechanism_cards.json"),
        "market_validation_basis": "existing_data_json" if data_json_path else "no_market_data_snapshot",
        "backtest_date": backtest_date,
        "strict_backtest_invariants": data_json.get("strict_backtest_invariants", {}) if data_json else {},
    }
    with open(os.path.join(run_dir, "run_summary.json"), "w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2, default=str)
        handle.write("\n")
    latest_summary_path = os.path.join(path_config.logs_dir, "control_service", "latest_console_run.json")
    os.makedirs(os.path.dirname(latest_summary_path), exist_ok=True)
    with open(latest_summary_path, "w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2, default=str)
        handle.write("\n")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return summary


def run_pipeline(args: argparse.Namespace) -> Dict[str, Any]:
    backtest_date = validate_date(args.date)
    available_models = resolve_available_models(args.models)
    if not available_models:
        raise RuntimeError("No enabled LLM models with effective API keys were found.")
    resume_from_existing = getattr(args, "resume_from_existing", False)

    if args.data_json:
        data_json = load_data_json(args.data_json)
    else:
        collector = DataCollector()
        data_json = collector.run(backtest_date=backtest_date)

    run_dir = build_run_dir(
        backtest_date,
        run_id=getattr(args, "run_id", None),
        output_dir=getattr(args, "output_dir", None),
        allow_existing=resume_from_existing,
    )
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
    recompute_belt_report = integrity_report.get("recompute_belt")
    if isinstance(recompute_belt_report, dict):
        recompute_report_path = os.path.join(run_dir, "recompute_report.json")
        with open(recompute_report_path, "w", encoding="utf-8") as handle:
            json.dump(recompute_belt_report, handle, ensure_ascii=False, indent=2, default=str)
            handle.write("\n")
    if integrity_report.get("blocked") or integrity_report.get("unpublishable"):
        event_narrative_ledger_path = ""
        if args.enable_news and news_event_ledger_payload:
            event_narrative_ledger_path = write_event_narrative_ledger(
                run_dir,
                event_ledger=news_event_ledger_payload,
                event_ledger_path=news_event_ledger_path,
                effective_date=backtest_date,
            )
        pure_data_report_path = os.path.join(run_dir, "pure_data_report.json")
        pure_data_report_payload = build_pure_data_report_manifest(
            run_dir=run_dir,
            data_integrity_report=integrity_report,
            output_path=pure_data_report_path,
        )
        integrated_synthesis_report_path = write_integrated_synthesis_report(
            run_dir,
            pure_data_report=pure_data_report_payload,
            data_integrity_report=integrity_report,
            event_narrative_ledger_path=event_narrative_ledger_path or None,
        )
        summary = {
            "run_dir": run_dir,
            "data_integrity_report": integrity_path,
            "pure_data_report": pure_data_report_path,
            "event_narrative_ledger": event_narrative_ledger_path,
            "event_source_raw": os.path.join(run_dir, "event_source_raw.jsonl") if args.enable_news else "",
            "event_clusters": os.path.join(run_dir, "event_clusters.json") if event_narrative_ledger_path else "",
            "event_claim_ledger": os.path.join(run_dir, "event_claim_ledger.json") if event_narrative_ledger_path else "",
            "event_research_packets": os.path.join(run_dir, "event_research_packets") if event_narrative_ledger_path else "",
            "event_market_validation": os.path.join(run_dir, "event_market_validation.json") if event_narrative_ledger_path else "",
            "event_narrative_report": os.path.join(run_dir, "event_narrative_report.md") if event_narrative_ledger_path else "",
            "event_adversarial_review": os.path.join(run_dir, "event_adversarial_review.json") if event_narrative_ledger_path else "",
            "event_layer_summary": os.path.join(run_dir, "event_layer_summary.json") if event_narrative_ledger_path else "",
            "event_mechanism_report": os.path.join(run_dir, "event_mechanism_report.json") if event_narrative_ledger_path else "",
            "event_mechanism_report_html": os.path.join(run_dir, "event_mechanism_report.html") if event_narrative_ledger_path else "",
            "cross_layer_questions": os.path.join(run_dir, "cross_layer_questions.json") if event_narrative_ledger_path else "",
            "event_mechanism_cards": os.path.join(run_dir, "event_mechanism_cards.json") if event_narrative_ledger_path else "",
            "integrated_synthesis_report": integrated_synthesis_report_path,
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
        context={"news_event_ledger_path": news_event_ledger_path, "event_material_policy": "layer_2_only_not_in_prompt"} if news_event_ledger_path else None,
        output_path=os.path.join(run_dir, "analysis_packet.json"),
    )
    chart_time_series_path = write_chart_time_series_artifact(
        run_dir,
        analysis_packet=packet,
        effective_date=backtest_date,
    )
    news_event_data_links_path = ""
    news_layer_analysis_path = ""
    event_narrative_ledger_path = ""
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
        event_narrative_ledger_path = write_event_narrative_ledger(
            run_dir,
            event_ledger=news_event_ledger_payload,
            news_event_data_links=news_event_data_links_payload,
            event_ledger_path=news_event_ledger_path,
            news_layer_analysis_path=news_layer_analysis_path,
            news_event_data_links_path=news_event_data_links_path,
            effective_date=backtest_date,
        )

    orchestrator = VNextOrchestrator(
        available_models=available_models,
        output_dir=run_dir,
        resume_from_existing=resume_from_existing,
    )
    artifacts = orchestrator.run(packet)
    claim_ledger = artifacts.get("final_claim_ledger") if isinstance(artifacts, dict) else None
    claim_gate = getattr(claim_ledger, "publish_gate", {}) if claim_ledger is not None else {}
    if not isinstance(claim_gate, dict):
        claim_gate = claim_gate.model_dump(mode="json") if hasattr(claim_gate, "model_dump") else {}
    claim_gate_status = str(claim_gate.get("status") or "missing")

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

    pure_data_report_path = os.path.join(run_dir, "pure_data_report.json")
    pure_data_report_payload = build_pure_data_report_manifest(
        run_dir=run_dir,
        data_integrity_report=integrity_report,
        artifacts=artifacts,
        output_path=pure_data_report_path,
    )
    integrated_synthesis_report_path = write_integrated_synthesis_report(
        run_dir,
        pure_data_report=pure_data_report_payload,
        data_integrity_report=integrity_report,
        event_narrative_ledger_path=event_narrative_ledger_path or None,
    )

    report_path = ""
    if not args.skip_report and claim_gate_status != "blocked":
        reporter = ReportGenerator(use_charts=not args.disable_charts)
        report_path = reporter.run(logic_json, data_json, backtest_date=backtest_date)

    schema_summary = _schema_guard_summary(artifacts)
    publish_quality_status = "publishable"
    if schema_summary and not schema_summary.get("passed", True):
        publish_quality_status = "review_required"
    if claim_gate_status == "blocked":
        publish_quality_status = "blocked_by_claim_gate"
    elif claim_gate_status != "pass":
        publish_quality_status = "review_required"

    state_ledger_result: Dict[str, Any] = {}
    try:
        state_ledger_result = append_state_ledger_entry(run_dir, official=getattr(args, "official", False))
    except Exception as exc:
        state_ledger_result = {"status": "failed", "error": str(exc)[:200]}

    summary = {
        "run_dir": run_dir,
        "logic_json": logic_path,
        "report_path": report_path,
        "state_ledger": state_ledger_result,
        "chart_time_series": chart_time_series_path,
        "news_event_ledger": news_event_ledger_path,
        "news_event_data_links": news_event_data_links_path,
        "news_layer_analysis": news_layer_analysis_path,
        "event_narrative_ledger": event_narrative_ledger_path,
        "event_source_raw": os.path.join(run_dir, "event_source_raw.jsonl") if args.enable_news else "",
        "event_clusters": os.path.join(run_dir, "event_clusters.json") if event_narrative_ledger_path else "",
        "event_claim_ledger": os.path.join(run_dir, "event_claim_ledger.json") if event_narrative_ledger_path else "",
        "event_research_packets": os.path.join(run_dir, "event_research_packets") if event_narrative_ledger_path else "",
        "event_market_validation": os.path.join(run_dir, "event_market_validation.json") if event_narrative_ledger_path else "",
        "event_narrative_report": os.path.join(run_dir, "event_narrative_report.md") if event_narrative_ledger_path else "",
        "event_adversarial_review": os.path.join(run_dir, "event_adversarial_review.json") if event_narrative_ledger_path else "",
        "event_layer_summary": os.path.join(run_dir, "event_layer_summary.json") if event_narrative_ledger_path else "",
        "event_mechanism_report": os.path.join(run_dir, "event_mechanism_report.json") if event_narrative_ledger_path else "",
        "event_mechanism_report_html": os.path.join(run_dir, "event_mechanism_report.html") if event_narrative_ledger_path else "",
        "cross_layer_questions": os.path.join(run_dir, "cross_layer_questions.json") if event_narrative_ledger_path else "",
        "event_mechanism_cards": os.path.join(run_dir, "event_mechanism_cards.json") if event_narrative_ledger_path else "",
        "pure_data_report": pure_data_report_path,
        "integrated_synthesis_report": integrated_synthesis_report_path,
        "final_stance": getattr(artifacts["final_adjudication"], "final_stance", ""),
        "approval_status": _enum_value(getattr(artifacts["final_adjudication"], "approval_status", "")),
        "run_review_report": os.path.join(run_dir, "run_review_report.json"),
        "outcome_review_report": os.path.join(run_dir, "outcome_review_report.json"),
        "models": available_models,
        "strict_backtest_invariants": data_json.get("strict_backtest_invariants", {}),
        "runtime_diagnostics": _runtime_diagnostics_summary(data_json),
        "data_quality_summary": _data_quality_summary(data_json),
        "schema_guard_summary": schema_summary,
        "claim_ledger_publish_gate": claim_gate,
        "publish_quality_status": publish_quality_status,
    }
    with open(os.path.join(run_dir, "run_summary.json"), "w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2, default=str)
        handle.write("\n")
    return summary


def main() -> int:
    args = parse_args()
    setup_logging()
    if args.enable_component_model:
        os.environ["NDX_ENABLE_COMPONENT_MODEL"] = "1"
    if args.event_only:
        run_event_only(args)
        return 0
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
