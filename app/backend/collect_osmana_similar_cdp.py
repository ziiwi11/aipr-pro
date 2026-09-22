from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from playwright.sync_api import Page, sync_playwright

from collect_osmana_candidates_cdp import candidate_from_search_item, precursor_eligible
from buyin_session_bootstrap import bootstrap_buyin_page
from console_io import configure_utf8_stdout
from embedded_cdp import connect_shop


configure_utf8_stdout()

SIMILAR_API_MARKER = "similar_kol/list"
SUGGEST_API_MARKER = "square/sug"
BUYIN_SIMILAR_URL = (
    "https://buyin.jinritemai.com/dashboard/servicehall/"
    "daren-square?dareSquareType=FindSimilarDaren"
)
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


def candidates_from_similar_payload(payload: dict[str, Any], seed_name: str, shop: str) -> list[dict[str, Any]]:
    if str(payload.get("code")) != "0" or not isinstance(payload.get("data"), dict):
        return []
    rows: list[dict[str, Any]] = []
    for item in payload["data"].get("author_list") or []:
        if not isinstance(item, dict) or not isinstance(item.get("author_data"), dict):
            continue
        if not isinstance(item.get("similarity_data"), dict):
            continue
        candidate = candidate_from_search_item(item["author_data"], f"similar:{seed_name}", shop)
        similarity = item.get("similarity_data") if isinstance(item.get("similarity_data"), dict) else {}
        avg = similarity.get("avg_score") if isinstance(similarity.get("avg_score"), dict) else {}
        candidate["similarity_score"] = int(avg.get("score") or 0)
        candidate["similarity_summary"] = compact(similarity.get("summary"))
        candidate["source_seed_nickname"] = seed_name
        candidate["source_type"] = "buyin_profile_similar"
        rows.append(candidate)
    return rows


def suggestions_from_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    if str(payload.get("code")) != "0" or not isinstance(payload.get("data"), dict):
        return []
    rows: list[dict[str, Any]] = []
    for item in payload["data"].get("sugList") or []:
        if not isinstance(item, dict) or not isinstance(item.get("author_info"), dict):
            continue
        rows.append(dict(item["author_info"]))
    return rows


def expected_seed_fans(seed: dict[str, Any]) -> int:
    direct = int(seed.get("fans") or seed.get("fans_num") or 0)
    if direct > 0:
        return direct
    nickname = re.escape(compact(seed.get("nickname")))
    profile = compact(seed.get("profile_text"))
    match = re.search(rf"{nickname}\s+([0-9.]+)(万)?粉丝", profile) if nickname else None
    if not match:
        return 0
    value = float(match.group(1))
    return int(value * 10000 if match.group(2) else value)


def choose_seed_suggestion(
    suggestions: list[dict[str, Any]],
    seed: dict[str, Any],
) -> dict[str, Any] | None:
    nickname = compact(seed.get("nickname")).casefold()
    matches = [row for row in suggestions if compact(row.get("nickname")).casefold() == nickname]
    if not matches:
        return None
    douyin_id = compact(seed.get("douyin_id"))
    stable_douyin_id = douyin_id if douyin_id and not douyin_id.startswith("v2_") else ""
    if stable_douyin_id:
        exact = [row for row in matches if compact(row.get("aweme_id")) == stable_douyin_id]
        if exact:
            return exact[0]
    expected_fans = expected_seed_fans(seed)
    if expected_fans:
        return min(matches, key=lambda row: abs(int(row.get("fans_num") or 0) - expected_fans))
    return matches[0]


def _legacy_seed_relevance_score(seed: dict[str, Any]) -> tuple[int, int, int]:
    evidence = seed.get("content_evidence") or []
    if not isinstance(evidence, list):
        evidence = [evidence]
    text = " ".join([
        compact(seed.get("category")),
        compact(seed.get("source_keyword")),
        compact(seed.get("profile_text")),
        *[compact(item) for item in evidence],
    ])
    target_hits = sum(
        1 for token in ("提臀", "塑形", "收腹", "内衣", "无痕", "打底裤", "瑜伽裤", "真人试穿")
        if token in text
    )
    return (
        target_hits,
        int(bool(seed.get("visual_persona_verified"))),
        int(seed.get("precontact_sales") or 0),
    )


def seed_content_relevance_hits(seed: dict[str, Any]) -> int:
    evidence = seed.get("content_evidence") or []
    if not isinstance(evidence, list):
        evidence = [evidence]
    text = " ".join(compact(item) for item in evidence)
    return sum(
        1 for token in (
            "提臀", "塑形", "塑身", "收腹", "内衣", "无痕",
            "美体衣", "打底裤", "瑜伽裤", "内裤", "胸贴", "真人试穿", "试穿", "穿搭",
        )
        if token in text
    )


def seed_relevance_score(seed: dict[str, Any]) -> tuple[int, int, int]:
    return (
        seed_content_relevance_hits(seed),
        int(bool(seed.get("visual_persona_verified"))),
        int(seed.get("precontact_sales") or 0),
    )


