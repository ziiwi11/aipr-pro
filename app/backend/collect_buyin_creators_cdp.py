from __future__ import annotations

import argparse
from asyncio import CancelledError
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.request import urlopen

from playwright.sync_api import Page, sync_playwright

from atomic_json_io import atomic_write_json
from console_io import configure_utf8_stdout
from buyin_session_bootstrap import bootstrap_buyin_page
from contact_pipeline_contract import build_profile_url
from embedded_cdp import connect_shop, is_embedded_endpoint
from creator_delivery_contract import expanded_exclusion_hit
from pipeline_acceptance import allocate_shop_targets, creator_name_key, remaining_shop_target, source_pool_target


configure_utf8_stdout()

BUYIN_URL = "https://buyin.jinritemai.com/dashboard/servicehall/daren-square"
SEARCH_API_MARKER = "square/search_feed_author"
SAFETY_MARKERS = (
    "请求过于频繁",
    "稍后再试",
    "访问频繁",
    "安全验证",
    "当前环境存在风险",
)
CATEGORY_LABELS = {
    # 「美妆个护」同时勾选「美妆」与「个护家清」两个平台标签：
    # 判定侧 creator_delivery_contract 本就接受「美妆」或「个护家清」，
    # 但采集侧此前只勾「美妆」，导致大量个护家清达人未被纳入候选。
    "美妆个护": ["美妆", "个护家清"],
    "个护家清": ["个护家清"],
    "服饰内衣": ["服饰内衣"],
    "母婴宠物": ["母婴宠物"],
    "食品饮料": ["食品饮料"],
    "泛生活好物": ["生活家居"],
}


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def resolve_cdp_endpoint(endpoint: str) -> str:
    if endpoint.startswith(("ws://", "wss://")):
        return endpoint
    with urlopen(endpoint.rstrip("/") + "/json/version", timeout=5) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return str(payload["webSocketDebuggerUrl"])


def is_explicitly_logged_out_page_list(pages: list[dict[str, Any]]) -> bool:
    urls = [compact(item.get("url")) for item in pages if isinstance(item, dict) and item.get("type") == "page"]
    has_buyin_square = any("buyin.jinritemai.com/dashboard/servicehall/daren-square" in url for url in urls)
    has_fxg_login = any("fxg.jinritemai.com/login/" in url for url in urls)
    return has_fxg_login and not has_buyin_square


def endpoint_is_explicitly_logged_out(endpoint: str) -> bool:
    if is_embedded_endpoint(endpoint):
        return False
    if endpoint.startswith(("ws://", "wss://")):
        return False
    with urlopen(endpoint.rstrip("/") + "/json/list", timeout=5) as response:
        pages = json.loads(response.read().decode("utf-8"))
    return isinstance(pages, list) and is_explicitly_logged_out_page_list(pages)


def should_resume_completed_pool(candidate_count: int, target: int) -> bool:
    return max(0, int(candidate_count or 0)) >= max(1, int(target or 1))


def compact(value: Any) -> str:
    return str(value or "").strip()


def normalize_gender(value: Any) -> int:
    text = compact(value).lower()
    if text in {"2", "女", "女性", "female", "woman"}:
        return 2
    if text in {"1", "男", "男性", "male", "man"}:
        return 1
    try:
        numeric = int(value or 0)
    except (TypeError, ValueError):
        return 0
    return numeric if numeric in {1, 2} else 0


def parse_count(value: Any) -> int:
    """Parse platform count fields such as 3,000, 1.2万, or 2w."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return max(0, int(value))
    text = compact(value).lower().replace(",", "").replace("，", "")
    if not text:
        return 0
    multiplier = 1
    if "亿" in text:
        multiplier = 100_000_000
    elif "万" in text or re.search(r"\d\s*w(?:\+)?$", text):
        multiplier = 10_000
    match = re.search(r"\d+(?:\.\d+)?", text)
    if not match:
        return 0
    try:
        return max(0, int(float(match.group(0)) * multiplier))
    except (TypeError, ValueError, OverflowError):
        return 0


def contact_signal(value: Any) -> bool:
    """Normalize platform flags without treating the string 'false' as truthy."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value > 0
    if isinstance(value, dict):
        return any(contact_signal(item) for item in value.values())
    if isinstance(value, (list, tuple, set)):
        return any(contact_signal(item) for item in value)
    text = compact(value).lower()
    if not text:
        return False
    false_values = {"0", "false", "no", "none", "null", "n", "无", "暂无"}
    false_markers = ("暂无联系方式", "无联系方式", "不可查看", "未开放", "not_available", "disabled")
    if text in false_values or any(marker in text for marker in false_markers):
        return False
    true_values = {"1", "true", "yes", "y", "有", "可查看"}
    true_markers = ("有联系方式", "查看联系方式", "点击小眼睛", "contact", "eye", "icon")
    if text in true_values or any(marker in text for marker in true_markers):
        return True
    return text.startswith(("/", "http://", "https://", "data:"))


def contact_field_present(value: Any) -> bool:
    text = compact(value).lower()
    if not text:
        return False
    placeholders = {
        "--", "-", "暂无", "无", "未设置", "未填写", "null", "none",
        "not available", "n/a", "na", "false", "0",
    }
    return text not in placeholders


def normalize_categories(value: Any) -> list[str]:
    if isinstance(value, str):
        parts = re.split(r"[、,，/|;；>＞]+", value)
    elif isinstance(value, (list, tuple, set)):
        parts = [item for child in value for item in normalize_categories(child)]
    else:
        parts = [compact(value)] if compact(value) else []
    return list(dict.fromkeys(compact(item) for item in parts if compact(item)))


def candidate_identity_values(candidate: dict[str, Any]) -> set[str]:
    return {
        compact(candidate.get(key))
        for key in ("identity", "buyin_uid", "douyin_id", "author_id", "sec_uid")
        if compact(candidate.get(key))
    }


def resolve_active_shops(strategy: dict[str, Any]) -> list[str]:
    requested = [compact(value).upper() for value in strategy.get("activeShops") or ["A", "B"]]
    return list(dict.fromkeys(shop for shop in requested if shop in {"A", "B"}))


def assign_keywords_to_shops(
    shops: list[tuple[str, str]], keywords: list[str]
) -> list[tuple[str, str, list[str]]]:
    """Distribute every keyword across the shops that are actually active."""
    if not shops:
        return []
    stride = len(shops)
    return [
        (shop, endpoint, keywords[index::stride])
        for index, (shop, endpoint) in enumerate(shops)
    ]


