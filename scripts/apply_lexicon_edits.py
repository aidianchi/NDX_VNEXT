#!/usr/bin/env python3
"""T72 语料改造 · A 档落地脚本（19 号改动稿的执行器）。

用途
----
把「给 AI 看的静态文本」里那批自造比喻词换成真名 / 人话。**只换叫法，不动任何逻辑。**

用法
----
    python3 scripts/apply_lexicon_edits.py            # dry-run：只打印将要改什么
    python3 scripts/apply_lexicon_edits.py --apply    # 真改（改前请先确认 git 状态干净或已了解改动面）

边界（与 19 号改动稿一致，越界就是 bug）
--------------------------------------
1. 只动「进 prompt 的静态文本」：prompts/*.md、编排层字符串字面量、契约 description、
   few-shot 示例、RESEARCH_CANON.md。**代码逻辑一行不动。**
2. .py 文件跳过纯注释行与 docstring —— 它们不进 prompt，改了是浪费，且会污染审计。
3. 不改字段名 / 枚举值 / 机制名（T71 边界，2026-08 老板亲定）。
   保留词：矛盾 · 护城河 · 安全垫 · 兑现 · 反证 · 判读 · 姿态(stance_label) ·
   共振链(resonance_chains) · 发布闸门 · 客观性防火墙。
4. 规则**有序**：长串在前，短词在后；命中先改，后续规则不再重复匹配。

设计取舍
--------
- 「给真名」优先于「禁外号」：本脚本只做换名，不产生任何禁用词表（老板已否决）。
- 全量可审计：每条规则带命中计数；0 命中的规则会被列出来，提示原文可能已漂移。
"""

from __future__ import annotations

import argparse
import ast
import glob
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# ── 作用域：只有这些文件里的文本会进 prompt ──────────────────────────────
SCOPE = [
    "src/agent_analysis/prompts/*.md",
    "src/agent_analysis/orchestrator.py",
    "src/agent_analysis/contracts.py",
    "src/agent_analysis/deep_research_canon.py",
    "src/prompt_examples.py",
    "src/reasoning_examples.py",
    "src/agent_analysis/few_shot.py",
    "RESEARCH_CANON.md",
]

