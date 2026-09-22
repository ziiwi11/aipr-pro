from __future__ import annotations

import unittest

from contact_icons_single import (
    confirm_contact_view,
    daily_quota_exhausted,
    parse_contact_items,
    parse_contact_view_confirmation,
    relevant_network_diagnostics,
    should_stop_contact_batch,
)


class FakeMouse:
    def __init__(self) -> None:
        self.clicks: list[tuple[float, float]] = []

    def click(self, x: float, y: float) -> None:
        self.clicks.append((x, y))


class FakePage:
    def __init__(self, payload: dict[str, object] | None) -> None:
        self.payload = payload
        self.mouse = FakeMouse()
        self.waits: list[int] = []
        self.evaluations = 0

    def evaluate(self, _script: str):
        self.evaluations += 1
        return self.payload

    def wait_for_timeout(self, delay_ms: int) -> None:
        self.waits.append(delay_ms)


class FakeResponse:
    def __init__(self, status: int, url: str, body: str, content_type: str = "application/json") -> None:
        self.status = status
        self.url = url
        self._body = body
        self.headers = {"content-type": content_type}

    def text(self) -> str:
        return self._body


class ContactIconsChineseTest(unittest.TestCase):
    def test_parses_revealed_chinese_contact_labels(self) -> None:
        parsed = parse_contact_items([
            "达人手机号：13800138000",
            "达人微信号：osmana_creator",
            "达人邮箱：creator@example.com",
        ])
        self.assertEqual(parsed["phone"], "13800138000")
        self.assertEqual(parsed["wechat"], "osmana_creator")
        self.assertEqual(parsed["email"], "creator@example.com")
        self.assertIn("微信:osmana_creator", parsed["contact"])

    def test_ignores_masked_values(self) -> None:
        parsed = parse_contact_items(["达人手机号：***********", "达人微信号：***********"])
        self.assertEqual(parsed["contact"], "")

    def test_parses_contact_view_confirmation_quota(self) -> None:
        parsed = parse_contact_view_confirmation({
            "text": "今日还剩下3次查看达人联系方式的机会，确认查看该达人的联系方式？",
            "confirm": {"x": 320, "y": 240},
        })
        self.assertEqual(parsed["remaining"], 3)
        self.assertEqual(parsed["status"], "confirmation_required")

    def test_confirms_contact_view_once_with_safe_delay(self) -> None:
        page = FakePage({
            "text": "今日还剩下3次查看达人联系方式的机会，确认查看该达人的联系方式？",
            "confirm": {"x": 320, "y": 240},
        })
        result = confirm_contact_view(page, 3000)
        self.assertEqual(result["status"], "confirmed")
        self.assertEqual(page.mouse.clicks, [])
        self.assertEqual(page.evaluations, 2)
        self.assertEqual(page.waits, [3000])

    def test_does_not_click_when_daily_quota_is_exhausted(self) -> None:
        page = FakePage({
            "text": "今日还剩下0次查看达人联系方式的机会",
            "confirm": {"x": 320, "y": 240},
        })
        result = confirm_contact_view(page, 3000)
        self.assertEqual(result["status"], "daily_quota_exhausted")
        self.assertEqual(page.mouse.clicks, [])

    def test_recognizes_daily_contact_view_limit_toast(self) -> None:
        self.assertTrue(daily_quota_exhausted("查看达人联系方式次数已达上限"))

    def test_stops_contact_batch_after_daily_quota_exhaustion(self) -> None:
        self.assertTrue(should_stop_contact_batch({"ui_contact_probe_status": "daily_quota_exhausted"}))
        self.assertFalse(should_stop_contact_batch({"ui_contact_probe_status": "revealed"}))

    def test_network_diagnostics_keep_rate_limit_but_drop_query_and_success_payload(self) -> None:
        responses = [
            FakeResponse(200, "https://buyin.example/contact?uid=secret", '{"wechat":"private-id"}'),
            FakeResponse(200, "https://buyin.example/contact?uid=secret", '{"message":"请求过于频繁，请稍后再试"}'),
        ]
        diagnostics = relevant_network_diagnostics(responses)
        self.assertEqual(len(diagnostics), 1)
        self.assertEqual(diagnostics[0]["url"], "https://buyin.example/contact")
        self.assertNotIn("private-id", str(diagnostics))


if __name__ == "__main__":
    unittest.main()
