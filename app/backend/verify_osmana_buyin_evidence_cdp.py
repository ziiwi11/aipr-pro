from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

from playwright.sync_api import Page, sync_playwright

from console_io import configure_utf8_stdout
from contact_pipeline_contract import merge_contact_candidates
from embedded_cdp import connect_shop
from osmana_creator_rules import evaluate_osmana_candidate, normalize_products


configure_utf8_stdout()

PRODUCT_API_MARKER = "sale_product_list"
SAFETY_MARKERS = ("请求过于频繁", "稍后再试", "访问频繁", "安全验证", "验证码")


def compact(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def resolve_cdp_endpoint(endpoint: str) -> str:
    if endpoint.startswith(("ws://", "wss://")):
        return endpoint
    with urlopen(endpoint.rstrip("/") + "/json/version", timeout=5) as response:
        return str(json.loads(response.read().decode("utf-8"))["webSocketDebuggerUrl"])


def parse_product_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or str(payload.get("code")) != "0":
        return []
    data = payload.get("data")
    if not isinstance(data, dict):
        return []
    products = data.get("product_info")
    if not isinstance(products, list):
        return []
    return normalize_products(item for item in products if isinstance(item, dict))


def author_level_from_url(url: str, fallback: Any = "") -> str:
    values = parse_qs(urlparse(url).query).get("author_level") or []
    return f"LV{values[0]}" if values else compact(fallback)


def click_visible(page: Page, label: str, *, last: bool = False) -> bool:
    locator = page.get_by_text(label, exact=True)
    indexes = range(locator.count() - 1, -1, -1) if last else range(locator.count())
    for index in indexes:
        node = locator.nth(index)
        try:
            if node.is_visible(timeout=500):
                node.click(timeout=2500)
                return True
        except Exception:
            continue
    return False


def unique_products(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for row in rows:
        key = compact(row.get("product_id")) or compact(row.get("title"))
        if not key:
            continue
        previous = merged.get(key)
        if previous is None or int(row.get("sales_low") or 0) > int(previous.get("sales_low") or 0):
            merged[key] = row
    return sorted(merged.values(), key=lambda item: int(item.get("sales_low") or 0), reverse=True)


def has_qualifying_short_video_underwear(products: list[dict[str, Any]], threshold: int = 10000) -> bool:
    return any(
        row.get("is_underwear")
        and int(row.get("sales_low") or 0) >= threshold
        and int(row.get("related_video_num") or 0) > 0
        and int(row.get("related_live_times") or 0) == 0
        for row in products
    )


def verify_profile(page: Page, candidate: dict[str, Any], delay_ms: int) -> dict[str, Any]:
    current = dict(candidate)
    profile_url = compact(current.get("buyin_profile_url") or current.get("精选联盟主页"))
    payloads: list[dict[str, Any]] = []

    def on_response(response) -> None:
        if PRODUCT_API_MARKER not in response.url:
            return
        try:
            payloads.append(response.json())
        except Exception:
            pass

    page.on("response", on_response)
    try:
        page.goto(profile_url, wait_until="domcontentloaded", timeout=45000)
        try:
            page.wait_for_function(
                """() => {
                  const text = document.body?.innerText || '';
                  return text.includes('达人简介') && text.includes('核心数据') && text.includes('带货分析');
                }""",
                timeout=18000,
            )
        except Exception:
            page.wait_for_timeout(max(3000, delay_ms))
        body = page.locator("body").inner_text(timeout=10000)
        marker = next((item for item in SAFETY_MARKERS if item in body), "")
        if marker:
            current["osmana_evidence_status"] = "platform_paused"
            current["osmana_evidence_error"] = marker
            return current

        current["profile_text"] = compact(body)[:24000]
        current["talent_level"] = author_level_from_url(page.url, current.get("talent_level"))
        click_visible(page, "概览")
        page.wait_for_timeout(400)
        try:
            with page.expect_response(lambda response: PRODUCT_API_MARKER in response.url, timeout=12000):
                if not click_visible(page, "带货分析"):
                    raise RuntimeError("sales_analysis_tab_not_found")
        except Exception:
            click_visible(page, "带货分析")
        page.wait_for_timeout(max(700, delay_ms // 2))

        first_pass: list[dict[str, Any]] = []
        for payload in payloads:
            first_pass.extend(parse_product_payload(payload))
        if not has_qualifying_short_video_underwear(first_pass):
            try:
                with page.expect_response(lambda response: PRODUCT_API_MARKER in response.url, timeout=5000):
                    click_visible(page, "服饰内衣", last=True)
            except Exception:
                pass
            page.wait_for_timeout(max(700, delay_ms // 2))

        products: list[dict[str, Any]] = []
        for payload in payloads:
            products.extend(parse_product_payload(payload))
        current["products_30d"] = unique_products(products)
        current["buyin_product_evidence_reviewed"] = bool(current["products_30d"])
        current["osmana_evidence_status"] = "buyin_evidence_ready" if current["products_30d"] else "product_evidence_missing"
    except Exception as exc:
        current["osmana_evidence_status"] = "error"
        current["osmana_evidence_error"] = compact(exc)[:500]
    finally:
        try:
            page.remove_listener("response", on_response)
        except Exception:
            pass
    return current


def save_progress(source_payload: dict[str, Any], candidates: list[dict[str, Any]], output: Path, strategy: dict[str, Any]) -> None:
    evaluations = [evaluate_osmana_candidate(row, strategy) for row in candidates]
    payload = {
        **source_payload,
        "status": "ready",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "candidate_count": len(candidates),
        "buyin_evidence_count": sum(1 for row in candidates if row.get("buyin_product_evidence_reviewed")),
        "strict_qualified_count": sum(1 for result in evaluations if result.get("qualified")),
        "candidates": [{**row, "osmana_evaluation": result} for row, result in zip(candidates, evaluations)],
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--shop-a", default="http://127.0.0.1:9222?shop=A")
    parser.add_argument("--shop-b", default="http://127.0.0.1:9222?shop=B")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--delay-ms", type=int, default=1800)
    args = parser.parse_args()

    source_path = Path(args.input).resolve()
    source_payload = json.loads(source_path.read_text(encoding="utf-8"))
    strategy = json.loads(Path(args.strategy).resolve().read_text(encoding="utf-8"))
    candidates = [dict(row) for row in source_payload.get("candidates") or [] if isinstance(row, dict)]
    selected = candidates[: args.limit or len(candidates)]
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / "osmana_buyin_evidence_highwater.json"
    processed = 0

    emit({"status": "osmana_buyin_evidence_started", "candidate_count": len(selected)})
    active_shops = [
        str(shop).upper()
        for shop in strategy.get("activeShops") or ["A"]
        if str(shop).upper() in {"A", "B"}
    ]
    endpoints = {"A": args.shop_a, "B": args.shop_b}
    for shop in active_shops:
        endpoint = endpoints[shop]
        rows = [row for row in selected if compact(row.get("shop")) in ("", shop)]
        if not rows:
            continue
        with sync_playwright() as playwright:
            browser, context, _embedded_page = connect_shop(playwright.chromium, endpoint)
            page = _embedded_page
            page.set_default_timeout(15000)
            for row in rows:
                updated = verify_profile(page, row, args.delay_ms)
                candidates = merge_contact_candidates(candidates, [updated])
                processed += 1
                save_progress(source_payload, candidates, output, strategy)
                emit({
                    "status": "osmana_buyin_evidence_progress",
                    "creator": updated.get("nickname", ""),
                    "shop": shop,
                    "processed": processed,
                    "total": len(selected),
                    "evidence_status": updated.get("osmana_evidence_status"),
                })
                if updated.get("osmana_evidence_status") == "platform_paused":
                    emit({"status": "platform_paused", "shop": shop, "message": updated.get("osmana_evidence_error", "")})
                    break

    save_progress(source_payload, candidates, output, strategy)
    final = json.loads(output.read_text(encoding="utf-8"))
    emit({
        "status": "osmana_buyin_evidence_finished",
        "output": str(output),
        "candidate_count": final.get("candidate_count", 0),
        "buyin_evidence_count": final.get("buyin_evidence_count", 0),
        "strict_qualified_count": final.get("strict_qualified_count", 0),
    })


if __name__ == "__main__":
    main()
