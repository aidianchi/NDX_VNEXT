from __future__ import annotations

import argparse
import json
import logging
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

try:
    from .config import path_config
    from .tools_L4 import _parse_trendonify_ndx_pe
except ImportError:
    from config import path_config
    from tools_L4 import _parse_trendonify_ndx_pe

logger = logging.getLogger(__name__)

TRENDONIFY_VALUATION_URLS = {
    "trailing_pe": "https://trendonify.com/united-states/stock-market/nasdaq-100/pe-ratio",
    "forward_pe": "https://trendonify.com/united-states/stock-market/nasdaq-100/forward-pe-ratio",
}


Runner = Callable[[Sequence[str], int], subprocess.CompletedProcess[str]]


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _default_runner(args: Sequence[str], timeout: int) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(args),
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _parse_bb_browser_eval_stdout(stdout: str) -> str:
    text = stdout.strip()
    if not text:
        return ""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return text

    candidates = [
        payload.get("result"),
        payload.get("value"),
        payload.get("text"),
        payload.get("stdout"),
        payload.get("data"),
    ]
    for candidate in candidates:
        if isinstance(candidate, str):
            return candidate
        if isinstance(candidate, dict):
            for key in ("value", "result", "text"):
                if isinstance(candidate.get(key), str):
                    return candidate[key]
    return text


