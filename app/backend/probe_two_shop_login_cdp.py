from __future__ import annotations

import argparse
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from playwright.sync_api import sync_playwright

from console_io import configure_utf8_stdout
from embedded_cdp import connect_shop, is_embedded_endpoint, split_endpoint


configure_utf8_stdout()


FXG_PING_URL = "https://fxg.jinritemai.com/byteshop/ping/v2"
BUYIN_URL = "https://buyin.jinritemai.com/dashboard/servicehall/daren-square"


def probe_context(endpoint: str, storage_path: Path) -> dict[str, Any]:
    with sync_playwright() as p:
        browser, context, embedded_page = connect_shop(p.chromium, endpoint)
        page = embedded_page
        if "buyin.jinritemai.com" not in page.url:
            page.goto(BUYIN_URL, wait_until="domcontentloaded", timeout=30000)
        try:
            page.wait_for_load_state("domcontentloaded", timeout=15000)
            page.wait_for_timeout(1800)
        except Exception:
            pass

        result = page.evaluate(
            """async (url) => {
                const out = { status: 0, code: "", msg: "", text: "", url: "" };
                try {
                    const response = await fetch(url, { credentials: "include" });
                    const text = await response.text();
                    let json = null;
                    try { json = JSON.parse(text); } catch (error) {}
                    out.status = response.status;
                    out.url = response.url;
                    out.text = text.slice(0, 300);
                    out.code = json && String(json.code ?? json.st ?? "");
                    out.msg = json && String(json.msg ?? json.message ?? "");
                } catch (error) {
                    out.text = String(error);
                }
                return out;
            }""",
            FXG_PING_URL,
        )

        body_text = ""
        try:
            body_text = page.locator("body").inner_text(timeout=5000)[:1200]
        except Exception:
            pass

        code = str(result.get("code") or "")
        msg = str(result.get("msg") or result.get("text") or "")
        merchant_ok = result.get("status") == 200 and code == "0" and "未登录" not in msg
        buyin_ready = "buyin.jinritemai.com" in page.url and (
            merchant_ok
            or any(token in body_text for token in ["达人广场", "找达人", "搜达人昵称", "主推类目", "有联系方式"])
        )

        if is_embedded_endpoint(endpoint):
            _base, shop = split_endpoint(endpoint)
            storage_reference = f"embedded_partition:{shop}"
        else:
            storage_path.parent.mkdir(parents=True, exist_ok=True)
            context.storage_state(path=str(storage_path))
            storage_reference = str(storage_path)

        # Do not call browser.close(): this attaches to the user's logged-in Chrome
        # windows through CDP, and must leave those windows open.
        return {
            "endpoint": endpoint,
            "storage_state": storage_reference,
            "merchant_logged_in": bool(merchant_ok),
            "buyin_ready": bool(buyin_ready),
            "current_url": page.url,
            "fxg_ping": result,
            "body_excerpt": body_text,
        }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--shop-a", default="http://127.0.0.1:9222?shop=A")
    parser.add_argument("--shop-b", default="http://127.0.0.1:9222?shop=B")
    parser.add_argument("--out-dir", default="output/aipr-brand-task")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results = {
        "status": "login_probe_finished",
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "shops": {
            "A": probe_context(args.shop_a, out_dir / f"shopA_storage_state_{stamp}.json"),
            "B": probe_context(args.shop_b, out_dir / f"shopB_storage_state_{stamp}.json"),
        },
    }
    output = out_dir / f"two_shop_login_probe_{stamp}.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), **results}, ensure_ascii=False))


if __name__ == "__main__":
    main()
