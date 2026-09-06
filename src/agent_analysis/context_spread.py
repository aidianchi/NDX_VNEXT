"""T47 上下文摊开器：把一次跑里全部站点**实际收到**的上下文完整导出。

设计依据（`T47_上下文根本性审查.md` 第三步第一步）：
- 导出的是真实发出去的字节（`prompt_audit/**/*.prompt.txt` 与其配套 payload/response），
  不是设计文档说该给什么。
- 覆盖三种落盘布局，一站不能少：
  1. 标准布局   ``<stage>/attempt_N.prompt.txt``
  2. 调查布局   ``<stage>/inv_<id>.attempt_N.prompt.txt``（controlled_investigation）
  3. 嵌套布局   ``<stage>/<timestamp>/attempt_N.prompt.txt``（integrated_adjudicator）
- 字符量太大时做投影，但必须机械证明投影没丢关键结构。

2026-08-08 骨架重修（T47 阶段零）——修复此前两条自证裂缝并补齐同类问题：
- **校验全部从实际落盘产物独立回查**：原文用 ``full/`` 落盘拷贝（并与 prompt_audit
  源文件做 sha256 逐字节回查），投影用 ``projected/`` 落盘文件本身——键路径与
  承诺内数值都从投影文件里重新解析，而不是把 ``_project_value`` 在内存里再算一遍
  跟自己比（此前的"自算自证"：篡改落盘投影文件，键校验照样放行）。
- **块发现共用一把尺子**：投影器与校验器共用 ``_iter_json_blocks``，缩进 JSON
  块（基线 run 有 37/103 块）不再漏校验。
- **数值口径修正**：正则覆盖 1–3 位整数、负号与科学计数法，同时排除
  标识符内的数字（attempt_1 / sha256 / v1.2 等不产生数值 token）。
- 校验写进 ``projection_verification.md`` 留证。

投影丢失边界（**三处**，全部在投影里留痕：长度/行数 + min/max，原值查 ``full/``）：
1. 超长散文字符串（>240 字符）的中段；
2. 长标量序列（标量 >20 项 / 非标量 >15 项）的中段；
3. 同构标量表（>30 行字典列表）的中段行。

输出（默认写在 run 目录下 ``context_spread/``，属生成物、不进 git）：
- ``full/<stage>/...``        原文逐字节拷贝（manifest 逐文件记 sha256）
- ``projected/<stage>/...``   供 AI 通读的结构投影
- ``manifest.json``           全站清单：布局、实例、字节量、逐文件 sha256、检查规则覆盖状态
- ``projection_verification.md``  投影无损校验留证（全部从落盘产物回查）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import sys
from collections import Counter
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
_NUMERIC_CHARS = frozenset("0123456789.+-")


def _numeric_span_at(text: str, cut: int, cap: int = 32):
    """体检 #6：投影截断器把数字从中间劈开（22.92→残留 .92、155.18→残留 5.18），
    残留「合法形状的错误文本」比纯丢失更危险。切点落在数字中间时返回该数字的
    (start, end)；切点不在数字上返回 None。数字串超过 cap 字符则放弃（维持原切点）。"""
    i = min(max(cut, 0), len(text))
    if i >= len(text) or text[i] not in _NUMERIC_CHARS:
        return None
    lo = i
    while lo > 0 and text[lo - 1] in _NUMERIC_CHARS and i - lo < cap:
        lo -= 1
    hi = i
    while hi < len(text) and text[hi] in _NUMERIC_CHARS and hi - i < cap:
        hi += 1
    return (lo, hi)
_STRING_TAIL = 60
_LIST_KEEP_ALL = 6          # 短列表全保留
_LIST_SCALAR_KEEP_ALL = 20  # 纯标量列表放宽
_LIST_NONSCALAR_KEEP_ALL = 15  # 非标量列表放宽到 15：截断只留头 10 尾 5，短于 16 项截断不省略任何元素
_LIST_HEAD = 3              # 长列表保留头 3 尾 1
_TABLE_MIN_ROWS = 30        # 同构标量字典列表超过此行数转表格投影
_MIN_JSON_SPAN = 200        # 小于此体积的 JSON 片段不投影，原样保留

# 数值 token 尺子：覆盖 1–3 位整数、小数、负号、科学计数法；
# 左边界排除标识符内的数字（attempt_1 / sha256 / v1.2 等不产生 token），
# 右边界只挡数字与点（允许 75bp / 10年 这类带单位数值成为 token——
# 它们只出现在逐字保留的散文/字符串里，两边同尺提取，口径不分裂）。
# 投影与校验共用同一把尺子，口径才不会分裂。
_NUMBER_RE = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?(?![\d.])")


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
            if layout == "investigation":
                # 按 实例+attempt 双前缀收编，attempt_2 不得把 attempt_1 的文件算进自己名下
                if not sname.startswith(f"{instance}.attempt_{attempt}."):
                    continue
            elif layout == "nested":
                # 嵌套布局同样按 attempt 收编，外加目录级共享文件
                if not sname.startswith(f"attempt_{attempt}."):
                    if sname not in {"meta.json", "output.validated.json"}:
                        continue
            elif layout == "standard" and not sname.startswith(f"attempt_{attempt}."):
                if sname not in {"meta.json", "output.validated.json"}:
                    continue
            # unknown 布局不挑拣：宁可多收不可漏收，供人工看
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


def _list_middle_omitted(value: List[Any]) -> bool:
    """列表中段是否被省略——投影器与丢失收集器共用同一判定，防止两边切口漂移。

    - ≤6 项全保留；纯标量 ≤20 全保留；
    - 非标量 ≤15 全保留（截断只留头 10 尾 5，短于 16 项时截断不省略任何元素，
      只会重复元素并产出负的 ``__omitted__``——2026-08-08 修复的 bug）；
    - 更长且**中段全为标量**才截断（头 10 尾 5，中段省略）：
      中段若含 dict/list，其键路径无法在投影里留痕，而键路径承诺是全覆盖——
      所以含结构化元素的中段不截断，整个列表逐元素保留。
    """
    if len(value) <= _LIST_KEEP_ALL:
        return False
    if all(_is_scalar(v) for v in value):
        threshold = _LIST_SCALAR_KEEP_ALL
    else:
        threshold = _LIST_NONSCALAR_KEEP_ALL
    if len(value) <= threshold:
        return False
    return all(_is_scalar(v) for v in value[10:-5])


def _project_value(value: Any) -> Any:
    """投影规则（承诺边界——校验按同一套规则核对，承诺内零丢失）：

    - dict：全部键保留，递归投影；
    - 字典列表：全部元素保留（逐元素投影），不丢行；
      例外是"同构标量表"（>30 行、每行键相同且全为标量，如行情序列）：
      压缩为 键清单 + 头 3 行 + 尾 1 行 + 每键 min/max + 总行数；
    - 标量列表：≤20 全保留；>20 保留头 10 尾 5 + 总条数 + min/max；
    - 非标量列表（元素含 dict/list）：≤15 全保留；>15 且中段全为标量才截断
      （头 10 尾 5 + 总条数），中段含结构化元素则逐元素全保留——键路径承诺
      是全覆盖，中段 dict/list 的键无法在投影里留痕；
    - 字符串：≤240 字逐字保留；超长保留头 120 尾 60 并标注省略字符数；
    - 数字/布尔/None：逐字保留。

    即：投影**看不到的**只有三处——超长散文字符串的中段、长标量序列的中段、
    同构标量表的中段行。这三处的存在性、长度/行数与范围（min/max）都在投影里
    留痕，需核对原值时查 full/。
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
        if not _list_middle_omitted(value):
            return projected
        numeric = [v for v in value if isinstance(v, (int, float)) and not isinstance(v, bool)]
        marker: Dict[str, Any] = {"__omitted__": len(value) - 10 - 5, "__total__": len(value)}
        if numeric:
            marker["min"] = min(numeric)
            marker["max"] = max(numeric)
        return projected[:10] + [marker] + projected[-5:]
    if isinstance(value, str) and len(value) > _LONG_STRING:
        omitted = len(value) - _STRING_HEAD - _STRING_TAIL
        # 头窗切点落在数字中间→右移把数字完整包含；尾窗切点落在数字中间→左移。
        # 两个方向都保证数字不被劈半、也不被整段丢进省略区。
        head = _STRING_HEAD
        span = _numeric_span_at(value, _STRING_HEAD)
        if span and span[1] - _STRING_HEAD <= 32:
            head = span[1]
        tail_start = len(value) - _STRING_TAIL
        span = _numeric_span_at(value, tail_start)
        if span and tail_start - span[0] <= 32:
            tail_start = span[0]
        return f"{value[:head]}«…省略 {omitted} 字符…»{value[tail_start:]}"
    return value


