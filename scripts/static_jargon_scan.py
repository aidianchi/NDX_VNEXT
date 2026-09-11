#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""静态黑话全量扫描器（T72 语料改造用）

目的
----
把「所有会进入 agent 上下文的静态文本」找齐，并在其中穷尽提取疑似黑话。

为什么需要它
------------
16 号清单只扫了 `src/agent_analysis/prompts/`，那只是静态源的一小部分。实际每个站的
prompt 由 8 段拼成，静态来源至少 11 组（见 SOURCES），合计约 62 万字符。本脚本全量收进。

三个提取器（都不判意思，只做机械筛选）
--------------------------------------
  A · 比喻字符命中词   —— 这套黑话的共同特征是「从物理世界借词」：
        桥 / 垫 / 墙 / 锚 / 水位 / 闸门 / 承重 / 地心引力 / 独木桥 / 温度 / 张力。
        凡是同时出现在静态源里的中文词，只要命中这些字符，就是高危候选。
        这是最强的信号，因为「借物理词当术语」正是黑话的成因本身。
  B · 引号词           —— 作者自己在标记「这是个词」。
  C · 范文差集         —— 静态源 >= N 次、14 号范文正文 0 次、且真的漏进了报告。
        这一档靠停用词表压掉「必须 / 不得 / 是否」这类指令用词。

输出组织
--------
  报告侧 = 已经漏到老板眼前的（必改）
  静态侧 = 还在源里潜伏的（随时会漏）
  两边取交集 = 罪证链（源 → 报告）

用法
----
  python3 scripts/static_jargon_scan.py
  python3 scripts/static_jargon_scan.py --json /tmp/jargon.json
