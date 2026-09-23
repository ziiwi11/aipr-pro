from __future__ import annotations

import re
import json
from datetime import datetime
from typing import Any, Iterable


ROBOT_CONTRACT_VERSION = "aipr.robot.outreach.v1"


def compact(value: Any) -> str:
    return str(value or "").strip()


def extract_sales_lower(value: Any) -> int:
    text = compact(value).replace(",", "")
    number_pattern = r"\d+(?:\.\d+)?"
    currency_ranges = re.findall(
        rf"(?:¥|￥)\s*({number_pattern})\s*(万|w)?\s*[~～至-]\s*(?:¥|￥)?\s*({number_pattern})\s*(万|w)?",
        text,
        flags=re.I,
    )
    if currency_ranges:
        return max(int(float(number) * (10000 if unit else 1)) for number, unit, _high, _high_unit in currency_ranges)
    unit_ranges = re.findall(
        rf"({number_pattern})\s*(万|w)\s*[~～至-]\s*({number_pattern})\s*(万|w)?",
        text,
        flags=re.I,
    )
    if unit_ranges:
        return max(int(float(number) * 10000) for number, _unit, _high, _high_unit in unit_ranges)
    range_match = re.search(rf"(?:¥|￥)?\s*({number_pattern})\s*(万|w)?\s*[~～至-]\s*(?:¥|￥)?\s*({number_pattern})\s*(万|w)?", text, flags=re.I)
    if range_match:
        number, unit = range_match.group(1), range_match.group(2)
        return int(float(number) * (10000 if unit else 1))
    matches = re.findall(rf"(?:¥|￥)?\s*({number_pattern})\s*(万|w)?", text, flags=re.I)
    values = [int(float(number) * (10000 if unit else 1)) for number, unit in matches]
    return max(values, default=0)


def extract_short_video_sales_lower(value: Any) -> int:
    text = compact(value).replace(",", "")
    number_pattern = r"\d+(?:\.\d+)?"
    matches = re.findall(
        rf"(?:短视频|视频)\s*\d+\s*件\s*[；;:：]?\s*(?:¥|￥)\s*({number_pattern})\s*(万|w)?\s*[~～至-]\s*(?:¥|￥)?\s*({number_pattern})\s*(万|w)?",
        text,
        flags=re.I,
    )
    return max(
        (int(float(number) * (10000 if unit else 1)) for number, unit, _high, _high_unit in matches),
        default=0,
    )


def has_positive_live_activity(value: Any) -> bool:
    return bool(re.search(r"直播\s*[1-9]\d*\s*(?:个|次|场|件)", compact(value)))


def content_blocked(text: str, evidence: list[str], safety_markers: list[str] | tuple[str, ...]) -> bool:
    return not evidence and any(marker and marker in compact(text) for marker in safety_markers)


def _plain(candidate: dict[str, Any], *keys: str) -> str:
    return next((compact(candidate.get(key)) for key in keys if compact(candidate.get(key))), "")


def expanded_exclusion_hit(candidate: dict[str, Any], rules: dict[str, Any]) -> str:
    """Return the configured exclusion whose common aliases match the creator.

    Platform categories are broad enough that business accounts and unrelated
    personas can still be labelled as beauty/personal care.  Apply the task's
    hard exclusions before the structured beauty fast-path so those accounts
    cannot become contact-reveal candidates merely because their category and
    gender fields look valid.
    """
    identity_text = " ".join([
        compact(candidate.get("nickname")),
        compact(candidate.get("category") or candidate.get("main_category")),
        compact(candidate.get("creator_intro")),
        compact(candidate.get("profile_intro")),
        compact(candidate.get("douyin_intro")),
    ])
    aliases: dict[str, tuple[str, ...]] = {
        "母婴": (
            "母婴", "育儿", "婴儿", "宝宝", "宝妈", "孕妈", "孕妇", "孕期",
            "二胎", "三胎", "妈妈", "妈咪", "麻麻",
        ),
        "男性": (
            "男士", "男生", "男人", "型男", "男妆", "男护", "帅哥", "变帅",
            "老爸", "爸爸", "老公", "大叔", "先生", "男友", "男朋友",
        ),
        "美食": ("美食", "零食", "月饼", "烘焙", "吃播", "探店吃", "餐饮"),
        "探店": ("探店", "到店", "本地生活"),
        "品牌店铺": (
            "官方旗舰店", "旗舰店", "专卖店", "工厂店", "品牌店", "品牌官方",
            "官方账号", "企业号", "品牌号", "有限公司", "个体工商户", "商贸",
            "护理中心", "美容中心", "美容院", "个人护理馆", "总店", "门店",
            "美妆店", "护肤店", "小卖部", "百货", "商行", "供应链",
            "源头厂家", "源头工厂",
        ),
        "宠物": ("宠物", "萌宠", "猫咪", "狗狗", "铲屎官"),
        "非真人搬运": ("搬运", "混剪", "素材号", "影视剪辑", "无人出镜"),
        "低质杂乱画面": ("低质", "杂乱画面"),
    }
    for raw in rules.get("exclusions") or []:
        exclusion = compact(raw).lstrip("：:")
        if not exclusion:
            continue
        if exclusion == "直播":
            continue
        terms = aliases.get(exclusion, (exclusion,))
        if any(term and term in identity_text for term in terms):
            return exclusion
    return ""


