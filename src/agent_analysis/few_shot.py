from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any, Dict, Iterable, List

logger = logging.getLogger(__name__)

LAYER_EXAMPLE_FALLBACKS = {
    "L1": ["get_10y_real_rate", "get_net_liquidity_momentum", "get_10y2y_spread_bp"],
    "L2": ["get_hy_oas_bp", "get_cnn_fear_greed_index", "get_xly_xlp_ratio"],
    "L3": ["get_qqq_qqew_ratio"],
    "L4": ["get_equity_risk_premium"],
    "L5": ["get_adx_qqq"],
}


@lru_cache(maxsize=1)
def _load_prompt_examples() -> Dict[str, List[Dict[str, Any]]]:
    try:
        try:
            from prompt_examples import PROMPT_EXAMPLES
        except ImportError:
            from ..prompt_examples import PROMPT_EXAMPLES  # type: ignore
    except Exception as exc:
        logger.warning("Failed to load prompt examples: %s", exc)
        return {}
    return {
        key: value
        for key, value in PROMPT_EXAMPLES.items()
        if isinstance(value, list)
    }


def _format_example(function_id: str, example: Dict[str, Any]) -> str:
    input_payload = example.get("input", {})
    if isinstance(input_payload, dict) and input_payload.get("comment"):
        input_text = input_payload["comment"]
    else:
        input_text = json.dumps(input_payload, ensure_ascii=False, default=str)
    return (
        f"### Example: {function_id}\n"
        f"CONTEXT: {example.get('context', '')}\n"
        f"INPUT: {input_text}\n"
        f"REASONING: {example.get('reasoning', '')}\n"
        f"CORRECT OUTPUT: {example.get('output_narrative', '')}"
    )


def _ordered_unique(items: Iterable[str]) -> List[str]:
    seen = set()
    ordered: List[str] = []
    for item in items:
        if item and item not in seen:
            ordered.append(item)
            seen.add(item)
    return ordered


def build_layer_few_shot_prompt(
    *,
    layer: str,
    layer_raw_data: Dict[str, Any],
    max_total_examples: int = 4,
) -> str:
    """Build a compact, layer-local 4C few-shot block.

    The examples are selected by function_id from the current layer first.
    This keeps examples useful while avoiding cross-layer prompt pollution.
    """
    examples_by_function = _load_prompt_examples()
    if not examples_by_function:
        return ""

    present_function_ids = list(layer_raw_data.keys()) if isinstance(layer_raw_data, dict) else []
    candidate_ids = _ordered_unique(
        [
            *(function_id for function_id in present_function_ids if function_id in examples_by_function),
            *(function_id for function_id in LAYER_EXAMPLE_FALLBACKS.get(layer, []) if function_id in examples_by_function),
        ]
    )
    selected = candidate_ids[:max_total_examples]
    if not selected:
        return ""

    rendered_examples = []
    for function_id in selected:
        function_examples = examples_by_function.get(function_id) or []
        if function_examples:
            rendered_examples.append(_format_example(function_id, function_examples[0]))

    if not rendered_examples:
        return ""

    return (
        "## Layer-Local 4C Few-Shot Examples\n"
        "这些范例只用于本层认知校准：语境化、精炼化、典范化、因果化。"
        "不要复制具体数值，只学习推理结构与叙事密度。\n\n"
        + "\n\n".join(rendered_examples)
    )
