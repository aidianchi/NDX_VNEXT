"""文档纪律闸门。

背景：状态漂移在本项目复发过两次（2026-07-13、2026-07-22 审计）——记分板声明
"已解决 47"、清单标题写 23、实际列 30，十余项无法寻址；路线图里 7 段方向有 4 段
是已完工内容。根因是同一状态被手抄在多份文档里，靠纪律同步，忘一次即永久错位。

结构上的解法是消灭副本：`现在.md` 是唯一可以声明事项状态的文件。因此本模块的
断言全部是"良构性"与"对照只增不改的历史"，**没有一条在校验两份副本是否相等**——
需要对账测试，就说明结构里还有冗余。
"""

import glob
import os
import re

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

BOARD = os.path.join(REPO_ROOT, "现在.md")
LETTERS = os.path.join(REPO_ROOT, "人话进度报告.md")
WORK_LOG = os.path.join(REPO_ROOT, "WORK_LOG.md")

# 活路由文档：新对话会直接读到，或由入口文档直接指向；其中的路径必须能走通。
ROUTE_DOCS = [os.path.join(REPO_ROOT, name) for name in (
    "CLAUDE.md",
    "AGENTS.md",
    "README.md",
    "现在.md",
    "ARCHITECTURE.md",
    "docs/archive/INDEX.md",
)]

VALID_STATUSES = {"可以做", "进行中", "等你", "后排", "等条件"}

LEDGER_ROW = re.compile(r"^\|\s*(T\d+)\s*\|(.+)\|\s*$")
CLOSED_IN_HISTORY = re.compile(r"【关闭\s*(T\d+)】")
ROUTED_PATH = re.compile(r"`([\w一-鿿./*_-]+\.(?:md|json|py|toml))`")


