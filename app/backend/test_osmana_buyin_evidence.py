from __future__ import annotations

import unittest

from verify_osmana_buyin_evidence_cdp import has_qualifying_short_video_underwear, parse_product_payload


class OsmanaBuyinEvidenceTest(unittest.TestCase):
    def test_parses_product_level_sales_ranges(self) -> None:
        payload = {
            "code": 0,
            "data": {
                "product_info": [
                    {
                        "good_info": {
                            "title": "高腰收腹提臀塑形裤女",
                            "pidStr": "123",
                            "detail_url": "https://example.test/123",
                        },
                        "goods_sale_low": 10000,
                        "goods_sale_high": 25000,
                        "related_video_num": 4,
                        "related_live_times": 0,
                    },
                    {
                        "good_info": {"title": "厚底洞洞鞋女", "pidStr": "456"},
                        "goods_sale_low": 25000,
                        "goods_sale_high": 50000,
                    },
                ]
            },
        }

        rows = parse_product_payload(payload)

        self.assertEqual(rows[0]["title"], "高腰收腹提臀塑形裤女")
        self.assertEqual(rows[0]["sales_low"], 10000)
        self.assertEqual(rows[0]["sales_high"], 25000)
        self.assertEqual(rows[0]["product_id"], "123")
        self.assertEqual(rows[0]["related_video_num"], 4)
        self.assertEqual(rows[0]["related_live_times"], 0)
        self.assertEqual(rows[1]["title"], "厚底洞洞鞋女")

    def test_ignores_invalid_or_failed_payload(self) -> None:
        self.assertEqual(parse_product_payload({"code": 11001, "data": {}}), [])
        self.assertEqual(parse_product_payload({"code": 0, "data": None}), [])

    def test_detects_short_video_underwear_at_or_above_threshold(self) -> None:
        qualified = [{"is_underwear": True, "sales_low": 10001, "related_video_num": 2, "related_live_times": 0}]
        live = [{"is_underwear": True, "sales_low": 25000, "related_video_num": 2, "related_live_times": 1}]
        boundary = [{"is_underwear": True, "sales_low": 10000, "related_video_num": 2, "related_live_times": 0}]
        self.assertTrue(has_qualifying_short_video_underwear(qualified))
        self.assertFalse(has_qualifying_short_video_underwear(live))
        self.assertTrue(has_qualifying_short_video_underwear(boundary))


if __name__ == "__main__":
    unittest.main()
