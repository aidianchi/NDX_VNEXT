# -*- coding: utf-8 -*-
"""同步巡逻：主链 run 的软暂停——出题官的课题亮给老板，圈定的立刻巡逻，成果上研究架。

老板 2026-08-25/26 三次裁定（快慢分路 + 出题官重构 + 时序回摆）：快变量课题
跟 run 同步走，且**出题和巡逻都在综合裁决之前**——出题官读六站对抗残局出题，
老板圈题当场巡逻，成果上研究成果架，本次 IA 从架上取（含本次新巡逻的成果）。
不许把题推到下次 run（老板原话教训）；慢叙事（宪章/跟踪名单）维持异步低频。

流程（挂在 src/main.py：IA 组装之前）：
1. 出题官出题（topic_composer.py，0-2 份任务书，铁律"现在能查"）；
2. 缺口桥把任务书收进议程账本（topic: 稳定键去重，历史遗留候选一并亮出）；
3. 终端/控制台亮出候选任务卡，老板圈题（软暂停：非交互 / 超时 / 直接回车 = 跳过，
   run 永不等人；没圈的留在账本里仍是候选，事后可激活）；
4. 圈中的候选激活 → 当场巡逻（runner.run_agenda，经费卡走日常档额度）；
5. 巡逻成果两份落盘：run_dir/event_research_patrols.json（本次留痕）+
   output/event_research/research_shelf.json（研究成果架，跨 run 累积）——
   **消费端过滤在装配时做**：对账通过的卡可当事实，降级卡只带"仅解读"资格；
6. 本次 IA 从研究架读成果（含刚巡逻的，按 effective_date 时点过滤），
   巡逻材料以"事件层二档候选材料"身份进 prompt，永不进数据主链。

时点纪律：回测 run（backtest_date 非空）整体跳过（含收题）——巡逻抓的是当下网页，
喂给历史截面等于伪装历史；回测留下的疑点也不进议程账本。

经费：同步巡逻用日常档 SYNC_PATROL_BUDGET_CAP（实测一次巡逻约百万级 token，
给 3 倍余量；老板可调）。账本里 boss/charter 来源的议程额度不受此影响。
"""

from __future__ import annotations

import json
import os
import select
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from . import agenda as agenda_mod
from .agenda import LEDGER_PATH
from .gap_bridge import harvest_gap_candidates
from .runner import RUNS_ROOT

ARTIFACT_NAME = "event_research_patrols.json"

# 研究成果架：跨 run 累积的巡逻成果（IA 从架子上取近期成果，带时点过滤）。
# 巡逻是"当下"的活，成果架让下一次 run 的裁决能用上——同一 run 的 IA 来不及用
# （出题官必须看过 IA 残局才出题，这是 08-26 重构定下的顺序）。
RESEARCH_SHELF_PATH = Path("output/event_research/research_shelf.json")
_SHELF_MAX_ENTRIES = 20

# 控制台圈题的文件交接：control_service 启动的 run 没有 stdin（服务以 DEVNULL 拉起
# 子进程），暂停时把候选清单写 pending 文件、控制台页面轮询展示，老板圈题由
# POST /gap-selection 写 answer 文件，本模块轮询读到后放行。服务注入的环境变量：
ENV_CONSOLE_LAUNCHED = "NDX_CONSOLE_LAUNCHED"
DEFAULT_PENDING_FILE = Path("output/state_ledger/gap_selection_pending.json")
DEFAULT_ANSWER_FILE = Path("output/state_ledger/gap_selection_answer.json")

# 日常档经费卡：实测一次真实巡逻约百万级 token，300 万给 3 倍余量（老板 2026-08-25
# 认可"同步巡逻另设小得多的日常档"；要改就改这一个数）。
SYNC_PATROL_BUDGET_CAP = 3_000_000

ENV_PAUSE_TIMEOUT = "NDX_GAP_PAUSE_TIMEOUT"
DEFAULT_PAUSE_TIMEOUT_SEC = 3600  # 软暂停默认等 1 小时；<=0 = 一直等

# IA 侧 prompt 体积护栏
_MAX_PATROLS_IN_PROMPT = 4
_MAX_CARDS_PER_PATROL = 8
_MAX_TEXT = 600


