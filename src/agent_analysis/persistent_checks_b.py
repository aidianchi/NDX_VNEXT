"""T47 常设检查 B 包（PC-11 ~ PC-27）。

只读机器检查：输入 = 一次 run 的落盘产物目录（run_dir），输出 = 结构化结果列表。
不调 LLM、不联网、不写 run_dir；模块 import 无副作用。

每条结果：
    {"check_id": "PC-xx", "name": "...", "passed": bool,
     "detail": "...", "evidence": "..."}

原始发现依据：
    investigation_reports/20260806_t47_context_review/03_根本审查总报告.md §3
    的 B4/B5/B7/B8/B11/B12/B13/C3/C5/C12 与 §8 第 20 项；
    PC-21~26 为 08-16 补病（B3/B6/B11 另一半/C1/C2/C4），B14 无法机器化（见注释）；
    PC-27 为 08-19 O17（IA 挑战数据判决亮灯：只有 challenged_by_data 行才亮，当日收窄）。
按"病出现 = failed"反写。
"""

from __future__ import annotations

import ast
import json
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

_REPO_ROOT = Path(__file__).resolve().parents[2]

# PC-15：high_severity_* 容器内 severity 允许值（任务书口径：high/medium；low 或缺失 → failed）。
_ALLOWED_HIGH_SEVERITY = {"high", "medium"}

# PC-16：下游站产物键（03 报告 B12 点名，含 run 目录常见产物名）。
_DOWNSTREAM_ARTIFACT_KEYS = {
    "thesis_draft",
    "critique",
    "risk_boundary_report",
    "analysis_revised",
    "final_adjudication",
    "event_adversarial_review",
    "event_layer_summary",
    "event_market_validation",
    "integrated_synthesis_report",
    "outcome_review_report",
    "pure_data_report",
    "analysis_packet",
}

# PC-18：L4 available 但数据陈旧的判定阈值。方向按 03 报告 C3（AMZN 最新季距
# effective_date 约 17 个月仍标 available=陈旧）；"365 天"是施工任务书 B 的收口
# 阈值，不是 03 原文数字，勿当作 03 报告引用。
_STALE_DAYS = 365

# PC-20②：真实错误定位的指纹。FIX-1 的输出形如：
#   "JSON 语法错误定位: ...（提取出的 JSON 块内第 3 行第 5 列）。"
# 契约/模式校验错误的真实定位是字段路径（形如 L1.get_vix.metric）或 pydantic
# 的 "validation error" 反馈——JSON 行/列号只有解析错误才有，两类都算数。
# 内容规则违例（禁句、数字锚定等）的真实定位是规则身份——统一以
# "dotted.rule.path: 消息" 前缀发放（形如 event_card.direction_overreach: ...）。
_LOCALIZATION_RE = re.compile(
    r"JSONDecodeError"
    r"|第\s*\d+\s*行第\s*\d+\s*列"
    r"|line\s+\d+\s*,\s*column\s+\d+|line\s+\d+\s+column\s+\d+"
    r"|\bL[1-5]\.[A-Za-z_][\w.]*"
    r"|validation error"
    r"|\b[a-z][a-z0-9_]*(?:\.[a-z0-9_]+)+:",
    re.IGNORECASE,
)

_LAYERS = ["L1", "L2", "L3", "L4", "L5"]


# --------------------------------------------------------------------------
# 基础工具
# --------------------------------------------------------------------------

def _make_result(check_id: str, name: str, passed: bool, detail: str, evidence: str) -> Dict[str, Any]:
    return {
        "check_id": check_id,
        "name": name,
        "passed": passed,
        "detail": detail,
        "evidence": evidence,
    }


def _load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _read_text(path: Path) -> str:
    with path.open("r", encoding="utf-8") as fh:
        return fh.read()


def _latest_payload_path(run_dir: Path, station: str) -> Optional[Path]:
    """返回 prompt_audit/<station>/attempt_*.payload.json 中 attempt 号最大的文件。"""
    stage_dir = run_dir / "prompt_audit" / station
    if not stage_dir.is_dir():
        return None
    payloads = sorted(stage_dir.glob("attempt_*.payload.json"))
    if not payloads:
        return None

    def attempt_no(p: Path) -> int:
        m = re.search(r"attempt_(\d+)\.payload\.json$", p.name)
        return int(m.group(1)) if m else -1

    return max(payloads, key=attempt_no)


def _latest_prompt_path(run_dir: Path, station: str) -> Optional[Path]:
    stage_dir = run_dir / "prompt_audit" / station
    if not stage_dir.is_dir():
        return None
    prompts = sorted(stage_dir.glob("attempt_*.prompt.txt"))
    if not prompts:
        return None

    def attempt_no(p: Path) -> int:
        m = re.search(r"attempt_(\d+)\.prompt\.txt$", p.name)
        return int(m.group(1)) if m else -1

    return max(prompts, key=attempt_no)


def _parse_date(value: Any) -> Optional[date]:
    """从字符串中提取日期；支持 ISO 与 '30 July 2026' 两类写法。"""
    if not isinstance(value, str):
        return None
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", value)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            return None
    m = re.search(r"(\d{1,2})\s+([A-Za-z]{3,9})\s+(\d{4})", value)
    if m:
        months = {
            "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
            "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
        }
        mon = months.get(m.group(2)[:3].lower())
        if mon:
            try:
                return date(int(m.group(3)), mon, int(m.group(1)))
            except ValueError:
                return None
    return None


def _run_data_date(run_dir: Path) -> Optional[date]:
    """run 数据日期：优先取顶层 context_brief.json 的 data_summary。"""
    cb = run_dir / "context_brief.json"
    if cb.is_file():
        try:
            d = _load_json(cb)
            if isinstance(d, dict):
                parsed = _parse_date(d.get("data_summary", ""))
                if parsed:
                    return parsed
        except Exception:
            pass
    # 回退：L1 payload 内的 context_brief.data_summary
    for layer in _LAYERS:
        pl = _load_layer_payload(run_dir, layer)
        if not pl:
            continue
        cb_in = pl.get("context_brief") or {}
        if isinstance(cb_in, dict):
            parsed = _parse_date(cb_in.get("data_summary", ""))
            if parsed:
                return parsed
    return None


def _load_layer_payload(run_dir: Path, layer: str) -> Optional[Dict[str, Any]]:
    """加载 L1-L5 最新 attempt 的 payload 字典（payload 字段内容）。"""
    path = _latest_payload_path(run_dir, layer)
    if not path:
        return None
    try:
        d = _load_json(path)
    except Exception:
        return None
    if isinstance(d, dict):
        pl = d.get("payload")
        if isinstance(pl, dict):
            return pl
    return None


