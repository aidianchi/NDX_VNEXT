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
# WORK_LOG 按月滚动归档（2026-07-29 起）。关闭记录会随条目一起搬进归档，因此"编号
# 永不复用"这条闸门必须连归档一起扫——否则每轮转一次就静默出现一段可复用的编号区间。
WORK_LOG_ARCHIVES = sorted(
    glob.glob(os.path.join(REPO_ROOT, "docs", "archive", "**", "*WORK_LOG*.md"), recursive=True)
)

# 活路由文档：新对话会直接读到，或由入口文档直接指向；其中的路径必须能走通。
ROUTE_DOCS = [os.path.join(REPO_ROOT, name) for name in (
    "CLAUDE.md",
    "AGENTS.md",
    "README.md",
    "现在.md",
    "系统说明书.md",
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

    扫描范围含 `docs/archive/**/*WORK_LOG*.md`：条目按月滚动归档后，退役编号仍然退役。
    """
    history = "\n".join(_read(path) for path in [WORK_LOG, *WORK_LOG_ARCHIVES])
    closed = set(CLOSED_IN_HISTORY.findall(history))
    live = {task_id for task_id, *_ in _ledger()}
    reused = sorted(closed & live)
    assert not reused, (
        f"编号 {reused} 已在 WORK_LOG.md 标记关闭，却又出现在现在.md 台账里。"
        "新事项必须用新编号，不得复用退役编号。"
    )


def test_board_stays_glanceable():
    """看板是给人一眼看的，细节住锚点文件；超限即细节开始回流。

    2026-08-05 改革的直接起因：owner 反馈"打开就看不懂"。当时 T38 单格塞了
    500+ 字符的验收细节，而同样内容在工单文件里本来就有完整版本。每次收工
    往格子里多塞一点都是合理的，累积起来就是不可读——所以用闸门挡，不靠自觉。
    """
    text = _read(BOARD)
    lines = text.splitlines()
    assert len(lines) <= 110, (
        f"现在.md 已有 {len(lines)} 行，超过 110 行上限——细节应搬去「细节在哪」指向的文件"
    )
    body = _section(text, "## 📋 全部未完成")
    for line in body.splitlines():
        match = LEDGER_ROW.match(line.strip())
        if not match:
            continue
        cells = [cell.strip() for cell in match.group(2).split("|")]
        task_id, one_liner, criterion = match.group(1), cells[0], cells[2]
        assert len(one_liner) <= 50, (
            f"{task_id} 的「一句话」有 {len(one_liner)} 字符（上限 50）——它该是标题，不是段落"
        )
        assert len(criterion) <= 120, (
            f"{task_id} 的「怎么算做完」有 {len(criterion)} 字符（上限 120）——"
            "验收细节写进锚点文件，这里只留一句可判定的话"
        )


def test_letters_stay_recent_and_indexed():
    """信件正文只保留最近几封；全量目录常驻，早期信整封滚进 docs/archive。

    与 WORK_LOG 按月滚动同理：owner 打开先看目录（每封一句话），要细节再进正文
    或档案。归档整封搬走、逐字不改——信是历史记录，压缩重写等于改写历史。
    """
    text = _read(LETTERS)
    letters = re.findall(r"^## 第 \d+ 封", text, flags=re.MULTILINE)
    assert letters, "人话进度报告.md 没有任何信件标题——解析器失效或文件被改坏"
    assert len(letters) <= 5, (
        f"人话进度报告.md 正文有 {len(letters)} 封信（上限 5）——最早的整封搬进 docs/archive/，目录里留一句话"
    )
    assert "## 📖 目录" in text, "人话进度报告.md 缺少「📖 目录」小节——目录是 owner 的一眼入口"


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


# 代码世界 vs 文档世界对照（2026-08-08 增加）。
# 背景：实测 9 个代码侧新模块（event_narrative_ledger、expectation_ledger、
# news_event_*、vintage_archiver、recompute_belt、state_ledger、outcome_scoring 等）
# 在四个核心文档中 0 提及——架构长出"新器官"，文档连门牌号都没写。修改时间证明不了
# 内容同步，只有机器检查能挡住漂移（对应项目 3.1b：能锁进测试的别只写进提示词）。
#
# 规则：核心业务模块必须在《系统说明书》或 CLAUDE.md 中有概念级提及。
# 只查"概念是否被文档承认"，不查"描述是否详尽"——详尽度交给维护纪律。
# 例外（明确不算业务概念）：入口/工具/兼容/基础设施类，见 _DOC_EXEMPT。
_DOC_EXEMPT = {
    "main", "config", "api_config", "tools", "tools_common", "legacy_adapter",
    "browser_sidecar", "manual_data", "prompt_examples", "reasoning_examples",
    "few_shot", "llm_engine", "vnext_reporter", "report_visual_coverage",
    "report_visual_regression", "chart_adapter_v6", "interactive_chart_workbench",
    "research_console", "open_research_console", "control_service", "console_run_all",
    "qqq_holdings", "chart_generator",
}
# 模块名 -> 文档中出现的检索词（下划线/大小写可能不同，统一用小写连续串匹配）
DOC_CANON = os.path.join(REPO_ROOT, "系统说明书.md")


def _module_tokens(module):
    """把 snake_case 模块名拆成关键 token 集合，去掉工具/层前缀。"""
    name = module.replace(".py", "")
    name = re.sub(r"^tools_", "", name)  # tools_L1 -> L1
    tokens = set(name.split("_"))
    return {t for t in tokens if len(t) >= 3}  # 去掉 ld/la 之类短噪音


def test_code_modules_are_acknowledged_in_docs():
    """代码侧每个核心业务模块，必须在《系统说明书》或 CLAUDE.md 里被提到。

    防止"架构长出新器官、文档零提及"复发。匹配方式是概念级子串：
    模块名任一 >=3 字符的 token（或 token 拼接）在文档里出现即算承认。
    """
    missing = []
    doc_text = _read(DOC_CANON) + "\n" + _read(os.path.join(REPO_ROOT, "CLAUDE.md"))
    doc_text_lower = doc_text.lower()

    for root, _dirs, files in os.walk(os.path.join(REPO_ROOT, "src")):
        for fname in files:
            if not fname.endswith(".py") or fname == "__init__.py":
                continue
            module = fname[:-3]
            if module in _DOC_EXEMPT:
                continue
            tokens = _module_tokens(module)
            if not tokens:
                continue
            # 任一 token 或"token 直接拼接"出现在文档即算承认（如 ledger、recompute_belt）
            hit = any(t in doc_text_lower for t in tokens) or any(
                t1 + t2 in doc_text_lower for t1 in tokens for t2 in tokens if t1 != t2
            )
            if not hit:
                missing.append(f"src/**/{fname}")

    assert not missing, (
        f"以下代码模块在任何核心文档中都未被提及——架构长出新器官而文档没跟上："
        f"{sorted(missing)}。请在《系统说明书》或 CLAUDE.md 中补充对应概念，"
        "不要删模块名硬凑测试。"
    )
