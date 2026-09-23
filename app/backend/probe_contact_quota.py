#!/usr/bin/env python3
"""风控额度探测（只读）

流程：进达人详情页 → 派发完整事件链点击联系按钮 → 读弹窗「还剩下 N 次」→ 不确认

关键：点击必须派发 pointerdown/mousedown/pointerup/mouseup/click 完整序列，
单纯 mouse.click 不会触发平台弹窗（与 contact_icons_single.py 一致）。
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from console_io import configure_utf8_stdout  # noqa: E402
configure_utf8_stdout()
from embedded_cdp import connect_shop  # noqa: E402

CONTACT_BTN = ".index-module__contact-item-btn___tZUqf"
CONTACT_ITEM = ".index-module__contact-item___ny9bn"


def emit(p: dict) -> None:
    print(json.dumps(p, ensure_ascii=False), flush=True)


def read_dialog(page) -> dict:
    return page.evaluate(
        """() => {
          const sels = '[role="dialog"], .auxo-modal-wrap, .auxo-modal';
          for (const d of document.querySelectorAll(sels)) {
            const t = (d.innerText || '').replace(/\\s+/g, ' ').trim();
            if (t.includes('联系方式') || t.includes('机会')) {
              const m = t.match(/还剩下\\s*(\\d+)\\s*次/);
              return { text: t.slice(0, 200), remaining: m ? Number(m[1]) : null };
            }
          }
          const body = (document.body.innerText || '').replace(/\\s+/g, ' ');
          const m = body.match(/还剩下\\s*(\\d+)\\s*次/);
          if (m) return { text: 'body_match', remaining: Number(m[1]) };
          return null;
        }"""
    )


def probe(page, uid: str, delay_ms: int = 3000) -> dict:
    url = f"https://buyin.jinritemai.com/dashboard/servicehall/daren-profile?uid={uid}"
    page.goto(url, wait_until="domcontentloaded", timeout=45000)
    page.wait_for_timeout(8000)

    n_items = page.locator(CONTACT_ITEM).count()
    n_btns = page.locator(CONTACT_BTN).count()
    if not n_btns:
        return {"ok": False, "reason": "no_contact_btn", "items": n_items, "btns": n_btns}

    # 派发完整事件链（与 contact_icons_single.py 一致）
    button = page.locator(CONTACT_BTN).first
    for ev in ("pointerdown", "mousedown", "pointerup", "mouseup", "click"):
        try:
            button.dispatch_event(ev)
        except Exception:
            pass
    page.wait_for_timeout(max(3000, delay_ms))

    dialog = read_dialog(page)

    # 关闭弹窗（不确认）
    page.evaluate(
        """() => {
          const sels = '[role="dialog"], .auxo-modal-wrap, .auxo-modal';
          for (const d of document.querySelectorAll(sels)) {
            const btn = Array.from(d.querySelectorAll('button')).find((b) => {
              const t = (b.innerText || '').trim();
              return t === '取消' || t === '关闭';
            });
            if (btn) { btn.click(); return true; }
          }
          return false;
        }"""
    )

    return {
        "ok": True,
        "items": n_items,
        "btns": n_btns,
        "dialog_text": ((dialog or {}).get("text") or "")[:180],
        "remaining": (dialog or {}).get("remaining"),
        "url": page.url[:120],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--shop", default="B", choices=["A", "B"])
    ap.add_argument("--uids-file", required=True, help="候选池 JSON")
    ap.add_argument("--limit", type=int, default=1)
    args = ap.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    pool = json.loads(Path(args.uids_file).read_text(encoding="utf-8"))
    cands = (pool.get("candidates") or [])[: args.limit]

    from playwright.sync_api import sync_playwright

    records = []
    with sync_playwright() as p:
        _b, _c, page = connect_shop(
            p.chromium, f"http://127.0.0.1:9222?shop={args.shop}", timeout=30000
        )
        for c in cands:
            uid = str(c.get("identity") or "").strip()
            nick = str(c.get("nickname") or "?")[:16]
            if not uid:
                continue
            try:
                r = probe(page, uid)
                rec = {"shop": args.shop, "uid": uid[:40], "nickname": nick,
                       "at": datetime.now().isoformat(timespec="seconds"), **r}
                records.append(rec)
                emit({"status": "quota_probe", "nickname": nick,
                      "remaining": r.get("remaining"), "reason": r.get("reason", "ok"),
                      "dialog": (r.get("dialog_text") or "")[:110]})
            except Exception as exc:
                emit({"status": "probe_failed", "nickname": nick, "error": str(exc)[:120]})

    log = out_dir / "quota-probe.jsonl"
    with log.open("w", encoding="utf-8") as fh:
        for r in records:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")

    emit({"status": "probe_finished", "count": len(records),
          "remaining": [r.get("remaining") for r in records], "log": str(log)})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
