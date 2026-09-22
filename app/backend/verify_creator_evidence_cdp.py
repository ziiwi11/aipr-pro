from __future__ import annotations

import argparse
import json
import re
import shutil
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from console_io import configure_utf8_stdout
from atomic_json_io import atomic_write_json
from contact_pipeline_contract import build_profile_url, creator_identity, merge_contact_candidates, profile_content_ready
from creator_delivery_contract import content_blocked, extract_sales_lower, mark_precontact_qualification
from cdp_session_hygiene import prune_automation_pages
from embedded_cdp import connect_shop
from source_pool_contract import source_only_pool_ready as evidence_source_pool_ready


configure_utf8_stdout()


def evidence_active_shops(payload: dict[str, Any]) -> list[str]:
    strategy = payload.get("strategy") if isinstance(payload.get("strategy"), dict) else {}
    requested = [compact(value).upper() for value in strategy.get("activeShops") or ["A", "B"]]
    return list(dict.fromkeys(shop for shop in requested if shop in {"A", "B"}))


def evidence_highwater_filename(payload: dict[str, Any]) -> str:
    strategy = payload.get("strategy") if isinstance(payload.get("strategy"), dict) else {}
    if compact(strategy.get("strategyPurpose")) == "replenishment-source-only":
        return "aipr_replenishment_evidence_highwater.json"
    return "aipr_evidence_highwater.json"


def evidence_output_prefix(payload: dict[str, Any]) -> str:
    strategy = payload.get("strategy") if isinstance(payload.get("strategy"), dict) else {}
    if compact(strategy.get("strategyPurpose")) == "replenishment-source-only":
        return "aipr_verified_creators_replenishment"
    return "aipr_verified_creators"


EVIDENCE_CONTRACT_VERSION = 4

SAFETY_MARKERS = ("安全验证", "验证码", "访问过于频繁", "请求过于频繁", "稍后再试")
DOUYIN_LABELS = ("达人抖音主页", "抖音主页", "查看抖音主页", "达人主页")


def emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False), flush=True)