# ── 替换规则（有序，长串在前） ──────────────────────────────────────────
# 每条：(旧文, 新文, 说明)
PHRASE_RULES: list[tuple[str, str, str]] = [
    # ── A9 · 三句总种子（模型看到的第一批「本层判断长什么样」的样例）──
    (
        "把读数、趋势与分位压缩成一句本层判断。",
        "用一句话说清这个数说明了什么：先说结论，再把数值和它的历史位置嵌进因果里。",
        "A9 结构示例占位句（narrative）",
    ),
    (
        "必须讨论本层内部指标之间的共振、背离、降噪和优先级",
        "必须讨论本层内部指标之间是互相印证、互相背离，还是只是噪声，以及哪个更重要",
        "A9 硬编码字段说明（internal_conflict_analysis）",
    ),
    (
        "要归纳本层指标的方向与张力，不写空泛套话。",
        "要归纳本层指标的方向，以及它们之间方向不一致的地方，不写空泛套话。",
        "A9 五站共用层综合句",
    ),
    # ── A4 · 契约字段说明里的「共振 / 降噪」──
    (
        "本层内部指标之间的矛盾、共振或降噪判断",
        "本层内部指标之间是互相矛盾、互相印证，还是只是日常噪声",
        "A4 contracts 字段说明（矛盾保留）",
    ),
    (
        "该指标对其他层可能产生的约束、共振或冲突",
        "该指标对其他层可能产生的约束、印证或冲突",
        "A4 contracts 字段说明",
    ),
    ("层内冲突/共振判断", "层内冲突 / 印证判断", "A4 contracts 字段说明"),
    # ── A8 · 编排层英文混排 ──
    ("context boundary 是信息隔离边界", "边界就是信息隔离边界", "A8 中英混排"),
    ("专业认知镜头", "专业认知视角", "A8 机制词换人话"),
    # ── A4 · 去掉内部版本号（V5.8 不该出现在给模型的示例里）──
    ("【典范化解读 + 分层降噪V5.8】", "【典范化解读 + 剔除日常波动】", "A4 few-shot 去版本号"),
    ("【因果化解读 + 分层降噪】", "【因果化解读 + 剔除日常波动】", "A4 few-shot 去版本号"),
    ("【语境化解读 + 分层降噪V5.8】", "【语境化解读 + 剔除日常波动】", "A4 few-shot 去版本号"),
    ("分层降噪", "剔除日常波动", "A4 few-shot 正文"),
    # ── A5 · 「读数」特例（必须排在通用"读数"之前）──
    ("读数事实", "数据事实", "A5 机制链首项"),
    (
        "该指标当前读数（引用 payload 实际数值）",
        "该指标当前水平（引用 payload 实际数值）",
        "A5 结构示例占位句",
    ),
    ("市场/经济读数", "市场/经济数据", "A5 契约字段说明"),
    ("是诚实读数", "是诚实回答", "A5 canon"),
    # ── A6 · 温度计（按语境换，不搞一刀切）──
    ("科技股专属风险温度计", "科技股专属风险的先行指标", "A6 温度计"),
    ("资金价格温度计", "资金价格的先行指标", "A6 温度计"),
    ("增长预期温度计", "增长预期的先行指标", "A6 温度计"),
    ("【高质量信用温度计】", "【高质量信用环境观察】", "A6 温度计"),
    ("消费者信心的实时温度计", "消费者信心的实时反映", "A6 温度计"),
    # ── A6 · 地心引力（按语境换）──
    ("未来现金流折现率的地心引力", "未来现金流折现率的约束作用", "A6 地心引力"),
    ("估值地心引力增强", "估值折现压力增强", "A6 地心引力"),
    ("成长股估值的真正'地心引力'", "成长股估值的核心折现约束", "A6 地心引力"),
    ('所有风险资产的"地心引力"', "所有风险资产的定价基准", "A6 地心引力"),
    # ── A6 · 水位表 / 垫子截断形式 ──
    # 教训：早先写成 ("财政抽水/放水水位表" → "财政抽水/放水")，替换后得到
    # "TGA 是财政抽水/放水；" 这种残句（谓语丢了）。**长句替换必须把谓语一起写进去。**
    ("TGA 是财政抽水/放水的水位表", "TGA 反映财政抽水/放水", "A6 水位表"),
    ("TGA 是财政抽水/放水水位表", "TGA 反映财政抽水/放水", "A6 水位表"),
    ("无风险利率的垫子薄", "无风险利率的安全垫偏薄", "A6 垫子截断形式"),
    ("收益率垫子", "收益率安全垫", "A6 垫子截断形式"),
    # ── A3 · 「张力」特例（必须排在通用"张力"之前）──
    ("持续性/过热风险之间的张力", "持续性/过热风险之间的拉扯", "A3 桥接特例"),
    # ── A2 · 锚家族（长串在前）──
    ("外部参考锚", "外部参考基准", "A2 锚"),
    ("implied ERP 参考锚", "implied ERP 参考基准", "A2 锚"),
    ("数据判决是锚", "数据判决是基准", "A2 锚"),
    ("参考锚", "参考基准", "A2 锚"),
    ("主锚", "主要依据", "A2 锚"),
    ("第一锚", "首要依据", "A2 锚"),
    ("权重锚", "权重基准", "A2 锚"),
    ("硬锚", "硬性基准", "A2 锚"),
    ("分位锚", "历史分位", "A2 锚"),
    ("背景锚", "背景参考", "A2 锚"),
    ("短端锚", "短端基准", "A2 锚"),
    ("资金之锚", "资金基准", "A2 锚"),
    ("锚日", "日期", "A2 锚"),
    ("回看锚", "回看值", "A2 锚"),
    ("估值锚", "估值依据", "A2 锚"),
    ("广度锚", "广度基准", "A2 锚"),
    ("FRED 锚缺席", "FRED 参照缺席", "A2 锚"),
    ("FRED 锚", "FRED 参照", "A2 锚"),
    ("锚点", "提示", "A2 锚"),
    # ── A7 · 闸门（只治限定词；「发布闸门」是机制名，不动）──
    ("内部质量闸门", "内部校验", "A7 闸门"),
    ("质量闸门", "内部校验", "A7 闸门"),
    ("证据闸门", "证据校验", "A7 闸门"),
    ("硬闸门", "硬性字数限制", "A7 闸门"),
    ("本闸门", "本项校验", "A7 闸门"),
    ("数据日和新鲜度闸门", "数据日和新鲜度校验", "A7 闸门"),
    ("验证闸门", "验证环节", "A7 闸门"),
    # ── 通用兜底（放最后，避免吃掉上面的特例）──
    ("张力", "分歧", "A3 通用"),
    ("降噪", "剔除日常噪声", "A4 通用"),
    ("共振", "印证", "A4 通用"),
    ("读数", "数值", "A5 通用"),
]


# 「读数」这个词有两副面孔，必须区别对待：
#   ① 泛指"这个数"（当前读数 / 证据读数 / 方向读数）→ 换成"数值"，这是本轮的靶子；
#   ② "X 读数"式自然搭配（情绪读数 / 周期读数 / 波动性读数）→ **本来就是好中文，
#      换掉反而变差**。首轮全量替换把这三处改坏了，已人工恢复，并在此登记为保留短语。
# 教训：批量换词必须预留"例外名单"，否则一定会在某处把好文本改坏。
KEEP_PHRASES = ("情绪读数", "周期读数", "波动性读数")


