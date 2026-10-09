from __future__ import annotations
from contact_shop_cooldown import cooldown_path, shop_cooldown_until

import argparse
import fcntl
import json
import os
import random
import time
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit
from urllib.request import urlopen

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from console_io import configure_utf8_stdout
from contact_pipeline_contract import copy_if_distinct, profile_content_ready, terminal_contact_failure
from embedded_cdp import connect_shop


configure_utf8_stdout()


OUT_DIR = Path(os.environ.get("AIPR_OUTPUT_DIR", "output"))
WORKER_OUT = Path(os.environ.get("AIPR_WORKER_OUTPUT", str(OUT_DIR)))


def latest(pattern: str) -> Path:
    files = sorted(OUT_DIR.glob(pattern), key=lambda item: item.stat().st_mtime)
    if not files:
        raise FileNotFoundError(pattern)
    return files[-1]


def resolve_cdp_endpoint(endpoint: str) -> str:
    if endpoint.startswith(("ws://", "wss://")):
        return endpoint
    with urlopen(endpoint.rstrip("/") + "/json/version", timeout=5) as response:
        payload = json.loads(response.read().decode("utf-8"))
    return str(payload["webSocketDebuggerUrl"])


def compact(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def parse_contact_items(items: list[str]) -> dict[str, str]:
    phone = ""
    wechat = ""
    email = ""
    lines: list[str] = []
    for item in items:
        text = compact(item)
        if not text or "********" in text:
            continue
        if "达人手机号" in text:
            match = re.search(r"1[3-9]\d{9}", text)
            phone = phone or (match.group(0) if match else text.split("：", 1)[-1].strip())
            lines.append(text)
        elif "达人微信号" in text:
            value = text.split("：", 1)[-1].strip()
            if value and "********" not in value:
                wechat = wechat or value
                lines.append(text)
        elif "达人邮箱" in text or "邮箱" in text:
            match = re.search(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text)
            email = email or (match.group(0) if match else text.split("：", 1)[-1].strip())
            lines.append(text)
    merged = "；".join(
        value
        for value in [
            f"微信:{wechat}" if wechat else "",
            f"手机:{phone}" if phone else "",
            f"邮箱:{email}" if email else "",
        ]
        if value
    )
    return {"contact": merged, "wechat": wechat, "phone": phone, "email": email, "evidence": " | ".join(lines)}


def visible_buttons(page) -> list[dict[str, Any]]:
    return page.evaluate(
        """() => Array.from(document.querySelectorAll('button')).map((b, i) => {
          const r = b.getBoundingClientRect();
          return {
            i,
            text: (b.innerText || b.textContent || '').trim().replace(/\\s+/g, ' '),
            x: r.x + r.width / 2,
            y: r.y + r.height / 2,
            w: r.width,
            h: r.height,
            disabled: Boolean(b.disabled),
          };
        }).filter(b => b.w > 0 && b.h > 0)"""
    )


def contact_items(page) -> list[str]:
    return page.evaluate(
        """() => Array.from(document.querySelectorAll('.index-module__contact-item___ny9bn'))
          .map(el => (el.innerText || el.textContent || '').trim().replace(/\\s+/g, ' '))
          .filter(Boolean)"""
    )


def unresolved_contact_icons(page, candidate: dict[str, Any]) -> list[dict[str, Any]]:
    visible = parse_contact_items(contact_items(page))
    known = {channel: visible[channel] or candidate.get(f"buyin_contact_{channel}") or candidate.get(f"cart_contact_{channel}") for channel in ("phone", "wechat", "email")}
    def missing(icon):
        text = str(icon.get("text") or "")
        channel = "wechat" if "微信" in text else "phone" if "手机" in text else "email" if "邮箱" in text else ""
        return not channel or not known[channel]
    return [icon for icon in contact_icons(page) if missing(icon)]


def contact_icons(page) -> list[dict[str, Any]]:
    return page.evaluate(
        """() => Array.from(document.querySelectorAll('.index-module__contact-item___ny9bn')).map((item, idx) => {
          const btn = item.querySelector('.index-module__contact-item-btn___tZUqf');
          if (!btn) return null;
          const r = btn.getBoundingClientRect();
          const text = (item.innerText || item.textContent || '').trim().replace(/\\s+/g, ' ');
          return {idx, text, x: r.x + r.width / 2, y: r.y + r.height / 2, w: r.width, h: r.height};
        }).filter(Boolean).filter(item => item.text.includes('********'))"""
    )


def parse_contact_view_confirmation(payload: Any) -> dict[str, Any]:
    data = payload if isinstance(payload, dict) else {}
    text = compact(data.get("text"))
    if "确认查看该达人的联系方式" not in text and "查看达人联系方式的机会" not in text:
        return {"status": "not_present", "text": text, "remaining": None, "confirm": None}
    match = re.search(r"还剩下\s*(\d+)\s*次", text)
    remaining = int(match.group(1)) if match else None
    confirm = data.get("confirm") if isinstance(data.get("confirm"), dict) else None
    if remaining == 0:
        status = "daily_quota_exhausted"
    elif confirm:
        status = "confirmation_required"
    else:
        status = "confirmation_button_missing"
    return {"status": status, "text": text, "remaining": remaining, "confirm": confirm}


def contact_view_confirmation(page) -> dict[str, Any]:
    payload = page.evaluate(
        """() => {
          const dialogs = Array.from(document.querySelectorAll('[role="dialog"], .auxo-modal-wrap'));
          const dialog = dialogs.find((item) => {
            const text = (item.innerText || item.textContent || '').replace(/\\s+/g, ' ').trim();
            return text.includes('确认查看该达人的联系方式') || text.includes('查看达人联系方式的机会');
          });
          if (!dialog) return null;
          const text = (dialog.innerText || dialog.textContent || '').replace(/\\s+/g, ' ').trim();
          const button = Array.from(dialog.querySelectorAll('button')).find((item) => {
            const label = (item.innerText || item.textContent || '').replace(/\\s+/g, ' ').trim();
            return label === '查看' && !item.disabled;
          });
          if (!button) return {text, confirm: null};
          const rect = button.getBoundingClientRect();
          return {
            text,
            confirm: {dom: true, x: rect.x + rect.width / 2, y: rect.y + rect.height / 2},
          };
        }"""
    )
    return parse_contact_view_confirmation(payload)


def confirm_contact_view(page, delay_ms: int) -> dict[str, Any]:
    confirmation = contact_view_confirmation(page)
    if confirmation["status"] != "confirmation_required":
        return confirmation
    if hasattr(page, "locator"):
        buttons = page.locator('[role="dialog"] button, .auxo-modal-wrap button')
        for index in range(buttons.count()):
            button = buttons.nth(index)
            if compact(button.inner_text(timeout=1000)) == "查看":
                for event in ("pointerdown", "mousedown", "pointerup", "mouseup", "click"):
                    button.dispatch_event(event)
                break
    else:
        page.evaluate("() => true")
    page.wait_for_timeout(max(3000, delay_ms))
    return {**confirmation, "status": "confirmed"}


def daily_quota_exhausted(message: Any) -> bool:
    text = compact(message)
    return "查看达人联系方式次数已达上限" in text


def should_stop_contact_batch(candidate: dict[str, Any]) -> bool:
    return candidate.get("ui_contact_probe_status") == "daily_quota_exhausted"


def wait_for_global_contact_slot(page, output_dir: Path, interval_ms: int, shop: str = '') -> int:
    """Serialize reveal requests across A/B and add human-like jitter.

    The contact endpoint applies a merchant-level throttle, so two individually
    slow browser lanes can still collide.  Keep the navigation parallel but
    serialize only the actual reveal click through a tiny cross-process lock.
    """
    lock_path = output_dir / ".contact_reveal.lock"
    state_path = output_dir / ".contact_reveal.timestamp"
    cooldown_file = cooldown_path(output_dir, shop)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+", encoding="utf-8") as lock_handle:
        fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)
        try:
            try:
                last_reveal = float(state_path.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                last_reveal = 0.0
            try:
                cooldown_until = float(cooldown_file.read_text(encoding="utf-8").strip())
            except (OSError, ValueError):
                cooldown_until = 0.0
            if shop in ("A", "B"):
                cooldown_until = shop_cooldown_until(output_dir, shop)
            if cooldown_until > time.time():
                raise RuntimeError(f"contact_cooldown_active:{cooldown_until}")
            jitter_ms = random.randint(1800, 5200)
            next_allowed = max(last_reveal + interval_ms / 1000, cooldown_until)
            remaining_ms = max(0, int((next_allowed - time.time()) * 1000))
            # 单次等待上限 15 分钟：避免冷却被写成很远的时间时，
            # 进程在这里无限阻塞（表现为「活着但零输出」的假死）。
            # 超过上限则让本轮尽快结束，由外层调度器在冷却过期后重试。
            if remaining_ms > 900000:
                raise RuntimeError(
                    f"contact_cooldown_too_long:{remaining_ms}ms"
                )
            waited_ms = remaining_ms + jitter_ms
            if waited_ms:
                page.wait_for_timeout(waited_ms)
            state_path.write_text(str(time.time()), encoding="utf-8")
            return waited_ms
        finally:
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)