def _all_number_token_counts(value: Any) -> Counter:
    """递归收集一个值里的全部数值 token（数字本身 + 字符串里的数值片段），计出现次数。
    用于被整体省略的元素。集合版见 ``_all_number_tokens``。"""
    counts: Counter = Counter()
    if isinstance(value, bool) or value is None:
        return counts
    if isinstance(value, (int, float)):
        # 用同一把 _NUMBER_RE 尺子提取，保证负数等序列化差异不造成口径分裂
        counts.update(m.group(0) for m in _NUMBER_RE.finditer(json.dumps(value)))
    elif isinstance(value, str):
        counts.update(m.group(0) for m in _NUMBER_RE.finditer(value))
    elif isinstance(value, dict):
        for k, v in value.items():
            counts.update(_all_number_token_counts(k))
            counts.update(_all_number_token_counts(v))
    elif isinstance(value, list):
        for v in value:
            counts.update(_all_number_token_counts(v))
    return counts


def _all_number_tokens(value: Any) -> set:
    return set(_all_number_token_counts(value))


def _dropped_number_token_counts(value: Any) -> Counter:
    """按投影同一套规则，收集会被丢弃的数值 token，计出现次数。

    只可能来自三处已声明边界：超长字符串中段、长序列中段、表格投影的中段行。
    切口判定与 ``_project_value`` 共用 ``_list_middle_omitted``，防止两边漂移。
    """
    dropped: Counter = Counter()
    if isinstance(value, dict):
        for v in value.values():
            dropped.update(_dropped_number_token_counts(v))
    elif isinstance(value, list):
        if value and all(isinstance(v, dict) for v in value):
            keys = [tuple(v.keys()) for v in value]
            scalar_rows = all(all(_is_scalar(x) for x in v.values()) for v in value)
            if len(value) > _TABLE_MIN_ROWS and len(set(keys)) == 1 and scalar_rows:
                for v in value[3:-1]:  # 头 3 尾 1 保留，中段整体省略
                    dropped.update(_all_number_token_counts(v))
                for v in value[:3] + value[-1:]:
                    dropped.update(_dropped_number_token_counts(v))
                return dropped
            for v in value:
                dropped.update(_dropped_number_token_counts(v))
            return dropped
        if _list_middle_omitted(value):
            for v in value[10:-5]:  # 与 _project_value 同一切口：头 10 尾 5 保留
                dropped.update(_all_number_token_counts(v))
            for v in value[:10] + value[-5:]:
                dropped.update(_dropped_number_token_counts(v))
            return dropped
        for v in value:
            dropped.update(_dropped_number_token_counts(v))
    elif isinstance(value, str):
        if len(value) > _LONG_STRING:
            middle = value[_STRING_HEAD : len(value) - _STRING_TAIL]
            dropped.update(m.group(0) for m in _NUMBER_RE.finditer(middle))
    return dropped


