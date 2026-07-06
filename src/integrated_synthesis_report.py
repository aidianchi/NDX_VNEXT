from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _load_json(path: str | Path, default: Any) -> Any:
    file_path = Path(path)
    if not file_path.exists():
        return default
    with file_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: str | Path, payload: Dict[str, Any]) -> str:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return str(output)


def _as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def _compact_refs(values: List[Any], limit: int = 8) -> List[str]:
    refs: List[str] = []
    for value in values:
        if isinstance(value, str) and value and value not in refs:
            refs.append(value)
        if len(refs) >= limit:
            break
    return refs


def build_pure_data_report_manifest(
    *,
    run_dir: str | Path,
    data_integrity_report: Dict[str, Any],
    artifacts: Optional[Dict[str, Any]] = None,
    output_path: Optional[str | Path] = None,
) -> Dict[str, Any]:
    """Write a manifest that declares the data-only layer-1 artifact set."""
    run_path = Path(run_dir)
    final = getattr((artifacts or {}).get("final_adjudication"), "model_dump", lambda **_: (artifacts or {}).get("final_adjudication", {}))(mode="json") if artifacts else _load_json(run_path / "final_adjudication.json", {})
    synthesis = getattr((artifacts or {}).get("synthesis_packet"), "model_dump", lambda **_: (artifacts or {}).get("synthesis_packet", {}))(mode="json") if artifacts else _load_json(run_path / "synthesis_packet.json", {})
    prompt_policy = {
        "data_only": True,
        "forbidden_runtime_inputs": [
            "news_event_ledger",
            "news_layer_analysis",
            "event_narrative_ledger",
            "event_mechanism_report",
            "cross_layer_questions",
            "browser_sidecar",
            "event_refs",
        ],
        "note": "Layer 1 is the pure data report. Event materials can only appear in layer 2 and layer 3 artifacts.",
    }
    payload = {
        "schema_version": "pure_data_report_v1",
        "generated_at_utc": _utc_now_iso(),
        "run_dir": str(run_path),
        "publish_status": data_integrity_report.get("publish_status") or ("blocked" if data_integrity_report.get("blocked") else ""),
        "prompt_policy": prompt_policy,
        "final_stance": final.get("final_stance", "") if isinstance(final, dict) else "",
        "approval_status": final.get("approval_status", "") if isinstance(final, dict) else "",
        "principal_contradictions": synthesis.get("principal_contradictions", []) if isinstance(synthesis, dict) else [],
        "source_artifacts": {
            "analysis_packet": str(run_path / "analysis_packet.json"),
            "layer_cards": str(run_path / "layer_cards"),
            "bridge_memos": str(run_path / "bridge_memos"),
            "synthesis_packet": str(run_path / "synthesis_packet.json"),
            "thesis_draft": str(run_path / "thesis_draft.json"),
            "risk_boundary_report": str(run_path / "risk_boundary_report.json"),
            "final_adjudication": str(run_path / "final_adjudication.json"),
            "data_integrity_report": str(run_path / "data_integrity_report.json"),
        },
    }
    if output_path:
        _write_json(output_path, payload)
    return payload