def normalize_contact_value(value: Any) -> str:
    text = compact(value).lower()
    if not text or any(marker in text for marker in ("*", "暂无", "未公开", "不可见", "待补")):
        return ""
    for normalizer in (normalize_phone_value, normalize_email_value, normalize_wechat_value):
        if normalized := normalizer(text):
            return normalized
    return re.sub(r"\s+", "", text)


def normalize_phone_value(value: Any) -> str:
    text = compact(value)
    if not text or "*" in text:
        return ""
    match = re.search(r"(?<!\d)(?:\+?86[\s-]?)?(1[3-9]\d{9})(?!\d)", text)
    return match.group(1) if match else ""


def normalize_wechat_value(value: Any) -> str:
    text = compact(value).lower()
    if not text or "*" in text:
        return ""
    if normalize_phone_value(text):
        return normalize_phone_value(text)
    return text if re.fullmatch(r"[a-z][a-z0-9_-]{5,19}", text) else ""


def normalize_email_value(value: Any) -> str:
    text = compact(value).lower()
    if not text or "*" in text:
        return ""
    return text if re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", text) else ""


def canonicalize_contact_fields(candidate: dict[str, Any]) -> dict[str, Any]:
    current = dict(candidate)
    groups = (
        (("buyin_contact_phone", "cart_contact_phone", "phone", "手机号"), normalize_phone_value),
        (("buyin_contact_wechat", "cart_contact_wechat", "wechat", "微信"), normalize_wechat_value),
        (("buyin_contact_email", "cart_contact_email", "email", "邮箱"), normalize_email_value),
    )
    for keys, normalizer in groups:
        for key in keys:
            if key in current and compact(current.get(key)):
                current[key] = normalizer(current.get(key))
    return current


def contact_identity_values(candidate: dict[str, Any]) -> set[str]:
    groups = (
        (("buyin_contact_wechat", "cart_contact_wechat", "wechat", "微信"), normalize_wechat_value),
        (("buyin_contact_phone", "cart_contact_phone", "phone", "手机号"), normalize_phone_value),
        (("buyin_contact_email", "cart_contact_email", "email", "邮箱"), normalize_email_value),
    )
    return {
        normalized
        for keys, normalizer in groups
        for key in keys
        if (normalized := normalizer(candidate.get(key)))
    }


def creator_identity_values(candidate: dict[str, Any]) -> set[str]:
    """Return every stable identity value exposed for a creator.

    A creator can appear with a different encrypted ``identity`` in separate
    collection passes while retaining the same public Douyin ID or Buyin UID.
    Delivery deduplication must therefore compare all available strong IDs,
    not only the first populated field.
    """
    keys = (
        "identity", "buyin_uid", "douyin_id", "author_id", "sec_uid",
        "creator_id", "uid", "id",
    )
    return {
        value.casefold()
        for key in keys
        if (value := compact(candidate.get(key)))
    }


def _sales(candidate: dict[str, Any]) -> int:
    short_video_sales = extract_short_video_sales_lower(candidate.get("profile_text"))
    if short_video_sales:
        return short_video_sales
    explicit = candidate.get("monthly_sales_value")
    if explicit not in (None, ""):
        try:
            return max(0, int(float(explicit)))
        except (TypeError, ValueError):
            pass
    return extract_sales_lower(" ".join([
        compact(candidate.get("monthly_sales")),
        compact(candidate.get("profile_text")),
        compact(candidate.get("ui_contact_page_excerpt")),
    ]))