def mark_global_rate_limit(output_dir: Path, cooldown_ms: int, shop: str = '') -> float:
    cooldown_file = cooldown_path(output_dir, shop)
    try:
        previous = float(cooldown_file.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        previous = 0.0
    until = max(previous, time.time() + max(0, cooldown_ms) / 1000)
    temporary = cooldown_file.with_suffix(f".{os.getpid()}.tmp")
    temporary.write_text(str(until), encoding="utf-8")
    temporary.replace(cooldown_file)
    return until


def page_message(page) -> str:
    body = compact(page.locator("body").inner_text(timeout=8000))
    for token in [
        "请求过于频繁",
        "稍后再试",
        "主推类目不属于店铺类目",
        "本周仅支持",
        "安全验证",
        "查看达人联系方式次数已达上限",
        "查看达人联系方式的机会",
    ]:
        index = body.find(token)
        if index >= 0:
            return body[max(0, index - 80) : index + 160]
    return ""


def relevant_network_diagnostics(responses: list[Any]) -> list[dict[str, Any]]:
    diagnostics: list[dict[str, Any]] = []
    for response in responses[-80:]:
        try:
            status = int(response.status)
            body = response.text() if status >= 400 else ""
            if status < 400:
                content_type = str(response.headers.get("content-type") or "")
                if "json" not in content_type:
                    continue
                body = response.text()
            compact_body = compact(body)
            markers = ("请求过于频繁", "稍后再试", "联系方式次数已达上限", "安全验证")
            if status < 400 and not any(marker in compact_body for marker in markers):
                continue
            parsed_url = urlsplit(str(response.url or ""))
            diagnostics.append({
                "status": status,
                "url": f"{parsed_url.scheme}://{parsed_url.netloc}{parsed_url.path}",
                "message": compact_body[:800],
            })
        except Exception:
            continue
    return diagnostics[-10:]


def run_candidate(
    page, candidate: dict[str, Any], delay_ms: int, output_dir: Path = OUT_DIR,
    reveal_interval_ms: int = 12000,
    stop_if_duplicate: Callable[[dict[str, Any]], bool] | None = None,
    primary_contact_only: bool = False,
) -> dict[str, Any]:
    current = dict(candidate)
    current.pop("ui_contact_remaining_skipped_reason", None)
    current["ui_contact_probe_at"] = datetime.now().isoformat(timespec="seconds")
    url = str(current.get("buyin_profile_url") or current.get("精选联盟主页") or "").strip()
    if not url:
        current["ui_contact_probe_status"] = "missing_profile_url"
        return current

    # Evidence review already loaded this exact creator in the same shop page.
    # Reuse it rather than requesting the entire profile a second time.
    reuse_profile = current.get("content_evidence_reviewed") is True and page.url == url
    if reuse_profile:
        body = compact(page.locator("body").inner_text(timeout=8000))
        reuse_profile = profile_content_ready(body) and not any(
            marker in body for marker in ("当前环境存在风险", "请求过于频繁", "验证码", "安全验证")
        )
    if not reuse_profile:
        page.goto(url, wait_until="domcontentloaded", timeout=45000)
        page.wait_for_timeout(max(3000, delay_ms))
    current["ui_contact_profile_reused"] = reuse_profile
    try:
        page.wait_for_function(
            """() => {
              const text = (document.body?.innerText || '').replace(/\\s+/g, ' ');
              return ['达人自主披露联系方式', '添加达人库', '已加达人库', '粉丝数', '带货口碑']
                .some(marker => text.includes(marker));
            }""",
            timeout=45000,
        )
    except PlaywrightTimeoutError:
        pass
    current["ui_contact_final_url"] = page.url
    current["ui_contact_page_title"] = compact(page.title())
    profile_body = compact(page.locator("body").inner_text(timeout=8000))
    current["ui_contact_page_excerpt"] = profile_body[:500]
    if not profile_content_ready(profile_body):
        if "douyinec.com" in page.url or ("立即入驻" in profile_body and "登录" in profile_body):
            current["ui_contact_probe_status"] = "login_required"
        else:
            current["ui_contact_probe_status"] = "profile_not_ready"
        return current

    add_clicked = page.evaluate(
        """() => {
          const button = Array.from(document.querySelectorAll('button')).find(item =>
            (item.innerText || item.textContent || '').includes('添加达人库') && !item.disabled);
          if (!button) return false;
          button.click();
          return true;
        }"""
    )
    buttons = visible_buttons(page)
    if add_clicked:
        page.wait_for_timeout(max(3000, delay_ms))
        current["ui_add_library_status"] = "clicked"
    elif any("已加达人库" in button.get("text", "") for button in buttons):
        current["ui_add_library_status"] = "already_added"
    else:
        current["ui_add_library_status"] = "not_found"

    before_items = contact_items(page)
    icons = unresolved_contact_icons(page, current)
    if primary_contact_only:
        icons.sort(key=lambda icon: 0 if "微信" in str(icon.get("text") or "") else 1)
    clicked = 0
    confirmations: list[dict[str, Any]] = []
    observed_responses: list[Any] = []
    response_listener = lambda response: observed_responses.append(response)
    page.on("response", response_listener)
    try:
        for icon in icons:
            if primary_contact_only:
                from creator_delivery_contract import contact_identity_values
                partial = parse_contact_items(contact_items(page))
                primary = {**current, **{f"buyin_contact_{channel}": partial[channel]
                           for channel in ("wechat", "phone", "email") if partial[channel]}}
                has_wechat = bool(contact_identity_values({"buyin_contact_wechat": primary.get("buyin_contact_wechat")}))
                wechat_available = any("微信" in str(item.get("text") or "") for item in icons)
                if contact_identity_values(primary) and (has_wechat or clicked > 0 or not wechat_available):
                    current["ui_contact_remaining_skipped_reason"] = "primary_ready_supplement_pending"
                    break
            # Only a proven strict-list collision may skip remaining channels.
            # Unique creators still receive the full phone/WeChat/email pass.
            if stop_if_duplicate is not None:
                partial = parse_contact_items(contact_items(page))
                probe = dict(current)
                for channel in ("wechat", "phone", "email"):
                    if partial[channel]:
                        probe[f"buyin_contact_{channel}"] = partial[channel]
                        probe[f"cart_contact_{channel}"] = partial[channel]
                try:
                    duplicate = stop_if_duplicate(probe)
                except Exception:
                    duplicate = False  # An unavailable audit must not skip evidence.
                if duplicate:
                    current["ui_contact_remaining_skipped_reason"] = "strict_contact_duplicate"
                    break
            # Other channels remain eligible after the first plaintext reveal.
            remaining = {item["idx"] for item in unresolved_contact_icons(page, current)}
            if icon["idx"] not in remaining:
                continue
            current["ui_contact_global_wait_ms"] = wait_for_global_contact_slot(
                page, output_dir, max(8000, reveal_interval_ms), str(current.get("contact_shop") or "")
            )
            # idx belongs to contact rows, including rows without a reveal button.
            # Indexing the shorter button list can select another contact or hang.
            button = page.locator('.index-module__contact-item___ny9bn').nth(icon["idx"]).locator(
                '.index-module__contact-item-btn___tZUqf'
            )
            for event in ("pointerdown", "mousedown", "pointerup", "mouseup", "click"):
                button.dispatch_event(event)
            clicked += 1
            page.wait_for_timeout(max(3000, delay_ms))
            confirmation = confirm_contact_view(page, max(3000, delay_ms))
            if confirmation["status"] != "not_present":
                confirmations.append(confirmation)
            if confirmation["status"] == "daily_quota_exhausted":
                break
            immediate_message = page_message(page)
            if "请求过于频繁" in immediate_message or "稍后再试" in immediate_message:
                break
    finally:
        try:
            page.remove_listener("response", response_listener)
        except Exception:
            pass

    after_items = contact_items(page)
    parsed = parse_contact_items(after_items)
    message = page_message(page)
    current["ui_contact_icon_count"] = len(icons)
    current["ui_contact_icon_clicked"] = clicked
    current["ui_contact_items_before"] = before_items
    current["ui_contact_items_after"] = after_items
    current["ui_contact_message"] = message
    current["ui_contact_network_diagnostics"] = relevant_network_diagnostics(observed_responses)
    current["ui_contact_confirmations"] = confirmations
    if confirmations:
        current["ui_contact_confirmation_status"] = confirmations[-1]["status"]
        current["ui_contact_daily_quota_remaining"] = confirmations[-1].get("remaining")

    # A partial reveal must never erase a previously saved channel.
    for channel in ("wechat", "phone", "email"):
        parsed[channel] = parsed[channel] or current.get(f"buyin_contact_{channel}") or current.get(f"cart_contact_{channel}") or ""
    parsed["contact"] = "；".join(f"{label}:{parsed[channel]}" for channel, label in (("wechat", "微信"), ("phone", "手机"), ("email", "邮箱")) if parsed[channel])
    blocked = "daily_quota_exhausted" if any(item.get("status") == "daily_quota_exhausted" for item in confirmations) or daily_quota_exhausted(message) else "rate_limited" if "请求过于频繁" in message or "稍后再试" in message else "category_not_matched" if "主推类目不属于店铺类目" in message or "本周仅支持" in message else ""
    current["ui_contact_channels_checked_at"] = datetime.now().isoformat(timespec="seconds")
    current["ui_contact_channels_status"] = blocked or ("partial" if unresolved_contact_icons(page, current) else "complete")
    current["ui_contact_remaining_masked_rows"] = [item.get("text", "") for item in unresolved_contact_icons(page, current)]
    if not blocked and current.get("ui_contact_remaining_skipped_reason") == "primary_ready_supplement_pending":
        current["ui_contact_channels_status"] = "primary_ready_supplement_pending"
    if parsed["contact"]:
        current["ui_contact_probe_status"] = "revealed"
        current["cart_contact_text"] = parsed["contact"]
        current["buyin_contact_text"] = parsed["contact"]
        current["cart_contact_wechat"] = parsed["wechat"]
        current["buyin_contact_wechat"] = parsed["wechat"]
        current["cart_contact_phone"] = parsed["phone"]
        current["buyin_contact_phone"] = parsed["phone"]
        current["cart_contact_email"] = parsed["email"]
        current["buyin_contact_email"] = parsed["email"]
        current["cart_contact_source"] = "buyin_profile_ui_contact_icon"
        current["buyin_contact_source"] = "buyin_profile_ui_contact_icon"
        current["cart_contact_probe_status"] = "revealed"
        current["buyin_contact_probe_status"] = "revealed"
        current["ui_contact_evidence"] = parsed["evidence"]
    elif any(item.get("status") == "daily_quota_exhausted" for item in confirmations) or daily_quota_exhausted(message):
        current["ui_contact_probe_status"] = "daily_quota_exhausted"
        current["cart_contact_probe_status"] = "daily_quota_exhausted"
        current["buyin_contact_probe_status"] = "daily_quota_exhausted"
    elif "主推类目不属于店铺类目" in message or "本周仅支持" in message:
        current["ui_contact_probe_status"] = "category_not_matched"
        current["cart_contact_probe_status"] = "category_not_matched"
        current["buyin_contact_probe_status"] = "category_not_matched"
    elif "请求过于频繁" in message or "稍后再试" in message:
        current["ui_contact_probe_status"] = "rate_limited"
        current["cart_contact_probe_status"] = "rate_limited"
        current["buyin_contact_probe_status"] = "rate_limited"
        current["ui_contact_rate_limit_until"] = mark_global_rate_limit(output_dir, 600000, str(current.get("contact_shop") or ""))
    elif clicked:
        current["ui_contact_probe_status"] = "clicked_not_revealed"
        current["cart_contact_probe_status"] = "clicked_not_revealed"
        current["buyin_contact_probe_status"] = "clicked_not_revealed"
    else:
        current["ui_contact_probe_status"] = "no_contact_icon"
        current["cart_contact_probe_status"] = "no_contact_icon"
        current["buyin_contact_probe_status"] = "no_contact_icon"
    if blocked:
        current["ui_contact_probe_status"] = blocked
        if blocked == "rate_limited":
            current["ui_contact_rate_limit_until"] = mark_global_rate_limit(output_dir, 600000, str(current.get("contact_shop") or ""))
    return current


def has_plain(candidate: dict[str, Any]) -> bool:
    return bool(
        candidate.get("cart_contact_wechat")
        or candidate.get("buyin_contact_wechat")
        or candidate.get("cart_contact_phone")
        or candidate.get("buyin_contact_phone")
        or candidate.get("cart_contact_email")
        or candidate.get("buyin_contact_email")
    )


def saved_contact_channels_complete(candidate: dict[str, Any]) -> bool:
    status = candidate.get("ui_contact_channels_status")
    if status == "category_not_matched":
        return True
    if status != "complete":
        return False
    for text in candidate.get("ui_contact_remaining_masked_rows", []):
        channel = "wechat" if "微信" in str(text) else "phone" if "手机" in str(text) else "email" if "邮箱" in str(text) else ""
        if not channel or not (candidate.get(f"buyin_contact_{channel}") or candidate.get(f"cart_contact_{channel}")):
            return False
    return True


def select_contact_targets(candidates: list[dict[str, Any]], shop: str, limit: int, complete_channels: bool = False) -> list[dict[str, Any]]:
    selected = [
        candidate
        for candidate in candidates
        if candidate.get("content_evidence_reviewed") is True
        and candidate.get("precontact_qualified") is True
        and (complete_channels or not has_plain(candidate))
        and not (complete_channels and saved_contact_channels_complete(candidate))
        and (complete_channels or not terminal_contact_failure(candidate))
        and (
            shop == "all"
            or compact(candidate.get("contact_shop") or candidate.get("lip_shop") or candidate.get("shop")) in ("", shop)
        )
    ]
    selected.sort(key=lambda candidate: (
        str(candidate.get("ui_contact_probe_status") or "") == "rate_limited",
        str(candidate.get("ui_contact_probe_at") or ""),
    ))
    return selected[:limit] if limit else selected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--complete-contact-channels", action="store_true")
    parser.add_argument("--input", default="")
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--shop", choices=["A", "B", "all"], required=True)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--delay-ms", type=int, default=3000)
    parser.add_argument("--reveal-interval-ms", type=int, default=18000)
    args = parser.parse_args()

    input_path = Path(args.input) if args.input else latest("*contact*queue*.json")
    payload = json.loads(input_path.read_text(encoding="utf-8"))
    candidates = [item for item in payload.get("candidates") or [] if isinstance(item, dict)]
    candidates = select_contact_targets(candidates, args.shop, args.limit, args.complete_contact_channels)
    max_count = len(candidates)

    processed: list[dict[str, Any]] = []
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output = OUT_DIR / f"ui_contact_icon_retry_{args.shop}_{stamp}.json"

    def save_checkpoint(inflight: dict[str, Any] | None = None) -> dict[str, Any]:
        snapshot = [*processed]
        if inflight and not any(
            compact(item.get("identity")) == compact(inflight.get("identity"))
            for item in snapshot
        ):
            snapshot.append(inflight)
        result = {
            **payload,
            "status": "running" if len(snapshot) < max_count else "succeeded",
            "source": str(input_path),
            "ui_contact_retry_at": datetime.now().isoformat(timespec="seconds"),
            "shop": args.shop,
            "candidate_count": len(snapshot),
            "plain_contact_count": sum(1 for item in snapshot if has_plain(item)),
            "wechat_contact_count": sum(1 for item in snapshot if item.get("cart_contact_wechat") or item.get("buyin_contact_wechat")),
            "candidates": snapshot,
        }
        temporary = output.with_suffix(".tmp")
        temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(output)
        return result

    with sync_playwright() as p:
        browser, context, _embedded_page = connect_shop(p.chromium, args.endpoint)
        page = _embedded_page
        page.set_default_timeout(15000)
        for index, candidate in enumerate(candidates):
            current = dict(candidate)
            if index >= max_count:
                current["ui_contact_probe_status"] = "limit_not_reached_this_run"
                processed.append(current)
                continue
            if has_plain(current) and not args.complete_contact_channels:
                current["ui_contact_probe_status"] = "already_has_plain"
                processed.append(current)
                continue
            try:
                current = run_candidate(
                    page, current, max(3000, args.delay_ms), OUT_DIR,
                    max(8000, args.reveal_interval_ms),
                )
                if current.get("ui_contact_probe_status") == "login_required":
                    processed.append(current)
                    processed.extend(dict(row) for row in candidates[index + 1:])
                    save_checkpoint()
                    print(json.dumps({"status": "contact_login_required", "shop": args.shop, "message": "店铺页面返回登录入口，已保存进度并停止该店铺"}, ensure_ascii=False), flush=True)
                    break
                if current.get("ui_contact_probe_status") == "rate_limited":
                    # A platform frequency-control response is a stop signal, not
                    # an invitation to retry inside a long-running worker.  Save
                    # the exact checkpoint and let the outer scheduler choose a
                    # later, single low-frequency resume window.
                    retry_until = mark_global_rate_limit(OUT_DIR, 1200000, args.shop)
                    print(json.dumps({
                        "status": "contact_platform_paused",
                        "message": "rate_limited：平台频率限制，保存进度后等待冷却",
                        "shop": args.shop,
                        "creator": current.get("nickname") or "",
                        "retry_at_epoch": retry_until,
                    }, ensure_ascii=False), flush=True)
                    processed.append(current)
                    save_checkpoint()
                    # 立即结束本轮。若继续处理后续达人，每个都会在
                    # wait_for_global_contact_slot 里阻塞等待冷却结束，
                    # 表现为「进程活着但零输出」的假死状态。
                    # 重试时机交给外层调度器（读 retry_at_epoch）。
                    for pending_item in candidates[index + 1:]:
                        processed.append(dict(pending_item))
                    break
            except PlaywrightTimeoutError as exc:
                current["ui_contact_probe_status"] = "timeout"
                current["ui_contact_error"] = str(exc)[:300]
            except Exception as exc:
                current["ui_contact_probe_status"] = "exception"
                current["ui_contact_error"] = str(exc)[:300]
                if str(exc).startswith("contact_cooldown_active:"):
                    current["ui_contact_probe_status"] = "rate_limited"
                    current["ui_contact_channels_status"] = "rate_limited"
                    processed.append(current)
                    processed.extend(dict(row) for row in candidates[index + 1:])
                    print(json.dumps({"status": "contact_platform_paused", "message": "rate_limited：当前店铺冷却中，已保存待处理名单", "shop": args.shop}, ensure_ascii=False), flush=True)
                    save_checkpoint()
                    break
            processed.append(current)
            print(json.dumps({
                "status": "contact_revealed" if has_plain(current) else "contact_progress",
                "creator": current.get("nickname") or current.get("达人昵称") or "",
                "shop": args.shop,
                "processed": len(processed),
                "total": max_count,
                "probe_status": current.get("ui_contact_probe_status"),
                "has_wechat": bool(current.get("buyin_contact_wechat") or current.get("cart_contact_wechat")),
                "has_phone": bool(current.get("buyin_contact_phone") or current.get("cart_contact_phone")),
                "has_email": bool(current.get("buyin_contact_email") or current.get("cart_contact_email")),
            }, ensure_ascii=False), flush=True)
            if len(processed) % 10 == 0 or has_plain(current):
                save_checkpoint()
            if should_stop_contact_batch(current):
                break

    result = save_checkpoint()
    result["status"] = "succeeded"
    output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    WORKER_OUT.mkdir(parents=True, exist_ok=True)
    worker_output = WORKER_OUT / output.name
    copy_if_distinct(output, worker_output)
    print(json.dumps({
                "output": str(output),
                "worker_output": str(worker_output),
                "candidate_count": result["candidate_count"],
                "plain_contact_count": result["plain_contact_count"],
                "wechat_contact_count": result["wechat_contact_count"],
                "status_counts": {
                    status: sum(1 for item in processed if item.get("ui_contact_probe_status") == status)
                    for status in sorted({str(item.get("ui_contact_probe_status") or "") for item in processed})
                },
            }, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
