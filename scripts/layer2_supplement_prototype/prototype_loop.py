# -*- coding: utf-8 -*-
"""T49-3 第二层补采原型：自焊小循环。

循环：planner（LLM，用 llm_engine 的 `call_with_fallback`，只给工具清单与议程）
→ 执行器（只允许白名单工具，工具返回全部进下一轮上下文）
→ reader（LLM，把本轮工具材料收成 0-2 张材料卡）
→ 机器校验（四条镣铐）
→ 校验失败带错误重试 ≤2 次
→ 下一轮。

产物（全部写在 run 目录内）：
- `materials.jsonl`：每条一张候选材料卡
- `run_summary.json`：运行汇总
- `prototype_audit/`：每轮 planner/reader 的 prompt 与响应落盘，能 grep
- `fetched_cache/`：fetch_official_url 抓取正文缓存，带 UTC 时间戳元数据

本模块不实际联网跑真实任务（真实任务由根线程另行执行）；网络工具只做实现，
测试用 fake http_get 注入网络行为。
"""
from __future__ import annotations

import argparse
import functools
import hashlib
import json
import re
import sys
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# 机器可查常量（域名白名单与四条镣铐都从这里 grep / import，不散落在逻辑里）
# ---------------------------------------------------------------------------

REPO_ROOT = Path(__file__).resolve().parents[2]

# 独立运行（不靠 PYTHONPATH）时也能 import 到 `src.*`：
# 把 repo 根与 repo/src 都放进 sys.path，`_build_default_engine` 再兜底一次。
for _sys_path in (str(REPO_ROOT), str(REPO_ROOT / "src")):
    if _sys_path not in sys.path:
        sys.path.insert(0, _sys_path)

# 材料卡治理行：每张卡都带这一行。
GOVERNANCE_NOTE = "本材料是第二层候选材料，判断以第一层数据为准"

# 循环上限（任务书：max_rounds ≤ 4；reader 校验失败重试 ≤ 2 次；每轮 0-2 张卡）。
MAX_ROUNDS_LIMIT = 4
READER_MAX_CARDS = 2
READER_RETRY_LIMIT = 2
MAX_TOOL_CALLS_PER_ROUND = 4  # 防御性上限：planner 每轮最多 4 个只读工具调用

# 网络工具常量。
FETCH_DEFAULT_MAX_CHARS = 6000
FETCH_MAX_CHARS_CAP = 20000
FETCH_TIMEOUT_SECONDS = 20
FETCH_REDIRECT_MAX_HOPS = 5  # 防御性上限（真实跳数校验由 response.geturl() 复核）

# read_local_material 单文件大小上限。
READ_LOCAL_MAX_BYTES = 200 * 1024

# collected_at_utc 允许的最大未来偏移：现在 + 5 分钟。
FUTURE_SKEW_TOLERANCE_SECONDS = 300

# 官方/主流域名白名单（写死在脚本里，https only）。
# 匹配规则：host == domain 或 host 以 "." + domain 结尾（覆盖 www 与子域）。
ALLOWED_FETCH_DOMAINS: Tuple[str, ...] = (
    "sec.gov",            # SEC（含 data.sec.gov EDGAR）
    "federalreserve.gov",  # Federal Reserve / FRB
    "newyorkfed.org",      # FRBNY
    "stlouisfed.org",      # FRED 数据
    "nasdaq.com",          # NASDAQ
    "cftc.gov",            # CFTC
    "finra.org",           # FINRA
    "bea.gov",             # BEA
    "bls.gov",             # BLS
    "treasurydirect.gov",  # TreasuryDirect
)

# 工具白名单（首版两个，都只读；fetch 写缓存到 run 目录的 fetched_cache/）。
TOOL_WHITELIST: Tuple[str, ...] = ("read_local_material", "fetch_official_url")

# 四条镣铐 · 字段名与枚举。
CARD_FIELDS: Tuple[str, ...] = (
    "card_id",
    "agenda_id",
    "fact_summary",
    "interpretation",
    "source_tier",
    "source_url",
    "collected_at_utc",
    "needs_data_confirmation",
    "limitations",
)
SOURCE_TIER_VALUES: Tuple[str, ...] = (
    "official",
    "primary_news",
    "aggregator_news",
    "weak_social",
    "unverified",
)

# 材料卡允许出现的全部字段：9 个 schema 字段 + 1 个治理行字段。之外的未知字段拒绝。
ALLOWED_CARD_FIELDS = frozenset(CARD_FIELDS) | {"governance_note"}

# fact_summary 不得含这些中文措辞（任务书点名"可能/预计/暗示"类；校验前会归一化
# 去空白、全半角，因此"可 能"、"可　能"也会命中）。
FACT_HEDGE_WORDS_CN: Tuple[str, ...] = (
    "可能",
    "也许",
    "预计",
    "暗示",
    "或将",
    "有望",
    "估计",
    "猜测",
    "大概",
    "或许",
)