def requires_underwear_product_evidence(rules: dict[str, Any]) -> bool:
    if rules.get("minimumUnderwearProductSales") not in (None, "", 0, "0"):
        return True
    brief = compact(rules.get("brief"))
    return any(marker in brief for marker in (
        "内衣单品", "单品月销", "单品销售额", "短视频销售额",
    ))


def score_candidate(candidate: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    evidence = " ".join([
        compact(candidate.get("nickname")),
        compact(candidate.get("profile_text")),
        compact(candidate.get("douyin_content_text")),
        " ".join(compact(item) for item in candidate.get("content_evidence") or []),
    ])
    identity_evidence = " ".join([
        compact(candidate.get("nickname")),
        compact(candidate.get("category")),
        compact(candidate.get("creator_intro")),
        compact(candidate.get("profile_intro")),
        compact(candidate.get("douyin_intro")),
        compact(candidate.get("gender")),
    ])
    exclusion = expanded_exclusion_hit(candidate, rules)
    for item in rules.get("exclusions") or []:
        if exclusion:
            break
        term = compact(item)
        if not term:
            continue
        if term == "直播":
            if has_positive_live_activity(candidate.get("profile_text")):
                exclusion = term
                break
        elif term in identity_evidence:
            exclusion = term
            break
    if exclusion:
        return {"score": 0, "excluded": True, "decision": "淘汰", "reason": f"命中硬性排除：{exclusion}"}

    strict_required = requires_underwear_product_evidence(rules)
    strict = candidate.get("osmana_evaluation") if isinstance(candidate.get("osmana_evaluation"), dict) else None
    if strict_required and strict is None:
        return {
            "score": 0,
            "excluded": True,
            "decision": "淘汰",
            "reason": "缺少内衣单品近30天短视频销售额证据",
            "sales": 0,
            "level": 1,
        }
    if strict is not None:
        failures = [compact(item) for item in strict.get("failures") or [] if compact(item)]
        level = int(strict.get("level") or 1)
        sales = int(strict.get("underwear_product_sales_low") or 0)
        minimum_sales = max(
            0,
            int(rules.get("minimumUnderwearProductSales") or rules.get("minimumMonthlySales") or 0),
        )
        allowed_levels = {int(item) for item in rules.get("creatorLevels") or [] if str(item).isdigit()}
        strict_incomplete = (
            sales < minimum_sales
            or (allowed_levels and level not in allowed_levels)
            or not candidate.get("content_evidence_reviewed")
            or not candidate.get("visual_persona_verified")
        )
        if not strict.get("qualified") or strict_incomplete:
            return {
                "score": 0,
                "excluded": True,
                "decision": "淘汰",
                "reason": "未通过内衣单品短视频硬规则：" + "、".join(failures or ["strict_evidence_incomplete"]),
                "sales": sales,
                "level": level,
            }
        return {
            "score": 100,
            "excluded": False,
            "decision": "推荐建联",
            "reason": "女性真人短视频、身材、等级、内衣单品销量及联系方式均已核验",
            "sales": sales,
            "level": level,
        }

    structured_gate = candidate.get("evidence_gate") if isinstance(candidate.get("evidence_gate"), dict) else {}
    candidate_category = compact(candidate.get("category") or candidate.get("main_category"))
    task_category = compact(rules.get("category"))
    beauty_task = any(marker in task_category for marker in ("美妆", "个护"))
    structured_beauty = bool(
        beauty_task
        and structured_gate.get("beauty_vertical_verified") is True
        and int(candidate.get("gender") or 0) == 2
        and any(marker in candidate_category for marker in ("美妆", "个护家清"))
        and candidate.get("contact_visible") is True
        and candidate.get("content_evidence_reviewed") is True
    )
    if structured_beauty:
        level_match = re.search(r"([1-4])", compact(candidate.get("talent_level") or candidate.get("author_level")))
        level = int(level_match.group(1)) if level_match else 1
        allowed_levels = {int(item) for item in rules.get("creatorLevels") or [] if str(item).isdigit()}
        if allowed_levels and level not in allowed_levels:
            return {"score": 0, "excluded": True, "decision": "淘汰", "reason": "达人等级不在筛选范围", "sales": 0, "level": level}
        sales = _sales(candidate)
        minimum_sales = max(0, int(rules.get("minimumMonthlySales") or 0))
        if sales < minimum_sales:
            return {
                "score": 0,
                "excluded": True,
                "decision": "淘汰",
                "reason": f"近30天销售额低于{minimum_sales}元",
                "sales": sales,
                "level": level,
            }
        contact = _plain(
            candidate,
            "buyin_contact_wechat", "cart_contact_wechat", "buyin_contact_phone", "cart_contact_phone",
            "buyin_contact_email", "cart_contact_email",
        )
        return {
            "score": 100 if contact else 85,
            "excluded": False,
            "decision": "推荐建联" if contact else "待补联系方式",
            "reason": "联盟结构化字段已核验女性、美妆个护垂类及联系方式可见" if contact else "联盟垂类证据通过，待内置主页揭示明文联系方式",
            "sales": sales,
            "level": level,
        }

    profile_verified = bool(candidate.get("profile_verified") or candidate.get("buyin_profile_url"))
    douyin_verified = bool(candidate.get("douyin_homepage"))
    content_reviewed = bool(candidate.get("content_evidence_reviewed"))
    contact = _plain(
        candidate,
        "buyin_contact_wechat", "cart_contact_wechat", "buyin_contact_phone", "cart_contact_phone",
        "buyin_contact_email", "cart_contact_email",
    )
    sales = _sales(candidate)
    level_match = re.search(r"([1-4])", compact(candidate.get("talent_level") or candidate.get("cart_talent_level")))
    level = int(level_match.group(1)) if level_match else 1

    allowed_levels = {int(item) for item in rules.get("creatorLevels") or [] if str(item).isdigit()}
    if allowed_levels and level not in allowed_levels:
        return {"score": 0, "excluded": True, "decision": "淘汰", "reason": "达人等级不在筛选范围", "sales": sales, "level": level}
    minimum_sales = max(0, int(rules.get("minimumMonthlySales") or 0))
    if sales < minimum_sales:
        return {"score": 0, "excluded": True, "decision": "淘汰", "reason": f"近30天销售额低于{minimum_sales}元", "sales": sales, "level": level}
    category = compact(rules.get("category"))
    category_terms = {
        "服饰内衣": ("服饰", "内衣", "塑形", "提臀", "收腹", "试穿", "穿搭"),
        "美妆个护": ("美妆", "个护", "护肤", "洗护", "彩妆", "口红", "精华"),
        "母婴宠物": ("母婴", "育儿", "婴儿", "宠物"),
        "食品饮料": ("食品", "零食", "饮料", "冲饮"),
    }.get(category, ())
    if category_terms and not any(term in evidence for term in category_terms):
        return {"score": 0, "excluded": True, "decision": "淘汰", "reason": f"内容与{category}类目不匹配", "sales": sales, "level": level}
    if compact(rules.get("contentType")) == "真人口播" and not any(
        term in evidence for term in ("真人", "口播", "试穿", "上身", "测评", "穿搭")
    ):
        return {"score": 0, "excluded": True, "decision": "淘汰", "reason": "缺少真人口播或真人展示证据", "sales": sales, "level": level}

    score = 0
    score += 15 if profile_verified else 0
    score += 15 if douyin_verified else 0
    score += 20 if content_reviewed else 0
    score += 25 if sales >= 100000 else 18 if sales >= 50000 else 10 if sales > 0 else 0
    score += 15 if contact else 0
    score += 10 if level in {2, 3, 4} else 4
    threshold = max(0, min(100, int(rules.get("threshold") or 78)))

    if not profile_verified or not douyin_verified or not content_reviewed:
        decision = "待内容复核"
        reason = "抖音主页或近期内容证据尚未完成复核"
    elif score >= threshold and contact:
        decision = "推荐建联"
        reason = f"证据完整，综合评分 {score} 分"
    elif not contact:
        decision = "待补联系方式"
        reason = "内容通过但尚无明文联系方式"
    else:
        decision = "暂不推荐"
        reason = f"综合评分 {score} 分，低于门槛 {threshold} 分"
    return {"score": score, "excluded": False, "decision": decision, "reason": reason, "sales": sales, "level": level}


def mark_precontact_qualification(candidate: dict[str, Any], rules: dict[str, Any]) -> dict[str, Any]:
    current = dict(candidate)
    probe = dict(current)
    probe["buyin_contact_wechat"] = _plain(current, "buyin_contact_wechat", "cart_contact_wechat") or "__precontact__"
    if requires_underwear_product_evidence(rules):
        from osmana_creator_rules import evaluate_osmana_candidate

        existing = current.get("osmana_evaluation")
        if current.get("products_30d") or not isinstance(existing, dict):
            probe["osmana_evaluation"] = evaluate_osmana_candidate(probe, rules)
        else:
            strict = dict(existing)
            strict["failures"] = [
                compact(item)
                for item in strict.get("failures") or []
                if compact(item) and compact(item) != "missing_plain_contact"
            ]
            strict["qualified"] = not strict["failures"]
            strict["plain_contact"] = probe["buyin_contact_wechat"]
            probe["osmana_evaluation"] = strict
    evaluation = score_candidate(probe, rules)
    current["precontact_qualified"] = evaluation.get("decision") == "推荐建联"
    current["precontact_reason"] = evaluation.get("reason", "")
    current["precontact_sales"] = evaluation.get("sales", 0)
    current["precontact_level"] = evaluation.get("level", 1)
    return current


def select_delivery_candidates(
    candidates: Iterable[dict[str, Any]],
    rules: dict[str, Any],
    target_count: int,
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    seen_identities: set[str] = set()
    excluded_identities = {
        compact(value).casefold()
        for value in rules.get("excludeIdentities") or []
        if compact(value)
    }
    seen_contacts = {
        normalized
        for value in rules.get("excludeContacts") or []
        if (normalized := normalize_contact_value(value))
    }
    target = max(1, int(target_count or 1))
    for index, candidate in enumerate(candidates):
        evaluation = score_candidate(candidate, rules)
        contact = _plain(
            candidate,
            "buyin_contact_wechat", "cart_contact_wechat", "wechat", "微信",
            "buyin_contact_phone", "cart_contact_phone", "phone", "手机号",
            "buyin_contact_email", "cart_contact_email", "email", "邮箱",
        )
        identities = creator_identity_values(candidate) or {f"row:{index}"}
        contact_values = contact_identity_values(candidate)
        if (
            evaluation.get("decision") != "推荐建联"
            or not contact
            or not contact_values
            or bool(identities & excluded_identities)
            or bool(identities & seen_identities)
            or bool(contact_values & seen_contacts)
        ):
            continue
        seen_identities.update(identities)
        seen_contacts.update(contact_values)
        selected.append(candidate)
        if len(selected) >= target:
            break
    return selected


def _fee(level: int, sales: int, rules: dict[str, Any] | None = None) -> int:
    pricing = (rules or {}).get("pricing") if isinstance((rules or {}).get("pricing"), dict) else {}
    if pricing:
        low = int(pricing.get("preferredMin") or 300)
        high = int(pricing.get("preferredMax") or low)
        if level <= 2:
            return low
        if level == 3:
            return min(high, max(low, low + (high - low) // 2))
        return high
    if level <= 1:
        return 150 if sales >= 5000 else 0
    if level == 2:
        return 500 if sales >= 100000 else 400 if sales >= 30000 else 300
    if level == 3:
        return 800 if sales >= 200000 else 650 if sales >= 80000 else 500
    return 1200 if sales >= 300000 else 1000 if sales >= 150000 else 800


def build_delivery(
    candidates: Iterable[dict[str, Any]],
    rules: dict[str, Any],
    task_id: str,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    robot_queue: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates, start=1):
        evaluation = score_candidate(candidate, rules)
        wechat = _plain(candidate, "buyin_contact_wechat", "cart_contact_wechat", "wechat", "微信")
        phone = _plain(candidate, "buyin_contact_phone", "cart_contact_phone", "phone", "手机号")
        email = _plain(candidate, "buyin_contact_email", "cart_contact_email", "email", "邮箱")
        contact = "；".join(item for item in [f"微信:{wechat}" if wechat else "", f"手机:{phone}" if phone else "", f"邮箱:{email}" if email else ""] if item)
        identity = _plain(candidate, "identity", "buyin_uid", "douyin_id", "id")
        nickname = _plain(candidate, "nickname", "达人昵称") or f"达人 {index}"
        evidence = candidate.get("content_evidence") or []
        evidence_text = " | ".join(compact(item) for item in evidence if compact(item))
        strict = candidate.get("osmana_evaluation") if isinstance(candidate.get("osmana_evaluation"), dict) else {}
        product = strict.get("underwear_product_evidence") if isinstance(strict.get("underwear_product_evidence"), dict) else {}
        screenshot = _plain(candidate, "content_evidence_screenshot") or " | ".join(
            compact(item) for item in candidate.get("evidence_screenshots") or [] if compact(item)
        )
        row = {
            "序号": index,
            "主页身份ID": identity,
            "达人昵称": nickname,
            "抖音号": _plain(candidate, "douyin_id", "douyin_account_id", "unique_id", "buyin_account_id"),
            "抖音主页": _plain(candidate, "douyin_homepage"),
            "精选联盟主页": _plain(candidate, "buyin_profile_url", "精选联盟主页"),
            "达人等级": f"LV{evaluation.get('level', 1)}",
            "历史销售额": evaluation.get("sales", 0),
            "综合评分": evaluation["score"],
            "推荐结论": evaluation["decision"],
            "推荐理由": evaluation["reason"],
            "内容证据": evidence_text,
            "内容证据截图": screenshot,
            "身高(cm)": strict.get("height_cm", ""),
            "体重(斤)": strict.get("weight_jin", ""),
            "内衣单品": strict.get("underwear_product_title", ""),
            "内衣单品近30天短视频销售额": strict.get("underwear_product_sales_low", ""),
            "关联短视频数": product.get("related_video_num", ""),
            "关联直播场次": product.get("related_live_times", ""),
            "内容形态": "短视频" if strict else "",
            "建议报价": _fee(int(evaluation.get("level", 1)), int(evaluation.get("sales", 0)), rules),
            "授权要求": "含授权" if (rules.get("pricing") or {}).get("authorizationIncluded") else "待确认",
            "明文联系方式": contact,
            "联系方式": contact,
            "微信": wechat,
            "手机号": phone,
            "邮箱": email,
            "联系方式来源": _plain(candidate, "buyin_contact_source", "cart_contact_source"),
            "联系方式状态": "已获取明文" if contact else "待补",
            "验证结论": "主页与内容已验证" if candidate.get("content_evidence_reviewed") else "待内容复核",
            "分跑店铺": _plain(candidate, "shop", "lip_shop"),
        }
        if __package__:
            from .creator_jev import review as jev_review
        else:
            from creator_jev import review as jev_review
        advisory = jev_review(candidate, rules, 'aipr-pro')
        if advisory.get('enabled'):
            row['Jev内容复核'] = json.dumps(advisory, ensure_ascii=False)
        rows.append(row)
        if evaluation["decision"] == "推荐建联" and contact:
            robot_queue.append({
                "schemaVersion": ROBOT_CONTRACT_VERSION,
                "event": "creator.outreach.requested",
                "eventId": f"{task_id}:{identity}",
                "task": {"id": task_id},
                "creator": {
                    "id": identity,
                    "name": nickname,
                    "douyinAccount": row["抖音号"],
                    "douyinHomepage": row["抖音主页"],
                    "buyinHomepage": row["精选联盟主页"],
                    "contact": {"wechat": wechat, "phone": phone, "email": email},
                },
                "recommendation": {
                    "score": evaluation["score"],
                    "fee": row["建议报价"],
                    "openingMessage": f"你好，我们正在为品牌筛选内容合作达人，看到你的内容与本次产品方向很匹配，想和你沟通合作细节。",
                    "reason": evaluation["reason"],
                },
                "guardrails": {
                    "requiresHumanApprovalForFee": True,
                    "requiresHumanApprovalForSample": True,
                    "requiresHumanApprovalForCustomPromise": True,
                    "allowAutomaticSend": False,
                },
                "status": "pending",
                "queuedAt": datetime.now().isoformat(timespec="seconds"),
            })

    plain = sum(1 for row in rows if row["明文联系方式"])
    return {
        "status": "ready",
        "task_id": task_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "target_count": len(rows),
        "candidate_count": len(rows),
        "recommended_count": sum(1 for row in rows if row["推荐结论"] == "推荐建联"),
        "plain_contact_count": plain,
        "wechat_contact_count": sum(1 for row in rows if row["微信"]),
        "phone_contact_count": sum(1 for row in rows if row["手机号"]),
        "pending_contact_count": max(0, len(rows) - plain),
        "robot_contract_version": ROBOT_CONTRACT_VERSION,
        "robot_queue_count": len(robot_queue),
        "rows": rows,
        "robot_queue": robot_queue,
    }