def _read(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def _resolve_path(source, raw_path):
    """兼容根目录路由与文档所在目录内的相对路由。"""
    candidates = [
        os.path.join(REPO_ROOT, raw_path),
        os.path.join(os.path.dirname(source), raw_path),
    ]
    for candidate in candidates:
        found = glob.glob(candidate) if "*" in raw_path else (
            [candidate] if os.path.exists(candidate) else []
        )
        if found:
            return found
    return []


def _section(text, heading):
    """取出某个二级小节的正文（到下一个二级标题为止）。"""
    assert heading in text, f"现在.md 缺少小节 {heading}，解析器无法定位"
    return text.split(heading, 1)[1].split("\n## ", 1)[0]


def _ledger():
    """返回 [(id, 状态, 完成判据, 细节锚点)]，取自「全部未完成」小节。"""
    body = _section(_read(BOARD), "## 📋 全部未完成")
    rows = []
    for line in body.splitlines():
        match = LEDGER_ROW.match(line.strip())
        if not match:
            continue
        cells = [cell.strip() for cell in match.group(2).split("|")]
        # 列序：一句话 | 状态 | 怎么算做完 | 细节在哪
        assert len(cells) == 4, f"台账行 {match.group(1)} 列数应为 5（含编号），实为 {len(cells) + 1}：{line}"
        rows.append((match.group(1), cells[1], cells[2], cells[3]))
    return rows


def test_ledger_is_well_formed():
    """编号唯一、状态合法、完成判据与细节锚点必填。

    完成判据必填是刻意的：它把"我说做完了"变成"标准说做完了"，让非技术 owner
    不必读代码也能验收。细节锚点必填则保证技术注意事项有地方落，不会因为看板
    要保持可读而被丢掉。
    """
    rows = _ledger()
    assert rows, "现在.md 未解析出任何台账条目——要么真的清空了（那就同步改计数行），要么表格被改坏"

    ids = [task_id for task_id, *_ in rows]
    duplicates = sorted({task_id for task_id in ids if ids.count(task_id) > 1})
    assert not duplicates, f"台账编号重复：{duplicates}"

    illegal = sorted({status for _, status, _, _ in rows if status not in VALID_STATUSES})
    assert not illegal, f"非法状态 {illegal}；合法值只有 {sorted(VALID_STATUSES)}（做完的条目应删行，不是改状态）"

    for task_id, _, criterion, anchor in rows:
        assert len(criterion) >= 10, f"{task_id} 的完成判据太短或缺失，无法用于验收：{criterion!r}"
        assert anchor, f"{task_id} 缺细节锚点，技术注意事项将无处安放"
        paths = ROUTED_PATH.findall(anchor)
        assert paths, f"{task_id} 的细节锚点没有可解析的文件路径：{anchor!r}"
        assert any(_resolve_path(BOARD, path) for path in paths), (
            f"{task_id} 的细节锚点没有任何真实文件：{paths}"
        )


def test_counts_match_the_ledger():
    """标题里的件数必须由实际行数支撑——手写计数是漂移的历史入口。"""
    text = _read(BOARD)
    rows = _ledger()

    total = re.search(r"全部未完成（(\d+) 件）", text)
    assert total, "现在.md 缺少「全部未完成（N 件）」标题计数"
    assert int(total.group(1)) == len(rows), (
        f"标题声明未完成 {total.group(1)} 件，台账实际 {len(rows)} 件"
    )

    waiting_on_user = [task_id for task_id, status, _, _ in rows if status == "等你"]
    declared = re.search(r"等你决定的（(\d+) 件）", text)
    assert declared, "现在.md 缺少「等你决定的（N 件）」标题计数"
    assert int(declared.group(1)) == len(waiting_on_user), (
        f"标题声明等你 {declared.group(1)} 件，台账中状态为「等你」的实际 {len(waiting_on_user)} 件：{waiting_on_user}"
    )

    user_section = _section(text, "## ⏳ 等你决定的")
    mentioned = set(re.findall(r"T\d+", user_section))
    assert mentioned == set(waiting_on_user), (
        f"「等你决定的」与台账的等你项不一致：小节={sorted(mentioned)}，"
        f"台账={sorted(waiting_on_user)}"
    )
    for task_id in waiting_on_user:
        assert task_id in user_section, f"{task_id} 状态是「等你」，却没出现在「等你决定的」小节里"


def test_board_carries_no_completed_items():
    """看板只讲现在。完成标记出现即意味着已完工内容开始回流。

    旧 NEXT_STEPS.md 正是这样烂掉的：7 段方向里 4 段是完工内容，谁也没删。
    """
    text = _read(BOARD)
    assert "✅" not in text, "现在.md 出现 ✅——完成的事应删行，完成记录写进 WORK_LOG.md"


def test_next_action_points_at_a_live_task():
    """「我接下来要做的」必须指向台账里真实存在的条目。

    这一行是 owner 的持续否决权入口，指向幽灵编号会让否决落空。
    """
    section = _section(_read(BOARD), "## ▶️ 我接下来要做的")
    referenced = set(re.findall(r"T\d+", section))
    assert referenced, "「我接下来要做的」没有指名任何编号"
    assert len(referenced) == 1, f"「下一件」必须只有一件，实际写了：{sorted(referenced)}"
    live = {task_id for task_id, *_ in _ledger()}
    assert referenced <= live, f"「我接下来要做的」指向了台账中不存在的编号：{sorted(referenced - live)}"
    statuses = {task_id: status for task_id, status, *_ in _ledger()}
    next_id = next(iter(referenced))
    assert statuses[next_id] in {"可以做", "进行中"}, (
        f"「下一件」{next_id} 当前状态是 {statuses[next_id]}，并不能直接开工"
    )


def test_task_ids_are_never_reused():
    """已关闭的编号不得复活。

    这是"东西不会被悄悄弄丢"的机器保证：owner 任何时候问「T03 后来怎么样了」，
    答案唯一。收工时在 WORK_LOG.md 写 `【关闭 T##】`，此后该编号永久退役。
    """
    closed = set(CLOSED_IN_HISTORY.findall(_read(WORK_LOG)))
    live = {task_id for task_id, *_ in _ledger()}
    reused = sorted(closed & live)
    assert not reused, (
        f"编号 {reused} 已在 WORK_LOG.md 标记关闭，却又出现在现在.md 台账里。"
        "新事项必须用新编号，不得复用退役编号。"
    )


def test_letters_carry_no_ledger():
    """《人话进度报告》是决策记录，不得再承载台账。

    历史上的漂移全部发生在信里内嵌的状态构件（记分板、计数、排队清单）上，
    叙述本身从未出错。切掉状态构件即切掉漂移面。
    """
    rows = [line for line in _read(LETTERS).splitlines() if LEDGER_ROW.match(line.strip())]
    assert not rows, (
        f"人话进度报告.md 出现了 {len(rows)} 行台账表格——状态只写在现在.md。"
        "信里可以叙述某件事，但不得列 T## 清单。"
    )


def test_routed_paths_all_exist():
    """活文档中的 Markdown 路由必须真实存在，防归档/改名留下死链。

    覆盖入口及其直接指向的活文档：本次改革中 README / AGENTS / ARCHITECTURE /
    归档索引都出现过死链，只查 CLAUDE.md 是抓不到的。
    """
    broken = []
    for source in ROUTE_DOCS:
        for raw_path in set(ROUTED_PATH.findall(_read(source))):
            # JSON / Python 路径可能是 artifact 形状示例，不是阅读路由；
            # 台账的技术文件锚点已在 well_formed 测试里单独验证。
            if not raw_path.endswith(".md"):
                continue
            found = _resolve_path(source, raw_path)
            if not found:
                broken.append(f"{os.path.basename(source)} → {raw_path}")
    assert not broken, f"文档引用了不存在的路径：{sorted(broken)}"