def source_keyword_delay_ms(strategy: dict[str, Any]) -> int:
    """Return a bounded delay after each visible keyword search."""
    try:
        configured = int(strategy.get("sourceKeywordDelayMs") or 2600)
    except (TypeError, ValueError):
        configured = 2600
    return min(15000, max(2600, configured))


def source_page_delay_ms(strategy: dict[str, Any]) -> int:
    """Return a bounded delay between search-feed pagination requests."""
    try:
        configured = int(strategy.get("sourcePageDelayMs") or 1100)
    except (TypeError, ValueError):
        configured = 1100
    return min(15000, max(1100, configured))


def source_max_pages(strategy: dict[str, Any], shop_target: int) -> int:
    """Bound pagination using the actual source-pool target, not delivery count."""
    configured = strategy.get("sourceMaxPages")
    if configured not in (None, ""):
        try:
            return min(8, max(1, int(configured)))
        except (TypeError, ValueError):
            pass
    return 8 if int(shop_target or 0) >= 500 else 3


def source_max_keywords_per_run(strategy: dict[str, Any]) -> int:
    """Return the voluntary keyword batch size; zero disables batching."""
    configured = strategy.get("sourceMaxKeywordsPerRun")
    if configured in (None, "", 0, "0"):
        return 0
    try:
        return min(50, max(1, int(configured)))
    except (TypeError, ValueError):
        return 0


def source_discovery_mode(strategy: dict[str, Any]) -> str:
    """Select keyword search or unbiased structured-filter browsing."""
    configured = compact(strategy.get("sourceDiscoveryMode")).lower()
    if configured in {"browse", "structured_browse", "filter_browse"}:
        return "structured_browse"
    return "keyword_search"


def source_browse_pages_per_run(strategy: dict[str, Any]) -> int:
    """Bound each structured-browse batch so a checkpoint is always nearby."""
    try:
        configured = int(strategy.get("sourceBrowsePagesPerRun") or 12)
    except (TypeError, ValueError):
        configured = 12
    return min(30, max(1, configured))


def source_browse_max_pages(strategy: dict[str, Any]) -> int:
    """Bound total browse depth without relying on keyword fan-out."""
    try:
        configured = int(strategy.get("sourceBrowseMaxPages") or 60)
    except (TypeError, ValueError):
        configured = 60
    return min(100, max(1, configured))


def source_browse_profile_id(strategy: dict[str, Any]) -> str:
    """Return a stable checkpoint key for one structured-filter combination."""
    explicit = compact(strategy.get("sourceBrowseProfileId"))
    if explicit:
        return explicit
    levels = "-".join(str(int(level)) for level in strategy.get("creatorLevels") or [])
    return "|".join((
        compact(strategy.get("category")),
        compact(strategy.get("contentType")),
        f"lv:{levels}",
        f"fans:{int(strategy.get('minimumFollowers') or 0)}-{int(strategy.get('maximumFollowers') or 0)}",
        f"contact:{bool(strategy.get('requireContact'))}",
    ))


def collection_highwater_filename(strategy: dict[str, Any]) -> str:
    if compact(strategy.get("strategyPurpose")) == "replenishment-source-only":
        return "aipr_replenishment_collection_highwater.json"
    return "aipr_collection_highwater.json"


def collection_output_prefix(strategy: dict[str, Any]) -> str:
    if compact(strategy.get("strategyPurpose")) == "replenishment-source-only":
        return "aipr_buyin_creator_pool_replenishment"
    return "aipr_buyin_creator_pool"


def completed_keywords_from_payload(payload: dict[str, Any]) -> dict[str, set[str]]:
    raw = payload.get("completed_keywords_by_shop")
    if not isinstance(raw, dict):
        return {}
    return {
        compact(shop).upper(): {
            compact(keyword) for keyword in keywords or [] if compact(keyword)
        }
        for shop, keywords in raw.items()
        if compact(shop).upper() in {"A", "B"} and isinstance(keywords, list)
    }


def completed_pages_from_payload(payload: dict[str, Any]) -> dict[str, set[int]]:
    raw = payload.get("completed_pages_by_shop")
    if not isinstance(raw, dict):
        return {}
    result: dict[str, set[int]] = {}
    for shop, pages in raw.items():
        normalized_shop = compact(shop).upper()
        if normalized_shop not in {"A", "B"} or not isinstance(pages, list):
            continue
        normalized_pages: set[int] = set()
        for page in pages:
            try:
                page_number = int(page)
            except (TypeError, ValueError):
                continue
            if page_number > 0:
                normalized_pages.add(page_number)
        result[normalized_shop] = normalized_pages
    return result


def pending_shop_keywords(keywords: list[str], completed: set[str]) -> list[tuple[int, str]]:
    return [
        (index, keyword)
        for index, keyword in enumerate(keywords)
        if keyword not in completed
    ]


def serialized_completed_keywords(
    strategy: dict[str, Any], completed_keywords_by_shop: dict[str, set[str]] | None,
) -> dict[str, list[str]]:
    keyword_order = [compact(item) for item in strategy.get("keywords") or [] if compact(item)]
    completed_keywords_by_shop = completed_keywords_by_shop or {}
    return {
        shop: [keyword for keyword in keyword_order if keyword in completed]
        for shop, completed in completed_keywords_by_shop.items()
        if shop in {"A", "B"} and completed
    }


def serialized_completed_pages(
    completed_pages_by_shop: dict[str, set[int]] | None,
) -> dict[str, list[int]]:
    return {
        compact(shop).upper(): sorted(int(page) for page in pages if int(page) > 0)
        for shop, pages in (completed_pages_by_shop or {}).items()
        if compact(shop).upper() in {"A", "B"}
    }


def click_text(page: Page, label: str) -> bool:
    if not label:
        return False
    try:
        locator = page.get_by_text(label, exact=True).first
        if locator.count() and locator.is_visible(timeout=800):
            try:
                locator.click(timeout=1800, force=True)
            except Exception:
                locator.evaluate("el => el.click()")
            return True
    except Exception:
        pass
    return False