def reference_seeds_from_strategy(strategy: dict[str, Any]) -> list[dict[str, Any]]:
    text = compact(" ".join([
        compact(strategy.get("viralExamples")),
        compact(strategy.get("brief")),
    ]))
    pattern = re.compile(
        r"(?:对标账号|参考账号)[：:\s]*([^，,。；;\s]+).*?"
        r"(?:抖音号|抖音ID)[：:\s]*([A-Za-z0-9_.-]{5,})",
        re.IGNORECASE,
    )
    seeds: list[dict[str, Any]] = []
    for match in pattern.finditer(text):
        nickname = compact(match.group(1))
        douyin_id = compact(match.group(2)).rstrip(".。")
        seeds.append({
            "identity": f"reference:{douyin_id}",
            "nickname": nickname,
            "douyin_id": douyin_id,
            "shop": "",
            "reference_seed_only": True,
            "content_evidence_reviewed": True,
            "precontact_qualified": True,
            "precontact_sales": 10000,
        })
    return seeds


def seed_search_query(seed: dict[str, Any]) -> str:
    douyin_id = compact(seed.get("douyin_id"))
    if seed.get("reference_seed_only") and douyin_id and not douyin_id.startswith("v2_"):
        return douyin_id
    return compact(seed.get("nickname"))


def merge_seed_lists(seed_lists: list[list[dict[str, Any]]], limit: int) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for rows in seed_lists:
        for row in rows:
            key = compact(row.get("douyin_id")) or compact(row.get("identity")) or compact(row.get("nickname"))
            if not key or key in seen:
                continue
            seen.add(key)
            merged.append(row)
    return merged[: limit or len(merged)]


