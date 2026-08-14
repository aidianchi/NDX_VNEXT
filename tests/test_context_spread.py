"""T47 摊开器的红灯测试。

守住三件事：
1. 三种落盘布局（标准 / investigation 前缀 / 嵌套时间戳）都能被发现——
   此前 integrated_adjudicator 与 controlled_investigation 正是因为布局特殊，
   连 prompt_inspector 都读不到它们的提示词（见 20260805_audit_verification/REPORT.md 三之二节）。
2. 投影不得丢键路径、不得丢数值、不得丢标题。
3. 全量导出必须是逐字节拷贝。

2026-08-08 骨架重修新增的红灯（每条对应一个已实锤的裂缝）：
4. 校验必须从落盘产物独立回查——篡改落盘投影/拷贝必须被抓到（此前自算自证）；
5. 数值正则必须看见 1–3 位整数（此前 "42→43" 偷换放行）；
6. 缩进 JSON 独立块必须被发现并校验（基线 run 37/103 块曾漏校验）；
7. 7–15 项非标量列表不得截断（此前 __omitted__ 为负、元素被重复）；
8. extras 按 attempt 归账且哈希必须落进 manifest；
9. 投影头部必须如实披露三处丢失边界（此前只披露两处，表格中段行被隐瞒）。
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent_analysis.context_spread import (
    _NUMBER_RE,
    _dropped_number_tokens,
    _iter_json_blocks,
    _project_value,
    discover_instances,
    project_prompt,
    spread_run,
    verify_instance_files,
)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _make_run(tmp_path: Path) -> Path:
    run = tmp_path / "run"
    audit = run / "prompt_audit"
    # 标准布局
    _write(audit / "L1" / "attempt_1.prompt.txt", "## System Message\n规则\n## User Message\n数据\n")
    _write(audit / "L1" / "attempt_1.payload.json", "{}")
    # investigation 布局（controlled_investigation）
    _write(audit / "controlled_investigation" / "inv_ab12.attempt_1.prompt.txt", "调查提示词\n")
    _write(audit / "controlled_investigation" / "inv_ab12.attempt_1.response.txt", "{}\n")
    _write(audit / "controlled_investigation" / "inv_cd34.attempt_2.prompt.txt", "调查提示词 2\n")
    # 嵌套时间戳布局（integrated_adjudicator）
    _write(
        audit / "integrated_adjudicator" / "20260730T165426Z" / "attempt_1.prompt.txt",
        "裁决提示词\n",
    )
    return run


def _spread_single(tmp_path: Path, prompt_text: str) -> tuple:
    """造一个只含 L1 一站的 run，摊开，返回 (full_prompt_path, projection_path, source_path)。"""
    run = tmp_path / "run"
    _write(run / "prompt_audit" / "L1" / "attempt_1.prompt.txt", prompt_text)
    spread_run(run, tmp_path / "spread")
    return (
        tmp_path / "spread" / "full" / "L1" / "attempt_1.prompt.txt",
        tmp_path / "spread" / "projected" / "L1" / "attempt_1.projection.md",
        run / "prompt_audit" / "L1" / "attempt_1.prompt.txt",
    )


# ---------------------------------------------------------------------------
# 旧防线（保留）：布局发现 / 投影保结构 / 散文逐字 / 逐字节拷贝 / 未知布局收编
# ---------------------------------------------------------------------------

def test_discover_covers_all_three_layouts(tmp_path: Path) -> None:
    run = _make_run(tmp_path)
    instances = discover_instances(run / "prompt_audit")
    layouts = {(i.stage, i.layout) for i in instances}
    assert ("L1", "standard") in layouts
    assert ("controlled_investigation", "investigation") in layouts
    assert ("integrated_adjudicator", "nested") in layouts
    assert len(instances) == 4  # 一站都不许缺


def test_projection_preserves_keys_numbers_and_headings(tmp_path: Path) -> None:
    payload = {
        "get_vxn": {"current_reading": "30.84，10年百分位87.2%，Spot/MA20=1.12"},
        "rows": [{"a": i, "note": "x" * 500} for i in range(40)],
        "series": [round(100.0 + i * 0.01, 4) for i in range(60)],
        "long_prose": "第一段。" * 100,
    }
    original = "## User Message\n### 材料\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n结尾散文\n"
    projected = project_prompt(original)
    orig_file = tmp_path / "orig.prompt.txt"
    proj_file = tmp_path / "proj.projection.md"
    _write(orig_file, original)
    _write(proj_file, projected)
    v = verify_instance_files(orig_file, proj_file)
    assert v["headings_missing"] == 0
    assert v["json_keys_missing"] == 0
    assert v["numbers_missing"] == 0, v["numbers_missing_list"]
    assert v["ok"] is True
    assert "30.84" in projected and "87.2" in projected
    # 同构标量表必须转表格投影并留 min/max 与总行数
    assert "__table_projection__" in projected and "__total__" in projected
    # 长标量序列必须留省略标记与 min/max
    assert "__omitted__" in projected and '"min"' in projected
    # 投影必须真的变小
    assert len(projected) < len(original)


def test_projection_leaves_prose_verbatim() -> None:
    prose = "## System Message\n你是解读员。铁律：事实和解读必须分开写。\n"
    assert project_prompt(prose) == prose


def test_spread_run_full_copy_is_byte_identical(tmp_path: Path) -> None:
    run = _make_run(tmp_path)
    manifest = spread_run(run, tmp_path / "spread")
    assert manifest["stage_dir_count"] == 3
    assert manifest["instance_count"] == 4
    for inst in manifest["instances"]:
        src = run / "prompt_audit" / inst["stage"]
        rel = Path(inst["instance"]) if inst["instance"] else Path()
        expected = (src / rel / f"attempt_{inst['attempt']}.prompt.txt")
        if inst["layout"] == "investigation":
            expected = src / f"{inst['instance']}.attempt_{inst['attempt']}.prompt.txt"
        copied = tmp_path / "spread" / "full" / inst["stage"] / rel / expected.name
        assert copied.read_bytes() == expected.read_bytes()
        assert inst["verification_ok"] is True
        # manifest 必须逐文件存 sha256（不许"算了就扔"），且能独立复算对上
        for fname, sha in inst["files"].items():
            assert len(sha) == 64
            assert sha == hashlib.sha256(copied.parent.joinpath(fname).read_bytes()).hexdigest()
        assert inst["projection_sha256"] == hashlib.sha256(
            (tmp_path / "spread" / "projected" / inst["stage"] / rel / inst["projection_file"]).read_bytes()
        ).hexdigest()
    # 校验留证文件必须生成且全部通过
    report = (tmp_path / "spread" / "projection_verification.md").read_text(encoding="utf-8")
    assert "全部实例校验通过" in report


def test_unknown_layout_is_collected_not_dropped(tmp_path: Path) -> None:
    run = tmp_path / "run"
    _write(run / "prompt_audit" / "weird" / "odd_name.prompt.txt", "x\n")
    instances = discover_instances(run / "prompt_audit")
    assert len(instances) == 1
    assert instances[0].layout == "unknown"


# ---------------------------------------------------------------------------
# 新红灯 4：校验必须从落盘产物独立回查——篡改落盘文件必须被抓到
# ---------------------------------------------------------------------------

def test_verify_catches_short_integer_swap_on_disk(tmp_path: Path) -> None:
    """裂缝(a)+(b) 的红灯：把落盘投影里的 42 偷换成 43。
    旧校验自算自证 + 正则看不见短整数，会放行；新校验必须抓。"""
    payload = {"alpha": {"beta": 42, "gamma": 19.46}, "note": "x" * 300}
    prompt = "## 任务\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    full_path, proj_path, source = _spread_single(tmp_path, prompt)
    tampered = proj_path.read_text(encoding="utf-8").replace('"beta": 42', '"beta": 43')
    assert tampered != proj_path.read_text(encoding="utf-8")
    proj_path.write_text(tampered, encoding="utf-8")
    v = verify_instance_files(full_path, proj_path, source)
    assert v["ok"] is False
    assert "42" in v["numbers_missing_list"]


def test_verify_catches_deleted_key_on_disk(tmp_path: Path) -> None:
    """裂缝(a) 的红灯：从落盘投影里删掉一个键（值为短整数，避开数值兜底）。
    旧键校验把 _project_value 再算一遍跟自己比，删了也发现不了；新校验必须抓。"""
    payload = {"alpha": {"beta": 42, "gamma": 7}, "note": "x" * 300}
    prompt = "## 任务\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    full_path, proj_path, source = _spread_single(tmp_path, prompt)
    lines = proj_path.read_text(encoding="utf-8").split("\n")
    tampered = "\n".join(ln for ln in lines if '"beta"' not in ln)
    proj_path.write_text(tampered, encoding="utf-8")
    v = verify_instance_files(full_path, proj_path, source)
    assert v["ok"] is False
    assert any("beta" in k for k in v["json_keys_missing_list"])


def test_verify_catches_deleted_block_on_disk(tmp_path: Path) -> None:
    """块配对红线：从落盘投影里删掉一整块 JSON，块数不一致必须报。"""
    block_a = json.dumps({"a": 1, "pad": "甲" * 150}, ensure_ascii=False, indent=2)
    block_b = json.dumps({"b": 2, "pad": "乙" * 150}, ensure_ascii=False, indent=2)
    prompt = "## 材料A\n" + block_a + "\n## 材料B\n" + block_b + "\n"
    full_path, proj_path, source = _spread_single(tmp_path, prompt)
    projected = proj_path.read_text(encoding="utf-8")
    # 投影文件里第二块是机器生成的投影（含 "b": 2），整段删掉
    marker = projected.index('"b": 2')
    start = projected.rindex("{", 0, marker)
    depth = 0
    for i in range(start, len(projected)):
        if projected[i] == "{":
            depth += 1
        elif projected[i] == "}":
            depth -= 1
            if depth == 0:
                proj_path.write_text(projected[:start] + projected[i + 1:], encoding="utf-8")
                break
    v = verify_instance_files(full_path, proj_path, source)
    assert v["ok"] is False
    assert v["blocks_paired"] is False


def test_verify_catches_tampered_full_copy(tmp_path: Path) -> None:
    """逐字节红线：full/ 落盘拷贝被改动，与源文件 sha256 比对必须报。"""
    full_path, proj_path, source = _spread_single(tmp_path, "## 任务\n材料\n")
    full_path.write_text("## 任务\n材料（被篡改）\n", encoding="utf-8")
    v = verify_instance_files(full_path, proj_path, source)
    assert v["bytes_identical"] is False
    assert v["ok"] is False


# ---------------------------------------------------------------------------
# 新红灯 5：数值正则边界——短整数可见，标识符内的数字不算数值
# ---------------------------------------------------------------------------

def test_number_regex_boundaries() -> None:
    tokens = lambda s: {m.group(0) for m in _NUMBER_RE.finditer(s)}
    # 1–3 位整数必须可见（旧正则 \d{4,} 全漏）
    assert "42" in tokens("占比 42%")
    assert "75" in tokens("加息 75bp")
    assert "7" in tokens("共 7 条事件")
    # 小数、负号、科学计数法
    assert "19.46" in tokens("PE 19.46")
    assert "-0.03" in tokens(json.dumps(-0.03))
    assert tokens(json.dumps(1e-5)) == {"1e-05"}
    # 标识符内的数字不是数值
    assert tokens("attempt_1") == set()
    assert tokens("sha256") == set()
    assert tokens("L1") == set()
    assert tokens("v1.2") == set()
    # 紧凑时间戳首段算日期数值 token（两边逐字出现，口径一致）；
    # 字母后面的数字段仍被排除（标识符碎片）
    assert tokens("20260730T165426Z") == {"20260730"}
    # 日期散文照常（逐字保留的散文里它们本来就在）
    assert {"2026", "07", "31"} <= tokens("2026-07-31")


# ---------------------------------------------------------------------------
# 新红灯 6：缩进 JSON 独立块必须被发现并校验
# ---------------------------------------------------------------------------

def test_indented_json_blocks_are_discovered_and_verified(tmp_path: Path) -> None:
    """基线 run 有 37/103 个缩进独立块曾被旧校验跳过（raw_decode 不吃前导空白）。"""
    inner = json.dumps({"delta": 88, "pad": "丙" * 150}, ensure_ascii=False, indent=2)
    indented = "\n".join("    " + ln for ln in inner.split("\n"))
    prompt = "## 材料\n下面是数据：\n" + indented + "\n结尾\n"
    blocks = _iter_json_blocks(prompt)
    assert len(blocks) == 1  # 缩进块必须被发现，且只算一次
    full_path, proj_path, source = _spread_single(tmp_path, prompt)
    v = verify_instance_files(full_path, proj_path, source)
    assert v["ok"] is True
    assert v["blocks_original"] == 1 and v["blocks_projected"] == 1
    # 篡改缩进块里的数值必须被抓
    tampered = proj_path.read_text(encoding="utf-8").replace('"delta": 88', '"delta": 89')
    proj_path.write_text(tampered, encoding="utf-8")
    v2 = verify_instance_files(full_path, proj_path, source)
    assert v2["ok"] is False
    assert "88" in v2["numbers_missing_list"]


# ---------------------------------------------------------------------------
# 新红灯 7：7–15 项非标量列表不得截断
# ---------------------------------------------------------------------------

def test_nonscalar_list_between_7_and_15_is_kept_whole() -> None:
    """旧实现：10 项混合列表被截成"头 10 + 标记 + 尾 5"，__omitted__ = -5，元素重复。"""
    mixed = [{"a": i} if i % 3 == 0 else i for i in range(10)]
    projected = _project_value(mixed)
    assert len(projected) == 10
    assert projected == mixed  # 不得有 __omitted__ 标记、不得重复元素
    assert _dropped_number_tokens(mixed) == set()  # 丢失收集器同一切口
    # 16 项才截断，且 __omitted__ 必须为正
    bigger = [{"a": i} if i % 3 == 0 else i for i in range(16)]
    p2 = _project_value(bigger)
    markers = [x for x in p2 if isinstance(x, dict) and "__omitted__" in x]
    assert len(markers) == 1
    assert markers[0]["__omitted__"] == 1
    assert len(p2) == 16  # 头 10 + 标记 1 + 尾 5
    # 中段含结构化元素则不截断：键路径承诺是全覆盖，中段 dict 的键无法留痕
    nested = list(range(16))
    nested[10] = {"b": 1}  # 头 10 尾 5 之外的中段位置
    p3 = _project_value(nested)
    assert len(p3) == 16
    assert not any(isinstance(x, dict) and "__omitted__" in x for x in p3)
    assert _dropped_number_tokens(nested) == set()
    # 头尾区段的 dict 照常保留，不挡截断
    tail_dict = list(range(16))
    tail_dict[12] = {"b": 1}
    p4 = _project_value(tail_dict)
    assert any(isinstance(x, dict) and x.get("__omitted__") == 1 for x in p4)
    assert p4[-1] == {"b": 1} or {"b": 1} in p4[-5:]
    # 长标量列表行为不变：>20 截断
    scalar = list(range(25))
    p4 = _project_value(scalar)
    assert any(isinstance(x, dict) and x.get("__omitted__") == 10 for x in p4)


# ---------------------------------------------------------------------------
# 新红灯 8：extras 按 attempt 归账 + 哈希落进 manifest
# ---------------------------------------------------------------------------

def test_investigation_extras_are_attempt_scoped(tmp_path: Path) -> None:
    """同一 inv 实例的 attempt_2 不得把 attempt_1 的文件算进自己名下（旧前缀只到实例级）。"""
    run = tmp_path / "run"
    audit = run / "prompt_audit"
    _write(audit / "controlled_investigation" / "inv_ab12.attempt_1.prompt.txt", "第一次\n")
    _write(audit / "controlled_investigation" / "inv_ab12.attempt_1.response.txt", "resp1\n")
    _write(audit / "controlled_investigation" / "inv_ab12.attempt_2.prompt.txt", "第二次\n")
    _write(audit / "controlled_investigation" / "inv_ab12.attempt_2.response.txt", "resp2\n")
    manifest = spread_run(run, tmp_path / "spread")
    inst2 = next(i for i in manifest["instances"] if i["attempt"] == 2)
    assert set(inst2["files"]) == {"inv_ab12.attempt_2.prompt.txt", "inv_ab12.attempt_2.response.txt"}


# ---------------------------------------------------------------------------
# 新红灯 9：投影头部如实披露三处丢失边界
# ---------------------------------------------------------------------------

def test_header_discloses_three_loss_boundaries(tmp_path: Path) -> None:
    """旧头部只说两处（散文中段、标量序列中段），同构标量表的中段行被隐瞒。"""
    payload = {"rows": [{"a": i, "b": i * 1.5} for i in range(40)]}
    prompt = "## 材料\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    _, proj_path, _ = _spread_single(tmp_path, prompt)
    header = proj_path.read_text(encoding="utf-8").split("---")[0]
    assert "三处" in header
    assert "同构标量表" in header
    assert "中段" in header


# ---------------------------------------------------------------------------
# 附带防线：重序列化表示差异不得误报（19.460 → 19.46）
# ---------------------------------------------------------------------------

def test_float_repr_normalization_no_false_positive(tmp_path: Path) -> None:
    block = '{"pe": 19.460, "name": "' + "x" * 200 + '", "count": 3}'
    prompt = "## 材料\n" + block + "\n"
    full_path, proj_path, source = _spread_single(tmp_path, prompt)
    v = verify_instance_files(full_path, proj_path, source)
    assert v["ok"] is True, v["numbers_missing_list"]
    assert v["numbers_missing"] == 0