def assert_safe(page: Page) -> None:
    try:
        body = page.locator("body").inner_text(timeout=3000)
    except Exception:
        return
    marker = next((item for item in SAFETY_MARKERS if item in body), "")
    if marker:
        raise RuntimeError(f"platform_paused:{marker}")


def assert_safe_payload(payload: dict[str, Any]) -> None:
    error_keys = {"message", "msg", "errmsg", "error_msg", "toast", "tips", "tip"}
    messages = [
        compact(value)
        for item in walk_objects(payload)
        for key, value in item.items()
        if compact(key).lower() in error_keys and isinstance(value, (str, int, float))
    ]
    marker = next(
        (safety for message in messages for safety in SAFETY_MARKERS if safety in message),
        "",
    )
    if marker:
        raise RuntimeError(f"platform_paused:{marker}")


def assert_safe_payloads(payloads: Iterable[dict[str, Any]]) -> None:
    for payload in payloads:
        if isinstance(payload, dict):
            assert_safe_payload(payload)


def fetch_search_page(page: Page, request_body: dict[str, Any], page_number: int) -> dict[str, Any]:
    body = {**request_body, "page": int(page_number), "refresh": False}
    payload = page.evaluate(
        """async body => {
            const response = await fetch('/square_pc_api/square/search_feed_author', {
                method: 'POST',
                credentials: 'include',
                headers: {'content-type': 'application/json'},
                body: JSON.stringify(body),
            });
            return await response.json();
        }""",
        body,
    )
    if not isinstance(payload, dict):
        raise RuntimeError("buyin_search_page_invalid_payload")
    assert_safe_payload(payload)
    return payload