def select_similar_seeds(
    candidates: list[dict[str, Any]],
    shop: str,
    limit: int,
    require_body_measurements: bool = True,
    allow_reference_seeds: bool = False,
    allow_cross_shop: bool = False,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    for row in candidates:
        if (
            allow_reference_seeds
            and row.get("reference_seed_only")
            and compact(row.get("shop")) in ("", shop)
        ):
            selected.append(row)
            continue
        evaluation = row.get("osmana_evaluation") or {}
        height = evaluation.get("height_cm")
        weight = evaluation.get("weight_jin")
        generic_eligible = bool(
            not require_body_measurements
            and row.get("precontact_qualified")
            and row.get("content_evidence_reviewed")
            and seed_content_relevance_hits(row) > 0
            and int(row.get("precontact_sales") or 0) >= 10000
            and compact(row.get("buyin_profile_url"))
        )
        body_invalid = require_body_measurements and (
            height is None
            or weight is None
            or not 155 <= float(height) <= 170
            or not 80 <= float(weight) <= 110
        )
        strict_eligible = bool(
            not body_invalid
            and int(evaluation.get("underwear_product_sales_low") or 0) > 10000
            and row.get("content_evidence_reviewed")
            and row.get("visual_persona_verified")
        )
        if (
            (not allow_cross_shop and compact(row.get("shop")) not in ("", shop))
            or not (generic_eligible or strict_eligible)
        ):
            continue
        selected.append(row)
    selected.sort(key=seed_relevance_score, reverse=True)
    return selected[: limit or len(selected)]


def click_visible(page: Page, label: str) -> bool:
    locator = page.get_by_text(label, exact=False)
    for index in range(min(locator.count(), 12)):
        node = locator.nth(index)
        try:
            if node.is_visible(timeout=400):
                node.scroll_into_view_if_needed(timeout=1800)
                node.click(timeout=2200)
                return True
        except Exception:
            continue
    return False


def click_selected_suggestion(page: Page, selected: dict[str, Any]) -> bool:
    nickname = compact(selected.get("nickname"))
    locator = page.get_by_text(nickname, exact=True)
    for index in range(locator.count()):
        node = locator.nth(index)
        try:
            if not node.is_visible(timeout=400):
                continue
            node.scroll_into_view_if_needed(timeout=1800)
            node.click(timeout=2500)
            return True
        except Exception:
            continue
    return False


def assert_safe(page: Page) -> None:
    body = page.locator("body").inner_text(timeout=12000)
    marker = next((value for value in SAFETY_MARKERS if value in body), "")
    if marker:
        raise RuntimeError(f"platform_paused:{marker}")


def merge_candidate(pool: dict[str, dict[str, Any]], row: dict[str, Any]) -> None:
    identity = compact(row.get("identity"))
    if not identity:
        return
    if identity not in pool:
        pool[identity] = row
        return
    current = pool[identity]
    current["source_keywords"] = list(dict.fromkeys([*(current.get("source_keywords") or []), *(row.get("source_keywords") or [])]))
    if int(row.get("similarity_score") or 0) > int(current.get("similarity_score") or 0):
        current["similarity_score"] = row["similarity_score"]
        current["similarity_summary"] = row.get("similarity_summary", "")
        current["source_seed_nickname"] = row.get("source_seed_nickname", "")


def save(output: Path, source: Path, shop: str, pool: dict[str, dict[str, Any]], completed_seeds: int) -> None:
    output.write_text(json.dumps({
        "status": "ready",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "source": str(source),
        "shop": shop,
        "completed_seed_count": completed_seeds,
        "candidate_count": len(pool),
        "candidates": list(pool.values()),
    }, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--shop", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--strategy")
    parser.add_argument("--allow-reference-seeds", action="store_true")
    parser.add_argument("--cross-shop-seeds", action="store_true")
    parser.add_argument("--seed-limit", type=int, default=0)
    parser.add_argument("--change-rounds", type=int, default=3)
    parser.add_argument("--target-count", type=int, default=0)
    args = parser.parse_args()

    source = Path(args.input).resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    strategy = (
        json.loads(Path(args.strategy).resolve().read_text(encoding="utf-8"))
        if args.strategy
        else {}
    )
    verified_seeds = select_similar_seeds(
        [row for row in payload.get("candidates") or [] if isinstance(row, dict)],
        args.shop,
        0,
        require_body_measurements=bool(strategy.get("requireBodyMeasurements", False)),
        allow_reference_seeds=args.allow_reference_seeds,
        allow_cross_shop=args.cross_shop_seeds,
    )
    seeds = merge_seed_lists(
        [reference_seeds_from_strategy(strategy), verified_seeds],
        args.seed_limit,
    )
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    output = out_dir / f"osmana_similar_pool_shop_{args.shop}.json"
    pool: dict[str, dict[str, Any]] = {}

    emit({"status": "osmana_similar_started", "shop": args.shop, "seed_count": len(seeds)})
    with sync_playwright() as playwright:
        browser, context, _embedded_page = connect_shop(playwright.chromium, args.endpoint)
        page = bootstrap_buyin_page(context, similar_mode=True, preferred_page=_embedded_page)
        page.set_default_timeout(15000)
        try:
            page.locator("input[placeholder='请输入达人昵称、抖音号']").first.wait_for(
                state="visible", timeout=30000
            )
            assert_safe(page)
            for seed_index, seed in enumerate(seeds, start=1):
                if args.target_count > 0 and len(pool) >= args.target_count:
                    break
                responses: list[dict[str, Any]] = []
                suggestion_payloads: list[dict[str, Any]] = []

                def on_response(response) -> None:
                    try:
                        if SIMILAR_API_MARKER in response.url:
                            responses.append(response.json())
                        elif SUGGEST_API_MARKER in response.url:
                            suggestion_payloads.append(response.json())
                    except Exception:
                        pass

                page.on("response", on_response)
                try:
                    input_node = page.locator("input[placeholder='请输入达人昵称、抖音号']").first
                    input_node.wait_for(state="visible", timeout=20000)
                    input_node.fill(seed_search_query(seed), force=True)
                    page.wait_for_timeout(1800)
                    assert_safe(page)
                    suggestions: list[dict[str, Any]] = []
                    for payload_item in suggestion_payloads:
                        suggestions.extend(suggestions_from_payload(payload_item))
                    selected = choose_seed_suggestion(suggestions, seed)
                    if not selected or not click_selected_suggestion(page, selected):
                        emit({
                            "status": "seed_not_resolved",
                            "shop": args.shop,
                            "seed": seed.get("nickname", ""),
                            "suggestion_count": len(suggestions),
                        })
                        continue
                    page.wait_for_timeout(3500)
                    assert_safe(page)
                    for _ in range(max(4, min(args.change_rounds * 3, 18))):
                        page.mouse.wheel(0, 1400)
                        page.wait_for_timeout(850)
                        assert_safe(page)

                    before_size = len(pool)
                    for response_payload in responses:
                        for candidate in candidates_from_similar_payload(response_payload, compact(seed.get("nickname")), args.shop):
                            if precursor_eligible(candidate):
                                merge_candidate(pool, candidate)
                    pool.pop(compact(seed.get("identity")), None)
                    save(output, source, args.shop, pool, seed_index)
                    emit({
                        "status": "osmana_similar_progress",
                        "shop": args.shop,
                        "seed": seed.get("nickname", ""),
                        "seed_index": seed_index,
                        "seed_total": len(seeds),
                        "resolved_douyin_id": selected.get("aweme_id", ""),
                        "new_candidates": len(pool) - before_size,
                        "pool_count": len(pool),
                    })
                except Exception as exc:
                    emit({"status": "seed_error", "shop": args.shop, "seed": seed.get("nickname", ""), "message": compact(exc)[:400]})
                finally:
                    try:
                        page.remove_listener("response", on_response)
                    except Exception:
                        pass
        finally:
            # Keep the user-owned Buyin tab alive for the next software round.
            pass

    save(output, source, args.shop, pool, len(seeds))
    emit({"status": "osmana_similar_finished", "shop": args.shop, "output": str(output), "candidate_count": len(pool)})


if __name__ == "__main__":
    main()
