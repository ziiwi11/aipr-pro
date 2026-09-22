from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from playwright.sync_api import sync_playwright

from console_io import configure_utf8_stdout
from embedded_cdp import connect_shop
from contact_pipeline_contract import terminal_contact_failure
from creator_delivery_contract import canonicalize_contact_fields, contact_identity_values


configure_utf8_stdout()


PHONE_RE = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
WECHAT_PATTERNS = [
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"(?:微信号?|微\s*信|V\s*信|VX|WX)\s*[:：号]?\s*([A-Za-z][A-Za-z0-9_-]{4,31})",
        r"(?:商务合作|合作联系|商务联系|合作V|商务V)\s*[:：]?\s*([A-Za-z][A-Za-z0-9_-]{4,31})",
        r"(?:🈴️?|合\s*作|商务|小助理|助理|联系我|找我|加我|咨询)\s*(?:作)?\s*[:：]?\s*([A-Za-z][A-Za-z0-9_-]{4,31})",
        r"([A-Za-z][A-Za-z0-9_-]{4,31})\s*[（(]?\s*(?:辛苦|需|请|不)?\s*备注(?:品牌|来意|意向)?",
    )
]


def compact(value: Any) -> str:
    return str(value or "").strip()


def resolve_cdp_endpoint(endpoint: str) -> str:
    if endpoint.startswith("ws://") or endpoint.startswith("wss://"):
        return endpoint
    with urlopen(endpoint.rstrip("/") + "/json/version", timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))["webSocketDebuggerUrl"]


def profile_intro(body: str) -> str:
    marker = "达人简介"
    start = body.find(marker)
    if start < 0:
        return ""
    intro = body[start + len(marker):]
    stops = [intro.find(label) for label in ("概览", "场景分析", "粉丝分析", "带货分析")]
    stops = [index for index in stops if index >= 0]
    return intro[: min(stops) if stops else 700].strip()


def extract_intro_contact(intro: str) -> tuple[str, str, str]:
    wechat = ""
    for pattern in WECHAT_PATTERNS:
        match = pattern.search(intro)
        if match:
            wechat = match.group(1)
            break
    phone_match = PHONE_RE.search(intro)
    email_match = EMAIL_RE.search(intro)
    return wechat, phone_match.group(1) if phone_match else "", email_match.group(0) if email_match else ""


def has_plain(row: dict[str, Any]) -> bool:
    return bool(contact_identity_values(canonicalize_contact_fields(row)))


def select_targets(candidates: list[dict[str, Any]], shop: str, limit: int) -> list[dict[str, Any]]:
    selected = [
        row for row in candidates
        if not has_plain(row)
        and not terminal_contact_failure(row)
        and row.get("content_evidence_reviewed")
        and compact(row.get("buyin_profile_url"))
        and (shop == "all" or compact(row.get("contact_shop") or row.get("shop") or row.get("lip_shop")) in ("", shop))
    ]
    return selected[:limit] if limit else selected


def apply_stored_profile_contact(row: dict[str, Any]) -> bool:
    body = compact(row.get("profile_text"))
    stored_intro = compact(row.get("buyin_public_intro"))
    if not body and not stored_intro:
        return False
    intro = stored_intro or profile_intro(body)
    wechat, phone, email = extract_intro_contact(intro)
    row["buyin_public_intro"] = intro[:600]
    row["buyin_public_intro_checked"] = True
    if wechat or phone or email:
        row["buyin_contact_wechat"] = row.get("buyin_contact_wechat") or wechat
        row["buyin_contact_phone"] = row.get("buyin_contact_phone") or phone
        row["buyin_contact_email"] = row.get("buyin_contact_email") or email
        row["buyin_contact_source"] = "buyin_profile_public_intro_cached"
        row["buyin_contact_probe_status"] = "public_intro_revealed"
    else:
        row["buyin_contact_probe_status"] = "public_intro_no_contact"
    normalized = canonicalize_contact_fields(row)
    row.clear()
    row.update(normalized)
    return True


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--output", required=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--delay-ms", type=int, default=2200)
    parser.add_argument("--shop", choices=("A", "B", "all"), default="all")
    args = parser.parse_args()

    source = Path(args.input).resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    candidates = [canonicalize_contact_fields(row) for row in payload.get("candidates") or []]
    targets = select_targets(candidates, args.shop, args.limit)
    target_keys = {compact(row.get("identity") or row.get("buyin_uid") or row.get("douyin_id")) for row in targets}
    processed = 0
    added = 0

    with sync_playwright() as playwright:
        browser, context, _embedded_page = connect_shop(playwright.chromium, args.endpoint)
        page = _embedded_page
        page.set_default_timeout(15000)
        for row in candidates:
            identity = compact(row.get("identity") or row.get("buyin_uid") or row.get("douyin_id"))
            if identity not in target_keys:
                continue
            processed += 1
            if apply_stored_profile_contact(row):
                if has_plain(row):
                    added += 1
                print(json.dumps({
                    "status": "public_intro_progress", "processed": processed, "total": len(targets),
                    "creator": row.get("nickname") or "", "probe_status": row.get("buyin_contact_probe_status"),
                }, ensure_ascii=False), flush=True)
                continue
            try:
                page.goto(compact(row.get("buyin_profile_url")), wait_until="domcontentloaded", timeout=35000)
                page.wait_for_timeout(max(1800, args.delay_ms))
                body = page.locator("body").inner_text(timeout=8000)
                intro = profile_intro(body)
                wechat, phone, email = extract_intro_contact(intro)
                row["buyin_public_intro"] = intro[:600]
                row["buyin_public_intro_checked"] = True
                if wechat or phone or email:
                    row["buyin_contact_wechat"] = row.get("buyin_contact_wechat") or wechat
                    row["buyin_contact_phone"] = row.get("buyin_contact_phone") or phone
                    row["buyin_contact_email"] = row.get("buyin_contact_email") or email
                    row["buyin_contact_source"] = "buyin_profile_public_intro"
                    row["buyin_contact_probe_status"] = "public_intro_revealed"
                    added += 1
                else:
                    row["buyin_contact_probe_status"] = "public_intro_no_contact"
                normalized = canonicalize_contact_fields(row)
                row.clear()
                row.update(normalized)
            except Exception as exc:
                row["buyin_contact_probe_status"] = "public_intro_error"
                row["buyin_contact_error"] = compact(exc)[:300]
            print(json.dumps({
                "status": "public_intro_progress",
                "processed": processed,
                "total": len(targets),
                "creator": row.get("nickname") or "",
                "probe_status": row.get("buyin_contact_probe_status"),
            }, ensure_ascii=False), flush=True)

    output = Path(args.output).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    result = {
        **payload,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "public_intro_processed": processed,
        "public_intro_added": added,
        "candidates": candidates,
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "processed": processed, "added": added}, ensure_ascii=False))


if __name__ == "__main__":
    main()
