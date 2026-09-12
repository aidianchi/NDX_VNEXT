#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""单站冻结重放：拿某次 run 落档的完整 prompt，原样喂给另一个模型。

为什么需要它
------------
"只变模型、其余全冻结"的单站实验，此前只能靠重跑全链（约 25 站、2 小时、
耗整轮额度）。但 `_run_stage` 已经把每一站的**完整 prompt** 落档在
`<run>/prompt_audit/<station>/attempt_N.prompt.txt`（含 System 与 User 两段）。
只要把 User 段原样取出、配上当前代码的 System 段，就能只花**一次调用**的钱
问到"换个模型，这一站会说什么"。

边界（必须知情）
----------------
- 这是**单站重放**，不是全链重跑：它复现的是"这一站收到同一份输入时的产出"。
  下游站若依赖本站输出（终审站没有下游 LLM 站），重放结果不会自动传导。
- 两侧对照的公平性前提是 System 段一致。脚本会逐字比对落档 System 与当前代码
  的 System，不一致时默认拒绝执行（--allow-system-drift 可放行并留痕）。
- `--strict-tools` 走 DeepSeek 专属的 beta strict function calling；不传则该站
  与 GLM 走同一套 json_object 协议（公平对照）。两者语义不同，报告里要写明。

用法
----
    PYTHONPATH=$PWD .venv/bin/python scripts/replay_station.py \
        --from-run output/analysis/vnext/20260911_233648 \
        --station final_adjudicator --attempt 1 \
        --model deepseek-flash \
        --out output/experiments/replay_20260912
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent_analysis.llm_engine import LLMEngine  # noqa: E402
from config import MODEL_CONFIGS  # noqa: E402

SYS_MARK = "## System Message"
USR_MARK = "## User Message"


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def split_prompt(text: str) -> tuple[str, str]:
    """拆出落档 prompt 的 System / User 两段。两个标记都必须存在。"""
    if SYS_MARK not in text or USR_MARK not in text:
        raise SystemExit(f"落档 prompt 缺少 '{SYS_MARK}' 或 '{USR_MARK}' 标记，无法拆分。")
    i = text.index(SYS_MARK) + len(SYS_MARK)
    j = text.index(USR_MARK)
    return text[i:j].strip(), text[j + len(USR_MARK):].strip()


def extract_json(raw: str | None) -> dict | None:
    """从模型原始响应里取出 JSON 对象。容忍 ```json 围栏与前后废话。"""
    if not raw:
        return None
    s = raw.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1]
        if s.rstrip().endswith("```"):
            s = s.rstrip()[:-3]
    try:
        return json.loads(s)
    except Exception:
        pass
    start, end = s.find("{"), s.rfind("}")
    if 0 <= start < end:
        try:
            return json.loads(s[start:end + 1])
        except Exception:
            return None
    return None