# fact_summary 不得含这些英文措辞（大小写归一化后按整词匹配）。
FACT_HEDGE_WORDS_EN: Tuple[str, ...] = (
    "may",
    "might",
    "could",
    "likely",
    "expected",
    "expects",
    "possibly",
    "perhaps",
    "maybe",
    "probably",
    "would",
    "should",
)

# interpretation 必须含这些假设标记之一（无单字"或"，避免命中普通"或者"）。
INTERPRETATION_MARKERS: Tuple[str, ...] = (
    "可能",
    "假设",
    "推测",
    "猜想",
    "若",
    "也许",
    "或许",
    "不排除",
    "待确认",
)

# read_local_material 允许读的 investigation_reports/ 文件扩展名白名单。
INVESTIGATION_REPORTS_READ_EXTENSIONS: Tuple[str, ...] = (".md", ".json")

# LLM stage 名（grep / fake engine 都按这个键）。
PLANNER_STAGE = "layer2_planner"
READER_STAGE = "layer2_reader"


# ---------------------------------------------------------------------------
# 时间与路径小工具
# ---------------------------------------------------------------------------

def _utc_now() -> datetime:
    """可被测试替换的 UTC 现在。"""
    return datetime.now(timezone.utc)


def parse_utc_iso(value: Any) -> Optional[datetime]:
    """解析 ISO 8601 UTC 时间；兼容 'Z' 后缀与无时区的朴素时间（按 UTC 解读）。"""
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z") or text.endswith("z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_within(path: Path, root: Path) -> bool:
    try:
        return path.resolve().is_relative_to(root.resolve())
    except ValueError:
        return False


def _host_allowed(host: str) -> bool:
    host = host.lower().strip()
    for domain in ALLOWED_FETCH_DOMAINS:
        if host == domain or host.endswith("." + domain):
            return True
    return False


def _normalize_text(text: str) -> Tuple[str, str]:
    """校验前归一化：NFKC（全半角/全角空格）→ casefold（英文大小写）→ 去空白。

    返回两个变体：
    - no_space：去空白后的文本，用于中文子串匹配（"可 能" → "可能"）。
    - with_space：保留空白（仅 NFKC + casefold），用于英文整词匹配（"may not"
      去掉空白会变成 "maynot" 导致整词边界失效）。
    """
    nfkc = unicodedata.normalize("NFKC", text).casefold()
    no_space = re.sub(r"[\s\u200b\u200c\u200d\ufeff]+", "", nfkc)
    return no_space, nfkc


def _contains_english_word(text: str, word: str) -> bool:
    """英文整词匹配（小写文本，避免把 "maybe" 的 "may" 当命中，也避免 "dis-may"?）。"""
    return re.search(r"(?<![a-z])" + re.escape(word) + r"(?![a-z])", text) is not None


def _validate_fetch_url(url: str) -> Optional[str]:
    """校验 URL scheme + host，返回错误码；合法返回 None。"""
    try:
        parsed = urllib.parse.urlparse(url)
    except ValueError:
        return "url_invalid"
    if parsed.scheme.lower() != "https":
        return "url_not_https"
    host = (parsed.hostname or "").lower()
    if not host or not _host_allowed(host):
        return "domain_not_allowed"
    return None