def target_files() -> list[str]:
    files: list[str] = []
    for pattern in SCOPE:
        files.extend(sorted(glob.glob(os.path.join(ROOT, pattern))))
    return files


# 只有真 docstring 才跳过。**不能把所有三引号都当 docstring**——
# reasoning_examples.py / prompt_examples.py 里的 few-shot 范例正文本身就存在
# 三引号字符串里（那是要改的数据），早期版本一刀切跳过，导致整个文件零改动。
#
# 曾试过用正则猜"紧跟 def/class 的三引号"，被多行函数签名坑了两次
# （def foo(\n  self,\n) -> X: 这种，参数行会把"签名待续"状态清掉）。
# 改用标准库 ast 精确定位 docstring —— 这是唯一不会误判的做法。
def docstring_line_numbers(lines: list[str]) -> set[int]:
    """用 AST 精确取出模块/类/函数 docstring 所占的行号（1-based）。"""
    try:
        tree = ast.parse("\n".join(lines))
    except SyntaxError:
        return set()
    skip: set[int] = set()
    for node in ast.walk(tree):
        if not isinstance(
            node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            continue
        body = getattr(node, "body", [])
        if not body:
            continue
        first = body[0]
        if (
            isinstance(first, ast.Expr)
            and isinstance(first.value, ast.Constant)
            and isinstance(first.value.value, str)
        ):
            end = getattr(first, "end_lineno", None) or first.lineno
            skip.update(range(first.lineno, end + 1))
    return skip


def lines_to_skip(lines: list[str], is_python: bool) -> set[int]:
    """返回不应改动的行号（1-based）：纯注释行 + docstring 块。"""
    if not is_python:
        return set()
    skip = docstring_line_numbers(lines)
    skip.update(
        idx for idx, line in enumerate(lines, 1) if line.lstrip().startswith("#")
    )
    return skip


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真正写回文件（默认只 dry-run）")
    args = ap.parse_args()

    counts = {rule[0]: 0 for rule in PHRASE_RULES}
    files_changed = 0
    total_hits = 0
    report: list[str] = []

    for path in target_files():
        rel = os.path.relpath(path, ROOT)
        with open(path, encoding="utf-8") as fh:
            original = fh.read()
        lines = original.split("\n")
        skip = lines_to_skip(lines, path.endswith(".py"))
        new_lines = list(lines)
        file_hits: list[str] = []

        for idx, line in enumerate(lines, 1):
            if idx in skip:
                continue
            new_line = line
            # 先把保留短语藏成占位符，"例外名单"才真的生效
            protected: dict[str, str] = {}
            for k, phrase in enumerate(KEEP_PHRASES):
                if phrase in new_line:
                    token = f"\x00K{k}\x00"
                    protected[token] = phrase
                    new_line = new_line.replace(phrase, token)
            for old, new, note in PHRASE_RULES:
                if old in new_line:
                    cnt = new_line.count(old)
                    counts[old] += cnt
                    total_hits += cnt
                    new_line = new_line.replace(old, new)
                    file_hits.append(f"      L{idx} [{note}] {cnt}x  {old} → {new}")
            for token, phrase in protected.items():
                new_line = new_line.replace(token, phrase)
            new_lines[idx - 1] = new_line

        updated = "\n".join(new_lines)
        if updated != original:
            files_changed += 1
            report.append(f"\n{rel}  （{len(file_hits)} 处）")
            report.extend(file_hits)
            if args.apply:
                with open(path, "w", encoding="utf-8") as fh:
                    fh.write(updated)

    print("=" * 78)
    print("T72 语料改造 · A 档" + ("【已写回】" if args.apply else "【DRY-RUN，未写文件】"))
    print("=" * 78)
    print("".join(report) if report else "（无改动）")

    print("\n" + "=" * 78)
    print("规则命中统计（0 命中 = 原文可能已漂移，需人工确认）")
    print("=" * 78)
    zero: list[str] = []
    for old, new, note in PHRASE_RULES:
        c = counts[old]
        flag = "  ← 0 命中" if c == 0 else ""
        print(f"  {c:>4}x  [{note}]  {old}{flag}")
        if c == 0:
            zero.append(old)

    print(f"\n合计改动 {total_hits} 处，涉及 {files_changed} 个文件。")
    if zero:
        print(f"0 命中规则 {len(zero)} 条：{zero}")
    if not args.apply:
        print("\n（dry-run 结束；确认无误后加 --apply 执行）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