def main() -> int:
    ap = argparse.ArgumentParser(description="单站冻结重放：换模型，不换输入。")
    ap.add_argument("--from-run", required=True, help="基准 run 目录（读它的 prompt_audit）")
    ap.add_argument("--station", default="final_adjudicator", help="站点名（prompt_audit 下的目录名）")
    ap.add_argument("--attempt", type=int, default=1, help="用哪一次 attempt 的落档 prompt（默认 1 = 全量输入）")
    ap.add_argument("--model", required=True, help="模型 key（须在 MODEL_CONFIGS 里，如 deepseek-flash）")
    ap.add_argument("--out", required=True, help="输出目录")
    ap.add_argument("--strict-tools", action="store_true",
                    help="走 DeepSeek beta strict function calling（真实全链条件）；默认走 json_object（与 GLM 同协议）")
    ap.add_argument("--strict-schema", default="", help="strict tools 的 pydantic 模型名，如 FinalAdjudication")
    ap.add_argument("--dry-run", action="store_true", help="只打印规模与校验结果，不调模型")
    ap.add_argument("--allow-system-drift", action="store_true",
                    help="落档 System 与当前代码不一致时仍继续（会留痕）")
    args = ap.parse_args()

    run_dir = Path(args.from_run)
    if not run_dir.is_absolute():
        run_dir = ROOT / run_dir
    prompt_path = run_dir / "prompt_audit" / args.station / f"attempt_{args.attempt}.prompt.txt"
    if not prompt_path.exists():
        raise SystemExit(f"找不到落档 prompt：{prompt_path}")

    if args.model not in MODEL_CONFIGS:
        raise SystemExit(f"模型 key 未注册：{args.model}（已注册：{sorted(MODEL_CONFIGS)}）")
    cfg = MODEL_CONFIGS[args.model]

    dumped = prompt_path.read_text(encoding="utf-8")
    dump_sys, user_prompt = split_prompt(dumped)

    engine = LLMEngine.__new__(LLMEngine)
    current_sys = engine._load_system_constraints()
    sys_same = dump_sys == current_sys
    if not sys_same and not args.allow_system_drift:
        raise SystemExit(
            "落档 System 段与当前代码不一致，重放不再是'只变模型'。\n"
            f"  落档 sha={sha256_text(dump_sys)[:16]} len={len(dump_sys)}\n"
            f"  当前 sha={sha256_text(current_sys)[:16]} len={len(current_sys)}\n"
            "确认要跑请加 --allow-system-drift。"
        )

    print("=" * 72)
    print(f"单站重放  station={args.station}  attempt={args.attempt}")
    print(f"  来源       : {prompt_path.relative_to(ROOT) if prompt_path.is_relative_to(ROOT) else prompt_path}")
    print(f"  目标模型   : {args.model}  ->  远程 {cfg['model']}（{cfg['name']}）")
    print(f"  输出协议   : {'strict function calling (beta)' if args.strict_tools else 'json_object'}")
    print(f"  User 段    : {len(user_prompt)} 字符")
    print(f"  System 一致: {sys_same}{'' if sys_same else '  ← 已放行，留痕'}")
    print("=" * 72)

    if args.dry_run:
        print("dry-run：未调用模型。")
        return 0

    real_engine = LLMEngine(available_models=[args.model])
    strict_schema = None
    strict_name = None
    if args.strict_tools:
        if not args.strict_schema:
            raise SystemExit("--strict-tools 需要同时给 --strict-schema（pydantic 模型名）")
        from agent_analysis import contracts as _c  # noqa: F401
        import agent_analysis.contracts as contracts_mod
        from agent_analysis.llm_engine import sanitize_json_schema_for_strict_tool_calling
        model_cls = getattr(contracts_mod, args.strict_schema, None)
        if model_cls is None:
            raise SystemExit(f"contracts 里没有模型：{args.strict_schema}")
        # 必须走系统真实用的清洗：DeepSeek strict 模式不认 pydantic 生成的
        # `format: date-time`（会 400），清洗函数负责把它摘掉。
        strict_schema = sanitize_json_schema_for_strict_tool_calling(model_cls.model_json_schema())
        strict_name = f"emit_{args.station}"

    t0 = time.perf_counter()
    raw, usage = real_engine._call_ai(
        user_prompt,
        args.model,
        stage=f"replay.{args.station}",
        strict_tool_schema=strict_schema,
        strict_tool_name=strict_name,
    )
    elapsed = time.perf_counter() - t0
    if raw is None:
        print("❌ 模型未返回内容（看日志里的报错）。")
        return 2

    parsed = extract_json(raw)

    out_dir = Path(args.out)
    if not out_dir.is_absolute():
        out_dir = ROOT / out_dir
    tag = f"{args.model}_{args.station}_attempt{args.attempt}" + ("_strict" if args.strict_tools else "")
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / f"{tag}.response.raw.txt").write_text(raw, encoding="utf-8")
    if parsed is not None:
        (out_dir / f"{tag}.parsed.json").write_text(
            json.dumps(parsed, ensure_ascii=False, indent=2), encoding="utf-8")

    reader = (parsed or {}).get("reader_final") or (parsed or {}).get("reader_conclusion") or {}
    reader_field = "reader_final" if (parsed or {}).get("reader_final") else (
        "reader_conclusion" if (parsed or {}).get("reader_conclusion") else "")
    (out_dir / f"{tag}.meta.json").write_text(json.dumps({
        "replayed_at": datetime.now(timezone.utc).isoformat(),
        "source_run": str(run_dir),
        "source_prompt": str(prompt_path),
        "station": args.station,
        "attempt": args.attempt,
        "model_key": args.model,
        "remote_model": cfg["model"],
        "protocol": "strict_tools" if args.strict_tools else "json_object",
        "user_prompt_chars": len(user_prompt),
        "user_prompt_sha256": sha256_text(user_prompt),
        "system_matches_current": sys_same,
        "elapsed_sec": round(elapsed, 1),
        "usage": usage,
        "json_parsed": parsed is not None,
        "top_level_keys": sorted(parsed.keys()) if isinstance(parsed, dict) else None,
        "has_reader_final": bool(reader),
        "reader_field_used": reader_field,
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print()
    print(f"耗时 {elapsed:.0f} 秒 | JSON 解析：{'成功' if parsed else '失败'} | 用量：{usage}")
    print(f"产物：{(out_dir / tag).relative_to(ROOT) if (out_dir / tag).is_relative_to(ROOT) else out_dir / tag}.*")
    print()
    if reader:
        print("-" * 72)
        print(f"门面 {reader_field}.one_liner：")
        print(reader.get("one_liner") or "(空)")
        print()
        reasons = reader.get("three_reasons") or reader.get("reasons") or []
        for i, r in enumerate(reasons, 1):
            print(f"理由{i}. {r}")
        if not reasons:
            print(f"（该站门面无三条理由字段；可用键={sorted(reader.keys())}）")
        print("-" * 72)
    elif parsed:
        print(f"（响应里没有 reader_final；顶层键={sorted(parsed.keys())[:12]}）")
    else:
        print("（响应不是可解析的 JSON，原始响应见落盘文件）")
        print(raw[:800])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