def structured_browse_request_body(
    request_bodies: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Reuse the platform's own filtered request while forcing an empty query."""
    for request_body in reversed(request_bodies):
        if not isinstance(request_body, dict):
            continue
        try:
            page_number = int(request_body.get("page") or 1)
        except (TypeError, ValueError):
            page_number = 1
        if page_number != 1:
            continue
        body = dict(request_body)
        body["query"] = ""
        body["page"] = 1
        body["refresh"] = False
        return body
    return None


def detach_page_response_listener(page: Page, callback) -> None:
    page.remove_listener("response", callback)


def record_search_response(
    response,
    payloads: list[dict[str, Any]],
    request_bodies: list[dict[str, Any]],
) -> None:
    """Best-effort response telemetry that stays quiet during CDP shutdown."""
    if SEARCH_API_MARKER not in response.url:
        return
    try:
        payload = response.json()
        if isinstance(payload, dict):
            payloads.append(payload)
    except (Exception, CancelledError):
        pass
    try:
        body = response.request.post_data_json
        if isinstance(body, dict):
            request_bodies.append(body)
    except (Exception, CancelledError):
        pass


def find_search_input(page: Page):
    candidates = page.locator("input,textarea,[contenteditable='true']")
    for index in range(min(candidates.count(), 80)):
        node = candidates.nth(index)
        try:
            if not node.is_visible(timeout=400):
                continue
            meta = node.evaluate(
                """el => `${el.placeholder || ''} ${el.getAttribute('aria-label') || ''} ${(el.closest('form,section,div') || el).innerText || ''}`"""
            )
            if any(token in meta for token in ("搜达人", "达人昵称", "抖音号", "带货品牌", "主推类目")):
                return node
        except Exception:
            continue
    raise RuntimeError("buyin_search_input_not_found")


def fill_search(page: Page, keyword: str) -> None:
    node = find_search_input(page)
    page.keyboard.press("Escape")
    page.wait_for_timeout(250)
    # The embedded shop view can be wider than Electron's visible viewport.
    # Clicking an otherwise visible Auxo combobox then fails with "outside of
    # the viewport". Playwright's forced fill still drives React's input
    # events and does not require pointer coordinates.
    try:
        node.fill(keyword, timeout=2200, force=True)
        node.focus(timeout=1200)
    except Exception:
        node.evaluate(
            """(el, value) => {
                const setter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value'
                )?.set;
                if (setter) setter.call(el, value); else el.value = value;
                el.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: value}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                el.focus();
            }""",
            keyword,
        )
    clicked = False
    try:
        buttons = page.locator("button").filter(has_text="搜索")
        for index in range(min(buttons.count(), 8)):
            button = buttons.nth(index)
            if button.is_visible(timeout=500) and button.is_enabled(timeout=500):
                button.click(timeout=1600)
                clicked = True
                break
    except Exception:
        pass
    if not clicked:
        page.keyboard.press("Enter")


def trigger_structured_browse(page: Page) -> None:
    """Refresh the filtered result list without submitting a search keyword."""
    node = find_search_input(page)
    page.keyboard.press("Escape")
    page.wait_for_timeout(250)
    try:
        node.fill("", timeout=2200, force=True)
        node.focus(timeout=1200)
    except Exception:
        node.evaluate(
            """el => {
                const setter = Object.getOwnPropertyDescriptor(
                    window.HTMLInputElement.prototype, 'value'
                )?.set;
                if (setter) setter.call(el, ''); else el.value = '';
                el.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'deleteContentBackward'}));
                el.dispatchEvent(new Event('change', {bubbles: true}));
                el.focus();
            }"""
        )
    clicked = False
    try:
        buttons = page.locator("button").filter(has_text="搜索")
        for index in range(min(buttons.count(), 8)):
            button = buttons.nth(index)
            if button.is_visible(timeout=500) and button.is_enabled(timeout=500):
                button.click(timeout=1600)
                clicked = True
                break
    except Exception:
        pass
    if not clicked:
        page.keyboard.press("Enter")


def strategy_filter_labels(strategy: dict[str, Any]) -> list[str]:
    category = compact(strategy.get("category"))
    content_type = compact(strategy.get("contentType"))
    labels = [*(CATEGORY_LABELS.get(category) or [category])]
    if content_type in {"真人口播", "短视频"}:
        labels.append("视频达人")
    elif content_type:
        labels.append(content_type)
    if strategy.get("requireContact"):
        labels.append("有联系方式")
    minimum_sales = int(strategy.get("minimumMonthlySales") or 0)
    if minimum_sales >= 100000:
        labels.append("10万以上")
    elif minimum_sales >= 50000:
        labels.append("5万以上")
    elif minimum_sales >= 10000:
        labels.append("1万以上")
    return list(dict.fromkeys(item for item in labels if item))


def apply_strategy_filters(page: Page, strategy: dict[str, Any]) -> list[str]:
    applied: list[str] = []
    for label in strategy_filter_labels(strategy):
        if click_text(page, label):
            applied.append(label)
    levels = [int(level) for level in strategy.get("creatorLevels") or []]
    if levels:
        click_text(page, "达人等级")
        for level in levels:
            label = f"LV{level}"
            if click_text(page, label):
                applied.append(label)
    return applied


def walk_objects(value: Any) -> Iterable[dict[str, Any]]:
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_objects(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_objects(child)


def candidate_from_object(item: dict[str, Any], keyword: str, shop: str) -> dict[str, Any] | None:
    nickname = compact(item.get("nickname") or item.get("nick_name") or item.get("author_name"))
    identity = compact(
        item.get("author_id") or item.get("account_id") or item.get("uid")
        or item.get("douyin_id") or item.get("sec_uid")
    )
    if not nickname or not identity:
        return None
    try:
        level = parse_count(item.get("talent_level") or item.get("level") or item.get("author_level"))
    except (TypeError, ValueError):
        level = 0
    profile_url = build_profile_url(identity, level)
    return {
        "identity": identity,
        "nickname": nickname,
        "douyin_id": compact(item.get("douyin_id") or item.get("unique_id") or identity),
        "sec_uid": compact(item.get("sec_uid")),
        "talent_level": compact(item.get("talent_level") or item.get("level") or item.get("author_level")),
        "fans": parse_count(item.get("fans") or item.get("fans_count") or item.get("follower_count")),
        "gender": normalize_gender(item.get("gender")),
        "city": compact(item.get("city")),
        "monthly_sales": item.get("monthly_sales") or item.get("sale_amount") or item.get("gmv") or "",
        "category": compact(item.get("category") or item.get("main_category") or item.get("first_cate_name")),
        "contact_visible": any(contact_signal(item.get(key)) for key in (
            "contact_visible", "has_contact", "show_contact", "contact_icon"
        )),
        "buyin_uid": identity,
        "buyin_profile_url": profile_url,
        "精选联盟主页": profile_url,
        "source_keyword": keyword,
        "source_discovery_mode": "keyword_search" if keyword else "structured_browse",
        "shop": shop,
    }


def candidate_from_search_item(item: dict[str, Any], keyword: str, shop: str) -> dict[str, Any] | None:
    base = item.get("author_base") if isinstance(item.get("author_base"), dict) else {}
    tags = item.get("author_tag") if isinstance(item.get("author_tag"), dict) else {}
    contact = item.get("author_contact") if isinstance(item.get("author_contact"), dict) else {}
    sale = item.get("author_sale") if isinstance(item.get("author_sale"), dict) else {}
    video = item.get("author_video") if isinstance(item.get("author_video"), dict) else {}
    identity = compact(base.get("uid") or base.get("author_id"))
    nickname = compact(base.get("nickname"))
    if not identity or not nickname:
        return None
    level = parse_count(base.get("author_level"))
    categories = normalize_categories(tags.get("main_cate"))
    contact_visible = contact_signal(tags.get("contact_icon")) or any(
        compact(reason.get("reason")) == "有联系方式"
        for reason in tags.get("author_rec_reasons") or []
        if isinstance(reason, dict)
    ) or any(contact_field_present(contact.get(key)) for key in ("wechat", "phone", "email"))
    profile_url = build_profile_url(identity)
    return {
        "identity": identity,
        "nickname": nickname,
        "douyin_id": compact(base.get("aweme_id")),
        "fans": parse_count(base.get("fans_num")),
        "gender": normalize_gender(base.get("gender")),
        "city": compact(base.get("city")),
        "talent_level": f"LV{level}",
        "author_level": level,
        "category": "/".join(categories),
        "categories": categories,
        "monthly_sales_low": parse_count(sale.get("sale_d30_low")),
        "monthly_sales_high": parse_count(sale.get("sale_d30_high")),
        "video_count_30d": parse_count(video.get("all_video_num_30d")),
        "main_sale_type": compact(sale.get("main_sale_type")),
        "contact_visible": contact_visible,
        "buyin_contact_visible": contact_visible,
        "buyin_contact_wechat": compact(contact.get("wechat")),
        "buyin_contact_phone": compact(contact.get("phone")),
        "buyin_uid": identity,
        "buyin_profile_url": profile_url,
        "精选联盟主页": profile_url,
        "source_keyword": keyword,
        "source_keywords": [keyword] if keyword else [],
        "source_discovery_mode": "keyword_search" if keyword else "structured_browse",
        "shop": shop,
    }


def extract_candidates(payloads: list[dict[str, Any]], keyword: str, shop: str) -> list[dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for payload in payloads:
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        rows = data.get("list") if isinstance(data.get("list"), list) else []
        if rows:
            for item in rows:
                if not isinstance(item, dict):
                    continue
                candidate = candidate_from_search_item(item, keyword, shop)
                if candidate:
                    result.setdefault(candidate["identity"], candidate)
            continue
        for item in walk_objects(payload):
            candidate = candidate_from_object(item, keyword, shop)
            if candidate:
                result.setdefault(candidate["identity"], candidate)
    return list(result.values())


def candidate_matches_strategy(candidate: dict[str, Any], strategy: dict[str, Any]) -> bool:
    if expanded_exclusion_hit(candidate, strategy):
        return False
    nickname = compact(candidate.get("nickname"))
    if any(
        marker and marker in nickname
        for marker in (
            compact(item) for item in strategy.get("excludeNicknameContains") or []
        )
    ):
        return False
    if strategy.get("requireContact") and not bool(candidate.get("contact_visible")):
        return False
    try:
        fans = parse_count(candidate.get("fans"))
    except (TypeError, ValueError):
        fans = 0
    minimum_followers = max(0, int(strategy.get("minimumFollowers") or 0))
    maximum_followers = max(0, int(strategy.get("maximumFollowers") or 0))
    if minimum_followers and fans < minimum_followers:
        return False
    if maximum_followers and fans > maximum_followers:
        return False
    minimum_videos_30d = max(0, int(strategy.get("minimumVideos30d") or 0))
    if minimum_videos_30d and parse_count(candidate.get("video_count_30d")) < minimum_videos_30d:
        return False
    category = compact(strategy.get("category"))
    keywords = " ".join(compact(item) for item in strategy.get("keywords") or [])
    beauty_task = category in {"美妆个护", "美妆", "个护家清"} or any(
        token in keywords for token in ("唇", "口红", "美妆", "护肤")
    )
    if beauty_task:
        if normalize_gender(candidate.get("gender")) != 2:
            return False
        creator_categories = compact(candidate.get("category"))
        if creator_categories and not any(
            token in creator_categories for token in ("美妆", "个护家清")
        ):
            return False
    return True


def candidate_matches_source_profile(
    candidate: dict[str, Any], strategy: dict[str, Any],
) -> bool:
    """Apply profile-only gates to newly fetched rows.

    Source browse profiles are additive: changing from LV1-LV2 to LV3-LV4
    must preserve the already accepted pool while preventing rows from the
    wrong level from being attributed to the new profile.  The platform's
    level popover is not reliably exposed to Playwright, so this local gate is
    also the final correctness boundary when the UI click does not stick.
    """
    requested_levels = {
        int(level)
        for level in strategy.get("creatorLevels") or []
        if str(level).strip().isdigit()
    }
    if requested_levels:
        candidate_level = parse_count(
            candidate.get("author_level") or candidate.get("talent_level")
        )
        if candidate_level not in requested_levels:
            return False
    if strategy.get("sourceProfileCategoryStrict"):
        requested_category = compact(strategy.get("category"))
        category_labels = CATEGORY_LABELS.get(requested_category) or [requested_category]
        candidate_categories = compact(candidate.get("category"))
        if requested_category and not any(
            label and label in candidate_categories for label in category_labels
        ):
            return False
    return True


def merge_candidate_pool(
    existing: dict[str, dict[str, Any]],
    incoming: list[dict[str, Any]],
    excluded: set[str] | None = None,
) -> tuple[dict[str, dict[str, Any]], int]:
    excluded = excluded or set()
    seen_names = {creator_name_key(item.get("nickname")) for item in existing.values() if creator_name_key(item.get("nickname"))}
    identity_owner = {
        value: key
        for key, item in existing.items()
        for value in candidate_identity_values(item)
    }
    added = 0
    for candidate in incoming:
        identity = compact(candidate.get("identity"))
        name_key = creator_name_key(candidate.get("nickname"))
        identity_values = candidate_identity_values(candidate)
        if not identity or identity_values & excluded:
            continue
        owner_key = next(
            (identity_owner[value] for value in identity_values if value in identity_owner),
            "",
        )
        if owner_key:
            previous = existing[owner_key]
            existing[owner_key] = {
                **candidate,
                **{key: value for key, value in previous.items() if value not in (None, "", [], {})},
            }
            for value in candidate_identity_values(existing[owner_key]) | identity_values:
                identity_owner[value] = owner_key
            continue
        if name_key and name_key in seen_names:
            continue
        existing[identity] = dict(candidate)
        for value in identity_values:
            identity_owner[value] = identity
        if name_key:
            seen_names.add(name_key)
        added += 1
    return existing, added


def process_new_candidate_identities(
    output: dict[str, dict[str, Any]],
    identities: list[str],
    processor: Any,
    context: Any,
    page: Any,
) -> dict[str, int | bool]:
    processed = 0
    paused = False
    rate_limited_streak = 0
    for identity in identities:
        candidate = output.get(identity)
        if not isinstance(candidate, dict):
            continue
        updated = processor.process(context, page, candidate)
        output[identity] = dict(updated)
        processed += 1
        reason = compact(updated.get("realtime_flow_reason")).lower()
        # 仅「每日配额耗尽」代表额度用尽，需要暂停整个流程。
        # 偶发「rate_limited」是单次频次抖动，跳过该达人继续即可；
        # 连续 3 次才升级为暂停，避免一次抖动就中断整轮采集。
        if reason == "daily_quota_exhausted":
            paused = True
            break
        if reason == "rate_limited":
            rate_limited_streak += 1
            if rate_limited_streak >= 3:
                paused = True
                break
        else:
            rate_limited_streak = 0
    return {"processed": processed, "paused": paused}


def create_realtime_review_page(context: Any, browse_page: Any) -> tuple[Any, bool]:
    """Use a dedicated page when possible, otherwise reuse Electron's BrowserView.

    AIPR's embedded shop contexts expose one visible target and deliberately do
    not implement Target.createTarget.  Reusing that visible page keeps review
    inside the app instead of falling back to an external browser.
    """
    try:
        review_page = context.new_page()
    except Exception as exc:
        if "notsupported" not in re.sub(r"\W", "", compact(exc)).lower():
            raise
        return browse_page, True
    return review_page, False


def restore_structured_browse_page(page: Any, strategy: dict[str, Any]) -> None:
    page.goto(BUYIN_URL, wait_until="domcontentloaded", timeout=45000)
    page.locator("input[placeholder*='搜达人昵称']").first.wait_for(
        state="visible", timeout=20000,
    )
    page.wait_for_timeout(500)
    assert_safe(page)
    click_text(page, "重置")
    page.wait_for_timeout(500)
    apply_strategy_filters(page, strategy)
    page.keyboard.press("Escape")
    page.wait_for_timeout(400)
    trigger_structured_browse(page)
    page.wait_for_timeout(source_keyword_delay_ms(strategy))
    assert_safe(page)


def filter_resumed_candidate_pool(
    candidates: dict[str, dict[str, Any]],
    strategy: dict[str, Any],
    excluded: set[str] | None = None,
) -> dict[str, dict[str, Any]]:
    """Reapply current hard gates to an older checkpoint before resuming.

    Filter aliases and task rules can be tightened after a checkpoint was
    written.  Keeping stale rows would let already identified business or
    off-vertical accounts survive every later resume.
    """
    excluded = excluded or set()
    return {
        identity: candidate
        for identity, candidate in candidates.items()
        if not (candidate_identity_values(candidate) & excluded)
        and candidate_matches_strategy(candidate, strategy)
    }


def save_highwater(
    path: Path,
    strategy: dict[str, Any],
    candidates: dict[str, dict[str, Any]],
    completed_keywords_by_shop: dict[str, set[str]] | None = None,
    completed_pages_by_shop: dict[str, set[int]] | None = None,
) -> None:
    target = source_pool_target(
        int(strategy.get("targetCount") or 500), bool(strategy.get("requireContact"))
    )
    complete = len(candidates) >= target
    atomic_write_json(path, {
        "status": "ready" if complete else "checkpoint",
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "strategy": strategy,
        "target_count": target,
        "candidate_count": len(candidates),
        "complete": complete,
        "completed_keywords_by_shop": serialized_completed_keywords(
            strategy, completed_keywords_by_shop,
        ),
        "completed_pages_by_shop": serialized_completed_pages(completed_pages_by_shop),
        "browse_profile_id": source_browse_profile_id(strategy),
        "candidates": list(candidates.values()),
    })


def collect_shop(
    endpoint: str,
    shop: str,
    keywords: list[str],
    strategy: dict[str, Any],
    output: dict[str, dict[str, Any]],
    shop_target: int,
    excluded: set[str],
    highwater_path: Path,
    completed_keywords_by_shop: dict[str, set[str]] | None = None,
) -> bool:
    completed_keywords_by_shop = completed_keywords_by_shop if completed_keywords_by_shop is not None else {}
    completed = completed_keywords_by_shop.setdefault(shop, set())
    with sync_playwright() as playwright:
        browser, context, _embedded_page = connect_shop(playwright.chromium, endpoint)
        page = bootstrap_buyin_page(context, preferred_page=_embedded_page)
        page.set_default_timeout(12000)
        realtime_processor = None
        realtime_page = None
        realtime_uses_browse_page = False
        if strategy.get("realtimeCreatorFlow") is True:
            from realtime_creator_processor import RealtimeCreatorProcessor

            realtime_processor = RealtimeCreatorProcessor(
                output_dir=highwater_path.parent,
                strategy=strategy,
                historical_strategy={},
            )
            realtime_page, realtime_uses_browse_page = create_realtime_review_page(
                context, page,
            )
            realtime_page.set_default_timeout(15000)
        payloads: list[dict[str, Any]] = []
        request_bodies: list[dict[str, Any]] = []

        def record_response(response) -> None:
            record_search_response(response, payloads, request_bodies)

        page.on("response", record_response)
        processed_keywords = 0
        keyword_batch_limit = source_max_keywords_per_run(strategy)
        try:
            page.locator("input[placeholder*='搜达人昵称']").first.wait_for(state="visible", timeout=20000)
            page.wait_for_timeout(800)
            assert_safe(page)
            click_text(page, "重置")
            page.wait_for_timeout(800)
            applied = apply_strategy_filters(page, strategy)
            page.keyboard.press("Escape")
            page.wait_for_timeout(700)
            emit({"status": "filters_applied", "shop": shop, "filters": applied})

            for index, keyword in pending_shop_keywords(keywords, completed):
                before = len(payloads)
                requests_before = len(request_bodies)
                fill_search(page, keyword)
                page.wait_for_timeout(source_keyword_delay_ms(strategy))
                assert_safe(page)
                assert_safe_payloads(payloads[before:])
                base_request = next((
                    body for body in reversed(request_bodies[requests_before:])
                    if compact(body.get("query")) == keyword and int(body.get("page") or 1) == 1
                ), None)
                if base_request:
                    maximum_page = source_max_pages(strategy, shop_target)
                    for page_number in range(2, maximum_page + 1):
                        fetched = fetch_search_page(page, base_request, page_number)
                        payloads.append(fetched)
                        data = fetched.get("data") if isinstance(fetched.get("data"), dict) else {}
                        page.wait_for_timeout(source_page_delay_ms(strategy))
                        assert_safe(page)
                        if not data.get("list") or data.get("has_more") is False:
                            break
                else:
                    # DOM scrolling remains a compatibility fallback if the
                    # platform changes the request body shape.
                    for _ in range(2):
                        page.mouse.wheel(0, 900)
                        page.wait_for_timeout(source_page_delay_ms(strategy))
                        assert_safe(page)
                candidates = [
                    candidate for candidate in extract_candidates(payloads[before:], keyword, shop)
                    if candidate_matches_strategy(candidate, strategy)
                ]
                current_shop_count = sum(1 for item in output.values() if item.get("shop") == shop)
                remaining = max(0, shop_target - current_shop_count)
                if remaining == 0:
                    break
                before_identities = set(output)
                output, accepted = merge_candidate_pool(output, candidates[:remaining], excluded)
                new_identities = [identity for identity in output if identity not in before_identities]
                if realtime_processor is not None and realtime_page is not None and new_identities:
                    realtime_result = process_new_candidate_identities(
                        output, new_identities, realtime_processor, context, realtime_page,
                    )
                    if realtime_uses_browse_page:
                        restore_structured_browse_page(page, strategy)
                    if realtime_result["paused"]:
                        save_highwater(highwater_path, strategy, output, completed_keywords_by_shop)
                        emit({
                            "status": "pipeline_waiting_for_contact_quota",
                            "shop": shop,
                            **realtime_processor.flow.summary(),
                        })
                        return True
                completed.add(keyword)
                processed_keywords += 1
                save_highwater(highwater_path, strategy, output, completed_keywords_by_shop)
                emit({
                    "status": "collection_progress", "shop": shop, "keyword": keyword,
                    "keyword_index": index + 1, "keyword_total": len(keywords),
                    "new_candidates": accepted, "source_candidates": len(candidates), "candidate_count": len(output),
                })
                if sum(1 for item in output.values() if item.get("shop") == shop) >= shop_target:
                    break
                if keyword_batch_limit and processed_keywords >= keyword_batch_limit:
                    emit({
                        "status": "collection_batch_checkpoint",
                        "shop": shop,
                        "processed_keywords": processed_keywords,
                        "candidate_count": len(output),
                    })
                    return True
        finally:
            detach_page_response_listener(page, record_response)
            # The browser belongs to the user and must remain open.
            pass
    return False


def collect_shop_browse(
    endpoint: str,
    shop: str,
    strategy: dict[str, Any],
    output: dict[str, dict[str, Any]],
    shop_target: int,
    excluded: set[str],
    highwater_path: Path,
    completed_pages_by_shop: dict[str, set[int]] | None = None,
) -> bool:
    """Collect from structured filters and pagination without search keywords."""
    completed_pages_by_shop = completed_pages_by_shop if completed_pages_by_shop is not None else {}
    completed_pages = completed_pages_by_shop.setdefault(shop, set())
    with sync_playwright() as playwright:
        browser, context, _embedded_page = connect_shop(playwright.chromium, endpoint)
        page = bootstrap_buyin_page(context, preferred_page=_embedded_page)
        page.set_default_timeout(12000)
        realtime_processor = None
        realtime_page = None
        realtime_uses_browse_page = False
        if strategy.get("realtimeCreatorFlow") is True:
            from realtime_creator_processor import RealtimeCreatorProcessor

            realtime_processor = RealtimeCreatorProcessor(
                output_dir=highwater_path.parent,
                strategy=strategy,
                historical_strategy={},
            )
            realtime_page, realtime_uses_browse_page = create_realtime_review_page(
                context, page,
            )
            realtime_page.set_default_timeout(15000)
        payloads: list[dict[str, Any]] = []
        request_bodies: list[dict[str, Any]] = []

        def record_response(response) -> None:
            record_search_response(response, payloads, request_bodies)

        page.on("response", record_response)
        try:
            page.locator("input[placeholder*='搜达人昵称']").first.wait_for(state="visible", timeout=20000)
            page.wait_for_timeout(800)
            assert_safe(page)
            click_text(page, "重置")
            page.wait_for_timeout(800)
            applied = apply_strategy_filters(page, strategy)
            page.keyboard.press("Escape")
            page.wait_for_timeout(700)
            trigger_structured_browse(page)
            page.wait_for_timeout(source_keyword_delay_ms(strategy))
            assert_safe(page)
            assert_safe_payloads(payloads)
            base_request = structured_browse_request_body(request_bodies)
            if not base_request:
                raise RuntimeError("buyin_structured_browse_request_not_found")
            emit({
                "status": "filters_applied", "shop": shop, "filters": applied,
                "source_discovery_mode": "structured_browse",
            })

            processed_pages = 0
            maximum_page = source_browse_max_pages(strategy)
            page_batch_limit = source_browse_pages_per_run(strategy)
            for page_number in range(1, maximum_page + 1):
                if page_number in completed_pages:
                    continue
                fetched = fetch_search_page(page, base_request, page_number)
                data = fetched.get("data") if isinstance(fetched.get("data"), dict) else {}
                candidates = []
                for candidate in extract_candidates([fetched], "", shop):
                    candidate["source_page"] = page_number
                    candidate["source_discovery_mode"] = "structured_browse"
                    if (
                        candidate_matches_strategy(candidate, strategy)
                        and candidate_matches_source_profile(candidate, strategy)
                    ):
                        candidates.append(candidate)
                current_shop_count = sum(1 for item in output.values() if item.get("shop") == shop)
                remaining = max(0, shop_target - current_shop_count)
                if remaining == 0:
                    break
                identities_before = set(output)
                output, accepted = merge_candidate_pool(output, candidates[:remaining], excluded)
                new_identities = [identity for identity in output if identity not in identities_before]
                realtime_result = {"processed": 0, "paused": False}
                if realtime_processor is not None and realtime_page is not None and new_identities:
                    realtime_result = process_new_candidate_identities(
                        output,
                        new_identities,
                        realtime_processor,
                        context=context,
                        page=realtime_page,
                    )
                completed_pages.add(page_number)
                processed_pages += 1
                save_highwater(
                    highwater_path, strategy, output,
                    completed_pages_by_shop=completed_pages_by_shop,
                )
                emit({
                    "status": "collection_browse_progress",
                    "shop": shop,
                    "page": page_number,
                    "page_total": maximum_page,
                    "new_candidates": accepted,
                    "source_candidates": len(candidates),
                    "candidate_count": len(output),
                })
                if realtime_processor is not None:
                    emit({
                        "status": "realtime_creator_progress",
                        "shop": shop,
                        "page": page_number,
                        **realtime_result,
                        **realtime_processor.flow.summary(),
                    })
                if (
                    realtime_uses_browse_page
                    and int(realtime_result.get("processed") or 0) > 0
                    and not realtime_result.get("paused")
                ):
                    restore_structured_browse_page(page, strategy)
                if realtime_result.get("paused"):
                    emit({
                        "status": "collection_batch_checkpoint",
                        "shop": shop,
                        "processed_pages": processed_pages,
                        "candidate_count": len(output),
                        "source_discovery_mode": "structured_browse",
                        "reason": "realtime_contact_platform_pause",
                    })
                    return True
                if len(output) >= shop_target:
                    break
                if not data.get("list") or data.get("has_more") is False:
                    break
                page.wait_for_timeout(source_page_delay_ms(strategy))
                assert_safe(page)
                if processed_pages >= page_batch_limit:
                    emit({
                        "status": "collection_batch_checkpoint",
                        "shop": shop,
                        "processed_pages": processed_pages,
                        "candidate_count": len(output),
                        "source_discovery_mode": "structured_browse",
                    })
                    return True
        finally:
            detach_page_response_listener(page, record_response)
            if realtime_page is not None and not realtime_uses_browse_page:
                try:
                    realtime_page.close()
                except Exception:
                    pass
            # The browser belongs to the user and must remain open.
            pass
    return False


def finish_collection(
    output_dir: Path,
    strategy: dict[str, Any],
    candidates: dict[str, dict[str, Any]],
    highwater_path: Path,
    emit_status: str = "collection_finished",
    completed_keywords_by_shop: dict[str, set[str]] | None = None,
    completed_pages_by_shop: dict[str, set[int]] | None = None,
) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = output_dir / f"{collection_output_prefix(strategy)}_{stamp}.json"
    target = source_pool_target(
        int(strategy.get("targetCount") or 500), bool(strategy.get("requireContact"))
    )
    complete = len(candidates) >= target and emit_status == "collection_finished"
    payload = {
        "status": "ready" if complete else "checkpoint",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "strategy": strategy,
        "target_count": target,
        "candidate_count": len(candidates),
        "complete": complete,
        "completed_keywords_by_shop": serialized_completed_keywords(
            strategy, completed_keywords_by_shop,
        ),
        "completed_pages_by_shop": serialized_completed_pages(completed_pages_by_shop),
        "browse_profile_id": source_browse_profile_id(strategy),
        "candidates": list(candidates.values()),
    }
    atomic_write_json(output, payload)
    save_highwater(
        highwater_path, strategy, candidates,
        completed_keywords_by_shop, completed_pages_by_shop,
    )
    emit({"status": emit_status, "output": str(output), "candidate_count": len(candidates)})
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect creators from Buyin using an editable AIPR strategy.")
    parser.add_argument("--strategy", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--shop-a", default="http://127.0.0.1:9222?shop=A")
    parser.add_argument("--shop-b", default="http://127.0.0.1:9222?shop=B")
    args = parser.parse_args()

    strategy_path = Path(args.strategy).resolve()
    strategy = json.loads(strategy_path.read_text(encoding="utf-8"))
    discovery_mode = source_discovery_mode(strategy)
    keywords = [compact(item) for item in strategy.get("keywords") or [] if compact(item)]
    if discovery_mode == "keyword_search" and not keywords:
        raise SystemExit("collection strategy has no keywords")

    output_dir = Path(args.out_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    highwater_path = output_dir / collection_highwater_filename(strategy)
    candidates: dict[str, dict[str, Any]] = {}
    completed_keywords_by_shop: dict[str, set[str]] = {}
    completed_pages_by_shop: dict[str, set[int]] = {}
    if highwater_path.exists():
        try:
            prior = json.loads(highwater_path.read_text(encoding="utf-8"))
            candidates = {
                compact(row.get("identity")): dict(row)
                for row in prior.get("candidates") or []
                if isinstance(row, dict) and compact(row.get("identity"))
            }
            completed_keywords_by_shop = completed_keywords_from_payload(prior)
            completed_pages_by_shop = completed_pages_from_payload(prior)
            prior_strategy = prior.get("strategy") if isinstance(prior.get("strategy"), dict) else {}
            prior_profile_id = compact(prior.get("browse_profile_id")) or source_browse_profile_id(prior_strategy)
            if discovery_mode == "structured_browse" and prior_profile_id != source_browse_profile_id(strategy):
                completed_pages_by_shop = {}
        except (OSError, json.JSONDecodeError):
            candidates = {}
            completed_keywords_by_shop = {}
            completed_pages_by_shop = {}
    excluded = {compact(item) for item in strategy.get("excludeIdentities") or [] if compact(item)}
    resumed_raw_count = len(candidates)
    candidates = filter_resumed_candidate_pool(candidates, strategy, excluded)
    target = source_pool_target(int(strategy.get("targetCount") or 500), bool(strategy.get("requireContact")))
    emit({
        "status": "collection_started",
        "source_discovery_mode": discovery_mode,
        "browse_profile_id": source_browse_profile_id(strategy) if discovery_mode == "structured_browse" else "",
        "keywords": keywords,
        "target_count": target,
        "resumed_count": len(candidates),
        "resumed_filtered_count": resumed_raw_count - len(candidates),
        "resumed_completed_keywords": {
            shop: len(values) for shop, values in completed_keywords_by_shop.items()
        },
        "resumed_completed_pages": {
            shop: len(values) for shop, values in completed_pages_by_shop.items()
        },
    })
    if should_resume_completed_pool(len(candidates), target):
        emit({"status": "collection_resumed_complete", "candidate_count": len(candidates), "target_count": target})
        finish_collection(
            output_dir, strategy, candidates, highwater_path,
            completed_keywords_by_shop=completed_keywords_by_shop,
            completed_pages_by_shop=completed_pages_by_shop,
        )
        return

    endpoints = {"A": args.shop_a, "B": args.shop_b}
    active_shops = resolve_active_shops(strategy)
    if not active_shops:
        emit({"status": "collection_error", "message": "strategy_has_no_active_shop"})
        raise SystemExit(2)
    shops = [(shop, endpoints[shop]) for shop in active_shops]
    if discovery_mode == "structured_browse":
        active_assignments = [(shop, endpoint, []) for shop, endpoint in shops]
    else:
        assignments = assign_keywords_to_shops(shops, keywords)
        active_assignments = [item for item in assignments if item[2]]
    shop_targets = allocate_shop_targets(target, len(active_assignments))
    platform_paused = False
    rate_limited_streak = 0
    batch_checkpoint = False
    for active_index, (shop, endpoint, assigned) in enumerate(active_assignments):
        try:
            if endpoint_is_explicitly_logged_out(endpoint):
                raise RuntimeError("fxg_merchant_not_logged_in")
            other_shop_count = sum(1 for item in candidates.values() if compact(item.get("shop")) not in {"", shop})
            dynamic_target = max(shop_targets[active_index], remaining_shop_target(target, other_shop_count))
            if discovery_mode == "structured_browse":
                batch_checkpoint = collect_shop_browse(
                    endpoint, shop, strategy, candidates, dynamic_target,
                    excluded, highwater_path, completed_pages_by_shop,
                )
            else:
                batch_checkpoint = collect_shop(
                    endpoint, shop, assigned, strategy, candidates, dynamic_target,
                    excluded, highwater_path, completed_keywords_by_shop,
                )
            if batch_checkpoint:
                break
        except Exception as exc:
            message = compact(exc)
            status = "rate_limited" if any(marker in message for marker in SAFETY_MARKERS) else "shop_error"
            # 单次 rate_limited 属频次抖动，跳过该店铺继续；连续 3 次才判定平台真限制。
            if status == "rate_limited":
                rate_limited_streak += 1
                if rate_limited_streak >= 3:
                    platform_paused = True
            else:
                rate_limited_streak = 0
            emit({"status": status, "shop": shop, "message": message[:500]})

    complete = len(candidates) >= target
    finish_collection(
        output_dir,
        strategy,
        candidates,
        highwater_path,
        emit_status="collection_finished" if complete and not platform_paused else "collection_checkpoint_saved",
        completed_keywords_by_shop=completed_keywords_by_shop,
        completed_pages_by_shop=completed_pages_by_shop,
    )
    if platform_paused:
        emit({
            "status": "platform_paused",
            "candidate_count": len(candidates),
            "target_count": target,
            "message": "平台提示请求频繁，已保存候选高水位并停止",
        })
        raise SystemExit(9)
    if batch_checkpoint and not complete:
        emit({
            "status": "collection_batch_paused",
            "candidate_count": len(candidates),
            "target_count": target,
            "message": "已达到本轮分页/关键词批次上限并保存断点",
        })
        return
    if not complete:
        emit({
            "status": "collection_incomplete",
            "candidate_count": len(candidates),
            "target_count": target,
            "message": "当前关键词候选不足，已保存高水位",
        })
        raise SystemExit(7)


if __name__ == "__main__":
    main()
