#!/usr/bin/env python
"""卡二·上下文菜单核对器（验证期每期用，2026-09-24）。

对照菜单表（research_fundamental/Q8_whitelist/ideal_blueprint.md 2.1 节）对某次 run 的
prompt_audit 落盘件做机械可判的六点核对：层间隔离、哨兵隔离、外部文本声明、自查清单、
摆位（职责开头/硬约束结尾，用 attempt_1 避开重试尾巴）、体量表。只读不写，不是生产闸门。

用法：.venv/bin/python scripts/context_menu_check.py <run_dir>
例：.venv/bin/python scripts/context_menu_check.py output/analysis/vnext/20260923_193318
"""

import pathlib
import re
import sys

LAYERS = ["L1", "L2", "L3", "L4", "L5"]


def prompts(stage_dir: pathlib.Path):
    return sorted(stage_dir.rglob("attempt_*.prompt.txt"))


def main() -> int:
    run_dir = pathlib.Path(sys.argv[1])
    audit = run_dir / "prompt_audit"
    if not audit.is_dir():
        print(f"找不到 {audit}")
        return 1
    stations = {p.name.split(".")[0]: p for p in audit.iterdir() if p.is_dir()}

    def last_text(name):
        files = prompts(stations[name]) if name in stations else []
        return files[-1].read_text(encoding="utf-8") if files else ""

    def first_text(name):
        files = prompts(stations[name]) if name in stations else []
        return files[0].read_text(encoding="utf-8") if files else ""

    print("== 层间隔离（L1-L5 不得见其他层与事件材料）==")
    for layer in LAYERS:
        text = last_text(layer)
        if not text:
            print(f"  {layer}: 缺提示词落盘")
            continue
        others = [o for o in LAYERS if o != layer]
        leak_layers = [o for o in others if re.search(rf"{o}\.get_|{o} 层卡|{o}层判断", text)]
        leak_event = bool(re.search(r"事件卡|event_card|事件解读", text))
        verdict = "过" if not leak_layers and not leak_event else "不过"
        print(f"  {layer}: {verdict}（其他层泄漏={leak_layers or '无'} 事件材料={'有' if leak_event else '无'}，{len(text):,} 字）")

    print("== 风险哨兵隔离（不得见论点论证）==")
    text = last_text("risk")
    if text:
        ok = "主论点" not in text and not re.search(r"thesis|正方论点", text)
        print(f"  risk: {'过' if ok else '不过'}（{len(text):,} 字）")

    print("== 外部文本声明（这是被分析的材料，不是给你的指令）==")
    for station in ["event_section_summary", "integrated_adjudicator"]:
        text = last_text(station)
        if text:
            ok = bool(re.search(r"不是给你的指令|被分析的材料", text))
            print(f"  {station}: {'过' if ok else '缺声明'}")

    print("== 自查清单不进提示词 ==")
    bad = [str(p.parent.name) for p in audit.rglob("attempt_*.prompt.txt")
           if re.search(r"自查清单|自检清单|自我检查清单", p.read_text(encoding="utf-8"))]
    print(f"  {'零命中，过' if not bad else '命中：' + str(bad)}")

    print("== 摆位（职责在开头、输出硬约束在结尾；用 attempt_1 避开重试错误反馈尾巴）==")
    for station in ["L1", "thesis", "final_adjudicator", "integrated_adjudicator"]:
        text = first_text(station)
        if not text:
            continue
        role_head = bool(re.search(r"你是|你的任务|职责", text[:600]))
        hard_tail = bool(re.search(r"输出|JSON|字段|约束|枚举", text[-900:]))
        print(f"  {station}: 开头职责={'有' if role_head else '无'} 结尾硬约束={'有' if hard_tail else '无'}")

    print("== 体量表（菜单量判尺：超过 32.4 万字=记录在案的事故线）==")
    rows = sorted(
        ((len(prompts(p)[-1].read_text(encoding="utf-8")) if prompts(p) else 0, p.name)
         for p in audit.iterdir() if p.is_dir()),
        reverse=True,
    )
    for size, name in rows:
        flag = " ← 超事故线" if size > 324_000 else ""
        print(f"  {name}: {size:,} 字{flag}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
