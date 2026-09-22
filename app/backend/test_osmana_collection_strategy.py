from __future__ import annotations

import unittest

from collect_osmana_candidates_cdp import candidate_from_search_item, precursor_eligible


class OsmanaCollectionStrategyTest(unittest.TestCase):
    def search_item(self) -> dict:
        return {
            "author_base": {
                "uid": "secure-uid",
                "nickname": "塑形达人",
                "fans_num": 42000,
                "gender": 2,
                "author_level": 3,
                "aweme_id": "douyin-123",
            },
            "author_tag": {
                "main_cate": ["服饰内衣", "美妆"],
                "contact_icon": "达人自主披露联系方式，你可点击小眼睛进行查看",
            },
            "author_sale": {"sale_d30_low": 25000, "sale_d30_high": 50000, "main_sale_type": "短视频为主"},
            "author_video": {"all_video_num_30d": 18, "video_sale_low": 25000, "video_sale_high": 50000},
            "latest_content": {"latest_video": {"title": "收腹提臀裤真人试穿"}},
        }

    def test_builds_candidate_from_nested_search_response(self) -> None:
        row = candidate_from_search_item(self.search_item(), "提臀塑形裤", "A")
        self.assertEqual(row["nickname"], "塑形达人")
        self.assertEqual(row["talent_level"], "LV3")
        self.assertEqual(row["douyin_id"], "douyin-123")
        self.assertEqual(row["monthly_sales_low"], 25000)
        self.assertTrue(row["contact_visible"])
        self.assertEqual(row["main_sale_type"], "短视频为主")
        self.assertEqual(row["video_sales_low"], 25000)
        self.assertIn("author_level=3", row["buyin_profile_url"])

    def test_precursor_requires_female_lv2_underwear_sales_and_contact(self) -> None:
        row = candidate_from_search_item(self.search_item(), "提臀塑形裤", "A")
        self.assertTrue(precursor_eligible(row))

        for field, value in (
            ("gender", 1),
            ("talent_level", "LV1"),
            ("category", "美妆"),
            ("monthly_sales_low", 9999),
            ("contact_visible", False),
            ("main_sale_type", "直播为主"),
            ("video_sales_low", 9999),
        ):
            rejected = dict(row)
            rejected[field] = value
            self.assertFalse(precursor_eligible(rejected), field)


if __name__ == "__main__":
    unittest.main()
