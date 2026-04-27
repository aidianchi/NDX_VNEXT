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

        report = {
            "confidence_percent": confidence,
            "notes": "；".join(notes),
        }
        logging.info("Data integrity: %.1f%%", confidence)
        return report
