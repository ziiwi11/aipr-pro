from __future__ import annotations

import json
from typing import Any
from urllib.parse import quote
from urllib.request import urlopen

from embedded_cdp import is_embedded_endpoint, split_endpoint


def stale_automation_page_ids(targets: list[dict[str, Any]]) -> list[str]:
    pages = [target for target in targets if target.get("type") == "page"]
    buyin = [target for target in pages if "buyin.jinritemai.com" in str(target.get("url") or "")]
    keep = next(
        (target for target in buyin if "daren-square" in str(target.get("url") or "")),
        buyin[0] if buyin else None,
    )
    keep_id = str(keep.get("id") or "") if keep else ""
    stale: list[str] = []
    for target in pages:
        target_id = str(target.get("id") or "")
        url = str(target.get("url") or "")
        if not target_id or target_id == keep_id:
            continue
        if "buyin.jinritemai.com" in url or "douyin.com" in url:
            stale.append(target_id)
    return stale


def prune_automation_pages(endpoint: str) -> int:
    if is_embedded_endpoint(endpoint):
        return 0
    base, _shop = split_endpoint(endpoint)
    if not base.startswith(("http://", "https://")):
        return 0
    with urlopen(f"{base}/json/list", timeout=10) as response:
        targets = json.loads(response.read().decode("utf-8"))
    closed = 0
    for target_id in stale_automation_page_ids(targets):
        try:
            with urlopen(f"{base}/json/close/{quote(target_id, safe='')}", timeout=5):
                closed += 1
        except Exception:
            continue
    return closed
