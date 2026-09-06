#!/usr/bin/env python3
"""06 期诊断实测脚本：对指定 vnext brief HTML 统计人话度形状指标。

只量形状，不判意思（符合宪法"闸门不判意思"）；输出供体检参考，不是闸门。

用法：
    python3 06_repro_重复与泄漏实测.py [brief_html路径]

默认路径：output/reports/vnext_brief_20260902_2336_70202609_0000.html
"""
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

DEFAULT_HTML = "output/reports/vnext_brief_20260902_2336_70202609_0000.html"

FRAMEWORK_WORDS = [
    "约束端", "吸收端", "补偿端", "折现率复合体", "口径", "对质", "裁决",
    "锚", "主线", "反方", "姿态", "赔率", "分寸", "计票", "悬案", "传导",
]
KEY_NUMBERS = ["2.44", "99.6", "4.75", "99.3", "8.97", "707.64", "+3.93%",
               "84%", "702.7", "718", "-1.42", "45.75", "1.33", "16.7", "57bp"]
MACHINE_PATTERNS = {
    "snake_case 字段名": r"\b[a-z]+_[a-z0-9_]+\b",
    "event:哈希": r"event:[0-9a-f]{6,}",
}
MACHINE_TOKENS = ["payload", "row_count", "effective_date", "受控调查",
                  "缺少来源链接", "claim schema", "Run Review"]
EVENT_KEYWORDS = ["伯克希尔", "378亿", "609亿", "950亿", "爱荷华", "Goolsbee", "129亿"]


class _TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self._skip += 1
        if tag in ("h1", "h2", "h3", "h4"):
            self.parts.append("\n\n")
        elif tag in ("p", "li", "tr", "div", "section", "summary", "details"):
            self.parts.append("\n")
        elif tag in ("td", "th"):
            self.parts.append(" | ")

    def handle_endtag(self, tag):
        if tag in ("script", "style") and self._skip > 0:
            self._skip -= 1

    def handle_data(self, data):
        if self._skip == 0:
            self.parts.append(data)


def extract_text(html: str) -> str:
    ex = _TextExtractor()
    ex.feed(html)
    text = "".join(ex.parts)
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text)


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_HTML)
    text = extract_text(path.read_text(encoding="utf-8"))

    gate_start = text.find("对纳指的判断是")
    sec01 = text.find("01 · 正方主论证")
    verdict = text[gate_start:sec01] if 0 <= gate_start < sec01 else ""

    print(f"样本：{path}")
    print(f"全文抽文本 {len(text)} 字符\n")

    print("== A. 门脸判决正文句子形状 ==")
    sents = [s.strip() for s in re.split(r"[。；]", verdict) if len(s.strip()) > 5]
    lens = [len(s) for s in sents]
    if lens:
        print(f"句数={len(lens)}  平均={sum(lens)/len(lens):.0f}字  "
              f"中位={sorted(lens)[len(lens)//2]}字  最长={max(lens)}字  "
              f">80字占比={sum(1 for x in lens if x > 80)/len(lens)*100:.0f}%")

    print("\n== B. 判决区框架词密度（次/千字） ==")
    hits = {w: verdict.count(w) for w in FRAMEWORK_WORDS}
    used = {w: n for w, n in hits.items() if n}
    total_hits = sum(used.values())
    if verdict:
        print(f"命中词：{'  '.join(f'{w}×{n}' for w, n in sorted(used.items(), key=lambda kv: -kv[1]))}")
        print(f"合计 {total_hits} 次 / {len(verdict)} 字 = {total_hits/len(verdict)*1000:.1f} 次/千字"
              f"（自家最佳样板 06-24 v1 基线 0.3）")

    print("\n== C. 关键数字全文重复次数 ==")
    print("  ".join(f"{n}×{text.count(n)}" for n in KEY_NUMBERS))

    print("\n== D. 机器 token / 内部语言泄漏（全文） ==")
    for name, pat in MACHINE_PATTERNS.items():
        print(f"{name}: {len(re.findall(pat, text))}")
    print("  ".join(f"{t}×{text.count(t)}" for t in MACHINE_TOKENS))

    print("\n== E. 事件链重复叙述次数 ==")
    print("  ".join(f"{k}×{text.count(k)}" for k in EVENT_KEYWORDS))

    print("\n说明：发言权/对质等卡片固定头与审计区词汇未剔除，读者默认可见面密度以 B 节（判决区）为准。")


if __name__ == "__main__":
    main()