def _iter_json_paths(obj: Any, path: str = "") -> Iterable[Tuple[str, Any]]:
    """递归遍历 JSON 树，产出 (路径, 值)。"""
    if isinstance(obj, dict):
        for key, value in obj.items():
            child = f"{path}.{key}" if path else key
            yield child, value
            yield from _iter_json_paths(value, child)
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            child = f"{path}[{idx}]"
            yield child, value
            yield from _iter_json_paths(value, child)


def _is_empty(value: Any) -> bool:
    if value is None:
        return True
    if isinstance(value, (str, list, dict)) and len(value) == 0:
        return True
    return False


def _basename(path: str) -> str:
    return path.rsplit(".", 1)[-1]


# --------------------------------------------------------------------------
# PC-11
# --------------------------------------------------------------------------

def _extract_example_function_ids(prompt_text: str) -> List[str]:
    """提取 prompt 正文中'正确示例/输出示例'点名的指标 function_id。

    覆盖两种形态：
    1. Few-shot 段头 `### Example: <function_id>`；
    2. `### 结构示例` 段内 `"function_id": "..."` 与 `covered_function_ids` 数组。
    """
    ids: List[str] = []
    for m in re.finditer(r"^###\s*Example:\s*([A-Za-z0-9_]+)", prompt_text, re.MULTILINE):
        ids.append(m.group(1))

    block = re.search(r"###\s*结构示例\s*\n(.*?)(?=\n#\s|\Z)", prompt_text, re.DOTALL)
    if block:
        section = block.group(1)
        ids.extend(re.findall(r'"function_id"\s*:\s*"([A-Za-z0-9_]+)"', section))
        cov = re.search(r'"covered_function_ids"\s*:\s*\[(.*?)\]', section, re.DOTALL)
        if cov:
            ids.extend(re.findall(r'"([A-Za-z0-9_]+)"', cov.group(1)))
    return ids


def _check_pc11(run_dir: Path) -> Dict[str, Any]:
    violations: List[str] = []
    checked_layers = 0
    for layer in _LAYERS:
        prompt_path = _latest_prompt_path(run_dir, layer)
        pl = _load_layer_payload(run_dir, layer)
        if not prompt_path or pl is None:
            violations.append(f"{layer}: 缺失 prompt 或 payload artifact")
            continue
        checked_layers += 1
        prompt_text = _read_text(prompt_path)
        example_ids = set(_extract_example_function_ids(prompt_text))
        if not example_ids:
            continue

        allowed: set[str] = set()
        lrd = pl.get("layer_raw_data")
        if isinstance(lrd, dict):
            allowed.update(lrd.keys())
        lf = pl.get("layer_facts") or {}
        if isinstance(lf, dict):
            km = lf.get("key_metrics")
            if isinstance(km, list):
                allowed.update(str(x) for x in km)
            cs = lf.get("core_signals")
            if isinstance(cs, list):
                for item in cs:
                    if isinstance(item, dict) and item.get("metric"):
                        allowed.add(str(item["metric"]))

        missing = sorted(example_ids - allowed)
        if missing:
            violations.append(f"{layer}: 示例点名 {sorted(example_ids)} 中本层不存在 {missing}")

    passed = not violations
    return _make_result(
        "PC-11",
        "输出示例指标本层存在性（B4）",
        passed,
        "全部层的输出/正确示例点名指标均在本层存在" if passed else "；".join(violations),
        f"prompt_audit/{{L1-L5}}/attempt_*.prompt.txt 示例段 vs payload.layer_raw_data/key_metrics/core_signals；检查层数 {checked_layers}",
    )


# --------------------------------------------------------------------------
# PC-12
# --------------------------------------------------------------------------

def _check_pc12(run_dir: Path) -> Dict[str, Any]:
    run_date = _run_data_date(run_dir)
    if run_date is None:
        return _make_result(
            "PC-12", "manual_overrides 陈旧占位日期（B5）", False,
            "无法确定 run 数据日期（context_brief.json 缺失或不可解析）",
            "context_brief.json:data_summary",
        )
    violations: List[str] = []
    for layer in _LAYERS:
        pl = _load_layer_payload(run_dir, layer)
        if pl is None:
            violations.append(f"{layer}: 缺失 payload")
            continue
        mo = pl.get("manual_overrides")
        if not isinstance(mo, dict):
            continue
        raw_date = mo.get("date")
        if not isinstance(raw_date, str):
            continue
        d = _parse_date(raw_date)
        stale = False
        reason = ""
        if d is None:
            stale = True
            reason = f"不可解析日期 {raw_date!r}"
        elif d.year == 2022 or (run_date - d).days > _STALE_DAYS:
            stale = True
            reason = f"{d.isoformat()}（距 run 数据日期 {(run_date - d).days} 天）"
        if stale:
            violations.append(f"{layer}: manual_overrides.date={raw_date}（{reason}）")

    passed = not violations
    return _make_result(
        "PC-12",
        "manual_overrides 陈旧占位日期（B5）",
        passed,
        "manual_overrides 无 2022 年/一年以上陈旧占位日期" if passed else "；".join(violations),
        f"prompt_audit/{{L1-L5}}/attempt_*.payload.json:payload.manual_overrides.date；run 数据日期 {run_date.isoformat()}",
    )


# --------------------------------------------------------------------------
# PC-13
# --------------------------------------------------------------------------

def _percentile_entries(obj: Any, path: str = "") -> Iterable[Tuple[str, float, bool]]:
    """产出 (路径, 数值, 是否带 unit/scale 声明)。"""
    if isinstance(obj, dict):
        for key, value in obj.items():
            child = f"{path}.{key}" if path else key
            if re.search(r"percentile", key, re.IGNORECASE):
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    declared = _has_scale_declaration(obj, key)
                    yield child, float(value), declared
            yield from _percentile_entries(value, child)
    elif isinstance(obj, list):
        for idx, value in enumerate(obj):
            child = f"{path}[{idx}]"
            yield from _percentile_entries(value, child)


def _has_scale_declaration(parent: dict, key: str) -> bool:
    for sibling, value in parent.items():
        if sibling == key:
            continue
        name = sibling.lower()
        if "scale" in name:
            return True
        if "percentile_unit" in name:
            return True
        if name == "unit" and isinstance(value, str):
            low = value.lower()
            if "percentile" in low or "0-1" in low or "0-100" in low:
                return True
    return False


