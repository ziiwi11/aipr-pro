import unittest
from finalize_creator_delivery import batch_new_candidates

class BatchDeliveryScopeTests(unittest.TestCase):
    def test_rotated_identity_is_historical_and_only_new_strong_identity_exports(self):
        before=[{"identity":"old-encrypted","douyin_id":"same","buyin_contact_wechat":"same_contact"}]
        current=[{"identity":"new-encrypted","douyin_id":"same"},{"identity":"new","douyin_id":"new-dy"}]
        self.assertEqual(batch_new_candidates(current,before),[current[1]])
        self.assertEqual(current[0]["identity"],"new-encrypted")
    def test_weak_baseline_cannot_hide_rows(self):
        with self.assertRaises(ValueError):batch_new_candidates([{"identity":"u"}],[{"nickname":"u"}])
