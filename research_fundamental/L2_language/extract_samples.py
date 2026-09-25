"""把取样的 brief HTML 转成纯文本，便于逐句审读。只读不写原文件。"""
import re
import sys
from html.parser import HTMLParser
from pathlib import Path

BLOCK = {"p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "tr",
         "section", "article", "details", "summary", "blockquote", "table", "br"}


class TextExtract(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("style", "script", "noscript"):
            self.skip += 1
        elif tag in BLOCK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("style", "script", "noscript") and self.skip:
            self.skip -= 1
        elif tag in BLOCK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def extract(src: Path, dst: Path):
    parser = TextExtract()
    parser.feed(src.read_text(encoding="utf-8", errors="replace"))
    text = "".join(parser.parts)
    lines = [re.sub(r"[ \t\u00a0]+", " ", ln).strip() for ln in text.split("\n")]
    out, blank = [], False
    for ln in lines:
        if not ln:
            if not blank:
                out.append("")
            blank = True
        else:
            out.append(ln)
            blank = False
    dst.write_text("\n".join(out), encoding="utf-8")
    print(f"{src.name}: {len(out)} 行 -> {dst}")


if __name__ == "__main__":
    base = Path("/Users/aidianchi/Desktop/ndx_mac/research_fundamental/L2_language/current_samples")
    for html in sorted(base.glob("vnext_brief_*.html")):
        extract(html, base / "extracted_text" / (html.stem + ".txt"))