def _check_pc13(run_dir: Path) -> Dict[str, Any]:
    violations: List[str] = []
    for layer in _LAYERS:
        entries: List[Tuple[str, float, bool]] = []
        pl = _load_layer_payload(run_dir, layer)
        if pl is not None:
            entries.extend(_percentile_entries(pl))
        card_path = run_dir / "layer_cards" / f"{layer}.json"
        if card_path.is_file():
            try:
                entries.extend(_percentile_entries(_load_json(card_path)))
            except Exception:
                pass

        if not entries:
            continue
        scale_01 = [(p, v) for p, v, _ in entries if v <= 1.0]
        scale_100 = [(p, v) for p, v, _ in entries if v > 1.0]
        undeclared = [p for p, _, declared in entries if not declared]
        if scale_01 and scale_100 and undeclared:
            sample_01 = scale_01[:3]
            sample_100 = scale_100[:3]
            violations.append(
                f"{layer}: 同时出现 0-1 口径 {sample_01} 与 0-100 口径 {sample_100}，"
                f"未带 unit/scale 声明的 percentile 字段 {len(undeclared)} 个"
            )

    passed = not violations
    return _make_result(
        "PC-13",
        "percentile 取值域混用（B7）",
        passed,
        "各层 percentile 类字段无 0-1/0-100 双口径混用" if passed else "；".join(violations),
        "prompt_audit/{L1-L5}/attempt_*.payload.json + layer_cards/{L1-L5}.json",
    )


# --------------------------------------------------------------------------
# PC-14
# --------------------------------------------------------------------------

_DATE_KEYS = {"date", "data_date", "visible_date", "effective_date", "as_of_date"}


def _indicator_dates_from_payload(pl: Dict[str, Any]) -> List[Tuple[str, str]]:
    """收集层 payload 中指标级 date/data_date/visible_date 等字段。

    只取指标层（layer_raw_data.* 与 layer_facts.core_signals[].value 的顶层），
    不深入 raw_series 这类行级明细，避免把每一行历史日期当成指标日期。
    """
    out: List[Tuple[str, str]] = []
    lrd = pl.get("layer_raw_data")
    if isinstance(lrd, dict):
        for fid, item in lrd.items():
            if not isinstance(item, dict):
                continue
            for key in ("date", "data_date", "visible_date", "effective_date", "as_of_date"):
                if isinstance(item.get(key), str):
                    out.append((f"layer_raw_data.{fid}.{key}", item[key]))
            dq = item.get("data_quality")
            if isinstance(dq, dict):
                for key in _DATE_KEYS:
                    if isinstance(dq.get(key), str):
                        out.append((f"layer_raw_data.{fid}.data_quality.{key}", dq[key]))
            value = item.get("value")
            if isinstance(value, dict):
                for key in _DATE_KEYS:
                    if isinstance(value.get(key), str):
                        out.append((f"layer_raw_data.{fid}.value.{key}", value[key]))

    lf = pl.get("layer_facts") or {}
    if isinstance(lf, dict):
        cs = lf.get("core_signals")
        if isinstance(cs, list):
            for idx, item in enumerate(cs):
                if not isinstance(item, dict):
                    continue
                value = item.get("value")
                if isinstance(value, dict):
                    for key in _DATE_KEYS:
                        if isinstance(value.get(key), str):
                            out.append((f"layer_facts.core_signals[{idx}].value.{key}", value[key]))
    return out


# B8 修复（2026-08-16）：brief 必须声明"各指标实际数据日期以各自 data_quality 为准"。
# 检查口径从"所有指标日期 == brief 日期"改为：不晚于运行时点即合法（月度指标滞后属正常），
# 晚于运行时点 = 未来数据泄漏。
_BRIEF_DATE_DISCLAIMER = "各指标实际数据日期以各自 data_quality"


def _check_pc14(run_dir: Path) -> Dict[str, Any]:
    violations: List[str] = []
    checked_layers = 0
    for layer in _LAYERS:
        pl = _load_layer_payload(run_dir, layer)
        if pl is None:
            violations.append(f"{layer}: 缺失 payload")
            continue
        checked_layers += 1
        cb = pl.get("context_brief") or {}
        brief_text = cb.get("data_summary", "") if isinstance(cb, dict) else ""
        brief_date = _parse_date(brief_text)
        if brief_date is None:
            violations.append(f"{layer}: context_brief.data_summary 不可解析")
            continue
        if _BRIEF_DATE_DISCLAIMER not in brief_text:
            violations.append(
                f"{layer}: context_brief 未声明'各指标实际数据日期以各自 data_quality 为准'"
            )
        bad: List[str] = []
        for path, raw in _indicator_dates_from_payload(pl):
            d = _parse_date(raw)
            if d is None:
                continue
            if d > brief_date:
                bad.append(f"{path}={raw}（晚于运行时点 {brief_date.isoformat()}）")
        if bad:
            violations.append(f"{layer}: 指标日期晚于运行时点（未来数据泄漏） {bad[:8]}{'...' if len(bad) > 8 else ''}")

    passed = not violations
    return _make_result(
        "PC-14",
        "context_brief 日期 vs 指标日期（B8）",
        passed,
        "context_brief 声明运行时点+各指标自查口径，且无晚于运行时点的指标日期" if passed else "；".join(violations),
        f"prompt_audit/{{L1-L5}}/attempt_*.payload.json；检查层数 {checked_layers}",
    )


# --------------------------------------------------------------------------
# PC-15
# --------------------------------------------------------------------------

def _check_pc15(run_dir: Path) -> Dict[str, Any]:
    packet_path = run_dir / "synthesis_packet.json"
    if not packet_path.is_file():
        return _make_result(
            "PC-15", "high_severity 容器名与 severity 字段一致性（B11）", False,
            "缺失 artifact: synthesis_packet.json",
            "synthesis_packet.json",
        )
    try:
        packet = _load_json(packet_path)
    except Exception as exc:
        return _make_result(
            "PC-15", "high_severity 容器名与 severity 字段一致性（B11）", False,
            f"check_error:{type(exc).__name__}:{exc}",
            "synthesis_packet.json",
        )
    if not isinstance(packet, dict):
        return _make_result(
            "PC-15", "high_severity 容器名与 severity 字段一致性（B11）", False,
            "check_error:synthesis_packet.json 顶层不是对象",
            "synthesis_packet.json",
        )

    violations: List[str] = []
    inspected: List[str] = []
    for key, value in packet.items():
        if not key.startswith("high_severity"):
            continue
        if not isinstance(value, list):
            violations.append(f"{key}: 不是数组（{type(value).__name__}）")
            continue
        inspected.append(f"{key}={len(value)}条")
        for idx, item in enumerate(value):
            if not isinstance(item, dict):
                violations.append(f"{key}[{idx}]: 不是对象")
                continue
            sev = item.get("severity")
            if sev is None:
                violations.append(f"{key}[{idx}] {item.get('conflict_id', '?')}: severity 缺失")
            elif sev not in _ALLOWED_HIGH_SEVERITY:
                violations.append(f"{key}[{idx}] {item.get('conflict_id', '?')}: severity={sev!r}（只允许 high/medium）")

    passed = not violations
    return _make_result(
        "PC-15",
        "high_severity 容器名与 severity 字段一致性（B11）",
        passed,
        "high_severity_* 容器内 severity 均为 high/medium" if passed else "；".join(violations),
        "synthesis_packet.json:high_severity_*；" + ("，".join(inspected) if inspected else "无 high_severity 容器"),
    )