def parse_selection(text: str, count: int) -> List[int]:
    """解析圈题输入 → 0-based 索引（去重保序）。支持 "1,3"、"1 3"、"all"/"a"；空串=[]；非法项忽略。"""
    text = (text or "").strip().lower()
    if not text:
        return []
    if text in {"all", "a", "全部"}:
        return list(range(count))
    picked: List[int] = []
    for token in text.replace("，", ",").replace("、", ",").replace(" ", ",").split(","):
        token = token.strip()
        if not token.isdigit():
            continue
        idx = int(token) - 1
        if 0 <= idx < count and idx not in picked:
            picked.append(idx)
    return picked


def _pending_gap_candidates(ledger_path: Path) -> List[Dict[str, Any]]:
    """账本里所有 source=gap 且仍处候选状态的议程（本期新收 + 历史遗留）。"""
    return [
        a
        for a in agenda_mod.current_agendas(ledger_path).values()
        if a.get("source") == "gap" and a.get("status") == "candidate"
    ]


def _pause_timeout() -> int:
    raw = os.environ.get(ENV_PAUSE_TIMEOUT, "").strip()
    if not raw:
        return DEFAULT_PAUSE_TIMEOUT_SEC
    try:
        return int(raw)
    except ValueError:
        return DEFAULT_PAUSE_TIMEOUT_SEC


def _read_stdin(timeout_sec: int) -> Optional[str]:
    """带超时的读一行；超时返回 None。timeout_sec <= 0 表示一直等。"""
    if timeout_sec > 0:
        ready, _, _ = select.select([sys.stdin], [], [], timeout_sec)
        if not ready:
            return None
    return sys.stdin.readline()


def _trim(value: Any, limit: int = _MAX_TEXT) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _compact_verified_card(card: Dict[str, Any]) -> Dict[str, Any]:
    pointer = card.get("source_pointer") if isinstance(card.get("source_pointer"), dict) else {}
    return {
        "fact_summary": _trim(card.get("fact_summary")),
        "interpretation": _trim(card.get("interpretation")),
        "source_url": str(card.get("source_url") or pointer.get("url") or ""),
        "source_tier": str(card.get("source_tier") or ""),
        "collected_at_utc": str(card.get("collected_at_utc") or ""),
    }


def _compact_downgraded_card(card: Dict[str, Any]) -> Dict[str, Any]:
    """降级卡的"仅解读"形态：内容留下，资格写死——带原因码，不得当事实引用。"""
    reconciliation = card.get("reconciliation") if isinstance(card.get("reconciliation"), dict) else {}
    compact = _compact_verified_card(card)
    compact["reconciliation_status"] = str(reconciliation.get("status") or "")
    compact["reconciliation_detail"] = _trim(reconciliation.get("detail"), 200)
    return compact


