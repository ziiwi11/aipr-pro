from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from console_io import configure_utf8_stdout
from atomic_json_io import atomic_write_json
from audit_strict_contact_highwater import build_strict_contact_highwater
from contact_highwater import contact_only_update, load_contact_highwater, save_contact_highwater
from contact_pipeline_contract import (
    contact_totals,
    creator_identity,
    merge_contact_candidates,
    profile_content_ready,
    terminal_contact_failure,
)
from creator_delivery_contract import canonicalize_contact_fields
from cdp_session_hygiene import prune_automation_pages
from embedded_cdp import connect_shop
from scrape_buyin_public_intro_contacts_cdp import apply_stored_profile_contact
from source_pool_contract import source_only_pool_ready as contact_source_pool_ready
from playwright.sync_api import sync_playwright


configure_utf8_stdout()


def emit(payload: dict) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def contact_resume_filename(payload: dict) -> str:
    strategy = payload.get("strategy") if isinstance(payload.get("strategy"), dict) else {}
    if str(strategy.get("strategyPurpose") or "").strip() == "replenishment-source-only":
        return "aipr_contact_resume_replenishment_input.json"
    return "aipr_contact_resume_input.json"


def public_intro_filename(payload: dict, shop: str) -> str:
    strategy = payload.get("strategy") if isinstance(payload.get("strategy"), dict) else {}
    if str(strategy.get("strategyPurpose") or "").strip() == "replenishment-source-only":
        return f"aipr_public_intro_replenishment_{shop}.json"
    return f"aipr_public_intro_{shop}.json"


def merge_recent_contact_shards(output_dir: Path, candidates: list[dict]) -> list[dict]:
    identities = {creator_identity(row) for row in candidates if creator_identity(row)}
    updates: list[dict] = []
    paths = sorted(output_dir.glob("ui_contact_icon_retry_?_*.json"), key=lambda path: path.stat().st_mtime)[-40:]
    for path in paths:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError):
            continue
        updates.extend(
            contact_only_update(row)
            for row in payload.get("candidates") or []
            if isinstance(row, dict) and creator_identity(row) in identities
        )
    return merge_contact_candidates(candidates, updates)


def profile_session_ready(final_url: str, body_text: str) -> bool:
    return "buyin.jinritemai.com" in str(final_url or "") and profile_content_ready(body_text)


def probe_contact_shop(endpoint: str, profile_url: str) -> bool:
    try:
        prune_automation_pages(endpoint)
        with sync_playwright() as playwright:
            browser, context, _embedded_page = connect_shop(playwright.chromium, endpoint, timeout=10000)
            page = _embedded_page
            page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
            for _attempt in range(15):
                body = page.locator("body").inner_text(timeout=3000)
                if profile_session_ready(page.url, body):
                    return True
                if "douyinec.com" in str(page.url or ""):
                    return False
                page.wait_for_timeout(1000)
            return False
    except Exception:
        return False


def assign_contact_lanes(candidates: list[dict], active_shops: list[str] | None = None) -> list[dict]:
    assigned: list[dict] = []
    eligible_index = 0
    shops = [shop for shop in (active_shops or ["A", "B"]) if shop in {"A", "B"}]
    for candidate in candidates:
        current = dict(candidate)
        current.pop("contact_shop", None)
        eligible = (
            bool(shops)
            and current.get("content_evidence_reviewed") is True
            and current.get("precontact_qualified") is True
            and contact_totals([current])["plain"] == 0
            and not terminal_contact_failure(current)
        )
        if eligible:
            source_shop = str(current.get("shop") or current.get("lip_shop") or "").upper()
            if source_shop in shops:
                current["contact_shop"] = source_shop
            else:
                current["contact_shop"] = shops[eligible_index % len(shops)]
                eligible_index += 1
        assigned.append(current)
    return assigned