# --------------------------------------------------------------------------
# PC-16
# --------------------------------------------------------------------------

def _check_pc16(run_dir: Path) -> Dict[str, Any]:
    stage_root = run_dir / "prompt_audit"
    if not stage_root.is_dir():
        return _make_result(
            "PC-16", "他站产物 null 占位/禁用标记进输入（B12）", False,
            "缺失 artifact: prompt_audit/ 目录",
            "prompt_audit/",
        )
    violations: List[str] = []
    stations_checked = 0
    for station_dir in sorted(stage_root.iterdir()):
        if not station_dir.is_dir():
            continue
        station = station_dir.name
        payload_path = _latest_payload_path(run_dir, station)
        if not payload_path:
            continue
        stations_checked += 1
        try:
            d = _load_json(payload_path)
        except Exception:
            continue
        pl = d.get("payload") if isinstance(d, dict) else None
        if not isinstance(pl, dict):
            continue
        for path, value in _iter_json_paths(pl):
            base = _basename(path)
            # 下游站产物键以非空值出现
            if base in _DOWNSTREAM_ARTIFACT_KEYS and not _is_empty(value):
                violations.append(f"{station}:{path} 下游产物键非空（{type(value).__name__}）")
            # _disabled 标记键 / forbidden_as_core_ref 标记键以非空值出现。
            # 注意：data_quality.forbidden_use（do_not_estimate_or_fabricate）是合法的数据质量纪律；
            # counter_thesis 的 forbidden_context_refs 是反方独立性边界的合法存在（机器化
            # "禁止读 thesis_draft/analysis_revised/final_adjudication"），都不属于 B12 病。
            marker_key = (
                "_disabled" in base.lower()
                or base.lower() == "forbidden_as_core_ref"
            )
            if marker_key and not _is_empty(value):
                violations.append(f"{station}:{path} 禁用标记键非空（{type(value).__name__}）")
            # 字符串值内藏 forbidden_as_core_ref 标记（如 usage_rule）
            if isinstance(value, str) and "forbidden_as_core_ref" in value.lower():
                violations.append(f"{station}:{path} 含 forbidden_as_core_ref 标记")

    passed = not violations
    detail = "未发现他站产物键/禁用标记以非空值进输入" if passed else "；".join(violations)
    if not passed:
        detail += "（旧 run 的 reviser/final pricing_expectation_ledger 属 C6 前形态，重跑基线后应消失）"
    return _make_result(
        "PC-16",
        "他站产物 null 占位/禁用标记进输入（B12）",
        passed,
        detail,
        f"prompt_audit/*/attempt_*.payload.json；检查站数 {stations_checked}",
    )


# --------------------------------------------------------------------------
# PC-17
# --------------------------------------------------------------------------

def _check_pc17(run_dir: Path) -> Dict[str, Any]:
    prompt_path = _latest_prompt_path(run_dir, "bridge")
    if not prompt_path:
        return _make_result(
            "PC-17", "bridge 冲突矩阵行完整性（B13）", False,
            "缺失 artifact: prompt_audit/bridge/attempt_*.prompt.txt",
            "prompt_audit/bridge/",
        )
    prompt_text = _read_text(prompt_path)
    # 只取"冲突矩阵 A-M"之后 40 行内的表格行，避免误收正文其他单字母行。
    m = re.search(r"检查冲突矩阵\s*A-M", prompt_text)
    if not m:
        return _make_result(
            "PC-17", "bridge 冲突矩阵行完整性（B13）", False,
            "bridge prompt 中未找到'检查冲突矩阵 A-M'段落",
            f"{prompt_path.name}",
        )
    tail = prompt_text[m.end(): m.end() + 4000]
    rows = set()
    for line in tail.splitlines():
        mm = re.match(r"^\s*\|\s*([A-M])\s*\|", line)
        if mm:
            rows.add(mm.group(1))
    expected = set("ABCDEFGHIJKLM")
    missing = sorted(expected - rows)
    passed = not missing
    return _make_result(
        "PC-17",
        "bridge 冲突矩阵行完整性（B13）",
        passed,
        f"冲突矩阵 A-M 行完整（{''.join(sorted(rows))}）" if passed
        else f"冲突矩阵缺行：{missing}（现只有 {sorted(rows)}）；待装配点补全",
        f"{prompt_path.name}: 检查冲突矩阵 A-M 表格",
    )


# --------------------------------------------------------------------------
# PC-18
# --------------------------------------------------------------------------

def _buyback_rows(value: Dict[str, Any]) -> List[Tuple[str, List[Dict[str, Any]]]]:
    """返回 (位置名, 行列表)，覆盖回购明细的两种形态。"""
    out: List[Tuple[str, List[Dict[str, Any]]]] = []
    for form in ("per_company", "raw_quarterly_series"):
        form_obj = value.get(form)
        if isinstance(form_obj, dict):
            for company, info in form_obj.items():
                if isinstance(info, dict):
                    quarters = info.get("quarters")
                    if isinstance(quarters, list):
                        out.append((f"{form}.{company}.quarters", [q for q in quarters if isinstance(q, dict)]))
                elif isinstance(info, list):
                    out.append((f"{form}.{company}", [q for q in info if isinstance(q, dict)]))
    return out


