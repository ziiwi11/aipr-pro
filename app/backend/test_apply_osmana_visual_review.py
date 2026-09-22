from __future__ import annotations

import unittest

from apply_osmana_visual_review import apply_visual_decisions


class ApplyOsmanaVisualReviewTest(unittest.TestCase):
    def test_applies_review_by_identity_and_recalculates_evaluation(self) -> None:
        candidate = {
            "identity": "creator-1",
            "shop": "B",
            "nickname": "真人达人",
            "talent_level": "LV3",
            "main_sale_type": "纯短视频",
            "profile_text": "165cm 49kg",
            "content_evidence_reviewed": True,
            "douyin_content_text": "收腹提臀塑形裤真人试穿",
            "buyin_contact_wechat": "wx_test",
            "products_30d": [{
                "title": "高腰收腹提臀塑形裤",
                "sales_low": 50000,
                "sales_high": 100000,
                "related_video_num": 6,
                "related_live_times": 0,
            }],
        }
        strategy = {
            "minimumLevel": 2,
            "heightCm": {"min": 155, "max": 170},
            "weightJin": {"min": 80, "max": 110},
            "minimumUnderwearProductSales": 10000,
            "requirePlainContact": True,
        }
        decisions = [{"identity": "creator-1", "visual_persona_verified": True, "visual_review_note": "女性真人试穿"}]

        reviewed = apply_visual_decisions([candidate], decisions, strategy)

        self.assertTrue(reviewed[0]["visual_persona_verified"])
        self.assertEqual(reviewed[0]["visual_review_status"], "approved")
        self.assertTrue(reviewed[0]["osmana_evaluation"]["qualified"])

    def test_rejected_visual_never_qualifies(self) -> None:
        candidate = {"identity": "creator-2", "shop": "A", "nickname": "商品号"}
        decisions = [{"identity": "creator-2", "visual_persona_verified": False, "visual_review_note": "纯商品画面"}]

        reviewed = apply_visual_decisions([candidate], decisions, {"requirePlainContact": False})

        self.assertFalse(reviewed[0]["visual_persona_verified"])
        self.assertEqual(reviewed[0]["visual_review_status"], "rejected")
        self.assertIn("visual_persona_unverified", reviewed[0]["osmana_evaluation"]["failures"])


    def test_manual_review_can_confirm_content_evidence(self) -> None:
        candidate = {
            "identity": "creator-3",
            "shop": "A",
            "nickname": "manual-review",
            "content_evidence_reviewed": True,
            "content_text_matched": False,
            "content_evidence": [],
        }
        decisions = [{
            "identity": "creator-3",
            "visual_persona_verified": True,
            "content_evidence_reviewed": True,
            "content_text_matched": True,
            "content_evidence": ["Manual review confirmed female underwear presentation."],
        }]

        reviewed = apply_visual_decisions([candidate], decisions, {"requirePlainContact": False})

        self.assertTrue(reviewed[0]["content_evidence_reviewed"])
        self.assertTrue(reviewed[0]["content_text_matched"])
        self.assertEqual(
            reviewed[0]["content_evidence"],
            ["Manual review confirmed female underwear presentation."],
        )


if __name__ == "__main__":
    unittest.main()
