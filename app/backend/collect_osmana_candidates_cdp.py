from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from playwright.sync_api import Page, sync_playwright

from console_io import configure_utf8_stdout
from embedded_cdp import connect_shop


configure_utf8_stdout()

BUYIN_URL = "https://buyin.jinritemai.com/dashboard/servicehall/daren-square"
SEARCH_API_MARKER = "square/search_feed_author"
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


def build_profile_url(uid: str, level: int) -> str:
    return BUYIN_URL.replace("daren-square", "daren-profile") + "?" + urlencode({"uid": uid, "author_level": level, "enter_from": 1, "scene": 1})


def candidate_from_search_item(item: dict[str, Any], keyword: str, shop: str) -> dict[str, Any]:
    base = item.get("author_base") if isinstance(item.get("author_base"), dict) else {}
    tags = item.get("author_tag") if isinstance(item.get("author_tag"), dict) else {}
    sale = item.get("author_sale") if isinstance(item.get("author_sale"), dict) else {}
    video = item.get("author_video") if isinstance(item.get("author_video"), dict) else {}
    sale_info = item.get("sale_info") if isinstance(item.get("sale_info"), dict) else {}
    video_total = sale_info.get("video_total_sales") if isinstance(sale_info.get("video_total_sales"), dict) else {}
    latest = item.get("latest_content") if isinstance(item.get("latest_content"), dict) else {}
    latest_video = latest.get("latest_video") if isinstance(latest.get("latest_video"), dict) else {}
    uid = compact(base.get("uid"))
    level = int(base.get("author_level") or 0)
    categories = [compact(value) for value in tags.get("main_cate") or [] if compact(value)]
    contact_visible = bool(compact(tags.get("contact_icon"))) or any(
        compact(reason.get("reason")) == "有联系方式"
        for reason in tags.get("author_rec_reasons") or []
        if isinstance(reason, dict)
    )
    return {
        "identity": uid,
        "buyin_uid": uid,
        "nickname": compact(base.get("nickname")),
        "douyin_id": compact(base.get("aweme_id")),
        "fans": int(base.get("fans_num") or 0),
        "gender": int(base.get("gender") or 0),
        "talent_level": f"LV{level}",
        "author_level": level,
        "category": "/".join(categories),
        "categories": categories,
        "monthly_sales_low": int(sale.get("sale_d30_low") or 0),
        "monthly_sales_high": int(sale.get("sale_d30_high") or 0),
        "video_count_30d": int(video.get("all_video_num_30d") or 0),
        "video_sales_low": int(video_total.get("sale_low") or video.get("video_sale_low") or 0),
        "video_sales_high": int(video_total.get("sale_high") or video.get("video_sale_high") or 0),
        "main_sale_type": compact(sale.get("main_sale_type")),
        "latest_video_title": compact(latest_video.get("title")),
        "latest_video_preview": compact(latest_video.get("preview_pic")),
        "latest_video_url": compact(latest_video.get("content_url")),
        "contact_visible": contact_visible,
        "buyin_contact_visible": contact_visible,
        "buyin_profile_url": build_profile_url(uid, level),
        "source_keyword": keyword,
        "source_keywords": [keyword],
        "shop": shop,
    }


def precursor_eligible(candidate: dict[str, Any]) -> bool:
    level_match = re.search(r"([0-9])", compact(candidate.get("talent_level")))
    level = int(level_match.group(1)) if level_match else int(candidate.get("author_level") or 0)
    return all((
        int(candidate.get("gender") or 0) == 2,
        2 <= level <= 4,
        "服饰内衣" in compact(candidate.get("category")),
        int(candidate.get("monthly_sales_low") or 0) >= 10000,
        bool(candidate.get("contact_visible")),
        int(candidate.get("video_count_30d") or 0) > 0,
        int(candidate.get("video_sales_low") or 0) >= 10000,
        "直播" not in compact(candidate.get("main_sale_type")),
    ))


def candidates_from_payload(payload: dict[str, Any], keyword: str, shop: str) -> list[dict[str, Any]]:
    if str(payload.get("code")) != "0" or not isinstance(payload.get("data"), dict):
        return []
    rows = payload["data"].get("list") or []
    return [candidate_from_search_item(item, keyword, shop) for item in rows if isinstance(item, dict)]


def click_visible(page: Page, label: str) -> bool:
    locator = page.get_by_text(label, exact=True)
    for index in range(locator.count()):
        node = locator.nth(index)
        try:
            if node.is_visible(timeout=400):
                node.click(timeout=2000)
                return True
        except Exception:
            continue
    return False


def apply_filters(page: Page) -> list[str]:
    clicked: list[str] = []
    click_visible(page, "找达人")
    page.wait_for_timeout(500)
    click_visible(page, "重置")
    page.wait_for_timeout(700)
    for label in ("服饰内衣", "视频达人", "有联系方式"):
        if click_visible(page, label):
            clicked.append(label)
            page.wait_for_timeout(450)
    if click_visible(page, "达人等级"):
        page.wait_for_timeout(500)
        for label in ("LV2", "LV3", "LV4", "LV5"):
            if click_visible(page, label):
                clicked.append(label)
                page.wait_for_timeout(300)
        page.keyboard.press("Escape")
    return clicked


