from __future__ import annotations

import unittest

from build_osmana_final_pool import build_final_pool


class BuildOsmanaFinalPoolTest(unittest.TestCase):
    def setUp(self) -> None:
        self.strategy = {
            "targetCount": 500,
            "minimumLevel": 2,
            "heightCm": {"min": 155, "max": 170},
            "weightJin": {"min": 80, "max": 110},
            "minimumUnderwearProductSales": 10000,
            "requirePlainContact": True,
        }

    def evidence_candidate(self) -> dict:
        return {
            "identity": "creator-1",
            "nickname": "真人塑形达人",
            "shop": "A",
            "talent_level": "LV3",
            "main_sale_type": "纯短视频",
            "profile_text": "165cm 49kg",
            "content_evidence_reviewed": True,
            "visual_persona_verified": True,
            "douyin_content_text": "收腹提臀塑形裤真人试穿",
            "products_30d": [{
                "title": "高腰收腹提臀塑形裤",
                "sales_low": 50000,
                "related_video_num": 4,
                "related_live_times": 0,
            }],
        }

    def test_merges_contact_then_emits_only_strictly_qualified_candidate(self) -> None:
        evidence = {"candidates": [self.evidence_candidate()]}
        contact = {"candidates": [{"identity": "creator-1", "buyin_contact_wechat": "wx_creator_1"}]}

        result = build_final_pool([evidence, contact], self.strategy, 500)

        self.assertEqual(result["qualified_count"], 1)
        self.assertEqual(result["status"], "incomplete")
        self.assertEqual(result["remaining_count"], 499)
        self.assertEqual(result["candidates"][0]["buyin_contact_wechat"], "wx_creator_1")
        self.assertTrue(result["candidates"][0]["osmana_evaluation"]["qualified"])

    def test_deduplicates_identity_and_rejects_live_associated_product(self) -> None:
        row = self.evidence_candidate()
        row["products_30d"][0]["related_live_times"] = 1
        row["buyin_contact_wechat"] = "wx_live"

        result = build_final_pool([{"candidates": [row, dict(row)]}], self.strategy, 500)

        self.assertEqual(result["unique_candidate_count"], 1)
        self.assertEqual(result["qualified_count"], 0)
        self.assertEqual(result["candidates"], [])

    def test_deduplicates_different_encrypted_ids_for_same_douyin_account(self) -> None:
        first = self.evidence_candidate()
        first["identity"] = "encrypted-a"
        first["douyin_id"] = "public-douyin-1"
        first["buyin_contact_wechat"] = "wx_same"
        second = dict(first)
        second["identity"] = "encrypted-b"

        result = build_final_pool([{"candidates": [first, second]}], self.strategy, 500)

        self.assertEqual(result["unique_candidate_count"], 1)
        self.assertEqual(result["qualified_count"], 1)


if __name__ == "__main__":
    unittest.main()