def _check_pc18(run_dir: Path) -> Dict[str, Any]:
    pl = _load_layer_payload(run_dir, "L4")
    if pl is None:
        return _make_result(
            "PC-18", "L4 数据陈旧（C3）+ 回购逐字重复行（C5）", False,
            "缺失 artifact: prompt_audit/L4/attempt_*.payload.json",
            "prompt_audit/L4/",
        )
    run_date = _run_data_date(run_dir)
    if run_date is None:
        return _make_result(
            "PC-18", "L4 数据陈旧（C3）+ 回购逐字重复行（C5）", False,
            "无法确定 run 数据日期（context_brief.json 缺失或不可解析）",
            "context_brief.json:data_summary",
        )

    violations: List[str] = []
    lrd = pl.get("layer_raw_data")
    buyback = lrd.get("get_m7_buyback_flow") if isinstance(lrd, dict) else None
    buyback_value = buyback.get("value") if isinstance(buyback, dict) else None

    # C3：available 但数据陈旧。任务书原文写"晚于 run 数据日期（陈旧）"，与 03 报告 C3
    # 病定义（AMZN 最新季 2024Q4，早于 effective_date 约 17 个月仍标 available）不符；
    # 按病定义与代码实况实现为"早于 run 数据日期一年以上"。
    if isinstance(buyback_value, dict):
        per_company = buyback_value.get("per_company")
        if isinstance(per_company, dict):
            for company, info in per_company.items():
                if not isinstance(info, dict):
                    continue
                if info.get("availability") != "available":
                    continue
                latest = info.get("latest_period_end") or info.get("latest_calendar_quarter")
                d = _parse_date(latest)
                if d is None:
                    continue
                if (run_date - d).days > _STALE_DAYS:
                    violations.append(
                        f"回购 {company}: available 但最新数据 {d.isoformat()}，"
                        f"早于 run 数据日期 {(run_date - d).days} 天（> {_STALE_DAYS} 天）"
                    )
        # 指标级 available 数据日期同样按陈旧阈值扫一遍（防御性）
        for fid, item in lrd.items() if isinstance(lrd, dict) else []:
            if not isinstance(item, dict):
                continue
            if item.get("availability") != "available":
                continue
            dq = item.get("data_quality") if isinstance(item.get("data_quality"), dict) else {}
            d = _parse_date(dq.get("data_date") or (item.get("value") or {}).get("data_date") or item.get("date"))
            if d is None:
                continue
            if (run_date - d).days > _STALE_DAYS:
                violations.append(
                    f"指标 {fid}: available 但 data_date={d.isoformat()}，"
                    f"早于 run 数据日期 {(run_date - d).days} 天"
                )

    # C5：回购明细逐字重复行。
    if isinstance(buyback_value, dict):
        for location, rows in _buyback_rows(buyback_value):
            seen: Dict[str, int] = {}
            for idx, row in enumerate(rows):
                serialized = json.dumps(row, sort_keys=True, ensure_ascii=False, default=str)
                if serialized in seen:
                    amount = row.get("value_usd_bn", row.get("value_usd"))
                    violations.append(
                        f"回购逐字重复行 {location}[{seen[serialized]}] 与 [{idx}]"
                        f"（calendar_quarter={row.get('calendar_quarter')}, "
                        f"period_end={row.get('period_end')}, value={amount}）"
                    )
                else:
                    seen[serialized] = idx

    passed = not violations
    return _make_result(
        "PC-18",
        "L4 数据陈旧（C3）+ 回购逐字重复行（C5）",
        passed,
        "L4 available 数据新鲜且回购明细无逐字重复行" if passed else "；".join(violations[:10]),
        f"prompt_audit/L4/attempt_*.payload.json:layer_raw_data.get_m7_buyback_flow；run 数据日期 {run_date.isoformat()}",
    )


# --------------------------------------------------------------------------
# PC-19
# --------------------------------------------------------------------------

def _extract_canon_map(prompt_text: str, layer: str) -> Optional[Dict[str, str]]:
    m = re.search(
        r"###\s*IndicatorCanon\s+for\s+" + re.escape(layer) + r"\s*\n(.*?)(?=\n###\s|\n#\s|\Z)",
        prompt_text,
        re.DOTALL,
    )
    if not m:
        return None
    block = m.group(1).strip()
    try:
        arr = json.loads(block)
    except Exception:
        return None
    if not isinstance(arr, list):
        return None
    canon: Dict[str, str] = {}
    for entry in arr:
        if isinstance(entry, dict) and entry.get("function_id") and entry.get("metric_name"):
            canon[str(entry["function_id"])] = str(entry["metric_name"])
    return canon


def _check_pc19(run_dir: Path) -> Dict[str, Any]:
    mismatches: List[str] = []
    checked_layers = 0
    for layer in _LAYERS:
        prompt_path = _latest_prompt_path(run_dir, layer)
        pl = _load_layer_payload(run_dir, layer)
        if not prompt_path or pl is None:
            mismatches.append(f"{layer}: 缺失 prompt 或 payload")
            continue
        checked_layers += 1
        canon = _extract_canon_map(_read_text(prompt_path), layer)
        if canon is None:
            mismatches.append(f"{layer}: 无法解析 IndicatorCanon 段")
            continue
        lrd = pl.get("layer_raw_data")
        if not isinstance(lrd, dict):
            continue
        for fid, item in lrd.items():
            if not isinstance(item, dict):
                continue
            input_name = item.get("metric_name")
            canon_name = canon.get(fid)
            if canon_name is None:
                continue
            if input_name != canon_name:
                mismatches.append(f"{layer}.{fid}: canon={canon_name!r} vs input={input_name!r}")

    passed = not mismatches
    return _make_result(
        "PC-19",
        "canon 名 vs 输入 metric_name（C12）",
        passed,
        "各层 payload metric_name 与 IndicatorCanon 注册名一致" if passed else "；".join(mismatches[:12]),
        f"prompt_audit/{{L1-L5}}/attempt_*.prompt.txt IndicatorCanon 段 vs payload.layer_raw_data.*.metric_name；检查层数 {checked_layers}",
    )


# --------------------------------------------------------------------------
# PC-20
# --------------------------------------------------------------------------

def _collect_retry_feedbacks(run_dir: Path) -> List[Tuple[str, str]]:
    """收集所有非空 retry_feedback（来自各站 attempt_*.payload.json）。"""
    out: List[Tuple[str, str]] = []
    stage_root = run_dir / "prompt_audit"
    if not stage_root.is_dir():
        return out
    for payload_path in sorted(stage_root.glob("*/attempt_*.payload.json")):
        try:
            d = _load_json(payload_path)
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        fb = d.get("retry_feedback")
        if isinstance(fb, str) and fb.strip():
            out.append((payload_path.parent.name, fb))
    return out


def _count_collected_tests(test_file: Path) -> Optional[int]:
    """统计 pytest 收集数；优先静态 AST 计数，失败时退回 pytest --collect-only。"""
    try:
        tree = ast.parse(test_file.read_text(encoding="utf-8"))
        count = 0
        for node in tree.body:
            if isinstance(node, ast.FunctionDef) and node.name.startswith("test_"):
                count += 1
            elif isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
                for sub in node.body:
                    if isinstance(sub, ast.FunctionDef) and sub.name.startswith("test_"):
                        count += 1
        if count >= 0:
            return count
    except Exception:
        pass
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "pytest", "--collect-only", "-q", "-p", "no:cacheprovider", str(test_file)],
            capture_output=True,
            text=True,
            timeout=60,
        )
        m = re.search(r"(\d+)\s+tests?\s+collected", proc.stdout + proc.stderr)
        if m:
            return int(m.group(1))
    except Exception:
        pass
    return None


