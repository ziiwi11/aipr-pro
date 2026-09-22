import unittest

from creator_delivery_contract import score_candidate, select_delivery_candidates


def candidate(identity: str, contact: str | None = None, sales: int = 20000) -> dict:
    return {
        "identity": identity,
        "nickname": f"达人{identity}",
        "talent_level": "LV2",
        "category": "服饰内衣",
        "profile_text": "服饰内衣 内容数据 直播 0个 视频 20个 真人试穿",
        "douyin_content_text": "真人试穿 提臀塑形裤 上身展示",
        "buyin_profile_url": f"https://example.test/{identity}",
        "douyin_homepage": f"https://douyin.com/user/{identity}",
        "content_evidence_reviewed": True,
        "monthly_sales_value": sales,
        "buyin_contact_wechat": f"wechat_{identity}" if contact is None else contact,
    }


class DeliveryGateTest(unittest.TestCase):
    def setUp(self):
        self.rules = {
            "threshold": 78,
            "category": "服饰内衣",
            "creatorLevels": [2, 3, 4],
            "minimumMonthlySales": 10000,
            "contentType": "真人口播",
            "requireContact": True,
            "exclusions": [],
        }

    def test_rejects_candidate_below_required_sales(self):
        result = score_candidate(candidate("low", sales=9999), self.rules)
        self.assertEqual(result["decision"], "淘汰")
        self.assertIn("销售额", result["reason"])

    def test_selects_only_unique_qualified_candidates_with_plain_contacts(self):
        rows = [candidate("1"), candidate("1"), candidate("2", contact=""), candidate("3")]
        selected = select_delivery_candidates(rows, self.rules, 2)
        self.assertEqual([row["identity"] for row in selected], ["1", "3"])

    def test_does_not_pad_an_incomplete_delivery(self):
        selected = select_delivery_candidates([candidate("1")], self.rules, 2)
        self.assertEqual(len(selected), 1)

    def test_rejects_reused_plain_contact_across_distinct_creators(self):
        rows = [candidate("1", contact="shared_contact"), candidate("2", contact="shared_contact"), candidate("3")]
        selected = select_delivery_candidates(rows, self.rules, 3)
        self.assertEqual([row["identity"] for row in selected], ["1", "3"])

    def test_rejects_plain_contact_already_delivered_in_prior_round(self):
        rules = {**self.rules, "excludeContacts": ["shared_contact"]}
        rows = [candidate("1", contact="shared_contact"), candidate("2", contact="fresh_contact")]
        selected = select_delivery_candidates(rows, rules, 2)
        self.assertEqual([row["identity"] for row in selected], ["2"])

    def test_navigation_and_zero_live_markers_do_not_trigger_hard_exclusions(self):
        row = candidate("clean", sales=18)
        row["profile_text"] = (
            "首页 找达人 数据统计时间：2026/06/18 至 2026/07/18 "
            "直播 0个；0次 视频 69件；¥5万-¥10万"
        )
        row["douyin_content_text"] = "直播 导航 热门美食 母婴推荐"
        row["content_evidence"] = ["真人试穿 提臀塑形裤 上身穿搭"]
        rules = {**self.rules, "exclusions": ["直播", "美食", "母婴", "男性"]}

        result = score_candidate(row, rules)

        self.assertEqual(result["decision"], "推荐建联")
        self.assertEqual(result["sales"], 50000)


if __name__ == "__main__":
    unittest.main()
