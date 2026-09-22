from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from playwright.sync_api import Page, sync_playwright

from console_io import configure_utf8_stdout
from contact_pipeline_contract import merge_contact_candidates
from embedded_cdp import connect_shop
from creator_delivery_contract import mark_precontact_qualification
from osmana_creator_rules import (
    SHAPEWEAR_TERMS,
    UNDERWEAR_TERMS,
    evaluate_osmana_candidate,
    extract_height_weight,
    extract_profile_intro,
)


configure_utf8_stdout()

DOUYIN_LABELS = ("达人抖音主页", "抖音主页", "查看抖音主页", "达人主页")
SAFETY_MARKERS = ("安全验证", "验证码", "访问过于频繁", "请求过于频繁", "稍后再试")
PERSONA_TERMS = ("真人口播", "口播", "真人试穿", "试穿", "上身展示", "穿搭", "测评")


def compact(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def safe_name(value: Any) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", compact(value))[:48] or "creator"


def screenshot_filename(candidate: dict[str, Any]) -> str:
    identity = compact(candidate.get("identity") or candidate.get("buyin_uid") or candidate.get("douyin_id"))
    suffix = hashlib.sha1(identity.encode("utf-8")).hexdigest()[:10] if identity else "unknown"
    return f"{safe_name(candidate.get('nickname'))}_{suffix}_douyin.jpg"


def stable_creator_key(candidate: dict[str, Any]) -> str:
    public = compact(
        candidate.get("douyin_id")
        or candidate.get("douyin_account_id")
        or candidate.get("douyin_homepage")
    ).lower()
    if public:
        return f"douyin:{public}"
    return f"identity:{compact(candidate.get('identity') or candidate.get('buyin_uid'))}"


def content_review_complete(candidate: dict[str, Any]) -> bool:
    status = compact(candidate.get("douyin_evidence_status"))
    screenshot = Path(compact(candidate.get("content_evidence_screenshot"))).name
    return status in {"verified", "content_not_matched"} and bool(
        re.search(r"_[0-9a-f]{10}_douyin\.jpg$", screenshot)
    )


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def resolve_cdp_endpoint(endpoint: str) -> str:
    if endpoint.startswith(("ws://", "wss://")):
        return endpoint
    with urlopen(endpoint.rstrip("/") + "/json/version", timeout=5) as response:
        return str(json.loads(response.read().decode("utf-8"))["webSocketDebuggerUrl"])


def extract_content_evidence(text: Any, require_shapewear: bool = True) -> list[str]:
    rows = [compact(line) for line in re.split(r"[\r\n]+", str(text or "")) if compact(line)]
    product_terms = SHAPEWEAR_TERMS if require_shapewear else (*SHAPEWEAR_TERMS, *UNDERWEAR_TERMS)
    selected = [
        line[:280]
        for line in rows
        if any(term in line for term in product_terms) or any(term in line for term in PERSONA_TERMS)
    ]
    return list(dict.fromkeys(selected))[:20]


def extract_douyin_profile_intro(text: Any) -> str:
    value = compact(text)
    match = re.search(
        r"IP属地[:：]\S+\s+(.*?)\s+关注\s+私信\s+作品(?:\s+\d+)?",
        value,
    )
    if not match:
        return ""
    return compact(match.group(1)).removesuffix("... 更多").strip()


def validate_product_evidence_input(candidates: list[dict[str, Any]]) -> None:
    if candidates and not any(
        row.get("buyin_product_evidence_reviewed") or row.get("products_30d")
        for row in candidates
    ):
        raise ValueError(
            "input is missing Buyin product evidence; use the Buyin evidence high-water file"
        )


def attach_douyin_body_evidence(candidate: dict[str, Any], douyin_intro: str) -> dict[str, Any]:
    current = dict(candidate)
    existing_intro = compact(current.get("profile_intro")) or extract_profile_intro(current.get("profile_text"))
    existing_height, existing_weight = extract_height_weight(existing_intro)
    douyin_height, douyin_weight = extract_height_weight(douyin_intro)
    if (existing_height is None or existing_weight is None) and douyin_height is not None and douyin_weight is not None:
        current["profile_intro"] = douyin_intro
        current["profile_intro_source"] = "douyin_homepage"
    return current


def select_product_evidence_candidates(
    candidates: list[dict[str, Any]],
    strategy: dict[str, Any],
    shop: str,
    limit: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    threshold = int(strategy.get("minimumUnderwearProductSales") or 10000)
    refreshed: list[dict[str, Any]] = []
    for row in candidates:
        current = dict(row)
        douyin_intro = extract_douyin_profile_intro(current.get("douyin_content_text"))
        if douyin_intro:
            current = attach_douyin_body_evidence(current, douyin_intro)
        current["osmana_evaluation"] = evaluate_osmana_candidate(current, strategy)
        refreshed.append(current)
    eligible = [
        row for row in refreshed
        if compact(row.get("shop")) in ("", shop)
        and int((row.get("osmana_evaluation") or {}).get("underwear_product_sales_low") or 0) >= threshold
        and not content_review_complete(row)
    ]
    height_range = strategy.get("heightCm") or {"min": 155, "max": 170}
    weight_range = strategy.get("weightJin") or {"min": 80, "max": 110}

    def priority(row: dict[str, Any]) -> tuple[int, int, str]:
        evaluation = row.get("osmana_evaluation") or {}
        height = evaluation.get("height_cm")
        weight = evaluation.get("weight_jin")
        body_complete = (
            height is not None
            and weight is not None
            and float(height_range["min"]) <= float(height) <= float(height_range["max"])
            and float(weight_range["min"]) <= float(weight) <= float(weight_range["max"])
        )
        return (
            0 if body_complete else 1,
            -int(evaluation.get("underwear_product_sales_low") or 0),
            compact(row.get("nickname") or row.get("identity")),
        )

    eligible.sort(key=priority)
    unique: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in eligible:
        key = stable_creator_key(row)
        if key in seen:
            continue
        seen.add(key)
        unique.append(row)
    eligible = unique
    return eligible[: limit or len(eligible)], refreshed


def click_douyin_homepage(context, profile_page: Page) -> tuple[Page | None, str]:
    before = set(context.pages)
    for label in DOUYIN_LABELS:
        locator = profile_page.get_by_text(label, exact=True)
        for index in range(locator.count()):
            node = locator.nth(index)
            try:
                if not node.is_visible(timeout=500):
                    continue
                node.click(timeout=2500)
                profile_page.wait_for_timeout(2500)
                opened = next((page for page in context.pages if page not in before and not page.is_closed()), None)
                if opened:
                    return opened, label
                if "douyin.com" in profile_page.url:
                    return profile_page, label
            except Exception:
                continue
    return None, ""


def verify_one(
    context,
    candidate: dict[str, Any],
    visual_dir: Path,
    delay_ms: int,
    strategy: dict[str, Any],
    page: Page | None = None,
) -> dict[str, Any]:
    current = dict(candidate)
    profile_url = compact(current.get("buyin_profile_url"))
    owns_page = page is None
    page = page or context.new_page()
    page.set_default_timeout(15000)
    opened: Page | None = None
    try:
        page.goto(profile_url, wait_until="domcontentloaded", timeout=45000)
        try:
            page.wait_for_function("() => (document.body?.innerText || '').includes('达人简介')", timeout=18000)
        except Exception:
            page.wait_for_timeout(max(3000, delay_ms))
        profile_text = page.locator("body").inner_text(timeout=10000)
        current["profile_text"] = compact(profile_text)[:24000]
        opened, method = click_douyin_homepage(context, page)
        if opened is None:
            current["douyin_evidence_status"] = "douyin_homepage_not_opened"
            return current
        try:
            opened.wait_for_load_state("domcontentloaded", timeout=18000)
        except Exception:
            pass
        opened.wait_for_timeout(max(3500, delay_ms))
        body = opened.locator("body").inner_text(timeout=12000)
        marker = next((value for value in SAFETY_MARKERS if value in body), "")
        if marker:
            current["douyin_evidence_status"] = "platform_paused"
            current["douyin_evidence_error"] = marker
            return current

        visual_dir.mkdir(parents=True, exist_ok=True)
        screenshot = visual_dir / screenshot_filename(current)
        opened.screenshot(path=str(screenshot), type="jpeg", quality=72, full_page=False)
        evidence = extract_content_evidence(
            body,
            require_shapewear=strategy.get("requireShapewearContent", True),
        )
        current["douyin_homepage"] = opened.url if "douyin.com" in opened.url else ""
        current["douyin_homepage_open_method"] = method
        current["douyin_content_text"] = compact(body)[:26000]
        douyin_intro = extract_douyin_profile_intro(body)
        if douyin_intro:
            current = attach_douyin_body_evidence(current, douyin_intro)
        current["content_evidence"] = evidence
        current["content_evidence_screenshot"] = str(screenshot)
        current["content_text_matched"] = bool(evidence)
        current["content_evidence_reviewed"] = bool(current["douyin_homepage"] and evidence and screenshot.exists())
        persona_text = " ".join(evidence)
        current["visual_persona_verified"] = bool(
            current["content_evidence_reviewed"]
            and any(term in persona_text for term in PERSONA_TERMS)
        )
        current["visual_review_note"] = (
            "抖音主页画面已抓取，内容文案命中真人口播/试穿证据"
            if current["visual_persona_verified"]
            else "已抓取画面，但未命中真人口播/试穿证据"
        )
        current["visual_reviewed_at"] = datetime.now().isoformat(timespec="seconds")
        current["visual_review_status"] = "frame_captured"
        current["douyin_evidence_status"] = "verified" if current["content_evidence_reviewed"] else "content_not_matched"
    except Exception as exc:
        current["douyin_evidence_status"] = "error"
        current["douyin_evidence_error"] = compact(exc)[:500]
    finally:
        if opened is not None and opened is not page:
            try:
                opened.close()
            except Exception:
                pass
        if owns_page:
            try:
                page.close()
            except Exception:
                pass
    return current


def save(payload: dict[str, Any], candidates: list[dict[str, Any]], strategy: dict[str, Any], output: Path) -> None:
    evaluated = [
        mark_precontact_qualification(
            {**row, "osmana_evaluation": evaluate_osmana_candidate(row, strategy)},
            strategy,
        )
        for row in candidates
    ]
    output.write_text(json.dumps({
        **payload,
        "status": "ready",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "candidate_count": len(evaluated),
        "douyin_verified_count": sum(1 for row in evaluated if row.get("content_evidence_reviewed")),
        "strict_qualified_count": sum(1 for row in evaluated if row["osmana_evaluation"].get("qualified")),
        "candidates": evaluated,
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--shop", required=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--delay-ms", type=int, default=1800)
    args = parser.parse_args()

    source = Path(args.input).resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    strategy = json.loads(Path(args.strategy).resolve().read_text(encoding="utf-8"))
    candidates = [dict(row) for row in payload.get("candidates") or [] if isinstance(row, dict)]
    validate_product_evidence_input(candidates)
    selected, candidates = select_product_evidence_candidates(candidates, strategy, args.shop, args.limit)
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / f"osmana_douyin_evidence_shop_{args.shop}_highwater.json"
    visual_dir = out_dir / "douyin_frames"

    emit({"status": "osmana_douyin_started", "shop": args.shop, "candidate_count": len(selected)})
    with sync_playwright() as playwright:
        browser, context, _embedded_page = connect_shop(playwright.chromium, args.endpoint)
        processed = 0
        for row in selected:
            updated = verify_one(context, row, visual_dir, args.delay_ms, strategy, page=_embedded_page)
            candidates = merge_contact_candidates(candidates, [updated])
            processed += 1
            save(payload, candidates, strategy, output)
            emit({
                "status": "osmana_douyin_progress",
                "shop": args.shop,
                "creator": updated.get("nickname", ""),
                "processed": processed,
                "total": len(selected),
                "evidence_status": updated.get("douyin_evidence_status"),
            })
            if updated.get("douyin_evidence_status") == "platform_paused":
                break
    save(payload, candidates, strategy, output)
    final = json.loads(output.read_text(encoding="utf-8"))
    emit({
        "status": "osmana_douyin_finished",
        "shop": args.shop,
        "output": str(output),
        "douyin_verified_count": final.get("douyin_verified_count", 0),
        "strict_qualified_count": final.get("strict_qualified_count", 0),
    })


if __name__ == "__main__":
    main()
