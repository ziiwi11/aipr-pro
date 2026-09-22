from __future__ import annotations

import json
import time
from typing import Any
from urllib.parse import parse_qs, urlsplit, urlunsplit
from urllib.request import urlopen


def split_endpoint(endpoint: str) -> tuple[str, str]:
    raw = str(endpoint or "").strip()
    parsed = urlsplit(raw)
    query = parse_qs(parsed.query)
    shop = str((query.get("shop") or [""])[0]).upper()
    base = urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", "")).rstrip("/")
    return base, shop if shop in {"A", "B"} else ""


def is_embedded_endpoint(endpoint: str) -> bool:
    _base, shop = split_endpoint(endpoint)
    return bool(shop)


def resolve_cdp_endpoint(endpoint: str) -> str:
    base, _shop = split_endpoint(endpoint)
    if base.startswith(("ws://", "wss://")):
        return base
    with urlopen(base + "/json/version", timeout=5) as response:
        payload = json.loads(response.read().decode("utf-8"))
    ws_url = payload.get("webSocketDebuggerUrl")
    if not ws_url:
        raise RuntimeError(f"missing webSocketDebuggerUrl from {base}/json/version")
    return str(ws_url)


def find_shop_context(browser: Any, endpoint: str) -> tuple[Any, Any]:
    _base, shop = split_endpoint(endpoint)
    marker = f"AIPR_SHOP_{shop}" if shop else ""
    fallback = None
    for context in browser.contexts:
        for page in context.pages:
            try:
                if fallback is None and "jinritemai.com" in str(page.url or ""):
                    fallback = (context, page)
                if marker and page.evaluate("window.name") == marker:
                    return context, page
            except Exception:
                continue
    if fallback and not marker:
        return fallback
    if marker:
        raise RuntimeError(f"embedded_shop_view_not_found:{shop}")
    if browser.contexts:
        context = browser.contexts[0]
        return context, context.pages[0] if context.pages else context.new_page()
    context = browser.new_context()
    return context, context.new_page()


def connect_shop(browser_type: Any, endpoint: str, timeout: int | None = None) -> tuple[Any, Any, Any]:
    kwargs = {"timeout": timeout} if timeout is not None else {}
    browser = browser_type.connect_over_cdp(resolve_cdp_endpoint(endpoint), **kwargs)
    deadline = time.monotonic() + max(5.0, (timeout or 15000) / 1000)
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            context, page = find_shop_context(browser, endpoint)
            return browser, context, page
        except RuntimeError as error:
            last_error = error
            time.sleep(0.25)
    raise last_error or RuntimeError("embedded_shop_view_not_found")


def endpoint_page_list(endpoint: str) -> list[dict[str, Any]]:
    base, _shop = split_endpoint(endpoint)
    if not base.startswith(("http://", "https://")):
        return []
    with urlopen(base + "/json/list", timeout=5) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return payload if isinstance(payload, list) else []
