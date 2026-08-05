"""T47 的粗糙原型（2026-08-05，非生产代码，勿接入主链）。

一次性扫描：把每次跑落盘的提示词语料摊开，机械检出"许可了但没给数值"。

**已知缺陷（正式实现必须修掉）**：`numbers()` 取的短数字（如 "10"、"20"）在两万字提示词里
必然偶然出现，导致漏判——**VXN 本身就是被这条漏掉的**（`L2.get_vxn` 的 current_reading
含 "10年百分位"，"10" 命中提示词他处即判为"已发"）。因此本脚本的产出是**下限**：
35 次跑扫出 41 条，真实数量更高（七路审计在单次跑里就人工数出 20 条）。
正式实现应按 ref 精确定位其数值段落，而非全文找数字。


判据全部是身份/存在性比对，不判语义：
- 声明集合：提示词里显式出现的 allow-list（allowed_data_refs / allowed_context_refs /
  ref_authority / key_evidence_refs）里列出的 ref 名字。
- 系统手里有没有：该 run 的 synthesis_packet.json 的 evidence_index[ref].current_reading。
- 实际给没给：current_reading 里的显著数字，在这一站的提示词里出现过没有。

只有"声明了 + 系统手里有 + 提示词里找不到数值"三者同时成立才报，避免误伤层间隔离
（L1-L5 的跨层 ref 只出现在格式示例里，不在 allow-list 内，天然不入选）。
"""
import json
import re
import sys
from pathlib import Path

REF = re.compile(r"L[1-5]\.get_[a-z0-9_]+", re.I)
ALLOW_KEYS = ("allowed_data_refs", "allowed_context_refs", "ref_authority", "key_evidence_refs")


def numbers(text):
    """从 current_reading 里取显著数字（两位以上或带小数），用于存在性比对。"""
    return [n for n in re.findall(r"-?\d+\.\d+|\d{2,}", str(text))][:4]


def allow_listed_refs(prompt):
    """取提示词里 allow-list 段落中出现的 ref 名。"""
    found = set()
    for key in ALLOW_KEYS:
        for m in re.finditer(re.escape(key), prompt):
            # 从 key 往后取一段，收集其中的 ref 名，遇到明显的段落边界就停
            window = prompt[m.end(): m.end() + 6000]
            window = re.split(r"\n\s*\n|\n#{2,}", window)[0]
            found.update(r for r in REF.findall(window))
    return found


def station_prompts(run):
    """返回 [(站名, 提示词文本)]，兼容多嵌一层时间戳目录的两站。"""
    out = []
    audit = run / "prompt_audit"
    if not audit.exists():
        return out
    for d in sorted(p for p in audit.iterdir() if p.is_dir()):
        files = sorted(d.glob("attempt_*.prompt.txt")) or sorted(d.glob("*/attempt_*.prompt.txt"))
        if files:
            out.append((d.name, files[-1].read_text(encoding="utf-8")))
    return out


def sweep(run):
    packet_file = run / "synthesis_packet.json"
    if not packet_file.exists():
        return None
    index = json.loads(packet_file.read_text(encoding="utf-8")).get("evidence_index", {})
    readings = {ref: v.get("current_reading") for ref, v in index.items() if isinstance(v, dict)}

    rows = []
    for station, prompt in station_prompts(run):
        declared = allow_listed_refs(prompt)
        if not declared:
            continue
        hollow = []
        for ref in sorted(declared):
            reading = readings.get(ref)
            if not reading:
                continue  # 系统自己也没有这个数，不算"给少了"
            nums = numbers(reading)
            if nums and not any(n in prompt for n in nums):
                hollow.append((ref, str(reading)[:40]))
        if declared:
            rows.append((station, len(declared), hollow))
    return rows


runs = sorted(Path("output/analysis/vnext").glob("2026*"))
runs = [r for r in runs if (r / "synthesis_packet.json").exists() and (r / "prompt_audit").exists()]
print(f"可扫描的 run：{len(runs)} 个\n")

total_hollow = 0
for run in runs:
    rows = sweep(run)
    if not rows:
        continue
    flagged = [r for r in rows if r[2]]
    if not flagged:
        print(f"{run.name}：{len(rows)} 站有许可清单，全部数值到位")
        continue
    print(f"{run.name}：")
    for station, n_declared, hollow in flagged:
        total_hollow += len(hollow)
        print(f"  ⚠ {station}：许可 {n_declared} 条，其中 {len(hollow)} 条系统手里有数值却没发过去")
        for ref, reading in hollow[:4]:
            print(f"      {ref} —— 系统持有 “{reading}…”")
        if len(hollow) > 4:
            print(f"      …另 {len(hollow) - 4} 条")
    print()

print(f"合计检出「系统手里有、却没发给已许可站点」的条目：{total_hollow} 条")