def _check_pc20(run_dir: Path, repo_root: Path = _REPO_ROOT) -> Dict[str, Any]:
    failures: List[str] = []

    # ① ESS 输入卡含 needs_data_confirmation（FIX-2）。
    ess_payload = _latest_payload_path(run_dir, "event_section_summary")
    if not ess_payload:
        failures.append("①缺失 artifact: prompt_audit/event_section_summary/attempt_*.payload.json")
    else:
        try:
            ess = _load_json(ess_payload)
            pl = ess.get("payload") if isinstance(ess, dict) else None
            cards = pl.get("event_cards") if isinstance(pl, dict) else None
            if not isinstance(cards, list) or not cards:
                failures.append("①ESS 输入卡 event_cards 缺失或为空")
            else:
                missing = [i for i, c in enumerate(cards) if not (isinstance(c, dict) and "needs_data_confirmation" in c)]
                if missing:
                    failures.append(f"①ESS 输入卡缺 needs_data_confirmation：{len(missing)}/{len(cards)} 张（索引 {missing[:5]}）")
        except Exception as exc:
            failures.append(f"①check_error:{type(exc).__name__}:{exc}")

    # ② 重试反馈含真实错误定位（FIX-1）。无重试反馈视为 N/A 通过。
    feedbacks = _collect_retry_feedbacks(run_dir)
    if feedbacks:
        bad = [(station, fb) for station, fb in feedbacks if not _LOCALIZATION_RE.search(fb)]
        if bad:
            previews = "；".join(f"{st}: {fb[:60]!r}" for st, fb in bad[:4])
            failures.append(f"②{len(bad)}/{len(feedbacks)} 条非空 retry_feedback 无行/列、JSONDecodeError、字段路径、validation error 或规则路径定位：{previews}")
    # 无 feedbacks：不 fail，明细里说明。

    # ③ tests/test_context_spread.py 存在且收集数 ≥ 15。
    test_file = repo_root / "tests" / "test_context_spread.py"
    if not test_file.is_file():
        failures.append("③缺失 tests/test_context_spread.py")
    else:
        count = _count_collected_tests(test_file)
        if count is None:
            failures.append("③无法统计 test_context_spread.py 收集数")
        elif count < 15:
            failures.append(f"③test_context_spread.py 测试收集数 {count} < 15")

    passed = not failures
    return _make_result(
        "PC-20",
        "已落地三件复核（FIX-1/FIX-2/摊开器）",
        passed,
        "ESS 卡含 needs_data_confirmation；重试反馈含真实定位；test_context_spread ≥ 15" if passed
        else "；".join(failures) + (f"；非空 retry_feedback 共 {len(feedbacks)} 条" if feedbacks else "；无重试反馈可查"),
        "prompt_audit/event_section_summary/*.payload.json + prompt_audit/*/attempt_*.payload.json:retry_feedback + tests/test_context_spread.py",
    )


# --------------------------------------------------------------------------
# PC-21+（08-16 补病检查：B3/B6/B11/C1/C2/C4）
# --------------------------------------------------------------------------

def _payload_body_from_path(path: Optional[Path]) -> Optional[Dict[str, Any]]:
    if path is None:
        return None
    try:
        d = _load_json(path)
    except Exception:
        return None
    if isinstance(d, dict) and isinstance(d.get("payload"), dict):
        return d["payload"]
    return None


def _check_pc21(run_dir: Path) -> Dict[str, Any]:
    """B3：事件站输出契约去重——output_contract 已从 payload 移除，不得回潮。"""
    audit = run_dir / "prompt_audit"
    if not audit.is_dir():
        return _make_result("PC-21", "事件站输出契约去重（B3）", False,
                            "缺失 artifact: prompt_audit", "prompt_audit")
    stations = sorted(
        p for p in audit.iterdir()
        if p.is_dir() and (p.name.startswith("event_card_interpreter.") or p.name == "event_section_summary")
    )
    if not stations:
        return _make_result("PC-21", "事件站输出契约去重（B3）", False,
                            "缺失 artifact: event_card_interpreter.* 与 event_section_summary",
                            "prompt_audit/event_*")
    violations: List[str] = []
    checked = 0
    for station in stations:
        body = _payload_body_from_path(_latest_payload_path(run_dir, station.name))
        if body is None:
            violations.append(f"{station.name}: 缺失 payload")
            continue
        checked += 1
        if "output_contract" in body:
            violations.append(f"{station.name}: payload 仍携带 output_contract（B3 回潮）")
    passed = not violations
    return _make_result(
        "PC-21",
        "事件站输出契约去重（B3）",
        passed,
        f"{checked} 个事件站 payload 均无 output_contract" if passed else "；".join(violations),
        f"prompt_audit/event_card_interpreter.* + event_section_summary；检查 {checked} 站",
    )


def _check_pc22(run_dir: Path) -> Dict[str, Any]:
    """B6：指标清单不得重复供给 data_quality（完整块只在 Runtime Input 一份）。"""
    violations: List[str] = []
    checked = 0
    for layer in _LAYERS:
        prompt_path = _latest_prompt_path(run_dir, layer)
        if prompt_path is None:
            violations.append(f"{layer}: 缺失 prompt")
            continue
        checked += 1
        text = _read_text(prompt_path)
        try:
            section = text.split("### 当前层指标清单\n", 1)[1].split("\n\n### 结构示例", 1)[0]
        except IndexError:
            violations.append(f"{layer}: 无法切出指标清单段")
            continue
        if '"data_quality"' in section:
            violations.append(f"{layer}: 指标清单重复供给 data_quality（B6 回潮）")
    passed = not violations
    return _make_result(
        "PC-22",
        "指标清单与 Runtime Input 去重（B6）",
        passed,
        f"{checked} 层指标清单均无 data_quality 重复块" if passed else "；".join(violations),
        f"prompt_audit/{{L1-L5}}/attempt_*.prompt.txt 指标清单段；检查 {checked} 层",
    )


