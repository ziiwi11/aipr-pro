from __future__ import annotations

from typing import Any, Iterable
from urllib.parse import quote
import shutil
from pathlib import Path


PROFILE_BASE = "https://buyin.jinritemai.com/dashboard/servicehall/daren-profile"
PROFILE_READY_MARKERS = ("达人自主披露联系方式", "添加达人库", "已加达人库", "粉丝数", "带货口碑")


def build_profile_url(uid: str, author_level: int | None = None) -> str:
    clean_uid = str(uid or "").strip()
    if not clean_uid:
        return ""
    level = f"&author_level={int(author_level)}" if author_level is not None else ""
    return (
        f"{PROFILE_BASE}?uid={quote(clean_uid, safe='_-.')}{level}"
        "&enter_from=1&scene=1&author_type=1"
        "&previous_page_name=0%2C5&previous_page_type=0%2C100"
        "&module_name=recommend"
    )


def profile_content_ready(body_text: str) -> bool:
    text = str(body_text or "").strip()
    return any(marker in text for marker in PROFILE_READY_MARKERS)


def creator_identity(candidate: dict[str, Any]) -> str:
    for key in ("identity", "buyin_uid", "douyin_id", "xingtu_author_id", "id", "buyin_profile_url"):
        value = str(candidate.get(key) or "").strip()
        if value:
            return value
    return str(candidate.get("nickname") or candidate.get("达人昵称") or "").strip()


def merge_contact_candidates(
    base_candidates: Iterable[dict[str, Any]],
    updates: Iterable[dict[str, Any]],
) -> list[dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for candidate in base_candidates:
        key = creator_identity(candidate)
        if not key:
            continue
        if key not in merged:
            order.append(key)
        merged[key] = dict(candidate)
    for update in updates:
        key = creator_identity(update)
        if not key:
            continue
        if key not in merged:
            order.append(key)
            merged[key] = {}
        clean_update = {name: value for name, value in update.items() if value not in (None, "", [], {})}
        merged[key] = {**merged[key], **clean_update}
    return [merged[key] for key in order]


def contact_totals(candidates: Iterable[dict[str, Any]]) -> dict[str, int]:
    rows = list(candidates)

    def value(row: dict[str, Any], *keys: str) -> str:
        return next((str(row.get(key) or "").strip() for key in keys if str(row.get(key) or "").strip()), "")

    wechat = sum(1 for row in rows if value(row, "buyin_contact_wechat", "cart_contact_wechat", "wechat", "微信"))
    phone = sum(1 for row in rows if value(row, "buyin_contact_phone", "cart_contact_phone", "phone", "手机号"))
    email = sum(1 for row in rows if value(row, "buyin_contact_email", "cart_contact_email", "email", "邮箱"))
    plain = sum(1 for row in rows if value(
        row,
        "buyin_contact_wechat", "cart_contact_wechat", "wechat", "微信",
        "buyin_contact_phone", "cart_contact_phone", "phone", "手机号",
        "buyin_contact_email", "cart_contact_email", "email", "邮箱",
    ))
    return {"plain": plain, "wechat": wechat, "phone": phone, "email": email}


def terminal_contact_failure(candidate: dict[str, Any]) -> bool:
    terminal = {"category_not_matched", "no_contact_icon", "missing_profile_url"}
    return any(
        str(candidate.get(key) or "").strip() in terminal
        for key in ("ui_contact_probe_status", "buyin_contact_probe_status", "cart_contact_probe_status")
    )


def copy_if_distinct(source: Path, destination: Path) -> bool:
    if source.resolve() == destination.resolve():
        return False
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
    return True
