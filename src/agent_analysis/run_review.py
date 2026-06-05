from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from .contracts import RunReviewFinding, RunReviewReport
except ImportError:
    from contracts import RunReviewFinding, RunReviewReport


INTERNAL_READER_PHRASES = [
    "批准",
    "审批",
    "放行",
    "分析框架完整",
    "质量闸门",
    "quality_gate",
    "adjudicator",
]

REQUIRED_PRICE_REFLECTION_CATEGORIES = {"credit", "rates", "valuation", "technical_panic", "liquidity"}


def _load_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return default


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _collect_refs(payload: Any) -> List[str]:
    refs: List[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            if key == "evidence_refs":
                refs.extend(str(item) for item in _as_list(value))
            else:
                refs.extend(_collect_refs(value))
    elif isinstance(payload, list):
        for item in payload:
            refs.extend(_collect_refs(item))
    return list(dict.fromkeys(ref for ref in refs if ref))


def _reader_text(final: Dict[str, Any]) -> str:
    reader = final.get("reader_final") if isinstance(final.get("reader_final"), dict) else {}
    parts = [
        reader.get("one_liner", ""),
        " ".join(str(item) for item in _as_list(reader.get("three_reasons"))),
    ]
    return " ".join(str(part) for part in parts if part)


def _parse_date_text(value: Any) -> Optional[str]:
    if not value:
        return None
    text = str(value)[:10]
    if len(text) != 10:
        return None
    return text


def _damodaran_erp_payload(analysis_packet: Dict[str, Any]) -> Dict[str, Any]:
    raw_data = analysis_packet.get("raw_data") if isinstance(analysis_packet.get("raw_data"), dict) else {}
    l4 = raw_data.get("L4") if isinstance(raw_data.get("L4"), dict) else {}
    item = l4.get("get_damodaran_us_implied_erp") if isinstance(l4.get("get_damodaran_us_implied_erp"), dict) else {}
    value = item.get("value") if isinstance(item.get("value"), dict) else {}
    return value if isinstance(value, dict) else {}


def _damodaran_review_finding(analysis_packet: Dict[str, Any], backtest_date: Optional[str]) -> RunReviewFinding:
    value = _damodaran_erp_payload(analysis_packet)
    windows = value.get("damodaran_erp_historical_percentiles", {}).get("windows", {}) if isinstance(value, dict) else {}
    window_5y = windows.get("5y") if isinstance(windows, dict) and isinstance(windows.get("5y"), dict) else {}
    window_10y = windows.get("10y") if isinstance(windows, dict) and isinstance(windows.get("10y"), dict) else {}
    cutoff = _parse_date_text(value.get("data_date") or value.get("damodaran_erp_historical_percentiles", {}).get("data_cutoff_date"))
    if backtest_date and cutoff and cutoff > backtest_date:
        return _finding(
            "data",
            "fail",
            f"Damodaran ERP 分位数据截止日 {cutoff} 晚于回测日 {backtest_date}，存在前视泄露风险。",
            ["analysis_packet.json:raw_data.L4.get_damodaran_us_implied_erp"],
            recommended_rule_update="Damodaran ERP percentile 必须先按 backtest_date 裁剪月度序列再计算。",
        )
    statuses = {str(window_5y.get("status") or ""), str(window_10y.get("status") or "")}
    artifact_ref = ["analysis_packet.json:raw_data.L4.get_damodaran_us_implied_erp.value.damodaran_erp_historical_percentiles"]
    if not value:
        return _finding("data", "observe", "Damodaran ERP 数据缺失，无法复盘官方月度 ERP 分位。", artifact_ref)
    if statuses <= {"available"}:
        return _finding(
            "data",
            "pass",
            "Damodaran ERP 官方月度分位可用："
            f"current={value.get('erp_t12m_adjusted_payout')}，"
            f"5Y={window_5y.get('percentile')}% ({window_5y.get('sample_count')} months)，"
            f"10Y={window_10y.get('percentile')}% ({window_10y.get('sample_count')} months)，"
            f"cutoff={cutoff or 'unknown'}。",
            artifact_ref,
            recommended_rule_update="报告和 prompt 必须继续把 Damodaran US implied ERP historical percentile 与 NDX PE/PB/Forward PE percentile 分开。",
        )
    return _finding(
        "data",
        "observe",
        "Damodaran ERP 官方月度分位不可完整使用："
        f"5Y status={window_5y.get('status')} sample={window_5y.get('sample_count')}/{window_5y.get('required_min_months')}；"
        f"10Y status={window_10y.get('status')} sample={window_10y.get('sample_count')}/{window_10y.get('required_min_months')}；"
        f"cutoff={cutoff or 'unknown'}。",
        artifact_ref,
        recommended_rule_update="样本不足或年度 fallback 时不得伪造 Damodaran ERP percentile。",
    )


def _finding(
    category: str,
    severity: str,
    finding: str,
    artifact_refs: Optional[List[str]] = None,
    evidence_refs: Optional[List[str]] = None,
    recommended_rule_update: str = "",
) -> RunReviewFinding:
    return RunReviewFinding(
        category=category,
        severity=severity,
        finding=finding,
        artifact_refs=artifact_refs or [],
        evidence_refs=evidence_refs or [],
        recommended_rule_update=recommended_rule_update,
    )


def build_run_review_report(
    *,
    run_dir: str = "",
    analysis_packet: Optional[Dict[str, Any]] = None,
    bridges: Optional[List[Dict[str, Any]]] = None,
    synthesis_packet: Optional[Dict[str, Any]] = None,
    thesis_draft: Optional[Dict[str, Any]] = None,
    risk_boundary_report: Optional[Dict[str, Any]] = None,
    final_adjudication: Optional[Dict[str, Any]] = None,
    data_integrity_report: Optional[Dict[str, Any]] = None,
    run_summary: Optional[Dict[str, Any]] = None,
) -> RunReviewReport:
    analysis_packet = analysis_packet or {}
    bridges = bridges or []
    synthesis_packet = synthesis_packet or {}
    thesis_draft = thesis_draft or {}
    risk_boundary_report = risk_boundary_report or {}
    final_adjudication = final_adjudication or {}
    data_integrity_report = data_integrity_report or {}
    run_summary = run_summary or {}

    findings: List[RunReviewFinding] = []

    meta = analysis_packet.get("meta", {}) if isinstance(analysis_packet.get("meta"), dict) else {}
    publish_status = data_integrity_report.get("publish_status") or ("blocked" if data_integrity_report.get("blocked") else "")
    boundaries = meta.get("backtest_data_boundaries") or analysis_packet.get("context", {}).get("backtest_data_boundaries", [])
    invariants = meta.get("strict_backtest_invariants") or analysis_packet.get("context", {}).get("strict_backtest_invariants", {})

    if publish_status in {"blocked", "unpublishable"} or data_integrity_report.get("blocked"):
        findings.append(
            _finding(
                "data",
                "fail",
                "DataIntegrity 阻断或不可发布，不能把报告继续当作可发布结论。",
                ["data_integrity_report.json"],
                recommended_rule_update="DataIntegrity blocked/unpublishable 必须继续作为发布闸门。",
            )
        )
    else:
        findings.append(
            _finding(
                "data",
                "pass",
                "DataIntegrity 未阻断；数据边界可进入后续判断。",
                ["data_integrity_report.json"],
            )
        )

    if meta.get("backtest_date") or run_summary.get("backtest_date"):
        if boundaries or invariants:
            findings.append(
                _finding(
                    "data",
                    "pass",
                    "回测边界或 strict invariant 已入包，缺口没有被静默抹平。",
                    ["analysis_packet.json", "run_summary.json"],
                )
            )
        else:
            findings.append(
                _finding(
                    "data",
                    "observe",
                    "这是回测/快照语境，但未看到 backtest_data_boundaries 或 strict_backtest_invariants。",
                    ["analysis_packet.json", "run_summary.json"],
                    recommended_rule_update="回测产物必须携带数据边界和 invariant 元数据。",
                )
            )

    findings.append(_damodaran_review_finding(analysis_packet, meta.get("backtest_date") or run_summary.get("backtest_date")))

    bridge = bridges[0] if bridges else {}
    typed_conflicts = _as_list(bridge.get("typed_conflicts"))
    principal = bridge.get("principal_contradiction") if isinstance(bridge.get("principal_contradiction"), dict) else {}
    price_map = _as_list(bridge.get("price_reflection_map"))
    if not bridges:
        findings.append(_finding("bridge", "fail", "缺少 Bridge artifact，跨层关系无法复盘。", ["bridge_memos/bridge_0.json"]))
    elif not principal:
        findings.append(
            _finding(
                "bridge",
                "fail" if typed_conflicts else "observe",
                "Bridge 未输出 principal_contradiction；主要矛盾仍可能被 Thesis 自行脑补。",
                ["bridge_memos/bridge_0.json"],
                _collect_refs(typed_conflicts),
                "Bridge 必须原生输出主要矛盾；legacy 兜底只能作为兼容，不应长期依赖。",
            )
        )
    else:
        findings.append(
            _finding(
                "bridge",
                "pass",
                "Bridge 已输出主要矛盾，可供 Thesis 消费。",
                ["bridge_memos/bridge_0.json:principal_contradiction"],
                _collect_refs(principal),
            )
        )
    if not price_map:
        findings.append(
            _finding(
                "bridge",
                "observe",
                "Bridge 未输出 price_reflection_map；价格是否已反映风险仍缺结构化判断。",
                ["bridge_memos/bridge_0.json:price_reflection_map"],
                recommended_rule_update="Bridge 必须判断关键风险/叙事是否已进入价格。",
            )
        )
    else:
        categories = {str(item.get("category") or "") for item in price_map if isinstance(item, dict)}
        missing_categories = sorted(REQUIRED_PRICE_REFLECTION_CATEGORIES - categories)
        thin_items = [
            str(item.get("category") or item.get("target") or "price_reflection")
            for item in price_map
            if isinstance(item, dict)
            and (
                not item.get("rationale")
                or (not _as_list(item.get("counterevidence")) and not _as_list(item.get("counterevidence_refs")))
                or not item.get("action_implication")
            )
        ]
        if missing_categories:
            findings.append(
                _finding(
                    "bridge",
                    "observe",
                    "Bridge price_reflection_map 未覆盖五类价格反映："
                    + ", ".join(missing_categories),
                    ["bridge_memos/bridge_0.json:price_reflection_map"],
                    recommended_rule_update="价格反映地图至少拆成 credit/rates/valuation/technical_panic/liquidity 五类。",
                )
            )
        elif thin_items:
            findings.append(
                _finding(
                    "bridge",
                    "observe",
                    "Bridge price_reflection_map 覆盖五类，但部分项缺少反证或动作含义："
                    + ", ".join(thin_items[:5]),
                    ["bridge_memos/bridge_0.json:price_reflection_map"],
                    recommended_rule_update="每类价格反映必须同时写 reflected_state、证据、反证和动作影响。",
                )
            )
        else:
            findings.append(
                _finding(
                    "bridge",
                    "pass",
                    "Bridge price_reflection_map 已覆盖信用、利率、估值、技术恐慌、流动性五类，并包含反证与动作含义。",
                    ["bridge_memos/bridge_0.json:price_reflection_map"],
                )
            )

    thesis_principal = thesis_draft.get("principal_contradiction") if isinstance(thesis_draft.get("principal_contradiction"), dict) else {}
    if not thesis_principal:
        findings.append(
            _finding(
                "thesis",
                "fail",
                "Thesis 未结构化输出主要矛盾，后续 Final 可能退回单一立场。",
                ["thesis_draft.json:principal_contradiction"],
                recommended_rule_update="Thesis 必须消费 Bridge 主要矛盾并说明价格反映与行动含义。",
            )
        )
    elif not thesis_principal.get("price_reflection"):
        findings.append(
            _finding(
                "thesis",
                "observe",
                "Thesis 有主要矛盾，但未说明价格反映程度。",
                ["thesis_draft.json:principal_contradiction.price_reflection"],
                _collect_refs(thesis_principal),
            )
        )
    else:
        findings.append(
            _finding(
                "thesis",
                "pass",
                "Thesis 已把主要矛盾与价格反映绑定。",
                ["thesis_draft.json:principal_contradiction"],
                _collect_refs(thesis_principal),
            )
        )

    if not thesis_draft.get("priced_narrative") or not thesis_draft.get("payoff_assessment"):
        findings.append(
            _finding(
                "thesis",
                "observe",
                "Thesis 的价格叙事或赔率判断为空，容易回到风险清单式表达。",
                ["thesis_draft.json:priced_narrative", "thesis_draft.json:payoff_assessment"],
                recommended_rule_update="状态、价格、赔率三个面必须同时非空。",
            )
        )

    opportunity_costs = _as_list(risk_boundary_report.get("opportunity_costs"))
    confirmation_costs = _as_list(risk_boundary_report.get("confirmation_costs"))
    false_safety = _as_list(risk_boundary_report.get("false_safety_risks"))
    if not risk_boundary_report:
        findings.append(_finding("risk", "fail", "缺少 Risk Sentinel artifact。", ["risk_boundary_report.json"]))
    elif not opportunity_costs or not confirmation_costs:
        findings.append(
            _finding(
                "risk",
                "observe",
                "Risk Sentinel 未完整输出踏空/确认成本，双向风险仍不稳。",
                ["risk_boundary_report.json:opportunity_costs", "risk_boundary_report.json:confirmation_costs"],
                recommended_rule_update="等待确认必须被当作有成本的选择，而不是默认安全答案。",
            )
        )
    else:
        findings.append(
            _finding(
                "risk",
                "pass",
                "Risk Sentinel 已输出踏空/确认成本。",
                ["risk_boundary_report.json"],
                _collect_refs(opportunity_costs + confirmation_costs + false_safety),
            )
        )

    final_principal = final_adjudication.get("principal_contradiction") if isinstance(final_adjudication.get("principal_contradiction"), dict) else {}
    reader = final_adjudication.get("reader_final") if isinstance(final_adjudication.get("reader_final"), dict) else {}
    if not final_principal:
        findings.append(
            _finding(
                "final",
                "fail",
                "Final 未保留 principal_contradiction，读者可能看不到真正支配判断的矛盾。",
                ["final_adjudication.json:principal_contradiction"],
                recommended_rule_update="Final 必须把主要矛盾带进最终读者判断。",
            )
        )
    else:
        findings.append(
            _finding(
                "final",
                "pass",
                "Final 已保留主要矛盾。",
                ["final_adjudication.json:principal_contradiction"],
                _collect_refs(final_principal),
            )
        )

    if not reader.get("one_liner"):
        findings.append(
            _finding(
                "expression",
                "fail",
                "reader_final.one_liner 为空，读者首屏结论不足。",
                ["final_adjudication.json:reader_final.one_liner"],
            )
        )
    else:
        internal_hits = [phrase for phrase in INTERNAL_READER_PHRASES if phrase.lower() in _reader_text(final_adjudication).lower()]
        if internal_hits:
            findings.append(
                _finding(
                    "expression",
                    "fail",
                    "读者结论混入内部审批话术：" + ", ".join(internal_hits),
                    ["final_adjudication.json:reader_final"],
                    recommended_rule_update="reader_final 只写读者行动语言，内部质检留在 quality_gate/adjudicator_notes。",
                )
            )
        else:
            findings.append(
                _finding(
                    "expression",
                    "pass",
                    "reader_final 未发现明显内部审批话术。",
                    ["final_adjudication.json:reader_final"],
                )
            )

    learning_updates = [
        finding.recommended_rule_update
        for finding in findings
        if finding.recommended_rule_update
    ]
    next_run_checks = [
        "检查 Bridge principal_contradiction 是否原生生成，而非只靠 normalize 兜底。",
        "检查 Thesis/Final 是否都保留主要矛盾、价格反映和行动含义。",
        "检查 Risk 是否同时输出下行风险、踏空风险和确认成本。",
        "检查 reader_final 是否没有内部审批话术。",
    ]

    return RunReviewReport(
        run_dir=run_dir,
        backtest_date=meta.get("backtest_date") or run_summary.get("backtest_date"),
        final_stance=final_adjudication.get("final_stance", ""),
        approval_status=str(final_adjudication.get("approval_status", "")),
        publish_status=str(publish_status or ""),
        attribution_findings=findings,
        learning_updates=list(dict.fromkeys(learning_updates)),
        next_run_checks=next_run_checks,
    )


def build_run_review_from_dir(run_dir: str | Path) -> RunReviewReport:
    run_path = Path(run_dir)
    bridge_dir = run_path / "bridge_memos"
    bridges = [
        _load_json(path, {})
        for path in sorted(bridge_dir.glob("*.json"))
        if path.is_file()
    ]
    return build_run_review_report(
        run_dir=str(run_path),
        analysis_packet=_load_json(run_path / "analysis_packet.json", {}),
        bridges=bridges,
        synthesis_packet=_load_json(run_path / "synthesis_packet.json", {}),
        thesis_draft=_load_json(run_path / "thesis_draft.json", {}),
        risk_boundary_report=_load_json(run_path / "risk_boundary_report.json", {}),
        final_adjudication=_load_json(run_path / "final_adjudication.json", {}),
        data_integrity_report=_load_json(run_path / "data_integrity_report.json", {}),
        run_summary=_load_json(run_path / "run_summary.json", {}),
    )


def write_run_review_report(run_dir: str | Path, output_path: str | Path | None = None) -> Path:
    report = build_run_review_from_dir(run_dir)
    target = Path(output_path) if output_path else Path(run_dir) / "run_review_report.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a vNext run review artifact.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()
    path = write_run_review_report(args.run_dir, args.output)
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