def build_patrols_artifact(patrols: List[Dict[str, Any]], reason: str = "") -> Dict[str, Any]:
    """装配 IA 消费的巡逻成果 payload。消费端过滤在此（老板 2026-08-26 口径）：

    - 对账通过（reconciliation.status == "verified"）的卡入 verified_cards，可当事实引用；
    - 降级卡入 downgraded_cards，只带"仅解读"资格（带原因码），不得当事实——
      内容不扔（形式不得拒收内容），但身份钉死。
    """
    out_patrols: List[Dict[str, Any]] = []
    for entry in patrols[:_MAX_PATROLS_IN_PROMPT]:
        agenda = entry["agenda"]
        summary = entry["summary"]
        patrol_run_dir = Path(str(summary.get("run_dir") or ""))
        verified_cards: List[Dict[str, Any]] = []
        downgraded_cards: List[Dict[str, Any]] = []
        cards_file = patrol_run_dir / "material_cards.jsonl"
        if cards_file.exists():
            with cards_file.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    card = json.loads(line)
                    if not isinstance(card, dict):
                        continue
                    reconciliation = card.get("reconciliation") if isinstance(card.get("reconciliation"), dict) else {}
                    if reconciliation.get("status") == "verified":
                        verified_cards.append(_compact_verified_card(card))
                    else:
                        downgraded_cards.append(_compact_downgraded_card(card))
        narrative = summary.get("narrative_state") if isinstance(summary.get("narrative_state"), dict) else {}
        out_patrols.append(
            {
                "agenda_id": agenda.get("agenda_id"),
                "question": _trim(agenda.get("question")),
                "narrative_state": {
                    key: _trim(narrative.get(key))
                    for key in (
                        "framework_position",
                        "conclusion",
                        "bull_strongest",
                        "bear_strongest",
                        "falsification",
                        "previous_position_delta",
                    )
                    if narrative.get(key)
                },
                "absence_signals": [_trim(s, 200) for s in (narrative.get("absence_signals") or [])][:4]
                if isinstance(narrative.get("absence_signals"), list)
                else [],
                "verified_cards": verified_cards[:_MAX_CARDS_PER_PATROL],
                "downgraded_cards": downgraded_cards[:_MAX_CARDS_PER_PATROL],
                "cards_verified": summary.get("cards_verified"),
                "cards_downgraded": summary.get("cards_downgraded"),
                "budget_exhausted": bool(summary.get("budget_exhausted")),
                "patrol_run_dir": str(patrol_run_dir),
            }
        )
    return {
        "schema_version": "event_research_patrols_v1",
        "generated_by": "sync_patrol",
        "skip_reason": reason,
        "consumption_rule": (
            "verified_cards 是对账通过的卡，可被引用为事实；"
            "downgraded_cards 是对账降级卡，只能按解读/线索对待，不得当事实引用（各带原因码）。"
            "本材料是事件层二档候选材料，只可与数据判决对质，永不充当 L1-L5 证据。"
        ),
        "patrols": out_patrols,
    }