def _dropped_number_tokens(value: Any) -> set:
    return set(_dropped_number_token_counts(value))


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


def _iter_json_blocks(text: str) -> List[Tuple[int, int, Any]]:
    """逐行扫描找出文本中的 JSON 块，返回 ``(起始偏移, 结束偏移, 解析值)`` 列表。

    投影器与校验器共用这同一把尺子，保证"哪些块被投影"两边口径一致：
    - 行首（去缩进后）为 ``{`` 或 ``[`` 时，从首个非空白字符起 raw_decode；
    - 解码成功即记为一块（不论大小），并跳过被它覆盖的行——嵌套在内层的
      ``{`` 行不会被重复计数；解码失败的行不消费，继续逐行扫描（内层可能
      还有能独立解码的块）；
    - 缩进的独立块同样被发现（旧校验器从行首含空白处 raw_decode 必然失败，
      导致基线 run 里 37/103 个被投影的块从未被键/数值校验——本轮修复）。
    """
    decoder = json.JSONDecoder()
    lines = text.split("\n")
    offsets = []
    cursor = 0
    for line in lines:
        offsets.append(cursor)
        cursor += len(line) + 1

    blocks: List[Tuple[int, int, Any]] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        stripped = line.lstrip()
        if stripped[:1] in ("{", "["):
            start = offsets[i] + (len(line) - len(stripped))
            try:
                value, end = decoder.raw_decode(text[start:])
            except Exception:
                i += 1
                continue
            blocks.append((start, start + end, value))
            while i < len(lines) and offsets[i] < start + end:
                i += 1
            continue
        i += 1
    return blocks


