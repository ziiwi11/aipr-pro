from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from contact_shop_cooldown import shop_cooldown_until
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


def _probe_contact_profile(endpoint: str, profile_url: str) -> bool:
    try:
        prune_automation_pages(endpoint)
        with sync_playwright() as playwright:
            browser, context, _embedded_page = connect_shop(playwright.chromium, endpoint, timeout=10000)
            page = _embedded_page
            request_errors = []
            response_errors = []
            page.on("requestfailed", lambda request: request_errors.append({"path": request.url.split("?")[0], "error": request.failure}))
            page.on("response", lambda response: response_errors.append({"path": response.url.split("?")[0], "status": response.status}) if response.status >= 400 else None)
            page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
            for _attempt in range(45):
                body = page.locator("body").inner_text(timeout=3000) or ""
                if profile_session_ready(page.url, body):
                    return True
                if "douyinec.com" in str(page.url or ""):
                    emit({"status": "contact_shop_preflight_failed", "reason": "login_redirect", "message": "主页检查：跳转至登录页"})
                    return False
                page.wait_for_timeout(1000)
            diagnostic = {"request_errors": request_errors[-12:], "response_errors": response_errors[-12:], "url_path": page.url.split("?")[0], "body_length": len(body), "short_page_message": body if len(body) < 200 else "", "ready_state": page.evaluate("document.readyState"), "profile_markers": [token for token in ("已加达人库", "添加达人库", "达人手机号", "达人微信号", "登录", "请求过于频繁", "页面不存在", "暂无权限") if token in body]}
            page.evaluate("window.__aiprPreflightDiagnostic = " + json.dumps(diagnostic))
            from urllib.parse import parse_qs, urlsplit
            lane = parse_qs(urlsplit(endpoint).query).get("shop", ["unknown"])[0]
            Path(__file__).with_name(f"contact_preflight_diagnostic_{lane}.json").write_text(json.dumps(diagnostic, ensure_ascii=False), encoding="utf-8")
            emit({"status": "contact_shop_preflight_failed", "reason": "profile_not_ready", "message": "主页检查：页面未就绪"})
            return False
    except Exception as exc:
        emit({"status": "contact_shop_preflight_failed", "reason": "probe_exception", "error_type": type(exc).__name__, "message": f"主页检查连接异常：{type(exc).__name__}"})
        return False


def probe_contact_shop(endpoint: str, profile_urls) -> bool:
    urls = [profile_urls] if isinstance(profile_urls, str) else profile_urls
    for url in urls:
        if _probe_contact_profile(endpoint, url):
            return True
    return False


def contact_preflight_profiles(candidates, shop):
    first = contact_preflight_profile_url(candidates, shop=shop)
    urls = [first] if first else []
    for row in reversed(candidates):
        url = str(row.get('buyin_profile_url') or '').strip()
        if row.get('precontact_qualified') is True and row.get('ui_contact_channels_status') == 'complete' and url and url not in urls:
            urls.append(url)
        if len(urls) >= 3:
            break
    return urls


def assign_contact_lanes(candidates: list[dict], active_shops: list[str] | None = None, complete_channels: bool = False) -> list[dict]:
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
            and (complete_channels or contact_totals([current])["plain"] == 0)
            and (complete_channels or not terminal_contact_failure(current))
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


def contact_preflight_profile_url(candidates: list[dict], shop: str = "") -> str:
    """Choose a healthy profile for session preflight.

    A creator that previously returned a platform rate-limit response is still
    resumable later, but it must not be used to decide whether the whole shop
    session is healthy.  Prefer an untouched profile so one poisoned row cannot
    make every embedded shop appear offline.
    """
    if shop:
        matching = [row for row in candidates if str(row.get("contact_shop") or row.get("shop") or row.get("lip_shop") or "").upper() == shop.upper()]
        candidates = matching + [row for row in candidates if row not in matching]
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
    # This stage runs after the realtime collector has exited. Keep its ledger
    # in step with contacts acquired by the subsequent bulk-contact stage.
    flow_path = output_path.parent / "aipr_realtime_creator_flow.json"
    if flow_path.exists():
        from realtime_creator_flow import RealtimeCreatorFlowStore
        RealtimeCreatorFlowStore(flow_path).reconcile_strict_selection(strict)
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
    parser.add_argument("--complete-contact-channels", action="store_true")
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
    working_payload = source_payload if args.complete_contact_channels else load_contact_highwater(output_dir, source_payload)
    merged_candidates = [canonicalize_contact_fields(row) for row in merge_recent_contact_shards(output_dir, [
        item for item in working_payload.get("candidates") or [] if isinstance(item, dict)
    ])]
    if args.complete_contact_channels:
        for row in merged_candidates:
            if row.get("ui_contact_channels_checked_at") and any(marker in str(row.get("ui_contact_message") or "") for marker in ("主推类目不属于店铺类目", "本周仅支持")):
                row["ui_contact_channels_status"] = "category_not_matched"
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
            shop: executor.submit(probe_contact_shop, endpoint, contact_preflight_profiles(merged_candidates, shop))
            for shop, endpoint in endpoints.items()
        }
        active_shops = [shop for shop, future in checks.items() if sample_profile_url and future.result()]
    cooling_shops = [shop for shop in active_shops if shop_cooldown_until(output_dir, shop) > time.time()]
    active_shops = [shop for shop in active_shops if shop not in cooling_shops]
    emit({"status": "contact_shop_preflight", "active_shops": active_shops, "cooling_shops": cooling_shops})
    if sample_profile_url and not active_shops:
        emit({"status": "error", "message": "no merchant workbench can open a creator profile"})
        raise SystemExit(8)
    merged_candidates = assign_contact_lanes(merged_candidates, active_shops=active_shops, complete_channels=args.complete_contact_channels)
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
        if args.complete_contact_channels:
            command.append("--complete-contact-channels")
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