def public_intro_required(candidates: list[dict], shop: str) -> bool:
    return any(
        row.get("contact_shop") == shop
        and row.get("precontact_qualified") is True
        and not row.get("buyin_public_intro_checked")
        and contact_totals([row])["plain"] == 0
        for row in candidates
    )


def contact_preflight_profile_url(candidates: list[dict]) -> str:
    """Choose a healthy profile for session preflight.

    A creator that previously returned a platform rate-limit response is still
    resumable later, but it must not be used to decide whether the whole shop
    session is healthy.  Prefer an untouched profile so one poisoned row cannot
    make every embedded shop appear offline.
    """
    previously_opened = next((
        str(row.get("buyin_profile_url") or "").strip()
        for row in candidates
        if row.get("precontact_qualified") is True
        and str(row.get("ui_contact_probe_status") or "").strip() == "revealed"
        and str(row.get("buyin_profile_url") or "").strip()
    ), "")
    if previously_opened:
        return previously_opened
    retryable_probe_failures = {"rate_limited", "request_too_frequent", "clicked_not_revealed", "timeout"}
    return next((
        str(row.get("buyin_profile_url") or "").strip()
        for row in candidates
        if row.get("precontact_qualified") is True
        and contact_totals([row])["plain"] == 0
        and not terminal_contact_failure(row)
        and str(row.get("ui_contact_probe_status") or "").strip() not in retryable_probe_failures
        and str(row.get("buyin_profile_url") or "").strip()
    ), "")


def daily_quota_exhausted_shops(results: list[tuple[str, list[dict]]]) -> list[str]:
    return [
        shop
        for shop, rows in results
        if any(row.get("ui_contact_probe_status") == "daily_quota_exhausted" for row in rows)
    ]


def save_strict_audit(
    contact_payload: dict,
    strategy_path: Path,
    historical_strategy_path: Path,
    output_path: Path,
    target_count: int,
) -> dict:
    current_rules = json.loads(strategy_path.read_text(encoding="utf-8"))
    historical_rules = json.loads(historical_strategy_path.read_text(encoding="utf-8"))
    strict = build_strict_contact_highwater(
        contact_payload,
        current_rules,
        historical_rules,
        max(1, target_count),
    )
    atomic_write_json(output_path, strict)
    return strict


