from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional


class DataIntegrity:
    """Generate a compact reliability report from collector output."""

    def _raw_data(self, item: Dict[str, Any]) -> Dict[str, Any]:
        return item.get("raw_data") if isinstance(item.get("raw_data"), dict) else {}

    def _is_skipped(self, item: Dict[str, Any]) -> bool:
        raw = self._raw_data(item)
        return bool(item.get("backtest_skipped") or raw.get("backtest_skipped"))

    def _has_value(self, item: Dict[str, Any]) -> bool:
        raw = self._raw_data(item)
        if "value" in raw:
            return raw.get("value") is not None
        return item.get("value") is not None or bool(raw)

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
        coverage_factors = {id(item): self._coverage_factor(item) for item in successful_items}
        future_violations = {
            item.get("metric_name") or item.get("function_id"): self._future_date_violations(item, backtest_date)
            for item in indicators
        }
        future_violations = {key: value for key, value in future_violations.items() if value}
        weighted_success = sum(coverage_factors.values())
        if future_violations:
            weighted_success = max(0.0, weighted_success - len(future_violations))
        confidence = round((weighted_success / total) * 100, 1) if total else 0.0
        blocking_reasons = []
        if future_violations:
            examples = [f"{name}: {', '.join(values[:2])}" for name, values in list(future_violations.items())[:3]]
            blocking_reasons.append(
                "future_data_after_backtest_date: " + "；".join(examples)
            )

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
        else:
            if not failed_metrics and not unavailable and not partial:
                notes.append("所有采集指标均返回有效值。")
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
            "future_date_violations": future_violations,
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
        }
        logging.info("Data integrity: %.1f%%", confidence)
        return report
