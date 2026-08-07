"""T47 摊开器的红灯测试。

守住三件事：
1. 三种落盘布局（标准 / investigation 前缀 / 嵌套时间戳）都能被发现——
   此前 integrated_adjudicator 与 controlled_investigation 正是因为布局特殊，
   连 prompt_inspector 都读不到它们的提示词（见 20260805_audit_verification/REPORT.md 三之二节）。
2. 投影不得丢键路径、不得丢数值、不得丢标题。
3. 全量导出必须是逐字节拷贝。
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent_analysis.context_spread import (
    discover_instances,
    project_prompt,
    spread_run,
    verify_projection,
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


def test_discover_covers_all_three_layouts(tmp_path: Path) -> None:
    run = _make_run(tmp_path)
    instances = discover_instances(run / "prompt_audit")
    layouts = {(i.stage, i.layout) for i in instances}
    assert ("L1", "standard") in layouts
    assert ("controlled_investigation", "investigation") in layouts
    assert ("integrated_adjudicator", "nested") in layouts
    assert len(instances) == 4  # 一站都不许缺


def test_projection_preserves_keys_numbers_and_headings() -> None:
    payload = {
        "get_vxn": {"current_reading": "30.84，10年百分位87.2%，Spot/MA20=1.12"},
        "rows": [{"a": i, "note": "x" * 500} for i in range(40)],
        "series": [round(100.0 + i * 0.01, 4) for i in range(60)],
        "long_prose": "第一段。" * 100,
    }
    original = "## User Message\n### 材料\n" + json.dumps(payload, ensure_ascii=False, indent=2) + "\n结尾散文\n"
    projected = project_prompt(original)
    v = verify_projection(original, projected)
    assert v["headings_missing"] == 0
    assert v["json_keys_missing"] == 0
    assert v["numbers_missing"] == 0, v["numbers_missing_list"]
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
    # 校验留证文件必须生成且全部通过
    report = (tmp_path / "spread" / "projection_verification.md").read_text(encoding="utf-8")
    assert "全部实例三重校验通过" in report


def test_unknown_layout_is_collected_not_dropped(tmp_path: Path) -> None:
    run = tmp_path / "run"
    _write(run / "prompt_audit" / "weird" / "odd_name.prompt.txt", "x\n")
    instances = discover_instances(run / "prompt_audit")
    assert len(instances) == 1
    assert instances[0].layout == "unknown"