def assert_safe(page: Page) -> None:
    try:
        body = page.locator("body").inner_text(timeout=12000)
    except Exception:
        return
    marker = next((value for value in SAFETY_MARKERS if value in body), "")
    if marker:
        raise RuntimeError(f"platform_paused:{marker}")


def fill_query(page: Page, keyword: str) -> None:
    # The Buyin SPA mounts and replaces the search input after the filters render.
    # Resolve it only when visible and fill it directly so transient overlays do
    # not turn a valid search into a click timeout.
    input_node = page.locator("input[type='search']:visible").first
    input_node.wait_for(state="visible", timeout=20000)
    input_node.fill(keyword, force=True, timeout=6000)
    input_node.press("Enter", timeout=6000)


def merge_candidate(pool: dict[str, dict[str, Any]], row: dict[str, Any]) -> None:
    identity = compact(row.get("identity"))
    if not identity:
        return
    if identity not in pool:
        pool[identity] = row
        return
    current = pool[identity]
    current["source_keywords"] = list(dict.fromkeys([*(current.get("source_keywords") or []), *(row.get("source_keywords") or [])]))
    for key, value in row.items():
        if current.get(key) in (None, "", [], {}) and value not in (None, "", [], {}):
            current[key] = value


def save_highwater(output: Path, strategy: dict[str, Any], shop: str, pool: dict[str, dict[str, Any]], per_keyword: list[dict[str, Any]]) -> None:
    candidates = list(pool.values())
    payload = {
        "status": "ready",
        "task_id": strategy.get("taskId"),
        "brand": strategy.get("brand"),
        "product": strategy.get("product"),
        "shop": shop,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "candidate_count": len(candidates),
        "precursor_eligible_count": sum(1 for row in candidates if precursor_eligible(row)),
        "per_keyword": per_keyword,
        "candidates": candidates,
    }
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--shop", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--scroll-rounds", type=int, default=8)
    parser.add_argument("--search-wait-ms", type=int, default=3200)
    parser.add_argument("--scroll-wait-ms", type=int, default=1100)
    args = parser.parse_args()

    strategy = json.loads(Path(args.strategy).resolve().read_text(encoding="utf-8"))
    keywords = [compact(value) for value in strategy.get("keywords") or [] if compact(value)]
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / f"osmana_candidate_pool_shop_{args.shop}.json"
    pool: dict[str, dict[str, Any]] = {}
    per_keyword: list[dict[str, Any]] = []

    with sync_playwright() as playwright:
        browser, context, _embedded_page = connect_shop(playwright.chromium, args.endpoint)
        page = _embedded_page
        page.set_default_timeout(15000)
        responses: list[dict[str, Any]] = []

        def on_response(response) -> None:
            if SEARCH_API_MARKER not in response.url:
                return
            try:
                responses.append(response.json())
            except Exception:
                pass

        page.on("response", on_response)
        try:
            page.goto(BUYIN_URL, wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(2200)
            assert_safe(page)
            clicked = apply_filters(page)
            emit({"status": "filters_applied", "shop": args.shop, "filters": clicked})
            for index, keyword in enumerate(keywords, start=1):
                before = len(responses)
                try:
                    fill_query(page, keyword)
                    page.wait_for_timeout(max(1800, args.search_wait_ms))
                    assert_safe(page)
                    for _ in range(max(0, min(args.scroll_rounds, 16))):
                        page.mouse.wheel(0, 1100)
                        page.wait_for_timeout(max(650, args.scroll_wait_ms))
                        assert_safe(page)
                except Exception as exc:
                    per_keyword.append({"keyword": keyword, "status": "paused", "message": compact(exc)[:300]})
                    save_highwater(output, strategy, args.shop, pool, per_keyword)
                    if "platform_paused" in compact(exc):
                        emit({"status": "platform_paused", "shop": args.shop, "message": compact(exc)})
                        break
                    continue

                keyword_rows: list[dict[str, Any]] = []
                for payload in responses[before:]:
                    keyword_rows.extend(candidates_from_payload(payload, keyword, args.shop))
                accepted = 0
                for row in keyword_rows:
                    if precursor_eligible(row):
                        before_size = len(pool)
                        merge_candidate(pool, row)
                        accepted += int(len(pool) > before_size)
                per_keyword.append({
                    "keyword": keyword,
                    "status": "succeeded",
                    "response_count": len(responses) - before,
                    "source_count": len(keyword_rows),
                    "new_precursor_count": accepted,
                    "pool_count": len(pool),
                })
                save_highwater(output, strategy, args.shop, pool, per_keyword)
                emit({
                    "status": "collection_progress",
                    "shop": args.shop,
                    "keyword": keyword,
                    "keyword_index": index,
                    "keyword_total": len(keywords),
                    "new_precursor_count": accepted,
                    "pool_count": len(pool),
                })
        finally:
            page.remove_listener("response", on_response)

    save_highwater(output, strategy, args.shop, pool, per_keyword)
    emit({"status": "collection_finished", "shop": args.shop, "output": str(output), "candidate_count": len(pool)})


if __name__ == "__main__":
    main()