def collect_page_text_with_bb_browser(
    url: str,
    *,
    timeout: int = 45,
    wait_seconds: float = 3.0,
    runner: Runner = _default_runner,
) -> Dict[str, Any]:
    commands: List[Dict[str, Any]] = []

    def run_step(args: Sequence[str], step_timeout: int) -> subprocess.CompletedProcess[str]:
        result = runner(args, step_timeout)
        commands.append(
            {
                "args": list(args),
                "returncode": result.returncode,
                "stderr_tail": (result.stderr or "")[-500:],
            }
        )
        return result

    daemon = run_step(["bb-browser", "daemon", "start", "--json"], timeout)
    daemon_text = f"{daemon.stderr or ''}\n{daemon.stdout or ''}".lower()
    # E1 P0 fix: a non-zero daemon-start return code must be reported here, at
    # the daemon step, as a daemon failure. Previously, error text merely
    # mentioning "cdp is reachable" (which can appear inside a failure message
    # explaining *why* CDP is not reachable) was treated the same as "already
    # running" and let the raise slide — the real daemon failure only
    # surfaced later, misattributed, when the subsequent `open` step also
    # failed with an unrelated-looking error. "already" (daemon already
    # running) remains the only benign non-zero case.
    if daemon.returncode != 0 and "already" not in daemon_text:
        raise RuntimeError(f"bb-browser daemon start failed: {(daemon.stderr or daemon.stdout)[-500:]}")

    opened = run_step(["bb-browser", "open", url, "--json"], timeout)
    if opened.returncode != 0:
        raise RuntimeError(f"bb-browser open failed: {(opened.stderr or opened.stdout)[-500:]}")

    expression = "document.body ? document.body.innerText : ''"
    page_text = ""
    evaluated: Optional[subprocess.CompletedProcess[str]] = None
    attempts = max(1, int(max(wait_seconds, 1.0) // 2) + 1)
    for attempt in range(attempts):
        time.sleep(2 if attempt else max(0.0, min(wait_seconds, 2.0)))
        evaluated = run_step(["bb-browser", "eval", expression, "--json"], timeout)
        if evaluated.returncode != 0:
            raise RuntimeError(f"bb-browser eval failed: {(evaluated.stderr or evaluated.stdout)[-500:]}")
        page_text = _parse_bb_browser_eval_stdout(evaluated.stdout)
        lowered = page_text.lower()
        if "cloudflare" not in lowered and "安全验证" not in page_text and "checking your browser" not in lowered:
            break

    return {
        "url": url,
        "text": page_text,
        "commands": commands,
    }


def collect_trendonify_valuation_sidecar(
    *,
    trusted: bool = False,
    timeout: int = 45,
    wait_seconds: float = 3.0,
    runner: Runner = _default_runner,
) -> Dict[str, Any]:
    pages: List[Dict[str, Any]] = []
    source_errors: List[Dict[str, Any]] = []

    for key, url in TRENDONIFY_VALUATION_URLS.items():
        try:
            collected = collect_page_text_with_bb_browser(
                url,
                timeout=timeout,
                wait_seconds=wait_seconds,
                runner=runner,
            )
            page_text = collected["text"]
            parsed = _parse_trendonify_ndx_pe(page_text, forward=(key == "forward_pe"))
            pages.append(
                {
                    "page_type": key,
                    "url": url,
                    "collected_at_utc": _utc_now_iso(),
                    "source_tier": "browser_sidecar_public_page",
                    "requires_user_trust": True,
                    "user_trusted": trusted,
                    "parse_status": "ok" if parsed.get("availability") == "available" or parsed.get("value") is not None else "unavailable",
                    "parsed": parsed,
                    "text_excerpt": page_text[:1800],
                    "bb_browser_steps": collected["commands"],
                }
            )
        except Exception as exc:
            source_errors.append(
                {
                    "page_type": key,
                    "url": url,
                    "error": str(exc)[:600],
                    "collected_at_utc": _utc_now_iso(),
                }
            )

    return {
        "schema_version": "browser_sidecar_v1",
        "source": "trendonify_ndx_valuation",
        "generated_at_utc": _utc_now_iso(),
        "policy": {
            "runtime_context_rule": "Browser sidecar output is not injected into L1-L5 layer-local prompts.",
            "usage_rule": "Use only after explicit user trust/confirmation; treat as third-party public-page valuation context.",
            "main_chain_rule": "The main L4 requests path records direct 403, then may merge this file only when user_trusted=true.",
        },
        "pages": pages,
        "source_errors": source_errors,
    }


def _has_available_trendonify_page(page: Dict[str, Any]) -> bool:
    parsed = page.get("parsed") if isinstance(page, dict) else None
    if not isinstance(parsed, dict):
        return False
    return parsed.get("availability") == "available" or parsed.get("value") is not None


def has_available_trendonify_sidecar_payload(payload: Dict[str, Any]) -> bool:
    for page in payload.get("pages", []):
        if _has_available_trendonify_page(page):
            return True
    return False


def merge_trendonify_sidecar_payload(existing: Optional[Dict[str, Any]], payload: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(existing, dict) or not existing.get("pages"):
        return payload
    existing_by_type = {
        page.get("page_type"): page
        for page in existing.get("pages", [])
        if isinstance(page, dict) and page.get("page_type") and _has_available_trendonify_page(page)
    }
    preserved: List[str] = []
    merged_pages: List[Dict[str, Any]] = []
    seen = set()
    for page in payload.get("pages", []):
        if not isinstance(page, dict):
            continue
        page_type = page.get("page_type")
        seen.add(page_type)
        if _has_available_trendonify_page(page) or page_type not in existing_by_type:
            merged_pages.append(page)
            continue
        old_page = dict(existing_by_type[page_type])
        old_page["preserved_after_failed_refresh_at_utc"] = payload.get("generated_at_utc")
        old_page["latest_failed_refresh"] = {
            "generated_at_utc": payload.get("generated_at_utc"),
            "parse_status": page.get("parse_status"),
            "text_excerpt": page.get("text_excerpt"),
        }
        merged_pages.append(old_page)
        preserved.append(str(page_type))

    for page_type, page in existing_by_type.items():
        if page_type not in seen:
            merged_pages.append(page)
            preserved.append(str(page_type))

    merged = dict(payload)
    merged["pages"] = merged_pages
    if preserved:
        merged["preserved_existing_page_types"] = sorted(set(preserved))
    return merged


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect isolated browser sidecar data for vNext research.")
    parser.add_argument("--source", default="trendonify_valuation", choices=["trendonify_valuation"])
    parser.add_argument(
        "--output",
        default=str(Path(path_config.output_dir) / "browser_sidecar" / "trendonify_ndx_valuation.json"),
    )
    parser.add_argument("--trusted", action="store_true", help="Mark output as explicitly trusted by the user.")
    parser.add_argument("--timeout", type=int, default=45)
    parser.add_argument("--wait-seconds", type=float, default=3.0)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
    if args.source != "trendonify_valuation":
        raise ValueError(f"Unsupported source: {args.source}")
    payload = collect_trendonify_valuation_sidecar(
        trusted=args.trusted,
        timeout=args.timeout,
        wait_seconds=args.wait_seconds,
    )
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    existing_payload: Optional[Dict[str, Any]] = None
    if output.exists():
        try:
            existing_payload = json.loads(output.read_text(encoding="utf-8"))
        except Exception:
            existing_payload = None
        payload = merge_trendonify_sidecar_payload(existing_payload, payload)
    if output.exists() and not has_available_trendonify_sidecar_payload(payload):
        failed_output = output.with_suffix(".failed.json")
        failed_output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        logger.warning(
            "browser sidecar refresh had no available parsed values; preserved existing file: %s (failed payload: %s)",
            output,
            failed_output,
        )
        return 0
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    logger.info("browser sidecar written: %s (%s pages, %s errors)", output, len(payload["pages"]), len(payload["source_errors"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
