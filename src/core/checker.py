from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional

try:
    from ..data_availability import NO_DATA_AVAILABLE, has_meaningful_observation_value, no_data_reason
except ImportError:
    from data_availability import NO_DATA_AVAILABLE, has_meaningful_observation_value, no_data_reason

try:
    from ..data_evidence import data_evidence_issues, flatten_issue_groups
except ImportError:
    from data_evidence import data_evidence_issues, flatten_issue_groups


class DataIntegrity:
    """Generate a compact reliability report from collector output."""

    def _raw_data(self, item: Dict[str, Any]) -> Dict[str, Any]:
        return item.get("raw_data") if isinstance(item.get("raw_data"), dict) else {}

    def _is_skipped(self, item: Dict[str, Any]) -> bool:
        raw = self._raw_data(item)
        return bool(item.get("backtest_skipped") or raw.get("backtest_skipped"))

    def _has_value(self, item: Dict[str, Any]) -> bool:
        raw = self._raw_data(item)
        if raw:
            if no_data_reason(raw):
                return False
            if "value" in raw:
                return has_meaningful_observation_value(raw.get("value"))
            return True
        if item.get("error"):
            return False
        if no_data_reason(item):
            return False
        return has_meaningful_observation_value(item.get("value"))

    def _no_data_reason(self, item: Dict[str, Any]) -> Optional[str]:
        raw = self._raw_data(item)
        return no_data_reason(raw) if raw else no_data_reason(item)

    def _fallback_chain(self, item: Dict[str, Any]) -> List[str]:
        raw = self._raw_data(item)
        data_quality = raw.get("data_quality") if isinstance(raw.get("data_quality"), dict) else {}
        chain = data_quality.get("fallback_chain") or raw.get("fallback_chain")
        return chain if isinstance(chain, list) else []

    def _coverage_numbers(self, value: Any) -> Iterable[float]:
        if isinstance(value, dict):
            for key, item in value.items():
                key_l = str(key).lower()
                if isinstance(item, (int, float)) and not isinstance(item, bool):
                    if "pct" in key_l or "percent" in key_l:
                        yield max(0.0, min(1.0, float(item) / 100.0))
                    elif key_l in {"coverage", "coverage_ratio"}:
                        yield max(0.0, min(1.0, float(item)))
                elif isinstance(item, dict):
                    yield from self._coverage_numbers(item)

    def _coverage_factor(self, item: Dict[str, Any]) -> float:
        raw = self._raw_data(item)
        data_quality = raw.get("data_quality") if isinstance(raw.get("data_quality"), dict) else {}
        coverage = data_quality.get("coverage")
        numbers = list(self._coverage_numbers(coverage))
        if numbers:
            return min(numbers)
        if isinstance(coverage, dict):
            missing = coverage.get("missing_tickers") or coverage.get("missing_constituents")
            if isinstance(missing, list) and missing:
                return 0.75
        return 1.0

    def _parse_date(self, value: Any) -> Optional[datetime]:
        if value is None:
            return None
        try:
            return datetime.fromisoformat(str(value)[:10])
        except Exception:
            return None

    def _is_observation_date_key(self, key: Any) -> bool:
        key_l = str(key).lower()
        if "timestamp" in key_l or "generated_at" in key_l or "collection" in key_l:
            return False
        return key_l in {
            "date",
            "data_date",
            "effective_date",
            "observation_date",
            "as_of",
            "asof",
            "expiry",
            "expiration",
            "expiration_date",
            "opt_date",
            "option_date",
            "published_at",
        }

    def _dates_in_note(self, text: str) -> Iterable[str]:
        for match in re.finditer(r"\b(20\d{2}-\d{2}-\d{2})\b", text):
            yield match.group(1)

    def _iter_future_date_candidates(self, value: Any, *, path: str = "") -> Iterable[tuple[str, Any]]:
        if isinstance(value, dict):
            for key, item in value.items():
                child_path = f"{path}.{key}" if path else str(key)
                if self._is_observation_date_key(key):
                    yield child_path, item
                if isinstance(item, str) and str(key).lower() in {"note", "notes", "reason", "unavailable_reason"}:
                    for date_text in self._dates_in_note(item):
                        yield f"{child_path}[text_date]", date_text
                yield from self._iter_future_date_candidates(item, path=child_path)
        elif isinstance(value, list):
            for index, item in enumerate(value):
                yield from self._iter_future_date_candidates(item, path=f"{path}[{index}]")

    def _future_date_violations(self, item: Dict[str, Any], backtest_date: Optional[str]) -> List[str]:
        effective = self._parse_date(backtest_date)
        if effective is None:
            return []
        violations = []
        for key, value in self._iter_future_date_candidates(self._raw_data(item)):
            parsed = self._parse_date(value)
            if parsed is not None and parsed > effective:
                violations.append(f"{key}={str(value)[:10]}")
        return sorted(set(violations))

    def _strict_backtest_invariants(self, data_json: Dict[str, Any]) -> Dict[str, Any]:
        invariants = data_json.get("strict_backtest_invariants") if isinstance(data_json, dict) else {}
        return invariants if isinstance(invariants, dict) else {}

    def _source_disagreement_issues(self, item: Dict[str, Any]) -> List[Dict[str, Any]]:
        raw = self._raw_data(item)
        data_quality = raw.get("data_quality") if isinstance(raw.get("data_quality"), dict) else {}
        issues = data_quality.get("source_disagreement_issues")
        if not isinstance(issues, list):
            return []
        label = item.get("metric_name") or item.get("function_id") or "unknown_metric"
        normalized = []
        for issue in issues:
            if not isinstance(issue, dict):
                continue
            normalized.append({"indicator": label, **issue})
        return normalized

    def run(self, data_json: Dict[str, Any]) -> Dict[str, Any]:
        indicators = data_json.get("indicators", [])
        total = len(indicators)
        backtest_date = data_json.get("backtest_date")
        unavailable = sum(1 for item in indicators if self._is_skipped(item))
        successful_items = [
            item for item in indicators
            if not item.get("error") and not self._is_skipped(item) and self._has_value(item)
        ]
        successful = len(successful_items)
        no_data_items = [
            item for item in indicators
            if not item.get("error") and not self._is_skipped(item) and self._no_data_reason(item)
        ]
        coverage_factors = {id(item): self._coverage_factor(item) for item in successful_items}
        future_violations = {
            item.get("metric_name") or item.get("function_id"): self._future_date_violations(item, backtest_date)
            for item in indicators
        }
        future_violations = {key: value for key, value in future_violations.items() if value}
        data_evidence_contract_issues = []
        for item in indicators:
            raw = self._raw_data(item)
            function_id = str(item.get("function_id") or raw.get("function_id") or item.get("metric_name") or "unknown_metric")
            issue_groups = data_evidence_issues(raw, function_id=function_id, backtest_date=backtest_date)
            for issue in flatten_issue_groups(issue_groups):
                issue["metric_name"] = item.get("metric_name")
                issue["layer"] = item.get("layer")
                data_evidence_contract_issues.append(issue)
        hard_evidence_issues = [
            issue for issue in data_evidence_contract_issues if issue.get("severity") == "hard_block"
        ]
        degraded_evidence_issues = [
            issue for issue in data_evidence_contract_issues if issue.get("severity") == "degraded"
        ]
        audit_evidence_issues = [
            issue for issue in data_evidence_contract_issues if issue.get("severity") == "audit_warn"
        ]
        weighted_success = sum(coverage_factors.values())
        if future_violations:
            weighted_success = max(0.0, weighted_success - len(future_violations))
        if hard_evidence_issues:
            weighted_success = max(0.0, weighted_success - len(hard_evidence_issues))
        quality_issues = []
        for item in successful_items:
            quality_issues.extend(self._source_disagreement_issues(item))
        blocking_quality_issues = [issue for issue in quality_issues if issue.get("blocks_publish")]
        if quality_issues:
            weighted_success = max(0.0, weighted_success - 0.5 * len(quality_issues))
        if blocking_quality_issues:
            weighted_success = max(0.0, weighted_success - len(blocking_quality_issues))
        confidence = round((weighted_success / total) * 100, 1) if total else 0.0
        blocking_reasons = []
        if future_violations:
            examples = [f"{name}: {', '.join(values[:2])}" for name, values in list(future_violations.items())[:3]]
            blocking_reasons.append(
                "future_data_after_backtest_date: " + "；".join(examples)
            )
        if blocking_quality_issues:
            examples = []
            for issue in blocking_quality_issues[:3]:
                examples.append(
                    f"{issue.get('indicator')}: {issue.get('metric')} component={issue.get('component_value')} "
                    f"reference={issue.get('reference_median')} diff={issue.get('relative_diff_pct')}%"
                )
            blocking_reasons.append("valuation_source_disagreement: " + "；".join(examples))
        if hard_evidence_issues:
            examples = [
                f"{issue.get('function_id')}: {issue.get('code')}"
                for issue in hard_evidence_issues[:5]
            ]
            blocking_reasons.append("data_evidence_contract_hard_block: " + "；".join(examples))

        failed_metrics = [
            item.get("metric_name") or item.get("function_id")
            for item in indicators
            if item.get("error") and not self._is_skipped(item)
        ]
        notes = []
        if failed_metrics:
            notes.append(
                f"{len(failed_metrics)} 个指标采集失败，示例: {', '.join(str(name) for name in failed_metrics[:3])}"
            )
        if unavailable:
            notes.append(f"{unavailable} 个指标因回测前瞻风险被跳过。")
        if no_data_items:
            examples = []
            for item in no_data_items[:3]:
                name = item.get("metric_name") or item.get("function_id")
                examples.append(f"{name}: {self._no_data_reason(item)}")
            notes.append(
                f"{len(no_data_items)} 个指标明确返回 {NO_DATA_AVAILABLE}，只能作为数据边界使用，示例: "
                + "；".join(str(item) for item in examples)
            )
        partial = [
            item.get("metric_name") or item.get("function_id")
            for item in successful_items
            if coverage_factors.get(id(item), 1.0) < 1.0
        ]
        if partial:
            notes.append(f"{len(partial)} 个指标覆盖率不足，示例: {', '.join(str(name) for name in partial[:3])}")
        if future_violations:
            examples = [f"{name}: {', '.join(values[:2])}" for name, values in list(future_violations.items())[:3]]
            notes.append(f"{len(future_violations)} 个指标存在晚于回测日的数据日期，示例: {'；'.join(examples)}")
        if quality_issues:
            examples = []
            for issue in quality_issues[:3]:
                examples.append(
                    f"{issue.get('indicator')} {issue.get('metric')} component={issue.get('component_value')}, "
                    f"ref={issue.get('reference_median')}, diff={issue.get('relative_diff_pct')}%"
                )
            notes.append(f"{len(quality_issues)} 个估值源严重冲突，示例: {'；'.join(examples)}")
        if hard_evidence_issues:
            examples = [
                f"{issue.get('function_id')}: {issue.get('code')}"
                for issue in hard_evidence_issues[:3]
            ]
            notes.append(f"{len(hard_evidence_issues)} 个数据证据合约硬阻断，示例: {'；'.join(examples)}")
        if degraded_evidence_issues:
            examples = [
                f"{issue.get('function_id')}: {issue.get('code')}"
                for issue in degraded_evidence_issues[:3]
            ]
            notes.append(f"{len(degraded_evidence_issues)} 个指标数据证据元信息不完整，已降级但不阻断，示例: {'；'.join(examples)}")
        if audit_evidence_issues:
            notes.append(f"{len(audit_evidence_issues)} 条数据证据审计提示进入审计区，不单独阻断发布。")
        if not future_violations and not quality_issues and not failed_metrics and not unavailable and not no_data_items and not partial:
            notes.append("所有采集指标均返回有效值。")
        strict_backtest_invariants = self._strict_backtest_invariants(data_json)
        declared_limitations = strict_backtest_invariants.get("declared_limitations", []) if strict_backtest_invariants else []
        if backtest_date and declared_limitations:
            limitation_labels = [
                str(item.get("invariant_id"))
                for item in declared_limitations
                if isinstance(item, dict) and item.get("invariant_id")
            ]
            notes.append(
                "严格回测限制已明示: "
                + ", ".join(limitation_labels[:4])
                + "；这些不是硬未来数据污染，但需要在发布审计中保留。"
            )
        runtime_diagnostics = data_json.get("runtime_diagnostics") if isinstance(data_json, dict) else {}
        yf_diag = runtime_diagnostics.get("yfinance") if isinstance(runtime_diagnostics, dict) else {}
        yf_status = yf_diag.get("by_status", {}) if isinstance(yf_diag, dict) else {}
        yf_failures = yf_diag.get("by_failure_type", {}) if isinstance(yf_diag, dict) else {}
        yf_backoff = yf_diag.get("total_backoff_seconds", 0) if isinstance(yf_diag, dict) else 0
        yf_retry_count = int(yf_status.get("retry_scheduled", 0) or 0) if isinstance(yf_status, dict) else 0
        yf_fallback_count = int(yf_status.get("cache_fallback", 0) or 0) if isinstance(yf_status, dict) else 0
        yf_failed_count = int(yf_status.get("failed", 0) or 0) if isinstance(yf_status, dict) else 0
        if yf_retry_count or yf_fallback_count or yf_failed_count:
            failure_summary = ", ".join(f"{key}={value}" for key, value in sorted(yf_failures.items())) or "unknown"
            notes.append(
                "yfinance 运行诊断: "
                f"retry={yf_retry_count}, cache_fallback={yf_fallback_count}, failed={yf_failed_count}, "
                f"backoff_seconds={yf_backoff}, failure_types={failure_summary}"
            )
        if confidence < 90:
            notes.append("数据完整性偏低，最终结论需要更保守。")

        # Layer-level breakdown
        layer_stats: Dict[str, Dict[str, int]] = {}
        for item in indicators:
            layer = str(item.get("layer", "unknown"))
            if layer not in layer_stats:
                layer_stats[layer] = {"total": 0, "success": 0}
            layer_stats[layer]["total"] += 1
            if not item.get("error") and not self._is_skipped(item) and self._has_value(item):
                layer_stats[layer]["success"] += 1

        # ThirdPartyChecks availability (cross-check health for L4)
        tp_total = 0
        tp_available = 0
        for item in indicators:
            raw = item.get("raw_data") if isinstance(item.get("raw_data"), dict) else {}
            value = raw.get("value") if isinstance(raw.get("value"), dict) else {}
            checks = value.get("ThirdPartyChecks")
            if isinstance(checks, list):
                tp_total += len(checks)
                tp_available += sum(1 for c in checks if isinstance(c, dict) and c.get("availability") == "available")

        report = {
            "confidence_percent": confidence,
            "notes": "；".join(notes),
            "blocked": bool(blocking_reasons),
            "unpublishable": bool(blocking_reasons),
            "publish_status": "blocked" if blocking_reasons else "publishable",
            "blocking_reasons": blocking_reasons,
            "quality_issues": quality_issues,
            "no_data_indicators": [
                {
                    "function_id": item.get("function_id"),
                    "metric_name": item.get("metric_name"),
                    "reason": self._no_data_reason(item),
                    "fallback_chain": self._fallback_chain(item),
                }
                for item in no_data_items
            ],
            "fallback_indicators": [
                {
                    "function_id": item.get("function_id"),
                    "metric_name": item.get("metric_name"),
                    "fallback_chain": self._fallback_chain(item),
                }
                for item in indicators
                if self._fallback_chain(item)
            ],
            "future_date_violations": future_violations,
            "data_evidence_contract_issues": data_evidence_contract_issues,
            "data_evidence_contract_summary": {
                "hard_block": len(hard_evidence_issues),
                "degraded": len(degraded_evidence_issues),
                "audit_warn": len(audit_evidence_issues),
            },
            "layer_breakdown": {
                layer: {
                    "total": stats["total"],
                    "success": stats["success"],
                    "confidence": round((stats["success"] / stats["total"]) * 100, 1) if stats["total"] else 0.0,
                }
                for layer, stats in sorted(layer_stats.items())
            },
            "third_party_checks": {
                "total": tp_total,
                "available": tp_available,
                "confidence": round((tp_available / tp_total) * 100, 1) if tp_total else 0.0,
            },
            "runtime_diagnostics": {
                "yfinance": {
                    "by_status": yf_status if isinstance(yf_status, dict) else {},
                    "by_failure_type": yf_failures if isinstance(yf_failures, dict) else {},
                    "total_backoff_seconds": yf_backoff,
                }
            },
            "strict_backtest_invariants": strict_backtest_invariants,
        }
        logging.info("Data integrity: %.1f%%", confidence)
        return report
