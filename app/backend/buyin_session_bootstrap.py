from __future__ import annotations

import time
from typing import Any

from playwright.sync_api import BrowserContext, Page


BUYIN_SQUARE_URL = "https://buyin.jinritemai.com/dashboard/servicehall/daren-square"
FXG_HOME_URL = "https://fxg.jinritemai.com/ffa/mshop/homepage/index"


def compact(value: Any) -> str:
    return " ".join(str(value or "").split())


def is_buyin_square_url(url: str) -> bool:
    return "buyin.jinritemai.com/dashboard/servicehall/daren-square" in compact(url)


def is_buyin_domain_url(url: str) -> bool:
    return "buyin.jinritemai.com/" in compact(url)


def is_similar_mode_url(url: str) -> bool:
    return "dareSquareType=FindSimilarDaren" in compact(url)


def buyin_page_ready(page: Page, timeout: int = 1200) -> bool:
    if page.is_closed() or not is_buyin_square_url(page.url):
        return False
    try:
        inputs = page.locator("input:visible")
        for index in range(min(inputs.count(), 12)):
            placeholder = compact(inputs.nth(index).get_attribute("placeholder"))
            if "达人" in placeholder:
                return True
        body = page.locator("body").inner_text(timeout=timeout)
        return "达人广场" in body and "找达人" in body
    except Exception:
        return False


def find_ready_buyin_page(context: BrowserContext) -> Page | None:
    for page in reversed(context.pages):
        if buyin_page_ready(page):
            return page
    return None


def first_visible_exact_text(page: Page, label: str):
    locator = page.get_by_text(label, exact=True)
    for index in range(locator.count()):
        node = locator.nth(index)
        try:
            if node.is_visible(timeout=500):
                return node
        except Exception:
            continue
    return None


def wait_for_ready_buyin_page(context: BrowserContext, timeout_ms: int = 30000) -> Page | None:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        page = find_ready_buyin_page(context)
        if page:
            return page
        time.sleep(0.35)
    return None


def wait_for_page_ready(page: Page, timeout_ms: int = 30000) -> bool:
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        if buyin_page_ready(page):
            return True
        time.sleep(0.35)
    return False


def bootstrap_buyin_page(
    context: BrowserContext,
    similar_mode: bool = False,
    preferred_page: Page | None = None,
) -> Page:
    # Electron exposes all embedded views through one CDP context even though
    # their persistent partitions are isolated.  When a view is supplied, use
    # that exact page only so shop A can never borrow shop B's session.
    if preferred_page is not None:
        page = preferred_page
        if page.is_closed():
            raise RuntimeError("embedded_shop_page_closed")
        if not buyin_page_ready(page):
            page.goto(BUYIN_SQUARE_URL, wait_until="domcontentloaded", timeout=45000)
            if not wait_for_page_ready(page, timeout_ms=30000):
                raise RuntimeError("buyin_session_bootstrap_failed")
    else:
        page = find_ready_buyin_page(context)
    if preferred_page is None and not page:
        buyin_page = next(
            (item for item in reversed(context.pages) if is_buyin_domain_url(item.url) and not item.is_closed()),
            None,
        )
        if buyin_page:
            buyin_page.goto(BUYIN_SQUARE_URL, wait_until="domcontentloaded", timeout=45000)
            page = wait_for_ready_buyin_page(context, timeout_ms=30000)

    if preferred_page is None and not page:
        fxg_page = next(
            (item for item in context.pages if "fxg.jinritemai.com" in item.url and not item.is_closed()),
            None,
        ) or context.new_page()
        fxg_page.goto(FXG_HOME_URL, wait_until="domcontentloaded", timeout=45000)
        fxg_page.get_by_text("精选联盟", exact=True).first.wait_for(state="visible", timeout=30000)
        fxg_page.get_by_text("精选联盟", exact=True).first.hover(timeout=5000)
        fxg_page.wait_for_timeout(800)
        cooperation = first_visible_exact_text(fxg_page, "找合作")
        if not cooperation:
            raise RuntimeError("fxg_merchant_not_logged_in_or_alliance_entry_missing")
        cooperation.click(timeout=6000)
        page = wait_for_ready_buyin_page(context, timeout_ms=30000)
        if not page:
            raise RuntimeError("buyin_session_bootstrap_failed")

    if not similar_mode and is_similar_mode_url(page.url):
        page.goto(BUYIN_SQUARE_URL, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_url(lambda url: is_buyin_square_url(url) and not is_similar_mode_url(url), timeout=30000)
        page.wait_for_timeout(800)

    if similar_mode and not is_similar_mode_url(page.url):
        tab = first_visible_exact_text(page, "找相似达人")
        if not tab:
            raise RuntimeError("buyin_similar_entry_missing")
        tab.click(timeout=5000)
        page.locator("input[placeholder='请输入达人昵称、抖音号']").first.wait_for(
            state="visible", timeout=30000
        )
    return page
