#!/usr/bin/env python3
"""人话度统计复现脚本（2026-09-02）。

对 vnext 研报 HTML 做同口径文本统计：去 <script>/<style> 与标签后按句号切分，
统计平均句长、长句占比、内部黑话密度。用法：

    python3 03_repro_人话度统计.py [html文件 ...]

不带参数时统计 02 号文档表格里的四份默认样本。
"""
import re
import sys
import html as htmllib

DEFAULTS = [
    "output/reports/vnext_brief_20260519_1849_20250409_0000.html",
    "output/reports/vnext_brief_20260624_2021.html",
    "output/reports/ndx_report_v9_20260728_120014.html",
    "output/reports/vnext_brief_20260831_2138.html",
]

JARGON = (
    r"supplier_reported_counts|pending_validation|supporting_only"
    r"|supplier_lookback|self_archive"
    r"|L[1-5]·|L[1-5]\.[a-z_]+|TC_0\d|SC_[a-z_]+"
    r"|hyp_(base|counter)_[0-9a-f]+|事件卡·[0-9a-f]+"
)


def extract_text(path: str) -> str:
    """去脚本/样式/标签后折叠空白，与 02 号文档表格口径一致。

    注意：05-19 长文版正文区嵌有数据表格，全文件口径会把句长抬到 200 字以上；
    要复现 02 号表格里 5 月版"114 字"的纯正文口径，需只取其判断~冲突章节的行区间。
    """
    s = open(path, encoding="utf-8").read()
    s = re.sub(r"<script[\s\S]*?</script>", "", s)
    s = re.sub(r"<style[\s\S]*?</style>", "", s)
    txt = re.sub(r"<[^>]+>", "\n", s)
    txt = htmllib.unescape(txt)
    lines = [ln.strip() for ln in txt.split("\n") if ln.strip()]
    return "\n".join(lines)


def metrics(txt: str) -> dict:
    sents = [x for x in re.split(r"[。！？]", txt) if len(x.strip()) > 4]
    lens = [len(x) for x in sents]
    n = max(len(lens), 1)
    return {
        "chars": len(txt),
        "sentences": len(lens),
        "avg_len": round(sum(lens) / n),
        "long_ratio": f"{sum(1 for x in lens if x >= 80) / n:.0%}",
        "jargon_per_kilo": round(len(re.findall(JARGON, txt)) / len(txt) * 1000, 1),
    }


def main(paths: list[str]) -> None:
    for p in paths:
        m = metrics(extract_text(p))
        print(f"== {p} ==")
        for k, v in m.items():
            print(f"  {k}: {v}")


if __name__ == "__main__":
    main(sys.argv[1:] or DEFAULTS)