def update_research_shelf(
    patrol_entries: List[Dict[str, Any]],
    shelf_path: Path = RESEARCH_SHELF_PATH,
) -> None:
    """把本次巡逻成果放上研究成果架（跨 run 累积，下次 run 的 IA 从架上取）。

    只追加新面孔（按 agenda_id 去重，同一议程重跑则更新条目），架上最多留
    _SHELF_MAX_ENTRIES 条最新的。架子是事件层产物，主链只读。
    """
    if not patrol_entries:
        return
    shelf_path = Path(shelf_path)
    existing: List[Dict[str, Any]] = []
    if shelf_path.exists():
        try:
            payload = json.loads(shelf_path.read_text(encoding="utf-8"))
            existing = [e for e in (payload.get("patrols") or []) if isinstance(e, dict)]
        except (json.JSONDecodeError, OSError):
            existing = []
    by_id = {str(e.get("agenda_id")): e for e in existing}
    for entry in patrol_entries:
        by_id[str(entry.get("agenda_id"))] = {**entry, "researched_at_utc": _utc_now_iso()}
    entries = sorted(by_id.values(), key=lambda e: str(e.get("researched_at_utc") or ""), reverse=True)
    shelf = {
        "schema_version": "research_shelf_v1",
        "generated_by": "sync_patrol",
        "patrols": entries[:_SHELF_MAX_ENTRIES],
    }
    shelf_path.parent.mkdir(parents=True, exist_ok=True)
    shelf_path.write_text(json.dumps(shelf, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _default_patrol_fn(ledger_path: Path, runs_root: Path) -> Callable[[str], Dict[str, Any]]:
    from .runner import run_agenda

    def _patrol(agenda_id: str) -> Dict[str, Any]:
        return run_agenda(agenda_id, ledger_path=ledger_path, runs_root=runs_root)

    return _patrol


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_pending_file(
    pending_file: Path,
    run_dir: Path,
    pending: List[Dict[str, Any]],
    new_ids: set,
    timeout_sec: int,
) -> None:
    """把候选清单写给控制台页面（control_service 的 GET /gap-candidates 读它）。"""
    payload = {
        "run_dir": str(run_dir),
        "created_at_utc": _utc_now_iso(),
        "deadline_at_utc": (
            datetime.fromtimestamp(time.time() + timeout_sec, timezone.utc).isoformat()
            if timeout_sec > 0
            else None
        ),
        "candidates": [
            {
                "agenda_id": a.get("agenda_id"),
                "question": a.get("question"),
                "tag": "本期新增" if a.get("agenda_id") in new_ids else "历史遗留",
                # 出题官任务书字段（08-26 重构）：面板按任务卡展示，不是干巴巴一行字
                "topic_brief": a.get("topic_brief") or {},
            }
            for a in pending
        ],
    }
    pending_file.parent.mkdir(parents=True, exist_ok=True)
    pending_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _await_console_selection(
    run_dir: Path,
    pending: List[Dict[str, Any]],
    new_ids: set,
    *,
    pending_file: Path,
    answer_file: Path,
    timeout_sec: int,
    poll_interval: float = 2.0,
) -> Optional[List[int]]:
    """控制台模式：写 pending 文件 → 轮询 answer 文件（POST /gap-selection 写入）。

    返回 0-based 索引列表；超时返回 None。结束时清掉交接文件，防下次误读。
    """
    _write_pending_file(pending_file, run_dir, pending, new_ids, timeout_sec)
    deadline = time.monotonic() + timeout_sec if timeout_sec > 0 else None
    try:
        while True:
            if answer_file.exists():
                try:
                    answer = json.loads(answer_file.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    answer = None
                if isinstance(answer, dict) and str(answer.get("run_dir") or "") == str(run_dir):
                    index_by_id = {a.get("agenda_id"): i for i, a in enumerate(pending)}
                    picked: List[int] = []
                    for agenda_id in answer.get("selected_agenda_ids") or []:
                        idx = index_by_id.get(str(agenda_id))
                        if idx is not None and idx not in picked:
                            picked.append(idx)
                    return picked
            if deadline is not None and time.monotonic() >= deadline:
                return None
            time.sleep(poll_interval)
    finally:
        for path in (pending_file, answer_file):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def run_sync_gap_patrol(
    run_dir: Path,
    *,
    backtest_date: Optional[str] = None,
    enabled: bool = True,
    ledger_path: Path = LEDGER_PATH,
    runs_root: Path = RUNS_ROOT,
    is_interactive: Optional[bool] = None,
    input_fn: Optional[Callable[[], str]] = None,
    output_fn: Callable[[str], None] = print,
    patrol_fn: Optional[Callable[[str], Dict[str, Any]]] = None,
    timeout_sec: Optional[int] = None,
    pending_file: Path = DEFAULT_PENDING_FILE,
    answer_file: Path = DEFAULT_ANSWER_FILE,
    shelf_path: Path = RESEARCH_SHELF_PATH,
) -> Dict[str, Any]:
    """同步巡逻主流程，返回小结 dict（进 run_summary 的 gap_patrol 键）。

    圈题交互两种形态：终端有 stdin 就终端亮清单（手跑 console_run_all 的情形）；
    控制台服务启动的 run 没有 stdin，走文件交接（pending/answer 文件 +
    control_service 的 /gap-candidates、/gap-selection 端点）。
    可测试性：is_interactive / input_fn / output_fn / patrol_fn / 交接文件路径
    全部可注入；默认 patrol_fn 是真实 run_agenda（花真钱），测试必须注入假的。
    """
    run_dir = Path(run_dir)
    result: Dict[str, Any] = {"status": "ok", "patrols_run": 0}

    # 时点纪律：回测 run 不收题也不巡逻（巡逻材料是"当下"的，喂历史截面是伪装）。
    if backtest_date:
        result.update({"status": "skipped", "reason": "backtest_run"})
        return result

    # 第一步永远执行：收题进账本（候选状态，不激活就不花钱）。
    harvest = harvest_gap_candidates(
        run_dir, ledger_path=ledger_path, budget_cap=SYNC_PATROL_BUDGET_CAP
    )
    result["harvest"] = {k: v for k, v in harvest.items() if k != "agendas"}
    new_ids = {a["agenda_id"] for a in harvest.get("agendas", [])}

    artifact_path = run_dir / ARTIFACT_NAME

    def _finish_with_artifact(reason: str, patrols: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
        payload = build_patrols_artifact(patrols or [], reason=reason)
        artifact_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        result["artifact"] = str(artifact_path)
        return result

    if not enabled:
        result.update({"status": "skipped", "reason": "disabled_by_flag"})
        return _finish_with_artifact("disabled_by_flag")

    pending = _pending_gap_candidates(ledger_path)
    result["pending_candidates"] = len(pending)
    if not pending:
        return _finish_with_artifact("no_pending_candidates")

    interactive = sys.stdin.isatty() if is_interactive is None else is_interactive
    console_mode = os.environ.get(ENV_CONSOLE_LAUNCHED, "") == "1"
    result["interaction"] = "console" if console_mode else ("terminal" if interactive else "none")
    if not interactive and not console_mode:
        result.update({"status": "skipped", "reason": "non_interactive"})
        return _finish_with_artifact("non_interactive")

    effective_timeout = _pause_timeout() if timeout_sec is None else timeout_sec

    if interactive and not console_mode:
        # 终端软暂停：亮清单，等老板圈题。
        output_fn("")
        output_fn("=" * 60)
        output_fn("本次 run 发现的未解疑点（缺口桥 → 事件层研究部候选题目）：")
        for i, agenda in enumerate(pending, 1):
            tag = "本期新增" if agenda.get("agenda_id") in new_ids else "历史遗留"
            output_fn(f"  [{i}] ({tag}) {agenda.get('question')}")
        output_fn("圈定要当场巡逻的编号（逗号分隔，all=全查，直接回车=都不查）：")
        output_fn("=" * 60)

        if input_fn is not None:
            try:
                raw: Optional[str] = input_fn()
            except (EOFError, KeyboardInterrupt):
                raw = ""
        else:
            raw = _read_stdin(effective_timeout)

        if raw is None:
            output_fn("（超时未收到选择，跳过同步巡逻，候选已留在账本。）")
            result.update({"status": "skipped", "reason": "timeout"})
            return _finish_with_artifact("timeout")
        picked = parse_selection(raw, len(pending))
    else:
        # 控制台软暂停：候选清单写 pending 文件，控制台页面圈题，轮询 answer 文件。
        picked = _await_console_selection(
            run_dir,
            pending,
            new_ids,
            pending_file=Path(pending_file),
            answer_file=Path(answer_file),
            timeout_sec=effective_timeout,
        )
        if picked is None:
            result.update({"status": "skipped", "reason": "timeout"})
            return _finish_with_artifact("timeout")

    if not picked:
        result.update({"status": "skipped", "reason": "no_selection"})
        return _finish_with_artifact("no_selection")

    patrol = patrol_fn or _default_patrol_fn(ledger_path, runs_root)
    succeeded: List[Dict[str, Any]] = []
    patrol_reports: List[Dict[str, Any]] = []
    for idx in picked:
        agenda = pending[idx]
        agenda_id = agenda["agenda_id"]
        agenda_mod.append_status_change(
            agenda_id, "active", note="同步巡逻：老板 run 内圈定", ledger_path=ledger_path
        )
        try:
            summary = patrol(agenda_id)
        except Exception as exc:  # 巡逻失败不阻断主链；退回候选等下次
            agenda_mod.append_status_change(
                agenda_id, "candidate", note=f"同步巡逻失败退回候选：{exc}", ledger_path=ledger_path
            )
            patrol_reports.append({"agenda_id": agenda_id, "status": "failed", "error": str(exc)[:200]})
            continue
        succeeded.append({"agenda": agenda, "summary": summary})
        patrol_reports.append(
            {
                "agenda_id": agenda_id,
                "status": "done",
                "run_dir": summary.get("run_dir"),
                "cards_verified": summary.get("cards_verified"),
                "cards_total": summary.get("cards_total"),
                "budget_exhausted": summary.get("budget_exhausted"),
            }
        )

    result["patrols_run"] = len(succeeded)
    result["patrols"] = patrol_reports
    final = _finish_with_artifact("", succeeded)
    if succeeded:
        # 上研究成果架：下次 run 的 IA 从架上取（时点过滤在 IA 侧做）。
        artifact_payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        try:
            update_research_shelf(artifact_payload.get("patrols") or [], shelf_path)
            final["research_shelf"] = str(shelf_path)
        except Exception as exc:  # 上架失败不阻断，留痕
            final["research_shelf_error"] = str(exc)[:200]
    return final
