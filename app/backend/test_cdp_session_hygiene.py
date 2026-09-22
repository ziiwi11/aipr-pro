from __future__ import annotations

import unittest

from cdp_session_hygiene import stale_automation_page_ids


class CdpSessionHygieneTest(unittest.TestCase):
    def test_keeps_one_buyin_square_and_closes_old_profile_and_douyin_pages(self):
        targets = [
            {"id": "square", "type": "page", "url": "https://buyin.jinritemai.com/dashboard/servicehall/daren-square"},
            {"id": "profile", "type": "page", "url": "https://buyin.jinritemai.com/dashboard/servicehall/daren-profile?uid=1"},
            {"id": "douyin", "type": "page", "url": "https://www.douyin.com/user/abc"},
            {"id": "docs", "type": "page", "url": "https://example.com/docs"},
            {"id": "worker", "type": "worker", "url": "https://www.douyin.com/worker.js"},
        ]
        self.assertEqual(stale_automation_page_ids(targets), ["profile", "douyin"])

    def test_keeps_first_buyin_page_when_square_is_not_open(self):
        targets = [
            {"id": "profile-a", "type": "page", "url": "https://buyin.jinritemai.com/daren-profile?uid=1"},
            {"id": "profile-b", "type": "page", "url": "https://buyin.jinritemai.com/daren-profile?uid=2"},
        ]
        self.assertEqual(stale_automation_page_ids(targets), ["profile-b"])


if __name__ == "__main__":
    unittest.main()