def _check_pc23(run_dir: Path) -> Dict[str, Any]:
    """B11 另一半：high_severity_conflicts 与 high_severity_typed_conflicts 条目集
    必须相等，且 thesis.retained_conflicts 必须保留全部这些编号。"""
    packet_path = run_dir / "synthesis_packet.json"
    thesis_path = run_dir / "thesis_draft.json"
    if not packet_path.is_file():
        return _make_result("PC-23", "高严重度冲突容器条目集一致（B11）", False,
                            "缺失 artifact: synthesis_packet.json", "synthesis_packet.json")
    try:
        packet = _load_json(packet_path)
    except Exception as exc:
        return _make_result("PC-23", "高严重度冲突容器条目集一致（B11）", False,
                            f"check_error:{type(exc).__name__}:{exc}", "synthesis_packet.json")
    hs = packet.get("high_severity_conflicts")
    ht = packet.get("high_severity_typed_conflicts")
    if not isinstance(hs, list) or not isinstance(ht, list):
        return _make_result("PC-23", "高严重度冲突容器条目集一致（B11）", False,
                            "high_severity_conflicts 或 high_severity_typed_conflicts 缺失/非列表",
                            "synthesis_packet.json")

    def ids(rows: List[Any]) -> set:
        return {str(row.get("conflict_id")) for row in rows if isinstance(row, dict) and row.get("conflict_id")}

    hs_ids = ids(hs)
    ht_ids = ids(ht)
    missing_typed = sorted(hs_ids - ht_ids)
    missing_plain = sorted(ht_ids - hs_ids)
    missing_thesis: List[str] = []
    if thesis_path.is_file():
        try:
            thesis = _load_json(thesis_path)
        except Exception:
            thesis = {}
        retained = thesis.get("retained_conflicts") if isinstance(thesis, dict) else None
        retained_ids = ids(retained) if isinstance(retained, list) else set()
        missing_thesis = sorted(hs_ids - retained_ids)

    violations: List[str] = []
    if missing_typed:
        violations.append(f"typed_conflicts 缺 {missing_typed}")
    if missing_plain:
        violations.append(f"high_severity_conflicts 缺 {missing_plain}")
    if missing_thesis:
        violations.append(f"thesis.retained_conflicts 缺 {missing_thesis}")
    passed = not violations
    return _make_result(
        "PC-23",
        "高严重度冲突容器条目集一致（B11 补全）",
        passed,
        f"两容器各 {len(hs_ids)}/{len(ht_ids)} 条、thesis 保留 {len(hs_ids) - len(missing_thesis)}/{len(hs_ids)} 条，集合一致"
        if passed else "；".join(violations),
        "synthesis_packet.json:high_severity_conflicts/high_severity_typed_conflicts + thesis_draft.json:retained_conflicts",
    )


def _check_pc24(run_dir: Path) -> Dict[str, Any]:
    """C1：L3 持仓锚必须分名分账（provider 总数 / 解析数 / as-of 与滞后天数），
    两个裸数字并存或缺少时点声明即报警。"""
    pl = _load_layer_payload(run_dir, "L3")
    if pl is None:
        return _make_result("PC-24", "L3 持仓锚计数与滞后声明（C1）", False,
                            "缺失 artifact: prompt_audit/L3/attempt_*.payload.json", "prompt_audit/L3")
    item = (pl.get("layer_raw_data") or {}).get("get_qqq_top10_concentration")
    if not isinstance(item, dict):
        return _make_result("PC-24", "L3 持仓锚计数与滞后声明（C1）", False,
                            "缺失 artifact: L3 layer_raw_data.get_qqq_top10_concentration", "prompt_audit/L3")
    value = item.get("value")
    if not isinstance(value, dict):
        return _make_result("PC-24", "L3 持仓锚计数与滞后声明（C1）", True,
                            "持仓指标不可用（value 非 dict），无计数可对账", "prompt_audit/L3")
    dq = item.get("data_quality")
    coverage = dq.get("coverage") if isinstance(dq, dict) else None
    violations: List[str] = []
    for key in ("holdings_as_of", "holdings_lag_days", "holdings_parsed", "total_holdings", "holdings_lag_note"):
        if value.get(key) in (None, ""):
            violations.append(f"value 缺 {key}")
    if isinstance(coverage, dict):
        if coverage.get("holdings_reported") != value.get("holdings_parsed"):
            violations.append(
                f"holdings_reported={coverage.get('holdings_reported')} != holdings_parsed={value.get('holdings_parsed')}"
            )
        if coverage.get("holdings_lag_days") != value.get("holdings_lag_days"):
            violations.append("coverage 与 value 的 holdings_lag_days 不一致")
    else:
        violations.append("data_quality.coverage 缺失")
    if isinstance(value.get("holdings_lag_days"), (int, float)) and value["holdings_lag_days"] < 0:
        violations.append("holdings_lag_days 为负（未来持仓日期）")
    passed = not violations
    return _make_result(
        "PC-24",
        "L3 持仓锚计数与滞后声明（C1）",
        passed,
        f"holdings_parsed={value.get('holdings_parsed')}, total_holdings={value.get('total_holdings')}, "
        f"holdings_as_of={value.get('holdings_as_of')}, lag_days={value.get('holdings_lag_days')}"
        if passed else "；".join(violations),
        "prompt_audit/L3:layer_raw_data.get_qqq_top10_concentration",
    )


def _check_pc25(run_dir: Path) -> Dict[str, Any]:
    """C2：supplier_lookback 处于 pending_validation 时仍作为 30d/90d 主斜率唯一材料
    即报警。老板 08-16 意见：列待审核项目，由新对话专审这批数据怎么来的、能不能撑主斜率；
    审核结论出来前不许悄悄转绿。审核与补验结论（08-17）：O12 专审维持 90d 不可撑主结论；
    30d 补验按 E3 同口径实测未通过（416 有效对子仅 57.69% 在 1% 容差内），
    30/90d 标签维持 pending_validation，本检查继续红。证据：
    investigation_reports/20260816_O12_supplier_lookback_专审/E3_lookback_validation_30d.md"""
    pl = _load_layer_payload(run_dir, "L4")
    if pl is None:
        return _make_result("PC-25", "supplier_lookback 待验证仍撑主斜率（C2）", False,
                            "缺失 artifact: prompt_audit/L4", "prompt_audit/L4")
    item = (pl.get("layer_raw_data") or {}).get("get_ndx_earnings_revision_metrics")
    value = item.get("value") if isinstance(item, dict) else None
    if not isinstance(value, dict):
        return _make_result("PC-25", "supplier_lookback 待验证仍撑主斜率（C2）", True,
                            "盈利修正指标不可用，无斜率可查", "prompt_audit/L4")
    violations: List[str] = []
    for field in ("slope_30d", "slope_90d"):
        slope = value.get(field)
        if not isinstance(slope, dict):
            continue
        if (
            slope.get("material") == "supplier_lookback"
            and slope.get("verification_status") == "pending_validation"
        ):
            violations.append(
                f"{field}: supplier_lookback+pending_validation（30d 补验 08-17 未通过、90d 未到可验期，标签维持 pending）"
            )
    passed = not violations
    return _make_result(
        "PC-25",
        "supplier_lookback 待验证仍撑主斜率（C2）",
        passed,
        "30d/90d 主斜率无 supplier_lookback pending_validation 组合" if passed else "；".join(violations),
        "prompt_audit/L4:layer_raw_data.get_ndx_earnings_revision_metrics.value.slope_30d/slope_90d",
    )


