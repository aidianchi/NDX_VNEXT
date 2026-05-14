from __future__ import annotations

import logging
from typing import Any, Dict


class DataIntegrity:
    """Generate a compact reliability report from collector output."""

    def run(self, data_json: Dict[str, Any]) -> Dict[str, Any]:
        indicators = data_json.get("indicators", [])
        total = len(indicators)
        successful = sum(1 for item in indicators if not item.get("error"))
        confidence = round((successful / total) * 100, 1) if total else 0.0

        failed_metrics = [item.get("metric_name") or item.get("function_id") for item in indicators if item.get("error")]
        notes = []
        if failed_metrics:
            notes.append(
                f"{len(failed_metrics)} 个指标采集失败，示例: {', '.join(str(name) for name in failed_metrics[:3])}"
            )
        else:
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
            if not item.get("error"):
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
