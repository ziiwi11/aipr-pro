from __future__ import annotations

import re
from typing import Any, Iterable


UNDERWEAR_TERMS = (
    "内衣", "内裤", "文胸", "胸罩", "bra", "塑身", "塑形", "提臀裤", "收腹裤",
    "束腰", "束身", "美体衣", "塑身背心", "无痕裤", "安全裤", "鲨鱼裤",
)
UNDERWEAR_EXCLUSION_TERMS = (
    "男士", "男款", "男生", "男童", "女童", "儿童", "青少年",
    "少女", "学生", "发育期", "孕妇", "哺乳",
)
SHAPEWEAR_TERMS = (
    "提臀", "塑形", "塑身", "收腹", "臀型", "臀线", "妈妈臀", "臀凹陷",
    "久坐", "产后", "腰臀", "身材管理", "前后对比", "上身展示", "真人试穿",
)
CONTACT_KEYS = (
    "buyin_contact_wechat", "cart_contact_wechat", "wechat", "微信",
    "buyin_contact_phone", "cart_contact_phone", "phone", "手机号",
    "buyin_contact_email", "cart_contact_email", "email", "邮箱",
)


def compact(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def extract_height_weight(text: Any) -> tuple[float | None, float | None]:
    value = compact(text).lower()
    height: float | None = None
    weight_jin: float | None = None

    slash = re.search(r"(?<!\d)(1[4-9][0-9])\s*(?:cm)?\s*[/／]\s*(\d{2,3}(?:\.\d+)?)\s*(kg|斤)?(?!\d)", value)
    if slash:
        height = float(slash.group(1))
        weight = float(slash.group(2))
        unit = slash.group(3)
        weight_jin = weight if unit == "斤" or (not unit and weight > 70) else weight * 2

    if height is None:
        match = re.search(r"(?:身高\s*[:：]?\s*)?(1[4-9][0-9])\s*cm", value)
        if not match:
            match = re.search(r"身高\s*[:：]?\s*(1[4-9][0-9])(?!\s*[/／\d])", value)
        if match:
            height = float(match.group(1))

    if weight_jin is None:
        kg = re.search(r"(?:体重\s*[:：]?\s*)?(\d{2}(?:\.\d+)?)\s*kg", value)
        jin = re.search(r"(?:体重\s*[:：]?\s*)?(\d{2,3}(?:\.\d+)?)\s*斤", value)
        if kg:
            weight_jin = float(kg.group(1)) * 2
        elif jin:
            weight_jin = float(jin.group(1))
        else:
            labelled = re.search(r"体重\s*[:：]?\s*(\d{2,3}(?:\.\d+)?)(?!\s*(?:kg|斤|\d))", value)
            if labelled:
                weight = float(labelled.group(1))
                weight_jin = weight if weight > 70 else weight * 2
    return height, weight_jin


def extract_profile_intro(text: Any) -> str:
    value = compact(text)
    marker = "达人简介："
    if marker not in value:
        return value
    intro = value.split(marker, 1)[1]
    for end in ("达人手机号", "达人微信号", "概览", "场景分析", "粉丝分析", "带货分析"):
        if end in intro:
            intro = intro.split(end, 1)[0]
    return compact(intro)


def is_underwear_product(title: Any) -> bool:
    value = compact(title).lower()
    if any(term in value for term in UNDERWEAR_EXCLUSION_TERMS):
        return False
    if any(term in value for term in UNDERWEAR_TERMS):
        return True
    return "瑜伽裤" in value and any(term in value for term in ("提臀", "收腹", "塑形", "塑身"))


def normalize_products(products: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in products:
        good = item.get("good_info") if isinstance(item.get("good_info"), dict) else {}
        title = compact(item.get("title") or good.get("title"))
        low = _number(item.get("sales_low"))
        high = _number(item.get("sales_high"))
        if low is None:
            low = _number(item.get("goods_sale_low")) or 0
        if high is None:
            high = _number(item.get("goods_sale_high")) or low
        normalized.append({
            "title": title,
            "sales_low": int(low),
            "sales_high": int(high),
            "product_id": compact(item.get("product_id") or good.get("pidStr") or good.get("pid")),
            "detail_url": compact(item.get("detail_url") or good.get("detail_url")),
            "is_underwear": is_underwear_product(title),
            "related_video_num": int(item.get("related_video_num") or 0),
            "related_live_times": int(item.get("related_live_times") or 0),
        })
    return normalized


def parse_level(value: Any) -> int:
    match = re.search(r"([0-9])", compact(value))
    return int(match.group(1)) if match else 0


def plain_contact(candidate: dict[str, Any]) -> str:
    return next((compact(candidate.get(key)) for key in CONTACT_KEYS if compact(candidate.get(key))), "")


def is_short_video_only_creator(candidate: dict[str, Any]) -> bool:
    profile_text = compact(candidate.get("profile_text"))
    content_stats = re.search(r"内容数据.*?直播\s*(\d+)个.*?视频\s*(\d+)个", profile_text)
    if content_stats:
        return int(content_stats.group(1)) == 0 and int(content_stats.group(2)) > 0
    return compact(candidate.get("main_sale_type") or candidate.get("buyin_main_sale_type")) == "纯短视频"


def evaluate_osmana_candidate(candidate: dict[str, Any], strategy: dict[str, Any]) -> dict[str, Any]:
    failures: list[str] = []
    level = parse_level(candidate.get("talent_level") or candidate.get("cart_talent_level") or candidate.get("author_level"))
    minimum_level = int(strategy.get("minimumLevel") or 2)
    if level < minimum_level:
        failures.append(f"level_below_{minimum_level}")
    if not is_short_video_only_creator(candidate):
        failures.append("creator_not_short_video_only")

    explicit_intro = compact(candidate.get("profile_intro") or candidate.get("bio") or candidate.get("达人简介"))
    profile_intro = explicit_intro or extract_profile_intro(candidate.get("profile_text"))
    height, weight_jin = extract_height_weight(profile_intro)
    height_range = strategy.get("heightCm") or {"min": 155, "max": 170}
    weight_range = strategy.get("weightJin") or {"min": 80, "max": 110}
    if strategy.get("requireBodyMeasurements", True):
        if height is None:
            failures.append("missing_height_evidence")
        elif not float(height_range["min"]) <= height <= float(height_range["max"]):
            failures.append("height_out_of_range")
        if weight_jin is None:
            failures.append("missing_weight_evidence")
        elif not float(weight_range["min"]) <= weight_jin <= float(weight_range["max"]):
            failures.append("weight_out_of_range")

    products = normalize_products(candidate.get("products_30d") or [])
    underwear_products = [
        item for item in products
        if item["is_underwear"] and item["related_video_num"] > 0 and item["related_live_times"] == 0
    ]
    best = max(underwear_products, key=lambda item: item["sales_low"], default=None)
    threshold = int(strategy.get("minimumUnderwearProductSales") or 10000)
    if not best or int(best["sales_low"]) < threshold:
        failures.append(f"underwear_product_sales_not_above_{threshold}")
        failures.append(f"short_video_underwear_sales_not_above_{threshold}")

    content = compact(candidate.get("douyin_content_text")) + " " + " ".join(
        compact(item) for item in candidate.get("content_evidence") or []
    )
    if not candidate.get("content_evidence_reviewed"):
        failures.append("content_unverified")
    if strategy.get("requireShapewearContent", True) and not any(term in content for term in SHAPEWEAR_TERMS):
        failures.append("content_not_shapewear_relevant")
    if not candidate.get("visual_persona_verified"):
        failures.append("visual_persona_unverified")

    contact = plain_contact(candidate)
    if strategy.get("requirePlainContact", True) and not contact:
        failures.append("missing_plain_contact")

    return {
        "qualified": not failures,
        "failures": failures,
        "level": level,
        "height_cm": height,
        "weight_jin": weight_jin,
        "underwear_product_title": best["title"] if best else "",
        "underwear_product_sales_low": int(best["sales_low"]) if best else 0,
        "underwear_product_sales_high": int(best["sales_high"]) if best else 0,
        "underwear_product_evidence": best or {},
        "plain_contact": contact,
    }