def save_contact_and_strict_highwater(
    output_dir: Path,
    contact_payload: dict,
    strategy_path: Path,
    historical_strategy_path: Path,
    audit_output_path: Path,
    target_count: int,
) -> dict:
    """Merge the stable contact pool before rebuilding the strict checkpoint.

    Replenishment batches can use a source file containing only newly found
    creators.  Auditing that narrow batch would overwrite the accumulated
    strict checkpoint and make previously accepted creators disappear.  The
    stable contact high-water is the authoritative union across source pools,
    so always audit the atomically merged payload instead.
    """
    contact_highwater_path = save_contact_highwater(output_dir, contact_payload)
    merged_payload = json.loads(contact_highwater_path.read_text(encoding="utf-8"))
    return save_strict_audit(
        merged_payload,
        strategy_path,
        historical_strategy_path,
        audit_output_path,
        target_count,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--out-dir", default="output")
    parser.add_argument("--delay-ms", type=int, default=3200)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--shop-a", default="http://127.0.0.1:9222?shop=A")
    parser.add_argument("--shop-b", default="http://127.0.0.1:9222?shop=B")
    parser.add_argument("--audit-strategy", default="")
    parser.add_argument("--audit-historical-strategy", default="")
    parser.add_argument("--audit-output", default="")
    parser.add_argument("--target-count", type=int, default=1000)
    args = parser.parse_args()

    delay_ms = max(3000, args.delay_ms)
    output_dir = Path(args.out_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    single = Path(__file__).with_name("contact_icons_single.py")
    env = {**os.environ, "AIPR_OUTPUT_DIR": str(output_dir), "AIPR_WORKER_OUTPUT": str(output_dir)}

    source_payload = json.loads(Path(args.input).resolve().read_text(encoding="utf-8"))
    source_ready, source_reason = contact_source_pool_ready(source_payload)
    if not source_ready:
        emit({
            "status": "contact_collection_failed",
            "stage": "source_pool",
            "message": "source_pool_incomplete",
            "reason": source_reason,
            "candidate_count": len(source_payload.get("candidates") or []),
            "target_count": source_payload.get("target_count"),
        })
        raise SystemExit(7)
    emit({"status": "started", "message": "双店页面慢速联系方式流程已启动", "delay_ms": delay_ms})
    working_payload = load_contact_highwater(output_dir, source_payload)
    merged_candidates = [canonicalize_contact_fields(row) for row in merge_recent_contact_shards(output_dir, [
        item for item in working_payload.get("candidates") or [] if isinstance(item, dict)
    ])]
    cached_intro_added = 0
    for row in merged_candidates:
        before_plain = contact_totals([row])["plain"]
        if before_plain == 0 and (row.get("profile_text") or row.get("buyin_public_intro")):
            apply_stored_profile_contact(row)
            normalized = canonicalize_contact_fields(row)
            row.clear()
            row.update(normalized)
        if before_plain == 0 and contact_totals([row])["plain"]:
            cached_intro_added += 1
    if cached_intro_added:
        emit({
            "status": "public_intro_cached_contacts_refreshed",
            "added": cached_intro_added,
            "message": "从已授权达人公开简介补齐联系方式",
        })
    sample_profile_url = contact_preflight_profile_url(merged_candidates)
    endpoints = {"A": args.shop_a, "B": args.shop_b}
    with ThreadPoolExecutor(max_workers=2) as executor:
        checks = {
            shop: executor.submit(probe_contact_shop, endpoint, sample_profile_url)
            for shop, endpoint in endpoints.items()
        }
        active_shops = [shop for shop, future in checks.items() if sample_profile_url and future.result()]
    emit({"status": "contact_shop_preflight", "active_shops": active_shops})
    if sample_profile_url and not active_shops:
        emit({"status": "error", "message": "no merchant workbench can open a creator profile"})
        raise SystemExit(8)
    merged_candidates = assign_contact_lanes(merged_candidates, active_shops=active_shops)
    working_payload = {**working_payload, "candidates": merged_candidates}
    working_input = output_dir / contact_resume_filename(working_payload)
    working_input.write_text(json.dumps(working_payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def run_shop(shop: str, endpoint: str) -> tuple[int, list[dict]]:
        public_intro = Path(__file__).with_name("scrape_buyin_public_intro_contacts_cdp.py")
        public_output = output_dir / public_intro_filename(working_payload, shop)
        public_command = [
            sys.executable, str(public_intro),
            "--input", str(working_input),
            "--endpoint", endpoint,
            "--output", str(public_output),
            "--shop", shop,
            "--delay-ms", str(max(2200, delay_ms)),
        ]
        contact_input = working_input
        if public_intro_required(merged_candidates, shop):
            emit({"status": "public_intro_started", "shop": shop, "endpoint": endpoint})
            public_process = subprocess.run(
                public_command, env=env, text=True, encoding="utf-8", errors="replace", capture_output=True,
            )
            for line in public_process.stdout.splitlines():
                if line.strip():
                    print(line.strip(), flush=True)
            if public_process.returncode == 0 and public_output.exists():
                contact_input = public_output
        else:
            emit({"status": "public_intro_reused", "shop": shop})
        command = [
            sys.executable, str(single), "--input", str(contact_input),
            "--endpoint", endpoint, "--shop", shop, "--delay-ms", str(delay_ms),
        ]
        if args.limit:
            command.extend(["--limit", str(args.limit)])
        emit({"status": "shop_started", "shop": shop, "endpoint": endpoint})
        before = set(output_dir.glob(f"ui_contact_icon_retry_{shop}_*.json"))
        process = subprocess.Popen(
            command, env=env, text=True, encoding="utf-8", errors="replace",
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        assert process.stdout is not None
        for line in process.stdout:
            if line.strip():
                print(line.strip(), flush=True)
        stderr = process.stderr.read() if process.stderr else ""
        return_code = process.wait()
        if return_code:
            emit({"status": "error", "shop": shop, "message": stderr[-1000:] or "页面任务执行失败"})
        created = sorted(
            set(output_dir.glob(f"ui_contact_icon_retry_{shop}_*.json")) - before,
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if created:
            shop_payload = json.loads(created[0].read_text(encoding="utf-8"))
            return return_code, shop_payload.get("candidates") or []
        return return_code, []

    with ThreadPoolExecutor(max_workers=max(1, len(active_shops))) as executor:
        futures = [executor.submit(run_shop, shop, endpoints[shop]) for shop in active_shops]
        results = [future.result() for future in futures]
    exit_code = max((code for code, _rows in results), default=0)
    for _code, rows in results:
        merged_candidates = merge_contact_candidates(merged_candidates, rows)
    merged_candidates = [canonicalize_contact_fields(row) for row in merged_candidates]
    exhausted_shops = daily_quota_exhausted_shops([
        (shop, rows) for shop, (_code, rows) in zip(active_shops, results)
    ])
    if exhausted_shops:
        emit({
            "status": "contact_daily_quota_exhausted",
            "shops": exhausted_shops,
            "message": "查看达人联系方式次数已达上限",
        })

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = output_dir / f"aipr_creator_contacts_{stamp}.json"
    totals = contact_totals(merged_candidates)
    qualified_candidates = [row for row in merged_candidates if row.get("precontact_qualified") is True]
    qualified_totals = contact_totals(qualified_candidates)
    result = {
        **working_payload,
        "status": "ready",
        "contact_collection_at": datetime.now().isoformat(timespec="seconds"),
        "candidate_count": len(merged_candidates),
        "plain_contact_count": totals["plain"],
        "wechat_contact_count": totals["wechat"],
        "phone_contact_count": totals["phone"],
        "email_contact_count": totals["email"],
        "qualified_plain_contact_count": qualified_totals["plain"],
        "qualified_wechat_contact_count": qualified_totals["wechat"],
        "qualified_phone_contact_count": qualified_totals["phone"],
        "daily_quota_exhausted_shops": exhausted_shops,
        "candidates": merged_candidates,
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.audit_strategy and args.audit_historical_strategy:
        audit_output = Path(args.audit_output).resolve() if args.audit_output else output_dir / "aipr_strict_contact_highwater.json"
        strict = save_contact_and_strict_highwater(
            output_dir,
            result,
            Path(args.audit_strategy).resolve(),
            Path(args.audit_historical_strategy).resolve(),
            audit_output,
            args.target_count,
        )
        emit({
            "status": "strict_contact_audit_finished",
            "output": str(audit_output),
            "target_count": strict["target_count"],
            "rows_with_plaintext": strict["rows_with_plaintext"],
            "strict_selected_count": strict["strict_selected_count"],
            "complete": strict["status"] == "complete",
            "audit": strict["audit"],
        })
    else:
        save_contact_highwater(output_dir, result)
    emit({
        "status": "contact_collection_finished",
        "message": "双店达人与联系方式采集已完成",
        "output": str(output),
        "candidate_count": len(merged_candidates),
        "plain_contact_count": totals["plain"],
        "wechat_contact_count": totals["wechat"],
        "phone_contact_count": totals["phone"],
        "email_contact_count": totals["email"],
        "qualified_plain_contact_count": qualified_totals["plain"],
        "qualified_wechat_contact_count": qualified_totals["wechat"],
        "qualified_phone_contact_count": qualified_totals["phone"],
    })
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