def _default_http_get(url: str, timeout: int, max_chars: int = FETCH_DEFAULT_MAX_CHARS) -> Tuple[str, str]:
    """真实抓取（真实任务由根线程执行时才会用到）。

    返回 (text, final_url)。urllib 会自动跟随 301/302/307 等重定向，这里用
    `response.geturl()` 拿到最终 URL 交给调用方复核 scheme+host；读取时按
    `max_chars + 1` 字节受限读取，不全文读入。
    """
    request = urllib.request.Request(url, headers={"User-Agent": "ndx-layer2-supplement-prototype/0.1"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        raw = response.read(max_chars + 1)
        text = raw.decode(charset, errors="replace")
        return text, response.geturl()


# ---------------------------------------------------------------------------
# 四条镣铐 · 机器校验
# ---------------------------------------------------------------------------

def validate_material_card(card: Dict[str, Any], now_utc: Optional[datetime] = None) -> List[str]:
    """逐字段校验材料卡，返回错误码列表（空列表 = 通过）。

    错误码全部是机器可 grep 的固定字符串，例如：
    `missing_field:fact_summary`、`fact_summary_hedge_word:可能`、
    `fact_summary_hedge_word_en:may`、`fact_summary_not_string`、
    `interpretation_missing_hypothesis_marker`、`source_tier_illegal`、
    `needs_data_confirmation_empty_or_invalid`、`collected_at_utc_in_future`、
    `unknown_field:xxx`。
    """
    errors: List[str] = []
    if not isinstance(card, dict):
        return ["card_not_object"]

    for key in card.keys():
        if key not in ALLOWED_CARD_FIELDS:
            errors.append(f"unknown_field:{key}")

    for field in CARD_FIELDS:
        if field not in card:
            errors.append(f"missing_field:{field}")

    if card.get("governance_note") != GOVERNANCE_NOTE:
        errors.append("governance_note_invalid")

    fact_raw = card.get("fact_summary")
    if not isinstance(fact_raw, str):
        errors.append("fact_summary_not_string")
        fact = ""
    else:
        fact = fact_raw.strip()

    interpretation_raw = card.get("interpretation")
    if not isinstance(interpretation_raw, str):
        errors.append("interpretation_not_string")
        interpretation = ""
    else:
        interpretation = interpretation_raw.strip()

    if not fact:
        errors.append("fact_summary_empty")
    else:
        fact_no_space, fact_with_space = _normalize_text(fact)
        for word in FACT_HEDGE_WORDS_CN:
            if word in fact_no_space:
                errors.append(f"fact_summary_hedge_word:{word}")
        for word in FACT_HEDGE_WORDS_EN:
            if _contains_english_word(fact_with_space, word):
                errors.append(f"fact_summary_hedge_word_en:{word}")

    if not interpretation:
        errors.append("interpretation_empty")
    else:
        interp_no_space, _ = _normalize_text(interpretation)
        if not any(marker in interp_no_space for marker in INTERPRETATION_MARKERS):
            errors.append("interpretation_missing_hypothesis_marker")

    if fact and interpretation:
        fact_no_space, _ = _normalize_text(fact)
        interp_no_space, _ = _normalize_text(interpretation)
        if (
            fact_no_space == interp_no_space
            or interp_no_space.startswith(fact_no_space)
            or fact_no_space.startswith(interp_no_space)
        ):
            errors.append("fact_interpretation_not_separated")

    if card.get("source_tier") not in SOURCE_TIER_VALUES:
        errors.append("source_tier_illegal")

    source_url = card.get("source_url")
    if not isinstance(source_url, str) or not source_url.strip():
        errors.append("source_url_empty")
    else:
        source_url = source_url.strip()
        if source_url.startswith(("http://", "https://")):
            source_url_error = _validate_fetch_url(source_url)
            if source_url_error:
                errors.append(f"source_url_{source_url_error}")

    needs = card.get("needs_data_confirmation")
    if (
        not isinstance(needs, list)
        or len(needs) == 0
        or not all(isinstance(item, str) and item.strip() for item in needs)
    ):
        errors.append("needs_data_confirmation_empty_or_invalid")

    limitations = card.get("limitations")
    if not isinstance(limitations, list):
        errors.append("limitations_invalid")

    parsed_ts = parse_utc_iso(card.get("collected_at_utc"))
    if parsed_ts is None:
        errors.append("collected_at_utc_invalid_iso")
    else:
        now = now_utc or _utc_now()
        if parsed_ts > now + timedelta(seconds=FUTURE_SKEW_TOLERANCE_SECONDS):
            errors.append("collected_at_utc_in_future")

    return errors


# ---------------------------------------------------------------------------
# 白名单工具实现（都只读；fetch 写缓存到 run 目录）
# ---------------------------------------------------------------------------

def _tool_error(tool: str, error_code: str, error: str, **extra: Any) -> Dict[str, Any]:
    result = {"tool": tool, "ok": False, "error_code": error_code, "error": error}
    result.update(extra)
    return result


def _read_local_material(args: Dict[str, Any], *, run_dir: Path, repo_root: Path, **_kwargs: Any) -> Dict[str, Any]:
    raw_path = args.get("path")
    if not isinstance(raw_path, str) or not raw_path.strip():
        return _tool_error("read_local_material", "path_missing", "缺少字符串参数 path")

    path = Path(raw_path)
    if path.is_absolute():
        return _tool_error("read_local_material", "absolute_path_denied", f"只接受相对路径：{raw_path!r}")

    # 以 `investigation_reports/` 开头的路径按 repo 根解析，只读其下白名单扩展名；
    # 其余相对路径一律按 run 目录解析。
    if path.parts and path.parts[0] == "investigation_reports":
        repo_root_resolved = repo_root.resolve()
        inv_root = (repo_root_resolved / "investigation_reports").resolve()
        candidate_inv = (repo_root_resolved / path).resolve()
        if not _is_within(candidate_inv, inv_root):
            return _tool_error("read_local_material", "outside_allowed_roots", f"路径逃出 investigation_reports/：{raw_path}")
        if not candidate_inv.is_file():
            return _tool_error("read_local_material", "file_not_found_in_investigation_reports", f"investigation_reports/ 下不存在：{raw_path}")
        if candidate_inv.suffix.lower() not in INVESTIGATION_REPORTS_READ_EXTENSIONS:
            return _tool_error(
                "read_local_material",
                "extension_not_whitelisted",
                f"investigation_reports/ 下只读白名单扩展名 {list(INVESTIGATION_REPORTS_READ_EXTENSIONS)}：{raw_path}",
            )
        try:
            if candidate_inv.stat().st_size > READ_LOCAL_MAX_BYTES:
                return _tool_error(
                    "read_local_material",
                    "file_too_large",
                    f"文件超过 {READ_LOCAL_MAX_BYTES} 字节上限：{raw_path}",
                )
            text = candidate_inv.read_text(encoding="utf-8")
        except OSError as exc:
            return _tool_error("read_local_material", "file_read_error", f"文件读取失败：{type(exc).__name__}: {exc}")
        except UnicodeDecodeError:
            return _tool_error("read_local_material", "not_utf8_text", f"文件不是 UTF-8 文本：{raw_path}")
        return {"tool": "read_local_material", "ok": True, "path": raw_path, "text": text}

    run_root = run_dir.resolve()
    candidate_run = (run_dir / path).resolve()
    if not _is_within(candidate_run, run_root):
        return _tool_error("read_local_material", "outside_allowed_roots", f"路径不在 run 目录或 investigation_reports/ 白名单内：{raw_path}")
    if not candidate_run.is_file():
        return _tool_error("read_local_material", "file_not_found_in_run_dir", f"run 目录内不存在：{raw_path}")
    try:
        if candidate_run.stat().st_size > READ_LOCAL_MAX_BYTES:
            return _tool_error(
                "read_local_material",
                "file_too_large",
                f"文件超过 {READ_LOCAL_MAX_BYTES} 字节上限：{raw_path}",
            )
        text = candidate_run.read_text(encoding="utf-8")
    except OSError as exc:
        return _tool_error("read_local_material", "file_read_error", f"文件读取失败：{type(exc).__name__}: {exc}")
    except UnicodeDecodeError:
        return _tool_error("read_local_material", "not_utf8_text", f"文件不是 UTF-8 文本：{raw_path}")
    return {"tool": "read_local_material", "ok": True, "path": raw_path, "text": text}


def _fetch_official_url(
    args: Dict[str, Any],
    *,
    run_dir: Path,
    fetched_cache_dir: Path,
    http_get: Optional[Callable[[str, int], str]] = None,
    now_utc_fn: Optional[Callable[[], datetime]] = None,
    **_kwargs: Any,
) -> Dict[str, Any]:
    url = args.get("url")
    if not isinstance(url, str) or not url.strip():
        return _tool_error("fetch_official_url", "url_missing", "缺少字符串参数 url")

    initial_error = _validate_fetch_url(url)
    if initial_error:
        return _tool_error("fetch_official_url", initial_error, f"URL 未通过 scheme/域名白名单校验（{initial_error}）：{url!r}")

    try:
        max_chars = int(args.get("max_chars", FETCH_DEFAULT_MAX_CHARS))
    except (TypeError, ValueError):
        return _tool_error("fetch_official_url", "max_chars_invalid", f"max_chars 必须是整数：{args.get('max_chars')!r}")
    max_chars = max(1, min(max_chars, FETCH_MAX_CHARS_CAP))

    fetched_at = (now_utc_fn or _utc_now)()
    try:
        getter = http_get or functools.partial(_default_http_get, max_chars=max_chars)
        fetch_result = getter(url, FETCH_TIMEOUT_SECONDS)
    except Exception as exc:
        return _tool_error(
            "fetch_official_url",
            "network_error",
            f"网络失败如实返回：{type(exc).__name__}: {exc}",
            url=url,
            fetched_at_utc=fetched_at.isoformat(),
        )

    if isinstance(fetch_result, tuple) and len(fetch_result) == 2:
        text, final_url = fetch_result
    else:
        text, final_url = fetch_result, url

    if not isinstance(text, str):
        return _tool_error("fetch_official_url", "network_error", f"网络返回不是文本：{type(text).__name__}", url=url)

    if not isinstance(final_url, str) or not final_url.strip():
        final_url = url
    final_url = final_url.strip()

    # 重定向复核：urllib 会自动跟随 301/302/307 等，这里对最终 URL 再过一次
    # scheme+host 白名单，目标逃逸白名单时如实报错、不落缓存。
    if final_url != url:
        final_error = _validate_fetch_url(final_url)
        if final_error:
            return _tool_error(
                "fetch_official_url",
                f"redirect_{final_error}",
                f"重定向目标未通过白名单校验（{final_error}）：{final_url}",
                url=url,
                final_url=final_url,
                fetched_at_utc=fetched_at.isoformat(),
            )

    truncated = text[:max_chars]
    cache_dir = fetched_cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]
    body_file = cache_dir / f"{digest}.txt"
    meta_file = cache_dir / f"{digest}.meta.json"
    body_file.write_text(truncated, encoding="utf-8")
    meta_file.write_text(
        json.dumps(
            {
                "url": url,
                "final_url": final_url,
                "fetched_at_utc": fetched_at.isoformat(),
                "char_count": len(truncated),
                "truncated": len(text) > max_chars,
                "cache_file": body_file.name,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    return {
        "tool": "fetch_official_url",
        "ok": True,
        "url": url,
        "final_url": final_url,
        "fetched_at_utc": fetched_at.isoformat(),
        "char_count": len(truncated),
        "truncated": len(text) > max_chars,
        "cache_file": str(body_file),
        "text": truncated,
    }


def execute_tool_call(
    name: str,
    args: Dict[str, Any],
    *,
    run_dir: Path,
    repo_root: Path,
    fetched_cache_dir: Optional[Path] = None,
    http_get: Optional[Callable[[str, int], str]] = None,
    now_utc_fn: Optional[Callable[[], datetime]] = None,
) -> Dict[str, Any]:
    """执行一次白名单工具调用；白名单外调用直接拒绝（不执行、不落盘）。"""
    run_dir = Path(run_dir)
    repo_root = Path(repo_root)
    cache_dir = Path(fetched_cache_dir) if fetched_cache_dir else run_dir / "fetched_cache"

    if name not in TOOL_WHITELIST:
        return _tool_error(name, "tool_not_whitelisted", f"工具 {name!r} 不在白名单 {list(TOOL_WHITELIST)}")

    if name == "read_local_material":
        return _read_local_material(args, run_dir=run_dir, repo_root=repo_root)
    if name == "fetch_official_url":
        return _fetch_official_url(
            args,
            run_dir=run_dir,
            fetched_cache_dir=cache_dir,
            http_get=http_get,
            now_utc_fn=now_utc_fn,
        )
    return _tool_error(name, "tool_not_implemented", f"工具 {name!r} 在白名单但未实现")


# ---------------------------------------------------------------------------
# LLM JSON 提取与 prompt 构建
# ---------------------------------------------------------------------------

def _extract_json(engine: Any, raw: Optional[str], stage: str) -> Optional[Dict[str, Any]]:
    if raw is None:
        return None
    extractor = getattr(engine, "extract_json", None)
    if callable(extractor):
        try:
            parsed = extractor(raw, stage)
        except Exception:
            parsed = None
        if isinstance(parsed, dict):
            return parsed
    try:
        parsed = json.loads(raw)
    except Exception:
        return None
    return parsed if isinstance(parsed, dict) else None


def _save_audit_text(run_dir: Path, filename: str, content: str) -> None:
    audit_dir = run_dir / "prototype_audit"
    audit_dir.mkdir(parents=True, exist_ok=True)
    (audit_dir / filename).write_text(content, encoding="utf-8")


def _serialize_tool_results(results: List[Dict[str, Any]]) -> str:
    return json.dumps(results, ensure_ascii=False, indent=2, default=str)


def _build_planner_prompt(
    agenda_id: str,
    question: str,
    round_no: int,
    max_rounds: int,
    prior_context: List[Dict[str, Any]],
) -> str:
    context_text = _serialize_tool_results(prior_context) if prior_context else "（空）"
    tool_lines = [
        "1. read_local_material(path)：只读 run 目录或 investigation_reports/ 下的白名单文件（.md/.json）。path 是相对路径。",
        "2. fetch_official_url(url, max_chars=6000)：只允许 https，只允许官方/主流域名白名单"
        "（SEC/FRB/FederalReserve/NASDAQ/CFTC/FINRA/BEA/BLS 等，写死在脚本里）；"
        "抓取正文存 fetched_cache/（带 UTC 时间戳）并返回截断文本。网络失败会如实返回错误。",
    ]
    return (
        "你是第二层补采原型的 planner。任务议程：\n"
        f"- agenda_id: {agenda_id}\n"
        f"- question: {question}\n"
        f"当前第 {round_no} / {max_rounds} 轮。\n\n"
        "你只能从下列白名单工具中选择（args 里不得出现白名单外的工具名）：\n"
        + "\n".join(tool_lines)
        + "\n\n纪律：\n"
        "- 你不许写数据层、第一层产物，也不许下任何结论；你只负责为补采选择本轮工具调用。\n"
        f"- 每轮最多 {MAX_TOOL_CALLS_PER_ROUND} 个工具调用，工具全部只读。\n"
        "- 输出严格 JSON，不要输出任何 JSON 之外的文本。\n\n"
        "输出格式：{\"tools\":[{\"tool\":\"read_local_material\",\"args\":{\"path\":\"...\"}}]}\n\n"
        f"上一轮及之前工具返回的上下文（如无则为空）：\n{context_text}"
    )


def _build_reader_prompt(
    agenda_id: str,
    question: str,
    round_no: int,
    tool_results: List[Dict[str, Any]],
    retry_errors: Optional[List[str]] = None,
) -> str:
    retry_block = ""
    if retry_errors:
        retry_block = "\n\n上一版被机器校验打回，错误如下（逐条修正后再输出）：\n" + "\n".join(
            f"- {error}" for error in retry_errors
        )
    return (
        "你是第二层补采原型的 reader。任务议程：\n"
        f"- agenda_id: {agenda_id}\n"
        f"- question: {question}\n"
        f"本轮（第 {round_no} 轮）工具返回如下（全部来自白名单只读工具）：\n"
        f"{_serialize_tool_results(tool_results)}\n\n"
        f"请把本轮工具材料收成 0-{READER_MAX_CARDS} 张候选材料卡（没有合格材料就输出空数组）。"
        "每张卡你只填这些字段：fact_summary, interpretation, source_tier, source_url, "
        "needs_data_confirmation, limitations。\n"
        "机器会自动补 card_id / agenda_id / collected_at_utc / governance_note。\n\n"
        "四条镣铐（机器会逐字段校验，不满足会被打回）：\n"
        "1. fact_summary 与 interpretation 都必须非空且内容分离：fact_summary 只写材料原文里的事实，"
        f"不得含 {list(FACT_HEDGE_WORDS_CN)} 或 {list(FACT_HEDGE_WORDS_EN)} 类措辞；"
        "interpretation 是假设性解读，"
        f"必须含假设标记（如 {list(INTERPRETATION_MARKERS)} 之一）。\n"
        f"2. source_tier 必须是 {list(SOURCE_TIER_VALUES)} 之一。\n"
        "3. collected_at_utc 由机器填，必须是 ISO 时间且不晚于现在+5分钟。\n"
        "4. needs_data_confirmation 必须是非空数组：写\"需要第一层哪些数据确认\"。\n\n"
        f"纪律：{GOVERNANCE_NOTE}；不许下结论。\n"
        "输出严格 JSON，格式："
        "{\"cards\":[{\"fact_summary\":\"...\",\"interpretation\":\"...\",\"source_tier\":\"official\","
        "\"source_url\":\"...\",\"needs_data_confirmation\":[\"...\"],\"limitations\":[\"...\"]}]}"
        + retry_block
    )


# ---------------------------------------------------------------------------
# 主循环
# ---------------------------------------------------------------------------

def _validate_task(task: Dict[str, Any]) -> Tuple[str, str, int, List[str]]:
    """校验任务输入，返回 (agenda_id, question, max_rounds, errors)。"""
    errors: List[str] = []
    if not isinstance(task, dict):
        return "", "", 0, ["task_not_object"]

    agenda_id = str(task.get("agenda_id") or "").strip()
    question = str(task.get("question") or "").strip()
    if not agenda_id:
        errors.append("agenda_id_missing")
    if not question:
        errors.append("question_missing")

    max_rounds = task.get("max_rounds")
    if max_rounds is None:
        errors.append("max_rounds_missing")
        max_rounds_value = 0
    else:
        try:
            max_rounds_value = int(max_rounds)
        except (TypeError, ValueError):
            errors.append("max_rounds_not_integer")
            max_rounds_value = 0
        else:
            if not 1 <= max_rounds_value <= MAX_ROUNDS_LIMIT:
                errors.append(f"max_rounds_out_of_range:需要 1..{MAX_ROUNDS_LIMIT}，实际 {max_rounds_value}")

    return agenda_id, question, max_rounds_value, errors


def run_prototype(
    task: Dict[str, Any],
    run_dir: Any,
    llm_engine: Any,
    *,
    repo_root: Any = None,
    runs_root: Any = None,
    http_get: Optional[Callable[[str, int], str]] = None,
    now_utc_fn: Optional[Callable[[], datetime]] = None,
    fetched_cache_dir: Any = None,
    models: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """执行一次补采小循环。真实任务由根线程另行执行，本函数只实现 + 被单测驱动。

    task: {"agenda_id": str, "question": str, "max_rounds": int(≤4)}
    run_dir: 本轮 run 目录（materials.jsonl / run_summary.json / prototype_audit/ / fetched_cache/ 都写这里）
    runs_root: run_dir 必须位于其下；默认 `<repo_root>/scripts/layer2_supplement_prototype/runs/`。
    llm_engine: 复用 llm_engine 的 `call_with_fallback`；测试传 Fake/SequencedFake。
    models: CLI 请求的模型 key 清单；与引擎最近成功模型一起写进 run_summary.models。
    """
    agenda_id, question, max_rounds, task_errors = _validate_task(task)
    if task_errors:
        raise ValueError("task_invalid: " + "; ".join(task_errors))

    repo_root = Path(repo_root) if repo_root is not None else REPO_ROOT
    run_dir = Path(run_dir)
    effective_runs_root = Path(runs_root) if runs_root is not None else repo_root / "scripts" / "layer2_supplement_prototype" / "runs"
    if not _is_within(run_dir, effective_runs_root):
        raise ValueError(
            f"run_dir_outside_runs_root: run_dir={run_dir}，必须位于 {effective_runs_root.resolve()}"
        )
    run_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = Path(fetched_cache_dir) if fetched_cache_dir is not None else run_dir / "fetched_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    now_fn = now_utc_fn or _utc_now

    materials_path = run_dir / "materials.jsonl"
    started_at = now_fn()

    summary: Dict[str, Any] = {
        "schema_version": "layer2_prototype_run_v1",
        "status": "completed",
        "agenda_id": agenda_id,
        "question": question,
        "max_rounds": max_rounds,
        "started_at_utc": started_at.isoformat(),
        "run_dir": str(run_dir),
        "runs_root": str(effective_runs_root.resolve()),
        "models": {
            "requested": list(models) if models else None,
            "engine_available_models": list(getattr(llm_engine, "available_models", []) or []),
            "planner_success_model": None,
            "reader_success_model": None,
        },
        "rounds": [],
        "total_cards": 0,
        "rejected_tool_calls": [],
        "materials_file": "materials.jsonl",
        "governance_note": GOVERNANCE_NOTE,
    }

    # 上一轮及之前所有工具返回，全部进下一轮 planner 上下文。
    prior_context: List[Dict[str, Any]] = []

    for round_no in range(1, max_rounds + 1):
        round_record: Dict[str, Any] = {
            "round": round_no,
            "planner_ok": False,
            "tool_calls": [],
            "tool_results": [],
            "reader_ok": False,
            "reader_retries": 0,
            "cards_produced": 0,
            "validation_errors": [],
        }

        # ---- planner ----
        planner_prompt = _build_planner_prompt(agenda_id, question, round_no, max_rounds, prior_context)
        _save_audit_text(run_dir, f"round_{round_no:03d}_planner_prompt.md", planner_prompt)
        planner_raw = llm_engine.call_with_fallback(planner_prompt, stage_name=PLANNER_STAGE)
        if planner_raw is not None:
            summary["models"]["planner_success_model"] = getattr(llm_engine, "successful_model", None)
        _save_audit_text(run_dir, f"round_{round_no:03d}_planner_response.txt", str(planner_raw))

        plan = _extract_json(llm_engine, planner_raw, PLANNER_STAGE)
        if plan is None:
            round_record["validation_errors"].append("planner_json_invalid")
            summary["rounds"].append(round_record)
            continue

        tool_calls = plan.get("tools") if isinstance(plan.get("tools"), list) else None
        if tool_calls is None:
            round_record["validation_errors"].append("planner_tools_not_list")
            summary["rounds"].append(round_record)
            continue

        round_record["planner_ok"] = True
        tool_calls = tool_calls[:MAX_TOOL_CALLS_PER_ROUND]

        # ---- 执行器：只允许白名单工具；全部返回进下一轮上下文 ----
        for call_item in tool_calls:
            if not isinstance(call_item, dict):
                round_record["tool_results"].append(_tool_error("(malformed)", "malformed_tool_call", "工具调用项不是对象"))
                continue
            tool_name = str(call_item.get("tool") or "")
            tool_args = call_item.get("args") if isinstance(call_item.get("args"), dict) else {}
            round_record["tool_calls"].append({"tool": tool_name, "args": tool_args})

            result = execute_tool_call(
                tool_name,
                tool_args,
                run_dir=run_dir,
                repo_root=repo_root,
                fetched_cache_dir=cache_dir,
                http_get=http_get,
                now_utc_fn=now_fn,
            )
            if not result.get("ok"):
                if result.get("error_code") == "tool_not_whitelisted":
                    summary["rejected_tool_calls"].append(
                        {"round": round_no, "tool": tool_name, "args": tool_args, "error_code": "tool_not_whitelisted"}
                    )
                round_record["validation_errors"].append(
                    f"tool_call_rejected:{tool_name}:{result.get('error_code')}"
                )
            round_record["tool_results"].append(result)
            prior_context.append(result)

        # ---- reader + 四条镣铐校验，失败带错误重试 ≤2 次 ----
        round_tool_results = round_record["tool_results"]
        cards_produced_this_round = 0
        last_validation_errors: List[str] = []

        for attempt in range(READER_RETRY_LIMIT + 1):
            retry_suffix = "" if attempt == 0 else f"_retry_{attempt}"
            if attempt > 0:
                round_record["reader_retries"] = attempt
            retry_errors = last_validation_errors if attempt > 0 else None
            reader_prompt = _build_reader_prompt(agenda_id, question, round_no, round_tool_results, retry_errors)
            _save_audit_text(run_dir, f"round_{round_no:03d}_reader_prompt{retry_suffix}.md", reader_prompt)
            reader_raw = llm_engine.call_with_fallback(reader_prompt, stage_name=READER_STAGE)
            if reader_raw is not None:
                summary["models"]["reader_success_model"] = getattr(llm_engine, "successful_model", None)
            _save_audit_text(run_dir, f"round_{round_no:03d}_reader_response{retry_suffix}.txt", str(reader_raw))

            reader_data = _extract_json(llm_engine, reader_raw, READER_STAGE)
            if reader_data is None:
                last_validation_errors = ["reader_json_invalid"]
                continue

            cards_raw = reader_data.get("cards") if isinstance(reader_data.get("cards"), list) else None
            if cards_raw is None:
                last_validation_errors = ["reader_cards_not_list"]
                continue

            # 超量不静默截断：整批打回重试（≤2 次），由 reader 自己砍到 0-2 张。
            if len(cards_raw) > READER_MAX_CARDS:
                last_validation_errors = [f"reader_too_many_cards:上限{READER_MAX_CARDS}，实际{len(cards_raw)}"]
                continue

            round_record["reader_ok"] = True
            last_validation_errors = []
            round_cards: List[Dict[str, Any]] = []
            for index, card_raw in enumerate(cards_raw):
                if not isinstance(card_raw, dict):
                    last_validation_errors.append(f"card_{index + 1}_not_object")
                    continue
                card = dict(card_raw)
                # 机器补身份字段，模型不许填这些。
                card["card_id"] = f"{agenda_id}_r{round_no:02d}_c{index + 1}"
                card["agenda_id"] = agenda_id
                card["collected_at_utc"] = now_fn().isoformat()
                card["governance_note"] = GOVERNANCE_NOTE

                card_errors = validate_material_card(card, now_utc=now_fn())
                if card_errors:
                    last_validation_errors.extend(f"card_{index + 1}:" + error for error in card_errors)
                    continue
                round_cards.append(card)

            if last_validation_errors:
                continue

            # 全部通过（或 0 张卡）：落盘 materials.jsonl。
            for card in round_cards:
                with materials_path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(card, ensure_ascii=False) + "\n")
                cards_produced_this_round += 1
            break

        round_record["cards_produced"] = cards_produced_this_round
        summary["total_cards"] += cards_produced_this_round
        round_record["validation_errors"] = round_record["validation_errors"] + last_validation_errors
        summary["rounds"].append(round_record)

    if not materials_path.exists():
        materials_path.write_text("", encoding="utf-8")

    all_rounds_clean = all(len(round_record["validation_errors"]) == 0 for round_record in summary["rounds"])
    if all_rounds_clean:
        summary["status"] = "completed"
    elif summary["total_cards"] > 0:
        summary["status"] = "degraded"
    else:
        summary["status"] = "failed"

    summary["ended_at_utc"] = now_fn().isoformat()
    try:
        token_report = llm_engine.get_token_report()
        summary["token_usage"] = token_report
    except Exception:
        summary["token_usage"] = None

    (run_dir / "run_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )
    return summary


# ---------------------------------------------------------------------------
# CLI（真实任务由根线程另行执行，这里只提供入口）
# ---------------------------------------------------------------------------

def _resolve_model_keys(models_csv: Optional[str] = None) -> List[str]:
    """解析 CLI --models（逗号分隔）；缺省时用 config 全部已配置模型 key。"""
    try:
        from src.config import MODEL_CONFIGS
    except ImportError:  # 兼容把 src 当包根的方式
        from config import MODEL_CONFIGS

    if models_csv:
        keys = [item.strip() for item in models_csv.split(",") if item.strip()]
    else:
        keys = list(MODEL_CONFIGS.keys())
    return keys


def _build_default_engine(models_csv: Optional[str] = None):
    """懒加载真实 LLMEngine；只给根线程以后跑真实任务用。"""
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))
    if str(REPO_ROOT / "src") not in sys.path:
        sys.path.insert(0, str(REPO_ROOT / "src"))
    try:
        from src.agent_analysis.llm_engine import LLMEngine
    except ImportError:  # 兼容把 src 当包根的方式
        from agent_analysis.llm_engine import LLMEngine

    return LLMEngine(available_models=_resolve_model_keys(models_csv))


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="T49-3 第二层补采原型：自焊小循环（真实任务由根线程另行执行）")
    parser.add_argument("--task", required=True, help="JSON 任务文件路径，内容 {agenda_id, question, max_rounds≤4}")
    parser.add_argument("--run-dir", default=None, help="run 目录；默认 scripts/layer2_supplement_prototype/runs/<agenda_id>_<UTC 时间>")
    parser.add_argument("--models", default=None, help="逗号分隔的模型 key；默认用 config 全部模型")
    args = parser.parse_args(argv)

    task_path = Path(args.task)
    if not task_path.is_file():
        print(f"任务文件不存在：{task_path}", file=sys.stderr)
        return 2
    try:
        task = json.loads(task_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"任务文件不是合法 JSON：{exc}", file=sys.stderr)
        return 2

    run_dir = Path(args.run_dir) if args.run_dir else REPO_ROOT / "scripts" / "layer2_supplement_prototype" / "runs" / f"{task.get('agenda_id', 'task')}_{_utc_now().strftime('%Y%m%d_%H%M%S')}"

    model_keys = _resolve_model_keys(args.models)
    engine = _build_default_engine(args.models)
    try:
        summary = run_prototype(task, run_dir, engine, repo_root=REPO_ROOT, models=model_keys)
    except ValueError as exc:
        print(f"任务非法：{exc}", file=sys.stderr)
        return 2

    print(json.dumps(summary, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