def _check_pc26(run_dir: Path) -> Dict[str, Any]:
    """C4：yield gap 身份按老板 08-16 裁决（O13）锁定为诊断性辅助指标——
    usage 必须 supporting_only，reason 必须写明诊断/辅助身份；偏离即报警。"""
    registry_path = run_dir / "evidence_registry.json"
    if not registry_path.is_file():
        return _make_result("PC-26", "yield gap 身份矛盾检测（C4）", False,
                            "缺失 artifact: evidence_registry.json", "evidence_registry.json")
    try:
        registry = _load_json(registry_path)
    except Exception as exc:
        return _make_result("PC-26", "yield gap 身份矛盾检测（C4）", False,
                            f"check_error:{type(exc).__name__}:{exc}", "evidence_registry.json")
    passport = (registry.get("passports") or {}).get("L4.get_equity_risk_premium#level")
    if not isinstance(passport, dict):
        return _make_result("PC-26", "yield gap 身份矛盾检测（C4）", False,
                            "缺失 passport: L4.get_equity_risk_premium#level", "evidence_registry.json")
    model = passport.get("authority_model") if isinstance(passport.get("authority_model"), dict) else {}
    field_authority = model.get("field_authority") if isinstance(model.get("field_authority"), dict) else {}
    usage = str(field_authority.get("usage") or model.get("field_usage") or "").strip().lower()
    reason = str(field_authority.get("reason") or "")
    contradictions: List[str] = []
    if usage == "core_allowed":
        contradictions.append("usage 仍为 core_allowed（老板已裁：只能当诊断用，supporting_only）")
    elif usage != "supporting_only":
        contradictions.append(f"usage={usage or '空'} 不是 supporting_only（老板已裁）")
    if "诊断" not in reason and "辅助" not in reason:
        contradictions.append("reason 未写明诊断/辅助身份")
    passed = not contradictions
    return _make_result(
        "PC-26",
        "yield gap 身份矛盾检测（C4）",
        passed,
        "yield gap = supporting_only 诊断性辅助指标，无身份矛盾" if passed else "；".join(contradictions),
        "evidence_registry.json:passports['L4.get_equity_risk_premium#level'].authority_model.field_authority",
    )


def _check_pc27(run_dir: Path) -> Dict[str, Any]:
    """O17（2026-08-19 老板裁决，当日收窄）：IA 挑战数据判决即亮灯。

    stance_echo 改代码装配（O16）后，`conflict_matrix` / `unexplained` 是"IA 认为
    数据判决与外部世界存在未解决张力"的看守通道。初版按"非空即亮灯"实现，实测最近
    四次真实跑 conflict_matrix 常态 9-10 行、unexplained 常态 3-4 条（多为
    not_yet_testable 例行登记）——天天亮等于没有灯。老板当日裁收窄：**只有
    `challenged_by_data` 行（事件材料挑战了数据判决）才亮灯**——该行在合约里必须
    带具体 data_side_refs（contracts.py IntegratedConflictRow），平时安静、出事才叫。
    亮灯**不是系统故障**——是 IA 按合约记录了挑战，需要人工阅读，不许静默流过。"""
    check_name = "IA 挑战数据判决亮灯（O17）"
    evidence = "integrated_synthesis_report.json:integrated_adjudication.conflict_matrix/unexplained"
    report_path = run_dir / "integrated_synthesis_report.json"
    if not report_path.is_file():
        return _make_result(
            "PC-27", check_name, True,
            "跳过：缺失 artifact integrated_synthesis_report.json（IA 未跑）",
            "integrated_synthesis_report.json",
        )
    try:
        report = _load_json(report_path)
    except Exception as exc:
        return _make_result(
            "PC-27", check_name, False,
            f"check_error:{type(exc).__name__}:{exc}",
            "integrated_synthesis_report.json",
        )
    adjudication = report.get("integrated_adjudication") if isinstance(report, dict) else None
    if not isinstance(adjudication, dict):
        return _make_result(
            "PC-27", check_name, True,
            "跳过：integrated_adjudication 为空（IA 未跑或降级未裁决）",
            evidence,
        )
    if not adjudication.get("llm_adjudicated"):
        return _make_result(
            "PC-27", check_name, True,
            "跳过：llm_adjudicated=false（降级拼装），异议通道不适用",
            evidence,
        )
    challenged = [
        row for row in adjudication.get("conflict_matrix") or []
        if isinstance(row, dict) and str(row.get("relation") or "") == "challenged_by_data"
    ]
    if challenged:
        return _make_result(
            "PC-27", check_name, False,
            "这不是系统故障，是 IA 记录了事件材料对数据判决的挑战，需要人工阅读："
            f"challenged_by_data {len(challenged)} 行",
            evidence,
        )
    return _make_result("PC-27", check_name, True, "IA 未记录对数据判决的挑战", evidence)


# B14（摘要层取舍标准无定义）不能机器化：必须先由人声明每层摘要取舍标准，之后才能
# 机械化检查"被省掉的恰是关键指标"这类语义问题。标准归 C9/T38 设计文档一并定，不单
# 独设检查；此注释即"为何不能"的留档。


# --------------------------------------------------------------------------
# 总入口
# --------------------------------------------------------------------------

_CHECKS: List[Tuple[str, str, Any]] = [
    ("PC-11", "输出示例指标本层存在性（B4）", _check_pc11),
    ("PC-12", "manual_overrides 陈旧占位日期（B5）", _check_pc12),
    ("PC-13", "percentile 取值域混用（B7）", _check_pc13),
    ("PC-14", "context_brief 日期 vs 指标日期（B8）", _check_pc14),
    ("PC-15", "high_severity 容器名与 severity 字段一致性（B11）", _check_pc15),
    ("PC-16", "他站产物 null 占位/禁用标记进输入（B12）", _check_pc16),
    ("PC-17", "bridge 冲突矩阵行完整性（B13）", _check_pc17),
    ("PC-18", "L4 数据陈旧（C3）+ 回购逐字重复行（C5）", _check_pc18),
    ("PC-19", "canon 名 vs 输入 metric_name（C12）", _check_pc19),
    ("PC-20", "已落地三件复核（FIX-1/FIX-2/摊开器）", _check_pc20),
    ("PC-21", "事件站输出契约去重（B3）", _check_pc21),
    ("PC-22", "指标清单与 Runtime Input 去重（B6）", _check_pc22),
    ("PC-23", "高严重度冲突容器条目集一致（B11 补全）", _check_pc23),
    ("PC-24", "L3 持仓锚计数与滞后声明（C1）", _check_pc24),
    ("PC-25", "supplier_lookback 待验证仍撑主斜率（C2）", _check_pc25),
    ("PC-26", "yield gap 身份矛盾检测（C4）", _check_pc26),
    ("PC-27", "IA 挑战数据判决亮灯（O17）", _check_pc27),
]


def run_checks_b(run_dir: Path) -> List[Dict[str, Any]]:
    """对一次 run 的落盘产物执行 PC-11 ~ PC-27 只读检查。"""
    results: List[Dict[str, Any]] = []
    for check_id, name, func in _CHECKS:
        try:
            results.append(func(Path(run_dir)))
        except Exception as exc:  # noqa: BLE001 - 常设检查单条异常不得整包崩
            results.append(_make_result(
                check_id, name, False,
                f"check_error:{type(exc).__name__}:{exc}",
                "",
            ))
    return results
