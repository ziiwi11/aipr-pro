from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse

from console_io import configure_utf8_stdout
from osmana_creator_rules import compact, parse_level


configure_utf8_stdout()

REJECT_TERMS = (
    "男士", "男生", "男童", "女童", "儿童", "青少年", "孕妇", "哺乳", "母婴",
)


def first_value(row: dict[str, Any], *keys: str) -> str:
    return next((compact(row.get(key)) for key in keys if compact(row.get(key))), "")


def convert_legacy_candidate(
    row: dict[str, Any],
    shop: str,
    allow_unknown_sale_type: bool = False,
) -> dict[str, Any] | None:
    supplied_profile = first_value(row, "buyin_profile_url", "精选联盟主页")
    parsed_uid = first_value(row, "buyin_uid", "buyin_author_id", "精选联盟UID")
    if not parsed_uid and supplied_profile:
        parsed_uid = compact((parse_qs(urlparse(supplied_profile).query).get("uid") or [""])[0])
    uid = parsed_uid
    level = parse_level(
        row.get("cart_talent_level")
        or row.get("talent_level")
        or row.get("达人等级")
        or row.get("等级")
    )
    sale_type = compact(row.get("buyin_main_sale_type") or row.get("main_sale_type"))
    wechat = first_value(row, "buyin_contact_wechat", "cart_contact_wechat", "aos_wechat", "微信")
    phone = first_value(row, "buyin_contact_phone", "cart_contact_phone", "aos_phone", "手机", "手机号")
    raw_keywords = row.get("source_keywords") or []
    if isinstance(raw_keywords, str):
        raw_keywords = [raw_keywords]
    source_keywords = [compact(value) for value in raw_keywords if compact(value)]
    nickname = first_value(row, "nickname", "达人昵称")
    reject_text = " ".join((nickname, *source_keywords))
    if (
        not uid
        or level < 2
        or (sale_type != "纯短视频" and not (allow_unknown_sale_type and not sale_type))
        or not (wechat or phone)
        or any(term in reject_text for term in REJECT_TERMS)
    ):
        return None

    douyin_id = first_value(row, "buyin_account_id", "unique_id", "douyin_id", "抖音号/账号ID")
    if douyin_id.startswith("v2_"):
        douyin_id = ""
    query = urlencode({"uid": uid, "author_level": level, "enter_from": 1, "scene": 1})
    return {
        "identity": uid,
        "buyin_uid": uid,
        "nickname": nickname,
        "douyin_id": douyin_id,
        "talent_level": f"LV{level}",
        "author_level": level,
        "category": compact(row.get("cart_category")),
        "categories": [compact(row.get("cart_category"))] if compact(row.get("cart_category")) else [],
        "main_sale_type": sale_type,
        "contact_visible": True,
        "buyin_contact_visible": True,
        "buyin_contact_text": first_value(row, "buyin_contact_text", "cart_contact_text"),
        "buyin_contact_wechat": wechat,
        "buyin_contact_phone": phone,
        "buyin_profile_url": supplied_profile or f"https://buyin.jinritemai.com/dashboard/servicehall/daren-profile?{query}",
        "source_keyword": source_keywords[0] if source_keywords else "奥斯曼娜历史池重验",
        "source_keywords": source_keywords,
        "source_type": "legacy_osmana_reverification",
        "shop": shop,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", action="append", required=True)
    parser.add_argument("--shop", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--allow-unknown-sale-type", action="store_true")
    args = parser.parse_args()

    converted: list[dict[str, Any]] = []
    seen: set[str] = set()
    for source_name in args.input:
        payload = json.loads(Path(source_name).resolve().read_text(encoding="utf-8"))
        for row in payload.get("candidates") or payload.get("rows") or []:
            candidate = convert_legacy_candidate(row, args.shop, args.allow_unknown_sale_type)
            if not candidate or candidate["identity"] in seen:
                continue
            seen.add(candidate["identity"])
            converted.append(candidate)

    output = Path(args.out).resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "status": "ready",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "candidate_count": len(converted),
        "candidates": converted,
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "candidate_count": len(converted)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