def project_prompt(text: str) -> str:
    """把提示词里的 JSON 块替换为结构投影；散文（任务、规则、问题）逐字保留。

    块发现与校验共用 ``_iter_json_blocks``；只有跨度 ≥ ``_MIN_JSON_SPAN`` 的块
    做投影，更小的块原样保留（本身就是全文，逐字即无损）。
    JSON 块后面同行若还有散文，散文原样留在 ``text[pos:]`` 里，不会被吞。
    投影头部附段落目录（标题 + 字符量），让通读者对"这站拿到的材料怎么分布"一目了然。
    """
    out: List[str] = []
    pos = 0
    for start, end, value in _iter_json_blocks(text):
        if end - start < _MIN_JSON_SPAN:
            continue
        out.append(text[pos:start])
        out.append(json.dumps(_project_value(value), ensure_ascii=False, indent=2, default=str))
        pos = end
    out.append(text[pos:])
    return "".join(out)


# ---------------------------------------------------------------------------
# 校验：全部从实际落盘产物独立回查——逐字节比对 + 块配对 + 键路径 + 承诺内数值 + 标题
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


def _number_tokens(text: str) -> set:
    return {m.group(0) for m in _NUMBER_RE.finditer(text)}


def verify_instance_files(
    full_prompt_path: Path,
    projection_path: Path,
    source_prompt_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """对单个实例做校验，**全部输入都是实际落盘文件**，不再自算自证。

    - 原文读 ``full/`` 落盘拷贝；给了 ``source_prompt_path`` 时与 prompt_audit
      源文件做 sha256 逐字节回查（拷贝本身也算被校验对象）；
    - 投影读 ``projected/`` 落盘文件本身：键路径从投影文件里重新解析出的值提取，
      承诺内数值在投影文件的块原文区间里重新检索——不再把 ``_project_value``
      在内存里再算一遍跟自己比（篡改落盘投影必须被抓到）。

    校验项：
    0. 逐字节：full/ 拷贝与源文件 sha256 一致；
    1. 标题覆盖：原文每个 ``#`` 开头行逐字出现在投影文件里；
    2. 块配对：原文与投影文件按同一发现器逐块配对，块数必须一致；
       逐字保留的小块两边解析值必须相等，被投影的块做键路径覆盖 +
       承诺内数值检查（承诺内 = 三处声明边界之外的全部数值）；
    3. 全文数值：散文区 raw token + 各 JSON 块 dumps 归一化 token，
       每个都必须出现在投影文件里，或属于已声明的丢弃边界
       （唯一 token 数与出现次数都报告）。
    """
    full_bytes = full_prompt_path.read_bytes()
    original = full_bytes.decode("utf-8")
    projected_text = projection_path.read_text(encoding="utf-8")

    # 0) 逐字节回查
    bytes_identical = True
    if source_prompt_path is not None:
        bytes_identical = _sha256_bytes(source_prompt_path.read_bytes()) == _sha256_bytes(full_bytes)

    # 1) 标题覆盖
    headings = [ln for ln in original.split("\n") if ln.lstrip().startswith("#")]
    missing_headings = [h for h in headings if h not in projected_text]

    # 2) 块配对 + 键路径 + 承诺内数值
    original_blocks = _iter_json_blocks(original)
    projected_blocks = _iter_json_blocks(projected_text)
    blocks_paired = len(original_blocks) == len(projected_blocks)
    missing_keys: List[str] = []
    promised_missing: List[str] = []
    total_keys = 0
    dropped_counts: Counter = Counter()
    if blocks_paired:
        for (o_start, o_end, o_value), (p_start, p_end, p_value) in zip(original_blocks, projected_blocks):
            dropped_counts.update(_dropped_number_token_counts(o_value))
            original_paths = _key_paths(o_value)
            total_keys += len(original_paths)
            if o_value == p_value and original[o_start:o_end] == projected_text[p_start:p_end]:
                continue  # 逐字保留的小块：原文区间与投影区间逐字相同，天然无损
            projected_paths = _key_paths(p_value)
            proj_dump = json.dumps(p_value, ensure_ascii=False, default=str)
            # 折叠路径（表格/列表投影的行内键）以叶名兜底：列名必须在投影文本中出现。
            # 注意不能用"前缀在投影里就算覆盖"——那会把被删掉的嵌套键放行（红灯测试 7）。
            for p in original_paths:
                if p not in projected_paths:
                    leaf = re.sub(r"\[\*\]", "", p).split(".")[-1]
                    if leaf not in proj_dump:
                        missing_keys.append(p)
            block_dropped = set(_dropped_number_token_counts(o_value))
            p_tokens = _number_tokens(projected_text[p_start:p_end])
            o_dump = json.dumps(o_value, ensure_ascii=False, default=str)
            for token in _number_tokens(o_dump):
                if token not in p_tokens and token not in block_dropped:
                    promised_missing.append(token)

    # 3) 全文数值：散文区按原文取 token，JSON 块按 dumps 归一化取 token
    #    （归一化避免 19.460→19.46 这类重序列化表示差异造成误报）
    prose_tokens: set = set()
    cursor = 0
    for start, end, _v in original_blocks:
        prose_tokens |= _number_tokens(original[cursor:start])
        cursor = end
    prose_tokens |= _number_tokens(original[cursor:])
    block_tokens: set = set()
    for _s, _e, o_value in original_blocks:
        block_tokens |= _number_tokens(json.dumps(o_value, ensure_ascii=False, default=str))
    all_numbers = prose_tokens | block_tokens
    projected_tokens = _number_tokens(projected_text)
    dropped_set = set(dropped_counts)
    missing_numbers = sorted(n for n in all_numbers if n not in projected_tokens and n not in dropped_set)

    numbers_missing = len(missing_numbers) + len(promised_missing)
    return {
        "bytes_identical": bytes_identical,
        "blocks_original": len(original_blocks),
        "blocks_projected": len(projected_blocks),
        "blocks_paired": blocks_paired,
        "headings_total": len(headings),
        "headings_missing": len(missing_headings),
        "headings_missing_list": missing_headings[:10],
        "json_keys_total": total_keys,
        "json_keys_missing": len(missing_keys),
        "json_keys_missing_list": sorted(missing_keys)[:10],
        "numbers_total": len(all_numbers),
        "numbers_dropped_unique": len(dropped_set & all_numbers),
        "numbers_dropped_occurrences": sum(dropped_counts.values()),
        "numbers_missing": numbers_missing,
        "numbers_missing_list": (missing_numbers + promised_missing)[:20],
        "ok": (
            bytes_identical
            and blocks_paired
            and not missing_headings
            and not missing_keys
            and not missing_numbers
            and not promised_missing
        ),
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
    # 重跑前清掉自己上次生成的产物，防止陈旧文件混入本轮留证
    # （只清本工具自己的输出：full/、projected/ 与两份报告，不动任何其他文件）
    for stale in (full_dir, proj_dir):
        if stale.is_dir():
            shutil.rmtree(stale)
    for stale_file in (out_dir / "manifest.json", out_dir / "projection_verification.md"):
        if stale_file.is_file():
            stale_file.unlink()
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
        copy_sources = {inst.prompt_path.name: inst.prompt_path}
        for sname, spath in inst.extras.items():
            (full_dest / sname).write_bytes(spath.read_bytes())
            copy_sources[sname] = spath
        # 逐文件从落盘回读算 sha256，并与源文件比对——哈希必须存进 manifest，
        # 不许"算了就扔"
        file_sha256: Dict[str, str] = {}
        extras_bytes_ok = True
        for sname, spath in copy_sources.items():
            dest_bytes = (full_dest / sname).read_bytes()
            file_sha256[sname] = _sha256_bytes(dest_bytes)
            if _sha256_bytes(spath.read_bytes()) != file_sha256[sname]:
                extras_bytes_ok = False

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
            f"- 投影规则：散文逐字保留；JSON 块保全部键路径与承诺内数值。投影**看不到的**只有三处："
            f"超长散文字符串的中段、长标量序列的中段、同构标量表（>30 行）的中段行"
            f"（三处都留长度/行数与 min/max 标记，原值查 full/）。\n\n"
            f"{toc}\n\n---\n\n"
        )
        proj_file = proj_dest / proj_name
        proj_file.write_text(header + projection, encoding="utf-8")
        projection_sha256 = _sha256_bytes(proj_file.read_bytes())

        # 校验全部从落盘产物回查：原文用 full/ 拷贝、投影用 projected/ 文件
        v = verify_instance_files(prompt_dest, proj_file, source_prompt_path=inst.prompt_path)
        v["station"] = inst.key
        v["extras_bytes_identical"] = extras_bytes_ok
        v["ok"] = v["ok"] and extras_bytes_ok
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
                "sha256": file_sha256[inst.prompt_path.name],
                "files": file_sha256,
                "projection_file": proj_name,
                "projection_sha256": projection_sha256,
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
        "spread_version": 2,
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
        "# 投影无损校验留证（T47，骨架重修版）",
        "",
        "校验口径（机械执行，非抽样——全站逐条，**全部从实际落盘产物独立回查**：",
        "原文用 full/ 落盘拷贝并与 prompt_audit 源文件做 sha256 逐字节比对，",
        "投影用 projected/ 落盘文件本身重新解析，不再自算自证）：",
        "0. **逐字节**：full/ 每个拷贝文件与源文件 sha256 一致；",
        "1. **块配对**：原文与投影文件的 JSON 块按同一发现器逐块配对，块数必须一致；",
        "2. **标题覆盖**：原文每个 `#` 开头行必须逐字出现在投影里；",
        "3. **键路径覆盖**：原文每个 JSON 块的全部键路径（列表以 `[*]` 归一）必须在投影中存在；",
        "4. **数值保留**：凡投影规则承诺保留的数值必须 100% 出现在投影里；允许丢弃的只有三类——"
        "超长散文字符串的中段、长标量序列的中段、同构标量表（>30 行）的中段行——"
        "逐站报告丢弃的唯一 token 数与出现次数（三处的存在性、长度/行数与 min/max 均在投影留痕）。",
        "",
        f"- run：`{manifest['run_dir']}`",
        f"- 站目录数：{manifest['stage_dir_count']}；实例数（含多次 attempt）：{manifest['instance_count']}",
        f"- 原文总字符：{manifest['total_prompt_chars']:,}；投影总字符：{manifest['total_projection_chars']:,}"
        f"（{manifest['total_projection_chars'] / max(manifest['total_prompt_chars'], 1) * 100:.1f}%）",
        "",
        "| 站.实例 | 逐字节 | 块配对 | 标题缺 | 键缺 | 承诺内数值缺 | 规则内丢弃(唯一/次) | 判定 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        lines.append(
            f"| {r['station']} | {'✅' if r['bytes_identical'] and r.get('extras_bytes_identical', True) else '❌'} "
            f"| {r['blocks_projected']}/{r['blocks_original']}{'✅' if r['blocks_paired'] else '❌'} "
            f"| {r['headings_missing']}/{r['headings_total']} "
            f"| {r['json_keys_missing']}/{r['json_keys_total']} "
            f"| {r['numbers_missing']} "
            f"| {r['numbers_dropped_unique']}/{r['numbers_dropped_occurrences']} "
            f"| {'✅ 承诺内零丢失' if r['ok'] else '❌ 有静默丢失'} |"
        )
    bad = [r for r in rows if not r["ok"]]
    lines.append("")
    if bad:
        lines.append("## 有损明细")
        for r in bad:
            lines.append(f"### {r['station']}")
            if not r["bytes_identical"]:
                lines.append("- 逐字节回查失败：full/ 拷贝与 prompt_audit 源文件 sha256 不一致")
            if not r.get("extras_bytes_identical", True):
                lines.append("- 配套文件逐字节回查失败：extras 拷贝与源文件 sha256 不一致")
            if not r["blocks_paired"]:
                lines.append(f"- 块配对失败：原文 {r['blocks_original']} 块 vs 投影文件 {r['blocks_projected']} 块")
            if r["headings_missing_list"]:
                lines.append(f"- 缺标题：{r['headings_missing_list']}")
            if r["json_keys_missing_list"]:
                lines.append(f"- 缺键：{r['json_keys_missing_list']}")
            if r["numbers_missing_list"]:
                lines.append(f"- 缺数值：{r['numbers_missing_list']}")
    else:
        lines.append("**全部实例校验通过：逐字节一致、块配对一致，投影未丢标题、键路径与任何承诺保留的数值（承诺边界见上）。**")
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
