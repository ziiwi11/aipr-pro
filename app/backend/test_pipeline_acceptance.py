from __future__ import annotations

import unittest

from pipeline_acceptance import allocate_shop_targets, creator_name_key, validate_candidate_count


class PipelineAcceptanceTest(unittest.TestCase):
    def test_rejects_empty_or_short_collection(self) -> None:
        with self.assertRaisesRegex(ValueError, "candidate_count_below_target"):
            validate_candidate_count(0, 10)
        with self.assertRaisesRegex(ValueError, "candidate_count_below_target"):
            validate_candidate_count(9, 10)

    def test_accepts_requested_candidate_count(self) -> None:
        self.assertEqual(validate_candidate_count(10, 10), 10)

    def test_allocates_target_across_two_shops(self) -> None:
        self.assertEqual(allocate_shop_targets(10, 2), [5, 5])
        self.assertEqual(allocate_shop_targets(11, 2), [6, 5])

    def test_creator_name_key_deduplicates_cross_shop_encrypted_ids(self) -> None:
        self.assertEqual(creator_name_key(" 小羊 多米✨ "), creator_name_key("小羊多米✨"))


if __name__ == "__main__":
    unittest.main()
