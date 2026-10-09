import unittest
from verify_creator_evidence_cdp import saved_review_candidates, compare_visible_contacts, fresh_contact_probe_input

class SavedReviewTest(unittest.TestCase):
    def test_bounded_missing_only_and_resume(self):
        rows = [{"buyin_uid": str(i), "evidence_screenshots": []} for i in range(30)]
        rows.insert(0, {"buyin_uid": "complete", "evidence_screenshots": ["old.jpg"]})
        selected = saved_review_candidates({"candidates": rows}, {"records": [{"identity": "0", "screenshots": ["new.jpg"]}]}, 100)
        self.assertEqual(len(selected), 20)
        self.assertNotIn("complete", [r["buyin_uid"] for r in selected])
        self.assertFalse(rows[1]["evidence_screenshots"])

    def test_numeric_wechat_remains_wechat_and_match_is_not_reachability(self):
        result = compare_visible_contacts({"buyin_contact_wechat": "13800000000", "buyin_contact_phone": "13900000000"}, {"wechat": "13800000000", "phone": "13911111111"})
        self.assertEqual(result["channels"]["wechat"], "platform_match")
        self.assertEqual(result["channels"]["phone"], "platform_mismatch")
        self.assertEqual(result["reachability"], "unverified")
        self.assertEqual(result["messages_sent"], 0)

    def test_fresh_probe_cannot_fall_back_to_saved_contact(self):
        saved = {"buyin_uid": "u", "buyin_profile_url": "https://example/profile", "buyin_contact_wechat": "old", "cart_contact_phone": "oldphone"}
        fresh = fresh_contact_probe_input(saved, "A")
        self.assertNotIn("buyin_contact_wechat", fresh)
        self.assertNotIn("cart_contact_phone", fresh)
        self.assertEqual(saved["buyin_contact_wechat"], "old")
        self.assertEqual(fresh["contact_shop"], "A")