class IntegratedSynthesisReportBuilder:
    """Build the layer-3 report without polluting data-only artifacts."""

    def build(
        self,
        *,
        pure_data_report: Dict[str, Any],
        event_narrative_ledger: Optional[Dict[str, Any]] = None,
        event_layer_summary: Optional[Dict[str, Any]] = None,
        event_mechanism_report: Optional[Dict[str, Any]] = None,
        data_integrity_report: Optional[Dict[str, Any]] = None,
        evidence_registry: Optional[Dict[str, Any]] = None,
        final_claim_ledger: Optional[Dict[str, Any]] = None,
        output_path: Optional[str | Path] = None,
        source_paths: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        data_integrity_report = data_integrity_report or {}
        event_narrative_ledger = event_narrative_ledger or {}
        event_layer_summary = event_layer_summary or {}
        event_mechanism_report = event_mechanism_report or {}
        evidence_registry = evidence_registry or {}
        final_claim_ledger = final_claim_ledger or {}
        publish_gate = self._publish_gate(data_integrity_report, event_narrative_ledger)
        events = _as_list(event_narrative_ledger.get("events"))
        claims = [
            claim
            for event in events
            if isinstance(event, dict)
            for claim in _as_list(event.get("claims"))
            if isinstance(claim, dict)
        ]
        judgment = self._main_judgment(pure_data_report, claims, publish_gate)
        payload = {
            "schema_version": "integrated_synthesis_report_v1",
            "generated_at_utc": _utc_now_iso(),
            "policy": {
                "inputs": ["pure_data_report", "event_mechanism_report", "event_layer_summary", "event_narrative_ledger", "evidence_registry", "final_claim_ledger"],
                "no_backflow_rule": "This report must not feed back into L1-L5, Bridge, Thesis, Risk, Reviser, or Final.",
                "evidence_rule": "Event claims can support explanation grades, not L1-L5 evidence_refs.",
            },
            "source_artifacts": source_paths or {},
            "evidence_registry_summary": self._compact_evidence_registry(evidence_registry),
            "final_claim_ledger_summary": self._compact_claim_ledger(final_claim_ledger),
            "event_mechanism_report": self._compact_event_mechanism_report(event_mechanism_report),
            "event_layer_summary": self._compact_event_summary(event_layer_summary),
            "integrated_judgments": [judgment] if judgment else [],
            "conflict_matrix": self._conflict_matrix(claims),
            "unexplained_items": self._unexplained_items(claims, publish_gate),
            "downgraded_claims": self._downgraded_claims(claims),
            "publish_gate": publish_gate,
        }
        if output_path:
            _write_json(output_path, payload)
        return payload

    def _publish_gate(self, data_integrity: Dict[str, Any], event_ledger: Dict[str, Any]) -> Dict[str, Any]:
        status = data_integrity.get("publish_status") or ("blocked" if data_integrity.get("blocked") else "publishable")
        blocking_reasons = _as_list(data_integrity.get("blocking_reasons"))
        if status in {"blocked", "unpublishable"} or data_integrity.get("blocked"):
            return {
                "status": "audit_only",
                "reason": "DataIntegrity blocked or marked the pure data report unpublishable.",
                "blocking_reasons": blocking_reasons,
                "formal_investment_conclusion_allowed": False,
            }
        if not _as_list(event_ledger.get("events")):
            return {
                "status": "publishable_with_caveats",
                "reason": "No layer-2 event ledger was available; integrated report is data-led with limited external context.",
                "blocking_reasons": [],
                "formal_investment_conclusion_allowed": True,
            }
        return {
            "status": "publishable_integrated_report",
            "reason": "Pure data report is publishable and layer-2 event ledger is available.",
            "blocking_reasons": [],
            "formal_investment_conclusion_allowed": True,
            }

    def _compact_event_summary(self, summary: Dict[str, Any]) -> Dict[str, Any]:
        if not summary:
            return {}
        return {
            "most_important_events": _as_list(summary.get("most_important_events"))[:6],
            "most_important_claims": _as_list(summary.get("most_important_claims"))[:8],
            "strongest_counterevidence": _as_list(summary.get("strongest_counterevidence"))[:8],
            "financial_links_most_related_to_layer_1": _as_list(summary.get("financial_links_most_related_to_layer_1")),
            "forbidden_for_l1_l5_statement": summary.get("forbidden_for_l1_l5_statement", ""),
        }

    def _compact_evidence_registry(self, registry: Dict[str, Any]) -> Dict[str, Any]:
        passports = registry.get("passports") if isinstance(registry.get("passports"), dict) else {}
        by_kind: Dict[str, int] = {}
        by_tier: Dict[str, int] = {}
        for item in passports.values():
            if not isinstance(item, dict):
                continue
            kind = str(item.get("evidence_kind") or "unknown")
            tier = str(item.get("source_tier") or "unknown")
            by_kind[kind] = by_kind.get(kind, 0) + 1
            by_tier[tier] = by_tier.get(tier, 0) + 1
        return {
            "schema_version": registry.get("schema_version", ""),
            "passport_count": len(passports),
            "by_kind": by_kind,
            "by_source_tier": by_tier,
            "downgrade_count": len(_as_list(registry.get("downgrade_summary"))),
        }

    def _compact_claim_ledger(self, ledger: Dict[str, Any]) -> Dict[str, Any]:
        entries = _as_list(ledger.get("entries")) if isinstance(ledger, dict) else []
        return {
            "schema_version": ledger.get("schema_version", "") if isinstance(ledger, dict) else "",
            "entry_count": len(entries),
            "publish_gate": ledger.get("publish_gate", {}) if isinstance(ledger.get("publish_gate"), dict) else {},
            "downgraded_claims": [
                {
                    "claim_id": entry.get("claim_id"),
                    "authority_status": entry.get("authority_status"),
                    "downgrade_reason": entry.get("downgrade_reason"),
                }
                for entry in entries
                if isinstance(entry, dict) and entry.get("authority_status") != "verified"
            ][:8],
        }

    def _compact_event_mechanism_report(self, report: Dict[str, Any]) -> Dict[str, Any]:
        if not report:
            return {}
        delivery = report.get("delivery_to_integrated_report", {}) if isinstance(report.get("delivery_to_integrated_report"), dict) else {}
        headline = report.get("headline_judgment", {}) if isinstance(report.get("headline_judgment"), dict) else {}
        return {
            "headline_judgment": {
                "title": headline.get("title", ""),
                "plain_text": headline.get("plain_text", ""),
                "confidence": headline.get("confidence", ""),
                "cannot_be_used_as_primary_evidence": bool(headline.get("cannot_be_used_as_primary_evidence", True)),
            },
            "mainlines": _as_list(report.get("mainlines"))[:4],
            "cross_layer_questions": _as_list(report.get("cross_layer_questions"))[:6],
            "delivery_to_integrated_report": {
                "one_sentence": delivery.get("one_sentence", ""),
                "must_preserve_risks": _as_list(delivery.get("must_preserve_risks"))[:6],
                "watchlist": _as_list(delivery.get("watchlist"))[:8],
            },
        }

    def _main_judgment(self, pure_data: Dict[str, Any], claims: List[Dict[str, Any]], publish_gate: Dict[str, Any]) -> Dict[str, Any]:
        data_refs = self._principal_data_refs(pure_data)
        event_refs = _compact_refs([claim.get("claim_id") for claim in claims], limit=6)
        allowed = bool(publish_gate.get("formal_investment_conclusion_allowed"))
        if not allowed:
            claim = "当前不能发布正式综合投资结论；只能说明数据闸门阻断原因和后续观察。"
            grade = "not_explained"
            confidence = "low"
        elif data_refs and event_refs:
            claim = "纯数据判断可发布，新闻事件只能作为解释线索和待确认问题；综合结论必须以数据侧判断为主，并保留反证。"
            grade = "integrated_explanation"
            confidence = "medium"
        else:
            claim = "纯数据判断可发布，但外部事件材料不足，综合解释应降级为数据侧解读。"
            grade = "data_supported_read"
            confidence = "medium"
        return {
            "judgment_object": "NDX",
            "claim": claim,
            "explanation_grade": grade,
            "confidence": confidence,
            "data_support": data_refs,
            "event_support": event_refs,
            "price_reflection": "unclear",
            "counterevidence": [
                "事件材料不得替代正式数据证据。",
                "新闻与价格同向变化不构成因果证明。",
            ],
            "unresolved_tension": self._unresolved_tensions(pure_data, claims),
            "falsifiers": [
                "DataIntegrity 转为 blocked/unpublishable。",
                "后续正式数据反驳事件叙事对应的金融链路。",
                "事件事实被更高等级来源更正或撤回。",
            ],
            "watchlist": sorted({link for claim in claims for link in _as_list(claim.get("affected_financial_links"))})[:8],
            "publishability_note": publish_gate.get("reason", ""),
        }

    def _principal_data_refs(self, pure_data: Dict[str, Any]) -> List[str]:
        refs: List[str] = []
        for item in _as_list(pure_data.get("principal_contradictions")):
            if isinstance(item, dict):
                refs.extend(_as_list(item.get("evidence_refs")))
        return _compact_refs(refs, limit=8)

    def _unresolved_tensions(self, pure_data: Dict[str, Any], claims: List[Dict[str, Any]]) -> List[str]:
        tensions = []
        if not self._principal_data_refs(pure_data):
            tensions.append("纯数据主要矛盾缺少可压缩引用，综合层只能降低置信度。")
        if claims:
            tensions.append("事件账本只说明外部材料可能影响的金融链路，仍需数据确认。")
        else:
            tensions.append("缺少事件账本，无法判断新闻/事件是否解释数据异常。")
        return tensions

    def _conflict_matrix(self, claims: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        return [
            {
                "claim_id": claim.get("claim_id"),
                "conflict_type": "event_claim_requires_data_confirmation",
                "data_side": "pure_data_report",
                "event_side": claim.get("claim_type"),
                "status": "unresolved",
                "required_check": claim.get("needs_data_confirmation", True),
            }
            for claim in claims[:12]
        ]

    def _unexplained_items(self, claims: List[Dict[str, Any]], publish_gate: Dict[str, Any]) -> List[Dict[str, Any]]:
        items = []
        if publish_gate.get("status") == "audit_only":
            items.append({"item": "data_integrity_blocked", "reason": publish_gate.get("reason", "")})
        for claim in claims:
            if claim.get("needs_data_confirmation"):
                items.append({
                    "item": claim.get("claim_id"),
                    "reason": "Event claim has not been confirmed by pure data evidence.",
                })
        return items[:12]

    def _downgraded_claims(self, claims: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        downgraded = []
        for claim in claims:
            source_type = str(claim.get("source_type") or "")
            if source_type not in {"official_fact", "company_disclosure", "primary_market_data_release"} or claim.get("needs_data_confirmation"):
                downgraded.append({
                    "claim_id": claim.get("claim_id"),
                    "source_type": source_type,
                    "downgraded_to": "plausible_hypothesis" if source_type != "unverified_signal" else "weak_signal",
                    "reason": "Claims without data confirmation cannot become strong investment conclusions.",
                })
        return downgraded[:12]


def write_integrated_synthesis_report(
    run_dir: str | Path,
    *,
    pure_data_report: Optional[Dict[str, Any]] = None,
    event_narrative_ledger: Optional[Dict[str, Any]] = None,
    event_layer_summary: Optional[Dict[str, Any]] = None,
    event_mechanism_report: Optional[Dict[str, Any]] = None,
    data_integrity_report: Optional[Dict[str, Any]] = None,
    evidence_registry: Optional[Dict[str, Any]] = None,
    final_claim_ledger: Optional[Dict[str, Any]] = None,
    pure_data_report_path: Optional[str | Path] = None,
    event_narrative_ledger_path: Optional[str | Path] = None,
    event_layer_summary_path: Optional[str | Path] = None,
    event_mechanism_report_path: Optional[str | Path] = None,
    data_integrity_report_path: Optional[str | Path] = None,
    evidence_registry_path: Optional[str | Path] = None,
    final_claim_ledger_path: Optional[str | Path] = None,
) -> str:
    run_path = Path(run_dir)
    pure_path = Path(pure_data_report_path) if pure_data_report_path else run_path / "pure_data_report.json"
    event_path = Path(event_narrative_ledger_path) if event_narrative_ledger_path else run_path / "event_narrative_ledger.json"
    summary_path = Path(event_layer_summary_path) if event_layer_summary_path else run_path / "event_layer_summary.json"
    mechanism_path = Path(event_mechanism_report_path) if event_mechanism_report_path else run_path / "event_mechanism_report.json"
    integrity_path = Path(data_integrity_report_path) if data_integrity_report_path else run_path / "data_integrity_report.json"
    registry_path = Path(evidence_registry_path) if evidence_registry_path else run_path / "evidence_registry.json"
    claim_ledger_path = Path(final_claim_ledger_path) if final_claim_ledger_path else run_path / "final_claim_ledger.json"
    output_path = run_path / "integrated_synthesis_report.json"
    IntegratedSynthesisReportBuilder().build(
        pure_data_report=pure_data_report if pure_data_report is not None else _load_json(pure_path, {}),
        event_narrative_ledger=event_narrative_ledger if event_narrative_ledger is not None else _load_json(event_path, {}),
        event_layer_summary=event_layer_summary if event_layer_summary is not None else _load_json(summary_path, {}),
        event_mechanism_report=event_mechanism_report if event_mechanism_report is not None else _load_json(mechanism_path, {}),
        data_integrity_report=data_integrity_report if data_integrity_report is not None else _load_json(integrity_path, {}),
        evidence_registry=evidence_registry if evidence_registry is not None else _load_json(registry_path, {}),
        final_claim_ledger=final_claim_ledger if final_claim_ledger is not None else _load_json(claim_ledger_path, {}),
        output_path=output_path,
        source_paths={
            "pure_data_report": str(pure_path),
            "event_mechanism_report": str(mechanism_path),
            "event_layer_summary": str(summary_path),
            "event_narrative_ledger": str(event_path),
            "data_integrity_report": str(integrity_path),
            "evidence_registry": str(registry_path),
            "final_claim_ledger": str(claim_ledger_path),
        },
    )
    return str(output_path)