"""

from __future__ import annotations

import argparse
import ast
import glob
import html as H
import json
import os
import re
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CJK = r"\u4e00-\u9fff"
FANWEN = "investigation_reports/20260902_研报语言第一性/14_目标范文_基于20260906run.md"

# 借自物理/日常世界的字符 —— 黑话的成因特征。
# 注意：必须收窄到「几乎不会出现在正常金融行文里」的字。
# 早先版本把 度 / 量 / 数 / 力 / 率 / 线 / 道 / 门 / 口 也放进来，
# 结果把「数据 / 趋势 / 指标 / 利率 / 通道」全捞进来了，那是误报。
METAPHOR_CHARS = set(
    "桥垫墙锚闸坝伞盾梯牢笼枷锤钉钻针镜炉帆舵桨藤蔓垛堤堰壕阀匙栓罐桶篮筐绳索桩楔铆焊铸锻锯刨槽"
)

# 这些是「物理比喻多字词」，单字命中不到，需单独列出
METAPHOR_PHRASES = (
    "水位", "水位计", "承重", "独木", "地心", "重力", "张力", "姿态",
    "读数", "摩擦", "惯性", "闸门", "垫子", "垫片", "温度计",
    "独木桥", "承重墙", "零垫子", "兑现桥", "地心引力",
)

# 老板 2026-09-11 裁定的「保留词」——一律不参与「疑似黑话」判定，别再删。
#   · 护城河：投资界通语（moat，巴菲特语汇），不是比喻私词。
#   · 矛盾  ：系统核心概念名兼字段名（principal_contradiction / secondary_contradictions），
#             与 typed_conflicts（冲突）是两个层级——冲突是全部冲突，矛盾是选出来的主导项。
#             「毛式辩证法术语」这个旧判定已撤回。
#   · 安全垫 / 兑现 / 反证 / 判读：业内通语，报告里密度不低于范文。
# 判决依据：investigation_reports/20260902_研报语言第一性/17_静态黑话全量清单_完整版.md
#           与同目录 18 号文档第四节。
KEEP_WORDS = (
    "护城河", "矛盾", "安全垫", "兑现", "反证", "判读",
    "主要矛盾", "次要矛盾",
)

STOPWORDS = {
    "必须","不得","是否","可以","需要","用于","作为","直接","真正","至少","同一","并且",
    "但是","因为","所以","如果","这些","那些","一个","中的","用的","属于","正式","重要",
    "避免","包含","结果","内容","其他","外部","发现","表明","程度","部分","形成","主要",
    "数据","信息","方式","情况","时间","问题","工作","方法","过程","才能","应当","应该",
    "可能","不能","不会","已经","正在","通过","根据","按照","对于","关于","由于","除了",
    "而且","或者","以及","等等","例如","比如","包括","其中","之间","之后","之前","同一",
    "上下","下文","上文","上面","下面","前面","后面","之后","一定","非常","十分","比较",
    "更加","最为","更为","有些","一些","每个","每个","各种","各类","若干","许多","多少",
    "输出","输入","字段","代码","校验","日期","文件","阶段","规则","机制","层级","路径",
    "材料","字符","序号","每条","原文","最终","返回","使用","获取","观察","保留","候选",
    "降级","版本","默认","参数","函数","接口","结构","格式","错误","状态","配置","检查",
    "报告","系统","分析","研究","判断","结论","证据","指标","数值","文本","逻辑","模型",
}

SOURCES: dict[str, list[str]] = {
    "1_系统纪律": ["src/agent_analysis/prompts/system_constraints.md"],
    "2_站提示词": ["src/agent_analysis/prompts"],
    "3_深度研究canon": ["src/agent_analysis/deep_research_canon.py"],
    "4_canon文档": ["RESEARCH_CANON.md"],
    "5_少样本示例": [
        "src/prompt_examples.py",
        "src/reasoning_examples.py",
        "src/agent_analysis/few_shot.py",
    ],
    "6_契约字段规格": ["src/agent_analysis/contracts.py"],
    "7_编排层硬编码": ["src/agent_analysis/orchestrator.py"],
    "8_工具函数文本": [
        "src/tools_L1.py","src/tools_L2.py","src/tools_L3.py",
        "src/tools_L4.py","src/tools_L5.py",
    ],
    "9_持续检查文本": [
        "src/agent_analysis/persistent_checks_a.py",
        "src/agent_analysis/persistent_checks_b.py",
    ],
    "10_事件研究": ["src/event_research"],
    "11_其他agent文本": [
        "src/agent_analysis/packet_builder.py",
        "src/agent_analysis/context_spread.py",
    ],
}


def read_text(path: str) -> str:
    try:
        return open(path, encoding="utf-8", errors="ignore").read()
    except OSError:
        return ""


def py_string_literals(path: str) -> str:
    src = read_text(path)
    if not src:
        return ""
    out: list[str] = []
    try:
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                out.append(node.value)
    except SyntaxError:
        pass
    out.extend(l.strip() for l in src.split("\n") if l.strip().startswith("#"))
    return "\n".join(out)


def collect_files(spec: list[str]) -> list[str]:
    files: list[str] = []
    for item in spec:
        p = os.path.join(ROOT, item)
        if os.path.isdir(p):
            for pat in ("*.md", "*.py", "*.json", "*.txt"):
                files.extend(glob.glob(os.path.join(p, pat)))
        elif os.path.isfile(p):
            files.append(p)
    return sorted(set(files))


def load_corpus() -> tuple[dict[str, str], dict[str, list[str]]]:
    corpus, filemap = {}, {}
    for group, spec in SOURCES.items():
        files = collect_files(spec)
        buf = [
            py_string_literals(f) if f.endswith(".py") else read_text(f) for f in files
        ]
        corpus[group] = "\n".join(buf)
        filemap[group] = files
    return corpus, filemap


def load_fanwen_body() -> str:
    text = read_text(os.path.join(ROOT, FANWEN))
    idx = text.find("# 范文说明")
    return text[:idx] if idx > 0 else text


def load_report(run_id: str) -> tuple[str, str]:
    """按 run 前缀对齐报告，避免字母序取到旧文件。"""
    stamp = run_id.split("_")[0]          # 20260906
    short = stamp[4:] + "_" + run_id.split("_")[1][:4]   # 0906_1059
    cands = sorted(glob.glob(os.path.join(ROOT, f"output/reports/vnext_brief_{stamp}*.html")))
    if not cands:
        cands = sorted(glob.glob(os.path.join(ROOT, "output/reports/vnext_brief_*.html")))
    path = next((c for c in cands if short in os.path.basename(c)), cands[-1] if cands else "")
    if not path:
        return "", ""
    raw = read_text(path)
    raw = re.sub(r"<script[\s\S]*?</script>|<style[\s\S]*?</style>", "", raw)
    text = H.unescape(re.sub(r"<[^>]+>", "\n", raw))
    text = "\n".join(l.strip() for l in text.split("\n") if l.strip())
    return path, text


def maxterms(text: str, lo: int, hi: int, min_count: int, keep) -> Counter:
    """极大中文词提取：被更长同频词包含的短词丢弃。keep 为候选过滤谓词。"""
    counts = {n: Counter(re.findall(rf"[{CJK}]{{{n}}}", text)) for n in range(lo, hi + 1)}
    kept: Counter = Counter()
    for n in range(hi, lo - 1, -1):
        for term, cnt in counts[n].items():
            if cnt < min_count or not keep(term):
                continue
            if any(
                sc == cnt and term in sup
                for longer in range(n + 1, hi + 1)
                for sup, sc in counts[longer].items()
            ):
                continue
            kept[term] = cnt
    return kept


def quoted_terms(text: str) -> Counter:
    out: Counter = Counter()
    for pat in (rf"[「『]([{CJK}\w]{{2,8}})[」』]", rf"[“\"]([{CJK}\w]{{2,8}})[”\"]]"):
        for m in re.finditer(pat, text):
            out[m.group(1)] += 1
    return out


def group_of(term: str, corpus: dict[str, str]) -> list[str]:
    return [g for g, t in corpus.items() if term in t]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default=None)
    ap.add_argument("--json", default=None)
    ap.add_argument("--metaphor", action="store_true", help="只输出比喻字符命中词（紧凑）")
    args = ap.parse_args()

    runs = sorted(glob.glob(os.path.join(ROOT, "output/analysis/vnext/2026*")))
    run_id = args.run or os.path.basename(runs[-1])

    corpus, filemap = load_corpus()
    fanwen = load_fanwen_body()
    report_path, report = load_report(run_id)

    print(f"基准 run : {run_id}")
    print(f"报告     : {report_path}（{len(report)} 字纯文本）")
    print(f"范文正文 : {len(fanwen)} 字\n")

    print(f"{'静态源分组':<18}{'文件':>5}{'字符':>9}")
    print("-" * 34)
    for g, t in corpus.items():
        print(f"{g:<18}{len(filemap[g]):>5}{len(t):>9}")
    print("-" * 34)
    print(f"{'合计':<18}{sum(len(v) for v in filemap.values()):>5}{sum(len(t) for t in corpus.values()):>9}")

    static_all = "\n".join(corpus.values())

    def has_metaphor(term: str) -> bool:
        if term in KEEP_WORDS:
            return False
        return any(ch in METAPHOR_CHARS for ch in term) or term in METAPHOR_PHRASES

    print("\n\n" + "=" * 62)
    print("A · 比喻词（借物理世界当术语 —— 黑话的成因特征）")
    print("=" * 62)

    s_meta = maxterms(static_all, 2, 5, 2, has_metaphor)
    r_meta = maxterms(report, 2, 5, 1, has_metaphor)
    for ph in METAPHOR_PHRASES:
        if ph in KEEP_WORDS:
            continue
        if ph in static_all:
            s_meta[ph] = static_all.count(ph)
        if ph in report:
            r_meta[ph] = report.count(ph)

    print(f"\n-- A1 潜伏在静态源里的比喻词（{len(s_meta)} 个）--")
    for t, c in sorted(s_meta.items(), key=lambda kv: (-kv[1], kv[0])):
        mark = "→已漏到报告" if t in report else ""
        print(f"  静态{c:>4}  报告{report.count(t):>3}  {t:<8}{mark:<12} {'/'.join(group_of(t, corpus))}")

    only_report = [t for t in r_meta if t not in s_meta]
    print(f"\n-- A2 只在报告里、静态源查不到（{len(only_report)} 个 —— 模型现场造词）--")
    for t in sorted(only_report, key=lambda x: -r_meta[x]):
        print(f"  报告{r_meta[t]:>4} 次   {t}")

    print("\n\n" + "=" * 62)
    print("B1 · 静态源里的引号词（作者自标「这是个词」）")
    print("=" * 62)
    qt = quoted_terms(static_all)
    for t, c in qt.most_common(60):
        tag = f"   →报告中 {report.count(t)} 次" if t in report else ""
        print(f"  {c:>4}  「{t}」{tag}")

    print("\n\n" + "=" * 62)
    print("B2 · 报告里的引号词（模型自标「这是我造的词」）")
    print("=" * 62)
    qr = quoted_terms(report)
    for t, c in qr.most_common(80):
        src = "静态源有" if t in static_all else "静态源无"
        print(f"  {c:>4}  「{t}」   {src}")

    print("\n\n" + "=" * 62)
    print("C · 范文差集（静态 >=3 / 范文 0 / 已漏进报告）")
    print("=" * 62)
    def is_candidate(term: str) -> bool:
        return term not in STOPWORDS and term not in KEEP_WORDS
    terms = maxterms(static_all, 2, 5, 3, is_candidate)
    leaked = sorted(
        [(t, c) for t, c in terms.items() if t not in fanwen and t in report],
        key=lambda kv: (-kv[1], kv[0]),
    )
    print(f"\n共 {len(leaked)} 个（前 120）\n")
    for t, c in leaked[:120]:
        print(f"  静态{c:>4}  报告{report.count(t):>3}  {t:<10} {'/'.join(group_of(t, corpus))}")

    if args.json:
        payload = {
            "run": run_id,
            "report": report_path,
            "sources": {g: {"files": filemap[g], "chars": len(corpus[g])} for g in corpus},
            "metaphor_static": [
                {"term": t, "static": c, "report": report.count(t), "groups": group_of(t, corpus)}
                for t, c in sorted(s_meta.items(), key=lambda kv: (-kv[1], kv[0]))
            ],
            "metaphor_report_only": [
                {"term": t, "report": c} for t, c in r_meta.items() if t not in s_meta
            ],
            "quoted": [{"term": t, "count": c, "report": report.count(t)} for t, c in qt.most_common(300)],
            "fanwen_diff_leaked": [
                {"term": t, "static": c, "report": report.count(t), "groups": group_of(t, corpus)}
                for t, c in leaked
            ],
        }
        with open(os.path.join(ROOT, args.json), "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, indent=1)
        print(f"\n结果已写入 {args.json}")


if __name__ == "__main__":
    main()
