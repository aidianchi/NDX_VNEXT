#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把「同一份输入、不同版本终审产物」的门面首屏并排渲染成一张对照页。

为什么需要它
------------
门面（`_brief_facade_section`）是全部修复里最靠"读起来像不像研报"的一环，而
`vnext_reporter` 的正常出口是整本 5MB 报告——为了看一眼首屏去生成整本报告太重。
本脚本直接调 `_brief_facade_section`，把 run 产物与若干重放产物各渲染一份首屏，
套上 slate_v3 皮肤拼成单页，供人眼比对。

用法
----
    PYTHONPATH=$PWD .venv/bin/python scripts/render_facade_compare.py \
        --run-dir output/analysis/vnext/20260911_233648 \
        --variant "改前 · 原架构" \
        --variant "改后 · GLM=output/experiments/replay_20260912/glm-5.3-flash_final_adjudicator_attempt1_arch.parsed.json" \
        --variant "改后 · DeepSeek=output/experiments/replay_20260912/deepseek-flash_final_adjudicator_attempt1_arch.parsed.json" \
        --out output/experiments/replay_20260912/门面改前改后.html

`--variant` 只给标签 = 用 run 自带的 final_adjudication（即"改前"那一版）；
给 `标签=json路径` = 用该 JSON 顶替 final_adjudication（重放产物）。

注意：这是**版面预览**，不是验收。验收是"哪个字段被渲染、契约是否通过"，
由 tests/test_vnext_reporter.py 与本脚本打印的字段表负责。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from agent_analysis.vnext_reporter import STYLES_DIR, VNextReportGenerator  # noqa: E402

POINT_LEVEL_RE = re.compile(r"\d+\.\d+")


def load_variant(spec: str) -> tuple[str, Path | None]:
    """把 '标签=路径' 或 '标签' 解析成 (标签, 覆盖 JSON 路径或 None)。"""
    if "=" in spec:
        label, raw_path = spec.split("=", 1)
        path = Path(raw_path.strip())
        if not path.is_absolute():
            path = ROOT / path
        if not path.exists():
            raise SystemExit(f"变体 JSON 不存在：{path}")
        return label.strip(), path
    return spec.strip(), None


def main() -> int:
    ap = argparse.ArgumentParser(description="并排渲染门面首屏，供人眼比对。")
    ap.add_argument("--run-dir", required=True, help="基准 run 目录（提供版面骨架与除终审外的其余产物）")
    ap.add_argument("--variant", action="append", default=[],
                    help="变体：'标签' 用 run 自带终审；'标签=JSON路径' 用该 JSON 顶替终审。可重复。")
    ap.add_argument("--out", required=True, help="输出 HTML 路径")
    ap.add_argument("--style", default="slate_v3", help="皮肤文件（report_styles/<name>.css）")
    ap.add_argument("--title", default="门面首屏对照", help="页面标题")
    args = ap.parse_args()

    run_dir = Path(args.run_dir)
    if not run_dir.is_absolute():
        run_dir = ROOT / run_dir
    if not run_dir.exists():
        raise SystemExit(f"run 目录不存在：{run_dir}")

    reporter = VNextReportGenerator()
    artifacts = reporter._load_artifacts(run_dir)

    variants = args.variant or ["当前 run 实产"]
    rendered: list[tuple[str, str, dict]] = []
    for spec in variants:
        label, override = load_variant(spec)
        arts = artifacts
        final = artifacts.get("final_adjudication") or {}
        if override is not None:
            final = json.loads(override.read_text(encoding="utf-8"))
            arts = dict(artifacts)
            arts["final_adjudication"] = final
        rendered.append((label, reporter._brief_facade_section(run_dir, arts), final))

    css_path = STYLES_DIR / f"{args.style}.css"
    if not css_path.exists():
        raise SystemExit(f"皮肤不存在：{css_path}")
    css = css_path.read_text(encoding="utf-8")

    parts = [
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">',
        f"<title>{args.title}</title><style>",
        css,
        "\n.fc-band{display:flex;align-items:center;gap:10px;margin:34px 0 10px;"
        "font-family:var(--sans);font-size:13px;letter-spacing:.14em;color:var(--accent);}",
        '\n.fc-band::after{content:"";flex:1;height:1px;background:var(--rule);}',
        "\n.fc-table{width:min(860px,calc(100% - 32px));margin:26px auto 0;"
        "font-family:var(--sans);font-size:12.5px;border-collapse:collapse;}",
        "\n.fc-table th,.fc-table td{border-bottom:1px solid var(--rule);padding:6px 10px;text-align:left;}",
        "\n.fc-table th{color:var(--ink-muted);font-weight:400;}\n</style></head>",
        '<body class="template-brief style-slate_v3 style-b style-b-light micro-1">',
    ]
    for label, block, _ in rendered:
        parts.append('<div class="shell">')
        parts.append(f'<div class="fc-band">{label}</div>')
        parts.append(block)
        parts.append("</div>")
    parts.append("</body></html>")

    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = ROOT / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(parts), encoding="utf-8")

    # 字段表：版面对照之外，把"哪个字段被渲染"也摊开（这才是可复核的部分）
    print(f"对照页：{out_path}（{out_path.stat().st_size} 字节）")
    print()
    print(f"{'变体':24s} {'标题字数':>8s} {'含点位':>6s} {'正文段数':>8s}  标题")
    for label, _, final in rendered:
        reader = (final.get("reader_final") or {})
        head = str(reader.get("headline") or "")
        verdict = str(final.get("reasoned_verdict") or "")
        paras = [s for s in re.split(r"\n\s*\n+", verdict) if s.strip()]
        print(
            f"{label:24s} {len(head) if head else '—':>8} "
            f"{('有' if POINT_LEVEL_RE.search(head) else '无'):>6s} "
            f"{len(paras) if paras else '—':>8}  {head or '（无 headline，走旧渲染）'}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
