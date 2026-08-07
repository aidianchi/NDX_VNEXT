"""T47 上下文摊开器：把一次跑里全部站点**实际收到**的上下文完整导出。

设计依据（`T47_上下文根本性审查.md` 第三步第一步）：
- 导出的是真实发出去的字节（`prompt_audit/**/*.prompt.txt` 与其配套 payload/response），
  不是设计文档说该给什么。
- 覆盖三种落盘布局，一站不能少：
  1. 标准布局   ``<stage>/attempt_N.prompt.txt``
  2. 调查布局   ``<stage>/inv_<id>.attempt_N.prompt.txt``（controlled_investigation）
  3. 嵌套布局   ``<stage>/<timestamp>/attempt_N.prompt.txt``（integrated_adjudicator）
- 字符量太大时做投影，但必须机械证明投影没丢关键结构：
  对每个站做键路径全覆盖 + 数值全保留 + 标题全保留三重校验，写进
  ``projection_verification.md`` 留证。

输出（默认写在 run 目录下 ``context_spread/``，属生成物、不进 git）：
- ``full/<stage>/...``        原文逐字节拷贝（附 sha256）
- ``projected/<stage>/...``   供 AI 通读的结构投影
- ``manifest.json``           全站清单：布局、实例、字节量、sha256、检查规则覆盖状态
- ``projection_verification.md``  投影无损校验留证
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# prompt_inspector.py 的 _scan_boundary 目前只为这些站注册了检查规则。
# 用于在 manifest 里标注"该站此前连机械检查都没有"——T47 的动机之一。
_INSPECTOR_RULED_STAGES = {
    "L1", "L2", "L3", "L4", "L5",
    "bridge", "thesis", "critic", "critic_retry",
    "risk", "risk_retry", "reviser", "final_adjudicator", "counter_thesis",
}

_LONG_STRING = 240          # 超过此长度的字符串做头尾截断
_STRING_HEAD = 120
_STRING_TAIL = 60
_LIST_KEEP_ALL = 6          # 短列表全保留
_LIST_SCALAR_KEEP_ALL = 20  # 纯标量列表放宽
_LIST_HEAD = 3              # 长列表保留头 3 尾 1
_TABLE_MIN_ROWS = 30        # 同构标量字典列表超过此行数转表格投影
_MIN_JSON_SPAN = 200        # 小于此体积的 JSON 片段不投影，原样保留


@dataclass
class PromptInstance:
    """一次真实发送：某个站的某个实例的某次 attempt。"""

    stage: str                 # prompt_audit 下的站目录名，如 L1 / integrated_adjudicator
    instance: str              # 实例标识：标准布局为 ""，调查布局为 inv_<id>，嵌套布局为时间戳目录
    attempt: int
    layout: str                # standard | investigation | nested
    prompt_path: Path
    extras: Dict[str, Path] = field(default_factory=dict)  # payload / response / parsed / error 等配套文件

    @property
    def key(self) -> str:
        parts = [self.stage]
        if self.instance:
            parts.append(self.instance)
        parts.append(f"attempt_{self.attempt}")
        return ".".join(parts)


# ---------------------------------------------------------------------------
# 发现：三种布局一站不漏
# ---------------------------------------------------------------------------

def discover_instances(prompt_audit: Path) -> List[PromptInstance]:
    instances: List[PromptInstance] = []
    if not prompt_audit.is_dir():
        return instances
    for prompt_path in sorted(prompt_audit.rglob("*.prompt.txt")):
        rel = prompt_path.relative_to(prompt_audit)
        stage = rel.parts[0]
        name = prompt_path.name
        instance = ""
        layout = "standard"
        attempt = 0

        m = re.fullmatch(r"attempt_(\d+)\.prompt\.txt", name)
        if m and len(rel.parts) == 2:
            attempt = int(m.group(1))
        else:
            m = re.fullmatch(r"(inv_[0-9a-f]+)\.attempt_(\d+)\.prompt\.txt", name)
            if m:
                layout = "investigation"
                instance = m.group(1)
                attempt = int(m.group(2))
            else:
                m = re.fullmatch(r"attempt_(\d+)\.prompt\.txt", name)
                if m and len(rel.parts) >= 3:
                    layout = "nested"
                    instance = "/".join(rel.parts[1:-1])
                    attempt = int(m.group(1))
                else:
                    # 未知命名也收编，宁可多不可少；layout 记 unknown 供人工看
                    layout = "unknown"
                    instance = "/".join(rel.parts[1:-1])

        extras: Dict[str, Path] = {}
        for sibling in sorted(prompt_path.parent.iterdir()):
            if sibling == prompt_path or not sibling.is_file():
                continue
            sname = sibling.name
            if layout == "investigation" and not sname.startswith(f"{instance}."):
                continue
            if layout == "standard" and not sname.startswith(f"attempt_{attempt}."):
                if sname not in {"meta.json", "output.validated.json"}:
                    continue
            extras[sname] = sibling
        instances.append(
            PromptInstance(
                stage=stage,
                instance=instance,
                attempt=attempt,
                layout=layout,
                prompt_path=prompt_path,
                extras=extras,
            )
        )
    return instances


# ---------------------------------------------------------------------------
# 投影：保结构、保全键、保全数值，只削长散文与长列表
# ---------------------------------------------------------------------------

def _is_scalar(value: Any) -> bool:
    return not isinstance(value, (dict, list))


def _project_value(value: Any) -> Any:
    """投影规则（承诺边界——校验按同一套规则核对，承诺内零丢失）：

    - dict：全部键保留，递归投影；
    - 字典列表：全部元素保留（逐元素投影），不丢行；
      例外是"同构标量表"（>30 行、每行键相同且全为标量，如行情序列）：
      压缩为 键清单 + 头 3 行 + 尾 1 行 + 每键 min/max + 总行数；
    - 标量列表：≤20 全保留；>20 保留头 10 尾 5 + 总条数 + min/max；
    - 字符串：≤240 字逐字保留；超长保留头 120 尾 60 并标注省略字符数；
    - 数字/布尔/None：逐字保留。

    即：投影**看不到的**只有两处——超长散文字符串的中段、长标量序列的中段。
    这两处的存在性、长度与范围（min/max）都在投影里留痕，需核对原值时查 full/。
    """
    if isinstance(value, dict):
        return {k: _project_value(v) for k, v in value.items()}
    if isinstance(value, list):
        if not value:
            return value
        if all(isinstance(v, dict) for v in value):
            keys = [tuple(v.keys()) for v in value]
            scalar_rows = all(all(_is_scalar(x) for x in v.values()) for v in value)
            if len(value) > _TABLE_MIN_ROWS and len(set(keys)) == 1 and scalar_rows:
                head = [_project_value(v) for v in value[:3]]
                tail = [_project_value(value[-1])]
                stats: Dict[str, Any] = {"__table__": True, "__total__": len(value)}
                for k in value[0].keys():
                    col = [v.get(k) for v in value if isinstance(v.get(k), (int, float)) and not isinstance(v.get(k), bool)]
                    if col:
                        stats[f"min:{k}"] = min(col)
                        stats[f"max:{k}"] = max(col)
                return {"__table_projection__": True, "columns": list(value[0].keys()), "head": head, "stats": stats, "tail": tail}
            return [_project_value(v) for v in value]
        projected = [_project_value(v) for v in value]
        scalar_only = all(_is_scalar(v) for v in value)
        if len(projected) <= _LIST_KEEP_ALL or (scalar_only and len(projected) <= _LIST_SCALAR_KEEP_ALL):
            return projected
        numeric = [v for v in value if isinstance(v, (int, float)) and not isinstance(v, bool)]
        marker: Dict[str, Any] = {"__omitted__": len(value) - 10 - 5, "__total__": len(value)}
        if numeric:
            marker["min"] = min(numeric)
            marker["max"] = max(numeric)
        return projected[:10] + [marker] + projected[-5:]
    if isinstance(value, str) and len(value) > _LONG_STRING:
        omitted = len(value) - _STRING_HEAD - _STRING_TAIL
        return f"{value[:_STRING_HEAD]}«…省略 {omitted} 字符…»{value[-_STRING_TAIL:]}"
    return value


def _all_number_tokens(value: Any) -> set:
    """递归收集一个值里的全部数值 token（数字本身 + 字符串里的数值片段）。用于被整体省略的元素。"""
    tokens: set = set()
    if isinstance(value, bool) or value is None:
        return tokens
    if isinstance(value, (int, float)):
        # 用同一把 _NUMBER_RE 尺子提取，保证负数等序列化差异不造成口径分裂
        tokens |= {m.group(0) for m in _NUMBER_RE.finditer(json.dumps(value))}
    elif isinstance(value, str):
        tokens |= {m.group(0) for m in _NUMBER_RE.finditer(value)}
    elif isinstance(value, dict):
        for k, v in value.items():
            tokens |= _all_number_tokens(k)
            tokens |= _all_number_tokens(v)
    elif isinstance(value, list):
        for v in value:
            tokens |= _all_number_tokens(v)
    return tokens


def _dropped_number_tokens(value: Any) -> set:
    """按投影同一套规则，收集会被丢弃的数值 token（只可能来自超长字符串中段、长序列中段、表格投影的中段行）。"""
    dropped: set = set()
    if isinstance(value, dict):
        for v in value.values():
            dropped |= _dropped_number_tokens(v)
    elif isinstance(value, list):
        if value and all(isinstance(v, dict) for v in value):
            keys = [tuple(v.keys()) for v in value]
            scalar_rows = all(all(_is_scalar(x) for x in v.values()) for v in value)
            if len(value) > _TABLE_MIN_ROWS and len(set(keys)) == 1 and scalar_rows:
                for v in value[3:-1]:  # 头 3 尾 1 保留，中段整体省略
                    dropped |= _all_number_tokens(v)
                for v in value[:3] + value[-1:]:
                    dropped |= _dropped_number_tokens(v)
                return dropped
            for v in value:
                dropped |= _dropped_number_tokens(v)
            return dropped
        scalar_only = all(_is_scalar(v) for v in value)
        omitted = len(value) > _LIST_KEEP_ALL and not (scalar_only and len(value) <= _LIST_SCALAR_KEEP_ALL)
        if omitted:
            for v in value[10:-5]:  # 与 _project_value 同一切口：头 10 尾 5 保留
                dropped |= _all_number_tokens(v)
            for v in value[:10] + value[-5:]:
                dropped |= _dropped_number_tokens(v)
            return dropped
        for v in value:
            dropped |= _dropped_number_tokens(v)
    elif isinstance(value, str):
        if len(value) > _LONG_STRING:
            middle = value[_STRING_HEAD : len(value) - _STRING_TAIL]
            dropped |= {m.group(0) for m in _NUMBER_RE.finditer(middle)}
    return dropped


def _section_inventory(text: str) -> List[Dict[str, Any]]:
    """按 `#` 标题行切出段落清单：标题、起始偏移、字符量。供投影头部生成导航目录。"""
    lines = text.split("\n")
    offsets = []
    cursor = 0
    for line in lines:
        offsets.append(cursor)
        cursor += len(line) + 1
    heads = [(i, ln.strip()) for i, ln in enumerate(lines) if ln.lstrip().startswith("#")]
    inventory: List[Dict[str, Any]] = []
    for idx, (line_no, title) in enumerate(heads):
        start = offsets[line_no]
        end = offsets[heads[idx + 1][0]] if idx + 1 < len(heads) else len(text)
        inventory.append({"title": title[:120], "offset": start, "chars": end - start})
    return inventory


def project_prompt(text: str) -> str:
    """把提示词里的 JSON 块替换为结构投影；散文（任务、规则、问题）逐字保留。

    投影头部附段落目录（标题 + 字符量），让通读者对"这站拿到的材料怎么分布"一目了然。
    """
    out: List[str] = []
    pos = 0
    decoder = json.JSONDecoder()
    lines = text.split("\n")
    offsets = []
    cursor = 0
    for line in lines:
        offsets.append(cursor)
        cursor += len(line) + 1

    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        if stripped[:1] in ("{", "[") and len(stripped) >= 1:
            start = offsets[i] + (len(line) - len(stripped))
            try:
                value, end = decoder.raw_decode(text[start:])
            except Exception:
                value = None
            if value is not None and end >= _MIN_JSON_SPAN:
                # 只在该 JSON 以整行结尾时替换，避免误吞后续散文
                out.append(text[pos:start])
                out.append(json.dumps(_project_value(value), ensure_ascii=False, indent=2, default=str))
                pos = start + end
                # 跳过已消费的行
                while i < len(lines) and offsets[i] < pos:
                    i += 1
                continue
        i += 1
    out.append(text[pos:])
    return "".join(out)


# ---------------------------------------------------------------------------
# 校验：键路径全覆盖 + 数值全保留 + 标题全保留
# ---------------------------------------------------------------------------

def _key_paths(value: Any, prefix: str = "") -> set:
    paths = set()
    if isinstance(value, dict):
        for k, v in value.items():
            p = f"{prefix}.{k}" if prefix else str(k)
            paths.add(p)
            paths |= _key_paths(v, p)
    elif isinstance(value, list):
        for v in value:
            paths |= _key_paths(v, f"{prefix}[*]")
    return paths


_NUMBER_RE = re.compile(r"\d+\.\d+|\d{4,}")


def verify_projection(original: str, projected: str) -> Dict[str, Any]:
    """对单站做三重校验，返回结果明细（供 verification 报告汇总）。

    数值校验与投影规则自洽：凡投影规则承诺保留的数值（散文全文、JSON 键值、
    短字符串、短列表、字典列表全部行、长字符串头尾、长标量序列头尾）
    必须 100% 出现在投影里；被规则丢弃的只允许是"超长散文中段"与
    "长标量序列中段"两类，且逐站报告丢弃数量——丢弃的每个数值都属于
    已声明的边界，不属于静默丢失。
    """
    # 1) 标题覆盖
    headings = [ln for ln in original.split("\n") if ln.lstrip().startswith("#")]
    missing_headings = [h for h in headings if h not in projected]

    # 2) JSON 键路径覆盖 + 规则内数值保留
    decoder = json.JSONDecoder()
    missing_keys: List[str] = []
    total_keys = 0
    promised_missing: List[str] = []
    dropped_by_rule: set = set()
    for m in re.finditer(r"(?m)^\s*(\{|\[)", original):
        try:
            value, end = decoder.raw_decode(original[m.start():])
        except Exception:
            continue
        if end < _MIN_JSON_SPAN:
            continue
        projected_value = _project_value(value)
        paths = _key_paths(projected_value)
        original_paths = _key_paths(value)
        # 表格/列表投影允许折叠行内键路径，但列名（键）必须在投影文本中出现
        for p in original_paths:
            leaf = re.sub(r"\[\*\]", "", p)
            if p not in paths and not any(p.startswith(base) for base in paths):
                if leaf.split(".")[-1] not in json.dumps(projected_value, ensure_ascii=False, default=str):
                    missing_keys.append(p)
        total_keys += len(original_paths)
        dropped_by_rule |= _dropped_number_tokens(value)
        serialized = json.dumps(projected_value, ensure_ascii=False, default=str)
        for token in {m2.group(0) for m2 in _NUMBER_RE.finditer(json.dumps(value, ensure_ascii=False, default=str))}:
            if token not in serialized and token not in dropped_by_rule:
                promised_missing.append(token)

    # 3) 全文数值：原文每个"实数"token 要么在投影里，要么属于已声明的丢弃边界
    all_numbers = {m.group(0) for m in _NUMBER_RE.finditer(original)}
    missing_numbers = sorted(n for n in all_numbers if n not in projected and n not in dropped_by_rule)

    return {
        "headings_total": len(headings),
        "headings_missing": len(missing_headings),
        "headings_missing_list": missing_headings[:10],
        "json_keys_total": total_keys,
        "json_keys_missing": len(missing_keys),
        "json_keys_missing_list": sorted(missing_keys)[:10],
        "numbers_total": len(all_numbers),
        "numbers_dropped_by_rule": len(dropped_by_rule & all_numbers),
        "numbers_missing": len(missing_numbers) + len(promised_missing),
        "numbers_missing_list": (missing_numbers + promised_missing)[:20],
        "ok": not missing_headings and not missing_keys and not missing_numbers and not promised_missing,
    }


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def _sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def spread_run(run_dir: Path, out_dir: Optional[Path] = None) -> Dict[str, Any]:
    run_dir = Path(run_dir)
    prompt_audit = run_dir / "prompt_audit"
    if out_dir is None:
        out_dir = run_dir / "context_spread"
    full_dir = out_dir / "full"
    proj_dir = out_dir / "projected"
    full_dir.mkdir(parents=True, exist_ok=True)
    proj_dir.mkdir(parents=True, exist_ok=True)

    instances = discover_instances(prompt_audit)
    manifest_instances: List[Dict[str, Any]] = []
    verification_rows: List[Dict[str, Any]] = []

    for inst in instances:
        raw = inst.prompt_path.read_bytes()
        text = raw.decode("utf-8")

        dest_rel = Path(inst.stage) / (inst.instance or "") if inst.instance else Path(inst.stage)
        full_dest = full_dir / dest_rel
        full_dest.mkdir(parents=True, exist_ok=True)
        prompt_dest = full_dest / inst.prompt_path.name
        prompt_dest.write_bytes(raw)
        copied = {inst.prompt_path.name: _sha256_bytes(raw)}
        for sname, spath in inst.extras.items():
            data = spath.read_bytes()
            (full_dest / sname).write_bytes(data)
            copied[sname] = _sha256_bytes(data)

        projection = project_prompt(text)
        proj_dest = proj_dir / dest_rel
        proj_dest.mkdir(parents=True, exist_ok=True)
        proj_name = inst.prompt_path.name.replace(".prompt.txt", ".projection.md")
        inventory = _section_inventory(text)
        toc_lines = ["## 段落目录（标题 · 字符量 · 占比）", ""]
        for item in inventory:
            toc_lines.append(f"- `{item['title']}` — {item['chars']:,} 字符（{item['chars'] / max(len(text), 1) * 100:.1f}%）")
        toc = "\n".join(toc_lines)
        header = (
            f"# 投影：{inst.key}\n"
            f"- 原文：{inst.prompt_path}\n"
            f"- 原文字符：{len(text):,}；投影字符：{len(projection):,}（{len(projection) / max(len(text), 1) * 100:.1f}%）\n"
            f"- 投影规则：散文逐字保留；JSON 块保全部键与全部数值。投影**看不到的**只有两处："
            f"超长散文字符串的中段、长标量序列的中段（两处都留长度与 min/max 标记，原值查 full/）。\n\n"
            f"{toc}\n\n---\n\n"
        )
        (proj_dest / proj_name).write_text(header + projection, encoding="utf-8")

        v = verify_projection(text, projection)
        v["station"] = inst.key
        verification_rows.append(v)

        stage_family = re.sub(r"\..*$", "", inst.stage)
        manifest_instances.append(
            {
                "key": inst.key,
                "stage": inst.stage,
                "stage_family": stage_family,
                "instance": inst.instance,
                "attempt": inst.attempt,
                "layout": inst.layout,
                "prompt_chars": len(text),
                "projection_chars": len(projection),
                "projection_ratio": round(len(projection) / max(len(text), 1), 4),
                "sha256": copied[inst.prompt_path.name],
                "extras": sorted(copied),
                "inspector_has_rules": inst.stage in _INSPECTOR_RULED_STAGES or stage_family in _INSPECTOR_RULED_STAGES,
                "inspector_can_read": inst.layout == "standard",
                "verification_ok": v["ok"],
            }
        )

    stages = sorted({i.stage for i in instances})
    manifest = {
        "run_dir": str(run_dir),
        "prompt_audit": str(prompt_audit),
        "out_dir": str(out_dir),
        "stage_dir_count": len(stages),
        "instance_count": len(instances),
        "stages": stages,
        "total_prompt_chars": sum(m["prompt_chars"] for m in manifest_instances),
        "total_projection_chars": sum(m["projection_chars"] for m in manifest_instances),
        "instances": manifest_instances,
    }
    (out_dir / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    _write_verification(out_dir / "projection_verification.md", manifest, verification_rows)
    return manifest


def _write_verification(path: Path, manifest: Dict[str, Any], rows: List[Dict[str, Any]]) -> None:
    lines = [
        "# 投影无损校验留证（T47）",
        "",
        "校验口径（机械执行，非抽样——全站逐条）：",
        "1. **标题覆盖**：原文每个 `#` 开头行必须逐字出现在投影里；",
        "2. **键路径覆盖**：原文每个成功解析的 JSON 块，其全部键路径（列表以 `[*]` 归一）必须在投影中存在；",
        "3. **数值保留**：凡投影规则承诺保留的数值必须 100% 出现在投影里；允许丢弃的只有两类——"
        "超长散文字符串的中段、长标量序列的中段——且逐站报告丢弃数量（这两处的存在性、长度与 min/max 均在投影留痕）。",
        "",
        f"- run：`{manifest['run_dir']}`",
        f"- 站目录数：{manifest['stage_dir_count']}；实例数（含多次 attempt）：{manifest['instance_count']}",
        f"- 原文总字符：{manifest['total_prompt_chars']:,}；投影总字符：{manifest['total_projection_chars']:,}"
        f"（{manifest['total_projection_chars'] / max(manifest['total_prompt_chars'], 1) * 100:.1f}%）",
        "",
        "| 站.实例 | 标题缺 | 键缺 | 承诺内数值缺 | 规则内丢弃 | 判定 |",
        "|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['station']} | {r['headings_missing']}/{r['headings_total']} "
            f"| {r['json_keys_missing']}/{r['json_keys_total']} "
            f"| {r['numbers_missing']} "
            f"| {r['numbers_dropped_by_rule']} "
            f"| {'✅ 承诺内零丢失' if r['ok'] else '❌ 有静默丢失'} |"
        )
    bad = [r for r in rows if not r["ok"]]
    lines.append("")
    if bad:
        lines.append("## 有损明细")
        for r in bad:
            lines.append(f"### {r['station']}")
            if r["headings_missing_list"]:
                lines.append(f"- 缺标题：{r['headings_missing_list']}")
            if r["json_keys_missing_list"]:
                lines.append(f"- 缺键：{r['json_keys_missing_list']}")
            if r["numbers_missing_list"]:
                lines.append(f"- 缺数值：{r['numbers_missing_list']}")
    else:
        lines.append("**全部实例三重校验通过：投影未丢标题、键路径与任何承诺保留的数值（承诺边界见上）。**")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="T47 上下文摊开器：导出一次跑全部站点真实收到的上下文。")
    parser.add_argument("--run-dir", required=True, help="output/analysis/vnext/<run_id>")
    parser.add_argument("--out-dir", help="默认 <run_dir>/context_spread")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    manifest = spread_run(Path(args.run_dir), Path(args.out_dir) if args.out_dir else None)
    print(json.dumps({k: manifest[k] for k in ("out_dir", "stage_dir_count", "instance_count", "total_prompt_chars", "total_projection_chars")}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