def compact(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def profile_data_loaded(body_text: Any) -> bool:
    text = compact(body_text)
    if "达人昵称 粉丝 履约分" in text:
        return False
    return bool("达人简介" in text and re.search(r"\d+(?:\.\d+)?\s*万?粉丝", text))


def is_beauty_profile_candidate(candidate: dict[str, Any], keywords: list[str]) -> bool:
    category = compact(candidate.get("category") or candidate.get("main_category"))
    return bool(
        any(marker in " ".join(keywords) for marker in ("唇", "口红", "润唇", "护肤", "美妆"))
        or any(marker in category for marker in ("美妆", "个护家清"))
    )


def required_evidence_free_bytes(candidate_count: int) -> int:
    return 256 * 1024 * 1024 + max(0, int(candidate_count or 0)) * 1024 * 1024


def ensure_evidence_free_space(
    output_dir: Path,
    candidate_count: int,
    *,
    free_bytes: int | None = None,
) -> int:
    available = shutil.disk_usage(output_dir).free if free_bytes is None else int(free_bytes)
    required = required_evidence_free_bytes(candidate_count)
    if available < required:
        raise OSError(
            f"insufficient disk space for evidence review: "
            f"need {required // (1024 * 1024)} MB, free {available // (1024 * 1024)} MB"
        )
    return available


def should_capture_evidence_screenshots(candidate: dict[str, Any]) -> bool:
    return candidate.get("content_evidence_reviewed") is True


def apply_structured_beauty_evidence(candidate: dict[str, Any], keywords: list[str]) -> dict[str, Any]:
    current = dict(candidate)
    beauty_task = is_beauty_profile_candidate(current, keywords)
    category = compact(current.get("category") or current.get("main_category"))
    qualified = bool(
        beauty_task
        and int(current.get("gender") or 0) == 2
        and any(marker in category for marker in ("美妆", "个护家清"))
        and current.get("contact_visible") is True
    )
    if not qualified:
        return current
    current.update({
        "content_evidence_reviewed": False,
        "content_evidence": [
            "平台性别：女性",
            f"平台主营类目：{category}",
            "平台联系方式：可查看",
        ],
        "content_evidence_source": "buyin_search_response",
        "evidence_status": "metadata_verified_pending_content",
        "evidence_contract_version": EVIDENCE_CONTRACT_VERSION,
        "evidence_reviewed_at": datetime.now().isoformat(timespec="seconds"),
        "evidence_gate": {
            "source": "buyin_search_response",
            "beauty_vertical_verified": True,
            "gender_verified": True,
            "category_verified": True,
            "contact_visibility_verified": True,
        },
    })
    current.pop("evidence_error", None)
    return current


def resolve_cdp_endpoint(endpoint: str) -> str:
    if endpoint.startswith(("ws://", "wss://")):
        return endpoint
    with urlopen(endpoint.rstrip("/") + "/json/version", timeout=5) as response:
        return str(json.loads(response.read().decode("utf-8"))["webSocketDebuggerUrl"])


def evidence_profile_session_ready(final_url: str, body_text: str) -> bool:
    return "buyin.jinritemai.com" in compact(final_url) and profile_content_ready(body_text)


def probe_evidence_shop(endpoint: str, profile_url: str) -> bool:
    try:
        with sync_playwright() as playwright:
            browser, context, _embedded_page = connect_shop(playwright.chromium, endpoint, timeout=10000)
            page = _embedded_page
            page.goto(profile_url, wait_until="domcontentloaded", timeout=30000)
            for _attempt in range(15):
                body = page.locator("body").inner_text(timeout=3000)
                if evidence_profile_session_ready(page.url, body):
                    return True
                if "douyinec.com" in compact(page.url):
                    return False
                page.wait_for_timeout(1000)
            return False
    except Exception:
        return False


def safe_name(value: Any) -> str:
    return re.sub(r"[^0-9A-Za-z\u4e00-\u9fff_-]+", "_", compact(value))[:48] or "creator"


def _legacy_meaningful_lines(text: str, keywords: list[str]) -> list[str]:
    lines = [compact(line) for line in re.split(r"[\r\n]+", text) if len(compact(line)) >= 6]
    markers = [*keywords, "视频", "作品", "播放", "点赞", "口播", "测评", "好物", "护肤", "美妆", "洗护"]
    selected = [line[:260] for line in lines if any(marker and marker in line for marker in markers)]
    return list(dict.fromkeys(selected))[:12]


def meaningful_lines(text: str, keywords: list[str]) -> list[str]:
    lines = [compact(line) for line in re.split(r"[\r\n]+", text) if len(compact(line)) >= 6]
    markers = list(dict.fromkeys([
        *keywords,
        "唇", "口红", "唇蜜", "唇膜", "唇油", "精华", "面膜",
        "护肤", "美妆", "彩妆", "妆容", "试色", "个护",
        "提臀", "塑形", "塑身", "收腹", "内衣", "无痕", "美体衣",
        "打底裤", "瑜伽裤", "内裤", "胸贴", "真人试穿", "试穿", "穿搭",
        # 通用内容词：类目搜索（structured_browse）时 keywords 为空，
        # 若只靠垂类词，个护家清/食品饮料等类目达人的文案无法命中，
        # 会导致 actual_profile_evidence 为空 → content_unverified。
        "测评", "好物", "推荐", "分享", "种草", "开箱", "使用", "效果",
        "家清", "日用", "清洁", "洗护", "身体", "护理", "保养",
        "美食", "零食", "生鲜", "母婴", "家居", "生活", "日常",
    ]))
    boilerplate = (
        "搜索 Ta 的作品", "搜索Ta的作品", "登录后免费畅享高清视频",
        "打开抖音", "安全验证", "关注 私信 作品", "关注私信作品",
    )
    cleaned_lines: list[str] = []
    for line in lines:
        cleaned = line
        for marker in boilerplate:
            cleaned = cleaned.replace(marker, " ")
        cleaned = compact(cleaned)
        if len(cleaned) >= 6:
            cleaned_lines.append(cleaned)
    selected = [
        line[:260]
        for line in cleaned_lines
        if any(marker and marker in line for marker in markers)
    ]
    return list(dict.fromkeys(selected))[:12]


def invalidate_stale_content_evidence(
    candidates: list[dict[str, Any]],
    keywords: list[str],
) -> list[dict[str, Any]]:
    refreshed: list[dict[str, Any]] = []
    for candidate in candidates:
        current = dict(candidate)
        if (
            current.get("evidence_status") == "content_unverified"
            and not compact(current.get("douyin_homepage"))
            and not current.get("content_evidence")
        ):
            current["evidence_status"] = "pending"
            current["content_evidence_reviewed"] = False
            refreshed.append(current)
            continue
        # 已有 buyin 侧内容证据、但因旧 markers 判定为未通过的记录，
        # 重置为 pending 以便用新 markers 重新评估。
        # （markers 曾只含垂类词，导致个护家清不在首位的达人被误判。）
        if (
            current.get("evidence_status") == "content_unverified"
            and not current.get("content_evidence_reviewed")
            and current.get("content_evidence")
            and current.get("profile_verified") is True
        ):
            current["evidence_status"] = "pending"
            current["content_evidence_reviewed"] = False
            refreshed.append(current)
            continue
        if (
            current.get("evidence_status") in {"verified", "content_unverified"}
            and int(current.get("evidence_contract_version") or 0) < EVIDENCE_CONTRACT_VERSION
        ):
            current["content_evidence_reviewed"] = False
            current["evidence_status"] = "pending"
            current["content_evidence"] = []
            refreshed.append(current)
            continue
        if current.get("content_evidence_reviewed") is True:
            source_text = compact(current.get("douyin_content_text")) or "\n".join(
                compact(item) for item in current.get("content_evidence") or []
            )
            evidence = meaningful_lines(source_text, keywords)
            if evidence:
                current["content_evidence"] = evidence
            else:
                current["content_evidence_reviewed"] = False
                current["evidence_status"] = "pending"
                current["content_evidence"] = []
        refreshed.append(current)
    return refreshed


def find_douyin_url(page) -> str:
    source = page.content()
    match = re.search(r"https?://(?:www\.)?douyin\.com/[^\s\"'<>\\]+", source)
    return match.group(0).rstrip("),.;") if match else ""


def open_douyin_homepage(context, profile_page) -> tuple[Any | None, str]:
    before = set(context.pages)
    for label in DOUYIN_LABELS:
        locator = profile_page.get_by_text(label, exact=True).first
        try:
            if not locator.count() or not locator.is_visible(timeout=600):
                continue
            locator.click(timeout=2500)
            profile_page.wait_for_timeout(3500)
            opened = next((item for item in context.pages if item not in before and not item.is_closed()), None)
            if opened:
                return opened, f"text:{label}"
            if "douyin.com" in profile_page.url:
                return profile_page, f"same-page:{label}"
        except Exception:
            continue
    return None, ""


def open_owned_douyin_page(context, profile_page) -> tuple[Any | None, str, str]:
    douyin_url = find_douyin_url(profile_page)
    if douyin_url:
        opened = context.new_page()
        opened.goto(douyin_url, wait_until="domcontentloaded", timeout=30000)
        return opened, douyin_url, "direct-profile-link"
    for label in DOUYIN_LABELS:
        locator = profile_page.get_by_text(label, exact=False)
        for index in range(min(locator.count(), 12)):
            node = locator.nth(index)
            try:
                if not node.is_visible(timeout=500):
                    continue
                with profile_page.expect_popup(timeout=6000) as popup_info:
                    node.click(timeout=5000)
                opened = popup_info.value
                return opened, compact(opened.url), f"popup:text:{label}"
            except PlaywrightTimeoutError:
                current_url = compact(profile_page.url)
                if "douyin.com" in current_url:
                    return profile_page, current_url, f"same-page:text:{label}"
            except Exception:
                continue
    return None, "", ""


def verify_one(context, candidate: dict[str, Any], evidence_dir: Path, keywords: list[str], page=None) -> dict[str, Any]:
    current = dict(candidate)
    current.pop("evidence_error", None)
    identity = compact(current.get("buyin_uid"))
    author_level = int(current.get("author_level") or re.sub(r"\D", "", compact(current.get("talent_level"))) or 0)
    profile_url = build_profile_url(identity, author_level) if identity else compact(
        current.get("buyin_profile_url") or current.get("精选联盟主页")
    )
    if profile_url:
        current["buyin_profile_url"] = profile_url
        current["精选联盟主页"] = profile_url
    current["evidence_reviewed_at"] = datetime.now().isoformat(timespec="seconds")
    if not profile_url:
        current["evidence_status"] = "missing_buyin_profile"
        return current

    owns_page = page is None
    page = page or context.new_page()
    page.set_default_timeout(15000)
    opened = None
    try:
        page.goto(profile_url, wait_until="domcontentloaded", timeout=45000)
        # 注意：原先的等待条件包含 `!text.includes('达人昵称 粉丝 履约分')`，
        # 但该文本是页面表头（非骨架屏），始终存在，导致该条件必然超时 18s，
        # 随后被 except 静默吞掉，页面在数据区渲染前就被抓取。
        # 现改为等待真正标志数据就绪的「达人简介」+「粉丝数」。
        try:
            page.wait_for_function(
                r"""() => {
                  const text = (document.body?.innerText || '').replace(/\s+/g, ' ').trim();
                  return text.includes('达人简介')
                    && /\d+(?:\.\d+)?\s*万?粉丝/.test(text);
                }""",
                timeout=18000,
            )
        except PlaywrightTimeoutError:
            pass
        # 二次等待：等「内容数据」区块真正渲染完成。
        # 注意：不能只用 /(\d+)\s*发布内容总数/ 作为条件 —— 骨架屏阶段
        # 该文本就已存在且数字为 0，条件会立即满足，导致读到未加载的数据。
        # 改为等待「内容数据」与「历史内容」同时出现（数据区已挂载）。
        try:
            page.wait_for_function(
                r"""() => {
                  const text = (document.body?.innerText || '').replace(/\s+/g, ' ').trim();
                  return text.includes('内容数据') && text.includes('历史内容');
                }""",
                timeout=15000,
            )
        except PlaywrightTimeoutError:
            pass
        # 三次等待：数据区出现后仍可能有短暂的空值，固定再等一段，
        # 让「发布内容总数」等字段完成填充。
        try:
            page.wait_for_timeout(2500)
        except Exception:
            pass
        body = page.locator("body").inner_text(timeout=8000)
        compact_body = compact(body)
        profile_content_match = re.search(r"(\d+)\s*发布内容总数", compact_body)
        profile_content_count = int(profile_content_match.group(1)) if profile_content_match else 0
        # 内容数为 0 时重载一次再读：平台页面偶发在数据区挂载前返回 0，
        # 直接采信会把「有内容」的达人误判为无内容（历史观测波动 170→71）。
        if profile_content_count == 0 and "内容数据" in compact_body:
            try:
                page.reload(wait_until="domcontentloaded", timeout=40000)
                page.wait_for_timeout(4000)
                body = page.locator("body").inner_text(timeout=8000)
                compact_body = compact(body)
                retry_match = re.search(r"(\d+)\s*发布内容总数", compact_body)
                if retry_match and int(retry_match.group(1)) > 0:
                    profile_content_count = int(retry_match.group(1))
                    current["profile_content_retry_used"] = True
            except Exception:
                pass
        current["profile_text"] = compact_body[:16000]
        current["profile_verified"] = profile_content_ready(compact_body) and not any(marker in compact_body for marker in SAFETY_MARKERS)
        current["monthly_sales_value"] = extract_sales_lower(compact_body)
        profile_evidence = meaningful_lines(body, keywords)
        actual_profile_evidence = list(profile_evidence)
        category = compact(current.get("category") or current.get("main_category"))
        beauty_task = is_beauty_profile_candidate(current, keywords)
        beauty_vertical_verified = bool(
            beauty_task
            and int(current.get("gender") or 0) == 2
            and any(marker in category for marker in ("美妆", "个护家清"))
            and current.get("contact_visible") is True
        )
        if beauty_vertical_verified:
            profile_evidence = [
                f"平台性别：女性",
                f"平台主营类目：{category}",
                "平台联系方式：可查看",
                *profile_evidence,
            ]
        profile_content_ready_for_review = bool(
            current["profile_verified"]
            and profile_content_count > 0
            and actual_profile_evidence
            and "历史内容" in compact_body
        )

        screenshots: list[str] = []

        opened, douyin_url, method = (None, "", "") if beauty_task else open_owned_douyin_page(context, page)
        if opened:
            try:
                opened.wait_for_load_state("domcontentloaded", timeout=15000)
            except Exception:
                pass
            opened.wait_for_timeout(5000)
            douyin_url = opened.url or douyin_url
            douyin_text = opened.locator("body").inner_text(timeout=10000)
        else:
            douyin_text = ""

        douyin_compact = compact(douyin_text)
        current["douyin_homepage"] = douyin_url if "douyin.com" in douyin_url else ""
        current["douyin_homepage_open_method"] = method
        current["douyin_content_text"] = douyin_compact[:16000]
        current["content_evidence"] = meaningful_lines(douyin_text, keywords) if douyin_text else profile_evidence
        blocked = content_blocked(douyin_compact, current["content_evidence"], SAFETY_MARKERS)
        current["evidence_gate"] = {
            "has_homepage": bool(current["douyin_homepage"]),
            "has_buyin_profile": bool(current["profile_verified"]),
            "buyin_content_count": profile_content_count,
            "beauty_vertical_verified": beauty_vertical_verified,
            "source": "douyin_homepage" if douyin_text else "buyin_profile",
            "text_length": len(douyin_compact),
            "evidence_count": len(current["content_evidence"]),
            "blocked": bool(blocked),
        }
        current["content_evidence_reviewed"] = bool(
            profile_content_ready_for_review
            or (current["douyin_homepage"] and len(douyin_compact) >= 80 and current["content_evidence"] and not blocked)
        )
        current["content_evidence_source"] = "buyin_profile" if profile_content_ready_for_review else method
        current["evidence_status"] = "verified" if current["content_evidence_reviewed"] else "douyin_blocked" if blocked else "content_unverified"
        current["evidence_contract_version"] = EVIDENCE_CONTRACT_VERSION
        if should_capture_evidence_screenshots(current):
            try:
                evidence_dir.mkdir(parents=True, exist_ok=True)
                stem = safe_name(current.get("nickname") or current.get("identity"))
                profile_shot = evidence_dir / f"{stem}_buyin.jpg"
                page.screenshot(path=str(profile_shot), type="jpeg", quality=68, full_page=False)
                screenshots.append(str(profile_shot))
                if opened:
                    douyin_shot = evidence_dir / f"{stem}_douyin.jpg"
                    opened.screenshot(path=str(douyin_shot), type="jpeg", quality=68, full_page=False)
                    screenshots.append(str(douyin_shot))
            except Exception as exc:
                # Embedded A/B views are intentionally hidden while the desktop UI
                # is foregrounded and can report a zero-sized viewport. Evidence is
                # already verified from the authorized profile response, so a
                # best-effort screenshot must never downgrade a valid creator.
                current["evidence_screenshot_error"] = compact(exc)[:300]
        current["evidence_screenshots"] = screenshots
    except Exception as exc:
        current["evidence_status"] = "error"
        current["evidence_error"] = compact(exc)[:500]
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


def pending_evidence_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    completed = {"verified", "content_unverified", "missing_buyin_profile"}
    return [
        row for row in candidates
        if not row.get("content_evidence_reviewed") and compact(row.get("evidence_status")) not in completed
    ]


def merge_evidence_candidate_updates(
    base: list[dict[str, Any]],
    updates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged = merge_contact_candidates(base, updates)
    authoritative = {
        creator_identity(row): row
        for row in updates
        if creator_identity(row)
    }
    fields = {
        "content_evidence_reviewed", "content_evidence", "evidence_status",
        "evidence_contract_version", "evidence_error", "evidence_gate",
        "evidence_screenshot_error",
        "douyin_content_text", "douyin_homepage", "douyin_homepage_open_method",
        "evidence_screenshots", "evidence_reviewed_at",
    }
    for row in merged:
        update = authoritative.get(creator_identity(row))
        if not update:
            continue
        for field in fields:
            if field in update:
                row[field] = update[field]
    return merged


def merge_evidence_highwater(base: list[dict[str, Any]], prior: list[dict[str, Any]]) -> list[dict[str, Any]]:
    identities = {compact(row.get("identity")) for row in base if compact(row.get("identity"))}
    relevant_prior = [row for row in prior if compact(row.get("identity")) in identities]
    return merge_evidence_candidate_updates(base, relevant_prior)


def partition_evidence_by_shop(
    candidates: list[dict[str, Any]],
    active_shops: list[str] | None = None,
) -> dict[str, list[dict[str, Any]]]:
    grouped = {"A": [], "B": []}
    shops = [shop for shop in (active_shops or ["A", "B"]) if shop in grouped]
    if not shops:
        return grouped
    fallback_index = 0
    for row in candidates:
        source_shop = compact(row.get("shop")).upper()
        if source_shop in shops:
            grouped[source_shop].append(row)
            continue
        grouped[shops[fallback_index % len(shops)]].append(row)
        fallback_index += 1
    return grouped


def partition_evidence_lanes(
    candidates: list[dict[str, Any]],
    lanes_per_shop: int = 2,
    active_shops: list[str] | None = None,
) -> list[tuple[str, list[dict[str, Any]]]]:
    grouped = partition_evidence_by_shop(candidates, active_shops=active_shops)
    lane_count = max(1, int(lanes_per_shop or 1))
    return [
        (shop, rows[index::lane_count])
        for shop, rows in grouped.items()
        for index in range(lane_count)
        if rows[index::lane_count]
    ]


def connect_over_cdp_serialized(browser_type: Any, endpoint: str, lock: threading.Lock) -> Any:
    with lock:
        return browser_type.connect_over_cdp(endpoint)


def connect_shop_serialized(browser_type: Any, endpoint: str, lock: threading.Lock) -> tuple[Any, Any, Any]:
    with lock:
        return connect_shop(browser_type, endpoint)


def save_highwater(path: Path, source_payload: dict[str, Any], candidates: list[dict[str, Any]]) -> None:
    source_ids = {
        creator_identity(row)
        for row in source_payload.get("candidates") or []
        if isinstance(row, dict) and creator_identity(row)
    }
    stable_candidates = [
        row for row in candidates
        if not source_ids or creator_identity(row) in source_ids
    ]
    if path.exists():
        try:
            previous = json.loads(path.read_text(encoding="utf-8"))
            previous_candidates = [
                row for row in previous.get("candidates") or []
                if isinstance(row, dict) and (not source_ids or creator_identity(row) in source_ids)
            ]
            stable_candidates = merge_contact_candidates(previous_candidates, stable_candidates)
            reviewed_updates = [
                row for row in candidates
                if row.get("evidence_reviewed_at")
                or compact(row.get("evidence_status")) in {"verified", "content_unverified", "missing_buyin_profile"}
            ]
            stable_candidates = merge_evidence_candidate_updates(stable_candidates, reviewed_updates)
        except (OSError, json.JSONDecodeError, TypeError, AttributeError):
            pass
    atomic_write_json(path, {
        **source_payload,
        "status": "ready",
        "evidence_reviewed_at": datetime.now().isoformat(timespec="seconds"),
        "candidate_count": len(stable_candidates),
        "evidence_verified_count": sum(1 for row in stable_candidates if row.get("content_evidence_reviewed")),
        "candidates": stable_candidates,
    })


def wait_for_lane_futures(futures: list[Any]) -> list[Exception]:
    failures: list[Exception] = []
    for future in futures:
        try:
            future.result()
        except Exception as exc:
            failures.append(exc)
    return failures


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--shop-a", default="http://127.0.0.1:9222?shop=A")
    parser.add_argument("--shop-b", default="http://127.0.0.1:9222?shop=B")
    parser.add_argument("--lanes-per-shop", type=int, default=4)
    parser.add_argument("--keywords-json", default="[]")
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()

    source = Path(args.input).resolve()
    payload = json.loads(source.read_text(encoding="utf-8"))
    source_ready, source_reason = evidence_source_pool_ready(payload)
    if not source_ready:
        emit({
            "status": "evidence_failed",
            "stage": "source_pool",
            "message": "source_pool_incomplete",
            "reason": source_reason,
            "candidate_count": len(payload.get("candidates") or []),
            "target_count": payload.get("target_count"),
        })
        raise SystemExit(7)
    base = [item for item in payload.get("candidates") or [] if isinstance(item, dict)]
    keywords = [compact(item) for item in json.loads(args.keywords_json) if compact(item)]
    output_dir = Path(args.out_dir).resolve()
    evidence_dir = output_dir / "evidence"
    highwater = output_dir / evidence_highwater_filename(payload)
    merged = list(base)
    if highwater.exists():
        try:
            prior = json.loads(highwater.read_text(encoding="utf-8"))
            merged = merge_evidence_highwater(merged, prior.get("candidates") or [])
        except (OSError, json.JSONDecodeError):
            pass
    merged = invalidate_stale_content_evidence(merged, keywords)
    merged = [apply_structured_beauty_evidence(row, keywords) for row in merged]
    evidence_target = max(1, int((payload.get("strategy") or {}).get("targetCount") or 500))
    target_reached = threading.Event()
    if sum(1 for row in merged if row.get("content_evidence_reviewed")) >= evidence_target:
        target_reached.set()
    pending = pending_evidence_candidates(merged)
    selected = [] if target_reached.is_set() else pending[: args.limit or len(pending)]
    if target_reached.is_set():
        emit({
            "status": "evidence_target_reached",
            "target_count": evidence_target,
            "evidence_verified_count": sum(1 for row in merged if row.get("content_evidence_reviewed")),
        })
    try:
        ensure_evidence_free_space(output_dir, len(selected))
    except OSError as exc:
        emit({"status": "evidence_failed", "stage": "disk_space", "message": str(exc)})
        raise SystemExit(7) from exc
    processed = 0
    state_lock = threading.Lock()

    endpoint_map = {"A": args.shop_a, "B": args.shop_b}
    requested_shops = evidence_active_shops(payload)
    if not requested_shops:
        emit({"status": "evidence_failed", "stage": "shop_preflight", "message": "strategy_has_no_active_shop"})
        raise SystemExit(2)
    endpoints = {shop: endpoint_map[shop] for shop in requested_shops}
    for shop, endpoint in endpoints.items():
        try:
            emit({"status": "cdp_session_cleaned", "shop": shop, "closed_pages": prune_automation_pages(endpoint)})
        except Exception as exc:
            emit({"status": "cdp_session_cleanup_warning", "shop": shop, "message": compact(exc)[:300]})
    sample_profile_url = next((
        compact(row.get("buyin_profile_url") or row.get("精选联盟主页"))
        for row in selected
        if compact(row.get("buyin_profile_url") or row.get("精选联盟主页"))
    ), "")
    if sample_profile_url:
        with ThreadPoolExecutor(max_workers=2) as executor:
            checks = {
                shop: executor.submit(probe_evidence_shop, endpoint, sample_profile_url)
                for shop, endpoint in endpoints.items()
            }
            active_shops = [shop for shop, future in checks.items() if future.result()]
    else:
        active_shops = requested_shops
    emit({"status": "evidence_shop_preflight", "active_shops": active_shops})
    if selected and not active_shops:
        emit({"status": "evidence_failed", "stage": "shop_preflight", "message": "no shop can open a creator profile"})
        raise SystemExit(8)
    emit({"status": "evidence_started", "candidate_count": len(selected)})
    connection_locks = {shop: threading.Lock() for shop in requested_shops}

    def process_lane(shop: str, shop_rows: list[dict[str, Any]]) -> None:
        nonlocal merged, processed
        with sync_playwright() as playwright:
            browser, context, _embedded_page = connect_shop_serialized(
                playwright.chromium,
                endpoints[shop],
                connection_locks[shop],
            )
            for row in shop_rows:
                if target_reached.is_set():
                    break
                verified = verify_one(context, row, evidence_dir, keywords, page=_embedded_page)
                verified["evidence_shop"] = shop
                with state_lock:
                    merged = merge_evidence_candidate_updates(merged, [verified])
                    save_highwater(highwater, payload, merged)
                    processed += 1
                    reviewed_count = sum(1 for item in merged if item.get("evidence_reviewed_at"))
                    verified_count = sum(1 for item in merged if item.get("content_evidence_reviewed"))
                    if verified_count >= evidence_target:
                        target_reached.set()
                    emit({
                        "status": "evidence_progress",
                        "creator": verified.get("nickname", ""),
                        "shop": shop,
                        "processed": processed,
                        "total": len(selected),
                        "evidence_status": verified.get("evidence_status"),
                        "evidence_highwater_count": reviewed_count,
                        "evidence_verified_count": verified_count,
                    })

    selected_ids = {creator_identity(row) for row in selected if creator_identity(row)}
    work = list(selected)
    for pass_index in range(2):
        # Each embedded shop is one persistent WebContents page.  Serializing a
        # shop lane prevents concurrent collectors from navigating that page.
        lane_width = 1 if any("?shop=" in endpoint for endpoint in endpoints.values()) else (
            args.lanes_per_shop if pass_index == 0 else 1
        )
        lanes = partition_evidence_lanes(work, lanes_per_shop=lane_width, active_shops=active_shops)
        if not lanes:
            break
        with ThreadPoolExecutor(max_workers=max(1, len(lanes))) as executor:
            futures = [executor.submit(process_lane, shop, rows) for shop, rows in lanes]
            failures = wait_for_lane_futures(futures)
        for exc in failures:
            emit({
                "status": "evidence_lane_retry",
                "pass": pass_index + 1,
                "message": compact(exc)[:500],
            })
        work = [
            row for row in pending_evidence_candidates(merged)
            if creator_identity(row) in selected_ids
        ]
        if not work:
            break
    if work:
        updates = []
        for row in work:
            current = dict(row)
            current["evidence_status"] = "error"
            current["evidence_error"] = "evidence lane interrupted after automatic retry"
            updates.append(current)
        merged = merge_evidence_candidate_updates(merged, updates)
        save_highwater(highwater, payload, merged)

    merged = [mark_precontact_qualification(row, payload.get("strategy") or {}) for row in merged]
    save_highwater(highwater, payload, merged)
    final_candidates = merged
    try:
        stable = json.loads(highwater.read_text(encoding="utf-8"))
        if len(stable.get("candidates") or []) > len(final_candidates):
            final_candidates = [row for row in stable.get("candidates") or [] if isinstance(row, dict)]
    except (OSError, json.JSONDecodeError, TypeError):
        pass
    final_candidates = [
        mark_precontact_qualification(row, payload.get("strategy") or {})
        for row in final_candidates
    ]
    save_highwater(highwater, payload, final_candidates)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = output_dir / f"{evidence_output_prefix(payload)}_{stamp}.json"
    result = {
        **payload,
        "status": "ready",
        "evidence_reviewed_at": datetime.now().isoformat(timespec="seconds"),
        "candidate_count": len(final_candidates),
        "evidence_verified_count": sum(1 for row in final_candidates if row.get("content_evidence_reviewed")),
        "candidates": final_candidates,
    }
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    save_highwater(highwater, payload, merged)
    emit({
        "status": "evidence_finished",
        "output": str(output),
        "candidate_count": len(merged),
        "evidence_verified_count": result["evidence_verified_count"],
    })


if __name__ == "__main__":
    main()
